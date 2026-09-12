"""Read immutable billing snapshots without repricing historical records."""

import math
from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.models.llm_usage import LLMUsageRecord


def cache_status_for_record(record: LLMUsageRecord) -> str:
    metadata = record.extra_metadata if isinstance(record.extra_metadata, dict) else {}
    raw = metadata.get("provider_usage") or {}
    if not isinstance(raw, dict):
        raw = {}
    # Older A4 Kimi aggregation silently replaced unrecognised cache counters
    # with zero. These persisted totals cannot prove a cache miss.
    if (getattr(record, "provider", None) == "moonshot"
            and metadata.get("usage_scope") == "a4_platform_fetch"
            and raw.get("cache_accounting_version") != 2):
        return "legacy_unknown"
    details = metadata.get("prompt_tokens_details") or raw.get("prompt_tokens_details") or raw.get("input_tokens_details") or {}
    if not isinstance(details, dict):
        details = {}
    normalized = metadata.get("normalized_usage") or {}
    if not isinstance(normalized, dict):
        normalized = {}
    hit_values = [raw.get("prompt_cache_hit_tokens"), raw.get("cached_tokens"), normalized.get("cached_prompt_tokens")]
    miss_values = [raw.get("prompt_cache_miss_tokens"), metadata.get("prompt_cache_miss_tokens"), normalized.get("cache_miss_prompt_tokens")]
    for candidate in (details, raw.get("prompt_tokens_details"), raw.get("input_tokens_details"), normalized.get("prompt_tokens_details")):
        if isinstance(candidate, dict):
            hit_values.append(candidate.get("cached_tokens"))
    hit_values = [value for value in hit_values if value is not None]
    miss_values = [value for value in miss_values if value is not None]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 0 for value in hit_values + miss_values):
        return "invalid"
    if len(set(hit_values)) > 1 or len(set(miss_values)) > 1:
        return "invalid"
    hit = hit_values[0] if hit_values else None
    miss = miss_values[0] if miss_values else None
    if hit is None and miss is None:
        return "unknown" if metadata.get("billing_snapshot_version") else "legacy_unknown"
    if any(value is not None and (not isinstance(value, int) or isinstance(value, bool) or value < 0) for value in (hit, miss)):
        return "invalid"
    prompt = record.prompt_tokens
    hit = prompt - miss if hit is None else hit
    miss = prompt - hit if miss is None else miss
    return "known" if min(hit, miss) >= 0 and hit + miss == prompt and hit == record.cached_prompt_tokens and miss == getattr(record, "billable_prompt_tokens", miss) else "invalid"


def billing_details(record: LLMUsageRecord) -> dict[str, Any]:
    metadata = record.extra_metadata if isinstance(record.extra_metadata, dict) else {}
    native_usage = metadata.get("native_provider_usage") or {}
    native_usage = native_usage if isinstance(native_usage, dict) else {}
    server_use = native_usage.get("server_tool_use") or {}
    requests = server_use.get("web_search_requests") if isinstance(server_use, dict) else None
    is_hy3 = getattr(record, "provider", None) == "hunyuan" and getattr(record, "model_name", None) == "hy3"
    is_kimi_search = (getattr(record, "provider", None) == "moonshot"
                      and (metadata.get("protocol") == "moonshot_chat_search"
                           or metadata.get("usage_scope") == "a4_platform_fetch"))
    if is_hy3 or is_kimi_search:
        provider_usage = metadata.get("provider_usage")
        tool_usage = provider_usage.get("tool_usage") if isinstance(provider_usage, dict) else None
        requests = tool_usage.get("web_search_call") if isinstance(tool_usage, dict) else None
    requests = requests if type(requests) is int and requests >= 0 else None
    search_status = "not_estimated" if metadata.get("protocol") == "anthropic_native_search" else "not_reported"
    search_cost = None
    search_currency = None
    if is_hy3 or is_kimi_search:
        # Only read the saved estimate, never apply today's rates to old calls.
        snapshot = metadata.get("search_pricing")
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        search_status = snapshot.get("status") or "legacy_unknown"
        candidate = snapshot.get("estimated_cost")
        if (search_status == "estimated" and requests is not None
                and type(snapshot.get("provider_web_search_requests")) is int
                and snapshot["provider_web_search_requests"] == requests
                and snapshot.get("currency") == "CNY"
                and type(candidate) in (int, float) and math.isfinite(candidate) and candidate >= 0):
            search_cost = float(candidate)
            search_currency = snapshot["currency"]
        elif search_status == "estimated":
            search_status = "invalid_usage"
    pricing = metadata.get("pricing")
    status = metadata.get("pricing_status")
    if not status:
        status = "legacy_snapshot" if pricing or record.estimated_cost or record.estimated_cost_cache_aware else "legacy_unknown"
    if status == "legacy_snapshot" and not pricing and not record.estimated_cost_cache_aware:
        status = "unknown_cache" if record.estimated_cost else "legacy_unknown"
    cache_status = cache_status_for_record(record)
    if cache_status == "invalid":
        status = "invalid_usage"
    if status in {"priced", "legacy_snapshot"} and cache_status != "known" and pricing and (
        pricing.get("input_cache_hit_price_per_mtokens") != pricing.get("input_cache_miss_price_per_mtokens")
    ) and record.prompt_tokens > 0:
        status = "unknown_cache"
    priced = status in {"priced", "legacy_snapshot"}
    baseline_known = priced or status == "unknown_cache"
    baseline = float(record.estimated_cost or 0.0) if baseline_known else None
    actual = float(record.estimated_cost_cache_aware or 0.0) if priced else None
    return {
        "pricing_status": status,
        "cache_status": cache_status,
        "pricing": pricing,
        "usage_time_basis": metadata.get("usage_time_basis", "legacy_unknown"),
        "cost_is_estimate": True,
        "cost_scope": metadata.get("cost_scope") or "token_estimate",
        "provider_web_search_requests": requests,
        "search_tool_cost_status": search_status,
        "estimated_search_tool_cost": search_cost,
        "search_tool_currency": search_currency,
        "currency": record.currency,
        "estimated_cost": baseline,
        "estimated_cost_cache_aware": actual,
        "estimated_savings": max(baseline - actual, 0.0) if priced and cache_status == "known" else None,
        "cache_hit_ratio": (
            record.cached_prompt_tokens / record.prompt_tokens
            if cache_status == "known" and record.prompt_tokens > 0 else None
        ),
    }


def summarize_billing(records: Iterable[LLMUsageRecord]) -> dict[str, Any]:
    records = list(records)
    priced_count = cache_count = known_prompt = known_hit = 0
    costs: dict[str, dict[str, Any]] = {}
    for record in records:
        details = billing_details(record)
        if details["cache_status"] == "known":
            cache_count += 1
            known_prompt += record.prompt_tokens
            known_hit += record.cached_prompt_tokens
        if details["estimated_cost"] is None:
            continue
        priced_count += 1
        currency = record.currency
        bucket = costs.setdefault(currency, {
            "currency": currency, "total_cost": 0.0,
            "total_cost_cache_aware": 0.0, "estimated_savings": 0.0,
            "priced_call_count": 0,
        })
        bucket["priced_call_count"] += 1
        bucket["total_cost"] += details["estimated_cost"]
        for field, detail in (("total_cost_cache_aware", "estimated_cost_cache_aware"), ("estimated_savings", "estimated_savings")):
            if bucket[field] is None or details[detail] is None:
                bucket[field] = None
            else:
                bucket[field] += details[detail]
    currency_rows = sorted(costs.values(), key=lambda row: row["currency"])
    for row in currency_rows:
        for field in ("total_cost", "total_cost_cache_aware", "estimated_savings"):
            if row[field] is not None:
                row[field] = round(row[field], 8)
    single = currency_rows[0] if len(currency_rows) == 1 else {}
    call_count = len(records)
    return {
        "priced_call_count": priced_count,
        "unknown_pricing_call_count": call_count - priced_count,
        "pricing_coverage": priced_count / call_count if call_count else 0.0,
        "cache_known_call_count": cache_count,
        "cache_unknown_call_count": call_count - cache_count,
        "cache_coverage": cache_count / call_count if call_count else 0.0,
        "cache_known_prompt_tokens": known_prompt,
        "cache_hit_ratio": known_hit / known_prompt if known_prompt else None,
        "currency": single.get("currency"),
        "total_cost": single.get("total_cost"),
        "total_cost_cache_aware": single.get("total_cost_cache_aware"),
        "estimated_savings": single.get("estimated_savings"),
        "costs_by_currency": currency_rows,
    }


def summarize_usage(records: list[LLMUsageRecord]) -> dict[str, Any]:
    fields = ("total_tokens", "prompt_tokens", "completion_tokens", "cached_prompt_tokens", "billable_prompt_tokens")
    latency = sum(record.latency_ms or 0 for record in records)
    return {
        **{field: sum(getattr(record, field) or 0 for record in records) for field in fields},
        "call_count": len(records),
        "total_latency_ms": latency,
        "avg_latency_ms": round(latency / len(records), 2) if records else 0.0,
        **summarize_billing(records),
    }


def grouped_usage(rows: list, indices: tuple[int, ...], names: tuple[str, ...]) -> list[dict]:
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[index] for index in indices)].append(row[0])
    return [
        {**dict(zip(names, key)), **summarize_usage(records)}
        for key, records in groups.items()
    ]
