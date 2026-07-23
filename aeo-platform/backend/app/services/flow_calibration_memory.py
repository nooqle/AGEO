"""Visible calibration memory helpers (Wave P).

Pure functions: turn orchestration events + run/topology lessons into
recommend scores/reasons and compile-time visible_memory blocks.

No silent topology mutation. No black-box learning.
"""

from __future__ import annotations

from typing import Any

from app.workflow.topology_resolver import CANVAS_PLATFORM_IDS, platform_edge_id

W_LESSON_ALIGN = 18
W_PATCH_SIGNAL = 6
MAX_REASON_LESSONS = 2
MAX_MEMORY_EVENTS = 5
MAX_MEMORY_LESSONS = 4
MAX_MEMORY_CHARS = 600


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def skipped_platforms_from_lessons(lessons: list[dict[str, Any]] | None) -> list[str]:
    """Platforms currently gated / recently skipped (from lesson node_ids)."""
    out: list[str] = []
    seen: set[str] = set()
    for item in lessons or []:
        if not isinstance(item, dict):
            continue
        node_id = str(item.get("node_id") or "")
        kind = str(item.get("kind") or "")
        if not node_id.startswith("platform-"):
            continue
        if kind not in {
            "skipped_platform",
            "run_skipped_platform",
            "fetch_partial",
            "run_fetch_partial",
        } and "skip" not in kind:
            # still accept platform-* lessons that imply skip via source topology
            if str(item.get("source") or "") not in {"topology", "last_run"}:
                continue
        platform = node_id.removeprefix("platform-")
        if platform not in CANVAS_PLATFORM_IDS or platform in seen:
            continue
        seen.add(platform)
        out.append(platform)
    return out


def skipped_platforms_from_topology(topology: dict[str, Any] | None) -> list[str]:
    doc = _as_dict(topology)
    removed = {
        str(x)
        for x in (doc.get("removedEdgeIds") or [])
        if isinstance(x, str) and x.strip()
    }
    return [
        p
        for p in CANVAS_PLATFORM_IDS
        if platform_edge_id(p) in removed
    ]


def recipe_enabled_platforms(topology: dict[str, Any] | None) -> set[str]:
    doc = _as_dict(topology)
    removed = {
        str(x)
        for x in (doc.get("removedEdgeIds") or [])
        if isinstance(x, str) and x.strip()
    }
    return {
        p
        for p in CANVAS_PLATFORM_IDS
        if platform_edge_id(p) not in removed
    }


def lesson_alignment_for_recipe(
    *,
    recipe_topology: dict[str, Any] | None,
    lessons: list[dict[str, Any]] | None,
    current_topology: dict[str, Any] | None = None,
) -> tuple[float, list[str]]:
    """Boost recipes that match skip lessons / current gated platforms."""
    skipped = set(skipped_platforms_from_lessons(lessons))
    if not skipped:
        skipped = set(skipped_platforms_from_topology(current_topology))
    if not skipped:
        return 0.0, []

    enabled = recipe_enabled_platforms(recipe_topology)
    # Recipe aligns if it also disables the skipped platforms
    aligned = sorted(p for p in skipped if p not in enabled)
    if not aligned:
        return 0.0, []

    labels = {
        "deepseek": "DeepSeek",
        "kimi": "Kimi",
        "doubao": "豆包",
        "hunyuan": "腾讯元宝",
    }
    names = "、".join(labels.get(p, p) for p in aligned[:3])
    pts = min(W_LESSON_ALIGN, 6.0 * len(aligned))
    reasons = [f"与近期教训一致：跳过{names}"]
    # Optional headline echo (cap)
    for item in lessons or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("source") or "") not in {"topology", "last_run"}:
            continue
        headline = str(item.get("headline") or "").strip()
        if headline and len(reasons) < MAX_REASON_LESSONS + 1:
            # keep one short echo only if different
            short = headline if len(headline) <= 48 else headline[:47] + "…"
            if short not in reasons:
                reasons.append(f"依据：{short}")
                break
    return pts, reasons[: MAX_REASON_LESSONS + 1]


def patch_event_soft_signals(events: list[dict[str, Any]] | None) -> tuple[float, list[str]]:
    """Soft points from recent apply_patch (not recipe-specific)."""
    reasons: list[str] = []
    count = 0
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("event_type") or "") != "apply_patch":
            continue
        count += 1
        if len(reasons) < 1:
            summary = str(ev.get("summary") or "").strip()
            if summary:
                reasons.append(f"近期改图：{summary[:40]}")
            else:
                reasons.append("近期有拓扑编排变更")
        if count >= 3:
            break
    if count <= 0:
        return 0.0, []
    return float(min(W_PATCH_SIGNAL, count * 2)), reasons


def build_calibration_meta(
    *,
    events: list[dict[str, Any]] | None,
    lessons: list[dict[str, Any]] | None,
    extra_signals: list[str] | None = None,
) -> dict[str, Any]:
    signals: list[str] = []
    apply_n = 0
    patch_n = 0
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        et = str(ev.get("event_type") or "")
        if et == "apply_recipe":
            apply_n += 1
        elif et == "apply_patch":
            patch_n += 1
    if apply_n:
        signals.append(f"apply_recipe×{apply_n}")
    if patch_n:
        signals.append(f"apply_patch×{patch_n}")
    for item in (lessons or [])[:6]:
        if not isinstance(item, dict):
            continue
        lid = str(item.get("id") or item.get("kind") or "").strip()
        if lid:
            signals.append(lid[:48])
    for s in extra_signals or []:
        if s and s not in signals:
            signals.append(s)
    return {
        "events_considered": len(events or []),
        "lessons_considered": len(lessons or []),
        "signals": signals[:12],
        "auto_applied": False,
    }


def build_visible_memory_block(
    *,
    events: list[dict[str, Any]] | None = None,
    lessons: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Trailing user-message memory for NL LLM compile (never system prompt)."""
    recent_changes: list[str] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        summary = str(ev.get("summary") or "").strip()
        if not summary:
            continue
        recent_changes.append(summary[:80])
        if len(recent_changes) >= MAX_MEMORY_EVENTS:
            break

    lesson_lines: list[str] = []
    for item in lessons or []:
        if not isinstance(item, dict):
            continue
        headline = str(item.get("headline") or "").strip()
        if not headline:
            continue
        lesson_lines.append(headline[:100])
        if len(lesson_lines) >= MAX_MEMORY_LESSONS:
            break

    # Soft char budget
    packed = "；".join(recent_changes + lesson_lines)
    if len(packed) > MAX_MEMORY_CHARS:
        # trim lessons first
        while lesson_lines and len("；".join(recent_changes + lesson_lines)) > MAX_MEMORY_CHARS:
            lesson_lines.pop()
        while recent_changes and len("；".join(recent_changes + lesson_lines)) > MAX_MEMORY_CHARS:
            recent_changes.pop()

    return {
        "recent_changes": recent_changes,
        "lessons": lesson_lines,
        "note": (
            "Hint only from visible orchestration memory. "
            "Never invent ops from memory alone; do not auto-apply; "
            "prefer the user instruction + current topology."
        ),
    }


def platforms_touched_from_ops(ops: list[Any] | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        platform = str(op.get("platform") or "").strip()
        if platform and platform not in seen:
            seen.add(platform)
            out.append(platform)
    return out


def ops_preview(ops: list[Any] | None, limit: int = 8) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for op in ops or []:
        if not isinstance(op, dict):
            continue
        entry: dict[str, Any] = {"op": str(op.get("op") or "")}
        if op.get("platform"):
            entry["platform"] = str(op.get("platform"))
        if op.get("node_id"):
            entry["node_id"] = str(op.get("node_id"))
        preview.append(entry)
        if len(preview) >= limit:
            break
    return preview
