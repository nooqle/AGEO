"""Keyword extraction helpers for A5 analytics."""

from typing import Any

import logging

logger = logging.getLogger(__name__)

_DOMAIN_STOPWORDS = {
    "可以", "使用", "进行", "通过", "提供", "需要", "包括", "以及",
    "作为", "其中", "对于", "这个", "那个", "就是", "还是", "已经",
    "但是", "因为", "所以", "如果", "或者", "虽然", "然而", "不过",
    "一些", "一个", "一种", "之一", "方面", "情况", "方式", "功能",
    "相关", "目前", "同时",
}


def extract_keyword_analysis(
    fetch_results: list,
    brand_profile: dict,
    top_k: int = 60,
) -> dict[str, Any]:
    """Extract TF-IDF keywords from all fetch result answers.

    Uses jieba.analyse to extract keywords, then enriches each keyword
    with platform occurrence info and context snippets.

    Returns a dict with total_keywords, platforms, and keywords list.
    """
    try:
        import jieba.analyse
    except ImportError:
        logger.warning("[A5] jieba not installed, skipping keyword analysis")
        return {}

    brand_name = brand_profile.get("brand_name", "")
    brand_name_en = brand_profile.get("brand_name_en", "")
    # Lowercase brand names for filtering
    brand_names_lower = {brand_name.lower(), brand_name_en.lower()} - {""}

    # Collect all text per platform
    platform_texts: dict[str, list[str]] = {}
    # Also collect per-keyword platform and context info
    all_texts: list[tuple[str, str]] = []  # (platform, content)

    for result in fetch_results:
        for pr in result.get("platform_results", []):
            platform = pr.get("platform", "unknown")
            if not pr.get("success"):
                continue
            answer = pr.get("answer", {})
            content = (
                answer.get("content", "")
                if isinstance(answer, dict)
                else str(answer)
            )
            if not content or len(content) < 10:
                continue
            platform_texts.setdefault(platform, []).append(content)
            all_texts.append((platform, content))

    if not all_texts:
        return {}

    # Combine all text for TF-IDF extraction
    combined_text = "\n".join(text for _, text in all_texts)

    # Extract top keywords via TF-IDF
    raw_keywords = jieba.analyse.extract_tags(
        combined_text, topK=top_k * 2, withWeight=True
    )

    # Filter: remove single chars, pure digits, brand name itself, stopwords
    filtered: list[tuple[str, float]] = []
    for word, weight in raw_keywords:
        if len(word) < 2:
            continue
        if word.isdigit():
            continue
        if word.lower() in brand_names_lower:
            continue
        if word in _DOMAIN_STOPWORDS:
            continue
        filtered.append((word, weight))
        if len(filtered) >= top_k:
            break

    if not filtered:
        return {}

    # Normalize weights to 10-100
    max_weight = filtered[0][1] if filtered else 1.0
    min_weight = filtered[-1][1] if filtered else 0.0
    weight_range = max_weight - min_weight if max_weight > min_weight else 1.0

    # Build keyword entries with platform and context info
    all_platforms = sorted(platform_texts.keys())
    keywords_list: list[dict[str, Any]] = []

    for word, weight in filtered:
        # Normalize value to 10-100 (single keyword gets max value)
        if len(filtered) == 1:
            value = 100.0
        else:
            normalized = 10 + ((weight - min_weight) / weight_range) * 90
            value = round(min(100, max(10, normalized)), 1)

        # Find which platforms mention this keyword
        kw_platforms: list[str] = []
        for plat in all_platforms:
            for text in platform_texts.get(plat, []):
                if word in text:
                    kw_platforms.append(plat)
                    break

        # Extract up to 3 context snippets (30 chars before and after)
        contexts: list[dict[str, str]] = []
        for plat, text in all_texts:
            if len(contexts) >= 3:
                break
            idx = text.find(word)
            if idx == -1:
                continue
            start = max(0, idx - 30)
            end = min(len(text), idx + len(word) + 30)
            snippet = text[start:end]
            if start > 0:
                snippet = "..." + snippet
            if end < len(text):
                snippet = snippet + "..."
            contexts.append({"text": snippet, "platform": plat})

        keywords_list.append({
            "word": word,
            "value": value,
            "platforms": kw_platforms,
            "contexts": contexts,
        })

    return {
        "total_keywords": len(keywords_list),
        "platforms": all_platforms,
        "keywords": keywords_list,
    }
