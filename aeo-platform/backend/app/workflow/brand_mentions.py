"""Helpers for robust brand mention detection across workflow stages."""

from __future__ import annotations

import re
from typing import Any

_CHINESE_SUFFIXES = (
    "汽车",
    "品牌",
    "集团",
    "科技",
    "股份",
    "有限公司",
    "公司",
)


def _clean_alias(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text


def _strip_parenthetical(text: str) -> str:
    return re.sub(r"[\(\[（【].*?[\)\]）】]", "", text).strip()


def _expand_brand_name(name: str) -> list[str]:
    if not name:
        return []
    aliases = [name]
    for suffix in _CHINESE_SUFFIXES:
        if name.endswith(suffix):
            stripped = name[: -len(suffix)].strip()
            if len(stripped) >= 2:
                aliases.append(stripped)
    if " " in name:
        first = name.split(" ", 1)[0].strip()
        if len(first) >= 2:
            aliases.append(first)
    return aliases


def extract_brand_aliases(brand_profile: dict[str, Any]) -> list[str]:
    """Build conservative but useful aliases for brand mention detection."""
    aliases: list[str] = []

    brand_name = _clean_alias(brand_profile.get("brand_name"))
    brand_name_en = _clean_alias(brand_profile.get("brand_name_en"))
    aliases.extend(_expand_brand_name(brand_name))
    aliases.extend(_expand_brand_name(brand_name_en))

    for product in brand_profile.get("core_products", []) or []:
        cleaned = _clean_alias(product)
        if not cleaned:
            continue
        aliases.append(cleaned)
        stripped = _strip_parenthetical(cleaned)
        if stripped and stripped != cleaned:
            aliases.append(stripped)

    for keyword in brand_profile.get("brand_keywords", []) or []:
        cleaned = _clean_alias(keyword)
        if not cleaned:
            continue
        # Keep only distinctive brand-owned keywords, avoid generic phrases.
        if (
            brand_name and brand_name.replace("汽车", "") in cleaned
        ) or (
            brand_name_en and brand_name_en.split(" ", 1)[0].lower() in cleaned.lower()
        ) or re.fullmatch(r"[A-Z0-9\-]{3,12}", cleaned):
            aliases.append(cleaned)

    deduped: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        normalized = alias.lower()
        if len(alias) < 2 or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(alias)
    return deduped


def content_mentions_brand(content: str, brand_profile: dict[str, Any]) -> bool:
    """Return True when content contains any accepted brand/product alias."""
    if not content:
        return False
    lowered = content.lower()
    return any(alias.lower() in lowered for alias in extract_brand_aliases(brand_profile))
