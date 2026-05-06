"""Profile-based LLM routing.

The global LLM provider remains a fallback. Runtime-sensitive tasks route
explicitly through three canonical model profiles so changing one skill does
not accidentally move A1/A4/AIO.
"""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.core.llm import BaseLLMModel, get_llm_model

logger = logging.getLogger(__name__)


def get_orchestrator_llm_model() -> BaseLLMModel:
    """Model for orchestration and complex planning."""

    return get_text_reasoning_llm_model(task_name="orchestrator")


def get_long_text_llm_model() -> BaseLLMModel:
    """Model for long-form analysis, summaries, and report explanations."""

    return get_text_reasoning_llm_model(task_name="long_text")


def get_a1_llm_model() -> BaseLLMModel:
    """Model for A1 brand discovery. Kept on GLM-5 for search behavior."""

    return get_multimodal_llm_model(task_name="a1_brand_discovery")


def get_a2_llm_model() -> BaseLLMModel:
    """Model for A2 persona generation."""

    return get_text_reasoning_llm_model(task_name="a2_persona_generation")


def get_a3_llm_model() -> BaseLLMModel:
    """Model for A3 question generation. Isolated from A1 and A2 routing."""

    return get_text_reasoning_llm_model(task_name="a3_question_generation")


def get_fast_structured_llm_model() -> BaseLLMModel:
    """Model for short JSON/structured generation where thinking is harmful."""

    return get_text_light_llm_model(task_name="fast_structured")


def get_text_reasoning_llm_model(*, task_name: str = "text_reasoning") -> BaseLLMModel:
    """Canonical text reasoning model profile, currently DeepSeek v4 Pro."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="TEXT_REASONING_LLM_PROVIDER",
        model_attr="TEXT_REASONING_MODEL_NAME",
        thinking_attr="TEXT_REASONING_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-v4-pro",
        default_thinking=True,
        fallback_profile="multimodal",
    )


def get_text_light_llm_model(*, task_name: str = "text_light") -> BaseLLMModel:
    """Canonical light text model profile, currently DeepSeek v4 Flash."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="TEXT_LIGHT_LLM_PROVIDER",
        model_attr="TEXT_LIGHT_MODEL_NAME",
        thinking_attr="TEXT_LIGHT_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-v4-flash",
        default_thinking=False,
        fallback_profile="multimodal",
    )


def get_multimodal_llm_model(*, task_name: str = "multimodal") -> BaseLLMModel:
    """Canonical multimodal model profile, currently GLM-5."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="MULTIMODAL_LLM_PROVIDER",
        model_attr="MULTIMODAL_MODEL_NAME",
        thinking_attr="MULTIMODAL_THINKING_ENABLED",
        default_provider="glm5",
        default_model="glm-5",
        default_thinking=True,
        fallback_profile=None,
    )


def _get_profile_model(
    *,
    task_name: str,
    provider_attr: str,
    model_attr: str,
    thinking_attr: str,
    default_provider: str,
    default_model: str,
    default_thinking: bool,
    fallback_profile: str | None,
) -> BaseLLMModel:
    settings = get_settings()
    provider = _settings_str(settings, provider_attr, default_provider).lower()
    model_name = _settings_str(settings, model_attr, default_model)
    thinking_enabled = bool(getattr(settings, thinking_attr, default_thinking))
    fallback_provider, fallback_model, fallback_thinking = _fallback_profile_values(
        settings,
        fallback_profile,
    )
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


def _fallback_profile_values(
    settings: Any,
    fallback_profile: str | None,
) -> tuple[str, str | None, bool]:
    if fallback_profile == "multimodal":
        return (
            _settings_str(settings, "MULTIMODAL_LLM_PROVIDER", "glm5").lower(),
            _settings_str(settings, "MULTIMODAL_MODEL_NAME", "glm-5"),
            bool(getattr(settings, "MULTIMODAL_THINKING_ENABLED", True)),
        )
    return ("glm5", "glm-5", True)
