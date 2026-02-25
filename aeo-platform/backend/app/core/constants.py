"""Application constants and configuration values.

This module contains all hardcoded values that should be configurable.
"""

from typing import Final


class WorkflowConstants:
    """Workflow execution constants."""

    # Timeout settings (seconds)
    LLM_TIMEOUT: Final[int] = 120
    FETCH_TIMEOUT_API: Final[int] = 30
    FETCH_TIMEOUT_BROWSER: Final[int] = 60

    # Retry settings
    MAX_RETRIES: Final[int] = 3
    RETRY_DELAY: Final[int] = 60

    # Concurrency settings
    MAX_CONCURRENT_API: Final[int] = 5
    MAX_CONCURRENT_BROWSER: Final[int] = 2

    # Progress settings
    PROGRESS_UPDATE_INTERVAL: Final[float] = 0.5

    # Question generation
    BASELINE_QUESTION_COUNT: Final[int] = 30
    PERSONA_QUESTION_COUNT: Final[int] = 20

    # Competitor analysis
    MIN_COMPETITORS: Final[int] = 8
    MAX_COMPETITORS: Final[int] = 12

    # Persona generation
    MIN_PERSONAS: Final[int] = 6
    MAX_PERSONAS: Final[int] = 8


class LLMConstants:
    """LLM model constants."""

    # Temperature settings
    DEFAULT_TEMPERATURE: Final[float] = 1.0
    CREATIVE_TEMPERATURE: Final[float] = 0.8
    PRECISE_TEMPERATURE: Final[float] = 0.5

    # Token limits
    DEFAULT_MAX_TOKENS: Final[int] = 16384
    EXTENDED_MAX_TOKENS: Final[int] = 16384

    # Model names
    DEFAULT_MODEL: Final[str] = "MiniMax-M2.1"
    FALLBACK_MODEL: Final[str] = "gpt-4"


class PlatformConstants:
    """AI platform constants."""

    SUPPORTED_PLATFORMS: Final[list[str]] = [
        "doubao",
        "hunyuan",
        "kimi",
        "deepseek",
    ]

    API_PLATFORMS: Final[list[str]] = ["doubao", "hunyuan"]
    BROWSER_PLATFORMS: Final[list[str]] = ["kimi", "deepseek"]

    # Platform-specific timeouts (per-question, seconds)
    PLATFORM_TIMEOUTS: Final[dict[str, int]] = {
        "doubao": 30,
        "hunyuan": 30,
        "kimi": 400,
        "deepseek": 90,
    }

    # Global per-pipeline timeout (seconds): caps entire browser platform regardless of question count
    BROWSER_PIPELINE_TIMEOUT: Final[int] = 600  # 10 minutes max per browser platform (12 questions × ~45s)


class CacheConstants:
    """Cache and storage constants."""

    # Redis TTL (seconds)
    TASK_TTL: Final[int] = 3600  # 1 hour
    SESSION_TTL: Final[int] = 86400  # 24 hours
    RESULT_TTL: Final[int] = 604800  # 7 days

    # Checkpoint settings
    CHECKPOINT_INTERVAL: Final[int] = 10  # Save every N steps


class WebSocketConstants:
    """WebSocket communication constants."""

    # Heartbeat
    HEARTBEAT_INTERVAL: Final[int] = 30  # seconds
    HEARTBEAT_TIMEOUT: Final[int] = 60  # seconds

    # Reconnection
    MAX_RECONNECT_ATTEMPTS: Final[int] = 5
    BASE_RECONNECT_DELAY: Final[int] = 1000  # milliseconds

    # Message size
    MAX_MESSAGE_SIZE: Final[int] = 1024 * 1024  # 1MB


class UIConstants:
    """UI and display constants."""

    # Progress display
    PROGRESS_DECIMALS: Final[int] = 1

    # Chart colors
    CHART_COLORS: Final[list[str]] = [
        "#6366F1",  # Primary
        "#10B981",  # Success
        "#F59E0B",  # Warning
        "#EF4444",  # Error
        "#8B5CF6",  # Purple
        "#EC4899",  # Pink
        "#06B6D4",  # Cyan
        "#84CC16",  # Lime
    ]

    # Animation durations (seconds)
    ANIMATION_FAST: Final[float] = 0.15
    ANIMATION_NORMAL: Final[float] = 0.25
    ANIMATION_SLOW: Final[float] = 0.35
