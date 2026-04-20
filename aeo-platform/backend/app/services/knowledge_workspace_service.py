"""Knowledge Workspace service."""

from __future__ import annotations

import re
import hashlib
from calendar import monthrange
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Iterable
from uuid import UUID

from sqlalchemy import delete, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils import extract_domain
from app.models.knowledge import KnowledgeRecord, KnowledgeSegment


def _id_or_none(value: str | UUID | None) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return str(value)
    return str(value)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _join_non_empty(parts: Iterable[Any], sep: str = "\n") -> str:
    return sep.join(part for part in (_text(p) for p in parts) if part)


def _normalize_query_sentiment(query: str) -> str | None:
    text = str(query or "").lower()
    if any(keyword in text for keyword in ["负向", "负面", "消极", "negative"]):
        return "negative"
    if any(keyword in text for keyword in ["正向", "正面", "积极", "positive"]):
        return "positive"
    if any(keyword in text for keyword in ["中性", "neutral"]):
        return "neutral"
    return None


def _sentiment_label(sentiment: str) -> str:
    return {
        "negative": "负向",
        "positive": "正向",
        "neutral": "中性",
    }.get(str(sentiment or "").lower(), "中性")


def _sentiment_terms(sentiment: str, has_brand_mention: bool) -> list[str]:
    canonical = str(sentiment or "").lower()
    if canonical == "negative":
        terms = ["负向", "负面", "消极", "negative"]
    elif canonical == "positive":
        terms = ["正向", "正面", "积极", "positive"]
    else:
        terms = ["中性", "neutral"]
    if has_brand_mention:
        label = _sentiment_label(canonical)
        terms.extend([f"{label}提及", f"{label}品牌提及"])
    return terms


def _analyze_answer_sentiment(text: str) -> str:
    from app.workflow.a5.metrics import analyze_sentiment

    return analyze_sentiment(text)


def _answer_has_brand_mention(
    answer: dict[str, Any],
    answer_text: str,
    brand_profile: dict[str, Any],
) -> bool:
    if bool(answer.get("has_brand_mention", False)):
        return True

    from app.workflow.brand_mentions import content_mentions_brand

    return content_mentions_brand(answer_text, brand_profile)


def _extract_query_terms(query: str) -> list[str]:
    terms = []
    semantic_keywords = [
        "品牌",
        "竞品",
        "答案",
        "引用",
        "官网",
        "来源",
        "平台",
        "问题",
        "抓取",
        "分析",
        "导出",
        "汇总",
        "统计",
        "盘点",
        "变化",
        "差距",
        "历史",
        "清单",
        "提及",
        "情感",
        "负向",
        "负面",
        "正向",
        "正面",
        "中性",
        "negative",
        "positive",
        "neutral",
        "deepseek",
        "kimi",
        "doubao",
        "hunyuan",
    ]
    for match in re.findall(r"[A-Za-z0-9_.-]+|[\u4e00-\u9fff]{2,}", query):
        item = match.strip().lower()
        if len(item) >= 2:
            terms.append(item)
            for keyword in semantic_keywords:
                if keyword in item:
                    terms.append(keyword)
    query_sentiment = _normalize_query_sentiment(query)
    if query_sentiment:
        terms.extend(_sentiment_terms(query_sentiment, has_brand_mention=True))
    seen: set[str] = set()
    deduped: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


def _chunk_text(content: str, max_chars: int = 900) -> list[str]:
    text = _text(content)
    if not text:
        return []

    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
            continue
        if len(current) + 2 + len(para) <= max_chars:
            current = f"{current}\n\n{para}"
            continue
        chunks.append(current)
        current = para

    if current:
        chunks.append(current)

    normalized: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            normalized.append(chunk)
            continue
        start = 0
        while start < len(chunk):
            normalized.append(chunk[start : start + max_chars])
            start += max_chars - 120
    return normalized


def _normalize_dedupe_key(dedupe_key: str, max_chars: int = 255) -> str:
    normalized = _text(dedupe_key)
    if len(normalized) <= max_chars:
        return normalized

    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()
    prefix_budget = max_chars - len(digest) - 1
    if prefix_budget <= 0:
        return digest[:max_chars]
    return f"{normalized[:prefix_budget]}:{digest}"


def _infer_month_range(query: str) -> tuple[str | None, str | None]:
    text = _text(query)
    if not text:
        return (None, None)

    match = re.search(r"(?:(\d{4})年)?\s*(1[0-2]|0?[1-9])月", text)
    if not match:
        return (None, None)

    year = int(match.group(1) or datetime.now(timezone.utc).year)
    month = int(match.group(2))
    last_day = monthrange(year, month)[1]
    start = f"{year:04d}-{month:02d}-01"
    end = f"{year:04d}-{month:02d}-{last_day:02d}"
    return (start, end)


def _source_type_label(source_type: str) -> str:
    return {
        "brand_profile": "品牌档案",
        "competitor_profile": "竞品档案",
        "fetch_answer": "过往回答",
        "fetch_citation": "过往引用",
    }.get(source_type, source_type)


def _coerce_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def _is_fetch_answer_scope(source_types: list[str] | None) -> bool:
    normalized = {
        _text(item).lower()
        for item in (source_types or [])
        if _text(item)
    }
    return normalized == {"fetch_answer"}


def _is_fetch_status_query(query: str) -> bool:
    text = _text(query).lower()
    if not text:
        return False
    keywords = (
        "当前",
        "最近",
        "最新",
        "上一轮",
        "上轮",
        "采集状态",
        "问题采集情况",
        "成功",
        "失败",
        "成功率",
        "补采",
        "补充采集",
    )
    return any(keyword in text for keyword in keywords)


def _infer_fetch_status_filter(query: str) -> str:
    text = _text(query).lower()
    if not text:
        return "all"

    strong_failure_keywords = (
        "失败的平台",
        "失败问题",
        "失败的问题",
        "没成功",
        "未成功",
        "没采集到",
        "没有采集到",
        "未采集到",
        "没拿到答案",
        "没有答案",
        "没答案",
        "补采",
        "补充采集",
        "跳过成功",
        "只采集没成功",
    )
    if any(keyword in text for keyword in strong_failure_keywords):
        return "failure"

    strong_success_keywords = (
        "成功的平台",
        "成功问题",
        "成功的问题",
        "全部成功",
    )
    if any(keyword in text for keyword in strong_success_keywords):
        return "success"

    has_failure = any(keyword in text for keyword in ("失败", "失败率"))
    has_success = any(keyword in text for keyword in ("成功", "成功率"))
    if has_failure and not has_success:
        return "failure"
    if has_success and not has_failure:
        return "success"
    return "all"


def _fetch_status_filter_label(status_filter: str) -> str:
    return {
        "failure": "失败记录",
        "success": "成功记录",
        "all": "全部记录",
    }.get(str(status_filter or "").lower(), "全部记录")


def _analysis_scope_label(scope: str) -> str:
    return {
        "latest_window": "最近一轮",
        "all_history": "全部历史",
    }.get(str(scope or "").lower(), "当前范围")


class KnowledgeWorkspaceService:
    """Persist and retrieve retrieval-friendly evidence objects."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest_a1_facts(
        self,
        *,
        entity_id: str | UUID | None,
        session_id: str | UUID | None,
        task_id: str | UUID | None,
        run_id: str | UUID | None,
        brand_profile: dict[str, Any],
        competitors: list[dict[str, Any]],
        occurred_at: datetime | None = None,
    ) -> None:
        brand_name = _text(brand_profile.get("brand_name"))
        occurred_at = occurred_at or datetime.now(timezone.utc)

        await self._upsert_record(
            dedupe_key=(
                f"a1:brand_profile:{task_id or session_id or brand_name}:{brand_name}"
            ),
            entity_id=entity_id,
            session_id=session_id,
            task_id=task_id,
            run_id=run_id,
            source_type="brand_profile",
            brand_name=brand_name,
            title=f"{brand_name} 品牌档案" if brand_name else "品牌档案",
            occurred_at=occurred_at,
            search_text=self._build_brand_search_text(brand_profile),
            payload=brand_profile,
            extra_metadata={
                "industry": brand_profile.get("industry"),
                "official_website": brand_profile.get("official_website"),
            },
            segments=self._build_brand_segments(brand_profile),
        )

        for index, competitor in enumerate(competitors):
            competitor_name = _text(competitor.get("name"))
            if not competitor_name:
                continue
            await self._upsert_record(
                dedupe_key=(
                    f"a1:competitor:{task_id or session_id or brand_name}:{index}:{competitor_name}"
                ),
                entity_id=entity_id,
                session_id=session_id,
                task_id=task_id,
                run_id=run_id,
                source_type="competitor_profile",
                brand_name=brand_name,
                title=f"{competitor_name} 竞品档案",
                competitor_name=competitor_name,
                occurred_at=occurred_at,
                search_text=self._build_competitor_search_text(brand_name, competitor),
                payload=competitor,
                extra_metadata={
                    "competition_type": competitor.get("competition_type"),
                    "relevance_score": competitor.get("relevance_score"),
                },
                segments=self._build_competitor_segments(brand_name, competitor),
            )

        await self.db.commit()

    async def ingest_a4_facts(
        self,
        *,
        entity_id: str | UUID | None,
        session_id: str | UUID | None,
        task_id: str | UUID | None,
        run_id: str | UUID | None,
        brand_profile: dict[str, Any],
        fetch_results: list[dict[str, Any]],
        occurred_at: datetime | None = None,
    ) -> None:
        brand_name = _text(brand_profile.get("brand_name"))
        occurred_at = occurred_at or datetime.now(timezone.utc)

        for question_index, question_result in enumerate(fetch_results):
            question_id = (
                _text(question_result.get("question_id")) or f"q{question_index + 1}"
            )
            question_text = _text(question_result.get("question_text"))
            for platform_result in question_result.get("platform_results", []):
                platform = _text(platform_result.get("platform"))
                answer = platform_result.get("answer") or {}
                answer_text = _text(answer.get("content"))
                has_brand_mention = _answer_has_brand_mention(
                    answer,
                    answer_text,
                    brand_profile,
                )
                sentiment = _analyze_answer_sentiment(answer_text)
                answer_payload = {
                    "question_id": question_id,
                    "question_text": question_text,
                    "platform": platform,
                    "fetch_method": platform_result.get("fetch_method"),
                    "success": platform_result.get("success", False),
                    "answer": answer,
                    "citations": platform_result.get("citations", []),
                    "duration": platform_result.get("duration"),
                }
                await self._upsert_record(
                    dedupe_key=(
                        f"a4:answer:{task_id or session_id or brand_name}:{question_id}:{platform}"
                    ),
                    entity_id=entity_id,
                    session_id=session_id,
                    task_id=task_id,
                    run_id=run_id,
                    source_type="fetch_answer",
                    brand_name=brand_name,
                    title=f"{platform} - {question_text[:80]}",
                    platform=platform,
                    question_id=question_id,
                    question_text=question_text,
                    occurred_at=occurred_at,
                    search_text=self._build_answer_search_text(
                        brand_name,
                        question_text,
                        platform,
                        answer_text,
                        sentiment,
                        has_brand_mention,
                    ),
                    payload=answer_payload,
                    extra_metadata={
                        "fetch_method": platform_result.get("fetch_method"),
                        "success": platform_result.get("success", False),
                        "has_brand_mention": has_brand_mention,
                        "citation_count": len(platform_result.get("citations", [])),
                        "sentiment": sentiment,
                        "sentiment_label": _sentiment_label(sentiment),
                    },
                    segments=self._build_answer_segments(
                        brand_name,
                        question_text,
                        platform,
                        answer_text,
                        sentiment,
                        has_brand_mention,
                    ),
                )

                citations = platform_result.get("citations", []) or []
                for citation_index, citation in enumerate(citations):
                    url = _text(citation.get("url"))
                    title = (
                        _text(citation.get("title"))
                        or url
                        or f"citation-{citation_index + 1}"
                    )
                    domain = _text(citation.get("domain")) or extract_domain(url)
                    site_name = _text(
                        citation.get("site_name") or citation.get("source")
                    )
                    is_official = bool(
                        domain
                        and extract_domain(_text(brand_profile.get("official_website")))
                        == domain
                    )
                    citation_payload = {
                        "question_id": question_id,
                        "question_text": question_text,
                        "platform": platform,
                        "citation": citation,
                        "is_official": is_official,
                    }
                    await self._upsert_record(
                        dedupe_key=(
                            f"a4:citation:{task_id or session_id or brand_name}:{question_id}:{platform}:{url or title}:{citation_index}"
                        ),
                        entity_id=entity_id,
                        session_id=session_id,
                        task_id=task_id,
                        run_id=run_id,
                        source_type="fetch_citation",
                        brand_name=brand_name,
                        title=title[:255],
                        platform=platform,
                        question_id=question_id,
                        question_text=question_text,
                        domain=domain or None,
                        occurred_at=occurred_at,
                        search_text=self._build_citation_search_text(
                            brand_name,
                            question_text,
                            platform,
                            title,
                            url,
                            site_name,
                            domain,
                        ),
                        payload=citation_payload,
                        extra_metadata={
                            "url": url,
                            "site_name": site_name,
                            "is_official": is_official,
                        },
                        segments=self._build_citation_segments(
                            question_text,
                            platform,
                            title,
                            url,
                            site_name,
                            domain,
                            is_official,
                        ),
                    )

        await self.db.commit()

    def _record_fetch_success(self, record: KnowledgeRecord) -> bool:
        metadata = record.extra_metadata if isinstance(record.extra_metadata, dict) else {}
        payload = record.payload if isinstance(record.payload, dict) else {}

        success = _coerce_bool(metadata.get("success"))
        if success is not None:
            return success

        success = _coerce_bool(payload.get("success"))
        if success is not None:
            return success

        answer = payload.get("answer")
        if isinstance(answer, dict) and _text(answer.get("content")):
            return True
        return False

    def _analysis_label_with_parts(
        self,
        record: KnowledgeRecord,
    ) -> tuple[str, str | None, str | None, str | None]:
        task_id = _text(record.task_id) or None
        run_id = _text(record.run_id) or None
        session_id = _text(record.session_id) or None
        if task_id:
            return (f"task:{task_id}", task_id, run_id, session_id)
        if run_id:
            return (f"run:{run_id}", None, run_id, session_id)
        if session_id:
            return (f"session:{session_id}", None, None, session_id)
        occurred_at = getattr(record, "occurred_at", None)
        if occurred_at:
            return (
                f"date:{occurred_at.strftime('%Y-%m-%d')}",
                None,
                None,
                session_id,
            )
        return ("unknown", None, None, session_id)

    def _latest_analysis_records(
        self,
        records: list[KnowledgeRecord],
    ) -> tuple[list[KnowledgeRecord], dict[str, Any]]:
        if not records:
            return ([], {})

        ordered = sorted(
            records,
            key=lambda record: record.occurred_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )
        label, task_id, run_id, session_id = self._analysis_label_with_parts(ordered[0])
        latest_records = [
            record
            for record in ordered
            if self._analysis_label_with_parts(record)[0] == label
        ]
        return (
            latest_records,
            {
                "analysis_label": label,
                "task_id": task_id,
                "run_id": run_id,
                "session_id": session_id,
                "occurred_at": (
                    latest_records[0].occurred_at.isoformat()
                    if latest_records and latest_records[0].occurred_at
                    else None
                ),
            },
        )

    def _build_fetch_status_summary(
        self,
        records: list[KnowledgeRecord],
    ) -> dict[str, Any]:
        latest_records, latest_identity = self._latest_analysis_records(records)
        if not latest_records:
            return {}

        success_count = 0
        failure_count = 0
        platform_rollup: dict[str, dict[str, Any]] = {}
        failed_targets: dict[str, dict[str, Any]] = {}

        for record in latest_records:
            platform = _text(record.platform).lower()
            question_id = _text(record.question_id)
            question_text = _text(record.question_text)
            is_success = self._record_fetch_success(record)

            if platform:
                row = platform_rollup.setdefault(
                    platform,
                    {
                        "platform": platform,
                        "success_count": 0,
                        "failure_count": 0,
                        "total_count": 0,
                    },
                )
                row["total_count"] += 1
                if is_success:
                    row["success_count"] += 1
                else:
                    row["failure_count"] += 1

            if is_success:
                success_count += 1
                continue

            failure_count += 1
            if question_id and question_text and platform:
                target = failed_targets.setdefault(
                    question_id,
                    {
                        "question_id": question_id,
                        "question_text": question_text,
                        "platforms": [],
                    },
                )
                if platform not in target["platforms"]:
                    target["platforms"].append(platform)

        total_count = success_count + failure_count
        failed_question_targets = sorted(
            failed_targets.values(),
            key=lambda item: item["question_id"],
        )
        failed_platforms = sorted(
            {
                platform
                for item in failed_question_targets
                for platform in item["platforms"]
            }
        )
        return {
            **latest_identity,
            "success_count": success_count,
            "failure_count": failure_count,
            "total_count": total_count,
            "success_rate": (success_count / total_count) if total_count else 0.0,
            "failed_question_count": len(failed_question_targets),
            "failed_platform_count": len(failed_platforms),
            "platform_breakdown": sorted(
                platform_rollup.values(),
                key=lambda item: (-int(item["failure_count"]), item["platform"]),
            ),
            "failed_question_targets": failed_question_targets,
        }

    def _filter_fetch_status_records(
        self,
        records: list[KnowledgeRecord],
        *,
        status_filter: str,
    ) -> list[KnowledgeRecord]:
        normalized = str(status_filter or "all").lower()
        if normalized not in {"success", "failure"}:
            return list(records)

        want_success = normalized == "success"
        return [
            record
            for record in records
            if self._record_fetch_success(record) is want_success
        ]

    async def get_manifest(
        self,
        *,
        entity_id: str | UUID | None = None,
        brand_name: str | None = None,
    ) -> dict[str, Any]:
        if _id_or_none(entity_id) is None and not brand_name:
            return {
                "available_sources": {
                    "brand_profile": False,
                    "competitor_profile": False,
                    "fetch_answer": False,
                    "fetch_citation": False,
                },
                "counts": {},
                "history": {"latest_analysis_at": None},
                "coverage": {"platform_count": 0, "question_count": 0},
            }

        stmt = select(
            KnowledgeRecord.source_type,
            func.count(KnowledgeRecord.id),
            func.max(KnowledgeRecord.occurred_at),
        )
        stmt = stmt.where(
            *self._scope_conditions(entity_id=entity_id, brand_name=brand_name)
        )
        stmt = stmt.group_by(KnowledgeRecord.source_type)
        result = await self.db.execute(stmt)
        rows = result.all()

        counts: dict[str, int] = defaultdict(int)
        latest = None
        for source_type, count, latest_at in rows:
            counts[source_type] = int(count or 0)
            if latest_at is not None and (latest is None or latest_at > latest):
                latest = latest_at

        platform_stmt = select(
            func.count(func.distinct(KnowledgeRecord.platform))
        ).where(
            *self._scope_conditions(entity_id=entity_id, brand_name=brand_name),
            KnowledgeRecord.platform.is_not(None),
        )
        question_stmt = select(
            func.count(func.distinct(KnowledgeRecord.question_id))
        ).where(
            *self._scope_conditions(entity_id=entity_id, brand_name=brand_name),
            KnowledgeRecord.question_id.is_not(None),
        )

        platform_count = int((await self.db.execute(platform_stmt)).scalar() or 0)
        question_count = int((await self.db.execute(question_stmt)).scalar() or 0)
        history_rows = (
            await self.db.execute(
                select(
                    KnowledgeRecord.task_id,
                    KnowledgeRecord.run_id,
                    KnowledgeRecord.session_id,
                    KnowledgeRecord.occurred_at,
                )
                .where(
                    *self._scope_conditions(entity_id=entity_id, brand_name=brand_name)
                )
                .order_by(desc(KnowledgeRecord.occurred_at))
                .limit(1000)
            )
        ).all()

        analysis_labels: set[str] = set()
        recent_months: list[str] = []
        for task_id, run_id, session_id, occurred_at in history_rows:
            label = None
            if task_id:
                label = f"task:{task_id}"
            elif run_id:
                label = f"run:{run_id}"
            elif session_id:
                label = f"session:{session_id}"
            elif occurred_at:
                label = f"date:{occurred_at.strftime('%Y-%m-%d')}"
            if label:
                analysis_labels.add(label)

            month_label = occurred_at.strftime("%Y-%m")
            if month_label not in recent_months:
                recent_months.append(month_label)
            if len(recent_months) >= 6:
                break

        latest_fetch_summary: dict[str, Any] = {}
        if counts.get("fetch_answer", 0) > 0:
            fetch_stmt = (
                select(KnowledgeRecord)
                .where(
                    *self._scope_conditions(entity_id=entity_id, brand_name=brand_name),
                    KnowledgeRecord.source_type == "fetch_answer",
                )
                .order_by(desc(KnowledgeRecord.occurred_at))
                .limit(2000)
            )
            fetch_records = list((await self.db.execute(fetch_stmt)).scalars())
            latest_fetch_summary = self._build_fetch_status_summary(fetch_records)

        return {
            "available_sources": {
                "brand_profile": counts.get("brand_profile", 0) > 0,
                "competitor_profile": counts.get("competitor_profile", 0) > 0,
                "fetch_answer": counts.get("fetch_answer", 0) > 0,
                "fetch_citation": counts.get("fetch_citation", 0) > 0,
            },
            "counts": dict(counts),
            "history": {
                "latest_analysis_at": latest.isoformat() if latest else None,
                "analysis_window_count": len(analysis_labels),
                "recent_months": recent_months,
                "latest_fetch": latest_fetch_summary,
            },
            "coverage": {
                "platform_count": platform_count,
                "question_count": question_count,
            },
        }

    async def lookup(
        self,
        *,
        query: str,
        entity_id: str | UUID | None = None,
        brand_name: str | None = None,
        source_types: list[str] | None = None,
        platform: str | None = None,
        competitor_name: str | None = None,
        domain: str | None = None,
        limit: int = 8,
    ) -> dict[str, Any]:
        if _id_or_none(entity_id) is None and not brand_name:
            return {
                "status": "miss",
                "query": query,
                "matches": [],
                "reason": "missing_scope",
            }

        terms = _extract_query_terms(query)
        base_stmt = (
            select(KnowledgeSegment, KnowledgeRecord)
            .join(KnowledgeRecord, KnowledgeSegment.record_id == KnowledgeRecord.id)
            .where(*self._scope_conditions(entity_id=entity_id, brand_name=brand_name))
        )
        if source_types:
            base_stmt = base_stmt.where(KnowledgeRecord.source_type.in_(source_types))
        if platform:
            base_stmt = base_stmt.where(KnowledgeRecord.platform == platform)
        if competitor_name:
            base_stmt = base_stmt.where(KnowledgeRecord.competitor_name == competitor_name)
        if domain:
            base_stmt = base_stmt.where(KnowledgeRecord.domain == domain)

        stmt = base_stmt
        if terms:
            term_conditions = [
                KnowledgeSegment.search_text.ilike(f"%{term}%") for term in terms
            ]
            stmt = stmt.where(or_(*term_conditions))
        stmt = stmt.order_by(desc(KnowledgeRecord.occurred_at)).limit(
            max(limit * 8, 40)
        )

        rows = (await self.db.execute(stmt)).all()
        if not rows and terms:
            fallback_stmt = base_stmt.order_by(desc(KnowledgeRecord.occurred_at)).limit(
                max(limit * 8, 40)
            )
            rows = (await self.db.execute(fallback_stmt)).all()
        ranked: list[dict[str, Any]] = []
        for segment, record in rows:
            score = self._score_match(
                query=query, terms=terms, record=record, segment=segment
            )
            ranked.append(
                {
                    "score": score,
                    "record_id": str(record.id),
                    "source_type": record.source_type,
                    "title": record.title,
                    "brand_name": record.brand_name,
                    "platform": record.platform,
                    "question_id": record.question_id,
                    "question_text": record.question_text,
                    "competitor_name": record.competitor_name,
                    "domain": record.domain,
                    "occurred_at": record.occurred_at.isoformat(),
                    "snippet": segment.content[:320],
                    "payload": record.payload,
                    "metadata": record.extra_metadata,
                }
            )

        ranked.sort(key=lambda item: (item["score"], item["occurred_at"]), reverse=True)
        matches = [item for item in ranked if item["score"] >= 3][:limit]
        return {
            "status": "hit" if matches else "miss",
            "query": query,
            "matches": matches,
        }

    async def aggregate(
        self,
        *,
        query: str = "",
        entity_id: str | UUID | None = None,
        brand_name: str | None = None,
        source_types: list[str] | None = None,
        group_by: str = "source_type",
        platform: str | None = None,
        competitor_name: str | None = None,
        domain: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        if _id_or_none(entity_id) is None and not brand_name:
            return {
                "status": "miss",
                "groups": [],
                "reason": "missing_scope",
            }

        inferred_start, inferred_end = _infer_month_range(query)
        start_date = start_date or inferred_start
        end_date = end_date or inferred_end
        fetch_status_query = _is_fetch_status_query(query)
        effective_source_types = list(source_types or [])
        if fetch_status_query and not effective_source_types:
            effective_source_types = ["fetch_answer"]

        records = await self._fetch_records(
            query=query,
            entity_id=entity_id,
            brand_name=brand_name,
            source_types=effective_source_types or None,
            platform=platform,
            competitor_name=competitor_name,
            domain=domain,
            start_date=start_date,
            end_date=end_date,
            max_records=max(limit * 20, 200),
        )
        fetch_scope = _is_fetch_answer_scope(effective_source_types or None)
        analysis_scope = "all_history"
        if fetch_scope and fetch_status_query:
            latest_records, _ = self._latest_analysis_records(records)
            if latest_records:
                records = latest_records
                analysis_scope = "latest_window"
        fetch_status_summary = (
            self._build_fetch_status_summary(records) if fetch_scope and records else {}
        )
        status_filter = _infer_fetch_status_filter(query) if fetch_scope else "all"
        records_for_groups = (
            self._filter_fetch_status_records(records, status_filter=status_filter)
            if fetch_scope
            else list(records)
        )

        grouped: dict[str, list[KnowledgeRecord]] = defaultdict(list)
        for record in records_for_groups:
            key = self._aggregate_key(record, group_by)
            if key is None:
                continue
            grouped[key].append(record)

        groups: list[dict[str, Any]] = []
        for key, items in grouped.items():
            success_count = 0
            failure_count = 0
            question_keys: set[str] = set()
            platform_keys: set[str] = set()
            failure_question_keys: set[str] = set()
            success_question_keys: set[str] = set()
            if fetch_scope:
                for item in items:
                    question_key = _text(item.question_id) or _text(item.question_text)
                    if question_key:
                        question_keys.add(question_key)
                    platform_key = _text(item.platform)
                    if platform_key:
                        platform_keys.add(platform_key)
                    if self._record_fetch_success(item):
                        success_count += 1
                        if question_key:
                            success_question_keys.add(question_key)
                    else:
                        failure_count += 1
                        if question_key:
                            failure_question_keys.add(question_key)
            groups.append(
                {
                    "group_key": key,
                    "count": len(items),
                    "success_count": success_count if fetch_scope else None,
                    "failure_count": failure_count if fetch_scope else None,
                    "question_count": len(question_keys) if fetch_scope else None,
                    "platform_count": len(platform_keys) if fetch_scope else None,
                    "success_question_count": (
                        len(success_question_keys) if fetch_scope else None
                    ),
                    "failure_question_count": (
                        len(failure_question_keys) if fetch_scope else None
                    ),
                    "success_rate": (
                        success_count / len(items) if fetch_scope and items else None
                    ),
                    "source_types": sorted(
                        {item.source_type for item in items if item.source_type}
                    ),
                    "sample_titles": [
                        title
                        for title in [
                            _text(item.title) for item in items[: min(len(items), 3)]
                        ]
                        if title
                    ],
                    "record_ids": [
                        str(item.id) for item in items[: min(len(items), 5)]
                    ],
                    "sample_records": [
                        self._serialize_record_summary(item)
                        for item in items[: min(len(items), 3)]
                    ],
                }
            )

        groups.sort(key=lambda item: (item["count"], item["group_key"]), reverse=True)
        return {
            "status": "hit" if groups else "miss",
            "group_by": group_by,
            "query": query,
            "analysis_scope": analysis_scope,
            "analysis_scope_label": _analysis_scope_label(analysis_scope),
            "status_filter": status_filter,
            "status_filter_label": _fetch_status_filter_label(status_filter),
            "total_records": len(records_for_groups),
            "unfiltered_total_records": len(records),
            "fetch_status_summary": fetch_status_summary,
            "groups": groups[:limit],
        }

    async def compare(
        self,
        *,
        entity_id: str | UUID | None = None,
        brand_name: str | None = None,
        compare_by: str = "platform",
        source_types: list[str] | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        if _id_or_none(entity_id) is None and not brand_name:
            return {
                "status": "miss",
                "comparisons": [],
                "reason": "missing_scope",
            }

        records = await self._fetch_records(
            query="",
            entity_id=entity_id,
            brand_name=brand_name,
            source_types=source_types,
            platform=None,
            competitor_name=None,
            domain=None,
            start_date=None,
            end_date=None,
            max_records=1000,
        )

        analysis_groups: dict[str, list[KnowledgeRecord]] = defaultdict(list)
        for record in records:
            label = self._analysis_group_label(record)
            analysis_groups[label].append(record)

        ordered_groups = sorted(
            analysis_groups.items(),
            key=lambda item: max(r.occurred_at for r in item[1]),
            reverse=True,
        )
        if len(ordered_groups) < 2:
            return {
                "status": "miss",
                "comparisons": [],
                "reason": "insufficient_history",
            }

        latest_label, latest_records = ordered_groups[0]
        previous_label, previous_records = ordered_groups[1]

        latest_counts = self._aggregate_counts(latest_records, compare_by)
        previous_counts = self._aggregate_counts(previous_records, compare_by)
        latest_grouped = self._group_records(latest_records, compare_by)
        previous_grouped = self._group_records(previous_records, compare_by)

        all_keys = set(latest_counts) | set(previous_counts)
        comparisons: list[dict[str, Any]] = []
        for key in all_keys:
            latest_count = latest_counts.get(key, 0)
            previous_count = previous_counts.get(key, 0)
            comparisons.append(
                {
                    "group_key": key,
                    "latest_count": latest_count,
                    "previous_count": previous_count,
                    "delta": latest_count - previous_count,
                    "latest_examples": [
                        self._serialize_record_summary(record)
                        for record in latest_grouped.get(key, [])[:2]
                    ],
                    "previous_examples": [
                        self._serialize_record_summary(record)
                        for record in previous_grouped.get(key, [])[:2]
                    ],
                }
            )

        comparisons.sort(
            key=lambda item: (
                abs(item["delta"]),
                item["latest_count"],
                item["group_key"],
            ),
            reverse=True,
        )

        return {
            "status": "hit",
            "compare_by": compare_by,
            "latest_label": latest_label,
            "previous_label": previous_label,
            "comparisons": comparisons[:limit],
        }

    async def export_table(
        self,
        *,
        query: str = "",
        entity_id: str | UUID | None = None,
        brand_name: str | None = None,
        source_types: list[str] | None = None,
        platform: str | None = None,
        competitor_name: str | None = None,
        domain: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        if _id_or_none(entity_id) is None and not brand_name:
            return {
                "status": "miss",
                "reason": "missing_scope",
                "columns": [],
                "rows": [],
            }

        inferred_start, inferred_end = _infer_month_range(query)
        start_date = start_date or inferred_start
        end_date = end_date or inferred_end

        effective_limit = max(min(limit, 500), 1)
        records = await self._fetch_records(
            query=query,
            entity_id=entity_id,
            brand_name=brand_name,
            source_types=source_types,
            platform=platform,
            competitor_name=competitor_name,
            domain=domain,
            start_date=start_date,
            end_date=end_date,
            max_records=effective_limit + 1,
        )
        truncated = len(records) > effective_limit
        visible_records = records[:effective_limit]
        rows = [self._serialize_export_row(record) for record in visible_records]
        if not rows:
            return {
                "status": "miss",
                "reason": "no_records",
                "columns": self._export_columns(),
                "rows": [],
            }

        effective_brand = (
            brand_name
            or next(
                (
                    _text(record.brand_name)
                    for record in visible_records
                    if _text(record.brand_name)
                ),
                "",
            )
            or "品牌"
        )
        source_set = sorted(
            {
                _text(record.source_type)
                for record in visible_records
                if _text(record.source_type)
            }
        )
        platforms = sorted(
            {
                _text(record.platform)
                for record in visible_records
                if _text(record.platform)
            }
        )
        description_parts = []
        if query:
            description_parts.append(f"主题：{query}")
        if start_date or end_date:
            period = " 至 ".join(part for part in [start_date, end_date] if part)
            description_parts.append(f"时间范围：{period}")
        if platform:
            description_parts.append(f"平台：{platform}")
        if competitor_name:
            description_parts.append(f"竞品：{competitor_name}")
        if domain:
            description_parts.append(f"域名：{domain}")
        if truncated:
            description_parts.append(
                f"当前结果较多，已仅展示前 {effective_limit} 条，请缩小筛选范围以导出完整结果"
            )

        return {
            "status": "hit",
            "title": f"{effective_brand} 过往资料表",
            "brand_name": effective_brand,
            "description": "；".join(description_parts)
            or "基于过往品牌资料整理的数据表",
            "columns": self._export_columns(),
            "rows": rows,
            "item_count": len(rows),
            "truncated": truncated,
            "has_more_records": truncated,
            "export_limit": effective_limit,
            "source_types": source_set,
            "platforms": platforms,
            "analysis_period": (
                " 至 ".join(part for part in [start_date, end_date] if part)
                if start_date or end_date
                else "历次分析汇总"
            ),
            "summary_metrics": {
                "导出条数": len(rows),
                "来源类型": len(source_set),
                "覆盖平台数": len(platforms),
                "结果截断": "是" if truncated else "否",
            },
        }

    def _scope_conditions(
        self,
        *,
        entity_id: str | UUID | None,
        brand_name: str | None,
    ) -> list[Any]:
        conditions: list[Any] = []
        entity_uuid = _id_or_none(entity_id)
        if entity_uuid is not None:
            conditions.append(KnowledgeRecord.entity_id == entity_uuid)
        elif brand_name:
            conditions.append(KnowledgeRecord.brand_name == brand_name)
        return conditions

    async def _fetch_records(
        self,
        *,
        query: str,
        entity_id: str | UUID | None,
        brand_name: str | None,
        source_types: list[str] | None,
        platform: str | None,
        competitor_name: str | None,
        domain: str | None,
        start_date: str | None,
        end_date: str | None,
        max_records: int,
    ) -> list[KnowledgeRecord]:
        base_stmt = select(KnowledgeRecord).where(
            *self._scope_conditions(entity_id=entity_id, brand_name=brand_name)
        )
        if source_types:
            base_stmt = base_stmt.where(KnowledgeRecord.source_type.in_(source_types))
        if platform:
            base_stmt = base_stmt.where(KnowledgeRecord.platform == platform)
        if competitor_name:
            base_stmt = base_stmt.where(KnowledgeRecord.competitor_name == competitor_name)
        if domain:
            base_stmt = base_stmt.where(KnowledgeRecord.domain == domain)

        if start_date:
            parsed_start = self._parse_date(start_date, end_of_day=False)
            if parsed_start is not None:
                base_stmt = base_stmt.where(KnowledgeRecord.occurred_at >= parsed_start)
        if end_date:
            parsed_end = self._parse_date(end_date, end_of_day=True)
            if parsed_end is not None:
                base_stmt = base_stmt.where(KnowledgeRecord.occurred_at <= parsed_end)

        terms = _extract_query_terms(query)
        stmt = base_stmt
        if terms:
            term_conditions = [
                KnowledgeRecord.search_text.ilike(f"%{term}%") for term in terms
            ]
            stmt = stmt.where(or_(*term_conditions))

        stmt = stmt.order_by(desc(KnowledgeRecord.occurred_at)).limit(max_records)
        records = list((await self.db.execute(stmt)).scalars())
        if records or not terms:
            return records

        fallback_stmt = base_stmt.order_by(desc(KnowledgeRecord.occurred_at)).limit(
            max_records
        )
        return list((await self.db.execute(fallback_stmt)).scalars())

    def _aggregate_key(self, record: KnowledgeRecord, group_by: str) -> str | None:
        if group_by == "platform":
            return _text(record.platform) or None
        if group_by == "competitor":
            return _text(record.competitor_name) or None
        if group_by == "domain":
            return _text(record.domain) or None
        if group_by == "question":
            return _text(record.question_text) or _text(record.question_id) or None
        if group_by == "month":
            return record.occurred_at.strftime("%Y-%m")
        return _text(record.source_type) or "unknown_source"

    def _analysis_group_label(self, record: KnowledgeRecord) -> str:
        if record.task_id:
            return f"task:{record.task_id}"
        if record.run_id:
            return f"run:{record.run_id}"
        if record.session_id:
            return f"session:{record.session_id}"
        return f"date:{record.occurred_at.strftime('%Y-%m-%d')}"

    def _aggregate_counts(
        self,
        records: list[KnowledgeRecord],
        compare_by: str,
    ) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for record in records:
            key = self._aggregate_key(record, compare_by)
            if key is None:
                continue
            counts[key] += 1
        return counts

    def _group_records(
        self,
        records: list[KnowledgeRecord],
        group_by: str,
    ) -> dict[str, list[KnowledgeRecord]]:
        grouped: dict[str, list[KnowledgeRecord]] = defaultdict(list)
        for record in records:
            key = self._aggregate_key(record, group_by)
            if key is None:
                continue
            grouped[key].append(record)
        return grouped

    def _parse_date(
        self,
        value: str,
        *,
        end_of_day: bool,
    ) -> datetime | None:
        value = _text(value)
        if not value:
            return None
        try:
            if len(value) == 7:
                base = datetime.strptime(value, "%Y-%m")
                if end_of_day:
                    last_day = monthrange(base.year, base.month)[1]
                    return base.replace(
                        day=last_day,
                        hour=23,
                        minute=59,
                        second=59,
                        tzinfo=timezone.utc,
                    )
                return base.replace(tzinfo=timezone.utc)
            base = datetime.strptime(value, "%Y-%m-%d")
            if end_of_day:
                return base.replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            return base.replace(tzinfo=timezone.utc)
        except ValueError:
            return None

    async def _upsert_record(
        self,
        *,
        dedupe_key: str,
        entity_id: str | UUID | None,
        session_id: str | UUID | None,
        task_id: str | UUID | None,
        run_id: str | UUID | None,
        source_type: str,
        brand_name: str | None,
        title: str | None,
        occurred_at: datetime,
        search_text: str,
        payload: dict[str, Any] | None,
        extra_metadata: dict[str, Any] | None,
        segments: list[dict[str, Any]],
        platform: str | None = None,
        question_id: str | None = None,
        question_text: str | None = None,
        competitor_name: str | None = None,
        domain: str | None = None,
    ) -> KnowledgeRecord:
        dedupe_key = _normalize_dedupe_key(dedupe_key)
        stmt = select(KnowledgeRecord).where(KnowledgeRecord.dedupe_key == dedupe_key)
        existing = (await self.db.execute(stmt)).scalar_one_or_none()
        if existing is None:
            existing = KnowledgeRecord(
                dedupe_key=dedupe_key,
                source_type=source_type,
            )
            self.db.add(existing)
            await self.db.flush()

        existing.entity_id = _id_or_none(entity_id)
        existing.session_id = _id_or_none(session_id)
        existing.task_id = _id_or_none(task_id)
        existing.run_id = _id_or_none(run_id)
        existing.brand_name = brand_name
        existing.title = title
        existing.platform = platform
        existing.question_id = question_id
        existing.question_text = question_text
        existing.competitor_name = competitor_name
        existing.domain = domain
        existing.occurred_at = occurred_at
        existing.search_text = search_text
        existing.payload = payload
        existing.extra_metadata = extra_metadata

        await self.db.flush()
        await self.db.execute(
            delete(KnowledgeSegment).where(KnowledgeSegment.record_id == existing.id)
        )
        for index, segment in enumerate(segments):
            self.db.add(
                KnowledgeSegment(
                    record_id=existing.id,
                    segment_index=index,
                    content=_text(segment.get("content")),
                    search_text=_text(
                        segment.get("search_text") or segment.get("content")
                    ),
                    extra_metadata=segment.get("metadata"),
                )
            )
        await self.db.flush()
        return existing

    def _score_match(
        self,
        *,
        query: str,
        terms: list[str],
        record: KnowledgeRecord,
        segment: KnowledgeSegment,
    ) -> int:
        metadata = (
            record.extra_metadata if isinstance(record.extra_metadata, dict) else {}
        )
        haystack = " ".join(
            part.lower()
            for part in [
                _text(record.title),
                _text(record.question_text),
                _text(record.competitor_name),
                _text(record.domain),
                _text(segment.search_text),
            ]
            if part
        )
        score = 0
        if query and query.lower() in haystack:
            score += 6
        for term in terms:
            if term in haystack:
                score += 2
        query_sentiment = _normalize_query_sentiment(query)
        record_sentiment = _text(metadata.get("sentiment")).lower()
        if query_sentiment and record_sentiment:
            if record_sentiment == query_sentiment:
                score += 8
            else:
                score -= 2
        if "提及" in query and bool(metadata.get("has_brand_mention")):
            score += 2
        if record.source_type in {"fetch_answer", "fetch_citation"}:
            score += 1
        return score

    def _export_columns(self) -> list[dict[str, Any]]:
        return [
            {"key": "occurred_at", "label": "时间", "sortable": True},
            {"key": "source_type", "label": "来源类型", "sortable": True},
            {"key": "platform", "label": "平台", "sortable": True},
            {"key": "competitor_name", "label": "竞品", "sortable": True},
            {"key": "question_text", "label": "问题", "sortable": False},
            {"key": "title", "label": "标题", "sortable": False},
            {"key": "domain", "label": "域名", "sortable": True},
            {"key": "site_name", "label": "站点", "sortable": True},
            {"key": "is_official", "label": "官网", "sortable": True},
            {"key": "snippet", "label": "摘要", "sortable": False},
            {"key": "url", "label": "链接", "sortable": False},
        ]

    def _build_brand_search_text(self, brand_profile: dict[str, Any]) -> str:
        return _join_non_empty(
            [
                brand_profile.get("brand_name"),
                brand_profile.get("brand_name_en"),
                brand_profile.get("industry"),
                brand_profile.get("description"),
                "核心产品：" + "、".join(brand_profile.get("core_products", []) or []),
                "品牌关键词："
                + "、".join(brand_profile.get("brand_keywords", []) or []),
                "品牌定位：" + _text(brand_profile.get("brand_positioning")),
                "目标受众：" + _text(brand_profile.get("target_audience")),
                "价格定位：" + _text(brand_profile.get("price_positioning")),
            ]
        )

    def _build_brand_segments(
        self, brand_profile: dict[str, Any]
    ) -> list[dict[str, Any]]:
        segments = [
            {
                "content": _join_non_empty(
                    [
                        f"品牌：{brand_profile.get('brand_name')}",
                        f"英文名：{brand_profile.get('brand_name_en')}",
                        f"行业：{brand_profile.get('industry')}",
                        f"官网：{brand_profile.get('official_website')}",
                        f"描述：{brand_profile.get('description')}",
                    ]
                )
            },
            {
                "content": _join_non_empty(
                    [
                        f"品牌定位：{brand_profile.get('brand_positioning')}",
                        f"目标受众：{brand_profile.get('target_audience')}",
                        f"价格定位：{brand_profile.get('price_positioning')}",
                        f"成立年份：{brand_profile.get('founded_year')}",
                    ]
                )
            },
            {
                "content": _join_non_empty(
                    [
                        "核心产品："
                        + "、".join(brand_profile.get("core_products", []) or []),
                        "品牌关键词："
                        + "、".join(brand_profile.get("brand_keywords", []) or []),
                    ]
                )
            },
        ]
        return [segment for segment in segments if _text(segment.get("content"))]

    def _build_competitor_search_text(
        self,
        brand_name: str,
        competitor: dict[str, Any],
    ) -> str:
        return _join_non_empty(
            [
                f"品牌：{brand_name}",
                f"竞品：{competitor.get('name')}",
                f"描述：{competitor.get('description')}",
                f"竞争类型：{competitor.get('competition_type')}",
                f"相关度：{competitor.get('relevance_score')}",
                "核心产品：" + "、".join(competitor.get("core_products", []) or []),
                f"竞争优势：{competitor.get('competitive_advantage')}",
            ]
        )

    def _build_competitor_segments(
        self,
        brand_name: str,
        competitor: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return [
            {
                "content": _join_non_empty(
                    [
                        f"品牌：{brand_name}",
                        f"竞品：{competitor.get('name')}",
                        f"描述：{competitor.get('description')}",
                        f"竞争类型：{competitor.get('competition_type')}",
                        f"相关度：{competitor.get('relevance_score')}",
                    ]
                )
            },
            {
                "content": _join_non_empty(
                    [
                        "核心产品："
                        + "、".join(competitor.get("core_products", []) or []),
                        f"竞争优势：{competitor.get('competitive_advantage')}",
                    ]
                )
            },
        ]

    def _build_answer_search_text(
        self,
        brand_name: str,
        question_text: str,
        platform: str,
        answer_text: str,
        sentiment: str,
        has_brand_mention: bool,
    ) -> str:
        sentiment_terms = "、".join(_sentiment_terms(sentiment, has_brand_mention))
        return _join_non_empty(
            [
                "类型：过往回答",
                "抓取结果",
                f"品牌：{brand_name}",
                f"平台：{platform}",
                f"问题：{question_text}",
                f"情感：{_sentiment_label(sentiment)}",
                f"品牌提及：{'是' if has_brand_mention else '否'}",
                f"标签：{sentiment_terms}",
                f"答案：{answer_text}",
            ]
        )

    def _build_answer_segments(
        self,
        brand_name: str,
        question_text: str,
        platform: str,
        answer_text: str,
        sentiment: str,
        has_brand_mention: bool,
    ) -> list[dict[str, Any]]:
        chunks = _chunk_text(answer_text)
        if not chunks:
            chunks = [""]
        return [
            {
                "content": _join_non_empty(
                    [
                        "类型：过往回答",
                        "抓取结果",
                        f"品牌：{brand_name}",
                        f"平台：{platform}",
                        f"问题：{question_text}",
                        f"情感：{_sentiment_label(sentiment)}",
                        f"品牌提及：{'是' if has_brand_mention else '否'}",
                        "标签："
                        + "、".join(_sentiment_terms(sentiment, has_brand_mention)),
                        chunk,
                    ]
                )
            }
            for chunk in chunks
        ]

    def _build_citation_search_text(
        self,
        brand_name: str,
        question_text: str,
        platform: str,
        title: str,
        url: str,
        site_name: str,
        domain: str,
    ) -> str:
        return _join_non_empty(
            [
                "类型：过往引用",
                "引用来源",
                "抓取结果",
                f"品牌：{brand_name}",
                f"平台：{platform}",
                f"问题：{question_text}",
                f"标题：{title}",
                f"站点：{site_name}",
                f"域名：{domain}",
                f"链接：{url}",
            ]
        )

    def _build_citation_segments(
        self,
        question_text: str,
        platform: str,
        title: str,
        url: str,
        site_name: str,
        domain: str,
        is_official: bool,
    ) -> list[dict[str, Any]]:
        return [
            {
                "content": _join_non_empty(
                    [
                        "类型：过往引用",
                        "引用来源",
                        "抓取结果",
                        f"平台：{platform}",
                        f"问题：{question_text}",
                        f"标题：{title}",
                        f"站点：{site_name}",
                        f"域名：{domain}",
                        f"链接：{url}",
                        f"是否官网：{'是' if is_official else '否'}",
                    ]
                )
            }
        ]

    def _serialize_record_summary(self, record: KnowledgeRecord) -> dict[str, Any]:
        snippet = ""
        if record.segments:
            snippet = _text(record.segments[0].content)[:180]
        return {
            "record_id": str(record.id),
            "source_type": record.source_type,
            "title": record.title,
            "platform": record.platform,
            "question_text": record.question_text,
            "competitor_name": record.competitor_name,
            "domain": record.domain,
            "occurred_at": record.occurred_at.isoformat(),
            "snippet": snippet,
        }

    def _serialize_export_row(self, record: KnowledgeRecord) -> dict[str, Any]:
        payload = record.payload if isinstance(record.payload, dict) else {}
        metadata = (
            record.extra_metadata if isinstance(record.extra_metadata, dict) else {}
        )
        citation = (
            payload.get("citation") if isinstance(payload.get("citation"), dict) else {}
        )

        snippet = _compact_for_export(record.search_text, 220)
        if record.source_type == "fetch_answer":
            answer = (
                payload.get("answer") if isinstance(payload.get("answer"), dict) else {}
            )
            snippet = _compact_for_export(
                answer.get("content") or record.search_text, 220
            )
        elif record.source_type == "fetch_citation":
            snippet = _compact_for_export(
                _join_non_empty(
                    [
                        payload.get("question_text"),
                        citation.get("title"),
                        citation.get("summary"),
                        citation.get("snippet"),
                    ]
                )
                or record.search_text,
                220,
            )

        return {
            "occurred_at": record.occurred_at.strftime("%Y-%m-%d %H:%M"),
            "source_type": _source_type_label(record.source_type),
            "platform": _text(record.platform),
            "competitor_name": _text(record.competitor_name),
            "question_text": _text(record.question_text),
            "title": _text(record.title),
            "domain": _text(record.domain),
            "site_name": _text(
                metadata.get("site_name")
                or citation.get("site_name")
                or citation.get("source")
            ),
            "is_official": (
                "是"
                if bool(metadata.get("is_official") or payload.get("is_official"))
                else "否"
            ),
            "snippet": snippet,
            "url": _text(metadata.get("url") or citation.get("url")),
        }


def _compact_for_export(value: Any, limit: int = 220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
