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
    BROWSER_AGENT_LLM_ENABLED: bool = True
    BROWSER_AGENT_LLM_MAX_CONCURRENCY: int = 2
    BROWSER_AGENT_LLM_MAX_TOKENS: int = 384
    BROWSER_AGENT_LLM_THINKING_ENABLED: bool = False
    BROWSER_AGENT_LLM_MODEL_NAME: str | None = "glm-5"
    BROWSER_AGENT_LLM_API_KEY: str | None = None

    # LLM Provider Selection
    LLM_PROVIDER: str = "glm5"

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
    GLM5_MODEL_NAME: str = "glm-5.1"
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

    # MiniMax cost config (optional)
    MINIMAX_PRICE_INPUT_PER_MTOKENS: float | None = None
    MINIMAX_PRICE_OUTPUT_PER_MTOKENS: float | None = None
    MINIMAX_CACHE_HIT_PRICE_FACTOR: float = 1.0

    # Doubao API
    DOUBAO_API_KEY: str | None = None
    DOUBAO_MODEL: str = "doubao-seed-2-0-lite-260215"

    # Hunyuan API
    HUNYUAN_API_KEY: str | None = None
    HUNYUAN_MODEL: str = "hunyuan-2.0-instruct-20251111"
    HUNYUAN_BASE_URL: str = "https://api.hunyuan.cloud.tencent.com/v1"

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
