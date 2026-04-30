"""DeepSeek LLM provider.

DeepSeek exposes an OpenAI-compatible API. The wrapper intentionally keeps
thinking mode disabled by default because thinking + tool calls requires
reasoning_content to be carried through every subsequent tool turn.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from time import perf_counter
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
class DeepSeekConfig(BaseLLMConfig):
    """Configuration for DeepSeek chat completions."""

    api_key: str | None = None
    base_url: str = "https://api.deepseek.com"
    model_name: str = "deepseek-v4-pro"
    thinking_enabled: bool | None = None
    reasoning_effort: str = "high"
    temperature: float = 0.0
    max_tokens: int = 8192
    timeout: float = 120.0

    def __post_init__(self) -> None:
        settings = get_settings()
        if self.api_key is None:
            self.api_key = getattr(settings, "DEEPSEEK_API_KEY", None)
        if self.base_url == "https://api.deepseek.com":
            self.base_url = getattr(settings, "DEEPSEEK_BASE_URL", self.base_url)
        if self.model_name == "deepseek-v4-pro":
            self.model_name = getattr(settings, "DEEPSEEK_MODEL_NAME", self.model_name)
        if self.thinking_enabled is None:
            self.thinking_enabled = bool(
                getattr(settings, "DEEPSEEK_THINKING_ENABLED", False)
            )
        if self.reasoning_effort == "high":
            self.reasoning_effort = getattr(
                settings,
                "DEEPSEEK_REASONING_EFFORT",
                self.reasoning_effort,
            )
        if self.temperature == 0.0:
            self.temperature = getattr(
                settings,
                "DEEPSEEK_TEMPERATURE",
                self.temperature,
            )
        if self.max_tokens == 8192:
            self.max_tokens = getattr(
                settings,
                "DEEPSEEK_MAX_TOKENS",
                self.max_tokens,
            )
        if self.timeout == 120.0:
            self.timeout = getattr(
                settings,
                "DEEPSEEK_TIMEOUT_SECONDS",
                self.timeout,
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
            "max_tokens": self.max_tokens,
        }
        if not self.thinking_enabled:
            kwargs["temperature"] = self.temperature
        else:
            kwargs["reasoning_effort"] = self.reasoning_effort
        kwargs["extra_body"] = {
            "thinking": {
                "type": "enabled" if self.thinking_enabled else "disabled",
            }
        }
        return kwargs

    def validate(self) -> None:
        if not self.api_key:
            raise ValueError("DeepSeek API key is required")
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be in range [0.0, 2.0]")
        if self.max_tokens < 1:
            raise ValueError("Max tokens must be positive")
        if self.reasoning_effort not in {"high", "max"}:
            raise ValueError("DeepSeek reasoning_effort must be high or max")


class DeepSeekModel(BaseLLMModel):
    """DeepSeek model wrapper using OpenAI-compatible chat completions."""

    ALLOWED_KWARGS = BaseLLMModel.ALLOWED_KWARGS | {
        "response_format",
        "reasoning_effort",
    }

    def __init__(self, config: DeepSeekConfig | None = None):
        self.config = config or DeepSeekConfig()
        self.config.validate()
        self.client = OpenAI(**self.config.to_openai_kwargs())

    def _parse_reasoning_content(self, message: Any) -> list[ThinkingBlock]:
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            return [ThinkingBlock(text=message.reasoning_content)]
        return []

    @staticmethod
    def _normalize_tool_calls(message: dict[str, Any]) -> list[str]:
        tool_calls = message.get("tool_calls")
        if not isinstance(tool_calls, list):
            return []

        ids: list[str] = []
        normalized_calls: list[dict[str, Any]] = []
        for index, call in enumerate(tool_calls, start=1):
            if not isinstance(call, dict):
                continue
            normalized = dict(call)
            call_id = str(normalized.get("id") or f"call_{index}")
            normalized["id"] = call_id
            normalized.setdefault("type", "function")
            function = normalized.get("function")
            if isinstance(function, dict):
                normalized_function = dict(function)
                arguments = normalized_function.get("arguments")
                if isinstance(arguments, (dict, list)):
                    normalized_function["arguments"] = json.dumps(
                        arguments,
                        ensure_ascii=False,
                    )
                elif arguments is None:
                    normalized_function["arguments"] = "{}"
                normalized["function"] = normalized_function
            normalized_calls.append(normalized)
            ids.append(call_id)
        message["tool_calls"] = normalized_calls
        return ids

    @staticmethod
    def _as_historical_assistant_note(message: dict[str, Any]) -> dict[str, Any]:
        content = str(message.get("content") or "").strip()
        if not content:
            content = "Historical tool result is available in the surrounding context."
        return {
            "role": "assistant",
            "content": f"[historical tool result] {content}",
        }

    @staticmethod
    def _missing_tool_result_message(tool_call_id: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": "Historical tool result was archived before this request.",
        }

    def _repair_tool_history(
        self,
        messages: list[dict[str, Any]],
        *,
        thinking_enabled: bool,
    ) -> list[dict[str, Any]]:
        repaired: list[dict[str, Any]] = []
        pending_tool_call_ids: list[str] = []

        def close_pending_tool_calls() -> None:
            nonlocal pending_tool_call_ids
            for pending_id in pending_tool_call_ids:
                repaired.append(self._missing_tool_result_message(pending_id))
            pending_tool_call_ids = []

        for message in messages:
            role = message.get("role")
            if role == "tool":
                if pending_tool_call_ids:
                    fixed = dict(message)
                    tool_call_id = str(fixed.get("tool_call_id") or "")
                    if tool_call_id not in pending_tool_call_ids:
                        tool_call_id = pending_tool_call_ids[0]
                    fixed["tool_call_id"] = tool_call_id
                    repaired.append(fixed)
                    pending_tool_call_ids.remove(tool_call_id)
                else:
                    repaired.append(self._as_historical_assistant_note(message))
                continue

            if pending_tool_call_ids:
                close_pending_tool_calls()

            if role == "assistant" and message.get("tool_calls"):
                fixed = dict(message)
                tool_call_ids = self._normalize_tool_calls(fixed)
                if thinking_enabled and not fixed.get("reasoning_content"):
                    fixed.pop("tool_calls", None)
                    fixed.pop("reasoning_content", None)
                    if not str(fixed.get("content") or "").strip():
                        fixed["content"] = (
                            "Historical tool call omitted because the original "
                            "DeepSeek reasoning_content is unavailable."
                        )
                    repaired.append(fixed)
                    continue
                repaired.append(fixed)
                pending_tool_call_ids = tool_call_ids
                continue

            repaired.append(message)

        if pending_tool_call_ids:
            close_pending_tool_calls()

        return repaired

    def _build_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        thinking_enabled: bool | None = None,
    ) -> list[dict[str, Any]]:
        formatted = super()._build_messages(messages)
        for source, target in zip(messages, formatted, strict=False):
            if source.get("reasoning_content"):
                target["reasoning_content"] = source["reasoning_content"]
        return self._repair_tool_history(
            formatted,
            thinking_enabled=(
                self.config.thinking_enabled
                if thinking_enabled is None
                else thinking_enabled
            ),
        )

    def _parse_tool_calls(self, message: Any) -> list[ToolCallBlock]:
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
    def _make_api_call(self, request_kwargs: dict[str, Any]) -> Any:
        if "timeout" not in request_kwargs:
            request_kwargs["timeout"] = self.config.timeout
        return self.client.chat.completions.create(**request_kwargs)

    @staticmethod
    def _apply_thinking_override(
        request_kwargs: dict[str, Any],
        thinking_enabled: bool | None,
    ) -> None:
        if thinking_enabled is None:
            return
        extra_body = dict(request_kwargs.get("extra_body") or {})
        extra_body["thinking"] = {
            "type": "enabled" if thinking_enabled else "disabled",
        }
        request_kwargs["extra_body"] = extra_body
        if thinking_enabled:
            request_kwargs.pop("temperature", None)
            request_kwargs.setdefault("reasoning_effort", "high")
        else:
            request_kwargs.pop("reasoning_effort", None)

    @staticmethod
    def _drop_sampling_kwargs_for_thinking(request_kwargs: dict[str, Any]) -> None:
        thinking = (request_kwargs.get("extra_body") or {}).get("thinking") or {}
        if thinking.get("type") == "enabled":
            request_kwargs.pop("temperature", None)

    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        thinking_enabled_override = kwargs.pop("thinking_enabled", None)
        request_kwargs = self.config.to_completion_kwargs()
        effective_thinking_enabled = (
            self.config.thinking_enabled
            if thinking_enabled_override is None
            else thinking_enabled_override
        )
        request_kwargs["messages"] = self._build_messages(
            messages,
            thinking_enabled=bool(effective_thinking_enabled),
        )
        if tools:
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
        self._apply_thinking_override(request_kwargs, thinking_enabled_override)
        request_kwargs.update(self._filter_kwargs(kwargs))
        self._drop_sampling_kwargs_for_thinking(request_kwargs)

        started_at = perf_counter()
        response = self._make_api_call(request_kwargs)
        latency_ms = max(int((perf_counter() - started_at) * 1000), 0)
        message = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        return LLMResponse(
            content=message.content or "",
            thinking_blocks=self._parse_reasoning_content(message),
            tool_calls=self._parse_tool_calls(message),
            usage=self._parse_usage(getattr(response, "usage", None)),
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
        thinking_enabled_override = kwargs.pop("thinking_enabled", None)
        request_kwargs = self.config.to_completion_kwargs()
        effective_thinking_enabled = (
            self.config.thinking_enabled
            if thinking_enabled_override is None
            else thinking_enabled_override
        )
        request_kwargs["messages"] = self._build_messages(
            messages,
            thinking_enabled=bool(effective_thinking_enabled),
        )
        request_kwargs["stream"] = True
        if tools:
            fn_tools = [t for t in tools if t.get("type") == "function"]
            if fn_tools:
                request_kwargs["tools"] = fn_tools
        self._apply_thinking_override(request_kwargs, thinking_enabled_override)
        request_kwargs.update(self._filter_kwargs(kwargs))
        self._drop_sampling_kwargs_for_thinking(request_kwargs)

        stream_response = self.client.chat.completions.create(**request_kwargs)

        content_buffer = ""
        reasoning_buffer = ""
        current_tool_calls: dict[int, dict[str, Any]] = {}
        last_finish_reason: str | None = None
        final_usage = None

        for chunk in stream_response:
            delta = chunk.choices[0].delta
            if (
                hasattr(chunk.choices[0], "finish_reason")
                and chunk.choices[0].finish_reason
            ):
                last_finish_reason = chunk.choices[0].finish_reason
            if getattr(chunk, "usage", None):
                final_usage = self._parse_usage(chunk.usage)

            reasoning_piece = getattr(delta, "reasoning_content", None)
            if reasoning_piece:
                reasoning_buffer += reasoning_piece
                yield LLMResponse(
                    content="",
                    thinking_blocks=[ThinkingBlock(text=reasoning_piece)],
                )

            if delta.content:
                content_buffer += delta.content
                yield LLMResponse(content=delta.content)

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
                content="",
                thinking_blocks=(
                    [ThinkingBlock(text=reasoning_buffer)] if reasoning_buffer else []
                ),
                tool_calls=tool_blocks,
                usage=final_usage,
                finish_reason=last_finish_reason,
            )
        elif final_usage or last_finish_reason:
            yield LLMResponse(
                content="",
                usage=final_usage,
                finish_reason=last_finish_reason,
            )
