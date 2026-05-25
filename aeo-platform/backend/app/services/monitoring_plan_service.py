"""Question set and monitoring plan service."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import case, delete, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.brand_intelligence import BrandIntelligenceQuestion, BrandObjectLink
from app.models.entity import Entity
from app.models.monitoring_plan import (
    MonitoringEvidenceRecord,
    MonitoringPlan,
    MonitoringPlanStatus,
    MonitoringQuestionSet,
    MonitoringRun,
    MonitoringRunPolicy,
    MonitoringRunStatus,
    QuestionSetSource,
    QuestionSetStatus,
)
from app.models.monitoring_schedule import (
    MonitoringSchedule,
    ScheduleFrequency,
    ScheduleStatus,
)
from app.models.task import AnalysisTask
from app.services.brand_object_link_service import BrandObjectLinkService
from app.services.monitoring_service import MonitoringService

logger = logging.getLogger(__name__)


MONITOR_MODE_ALIASES = {
    "panorama": "panorama",
    "panorama_monitoring": "panorama",
    "baseline": "panorama",
    "brand": "panorama",
    "scenario": "scenario",
    "scenario_monitoring": "scenario",
    "persona": "scenario",
}

ENDPOINT_REGISTRY: dict[str, dict[str, str]] = {
    "doubao_api": {
        "id": "doubao_api",
        "platform": "doubao",
        "fetch_method": "api",
        "display_name": "豆包API",
    },
    "doubao_browser": {
        "id": "doubao_browser",
        "platform": "doubao",
        "fetch_method": "browser",
        "display_name": "豆包网页版",
    },
    "deepseek_browser": {
        "id": "deepseek_browser",
        "platform": "deepseek",
        "fetch_method": "browser",
        "display_name": "DeepSeek网页版",
    },
    "yuanbao_api": {
        "id": "yuanbao_api",
        "platform": "yuanbao",
        "fetch_method": "api",
        "display_name": "元宝API",
    },
    "yuanbao_browser": {
        "id": "yuanbao_browser",
        "platform": "yuanbao",
        "fetch_method": "browser",
        "display_name": "元宝网页版",
    },
    "kimi_api": {
        "id": "kimi_api",
        "platform": "kimi",
        "fetch_method": "api",
        "display_name": "Kimi API",
    },
    "kimi_browser": {
        "id": "kimi_browser",
        "platform": "kimi",
        "fetch_method": "browser",
        "display_name": "Kimi 网页版",
    },
}

QUICK_ENDPOINT_IDS = ["doubao_api", "yuanbao_api", "kimi_api", "deepseek_browser"]
FULL_BROWSER_ENDPOINT_IDS = [
    "doubao_browser",
    "yuanbao_browser",
    "kimi_browser",
    "deepseek_browser",
]


class MonitoringPlanService:
    """Owns user-confirmed question sets, plans, runs, and evidence rows."""

    MAX_PLAN_QUESTIONS = 30

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _finish_mutation(self, row: Any, *, commit: bool = True) -> None:
        if commit:
            await self.db.commit()
            await self.db.refresh(row)
            return
        await self.db.flush()

    @classmethod
    def normalize_monitor_mode(cls, value: str | None) -> str:
        normalized = str(value or "").strip().lower()
        if not normalized:
            return "panorama"
        mode = MONITOR_MODE_ALIASES.get(normalized)
        if mode is None:
            raise ValueError("monitor_mode must be panorama or scenario")
        return mode

    @classmethod
    def endpoint_catalog(cls) -> list[dict[str, str]]:
        return [dict(item) for item in ENDPOINT_REGISTRY.values()]

    @classmethod
    def endpoint_display_name(cls, endpoint_id: str) -> str:
        endpoint = ENDPOINT_REGISTRY.get(str(endpoint_id or "").strip())
        return endpoint["display_name"] if endpoint else str(endpoint_id or "")

    @classmethod
    def normalize_endpoint_ids(
        cls,
        endpoint_ids: list[str] | None,
        *,
        run_policy: str | None = None,
    ) -> list[str]:
        if not endpoint_ids:
            if run_policy == MonitoringRunPolicy.FULL_BROWSER.value:
                endpoint_ids = list(FULL_BROWSER_ENDPOINT_IDS)
            else:
                endpoint_ids = list(QUICK_ENDPOINT_IDS)

        normalized: list[str] = []
        invalid: list[str] = []
        for raw_endpoint_id in endpoint_ids:
            endpoint_id = str(raw_endpoint_id or "").strip()
            if not endpoint_id:
                continue
            if endpoint_id not in ENDPOINT_REGISTRY:
                invalid.append(endpoint_id)
                continue
            if endpoint_id not in normalized:
                normalized.append(endpoint_id)

        if invalid:
            supported = "、".join(
                item["display_name"] for item in ENDPOINT_REGISTRY.values()
            )
            raise ValueError(
                f"不支持的平台来源：{'、'.join(invalid)}。支持范围：{supported}"
            )
        if not normalized:
            raise ValueError("至少需要选择一个平台来源。")
        return normalized

    @classmethod
    def endpoint_ids_to_platforms(cls, endpoint_ids: list[str]) -> list[str]:
        platforms: list[str] = []
        for endpoint_id in endpoint_ids:
            endpoint = ENDPOINT_REGISTRY.get(endpoint_id)
            platform = endpoint.get("platform") if endpoint else None
            if platform and platform not in platforms:
                platforms.append(platform)
        return platforms

    @classmethod
    def endpoint_ids_to_labels(cls, endpoint_ids: list[str] | None) -> list[str]:
        return [
            cls.endpoint_display_name(endpoint_id)
            for endpoint_id in endpoint_ids or []
            if endpoint_id in ENDPOINT_REGISTRY
        ]

    @classmethod
    def endpoint_id_for_answer(
        cls,
        platform: str | None,
        fetch_method: str | None,
    ) -> tuple[str, str]:
        normalized_platform = str(platform or "").strip().lower()
        normalized_method = str(fetch_method or "").strip().lower()
        if normalized_method in {"web", "webpage", "web_page"}:
            normalized_method = "browser"
        if normalized_platform == "hunyuan":
            normalized_platform = "yuanbao"
        for endpoint_id, endpoint in ENDPOINT_REGISTRY.items():
            if (
                endpoint["platform"] == normalized_platform
                and endpoint["fetch_method"] == normalized_method
            ):
                return endpoint_id, endpoint["display_name"]
        if normalized_platform == "deepseek":
            return "deepseek_browser", "DeepSeek网页版"
        label = normalized_platform or str(platform or "")
        return f"{normalized_platform}:{normalized_method}", label

    @classmethod
    def normalize_questions(cls, questions: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        for index, item in enumerate(questions or [], start=1):
            if isinstance(item, str):
                text = item.strip()
                raw: dict[str, Any] = {}
            elif isinstance(item, dict):
                raw = item
                text = str(
                    raw.get("question_text")
                    or raw.get("text")
                    or raw.get("core_question")
                    or raw.get("question")
                    or ""
                ).strip()
            else:
                continue
            if not text:
                continue
            dedupe_key = " ".join(text.split()).casefold()
            if dedupe_key in seen_texts:
                continue
            seen_texts.add(dedupe_key)
            question_id = str(
                raw.get("question_id") or raw.get("id") or f"q_{index:03d}"
            ).strip()
            normalized.append(
                {
                    "question_id": question_id,
                    "question_text": text,
                    "scene": str(
                        raw.get("scene") or raw.get("category") or ""
                    ).strip(),
                    "intent": str(
                        raw.get("intent") or raw.get("user_intent") or ""
                    ).strip(),
                    "stage": str(
                        raw.get("stage") or raw.get("decision_stage") or ""
                    ).strip(),
                }
            )
        return normalized

    def _enforce_question_limit(self, questions: list[dict[str, Any]]) -> None:
        if len(questions) > self.MAX_PLAN_QUESTIONS:
            raise ValueError(
                f"一个监测计划最多支持 {self.MAX_PLAN_QUESTIONS} 个问题，请删减或拆分问题集。"
            )

    @staticmethod
    def _monitoring_question_object_id(
        question_set_id: UUID,
        question_id: str,
    ) -> str:
        normalized_question_id = str(question_id or "").strip() or "question"
        return f"mqs:{question_set_id.hex[:12]}:{normalized_question_id[:80]}"

    async def _ensure_brand_questions_for_question_set(
        self,
        question_set: MonitoringQuestionSet,
    ) -> list[BrandIntelligenceQuestion]:
        rows: list[BrandIntelligenceQuestion] = []
        normalized_questions = self.normalize_questions(question_set.questions or [])
        for projection in normalized_questions:
            original_question_id = str(projection.get("question_id") or "")
            durable_question_id = self._monitoring_question_object_id(
                question_set.id,
                original_question_id,
            )
            conditions = [
                BrandIntelligenceQuestion.entity_id == question_set.entity_id,
                BrandIntelligenceQuestion.question_id.in_(
                    [original_question_id, durable_question_id]
                ),
                BrandIntelligenceQuestion.question_text
                == str(projection.get("question_text") or ""),
            ]
            if question_set.source_session_id is None:
                conditions.append(BrandIntelligenceQuestion.session_id.is_(None))
            else:
                conditions.append(
                    BrandIntelligenceQuestion.session_id
                    == question_set.source_session_id
                )
            existing = (
                await self.db.execute(
                    select(BrandIntelligenceQuestion)
                    .where(*conditions)
                    .order_by(desc(BrandIntelligenceQuestion.created_at))
                    .limit(1)
                )
            ).scalar_one_or_none()
            if existing is not None:
                if question_set.status == QuestionSetStatus.CONFIRMED.value:
                    existing.status = "confirmed"
                rows.append(existing)
                continue

            row = BrandIntelligenceQuestion(
                entity_id=question_set.entity_id,
                session_id=question_set.source_session_id,
                question_id=durable_question_id,
                question_text=str(projection.get("question_text") or ""),
                category=str(projection.get("scene") or ""),
                user_intent=str(projection.get("intent") or ""),
                decision_stage=str(projection.get("stage") or ""),
                status=(
                    "confirmed"
                    if question_set.status == QuestionSetStatus.CONFIRMED.value
                    else "generated"
                ),
                source_payload={
                    "source": "monitoring_question_set",
                    "question_set_id": str(question_set.id),
                    "original_question_id": str(projection.get("question_id") or ""),
                },
            )
            self.db.add(row)
            rows.append(row)
        await self.db.flush()
        return rows

    async def _replace_monitoring_plan_links(
        self,
        plan: MonitoringPlan,
        question_sets: list[MonitoringQuestionSet],
    ) -> None:
        await self.db.execute(
            delete(BrandObjectLink).where(
                BrandObjectLink.entity_id == plan.entity_id,
                BrandObjectLink.from_object_type == "monitoring_plan",
                BrandObjectLink.from_object_id == str(plan.id),
                BrandObjectLink.link_type.in_(
                    [
                        "monitoring_plan_uses_question_set",
                        "monitoring_plan_tracks_question",
                    ]
                ),
            )
        )
        link_service = BrandObjectLinkService(self.db)
        for question_set in question_sets:
            await self.db.execute(
                delete(BrandObjectLink).where(
                    BrandObjectLink.entity_id == plan.entity_id,
                    BrandObjectLink.from_object_type == "question_set",
                    BrandObjectLink.from_object_id == str(question_set.id),
                    BrandObjectLink.link_type == "question_set_contains_question",
                )
            )
            await link_service.ensure_link(
                entity_id=plan.entity_id,
                link_type="monitoring_plan_uses_question_set",
                from_object_type="monitoring_plan",
                from_object_id=str(plan.id),
                to_object_type="question_set",
                to_object_id=str(question_set.id),
                extra_metadata={
                    "monitor_mode": question_set.monitor_mode,
                    "question_count": question_set.question_count,
                },
            )
            question_rows = await self._ensure_brand_questions_for_question_set(
                question_set
            )
            for question in question_rows:
                await link_service.ensure_link(
                    entity_id=plan.entity_id,
                    link_type="question_set_contains_question",
                    from_object_type="question_set",
                    from_object_id=str(question_set.id),
                    to_object_type="simulated_question",
                    to_object_id=str(question.id),
                    extra_metadata={"question_id": question.question_id},
                )
                await link_service.ensure_link(
                    entity_id=plan.entity_id,
                    link_type="monitoring_plan_tracks_question",
                    from_object_type="monitoring_plan",
                    from_object_id=str(plan.id),
                    to_object_type="simulated_question",
                    to_object_id=str(question.id),
                    extra_metadata={
                        "question_set_id": str(question_set.id),
                        "question_id": question.question_id,
                    },
                )

    async def create_question_set(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        monitor_mode: str,
        questions: list[Any],
        title: str | None = None,
        source: QuestionSetSource | str = QuestionSetSource.CHAT_GENERATED,
        source_session_id: UUID | None = None,
        source_task_id: UUID | None = None,
        extra_metadata: dict[str, Any] | None = None,
        commit: bool = True,
    ) -> MonitoringQuestionSet:
        mode = self.normalize_monitor_mode(monitor_mode)
        normalized_questions = self.normalize_questions(questions)
        self._enforce_question_limit(normalized_questions)
        if not normalized_questions:
            raise ValueError("问题集不能为空。")
        source_value = source.value if isinstance(source, QuestionSetSource) else str(source)
        question_set = MonitoringQuestionSet(
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=mode,
            status=QuestionSetStatus.DRAFT.value,
            source=source_value,
            title=title or ("用户场景问题集" if mode == "scenario" else "品牌全景问题集"),
            version=1,
            questions=normalized_questions,
            question_count=len(normalized_questions),
            source_session_id=source_session_id,
            source_task_id=source_task_id,
            extra_metadata=extra_metadata or {},
        )
        self.db.add(question_set)
        await self._finish_mutation(question_set, commit=commit)
        return question_set

    async def append_questions(
        self,
        *,
        question_set_id: UUID,
        user_id: UUID,
        questions: list[Any],
        commit: bool = True,
    ) -> MonitoringQuestionSet:
        question_set = await self.get_question_set(question_set_id, user_id=user_id)
        if question_set is None:
            raise ValueError("问题集不存在。")
        if question_set.status != QuestionSetStatus.DRAFT.value:
            raise ValueError("只能给草稿问题集追加问题。")
        merged = self.normalize_questions((question_set.questions or []) + questions)
        self._enforce_question_limit(merged)
        question_set.questions = merged
        question_set.question_count = len(merged)
        question_set.version = (question_set.version or 1) + 1
        question_set.updated_at = datetime.now(timezone.utc)
        await self._finish_mutation(question_set, commit=commit)
        return question_set

    async def confirm_question_set(
        self,
        *,
        question_set_id: UUID,
        user_id: UUID,
        commit: bool = True,
    ) -> MonitoringQuestionSet:
        question_set = await self.get_question_set(question_set_id, user_id=user_id)
        if question_set is None:
            raise ValueError("问题集不存在。")
        self._enforce_question_limit(question_set.questions or [])
        if not question_set.questions:
            raise ValueError("问题集不能为空。")
        question_set.status = QuestionSetStatus.CONFIRMED.value
        question_set.confirmed_at = question_set.confirmed_at or datetime.now(timezone.utc)
        question_set.updated_at = datetime.now(timezone.utc)
        await self._finish_mutation(question_set, commit=commit)
        return question_set

    async def get_question_set(
        self,
        question_set_id: UUID,
        *,
        user_id: UUID | None = None,
        entity_id: UUID | None = None,
    ) -> MonitoringQuestionSet | None:
        conditions = [MonitoringQuestionSet.id == question_set_id]
        if user_id is not None:
            conditions.append(MonitoringQuestionSet.user_id == user_id)
        if entity_id is not None:
            conditions.append(MonitoringQuestionSet.entity_id == entity_id)
        result = await self.db.execute(select(MonitoringQuestionSet).where(*conditions))
        return result.scalar_one_or_none()

    async def list_question_sets(
        self,
        *,
        user_id: UUID,
        entity_id: UUID | None = None,
        monitor_mode: str | None = None,
        status: str | None = None,
        limit: int = 50,
    ) -> list[MonitoringQuestionSet]:
        conditions = [MonitoringQuestionSet.user_id == user_id]
        if entity_id is not None:
            conditions.append(MonitoringQuestionSet.entity_id == entity_id)
        if monitor_mode:
            conditions.append(
                MonitoringQuestionSet.monitor_mode
                == self.normalize_monitor_mode(monitor_mode)
            )
        if status:
            conditions.append(MonitoringQuestionSet.status == status)
        result = await self.db.execute(
            select(MonitoringQuestionSet)
            .where(*conditions)
            .order_by(desc(MonitoringQuestionSet.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create_plan(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        monitor_mode: str,
        question_set_ids: list[UUID],
        endpoint_ids: list[str] | None = None,
        run_policy: str = MonitoringRunPolicy.QUICK.value,
        status: str = MonitoringPlanStatus.DRAFT.value,
        frequency: str = "weekly",
        preferred_hour: int = 3,
        timezone_str: str = "Asia/Shanghai",
        title: str | None = None,
        commit: bool = True,
    ) -> MonitoringPlan:
        mode = self.normalize_monitor_mode(monitor_mode)
        run_policy = self._normalize_run_policy(run_policy)
        endpoint_ids = self.normalize_endpoint_ids(endpoint_ids, run_policy=run_policy)
        plan_status = self._normalize_plan_status(status)
        if plan_status == MonitoringPlanStatus.ACTIVE.value and run_policy != MonitoringRunPolicy.QUICK.value:
            raise ValueError("v1 自动监测只支持快速监测；完整浏览器监测需后续单独启用。")

        question_sets = await self._load_question_sets(
            user_id=user_id,
            entity_id=entity_id,
            question_set_ids=question_set_ids,
            require_confirmed=plan_status == MonitoringPlanStatus.ACTIVE.value,
        )
        questions = self._combine_question_sets(question_sets)
        self._enforce_question_limit(questions)
        if not questions:
            raise ValueError("监测计划至少需要一个问题。")

        plan = MonitoringPlan(
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=mode,
            status=plan_status,
            title=title or ("用户场景监测计划" if mode == "scenario" else "全景监测计划"),
            question_set_ids=[str(item.id) for item in question_sets],
            endpoint_ids=endpoint_ids,
            run_policy=run_policy,
            frequency=frequency,
            preferred_hour=preferred_hour,
            timezone=timezone_str,
        )
        self.db.add(plan)
        await self.db.flush()
        await self._replace_monitoring_plan_links(plan, question_sets)
        if plan.status == MonitoringPlanStatus.ACTIVE.value:
            await self._upsert_schedule_for_plan(plan, question_sets)
        await self._finish_mutation(plan, commit=commit)
        return plan

    async def create_or_update_active_plan_from_question_set(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        question_set_id: UUID,
        monitor_mode: str,
        fetch_mode: str = "fast",
    ) -> MonitoringPlan:
        mode = self.normalize_monitor_mode(monitor_mode)
        run_policy = (
            MonitoringRunPolicy.FULL_BROWSER.value
            if str(fetch_mode or "").strip().lower() == "full"
            else MonitoringRunPolicy.QUICK.value
        )
        if run_policy != MonitoringRunPolicy.QUICK.value:
            raise ValueError("v1 自动监测只支持快速监测；完整浏览器监测需后续单独启用。")

        question_set_preview = await self.get_question_set(
            question_set_id,
            user_id=user_id,
        )
        if question_set_preview is None:
            raise ValueError("问题集不存在。")
        if str(question_set_preview.entity_id) != str(entity_id):
            raise ValueError("问题集不属于当前品牌。")
        if question_set_preview.monitor_mode != mode:
            raise ValueError("问题集监测模式与当前计划不匹配。")

        question_set = await self.confirm_question_set(
            question_set_id=question_set_id,
            user_id=user_id,
        )

        existing = await self.get_entity_plan(
            user_id=user_id,
            entity_id=entity_id,
            monitor_mode=mode,
            include_archived=False,
        )
        if existing is None:
            return await self.create_plan(
                user_id=user_id,
                entity_id=entity_id,
                monitor_mode=mode,
                question_set_ids=[question_set.id],
                run_policy=run_policy,
                status=MonitoringPlanStatus.ACTIVE.value,
            )

        existing.status = MonitoringPlanStatus.ACTIVE.value
        existing.question_set_ids = [str(question_set.id)]
        existing.endpoint_ids = self.normalize_endpoint_ids(None, run_policy=run_policy)
        existing.run_policy = run_policy
        existing.updated_at = datetime.now(timezone.utc)
        await self._replace_monitoring_plan_links(existing, [question_set])
        await self._upsert_schedule_for_plan(existing, [question_set])
        await self.db.commit()
        await self.db.refresh(existing)
        return existing

    async def confirm_question_set_and_activate_quick_plan(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        question_set_id: UUID,
        monitor_mode: str,
    ) -> MonitoringPlan:
        """Main Chat confirmation path for enabling a confirmed quick plan."""
        return await self.create_or_update_active_plan_from_question_set(
            user_id=user_id,
            entity_id=entity_id,
            question_set_id=question_set_id,
            monitor_mode=monitor_mode,
            fetch_mode="fast",
        )

    async def get_entity_plan(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        monitor_mode: str,
        include_archived: bool = False,
    ) -> MonitoringPlan | None:
        conditions = [
            MonitoringPlan.user_id == user_id,
            MonitoringPlan.entity_id == entity_id,
            MonitoringPlan.monitor_mode == self.normalize_monitor_mode(monitor_mode),
        ]
        if not include_archived:
            conditions.append(MonitoringPlan.status != MonitoringPlanStatus.ARCHIVED.value)
        result = await self.db.execute(
            select(MonitoringPlan)
            .where(*conditions)
            .order_by(
                case(
                    (MonitoringPlan.status == MonitoringPlanStatus.ACTIVE.value, 0),
                    (MonitoringPlan.status == MonitoringPlanStatus.PAUSED.value, 1),
                    (MonitoringPlan.status == MonitoringPlanStatus.DRAFT.value, 2),
                    else_=3,
                ),
                desc(MonitoringPlan.updated_at),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_plan(self, plan_id: UUID, *, user_id: UUID | None = None) -> MonitoringPlan | None:
        conditions = [MonitoringPlan.id == plan_id]
        if user_id is not None:
            conditions.append(MonitoringPlan.user_id == user_id)
        result = await self.db.execute(select(MonitoringPlan).where(*conditions))
        return result.scalar_one_or_none()

    async def list_plans(
        self,
        *,
        user_id: UUID,
        entity_id: UUID | None = None,
        monitor_mode: str | None = None,
        limit: int = 50,
    ) -> list[MonitoringPlan]:
        conditions = [MonitoringPlan.user_id == user_id]
        if entity_id is not None:
            conditions.append(MonitoringPlan.entity_id == entity_id)
        if monitor_mode:
            conditions.append(
                MonitoringPlan.monitor_mode == self.normalize_monitor_mode(monitor_mode)
            )
        result = await self.db.execute(
            select(MonitoringPlan)
            .where(*conditions)
            .order_by(desc(MonitoringPlan.updated_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def activate_plan(
        self,
        *,
        plan_id: UUID,
        user_id: UUID,
        commit: bool = True,
    ) -> MonitoringPlan:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            raise ValueError("监测计划不存在。")
        if plan.run_policy != MonitoringRunPolicy.QUICK.value:
            raise ValueError("v1 自动监测只支持快速监测；完整浏览器监测需后续单独启用。")
        question_sets = await self._load_question_sets(
            user_id=user_id,
            entity_id=plan.entity_id,
            question_set_ids=[UUID(str(item)) for item in plan.question_set_ids or []],
            require_confirmed=True,
        )
        questions = self._combine_question_sets(question_sets)
        self._enforce_question_limit(questions)
        plan.status = MonitoringPlanStatus.ACTIVE.value
        plan.updated_at = datetime.now(timezone.utc)
        await self._replace_monitoring_plan_links(plan, question_sets)
        await self._upsert_schedule_for_plan(plan, question_sets)
        await self._finish_mutation(plan, commit=commit)
        return plan

    async def update_plan(
        self,
        *,
        plan_id: UUID,
        user_id: UUID,
        question_set_ids: list[UUID] | None = None,
        endpoint_ids: list[str] | None = None,
        run_policy: str | None = None,
        status: str | None = None,
        frequency: str | None = None,
        preferred_hour: int | None = None,
        timezone_str: str | None = None,
        title: str | None = None,
        commit: bool = True,
    ) -> MonitoringPlan:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            raise ValueError("监测计划不存在。")
        question_sets_for_links: list[MonitoringQuestionSet] | None = None
        if run_policy is not None:
            plan.run_policy = self._normalize_run_policy(run_policy)
        if endpoint_ids is not None:
            plan.endpoint_ids = self.normalize_endpoint_ids(
                endpoint_ids,
                run_policy=plan.run_policy,
            )
        if question_set_ids is not None:
            question_sets = await self._load_question_sets(
                user_id=user_id,
                entity_id=plan.entity_id,
                question_set_ids=question_set_ids,
                require_confirmed=plan.status == MonitoringPlanStatus.ACTIVE.value,
            )
            self._enforce_question_limit(self._combine_question_sets(question_sets))
            plan.question_set_ids = [str(item.id) for item in question_sets]
            question_sets_for_links = question_sets
        if status is not None:
            plan.status = self._normalize_plan_status(status)
        if frequency is not None:
            plan.frequency = frequency
        if preferred_hour is not None:
            plan.preferred_hour = preferred_hour
        if timezone_str is not None:
            plan.timezone = timezone_str
        if title is not None:
            plan.title = title
        if plan.status == MonitoringPlanStatus.ACTIVE.value:
            if plan.run_policy != MonitoringRunPolicy.QUICK.value:
                raise ValueError("v1 自动监测只支持快速监测；完整浏览器监测需后续单独启用。")
            question_sets = await self._load_question_sets(
                user_id=user_id,
                entity_id=plan.entity_id,
                question_set_ids=[
                    UUID(str(item)) for item in plan.question_set_ids or []
                ],
                require_confirmed=True,
            )
            await self._replace_monitoring_plan_links(plan, question_sets)
            await self._upsert_schedule_for_plan(plan, question_sets)
        elif question_sets_for_links is not None:
            await self._replace_monitoring_plan_links(plan, question_sets_for_links)
        plan.updated_at = datetime.now(timezone.utc)
        await self._finish_mutation(plan, commit=commit)
        return plan

    async def pause_plan(
        self,
        *,
        plan_id: UUID,
        user_id: UUID,
        commit: bool = True,
    ) -> MonitoringPlan:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            raise ValueError("监测计划不存在。")
        plan.status = MonitoringPlanStatus.PAUSED.value
        plan.updated_at = datetime.now(timezone.utc)
        schedule = await self._get_schedule_for_plan(plan.id)
        if schedule is not None and schedule.status == ScheduleStatus.ACTIVE:
            schedule.status = ScheduleStatus.PAUSED
            schedule.next_run_at = None
        await self._finish_mutation(plan, commit=commit)
        return plan

    async def archive_plan(
        self,
        *,
        plan_id: UUID,
        user_id: UUID,
        commit: bool = True,
    ) -> MonitoringPlan:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            raise ValueError("监测计划不存在。")
        plan.status = MonitoringPlanStatus.ARCHIVED.value
        plan.updated_at = datetime.now(timezone.utc)
        schedule = await self._get_schedule_for_plan(plan.id)
        if schedule is not None:
            schedule.status = ScheduleStatus.PAUSED
            schedule.next_run_at = None
        await self._finish_mutation(plan, commit=commit)
        return plan

    async def submit_plan_run(self, *, plan_id: UUID, user_id: UUID) -> MonitoringRun:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            raise ValueError("监测计划不存在。")
        if plan.status != MonitoringPlanStatus.ACTIVE.value:
            raise ValueError("只有 active 监测计划可以触发复测。")
        if plan.run_policy != MonitoringRunPolicy.QUICK.value:
            raise ValueError("完整浏览器监测暂未接入自动执行。")
        schedule = await self._get_schedule_for_plan(plan.id)
        if schedule is None:
            question_sets = await self._load_question_sets(
                user_id=user_id,
                entity_id=plan.entity_id,
                question_set_ids=[UUID(str(item)) for item in plan.question_set_ids or []],
                require_confirmed=True,
            )
            schedule = await self._upsert_schedule_for_plan(plan, question_sets)

        entity = await self.db.get(Entity, plan.entity_id)
        if entity is None:
            raise ValueError("品牌不存在。")

        from app.services.job_submission_service import JobSubmissionService
        from app.services.scheduler import _get_or_create_monitoring_session

        monitoring_session = await _get_or_create_monitoring_session(
            self.db,
            schedule_id=schedule.id,
            user_id=plan.user_id,
            entity_id=plan.entity_id,
            entity_name=entity.name,
        )
        submitted = await JobSubmissionService(self.db).submit_scheduled_analysis(
            user_id=plan.user_id,
            session_id=monitoring_session.id,
            brand_name=entity.name,
            entity_id=plan.entity_id,
            monitoring_schedule_id=schedule.id,
        )
        monitoring_run = await self._create_or_update_run_for_task(
            plan=plan,
            schedule=schedule,
            task=submitted.task,
            task_run_id=submitted.run.id,
            status=MonitoringRunStatus.PENDING.value,
        )
        await self.db.commit()
        await self.db.refresh(monitoring_run)
        return monitoring_run

    async def record_scheduler_run_started(
        self,
        *,
        schedule: MonitoringSchedule,
        task: AnalysisTask,
        task_run_id: UUID | None,
    ) -> MonitoringRun | None:
        if schedule.monitoring_plan_id is None:
            return None
        plan = await self.get_plan(schedule.monitoring_plan_id)
        if plan is None:
            return None
        run = await self._create_or_update_run_for_task(
            plan=plan,
            schedule=schedule,
            task=task,
            task_run_id=task_run_id,
            status=MonitoringRunStatus.RUNNING.value,
        )
        run.started_at = run.started_at or datetime.now(timezone.utc)
        await self.db.commit()
        return run

    async def record_run_completed(
        self,
        *,
        task_id: UUID,
        snapshot_id: UUID,
        final_state: dict[str, Any] | None = None,
    ) -> None:
        run = await self._get_run_by_task(task_id)
        if run is None:
            return
        now = datetime.now(timezone.utc)
        run.status = MonitoringRunStatus.COMPLETED.value
        run.snapshot_id = snapshot_id
        run.completed_at = now
        run.updated_at = now
        await self._replace_evidence_records(run, final_state or {})
        await self.db.commit()

    async def record_run_failed(
        self,
        *,
        task_id: UUID,
        error_message: str,
        error_stage: str | None = None,
    ) -> None:
        run = await self._get_run_by_task(task_id)
        if run is None:
            return
        now = datetime.now(timezone.utc)
        run.status = MonitoringRunStatus.FAILED.value
        run.error_message = error_message
        run.error_stage = error_stage
        run.completed_at = now
        run.updated_at = now
        await self.db.commit()

    async def list_runs(
        self,
        *,
        plan_id: UUID,
        user_id: UUID,
        limit: int = 20,
    ) -> list[MonitoringRun]:
        plan = await self.get_plan(plan_id, user_id=user_id)
        if plan is None:
            return []
        result = await self.db.execute(
            select(MonitoringRun)
            .where(MonitoringRun.plan_id == plan_id)
            .order_by(desc(MonitoringRun.created_at))
            .limit(limit)
        )
        return list(result.scalars().all())

    async def question_set_to_dict(self, question_set: MonitoringQuestionSet) -> dict[str, Any]:
        return {
            "id": str(question_set.id),
            "user_id": str(question_set.user_id),
            "entity_id": str(question_set.entity_id),
            "monitor_mode": question_set.monitor_mode,
            "status": question_set.status,
            "source": question_set.source,
            "title": question_set.title,
            "version": question_set.version,
            "questions": question_set.questions or [],
            "question_count": question_set.question_count,
            "source_session_id": (
                str(question_set.source_session_id)
                if question_set.source_session_id
                else None
            ),
            "source_task_id": (
                str(question_set.source_task_id) if question_set.source_task_id else None
            ),
            "confirmed_at": (
                question_set.confirmed_at.isoformat()
                if question_set.confirmed_at
                else None
            ),
            "created_at": question_set.created_at.isoformat(),
            "updated_at": question_set.updated_at.isoformat(),
        }

    async def plan_to_dict(self, plan: MonitoringPlan) -> dict[str, Any]:
        question_set_ids = [str(item) for item in plan.question_set_ids or []]
        question_sets = await self._load_question_sets(
            user_id=plan.user_id,
            entity_id=plan.entity_id,
            question_set_ids=[UUID(item) for item in question_set_ids],
            require_confirmed=False,
        )
        question_count = len(self._combine_question_sets(question_sets))
        endpoint_ids = [str(item) for item in plan.endpoint_ids or []]
        schedule = await self._get_schedule_for_plan(plan.id)
        return {
            "id": str(plan.id),
            "user_id": str(plan.user_id),
            "entity_id": str(plan.entity_id),
            "monitor_mode": plan.monitor_mode,
            "status": plan.status,
            "title": plan.title,
            "question_set_ids": question_set_ids,
            "question_set_label": "、".join(
                item.title for item in question_sets if item.title
            )
            or ("用户场景问题集" if plan.monitor_mode == "scenario" else "品牌全景问题集"),
            "question_count": question_count,
            "endpoint_ids": endpoint_ids,
            "endpoint_labels": self.endpoint_ids_to_labels(endpoint_ids),
            "run_policy": plan.run_policy,
            "frequency": plan.frequency,
            "preferred_hour": plan.preferred_hour,
            "timezone": plan.timezone,
            "schedule_id": str(schedule.id) if schedule else None,
            "schedule_status": schedule.status.value if schedule and schedule.status else None,
            "created_at": plan.created_at.isoformat(),
            "updated_at": plan.updated_at.isoformat(),
        }

    async def run_to_dict(self, run: MonitoringRun) -> dict[str, Any]:
        return {
            "id": str(run.id),
            "user_id": str(run.user_id),
            "entity_id": str(run.entity_id),
            "plan_id": str(run.plan_id),
            "schedule_id": str(run.schedule_id) if run.schedule_id else None,
            "task_id": str(run.task_id) if run.task_id else None,
            "task_run_id": str(run.task_run_id) if run.task_run_id else None,
            "snapshot_id": str(run.snapshot_id) if run.snapshot_id else None,
            "status": run.status,
            "run_policy": run.run_policy,
            "monitor_mode": run.monitor_mode,
            "endpoint_ids": run.endpoint_ids or [],
            "endpoint_labels": self.endpoint_ids_to_labels(run.endpoint_ids or []),
            "question_set_ids": run.question_set_ids or [],
            "question_count": run.question_count,
            "error_message": run.error_message,
            "error_stage": run.error_stage,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "created_at": run.created_at.isoformat(),
            "updated_at": run.updated_at.isoformat(),
        }

    def _normalize_plan_status(self, value: str) -> str:
        normalized = str(value or "").strip().lower()
        allowed = {item.value for item in MonitoringPlanStatus}
        if normalized not in allowed:
            raise ValueError(f"Invalid plan status: {value}")
        return normalized

    def _normalize_run_policy(self, value: str) -> str:
        normalized = str(value or MonitoringRunPolicy.QUICK.value).strip().lower()
        allowed = {item.value for item in MonitoringRunPolicy}
        if normalized not in allowed:
            raise ValueError(f"Invalid run policy: {value}")
        return normalized

    async def _load_question_sets(
        self,
        *,
        user_id: UUID,
        entity_id: UUID,
        question_set_ids: list[UUID],
        require_confirmed: bool,
    ) -> list[MonitoringQuestionSet]:
        if not question_set_ids:
            raise ValueError("监测计划至少需要一个问题集。")
        result = await self.db.execute(
            select(MonitoringQuestionSet).where(
                MonitoringQuestionSet.user_id == user_id,
                MonitoringQuestionSet.entity_id == entity_id,
                MonitoringQuestionSet.id.in_(question_set_ids),
            )
        )
        rows = list(result.scalars().all())
        by_id = {item.id: item for item in rows}
        missing = [item for item in question_set_ids if item not in by_id]
        if missing:
            raise ValueError("问题集不存在或不属于当前品牌。")
        if require_confirmed:
            drafts = [
                item.title or str(item.id)
                for item in rows
                if item.status != QuestionSetStatus.CONFIRMED.value
            ]
            if drafts:
                raise ValueError("问题集必须先由用户确认，才能启用自动监测。")
        modes = {item.monitor_mode for item in rows}
        if len(modes) > 1:
            raise ValueError("一个监测计划不能混合全景问题集和用户场景问题集。")
        return [by_id[item] for item in question_set_ids]

    def _combine_question_sets(
        self,
        question_sets: list[MonitoringQuestionSet],
    ) -> list[dict[str, Any]]:
        combined: list[Any] = []
        for question_set in question_sets:
            combined.extend(question_set.questions or [])
        return self.normalize_questions(combined)

    def _build_baseline_data(
        self,
        *,
        entity: Entity,
        question_sets: list[MonitoringQuestionSet],
    ) -> dict[str, Any]:
        questions = self._combine_question_sets(question_sets)
        aliases = []
        if entity.aliases:
            try:
                parsed_aliases = json.loads(entity.aliases)
                if isinstance(parsed_aliases, list):
                    aliases = [str(item) for item in parsed_aliases if item]
            except (TypeError, json.JSONDecodeError):
                aliases = []
        official_website = entity.domain or ""
        if official_website and not official_website.startswith(("http://", "https://")):
            official_website = f"https://{official_website}"
        return {
            "questions": [
                {
                    "id": item.get("question_id"),
                    "text": item.get("question_text"),
                    "category": item.get("scene") or "",
                    "intent": item.get("intent") or "",
                    "stage": item.get("stage") or "",
                }
                for item in questions
            ],
            "simulated_questions": {
                "generation_mode": "monitoring_plan",
                "simulated_questions": questions,
            },
            "brand_profile": {
                "brand_name": entity.name,
                "brand_keywords": aliases,
                "official_website": official_website,
                "industry": entity.industry,
                "description": entity.description,
            },
            "competitors": [],
            "competitive_landscape": None,
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "source": "monitoring_plan",
            "question_set_ids": [str(item.id) for item in question_sets],
        }

    async def _upsert_schedule_for_plan(
        self,
        plan: MonitoringPlan,
        question_sets: list[MonitoringQuestionSet],
    ) -> MonitoringSchedule:
        entity = await self.db.get(Entity, plan.entity_id)
        if entity is None:
            raise ValueError("品牌不存在。")
        baseline_data = self._build_baseline_data(entity=entity, question_sets=question_sets)
        monitoring_service = MonitoringService(self.db)
        schedule = await self._get_schedule_for_plan(plan.id)
        platforms = self.endpoint_ids_to_platforms(plan.endpoint_ids or [])
        if schedule is None:
            try:
                frequency = ScheduleFrequency(plan.frequency)
            except ValueError:
                frequency = ScheduleFrequency.WEEKLY
            schedule = await monitoring_service.create_schedule(
                user_id=plan.user_id,
                entity_id=plan.entity_id,
                frequency=frequency,
                preferred_hour=plan.preferred_hour,
                timezone_str=plan.timezone,
                platforms=platforms,
                status=(
                    ScheduleStatus.ACTIVE
                    if plan.status == MonitoringPlanStatus.ACTIVE.value
                    else ScheduleStatus.PAUSED
                ),
                monitor_mode=plan.monitor_mode,
                question_set_ids=[str(item.id) for item in question_sets],
                endpoint_ids=plan.endpoint_ids or [],
                run_policy=plan.run_policy,
                monitoring_plan_id=plan.id,
                baseline_data=baseline_data,
            )
        else:
            try:
                frequency = ScheduleFrequency(plan.frequency)
            except ValueError:
                frequency = ScheduleFrequency.WEEKLY
            await monitoring_service.update_schedule(
                schedule.id,
                frequency=frequency,
                preferred_hour=plan.preferred_hour,
                timezone=plan.timezone,
                platforms=platforms,
                status=(
                    ScheduleStatus.ACTIVE
                    if plan.status == MonitoringPlanStatus.ACTIVE.value
                    else ScheduleStatus.PAUSED
                ),
                monitor_mode=plan.monitor_mode,
                question_set_ids=[str(item.id) for item in question_sets],
                endpoint_ids=plan.endpoint_ids or [],
                run_policy=plan.run_policy,
                baseline_data=baseline_data,
                monitoring_plan_id=plan.id,
            )
            schedule = await monitoring_service.get_schedule(schedule.id) or schedule
        return schedule

    async def _get_schedule_for_plan(self, plan_id: UUID) -> MonitoringSchedule | None:
        result = await self.db.execute(
            select(MonitoringSchedule)
            .where(MonitoringSchedule.monitoring_plan_id == plan_id)
            .order_by(desc(MonitoringSchedule.updated_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_run_by_task(self, task_id: UUID) -> MonitoringRun | None:
        result = await self.db.execute(
            select(MonitoringRun)
            .where(MonitoringRun.task_id == task_id)
            .order_by(desc(MonitoringRun.created_at))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _create_or_update_run_for_task(
        self,
        *,
        plan: MonitoringPlan,
        schedule: MonitoringSchedule,
        task: AnalysisTask,
        task_run_id: UUID | None,
        status: str,
    ) -> MonitoringRun:
        existing = await self._get_run_by_task(task.id)
        question_count = len(schedule.baseline_data.get("questions", [])) if schedule.baseline_data else 0
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = MonitoringRun(
                user_id=plan.user_id,
                entity_id=plan.entity_id,
                plan_id=plan.id,
                schedule_id=schedule.id,
                task_id=task.id,
                task_run_id=task_run_id,
                status=status,
                run_policy=plan.run_policy,
                monitor_mode=plan.monitor_mode,
                endpoint_ids=plan.endpoint_ids or [],
                question_set_ids=plan.question_set_ids or [],
                question_count=question_count,
            )
            self.db.add(existing)
        else:
            existing.status = status
            existing.task_run_id = task_run_id or existing.task_run_id
            existing.endpoint_ids = plan.endpoint_ids or []
            existing.question_set_ids = plan.question_set_ids or []
            existing.question_count = question_count
            existing.updated_at = now
        if status == MonitoringRunStatus.RUNNING.value:
            existing.started_at = existing.started_at or now
        return existing

    async def _replace_evidence_records(
        self,
        run: MonitoringRun,
        final_state: dict[str, Any],
    ) -> None:
        await self.db.execute(
            delete(MonitoringEvidenceRecord).where(
                MonitoringEvidenceRecord.monitoring_run_id == run.id
            )
        )
        fetch_results = final_state.get("fetch_results") or []
        if not isinstance(fetch_results, list):
            return
        for question_result in fetch_results:
            if not isinstance(question_result, dict):
                continue
            question_id = str(question_result.get("question_id") or "").strip()
            question_text = str(question_result.get("question_text") or "").strip()
            for platform_result in question_result.get("platform_results") or []:
                if not isinstance(platform_result, dict):
                    continue
                platform = str(platform_result.get("platform") or "").strip()
                fetch_method = str(
                    platform_result.get("fetch_method")
                    or platform_result.get("source_variant")
                    or ""
                ).strip()
                endpoint_id, endpoint_label = self.endpoint_id_for_answer(
                    platform,
                    fetch_method,
                )
                citations = platform_result.get("citations") or []
                cited_domains = []
                if isinstance(citations, list):
                    for citation in citations:
                        if not isinstance(citation, dict):
                            continue
                        domain = str(
                            citation.get("domain")
                            or citation.get("source_domain")
                            or citation.get("url")
                            or ""
                        ).strip()
                        if domain:
                            cited_domains.append(domain)
                self.db.add(
                    MonitoringEvidenceRecord(
                        monitoring_run_id=run.id,
                        plan_id=run.plan_id,
                        entity_id=run.entity_id,
                        question_id=question_id,
                        question_text=question_text,
                        endpoint_id=endpoint_id,
                        endpoint_label=endpoint_label,
                        platform=platform,
                        fetch_method=fetch_method,
                        answer_status=(
                            "ok" if platform_result.get("success") else "failed"
                        ),
                        cited_domains=cited_domains,
                        raw_evidence=platform_result,
                    )
                )
