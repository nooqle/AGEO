"""LLM usage persistence and cost estimation helpers."""

from __future__ import annotations

import logging
import math
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
from app.services.deepseek_pricing import resolve_deepseek_tariff

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UsagePricingSnapshot:
    """Pricing inputs used to estimate one LLM call."""

    provider: str
    model_name: str
    pricing_model: str
    input_cache_miss_price_per_mtokens: float
    input_cache_hit_price_per_mtokens: float
    output_price_per_mtokens: float
    pricing_currency: str
    reporting_currency: str
    source: str
    source_url: str | None = None
    rate_version: str | None = None
    tariff_period: str | None = None
    priced_at: str | None = None
    pricing_timezone: str | None = None

    def to_metadata(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model_name": self.model_name,
            "pricing_model": self.pricing_model,
            "input_cache_miss_price_per_mtokens": (
                self.input_cache_miss_price_per_mtokens
            ),
            "input_cache_hit_price_per_mtokens": self.input_cache_hit_price_per_mtokens,
            "output_price_per_mtokens": self.output_price_per_mtokens,
            "pricing_currency": self.pricing_currency,
            "reporting_currency": self.reporting_currency,
            "source": self.source,
            "source_url": self.source_url,
            "rate_version": self.rate_version or self.source,
            "tariff_period": self.tariff_period,
            "priced_at": self.priced_at,
            "pricing_timezone": self.pricing_timezone,
        }


@dataclass(frozen=True)
class UsageCostBreakdown:
    """Normalized token counters and estimated costs for one LLM call."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_prompt_tokens: int
    billable_prompt_tokens: int
    estimated_cost: float | None
    estimated_cost_cache_aware: float | None
    estimated_cost_savings: float | None
    currency: str
    pricing_snapshot: UsagePricingSnapshot | None
    pricing_status: str = "priced"
    cache_status: str = "known"


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


def resolve_llm_model_identity(model: BaseLLMModel) -> str:
    provider, model_name = _resolve_model_metadata(model)
    return f"{provider}:{model_name}"


def _resolve_pricing(
    provider: str,
    model_name: str,
    prompt_tokens: int,
    occurred_at: datetime | None = None,
) -> UsagePricingSnapshot | None:
    """Resolve standard and cache-hit pricing for a provider/model pair."""
    settings = get_settings()
    model_key = model_name.lower()
    reporting_currency = str(
        getattr(settings, "LLM_COST_REPORTING_CURRENCY", "CNY") or "CNY"
    ).upper()
    long_context_threshold = max(
        int(getattr(settings, "GLM5_LONG_CONTEXT_THRESHOLD_TOKENS", 32000) or 32000),
        1,
    )
    is_long_context = prompt_tokens >= long_context_threshold

    input_price = None
    output_price = None
    cache_hit_factor = 1.0
    cached_input_price = None
    pricing_model = model_name
    pricing_currency = reporting_currency
    source = "configured_provider_pricing"
    source_url = None

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
    elif provider in {"deepseekmodel", "deepseek"}:
        tariff = resolve_deepseek_tariff(
            model_name, occurred_at or datetime.now(timezone.utc)
        )
        return UsagePricingSnapshot(provider=provider, model_name=model_name, **tariff) if tariff else None
    elif provider == "doubao":
        pricing_currency = "CNY"
        source = "volcengine_doubao_official_pricing_2026_07_16"
        source_url = "https://www.volcengine.com/product/doubao/"
        if "doubao-seed-2-0-mini" in model_key:
            pricing_model = "doubao-seed-2.0-mini"
            input_price = settings.DOUBAO_MINI_PRICE_INPUT_CACHE_MISS_PER_MTOKENS
            cached_input_price = settings.DOUBAO_MINI_PRICE_INPUT_CACHE_HIT_PER_MTOKENS
            output_price = settings.DOUBAO_MINI_PRICE_OUTPUT_PER_MTOKENS
        elif "doubao-seed-2-0-lite" in model_key:
            pricing_model = "doubao-seed-2.0-lite"
            input_price = settings.DOUBAO_LITE_PRICE_INPUT_CACHE_MISS_PER_MTOKENS
            cached_input_price = settings.DOUBAO_LITE_PRICE_INPUT_CACHE_HIT_PER_MTOKENS
            output_price = settings.DOUBAO_LITE_PRICE_OUTPUT_PER_MTOKENS
    elif provider == "hunyuan" and "hunyuan-2.0-instruct" in model_key:
        pricing_currency = "CNY"
        pricing_model = "hunyuan-2.0-instruct"
        source = "tencent_hunyuan_official_pricing_2026_03_13"
        source_url = "https://cloud.tencent.com/announce/detail/2227"
        input_price = settings.HUNYUAN_2_INSTRUCT_PRICE_INPUT_PER_MTOKENS
        output_price = settings.HUNYUAN_2_INSTRUCT_PRICE_OUTPUT_PER_MTOKENS
    elif provider == "moonshot" and model_key.startswith("kimi-k2.5"):
        pricing_currency = "CNY"
        pricing_model = "kimi-k2.5"
        source = "kimi_k2_5_official_pricing_2026_07_16"
        source_url = "https://platform.kimi.com/docs/pricing/chat-k25"
        input_price = settings.MOONSHOT_PRICE_INPUT_CACHE_MISS_PER_MTOKENS
        cached_input_price = settings.MOONSHOT_PRICE_INPUT_CACHE_HIT_PER_MTOKENS
        output_price = settings.MOONSHOT_PRICE_OUTPUT_PER_MTOKENS

    if input_price is None or output_price is None:
        return None

    if cached_input_price is None:
        cached_input_price = input_price * max(cache_hit_factor, 0.0)

    if any(not math.isfinite(float(price)) or float(price) < 0 for price in (
        input_price, cached_input_price, output_price
    )):
        return None

    # No implicit FX conversion: retain each provider tariff currency.
    reporting_currency = pricing_currency

    return UsagePricingSnapshot(
        provider=provider,
        model_name=model_name,
        pricing_model=pricing_model,
        input_cache_miss_price_per_mtokens=float(input_price),
        input_cache_hit_price_per_mtokens=float(cached_input_price),
        output_price_per_mtokens=float(output_price),
        pricing_currency=pricing_currency,
        reporting_currency=reporting_currency,
        source=source,
        source_url=source_url,
        priced_at=(occurred_at or datetime.now(timezone.utc)).isoformat(),
    )


def _token_count(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        count = int(value)
        return count if count >= 0 and str(value).strip() == str(count) else None
    except (ValueError, TypeError, OverflowError):
        return None


def estimate_usage_costs(
    provider: str,
    model_name: str,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    cached_prompt_tokens: int | None = None,
    cache_miss_prompt_tokens: int | None = None,
    occurred_at: datetime | None = None,
) -> UsageCostBreakdown:
    """Price reported counters only; missing/contradictory usage is not free."""
    prompt = _token_count(prompt_tokens)
    completion = _token_count(completion_tokens)
    hit = _token_count(cached_prompt_tokens)
    miss = _token_count(cache_miss_prompt_tokens)
    invalid = any(value is not None and _token_count(value) is None for value in (
        prompt_tokens, completion_tokens, cached_prompt_tokens, cache_miss_prompt_tokens
    ))
    if prompt is None and hit is not None and miss is not None:
        prompt = hit + miss
    cache_status = "unknown"
    if prompt is not None and (hit is not None or miss is not None):
        hit = prompt - miss if hit is None else hit
        miss = prompt - hit if miss is None else miss
        cache_status = "known"
        if min(hit, miss) < 0 or hit + miss != prompt:
            invalid = True
    if invalid:
        cache_status = "invalid"
    pricing = _resolve_pricing(provider, model_name, prompt or 0, occurred_at)
    status = "priced"
    if invalid:
        status = "invalid_usage"
    elif prompt is None or completion is None:
        status = "unknown_usage"
    elif pricing is None:
        status = "unknown_price"
    elif cache_status != "known" and prompt > 0 and (
        pricing.input_cache_hit_price_per_mtokens != pricing.input_cache_miss_price_per_mtokens
    ):
        status = "unknown_cache"
    baseline = actual = savings = None
    if pricing is not None and prompt is not None and completion is not None and not invalid:
        baseline = (prompt * pricing.input_cache_miss_price_per_mtokens
                    + completion * pricing.output_price_per_mtokens) / 1_000_000
        if cache_status == "known":
            actual = (hit * pricing.input_cache_hit_price_per_mtokens
                      + miss * pricing.input_cache_miss_price_per_mtokens
                      + completion * pricing.output_price_per_mtokens) / 1_000_000
            savings = max(baseline - actual, 0.0)
        elif status == "priced":
            actual = baseline
            savings = 0.0
    return UsageCostBreakdown(
        prompt_tokens=prompt or 0,
        completion_tokens=completion or 0,
        total_tokens=(prompt or 0) + (completion or 0),
        cached_prompt_tokens=hit if cache_status == "known" else 0,
        billable_prompt_tokens=miss if cache_status == "known" else (prompt or 0),
        estimated_cost=baseline,
        estimated_cost_cache_aware=actual,
        estimated_cost_savings=savings,
        currency=pricing.pricing_currency if pricing else "UNKNOWN",
        pricing_snapshot=pricing,
        pricing_status=status,
        cache_status=cache_status,
    )


def estimate_usage_cost(
    provider: str,
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float | None:
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
        model: BaseLLMModel | None,
        usage: LLMUsage,
        provider: str | None = None,
        model_name: str | None = None,
        latency_ms: int | None = None,
        extra_metadata: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        usage_time_basis: str | None = None,
    ) -> LLMUsageRecord:
        if model is not None:
            resolved_provider, resolved_model_name = _resolve_model_metadata(model)
        else:
            resolved_provider = str(provider or "unknown").strip().lower() or "unknown"
            resolved_model_name = str(model_name or "unknown").strip() or "unknown"
        usage_time_basis = usage_time_basis or ("caller_supplied_estimate" if occurred_at is not None else "recorded_at_estimate")
        occurred_at = occurred_at or datetime.now(timezone.utc)
        if occurred_at.tzinfo is None:
            raise ValueError("Usage timestamp must be timezone aware")
        cost_breakdown = estimate_usage_costs(
            provider=resolved_provider,
            model_name=resolved_model_name,
            prompt_tokens=usage.prompt_tokens,
            completion_tokens=usage.completion_tokens,
            cached_prompt_tokens=usage.cached_prompt_tokens,
            cache_miss_prompt_tokens=usage.cache_miss_prompt_tokens,
            occurred_at=occurred_at,
        )
        prompt_tokens = cost_breakdown.prompt_tokens
        completion_tokens = cost_breakdown.completion_tokens
        total_tokens = cost_breakdown.total_tokens
        cached_prompt_tokens = min(cost_breakdown.cached_prompt_tokens, prompt_tokens)
        billable_prompt_tokens = min(
            cost_breakdown.billable_prompt_tokens,
            prompt_tokens,
        )
        normalized_latency_ms = max(int(latency_ms or 0), 0)
        # Legacy NOT NULL columns require zero placeholders; metadata is authoritative.
        estimated_cost = cost_breakdown.estimated_cost or 0.0
        estimated_cost_cache_aware = cost_breakdown.estimated_cost_cache_aware or 0.0

        session_uuid = _safe_uuid(session_id)
        task_uuid = _safe_uuid(task_id)

        normalized_extra_metadata = dict(extra_metadata or {})
        if usage.prompt_tokens_details:
            normalized_extra_metadata.setdefault(
                "prompt_tokens_details",
                usage.prompt_tokens_details,
            )
        if usage.cache_miss_prompt_tokens is not None:
            normalized_extra_metadata.setdefault(
                "prompt_cache_miss_tokens",
                usage.cache_miss_prompt_tokens,
            )
        normalized_extra_metadata["pricing_status"] = cost_breakdown.pricing_status
        normalized_extra_metadata["cache_status"] = cost_breakdown.cache_status
        normalized_extra_metadata["usage_occurred_at"] = occurred_at.isoformat()
        normalized_extra_metadata["usage_time_basis"] = usage_time_basis
        normalized_extra_metadata["cost_is_estimate"] = True
        normalized_extra_metadata["billing_snapshot_version"] = 1
        normalized_extra_metadata["pricing"] = (
            cost_breakdown.pricing_snapshot.to_metadata()
            if cost_breakdown.pricing_snapshot else None
        )
        normalized_extra_metadata["normalized_usage"] = usage.to_dict()
        if usage.raw:
            normalized_extra_metadata.setdefault("provider_usage", usage.raw)

        async with self.db.begin_nested():
            record = LLMUsageRecord(
                created_at=occurred_at,
                session_id=session_uuid,
                task_id=task_uuid,
                provider=resolved_provider,
                model_name=resolved_model_name,
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
                currency=cost_breakdown.currency,
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
                    if cost_breakdown.currency != str(getattr(get_settings(), "LLM_COST_REPORTING_CURRENCY", "CNY")).upper():
                        estimated_cost = estimated_cost_cache_aware = 0.0
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
    occurred_at = datetime.now(timezone.utc)

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
                occurred_at=occurred_at,
                usage_time_basis="recorded_at_estimate",
                latency_ms=latency_ms,
                extra_metadata=extra_metadata,
            )
    except Exception as exc:
        logger.warning("[LLMUsage] Failed to persist usage: %s", exc)


async def record_provider_usage_async(
    *,
    session_id: str | None,
    task_id: str | None,
    skill_key: str | None,
    step: str | None,
    step_name: str | None,
    provider: str,
    model_name: str,
    usage: LLMUsage | None,
    latency_ms: int | None = None,
    extra_metadata: dict[str, Any] | None = None,
) -> None:
    """Persist usage from provider APIs that do not use ``BaseLLMModel``."""

    normalized_usage = usage or LLMUsage()
    occurred_at = datetime.now(timezone.utc)

    try:
        async with AsyncSessionLocal() as db:
            service = LLMUsageService(db)
            await service.record_usage(
                session_id=session_id,
                task_id=task_id,
                skill_key=skill_key,
                step=step,
                step_name=step_name,
                model=None,
                provider=provider,
                model_name=model_name,
                usage=normalized_usage,
                occurred_at=occurred_at,
                usage_time_basis="recorded_at_estimate",
                latency_ms=latency_ms,
                extra_metadata=extra_metadata,
            )
    except Exception as exc:
        logger.warning("[LLMUsage] Failed to persist provider usage: %s", exc)
