"""Doubao API client."""

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.constants import PlatformConstants
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference


class DoubaoClient(BaseAPIClient):
    """Doubao (ByteDance) API client.

    Uses the Responses API with web search tool enabled.
    API key is read from settings (loaded from .env file).
    """

    DEFAULT_ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/responses"

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
    ):
        """Initialize Doubao client.

        Args:
            api_key: API key (optional, defaults to settings.DOUBAO_API_KEY)
            endpoint: API endpoint (optional, defaults to DEFAULT_ENDPOINT)
            model: Model name (optional, defaults to settings.DOUBAO_MODEL)
        """
        # Read from settings (which loads from .env file) if not provided
        api_key = api_key or settings.DOUBAO_API_KEY
        endpoint = endpoint or self.DEFAULT_ENDPOINT
        model = model or settings.DOUBAO_MODEL

        if not api_key:
            raise ValueError(
                "Doubao API key is required. "
                "Set DOUBAO_API_KEY environment variable or pass api_key parameter."
            )

        super().__init__(api_key, endpoint)
        self.model = model

    async def ask_with_search(self, question: str) -> LLMResponse:
        """Send question and get answer with search references.

        Args:
            question: Question to ask

        Returns:
            LLMResponse with answer and references
        """
        start_time = time.time()

        # Build request payload
        payload = {
            "model": self.model,
            "stream": False,
            "max_tool_calls": 2,
            "tools": [
                {
                    "type": "web_search",
                    "max_keyword": 3,
                    "limit": 10,
                    "sources": ["douyin", "toutiao"],
                    "user_location": {
                        "type": "approximate",
                        "country": "中国",
                    },
                }
            ],
            "input": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "input_text",
                            "text": self._build_system_prompt(),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": question,
                        }
                    ],
                },
            ],
        }

        # Make request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=PlatformConstants.PLATFORM_API_TIMEOUTS["doubao"],
            )
            response.raise_for_status()
            data = response.json()

        # Parse response
        answer_text = self._extract_answer(data)
        search_refs = self._extract_search_references(data)

        duration = time.time() - start_time

        return LLMResponse(
            answer_text=answer_text,
            search_references=search_refs,
            raw_response=data,
            duration=duration,
        )

    def _extract_answer(self, data: dict[str, Any]) -> str:
        """Extract answer text from response.

        Args:
            data: Raw API response

        Returns:
            Answer text
        """
        try:
            output = data.get("output", [])
            for item in output:
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for part in content:
                        if part.get("type") == "output_text":
                            return part.get("text", "")
            return ""
        except Exception:
            return ""

    def _extract_search_references(self, data: dict[str, Any]) -> list[SearchReference]:
        """Extract search references from response.

        Citations are embedded in message content as 'url_citation' annotations.

        Args:
            data: Raw API response

        Returns:
            List of search references
        """
        references = []
        try:
            output = data.get("output", [])
            for item in output:
                # Look for message type with annotations
                if item.get("type") == "message":
                    content = item.get("content", [])
                    for part in content:
                        if part.get("type") == "output_text":
                            annotations = part.get("annotations", [])
                            for idx, annotation in enumerate(annotations, 1):
                                if annotation.get("type") == "url_citation":
                                    ref = SearchReference(
                                        index=idx,
                                        title=annotation.get("title", ""),
                                        url=annotation.get("url", ""),
                                        snippet=annotation.get("summary", ""),
                                        site_name=annotation.get("site_name", ""),
                                        is_official=annotation.get(
                                            "is_official", False
                                        ),
                                    )
                                    references.append(ref)

                # Fallback: also check web_search_call for older API versions
                if item.get("type") == "web_search_call":
                    results = item.get("results", [])
                    for idx, result in enumerate(results, 1):
                        # Only add if not already found from annotations
                        if not any(r.url == result.get("url") for r in references):
                            ref = SearchReference(
                                index=len(references) + 1,
                                title=result.get("title", ""),
                                url=result.get("url", ""),
                                snippet=result.get("snippet", ""),
                                site_name=result.get("site_name", ""),
                                is_official=result.get("is_official", False),
                            )
                            references.append(ref)
        except Exception:
            pass
        return references
