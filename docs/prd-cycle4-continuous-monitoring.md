# Cycle 4: Continuous Monitoring (Scheduled Analysis + Trend Tracking + Alerting)

> **Document Status**: Revised (v1.1)
> **Author**: Marty Cagan (Product Manager)
> **Created**: 2026-02-21
> **Last Updated**: 2026-02-21
> **Priority**: P2
> **Estimated Effort**: ~127h (16-18 working days, 3-4 weeks)
> **Dependency Documents**:
>   - `D:\AGEO\docs\reform-plan.md` (Reform Plan v2.0)
>   - `D:\AGEO\docs\prd-cycle3-multi-turn-async-quality.md` (Cycle 3 PRD)
>   - `D:\AGEO\docs\prd-cycle2-snapshot-report-wait.md` (Cycle 2 PRD)

> **v1.1 Revision Notes**:
> - Corrected headless pipeline design: reuse existing LangGraph workflow via `compiled_workflow.ainvoke()` with sentinel session_id (Section 2.6)
> - Replaced `_running_count` manual counter with `asyncio.Semaphore` (Section 2.6)
> - Added nullable `session_id` full impact audit (Section 2.7)
> - Resolved all 6 Open Questions (Section 13)
> - Added Scheduler health check endpoint (Section 2.9)
> - Added LLM API quota competition mitigation (Section 5.4)
> - Integrated UX design specifications for MonitoringTab, TrendChart, NotificationBell (Sections 8-9)
> - Updated effort estimate to ~127h
> - Added `platforms` field to MonitoringSchedule and `timezone` field for preferred_hour
> - Added SQLite `batch_alter_table` requirement for migrations
> - Added scheduler shutdown graceful cancellation

---

## 1. Background & Objectives

### 1.1 What Problem Are We Solving?

Cycles 1-3 built a solid single-shot analysis platform: users can chat to trigger brand analysis (A1-A5 pipeline), persist results as Snapshots, reconnect to running tasks, drill down into results, and compare two Snapshots manually. But the product still operates in a **reactive, on-demand model** -- the user must open the platform, start a conversation, and explicitly request an analysis every single time.

For enterprise brand management, this creates three critical gaps:

1. **No automated tracking**: Brand visibility in AI search engines changes constantly. Competitors launch new products, AI models get updated, content strategies evolve. Without automatic periodic analysis, brand teams miss critical shifts -- sometimes for weeks -- until someone remembers to manually check.

2. **No trend visibility**: While Cycle 2 introduced Snapshots and Cycle 3 added `compare_snapshots`, there is no structured way to visualize how BWVS and its sub-metrics change over time across multiple data points. Users can compare point A to point B, but cannot see a continuous trend line or identify patterns.

3. **No proactive alerting**: When a brand's BWVS drops 15 points because a competitor launched an aggressive campaign, or when sentiment shifts from positive to negative across AI platforms, nobody is notified. The brand team discovers the problem days later during a manual review.

### 1.2 Who Has This Problem? How Painful?

**Target User**: Brand marketing/operations managers responsible for ongoing AEO performance.

**Pain Severity**: Hair on fire for enterprise customers; nice-to-have for occasional users.

- **Automated tracking**: Marketing managers managing 3-10 brands cannot realistically run manual analyses weekly for each brand across 4 AI platforms. That is 3-10 chat sessions per week, each taking 1-5 minutes. They need a "set it and forget it" approach.
- **Trend visibility**: Without trends, every report feels isolated. Managers cannot answer "Is our brand visibility improving or declining?" -- the single most common question from CMOs.
- **Proactive alerting**: A 20% BWVS drop that goes unnoticed for 2 weeks can translate to real business impact. CMOs expect dashboards to flag issues proactively.

### 1.3 How Do They Solve It Today?

- **Manual scheduling**: Set calendar reminders to run analyses weekly. High friction, low compliance.
- **Spreadsheet tracking**: Manually copy BWVS scores into Excel after each analysis. Error-prone, no automation.
- **No alerting**: Review results manually on a periodic basis. Hope nothing bad happens between reviews.

### 1.4 Hypothesis & Expected Outcomes

**Hypothesis**: By enabling scheduled automatic analysis, continuous trend visualization, and anomaly alerting, we transform Specta AI from a "point-in-time analysis tool" into a "continuous brand monitoring platform" -- significantly increasing stickiness and enterprise value.

| Metric | Current | Target |
|--------|---------|--------|
| Analysis frequency per brand per month | 1-2 (manual) | 4-8 (automated weekly/biweekly) |
| Time to detect significant BWVS change | 1-2 weeks (manual review) | < 24 hours (automated alert) |
| Trend data points per brand | 1-3 (sporadic) | 8+ (weekly cadence, 2 months) |
| Dashboard engagement (return visits per week) | 0.5 (estimated) | 2-3 (driven by trend updates + alerts) |
| User retention at 30 days | Unknown (new product) | +30% improvement (hypothesis) |

### 1.5 Alignment with Reform Plan

This Cycle directly implements **P2-2 (Continuous Monitoring)** from the Reform Plan:

| Reform Plan Item | Cycle 4 Module | Coverage |
|-----------------|----------------|----------|
| P2-2: Scheduled tasks (weekly/monthly auto-analysis) | Module 1: Monitoring Schedules & Scheduler | Full |
| P2-2: Trend comparison (this period vs last period) | Module 2: Trend Engine & Change Detection | Full |
| P2-2: Alerting mechanism (anomaly notifications) | Module 3: Alerting & Notification | Full |

### 1.6 Alignment with Five Principles

| Principle | How This Cycle Aligns |
|-----------|-----------------------|
| 1. Full Feature Preservation | Adds capability on top of existing pipeline -- no feature removal |
| 2. 4 Platforms Full Coverage | Scheduled analysis uses the same A1-A5 pipeline covering all 4 AI platforms (default API-only, configurable) |
| 3. Performance via UX First | Scheduled tasks run in background; users get notified when done |
| 4. Protect Existing Code | Reuses AnalysisTask, Snapshot, pipeline nodes -- no refactoring |
| 5. Fix Fake Data, Keep Features | Builds on Cycle 1 real metrics (BWVS v2, sentiment, competitor) |

### 1.7 Linkage with Cycles 1-3

```
Cycle 1 (P0)           Cycle 2              Cycle 3 (P1)              Cycle 4 (this, P2)
-----------            -------              ------------              ------------------
BWVS v2 real metrics   Snapshot model        AnalysisTask model   -->  MonitoringSchedule model
Sentiment/competitor   Snapshot persistence   Task lifecycle       -->  Scheduler auto-creates tasks
Degradation handling   7-chapter report       Async notification   -->  Alert notification system
                                             compare_snapshots    -->  Trend engine (multi-point)
                                             Orphan recovery      -->  Scheduled task failure handling
```

Key dependencies on Cycle 3:
- **AnalysisTask model**: Scheduled runs create AnalysisTask instances (reuse, not duplicate)
- **TaskService**: Scheduled runs use the same lifecycle management (create -> start -> complete/fail)
- **Orphan task recovery**: Covers scheduled tasks that fail due to server restart
- **Snapshot model**: Each scheduled run generates a new Snapshot -- trend engine reads these

### 1.8 Chat-First Integration

Per the Reform Plan's core positioning, **continuous monitoring should be Chat-first**:

- **Setup via chat**: "Help me set up weekly monitoring for Xiaomi" -> Orchestrator creates a MonitoringSchedule. A confirmation step is presented before creation (e.g., "I will set up weekly monitoring for Xiaomi at 11:00 AM Beijing time with a 10-point BWVS alert threshold. Shall I proceed?").
- **Results delivered in chat**: When a scheduled analysis completes, the next time the user opens the relevant session, a summary message appears: "Weekly monitoring completed. BWVS: 52.3 (+3.1). No significant changes detected."
- **Alerts in chat**: "Alert: Your brand BWVS for Huawei dropped 12.5 points since last week. Would you like me to drill into the details?"
- **Dashboard as supplementary view**: The trend charts on Dashboard provide visual context, but the primary interaction remains conversational.
- **Dashboard editable**: Users can also edit schedule settings (frequency, threshold, pause/resume) directly from the Dashboard MonitoringTab for convenience.

---

## 2. Module 1: Monitoring Schedules & Scheduler

### 2.1 Problem Statement

Users need a way to configure automated periodic analysis for their brands. The system needs to execute these analyses on schedule without user intervention, reusing the existing A1-A5 pipeline and AnalysisTask infrastructure.

### 2.2 User Stories

- As a marketing manager, I want to tell the AI "set up weekly monitoring for Xiaomi" and have analyses run automatically every week.
- As a marketing manager, I want to see a list of all my active monitoring schedules and their next run times.
- As a marketing manager, I want to pause or stop a monitoring schedule when a campaign ends.
- As a marketing manager, I want each scheduled analysis to produce the same quality report as a manual analysis.

### 2.3 Success Metrics

- **Primary**: Scheduled analysis executes automatically within 15 minutes of the scheduled time
- **Secondary**: User can create, view, pause, resume, and delete monitoring schedules
- **Guardrail**: Scheduled runs do not degrade manual analysis performance or reliability

### 2.4 Data Model: MonitoringSchedule

**New file**: `aeo-platform/backend/app/models/monitoring_schedule.py`

```python
"""Monitoring Schedule model -- defines automated periodic analysis configuration."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.user import User


class ScheduleFrequency(str, PyEnum):
    """Monitoring frequency options."""
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class ScheduleStatus(str, PyEnum):
    """Schedule lifecycle status."""
    ACTIVE = "active"        # Actively scheduled
    PAUSED = "paused"        # Temporarily paused by user
    COMPLETED = "completed"  # Reached end_date or max_runs
    ERROR = "error"          # Too many consecutive failures


class MonitoringSchedule(Base):
    """Defines an automated periodic analysis configuration for a brand entity.

    Design notes:
    - One Entity can have at most ONE active schedule (enforced at service layer).
    - Each scheduled execution creates an AnalysisTask (via monitoring_schedule_id FK).
    - The scheduler reads active schedules and creates tasks when next_run_at <= now().
    - Chat-first: schedules can be created via natural language OR settings UI.
    """

    __tablename__ = "monitoring_schedules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Schedule configuration
    frequency: Mapped[ScheduleFrequency] = mapped_column(
        Enum(ScheduleFrequency),
        default=ScheduleFrequency.WEEKLY,
        nullable=False,
    )
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus),
        default=ScheduleStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # Preferred execution time (hour of day, 0-23)
    preferred_hour: Mapped[int] = mapped_column(
        Integer, default=3, nullable=False
    )  # Default: 3 (UTC), interpreted via timezone field

    # Timezone for preferred_hour interpretation (IANA timezone string)
    timezone: Mapped[str] = mapped_column(
        String(50), default="Asia/Shanghai", nullable=False
    )  # Default: Beijing time. preferred_hour=11 + timezone=Asia/Shanghai = 11 AM Beijing = 3 AM UTC

    # Platform configuration
    # JSON list of platform names to include in scheduled runs.
    # Default: ["doubao", "hunyuan"] (API-only for reliability).
    # Can be configured to include ["kimi", "deepseek"] for broader coverage.
    platforms: Mapped[list | None] = mapped_column(
        JSONText, nullable=True
    )  # None = use default API-only platforms ["doubao", "hunyuan"]

    # Alert configuration
    alert_on_significant_change: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    alert_threshold_bwvs: Mapped[float] = mapped_column(
        Float, default=10.0, nullable=False
    )  # Alert if BWVS changes by more than this absolute value

    # Execution tracking
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_tasks.id", ondelete="SET NULL"),
        nullable=True,
    )
    total_runs: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )

    # Optional limits
    max_runs: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # None = unlimited
    end_date: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="monitoring_schedules")
    entity: Mapped["Entity"] = relationship("Entity", backref="monitoring_schedules")
```

**AnalysisTask extension** -- add `monitoring_schedule_id` FK:

```python
# In app/models/task.py -- add to AnalysisTask

    # Link to monitoring schedule (null for manual analyses)
    monitoring_schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
```

**AnalysisSnapshot extension** -- `triggered_by` already supports "manual" / "scheduled":

The existing `triggered_by: Mapped[str]` field on AnalysisSnapshot will use `"scheduled"` for monitoring-triggered analyses. No schema change needed.

**Design Decisions**:

1. **One active schedule per entity**: Enforced at service layer. Prevents duplicate/conflicting schedules for the same brand. Users must pause/delete the existing one before creating a new one.
2. **Preferred hour + timezone**: Users think in "weekly on Monday mornings at 11 AM", not `0 3 * * 1`. The `preferred_hour` + `timezone` + `frequency` combination is sufficient for V1. The `timezone` field (IANA string, default `Asia/Shanghai`) allows correct local-time interpretation without cron complexity.
3. **No dedicated Session per scheduled run**: Scheduled analyses create AnalysisTask records that are NOT tied to any real Session. They use a sentinel `session_id` of the form `"headless-{task_id}"` in the AgentState so existing pipeline code paths execute normally. The results (Snapshots) are accessible via Dashboard trends and via chat ("show me my latest monitoring results").
4. **consecutive_failures auto-pause**: After 3 consecutive failures, the schedule transitions to `ERROR` status and user is notified. This prevents infinite retries of a fundamentally broken analysis.
5. **Configurable platforms**: The `platforms` field (JSON list) allows per-schedule platform selection. Default is API-only (`["doubao", "hunyuan"]`) for reliability. Users can opt into browser-based platforms (`["kimi", "deepseek"]`) for broader coverage, understanding the trade-off.
6. **Schedule limits**: Per-user limit of 10 active schedules. System-wide limit of 100 active schedules. Enforced at service layer during `create_schedule`.

### 2.5 MonitoringService

**New file**: `aeo-platform/backend/app/services/monitoring_service.py`

```python
"""Monitoring Schedule lifecycle management service."""

class MonitoringService:
    """Manages MonitoringSchedule CRUD, execution orchestration, and scheduling logic."""

    # Schedule limits
    MAX_SCHEDULES_PER_USER = 10
    MAX_SCHEDULES_GLOBAL = 100

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_schedule(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        frequency: ScheduleFrequency = ScheduleFrequency.WEEKLY,
        preferred_hour: int = 3,
        timezone: str = "Asia/Shanghai",
        platforms: list[str] | None = None,
        alert_on_significant_change: bool = True,
        alert_threshold_bwvs: float = 10.0,
        max_runs: int | None = None,
        end_date: datetime | None = None,
    ) -> MonitoringSchedule:
        """Create a new monitoring schedule.

        Validates:
        - Entity exists and belongs to user
        - No other ACTIVE schedule exists for this entity
        - preferred_hour is 0-23
        - timezone is a valid IANA timezone string
        - User has not exceeded MAX_SCHEDULES_PER_USER
        - System has not exceeded MAX_SCHEDULES_GLOBAL
        Calculates initial next_run_at based on frequency, preferred_hour, and timezone.
        """

    async def update_schedule(
        self,
        schedule_id: UUID,
        *,
        frequency: ScheduleFrequency | None = None,
        preferred_hour: int | None = None,
        timezone: str | None = None,
        platforms: list[str] | None = None,
        alert_on_significant_change: bool | None = None,
        alert_threshold_bwvs: float | None = None,
    ) -> MonitoringSchedule | None:
        """Update schedule configuration. Recalculates next_run_at if frequency changes."""

    async def pause_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Pause an active schedule. Sets status=PAUSED, clears next_run_at."""

    async def resume_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Resume a paused schedule. Recalculates next_run_at from now."""

    async def delete_schedule(self, schedule_id: UUID) -> bool:
        """Soft-delete or hard-delete a schedule."""

    async def get_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Get a single schedule by ID."""

    async def get_entity_schedule(self, entity_id: UUID) -> MonitoringSchedule | None:
        """Get the active/paused schedule for an entity (at most one)."""

    async def list_user_schedules(
        self,
        user_id: UUID,
        *,
        status: ScheduleStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MonitoringSchedule], int]:
        """List all schedules for a user, optionally filtered by status."""

    async def get_due_schedules(self) -> list[MonitoringSchedule]:
        """Get all ACTIVE schedules where next_run_at <= now().

        Called by the scheduler loop. Returns schedules ordered by next_run_at ASC.
        """

    async def record_run_started(
        self, schedule_id: UUID, task_id: UUID
    ) -> None:
        """Record that a scheduled run has started.

        Updates: last_run_at, last_task_id, total_runs += 1,
                 calculates and sets next_run_at.
        Checks: max_runs / end_date -> transitions to COMPLETED if limit reached.
        """

    async def record_run_completed(self, schedule_id: UUID) -> None:
        """Record successful completion. Resets consecutive_failures to 0."""

    async def record_run_failed(self, schedule_id: UUID) -> None:
        """Record failure. Increments consecutive_failures.
        If consecutive_failures >= 3, transitions to ERROR status.
        """

    @staticmethod
    def calculate_next_run(
        frequency: ScheduleFrequency,
        preferred_hour: int,
        timezone: str = "Asia/Shanghai",
        from_time: datetime | None = None,
    ) -> datetime:
        """Calculate the next run time based on frequency, preferred hour, and timezone.

        DAILY:    next day at preferred_hour (in specified timezone)
        WEEKLY:   next week same day at preferred_hour
        BIWEEKLY: two weeks from now at preferred_hour
        MONTHLY:  next month same date at preferred_hour

        Returns a timezone-aware datetime in UTC.
        """
```

### 2.6 Scheduler Engine

**New file**: `aeo-platform/backend/app/services/scheduler.py`

The scheduler is a lightweight async loop that runs inside the FastAPI process (no external dependency like Celery needed for V1).

**Critical Design Decision -- Reuse Existing LangGraph Workflow**:

The headless pipeline **reuses the existing `compiled_workflow` from `app/workflow/graph.py`** by calling `compiled_workflow.ainvoke(initial_state, config)` directly. This is the same workflow that runs for manual (session-based) analyses.

**Rationale for NOT creating a separate "fixed-order pipeline runner"**:
1. The Orchestrator has been validated through E2E testing (Round 12: 6 PASS, full_pipeline coverage A1->A2->A3->A4->A5, 5/5).
2. Maintaining two separate pipeline execution paths (Orchestrator-based and fixed-order) would cause code divergence and maintenance burden.
3. The Orchestrator's LLM function calling token cost is negligible compared to the A1-A5 agent calls themselves.
4. Using the same pipeline ensures scheduled runs produce identical quality results to manual runs.
5. This reduces headless pipeline implementation from ~14h to **5-6h**.

**WebSocket graceful degradation**:
- `emit_to_session()` in `websocket_server.py` already returns silently when no connections exist for a session_id (`if session_id not in self.session_connections: return`). No modification needed.
- `save_and_send_artifact()` needs a conditional branch: when `session_id` starts with `"headless-"`, skip Message persistence (no valid session FK) and rely solely on Snapshot persistence. The `send_output_ready()` call will be a no-op since no WebSocket client is connected.
- AgentState uses a sentinel `session_id` of the form `"headless-{task_id}"` so all existing code paths that reference `state["session_id"]` continue to function.

```python
"""Lightweight async scheduler for monitoring schedules.

V1 Design: Single-process async loop using asyncio.create_task().
No external dependency (no APScheduler, no Celery, no Redis queue).

Rationale:
- The expected volume is low (<100 concurrent schedules in V1).
- The existing pipeline already runs as an async Python coroutine.
- APScheduler would add a dependency for minimal benefit at this scale.
- Celery integration is deferred until we need multi-process scalability.

The scheduler starts on app startup and runs a poll loop every 60 seconds.
Due schedules create AnalysisTask instances and trigger the existing
LangGraph compiled_workflow in background async tasks.

Concurrency is controlled via asyncio.Semaphore to avoid race conditions.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.database import AsyncSessionLocal
from app.services.monitoring_service import MonitoringService
from app.services.task_service import TaskService
from app.workflow.graph import get_compiled_workflow

logger = logging.getLogger(__name__)

# Maximum concurrent scheduled analyses
MAX_CONCURRENT_SCHEDULED = 3
POLL_INTERVAL_SECONDS = 60

_scheduler_task: asyncio.Task | None = None
_running_tasks: set[asyncio.Task] = set()  # Track running pipeline tasks for shutdown
_concurrency_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCHEDULED)


async def start_scheduler() -> None:
    """Start the scheduler background loop. Called from app startup."""
    global _scheduler_task
    if _scheduler_task is not None:
        return
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("[Scheduler] Started with poll interval %ds, max concurrent %d",
                POLL_INTERVAL_SECONDS, MAX_CONCURRENT_SCHEDULED)


async def stop_scheduler() -> None:
    """Stop the scheduler gracefully. Called from app shutdown.

    1. Cancel the poll loop task.
    2. Cancel all running pipeline tasks.
    3. Wait for cancellation to complete (with timeout).
    """
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
        # Wait for all tasks to finish (with 30s timeout)
        await asyncio.wait(_running_tasks, timeout=30.0)
        _running_tasks.clear()

    logger.info("[Scheduler] Stopped")


def get_scheduler_status() -> dict:
    """Return scheduler health info for the /health/scheduler endpoint."""
    return {
        "running": _scheduler_task is not None and not _scheduler_task.done(),
        "active_pipeline_count": len(_running_tasks),
        "max_concurrent": MAX_CONCURRENT_SCHEDULED,
        "semaphore_available": _concurrency_semaphore._value,
        "poll_interval_seconds": POLL_INTERVAL_SECONDS,
    }


async def _scheduler_loop() -> None:
    """Main scheduler poll loop.

    Every POLL_INTERVAL_SECONDS:
    1. Query MonitoringSchedule where status=ACTIVE and next_run_at <= now()
    2. For each due schedule (respecting semaphore concurrency limit):
       a. Create an AnalysisTask (triggered_by="scheduled", sentinel session_id)
       b. Launch the LangGraph compiled_workflow as a background async task
       c. Update schedule.last_run_at and schedule.next_run_at
    3. Sleep
    """
    while True:
        try:
            await _process_due_schedules()
        except Exception as e:
            logger.error("[Scheduler] Error in poll loop: %s", e, exc_info=True)

        await asyncio.sleep(POLL_INTERVAL_SECONDS)


async def _process_due_schedules() -> None:
    """Process all due monitoring schedules."""
    # Check if we have any capacity before querying DB
    if _concurrency_semaphore.locked():
        logger.debug("[Scheduler] At capacity (%d running), skipping poll",
                     len(_running_tasks))
        return

    async with AsyncSessionLocal() as db:
        monitoring_service = MonitoringService(db)
        due_schedules = await monitoring_service.get_due_schedules()

        for schedule in due_schedules:
            if _concurrency_semaphore.locked():
                break

            try:
                # Validate entity still exists before launching
                entity = await db.get(Entity, schedule.entity_id)
                if entity is None:
                    logger.warning(
                        "[Scheduler] Entity %s not found for schedule %s, skipping",
                        schedule.entity_id, schedule.id,
                    )
                    continue

                await _launch_scheduled_analysis(db, schedule, entity)
            except Exception as e:
                logger.error(
                    "[Scheduler] Failed to start schedule %s: %s",
                    schedule.id, e, exc_info=True,
                )


async def _launch_scheduled_analysis(db, schedule, entity) -> None:
    """Create a task and launch the pipeline for a scheduled analysis.

    Pipeline execution reuses the existing LangGraph compiled_workflow:
    1. Create AnalysisTask with monitoring_schedule_id (no real session)
    2. Build initial_state with sentinel session_id = "headless-{task_id}"
    3. Invoke compiled_workflow.ainvoke(initial_state, config)
    4. On completion: update task, create Snapshot, check for alerts
    5. On failure: record failure on schedule, notify if consecutive

    WebSocket events gracefully degrade:
    - emit_to_session() returns silently (no connections for sentinel session_id)
    - save_and_send_artifact() skips Message persistence for headless sessions
    """
    # Create AnalysisTask (headless -- sentinel session_id, NOT null)
    task_service = TaskService(db)
    task = await task_service.create_task(
        user_id=schedule.user_id,
        session_id=None,  # Nullable session_id for scheduled tasks
        brand_name=entity.name,
        entity_id=schedule.entity_id,
        monitoring_schedule_id=schedule.id,
    )

    monitoring_service = MonitoringService(db)
    await monitoring_service.record_run_started(schedule.id, task.id)

    # Launch pipeline in background (semaphore-controlled)
    pipeline_task = asyncio.create_task(
        _run_pipeline_headless(
            task_id=task.id,
            entity=entity,
            schedule_id=schedule.id,
            user_id=schedule.user_id,
            platforms=schedule.platforms,
        )
    )
    _running_tasks.add(pipeline_task)
    pipeline_task.add_done_callback(_running_tasks.discard)


async def _run_pipeline_headless(
    task_id, entity, schedule_id, user_id, platforms=None
) -> None:
    """Run the A1-A5 pipeline using the existing LangGraph compiled_workflow.

    Uses a sentinel session_id ("headless-{task_id}") so that:
    - All agent nodes can reference state["session_id"] without modification
    - emit_to_session() silently returns (no WebSocket clients for this ID)
    - save_and_send_artifact() detects the "headless-" prefix and skips
      Message persistence (no valid session FK), relying on Snapshot only

    On completion:
    - Creates Snapshot with triggered_by="scheduled"
    - Calls MonitoringService.record_run_completed()
    - Invokes change detection (Module 2) against previous snapshot
    - If significant change detected, creates alert (Module 3)

    On failure:
    - Calls TaskService.fail_task()
    - Calls MonitoringService.record_run_failed()
    """
    async with _concurrency_semaphore:
        try:
            sentinel_session_id = f"headless-{task_id}"
            workflow = get_compiled_workflow()

            # Build initial state matching the manual analysis pattern
            # (see websocket_langgraph.py for reference)
            initial_state = {
                "session_id": sentinel_session_id,
                "user_id": str(user_id),
                "entity_id": str(entity.id),
                "brand_name": entity.name,
                "industry": getattr(entity, "industry", None),
                "messages": [],
                "orchestrator_history": [],
                "execution_status": "idle",
                "awaiting_user": False,
                "user_decisions": {},
                "platform_filter": platforms,  # Use schedule-configured platforms
                "baseline_fetch_results": None,
            }

            config = {"configurable": {"thread_id": sentinel_session_id}}

            # Invoke the same compiled workflow used by manual analyses
            final_state = await workflow.ainvoke(initial_state, config=config)

            # Handle completion
            async with AsyncSessionLocal() as db:
                task_service = TaskService(db)
                await task_service.complete_task(task_id, snapshot_id=...)

                monitoring_service = MonitoringService(db)
                await monitoring_service.record_run_completed(schedule_id)

                # Generate alerts if significant changes detected
                alert_service = AlertService(db)
                await alert_service.generate_alerts_for_snapshot(
                    entity_id=entity.id,
                    schedule_id=schedule_id,
                    snapshot_id=...,  # From final_state or Snapshot query
                )

        except asyncio.CancelledError:
            logger.info("[Scheduler] Pipeline task %s cancelled (shutdown)", task_id)
            raise
        except Exception as e:
            logger.error("[Scheduler] Pipeline failed for task %s: %s",
                        task_id, e, exc_info=True)
            async with AsyncSessionLocal() as db:
                task_service = TaskService(db)
                await task_service.fail_task(task_id, str(e), error_stage="pipeline")

                monitoring_service = MonitoringService(db)
                await monitoring_service.record_run_failed(schedule_id)
```

**Integration with app startup**:

```python
# In app/main.py -- on_startup addition

from app.services.scheduler import start_scheduler, stop_scheduler

@app.on_event("startup")
async def on_startup():
    # ... existing startup logic ...
    await start_scheduler()

@app.on_event("shutdown")
async def on_shutdown():
    await stop_scheduler()
```

**`save_and_send_artifact` conditional branch for headless mode**:

```python
# In app/workflow/events.py -- modify save_and_send_artifact

async def save_and_send_artifact(
    session_id: str,
    output_type: str,
    title: str,
    data: dict,
    related_message_id: str | None = None,
) -> str:
    """Save artifact to DB and send to frontend via WebSocket.

    For headless sessions (session_id starts with "headless-"):
    - Skip Message persistence (no valid session FK)
    - Skip WebSocket send (no connected client)
    - Rely on Snapshot persistence for data durability
    - Return empty string as output_id
    """
    # Headless mode: skip Message save, rely on Snapshot only
    if session_id.startswith("headless-"):
        logger.info(f"[Artifact] Headless mode, skipping Message save: {title}")
        return ""

    # ... existing implementation unchanged ...
```

**Design Decisions**:

1. **No APScheduler for V1**: The expected volume (< 100 schedules) does not justify the added dependency. A simple `asyncio` poll loop with 60-second intervals is sufficient. APScheduler or Celery Beat can be introduced if scale demands it.
2. **`asyncio.Semaphore` for concurrency control**: Replaces a manual `_running_count` counter. The Semaphore guarantees atomic acquire/release without race conditions in concurrent asyncio code. `MAX_CONCURRENT_SCHEDULED = 3` limits resource consumption.
3. **Reuse existing LangGraph compiled_workflow**: Scheduled runs invoke the same `compiled_workflow.ainvoke()` as manual analyses. No separate "fixed-order pipeline runner" is created. This ensures code path parity and eliminates divergence risk.
4. **Sentinel session_id (`"headless-{task_id}"`)**: Avoids making `session_id` truly null in AgentState (which would require auditing every state access). The sentinel value allows all existing code to function normally while WebSocket events gracefully degrade.
5. **Nullable session_id on AnalysisTask**: The database model allows `NULL` for `session_id` on AnalysisTask, distinguishing headless tasks. But the pipeline's AgentState always has a string session_id (the sentinel).
6. **Entity existence check**: Before launching a pipeline, the scheduler verifies the entity still exists. If deleted (CASCADE would clean up the schedule too), the check is a safety net.
7. **Graceful shutdown**: `stop_scheduler()` cancels both the poll loop and all running pipeline tasks, with a 30-second timeout for cleanup.
8. **Tracked running tasks**: `_running_tasks` set enables both shutdown cleanup and health monitoring.

### 2.7 AnalysisTask Schema Change & Nullable session_id Impact Audit

The current AnalysisTask model has `session_id` as NOT NULL. For scheduled (headless) tasks, we need to make it nullable:

```python
# Modified: app/models/task.py

    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=True,  # Changed from False -> True for scheduled tasks
        index=True,
    )

    # Relationship must declare Optional type
    session: Mapped["Session | None"] = relationship(
        "Session", back_populates="tasks"
    )
```

**Full impact audit of nullable `session_id`**:

| Location | Current Behavior | Required Change | Risk |
|----------|-----------------|-----------------|------|
| `TaskService.get_session_active_task()` | Filters by session_id | No change needed (filters by specific session_id value) | None |
| `TaskService.list_tasks()` | Optional session_id filter | No change needed (filter is already optional) | None |
| `TaskService.create_task()` | Requires session_id | Make parameter optional, default None | Low |
| `task_to_dict()` / task serialization | `str(task.session_id)` | **Fix**: `str(task.session_id) if task.session_id else None` to avoid `str(None)` = `"None"` | **Medium** -- must fix |
| Session.tasks relationship | Expects all tasks to have session_id | Add `Mapped["Session \| None"]` on Task side; Session backref naturally excludes NULL FK tasks | Low |
| Frontend task list | Displays tasks with session context | Add UI differentiation: headless tasks show "Scheduled" badge instead of session link. Group/filter by `session_id IS NULL` | **Medium** |
| Orphan task recovery (Cycle 3) | Queries tasks by session_id | Exclude headless tasks from orphan recovery (they have their own failure handling via MonitoringService) | Low |
| `websocket_langgraph.py` | Accesses `task.session_id` for routing | No change -- manual analysis tasks always have session_id | None |

**Alembic migration notes**:

```python
# Migration for AnalysisTask.session_id nullable change

def upgrade():
    # SQLite requires batch mode for ALTER COLUMN
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.alter_column("session_id", nullable=True)
        batch_op.add_column(
            sa.Column("monitoring_schedule_id", UUID(as_uuid=True),
                      sa.ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
                      nullable=True, index=True)
        )

def downgrade():
    with op.batch_alter_table("analysis_tasks") as batch_op:
        batch_op.drop_column("monitoring_schedule_id")
        batch_op.alter_column("session_id", nullable=False)
```

**Important**: All Alembic migrations in this cycle MUST use `op.batch_alter_table()` for SQLite compatibility. PostgreSQL handles `ALTER COLUMN` natively, but SQLite requires table recreation via batch mode.

### 2.8 Orchestrator Tool: create_monitoring

To support Chat-first schedule creation, add a new tool to the Orchestrator:

```python
# orchestrator_node.py -- AGENT_REGISTRY addition

{
    "name": "create_monitoring_schedule",
    "description": (
        "Create a scheduled monitoring plan for a brand entity. "
        "Examples: 'Monitor Xiaomi weekly', 'Set up monthly tracking for Huawei'. "
        "REQUIRES: An entity_id in the current session (brand must have been analyzed at least once). "
        "Creates a recurring schedule that automatically runs the full analysis pipeline."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "frequency": {
                "type": "string",
                "description": "'daily', 'weekly' (default), 'biweekly', or 'monthly'",
            },
            "preferred_hour": {
                "type": "integer",
                "description": "Preferred hour of day to run (0-23 in user's timezone). Default: 11.",
            },
            "alert_threshold": {
                "type": "number",
                "description": "BWVS change threshold for alerts. Default: 10.0.",
            },
        },
    },
},
```

**New node**: `create_monitoring_node` in `nodes_monitoring.py`:

```python
async def create_monitoring_node(state: AgentState) -> Command:
    """Create a monitoring schedule via chat command.

    Includes a confirmation step before creation to verify settings with user.
    """
    entity_id = state.get("entity_id")
    if not entity_id:
        # Guide user to analyze a brand first
        msg = "Please complete a brand analysis first so I know which brand to monitor."
        await send_reply_event(state["session_id"], msg, ...)
        return Command(update={"execution_status": "completed"})

    tool_args = state.get("tool_call_args") or {}
    frequency = tool_args.get("frequency", "weekly")
    preferred_hour = tool_args.get("preferred_hour", 11)

    async with AsyncSessionLocal() as db:
        service = MonitoringService(db)
        schedule = await service.create_schedule(
            user_id=state["user_id"],
            entity_id=UUID(entity_id),
            frequency=ScheduleFrequency(frequency),
            preferred_hour=preferred_hour,
            alert_threshold_bwvs=tool_args.get("alert_threshold", 10.0),
        )

    freq_label = {"daily": "every day", "weekly": "every week",
                  "biweekly": "every two weeks", "monthly": "every month"}
    msg = (
        f"Monitoring schedule created. I will automatically analyze "
        f"{state.get('brand_name', 'this brand')} {freq_label.get(frequency, frequency)}. "
        f"You will be notified if the BWVS changes by more than "
        f"{tool_args.get('alert_threshold', 10.0)} points."
    )
    await send_reply_event(state["session_id"], msg, ...)
    return Command(update={"execution_status": "completed"})
```

### 2.9 Monitoring Schedule API

**New file**: `aeo-platform/backend/app/api/v1/monitoring.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/monitoring/schedules` | Create a monitoring schedule |
| GET | `/api/v1/monitoring/schedules` | List user's monitoring schedules |
| GET | `/api/v1/monitoring/schedules/{id}` | Get schedule details |
| PATCH | `/api/v1/monitoring/schedules/{id}` | Update schedule configuration |
| POST | `/api/v1/monitoring/schedules/{id}/pause` | Pause a schedule |
| POST | `/api/v1/monitoring/schedules/{id}/resume` | Resume a schedule |
| DELETE | `/api/v1/monitoring/schedules/{id}` | Delete a schedule |
| GET | `/api/v1/monitoring/schedules/{id}/history` | Get task history for a schedule |

**Scheduler health check endpoint**:

```python
# In app/api/v1/monitoring.py or a new app/api/v1/health.py

@router.get("/health/scheduler")
async def get_scheduler_health():
    """Return scheduler operational status.

    Response:
    {
        "running": true,
        "active_pipeline_count": 2,
        "max_concurrent": 3,
        "semaphore_available": 1,
        "poll_interval_seconds": 60
    }

    Used by ops monitoring and frontend health indicators.
    """
    from app.services.scheduler import get_scheduler_status
    return get_scheduler_status()
```

**Schedule response**:

```json
{
  "id": "uuid",
  "entity_id": "uuid",
  "entity_name": "Xiaomi",
  "frequency": "weekly",
  "status": "active",
  "preferred_hour": 11,
  "timezone": "Asia/Shanghai",
  "platforms": ["doubao", "hunyuan"],
  "alert_on_significant_change": true,
  "alert_threshold_bwvs": 10.0,
  "next_run_at": "2026-02-28T03:00:00Z",
  "last_run_at": "2026-02-21T03:00:00Z",
  "last_task_id": "uuid",
  "total_runs": 4,
  "consecutive_failures": 0,
  "created_at": "2026-02-01T10:00:00Z"
}
```

### 2.10 Acceptance Criteria

- [ ] **AC-1**: MonitoringSchedule table created via Alembic migration (SQLite `batch_alter_table` + PostgreSQL compatible)
- [ ] **AC-2**: AnalysisTask.session_id made nullable; AnalysisTask gains monitoring_schedule_id FK. All migrations use `batch_alter_table` for SQLite.
- [ ] **AC-3**: User can create a monitoring schedule via REST API with frequency, preferred_hour, timezone, platforms, alert config
- [ ] **AC-4**: Only one ACTIVE schedule allowed per entity (service-level validation)
- [ ] **AC-5**: Per-user limit of 10 and system-wide limit of 100 active schedules enforced
- [ ] **AC-6**: Scheduler background loop starts on app startup, polls every 60 seconds
- [ ] **AC-7**: Due schedules (next_run_at <= now()) automatically create AnalysisTask and launch pipeline via `compiled_workflow.ainvoke()`
- [ ] **AC-8**: Pipeline execution runs with sentinel session_id (`"headless-{task_id}"`); WebSocket events gracefully degrade; `save_and_send_artifact` skips Message persistence for headless runs
- [ ] **AC-9**: MonitoringService correctly calculates next_run_at for all frequencies (daily/weekly/biweekly/monthly) with timezone support
- [ ] **AC-10**: After 3 consecutive failures, schedule transitions to ERROR and user is notified
- [ ] **AC-11**: Schedule automatically transitions to COMPLETED when max_runs or end_date is reached
- [ ] **AC-12**: User can pause/resume/delete schedules via REST API
- [ ] **AC-13**: Orchestrator can create monitoring schedule via chat command ("monitor Xiaomi weekly") with confirmation step
- [ ] **AC-14**: Scheduler respects `asyncio.Semaphore(3)` concurrency limit; no race conditions
- [ ] **AC-15**: Existing manual analysis workflow (session-based) is completely unaffected
- [ ] **AC-16**: `task_to_dict()` correctly handles `session_id=None` (no `str(None)`)
- [ ] **AC-17**: `GET /health/scheduler` returns scheduler operational status
- [ ] **AC-18**: `stop_scheduler()` cancels all running pipeline tasks within 30s timeout
- [ ] **AC-19**: Scheduler validates entity existence before launching pipeline

---

## 3. Module 2: Trend Engine & Change Detection

### 3.1 Problem Statement

While Snapshots store point-in-time metrics and `SnapshotService.get_trend()` returns a time series, there is no layer that:

1. Computes deltas between consecutive snapshots (period-over-period change)
2. Detects statistically significant changes vs. normal fluctuation
3. Categorizes changes into actionable insight types (improvement, decline, anomaly)
4. Provides aggregated trend summaries for Dashboard visualization

### 3.2 User Stories

- As a marketing manager, I want to see a BWVS trend line on the Dashboard showing my brand's visibility over time.
- As a marketing manager, I want to see period-over-period deltas (e.g., "+3.2 vs last week") on KPI cards.
- As a marketing manager, I want the system to automatically detect when a metric change is significant vs. normal noise.
- As a marketing manager, I want to ask "How is my brand doing over time?" and get a trend summary.

### 3.3 Success Metrics

- **Primary**: Dashboard displays BWVS trend with at least 3 data points after 3 weeks of monitoring
- **Secondary**: Period-over-period deltas shown on KPI cards with directional indicators
- **Guardrail**: Trend queries complete within 500ms for up to 100 snapshots

### 3.4 TrendEngine Service

**New file**: `aeo-platform/backend/app/services/trend_engine.py`

**Data source**: TrendEngine reads exclusively from AnalysisSnapshot's independent columns (`bwvs_index`, `mention_rate`, `sentiment_score`, `coverage_score`, `citation_score`). It does NOT parse the `output_data` JSON blob. Both manually-triggered and scheduled Snapshots are included in trend calculations.

```python
"""Trend analysis engine for monitoring data.

Reads AnalysisSnapshot time series (independent columns only) and computes:
- Period-over-period deltas
- Moving averages (for noise reduction)
- Significant change detection
- Trend direction classification
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class TrendDirection(str, Enum):
    IMPROVING = "improving"    # Metric is going up (good for BWVS)
    DECLINING = "declining"    # Metric is going down (bad for BWVS)
    STABLE = "stable"          # Within normal fluctuation
    VOLATILE = "volatile"      # Frequent up/down swings


@dataclass
class MetricDelta:
    """Change between two consecutive data points."""
    current_value: float | None
    previous_value: float | None
    absolute_change: float
    percentage_change: float
    is_significant: bool
    direction: str  # "up" | "down" | "stable"


@dataclass
class TrendSummary:
    """Summary of a metric's trend over a time range."""
    metric_name: str
    current_value: float | None
    period_delta: MetricDelta | None         # vs. previous snapshot
    trend_direction: TrendDirection
    data_points: int
    time_range_days: int
    moving_average: float | None  # Over last N data points (not fixed days)
    min_value: float | None
    max_value: float | None


class TrendEngine:
    """Analyzes metric trends from Snapshot time series.

    Data source: Reads from AnalysisSnapshot independent columns
    (bwvs_index, mention_rate, sentiment_score, coverage_score, citation_score).
    Does NOT parse output_data JSON.

    Both manually-triggered and scheduled Snapshots are used for trend calculations.
    """

    # Minimum data points for trend direction classification
    MIN_POINTS_FOR_TREND = 3
    # With 2 points, only show delta (no trend direction)
    MIN_POINTS_FOR_DELTA = 2

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_entity_trend_summary(
        self,
        entity_id: UUID,
        metric_names: list[str] | None = None,
    ) -> dict[str, TrendSummary]:
        """Get trend summary for an entity across all core metrics.

        Default metrics: bwvs_index, mention_rate, sentiment_score,
                        coverage_score, citation_score.

        Returns a dict of metric_name -> TrendSummary.

        Behavior by data point count:
        - 0 points: Returns TrendSummary with all None values
        - 1 point: Returns current_value only, direction=STABLE, no delta
        - 2 points: Returns delta, direction=STABLE (insufficient for trend)
        - 3+ points: Full trend analysis with direction classification
        """

    async def get_period_deltas(
        self,
        entity_id: UUID,
    ) -> dict[str, MetricDelta]:
        """Get period-over-period deltas (latest vs. previous snapshot).

        Used by Dashboard KPI cards to show "+3.2" or "-1.5" indicators.
        Requires at least 2 snapshots. Returns empty dict if insufficient data.
        """

    async def get_trend_data_points(
        self,
        entity_id: UUID,
        metric_name: str = "bwvs_index",
        limit: int = 100,
    ) -> list[dict]:
        """Get time series data points for chart rendering.

        Returns: [
            {"date": "2026-02-01", "value": 45.2, "snapshot_id": "...",
             "triggered_by": "manual", "is_significant": false},
            {"date": "2026-02-08", "value": 48.1, "snapshot_id": "...",
             "triggered_by": "scheduled", "is_significant": true},
            ...
        ]
        """

    async def detect_significant_change(
        self,
        entity_id: UUID,
        threshold_absolute: float = 10.0,
        threshold_percentage: float = 20.0,
    ) -> list[dict]:
        """Detect significant metric changes between latest two snapshots.

        A change is "significant" if it exceeds EITHER:
        - absolute threshold (e.g., BWVS changed by > 10 points)
        - percentage threshold (e.g., mention_rate changed by > 20%)

        Returns a list of detected changes:
        [
            {
                "metric": "bwvs_index",
                "current": 52.3,
                "previous": 38.1,
                "change_absolute": 14.2,
                "change_percentage": 37.3,
                "direction": "up",
                "severity": "high",  # high/medium/low
            },
            ...
        ]
        """

    @staticmethod
    def classify_trend_direction(
        values: list[float],
    ) -> TrendDirection:
        """Classify overall trend direction from a series of values.

        Requires at least 3 values. With fewer, returns STABLE.

        Uses simple linear regression slope:
        - Positive slope above threshold -> IMPROVING
        - Negative slope below threshold -> DECLINING
        - Slope near zero -> STABLE
        - High variance -> VOLATILE
        """

    @staticmethod
    def calculate_moving_average(
        data_points: list[dict],
        window_size: int = 3,
    ) -> float | None:
        """Calculate moving average over the last N data points.

        Uses data point count (not fixed days) to handle sparse/irregular
        scheduled runs gracefully. Default window = 3 data points.
        Returns None if fewer than window_size data points available.
        """
```

### 3.5 Analytics Service Enhancement

**Affected file**: `aeo-platform/backend/app/services/analytics_service.py`

Enhance `get_overview()` to include period-over-period deltas from TrendEngine:

```python
# analytics_service.py -- get_overview() enhancement

async def get_overview(
    self, brand_id: str | None, date_range: str
) -> dict[str, Any]:
    """Get KPI overview with trend deltas."""
    # ... existing metrics extraction ...

    # NEW: Compute period-over-period deltas from Snapshots
    if brand_id:
        try:
            trend_engine = TrendEngine(self.db)
            deltas = await trend_engine.get_period_deltas(UUID(brand_id))

            if "bwvs_index" in deltas:
                kpi["visibilityTrend"] = deltas["bwvs_index"].absolute_change
            if "mention_rate" in deltas:
                kpi["mentionTrend"] = deltas["mention_rate"].absolute_change
        except Exception as trend_err:
            logger.warning("Failed to compute trend deltas: %s", trend_err)

    return {"kpi": kpi}
```

**New analytics endpoint for trend data**:

```python
# analytics.py -- new endpoint

@router.get("/trend")
async def get_trend(
    brand_id: str = Query(...),
    metric: str = Query("bwvs_index"),
    limit: int = Query(50),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get trend time series for a specific metric."""
    from app.services.trend_engine import TrendEngine
    engine = TrendEngine(db)
    data_points = await engine.get_trend_data_points(
        UUID(brand_id), metric_name=metric, limit=limit
    )
    return {"trend": data_points, "metric": metric}


@router.get("/trend/summary")
async def get_trend_summary(
    brand_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Get trend summary for all core metrics."""
    from app.services.trend_engine import TrendEngine
    engine = TrendEngine(db)
    summaries = await engine.get_entity_trend_summary(UUID(brand_id))
    return {
        "summaries": {
            name: {
                "current_value": s.current_value,
                "direction": s.trend_direction.value,
                "period_delta": {
                    "absolute": s.period_delta.absolute_change if s.period_delta else 0,
                    "percentage": s.period_delta.percentage_change if s.period_delta else 0,
                    "is_significant": s.period_delta.is_significant if s.period_delta else False,
                } if s.period_delta else None,
                "data_points": s.data_points,
                "moving_average": s.moving_average,
            }
            for name, s in summaries.items()
        }
    }
```

### 3.6 Acceptance Criteria

- [ ] **AC-20**: TrendEngine computes correct period-over-period deltas for all 5 core metrics
- [ ] **AC-21**: TrendEngine reads exclusively from Snapshot independent columns, not output_data JSON
- [ ] **AC-22**: Significant change detection works with configurable absolute and percentage thresholds
- [ ] **AC-23**: Trend direction classification correctly identifies improving/declining/stable/volatile patterns (requires >= 3 data points)
- [ ] **AC-24**: With 2 data points, only delta is shown (no trend direction); with < 2, "Insufficient data" returned
- [ ] **AC-25**: Dashboard KPI cards show period-over-period deltas ("+3.2" / "-1.5" indicators)
- [ ] **AC-26**: `/api/v1/analytics/trend` returns time series data points suitable for chart rendering
- [ ] **AC-27**: `/api/v1/analytics/trend/summary` returns aggregated trend summaries for all metrics
- [ ] **AC-28**: Trend queries complete within 500ms for up to 100 snapshots
- [ ] **AC-29**: Moving average uses N data points (default 3) rather than fixed days, handling sparse data gracefully

---

## 4. Module 3: Alerting & Notification

### 4.1 Problem Statement

When a scheduled analysis detects a significant change in brand metrics (e.g., BWVS drops 15 points), the user needs to be proactively notified. Without alerting, the value of continuous monitoring is significantly diminished -- users would still need to actively check the Dashboard to discover changes.

### 4.2 User Stories

- As a marketing manager, I want to receive an in-app notification when my brand's BWVS changes significantly between scheduled analyses.
- As a marketing manager, I want to see alert details (what changed, by how much, possible reasons) so I can decide whether to investigate.
- As a marketing manager, I want to control alert sensitivity (threshold) per brand to reduce noise.
- As a marketing manager, I want to see an alert history to review past notifications.

### 4.3 Success Metrics

- **Primary**: User receives notification within 5 minutes of a scheduled analysis detecting a significant change
- **Secondary**: Alert includes actionable context (metric, change amount, direction, affected platforms)
- **Guardrail**: False positive rate < 20% (alerts that users dismiss without action)

### 4.4 Data Model: MonitoringAlert

**New file**: `aeo-platform/backend/app/models/monitoring_alert.py`

```python
"""Monitoring Alert model -- records detected metric anomalies."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean, DateTime, Enum, Float, ForeignKey,
    String, Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.user import User


class AlertSeverity(str, PyEnum):
    """Alert severity level."""
    LOW = "low"          # Small but notable change
    MEDIUM = "medium"    # Moderate change worth reviewing
    HIGH = "high"        # Large change requiring attention
    CRITICAL = "critical"  # Extreme change, immediate action needed


class AlertStatus(str, PyEnum):
    """Alert lifecycle status."""
    UNREAD = "unread"
    READ = "read"
    DISMISSED = "dismissed"
    ACTIONED = "actioned"  # User took action (e.g., ran drill-down)


class MonitoringAlert(Base):
    """Records a detected metric anomaly from continuous monitoring.

    Created by the TrendEngine when a scheduled analysis detects
    a significant change. Displayed in the notification center
    and optionally injected into the chat session.
    """

    __tablename__ = "monitoring_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    schedule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monitoring_schedules.id", ondelete="SET NULL"),
        nullable=True,
    )
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Alert content
    severity: Mapped[AlertSeverity] = mapped_column(
        Enum(AlertSeverity),
        nullable=False,
        index=True,
    )
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus),
        default=AlertStatus.UNREAD,
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(
        String(500), nullable=False
    )  # e.g., "BWVS decreased by 12.5 points for Xiaomi"
    summary: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # Human-readable explanation

    # Metric details
    metric_name: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "bwvs_index", "mention_rate", etc.
    previous_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    current_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    change_absolute: Mapped[float] = mapped_column(Float, nullable=False)
    change_percentage: Mapped[float] = mapped_column(Float, nullable=False)

    # Extended details (JSON -- platform breakdown, affected questions, etc.)
    details: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="monitoring_alerts")
    entity: Mapped["Entity"] = relationship("Entity", backref="monitoring_alerts")
```

### 4.5 AlertService

**New file**: `aeo-platform/backend/app/services/alert_service.py`

```python
"""Alert lifecycle management and generation service."""

class AlertService:
    """Manages MonitoringAlert creation, delivery, and lifecycle."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def generate_alerts_for_snapshot(
        self,
        entity_id: UUID,
        schedule_id: UUID,
        snapshot_id: UUID,
    ) -> list[MonitoringAlert]:
        """Generate alerts by comparing the new snapshot with the previous one.

        Called after each scheduled analysis completes.

        Flow:
        1. Load the new snapshot and the previous snapshot (if any)
        2. Run TrendEngine.detect_significant_change()
        3. For each significant change, create a MonitoringAlert
        4. Return created alerts (caller handles notification delivery)
        """

    async def list_user_alerts(
        self,
        user_id: UUID,
        *,
        status: AlertStatus | None = None,
        entity_id: UUID | None = None,
        severity: AlertSeverity | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MonitoringAlert], int]:
        """List alerts for a user with filtering."""

    async def get_unread_count(self, user_id: UUID) -> int:
        """Get count of unread alerts. Used for notification badge."""

    async def mark_read(self, alert_id: UUID) -> MonitoringAlert | None:
        """Mark an alert as read."""

    async def mark_all_read(self, user_id: UUID) -> int:
        """Mark all unread alerts as read. Returns count updated."""

    async def dismiss_alert(self, alert_id: UUID) -> MonitoringAlert | None:
        """Dismiss an alert (user acknowledges but takes no action)."""

    @staticmethod
    def classify_severity(
        change_absolute: float,
        change_percentage: float,
    ) -> AlertSeverity:
        """Classify alert severity based on change magnitude.

        LOW:      |change| < 5 points or < 10%
        MEDIUM:   |change| 5-15 points or 10-25%
        HIGH:     |change| 15-25 points or 25-50%
        CRITICAL: |change| > 25 points or > 50%
        """

    @staticmethod
    def generate_alert_summary(
        entity_name: str,
        metric_name: str,
        change: dict,
    ) -> str:
        """Generate a human-readable alert summary.

        Example: "Xiaomi's BWVS index dropped from 52.3 to 39.8 (-12.5 points, -23.9%).
        This is a significant decline that may be worth investigating.
        Consider running a detailed analysis to understand the contributing factors."
        """
```

### 4.6 Alert API

**New file**: `aeo-platform/backend/app/api/v1/alerts.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/alerts` | List user's alerts (paginated, filterable) |
| GET | `/api/v1/alerts/unread-count` | Get unread alert count (for badge) |
| GET | `/api/v1/alerts/{id}` | Get alert details |
| POST | `/api/v1/alerts/{id}/read` | Mark alert as read |
| POST | `/api/v1/alerts/read-all` | Mark all alerts as read |
| POST | `/api/v1/alerts/{id}/dismiss` | Dismiss an alert |

**Alert response**:

```json
{
  "id": "uuid",
  "entity_id": "uuid",
  "entity_name": "Xiaomi",
  "severity": "high",
  "status": "unread",
  "title": "BWVS decreased by 12.5 points",
  "summary": "Xiaomi's BWVS index dropped from 52.3 to 39.8 (-12.5 points, -23.9%). ...",
  "metric_name": "bwvs_index",
  "previous_value": 52.3,
  "current_value": 39.8,
  "change_absolute": -12.5,
  "change_percentage": -23.9,
  "snapshot_id": "uuid",
  "created_at": "2026-02-21T03:05:00Z"
}
```

### 4.7 Acceptance Criteria

- [ ] **AC-30**: MonitoringAlert table created via Alembic migration (using `batch_alter_table` for SQLite)
- [ ] **AC-31**: AlertService generates alerts when TrendEngine detects significant changes after scheduled runs
- [ ] **AC-32**: Alert severity correctly classified as LOW/MEDIUM/HIGH/CRITICAL based on change magnitude
- [ ] **AC-33**: Alert summary is human-readable and actionable (includes metric, change, direction)
- [ ] **AC-34**: GET `/api/v1/alerts/unread-count` returns correct count for notification badge
- [ ] **AC-35**: Mark-read and dismiss operations update alert status correctly
- [ ] **AC-36**: Alerts are only generated when alert_on_significant_change is true on the schedule

---

## 5. Technical Constraints

### 5.1 Must Reuse Existing Architecture

- **A1-A5 pipeline**: Scheduled runs invoke the same LangGraph `compiled_workflow.ainvoke()` as manual analyses
- **AnalysisTask model**: Scheduled runs create AnalysisTask instances (with nullable session_id + monitoring_schedule_id FK)
- **AnalysisSnapshot model**: Each scheduled run creates a Snapshot (with triggered_by="scheduled")
- **SnapshotService**: Reuse for creating Snapshots; TrendEngine reads existing Snapshots
- **TaskService lifecycle**: Reuse create/start/complete/fail for scheduled tasks
- **Orchestrator star topology**: New `create_monitoring_schedule` tool goes through the same routing
- **WebSocket event system**: Events gracefully degrade (silent return) for headless sessions
- **Zustand stores**: New alertStore follows existing patterns (dashboardStore, entityStore)

### 5.2 Must Not Break Existing Functionality

- Manual analysis workflow (chat-triggered, session-based) must work identically
- Existing Dashboard features must remain functional
- Existing task list and reconnection behavior must work for session-based tasks
- Snapshot creation and comparison features must be unaffected
- Multi-turn follow-up tools (Cycle 3) must continue working

### 5.3 Database Compatibility

- All new migrations must work on both SQLite (dev) and PostgreSQL (prod)
- **All migrations MUST use `op.batch_alter_table()` for ALTER COLUMN operations** (SQLite compatibility)
- UUID/Enum type handling follows existing patterns
- MonitoringSchedule.next_run_at indexed for efficient scheduler queries
- MonitoringAlert.status indexed for efficient unread count queries

### 5.4 Performance Constraints

- Scheduler poll loop: max 1 query per 60 seconds
- `asyncio.Semaphore(MAX_CONCURRENT_SCHEDULED=3)` for concurrent pipeline runs
- Trend queries: < 500ms for up to 100 snapshots
- Alert generation: < 2 seconds per scheduled run completion
- Notification badge poll: max 1 request per 60 seconds per client
- **LLM API quota competition mitigation**:
  - Scheduled runs use `asyncio.Semaphore(3)` to limit concurrent LLM calls
  - When the semaphore is fully acquired (3 scheduled runs active), the scheduler defers new scheduled runs until capacity frees up
  - Manual (session-based) analyses are NOT subject to this semaphore -- they always run immediately
  - In a future iteration, a priority queue can be introduced where manual analyses can preempt scheduled runs if LLM API quotas are exhausted
  - The `platforms` field on MonitoringSchedule defaults to API-only (`["doubao", "hunyuan"]`), reducing per-run token consumption compared to 4-platform runs

### 5.5 A4 Browser Agent Resource Contention

Scheduled runs use **API-only platforms by default** (`["doubao", "hunyuan"]`). This avoids Playwright browser instance contention between scheduled and manual analyses.

If a schedule is configured to include browser-based platforms (`["kimi", "deepseek"]`), the pipeline's A4 node will attempt browser automation. However:
- The existing A4 retry and timeout mechanisms (max 2 retries, exponential backoff) apply
- Scheduled runs should be configured for off-peak hours (default preferred_hour=3 UTC / 11 AM Beijing) to minimize contention
- The Semaphore limit of 3 concurrent scheduled runs naturally caps browser resource usage

### 5.6 New Dependency Analysis

| Dependency | Decision | Rationale |
|-----------|----------|-----------|
| APScheduler | NOT added | asyncio poll loop sufficient for V1 volume |
| Celery Beat | NOT added | Existing celery_config.py is unused; adding Beat adds Redis requirement |
| Redis | NOT required | Scheduler state is in PostgreSQL; no need for distributed locking at V1 scale |
| Recharts | Already in frontend | Used for TrendChart; no new dependency |

---

## 6. Data Model Summary

### 6.1 New Tables

| Table | Purpose | Key Relationships |
|-------|---------|-------------------|
| `monitoring_schedules` | Schedule configuration for automated periodic analysis | FK: user_id, entity_id, last_task_id |
| `monitoring_alerts` | Detected metric anomalies and notifications | FK: user_id, entity_id, schedule_id, snapshot_id |

### 6.2 Modified Tables

| Table | Change | Migration Complexity |
|-------|--------|---------------------|
| `analysis_tasks` | Add `monitoring_schedule_id` FK (nullable); change `session_id` to nullable | Low (additive, uses `batch_alter_table`) |

### 6.3 Entity Relationship Diagram (Relevant Models)

```
User (1) ----< (N) MonitoringSchedule
Entity (1) ----< (N) MonitoringSchedule (at most 1 ACTIVE per entity)
MonitoringSchedule (1) ----< (N) AnalysisTask (via monitoring_schedule_id)
MonitoringSchedule (1) ----< (N) MonitoringAlert (via schedule_id)
Entity (1) ----< (N) AnalysisSnapshot
AnalysisTask (1) ---- (0..1) AnalysisSnapshot (via snapshot_id)
AnalysisSnapshot (1) ----< (N) MonitoringAlert (via snapshot_id)
Session (1) ----< (N) AnalysisTask (via session_id, NOW NULLABLE)
```

---

## 7. API Design Summary

### 7.1 New Endpoints

| Method | Endpoint | Module | Description |
|--------|----------|--------|-------------|
| POST | `/api/v1/monitoring/schedules` | M1 | Create schedule |
| GET | `/api/v1/monitoring/schedules` | M1 | List user schedules |
| GET | `/api/v1/monitoring/schedules/{id}` | M1 | Get schedule details |
| PATCH | `/api/v1/monitoring/schedules/{id}` | M1 | Update schedule |
| POST | `/api/v1/monitoring/schedules/{id}/pause` | M1 | Pause schedule |
| POST | `/api/v1/monitoring/schedules/{id}/resume` | M1 | Resume schedule |
| DELETE | `/api/v1/monitoring/schedules/{id}` | M1 | Delete schedule |
| GET | `/api/v1/monitoring/schedules/{id}/history` | M1 | Schedule task history |
| GET | `/health/scheduler` | M1 | Scheduler health status |
| GET | `/api/v1/analytics/trend` | M2 | Trend time series data |
| GET | `/api/v1/analytics/trend/summary` | M2 | Trend summary per metric |
| GET | `/api/v1/alerts` | M3 | List alerts |
| GET | `/api/v1/alerts/unread-count` | M3 | Unread alert count |
| GET | `/api/v1/alerts/{id}` | M3 | Alert details |
| POST | `/api/v1/alerts/{id}/read` | M3 | Mark read |
| POST | `/api/v1/alerts/read-all` | M3 | Mark all read |
| POST | `/api/v1/alerts/{id}/dismiss` | M3 | Dismiss alert |

### 7.2 Modified Endpoints

| Method | Endpoint | Change |
|--------|----------|--------|
| GET | `/api/v1/analytics/overview` | Now includes trend deltas from TrendEngine |
| GET | `/api/v1/tasks` | Returns both session-based and headless tasks |

---

## 8. Frontend Design Specification

### 8.1 Module 1: MonitoringTab (Dashboard)

**Location**: New tab in Dashboard TABS, added as the last tab before "Optimization".

```typescript
const TABS = [
  { id: 'visibility', label: 'Visibility' },
  { id: 'platform', label: 'Platform Comparison' },
  { id: 'sources', label: 'Source Distribution' },
  { id: 'aeo', label: 'AEO Metrics' },
  { id: 'monitoring', label: '监测' },  // NEW
  { id: 'optimization', label: 'Optimization' },
] as const;
```

**MonitoringTab layout** (`src/components/dashboard/MonitoringTab.tsx`):

```
+-- MonitoringTab --------------------------------------------------+
|                                                                    |
|  [ScheduleStatusCard]                                              |
|  [green pulse] Active | Weekly | Next: Feb 28 11:00 AM            |
|  [Pause]  [Edit Settings]                                          |
|                                                                    |
|  [TrendChart]                                                      |
|  (line chart, dimension switching pills: BWVS / MentionRate /     |
|   Sentiment / Coverage)                                            |
|  Significant change points highlighted with glow effect            |
|  Trend indicator: "improving" (green arrow) / "declining" (red)    |
|                                                                    |
|  [MetricDeltaCards] (2x2 grid)                                     |
|  +--------------------+  +--------------------+                    |
|  | Mention Rate       |  | Sentiment Score    |                    |
|  | 32.1%  +2.3%       |  | 65.2   -1.1        |                    |
|  | [sparkline]  vs LW |  | [sparkline]  vs LW |                    |
|  +--------------------+  +--------------------+                    |
|  +--------------------+  +--------------------+                    |
|  | Coverage Score     |  | Citation Score     |                    |
|  | 75.0   stable      |  | 42.3   +5.1        |                    |
|  | [sparkline]  vs LW |  | [sparkline]  vs LW |                    |
|  +--------------------+  +--------------------+                    |
|                                                                    |
|  [Recent Alerts] (max 3)                                           |
|  [!] HIGH   BWVS improved +5.2         2 hours ago                 |
|  [!] MEDIUM Mention rate dropped -8.3%  1 day ago                  |
|  [i] LOW    Sentiment improved          3 days ago                  |
|                                                                    |
|  [Run History Table]                                               |
|  Time          | Status    | BWVS  | Change | Actions              |
|  Feb 21 03:00  | Completed | 52.3  | +5.2   | [View Snapshot]      |
|  Feb 14 03:00  | Completed | 47.1  | -2.1   | [View Snapshot]      |
|  Feb 07 03:00  | Failed    | --    | --     | [View Error]         |
|                                                                    |
|  [Empty State] (when no schedule exists)                           |
|  "This brand has no monitoring schedule yet.                       |
|   Go to Chat and say 'Set up weekly monitoring for [brand]'        |
|   to get started."                                                 |
|                                                                    |
+-------------------------------------------------------------------+
```

**ScheduleStatusCard** (`src/components/dashboard/ScheduleStatusCard.tsx`):
- Status indicator: animated dot (active=green pulse/breathing animation, paused=yellow static, error=red static, completed=gray static)
- Displays: frequency, next execution time, current alert threshold
- Action buttons: [Pause/Resume] and [Edit Settings]
- Edit mode: inline expand (not modal) with:
  - Pill-style frequency selector (Daily / Weekly / Biweekly / Monthly)
  - Time dropdown for preferred_hour
  - Alert threshold number input
  - Delete button with confirmation dialog ("Are you sure? This will stop all scheduled analyses for this brand.")

**Responsive behavior**:
- `lg` (>= 1024px): 4-column grid for MetricDeltaCards
- `md` (>= 768px): 2-column grid
- `sm` (< 768px): single column stack

### 8.2 Module 2: TrendChart & MetricDeltaCard

**TrendChart** (`src/components/dashboard/TrendChart.tsx`):

```typescript
interface TrendChartProps {
  data: TrendDataPoint[];
  metric: string;
  height?: number;
  significantChanges?: SignificantChange[];
}

interface TrendDataPoint {
  date: string;      // "2026-02-01"
  value: number;     // 45.2
  snapshotId: string;
  triggeredBy: 'manual' | 'scheduled';
}

interface SignificantChange {
  date: string;
  direction: 'up' | 'down';
  magnitude: number;
}
```

- Recharts `<LineChart>` with data point markers
- **Dimension switching**: Pill-style selector above chart (BWVS / Mention Rate / Sentiment / Coverage / Citation)
- **Significant change highlighting**: Data points with significant changes rendered at larger radius with subtle glow effect (`filter: drop-shadow(...)`) + enhanced tooltip showing change details
- **Trend direction indicator**: Text label below chart showing direction:
  - "improving" = "上升中" (green text + upward arrow)
  - "declining" = "下降中" (red text + downward arrow)
  - "stable" = "保持稳定" (gray text + horizontal line)
  - "volatile" = "波动较大" (yellow text + zigzag icon)
- **Insufficient data behavior** (< 3 data points):
  - Show existing data points normally
  - Add dashed line extending to the next projected execution date
  - Display helper text: "Need at least 3 data points for trend analysis. Next scheduled execution: [date]"

**MetricDeltaCard** (`src/components/dashboard/MetricDeltaCard.tsx`):
- Extends the existing KPICard design language
- Adds sparkline mini-trend (tiny `<LineChart>` from last 5-7 data points, no axes)
- Shows "vs last week" label with delta value and direction arrow
- Color coding: green for improvement, red for decline, gray for stable
- No separate hover state -- card is informational only

### 8.3 Module 3: NotificationBell, NotificationPanel & AlertCard

**NotificationBell placement**:
- `DashboardTopBar.tsx`: Add NotificationBell to the right side of the top bar
- `ChatSidebar.tsx`: Add NotificationBell to the sidebar header area
- Both instances share the same `alertStore` (Zustand) for consistent state

**NotificationBell** (`src/components/notifications/NotificationBell.tsx`):
- Bell icon (from Radix UI icons or similar)
- Red circular badge showing unread count
  - Count > 99 displays "99+"
  - Badge hidden when count = 0
- Polling: 60-second interval via `setInterval` calling `GET /api/v1/alerts/unread-count`
- Click toggles NotificationPanel dropdown

**NotificationPanel** (`src/components/notifications/NotificationPanel.tsx`):
- Fixed width: 380px dropdown, positioned below the bell icon
- Header: "Notifications ([N] unread)" + [Mark all read] button
- Body: Scrollable list of AlertCards, max 5-6 visible without scrolling
- Footer: "View all notifications" link (future: navigates to full alert history page)
- Close behavior: Click outside / Escape key / Route change
- Max items shown: Latest 20 (paginated on "View all" page)

**AlertCard** (`src/components/notifications/AlertCard.tsx`):
- Left border: 4px solid, color = severity
  - `critical` = red (`border-l-red-500`)
  - `high` = yellow/amber (`border-l-amber-500`)
  - `medium` = blue (`border-l-blue-500`)
  - `low` = gray (`border-l-gray-400`)
- Icon: Severity-specific (critical=exclamation-circle, high=exclamation-triangle, medium=info-circle, low=bell)
- Content: Entity name + metric change (e.g., "Xiaomi BWVS -12.5 pts (-23.9%)")
- Timestamp: Relative format ("2 hours ago", "1 day ago")
- Read/unread visual:
  - Unread: `bg-tertiary` background + normal text color
  - Read: transparent background + muted text color
  - Dismissed: removed from list
- Click behavior: Mark as read -> Navigate to Dashboard -> Select the entity -> Switch to Monitoring tab
- Entry animation: Fade-in + slight slide-down for newly appearing alerts

**Accessibility requirements**:
- Full ARIA markup: `role="alert"` on new notifications, `role="status"` on badge
- Keyboard navigation: Tab through alerts, Enter to open, Escape to close panel
- Severity conveyed by icon + text label, NOT only by color (for color-blind users)
- Screen reader announcements for new unread notifications

### 8.4 New Components

| Component | Location | Purpose |
|-----------|----------|---------|
| `NotificationBell` | `src/components/notifications/NotificationBell.tsx` | Header bell icon + unread badge |
| `NotificationPanel` | `src/components/notifications/NotificationPanel.tsx` | Alert list dropdown (380px) |
| `AlertCard` | `src/components/notifications/AlertCard.tsx` | Individual alert display with severity border |
| `MonitoringTab` | `src/components/dashboard/MonitoringTab.tsx` | Dashboard monitoring tab (schedule + trend + alerts + history) |
| `TrendChart` | `src/components/dashboard/TrendChart.tsx` | Recharts line chart with dimension switching + significant change highlighting |
| `ScheduleStatusCard` | `src/components/dashboard/ScheduleStatusCard.tsx` | Schedule config display with status dot + inline edit |
| `MetricDeltaCard` | `src/components/dashboard/MetricDeltaCard.tsx` | Period-over-period metric card with sparkline |
| `RunHistoryTable` | `src/components/dashboard/RunHistoryTable.tsx` | Execution history table (time/status/BWVS/change/actions) |

### 8.5 New Stores

| Store | Location | Purpose |
|-------|----------|---------|
| `alertStore` | `src/stores/alertStore.ts` | Alert state management + polling |
| `monitoringStore` | `src/stores/monitoringStore.ts` | Schedule + trend data state management |

**alertStore interface**:

```typescript
interface AlertState {
  alerts: MonitoringAlert[];
  unreadCount: number;
  isLoading: boolean;
  isPanelOpen: boolean;

  // Actions
  fetchAlerts: () => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markRead: (alertId: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  dismissAlert: (alertId: string) => Promise<void>;
  togglePanel: () => void;
  closePanel: () => void;

  // Polling
  startPolling: () => void;
  stopPolling: () => void;
}
```

**monitoringStore interface**:

```typescript
interface MonitoringState {
  schedule: MonitoringSchedule | null;
  trendData: Record<string, TrendDataPoint[]>;  // metric_name -> data points
  trendSummaries: Record<string, TrendSummary>;
  runHistory: RunHistoryEntry[];
  isLoading: boolean;

  // Actions
  fetchSchedule: (entityId: string) => Promise<void>;
  fetchTrendData: (entityId: string, metric: string) => Promise<void>;
  fetchTrendSummaries: (entityId: string) => Promise<void>;
  fetchRunHistory: (scheduleId: string) => Promise<void>;
  pauseSchedule: (scheduleId: string) => Promise<void>;
  resumeSchedule: (scheduleId: string) => Promise<void>;
  updateSchedule: (scheduleId: string, updates: Partial<MonitoringSchedule>) => Promise<void>;
  deleteSchedule: (scheduleId: string) => Promise<void>;
}
```

### 8.6 Modified Components

| Component | Change |
|-----------|--------|
| `DashboardPage.tsx` | Add "监测" tab to TABS array; render MonitoringTab when selected |
| `DashboardTopBar.tsx` | Add NotificationBell to right side of top bar |
| `ChatSidebar.tsx` | Add NotificationBell to sidebar header |
| `dashboardStore.ts` | Add trendData fetching (delegated to monitoringStore) |
| `KPICard.tsx` | Already supports trend prop -- enhanced by real delta data from TrendEngine |
| `api.ts` | Add monitoring schedule, alert, and trend API methods |
| `globals.css` | Add badge pulse animation + AlertCard entry animation keyframes |

### 8.7 New TypeScript Types

```typescript
// types/monitoring.ts

export interface MonitoringSchedule {
  id: string;
  entity_id: string;
  entity_name: string;
  frequency: 'daily' | 'weekly' | 'biweekly' | 'monthly';
  status: 'active' | 'paused' | 'completed' | 'error';
  preferred_hour: number;
  timezone: string;
  platforms: string[] | null;
  alert_on_significant_change: boolean;
  alert_threshold_bwvs: number;
  next_run_at: string | null;
  last_run_at: string | null;
  total_runs: number;
  consecutive_failures: number;
  created_at: string;
}

export interface MonitoringAlert {
  id: string;
  entity_id: string;
  entity_name: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  status: 'unread' | 'read' | 'dismissed' | 'actioned';
  title: string;
  summary: string;
  metric_name: string;
  previous_value: number | null;
  current_value: number | null;
  change_absolute: number;
  change_percentage: number;
  snapshot_id: string | null;
  created_at: string;
  read_at: string | null;
}

export interface TrendDataPoint {
  date: string;
  value: number;
  snapshotId: string;
  triggeredBy: 'manual' | 'scheduled';
  isSignificant?: boolean;
}

export interface TrendSummary {
  current_value: number | null;
  direction: 'improving' | 'declining' | 'stable' | 'volatile';
  period_delta: {
    absolute: number;
    percentage: number;
    is_significant: boolean;
  } | null;
  data_points: number;
  moving_average: number | null;
}

export interface RunHistoryEntry {
  task_id: string;
  started_at: string;
  completed_at: string | null;
  status: 'running' | 'completed' | 'failed';
  bwvs: number | null;
  bwvs_change: number | null;
  snapshot_id: string | null;
  error_message: string | null;
}

export interface SchedulerHealth {
  running: boolean;
  active_pipeline_count: number;
  max_concurrent: number;
  semaphore_available: number;
  poll_interval_seconds: number;
}
```

### 8.8 Frontend Acceptance Criteria

- [ ] **AC-37**: NotificationBell appears in both DashboardTopBar and ChatSidebar, sharing alertStore
- [ ] **AC-38**: Notification badge shows unread count (0 = hidden, >99 = "99+"), polls every 60s
- [ ] **AC-39**: NotificationPanel (380px) displays up to 5-6 AlertCards with severity-colored left border
- [ ] **AC-40**: Clicking an AlertCard: marks read -> navigates to Dashboard -> selects entity -> switches to Monitoring tab
- [ ] **AC-41**: NotificationPanel closes on click-outside / Escape / route change
- [ ] **AC-42**: TrendChart renders BWVS time series with dimension switching pills
- [ ] **AC-43**: Significant change data points show enlarged radius + glow effect + enhanced tooltip
- [ ] **AC-44**: Trend direction indicator displays correct label and color (improving/declining/stable/volatile)
- [ ] **AC-45**: With < 3 data points, TrendChart shows existing points + dashed projection line + helper text
- [ ] **AC-46**: MetricDeltaCards show sparkline mini-trend + "vs last week" delta
- [ ] **AC-47**: ScheduleStatusCard shows animated status dot (green pulse for active)
- [ ] **AC-48**: ScheduleStatusCard inline edit mode: pill frequency selector + time dropdown + threshold input + delete with confirmation
- [ ] **AC-49**: MonitoringTab shows schedule status, trend chart, metric deltas, recent alerts (max 3), and run history table
- [ ] **AC-50**: MonitoringTab empty state guides user to Chat for setup
- [ ] **AC-51**: Responsive layout: lg=4col / md=2col / sm=stack for MetricDeltaCards
- [ ] **AC-52**: Full ARIA markup + keyboard navigation + severity conveyed by icon+text (not color alone)
- [ ] **AC-53**: Badge pulse animation + AlertCard fade-in entry animation defined in globals.css

---

## 9. Impact Summary

### 9.1 Backend File Changes

| File | Change Type | Description |
|------|------------|-------------|
| `app/models/monitoring_schedule.py` | **New** | MonitoringSchedule model (with timezone, platforms fields) |
| `app/models/monitoring_alert.py` | **New** | MonitoringAlert model |
| `app/models/task.py` | Modify | Add monitoring_schedule_id FK; make session_id nullable; update Relationship type |
| `app/models/__init__.py` | Modify | Export new models |
| `app/services/monitoring_service.py` | **New** | MonitoringService (schedule CRUD + execution tracking + limits) |
| `app/services/trend_engine.py` | **New** | TrendEngine (trend analysis + change detection, reads Snapshot columns only) |
| `app/services/alert_service.py` | **New** | AlertService (alert generation + lifecycle) |
| `app/services/scheduler.py` | **New** | Async scheduler engine (Semaphore concurrency + graceful shutdown + health check) |
| `app/api/v1/monitoring.py` | **New** | Monitoring schedule API endpoints + scheduler health |
| `app/api/v1/alerts.py` | **New** | Alert API endpoints |
| `app/api/v1/analytics.py` | Modify | Add trend endpoints; enhance overview with deltas |
| `app/api/v1/router.py` | Modify | Register new route modules |
| `app/workflow/orchestrator_node.py` | Modify | Add create_monitoring_schedule tool |
| `app/workflow/graph.py` | Modify | Add create_monitoring node |
| `app/workflow/nodes_monitoring.py` | **New** | create_monitoring_node |
| `app/workflow/events.py` | Modify | Add headless conditional branch to `save_and_send_artifact` |
| `app/services/analytics_service.py` | Modify | Integrate TrendEngine for KPI deltas |
| `app/services/task_service.py` | Modify | `task_to_dict` null-safe session_id; `create_task` optional session_id |
| `app/main.py` | Modify | Start/stop scheduler in startup/shutdown |
| Alembic migration | **New** | MonitoringSchedule + MonitoringAlert tables; AnalysisTask changes (batch mode) |

### 9.2 Frontend File Changes

| File | Change Type | Description |
|------|------------|-------------|
| `src/types/monitoring.ts` | **New** | TypeScript types for monitoring + alerts + trends |
| `src/stores/alertStore.ts` | **New** | Alert state management + 60s polling |
| `src/stores/monitoringStore.ts` | **New** | Monitoring schedule + trend state |
| `src/services/api.ts` | Modify | Add monitoring, alert, trend API calls |
| `src/components/notifications/NotificationBell.tsx` | **New** | Header notification bell with badge |
| `src/components/notifications/NotificationPanel.tsx` | **New** | 380px alert dropdown panel |
| `src/components/notifications/AlertCard.tsx` | **New** | Alert card with severity border + click navigation |
| `src/components/dashboard/MonitoringTab.tsx` | **New** | Dashboard monitoring tab (composite layout) |
| `src/components/dashboard/TrendChart.tsx` | **New** | Recharts line chart with dimension pills + glow highlights |
| `src/components/dashboard/ScheduleStatusCard.tsx` | **New** | Schedule status with animated dot + inline edit |
| `src/components/dashboard/MetricDeltaCard.tsx` | **New** | Metric delta with sparkline + "vs LW" label |
| `src/components/dashboard/RunHistoryTable.tsx` | **New** | Execution history table |
| `src/components/dashboard/DashboardPage.tsx` | Modify | Add Monitoring tab |
| `src/components/dashboard/DashboardTopBar.tsx` | Modify | Add NotificationBell |
| `src/components/chat/ChatSidebar.tsx` | Modify | Add NotificationBell |
| `src/stores/dashboardStore.ts` | Modify | Add trend data state |
| `src/styles/globals.css` | Modify | Add badge pulse + AlertCard entry animations |

### 9.3 Unchanged

- A1-A5 Agent node implementations (pipeline is reused, not modified)
- Orchestrator core routing logic (only adds one new tool)
- WebSocket event system (graceful degradation, no modification needed)
- `emit_to_session()` implementation (already handles missing sessions)
- Snapshot model schema (uses existing triggered_by field)
- Multi-turn follow-up tools (Cycle 3)
- Entity/Session CRUD
- Report generation and rendering
- LLM abstraction layer

---

## 10. Schedule Estimate

| Task | Estimate | Owner | Dependencies |
|------|----------|-------|-------------|
| **Module 1: Monitoring Schedules & Scheduler** | | | |
| MonitoringSchedule model + Alembic migration (batch mode) | 2h | Backend Dev | None |
| AnalysisTask schema changes (nullable session_id + FK) + migration + nullable audit | 2.5h | Backend Dev | None |
| MonitoringService (CRUD + scheduling logic + limits) | 6h | Backend Dev | Model |
| Scheduler engine (Semaphore concurrency + graceful shutdown + health check) | 8h | Backend Dev | MonitoringService, TaskService |
| Headless pipeline integration (sentinel session_id + save_and_send_artifact branch) | 5.5h | Backend Dev | Scheduler |
| Monitoring schedule API (8 endpoints + health endpoint) | 4.5h | Backend Dev | MonitoringService |
| Orchestrator tool + create_monitoring_node (with confirmation step) | 3h | Backend Dev | MonitoringService |
| **Module 2: Trend Engine & Change Detection** | | | |
| TrendEngine service (deltas, trends, N-point moving average, direction) | 6h | Backend Dev | SnapshotService |
| Significant change detection algorithm | 3h | Backend Dev | TrendEngine |
| Analytics API trend endpoints (2 new) | 2h | Backend Dev | TrendEngine |
| Analytics overview enhancement (delta integration) | 2h | Backend Dev | TrendEngine |
| **Module 3: Alerting & Notification** | | | |
| MonitoringAlert model + migration (batch mode) | 1.5h | Backend Dev | None |
| AlertService (generation + lifecycle) | 5h | Backend Dev | TrendEngine |
| Alert API (6 endpoints) | 3h | Backend Dev | AlertService |
| Scheduler completion hook (alert generation) | 2h | Backend Dev | AlertService, Scheduler |
| **Frontend** | | | |
| TypeScript types (monitoring.ts) | 1h | Frontend Dev | None |
| alertStore + monitoringStore (with polling) | 3h | Frontend Dev | API |
| API service additions (monitoring + alert + trend) | 2h | Frontend Dev | API |
| NotificationBell + NotificationPanel + AlertCard (with ARIA + animations) | 6h | Frontend Dev | alertStore |
| TrendChart component (Recharts, dimension pills, glow highlights, projection line) | 5h | Frontend Dev | trend API |
| MonitoringTab (schedule status + trend + alerts + history + empty state) | 6h | Frontend Dev | All stores |
| ScheduleStatusCard (status dot + inline edit) + MetricDeltaCard (sparkline) | 4h | Frontend Dev | monitoringStore |
| RunHistoryTable | 2h | Frontend Dev | monitoringStore |
| DashboardPage tab integration + DashboardTopBar/ChatSidebar NotificationBell | 1.5h | Frontend Dev | MonitoringTab, NotificationBell |
| KPI card real delta data binding | 1h | Frontend Dev | dashboardStore |
| globals.css animations (badge pulse, AlertCard entry, status dot breathing) | 1h | Frontend Dev | None |
| **Testing** | | | |
| MonitoringService unit tests (including limits + timezone) | 3h | QA | MonitoringService |
| Scheduler unit tests (Semaphore, graceful shutdown, entity check, failure handling) | 4h | QA | Scheduler |
| TrendEngine unit tests (deltas, direction, N-point moving average, sparse data) | 3h | QA | TrendEngine |
| AlertService unit tests (generation, severity classification) | 2h | QA | AlertService |
| Nullable session_id audit tests (task_to_dict, TaskService, orphan recovery) | 2h | QA | task.py changes |
| E2E: schedule creation via chat + API | 3h | QA | All M1 |
| E2E: scheduled pipeline execution end-to-end (headless workflow) | 4h | QA | All M1 + pipeline |
| E2E: trend chart with multiple snapshots | 2h | QA | M2 + frontend |
| E2E: alert generation and notification flow | 3h | QA | All M3 |
| **Total** | **~127h (~16-18 days)** | | |

### Suggested Execution Order

```
Week 1 (Day 1-5):
  Day 1:    Models + Alembic migrations (MonitoringSchedule, MonitoringAlert,
            AnalysisTask changes) -- all using batch_alter_table
  Day 2-3:  MonitoringService + TrendEngine (backend services)
            + nullable session_id audit (task_to_dict, TaskService, Relationships)
  Day 4-5:  Scheduler engine (Semaphore + graceful shutdown + health check)
            + headless pipeline (sentinel session_id + save_and_send_artifact branch)

Week 2 (Day 6-10):
  Day 6-7:  AlertService + alert generation hooks + scheduler completion integration
  Day 8:    All API endpoints (monitoring, alerts, trend, health)
  Day 9:    Orchestrator tool + create_monitoring_node (with confirmation)
  Day 10:   Backend unit tests (MonitoringService, Scheduler, TrendEngine,
            AlertService, nullable audit)

Week 3 (Day 11-16):
  Day 11-12: Frontend stores + TypeScript types + API integration
             + globals.css animations
  Day 13-14: NotificationBell/Panel/AlertCard (with ARIA + accessibility)
             + TrendChart (dimension pills + glow + projection line)
  Day 15:    MonitoringTab + ScheduleStatusCard + MetricDeltaCard +
             RunHistoryTable + empty state
  Day 16:    DashboardPage tab integration + TopBar/Sidebar NotificationBell
             + KPI delta binding + responsive testing

Week 4 (Day 17-18):
  Day 17:   Frontend polishing + edge cases + cross-browser testing
  Day 18:   E2E integration testing (4 E2E test suites)
```

Rationale: Backend services first (models -> services -> scheduler -> API), then frontend builds on top of stable APIs. Testing is distributed throughout but concentrated in the final days. The nullable session_id audit runs in parallel with service development (Day 2-3) to catch issues early.

---

## 11. Risks & Dependencies

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Headless pipeline execution via sentinel session_id causes unexpected behavior in agent nodes | Low | Scheduled runs may emit events that fail silently | Sentinel pattern ensures all state accesses work; `emit_to_session` already handles missing sessions; `save_and_send_artifact` conditional branch handles Message persistence |
| Scheduler poll loop crashes silently | Medium | No scheduled analyses execute | Wrap loop body in try/except with logging; `/health/scheduler` endpoint for monitoring; orphan task recovery covers stale tasks |
| Concurrent scheduled runs exhaust LLM API quotas | Medium | Both scheduled and manual analyses slow down or fail | `asyncio.Semaphore(3)` limits scheduled concurrency; manual analyses bypass semaphore; default API-only platforms reduce token usage |
| Single-process scheduler does not survive server restart | Low | Missed scheduled runs | next_run_at is persisted in DB; after restart, the scheduler picks up from where it left off at next poll |
| Alert fatigue: too many low-severity alerts | Medium | Users ignore notifications | Default threshold of 10 BWVS points filters minor fluctuations; user can adjust threshold per schedule |
| Trend direction misclassification with few data points | Medium | Misleading trend indicators | Require minimum 3 data points for trend classification; with 2 show only delta; show "Insufficient data" otherwise |
| AnalysisTask.session_id nullable change breaks existing queries | Low | Frontend task list or reconnection breaks | Full impact audit (Section 2.7); `task_to_dict` null-safe fix; Relationship type annotation; exclude headless tasks from orphan recovery |
| Browser Agent (A6) resource contention between scheduled and manual | Medium | Playwright browser instances conflict | Scheduler defaults to API-only platforms; `platforms` field configurable per schedule |
| `asyncio.Semaphore` exhaustion under sustained load | Low | Scheduled runs queued indefinitely | Scheduler skips poll when semaphore locked; health endpoint reports semaphore availability |
| SQLite batch_alter_table migration issues | Low | Migration fails on dev environment | All ALTER COLUMN operations explicitly use `batch_alter_table`; tested on both SQLite and PostgreSQL |

### Dependencies

| Dependency | Type | Risk |
|-----------|------|------|
| Cycle 3 AnalysisTask model implemented | Hard | Cycle 3 must be complete for task lifecycle reuse |
| Cycle 2 Snapshot model implemented | Hard | Trend engine reads Snapshots |
| Cycle 3 TaskService implemented | Hard | Scheduler creates tasks via TaskService |
| Cycle 1 BWVS v2 metrics | Hard | Trend analysis requires real (non-fake) metric values |
| Entity model exists with brand data | Soft | Already implemented |

---

## 12. Out of Scope (Deferred)

1. **Email / Webhook notifications**: V1 uses in-app notification only. Email/Webhook integration deferred to future cycle. (Webhook interface is architecturally reserved in AlertService but not implemented.)
2. **Multi-process scheduler (Celery Beat)**: V1 uses single-process asyncio. Celery Beat for horizontal scaling deferred.
3. **Custom cron expressions**: V1 supports 4 preset frequencies. Custom cron deferred.
4. **Comparison reports across scheduled runs**: V1 shows trend data; full comparative report generation deferred.
5. **Team sharing**: Alerts go to schedule creator only. Team/role-based notification deferred.
6. **Department-specific scheduled monitoring** (P2-1): Each department running their own monitoring perspective. Deferred until department views are implemented.
7. **BWVS weight customization** (P2-3): Related but independent. Scheduled monitoring uses whatever BWVS formula is current.
8. **Historical data backfill**: If a user sets up monitoring, they only get trend data from the first scheduled run onward. No retroactive analysis.
9. **Smart scheduling**: Automatically adjusting frequency based on volatility (e.g., if metrics are stable, reduce frequency). Deferred.

---

## 13. Open Questions (Resolved)

1. **Q: Should scheduled analyses use browser-based platforms (Kimi/DeepSeek) or API-only?**
   - **Decision**: API-only (`["doubao", "hunyuan"]`) as the **default**. The `MonitoringSchedule.platforms` field (JSON list) allows per-schedule configuration. Users who want broader coverage can opt into `["kimi", "deepseek"]`, understanding the reliability trade-off.
   - Rationale: Browser automation is slower, less reliable, and competes for Playwright resources. API-first prioritizes reliability for unattended scheduled runs.

2. **Q: What is the minimum number of data points before showing a trend line?**
   - **Decision**: 3 data points minimum for trend direction classification. With 2 points, show only the delta (no direction label). With < 2, show "Insufficient data for trend analysis."
   - Rationale: Linear regression with < 3 points is mathematically degenerate. Two-point delta is still useful information.

3. **Q: Should there be a global limit on total active schedules across all users?**
   - **Decision**: Yes. **Per-user: 10 active schedules. System-wide: 100 active schedules.** With `MAX_CONCURRENT_SCHEDULED = 3` and a 60-second poll, this means a schedule could wait up to ~33 minutes in the worst case (100 schedules, 3 concurrent, each taking ~1-2 minutes). This is acceptable for a background monitoring system.
   - Rationale: Prevents resource exhaustion while supporting reasonable enterprise usage (10 brands per user).

4. **Q: How to handle the case where a scheduled run produces significantly different results from a manual run done the same day?**
   - **Decision**: Both produce separate Snapshots. The TrendEngine uses **all Snapshots regardless of trigger source** (`triggered_by = "manual"` or `"scheduled"`). This is expected -- AI platform results naturally vary between runs.
   - Rationale: Including both sources gives a more complete picture. The TrendChart marks triggered_by for visual differentiation.

5. **Q: Should the monitoring schedule be editable from the Dashboard UI or only via chat?**
   - **Decision**: **Both**. Chat for creation (with confirmation step per Chat-first principle). Dashboard MonitoringTab for viewing, editing (inline), pausing, resuming, and deleting. The REST API supports both interaction patterns identically.
   - Rationale: Chat-first for setup; Dashboard for ongoing management. Users should not be forced back to chat just to pause a schedule.

6. **Q: What happens to a monitoring schedule when the associated Entity is deleted?**
   - **Decision**: CASCADE delete (`FK ondelete="CASCADE"`). The schedule and its alerts are deleted along with the entity. Additionally, the headless pipeline runner checks entity existence at the start of `_launch_scheduled_analysis()` as a safety net (in case the entity is deleted between poll queries).
   - Rationale: An entity deletion is a deliberate action. There is no use for a schedule without its entity.

---

## Appendix A: Scheduler Sequence Diagram

```
[Scheduler Loop (every 60s)]
    |
    |-- Check: _concurrency_semaphore.locked()?
    |   |-- YES: Skip this poll, log debug
    |   |-- NO:  Continue
    |
    |-- Query: SELECT * FROM monitoring_schedules
    |          WHERE status = 'active' AND next_run_at <= now()
    |
    |-- For each due schedule:
    |
    |   [Validate: Entity still exists?]
    |       |-- NO: Log warning, skip
    |       |-- YES: Continue
    |
    |   [MonitoringService.record_run_started()]
    |       |-- Update: last_run_at = now(), total_runs += 1
    |       |-- Calculate: next_run_at = calculate_next_run(frequency, preferred_hour, timezone)
    |       |-- Check: max_runs / end_date -> COMPLETED if limit reached
    |
    |   [TaskService.create_task()]
    |       |-- Create AnalysisTask (session_id=NULL, monitoring_schedule_id=X)
    |
    |   [asyncio.create_task(_run_pipeline_headless())]
    |       |-- _running_tasks.add(task)
    |       |-- async with _concurrency_semaphore:
    |       |   |-- sentinel_session_id = "headless-{task_id}"
    |       |   |-- workflow = get_compiled_workflow()
    |       |   |-- initial_state = {..., session_id=sentinel, platform_filter=schedule.platforms}
    |       |   |-- final_state = await workflow.ainvoke(initial_state, config)
    |       |   |
    |       |   |-- [Agent nodes execute normally]
    |       |   |   |-- emit_to_session() -> silent return (no WS clients)
    |       |   |   |-- save_and_send_artifact() -> detects "headless-" prefix
    |       |   |   |   -> skips Message persistence, returns ""
    |       |   |   |-- Snapshot creation works normally
    |       |   |
    |       |   |-- ON SUCCESS:
    |       |   |   |-- TaskService.complete_task(snapshot_id=X)
    |       |   |   |-- MonitoringService.record_run_completed()
    |       |   |   |-- AlertService.generate_alerts_for_snapshot()
    |       |   |   |   |-- TrendEngine.detect_significant_change()
    |       |   |   |   |-- If significant: CREATE MonitoringAlert
    |       |   |
    |       |   |-- ON FAILURE:
    |       |       |-- TaskService.fail_task(error_message, error_stage)
    |       |       |-- MonitoringService.record_run_failed()
    |       |       |   |-- consecutive_failures += 1
    |       |       |   |-- If >= 3: status -> ERROR, create alert
    |       |
    |       |-- _running_tasks.discard(task)  [via done_callback]
    |
    |-- Sleep(60s)

[Shutdown]
    |-- Cancel _scheduler_task (poll loop)
    |-- Cancel all _running_tasks (pipeline tasks)
    |-- Wait with 30s timeout
    |-- Clear _running_tasks
```

## Appendix B: Chat-First Interaction Examples

**Creating a monitoring schedule (with confirmation):**
```
User: "I want to track Xiaomi's AI visibility automatically."
AI:   "I can set up automatic monitoring for Xiaomi. How often would you like
       me to run the analysis?
       - Daily
       - Weekly (recommended)
       - Biweekly
       - Monthly"
User: "Weekly is fine."
AI:   "I will set up weekly monitoring for Xiaomi with these settings:
       - Frequency: Every week
       - Execution time: 11:00 AM (Beijing time)
       - Alert threshold: BWVS change > 10 points
       - Platforms: Doubao + Hunyuan (API-based)

       Shall I proceed?"
User: "Yes."
AI:   "Monitoring schedule created! I will automatically analyze Xiaomi every
       week at 11:00 AM (Beijing time). You will be notified if the BWVS
       changes by more than 10 points. You can view trends on the Dashboard
       under the Monitoring tab."
```

**Alert delivered in chat:**
```
[System notification in chat session]
AI:   "Alert: Xiaomi's BWVS index dropped from 52.3 to 39.8 (-12.5 points,
       -23.9%) in this week's automated analysis. This is a significant decline.

       Key changes:
       - Mention rate decreased on DeepSeek (-18%)
       - Sentiment shifted from positive to neutral on Kimi
       - Coverage on Hunyuan remained stable

       Would you like me to drill into the details of the DeepSeek decline?"
User: "Yes, tell me more about DeepSeek."
AI:   [Invokes drill_down_analysis tool with focus_dimension=platform,
       focus_value=deepseek, using the latest scheduled Snapshot data]
```

**Checking monitoring status:**
```
User: "How is my brand monitoring going?"
AI:   "Here is the status of your monitoring schedules:

       Xiaomi (weekly, active):
       - Last run: Feb 21 (BWVS: 52.3, +3.1 vs previous)
       - Next run: Feb 28 at 11:00 AM
       - Trend: Improving over last 4 weeks
       - 0 alerts this week

       Huawei (biweekly, active):
       - Last run: Feb 14 (BWVS: 41.7, -2.3 vs previous)
       - Next run: Feb 28 at 11:00 AM
       - Trend: Slightly declining
       - 1 alert (medium severity)

       Would you like to see the trend charts on the Dashboard?"
```

## Appendix C: Frontend Component Wireframes

### C.1 NotificationBell & Panel

```
Header:  [...other items...]  [Bell Icon (3)]  [User Avatar]
                                      |
                                      v
         +-- NotificationPanel (380px) -------------------------+
         |  Notifications (3 unread)              [Mark all read] |
         |                                                         |
         |  +-- AlertCard (unread, bg-tertiary) ----------------+ |
         |  | [4px red border]  [!] CRITICAL                     | |
         |  |  Xiaomi BWVS -12.5 pts (-23.9%)                   | |
         |  |  2 hours ago                                        | |
         |  +----------------------------------------------------+ |
         |                                                         |
         |  +-- AlertCard (unread, bg-tertiary) ----------------+ |
         |  | [4px amber border]  [!] HIGH                       | |
         |  |  Huawei mention rate dropped 15%                   | |
         |  |  1 day ago                                          | |
         |  +----------------------------------------------------+ |
         |                                                         |
         |  +-- AlertCard (read, transparent bg) ---------------+ |
         |  | [4px gray border]  [i] LOW                         | |
         |  |  Xiaomi sentiment improved slightly                | |
         |  |  3 days ago                                         | |
         |  +----------------------------------------------------+ |
         |                                                         |
         |  [View all notifications ->]                            |
         +---------------------------------------------------------+
```

### C.2 ScheduleStatusCard Edit Mode

```
+-- ScheduleStatusCard (normal) --------------------------------+
|  [green pulse dot] Active  |  Weekly  |  Next: Feb 28 11:00 AM |
|  Threshold: 10 pts         [Pause]  [Edit Settings]            |
+---------------------------------------------------------------+

    |  (click Edit Settings)
    v

+-- ScheduleStatusCard (edit mode, inline expand) --------------+
|  [green pulse dot] Active                                      |
|                                                                |
|  Frequency:  [Daily] [*Weekly*] [Biweekly] [Monthly]  (pills) |
|                                                                |
|  Time:       [11:00 AM  v]  (dropdown)                         |
|  Timezone:   Asia/Shanghai                                     |
|                                                                |
|  Alert threshold:  [10.0] points                               |
|                                                                |
|  [Save]  [Cancel]           [Delete Schedule] (red, small)     |
|                                                                |
|  (Delete triggers confirmation dialog)                         |
+---------------------------------------------------------------+
```
