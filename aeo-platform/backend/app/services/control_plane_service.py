from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.task import AnalysisTask, TaskStatus
from app.services.account_admin_service import AccountAdminService


class ControlPlaneService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.accounts = AccountAdminService(db)

    def _since(self, days: int) -> datetime:
        return datetime.now(timezone.utc) - timedelta(days=days)

    async def list_customers(self, *, days: int = 7) -> list[dict[str, object]]:
        organizations = await self.accounts.list_organizations()
        if not organizations:
            return []

        org_ids = [organization.id for organization in organizations]
        stats = await self._build_usage_stats(org_ids=org_ids, days=days)
        org_meta = self.accounts.build_organization_stats(organizations)

        rows: list[dict[str, object]] = []
        for organization in organizations:
            meta = org_meta.get(organization.id, {})
            usage = stats.get(organization.id, {})
            rows.append(
                {
                    "organization_id": organization.id,
                    "customer_name": organization.legal_name,
                    "primary_account": meta.get("primary_account"),
                    "member_count": int(meta.get("member_count", 0)),
                    "brand_count": int(meta.get("entity_count", 0)),
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
                "tokens_7d": 0,
                "cost_7d": 0.0,
                "active_task_count": 0,
                "last_active_at": None,
            }

        users = sorted(organization.users, key=lambda item: item.created_at)
        entities = sorted(
            organization.entities, key=lambda item: item.updated_at, reverse=True
        )
        tasks_result = await self.db.execute(
            select(AnalysisTask)
            .join(Entity, AnalysisTask.entity_id == Entity.id)
            .where(Entity.organization_id == organization_id)
            .order_by(AnalysisTask.updated_at.desc())
            .limit(recent_task_limit)
        )
        recent_tasks = list(tasks_result.scalars().all())

        return {
            "organization": organization,
            "summary": summary,
            "users": users,
            "entities": entities,
            "recent_tasks": recent_tasks,
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
                Entity.organization_id,
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
            .join(Entity, AnalysisTask.entity_id == Entity.id)
            .where(
                Entity.organization_id.in_(org_ids),
                AnalysisTask.updated_at >= since,
            )
            .group_by(Entity.organization_id)
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
