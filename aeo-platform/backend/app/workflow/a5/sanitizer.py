"""Sanitizers for user-facing A5 report copy."""

import re
from typing import Any

def _strip_bwvs_phrases(text: str) -> str:
    """Remove BWVS-forward phrasing from user-facing copy."""
    if not text:
        return text

    cleaned = text
    patterns = [
        r"[，,；; ]*品牌AI可见度指数（?BWVS）?[^，。；;\n]*",
        r"[，,；; ]*BWVS(?:综合)?(?:指数|得分|分数)?[:：]?\s*[0-9]+(?:\.[0-9]+)?[^，。；;\n]*",
        r"[，,；; ]*场景 BWVS vs 基线 BWVS[^，。；;\n]*",
        r"[，,；; ]*基线 BWVS[:：]?\s*[0-9]+(?:\.[0-9]+)?[^，。；;\n]*",
    ]
    for pattern in patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"[，,]{2,}", "，", cleaned)
    cleaned = re.sub(r"([。；])\1+", r"\1", cleaned)
    cleaned = re.sub(r"^\s*[，,；;]\s*", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or text


def _sanitize_user_facing_report(report_data: Any) -> Any:
    """Recursively sanitize BWVS-forward copy from report payload."""
    if isinstance(report_data, str):
        return _strip_bwvs_phrases(report_data)
    if isinstance(report_data, list):
        return [_sanitize_user_facing_report(item) for item in report_data]
    if isinstance(report_data, dict):
        return {key: _sanitize_user_facing_report(value) for key, value in report_data.items()}
    return report_data


def _normalize_report_data(report_data: dict[str, Any]) -> dict[str, Any]:
    """规范化 LLM 输出的报告数据，处理缺失字段。

    LLM 输出可能漏掉新增的 optional 字段，
    此函数确保所有字段都有安全的默认值。
    """
    # Required fields
    report_data.setdefault("executive_summary", "分析已完成。")
    report_data.setdefault("key_findings", [])
    report_data.setdefault("strengths", [])
    report_data.setdefault("weaknesses", [])
    report_data.setdefault("opportunities", [])
    report_data.setdefault("threats", [])

