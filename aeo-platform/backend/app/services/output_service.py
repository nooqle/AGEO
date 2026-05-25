"""Output service for managing analysis outputs."""

import json
from pathlib import Path
import re
from typing import Any, List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.message import Message, MessageType
from app.services.fetch_run_platform_state_service import FetchRunPlatformStateService


def _normalize_user_visible_output_payload(value: Any) -> Any:
    if isinstance(value, str):
        normalized = re.sub(r"\[\]\(@mark_[^)]+\)", "", value)
        return re.sub(r"\bhunyuan\b", "元宝", normalized, flags=re.IGNORECASE)
    if isinstance(value, list):
        return [_normalize_user_visible_output_payload(item) for item in value]
    if isinstance(value, dict):
        return {
            key: _normalize_user_visible_output_payload(item)
            for key, item in value.items()
        }
    return value


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


def _compact_output_payload(payload: dict[str, Any]) -> dict[str, Any]:
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
        "executive_summary_text",
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

    compact["hydration_stub"] = True
    return compact


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
        *,
        compact: bool = False,
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
        outputs = [self._output_to_dict(msg, compact=compact) for msg in messages]
        return await self._merge_authoritative_fetch_results_output(
            session_id=session_id,
            outputs=outputs,
            compact=compact,
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

    def _output_to_dict(
        self, message: Message, *, compact: bool = False
    ) -> dict[str, Any]:
        data = None
        metadata = None
        if message.output_data:
            try:
                data = json.loads(message.output_data)
            except Exception:
                data = message.output_data
        data = _normalize_user_visible_output_payload(data)
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
            if isinstance(metadata, dict)
            and isinstance(metadata.get("artifact_kind"), str)
            else None
        )
        report_kind = (
            metadata.get("report_kind")
            if isinstance(metadata, dict)
            and isinstance(metadata.get("report_kind"), str)
            else None
        )
        if (
            artifact_kind
            not in {
                "confidence_signal",
                "confidence_analysis",
                "site_confidence_report",
            }
            and report_kind
            not in {
                "confidence_signal",
                "confidence_analysis",
                "site_confidence_report",
            }
            and message.output_type
            and message.output_type.startswith("report")
        ):
            if report_kind in {"panorama", "scenario"}:
                category = report_kind
            else:
                category = "scenario"
        if compact and isinstance(data, dict):
            data = _compact_output_payload(data)
        return {
            "id": str(message.id),
            "artifact_id": artifact_id,
            "message_id": str(message.id),
            "session_id": str(message.session_id),
            "type": message.output_type,
            "title": _normalize_user_visible_output_payload(
                message.content or "分析结果"
            ),
            "data": data,
            "metadata": metadata,
            "category": category,
            "sequence": getattr(message, "sequence", None),
            "created_at": message.created_at.isoformat(),
        }

    async def _get_authoritative_fetch_results_output(
        self,
        *,
        session_id: UUID,
        compact: bool = False,
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
        fetch_anchor_message = (
            fetch_anchor_result.scalar_one_or_none()
            if hasattr(fetch_anchor_result, "scalar_one_or_none")
            else None
        )

        data = {
            "fetchResults": fetch_results,
            "platformStatus": projection.get("platform_status") or {},
            "timingSummary": projection.get("timing_summary") or {},
        }
        data = _normalize_user_visible_output_payload(data)
        if compact:
            data = _compact_output_payload(data)

        return {
            "id": str(latest_row.task_run_id),
            "artifact_id": f"{session_id}_fetchResults",
            "message_id": (
                str(fetch_anchor_message.id) if fetch_anchor_message else None
            ),
            "session_id": str(session_id),
            "type": "fetchResults",
            "title": (
                _normalize_user_visible_output_payload(fetch_anchor_message.content)
                if fetch_anchor_message and fetch_anchor_message.content
                else "AI答案抓取结果"
            ),
            "data": data,
            "metadata": {
                "synthetic": True,
                "source": "fetch_run_platform_states",
                "task_run_id": str(latest_row.task_run_id),
                "hydration_stub": compact,
            },
            "category": None,
            "sequence": (
                getattr(fetch_anchor_message, "sequence", None)
                if fetch_anchor_message
                else None
            ),
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
        compact: bool = False,
    ) -> list[dict[str, Any]]:
        authoritative_fetch_results = (
            await self._get_authoritative_fetch_results_output(
                session_id=session_id,
                compact=compact,
            )
        )
        if not authoritative_fetch_results:
            return outputs

        non_fetch_outputs = [
            output for output in outputs if output.get("type") != "fetchResults"
        ]
        non_fetch_outputs.append(authoritative_fetch_results)
        non_fetch_outputs.sort(
            key=lambda output: (
                (
                    output.get("sequence")
                    if isinstance(output.get("sequence"), int)
                    else 10**9
                ),
                str(output.get("created_at") or ""),
            ),
        )
        return non_fetch_outputs
