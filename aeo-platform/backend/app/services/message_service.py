"""Message service for managing conversation messages."""

import json
from typing import Any, List
from uuid import UUID

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message, MessageRole, MessageType


def _looks_like_corrupted_question_marks(text: str | None) -> bool:
    normalized = str(text or "").strip()
    if len(normalized) < 8:
        return False
    meaningful_chars = [char for char in normalized if not char.isspace()]
    if len(meaningful_chars) < 8:
        return False
    question_like_count = sum(char in {"?", "？"} for char in meaningful_chars)
    return question_like_count / len(meaningful_chars) >= 0.6


def _extract_summary_metrics(payload: dict[str, Any]) -> dict[str, Any] | None:
    summary_metrics = payload.get("summary_metrics")
    if isinstance(summary_metrics, dict) and summary_metrics:
        return summary_metrics

    metrics = payload.get("metrics")
    if isinstance(metrics, dict) and metrics:
        return metrics

    sections = payload.get("sections")
    if not isinstance(sections, list):
        return None

    for section in sections:
        if not isinstance(section, dict):
            continue
        if section.get("section_name") != "summary":
            continue
        data = section.get("data")
        if not isinstance(data, dict):
            continue
        rows = data.get("metrics")
        if not isinstance(rows, list):
            continue
        compact_metrics: dict[str, Any] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            label = row.get("label")
            value = row.get("value")
            if isinstance(label, str) and label.strip() and value is not None:
                compact_metrics[label.strip()] = value
        if compact_metrics:
            return compact_metrics
    return None


def _extract_preview_item_count(payload: dict[str, Any]) -> int | None:
    explicit_item_count = payload.get("itemCount")
    if isinstance(explicit_item_count, int):
        return explicit_item_count

    for key in ("items", "rows", "questions", "fetchResults", "fetch_results"):
        value = payload.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _compact_output_payload(
    payload: dict[str, Any],
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in (
        "output_id",
        "artifact_id",
        "title",
        "headline",
        "report_kind",
        "artifact_kind",
        "preview_description",
        "description",
        "executive_summary",
        "updated_at",
        "brand_name",
        "root_domain",
        "site_root_url",
        "analysis_period",
    ):
        value = payload.get(key)
        if isinstance(value, (str, int, float, bool)) and value != "":
            compact[key] = value

    summary_metrics = _extract_summary_metrics(payload)
    if summary_metrics:
        compact["summary_metrics"] = summary_metrics

    item_count = _extract_preview_item_count(payload)
    if item_count is not None:
        compact["itemCount"] = item_count

    return compact


def _sanitize_history_message_content(
    *,
    role: str,
    content: str | None,
    metadata: dict[str, Any] | None,
) -> str:
    normalized = str(content or "")
    if not _looks_like_corrupted_question_marks(normalized):
        return normalized

    if metadata:
        for key in ("confirmation_label", "selected_option_label", "resolved_label"):
            value = metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    if role == "user":
        return "用户已确认继续"
    return "历史消息已恢复，请查看关联交付物。"


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
        *,
        compact_output: bool = True,
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

        return [self._message_to_dict(msg, compact_output=compact_output) for msg in messages]

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

    def _message_to_dict(
        self,
        message: Message,
        *,
        compact_output: bool = False,
    ) -> dict[str, Any]:
        """Convert message model to dict.

        Args:
            message: Message model

        Returns:
            Message dict
        """
        metadata = json.loads(message.extra_metadata) if message.extra_metadata else None
        role = "agent" if message.role == MessageRole.ASSISTANT else message.role.value

        result = {
            "id": str(message.id),
            "session_id": str(message.session_id),
            "role": role,
            "type": message.type.value,
            "content": _sanitize_history_message_content(
                role=role,
                content=message.content,
                metadata=metadata if isinstance(metadata, dict) else None,
            ),
            "sequence": message.sequence,
            "metadata": metadata,
            "created_at": message.created_at.isoformat(),
        }
        if message.type == MessageType.OUTPUT:
            result["output_type"] = message.output_type
            parsed_output = json.loads(message.output_data) if message.output_data else None
            if compact_output and isinstance(parsed_output, dict):
                result["output_data"] = _compact_output_payload(parsed_output)
            else:
                result["output_data"] = parsed_output
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
