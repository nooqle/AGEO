# Cycle 3: Multi-Turn Dialogue + Async Task Resilience + A1 Quality

> **Document Status**: Reviewed (v1.1 -- Architecture & Technical Review Integrated)
> **Author**: Marty Cagan (Product Manager)
> **Created**: 2026-02-21
> **Last Reviewed**: 2026-02-21
> **Reviewers**: Martin Fowler (Architecture), John Carmack (Technical)
> **Priority**: P1
> **Estimated Effort**: ~80h (10-11 days)
> **Dependency Documents**:
>   - `D:\AGEO\docs\reform-plan.md` (Reform Plan v2.0)
>   - `D:\AGEO\docs\prd-cycle2-snapshot-report-wait.md` (Cycle 2 PRD)
>   - `D:\AGEO\docs\ux-design-cycle2-snapshot-report-wait.md` (Cycle 2 UX Design)

> **Review Change Log (v1.1)**:
> - **C1/T2**: stage_results_cache 并发写入 -- 改用 SELECT FOR UPDATE 行锁 + 事务保护
> - **C2/T1**: events.py 双写职责 -- 不修改 events.py 签名，在节点层关键里程碑处调用 TaskService
> - **C3**: AnalysisTask 与 Session 一对多 -- selective_refetch 从 Snapshot.raw_data 读取基础数据
> - **C4/T5**: 9 工具 LLM 路由 -- context summary 含工具可用性提示 + 工具 description 强区分 + E2E routing 测试矩阵
> - **C5/T3**: selective_refetch 合并策略 -- V1 简化为 A4 平台过滤模式
> - **C6/T9**: 无 Celery 安全网 -- 新增 Orphan Task Recovery 机制
> - **C7**: compare_snapshots_node 直接访问 DB -- 允许但需代码注释说明设计差异
> - **T4**: drill_down 需 join simulated_questions -- 补充读取 state["simulated_questions"]
> - **T6**: compare_snapshots 应用 get_snapshot 非 get_trend -- 获取完整 snapshot
> - **T7**: 断线重连 replay 去重 -- addStageResult 按 stage+resultType 去重
> - **T8**: cancel 只标记状态 -- complete_task() 检查 CANCELLED 状态

---

## 1. Background & Objectives

### 1.1 What Problem Are We Solving?

Cycle 1 built the reliability foundation (resilience model + BWVS v2). Cycle 2 established the data persistence layer (Snapshot model), enriched report content (7-chapter report), and optimized the wait experience (StageResultCard + MiniProgress). Together, they elevated the platform from "barely functional" to "single-session usable".

But three critical gaps remain that block the product from being **commercially viable**:

1. **Single-shot analysis with no follow-up capability**: Users complete an analysis and see a report. If they want to drill deeper -- "How does my brand perform specifically on DeepSeek?" or "Compare this result with last week's" -- they must start a brand new session. The Orchestrator treats every conversation as a fresh start. There is no contextual memory across turns within a session, nor any ability to reference previous Snapshots in natural language.

2. **Synchronous execution locks the browser tab**: The analysis pipeline (A1-A5) takes 1-5 minutes. Despite Cycle 2's wait experience improvements, the user MUST keep the browser tab open. If the tab is closed, the WebSocket connection drops, and while the LangGraph workflow continues server-side via MemorySaver, the user has no way to know when it finishes or to retrieve results without manually reopening the session. For enterprise users running multiple brand analyses, this is a dealbreaker.

3. **A1 data quality inconsistency**: A1 brand analysis sometimes returns sparse or malformed data -- missing `competitors`, truncated `brand_profile` fields, or incorrect industry classification. Since A1 is the foundational data source for A2-A5, any quality issue here cascades through the entire pipeline. Cycle 1 addressed A2/A4/A5 quality, but A1 was deferred.

### 1.2 Who Has This Problem? How Painful?

**Target User**: Brand marketing/operations staff who need regular, iterative AEO insights.

**Pain Severity**: Hair on fire (blocking commercial viability)

- **Multi-turn**: After receiving a report, 100% of users we've observed want to ask follow-up questions. Currently they cannot. They either give up or start over, losing context.
- **Async execution**: Enterprise users managing 5-10 brands refuse to dedicate a browser tab per brand. This is the #1 adoption blocker for multi-brand usage.
- **A1 quality**: When A1 returns bad data, the entire 3-5 minute pipeline produces a misleading report. Users lose trust after one bad experience.

### 1.3 How Do They Solve It Today?

- **Multi-turn**: Start a new session, re-type context. Or manually cross-reference the report with the chat history.
- **Async**: Keep multiple tabs open. Check back periodically. Hope nothing crashed.
- **A1 quality**: Run the same analysis multiple times and compare results manually.

### 1.4 Hypothesis & Expected Outcomes

**Hypothesis**: By enabling multi-turn follow-up analysis, async task persistence with notification, and improving A1 data quality, we can make the product viable for enterprise customers managing multiple brands.

| Metric | Current | Target |
|--------|---------|--------|
| Follow-up analysis capability | None | 3+ interaction patterns |
| Browser-tab dependency | Required | Optional (can close & return) |
| A1 data completeness rate | ~70% (estimated) | 90%+ |
| Multi-brand concurrent usage | 1 (single tab) | 5+ (async) |
| User trust after first analysis | Medium | High |

### 1.5 Alignment with Reform Plan

This Cycle directly implements **P1 (Enhance Dialogue)** from the Reform Plan:

| Reform Plan Item | Cycle 3 Module | Coverage |
|-----------------|----------------|----------|
| P1-1: Async tasks + notifications | Module 1: Task Persistence & Notification | Full |
| P1-2: Multi-turn dialogue optimization | Module 2: Multi-Turn Follow-Up | Core patterns |
| P1-3: A1 data quality improvement | Module 3: A1 Quality Hardening | Full |

### 1.6 Linkage with Cycle 1-2

```
Cycle 1 (P0)                    Cycle 2                           Cycle 3 (this)
-----------                     -------                           --------------
Resilience model          -->   Snapshot data model          -->  Task persistence model
BWVS v2 calculation       -->   7-chapter report             -->  Multi-turn report drill-down
Degradation notifications -->   StageResultCard + MiniProgress -> Async notification system
                                                                  A1 quality hardening
```

Key dependencies on Cycle 2:
- **Snapshot model**: Cycle 3 multi-turn "compare with last time" requires reading AnalysisSnapshot
- **StageResultCard**: Async task reconnection replays stage results from persisted state
- **Enhanced report**: Multi-turn drill-down references report chapters by name

---

## 2. Module 1: Task Persistence & Reconnection

### 2.1 Problem Statement

The current architecture has a subtle but critical gap: the LangGraph workflow uses `MemorySaver` (in-memory checkpointer) for state persistence. This means:

1. **Server restart = state loss**: If the server restarts while a workflow is running, all in-flight state is gone.
2. **No task registry**: There is no database table tracking "which workflows are running, which finished, which failed". The only way to know is to hold a WebSocket connection.
3. **Reconnection is fragile**: `rebuild_state_from_db()` in `websocket_langgraph.py` attempts to reconstruct state from Message records, but this is a "best effort" reconstruction that loses orchestrator context.

The Reform Plan's P1-1 calls for "close the page and come back to see results". This requires a lightweight task persistence layer.

### 2.2 User Stories

- As a marketing manager, I want to start a brand analysis and close my browser, so that I can continue working on other tasks.
- As a marketing manager, I want to see a list of my running/completed analyses across all brands, so that I can manage multiple concurrent analyses.
- As a marketing manager, I want to receive a notification when my analysis completes, so that I know when to review the results.

### 2.3 Success Metrics

- **Primary**: User can close browser tab after starting analysis and find completed results upon return
- **Secondary**: Task list shows accurate status for all analyses (running/completed/failed)
- **Guardrail**: No regression in existing WebSocket real-time experience for users who stay on the page

### 2.4 Data Model: AnalysisTask

**New file**: `aeo-platform/backend/app/models/task.py`

```python
"""Analysis Task model -- tracks lifecycle of each analysis pipeline execution."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.snapshot import JSONText  # Reuse from Cycle 2

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.session import Session
    from app.models.user import User


class TaskStatus(str, PyEnum):
    """Task lifecycle status."""
    PENDING = "pending"       # Created, not yet started
    RUNNING = "running"       # Workflow is executing
    COMPLETED = "completed"   # Successfully finished
    FAILED = "failed"         # Failed with error
    CANCELLED = "cancelled"   # User cancelled


class AnalysisTask(Base):
    """Tracks each analysis pipeline execution.

    Created when user initiates a brand analysis.
    Updated as workflow progresses through A1-A5.
    Referenced by frontend for task list and reconnection.

    Design note: AnalysisTask has a many-to-one relationship with Session.
    A single session may contain multiple tasks over time (e.g., initial analysis
    followed by selective_refetch). Each task represents one pipeline execution.
    """

    __tablename__ = "analysis_tasks"

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
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Task metadata
    brand_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    current_stage: Mapped[str] = mapped_column(
        String(10), default="", nullable=False
    )  # "A1", "A2", ..., "A5", ""

    # Progress tracking (mirrors execution_progress event data)
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    progress_message: Mapped[str] = mapped_column(
        String(255), default="", nullable=False
    )

    # Stage results snapshot (for reconnection replay)
    # Stores the stage_result events so reconnecting clients can replay them
    #
    # CONCURRENCY NOTE (Review C1/T2): This JSON column is subject to concurrent
    # read-modify-write from multiple async tasks. All writes to this field MUST
    # use SELECT FOR UPDATE row-level locking within a transaction:
    #   async with db.begin():
    #       task = await db.execute(
    #           select(AnalysisTask).where(...).with_for_update()
    #       )
    #       # modify stage_results_cache
    #       await db.flush()
    stage_results_cache: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # Result references
    snapshot_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Error info (if failed)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stage: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Notification preferences
    notify_on_complete: Mapped[bool] = mapped_column(
        default=True, nullable=False
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship("User", backref="analysis_tasks")
    session: Mapped["Session"] = relationship("Session", backref="analysis_tasks")
    entity: Mapped["Entity | None"] = relationship("Entity", backref="analysis_tasks")
```

**Design Decisions**:

1. **Separate from Snapshot**: AnalysisTask tracks the *execution lifecycle* (running/failed/completed). AnalysisSnapshot stores the *analysis results*. A completed task links to a snapshot via `snapshot_id`.
2. **stage_results_cache**: When a `stage_result` event fires, the TaskService also persists it to this JSON field. Upon WebSocket reconnection, the frontend replays these cached events to restore the wait experience.
3. **No Celery dependency for V1**: The existing `celery_config.py` and `redis_client.py` are present but unused in the current LangGraph workflow. V1 task persistence operates purely via database polling -- the workflow already runs as an async Python coroutine. We simply track its lifecycle in the database. Celery integration is deferred to P2 (scheduled tasks).
4. **Session-to-Task is one-to-many** (Review C3): A session can have multiple tasks (initial analysis + subsequent selective_refetch). Each task creates its own Snapshot on completion.
5. **Concurrent write safety** (Review C1/T2): The `stage_results_cache` JSON column uses `SELECT FOR UPDATE` row-level locking within explicit transactions (`async with db.begin()`) to prevent lost-update from concurrent read-modify-write. See TaskService.append_stage_result() for implementation.

### 2.5 TaskService

**New file**: `aeo-platform/backend/app/services/task_service.py`

```python
"""Task lifecycle management service."""

class TaskService:
    """Manages AnalysisTask CRUD and lifecycle transitions.

    IMPORTANT (Review C2/T1): TaskService is NOT injected into events.py.
    Instead, it is called directly at key milestones within agent node
    functions (e.g., a1_brand_node, a5_analytics_node). This preserves
    the existing events.py function signatures and avoids responsibility
    bloat in the event system.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_task(
        self,
        *,
        user_id: UUID,
        session_id: UUID,
        brand_name: str,
        entity_id: UUID | None = None,
    ) -> AnalysisTask:
        """Create a new analysis task when user initiates analysis."""

    async def update_progress(
        self,
        task_id: UUID,
        *,
        stage: str,
        progress: float,
        message: str,
        status: TaskStatus = TaskStatus.RUNNING,
    ) -> None:
        """Update task progress.

        Called at key milestones in agent nodes (not from events.py).
        Milestone points: A1 start, A1 complete, A2 complete, A3 complete,
        A4 start (per platform), A4 complete, A5 start, A5 complete.
        """

    async def append_stage_result(
        self,
        task_id: UUID,
        stage_result: dict,
    ) -> None:
        """Append a stage_result to the cache (for reconnection replay).

        CONCURRENCY (Review C1/T2): Uses SELECT FOR UPDATE within a
        transaction to prevent lost updates from concurrent writes:

            async with self.db.begin():
                stmt = select(AnalysisTask).where(
                    AnalysisTask.id == task_id
                ).with_for_update()
                task = (await self.db.execute(stmt)).scalar_one()
                cache = task.stage_results_cache or []
                cache.append(stage_result)
                task.stage_results_cache = cache
                await self.db.flush()
        """

    async def complete_task(
        self,
        task_id: UUID,
        *,
        snapshot_id: UUID | None = None,
    ) -> AnalysisTask:
        """Mark task as completed, optionally linking to a snapshot.

        CANCELLATION CHECK (Review T8): Before marking COMPLETED, checks
        if task.status == CANCELLED. If so, skips the transition and returns
        early -- the user's cancellation intent takes precedence.
        """

    async def fail_task(
        self,
        task_id: UUID,
        *,
        error_message: str,
        error_stage: str,
    ) -> AnalysisTask:
        """Mark task as failed with error details."""

    async def cancel_task(
        self,
        task_id: UUID,
    ) -> AnalysisTask:
        """Mark task as cancelled.

        NOTE (Review T8): This only marks the database status as CANCELLED.
        It does NOT stop the running LangGraph workflow. The workflow will
        continue to completion, but complete_task() will detect the CANCELLED
        status and skip the COMPLETED transition.
        """

    async def get_user_tasks(
        self,
        user_id: UUID,
        *,
        status: TaskStatus | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[AnalysisTask], int]:
        """Get tasks for a user, optionally filtered by status."""

    async def get_task(self, task_id: UUID) -> AnalysisTask | None:
        """Get a single task by ID."""

    async def get_session_active_task(
        self, session_id: UUID
    ) -> AnalysisTask | None:
        """Get the active (PENDING/RUNNING) task for a session."""

    async def recover_orphan_tasks(self, timeout_minutes: int = 30) -> int:
        """Recover orphan tasks on server startup (Review C6/T9).

        Scans for tasks with status=RUNNING that have been running for
        longer than timeout_minutes. Marks them as FAILED with
        error_message="Server restarted during execution".

        Returns the count of recovered (marked FAILED) tasks.

        Called once during application startup (lifespan event).
        """
```

### 2.6 Orphan Task Recovery (Review C6/T9)

Since V1 does not use Celery, there is no external process manager to detect crashed workflows. We add a startup recovery mechanism as a safety net:

**Integration point**: `aeo-platform/backend/app/main.py` lifespan event

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup logic ...

    # Orphan task recovery (Review C6/T9)
    async with AsyncSessionLocal() as db:
        service = TaskService(db)
        recovered = await service.recover_orphan_tasks(timeout_minutes=30)
        if recovered > 0:
            logger.warning(f"Recovered {recovered} orphan tasks on startup")

    yield

    # ... existing shutdown logic ...
```

**Behavior**:
- On server startup, scan `analysis_tasks` for rows with `status = RUNNING` and `started_at < now() - 30 minutes`
- Mark each as `status = FAILED`, `error_message = "Server restarted during execution. Please retry."`, `completed_at = now()`
- Log count for monitoring
- Users see these as FAILED tasks with a retry option

### 2.7 Workflow Integration

**Affected files**:
- `aeo-platform/backend/app/api/v1/websocket_langgraph.py` -- task creation at workflow start
- `aeo-platform/backend/app/workflow/nodes.py` -- A1 milestone updates task progress
- `aeo-platform/backend/app/workflow/nodes_a5.py` -- A5 completion marks task complete

**NOT affected** (Review C2/T1):
- `aeo-platform/backend/app/workflow/events.py` -- events.py function signatures remain unchanged. TaskService is NOT called from events.py. Instead, task progress updates happen at key milestones within agent node functions.

**Lifecycle**:

```
User sends "analyze brand X"
    |
    v
[websocket_langgraph.py] handle_user_message_langgraph()
    |-- Create AnalysisTask (status=PENDING, brand_name="X")
    |-- Store task_id in AgentState
    |-- Start LangGraph workflow
    |
    v
[orchestrator_node.py] Routes to A1
    |
    v
[nodes.py] a1_brand_node()
    |-- TaskService.update_progress(task_id, stage="A1", progress=0.05, ...)
    |-- ... A1 logic ...
    |-- TaskService.update_progress(task_id, stage="A1", progress=0.15, ...)
    |-- TaskService.append_stage_result(task_id, stage_result_data)
    |
    ... A2 -> A3 -> A4 -> A5 (each node calls TaskService at milestones) ...
    |
[nodes_a5.py] A5 completes
    |-- Creates Snapshot (Cycle 2)
    |-- TaskService.complete_task(task_id, snapshot_id=snapshot.id)
    |   (checks CANCELLED status before transitioning -- Review T8)
    |
    v
Task status = COMPLETED (or remains CANCELLED if user cancelled)
```

**Error path**:

```
Any agent throws unrecoverable error
    |
[orchestrator_node.py] Catches error
    |-- Calls TaskService.fail_task(task_id, error_message, error_stage)
    |-- Sends error WebSocket event (existing behavior)
```

### 2.8 Reconnection Flow

When user reopens a session with a RUNNING task:

```
User opens session page
    |
    v
Frontend: GET /api/v1/tasks/session/{session_id}/active
    |
    v
If task exists and status = RUNNING:
    |-- Render MiniProgress with task.progress / task.current_stage
    |-- Replay task.stage_results_cache as StageResultCard components
    |   (deduplicated by stage+resultType -- Review T7)
    |-- Connect WebSocket for live updates
    |
If task exists and status = COMPLETED:
    |-- Show "analysis completed" banner with link to report
    |-- task.snapshot_id -> load Snapshot -> render report
    |
If task exists and status = FAILED:
    |-- Show error message with retry option
```

### 2.9 Task List API

**New file**: `aeo-platform/backend/app/api/v1/tasks.py`

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/tasks` | List user's tasks (paginated, filterable by status) |
| GET | `/api/v1/tasks/{task_id}` | Get task details |
| GET | `/api/v1/tasks/session/{session_id}/active` | Get active task for a session |
| POST | `/api/v1/tasks/{task_id}/cancel` | Cancel a running task (marks status only -- Review T8) |

**Task list response**:

```json
{
  "tasks": [
    {
      "id": "uuid",
      "brand_name": "Xiaomi",
      "status": "completed",
      "current_stage": "A5",
      "progress": 1.0,
      "progress_message": "Analysis complete",
      "snapshot_id": "uuid",
      "created_at": "2026-02-21T10:00:00Z",
      "completed_at": "2026-02-21T10:03:42Z",
      "session_id": "uuid",
      "entity_id": "uuid"
    },
    {
      "id": "uuid",
      "brand_name": "Huawei",
      "status": "running",
      "current_stage": "A4",
      "progress": 0.65,
      "progress_message": "Fetching from DeepSeek...",
      "snapshot_id": null,
      "created_at": "2026-02-21T10:05:00Z",
      "completed_at": null,
      "session_id": "uuid",
      "entity_id": "uuid"
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

### 2.10 Frontend: Task Status Awareness

**Affected files**:
- `D:\AGEO\frontend\src\stores\conversationStore.ts` -- add `activeTask` state
- `D:\AGEO\frontend\src\app\chat\[sessionId]\page.tsx` -- check for active task on mount
- `D:\AGEO\frontend\src\components\chat\MiniProgress.tsx` -- restore from task data
- `D:\AGEO\frontend\src\components\chat\StageResultCard.tsx` -- replay cached stage results

**New TypeScript types**:

```typescript
// types/task.ts

export interface AnalysisTask {
  id: string;
  brand_name: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  current_stage: string;
  progress: number;
  progress_message: string;
  snapshot_id: string | null;
  session_id: string;
  entity_id: string | null;
  error_message: string | null;
  error_stage: string | null;
  stage_results_cache: StageResult[] | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}
```

**Session page mount behavior** (pseudocode):

```typescript
// page.tsx -- useEffect on mount
const activeTask = await api.getActiveTask(sessionId);

if (activeTask) {
  if (activeTask.status === 'running') {
    // Restore progress UI
    setExecutionProgress({ progress: activeTask.progress, message: activeTask.progress_message });
    setIsAgentExecuting(true);

    // Replay cached stage results (with deduplication -- Review T7)
    if (activeTask.stage_results_cache) {
      activeTask.stage_results_cache.forEach(sr => addStageResult(sr));
    }

    // Connect WebSocket for live updates
    connectWebSocket(sessionId);
  } else if (activeTask.status === 'completed') {
    // Show completion banner
    showCompletionBanner(activeTask);
  } else if (activeTask.status === 'failed') {
    // Show error with retry
    showErrorBanner(activeTask);
  }
}
```

**Stage result replay deduplication** (Review T7):

```typescript
// conversationStore.ts -- addStageResult action
addStageResult: (sr: StageResult) => {
  set((state) => {
    // Deduplicate by stage + resultType to prevent duplicates on reconnection replay
    const key = `${sr.stage}:${sr.resultType}`;
    const exists = state.stageResults.some(
      existing => `${existing.stage}:${existing.resultType}` === key
    );
    if (exists) {
      // Replace existing entry (latest wins)
      return {
        stageResults: state.stageResults.map(existing =>
          `${existing.stage}:${existing.resultType}` === key ? sr : existing
        ),
      };
    }
    return { stageResults: [...state.stageResults, sr] };
  });
},
```

### 2.11 In-App Notification (V1)

For V1, we implement in-app notification only (no email/webhook -- those are P2):

**Mechanism**: When a task completes and the user is NOT connected via WebSocket to that session:

1. Backend: `TaskService.complete_task()` checks if session has active WebSocket connections via `manager.session_connections`.
2. If no connections: Store a notification record in a lightweight `notifications` table (or use the task itself as the notification source).
3. Frontend: On app mount (any page), poll `GET /api/v1/tasks?status=completed&unread=true` to check for newly completed tasks.
4. Display a toast notification: "Your analysis of [brand] has completed. [View Report]"

**Why not WebSocket push for notifications**: The user may not have any WebSocket connection open. Polling on page load is simpler and sufficient for V1.

**Notification display**:

```
+-- Top-right toast (auto-dismiss 10s) -------------------+
|  [check icon]  Analysis of "Xiaomi" completed            |
|  BWVS: 52.3 (Good)  |  [View Report ->]                |
+----------------------------------------------------------+
```

### 2.12 Acceptance Criteria

- [ ] **AC-1**: AnalysisTask table created via Alembic migration (SQLite + PostgreSQL compatible)
- [ ] **AC-2**: Starting a brand analysis creates an AnalysisTask with status=PENDING, then transitions to RUNNING
- [ ] **AC-3**: Each stage_result event is persisted to task.stage_results_cache (using SELECT FOR UPDATE row lock -- Review C1/T2)
- [ ] **AC-4**: Successful A5 completion transitions task to COMPLETED with snapshot_id (unless CANCELLED -- Review T8)
- [ ] **AC-5**: Workflow error transitions task to FAILED with error_message and error_stage
- [ ] **AC-6**: `GET /api/v1/tasks` returns paginated task list filtered by user
- [ ] **AC-7**: `GET /api/v1/tasks/session/{id}/active` returns the RUNNING/PENDING task for a session
- [ ] **AC-8**: Closing and reopening a session page correctly restores progress from task data
- [ ] **AC-9**: Cached stage results are replayed as StageResultCard components on reconnection (deduplicated by stage+resultType -- Review T7)
- [ ] **AC-10**: Completed task for a disconnected user shows toast notification on next page load
- [ ] **AC-11**: Existing real-time WebSocket experience is not degraded for users who stay on the page
- [ ] **AC-12**: TaskService is called at node-level milestones, NOT from events.py (Review C2/T1)
- [ ] **AC-13**: complete_task() checks for CANCELLED status before transitioning to COMPLETED (Review T8)
- [ ] **AC-14**: Orphan Task Recovery runs on server startup, marking RUNNING tasks older than 30 min as FAILED (Review C6/T9)

---

## 3. Module 2: Multi-Turn Follow-Up Analysis

### 3.1 Problem Statement

The Orchestrator (`orchestrator_node.py`) uses MiniMax Function Calling to dynamically route user messages to Agent tools (brand_analysis, persona_generation, question_simulation, answer_fetch, data_analytics). Currently, the Orchestrator treats each user message as potentially triggering the full A1-A5 pipeline. There is no mechanism for:

1. **Contextual follow-up**: "Drill deeper into the DeepSeek results" should reference the current session's `fetch_results` and filter/re-analyze, not restart the full pipeline.
2. **Snapshot comparison**: "Compare with my last analysis" should query the Snapshot table and present a delta view.
3. **Selective re-analysis**: "Re-run the analysis but only for Kimi and DeepSeek" should invoke A4 with a platform filter, then A5, skipping A1-A3.

The root cause: the Orchestrator's tool registry (`AGENT_REGISTRY`) only has "full pipeline" tools. There are no "lightweight" tools for follow-up queries.

### 3.2 User Stories

- As a marketing manager, after seeing a report, I want to ask "How does my brand perform on DeepSeek specifically?" and get a focused analysis without re-running the full pipeline.
- As a marketing manager, I want to say "Compare this with my last analysis" and see a delta comparison.
- As a marketing manager, I want to say "Re-analyze but only for Kimi" and have the system re-fetch from Kimi only, then update the report.

### 3.3 Success Metrics

- **Primary**: User can ask 3 types of follow-up questions and receive contextual responses
- **Secondary**: Follow-up responses reference existing session data (no redundant pipeline execution)
- **Guardrail**: Full pipeline analysis still works identically for first-time analysis requests

### 3.4 Approach: Orchestrator Tool Expansion

Rather than building a new conversation engine, we extend the existing Orchestrator's tool registry with follow-up-specific tools. The LLM naturally decides which tool to call based on user intent.

**New tools added to AGENT_REGISTRY**:

```python
# orchestrator_node.py -- AGENT_REGISTRY additions

{
    "name": "drill_down_analysis",
    "description": (
        "Drill deeper into specific aspects of an EXISTING analysis in this session. "
        "Examples: 'Tell me more about DeepSeek results', 'What about product recommendation questions?'. "
        "REQUIRES: A completed full analysis (fetch_results must exist in session). "
        "If no analysis data exists, DO NOT call this tool -- ask user to run a full analysis first. "
        "Uses existing fetch_results and metrics data WITHOUT re-running the pipeline."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "focus_dimension": {
                "type": "string",
                "description": "What to drill into: 'platform', 'question_category', 'competitor', 'sentiment'",
            },
            "focus_value": {
                "type": "string",
                "description": "Specific value to focus on (e.g., 'deepseek', 'product_recommendation', 'Huawei')",
            },
        },
        "required": ["focus_dimension"],
    },
},
{
    "name": "compare_snapshots",
    "description": (
        "Compare current analysis results with a PREVIOUS analysis snapshot. "
        "Examples: 'Compare with last time', 'How has my score changed?', 'Show me the trend'. "
        "REQUIRES: At least 2 snapshots for the same entity (entity_id must exist in session). "
        "If only 1 or 0 snapshots exist, DO NOT call this tool -- inform user more data is needed."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "comparison_type": {
                "type": "string",
                "description": "'vs_previous' (default) or 'vs_specific' (compare specific snapshots)",
            },
        },
    },
},
{
    "name": "selective_refetch",
    "description": (
        "Re-run analysis for SPECIFIC PLATFORMS only, keeping results from other platforms. "
        "Examples: 'Re-analyze Kimi results', 'Fetch again from DeepSeek'. "
        "REQUIRES: A completed full analysis in this session (simulated_questions must exist). "
        "Runs A4 for selected platforms only, merges with existing results, then A5 to regenerate report."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "platforms": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of platforms to re-fetch: 'kimi', 'deepseek', 'doubao', 'hunyuan'",
            },
        },
        "required": ["platforms"],
    },
},
```

**Tool description design notes** (Review C4): Each tool description now explicitly states its REQUIRES preconditions and includes negative guidance ("DO NOT call this tool if..."). This helps the LLM distinguish between the 9 available tools (6 existing + 3 new) and reduces misrouting risk.

### 3.5 New Agent Nodes

**3.5.1 drill_down_node**

**New file**: `aeo-platform/backend/app/workflow/nodes_followup.py`

This node does NOT re-run the pipeline. It reads existing state data (`fetch_results`, `metrics`, `report`, `simulated_questions`) and uses LLM to generate a focused analysis.

```python
async def drill_down_node(state: AgentState) -> Command:
    """Generate focused drill-down analysis from existing data.

    Reads: fetch_results, metrics, report, brand_profile, simulated_questions from state.
    Does NOT invoke any Agent pipeline.
    Uses LLM to generate targeted analysis based on focus_dimension/focus_value.
    Sends result via reply_delta (chat response, not a full report).
    """
    session_id = state["session_id"]
    tool_args = state.get("tool_call_args") or {}
    focus_dimension = tool_args.get("focus_dimension", "platform")
    focus_value = tool_args.get("focus_value", "")

    fetch_results = state.get("fetch_results") or []
    metrics = state.get("metrics") or {}
    brand_profile = state.get("brand_profile") or {}
    simulated_questions = state.get("simulated_questions") or []  # Review T4

    # Precondition check (Review T5): If no fetch_results exist,
    # return a helpful error instead of generating empty analysis
    if not fetch_results:
        error_msg = (
            "No analysis data available in this session. "
            "Please run a full brand analysis first before drilling down."
        )
        await send_reply_event(session_id, error_msg, is_delta=False, is_complete=True)
        return Command(update={
            "orchestrator_reply": error_msg,
            "execution_status": "completed",
        })

    # Filter data based on focus dimension
    # Includes simulated_questions for question_category drill-down (Review T4)
    filtered_data = _filter_by_dimension(
        fetch_results, metrics, simulated_questions,
        focus_dimension, focus_value
    )

    # Generate focused analysis via LLM
    analysis = await _generate_drill_down(
        brand_profile, filtered_data, focus_dimension, focus_value
    )

    # Send as chat reply (not Canvas artifact)
    await send_reply_event(session_id, analysis, is_delta=False, is_complete=True)

    return Command(update={
        "orchestrator_reply": analysis,
        "execution_status": "completed",
    })
```

**3.5.2 compare_snapshots_node**

```python
async def compare_snapshots_node(state: AgentState) -> Command:
    """Compare current analysis with previous snapshot.

    Design note (Review C7): This node directly accesses the DB layer
    (AsyncSessionLocal + SnapshotService) rather than going through the
    Orchestrator's tool result pattern. This is an intentional design
    difference -- follow-up nodes are "read-only queries" that need DB
    access for historical data, unlike pipeline nodes (A1-A5) that
    operate on in-memory state. This pattern is acceptable but should
    not be extended to pipeline nodes.

    Uses get_snapshot() to retrieve full snapshot data (Review T6),
    not get_trend() which only returns summary/metadata.
    """
    session_id = state["session_id"]
    entity_id = state.get("entity_id")

    if not entity_id:
        await send_reply_event(
            session_id,
            "Currently there is no brand entity to compare. Please complete a full analysis first.",
            is_delta=False, is_complete=True,
        )
        return Command(update={"execution_status": "completed"})

    async with AsyncSessionLocal() as db:
        service = SnapshotService(db)
        # Get the latest 2 full snapshots (Review T6: use get_snapshot, not get_trend)
        snapshots = await service.list_snapshots(entity_id, limit=2, order_by="desc")

    if len(snapshots) < 2:
        await send_reply_event(
            session_id,
            "Only one analysis record is available. Please run the analysis at least twice to enable comparison.",
            is_delta=False, is_complete=True,
        )
        return Command(update={"execution_status": "completed"})

    # Load full snapshot data for comparison (Review T6)
    async with AsyncSessionLocal() as db:
        service = SnapshotService(db)
        snapshot_old = await service.get_snapshot(snapshots[1].id)  # older
        snapshot_new = await service.get_snapshot(snapshots[0].id)  # newer

    # Generate comparison via LLM
    comparison = await _generate_comparison(
        snapshot_old.raw_data, snapshot_new.raw_data, state.get("brand_profile")
    )

    await send_reply_event(session_id, comparison, is_delta=False, is_complete=True)

    return Command(update={
        "orchestrator_reply": comparison,
        "execution_status": "completed",
    })
```

**3.5.3 selective_refetch_node (V1 Simplified -- Review C5/T3)**

The original design proposed a complex merge strategy. Based on technical review, V1 simplifies to a **platform filter mode**: set `platform_filter` in state, let A4 read it to filter platforms, then A5 regenerates from merged results.

```python
async def selective_refetch_node(state: AgentState) -> Command:
    """Re-fetch from selected platforms and regenerate report.

    V1 SIMPLIFIED APPROACH (Review C5/T3):
    Instead of a complex merge node, we use a platform filter pattern:
    1. Read the LATEST Snapshot.raw_data for the entity to get baseline data
       (existing fetch_results from unselected platforms) -- Review C3
    2. Set state["platform_filter"] = requested platforms
    3. Route to A4 which reads platform_filter and only fetches those platforms
    4. After A4, merge: replace selected-platform results, keep unselected from baseline
    5. Route to A5 to regenerate report from merged data
    6. Create a new Snapshot with merged results (Review C5)

    Precondition: simulated_questions must exist in state (from prior full analysis).
    """
    session_id = state["session_id"]
    tool_args = state.get("tool_call_args") or {}
    platforms = tool_args.get("platforms", [])

    # Precondition check (Review T5)
    simulated_questions = state.get("simulated_questions") or []
    if not simulated_questions:
        error_msg = (
            "No analysis data available in this session. "
            "Please run a full brand analysis first before selective re-fetch."
        )
        await send_reply_event(session_id, error_msg, is_delta=False, is_complete=True)
        return Command(update={
            "orchestrator_reply": error_msg,
            "execution_status": "completed",
        })

    # Load baseline fetch_results from latest Snapshot (Review C3)
    entity_id = state.get("entity_id")
    baseline_fetch_results = []
    if entity_id:
        async with AsyncSessionLocal() as db:
            service = SnapshotService(db)
            latest = await service.get_latest_snapshot(entity_id)
            if latest and latest.raw_data:
                baseline_fetch_results = latest.raw_data.get("fetch_results", [])

    # Merge strategy (Review C5):
    # - Keep fetch_results from UNSELECTED platforms (from baseline)
    # - Selected platforms will be re-fetched by A4
    unselected_results = [
        r for r in baseline_fetch_results
        if r.get("platform") not in platforms
    ]

    return Command(
        update={
            "platform_filter": platforms,           # A4 reads this to filter
            "baseline_fetch_results": unselected_results,  # For post-A4 merge
            "execution_status": "running",
        },
        goto="a4_fetch",  # Route to existing A4 node with filter
    )
```

**Post-A4 merge** (in A4 or a small merge step before A5):
```python
# After A4 completes with filtered results:
# merged = state["baseline_fetch_results"] + new_a4_results
# state["fetch_results"] = merged
# Then proceed to A5 which regenerates report from merged data
# A5 creates a new Snapshot with the merged results (Review C5)
```

### 3.6 Graph Topology Update

**Affected file**: `aeo-platform/backend/app/workflow/graph.py`

```python
# Add new follow-up nodes
from app.workflow.nodes_followup import (
    drill_down_node,
    compare_snapshots_node,
    selective_refetch_node,
)

workflow.add_node("drill_down", drill_down_node)
workflow.add_node("compare_snapshots", compare_snapshots_node)
workflow.add_node("selective_refetch", selective_refetch_node)

# drill_down and compare_snapshots return directly to orchestrator
for node in ["drill_down", "compare_snapshots"]:
    workflow.add_edge(node, "orchestrator")

# selective_refetch routes to a4_fetch (not back to orchestrator)
# A4 -> A5 -> orchestrator is the existing pipeline path
workflow.add_edge("selective_refetch", "a4_fetch")
```

### 3.7 Orchestrator Routing Update

**Affected file**: `aeo-platform/backend/app/workflow/orchestrator_node.py`

The Orchestrator's tool-to-node mapping needs to include the new tools:

```python
TOOL_TO_NODE: dict[str, str] = {
    "brand_analysis": "a1_brand",
    "persona_generation": "a2_persona",
    "question_simulation": "a3_question",
    "answer_fetch": "a4_fetch",
    "data_analytics": "a5_analytics",
    # New follow-up tools
    "drill_down_analysis": "drill_down",
    "compare_snapshots": "compare_snapshots",
    "selective_refetch": "selective_refetch",
}
```

### 3.8 Context Enrichment for Orchestrator (Enhanced -- Review C4)

For the Orchestrator LLM to correctly choose follow-up tools, it needs to know what data already exists in the session AND which tools are available given the current state.

**Enhancement**: Add a "session context summary" with **tool availability hints** to the Orchestrator's system prompt dynamically:

```python
def _build_context_summary(state: AgentState) -> str:
    """Build a summary of what data exists in the current session.

    Includes tool availability hints (Review C4) to help LLM
    distinguish between 9 tools and avoid misrouting.
    """
    parts = []
    available_tools = []
    unavailable_tools = []

    if state.get("brand_profile"):
        brand = state["brand_profile"]
        parts.append(f"- Brand analyzed: {brand.get('brand_name', 'unknown')}")
        parts.append(f"- Industry: {brand.get('industry', 'unknown')}")

    if state.get("competitors"):
        names = [c.get("name", "") for c in state["competitors"][:5]]
        parts.append(f"- Competitors identified: {', '.join(names)}")

    if state.get("fetch_results"):
        parts.append(f"- Fetch results available: {len(state['fetch_results'])} questions")
        available_tools.append("drill_down_analysis (can analyze existing results)")
        available_tools.append("selective_refetch (can re-fetch specific platforms)")
    else:
        unavailable_tools.append("drill_down_analysis (no fetch_results yet)")
        unavailable_tools.append("selective_refetch (no prior analysis yet)")

    if state.get("metrics"):
        m = state["metrics"]
        parts.append(f"- BWVS score: {m.get('bwvs_index', 'N/A')}")

    if state.get("entity_id"):
        parts.append(f"- Entity ID: {state['entity_id']} (Snapshot history available)")
        available_tools.append("compare_snapshots (can compare with previous analyses)")
    else:
        unavailable_tools.append("compare_snapshots (no entity_id yet)")

    if not parts:
        summary = "No analysis data in current session yet."
    else:
        summary = "Current session data:\n" + "\n".join(parts)

    # Tool availability hints (Review C4)
    if available_tools:
        summary += "\n\nAvailable follow-up tools:\n" + "\n".join(f"  - {t}" for t in available_tools)
    if unavailable_tools:
        summary += "\n\nUnavailable tools (missing prerequisites):\n" + "\n".join(f"  - {t}" for t in unavailable_tools)

    return summary
```

This summary is injected into the Orchestrator's system prompt before each LLM call, enabling the LLM to make informed routing decisions.

### 3.9 Acceptance Criteria

- [ ] **AC-15**: Orchestrator correctly routes "Tell me more about DeepSeek" to drill_down_node when session has existing data
- [ ] **AC-16**: drill_down_node generates a focused platform-specific analysis from existing fetch_results and simulated_questions (Review T4)
- [ ] **AC-17**: drill_down_node returns helpful error when no fetch_results exist (precondition check -- Review T5)
- [ ] **AC-18**: "Compare with last time" routes to compare_snapshots_node and displays delta comparison using full snapshot data (Review T6)
- [ ] **AC-19**: compare_snapshots_node gracefully handles < 2 snapshots with user-friendly message
- [ ] **AC-20**: "Re-analyze Kimi only" routes to selective_refetch_node and only fetches from Kimi
- [ ] **AC-21**: selective_refetch reads baseline from latest Snapshot.raw_data (Review C3), merges selected-platform results (replace), keeps unselected (preserve), creates new Snapshot (Review C5)
- [ ] **AC-22**: selective_refetch returns helpful error when no simulated_questions exist (precondition check -- Review T5)
- [ ] **AC-23**: Full pipeline analysis (first-time "Analyze brand X") still works identically
- [ ] **AC-24**: Orchestrator system prompt includes session context summary with tool availability hints (Review C4)
- [ ] **AC-25**: New tools are registered in AGENT_REGISTRY with clear descriptions including REQUIRES preconditions (Review C4)
- [ ] **AC-26**: compare_snapshots_node has code comment explaining why it directly accesses DB layer (Review C7)
- [ ] **AC-27**: E2E routing test matrix: verify correct tool selection for at least 10 representative user messages covering all 9 tools (Review C4)

---

## 4. Module 3: A1 Quality Hardening

### 4.1 Problem Statement

A1 (`a1_brand_node` in `nodes.py`) uses LLM to generate brand profile and competitor data. Known issues:

1. **Sparse competitor data**: Sometimes returns 0-2 competitors instead of the expected 3-5, or competitors are irrelevant (e.g., generic industry players instead of direct competitors).
2. **Missing brand_profile fields**: Fields like `core_products`, `brand_keywords`, `brand_positioning` are sometimes empty strings or omitted entirely.
3. **Industry misclassification**: LLM occasionally assigns incorrect industry categories (e.g., "Technology" instead of "Consumer Electronics" for Xiaomi).
4. **Inconsistent output format**: Field names vary (e.g., `main_products` vs `core_products`), causing downstream agents to miss data.

These issues cascade: A2 uses brand_profile for persona generation, A3 uses it for question templates, A5 uses competitors for competitive analysis.

### 4.2 User Stories

- As a marketing analyst, I want the brand profile to accurately reflect my brand's industry, products, and positioning, so that the downstream analysis is relevant.
- As a marketing analyst, I want at least 3 meaningful competitors identified, so that the competitive analysis has substance.

### 4.3 Success Metrics

- **Primary**: A1 output completeness rate >= 90% (all required fields populated with meaningful values)
- **Secondary**: Competitor count >= 3 per analysis
- **Guardrail**: A1 execution time does not increase by more than 50%

### 4.4 Solution: Structured Output + Validation + Retry

**Affected files**:
- `aeo-platform/backend/app/workflow/nodes.py` -- `a1_brand_node()`
- `aeo-platform/backend/prompts/brand_competition_agent.md` -- A1 prompt

**4.4.1 Output Schema Enforcement**

Define a strict schema for A1 output and validate against it:

```python
# nodes.py -- new validation

A1_REQUIRED_FIELDS = {
    "brand_profile": {
        "brand_name": str,
        "industry": str,
        "description": str,  # min 20 chars
        "core_products": list,  # min 1 item
        "brand_keywords": list,  # min 3 items
        "brand_positioning": str,
    },
    "competitors": {
        "_min_count": 3,
        "_item_fields": {
            "name": str,
            "description": str,
            "relevance_score": (int, float),
        },
    },
}


def _validate_a1_output(
    brand_profile: dict, competitors: list
) -> tuple[bool, list[str]]:
    """Validate A1 output against required schema.

    Returns:
        (is_valid, list_of_issues)
    """
    issues = []

    # Validate brand_profile
    for field, expected_type in A1_REQUIRED_FIELDS["brand_profile"].items():
        value = brand_profile.get(field)
        if value is None or value == "":
            issues.append(f"brand_profile.{field} is missing or empty")
        elif expected_type == list and (not isinstance(value, list) or len(value) == 0):
            issues.append(f"brand_profile.{field} is empty list")
        elif field == "description" and isinstance(value, str) and len(value) < 20:
            issues.append(f"brand_profile.description is too short ({len(value)} chars)")

    # Validate competitors
    min_count = A1_REQUIRED_FIELDS["competitors"]["_min_count"]
    if len(competitors) < min_count:
        issues.append(f"Only {len(competitors)} competitors found (min {min_count})")

    for i, comp in enumerate(competitors):
        for field, expected_type in A1_REQUIRED_FIELDS["competitors"]["_item_fields"].items():
            value = comp.get(field)
            if value is None or value == "":
                issues.append(f"competitor[{i}].{field} is missing")

    return (len(issues) == 0, issues)
```

**4.4.2 Retry with Focused Prompt**

If validation fails, retry once with a more explicit prompt that addresses the specific issues:

```python
# nodes.py -- a1_brand_node() enhancement

async def a1_brand_node(state: AgentState) -> Command:
    # ... existing logic ...

    brand_profile, competitors, landscape = await _call_a1_llm(brand_name, ...)

    # Validate
    is_valid, issues = _validate_a1_output(brand_profile, competitors)

    if not is_valid and retry_count == 0:
        logger.warning(f"[A1] Validation failed: {issues}. Retrying with focused prompt.")

        # Retry with explicit instructions addressing issues
        retry_prompt = _build_a1_retry_prompt(brand_name, issues, brand_profile, competitors)
        brand_profile, competitors, landscape = await _call_a1_llm(
            brand_name, override_prompt=retry_prompt
        )

        # Validate again
        is_valid, issues = _validate_a1_output(brand_profile, competitors)

    if not is_valid:
        logger.warning(f"[A1] Validation still failing after retry: {issues}. Using best-effort data.")
        # Apply field normalization (fill defaults, fix naming)
        brand_profile = _normalize_brand_profile(brand_profile)
        competitors = _normalize_competitors(competitors)
    # ... continue ...
```

**4.4.3 Field Normalization**

Handle inconsistent field names from LLM output:

```python
def _normalize_brand_profile(profile: dict) -> dict:
    """Normalize A1 brand_profile field names and fill defaults."""
    normalized = dict(profile)

    # Fix common field name variants
    field_aliases = {
        "core_products": ["main_products", "products", "key_products"],
        "brand_keywords": ["keywords", "key_words", "brand_tags"],
        "brand_positioning": ["positioning", "market_positioning"],
        "brand_name_en": ["english_name", "name_en", "en_name"],
    }

    for canonical, aliases in field_aliases.items():
        if not normalized.get(canonical):
            for alias in aliases:
                if normalized.get(alias):
                    normalized[canonical] = normalized.pop(alias)
                    break

    # Fill remaining empty required fields with safe defaults
    normalized.setdefault("core_products", [])
    normalized.setdefault("brand_keywords", [])
    normalized.setdefault("brand_positioning", "")
    normalized.setdefault("description", "")

    return normalized


def _normalize_competitors(competitors: list) -> list:
    """Normalize competitor data and ensure minimum quality."""
    normalized = []
    for comp in competitors:
        c = dict(comp)
        c.setdefault("name", "")
        c.setdefault("description", "")
        c.setdefault("relevance_score", 50)
        c.setdefault("competition_type", "direct")
        c.setdefault("core_products", [])
        if c["name"]:  # Only keep competitors with names
            normalized.append(c)
    return normalized
```

**4.4.4 A1 Prompt Enhancement**

**Affected file**: `aeo-platform/backend/prompts/brand_competition_agent.md`

Add explicit output requirements to the A1 system prompt:

```markdown
## Output Quality Requirements

1. brand_profile MUST include ALL of these fields with non-empty values:
   - brand_name, brand_name_en, industry, description (min 50 chars),
     core_products (min 1), brand_keywords (min 3), brand_positioning

2. competitors MUST include at least 3 direct competitors, each with:
   - name, description, relevance_score (1-100), competition_type,
     core_products, competitive_advantage

3. Use consistent field names as specified above. Do NOT use aliases.

4. Industry classification should be specific (e.g., "Consumer Electronics"
   not just "Technology"; "Fast Fashion" not just "Retail").
```

### 4.5 Acceptance Criteria

- [ ] **AC-28**: A1 output is validated against the required schema after LLM call
- [ ] **AC-29**: If validation fails, A1 retries once with a focused prompt addressing specific issues
- [ ] **AC-30**: After retry, remaining issues are handled via field normalization (not silent failure)
- [ ] **AC-31**: brand_profile always contains all required fields (with defaults if necessary)
- [ ] **AC-32**: competitors list always has >= 3 entries (with retry/normalization)
- [ ] **AC-33**: Field name variants (main_products vs core_products) are normalized
- [ ] **AC-34**: A1 total execution time (including retry) does not exceed 150% of current time
- [ ] **AC-35**: A1 prompt explicitly specifies output structure requirements

---

## 5. Technical Constraints

### 5.1 Must Reuse Existing Architecture

- **LangGraph workflow**: New nodes are added to the existing graph, not a separate graph
- **Orchestrator star topology**: Follow-up tools go through the same Orchestrator LLM routing
- **WebSocket event system**: Task events use existing event patterns (no new event transport)
- **Zustand stores**: Task state is added to existing conversationStore
- **SQLAlchemy models**: AnalysisTask follows the same patterns as Session/Entity/Snapshot
- **events.py preservation** (Review C2/T1): events.py function signatures remain unchanged; TaskService is invoked at node level

### 5.2 Must Not Break Existing Functionality

- Full pipeline analysis (A1-A5) must work identically
- Existing WebSocket events must continue to function
- Snapshot creation (Cycle 2) must not be affected
- StageResultCard rendering must continue working
- Dashboard and report features must remain functional

### 5.3 Database Compatibility

- AnalysisTask migration must work on both SQLite (dev) and PostgreSQL (prod)
- UUID/Enum type handling follows the same pattern as AnalysisSnapshot (Cycle 2)
- stage_results_cache concurrent access uses SELECT FOR UPDATE (PostgreSQL) / BEGIN IMMEDIATE (SQLite)

### 5.4 Performance Constraints

- Task status polling: max 1 request per 30 seconds per client
- Follow-up tools (drill_down, compare): must respond within 15 seconds (LLM-only, no pipeline)
- A1 retry: max 1 retry, total A1 time <= 30 seconds

---

## 6. Impact Summary

### 6.1 Backend File Changes

| File | Change Type | Description |
|------|------------|-------------|
| `app/models/task.py` | **New** | AnalysisTask model |
| `app/models/__init__.py` | Modify | Export AnalysisTask |
| `app/services/task_service.py` | **New** | TaskService lifecycle management (including orphan recovery) |
| `app/api/v1/tasks.py` | **New** | Task CRUD API endpoints |
| `app/workflow/nodes_followup.py` | **New** | drill_down_node, compare_snapshots_node, selective_refetch_node |
| `app/workflow/graph.py` | Modify | Add 3 new nodes + edges |
| `app/workflow/orchestrator_node.py` | Modify | Add 3 new tools to AGENT_REGISTRY + TOOL_TO_NODE + context summary with tool availability |
| `app/workflow/state.py` | Modify | Add task_id, platform_filter, baseline_fetch_results fields to AgentState |
| `app/workflow/nodes.py` | Modify | A1 validation + retry + normalization; A1 milestone TaskService calls |
| `app/workflow/nodes_a5.py` | Modify | A5 milestone TaskService.complete_task() call (with CANCELLED check) |
| `app/main.py` | Modify | Add orphan task recovery to lifespan startup |
| `prompts/brand_competition_agent.md` | Modify | A1 prompt quality requirements |
| Alembic migration | **New** | AnalysisTask table |

**NOT changed** (Review C2/T1):
| `app/workflow/events.py` | **Unchanged** | Function signatures preserved; no TaskService injection |

### 6.2 Frontend File Changes

| File | Change Type | Description |
|------|------------|-------------|
| `src/types/task.ts` | **New** | AnalysisTask TypeScript types |
| `src/services/api.ts` | Modify | Task API calls |
| `src/stores/conversationStore.ts` | Modify | activeTask state + actions + addStageResult dedup (Review T7) |
| `src/app/chat/[sessionId]/page.tsx` | Modify | Task-aware mount behavior |
| `src/components/chat/MiniProgress.tsx` | Modify | Restore progress from task data |
| `src/components/chat/StageResultCard.tsx` | Modify | Support replay from cached data |
| `src/components/layout/ChatLayout.tsx` or `ChatSidebar.tsx` | Modify | Task completion toast notification |

### 6.3 Unchanged

- Snapshot model and SnapshotService (Cycle 2)
- Report generation and rendering
- A2/A3/A4/A5 core agent logic (A4 gains platform_filter awareness)
- LLM abstraction layer
- Browser Agent (A6)
- Dashboard and Entity CRUD
- events.py function signatures (Review C2/T1)

---

## 7. Schedule Estimate

| Task | Estimate | Owner | Dependencies |
|------|----------|-------|-------------|
| **Module 1: Task Persistence** | | | |
| AnalysisTask model + Alembic migration | 2h | Backend Dev | None |
| TaskService (create/update/complete/fail/cancel/list + orphan recovery) | 5h | Backend Dev | Model |
| Task API endpoints (4 routes) | 3h | Backend Dev | Service |
| Workflow integration (node-level milestone calls, NOT events.py) | 4h | Backend Dev | Service |
| stage_results_cache with SELECT FOR UPDATE locking | 2h | Backend Dev | Service |
| Task-aware session reconnection (backend) | 3h | Backend Dev | Service |
| Frontend: types/task.ts + api calls | 1h | Frontend Dev | API |
| Frontend: session page mount task awareness | 3h | Frontend Dev | API |
| Frontend: stage result replay with dedup (Review T7) | 2.5h | Frontend Dev | Backend |
| Frontend: completion toast notification | 2h | Frontend Dev | API |
| **Module 2: Multi-Turn Follow-Up** | | | |
| nodes_followup.py: drill_down_node + compare_snapshots_node | 5h | Backend Dev | None |
| drill_down: LLM prompt + data filtering + simulated_questions join | 3h | Backend Dev + PM | None |
| compare_snapshots: full snapshot retrieval + comparison | 2.5h | Backend Dev | Cycle 2 |
| selective_refetch: V1 platform filter mode + baseline merge + new Snapshot | 5.5h | Backend Dev | None |
| graph.py topology update | 1h | Backend Dev | Nodes |
| orchestrator_node.py: tool registry + context summary + tool availability | 3.5h | Backend Dev | Nodes |
| state.py: task_id, platform_filter, baseline_fetch_results fields | 0.5h | Backend Dev | None |
| **Module 3: A1 Quality** | | | |
| A1 validation schema + _validate_a1_output | 2h | Backend Dev | None |
| A1 retry logic with focused prompt | 2h | Backend Dev | Validation |
| Field normalization functions | 1.5h | Backend Dev | None |
| A1 prompt enhancement | 1h | PM | None |
| **Testing** | | | |
| TaskService unit tests (including orphan recovery) | 2.5h | QA | Service |
| Follow-up node unit tests (including precondition checks) | 3h | QA | Nodes |
| A1 validation unit tests | 1.5h | QA | Validation |
| E2E: task persistence reconnection | 3h | QA | All Module 1 |
| E2E: multi-turn follow-up flows | 3h | QA | All Module 2 |
| E2E: tool routing test matrix (10+ representative messages across 9 tools -- Review C4) | 3h | QA | Module 2 |
| E2E: A1 quality (multiple brands) | 2h | QA | Module 3 |
| **Total** | **~80h (10-11 days)** | | |

### Delta from Draft (v1.0 -> v1.1)

| Item | v1.0 | v1.1 | Reason |
|------|------|------|--------|
| TaskService | 4h | 5h | +orphan recovery, +cancel with CANCELLED check |
| stage_results_cache | (included in events.py 2h) | 2h standalone | SELECT FOR UPDATE locking complexity |
| Frontend replay | 2h | 2.5h | +dedup logic |
| selective_refetch | 3h | 5.5h | V1 platform filter mode + baseline merge + new Snapshot |
| compare_snapshots | 2h | 2.5h | get_snapshot (full) instead of get_trend |
| orchestrator context | 3h | 3.5h | +tool availability hints |
| Testing: routing matrix | 0h | 3h | New E2E requirement |
| Testing: TaskService | 2h | 2.5h | +orphan recovery tests |
| **Total** | **~72h** | **~80h** | **+8h from review items** |

### Suggested Execution Order

```
Week 1 (Day 1-5):
  Day 1-2: Module 3 (A1 Quality) -- smallest scope, immediate quality impact
  Day 3-5: Module 1 Backend (Task model + service + API + workflow integration + orphan recovery)

Week 2 (Day 6-11):
  Day 6-7: Module 1 Frontend (reconnection + notification + replay dedup)
  Day 8-10: Module 2 (Follow-up nodes + orchestrator update + routing tests)
  Day 11:  Integration testing + E2E
```

Rationale: A1 Quality is the lowest-risk, highest-immediate-impact module. Task Persistence is the largest module and needs backend + frontend work. Multi-Turn builds on both Task Persistence (for session awareness) and existing pipeline (for data availability).

---

## 8. Risks & Dependencies

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|-----------|
| Orchestrator LLM misroutes follow-up questions to full pipeline (9 tools) | Medium | User re-runs full analysis unnecessarily | Context summary with tool availability hints (Review C4); tool descriptions with explicit REQUIRES and negative guidance; E2E routing test matrix (10+ messages) as AC |
| Task status becomes stale (server crash during RUNNING) | Low | Orphaned RUNNING tasks | Startup orphan recovery: scan RUNNING > 30 min, mark FAILED (Review C6/T9); expose "retry" button on failed tasks |
| drill_down_node LLM output quality varies | Medium | Shallow or irrelevant drill-down | Constrain LLM output with structured prompt; include data samples in context; set max_tokens=4096; include simulated_questions for richer context (Review T4) |
| MemorySaver state loss on server restart breaks reconnection | Medium | Task shows RUNNING but workflow is dead | `rebuild_state_from_db()` already exists; combine with task.stage_results_cache for comprehensive recovery; orphan recovery marks stale tasks FAILED |
| A1 retry doubles LLM cost for every analysis | Low | Cost increase | Retry only when validation fails (~30% of cases); single retry limit |
| selective_refetch partial update produces inconsistent report | Medium | Misleading delta | V1 simplified merge: selected platforms replace, unselected preserve from Snapshot baseline, A5 regenerates full report from merged data, new Snapshot created (Review C5/T3) |
| Frontend reconnection creates duplicate StageResultCards | Low | Visual duplication | addStageResult deduplicates by stage+resultType (Review T7) |
| stage_results_cache concurrent write causes lost update | Low | Missing stage results on reconnect | SELECT FOR UPDATE row-level locking in transaction (Review C1/T2) |
| cancel_task does not stop LangGraph workflow | Medium | Resource waste | complete_task() checks CANCELLED status, skips COMPLETED transition (Review T8); true cancellation deferred to P2 |

### Dependencies

| Dependency | Type | Risk |
|-----------|------|------|
| Cycle 2 Snapshot model implemented | Hard | Cycle 2 must be complete before compare_snapshots works |
| Cycle 2 StageResultCard component exists | Hard | Reconnection replay depends on this component |
| Cycle 2 events.py send_stage_result() exists | Hard | Task persistence hooks into milestone points near this function |
| MiniMax Function Calling supports 9 tools (6+3) | Soft | If tool count causes routing issues, consolidate tools or improve descriptions (Review C4) |

---

## 9. Out of Scope (Deferred)

1. **Email/Webhook notifications**: P2 scope. V1 uses in-app notification only.
2. **Scheduled/periodic analysis**: P2-2. Requires Celery task queue integration.
3. **Department-specific views**: P2-1. Multi-perspective analysis.
4. **BWVS weight customization**: P2-3.
5. **Task cancellation with workflow interruption**: V1 `cancel` only marks status, does not stop running LangGraph. True cancellation requires LangGraph interrupt support.
6. **Conversation history summarization**: Long sessions with many turns could exceed LLM context. Deferred -- current sessions rarely exceed 5-10 turns.
7. **Cross-session data sharing**: "Compare brand X analysis from session A with session B". Deferred -- compare_snapshots handles same-entity comparisons.
8. **Independent task_stage_results table** (Review C1 alternative B): V1 uses JSON column with row locking. If performance degrades, consider normalizing to a separate table in future cycle.

---

## 10. Open Questions

1. **Q: Should follow-up responses go to Chat (reply_delta) or Canvas (output_ready)?**
   - Current recommendation: Chat reply for drill_down and compare_snapshots (lighter, conversational). Canvas for selective_refetch (full report regeneration).
   - Decision owner: UX Designer.

2. **Q: How many concurrent tasks should one user be allowed?**
   - Current recommendation: 3 concurrent RUNNING tasks. Additional requests queue as PENDING.
   - Rationale: Server resource protection. Each running workflow consumes LLM API calls and browser sessions.

3. **Q: Should task_id be exposed in the URL or kept internal?**
   - Current recommendation: Internal. Users interact via session_id. Task is an implementation detail.

4. **Q: What happens if user sends a new analysis request while one is RUNNING in the same session?**
   - Current recommendation: Block with message "An analysis is already in progress. Please wait for it to complete or cancel it."
   - This is enforced at the WebSocket handler level.

5. **Q: Should A1 retry use a different LLM provider (e.g., GLM5 as fallback)?**
   - Current recommendation: No. Use same provider with different prompt. Provider switching adds complexity.
   - Revisit if A1 failure rate stays high after prompt improvements.

---

## Appendix A: Review Traceability Matrix

| Review ID | Source | Section(s) Updated | AC(s) Added/Modified |
|-----------|--------|--------------------|--------------------|
| C1 | Architecture | 2.4 (concurrency note), 2.5 (append_stage_result) | AC-3 |
| C2 | Architecture | 2.5 (class docstring), 2.7 (NOT affected), 5.1, 6.1, 6.3 | AC-12 |
| C3 | Architecture | 2.4 (design decision 4), 3.5.3 (baseline from Snapshot) | AC-21 |
| C4 | Architecture | 3.4 (tool descriptions), 3.8 (tool availability), 3.9 | AC-24, AC-25, AC-27 |
| C5 | Architecture | 3.5.3 (merge strategy) | AC-21 |
| C6 | Architecture | 2.5 (recover_orphan_tasks), 2.6 (new section) | AC-14 |
| C7 | Architecture | 3.5.2 (design note comment) | AC-26 |
| T1 | Technical | 2.5 (class docstring), 2.7 (lifecycle) | AC-12 |
| T2 | Technical | 2.4 (concurrency note), 2.5 (append_stage_result) | AC-3 |
| T3 | Technical | 3.5.3 (V1 simplified) | AC-21 |
| T4 | Technical | 3.5.1 (simulated_questions) | AC-16 |
| T5 | Technical | 3.4 (tool descriptions), 3.5.1 (precondition), 3.5.3 (precondition) | AC-17, AC-22 |
| T6 | Technical | 3.5.2 (get_snapshot) | AC-18 |
| T7 | Technical | 2.8 (dedup note), 2.10 (dedup code) | AC-9 |
| T8 | Technical | 2.5 (complete_task, cancel_task) | AC-4, AC-13 |
| T9 | Technical | 2.5 (recover_orphan_tasks), 2.6 (new section) | AC-14 |
