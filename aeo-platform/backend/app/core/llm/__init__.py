"""LLM abstraction layer.

Usage:
    from app.core.llm import get_llm_model, LLMResponse

    model = get_llm_model()          # returns provider based on LLM_PROVIDER setting
    response = model(messages=[...])  # LLMResponse
"""

from app.core.llm.base import (  # noqa: F401
    BaseLLMConfig,
    BaseLLMModel,
    LLMResponse,
    ThinkingBlock,
    ToolCallBlock,
)


def get_llm_model() -> BaseLLMModel:
    """Factory: create LLM model instance based on LLM_PROVIDER setting."""
    from app.config import get_settings

    settings = get_settings()
    provider = getattr(settings, "LLM_PROVIDER", "minimax").lower()

    if provider == "minimax":
        from app.core.llm.minimax import MiniMaxConfig, MiniMaxModel

        return MiniMaxModel(MiniMaxConfig())

    if provider == "glm5":
        from app.core.llm.glm5 import GLM5Config, GLM5Model

        return GLM5Model(GLM5Config())

    raise ValueError(f"Unknown LLM provider: {provider}")
