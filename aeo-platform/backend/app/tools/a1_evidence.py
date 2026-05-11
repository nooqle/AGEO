"""A1 web-search evidence helpers."""

from typing import Any


A1_WEB_SEARCH_PROMPT = (
    "你是品牌档案核验助手。请从网络搜索{search_result}中提取可用于核验品牌档案、"
    "官网、核心产品、竞品与竞品官网的证据。回答时必须保留来源标题、链接、媒体、"
    "发布日期和 refer；不要编造搜索结果以外的链接。"
)


def build_a1_web_search_tool() -> dict[str, Any]:
    """Build the GLM Web Search in Chat tool for A1 brand discovery."""

    return {
        "type": "web_search",
        "web_search": {
            "enable": True,
            "search_engine": "search_pro",
            "search_result": True,
            "search_prompt": A1_WEB_SEARCH_PROMPT,
            "count": 10,
            "search_recency_filter": "noLimit",
            "content_size": "high",
        },
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_evidence_sources(value: Any, *, limit: int = 12) -> list[dict[str, str]]:
    """Normalize model-returned A1 evidence sources for artifact persistence."""

    if not isinstance(value, list):
        return []

    sources: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue

        title = _clean_text(
            item.get("title")
            or item.get("source_title")
            or item.get("name")
        )
        link = _clean_text(
            item.get("link")
            or item.get("url")
            or item.get("source_url")
        )
        if not title and not link:
            continue

        sources.append(
            {
                "title": title or link,
                "link": link,
                "media": _clean_text(item.get("media") or item.get("site_name")),
                "publish_date": _clean_text(
                    item.get("publish_date") or item.get("published_at")
                ),
                "refer": _clean_text(item.get("refer") or item.get("ref")),
                "usage": _clean_text(
                    item.get("usage")
                    or item.get("supports")
                    or item.get("evidence_for")
                ),
            }
        )
        if len(sources) >= limit:
            break

    return sources
