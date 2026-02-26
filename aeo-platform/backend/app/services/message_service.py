"""Message service for managing conversation messages."""

import json
from typing import Any, List
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole, MessageType


class MessageService:
    """Service for managing messages."""

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 50,
        before: UUID | None = None,
    ) -> List[dict[str, Any]]:
        """Get message list.

        Args:
            session_id: Session ID
            limit: Limit
            before: Before message ID

        Returns:
            List of messages
        """
        query = select(Message).where(Message.session_id == session_id)

        if before:
            # Get messages before a specific message
            before_msg = await self.db.get(Message, before)
            if before_msg:
                query = query.where(Message.sequence < before_msg.sequence)

        query = query.order_by(Message.sequence.desc()).limit(limit)

        result = await self.db.execute(query)
        messages = result.scalars().all()

        # Reverse to get chronological order
        messages = list(reversed(messages))

        return [self._message_to_dict(msg) for msg in messages]

    async def save_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        metadata: dict | None = None,
        message_type: str | None = None,
        output_type: str | None = None,
        output_data: str | None = None,
    ) -> dict[str, Any]:
        """Save message.

        Args:
            session_id: Session ID
            role: Message role (user/agent)
            content: Message content
            metadata: Additional metadata
            message_type: Message type override (text/output/etc.)
            output_type: Output type for OUTPUT messages
            output_data: JSON string of output data for OUTPUT messages

        Returns:
            Saved message
        """
        # Get next sequence number
        query = (
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.sequence.desc())
            .limit(1)
        )
        result = await self.db.execute(query)
        last_message = result.scalar_one_or_none()
        next_sequence = (last_message.sequence + 1) if last_message else 1

        # Map role string to enum
        role_enum = MessageRole.ASSISTANT if role == "agent" else MessageRole.USER

        # Determine message type
        msg_type = MessageType.TEXT
        if message_type == "OUTPUT":
            msg_type = MessageType.OUTPUT

        # Create message
        message = Message(
            session_id=session_id,
            role=role_enum,
            type=msg_type,
            content=content,
            sequence=next_sequence,
            output_type=output_type,
            output_data=output_data,
            extra_metadata=json.dumps(metadata) if metadata else None,
        )

        self.db.add(message)
        await self.db.commit()
        await self.db.refresh(message)

        return self._message_to_dict(message)

    def _message_to_dict(self, message: Message) -> dict[str, Any]:
        """Convert message model to dict.

        Args:
            message: Message model

        Returns:
            Message dict
        """
        result = {
            "id": str(message.id),
            "session_id": str(message.session_id),
            "role": (
                "agent" if message.role == MessageRole.ASSISTANT else message.role.value
            ),
            "type": message.type.value,
            "content": message.content,
            "sequence": message.sequence,
            "metadata": (
                json.loads(message.extra_metadata) if message.extra_metadata else None
            ),
            "created_at": message.created_at.isoformat(),
        }
        if message.type == MessageType.OUTPUT:
            result["output_type"] = message.output_type
            result["output_data"] = (
                json.loads(message.output_data) if message.output_data else None
            )
        return result

    async def rollback_after(
        self,
        session_id: UUID,
        message_id: UUID,
    ) -> dict[str, Any]:
        """Rollback: delete all messages after specified message.

        Args:
            session_id: Session ID
            message_id: Message ID

        Returns:
            Result
        """
        message = await self.db.get(Message, message_id)
        if not message or message.session_id != session_id:
            return {
                "status": "not_found",
                "deleted_count": 0,
            }

        delete_stmt = delete(Message).where(
            Message.session_id == session_id,
            Message.sequence > message.sequence,
        )
        result = await self.db.execute(delete_stmt)
        await self.db.commit()
        deleted_count = result.rowcount or 0

        return {
            "status": "success",
            "deleted_count": deleted_count,
        }

    async def rollback_from(
        self,
        session_id: UUID,
        message_id: UUID,
    ) -> dict[str, Any]:
        """Rollback: delete target message AND all messages after it.

        Args:
            session_id: Session ID
            message_id: Target message ID (will also be deleted)

        Returns:
            Result with status and deleted_count
        """
        message = await self.db.get(Message, message_id)
        if not message or message.session_id != session_id:
            return {
                "status": "not_found",
                "deleted_count": 0,
            }

        delete_stmt = delete(Message).where(
            Message.session_id == session_id,
            Message.sequence >= message.sequence,
        )
        result = await self.db.execute(delete_stmt)
        await self.db.commit()
        deleted_count = result.rowcount or 0

        return {
            "status": "success",
            "deleted_count": deleted_count,
        }
