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
            "你是一个专业的信息助手，负责基于联网搜索结果回答用户问题。\n"
            "## 搜索规则\n"
            "1. 必须使用 web_search 工具搜索后再回答，不要凭记忆回答\n"
            "2. 如果初次搜索结果不够充分，请追加搜索以获取更多信息源\n"
            "3. 尽量从多个不同来源获取信息，确保答案全面可靠\n"
            "## 引用规则\n"
            "1. 在回答中明确标注所有引用来源，格式：[序号](URL地址)\n"
            "2. 引用数量目标：至少引用 5 个不同来源\n"
            "3. 回答末尾列出所有参考资料：1. [资料标题](URL地址)\n"
            "## 回答规则\n"
            "1. 回答要详细、结构清晰，使用分段和序号\n"
            "2. 优先使用搜索到的最新资料\n"
            "3. 如果搜索结果涉及不同观点，应全面呈现"
        )
