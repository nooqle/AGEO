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

    Snapshot 在 metrics 计算完成后一次性创建，不存在"进行中"状态。
    - A5 失败时不创建 Snapshot（错误记录在 Message/state 中）。
    - 等待体验已有 stage_result + execution_progress 覆盖。
    """

    COMPLETED = "completed"
    PARTIAL = "partial"


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

    # --- 完整原始数据（JSONText 自动 dict <-> JSON 转换） ---
    raw_data: Mapped[dict | None] = mapped_column(JSONText, nullable=True)

    # --- 元数据 ---
    snapshot_type: Mapped[str] = mapped_column(
        String(20), default="legacy", nullable=False, index=True
    )  # Values: "baseline" / "persona" / "legacy"
    triggered_by: Mapped[str] = mapped_column(
        String(50), default="manual", nullable=False
    )

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
    entity: Mapped["Entity"] = relationship("Entity", backref="analysis_snapshots")
    session: Mapped["Session | None"] = relationship("Session", backref="analysis_snapshots")

    def __repr__(self) -> str:
        return (
            f"<AnalysisSnapshot(id={self.id}, entity={self.entity_id}, "
            f"bwvs={self.bwvs_index}, status={self.status})>"
        )
