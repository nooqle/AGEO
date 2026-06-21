"""Shared Amway association-circle dashboard variant helpers."""

from __future__ import annotations

from typing import Any


AMWAY_ASSOCIATION_DASHBOARD_VARIANT = "amway_association_circle"
BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE = "brand_association_circle"
BRAND_ASSOCIATION_CIRCLE_REPORT_KIND = "brand_association_circle"
AMWAY_ASSOCIATION_CENTER_TERMS = [
    "安利",
    "安利中国",
    "纽崔莱",
    "Amway China",
    "Nutrilite",
]
AMWAY_ASSOCIATION_ENABLED_SURFACES = [
    "dashboard",
    "chat",
    "canvas",
    "brand_world",
]

_AMWAY_ENTITY_ALIASES = {
    "安利",
    "安利中国",
    "纽崔莱",
    "amway",
    "amwaychina",
    "amway china",
    "nutrilite",
}
_AMWAY_DOMAIN_MARKERS = ("amway", "nutrilite")


def _normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _compact_identity(value: Any) -> str:
    return _normalize_text(value).replace(" ", "")


def is_amway_association_entity(
    *,
    name: Any = None,
    domain: Any = None,
    aliases: list[Any] | tuple[Any, ...] | None = None,
) -> bool:
    """Return whether an entity should receive the Amway circle dashboard variant."""

    candidates = [_normalize_text(name), _compact_identity(name)]
    for alias in aliases or []:
        candidates.extend([_normalize_text(alias), _compact_identity(alias)])
    if any(candidate in _AMWAY_ENTITY_ALIASES for candidate in candidates if candidate):
        return True

    normalized_domain = _normalize_text(domain)
    return any(marker in normalized_domain for marker in _AMWAY_DOMAIN_MARKERS)


def build_amway_association_context(
    *,
    name: Any = None,
    domain: Any = None,
    aliases: list[Any] | tuple[Any, ...] | None = None,
) -> dict[str, Any] | None:
    """Build the optional Dashboard context for the Amway association circle."""

    if not is_amway_association_entity(name=name, domain=domain, aliases=aliases):
        return None
    return {
        "dashboard_variant": AMWAY_ASSOCIATION_DASHBOARD_VARIANT,
        "analysis_mode": BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
        "report_kind": BRAND_ASSOCIATION_CIRCLE_REPORT_KIND,
        "center_terms": list(AMWAY_ASSOCIATION_CENTER_TERMS),
        "enabled_surfaces": list(AMWAY_ASSOCIATION_ENABLED_SURFACES),
    }
