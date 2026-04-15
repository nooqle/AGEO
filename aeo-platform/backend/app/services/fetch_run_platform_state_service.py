"""Authoritative per-platform fetch state service."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fetch_run_platform_state import FetchRunPlatformState
from app.tools.a4_fetch_agent import normalize_public_platform_id


_STATUS_PRIORITY = {
    "pending": 0,
    "running": 1,
    "takeover_required": 2,
    "skipped": 3,
    "failed": 4,
    "succeeded": 5,
}
_TERMINAL_STATUSES = {"skipped", "failed", "succeeded"}


class FetchRunPlatformStateService:
    """Persist and project authoritative A4/A5 per-platform state."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def delete_for_session(self, session_id: UUID) -> int:
        stmt = delete(FetchRunPlatformState).where(
            FetchRunPlatformState.session_id == session_id
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.rowcount or 0

    @staticmethod
    def canonicalize_platform(platform: Any) -> str:
        normalized = normalize_public_platform_id(platform)
        if normalized:
            return normalized
        return str(platform or "").strip().lower()

    @staticmethod
    def _normalize_status(status: Any) -> str:
        value = str(status or "").strip().lower()
        if value in _STATUS_PRIORITY:
            return value
        if value == "result":
            return "succeeded"
        if value == "success":
            return "succeeded"
        return "failed"

    @staticmethod
    def _normalize_auth_state(auth_state: Any) -> str:
        value = str(auth_state or "").strip().lower()
        if value in {
            "unknown",
            "authenticated",
            "needs_login",
            "needs_verify",
            "skipped",
        }:
            return value
        return "unknown"

    @staticmethod
    def _status_to_legacy(status: str) -> str:
        if status == "succeeded":
            return "success"
        return status

    @classmethod
    def _status_to_projection(cls, status: Any) -> str:
        normalized = cls._normalize_status(status)
        if normalized == "succeeded":
            return "success"
        return normalized

    @classmethod
    def _project_auth_state(cls, packet: dict[str, Any], status: str) -> str:
        auth_state = cls._normalize_auth_state(packet.get("auth_state"))
        if auth_state != "unknown":
            return auth_state
        reason_code = str(packet.get("reason_code") or "").strip().lower()
        if status == "skipped":
            return "skipped"
        if packet.get("auth_state_updated"):
            return "authenticated"
        if reason_code in {"login", "needs_login"}:
            return "needs_login"
        if reason_code in {
            "verify",
            "captcha",
            "security_confirmation",
            "account_selection",
            "needs_verify",
        }:
            return "needs_verify"
        return "unknown"

    @classmethod
    def _derive_status_from_packet(cls, packet: dict[str, Any]) -> str:
        status = cls._normalize_status(packet.get("status"))
        if status == "failed" and packet.get("skipped_by_user"):
            return "skipped"
        return status

    @staticmethod
    def _merge_timing(packet: dict[str, Any]) -> dict[str, Any]:
        duration = packet.get("duration")
        timing = packet.get("timing_json")
        merged = dict(timing) if isinstance(timing, dict) else {}
        if duration is not None and "total_ms" not in merged:
            try:
                merged["total_ms"] = int(float(duration) * 1000)
            except (TypeError, ValueError):
                pass
        return merged or {}

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if not isinstance(value, str):
            return None
        normalized = value.strip()
        if not normalized:
            return None
        normalized = normalized.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed

    @classmethod
    def _extract_packet_started_at(cls, packet: dict[str, Any]) -> datetime | None:
        timing = packet.get("timing_json")
        candidates = [
            packet.get("started_at"),
            packet.get("fetch_started_at"),
            packet.get("created_at"),
        ]
        if isinstance(timing, dict):
            candidates.extend(
                [
                    timing.get("started_at"),
                    timing.get("fetch_started_at"),
                ]
            )
        for candidate in candidates:
            parsed = cls._parse_datetime(candidate)
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _extract_packet_finished_at(cls, packet: dict[str, Any]) -> datetime | None:
        timing = packet.get("timing_json")
        candidates = [
            packet.get("finished_at"),
            packet.get("fetch_finished_at"),
            packet.get("completed_at"),
            packet.get("updated_at"),
        ]
        if isinstance(timing, dict):
            candidates.extend(
                [
                    timing.get("finished_at"),
                    timing.get("fetch_finished_at"),
                    timing.get("completed_at"),
                ]
            )
        for candidate in candidates:
            parsed = cls._parse_datetime(candidate)
            if parsed is not None:
                return parsed
        return None

    @classmethod
    def _aggregate_packet_timing(
        cls,
        packets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        aggregated: dict[str, int] = {}
        for packet in packets:
            timing = cls._merge_timing(packet)
            for key, value in timing.items():
                numeric = cls._to_int_timing(value)
                if numeric is None:
                    continue
                aggregated[key] = aggregated.get(key, 0) + numeric
        return aggregated

    @staticmethod
    def _merge_timing_maps(
        existing: dict[str, Any] | None,
        incoming: dict[str, Any] | None,
    ) -> dict[str, Any]:
        merged = dict(existing) if isinstance(existing, dict) else {}
        if isinstance(incoming, dict):
            for key, value in incoming.items():
                if value is not None:
                    merged[key] = value
        return merged

    @staticmethod
    def _to_int_timing(value: Any) -> int | None:
        try:
            numeric = int(float(value))
        except (TypeError, ValueError):
            return None
        return numeric if numeric >= 0 else None

    @classmethod
    def _build_timing_summary(
        cls,
        rows: list[FetchRunPlatformState],
    ) -> dict[str, Any]:
        if not rows:
            return {}

        stage_totals_ms: dict[str, int] = {}
        platform_timings: dict[str, dict[str, int]] = {}
        started_points: list[datetime] = []
        finished_points: list[datetime] = []

        for row in rows:
            timing = row.timing_json if isinstance(row.timing_json, dict) else {}
            normalized_timing: dict[str, int] = {}
            for key, value in timing.items():
                numeric = cls._to_int_timing(value)
                if numeric is None:
                    continue
                normalized_timing[key] = numeric
                stage_totals_ms[key] = stage_totals_ms.get(key, 0) + numeric
            if normalized_timing:
                platform_timings[row.platform] = normalized_timing
            started_at = getattr(row, "started_at", None)
            if started_at is not None:
                started_points.append(started_at)
            finished_point = (
                getattr(row, "finished_at", None)
                or getattr(row, "updated_at", None)
                or getattr(row, "created_at", None)
            )
            if finished_point is not None:
                finished_points.append(finished_point)

        total_ms = 0
        if started_points and finished_points:
            total_ms = max(
                0,
                int(
                    (
                        max(finished_points) - min(started_points)
                    ).total_seconds()
                    * 1000
                ),
            )
        if total_ms == 0:
            total_ms = max(
                (
                    timing.get("total_ms", 0)
                    for timing in platform_timings.values()
                    if isinstance(timing.get("total_ms"), int)
                ),
                default=0,
            )

        return {
            "total_ms": total_ms,
            "platforms": platform_timings,
            "stage_totals_ms": stage_totals_ms,
        }

    @classmethod
    def _merge_status(cls, current: str | None, incoming: str | None) -> str:
        current_value = cls._normalize_status(current)
        incoming_value = cls._normalize_status(incoming)
        if current_value == incoming_value:
            return current_value
        if current_value in _TERMINAL_STATUSES and incoming_value not in _TERMINAL_STATUSES:
            return current_value
        if incoming_value in _TERMINAL_STATUSES:
            return incoming_value
        if current_value == "takeover_required" and incoming_value == "running":
            return incoming_value
        if current_value == "pending":
            return incoming_value
        return (
            incoming_value
            if _STATUS_PRIORITY[incoming_value] >= _STATUS_PRIORITY[current_value]
            else current_value
        )

    @classmethod
    def _merge_auth_state(cls, current: str | None, incoming: str | None) -> str:
        current_value = cls._normalize_auth_state(current)
        incoming_value = cls._normalize_auth_state(incoming)
        if incoming_value == "unknown":
            return current_value
        if incoming_value == "skipped":
            return incoming_value
        if incoming_value == "authenticated":
            return incoming_value
        if current_value == "authenticated":
            return current_value
        if current_value == "skipped":
            return current_value
        return incoming_value

    @staticmethod
    def _merge_started_at(
        current: datetime | None,
        incoming: datetime | None,
    ) -> datetime | None:
        if current is None:
            return incoming
        if incoming is None:
            return current
        return current if current <= incoming else incoming

    @staticmethod
    def _resolve_finished_at(
        *,
        merged_status: str,
        current_finished_at: datetime | None,
        incoming_finished_at: datetime | None,
    ) -> datetime | None:
        if merged_status not in _TERMINAL_STATUSES:
            return None
        if current_finished_at is not None:
            return current_finished_at
        return incoming_finished_at

    @classmethod
    def _build_takeover_packet(
        cls,
        *,
        platform: str,
        status: str,
        auth_state: str,
        action_type: str | None,
        reason_code: str | None,
        request_id: str | None,
        target_url: str | None,
        blocking_url: str | None,
        blocking_fingerprint: str | None,
        timing_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "platform": platform,
            "status": status,
            "auth_state": auth_state,
            "action_type": action_type,
            "reason_code": reason_code,
            "request_id": request_id,
            "target_url": target_url,
            "blocking_url": blocking_url,
            "blocking_fingerprint": blocking_fingerprint,
            "timing_json": timing_json or {},
        }

    async def _get_existing_row(
        self,
        *,
        task_run_id: UUID,
        platform: str,
    ) -> FetchRunPlatformState | None:
        stmt = select(FetchRunPlatformState).where(
            FetchRunPlatformState.task_run_id == task_run_id,
            FetchRunPlatformState.platform == platform,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    @classmethod
    def _build_platform_stats(
        cls,
        *,
        platform: str,
        fetch_results: list[dict[str, Any]],
    ) -> dict[str, int]:
        completed = 0
        total = 0
        mentions = 0
        for fetch_result in fetch_results:
            packets = fetch_result.get("aio_platform_packets", []) or []
            platform_packet = next(
                (
                    packet
                    for packet in packets
                    if isinstance(packet, dict)
                    and cls.canonicalize_platform(packet.get("platform")) == platform
                ),
                None,
            )
            if platform_packet is None:
                continue
            total += 1
            status = cls._derive_status_from_packet(platform_packet)
            if status == "succeeded":
                completed += 1
            answer = platform_packet.get("answer")
            if isinstance(answer, dict) and answer.get("has_brand_mention"):
                mentions += 1
        return {
            "completed": completed,
            "total": total,
            "mentions": mentions,
        }

    @classmethod
    def _normalize_packet_projection(
        cls,
        packet: dict[str, Any],
    ) -> dict[str, Any] | None:
        platform = cls.canonicalize_platform(packet.get("platform"))
        status = cls._status_to_projection(packet.get("status"))
        if not platform:
            return None
        normalized: dict[str, Any] = {
            "platform": platform,
            "status": status,
        }
        for key in (
            "auth_state",
            "action_type",
            "reason_code",
            "request_id",
            "target_url",
            "blocking_url",
            "blocking_fingerprint",
            "fetch_method",
            "error",
            "duration",
        ):
            value = packet.get(key)
            if value is not None:
                normalized[key] = value
        answer = packet.get("answer")
        if isinstance(answer, dict):
            normalized["answer"] = answer
        citations = packet.get("citations")
        if isinstance(citations, list):
            normalized["citations"] = citations
        timing_json = packet.get("timing_json")
        if isinstance(timing_json, dict):
            normalized["timing_json"] = timing_json
        if packet.get("skipped_by_user"):
            normalized["skipped_by_user"] = True
        return normalized

    @classmethod
    def _normalize_legacy_projection(
        cls,
        legacy_result: dict[str, Any],
    ) -> dict[str, Any] | None:
        platform = cls.canonicalize_platform(legacy_result.get("platform"))
        if not platform:
            return None
        status = legacy_result.get("status")
        success = legacy_result.get("success")
        if status is None:
            status = "success" if success else "failed"
        normalized_status = cls._status_to_projection(status)
        normalized: dict[str, Any] = {
            "platform": platform,
            "platform_name": legacy_result.get("platform_name")
            or legacy_result.get("platform")
            or platform,
            "status": normalized_status,
            "success": normalized_status == "success",
        }
        for key in ("fetch_method", "error", "duration"):
            value = legacy_result.get(key)
            if value is not None:
                normalized[key] = value
        answer = legacy_result.get("answer")
        if isinstance(answer, dict):
            normalized["answer"] = answer
        elif isinstance(answer, str):
            normalized["answer"] = {"content": answer}
        citations = legacy_result.get("citations")
        if isinstance(citations, list):
            normalized["citations"] = citations
        return normalized

    @classmethod
    def _merge_projection_result(
        cls,
        legacy_result: dict[str, Any] | None,
        packet: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        if legacy_result is None and packet is None:
            return None
        platform = cls.canonicalize_platform(
            (packet or {}).get("platform") or (legacy_result or {}).get("platform")
        )
        status = cls._status_to_projection(
            (packet or {}).get("status")
            or (legacy_result or {}).get("status")
            or ("success" if (legacy_result or {}).get("success") else "failed")
        )
        merged: dict[str, Any] = {
            "platform": platform,
            "platform_name": (
                (legacy_result or {}).get("platform_name")
                or (packet or {}).get("platform")
                or (legacy_result or {}).get("platform")
                or platform
            ),
            "status": status,
            "success": status == "success",
        }
        merged["fetch_method"] = (
            (packet or {}).get("fetch_method") or (legacy_result or {}).get("fetch_method")
        )
        merged["answer"] = (packet or {}).get("answer") or (legacy_result or {}).get("answer")
        merged["citations"] = (
            (packet or {}).get("citations")
            if isinstance((packet or {}).get("citations"), list) and (packet or {}).get("citations")
            else (legacy_result or {}).get("citations")
        )
        merged["error"] = (
            (packet or {}).get("error")
            or (legacy_result or {}).get("error")
            or ("已跳过该平台" if status == "skipped" else None)
        )
        merged["duration"] = (
            (packet or {}).get("duration")
            if (packet or {}).get("duration") is not None
            else (legacy_result or {}).get("duration")
        )
        return merged

    @classmethod
    def _build_rows_from_fetch_results(
        cls,
        *,
        task_run_id: UUID,
        task_id: UUID,
        session_id: UUID | None,
        entity_id: UUID | None,
        user_id: UUID,
        fetch_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        platform_packets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for fetch_result in fetch_results:
            for packet in fetch_result.get("aio_platform_packets", []) or []:
                if not isinstance(packet, dict):
                    continue
                platform = cls.canonicalize_platform(packet.get("platform"))
                if not platform:
                    continue
                platform_packets[platform].append(packet)

        rows: list[dict[str, Any]] = []
        for platform, packets in platform_packets.items():
            latest_packet = packets[-1]
            status = cls._derive_status_from_packet(latest_packet)
            auth_state = cls._project_auth_state(latest_packet, status)
            timing_json = cls._aggregate_packet_timing(packets)
            packet_entries: list[dict[str, Any]] = []
            for fetch_result in fetch_results:
                question_id = fetch_result.get("question_id") or ""
                question_text = fetch_result.get("question_text") or ""
                platform_packet = next(
                    (
                        packet
                        for packet in fetch_result.get("aio_platform_packets", []) or []
                        if isinstance(packet, dict)
                        and cls.canonicalize_platform(packet.get("platform")) == platform
                    ),
                    None,
                )
                legacy_result = next(
                    (
                        result
                        for result in fetch_result.get("platform_results", []) or []
                        if cls.canonicalize_platform(result.get("platform")) == platform
                    ),
                    None,
                )
                if platform_packet is None and legacy_result is None:
                    continue
                packet_entries.append(
                    {
                        "question_id": question_id,
                        "question_text": question_text,
                        "packet": platform_packet,
                        "legacy_result": legacy_result,
                    }
                )
            started_points = [
                started_at
                for packet in packets
                if (started_at := cls._extract_packet_started_at(packet)) is not None
            ]
            finished_points = [
                finished_at
                for packet in packets
                if (finished_at := cls._extract_packet_finished_at(packet)) is not None
            ]
            started_at = min(started_points) if started_points else None
            finished_at = max(finished_points) if finished_points else None

            rows.append(
                {
                    "task_run_id": task_run_id,
                    "task_id": task_id,
                    "session_id": session_id,
                    "entity_id": entity_id,
                    "user_id": user_id,
                    "platform": platform,
                    "status": status,
                    "attempt_no": max(1, len(packets)),
                    "auth_state": auth_state,
                    "latest_packet": {
                        "platform": platform,
                        "status": status,
                        "auth_state": auth_state,
                        "question_results": packet_entries,
                        "stats": cls._build_platform_stats(
                            platform=platform,
                            fetch_results=fetch_results,
                        ),
                    },
                    "latest_takeover_request_id": latest_packet.get("request_id"),
                    "latest_blocking_fingerprint": latest_packet.get(
                        "blocking_fingerprint"
                    ),
                    "artifact_write_status": None,
                    "error_kind": latest_packet.get("error_type"),
                    "error_message": latest_packet.get("error"),
                    "timing_json": timing_json,
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
            )
        return rows

    async def upsert_many(self, rows: list[dict[str, Any]]) -> list[FetchRunPlatformState]:
        persisted: list[FetchRunPlatformState] = []
        now = datetime.now(timezone.utc)
        for row in rows:
            existing = await self._get_existing_row(
                task_run_id=row["task_run_id"],
                platform=row["platform"],
            )
            if existing is None:
                existing = FetchRunPlatformState(**row)
                self.db.add(existing)
            else:
                merged_status = self._merge_status(existing.status, row.get("status"))
                merged_auth_state = self._merge_auth_state(
                    existing.auth_state,
                    row.get("auth_state"),
                )
                existing.task_id = row.get("task_id", existing.task_id)
                existing.session_id = row.get("session_id", existing.session_id)
                existing.entity_id = row.get("entity_id", existing.entity_id)
                existing.user_id = row.get("user_id", existing.user_id)
                existing.platform = row.get("platform", existing.platform)
                existing.status = merged_status
                existing.attempt_no = max(
                    int(existing.attempt_no or 1),
                    int(row.get("attempt_no") or 1),
                )
                existing.auth_state = merged_auth_state
                if row.get("latest_packet") is not None:
                    existing.latest_packet = row.get("latest_packet")
                existing.latest_takeover_request_id = (
                    row.get("latest_takeover_request_id")
                    or existing.latest_takeover_request_id
                )
                existing.latest_blocking_fingerprint = (
                    row.get("latest_blocking_fingerprint")
                    or existing.latest_blocking_fingerprint
                )
                existing.artifact_write_status = (
                    row.get("artifact_write_status")
                    if row.get("artifact_write_status") is not None
                    else existing.artifact_write_status
                )
                existing.error_kind = (
                    row.get("error_kind")
                    if row.get("error_kind") is not None
                    else existing.error_kind
                )
                existing.error_message = (
                    row.get("error_message")
                    if row.get("error_message") is not None
                    else existing.error_message
                )
                existing.timing_json = self._merge_timing_maps(
                    existing.timing_json,
                    row.get("timing_json"),
                )
                existing.started_at = self._merge_started_at(
                    existing.started_at,
                    row.get("started_at"),
                )
                existing.finished_at = self._resolve_finished_at(
                    merged_status=merged_status,
                    current_finished_at=existing.finished_at,
                    incoming_finished_at=row.get("finished_at"),
                )
                existing.updated_at = now
            persisted.append(existing)
        await self.db.flush()
        return persisted

    async def upsert_browser_action_state(
        self,
        *,
        task_run_id: UUID,
        task_id: UUID,
        session_id: UUID | None,
        entity_id: UUID | None,
        user_id: UUID,
        platform: str,
        status: str,
        request_id: str | None,
        action_type: str | None,
        reason_code: str | None,
        target_url: str | None,
        blocking_url: str | None,
        blocking_fingerprint: str | None,
        auth_state: str | None = None,
        timing_json: dict[str, Any] | None = None,
        error_kind: str | None = None,
        error_message: str | None = None,
    ) -> FetchRunPlatformState:
        normalized_platform = self.canonicalize_platform(platform)
        normalized_status = self._normalize_status(status)
        normalized_auth_state = self._merge_auth_state(
            "unknown",
            auth_state
            or (
                "needs_login"
                if str(reason_code or "").strip().lower() in {"login", "needs_login"}
                else "needs_verify"
                if str(reason_code or "").strip().lower()
                in {
                    "verify",
                    "captcha",
                    "security_confirmation",
                    "account_selection",
                    "needs_verify",
                }
                else "unknown"
            ),
        )
        packet = self._build_takeover_packet(
            platform=normalized_platform,
            status=normalized_status,
            auth_state=normalized_auth_state,
            action_type=action_type,
            reason_code=reason_code,
            request_id=request_id,
            target_url=target_url,
            blocking_url=blocking_url,
            blocking_fingerprint=blocking_fingerprint,
            timing_json=timing_json,
        )
        row = {
            "task_run_id": task_run_id,
            "task_id": task_id,
            "session_id": session_id,
            "entity_id": entity_id,
            "user_id": user_id,
            "platform": normalized_platform,
            "status": normalized_status,
            "attempt_no": 1,
            "auth_state": normalized_auth_state,
            "latest_packet": packet,
            "latest_takeover_request_id": request_id,
            "latest_blocking_fingerprint": blocking_fingerprint,
            "artifact_write_status": None,
            "error_kind": error_kind,
            "error_message": error_message,
            "timing_json": timing_json or {},
            "started_at": None,
            "finished_at": None,
        }
        persisted = await self.upsert_many([row])
        return persisted[0]

    async def mark_browser_action_resolution(
        self,
        *,
        task_run_id: UUID,
        platform: str,
        resolution: str,
        request_id: str | None = None,
        auth_state: str | None = None,
        timing_json: dict[str, Any] | None = None,
    ) -> FetchRunPlatformState | None:
        normalized_platform = self.canonicalize_platform(platform)
        existing = await self._get_existing_row(
            task_run_id=task_run_id,
            platform=normalized_platform,
        )
        if existing is None:
            return None

        normalized_resolution = str(resolution or "").strip().lower()
        next_status = "skipped" if normalized_resolution == "skip" else "running"
        next_auth_state = (
            self._merge_auth_state(existing.auth_state, auth_state or "skipped")
            if next_status == "skipped"
            else self._merge_auth_state(existing.auth_state, auth_state)
        )
        packet = dict(existing.latest_packet) if isinstance(existing.latest_packet, dict) else {}
        packet.update(
            {
                "platform": normalized_platform,
                "status": next_status,
                "auth_state": next_auth_state,
                "request_id": request_id or existing.latest_takeover_request_id,
                "timing_json": self._merge_timing_maps(
                    packet.get("timing_json") if isinstance(packet.get("timing_json"), dict) else {},
                    timing_json,
                ),
            }
        )
        rows = await self.upsert_many(
            [
                {
                    "task_run_id": existing.task_run_id,
                    "task_id": existing.task_id,
                    "session_id": existing.session_id,
                    "entity_id": existing.entity_id,
                    "user_id": existing.user_id,
                    "platform": normalized_platform,
                    "status": next_status,
                    "attempt_no": existing.attempt_no,
                    "auth_state": next_auth_state,
                    "latest_packet": packet,
                    "latest_takeover_request_id": request_id
                    or existing.latest_takeover_request_id,
                    "latest_blocking_fingerprint": existing.latest_blocking_fingerprint,
                    "artifact_write_status": existing.artifact_write_status,
                    "error_kind": None if next_status == "running" else existing.error_kind,
                    "error_message": None if next_status == "running" else existing.error_message,
                    "timing_json": timing_json or {},
                    "started_at": existing.started_at,
                    "finished_at": existing.finished_at,
                }
            ]
        )
        return rows[0]

    async def sync_fetch_results(
        self,
        *,
        task_run_id: UUID,
        task_id: UUID,
        session_id: UUID | None,
        entity_id: UUID | None,
        user_id: UUID,
        fetch_results: list[dict[str, Any]],
    ) -> list[FetchRunPlatformState]:
        rows = self._build_rows_from_fetch_results(
            task_run_id=task_run_id,
            task_id=task_id,
            session_id=session_id,
            entity_id=entity_id,
            user_id=user_id,
            fetch_results=fetch_results,
        )
        return await self.upsert_many(rows)

    async def mark_artifact_write_status(
        self,
        *,
        task_run_id: UUID,
        status: str,
    ) -> None:
        rows = await self.list_for_task_run(task_run_id)
        for row in rows:
            row.artifact_write_status = status
        await self.db.flush()

    async def list_for_task_run(self, task_run_id: UUID) -> list[FetchRunPlatformState]:
        stmt = (
            select(FetchRunPlatformState)
            .where(FetchRunPlatformState.task_run_id == task_run_id)
            .order_by(FetchRunPlatformState.platform.asc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_for_task(self, task_id: UUID) -> list[FetchRunPlatformState]:
        stmt = (
            select(FetchRunPlatformState)
            .where(FetchRunPlatformState.task_id == task_id)
            .order_by(
                FetchRunPlatformState.updated_at.desc(),
                FetchRunPlatformState.created_at.desc(),
                FetchRunPlatformState.task_run_id.desc(),
                FetchRunPlatformState.platform.asc(),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_for_task(self, task_id: UUID) -> list[FetchRunPlatformState]:
        rows = await self.list_for_task(task_id)
        if not rows:
            return []
        latest_run_id = rows[0].task_run_id
        return [row for row in rows if row.task_run_id == latest_run_id]

    async def list_for_session(self, session_id: UUID) -> list[FetchRunPlatformState]:
        stmt = (
            select(FetchRunPlatformState)
            .where(FetchRunPlatformState.session_id == session_id)
            .order_by(
                FetchRunPlatformState.updated_at.desc(),
                FetchRunPlatformState.created_at.desc(),
                FetchRunPlatformState.task_run_id.desc(),
                FetchRunPlatformState.platform.asc(),
            )
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_latest_for_session(
        self,
        session_id: UUID,
    ) -> list[FetchRunPlatformState]:
        rows = await self.list_for_session(session_id)
        if not rows:
            return []
        latest_run_id = rows[0].task_run_id
        return [row for row in rows if row.task_run_id == latest_run_id]

    def build_platform_status_projection(
        self,
        rows: list[FetchRunPlatformState],
    ) -> dict[str, Any]:
        platforms: list[dict[str, Any]] = []
        statuses: dict[str, str] = {}
        for row in rows:
            packet = row.latest_packet if isinstance(row.latest_packet, dict) else {}
            platform_stats = packet.get("stats", {}) if isinstance(packet, dict) else {}
            legacy_status = self._status_to_legacy(row.status)
            statuses[row.platform] = legacy_status
            platforms.append(
                {
                    "platform": row.platform,
                    "status": legacy_status,
                    "questions_completed": int(platform_stats.get("completed", 0) or 0),
                    "questions_total": int(platform_stats.get("total", 0) or 0),
                    "mention_count": int(platform_stats.get("mentions", 0) or 0),
                    "error": row.error_message,
                    "auth_state": row.auth_state,
                    "artifact_write_status": row.artifact_write_status,
                    "timing": row.timing_json or {},
                }
            )
        return {
            "platforms": platforms,
            "platform_statuses": statuses,
        }

    def build_fetch_results_projection(
        self,
        rows: list[FetchRunPlatformState],
    ) -> list[dict[str, Any]]:
        by_question: dict[str, dict[str, Any]] = {}
        for row in rows:
            packet = row.latest_packet if isinstance(row.latest_packet, dict) else {}
            question_results = packet.get("question_results", [])
            if not isinstance(question_results, list):
                continue
            for packet_item in question_results:
                if not isinstance(packet_item, dict):
                    continue
                question_id = packet_item.get("question_id") or ""
                question_text = packet_item.get("question_text") or ""
                question_entry = by_question.setdefault(
                    question_id,
                    {
                        "question_id": question_id,
                        "question_text": question_text,
                        "platform_results": [],
                        "aio_platform_packets": [],
                    },
                )
                packet_payload = self._normalize_packet_projection(
                    packet_item.get("packet")
                ) if isinstance(packet_item.get("packet"), dict) else None
                legacy_result = self._normalize_legacy_projection(
                    packet_item.get("legacy_result")
                ) if isinstance(packet_item.get("legacy_result"), dict) else None

                if packet_payload is not None:
                    packets_by_platform = question_entry.setdefault(
                        "_packets_by_platform",
                        {},
                    )
                    packets_by_platform[packet_payload["platform"]] = packet_payload

                merged_result = self._merge_projection_result(
                    legacy_result=legacy_result,
                    packet=packet_payload,
                )
                if merged_result is not None:
                    merged_results_by_platform = question_entry.setdefault(
                        "_results_by_platform",
                        {},
                    )
                    merged_results_by_platform[merged_result["platform"]] = merged_result

        projection: list[dict[str, Any]] = []
        for item in sorted(
            by_question.values(),
            key=lambda entry: str(entry.get("question_id") or ""),
        ):
            packets_by_platform = item.pop("_packets_by_platform", {})
            results_by_platform = item.pop("_results_by_platform", {})
            item["aio_platform_packets"] = list(packets_by_platform.values())
            item["platform_results"] = list(results_by_platform.values())
            projection.append(item)
        return projection

    def build_summary_projection(
        self,
        rows: list[FetchRunPlatformState],
    ) -> dict[str, Any]:
        platform_status = self.build_platform_status_projection(rows)
        fetch_results = self.build_fetch_results_projection(rows)
        timing_summary = self._build_timing_summary(rows)
        success_count = sum(
            1 for row in rows if self._status_to_legacy(row.status) == "success"
        )
        fail_count = sum(
            1
            for row in rows
            if self._status_to_legacy(row.status) == "failed"
        )
        skipped_count = sum(1 for row in rows if row.status == "skipped")
        return {
            "fetch_results": fetch_results,
            "platform_status": platform_status,
            "timing_summary": timing_summary,
            "success_count": success_count,
            "fail_count": fail_count,
            "skipped_count": skipped_count,
        }
