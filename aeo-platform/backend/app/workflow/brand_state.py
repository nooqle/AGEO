"""Helpers for reconstructing minimal brand context from persisted state."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [_as_text(item) for item in value if _as_text(item)]
    if isinstance(value, (tuple, set)):
        return [_as_text(item) for item in value if _as_text(item)]
    text = _as_text(value)
    return [text] if text else []


def build_effective_brand_profile(
    state_values: Mapping[str, Any],
    *,
    entity_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the smallest useful brand profile for downstream prompt generation."""

    profile = dict(state_values.get("brand_profile") or {})
    entity_data = entity_data or {}

    brand_name = (
        _as_text(profile.get("brand_name"))
        or _as_text(profile.get("name"))
        or _as_text(state_values.get("brand_name"))
        or _as_text(entity_data.get("name"))
    )
    official_website = (
        _as_text(profile.get("official_website"))
        or _as_text(state_values.get("official_website"))
        or _as_text(entity_data.get("domain"))
    )
    industry = (
        _as_text(profile.get("industry"))
        or _as_text(state_values.get("industry_hint"))
        or _as_text(entity_data.get("industry"))
    )
    description = (
        _as_text(profile.get("description"))
        or _as_text(entity_data.get("description"))
    )
    core_products = _normalize_string_list(profile.get("core_products"))

    if brand_name:
        profile["brand_name"] = brand_name
    if official_website:
        profile["official_website"] = official_website
    if industry:
        profile["industry"] = industry
    if description:
        profile["description"] = description
    if core_products or "core_products" not in profile:
        profile["core_products"] = core_products

    if any(
        (
            profile.get("brand_name"),
            profile.get("official_website"),
            profile.get("industry"),
            profile.get("description"),
            profile.get("core_products"),
        )
    ):
        return profile
    return {}


def seed_effective_brand_profile(
    state_values: MutableMapping[str, Any],
    *,
    entity_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the effective minimal brand profile back into mutable state."""

    profile = build_effective_brand_profile(state_values, entity_data=entity_data)
    if not profile:
        return {}

    state_values["brand_profile"] = profile
    if not _as_text(state_values.get("brand_name")):
        state_values["brand_name"] = profile.get("brand_name") or None
    if not _as_text(state_values.get("official_website")):
        state_values["official_website"] = profile.get("official_website") or None
    if not _as_text(state_values.get("industry_hint")):
        state_values["industry_hint"] = profile.get("industry") or None
    return profile
