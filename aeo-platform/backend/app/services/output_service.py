"""Output service for managing analysis outputs."""

import json
from pathlib import Path
from typing import Any, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message, MessageType
from app.services.fetch_run_platform_state_service import FetchRunPlatformStateService


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
        outputs = [self._output_to_dict(msg) for msg in messages]
        return await self._merge_authoritative_fetch_results_output(
            session_id=session_id,
            outputs=outputs,
        )

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
            synthetic = await self._get_authoritative_fetch_results_output(
                session_id=session_id,
            )
            if synthetic and synthetic["id"] == str(output_id):
                return synthetic
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
        metadata = None
        if message.output_data:
            try:
                data = json.loads(message.output_data)
            except Exception:
                data = message.output_data
        if message.extra_metadata:
            try:
                metadata = json.loads(message.extra_metadata)
            except Exception:
                metadata = None
        artifact_id = (
            metadata.get("output_id")
            if isinstance(metadata, dict) and isinstance(metadata.get("output_id"), str)
            else f"{message.session_id}_{message.output_type}"
        )
        # Derive category from canonical report metadata first, then legacy output_type.
        category = None
        artifact_kind = (
            metadata.get("artifact_kind")
            if isinstance(metadata, dict) and isinstance(metadata.get("artifact_kind"), str)
            else None
        )
        report_kind = (
            metadata.get("report_kind")
            if isinstance(metadata, dict) and isinstance(metadata.get("report_kind"), str)
            else None
        )
        if (
            artifact_kind
            not in {"confidence_signal", "confidence_analysis", "site_confidence_report"}
            and report_kind
            not in {"confidence_signal", "confidence_analysis", "site_confidence_report"}
            and message.output_type
            and message.output_type.startswith("report")
        ):
            if report_kind in {"panorama", "scenario"}:
                category = report_kind
            else:
                category = "scenario"
        return {
            "id": str(message.id),
            "artifact_id": artifact_id,
            "message_id": str(message.id),
            "session_id": str(message.session_id),
            "type": message.output_type,
            "title": message.content or "分析结果",
            "data": data,
            "metadata": metadata,
            "category": category,
            "sequence": message.sequence,
            "created_at": message.created_at.isoformat(),
        }

    async def _get_authoritative_fetch_results_output(
        self,
        *,
        session_id: UUID,
    ) -> dict[str, Any] | None:
        state_service = FetchRunPlatformStateService(self.db)
        rows = await state_service.list_latest_for_session(session_id)
        if not rows:
            return None

        projection = state_service.build_summary_projection(rows)
        fetch_results = projection.get("fetch_results") or []
        if not fetch_results:
            return None

        latest_row = max(
            rows,
            key=lambda row: (
                row.updated_at or row.created_at,
                row.created_at,
            ),
        )
        fetch_anchor_query = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.type == MessageType.OUTPUT,
                Message.output_type == "fetchResults",
            )
            .order_by(Message.sequence.asc())
            .limit(1)
        )
        fetch_anchor_result = await self.db.execute(fetch_anchor_query)
        fetch_anchor_message = fetch_anchor_result.scalar_one_or_none()

        return {
            "id": str(latest_row.task_run_id),
            "artifact_id": f"{session_id}_fetchResults",
            "message_id": str(fetch_anchor_message.id) if fetch_anchor_message else None,
            "session_id": str(session_id),
            "type": "fetchResults",
            "title": (
                fetch_anchor_message.content
                if fetch_anchor_message and fetch_anchor_message.content
                else "AI答案抓取结果"
            ),
            "data": {
                "fetchResults": fetch_results,
                "platformStatus": projection.get("platform_status") or {},
                "timingSummary": projection.get("timing_summary") or {},
            },
            "metadata": {
                "synthetic": True,
                "source": "fetch_run_platform_states",
                "task_run_id": str(latest_row.task_run_id),
            },
            "category": None,
            "sequence": fetch_anchor_message.sequence if fetch_anchor_message else None,
            "created_at": (
                fetch_anchor_message.created_at
                if fetch_anchor_message
                else (latest_row.updated_at or latest_row.created_at)
            ).isoformat(),
        }

    async def _merge_authoritative_fetch_results_output(
        self,
        *,
        session_id: UUID,
        outputs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        authoritative_fetch_results = await self._get_authoritative_fetch_results_output(
            session_id=session_id,
        )
        if not authoritative_fetch_results:
            return outputs

        non_fetch_outputs = [
            output for output in outputs if output.get("type") != "fetchResults"
        ]
        non_fetch_outputs.append(authoritative_fetch_results)
        non_fetch_outputs.sort(
            key=lambda output: (
                output.get("sequence")
                if isinstance(output.get("sequence"), int)
                else 10**9,
                str(output.get("created_at") or ""),
            ),
        )
        return non_fetch_outputs
