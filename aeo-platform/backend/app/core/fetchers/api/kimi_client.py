"""Kimi (Moonshot) API client."""

import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse

logger = logging.getLogger(__name__)

# Maximum tool_calls rounds to prevent infinite loops
MAX_TOOL_ROUNDS = 3


class KimiClient(BaseAPIClient):
    """Moonshot Kimi API client.

    Uses the OpenAI-compatible chat completions API with built-in web search.
    The $web_search tool is invoked via the standard tool_calls flow:
      1. Send messages + tools definition
      2. If finish_reason == "tool_calls", append assistant + tool result, call again
      3. If finish_reason == "stop", extract content as answer
    """

    DEFAULT_ENDPOINT = "https://api.moonshot.cn/v1/chat/completions"

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
            {"role": "system", "content": self._build_system_prompt()},
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
                }

                response = await client.post(
                    self.endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60.0,
                )
                response.raise_for_status()
                data = response.json()

                choice = data.get("choices", [{}])[0]
                finish_reason = choice.get("finish_reason", "")
                assistant_msg = choice.get("message", {})

                if finish_reason == "tool_calls":
                    # Append the assistant message (with tool_calls) to history
                    messages.append(assistant_msg)

                    # Append tool result for each tool call
                    tool_calls = assistant_msg.get("tool_calls", [])
                    for tc in tool_calls:
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.get("id", ""),
                            "name": tc.get("function", {}).get("name", ""),
                            "content": tc.get("function", {}).get("arguments", "{}"),
                        })
                    continue

                # finish_reason == "stop" or other terminal state
                answer_text = assistant_msg.get("content", "") or ""
                duration = time.time() - start_time

                return LLMResponse(
                    answer_text=answer_text,
                    search_references=[],
                    raw_response=data,
                    duration=duration,
                )

        # Exhausted tool rounds — return whatever we have
        duration = time.time() - start_time
        logger.warning("[KimiClient] Exhausted %d tool rounds", MAX_TOOL_ROUNDS)
        return LLMResponse(
            answer_text="",
            search_references=[],
            raw_response={},
            duration=duration,
        )
