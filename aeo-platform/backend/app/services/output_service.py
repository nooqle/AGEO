"""Output service for managing analysis outputs."""

import json
from pathlib import Path
from typing import Any, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message, MessageType


class OutputService:
    """Service for managing outputs."""

    def __init__(self, db: AsyncSession):
        """Initialize service.

        Args:
            db: Database session
        """
        self.db = db

    async def get_outputs(
        self,
        session_id: UUID,
    ) -> List[dict[str, Any]]:
        """Get all outputs.

        Args:
            session_id: Session ID

        Returns:
            List of outputs
        """
        query = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.type == MessageType.OUTPUT,
            )
            .order_by(Message.sequence.asc())
        )
        result = await self.db.execute(query)
        messages = result.scalars().all()
        return [self._output_to_dict(msg) for msg in messages]

    async def get_output(
        self,
        session_id: UUID,
        output_id: UUID,
    ) -> dict[str, Any] | None:
        """Get single output details.

        Args:
            session_id: Session ID
            output_id: Output ID

        Returns:
            Output data or None
        """
        message = await self.db.get(Message, output_id)
        if (
            not message
            or message.session_id != session_id
            or message.type != MessageType.OUTPUT
        ):
            return None
        return self._output_to_dict(message)

    async def export_output(
        self,
        session_id: UUID,
        output_id: UUID,
        format: str = "pdf",
    ) -> str:
        """Export output.

        Args:
            session_id: Session ID
            output_id: Output ID
            format: Export format (pdf | excel)

        Returns:
            File path
        """
        if format not in {"pdf", "excel"}:
            raise ValueError("Unsupported format")

        output = await self.get_output(session_id, output_id)
        if not output:
            raise FileNotFoundError("Output not found")

        output_dir = Path(settings.OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        file_path = output_dir / f"export_{output_id}.{format}"

        data = output.get("data")
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except Exception:
                pass

        with file_path.open("w", encoding="utf-8") as file:
            if isinstance(data, (dict, list)):
                file.write(json.dumps(data, ensure_ascii=False, indent=2))
            elif data is None:
                file.write("")
            else:
                file.write(str(data))

        return str(file_path)

    def _output_to_dict(self, message: Message) -> dict[str, Any]:
        data = None
        if message.output_data:
            try:
                data = json.loads(message.output_data)
            except Exception:
                data = message.output_data
        # Use same artifact_id format as WebSocket output_ready event
        # so loadArtifacts() and WS events merge into one Tab instead of duplicating
        artifact_id = f"{message.session_id}_{message.output_type}"
        # Derive category from output_type (report_baseline → baseline, report → scenario)
        category = None
        if message.output_type and message.output_type.startswith("report"):
            category = "baseline" if message.output_type == "report_baseline" else "scenario"
        return {
            "id": artifact_id,
            "message_id": str(message.id),
            "session_id": str(message.session_id),
            "type": message.output_type,
            "title": message.content or "分析结果",
            "data": data,
            "category": category,
            "created_at": message.created_at.isoformat(),
        }
