"""Organization feature entitlement helpers."""

from __future__ import annotations

from typing import Any


FEATURE_AMWAYCHINA_CONSOLE = "amwaychina_console"

ALLOWED_ORGANIZATION_FEATURE_FLAGS = {
    FEATURE_AMWAYCHINA_CONSOLE,
}


def normalize_organization_feature_flags(value: Any) -> dict[str, bool]:
    if not isinstance(value, dict):
        return {}
    flags: dict[str, bool] = {}
    for key in ALLOWED_ORGANIZATION_FEATURE_FLAGS:
        flags[key] = bool(value.get(key))
    return flags


def organization_feature_enabled(value: Any, feature_key: str) -> bool:
    return bool(normalize_organization_feature_flags(value).get(feature_key))
