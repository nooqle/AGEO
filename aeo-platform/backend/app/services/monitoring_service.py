"""Monitoring Schedule lifecycle management service."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.monitoring_schedule import (
    MonitoringSchedule,
    ScheduleFrequency,
    ScheduleStatus,
)
from app.models.snapshot import AnalysisSnapshot
from app.models.task import AnalysisTask
from app.models.user import User
from app.services.access_scope_service import AccessScopeService

logger = logging.getLogger(__name__)


class MonitoringService:
    """Manages MonitoringSchedule CRUD, scheduling logic, and execution tracking."""

    MAX_SCHEDULES_PER_USER = 10
    MAX_SCHEDULES_GLOBAL = 100
    DEFAULT_PLATFORMS = ["doubao", "yuanbao", "kimi", "deepseek"]
    MONITORING_PLATFORM_ALIASES = {
        "hunyuan": "yuanbao",
    }
    SUPPORTED_PLATFORM_SET = frozenset(
        {"doubao", "yuanbao", "hunyuan", "kimi", "deepseek"}
    )

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # =========================================================================
    # CRUD
    # =========================================================================

    async def create_schedule(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        frequency: ScheduleFrequency = ScheduleFrequency.WEEKLY,
        preferred_hour: int = 3,
        timezone_str: str = "Asia/Shanghai",
        platforms: list[str] | None = None,
        alert_on_significant_change: bool = True,
        alert_threshold_bwvs: float = 10.0,
        max_runs: int | None = None,
        end_date: datetime | None = None,
        status: ScheduleStatus = ScheduleStatus.ACTIVE,
        monitor_mode: str = "panorama",
        question_set_ids: list[str] | None = None,
        endpoint_ids: list[str] | None = None,
        run_policy: str = "quick",
        monitoring_plan_id: UUID | None = None,
        baseline_data: dict | None = None,
    ) -> MonitoringSchedule:
        """Create a new monitoring schedule.

        Validates limits and calculates initial next_run_at.
        """
        # Validate preferred_hour
        if not 0 <= preferred_hour <= 23:
            raise ValueError(f"preferred_hour must be 0-23, got {preferred_hour}")

        # Check per-user limit
        user_count = await self._count_active_schedules(user_id=user_id)
        if user_count >= self.MAX_SCHEDULES_PER_USER:
            raise ValueError(
                f"User schedule limit reached ({self.MAX_SCHEDULES_PER_USER}). "
                "Please pause or delete an existing schedule first."
            )

        # Check system-wide limit
        global_count = await self._count_active_schedules()
        if global_count >= self.MAX_SCHEDULES_GLOBAL:
            raise ValueError(
                f"System schedule limit reached ({self.MAX_SCHEDULES_GLOBAL}). "
                "Please try again later."
            )

        # Legacy schedules remain one-active-per-entity/mode. Plan-backed
        # schedules are independent so each active plan can own its schedule.
        if monitoring_plan_id is None:
            existing = await self.get_entity_active_schedule(
                entity_id,
                monitor_mode=monitor_mode,
            )
            if existing is not None:
                raise ValueError(
                    "An active schedule already exists for this entity. "
                    "Pause or delete the existing schedule first."
                )
        else:
            existing = await self.get_plan_active_schedule(monitoring_plan_id)
            if existing is not None:
                raise ValueError(
                    "An active schedule already exists for this monitoring plan. "
                    "Pause or update the existing schedule first."
                )

        normalized_platforms = self._normalize_platforms(
            platforms, use_default_when_missing=True
        )
        next_run = (
            self.calculate_next_run(frequency, preferred_hour, timezone_str)
            if status == ScheduleStatus.ACTIVE
            else None
        )

        schedule = MonitoringSchedule(
            user_id=user_id,
            entity_id=entity_id,
            frequency=frequency,
            preferred_hour=preferred_hour,
            timezone=timezone_str,
            platforms=normalized_platforms,
            monitor_mode=monitor_mode,
            question_set_ids=question_set_ids,
            endpoint_ids=endpoint_ids,
            run_policy=run_policy,
            monitoring_plan_id=monitoring_plan_id,
            alert_on_significant_change=alert_on_significant_change,
            alert_threshold_bwvs=alert_threshold_bwvs,
            max_runs=max_runs,
            end_date=end_date,
            next_run_at=next_run,
            status=status,
            baseline_data=baseline_data,
        )
        self.db.add(schedule)
        await self.db.commit()
        await self.db.refresh(schedule)

        if schedule.baseline_data is None:
            try:
                await self.seed_baseline_from_latest_panorama(
                    schedule_id=schedule.id,
                    require_report=status == ScheduleStatus.ACTIVE,
                )
                await self.db.refresh(schedule)
            except ValueError:
                if status == ScheduleStatus.ACTIVE:
                    await self.db.delete(schedule)
                    await self.db.commit()
                raise

        logger.info(
            "[MonitoringService] Created schedule %s for entity %s "
            "(freq=%s, status=%s, next_run=%s)",
            schedule.id,
            entity_id,
            frequency.value,
            status.value,
            next_run,
        )
        return schedule

    async def get_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Get a single schedule by ID (eager-loads entity for entity_name)."""
        stmt = (
            select(MonitoringSchedule)
            .options(selectinload(MonitoringSchedule.entity))
            .where(MonitoringSchedule.id == schedule_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_entity_active_schedule(
        self, entity_id: UUID, monitor_mode: str | None = None
    ) -> MonitoringSchedule | None:
        """Get the active schedule for an entity and optional monitoring mode."""
        conditions = [
            MonitoringSchedule.entity_id == entity_id,
            MonitoringSchedule.status == ScheduleStatus.ACTIVE,
        ]
        if monitor_mode:
            conditions.append(MonitoringSchedule.monitor_mode == monitor_mode)
        stmt = (
            select(MonitoringSchedule)
            .where(*conditions)
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_plan_active_schedule(
        self,
        monitoring_plan_id: UUID,
    ) -> MonitoringSchedule | None:
        """Get the active schedule owned by a monitoring plan."""
        stmt = (
            select(MonitoringSchedule)
            .where(
                MonitoringSchedule.monitoring_plan_id == monitoring_plan_id,
                MonitoringSchedule.status == ScheduleStatus.ACTIVE,
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_schedules(
        self,
        user_id: UUID,
        *,
        entity_id: UUID | None = None,
        status: ScheduleStatus | None = None,
        monitor_mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MonitoringSchedule], int]:
        """List schedules for a user with optional filters."""
        conditions = [MonitoringSchedule.user_id == user_id]
        if entity_id is not None:
            conditions.append(MonitoringSchedule.entity_id == entity_id)
        if status is not None:
            conditions.append(MonitoringSchedule.status == status)
        if monitor_mode is not None:
            conditions.append(MonitoringSchedule.monitor_mode == monitor_mode)

        count_stmt = (
            select(func.count()).select_from(MonitoringSchedule).where(*conditions)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(MonitoringSchedule)
            .options(selectinload(MonitoringSchedule.entity))
            .where(*conditions)
            .order_by(MonitoringSchedule.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        schedules = list(result.scalars().all())
        return schedules, total

    async def list_schedules_for_viewer(
        self,
        viewer: User,
        *,
        entity_id: UUID | None = None,
        status: ScheduleStatus | None = None,
        monitor_mode: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[MonitoringSchedule], int]:
        conditions = [AccessScopeService.schedule_visibility_filter(viewer)]
        if entity_id is not None:
            conditions.append(MonitoringSchedule.entity_id == entity_id)
        if status is not None:
            conditions.append(MonitoringSchedule.status == status)
        if monitor_mode is not None:
            conditions.append(MonitoringSchedule.monitor_mode == monitor_mode)

        count_stmt = (
            select(func.count()).select_from(MonitoringSchedule).where(*conditions)
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar() or 0

        query = (
            select(MonitoringSchedule)
            .options(selectinload(MonitoringSchedule.entity))
            .where(*conditions)
            .order_by(MonitoringSchedule.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.db.execute(query)
        schedules = list(result.scalars().all())
        return schedules, total

    async def get_schedule_for_viewer(
        self,
        schedule_id: UUID,
        viewer: User,
    ) -> MonitoringSchedule | None:
        stmt = (
            select(MonitoringSchedule)
            .options(selectinload(MonitoringSchedule.entity))
            .where(
                MonitoringSchedule.id == schedule_id,
                AccessScopeService.schedule_visibility_filter(viewer),
            )
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_schedule(
        self,
        schedule_id: UUID,
        **kwargs,
    ) -> MonitoringSchedule | None:
        """Update schedule configuration. Recalculates next_run_at if frequency changes."""
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return None

        recalculate_next = False
        for key, value in kwargs.items():
            if value is not None and hasattr(schedule, key):
                if key == "platforms":
                    value = self._normalize_platforms(
                        value, use_default_when_missing=False
                    )
                setattr(schedule, key, value)
                if key in ("frequency", "preferred_hour", "timezone", "status"):
                    recalculate_next = True

        if recalculate_next:
            if schedule.status == ScheduleStatus.ACTIVE:
                schedule.next_run_at = self.calculate_next_run(
                    schedule.frequency,
                    schedule.preferred_hour,
                    schedule.timezone,
                )
            else:
                schedule.next_run_at = None

        schedule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(schedule)
        return schedule

    async def pause_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Pause an active schedule."""
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return None
        if schedule.status != ScheduleStatus.ACTIVE:
            raise ValueError(
                f"Cannot pause schedule with status: {schedule.status.value}"
            )
        schedule.status = ScheduleStatus.PAUSED
        schedule.next_run_at = None
        schedule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(schedule)
        logger.info("[MonitoringService] Paused schedule %s", schedule_id)
        return schedule

    async def resume_schedule(self, schedule_id: UUID) -> MonitoringSchedule | None:
        """Resume a paused or errored schedule."""
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return None
        if schedule.status not in (ScheduleStatus.PAUSED, ScheduleStatus.ERROR):
            raise ValueError(
                f"Cannot resume schedule with status: {schedule.status.value}"
            )
        schedule.status = ScheduleStatus.ACTIVE
        schedule.consecutive_failures = 0
        schedule.next_run_at = self.calculate_next_run(
            schedule.frequency,
            schedule.preferred_hour,
            schedule.timezone,
        )
        schedule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(schedule)
        try:
            await self.seed_baseline_from_latest_panorama(
                schedule_id=schedule.id,
                require_report=True,
            )
            await self.db.refresh(schedule)
        except ValueError:
            schedule.status = ScheduleStatus.PAUSED
            schedule.next_run_at = None
            schedule.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(schedule)
            raise
        logger.info("[MonitoringService] Resumed schedule %s", schedule_id)
        return schedule

    async def delete_schedule(self, schedule_id: UUID) -> bool:
        """Hard-delete a schedule."""
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return False
        await self.db.delete(schedule)
        await self.db.commit()
        logger.info("[MonitoringService] Deleted schedule %s", schedule_id)
        return True

    # =========================================================================
    # Scheduler Support
    # =========================================================================

    async def get_due_schedules(self) -> list[MonitoringSchedule]:
        """Get all ACTIVE schedules where next_run_at <= now()."""
        now = datetime.now(timezone.utc)
        stmt = (
            select(MonitoringSchedule)
            .where(
                MonitoringSchedule.status == ScheduleStatus.ACTIVE,
                MonitoringSchedule.next_run_at <= now,
            )
            .order_by(MonitoringSchedule.next_run_at.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def record_run_started(self, schedule_id: UUID, task_id: UUID) -> None:
        """Record that a scheduled run has started."""
        now = datetime.now(timezone.utc)
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return

        schedule.last_run_at = now
        schedule.last_task_id = task_id
        schedule.total_runs = (schedule.total_runs or 0) + 1
        schedule.updated_at = now

        # Calculate next_run_at
        schedule.next_run_at = self.calculate_next_run(
            schedule.frequency,
            schedule.preferred_hour,
            schedule.timezone,
        )

        # Check limits
        if schedule.max_runs and schedule.total_runs >= schedule.max_runs:
            schedule.status = ScheduleStatus.COMPLETED
            schedule.next_run_at = None
            logger.info(
                "[MonitoringService] Schedule %s completed (max_runs=%d reached)",
                schedule_id,
                schedule.max_runs,
            )
        elif schedule.end_date and now >= schedule.end_date:
            schedule.status = ScheduleStatus.COMPLETED
            schedule.next_run_at = None
            logger.info(
                "[MonitoringService] Schedule %s completed (end_date reached)",
                schedule_id,
            )

        await self.db.commit()

    async def record_run_completed(self, schedule_id: UUID) -> None:
        """Record successful completion. Resets consecutive_failures."""
        await self.db.execute(
            update(MonitoringSchedule)
            .where(MonitoringSchedule.id == schedule_id)
            .values(
                consecutive_failures=0,
                updated_at=datetime.now(timezone.utc),
            )
        )
        await self.db.commit()

    async def record_run_failed(self, schedule_id: UUID) -> None:
        """Record failure. Increments consecutive_failures.

        If consecutive_failures >= max_failures, transitions to ERROR.
        """
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return

        schedule.consecutive_failures = (schedule.consecutive_failures or 0) + 1
        schedule.updated_at = datetime.now(timezone.utc)

        if schedule.consecutive_failures >= schedule.max_failures:
            schedule.status = ScheduleStatus.ERROR
            schedule.next_run_at = None
            logger.warning(
                "[MonitoringService] Schedule %s set to ERROR after %d consecutive failures",
                schedule_id,
                schedule.consecutive_failures,
            )

        await self.db.commit()

    async def get_run_history(
        self, schedule_id: UUID, limit: int = 20
    ) -> list[AnalysisTask]:
        """Get task execution history for a schedule."""
        stmt = (
            select(AnalysisTask)
            .where(AnalysisTask.monitoring_schedule_id == schedule_id)
            .order_by(AnalysisTask.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    # =========================================================================
    # Baseline Management
    # =========================================================================

    # Maximum baseline JSON size: 512 KB
    MAX_BASELINE_SIZE = 512 * 1024
    # Maximum questions to keep in baseline
    MAX_BASELINE_QUESTIONS = 50

    async def save_baseline(self, schedule_id: UUID, baseline: dict) -> None:
        """Save baseline data extracted from first successful pipeline run.

        The baseline contains A1 brand profile + A3 simulated questions so
        that subsequent scheduled runs can skip A1-A3 and only re-run A4+A5
        with the same questions, enabling meaningful trend comparison.
        """
        import json

        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            logger.warning(
                "[MonitoringService] Cannot save baseline: schedule %s not found",
                schedule_id,
            )
            return

        # Truncate questions if too many
        questions = baseline.get("questions", [])
        if len(questions) > self.MAX_BASELINE_QUESTIONS:
            logger.warning(
                "[MonitoringService] Truncating baseline questions from %d to %d",
                len(questions),
                self.MAX_BASELINE_QUESTIONS,
            )
            baseline["questions"] = questions[: self.MAX_BASELINE_QUESTIONS]

        # Check serialized size
        serialized = json.dumps(baseline, ensure_ascii=False)
        if len(serialized) > self.MAX_BASELINE_SIZE:
            logger.warning(
                "[MonitoringService] Baseline too large (%d bytes > %d), "
                "stripping simulated_questions detail",
                len(serialized),
                self.MAX_BASELINE_SIZE,
            )
            # Keep only essentials: questions (flat) + brand_profile + competitors
            baseline.pop("simulated_questions", None)
            baseline.pop("competitive_landscape", None)

        schedule.baseline_data = baseline
        schedule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            "[MonitoringService] Saved baseline for schedule %s "
            "(%d questions, source_task=%s)",
            schedule_id,
            len(baseline.get("questions", [])),
            baseline.get("source_task_id"),
        )

    async def get_baseline(self, schedule_id: UUID) -> dict | None:
        """Get baseline data for a schedule.

        Returns None if no baseline has been saved yet.
        """
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            return None
        return schedule.baseline_data

    async def clear_baseline(self, schedule_id: UUID) -> None:
        """Clear baseline data so the next run executes the full A1-A5 pipeline.

        Use case: user wants to refresh the question set (e.g. after brand
        repositioning or adding new competitors).
        """
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            logger.warning(
                "[MonitoringService] Cannot clear baseline: schedule %s not found",
                schedule_id,
            )
            return

        schedule.baseline_data = None
        schedule.updated_at = datetime.now(timezone.utc)
        await self.db.commit()
        logger.info(
            "[MonitoringService] Cleared baseline for schedule %s",
            schedule_id,
        )

    async def seed_baseline_from_latest_panorama(
        self,
        *,
        schedule_id: UUID,
        require_report: bool,
    ) -> bool:
        """Seed schedule baseline from the latest panorama snapshot.

        Panorama auto-monitoring should always reuse the latest panorama question
        set. If no panorama snapshot exists and *require_report* is True, raise a
        ValueError so the caller can block activation.
        """
        schedule = await self.get_schedule(schedule_id)
        if schedule is None:
            logger.warning(
                "[MonitoringService] Cannot seed baseline: schedule %s not found",
                schedule_id,
            )
            return False

        current_baseline = schedule.baseline_data or {}
        if current_baseline.get("questions"):
            return True

        stmt = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == schedule.entity_id,
                AnalysisSnapshot.snapshot_type.in_(["panorama", "baseline"]),
            )
            .order_by(desc(AnalysisSnapshot.created_at))
            .limit(1)
        )
        result = await self.db.execute(stmt)
        snapshot = result.scalar_one_or_none()

        if snapshot is None:
            if require_report:
                raise ValueError("请先完成一次品牌全景分析，再启用自动监测。")
            return False

        seeded_baseline = self._build_baseline_from_snapshot(snapshot)
        if seeded_baseline is None:
            if require_report:
                raise ValueError("最近一次品牌全景分析缺少可复用的问题基线，请先重新生成全景分析。")
            return False

        await self.save_baseline(schedule_id, seeded_baseline)
        return True

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _build_baseline_from_snapshot(snapshot: AnalysisSnapshot) -> dict | None:
        raw_data = snapshot.raw_data if isinstance(snapshot.raw_data, dict) else {}
        report_data = raw_data.get("report_data", {})
        input_bundle = (
            report_data.get("input_bundle", {})
            if isinstance(report_data, dict)
            else {}
        )
        brand_master = (
            input_bundle.get("brand_master", {})
            if isinstance(input_bundle, dict)
            else {}
        )

        questions = None
        if isinstance(input_bundle.get("questions"), list):
            questions = input_bundle.get("questions")
        elif isinstance(report_data.get("questions"), list):
            questions = report_data.get("questions")
        elif isinstance(raw_data.get("questions"), list):
            questions = raw_data.get("questions")

        if not questions:
            return None

        monitor_brand = brand_master.get("monitor_brand")
        aliases = brand_master.get("monitor_brand_aliases") or []
        official_domains = brand_master.get("official_domains") or []
        competitor_names = brand_master.get("competitor_brands") or []

        official_website = None
        if official_domains:
            first_domain = str(official_domains[0]).strip()
            if first_domain:
                official_website = (
                    first_domain
                    if first_domain.startswith("http://")
                    or first_domain.startswith("https://")
                    else f"https://{first_domain}"
                )

        return {
            "questions": questions,
            "simulated_questions": None,
            "brand_profile": {
                "brand_name": monitor_brand,
                "brand_keywords": aliases,
                "official_website": official_website,
            },
            "competitors": [{"name": name} for name in competitor_names if name],
            "competitive_landscape": None,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "source_task_id": str(snapshot.id),
        }

    async def _count_active_schedules(self, user_id: UUID | None = None) -> int:
        """Count active schedules, optionally for a specific user."""
        conditions = [
            MonitoringSchedule.status == ScheduleStatus.ACTIVE,
        ]
        if user_id is not None:
            conditions.append(MonitoringSchedule.user_id == user_id)

        stmt = select(func.count()).select_from(MonitoringSchedule).where(*conditions)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    @classmethod
    def _normalize_platforms(
        cls,
        platforms: list[str] | None,
        *,
        use_default_when_missing: bool,
    ) -> list[str]:
        if platforms is None:
            return list(cls.DEFAULT_PLATFORMS) if use_default_when_missing else []

        normalized: list[str] = []
        invalid: list[str] = []

        for raw_platform in platforms:
            platform = str(raw_platform).strip().lower()
            if not platform:
                continue
            platform = cls.MONITORING_PLATFORM_ALIASES.get(platform, platform)
            if platform not in cls.SUPPORTED_PLATFORM_SET:
                invalid.append(str(raw_platform))
                continue
            if platform not in normalized:
                normalized.append(platform)

        if invalid:
            supported = ", ".join(["doubao", "yuanbao", "kimi", "deepseek"])
            raise ValueError(
                "Unsupported monitoring platforms: "
                f"{', '.join(invalid)}. Must be one of: {supported}"
            )

        if normalized:
            return normalized

        if use_default_when_missing:
            return list(cls.DEFAULT_PLATFORMS)

        raise ValueError("At least one supported monitoring platform must be provided.")

    @staticmethod
    def calculate_next_run(
        frequency: ScheduleFrequency,
        preferred_hour: int,
        timezone_str: str = "Asia/Shanghai",
        from_time: datetime | None = None,
    ) -> datetime:
        """Calculate the next run time based on frequency.

        Uses preferred_hour in the specified timezone, returns UTC datetime.
        For simplicity, uses fixed UTC offsets for common timezones.
        """
        # Resolve timezone offset (simplified -- handles common cases)
        tz_offsets = {
            "Asia/Shanghai": 8,
            "Asia/Tokyo": 9,
            "Asia/Seoul": 9,
            "UTC": 0,
            "US/Eastern": -5,
            "US/Pacific": -8,
            "Europe/London": 0,
            "Europe/Berlin": 1,
        }
        offset_hours = tz_offsets.get(timezone_str, 8)  # Default to CST

        now = from_time or datetime.now(timezone.utc)

        # Calculate the preferred_hour in UTC
        utc_hour = (preferred_hour - offset_hours) % 24

        # Calculate today's target time at the preferred UTC hour
        base = now.replace(hour=utc_hour, minute=0, second=0, microsecond=0)

        if frequency == ScheduleFrequency.DAILY:
            delta = timedelta(days=1)
        elif frequency == ScheduleFrequency.WEEKLY:
            delta = timedelta(weeks=1)
        elif frequency == ScheduleFrequency.BIWEEKLY:
            delta = timedelta(weeks=2)
        elif frequency == ScheduleFrequency.MONTHLY:
            delta = timedelta(days=30)  # Approximation for V1
        else:
            delta = timedelta(weeks=1)

        # If today's target time is still in the future, use it directly
        if base > now:
            next_run = base
        else:
            next_run = base + delta

        # Safety: ensure next_run is strictly in the future
        while next_run <= now:
            next_run += delta

        return next_run
