"""Read-only bounded Yuanbao API diagnostics using existing service credentials."""

import argparse
import asyncio
import json
import logging
import math
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit
from types import SimpleNamespace


ROOT = Path("/srv/ageo-deploy")
LEGACY_HOST = "api.hunyuan.cloud.tencent.com"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")
ERROR_KEYS = {"code", "type", "source", "upstream_status", "status", "status_code"}
HY3_BASE = "https://tokenhub.tencentmaas.com/v1"
HY3_ENDPOINT = HY3_BASE + "/chat/completions"


def retirement_indicator(response):
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        message = str(error.get("message") or "") + str(error.get("message_zh") or "")
        return any(term in message.lower() for term in ("retired", "deprecated", "offline", "\u4e0b\u7ebf"))
    except (ValueError, TypeError, AttributeError):
        return False


def emit(section, **values):
    print(json.dumps({"section": section, **values}, ensure_ascii=True), flush=True)


def service_config(expected):
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("invalid_expected_release")
    release = (ROOT / "current").resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output(
        ["systemctl", "show", "ageo-backend.service", "--property=MainPID", "--value"],
        text=True, timeout=15,
    ).strip()
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError("backend_not_running")
    backend = release / "aeo-platform/backend"
    if Path(f"/proc/{pid}/cwd").resolve() != backend.resolve():
        raise ValueError("service_release_mismatch")
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    process_env = {key.decode(): value.decode() for item in entries if b"=" in item
                   for key, value in [item.split(b"=", 1)]}
    os.environ.clear()
    os.environ.update(process_env)
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    emit("release", sha=expected, process_matches_release=True)


def safe_identifier(value, secret):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    if (not IDENTIFIER.fullmatch(text) or text.lower().startswith(("sk-", "bearer"))
            or (secret and (secret in text or text in secret))):
        return None
    return text


def endpoint_summary(endpoint, secret):
    parsed = urlsplit(endpoint)
    path = parsed.path or "/"
    if not re.fullmatch(r"/[A-Za-z0-9_./-]{0,159}", path) or (secret and secret in path):
        path = None
    return {"host": safe_identifier(parsed.hostname or "", secret), "path": path}


def structured_error(response, secret):
    """Do not emit messages, arbitrary fields, response bodies, or request headers."""
    try:
        body = response.json()
    except (ValueError, TypeError):
        return []
    found = []
    pending = [("root", body, 0)]
    while pending:
        location, node, depth = pending.pop()
        if not isinstance(node, dict):
            continue
        fields = {}
        for key, value in node.items():
            if not isinstance(key, str):
                continue
            normalized = key.lower()
            if normalized in ERROR_KEYS:
                safe = safe_identifier(value, secret)
                if safe is not None:
                    fields[normalized] = safe
            if depth < 2 and normalized in {"error", "response", "upstream", "details"}:
                pending.append((location + "." + normalized, value, depth + 1))
        if fields:
            found.append({"location": location, **fields})
    return found


def require_check(name, passed):
    emit("hy3_check", check=name, passed=bool(passed))
    if not passed:
        raise ValueError("hy3_acceptance_failed")


async def check_existing_control_record():
    """Production reads only: record_usage commits internally, so never call it."""
    from sqlalchemy import select, text
    from app.core.database import AsyncSessionLocal, engine
    from app.models.llm_usage import LLMUsageRecord
    from app.services.usage_billing_summary import billing_details

    require_check("database_postgresql", engine.dialect.name == "postgresql")
    engine.echo = False
    async with AsyncSessionLocal() as db:
        try:
            await db.execute(text("SET TRANSACTION READ ONLY"))
            await db.execute(text("SET LOCAL statement_timeout = '10000ms'"))
            record = (await db.execute(select(LLMUsageRecord).order_by(
                LLMUsageRecord.created_at.desc()).limit(1))).scalar_one_or_none()
            require_check("existing_control_record", record is not None)
            details = billing_details(record)
            require_check("existing_control_dto", isinstance(details, dict)
                          and "pricing_status" in details and "cache_status" in details)
        finally:
            await db.rollback()
    emit("hy3_database", read_only=True, database_writes=False, persistence_verified=False)


async def capture_a4_recording(result):
    """Exercise A4's recorder contract without letting it schedule a DB write."""
    from app.workflow import nodes_a4

    captured = []

    async def capture(**kwargs):
        captured.append(kwargs)

    original = nodes_a4.record_provider_usage_async
    try:
        nodes_a4.record_provider_usage_async = capture
        await nodes_a4._record_a4_api_usage(
            session_id=None, task_id=None, question_id="hy3-acceptance-read-only",
            platform="hunyuan", result=result,
        )
    finally:
        nodes_a4.record_provider_usage_async = original
    require_check("a4_recorder_called_once", len(captured) == 1)
    call = captured[0]
    metadata = call.get("extra_metadata") or {}
    require_check("a4_recorder_identity", call.get("provider") == "hunyuan"
                  and call.get("model_name") == "hy3" and call.get("step") == "A4"
                  and call.get("session_id") is None and call.get("task_id") is None
                  and metadata.get("requested_method") == "api"
                  and metadata.get("actual_provider") == "hunyuan"
                  and metadata.get("provider_endpoint") == HY3_ENDPOINT
                  and metadata.get("protocol") == "hunyuan_chat_search"
                  and metadata.get("search_source") == "lite")
    require_check("a4_recorder_usage", call["usage"].raw == result["provider_usage"])
    return call["usage"]


def check_live_billing(result, usage):
    from app.models.llm_usage import LLMUsageRecord
    from app.services.llm_usage_service import estimate_usage_costs, hy3_search_pricing_snapshot
    from app.services.usage_billing_summary import billing_details

    route = {name: result[name] for name in ("provider_endpoint", "protocol", "search_source")}
    costs = estimate_usage_costs(
        "hunyuan", "hy3", usage.prompt_tokens, usage.completion_tokens,
        usage.cached_prompt_tokens, usage.cache_miss_prompt_tokens, provider_metadata=route,
    )
    require_check("token_cache_priced", costs.pricing_status == "priced"
                  and costs.cache_status == "known" and costs.currency == "CNY")
    hit, miss = costs.cached_prompt_tokens, costs.billable_prompt_tokens
    expected = (hit * .25 + miss + costs.completion_tokens * 4) / 1_000_000
    require_check("token_price_formula", math.isclose(
        costs.estimated_cost_cache_aware, expected, rel_tol=1e-9, abs_tol=1e-12))
    search = hy3_search_pricing_snapshot("hunyuan", "hy3", route, usage.raw)
    calls = usage.raw["tool_usage"]["web_search_call"]
    require_check("search_price_formula", search["status"] == "estimated"
                  and math.isclose(search["estimated_cost"], calls * .007, rel_tol=1e-9))
    # This object is never added to a session: DTO verification is explicitly in-memory.
    record = LLMUsageRecord(
        provider="hunyuan", model_name="hy3", prompt_tokens=costs.prompt_tokens,
        cached_prompt_tokens=hit, billable_prompt_tokens=miss, currency=costs.currency,
        estimated_cost=costs.estimated_cost,
        estimated_cost_cache_aware=costs.estimated_cost_cache_aware,
        extra_metadata={**route, "pricing_status": costs.pricing_status,
                        "billing_snapshot_version": 1, "provider_usage": usage.raw,
                        "normalized_usage": usage.to_dict(), "search_pricing": search,
                        "pricing": costs.pricing_snapshot.to_metadata()},
    )
    details = billing_details(record)
    require_check("live_control_dto", details["pricing_status"] == "priced"
                  and details["cache_status"] == "known"
                  and details["provider_web_search_requests"] == calls
                  and details["search_tool_cost_status"] == "estimated"
                  and details["estimated_search_tool_cost"] == search["estimated_cost"]
                  and details["estimated_cost_cache_aware"] == costs.estimated_cost_cache_aware)
    emit("hy3_billing", in_memory=True, prompt_tokens=costs.prompt_tokens,
         completion_tokens=costs.completion_tokens, cached_tokens=hit,
         cache_miss_tokens=miss, search_calls=calls,
         token_estimate_cny=costs.estimated_cost_cache_aware,
         search_estimate_cny=search["estimated_cost"])


async def accept_hy3(client):
    from app.workflow.nodes_a4 import (
        _fetch_from_hunyuan, _llm_usage_from_provider_payload, _retry_fetch,
    )

    observed_models = []

    async def observed_ask(question):
        import httpx

        try:
            response = await client.ask_with_search(question)
        except httpx.HTTPStatusError as error:
            emit("hy3_http_failure", http_status=error.response.status_code,
                 error_fields=structured_error(error.response, client.api_key))
            raise
        raw = response.raw_response
        raw = raw if isinstance(raw, dict) else {}
        observed_models.append(raw.get("model") == "hy3")
        choices = raw.get("choices")
        choices = choices if isinstance(choices, list) else []
        first = choices[0] if choices and isinstance(choices[0], dict) else {}
        message = first.get("message")
        message = message if isinstance(message, dict) else {}
        message_refs = message.get("search_results")
        search_info = raw.get("search_info")
        search_info = search_info if isinstance(search_info, dict) else {}
        top_refs = search_info.get("search_results")
        usage = raw.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        tools = usage.get("tool_usage")
        tools = tools if isinstance(tools, dict) else {}
        calls = tools.get("web_search_call")
        prompt_details = usage.get("prompt_tokens_details")
        prompt_details = prompt_details if isinstance(prompt_details, dict) else {}
        input_details = usage.get("input_tokens_details")
        input_details = input_details if isinstance(input_details, dict) else {}
        emit("hy3_response_shape", model_is_hy3=raw.get("model") == "hy3",
             choices_count=len(choices),
             message_search_results_count=len(message_refs) if isinstance(message_refs, list) else 0,
             top_search_results_count=len(top_refs) if isinstance(top_refs, list) else 0,
             search_call_valid=type(calls) is int and calls >= 0,
             web_search_call=calls if type(calls) is int and calls >= 0 else None,
             prompt_cached_tokens_present="cached_tokens" in prompt_details,
             input_cached_tokens_present="cached_tokens" in input_details,
             prompt_cache_hit_tokens_present="prompt_cache_hit_tokens" in usage,
             prompt_cache_miss_tokens_present="prompt_cache_miss_tokens" in usage,
             cached_prompt_tokens_present="cached_prompt_tokens" in usage,
             cache_miss_prompt_tokens_present="cache_miss_prompt_tokens" in usage,
             answer_contains_http=isinstance(response.answer_text, str)
             and "http" in response.answer_text.lower())
        return response

    observed_client = SimpleNamespace(
        model=client.model, endpoint=client.endpoint, search_source=client.search_source,
        ask_with_search=observed_ask,
    )
    result = await _retry_fetch(
        _fetch_from_hunyuan, observed_client,
        "Search the web for Tencent's official HY3 documentation. Explain its API "
        "and native web search support briefly, citing official Tencent source URLs.",
        platform="hunyuan", method="api",
    )
    require_check("a4_answer", result.get("success") is True
                  and bool((result.get("answer") or {}).get("content", "").strip()))
    citations = result.get("citations") or []
    require_check("a4_citations", bool(citations))
    require_check("actual_model_protocol", bool(observed_models) and all(observed_models)
                  and result.get("provider_model") == "hy3"
                  and result.get("protocol") == "hunyuan_chat_search"
                  and result.get("actual_provider") == "hunyuan"
                  and result.get("provider_endpoint") == HY3_ENDPOINT
                  and result.get("search_source") == "lite")
    raw = result.get("provider_usage") or {}
    calls = (raw.get("tool_usage") or {}).get("web_search_call")
    require_check("search_executed", type(calls) is int and calls > 0)
    usage = _llm_usage_from_provider_payload(raw)
    require_check("token_counters", all(type(value) is int and value > 0 for value in (
        usage.prompt_tokens, usage.completion_tokens, usage.total_tokens))
        and usage.total_tokens == usage.prompt_tokens + usage.completion_tokens)
    require_check("cache_counters", any(value is not None for value in (
        usage.cached_prompt_tokens, usage.cache_miss_prompt_tokens))
        and all(value is None or type(value) is int and 0 <= value <= usage.prompt_tokens
                for value in (usage.cached_prompt_tokens, usage.cache_miss_prompt_tokens)))
    recorded_usage = await capture_a4_recording(result)
    check_live_billing(result, recorded_usage)
    await check_existing_control_record()
    emit("hy3_acceptance", passed=True, citation_count=len(citations),
         api_responses=len(observed_models), database_writes=False, persistence_verified=False)


async def inspect():
    import httpx
    from dotenv import dotenv_values
    from app.core.config import settings
    from app.core.fetchers.api.hunyuan_client import HunyuanClient

    key = (settings.HUNYUAN_API_KEY or "").strip()
    shared = dotenv_values(ROOT / "shared/backend/.env.local")
    emit("existing_credential_slots", present={
        name: bool(os.environ.get(name) or shared.get(name))
        for name in ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY", "HUNYUAN_API_KEY")
    })
    del shared
    configured_url = (settings.HUNYUAN_BASE_URL or "").strip()
    configured_model = settings.HUNYUAN_FAST_MODEL or settings.HUNYUAN_MODEL
    if configured_model == "hy3" or urlsplit(configured_url).hostname == "tokenhub.tencentmaas.com":
        require_check("official_hy3_configuration", bool(key)
                      and configured_url in {HY3_BASE, HY3_ENDPOINT}
                      and settings.HUNYUAN_MODEL == "hy3"
                      and settings.HUNYUAN_FAST_MODEL == "hy3"
                      and settings.HUNYUAN_SEARCH_SOURCE == "lite")
        client = HunyuanClient(model=settings.HUNYUAN_FAST_MODEL)
        require_check("effective_hy3_configuration", client.endpoint == HY3_ENDPOINT
                      and client.model == "hy3" and client.search_source == "lite")
        await asyncio.wait_for(accept_hy3(client), timeout=150)
        return
    configured = endpoint_summary(configured_url, key)
    configured["model"] = safe_identifier(configured_model, key)
    client = HunyuanClient(model=settings.HUNYUAN_FAST_MODEL or None) if key else None
    effective = endpoint_summary(client.endpoint, key) if client else None
    if effective is not None:
        effective["model"] = safe_identifier(client.model, key)
    emit("configuration", configured=configured, effective=effective,
         key_present=bool(key),
         legacy_configuration=HunyuanClient.has_legacy_configuration(
             configured_url, configured_model))
    if client is None:
        emit("current_client", skipped="key_missing")
        return
    try:
        result = await asyncio.wait_for(
            client.ask_with_search("What is Tencent? Answer briefly."), timeout=70,
        )
        emit("current_client", http_status=200, answer_present=bool(result.answer_text),
             references=len(result.search_references or []))
    except httpx.HTTPStatusError as error:
        emit("current_client", http_status=error.response.status_code,
             error_fields=structured_error(error.response, key))
    except Exception as error:
        emit("current_client", failure_type=type(error).__name__)

    parsed = urlsplit(configured_url)
    if parsed.hostname != LEGACY_HOST:
        emit("original_endpoint", skipped="configured_host_is_not_official_legacy")
        return
    if (parsed.scheme != "https" or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        emit("original_endpoint", skipped="unsupported_endpoint_shape")
        return
    endpoint = configured_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as http:
            response = await http.post(
                endpoint, headers={"Authorization": "Bearer " + key},
                json={"model": configured_model, "stream": False, "max_tokens": 32,
                      "messages": [{"role": "user", "content": "Reply OK."}]},
            )
        emit("original_endpoint", endpoint=endpoint_summary(endpoint, key),
             model=safe_identifier(configured_model, key),
             http_status=response.status_code,
             retirement_mentioned=retirement_indicator(response),
             error_fields=structured_error(response, key) if response.status_code >= 400 else [])
    except Exception as error:
        emit("original_endpoint", failure_type=type(error).__name__)

    # Test HY3 on the same verified original gateway without client URL/model rewriting.
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as http:
            response = await asyncio.wait_for(
                http.post(
                    endpoint, headers={"Authorization": "Bearer " + key},
                    json={"model": "hy3", "stream": False, "max_tokens": 32,
                          "messages": [{"role": "user", "content": "Reply OK."}]},
                ),
                timeout=25,
            )
        answer_present = False
        if response.status_code == 200:
            try:
                answer_present = bool(client._extract_answer(response.json()).strip())
            except (ValueError, TypeError):
                pass
        emit("original_endpoint_hy3", model="hy3", http_status=response.status_code,
             answer_present=answer_present,
             error_fields=structured_error(response, key) if response.status_code >= 400 else [])
    except Exception as error:
        emit("original_endpoint_hy3", model="hy3", answer_present=False,
             failure_type=type(error).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    service_config(args.expected_release)
    asyncio.run(inspect())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("failure", failure_type=type(error).__name__)
        raise SystemExit(1)
