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
import logging
from datetime import datetime, timezone
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.models.entity import Entity

logger = logging.getLogger(__name__)

# Maximum concurrent scheduled analyses
MAX_CONCURRENT_SCHEDULED = 3
POLL_INTERVAL_SECONDS = 60

_scheduler_task: asyncio.Task | None = None
_running_tasks: set[asyncio.Task] = set()
_concurrency_semaphore: asyncio.Semaphore | None = None


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
    _scheduler_task = asyncio.create_task(_scheduler_loop())
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
        logger.info(
            "[Scheduler] Cancelling %d running tasks...", len(_running_tasks)
        )
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
            await _process_due_schedules()
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

        logger.info(
            "[Scheduler] Found %d due schedules", len(due_schedules)
        )

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
    """Create a task and launch the pipeline for a scheduled analysis.

    If the schedule has baseline_data (from a previous successful run),
    pass it to the pipeline so it skips A1-A3 and only runs A4+A5 with
    the same questions. This enables meaningful trend comparison.
    """
    from app.services.monitoring_service import MonitoringService
    from app.services.task_service import TaskService

    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=schedule.user_id,
        session_id=None,
        brand_name=entity.name,
        entity_id=schedule.entity_id,
        monitoring_schedule_id=schedule.id,
    )

    monitoring_service = MonitoringService(db)
    await monitoring_service.record_run_started(schedule.id, task.id)

    # Load baseline (None on first run, dict on subsequent runs)
    baseline = schedule.baseline_data

    # Launch pipeline in background (semaphore-controlled)
    try:
        pipeline_task = asyncio.create_task(
            _run_pipeline_headless(
                task_id=task.id,
                entity_id=entity.id,
                entity_name=entity.name,
                entity_industry=getattr(entity, "industry", None),
                schedule_id=schedule.id,
                user_id=schedule.user_id,
                platforms=schedule.platforms,
                baseline=baseline,
            )
        )
    except Exception as e:
        # create_task failed (e.g. event loop closing) — mark run as failed
        logger.error(
            "[Scheduler] Failed to create pipeline task for schedule %s: %s",
            schedule.id,
            e,
            exc_info=True,
        )
        await monitoring_service.record_run_failed(schedule.id)
        from app.services.task_service import TaskService

        task_service = TaskService(db)
        await task_service.fail_task(
            task.id,
            error_message=f"Failed to launch pipeline: {e}",
            error_stage="scheduler",
        )
        return

    _running_tasks.add(pipeline_task)
    pipeline_task.add_done_callback(_running_tasks.discard)

    logger.info(
        "[Scheduler] Launched pipeline for schedule %s (task=%s, entity=%s)",
        schedule.id,
        task.id,
        entity.name,
    )


async def _run_pipeline_headless(
    task_id: UUID,
    entity_id: UUID,
    entity_name: str,
    entity_industry: str | None,
    schedule_id: UUID,
    user_id: UUID,
    platforms: list[str] | None = None,
    baseline: dict | None = None,
) -> None:
    """Run the analysis pipeline using the existing LangGraph compiled_workflow.

    If *baseline* is provided (from a previous successful run), the state is
    pre-filled with A1+A3 outputs and the orchestrator is instructed to jump
    directly to A4 (fetch) + A5 (analytics).  Otherwise a full A1→A5 run
    is executed and the baseline is saved on success.

    Uses a sentinel session_id ("headless-{task_id}") so all existing
    code paths function normally while WebSocket events gracefully degrade.
    """
    sem = _get_semaphore()

    async with sem:
        sentinel_session_id = f"headless-{task_id}"

        try:
            from app.workflow.graph import get_compiled_workflow

            workflow = await get_compiled_workflow()

            # --- Build initial state ---
            # Common fields shared by both first-run and baseline-run
            base_state = {
                "session_id": sentinel_session_id,
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
                "user_decisions": {},
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
                "platform_filter": platforms,
                "preserved_fetch_results": None,
                "auto_trigger_a5": False,
                # Baseline Analysis (Issue #4)
                "analysis_mode": None,
                "baseline_questions": None,
                "baseline_fetch_results": None,
                "baseline_metrics": None,
                "baseline_report": None,
                "headless_mode": True,
            }

            if baseline and baseline.get("questions"):
                # Subsequent run: pre-fill A1+A3 data, instruct orchestrator
                # to skip directly to A4 answer_fetch → A5 data_analytics
                n_questions = len(baseline["questions"])
                initial_state = {
                    **base_state,
                    "brand_profile": baseline.get("brand_profile"),
                    "competitors": baseline.get("competitors"),
                    "competitive_landscape": baseline.get("competitive_landscape"),
                    "marketing_personas": None,
                    "simulated_questions": baseline.get("simulated_questions"),
                    "questions": baseline["questions"],
                    "orchestrator_history": [{
                        "role": "user",
                        "content": (
                            f"这是定时监测任务。品牌「{entity_name}」已有"
                            f"{n_questions}组监测问题基线，"
                            f"请直接使用 answer_fetch 抓取最新AI答案，"
                            f"然后使用 data_analytics 生成分析报告。"
                        ),
                    }],
                }
                logger.info(
                    "[Scheduler] Baseline run for task %s: %d questions preloaded",
                    task_id, n_questions,
                )
            else:
                # First run: full A1→A5 pipeline with explicit instruction
                initial_state = {
                    **base_state,
                    "brand_profile": None,
                    "competitors": None,
                    "competitive_landscape": None,
                    "marketing_personas": None,
                    "simulated_questions": None,
                    "questions": None,
                    "orchestrator_history": [{
                        "role": "user",
                        "content": (
                            f"这是定时监测任务。请对品牌「{entity_name}」执行完整分析流程："
                            f"品牌分析 → 用户画像 → 问题模拟（品牌全景模式）"
                            f" → AI答案抓取 → 数据分析报告。无需确认，直接执行。"
                        ),
                    }],
                }
                logger.info(
                    "[Scheduler] First run for task %s: full pipeline (no baseline)",
                    task_id,
                )

            config = {"configurable": {"thread_id": sentinel_session_id}}

            logger.info(
                "[Scheduler] Starting pipeline for task %s (entity=%s)",
                task_id,
                entity_name,
            )

            # Mark task as running
            async with AsyncSessionLocal() as db:
                from app.services.task_service import TaskService

                ts = TaskService(db)
                await ts.start_task(task_id)

            # Invoke the same compiled workflow used by manual analyses
            final_state = await workflow.ainvoke(initial_state, config=config)

            # Handle completion
            await _handle_pipeline_success(
                task_id=task_id,
                entity_id=entity_id,
                schedule_id=schedule_id,
                user_id=user_id,
                final_state=final_state,
                is_first_run=baseline is None or not baseline.get("questions"),
            )

        except asyncio.CancelledError:
            logger.info(
                "[Scheduler] Pipeline task %s cancelled (shutdown)", task_id
            )
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
                schedule_id=schedule_id,
                error=str(e),
            )


async def _handle_pipeline_success(
    task_id: UUID,
    entity_id: UUID,
    schedule_id: UUID,
    user_id: UUID,
    final_state: dict,
    is_first_run: bool = False,
) -> None:
    """Handle successful pipeline completion for a scheduled run.

    On *is_first_run* (no baseline existed), extracts A1+A3 data from
    final_state and saves it as the schedule's baseline so subsequent
    runs can skip A1-A3 and only re-run A4+A5 with the same questions.
    """
    from app.services.alert_service import AlertService
    from app.services.monitoring_service import MonitoringService
    from app.services.snapshot_service import SnapshotService
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        monitoring_service = MonitoringService(db)
        snapshot_service = SnapshotService(db)

        # Extract metrics from final state
        metrics = final_state.get("metrics")
        report = final_state.get("report")
        fetch_results = final_state.get("fetch_results")
        questions = final_state.get("questions")

        snapshot_id = None
        if metrics:
            # Create snapshot with triggered_by="scheduled"
            snapshot = await snapshot_service.create_completed_snapshot(
                entity_id=entity_id,
                session_id=None,
                metrics=metrics,
                report_data=report or {},
                fetch_results_summary=(
                    [{"question_count": len(fetch_results)}]
                    if fetch_results
                    else None
                ),
                triggered_by="scheduled",
                snapshot_type=final_state.get("analysis_mode") or "baseline",
            )
            snapshot_id = snapshot.id

            # Generate alerts if schedule has alerting enabled
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

        # Save baseline on first successful run (when questions exist)
        if is_first_run and questions:
            # Double-check: baseline may have been saved by a concurrent run
            # or cleared by user during pipeline execution
            current_baseline = await monitoring_service.get_baseline(schedule_id)
            if current_baseline is not None:
                logger.info(
                    "[Scheduler] Baseline already exists for schedule %s, "
                    "skipping save (concurrent run or manual update)",
                    schedule_id,
                )
            else:
                baseline_data = {
                    "questions": questions,
                    "simulated_questions": final_state.get("simulated_questions"),
                    "brand_profile": final_state.get("brand_profile"),
                    "competitors": final_state.get("competitors"),
                    "competitive_landscape": final_state.get(
                        "competitive_landscape"
                    ),
                    "saved_at": datetime.now(timezone.utc).isoformat(),
                    "source_task_id": str(task_id),
                }
                await monitoring_service.save_baseline(
                    schedule_id, baseline_data
                )
                logger.info(
                    "[Scheduler] Saved baseline for schedule %s (%d questions)",
                    schedule_id, len(questions),
                )

        await task_service.complete_task(task_id, snapshot_id=snapshot_id)
        await monitoring_service.record_run_completed(schedule_id)

        logger.info(
            "[Scheduler] Pipeline completed for task %s (snapshot=%s, first_run=%s)",
            task_id,
            snapshot_id,
            is_first_run,
        )


async def _handle_pipeline_failure(
    task_id: UUID,
    schedule_id: UUID,
    error: str,
) -> None:
    """Handle pipeline failure for a scheduled run."""
    from app.services.monitoring_service import MonitoringService
    from app.services.task_service import TaskService

    async with AsyncSessionLocal() as db:
        task_service = TaskService(db)
        await task_service.fail_task(
            task_id,
            error_message=error,
            error_stage="pipeline",
        )

        monitoring_service = MonitoringService(db)
        await monitoring_service.record_run_failed(schedule_id)
