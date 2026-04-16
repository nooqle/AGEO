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
    SCHEDULER_ENABLED: bool = True

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
        "http://localhost:3001",
        "http://127.0.0.1:3001",
        "http://localhost:3010",
        "http://127.0.0.1:3010",
        "http://localhost:3011",
        "http://127.0.0.1:3011",
    ]

    # Browser
    PLAYWRIGHT_BROWSERS_PATH: str = "0"

    # AIO Cloud Sandbox
    AIO_ENABLED: bool = False
    AIO_BASE_URL: str | None = None
    AIO_AUTH_TOKEN: str | None = None
    AIO_REQUEST_TIMEOUT_SECONDS: float = 20.0
    AIO_DEFAULT_ACCESS_MODE: str = "vnc_fallback"
    AIO_IDLE_TTL_SECONDS: int = 900
    AIO_TAKEOVER_HEARTBEAT_INTERVAL_MS: int = 10000
    AIO_TAKEOVER_ISSUED_TTL_SECONDS: int = 480
    AIO_TAKEOVER_HEARTBEAT_TTL_SECONDS: int = 30
    AIO_MAX_PARALLEL_BROWSER_SESSIONS: int = 4
    AIO_AUTH_ENV_SCOPE: str = "default"
    AIO_BROWSER_LOCALE: str = "zh-CN"
    AIO_BROWSER_ACCEPT_LANGUAGE: str = "zh-CN,zh;q=0.9,en;q=0.8"
    AIO_BROWSER_TIMEZONE_ID: str = "Asia/Shanghai"

    # LLM Orchestration Mode (v2)
    USE_LLM_ORCHESTRATION: bool = False

    # Outputs
    OUTPUT_DIR: str = "outputs"

    # Auth
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    VERIFICATION_CODE_EXPIRE_MINUTES: int = 10
    INVITE_CODE_EXPIRE_MINUTES: int = 60 * 24 * 7
    VERIFICATION_SEND_COOLDOWN_SECONDS: int = 60
    VERIFICATION_MAX_ATTEMPTS: int = 5
    VERIFICATION_EMAIL_PROVIDER: str = "console"
    VERIFICATION_SMS_PROVIDER: str = "console"
    VERIFICATION_EMAIL_FROM_ADDRESS: str | None = None
    VERIFICATION_EMAIL_FROM_NAME: str = "Specta AI"
    VERIFICATION_EMAIL_SUBJECT_PREFIX: str = "【Specta AI】"
    ACCOUNT_APPROVAL_EMAIL_SUBJECT_PREFIX: str = "【Specta AI】"
    VERIFICATION_SMTP_HOST: str | None = None
    VERIFICATION_SMTP_PORT: int = 587
    VERIFICATION_SMTP_USERNAME: str | None = None
    VERIFICATION_SMTP_PASSWORD: str | None = None
    VERIFICATION_SMTP_USE_TLS: bool = True
    VERIFICATION_SMTP_USE_SSL: bool = False
    TENCENT_SES_SECRET_ID: str | None = None
    TENCENT_SES_SECRET_KEY: str | None = None
    TENCENT_SES_REGION: str = "ap-guangzhou"
    TENCENT_SES_FROM_EMAIL_ADDRESS: str | None = None
    TENCENT_SES_REPLY_TO_ADDRESS: str | None = None
    TENCENT_SES_TEMPLATE_ID: int | None = None
    TENCENT_SES_TEMPLATE_VARIABLES: str = "code"
    TENCENT_SES_INVITE_CODE_TEMPLATE_ID: int | None = None
    TENCENT_SES_INVITE_CODE_TEMPLATE_VARIABLES: str = "code,login_url"
    TENCENT_SES_ACCOUNT_APPROVAL_TEMPLATE_ID: int | None = None
    TENCENT_SES_ACCOUNT_APPROVAL_TEMPLATE_VARIABLES: str = (
        "email,organization_name,login_url"
    )
    APP_LOGIN_URL: str = "http://127.0.0.1:3011/auth"

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


def _require_settings() -> None:
    is_dev = settings.DEBUG or settings.DEV_MODE_ENABLED
    if not is_dev and settings.JWT_SECRET == "dev-secret-change-me":
        raise RuntimeError("生产环境禁止使用默认 JWT_SECRET，请在环境变量中显式配置")

    email_provider = settings.VERIFICATION_EMAIL_PROVIDER.strip().lower()
    if email_provider == "smtp":
        missing: list[str] = []
        if not settings.VERIFICATION_SMTP_HOST:
            missing.append("VERIFICATION_SMTP_HOST")
        if not settings.VERIFICATION_SMTP_PORT:
            missing.append("VERIFICATION_SMTP_PORT")
        if not settings.VERIFICATION_SMTP_PASSWORD:
            missing.append("VERIFICATION_SMTP_PASSWORD")
        if not settings.VERIFICATION_EMAIL_FROM_ADDRESS:
            missing.append("VERIFICATION_EMAIL_FROM_ADDRESS")
        if missing:
            raise RuntimeError("SMTP 邮件 provider 缺少必填配置: " + ", ".join(missing))
    if email_provider == "tencent_ses_api":
        missing: list[str] = []
        if not settings.TENCENT_SES_SECRET_ID:
            missing.append("TENCENT_SES_SECRET_ID")
        if not settings.TENCENT_SES_SECRET_KEY:
            missing.append("TENCENT_SES_SECRET_KEY")
        if not settings.TENCENT_SES_FROM_EMAIL_ADDRESS:
            missing.append("TENCENT_SES_FROM_EMAIL_ADDRESS")
        if not settings.TENCENT_SES_TEMPLATE_ID:
            missing.append("TENCENT_SES_TEMPLATE_ID")
        if missing:
            raise RuntimeError(
                "腾讯云 SES 邮件 provider 缺少必填配置: " + ", ".join(missing)
            )


_require_settings()
