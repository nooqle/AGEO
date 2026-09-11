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
    """Model for A1 synthesis after native search evidence is retrieved."""

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
    """Canonical text reasoning model profile, currently DeepSeek V4.1 Flash."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="TEXT_REASONING_LLM_PROVIDER",
        model_attr="TEXT_REASONING_MODEL_NAME",
        thinking_attr="TEXT_REASONING_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-flash",
        default_thinking=True,
        fallback_profile=None,
    )


def get_text_light_llm_model(*, task_name: str = "text_light") -> BaseLLMModel:
    """Canonical light text model profile, currently DeepSeek V4.1 Flash."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="TEXT_LIGHT_LLM_PROVIDER",
        model_attr="TEXT_LIGHT_MODEL_NAME",
        thinking_attr="TEXT_LIGHT_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-flash",
        default_thinking=False,
        fallback_profile=None,
    )


def get_multimodal_llm_model(*, task_name: str = "multimodal") -> BaseLLMModel:
    """Canonical multimodal model profile, currently DeepSeek V4.1 Flash."""

    return _get_profile_model(
        task_name=task_name,
        provider_attr="MULTIMODAL_LLM_PROVIDER",
        model_attr="MULTIMODAL_MODEL_NAME",
        thinking_attr="MULTIMODAL_THINKING_ENABLED",
        default_provider="deepseek",
        default_model="deepseek-flash",
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
    return get_llm_model(
        provider=provider,
        model_name=model_name,
        thinking_enabled=thinking_enabled,
    )


def _settings_str(settings: Any, attr: str, default: str) -> str:
    return str(getattr(settings, attr, default) or default).strip()
