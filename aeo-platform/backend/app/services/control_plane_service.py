from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.models.entity import Entity, EntityVisibilityScope
from app.models.llm_usage import LLMUsageRecord
from app.models.organization import Organization
from app.models.session import Session as ChatSession
from app.models.task import AnalysisTask, TaskStatus
from app.models.user import User
from app.services.account_admin_service import AccountAdminService


class ControlPlaneService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.accounts = AccountAdminService(db)

    def _since(self, days: int) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    @staticmethod
    def _cache_hit_ratio(prompt_tokens: int, cached_prompt_tokens: int) -> float:
        if prompt_tokens <= 0:
            return 0.0
        return round(cached_prompt_tokens / prompt_tokens, 4)

    async def list_customers(self, *, days: int = 7) -> list[dict[str, object]]:
        organizations = await self.accounts.list_organizations()
        if not organizations:
            return []

        org_ids = [organization.id for organization in organizations]
        stats = await self._build_usage_stats(org_ids=org_ids, days=days)
        org_meta = self.accounts.build_organization_stats(organizations)
        personal_brand_counts = await self._build_personal_brand_counts(org_ids=org_ids)

        rows: list[dict[str, object]] = []
        for organization in organizations:
            meta = org_meta.get(organization.id, {})
            usage = stats.get(organization.id, {})
            organization_brand_count = int(meta.get("entity_count", 0))
            personal_brand_count = int(personal_brand_counts.get(organization.id, 0))
            rows.append(
                {
                    "organization_id": organization.id,
                    "customer_name": organization.legal_name,
                    "primary_account": meta.get("primary_account"),
                    "member_count": int(meta.get("member_count", 0)),
                    "brand_count": organization_brand_count + personal_brand_count,
                    "organization_brand_count": organization_brand_count,
                    "personal_brand_count": personal_brand_count,
                    "tokens_7d": int(usage.get("tokens_7d", 0)),
                    "cost_7d": float(usage.get("cost_7d", 0.0)),
                    "active_task_count": int(usage.get("active_task_count", 0)),
                    "last_active_at": usage.get("last_active_at"),
                }
            )
        rows.sort(
            key=lambda item: (
                item["last_active_at"] or datetime.fromtimestamp(0, tz=timezone.utc),
                item["cost_7d"],
            ),
            reverse=True,
        )
        return rows

    async def get_customer_detail(
        self,
        *,
        organization_id: UUID,
        days: int = 7,
        recent_task_limit: int = 20,
    ) -> dict[str, object]:
        organization = await self.accounts.get_organization(organization_id)
        if organization is None:
            raise ValueError("客户组织不存在")

        summaries = await self.list_customers(days=days)
        summary = next(
            (item for item in summaries if item["organization_id"] == organization_id),
            None,
        )
        if summary is None:
            summary = {
                "organization_id": organization.id,
                "customer_name": organization.legal_name,
                "primary_account": None,
                "member_count": len(organization.users),
                "brand_count": len(organization.entities),
                "organization_brand_count": len(organization.entities),
                "personal_brand_count": 0,
                "tokens_7d": 0,
                "cost_7d": 0.0,
                "active_task_count": 0,
                "last_active_at": None,
            }

        users = sorted(organization.users, key=lambda item: item.created_at)
        personal_entities_result = await self.db.execute(
            select(Entity)
            .options(selectinload(Entity.owner))
            .join(User, Entity.owner_user_id == User.id)
            .where(
                Entity.visibility_scope == EntityVisibilityScope.PERSONAL,
                User.organization_id == organization_id,
            )
            .order_by(Entity.updated_at.desc())
        )
        personal_entities = list(personal_entities_result.scalars().all())
        entities = sorted(
            [*organization.entities, *personal_entities],
            key=lambda item: item.updated_at,
            reverse=True,
        )
        tasks_result = await self.db.execute(
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.user),
                selectinload(AnalysisTask.entity),
            )
            .join(User, AnalysisTask.user_id == User.id)
            .where(User.organization_id == organization_id)
            .order_by(AnalysisTask.updated_at.desc())
            .limit(recent_task_limit)
        )
        recent_tasks = list(tasks_result.scalars().all())

        summary["brand_count"] = len(entities)
        summary["organization_brand_count"] = len(organization.entities)
        summary["personal_brand_count"] = len(personal_entities)

        return {
            "organization": organization,
            "summary": summary,
            "users": users,
            "entities": entities,
            "recent_tasks": recent_tasks,
        }

    async def list_tasks(
        self,
        *,
        days: int = 7,
        status: TaskStatus | None = None,
        organization_id: UUID | None = None,
        limit: int = 100,
    ) -> list[AnalysisTask]:
        since = self._since(days)
        stmt = (
            select(AnalysisTask)
            .options(
                selectinload(AnalysisTask.user).selectinload(User.organization),
                selectinload(AnalysisTask.entity),
            )
            .join(User, AnalysisTask.user_id == User.id)
            .where(AnalysisTask.updated_at >= since)
            .order_by(AnalysisTask.updated_at.desc())
            .limit(limit)
        )
        if status is not None:
            stmt = stmt.where(AnalysisTask.status == status)
        if organization_id is not None:
            stmt = stmt.where(User.organization_id == organization_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_observability_snapshot(
        self,
        *,
        days: int = 30,
        organization_id: UUID | None = None,
        limit: int = 12,
    ) -> dict[str, object]:
        since = self._since(days)
        item_limit = min(max(limit, 1), 50)

        task_user = aliased(User)
        session_user = aliased(User)
        task_org = aliased(Organization)
        session_org = aliased(Organization)

        org_id_expr = func.coalesce(task_org.id, session_org.id)
        customer_name_expr = func.coalesce(task_org.legal_name, session_org.legal_name)
        brand_name_expr = func.coalesce(
            AnalysisTask.brand_name,
            ChatSession.title,
            "未关联品牌",
        )

        summary_stmt = (
            select(
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.total_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.completion_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.cached_prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.billable_prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost_cache_aware), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.latency_ms), 0),
                func.coalesce(func.avg(LLMUsageRecord.latency_ms), 0.0),
                func.count(func.distinct(LLMUsageRecord.model_name)),
                func.min(LLMUsageRecord.created_at),
                func.max(LLMUsageRecord.created_at),
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .where(LLMUsageRecord.created_at >= since)
        )
        if organization_id is not None:
            summary_stmt = summary_stmt.where(
                or_(
                    task_user.organization_id == organization_id,
                    session_user.organization_id == organization_id,
                )
            )
        summary_row = (await self.db.execute(summary_stmt)).one()
        (
            total_calls,
            total_tokens,
            prompt_tokens,
            completion_tokens,
            cached_prompt_tokens,
            billable_prompt_tokens,
            total_cost,
            total_cost_cache_aware,
            total_latency_ms,
            avg_latency_ms,
            unique_models,
            first_call_at,
            last_call_at,
        ) = summary_row

        by_customer_brand_stmt = (
            select(
                org_id_expr,
                customer_name_expr,
                brand_name_expr,
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.total_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.cached_prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost_cache_aware), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.latency_ms), 0),
                func.coalesce(func.avg(LLMUsageRecord.latency_ms), 0.0),
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .outerjoin(task_org, task_user.organization_id == task_org.id)
            .outerjoin(session_org, session_user.organization_id == session_org.id)
            .where(LLMUsageRecord.created_at >= since)
            .group_by(org_id_expr, customer_name_expr, brand_name_expr)
            .order_by(desc(func.sum(LLMUsageRecord.estimated_cost_cache_aware)))
            .limit(item_limit)
        )
        if organization_id is not None:
            by_customer_brand_stmt = by_customer_brand_stmt.where(
                or_(
                    task_user.organization_id == organization_id,
                    session_user.organization_id == organization_id,
                )
            )
        by_customer_brand_rows = (await self.db.execute(by_customer_brand_stmt)).all()

        by_model_stmt = (
            select(
                LLMUsageRecord.provider,
                LLMUsageRecord.model_name,
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.total_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.cached_prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost_cache_aware), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.latency_ms), 0),
                func.coalesce(func.avg(LLMUsageRecord.latency_ms), 0.0),
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .where(LLMUsageRecord.created_at >= since)
            .group_by(LLMUsageRecord.provider, LLMUsageRecord.model_name)
            .order_by(desc(func.sum(LLMUsageRecord.estimated_cost_cache_aware)))
            .limit(item_limit)
        )
        if organization_id is not None:
            by_model_stmt = by_model_stmt.where(
                or_(
                    task_user.organization_id == organization_id,
                    session_user.organization_id == organization_id,
                )
            )
        by_model_rows = (await self.db.execute(by_model_stmt)).all()

        by_step_stmt = (
            select(
                LLMUsageRecord.step,
                LLMUsageRecord.step_name,
                func.count(LLMUsageRecord.id),
                func.coalesce(func.sum(LLMUsageRecord.total_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.cached_prompt_tokens), 0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.estimated_cost_cache_aware), 0.0),
                func.coalesce(func.sum(LLMUsageRecord.latency_ms), 0),
                func.coalesce(func.avg(LLMUsageRecord.latency_ms), 0.0),
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .where(LLMUsageRecord.created_at >= since)
            .group_by(LLMUsageRecord.step, LLMUsageRecord.step_name)
            .order_by(desc(func.sum(LLMUsageRecord.estimated_cost_cache_aware)))
            .limit(item_limit)
        )
        if organization_id is not None:
            by_step_stmt = by_step_stmt.where(
                or_(
                    task_user.organization_id == organization_id,
                    session_user.organization_id == organization_id,
                )
            )
        by_step_rows = (await self.db.execute(by_step_stmt)).all()

        recent_calls_stmt = (
            select(
                LLMUsageRecord,
                org_id_expr,
                customer_name_expr,
                brand_name_expr,
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .outerjoin(task_org, task_user.organization_id == task_org.id)
            .outerjoin(session_org, session_user.organization_id == session_org.id)
            .where(LLMUsageRecord.created_at >= since)
            .order_by(desc(LLMUsageRecord.created_at))
            .limit(item_limit)
        )
        if organization_id is not None:
            recent_calls_stmt = recent_calls_stmt.where(
                or_(
                    task_user.organization_id == organization_id,
                    session_user.organization_id == organization_id,
                )
            )
        recent_call_rows = (await self.db.execute(recent_calls_stmt)).all()

        def build_breakdown(
            *,
            call_count: int,
            total_tokens: int,
            prompt_tokens: int,
            cached_prompt_tokens: int,
            total_cost: float,
            total_cost_cache_aware: float,
            total_latency_ms: int,
            avg_latency_ms: float,
            **extra: object,
        ) -> dict[str, object]:
            estimated_savings = round(
                max(
                    float(total_cost or 0.0) - float(total_cost_cache_aware or 0.0), 0.0
                ),
                6,
            )
            return {
                **extra,
                "call_count": int(call_count or 0),
                "total_tokens": int(total_tokens or 0),
                "prompt_tokens": int(prompt_tokens or 0),
                "cached_prompt_tokens": int(cached_prompt_tokens or 0),
                "cache_hit_ratio": self._cache_hit_ratio(
                    int(prompt_tokens or 0), int(cached_prompt_tokens or 0)
                ),
                "total_cost": round(float(total_cost or 0.0), 6),
                "total_cost_cache_aware": round(
                    float(total_cost_cache_aware or 0.0), 6
                ),
                "estimated_savings": estimated_savings,
                "total_latency_ms": int(total_latency_ms or 0),
                "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
            }

        return {
            "summary": {
                "days": days,
                "call_count": int(total_calls or 0),
                "total_tokens": int(total_tokens or 0),
                "prompt_tokens": int(prompt_tokens or 0),
                "completion_tokens": int(completion_tokens or 0),
                "cached_prompt_tokens": int(cached_prompt_tokens or 0),
                "billable_prompt_tokens": int(billable_prompt_tokens or 0),
                "cache_hit_ratio": self._cache_hit_ratio(
                    int(prompt_tokens or 0), int(cached_prompt_tokens or 0)
                ),
                "total_cost": round(float(total_cost or 0.0), 6),
                "total_cost_cache_aware": round(
                    float(total_cost_cache_aware or 0.0), 6
                ),
                "estimated_savings": round(
                    max(
                        float(total_cost or 0.0) - float(total_cost_cache_aware or 0.0),
                        0.0,
                    ),
                    6,
                ),
                "total_latency_ms": int(total_latency_ms or 0),
                "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
                "unique_models": int(unique_models or 0),
                "first_call_at": first_call_at,
                "last_call_at": last_call_at,
            },
            "by_customer_brand": [
                build_breakdown(
                    organization_id=organization_uuid,
                    customer_name=customer_name,
                    brand_name=brand_name,
                    call_count=call_count,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    cached_prompt_tokens=cached_prompt_tokens,
                    total_cost=total_cost,
                    total_cost_cache_aware=total_cost_cache_aware,
                    total_latency_ms=total_latency_ms,
                    avg_latency_ms=avg_latency_ms,
                )
                for (
                    organization_uuid,
                    customer_name,
                    brand_name,
                    call_count,
                    total_tokens,
                    prompt_tokens,
                    cached_prompt_tokens,
                    total_cost,
                    total_cost_cache_aware,
                    total_latency_ms,
                    avg_latency_ms,
                ) in by_customer_brand_rows
            ],
            "by_model": [
                build_breakdown(
                    provider=provider,
                    model_name=model_name,
                    call_count=call_count,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    cached_prompt_tokens=cached_prompt_tokens,
                    total_cost=total_cost,
                    total_cost_cache_aware=total_cost_cache_aware,
                    total_latency_ms=total_latency_ms,
                    avg_latency_ms=avg_latency_ms,
                )
                for (
                    provider,
                    model_name,
                    call_count,
                    total_tokens,
                    prompt_tokens,
                    cached_prompt_tokens,
                    total_cost,
                    total_cost_cache_aware,
                    total_latency_ms,
                    avg_latency_ms,
                ) in by_model_rows
            ],
            "by_step": [
                build_breakdown(
                    step=step,
                    step_name=step_name,
                    call_count=call_count,
                    total_tokens=total_tokens,
                    prompt_tokens=prompt_tokens,
                    cached_prompt_tokens=cached_prompt_tokens,
                    total_cost=total_cost,
                    total_cost_cache_aware=total_cost_cache_aware,
                    total_latency_ms=total_latency_ms,
                    avg_latency_ms=avg_latency_ms,
                )
                for (
                    step,
                    step_name,
                    call_count,
                    total_tokens,
                    prompt_tokens,
                    cached_prompt_tokens,
                    total_cost,
                    total_cost_cache_aware,
                    total_latency_ms,
                    avg_latency_ms,
                ) in by_step_rows
            ],
            "recent_calls": [
                {
                    "id": record.id,
                    "task_id": record.task_id,
                    "session_id": record.session_id,
                    "organization_id": organization_uuid,
                    "customer_name": customer_name,
                    "brand_name": brand_name,
                    "provider": record.provider,
                    "model_name": record.model_name,
                    "step": record.step,
                    "step_name": record.step_name,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_tokens": record.total_tokens,
                    "cached_prompt_tokens": record.cached_prompt_tokens,
                    "billable_prompt_tokens": record.billable_prompt_tokens,
                    "cache_hit_ratio": self._cache_hit_ratio(
                        record.prompt_tokens, record.cached_prompt_tokens
                    ),
                    "latency_ms": record.latency_ms,
                    "estimated_cost": round(float(record.estimated_cost or 0.0), 6),
                    "estimated_cost_cache_aware": round(
                        float(record.estimated_cost_cache_aware or 0.0), 6
                    ),
                    "estimated_savings": round(
                        max(
                            float(record.estimated_cost or 0.0)
                            - float(record.estimated_cost_cache_aware or 0.0),
                            0.0,
                        ),
                        6,
                    ),
                    "created_at": record.created_at,
                }
                for record, organization_uuid, customer_name, brand_name in recent_call_rows
            ],
        }

    async def _build_usage_stats(
        self,
        *,
        org_ids: Sequence[UUID],
        days: int,
    ) -> dict[UUID, dict[str, object]]:
        if not org_ids:
            return {}
        since = self._since(days)
        result = await self.db.execute(
            select(
                User.organization_id,
                func.coalesce(func.sum(AnalysisTask.llm_total_tokens), 0),
                func.coalesce(func.sum(AnalysisTask.llm_estimated_cost), 0.0),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                AnalysisTask.status.in_(
                                    [TaskStatus.PENDING, TaskStatus.RUNNING]
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.max(AnalysisTask.updated_at),
            )
            .join(User, AnalysisTask.user_id == User.id)
            .where(
                User.organization_id.in_(org_ids),
                AnalysisTask.updated_at >= since,
            )
            .group_by(User.organization_id)
        )
        stats: dict[UUID, dict[str, object]] = {}
        for organization_id, tokens, cost, active_count, last_active_at in result.all():
            if organization_id is None:
                continue
            stats[organization_id] = {
                "tokens_7d": int(tokens or 0),
                "cost_7d": float(cost or 0.0),
                "active_task_count": int(active_count or 0),
                "last_active_at": last_active_at,
            }
        return stats

    async def _build_personal_brand_counts(
        self,
        *,
        org_ids: Sequence[UUID],
    ) -> dict[UUID, int]:
        if not org_ids:
            return {}
        result = await self.db.execute(
            select(User.organization_id, func.count(Entity.id))
            .join(User, Entity.owner_user_id == User.id)
            .where(
                User.organization_id.in_(org_ids),
                Entity.visibility_scope == EntityVisibilityScope.PERSONAL,
            )
            .group_by(User.organization_id)
        )
        counts: dict[UUID, int] = {}
        for organization_id, total in result.all():
            if organization_id is None:
                continue
            counts[organization_id] = int(total or 0)
        return counts
