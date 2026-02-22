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
class LLMResponse:
    """Parsed response from an LLM provider."""

    content: str = ""
    thinking_blocks: list[ThinkingBlock] = field(default_factory=list)
    tool_calls: list[ToolCallBlock] = field(default_factory=list)
    raw_response: Any = None
    finish_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "thinking": [t.to_dict() for t in self.thinking_blocks],
            "tool_calls": [t.to_dict() for t in self.tool_calls],
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

    ALLOWED_KWARGS: set[str] = {"temperature", "max_tokens", "tool_choice", "timeout"}

    def _filter_kwargs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Filter kwargs to only allow known parameters."""
        allowed = self.ALLOWED_KWARGS
        return {k: v for k, v in kwargs.items() if k in allowed}

    def _build_messages(
        self, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
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

    @abstractmethod
    def __call__(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> LLMResponse:
        ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> Generator[LLMResponse, None, None]:
        ...

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
            formatted.append({
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("parameters", {"type": "object"}),
                },
            })
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
