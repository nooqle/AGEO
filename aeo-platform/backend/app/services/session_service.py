"""Session service for managing conversation sessions."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole
from app.models.session import Session, SessionStatus
from app.models.user import User
from app.services.access_scope_service import AccessScopeService


class SessionService:
    """Service for managing sessions."""

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def list_sessions(
        self,
        viewer: User,
        limit: int = 20,
        offset: int = 0,
        status: SessionStatus | None = None,
    ) -> dict[str, Any]:
        """获取会话列表，含消息统计和最新消息预览。

        Args:
            user_id: 用户 ID
            limit: 每页数量
            offset: 偏移量
            status: 状态过滤（已由路由层校验）

        Returns:
            包含 sessions 列表和 total 的字典
        """
        # 基础过滤条件
        base_filter = [AccessScopeService.session_visibility_filter(viewer)]
        if status is not None:
            base_filter.append(Session.status == status)

        # 查询总数
        count_stmt = select(func.count(Session.id)).where(*base_filter)
        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        # 查询会话列表（分页，按 updated_at 降序）
        sessions_stmt = (
            select(Session)
            .where(*base_filter)
            .order_by(Session.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )
        sessions_result = await self.db.execute(sessions_stmt)
        sessions = sessions_result.scalars().all()

        # 批量获取每个 session 的消息统计
        session_ids = [s.id for s in sessions]
        if not session_ids:
            return {"sessions": [], "total": total}

        # 子查询：每个 session 的 message_count
        msg_count_stmt = (
            select(
                Message.session_id,
                func.count(Message.id).label("message_count"),
            )
            .where(Message.session_id.in_(session_ids))
            .group_by(Message.session_id)
        )
        msg_count_result = await self.db.execute(msg_count_stmt)
        msg_counts = {row.session_id: row.message_count for row in msg_count_result}

        # 子查询：每个 session 的最新消息（ROW_NUMBER 避免同时间戳重复行）
        latest_msg_subq = (
            select(
                Message.session_id,
                Message.content,
                func.row_number()
                .over(
                    partition_by=Message.session_id,
                    order_by=Message.created_at.desc(),
                )
                .label("rn"),
            )
            .where(Message.session_id.in_(session_ids))
            .subquery()
        )
        latest_msg_stmt = select(
            latest_msg_subq.c.session_id, latest_msg_subq.c.content
        ).where(latest_msg_subq.c.rn == 1)
        latest_msg_result = await self.db.execute(latest_msg_stmt)
        latest_msgs = {row.session_id: row.content for row in latest_msg_result}

        # 子查询：每个 session 的第一条 user 消息（ROW_NUMBER 避免同时间戳重复行）
        first_user_msg_subq = (
            select(
                Message.session_id,
                Message.content,
                func.row_number()
                .over(
                    partition_by=Message.session_id,
                    order_by=Message.created_at.asc(),
                )
                .label("rn"),
            )
            .where(
                Message.session_id.in_(session_ids),
                Message.role == MessageRole.USER,
            )
            .subquery()
        )
        first_user_msg_stmt = select(
            first_user_msg_subq.c.session_id, first_user_msg_subq.c.content
        ).where(first_user_msg_subq.c.rn == 1)
        first_user_msg_result = await self.db.execute(first_user_msg_stmt)
        first_user_msgs = {row.session_id: row.content for row in first_user_msg_result}

        # 组装结果
        items = []
        for session in sessions:
            brand_name = self._extract_brand_name(
                session, first_user_msgs.get(session.id)
            )
            last_msg = latest_msgs.get(session.id) or ""
            # 截断 100 字符
            preview = last_msg[:100] if last_msg else None

            items.append(
                {
                    "id": str(session.id),
                    "title": session.title,
                    "status": (
                        session.status.value
                        if hasattr(session.status, "value")
                        else session.status
                    ),
                    "entity_id": str(session.entity_id) if session.entity_id else None,
                    "brand_name": brand_name,
                    "last_message_preview": preview,
                    "message_count": msg_counts.get(session.id, 0),
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                }
            )

        return {"sessions": items, "total": total}

    @staticmethod
    def _extract_brand_name(
        session: Session, first_user_content: str | None
    ) -> str | None:
        """从 session 的 extra_metadata 或第一条用户消息中提取品牌名。

        优先级：extra_metadata.brand_name > 第一条 user message content（截断 20 字符）
        """
        # 尝试从 extra_metadata JSON 中提取
        if session.extra_metadata:
            try:
                meta = json.loads(session.extra_metadata)
                if isinstance(meta, dict):
                    brand = meta.get("brand_name")
                    if brand:
                        return str(brand)
            except (json.JSONDecodeError, TypeError):
                pass

        # 降级：取第一条 user message 内容截断
        if first_user_content:
            return first_user_content[:20]

        return None

    async def create_session(
        self, viewer: User, entity_id: UUID | None = None
    ) -> dict[str, Any]:
        """Create new session.

        Args:
            user_id: User ID
            entity_id: Optional Entity ID to associate with session

        Returns:
            Session data
        """
        session = Session(
            user_id=viewer.id,
            status="active",
            entity_id=entity_id,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return self._session_to_dict(session)

    async def get_latest_session_by_entity(
        self,
        entity_id: UUID,
        viewer: User,
    ) -> dict[str, Any] | None:
        stmt = (
            select(Session)
            .where(
                Session.entity_id == entity_id,
                AccessScopeService.session_visibility_filter(viewer),
            )
            .order_by(Session.updated_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        session = result.scalar_one_or_none()
        if not session:
            return None
        return self._session_to_dict(session)

    async def get_session(
        self, session_id: UUID, viewer: User
    ) -> dict[str, Any] | None:
        """Get session details.

        Args:
            session_id: Session ID

        Returns:
            Session data or None
        """
        result = await self.db.execute(
            select(Session).where(
                Session.id == session_id,
                AccessScopeService.session_visibility_filter(viewer),
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return None
        return self._session_to_dict(session)

    async def delete_session(self, session_id: UUID, viewer: User) -> bool:
        """Delete session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted
        """
        result = await self.db.execute(
            select(Session).where(
                Session.id == session_id, Session.user_id == viewer.id
            )
        )
        session = result.scalar_one_or_none()
        if not session:
            return False
        await self.db.delete(session)
        await self.db.commit()
        return True

    def _session_to_dict(self, session: Session) -> dict[str, Any]:
        return {
            "id": str(session.id),
            "title": session.title,
            "status": (
                session.status.value
                if hasattr(session.status, "value")
                else session.status
            ),
            "entity_id": str(session.entity_id) if session.entity_id else None,
            "context": session.context,
            "extra_metadata": session.extra_metadata,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "completed_at": (
                session.completed_at.isoformat() if session.completed_at else None
            ),
        }
