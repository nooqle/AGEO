"""Bocha Web Search API Service.

This module provides a service layer for interacting with the Bocha Web Search API.
"""

from datetime import datetime
from typing import Any

import httpx

from app.core.config import settings


class BochaService:
    """Service for Bocha Web Search API.

    Example:
        ```python
        service = BochaService()
        results = service.search("阿里巴巴2024年ESG报告", count=5)
        ```
    """

    BASE_URL = "https://api.bocha.cn/v1/web-search"
    DEFAULT_TIMEOUT = 10.0
    MAX_RETRIES = 2

    def __init__(self, api_key: str | None = None):
        """Initialize Bocha service.

        Args:
            api_key: Bocha API key. If None, reads from settings.BOCHA_API_KEY.
        """
        self.api_key = api_key or settings.BOCHA_API_KEY
        if not self.api_key:
            raise ValueError(
                "Bocha API key is required. "
                "Set BOCHA_API_KEY in .env file or pass api_key parameter."
            )

    def search(
        self,
        query: str,
        count: int = 10,
        freshness: str = "noLimit",
        summary: bool = True,
    ) -> dict[str, Any]:
        """Search the web using Bocha API.

        Args:
            query: Search query string
            count: Number of results to return (1-50, default 10)
            freshness: Time range filter (noLimit/oneDay/oneWeek/oneMonth/oneYear)
            summary: Whether to include text summary

        Returns:
            Dictionary containing cleaned search results or error info
        """
        # Validate parameters
        count = max(1, min(50, count))

        payload = {
            "query": query,
            "count": count,
            "freshness": freshness,
            "summary": summary,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        # Attempt search with retries
        for attempt in range(self.MAX_RETRIES):
            try:
                response = httpx.post(
                    self.BASE_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.DEFAULT_TIMEOUT,
                )

                # Handle HTTP errors
                if response.status_code == 200:
                    data = response.json()
                    return self._clean_results(data, query)

                elif response.status_code == 401:
                    return {
                        "success": False,
                        "error": "Invalid API key",
                        "query": query,
                        "results": [],
                    }

                elif response.status_code == 429:
                    return {
                        "success": False,
                        "error": "Rate limit exceeded",
                        "query": query,
                        "results": [],
                    }

                elif response.status_code >= 500:
                    # Server error, retry
                    if attempt < self.MAX_RETRIES - 1:
                        continue
                    return {
                        "success": False,
                        "error": f"Server error: {response.status_code}",
                        "query": query,
                        "results": [],
                    }

                else:
                    return {
                        "success": False,
                        "error": f"HTTP {response.status_code}: {response.text}",
                        "query": query,
                        "results": [],
                    }

            except httpx.TimeoutException:
                if attempt < self.MAX_RETRIES - 1:
                    continue
                return {
                    "success": False,
                    "error": "Request timeout",
                    "query": query,
                    "results": [],
                }

            except httpx.HTTPError as e:
                if attempt < self.MAX_RETRIES - 1:
                    continue
                return {
                    "success": False,
                    "error": f"HTTP error: {str(e)}",
                    "query": query,
                    "results": [],
                }

            except Exception as e:
                return {
                    "success": False,
                    "error": f"Unexpected error: {str(e)}",
                    "query": query,
                    "results": [],
                }

        # Should not reach here, but just in case
        return {
            "success": False,
            "error": "Max retries exceeded",
            "query": query,
            "results": [],
        }

    def _clean_results(self, data: dict, query: str) -> dict[str, Any]:
        """Clean and extract relevant fields from API response.

        Args:
            data: Raw API response
            query: Original search query

        Returns:
            Cleaned results dictionary
        """
        if data.get("code") != 200:
            return {
                "success": False,
                "error": data.get("msg", "Unknown error"),
                "query": query,
                "results": [],
            }

        web_pages = data.get("data", {}).get("webPages", {})
        values = web_pages.get("value", [])

        cleaned_results = []
        for item in values:
            # Extract and clean date
            date_str = item.get("datePublished") or item.get("dateLastCrawled", "")
            if date_str:
                # Try to parse and format date
                try:
                    # Handle ISO format with timezone
                    date_str = date_str.replace("Z", "+00:00")
                    dt = datetime.fromisoformat(date_str)
                    formatted_date = dt.strftime("%Y-%m-%d")
                except (ValueError, TypeError):
                    formatted_date = date_str[:10] if date_str else ""
            else:
                formatted_date = ""

            cleaned_item = {
                "name": item.get("name", ""),
                "url": item.get("url", ""),
                "snippet": item.get("snippet", ""),
                "summary": item.get("summary", ""),
                "date": formatted_date,
                "site_name": item.get("siteName", ""),
            }
            cleaned_results.append(cleaned_item)

        return {
            "success": True,
            "query": query,
            "total": web_pages.get("totalEstimatedMatches", 0),
            "results": cleaned_results,
        }

    def search_to_markdown(
        self,
        query: str,
        count: int = 5,
        freshness: str = "noLimit",
    ) -> str:
        """Search and return results formatted as Markdown.

        Args:
            query: Search query
            count: Number of results
            freshness: Time range filter

        Returns:
            Markdown formatted search results
        """
        result = self.search(query, count=count, freshness=freshness)

        if not result["success"]:
            return f"搜索失败: {result.get('error', '未知错误')}"

        results = result.get("results", [])
        if not results:
            return "未找到相关信息"

        lines = [f"### 搜索结果: {query}", ""]

        for i, item in enumerate(results, 1):
            name = item.get("name", "无标题")
            url = item.get("url", "")
            snippet = item.get("snippet", "")
            date = item.get("date", "")

            # Use summary if snippet is empty
            content = snippet or item.get("summary", "")
            # Truncate content to save tokens
            if len(content) > 200:
                content = content[:200] + "..."

            date_str = f" - {date}" if date else ""
            lines.append(f"{i}. [{name}]({url}){date_str}: {content}")

        return "\n".join(lines)


# Singleton instance for convenience
_bocha_service: BochaService | None = None


def get_bocha_service() -> BochaService:
    """Get or create singleton BochaService instance.

    Returns:
        BochaService instance
    """
    global _bocha_service
    if _bocha_service is None:
        _bocha_service = BochaService()
    return _bocha_service
