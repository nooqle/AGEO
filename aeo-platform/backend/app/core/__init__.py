"""Core modules."""

from app.core.database import Base, engine, get_db, init_db
from app.core.exceptions import (
    AppException,
    ConflictException,
    ForbiddenException,
    NotFoundException,
    UnauthorizedException,
    ValidationException,
)
from app.core.llm import (
    get_llm_model,
    LLMResponse,
    ThinkingBlock,
    ToolCallBlock,
    BaseLLMModel,
)
# Backward-compat re-exports
from app.core.minimax_config import MiniMaxConfig  # noqa: F401
from app.core.minimax_model import MiniMaxModel  # noqa: F401

__all__ = [
    # Database
    "Base",
    "engine",
    "get_db",
    "init_db",
    # Exceptions
    "AppException",
    "ConflictException",
    "ForbiddenException",
    "NotFoundException",
    "UnauthorizedException",
    "ValidationException",
    # LLM (new)
    "get_llm_model",
    "LLMResponse",
    "ThinkingBlock",
    "ToolCallBlock",
    "BaseLLMModel",
    # Backward compat
    "MiniMaxConfig",
    "MiniMaxModel",
]
