"""Snapshot 生命周期管理服务。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.workflow.a5.canonical import normalize_report_kind


class SnapshotService:
    """集中管理 Snapshot 的创建、查询和趋势分析。

    设计原则:
    - 单一职责: 所有 Snapshot 数据库操作归口于此
    - A5 node 调用一次 create_completed_snapshot() 即完成写入
    - 可独立测试（注入 AsyncSession）
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_completed_snapshot(
        self,
        *,
        entity_id: str | UUID,
        session_id: str | UUID | None,
        metrics: dict[str, Any],
        report_data: dict[str, Any],
        competitor_metrics: dict[str, Any] | None = None,
        fetch_results_summary: list[dict] | None = None,
        is_degraded: bool = False,
        triggered_by: str = "manual",
        snapshot_type: str = "legacy",
        monitoring_metadata: dict[str, Any] | None = None,
    ) -> AnalysisSnapshot:
        """在 metrics 计算完成后一次性创建 Snapshot。

        不存在 RUNNING 状态，直接创建 COMPLETED/PARTIAL。

        Args:
            entity_id: 品牌实体 ID（str 会自动转 UUID）
            session_id: 触发分析的会话 ID
            metrics: A5 计算的核心指标
            report_data: LLM 生成的报告数据
            competitor_metrics: 竞品指标（可选）
            fetch_results_summary: 抓取结果摘要（可选）
            is_degraded: 是否为降级报告
            triggered_by: 触发方式

        Returns:
            创建的 AnalysisSnapshot 实例
        """
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        if session_id is not None and isinstance(session_id, str):
            session_id = UUID(session_id)

        breakdown = metrics.get("bwvs_breakdown", {})

        normalized_snapshot_type = normalize_report_kind(snapshot_type)
        artifact_kind = (
            report_data.get("artifact_kind")
            if isinstance(report_data, dict) and report_data.get("artifact_kind")
            else "geo_report"
        )
        raw_data = {
            "artifact_kind": artifact_kind,
            "report_kind": normalized_snapshot_type,
            "metrics": metrics,
            "report_data": report_data,
            "competitor_metrics": competitor_metrics,
            "fetch_results_summary": fetch_results_summary,
            "metric_bundle": report_data.get("metric_bundle") if isinstance(report_data, dict) else None,
            "comparison_bundle": report_data.get("comparison_bundle") if isinstance(report_data, dict) else None,
            "dashboard_projection": report_data.get("dashboard_projection") if isinstance(report_data, dict) else None,
            "sections": report_data.get("sections") if isinstance(report_data, dict) else None,
        }
        if monitoring_metadata:
            raw_data["monitoring"] = monitoring_metadata

        snapshot = AnalysisSnapshot(
            entity_id=entity_id,
            session_id=session_id,
            status=SnapshotStatus.PARTIAL if is_degraded else SnapshotStatus.COMPLETED,
            bwvs_index=metrics.get("bwvs_index"),
            mention_rate=metrics.get("mention_rate"),
            sentiment_score=breakdown.get("sentiment_score"),
            coverage_score=breakdown.get("coverage_score"),
            citation_score=breakdown.get("citation_score"),
            total_questions=metrics.get("total_questions", 0),
            total_mentions=metrics.get("total_mentions", 0),
            platforms_success=len([
                p for p in metrics.get("platform_breakdown", {}).values()
                if isinstance(p, dict) and p.get("success", 0) > 0
            ]),
            raw_data=raw_data,
            triggered_by=triggered_by,
            snapshot_type=normalized_snapshot_type,
            completed_at=datetime.now(timezone.utc),
        )

        self.db.add(snapshot)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def get_previous_snapshot(
        self,
        entity_id: str | UUID,
        exclude_snapshot_id: UUID | None = None,
        snapshot_type: str | None = None,
    ) -> AnalysisSnapshot | None:
        """获取同一 Entity 的上一个已完成 Snapshot（用于计算 delta）。

        Args:
            entity_id: 品牌实体 ID
            exclude_snapshot_id: 排除的 Snapshot ID（通常为当前新创建的）

        Returns:
            上一个 Snapshot 或 None
        """
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        conditions = [
            AnalysisSnapshot.entity_id == entity_id,
            AnalysisSnapshot.status.in_([
                SnapshotStatus.COMPLETED,
                SnapshotStatus.PARTIAL,
            ]),
        ]
        if exclude_snapshot_id:
            conditions.append(AnalysisSnapshot.id != exclude_snapshot_id)
        if snapshot_type:
            conditions.append(AnalysisSnapshot.snapshot_type == snapshot_type)

        query = (
            select(AnalysisSnapshot)
            .where(*conditions)
            .order_by(desc(AnalysisSnapshot.created_at))
            .limit(1)
        )
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def get_trend(
        self,
        entity_id: str | UUID,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """获取 BWVS 趋势数据（时间序列）。

        Args:
            entity_id: 品牌实体 ID
            limit: 最大返回条数，默认 100

        Returns:
            按时间正序排列的趋势数据点列表
        """
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        query = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == entity_id,
                AnalysisSnapshot.status.in_([
                    SnapshotStatus.COMPLETED,
                    SnapshotStatus.PARTIAL,
                ]),
            )
            .order_by(AnalysisSnapshot.created_at)
            .limit(limit)
        )
        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        return [
            {
                "date": snap.created_at.strftime("%Y-%m-%d"),
                "bwvs_index": round(snap.bwvs_index, 2) if snap.bwvs_index is not None else None,
                "mention_rate": round(snap.mention_rate, 4) if snap.mention_rate is not None else None,
                "sentiment_score": round(snap.sentiment_score, 2) if snap.sentiment_score is not None else None,
                "coverage_score": round(snap.coverage_score, 2) if snap.coverage_score is not None else None,
                "citation_score": round(snap.citation_score, 2) if snap.citation_score is not None else None,
                "snapshot_id": str(snap.id),
            }
            for snap in snapshots
        ]

    async def list_snapshots(
        self,
        entity_id: str | UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """分页获取某品牌的所有快照列表。

        Args:
            entity_id: 品牌实体 ID
            page: 页码（从 1 开始）
            page_size: 每页条数

        Returns:
            包含 snapshots, total, page, page_size 的字典
        """
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)

        from sqlalchemy import func

        # Count total
        count_query = (
            select(func.count())
            .select_from(AnalysisSnapshot)
            .where(AnalysisSnapshot.entity_id == entity_id)
        )
        count_result = await self.db.execute(count_query)
        total = count_result.scalar() or 0

        # Fetch page
        offset = (page - 1) * page_size
        query = (
            select(AnalysisSnapshot)
            .where(AnalysisSnapshot.entity_id == entity_id)
            .order_by(desc(AnalysisSnapshot.created_at))
            .offset(offset)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        return {
            "snapshots": [self._snapshot_to_dict(s) for s in snapshots],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def get_snapshot(
        self,
        snapshot_id: str | UUID,
    ) -> AnalysisSnapshot | None:
        """获取快照详情（含 raw_data）。

        Args:
            snapshot_id: 快照 ID

        Returns:
            AnalysisSnapshot 实例或 None
        """
        if isinstance(snapshot_id, str):
            snapshot_id = UUID(snapshot_id)

        query = select(AnalysisSnapshot).where(AnalysisSnapshot.id == snapshot_id)
        result = await self.db.execute(query)
        return result.scalar_one_or_none()

    async def compare_snapshots(
        self,
        base_id: str | UUID,
        target_id: str | UUID,
        entity_id: str | UUID | None = None,
    ) -> dict[str, Any] | None:
        """对比两个快照，计算 delta。

        base 是基准快照（通常是旧的），target 是对比目标（通常是新的）。
        delta = target - base

        Args:
            base_id: 基准快照 ID
            target_id: 对比目标快照 ID
            entity_id: 可选，验证快照归属的品牌实体 ID

        Returns:
            包含 base, target, delta 的字典，或 None（找不到快照时）
        """
        base = await self.get_snapshot(base_id)
        target = await self.get_snapshot(target_id)

        if not base or not target:
            return None

        # Validate entity_id ownership if provided
        if entity_id is not None:
            if isinstance(entity_id, str):
                entity_id = UUID(entity_id)
            if base.entity_id != entity_id or target.entity_id != entity_id:
                return None

        def _calc_delta(base_val: float | None, target_val: float | None) -> dict[str, Any]:
            if base_val is None or target_val is None:
                return {"value": 0, "percentage": 0, "direction": "stable"}
            delta = target_val - base_val
            pct = (delta / base_val * 100) if base_val != 0 else 0
            direction = "up" if delta > 0 else "down" if delta < 0 else "stable"
            return {
                "value": round(delta, 2),
                "percentage": round(pct, 1),
                "direction": direction,
            }

        return {
            "base": self._snapshot_to_dict(base),
            "target": self._snapshot_to_dict(target),
            "delta": {
                "bwvs_index": _calc_delta(base.bwvs_index, target.bwvs_index),
                "mention_rate": _calc_delta(base.mention_rate, target.mention_rate),
                "sentiment_score": _calc_delta(base.sentiment_score, target.sentiment_score),
                "coverage_score": _calc_delta(base.coverage_score, target.coverage_score),
                "citation_score": _calc_delta(base.citation_score, target.citation_score),
            },
        }

    @staticmethod
    def _snapshot_to_dict(snap: AnalysisSnapshot) -> dict[str, Any]:
        """Convert snapshot to API-friendly dict."""
        return {
            "id": str(snap.id),
            "entity_id": str(snap.entity_id),
            "session_id": str(snap.session_id) if snap.session_id else None,
            "status": snap.status.value if snap.status else "completed",
            "bwvs_index": snap.bwvs_index,
            "mention_rate": snap.mention_rate,
            "sentiment_score": snap.sentiment_score,
            "coverage_score": snap.coverage_score,
            "citation_score": snap.citation_score,
            "platforms_total": snap.platforms_total,
            "platforms_success": snap.platforms_success,
            "total_questions": snap.total_questions,
            "total_mentions": snap.total_mentions,
            "triggered_by": snap.triggered_by,
            "snapshot_type": snap.snapshot_type,
            "created_at": snap.created_at.isoformat() if snap.created_at else None,
            "completed_at": snap.completed_at.isoformat() if snap.completed_at else None,
        }
