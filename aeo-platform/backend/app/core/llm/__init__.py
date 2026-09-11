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
    LLMUsage,
    ThinkingBlock,
    ToolCallBlock,
)


def get_llm_model(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    thinking_enabled: bool | None = None,
    api_key: str | None = None,
) -> BaseLLMModel:
    """Factory: create LLM model instance.

    When provider is omitted, the global LLM_PROVIDER remains the default.
    Task-specific callers should pass provider/model_name explicitly so a
    local skill can move providers without changing A4/AIO runtime behavior.
    """
    from app.config import get_settings

    settings = get_settings()
    selected_provider = (provider or getattr(settings, "LLM_PROVIDER", "deepseek")).lower()

    if selected_provider == "minimax":
        from app.core.llm.minimax import MiniMaxConfig, MiniMaxModel

        return MiniMaxModel(MiniMaxConfig(model_name=model_name or "MiniMax-M2.1", api_key=api_key))

    if selected_provider == "glm5":
        from app.core.llm.glm5 import GLM5Config, GLM5Model

        config_kwargs = {}
        if api_key:
            config_kwargs["api_key"] = api_key
        if model_name:
            config_kwargs["model_name"] = model_name
        if thinking_enabled is not None:
            config_kwargs["thinking_enabled"] = thinking_enabled
        return GLM5Model(GLM5Config(**config_kwargs))

    if selected_provider == "deepseek":
        from app.core.llm.deepseek import DeepSeekConfig, DeepSeekModel

        config_kwargs = {}
        if api_key:
            config_kwargs["api_key"] = api_key
        if model_name:
            config_kwargs["model_name"] = model_name
        if thinking_enabled is not None:
            config_kwargs["thinking_enabled"] = thinking_enabled
        return DeepSeekModel(DeepSeekConfig(**config_kwargs))

    raise ValueError(f"Unknown LLM provider: {selected_provider}")
