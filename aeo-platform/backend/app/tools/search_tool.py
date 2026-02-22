"""Web Search Tool for Agent Function Calling.

This module provides the web_search tool that allows agents to search
real-time information from the internet using Bocha API.
"""

from app.services.bocha_service import get_bocha_service

# OpenAI Function Calling compatible schema for web_search
WEB_SEARCH_SCHEMA = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": (
            "Search the internet for real-time information. "
            "Use this tool when you need to find current information, "
            "verify facts, or get the latest news about a topic. "
            "The tool returns search results with titles, URLs, and snippets."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query. Be specific and concise. "
                        "For best results, use keywords rather than full sentences."
                    ),
                },
                "count": {
                    "type": "integer",
                    "description": "Number of results to return (1-10). Default is 5.",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


def execute_search(query: str, count: int = 5) -> str:
    """Execute web search and return formatted results.

    This function is called by the agent when it decides to use the web_search tool.
    It searches the internet using Bocha API and returns results in a compact
    Markdown format suitable for LLM consumption.

    Args:
        query: Search query string
        count: Number of results to return (1-10)

    Returns:
        Markdown formatted search results or error message
    """
    try:
        service = get_bocha_service()
        return service.search_to_markdown(
            query=query,
            count=min(max(1, count), 10),  # Clamp between 1-10
            freshness="noLimit",
        )
    except Exception as e:
        # Return graceful error message
        return f"搜索服务暂时不可用: {str(e)}\n" "请基于已有知识回答问题。"


def format_search_results_for_llm(results: list[dict]) -> str:
    """Format search results into a compact string for LLM.

    Args:
        results: List of search result dictionaries

    Returns:
        Compact formatted string
    """
    if not results:
        return "未找到相关信息"

    lines = []
    for i, item in enumerate(results[:5], 1):  # Limit to 5 results
        name = item.get("name", "无标题")
        url = item.get("url", "")
        snippet = item.get("snippet", "")
        date = item.get("date", "")

        # Truncate snippet to save tokens
        if len(snippet) > 150:
            snippet = snippet[:150] + "..."

        date_str = f" [{date}]" if date else ""
        lines.append(f"{i}. {name}{date_str}\n   URL: {url}\n   {snippet}")

    return "\n\n".join(lines)
