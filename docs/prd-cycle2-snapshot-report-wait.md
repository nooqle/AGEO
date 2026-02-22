# PRD: Cycle 2 -- Snapshot 模型 + 报告深度增强 + 等待体验优化

> **文档状态**: Reviewed
> **作者**: Marty Cagan (产品经理)
> **创建日期**: 2026-02-20
> **修订日期**: 2026-02-21
> **优先级**: P1
> **依赖文档**:
>   - `D:\AGEO\docs\reform-plan.md` (改造方案 v2.0)
>   - `D:\AGEO\docs\prd-p0-reliability-bwvs.md` (Cycle 1 PRD)
>   - `D:\AGEO\docs\ux-design-p0-bwvs-resilience.md` (Cycle 1 UX 设计)

### 评审记录

| 日期 | 评审人 | 角色 | 结论 | 修正项 |
|------|--------|------|------|--------|
| 2026-02-21 | Martin Fowler | 架构师 | 有条件通过 | C1-C5 共 5 项修正 |
| 2026-02-21 | John Carmack | 技术负责人 | 有条件通过 | T1-T7 共 7 项修正 |

> 本版本已整合两位评审人全部 12 项修正意见。详见附录 D "评审修正汇总"。

---

## 一、背景与动机

### 1.1 我们在解决什么问题?

Cycle 1 完成了端到端可靠性修复和 BWVS v2 多维评分，让分析流水线从"勉强能跑"提升到了"基本可用"。但 E2E 测试评估暴露了三个核心体验短板：

1. **分析过程等待体验差**: 整个分析链路 (A1->A5) 需要 1-5 分钟，用户在此期间看到的是一个旋转动画和粗粒度的步骤列表 (MiniProgress)，没有阶段性产出可看，也不知道系统正在做什么、还要等多久。
2. **报告内容浅，决策参考价值不足**: A5 报告只有基础指标和模板化的 SWOT，缺乏行业背景洞察、竞品深度对比、按平台逐一分析、具体可执行的优化建议。品牌客户拿到报告后仍然不知道"下一步该做什么"。
3. **每次分析是独立孤岛**: 分析结果存储在 Message.output_data 的 JSON 字段中，每次分析都覆盖之前的展示。用户无法看到上次分析 BWVS 是多少、这次变了多少、趋势是上升还是下降。Dashboard 的 visibility trend 虽然尝试聚合历史数据，但逻辑粗糙且 UI 无明确的快照对比入口。

### 1.2 谁有这个问题? 有多痛?

**目标用户**: 品牌客户的市场部/运营部/产品部人员

**痛点程度**: Hair on fire (高频、阻塞性)

- **等待体验**: 用户评估中"可用性"评分仅 5.5，"好用性"仅 4.0。核心原因是等待焦虑 -- 3-5 分钟的黑盒等待让用户怀疑系统是否在工作、是否会出错、是否值得等。这是最大的流失风险。
- **报告深度**: 品牌客户向管理层汇报时，模板化的"品牌知名度较高"式结论没有说服力。他们需要"你的品牌在 DeepSeek 上的产品推荐类问题中提及率仅 15%，而竞品 X 达到 60%，建议优先优化 XX 方向的内容"这种精度。
- **历史趋势**: 品牌 AEO 优化是持续过程，单次分析如同"一次性体检"，没有复诊记录就无法评估优化效果。

### 1.3 他们现在怎么解决?

- 等待体验: 反复刷新页面，或切到别的标签页等着，不确定何时完成
- 报告深度: 手动整理原始数据，结合行业经验撰写更深入的分析报告
- 历史趋势: 手动截图/导出每次分析结果，用 Excel 做对比表

### 1.4 假设与预期

**假设**: 通过 Snapshot 快照模型 + 报告深度增强 + 等待体验优化三个维度的改进，可以将综合体验评分从 5.5 提升到 7.5+。

**预期效果**:

| 指标 | 当前 | 目标 |
|------|------|------|
| 综合体验评分 (产品) | 5.5 | 7.5+ |
| 综合体验评分 (UX) | 6.0 | 7.5+ |
| "好用性"评分 | 4.0 | 7.0+ |
| 用户在等待期间的流失率 | 高 (无数据) | 显著降低 |
| 报告可直接用于汇报的比例 | ~10% (估) | ~50% |
| 用户能看到历史趋势 | 否 | 是 |

---

## 二、功能一: Snapshot 快照模型

### 2.1 Problem Statement

每次品牌分析的结果 (BWVS 分数、各维度得分、平台数据等) 存储在 `Message.output_data` JSON 中，与 Session/Message 强耦合。没有独立的快照实体来表示"某品牌在某时刻的分析结果"。这导致：

1. 历史数据查询需要遍历所有 OUTPUT 类型消息并解析 JSON -- 性能差且逻辑脆弱
2. 无法简洁地做"本次 vs 上次"对比
3. Dashboard 的趋势图数据来源不可靠（从 output_data JSON 中提取，字段不稳定）
4. 未来的定时监测 (P2-2) 没有存储归属

### 2.2 Target User

- 所有使用 Specta AI 的品牌客户
- 特别是需要定期汇报品牌 AI 可见性变化的市场部人员

### 2.3 Success Metrics

- **Primary**: 用户能在 Dashboard 看到品牌 BWVS 的历史趋势折线图（至少 2 个快照）
- **Secondary**: 报告中包含"vs 上次"的对比数据
- **Guardrail**: 新增快照不影响现有 Message/Session 模型，不破坏已有数据

### 2.4 数据模型: AnalysisSnapshot

**新增文件**: `aeo-platform/backend/app/models/snapshot.py`

```python
"""Analysis Snapshot model -- 每次品牌分析结果的时间快照。"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.session import Session


class JSONText(TypeDecorator):
    """将 Python dict 自动序列化为 JSON 字符串存储在 Text 列中。

    写入时传 dict，读出时拿 dict，消除手动 json.dumps/loads。
    兼容 PostgreSQL 和 SQLite。
    [评审修正 C1]
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: Any | None, dialect: Any) -> str | None:
        if value is not None:
            return json.dumps(value, ensure_ascii=False)
        return None

    def process_result_value(self, value: str | None, dialect: Any) -> Any | None:
        if value is not None:
            return json.loads(value)
        return None


class SnapshotStatus(str, PyEnum):
    """Snapshot lifecycle status.

    [评审修正 C2/T4] 删除 RUNNING 状态。
    Snapshot 在 metrics 计算完成后一次性创建，不存在"进行中"状态。
    - A5 失败时不创建 Snapshot（错误记录在 Message/state 中）。
    - 等待体验已有 stage_result + execution_progress 覆盖。
    """
    COMPLETED = "completed"   # 分析完成
    PARTIAL = "partial"       # 部分完成（LLM 降级场景）


class AnalysisSnapshot(Base):
    """每次品牌分析的时间快照。

    一个 Entity 可以有多个 Snapshot（时间序列）。
    每个 Snapshot 关联一个 Session（触发分析的对话）。

    核心字段独立列存储（用于查询/排序/趋势聚合），
    完整原始数据存储在 raw_data JSON 字段中（JSONText 自动序列化）。
    """

    __tablename__ = "analysis_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[SnapshotStatus] = mapped_column(
        Enum(SnapshotStatus),
        default=SnapshotStatus.COMPLETED,
        nullable=False,
    )

    # --- 核心指标（独立列，用于查询/排序/趋势） ---
    bwvs_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    mention_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    coverage_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    citation_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # 平台覆盖统计
    platforms_total: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    platforms_success: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # 问题/提及统计
    total_questions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_mentions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # --- 完整原始数据（JSONText 自动 dict <-> JSON 转换）[评审修正 C1] ---
    # 包含: metrics, bwvs_breakdown, platform_breakdown, sentiment_distribution,
    #        competitor_metrics, report_data, fetch_results_summary 等
    raw_data: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # --- 元数据 ---
    triggered_by: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )  # "manual" | "scheduled" | "api"

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    # [评审修正: 共同建议] backref 改为 "analysis_snapshots" 避免与其他名称混淆
    entity: Mapped["Entity"] = relationship("Entity", backref="analysis_snapshots")
    session: Mapped["Session | None"] = relationship("Session", backref="analysis_snapshots")

    def __repr__(self) -> str:
        return (
            f"<AnalysisSnapshot(id={self.id}, entity={self.entity_id}, "
            f"bwvs={self.bwvs_index}, status={self.status})>"
        )
```

**关键设计决策**:

1. **核心指标独立列**: `bwvs_index`, `mention_rate`, `sentiment_score`, `coverage_score`, `citation_score` 作为独立列，方便 SQL 查询排序和趋势聚合（`SELECT bwvs_index, created_at FROM snapshots WHERE entity_id = ? ORDER BY created_at`），无需每次解析 JSON。
2. **raw_data 使用 JSONText TypeDecorator** [评审修正 C1]: 写入时传 dict，读出时拿 dict，消除手动 `json.dumps/loads`。底层存储为 Text 列（兼容 PostgreSQL 和 SQLite）。
3. **无 RUNNING 状态** [评审修正 C2/T4]: Snapshot 在 metrics 计算完成后一次性创建，状态直接为 COMPLETED 或 PARTIAL（LLM 降级时）。A5 失败时不创建 Snapshot。等待体验由 `stage_result` + `execution_progress` 事件覆盖，无需 Snapshot 介入。这将原设计的 3 次数据库操作降为 1 次。
4. **与 Entity 一对多**: 一个品牌实体可以有多个快照，自然形成时间序列。

**数据库 Migration**:

> **[评审修正 T7] P0 前置步骤**: 在执行 `alembic revision` 之前，必须先完成 `models/__init__.py` 更新（导出 AnalysisSnapshot），否则 Alembic 的 `--autogenerate` 无法检测到新模型。

```python
# 步骤 1 (前置): 更新 models/__init__.py（见下方）
# 步骤 2: alembic revision --autogenerate -m "add_analysis_snapshots_table"
# 步骤 3: alembic upgrade head
```

**[评审修正 T1] SQLite 兼容性说明**:

当前开发/测试环境使用 SQLite，生产环境使用 PostgreSQL。Migration 脚本需注意以下类型映射：

| PostgreSQL 类型 | SQLite 兼容处理 |
|----------------|----------------|
| `UUID(as_uuid=True)` | 自动降级为 `CHAR(32)` |
| `Enum(SnapshotStatus)` | 自动降级为 `VARCHAR` |

SQLAlchemy 的 `UUID` 和 `Enum` 类型在 SQLite 下会自动处理降级，无需手动 `with_variant()`。但需确认 Alembic 生成的迁移脚本在两种数据库下均可执行。

**models/__init__.py 更新**:

```python
from app.models.snapshot import AnalysisSnapshot

__all__ = [
    "Session", "Message", "BrandProfile", "User",
    "Entity", "FileMetadata", "AnalysisSnapshot",
]
```

### 2.5 SnapshotService 服务类 [评审修正 C3]

**新增文件**: `aeo-platform/backend/app/services/snapshot_service.py`

集中管理 Snapshot 生命周期，提高可测试性。A5 node 中通过单次调用完成 Snapshot 创建，不再分散数据库操作。

```python
"""Snapshot 生命周期管理服务。[评审修正 C3]"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.snapshot import AnalysisSnapshot, SnapshotStatus


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
        session_id: str | UUID,
        metrics: dict[str, Any],
        report_data: dict[str, Any],
        competitor_metrics: dict[str, Any] | None = None,
        fetch_results_summary: list[dict] | None = None,
        is_degraded: bool = False,
        triggered_by: str = "manual",
    ) -> AnalysisSnapshot:
        """在 metrics 计算完成后一次性创建 Snapshot。

        [评审修正 C2/T4] 不再有 RUNNING 状态，直接创建 COMPLETED/PARTIAL。
        [评审修正 T3] entity_id 从 str 转换为 UUID。

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
        # [评审修正 T3] entity_id 类型转换
        if isinstance(entity_id, str):
            entity_id = UUID(entity_id)
        if isinstance(session_id, str):
            session_id = UUID(session_id)

        breakdown = metrics.get("bwvs_breakdown", {})

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
            # [评审修正 C1] raw_data 直接传 dict，JSONText 自动序列化
            raw_data={
                "metrics": metrics,
                "report_data": report_data,
                "competitor_metrics": competitor_metrics,
                "fetch_results_summary": fetch_results_summary,
            },
            triggered_by=triggered_by,
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

        [评审修正: 共同建议] 默认 LIMIT 100。

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
                "bwvs_index": round(snap.bwvs_index, 2) if snap.bwvs_index else None,
                "mention_rate": round(snap.mention_rate, 4) if snap.mention_rate else None,
                "sentiment_score": round(snap.sentiment_score, 2) if snap.sentiment_score else None,
                "coverage_score": round(snap.coverage_score, 2) if snap.coverage_score else None,
                "citation_score": round(snap.citation_score, 2) if snap.citation_score else None,
                "snapshot_id": str(snap.id),
            }
            for snap in snapshots
        ]
```

### 2.6 Snapshot 写入逻辑

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py` -- `a5_analytics_node()` 函数

**写入时机** [评审修正 C2/T4]:

Snapshot 在 `_calculate_metrics()` 成功后、通过 `SnapshotService.create_completed_snapshot()` 一次性创建。不在 A5 开始时创建，不存在 RUNNING 状态。

- **A5 metrics 计算成功 + LLM 报告成功**: 创建 Snapshot，status = COMPLETED
- **A5 metrics 计算成功 + LLM 报告降级**: 创建 Snapshot，status = PARTIAL
- **A5 metrics 计算失败**: 不创建 Snapshot（错误记录在 Message/state 中）

> [评审修正 C4] **前置条件**: entity_id 必须在 A1 完成后正确写入 AgentState。A1 node 在识别品牌并获取/创建 Entity 后，将 entity_id 写入 state。

**伪代码**:

```python
# nodes_a5.py -- a5_analytics_node() 内部

from app.services.snapshot_service import SnapshotService
from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
from app.core.database import AsyncSessionLocal

async def a5_analytics_node(state: AgentState) -> Command:
    session_id = state["session_id"]
    entity_id = state.get("entity_id")  # [评审修正 C4] A1 完成后写入 state
    brand_profile = state.get("brand_profile") or {}
    fetch_results = state.get("fetch_results") or []

    try:
        metrics = _calculate_metrics(fetch_results, brand_profile)

        # LLM 报告生成（设置 max_tokens=8192）[评审修正 T2]
        report_data = await _generate_report(
            brand_profile, metrics, fetch_results,
            max_tokens=8192,
        )

        # [评审修正 T2] 容错: 规范化报告数据，处理 LLM 输出缺失字段
        report_data = _normalize_report_data(report_data)

        is_degraded = report_data.get("_degraded", False)

        # [评审修正 C2/C3] 一次性创建 Snapshot（仅在 entity_id 存在时）
        snapshot = None
        if entity_id:
            async with AsyncSessionLocal() as db:
                service = SnapshotService(db)
                snapshot = await service.create_completed_snapshot(
                    entity_id=entity_id,    # [评审修正 T3] str -> UUID 由 service 内部处理
                    session_id=session_id,
                    metrics=metrics,
                    report_data=report_data,
                    competitor_metrics=competitor_metrics,
                    fetch_results_summary=fetch_results_summary,
                    is_degraded=is_degraded,
                )

        # 查询上次 Snapshot 计算 delta
        delta_vs_previous = None
        if entity_id and snapshot:
            async with AsyncSessionLocal() as db:
                service = SnapshotService(db)
                previous = await service.get_previous_snapshot(
                    entity_id=entity_id,
                    exclude_snapshot_id=snapshot.id,
                )
                if previous and previous.bwvs_index is not None:
                    current_bwvs = metrics.get("bwvs_index", 0)
                    prev_bwvs = previous.bwvs_index
                    delta_value = current_bwvs - prev_bwvs
                    delta_pct = (delta_value / prev_bwvs * 100) if prev_bwvs else 0
                    delta_vs_previous = {
                        "bwvs_index": {
                            "current": round(current_bwvs, 2),
                            "previous": round(prev_bwvs, 2),
                            "delta": round(delta_value, 2),
                            "percentage": round(delta_pct, 1),
                            "direction": (
                                "up" if delta_value > 0
                                else "down" if delta_value < 0
                                else "stable"
                            ),
                        },
                        "previous_date": previous.created_at.strftime("%Y-%m-%d"),
                        "previous_snapshot_id": str(previous.id),
                    }

        # [评审修正 T6] save_and_send_artifact 中透传所有新增字段
        await save_and_send_artifact(
            session_id=session_id,
            output_type="report",
            data={
                # ... 现有字段 ...
                "metrics": metrics,
                "report_data": report_data,
                "delta_vs_previous": delta_vs_previous,
                # [评审修正 T6] 新增字段显式透传
                "industry_insights": report_data.get("industry_insights"),
                "platform_analysis": report_data.get("platform_analysis", []),
                "competitor_deep_analysis": report_data.get("competitor_deep_analysis"),
                "actionable_recommendations": report_data.get("actionable_recommendations", []),
                "risk_alerts": report_data.get("risk_alerts", []),
            },
        )

    except Exception as e:
        # [评审修正 C2] A5 失败时不创建 Snapshot
        # 错误信息记录在 Message/state 中，由现有错误处理机制覆盖
        raise
```

**[评审修正 T2] _normalize_report_data 容错函数**:

```python
def _normalize_report_data(report_data: dict[str, Any]) -> dict[str, Any]:
    """规范化 LLM 输出的报告数据，处理缺失字段。

    [评审修正 T2] LLM 输出可能漏掉新增的 optional 字段，
    此函数确保所有字段都有安全的默认值。

    Args:
        report_data: LLM 原始输出（已解析为 dict）

    Returns:
        规范化后的 report_data
    """
    # 必需字段: 如果缺失则给合理默认值
    report_data.setdefault("executive_summary", "分析已完成。")
    report_data.setdefault("key_findings", [])
    report_data.setdefault("strengths", [])
    report_data.setdefault("weaknesses", [])
    report_data.setdefault("opportunities", [])
    report_data.setdefault("threats", [])
    report_data.setdefault("recommendations", [])

    # [评审修正 T2] 新增字段标记为 optional，缺失时给 None/空列表
    report_data.setdefault("industry_insights", None)
    report_data.setdefault("platform_analysis", [])
    report_data.setdefault("competitor_deep_analysis", None)
    report_data.setdefault("actionable_recommendations", [])
    report_data.setdefault("risk_alerts", [])

    return report_data
```

### 2.7 Snapshot API

**新增文件**: `aeo-platform/backend/app/api/v1/snapshots.py`

| Method | Endpoint | 描述 |
|--------|---------|------|
| GET | `/api/v1/entities/{entity_id}/snapshots` | 获取某品牌的所有快照列表（分页） |
| GET | `/api/v1/entities/{entity_id}/snapshots/latest` | 获取最新快照 |
| GET | `/api/v1/snapshots/{snapshot_id}` | 获取快照详情（含 raw_data） |
| GET | `/api/v1/entities/{entity_id}/snapshots/compare?base=uuid1&target=uuid2` | 对比两个快照 [评审修正 C5] |
| GET | `/api/v1/entities/{entity_id}/snapshots/trend` | 获取 BWVS 趋势数据（默认 LIMIT 100）[评审修正: 共同建议] |

> **[评审修正 C5]** compare 端点参数从 `?ids=id1,id2` 改为 `?base=uuid1&target=uuid2`，语义更清晰: base 是基准快照（通常是旧的），target 是对比目标（通常是新的），delta = target - base。

**快照列表响应**:

```json
{
  "snapshots": [
    {
      "id": "uuid",
      "entity_id": "uuid",
      "status": "completed",
      "bwvs_index": 52.3,
      "mention_rate": 0.65,
      "sentiment_score": 72.0,
      "coverage_score": 75.0,
      "citation_score": 45.0,
      "platforms_success": 3,
      "platforms_total": 4,
      "total_questions": 48,
      "total_mentions": 31,
      "triggered_by": "manual",
      "created_at": "2026-02-20T10:30:00Z",
      "completed_at": "2026-02-20T10:33:42Z"
    }
  ],
  "total": 5,
  "page": 1,
  "page_size": 20
}
```

**趋势数据响应** (`/trend`):

```json
{
  "trend": [
    {
      "date": "2026-02-10",
      "bwvs_index": 35.4,
      "mention_rate": 0.42,
      "sentiment_score": 50.0,
      "coverage_score": 50.0,
      "citation_score": 50.0,
      "snapshot_id": "uuid"
    },
    {
      "date": "2026-02-17",
      "bwvs_index": 48.2,
      "mention_rate": 0.58,
      "sentiment_score": 65.5,
      "coverage_score": 75.0,
      "citation_score": 42.0,
      "snapshot_id": "uuid"
    }
  ]
}
```

**对比数据响应** (`/compare?base=uuid1&target=uuid2`) [评审修正 C5]:

```json
{
  "base": { "id": "uuid-1", "created_at": "...", "bwvs_index": 35.4, "...": "..." },
  "target": { "id": "uuid-2", "created_at": "...", "bwvs_index": 48.2, "...": "..." },
  "delta": {
    "bwvs_index": { "value": 12.8, "percentage": 36.2, "direction": "up" },
    "mention_rate": { "value": 0.16, "percentage": 38.1, "direction": "up" },
    "sentiment_score": { "value": 15.5, "percentage": 31.0, "direction": "up" },
    "coverage_score": { "value": 25.0, "percentage": 50.0, "direction": "up" },
    "citation_score": { "value": -8.0, "percentage": -16.0, "direction": "down" }
  }
}
```

### 2.8 analytics_service.py 适配

**影响文件**: `aeo-platform/backend/app/services/analytics_service.py`

当前 `_get_all_outputs()` 从 Message 表中遍历 OUTPUT 类型消息并解析 JSON 来获取指标数据。有了 Snapshot 表后，趋势数据应优先从 Snapshot 表读取。

**修改策略**: 渐进式迁移，不破坏现有逻辑。

```python
# analytics_service.py

async def get_visibility_data(
    self, brand_id: str | None, date_range: str
) -> dict[str, Any]:
    """Get visibility trend data.

    优先从 AnalysisSnapshot 表读取（结构化、快速）。
    如果 Snapshot 数据不足，回退到 Message.output_data 解析（兼容旧数据）。
    """
    visibility_points = []

    # 1) 优先从 Snapshot 表读取
    if brand_id:
        from app.models.snapshot import AnalysisSnapshot, SnapshotStatus
        query = (
            select(AnalysisSnapshot)
            .where(
                AnalysisSnapshot.entity_id == UUID(brand_id),
                AnalysisSnapshot.status.in_([
                    SnapshotStatus.COMPLETED,
                    SnapshotStatus.PARTIAL,
                ]),
            )
            .order_by(AnalysisSnapshot.created_at)
            .limit(100)  # [评审修正: 共同建议] 默认 LIMIT 100
        )
        result = await self.db.execute(query)
        snapshots = result.scalars().all()

        for snap in snapshots:
            if snap.bwvs_index is not None:
                visibility_points.append({
                    "date": snap.created_at.strftime("%Y-%m-%d"),
                    "score": round(snap.bwvs_index, 2),
                    "snapshot_id": str(snap.id),
                })

    # 2) 如果 Snapshot 数据不足，回退到旧逻辑
    if len(visibility_points) < 2:
        outputs = await self._get_all_outputs(brand_id=brand_id)
        for output in outputs:
            metrics = self._extract_metrics(output)
            if metrics:
                created_at = output.get("_created_at", "")
                bwvs = metrics.get("bwvs_index", 0)
                if bwvs and created_at:
                    visibility_points.append({
                        "date": created_at[:10],
                        "score": round(bwvs, 2),
                    })

    return {"visibility": visibility_points}
```

### 2.9 前端: Dashboard 趋势图增强

**影响文件**: `D:\AGEO\frontend\src\components\dashboard\DashboardPage.tsx`

**当前状态**: Dashboard 已有 VisibilityChart 展示 visibility trend 折线图，数据来自 `/api/v1/analytics/visibility` 接口。

**增强**:

1. 折线图 X 轴标注快照日期，hover 显示快照详情 (BWVS 各维度)
2. 支持切换维度: BWVS 总分 / 提及率 / 情感得分 / 覆盖度
3. 最新 vs 上一次快照的 delta 展示 (如 BWVS +12.8, +36.2%)

**新增 TypeScript 类型**:

```typescript
// types/snapshot.ts

export interface SnapshotSummary {
  id: string;
  entity_id: string;
  status: 'completed' | 'partial';  // [评审修正 C2] 删除 'running' 和 'failed'
  bwvs_index: number | null;
  mention_rate: number | null;
  sentiment_score: number | null;
  coverage_score: number | null;
  citation_score: number | null;
  platforms_success: number;
  platforms_total: number;
  total_questions: number;
  total_mentions: number;
  triggered_by: string;
  created_at: string;
  completed_at: string | null;
}

export interface SnapshotTrendPoint {
  date: string;
  bwvs_index: number;
  mention_rate: number;
  sentiment_score: number;
  coverage_score: number;
  citation_score: number;
  snapshot_id: string;
}

export interface SnapshotDelta {
  value: number;
  percentage: number;
  direction: 'up' | 'down' | 'stable';
}

export interface SnapshotCompare {
  base: SnapshotSummary;      // [评审修正 C5] 从 snapshots[] 改为 base/target
  target: SnapshotSummary;
  delta: {
    bwvs_index: SnapshotDelta;
    mention_rate: SnapshotDelta;
    sentiment_score: SnapshotDelta;
    coverage_score: SnapshotDelta;
    citation_score: SnapshotDelta;
  };
}
```

### 2.10 前端: 报告中的"vs 上次"对比

**影响文件**: `D:\AGEO\frontend\src\components\canvas\contents\ReportContent.tsx`

在 Score Card 区域，如果存在上一次快照数据，展示 delta 指示器:

```
+----------------------------------------------------------+
|   52.3         BWVS 指数                                   |
|   (+12.8 / +36.2%)  vs 2026-02-17                         |
|   [=====================          ] 良好                    |
+----------------------------------------------------------+
```

**实现方式**: A5 通过 SnapshotService.get_previous_snapshot() 查询上一个 Snapshot，计算 delta 并写入 artifact data（见 2.6 伪代码）。

**前端渲染** (ReportContent.tsx):

```tsx
{/* Delta vs previous snapshot */}
{deltaVsPrevious && (
  <div className="flex items-center gap-2 mt-2">
    <span className={cn(
      'text-sm font-medium',
      deltaVsPrevious.bwvs_index.direction === 'up' ? 'text-emerald-400' : 'text-red-400'
    )}>
      {deltaVsPrevious.bwvs_index.direction === 'up' ? '+' : ''}
      {deltaVsPrevious.bwvs_index.delta.toFixed(1)}
    </span>
    <span className="text-xs text-[#737373]">
      ({deltaVsPrevious.bwvs_index.direction === 'up' ? '+' : ''}
      {deltaVsPrevious.bwvs_index.percentage.toFixed(1)}%)
    </span>
    <span className="text-xs text-[#525252]">
      vs {deltaVsPrevious.previous_date}
    </span>
  </div>
)}
```

### 2.11 验收标准

- [ ] **AC-1**: AnalysisSnapshot 表成功创建，Alembic migration 可执行（SQLite + PostgreSQL）
- [ ] **AC-2**: 每次完整分析 (A1->A5) 后，在 Snapshot 表中写入一条记录，status=completed
- [ ] **AC-3**: Snapshot 记录包含正确的 bwvs_index, mention_rate, sentiment_score, coverage_score, citation_score
- [ ] **AC-4**: `/api/v1/entities/{id}/snapshots` 返回按时间倒序排列的快照列表
- [ ] **AC-5**: `/api/v1/entities/{id}/snapshots/trend` 返回时间序列趋势数据（默认 LIMIT 100）
- [ ] **AC-6**: 第二次分析同一品牌时，报告中显示"vs 上次"delta 数据
- [ ] **AC-7**: Dashboard 趋势图使用 Snapshot 数据源，数据正确
- [ ] **AC-8**: 降级场景下 Snapshot.status = "partial"，不影响趋势展示
- [ ] **AC-9**: entity_id 在 A1 完成后正确写入 AgentState，Snapshot 写入时可获取 [评审修正 C4]
- [ ] **AC-10**: SnapshotService 单元测试覆盖 create/get_previous/get_trend 三个方法 [评审修正 C3]
- [ ] **AC-11**: `/api/v1/entities/{id}/snapshots/compare?base=uuid1&target=uuid2` 正确返回对比数据 [评审修正 C5]

---

## 三、功能二: 报告深度增强

### 3.1 Problem Statement

当前 A5 报告的 LLM 生成部分 (`_get_a5_system_prompt` + `_build_a5_user_content`) 使用通用模板，输出内容缺乏深度:

1. **无行业背景**: 报告不知道"手机行业平均 AI 提及率是多少"，无法给出行业对标参考
2. **竞品分析浅**: 只列出竞品名称和提及率，没有"为什么竞品做得好/差"的分析
3. **平台分析缺失**: 不按平台逐一分析差异（如"DeepSeek 偏好技术类内容，Kimi 偏好生活场景"）
4. **建议不可执行**: "提升品牌知名度"式建议没有具体行动步骤
5. **无 A2 画像联动**: 当 A2 成功生成画像时，报告未利用画像数据做差异化分析

### 3.2 Target User

品牌客户的市场部/运营部人员 -- 需要拿着报告直接做决策或向管理层汇报

### 3.3 Success Metrics

- **Primary**: 报告包含行业洞察、竞品深度对比、平台差异分析、可执行建议四个维度
- **Secondary**: 报告字数从当前 ~500 字增加到 ~1500 字（有实质内容的增加，非注水）
- **Guardrail**: 报告生成时间不超过现有时间的 150%（可接受增加 50%）

### 3.4 A5 Prompt 增强

**影响文件**: `aeo-platform/backend/prompts/data_analytics_agent.md` 或 `aeo-platform/backend/app/workflow/nodes_a5.py` 中的 `_get_a5_system_prompt()` 和 `_build_a5_user_content()`

**增强方向**:

#### 3.4.1 System Prompt 增强

在 A5 system prompt 中增加以下指令模块:

```markdown
## 报告结构要求

你需要生成一份高质量的品牌 AI 可见度分析报告，包含以下章节:

### 1. 执行摘要 (executive_summary)
- 一句话核心结论（如"该品牌 AI 可见度处于行业中游水平，主要短板在产品推荐类问题覆盖不足"）
- BWVS 综合评分及评级
- 3 个最关键发现

### 2. 行业洞察 (industry_insights) [optional]
- 基于品牌所在行业，给出 AI 搜索领域的行业背景分析
- 该行业品牌在 AI 搜索中的典型表现特征
- 行业趋势和机会点
- 注意: 这部分基于你的行业知识生成，标注"基于行业经验"

### 3. 平台差异分析 (platform_analysis)
对每个有数据的平台，逐一分析:
- 品牌在该平台的表现特点
- 该平台的内容偏好和推荐逻辑特征
- 品牌在该平台的优势和短板
- 针对该平台的优化建议

### 4. 竞品深度对比 (competitor_deep_analysis)
如果有竞品数据:
- 竞品 vs 本品牌的详细对比矩阵
- 竞品做得好的原因分析（内容策略、SEO 布局等推测）
- 本品牌可借鉴的具体做法
- 差异化竞争建议

### 5. 可执行优化建议 (actionable_recommendations)
每条建议必须包含:
- 优先级 (P0/P1/P2)
- 具体行动（不是"提升品牌知名度"，而是"在知乎/百科创建 XX 内容"）
- 预期效果
- 实施难度 (低/中/高)
- 预计见效时间

### 6. SWOT 分析 (strengths, weaknesses, opportunities, threats)
- 每项 2-4 条，每条附带具体数据支撑

### 7. 风险提示 (risk_alerts) [optional]
- 品牌当前面临的 AI 可见性风险
- 竞品动态可能带来的威胁
```

> **[评审修正 T2]** industry_insights 和 risk_alerts 标记为 `[optional]`，LLM 可能因 token 预算限制不输出这些章节。`_normalize_report_data()` 会兜底处理缺失情况。

#### 3.4.2 User Content 增强

在 `_build_a5_user_content()` 中增加以下数据:

> **[评审修正 T2]** 显式设置 `max_tokens=8192`，输出 JSON schema 精简（不用嵌套示例），避免 token 预算不足。

```python
def _build_a5_user_content(
    brand_profile: dict,
    metrics: dict,
    fetch_results: list,
    competitors: list,
    marketing_personas: dict | None = None,  # 新增: A2 画像数据
    previous_snapshot: dict | None = None,     # 新增: 上次快照数据
) -> str:
    """构建 A5 LLM 的 user content。

    [评审修正 T2] JSON schema 精简，不使用嵌套示例，节省 token 预算。
    """

    sections = []

    # 1. 品牌基本信息
    sections.append(f"## 品牌信息\n{json.dumps(brand_profile, ensure_ascii=False, indent=2)}")

    # 2. 核心指标
    sections.append(f"## 核心指标\n{json.dumps(metrics, ensure_ascii=False, indent=2)}")

    # 3. 各平台原始回答（抽样，每平台最多 3 条）
    platform_samples = _extract_platform_samples(fetch_results, max_per_platform=3)
    sections.append(f"## 各平台回答样本\n{json.dumps(platform_samples, ensure_ascii=False, indent=2)}")

    # 4. 竞品数据
    if competitors:
        sections.append(f"## 竞品数据\n{json.dumps(competitors, ensure_ascii=False, indent=2)}")

    # 5. 用户画像（如果 A2 成功）
    if marketing_personas:
        personas = marketing_personas.get("user_personas", [])
        if personas:
            sections.append(f"## 目标用户画像\n{json.dumps(personas[:3], ensure_ascii=False, indent=2)}")

    # 6. 上次分析对比（如果有）
    if previous_snapshot:
        sections.append(f"## 上次分析数据 (日期: {previous_snapshot.get('date', 'N/A')})\n"
                       f"{json.dumps(previous_snapshot, ensure_ascii=False, indent=2)}")

    return "\n\n".join(sections)


def _extract_platform_samples(
    fetch_results: list, max_per_platform: int = 3
) -> dict[str, list[dict]]:
    """从 fetch_results 中提取各平台的回答样本。

    每个平台最多 max_per_platform 条，避免 context 过长。
    优先选取品牌被提及的回答。
    """
    platform_samples: dict[str, list[dict]] = {}

    for fr in fetch_results:
        for pr in fr.get("platform_results", []):
            platform = pr.get("platform", "unknown")
            if platform not in platform_samples:
                platform_samples[platform] = []

            if len(platform_samples[platform]) >= max_per_platform:
                continue

            if pr.get("success"):
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                has_mention = answer.get("has_brand_mention", False) if isinstance(answer, dict) else False

                # 截断过长的回答
                if len(content) > 500:
                    content = content[:500] + "..."

                platform_samples[platform].append({
                    "question": fr.get("question", {}).get("text", ""),
                    "answer_excerpt": content,
                    "has_brand_mention": has_mention,
                    "citations_count": len(pr.get("citations", [])),
                })

    return platform_samples
```

#### 3.4.3 LLM 输出结构增强

A5 LLM 输出的 JSON 结构扩展:

> **[评审修正 T2]** `industry_insights` 和 `risk_alerts` 为 optional 字段，LLM 可不输出。`_normalize_report_data()` 兜底。

```json
{
  "executive_summary": "核心结论文本...",
  "key_findings": ["发现1", "发现2", "发现3"],

  "industry_insights": {
    "_optional": true,
    "background": "该品牌所在的XX行业在AI搜索领域...",
    "typical_performance": "同行业品牌的典型AI提及率在30%-60%之间...",
    "trends": ["趋势1", "趋势2"],
    "opportunities": ["机会点1", "机会点2"]
  },

  "platform_analysis": [
    {
      "platform": "deepseek",
      "platform_name": "DeepSeek",
      "performance_summary": "品牌在DeepSeek上表现...",
      "content_preference": "DeepSeek偏好技术深度内容...",
      "strengths": ["优势1"],
      "weaknesses": ["短板1"],
      "optimization_tips": ["建议1"]
    }
  ],

  "competitor_deep_analysis": {
    "overview": "在本次分析的N个竞品中...",
    "comparison_matrix": [
      {
        "competitor": "竞品X",
        "vs_brand": "高于/低于本品牌",
        "advantage_reasons": ["原因1"],
        "learnings": ["可借鉴做法1"]
      }
    ],
    "differentiation_strategy": "差异化竞争建议..."
  },

  "actionable_recommendations": [
    {
      "priority": "P0",
      "title": "优化百科词条内容",
      "action": "在百度百科和维基百科更新品牌词条，增加产品技术参数和用户评价引用",
      "expected_impact": "预计提升AI搜索中的引用质量得分15-25%",
      "difficulty": "低",
      "timeline": "1-2周"
    }
  ],

  "strengths": ["...", "..."],
  "weaknesses": ["...", "..."],
  "opportunities": ["...", "..."],
  "threats": ["...", "..."],

  "risk_alerts": [
    {
      "_optional": true,
      "level": "high",
      "title": "竞品X在AI搜索布局加速",
      "description": "...",
      "mitigation": "..."
    }
  ]
}
```

### 3.5 前端报告展示增强

**影响文件**: `D:\AGEO\frontend\src\components\canvas\contents\ReportContent.tsx`

**增强内容**:

1. **行业洞察 Tab**: 新增或在"总览"Tab 中增加行业洞察区块
2. **平台分析 Tab 增强**: 从简单的 platform_breakdown 数据展示升级为逐平台分析卡片
3. **竞品 Tab 增强**: 从简单列表升级为对比矩阵 + 深度分析
4. **建议 Tab 增强**: 从简单列表升级为带优先级/难度/时间线的可执行建议卡片

**平台分析卡片设计** (platforms Tab):

```
+-------------------------------------------------------------------+
|  DeepSeek                                               提及率 60% |
|  ----------------------------------------------------------------- |
|  表现概述: 品牌在DeepSeek上表现良好，尤其在技术类问题中...          |
|                                                                     |
|  内容偏好: DeepSeek偏好引用技术文档和产品规格信息                    |
|                                                                     |
|  优势:                                                              |
|  - 技术文档覆盖完整，被引用频率高                                    |
|  短板:                                                              |
|  - 用户评价类内容缺失，产品推荐问题提及率低                          |
|                                                                     |
|  优化建议:                                                          |
|  - 增加用户评价类内容在第三方平台的布局                              |
+-------------------------------------------------------------------+
```

**可执行建议卡片设计** (recommendations Tab):

```
+-------------------------------------------------------------------+
|  P0  优化百科词条内容                               难度: 低       |
|  ----------------------------------------------------------------- |
|  行动: 在百度百科和维基百科更新品牌词条，增加产品技术参数...         |
|  预期效果: 提升引用质量得分 15-25%                                  |
|  预计时间: 1-2 周                                                   |
+-------------------------------------------------------------------+
```

### 3.6 _generate_fallback_report 适配

**影响文件**: `aeo-platform/backend/app/workflow/nodes_a5.py` -- `_generate_fallback_report()`

降级报告也需要包含新的字段结构（使用空值或默认值），确保前端渲染不报错:

> **[评审修正 T6]** 所有新增字段 (industry_insights, platform_analysis, competitor_deep_analysis, actionable_recommendations, risk_alerts) 必须包含默认值。

```python
def _generate_fallback_report(metrics: dict, brand_profile: dict) -> dict[str, Any]:
    """Generate a basic report from metrics without LLM.

    当 LLM 调用失败时使用。包含所有必要字段的默认值。
    [评审修正 T6] 新增字段均包含默认值。
    """
    brand_name = brand_profile.get("brand_name", "品牌")
    mention_rate = metrics.get("mention_rate", 0)
    bwvs = metrics.get("bwvs_index", 0)

    return {
        "executive_summary": (
            f"{brand_name} 的 AI 搜索可见度分析已完成。"
            f"整体提及率为 {mention_rate:.1%}，BWVS 指数为 {bwvs:.1f}。"
        ),
        "key_findings": [
            f"品牌整体提及率: {mention_rate:.1%}",
            f"BWVS 综合指数: {bwvs:.1f}",
        ],
        # [评审修正 T6] 新增字段的默认值
        "industry_insights": None,
        "platform_analysis": [],
        "competitor_deep_analysis": None,
        "actionable_recommendations": [],
        "risk_alerts": [],
        # 保留原有字段
        "strengths": [f"品牌在 AI 搜索中有基础曝光 (提及率 {mention_rate:.1%})"],
        "weaknesses": [],
        "opportunities": ["建议增加品牌相关内容在权威平台的布局"],
        "threats": [],
        "recommendations": [],
        "action_plan": {},
        # 降级标记
        "_degraded": True,
    }
```

### 3.7 验收标准

- [ ] **AC-12**: A5 报告包含 `industry_insights` 字段，有行业背景分析（或 None，不报错）
- [ ] **AC-13**: A5 报告包含 `platform_analysis` 字段，每个有数据的平台有独立分析
- [ ] **AC-14**: A5 报告包含 `competitor_deep_analysis` 字段，有竞品对比矩阵
- [ ] **AC-15**: A5 报告包含 `actionable_recommendations` 字段，每条建议有优先级/行动/效果/难度/时间
- [ ] **AC-16**: 前端 ReportContent 的"平台分析" Tab 渲染逐平台分析卡片
- [ ] **AC-17**: 前端 ReportContent 的"优化建议" Tab 渲染可执行建议卡片（含优先级标签）
- [ ] **AC-18**: 降级报告 (_generate_fallback_report) 包含所有新增字段的默认值，前端不报错
- [ ] **AC-19**: 报告生成时间不超过 Cycle 1 的 150%
- [ ] **AC-20**: `_normalize_report_data()` 对缺失字段正确兜底 [评审修正 T2]
- [ ] **AC-21**: A5 LLM 调用显式设置 max_tokens=8192 [评审修正 T2]

---

## 四、功能三: 等待体验优化

### 4.1 Problem Statement

当前分析过程 (A1->A5) 耗时 1-5 分钟，用户在等待期间的体验链路:

1. 发送消息 -> 看到 MiniProgress 组件显示"正在分析..."
2. MiniProgress 列出 5 个步骤 (A1-A5)，每个步骤有 pending/in_progress/completed 状态
3. 后端通过 `execution_progress` WebSocket 事件推送进度百分比
4. 但: 前端 `executionProgress` store 有数据，却没有 UI consumer（MEMORY.md 中记录的发现）

问题:
- 进度信息粒度太粗: 只知道"A3 进行中"，不知道 A3 在做什么
- 无阶段性产出: 即使 A1 已完成并有品牌档案数据，用户也看不到
- 无预估时间: 用户不知道还要等多久
- 无中间结果: A4 已抓取到部分平台数据时，用户看不到

### 4.2 Target User

- 所有使用 Specta AI 发起品牌分析的用户

### 4.3 Success Metrics

- **Primary**: 用户在等待期间感知到系统在"持续工作且有产出"（用户体验评估中"好用性"提升）
- **Secondary**: 平均感知等待时间降低（即使实际耗时相同）
- **Guardrail**: 新增的进度推送不显著增加 WebSocket 消息量（< 50% 增加）

### 4.4 方案: 阶段性结果实时推送

#### 4.4.1 核心思路

不是缩短实际等待时间（那是技术优化的事），而是让等待变得有意义:

1. **A1 完成后**: 立即在 Chat 中展示品牌档案摘要（"已识别品牌: XX，行业: YY，竞品: ZZ"）
2. **A2 完成后**: 展示画像摘要（"已生成 N 个用户画像: 画像1、画像2..."）
3. **A3 完成后**: 展示问题列表预览（"已生成 N 个模拟问题，涵盖 M 个类别"）
4. **A4 每个平台完成后**: 实时展示平台状态（"DeepSeek: 已完成 12/12，提及率 65%"）
5. **A5 计算完成后**: 先展示 BWVS 速算结果，再等 LLM 报告生成

#### 4.4.2 实现: Agent Summary 增强

**当前状态**: 每个 Agent node 完成后通过 `send_action_log_event()` 发送一条 summary。当前 summary 是简短的一句话。

**增强**: 将 summary 升级为结构化的阶段性结果推送，在 Chat 面板中渲染为"阶段性成果卡片"。

**新增 WebSocket 事件**: `stage_result`

```python
# events.py
async def send_stage_result(
    session_id: str,
    stage: str,
    stage_name: str,
    result_type: str,  # "brand_profile" | "personas" | "questions" | "platform_status" | "metrics_preview"
    data: dict[str, Any],
) -> None:
    """发送阶段性结果到前端。"""
    await manager.emit_to_session(
        session_id,
        "stage_result",
        {
            "stage": stage,
            "stage_name": stage_name,
            "result_type": result_type,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
```

#### 4.4.3 各 Agent 的阶段性结果

**A1 完成后** (nodes.py):

```python
# a1_brand_node() 末尾，return Command 之前
await send_stage_result(
    session_id, "A1", "品牌分析",
    result_type="brand_profile",
    data={
        "brand_name": brand_profile.get("brand_name", ""),
        "industry": brand_profile.get("industry", ""),
        "competitors": [c.get("name", "") for c in competitors[:5]],
        "key_products": brand_profile.get("main_products", "")[:100],
    },
)
```

**A2 完成后** (nodes.py):

```python
# a2_persona_node() 成功路径
if marketing_personas:
    personas = marketing_personas.get("user_personas", [])
    await send_stage_result(
        session_id, "A2", "用户画像",
        result_type="personas",
        data={
            "persona_count": len(personas),
            "persona_names": [p.get("name", "") for p in personas[:4]],
        },
    )
```

**A3 完成后** (nodes_a3.py):

```python
# a3_question_node() 末尾
questions = simulated_questions.get("simulated_questions", [])
categories = list(set(q.get("category", "") for q in questions))
await send_stage_result(
    session_id, "A3", "问题生成",
    result_type="questions",
    data={
        "question_count": len(questions),
        "categories": categories,
        "sample_questions": [q.get("text", "")[:50] for q in questions[:3]],
    },
)
```

**A4 平台完成推送** (nodes_a4.py):

> **[评审修正: 共同建议]** A4 stage_result 推送时机: 在 gather 返回后逐个检查结果并推送，不在 fetch 内部推送。这避免了并发 fetch 时的竞态条件和重复推送。

```python
# 在 _api_phase() 的 gather 返回后
api_results = await asyncio.gather(*tasks, return_exceptions=True)

for platform_name, result in zip(platform_names, api_results):
    if isinstance(result, Exception):
        status, completed, total, mentions, error = "failed", 0, question_count, 0, str(result)
    else:
        status = "success" if result.get("success") else "failed"
        completed = result.get("completed", 0)
        total = result.get("total", question_count)
        mentions = result.get("mention_count", 0)
        error = result.get("error") if not result.get("success") else None

    await send_stage_result(
        session_id, "A4", "数据抓取",
        result_type="platform_status",
        data={
            "platform": platform_name,
            "status": status,
            "questions_completed": completed,
            "questions_total": total,
            "mention_count": mentions,
            "error": error,
        },
    )
```

**A5 metrics 计算完成后** (nodes_a5.py):

```python
# 在 LLM 报告生成之前（metrics 已计算完成时）
await send_stage_result(
    session_id, "A5", "数据分析",
    result_type="metrics_preview",
    data={
        "bwvs_index": round(metrics.get("bwvs_index", 0), 1),
        "mention_rate": f"{metrics.get('mention_rate', 0):.1%}",
        "total_mentions": metrics.get("total_mentions", 0),
        "total_questions": metrics.get("total_questions", 0),
        "score_band": (
            "优秀" if metrics.get("bwvs_index", 0) >= 70
            else "良好" if metrics.get("bwvs_index", 0) >= 40
            else "需改进"
        ),
    },
)
```

#### 4.4.4 前端: StageResultCard 组件

**新增文件**: `D:\AGEO\frontend\src\components\chat\StageResultCard.tsx`

在 Chat 消息流中，当收到 `stage_result` 事件时，渲染一个紧凑的阶段性成果卡片。

**设计规格**:

```
+-- A1 品牌分析 --------[已完成]--+
|                                   |
|  品牌: 小米                       |
|  行业: 消费电子                   |
|  竞品: 华为, 苹果, OPPO, vivo     |
|                                   |
+-----------------------------------+

+-- A4 数据抓取 -----[进行中 2/4]--+
|                                   |
|  [v] DeepSeek   12/12  提及8次    |
|  [v] 豆包       12/12  提及6次    |
|  [ ] Kimi       抓取中...         |
|  [ ] 混元       等待中            |
|                                   |
+-----------------------------------+

+-- A5 数据分析 -----[速算完成]----+
|                                   |
|  BWVS 指数: 48.2 (良好)          |
|  提及率: 58.3%                    |
|  报告正在生成中...                |
|                                   |
+-----------------------------------+
```

**视觉规格**:

| 元素 | 规格 |
|------|------|
| 容器 | `bg-[#111111]`, `border: 1px solid #262626`, `border-radius: 10px`, `padding: 10px 14px`, `margin: 4px 0` |
| 标题行 | 左: Agent 名称 `text-xs font-medium text-[#A3A3A3]`; 右: 状态标签 `text-[10px]` |
| 数据行 | `text-xs text-[#D4D4D4]`, `line-height: 1.6` |
| 入场动画 | `animate-slide-up`, `duration: 200ms` |
| 最大高度 | `max-height: 120px`，超出截断 + "展开"按钮 |

**前端状态管理**:

> **[评审修正 T5]** `addStageResult` 需对 `platform_status` 类型做特殊合并处理: 查找已有的 A4 stage result，将新平台数据 merge 进已有数据，而非追加为独立条目。

```typescript
// conversationStore.ts 新增

interface StageResult {
  stage: string;
  stageName: string;
  resultType: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// state 新增
stageResults: StageResult[];

// actions 新增
addStageResult: (result: StageResult) => void;
clearStageResults: () => void;

// [评审修正 T5] addStageResult 实现
addStageResult: (result) => set((state) => {
  // platform_status 类型: 合并到已有的 A4 结果中
  if (result.resultType === 'platform_status') {
    const existingIndex = state.stageResults.findIndex(
      (r) => r.stage === 'A4' && r.resultType === 'platform_status'
    );

    if (existingIndex >= 0) {
      // 合并: 将新平台数据追加到已有的 platforms 数组中
      const existing = state.stageResults[existingIndex];
      const platforms = (existing.data.platforms as Array<Record<string, unknown>>) || [];
      platforms.push(result.data);

      const updated = [...state.stageResults];
      updated[existingIndex] = {
        ...existing,
        data: {
          ...existing.data,
          platforms,
          completedCount: platforms.filter((p) => p.status === 'success').length,
          totalCount: 4,  // 总平台数
        },
        timestamp: result.timestamp,
      };
      return { stageResults: updated };
    }

    // 首个平台: 创建新的 A4 stage result，包装为 platforms 数组
    return {
      stageResults: [
        ...state.stageResults,
        {
          ...result,
          data: {
            platforms: [result.data],
            completedCount: result.data.status === 'success' ? 1 : 0,
            totalCount: 4,
          },
        },
      ],
    };
  }

  // 其他类型: 直接追加
  return { stageResults: [...state.stageResults, result] };
}),
```

**WebSocket handler**:

```typescript
// useWebSocket.ts -- 新增 stage_result 事件监听

socket.on('stage_result', (payload: StageResult) => {
  conversationStore.getState().addStageResult(payload);
});
```

#### 4.4.5 MiniProgress 增强: 预估时间

**影响文件**: `D:\AGEO\frontend\src\components\chat\MiniProgress.tsx`

在 MiniProgress 的顶部摘要行中增加预估剩余时间:

```
[o] 正在分析... 3/5 · 预计还需 ~1 分钟
```

**实现**: 基于已完成步骤的平均耗时动态估算。

```typescript
// MiniProgress.tsx

// 基于各步骤的经验平均耗时（秒）
const STEP_ESTIMATES: Record<string, number> = {
  'A1': 10,   // 品牌分析
  'A2': 15,   // 用户画像
  'A3': 5,    // 问题生成
  'A4': 60,   // 数据抓取（最慢）
  'A5': 30,   // 数据分析
};

function estimateRemaining(steps: ProgressStep[]): string | null {
  const remaining = steps.filter(s => s.status === 'pending' || s.status === 'in_progress');
  if (remaining.length === 0) return null;

  const totalSeconds = remaining.reduce((sum, step) => {
    const estimate = STEP_ESTIMATES[step.id] || 15;
    // in_progress 步骤只算一半时间
    return sum + (step.status === 'in_progress' ? estimate * 0.5 : estimate);
  }, 0);

  if (totalSeconds < 60) return `~${Math.ceil(totalSeconds / 10) * 10} 秒`;
  return `~${Math.ceil(totalSeconds / 60)} 分钟`;
}
```

#### 4.4.6 进度百分比消费: ProgressBar 集成

**问题**: MEMORY.md 中记录了 `executionProgress` store 有数据但无 UI consumer。

**修复**: 在 MiniProgress 组件中消费 `executionProgress` 数据，显示全局进度条。

```tsx
// MiniProgress.tsx -- 新增全局进度条

const executionProgress = useConversationStore(s => s.executionProgress);

// 在步骤列表上方
{executionProgress && (
  <div className="px-3 py-1">
    <div className="w-full h-1 bg-[#262626] rounded-full overflow-hidden">
      <div
        className="h-full bg-[#6366F1] rounded-full transition-all duration-500"
        style={{ width: `${Math.round(executionProgress.progress * 100)}%` }}
      />
    </div>
    <div className="flex justify-between mt-1">
      <span className="text-[10px] text-[#525252]">{executionProgress.message}</span>
      <span className="text-[10px] text-[#525252]">
        {Math.round(executionProgress.progress * 100)}%
      </span>
    </div>
  </div>
)}
```

### 4.5 验收标准

- [ ] **AC-22**: A1 完成后，Chat 面板中出现品牌档案摘要卡片
- [ ] **AC-23**: A4 每个平台完成后，Chat 面板中实时更新平台状态卡片（合并为单张卡片，非 4 张独立卡片）[评审修正 T5]
- [ ] **AC-24**: A5 metrics 计算完成后（LLM 报告生成前），展示 BWVS 速算结果
- [ ] **AC-25**: MiniProgress 显示预估剩余时间
- [ ] **AC-26**: MiniProgress 显示全局进度条（消费 executionProgress store 数据）
- [ ] **AC-27**: StageResultCard 在聊天面板中正确渲染，不遮挡主内容
- [ ] **AC-28**: WebSocket 消息总量增加不超过 50%
- [ ] **AC-29**: A4 stage_result 在 gather 返回后逐个推送，非 fetch 内部推送 [评审修正: 共同建议]

---

## 五、影响范围总结

### 5.1 后端文件变更

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `app/models/snapshot.py` | **新增** | AnalysisSnapshot 模型 + JSONText TypeDecorator [C1] |
| `app/models/__init__.py` | 修改 | 导出 AnalysisSnapshot [T7: P0 前置] |
| `app/services/snapshot_service.py` | **新增** | SnapshotService 服务类 [C3] |
| `app/api/v1/snapshots.py` | **新增** | Snapshot CRUD API (含 compare base/target) [C5] |
| `app/workflow/nodes_a5.py` | 修改 | Snapshot 一次性写入 [C2] + 报告 prompt 增强 [T2] + stage_result 推送 + delta 对比 + _normalize_report_data [T2] + 新字段透传 [T6] |
| `app/workflow/nodes.py` | 修改 | A1 entity_id 写入 state [C4] + A1/A2 stage_result 推送 |
| `app/workflow/nodes_a3.py` | 修改 | A3 stage_result 推送 |
| `app/workflow/nodes_a4.py` | 修改 | A4 逐平台 stage_result 推送（gather 后推送）[共同建议] |
| `app/workflow/events.py` | 修改 | 新增 `send_stage_result()` 函数 |
| `app/services/analytics_service.py` | 修改 | 趋势数据优先从 Snapshot 表读取 (LIMIT 100) [共同建议] |
| `prompts/data_analytics_agent.md` | 修改 | A5 prompt 增强（报告结构要求 + optional 标记）[T2] |
| Alembic migration | **新增** | AnalysisSnapshot 表迁移脚本 (UUID->CHAR(32), Enum->VARCHAR for SQLite) [T1] |

### 5.2 前端文件变更

| 文件 | 变更类型 | 变更内容 |
|------|---------|---------|
| `src/types/snapshot.ts` | **新增** | Snapshot 相关类型定义 (无 running/failed 状态, base/target 对比) [C2][C5] |
| `src/components/chat/StageResultCard.tsx` | **新增** | 阶段性成果卡片组件 |
| `src/components/chat/MiniProgress.tsx` | 修改 | 预估时间 + 全局进度条 + executionProgress 消费 |
| `src/components/chat/ChatPanel.tsx` | 修改 | 渲染 StageResultCard |
| `src/components/canvas/contents/ReportContent.tsx` | 修改 | delta_vs_previous 展示 + 增强报告渲染 |
| `src/stores/conversationStore.ts` | 修改 | stageResults 状态 + addStageResult action (含 platform_status 合并逻辑) [T5] |
| `src/hooks/useWebSocket.ts` | 修改 | 监听 stage_result 事件 |
| `src/components/dashboard/DashboardPage.tsx` | 修改 | 趋势图增强（Snapshot 数据源） |
| `src/services/api.ts` | 修改 | Snapshot API 调用封装 (compare 参数格式: base/target) [C5] |

### 5.3 不影响的部分

- **现有 Message/Session 数据模型**: Snapshot 是新增表，不修改现有表
- **现有 WebSocket 事件**: stage_result 是新增事件，不修改 reply_delta / action_log / output_ready 等
- **LLM 抽象层**: 无变更
- **A6 Browser Agent**: 无变更
- **Entity CRUD**: 无变更（Snapshot 通过 entity_id 外键关联）

---

## 六、非目标 (Out of Scope)

本次 Cycle 2 明确不做以下内容:

1. **异步任务 + 关闭页面后台运行**: 改革计划 P1-1 中的"关闭页面也能跑"功能，涉及任务队列和通知体系，工作量较大，推迟到 Cycle 3。
2. **通知推送 (邮件/Webhook)**: 同上，推迟到 Cycle 3。
3. **BWVS 权重用户自定义**: 当前权重为全局常量，用户自定义推迟到 P2 阶段。
4. **定时监测**: P2-2 的自动定期分析功能，推迟到 Cycle 3。
5. **部门化视角**: P2-1 的多部门视角，推迟到 Cycle 3。
6. **多轮追问式对比**: "和上次分析结果对比一下"这种自然语言追问功能，本次仅支持报告中的自动 delta 展示，不支持对话式追问。
7. **Snapshot 删除/归档**: V1 快照只增不删，未来再做管理功能。

---

## 七、技术风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| A5 增强 prompt 导致 LLM 输出过长/不稳定 | 中 | 报告生成失败率上升 | Cycle 1 的 A5 降级机制 (_generate_fallback_report) 已覆盖；显式设置 max_tokens=8192 [T2]；新增 _normalize_report_data() 容错 [T2] |
| Snapshot 表数据增长过快 | 低 | 数据库空间 | raw_data JSON 平均 ~50KB/条，1000 次分析 = ~50MB，短期内不成问题；trend 查询默认 LIMIT 100 [共同建议] |
| stage_result 事件过多导致 WebSocket 拥堵 | 低 | 前端卡顿 | A4 在 gather 后推送（非 fetch 内部），最多 4 条 [共同建议]；总事件量在阈值内 |
| 报告内容增加导致 LLM 调用时间延长 | 中 | 等待时间增加 | 通过 stage_result 在 LLM 调用前就展示 metrics_preview，用户感知等待时间不增加 |
| _extract_platform_samples 截断过多导致 LLM 上下文不足 | 低 | 报告分析不够深入 | 每平台 3 条样本、每条 500 字上限，总量 ~6000 字在 context 安全范围内 |
| Snapshot 与 Entity 的关联依赖 entity_id | 中 | 无 Entity 时无法创建 Snapshot | 仅在 entity_id 存在时创建 Snapshot；A1 完成后确保 entity_id 写入 state [C4]；无 Entity 的分析走现有 Message.output_data 存储 |
| entity_id 在 state 中为 str，Snapshot model 为 UUID | 低 | 写入报错 | SnapshotService 内部统一处理 str -> UUID 转换 [T3] |
| SQLite/PostgreSQL 类型差异 | 低 | Migration 失败 | UUID->CHAR(32), Enum->VARCHAR 自动降级 [T1] |

---

## 八、排期建议

> **[评审修正: 共同建议]** 工时从原 ~40h 调整为 ~57h (7-8 天)，主要增量来自: SnapshotService 服务类 (4h)、_normalize_report_data 容错 (2h)、platform_status 合并逻辑 (2h)、SQLite 兼容性测试 (2h)、entity_id 写入链路 (1h)、额外测试覆盖 (3h)。

| 任务 | 估时 | 负责角色 | 依赖 |
|------|------|---------|------|
| **Snapshot 模型** | | | |
| [T7 前置] models/__init__.py 更新 | 0.5h | 后端开发 | 无 |
| snapshot.py 模型 + JSONText [C1] + Alembic migration | 2.5h | 后端开发 | __init__.py |
| [T1] SQLite 兼容性验证 | 1h | 后端开发 | migration |
| SnapshotService 服务类 [C3] | 4h | 后端开发 | 模型 |
| snapshots.py API 路由 (含 compare base/target [C5]) | 3.5h | 后端开发 | Service |
| nodes.py A1 entity_id 写入 state [C4] | 1h | 后端开发 | 无 |
| nodes_a5.py Snapshot 一次性写入 [C2/T4] + delta 查询 | 3h | 后端开发 | Service |
| analytics_service.py 适配 Snapshot 数据源 | 2h | 后端开发 | API |
| types/snapshot.ts + api 封装 | 1h | 前端开发 | API |
| Dashboard 趋势图 Snapshot 数据源 | 2h | 前端开发 | API |
| ReportContent delta_vs_previous 展示 | 1.5h | 前端开发 | 后端 |
| **报告深度增强** | | | |
| A5 system prompt 增强 | 2h | 产品 + 后端开发 | 无 |
| _build_a5_user_content 增强 + _extract_platform_samples | 2h | 后端开发 | 无 |
| _normalize_report_data 容错函数 [T2] | 1.5h | 后端开发 | prompt |
| _generate_fallback_report 适配新字段 [T6] | 1h | 后端开发 | prompt |
| save_and_send_artifact 新字段透传 [T6] | 0.5h | 后端开发 | prompt |
| ReportContent 平台分析 Tab 增强 | 3h | 前端开发 | 后端 |
| ReportContent 优化建议 Tab 增强 | 2h | 前端开发 | 后端 |
| ReportContent 行业洞察区块 | 1.5h | 前端开发 | 后端 |
| **等待体验优化** | | | |
| events.py send_stage_result | 1h | 后端开发 | 无 |
| 各 Agent node stage_result 推送 (A4 gather 后推送) [共同建议] | 3h | 后端开发 | events.py |
| StageResultCard.tsx 组件 | 3h | 前端开发 | 后端 |
| MiniProgress.tsx 增强 (预估时间 + 进度条) | 2h | 前端开发 | 无 |
| conversationStore + useWebSocket 适配 (含 platform_status 合并 [T5]) | 2.5h | 前端开发 | 后端 |
| ChatPanel.tsx 集成 StageResultCard | 1h | 前端开发 | 组件 |
| **测试** | | | |
| SnapshotService 单元测试 [C3] | 2h | QA | Service |
| _normalize_report_data 单元测试 [T2] | 1h | QA | 函数 |
| E2E 测试 (全链路) | 4h | QA | 全部完成 |
| SQLite + PostgreSQL 双环境验证 [T1] | 1h | QA | migration |
| **总计** | **~57h (7-8 天)** | | |

---

## 九、Open Questions

1. **Q: Snapshot 是否需要限制每个 Entity 的最大数量?**
   - **已决策** [评审修正: 共同建议]: V1 不限制总数，但查询端点默认 LIMIT 100。如果后续数据量增大，可按时间清理。

2. **Q: stage_result 事件是否需要持久化?**
   - 当前建议: 不持久化。stage_result 是瞬时展示，页面刷新后从 Snapshot/Message 恢复最终结果即可。
   - 原因: 持久化增加复杂度，且重新加载时用户看最终报告即可，不需要回放中间过程。

3. **Q: A5 prompt 增强后，LLM 输出的 JSON 是否稳定?**
   - 风险: 增加字段后 LLM 输出可能漏掉某些字段或格式不正确。
   - **已缓解** [评审修正 T2]: 新增 `_normalize_report_data()` 容错函数，对缺失字段给安全默认值。industry_insights 和 risk_alerts 标记为 optional。max_tokens 显式设置为 8192。

4. **Q: _extract_platform_samples 中回答内容是否存在隐私/敏感信息?**
   - 当前策略: AI 搜索回答内容是公开信息，不涉及用户隐私。截断到 500 字避免 context 过长。
   - 后续: 如果品牌客户有数据安全要求，可增加内容脱敏选项。

5. **Q: Snapshot 的 raw_data 是否需要加密存储?**
   - 当前建议: V1 明文存储。如有合规要求，后续加密。

6. **Q: 前端 StageResultCard 与 ActionLog 的关系?**
   - 设计: StageResultCard 是 ActionLog 的"丰富版"。ActionLog 保持现有的精简文字日志，StageResultCard 是额外的结构化数据展示。两者在消息流中并存。
   - 决策人: UX 设计师评审时确认是否有视觉冲突。

---

## 附录 A: 数据流全景

### 分析流程中的 Snapshot + Stage Result 时序

```
用户: "帮我分析小米的品牌AI可见度"
    |
    v
Orchestrator -> A1 (品牌分析)
    |
    +-- [entity_id 写入 AgentState] [评审修正 C4]
    +-- [stage_result: brand_profile] --> 前端 Chat: 品牌档案卡片
    |
    v
Orchestrator -> A2 (用户画像)
    |
    +-- [stage_result: personas] --> 前端 Chat: 画像摘要卡片
    |   (或 A2 降级: degradation_notice)
    |
    v
Orchestrator -> A3 (问题生成)
    |
    +-- [stage_result: questions] --> 前端 Chat: 问题预览卡片
    |
    v
Orchestrator -> A4 (数据抓取)
    |
    +-- [gather 返回后逐个推送] [评审修正: 共同建议]
    +-- [stage_result: platform_status (DeepSeek)] --> 前端: 合并到A4卡片 [T5]
    +-- [stage_result: platform_status (豆包)]      --> 前端: 合并到A4卡片
    +-- [stage_result: platform_status (Kimi)]      --> 前端: 合并到A4卡片
    +-- [stage_result: platform_status (混元)]      --> 前端: 合并到A4卡片
    |
    v
Orchestrator -> A5 (数据分析)
    |
    +-- [metrics 计算完成]
    +-- [stage_result: metrics_preview] --> 前端 Chat: BWVS 速算卡片
    +-- [LLM 报告生成中... (max_tokens=8192)] [评审修正 T2]
    +-- [_normalize_report_data() 容错处理] [评审修正 T2]
    +-- [查询上次 Snapshot via SnapshotService, 计算 delta] [评审修正 C3]
    +-- [save_and_send_artifact: report + delta + 新字段透传] [评审修正 T6]
    +-- [SnapshotService.create_completed_snapshot()] [评审修正 C2/C3]
    |   (一次性创建，status=COMPLETED 或 PARTIAL)
    |
    v
前端 Canvas: 完整报告（含 delta_vs_previous + 新增字段）
前端 Dashboard: 趋势图更新（新 Snapshot 数据点）
```

### 数据存储归属

```
+------------------+     +---------------------+     +------------------+
|   Entity         |     | AnalysisSnapshot    |     | Message          |
|  (品牌实体)      | 1:N |  (分析快照)          | N:1 |  (对话消息)      |
|                  | <-- |                     | --> |                  |
| id               |     | entity_id (FK)      |     | output_data JSON |
| name             |     | session_id (FK)     |     |  (完整报告数据)  |
| domain           |     | bwvs_index          |     |                  |
| industry         |     | mention_rate        |     |                  |
|                  |     | sentiment_score     |     |                  |
|                  |     | coverage_score      |     |                  |
|                  |     | citation_score      |     |                  |
|                  |     | raw_data (JSONText)  |     |                  |
|                  |     | status (无 RUNNING)  |     |                  |
|                  |     | created_at          |     |                  |
+------------------+     +---------------------+     +------------------+
        |                         |
        |    1:N                  |
        +-------------------------+
        趋势查询: SELECT bwvs_index, created_at
                   FROM analysis_snapshots
                   WHERE entity_id = ?
                   ORDER BY created_at
                   LIMIT 100
```

---

## 附录 B: Snapshot 状态机 [评审修正 C2/T4 -- 简化版]

```
                          A5 metrics 计算成功
                         /                     \
                        /                       \
                       v                         v
                +----------+              +---------+
                | COMPLETED |              | PARTIAL |
                | (正常完成) |              | (LLM降级)|
                +----------+              +---------+

A5 失败: 不创建 Snapshot（错误记录在 Message/state 中）

COMPLETED: A5 正常完成，metrics + report_data 已写入
PARTIAL  : A5 降级完成（LLM 失败用 fallback），有 metrics 但报告为简版
```

> **对比原设计**: 原设计有 RUNNING -> COMPLETED/PARTIAL/FAILED 四状态流转，需要 3 次数据库操作（创建 -> 更新成功/失败）。简化后只有 2 个终态，1 次数据库写入。等待体验由 stage_result + execution_progress 事件覆盖，无需 Snapshot 的 RUNNING 状态。

---

## 附录 C: 前端 StageResultCard 渲染示例

### brand_profile 类型

```tsx
<StageResultCard>
  <Header icon={<BuildingIcon />} title="品牌分析" status="completed" />
  <Body>
    <Row label="品牌" value="小米" />
    <Row label="行业" value="消费电子" />
    <Row label="竞品" value="华为, 苹果, OPPO, vivo" />
  </Body>
</StageResultCard>
```

### platform_status 类型 (累积合并) [评审修正 T5]

> 多个 platform_status 事件合并到同一张 A4 卡片中，而非显示 4 张独立卡片。

```tsx
<StageResultCard>
  <Header icon={<GlobeIcon />} title="数据抓取" status="in_progress" badge="2/4" />
  <Body>
    <PlatformRow name="DeepSeek" status="success" detail="12/12 提及8次" />
    <PlatformRow name="豆包" status="success" detail="12/12 提及6次" />
    <PlatformRow name="Kimi" status="in_progress" detail="抓取中..." />
    <PlatformRow name="混元" status="pending" detail="等待中" />
  </Body>
</StageResultCard>
```

### metrics_preview 类型

```tsx
<StageResultCard>
  <Header icon={<ChartIcon />} title="数据分析" status="partial" />
  <Body>
    <BigNumber value={48.2} label="BWVS 指数" band="良好" />
    <Row label="提及率" value="58.3%" />
    <Row label="提及数" value="31 / 48" />
    <Footnote>报告正在生成中...</Footnote>
  </Body>
</StageResultCard>
```

---

## 附录 D: 评审修正汇总

本章节完整记录两位评审人的所有修正意见及其在 PRD 中的落实位置。

### 架构师 (Martin Fowler) -- 5 项修正

| 编号 | 修正内容 | PRD 落实位置 |
|------|---------|-------------|
| **C1** | raw_data 字段从 `Text` 改为 `JSONText` TypeDecorator，自动 json.dumps/loads | 2.4 数据模型 (snapshot.py 中新增 JSONText 类)；2.6 伪代码 (raw_data 直接传 dict) |
| **C2** | 删除 RUNNING 状态，Snapshot 在 metrics 计算完成后一次性创建 | 2.4 SnapshotStatus (仅 COMPLETED/PARTIAL)；2.6 写入逻辑 (单次创建)；附录 B (简化状态机) |
| **C3** | 新增 SnapshotService 服务类，集中管理 Snapshot 生命周期 | 2.5 SnapshotService (完整规格)；2.6 伪代码 (调用 service) |
| **C4** | entity_id 写入链路: A1 完成后将 entity_id 写入 AgentState | 2.6 前置条件说明；2.11 AC-9；附录 A 时序图 |
| **C5** | compare API 参数从 `?ids=id1,id2` 改为 `?base=uuid1&target=uuid2` | 2.7 API 表格 + 响应示例；2.9 TypeScript 类型 (SnapshotCompare) |

### 技术负责人 (John Carmack) -- 7 项修正

| 编号 | 修正内容 | PRD 落实位置 |
|------|---------|-------------|
| **T1** | SQLite 兼容性文档: UUID->CHAR(32), Enum->VARCHAR | 2.4 Migration 章节 (SQLite 兼容性说明表格) |
| **T2** | A5 token 预算: max_tokens=8192 + optional 字段 + _normalize_report_data() | 2.6 _normalize_report_data 函数；3.4.1 optional 标记；3.4.2 schema 精简说明；2.11 AC-20/AC-21 |
| **T3** | entity_id UUID 转换: state 中 str -> Snapshot model UUID | 2.5 SnapshotService (内部转换逻辑)；2.6 伪代码注释 |
| **T4** | Snapshot 写入时机: 在 _calculate_metrics 成功后创建（与 C2 一致） | 2.6 写入逻辑（与 C2 合并处理） |
| **T5** | platform_status 前端合并逻辑: addStageResult 特殊处理 | 4.4.4 conversationStore addStageResult 实现；附录 C platform_status 渲染 |
| **T6** | 新字段透传: save_and_send_artifact + _generate_fallback_report | 2.6 artifact 透传代码；3.6 fallback 包含所有新字段默认值 |
| **T7** | Alembic 前置条件: 先改 __init__.py 再跑 alembic revision | 2.4 Migration 章节 (P0 前置步骤说明) |

### 两位评审共同建议

| 内容 | PRD 落实位置 |
|------|-------------|
| 工时从 40h 调整为 55-60h (实际估算 57h) | 八、排期建议 |
| A4 stage_result 在 gather 返回后逐个推送 | 4.4.3 A4 推送代码；4.5 AC-29 |
| Session 端 backref 改为 "analysis_snapshots" | 2.4 模型代码 relationship 定义 |
| trend 端点默认 LIMIT 100 | 2.5 SnapshotService.get_trend()；2.8 analytics_service；2.11 AC-5 |
