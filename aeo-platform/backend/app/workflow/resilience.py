"""Three-layer resilience model for Specta AI workflow.

Layer 1: Call-level retry (handled inline by each agent)
Layer 2: Agent-level degradation (DegradationRegistry)
Layer 3: Platform-level circuit breaker (CircuitBreaker)
"""

import logging
import time
from enum import Enum
from threading import Lock
from typing import Any

from app.workflow.events import send_system_notice_event

logger = logging.getLogger(__name__)


# ============================================================================
# Layer 2: Agent-level Degradation Registry
# ============================================================================


class DegradationRegistry:
    """Agent-level degradation strategy registry.

    Defines fallback behavior when an agent fails:
    - should_block: whether failure blocks the entire pipeline
    - fallback_message: user-facing degradation notice

    NOTE: State mutation logic lives inside each agent node (e.g. A2's
    user_decisions merge), not in this registry. A4's dynamic message
    construction also lives in nodes_a4.py.
    """

    STRATEGIES: dict[str, dict[str, Any]] = {
        "A2": {
            "should_block": False,
            "fallback_message": (
                "用户画像生成未能完成，已自动切换为品牌全景模式继续分析。"
                "后续问题将基于品牌整体信息生成，不按用户画像分类。"
            ),
        },
        "A4": {
            "should_block": False,
            "min_platforms": 2,
            "partial_message_template": (
                "{success_count} 个平台数据获取成功，"
                "{fail_count} 个平台暂时不可用。基于已有数据继续分析。"
            ),
            "total_fail_message": (
                "所有平台数据获取均失败，无法继续分析。"
                "请检查网络连接后重试。"
            ),
        },
        "A5": {
            "should_block": False,
            "fallback_message": (
                "高级分析报告生成遇到问题，已基于原始数据生成简要报告。"
            ),
        },
    }

    @classmethod
    def get_strategy(cls, agent_step: str) -> dict[str, Any] | None:
        """Get degradation strategy for the given agent."""
        return cls.STRATEGIES.get(agent_step)

    @classmethod
    def should_block_pipeline(cls, agent_step: str) -> bool:
        """Whether this agent's failure should block the pipeline."""
        strategy = cls.STRATEGIES.get(agent_step)
        if strategy is None:
            return True  # Unregistered agents block by default
        return strategy.get("should_block", True)

    @classmethod
    async def send_degradation_notice(
        cls,
        session_id: str,
        agent_step: str,
        context: dict[str, Any] | None = None,
    ) -> None:
        """Send a degradation notice to the user via WebSocket."""
        strategy = cls.STRATEGIES.get(agent_step)
        if not strategy:
            return

        message = strategy.get("fallback_message", "")

        # A4 special handling: build message dynamically from context
        if agent_step == "A4" and context:
            success_count = context.get("success_count", 0)
            fail_count = context.get("fail_count", 0)
            if success_count >= strategy.get("min_platforms", 2):
                message = strategy["partial_message_template"].format(
                    success_count=success_count, fail_count=fail_count
                )
            else:
                message = strategy["total_fail_message"]

        if not message:
            return

        # A4 special handling: structured platform_status notice
        if agent_step == "A4" and context:
            success_count = context.get("success_count", 0)
            fail_count = context.get("fail_count", 0)

            # Determine level based on success_count
            if success_count >= 2:
                level = "info"
            elif success_count >= 1:
                level = "warning"
            else:
                level = "error"

            # Build platforms list from PLATFORMS config with per-platform status
            platform_statuses = context.get("platform_statuses", {})
            platforms_list: list[dict[str, Any]] = []
            try:
                from app.workflow.nodes_a4 import PLATFORMS as A4_PLATFORMS

                for key, cfg in A4_PLATFORMS.items():
                    status = platform_statuses.get(key, "failed")
                    platforms_list.append({
                        "name": cfg.get("name", key),
                        "key": key,
                        "status": status,
                    })
            except ImportError:
                pass

            await send_system_notice_event(
                session_id,
                subtype="platform_status",
                level=level,
                title="平台数据获取状态",
                description=message,
                impact=f"{success_count} 个平台成功, {fail_count} 个平台失败",
                platforms=platforms_list if platforms_list else None,
            )
        else:
            # A2 / A5 degradation notice
            await send_system_notice_event(
                session_id,
                subtype="degradation",
                level="warning",
                title=f"{agent_step} 降级通知",
                description=message,
                impact=message,
            )

        logger.info(
            "[Resilience] Sent degradation notice for %s: %s",
            agent_step,
            message[:80] + "...",
        )


# ============================================================================
# Layer 3: Platform-level Circuit Breaker
# ============================================================================


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """In-process circuit breaker for Browser platforms (Kimi/DeepSeek).

    State machine:
        CLOSED  --[N consecutive failures]--> OPEN
        OPEN    --[cooldown elapsed]--------> HALF_OPEN
        HALF_OPEN --[one success]-----------> CLOSED
        HALF_OPEN --[one failure]-----------> OPEN

    Thread-safe: all state transitions are guarded by threading.Lock.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300.0,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: float = 0.0
        self._lock = Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if (
                    time.monotonic() - self._last_failure_time
                    >= self.cooldown_seconds
                ):
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        "[CircuitBreaker:%s] OPEN -> HALF_OPEN "
                        "(cooldown %.0fs elapsed)",
                        self.name,
                        self.cooldown_seconds,
                    )
            return self._state

    def allow_request(self) -> bool:
        """Whether a request is currently allowed."""
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        if current_state == CircuitState.HALF_OPEN:
            return True  # Allow one probe request
        # OPEN
        return False

    def record_success(self) -> None:
        """Record a successful request."""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(
                    "[CircuitBreaker:%s] HALF_OPEN -> CLOSED (success)",
                    self.name,
                )
                self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """Record a failed request."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.info(
                    "[CircuitBreaker:%s] HALF_OPEN -> OPEN (probe failed)",
                    self.name,
                )
            elif self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        "[CircuitBreaker:%s] CLOSED -> OPEN "
                        "(consecutive failures: %d)",
                        self.name,
                        self._failure_count,
                    )
                    self._state = CircuitState.OPEN

    def reset(self) -> None:
        """Manually reset the breaker to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0


# Global breaker instances (in-process singletons, shared across sessions).
# Platform availability is global state -- not session-specific.
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = Lock()


def get_circuit_breaker(platform: str) -> CircuitBreaker:
    """Get or lazily create a circuit breaker for the given platform."""
    with _breakers_lock:
        if platform not in _breakers:
            _breakers[platform] = CircuitBreaker(
                name=platform,
                failure_threshold=3,
                cooldown_seconds=300.0,
            )
        return _breakers[platform]
