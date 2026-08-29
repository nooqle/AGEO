from __future__ import annotations

import base64
import json
import os
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FAILURE_LAYERS = {"client", "adapter", "executor", "orchestrator"}
FAILURE_REASONS = {
    "navigation_failed",
    "browser_context_closed",
    "submission_not_confirmed",
    "network_intercept_empty",
    "dom_extraction_empty",
    "empty_answer",
    "risk_control_page",
    "page_runtime_retry_or_risk_control",
    "parser_error",
    "question_timeout",
    "verify_required",
    "modal_blocked",
    "auth_required",
    "global_timeout",
    "rate_limit",
    "resume_gate_failed",
}

_FAILURE_REASON_ALIASES = {
    "target_closed": "browser_context_closed",
    "page_closed": "browser_context_closed",
    "context_closed": "browser_context_closed",
    "verify": "verify_required",
    "captcha": "verify_required",
    "needs_verify": "verify_required",
    "login": "auth_required",
    "needs_login": "auth_required",
    "modal_timeout": "modal_blocked",
    "modal_reopen_failed": "modal_blocked",
    "empty_response": "empty_answer",
    "risk_control": "risk_control_page",
    "runtime_retry": "page_runtime_retry_or_risk_control",
    "runtime_risk_control": "page_runtime_retry_or_risk_control",
    "page_runtime_risk_control": "page_runtime_retry_or_risk_control",
}

_FAILURE_LAYER_BY_REASON = {
    "navigation_failed": "client",
    "browser_context_closed": "client",
    "submission_not_confirmed": "executor",
    "network_intercept_empty": "executor",
    "dom_extraction_empty": "adapter",
    "empty_answer": "adapter",
    "risk_control_page": "adapter",
    "page_runtime_retry_or_risk_control": "adapter",
    "parser_error": "adapter",
    "question_timeout": "executor",
    "verify_required": "adapter",
    "modal_blocked": "adapter",
    "auth_required": "adapter",
    "global_timeout": "orchestrator",
    "rate_limit": "executor",
    "resume_gate_failed": "executor",
}

_BROWSER_CONTEXT_CLOSED_MARKERS = (
    "target page, context or browser has been closed",
    "target page has been closed",
    "context has been closed",
    "browser has been closed",
    "page has been closed",
    "target closed",
    "target crashed",
    "page crashed",
    "renderer process crashed",
    "aw, snap",
    "sigtrap",
)


def is_browser_context_closed_error(error: BaseException | str | None) -> bool:
    message = str(error or "").strip().lower()
    if not message:
        return False
    return any(marker in message for marker in _BROWSER_CONTEXT_CLOSED_MARKERS)


def normalize_failure_reason(reason: str | None) -> str:
    value = str(reason or "").strip().lower()
    if not value:
        return "parser_error"
    value = _FAILURE_REASON_ALIASES.get(value, value)
    return value if value in FAILURE_REASONS else "parser_error"


def infer_failure_layer(reason: str | None, fallback: str = "executor") -> str:
    normalized = normalize_failure_reason(reason)
    return _FAILURE_LAYER_BY_REASON.get(normalized, fallback)


def build_failure_contract(
    *,
    failure_reason: str | None,
    execution_stage: str | None,
    retryable: bool | None = None,
    needs_handoff: bool | None = None,
    failure_layer: str | None = None,
    evidence_ref: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized_reason = normalize_failure_reason(failure_reason)
    resolved_layer = failure_layer or infer_failure_layer(normalized_reason)
    return {
        "failure_layer": (
            resolved_layer if resolved_layer in FAILURE_LAYERS else "executor"
        ),
        "failure_reason": normalized_reason,
        "execution_stage": str(execution_stage or "unknown").strip().lower(),
        "retryable": bool(retryable) if retryable is not None else False,
        "needs_handoff": bool(needs_handoff) if needs_handoff is not None else False,
        "evidence_ref": evidence_ref,
    }


class BrowserFailureEvidenceService:
    """Persist short-lived browser failure evidence bundles to local storage."""

    def __init__(
        self,
        *,
        root_dir: str | os.PathLike[str] | None = None,
        retention_days: int = 7,
    ) -> None:
        self.root_dir = Path(root_dir) if root_dir else self._default_root_dir()
        self.retention_days = retention_days

    @staticmethod
    def _default_root_dir() -> Path:
        configured = os.getenv("A4_FAILURE_EVIDENCE_DIR")
        if configured:
            return Path(configured)
        if os.name != "nt":
            return Path("/srv/ageo/runtime/failure-evidence")
        return Path.cwd() / "runtime" / "failure-evidence"

    @staticmethod
    def _slug(value: str, *, fallback: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", str(value or "").strip())[:64].strip("-")
        return slug or fallback

    @staticmethod
    def _resolve_screenshot_bytes(
        screenshot_payload: dict[str, Any] | bytes | bytearray | None,
    ) -> bytes | None:
        if screenshot_payload is None:
            return None
        if isinstance(screenshot_payload, (bytes, bytearray)):
            return bytes(screenshot_payload)
        image_base64 = screenshot_payload.get("image_base64")
        if not isinstance(image_base64, str) or not image_base64.strip():
            return None
        try:
            return base64.b64decode(image_base64)
        except Exception:
            return None

    def capture(
        self,
        *,
        platform: str,
        question_id: str | None,
        failure_reason: str,
        execution_stage: str,
        current_url: str | None,
        screenshot_payload: dict[str, Any] | bytes | bytearray | None = None,
        text_snapshot: str | None = None,
        metadata: dict[str, Any] | None = None,
        captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        timestamp = captured_at or datetime.now(timezone.utc)
        evidence_id = (
            f"{self._slug(platform, fallback='platform')}_"
            f"{self._slug(question_id or 'unknown', fallback='unknown')}_"
            f"{self._slug(failure_reason, fallback='failure')}_"
            f"{timestamp.strftime('%Y%m%dT%H%M%S%fZ')}"
        )
        day_dir = self.root_dir / timestamp.strftime("%Y-%m-%d")
        evidence_dir = day_dir / evidence_id
        evidence_dir.mkdir(parents=True, exist_ok=True)

        screenshot_path: str | None = None
        screenshot_bytes = self._resolve_screenshot_bytes(screenshot_payload)
        if screenshot_bytes:
            image_path = evidence_dir / "screenshot.png"
            image_path.write_bytes(screenshot_bytes)
            screenshot_path = str(image_path)

        text_path: str | None = None
        if isinstance(text_snapshot, str) and text_snapshot.strip():
            snapshot_path = evidence_dir / "snapshot.txt"
            snapshot_path.write_text(text_snapshot, encoding="utf-8")
            text_path = str(snapshot_path)

        payload = {
            "evidence_id": evidence_id,
            "platform": platform,
            "question_id": question_id,
            "failure_reason": normalize_failure_reason(failure_reason),
            "execution_stage": str(execution_stage or "unknown").strip().lower(),
            "current_url": current_url,
            "captured_at": timestamp.isoformat(),
            "screenshot_path": screenshot_path,
            "text_snapshot_path": text_path,
            "metadata": metadata or {},
        }
        metadata_path = evidence_dir / "metadata.json"
        metadata_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return {
            "evidence_id": evidence_id,
            "storage_kind": "filesystem",
            "captured_at": payload["captured_at"],
            "screenshot_path": screenshot_path,
            "metadata_path": str(metadata_path),
            "text_snapshot_path": text_path,
        }

    def cleanup_expired(self, *, now: datetime | None = None) -> int:
        root = self.root_dir
        if not root.exists():
            return 0

        cutoff = (now or datetime.now(timezone.utc)) - timedelta(
            days=self.retention_days
        )
        deleted = 0
        for entry in root.iterdir():
            if not entry.is_dir():
                continue
            try:
                entry_date = datetime.strptime(entry.name, "%Y-%m-%d").replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue
            if entry_date < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
                deleted += 1
        return deleted
