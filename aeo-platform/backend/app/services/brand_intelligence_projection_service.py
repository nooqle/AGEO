"""Projection helpers for durable AI brand intelligence objects."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import (
    BrandAudiencePersona,
    BrandCitationSource,
    BrandCompetitorEntity,
    BrandEvidenceSet,
    BrandIntelligenceFinding,
    BrandIntelligenceQuestion,
    BrandMetricSnapshot,
    BrandMention,
    BrandPlatformAnswer,
    BrandReportVersion,
    BrandUsageScenario,
)
from app.models.entity import Entity
from app.services.brand_object_link_service import BrandObjectLinkService


@dataclass(frozen=True)
class QuestionProjection:
    question_id: str
    question_text: str
    category: str = ""
    subcategory: str = ""
    user_intent: str = ""
    decision_stage: str = ""
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class AnswerProjection:
    dedupe_key: str
    question_id: str
    platform: str
    fetch_method: str
    status: str
    success: bool
    answer_text: str
    answer_payload: dict[str, Any] | None
    raw_payload: dict[str, Any]
    run_id: str | None = None
    brand_mentioned: bool | None = None
    duration_ms: float | None = None


@dataclass(frozen=True)
class CitationProjection:
    dedupe_key: str
    answer_dedupe_key: str
    url: str = ""
    domain: str = ""
    source_title: str = ""
    snippet: str = ""
    confidence: float | None = None
    citation_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class MentionProjection:
    dedupe_key: str
    answer_dedupe_key: str | None = None
    question_id: str = ""
    platform: str = ""
    mentioned_brand_key: str = ""
    mentioned_brand_name: str = ""
    mentioned_object_type: str = ""
    mentioned_object_id: str = ""
    mention_role: str = "target_brand"
    sentiment: str = "neutral"
    quote: str = ""
    confidence: float | None = None
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class CompetitorProjection:
    competitor_key: str
    normalized_name: str
    display_name: str = ""
    website: str = ""
    competition_type: str = ""
    relevance_score: float | None = None
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class ScenarioProjection:
    scenario_key: str
    scenario_name: str
    description: str = ""
    decision_stage: str = ""
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class PersonaProjection:
    persona_id: str
    persona_name: str
    description: str = ""
    segment: str = ""
    priority: str = ""
    scenarios: tuple[ScenarioProjection, ...] = ()
    source_payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class FetchProjectionBundle:
    questions: tuple[QuestionProjection, ...]
    answers: tuple[AnswerProjection, ...]
    citations: tuple[CitationProjection, ...]


@dataclass(frozen=True)
class FindingProjection:
    finding_key: str
    title: str
    summary: str
    finding_type: str = "observation"
    severity: str = "medium"
    confidence: float | None = None
    evidence_summary: str = ""
    suggested_action_type: str = ""
    suggested_action_payload: dict[str, Any] | None = None
    source_payload: dict[str, Any] | None = None


PLATFORM_ANSWER_LIFECYCLE_ALIASES: dict[str, str] = {
    "completed": "captured",
    "success": "captured",
    "succeeded": "captured",
    "ok": "captured",
    "error": "failed",
    "timeout": "failed",
    "timed_out": "failed",
    "skipped": "failed",
    "pending": "requested",
}


class BrandIntelligenceProjectionService:
    """Builds and persists durable objects from existing workflow payloads."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.links = BrandObjectLinkService(db)

    @classmethod
    def normalize_questions(cls, payload: Any) -> tuple[QuestionProjection, ...]:
        """Normalize A3 question payloads into durable question projections."""

        raw_questions = cls._extract_question_items(payload)
        projections: list[QuestionProjection] = []
        seen: set[str] = set()
        for index, raw_item in enumerate(raw_questions, start=1):
            item = raw_item if isinstance(raw_item, dict) else {"question": raw_item}
            question_text = cls._first_text(
                item,
                "core_question",
                "question_text",
                "text",
                "question",
            )
            if not question_text:
                continue
            question_id = cls._first_text(item, "question_id", "id") or f"q_{index:03d}"
            dedupe_key = question_id.strip() or cls._stable_hash([question_text])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            projections.append(
                QuestionProjection(
                    question_id=question_id,
                    question_text=question_text,
                    category=cls._first_text(item, "category") or "",
                    subcategory=cls._first_text(item, "subcategory") or "",
                    user_intent=cls._first_text(item, "user_intent", "intent") or "",
                    decision_stage=cls._first_text(
                        item,
                        "decision_stage",
                        "stage",
                    )
                    or "",
                    source_payload=item,
                )
            )
        return tuple(projections)

    @classmethod
    def normalize_fetch_results(cls, fetch_results: Any) -> FetchProjectionBundle:
        """Normalize A4 fetch results into question, answer, and citation objects."""

        if not isinstance(fetch_results, list):
            return FetchProjectionBundle(questions=(), answers=(), citations=())

        questions_by_id: dict[str, QuestionProjection] = {}
        answers: list[AnswerProjection] = []
        citations: list[CitationProjection] = []

        for question_index, question_result in enumerate(fetch_results, start=1):
            if not isinstance(question_result, dict):
                continue
            question_id = (
                cls._first_text(question_result, "question_id", "id")
                or f"q_{question_index:03d}"
            )
            question_text = cls._first_text(
                question_result,
                "question_text",
                "core_question",
                "question",
                "text",
            )
            if question_text and question_id not in questions_by_id:
                questions_by_id[question_id] = QuestionProjection(
                    question_id=question_id,
                    question_text=question_text,
                    category=cls._first_text(question_result, "category") or "",
                    source_payload=question_result,
                )

            platform_results = question_result.get("platform_results")
            if not isinstance(platform_results, list):
                continue
            for platform_index, platform_result in enumerate(platform_results, start=1):
                if not isinstance(platform_result, dict):
                    continue
                answer = cls._build_answer_projection(
                    question_id=question_id,
                    platform_result=platform_result,
                    fallback_index=platform_index,
                )
                answers.append(answer)
                citations.extend(
                    cls._build_citation_projections(
                        answer=answer,
                        platform_result=platform_result,
                    )
                )

        return FetchProjectionBundle(
            questions=tuple(questions_by_id.values()),
            answers=tuple(answers),
            citations=tuple(citations),
        )

    @classmethod
    def normalize_competitors(cls, payload: Any) -> tuple[CompetitorProjection, ...]:
        """Normalize A1 competitor payloads into durable competitor objects."""

        competitors = payload if isinstance(payload, list) else []
        projections: list[CompetitorProjection] = []
        seen: set[str] = set()
        for index, raw_item in enumerate(competitors, start=1):
            if isinstance(raw_item, str):
                item = {"name": raw_item}
            elif isinstance(raw_item, dict):
                item = raw_item
            else:
                continue
            name = cls._first_text(item, "normalized_name", "name", "brand_name")
            if not name:
                continue
            competitor_key = (
                cls._first_text(item, "competitor_key", "id", "name_en")
                or cls._stable_object_key("competitor", name)
                or f"competitor_{index:03d}"
            )
            if competitor_key in seen:
                continue
            seen.add(competitor_key)
            projections.append(
                CompetitorProjection(
                    competitor_key=competitor_key,
                    normalized_name=name,
                    display_name=cls._first_text(item, "display_name", "name") or name,
                    website=cls._first_text(item, "website", "official_website") or "",
                    competition_type=cls._first_text(item, "competition_type") or "",
                    relevance_score=cls._number_or_none(item.get("relevance_score")),
                    source_payload=item,
                )
            )
        return tuple(projections)

    @classmethod
    def normalize_personas(cls, payload: Any) -> tuple[PersonaProjection, ...]:
        """Normalize A2 persona payloads into personas and usage scenarios."""

        if isinstance(payload, dict):
            raw_personas = payload.get("user_personas") or payload.get("userPersonas")
        else:
            raw_personas = payload
        if not isinstance(raw_personas, list):
            return ()

        projections: list[PersonaProjection] = []
        seen: set[str] = set()
        for index, raw_item in enumerate(raw_personas, start=1):
            if not isinstance(raw_item, dict):
                continue
            name = (
                cls._first_text(raw_item, "persona_name", "name", "label")
                or f"Persona {index}"
            )
            persona_id = (
                cls._first_text(raw_item, "persona_id", "id")
                or cls._stable_object_key("persona", name)
                or f"persona_{index:03d}"
            )
            if persona_id in seen:
                continue
            seen.add(persona_id)
            projections.append(
                PersonaProjection(
                    persona_id=persona_id,
                    persona_name=name,
                    description=cls._first_text(
                        raw_item,
                        "persona_description",
                        "description",
                        "subtitle",
                    )
                    or "",
                    segment=cls._first_text(
                        raw_item,
                        "segment",
                        "occupation",
                        "role",
                    )
                    or "",
                    priority=cls._first_text(
                        raw_item,
                        "persona_priority",
                        "priority",
                    )
                    or "",
                    scenarios=cls._normalize_scenarios(raw_item, persona_id),
                    source_payload=raw_item,
                )
            )
        return tuple(projections)

    @classmethod
    def normalize_report_findings(
        cls,
        *,
        payload: dict[str, Any],
        report_id: str,
        report_version: int,
    ) -> tuple[FindingProjection, ...]:
        """Normalize report conclusions into durable intelligence judgments."""

        raw_items = cls._extract_finding_items(payload)
        if not raw_items:
            summary = cls._report_summary(payload)
            if summary:
                raw_items = [
                    {
                        "title": "报告核心判断",
                        "summary": summary,
                        "finding_type": "summary",
                    }
                ]
        projections: list[FindingProjection] = []
        seen: set[str] = set()
        for index, raw_item in enumerate(raw_items, start=1):
            projection = cls._build_finding_projection(
                raw_item=raw_item,
                report_id=report_id,
                report_version=report_version,
                fallback_index=index,
            )
            if projection is None or projection.finding_key in seen:
                continue
            seen.add(projection.finding_key)
            projections.append(projection)
        return tuple(projections)

    async def persist_questions(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        payload: Any,
    ) -> list[BrandIntelligenceQuestion]:
        projections = self.normalize_questions(payload)
        rows: list[BrandIntelligenceQuestion] = []
        for projection in projections:
            rows.append(
                await self._upsert_question(
                    entity_id=entity_id,
                    session_id=session_id,
                    projection=projection,
                )
            )
        await self.db.flush()
        return rows

    async def persist_brand_context(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        competitors: Any = None,
        marketing_personas: Any = None,
        source_action_record_id: UUID | None = None,
    ) -> dict[str, int]:
        """Persist A1/A2 business context objects and relationship links."""

        competitor_rows: list[BrandCompetitorEntity] = []
        for projection in self.normalize_competitors(competitors):
            row = await self._upsert_competitor(
                entity_id=entity_id,
                session_id=session_id,
                projection=projection,
            )
            competitor_rows.append(row)
        await self.db.flush()
        for competitor in competitor_rows:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="brand_has_competitor",
                from_object_type="brand_entity",
                from_object_id=str(entity_id),
                to_object_type="competitor_entity",
                to_object_id=str(competitor.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"competitor_key": competitor.competitor_key},
            )

        persona_rows: list[BrandAudiencePersona] = []
        scenario_count = 0
        for projection in self.normalize_personas(marketing_personas):
            persona = await self._upsert_persona(
                entity_id=entity_id,
                session_id=session_id,
                projection=projection,
            )
            persona_rows.append(persona)
            await self.db.flush()
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="brand_has_persona",
                from_object_type="brand_entity",
                from_object_id=str(entity_id),
                to_object_type="audience_persona",
                to_object_id=str(persona.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"persona_id": persona.persona_id},
            )
            for scenario_projection in projection.scenarios:
                scenario = await self._upsert_scenario(
                    entity_id=entity_id,
                    session_id=session_id,
                    persona=persona,
                    projection=scenario_projection,
                )
                await self.db.flush()
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="persona_has_scenario",
                    from_object_type="audience_persona",
                    from_object_id=str(persona.id),
                    to_object_type="usage_scenario",
                    to_object_id=str(scenario.id),
                    source_action_record_id=source_action_record_id,
                    extra_metadata={"scenario_key": scenario.scenario_key},
                )
                scenario_count += 1

        return {
            "competitors": len(competitor_rows),
            "personas": len(persona_rows),
            "scenarios": scenario_count,
        }

    async def persist_fetch_results(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        fetch_results: Any,
        source_action_record_id: UUID | None = None,
    ) -> dict[str, int]:
        bundle = self.normalize_fetch_results(fetch_results)
        questions_by_id: dict[str, BrandIntelligenceQuestion] = {}
        for projection in bundle.questions:
            question = await self._upsert_question(
                entity_id=entity_id,
                session_id=session_id,
                projection=projection,
            )
            questions_by_id[projection.question_id] = question
        await self.db.flush()

        answers_by_dedupe: dict[str, BrandPlatformAnswer] = {}
        answer_dedupe_key_by_original: dict[str, str] = {}
        for projection in bundle.answers:
            answer_dedupe_key = await self._answer_dedupe_key_for_entity(
                entity_id=entity_id,
                dedupe_key=projection.dedupe_key,
            )
            answer_dedupe_key_by_original[projection.dedupe_key] = answer_dedupe_key
            answer_projection = (
                projection
                if answer_dedupe_key == projection.dedupe_key
                else replace(projection, dedupe_key=answer_dedupe_key)
            )
            answer = await self._upsert_answer(
                entity_id=entity_id,
                session_id=session_id,
                question=questions_by_id.get(projection.question_id),
                projection=answer_projection,
            )
            answers_by_dedupe[projection.dedupe_key] = answer
        await self.db.flush()

        link_count = 0
        for projection in bundle.answers:
            question = questions_by_id.get(projection.question_id)
            answer = answers_by_dedupe.get(projection.dedupe_key)
            if question is None or answer is None:
                continue
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="question_answered_by",
                from_object_type="simulated_question",
                from_object_id=str(question.id),
                to_object_type="platform_answer",
                to_object_id=str(answer.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={
                    "question_id": projection.question_id,
                    "platform": projection.platform,
                },
            )
            link_count += 1

        citation_links: list[tuple[BrandPlatformAnswer, BrandCitationSource]] = []
        for projection in bundle.citations:
            answer = answers_by_dedupe.get(projection.answer_dedupe_key)
            if answer is None:
                continue
            answer_dedupe_key = answer_dedupe_key_by_original.get(
                projection.answer_dedupe_key,
                projection.answer_dedupe_key,
            )
            citation_projection = projection
            if answer_dedupe_key != projection.answer_dedupe_key:
                citation_projection = replace(
                    projection,
                    answer_dedupe_key=answer_dedupe_key,
                    dedupe_key=self._entity_scoped_dedupe_key(
                        entity_id=entity_id,
                        dedupe_key=projection.dedupe_key,
                    ),
                )
            citation = await self._upsert_citation(
                entity_id=entity_id,
                session_id=session_id,
                answer=answer,
                projection=citation_projection,
            )
            citation_links.append((answer, citation))
        await self.db.flush()

        for answer, citation in citation_links:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="platform_answer_cites_source",
                from_object_type="platform_answer",
                from_object_id=str(answer.id),
                to_object_type="citation_source",
                to_object_id=str(citation.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"platform": answer.platform},
            )
            link_count += 1

        await self._persist_mentions_for_answers(
            entity_id=entity_id,
            session_id=session_id,
            answers=list(answers_by_dedupe.values()),
            answer_dedupe_by_id={
                answer.id: original_dedupe
                for original_dedupe, answer in answers_by_dedupe.items()
            },
            source_action_record_id=source_action_record_id,
        )

        return {
            "questions": len(bundle.questions),
            "answers": len(bundle.answers),
            "citations": len(bundle.citations),
            "links": link_count,
        }

    async def persist_report_artifact(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        report_kind: str,
        title: str,
        artifact_id: str,
        payload: dict[str, Any],
        message_id: UUID | None = None,
        source_action_record_id: UUID | None = None,
    ) -> BrandReportVersion:
        """Persist a report version and bind it to the current evidence set."""

        answers = (
            (
                await self.db.execute(
                    self._answer_query_for_scope(
                        entity_id=entity_id, session_id=session_id
                    )
                )
            )
            .scalars()
            .all()
        )
        answer_ids = [answer.id for answer in answers]
        question_ids = [
            answer.question_object_id
            for answer in answers
            if answer.question_object_id is not None
        ]
        citation_ids: list[UUID] = []
        if answer_ids:
            citation_ids = [
                citation_id
                for citation_id in (
                    await self.db.execute(
                        select(BrandCitationSource.id).where(
                            BrandCitationSource.answer_id.in_(answer_ids)
                        )
                    )
                )
                .scalars()
                .all()
            ]

        evidence_set = BrandEvidenceSet(
            entity_id=entity_id,
            session_id=session_id,
            evidence_set_type="report",
            title=title,
            definition={
                "scope": "session_answers",
                "report_kind": report_kind,
                "artifact_id": artifact_id,
            },
            question_ids=sorted(str(item) for item in set(question_ids)),
            answer_ids=[str(item) for item in answer_ids],
            citation_ids=[str(item) for item in citation_ids],
            question_count=len(set(question_ids)),
            answer_count=len(answer_ids),
            citation_count=len(citation_ids),
        )
        self.db.add(evidence_set)
        await self.db.flush()

        for answer_id in answer_ids:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="evidence_set_contains_answer",
                from_object_type="evidence_set",
                from_object_id=str(evidence_set.id),
                to_object_type="platform_answer",
                to_object_id=str(answer_id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"report_kind": report_kind},
            )

        report_id = str(payload.get("report_id") or artifact_id or "").strip()
        if not report_id:
            report_id = "report:" + self._stable_hash([str(entity_id), report_kind])
        version = await self._next_report_version(
            entity_id=entity_id,
            report_id=report_id,
        )
        report_version = BrandReportVersion(
            entity_id=entity_id,
            session_id=session_id,
            evidence_set_id=evidence_set.id,
            message_id=message_id,
            report_id=report_id,
            version=version,
            report_kind=report_kind,
            artifact_id=artifact_id,
            title=title,
            summary=self._report_summary(payload),
            payload=payload,
            publication_status="pre_graph_update",
        )
        self.db.add(report_version)
        await self.db.flush()
        metric_snapshot = await self._upsert_metric_snapshot(
            entity_id=entity_id,
            session_id=session_id,
            report_version=report_version,
            payload=payload,
        )
        await self.links.ensure_link(
            entity_id=entity_id,
            link_type="report_uses_evidence_set",
            from_object_type="report_artifact",
            from_object_id=str(report_version.id),
            to_object_type="evidence_set",
            to_object_id=str(evidence_set.id),
            source_action_record_id=source_action_record_id,
            extra_metadata={
                "report_id": report_id,
                "report_kind": report_kind,
                "artifact_id": artifact_id,
            },
        )
        if metric_snapshot is not None:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="metric_snapshot_measures_brand",
                from_object_type="metric_snapshot",
                from_object_id=str(metric_snapshot.id),
                to_object_type="brand_entity",
                to_object_id=str(entity_id),
                source_action_record_id=source_action_record_id,
                extra_metadata={
                    "report_id": report_id,
                    "report_version_id": str(report_version.id),
                },
            )
        await self._persist_report_findings(
            entity_id=entity_id,
            session_id=session_id,
            report_version=report_version,
            evidence_set=evidence_set,
            payload=payload,
            question_count=len(set(question_ids)),
            answer_count=len(answer_ids),
            citation_count=len(citation_ids),
            source_action_record_id=source_action_record_id,
        )
        await self._persist_report_mentions(
            entity_id=entity_id,
            session_id=session_id,
            report_version=report_version,
            payload=payload,
            source_action_record_id=source_action_record_id,
        )
        return report_version

    async def persist_mentions_for_existing_answers(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None = None,
        source_action_record_id: UUID | None = None,
    ) -> int:
        """Backfill mention facts from already persisted platform answers."""

        before_count = await self._mention_count(entity_id=entity_id)
        query = select(BrandPlatformAnswer).where(
            BrandPlatformAnswer.entity_id == entity_id
        )
        if session_id is not None:
            query = query.where(BrandPlatformAnswer.session_id == session_id)
        answers = (await self.db.execute(query)).scalars().all()
        await self._persist_mentions_for_answers(
            entity_id=entity_id,
            session_id=session_id,
            answers=list(answers),
            answer_dedupe_by_id={answer.id: answer.dedupe_key for answer in answers},
            source_action_record_id=source_action_record_id,
        )
        after_count = await self._mention_count(entity_id=entity_id)
        return max(after_count - before_count, 0)

    async def _mention_count(self, *, entity_id: UUID) -> int:
        return int(
            (
                await self.db.execute(
                    select(func.count())
                    .select_from(BrandMention)
                    .where(BrandMention.entity_id == entity_id)
                )
            ).scalar_one()
            or 0
        )

    async def _persist_mentions_for_answers(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        answers: list[BrandPlatformAnswer],
        answer_dedupe_by_id: dict[UUID, str],
        source_action_record_id: UUID | None = None,
    ) -> int:
        if not answers:
            return 0
        entity = await self.db.get(Entity, entity_id)
        if entity is None:
            return 0
        competitors = await self._competitor_lookup(entity_id=entity_id)
        mention_rows: list[BrandMention] = []
        for answer in answers:
            projections = self._mention_projections_from_answer(
                entity=entity,
                answer=answer,
                answer_dedupe_key=answer_dedupe_by_id.get(
                    answer.id,
                    answer.dedupe_key,
                ),
                competitors=competitors,
            )
            for projection in projections:
                mention_rows.append(
                    await self._upsert_mention(
                        entity_id=entity_id,
                        session_id=(
                            session_id if session_id is not None else answer.session_id
                        ),
                        answer=answer,
                        report_version=None,
                        projection=projection,
                    )
                )
        await self.db.flush()
        await self._link_mentions(
            entity_id=entity_id,
            mentions=mention_rows,
            source_action_record_id=source_action_record_id,
        )
        return len(mention_rows)

    async def _persist_report_mentions(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        report_version: BrandReportVersion,
        payload: dict[str, Any],
        source_action_record_id: UUID | None = None,
    ) -> int:
        entity = await self.db.get(Entity, entity_id)
        if entity is None:
            return 0
        competitors = await self._competitor_lookup(entity_id=entity_id)
        projections = self._mention_projections_from_report(
            entity=entity,
            report_version=report_version,
            payload=payload,
            competitors=competitors,
        )
        mention_rows = [
            await self._upsert_mention(
                entity_id=entity_id,
                session_id=session_id,
                answer=None,
                report_version=report_version,
                projection=projection,
            )
            for projection in projections
        ]
        await self.db.flush()
        await self._link_mentions(
            entity_id=entity_id,
            mentions=mention_rows,
            source_action_record_id=source_action_record_id,
        )
        for mention in mention_rows:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="report_contains_brand_mention",
                from_object_type="report_artifact",
                from_object_id=str(report_version.id),
                to_object_type="brand_mention",
                to_object_id=str(mention.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"sentiment": mention.sentiment},
            )
        return len(mention_rows)

    async def _upsert_mention(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        answer: BrandPlatformAnswer | None,
        report_version: BrandReportVersion | None,
        projection: MentionProjection,
    ) -> BrandMention:
        row = (
            await self.db.execute(
                select(BrandMention).where(
                    BrandMention.entity_id == entity_id,
                    BrandMention.dedupe_key == projection.dedupe_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = BrandMention(
                entity_id=entity_id,
                session_id=session_id,
                answer_id=answer.id if answer is not None else None,
                dedupe_key=projection.dedupe_key,
            )
            self.db.add(row)
        row.session_id = session_id
        row.answer_id = answer.id if answer is not None else row.answer_id
        row.question_object_id = (
            answer.question_object_id if answer is not None else row.question_object_id
        )
        row.report_version_id = (
            report_version.id if report_version is not None else row.report_version_id
        )
        row.platform = projection.platform or (answer.platform if answer else "")
        row.mentioned_brand_key = projection.mentioned_brand_key
        row.mentioned_brand_name = projection.mentioned_brand_name
        row.mentioned_object_type = projection.mentioned_object_type
        row.mentioned_object_id = projection.mentioned_object_id
        row.mention_role = projection.mention_role or "target_brand"
        row.sentiment = self._normalize_sentiment(projection.sentiment)
        row.quote = self._safe_preview(projection.quote, limit=360)
        row.confidence = projection.confidence
        row.status = "observed"
        row.source_payload = projection.source_payload
        return row

    async def _link_mentions(
        self,
        *,
        entity_id: UUID,
        mentions: list[BrandMention],
        source_action_record_id: UUID | None = None,
    ) -> None:
        for mention in mentions:
            if mention.answer_id is not None:
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="platform_answer_has_brand_mention",
                    from_object_type="platform_answer",
                    from_object_id=str(mention.answer_id),
                    to_object_type="brand_mention",
                    to_object_id=str(mention.id),
                    source_action_record_id=source_action_record_id,
                    extra_metadata={"sentiment": mention.sentiment},
                )
            if mention.question_object_id is not None:
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="brand_mention_about_question",
                    from_object_type="brand_mention",
                    from_object_id=str(mention.id),
                    to_object_type="simulated_question",
                    to_object_id=str(mention.question_object_id),
                    source_action_record_id=source_action_record_id,
                    extra_metadata={"platform": mention.platform},
                )
            if mention.mentioned_object_type == "brand_entity":
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="brand_mention_mentions_brand",
                    from_object_type="brand_mention",
                    from_object_id=str(mention.id),
                    to_object_type="brand_entity",
                    to_object_id=str(entity_id),
                    source_action_record_id=source_action_record_id,
                    extra_metadata={"mention_role": mention.mention_role},
                )
            elif mention.mentioned_object_type == "competitor_entity":
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="brand_mention_mentions_competitor",
                    from_object_type="brand_mention",
                    from_object_id=str(mention.id),
                    to_object_type="competitor_entity",
                    to_object_id=mention.mentioned_object_id,
                    source_action_record_id=source_action_record_id,
                    extra_metadata={"mention_role": mention.mention_role},
                )

    async def _competitor_lookup(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, BrandCompetitorEntity]:
        rows = (
            (
                await self.db.execute(
                    select(BrandCompetitorEntity).where(
                        BrandCompetitorEntity.entity_id == entity_id
                    )
                )
            )
            .scalars()
            .all()
        )
        lookup: dict[str, BrandCompetitorEntity] = {}
        for row in rows:
            for value in (row.normalized_name, row.display_name, row.competitor_key):
                key = self._brand_key(value)
                if key:
                    lookup.setdefault(key, row)
        return lookup

    @classmethod
    def _mention_projections_from_answer(
        cls,
        *,
        entity: Entity,
        answer: BrandPlatformAnswer,
        answer_dedupe_key: str,
        competitors: dict[str, BrandCompetitorEntity],
    ) -> list[MentionProjection]:
        payload = (
            answer.answer_payload if isinstance(answer.answer_payload, dict) else {}
        )
        projections: list[MentionProjection] = []
        brand_key = cls._brand_key(entity.name)
        quote = cls._extract_mention_quote(payload, answer.answer_text)
        sentiment = cls._extract_sentiment(payload, answer.answer_text)
        if answer.brand_mentioned is True or cls._brand_mentioned(payload) is True:
            projections.append(
                MentionProjection(
                    dedupe_key="mention:"
                    + cls._stable_hash([answer_dedupe_key, brand_key, "target_brand"]),
                    answer_dedupe_key=answer_dedupe_key,
                    question_id=answer.question_id,
                    platform=answer.platform,
                    mentioned_brand_key=brand_key,
                    mentioned_brand_name=entity.name,
                    mentioned_object_type="brand_entity",
                    mentioned_object_id=str(entity.id),
                    mention_role="target_brand",
                    sentiment=sentiment,
                    quote=quote,
                    confidence=cls._number_or_none(payload.get("confidence")),
                    source_payload=cls._public_mention_payload(payload),
                )
            )
        for item in cls._extract_competitor_mentions(payload):
            competitor_name = item.get("name") or item.get("brand") or ""
            competitor_key = cls._brand_key(competitor_name)
            competitor = competitors.get(competitor_key)
            if competitor is None or competitor_key == brand_key:
                continue
            projections.append(
                MentionProjection(
                    dedupe_key="mention:"
                    + cls._stable_hash(
                        [answer_dedupe_key, competitor_key, "competitor"]
                    ),
                    answer_dedupe_key=answer_dedupe_key,
                    question_id=answer.question_id,
                    platform=answer.platform,
                    mentioned_brand_key=competitor_key,
                    mentioned_brand_name=competitor.display_name or competitor_name,
                    mentioned_object_type="competitor_entity",
                    mentioned_object_id=str(competitor.id),
                    mention_role="competitor",
                    sentiment=cls._normalize_sentiment(
                        str(item.get("sentiment") or "neutral")
                    ),
                    quote=cls._safe_preview(
                        str(item.get("quote") or item.get("snippet") or quote),
                        limit=360,
                    ),
                    confidence=cls._number_or_none(item.get("confidence")),
                    source_payload=cls._public_mention_payload(item),
                )
            )
        return projections

    @classmethod
    def _mention_projections_from_report(
        cls,
        *,
        entity: Entity,
        report_version: BrandReportVersion,
        payload: dict[str, Any],
        competitors: dict[str, BrandCompetitorEntity],
    ) -> list[MentionProjection]:
        projections: list[MentionProjection] = []
        mention_payload = payload.get("mention_sentiment_analysis")
        if not isinstance(mention_payload, dict):
            mention_payload = {}
        brand_payload = mention_payload.get("brand")
        brand_mentions = []
        if isinstance(brand_payload, dict):
            brand_mentions = cls._as_dict_list(
                brand_payload.get("mentions")
                or brand_payload.get("brand_mentions")
                or brand_payload.get("samples")
            )
        for index, item in enumerate(brand_mentions[:50], start=1):
            quote = cls._first_text(item, "quote", "snippet", "content", "answer")
            projections.append(
                MentionProjection(
                    dedupe_key="mention:"
                    + cls._stable_hash(
                        [
                            report_version.report_id,
                            str(report_version.version),
                            "target_brand",
                            str(index),
                            quote,
                        ]
                    ),
                    platform=cls._canonical_platform(cls._first_text(item, "platform")),
                    mentioned_brand_key=cls._brand_key(entity.name),
                    mentioned_brand_name=entity.name,
                    mentioned_object_type="brand_entity",
                    mentioned_object_id=str(entity.id),
                    mention_role="target_brand",
                    sentiment=cls._normalize_sentiment(
                        cls._first_text(item, "sentiment") or "neutral"
                    ),
                    quote=quote,
                    confidence=cls._number_or_none(item.get("confidence")),
                    source_payload=cls._public_mention_payload(item),
                )
            )
        competitor_payload = mention_payload.get("competitors")
        for index, item in enumerate(
            cls._as_dict_list(competitor_payload)[:80], start=1
        ):
            competitor_name = cls._first_text(item, "brand", "name", "display_name")
            competitor = competitors.get(cls._brand_key(competitor_name))
            if competitor is None:
                continue
            quote = cls._first_text(item, "quote", "snippet", "content", "answer")
            projections.append(
                MentionProjection(
                    dedupe_key="mention:"
                    + cls._stable_hash(
                        [
                            report_version.report_id,
                            str(report_version.version),
                            "competitor",
                            competitor.competitor_key,
                            str(index),
                            quote,
                        ]
                    ),
                    platform=cls._canonical_platform(cls._first_text(item, "platform")),
                    mentioned_brand_key=cls._brand_key(competitor.display_name),
                    mentioned_brand_name=competitor.display_name,
                    mentioned_object_type="competitor_entity",
                    mentioned_object_id=str(competitor.id),
                    mention_role="competitor",
                    sentiment=cls._normalize_sentiment(
                        cls._first_text(item, "sentiment") or "neutral"
                    ),
                    quote=quote,
                    confidence=cls._number_or_none(item.get("confidence")),
                    source_payload=cls._public_mention_payload(item),
                )
            )
        return projections

    async def _persist_report_findings(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        report_version: BrandReportVersion,
        evidence_set: BrandEvidenceSet,
        payload: dict[str, Any],
        question_count: int,
        answer_count: int,
        citation_count: int,
        source_action_record_id: UUID | None = None,
    ) -> list[BrandIntelligenceFinding]:
        projections = self.normalize_report_findings(
            payload=payload,
            report_id=report_version.report_id,
            report_version=report_version.version,
        )
        rows: list[BrandIntelligenceFinding] = []
        for projection in projections:
            rows.append(
                await self._upsert_finding(
                    entity_id=entity_id,
                    session_id=session_id,
                    report_version=report_version,
                    evidence_set=evidence_set,
                    projection=projection,
                    question_count=question_count,
                    answer_count=answer_count,
                    citation_count=citation_count,
                )
            )
        await self.db.flush()

        for finding in rows:
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="brand_has_intelligence_finding",
                from_object_type="brand_entity",
                from_object_id=str(entity_id),
                to_object_type="intelligence_finding",
                to_object_id=str(finding.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={"finding_key": finding.finding_key},
            )
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="report_contains_intelligence_finding",
                from_object_type="report_artifact",
                from_object_id=str(report_version.id),
                to_object_type="intelligence_finding",
                to_object_id=str(finding.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={
                    "report_id": report_version.report_id,
                    "report_version": report_version.version,
                },
            )
            await self.links.ensure_link(
                entity_id=entity_id,
                link_type="intelligence_finding_uses_evidence_set",
                from_object_type="intelligence_finding",
                from_object_id=str(finding.id),
                to_object_type="evidence_set",
                to_object_id=str(evidence_set.id),
                source_action_record_id=source_action_record_id,
                extra_metadata={
                    "question_count": question_count,
                    "answer_count": answer_count,
                    "citation_count": citation_count,
                },
            )
        return rows

    async def _upsert_competitor(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        projection: CompetitorProjection,
    ) -> BrandCompetitorEntity:
        query = select(BrandCompetitorEntity).where(
            BrandCompetitorEntity.entity_id == entity_id,
            BrandCompetitorEntity.competitor_key == projection.competitor_key,
        )
        if session_id is None:
            query = query.where(BrandCompetitorEntity.session_id.is_(None))
        else:
            query = query.where(BrandCompetitorEntity.session_id == session_id)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandCompetitorEntity(
                entity_id=entity_id,
                session_id=session_id,
                competitor_key=projection.competitor_key,
                normalized_name=projection.normalized_name,
            )
            self.db.add(row)
        row.normalized_name = projection.normalized_name
        row.display_name = projection.display_name or projection.normalized_name
        row.website = projection.website or row.website
        row.competition_type = projection.competition_type or row.competition_type
        row.relevance_score = (
            projection.relevance_score
            if projection.relevance_score is not None
            else row.relevance_score
        )
        row.source_payload = projection.source_payload
        return row

    async def _upsert_persona(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        projection: PersonaProjection,
    ) -> BrandAudiencePersona:
        query = select(BrandAudiencePersona).where(
            BrandAudiencePersona.entity_id == entity_id,
            BrandAudiencePersona.persona_id == projection.persona_id,
        )
        if session_id is None:
            query = query.where(BrandAudiencePersona.session_id.is_(None))
        else:
            query = query.where(BrandAudiencePersona.session_id == session_id)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandAudiencePersona(
                entity_id=entity_id,
                session_id=session_id,
                persona_id=projection.persona_id,
                persona_name=projection.persona_name,
            )
            self.db.add(row)
        row.persona_name = projection.persona_name
        row.description = projection.description
        row.segment = projection.segment
        row.priority = projection.priority
        row.source_payload = projection.source_payload
        return row

    async def _upsert_scenario(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        persona: BrandAudiencePersona,
        projection: ScenarioProjection,
    ) -> BrandUsageScenario:
        query = select(BrandUsageScenario).where(
            BrandUsageScenario.entity_id == entity_id,
            BrandUsageScenario.scenario_key == projection.scenario_key,
        )
        if session_id is None:
            query = query.where(BrandUsageScenario.session_id.is_(None))
        else:
            query = query.where(BrandUsageScenario.session_id == session_id)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandUsageScenario(
                entity_id=entity_id,
                session_id=session_id,
                scenario_key=projection.scenario_key,
                scenario_name=projection.scenario_name,
            )
            self.db.add(row)
        row.persona_object_id = persona.id
        row.scenario_name = projection.scenario_name
        row.description = projection.description
        row.decision_stage = projection.decision_stage
        row.source_payload = projection.source_payload
        return row

    async def _upsert_finding(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        report_version: BrandReportVersion,
        evidence_set: BrandEvidenceSet,
        projection: FindingProjection,
        question_count: int,
        answer_count: int,
        citation_count: int,
    ) -> BrandIntelligenceFinding:
        query = select(BrandIntelligenceFinding).where(
            BrandIntelligenceFinding.entity_id == entity_id,
            BrandIntelligenceFinding.finding_key == projection.finding_key,
        )
        if session_id is None:
            query = query.where(BrandIntelligenceFinding.session_id.is_(None))
        else:
            query = query.where(BrandIntelligenceFinding.session_id == session_id)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandIntelligenceFinding(
                entity_id=entity_id,
                session_id=session_id,
                finding_key=projection.finding_key,
                title=projection.title,
            )
            self.db.add(row)
        row.report_version_id = report_version.id
        row.evidence_set_id = evidence_set.id
        row.title = projection.title
        row.summary = projection.summary
        row.finding_type = projection.finding_type
        row.severity = projection.severity
        row.confidence = projection.confidence
        row.status = "observed"
        row.evidence_summary = projection.evidence_summary or (
            f"{question_count} 个问题，{answer_count} 条回答，"
            f"{citation_count} 个引用"
        )
        row.supporting_question_count = question_count
        row.supporting_answer_count = answer_count
        row.supporting_citation_count = citation_count
        row.suggested_action_type = projection.suggested_action_type
        row.suggested_action_payload = projection.suggested_action_payload
        row.source_payload = projection.source_payload
        return row

    async def _upsert_metric_snapshot(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        report_version: BrandReportVersion,
        payload: dict[str, Any],
    ) -> BrandMetricSnapshot | None:
        metrics = self._extract_metric_payload(payload)
        if not metrics:
            return None
        snapshot_key = "metric:" + self._stable_hash(
            [str(entity_id), report_version.report_id, str(report_version.version)]
        )
        row = (
            await self.db.execute(
                select(BrandMetricSnapshot).where(
                    BrandMetricSnapshot.entity_id == entity_id,
                    BrandMetricSnapshot.snapshot_key == snapshot_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = BrandMetricSnapshot(
                entity_id=entity_id,
                session_id=session_id,
                report_version_id=report_version.id,
                snapshot_key=snapshot_key,
            )
            self.db.add(row)
        row.report_version_id = report_version.id
        row.metric_kind = report_version.report_kind or "report"
        row.bwvs_index = self._number_or_none(metrics.get("bwvs_index"))
        row.mention_rate = self._number_or_none(metrics.get("mention_rate"))
        total_questions = self._number_or_none(metrics.get("total_questions"))
        row.total_questions = (
            int(total_questions) if total_questions is not None else None
        )
        row.metric_payload = metrics
        return row

    async def _upsert_question(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        projection: QuestionProjection,
    ) -> BrandIntelligenceQuestion:
        query = select(BrandIntelligenceQuestion).where(
            BrandIntelligenceQuestion.entity_id == entity_id,
            BrandIntelligenceQuestion.question_id == projection.question_id,
        )
        if session_id is None:
            query = query.where(BrandIntelligenceQuestion.session_id.is_(None))
        else:
            query = query.where(BrandIntelligenceQuestion.session_id == session_id)
        row = (await self.db.execute(query)).scalar_one_or_none()
        if row is None:
            row = BrandIntelligenceQuestion(
                entity_id=entity_id,
                session_id=session_id,
                question_id=projection.question_id,
                question_text=projection.question_text,
            )
            self.db.add(row)
        row.question_text = projection.question_text
        row.category = projection.category
        row.subcategory = projection.subcategory
        row.user_intent = projection.user_intent
        row.decision_stage = projection.decision_stage
        row.source_payload = projection.source_payload
        return row

    async def _upsert_answer(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        question: BrandIntelligenceQuestion | None,
        projection: AnswerProjection,
    ) -> BrandPlatformAnswer:
        row = (
            await self.db.execute(
                select(BrandPlatformAnswer).where(
                    BrandPlatformAnswer.dedupe_key == projection.dedupe_key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = BrandPlatformAnswer(
                entity_id=entity_id,
                session_id=session_id,
                dedupe_key=projection.dedupe_key,
                platform=projection.platform,
            )
            self.db.add(row)
        row.question_object_id = question.id if question is not None else None
        row.question_id = projection.question_id
        row.platform = projection.platform
        row.fetch_method = projection.fetch_method
        row.status = projection.status
        row.success = projection.success
        row.brand_mentioned = projection.brand_mentioned
        row.answer_text = projection.answer_text
        row.answer_payload = projection.answer_payload
        row.raw_payload = projection.raw_payload
        row.run_id = projection.run_id
        row.duration_ms = projection.duration_ms
        if question is not None and projection.status == "captured":
            question.status = "fetched"
        return row

    async def _answer_dedupe_key_for_entity(
        self,
        *,
        entity_id: UUID,
        dedupe_key: str,
    ) -> str:
        existing = (
            await self.db.execute(
                select(BrandPlatformAnswer).where(
                    BrandPlatformAnswer.dedupe_key == dedupe_key
                )
            )
        ).scalar_one_or_none()
        if existing is None or existing.entity_id == entity_id:
            return dedupe_key
        return self._entity_scoped_dedupe_key(
            entity_id=entity_id,
            dedupe_key=dedupe_key,
        )

    @staticmethod
    def _entity_scoped_dedupe_key(*, entity_id: UUID, dedupe_key: str) -> str:
        scoped_suffix = f":entity:{entity_id.hex[:12]}"
        max_prefix_length = 255 - len(scoped_suffix)
        return f"{dedupe_key[:max_prefix_length]}{scoped_suffix}"

    async def _upsert_citation(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        answer: BrandPlatformAnswer,
        projection: CitationProjection,
    ) -> BrandCitationSource:
        row = (
            await self.db.execute(
                select(BrandCitationSource).where(
                    BrandCitationSource.dedupe_key == projection.dedupe_key
                )
            )
        ).scalar_one_or_none()
        if row is None:
            row = BrandCitationSource(
                entity_id=entity_id,
                session_id=session_id,
                answer_id=answer.id,
                dedupe_key=projection.dedupe_key,
            )
            self.db.add(row)
        row.answer_id = answer.id
        row.url = projection.url
        row.domain = projection.domain
        row.source_title = projection.source_title
        row.snippet = projection.snippet
        row.confidence = projection.confidence
        row.citation_payload = projection.citation_payload
        return row

    def _answer_query_for_scope(self, *, entity_id: UUID, session_id: UUID | None):
        query = select(BrandPlatformAnswer).where(
            BrandPlatformAnswer.entity_id == entity_id
        )
        if session_id is None:
            return query
        return query.where(BrandPlatformAnswer.session_id == session_id)

    async def _next_report_version(self, *, entity_id: UUID, report_id: str) -> int:
        latest = (
            await self.db.execute(
                select(func.max(BrandReportVersion.version)).where(
                    BrandReportVersion.entity_id == entity_id,
                    BrandReportVersion.report_id == report_id,
                )
            )
        ).scalar_one_or_none()
        return int(latest or 0) + 1

    @classmethod
    def _extract_question_items(cls, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if not isinstance(payload, dict):
            return []
        for key in ("simulated_questions", "questions", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
        return []

    @classmethod
    def _extract_finding_items(cls, payload: dict[str, Any]) -> list[Any]:
        for key in (
            "key_findings",
            "findings",
            "insights",
            "diagnostic_conclusions",
            "strategic_findings",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                return value
            if isinstance(value, dict):
                nested = value.get("items") or value.get("findings")
                if isinstance(nested, list):
                    return nested
        report_v2 = payload.get("report_v2")
        if isinstance(report_v2, dict):
            value = report_v2.get("key_findings") or report_v2.get("findings")
            if isinstance(value, list):
                return value
        return []

    @classmethod
    def _build_finding_projection(
        cls,
        *,
        raw_item: Any,
        report_id: str,
        report_version: int,
        fallback_index: int,
    ) -> FindingProjection | None:
        if isinstance(raw_item, str):
            item = {"summary": raw_item}
        elif isinstance(raw_item, dict):
            item = raw_item
        else:
            return None

        summary = cls._first_text(
            item,
            "summary",
            "detail",
            "description",
            "body",
            "explanation",
        ) or cls._first_text(item, "fact", "finding", "title", "label", "headline")
        if not summary:
            return None
        title = cls._first_text(
            item, "title", "headline", "fact", "finding", "label"
        ) or cls._short_title(summary)
        title = cls._short_title(title)
        finding_type = cls._normalize_finding_type(
            cls._first_text(item, "finding_type", "type", "category"),
            f"{title} {summary}",
        )
        severity = cls._normalize_finding_severity(
            cls._first_text(item, "severity", "priority", "risk_level"),
            finding_type=finding_type,
        )
        suggested_action_payload = cls._suggested_action_payload(item)
        suggested_action_type = cls._first_text(
            item, "suggested_action_type", "action_type"
        ) or ("record_user_feedback" if suggested_action_payload is not None else "")
        finding_key = cls._first_text(
            item, "finding_key", "finding_id", "id"
        ) or "finding:" + cls._stable_hash(
            [
                report_id,
                str(report_version),
                str(fallback_index),
                title,
                summary,
            ]
        )
        return FindingProjection(
            finding_key=finding_key[:160],
            title=title,
            summary=summary[:2000],
            finding_type=finding_type,
            severity=severity,
            confidence=cls._number_or_none(
                item.get("confidence", item.get("confidence_score"))
            ),
            evidence_summary=cls._first_text(
                item,
                "evidence_summary",
                "evidence",
                "supporting_evidence",
            ),
            suggested_action_type=suggested_action_type,
            suggested_action_payload=suggested_action_payload,
            source_payload=item,
        )

    @staticmethod
    def _short_title(value: str, limit: int = 96) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "..."

    @classmethod
    def _normalize_finding_type(cls, raw_value: str, text: str) -> str:
        cleaned = str(raw_value or "").strip().lower()
        if cleaned in {
            "summary",
            "observation",
            "risk",
            "opportunity",
            "recommendation_advantage",
            "competitor_pressure",
            "evidence_gap",
        }:
            return cleaned
        text_value = f"{cleaned} {text}".lower()
        if any(marker in text_value for marker in ("risk", "风险", "误判")):
            return "risk"
        if any(marker in text_value for marker in ("gap", "缺口", "引用", "来源")):
            return "evidence_gap"
        if any(marker in text_value for marker in ("competitor", "竞品", "竞争")):
            return "competitor_pressure"
        if any(marker in text_value for marker in ("opportunity", "机会", "建议")):
            return "opportunity"
        if any(marker in text_value for marker in ("advantage", "优势", "推荐")):
            return "recommendation_advantage"
        if "summary" in text_value or "核心判断" in text_value:
            return "summary"
        return "observation"

    @staticmethod
    def _normalize_finding_severity(raw_value: str, *, finding_type: str) -> str:
        cleaned = str(raw_value or "").strip().lower()
        if cleaned in {"critical", "high", "medium", "low"}:
            return cleaned
        if any(marker in cleaned for marker in ("严重", "高", "紧急")):
            return "high"
        if any(marker in cleaned for marker in ("低", "轻微")):
            return "low"
        if finding_type in {"risk", "competitor_pressure"}:
            return "high"
        if finding_type == "evidence_gap":
            return "medium"
        return "medium"

    @classmethod
    def _suggested_action_payload(cls, item: dict[str, Any]) -> dict[str, Any] | None:
        for key in ("suggested_action", "recommendation", "next_action"):
            value = item.get(key)
            if isinstance(value, dict):
                return value
            if isinstance(value, str) and value.strip():
                return {"text": value.strip()}
        return None

    @classmethod
    def _normalize_scenarios(
        cls,
        persona_payload: dict[str, Any],
        persona_id: str,
    ) -> tuple[ScenarioProjection, ...]:
        raw_scenarios = (
            persona_payload.get("usage_scenarios")
            or persona_payload.get("scenarios")
            or []
        )
        if isinstance(raw_scenarios, dict):
            raw_scenarios = [raw_scenarios]
        if not isinstance(raw_scenarios, list):
            return ()

        projections: list[ScenarioProjection] = []
        seen: set[str] = set()
        for index, raw_item in enumerate(raw_scenarios, start=1):
            if isinstance(raw_item, str):
                item = {"scenario_name": raw_item}
            elif isinstance(raw_item, dict):
                item = raw_item
            else:
                continue
            name = (
                cls._first_text(item, "scenario_name", "name", "label")
                or f"Scenario {index}"
            )
            scenario_key = (
                cls._first_text(item, "scenario_key", "id")
                or cls._stable_object_key("scenario", f"{persona_id}:{name}")
                or f"{persona_id}:scenario_{index:03d}"
            )
            if scenario_key in seen:
                continue
            seen.add(scenario_key)
            projections.append(
                ScenarioProjection(
                    scenario_key=scenario_key,
                    scenario_name=name,
                    description=cls._first_text(
                        item,
                        "scenario_description",
                        "description",
                        "task_goal",
                    )
                    or "",
                    decision_stage=cls._first_text(
                        item,
                        "decision_stage",
                        "stage",
                    )
                    or "",
                    source_payload=item,
                )
            )
        return tuple(projections)

    @classmethod
    def _build_answer_projection(
        cls,
        *,
        question_id: str,
        platform_result: dict[str, Any],
        fallback_index: int,
    ) -> AnswerProjection:
        platform = cls._canonical_platform(cls._first_text(platform_result, "platform"))
        fetch_method = cls._first_text(platform_result, "fetch_method", "method") or ""
        success = bool(platform_result.get("success"))
        raw_status = cls._first_text(platform_result, "status")
        status = cls._normalize_platform_answer_status(raw_status, success=success)
        answer_payload = cls._answer_payload(platform_result.get("answer"))
        answer_text = cls._answer_text(platform_result.get("answer"))
        run_id = cls._first_text(platform_result, "run_id", "task_run_id")
        duration_ms = cls._number_or_none(
            platform_result.get("duration_ms", platform_result.get("duration"))
        )
        brand_mentioned = cls._brand_mentioned(answer_payload)
        dedupe_key = "answer:" + cls._stable_hash(
            [
                question_id,
                platform,
                fetch_method,
                run_id or str(fallback_index),
                answer_text,
            ]
        )
        return AnswerProjection(
            dedupe_key=dedupe_key,
            question_id=question_id,
            platform=platform,
            fetch_method=fetch_method,
            status=status,
            success=success,
            answer_text=answer_text,
            answer_payload=answer_payload,
            raw_payload=platform_result,
            run_id=run_id,
            brand_mentioned=brand_mentioned,
            duration_ms=duration_ms,
        )

    @classmethod
    def _normalize_platform_answer_status(
        cls,
        raw_status: str | None,
        *,
        success: bool,
    ) -> str:
        cleaned = str(raw_status or "").strip().lower()
        if cleaned in {"requested", "captured", "failed", "superseded"}:
            return cleaned
        if cleaned in PLATFORM_ANSWER_LIFECYCLE_ALIASES:
            return PLATFORM_ANSWER_LIFECYCLE_ALIASES[cleaned]
        return "captured" if success else "failed"

    @classmethod
    def _build_citation_projections(
        cls,
        *,
        answer: AnswerProjection,
        platform_result: dict[str, Any],
    ) -> tuple[CitationProjection, ...]:
        raw_citations = platform_result.get("citations")
        if not isinstance(raw_citations, list) and answer.answer_payload:
            raw_citations = answer.answer_payload.get("citations")
        if not isinstance(raw_citations, list):
            return ()

        projections: list[CitationProjection] = []
        for index, raw_item in enumerate(raw_citations, start=1):
            if isinstance(raw_item, str):
                item = {"url": raw_item}
            elif isinstance(raw_item, dict):
                item = raw_item
            else:
                continue
            url = cls._first_text(item, "url", "link", "href") or ""
            title = cls._first_text(item, "title", "source_title", "name") or ""
            domain = (
                cls._first_text(item, "domain") or cls._domain_from_url(url) or title
            )
            snippet = cls._first_text(item, "snippet", "summary", "text") or ""
            confidence = cls._number_or_none(item.get("confidence"))
            dedupe_key = "citation:" + cls._stable_hash(
                [answer.dedupe_key, url, domain, title, str(index)]
            )
            projections.append(
                CitationProjection(
                    dedupe_key=dedupe_key,
                    answer_dedupe_key=answer.dedupe_key,
                    url=url,
                    domain=domain,
                    source_title=title,
                    snippet=snippet,
                    confidence=confidence,
                    citation_payload=item,
                )
            )
        return tuple(projections)

    @staticmethod
    def _first_text(payload: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if value is not None and not isinstance(value, (dict, list)):
                text = str(value).strip()
                if text:
                    return text
        return ""

    @staticmethod
    def _answer_payload(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return {"content": value}
        return None

    @classmethod
    def _answer_text(cls, value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return cls._first_text(value, "content", "text", "answer")
        return ""

    @staticmethod
    def _brand_mentioned(answer_payload: dict[str, Any] | None) -> bool | None:
        if not answer_payload:
            return None
        value = answer_payload.get("has_brand_mention")
        return value if isinstance(value, bool) else None

    @classmethod
    def _extract_sentiment(
        cls, payload: dict[str, Any], fallback_text: str = ""
    ) -> str:
        for key in (
            "sentiment",
            "brand_sentiment",
            "mention_sentiment",
            "tone",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return cls._normalize_sentiment(value)
        text = str(fallback_text or "")
        if any(token in text for token in ("优势", "领先", "推荐", "适合", "优秀")):
            return "positive"
        if any(token in text for token in ("不足", "风险", "投诉", "问题", "负面")):
            return "negative"
        return "neutral"

    @classmethod
    def _extract_mention_quote(
        cls,
        payload: dict[str, Any],
        fallback_text: str = "",
    ) -> str:
        for key in (
            "mention_quote",
            "brand_mention_quote",
            "quote",
            "snippet",
            "evidence",
            "content",
            "text",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return cls._safe_preview(value, limit=360)
        return cls._safe_preview(fallback_text, limit=360)

    @classmethod
    def _extract_competitor_mentions(
        cls,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for key in (
            "competitor_mentions",
            "competitors",
            "mentioned_competitors",
            "mentioned_brands",
        ):
            value = payload.get(key)
            if isinstance(value, list):
                items.extend(cls._as_dict_list(value))
        return items

    @staticmethod
    def _as_dict_list(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        rows: list[dict[str, Any]] = []
        for item in value:
            if isinstance(item, dict):
                rows.append(item)
            elif isinstance(item, str) and item.strip():
                rows.append({"name": item.strip()})
        return rows

    @staticmethod
    def _brand_key(value: str) -> str:
        return "".join(str(value or "").casefold().split())

    @staticmethod
    def _safe_preview(value: Any, *, limit: int) -> str:
        text = " ".join(str(value or "").split())
        if len(text) <= limit:
            return text
        return text[: limit - 1] + "..."

    @staticmethod
    def _normalize_sentiment(value: str) -> str:
        cleaned = str(value or "").strip().lower()
        positive_values = {"positive", "pos", "good", "favorable", "正向", "积极"}
        negative_values = {"negative", "neg", "bad", "unfavorable", "负向", "消极"}
        neutral_values = {"neutral", "neu", "mixed", "中性", "客观", "未知"}
        if cleaned in positive_values:
            return "positive"
        if cleaned in negative_values:
            return "negative"
        if cleaned in neutral_values:
            return "neutral"
        return "neutral"

    @staticmethod
    def _public_mention_payload(payload: dict[str, Any]) -> dict[str, Any]:
        public_keys = {
            "platform",
            "question_id",
            "sentiment",
            "tone",
            "confidence",
            "source",
            "domain",
            "url",
        }
        return {key: payload.get(key) for key in public_keys if key in payload}

    @staticmethod
    def _number_or_none(value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                return None
        return None

    @staticmethod
    def _canonical_platform(value: str) -> str:
        normalized = str(value or "").strip().lower()
        if normalized == "hunyuan":
            return "yuanbao"
        return normalized

    @classmethod
    def _report_summary(cls, payload: dict[str, Any]) -> str:
        for key in (
            "executive_summary_text",
            "executive_summary",
            "summary",
            "headline",
            "description",
        ):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:2000]
        sections = payload.get("sections")
        if isinstance(sections, list):
            for section in sections:
                if not isinstance(section, dict):
                    continue
                text = cls._first_text(section, "summary", "content", "text")
                if text:
                    return text[:2000]
        return ""

    @staticmethod
    def _extract_metric_payload(payload: dict[str, Any]) -> dict[str, Any]:
        for key in ("metrics", "metric_snapshot"):
            value = payload.get(key)
            if isinstance(value, dict):
                return value
        data = payload.get("data")
        if isinstance(data, dict):
            value = data.get("metrics") or data.get("metric_snapshot")
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _domain_from_url(url: str) -> str:
        if not url:
            return ""
        parsed = urlparse(url if "://" in url else f"https://{url}")
        return parsed.netloc.lower()

    @classmethod
    def _stable_object_key(cls, prefix: str, value: str) -> str:
        cleaned = " ".join(str(value or "").split()).casefold()
        if not cleaned:
            return ""
        return f"{prefix}:{cls._stable_hash([cleaned])[:16]}"

    @staticmethod
    def _stable_hash(parts: list[str]) -> str:
        payload = json.dumps(parts, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:40]
