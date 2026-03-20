"""GLM5 (智谱AI) LLM provider.

Uses OpenAI SDK with GLM5 base_url. Key differences from MiniMax:
- Thinking field: `reasoning_content` (string) instead of `reasoning_details` (list)
- Thinking config: extra_body {thinking: {type: "enabled"}} instead of {reasoning_split: true}
- Tool streaming: needs `tool_stream: true` in extra_body
- No XML tool call fallback
- Final tool_calls chunk does NOT repeat content_buffer
"""

import json
import logging
from time import perf_counter
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

logger = logging.getLogger(__name__)


@dataclass
class GLM5Config(BaseLLMConfig):
    """Configuration for GLM5 model."""

    api_key: str | None = None
    base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    model_name: str = "glm-5"
    thinking_enabled: bool = True
    temperature: float = 0.7
    max_tokens: int = 16384
    timeout: float = 120.0

    def __post_init__(self):
        settings = get_settings()
        if self.api_key is None:
            self.api_key = getattr(settings, "GLM5_API_KEY", None)
        if self.base_url == "https://open.bigmodel.cn/api/paas/v4":
            self.base_url = getattr(
                settings, "GLM5_BASE_URL", self.base_url
            )
        if self.model_name == "glm-5":
            self.model_name = getattr(
                settings, "GLM5_MODEL_NAME", self.model_name
            )
        if self.thinking_enabled:
            self.thinking_enabled = getattr(
                settings, "GLM5_THINKING_ENABLED", True
            )
        if self.temperature == 0.7:
            self.temperature = getattr(
                settings, "GLM5_TEMPERATURE", self.temperature
            )
        if self.max_tokens == 16384:
            self.max_tokens = getattr(
                settings, "GLM5_MAX_TOKENS", self.max_tokens
            )

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
        extra_body: dict[str, Any] = {}
        if self.thinking_enabled:
            extra_body["thinking"] = {"type": "enabled", "clear_thinking": True}
        if extra_body:
            kwargs["extra_body"] = extra_body
        return kwargs

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("GLM5 API key is required")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be in range [0.0, 2.0]")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")


class GLM5Model(BaseLLMModel):
    """GLM5 model wrapper using OpenAI compatible API."""

    ALLOWED_KWARGS = BaseLLMModel.ALLOWED_KWARGS | {"tool_stream"}

    def __init__(self, config: GLM5Config | None = None):
        self.config = config or GLM5Config()
        self.config.validate()
        self.client = OpenAI(**self.config.to_openai_kwargs())

    def _parse_reasoning_content(self, message: Any) -> list[ThinkingBlock]:
        """Parse reasoning_content (string) from GLM5 response."""
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            return [ThinkingBlock(text=message.reasoning_content)]
        return []

    def _parse_tool_calls(self, message: Any) -> list[ToolCallBlock]:
        """Parse tool_calls — pure OpenAI format, no XML fallback."""
        tool_calls = []
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
        return tool_calls

    @retry_llm_call
    def _make_api_call(self, request_kwargs: dict) -> Any:
        if "timeout" not in request_kwargs:
            request_kwargs["timeout"] = self.config.timeout
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
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
        request_kwargs.update(self._filter_kwargs(kwargs))

        started_at = perf_counter()
        response = self._make_api_call(request_kwargs)
        latency_ms = max(int((perf_counter() - started_at) * 1000), 0)
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        thinking_blocks = self._parse_reasoning_content(message)
        tool_calls = self._parse_tool_calls(message)
        content = message.content or ""
        usage = self._parse_usage(getattr(response, "usage", None))

        return LLMResponse(
            content=content,
            thinking_blocks=thinking_blocks,
            tool_calls=tool_calls,
            usage=usage,
            raw_response=response,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
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

        # GLM5 needs tool_stream for streaming tool calls
        if tools:
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
                extra = request_kwargs.get("extra_body", {})
                extra["tool_stream"] = True
                request_kwargs["extra_body"] = extra

        request_kwargs.update(self._filter_kwargs(kwargs))

        stream_response = self.client.chat.completions.create(**request_kwargs)

        content_buffer = ""
        reasoning_buffer = ""
        current_tool_calls: dict[int, dict[str, Any]] = {}
        last_finish_reason: str | None = None
        final_usage = None

        for chunk in stream_response:
            delta = chunk.choices[0].delta
            if hasattr(chunk.choices[0], "finish_reason") and chunk.choices[0].finish_reason:
                last_finish_reason = chunk.choices[0].finish_reason
            if getattr(chunk, "usage", None):
                final_usage = self._parse_usage(chunk.usage)

            # GLM5 reasoning: delta.reasoning_content is a string
            if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                text = delta.reasoning_content
                reasoning_buffer += text
                yield LLMResponse(
                    content="",
                    thinking_blocks=[ThinkingBlock(text=text)],
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

        # Final tool calls chunk — GLM5 does NOT repeat content_buffer
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
                content="",  # GLM5: no content duplication in final chunk
                thinking_blocks=(
                    [ThinkingBlock(text=reasoning_buffer)]
                    if reasoning_buffer
                    else []
                ),
                tool_calls=tool_blocks,
                usage=final_usage,
                finish_reason=last_finish_reason,
            )
        elif final_usage or last_finish_reason:
            # No tool calls but we may still have usage/finish metadata to report
            yield LLMResponse(
                content="",
                usage=final_usage,
                finish_reason=last_finish_reason,
            )
