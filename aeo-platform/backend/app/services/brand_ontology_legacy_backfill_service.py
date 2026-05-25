"""Project legacy brand analysis artifacts into the ontology object world."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import (
    BrandIntelligenceQuestion,
    BrandPlatformAnswer,
    BrandReportVersion,
)
from app.models.fetch_run_platform_state import FetchRunPlatformState
from app.models.message import Message, MessageType
from app.models.monitoring_plan import MonitoringPlan, MonitoringQuestionSet
from app.models.session import Session
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.services.brand_intelligence_projection_service import (
    BrandIntelligenceProjectionService,
)
from app.services.brand_object_link_service import BrandObjectLinkService
from app.services.fetch_run_platform_state_service import FetchRunPlatformStateService
from app.services.monitoring_plan_service import MonitoringPlanService


class BrandOntologyLegacyBackfillService:
    """Bridges pre-ontology analysis state into durable objects and links.

    New A3/A4/A5 paths already dual-write to ontology objects. This service handles
    brands whose useful evidence exists only in older chat outputs, monitoring
    question sets, fetch run state, or analysis snapshots.
    """

    MESSAGE_SCAN_LIMIT = 20
    QUESTION_SET_SCAN_LIMIT = 50
    PLAN_SCAN_LIMIT = 20
    FETCH_STATE_SCAN_LIMIT = 120
    SNAPSHOT_SCAN_LIMIT = 1

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.projection = BrandIntelligenceProjectionService(db)
        self.links = BrandObjectLinkService(db)

    async def run(
        self,
        *,
        entity_id: UUID,
        force: bool = False,
    ) -> dict[str, Any]:
        """Project missing legacy state for one brand entity.

        The method is idempotent for questions, answers, citations, and links. Report
        versions are append-only, so legacy reports are skipped once their message,
        artifact id, or report id is already represented.
        """

        counts = {
            "question_sets": 0,
            "monitoring_plans": 0,
            "questions": 0,
            "fetch_bundles": 0,
            "answers": 0,
            "citations": 0,
            "mentions": 0,
            "reports": 0,
            "brand_context_sources": 0,
            "snapshots": 0,
        }
        existing = await self._existing_counts(entity_id=entity_id)
        if force or existing["questions"] == 0:
            question_counts = await self._project_monitoring_question_sets(
                entity_id=entity_id,
            )
            counts["question_sets"] += question_counts["question_sets"]
            counts["questions"] += question_counts["questions"]

        plan_counts = await self._project_monitoring_plan_links(entity_id=entity_id)
        counts["monitoring_plans"] += plan_counts["monitoring_plans"]
        counts["questions"] += plan_counts["questions"]

        if force or existing["answers"] == 0:
            fetch_state_counts = await self._project_fetch_run_states(
                entity_id=entity_id,
            )
            counts["fetch_bundles"] += fetch_state_counts["fetch_bundles"]
            counts["answers"] += fetch_state_counts["answers"]
            counts["citations"] += fetch_state_counts["citations"]

        message_existing = {
            **existing,
            "questions": existing["questions"] or int(counts["questions"] > 0),
            "answers": existing["answers"] or int(counts["answers"] > 0),
            "reports": existing["reports"] or int(counts["reports"] > 0),
        }
        message_counts = await self._project_message_outputs(
            entity_id=entity_id,
            existing=message_existing,
            force=force,
        )
        for key in (
            "questions",
            "fetch_bundles",
            "answers",
            "citations",
            "mentions",
            "reports",
            "brand_context_sources",
        ):
            counts[key] += message_counts[key]

        snapshot_counts = (
            await self._project_snapshots(
                entity_id=entity_id,
                force=force,
            )
            if force or (existing["reports"] == 0 and counts["reports"] == 0)
            else {"snapshots": 0, "reports": 0}
        )
        counts["snapshots"] += snapshot_counts["snapshots"]
        counts["reports"] += snapshot_counts["reports"]
        counts[
            "mentions"
        ] += await self.projection.persist_mentions_for_existing_answers(
            entity_id=entity_id
        )

        await self.db.flush()
        return {
            **counts,
            "changed": any(value > 0 for value in counts.values()),
        }

    async def _existing_counts(self, *, entity_id: UUID) -> dict[str, int]:
        return {
            "questions": await self._count(BrandIntelligenceQuestion, entity_id),
            "answers": await self._count(BrandPlatformAnswer, entity_id),
            "reports": await self._count(BrandReportVersion, entity_id),
        }

    async def _project_monitoring_question_sets(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, int]:
        question_sets = (
            (
                await self.db.execute(
                    select(MonitoringQuestionSet)
                    .where(MonitoringQuestionSet.entity_id == entity_id)
                    .order_by(desc(MonitoringQuestionSet.updated_at))
                    .limit(self.QUESTION_SET_SCAN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        service = MonitoringPlanService(self.db)
        question_count = 0
        for question_set in question_sets:
            question_rows = await service._ensure_brand_questions_for_question_set(
                question_set,
            )
            question_count += len(question_rows)
            for question in question_rows:
                await self.links.ensure_link(
                    entity_id=entity_id,
                    link_type="question_set_contains_question",
                    from_object_type="question_set",
                    from_object_id=str(question_set.id),
                    to_object_type="simulated_question",
                    to_object_id=str(question.id),
                    extra_metadata={
                        "question_set_id": str(question_set.id),
                        "question_id": question.question_id,
                    },
                )
        return {
            "question_sets": len(question_sets),
            "questions": question_count,
        }

    async def _project_monitoring_plan_links(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, int]:
        plans = (
            (
                await self.db.execute(
                    select(MonitoringPlan)
                    .where(MonitoringPlan.entity_id == entity_id)
                    .order_by(desc(MonitoringPlan.updated_at))
                    .limit(self.PLAN_SCAN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        service = MonitoringPlanService(self.db)
        question_count = 0
        linked_plan_count = 0
        for plan in plans:
            question_sets = await self._question_sets_for_plan(plan)
            if not question_sets:
                continue
            await service._replace_monitoring_plan_links(plan, question_sets)
            question_count += sum(
                int(question_set.question_count or 0) for question_set in question_sets
            )
            linked_plan_count += 1
        return {
            "monitoring_plans": linked_plan_count,
            "questions": question_count,
        }

    async def _project_fetch_run_states(
        self,
        *,
        entity_id: UUID,
    ) -> dict[str, int]:
        rows = (
            (
                await self.db.execute(
                    select(FetchRunPlatformState)
                    .where(FetchRunPlatformState.entity_id == entity_id)
                    .order_by(
                        desc(FetchRunPlatformState.updated_at),
                        desc(FetchRunPlatformState.created_at),
                    )
                    .limit(self.FETCH_STATE_SCAN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        latest_rows = _latest_fetch_state_group(rows)
        if not latest_rows:
            return {"fetch_bundles": 0, "answers": 0, "citations": 0}
        projection = FetchRunPlatformStateService(self.db).build_summary_projection(
            latest_rows,
        )
        fetch_results = projection.get("fetch_results")
        if not fetch_results:
            return {"fetch_bundles": 0, "answers": 0, "citations": 0}
        session_id = latest_rows[0].session_id
        counts = await self.projection.persist_fetch_results(
            entity_id=entity_id,
            session_id=session_id,
            fetch_results=fetch_results,
        )
        return {
            "fetch_bundles": 1,
            "answers": int(counts.get("answers") or 0),
            "citations": int(counts.get("citations") or 0),
        }

    async def _project_message_outputs(
        self,
        *,
        entity_id: UUID,
        existing: dict[str, int],
        force: bool,
    ) -> dict[str, int]:
        messages = (
            (
                await self.db.execute(
                    select(Message)
                    .join(Session, Message.session_id == Session.id)
                    .where(
                        Session.entity_id == entity_id,
                        Message.type == MessageType.OUTPUT,
                    )
                    .order_by(desc(Message.created_at))
                    .limit(self.MESSAGE_SCAN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        counts = {
            "questions": 0,
            "fetch_bundles": 0,
            "answers": 0,
            "citations": 0,
            "mentions": 0,
            "reports": 0,
            "brand_context_sources": 0,
        }
        latest_report_message_id = _latest_report_message_id(messages)
        for message in reversed(messages):
            payload = _safe_json_loads(message.output_data)
            if not isinstance(payload, dict):
                continue
            context_counts = await self._project_brand_context_from_payload(
                entity_id=entity_id,
                session_id=message.session_id,
                payload=payload,
            )
            if any(context_counts.values()):
                counts["brand_context_sources"] += 1

            question_payload = _extract_question_payload(payload)
            if question_payload is not None and (force or existing["questions"] == 0):
                questions = await self.projection.persist_questions(
                    entity_id=entity_id,
                    session_id=message.session_id,
                    payload=question_payload,
                )
                counts["questions"] += len(questions)

            fetch_results = _extract_fetch_results(payload)
            if fetch_results and (force or existing["answers"] == 0):
                fetch_counts = await self.projection.persist_fetch_results(
                    entity_id=entity_id,
                    session_id=message.session_id,
                    fetch_results=fetch_results,
                )
                counts["fetch_bundles"] += 1
                counts["answers"] += int(fetch_counts.get("answers") or 0)
                counts["citations"] += int(fetch_counts.get("citations") or 0)

            report_payload = _extract_report_payload(payload)
            if report_payload is None:
                continue
            if (
                latest_report_message_id is not None
                and message.id != latest_report_message_id
            ):
                continue
            artifact_id = _message_artifact_id(message=message, payload=payload)
            report_id = str(report_payload.get("report_id") or artifact_id).strip()
            if not force and await self._report_already_projected(
                entity_id=entity_id,
                report_id=report_id,
                artifact_id=artifact_id,
                message_id=message.id,
            ):
                continue
            await self.projection.persist_report_artifact(
                entity_id=entity_id,
                session_id=message.session_id,
                report_kind=_report_kind(payload, report_payload),
                title=_report_title(message=message, payload=report_payload),
                artifact_id=artifact_id,
                payload={**report_payload, "report_id": report_id},
                message_id=message.id,
            )
            counts["reports"] += 1
        return counts

    async def _project_brand_context_from_payload(
        self,
        *,
        entity_id: UUID,
        session_id: UUID | None,
        payload: dict[str, Any],
    ) -> dict[str, int]:
        competitors = payload.get("competitors")
        marketing_personas = (
            payload.get("marketing_personas")
            or payload.get("personas")
            or payload.get("user_personas")
        )
        if not isinstance(competitors, list) and marketing_personas is None:
            return {"competitors": 0, "personas": 0, "scenarios": 0}
        return await self.projection.persist_brand_context(
            entity_id=entity_id,
            session_id=session_id,
            competitors=competitors if isinstance(competitors, list) else None,
            marketing_personas=marketing_personas,
        )

    async def _project_snapshots(
        self,
        *,
        entity_id: UUID,
        force: bool,
    ) -> dict[str, int]:
        snapshots = (
            (
                await self.db.execute(
                    select(AnalysisSnapshot)
                    .where(
                        AnalysisSnapshot.entity_id == entity_id,
                        AnalysisSnapshot.status.in_(
                            [SnapshotStatus.COMPLETED, SnapshotStatus.PARTIAL]
                        ),
                    )
                    .order_by(desc(AnalysisSnapshot.created_at))
                    .limit(self.SNAPSHOT_SCAN_LIMIT)
                )
            )
            .scalars()
            .all()
        )
        counts = {"snapshots": 0, "reports": 0}
        for snapshot in snapshots:
            payload = _snapshot_report_payload(snapshot)
            if payload is None:
                continue
            artifact_id = f"snapshot:{snapshot.id}"
            report_id = str(payload.get("report_id") or artifact_id).strip()
            if not force and await self._report_already_projected(
                entity_id=entity_id,
                report_id=report_id,
                artifact_id=artifact_id,
                message_id=None,
            ):
                continue
            await self.projection.persist_report_artifact(
                entity_id=entity_id,
                session_id=snapshot.session_id,
                report_kind=str(
                    payload.get("report_kind")
                    or payload.get("_report_kind")
                    or snapshot.snapshot_type
                    or "snapshot"
                ),
                title=str(payload.get("title") or "历史分析快照"),
                artifact_id=artifact_id,
                payload={**payload, "report_id": report_id},
            )
            counts["snapshots"] += 1
            counts["reports"] += 1
        return counts

    async def _question_sets_for_plan(
        self,
        plan: MonitoringPlan,
    ) -> list[MonitoringQuestionSet]:
        raw_ids = (
            plan.question_set_ids if isinstance(plan.question_set_ids, list) else []
        )
        question_set_ids: list[UUID] = []
        for raw_id in raw_ids:
            try:
                question_set_ids.append(UUID(str(raw_id)))
            except (TypeError, ValueError):
                continue
        if not question_set_ids:
            return []
        rows = (
            (
                await self.db.execute(
                    select(MonitoringQuestionSet).where(
                        MonitoringQuestionSet.entity_id == plan.entity_id,
                        MonitoringQuestionSet.id.in_(question_set_ids),
                    )
                )
            )
            .scalars()
            .all()
        )
        by_id = {row.id: row for row in rows}
        return [by_id[item] for item in question_set_ids if item in by_id]

    async def _report_already_projected(
        self,
        *,
        entity_id: UUID,
        report_id: str,
        artifact_id: str,
        message_id: UUID | None,
    ) -> bool:
        conditions = [BrandReportVersion.entity_id == entity_id]
        if message_id is not None:
            message_match = (
                await self.db.execute(
                    select(BrandReportVersion.id)
                    .where(
                        *conditions,
                        BrandReportVersion.message_id == message_id,
                    )
                    .limit(1)
                )
            ).scalar_one_or_none()
            if message_match is not None:
                return True
        row = (
            await self.db.execute(
                select(BrandReportVersion.id)
                .where(
                    *conditions,
                    (
                        (BrandReportVersion.report_id == report_id)
                        | (BrandReportVersion.artifact_id == artifact_id)
                    ),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        return row is not None

    async def _count(self, model: type, entity_id: UUID) -> int:
        return int(
            (
                await self.db.execute(
                    select(model.id).where(model.entity_id == entity_id).limit(1)
                )
            ).scalar_one_or_none()
            is not None
        )


def _safe_json_loads(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None


def _extract_question_payload(payload: dict[str, Any]) -> Any | None:
    for key in ("simulated_questions", "questions", "items"):
        if isinstance(payload.get(key), list):
            return payload
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_question_payload(data)
    return None


def _extract_fetch_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("fetchResults", "fetch_results", "fetch_results_summary", "results"):
        value = payload.get(key)
        if isinstance(value, list):
            if key == "fetch_results_summary":
                return [{"platform_results": value}]
            return [item for item in value if isinstance(item, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_fetch_results(data)
    return []


def _extract_report_payload(payload: dict[str, Any]) -> dict[str, Any] | None:
    report = payload.get("report")
    if isinstance(report, dict):
        return {
            **report,
            **{
                key: payload[key]
                for key in (
                    "metric_bundle",
                    "comparison_bundle",
                    "dashboard_projection",
                )
                if isinstance(payload.get(key), dict) and key not in report
            },
        }
    if (
        payload.get("artifact_kind") == "geo_report"
        or payload.get("_artifact_kind") == "geo_report"
    ):
        return payload
    if any(
        key in payload
        for key in (
            "executive_summary",
            "key_findings",
            "findings",
            "report_v2",
            "dashboard_projection",
            "metric_bundle",
        )
    ):
        return payload
    data = payload.get("data")
    if isinstance(data, dict):
        return _extract_report_payload(data)
    return None


def _latest_report_message_id(messages: list[Message]) -> UUID | None:
    for message in messages:
        payload = _safe_json_loads(message.output_data)
        if isinstance(payload, dict) and _extract_report_payload(payload) is not None:
            return message.id
    return None


def _snapshot_report_payload(snapshot: AnalysisSnapshot) -> dict[str, Any] | None:
    raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
    report_data = raw_data.get("report_data")
    report_data = report_data if isinstance(report_data, dict) else {}
    if not report_data:
        return None
    return {
        **report_data,
        "metric_bundle": (
            raw_data.get("metric_bundle")
            if isinstance(raw_data.get("metric_bundle"), dict)
            else report_data.get("metric_bundle")
        ),
        "comparison_bundle": (
            raw_data.get("comparison_bundle")
            if isinstance(raw_data.get("comparison_bundle"), dict)
            else report_data.get("comparison_bundle")
        ),
        "dashboard_projection": (
            raw_data.get("dashboard_projection")
            if isinstance(raw_data.get("dashboard_projection"), dict)
            else report_data.get("dashboard_projection")
        ),
        "_report_kind": str(
            raw_data.get("report_kind") or snapshot.snapshot_type or ""
        ),
        "_triggered_by": str(snapshot.triggered_by or ""),
    }


def _message_artifact_id(*, message: Message, payload: dict[str, Any]) -> str:
    metadata = _safe_json_loads(message.extra_metadata)
    if isinstance(metadata, dict) and isinstance(metadata.get("output_id"), str):
        return metadata["output_id"]
    value = payload.get("artifact_id") or payload.get("output_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return f"message:{message.id}"


def _report_kind(payload: dict[str, Any], report_payload: dict[str, Any]) -> str:
    for key in ("report_kind", "_report_kind", "snapshot_type", "monitor_mode"):
        value = report_payload.get(key) or payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "legacy_report"


def _report_title(*, message: Message, payload: dict[str, Any]) -> str:
    for key in ("title", "report_title", "name"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:255]
    return str(message.content or "历史分析报告").strip()[:255]


def _latest_fetch_state_group(
    rows: list[FetchRunPlatformState],
) -> list[FetchRunPlatformState]:
    if not rows:
        return []
    first = rows[0]
    return [
        row
        for row in rows
        if row.task_run_id == first.task_run_id and row.session_id == first.session_id
    ]
