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

    async def ask_with_search(self, question: str) -> LLMResponse:
        start_time = time.time()

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

                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=PlatformConstants.PLATFORM_API_TIMEOUTS["kimi"],
                )
                response.raise_for_status()
                data = response.json()

                choice = data.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason", "")
                assistant_msg = choice.get("message", {})

                if finish_reason == "tool_calls":
                    messages.append(assistant_msg)

                    tool_calls = assistant_msg.get("tool_calls", [])
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

                return LLMResponse(
                    answer_text=answer_text,
                    search_references=search_refs,
                    raw_response=data,
                    duration=duration,
                )

        # Exhausted tool rounds
        duration = time.time() - start_time
        logger.warning("[KimiClient] Exhausted %d tool rounds", MAX_TOOL_ROUNDS)
        return LLMResponse(
            answer_text="",
            search_references=[],
            raw_response={},
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
