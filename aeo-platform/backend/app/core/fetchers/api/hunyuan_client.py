"""Hunyuan API client."""

import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.fetchers.api.base_client import BaseAPIClient
from app.schemas.fetch import LLMResponse, SearchReference


class HunyuanClient(BaseAPIClient):
    """Tencent Hunyuan API client.

    Uses the OpenAI-compatible chat completions API with search enabled.
    API key is read from settings (loaded from .env file).
    """

    DEFAULT_ENDPOINT = "https://api.hunyuan.cloud.tencent.com/v1/chat/completions"

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        model: str | None = None,
    ):
        """Initialize Hunyuan client.

        Args:
            api_key: API key (optional, defaults to settings.HUNYUAN_API_KEY)
            endpoint: API endpoint (optional, defaults to settings.HUNYUAN_BASE_URL)
            model: Model name (optional, defaults to settings.HUNYUAN_MODEL)
        """
        # Read from settings (which loads from .env file) if not provided
        api_key = api_key or settings.HUNYUAN_API_KEY
        base_url = endpoint or settings.HUNYUAN_BASE_URL or ""
        # Ensure full path: base URL → append /chat/completions
        if base_url and "/chat/completions" not in base_url:
            endpoint = base_url.rstrip("/") + "/chat/completions"
        else:
            endpoint = base_url or self.DEFAULT_ENDPOINT
        model = model or settings.HUNYUAN_MODEL

        if not api_key:
            raise ValueError(
                "Hunyuan API key is required. "
                "Set HUNYUAN_API_KEY environment variable or pass api_key parameter."
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
            "messages": [
                {
                    "role": "system",
                    "content": self._build_system_prompt(),
                },
                {
                    "role": "user",
                    "content": question,
                },
            ],
            "enable_enhancement": True,
            "search_info": True,
            "citation": True,
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
                timeout=60.0,
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
            choices = data.get("choices", [])
            if choices:
                message = choices[0].get("message", {})
                return message.get("content", "")
            return ""
        except Exception:
            return ""

    def _extract_search_references(self, data: dict[str, Any]) -> list[SearchReference]:
        """Extract search references from response.

        Args:
            data: Raw API response

        Returns:
            List of search references
        """
        references = []
        try:
            search_info = data.get("search_info", {})
            # API returns "search_results" (snake_case), not "SearchResults"
            search_results = search_info.get("search_results", [])
            for idx, result in enumerate(search_results, 1):
                ref = SearchReference(
                    index=result.get("index", idx),
                    title=result.get("title", ""),
                    url=result.get("url", ""),
                    snippet=result.get("text", ""),
                    site_name=result.get("site_name", ""),
                    is_official=result.get("is_official", False),
                )
                references.append(ref)
        except Exception:
            pass
        return references
