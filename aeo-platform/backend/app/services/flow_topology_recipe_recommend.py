"""Deterministic recipe recommendations with visible reasons (Wave C / 3b-2.2 v0).

No LLM, no silent apply, no black-box learning. Ranking uses:
- entity vs organization scope
- recent apply_recipe orchestration events
- structural similarity of topology (fetch platforms / removed edges)
- optional intent keyword match on name/description
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from app.workflow.topology_resolver import CANVAS_PLATFORM_IDS, platform_edge_id

# Scoring weights (absolute points; sorted descending)
W_ENTITY_SCOPE = 30
W_RECENT_APPLY_BASE = 15
W_APPLY_COUNT_UNIT = 10
W_APPLY_COUNT_CAP = 40
W_STRUCTURE_MAX = 25
W_INTENT_MATCH = 20
W_UPDATED_RECENCY_SOFT = 5  # tiny tie-break via updated_at presence only in caller

DEFAULT_LIMIT = 3
MAX_LIMIT = 5


def _as_dict(topology: Any) -> dict[str, Any]:
    return topology if isinstance(topology, dict) else {}


def topology_structure_signature(topology: Any) -> dict[str, Any]:
    """Stable, comparable structure for platform / edge gating."""
    doc = _as_dict(topology)
    removed = {
        str(x)
        for x in (doc.get("removedEdgeIds") or [])
        if isinstance(x, str) and x.strip()
    }
    fetch_removed = {
        platform_edge_id(p)
        for p in CANVAS_PLATFORM_IDS
        if platform_edge_id(p) in removed
    }
    enabled_platforms = sorted(
        p for p in CANVAS_PLATFORM_IDS if platform_edge_id(p) not in removed
    )
    custom = doc.get("customNodes") or []
    custom_count = len(custom) if isinstance(custom, list) else 0
    return {
        "enabled_platforms": enabled_platforms,
        "fetch_removed": sorted(fetch_removed),
        "custom_node_count": custom_count,
    }


def structure_similarity_score(
    current: dict[str, Any], candidate: dict[str, Any]
) -> tuple[float, str | None]:
    """Jaccard on enabled platform sets → [0, W_STRUCTURE_MAX] + reason."""
    cur = set(current.get("enabled_platforms") or [])
    cand = set(candidate.get("enabled_platforms") or [])
    if not cur and not cand:
        return 0.0, None
    union = cur | cand
    inter = cur & cand
    if not union:
        return 0.0, None
    jaccard = len(inter) / len(union)
    points = round(jaccard * W_STRUCTURE_MAX, 2)
    if points <= 0:
        return 0.0, None
    if jaccard >= 0.99:
        reason = f"与当前生产线平台一致（{len(inter)} 平台）"
    elif jaccard >= 0.5:
        reason = f"与当前生产线结构相近（{len(inter)}/{len(union)} 平台重叠）"
    else:
        reason = f"部分平台重叠（{len(inter)}/{len(union)}）"
    return points, reason


def intent_match_score(
    intent: str | None, name: str, description: str | None
) -> tuple[float, str | None]:
    q = str(intent or "").strip().lower()
    if not q:
        return 0.0, None
    hay = f"{name or ''} {description or ''}".lower()
    # Prefer whole-phrase then token hits
    if q in hay:
        return float(W_INTENT_MATCH), f"与意图「{str(intent).strip()[:40]}」名称/描述匹配"
    tokens = [t for t in q.replace("，", " ").replace(",", " ").split() if len(t) >= 2]
    hits = [t for t in tokens if t in hay]
    if hits:
        return float(W_INTENT_MATCH * 0.7), f"意图关键词命中：{hits[0][:20]}"
    return 0.0, None


def score_recipe_candidate(
    *,
    recipe: dict[str, Any],
    current_sig: dict[str, Any],
    apply_counts: dict[str, int],
    last_applied_recipe_id: str | None,
    intent: str | None = None,
    active_recipe_id: str | None = None,
) -> dict[str, Any] | None:
    """
    Score one recipe. Returns None if it should be excluded from suggestions
    (e.g. already active and not dirty context — caller passes active id).
    """
    rid = str(recipe.get("id") or "")
    if not rid:
        return None
    if active_recipe_id and rid == str(active_recipe_id):
        # Already on this recipe — do not re-suggest
        return None

    reasons: list[str] = []
    score = 0.0

    scope = str(recipe.get("scope") or "")
    if recipe.get("entity_id") or scope == "entity":
        score += W_ENTITY_SCOPE
        reasons.append("品牌级配方")
    else:
        reasons.append("组织级配方")

    cnt = int(apply_counts.get(rid) or 0)
    if cnt > 0:
        apply_pts = min(W_APPLY_COUNT_CAP, cnt * W_APPLY_COUNT_UNIT)
        score += apply_pts
        reasons.append(f"本品牌曾套用 {cnt} 次")
    if last_applied_recipe_id and rid == str(last_applied_recipe_id):
        score += W_RECENT_APPLY_BASE
        reasons.append("最近一次套用过")

    cand_sig = topology_structure_signature(recipe.get("topology"))
    struct_pts, struct_reason = structure_similarity_score(current_sig, cand_sig)
    score += struct_pts
    if struct_reason:
        reasons.append(struct_reason)

    intent_pts, intent_reason = intent_match_score(
        intent,
        str(recipe.get("name") or ""),
        recipe.get("description") if isinstance(recipe.get("description"), str) else None,
    )
    score += intent_pts
    if intent_reason:
        reasons.append(intent_reason)

    # Ensure at least one concrete reason
    if not reasons:
        reasons.append("可见配方池候选")

    return {
        "recipe_id": rid,
        "name": str(recipe.get("name") or ""),
        "scope": "entity" if recipe.get("entity_id") else "organization",
        "description": recipe.get("description"),
        "version": int(recipe.get("version") or 1),
        "score": round(score, 2),
        "reasons": reasons,
    }


def rank_recommendations(
    *,
    recipes: list[dict[str, Any]],
    current_topology: dict[str, Any] | None,
    events: list[dict[str, Any]] | None = None,
    intent: str | None = None,
    active_recipe_id: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    """Pure ranking over already-serialized recipe dicts + event dicts."""
    lim = max(1, min(int(limit or DEFAULT_LIMIT), MAX_LIMIT))
    current_sig = topology_structure_signature(current_topology)

    apply_counts: dict[str, int] = {}
    last_applied: str | None = None
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if str(ev.get("event_type") or "") != "apply_recipe":
            continue
        payload = ev.get("payload") if isinstance(ev.get("payload"), dict) else {}
        rid = str(payload.get("recipe_id") or "").strip()
        if not rid:
            continue
        apply_counts[rid] = apply_counts.get(rid, 0) + 1
        if last_applied is None:
            last_applied = rid  # events assumed newest-first

    scored: list[dict[str, Any]] = []
    for r in recipes:
        if not isinstance(r, dict):
            continue
        item = score_recipe_candidate(
            recipe=r,
            current_sig=current_sig,
            apply_counts=apply_counts,
            last_applied_recipe_id=last_applied,
            intent=intent,
            active_recipe_id=active_recipe_id,
        )
        if item is not None and item["score"] > 0:
            scored.append(item)

    scored.sort(key=lambda x: (-float(x["score"]), str(x.get("name") or "")))
    return scored[:lim]


def build_recommendation_payload(
    items: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "recommendations": items,
        "engine": "deterministic_v0",
        "auto_applied": False,
    }
