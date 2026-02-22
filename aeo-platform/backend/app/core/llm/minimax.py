"""MiniMax M2.1 LLM provider.

Migrated from app/core/minimax_config.py + app/core/minimax_model.py.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Generator

from openai import OpenAI

from app.config import get_settings
from app.core.llm.base import (
    BaseLLMConfig,
    BaseLLMModel,
    LLMResponse,
    ThinkingBlock,
    ToolCallBlock,
)
from app.core.retry_utils import retry_llm_call


@dataclass
class MiniMaxConfig(BaseLLMConfig):
    """Configuration for MiniMax M2.1 model."""

    api_key: str | None = None
    base_url: str = "https://api.minimaxi.com/v1"
    model_name: str = "MiniMax-M2.1"
    reasoning_split: bool = True
    temperature: float = 1.0
    max_tokens: int = 16384
    timeout: float = 60.0

    def __post_init__(self):
        settings = get_settings()
        if self.api_key is None:
            self.api_key = settings.MINIMAX_API_KEY
        if self.base_url == "https://api.minimaxi.com/v1":
            self.base_url = settings.MINIMAX_BASE_URL
        if self.model_name == "MiniMax-M2.1":
            self.model_name = settings.MINIMAX_MODEL_NAME
        if self.reasoning_split:
            self.reasoning_split = settings.MINIMAX_REASONING_SPLIT
        if self.temperature == 1.0:
            self.temperature = settings.MINIMAX_TEMPERATURE
        if self.max_tokens == 16384:
            self.max_tokens = getattr(settings, "MINIMAX_MAX_TOKENS", self.max_tokens)

    def to_openai_kwargs(self) -> dict[str, Any]:
        return {
            "api_key": self.api_key,
            "base_url": self.base_url,
            "timeout": self.timeout,
        }

    def to_completion_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "model": self.model_name,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if self.reasoning_split:
            kwargs["extra_body"] = {"reasoning_split": True}
        return kwargs

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("MiniMax API key is required")
        if not 0.0 < self.temperature <= 1.0:
            raise ValueError("Temperature must be in range (0.0, 1.0]")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")


class MiniMaxModel(BaseLLMModel):
    """MiniMax M2.1 model wrapper using OpenAI compatible API."""

    ALLOWED_KWARGS = BaseLLMModel.ALLOWED_KWARGS | {"do_sample"}

    def __init__(self, config: MiniMaxConfig | None = None):
        self.config = config or MiniMaxConfig()
        self.config.validate()
        self.client = OpenAI(**self.config.to_openai_kwargs())

    # ------------------------------------------------------------------
    # Parsing helpers
    # ------------------------------------------------------------------

    def _parse_reasoning_details(self, message: Any) -> list[ThinkingBlock]:
        thinking_blocks = []
        if hasattr(message, "reasoning_details") and message.reasoning_details:
            for detail in message.reasoning_details:
                if isinstance(detail, dict) and detail.get("type") == "reasoning.text":
                    thinking_blocks.append(
                        ThinkingBlock(
                            text=detail.get("text", ""),
                            id=detail.get("id", "reasoning-1"),
                        )
                    )
        return thinking_blocks

    def _parse_tool_calls(self, message: Any) -> list[ToolCallBlock]:
        tool_calls = []
        # Standard OpenAI format
        if hasattr(message, "tool_calls") and message.tool_calls:
            for call in message.tool_calls:
                try:
                    arguments = json.loads(call.function.arguments)
                except (json.JSONDecodeError, AttributeError):
                    arguments = {}
                tool_calls.append(
                    ToolCallBlock(
                        name=call.function.name,
                        arguments=arguments,
                        id=call.id,
                    )
                )
        # MiniMax native XML tool call format
        if hasattr(message, "content") and message.content:
            content = message.content
            if "<minimax:tool_call>" in content:
                pattern = (
                    r'<invoke name="([^"]+)">\s*'
                    r'<parameter name="([^"]+)">([^<]+)</parameter>'
                    r'(?:\s*<parameter name="([^"]+)">([^<]+)</parameter>)?'
                    r"\s*</invoke>"
                )
                matches = re.findall(pattern, content)
                for match in matches:
                    tool_name = match[0]
                    args: dict[str, Any] = {}
                    if match[1] and match[2]:
                        args[match[1]] = match[2]
                    if match[3] and match[4]:
                        args[match[3]] = match[4]
                    for key, value in args.items():
                        if isinstance(value, str) and value.isdigit():
                            args[key] = int(value)
                    tool_calls.append(
                        ToolCallBlock(
                            name=tool_name,
                            arguments=args,
                            id=f"call_{len(tool_calls)}",
                        )
                    )
        return tool_calls

    # ------------------------------------------------------------------
    # API calls
    # ------------------------------------------------------------------

    @retry_llm_call
    def _make_api_call(self, request_kwargs: dict) -> Any:
        if "timeout" not in request_kwargs:
            request_kwargs["timeout"] = 60.0
        return self.client.chat.completions.create(**request_kwargs)

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        request_kwargs = self.config.to_completion_kwargs()
        request_kwargs["messages"] = self._build_messages(messages)
        if tools:
            # MiniMax only supports function-type tools; filter out others (e.g. web_search)
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
        request_kwargs.update(self._filter_kwargs(kwargs))

        response = self._make_api_call(request_kwargs)
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        thinking_blocks = self._parse_reasoning_details(message)
        tool_calls = self._parse_tool_calls(message)

        content = message.content or ""
        if tool_calls and "<minimax:tool_call>" in content:
            content = ""

        return LLMResponse(
            content=content,
            thinking_blocks=thinking_blocks,
            tool_calls=tool_calls,
            raw_response=response,
            finish_reason=finish_reason,
        )

    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[LLMResponse, None, None]:
        request_kwargs = self.config.to_completion_kwargs()
        request_kwargs["messages"] = self._build_messages(messages)
        request_kwargs["stream"] = True
        if tools:
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
        request_kwargs.update(self._filter_kwargs(kwargs))

        stream_response = self.client.chat.completions.create(**request_kwargs)

        content_buffer = ""
        reasoning_buffer = ""
        current_tool_calls: dict[int, dict[str, Any]] = {}
        last_finish_reason: str | None = None

        for chunk in stream_response:
            delta = chunk.choices[0].delta
            if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
                last_finish_reason = chunk.choices[0].finish_reason

            # Reasoning details
            if hasattr(delta, "reasoning_details") and delta.reasoning_details:
                for detail in delta.reasoning_details:
                    if (
                        isinstance(detail, dict)
                        and detail.get("type") == "reasoning.text"
                    ):
                        text = detail.get("text", "")
                        if text:
                            reasoning_buffer += text
                            yield LLMResponse(
                                content="",
                                thinking_blocks=[
                                    ThinkingBlock(
                                        text=text,
                                        id=detail.get("id", "reasoning-1"),
                                    )
                                ],
                            )

            # Content
            if delta.content:
                content_buffer += delta.content
                yield LLMResponse(content=delta.content)

            # Tool calls
            if hasattr(delta, "tool_calls") and delta.tool_calls:
                for tool_call in delta.tool_calls:
                    index = tool_call.index
                    if index not in current_tool_calls:
                        current_tool_calls[index] = {
                            "id": tool_call.id,
                            "name": tool_call.function.name or "",
                            "arguments": tool_call.function.arguments or "",
                        }
                    else:
                        current_tool_calls[index]["name"] += (
                            tool_call.function.name or ""
                        )
                        current_tool_calls[index]["arguments"] += (
                            tool_call.function.arguments or ""
                        )

        # Final tool calls chunk
        if current_tool_calls:
            tool_blocks = []
            for idx in sorted(current_tool_calls.keys()):
                call_data = current_tool_calls[idx]
                try:
                    arguments = json.loads(call_data["arguments"])
                except json.JSONDecodeError:
                    arguments = {"raw": call_data["arguments"]}
                tool_blocks.append(
                    ToolCallBlock(
                        name=call_data["name"],
                        arguments=arguments,
                        id=call_data["id"],
                    )
                )
            yield LLMResponse(
                content="",  # No content duplication in final chunk (aligned with GLM5)
                thinking_blocks=(
                    [ThinkingBlock(text=reasoning_buffer)]
                    if reasoning_buffer
                    else []
                ),
                tool_calls=tool_blocks,
                finish_reason=last_finish_reason,
            )
        elif last_finish_reason:
            yield LLMResponse(content="", finish_reason=last_finish_reason)
