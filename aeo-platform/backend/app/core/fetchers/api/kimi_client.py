"""Kimi (Moonshot) API client."""

import asyncio
import json
import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.constants import LLMConstants, PlatformConstants
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools

logger = logging.getLogger(__name__)

# Maximum tool_calls rounds to prevent infinite loops
MAX_TOOL_ROUNDS = LLMConstants.MAX_TOOL_ROUNDS

# System prompt requesting JSON output with answer + citations
_SYSTEM_PROMPT = """\
你是一个专业的信息助手。请基于搜索结果回答问题。

请使用如下 JSON 格式输出你的回复：

{
  "answer": "你的完整回答内容",
  "citations": [
    {"index": 1, "title": "来源标题", "url": "来源URL", "snippet": "相关摘要"}
  ]
}

要求：
- answer 字段包含完整的回答文本
- citations 数组列出你引用的所有来源，每个来源包含 index（序号）、title（标题）、url（链接）、snippet（摘要）
- 如果没有引用来源，citations 为空数组 []
"""


def _token_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        count = int(value)
        return count if count >= 0 and count == float(value) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _usage_snapshot(raw: Any) -> dict[str, Any] | None:
    """Retain usage evidence only; never copy provider content into metadata."""
    if not isinstance(raw, dict):
        return None
    keys = (
        "prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens",
        "cached_prompt_tokens", "prompt_cache_hit_tokens",
        "cache_miss_prompt_tokens", "prompt_cache_miss_tokens",
    )
    snapshot = {key: _token_count(raw[key]) for key in keys if key in raw}
    details = raw.get("prompt_tokens_details")
    if isinstance(details, dict) and "cached_tokens" in details:
        snapshot["prompt_tokens_details"] = {
            "cached_tokens": _token_count(details["cached_tokens"]),
        }
    return snapshot


def _cache_counts(usage: dict[str, Any]) -> tuple[int | None, int | None]:
    """Infer a missing side only from valid, non-conflicting provider counters."""
    prompt = _token_count(usage.get("prompt_tokens"))
    if prompt is None:
        return None, None
    hits = [usage[key] for key in (
        "cached_tokens", "cached_prompt_tokens", "prompt_cache_hit_tokens",
    ) if key in usage]
    details = usage.get("prompt_tokens_details") or {}
    if "cached_tokens" in details:
        hits.append(details["cached_tokens"])
    misses = [usage[key] for key in (
        "cache_miss_prompt_tokens", "prompt_cache_miss_tokens",
    ) if key in usage]
    hit_values = {_token_count(value) for value in hits}
    miss_values = {_token_count(value) for value in misses}
    if None in hit_values or None in miss_values or len(hit_values) > 1 or len(miss_values) > 1:
        return None, None
    hit = next(iter(hit_values), None)
    miss = next(iter(miss_values), None)
    if hit is None and miss is None:
        return None, None
    if hit is None:
        hit = prompt - miss
    if miss is None:
        miss = prompt - hit
    if hit < 0 or miss < 0 or hit + miss != prompt:
        return None, None
    return hit, miss


def _aggregate_usage(rounds: list[dict[str, Any] | None], searches: int) -> dict[str, Any]:
    """A missing round or cache counter makes the corresponding total unknown."""
    totals: dict[str, Any] = dict.fromkeys(
        ("prompt_tokens", "completion_tokens", "total_tokens",
         "cached_prompt_tokens", "cache_miss_prompt_tokens"), 0,
    )
    for raw in rounds:
        usage = raw or {}
        cached, miss = _cache_counts(usage)
        values = {**usage, "cached_prompt_tokens": cached, "cache_miss_prompt_tokens": miss}
        for key, previous in totals.items():
            value = _token_count(values.get(key))
            totals[key] = previous + value if previous is not None and value is not None else None
    totals.update(
        prompt_tokens_details={"cached_tokens": totals["cached_prompt_tokens"]},
        tool_usage={"web_search_call": searches},
        cache_accounting_version=2,
        rounds=rounds,
    )
    return totals


class KimiClient(BaseAPIClient):
    """Moonshot Kimi API client.

    Uses the OpenAI-compatible chat completions API with built-in web search.
    Combines $web_search (builtin_function) with JSON Mode to get structured
    output including answer text and citations.

    Flow:
      1. Send messages + $web_search tool definition
      2. If finish_reason == "tool_calls", echo arguments back as tool result
      3. Second call with response_format=json_object returns structured answer
    """

    DEFAULT_ENDPOINT = settings.MOONSHOT_BASE_URL

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
    ):
        api_key = api_key or settings.MOONSHOT_API_KEY
        endpoint = endpoint or self.DEFAULT_ENDPOINT
        model = model or settings.MOONSHOT_MODEL

        if not api_key:
            raise ValueError(
                "Moonshot API key is required. "
                "Set MOONSHOT_API_KEY environment variable or pass api_key parameter."
            )

        super().__init__(api_key, endpoint)
        self.model = model

    @staticmethod
    def _request_timeout() -> float:
        try:
            configured = float(settings.A4_KIMI_API_TIMEOUT_SECONDS)
        except (TypeError, ValueError):
            configured = PlatformConstants.PLATFORM_API_TIMEOUTS["kimi"]
        return max(5.0, configured)

    async def ask_with_search(self, question: str) -> LLMResponse:
        start_time = time.time()
        usage_rounds: list[dict[str, Any] | None] = []
        search_calls = 0

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        tools = [
            {
                "type": "builtin_function",
                "function": {"name": "$web_search"},
            }
        ]
        request_metadata = {
            "static_prompt_hash": fingerprint_text(_SYSTEM_PROMPT),
            "tool_surface_hash": fingerprint_tools(tools),
            "runtime_context_size": 0,
            "runtime_context_unit": "characters",
            "runtime_context_scope": "max_serialized_non_system_messages",
            "request_round_count": 0,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            for _round in range(MAX_TOOL_ROUNDS):
                payload: dict[str, Any] = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "thinking": {"type": "disabled"},
                    "response_format": {"type": "json_object"},
                }
                runtime_chars = len(json.dumps(
                    messages[1:], ensure_ascii=False, separators=(",", ":"),
                ))
                request_metadata["runtime_context_size"] = max(
                    request_metadata["runtime_context_size"], runtime_chars,
                )
                request_metadata["request_round_count"] += 1

                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=self._request_timeout(),
                )
                response.raise_for_status()
                data = response.json()
                usage_rounds.append(_usage_snapshot(data.get("usage")))

                choice = data.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason", "")
                assistant_msg = choice.get("message", {})

                if finish_reason == "tool_calls":
                    messages.append(assistant_msg)

                    tool_calls = assistant_msg.get("tool_calls", [])
                    search_calls += sum(
                        tc.get("function", {}).get("name") == "$web_search"
                        for tc in tool_calls
                    )
                    for tc in tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "content": tc.get("function", {}).get("arguments", "{}"),
                        })
                    await asyncio.sleep(1.0)  # Ease pressure between consecutive tool_calls requests
                    continue

                # finish_reason == "stop" — parse JSON response
                raw_content = assistant_msg.get("content", "") or ""
                duration = time.time() - start_time

                answer_text, search_refs = self._parse_json_response(raw_content)
                raw_response = dict(data)
                raw_response.update(
                    usage_aggregate=_aggregate_usage(usage_rounds, search_calls),
                    request_metadata=request_metadata,
                )

                return LLMResponse(
                    answer_text=answer_text,
                    search_references=search_refs,
                    raw_response=raw_response,
                    duration=duration,
                )

        # Exhausted tool rounds
        duration = time.time() - start_time
        logger.warning("[KimiClient] Exhausted %d tool rounds", MAX_TOOL_ROUNDS)
        return LLMResponse(
            answer_text="",
            search_references=[],
            raw_response={
                "usage_aggregate": _aggregate_usage(usage_rounds, search_calls),
                "request_metadata": request_metadata,
            },
            duration=duration,
        )

    @staticmethod
    def _parse_json_response(content: str) -> tuple[str, list[SearchReference]]:
        """Parse JSON Mode response into answer text and search references."""
        try:
            obj = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            # Fallback: treat entire content as plain text answer
            return content, []

        answer_text = obj.get("answer", content)

        refs: list[SearchReference] = []
        for idx, cite in enumerate(obj.get("citations", []), 1):
            refs.append(SearchReference(
                index=cite.get("index", idx),
                title=cite.get("title", ""),
                url=cite.get("url", ""),
                snippet=cite.get("snippet"),
                site_name=cite.get("site_name"),
                is_official=False,
            ))

        return answer_text, refs
