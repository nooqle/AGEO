"""Domain memory lookup and synchronous model-backed resolution."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain_normalization import domain_matches, normalize_domain
from app.core.llm import get_llm_model
from app.models.domain_memory import BrandDomainRelation, DomainIdentityRecord

logger = logging.getLogger(__name__)

SOURCE_TYPES = {
    "official",
    "authority_media",
    "vertical_media",
    "community",
    "video_or_content",
    "other",
}
RELATION_TYPES = {
    "official",
    "official_channel",
    "third_party_channel",
    "media_reference",
    "unrelated",
    "unknown",
}


@dataclass(frozen=True)
class DomainResolution:
    canonical_domain: str | None
    display_name: str
    owner_name: str | None
    source_type: str
    site_category: str | None
    is_official: bool
    relation_type: str
    confidence: float | None
    status: str
    resolved_by: str | None


class DomainMemoryService:
    """Resolve citation domains through deterministic keys plus memory tables."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_citation_domain(
        self,
        *,
        url: str | None,
        raw_domain: str | None,
        title: str | None,
        snippet: str | None,
        site_name: str | None,
        brand_name: str,
        entity_id: str | None,
        official_domains: list[str],
        platform: str | None,
    ) -> DomainResolution:
        canonical_domain = normalize_domain(raw_domain or url)
        if not canonical_domain:
            return DomainResolution(
                canonical_domain=None,
                display_name=site_name or "N/A",
                owner_name=None,
                source_type="other",
                site_category=None,
                is_official=False,
                relation_type="unknown",
                confidence=None,
                status="missing_domain",
                resolved_by=None,
            )

        identity = await self._get_or_resolve_identity(
            canonical_domain=canonical_domain,
            url=url,
            title=title,
            snippet=snippet,
            site_name=site_name,
            platform=platform,
        )
        relation = await self._get_or_resolve_relation(
            canonical_domain=canonical_domain,
            brand_name=brand_name,
            entity_id=entity_id,
            official_domains=official_domains,
            url=url,
            title=title,
            snippet=snippet,
            platform=platform,
        )
        is_official = relation.relation_type == "official"
        source_type = "official" if is_official else (identity.source_type or "other")
        display_name = identity.display_name or site_name or canonical_domain
        status = "resolved" if identity.status in {"resolved", "manual"} else "unresolved"
        if relation.status in {"resolved", "manual"}:
            status = "resolved"
        elif relation.status == "unresolved":
            status = "unresolved"
        confidence_values = [
            value
            for value in (identity.confidence, relation.confidence)
            if isinstance(value, (int, float))
        ]
        confidence = max(confidence_values) if confidence_values else None
        return DomainResolution(
            canonical_domain=canonical_domain,
            display_name=display_name,
            owner_name=identity.owner_name,
            source_type=source_type,
            site_category=identity.site_category,
            is_official=is_official,
            relation_type=relation.relation_type,
            confidence=confidence,
            status=status,
            resolved_by=relation.resolved_by or identity.resolved_by,
        )

    async def _get_or_resolve_identity(
        self,
        *,
        canonical_domain: str,
        url: str | None,
        title: str | None,
        snippet: str | None,
        site_name: str | None,
        platform: str | None,
    ) -> DomainIdentityRecord:
        result = await self.db.execute(
            select(DomainIdentityRecord).where(
                DomainIdentityRecord.canonical_domain == canonical_domain
            )
        )
        record = result.scalar_one_or_none()
        if record:
            return record

        resolved = await self._resolve_identity_with_model(
            canonical_domain=canonical_domain,
            url=url,
            title=title,
            snippet=snippet,
            site_name=site_name,
            platform=platform,
        )
        now = datetime.now(timezone.utc)
        record = DomainIdentityRecord(
            canonical_domain=canonical_domain,
            display_name=resolved["display_name"],
            owner_name=resolved.get("owner_name"),
            source_type=resolved["source_type"],
            site_category=resolved.get("site_category"),
            confidence=resolved["confidence"],
            status=resolved["status"],
            resolved_by=resolved["resolved_by"],
            evidence_payload={
                "url": url,
                "title": title,
                "snippet": snippet,
                "site_name": site_name,
                "platform": platform,
                "model_reason": resolved.get("reason"),
            },
            notes=resolved.get("error"),
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _get_or_resolve_relation(
        self,
        *,
        canonical_domain: str,
        brand_name: str,
        entity_id: str | None,
        official_domains: list[str],
        url: str | None,
        title: str | None,
        snippet: str | None,
        platform: str | None,
    ) -> BrandDomainRelation:
        conditions = [
            BrandDomainRelation.canonical_domain == canonical_domain,
            BrandDomainRelation.brand_name == brand_name,
        ]
        if entity_id:
            conditions.append(
                or_(
                    BrandDomainRelation.entity_id == entity_id,
                    BrandDomainRelation.entity_id.is_(None),
                )
            )
        else:
            conditions.append(BrandDomainRelation.entity_id.is_(None))
        result = await self.db.execute(select(BrandDomainRelation).where(*conditions))
        record = result.scalars().first()
        if record:
            return record

        official = domain_matches(canonical_domain, official_domains)
        if official:
            resolved = {
                "relation_type": "official",
                "confidence": 0.99,
                "status": "resolved",
                "resolved_by": "deterministic_official_domain",
                "reason": "canonical domain matches brand official domain",
            }
        else:
            resolved = await self._resolve_relation_with_model(
                canonical_domain=canonical_domain,
                brand_name=brand_name,
                url=url,
                title=title,
                snippet=snippet,
                platform=platform,
            )
        now = datetime.now(timezone.utc)
        record = BrandDomainRelation(
            entity_id=entity_id,
            brand_name=brand_name,
            canonical_domain=canonical_domain,
            relation_type=resolved["relation_type"],
            confidence=resolved["confidence"],
            status=resolved["status"],
            resolved_by=resolved["resolved_by"],
            evidence_payload={
                "url": url,
                "title": title,
                "snippet": snippet,
                "platform": platform,
                "official_domains": official_domains,
                "model_reason": resolved.get("reason"),
            },
            notes=resolved.get("error"),
            created_at=now,
            updated_at=now,
        )
        self.db.add(record)
        await self.db.flush()
        return record

    async def _resolve_identity_with_model(
        self,
        *,
        canonical_domain: str,
        url: str | None,
        title: str | None,
        snippet: str | None,
        site_name: str | None,
        platform: str | None,
    ) -> dict[str, object]:
        fallback = {
            "display_name": site_name or canonical_domain,
            "owner_name": None,
            "source_type": "other",
            "site_category": None,
            "confidence": 0.1,
            "status": "unresolved",
            "resolved_by": "llm_failed_fallback",
        }
        prompt = {
            "task": "识别引用来源域名的网站身份。只返回 JSON，不要解释。",
            "schema": {
                "display_name": "网站中文名或通用名",
                "owner_name": "归属主体，可为空",
                "source_type": "official|authority_media|vertical_media|community|video_or_content|other",
                "site_category": "更细分类，可为空",
                "confidence": "0 到 1",
                "reason": "一句话判断依据",
            },
            "domain": canonical_domain,
            "url": url,
            "title": title,
            "snippet": snippet,
            "site_name_from_fetcher": site_name,
            "platform": platform,
        }
        try:
            response = await get_llm_model().async_call(
                messages=[
                    {
                        "role": "system",
                        "content": "你是引用来源域名归属识别器。必须输出严格 JSON。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt, ensure_ascii=False),
                    },
                ],
                temperature=0,
                max_tokens=500,
            )
            data = _parse_json_object(response.content)
            source_type = str(data.get("source_type") or "other")
            if source_type not in SOURCE_TYPES:
                source_type = "other"
            return {
                "display_name": str(data.get("display_name") or site_name or canonical_domain).strip(),
                "owner_name": _optional_text(data.get("owner_name")),
                "source_type": source_type,
                "site_category": _optional_text(data.get("site_category")),
                "confidence": _coerce_confidence(data.get("confidence"), default=0.5),
                "status": "resolved",
                "resolved_by": "llm",
                "reason": _optional_text(data.get("reason")),
            }
        except Exception as exc:
            logger.warning("Domain identity LLM resolution failed for %s: %s", canonical_domain, exc)
            fallback["error"] = str(exc)
            return fallback

    async def _resolve_relation_with_model(
        self,
        *,
        canonical_domain: str,
        brand_name: str,
        url: str | None,
        title: str | None,
        snippet: str | None,
        platform: str | None,
    ) -> dict[str, object]:
        fallback = {
            "relation_type": "unknown",
            "confidence": 0.1,
            "status": "unresolved",
            "resolved_by": "llm_failed_fallback",
        }
        prompt = {
            "task": "判断引用域名与当前品牌的关系。只返回 JSON，不要解释。",
            "schema": {
                "relation_type": "official|official_channel|third_party_channel|media_reference|unrelated|unknown",
                "confidence": "0 到 1",
                "reason": "一句话判断依据",
            },
            "brand_name": brand_name,
            "domain": canonical_domain,
            "url": url,
            "title": title,
            "snippet": snippet,
            "platform": platform,
        }
        try:
            response = await get_llm_model().async_call(
                messages=[
                    {
                        "role": "system",
                        "content": "你是品牌与引用来源关系识别器。必须输出严格 JSON。",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(prompt, ensure_ascii=False),
                    },
                ],
                temperature=0,
                max_tokens=400,
            )
            data = _parse_json_object(response.content)
            relation_type = str(data.get("relation_type") or "unknown")
            if relation_type not in RELATION_TYPES:
                relation_type = "unknown"
            return {
                "relation_type": relation_type,
                "confidence": _coerce_confidence(data.get("confidence"), default=0.5),
                "status": "resolved",
                "resolved_by": "llm",
                "reason": _optional_text(data.get("reason")),
            }
        except Exception as exc:
            logger.warning(
                "Brand-domain relation LLM resolution failed for %s/%s: %s",
                brand_name,
                canonical_domain,
                exc,
            )
            fallback["error"] = str(exc)
            return fallback


def _parse_json_object(content: str) -> dict[str, object]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("LLM response is not a JSON object")
    return data


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _coerce_confidence(value: object, *, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, number))
