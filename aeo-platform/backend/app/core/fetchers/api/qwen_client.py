"""Qwen (qianwen AI platform) DashScope multimodal-generation API client.

Uses the user-linked qianwen AI platform (not the old aliyun DashScope host)
with the official DashScope multimodal-generation HTTP SSE protocol.

Official constraints encoded here:
- multimodal models such as qwen3.8-max must be called via the
  multimodal-generation endpoint, not text-generation
- multimodal web search requires streaming (`stream=true`)
- only DashScope returns `search_info.search_results` plus inline citation
  marks (`[ref_1]` when requested), so cited references can be separated from
  retrieved-only sources
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = (
    "https://maas.qianwenaiapi.com/api/v1/services/aigc/"
    "multimodal-generation/generation"
)
DEFAULT_MODEL = "qwen3.8-max"

# Bounded SSE body so a runaway stream cannot exhaust memory.
MAX_SSE_BODY_BYTES = 2_000_000

PROTOCOL = "qianwen_dashscope_multimodal_search"
# search_references hold answer-cited URLs only; retrieved candidates stay in
# raw metadata. Never treat every search hit as a citation.
REFERENCE_SCOPE = "cited_references"

# Request the unambiguous provider citation format below.
_CITATION_REF_RE = re.compile(r"\[ref_(\d+)\]")


def _token_count(value: Any) -> int | None:
    """Return a non-negative int counter, or None when absent/invalid."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        count = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if count < 0 or count != float(value):
        return None
    return count


def _extract_cited_indexes(answer_text: str) -> set[int]:
    """Collect provider citation marks, never ordinary numbered list markers."""
    indexes: set[int] = set()
    for match in _CITATION_REF_RE.finditer(answer_text or ""):
        value = int(match.group(1))
        if value > 0:
            indexes.add(value)
    return indexes


def _iter_sse_events(body: str):
    """Yield (event_type, payload) from an SSE body.

    payload is a parsed JSON object, {"__done__": True} for `data: [DONE]`,
    or {"__malformed__": snippet} for undecodable data lines.
    """
    current_event = ""
    for raw_line in (body or "").splitlines():
        line = raw_line.strip()
        if not line:
            current_event = ""
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("id:"):
            continue
        if line.startswith(":"):
            continue
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload:
            continue
        if payload == "[DONE]":
            yield current_event, {"__done__": True}
            continue
        try:
            parsed = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            yield current_event, {"__malformed__": payload[:200]}
            continue
        if isinstance(parsed, dict):
            yield current_event, parsed
        else:
            yield current_event, {"__malformed__": payload[:200]}


def _extract_chunk_text(chunk: dict[str, Any]) -> str | None:
    """Extract answer text from one multimodal-generation chunk, if present."""
    output = chunk.get("output")
    if not isinstance(output, dict):
        return None
    if isinstance(output.get("text"), str):
        return output["text"]
    choices = output.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    choice = choices[0] if isinstance(choices[0], dict) else {}
    message = choice.get("message")
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                parts.append(part["text"])
        return "".join(parts) if parts else None
    return None


def _extract_finish_reason(chunk: dict[str, Any]) -> str | None:
    output = chunk.get("output")
    if not isinstance(output, dict):
        return None
    if isinstance(output.get("finish_reason"), str):
        return output["finish_reason"]
    choices = output.get("choices")
    if isinstance(choices, list) and choices:
        choice = choices[0] if isinstance(choices[0], dict) else {}
        reason = choice.get("finish_reason")
        if isinstance(reason, str):
            return reason
    return None


def _extract_search_info(chunk: dict[str, Any]) -> dict[str, Any] | None:
    output = chunk.get("output")
    if isinstance(output, dict) and isinstance(output.get("search_info"), dict):
        return output["search_info"]
    if isinstance(chunk.get("search_info"), dict):
        return chunk["search_info"]
    return None


def _extract_request_id(chunk: dict[str, Any]) -> str | None:
    request_id = chunk.get("request_id")
    return request_id if isinstance(request_id, str) and request_id else None


def _retrieved_sources_from_search_info(
    search_info: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Normalize search_info.search_results into bounded retrieved-source rows."""
    if not isinstance(search_info, dict):
        return []
    results = search_info.get("search_results")
    if not isinstance(results, list):
        return []
    sources: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    for position, item in enumerate(results, 1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        index = _token_count(item.get("index"))
        sources.append(
            {
                "index": index if index is not None else position,
                "title": str(item.get("title") or "") or url,
                "url": url,
                "snippet": item.get("summary") or item.get("snippet") or item.get("text"),
                "site_name": item.get("site_name") or item.get("sitename") or item.get("site"),
            }
        )
    return sources


def _provider_tool_count(usage: dict[str, Any]) -> int | None:
    """Read an explicit provider tool/search counter; never invent one."""
    candidates = [
        usage.get("web_search_call"),
        usage.get("web_search_calls"),
        usage.get("web_search_requests"),
        usage.get("web_search_count"),
    ]
    x_tools = usage.get("x_tools")
    if isinstance(x_tools, dict):
        web_search = x_tools.get("web_search")
        if isinstance(web_search, dict):
            candidates.append(web_search.get("count"))
        candidates.append(x_tools.get("web_search"))
    plugins = usage.get("plugins")
    if isinstance(plugins, dict):
        search = plugins.get("search")
        if isinstance(search, dict):
            candidates.append(search.get("count"))
    tool_usage = usage.get("tool_usage")
    if isinstance(tool_usage, dict):
        candidates.append(tool_usage.get("web_search_call"))
    server_tool_use = usage.get("server_tool_use")
    if isinstance(server_tool_use, dict):
        candidates.append(server_tool_use.get("web_search_requests"))

    values = {_token_count(value) for value in candidates if value is not None}
    values.discard(None)
    if len(values) != 1:
        return None
    return next(iter(values))


def _usage_snapshot(raw: Any) -> dict[str, Any] | None:
    """Keep provider counters as returned; missing counters stay unknown (None)."""
    if not isinstance(raw, dict):
        return None
    snapshot: dict[str, Any] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "prompt_tokens",
        "completion_tokens",
        "image_tokens",
        "video_tokens",
        "audio_tokens",
    ):
        if key in raw:
            snapshot[key] = _token_count(raw[key])

    prompt_details = raw.get("prompt_tokens_details")
    if isinstance(prompt_details, dict) and (
        "cached_tokens" in prompt_details
        or "cache_creation_input_tokens" in prompt_details
    ):
        snapshot["prompt_tokens_details"] = {
            key: _token_count(prompt_details[key])
            for key in ("cached_tokens", "cache_creation_input_tokens")
            if key in prompt_details
        }
    input_details = raw.get("input_tokens_details")
    if isinstance(input_details, dict) and input_details:
        snapshot["input_tokens_details"] = {
            key: _token_count(input_details[key])
            for key in ("text_tokens", "image_tokens", "video_tokens", "audio_tokens", "cached_tokens")
            if key in input_details
        }
    output_details = raw.get("output_tokens_details")
    if isinstance(output_details, dict) and output_details:
        snapshot["output_tokens_details"] = {
            key: _token_count(output_details[key])
            for key in ("text_tokens", "reasoning_tokens")
            if key in output_details
        }

    tool_count = _provider_tool_count(raw)
    if tool_count is not None:
        snapshot["tool_usage"] = {"web_search_call": tool_count}
    return snapshot


def _aggregate_usage(raw_usage: dict[str, Any] | None) -> dict[str, Any]:
    """Canonical usage ledger: real counters when returned, unknown when absent.

    Never invent zero search/tool fees. A missing counter is unknown (None),
    not free and not zero.
    """
    source = raw_usage if isinstance(raw_usage, dict) else {}
    snapshot = _usage_snapshot(source) or {}

    prompt = _token_count(source.get("prompt_tokens"))
    if prompt is None:
        prompt = _token_count(source.get("input_tokens"))
    completion = _token_count(source.get("completion_tokens"))
    if completion is None:
        completion = _token_count(source.get("output_tokens"))
    total = _token_count(source.get("total_tokens"))

    prompt_details = source.get("prompt_tokens_details")
    cache_creation = None
    if isinstance(prompt_details, dict):
        cache_creation = _token_count(prompt_details.get("cache_creation_input_tokens"))
    input_details = source.get("input_tokens_details")
    hit_fields = (
        (prompt_details, "cached_tokens"),
        (input_details, "cached_tokens"),
        (source, "prompt_cache_hit_tokens"),
        (source, "cached_tokens"),
    )
    hit_values = {
        _token_count(mapping[key])
        for mapping, key in hit_fields
        if isinstance(mapping, dict) and key in mapping
    }
    hit_invalid = None in hit_values or len(hit_values) > 1
    cached = next(iter(hit_values)) if len(hit_values) == 1 and not hit_invalid else None
    miss_values = {
        _token_count(source[key])
        for key in ("prompt_cache_miss_tokens", "cache_miss_prompt_tokens")
        if key in source
    }
    miss_invalid = None in miss_values or len(miss_values) > 1
    cache_miss = next(iter(miss_values)) if len(miss_values) == 1 and not miss_invalid else None
    # A contradictory/invalid hit cannot be repaired from a reported miss (or
    # vice versa); the generic billing layer otherwise infers and prices it.
    if hit_invalid or miss_invalid or (
        prompt is not None and cached is not None and cache_miss is not None
        and cached + cache_miss != prompt
    ):
        cached = cache_miss = None

    tool_count = _provider_tool_count(source)
    aggregate: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "prompt_cache_hit_tokens": cached,
        "prompt_cache_miss_tokens": cache_miss,
        "cache_creation_input_tokens": cache_creation,
        "tool_usage": {"web_search_call": tool_count},
        # Search tool pricing is separate from model tokens. Without a provider
        # counter we must not claim zero search usage or zero search fee.
        "search_tool_cost_status": "reported" if tool_count is not None else "unknown",
        "native_usage": snapshot,
    }
    return aggregate


def parse_dashscope_sse(body: str) -> dict[str, Any]:
    """Parse a DashScope multimodal-generation SSE body into structured evidence.

    With `incremental_output=true` each text chunk carries only a new fragment.
    """
    answer_parts: list[str] = []
    finish_reason: str | None = None
    search_info: dict[str, Any] | None = None
    usage: dict[str, Any] | None = None
    request_id: str | None = None
    event_count = 0
    malformed_count = 0
    saw_done = False
    error_events: list[str] = []

    for event_type, payload in _iter_sse_events(body or ""):
        event_count += 1
        if payload.get("__done__"):
            saw_done = True
            continue
        if "__malformed__" in payload:
            malformed_count += 1
            continue

        is_error_event = event_type.upper() in {"ERROR", "STREAM_ERROR"}
        code = payload.get("code")
        has_code = code not in (None, "")
        if is_error_event or (has_code and payload.get("message") and not payload.get("output")):
            error_events.append(
                f"{str(code or event_type or 'error')}: {str(payload.get('message') or '')[:200]}"
            )
            continue

        chunk_request_id = _extract_request_id(payload)
        if chunk_request_id:
            request_id = chunk_request_id

        chunk_text = _extract_chunk_text(payload)
        # The provider requires incremental output for this model. Empty
        # terminal chunks must not wipe previously received fragments.
        if chunk_text:
            answer_parts.append(chunk_text)

        chunk_finish = _extract_finish_reason(payload)
        if chunk_finish is not None:
            finish_reason = chunk_finish

        chunk_search = _extract_search_info(payload)
        # A later cumulative text chunk may carry an empty search_info. Keep
        # the last positive source list instead of losing earlier evidence.
        if chunk_search is not None and (
            search_info is None or chunk_search.get("search_results")
        ):
            search_info = chunk_search

        chunk_usage = payload.get("usage")
        if isinstance(chunk_usage, dict) and chunk_usage:
            # A terminal SSE event may omit counters or include an empty
            # object; neither should erase earlier provider usage.
            usage = chunk_usage

    return {
        "answer_text": "".join(answer_parts),
        "finish_reason": finish_reason,
        "search_info": search_info,
        "usage": usage,
        "request_id": request_id,
        "event_count": event_count,
        "malformed_count": malformed_count,
        "saw_done": saw_done,
        "error_events": error_events,
    }


def _create_http_client() -> httpx.AsyncClient:
    """HTTP client factory; tests replace this to inject mocked SSE streams."""
    return httpx.AsyncClient()


class QwenClient(BaseAPIClient):
    """Qwen DashScope multimodal-generation client with cited web search."""

    DEFAULT_ENDPOINT = DEFAULT_ENDPOINT
    DEFAULT_MODEL = DEFAULT_MODEL

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
    ):
        api_key = api_key or getattr(settings, "QWEN_API_KEY", None)
        endpoint = endpoint or getattr(settings, "QWEN_ENDPOINT", None) or DEFAULT_ENDPOINT
        model = model or getattr(settings, "QWEN_MODEL", DEFAULT_MODEL)

        if not api_key:
            raise ValueError(
                "Qwen API key is required. "
                "Set QWEN_API_KEY or pass api_key parameter."
            )

        super().__init__(api_key, endpoint)
        self.model = model or DEFAULT_MODEL

    @staticmethod
    def _request_timeout() -> float:
        try:
            configured = float(getattr(settings, "A4_QWEN_API_TIMEOUT_SECONDS", 90.0))
        except (TypeError, ValueError):
            configured = 90.0
        return max(5.0, configured)

    def _build_payload(self, question: str) -> dict[str, Any]:
        """Build the official multimodal-generation request with web search on."""
        search_options = {
            "search_strategy": "turbo",
            "forced_search": True,
            "enable_source": True,
            "enable_citation": True,
            "citation_format": "[ref_<number>]",
        }
        return {
            "model": self.model,
            "input": {
                "messages": [
                    {
                        "role": "system",
                        "content": self._build_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": [{"text": question}],
                    },
                ]
            },
            "parameters": {
                "result_format": "message",
                "stream": True,
                "incremental_output": True,
                "enable_thinking": False,
                "enable_search": True,
                "search_options": search_options,
            },
        }

    def _request_metadata(self, question: str) -> dict[str, Any]:
        payload = self._build_payload(question)
        return {
            "static_prompt_hash": fingerprint_text(self._build_system_prompt()),
            "tool_surface_hash": fingerprint_tools(
                [{"search_options": payload["parameters"]["search_options"]}]
            ),
            "runtime_context_size": len(question or ""),
            "runtime_context_unit": "characters",
            "runtime_context_scope": "max_serialized_non_system_messages",
            "request_round_count": 1,
            "search_strategy": payload["parameters"]["search_options"]["search_strategy"],
        }

    @staticmethod
    def _redact(text: str, api_key: str | None) -> str:
        value = str(text or "")
        if api_key:
            value = value.replace(api_key, "[REDACTED]")
        return value

    async def _read_sse_body(self, response: httpx.Response) -> tuple[bytes, bool]:
        """Read at most MAX_SSE_BODY_BYTES of the stream body."""
        chunks: list[bytes] = []
        total = 0
        truncated = False
        async for chunk in response.aiter_bytes():
            if not chunk:
                continue
            remaining = MAX_SSE_BODY_BYTES - total
            if remaining <= 0:
                truncated = True
                break
            if len(chunk) > remaining:
                chunks.append(chunk[:remaining])
                total += remaining
                truncated = True
                break
            chunks.append(chunk)
            total += len(chunk)
        return b"".join(chunks), truncated

    def _build_references(
        self,
        retrieved_sources: list[dict[str, Any]],
        cited_indexes: set[int],
    ) -> list[SearchReference]:
        """Map cited indexes only; never emit uncited retrieved URLs as citations."""
        by_index: dict[int, dict[str, Any]] = {}
        for source in retrieved_sources:
            index = source.get("index")
            if isinstance(index, int) and index > 0 and index not in by_index:
                by_index[index] = source

        references: list[SearchReference] = []
        for index in sorted(cited_indexes):
            source = by_index.get(index)
            if not source:
                continue
            url = str(source.get("url") or "").strip()
            if not url:
                continue
            references.append(
                SearchReference(
                    index=index,
                    title=str(source.get("title") or url),
                    url=url,
                    snippet=source.get("snippet"),
                    site_name=source.get("site_name"),
                    is_official=False,
                )
            )
        return references

    def _build_raw_response(
        self,
        *,
        parsed: dict[str, Any],
        retrieved_sources: list[dict[str, Any]],
        cited_indexes: set[int],
        truncated: bool,
        request_metadata: dict[str, Any],
        body_bytes: int,
    ) -> dict[str, Any]:
        usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else None
        observed_answer = str(parsed.get("answer_text") or "")
        finish_reason = parsed.get("finish_reason")
        has_search_evidence = bool(retrieved_sources)
        finish_complete = (
            finish_reason == "stop"
            and not truncated
            and bool(observed_answer.strip())
            and not parsed.get("error_events")
        )

        raw: dict[str, Any] = {
            "protocol": PROTOCOL,
            "model": self.model,
            "request_id": parsed.get("request_id"),
            "finish_reason": finish_reason,
            "web_search_executed": has_search_evidence,
            "reference_scope": REFERENCE_SCOPE,
            "retrieved_sources": retrieved_sources,
            "cited_indexes": sorted(index for index in cited_indexes if index > 0),
            "usage": usage,
            "usage_aggregate": _aggregate_usage(usage),
            "request_metadata": request_metadata,
            "sse_body_bytes": body_bytes,
            "sse_body_truncated": truncated,
            "sse_saw_done": bool(parsed.get("saw_done")),
            "event_count": parsed.get("event_count"),
            "malformed_event_count": parsed.get("malformed_count"),
        }
        if parsed.get("search_info") is not None:
            raw["search_info"] = parsed["search_info"]
        if parsed.get("error_events"):
            raw["provider_error_events"] = parsed["error_events"]

        if not has_search_evidence:
            raw["search_error"] = (
                "No positive web-search execution/source evidence "
                "(search_info.search_results empty or absent)"
            )
            raw["observed_answer_text"] = observed_answer
        elif not finish_complete:
            raw["search_error"] = (
                "Incomplete finish: expected finish_reason=stop with a non-empty "
                f"answer (finish_reason={finish_reason!r}, truncated={truncated})"
            )
            raw["observed_answer_text"] = observed_answer
        return raw

    async def ask_with_search(self, question: str) -> LLMResponse:
        """Send a question and return only positively searched, complete answers."""
        start_time = time.monotonic()
        payload = self._build_payload(question)
        request_metadata = self._request_metadata(question)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-DashScope-SSE": "enable",
        }

        try:
            async with _create_http_client() as client:
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self._request_timeout(),
                ) as response:
                    try:
                        response.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        # Streaming responses are unread here. Accessing
                        # response.text first raises ResponseNotRead and hides
                        # the original 401/429 from A4 retry handling.
                        error_body, _ = await self._read_sse_body(response)
                        detail = self._redact(
                            error_body[:500].decode("utf-8", errors="replace"),
                            self.api_key,
                        )
                        logger.error(
                            "[QwenClient] HTTP %s from qianwen multimodal-generation: %s",
                            exc.response.status_code,
                            detail,
                        )
                        raise
                    body_bytes, truncated = await self._read_sse_body(response)
        except httpx.HTTPStatusError:
            raise
        except Exception as exc:
            duration = time.monotonic() - start_time
            logger.warning("[QwenClient] request failed: %s", type(exc).__name__)
            return LLMResponse(
                answer_text="",
                search_references=[],
                raw_response={
                    "protocol": PROTOCOL,
                    "model": self.model,
                    "web_search_executed": False,
                    "reference_scope": REFERENCE_SCOPE,
                    "usage_aggregate": _aggregate_usage(None),
                    "request_metadata": request_metadata,
                    "search_error": self._redact(
                        f"{type(exc).__name__}: {exc}", self.api_key
                    ),
                },
                duration=duration,
            )

        body = body_bytes.decode("utf-8", errors="replace")
        parsed = parse_dashscope_sse(body)
        retrieved_sources = _retrieved_sources_from_search_info(parsed.get("search_info"))
        observed_answer = str(parsed.get("answer_text") or "")
        cited_indexes = _extract_cited_indexes(observed_answer)
        raw = self._build_raw_response(
            parsed=parsed,
            retrieved_sources=retrieved_sources,
            cited_indexes=cited_indexes,
            truncated=truncated,
            request_metadata=request_metadata,
            body_bytes=len(body_bytes),
        )
        usage_summary = raw["usage_aggregate"]
        logger.info(
            "[QwenClient] usage_observed=%s prompt_tokens=%s completion_tokens=%s "
            "search_count=%s stream_truncated=%s",
            isinstance(parsed.get("usage"), dict),
            usage_summary.get("prompt_tokens"),
            usage_summary.get("completion_tokens"),
            usage_summary.get("tool_usage", {}).get("web_search_call"),
            truncated,
        )

        complete = "search_error" not in raw
        if complete:
            return LLMResponse(
                answer_text=observed_answer,
                search_references=self._build_references(
                    retrieved_sources, cited_indexes
                ),
                raw_response=raw,
                duration=time.monotonic() - start_time,
            )

        # Fail closed: no positive search evidence or incomplete finish must not
        # masquerade as a successful web-search answer. Keep diagnostics in raw.
        return LLMResponse(
            answer_text="",
            search_references=[],
            raw_response=raw,
            duration=time.monotonic() - start_time,
        )
