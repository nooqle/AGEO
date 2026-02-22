# PRD: P0 端到端可靠性 + BWVS v2 多维评分

> **文档状态**: Draft (审查修正后)
> **作者**: Marty Cagan (产品经理)
> **创建日期**: 2026-02-20
> **优先级**: P0
> **依赖文档**: `D:\AGEO\docs\reform-plan.md` (改造方案 v2.0)

---

## 一、背景与动机

### 1.1 我们在解决什么问题?

Specta AI 的端到端分析流水线 (A1->A2->A3->A4->A5) 当前成功率约 50%（跳过 A2 时），含 A2 仅约 2.5%。这意味着每两次品牌分析只有一次能顺利完成，严重影响用户体验和产品可信度。

同时，核心指标 BWVS 当前仅等于 `mention_rate * 100`，无法区分"被提及但评价负面"与"被推荐且权威引用"这两种截然不同的品牌可见性状态。品牌客户需要多维度、可解释的评分体系来指导 AEO 优化决策。

### 1.2 谁有这个问题? 有多痛?

**目标用户**: 品牌客户的市场部/运营部人员

**痛点程度**: Hair on fire (高频、阻塞性)

- **可靠性**: 用户发起品牌分析后等待数分钟，却以失败告终且没有可用结果 -- 这是最差的用户体验。用户不会给第二次机会。
- **评分维度**: 品牌客户向管理层汇报时，需要的不仅是"被提及了多少次"，还需要知道"提及的质量如何"、"在哪些平台有覆盖"、"是正面还是负面提及"。单一的提及率无法支撑决策。

### 1.3 他们现在怎么解决?

- 可靠性: 反复重试，或放弃使用平台
- 评分维度: 手动导出原始数据，自行分析 -- 这违背了产品"自然语言对话驱动 AEO"的核心定位

### 1.4 假设与预期

**假设**: 通过三层韧性模型 + BWVS 多维评分，可以将端到端成功率提升到 80%+，同时让品牌评分具备真实的决策参考价值。

**预期效果**:
| 指标 | 当前 | 目标 |
|------|------|------|
| 端到端成功率（含 A2） | ~2.5% | 80%+ |
| 端到端成功率（跳过 A2） | ~50% | 90%+ |
| BWVS 评分维度 | 1 维（提及率） | 4 维（提及率+情感+覆盖+引用） |
| 用户对失败的感知 | 流程中断、无结果 | 降级提示、部分结果可用 |

---

## 二、功能一: 三层韧性模型

### 2.1 Problem Statement

当前失败源分布:
- **A2 LLM 输出截断** (~95% A2 失败率): JSON Schema 过复杂导致 `finish_reason=length`
- **A4 Browser 超时** (~30-40% Browser 平台失败): Kimi/DeepSeek 的 Playwright 抓取不稳定
- **Orchestrator 不区分错误类型**: 所有失败走同一条路径，无降级策略

### 2.2 Target User

- 所有使用 Specta AI 进行品牌分析的用户
- 特别是首次使用的新用户（首次体验决定留存）

### 2.3 Success Metrics

- **Primary**: 端到端成功率（定义: 用户发起分析后能看到 A5 报告的比例）从 ~50% 提升到 ~80%
- **Secondary**: 平均分析耗时降低（Browser 熔断避免无效等待）
- **Guardrail**: A5 报告数据质量不降级（降级模式下报告明确标注数据来源受限）

### 2.4 设计概览

```
Layer 1: 调用级重试（单次 LLM/API 调用的重试策略）
    |
Layer 2: Agent 级降级（某个 Agent 整体失败后的替代方案）
    |
Layer 3: 平台级熔断（Browser 平台连续失败后的自动跳过）
```

---

### 2.5 Layer 1 -- 调用级重试

#### 2.5.1 A2 LLM max_tokens 显式传参

**问题根因**: A2 调用 LLM 时未显式指定 `max_tokens`，LLM 默认值可能不足以输出完整 JSON，导致 `finish_reason=length` 截断。

**方案**:

在 `_a2_call_and_parse()` 调用 `call_llm_streaming()` 时，透传 `max_tokens=8192` 参数。A2 画像 JSON 输出约 3000-5000 tokens，8192 提供更安全的 buffer。

**影响文件**:
- `aeo-platform/backend/app/workflow/nodes.py` -- `_a2_call_and_parse()` 函数（第 561-616 行）
- `aeo-platform/backend/app/workflow/nodes_streaming.py` -- `call_llm_streaming()` 和 `stream_llm_with_tpaor()` 需支持 `max_tokens` 透传（当前签名无此参数）

**详细实现规格**:

1. `stream_llm_with_tpaor()` 签名新增可选参数 `max_tokens: int | None = None`
2. `call_llm_streaming()` 签名新增可选参数 `max_tokens: int | None = None`，透传给 `stream_llm_with_tpaor()`
3. 在 `stream_llm_with_tpaor()` 内部，调用 `model.stream()` 时将 `max_tokens` 传入（如果非 None）
4. `_a2_call_and_parse()` 调用时指定 `max_tokens=8192`

**伪代码**:

```python
# nodes_streaming.py
async def stream_llm_with_tpaor(
    session_id: str,
    model: BaseLLMModel,
    messages: list[dict[str, Any]],
    step: str,
    step_name: str,
    progress_start: float = 0.0,
    progress_end: float = 1.0,
    tools: list[dict[str, Any]] | None = None,
    max_tokens: int | None = None,            # <-- 新增
) -> AsyncGenerator[LLMResponse, None]:
    ...
    stream_kwargs = {}
    if tools:
        stream_kwargs["tools"] = tools
    if max_tokens is not None:
        stream_kwargs["max_tokens"] = max_tokens
    async for chunk in async_wrap_sync_gen(
        lambda: model.stream(messages, **stream_kwargs)
    ):
        ...

# nodes.py
async def _a2_call_and_parse(...) -> dict | None:
    response = await call_llm_streaming(
        ...,
        max_tokens=8192,                       # <-- 新增
    )
```

#### 2.5.2 API 调用重试（已有，保持现状）

A4 的 API 平台（豆包/混元）已有 `_retry_fetch()` 实现（最多 2 次重试 + 指数退避），无需修改。

**当前代码位置**: `nodes_a4.py:65-105`

#### 2.5.3 A2 LLM 简化 prompt 重试（已有，保持现状）

A2 已有两次尝试机制: 第一次用标准 prompt，第二次用简化 prompt。无需修改。

**当前代码位置**: `nodes.py:420-456`

---

### 2.6 Layer 2 -- Agent 级降级

#### 2.6.1 降级策略注册表

**新增文件**: `aeo-platform/backend/app/workflow/resilience.py`

该文件包含两部分:
1. **降级策略注册表** (`DegradationRegistry`): 定义每个 Agent 失败时的降级行为
2. **熔断器** (`CircuitBreaker`): 针对 Browser 平台的熔断机制（见 Layer 3）

**降级策略注册表设计**:

```python
# resilience.py

import logging
from typing import Any
from app.workflow.events import send_reply_event

logger = logging.getLogger(__name__)


class DegradationRegistry:
    """Agent 级降级策略注册表。

    定义每个 Agent 失败时的处理方式:
    - should_block: 失败是否阻塞整个流程
    - fallback_message: 降级通知消息

    注意: state 修改逻辑由各 Agent node 内部负责（如 A2 的 user_decisions 合并），
    不在注册表中声明。A4 的动态消息构建也在 nodes_a4.py 内部完成。
    """

    STRATEGIES: dict[str, dict[str, Any]] = {
        "A2": {
            "should_block": False,
            "fallback_message": (
                "用户画像生成未能完成，已自动切换为品牌全景模式继续分析。"
                "后续问题将基于品牌整体信息生成，不按用户画像分类。"
            ),
            # state 修改（marketing_personas=None, user_decisions 合并）
            # 由 a2_persona_node() except 块内部负责，不在此声明
        },
        "A4": {
            "should_block": False,  # 部分失败不阻塞
            "min_platforms": 2,     # 至少 2 个平台有数据
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
            # A5 降级 = 跳过 LLM 报告生成，直接用 _generate_fallback_report()
        },
    }

    @classmethod
    def get_strategy(cls, agent_step: str) -> dict[str, Any] | None:
        """获取指定 Agent 的降级策略。"""
        return cls.STRATEGIES.get(agent_step)

    @classmethod
    def should_block_pipeline(cls, agent_step: str) -> bool:
        """该 Agent 失败是否阻塞整体流程。"""
        strategy = cls.STRATEGIES.get(agent_step)
        if strategy is None:
            return True  # 未注册的 Agent 默认阻塞
        return strategy.get("should_block", True)

    @classmethod
    async def send_degradation_notice(
        cls, session_id: str, agent_step: str, context: dict[str, Any] | None = None
    ) -> None:
        """向用户发送降级通知。"""
        strategy = cls.STRATEGIES.get(agent_step)
        if not strategy:
            return

        message = strategy.get("fallback_message", "")

        # A4 特殊处理: 根据成功/失败平台数动态生成消息
        if agent_step == "A4" and context:
            success_count = context.get("success_count", 0)
            fail_count = context.get("fail_count", 0)
            if success_count >= strategy.get("min_platforms", 2):
                message = strategy["partial_message_template"].format(
                    success_count=success_count, fail_count=fail_count
                )
            else:
                message = strategy["total_fail_message"]

        if message:
            await send_reply_event(
                session_id, f"\n---\n**[系统通知]** {message}\n---\n",
                is_delta=False, is_new_round=True,
            )
            # 标记完成
            await send_reply_event(session_id, "", is_complete=True)
            logger.info(f"[Resilience] Sent degradation notice for {agent_step}: {message[:80]}...")
```

#### 2.6.2 A2 降级: 自动跳过，全景模式继续

**触发条件**: A2 两次尝试均失败（`_a2_call_and_parse` 两次返回 None 后 raise RuntimeError）

**降级行为**:
1. 捕获 A2 的 RuntimeError
2. 不设置 `execution_status: "error"`（不阻塞流程）
3. 通过 `DegradationRegistry.send_degradation_notice()` 发送用户通知
4. 设置 `marketing_personas = None`，`user_decisions.a3_mode = "brand"`
5. 返回 `Command(update={...})` 让 Orchestrator 继续调度 A3

**影响文件**: `aeo-platform/backend/app/workflow/nodes.py` -- `a2_persona_node()` 的 except 块（第 544-558 行）

**修改前** (当前代码):
```python
except Exception as e:
    logger.error(f"[A2] Failed: {e}")
    await send_error_event(session_id, "A2", str(e), recoverable=True)
    return Command(
        update={
            "error_info": {
                "step": "A2",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            "current_step": "A2",
            "marketing_personas": None,
        },
    )
```

**修改后**:
```python
except Exception as e:
    logger.error(f"[A2] Failed: {e}")

    # Layer 2 降级: A2 失败不阻塞流程，自动切换全景模式
    from app.workflow.resilience import DegradationRegistry

    if not DegradationRegistry.should_block_pipeline("A2"):
        logger.info("[A2] Degrading to brand panorama mode")
        await DegradationRegistry.send_degradation_notice(session_id, "A2")

        # user_decisions 必须做字典合并，不能整体替换，
        # 否则会丢失之前步骤设置的其他 decision 字段
        existing_decisions = state.get("user_decisions", {})
        existing_decisions.update({"a3_mode": "brand", "a2_degraded": True})

        return Command(
            update={
                "current_step": "A2",
                "marketing_personas": None,
                "user_decisions": existing_decisions,
                # 注意: 不设置 error_info 和 execution_status="error"
                # 让 Orchestrator 知道 A2 完成了（虽然没有数据）
            },
        )

    # 如果策略配置为阻塞（当前不会走到这里），走原有错误路径
    await send_error_event(session_id, "A2", str(e), recoverable=True)
    return Command(
        update={
            "error_info": {
                "step": "A2",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            },
            "current_step": "A2",
            "marketing_personas": None,
        },
    )
```

**Orchestrator 侧适配**: `orchestrator_node.py` 中 `_build_agent_result_summary()` 的 `persona_generation` 分支已正确处理 `marketing_personas=None` 的情况（返回"画像未获取到数据"），Orchestrator 系统提示词的失败处理规则也已引导 LLM 提供建设性选项。因此 Orchestrator 无需修改。

降级后 Orchestrator 的行为:
1. 收到 A2 的 tool_result = "画像未获取到数据，请提供建设性选项帮助用户继续。"
2. 但由于 `user_decisions.a3_mode = "brand"` 已设置，且没有 `error_info`
3. LLM 会继续调度 A3（品牌全景模式），流程不中断

#### 2.6.3 A4 降级: 部分平台失败继续分析

**触发条件**: 部分平台失败但 >= 2 个平台有数据

**降级行为**:
1. 已有逻辑（`nodes_a4.py:380-400`）检查 `successful_platforms >= MIN_PLATFORMS_REQUIRED`
2. **增强**: 当满足最低平台数时，发送降级通知而非 error event
3. **增强**: 当不满足最低平台数时，走原有 error 路径

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a4.py` -- 第 380-400 行区域

**修改规格**:

当前代码在 `len(successful_platforms) < MIN_PLATFORMS_REQUIRED` 时发送 error event，但实际上即使发送了 error，流程仍然会继续（因为 Command 不设置 error_info）。需要增强为:

```python
# nodes_a4.py 第 380-400 行区域修改

from app.workflow.resilience import DegradationRegistry

total_platforms = len(PLATFORMS)
fail_count = total_platforms - len(successful_platforms)

if len(successful_platforms) < MIN_PLATFORMS_REQUIRED:
    # 平台数不足，发送错误（但流程仍可继续，如果至少有1个平台数据）
    if len(successful_platforms) > 0:
        await DegradationRegistry.send_degradation_notice(
            session_id, "A4",
            context={"success_count": len(successful_platforms), "fail_count": fail_count},
        )
    else:
        await send_error_event(
            session_id, "A4",
            "所有平台数据获取均失败，请检查网络连接后重试",
            recoverable=True,
        )
elif fail_count > 0:
    # 满足最低要求但有部分失败，发送通知
    await DegradationRegistry.send_degradation_notice(
        session_id, "A4",
        context={"success_count": len(successful_platforms), "fail_count": fail_count},
    )
```

#### 2.6.4 A5 降级: 原始数据生成简易报告

**触发条件**: A5 的 LLM 调用失败（`call_llm_streaming` 抛出异常或返回无法解析的内容）

**降级行为**: A5 已有 `_generate_fallback_report()` 函数（`nodes_a5.py:578-619`）用于 LLM 解析失败时的兜底。本次增强:

1. **已有**: `report_data = parse_llm_response(response)` 返回 None 时调用 `_generate_fallback_report()`
2. **新增**: 当 `call_llm_streaming()` 本身抛出异常时，也调用 `_generate_fallback_report()` 而非直接进入 error 路径
3. **新增**: 降级报告中标注 "本报告基于原始数据自动生成，未经 AI 深度分析"

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py` -- `a5_analytics_node()` 的 try 块内（第 120-133 行）和 except 块（第 283-305 行）

**修改规格**:

```python
# nodes_a5.py a5_analytics_node() 内

try:
    # ... 现有 metrics 计算代码 ...

    # LLM 报告生成 -- 包裹在内层 try 中
    report_data = None
    try:
        system_prompt = _get_a5_system_prompt()
        user_content = _build_a5_user_content(...)
        model = get_llm_model_compat()
        response = await call_llm_streaming(...)
        report_data = parse_llm_response(response)
    except Exception as llm_err:
        logger.warning(f"[A5] LLM report generation failed, using fallback: {llm_err}")

    if not report_data:
        report_data = _generate_fallback_report(metrics, brand_profile)
        report_data["_degraded"] = True  # 标记为降级报告
        report_data["_degradation_note"] = "本报告基于原始数据自动生成，未经 AI 深度分析"
        from app.workflow.resilience import DegradationRegistry
        await DegradationRegistry.send_degradation_notice(session_id, "A5")

    # ... 后续 artifact 发送代码不变 ...

except Exception as e:
    # 外层异常（metrics 计算失败等严重错误）仍走 error 路径
    ...
```

---

### 2.7 Layer 3 -- 平台级熔断器

#### 2.7.1 熔断器设计

**新增位置**: `aeo-platform/backend/app/workflow/resilience.py` 内

**熔断器状态机**:

```
CLOSED (正常) --[连续 N 次失败]--> OPEN (熔断)
OPEN (熔断) --[cooldown 超时]--> HALF_OPEN (半开)
HALF_OPEN --[一次成功]--> CLOSED (恢复)
HALF_OPEN --[一次失败]--> OPEN (继续熔断)
```

**参数**:

| 参数 | 值 | 说明 |
|------|-----|------|
| `failure_threshold` | 3 | 连续失败 N 次后触发熔断 |
| `cooldown_seconds` | 300 | 熔断后 5 分钟自动进入 HALF_OPEN |
| `scope` | 进程内内存（全局单例） | 无需 Redis，单进程即可。同一进程中所有 session 共享同一组 breaker，这是期望行为: 某平台对一个 session 不可用时，大概率对其他 session 也不可用 |

**实现规格**:

```python
# resilience.py

import time
from enum import Enum
from threading import Lock


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """进程内熔断器，针对 Browser 平台（Kimi/DeepSeek）。

    - CLOSED: 正常状态，所有请求通过
    - OPEN: 熔断状态，直接拒绝请求
    - HALF_OPEN: 半开状态，允许一个请求通过以探测恢复

    线程安全: 使用 threading.Lock 保护状态变更。
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
                # 检查是否可以进入 HALF_OPEN
                if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.info(
                        f"[CircuitBreaker:{self.name}] OPEN -> HALF_OPEN "
                        f"(cooldown {self.cooldown_seconds}s elapsed)"
                    )
            return self._state

    def allow_request(self) -> bool:
        """当前是否允许发送请求。"""
        current_state = self.state
        if current_state == CircuitState.CLOSED:
            return True
        if current_state == CircuitState.HALF_OPEN:
            return True  # 允许一个探测请求
        # OPEN
        return False

    def record_success(self) -> None:
        """记录一次成功请求。"""
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                logger.info(f"[CircuitBreaker:{self.name}] HALF_OPEN -> CLOSED (success)")
                self._state = CircuitState.CLOSED
            self._failure_count = 0

    def record_failure(self) -> None:
        """记录一次失败请求。"""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.info(f"[CircuitBreaker:{self.name}] HALF_OPEN -> OPEN (probe failed)")
            elif self._failure_count >= self.failure_threshold:
                if self._state != CircuitState.OPEN:
                    logger.warning(
                        f"[CircuitBreaker:{self.name}] CLOSED -> OPEN "
                        f"(consecutive failures: {self._failure_count})"
                    )
                    self._state = CircuitState.OPEN

    def reset(self) -> None:
        """手动重置熔断器。"""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._last_failure_time = 0.0


# 全局熔断器实例（进程内单例，跨 session 共享）。
# 所有 session 共享同一组 breaker，因为平台可用性是全局状态，
# 不因 session 而异。这是期望行为。
_breakers: dict[str, CircuitBreaker] = {}
_breakers_lock = Lock()


def get_circuit_breaker(platform: str) -> CircuitBreaker:
    """获取指定平台的熔断器实例（惰性创建，进程内全局共享）。"""
    with _breakers_lock:
        if platform not in _breakers:
            _breakers[platform] = CircuitBreaker(
                name=platform,
                failure_threshold=3,
                cooldown_seconds=300.0,
            )
        return _breakers[platform]
```

#### 2.7.2 集成到 A4 Browser 流程

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a4.py` -- `_browser_pipeline()` 内部函数（第 291-314 行）

**修改规格**:

在 `_browser_pipeline()` 中，每次发送 Browser 请求前检查熔断器:

```python
async def _browser_pipeline(
    handler, browser_client, platform: str, platform_name: str,
) -> list[tuple[int, dict[str, Any]]]:
    """Process all questions through one browser sequentially."""
    from app.workflow.resilience import get_circuit_breaker

    breaker = get_circuit_breaker(platform)
    results = []

    for idx, question in enumerate(questions):
        q_text = question.get("text", "")

        # 熔断器检查
        if not breaker.allow_request():
            logger.info(f"[A4] {platform_name} circuit OPEN, skipping Q{idx+1}")
            results.append((idx, {
                "platform": platform,
                "platform_name": platform_name,
                "fetch_method": "browser",
                "success": False,
                "error": f"平台 {platform_name} 暂时不可用（熔断保护）",
                "skipped_by_breaker": True,
            }))
            continue

        r = await _browser_fetch_with_timeout(
            _fetch_from_browser,
            handler, q_text, brand_profile,
            platform, platform_name, BrowserState,
            timeout=BROWSER_TIMEOUT_SECONDS,
        )

        # 更新熔断器状态
        if r.get("success"):
            breaker.record_success()
        else:
            breaker.record_failure()

        results.append((idx, r))

        # 进度通知（保持现有逻辑）
        if (idx + 1) % 4 == 0 or idx == total - 1:
            ...

    return results
```

**关键行为**:
- 仅 Browser 平台（Kimi/DeepSeek）使用熔断器
- API 平台（豆包/混元）不使用熔断器（已有重试机制，且稳定性较高）
- 熔断后该平台的所有后续请求直接返回失败结果，不浪费等待时间
- 5 分钟后自动探测恢复

---

### 2.8 用户通知设计

所有降级/熔断事件必须透明通知用户，原则: **不隐藏问题，但不阻塞流程**。

通知方式: 通过现有 WebSocket `reply_delta` 事件在聊天面板中展示，无需新增 WebSocket 事件类型。

**通知消息规范**:

| 场景 | 消息模板 | 样式 |
|------|---------|------|
| A2 降级 | "用户画像生成未能完成，已自动切换为品牌全景模式继续分析。后续问题将基于品牌整体信息生成，不按用户画像分类。" | 系统通知 |
| A4 部分失败 | "{N} 个平台数据获取成功，{M} 个平台暂时不可用。基于已有数据继续分析。" | 系统通知 |
| A4 全部失败 | "所有平台数据获取均失败，请检查网络连接后重试。" | 错误通知 |
| A5 降级 | "高级分析报告生成遇到问题，已基于原始数据生成简要报告。" | 系统通知 |
| Browser 熔断 | （不单独通知，包含在 A4 部分失败消息中） | -- |

---

### 2.9 验收标准

- [ ] **AC-1**: A2 失败时流程不中断，自动降级为品牌全景模式
  - 测试方法: Mock A2 LLM 返回截断输出，验证 A3 仍以品牌全景模式执行
- [ ] **AC-2**: A4 至少 2/4 平台有数据即可生成报告
  - 测试方法: Mock 2 个平台超时，验证 A5 仍生成报告
- [ ] **AC-3**: Browser 平台连续 3 次失败后自动跳过后续请求
  - 测试方法: Mock Kimi 连续 3 次超时，验证第 4 次请求被 breaker 跳过
  - 验证 5 分钟后 breaker 进入 HALF_OPEN 并允许探测请求
- [ ] **AC-4**: 用户在聊天面板中收到每次降级/跳过的通知消息
  - 测试方法: 验证 WebSocket 收到 `reply_delta` 事件包含降级文案
- [ ] **AC-5**: 整体端到端成功率从 ~50% 提升到 ~80%
  - 测试方法: 运行 10 次完整分析流程，统计成功率
- [ ] **AC-6**: `max_tokens=8192` 正确透传到 A2 的 LLM 调用（A2 画像 JSON 约 3000-5000 tokens，8192 提供安全 buffer）
  - 测试方法: 检查 LLM 请求日志中 max_tokens 参数
- [ ] **AC-7**: 降级报告中标注数据来源受限
  - 测试方法: A5 降级时 report_data 包含 `_degraded: true` 和 `_degradation_note`

---

## 三、功能二: BWVS v2 多维评分公式

### 3.1 Problem Statement

当前 BWVS 计算公式:
```python
bwvs_index = min(100, mention_rate * 100)
```

这本质上就是提及率的百分化，无法区分以下两种情况:
- **品牌 A**: 80% 提及率，但多为负面提及（"XX品牌质量问题频发"）
- **品牌 B**: 60% 提及率，全部为正面推荐且引用官方来源

在当前公式下，品牌 A (BWVS=80) 分数高于品牌 B (BWVS=60)，这对品牌客户具有误导性。

### 3.2 Target User

- 品牌客户的市场部/运营部：需要多维度评估品牌 AI 可见性
- 品牌客户的管理层：需要一个可解释的综合评分用于决策和汇报

### 3.3 Success Metrics

- **Primary**: BWVS 评分包含 4 个维度，且各维度得分在 Dashboard 可见
- **Secondary**: A5 报告中展示 BWVS breakdown（可视化）
- **Guardrail**: 无数据维度给中性默认分（不是 0），避免因数据缺失导致分数异常偏低

### 3.4 公式设计

#### 3.4.1 总分公式

```
BWVS = W1 * mention_score + W2 * sentiment_score + W3 * coverage_score + W4 * citation_score
```

**默认权重**（V1 全局常量，后续迁移为品牌级可配置）:

| 维度 | 权重 | 说明 |
|------|------|------|
| W1: 提及率得分 | 40 | 品牌被 AI 回答提及的频率 |
| W2: 情感得分 | 25 | 提及内容的情感倾向 |
| W3: 平台覆盖度 | 20 | 跨平台覆盖的广度 |
| W4: 引用质量 | 15 | AI 引用品牌官方来源的比例 |

**权重约束**: W1 + W2 + W3 + W4 = 100

#### 3.4.2 各维度计算方法

**1. 提及率得分 (mention_score, 0-100)**

```python
mention_score = min(100, mention_rate * 120)
```

- 放大系数 1.2: 83.3% 的提及率即可满分
- 原因: 100% 提及率在实际场景中几乎不可能（AI 回答并非总会提及特定品牌），稍微放大避免评分天花板过低

**2. 情感得分 (sentiment_score, 0-100)**

```python
# 基于已有 _analyze_sentiment() 关键词匹配的结果
total_analyzed = pos_count + neg_count + neutral_count
if total_analyzed == 0:
    sentiment_score = 50  # 无数据时中性分

else:
    pos_ratio = pos_count / total_analyzed
    neg_ratio = neg_count / total_analyzed
    # 公式: 将 [-1, 1] 区间映射到 [0, 100]
    sentiment_score = max(0, min(100, (pos_ratio - neg_ratio + 1) * 50))
```

- 全部正面: `(1 - 0 + 1) * 50 = 100`
- 全部中性: `(0 - 0 + 1) * 50 = 50`
- 全部负面: `(0 - 1 + 1) * 50 = 0`
- 无数据: `50`（中性默认分）

**3. 平台覆盖度 (coverage_score, 0-100)**

```python
# platforms_with_mention = 有至少一次品牌提及的平台数
# 分母固定为 len(PLATFORMS) = 4，不随降级场景缩小。
# 当 A4 降级后只有 2 个平台有数据时，coverage 自然偏低，更真实地反映覆盖不足。
coverage_score = (platforms_with_mention / len(PLATFORMS)) * 100
```

- 4/4 平台有提及 = 100 分
- 3/4 平台有提及 = 75 分
- 2/4 平台有提及 = 50 分
- 1/4 平台有提及 = 25 分
- 无提及 = 0 分（此维度允许 0 分，因为确实没有覆盖）
- 降级场景: 例如 A4 熔断后仅 2 个平台返回数据且都有提及，coverage = 2/4 = 50 分（而非 2/2 = 100 分）

**4. 引用质量 (citation_score, 0-100)**

```python
# 从 fetch_results 中提取所有引用（citations）
# 品牌官方域名从 brand_profile.official_website 或 Entity.domain 获取
# 例: brand_profile["official_website"] = "https://www.nike.com" -> domain = "nike.com"

total_citations = 所有成功回答中的引用总数
official_citations = 其中引用域名匹配品牌官方域名的数量

if not brand_domain:
    # brand_profile["official_website"] 和 Entity.domain 都为空
    citation_score = 50  # 无法计算，给中性默认分
    # 在 bwvs_breakdown 中增加说明字段
    citation_note = "未配置品牌域名，引用质量使用中性默认分"
elif total_citations == 0:
    citation_score = 50  # 无引用数据时中性分
else:
    citation_score = (official_citations / total_citations) * 100
```

- 品牌官方域名匹配逻辑: `citation_domain.endswith(brand_domain)` 或 `brand_domain in citation_domain`
- 从 `brand_profile["official_website"]` 提取域名: `urlparse(url).netloc.replace("www.", "")`
- 如果 `brand_profile["official_website"]` 为空，回退尝试 `Entity.domain`
- 如果两者都为空，citation_score 给 50 分，并在 `bwvs_breakdown` 中增加 `citation_note` 字段说明原因

#### 3.4.3 权重常量定义

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`

```python
# BWVS v2 权重常量（V1: 全局默认，后续版本迁移为品牌级配置）
BWVS_WEIGHTS = {
    "mention": 40,     # W1: 提及率得分权重
    "sentiment": 25,   # W2: 情感得分权重
    "coverage": 20,    # W3: 平台覆盖度权重
    "citation": 15,    # W4: 引用质量权重
}

# 验证权重总和
assert sum(BWVS_WEIGHTS.values()) == 100, "BWVS weights must sum to 100"
```

### 3.5 后端实现规格

#### 3.5.1 `_calculate_metrics()` 修改

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py` -- `_calculate_metrics()` 函数（第 308-374 行）

**当前返回值**:
```python
{
    "total_questions": int,
    "total_mentions": int,
    "mention_rate": float,
    "bwvs_index": float,  # = min(100, mention_rate * 100)
    "sentiment_distribution": {"positive": N, "neutral": N, "negative": N},
    "platform_breakdown": {...},
}
```

**修改后返回值**:
```python
{
    "total_questions": int,
    "total_mentions": int,
    "mention_rate": float,
    "bwvs_index": float,                    # v2 多维加权分数
    "bwvs_breakdown": {                      # 新增: 四维分项
        "mention_score": float,              # 0-100
        "sentiment_score": float,            # 0-100
        "coverage_score": float,             # 0-100, 分母固定为 len(PLATFORMS)=4
        "citation_score": float,             # 0-100
        "citation_note": str | None,         # 可选, 当无法计算引用质量时的说明
        "weights": {                         # 权重说明
            "mention": 40,
            "sentiment": 25,
            "coverage": 20,
            "citation": 15,
        },
        "formula": "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量",
    },
    "sentiment_distribution": {"positive": N, "neutral": N, "negative": N},
    "platform_breakdown": {...},
}
```

**完整的 `_calculate_metrics()` 新实现**:

```python
from app.core.utils import extract_domain

def _calculate_metrics(fetch_results: list, brand_profile: dict) -> dict[str, Any]:
    """Calculate BWVS v2 metrics from fetch results.

    BWVS v2 = W1*mention_score + W2*sentiment_score + W3*coverage_score + W4*citation_score
    """
    if not fetch_results:
        return {
            "total_questions": 0,
            "total_mentions": 0,
            "mention_rate": 0.0,
            "bwvs_index": 0.0,
            "bwvs_breakdown": {
                "mention_score": 0.0,
                "sentiment_score": 50.0,     # 无数据中性分
                "coverage_score": 0.0,
                "citation_score": 50.0,      # 无数据中性分
                "weights": dict(BWVS_WEIGHTS),
                "formula": "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量",
            },
            "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
            "platform_breakdown": {},
        }

    total_questions = len(fetch_results)
    total_mentions = 0
    platform_stats = {}
    platforms_with_mention = set()

    # 统计情感分布
    sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}

    # 统计引用
    total_citations = 0
    official_citations = 0
    brand_domain = extract_domain(brand_profile.get("official_website", ""))

    for result in fetch_results:
        for platform_result in result.get("platform_results", []):
            platform = platform_result.get("platform", "unknown")

            if platform not in platform_stats:
                platform_stats[platform] = {"total": 0, "mentions": 0, "success": 0}

            platform_stats[platform]["total"] += 1

            if platform_result.get("success"):
                platform_stats[platform]["success"] += 1

                answer = platform_result.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)

                # 情感分析
                sentiment = _analyze_sentiment(content)
                sentiment_counts[sentiment] += 1

                # 品牌提及
                if answer.get("has_brand_mention", False) if isinstance(answer, dict) else False:
                    total_mentions += 1
                    platform_stats[platform]["mentions"] += 1
                    platforms_with_mention.add(platform)

                # 引用统计
                citations = platform_result.get("citations", [])
                for citation in citations:
                    total_citations += 1
                    citation_url = citation.get("url", "") if isinstance(citation, dict) else ""
                    citation_domain = extract_domain(citation_url)
                    if brand_domain and citation_domain and (
                        citation_domain.endswith(brand_domain) or brand_domain in citation_domain
                    ):
                        official_citations += 1

    # ---- 维度 1: 提及率得分 ----
    total_platform_results = sum(p["total"] for p in platform_stats.values())
    mention_rate = total_mentions / total_platform_results if total_platform_results > 0 else 0
    mention_score = min(100, mention_rate * 120)

    # ---- 维度 2: 情感得分 ----
    total_analyzed = sum(sentiment_counts.values())
    if total_analyzed > 0:
        pos_ratio = sentiment_counts["positive"] / total_analyzed
        neg_ratio = sentiment_counts["negative"] / total_analyzed
        sentiment_score = max(0, min(100, (pos_ratio - neg_ratio + 1) * 50))
    else:
        sentiment_score = 50.0  # 无数据中性分

    # ---- 维度 3: 平台覆盖度 ----
    # 分母固定为 len(PLATFORMS) = 4，不随降级场景缩小
    total_platforms = len(PLATFORMS)
    coverage_score = (len(platforms_with_mention) / total_platforms * 100) if total_platforms > 0 else 0

    # ---- 维度 4: 引用质量 ----
    citation_note = None  # 当无法计算时附带说明
    if not brand_domain:
        # brand_profile["official_website"] 和 Entity.domain 都为空
        citation_score = 50.0
        citation_note = "未配置品牌域名，引用质量使用中性默认分"
    elif total_citations > 0:
        citation_score = (official_citations / total_citations) * 100
    else:
        citation_score = 50.0  # 无引用数据中性分

    # ---- BWVS v2 总分 ----
    bwvs_index = (
        BWVS_WEIGHTS["mention"] * mention_score / 100
        + BWVS_WEIGHTS["sentiment"] * sentiment_score / 100
        + BWVS_WEIGHTS["coverage"] * coverage_score / 100
        + BWVS_WEIGHTS["citation"] * citation_score / 100
    )

    return {
        "total_questions": total_questions,
        "total_mentions": total_mentions,
        "mention_rate": round(mention_rate, 4),
        "bwvs_index": round(bwvs_index, 2),
        "bwvs_breakdown": {
            "mention_score": round(mention_score, 2),
            "sentiment_score": round(sentiment_score, 2),
            "coverage_score": round(coverage_score, 2),
            "citation_score": round(citation_score, 2),
            **({"citation_note": citation_note} if citation_note else {}),
            "weights": dict(BWVS_WEIGHTS),
            "formula": "BWVS = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量",
        },
        "sentiment_distribution": sentiment_counts,
        "platform_breakdown": platform_stats,
    }


## 注意: _extract_domain 提取到 app/core/utils.py，与 analytics_service.py 的 URL 解析共享

# app/core/utils.py
def extract_domain(url: str) -> str:
    """从 URL 中提取域名（去除 www. 前缀）。

    此函数由 nodes_a5.py 和 analytics_service.py 共享使用。
    """
    if not url:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url if url.startswith("http") else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
        return domain.lower().replace("www.", "")
    except Exception:
        return ""

# nodes_a5.py 中使用:
# from app.core.utils import extract_domain
# brand_domain = extract_domain(brand_profile.get("official_website", ""))
```

#### 3.5.2 A5 Artifact 数据适配

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py` -- `save_and_send_artifact()` 调用处（第 172-224 行）

在 artifact `data` 中新增 `bwvs_breakdown` 字段:

```python
await save_and_send_artifact(
    session_id=session_id,
    output_type="report",
    title="品牌可见度分析报告",
    data={
        # ... 现有字段保持不变 ...
        "overallScore": metrics.get("bwvs_index", 0),  # 改为 BWVS v2 总分
        "bwvs_breakdown": metrics.get("bwvs_breakdown", {}),  # 新增
        # ... 其余字段不变 ...
    },
)
```

**注意**: `overallScore` 原来是 `mention_rate * 100`，现在改为 `bwvs_index`（v2 多维加权分数）。`scoreBand` 的阈值也相应调整:

```python
# 原来基于 mention_rate，现在基于 bwvs_index
"scoreBand": (
    "优秀" if metrics.get("bwvs_index", 0) >= 70
    else "良好" if metrics.get("bwvs_index", 0) >= 40
    else "需改进"
),
```

#### 3.5.3 analytics_service.py 适配

**影响文件**: `aeo-platform/backend/app/services/analytics_service.py`

1. `get_overview()` 方法返回 `bwvs_breakdown`:

```python
return {
    "kpi": {
        "brandVisibility": bwvs,
        "mentionRate": mention_rate,
        "shareOfVoice": sov,
        "bwvsBreakdown": metrics.get("bwvs_breakdown"),  # 新增
        # ... 其余字段不变 ...
    }
}
```

2. `get_aeo_metrics()` 方法增加 breakdown 维度指标:

```python
# 在现有 aeo_metrics 列表后追加 breakdown 维度
breakdown = metrics.get("bwvs_breakdown", {})
if breakdown:
    aeo_metrics.extend([
        {
            "metric": "提及率得分",
            "value": round(breakdown.get("mention_score", 0), 1),
            "benchmark": 60,
            "status": _aeo_status(breakdown.get("mention_score", 0), "bwvs_index"),
            "weight": "40%",
        },
        {
            "metric": "情感得分",
            "value": round(breakdown.get("sentiment_score", 50), 1),
            "benchmark": 60,
            "status": _aeo_status(breakdown.get("sentiment_score", 50), "bwvs_index"),
            "weight": "25%",
        },
        {
            "metric": "平台覆盖度",
            "value": round(breakdown.get("coverage_score", 0), 1),
            "benchmark": 75,
            "status": _aeo_status(breakdown.get("coverage_score", 0), "bwvs_index"),
            "weight": "20%",
        },
        {
            "metric": "引用质量",
            "value": round(breakdown.get("citation_score", 50), 1),
            "benchmark": 50,
            "status": _aeo_status(breakdown.get("citation_score", 50), "bwvs_index"),
            "weight": "15%",
        },
    ])
```

### 3.6 前端展示规格

#### 3.6.1 Dashboard KPI 卡片 BWVS Breakdown Tooltip

**影响文件**: `D:\AGEO\frontend\src\components\dashboard\KPICard.tsx`

**当前状态**: KPICard 已支持 `tooltip` 属性（纯文本字符串），hover 时显示简单 tooltip。

**增强方案**: 扩展 `tooltip` 属性支持结构化数据，当 BWVS KPI 卡片 hover 时展示四维分项得分。

**方案 A (简单方案，V1 推荐)**: tooltip 使用多行文本:

```
BWVS 综合评分 = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量

提及率得分: 72.0/100 (权重40%)
情感得分: 65.5/100 (权重25%)
平台覆盖度: 75.0/100 (权重20%)
引用质量: 42.0/100 (权重15%)
```

Dashboard 页面传入 KPICard 时构造此 tooltip 字符串:

```typescript
// 假设从 API 获取到 bwvsBreakdown
const bwvsTooltip = bwvsBreakdown
  ? `BWVS 综合评分 = 40%*提及率 + 25%*情感 + 20%*覆盖度 + 15%*引用质量\n\n` +
    `提及率得分: ${bwvsBreakdown.mention_score?.toFixed(1) ?? '--'}/100 (权重40%)\n` +
    `情感得分: ${bwvsBreakdown.sentiment_score?.toFixed(1) ?? '--'}/100 (权重25%)\n` +
    `平台覆盖度: ${bwvsBreakdown.coverage_score?.toFixed(1) ?? '--'}/100 (权重20%)\n` +
    `引用质量: ${bwvsBreakdown.citation_score?.toFixed(1) ?? '--'}/100 (权重15%)`
  : undefined;
```

**KPICard.tsx 修改**: tooltip 内容支持 `whitespace-pre-wrap` 以正确显示多行:

当前 tooltip span 已有 `whitespace-normal`，需修改为 `whitespace-pre-wrap`。

#### 3.6.2 ReportContent BWVS Breakdown 展示

**影响文件**: `D:\AGEO\frontend\src\components\canvas\contents\ReportContent.tsx`

在"总览"Tab 的 Score Card 区域（第 88-113 行）下方，新增 BWVS Breakdown 展示:

**设计规格**:

```tsx
{/* BWVS Breakdown -- 四维分项得分 */}
{bwvsBreakdown && (
  <div className="p-4 bg-[#1A1A1A] border border-[#262626] rounded-lg">
    <h4 className="text-sm font-medium text-[#E5E5E5] mb-3">BWVS 评分维度</h4>
    <p className="text-xs text-[#737373] mb-4">{bwvsBreakdown.formula}</p>
    <div className="grid grid-cols-2 gap-3">
      {[
        { label: "提及率", score: bwvsBreakdown.mention_score, weight: 40, color: "#6366F1" },
        { label: "情感倾向", score: bwvsBreakdown.sentiment_score, weight: 25, color: "#10B981" },
        { label: "平台覆盖", score: bwvsBreakdown.coverage_score, weight: 20, color: "#3B82F6" },
        { label: "引用质量", score: bwvsBreakdown.citation_score, weight: 15, color: "#F59E0B" },
      ].map((dim) => (
        <div key={dim.label} className="p-3 bg-[#0A0A0A] rounded-lg">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-xs text-[#A3A3A3]">{dim.label}</span>
            <span className="text-xs text-[#737373]">权重 {dim.weight}%</span>
          </div>
          <div className="text-lg font-semibold text-[#E5E5E5]">
            {dim.score?.toFixed(1) ?? '--'}
          </div>
          <div className="w-full h-1.5 bg-[#262626] rounded-full overflow-hidden mt-1.5">
            <div
              className="h-full rounded-full"
              style={{
                width: `${Math.min(100, dim.score ?? 0)}%`,
                backgroundColor: dim.color,
              }}
            />
          </div>
        </div>
      ))}
    </div>
  </div>
)}
```

**数据获取**: 从 `data.bwvs_breakdown` 或 `ext.bwvs_breakdown` 中读取。

```tsx
const bwvsBreakdown = (ext.bwvs_breakdown || null) as {
  mention_score: number;
  sentiment_score: number;
  coverage_score: number;
  citation_score: number;
  weights: Record<string, number>;
  formula: string;
} | null;
```

---

### 3.7 验收标准

- [ ] **AC-8**: BWVS 不再等于 `mention_rate * 100`
  - 测试方法: 运行完整分析流程，验证 `metrics.bwvs_index` !== `metrics.mention_rate * 100`
- [ ] **AC-9**: `metrics` 返回值包含 `bwvs_breakdown` 四维分项
  - 测试方法: 检查 A5 输出的 metrics dict
- [ ] **AC-10**: Dashboard KPI 卡片 hover 显示四维分项得分
  - 测试方法: 前端 hover BWVS 卡片，tooltip 显示 4 个维度分数
- [ ] **AC-11**: ReportContent "总览" Tab 显示 BWVS breakdown 可视化
  - 测试方法: 打开报告 Canvas，确认 4 个维度的进度条和分数
- [ ] **AC-12**: 无数据维度给默认中性分（不是 0）
  - 测试方法: 无 fetch_results 时 sentiment_score=50, citation_score=50
  - 有 fetch_results 但无 citations 时 citation_score=50
- [ ] **AC-13**: 权重可在代码中配置
  - 测试方法: 修改 `BWVS_WEIGHTS` 常量，验证评分变化
  - 验证 assert 检查权重总和 = 100
- [ ] **AC-14**: 引用质量正确计算品牌官方域名匹配
  - 测试方法: Mock brand_profile 含 official_website，Mock citations 含匹配/不匹配域名

---

## 四、影响范围总结

### 4.1 后端文件变更

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `app/workflow/resilience.py` | **新增** | DegradationRegistry + CircuitBreaker |
| `app/core/utils.py` | **新增/修改** | `extract_domain()` 函数（从 nodes_a5.py 提取，与 analytics_service.py 共享） |
| `app/workflow/nodes.py` | 修改 | A2 except 块降级逻辑（含 user_decisions 字典合并） |
| `app/workflow/nodes_a4.py` | 修改 | Browser pipeline 集成熔断器 + 降级通知 |
| `app/workflow/nodes_a5.py` | 修改 | BWVS v2 公式 + LLM 降级 + BWVS_WEIGHTS 常量 + 引用 extract_domain |
| `app/workflow/nodes_streaming.py` | 修改 | max_tokens 参数透传 |
| `app/services/analytics_service.py` | 修改 | bwvs_breakdown 数据适配 + 引用 extract_domain |

### 4.2 前端文件变更

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `components/dashboard/KPICard.tsx` | 修改 | tooltip whitespace-pre-wrap |
| `components/canvas/contents/ReportContent.tsx` | 修改 | BWVS breakdown 四维展示区块 |
| Dashboard 页面（KPI 传入处） | 修改 | 构造 BWVS tooltip 字符串 |

### 4.3 不影响的部分

- **数据库模型无变更**: BWVS breakdown 存储在 output_data JSON 字段中
- **WebSocket 协议无变更**: 降级通知使用现有 `reply_delta` 事件
- **前端路由无变更**
- **LLM 抽象层无变更**: `BaseLLMModel.stream()` 已支持 kwargs 透传
- **A1/A3 Agent 无变更**

---

## 五、技术风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| `max_tokens=8192` 仍不够 A2 输出 | 极低 | A2 继续截断 | Layer 2 降级兜底；8192 已为 A2 画像 JSON (3000-5000 tokens) 提供充足 buffer |
| 熔断器误触发（网络临时抖动） | 中 | 正常平台被跳过 | `failure_threshold=3` 较保守；5 分钟自动恢复 |
| 情感分析关键词匹配精度不足 | 中 | 情感得分偏差 | V1 可接受；后续升级为 LLM-based 情感分析 |
| 引用质量得分在无引用时不准确 | 低 | 中性分 50 可能不反映真实情况 | 产品定义: 无数据 = 中性，符合预期 |
| Browser 平台全部被熔断 | 低 | 仅 API 平台数据 | A4 降级逻辑保证 >= 2 平台即可继续 |

---

## 六、排期建议

| 任务 | 估时 | 负责角色 | 依赖 |
|------|------|---------|------|
| resilience.py (降级注册表+熔断器) | 3h | 后端开发 | 无 |
| nodes_streaming.py max_tokens 透传 | 1h | 后端开发 | 无 |
| nodes.py A2 降级逻辑 | 1h | 后端开发 | resilience.py |
| nodes_a4.py 熔断器集成 | 2h | 后端开发 | resilience.py |
| nodes_a5.py BWVS v2 公式 | 3h | 后端开发 | 无 |
| analytics_service.py 适配 | 1h | 后端开发 | nodes_a5.py |
| KPICard.tsx tooltip | 0.5h | 前端开发 | analytics_service.py |
| ReportContent.tsx breakdown | 2h | 前端开发 | nodes_a5.py |
| E2E 测试验证 | 4h | QA | 全部完成 |
| **总计** | **~17.5h (2-3天)** | | |

---

## 七、Open Questions

1. **Q: 熔断器的 cooldown 时间 5 分钟是否合适?**
   - 当前建议: 5 分钟。如果 Browser 平台恢复较快，可缩短到 3 分钟。
   - 决策人: 后端开发 + QA 根据实测数据调整。

2. **Q: BWVS 权重是否需要在 V1 就支持用户自定义?**
   - 当前建议: V1 使用全局常量，不支持自定义。P2 阶段再加。
   - 原因: 多数用户不会调整权重，先提供合理默认值。

3. **Q: 引用质量中"品牌官方域名"如何获取?**
   - 方案: 优先从 `brand_profile["official_website"]` 提取域名，回退尝试 `Entity.domain`。
   - 如果两者都为空，则 citation_score 给中性分 50，并在 `bwvs_breakdown` 中增加 `citation_note: "未配置品牌域名，引用质量使用中性默认分"` 字段。
   - 后续可在 Entity CRUD 中让用户手动设置 domain。

4. **Q: A5 降级报告是否需要在前端有特殊标记?**
   - 当前建议: report_data 中的 `_degraded` 和 `_degradation_note` 字段可被前端读取展示。
   - V1: 在报告顶部展示一行文字提示即可，不需要大改 UI。

---

## 附录 A: 数据流示例

### 正常流程

```
A1(品牌分析) -> A2(画像生成) -> A3(问题模拟) -> A4(答案抓取) -> A5(数据分析)
                                                                    |
                                                            metrics = {
                                                              bwvs_index: 52.35,
                                                              bwvs_breakdown: {
                                                                mention_score: 72.0,
                                                                sentiment_score: 65.5,
                                                                coverage_score: 75.0,
                                                                citation_score: 42.0,
                                                                weights: {mention:40, sentiment:25, coverage:20, citation:15},
                                                              }
                                                            }
```

### 降级流程 (A2 失败)

```
A1(品牌分析) -> A2(失败!) -> [降级通知] -> A3(品牌全景模式) -> A4(答案抓取) -> A5(数据分析)
                   |
           marketing_personas = None
           user_decisions = {**existing, "a3_mode": "brand", "a2_degraded": True}  # 字典合并
```

### 熔断流程 (Kimi 连续失败)

```
A4 Phase 2:
  Q1: Kimi 超时 -> breaker.record_failure() (count=1)
  Q2: Kimi 超时 -> breaker.record_failure() (count=2)
  Q3: Kimi 超时 -> breaker.record_failure() (count=3, CLOSED->OPEN)
  Q4: Kimi breaker.allow_request()=False -> 直接跳过
  Q5: Kimi breaker.allow_request()=False -> 直接跳过
  ...
  [5分钟后] OPEN -> HALF_OPEN
  下次请求: Kimi breaker.allow_request()=True -> 尝试一次
    成功 -> HALF_OPEN -> CLOSED (恢复正常)
    失败 -> HALF_OPEN -> OPEN (继续熔断)
```

---

## 附录 B: BWVS v2 评分示例

### 示例 1: 高可见性高质量品牌（如耐克）

| 维度 | 原始数据 | 得分 | 权重 | 加权分 |
|------|---------|------|------|--------|
| 提及率 | 75% | 90.0 | 40% | 36.0 |
| 情感 | 正面70% 中性20% 负面10% | 80.0 | 25% | 20.0 |
| 覆盖度 | 4/4 平台 | 100.0 | 20% | 20.0 |
| 引用质量 | 30% 官方引用 | 30.0 | 15% | 4.5 |
| **BWVS** | | | | **80.5** |

### 示例 2: 高提及但负面品牌

| 维度 | 原始数据 | 得分 | 权重 | 加权分 |
|------|---------|------|------|--------|
| 提及率 | 80% | 96.0 | 40% | 38.4 |
| 情感 | 正面10% 中性30% 负面60% | 25.0 | 25% | 6.25 |
| 覆盖度 | 3/4 平台 | 75.0 | 20% | 15.0 |
| 引用质量 | 5% 官方引用 | 5.0 | 15% | 0.75 |
| **BWVS** | | | | **60.4** |

对比 v1: 两个品牌在 v1 下分数分别是 75 和 80（仅基于提及率），v2 下分别是 80.5 和 60.4，更准确反映了品牌可见性的真实质量。

### 示例 3: 新品牌（数据稀疏）

| 维度 | 原始数据 | 得分 | 权重 | 加权分 |
|------|---------|------|------|--------|
| 提及率 | 20% | 24.0 | 40% | 9.6 |
| 情感 | 无足够数据 | 50.0 (中性默认) | 25% | 12.5 |
| 覆盖度 | 1/4 平台 | 25.0 | 20% | 5.0 |
| 引用质量 | 无引用数据 | 50.0 (中性默认) | 15% | 7.5 |
| **BWVS** | | | | **34.6** |

无数据维度给中性分 50 而非 0，避免了新品牌评分过低的问题。

---

## 附录 C: 审查修正记录

> **审查日期**: 2026-02-20
> **审查来源**: 架构师 (Martin Fowler) + 技术审查

| # | 修正项 | 修正前 | 修正后 | 理由 |
|---|--------|--------|--------|------|
| 1 | A2 `max_tokens` 值 | 4096 | **8192** | A2 画像 JSON 输出约 3000-5000 tokens，4096 buffer 不足，8192 提供更安全的余量 |
| 2 | `DegradationRegistry.state_patch` 字段 | 存在（A2 策略中声明 state_patch） | **删除** | 死字段，未被消费。state 修改逻辑由各 Agent node 内部负责；A4 的动态消息构建移到 `nodes_a4.py` 内部 |
| 3 | A2 降级时 `user_decisions` 写入方式 | 整体赋值 `{"a3_mode": "brand", "a2_degraded": True}` | **字典合并** `existing_decisions.update(...)` | 整体替换会覆盖之前步骤设置的其他 decision 字段，必须做 merge |
| 4 | 熔断器跨 session 共享 | 未明确说明 | **明确: 进程内全局，跨 session 共享** | 平台可用性是全局状态，不因 session 而异。这是期望行为，避免一个 session 的熔断信息对其他 session 不可见 |
| 5 | `coverage_score` 分母 | `len(platform_stats)` (动态，随实际返回平台数变化) | **固定 `len(PLATFORMS)` = 4** | 降级场景下 A4 熔断后只有 2 个平台有数据时，分母缩小会导致 coverage 虚高 (2/2=100%)，固定分母更真实 (2/4=50%) |
| 6 | `citation_score` 无域名时的处理 | 仅考虑 `total_citations == 0` 的情况 | **新增: `brand_domain` 为空时给 50 分 + `citation_note` 说明字段** | `brand_profile["official_website"]` 和 `Entity.domain` 都为空时无法计算引用质量，应明确给中性默认分并附带原因说明 |
| 7 | `_extract_domain` 函数位置 | `nodes_a5.py` 内部私有函数 | **提取到 `app/core/utils.py`** (重命名为 `extract_domain`) | `analytics_service.py` 中也有 URL 解析需求，共享工具函数避免重复 |
| 8 | E2E 测试预算 | 3h | **4h** | 熔断器状态机测试（CLOSED/OPEN/HALF_OPEN 转换 + cooldown 时间模拟）比预期复杂，需要额外 1h |
