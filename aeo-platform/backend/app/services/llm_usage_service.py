"""LLM usage persistence and cost estimation helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm import BaseLLMModel, LLMUsage
from app.models.llm_usage import LLMUsageRecord
from app.models.session import Session as ChatSession
from app.models.task import AnalysisTask

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsageCostBreakdown:
    """Normalized token counters and estimated costs for one LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_prompt_tokens: int
    billable_prompt_tokens: int
    estimated_cost: float
    estimated_cost_cache_aware: float
    estimated_cost_savings: float


def _safe_uuid(value: str | None) -> UUID | None:
    if not value:
        return None
    try:
        return UUID(value)
    except (ValueError, TypeError):
        return None


def _resolve_model_metadata(model: BaseLLMModel) -> tuple[str, str]:
    config = getattr(model, "config", None)
    model_name = getattr(config, "model_name", None) or model.__class__.__name__
    provider = model.__class__.__name__.replace("Model", "").lower()
    return provider, str(model_name)


def _resolve_pricing(
    provider: str,
    model_name: str,
    prompt_tokens: int,
) -> tuple[float | None, float | None, float | None]:
    """Resolve standard and cache-hit pricing for a provider/model pair."""
    settings = get_settings()
    model_key = model_name.lower()
    long_context_threshold = max(
        int(getattr(settings, "GLM5_LONG_CONTEXT_THRESHOLD_TOKENS", 32000) or 32000),
        1,
    )
    is_long_context = prompt_tokens >= long_context_threshold

    input_price = None
    output_price = None
    cache_hit_factor = 1.0

    if provider == "glm5model" or provider == "glm5":
        if model_key.startswith("glm-5-turbo"):
            cache_hit_factor = float(
                getattr(settings, "GLM5_TURBO_CACHE_HIT_PRICE_FACTOR", 0.5) or 0.5
            )
            if is_long_context:
                input_price = settings.GLM5_TURBO_PRICE_LONG_INPUT_PER_MTOKENS
                output_price = settings.GLM5_TURBO_PRICE_LONG_OUTPUT_PER_MTOKENS
            else:
                input_price = settings.GLM5_TURBO_PRICE_INPUT_PER_MTOKENS
                output_price = settings.GLM5_TURBO_PRICE_OUTPUT_PER_MTOKENS
        elif model_key.startswith("glm-5"):
            cache_hit_factor = float(
                getattr(settings, "GLM5_CACHE_HIT_PRICE_FACTOR", 0.5) or 0.5
            )
            if is_long_context:
                input_price = settings.GLM5_PRICE_LONG_INPUT_PER_MTOKENS
                output_price = settings.GLM5_PRICE_LONG_OUTPUT_PER_MTOKENS
            else:
                input_price = settings.GLM5_PRICE_INPUT_PER_MTOKENS
                output_price = settings.GLM5_PRICE_OUTPUT_PER_MTOKENS
    elif provider == "minimaxmodel" or provider == "minimax":
        input_price = settings.MINIMAX_PRICE_INPUT_PER_MTOKENS
        output_price = settings.MINIMAX_PRICE_OUTPUT_PER_MTOKENS
        cache_hit_factor = float(
            getattr(settings, "MINIMAX_CACHE_HIT_PRICE_FACTOR", 1.0) or 1.0
        )

    if input_price is None or output_price is None:
        return None, None, None

    cached_input_price = input_price * max(cache_hit_factor, 0.0)
    return input_price, output_price, cached_input_price


def estimate_usage_costs(
    provider: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_prompt_tokens: int = 0,
) -> UsageCostBreakdown:
    """Estimate both legacy and cache-aware costs for one usage event."""
    normalized_prompt_tokens = max(int(prompt_tokens or 0), 0)
    normalized_completion_tokens = max(int(completion_tokens or 0), 0)
    normalized_total_tokens = normalized_prompt_tokens + normalized_completion_tokens
    normalized_cached_prompt_tokens = min(
        max(int(cached_prompt_tokens or 0), 0),
        normalized_prompt_tokens,
    )
    billable_prompt_tokens = normalized_prompt_tokens - normalized_cached_prompt_tokens

    input_price, output_price, cached_input_price = _resolve_pricing(
        provider=provider,
        model_name=model_name,
        prompt_tokens=normalized_prompt_tokens,
    )
    if input_price is None or output_price is None or cached_input_price is None:
        return UsageCostBreakdown(
            prompt_tokens=normalized_prompt_tokens,
            completion_tokens=normalized_completion_tokens,
            total_tokens=normalized_total_tokens,
            cached_prompt_tokens=normalized_cached_prompt_tokens,
            billable_prompt_tokens=billable_prompt_tokens,
            estimated_cost=0.0,
            estimated_cost_cache_aware=0.0,
            estimated_cost_savings=0.0,
        )

    estimated_cost = round(
        (normalized_prompt_tokens / 1_000_000.0) * input_price
        + (normalized_completion_tokens / 1_000_000.0) * output_price,
        6,
    )
    estimated_cost_cache_aware = round(
        (billable_prompt_tokens / 1_000_000.0) * input_price
        + (normalized_cached_prompt_tokens / 1_000_000.0) * cached_input_price
        + (normalized_completion_tokens / 1_000_000.0) * output_price,
        6,
    )
    estimated_cost_savings = round(
        max(estimated_cost - estimated_cost_cache_aware, 0.0),
        6,
    )

    return UsageCostBreakdown(
        prompt_tokens=normalized_prompt_tokens,
        completion_tokens=normalized_completion_tokens,
        total_tokens=normalized_total_tokens,
        cached_prompt_tokens=normalized_cached_prompt_tokens,
        billable_prompt_tokens=billable_prompt_tokens,
        estimated_cost=estimated_cost,
        estimated_cost_cache_aware=estimated_cost_cache_aware,
        estimated_cost_savings=estimated_cost_savings,
    )


def estimate_usage_cost(
    provider: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Backward-compatible legacy cost estimate without cache discount."""
    return estimate_usage_costs(
        provider=provider,
        model_name=model_name,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    ).estimated_cost


def _cache_hit_ratio(prompt_tokens: int, cached_prompt_tokens: int) -> float:
    if prompt_tokens <= 0:
        return 0.0
    return round(cached_prompt_tokens / prompt_tokens, 4)


class LLMUsageService:
    """Persists per-call usage records and updates task aggregates."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _build_scope_conditions(
        *,
        user_id: UUID,
        entity_id: UUID | None = None,
        since: datetime | None = None,
    ) -> list[Any]:
        conditions: list[Any] = [
            or_(
                AnalysisTask.user_id == user_id,
                ChatSession.user_id == user_id,
            )
        ]
        if since is not None:
            conditions.append(LLMUsageRecord.created_at >= since)
        if entity_id is not None:
            conditions.append(
                func.coalesce(AnalysisTask.entity_id, ChatSession.entity_id)
                == entity_id
            )
        return conditions

    async def record_usage(
        self,
        *,
        session_id: str | None,
        task_id: str | None,
        skill_key: str | None,
        step: str | None,
        step_name: str | None,
        model: BaseLLMModel,
        usage: LLMUsage,
        latency_ms: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
    ) -> LLMUsageRecord:
        provider, model_name = _resolve_model_metadata(model)
        cost_breakdown = estimate_usage_costs(
            provider=provider,
            model_name=model_name,
            prompt_tokens=int(usage.prompt_tokens or 0),
            completion_tokens=int(usage.completion_tokens or 0),
            cached_prompt_tokens=int(usage.cached_prompt_tokens or 0),
        )
        prompt_tokens = cost_breakdown.prompt_tokens
        completion_tokens = cost_breakdown.completion_tokens
        total_tokens = int(usage.total_tokens or cost_breakdown.total_tokens)
        cached_prompt_tokens = min(cost_breakdown.cached_prompt_tokens, prompt_tokens)
        billable_prompt_tokens = min(
            cost_breakdown.billable_prompt_tokens,
            prompt_tokens,
        )
        normalized_latency_ms = max(int(latency_ms or 0), 0)
        estimated_cost = cost_breakdown.estimated_cost
        estimated_cost_cache_aware = cost_breakdown.estimated_cost_cache_aware

        session_uuid = _safe_uuid(session_id)
        task_uuid = _safe_uuid(task_id)

        normalized_extra_metadata = dict(extra_metadata or {})
        if usage.prompt_tokens_details:
            normalized_extra_metadata.setdefault(
                "prompt_tokens_details",
                usage.prompt_tokens_details,
            )
        if usage.raw:
            normalized_extra_metadata.setdefault("provider_usage", usage.raw)

        async with self.db.begin_nested():
            record = LLMUsageRecord(
                session_id=session_uuid,
                task_id=task_uuid,
                provider=provider,
                model_name=model_name,
                skill_key=skill_key,
                step=step,
                step_name=step_name,
                raw_session_id=session_id if session_uuid is None else None,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cached_prompt_tokens=cached_prompt_tokens,
                billable_prompt_tokens=billable_prompt_tokens,
                latency_ms=normalized_latency_ms,
                estimated_cost=estimated_cost,
                estimated_cost_cache_aware=estimated_cost_cache_aware,
                extra_metadata=normalized_extra_metadata or None,
            )
            self.db.add(record)

            if task_uuid is not None:
                task_stmt = (
                    select(AnalysisTask)
                    .where(AnalysisTask.id == task_uuid)
                    .with_for_update()
                )
                task_result = await self.db.execute(task_stmt)
                task = task_result.scalar_one_or_none()
                if task is not None:
                    task.llm_call_count += 1
                    task.llm_prompt_tokens += prompt_tokens
                    task.llm_completion_tokens += completion_tokens
                    task.llm_total_tokens += total_tokens
                    task.llm_cached_prompt_tokens += cached_prompt_tokens
                    task.llm_billable_prompt_tokens += billable_prompt_tokens
                    task.llm_total_latency_ms += normalized_latency_ms
                    task.llm_estimated_cost = round(
                        float(task.llm_estimated_cost or 0.0) + estimated_cost,
                        6,
                    )
                    task.llm_estimated_cost_cache_aware = round(
                        float(task.llm_estimated_cost_cache_aware or 0.0)
                        + estimated_cost_cache_aware,
                        6,
                    )

            await self.db.flush()

        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def get_observability_snapshot(
        self,
        *,
        user_id: UUID,
        entity_id: UUID | None = None,
        days: int = 30,
        limit: int = 20,
    ) -> dict[str, Any]:
        window_days = max(days, 1)
        item_limit = min(max(limit, 1), 100)
        since = datetime.now(timezone.utc) - timedelta(days=window_days)
        conditions = self._build_scope_conditions(
            user_id=user_id,
            entity_id=entity_id,
            since=since,
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
                func.max(LLMUsageRecord.created_at),
                func.min(LLMUsageRecord.created_at),
            )
            .select_from(LLMUsageRecord)
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .where(*conditions)
        )
        summary_row = (await self.db.execute(summary_stmt)).one()
        total_calls = int(summary_row[0] or 0)
        total_tokens = int(summary_row[1] or 0)
        total_prompt_tokens = int(summary_row[2] or 0)
        total_completion_tokens = int(summary_row[3] or 0)
        total_cached_prompt_tokens = int(summary_row[4] or 0)
        total_billable_prompt_tokens = int(summary_row[5] or 0)
        total_cost = round(float(summary_row[6] or 0.0), 6)
        total_cost_cache_aware = round(float(summary_row[7] or 0.0), 6)
        total_latency_ms = int(summary_row[8] or 0)
        avg_latency_ms = round(float(summary_row[9] or 0.0), 2)
        unique_models = int(summary_row[10] or 0)
        last_call_at = summary_row[11]
        first_call_at = summary_row[12]
        cache_hit_ratio = _cache_hit_ratio(
            total_prompt_tokens,
            total_cached_prompt_tokens,
        )
        estimated_savings = round(
            max(total_cost - total_cost_cache_aware, 0.0),
            6,
        )

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
            .where(*conditions)
            .group_by(LLMUsageRecord.provider, LLMUsageRecord.model_name)
            .order_by(
                desc(func.count(LLMUsageRecord.id)),
                desc(func.sum(LLMUsageRecord.total_tokens)),
            )
            .limit(5)
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
            .where(*conditions)
            .group_by(LLMUsageRecord.step, LLMUsageRecord.step_name)
            .order_by(
                desc(func.count(LLMUsageRecord.id)),
                desc(func.sum(LLMUsageRecord.total_tokens)),
            )
            .limit(6)
        )
        by_step_rows = (await self.db.execute(by_step_stmt)).all()

        by_skill_stmt = (
            select(
                LLMUsageRecord.skill_key,
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
            .where(*conditions)
            .where(LLMUsageRecord.skill_key.is_not(None))
            .group_by(LLMUsageRecord.skill_key)
            .order_by(
                desc(func.count(LLMUsageRecord.id)),
                desc(func.sum(LLMUsageRecord.total_tokens)),
            )
            .limit(6)
        )
        by_skill_rows = (await self.db.execute(by_skill_stmt)).all()

        recent_stmt = (
            select(
                LLMUsageRecord,
                AnalysisTask.brand_name,
                ChatSession.title,
            )
            .outerjoin(AnalysisTask, LLMUsageRecord.task_id == AnalysisTask.id)
            .outerjoin(ChatSession, LLMUsageRecord.session_id == ChatSession.id)
            .where(*conditions)
            .order_by(desc(LLMUsageRecord.created_at))
            .limit(item_limit)
        )
        recent_rows = (await self.db.execute(recent_stmt)).all()

        return {
            "summary": {
                "days": window_days,
                "entity_id": str(entity_id) if entity_id else None,
                "call_count": total_calls,
                "total_tokens": total_tokens,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "cached_prompt_tokens": total_cached_prompt_tokens,
                "billable_prompt_tokens": total_billable_prompt_tokens,
                "cache_hit_ratio": cache_hit_ratio,
                "total_cost": total_cost,
                "total_cost_cache_aware": total_cost_cache_aware,
                "estimated_savings": estimated_savings,
                "total_latency_ms": total_latency_ms,
                "avg_latency_ms": avg_latency_ms,
                "unique_models": unique_models,
                "first_call_at": first_call_at.isoformat() if first_call_at else None,
                "last_call_at": last_call_at.isoformat() if last_call_at else None,
            },
            "by_model": [
                {
                    "provider": provider,
                    "model_name": model_name,
                    "call_count": int(call_count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "prompt_tokens": int(prompt_tokens or 0),
                    "cached_prompt_tokens": int(cached_prompt_tokens or 0),
                    "cache_hit_ratio": _cache_hit_ratio(
                        int(prompt_tokens or 0),
                        int(cached_prompt_tokens or 0),
                    ),
                    "total_cost": round(float(total_cost or 0.0), 6),
                    "total_cost_cache_aware": round(
                        float(total_cost_cache_aware or 0.0),
                        6,
                    ),
                    "estimated_savings": round(
                        max(
                            float(total_cost or 0.0)
                            - float(total_cost_cache_aware or 0.0),
                            0.0,
                        ),
                        6,
                    ),
                    "total_latency_ms": int(total_latency_ms or 0),
                    "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
                }
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
                {
                    "step": step,
                    "step_name": step_name,
                    "call_count": int(call_count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "prompt_tokens": int(prompt_tokens or 0),
                    "cached_prompt_tokens": int(cached_prompt_tokens or 0),
                    "cache_hit_ratio": _cache_hit_ratio(
                        int(prompt_tokens or 0),
                        int(cached_prompt_tokens or 0),
                    ),
                    "total_cost": round(float(total_cost or 0.0), 6),
                    "total_cost_cache_aware": round(
                        float(total_cost_cache_aware or 0.0),
                        6,
                    ),
                    "estimated_savings": round(
                        max(
                            float(total_cost or 0.0)
                            - float(total_cost_cache_aware or 0.0),
                            0.0,
                        ),
                        6,
                    ),
                    "total_latency_ms": int(total_latency_ms or 0),
                    "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
                }
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
            "by_skill": [
                {
                    "skill_key": skill_key,
                    "call_count": int(call_count or 0),
                    "total_tokens": int(total_tokens or 0),
                    "prompt_tokens": int(prompt_tokens or 0),
                    "cached_prompt_tokens": int(cached_prompt_tokens or 0),
                    "cache_hit_ratio": _cache_hit_ratio(
                        int(prompt_tokens or 0),
                        int(cached_prompt_tokens or 0),
                    ),
                    "total_cost": round(float(total_cost or 0.0), 6),
                    "total_cost_cache_aware": round(
                        float(total_cost_cache_aware or 0.0),
                        6,
                    ),
                    "estimated_savings": round(
                        max(
                            float(total_cost or 0.0)
                            - float(total_cost_cache_aware or 0.0),
                            0.0,
                        ),
                        6,
                    ),
                    "total_latency_ms": int(total_latency_ms or 0),
                    "avg_latency_ms": round(float(avg_latency_ms or 0.0), 2),
                }
                for (
                    skill_key,
                    call_count,
                    total_tokens,
                    prompt_tokens,
                    cached_prompt_tokens,
                    total_cost,
                    total_cost_cache_aware,
                    total_latency_ms,
                    avg_latency_ms,
                ) in by_skill_rows
            ],
            "recent_calls": [
                {
                    "id": str(record.id),
                    "task_id": str(record.task_id) if record.task_id else None,
                    "session_id": str(record.session_id) if record.session_id else None,
                    "brand_name": brand_name or session_title or "未关联任务",
                    "provider": record.provider,
                    "model_name": record.model_name,
                    "skill_key": record.skill_key,
                    "step": record.step,
                    "step_name": record.step_name,
                    "prompt_tokens": record.prompt_tokens,
                    "completion_tokens": record.completion_tokens,
                    "total_tokens": record.total_tokens,
                    "cached_prompt_tokens": record.cached_prompt_tokens,
                    "billable_prompt_tokens": record.billable_prompt_tokens,
                    "cache_hit_ratio": _cache_hit_ratio(
                        record.prompt_tokens,
                        record.cached_prompt_tokens,
                    ),
                    "latency_ms": record.latency_ms,
                    "estimated_cost": record.estimated_cost,
                    "estimated_cost_cache_aware": record.estimated_cost_cache_aware,
                    "estimated_savings": round(
                        max(
                            float(record.estimated_cost or 0.0)
                            - float(record.estimated_cost_cache_aware or 0.0),
                            0.0,
                        ),
                        6,
                    ),
                    "created_at": (
                        record.created_at.isoformat() if record.created_at else None
                    ),
                }
                for record, brand_name, session_title in recent_rows
            ],
        }


async def record_llm_usage_async(
    *,
    session_id: str | None,
    task_id: str | None,
    skill_key: str | None,
    step: str | None,
    step_name: str | None,
    model: BaseLLMModel,
    usage: LLMUsage | None,
    latency_ms: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Persist token/cost/latency metrics when the provider produced them."""
    normalized_usage = usage or LLMUsage()
    has_any_counter = any(
        value is not None
        for value in (
            normalized_usage.prompt_tokens,
            normalized_usage.completion_tokens,
            normalized_usage.total_tokens,
        )
    )
    if not has_any_counter and latency_ms is None:
        return

    try:
        async with AsyncSessionLocal() as db:
            service = LLMUsageService(db)
            await service.record_usage(
                session_id=session_id,
                task_id=task_id,
                skill_key=skill_key,
                step=step,
                step_name=step_name,
                model=model,
                usage=normalized_usage,
                latency_ms=latency_ms,
                extra_metadata=extra_metadata,
            )
    except Exception as exc:
        logger.warning("[LLMUsage] Failed to persist usage: %s", exc)
