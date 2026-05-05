from __future__ import annotations

from typing import Any, Mapping

from app.tools.a4_fetch_agent import normalize_public_platform_id


_SUPPLEMENTAL_FETCH_KEYWORDS = (
    "补采",
    "补充采集",
    "失败的平台",
    "失败的问题",
    "只采集没成功的",
    "成功的就跳过",
    "失败题目",
    "失败题",
)

_BROWSER_FETCH_KEYWORDS = (
    "浏览器",
    "全浏览器",
    "full",
    "完整采集",
    "完整重抓",
)

_FAST_FETCH_KEYWORDS = (
    "fast",
    "quick",
    "快速",
    "快采",
    "快速采集",
    "快速监测",
)


def normalize_fetch_mode(value: Any) -> str | None:
    candidate = str(value or "").strip().lower()
    if candidate in {"fast", "full"}:
        return candidate
    return None


def resolve_supplemental_fetch_mode(
    state: Mapping[str, Any],
    plan: Mapping[str, Any] | None = None,
) -> str:
    """Resolve retry mode from the failed A4 run, defaulting to A4's fast mode."""

    for source in (
        state.get("fetch_mode"),
        (plan or {}).get("fetch_mode"),
    ):
        mode = normalize_fetch_mode(source)
        if mode:
            return mode
    return "fast"


def extract_base_fetch_results_from_state(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return the latest canonical A4 matrix available for supplemental merge."""

    direct_results = state.get("fetch_results")
    if isinstance(direct_results, list) and direct_results:
        return [item for item in direct_results if isinstance(item, dict)]

    canonical = state.get("a4_canonical_result")
    if isinstance(canonical, Mapping):
        canonical_results = canonical.get("fetch_results")
        if isinstance(canonical_results, list) and canonical_results:
            return [item for item in canonical_results if isinstance(item, dict)]

    return []


def canonicalize_fetch_platform(value: Any) -> str:
    normalized = normalize_public_platform_id(value)
    if normalized:
        return normalized
    return str(value or "").strip().lower()


def normalize_question_targets(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    targets: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in value:
        if not isinstance(item, Mapping):
            continue
        question_id = str(item.get("question_id") or item.get("id") or "").strip()
        question_text = str(item.get("question_text") or item.get("text") or "").strip()
        if not question_id or not question_text or question_id in seen_ids:
            continue
        platforms: list[str] = []
        seen_platforms: set[str] = set()
        for raw_platform in item.get("platforms") or []:
            platform = canonicalize_fetch_platform(raw_platform)
            if not platform or platform in seen_platforms:
                continue
            platforms.append(platform)
            seen_platforms.add(platform)
        if not platforms:
            continue
        targets.append(
            {
                "question_id": question_id,
                "question_text": question_text,
                "platforms": platforms,
            }
        )
        seen_ids.add(question_id)
    return targets


def build_failed_question_targets(
    fetch_results: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    for item in fetch_results or []:
        if not isinstance(item, Mapping):
            continue
        question_id = str(item.get("question_id") or "").strip()
        question_text = str(item.get("question_text") or "").strip()
        if not question_id or not question_text:
            continue
        failed_platforms: list[str] = []
        seen_platforms: set[str] = set()
        for result in item.get("platform_results") or []:
            if not isinstance(result, Mapping):
                continue
            platform = canonicalize_fetch_platform(result.get("platform"))
            if not platform or platform in seen_platforms:
                continue
            if bool(result.get("success")):
                continue
            failed_platforms.append(platform)
            seen_platforms.add(platform)
        if failed_platforms:
            targets.append(
                {
                    "question_id": question_id,
                    "question_text": question_text,
                    "platforms": failed_platforms,
                }
            )
    return targets


def build_fetch_recovery_plan(
    fetch_results: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    platform_breakdown: dict[str, dict[str, Any]] = {}
    success_count = 0
    failure_count = 0

    for item in fetch_results or []:
        if not isinstance(item, Mapping):
            continue
        for result in item.get("platform_results") or []:
            if not isinstance(result, Mapping):
                continue
            platform = canonicalize_fetch_platform(result.get("platform"))
            if not platform:
                continue
            row = platform_breakdown.setdefault(
                platform,
                {
                    "platform": platform,
                    "success_count": 0,
                    "failure_count": 0,
                    "total_count": 0,
                },
            )
            row["total_count"] += 1
            if bool(result.get("success")):
                row["success_count"] += 1
                success_count += 1
            else:
                row["failure_count"] += 1
                failure_count += 1

    total_count = success_count + failure_count
    question_targets = build_failed_question_targets(fetch_results)
    if total_count <= 0 and not question_targets:
        return None

    failed_platforms = sorted(
        {
            platform
            for target in question_targets
            for platform in target.get("platforms") or []
        }
    )
    return {
        "question_targets": question_targets,
        "platforms": failed_platforms,
        "success_count": success_count,
        "failure_count": failure_count,
        "total_count": total_count,
        "success_rate": (success_count / total_count) if total_count else 0.0,
        "failed_question_count": len(question_targets),
        "failed_platform_count": len(failed_platforms),
        "platform_breakdown": sorted(
            platform_breakdown.values(),
            key=lambda item: (-int(item["failure_count"]), item["platform"]),
        ),
    }


def extract_latest_fetch_recovery_plan_from_state(
    state: Mapping[str, Any],
) -> dict[str, Any] | None:
    current_plan = state.get("fetch_recovery_plan")
    if (
        isinstance(current_plan, Mapping)
        and int(current_plan.get("failure_count") or 0) > 0
    ):
        return {
            "question_targets": normalize_question_targets(
                current_plan.get("question_targets")
            ),
            "platforms": list(current_plan.get("platforms") or []),
            "success_count": int(current_plan.get("success_count") or 0),
            "failure_count": int(current_plan.get("failure_count") or 0),
            "total_count": int(current_plan.get("total_count") or 0),
            "success_rate": float(current_plan.get("success_rate") or 0.0),
            "failed_question_count": int(
                current_plan.get("failed_question_count") or 0
            ),
            "failed_platform_count": int(
                current_plan.get("failed_platform_count") or 0
            ),
            "platform_breakdown": list(current_plan.get("platform_breakdown") or []),
            "task_id": str(current_plan.get("task_id") or "").strip() or None,
            "fetch_mode": normalize_fetch_mode(
                current_plan.get("fetch_mode") or state.get("fetch_mode")
            ),
        }

    current_fetch_results = state.get("fetch_results")
    if isinstance(current_fetch_results, list):
        plan = build_fetch_recovery_plan(current_fetch_results)
        if plan and plan.get("failure_count", 0) > 0:
            manifest = state.get("knowledge_manifest") or {}
            latest_fetch = (manifest.get("history") or {}).get("latest_fetch") or {}
            task_id = str(
                latest_fetch.get("task_id") or state.get("task_id") or ""
            ).strip()
            if task_id:
                plan["task_id"] = task_id
            plan["fetch_mode"] = normalize_fetch_mode(state.get("fetch_mode"))
            return plan

    manifest = state.get("knowledge_manifest") or {}
    latest_fetch = (manifest.get("history") or {}).get("latest_fetch") or {}
    question_targets = normalize_question_targets(
        latest_fetch.get("failed_question_targets")
        or latest_fetch.get("question_targets")
    )
    if not question_targets:
        return None

    failure_count = int(latest_fetch.get("failure_count") or 0)
    if failure_count <= 0:
        return None

    platforms = sorted(
        {
            platform
            for target in question_targets
            for platform in target.get("platforms") or []
        }
    )
    return {
        "question_targets": question_targets,
        "platforms": platforms,
        "success_count": int(latest_fetch.get("success_count") or 0),
        "failure_count": failure_count,
        "total_count": int(latest_fetch.get("total_count") or 0),
        "success_rate": float(latest_fetch.get("success_rate") or 0.0),
        "failed_question_count": int(
            latest_fetch.get("failed_question_count") or len(question_targets)
        ),
        "failed_platform_count": int(
            latest_fetch.get("failed_platform_count") or len(platforms)
        ),
        "platform_breakdown": list(latest_fetch.get("platform_breakdown") or []),
        "task_id": str(latest_fetch.get("task_id") or "").strip() or None,
        "fetch_mode": normalize_fetch_mode(
            latest_fetch.get("fetch_mode") or state.get("fetch_mode")
        ),
    }


def is_supplemental_fetch_request(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in _SUPPLEMENTAL_FETCH_KEYWORDS)


def prefers_browser_fetch_mode(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in _BROWSER_FETCH_KEYWORDS)


def prefers_fast_fetch_mode(text: str) -> bool:
    lowered = str(text or "").strip().lower()
    if not lowered:
        return False
    return any(keyword in lowered for keyword in _FAST_FETCH_KEYWORDS)


def resolve_explicit_fetch_mode_from_text(text: str) -> str | None:
    """Resolve an explicit user-selected fetch mode from natural language."""

    if prefers_browser_fetch_mode(text):
        return "full"
    if prefers_fast_fetch_mode(text):
        return "fast"
    return None
