"""One-shot brand-scoped data purge for GEO canonical launch cutover.

This script removes generated brand data while preserving account/auth records.
It supports a dry-run preview so launch cleanup can be validated before
destructive execution.
"""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass

from sqlalchemy import delete, func, select

from app.core.database import AsyncSessionLocal
from app.models.entity import Entity
from app.models.fetch_run_platform_state import FetchRunPlatformState
from app.models.knowledge import KnowledgeRecord, KnowledgeSegment
from app.models.message import Message
from app.models.monitoring_alert import MonitoringAlert
from app.models.monitoring_schedule import MonitoringSchedule
from app.models.session import Session
from app.models.snapshot import AnalysisSnapshot
from app.models.task import AnalysisTask
from app.models.task_run import TaskRun
from app.models.task_run_child_attempt import TaskRunChildAttempt


@dataclass(frozen=True)
class PurgeTarget:
    label: str
    model: type


PURGE_TARGETS: tuple[PurgeTarget, ...] = (
    PurgeTarget("task_run_child_attempts", TaskRunChildAttempt),
    PurgeTarget("fetch_run_platform_states", FetchRunPlatformState),
    PurgeTarget("task_runs", TaskRun),
    PurgeTarget("analysis_tasks", AnalysisTask),
    PurgeTarget("knowledge_segments", KnowledgeSegment),
    PurgeTarget("knowledge_records", KnowledgeRecord),
    PurgeTarget("monitoring_alerts", MonitoringAlert),
    PurgeTarget("analysis_snapshots", AnalysisSnapshot),
    PurgeTarget("monitoring_schedules", MonitoringSchedule),
    PurgeTarget("messages", Message),
    PurgeTarget("sessions", Session),
    PurgeTarget("entities", Entity),
)


async def collect_purge_counts() -> dict[str, int]:
    async with AsyncSessionLocal() as db:
        counts: dict[str, int] = {}
        for target in PURGE_TARGETS:
            result = await db.execute(select(func.count()).select_from(target.model))
            counts[target.label] = int(result.scalar_one() or 0)
        return counts


async def purge_brand_generated_data() -> dict[str, int]:
    counts = await collect_purge_counts()
    async with AsyncSessionLocal() as db:
        async with db.begin():
            for target in PURGE_TARGETS:
                await db.execute(delete(target.model))
    return counts


def _print_counts(counts: dict[str, int]) -> None:
    total = sum(counts.values())
    print("Purge preview for brand-scoped generated data:")
    for label, count in counts.items():
        print(f"- {label}: {count}")
    print(f"Total rows targeted: {total}")
    print("Preserved scope: users / organizations / auth / identity")


async def _async_main() -> int:
    dry_run = "--dry-run" in sys.argv or "--confirm" not in sys.argv
    counts = await collect_purge_counts()
    _print_counts(counts)

    if dry_run:
        print("Dry run only. Re-run with --confirm to execute purge.")
        return 0

    deleted_counts = await purge_brand_generated_data()
    print("Brand-scoped generated data purged.")
    _print_counts(deleted_counts)
    return 0


def main() -> int:
    return asyncio.run(_async_main())


if __name__ == "__main__":
    raise SystemExit(main())
