"""Pure text/normalization helpers for orchestrator (P2 knife 1)."""

from __future__ import annotations

import re
from typing import Any

def _normalize_public_report_kind(value: Any) -> str:
    """Normalize external report kind names to canonical panorama/scenario."""
    raw = str(value or "").strip().lower()
    if raw in {"baseline", "panorama"}:
        return "panorama"
    if raw in {"persona", "scenario"}:
        return "scenario"
    return "scenario"

def _normalize_internal_analysis_mode(value: Any) -> str:
    """Keep workflow state compatible while public APIs move to canonical terms."""
    return (
        "baseline" if _normalize_public_report_kind(value) == "panorama" else "persona"
    )

def _compact_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"

def _normalize_public_knowledge_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = re.sub(r"\[\]\(@mark_[^)]+\)", "", text)
    text = re.sub(r"\bhunyuan\b", "元宝", text, flags=re.IGNORECASE)
    return " ".join(text.split())

def _extract_exact_datetime_scope_text(text: str) -> str | None:
    match = re.search(
        r"(\d{4}[-/年]\d{1,2}[-/月]\d{1,2}(?:日)?\s+\d{1,2}:\d{2}(?::\d{2})?)",
        str(text or ""),
    )
    if not match:
        return None
    return match.group(1).replace("年", "-").replace("月", "-").replace("日", "")

def _contains_non_negated_keyword(text: str, keywords: list[str]) -> bool:
    normalized = str(text or "")
    negative_prefixes = ("不要", "别", "不需要", "无需", "不是")
    for keyword in keywords:
        if keyword not in normalized:
            continue
        if any(f"{prefix}{keyword}" in normalized for prefix in negative_prefixes):
            continue
        return True
    return False

def _is_english_dominant_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    ascii_letters = sum(1 for ch in stripped if ch.isascii() and ch.isalpha())
    cjk_chars = sum(1 for ch in stripped if "\u4e00" <= ch <= "\u9fff")
    if ascii_letters >= 8 and cjk_chars == 0:
        return True
    return ascii_letters >= 12 and ascii_letters > max(1, cjk_chars * 2)

