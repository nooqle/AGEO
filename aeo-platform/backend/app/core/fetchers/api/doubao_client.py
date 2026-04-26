"""Doubao API client."""

import logging
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.constants import PlatformConstants
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference

logger = logging.getLogger(__name__)


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
        use_doubao_app: bool | None = None,
        doubao_app_feature: str | None = None,
        doubao_app_role_description: str | None = None,
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
        self.use_doubao_app = (
            settings.DOUBAO_USE_APP_API
            if use_doubao_app is None
            else bool(use_doubao_app)
        )
        self.doubao_app_feature = (
            doubao_app_feature or settings.DOUBAO_APP_FEATURE or "ai_search"
        ).strip() or "ai_search"
        self.doubao_app_role_description = (
            doubao_app_role_description or settings.DOUBAO_APP_ROLE_DESCRIPTION
        ).strip()

    async def ask_with_search(self, question: str) -> LLMResponse:
        """Send question and get answer with search references.

        Args:
            question: Question to ask

        Returns:
            LLMResponse with answer and references
        """
        if self.use_doubao_app:
            try:
                return await self._ask_with_doubao_app(question)
            except httpx.HTTPStatusError as exc:
                if not self._should_fallback_from_doubao_app(exc):
                    raise
                logger.warning(
                    "[DoubaoClient] doubao_app failed with HTTP %s; falling back to web_search",
                    exc.response.status_code,
                )
            except Exception:
                if not settings.DOUBAO_APP_API_FALLBACK_TO_WEB_SEARCH:
                    raise
                logger.warning(
                    "[DoubaoClient] doubao_app failed; falling back to web_search",
                    exc_info=True,
                )

        return await self._ask_with_web_search(question)

    async def _ask_with_web_search(self, question: str) -> LLMResponse:
        """Send question through the generic Responses web_search tool."""
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
                        "country": "\u4e2d\u56fd",
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

    async def _ask_with_doubao_app(self, question: str) -> LLMResponse:
        """Send question through the Doubao App assistant tool."""
        start_time = time.time()

        payload = {
            "model": self.model,
            "stream": False,
            "tools": [
                {
                    "type": "doubao_app",
                    "feature": {
                        self.doubao_app_feature: {
                            "type": "enabled",
                            "role_description": self.doubao_app_role_description,
                        }
                    },
                    "user_location": {
                        "type": "approximate",
                        "country": "\u4e2d\u56fd",
                    },
                }
            ],
            "input": [
                {
                    "type": "message",
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": question,
                        }
                    ],
                }
            ],
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "ark-beta-doubao-app": "true",
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

        answer_text = self._extract_doubao_app_answer(data)
        search_refs = self._extract_doubao_app_references(data)
        duration = time.time() - start_time

        return LLMResponse(
            answer_text=answer_text,
            search_references=search_refs,
            raw_response=data,
            duration=duration,
        )

    @staticmethod
    def _should_fallback_from_doubao_app(exc: httpx.HTTPStatusError) -> bool:
        if not settings.DOUBAO_APP_API_FALLBACK_TO_WEB_SEARCH:
            return False
        # Keep rate limiting visible to A4 retry handling instead of hiding it
        # behind the slower generic web_search path.
        if exc.response.status_code == 429:
            return False
        return exc.response.status_code in {400, 403, 404}

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

    def _extract_doubao_app_answer(self, data: dict[str, Any]) -> str:
        """Extract answer text from doubao_app response blocks."""
        text_parts: list[str] = []
        try:
            for item in data.get("output", []):
                if item.get("type") == "doubao_app_call":
                    for block in item.get("blocks", []):
                        if block.get("type") == "output_text" and block.get("text"):
                            text_parts.append(str(block.get("text") or ""))
                if item.get("type") == "message":
                    for part in item.get("content", []):
                        if part.get("type") in {"output_text", "text"}:
                            text_parts.append(str(part.get("text") or ""))
            return "\n\n".join(part.strip() for part in text_parts if part.strip())
        except Exception:
            return ""

    def _extract_doubao_app_references(
        self,
        data: dict[str, Any],
    ) -> list[SearchReference]:
        """Extract search references from doubao_app search blocks."""
        references: list[SearchReference] = []
        seen_urls: set[str] = set()
        try:
            for item in data.get("output", []):
                if item.get("type") != "doubao_app_call":
                    continue
                for block in item.get("blocks", []):
                    if block.get("type") != "search":
                        continue
                    for result in block.get("results", []):
                        card = result.get("text_card") or result.get("card") or result
                        if not isinstance(card, dict):
                            continue
                        url = str(card.get("url") or "").strip()
                        if not url or url in seen_urls:
                            continue
                        seen_urls.add(url)
                        references.append(
                            SearchReference(
                                index=len(references) + 1,
                                title=str(card.get("title") or url),
                                url=url,
                                snippet=card.get("summary") or card.get("snippet"),
                                site_name=card.get("sitename") or card.get("site_name"),
                                is_official=bool(card.get("is_official", False)),
                            )
                        )
        except Exception:
            return references
        return references

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
