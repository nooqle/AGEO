from __future__ import annotations

from types import SimpleNamespace

from app.core.llm.deepseek import DeepSeekConfig, DeepSeekModel
from app.services.control_plane_service import ControlPlaneService
from app.services import llm_usage_service


def _deepseek_pricing_settings(
    *,
    reporting_currency: str = "CNY",
    pricing_currency: str = "CNY",
) -> SimpleNamespace:
    return SimpleNamespace(
        GLM5_LONG_CONTEXT_THRESHOLD_TOKENS=32000,
        LLM_COST_REPORTING_CURRENCY=reporting_currency,
        DEEPSEEK_PRICE_CURRENCY=pricing_currency,
        DEEPSEEK_FLASH_MODEL_NAME="deepseek-v4-flash",
        DEEPSEEK_PRO_MODEL_NAME="deepseek-v4-pro",
        DEEPSEEK_FLASH_PRICE_INPUT_CACHE_HIT_PER_MTOKENS=0.02,
        DEEPSEEK_FLASH_PRICE_INPUT_CACHE_MISS_PER_MTOKENS=1.0,
        DEEPSEEK_FLASH_PRICE_OUTPUT_PER_MTOKENS=2.0,
        DEEPSEEK_PRO_PRICE_INPUT_CACHE_HIT_PER_MTOKENS=0.025,
        DEEPSEEK_PRO_PRICE_INPUT_CACHE_MISS_PER_MTOKENS=3.0,
        DEEPSEEK_PRO_PRICE_OUTPUT_PER_MTOKENS=6.0,
    )


def test_deepseek_usage_parser_reads_cache_hit_and_miss_tokens() -> None:
    model = DeepSeekModel(DeepSeekConfig(api_key="test-key"))

    usage = model._parse_usage(
        {
            "completion_tokens": 42,
            "total_tokens": 165,
            "prompt_cache_hit_tokens": 100,
            "prompt_cache_miss_tokens": 23,
        }
    )

    assert usage is not None
    assert usage.prompt_tokens == 123
    assert usage.completion_tokens == 42
    assert usage.cached_prompt_tokens == 100
    assert usage.cache_miss_prompt_tokens == 23


def test_deepseek_v4_pro_cost_uses_chinese_cache_hit_and_miss_prices(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        llm_usage_service,
        "get_settings",
        lambda: _deepseek_pricing_settings(),
    )

    cost = llm_usage_service.estimate_usage_costs(
        provider="deepseek",
        model_name="deepseek-v4-pro",
        prompt_tokens=1_000_000,
        completion_tokens=1_000_000,
        cached_prompt_tokens=200_000,
        cache_miss_prompt_tokens=800_000,
    )

    assert cost.currency == "CNY"
    assert cost.estimated_cost == 9.0
    assert cost.estimated_cost_cache_aware == 8.405
    assert cost.estimated_cost_savings == 0.595
    assert cost.billable_prompt_tokens == 800_000
    assert cost.pricing_snapshot is not None
    assert cost.pricing_snapshot.pricing_model == "deepseek-v4-pro"
    assert cost.pricing_snapshot.pricing_currency == "CNY"
    assert cost.pricing_snapshot.source_url == (
        "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    )


def test_deepseek_aliases_use_flash_pricing(monkeypatch) -> None:
    monkeypatch.setattr(
        llm_usage_service,
        "get_settings",
        lambda: _deepseek_pricing_settings(),
    )

    cost = llm_usage_service.estimate_usage_costs(
        provider="deepseek",
        model_name="deepseek-reasoner",
        prompt_tokens=1_000_000,
        completion_tokens=0,
    )

    assert cost.estimated_cost == 1.0
    assert cost.pricing_snapshot is not None
    assert cost.pricing_snapshot.pricing_model == "deepseek-v4-flash"


def test_deepseek_cost_is_unknown_when_price_currency_differs_from_report_currency(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        llm_usage_service,
        "get_settings",
        lambda: _deepseek_pricing_settings(
            reporting_currency="CNY",
            pricing_currency="USD",
        ),
    )

    cost = llm_usage_service.estimate_usage_costs(
        provider="deepseek",
        model_name="deepseek-v4-flash",
        prompt_tokens=1_000_000,
        completion_tokens=0,
        cached_prompt_tokens=500_000,
        cache_miss_prompt_tokens=500_000,
    )

    assert cost.currency == "CNY"
    assert cost.estimated_cost == 0.0
    assert cost.estimated_cost_cache_aware == 0.0
    assert cost.pricing_snapshot is None


def test_control_plane_reuse_diagnostics_flags_low_cache_and_hash_changes() -> None:
    records = [
        SimpleNamespace(
            prompt_tokens=1000,
            cached_prompt_tokens=100,
            provider="deepseek",
            model_name="deepseek-v4-pro",
            extra_metadata={
                "static_prompt_hash": "static-a",
                "tool_surface_hash": "tool-a",
                "model_identity": "deepseek:deepseek-v4-pro",
                "runtime_context_size": 8000,
            },
        ),
        SimpleNamespace(
            prompt_tokens=1000,
            cached_prompt_tokens=900,
            provider="deepseek",
            model_name="deepseek-v4-pro",
            extra_metadata={
                "static_prompt_hash": "static-b",
                "tool_surface_hash": "tool-b",
                "model_identity": "deepseek:deepseek-v4-pro",
                "runtime_context_size": 13000,
            },
        ),
    ]

    summary, diagnostics = ControlPlaneService._build_reuse_diagnostics(records)

    assert summary["diagnostic_sample_count"] == 2
    assert summary["low_cache_call_count"] == 1
    assert summary["static_prompt_variant_count"] == 2
    assert summary["tool_surface_variant_count"] == 2
    assert summary["max_runtime_context_size"] == 13000
    codes = {item["code"] for item in diagnostics}
    assert {
        "low_cache_hit_ratio",
        "static_prompt_hash_changed",
        "tool_surface_hash_changed",
        "runtime_context_oversized",
    } <= codes


def test_control_plane_reuse_diagnostics_empty_sample_has_no_stable_signal() -> None:
    summary, diagnostics = ControlPlaneService._build_reuse_diagnostics([])

    assert summary["diagnostic_sample_count"] == 0
    assert diagnostics == []


def test_recent_call_reuse_diagnosis_does_not_expose_prompt_content() -> None:
    record = SimpleNamespace(
        prompt_tokens=1000,
        cached_prompt_tokens=0,
        provider="deepseek",
        model_name="deepseek-v4-pro",
        extra_metadata={
            "static_prompt_hash": "hash-only",
            "tool_surface_hash": "tool-only",
            "runtime_context_size": 120,
        },
    )

    diagnosis = ControlPlaneService._reuse_diagnosis_for_record(record)

    assert diagnosis == "复用率低"
    assert "hash-only" not in diagnosis
