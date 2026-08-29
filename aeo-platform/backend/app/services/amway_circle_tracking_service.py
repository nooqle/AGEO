"""Read helpers for Amway China circle tracking snapshots."""

from __future__ import annotations

import calendar
import hashlib
import json
import re
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import and_, desc, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.amway_circle_tracking import (
    AmwayCircleAnswer,
    AmwayCircleEdgeSnapshot,
    AmwayCircleEntityMention,
    AmwayCircleEvidence,
    AmwayCircleNodeSnapshot,
    AmwayCircleProjection,
    AmwayCircleReport,
    AmwayCircleRun,
)
from app.models.brand_intelligence_run import BrandIntelligenceRun
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringQuestionSet
from app.models.snapshot import AnalysisSnapshot
from app.ontology import load_default_amway_entity_ontology
from app.services.brand_association_circle_variant import (
    is_amway_association_entity,
)
from app.services.amway_entity_calibration_service import (
    CALIBRATION_SCHEMA_VERSION,
    SKEPTICAL_CONTEXT_CUES,
    SUPPORTIVE_CONTEXT_CUES,
)
from app.services.amway_entity_extraction_service import EXTRACTION_SCHEMA_VERSION
from app.tools.a4_fetch_agent import normalize_public_platform_id
from app.workflow.a5.association_circle import (
    REPORT_COPY_CONSTRAINT_VERSION,
    SCHEMA_VERSION as REPORT_SCHEMA_VERSION,
    _build_report_quality_checks,
    build_brand_association_circle_report_artifact,
)

COMPLETED_RUN_STATUSES = ("completed", "partial")
PERIOD_DAY_COUNTS = {
    "last_7_days": 7,
    "last_14_days": 14,
    "last_30_days": 30,
}
PERIOD_VIEW_PROJECTION_VERSION = "amway-period-view.v9"
CHINA_TZ = timezone(timedelta(hours=8))
TRACK_ALIASES = {
    "stable": "stable",
    "stable_asset": "stable",
    "core_near": "stable",
    "strong": "stable",
    "opportunity": "opportunity",
    "near_opportunity": "opportunity",
    "far_opportunity": "opportunity",
    "contestable": "opportunity",
    "watch": "watch",
    "watch_signal": "watch",
    "evidence_gap": "watch",
    "weak": "watch",
    "blank": "watch",
    "risk": "risk",
    "risk_shadow": "risk",
}


class AmwayCircleTrackingService:
    """Expose persisted Amway circle runs, projections, and node evidence."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_runs(self, entity_id: UUID, *, limit: int = 30) -> dict[str, Any]:
        rows = (
            (
                await self.db.execute(
                    select(AmwayCircleRun)
                    .where(AmwayCircleRun.entity_id == entity_id)
                    .order_by(desc(AmwayCircleRun.created_at))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )
        run_ids = [row.id for row in rows]
        latest_projection_ids = await self._latest_projection_ids(run_ids)
        latest_report_ids = await self._latest_report_ids(run_ids)
        total = await self._run_count(entity_id)
        return {
            "runs": [
                self._run_summary(
                    row,
                    latest_projection_ids.get(row.id),
                    latest_report_ids.get(row.id),
                )
                for row in rows
            ],
            "total": total,
        }

    async def get_projection(
        self,
        entity_id: UUID,
        *,
        scope: str = "cumulative",
        run_id: UUID | None = None,
        base_run_id: UUID | None = None,
        target_run_id: UUID | None = None,
    ) -> dict[str, Any] | None:
        query = select(AmwayCircleProjection).where(
            AmwayCircleProjection.entity_id == entity_id,
            AmwayCircleProjection.projection_scope == scope,
        )
        query = query.where(AmwayCircleProjection.status == "ready")
        if scope == "run":
            if run_id is None:
                return None
            query = query.where(AmwayCircleProjection.circle_run_id == run_id)
        elif scope == "compare":
            if base_run_id is not None:
                query = query.where(AmwayCircleProjection.base_run_id == base_run_id)
            if target_run_id is not None:
                query = query.where(
                    AmwayCircleProjection.target_run_id == target_run_id
                )
            if base_run_id is None and target_run_id is None:
                query = query.where(AmwayCircleProjection.is_latest.is_(True))
        else:
            query = query.where(AmwayCircleProjection.is_latest.is_(True))
        row = (
            (
                await self.db.execute(
                    query.order_by(
                        desc(AmwayCircleProjection.is_latest),
                        desc(AmwayCircleProjection.built_at),
                    ).limit(1)
                )
            )
            .scalars()
            .first()
        )
        return self._projection_payload(row) if row else None

    async def get_period_view(
        self,
        entity_id: UUID,
        *,
        period_type: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        center_term: str | None = None,
    ) -> dict[str, Any]:
        current_start: datetime | None = None
        current_end: datetime | None = None
        previous_start: datetime | None = None
        previous_end: datetime | None = None
        previous_include_end = False

        if period_type == "custom":
            if start_at is None or end_at is None:
                raise ValueError("自定义周期需要同时提供 start_at 和 end_at。")
            current_start = _as_utc(start_at)
            current_end = _as_utc(end_at)
            if current_start >= current_end:
                raise ValueError("start_at 必须早于 end_at。")
            natural_months = _natural_month_count(current_start, current_end)
            if natural_months:
                previous_start = _shift_month_start(current_start, -natural_months)
                previous_end = current_start - timedelta(microseconds=1)
                previous_include_end = True
            else:
                span = current_end - current_start
                previous_start = current_start - span
                previous_end = current_start
        elif period_type != "latest_run" and period_type not in PERIOD_DAY_COUNTS:
            raise ValueError("不支持的周期类型。")

        latest = await self._latest_completed_run(entity_id, center_term=center_term)
        if latest is None:
            if period_type == "custom":
                current_summary = _period_summary(
                    period_type,
                    [],
                    current_start,
                    current_end,
                )
                projection = _empty_period_projection(
                    current_summary,
                    center_term or "安利",
                )
                notice = _comparison_notice([], [], False)
                _attach_period_tracking(
                    projection,
                    current_summary,
                    None,
                    [],
                    False,
                    notice,
                )
                return {
                    "period_type": period_type,
                    "current_period": current_summary,
                    "previous_period": None,
                    "question_set_changed": False,
                    "comparison_notice": notice,
                    "change_top5": [],
                    "projection": projection,
                    "report_input": _period_report_input(
                        current_summary,
                        None,
                        [],
                        False,
                        notice,
                        projection,
                    ),
                    "report_id": None,
                }
            return _empty_period_view(period_type)

        if period_type == "latest_run":
            current_runs = [latest]
            previous = await self._previous_completed_run(
                entity_id,
                latest,
                center_term=center_term,
            )
            previous_runs = [previous] if previous else []
        else:
            if period_type != "custom":
                days = PERIOD_DAY_COUNTS.get(period_type)
                assert days is not None
                current_end = _as_utc(latest.completed_at or latest.created_at)
                current_start = current_end - timedelta(days=days)
                span = timedelta(days=days)
                previous_end = current_start
                previous_start = current_start - span
            current_runs = await self._completed_runs_between(
                entity_id,
                current_start,
                current_end,
                center_term=center_term,
                include_end=period_type != "custom",
            )
            previous_runs = await self._completed_runs_between(
                entity_id,
                previous_start,
                previous_end,
                center_term=center_term,
                include_end=previous_include_end,
            )

        current_projections = await self._run_projections(
            entity_id,
            [row.id for row in current_runs],
        )
        previous_projections = await self._run_projections(
            entity_id,
            [row.id for row in previous_runs],
        )
        current_summary = _period_summary(
            period_type,
            current_runs,
            current_start,
            current_end,
        )
        previous_summary = (
            _period_summary("previous", previous_runs, previous_start, previous_end)
            if previous_runs
            else None
        )
        previous_projection = _aggregate_projection(
            previous_projections,
            _projection_summary(previous_summary, previous_projections),
        )
        if previous_projection is not None:
            await self._apply_regulatory_risk_scope(
                previous_projection,
                [row.id for row in previous_runs],
            )
        if previous_projection is not None:
            previous_summary = _dict(previous_projection.get("sample_scope"))
        projection = _aggregate_projection(
            current_projections,
            _projection_summary(current_summary, current_projections),
        )
        if projection is not None:
            await self._apply_regulatory_risk_scope(
                projection,
                [row.id for row in current_runs],
            )
        if projection is not None:
            current_summary = _dict(projection.get("sample_scope"))
        if projection is None:
            projection = _empty_period_projection(
                current_summary,
                center_term or latest.center_term or "安利",
            )
        change_top5 = (
            _change_top5(projection, previous_projection)
            if _should_compare_period(
                current_projections,
                previous_projection,
                projection,
            )
            else []
        )
        question_set_changed = bool(current_runs and previous_runs) and (
            _question_signatures(current_runs) != _question_signatures(previous_runs)
        )
        notice = _comparison_notice(current_runs, previous_runs, question_set_changed)
        if previous_summary is not None and (
            _int(current_summary.get("valid_answer_count")) <= 0
            or _int(previous_summary.get("valid_answer_count")) <= 0
        ):
            notice = "任一期没有有效回答，提及率不可评估，不生成方向性变化。"
        if projection:
            _attach_period_tracking(
                projection,
                current_summary,
                previous_summary,
                change_top5,
                question_set_changed,
                notice,
            )
        view = {
            "period_type": period_type,
            "current_period": current_summary,
            "previous_period": previous_summary,
            "question_set_changed": question_set_changed,
            "comparison_notice": notice,
            "change_top5": change_top5,
            "projection": projection,
            "report_input": _period_report_input(
                current_summary,
                previous_summary,
                change_top5,
                question_set_changed,
                notice,
                projection,
            ),
            "report_id": None,
        }
        source_hash = _period_view_source_hash(
            period_type=period_type,
            current_summary=current_summary,
            previous_summary=previous_summary,
            current_projections=current_projections,
            previous_projections=previous_projections,
            center_term=center_term or latest.center_term or "安利",
        )
        saved = await self._period_view_report(entity_id, source_hash)
        if saved:
            saved_projection, saved_report = saved
            view["projection"] = _normalize_period_projection(
                saved_projection.association_circle_projection
            )
            await self._apply_regulatory_risk_scope(
                view["projection"],
                [row.id for row in current_runs],
            )
            _finalize_period_projection_quality(view["projection"])
            view["report_id"] = str(saved_report.id)
            view["report_input"] = _period_report_input(
                current_summary,
                previous_summary,
                change_top5,
                question_set_changed,
                notice,
                view["projection"],
            )
        return view

    async def _apply_regulatory_risk_scope(
        self,
        projection: dict[str, Any],
        run_ids: list[UUID],
    ) -> None:
        if not run_ids:
            return
        has_regulatory_risk = any(
            isinstance(node, dict)
            and str(
                node.get("lexicon_entity_id") or node.get("entity_id") or ""
            ).strip()
            == "evidence_regulation"
            and _node_track(node) == "risk"
            for node in _list(projection.get("nodes"))
        )
        if not has_regulatory_risk:
            return
        rows = (
            await self.db.execute(
                select(
                    AmwayCircleAnswer.platform,
                    AmwayCircleEntityMention.circle_run_id,
                    AmwayCircleEntityMention.answer_id,
                    AmwayCircleEntityMention.relation_type,
                    AmwayCircleEntityMention.sentiment_context,
                    AmwayCircleEntityMention.context_text,
                    AmwayCircleEntityMention.evidence_text,
                    AmwayCircleEntityMention.risk_context,
                    AmwayCircleAnswer.question_text,
                )
                .join(
                    AmwayCircleAnswer,
                    and_(
                        AmwayCircleAnswer.id == AmwayCircleEntityMention.answer_id,
                        AmwayCircleAnswer.circle_run_id
                        == AmwayCircleEntityMention.circle_run_id,
                    ),
                )
                .where(
                    AmwayCircleEntityMention.circle_run_id.in_(run_ids),
                    AmwayCircleEntityMention.lexicon_entity_id == "evidence_regulation",
                )
                .order_by(
                    AmwayCircleEntityMention.created_at,
                    AmwayCircleEntityMention.id,
                )
            )
        ).all()
        if not rows:
            return

        stance_by_answer: dict[UUID, str] = {}
        platform_by_answer: dict[UUID, str] = {}
        run_by_answer: dict[UUID, UUID] = {}
        for (
            platform,
            circle_run_id,
            answer_id,
            relation_type,
            sentiment_context,
            context_text,
            evidence_text,
            risk_context,
            question_text,
        ) in rows:
            if answer_id in stance_by_answer:
                continue
            run_by_answer[answer_id] = circle_run_id
            platform_by_answer[answer_id] = _normalize_platform_name(platform)
            stance = _persisted_regulatory_stance(
                relation_type=relation_type,
                sentiment_context=sentiment_context,
                context_text=context_text,
                evidence_text=evidence_text,
                risk_context=risk_context,
                question_text=question_text,
            )
            stance_by_answer[answer_id] = stance

        stance_by_answer = {
            answer_id: stance
            for answer_id, stance in stance_by_answer.items()
            if stance in {"skeptical", "risk", "competitive"}
        }
        platform_by_answer = {
            answer_id: platform
            for answer_id, platform in platform_by_answer.items()
            if answer_id in stance_by_answer
        }

        platform_distribution: dict[str, int] = {}
        for answer_id, platform in platform_by_answer.items():
            if not platform:
                continue
            platform_distribution[platform] = platform_distribution.get(platform, 0) + 1
        stance_summary = {
            "supportive": 0,
            "neutral": 0,
            "skeptical": sum(
                1 for stance in stance_by_answer.values() if stance == "skeptical"
            ),
            "risk": sum(1 for stance in stance_by_answer.values() if stance == "risk"),
            "competitive": sum(
                1 for stance in stance_by_answer.values() if stance == "competitive"
            ),
        }
        _apply_regulatory_risk_scope(
            projection,
            answer_count=len(stance_by_answer),
            answer_refs=[
                f"{run_by_answer[answer_id]}:{answer_id}"
                for answer_id in stance_by_answer
            ],
            platform_distribution=platform_distribution,
            stance_summary=stance_summary,
        )

    async def create_period_report(
        self,
        entity_id: UUID,
        *,
        period_type: str,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        center_term: str,
        created_by_user_id: UUID | None = None,
    ) -> dict[str, Any]:
        center_term = center_term.strip()
        if not center_term:
            raise ValueError("center_term 不能为空。")

        await self._lock_entity(entity_id)
        view = await self.get_period_view(
            entity_id,
            period_type=period_type,
            start_at=start_at,
            end_at=end_at,
            center_term=center_term,
        )
        if not _int(_dict(view.get("current_period")).get("run_count")):
            raise ValueError("当前周期没有可用采集轮次，无法生成报告。")
        if view.get("report_id"):
            return view

        current_summary = _dict(view.get("current_period"))
        previous_summary = _dict_or_none(view.get("previous_period"))
        current_projections = await self._run_projections(
            entity_id,
            _uuid_list(current_summary.get("run_ids")),
        )
        previous_projections = await self._run_projections(
            entity_id,
            _uuid_list((previous_summary or {}).get("run_ids")),
        )
        source_hash = _period_view_source_hash(
            period_type=period_type,
            current_summary=current_summary,
            previous_summary=previous_summary,
            current_projections=current_projections,
            previous_projections=previous_projections,
            center_term=center_term,
        )
        saved = await self._period_view_report(entity_id, source_hash)
        if saved:
            projection, report = saved
            view["projection"] = _normalize_period_projection(
                projection.association_circle_projection
            )
            await self._apply_regulatory_risk_scope(
                view["projection"],
                _uuid_list(current_summary.get("run_ids")),
            )
            _finalize_period_projection_quality(view["projection"])
            view["report_id"] = str(report.id)
            view["report_input"] = _period_report_input(
                current_summary,
                previous_summary,
                _list(view.get("change_top5")),
                bool(view.get("question_set_changed")),
                str(view.get("comparison_notice") or ""),
                view["projection"],
            )
            return view

        projection_body = _dict(view.get("projection"))
        artifact = _build_period_report_artifact(
            _projection_bodies(current_projections),
            projection_body,
            _dict(projection_body.get("sample_scope")),
            _dict(projection_body.get("tracking_projection")),
            entity_id=entity_id,
        )
        generated_projection = _period_projection_from_artifact(
            artifact,
            projection_body,
            current_summary,
            _dict(projection_body.get("tracking_projection")),
        )
        current_run_ids = _uuid_list(current_summary.get("run_ids"))
        previous_run_ids = _uuid_list((previous_summary or {}).get("run_ids"))
        await self._apply_regulatory_risk_scope(
            generated_projection,
            current_run_ids,
        )
        _finalize_period_projection_quality(generated_projection)
        _synchronize_report_artifact(artifact, generated_projection)
        report_quality_passed = bool(
            _dict(generated_projection.get("report_quality_checks")).get("passed")
            is True
        )
        generated_projection["report_delivery_status"] = (
            "ready" if report_quality_passed else "quality_failed"
        )
        generated_report_input = _period_report_input(
            current_summary,
            previous_summary,
            _list(view.get("change_top5")),
            bool(view.get("question_set_changed")),
            str(view.get("comparison_notice") or ""),
            generated_projection,
        )

        await self.db.execute(
            update(AmwayCircleProjection)
            .where(
                AmwayCircleProjection.entity_id == entity_id,
                AmwayCircleProjection.projection_scope == "period_view",
                AmwayCircleProjection.is_latest.is_(True),
            )
            .values(is_latest=False)
        )
        projection = AmwayCircleProjection(
            entity_id=entity_id,
            circle_run_id=None,
            base_run_id=previous_run_ids[0] if previous_run_ids else None,
            target_run_id=current_run_ids[0],
            as_of_run_id=current_run_ids[0],
            projection_scope="period_view",
            projection_version=PERIOD_VIEW_PROJECTION_VERSION,
            status="ready",
            is_latest=True,
            source_run_ids=[
                *current_summary.get("run_ids", []),
                *((previous_summary or {}).get("run_ids", [])),
            ],
            source_run_count=len(current_run_ids) + len(previous_run_ids),
            source_run_hash=source_hash,
            sample_scope=current_summary,
            association_circle_projection=generated_projection,
            report_input=generated_report_input,
            compare_summary={
                "previous_period": previous_summary,
                "change_top5": _list(view.get("change_top5")),
            },
            data_quality=_dict(artifact.get("report_quality_checks")),
        )
        self.db.add(projection)
        await self.db.flush()
        report = AmwayCircleReport(
            entity_id=entity_id,
            projection_id=projection.id,
            circle_run_id=None,
            report_scope="period_view",
            report_version=str(artifact.get("schema_version") or "v1"),
            title=str(artifact.get("title") or "品牌联想圈层周期报告"),
            status="ready" if report_quality_passed else "quality_failed",
            markdown_body=str(
                artifact.get("report_markdown") or artifact.get("full_markdown") or ""
            ),
            structured_body=artifact,
            source_report_input=_dict(artifact.get("report_input")),
            source_projection_hash=source_hash,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(report)
        await self.db.flush()
        generated_projection = {
            **generated_projection,
            "report_id": str(report.id),
        }
        projection.association_circle_projection = generated_projection
        view["projection"] = generated_projection
        view["report_input"] = generated_report_input
        view["report_id"] = str(report.id)
        return view

    async def _period_view_report(
        self,
        entity_id: UUID,
        source_hash: str,
    ) -> tuple[AmwayCircleProjection, AmwayCircleReport] | None:
        row = (
            await self.db.execute(
                select(AmwayCircleProjection, AmwayCircleReport)
                .join(
                    AmwayCircleReport,
                    AmwayCircleReport.projection_id == AmwayCircleProjection.id,
                )
                .where(
                    AmwayCircleProjection.entity_id == entity_id,
                    AmwayCircleProjection.projection_scope == "period_view",
                    AmwayCircleProjection.projection_version
                    == PERIOD_VIEW_PROJECTION_VERSION,
                    AmwayCircleProjection.source_run_hash == source_hash,
                    AmwayCircleProjection.status == "ready",
                    AmwayCircleReport.report_scope == "period_view",
                    AmwayCircleReport.status.in_(["ready", "quality_failed"]),
                )
                .order_by(desc(AmwayCircleReport.updated_at))
                .limit(1)
            )
        ).first()
        return (row[0], row[1]) if row else None

    async def persist_calibrated_run(
        self,
        brand_run: BrandIntelligenceRun,
        calibrated_state: dict[str, Any],
    ) -> AmwayCircleRun | None:
        calibration = _dict(calibrated_state.get("entity_calibration_result"))
        projection_body = _dict(
            calibrated_state.get("association_circle_projection")
        ) or _dict(calibration.get("association_circle_projection"))
        if not projection_body:
            return None
        artifact = _calibration_artifact(calibrated_state, calibration, projection_body)
        return await self._persist_tracking_run(
            brand_run=brand_run,
            state=calibrated_state,
            artifact=artifact,
            projection_body=projection_body,
            create_report=False,
        )

    async def persist_completed_run(
        self,
        brand_run: BrandIntelligenceRun,
        final_state: dict[str, Any],
    ) -> AmwayCircleRun | None:
        artifact = _dict(final_state.get("report"))
        dashboard = _dict(artifact.get("dashboard_projection"))
        projection_body = _dict(dashboard.get("association_circle_projection"))
        if (
            str(artifact.get("report_kind") or "").strip() != "brand_association_circle"
            or not projection_body
        ):
            return None
        return await self._persist_tracking_run(
            brand_run=brand_run,
            state=final_state,
            artifact=artifact,
            projection_body=projection_body,
            create_report=True,
            create_run_if_missing=False,
        )

    async def _persist_tracking_run(
        self,
        *,
        brand_run: BrandIntelligenceRun,
        state: dict[str, Any],
        artifact: dict[str, Any],
        projection_body: dict[str, Any],
        create_report: bool,
        create_run_if_missing: bool = True,
    ) -> AmwayCircleRun | None:
        entity = await self.db.get(Entity, brand_run.entity_id)
        if entity is None or not is_amway_association_entity(
            name=entity.name,
            domain=entity.domain,
            aliases=_entity_aliases(entity.aliases),
        ):
            return None

        await self._lock_entity(entity.id)
        circle_run = (
            (
                await self.db.execute(
                    select(AmwayCircleRun).where(
                        AmwayCircleRun.brand_intelligence_run_id == brand_run.id
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if circle_run is None and not create_run_if_missing:
            return None
        if circle_run is not None and create_report:
            projection = (
                (
                    await self.db.execute(
                        select(AmwayCircleProjection)
                        .where(
                            AmwayCircleProjection.circle_run_id == circle_run.id,
                            AmwayCircleProjection.projection_scope == "run",
                        )
                        .order_by(desc(AmwayCircleProjection.built_at))
                        .limit(1)
                    )
                )
                .scalars()
                .first()
            )
            if projection is None:
                return None
            await self._upsert_run_report(
                brand_run=brand_run,
                circle_run=circle_run,
                projection=projection,
                artifact=artifact,
                calibrated=(
                    circle_run.status == "completed"
                    and circle_run.include_in_cumulative
                ),
            )
            await self.db.flush()
            return circle_run

        input_scope = _dict(brand_run.input_scope)
        sample_scope = _dict(artifact.get("sample_scope")) or _dict(
            projection_body.get("sample_scope")
        )
        center_terms = _string_list(
            artifact.get("center_terms") or projection_body.get("center_terms")
        ) or [entity.name]
        requested_platforms = _string_list(input_scope.get("platforms"))
        completed_platforms = _completed_platforms(
            artifact.get("platform_source_summary"), requested_platforms
        )
        question_bank = _list(
            artifact.get("question_bank")
        ) or _question_bank_from_state(state)
        question_set_id = await self._scoped_question_set_id(
            input_scope.get("uploaded_question_set_id"), entity.id
        )
        extraction_result = _dict(state.get("entity_extraction_result"))
        calibration_result = _dict(state.get("entity_calibration_result"))
        artifact_calibration = _dict(artifact.get("entity_calibration_result"))
        calibrated = str(
            projection_body.get("generated_from") or ""
        ) == "entity_calibration" or bool(calibration_result)
        ontology = load_default_amway_entity_ontology().definition
        ontology_version = str(
            calibration_result.get("ontology_version")
            or extraction_result.get("ontology_version")
            or artifact_calibration.get("ontology_version")
            or ontology.version
        )
        completed_at = _datetime_or_now(
            artifact.get("updated_at") or calibration_result.get("generated_at")
        )
        question_count = _int(sample_scope.get("question_count"))
        expected_answer_count = question_count * len(requested_platforms)
        valid_answer_count = _int(sample_scope.get("valid_answer_count"))
        failed_answer_count = _int(sample_scope.get("failed_answer_count"))
        collection_status = _collection_status(
            calibrated=calibrated,
            expected_answer_count=expected_answer_count,
            valid_answer_count=valid_answer_count,
        )
        collection_coverage = {
            "status": collection_status,
            "expected_answer_count": expected_answer_count,
            "valid_answer_count": valid_answer_count,
            "failed_answer_count": failed_answer_count,
            "coverage_ratio": _coverage_ratio(
                valid_answer_count,
                expected_answer_count,
            ),
        }
        include_in_cumulative = calibrated and collection_status != "failed"
        excluded_reason = None
        if not calibrated:
            excluded_reason = "missing_entity_calibration"
        elif collection_status == "failed":
            excluded_reason = "no_valid_answers"
        sequence = (
            circle_run.run_sequence
            if circle_run
            else await self._next_sequence(entity.id)
        )
        values = {
            "question_set_id": question_set_id,
            "status": collection_status,
            "center_term": center_terms[0],
            "center_terms": center_terms,
            "platforms_requested": requested_platforms,
            "platforms_completed": completed_platforms,
            "question_count": question_count,
            "valid_answer_count": valid_answer_count,
            "failed_answer_count": failed_answer_count,
            "answer_scope": {
                "question_definition": _dict(artifact.get("question_definition")),
                "platform_source_summary": _dict(
                    artifact.get("platform_source_summary")
                ),
                "collection_coverage": collection_coverage,
            },
            "question_signature": _question_signature(question_bank),
            "lexicon_version": ontology_version,
            "lexicon_hash": _payload_hash(ontology.model_dump(mode="json")),
            "extraction_version": str(
                extraction_result.get("schema_version") or EXTRACTION_SCHEMA_VERSION
            ),
            "calibration_version": str(
                calibration_result.get("schema_version")
                or artifact_calibration.get("schema_version")
                or CALIBRATION_SCHEMA_VERSION
            ),
            "projection_version": str(artifact.get("schema_version") or "v1"),
            "include_in_cumulative": include_in_cumulative,
            "excluded_reason": excluded_reason,
            "completed_at": completed_at,
        }
        if circle_run is None:
            circle_run = AmwayCircleRun(
                entity_id=entity.id,
                organization_id=entity.organization_id,
                created_by_user_id=brand_run.created_by_user_id,
                brand_intelligence_run_id=brand_run.id,
                analysis_task_id=brand_run.analysis_task_id,
                run_sequence=sequence,
                run_label=str(
                    input_scope.get("uploaded_question_source")
                    or input_scope.get("question_set_version")
                    or f"第 {sequence} 轮"
                ),
                expected_answer_count=expected_answer_count,
                started_at=brand_run.started_at or brand_run.created_at,
                **values,
            )
            self.db.add(circle_run)
            await self.db.flush()
        else:
            for key, value in values.items():
                setattr(circle_run, key, value)
            circle_run.expected_answer_count = expected_answer_count

        await self._persist_run_snapshots(
            circle_run=circle_run,
            state=state,
            artifact=artifact,
            projection_body=projection_body,
        )
        projection = await self._upsert_run_projection(
            circle_run=circle_run,
            artifact=artifact,
            projection_body=projection_body,
            sample_scope=sample_scope,
            completed_at=completed_at,
            calibrated=calibrated,
        )
        if create_report:
            report = await self._upsert_run_report(
                brand_run=brand_run,
                circle_run=circle_run,
                projection=projection,
                artifact=artifact,
                calibrated=calibrated,
            )
            projection.association_circle_projection = {
                **projection_body,
                "report_id": str(report.id),
            }
        await self.db.flush()
        return circle_run

    async def _lock_entity(self, entity_id: UUID) -> None:
        if self.db.get_bind().dialect.name != "postgresql":
            return
        await self.db.execute(
            text(
                "SELECT pg_advisory_xact_lock("
                "hashtext('amway_circle'), hashtext(:entity_id))"
            ),
            {"entity_id": str(entity_id)},
        )

    async def _scoped_question_set_id(self, value: Any, entity_id: UUID) -> UUID | None:
        question_set_id = _uuid_or_none(value)
        if question_set_id is None:
            return None
        return await self.db.scalar(
            select(MonitoringQuestionSet.id).where(
                MonitoringQuestionSet.id == question_set_id,
                MonitoringQuestionSet.entity_id == entity_id,
            )
        )

    async def _next_sequence(self, entity_id: UUID) -> int:
        current = await self.db.scalar(
            select(func.max(AmwayCircleRun.run_sequence)).where(
                AmwayCircleRun.entity_id == entity_id
            )
        )
        return int(current or 0) + 1

    async def _upsert_run_projection(
        self,
        *,
        circle_run: AmwayCircleRun,
        artifact: dict[str, Any],
        projection_body: dict[str, Any],
        sample_scope: dict[str, Any],
        completed_at: datetime,
        calibrated: bool,
    ) -> AmwayCircleProjection:
        projection = (
            (
                await self.db.execute(
                    select(AmwayCircleProjection)
                    .where(
                        AmwayCircleProjection.circle_run_id == circle_run.id,
                        AmwayCircleProjection.projection_scope == "run",
                    )
                    .order_by(desc(AmwayCircleProjection.built_at))
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        await self.db.execute(
            update(AmwayCircleProjection)
            .where(
                AmwayCircleProjection.entity_id == circle_run.entity_id,
                AmwayCircleProjection.projection_scope == "run",
                AmwayCircleProjection.is_latest.is_(True),
            )
            .values(is_latest=False)
        )
        source_hash = hashlib.sha256(str(circle_run.id).encode("utf-8")).hexdigest()
        values = {
            "as_of_run_id": circle_run.id,
            "projection_version": str(artifact.get("schema_version") or "v1"),
            "status": "ready" if calibrated else "partial",
            "is_latest": True,
            "source_run_ids": [str(circle_run.id)],
            "source_run_count": 1,
            "source_run_hash": source_hash,
            "sample_scope": sample_scope,
            "association_circle_projection": projection_body,
            "report_input": _dict(artifact.get("report_input")),
            "data_quality": _dict(artifact.get("report_quality_checks")),
            "built_at": completed_at,
        }
        if projection is None:
            projection = AmwayCircleProjection(
                entity_id=circle_run.entity_id,
                circle_run_id=circle_run.id,
                projection_scope="run",
                **values,
            )
            self.db.add(projection)
        else:
            for key, value in values.items():
                setattr(projection, key, value)
        await self.db.flush()
        return projection

    async def _upsert_run_report(
        self,
        *,
        brand_run: BrandIntelligenceRun,
        circle_run: AmwayCircleRun,
        projection: AmwayCircleProjection,
        artifact: dict[str, Any],
        calibrated: bool,
    ) -> AmwayCircleReport:
        report = (
            (
                await self.db.execute(
                    select(AmwayCircleReport)
                    .where(
                        AmwayCircleReport.circle_run_id == circle_run.id,
                        AmwayCircleReport.report_scope == "run",
                    )
                    .order_by(desc(AmwayCircleReport.updated_at))
                    .limit(1)
                )
            )
            .scalars()
            .first()
        )
        values = {
            "projection_id": projection.id,
            "report_version": str(artifact.get("schema_version") or "v1"),
            "title": str(artifact.get("title") or "品牌联想圈层报告"),
            "status": "ready" if calibrated else "partial",
            "markdown_body": str(
                artifact.get("report_markdown") or artifact.get("full_markdown") or ""
            ),
            "structured_body": artifact,
            "source_report_input": _dict(artifact.get("report_input")),
            "source_projection_hash": projection.source_run_hash,
        }
        if report is None:
            report = AmwayCircleReport(
                entity_id=circle_run.entity_id,
                circle_run_id=circle_run.id,
                report_scope="run",
                created_by_user_id=brand_run.created_by_user_id,
                **values,
            )
            self.db.add(report)
        else:
            for key, value in values.items():
                setattr(report, key, value)
        await self.db.flush()
        return report

    async def persist_completed_run_from_snapshot(
        self,
        brand_run: BrandIntelligenceRun,
        snapshot_id: UUID | None,
    ) -> AmwayCircleRun | None:
        if snapshot_id is None:
            return None
        snapshot = await self.db.get(AnalysisSnapshot, snapshot_id)
        if snapshot is None or snapshot.entity_id != brand_run.entity_id:
            return None
        raw_data = _dict(snapshot.raw_data)
        report = _dict(raw_data.get("report_data"))
        if not report:
            return None
        dashboard = _dict(report.get("dashboard_projection"))
        projection_body = _dict(dashboard.get("association_circle_projection"))
        if (
            str(report.get("report_kind") or "").strip() != "brand_association_circle"
            or not projection_body
        ):
            return None
        source_appendix = _list(raw_data.get("source_appendix")) or _list(
            report.get("source_appendix")
        )
        if source_appendix and not report.get("source_appendix"):
            report = {**report, "source_appendix": source_appendix}
        fetch_results = _list(raw_data.get("fetch_results"))
        if not fetch_results:
            fetch_results = _list(raw_data.get("fetch_results_summary"))
        if not fetch_results:
            fetch_results = _fetch_results_from_source_appendix(source_appendix)
        extraction_result = _dict(raw_data.get("entity_extraction_result"))
        state = {
            "report": report,
            "fetch_results": fetch_results,
            "entity_extraction_result": extraction_result,
            "entity_calibration_result": _dict(
                raw_data.get("entity_calibration_result")
            )
            or _dict(report.get("entity_calibration_result")),
        }
        await self._lock_entity(brand_run.entity_id)
        existing_run_id = await self.db.scalar(
            select(AmwayCircleRun.id).where(
                AmwayCircleRun.brand_intelligence_run_id == brand_run.id
            )
        )
        circle_run = await self._persist_tracking_run(
            brand_run=brand_run,
            state=state,
            artifact=report,
            projection_body=projection_body,
            create_report=True,
        )
        if circle_run is None:
            return None
        if existing_run_id is not None:
            return circle_run
        expected = _snapshot_expected_counts(
            state=state,
            artifact=report,
            projection_body=projection_body,
            center_terms=_string_list(circle_run.center_terms),
        )
        manifest = await self._snapshot_integrity_manifest(circle_run.id, expected)
        incomplete = [
            category
            for category, item in manifest.items()
            if item["declared"] and not item["complete"]
        ]
        if not extraction_result and _has_peripheral_nodes(projection_body):
            manifest["mentions"]["required_by_graph"] = True
            manifest["mentions"]["complete"] = False
            incomplete.append("mentions")
        circle_run.answer_scope = {
            **_dict(circle_run.answer_scope),
            "snapshot_integrity": manifest,
        }
        if incomplete:
            if circle_run.status != "failed":
                circle_run.status = "partial"
            circle_run.include_in_cumulative = False
            circle_run.excluded_reason = "incomplete_snapshot:" + ",".join(
                _unique_strings(incomplete)
            )
            await self.db.execute(
                update(AmwayCircleProjection)
                .where(AmwayCircleProjection.circle_run_id == circle_run.id)
                .values(status="partial")
            )
            await self.db.execute(
                update(AmwayCircleReport)
                .where(AmwayCircleReport.circle_run_id == circle_run.id)
                .values(status="partial")
            )
        await self.db.flush()
        return circle_run

    async def _snapshot_integrity_manifest(
        self,
        circle_run_id: UUID,
        expected: dict[str, int | None],
    ) -> dict[str, dict[str, Any]]:
        models = {
            "answers": AmwayCircleAnswer,
            "mentions": AmwayCircleEntityMention,
            "evidence": AmwayCircleEvidence,
            "nodes": AmwayCircleNodeSnapshot,
            "edges": AmwayCircleEdgeSnapshot,
        }
        manifest: dict[str, dict[str, Any]] = {}
        for category, model in models.items():
            expected_count = expected.get(category)
            actual_count = _int(
                await self.db.scalar(
                    select(func.count(model.id)).where(
                        model.circle_run_id == circle_run_id
                    )
                )
            )
            manifest[category] = {
                "declared": expected_count is not None,
                "expected": expected_count or 0,
                "actual": actual_count,
                "complete": (expected_count is None or actual_count >= expected_count),
            }
        return manifest

    async def _persist_run_snapshots(
        self,
        *,
        circle_run: AmwayCircleRun,
        state: dict[str, Any],
        artifact: dict[str, Any],
        projection_body: dict[str, Any],
    ) -> None:
        answer_rows = await self._persist_answers(
            circle_run,
            _answer_records(
                fetch_results=_list(state.get("fetch_results")),
                source_appendix=_list(artifact.get("source_appendix"))
                or _list(projection_body.get("source_appendix")),
                center_terms=_string_list(circle_run.center_terms),
            ),
        )
        mention_rows = await self._persist_mentions(
            circle_run,
            answer_rows,
            _dict(state.get("entity_extraction_result")),
        )
        await self._persist_evidence(
            circle_run,
            answer_rows,
            mention_rows,
            _evidence_records(artifact, projection_body),
        )
        await self._persist_node_edge_snapshots(circle_run, projection_body)

    async def _persist_answers(
        self,
        circle_run: AmwayCircleRun,
        items: list[dict[str, Any]],
    ) -> dict[tuple[str, str], AmwayCircleAnswer]:
        existing = (
            (
                await self.db.execute(
                    select(AmwayCircleAnswer).where(
                        AmwayCircleAnswer.circle_run_id == circle_run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        rows = {(row.question_id, row.platform): row for row in existing}
        for item in items:
            key = (item["question_id"], item["platform"])
            if key in rows:
                continue
            row = AmwayCircleAnswer(
                circle_run_id=circle_run.id,
                entity_id=circle_run.entity_id,
                question_set_id=circle_run.question_set_id,
                center_context_type="answer" if item["mentions_center"] else "none",
                **item,
            )
            self.db.add(row)
            rows[key] = row
        if items:
            await self.db.flush()
        return rows

    async def _persist_mentions(
        self,
        circle_run: AmwayCircleRun,
        answer_rows: dict[tuple[str, str], AmwayCircleAnswer],
        extraction_result: dict[str, Any],
    ) -> dict[tuple[UUID, str], AmwayCircleEntityMention]:
        existing = (
            (
                await self.db.execute(
                    select(AmwayCircleEntityMention).where(
                        AmwayCircleEntityMention.circle_run_id == circle_run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        dedupe_keys = {row.dedupe_key for row in existing}
        rows = {
            (row.answer_id, str(row.lexicon_entity_id or "")): row for row in existing
        }
        for signal in _list(extraction_result.get("signals")):
            if not isinstance(signal, dict):
                continue
            answer = answer_rows.get(
                (
                    str(signal.get("question_id") or "").strip(),
                    _normalize_platform_name(signal.get("platform")),
                )
            )
            if answer is None:
                continue
            values = _mention_values(signal, extraction_result)
            if values["dedupe_key"] in dedupe_keys:
                continue
            row = AmwayCircleEntityMention(
                circle_run_id=circle_run.id,
                answer_id=answer.id,
                entity_id=circle_run.entity_id,
                **values,
            )
            self.db.add(row)
            dedupe_keys.add(row.dedupe_key)
            rows[(answer.id, str(row.lexicon_entity_id or ""))] = row
        if extraction_result.get("signals"):
            await self.db.flush()
        return rows

    async def _persist_evidence(
        self,
        circle_run: AmwayCircleRun,
        answer_rows: dict[tuple[str, str], AmwayCircleAnswer],
        mention_rows: dict[tuple[UUID, str], AmwayCircleEntityMention],
        items: list[dict[str, Any]],
    ) -> None:
        existing_refs = set(
            (
                await self.db.execute(
                    select(AmwayCircleEvidence.evidence_ref).where(
                        AmwayCircleEvidence.circle_run_id == circle_run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for source_rank, item in enumerate(items, start=1):
            if item["evidence_ref"] in existing_refs:
                continue
            key = (item["question_id"], item["platform"])
            answer = answer_rows.get(key)
            if answer is None:
                fallback = _fallback_answer_record(item, circle_run.center_terms)
                answer = AmwayCircleAnswer(
                    circle_run_id=circle_run.id,
                    entity_id=circle_run.entity_id,
                    question_set_id=circle_run.question_set_id,
                    center_context_type=(
                        "answer" if fallback["mentions_center"] else "none"
                    ),
                    **fallback,
                )
                self.db.add(answer)
                await self.db.flush()
                answer_rows[key] = answer
            mention = mention_rows.get(
                (answer.id, str(item.get("lexicon_entity_id") or ""))
            )
            self.db.add(
                AmwayCircleEvidence(
                    circle_run_id=circle_run.id,
                    answer_id=answer.id,
                    mention_id=mention.id if mention else None,
                    evidence_ref=item["evidence_ref"],
                    platform=item["platform"],
                    question_id=item["question_id"],
                    question_text=item["question_text"],
                    quote_text=item["quote_text"],
                    quote_type=item["quote_type"],
                    entity_names=item["entity_names"],
                    strategy_terms=item["strategy_terms"],
                    scenario_tags=item["scenario_tags"],
                    source_rank=source_rank,
                )
            )
            existing_refs.add(item["evidence_ref"])
        if items:
            await self.db.flush()

    async def _persist_node_edge_snapshots(
        self,
        circle_run: AmwayCircleRun,
        projection_body: dict[str, Any],
    ) -> None:
        existing_node_ids = set(
            (
                await self.db.execute(
                    select(AmwayCircleNodeSnapshot.node_id).where(
                        AmwayCircleNodeSnapshot.circle_run_id == circle_run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for raw_node in _list(projection_body.get("nodes")):
            if not isinstance(raw_node, dict):
                continue
            node = _normalize_tracking_node(raw_node)
            node_id = str(node.get("node_id") or "")
            if not node_id or node_id in existing_node_ids:
                continue
            self.db.add(
                AmwayCircleNodeSnapshot(
                    circle_run_id=circle_run.id,
                    entity_id=circle_run.entity_id,
                    **_node_snapshot_values(node),
                )
            )
            existing_node_ids.add(node_id)
        await self.db.flush()

        existing_edge_ids = set(
            (
                await self.db.execute(
                    select(AmwayCircleEdgeSnapshot.edge_id).where(
                        AmwayCircleEdgeSnapshot.circle_run_id == circle_run.id
                    )
                )
            )
            .scalars()
            .all()
        )
        for raw_edge in _list(projection_body.get("edges")):
            if not isinstance(raw_edge, dict):
                continue
            values = _edge_snapshot_values(raw_edge)
            if (
                not values["edge_id"]
                or values["edge_id"] in existing_edge_ids
                or values["source_node_id"] not in existing_node_ids
                or values["target_node_id"] not in existing_node_ids
            ):
                continue
            self.db.add(AmwayCircleEdgeSnapshot(circle_run_id=circle_run.id, **values))
            existing_edge_ids.add(values["edge_id"])
        await self.db.flush()

    async def get_node_insight(
        self,
        entity_id: UUID,
        *,
        projection_id: UUID,
        node_id: str,
    ) -> dict[str, Any] | None:
        projection = (
            (
                await self.db.execute(
                    select(AmwayCircleProjection).where(
                        AmwayCircleProjection.id == projection_id,
                        AmwayCircleProjection.entity_id == entity_id,
                    )
                )
            )
            .scalars()
            .one_or_none()
        )
        if projection is None:
            return None

        projection_body = _dict(projection.association_circle_projection)
        node = _find_node(projection_body.get("nodes"), node_id)
        if node is None:
            return None

        evidence_refs = _string_list(node.get("evidence_refs"))
        run_ids = _uuid_list(projection.source_run_ids)
        if not run_ids:
            run_ids = _projection_fallback_run_ids(projection)
        quotes = await self._evidence_quotes(entity_id, evidence_refs, run_ids)
        return {
            "node_id": str(node.get("node_id") or node_id),
            "title": str(
                node.get("display_name") or node.get("canonical_name") or node_id
            ),
            "role_label": _track_label(str(node.get("track") or "")),
            "relationship_to_center": _relationship_summary(node),
            "brand_meaning": str(node.get("track_reason") or ""),
            "evidence_summary": {
                "question_count": int(node.get("question_count") or 0),
                "answer_count": int(node.get("mention_answer_count") or 0),
                "platform_count": int(node.get("platform_count") or 0),
                "top_platforms": _top_platforms(node.get("platform_summary")),
            },
            "representative_quotes": quotes,
            "next_action": _next_action(node),
        }

    async def _latest_completed_run(
        self,
        entity_id: UUID,
        *,
        center_term: str | None = None,
    ) -> AmwayCircleRun | None:
        query = _eligible_run_query(entity_id, center_term=center_term)
        row = (
            (
                await self.db.execute(
                    query.order_by(
                        desc(AmwayCircleRun.completed_at),
                        desc(AmwayCircleRun.created_at),
                        desc(AmwayCircleRun.run_sequence),
                    ).limit(1)
                )
            )
            .scalars()
            .first()
        )
        return row

    async def _previous_completed_run(
        self,
        entity_id: UUID,
        latest: AmwayCircleRun,
        *,
        center_term: str | None = None,
    ) -> AmwayCircleRun | None:
        completed_at = latest.completed_at or latest.created_at
        query = _eligible_run_query(entity_id, center_term=center_term).where(
            AmwayCircleRun.id != latest.id,
            or_(
                AmwayCircleRun.completed_at < completed_at,
                and_(
                    AmwayCircleRun.completed_at == completed_at,
                    or_(
                        AmwayCircleRun.created_at < latest.created_at,
                        and_(
                            AmwayCircleRun.created_at == latest.created_at,
                            AmwayCircleRun.run_sequence < latest.run_sequence,
                        ),
                    ),
                ),
            ),
        )
        row = (
            (
                await self.db.execute(
                    query.order_by(
                        desc(AmwayCircleRun.completed_at),
                        desc(AmwayCircleRun.created_at),
                        desc(AmwayCircleRun.run_sequence),
                    ).limit(1)
                )
            )
            .scalars()
            .first()
        )
        return row

    async def _completed_runs_between(
        self,
        entity_id: UUID,
        start_at: datetime,
        end_at: datetime,
        *,
        center_term: str | None = None,
        include_end: bool,
    ) -> list[AmwayCircleRun]:
        end_filter = (
            AmwayCircleRun.completed_at <= end_at
            if include_end
            else AmwayCircleRun.completed_at < end_at
        )
        rows = (
            (
                await self.db.execute(
                    _eligible_run_query(entity_id, center_term=center_term)
                    .where(AmwayCircleRun.completed_at >= start_at, end_filter)
                    .order_by(
                        desc(AmwayCircleRun.completed_at),
                        desc(AmwayCircleRun.created_at),
                        desc(AmwayCircleRun.run_sequence),
                    )
                )
            )
            .scalars()
            .all()
        )
        return list(rows)

    async def _run_projections(
        self,
        entity_id: UUID,
        run_ids: list[UUID],
    ) -> list[AmwayCircleProjection]:
        if not run_ids:
            return []
        rows = (
            (
                await self.db.execute(
                    select(AmwayCircleProjection)
                    .where(
                        AmwayCircleProjection.entity_id == entity_id,
                        AmwayCircleProjection.circle_run_id.in_(run_ids),
                        AmwayCircleProjection.projection_scope == "run",
                        AmwayCircleProjection.status == "ready",
                    )
                    .order_by(
                        AmwayCircleProjection.circle_run_id,
                        desc(AmwayCircleProjection.built_at),
                        desc(AmwayCircleProjection.id),
                    )
                )
            )
            .scalars()
            .all()
        )
        latest_by_run: dict[UUID, AmwayCircleProjection] = {}
        for row in rows:
            if row.circle_run_id and row.circle_run_id not in latest_by_run:
                latest_by_run[row.circle_run_id] = row
        return [latest_by_run[run_id] for run_id in run_ids if run_id in latest_by_run]

    @staticmethod
    def _run_summary(
        row: AmwayCircleRun,
        latest_projection_id: str | None,
        latest_report_id: str | None,
    ) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "entity_id": str(row.entity_id),
            "run_sequence": row.run_sequence,
            "run_label": row.run_label,
            "status": row.status,
            "center_term": row.center_term,
            "platforms_requested": _list(row.platforms_requested),
            "platforms_completed": _list(row.platforms_completed),
            "question_count": row.question_count,
            "expected_answer_count": row.expected_answer_count,
            "valid_answer_count": row.valid_answer_count,
            "failed_answer_count": row.failed_answer_count,
            "include_in_cumulative": row.include_in_cumulative,
            "started_at": _iso(row.started_at),
            "completed_at": _iso(row.completed_at),
            "created_at": _iso(row.created_at),
            "latest_projection_id": latest_projection_id,
            "latest_report_id": latest_report_id,
        }

    async def _latest_projection_ids(self, run_ids: list[UUID]) -> dict[UUID, str]:
        if not run_ids:
            return {}
        rows = (
            await self.db.execute(
                select(
                    AmwayCircleProjection.circle_run_id,
                    AmwayCircleProjection.id,
                )
                .where(
                    AmwayCircleProjection.circle_run_id.in_(run_ids),
                    AmwayCircleProjection.projection_scope == "run",
                    AmwayCircleProjection.status == "ready",
                )
                .order_by(
                    AmwayCircleProjection.circle_run_id,
                    desc(AmwayCircleProjection.built_at),
                    desc(AmwayCircleProjection.id),
                )
            )
        ).all()
        latest: dict[UUID, str] = {}
        for circle_run_id, projection_id in rows:
            latest.setdefault(circle_run_id, str(projection_id))
        return latest

    async def _run_count(self, entity_id: UUID) -> int:
        row = (
            await self.db.execute(
                select(func.count())
                .select_from(AmwayCircleRun)
                .where(AmwayCircleRun.entity_id == entity_id)
            )
        ).scalar_one()
        return int(row or 0)

    async def _latest_report_ids(self, run_ids: list[UUID]) -> dict[UUID, str]:
        if not run_ids:
            return {}
        rows = (
            await self.db.execute(
                select(AmwayCircleReport.circle_run_id, AmwayCircleReport.id)
                .join(
                    AmwayCircleProjection,
                    and_(
                        AmwayCircleProjection.id == AmwayCircleReport.projection_id,
                        AmwayCircleProjection.entity_id == AmwayCircleReport.entity_id,
                        AmwayCircleProjection.circle_run_id
                        == AmwayCircleReport.circle_run_id,
                    ),
                )
                .where(
                    AmwayCircleReport.circle_run_id.in_(run_ids),
                    AmwayCircleReport.report_scope == "run",
                    AmwayCircleReport.status == "ready",
                    AmwayCircleProjection.projection_scope == "run",
                    AmwayCircleProjection.status == "ready",
                )
                .order_by(
                    AmwayCircleReport.circle_run_id,
                    desc(AmwayCircleReport.updated_at),
                    desc(AmwayCircleReport.id),
                )
            )
        ).all()
        latest: dict[UUID, str] = {}
        for circle_run_id, report_id in rows:
            latest.setdefault(circle_run_id, str(report_id))
        return latest

    async def _evidence_quotes(
        self,
        entity_id: UUID,
        evidence_refs: list[str],
        run_ids: list[UUID],
    ) -> list[dict[str, Any]]:
        evidence_keys = _evidence_keys(evidence_refs, run_ids)
        if not evidence_keys:
            return []
        query_run_ids = list({run_id for run_id, _ in evidence_keys})
        query_refs = list({evidence_ref for _, evidence_ref in evidence_keys})
        allowed = set(evidence_keys)
        rows = (
            await self.db.execute(
                select(AmwayCircleEvidence, AmwayCircleAnswer)
                .join(
                    AmwayCircleAnswer,
                    and_(
                        AmwayCircleAnswer.id == AmwayCircleEvidence.answer_id,
                        AmwayCircleAnswer.circle_run_id
                        == AmwayCircleEvidence.circle_run_id,
                    ),
                )
                .where(
                    AmwayCircleAnswer.entity_id == entity_id,
                    AmwayCircleEvidence.circle_run_id.in_(query_run_ids),
                    AmwayCircleEvidence.evidence_ref.in_(query_refs),
                )
                .order_by(
                    AmwayCircleEvidence.circle_run_id,
                    AmwayCircleEvidence.source_rank,
                )
            )
        ).all()
        rank = {key: idx for idx, key in enumerate(evidence_keys)}
        scoped_rows = [
            (evidence, answer)
            for evidence, answer in rows
            if (evidence.circle_run_id, evidence.evidence_ref) in allowed
        ]
        ordered = sorted(
            scoped_rows,
            key=lambda item: (
                rank.get((item[0].circle_run_id, item[0].evidence_ref), 9999),
                item[0].source_rank,
            ),
        )[:8]
        return [
            {
                "circle_run_id": str(evidence.circle_run_id),
                "evidence_ref": evidence.evidence_ref,
                "platform": evidence.platform,
                "platform_model": answer.platform_model,
                "fetch_agent_version": answer.fetch_agent_version,
                "question_id": evidence.question_id,
                "question_hash": answer.question_hash,
                "question_text": evidence.question_text,
                "quote_text": evidence.quote_text,
                "quote_type": evidence.quote_type,
                "entity_names": _string_list(evidence.entity_names),
                "strategy_terms": _string_list(evidence.strategy_terms),
            }
            for evidence, answer in ordered
        ]

    @staticmethod
    def _projection_payload(row: AmwayCircleProjection) -> dict[str, Any]:
        return {
            "id": str(row.id),
            "entity_id": str(row.entity_id),
            "projection_scope": row.projection_scope,
            "circle_run_id": str(row.circle_run_id) if row.circle_run_id else None,
            "base_run_id": str(row.base_run_id) if row.base_run_id else None,
            "target_run_id": str(row.target_run_id) if row.target_run_id else None,
            "as_of_run_id": str(row.as_of_run_id) if row.as_of_run_id else None,
            "projection_version": row.projection_version,
            "status": row.status,
            "source_run_ids": _string_list(row.source_run_ids),
            "source_run_count": row.source_run_count,
            "source_run_hash": row.source_run_hash,
            "sample_scope": _dict(row.sample_scope),
            "association_circle_projection": _dict(row.association_circle_projection),
            "compare_summary": _dict_or_none(row.compare_summary),
            "data_quality": _dict(row.data_quality),
            "built_at": _iso(row.built_at),
        }


def _calibration_artifact(
    state: dict[str, Any],
    calibration: dict[str, Any],
    projection: dict[str, Any],
) -> dict[str, Any]:
    report_input = _dict(calibration.get("report_input")) or _dict(
        state.get("brand_association_report_input")
    )
    return {
        "schema_version": str(calibration.get("schema_version") or "v1"),
        "updated_at": calibration.get("generated_at"),
        "center_terms": _string_list(projection.get("center_terms")),
        "sample_scope": _dict(calibration.get("sample_scope"))
        or _dict(projection.get("sample_scope")),
        "question_bank": _list(projection.get("question_bank")),
        "question_definition": _dict(report_input.get("question_scope")),
        "platform_source_summary": _dict(calibration.get("platform_summary"))
        or _dict(projection.get("platform_source_summary")),
        "report_input": report_input,
        "report_quality_checks": {},
        "source_appendix": _list(projection.get("source_appendix")),
        "entity_calibration_result": calibration,
    }


def _question_bank_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(_list(state.get("fetch_results")), start=1):
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "id": str(item.get("question_id") or item.get("id") or index),
                "text": str(item.get("question_text") or item.get("question") or ""),
            }
        )
    return rows


def _snapshot_expected_counts(
    *,
    state: dict[str, Any],
    artifact: dict[str, Any],
    projection_body: dict[str, Any],
    center_terms: list[str],
) -> dict[str, int | None]:
    source_appendix = _list(artifact.get("source_appendix")) or _list(
        projection_body.get("source_appendix")
    )
    answers = _answer_records(
        fetch_results=_list(state.get("fetch_results")),
        source_appendix=source_appendix,
        center_terms=center_terms,
    )
    extraction_result = _dict(state.get("entity_extraction_result"))
    mention_keys = {
        _mention_values(signal, extraction_result)["dedupe_key"]
        for signal in _list(extraction_result.get("signals"))
        if isinstance(signal, dict)
    }
    evidence_refs = {
        item["evidence_ref"] for item in _evidence_records(artifact, projection_body)
    }
    node_ids = {
        str(_normalize_tracking_node(node).get("node_id") or "")
        for node in _list(projection_body.get("nodes"))
        if isinstance(node, dict)
    }
    edge_ids = {
        _edge_snapshot_values(edge)["edge_id"]
        for edge in _list(projection_body.get("edges"))
        if isinstance(edge, dict)
    }
    counts = {
        "answers": len(answers),
        "mentions": len(mention_keys),
        "evidence": len(evidence_refs),
        "nodes": len(node_ids - {""}),
        "edges": len(edge_ids - {""}),
    }
    return {category: count or None for category, count in counts.items()}


def _has_peripheral_nodes(projection_body: dict[str, Any]) -> bool:
    center_terms = {
        value.casefold() for value in _string_list(projection_body.get("center_terms"))
    }
    for raw_node in _list(projection_body.get("nodes")):
        if not isinstance(raw_node, dict) or raw_node.get("is_center") is True:
            continue
        role = str(raw_node.get("node_role") or raw_node.get("role") or "").lower()
        if role == "center":
            continue
        node = _normalize_tracking_node(raw_node)
        if _node_name(node).casefold() not in center_terms:
            return True
    return False


def _payload_hash(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _entity_aliases(value: Any) -> list[Any]:
    if not value:
        return []
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        parsed = [value]
    return list(parsed) if isinstance(parsed, (list, tuple, set)) else [parsed]


def _mention_values(
    signal: dict[str, Any], extraction_result: dict[str, Any]
) -> dict[str, Any]:
    lexicon_entity_id = str(
        signal.get("lexicon_entity_id") or signal.get("entity_id") or ""
    ).strip()
    matched_text = str(signal.get("matched_text") or "").strip()
    context_text = str(
        signal.get("center_context_excerpt") or signal.get("evidence_text") or ""
    ).strip()
    return {
        "lexicon_entity_id": lexicon_entity_id or None,
        "canonical_name": str(
            signal.get("canonical_name") or signal.get("entity_name") or matched_text
        ).strip(),
        "entity_type": str(signal.get("entity_type") or "").strip(),
        "source_type": str(signal.get("source_type") or "lexicon").strip(),
        "matched_text": matched_text,
        "matched_alias": (
            matched_text if signal.get("match_source") == "alias" else None
        ),
        "context_text": context_text,
        "evidence_text": str(signal.get("evidence_text") or context_text).strip(),
        "relation_type": str(signal.get("relation_type") or "").strip(),
        "amway_anchor": _mention_anchor(signal),
        "sentiment_context": str(
            signal.get("sentiment_context")
            or signal.get("context_polarity")
            or "neutral"
        ).strip(),
        "risk_context": str(
            signal.get("risk_context") or signal.get("risk_attribution") or ""
        ).strip()
        or None,
        "confidence_score": _float(signal.get("confidence_score") or 1.0),
        "extractor_version": str(
            extraction_result.get("schema_version") or EXTRACTION_SCHEMA_VERSION
        ),
        "dedupe_key": _payload_hash(
            [
                signal.get("answer_id"),
                signal.get("question_id"),
                signal.get("platform"),
                lexicon_entity_id,
                matched_text,
            ]
        ),
    }


def _mention_anchor(signal: dict[str, Any]) -> str:
    if signal.get("answer_mentions_center") and signal.get("near_center_context"):
        return "direct"
    if signal.get("near_center_context"):
        return "nearby"
    if signal.get("question_mentions_center"):
        return "question_only"
    return "none"


def _normalize_tracking_node(raw_node: dict[str, Any]) -> dict[str, Any]:
    node = deepcopy(raw_node)
    lexicon_entity_id = str(
        node.get("lexicon_entity_id") or node.get("entity_id") or ""
    ).strip()
    node["node_id"] = str(node.get("node_id") or lexicon_entity_id).strip()
    node["lexicon_entity_id"] = lexicon_entity_id or None
    node["track"] = _normalize_track(
        node.get("track") or node.get("maturity_tier") or node.get("orbit")
    )
    node["canonical_name"] = _node_name(node)
    if lexicon_entity_id == "evidence_regulation" and node["track"] == "risk":
        node["canonical_name"] = "监管合规质疑"
        node["display_name"] = "监管合规质疑"
        node["term"] = "监管合规质疑"
        stance_summary = _dict(node.get("stance_summary"))
        risk_evidence_count = sum(
            _int(stance_summary.get(key))
            for key in ("skeptical", "risk", "competitive")
        )
        if risk_evidence_count > 0:
            node["mention_answer_count"] = risk_evidence_count
            node["answer_count"] = risk_evidence_count
            node["evidence_count"] = risk_evidence_count
            node["stance_summary"] = {
                "supportive": 0,
                "neutral": 0,
                "skeptical": _int(stance_summary.get("skeptical")),
                "risk": _int(stance_summary.get("risk")),
                "competitive": _int(stance_summary.get("competitive")),
            }
    node["track_reason"] = str(
        node.get("track_reason") or node.get("orbit_reason") or ""
    )
    node["mention_answer_count"] = _node_answers(node)
    node["question_count"] = _int(node.get("question_count")) or len(
        _string_list(node.get("trigger_questions"))
    )
    node["evidence_refs"] = _node_evidence_refs(node)
    return node


def _normalize_track(value: Any) -> str:
    track = str(value or "").strip().lower()
    return TRACK_ALIASES.get(track, "risk" if "risk" in track else "watch")


def _node_evidence_refs(node: dict[str, Any]) -> list[str]:
    return _unique_strings(
        _string_list(node.get("evidence_refs"))
        + _string_list(node.get("evidence_samples"))
    )


def _qualify_item_evidence_refs(item: dict[str, Any], run_id: str) -> None:
    for field in ("evidence_refs", "evidence_samples"):
        values = item.get(field)
        if isinstance(values, list) and all(
            not isinstance(value, (dict, list)) for value in values
        ):
            item[field] = _qualify_evidence_refs(run_id, _string_list(values))


def _node_snapshot_values(node: dict[str, Any]) -> dict[str, Any]:
    position = _dict(node.get("position"))
    platform_summary = node.get("platform_summary") or node.get("platform_distribution")
    if not isinstance(platform_summary, dict):
        platform_summary = {}
    question_summary = _dict(node.get("question_summary")) or {
        "question_ids": _string_list(node.get("trigger_questions"))
    }
    return {
        "node_id": str(node.get("node_id") or ""),
        "lexicon_entity_id": node.get("lexicon_entity_id"),
        "canonical_name": str(node.get("canonical_name") or ""),
        "entity_type": str(node.get("entity_type") or ""),
        "source_type": str(
            node.get("source_type") or node.get("term_origin") or "answer_entity"
        ),
        "track": str(node.get("track") or "watch"),
        "track_reason": str(node.get("track_reason") or ""),
        "mention_answer_count": _node_answers(node),
        "question_count": _int(node.get("question_count")),
        "platform_count": _int(node.get("platform_count")) or len(platform_summary),
        "evidence_count": _int(node.get("evidence_count"))
        or len(_node_evidence_refs(node)),
        "center_anchor_count": _int(node.get("center_anchor_count")),
        "amway_anchor_ratio": _float(node.get("amway_anchor_ratio")),
        "gravity_score": _float(node.get("gravity_score")),
        "distance_score": _float(node.get("distance_score")),
        "stability_score": _float(node.get("stability_score")),
        "risk_score": _float(node.get("risk_score")),
        "position_x": _float(node.get("position_x") or position.get("x")),
        "position_y": _float(node.get("position_y") or position.get("y")),
        "node_size": _float(node.get("node_size") or node.get("size") or 1),
        "display_priority": _int(
            node.get("display_priority") or node.get("priority_rank")
        ),
        "platform_summary": platform_summary,
        "question_summary": question_summary,
        "evidence_refs": _node_evidence_refs(node),
        "calibration_payload": node,
    }


def _edge_snapshot_values(edge: dict[str, Any]) -> dict[str, Any]:
    source = _edge_endpoint(
        edge.get("source_node_id") or edge.get("source") or edge.get("from")
    )
    target = _edge_endpoint(
        edge.get("target_node_id") or edge.get("target") or edge.get("to")
    )
    relation_type = str(
        edge.get("relation_type") or edge.get("type") or edge.get("kind") or ""
    ).strip()
    edge_id = str(edge.get("edge_id") or edge.get("id") or "").strip()
    if not edge_id and source and target:
        edge_id = f"edge_{_payload_hash([source, target, relation_type])[:32]}"
    evidence_refs = _unique_strings(
        _string_list(edge.get("evidence_refs"))
        + _string_list(edge.get("evidence_samples"))
    )
    return {
        "edge_id": edge_id,
        "source_node_id": source,
        "target_node_id": target,
        "relation_type": relation_type,
        "relation_label": str(edge.get("relation_label") or edge.get("label") or ""),
        "strength_score": _float(edge.get("strength_score") or edge.get("strength")),
        "risk_context": str(edge.get("risk_context") or "").strip() or None,
        "evidence_count": _int(edge.get("evidence_count")) or len(evidence_refs),
        "platform_count": _int(edge.get("platform_count")),
        "question_count": _int(edge.get("question_count")),
        "evidence_refs": evidence_refs,
        "edge_payload": edge,
    }


def _edge_endpoint(value: Any) -> str:
    if isinstance(value, dict):
        value = value.get("node_id") or value.get("id")
    return str(value or "").strip()


def _eligible_run_query(
    entity_id: UUID,
    *,
    center_term: str | None = None,
):
    query = select(AmwayCircleRun).where(
        AmwayCircleRun.entity_id == entity_id,
        AmwayCircleRun.status.in_(COMPLETED_RUN_STATUSES),
        AmwayCircleRun.include_in_cumulative.is_(True),
        AmwayCircleRun.completed_at.is_not(None),
    )
    if center_term:
        query = query.where(AmwayCircleRun.center_term == center_term)
    return query


def _empty_period_view(period_type: str) -> dict[str, Any]:
    return {
        "period_type": period_type,
        "current_period": {
            "period_type": period_type,
            "run_ids": [],
            "run_count": 0,
            "question_count": 0,
            "valid_answer_count": 0,
            "failed_answer_count": 0,
            "platforms": [],
            "platform_count": 0,
            "start_at": None,
            "end_at": None,
            "latest_run_id": None,
        },
        "previous_period": None,
        "question_set_changed": False,
        "comparison_notice": "当前还没有可用采集轮次。",
        "change_top5": [],
        "projection": None,
        "report_input": {},
        "report_id": None,
    }


def _empty_period_projection(
    summary: dict[str, Any],
    center_term: str,
) -> dict[str, Any]:
    return {
        "schema_version": PERIOD_VIEW_PROJECTION_VERSION,
        "status": "empty",
        "center_terms": [center_term],
        "nodes": [],
        "edges": [],
        "sample_scope": summary,
        "source_run_ids": summary["run_ids"],
        "source_run_count": summary["run_count"],
        "report_narrative_sections": [],
        "association_actions": [],
        "platform_comparison": [],
        "question_bank": [],
        "evidence_samples": [],
    }


def _period_summary(
    period_type: str,
    runs: list[AmwayCircleRun],
    start_at: datetime | None,
    end_at: datetime | None,
) -> dict[str, Any]:
    completed = [_as_utc(row.completed_at or row.created_at) for row in runs]
    effective_start = start_at or (min(completed) if completed else None)
    effective_end = end_at or (max(completed) if completed else None)
    platforms = _normalized_platforms(
        platform
        for row in runs
        for platform in _string_list(getattr(row, "platforms_completed", []))
    )
    requested_platforms = _normalized_platforms(
        platform
        for row in runs
        for platform in _string_list(getattr(row, "platforms_requested", []))
    )
    question_observation_count = sum(int(row.question_count or 0) for row in runs)
    expected_answer_count = sum(
        int(
            getattr(row, "expected_answer_count", 0)
            or int(getattr(row, "question_count", 0) or 0)
            * len(_string_list(getattr(row, "platforms_requested", [])))
        )
        for row in runs
    )
    valid_answer_count = sum(int(row.valid_answer_count or 0) for row in runs)
    failed_answer_count = sum(int(row.failed_answer_count or 0) for row in runs)
    collection_status = _aggregate_collection_status(
        runs,
        expected_answer_count=expected_answer_count,
        valid_answer_count=valid_answer_count,
    )
    return _period_sample_scope(
        {
            "period_type": period_type,
            "run_ids": [str(row.id) for row in runs],
            "run_count": len(runs),
            "question_count": question_observation_count,
            "question_observation_count": question_observation_count,
            "distinct_question_count": None,
            "expected_answer_count": expected_answer_count,
            "valid_answer_count": valid_answer_count,
            "failed_answer_count": failed_answer_count,
            "collection_status": collection_status,
            "coverage_ratio": _coverage_ratio(
                valid_answer_count,
                expected_answer_count,
            ),
            "platforms": platforms,
            "requested_platforms": requested_platforms,
            "question_signatures": sorted(_question_signatures(runs)),
            "start_at": _iso(effective_start),
            "end_at": _iso(effective_end),
            "latest_run_id": str(runs[0].id) if runs else None,
        }
    )


def _projection_summary(
    summary: dict[str, Any] | None,
    projections: list[AmwayCircleProjection],
) -> dict[str, Any] | None:
    if summary is None:
        return None
    run_ids = [
        str(row.circle_run_id) for row in projections if row.circle_run_id is not None
    ]
    return {
        **summary,
        "run_ids": run_ids,
        "run_count": len(run_ids),
    }


def _period_view_source_hash(
    *,
    period_type: str,
    current_summary: dict[str, Any],
    previous_summary: dict[str, Any] | None,
    current_projections: list[AmwayCircleProjection],
    previous_projections: list[AmwayCircleProjection],
    center_term: str,
) -> str:
    return _payload_hash(
        {
            "projection_version": PERIOD_VIEW_PROJECTION_VERSION,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "report_copy_constraint_version": REPORT_COPY_CONSTRAINT_VERSION,
            "extraction_version": EXTRACTION_SCHEMA_VERSION,
            "calibration_version": CALIBRATION_SCHEMA_VERSION,
            "period_type": period_type,
            "center_term": center_term.strip(),
            "current": _period_source_payload(
                current_summary,
                current_projections,
            ),
            "previous": _period_source_payload(
                previous_summary,
                previous_projections,
            ),
        }
    )


def _period_source_payload(
    summary: dict[str, Any] | None,
    projections: list[AmwayCircleProjection],
) -> dict[str, Any] | None:
    if summary is None:
        return None
    by_run_id = {str(row.circle_run_id): row for row in projections}
    return {
        "summary": summary,
        "runs": [
            {
                "run_id": run_id,
                "projection_source_hash": str(
                    getattr(by_run_id.get(run_id), "source_run_hash", "") or ""
                ),
                "projection_version": str(
                    getattr(by_run_id.get(run_id), "projection_version", "") or ""
                ),
                "projection_content_hash": _payload_hash(
                    _dict(
                        getattr(
                            by_run_id.get(run_id),
                            "association_circle_projection",
                            None,
                        )
                    )
                ),
            }
            for run_id in _string_list(summary.get("run_ids"))
        ],
    }


def _natural_month_count(start_at: datetime, end_at: datetime) -> int:
    start_at = _as_utc(start_at).astimezone(CHINA_TZ)
    end_at = _as_utc(end_at).astimezone(CHINA_TZ)
    if (
        start_at.day != 1
        or start_at.hour
        or start_at.minute
        or start_at.second
        or start_at.microsecond
    ):
        return 0
    last_day = calendar.monthrange(end_at.year, end_at.month)[1]
    if end_at.day != last_day or end_at.hour != 23 or end_at.minute != 59:
        return 0
    if end_at.second not in {59}:
        return 0
    return (end_at.year - start_at.year) * 12 + end_at.month - start_at.month + 1


def _shift_month_start(value: datetime, months: int) -> datetime:
    value = _as_utc(value).astimezone(CHINA_TZ)
    month_index = value.year * 12 + value.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    return value.replace(year=year, month=month_zero + 1, day=1).astimezone(
        timezone.utc
    )


def _question_signatures(runs: list[AmwayCircleRun]) -> set[str]:
    return {row.question_signature for row in runs if row.question_signature}


def _comparison_notice(
    current_runs: list[AmwayCircleRun],
    previous_runs: list[AmwayCircleRun],
    question_set_changed: bool,
) -> str:
    if not current_runs:
        return "当前周期没有可用采集轮次，本报告仅作为空周期提示。"
    if not previous_runs:
        return "当前周期没有可比上一周期，本报告仅作为本周期基线。"
    if question_set_changed:
        return "本周期与上一周期的问题集不同，变化 Top5 只用于观察方向，不作为严格同题对照。"
    return ""


def _aggregate_projection(
    projections: list[AmwayCircleProjection],
    summary: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not projections:
        return None
    bodies = _projection_bodies(projections)
    body = _period_projection_shell(bodies[0][1])
    body["nodes"] = _aggregate_nodes(list(reversed(bodies)))
    question_bank = _aggregate_question_bank(bodies)
    # 实时聚合路径同样需要携带证据与答案原文（报告路径 _build_period_report_artifact
    # 有相同逻辑），否则 period view 的 projection 会丢 source_appendix/evidence_samples。
    evidence_samples = _aggregate_period_items(
        bodies,
        field="evidence_samples",
        id_field="evidence_id",
    )
    source_appendix = _aggregate_period_items(
        bodies,
        field="source_appendix",
        id_field="evidence_id",
    )
    source_ids = {
        str(item.get("evidence_id") or "").strip()
        for item in source_appendix
        if str(item.get("evidence_id") or "").strip()
    }
    source_appendix.extend(
        deepcopy(item)
        for item in evidence_samples
        if str(item.get("evidence_id") or "").strip() not in source_ids
    )
    body["evidence_samples"] = evidence_samples
    body["source_appendix"] = source_appendix
    if summary is not None:
        distinct_question_count = len(question_bank) or _int(
            summary.get("distinct_question_count")
        )
        scoped_summary = {
            **summary,
            "question_observation_count": _int(
                summary.get("question_observation_count")
                or summary.get("question_count")
            ),
            "distinct_question_count": distinct_question_count or None,
            "question_count": distinct_question_count
            or _int(summary.get("question_count")),
        }
        sample_scope = _period_sample_scope(scoped_summary, body)
        body["sample_scope"] = sample_scope
        body["source_run_ids"] = sample_scope["run_ids"]
        body["source_run_count"] = sample_scope["run_count"]
    return body


def _normalize_period_projection(value: Any) -> dict[str, Any]:
    body = deepcopy(_dict(value))
    body["nodes"] = [
        _normalize_tracking_node(node)
        for node in _list(body.get("nodes"))
        if isinstance(node, dict)
    ]
    return body


def _persisted_regulatory_stance(
    *,
    relation_type: Any,
    sentiment_context: Any,
    context_text: Any,
    evidence_text: Any,
    risk_context: Any,
    question_text: Any,
) -> str:
    relation = str(relation_type or "").strip()
    sentiment = str(sentiment_context or "").strip()
    risk_scope = str(risk_context or "").strip()
    text_value = " ".join(
        str(value or "").strip()
        for value in (context_text, evidence_text, risk_context, question_text)
        if str(value or "").strip()
    )
    if relation == "COMPETES_WITH":
        return "competitive"
    if relation == "RISKS_AS":
        return "risk"
    if relation == "RISK_DENIED":
        return "supportive"
    if risk_scope == "denied":
        return "supportive"
    if sentiment == "negative":
        return "skeptical"
    if any(cue in text_value for cue in SKEPTICAL_CONTEXT_CUES):
        return "skeptical"
    if any(cue in text_value for cue in SUPPORTIVE_CONTEXT_CUES):
        return "supportive"
    return "neutral"


def _apply_regulatory_risk_scope(
    projection: dict[str, Any],
    *,
    answer_count: int,
    answer_refs: list[str],
    platform_distribution: dict[str, int],
    stance_summary: dict[str, int],
) -> None:
    platform_summary = {
        platform: {
            "platform": platform,
            "mention_answer_count": count,
            "question_count": 0,
        }
        for platform, count in platform_distribution.items()
    }
    evidence_samples = []
    retained_evidence_ids: set[str] = set()
    for item in _list(projection.get("evidence_samples")):
        if not isinstance(item, dict):
            continue
        lexicon_entity_id = str(
            item.get("lexicon_entity_id") or item.get("entity_id") or ""
        ).strip()
        if lexicon_entity_id != "evidence_regulation":
            evidence_samples.append(item)
            continue
        relation_type = str(item.get("relation_type") or "").strip()
        context_polarity = str(item.get("context_polarity") or "").strip()
        if relation_type == "RISKS_AS" or context_polarity == "negative":
            normalized_item = deepcopy(item)
            normalized_item["node_term"] = "监管合规质疑"
            evidence_samples.append(normalized_item)
            evidence_id = str(normalized_item.get("evidence_id") or "").strip()
            if evidence_id:
                retained_evidence_ids.add(evidence_id.rsplit(":", maxsplit=1)[-1])
    if projection.get("evidence_samples") is not None:
        projection["evidence_samples"] = evidence_samples

    node_groups = [_list(projection.get("nodes"))]
    risk_map = projection.get("risk_map")
    if isinstance(risk_map, dict):
        node_groups.extend(
            [
                _list(risk_map.get("nodes")),
                _list(risk_map.get("top_risks")),
            ]
        )
    for node_group in node_groups:
        for raw_node in node_group:
            if not isinstance(raw_node, dict) or not _is_regulatory_risk_node(raw_node):
                continue
            _update_regulatory_risk_node(
                raw_node,
                answer_count=answer_count,
                answer_refs=answer_refs,
                platform_distribution=platform_distribution,
                platform_summary=platform_summary,
                stance_summary=stance_summary,
                retained_evidence_ids=retained_evidence_ids,
            )
    _normalize_regulatory_report_payload(
        projection,
        answer_count=answer_count,
        platform_count=len(platform_distribution),
    )
    regulatory_node = next(
        (
            node
            for node in _list(projection.get("nodes"))
            if isinstance(node, dict) and _is_regulatory_risk_node(node)
        ),
        None,
    )
    if regulatory_node is not None:
        _synchronize_regulatory_entity_rankings(projection, regulatory_node)


def _is_regulatory_risk_node(node: dict[str, Any]) -> bool:
    lexicon_entity_id = str(
        node.get("lexicon_entity_id") or node.get("entity_id") or ""
    ).strip()
    if lexicon_entity_id != "evidence_regulation":
        return False
    return (
        _normalize_track(
            node.get("track") or node.get("maturity_tier") or node.get("orbit")
        )
        == "risk"
    )


def _update_regulatory_risk_node(
    node: dict[str, Any],
    *,
    answer_count: int,
    answer_refs: list[str],
    platform_distribution: dict[str, int],
    platform_summary: dict[str, dict[str, Any]],
    stance_summary: dict[str, int],
    retained_evidence_ids: set[str],
) -> None:
    skeptical_count = _int(stance_summary.get("skeptical"))
    risk_count = _int(stance_summary.get("risk"))
    node["canonical_name"] = "监管合规质疑"
    node["display_name"] = "监管合规质疑"
    node["term"] = "监管合规质疑"
    node["mention_answer_count"] = answer_count
    node["answer_count"] = answer_count
    node["answer_refs"] = _unique_strings(answer_refs)
    node["count_semantics"] = "distinct_answer_refs"
    node["answer_count_is_exact"] = True
    node["evidence_count"] = answer_count
    node["platform_count"] = len(platform_distribution)
    node["platform_distribution"] = deepcopy(platform_distribution)
    node["platform_summary"] = deepcopy(platform_summary)
    node["stance_summary"] = deepcopy(stance_summary)
    node["relation_type_distribution"] = {
        "LINKED_TO_CENTER_BRAND": skeptical_count,
        "RISKS_AS": risk_count,
    }
    node["supportive_evidence_count"] = 0
    node["neutral_evidence_count"] = 0
    node["skeptical_evidence_count"] = skeptical_count
    node["risk_evidence_count"] = risk_count
    if retained_evidence_ids and isinstance(node.get("evidence_refs"), list):
        node["evidence_refs"] = [
            evidence_ref
            for evidence_ref in node["evidence_refs"]
            if str(evidence_ref).rsplit(":", maxsplit=1)[-1] in retained_evidence_ids
        ]
    reason = (
        f"监管合规质疑在 {answer_count} 条回答中以质疑或风险语境出现，"
        f"覆盖 {len(platform_distribution)} 个平台，应进入风险关系单独查看。"
    )
    node["track_reason"] = reason
    node["orbit_reason"] = reason


def _synchronize_regulatory_entity_rankings(
    value: Any, regulatory_node: dict[str, Any]
) -> None:
    if isinstance(value, dict):
        ranking = value.get("entity_ranking")
        if isinstance(ranking, list):
            for raw_item in ranking:
                if not isinstance(raw_item, dict) or not _is_regulatory_report_item(
                    raw_item
                ):
                    continue
                raw_item.update(
                    {
                        "node_id": regulatory_node.get("node_id"),
                        "entity_id": regulatory_node.get("lexicon_entity_id")
                        or regulatory_node.get("entity_id"),
                        "term": "监管合规质疑",
                        "business_tag": regulatory_node.get("business_tag"),
                        "orbit_label": regulatory_node.get("orbit_label"),
                        "answer_count": _node_answers(regulatory_node),
                        "answer_count_is_exact": True,
                        "count_semantics": "distinct_answer_refs",
                        "platform_count": _int(regulatory_node.get("platform_count")),
                        "gravity_score": _int(regulatory_node.get("gravity_score")),
                        "risk_context_count": _int(
                            regulatory_node.get("risk_evidence_count")
                        )
                        + _int(regulatory_node.get("skeptical_evidence_count"))
                        + _int(regulatory_node.get("competitive_evidence_count")),
                        "evidence_refs": deepcopy(
                            _string_list(regulatory_node.get("evidence_refs"))
                        ),
                    }
                )
            ranking.sort(
                key=lambda item: (
                    -_int(item.get("answer_count")) if isinstance(item, dict) else 0,
                    -_int(item.get("platform_count")) if isinstance(item, dict) else 0,
                    -_int(item.get("gravity_score")) if isinstance(item, dict) else 0,
                    str(item.get("term") or "") if isinstance(item, dict) else "",
                )
            )
        for item in value.values():
            _synchronize_regulatory_entity_rankings(item, regulatory_node)
    elif isinstance(value, list):
        for item in value:
            _synchronize_regulatory_entity_rankings(item, regulatory_node)


def _normalize_regulatory_report_payload(
    projection: dict[str, Any],
    *,
    answer_count: int,
    platform_count: int,
) -> None:
    for field in (
        "evidence_findings",
        "association_actions",
        "report_narrative_sections",
        "analysis_tool_trace",
        "storyline_analysis",
        "report_input",
        "report_markdown",
        "full_markdown",
    ):
        if field in projection:
            projection[field] = _normalize_regulatory_report_value(
                projection[field],
                answer_count=answer_count,
                platform_count=platform_count,
            )
    regulatory_node = next(
        (
            node
            for node in _list(projection.get("nodes"))
            if isinstance(node, dict) and _is_regulatory_risk_node(node)
        ),
        None,
    )
    evidence_refs = (
        _unique_strings(_list(regulatory_node.get("evidence_refs")))
        if regulatory_node
        else []
    )
    retained_evidence_ids = {
        reference.rsplit(":", maxsplit=1)[-1] for reference in evidence_refs
    }
    sample = next(
        (
            item
            for item in _list(projection.get("evidence_samples"))
            if isinstance(item, dict)
            and _is_regulatory_report_item(item)
            and (
                not retained_evidence_ids
                or str(item.get("evidence_id") or "").rsplit(":", maxsplit=1)[-1]
                in retained_evidence_ids
            )
        ),
        None,
    )
    for finding in _list(projection.get("evidence_findings")):
        if not isinstance(finding, dict) or not _is_regulatory_report_item(finding):
            continue
        finding["node_term"] = "监管合规质疑"
        for field in ("claim", "implication", "supporting_facts"):
            finding[field] = _normalize_regulatory_report_value(
                finding.get(field),
                answer_count=answer_count,
                platform_count=platform_count,
                force_regulatory_scope=True,
            )
        finding["evidence_refs"] = deepcopy(evidence_refs)
        if sample:
            finding["sample_platform"] = sample.get("platform")
            finding["sample_question"] = sample.get("question")
            finding["sample_excerpt"] = sample.get("answer_excerpt")
    for action in _list(projection.get("association_actions")):
        if isinstance(action, dict) and _is_regulatory_report_item(action):
            action["evidence_refs"] = deepcopy(evidence_refs)
    source_appendix = []
    for item in _list(projection.get("source_appendix")):
        if not isinstance(item, dict) or not _is_regulatory_report_item(item):
            source_appendix.append(item)
            continue
        evidence_id = str(item.get("evidence_id") or "").rsplit(":", maxsplit=1)[-1]
        if retained_evidence_ids and evidence_id not in retained_evidence_ids:
            continue
        item["node_term"] = "监管合规质疑"
        source_appendix.append(item)
    if "source_appendix" in projection:
        projection["source_appendix"] = source_appendix


def _finalize_period_projection_quality(projection: dict[str, Any]) -> None:
    available_refs = {
        str(item.get("evidence_id") or "").strip()
        for item in _list(projection.get("source_appendix"))
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    _prune_projection_evidence_refs(projection, available_refs)
    _synchronize_evidence_finding_reference_counts(projection)
    quality = _build_report_quality_checks(
        narrative_sections=_list(projection.get("report_narrative_sections")),
        question_definition=_dict(projection.get("question_definition")),
        platform_source_summary=_dict(projection.get("platform_source_summary")),
        evidence_findings=_list(projection.get("evidence_findings")),
        association_actions=_list(projection.get("association_actions")),
        source_appendix=_list(projection.get("source_appendix")),
        nodes=_list(projection.get("nodes")),
        sample_scope=_dict(projection.get("sample_scope")),
        storyline_analysis=_dict(projection.get("storyline_analysis")),
    )
    projection["report_quality_checks"] = quality
    projection["report_delivery_status"] = (
        "ready" if quality.get("passed") is True else "quality_failed"
    )


def _synchronize_evidence_finding_reference_counts(
    projection: dict[str, Any],
) -> None:
    for finding in _list(projection.get("evidence_findings")):
        if not isinstance(finding, dict):
            continue
        reference_count = len(_unique_strings(_string_list(finding.get("evidence_refs"))))
        facts = _string_list(finding.get("supporting_facts"))
        finding["supporting_facts"] = [
            re.sub(
                r"可追溯证据(?:引用)?\s*\d+\s*个",
                f"可追溯证据引用 {reference_count} 个",
                fact,
            )
            for fact in facts
        ]


def _prune_projection_evidence_refs(value: Any, available_refs: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "evidence_refs" and isinstance(item, list):
                value[key] = [
                    reference
                    for reference in _string_list(item)
                    if reference in available_refs
                ]
            else:
                _prune_projection_evidence_refs(item, available_refs)
    elif isinstance(value, list):
        for item in value:
            _prune_projection_evidence_refs(item, available_refs)


def _synchronize_report_artifact(
    artifact: dict[str, Any], projection: dict[str, Any]
) -> None:
    synchronized_fields = (
        "nodes",
        "evidence_samples",
        "association_actions",
        "report_narrative_sections",
        "evidence_findings",
        "source_appendix",
        "storyline_analysis",
        "risk_map",
        "report_input",
        "report_markdown",
        "full_markdown",
        "report_quality_checks",
        "copy_constraints",
    )
    for field in synchronized_fields:
        if field in projection:
            artifact[field] = deepcopy(projection[field])
    dashboard_projection = _dict(artifact.get("dashboard_projection"))
    if dashboard_projection:
        dashboard_projection["association_circle_projection"] = deepcopy(projection)
        artifact["dashboard_projection"] = dashboard_projection


def _is_regulatory_report_item(item: dict[str, Any]) -> bool:
    identity_rules = {
        "entity_id": {"evidence_regulation"},
        "lexicon_entity_id": {"evidence_regulation"},
        "node_id": {"node_evidence_regulation"},
        "node_term": {"监管信息", "监管合规质疑"},
        "term": {"监管信息", "监管合规质疑"},
    }
    explicit_identities = [
        (field, str(item.get(field) or "").strip())
        for field in identity_rules
        if str(item.get(field) or "").strip()
    ]
    if explicit_identities:
        return all(
            value in identity_rules[field] for field, value in explicit_identities
        )
    title = str(item.get("title") or "")
    return "监管信息" in title or "监管合规质疑" in title


def _normalize_regulatory_report_value(
    value: Any,
    *,
    answer_count: int,
    platform_count: int,
    force_regulatory_scope: bool = False,
) -> Any:
    if isinstance(value, dict):
        return {
            key: (
                item
                if key
                in {
                    "answer_excerpt",
                    "context_text",
                    "evidence_text",
                    "matched_text",
                    "question",
                    "question_text",
                    "raw_answer",
                    "sample_excerpt",
                    "source_text",
                }
                else _normalize_regulatory_report_value(
                    item,
                    answer_count=answer_count,
                    platform_count=platform_count,
                    force_regulatory_scope=force_regulatory_scope,
                )
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _normalize_regulatory_report_value(
                item,
                answer_count=answer_count,
                platform_count=platform_count,
                force_regulatory_scope=force_regulatory_scope,
            )
            for item in value
        ]
    if not isinstance(value, str):
        return value
    normalized = value.replace("监管信息", "监管合规质疑")
    if "监管合规质疑" not in normalized and not force_regulatory_scope:
        return normalized
    scoped_summary = (
        f"监管合规质疑在 {answer_count} 条回答中以质疑或风险语境出现，"
        f"覆盖 {platform_count} 个平台"
    )
    normalized = re.sub(
        r"监管合规质疑(?:被|在)\s*\d+\s*条回答(?:提到|中以质疑或风险语境出现)"
        r"，覆盖\s*\d+\s*个平台",
        scoped_summary,
        normalized,
    )
    normalized = re.sub(
        r"监管合规质疑被\s*\d+\s*条回答提到",
        f"监管合规质疑在 {answer_count} 条回答中以质疑或风险语境出现",
        normalized,
    )
    if not force_regulatory_scope:
        return normalized
    normalized = re.sub(
        r"\d+\s*条回答提及",
        f"{answer_count} 条回答提及",
        normalized,
    )
    normalized = re.sub(
        r"本周期证据\s*\d+\s*条",
        f"本周期证据 {answer_count} 条",
        normalized,
    )
    return re.sub(
        r"覆盖\s*\d+\s*个平台",
        f"覆盖 {platform_count} 个平台",
        normalized,
    )


def _projection_bodies(
    projections: list[AmwayCircleProjection],
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (
            str(row.circle_run_id) if row.circle_run_id else "",
            _dict(row.association_circle_projection),
        )
        for row in projections
    ]


def _period_projection_shell(base: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": PERIOD_VIEW_PROJECTION_VERSION,
        "status": "ready",
        "center_terms": deepcopy(_string_list(base.get("center_terms"))),
        "nodes": [],
        "edges": [],
        "artifact_id": None,
    }


def _build_period_report_artifact(
    bodies: list[tuple[str, dict[str, Any]]],
    body: dict[str, Any],
    summary: dict[str, Any],
    tracking_projection: dict[str, Any],
    *,
    entity_id: UUID | None = None,
) -> dict[str, Any]:
    evidence_samples = _aggregate_period_items(
        bodies,
        field="evidence_samples",
        id_field="evidence_id",
    )
    source_appendix = _aggregate_period_items(
        bodies,
        field="source_appendix",
        id_field="evidence_id",
    )
    source_ids = {
        str(item.get("evidence_id") or "").strip()
        for item in source_appendix
        if str(item.get("evidence_id") or "").strip()
    }
    source_appendix.extend(
        deepcopy(item)
        for item in evidence_samples
        if str(item.get("evidence_id") or "").strip() not in source_ids
    )
    available_evidence_refs = {
        str(item.get("evidence_id") or "").strip()
        for item in [*evidence_samples, *source_appendix]
        if isinstance(item, dict) and str(item.get("evidence_id") or "").strip()
    }
    body = _filter_projection_evidence_refs(body, available_evidence_refs)
    question_bank = _aggregate_question_bank(bodies)
    platform_scope = _aggregate_platform_scope(bodies, summary)
    strategy_validation = _aggregate_strategy_validation(bodies, body["nodes"])
    strategy_validation = _filter_item_evidence_refs(
        strategy_validation, available_evidence_refs
    )
    risk_summary = _period_risk_summary(body["nodes"])
    evidence_findings = _period_evidence_findings(
        body["nodes"],
        source_appendix,
    )
    association_actions = _aggregate_actions(bodies)
    association_actions = _filter_item_evidence_refs(
        association_actions, available_evidence_refs
    )
    center_terms = _string_list(body.get("center_terms")) or ["安利"]
    question_scope = {
        **_dict(body.get("question_definition")),
        "center_term": center_terms[0],
        "question_count": _int(summary.get("question_count")),
        "sample_questions": question_bank[:8],
    }
    report_input = {
        "question_scope": question_scope,
        "platform_scope": platform_scope,
        "association_map": {
            "center_terms": center_terms,
            "nodes": body["nodes"],
            "evidence_samples": evidence_samples,
            "generated_from": "entity_calibration",
        },
        "strategy_validation": strategy_validation,
        "strategy_storyline": {},
        "risk_summary": risk_summary,
        "evidence_findings": evidence_findings,
        "source_appendix": source_appendix,
        "association_actions": association_actions,
        "tracking_projection": tracking_projection,
    }
    calibration_result = {
        "schema_version": CALIBRATION_SCHEMA_VERSION,
        "ontology_version": load_default_amway_entity_ontology().definition.version,
        "sample_scope": summary,
        "association_circle_projection": {
            **body,
            "evidence_samples": evidence_samples,
            "source_appendix": source_appendix,
            "question_bank": question_bank,
            "platform_source_summary": platform_scope,
            "strategy_validation": strategy_validation,
            "risk_map": risk_summary,
            "evidence_findings": evidence_findings,
            "association_actions": association_actions,
            "tracking_projection": tracking_projection,
        },
        "report_input": report_input,
    }
    artifact = build_brand_association_circle_report_artifact(
        session_id="period-view",
        entity_id=str(entity_id) if entity_id else None,
        brand_profile={"brand_name": center_terms[0]},
        fetch_results=[],
        simulated_questions=question_bank,
        center_terms=center_terms,
        entity_calibration_result=calibration_result,
    )
    return artifact


def _filter_projection_evidence_refs(
    body: dict[str, Any],
    available_refs: set[str],
) -> dict[str, Any]:
    filtered = deepcopy(body)
    filtered["nodes"] = _filter_item_evidence_refs(
        _list(filtered.get("nodes")), available_refs
    )
    return filtered


def _filter_item_evidence_refs(
    rows: list[Any],
    available_refs: set[str],
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for raw_item in rows:
        if not isinstance(raw_item, dict):
            continue
        item = deepcopy(raw_item)
        for field in ("evidence_refs", "evidence_samples"):
            if isinstance(item.get(field), list):
                item[field] = [
                    ref
                    for ref in _string_list(item.get(field))
                    if ref in available_refs
                ]
        filtered.append(item)
    return filtered


def _period_projection_from_artifact(
    artifact: dict[str, Any],
    body: dict[str, Any],
    summary: dict[str, Any],
    tracking_projection: dict[str, Any],
) -> dict[str, Any]:
    generated = _dict(
        _dict(artifact.get("dashboard_projection")).get("association_circle_projection")
    )
    if not generated:
        return body
    generated["artifact_id"] = None
    generated["report_id"] = None
    generated["source_run_ids"] = _string_list(summary.get("run_ids"))
    generated["source_run_count"] = _int(summary.get("run_count"))
    generated["sample_scope"] = summary
    generated["tracking_projection"] = tracking_projection
    generated["report_markdown"] = artifact.get("report_markdown")
    generated["full_markdown"] = artifact.get("full_markdown")
    generated["title"] = artifact.get("title")
    return generated


def _build_period_report_projection(
    bodies: list[tuple[str, dict[str, Any]]],
    body: dict[str, Any],
    summary: dict[str, Any],
    tracking_projection: dict[str, Any],
) -> dict[str, Any]:
    artifact = _build_period_report_artifact(
        bodies,
        body,
        summary,
        tracking_projection,
    )
    return _period_projection_from_artifact(
        artifact,
        body,
        summary,
        tracking_projection,
    )


def _aggregate_period_items(
    bodies: list[tuple[str, dict[str, Any]]],
    *,
    field: str,
    id_field: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run_id, body in reversed(bodies):
        for raw_item in _list(body.get(field)):
            if not isinstance(raw_item, dict):
                continue
            item = deepcopy(raw_item)
            for platform_field in ("platform", "source_platform", "platform_id"):
                if platform_field not in item:
                    continue
                normalized_platform = _normalize_platform_name(item.get(platform_field))
                if normalized_platform:
                    item[platform_field] = normalized_platform
            raw_id = str(item.get(id_field) or "").strip()
            if not raw_id:
                continue
            qualified_id = _qualify_evidence_refs(run_id, [raw_id])[0]
            if qualified_id in seen:
                continue
            item[id_field] = qualified_id
            if item.get("answer_id"):
                item["answer_id"] = _qualify_evidence_refs(
                    run_id, [str(item["answer_id"])]
                )[0]
            _qualify_item_evidence_refs(item, run_id)
            rows.append(item)
            seen.add(qualified_id)
    return rows


def _aggregate_question_bank(
    bodies: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for _, body in reversed(bodies):
        for raw_item in _list(body.get("question_bank")):
            if not isinstance(raw_item, dict):
                continue
            key = _text_hash(
                raw_item.get("text")
                or raw_item.get("question_text")
                or raw_item.get("question")
                or raw_item.get("id")
            )
            if key in seen:
                continue
            rows.append(deepcopy(raw_item))
            seen.add(key)
    if rows:
        return rows
    for _, body in reversed(bodies):
        for raw_item in _list(body.get("source_appendix")):
            if not isinstance(raw_item, dict):
                continue
            text = str(
                raw_item.get("question") or raw_item.get("question_text") or ""
            ).strip()
            question_id = str(raw_item.get("question_id") or "").strip()
            key = _text_hash(text or question_id)
            if not key or key in seen:
                continue
            rows.append(
                {
                    "id": question_id,
                    "text": text,
                    "audience_segment": raw_item.get("audience_segment"),
                    "life_scene": raw_item.get("life_scene"),
                    "opportunity_point": raw_item.get("opportunity_point"),
                    "probe_type": raw_item.get("probe_type"),
                    "source": "source_appendix",
                }
            )
            seen.add(key)
    return rows


def _aggregate_platform_scope(
    bodies: list[tuple[str, dict[str, Any]]],
    summary: dict[str, Any],
) -> dict[str, Any]:
    sample_scope = _period_sample_scope(summary)
    buckets: dict[str, dict[str, Any]] = {}
    for _, body in bodies:
        source = _dict(body.get("platform_source_summary"))
        platform_rows = _list(source.get("platforms")) or _list(
            body.get("platform_comparison")
        )
        for raw_item in platform_rows:
            if not isinstance(raw_item, dict):
                continue
            platform = _normalize_platform_name(
                raw_item.get("platform") or raw_item.get("name")
            )
            if not platform:
                continue
            bucket = buckets.setdefault(platform, {"platform": platform})
            for key in (
                "valid_answer_count",
                "failed_answer_count",
                "empty_answer_count",
                "mention_answer_count",
            ):
                bucket[key] = _int(bucket.get(key)) + _int(raw_item.get(key))
            if raw_item.get("tendency"):
                bucket["tendency"] = raw_item.get("tendency")
    for platform in _string_list(sample_scope.get("platforms")):
        buckets.setdefault(platform, {"platform": platform})
    platforms = list(buckets.values())
    return {
        **sample_scope,
        "platforms": platforms,
        "platform_names": [item["platform"] for item in platforms],
        "valid_platform_names": [item["platform"] for item in platforms],
        "empty_answer_count": sum(
            _int(item.get("empty_answer_count")) for item in platforms
        ),
    }


def _aggregate_strategy_validation(
    bodies: list[tuple[str, dict[str, Any]]],
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for run_id, body in reversed(bodies):
        for raw_item in _list(body.get("strategy_validation")):
            if not isinstance(raw_item, dict):
                continue
            term = str(
                raw_item.get("strategy_term")
                or raw_item.get("term")
                or raw_item.get("name")
                or ""
            ).strip()
            if term:
                item = deepcopy(raw_item)
                _qualify_item_evidence_refs(item, run_id)
                bucket = buckets.setdefault(
                    term,
                    {
                        "latest": {},
                        "answers": 0,
                        "count_modes": set(),
                        "answer_refs": [],
                        "evidence_refs": [],
                        "question_refs": [],
                    },
                )
                bucket["latest"] = item
                raw_answer_refs = item.get("answer_refs")
                count_mode = _answer_count_merge_mode(item)
                bucket["count_modes"].add(count_mode)
                bucket["answers"] += _answer_count_merge_contribution(item, count_mode)
                if isinstance(raw_answer_refs, list):
                    bucket["answer_refs"] = _unique_strings(
                        bucket["answer_refs"]
                        + _qualify_evidence_refs(run_id, _string_list(raw_answer_refs))
                    )
                bucket["evidence_refs"] = _unique_strings(
                    bucket["evidence_refs"] + _string_list(item.get("evidence_refs"))
                )
                bucket["question_refs"] = _unique_strings(
                    bucket["question_refs"] + _string_list(item.get("question_refs"))
                )
    nodes_by_name = {_node_name(node): node for node in nodes}
    rows: list[dict[str, Any]] = []
    for term, bucket in buckets.items():
        item = deepcopy(bucket["latest"])
        node = nodes_by_name.get(term)
        if node is not None:
            answer_count = _node_answers(node)
            item["answer_count"] = answer_count
            item["answer_mention_count"] = answer_count
            item["evidence_count"] = _int(node.get("evidence_count"))
            item["platform_count"] = _int(node.get("platform_count"))
            item["platform_distribution"] = deepcopy(
                _dict(node.get("platform_distribution"))
            )
            item["stability_score"] = _int(node.get("stability_score"))
            item["gravity_score"] = _int(node.get("gravity_score"))
            item["node_score"] = _int(node.get("gravity_score"))
            item["distance_score"] = _int(node.get("distance_score"))
            item["orbit"] = node.get("orbit") or node.get("track")
            count_mode = _answer_count_merge_mode(node)
            if isinstance(node.get("answer_refs"), list) and count_mode != "legacy":
                item["answer_refs"] = deepcopy(node["answer_refs"])
            else:
                item.pop("answer_refs", None)
            if count_mode == "exact":
                item["count_semantics"] = "distinct_answer_refs"
                item["answer_count_is_exact"] = True
            elif count_mode == "lower_bound":
                item["count_semantics"] = "known_answer_refs_lower_bound"
                item["answer_count_is_exact"] = False
            else:
                item["count_semantics"] = "legacy_summed_mentions"
                item["answer_count_is_exact"] = False
        else:
            answer_count, count_semantics, is_exact, keep_refs = (
                _merged_answer_count_semantics(
                    bucket["count_modes"],
                    bucket["answers"],
                    bucket["answer_refs"],
                )
            )
            item["answer_count"] = answer_count
            item["answer_mention_count"] = answer_count
            item["count_semantics"] = count_semantics
            item["answer_count_is_exact"] = is_exact
            if keep_refs:
                item["answer_refs"] = bucket["answer_refs"]
            else:
                item.pop("answer_refs", None)
        item["evidence_refs"] = bucket["evidence_refs"]
        item["question_refs"] = bucket["question_refs"]
        rows.append(item)
    return rows


def _period_risk_summary(nodes: list[dict[str, Any]]) -> dict[str, Any]:
    risk_nodes = [node for node in nodes if str(node.get("track") or "") == "risk"]
    competition_nodes = [
        node
        for node in risk_nodes
        if str(node.get("entity_type") or "") == "Competitor"
        or str(node.get("business_tag") or "") == "竞争关系"
    ]
    pure_risk_nodes = [node for node in risk_nodes if node not in competition_nodes]
    return {
        "risk_count": len(risk_nodes),
        "nodes": risk_nodes,
        "top_risks": risk_nodes[:5],
        "risk_nodes": pure_risk_nodes,
        "top_risk_nodes": pure_risk_nodes[:5],
        "competition_count": len(competition_nodes),
        "competition_nodes": competition_nodes,
        "top_competitors": competition_nodes[:5],
    }


def _period_evidence_findings(
    nodes: list[dict[str, Any]],
    source_appendix: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for node in nodes[:80]:
        refs = _string_list(node.get("evidence_refs"))
        sample = next(
            (
                item
                for item in source_appendix
                if str(item.get("evidence_id") or "") in refs
                and _evidence_sample_mentions_node(item, node)
            ),
            None,
        )
        name = _node_name(node)
        if not name:
            continue
        count_phrase = _node_count_phrase(node)
        platform_count = _int(node.get("platform_count"))
        track = _node_track(node)
        if track == "risk":
            relationship = (
                "竞争参照"
                if str(node.get("entity_type") or "") == "Competitor"
                or str(node.get("business_tag") or "") == "竞争关系"
                else "风险观察"
            )
            claim = f"{name}已进入{relationship}；{count_phrase}，覆盖 {platform_count} 个平台。"
        else:
            track_label = {
                "stable": "稳定资产区",
                "opportunity": "机会区",
                "watch": "观察区",
            }.get(track, "当前轨道")
            claim = f"{name}当前位于{track_label}；{count_phrase}，覆盖 {platform_count} 个平台。"
        rows.append(
            {
                "node_id": node.get("node_id"),
                "node_term": name,
                "claim": claim,
                "orbit": node.get("orbit") or node.get("track"),
                "supporting_facts": [
                    f"{count_phrase}，覆盖 {platform_count} 个平台。",
                    f"可追溯证据 {len(refs)} 个，距离值 {_int(node.get('distance_score'))}。",
                ],
                "evidence_refs": refs,
                "sample_platform": str((sample or {}).get("platform") or ""),
                "sample_question": str((sample or {}).get("question") or ""),
                "sample_excerpt": str((sample or {}).get("answer_excerpt") or ""),
                "implication": str(
                    node.get("track_reason") or node.get("orbit_reason") or ""
                ),
            }
        )
    return rows


def _aggregate_actions(
    bodies: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for run_id, body in bodies:
        for raw_item in _list(body.get("association_actions")):
            if not isinstance(raw_item, dict):
                continue
            key = str(
                raw_item.get("node_id")
                or raw_item.get("title")
                or raw_item.get("action_label")
                or ""
            ).strip()
            if not key or key in seen:
                continue
            item = deepcopy(raw_item)
            _qualify_item_evidence_refs(item, run_id)
            rows.append(item)
            seen.add(key)
    return rows[:20]


def _aggregate_nodes(
    bodies: list[tuple[str, dict[str, Any]]],
) -> list[dict[str, Any]]:
    score_fields = (
        "raw_gravity_score",
        "gravity_score",
        "frequency_score",
        "position_score",
        "relation_type_score",
        "scene_coverage_score",
        "model_consistency_score",
        "stability_score",
        "risk_score",
    )
    buckets: dict[str, dict[str, Any]] = {}
    latest_body_index = len(bodies) - 1
    for body_index, (run_id, body) in enumerate(bodies):
        for raw_node in _list(body.get("nodes")):
            if not isinstance(raw_node, dict):
                continue
            node = _normalize_tracking_node(raw_node)
            key = _node_key(node)
            if not key:
                continue
            bucket = buckets.setdefault(
                key,
                {
                    "latest_node": None,
                    "fallback_node": None,
                    "fallback_evidence": -1,
                    "answers": 0,
                    "questions": 0,
                    "question_ids": set(),
                    "evidence": 0,
                    "center": 0,
                    "scores": {field: 0.0 for field in score_fields},
                    "score_weights": {field: 0 for field in score_fields},
                    "platform_summary": {},
                    "evidence_refs": [],
                    "answer_refs": [],
                    "count_modes": set(),
                    "stance_summary": {},
                    "relation_type_distribution": {},
                },
            )
            answers = _node_answers(node)
            evidence = _int(node.get("evidence_count"))
            if body_index == latest_body_index:
                bucket["latest_node"] = node
            if evidence > bucket["fallback_evidence"]:
                bucket["fallback_node"] = node
                bucket["fallback_evidence"] = evidence
            weight = max(answers, 1)
            bucket["answers"] += answers
            bucket["questions"] += _int(node.get("question_count"))
            bucket["question_ids"].update(_string_list(node.get("trigger_questions")))
            bucket["evidence"] += evidence
            bucket["center"] += _int(node.get("center_anchor_count"))
            for field in score_fields:
                value = node.get(field)
                if value is None and field == "raw_gravity_score":
                    value = node.get("gravity_score")
                if value is None:
                    continue
                bucket["scores"][field] += _float(value) * weight
                bucket["score_weights"][field] += weight
            bucket["evidence_refs"] = _unique_strings(
                bucket["evidence_refs"]
                + _qualify_evidence_refs(run_id, _node_evidence_refs(node))
            )
            bucket["platform_summary"] = _merge_platform_summary(
                bucket["platform_summary"],
                node.get("platform_summary") or node.get("platform_distribution"),
            )
            raw_answer_refs = node.get("answer_refs")
            count_mode = _answer_count_merge_mode(node)
            bucket["count_modes"].add(count_mode)
            bucket["answers"] -= answers
            bucket["answers"] += _answer_count_merge_contribution(node, count_mode)
            if isinstance(raw_answer_refs, list):
                bucket["answer_refs"] = _unique_strings(
                    bucket["answer_refs"]
                    + _qualify_evidence_refs(run_id, _string_list(raw_answer_refs))
                )
            bucket["stance_summary"] = _merge_count_mapping(
                bucket["stance_summary"], node.get("stance_summary")
            )
            bucket["relation_type_distribution"] = _merge_count_mapping(
                bucket["relation_type_distribution"],
                node.get("relation_type_distribution"),
            )

    rows: list[dict[str, Any]] = []
    for bucket in buckets.values():
        node = deepcopy(bucket["latest_node"] or bucket["fallback_node"] or {})
        platform_summary = bucket["platform_summary"]
        answer_count, count_semantics, is_exact, keep_refs = (
            _merged_answer_count_semantics(
                bucket["count_modes"],
                bucket["answers"],
                bucket["answer_refs"],
            )
        )
        if keep_refs:
            node["answer_refs"] = bucket["answer_refs"]
        else:
            node.pop("answer_refs", None)
        node["count_semantics"] = count_semantics
        node["answer_count_is_exact"] = is_exact
        node["mention_answer_count"] = answer_count
        node["answer_count"] = answer_count
        node["question_count"] = (
            len(bucket["question_ids"])
            if bucket["question_ids"]
            else bucket["questions"]
        )
        node["distinct_question_count"] = node["question_count"]
        node["question_observation_count"] = bucket["questions"]
        node["evidence_count"] = bucket["evidence"]
        node["center_anchor_count"] = bucket["center"]
        node["platform_summary"] = platform_summary
        node["platform_distribution"] = {
            platform: _int(item.get("mention_answer_count"))
            for platform, item in platform_summary.items()
        }
        node["platform_count"] = len(platform_summary)
        node["evidence_refs"] = bucket["evidence_refs"]
        node.pop("evidence_samples", None)
        for field in score_fields:
            field_weight = bucket["score_weights"][field]
            if field_weight:
                node[field] = round(bucket["scores"][field] / field_weight)
        score = _int(node.get("gravity_score"))
        if node.get("raw_gravity_score") is not None:
            score = min(score, _int(node.get("raw_gravity_score")))
        node["gravity_score"] = score
        node["sentiment_gate_score"] = score
        node["association_score"] = score
        node["closeness_score"] = score
        node["distance_score"] = 100 - score
        is_risk = bool(node.get("is_risk_term")) or _node_track(node) == "risk"
        orbit, orbit_label = _period_orbit_for(score, is_risk=is_risk)
        maturity_tier, maturity_label = _period_maturity_for(score, is_risk=is_risk)
        node["orbit"] = orbit
        node["orbit_label"] = orbit_label
        node["track"] = _period_track_for(score, is_risk=is_risk)
        node["maturity_tier"] = maturity_tier
        node["maturity_label"] = maturity_label
        node["stance_summary"] = bucket["stance_summary"]
        node["relation_type_distribution"] = bucket["relation_type_distribution"]
        node["score_aggregation"] = "answer_weighted_run_average"
        rows.append(node)
    return sorted(rows, key=lambda item: _node_sort_key(item))


def _merge_count_mapping(left: dict[str, Any], value: Any) -> dict[str, int]:
    merged = {str(key): _int(count) for key, count in left.items()}
    if not isinstance(value, dict):
        return merged
    for key, count in value.items():
        normalized = str(key).strip()
        if normalized:
            merged[normalized] = merged.get(normalized, 0) + _int(count)
    return merged


def _period_orbit_for(score: int, *, is_risk: bool) -> tuple[str, str]:
    if is_risk:
        return "risk_shadow", "风险关系"
    if score >= 80:
        return "core_near", "已绑定资产"
    if score >= 60:
        return "strong", "已绑定资产"
    if score >= 50:
        return "near_opportunity", "近端机会"
    if score >= 35:
        return "far_opportunity", "远端机会"
    if score >= 20:
        return "weak", "待观察"
    return "blank", "远端待验证"


def _period_track_for(score: int, *, is_risk: bool) -> str:
    if is_risk:
        return "risk"
    if score >= 60:
        return "stable"
    if score >= 35:
        return "opportunity"
    return "watch"


def _period_maturity_for(score: int, *, is_risk: bool) -> tuple[str, str]:
    if is_risk:
        return "risk", "风险关系"
    if score >= 60:
        return "stable_asset", "稳定资产"
    if score >= 50:
        return "near_opportunity", "近端机会"
    if score >= 35:
        return "far_opportunity", "远端机会"
    if score >= 20:
        return "watch_signal", "待观察"
    return "evidence_gap", "证据缺口"


def _merge_platform_summary(
    left: dict[str, Any],
    value: Any,
) -> dict[str, Any]:
    merged = deepcopy(left)
    if not isinstance(value, dict):
        return merged
    for platform, raw_item in value.items():
        if not isinstance(raw_item, dict):
            raw_item = {"mention_answer_count": raw_item}
        key = _normalize_platform_name(platform)
        if not key:
            continue
        item = merged.setdefault(key, {"platform": key})
        item["mention_answer_count"] = _int(item.get("mention_answer_count")) + _int(
            raw_item.get("mention_answer_count") or raw_item.get("count")
        )
        item["question_count"] = _int(item.get("question_count")) + _int(
            raw_item.get("question_count")
        )
        if raw_item.get("tendency"):
            item["tendency"] = raw_item.get("tendency")
    return merged


def _change_top5(
    current_projection: dict[str, Any] | None,
    previous_projection: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    current = _node_map(current_projection)
    previous = _node_map(previous_projection)
    current_answers = _projection_valid_answer_count(current_projection)
    previous_answers = _projection_valid_answer_count(previous_projection)
    if current_answers <= 0 or previous_answers <= 0:
        return []
    rows: list[dict[str, Any]] = []
    for key in sorted(set(current) | set(previous)):
        node = current.get(key)
        old = previous.get(key)
        name = _node_name(node or old or {})
        gravity_delta = round(
            _float((node or {}).get("gravity_score"))
            - _float((old or {}).get("gravity_score"))
        )
        distance_delta = round(
            _float((node or {}).get("distance_score"))
            - _float((old or {}).get("distance_score"))
        )
        mention_delta = _node_answers(node or {}) - _node_answers(old or {})
        mention_rate = _mention_rate(_node_answers(node or {}), current_answers)
        previous_mention_rate = _mention_rate(
            _node_answers(old or {}), previous_answers
        )
        assert mention_rate is not None and previous_mention_rate is not None
        mention_rate_delta = mention_rate - previous_mention_rate
        platform_delta = _int((node or {}).get("platform_count")) - _int(
            (old or {}).get("platform_count")
        )
        if node is None:
            change_type = "dropped"
        elif old is None:
            change_type = "new"
        elif _node_track(node) != _node_track(old):
            change_type = "track_moved"
        else:
            change_type = _same_track_change_type(
                gravity_delta,
                mention_rate_delta,
                platform_delta,
            )
        if change_type == "stable":
            continue
        platform_base = max(
            _int((node or {}).get("platform_count")),
            _int((old or {}).get("platform_count")),
            1,
        )
        change_score = round(
            min(abs(gravity_delta), 100) * 0.45
            + min(abs(mention_rate_delta) * 100, 100) * 0.30
            + min(abs(platform_delta) / platform_base * 100, 100) * 0.15
            + (10 if change_type == "track_moved" else 0),
            1,
        )
        rows.append(
            {
                "node_id": str((node or old or {}).get("node_id") or key),
                "term": name,
                "change_type": change_type,
                "gravity_delta": gravity_delta,
                "distance_delta": distance_delta,
                "mention_delta": mention_delta,
                "mention_rate": round(mention_rate, 6),
                "previous_mention_rate": round(previous_mention_rate, 6),
                "mention_rate_delta": round(mention_rate_delta, 6),
                "platform_delta": platform_delta,
                "track_from": _node_track(old),
                "track_to": _node_track(node),
                "change_score": change_score,
                "evidence_refs": _unique_strings(
                    _node_evidence_refs(node or {}) + _node_evidence_refs(old or {})
                ),
                "explanation": _change_explanation(
                    name,
                    change_type,
                    gravity_delta,
                    mention_delta,
                ),
            }
        )
    return sorted(rows, key=_change_sort_key, reverse=True)[:5]


def _projection_valid_answer_count(projection: dict[str, Any] | None) -> int:
    body = _dict(projection)
    return _int(_dict(body.get("sample_scope")).get("valid_answer_count"))


def _mention_rate(mention_count: int, valid_answer_count: int) -> float | None:
    if valid_answer_count <= 0:
        return None
    return round(mention_count / valid_answer_count, 12)


def _should_compare_period(
    current_projections: list[AmwayCircleProjection],
    previous_projection: dict[str, Any] | None,
    current_projection: dict[str, Any] | None = None,
) -> bool:
    if not current_projections or previous_projection is None:
        return False
    if current_projection is None:
        current_answers = sum(
            _projection_valid_answer_count(
                _dict(projection.association_circle_projection)
            )
            for projection in current_projections
        )
    else:
        current_answers = _projection_valid_answer_count(current_projection)
    return (
        current_answers > 0 and _projection_valid_answer_count(previous_projection) > 0
    )


def _same_track_change_type(
    gravity_delta: int,
    mention_rate_delta: float,
    platform_delta: int,
) -> str:
    if mention_rate_delta < 0:
        return "weakened"
    if mention_rate_delta > 0:
        return "strengthened"
    if gravity_delta < 0 or platform_delta < 0:
        return "weakened"
    if gravity_delta > 0 or platform_delta > 0:
        return "strengthened"
    return "stable"


def _attach_period_tracking(
    projection: dict[str, Any],
    current_summary: dict[str, Any],
    previous_summary: dict[str, Any] | None,
    change_top5: list[dict[str, Any]],
    question_set_changed: bool,
    notice: str,
) -> None:
    projection["tracking_projection"] = {
        "status": "period_view",
        "status_label": "周期视图",
        "period_view": {
            "current_period": current_summary,
            "previous_period": previous_summary,
            "change_top5": change_top5,
            "question_set_changed": question_set_changed,
            "comparison_notice": notice,
        },
    }


def _period_report_input(
    current_summary: dict[str, Any],
    previous_summary: dict[str, Any] | None,
    change_top5: list[dict[str, Any]],
    question_set_changed: bool,
    notice: str,
    projection: dict[str, Any] | None,
) -> dict[str, Any]:
    body = _dict(projection)
    nodes = _list(body.get("nodes"))
    sample_scope = _period_sample_scope(current_summary, body)
    return {
        "contract_version": PERIOD_VIEW_PROJECTION_VERSION,
        "scope": "period_view",
        "count_semantics": {
            "question_count": "distinct_questions",
            "question_observation_count": "run_level_question_observations",
            "node_answer_count": "distinct_answer_refs_or_known_answer_refs_lower_bound_or_legacy_summed_mentions",
        },
        "current_period": sample_scope,
        "previous_period": previous_summary,
        "change_top5": change_top5,
        "question_set_changed": question_set_changed,
        "comparison_notice": notice,
        "current_projection_summary": {
            "node_count": len(nodes),
            "sample_scope": sample_scope,
        },
        "evidence_findings": _list(body.get("evidence_findings")),
        "source_appendix": _list(body.get("source_appendix")),
    }


def _node_map(projection: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    body = _dict(projection)
    rows: dict[str, dict[str, Any]] = {}
    for node in _list(body.get("nodes")):
        if isinstance(node, dict):
            normalized = _normalize_tracking_node(node)
            key = _node_key(normalized)
            if key:
                rows[key] = normalized
    return rows


def _node_key(node: dict[str, Any]) -> str:
    normalized = _normalize_tracking_node(node)
    stable_id = str(
        normalized.get("lexicon_entity_id") or normalized.get("node_id") or ""
    ).strip()
    if stable_id:
        return f"id:{stable_id}".lower()
    name = _node_name(normalized)
    if not name:
        return ""
    entity_type = str(
        normalized.get("entity_type") or normalized.get("source_type") or ""
    ).strip()
    return f"{entity_type}:{name}".lower()


def _node_name(node: dict[str, Any]) -> str:
    return str(
        node.get("canonical_name")
        or node.get("display_name")
        or node.get("term")
        or node.get("node_id")
        or ""
    ).strip()


def _node_answers(node: dict[str, Any]) -> int:
    return _int(node.get("mention_answer_count") or node.get("answer_count"))


def _node_count_phrase(node: dict[str, Any]) -> str:
    count = _node_answers(node)
    mode = _answer_count_merge_mode(node)
    if mode == "exact":
        return f"{count} 条回答"
    if mode == "lower_bound":
        return f"至少 {count} 条可确认回答"
    return f"{count} 次节点提及"


def _evidence_sample_mentions_node(
    sample: dict[str, Any], node: dict[str, Any]
) -> bool:
    text = "".join(
        str(sample.get(field) or "")
        for field in ("question", "answer_excerpt", "quote_text", "evidence_text")
    ).casefold()
    aliases = _unique_strings(
        [
            _node_name(node),
            str(node.get("canonical_name") or ""),
            str(node.get("display_name") or ""),
            *_string_list(node.get("aliases")),
        ]
    )
    expanded_aliases = [
        part.strip()
        for alias in aliases
        for part in re.split(r"[/／、|｜,，()（）]", alias)
        if len(part.strip()) >= 2
    ]
    return any(alias.casefold() in text for alias in [*aliases, *expanded_aliases])


def _answer_count_merge_mode(item: dict[str, Any]) -> str:
    """Return the most conservative merge mode declared by a count record."""
    semantics = str(item.get("count_semantics") or "").strip()
    answer_refs = item.get("answer_refs")
    is_exact = item.get("answer_count_is_exact")
    if semantics == "known_answer_refs_lower_bound":
        return "lower_bound"
    if semantics == "legacy_summed_mentions" or is_exact is False:
        return "legacy"
    if (semantics == "distinct_answer_refs" or is_exact is True) and isinstance(
        answer_refs, list
    ):
        return "exact"
    if isinstance(answer_refs, list) and is_exact is not False:
        return "exact"
    return "legacy"


def _answer_count_merge_contribution(item: dict[str, Any], mode: str) -> int:
    declared_count = _int(
        item.get("mention_answer_count")
        or item.get("answer_count")
        or item.get("answer_mention_count")
    )
    answer_refs = _unique_strings(_string_list(item.get("answer_refs")))
    if mode == "exact":
        return len(answer_refs)
    if mode == "lower_bound":
        return max(declared_count, len(answer_refs))
    return declared_count


def _merged_answer_count_semantics(
    modes: set[str],
    summed_count: int,
    answer_refs: list[str],
) -> tuple[int, str, bool, bool]:
    if modes == {"exact"}:
        return len(answer_refs), "distinct_answer_refs", True, True
    if modes and modes <= {"exact", "lower_bound"}:
        return summed_count, "known_answer_refs_lower_bound", False, True
    return summed_count, "legacy_summed_mentions", False, False


def _node_track(node: dict[str, Any] | None) -> str:
    row = node or {}
    return _normalize_track(
        row.get("track") or row.get("maturity_tier") or row.get("orbit")
    )


def _node_sort_key(node: dict[str, Any]) -> tuple[int, int, int]:
    return (
        _int(node.get("display_priority") or 999),
        -_node_answers(node),
        -_int(node.get("evidence_count")),
    )


def _change_sort_key(item: dict[str, Any]) -> tuple[float, int, int]:
    return (
        _float(item.get("change_score")),
        abs(_int(item.get("mention_delta"))),
        abs(_int(item.get("gravity_delta"))),
    )


def _change_explanation(
    name: str,
    change_type: str,
    gravity_delta: int,
    mention_delta: int,
) -> str:
    if change_type == "new":
        return f"{name}进入本周期图谱，新增{mention_delta}条提及。"
    if change_type == "dropped":
        return f"{name}在本周期未继续出现，提及减少{abs(mention_delta)}条。"
    if change_type == "track_moved":
        return (
            f"{name}发生轨道变化，贴近度变化{gravity_delta}，提及变化{mention_delta}。"
        )
    if change_type == "weakened":
        return f"{name}与品牌的回答绑定变弱，贴近度变化{gravity_delta}，提及变化{mention_delta}。"
    return f"{name}与品牌的回答绑定增强，贴近度变化{gravity_delta}，提及变化{mention_delta}。"


def _unique_strings(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    rows: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        rows.append(item)
    return rows


def _qualify_evidence_refs(run_id: str, refs: list[str]) -> list[str]:
    if not run_id:
        return refs
    rows: list[str] = []
    for ref in refs:
        if _parse_qualified_evidence_ref(ref) is not None:
            rows.append(ref)
        else:
            rows.append(f"{run_id}:{ref}")
    return rows


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _coverage_ratio(valid_answer_count: int, expected_answer_count: int) -> float:
    if expected_answer_count <= 0:
        return 0.0
    return round(
        min(max(valid_answer_count, 0), expected_answer_count)
        / expected_answer_count,
        4,
    )


def _collection_status(
    *,
    calibrated: bool,
    expected_answer_count: int,
    valid_answer_count: int,
) -> str:
    if not calibrated:
        return "partial"
    if valid_answer_count <= 0:
        return "failed"
    if expected_answer_count <= 0:
        return "completed"
    if valid_answer_count < expected_answer_count:
        return "partial"
    return "completed"


def _aggregate_collection_status(
    runs: list[AmwayCircleRun],
    *,
    expected_answer_count: int,
    valid_answer_count: int,
) -> str:
    if not runs:
        return "empty"
    if valid_answer_count <= 0 and expected_answer_count > 0:
        return "failed"
    if any(
        str(getattr(row, "status", "completed") or "completed") != "completed"
        for row in runs
    ):
        return "partial"
    if expected_answer_count > 0 and valid_answer_count < expected_answer_count:
        return "partial"
    return "completed"


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _find_node(nodes: Any, node_id: str) -> dict[str, Any] | None:
    if not isinstance(nodes, list):
        return None
    for item in nodes:
        if isinstance(item, dict) and str(item.get("node_id")) == node_id:
            return item
    return None


def _projection_fallback_run_ids(projection: AmwayCircleProjection) -> list[UUID]:
    run_ids: list[UUID] = []
    for value in (
        projection.circle_run_id,
        projection.base_run_id,
        projection.target_run_id,
        projection.as_of_run_id,
    ):
        if value is not None and value not in run_ids:
            run_ids.append(value)
    return run_ids


def _evidence_keys(
    evidence_refs: list[str],
    run_ids: list[UUID],
) -> list[tuple[UUID, str]]:
    allowed_run_ids = set(run_ids)
    keys: list[tuple[UUID, str]] = []
    loose_refs: list[str] = []
    for raw_ref in evidence_refs:
        parsed = _parse_qualified_evidence_ref(raw_ref)
        if parsed is None:
            loose_refs.append(raw_ref)
            continue
        if parsed[0] not in allowed_run_ids:
            continue
        keys.append(parsed)
    if keys:
        return _unique_evidence_keys(keys)
    if len(run_ids) != 1:
        return []
    return _unique_evidence_keys((run_ids[0], ref) for ref in loose_refs)


def _parse_qualified_evidence_ref(value: str) -> tuple[UUID, str] | None:
    raw = value.strip()
    for separator in (":", "#", "|", "/"):
        if separator not in raw:
            continue
        left, right = raw.split(separator, 1)
        try:
            run_id = UUID(left)
        except ValueError:
            continue
        evidence_ref = right.strip()
        if evidence_ref:
            return run_id, evidence_ref
    return None


def _unique_evidence_keys(values: Iterable[tuple[UUID, str]]) -> list[tuple[UUID, str]]:
    seen: set[tuple[UUID, str]] = set()
    rows: list[tuple[UUID, str]] = []
    for run_id, evidence_ref in values:
        key = (run_id, evidence_ref)
        if key in seen:
            continue
        seen.add(key)
        rows.append(key)
    return rows


def _relationship_summary(node: dict[str, Any]) -> str:
    name = str(node.get("display_name") or node.get("canonical_name") or "该节点")
    track = _track_label(str(node.get("track") or ""))
    answers = int(node.get("mention_answer_count") or 0)
    platforms = int(node.get("platform_count") or 0)
    distance = int(float(node.get("distance_score") or 0))
    return f"{name}当前位于{track}，有{answers}条回答提及，覆盖{platforms}个平台，距离值为{distance}。"


def _next_action(node: dict[str, Any]) -> str:
    track = str(node.get("track") or "")
    if track == "stable":
        return "保留为稳定资产，继续观察平台是否持续主动带回安利。"
    if track == "opportunity":
        return "补充更直接的品牌证据，让它从机会关系进入稳定资产。"
    if track == "risk":
        return "进入风险关系图，逐条核对原文语气和场景来源。"
    return "继续观察，优先确认它是否真的出现在安利上下文里。"


def _top_platforms(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    rows: list[dict[str, Any]] = []
    for platform, item in value.items():
        if isinstance(item, dict):
            rows.append(
                {
                    "platform": str(item.get("platform") or platform),
                    "count": int(
                        item.get("mention_answer_count") or item.get("count") or 0
                    ),
                    "tendency": str(item.get("tendency") or ""),
                }
            )
    return sorted(rows, key=lambda item: item["count"], reverse=True)[:4]


def _track_label(track: str) -> str:
    return {
        "stable": "稳定轨",
        "opportunity": "机会轨",
        "watch": "观察轨",
        "risk": "风险关系",
    }.get(track, "未归类")


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _dict_or_none(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _uuid_or_none(value: Any) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


def _question_signature(question_bank: list[Any]) -> str:
    payload = json.dumps(
        question_bank,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _fetch_results_from_source_appendix(
    source_appendix: list[Any],
) -> list[dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(source_appendix, start=1):
        if not isinstance(item, dict):
            continue
        question_id = str(item.get("question_id") or f"appendix_{index:03d}").strip()
        platform = _normalize_platform_name(item.get("platform"))
        if not question_id or not platform or (question_id, platform) in seen:
            continue
        row = rows.setdefault(
            question_id,
            {
                "question_id": question_id,
                "question_text": str(
                    item.get("question") or item.get("question_text") or question_id
                ).strip(),
                "platform_results": [],
            },
        )
        answer_text = str(
            item.get("answer_excerpt")
            or item.get("quote_text")
            or item.get("evidence_text")
            or ""
        ).strip()
        row["platform_results"].append(
            {
                "platform": platform,
                "success": bool(answer_text),
                "answer": {"content": answer_text},
            }
        )
        seen.add((question_id, platform))
    return list(rows.values())


def _answer_records(
    *,
    fetch_results: list[Any],
    source_appendix: list[Any],
    center_terms: list[str],
) -> list[dict[str, Any]]:
    rows: dict[tuple[str, str], dict[str, Any]] = {}
    for question_index, raw_question in enumerate(fetch_results, start=1):
        if not isinstance(raw_question, dict):
            continue
        question_id = str(
            raw_question.get("question_id") or f"q_{question_index:03d}"
        ).strip()
        question_text = str(
            raw_question.get("question_text")
            or raw_question.get("question")
            or raw_question.get("query")
            or question_id
        ).strip()
        question_metadata = {
            key: raw_question.get(key)
            for key in (
                "audience_segment",
                "core_anxiety",
                "life_scene",
                "opportunity_point",
                "probe_type",
                "mother_theme",
                "question_type",
            )
            if raw_question.get(key) not in (None, "")
        }
        for platform_result in _list(raw_question.get("platform_results")):
            if not isinstance(platform_result, dict):
                continue
            platform = _normalize_platform_name(platform_result.get("platform"))
            if not platform:
                continue
            answer_payload = _dict(platform_result.get("answer"))
            answer_text = str(
                answer_payload.get("content")
                or platform_result.get("answer_text")
                or platform_result.get("content")
                or ""
            ).strip()
            success = bool(platform_result.get("success", bool(answer_text)))
            rows[(question_id, platform)] = {
                "question_id": question_id,
                "question_hash": _text_hash(question_text),
                "question_index": question_index,
                "question_text": question_text,
                "question_metadata": question_metadata,
                "platform": platform,
                "platform_model": str(
                    platform_result.get("model")
                    or platform_result.get("platform_model")
                    or ""
                ).strip()
                or None,
                "fetch_agent_version": str(
                    platform_result.get("fetch_agent_version") or ""
                ).strip(),
                "fetch_status": "success" if success and answer_text else "failed",
                "answer_text": answer_text or None,
                "answer_excerpt": answer_text[:1200] or None,
                "answer_hash": _text_hash(answer_text) if answer_text else None,
                "mentions_center": any(term in answer_text for term in center_terms),
                "answer_quality": "valid" if answer_text else "empty",
                "raw_payload": platform_result,
                "error_code": str(platform_result.get("error_code") or "").strip()
                or None,
                "error_message": str(platform_result.get("error_message") or "").strip()
                or None,
                "fetched_at": _datetime_or_none(platform_result.get("fetched_at")),
            }

    for source_rank, raw_item in enumerate(source_appendix, start=1):
        if not isinstance(raw_item, dict):
            continue
        question_id = str(
            raw_item.get("question_id") or f"appendix_{source_rank:03d}"
        ).strip()
        platform = _normalize_platform_name(raw_item.get("platform"))
        if not platform or (question_id, platform) in rows:
            continue
        item = {
            "question_id": question_id,
            "question_text": str(raw_item.get("question") or question_id).strip(),
            "platform": platform,
            "quote_text": str(raw_item.get("answer_excerpt") or "").strip(),
        }
        rows[(question_id, platform)] = _fallback_answer_record(item, center_terms)
        rows[(question_id, platform)]["question_index"] = source_rank
    return list(rows.values())


def _evidence_records(
    artifact: dict[str, Any],
    projection_body: dict[str, Any],
) -> list[dict[str, Any]]:
    association_circle = _dict(artifact.get("association_circle"))
    candidates = (
        _list(projection_body.get("evidence_samples"))
        + _list(association_circle.get("evidence_samples"))
        + _list(artifact.get("source_appendix"))
        + _list(projection_body.get("source_appendix"))
    )
    rows: dict[str, dict[str, Any]] = {}
    for raw_item in candidates:
        if not isinstance(raw_item, dict):
            continue
        evidence_ref = str(
            raw_item.get("evidence_id") or raw_item.get("evidence_ref") or ""
        ).strip()
        if not evidence_ref:
            continue
        question_id = str(raw_item.get("question_id") or "").strip()
        platform = _normalize_platform_name(raw_item.get("platform"))
        if not question_id or not platform:
            continue
        current = rows.setdefault(
            evidence_ref,
            {
                "evidence_ref": evidence_ref,
                "lexicon_entity_id": str(
                    raw_item.get("lexicon_entity_id") or raw_item.get("entity_id") or ""
                ).strip()
                or None,
                "platform": platform,
                "question_id": question_id,
                "question_text": "",
                "quote_text": "",
                "quote_type": "answer_excerpt",
                "entity_names": [],
                "strategy_terms": [],
                "scenario_tags": [],
            },
        )
        current["question_text"] = str(
            raw_item.get("question")
            or raw_item.get("question_text")
            or current["question_text"]
        ).strip()
        current["quote_text"] = str(
            raw_item.get("answer_excerpt")
            or raw_item.get("quote_text")
            or raw_item.get("evidence_text")
            or current["quote_text"]
        ).strip()
        current["quote_type"] = str(
            raw_item.get("quote_type") or current["quote_type"]
        ).strip()
        current["lexicon_entity_id"] = (
            current.get("lexicon_entity_id")
            or str(
                raw_item.get("lexicon_entity_id") or raw_item.get("entity_id") or ""
            ).strip()
            or None
        )
        node_term = str(
            raw_item.get("node_term") or raw_item.get("entity_name") or ""
        ).strip()
        if node_term:
            current["entity_names"] = _unique_strings(
                current["entity_names"] + [node_term]
            )
        current["strategy_terms"] = _unique_strings(
            current["strategy_terms"] + _string_list(raw_item.get("strategy_terms"))
        )
        current["scenario_tags"] = _unique_strings(
            current["scenario_tags"]
            + _string_list(raw_item.get("scenario_tags"))
            + _string_list(raw_item.get("life_scene"))
            + _string_list(raw_item.get("opportunity_point"))
        )
    return [item for item in rows.values() if item["quote_text"]]


def _fallback_answer_record(item: dict[str, Any], center_terms: Any) -> dict[str, Any]:
    question_text = str(item.get("question_text") or item["question_id"]).strip()
    answer_text = str(item.get("quote_text") or "").strip()
    return {
        "question_id": item["question_id"],
        "question_hash": _text_hash(question_text),
        "question_index": 0,
        "question_text": question_text,
        "question_metadata": {},
        "platform": item["platform"],
        "platform_model": None,
        "fetch_agent_version": "",
        "fetch_status": "success" if answer_text else "failed",
        "answer_text": answer_text or None,
        "answer_excerpt": answer_text[:1200] or None,
        "answer_hash": _text_hash(answer_text) if answer_text else None,
        "mentions_center": any(
            term in answer_text for term in _string_list(center_terms)
        ),
        "answer_quality": "valid" if answer_text else "empty",
        "raw_payload": None,
        "error_code": None,
        "error_message": None,
        "fetched_at": None,
    }


def _text_hash(value: Any) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _normalize_platform_name(value: Any) -> str:
    return normalize_public_platform_id(value) or ""


def _normalized_platforms(values: Any) -> list[str]:
    return sorted(
        {platform for value in values if (platform := _normalize_platform_name(value))}
    )


def _period_sample_scope(
    summary: dict[str, Any],
    projection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    platforms = _normalized_platforms(
        [
            *_string_list(summary.get("platforms")),
            *_projection_platforms(projection),
        ]
    )
    requested_platforms = (
        _normalized_platforms(_string_list(summary.get("requested_platforms")))
        or platforms
    )
    nodes = _list(_dict(projection).get("nodes")) if projection is not None else []
    return {
        **summary,
        "question_count": _int(summary.get("question_count")),
        "requested_platforms": requested_platforms,
        "requested_platform_count": len(requested_platforms),
        "platforms": platforms,
        "valid_platform_names": platforms,
        "valid_platform_count": len(platforms),
        "platform_count": len(platforms),
        "valid_answer_count": _int(summary.get("valid_answer_count")),
        "failed_answer_count": _int(summary.get("failed_answer_count")),
        "expected_answer_count": _int(summary.get("expected_answer_count")),
        "collection_status": str(summary.get("collection_status") or "").strip()
        or "completed",
        "coverage_ratio": _float(summary.get("coverage_ratio")),
        "normalized_node_count": (
            len(nodes)
            if projection is not None
            else _int(summary.get("normalized_node_count"))
        ),
    }


def _projection_platforms(projection: dict[str, Any] | None) -> list[str]:
    body = _dict(projection)
    rows: list[str] = []
    source = _dict(body.get("platform_source_summary"))
    rows.extend(
        _string_list(source.get("valid_platform_names") or source.get("platform_names"))
    )
    for item in _list(source.get("platforms")):
        if isinstance(item, dict):
            rows.append(str(item.get("platform") or item.get("name") or ""))
    for node in _list(body.get("nodes")):
        if isinstance(node, dict):
            rows.extend(_dict(node.get("platform_distribution")).keys())
    return _normalized_platforms(rows)


def _completed_platforms(value: Any, requested: list[str]) -> list[str]:
    summary = _dict(value)
    rows = _string_list(
        summary.get("valid_platform_names") or summary.get("completed_platforms")
    )
    for item in _list(summary.get("platforms")):
        if not isinstance(item, dict):
            continue
        platform = str(item.get("platform") or item.get("name") or "").strip()
        valid = _int(
            item.get("valid_answer_count")
            or item.get("success_count")
            or item.get("answer_count")
        )
        if platform and valid > 0:
            rows.append(platform)
    normalized = _normalized_platforms(rows)
    allowed = set(_normalized_platforms(requested))
    return [
        item for item in _unique_strings(normalized) if not allowed or item in allowed
    ]


def _datetime_or_now(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _as_utc(value)
    text = str(value or "").strip()
    if text:
        try:
            return _as_utc(datetime.fromisoformat(text.replace("Z", "+00:00")))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _datetime_or_none(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return _as_utc(value)
    try:
        return _as_utc(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except ValueError:
        return None


def _uuid_list(value: Any) -> list[UUID]:
    rows: list[UUID] = []
    for item in _string_list(value):
        try:
            rows.append(UUID(item))
        except ValueError:
            continue
    return rows


def _iso(value: Any) -> str | None:
    return value.isoformat() if value else None
