from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.config import get_settings
from app.models.entity import Entity, EntityVisibilityScope
from app.models.llm_usage import LLMUsageRecord
from app.models.organization import Organization
from app.models.session import Session as ChatSession
from app.models.task import AnalysisTask, TaskStatus
from app.models.user import User
from app.services.account_admin_service import AccountAdminService
from app.services.usage_billing_summary import billing_details, cache_status_for_record, summarize_billing, summarize_usage, grouped_usage


class ControlPlaneService:
    LOW_CACHE_HIT_RATIO_THRESHOLD = 0.2
    RUNTIME_CONTEXT_SIZE_BUDGET = 12000
    DIAGNOSTIC_SAMPLE_LIMIT = 5000

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

    @staticmethod
    def _reporting_currency() -> str:
        return str(
            getattr(get_settings(), "LLM_COST_REPORTING_CURRENCY", "CNY") or "CNY"
        ).upper()

    @staticmethod
    def _metadata(record: LLMUsageRecord) -> dict[str, object]:
        return record.extra_metadata if isinstance(record.extra_metadata, dict) else {}

    @staticmethod
    def _metadata_int(metadata: dict[str, object], key: str) -> int | None:
        value = metadata.get(key)
        if value is None:
            return None
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _reuse_diagnosis_for_record(cls, record: LLMUsageRecord) -> str | None:
        metadata = cls._metadata(record)
        cache_hit_ratio = cls._cache_hit_ratio(
            record.prompt_tokens,
            record.cached_prompt_tokens,
        )
        runtime_context_size = cls._metadata_int(metadata, "runtime_context_size")
        if cache_status_for_record(record) == "known" and record.prompt_tokens > 0 and cache_hit_ratio < cls.LOW_CACHE_HIT_RATIO_THRESHOLD:
            return "复用率低"
        if runtime_context_size is not None and (
            runtime_context_size > cls.RUNTIME_CONTEXT_SIZE_BUDGET
        ):
            return "动态上下文偏大"
        if not metadata.get("static_prompt_hash") or not metadata.get(
            "tool_surface_hash"
        ):
            return "缺少提示词指纹"
        return None

    @classmethod
    def _build_reuse_diagnostics(
        cls,
        records: Sequence[LLMUsageRecord],
    ) -> tuple[dict[str, object], list[dict[str, object]]]:
        sample_count = len(records)
        static_prompt_hashes: set[str] = set()
        tool_surface_hashes: set[str] = set()
        model_identities: set[str] = set()
        runtime_context_sizes: list[int] = []
        low_cache_call_count = 0
        missing_fingerprint_count = 0
        oversized_runtime_context_count = 0

        if sample_count == 0:
            return (
                {
                    "diagnostic_sample_count": 0,
                    "low_cache_call_count": 0,
                    "low_cache_call_ratio": 0.0,
                    "static_prompt_variant_count": 0,
                    "tool_surface_variant_count": 0,
                    "model_identity_variant_count": 0,
                    "avg_runtime_context_size": 0,
                    "max_runtime_context_size": 0,
                },
                [],
            )

        for record in records:
            metadata = cls._metadata(record)
            static_prompt_hash = metadata.get("static_prompt_hash")
            tool_surface_hash = metadata.get("tool_surface_hash")
            model_identity = metadata.get("model_identity")
            runtime_context_size = cls._metadata_int(metadata, "runtime_context_size")
            if isinstance(static_prompt_hash, str) and static_prompt_hash:
                static_prompt_hashes.add(static_prompt_hash)
            if isinstance(tool_surface_hash, str) and tool_surface_hash:
                tool_surface_hashes.add(tool_surface_hash)
            if isinstance(model_identity, str) and model_identity:
                model_identities.add(model_identity)
            else:
                model_identities.add(f"{record.provider}:{record.model_name}")
            if runtime_context_size is not None:
                runtime_context_sizes.append(runtime_context_size)
                if runtime_context_size > cls.RUNTIME_CONTEXT_SIZE_BUDGET:
                    oversized_runtime_context_count += 1
            if not static_prompt_hash or not tool_surface_hash:
                missing_fingerprint_count += 1
            if cache_status_for_record(record) == "known" and record.prompt_tokens > 0 and (
                cls._cache_hit_ratio(record.prompt_tokens, record.cached_prompt_tokens)
                < cls.LOW_CACHE_HIT_RATIO_THRESHOLD
            ):
                low_cache_call_count += 1

        low_cache_ratio = (
            round(low_cache_call_count / sample_count, 4) if sample_count > 0 else 0.0
        )
        missing_fingerprint_ratio = (
            round(missing_fingerprint_count / sample_count, 4)
            if sample_count > 0
            else 0.0
        )
        avg_runtime_context_size = (
            round(sum(runtime_context_sizes) / len(runtime_context_sizes))
            if runtime_context_sizes
            else 0
        )
        max_runtime_context_size = max(runtime_context_sizes, default=0)

        diagnostics: list[dict[str, object]] = []
        if low_cache_call_count > 0:
            severity = "critical" if low_cache_ratio >= 0.5 else "warning"
            diagnostics.append(
                {
                    "severity": severity,
                    "code": "low_cache_hit_ratio",
                    "title": "提示词复用率偏低",
                    "message": (
                        "最近调用中有较多请求没有命中缓存，优先检查固定提示词、"
                        "工具清单和模型身份是否在频繁变化。"
                    ),
                    "affected_count": low_cache_call_count,
                    "ratio": low_cache_ratio,
                }
            )
        if len(static_prompt_hashes) > 1:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "static_prompt_hash_changed",
                    "title": "固定提示词指纹出现多个版本",
                    "message": "同一窗口内固定提示词 hash 不止一个，需要确认是否为预期发布或 flag 变化。",
                    "affected_count": len(static_prompt_hashes),
                    "ratio": None,
                }
            )
        if len(tool_surface_hashes) > 1:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "tool_surface_hash_changed",
                    "title": "工具清单指纹出现多个版本",
                    "message": "工具面仍在变化，可能来自 feature flag、skill 注册或状态相关工具过滤。",
                    "affected_count": len(tool_surface_hashes),
                    "ratio": None,
                }
            )
        if oversized_runtime_context_count > 0:
            diagnostics.append(
                {
                    "severity": "warning",
                    "code": "runtime_context_oversized",
                    "title": "动态上下文偏大",
                    "message": "本轮提醒或运行时上下文过长，会增加输入 token，也可能稀释可复用比例。",
                    "affected_count": oversized_runtime_context_count,
                    "ratio": round(oversized_runtime_context_count / sample_count, 4)
                    if sample_count > 0
                    else 0.0,
                }
            )
        if missing_fingerprint_count > 0:
            severity = "warning" if missing_fingerprint_ratio >= 0.3 else "info"
            diagnostics.append(
                {
                    "severity": severity,
                    "code": "prompt_fingerprint_missing",
                    "title": "部分调用缺少提示词指纹",
                    "message": "这些调用可能不是 orchestrator，或发生在观测字段上线前，低复用原因无法完全解释。",
                    "affected_count": missing_fingerprint_count,
                    "ratio": missing_fingerprint_ratio,
                }
            )
        if not diagnostics:
            diagnostics.append(
                {
                    "severity": "info",
                    "code": "reuse_signal_stable",
                    "title": "未发现明显复用异常",
                    "message": "当前窗口内固定提示词、工具清单和动态上下文没有明显异常信号。",
                    "affected_count": 0,
                    "ratio": None,
                }
            )

        return (
            {
                "diagnostic_sample_count": sample_count,
                "low_cache_call_count": low_cache_call_count,
                "low_cache_call_ratio": low_cache_ratio,
                "static_prompt_variant_count": len(static_prompt_hashes),
                "tool_surface_variant_count": len(tool_surface_hashes),
                "model_identity_variant_count": len(model_identities),
                "avg_runtime_context_size": avg_runtime_context_size,
                "max_runtime_context_size": max_runtime_context_size,
            },
            diagnostics,
        )

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
                    "cost_7d": usage.get("cost_7d"),
                    **{key: usage.get(key) for key in ("currency", "costs_by_currency", "priced_call_count", "unknown_pricing_call_count", "pricing_coverage")},
                    "active_task_count": int(usage.get("active_task_count", 0)),
                    "last_active_at": usage.get("last_active_at"),
                }
            )
        rows.sort(
            key=lambda item: (
                item["last_active_at"] or datetime.fromtimestamp(0, tz=timezone.utc),
                item["cost_7d"] or 0.0,
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
                "cost_7d": None,
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

    async def get_task_billing(self, task_ids: Sequence[UUID]) -> dict[UUID, dict]:
        if not task_ids:
            return {}
        result = await self.db.execute(
            select(LLMUsageRecord).where(LLMUsageRecord.task_id.in_(task_ids))
        )
        records = list(result.scalars().all())
        return {
            task_id: summarize_billing([r for r in records if r.task_id == task_id])
            for task_id in task_ids
        }

    def _usage_rows_statement(self, since: datetime):
        task_user = aliased(User)
        session_user = aliased(User)
        organization = aliased(Organization)
        # One task and one session per ledger row. Task attribution wins consistently.
        org_id = func.coalesce(task_user.organization_id, session_user.organization_id)
        stmt = (
            select(LLMUsageRecord, org_id, organization.legal_name,
                   func.coalesce(AnalysisTask.brand_name, ChatSession.title, "Unlinked"))
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .outerjoin(task_user, AnalysisTask.user_id == task_user.id)
            .outerjoin(session_user, ChatSession.user_id == session_user.id)
            .outerjoin(organization, org_id == organization.id)
            .where(LLMUsageRecord.created_at >= since)
            .order_by(LLMUsageRecord.created_at.desc(), LLMUsageRecord.id.desc())
        )
        return stmt, org_id

    async def get_observability_snapshot(
        self, *, days: int = 30, organization_id: UUID | None = None,
        limit: int = 12,
    ) -> dict[str, object]:
        stmt, org_id = self._usage_rows_statement(self._since(days))
        if organization_id is not None:
            stmt = stmt.where(org_id == organization_id)
        rows = list((await self.db.execute(stmt)).all())
        records = [row[0] for row in rows]
        reuse_summary, diagnostics = self._build_reuse_diagnostics(
            records[:self.DIAGNOSTIC_SAMPLE_LIMIT]
        )
        item_limit = min(max(limit, 1), 50)
        recent = []
        for record, organization_uuid, customer_name, brand_name in rows[:item_limit]:
            metadata = self._metadata(record)
            recent.append({
                **{field: getattr(record, field) for field in (
                    "id", "task_id", "session_id", "provider", "model_name",
                    "step", "step_name", "prompt_tokens", "completion_tokens",
                    "total_tokens", "cached_prompt_tokens", "billable_prompt_tokens",
                    "latency_ms", "created_at",
                )},
                "organization_id": organization_uuid,
                "customer_name": customer_name,
                "brand_name": brand_name,
                **{field: metadata.get(field) for field in (
                    "static_prompt_hash", "tool_surface_hash", "model_identity",
                    "runtime_context_size", "runtime_reminder_enabled",
                    "stable_tool_surface_enabled", "stable_skill_tool_description_enabled",
                )},
                "reuse_diagnosis": self._reuse_diagnosis_for_record(record),
                **billing_details(record),
            })
        model_rows = [(r, r.provider, r.model_name) for r in records]
        step_rows = [(r, r.step, r.step_name) for r in records]
        return {
            "summary": {
                "days": days, **summarize_usage(records), **reuse_summary,
                "unique_models": len({(r.provider, r.model_name) for r in records}),
                "first_call_at": records[-1].created_at if records else None,
                "last_call_at": records[0].created_at if records else None,
            },
            "reuse_diagnostics": diagnostics,
            "by_customer_brand": grouped_usage(rows, (1, 2, 3), ("organization_id", "customer_name", "brand_name")),
            "by_model": grouped_usage(model_rows, (1, 2), ("provider", "model_name")),
            "by_step": grouped_usage(step_rows, (1, 2), ("step", "step_name")),
            "recent_calls": recent,
        }

    async def _build_usage_stats(
        self, *, org_ids: Sequence[UUID], days: int,
    ) -> dict[UUID, dict[str, object]]:
        if not org_ids:
            return {}
        since = self._since(days)
        stmt, org_id = self._usage_rows_statement(since)
        rows = list((await self.db.execute(stmt.where(org_id.in_(org_ids)))).all())
        stats = {}
        for organization_id in org_ids:
            records = [row[0] for row in rows if row[1] == organization_id]
            billing = summarize_billing(records)
            stats[organization_id] = {
                "tokens_7d": sum(r.total_tokens for r in records),
                "cost_7d": billing["total_cost_cache_aware"],
                **billing,
                "active_task_count": 0,
                "last_active_at": records[0].created_at if records else None,
            }
        # Task status is separate from usage accounting and cannot multiply ledger rows.
        active = await self.db.execute(
            select(User.organization_id, func.count(AnalysisTask.id))
            .select_from(AnalysisTask).join(User, AnalysisTask.user_id == User.id)
            .where(User.organization_id.in_(org_ids),
                   AnalysisTask.status.in_([TaskStatus.PENDING, TaskStatus.RUNNING]))
            .group_by(User.organization_id)
        )
        for organization_id, count in active.all():
            stats[organization_id]["active_task_count"] = int(count)
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
