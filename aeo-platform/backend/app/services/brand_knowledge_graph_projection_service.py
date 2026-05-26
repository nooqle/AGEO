"""Dashboard projections for the AI brand knowledge graph."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import (
    BrandCitationSource,
    BrandCompetitorEntity,
    BrandIntelligenceQuestion,
    BrandMention,
    BrandMetricSnapshot,
    BrandPlatformAnswer,
    BrandUserDecision,
)
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringPlan
from app.services.brand_domain_canonicalization import (
    domain_matches_official,
    official_domains_for_entity,
    primary_official_domain,
)


INTERNAL_EVIDENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"prompt|debug|trace|chain[-_ ]?of[-_ ]?thought", re.IGNORECASE),
    re.compile(r"web[_\s-]*search(?:\s*工具)?|调用工具|工具调用|浏览器工具", re.IGNORECASE),
    re.compile(r"推理过程|思考过程|内部过程|调度日志|模型过程"),
    re.compile(r"作为\s*AI|我将|首先我需要|接下来我会"),
)


class BrandKnowledgeGraphProjectionService:
    """Builds user-facing projections from durable brand intelligence objects."""

    ANSWER_LIMIT = 500
    MENTION_LIMIT = 800
    CITATION_LIMIT = 1200
    COMPETITOR_LIMIT = 60
    RANKING_MIN_ANSWER_SAMPLE = 20
    RANKING_MIN_COMPETITOR_COUNT = 2
    RANKING_MIN_COMPETITORS_WITH_MENTIONS = 2
    RANKING_MIN_COMPETITOR_MENTION_COUNT = 3

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self,
        *,
        entity_id: UUID,
        action_queue: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        entity = await self.db.get(Entity, entity_id)
        if entity is None:
            return {
                "summary_projection": {},
                "evidence_projection": {},
                "graph_projection": {"nodes": [], "edges": [], "default_focus": None},
                "recommendation_projection": {"recommendations": []},
            }

        answers = await self._answers(entity_id=entity_id)
        mentions = await self._mentions(entity_id=entity_id)
        citations = await self._citations(entity_id=entity_id)
        competitors = await self._competitors(entity_id=entity_id)
        questions = await self._question_map(entity_id=entity_id)
        latest_metric = await self._latest_metric(entity_id=entity_id)
        monitoring_count = await self._monitoring_count(entity_id=entity_id)
        recommendation_tasks = await self._recommendation_task_summary(
            entity_id=entity_id,
        )

        official_domain = primary_official_domain(entity)
        official_domains = official_domains_for_entity(entity)
        answer_by_id = {answer.id: answer for answer in answers}
        successful_answers = [answer for answer in answers if answer.success]
        analyzable_answers = [
            answer
            for answer in successful_answers
            if _question_text_for_answer(answer, questions)
            and _answer_text_for_sample(answer)
        ]
        analyzable_answer_ids = {answer.id for answer in analyzable_answers}
        unreadable_answer_count = max(
            len(successful_answers) - len(analyzable_answers),
            0,
        )
        answer_mentions = [
            mention
            for mention in mentions
            if mention.answer_id is not None
            and mention.answer_id in analyzable_answer_ids
        ]
        target_mentions = [
            mention
            for mention in answer_mentions
            if mention.mention_role == "target_brand"
            and mention.mentioned_object_type == "brand_entity"
        ]
        target_answer_ids = {
            mention.answer_id
            for mention in target_mentions
            if mention.answer_id is not None
        }
        denominator = len(analyzable_answers)
        numerator = len(target_answer_ids)
        unmentioned_answer_count = len(
            [
                answer
                for answer in analyzable_answers
                if answer.id not in target_answer_ids
            ]
        )
        mention_rate = (numerator / denominator) if denominator else None

        citations_by_answer: dict[UUID, list[BrandCitationSource]] = defaultdict(list)
        valid_citations = [
            citation
            for citation in citations
            if citation.answer_id in analyzable_answer_ids
        ]
        for citation in valid_citations:
            citations_by_answer[citation.answer_id].append(citation)
        official_citations = [
            citation
            for citation in valid_citations
            if _matches_official_domain(citation.domain, official_domains)
            or _matches_official_domain(_normalize_domain(citation.url), official_domains)
        ]
        official_rate = (
            len(official_citations) / len(valid_citations) if valid_citations else None
        )
        sentiment_counts = _sentiment_counts(target_mentions)
        ranking_rows = self._ranking_rows(
            entity=entity,
            competitors=competitors,
            mentions=answer_mentions,
            answer_count=denominator,
        )
        ranking_sufficiency = self._ranking_sufficiency(
            ranking_rows=ranking_rows,
            answer_count=denominator,
        )
        target_rank = next(
            (
                index + 1
                for index, row in enumerate(ranking_rows)
                if row["is_current_brand"]
            ),
            None,
        )
        platform_rows = self._platform_rows(
            answers=analyzable_answers,
            mentions=target_mentions,
        )
        answer_samples = self._answer_samples(
            mentions=target_mentions,
            answer_by_id=answer_by_id,
            questions=questions,
            citations_by_answer=citations_by_answer,
        )
        unmentioned_answer_samples = self._unmentioned_answer_samples(
            answers=analyzable_answers,
            target_answer_ids=target_answer_ids,
            questions=questions,
            citations_by_answer=citations_by_answer,
        )
        unmentioned_unreadable_count = max(
            unmentioned_answer_count - len(unmentioned_answer_samples),
            0,
        )
        external_domains = self._external_domain_rows(
            citations=valid_citations,
            official_domains=official_domains,
        )
        platform_source_targets = self._platform_source_targets(
            citations=valid_citations,
            answer_by_id=answer_by_id,
            official_domains=official_domains,
        )
        content_topics = self._content_topics(
            entity=entity,
            questions=questions,
            answer_samples=answer_samples,
            unmentioned_answer_samples=unmentioned_answer_samples,
        )
        summary_projection = {
            "brand": {
                "id": str(entity.id),
                "name": entity.name,
                "domain": entity.domain,
                "industry": entity.industry,
            },
            "sample_scope": {
                "platform_count": len(
                    {answer.platform for answer in answers if answer.platform}
                ),
                "question_count": len(questions)
                or len(
                    {
                        answer.question_id
                        for answer in analyzable_answers
                        if answer.question_id
                    }
                ),
                "answer_count": denominator,
                "citation_count": len(valid_citations),
                "mention_count": numerator,
                "raw_answer_record_count": len(successful_answers),
                "excluded_unreadable_answer_count": unreadable_answer_count,
                "captured_from": _min_iso(
                    [answer.captured_at for answer in analyzable_answers]
                ),
                "captured_to": _max_iso(
                    [answer.captured_at for answer in analyzable_answers]
                ),
            },
            "metrics": {
                "mention_rate": {
                    "key": "mention_rate",
                    "label": "AI 提及率",
                    "value": mention_rate,
                    "display_value": _percent(mention_rate),
                    "numerator": numerator,
                    "denominator": denominator,
                    "sample_sufficiency": _metric_sample_sufficiency(
                        metric_key="mention_rate",
                        denominator=denominator,
                        numerator=numerator,
                    ),
                },
                "mention_ranking": {
                    "key": "mention_ranking",
                    "label": "提及排名",
                    "rank": target_rank,
                    "display_rank": (
                        target_rank if ranking_sufficiency["is_comparable"] else None
                    ),
                    "total": len(ranking_rows),
                    "rows": ranking_rows[:8],
                    "sample_sufficiency": ranking_sufficiency,
                },
                "official_citation_rate": {
                    "key": "official_citation_rate",
                    "label": "官网引用率",
                    "value": official_rate,
                    "display_value": _percent(official_rate),
                    "numerator": len(official_citations),
                    "denominator": len(valid_citations),
                    "official_domain": official_domain,
                    "official_domains": official_domains,
                    "top_external_domain": (
                        external_domains[0]["domain"] if external_domains else None
                    ),
                    "sample_sufficiency": _metric_sample_sufficiency(
                        metric_key="official_citation_rate",
                        denominator=len(valid_citations),
                        numerator=len(official_citations),
                    ),
                },
                "sentiment_distribution": {
                    "key": "sentiment_distribution",
                    "label": "语气性质",
                    **sentiment_counts,
                    "sample_sufficiency": _metric_sample_sufficiency(
                        metric_key="sentiment_distribution",
                        denominator=numerator,
                        numerator=sentiment_counts.get("total", 0),
                    ),
                },
            },
            "top_opportunity": self._top_opportunity(
                official_rate=official_rate,
                mention_rate=mention_rate,
                external_domains=external_domains,
            ),
            "top_risk": self._top_risk(
                sentiment_counts=sentiment_counts,
                ranking_rows=ranking_rows,
                target_rank=target_rank,
                ranking_sufficiency=ranking_sufficiency,
            ),
        }
        recommendation_sample_status = _recommendation_sample_status(
            question_count=summary_projection["sample_scope"]["question_count"],
            answer_count=denominator,
            platform_count=summary_projection["sample_scope"]["platform_count"],
        )
        evidence_projection = {
            "mention_rate_detail": {
                "metric_key": "mention_rate",
                "numerator": numerator,
                "denominator": denominator,
                "value": mention_rate,
                "unmentioned_count": unmentioned_answer_count,
                "unmentioned_sample_count": len(unmentioned_answer_samples),
                "unmentioned_unreadable_count": unmentioned_unreadable_count,
                "excluded_unreadable_answer_count": unreadable_answer_count,
                "platform_rows": platform_rows,
                "answer_samples": answer_samples[:24],
                "unmentioned_answer_samples": unmentioned_answer_samples[:12],
                "sample_quality": _sample_quality(
                    metric_key="mention_rate",
                    sample_count=denominator,
                    evidence_count=numerator,
                    excluded_count=unreadable_answer_count,
                ),
            },
            "ranking_detail": {
                "metric_key": "mention_ranking",
                "rank": target_rank,
                "display_rank": (
                    target_rank if ranking_sufficiency["is_comparable"] else None
                ),
                "total": len(ranking_rows),
                "brands": ranking_rows,
                "sample_sufficiency": ranking_sufficiency,
                "sample_quality": _sample_quality(
                    metric_key="mention_ranking",
                    sample_count=denominator,
                    evidence_count=sum(
                        int(row.get("mention_count") or 0) for row in ranking_rows
                    ),
                    excluded_count=unreadable_answer_count,
                ),
            },
            "official_citation_detail": {
                "metric_key": "official_citation_rate",
                "official_domain": official_domain,
                "official_domains": official_domains,
                "official_citation_count": len(official_citations),
                "total_citation_count": len(valid_citations),
                "value": official_rate,
                "top_external_domains": external_domains[:12],
                "official_samples": [
                    _citation_sample(citation) for citation in official_citations[:8]
                ],
                "sample_quality": _sample_quality(
                    metric_key="official_citation_rate",
                    sample_count=len(valid_citations),
                    evidence_count=len(official_citations),
                    excluded_count=0,
                ),
            },
            "sentiment_detail": {
                "metric_key": "sentiment_distribution",
                "summary": sentiment_counts,
                "positive": [
                    sample
                    for sample in answer_samples
                    if sample.get("sentiment") == "positive"
                ][:8],
                "neutral": [
                    sample
                    for sample in answer_samples
                    if sample.get("sentiment") == "neutral"
                ][:8],
                "negative": [
                    sample
                    for sample in answer_samples
                    if sample.get("sentiment") == "negative"
                ][:8],
                "sample_quality": _sample_quality(
                    metric_key="sentiment_distribution",
                    sample_count=numerator,
                    evidence_count=sentiment_counts.get("total", 0),
                    excluded_count=0,
                ),
            },
        }
        recommendation_projection = {
            "sample_status": recommendation_sample_status,
            "recommendations": self._recommendations(
                entity=entity,
                mention_rate=mention_rate,
                official_rate=official_rate,
                sentiment_counts=sentiment_counts,
                external_domains=external_domains,
                platform_source_targets=platform_source_targets,
                ranking_rows=ranking_rows,
                ranking_sufficiency=ranking_sufficiency,
                monitoring_count=monitoring_count,
                action_queue=action_queue or [],
                denominator=denominator,
                numerator=numerator,
                sample_ready=recommendation_sample_status["is_ready"],
                content_topics=content_topics,
                unmentioned_answer_samples=unmentioned_answer_samples,
                recommendation_tasks=recommendation_tasks,
            )
        }
        graph_projection = self._graph_projection(
            entity=entity,
            summary=summary_projection,
            evidence=evidence_projection,
            recommendations=recommendation_projection["recommendations"],
            platform_rows=platform_rows,
            ranking_rows=ranking_rows,
            external_domains=external_domains,
            latest_metric=latest_metric,
        )
        return {
            "summary_projection": summary_projection,
            "evidence_projection": evidence_projection,
            "graph_projection": graph_projection,
            "recommendation_projection": recommendation_projection,
        }

    async def _answers(self, *, entity_id: UUID) -> list[BrandPlatformAnswer]:
        rows = (
            (
                await self.db.execute(
                    select(BrandPlatformAnswer)
                    .where(BrandPlatformAnswer.entity_id == entity_id)
                    .order_by(desc(BrandPlatformAnswer.captured_at))
                    .limit(self.ANSWER_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _mentions(self, *, entity_id: UUID) -> list[BrandMention]:
        rows = (
            (
                await self.db.execute(
                    select(BrandMention)
                    .where(BrandMention.entity_id == entity_id)
                    .order_by(desc(BrandMention.captured_at))
                    .limit(self.MENTION_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _citations(self, *, entity_id: UUID) -> list[BrandCitationSource]:
        rows = (
            (
                await self.db.execute(
                    select(BrandCitationSource)
                    .where(BrandCitationSource.entity_id == entity_id)
                    .order_by(desc(BrandCitationSource.created_at))
                    .limit(self.CITATION_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _competitors(self, *, entity_id: UUID) -> list[BrandCompetitorEntity]:
        rows = (
            (
                await self.db.execute(
                    select(BrandCompetitorEntity)
                    .where(BrandCompetitorEntity.entity_id == entity_id)
                    .order_by(desc(BrandCompetitorEntity.relevance_score))
                    .limit(self.COMPETITOR_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _question_map(
        self,
        *,
        entity_id: UUID,
    ) -> dict[UUID, BrandIntelligenceQuestion]:
        rows = (
            (
                await self.db.execute(
                    select(BrandIntelligenceQuestion).where(
                        BrandIntelligenceQuestion.entity_id == entity_id
                    )
                )
            )
            .scalars()
            .all()
        )
        return {row.id: row for row in rows}

    async def _latest_metric(self, *, entity_id: UUID) -> BrandMetricSnapshot | None:
        return (
            (
                await self.db.execute(
                    select(BrandMetricSnapshot)
                    .where(BrandMetricSnapshot.entity_id == entity_id)
                    .order_by(desc(BrandMetricSnapshot.captured_at))
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )

    async def _monitoring_count(self, *, entity_id: UUID) -> int:
        rows = (
            await self.db.execute(
                select(MonitoringPlan.id).where(MonitoringPlan.entity_id == entity_id)
            )
        ).all()
        return len(rows)

    async def _recommendation_task_summary(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, dict[str, Any]]:
        rows = (
            (
                await self.db.execute(
                    select(BrandUserDecision)
                    .where(
                        BrandUserDecision.entity_id == entity_id,
                        BrandUserDecision.decision_type == "recommendation_task",
                    )
                    .order_by(desc(BrandUserDecision.decided_at))
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        tasks: dict[str, dict[str, Any]] = {}
        for row in rows:
            payload = row.input_payload if isinstance(row.input_payload, dict) else {}
            recommendation_id = str(
                payload.get("recommendation_id")
                or str(row.decision_key or "").replace("recommendation:", "", 1)
            ).strip()
            if not recommendation_id or recommendation_id in tasks:
                continue
            task_status = str(payload.get("task_status") or row.status or "").strip()
            tasks[recommendation_id] = {
                "task_state": _public_recommendation_task_state(task_status),
                "owner_label": _safe_public_text(payload.get("owner_label"), 80),
                "due_at": _safe_public_text(payload.get("due_at"), 40),
                "review_at": _safe_public_text(payload.get("review_at"), 40),
                "latest_feedback_at": row.decided_at.isoformat(),
                "has_feedback_text": bool(str(row.feedback_text or "").strip()),
            }
        return tasks

    def _platform_rows(
        self,
        *,
        answers: list[BrandPlatformAnswer],
        mentions: list[BrandMention],
    ) -> list[dict[str, Any]]:
        answer_counts: Counter[str] = Counter()
        mention_answer_ids_by_platform: dict[str, set[UUID]] = defaultdict(set)
        for answer in answers:
            if answer.success:
                answer_counts[answer.platform or "unknown"] += 1
        for mention in mentions:
            if mention.answer_id is not None:
                mention_answer_ids_by_platform[mention.platform or "unknown"].add(
                    mention.answer_id
                )
        rows = []
        for platform, answer_count in sorted(answer_counts.items()):
            mention_count = len(mention_answer_ids_by_platform.get(platform, set()))
            rows.append(
                {
                    "platform": platform,
                    "answer_count": answer_count,
                    "mention_count": mention_count,
                    "mention_rate": (
                        mention_count / answer_count if answer_count else None
                    ),
                }
            )
        return sorted(rows, key=lambda item: item["mention_count"], reverse=True)

    def _ranking_rows(
        self,
        *,
        entity: Entity,
        competitors: list[BrandCompetitorEntity],
        mentions: list[BrandMention],
        answer_count: int,
    ) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        target_key = f"brand_entity:{entity.id}"
        for mention in mentions:
            key = f"{mention.mentioned_object_type}:{mention.mentioned_object_id}"
            counts[key] += 1
        rows = [
            {
                "brand_id": str(entity.id),
                "brand_name": entity.name,
                "mention_count": counts[target_key],
                "mention_rate": (
                    counts[target_key] / answer_count if answer_count else None
                ),
                "sample_count": answer_count,
                "is_current_brand": True,
            }
        ]
        for competitor in competitors:
            key = f"competitor_entity:{competitor.id}"
            rows.append(
                {
                    "brand_id": str(competitor.id),
                    "brand_name": competitor.display_name or competitor.normalized_name,
                    "mention_count": counts[key],
                    "mention_rate": (
                        counts[key] / answer_count if answer_count else None
                    ),
                    "sample_count": answer_count,
                    "is_current_brand": False,
                }
            )
        rows = sorted(
            rows,
            key=lambda item: (
                float(item.get("mention_rate") or 0),
                int(item.get("mention_count") or 0),
            ),
            reverse=True,
        )
        for index, row in enumerate(rows, start=1):
            row["rank"] = index
            row["provisional_rank"] = index
        return rows

    def _ranking_sufficiency(
        self,
        *,
        ranking_rows: list[dict[str, Any]],
        answer_count: int,
    ) -> dict[str, Any]:
        competitor_rows = [
            row for row in ranking_rows if not bool(row.get("is_current_brand"))
        ]
        competitors_with_mentions = [
            row for row in competitor_rows if int(row.get("mention_count") or 0) > 0
        ]
        current_brand_mention_count = next(
            (
                int(row.get("mention_count") or 0)
                for row in ranking_rows
                if bool(row.get("is_current_brand"))
            ),
            0,
        )
        comparison_sample = {
            "answer_count": answer_count,
            "competitor_count": len(competitor_rows),
            "competitor_mention_count": sum(
                int(row.get("mention_count") or 0) for row in competitor_rows
            ),
            "competitors_with_mentions": len(competitors_with_mentions),
            "current_brand_mention_count": current_brand_mention_count,
            "minimum_answer_sample": self.RANKING_MIN_ANSWER_SAMPLE,
            "minimum_competitor_count": self.RANKING_MIN_COMPETITOR_COUNT,
            "minimum_competitors_with_mentions": (
                self.RANKING_MIN_COMPETITORS_WITH_MENTIONS
            ),
            "minimum_competitor_mention_count": (
                self.RANKING_MIN_COMPETITOR_MENTION_COUNT
            ),
        }
        if answer_count < self.RANKING_MIN_ANSWER_SAMPLE:
            status = "insufficient_answer_sample"
            label = "答案样本不足"
            reason = (
                f"当前只有 {answer_count} 条有效回答，至少需要 "
                f"{self.RANKING_MIN_ANSWER_SAMPLE} 条后再形成排名。"
            )
        elif not competitor_rows:
            status = "no_competitor"
            label = "缺少竞品样本"
            reason = "当前品牌还没有可比较的竞品对象。"
        elif len(competitor_rows) < self.RANKING_MIN_COMPETITOR_COUNT:
            status = "insufficient_competitor_scope"
            label = "竞品范围不足"
            reason = (
                f"当前只有 {len(competitor_rows)} 个竞品，至少需要 "
                f"{self.RANKING_MIN_COMPETITOR_COUNT} 个竞品同场比较。"
            )
        elif (
            comparison_sample["competitor_mention_count"]
            < self.RANKING_MIN_COMPETITOR_MENTION_COUNT
            or len(competitors_with_mentions)
            < self.RANKING_MIN_COMPETITORS_WITH_MENTIONS
        ):
            status = "insufficient_competitor_sample"
            label = "竞品提及样本不足"
            reason = (
                "当前竞品提及覆盖不足，需要更多竞品在同一批问题里被提到，"
                "再形成稳定排名。"
            )
        else:
            status = "formed"
            label = "排名已形成"
            reason = "当前样本量和竞品提及覆盖已达到同场景对比要求。"
        return {
            "is_comparable": status == "formed",
            "is_rank_reliable": status == "formed",
            "rank_status": status,
            "rank_status_label": label,
            "rank_reason": reason,
            "comparison_sample": comparison_sample,
        }

    def _answer_samples(
        self,
        *,
        mentions: list[BrandMention],
        answer_by_id: dict[UUID, BrandPlatformAnswer],
        questions: dict[UUID, BrandIntelligenceQuestion],
        citations_by_answer: dict[UUID, list[BrandCitationSource]],
    ) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        seen_answers: set[UUID] = set()
        for mention in mentions:
            if mention.answer_id is None or mention.answer_id in seen_answers:
                continue
            answer = answer_by_id.get(mention.answer_id)
            if answer is None:
                continue
            seen_answers.add(mention.answer_id)
            question = (
                questions.get(answer.question_object_id)
                if answer.question_object_id is not None
                else None
            )
            question_text = _question_text_for_answer(answer, questions, question)
            answer_preview = _answer_text_for_sample(answer)
            mention_quote = _preview(mention.quote, 220)
            if not question_text or not (mention_quote or answer_preview):
                continue
            answer_citations = citations_by_answer.get(answer.id, [])
            samples.append(
                {
                    "answer_id": str(answer.id),
                    "question_id": answer.question_id,
                    "question": _preview(question_text, 160),
                    "platform": answer.platform,
                    "answer_preview": answer_preview,
                    "mention_quote": mention_quote,
                    "sentiment": mention.sentiment,
                    "cited_domains": _unique_domains(answer_citations),
                    "citation_sources": [
                        _citation_sample(citation) for citation in answer_citations[:5]
                    ],
                    "captured_at": answer.captured_at.isoformat(),
                }
            )
        return samples

    def _unmentioned_answer_samples(
        self,
        *,
        answers: list[BrandPlatformAnswer],
        target_answer_ids: set[UUID],
        questions: dict[UUID, BrandIntelligenceQuestion],
        citations_by_answer: dict[UUID, list[BrandCitationSource]],
    ) -> list[dict[str, Any]]:
        samples: list[dict[str, Any]] = []
        for answer in answers:
            if answer.id in target_answer_ids:
                continue
            question = (
                questions.get(answer.question_object_id)
                if answer.question_object_id is not None
                else None
            )
            question_text = _question_text_for_answer(answer, questions, question)
            answer_preview = _answer_text_for_sample(answer)
            if not question_text or not answer_preview:
                continue
            answer_citations = citations_by_answer.get(answer.id, [])
            samples.append(
                {
                    "answer_id": str(answer.id),
                    "question_id": answer.question_id,
                    "question": _preview(question_text, 160),
                    "platform": answer.platform,
                    "answer_preview": answer_preview,
                    "mention_quote": "",
                    "sentiment": "not_mentioned",
                    "cited_domains": _unique_domains(answer_citations),
                    "citation_sources": [
                        _citation_sample(citation) for citation in answer_citations[:5]
                    ],
                    "captured_at": answer.captured_at.isoformat(),
                }
            )
        return samples

    def _external_domain_rows(
        self,
        *,
        citations: list[BrandCitationSource],
        official_domains: list[str],
    ) -> list[dict[str, Any]]:
        by_domain: dict[str, dict[str, Any]] = {}
        for citation in citations:
            domain = _normalize_domain(citation.domain) or _normalize_domain(
                citation.url
            )
            if (
                not domain
                or _matches_official_domain(domain, official_domains)
                or not _is_distribution_domain(domain)
            ):
                continue
            row = by_domain.setdefault(
                domain,
                {
                    "domain": domain,
                    "citation_count": 0,
                    "answer_ids": set(),
                    "sample_titles": [],
                },
            )
            row["citation_count"] += 1
            row["answer_ids"].add(str(citation.answer_id))
            if citation.source_title and len(row["sample_titles"]) < 3:
                row["sample_titles"].append(citation.source_title)
        rows: list[dict[str, Any]] = []
        for row in by_domain.values():
            rows.append(
                {
                    "domain": row["domain"],
                    "citation_count": row["citation_count"],
                    "answer_count": len(row["answer_ids"]),
                    "sample_titles": row["sample_titles"],
                }
            )
        return sorted(rows, key=lambda item: item["citation_count"], reverse=True)

    def _platform_source_targets(
        self,
        *,
        citations: list[BrandCitationSource],
        answer_by_id: dict[UUID, BrandPlatformAnswer],
        official_domains: list[str],
    ) -> list[dict[str, Any]]:
        counter: Counter[tuple[str, str]] = Counter()
        for citation in citations:
            domain = _normalize_domain(citation.domain) or _normalize_domain(
                citation.url
            )
            if (
                not domain
                or _matches_official_domain(domain, official_domains)
                or not _is_distribution_domain(domain)
            ):
                continue
            answer = answer_by_id.get(citation.answer_id)
            platform = str(getattr(answer, "platform", "") or "").strip()
            if not platform:
                continue
            counter[(platform, domain)] += 1

        rows = [
            {
                "platform": platform,
                "domain": domain,
                "citation_count": count,
                "reason": (
                    f"{_platform_label(platform)}当前样本引用"
                    f"「{_distribution_target_name(domain)}」{count} 次"
                ),
            }
            for (platform, domain), count in counter.items()
        ]
        rows.sort(key=lambda item: int(item["citation_count"]), reverse=True)
        return rows[:8]

    def _content_topics(
        self,
        *,
        entity: Entity,
        questions: dict[UUID, BrandIntelligenceQuestion],
        answer_samples: list[dict[str, Any]],
        unmentioned_answer_samples: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        candidates: list[tuple[str, str, str]] = []
        for sample in unmentioned_answer_samples:
            question = str(sample.get("question") or "").strip()
            if question:
                candidates.append((_topic_title(question), question, "未提及样本"))
        for question in questions.values():
            question_text = str(question.question_text or "").strip()
            if not question_text:
                continue
            category = str(question.category or "").strip()
            title = (
                category if category and not _looks_like_internal_id(category) else ""
            )
            candidates.append(
                (title or _topic_title(question_text), question_text, "问题样本")
            )
        for sample in answer_samples:
            question = str(sample.get("question") or "").strip()
            if question:
                candidates.append((_topic_title(question), question, "已提及样本"))

        topics: list[dict[str, str]] = []
        seen: set[str] = set()
        for title, question, source in candidates:
            clean_title = _preview(title, 28)
            clean_question = _preview(question, 90)
            key = clean_title or clean_question
            if not key or key in seen:
                continue
            seen.add(key)
            topics.append(
                {
                    "title": clean_title,
                    "question": clean_question,
                    "evidence": f"{source}: {clean_question}",
                }
            )
            if len(topics) >= 3:
                break

        if topics:
            return topics
        return [
            {
                "title": f"{entity.name} 核心优势",
                "question": f"{entity.name} 的核心优势是什么？",
                "evidence": "当前问题样本不足，先从品牌核心优势开始补内容。",
            }
        ]

    def _top_opportunity(
        self,
        *,
        official_rate: float | None,
        mention_rate: float | None,
        external_domains: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if official_rate is not None and official_rate < 0.05:
            return {
                "title": "发布官网证据页",
                "target_metric": "official_citation_rate",
                "reason": f"官网引用率为 {_percent(official_rate)}",
            }
        if mention_rate is not None and mention_rate < 0.5:
            return {
                "title": "补齐未提及问题内容",
                "target_metric": "mention_rate",
                "reason": f"AI 提及率为 {_percent(mention_rate)}",
            }
        if external_domains:
            return {
                "title": "对齐高频外部来源",
                "target_metric": "official_citation_rate",
                "reason": f"{external_domains[0]['domain']} 是当前高频来源",
            }
        return {"title": "保持样本更新", "target_metric": "mention_rate", "reason": ""}

    def _top_risk(
        self,
        *,
        sentiment_counts: dict[str, int],
        ranking_rows: list[dict[str, Any]],
        target_rank: int | None,
        ranking_sufficiency: dict[str, Any],
    ) -> dict[str, Any]:
        if sentiment_counts.get("negative", 0) > 0:
            return {
                "title": "修正负向场景内容",
                "target_metric": "sentiment_distribution",
                "reason": f"{sentiment_counts['negative']} 条负向提及",
            }
        if not ranking_sufficiency["is_comparable"]:
            return {
                "title": "补竞品同场样本",
                "target_metric": "mention_ranking",
                "reason": str(ranking_sufficiency.get("rank_status_label") or ""),
            }
        if target_rank and target_rank > 1:
            leader = ranking_rows[0]["brand_name"] if ranking_rows else ""
            return {
                "title": "补竞品对照内容",
                "target_metric": "mention_ranking",
                "reason": f"当前排名第 {target_rank}，领先品牌为 {leader}",
            }
        return {
            "title": "暂无高优先级风险",
            "target_metric": "mention_rate",
            "reason": "",
        }

    def _recommendations(
        self,
        *,
        entity: Entity,
        mention_rate: float | None,
        official_rate: float | None,
        sentiment_counts: dict[str, int],
        external_domains: list[dict[str, Any]],
        platform_source_targets: list[dict[str, Any]],
        ranking_rows: list[dict[str, Any]],
        ranking_sufficiency: dict[str, Any],
        monitoring_count: int,
        action_queue: list[dict[str, Any]],
        denominator: int,
        numerator: int,
        sample_ready: bool,
        content_topics: list[dict[str, str]],
        unmentioned_answer_samples: list[dict[str, Any]],
        recommendation_tasks: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not sample_ready:
            return []

        recommendations: list[dict[str, Any]] = []
        official_domain = primary_official_domain(entity)
        distribution_targets = _content_distribution_targets(
            official_domain=official_domain,
            external_domains=external_domains,
            platform_source_targets=platform_source_targets,
        )
        content_directions = _content_directions(
            entity=entity,
            topics=content_topics,
            metric_label="AI 提及率",
        )

        if mention_rate is None or mention_rate < 0.6:
            sample_question = (
                str(unmentioned_answer_samples[0].get("question") or "")
                if unmentioned_answer_samples
                else str(
                    (content_topics[0] if content_topics else {}).get("question") or ""
                )
            )
            recommendations.append(
                {
                    "id": "mention-rate-content-gap",
                    "title": "补齐未提及问题的内容包",
                    "target_metric": "mention_rate",
                    "reason": (
                        f"AI 提及率为 {_percent(mention_rate)}，"
                        f"{denominator} 条答案样本里 {numerator} 条提到 {entity.name}。"
                    ),
                    "impact": "让用户高频问题里更容易出现品牌优势和适用场景。",
                    "priority": "high",
                    "next_action": "ask_chat",
                    "cta_label": "生成内容草稿",
                    "content_brief": (
                        f"围绕未提及问题写内容，先回答用户真实会问的场景，再补 {entity.name} "
                        "的优势、证据和边界。"
                    ),
                    "content_format": "场景问答内容包",
                    "content_directions": content_directions,
                    "distribution_targets": distribution_targets,
                    "execution_steps": _execution_steps(
                        metric_label="AI 提及率",
                        content_format="场景问答内容包",
                        targets=distribution_targets,
                    ),
                    "content_generation_brief": _content_generation_brief(
                        brand_name=entity.name,
                        target_metric="AI 提及率",
                        content_format="场景问答内容包",
                        content_brief=(
                            "补齐 AI 回答未提及品牌的高频问题。"
                            f"优先问题：{sample_question}"
                        ),
                    ),
                    "evidence_refs": [
                        item.get("question")
                        for item in unmentioned_answer_samples[:3]
                        if item.get("question")
                    ],
                }
            )

        if official_rate is None or official_rate < 0.1:
            official_targets = [
                target for target in distribution_targets if target["role"] == "官网"
            ] or distribution_targets[:1]
            official_directions = _content_directions(
                entity=entity,
                topics=content_topics,
                metric_label="官网引用率",
            )
            recommendations.append(
                {
                    "id": "official-citation-gap",
                    "title": "发布官网证据页",
                    "target_metric": "official_citation_rate",
                    "reason": (
                        f"官网引用率为 {_percent(official_rate)}。"
                        "AI 现在更依赖外部来源而不是官网。"
                    ),
                    "impact": "让 AI 回答有机会引用品牌自己的可核验材料。",
                    "priority": "high",
                    "next_action": "ask_chat",
                    "cta_label": "生成官网内容",
                    "content_brief": (
                        "把官网做成可引用的证据页：用户场景、产品事实、对比边界、"
                        "常见问题和更新时间要写清楚。"
                    ),
                    "content_format": "官网证据页",
                    "content_directions": official_directions,
                    "distribution_targets": official_targets,
                    "execution_steps": _execution_steps(
                        metric_label="官网引用率",
                        content_format="官网证据页",
                        targets=official_targets,
                    ),
                    "content_generation_brief": _content_generation_brief(
                        brand_name=entity.name,
                        target_metric="官网引用率",
                        content_format="官网证据页",
                        content_brief="写一页让 AI 容易引用的官网内容，主题必须来自当前问题样本。",
                    ),
                    "evidence_refs": [
                        f"官网引用率 {_percent(official_rate)}",
                        *[
                            f"{item['domain']} 引用 {item['citation_count']} 次"
                            for item in external_domains[:2]
                        ],
                    ],
                }
            )
        if not ranking_sufficiency["is_comparable"]:
            ranking_directions = _content_directions(
                entity=entity,
                topics=content_topics,
                metric_label="提及排名",
            )
            recommendations.append(
                {
                    "id": "competitor-sample-gap",
                    "title": "补竞品对照内容",
                    "target_metric": "mention_ranking",
                    "reason": "当前竞品样本不足，排名只能作为初步观察。",
                    "impact": "让用户看到品牌和竞品在同一问题里的差异。",
                    "priority": "medium",
                    "next_action": "ask_chat",
                    "cta_label": "生成对照内容",
                    "content_brief": (
                        "围绕同一批用户问题写品牌与竞品对照，重点解释适合谁、不适合谁、"
                        "差异证据是什么。"
                    ),
                    "content_format": "竞品对照问答",
                    "content_directions": ranking_directions,
                    "distribution_targets": distribution_targets,
                    "execution_steps": _execution_steps(
                        metric_label="提及排名",
                        content_format="竞品对照问答",
                        targets=distribution_targets,
                    ),
                    "content_generation_brief": _content_generation_brief(
                        brand_name=entity.name,
                        target_metric="提及排名",
                        content_format="竞品对照问答",
                        content_brief="写同场景下的品牌与竞品对照内容，不夸大排名。",
                    ),
                    "evidence_refs": [
                        f"当前可比品牌 {max(len(ranking_rows) - 1, 0)} 个"
                    ],
                }
            )
        if sentiment_counts.get("negative", 0) > 0:
            sentiment_directions = _content_directions(
                entity=entity,
                topics=content_topics,
                metric_label="语气性质",
            )
            recommendations.append(
                {
                    "id": "negative-mentions",
                    "title": "修正负向场景内容",
                    "target_metric": "sentiment_distribution",
                    "reason": f"{sentiment_counts['negative']} 条回答带有负向语气。",
                    "impact": "优先解释争议场景，减少含糊或负向表述继续扩散。",
                    "priority": "high",
                    "next_action": "ask_chat",
                    "cta_label": "生成修正内容",
                    "content_brief": (
                        "针对负向或含糊回答写澄清内容：承认边界，补事实，说明适用场景。"
                    ),
                    "content_format": "争议场景澄清页",
                    "content_directions": sentiment_directions,
                    "distribution_targets": distribution_targets,
                    "execution_steps": _execution_steps(
                        metric_label="语气性质",
                        content_format="争议场景澄清页",
                        targets=distribution_targets,
                    ),
                    "content_generation_brief": _content_generation_brief(
                        brand_name=entity.name,
                        target_metric="语气性质",
                        content_format="争议场景澄清页",
                        content_brief="写一版用于修正负向或含糊回答的内容。",
                    ),
                    "evidence_refs": [f"{sentiment_counts['negative']} 条负向提及"],
                }
            )
        if external_domains:
            top_domain = external_domains[0]["domain"]
            top_source_name = _distribution_target_name(top_domain)
            external_targets = [
                target
                for target in distribution_targets
                if target.get("domain") == top_domain
            ] or distribution_targets[:3]
            recommendations.append(
                {
                    "id": "external-source-check",
                    "title": "对齐高频外部来源",
                    "target_metric": "official_citation_rate",
                    "reason": f"{top_source_name}是当前高频引用来源。",
                    "impact": "把已被 AI 引用的外部来源变成可持续校准的内容阵地。",
                    "priority": "medium",
                    "next_action": "ask_chat",
                    "cta_label": "生成外部投放稿",
                    "content_brief": (
                        f"围绕 {top_source_name} 这类高频来源准备可投放或可对齐的内容，"
                        "重点是事实更新、优势证据和常见问题。"
                    ),
                    "content_format": "外部来源投放稿",
                    "content_directions": content_directions,
                    "distribution_targets": external_targets,
                    "execution_steps": _execution_steps(
                        metric_label="官网引用率",
                        content_format="外部来源投放稿",
                        targets=external_targets,
                    ),
                    "content_generation_brief": _content_generation_brief(
                        brand_name=entity.name,
                        target_metric="官网引用率",
                        content_format="外部来源投放稿",
                        content_brief=(
                            f"面向 {top_source_name} 这类外部来源写可发布内容，"
                            "让事实和优势更容易被 AI 引用。"
                        ),
                    ),
                    "evidence_refs": [
                        f"{top_source_name} 引用 {external_domains[0]['citation_count']} 次"
                    ],
                }
            )
        if monitoring_count == 0:
            recommendations.append(
                {
                    "id": "open-monitoring",
                    "title": "建立周期复查",
                    "target_metric": "mention_rate",
                    "reason": f"跟踪 {entity.name} 的提及率、排名、官网引用率和语气变化。",
                    "impact": "验证内容发布后，AI 回答是否真的发生变化。",
                    "priority": "medium",
                    "next_action": "open_monitoring_settings",
                    "cta_label": "打开监测设置",
                    "content_brief": "内容发布后按周期复查指标变化。",
                    "content_format": "周期复查",
                    "content_directions": [],
                    "distribution_targets": [],
                    "execution_steps": [
                        "选择监测品牌和平台。",
                        "确认执行频率。",
                        "内容发布后对比提及率、排名、官网引用率和语气变化。",
                    ],
                    "content_generation_brief": "",
                    "evidence_refs": ["复查 AI 提及率、提及排名、官网引用率和语气性质"],
                }
            )
        if not recommendations and action_queue:
            recommendations.append(
                {
                    "id": "review-pending-work",
                    "title": "确认待处理事项",
                    "target_metric": "mention_rate",
                    "reason": "当前有建议等待确认。",
                    "impact": "确认后可继续补充样本和来源。",
                    "priority": "medium",
                    "next_action": "ask_chat",
                    "cta_label": "查看建议",
                    "content_brief": "先确认已有事项，再决定是否生成内容。",
                    "content_format": "待确认事项",
                    "content_directions": [],
                    "distribution_targets": [],
                    "execution_steps": ["确认已有事项。", "再决定是否生成内容或补充样本。"],
                    "content_generation_brief": "",
                    "evidence_refs": [],
                }
            )
        return [
            _attach_recommendation_task_state(item, recommendation_tasks)
            for item in recommendations[:6]
        ]

    def _graph_projection(
        self,
        *,
        entity: Entity,
        summary: dict[str, Any],
        evidence: dict[str, Any],
        recommendations: list[dict[str, Any]],
        platform_rows: list[dict[str, Any]],
        ranking_rows: list[dict[str, Any]],
        external_domains: list[dict[str, Any]],
        latest_metric: BrandMetricSnapshot | None,
    ) -> dict[str, Any]:
        brand_id = f"brand:{entity.id}"
        nodes: list[dict[str, Any]] = [
            {
                "id": brand_id,
                "type": "brand",
                "label": entity.name,
                "level": 0,
                "summary": entity.domain,
                "business_meaning": "当前品牌是所有指标、竞品、平台、来源和建议的中心。",
                "evidence_count": int(
                    (summary.get("sample_scope") or {}).get("answer_count") or 0
                ),
                "next_actions": [],
            }
        ]
        edges: list[dict[str, Any]] = []

        def add_node(
            node_id: str,
            node_type: str,
            label: str,
            *,
            level: int,
            metric_key: str | None = None,
            summary_text: str = "",
            value: str | None = None,
            parent_id: str | None = None,
            business_meaning: str = "",
            evidence_count: int = 0,
            next_actions: list[dict[str, Any]] | None = None,
        ) -> None:
            nodes.append(
                {
                    "id": node_id,
                    "type": node_type,
                    "label": label,
                    "level": level,
                    "metric_key": metric_key,
                    "summary": summary_text,
                    "value": value,
                    "parent_id": parent_id,
                    "business_meaning": business_meaning,
                    "evidence_count": int(evidence_count or 0),
                    "next_actions": list(next_actions or []),
                }
            )

        def add_edge(
            source: str,
            target: str,
            label: str,
            *,
            relation_type: str,
            strength: str = "strong",
            business_meaning: str = "",
            evidence_count: int = 0,
        ) -> None:
            edges.append(
                {
                    "id": f"{source}->{target}",
                    "from": source,
                    "to": target,
                    "label": label,
                    "type": relation_type,
                    "strength": strength,
                    "business_meaning": business_meaning,
                    "evidence_count": int(evidence_count or 0),
                }
            )

        metric_nodes = [
            ("metric:mention_rate", "AI 提及率", "mention_rate"),
            ("metric:mention_ranking", "提及排名", "mention_ranking"),
            ("metric:official_citation_rate", "官网引用率", "official_citation_rate"),
            ("metric:sentiment_distribution", "语气性质", "sentiment_distribution"),
        ]
        metrics = summary.get("metrics") or {}
        for node_id, label, key in metric_nodes:
            metric = metrics.get(key) or {}
            add_node(
                node_id,
                "metric",
                label,
                level=1,
                metric_key=key,
                summary_text=str(metric.get("label") or label),
                value=(
                    str(metric.get("display_value"))
                    if metric.get("display_value") is not None
                    else None
                ),
                parent_id=brand_id,
                business_meaning=_metric_business_meaning(key, metric),
                evidence_count=int(
                    metric.get("denominator") or metric.get("total") or 0
                ),
                next_actions=_metric_next_actions(key, recommendations),
            )
            add_edge(
                brand_id,
                node_id,
                "指标",
                relation_type="measures",
                business_meaning=f"{label}用于判断品牌在 AI 回答里的表现。",
                evidence_count=int(
                    metric.get("denominator") or metric.get("total") or 0
                ),
            )

        group_nodes = [
            ("group:competitors", "竞品", "competitors"),
            ("group:platforms", "AI 平台", "platforms"),
            ("group:sources", "引用来源", "sources"),
            ("group:recommendations", "建议", "recommendations"),
        ]
        for node_id, label, group_key in group_nodes:
            add_node(
                node_id,
                "group",
                label,
                level=1,
                summary_text="",
                parent_id=brand_id,
                business_meaning=_group_business_meaning(group_key),
            )
            add_edge(
                brand_id,
                node_id,
                "关联",
                relation_type=group_key,
                business_meaning=_group_business_meaning(group_key),
            )

        for row in platform_rows[:8]:
            node_id = f"platform:{row['platform']}"
            add_node(
                node_id,
                "platform",
                str(row["platform"]),
                level=2,
                metric_key="mention_rate",
                summary_text=f"{row['mention_count']} / {row['answer_count']} 条答案样本提及",
                value=_percent(row.get("mention_rate")),
                parent_id="metric:mention_rate",
                business_meaning=(
                    f"{row['platform']} 上 {row['answer_count']} 条答案样本里，"
                    f"{row['mention_count']} 条提到品牌。"
                ),
                evidence_count=int(row.get("answer_count") or 0),
            )
            add_edge(
                "metric:mention_rate",
                node_id,
                "平台拆分",
                relation_type="breakdown",
                business_meaning="按 AI 平台拆解提及率来源。",
                evidence_count=int(row.get("answer_count") or 0),
            )
            add_edge(
                "group:platforms",
                node_id,
                "包含",
                relation_type="contains",
                business_meaning="该平台参与了当前品牌情报样本。",
                evidence_count=int(row.get("answer_count") or 0),
            )

        for row in ranking_rows[:8]:
            if row["is_current_brand"]:
                continue
            node_id = f"competitor:{row['brand_id']}"
            rank_summary = (
                f"排名第 {row['rank']}"
                if summary.get("metrics", {})
                .get("mention_ranking", {})
                .get("sample_sufficiency", {})
                .get("is_comparable")
                else "竞品样本不足"
            )
            add_node(
                node_id,
                "competitor",
                str(row["brand_name"]),
                level=2,
                metric_key="mention_ranking",
                summary_text=rank_summary,
                value=_percent(row.get("mention_rate")),
                parent_id="metric:mention_ranking",
                business_meaning=(
                    f"{row['brand_name']} 是当前品牌的竞品样本，"
                    "用于判断同场景下的提及差异。"
                ),
                evidence_count=int(row.get("sample_count") or 0),
            )
            add_edge(
                "metric:mention_ranking",
                node_id,
                "竞争比较",
                relation_type="compares",
                business_meaning="该竞品参与提及排名的同场景比较。",
                evidence_count=int(row.get("sample_count") or 0),
            )
            add_edge(
                "group:competitors",
                node_id,
                "包含",
                relation_type="contains",
                business_meaning="该竞品属于当前可观察的竞争样本。",
                evidence_count=int(row.get("sample_count") or 0),
            )

        official_detail = evidence.get("official_citation_detail", {}) or {}
        official_domains = [
            str(domain)
            for domain in (official_detail.get("official_domains") or [])
            if domain
        ]
        official_citation_count = int(official_detail.get("official_citation_count") or 0)
        official_node_domain = official_domains[0] if official_domains else primary_official_domain(entity)
        add_node(
            f"official_domain:{official_node_domain or entity.id}",
            "official_domain",
            official_node_domain or "品牌官网",
            level=2,
            metric_key="official_citation_rate",
            summary_text=f"官网引用 {official_citation_count} 次",
            value=str(official_citation_count),
            parent_id="metric:official_citation_rate",
            business_meaning="品牌官网能否成为 AI 回答依据，决定自有信息的可见度。",
            evidence_count=official_citation_count,
        )
        add_edge(
            "metric:official_citation_rate",
            f"official_domain:{official_node_domain or entity.id}",
            "官网引用",
            relation_type="official_source",
            business_meaning="官网被 AI 回答引用时，会支撑品牌自有叙事进入答案。",
            evidence_count=official_citation_count,
        )
        add_edge(
            "group:sources",
            f"official_domain:{official_node_domain or entity.id}",
            "包含",
            relation_type="contains",
            business_meaning="官网属于品牌自有来源。",
            evidence_count=official_citation_count,
        )

        for row in external_domains[:8]:
            node_id = f"domain:{row['domain']}"
            add_node(
                node_id,
                "source_domain",
                str(row["domain"]),
                level=2,
                metric_key="official_citation_rate",
                summary_text=f"{row['citation_count']} 次引用",
                value=str(row["citation_count"]),
                parent_id="metric:official_citation_rate",
                business_meaning=(
                    f"{row['domain']} 是 AI 回答引用的外部来源，"
                    "可用于判断外部内容阵地的影响。"
                ),
                evidence_count=int(row.get("citation_count") or 0),
            )
            add_edge(
                "metric:official_citation_rate",
                node_id,
                "外部来源",
                relation_type="cites",
                business_meaning="AI 回答通过该外部来源形成品牌判断。",
                evidence_count=int(row.get("citation_count") or 0),
            )
            add_edge(
                "group:sources",
                node_id,
                "包含",
                relation_type="contains",
                business_meaning="该域名属于当前引用来源。",
                evidence_count=int(row.get("citation_count") or 0),
            )

        sentiment_summary = evidence.get("sentiment_detail", {}).get("summary", {})
        sentiment_detail = evidence.get("sentiment_detail", {}) or {}
        for key, label in (
            ("positive", "正向"),
            ("neutral", "中性"),
            ("negative", "负向"),
        ):
            node_id = f"sentiment:{key}"
            add_node(
                node_id,
                "sentiment",
                label,
                level=2,
                metric_key="sentiment_distribution",
                summary_text=f"{int(sentiment_summary.get(key) or 0)} 条",
                value=str(int(sentiment_summary.get(key) or 0)),
                parent_id="metric:sentiment_distribution",
                business_meaning=f"{label}回答反映 AI 提到品牌时的描述倾向。",
                evidence_count=int(sentiment_summary.get(key) or 0),
            )
            add_edge(
                "metric:sentiment_distribution",
                node_id,
                "语气拆分",
                relation_type="breakdown",
                business_meaning=f"把已提及品牌的回答拆成{label}样本。",
                evidence_count=int(sentiment_summary.get(key) or 0),
            )
            for sample_index, sample in enumerate((sentiment_detail.get(key) or [])[:2]):
                sample_node_id = (
                    f"answer_sample:{key}:"
                    f"{sample.get('answer_id') or sample_index}"
                )
                sample_text = _preview(
                    str(
                        sample.get("mention_quote")
                        or sample.get("answer_preview")
                        or sample.get("question")
                        or ""
                    ),
                    54,
                )
                add_node(
                    sample_node_id,
                    "answer_sample",
                    f"{label}样本",
                    level=2,
                    metric_key="sentiment_distribution",
                    summary_text=sample_text,
                    value=str(sample.get("platform") or ""),
                    parent_id="metric:sentiment_distribution",
                    business_meaning="这是一条代表性回答摘录，用于解释语气判断。",
                    evidence_count=1,
                )
                add_edge(
                    "metric:sentiment_distribution",
                    sample_node_id,
                    "回答样本",
                    relation_type="evidence_sample",
                    business_meaning="该回答样本支撑语气性质判断。",
                    evidence_count=1,
                )

        for item in recommendations[:5]:
            node_id = f"recommendation:{item['id']}"
            add_node(
                node_id,
                "recommendation",
                str(item["title"]),
                level=2,
                metric_key=str(item.get("target_metric") or ""),
                summary_text=str(item.get("reason") or ""),
                parent_id="group:recommendations",
                business_meaning=str(
                    item.get("expected_impact")
                    or item.get("impact")
                    or item.get("reason")
                    or ""
                ),
                evidence_count=len(item.get("evidence_refs") or []),
                next_actions=[
                    {
                        "label": item.get("cta_label") or "加入跟进",
                        "action": item.get("next_action") or "ask_chat",
                    }
                ],
            )
            add_edge(
                "group:recommendations",
                node_id,
                "建议",
                relation_type="recommends",
                business_meaning="这条建议可转为后续跟进任务。",
                evidence_count=len(item.get("evidence_refs") or []),
            )
        return {
            "nodes": nodes,
            "edges": edges,
            "default_focus": brand_id,
            "metric_snapshot_id": str(latest_metric.id) if latest_metric else None,
            "expand_rules": [
                {"from_type": "metric", "show_levels": [1, 2]},
                {"from_type": "group", "show_levels": [1, 2]},
            ],
        }


def _metric_business_meaning(key: str, metric: dict[str, Any]) -> str:
    if key == "mention_rate":
        return (
            f"当前样本 {metric.get('denominator') or 0} 条答案里，"
            f"{metric.get('numerator') or 0} 条提到品牌。"
        )
    if key == "mention_ranking":
        sufficiency = metric.get("sample_sufficiency") or {}
        if sufficiency.get("is_comparable") is False:
            return str(
                sufficiency.get("rank_reason")
                or "当前样本不足，排名只能作为观察。"
            )
        return "在同一批问题和平台下比较品牌与竞品的提及率。"
    if key == "official_citation_rate":
        return (
            f"当前样本 {metric.get('denominator') or 0} 次引用里，"
            f"{metric.get('numerator') or 0} 次来自品牌官网。"
        )
    if key == "sentiment_distribution":
        return "只统计已提及品牌的回答，观察正向、中性、负向描述。"
    return ""


def _metric_next_actions(
    key: str,
    recommendations: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in recommendations:
        if str(item.get("target_metric") or "") != key:
            continue
        actions.append(
            {
                "label": item.get("cta_label") or "加入跟进",
                "recommendation_id": item.get("id"),
                "action": item.get("next_action") or "ask_chat",
            }
        )
    return actions[:3]


def _group_business_meaning(group_key: str) -> str:
    return {
        "competitors": "竞品用于解释品牌在同场景问题里的相对位置。",
        "platforms": "AI 平台用于拆解不同回答入口里的品牌可见度。",
        "sources": "引用来源用于判断 AI 回答凭什么形成品牌判断。",
        "recommendations": "建议把情报转成可执行、可复查的后续任务。",
    }.get(group_key, "该分组用于组织品牌情报关系。")


def _content_distribution_targets(
    *,
    official_domain: str,
    external_domains: list[dict[str, Any]],
    platform_source_targets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    def add_target(
        *,
        name: str,
        role: str,
        reason: str,
        domain: str = "",
        platform: str = "",
    ) -> None:
        if not name:
            return
        if domain and role != "官网" and not _is_distribution_domain(domain):
            return
        key = (role, domain or name)
        if key in seen:
            return
        seen.add(key)
        targets.append(
            {
                "name": name,
                "role": role,
                "domain": domain,
                "platform": platform,
                "reason": reason,
            }
        )

    add_target(
        name=official_domain or "品牌官网",
        role="官网",
        domain=official_domain,
        reason="品牌自有来源，适合承载可核验事实和更新时间。",
    )

    for row in platform_source_targets[:4]:
        domain = str(row.get("domain") or "")
        add_target(
            name=_distribution_target_name(domain),
            role="外部来源",
            domain=domain,
            platform=str(row.get("platform") or ""),
            reason=str(row.get("reason") or ""),
        )

    for row in external_domains[:3]:
        domain = str(row.get("domain") or "")
        add_target(
            name=_distribution_target_name(domain),
            role="外部来源",
            domain=domain,
            reason=f"当前样本被引用 {int(row.get('citation_count') or 0)} 次。",
        )
    return targets[:6]


def _content_directions(
    *,
    entity: Entity,
    topics: list[dict[str, str]],
    metric_label: str,
) -> list[dict[str, str]]:
    directions: list[dict[str, str]] = []
    for topic in topics[:3]:
        title = topic.get("title") or topic.get("question") or f"{entity.name} 核心优势"
        question = topic.get("question") or title
        directions.append(
            {
                "title": title,
                "angle": (
                    f"回答「{question}」，写清 {entity.name} 的适用人群、"
                    "核心优势、事实依据和不适用边界。"
                ),
                "evidence": topic.get("evidence") or f"关联指标: {metric_label}",
            }
        )
    return directions


def _execution_steps(
    *,
    metric_label: str,
    content_format: str,
    targets: list[dict[str, Any]],
) -> list[str]:
    first_target = targets[0].get("name") if targets else "品牌官网"
    return [
        f"确认要补强的指标：{metric_label}。",
        f"生成一版{content_format}，每个主张都保留事实依据。",
        f"优先发布到{first_target}，再观察 AI 回答是否更新。",
    ]


def _content_generation_brief(
    *,
    brand_name: str,
    target_metric: str,
    content_format: str,
    content_brief: str,
) -> str:
    return (
        f"为{brand_name}生成{content_format}，目标是改善{target_metric}。"
        f"{content_brief} 内容必须包含适用场景、事实依据、不适用边界和复查指标。"
    )


def _topic_title(question_text: str) -> str:
    text = _preview(question_text, 34)
    for suffix in ("？", "?", "。", "."):
        text = text.rstrip(suffix)
    if len(text) > 26:
        return text[:25] + "..."
    return text


def _looks_like_internal_id(value: str) -> bool:
    normalized = _normalized_question_key(value)
    if not normalized:
        return False
    compact = normalized.replace("_", "").replace("-", "")
    return bool(
        compact.isdigit()
        or (compact.startswith("q") and compact[1:].isdigit())
        or (compact.startswith("id") and compact[2:].isdigit())
    )


def _sentiment_counts(mentions: list[BrandMention]) -> dict[str, int]:
    counts = Counter(mention.sentiment or "neutral" for mention in mentions)
    total = sum(counts.values())
    return {
        "positive": int(counts.get("positive") or 0),
        "neutral": int(counts.get("neutral") or 0),
        "negative": int(counts.get("negative") or 0),
        "total": total,
        "dominant_sentiment": (
            max(("positive", "neutral", "negative"), key=lambda key: counts.get(key, 0))
            if total
            else "neutral"
        ),
    }


def _metric_sample_sufficiency(
    *,
    metric_key: str,
    denominator: int,
    numerator: int,
) -> dict[str, Any]:
    if denominator <= 0:
        return {
            "is_comparable": False,
            "status": "no_sample",
            "status_label": "暂无可分析样本",
            "reason": "当前还没有可用于判断的答案或引用样本。",
            "sample_count": 0,
            "evidence_count": 0,
        }
    if metric_key == "sentiment_distribution" and numerator <= 0:
        return {
            "is_comparable": False,
            "status": "no_mention_sample",
            "status_label": "暂无提及样本",
            "reason": "语气性质只统计已经提到品牌的回答。",
            "sample_count": denominator,
            "evidence_count": numerator,
        }
    return {
        "is_comparable": True,
        "status": "formed",
        "status_label": "样本已形成",
        "reason": "当前样本可以用于展示该指标。",
        "sample_count": denominator,
        "evidence_count": numerator,
    }


def _sample_quality(
    *,
    metric_key: str,
    sample_count: int,
    evidence_count: int,
    excluded_count: int,
) -> dict[str, Any]:
    status = "formed" if sample_count > 0 else "no_sample"
    return {
        "metric_key": metric_key,
        "status": status,
        "status_label": "样本已形成" if status == "formed" else "暂无可分析样本",
        "sample_count": max(int(sample_count or 0), 0),
        "evidence_count": max(int(evidence_count or 0), 0),
        "excluded_unreadable_count": max(int(excluded_count or 0), 0),
    }


def _recommendation_sample_status(
    *,
    question_count: int,
    answer_count: int,
    platform_count: int,
) -> dict[str, Any]:
    if question_count <= 0:
        return {
            "is_ready": False,
            "status": "needs_question_samples",
            "status_label": "等待问题样本",
            "reason": "还没有可用于采集的品牌问题，先生成问题并抓取答案后再生成跟进建议。",
            "question_count": 0,
            "answer_count": 0,
            "platform_count": max(int(platform_count or 0), 0),
        }
    if answer_count <= 0:
        return {
            "is_ready": False,
            "status": "needs_answer_samples",
            "status_label": "等待答案样本",
            "reason": "还没有可分析的 AI 回答，先抓取答案后再生成跟进建议。",
            "question_count": max(int(question_count or 0), 0),
            "answer_count": 0,
            "platform_count": max(int(platform_count or 0), 0),
        }
    return {
        "is_ready": True,
        "status": "ready",
        "status_label": "可以生成建议",
        "reason": "已存在可分析的 AI 回答样本。",
        "question_count": max(int(question_count or 0), 0),
        "answer_count": max(int(answer_count or 0), 0),
        "platform_count": max(int(platform_count or 0), 0),
    }


def _attach_recommendation_task_state(
    item: dict[str, Any],
    task_summary: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    recommendation = dict(item)
    task = task_summary.get(str(item.get("id") or "")) or {}
    recommendation["task_state"] = task.get("task_state") or "not_started"
    recommendation["owner_label"] = task.get("owner_label") or ""
    recommendation["due_at"] = task.get("due_at") or ""
    recommendation["review_at"] = task.get("review_at") or ""
    recommendation["latest_feedback_at"] = task.get("latest_feedback_at")
    recommendation["expected_impact"] = (
        recommendation.get("expected_impact")
        or recommendation.get("impact")
        or _expected_impact_for_metric(str(recommendation.get("target_metric") or ""))
    )
    recommendation["review_criteria"] = recommendation.get(
        "review_criteria"
    ) or _review_criteria_for_metric(str(recommendation.get("target_metric") or ""))
    return recommendation


def _expected_impact_for_metric(target_metric: str) -> str:
    return {
        "mention_rate": "提升高价值问题里品牌被提到的机会。",
        "mention_ranking": "让品牌和竞品能在同一批问题里被稳定比较。",
        "official_citation_rate": "提高官网成为 AI 回答依据的机会。",
        "sentiment_distribution": "减少含糊或负向回答继续扩散。",
    }.get(target_metric, "帮助下一轮品牌情报复查。")


def _review_criteria_for_metric(target_metric: str) -> str:
    return {
        "mention_rate": "下一轮复查 AI 提及率和未提及问题是否减少。",
        "mention_ranking": "下一轮复查同场景竞品样本是否充足、排名是否形成。",
        "official_citation_rate": "下一轮复查官网引用次数和外部来源占比。",
        "sentiment_distribution": "下一轮复查负向样本是否减少，正向和中性描述是否更清晰。",
    }.get(target_metric, "下一轮复查相关指标和证据变化。")


def _public_recommendation_task_state(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    return {
        "todo": "not_started",
        "not_started": "not_started",
        "submitted": "not_started",
        "in_progress": "in_progress",
        "doing": "in_progress",
        "completed": "completed",
        "done": "completed",
        "review_pending": "review_pending",
        "review": "review_pending",
    }.get(normalized, normalized or "not_started")


def _safe_public_text(value: Any, limit: int) -> str:
    return _preview(value, limit) if value is not None else ""


def _citation_sample(citation: BrandCitationSource) -> dict[str, Any]:
    return {
        "citation_id": str(citation.id),
        "url": citation.url,
        "domain": citation.domain,
        "title": citation.source_title or citation.domain,
        "snippet_preview": _preview(citation.snippet, 180),
        "confidence": citation.confidence,
    }


def _unique_domains(citations: list[BrandCitationSource], limit: int = 5) -> list[str]:
    domains: list[str] = []
    seen: set[str] = set()
    for citation in citations:
        domain = str(citation.domain or "").strip()
        if not domain:
            continue
        normalized = _normalize_domain(domain)
        if normalized in seen:
            continue
        seen.add(normalized)
        domains.append(domain)
        if len(domains) >= limit:
            break
    return domains


def _preview(value: Any, limit: int) -> str:
    text = _repair_mojibake(str(value or ""))
    text = _strip_internal_evidence_text(text)
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "..."


def _strip_internal_evidence_text(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = re.sub(
        r"[^。！？.!?]*web[_\s-]*search(?:\s*工具)?[^。！？.!?]*(?:[。！？.!?]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"[^。！？.!?]*(?:调用工具|工具调用|浏览器工具|推理过程|思考过程|内部过程|调度日志|模型过程)[^。！？.!?]*(?:[。！？.!?]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"[^。！？.!?]*(?:作为\s*AI|我将|首先我需要|接下来我会)[^。！？.!?]*(?:[。！？.!?]|$)",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    kept_lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(pattern.search(line) for pattern in INTERNAL_EVIDENCE_PATTERNS):
            continue
        kept_lines.append(line)
    if kept_lines:
        return " ".join(kept_lines)
    if any(pattern.search(text) for pattern in INTERNAL_EVIDENCE_PATTERNS):
        return ""
    return text


def _repair_mojibake(value: str) -> str:
    text = str(value or "")
    if not text:
        return ""
    if not any(marker in text for marker in ("Ã", "Â", "â", "å", "ç", "è", "\x80")):
        return text
    try:
        repaired = text.encode("latin1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    if _readability_score(repaired) > _readability_score(text) + 3:
        return repaired
    return text


def _readability_score(value: str) -> int:
    cjk_count = sum(1 for char in value if "\u4e00" <= char <= "\u9fff")
    mojibake_penalty = sum(
        value.count(marker) for marker in ("Ã", "Â", "â", "å", "ç", "è")
    )
    control_penalty = sum(
        1 for char in value if ord(char) < 32 or 127 <= ord(char) <= 159
    )
    return cjk_count * 2 - mojibake_penalty - control_penalty


def _question_text_for_answer(
    answer: BrandPlatformAnswer,
    questions: dict[UUID, BrandIntelligenceQuestion],
    question: BrandIntelligenceQuestion | None = None,
) -> str:
    if question is not None and question.question_text:
        text = _clean_question_text(question.question_text)
        if text:
            return text
    if answer.question_object_id is not None:
        direct_question = questions.get(answer.question_object_id)
        if direct_question is not None and direct_question.question_text:
            text = _clean_question_text(direct_question.question_text)
            if text:
                return text

    answer_question_key = _normalized_question_key(answer.question_id)
    for candidate in questions.values():
        if _normalized_question_key(candidate.question_id) == answer_question_key:
            text = _clean_question_text(candidate.question_text)
            if text:
                return text

    for payload in (answer.answer_payload, answer.raw_payload):
        text = _first_payload_text(payload, "question_text", "question", "query")
        text = _clean_question_text(text)
        if text:
            return text
    return ""


def _answer_text_for_sample(answer: BrandPlatformAnswer, limit: int = 220) -> str:
    text = _preview(answer.answer_text, limit)
    if text:
        return text
    for payload in (answer.answer_payload, answer.raw_payload):
        text = _first_payload_text(payload, "content", "text", "answer")
        if text:
            return _preview(text, limit)
        nested_answer = payload.get("answer") if isinstance(payload, dict) else None
        text = _first_payload_text(nested_answer, "content", "text", "answer")
        if text:
            return _preview(text, limit)
    return ""


def _first_payload_text(payload: Any, *keys: str) -> str:
    if isinstance(payload, str):
        return " ".join(payload.split())
    if not isinstance(payload, dict):
        return ""
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return " ".join(value.split())
        if value is not None and not isinstance(value, (dict, list)):
            text = str(value).strip()
            if text:
                return " ".join(text.split())
    return ""


def _clean_question_text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if not text or _looks_like_internal_id(text):
        return ""
    return text


def _normalized_question_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    for prefix in ("pq_", "q_", "question_", "question-"):
        if text.startswith(prefix):
            return text[len(prefix) :]
    return text


def _percent(value: Any) -> str:
    if not isinstance(value, (int, float)):
        return "样本不足"
    return f"{float(value) * 100:.1f}%"


def _normalize_domain(value: str) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    domain = parsed.netloc or parsed.path
    if domain.startswith("www."):
        domain = domain[4:]
    return domain.split("/")[0].strip()


def _same_domain(left: str, right: str) -> bool:
    normalized_left = _normalize_domain(left)
    normalized_right = _normalize_domain(right)
    if not normalized_left or not normalized_right:
        return False
    return normalized_left == normalized_right


def _matches_official_domain(domain: str | None, official_domains: list[str]) -> bool:
    return domain_matches_official(domain, official_domains)


def _is_distribution_domain(domain: str) -> bool:
    normalized = _normalize_domain(domain)
    if not normalized:
        return False
    blocked_domains = {
        "ichgcp.net",
        "googleusercontent.com",
        "gstatic.com",
        "cloudfront.net",
        "aliyuncs.com",
        "qpic.cn",
        "bdstatic.com",
        "sinaimg.cn",
        "byteimg.com",
        "doubleclick.net",
    }
    if normalized in blocked_domains or any(
        normalized.endswith(f".{blocked}") for blocked in blocked_domains
    ):
        return False
    blocked_fragments = (
        "cdn",
        "static",
        "assets",
        "image",
        "img",
        "tracking",
        "analytics",
        "beacon",
    )
    return not any(fragment in normalized for fragment in blocked_fragments)


def _distribution_target_name(domain: str) -> str:
    normalized = _normalize_domain(domain)
    target_names = {
        "dongchedi.com": "懂车帝",
        "autohome.com.cn": "汽车之家",
        "pcauto.com.cn": "太平洋汽车",
        "toutiao.com": "今日头条",
        "m.toutiao.com": "今日头条",
        "iesdouyin.com": "抖音",
        "douyin.com": "抖音",
        "news.qq.com": "腾讯新闻",
        "qq.com": "腾讯新闻",
        "zhihu.com": "知乎",
        "baidu.com": "百度",
    }
    if normalized in target_names:
        return target_names[normalized]
    for suffix, label in target_names.items():
        if normalized.endswith(f".{suffix}"):
            return label
    return domain


def _platform_label(platform: str) -> str:
    labels = {
        "yuanbao": "腾讯元宝",
        "doubao": "豆包",
        "deepseek": "DeepSeek",
        "kimi": "Kimi",
        "chatgpt": "ChatGPT",
        "gpt": "ChatGPT",
    }
    return labels.get(str(platform or "").strip().lower(), platform or "AI 平台")


def _min_iso(values: list[datetime]) -> str | None:
    return min(values).isoformat() if values else None


def _max_iso(values: list[datetime]) -> str | None:
    return max(values).isoformat() if values else None
