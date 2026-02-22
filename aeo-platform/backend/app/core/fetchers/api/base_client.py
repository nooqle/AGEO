"""Base API client for LLM platforms."""

from abc import ABC, abstractmethod
from typing import Any

from app.schemas.fetch import LLMResponse


class BaseAPIClient(ABC):
    """Base class for LLM API clients.

    All API clients should inherit from this class and implement
    the ask_with_search method.
    """

    def __init__(self, api_key: str, endpoint: str):
        """Initialize the API client.

        Args:
            api_key: API key for authentication
            endpoint: API endpoint URL
        """
        self.api_key = api_key
        self.endpoint = endpoint

    @abstractmethod
    async def ask_with_search(self, question: str) -> LLMResponse:
        """Send a question and get answer with search references.

        Args:
            question: The question to ask

        Returns:
            LLMResponse containing answer and search references
        """
        pass

    async def ask(self, question: str) -> dict[str, Any]:
        """Backward-compat wrapper used by workflow nodes.

        Returns a simple dict with 'content' and 'citations' keys.
        """
        resp = await self.ask_with_search(question)
        return {
            "content": resp.answer_text,
            "citations": [ref.model_dump() for ref in resp.search_references],
            "raw": resp.raw_response,
        }

    def _build_system_prompt(self) -> str:
        """Build the system prompt for the LLM.

        Returns:
            System prompt string
        """
        return (
            "你是一个专业的信息助手。请基于搜索结果回答问题，"
            "并在回答中明确标注引用来源。引用格式为：[序号](URL地址)。"
            "在回答末尾，请列出所有参考资料，格式为：1. [资料标题](URL地址)"
        )
