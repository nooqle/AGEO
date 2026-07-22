"""Brand seed / site confidence / panorama intro helpers (P2 knife 3)."""

from __future__ import annotations

import re
from typing import Any, Mapping

from app.workflow.orchestrator.history_query import (
    _is_explicit_question_generation_only_request,
)
from app.workflow.orchestrator.run_context import _get_latest_user_message

def _build_panorama_step_intro(
    tool_name: str,
    tool_args: dict[str, Any],
    reply_text: str,
    state: Mapping[str, Any],
) -> str:
    if tool_name != "question_simulation":
        return ""
    if str(tool_args.get("mode") or "").strip().lower() != "baseline_dynamic":
        return ""

    existing_text = str(reply_text or "")
    latest_user_message = _get_latest_user_message(state)
    question_only = bool(
        tool_args.get("question_only")
        or state.get("question_generation_only")
        or _is_explicit_question_generation_only_request(latest_user_message)
    )
    if question_only:
        if any(
            marker in existing_text
            for marker in ("只生成问题", "只生成问题列表", "不会抓取", "不抓取")
        ):
            return ""
        topic_keywords = _normalize_tool_topic_keywords(tool_args.get("topic_keywords"))
        topic_label = "、".join(topic_keywords)
        brand_name = (
            str((state.get("brand_profile") or {}).get("brand_name") or "").strip()
            or str(state.get("brand_name") or "").strip()
        )
        focus_label = topic_label or brand_name or "当前主题"
        return (
            f"开始围绕「{focus_label}」生成全景问题列表。\n"
            "本次只生成问题，不会抓取平台回答，也不会生成品牌全景分析报告。"
        )

    if (
        "品牌全景分析" in existing_text
        and "第二步" in existing_text
        and "第三步" in existing_text
    ):
        return ""

    brand_name = (
        str((state.get("brand_profile") or {}).get("brand_name") or "").strip()
        or str(state.get("brand_name") or "").strip()
        or "该品牌"
    )
    return (
        f"开始运行{brand_name}的品牌全景分析。\n"
        "本次分析会分 3 步推进：\n"
        "1. 生成行业通用问题集\n"
        "2. 抓取 4 个 AI 平台对同一组问题的真实回答\n"
        "3. 汇总品牌提及、引用来源和风险信号，输出品牌全景分析报告\n"
        "现在先开始第 1 步：生成行业通用问题集。"
    )

def _extract_site_confidence_root_url(state: Mapping[str, Any]) -> str | None:
    latest_user_message = _get_latest_user_message(state)
    match = re.search(r"https?://[^\s，。；;、）)]+", latest_user_message)
    if match:
        return match.group(0).strip(" \"'“”‘’")

    candidates = [
        state.get("official_website"),
        (state.get("brand_profile") or {}).get("official_website"),
        (state.get("brand_profile") or {}).get("website"),
        (state.get("brand_profile") or {}).get("domain"),
    ]
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        if value.startswith(("http://", "https://")):
            return value
        return f"https://{value}"
    return None

def _is_site_confidence_request(state: Mapping[str, Any]) -> bool:
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return False
    normalized = re.sub(r"\s+", "", latest_user_message).lower()
    site_markers = (
        "官网",
        "官方网站",
        "officialwebsite",
        "siteconfidence",
        "aice",
        "9c",
    )
    evaluation_markers = (
        "ai友好",
        "友好度",
        "官网评估",
        "评估官网",
        "官网报告",
        "审核",
        "aice",
        "9c",
    )
    return any(marker in normalized for marker in site_markers) and any(
        marker in normalized for marker in evaluation_markers
    )

def _infer_brand_seed_candidate(state: Mapping[str, Any]) -> str | None:
    """Treat a bare brand-name turn as an implicit analysis seed, not an ambiguity."""

    if state.get("awaiting_user") or state.get("pending_confirmation"):
        return None
    if state.get("pending_table_intake"):
        return None
    if state.get("brand_profile") or state.get("brand_name") or state.get("entity_id"):
        return None
    if state.get("fetch_results") or state.get("report") or state.get("metrics"):
        return None

    latest_user_message = _get_latest_user_message(state).strip()
    if not latest_user_message or "\n" in latest_user_message:
        return None

    candidate = latest_user_message.strip(
        " \t\r\n,，。.!！？?：:；;、\"'“”‘’()（）[]【】<>《》"
    )
    if not candidate or len(candidate) > 24:
        return None
    if _looks_like_keyword_list(candidate):
        return None

    lowered = candidate.lower()
    intent_keywords = (
        "分析",
        "报告",
        "导出",
        "下载",
        "对比",
        "比较",
        "变化",
        "趋势",
        "抓取",
        "重抓",
        "重跑",
        "引用",
        "官网",
        "画像",
        "问题",
        "回答",
        "结果",
        "历史",
        "怎么",
        "如何",
        "为什么",
        "有没有",
        "是否",
        "查询",
        "监测",
        "fast",
        "full",
        "browser",
        "api",
    )
    if any(keyword in lowered for keyword in intent_keywords):
        return None

    return candidate

def _looks_like_keyword_list(value: str) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    parts = [part.strip() for part in re.split(r"[,，、;；|/]+", text) if part.strip()]
    return len(parts) >= 2

def _normalize_tool_topic_keywords(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_values = re.split(r"[,，、;；|/\n\t]+", value)
    elif isinstance(value, list):
        raw_values = []
        for item in value:
            if item is None:
                continue
            raw_values.extend(re.split(r"[,，、;；|/\n\t]+", str(item)))
    else:
        raw_values = []

    keywords: list[str] = []
    for raw in raw_values:
        keyword = " ".join(str(raw or "").strip().split())
        if keyword and keyword not in keywords:
            keywords.append(keyword)
    return keywords[:12]

def _has_persona_prerequisites(state: Mapping[str, Any]) -> bool:
    brand_profile = state.get("brand_profile")
    competitors = state.get("competitors")
    if not isinstance(brand_profile, dict) or not brand_profile.get("brand_name"):
        return False
    if not isinstance(competitors, list):
        return False
    return any(
        isinstance(item, dict) and str(item.get("name") or "").strip()
        for item in competitors
    )

def _resolve_brand_name_for_dependency_rebuild(
    state: Mapping[str, Any], tool_args: dict
) -> str:
    brand_profile = state.get("brand_profile") or {}
    candidates = (
        tool_args.get("brand_name"),
        brand_profile.get("brand_name") if isinstance(brand_profile, dict) else None,
        brand_profile.get("name") if isinstance(brand_profile, dict) else None,
        state.get("brand_name"),
    )
    for candidate in candidates:
        text = str(candidate or "").strip()
        if text:
            return text
    return ""

