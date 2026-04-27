"""Deterministic URL/domain normalization utilities.

This module intentionally does not encode site ownership knowledge. Semantic
identity such as website name, owner, source type, and brand relation belongs in
domain memory records resolved by model/manual judgment.
"""

from __future__ import annotations

from app.core.utils import extract_domain

MOBILE_PREFIXES = {"m", "mip", "wap", "3g", "mobile", "touch"}


def normalize_domain(url_or_domain: str | None) -> str | None:
    """Extract a stable domain key for aggregation and memory lookup."""

    domain = extract_domain(str(url_or_domain or "")).strip().lower().rstrip(".")
    if not domain:
        return None
    labels = [label for label in domain.split(".") if label]
    if len(labels) >= 3 and labels[0] in MOBILE_PREFIXES:
        domain = ".".join(labels[1:])
    return domain or None


def domain_matches(domain: str | None, target_domains: list[str]) -> bool:
    """Return whether domain matches any target domain after normalization."""

    normalized = normalize_domain(domain)
    if not normalized:
        return False
    normalized_targets = [item for item in (normalize_domain(item) for item in target_domains) if item]
    return any(
        normalized == target or normalized.endswith(f".{target}")
        for target in normalized_targets
    )
