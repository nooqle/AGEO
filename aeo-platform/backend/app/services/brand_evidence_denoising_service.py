"""Evidence denoising projections for the brand ontology Dashboard."""

from __future__ import annotations

import ipaddress
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.core.domain_normalization import domain_matches, normalize_domain
from app.models.brand_intelligence import (
    BrandCitationSource,
    BrandIntelligenceQuestion,
    BrandPlatformAnswer,
)
from app.models.entity import Entity
from app.services.brand_domain_canonicalization import official_domains_for_entity
from app.services.page_feature_service import fetch_page_features
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_CITATION_ROWS = 2000
MAX_SOURCE_DOMAINS = 8
MAX_EVIDENCE_CLUSTERS = 6
MAX_CLUSTER_SAMPLES = 3
MAX_OFFICIAL_SAMPLES = 4
MAX_OFFICIAL_COMPARISON_DOMAINS = 3

SOURCE_ROLE_LABELS: dict[str, str] = {
    "official_website": "官网资产",
    "news_media": "新闻媒体",
    "industry_vertical": "行业垂直站",
    "community": "社区讨论",
    "knowledge_base": "百科/资料库",
    "commerce_platform": "交易平台",
    "other": "其他来源",
}


@dataclass(frozen=True)
class CitationEvidenceRow:
    citation_id: str
    answer_id: str
    question_id: str
    question_text: str
    category: str
    platform: str
    url: str
    domain: str
    title: str
    snippet: str
    confidence: float | None
    created_at: datetime | None
    payload: dict[str, Any]


class BrandEvidenceDenoisingService:
    """Builds Dashboard-facing evidence clusters from raw citation leaves.

    Raw citation rows remain the traceable leaves. This service only derives a
    compact read model so users see business evidence before they see thousands
    of URLs.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build_summary(
        self,
        *,
        entity_id: UUID,
        include_content_audit: bool = True,
    ) -> dict[str, Any]:
        entity = await self.db.get(Entity, entity_id)
        rows = await self._load_citation_rows(entity_id=entity_id)
        official_domains = self._official_domains(entity)
        source_domains = self._source_domain_summary(
            rows=rows,
            official_domains=official_domains,
        )
        evidence_clusters = self._evidence_clusters(
            rows=rows,
            official_domains=official_domains,
        )
        official_observation = await self._official_website_observation(
            entity=entity,
            rows=rows,
            official_domains=official_domains,
            include_content_audit=include_content_audit,
        )
        return {
            "evidence_clusters": evidence_clusters,
            "source_domain_summary": source_domains,
            "official_website_observation": official_observation,
        }

    async def _load_citation_rows(
        self, *, entity_id: UUID
    ) -> list[CitationEvidenceRow]:
        result = await self.db.execute(
            select(BrandCitationSource, BrandPlatformAnswer, BrandIntelligenceQuestion)
            .join(
                BrandPlatformAnswer,
                BrandCitationSource.answer_id == BrandPlatformAnswer.id,
            )
            .outerjoin(
                BrandIntelligenceQuestion,
                BrandPlatformAnswer.question_object_id == BrandIntelligenceQuestion.id,
            )
            .where(BrandCitationSource.entity_id == entity_id)
            .order_by(desc(BrandCitationSource.created_at))
            .limit(MAX_CITATION_ROWS)
        )
        rows: list[CitationEvidenceRow] = []
        for citation, answer, question in result.all():
            payload = citation.citation_payload
            if not isinstance(payload, dict):
                payload = {}
            domain = (
                normalize_domain(citation.domain)
                or normalize_domain(citation.url)
                or str(citation.domain or "").strip().lower()
            )
            rows.append(
                CitationEvidenceRow(
                    citation_id=str(citation.id),
                    answer_id=str(answer.id),
                    question_id=str(answer.question_id or ""),
                    question_text=str(
                        getattr(question, "question_text", "") or ""
                    ).strip(),
                    category=str(getattr(question, "category", "") or "").strip(),
                    platform=str(answer.platform or "").strip(),
                    url=str(citation.url or "").strip(),
                    domain=domain or "",
                    title=str(citation.source_title or "").strip(),
                    snippet=str(citation.snippet or "").strip(),
                    confidence=citation.confidence,
                    created_at=citation.created_at,
                    payload=payload,
                )
            )
        return rows

    def _source_domain_summary(
        self,
        *,
        rows: list[CitationEvidenceRow],
        official_domains: list[str],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[CitationEvidenceRow]] = defaultdict(list)
        for row in rows:
            if row.domain:
                grouped[row.domain].append(row)

        summaries: list[dict[str, Any]] = []
        for domain, items in grouped.items():
            role = self._source_role(items[0], official_domains=official_domains)
            title_counter = Counter(
                self._site_name(item) for item in items if self._site_name(item)
            )
            platform_count = len({item.platform for item in items if item.platform})
            answer_count = len({item.answer_id for item in items if item.answer_id})
            sample_titles = _unique_non_empty(
                [item.title or item.url or domain for item in items],
                limit=3,
            )
            summaries.append(
                {
                    "domain": domain,
                    "site_name": (
                        title_counter.most_common(1)[0][0] if title_counter else domain
                    ),
                    "source_role": role,
                    "source_role_label": SOURCE_ROLE_LABELS.get(role, "其他来源"),
                    "citation_count": len(items),
                    "answer_count": answer_count,
                    "platform_count": platform_count,
                    "is_official": self._is_official_domain(
                        domain,
                        official_domains=official_domains,
                    ),
                    "sample_titles": sample_titles,
                }
            )

        summaries.sort(
            key=lambda item: (
                not bool(item["is_official"]),
                -int(item["citation_count"]),
                str(item["domain"]),
            )
        )
        return summaries[:MAX_SOURCE_DOMAINS]

    def _evidence_clusters(
        self,
        *,
        rows: list[CitationEvidenceRow],
        official_domains: list[str],
    ) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str], list[CitationEvidenceRow]] = defaultdict(list)
        for row in rows:
            if not row.domain and not row.url and not row.title:
                continue
            topic_key, _topic_label = self._topic(row)
            source_role = self._source_role(row, official_domains=official_domains)
            grouped[(topic_key, source_role)].append(row)

        clusters: list[dict[str, Any]] = []
        for (topic_key, source_role), items in grouped.items():
            topic_label = self._topic_label(items)
            domains = _unique_non_empty([item.domain for item in items], limit=5)
            answer_count = len({item.answer_id for item in items if item.answer_id})
            question_count = len(
                {item.question_id for item in items if item.question_id}
            )
            official_count = sum(
                1
                for item in items
                if self._is_official_domain(
                    item.domain,
                    official_domains=official_domains,
                )
            )
            samples = self._sample_citations(
                rows=items,
                official_domains=official_domains,
                limit=MAX_CLUSTER_SAMPLES,
            )
            clusters.append(
                {
                    "cluster_id": f"{topic_key}:{source_role}",
                    "title": f"{topic_label} · {SOURCE_ROLE_LABELS.get(source_role, '其他来源')}",
                    "topic_key": topic_key,
                    "topic_label": topic_label,
                    "source_role": source_role,
                    "source_role_label": SOURCE_ROLE_LABELS.get(
                        source_role,
                        "其他来源",
                    ),
                    "citation_count": len(items),
                    "answer_count": answer_count,
                    "question_count": question_count,
                    "domain_count": len({item.domain for item in items if item.domain}),
                    "official_citation_count": official_count,
                    "source_domains": domains,
                    "samples": samples,
                    "business_readout": self._cluster_readout(
                        topic_label=topic_label,
                        source_role=source_role,
                        citation_count=len(items),
                        domain_count=len(domains),
                        official_count=official_count,
                    ),
                }
            )

        clusters.sort(
            key=lambda item: (
                0 if item["source_role"] == "official_website" else 1,
                1 if item["topic_label"] == "综合外部来源" else 0,
                -int(item["question_count"]),
                -int(item["answer_count"]),
                -int(item["citation_count"]),
                str(item["title"]),
            )
        )
        return clusters[:MAX_EVIDENCE_CLUSTERS]

    async def _official_website_observation(
        self,
        *,
        entity: Entity | None,
        rows: list[CitationEvidenceRow],
        official_domains: list[str],
        include_content_audit: bool,
    ) -> dict[str, Any]:
        domain = official_domains[0] if official_domains else ""
        total_citations = len(rows)
        unique_questions = {item.question_id for item in rows if item.question_id}
        unique_platforms = {item.platform for item in rows if item.platform}
        official_rows = [
            item
            for item in rows
            if self._is_official_domain(
                item.domain,
                official_domains=official_domains,
            )
        ]

        if not domain:
            return {
                "status": "missing_domain",
                "domain": "",
                "observed_domain_count": 0,
                "citation_count": 0,
                "citation_share": 0,
                "question_count": 0,
                "platform_count": 0,
                "value_score": 0,
                "value_label": "官网待补充",
                "business_readout": "品牌还没有官网域名，无法判断官网是否在智能回答里承担证据价值。",
                "sampling_policy": self._official_sampling_policy(domain=""),
                "comparison_domains": [],
                "content_audit": self._official_content_audit_missing(),
                "samples": [],
                "gaps": ["缺少品牌官网域名"],
            }

        official_question_count = len(
            {item.question_id for item in official_rows if item.question_id}
        )
        official_platform_count = len(
            {item.platform for item in official_rows if item.platform}
        )
        citation_share = len(official_rows) / total_citations if total_citations else 0
        question_coverage = (
            official_question_count / len(unique_questions) if unique_questions else 0
        )
        platform_coverage = (
            official_platform_count / len(unique_platforms) if unique_platforms else 0
        )
        value_score = round(
            min(
                100,
                citation_share * 45 + question_coverage * 35 + platform_coverage * 20,
            )
        )
        status, value_label = self._official_value_status(
            official_count=len(official_rows),
            value_score=value_score,
            total_citations=total_citations,
        )
        samples = self._sample_citations(
            rows=official_rows,
            official_domains=official_domains,
            limit=MAX_OFFICIAL_SAMPLES,
        )
        gaps = self._official_gaps(
            domain=domain,
            official_count=len(official_rows),
            total_citations=total_citations,
            question_coverage=question_coverage,
            platform_coverage=platform_coverage,
        )
        comparison_domains = self._official_comparison_domains(
            rows=rows,
            official_domains=official_domains,
        )
        brand_name = str(getattr(entity, "name", "") or "当前品牌").strip()
        content_audit = (
            await self._official_content_audit(
                entity=entity,
                domain=domain,
                brand_name=brand_name,
            )
            if include_content_audit
            else self._official_content_audit_deferred(domain=domain)
        )
        return {
            "status": status,
            "domain": domain,
            "observed_domain_count": len(
                {item.domain for item in official_rows if item.domain}
            ),
            "citation_count": len(official_rows),
            "citation_share": round(citation_share, 4),
            "question_count": official_question_count,
            "platform_count": official_platform_count,
            "value_score": value_score,
            "value_label": value_label,
            "business_readout": self._official_readout(
                brand_name=brand_name,
                domain=domain,
                official_count=len(official_rows),
                citation_share=citation_share,
                question_count=official_question_count,
                platform_count=official_platform_count,
            ),
            "sampling_policy": self._official_sampling_policy(domain=domain),
            "comparison_domains": comparison_domains,
            "content_audit": content_audit,
            "samples": samples,
            "gaps": gaps,
        }

    async def _official_content_audit(
        self,
        *,
        entity: Entity | None,
        domain: str,
        brand_name: str,
    ) -> dict[str, Any]:
        url = self._official_fetch_url(entity=entity, domain=domain)
        if not url:
            return self._official_content_audit_missing()

        features = await fetch_page_features(url)
        return self._official_content_audit_payload(
            domain=domain,
            brand_name=brand_name,
            features=features,
        )

    @staticmethod
    def _official_content_audit_payload(
        *,
        domain: str,
        brand_name: str,
        features: dict[str, Any],
    ) -> dict[str, Any]:
        readable = bool(features.get("crawl_readable"))
        title = _compact(str(features.get("fetched_title") or ""), limit=120)
        meta_description = _compact(
            str(features.get("meta_description") or ""),
            limit=220,
        )
        h1_texts = [
            _compact(str(item or ""), limit=80)
            for item in (features.get("h1_texts") or [])[:3]
            if str(item or "").strip()
        ]
        schema_types = [
            str(item)
            for item in (features.get("schema_types") or [])[:5]
            if str(item or "").strip()
        ]
        body_excerpt = str(features.get("body_text_excerpt") or "")
        body_text_length = int(features.get("body_text_length") or 0)
        brand_needles = _brand_needles(brand_name=brand_name, domain=domain)
        title_haystack = f"{title} {meta_description} {' '.join(h1_texts)}".lower()
        body_haystack = body_excerpt.lower()
        brand_in_title = any(needle in title_haystack for needle in brand_needles)
        brand_in_body = any(needle in body_haystack for needle in brand_needles)

        gaps: list[str] = []
        if not readable:
            reason = str(features.get("fetch_failure_reason") or "request_error")
            gaps.append(f"官网首页不可读：{reason}")
        if readable and not title:
            gaps.append("缺少页面标题")
        if readable and not meta_description:
            gaps.append("缺少页面描述")
        if readable and not h1_texts:
            gaps.append("缺少清晰 H1")
        if readable and body_text_length < 300:
            gaps.append("页面可读正文偏少")
        if readable and not (brand_in_title or brand_in_body):
            gaps.append("页面可读文本里没有明显品牌名")

        score = 0
        if readable:
            score += 20
        if int(features.get("http_status") or 0) < 400 and features.get("http_status"):
            score += 10
        if title:
            score += 12
        if meta_description:
            score += 12
        if h1_texts:
            score += 12
        if bool(features.get("has_main")) or bool(features.get("has_article")):
            score += 8
        if body_text_length >= 900:
            score += 16
        elif body_text_length >= 300:
            score += 8
        if schema_types:
            score += 8
        if brand_in_title:
            score += 8
        if brand_in_body:
            score += 8
        score = min(score, 100)

        if not readable:
            status = "unreachable"
            label = "官网首页暂不可读"
        elif score >= 72:
            status = "content_ready"
            label = "官网内容适合作为品牌证据"
        elif score >= 42:
            status = "partially_readable"
            label = "官网内容可读但证据结构偏弱"
        else:
            status = "thin_content"
            label = "官网可读内容偏薄"

        return {
            "status": status,
            "value_score": score,
            "value_label": label,
            "http_status": features.get("http_status"),
            "final_url": str(features.get("final_url") or ""),
            "content_type": str(features.get("content_type") or ""),
            "title": title,
            "meta_description": meta_description,
            "h1_texts": h1_texts,
            "schema_types": schema_types,
            "body_text_length": body_text_length,
            "brand_name_in_title": brand_in_title,
            "brand_name_in_body": brand_in_body,
            "business_readout": _official_content_readout(
                domain=domain,
                status=status,
                score=score,
                title=title,
            ),
            "gaps": gaps,
        }

    @staticmethod
    def _official_content_audit_missing() -> dict[str, Any]:
        return {
            "status": "missing_domain",
            "value_score": 0,
            "value_label": "官网内容待观测",
            "http_status": None,
            "final_url": "",
            "content_type": "",
            "title": "",
            "meta_description": "",
            "h1_texts": [],
            "schema_types": [],
            "body_text_length": 0,
            "brand_name_in_title": False,
            "brand_name_in_body": False,
            "business_readout": "品牌还没有官网域名，无法审计官网自身内容价值。",
            "gaps": ["缺少品牌官网域名"],
        }

    @staticmethod
    def _official_content_audit_deferred(*, domain: str) -> dict[str, Any]:
        return {
            "status": "deferred",
            "value_score": 0,
            "value_label": "官网内容未在本轮实时读取",
            "http_status": None,
            "final_url": domain,
            "content_type": "",
            "title": "",
            "meta_description": "",
            "h1_texts": [],
            "schema_types": [],
            "body_text_length": 0,
            "brand_name_in_title": False,
            "brand_name_in_body": False,
            "business_readout": "本轮只使用已沉淀的引用证据，不实时抓取官网首页。",
            "gaps": [],
        }

    @staticmethod
    def _official_fetch_url(*, entity: Entity | None, domain: str) -> str:
        raw = str(getattr(entity, "domain", "") or "").strip()
        candidate = raw if raw.startswith(("http://", "https://")) else ""
        if not candidate and domain:
            candidate = f"https://{domain}"
        if not _is_safe_public_website_url(candidate):
            return ""
        return candidate

    @staticmethod
    def _official_domains(entity: Entity | None) -> list[str]:
        return official_domains_for_entity(entity)

    def _source_role(
        self,
        row: CitationEvidenceRow,
        *,
        official_domains: list[str],
    ) -> str:
        if self._is_official_domain(row.domain, official_domains=official_domains):
            return "official_website"
        category = self._category(row).lower()
        domain = row.domain.lower()
        title = f"{row.title} {self._site_name(row)}".lower()
        haystack = f"{category} {domain} {title}"
        if any(token in haystack for token in ("官网", "official", "企业网站")):
            return "official_website"
        if any(
            token in haystack
            for token in ("auto", "car", "industry", "vertical", "汽车", "行业", "垂直")
        ):
            return "industry_vertical"
        if any(token in haystack for token in ("news", "media", "新闻", "媒体")):
            return "news_media"
        if any(
            token in haystack
            for token in (
                "forum",
                "community",
                "social",
                "知乎",
                "小红书",
                "微博",
                "社区",
            )
        ):
            return "community"
        if any(
            token in haystack
            for token in ("wiki", "百科", "database", "资料", "知识库")
        ):
            return "knowledge_base"
        if any(
            token in haystack
            for token in ("shop", "mall", "store", "电商", "商城", "交易")
        ):
            return "commerce_platform"
        return "other"

    def _sample_citations(
        self,
        *,
        rows: list[CitationEvidenceRow],
        official_domains: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        if not rows:
            return []
        domain_counts = Counter(item.domain for item in rows if item.domain)
        unique_by_url: dict[str, CitationEvidenceRow] = {}
        for item in rows:
            key = item.url or f"{item.domain}:{item.title}:{item.citation_id}"
            if key not in unique_by_url:
                unique_by_url[key] = item
        scored_rows = sorted(
            unique_by_url.values(),
            key=lambda item: (
                -self._sample_score(
                    item,
                    domain_counts=domain_counts,
                    official_domains=official_domains,
                ),
                -(item.created_at.timestamp() if item.created_at else 0),
                item.title or item.url,
            ),
        )
        return [
            self._sample_payload(
                item,
                sample_reason=self._sample_reason(
                    item,
                    domain_counts=domain_counts,
                    official_domains=official_domains,
                ),
                official_domains=official_domains,
            )
            for item in scored_rows[:limit]
        ]

    def _sample_score(
        self,
        row: CitationEvidenceRow,
        *,
        domain_counts: Counter[str],
        official_domains: list[str],
    ) -> float:
        score = float(row.confidence or 0)
        if self._is_official_domain(row.domain, official_domains=official_domains):
            score += 3
        score += min(domain_counts.get(row.domain, 0), 10) / 10
        if row.snippet:
            score += 0.2
        if self._is_homepage(row.url):
            score += 0.5
        return score

    def _sample_reason(
        self,
        row: CitationEvidenceRow,
        *,
        domain_counts: Counter[str],
        official_domains: list[str],
    ) -> str:
        if self._is_official_domain(row.domain, official_domains=official_domains):
            return "官网样本"
        if domain_counts.get(row.domain, 0) >= 3:
            return "高频来源"
        if row.confidence is not None:
            return "高置信来源"
        return "代表样本"

    @staticmethod
    def _official_sampling_policy(*, domain: str) -> dict[str, Any]:
        if not domain:
            return {
                "object_type": "official_website_asset",
                "sample_unit": "citation_source",
                "max_samples": MAX_OFFICIAL_SAMPLES,
                "summary": "先补齐品牌官网域名，再抽取官网引用样本。",
                "priority": [
                    "官网域名匹配",
                    "首页或关键页面",
                    "高置信",
                    "多平台覆盖",
                    "近期样本",
                ],
                "comparison_baseline": "外部来源域名只作为对照，不混入官网样本。",
            }
        return {
            "object_type": "official_website_asset",
            "sample_unit": "citation_source",
            "max_samples": MAX_OFFICIAL_SAMPLES,
            "summary": (
                f"只抽取 {domain} 的官网引用；优先首页或关键页面、高置信、多平台覆盖和近期样本。"
            ),
            "priority": [
                "官网域名匹配",
                "首页或关键页面",
                "高置信",
                "多平台覆盖",
                "近期样本",
            ],
            "comparison_baseline": "外部来源域名只作为对照，用来判断品牌叙事由谁塑造。",
        }

    def _official_comparison_domains(
        self,
        *,
        rows: list[CitationEvidenceRow],
        official_domains: list[str],
    ) -> list[dict[str, Any]]:
        grouped: dict[str, list[CitationEvidenceRow]] = defaultdict(list)
        for row in rows:
            if not row.domain:
                continue
            if self._is_official_domain(row.domain, official_domains=official_domains):
                continue
            grouped[row.domain].append(row)

        summaries: list[dict[str, Any]] = []
        for domain, items in grouped.items():
            source_role = self._source_role(items[0], official_domains=official_domains)
            summaries.append(
                {
                    "domain": domain,
                    "source_role": source_role,
                    "source_role_label": SOURCE_ROLE_LABELS.get(
                        source_role,
                        "其他来源",
                    ),
                    "citation_count": len(items),
                    "answer_count": len(
                        {item.answer_id for item in items if item.answer_id}
                    ),
                }
            )
        summaries.sort(
            key=lambda item: (-int(item["citation_count"]), str(item["domain"]))
        )
        return summaries[:MAX_OFFICIAL_COMPARISON_DOMAINS]

    def _sample_payload(
        self,
        row: CitationEvidenceRow,
        *,
        sample_reason: str,
        official_domains: list[str],
    ) -> dict[str, Any]:
        return {
            "citation_id": row.citation_id,
            "url": row.url,
            "domain": row.domain,
            "title": _compact(row.title or row.url or row.domain, limit=90),
            "snippet_preview": _compact(row.snippet, limit=140),
            "platform": row.platform,
            "confidence": row.confidence,
            "sample_reason": sample_reason,
            "is_official": self._is_official_domain(
                row.domain,
                official_domains=official_domains,
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def _topic(self, row: CitationEvidenceRow) -> tuple[str, str]:
        label = self._row_topic_label(row)
        if _looks_like_internal_question_id(label):
            label = "综合外部来源"
        normalized = "".join(
            char.lower() if char.isalnum() else "-" for char in str(label or "general")
        ).strip("-")
        normalized = "-".join(part for part in normalized.split("-") if part)
        return (normalized[:48] or "general", label)

    def _row_topic_label(self, row: CitationEvidenceRow) -> str:
        category = _compact(row.category, limit=24)
        if category and not _looks_like_internal_question_id(category):
            return category
        inferred = self._inferred_business_topic([row])
        if inferred != "综合外部来源":
            return inferred
        question = _compact(row.question_text, limit=24)
        if question and not _looks_like_internal_question_id(question):
            return question
        return inferred

    def _topic_label(self, rows: list[CitationEvidenceRow]) -> str:
        categories = Counter(row.category for row in rows if row.category)
        if categories:
            label = _compact(categories.most_common(1)[0][0], limit=24)
            if label and not _looks_like_internal_question_id(label):
                return label
        questions = Counter(row.question_text for row in rows if row.question_text)
        if questions:
            label = _compact(questions.most_common(1)[0][0], limit=24)
            if (
                label
                and not _looks_like_internal_question_id(label)
                and len(str(questions.most_common(1)[0][0] or "")) <= 36
            ):
                return label
        return self._inferred_business_topic(rows)

    def _inferred_business_topic(self, rows: list[CitationEvidenceRow]) -> str:
        haystack = " ".join(
            f"{row.question_text} {row.title} {row.snippet} {row.domain}"
            for row in rows[:80]
        ).lower()
        topic_rules: tuple[tuple[tuple[str, ...], str], ...] = (
            (("价格", "售价", "优惠", "多少钱", "购车"), "价格与购车决策"),
            (("续航", "能耗", "电池", "充电", "补能"), "续航与补能"),
            (("智驾", "智能驾驶", "辅助驾驶", "noa", "安全"), "智能驾驶与安全"),
            (("空间", "家庭", "座椅", "舒适", "内饰"), "家庭用车体验"),
            (("评测", "对比", "排名", "口碑", "优缺点"), "评测口碑"),
            (("参数", "配置", "车型", "产品"), "车型与配置"),
            (("销量", "交付", "财报", "公司", "投资"), "品牌经营表现"),
        )
        for keywords, label in topic_rules:
            if any(keyword in haystack for keyword in keywords):
                return label

        role_counter = Counter(
            self._source_role(row, official_domains=[]) for row in rows if row.domain
        )
        role = role_counter.most_common(1)[0][0] if role_counter else "other"
        role_topics = {
            "industry_vertical": "行业媒体评价",
            "news_media": "新闻报道",
            "community": "用户讨论",
            "knowledge_base": "资料型来源",
            "commerce_platform": "交易平台信息",
            "official_website": "官网信息",
        }
        return role_topics.get(role, "综合外部来源")

    @staticmethod
    def _cluster_readout(
        *,
        topic_label: str,
        source_role: str,
        citation_count: int,
        domain_count: int,
        official_count: int,
    ) -> str:
        role_label = SOURCE_ROLE_LABELS.get(source_role, "其他来源")
        if source_role == "official_website":
            return f"{topic_label} 里有 {citation_count} 条引用来自官网，说明智能回答正在把品牌自有内容当作证据。"
        if official_count:
            return f"{topic_label} 同时被官网和{role_label}支撑，可对照自有内容与外部叙事是否一致。"
        return f"{topic_label} 主要由 {domain_count} 个{role_label}支撑，可用少量样本判断外部叙事。"

    @staticmethod
    def _official_value_status(
        *,
        official_count: int,
        value_score: int,
        total_citations: int,
    ) -> tuple[str, str]:
        if total_citations <= 0:
            return "no_evidence", "暂无引用证据"
        if official_count <= 0:
            return "not_cited", "官网暂未成为智能回答证据源"
        if value_score >= 60:
            return "strong", "官网已是核心证据源"
        if value_score >= 25:
            return "visible", "官网已有可见证据价值"
        return "weak", "官网被引用但覆盖偏弱"

    @staticmethod
    def _official_gaps(
        *,
        domain: str,
        official_count: int,
        total_citations: int,
        question_coverage: float,
        platform_coverage: float,
    ) -> list[str]:
        gaps: list[str] = []
        if not domain:
            gaps.append("缺少品牌官网域名")
        if total_citations > 0 and official_count == 0:
            gaps.append("智能回答引用了外部来源，但没有引用官网")
        if official_count > 0 and question_coverage < 0.3:
            gaps.append("官网只覆盖少量问题")
        if official_count > 0 and platform_coverage < 0.5:
            gaps.append("官网只被少量平台引用")
        return gaps

    @staticmethod
    def _official_readout(
        *,
        brand_name: str,
        domain: str,
        official_count: int,
        citation_share: float,
        question_count: int,
        platform_count: int,
    ) -> str:
        if official_count <= 0:
            return f"{brand_name} 的官网 {domain} 目前没有进入智能回答引用，品牌叙事更多由外部来源塑造。"
        percent = round(citation_share * 100)
        return (
            f"{brand_name} 的官网 {domain} 被引用 {official_count} 次，占全部引用约 {percent}%，"
            f"覆盖 {question_count} 个问题和 {platform_count} 个平台。"
        )

    @staticmethod
    def _is_official_domain(domain: str, *, official_domains: list[str]) -> bool:
        if not domain or not official_domains:
            return False
        return domain_matches(domain, official_domains)

    @staticmethod
    def _is_homepage(url: str) -> bool:
        if not url:
            return False
        try:
            from urllib.parse import urlparse

            parsed = urlparse(url if "://" in url else f"https://{url}")
            path = str(parsed.path or "/").strip()
            return path in {"", "/"}
        except Exception:
            return False

    @staticmethod
    def _category(row: CitationEvidenceRow) -> str:
        payload = row.payload
        for key in ("source_category", "site_category", "category", "source_type"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        url_intelligence = payload.get("url_intelligence")
        if isinstance(url_intelligence, dict):
            value = url_intelligence.get("category")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _site_name(row: CitationEvidenceRow) -> str:
        payload = row.payload
        for key in ("site_name", "source_name", "source_title", "title"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        url_intelligence = payload.get("url_intelligence")
        if isinstance(url_intelligence, dict):
            value = url_intelligence.get("site_name")
            if isinstance(value, str) and value.strip():
                return value.strip()
        return row.title or row.domain


def _compact(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _looks_like_internal_question_id(value: str) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return False
    return bool(
        text.startswith("q_")
        or text.startswith("问题 q_")
        or text.startswith("question_")
    )


def _unique_non_empty(values: list[str], *, limit: int) -> list[str]:
    seen: set[str] = set()
    items: list[str] = []
    for value in values:
        text = " ".join(str(value or "").split())
        if not text or text in seen:
            continue
        seen.add(text)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _brand_needles(*, brand_name: str, domain: str) -> list[str]:
    candidates = [
        str(brand_name or "").strip().lower(),
        str(domain or "").strip().lower(),
        str(domain or "").split(".", 1)[0].strip().lower(),
    ]
    return [item for item in candidates if len(item) >= 2]


def _official_content_readout(
    *,
    domain: str,
    status: str,
    score: int,
    title: str,
) -> str:
    if status == "unreachable":
        return f"官网 {domain} 当前不可读，智能回答和搜索系统都可能难以把它当作稳定证据。"
    if status == "content_ready":
        return f"官网 {domain} 可读性较好，页面标题“{title or domain}”可以支撑品牌自有叙事。"
    if status == "partially_readable":
        return (
            f"官网 {domain} 可以读取，但内容结构还不够完整，当前内容价值分为 {score}。"
        )
    return f"官网 {domain} 可读内容偏少，当前更难支撑智能回答形成稳定引用。"


def _is_safe_public_website_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except Exception:
        return False
    if parsed.scheme not in {"http", "https"}:
        return False
    host = str(parsed.hostname or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
        or address.is_unspecified
    )
