"""Application configuration using Pydantic Settings."""

from functools import lru_cache
from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录的绝对路径
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=(
            str(_BACKEND_DIR / ".env"),
            str(_BACKEND_DIR / ".env.local"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Specta AI Platform"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:password@localhost:5432/specta_db"
    )
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10

    # Sync Database URL for Alembic
    SYNC_DATABASE_URL: str = "postgresql://postgres:password@localhost:5432/specta_db"

    # CORS
    CORS_ORIGINS: str = (
        "http://localhost:3000,"
        "http://127.0.0.1:3000,"
        "http://localhost:3001,"
        "http://127.0.0.1:3001"
    )

    # Logging
    LOG_LEVEL: str = "INFO"
    SCHEDULER_ENABLED: bool = True

    # Redis (Optional)
    REDIS_URL: str | None = None

    # AIO Cloud Sandbox
    AIO_ENABLED: bool = False
    AIO_BASE_URL: str | None = None
    AIO_AUTH_TOKEN: str | None = None
    AIO_REQUEST_TIMEOUT_SECONDS: float = 20.0
    AIO_DEFAULT_ACCESS_MODE: str = "canvas_cdp"
    AIO_IDLE_TTL_SECONDS: int = 900
    AIO_TAKEOVER_HEARTBEAT_INTERVAL_MS: int = 10000
    AIO_TAKEOVER_HEARTBEAT_TTL_SECONDS: int = 30
    AIO_FOREGROUND_LEASE_ENABLED: bool = True
    AIO_FOREGROUND_GUI_LEASE_TTL_SECONDS: int = 30
    AIO_FOREGROUND_GUI_LEASE_WAIT_SECONDS: float = 60.0
    AIO_FOREGROUND_HUMAN_LEASE_TTL_SECONDS: int = 480
    AIO_FOREGROUND_HUMAN_LEASE_WAIT_SECONDS: float = 15.0
    BROWSER_AGENT_LLM_ENABLED: bool = False
    BROWSER_AGENT_LLM_MAX_CONCURRENCY: int = 2
    BROWSER_AGENT_LLM_MAX_TOKENS: int = 384
    BROWSER_AGENT_LLM_THINKING_ENABLED: bool = False
    BROWSER_AGENT_LLM_MODEL_NAME: str | None = None
    BROWSER_AGENT_LLM_API_KEY: str | None = None

    # LLM Provider Selection
    LLM_PROVIDER: str = "deepseek"

    # LLM API Keys
    MINIMAX_API_KEY: str | None = None
    MINIMAX_BASE_URL: str = "https://api.minimaxi.com/v1"
    MINIMAX_MODEL_NAME: str = "MiniMax-M2.1"
    MINIMAX_REASONING_SPLIT: bool = True
    MINIMAX_TEMPERATURE: float = 1.0
    MINIMAX_MAX_TOKENS: int = 16384

    # GLM5 (智谱AI)
    GLM5_API_KEY: str | None = None
    GLM5_BASE_URL: str = "https://open.bigmodel.cn/api/paas/v4"
    GLM5_MODEL_NAME: str = "glm-5"
    GLM5_THINKING_ENABLED: bool = True
    GLM5_TEMPERATURE: float = 0.7
    GLM5_MAX_TOKENS: int = 16384
    GLM5_LONG_CONTEXT_THRESHOLD_TOKENS: int = 32000
    GLM5_PRICE_INPUT_PER_MTOKENS: float | None = None
    GLM5_PRICE_OUTPUT_PER_MTOKENS: float | None = None
    GLM5_PRICE_LONG_INPUT_PER_MTOKENS: float | None = None
    GLM5_PRICE_LONG_OUTPUT_PER_MTOKENS: float | None = None
    GLM5_TURBO_PRICE_INPUT_PER_MTOKENS: float | None = None
    GLM5_TURBO_PRICE_OUTPUT_PER_MTOKENS: float | None = None
    GLM5_TURBO_PRICE_LONG_INPUT_PER_MTOKENS: float | None = None
    GLM5_TURBO_PRICE_LONG_OUTPUT_PER_MTOKENS: float | None = None
    GLM5_CACHE_HIT_PRICE_FACTOR: float = 0.5
    GLM5_TURBO_CACHE_HIT_PRICE_FACTOR: float = 0.5
    LLM_COST_REPORTING_CURRENCY: str = "CNY"

    # DeepSeek
    DEEPSEEK_API_KEY: str | None = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL_NAME: str = "deepseek-flash"
    DEEPSEEK_FLASH_MODEL_NAME: str = "deepseek-flash"
    DEEPSEEK_PRO_MODEL_NAME: str = "deepseek-flash"
    DEEPSEEK_THINKING_ENABLED: bool = False
    DEEPSEEK_REASONING_EFFORT: str = "high"
    DEEPSEEK_TEMPERATURE: float = 0.0
    DEEPSEEK_MAX_TOKENS: int = 8192
    DEEPSEEK_TIMEOUT_SECONDS: float = 120.0
    DEEPSEEK_PRICE_CURRENCY: str = "CNY"
    DEEPSEEK_FLASH_PRICE_INPUT_CACHE_HIT_PER_MTOKENS: float = 0.02
    DEEPSEEK_FLASH_PRICE_INPUT_CACHE_MISS_PER_MTOKENS: float = 1.0
    DEEPSEEK_FLASH_PRICE_OUTPUT_PER_MTOKENS: float = 2.0
    DEEPSEEK_PRO_PRICE_INPUT_CACHE_HIT_PER_MTOKENS: float = 0.025
    DEEPSEEK_PRO_PRICE_INPUT_CACHE_MISS_PER_MTOKENS: float = 3.0
    DEEPSEEK_PRO_PRICE_OUTPUT_PER_MTOKENS: float = 6.0

    # Canonical model profiles
    TEXT_REASONING_LLM_PROVIDER: str = "deepseek"
    TEXT_REASONING_MODEL_NAME: str = "deepseek-flash"
    TEXT_REASONING_THINKING_ENABLED: bool = True
    TEXT_LIGHT_LLM_PROVIDER: str = "deepseek"
    TEXT_LIGHT_MODEL_NAME: str = "deepseek-flash"
    TEXT_LIGHT_THINKING_ENABLED: bool = False
    MULTIMODAL_LLM_PROVIDER: str = "deepseek"
    MULTIMODAL_MODEL_NAME: str = "deepseek-flash"
    MULTIMODAL_THINKING_ENABLED: bool = True

    # Legacy task-level LLM routing fields retained for old env compatibility.
    # Runtime task routing now maps tasks to the canonical model profiles above.
    ORCHESTRATOR_LLM_PROVIDER: str = "deepseek"
    ORCHESTRATOR_MODEL_NAME: str = "deepseek-flash"
    ORCHESTRATOR_THINKING_ENABLED: bool = True
    ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED: bool = False
    ORCHESTRATOR_STABLE_TOOL_SURFACE_ENABLED: bool = False
    STABLE_SKILL_TOOL_DESCRIPTION_ENABLED: bool = False
    LONG_TEXT_LLM_PROVIDER: str = "deepseek"
    LONG_TEXT_MODEL_NAME: str = "deepseek-flash"
    LONG_TEXT_THINKING_ENABLED: bool = True
    A1_LLM_PROVIDER: str = "deepseek"
    A1_MODEL_NAME: str = "deepseek-flash"
    A1_THINKING_ENABLED: bool = True
    A3_LLM_PROVIDER: str = "deepseek"
    A3_MODEL_NAME: str = "deepseek-flash"
    A3_THINKING_ENABLED: bool = False
    FAST_STRUCTURED_LLM_PROVIDER: str | None = None
    FAST_STRUCTURED_MODEL_NAME: str | None = None
    FAST_STRUCTURED_THINKING_ENABLED: bool = False
    URL_INTELLIGENCE_LLM_PROVIDER: str = "deepseek"
    URL_INTELLIGENCE_MODEL_NAME: str = "deepseek-flash"
    URL_INTELLIGENCE_TIMEOUT_SECONDS: float = 45.0
    URL_INTELLIGENCE_BATCH_SIZE: int = 60

    # MiniMax cost config (optional)
    MINIMAX_PRICE_INPUT_PER_MTOKENS: float | None = None
    MINIMAX_PRICE_OUTPUT_PER_MTOKENS: float | None = None
    MINIMAX_CACHE_HIT_PRICE_FACTOR: float = 1.0

    # Doubao API
    DOUBAO_API_KEY: str | None = None
    DOUBAO_MODEL: str = "doubao-seed-2-0-lite-260215"
    DOUBAO_FAST_MODEL: str | None = "doubao-seed-2-0-mini-260215"
    DOUBAO_USE_APP_API: bool = False
    DOUBAO_FAST_USE_APP_API: bool = True
    DOUBAO_APP_FEATURE: str = "ai_search"
    DOUBAO_APP_ROLE_DESCRIPTION: str = (
        "You are a professional information assistant. Use search to answer "
        "accurately and cite sources when available."
    )
    DOUBAO_APP_API_FALLBACK_TO_WEB_SEARCH: bool = True
    DOUBAO_LITE_PRICE_INPUT_CACHE_MISS_PER_MTOKENS: float = 0.6
    DOUBAO_LITE_PRICE_INPUT_CACHE_HIT_PER_MTOKENS: float = 0.12
    DOUBAO_LITE_PRICE_OUTPUT_PER_MTOKENS: float = 3.6
    DOUBAO_MINI_PRICE_INPUT_CACHE_MISS_PER_MTOKENS: float = 0.2
    DOUBAO_MINI_PRICE_INPUT_CACHE_HIT_PER_MTOKENS: float = 0.04
    DOUBAO_MINI_PRICE_OUTPUT_PER_MTOKENS: float = 2.0

    # Hunyuan API
    HUNYUAN_API_KEY: str | None = None
    HUNYUAN_MODEL: str = "hy3"
    HUNYUAN_FAST_MODEL: str | None = None
    HUNYUAN_BASE_URL: str = "https://tokenhub.tencentmaas.com/v1"
    HUNYUAN_2_INSTRUCT_PRICE_INPUT_PER_MTOKENS: float = 4.505
    HUNYUAN_2_INSTRUCT_PRICE_OUTPUT_PER_MTOKENS: float = 11.13

    # Moonshot / Kimi API
    MOONSHOT_PRICE_INPUT_CACHE_MISS_PER_MTOKENS: float = 4.0
    MOONSHOT_PRICE_INPUT_CACHE_HIT_PER_MTOKENS: float = 0.7
    MOONSHOT_PRICE_OUTPUT_PER_MTOKENS: float = 21.0

    # A4 fast fetch tuning
    A4_DOUBAO_API_DELAY_SECONDS: float = 3.0
    A4_HUNYUAN_API_DELAY_SECONDS: float = 1.0
    A4_KIMI_API_DELAY_SECONDS: float = 8.0
    A4_DOUBAO_API_CONCURRENCY: int = 1
    A4_HUNYUAN_API_CONCURRENCY: int = 1
    A4_KIMI_API_CONCURRENCY: int = 1
    A4_DOUBAO_API_MAX_RETRIES: int = 2
    A4_HUNYUAN_API_MAX_RETRIES: int = 2
    A4_KIMI_API_MAX_RETRIES: int = 2
    A4_KIMI_API_TIMEOUT_SECONDS: float = 90.0
    A4_KIMI_API_429_COOLDOWN_SECONDS: float = 20.0

    # Bocha API
    BOCHA_API_KEY: str | None = None

    # LLM Orchestration
    USE_LLM_ORCHESTRATION: bool = True

    DASHSCOPE_API_KEY: str | None = None

    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins string to list."""
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
