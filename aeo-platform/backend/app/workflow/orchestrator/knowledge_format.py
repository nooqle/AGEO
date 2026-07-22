"""Knowledge result formatting helpers (P2 knife 2)."""

from __future__ import annotations

from typing import Any

from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _normalize_public_knowledge_text,
)

def _format_knowledge_lookup_match(match: dict[str, Any]) -> str:
    parts = [f"类型={match.get('source_type', 'unknown')}"]
    if match.get("platform"):
        parts.append(f"平台={_normalize_public_knowledge_text(match['platform'])}")
    if match.get("competitor_name"):
        parts.append(f"竞品={match['competitor_name']}")
    if match.get("domain"):
        parts.append(f"域名={match['domain']}")
    if match.get("question_text"):
        parts.append(
            f"问题={_compact_text(_normalize_public_knowledge_text(match['question_text']), 48)}"
        )
    snippet = _compact_text(_normalize_public_knowledge_text(match.get("snippet")), 120)
    title = _compact_text(_normalize_public_knowledge_text(match.get("title")), 48)
    return f"- {title}（{'，'.join(parts)}）: {snippet}"

def _format_knowledge_group(group: dict[str, Any]) -> str:
    sample_titles = list(group.get("sample_titles") or [])
    if not sample_titles:
        sample_titles = [
            item.get("title", "")
            for item in (group.get("sample_records") or [])[:2]
            if item.get("title")
        ]
    samples = "；".join(_compact_text(item, 32) for item in sample_titles[:2])
    sample_suffix = f"；样例={samples}" if samples else ""
    fetch_suffix = ""
    success_count = group.get("success_count")
    failure_count = group.get("failure_count")
    fetch_metrics: list[str] = []
    if isinstance(success_count, int) and isinstance(failure_count, int):
        fetch_metrics.extend([f"成功={success_count}", f"失败={failure_count}"])
    question_count = group.get("question_count")
    if isinstance(question_count, int):
        fetch_metrics.append(f"问题数={question_count}")
    platform_count = group.get("platform_count")
    if isinstance(platform_count, int):
        fetch_metrics.append(f"平台数={platform_count}")
    if fetch_metrics:
        fetch_suffix = "；" + "；".join(fetch_metrics)
    return (
        f"- {group.get('group_key', 'unknown')}：{group.get('count', 0)} 条"
        f"{fetch_suffix}；来源={','.join(group.get('source_types') or [])}{sample_suffix}"
    )

def _format_knowledge_comparison(item: dict[str, Any]) -> str:
    examples = [
        example.get("title", "")
        for example in (item.get("latest_examples") or [])[:1]
        if example.get("title")
    ]
    example_suffix = f"；最新样例={_compact_text(examples[0], 28)}" if examples else ""
    return (
        f"- {item.get('group_key', 'unknown')}：最新 {item.get('latest_count', 0)}，"
        f"上次 {item.get('previous_count', 0)}，变化 {item.get('delta', 0):+d}"
        f"{example_suffix}"
    )

