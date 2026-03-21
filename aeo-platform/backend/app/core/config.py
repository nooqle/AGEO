"""Application configuration."""

from pathlib import Path
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/ 目录的绝对路径，确保无论 cwd 在哪都能找到 .env.local
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


def _resolve_sqlite_url(url: str) -> str:
    """Pin relative SQLite URLs to the backend directory.

    Dev restarts on Windows may happen from different working directories. A
    relative sqlite path would silently create a second empty DB and make the UI
    look like all history disappeared.
    """
    prefixes = ("sqlite+aiosqlite:///", "sqlite:///")
    for prefix in prefixes:
        if url.startswith(prefix):
            db_path = url[len(prefix) :]
            if db_path.startswith("./"):
                absolute = (_BACKEND_DIR / db_path[2:]).resolve().as_posix()
                return f"{prefix}{absolute}"
            break
    return url


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(
        env_file=str(_BACKEND_DIR / ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    APP_NAME: str = "Specta AI"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./specta_dev.db"

    # Redis (optional)
    REDIS_URL: str | None = None

    # LLM API Keys
    MINIMAX_API_KEY: str | None = None
    MINIMAX_BASE_URL: str = "https://api.minimaxi.com/v1"
    MINIMAX_MODEL: str = "MiniMax-M2.1"
    DOUBAO_API_KEY: str | None = None
    DOUBAO_MODEL: str = "doubao-seed-2-0-lite-260215"
    HUNYUAN_API_KEY: str | None = None
    HUNYUAN_MODEL: str = "hunyuan-2.0-instruct-20251111"
    HUNYUAN_BASE_URL: str = "https://api.hunyuan.cloud.tencent.com/v1"
    MOONSHOT_API_KEY: str | None = None
    MOONSHOT_MODEL: str = "kimi-k2-turbo-preview"
    MOONSHOT_BASE_URL: str = "https://api.moonshot.cn/v1/chat/completions"
    BOCHA_API_KEY: str | None = None

    # CORS
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3010",
        "http://127.0.0.1:3010",
        "http://localhost:3011",
        "http://127.0.0.1:3011",
    ]

    # Browser
    PLAYWRIGHT_BROWSERS_PATH: str = "0"

    # LLM Orchestration Mode (v2)
    USE_LLM_ORCHESTRATION: bool = False

    # Outputs
    OUTPUT_DIR: str = "outputs"

    # Auth
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # Development mode settings
    DEV_MODE_ENABLED: bool = (
        False  # Enable development mode features (set True in .env.local)
    )
    DEV_TOKEN: str = "dev-token"  # Default token for development
    DEV_USER_EMAIL: str = "dev@test.com"  # Default test user email
    DEV_USER_NAME: str = "Development User"  # Default test user name

    @property
    def is_sqlite(self) -> bool:
        """Check if using SQLite."""
        return self.DATABASE_URL.startswith("sqlite")

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self.DATABASE_URL.startswith("postgresql")


# Global settings instance
settings = Settings()
settings.DATABASE_URL = _resolve_sqlite_url(settings.DATABASE_URL)
