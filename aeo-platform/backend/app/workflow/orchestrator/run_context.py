"""Run/session context helpers for orchestrator (P2 knife 1)."""

from __future__ import annotations

from typing import Any, Mapping

def _get_latest_user_message(state: Mapping[str, Any]) -> str:
    history = state.get("orchestrator_history") or []
    for item in reversed(history):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""



def parse_recipe_meta_from_mapping(scope: Any) -> dict[str, str | None]:
    """Extract visible recipe metadata from input_scope / dashboard-like dicts."""
    if not isinstance(scope, dict):
        return {"recipe_id": None, "recipe_name": None}
    rid = scope.get("recipe_id") or scope.get("recipeId")
    rname = scope.get("recipe_name") or scope.get("recipeName")
    return {
        "recipe_id": str(rid).strip() if rid not in (None, "") else None,
        "recipe_name": str(rname).strip() if rname not in (None, "") else None,
    }


def get_input_scope(state: Mapping[str, Any]) -> dict[str, Any]:
    raw = state.get("input_scope")
    return raw if isinstance(raw, dict) else {}


def get_recipe_meta_from_state(state: Mapping[str, Any]) -> dict[str, str | None]:
    return parse_recipe_meta_from_mapping(get_input_scope(state))
