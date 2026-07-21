"""Dashboard task center for brand intelligence workflows."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.brand_intelligence_run import (
    BRAND_INTELLIGENCE_ACTIVE_RUN_STATUSES,
    BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES, BrandIntelligenceRun,
    BrandIntelligenceRunStatus)
from app.models.entity import Entity
from app.models.session import Session, SessionStatus
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.models.task import AnalysisTask, TaskStatus
from app.models.task_run import TaskTriggerSource
from app.models.user import User
from app.services.amway_circle_tracking_service import \
    AmwayCircleTrackingService
from app.services.brand_association_circle_variant import (
    BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
    build_amway_association_context,
)
from app.services.brand_ontology_world_service import BrandOntologyWorldService
from app.services.entity_service import EntityService
from app.services.job_submission_service import JobSubmissionService
from app.services.runtime_coordinator import runtime_coordinator
from app.services.task_service import TaskService
from app.workflow.graph import get_compiled_workflow
from app.workflow.runtime_policy_executor import build_next_required_action

logger = logging.getLogger(__name__)


DEFAULT_RUN_GOAL = "分析当前品牌在 AI 平台里的表现"
RUN_STAGE_PROGRESS: dict[str, float] = {
    BrandIntelligenceRunStatus.NOT_STARTED.value: 0.0,
    BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value: 0.12,
    BrandIntelligenceRunStatus.FETCHING_ANSWERS.value: 0.45,
    BrandIntelligenceRunStatus.WAITING_TAKEOVER.value: 0.5,
    BrandIntelligenceRunStatus.ANALYZING_METRICS.value: 0.72,
    BrandIntelligenceRunStatus.BUILDING_WORLD.value: 0.86,
    BrandIntelligenceRunStatus.GENERATING_RECOMMENDATIONS.value: 0.94,
    BrandIntelligenceRunStatus.WAITING_USER.value: 0.5,
    BrandIntelligenceRunStatus.COMPLETED.value: 1.0,
    BrandIntelligenceRunStatus.FAILED.value: 0.0,
    BrandIntelligenceRunStatus.CANCELLED.value: 0.0,
}

TASK_STAGE_TO_RUN_STATUS: dict[str, str] = {
    "A3": BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value,
    "question_simulation": BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value,
    "A4": BrandIntelligenceRunStatus.FETCHING_ANSWERS.value,
    "answer_fetch": BrandIntelligenceRunStatus.FETCHING_ANSWERS.value,
    "A5": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    "analysis_report": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    "analysis_report_skill": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    # 3b-1.5 canvas custom nodes (still under the analyzing phase of a run)
    "SECONDARY_ANALYSIS": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    "amway_secondary_analysis": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    "CONTENT_DRAFT": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
    "amway_content_draft": BrandIntelligenceRunStatus.ANALYZING_METRICS.value,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_uuid(value: str | UUID | None, field_name: str) -> UUID | None:
    if value is None:
        return None
    try:
        return value if isinstance(value, UUID) else UUID(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid UUID for {field_name}: {value}") from exc


def _normalize_mode(value: str | None) -> str:
    normalized = str(value or "panorama").strip().lower()
    if normalized in {
        BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
        "association_circle",
        "amway_association_circle",
    }:
        return BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE
    if normalized in {"scenario", "persona", "scenario_monitoring"}:
        return "scenario"
    return "panorama"


def _merge_json(existing: dict | None, patch: dict | None) -> dict | None:
    if not patch:
        return existing
    merged = dict(existing or {})
    merged.update(patch)
    return merged


def _string_list(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value or "").strip()
    return [text] if text else []


def _build_minimal_brand_profile(entity: Entity) -> dict[str, Any]:
    profile: dict[str, Any] = {"brand_name": entity.name}
    if entity.domain:
        profile["official_website"] = entity.domain
    if entity.industry:
        profile["industry"] = entity.industry
    if getattr(entity, "description", None):
        profile["description"] = entity.description
    return profile


def _association_context_from_scope(
    input_scope: dict[str, Any]
) -> dict[str, Any] | None:
    context: dict[str, Any] = {}
    for key in ("center_terms", "enabled_surfaces"):
        value = input_scope.get(key)
        if isinstance(value, list) and (normalized := _string_list(value)):
            context[key] = normalized
    active_center_term = input_scope.get("active_center_term")
    if isinstance(active_center_term, str) and active_center_term.strip():
        context["active_center_term"] = active_center_term.strip()
    return context or None


def _association_context_for_run(
    *,
    entity: Entity,
    input_scope: dict[str, Any],
) -> dict[str, Any] | None:
    raw_aliases = getattr(entity, "aliases", None)
    try:
        aliases = json.loads(raw_aliases) if raw_aliases else []
    except (json.JSONDecodeError, TypeError):
        aliases = [raw_aliases]
    if not isinstance(aliases, list):
        aliases = [aliases]

    association_context = build_amway_association_context(
        name=entity.name,
        domain=entity.domain,
        aliases=aliases,
    )
    if association_context is None:
        return None
    return _merge_json(
        association_context,
        _association_context_from_scope(input_scope),
    )


def _uploaded_question_payload_from_scope(
    input_scope: dict[str, Any],
) -> dict[str, Any] | None:
    raw_questions = input_scope.get("uploaded_questions")
    if not isinstance(raw_questions, list):
        return None

    questions: list[dict[str, Any]] = []
    for index, item in enumerate(raw_questions, start=1):
        if isinstance(item, str):
            text = item.strip()
            question = {"id": f"dashboard_upload_{index:03d}", "text": text}
        elif isinstance(item, dict):
            text = str(
                item.get("text")
                or item.get("core_question")
                or item.get("question")
                or ""
            ).strip()
            question = dict(item)
            question["text"] = text
            question.setdefault("id", f"dashboard_upload_{index:03d}")
        else:
            continue
        if not text:
            continue
        question.setdefault("source", "uploaded_table")
        questions.append(question)

    if not questions:
        return None

    source_file_name = str(
        input_scope.get("uploaded_question_source") or "dashboard_upload"
    ).strip()
    source_file_id = str(input_scope.get("uploaded_question_file_id") or "").strip()

    return {
        "table_kind": "question_list",
        "source_file": {
            "file_id": source_file_id or None,
            "name": source_file_name or "dashboard_upload",
        },
        "normalized_payload": {"questions": questions},
        "import_intent": {
            "mode": str(input_scope.get("question_import_mode") or "replace"),
        },
        "warnings": [],
    }


def _build_brand_run_initial_state(
    *,
    run: BrandIntelligenceRun,
    entity: Entity,
    session_uuid: UUID,
    task_id: UUID,
    task_run_uuid: UUID,
) -> dict[str, Any]:
    input_scope = dict(run.input_scope or {})
    association_context = _association_context_for_run(
        entity=entity,
        input_scope=input_scope,
    )
    platform_filter = _string_list(input_scope.get("platforms"))
    uploaded_question_payload = _uploaded_question_payload_from_scope(input_scope)
    fetch_mode = str(input_scope.get("fetch_mode") or "fast").strip().lower()
    if fetch_mode not in {"fast", "full"}:
        fetch_mode = "fast"
    run_policy = "full_browser" if fetch_mode == "full" else "quick"

    resolved_analysis_mode = (
        BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE
        if association_context
        else "persona" if run.analysis_mode == "scenario" else "baseline"
    )
    dashboard_context = {
        "source": "brand_intelligence_run",
        "run_id": str(run.id),
        "analysis_mode": run.analysis_mode,
    }
    if association_context:
        dashboard_context.update(association_context)
        input_scope = _merge_json(input_scope, association_context) or input_scope

    user_decisions = {
        "fetch_mode": fetch_mode,
        "fetch_mode_confirmed": True,
        "fetch_mode_pending": False,
    }
    if association_context:
        user_decisions["a3_mode"] = BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE
    if uploaded_question_payload:
        user_decisions.update(
            {
                "a3_mode": "uploaded_list",
                "table_import_confirmed": True,
                "confirmed_table_kind": "question_list",
                "question_import_mode": uploaded_question_payload["import_intent"][
                    "mode"
                ],
            }
        )

    next_tool_args = {"mode": "baseline_dynamic"}
    if association_context:
        next_tool_args.update(
            {
                "analysis_mode": BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
                "report_kind": BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE,
                "center_terms": association_context.get("center_terms"),
            }
        )
    if uploaded_question_payload:
        next_tool_args["mode"] = "uploaded_list"

    return {
        "session_id": str(session_uuid),
        "user_id": str(run.created_by_user_id) if run.created_by_user_id else None,
        "entity_id": str(run.entity_id),
        "messages": [],
        "brand_name": entity.name,
        "official_website": entity.domain or None,
        "industry_hint": entity.industry or None,
        "brand_profile": _build_minimal_brand_profile(entity),
        "competitors": None,
        "competitive_landscape": None,
        "marketing_personas": None,
        "simulated_questions": None,
        "questions": None,
        "fetch_results": None,
        "metrics": None,
        "report": None,
        "snapshot_id": None,
        "current_step": "",
        "execution_status": "idle",
        "progress": 0.0,
        "progress_message": "",
        "pending_confirmation": None,
        "user_decisions": user_decisions,
        "error_info": None,
        "orchestrator_history": [],
        "orchestrator_reply": None,
        "next_action": None,
        "awaiting_user": False,
        "tool_call_args": None,
        "tool_call_id": None,
        "agent_retry_counts": {},
        "selected_tool_mode": None,
        "latest_user_input": run.run_goal or DEFAULT_RUN_GOAL,
        "dashboard_context": dashboard_context,
        "table_intake_result": uploaded_question_payload,
        "confirmed_import_action": (
            {"import_mode": uploaded_question_payload["import_intent"]["mode"]}
            if uploaded_question_payload
            else None
        ),
        "task_id": str(task_id),
        "run_id": str(task_run_uuid),
        "analysis_mode": resolved_analysis_mode,
        "headless_mode": True,
        "fetch_mode": fetch_mode,
        "run_policy": run_policy,
        "platform_filter": platform_filter or None,
        "preserved_fetch_results": None,
        "baseline_questions": None,
        "baseline_fetch_results": None,
        "baseline_metrics": None,
        "baseline_report": None,
        "next_required_action": build_next_required_action(
            tool_name="question_simulation",
            authority="authoritative_resume",
            reason="Dashboard started a background brand intelligence run.",
            tool_args=next_tool_args,
            source_step="brand_intelligence_run",
            metadata={
                "brand_intelligence_run_id": str(run.id),
                "headless_mode": True,
                "preselected_fetch_mode": fetch_mode,
                "uploaded_question_count": len(
                    (
                        uploaded_question_payload
                        or {"normalized_payload": {"questions": []}}
                    )["normalized_payload"]["questions"]
                ),
            },
        ),
    }


class BrandIntelligenceRunService:
    """State source for Dashboard-driven brand intelligence workflows."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_run(
        self,
        *,
        entity_id: str | UUID,
        current_user: User,
    ) -> BrandIntelligenceRun | None:
        entity = await self._require_entity(entity_id, current_user)
        stmt = (
            select(BrandIntelligenceRun)
            .where(
                BrandIntelligenceRun.entity_id == entity.id,
                BrandIntelligenceRun.status.in_(BRAND_INTELLIGENCE_ACTIVE_RUN_STATUSES),
            )
            .order_by(desc(BrandIntelligenceRun.updated_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return await self._sync_with_analysis_task(result.scalar_one_or_none())

    async def get_run(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> BrandIntelligenceRun | None:
        run_uuid = _coerce_uuid(run_id, "run_id")
        stmt = select(BrandIntelligenceRun).where(BrandIntelligenceRun.id == run_uuid)
        result = await self.db.execute(stmt)
        run = result.scalar_one_or_none()
        if run is None:
            return None
        try:
            entity = await self._require_entity(run.entity_id, current_user)
        except LookupError:
            return None
        if entity.id != run.entity_id:
            return None
        return await self._sync_with_analysis_task(run)

    async def create_or_reuse_run(
        self,
        *,
        entity_id: str | UUID,
        current_user: User,
        run_goal: str | None = None,
        analysis_mode: str | None = None,
        input_scope: dict[str, Any] | None = None,
        origin_surface: str = "dashboard",
        origin_session_id: str | UUID | None = None,
        origin_event_id: str | None = None,
        start_immediately: bool = True,
        commit: bool = True,
    ) -> BrandIntelligenceRun:
        entity = await self._require_entity(entity_id, current_user)
        association_context = build_amway_association_context(
            name=entity.name,
            domain=entity.domain,
        )
        normalized_input_scope = (
            _merge_json(input_scope, association_context)
            if association_context
            else input_scope
        )
        normalized_analysis_mode = (
            BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE
            if association_context
            else _normalize_mode(analysis_mode)
        )
        normalized_event_id = str(origin_event_id or "").strip() or None
        if normalized_event_id:
            existing_by_event = await self._find_by_origin_event(
                entity_id=entity.id,
                origin_event_id=normalized_event_id,
            )
            if existing_by_event is not None:
                return existing_by_event

        active = await self.get_active_run(
            entity_id=entity.id,
            current_user=current_user,
        )
        if active is not None:
            active.input_scope = _merge_json(active.input_scope, normalized_input_scope)
            active.analysis_mode = normalized_analysis_mode
            active.last_activity_at = _now()
            active.updated_at = active.last_activity_at
            if (
                start_immediately
                and active.status == BrandIntelligenceRunStatus.NOT_STARTED.value
            ):
                active.status = BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value
                active.stage = "planning_questions"
                active.progress = RUN_STAGE_PROGRESS[
                    BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value
                ]
                active.message = "正在生成问题和样本范围"
                active.started_at = active.started_at or active.last_activity_at
            if commit:
                await self.db.commit()
                await self.db.refresh(active)
            else:
                await self.db.flush()
            return active

        now = _now()
        initial_status = (
            BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value
            if start_immediately
            else BrandIntelligenceRunStatus.NOT_STARTED.value
        )
        initial_stage = "planning_questions" if start_immediately else "not_started"
        run = BrandIntelligenceRun(
            entity_id=entity.id,
            created_by_user_id=current_user.id,
            origin_session_id=_coerce_uuid(origin_session_id, "origin_session_id"),
            origin_surface=(origin_surface or "dashboard")[:80],
            origin_event_id=normalized_event_id,
            status=initial_status,
            stage=initial_stage,
            progress=RUN_STAGE_PROGRESS[initial_status],
            message=("正在生成问题和样本范围" if start_immediately else "等待开始分析"),
            run_goal=(run_goal or DEFAULT_RUN_GOAL).strip() or DEFAULT_RUN_GOAL,
            analysis_mode=normalized_analysis_mode,
            input_scope=normalized_input_scope or {},
            output_refs={},
            started_at=now if start_immediately else None,
            last_activity_at=now,
            created_at=now,
            updated_at=now,
        )
        self.db.add(run)
        if commit:
            await self.db.commit()
            await self.db.refresh(run)
        else:
            await self.db.flush()
        return run

    async def ensure_runtime_submitted(
        self,
        *,
        run: BrandIntelligenceRun,
        current_user: User,
    ) -> BrandIntelligenceRun:
        if run.analysis_task_id:
            return run
        entity = await self._require_entity(run.entity_id, current_user)
        session = Session(
            user_id=current_user.id,
            title=f"{entity.name} AI 品牌情报",
            status=SessionStatus.ACTIVE,
            entity_id=entity.id,
            extra_metadata=json.dumps(
                {
                    "source": "brand_intelligence_run",
                    "run_id": str(run.id),
                    "origin_surface": run.origin_surface,
                },
                ensure_ascii=False,
            ),
        )
        self.db.add(session)
        await self.db.flush()

        submitted = await JobSubmissionService(self.db).submit_manual_analysis(
            user_id=current_user.id,
            session_id=session.id,
            brand_name=entity.name,
            entity_id=entity.id,
            trigger_source=TaskTriggerSource.MESSAGES_API,
        )
        reloaded = await self._get_run_unscoped(run.id)
        if reloaded is None:
            return run
        output_refs = dict(reloaded.output_refs or {})
        output_refs.update(
            {
                "session_id": str(session.id),
                "task_run_id": str(submitted.run.id),
            }
        )
        reloaded.origin_session_id = session.id
        reloaded.analysis_task_id = submitted.task.id
        reloaded.output_refs = output_refs
        reloaded.last_activity_at = _now()
        reloaded.updated_at = reloaded.last_activity_at
        await self.db.commit()
        await self.db.refresh(reloaded)
        return reloaded

    async def resume_run(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> BrandIntelligenceRun | None:
        run = await self.get_run(run_id=run_id, current_user=current_user)
        if run is None:
            return None
        if run.status == BrandIntelligenceRunStatus.CANCELLED.value:
            raise ValueError("已取消的任务不能继续")
        if run.status == BrandIntelligenceRunStatus.COMPLETED.value:
            return run
        return await self.transition(
            run,
            status=BrandIntelligenceRunStatus.FETCHING_ANSWERS.value,
            stage="fetching_answers",
            progress=max(run.progress, RUN_STAGE_PROGRESS["fetching_answers"]),
            message="正在继续采集 AI 回答",
            requires_user_action=False,
            user_action_type=None,
            blocking_reason=None,
            clear_error=True,
        )

    async def cancel_run(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
    ) -> BrandIntelligenceRun | None:
        run = await self.get_run(run_id=run_id, current_user=current_user)
        if run is None:
            return None
        if run.status in BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES:
            return run
        now = _now()
        run.status = BrandIntelligenceRunStatus.CANCELLED.value
        run.stage = "cancelled"
        run.message = "已取消"
        run.requires_user_action = False
        run.user_action_type = None
        run.blocking_reason = None
        run.completed_at = now
        run.last_activity_at = now
        run.updated_at = now
        task_id = run.analysis_task_id
        task_run_id_raw = (run.output_refs or {}).get("task_run_id")
        task_run_id = _coerce_uuid(task_run_id_raw, "task_run_id")
        session_id = str(run.origin_session_id) if run.origin_session_id else None
        if task_id is not None:
            await TaskService(self.db).cancel_task(task_id, run_id=task_run_id)
        await self.db.commit()
        if task_id is not None:
            await runtime_coordinator.cancel_task_execution(
                task_id,
                session_id=session_id,
            )
        await self.db.refresh(run)
        return run

    async def confirm_run(
        self,
        *,
        run_id: str | UUID,
        current_user: User,
        user_action_type: str | None = None,
        feedback_text: str | None = None,
        provided_inputs: dict[str, Any] | None = None,
        origin_event_id: str | None = None,
    ) -> BrandIntelligenceRun | None:
        run = await self.get_run(run_id=run_id, current_user=current_user)
        if run is None:
            return None
        output_refs = dict(run.output_refs or {})
        confirmations = list(output_refs.get("confirmations") or [])
        confirmations.append(
            {
                "user_action_type": user_action_type,
                "feedback_text": feedback_text,
                "provided_inputs": provided_inputs or {},
                "origin_event_id": origin_event_id,
                "confirmed_at": _now().isoformat(),
            }
        )
        run.output_refs = {**output_refs, "confirmations": confirmations}
        return await self.transition(
            run,
            status=BrandIntelligenceRunStatus.FETCHING_ANSWERS.value,
            stage="fetching_answers",
            progress=max(run.progress, RUN_STAGE_PROGRESS["fetching_answers"]),
            message="已确认，正在继续采集 AI 回答",
            requires_user_action=False,
            user_action_type=None,
            blocking_reason=None,
            clear_error=True,
        )

    async def transition(
        self,
        run: BrandIntelligenceRun,
        *,
        status: str,
        stage: str,
        progress: float | None = None,
        message: str | None = None,
        sample_scope: dict[str, Any] | None = None,
        output_refs: dict[str, Any] | None = None,
        requires_user_action: bool | None = None,
        user_action_type: str | None = None,
        blocking_reason: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        clear_error: bool = False,
    ) -> BrandIntelligenceRun:
        if (
            run.status in BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES
            and status not in (run.status, BrandIntelligenceRunStatus.FAILED.value)
            and not (
                status == BrandIntelligenceRunStatus.COMPLETED.value
                and run.status
                in {
                    BrandIntelligenceRunStatus.CANCELLED.value,
                    BrandIntelligenceRunStatus.FAILED.value,
                }
            )
        ):
            return run
        now = _now()
        run.status = status
        run.stage = stage[:40]
        if progress is not None:
            run.progress = max(0.0, min(1.0, float(progress)))
        if message is not None:
            run.message = message[:255]
        if sample_scope is not None:
            run.sample_scope = sample_scope
        if output_refs is not None:
            run.output_refs = _merge_json(run.output_refs, output_refs)
        if requires_user_action is not None:
            run.requires_user_action = requires_user_action
        run.user_action_type = user_action_type
        run.blocking_reason = blocking_reason
        if clear_error:
            run.error_code = None
            run.error_message = None
            run.failed_at = None
        if error_code is not None:
            run.error_code = error_code
        if error_message is not None:
            run.error_message = error_message
        if status == BrandIntelligenceRunStatus.COMPLETED.value:
            run.completed_at = now
            run.requires_user_action = False
        if status == BrandIntelligenceRunStatus.CANCELLED.value:
            run.completed_at = run.completed_at or now
            run.requires_user_action = False
        if status == BrandIntelligenceRunStatus.FAILED.value:
            run.failed_at = now
        run.last_activity_at = now
        run.updated_at = now
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _resolve_snapshot_id(
        self,
        *,
        final_state: dict[str, Any],
        entity_id: UUID,
        session_id: UUID,
    ) -> UUID | None:
        raw_snapshot_id = final_state.get("snapshot_id")
        snapshot_id = _coerce_uuid(raw_snapshot_id, "snapshot_id")
        if snapshot_id is not None:
            return snapshot_id

        stmt = (
            select(AnalysisSnapshot.id)
            .where(
                AnalysisSnapshot.entity_id == entity_id,
                AnalysisSnapshot.session_id == session_id,
                AnalysisSnapshot.status.in_(
                    [SnapshotStatus.COMPLETED, SnapshotStatus.PARTIAL]
                ),
            )
            .order_by(desc(AnalysisSnapshot.created_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _sync_with_analysis_task(
        self,
        run: BrandIntelligenceRun | None,
    ) -> BrandIntelligenceRun | None:
        if run is None or run.analysis_task_id is None:
            return run
        if run.status == BrandIntelligenceRunStatus.COMPLETED.value:
            snapshot_id = _coerce_uuid(
                (run.output_refs or {}).get("snapshot_id"),
                "snapshot_id",
            )
            if snapshot_id is None:
                completed_task = await self.db.get(AnalysisTask, run.analysis_task_id)
                snapshot_id = completed_task.snapshot_id if completed_task else None
            await AmwayCircleTrackingService(
                self.db
            ).persist_completed_run_from_snapshot(run, snapshot_id)
            await self.db.commit()
            return run

        task = await self.db.get(AnalysisTask, run.analysis_task_id)
        if task is None:
            return run
        if (
            run.status in BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES
            and task.status != TaskStatus.COMPLETED
        ):
            return run

        status = run.status
        stage = run.stage
        progress = run.progress
        message = run.message
        output_refs = dict(run.output_refs or {})

        if task.status == TaskStatus.COMPLETED:
            status = BrandIntelligenceRunStatus.COMPLETED.value
            stage = "completed"
            progress = 1.0
            message = task.progress_message or "分析已完成"
            if task.snapshot_id:
                output_refs["snapshot_id"] = str(task.snapshot_id)
        elif task.status == TaskStatus.FAILED:
            status = BrandIntelligenceRunStatus.FAILED.value
            stage = str(task.error_stage or task.current_stage or "runtime")[:40]
            progress = run.progress
            message = task.error_message or "分析失败"
        elif task.status == TaskStatus.CANCELLED:
            status = BrandIntelligenceRunStatus.CANCELLED.value
            stage = "cancelled"
            progress = run.progress
            message = "已取消"
        elif task.status in {TaskStatus.PENDING, TaskStatus.RUNNING}:
            task_stage = str(task.current_stage or "").strip()
            status = TASK_STAGE_TO_RUN_STATUS.get(task_stage, run.status)
            stage = status
            progress = max(
                float(run.progress or 0.0),
                min(0.98, float(task.progress or 0.0)),
                RUN_STAGE_PROGRESS.get(status, 0.0),
            )
            message = task.progress_message or run.message

        changed = (
            run.status != status
            or run.stage != stage
            or abs(float(run.progress or 0.0) - float(progress or 0.0)) > 0.0001
            or run.message != message
            or run.output_refs != output_refs
        )
        if not changed:
            return run

        now = _now()
        run.status = status
        run.stage = stage[:40]
        run.progress = max(0.0, min(1.0, float(progress or 0.0)))
        run.message = (message or run.message or "")[:255]
        run.output_refs = output_refs
        run.last_activity_at = now
        run.updated_at = now
        if status == BrandIntelligenceRunStatus.COMPLETED.value:
            run.completed_at = run.completed_at or now
            run.requires_user_action = False
            await AmwayCircleTrackingService(
                self.db
            ).persist_completed_run_from_snapshot(run, task.snapshot_id)
        elif status == BrandIntelligenceRunStatus.FAILED.value:
            run.failed_at = run.failed_at or now
            run.error_code = run.error_code or "analysis_task_failed"
            run.error_message = run.error_message or message
        elif status == BrandIntelligenceRunStatus.CANCELLED.value:
            run.completed_at = run.completed_at or now
            run.requires_user_action = False

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _require_entity(
        self,
        entity_id: str | UUID,
        current_user: User,
    ) -> Entity:
        entity_uuid = _coerce_uuid(entity_id, "entity_id")
        entity = await EntityService(self.db).get_entity_model(
            str(entity_uuid),
            current_user,
            allow_internal_admin_bypass=False,
        )
        if entity is None:
            raise LookupError("Entity not found")
        return entity

    async def _find_by_origin_event(
        self,
        *,
        entity_id: UUID,
        origin_event_id: str,
    ) -> BrandIntelligenceRun | None:
        stmt = (
            select(BrandIntelligenceRun)
            .where(
                BrandIntelligenceRun.entity_id == entity_id,
                BrandIntelligenceRun.origin_event_id == origin_event_id,
            )
            .order_by(desc(BrandIntelligenceRun.created_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _get_run_unscoped(
        self,
        run_id: str | UUID,
    ) -> BrandIntelligenceRun | None:
        run_uuid = _coerce_uuid(run_id, "run_id")
        result = await self.db.execute(
            select(BrandIntelligenceRun).where(BrandIntelligenceRun.id == run_uuid)
        )
        return result.scalar_one_or_none()

    @staticmethod
    def to_dict(run: BrandIntelligenceRun | None) -> dict[str, Any] | None:
        if run is None:
            return None

        def dt(value: datetime | None) -> str | None:
            return value.isoformat() if value else None

        input_scope = run.input_scope if isinstance(run.input_scope, dict) else {}
        return {
            "id": str(run.id),
            "entity_id": str(run.entity_id),
            "created_by_user_id": (
                str(run.created_by_user_id) if run.created_by_user_id else None
            ),
            "origin_session_id": (
                str(run.origin_session_id) if run.origin_session_id else None
            ),
            "analysis_task_id": (
                str(run.analysis_task_id) if run.analysis_task_id else None
            ),
            "origin_surface": run.origin_surface,
            "origin_event_id": run.origin_event_id,
            "status": run.status,
            "stage": run.stage,
            "progress": run.progress,
            "message": run.message,
            "run_goal": run.run_goal,
            "analysis_mode": run.analysis_mode,
            "dashboard_variant": input_scope.get("dashboard_variant"),
            "center_terms": input_scope.get("center_terms"),
            "enabled_surfaces": input_scope.get("enabled_surfaces"),
            "input_scope": run.input_scope,
            "sample_scope": run.sample_scope,
            "output_refs": run.output_refs,
            "requires_user_action": run.requires_user_action,
            "user_action_type": run.user_action_type,
            "blocking_reason": run.blocking_reason,
            "error_code": run.error_code,
            "error_message": run.error_message,
            "started_at": dt(run.started_at),
            "completed_at": dt(run.completed_at),
            "failed_at": dt(run.failed_at),
            "last_activity_at": dt(run.last_activity_at),
            "created_at": dt(run.created_at),
            "updated_at": dt(run.updated_at),
        }


async def dispatch_brand_intelligence_run(run_id: str) -> None:
    """Run the workflow without requiring the user to keep Chat open."""

    try:
        run_uuid = UUID(str(run_id))
    except ValueError:
        logger.warning("[BrandRun] Invalid run_id for background dispatch: %s", run_id)
        return

    async with AsyncSessionLocal() as db:
        service = BrandIntelligenceRunService(db)
        run = await service._get_run_unscoped(run_uuid)
        if run is None or not run.analysis_task_id:
            return
        if run.status in BRAND_INTELLIGENCE_TERMINAL_RUN_STATUSES:
            return
        entity = await db.get(Entity, run.entity_id)
        task_run_id = (run.output_refs or {}).get("task_run_id")
        session_id = (run.output_refs or {}).get("session_id") or run.origin_session_id
        if entity is None or not task_run_id or not session_id:
            await service.transition(
                run,
                status=BrandIntelligenceRunStatus.FAILED.value,
                stage="runtime",
                message="后台任务缺少执行上下文",
                error_code="runtime_context_missing",
                error_message="Missing entity, session or task run reference",
            )
            return
        task_id = run.analysis_task_id
        task_run_uuid = UUID(str(task_run_id))
        session_uuid = UUID(str(session_id))
        await service.transition(
            run,
            status=BrandIntelligenceRunStatus.PLANNING_QUESTIONS.value,
            stage="planning_questions",
            progress=RUN_STAGE_PROGRESS["planning_questions"],
            message="正在生成问题和样本范围",
        )

    try:
        workflow = await get_compiled_workflow()
        lease_owner = f"brand-intelligence-run:{run_uuid}"
        async with AsyncSessionLocal() as db:
            await TaskService(db).start_task(
                task_id,
                run_id=task_run_uuid,
                lease_owner=lease_owner,
            )
            current_task = asyncio.current_task()
            if current_task is not None:
                await runtime_coordinator.register_local_execution(
                    session_id=str(session_uuid),
                    task_id=task_id,
                    run_id=task_run_uuid,
                    lease_owner=lease_owner,
                    execution_task=current_task,
                )

        initial_state = _build_brand_run_initial_state(
            run=run,
            entity=entity,
            session_uuid=session_uuid,
            task_id=task_id,
            task_run_uuid=task_run_uuid,
        )

        final_state = await workflow.ainvoke(
            initial_state,
            config={
                "configurable": {"thread_id": f"brand-intelligence-run:{run_uuid}"}
            },
        )

        async with AsyncSessionLocal() as db:
            service = BrandIntelligenceRunService(db)
            reloaded = await service._get_run_unscoped(run_uuid)
            if reloaded is None:
                return
            if final_state.get("awaiting_user") or final_state.get(
                "pending_confirmation"
            ):
                await TaskService(db).mark_waiting_for_input(
                    task_id,
                    run_id=task_run_uuid,
                    checkpoint_stage=str(final_state.get("current_step") or "runtime"),
                    progress=float(final_state.get("progress") or 0.5),
                    progress_message="需要用户确认后继续",
                )
                await service.transition(
                    reloaded,
                    status=BrandIntelligenceRunStatus.WAITING_USER.value,
                    stage=str(final_state.get("current_step") or "waiting_user"),
                    progress=float(final_state.get("progress") or 0.5),
                    message="需要确认后继续",
                    requires_user_action=True,
                    user_action_type="workflow_confirmation",
                    blocking_reason="需要用户确认或接管",
                    output_refs={
                        "pending_confirmation": final_state.get("pending_confirmation")
                    },
                )
                return

            snapshot_id = await service._resolve_snapshot_id(
                final_state=final_state,
                entity_id=run.entity_id,
                session_id=session_uuid,
            )
            if snapshot_id is None:
                await TaskService(db).fail_task(
                    task_id,
                    error_message="本轮分析没有生成可展示报告",
                    error_stage="analysis_report",
                    run_id=task_run_uuid,
                )
                await service.transition(
                    reloaded,
                    status=BrandIntelligenceRunStatus.FAILED.value,
                    stage="analysis_report",
                    message="分析完成但没有生成报告",
                    error_code="snapshot_missing",
                    error_message="Workflow finished without snapshot_id",
                )
                return

            circle_run = await AmwayCircleTrackingService(db).persist_completed_run(
                reloaded,
                final_state,
            )
            if (
                _normalize_mode(reloaded.analysis_mode)
                == BRAND_ASSOCIATION_CIRCLE_ANALYSIS_MODE
                and circle_run is None
            ):
                await TaskService(db).fail_task(
                    task_id,
                    error_message="本轮校准结果未写入品牌圈层历史",
                    error_stage="entity_calibration",
                    run_id=task_run_uuid,
                )
                await service.transition(
                    reloaded,
                    status=BrandIntelligenceRunStatus.FAILED.value,
                    stage="entity_calibration",
                    message="圈层历史写入失败，请重试",
                    error_code="circle_run_snapshot_missing",
                    error_message="Calibration completed without a circle run snapshot",
                )
                return
            await TaskService(db).complete_task(
                task_id,
                snapshot_id=snapshot_id,
                run_id=task_run_uuid,
            )
            await service.transition(
                reloaded,
                status=BrandIntelligenceRunStatus.COMPLETED.value,
                stage="completed",
                progress=1.0,
                message="分析已完成",
                output_refs={"snapshot_id": str(snapshot_id)},
            )
            try:
                BrandOntologyWorldService.invalidate_cache(run.entity_id)
                await BrandOntologyWorldService(db).ensure_legacy_backfill(
                    entity_id=run.entity_id
                )
            except Exception as projection_err:
                logger.warning(
                    "[BrandRun] World refresh failed for run %s: %s",
                    run_uuid,
                    projection_err,
                )
    except asyncio.CancelledError:
        logger.info("[BrandRun] Background run cancelled: %s", run_uuid)
        async with AsyncSessionLocal() as db:
            service = BrandIntelligenceRunService(db)
            reloaded = await service._get_run_unscoped(run_uuid)
            if reloaded is not None:
                task_service = TaskService(db)
                task_after_cancel = await task_service.finalize_cancel_if_requested(
                    task_id,
                    run_id=task_run_uuid,
                )
                if (
                    task_after_cancel is not None
                    and task_after_cancel.status == TaskStatus.COMPLETED
                    and task_after_cancel.snapshot_id is not None
                ):
                    await AmwayCircleTrackingService(
                        db
                    ).persist_completed_run_from_snapshot(
                        reloaded,
                        task_after_cancel.snapshot_id,
                    )
                    await service.transition(
                        reloaded,
                        status=BrandIntelligenceRunStatus.COMPLETED.value,
                        stage="completed",
                        progress=1.0,
                        message="分析已完成",
                        output_refs={"snapshot_id": str(task_after_cancel.snapshot_id)},
                    )
                    return
                if (
                    task_after_cancel is not None
                    and task_after_cancel.status == TaskStatus.CANCELLED
                ):
                    await service.transition(
                        reloaded,
                        status=BrandIntelligenceRunStatus.CANCELLED.value,
                        stage="cancelled",
                        message="已取消",
                        requires_user_action=False,
                        user_action_type=None,
                        blocking_reason=None,
                    )
                    return
                await service.transition(
                    reloaded,
                    status=BrandIntelligenceRunStatus.FAILED.value,
                    stage="background_interrupted",
                    message="后台执行中断，可继续分析",
                    error_code="background_interrupted",
                    error_message="Background execution was interrupted before completion",
                )
        raise
    except Exception as exc:
        logger.error("[BrandRun] Background run failed: %s", exc, exc_info=True)
        async with AsyncSessionLocal() as db:
            service = BrandIntelligenceRunService(db)
            reloaded = await service._get_run_unscoped(run_uuid)
            if reloaded is None:
                return
            await TaskService(db).fail_task(
                task_id,
                error_message=str(exc),
                error_stage="brand_run",
                run_id=task_run_uuid,
            )
            await service.transition(
                reloaded,
                status=BrandIntelligenceRunStatus.FAILED.value,
                stage="brand_run",
                message="分析失败，请重试",
                error_code="background_run_failed",
                error_message=str(exc),
            )
