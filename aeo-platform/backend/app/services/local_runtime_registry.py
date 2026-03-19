"""Registry for in-process local workflow executions.

This keeps runtime concerns separate from the WebSocket request loop:
- bind a durable TaskRun to the currently executing asyncio task
- refresh lease heartbeats while the local executor is alive
- honor cooperative cancellation requests persisted in the database
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable
from uuid import UUID

from app.core.database import AsyncSessionLocal
from app.models.task_run import TaskRunStatus
from app.services.job_dispatcher import JobDispatcher

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_SECONDS = 5

ExecutionHeartbeatCallback = Callable[[str, UUID, UUID, str], Awaitable[None]]
ExecutionReleaseCallback = Callable[[str, UUID, UUID, str], Awaitable[None]]


@dataclass(slots=True)
class LocalExecutionBinding:
    """Tracks one in-process workflow execution bound to a durable TaskRun."""

    session_id: str
    task_id: UUID
    run_id: UUID
    lease_owner: str
    execution_task: asyncio.Task
    monitor_task: asyncio.Task
    heartbeat_callback: ExecutionHeartbeatCallback | None = None
    release_callback: ExecutionReleaseCallback | None = None


class LocalRuntimeRegistry:
    """Owns registration and cooperative stop for local workflow executors."""

    def __init__(self) -> None:
        self._bindings_by_session: dict[str, LocalExecutionBinding] = {}
        self._bindings_by_task: dict[UUID, LocalExecutionBinding] = {}
        self._bindings_by_run: dict[UUID, LocalExecutionBinding] = {}
        self._runtime_blocked_sessions: set[str] = set()
        self._lock = asyncio.Lock()

    @staticmethod
    def _binding_is_live(binding: LocalExecutionBinding) -> bool:
        return not binding.execution_task.done()

    async def register_execution(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        execution_task: asyncio.Task,
        heartbeat_callback: ExecutionHeartbeatCallback | None = None,
        release_callback: ExecutionReleaseCallback | None = None,
    ) -> None:
        """Register the current asyncio task as the live executor for a run."""

        async with self._lock:
            stale = self._bindings_by_run.get(run_id)
            if stale is not None:
                if self._binding_is_live(stale):
                    raise RuntimeError(
                        f"Run {run_id} is already bound to a live local executor"
                    )
                await self._remove_binding(stale, cancel_monitor=True)

            existing = self._bindings_by_session.get(session_id)
            if existing is not None and existing.run_id != run_id:
                if self._binding_is_live(existing):
                    raise RuntimeError(
                        "Session already has a live local executor bound "
                        f"(session={session_id}, run={existing.run_id})"
                    )
                await self._remove_binding(existing, cancel_monitor=True)

            monitor_task = asyncio.create_task(
                self._monitor_execution(
                    session_id=session_id,
                    task_id=task_id,
                    run_id=run_id,
                    lease_owner=lease_owner,
                    execution_task=execution_task,
                )
            )
            binding = LocalExecutionBinding(
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                lease_owner=lease_owner,
                execution_task=execution_task,
                monitor_task=monitor_task,
                heartbeat_callback=heartbeat_callback,
                release_callback=release_callback,
            )
            self._runtime_blocked_sessions.discard(session_id)
            self._bindings_by_session[session_id] = binding
            self._bindings_by_task[task_id] = binding
            self._bindings_by_run[run_id] = binding

        execution_task.add_done_callback(
            lambda _: asyncio.create_task(self.unregister_run(run_id))
        )

    async def unregister_run(self, run_id: UUID) -> None:
        """Remove a completed/stale binding."""

        async with self._lock:
            binding = self._bindings_by_run.get(run_id)
            if binding is None:
                return
            await self._remove_binding(binding, cancel_monitor=True)

    async def cancel_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        """Cancel the live executor currently bound to a session, if any."""

        async with self._lock:
            self._runtime_blocked_sessions.add(session_id)
            binding = self._bindings_by_session.get(session_id)
            if binding is None:
                return None

            if not binding.execution_task.done():
                binding.execution_task.cancel()
            return binding

    async def cancel_task_execution(
        self, task_id: UUID
    ) -> LocalExecutionBinding | None:
        """Cancel the live executor currently bound to a task, if any."""

        async with self._lock:
            binding = self._bindings_by_task.get(task_id)
            if binding is None:
                return None

            self._runtime_blocked_sessions.add(binding.session_id)
            if not binding.execution_task.done():
                binding.execution_task.cancel()
            return binding

    async def allow_session_runtime_events(self, session_id: str) -> None:
        """Clear any cancellation-based event suppression for a session."""

        async with self._lock:
            self._runtime_blocked_sessions.discard(session_id)

    async def get_live_session_execution(
        self, session_id: str
    ) -> LocalExecutionBinding | None:
        """Return the live binding for a session, if the executor is still running."""

        async with self._lock:
            binding = self._bindings_by_session.get(session_id)
            if binding is None:
                return None
            if self._binding_is_live(binding):
                return binding

            await self._remove_binding(binding, cancel_monitor=True)
            return None

    def is_session_runtime_blocked(self, session_id: str) -> bool:
        """Return True when runtime events for a session should be suppressed."""

        return session_id in self._runtime_blocked_sessions

    async def _monitor_execution(
        self,
        *,
        session_id: str,
        task_id: UUID,
        run_id: UUID,
        lease_owner: str,
        execution_task: asyncio.Task,
    ) -> None:
        """Heartbeat the durable run and stop the local task on cancel."""

        try:
            while not execution_task.done():
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)

                async with AsyncSessionLocal() as db:
                    from app.services.task_service import TaskService

                    task_service = TaskService(db)
                    run = await task_service.get_task_run(task_id, run_id)
                    if run is None:
                        if not execution_task.done():
                            execution_task.cancel()
                        return

                    if run.status in {
                        TaskRunStatus.CANCELLED,
                        TaskRunStatus.COMPLETED,
                        TaskRunStatus.FAILED,
                    }:
                        if not execution_task.done():
                            execution_task.cancel()
                        return

                    if (
                        run.cancel_requested_at is not None
                        or run.status == TaskRunStatus.CANCELLING
                    ):
                        logger.info(
                            "[LocalRuntime] Cooperative cancel for session %s "
                            "(task=%s, run=%s)",
                            session_id,
                            task_id,
                            run_id,
                        )
                        if not execution_task.done():
                            execution_task.cancel()
                        return

                    dispatcher = JobDispatcher(db)
                    await dispatcher.heartbeat_run(
                        task_id=task_id,
                        run_id=run_id,
                        lease_owner=lease_owner,
                    )

                binding = self._bindings_by_run.get(run_id)
                if (
                    binding is not None
                    and binding.heartbeat_callback is not None
                    and not execution_task.done()
                ):
                    await binding.heartbeat_callback(
                        session_id,
                        task_id,
                        run_id,
                        lease_owner,
                    )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "[LocalRuntime] Monitor failed for session %s (task=%s, run=%s)",
                session_id,
                task_id,
                run_id,
            )

    async def _remove_binding(
        self,
        binding: LocalExecutionBinding,
        *,
        cancel_monitor: bool,
    ) -> None:
        if binding.release_callback is not None:
            try:
                await binding.release_callback(
                    binding.session_id,
                    binding.task_id,
                    binding.run_id,
                    binding.lease_owner,
                )
            except Exception:
                logger.exception(
                    "[LocalRuntime] Release callback failed "
                    "(session=%s, task=%s, run=%s)",
                    binding.session_id,
                    binding.task_id,
                    binding.run_id,
                )

        self._bindings_by_run.pop(binding.run_id, None)
        self._bindings_by_task.pop(binding.task_id, None)
        self._bindings_by_session.pop(binding.session_id, None)

        if cancel_monitor and not binding.monitor_task.done():
            binding.monitor_task.cancel()
            try:
                await binding.monitor_task
            except asyncio.CancelledError:
                pass


local_runtime_registry = LocalRuntimeRegistry()
