"""Lightweight async scheduler for monitoring schedules.

V1 Design: Single-process async loop using asyncio.create_task().
No external dependency (no APScheduler, no Celery, no Redis queue).

The scheduler starts on app startup and runs a poll loop every 60 seconds.
Due schedules create AnalysisTask instances and trigger the existing
LangGraph compiled_workflow in background async tasks.

Concurrency is controlled via asyncio.Semaphore to avoid overload.
"""

from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.entity import Entity
from app.models.monitoring_plan import MonitoringQuestionSet
from app.models.monitoring_schedule import MonitoringSchedule
from app.models.session import Session, SessionStatus
from app.models.task import AnalysisTask
from app.models.task_run import ExecutorKind, TaskTriggerSource
from app.services.runtime_coordinator import runtime_coordinator
from app.workflow.runtime_policy_executor import build_next_required_action

logger = logging.getLogger(__name__)

# Maximum concurrent scheduled analyses
MAX_CONCURRENT_SCHEDULED = 3
POLL_INTERVAL_SECONDS = 60
SCHEDULE_RUN_LEASE_TIMEOUT_SECONDS = 180

_scheduler_task: asyncio.Task | None = None
_running_tasks: set[asyncio.Task] = set()
_concurrency_semaphore: asyncio.Semaphore | None = None
_DEFAULT_MONITORING_PLATFORMS = ["doubao", "yuanbao", "kimi", "deepseek"]


def _parse_session_metadata(raw_metadata: str | None) -> dict:
    if not raw_metadata:
        return {}
    try:
        parsed = json.loads(raw_metadata)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_monitoring_session(session: Session | None) -> bool:
    if session is None:
        return False
    metadata = _parse_session_metadata(session.extra_metadata)
    return metadata.get("source") == "monitoring"


def _coerce_uuid(value: object) -> UUID | None:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _iter_schedule_source_session_candidates(
    schedule: MonitoringSchedule,
) -> list[UUID]:
    baseline = (
        schedule.baseline_data if isinstance(schedule.baseline_data, dict) else {}
    )
    raw_candidates = [
        baseline.get("source_session_id"),
        baseline.get("origin_session_id"),
        baseline.get("chat_session_id"),
    ]
    candidates: list[UUID] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        candidate = _coerce_uuid(raw)
        if candidate is None or str(candidate) in seen:
            continue
        candidates.append(candidate)
        seen.add(str(candidate))
    return candidates


async def _load_question_set_source_session_ids(
    db,
    *,
    schedule: MonitoringSchedule,
) -> list[UUID]:
    raw_ids = schedule.question_set_ids or []
    question_set_ids = [
        question_set_id
        for item in raw_ids
        if (question_set_id := _coerce_uuid(item)) is not None
    ]
    if not question_set_ids:
        return []

    result = await db.execute(
        select(MonitoringQuestionSet)
        .where(
            MonitoringQuestionSet.user_id == schedule.user_id,
            MonitoringQuestionSet.entity_id == schedule.entity_id,
            MonitoringQuestionSet.id.in_(question_set_ids),
        )
        .order_by(MonitoringQuestionSet.updated_at.desc())
    )
    candidates: list[UUID] = []
    seen: set[str] = set()
    for question_set in result.scalars().all():
        candidate = question_set.source_session_id
        if candidate is None or str(candidate) in seen:
            continue
        candidates.append(candidate)
        seen.add(str(candidate))
    return candidates


async def _get_valid_source_session(
    db,
    *,
    session_id: UUID,
    user_id: UUID,
    entity_id: UUID,
) -> Session | None:
    session = await db.get(Session, session_id)
    if (
        session is None
        or session.user_id != user_id
        or session.entity_id != entity_id
        or session.status == SessionStatus.ARCHIVED
        or _is_monitoring_session(session)
    ):
        return None
    session.status = SessionStatus.ACTIVE
    return session


async def resolve_monitoring_chat_session(
    db,
    *,
    schedule_id: UUID,
    user_id: UUID,
    entity_id: UUID,
    entity_name: str,
    schedule: MonitoringSchedule | None = None,
) -> Session:
    """Resolve the user-visible brand chat that scheduled runs should append to."""

    if schedule is not None:
        for candidate in _iter_schedule_source_session_candidates(schedule):
            session = await _get_valid_source_session(
                db,
                session_id=candidate,
                user_id=user_id,
                entity_id=entity_id,
            )
            if session is not None:
                return session

        for candidate in await _load_question_set_source_session_ids(
            db,
            schedule=schedule,
        ):
            session = await _get_valid_source_session(
                db,
                session_id=candidate,
                user_id=user_id,
                entity_id=entity_id,
            )
            if session is not None:
                return session

    stmt = (
        select(Session)
        .where(
            Session.user_id == user_id,
            Session.entity_id == entity_id,
            Session.status != SessionStatus.ARCHIVED,
        )
        .order_by(Session.updated_at.desc())
    )
    result = await db.execute(stmt)
    sessions = list(result.scalars().all())
    for session in sessions:
        if _is_monitoring_session(session):
            continue
        session.status = SessionStatus.ACTIVE
        return session

    session = Session(
        user_id=user_id,
        title=entity_name,
        status=SessionStatus.ACTIVE,
        entity_id=entity_id,
        extra_metadata=json.dumps(
            {
                "brand_name": entity_name,
                "source": "scheduled_monitoring_chat",
                "monitoring_schedule_id": str(schedule_id),
            },
            ensure_ascii=False,
        ),
    )
    db.add(session)
    await db.flush()
    return session


def _resolve_monitoring_platforms(platforms: list[str] | None) -> list[str]:
    resolved = [
        str(platform).strip().lower()
        for platform in (platforms or _DEFAULT_MONITORING_PLATFORMS)
        if str(platform).strip()
    ]
    return resolved or list(_DEFAULT_MONITORING_PLATFORMS)


def _normalize_intro_questions(questions: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for index, item in enumerate(questions or [], start=1):
        if not isinstance(item, dict):
            continue
        text = str(
            item.get("text") or item.get("question_text") or item.get("question") or ""
        ).strip()
        if not text:
            continue
        normalized.append(
            {
                "id": str(item.get("id") or item.get("question_id") or f"Q{index}"),
                "text": text,
                "category": item.get("category") or item.get("scene") or "",
                "intent": item.get("intent") or "",
                "stage": item.get("stage") or item.get("decision_stage") or "",
            }
        )
    return normalized


async def _persist_scheduled_run_intro(
    *,
    session_id: UUID,
    entity_name: str,
    schedule_id: UUID,
    run_id: UUID,
    monitor_mode: str,
    questions: list[dict] | None,
) -> None:
    """Append a visible scheduled-run intro and question artifact to the chat."""

    normalized_questions = _normalize_intro_questions(questions)
    async with AsyncSessionLocal() as db:
        from app.services.message_service import MessageService

        message_service = MessageService(db)
        await message_service.save_message(
            session_id=session_id,
            role="agent",
            content=(
                f"自动监测已触发。本轮将使用已确认的"
                f"{'全景' if monitor_mode == 'panorama' else '场景'}问题集，"
                "继续执行答案抓取与分析。"
            ),
            metadata={
                "triggered_by": "scheduled",
                "monitoring_schedule_id": str(schedule_id),
                "run_id": str(run_id),
                "message_kind": "scheduled_monitoring_intro",
            },
        )

    if not normalized_questions:
        return

    from app.workflow.events import save_and_send_artifact

    await save_and_send_artifact(
        session_id=str(session_id),
        output_type="questionList",
        title="自动监测问题列表",
        data={
            "simulatedQuestions": {
                "generation_mode": "scheduled_monitoring",
                "simulated_questions": normalized_questions,
                "generation_context": {
                    "triggered_by": "scheduled",
                    "monitoring_schedule_id": str(schedule_id),
                    "run_id": str(run_id),
                },
            },
            "questions": normalized_questions,
            "generationMode": "自动监测",
            "triggered_by": "scheduled",
            "monitoring": {
                "schedule_id": str(schedule_id),
                "run_id": str(run_id),
                "brand_name": entity_name,
            },
        },
        artifact_key=f"{session_id}_questionList_scheduled_{run_id}",
    )


def _get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore so it is created in the correct event loop."""
    global _concurrency_semaphore
    if _concurrency_semaphore is None:
        _concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCHEDULED)
    return _concurrency_semaphore


async def start_scheduler() -> None:
    """Start the scheduler background loop. Called from app startup."""
    global _scheduler_task
    if _scheduler_task is not None:
        return
    recovered = await _recover_stale_scheduler_runs(lease_timeout_seconds=0)
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    if recovered:
        logger.warning(
            "[Scheduler] Re-queued %d stale scheduled runs during startup recovery",
            recovered,
        )
    logger.info(
        "[Scheduler] Started with poll interval %ds, max concurrent %d",
        POLL_INTERVAL_SECONDS,
        MAX_CONCURRENT_SCHEDULED,
    )


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully. Called from app shutdown."""
    global _scheduler_task

    # Stop the poll loop
    if _scheduler_task is not None:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        _scheduler_task = None

    # Cancel all running pipeline tasks
    if _running_tasks:
        logger.info("[Scheduler] Cancelling %d running tasks...", len(_running_tasks))
        for task in _running_tasks:
            task.cancel()
        await asyncio.wait(_running_tasks, timeout=30.0)
        _running_tasks.clear()

    logger.info("[Scheduler] Stopped")


def get_scheduler_status() -> dict:
    """Return scheduler health info for the /health/scheduler endpoint."""
    return {
        "running": _scheduler_task is not None and not _scheduler_task.done(),
        "active_pipeline_count": len(_running_tasks),
        "max_concurrent": MAX_CONCURRENT_SCHEDULED,
        "semaphore_available": MAX_CONCURRENT_SCHEDULED - len(_running_tasks),
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
    }


async def _scheduler_loop() -> None:
    """Main scheduler poll loop.

    Every POLL_INTERVAL_SECONDS:
    1. Query due schedules
    2. Launch pipeline for each (within semaphore limit)
    3. Sleep
    """
    while True:
        try:
            await _recover_stale_scheduler_runs(
                lease_timeout_seconds=SCHEDULE_RUN_LEASE_TIMEOUT_SECONDS
            )
            await _process_due_schedules()
            await _dispatch_queued_runs()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("[Scheduler] Error in poll loop: %s", e, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _process_due_schedules() -> None:
    """Process all due monitoring schedules."""
    # Quick capacity check using actual running task count
    if len(_running_tasks) >= MAX_CONCURRENT_SCHEDULED:
        logger.debug(
            "[Scheduler] At capacity (%d/%d running), skipping poll",
            len(_running_tasks),
            MAX_CONCURRENT_SCHEDULED,
        )
        return

    from app.services.monitoring_service import MonitoringService

    async with AsyncSessionLocal() as db:
        monitoring_service = MonitoringService(db)
        due_schedules = await monitoring_service.get_due_schedules()

        if not due_schedules:
            return

        logger.info("[Scheduler] Found %d due schedules", len(due_schedules))

        for schedule in due_schedules:
            if len(_running_tasks) >= MAX_CONCURRENT_SCHEDULED:
                logger.info(
                    "[Scheduler] At capacity (%d/%d), deferring remaining schedules",
                    len(_running_tasks),
                    MAX_CONCURRENT_SCHEDULED,
                )
                break

            try:
                # Validate entity still exists
                entity = await db.get(Entity, schedule.entity_id)
                if entity is None:
                    logger.warning(
                        "[Scheduler] Entity %s not found for schedule %s, skipping",
                        schedule.entity_id,
                        schedule.id,
                    )
                    continue

                await _launch_scheduled_analysis(db, schedule, entity)
            except Exception as e:
                logger.error(
                    "[Scheduler] Failed to start schedule %s: %s",
                    schedule.id,
                    e,
                    exc_info=True,
                )


async def _launch_scheduled_analysis(db, schedule, entity) -> None:
    """Create a task and queue it for runtime dispatch.

    If the schedule has baseline_data (from a previous successful run),
    pass it to the pipeline so it skips A1-A3 and only runs A4+A5 with
    the same questions. This enables meaningful trend comparison.
    """
    from app.services.job_submission_service import JobSubmissionService

    monitoring_session = await resolve_monitoring_chat_session(
        db,
        schedule_id=schedule.id,
        user_id=schedule.user_id,
        entity_id=schedule.entity_id,
        entity_name=entity.name,
        schedule=schedule,
    )
    submission_service = JobSubmissionService(db)
    submitted = await submission_service.submit_scheduled_analysis(
        user_id=schedule.user_id,
        session_id=monitoring_session.id,
        brand_name=entity.name,
        entity_id=schedule.entity_id,
        monitoring_schedule_id=schedule.id,
    )
    task = submitted.task
    run = submitted.run

    logger.info(
        "[Scheduler] Queued scheduled run %s for schedule %s (task=%s, entity=%s)",
        run.id,
        schedule.id,
        task.id,
        entity.name,
    )


async def _dispatch_queued_runs() -> None:
    """Claim queued scheduler runs and launch them in background workers."""

    if len(_running_tasks) >= MAX_CONCURRENT_SCHEDULED:
        return

    from app.models.monitoring_schedule import MonitoringSchedule
    from app.services.job_dispatcher import JobDispatcher
    from app.services.monitoring_service import MonitoringService
    from app.services.task_service import TaskService

    while len(_running_tasks) < MAX_CONCURRENT_SCHEDULED:
        async with AsyncSessionLocal() as db:
            dispatcher = JobDispatcher(db)
            claimed = await dispatcher.claim_next_run(
                lease_owner="scheduler:dispatcher",
                executor_kind=ExecutorKind.LOCAL_WORKFLOW,
                trigger_source=TaskTriggerSource.SCHEDULER,
                executor_ref="scheduler:dispatcher",
            )
            if claimed is None:
                break

            task = await db.get(AnalysisTask, claimed.task_id)
            if task is None or task.monitoring_schedule_id is None:
                logger.warning(
                    "[Scheduler] Claimed run %s has no scheduled task context, failing",
                    claimed.id,
                )
                task_service = TaskService(db)
                await task_service.fail_task(
                    claimed.task_id,
                    error_message="Scheduled run is missing task context",
                    error_stage="sched_disp",
                    run_id=claimed.id,
                )
                continue

            schedule = await db.get(MonitoringSchedule, task.monitoring_schedule_id)
            entity = await db.get(Entity, task.entity_id) if task.entity_id else None
            if schedule is None or entity is None:
                logger.warning(
                    "[Scheduler] Claimed run %s missing schedule/entity, failing",
                    claimed.id,
                )
                task_service = TaskService(db)
                await task_service.fail_task(
                    task.id,
                    error_message="Scheduled run is missing schedule or entity",
                    error_stage="sched_disp",
                    run_id=claimed.id,
                )
                monitoring_service = MonitoringService(db)
                await monitoring_service.record_run_failed(task.monitoring_schedule_id)
                try:
                    from app.services.monitoring_plan_service import (
                        MonitoringPlanService,
                    )

                    await MonitoringPlanService(db).record_run_failed(
                        task_id=task.id,
                        error_message="Scheduled monitoring requires confirmed baseline questions",
                        error_stage="sched_base",
                    )
                except Exception as run_err:
                    logger.warning(
                        "[Scheduler] Failed to mark monitoring run failed: %s",
                        run_err,
                    )
                continue

            if task.session_id is None or _is_monitoring_session(
                await db.get(Session, task.session_id)
            ):
                monitoring_session = await resolve_monitoring_chat_session(
                    db,
                    schedule_id=schedule.id,
                    user_id=schedule.user_id,
                    entity_id=schedule.entity_id,
                    entity_name=entity.name,
                    schedule=schedule,
                )
                task.session_id = monitoring_session.id
                await db.commit()

            baseline = schedule.baseline_data
            if not baseline or not baseline.get("questions"):
                error_message = (
                    "Scheduled monitoring requires confirmed baseline questions"
                )
                logger.error(
                    "[Scheduler] Schedule %s missing baseline questions; refusing fast monitoring run",
                    schedule.id,
                )
                task_service = TaskService(db)
                await task_service.fail_task(
                    task.id,
                    error_message=error_message,
                    error_stage="sched_base",
                    run_id=claimed.id,
                )
                monitoring_service = MonitoringService(db)
                await monitoring_service.record_run_failed(task.monitoring_schedule_id)
                try:
                    from app.services.monitoring_plan_service import (
                        MonitoringPlanService,
                    )

                    await MonitoringPlanService(db).record_run_failed(
                        task_id=task.id,
                        error_message=error_message,
                        error_stage="sched_base",
                    )
                except Exception as run_err:
                    logger.warning(
                        "[Scheduler] Failed to mark monitoring run failed: %s",
                        run_err,
                    )
                continue

            lease_owner = claimed.lease_owner or "scheduler:dispatcher"
            monitoring_service = MonitoringService(db)
            await monitoring_service.record_run_started(schedule.id, task.id)
            try:
                from app.services.monitoring_plan_service import MonitoringPlanService

                await MonitoringPlanService(db).record_scheduler_run_started(
                    schedule=schedule,
                    task=task,
                    task_run_id=claimed.id,
                )
            except Exception as run_err:
                logger.warning(
                    "[Scheduler] Failed to mark monitoring run started: %s",
                    run_err,
                )
            platforms = _resolve_monitoring_platforms(schedule.platforms)
            entity_id = entity.id
            entity_name = entity.name
            entity_industry = getattr(entity, "industry", None)
            schedule_id = schedule.id
            user_id = schedule.user_id
            task_id = task.id
            run_id = claimed.id
            session_id = task.session_id
            monitor_mode = schedule.monitor_mode or "panorama"
            run_policy = schedule.run_policy or "quick"
            monitoring_plan_id = schedule.monitoring_plan_id
            question_set_ids = schedule.question_set_ids or []
            endpoint_ids = schedule.endpoint_ids or []

        try:
            pipeline_task = asyncio.create_task(
                _run_pipeline_headless(
                    task_id=task_id,
                    run_id=run_id,
                    session_id=session_id,
                    entity_id=entity_id,
                    entity_name=entity_name,
                    entity_industry=entity_industry,
                    schedule_id=schedule_id,
                    user_id=user_id,
                    platforms=platforms,
                    baseline=baseline,
                    monitor_mode=monitor_mode,
                    run_policy=run_policy,
                    monitoring_plan_id=monitoring_plan_id,
                    question_set_ids=question_set_ids,
                    endpoint_ids=endpoint_ids,
                    lease_owner=lease_owner,
                )
            )
        except Exception as e:
            logger.error(
                "[Scheduler] Failed to launch claimed run %s: %s",
                run_id,
                e,
                exc_info=True,
            )
            async with AsyncSessionLocal() as db:
                monitoring_service = MonitoringService(db)
                await monitoring_service.record_run_failed(schedule_id)
                task_service = TaskService(db)
                error_message = f"Failed to launch pipeline: {e}"
                await task_service.fail_task(
                    task_id,
                    error_message=error_message,
                    error_stage="sched_disp",
                    run_id=run_id,
                )
                try:
                    from app.services.monitoring_plan_service import (
                        MonitoringPlanService,
                    )

                    await MonitoringPlanService(db).record_run_failed(
                        task_id=task_id,
                        error_message=error_message,
                        error_stage="sched_disp",
                    )
                except Exception as run_err:
                    logger.warning(
                        "[Scheduler] Failed to mark monitoring run failed: %s",
                        run_err,
                    )
            continue

        _running_tasks.add(pipeline_task)
        pipeline_task.add_done_callback(_running_tasks.discard)
        logger.info(
            "[Scheduler] Dispatched claimed run %s for task %s",
            run_id,
            task_id,
        )


async def _recover_stale_scheduler_runs(*, lease_timeout_seconds: int) -> int:
    """Re-queue scheduled runs whose lease heartbeat expired."""

    from app.services.job_dispatcher import JobDispatcher

    async with AsyncSessionLocal() as db:
        dispatcher = JobDispatcher(db)
        recovered = await dispatcher.requeue_expired_runs(
            lease_timeout_seconds=lease_timeout_seconds,
            executor_kind=ExecutorKind.LOCAL_WORKFLOW,
            trigger_source=TaskTriggerSource.SCHEDULER,
        )
        if recovered:
            logger.warning(
                "[Scheduler] Re-queued %d stale scheduled runs (timeout=%ss)",
                recovered,
                lease_timeout_seconds,
            )
        return recovered


async def _run_pipeline_headless(
    task_id: UUID,
    run_id: UUID,
    session_id: UUID,
    entity_id: UUID,
    entity_name: str,
    entity_industry: str | None,
    schedule_id: UUID,
    user_id: UUID,
    platforms: list[str] | None = None,
    baseline: dict | None = None,
    monitor_mode: str = "panorama",
    run_policy: str = "quick",
    monitoring_plan_id: UUID | None = None,
    question_set_ids: list[str] | None = None,
    endpoint_ids: list[str] | None = None,
    lease_owner: str | None = None,
) -> None:
    """Run the analysis pipeline using the existing LangGraph compiled_workflow.

    If *baseline* is provided (from a previous successful run), the state is
    pre-filled with A1+A3 outputs and the orchestrator is instructed to jump
    directly to A4 (fetch) + A5 (analytics).  Otherwise a full A1→A5 run
    is executed and the baseline is saved on success.

    Uses a real monitoring session for artifact persistence while isolating
    each workflow run with a dedicated thread_id.
    """
    sem = _get_semaphore()

    async with sem:
        try:
            from app.workflow.graph import get_compiled_workflow

            workflow = await get_compiled_workflow()
            effective_lease_owner = lease_owner or f"scheduler:{schedule_id}"
            resolved_session_id = str(session_id)
            workflow_thread_id = f"monitoring:{session_id}:{run_id}"
            effective_platforms = _resolve_monitoring_platforms(platforms)
            effective_run_policy = str(run_policy or "quick").strip().lower()
            effective_fetch_mode = (
                "full" if effective_run_policy == "full_browser" else "fast"
            )
            effective_monitor_mode = str(monitor_mode or "panorama").strip().lower()
            effective_analysis_mode = (
                "persona" if effective_monitor_mode == "scenario" else "baseline"
            )

            # --- Build initial state ---
            base_state = {
                "session_id": resolved_session_id,
                "entity_id": str(entity_id),
                "brand_name": entity_name,
                "industry_hint": entity_industry,
                "official_website": None,
                "messages": [],
                "orchestrator_reply": None,
                "next_action": None,
                "awaiting_user": False,
                "tool_call_args": None,
                "tool_call_id": None,
                "agent_retry_counts": {},
                "user_decisions": {
                    "fetch_mode_confirmed": True,
                    "fetch_mode_pending": False,
                },
                "execution_status": "idle",
                "current_step": "",
                "progress": 0.0,
                "progress_message": "",
                "pending_confirmation": None,
                "error_info": None,
                "fetch_results": None,
                "metrics": None,
                "report": None,
                "task_id": str(task_id),
                "run_id": str(run_id),
                "monitoring_schedule_id": str(schedule_id),
                "monitoring_plan_id": (
                    str(monitoring_plan_id) if monitoring_plan_id else None
                ),
                "question_set_ids": question_set_ids or [],
                "endpoint_ids": endpoint_ids or [],
                "run_policy": effective_run_policy,
                "platform_filter": effective_platforms,
                "fetch_mode": effective_fetch_mode,
                "preserved_fetch_results": None,
                "next_required_action": build_next_required_action(
                    tool_name="answer_fetch",
                    authority="authoritative_resume",
                    reason="Scheduled monitoring runs A4/A5 from the confirmed monitoring plan baseline.",
                    tool_args={
                        "fetch_mode": effective_fetch_mode,
                        "platforms": effective_platforms,
                    },
                    source_step="scheduler_dispatch",
                    metadata={
                        "headless_mode": True,
                        "monitoring_schedule_id": str(schedule_id),
                        "monitoring_plan_id": (
                            str(monitoring_plan_id) if monitoring_plan_id else None
                        ),
                    },
                ),
                "analysis_mode": effective_analysis_mode,
                "baseline_questions": None,
                "baseline_fetch_results": None,
                "baseline_metrics": None,
                "baseline_report": None,
                "headless_mode": True,
            }

            initial_state = {
                **base_state,
                "brand_profile": baseline.get("brand_profile"),
                "competitors": baseline.get("competitors"),
                "competitive_landscape": baseline.get("competitive_landscape"),
                "marketing_personas": None,
                "simulated_questions": baseline.get("simulated_questions"),
                "questions": baseline.get("questions"),
                "orchestrator_history": [],
            }
            logger.info(
                "[Scheduler] Monitoring run for task %s: %s A4+A5 on %d confirmed questions",
                task_id,
                effective_monitor_mode,
                len(initial_state.get("questions") or []),
            )

            config = {"configurable": {"thread_id": workflow_thread_id}}

            logger.info(
                "[Scheduler] Starting pipeline for task %s (entity=%s, session=%s, thread=%s)",
                task_id,
                entity_name,
                resolved_session_id,
                workflow_thread_id,
            )

            # Claim the queued run, then mark task as running
            async with AsyncSessionLocal() as db:
                from app.services.task_service import TaskService

                ts = TaskService(db)
                await ts.start_task(
                    task_id,
                    run_id=run_id,
                    lease_owner=effective_lease_owner,
                )
                current_task = asyncio.current_task()
                if current_task is not None:
                    await runtime_coordinator.register_local_execution(
                        session_id=resolved_session_id,
                        task_id=task_id,
                        run_id=run_id,
                        lease_owner=effective_lease_owner,
                        execution_task=current_task,
                    )

            try:
                await _persist_scheduled_run_intro(
                    session_id=session_id,
                    entity_name=entity_name,
                    schedule_id=schedule_id,
                    run_id=run_id,
                    monitor_mode=effective_monitor_mode,
                    questions=initial_state.get("questions"),
                )
            except Exception as intro_err:
                logger.warning(
                    "[Scheduler] Failed to persist scheduled run intro: %s",
                    intro_err,
                    exc_info=True,
                )

            # Invoke the same compiled workflow used by manual analyses
            final_state = await workflow.ainvoke(initial_state, config=config)

            # Handle completion
            await _handle_pipeline_success(
                task_id=task_id,
                run_id=run_id,
                entity_id=entity_id,
                schedule_id=schedule_id,
                user_id=user_id,
                final_state=final_state,
            )

        except asyncio.CancelledError:
            logger.info("[Scheduler] Pipeline task %s cancelled (shutdown)", task_id)
            raise
        except Exception as e:
            logger.error(
                "[Scheduler] Pipeline failed for task %s: %s",
                task_id,
                e,
                exc_info=True,
            )
            await _handle_pipeline_failure(
                task_id=task_id,
                run_id=run_id,
                schedule_id=schedule_id,
                error=str(e),
            )


async def _handle_pipeline_success(
    task_id: UUID,
    run_id: UUID,
    entity_id: UUID,
    schedule_id: UUID,
    user_id: UUID,
    final_state: dict,
) -> None:
    """Handle successful pipeline completion for a scheduled run."""
    from app.services.alert_service import AlertService
    from app.services.monitoring_plan_service import MonitoringPlanService
    from app.services.monitoring_service import MonitoringService
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        monitoring_service = MonitoringService(db)
        snapshot_id_raw = final_state.get("snapshot_id")
        snapshot_id = UUID(snapshot_id_raw) if snapshot_id_raw else None

        if snapshot_id is not None:
            try:
                alert_service = AlertService(db)
                schedule = await monitoring_service.get_schedule(schedule_id)
                if schedule and schedule.alert_on_significant_change:
                    await alert_service.generate_alerts_for_snapshot(
                        entity_id=entity_id,
                        user_id=user_id,
                        schedule_id=schedule_id,
                        snapshot_id=snapshot_id,
                        threshold=schedule.alert_threshold_bwvs,
                    )
            except Exception as alert_err:
                logger.warning(
                    "[Scheduler] Alert generation failed for task %s: %s",
                    task_id,
                    alert_err,
                )
        if snapshot_id is None:
            error_message = "本次自动监测已结束，但没有生成可用于看板展示的报告。"
            logger.error(
                "[Scheduler] %s task=%s run=%s", error_message, task_id, run_id
            )
            await task_service.fail_task(
                task_id,
                error_message=error_message,
                error_stage="analysis_report",
                run_id=run_id,
            )
            await monitoring_service.record_run_failed(schedule_id)
            await MonitoringPlanService(db).record_run_failed(
                task_id=task_id,
                error_message=error_message,
                error_stage="analysis_report",
            )
            return

        await task_service.complete_task(
            task_id,
            snapshot_id=snapshot_id,
            run_id=run_id,
        )
        await monitoring_service.record_run_completed(schedule_id)
        await MonitoringPlanService(db).record_run_completed(
            task_id=task_id,
            snapshot_id=snapshot_id,
            final_state=final_state,
        )

        logger.info(
            "[Scheduler] Pipeline completed for task %s (snapshot=%s)",
            task_id,
            snapshot_id,
        )


async def _handle_pipeline_failure(
    task_id: UUID,
    run_id: UUID,
    schedule_id: UUID,
    error: str,
) -> None:
    """Handle pipeline failure for a scheduled run."""
    from app.services.monitoring_plan_service import MonitoringPlanService
    from app.services.monitoring_service import MonitoringService
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        await task_service.fail_task(
            task_id,
            error_message=error,
            error_stage="pipeline",
            run_id=run_id,
        )

        monitoring_service = MonitoringService(db)
        await monitoring_service.record_run_failed(schedule_id)
        await MonitoringPlanService(db).record_run_failed(
            task_id=task_id,
            error_message=error,
            error_stage="pipeline",
        )
