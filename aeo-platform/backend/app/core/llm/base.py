"""LLM abstraction layer - base types and interfaces.

Provider-agnostic types that all LLM providers must implement.
Consumers only need: `from app.core.llm import get_llm_model, LLMResponse`
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generator


@dataclass
class ThinkingBlock:
    """Represents a thinking/reasoning block from the model."""

    text: str = ""
    type: str = "thinking"
    id: str = "reasoning-1"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "text": self.text, "id": self.id}


@dataclass
class ToolCallBlock:
    """Represents a tool call block from the model."""

    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    type: str = "tool_call"
    id: str = "call-1"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "name": self.name,
            "arguments": self.arguments,
            "id": self.id,
        }


@dataclass
class LLMUsage:
    """Token usage information reported by the provider."""

    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cached_prompt_tokens: int | None = None
    cache_miss_prompt_tokens: int | None = None
    reasoning_tokens: int | None = None
    image_tokens: int | None = None
    video_tokens: int | None = None
    prompt_tokens_details: dict[str, Any] | None = None
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cached_prompt_tokens": self.cached_prompt_tokens,
            "cache_miss_prompt_tokens": self.cache_miss_prompt_tokens,
            "reasoning_tokens": self.reasoning_tokens,
            "image_tokens": self.image_tokens,
            "video_tokens": self.video_tokens,
            "prompt_tokens_details": self.prompt_tokens_details,
            "raw": self.raw,
        }


@dataclass
class LLMResponse:
    """Parsed response from an LLM provider."""

    content: str = ""
    thinking_blocks: list[ThinkingBlock] = field(default_factory=list)
    tool_calls: list[ToolCallBlock] = field(default_factory=list)
    usage: LLMUsage | None = None
    raw_response: Any = None
    finish_reason: str | None = None
    latency_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "thinking": [t.to_dict() for t in self.thinking_blocks],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
            "usage": self.usage.to_dict() if self.usage else None,
            "latency_ms": self.latency_ms,
        }


class BaseLLMConfig(ABC):
    """Abstract base for LLM provider configuration."""

    @abstractmethod
    def to_openai_kwargs(self) -> dict[str, Any]:
        """Return kwargs for OpenAI client constructor."""
        ...

    @abstractmethod
    def to_completion_kwargs(self) -> dict[str, Any]:
        """Return kwargs for chat.completions.create()."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Validate configuration values."""
        ...


class BaseLLMModel(ABC):
    """Abstract base for LLM provider model."""

    ALLOWED_KWARGS: set[str] = {
        "temperature",
        "max_tokens",
        "tool_choice",
        "timeout",
        "model",
    }

    def _filter_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Filter kwargs to only allow known parameters."""
        allowed = self.ALLOWED_KWARGS
        return {k: v for k, v in kwargs.items() if k in allowed}

    def _build_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Format messages for OpenAI-compatible API calls."""
        formatted_messages = []
        for msg in messages:
            formatted_msg: dict[str, Any] = {
                "role": msg.get("role", "user"),
                "content": msg.get("content", ""),
            }
            if "tool_calls" in msg:
                formatted_msg["tool_calls"] = msg["tool_calls"]
            if "tool_call_id" in msg:
                formatted_msg["tool_call_id"] = msg["tool_call_id"]
            if "name" in msg:
                formatted_msg["name"] = msg["name"]
            formatted_messages.append(formatted_msg)
        return formatted_messages

    def _parse_usage(self, usage: Any) -> LLMUsage | None:
        """Normalize provider usage payload into a shared structure."""
        if not usage:
            return None

        if isinstance(usage, dict):
            data = usage
        elif hasattr(usage, "model_dump"):
            data = usage.model_dump()
        elif hasattr(usage, "dict"):
            data = usage.dict()
        else:
            data = {
                key: getattr(usage, key)
                for key in (
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "prompt_tokens_details",
                    "prompt_cache_hit_tokens",
                    "prompt_cache_miss_tokens",
                    "reasoning_tokens",
                    "image_tokens",
                    "video_tokens",
                )
                if hasattr(usage, key)
            }

        if not data:
            return None

        prompt_tokens_details = data.get("prompt_tokens_details")
        if prompt_tokens_details is not None and not isinstance(
            prompt_tokens_details, dict
        ):
            if hasattr(prompt_tokens_details, "model_dump"):
                prompt_tokens_details = prompt_tokens_details.model_dump()
            elif hasattr(prompt_tokens_details, "dict"):
                prompt_tokens_details = prompt_tokens_details.dict()
            else:
                prompt_tokens_details = {
                    key: getattr(prompt_tokens_details, key)
                    for key in ("cached_tokens",)
                    if hasattr(prompt_tokens_details, key)
                }

        cached_prompt_tokens = None
        cache_miss_prompt_tokens = None
        if isinstance(prompt_tokens_details, dict):
            cached_prompt_tokens = prompt_tokens_details.get("cached_tokens")

        if data.get("prompt_cache_hit_tokens") is not None:
            cached_prompt_tokens = data.get("prompt_cache_hit_tokens")
        if data.get("prompt_cache_miss_tokens") is not None:
            cache_miss_prompt_tokens = data.get("prompt_cache_miss_tokens")

        prompt_tokens = data.get("prompt_tokens")
        if prompt_tokens is None and (
            cached_prompt_tokens is not None or cache_miss_prompt_tokens is not None
        ):
            prompt_tokens = int(cached_prompt_tokens or 0) + int(
                cache_miss_prompt_tokens or 0
            )

        normalized_raw = dict(data)
        normalized_raw["prompt_tokens_details"] = prompt_tokens_details

        return LLMUsage(
            prompt_tokens=prompt_tokens,
            completion_tokens=data.get("completion_tokens"),
            total_tokens=data.get("total_tokens"),
            cached_prompt_tokens=cached_prompt_tokens,
            cache_miss_prompt_tokens=cache_miss_prompt_tokens,
            reasoning_tokens=data.get("reasoning_tokens"),
            image_tokens=data.get("image_tokens"),
            video_tokens=data.get("video_tokens"),
            prompt_tokens_details=prompt_tokens_details,
            raw=normalized_raw,
        )

    @abstractmethod
    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse: ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[LLMResponse, None, None]: ...

    async def async_call(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        """Default async implementation via run_in_executor."""
        import asyncio

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            lambda: self(messages=messages, tools=tools, **kwargs),
        )

    def format_tools_for_agentscope(
        self, tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Format tools to AgentScope compatible format."""
        formatted = []
        for tool in tools:
            formatted.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": tool.get("parameters", {"type": "object"}),
                    },
                }
            )
        return formatted

    def create_tool_result_message(
        self, tool_call_id: str, content: str
    ) -> dict[str, Any]:
        """Create a tool result message for the conversation."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }
