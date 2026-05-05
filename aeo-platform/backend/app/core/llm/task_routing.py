"""Task-level LLM routing.

The global LLM provider remains a fallback. Runtime-sensitive tasks route
explicitly so changing one skill does not accidentally move A1/A4/AIO.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.core.llm import BaseLLMModel, get_llm_model

logger = logging.getLogger(__name__)


def get_orchestrator_llm_model() -> BaseLLMModel:
    """Model for orchestration and complex planning."""

    return _get_task_model(
        task_name="orchestrator",
        provider_attr="ORCHESTRATOR_LLM_PROVIDER",
        model_attr="ORCHESTRATOR_MODEL_NAME",
        thinking_attr="ORCHESTRATOR_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-v4-pro",
        default_thinking=True,
        fallback_provider="glm5",
        fallback_model="glm-5",
        fallback_thinking=True,
    )


def get_long_text_llm_model() -> BaseLLMModel:
    """Model for long-form analysis, summaries, and report explanations."""

    return _get_task_model(
        task_name="long_text",
        provider_attr="LONG_TEXT_LLM_PROVIDER",
        model_attr="LONG_TEXT_MODEL_NAME",
        thinking_attr="LONG_TEXT_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-v4-pro",
        default_thinking=True,
        fallback_provider="glm5",
        fallback_model="glm-5",
        fallback_thinking=True,
    )


def get_a1_llm_model() -> BaseLLMModel:
    """Model for A1 brand discovery. Kept on GLM-5 for search behavior."""

    return _get_task_model(
        task_name="a1_brand_discovery",
        provider_attr="A1_LLM_PROVIDER",
        model_attr="A1_MODEL_NAME",
        thinking_attr="A1_THINKING_ENABLED",
        default_provider="glm5",
        default_model="glm-5",
        default_thinking=True,
        fallback_provider="glm5",
        fallback_model="glm-5",
        fallback_thinking=True,
    )


def get_a3_llm_model() -> BaseLLMModel:
    """Model for A3 question generation. Isolated from A1 and A2 routing."""

    return _get_task_model(
        task_name="a3_question_generation",
        provider_attr="A3_LLM_PROVIDER",
        model_attr="A3_MODEL_NAME",
        thinking_attr="A3_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-v4-pro",
        default_thinking=False,
        fallback_provider="glm5",
        fallback_model="glm-5",
        fallback_thinking=False,
    )


def get_fast_structured_llm_model() -> BaseLLMModel:
    """Model for short JSON/structured generation where thinking is harmful."""

    settings = get_settings()
    provider = _settings_str(settings, "FAST_STRUCTURED_LLM_PROVIDER", "").lower()
    model_name = _settings_optional_str(settings, "FAST_STRUCTURED_MODEL_NAME")
    if not provider:
        provider = _settings_str(settings, "LLM_PROVIDER", "glm5").lower()
    if not model_name:
        model_name = _default_model_for_provider(provider, settings)

    return _get_model_with_fallback(
        task_name="fast_structured",
        provider=provider,
        model_name=model_name,
        thinking_enabled=bool(
            getattr(settings, "FAST_STRUCTURED_THINKING_ENABLED", False)
        ),
        fallback_provider="glm5",
        fallback_model="glm-5",
        fallback_thinking=False,
    )


def _get_task_model(
    *,
    task_name: str,
    provider_attr: str,
    model_attr: str,
    thinking_attr: str,
    default_provider: str,
    default_model: str,
    default_thinking: bool,
    fallback_provider: str,
    fallback_model: str,
    fallback_thinking: bool,
) -> BaseLLMModel:
    settings = get_settings()
    provider = _settings_str(settings, provider_attr, default_provider).lower()
    model_name = _settings_str(settings, model_attr, default_model)
    thinking_enabled = bool(getattr(settings, thinking_attr, default_thinking))
    return _get_model_with_fallback(
        task_name=task_name,
        provider=provider,
        model_name=model_name,
        thinking_enabled=thinking_enabled,
        fallback_provider=fallback_provider,
        fallback_model=fallback_model,
        fallback_thinking=fallback_thinking,
    )


def _get_model_with_fallback(
    *,
    task_name: str,
    provider: str,
    model_name: str | None,
    thinking_enabled: bool,
    fallback_provider: str,
    fallback_model: str | None,
    fallback_thinking: bool,
) -> BaseLLMModel:
    try:
        return get_llm_model(
            provider=provider,
            model_name=model_name,
            thinking_enabled=thinking_enabled,
        )
    except Exception as exc:
        logger.warning(
            "[llm-task-routing] %s failed to initialize %s/%s; falling back to %s/%s: %s",
            task_name,
            provider,
            model_name,
            fallback_provider,
            fallback_model,
            exc,
        )
        return get_llm_model(
            provider=fallback_provider,
            model_name=fallback_model,
            thinking_enabled=fallback_thinking,
        )


def _settings_str(settings: Any, attr: str, default: str) -> str:
    return str(getattr(settings, attr, default) or default).strip()


def _settings_optional_str(settings: Any, attr: str) -> str | None:
    value = getattr(settings, attr, None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _default_model_for_provider(provider: str, settings: Any) -> str | None:
    provider = provider.lower()
    if provider == "deepseek":
        return str(getattr(settings, "DEEPSEEK_PRO_MODEL_NAME", "") or "").strip() or (
            "deepseek-v4-pro"
        )
    if provider == "glm5":
        return str(getattr(settings, "GLM5_MODEL_NAME", "") or "").strip() or "glm-5"
    if provider == "minimax":
        return (
            str(getattr(settings, "MINIMAX_MODEL_NAME", "") or "").strip()
            or "MiniMax-M2.1"
        )
    return None
