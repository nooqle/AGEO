"""Brand-owned domain canonicalization for user-facing intelligence projections."""

from __future__ import annotations

import json
from typing import Any

from app.core.domain_normalization import domain_matches, normalize_domain
from app.models.entity import Entity


OFFICIAL_DOMAIN_ALIASES: dict[str, tuple[str, ...]] = {
    "li.auto": ("lixiang.com",),
    "lixiang.com": ("li.auto",),
}


def official_domains_for_entity(entity: Entity | None) -> list[str]:
    """Return brand-owned domains used for citation attribution."""

    if entity is None:
        return []
    domains: list[str] = []
    _append_domain(domains, getattr(entity, "domain", None))

    aliases = _entity_aliases(entity)
    for alias in aliases:
        if "." in alias or alias.startswith(("http://", "https://")):
            _append_domain(domains, alias)

    index = 0
    while index < len(domains):
        for alias in OFFICIAL_DOMAIN_ALIASES.get(domains[index], ()):
            _append_domain(domains, alias)
        index += 1
    return domains


def primary_official_domain(entity: Entity | None) -> str:
    domains = official_domains_for_entity(entity)
    return domains[0] if domains else ""


def domain_matches_official(domain: str | None, official_domains: list[str]) -> bool:
    return domain_matches(domain, official_domains)


def _append_domain(domains: list[str], value: Any) -> None:
    domain = normalize_domain(str(value or ""))
    if domain and domain not in domains:
        domains.append(domain)


def _entity_aliases(entity: Entity) -> list[str]:
    raw = getattr(entity, "aliases", None)
    if not raw:
        return []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if not isinstance(raw, str):
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return [item.strip() for item in raw.split(",") if item.strip()]
    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    return []
