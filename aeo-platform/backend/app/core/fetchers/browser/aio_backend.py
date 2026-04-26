"""AIO-backed browser execution subset for Specta A4 integration."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from typing import Any

from app.core.fetchers.browser.aio_client import AioBackendError, AioCodeExecuteResult
from app.services.aio_runtime_contracts import AioBlockerCode
from app.services.aio_session_manager import SpectaAioTakeover, aio_session_manager


_AIO_KEY_ALIASES = {
    "Enter": "enter",
    "Return": "return",
    "Escape": "escape",
    "Esc": "escape",
    "Backspace": "backspace",
    "Delete": "delete",
    "Tab": "tab",
    "Space": "space",
}


@dataclass(frozen=True, slots=True)
class AioVisibleRuntime:
    """Minimal runtime handle exposed to A4 V1."""

    session_id: str
    sandbox_ref: str
    base_url: str
    cdp_url: str | None
    vnc_url: str | None
    platform: str
    profile_root: str
    run_root: str
    cookies_path: str
    state_path: str
    session_meta_path: str
    checkpoint_root: str
    snapshot_root: str
    download_root: str
    extraction_path: str


class AioSandboxBackend:
    """Minimal A4-visible subset of the AIO backend adapter.

    This class intentionally stays within the A4 V1 visible subset:
    navigation/interaction, perception, extraction, state save/load and
    takeover handoff. Shell/file/code helpers remain internal-only helpers.
    """

    async def ensure_runtime(
        self,
        *,
        workspace_id: str,
        task_id: str,
        platform: str,
        purpose: str = "a4",
    ) -> AioVisibleRuntime:
        session = await aio_session_manager.acquire_session(
            workspace_id=workspace_id,
            task_id=task_id,
            purpose=purpose,
            platforms=[platform],
        )
        roots = await aio_session_manager.ensure_platform_roots(
            session_id=session.session_id,
            task_id=task_id,
            platform=platform,
        )
        browser = await aio_session_manager.get_browser_connection(session.session_id)
        return AioVisibleRuntime(
            session_id=session.session_id,
            sandbox_ref=session.sandbox_ref,
            base_url=session.base_url,
            cdp_url=browser["cdp_url"],
            vnc_url=browser["vnc_url"],
            platform=platform,
            profile_root=roots.profile_root,
            run_root=roots.run_root,
            cookies_path=roots.cookies_path,
            state_path=roots.state_path,
            session_meta_path=roots.session_meta_path,
            checkpoint_root=roots.checkpoint_root,
            snapshot_root=roots.snapshot_root,
            download_root=roots.download_root,
            extraction_path=roots.extraction_path,
        )

    async def request_takeover(
        self,
        *,
        session_id: str,
        user_id: str,
        platform: str,
        mode: str,
        reason: str,
    ) -> SpectaAioTakeover:
        return await aio_session_manager.create_takeover_access(
            session_id=session_id,
            user_id=user_id,
            platform=platform,
            mode=mode,
            reason=reason,
        )

    async def get_browser_connection(self, session_id: str) -> dict[str, Any]:
        return await aio_session_manager.get_browser_connection(session_id)

    async def configure_browser_surface(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
        preferred_url: str = "about:blank",
    ) -> dict[str, Any]:
        """Configure and stabilize the AIO browser surface before takeover."""

        client = aio_session_manager.get_runtime_client()
        config = await client.set_browser_config(width=width, height=height)
        stabilized = await client.stabilize_browser_surface(
            preferred_url=preferred_url,
            allow_blank_fallback=True,
        )
        return {
            "config_applied": config.applied,
            "stabilized": stabilized,
        }

    async def execute_action(
        self,
        *,
        action_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute one validated AIO browser action against the live display."""

        action_payload = self._normalize_browser_action_payload(action_payload)
        result = await aio_session_manager.get_runtime_client().execute_browser_action(
            action_payload
        )
        return {
            "status": result.status,
            "action_performed": result.action_performed,
            "detail": result.detail,
        }

    @staticmethod
    def _normalize_browser_action_payload(
        action_payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize Playwright-style key aliases into AIO GUI action keys."""

        normalized = dict(action_payload)
        action_type = str(normalized.get("action_type") or "").upper()
        if action_type not in {"PRESS", "KEY_DOWN", "KEY_UP"}:
            return normalized

        key = normalized.get("key")
        if isinstance(key, str):
            normalized["key"] = _AIO_KEY_ALIASES.get(key, key)
        return normalized

    async def wait(self, *, duration_seconds: float) -> dict[str, Any]:
        """Small convenience wrapper over the official WAIT action."""

        return await self.execute_action(
            action_payload={
                "action_type": "WAIT",
                "duration": duration_seconds,
            }
        )

    async def take_screenshot(self) -> dict[str, Any]:
        """Capture the current AIO display for diagnostics or takeover preview."""

        shot = await aio_session_manager.get_runtime_client().take_browser_screenshot()
        return {
            "content_type": shot.content_type,
            "screen_width": shot.screen_width,
            "screen_height": shot.screen_height,
            "image_width": shot.image_width,
            "image_height": shot.image_height,
            "image_base64": base64.b64encode(shot.image_bytes).decode("ascii"),
        }

    async def load_runtime_state(self, runtime: AioVisibleRuntime) -> dict[str, Any] | None:
        """Load persisted browser state from the canonical profile_root files."""

        client = aio_session_manager.get_runtime_client()
        state_file = await client.read_text_file(runtime.state_path, missing_ok=True)
        if state_file is None or not state_file.content.strip():
            return None
        try:
            payload = json.loads(state_file.content)
        except json.JSONDecodeError as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.STATE_INVALID.value,
                recover_hint="reset_persisted_state",
                transport_used="rest",
                retryable=False,
                detail=f"Invalid browser_state.json: {exc}",
            ) from exc
        await aio_session_manager.mark_platform_state_loaded(
            session_id=runtime.session_id,
            task_id=self._derive_task_id(runtime),
            platform=runtime.platform,
        )
        return payload if isinstance(payload, dict) else None

    async def save_runtime_state(
        self,
        runtime: AioVisibleRuntime,
        *,
        browser_state: dict[str, Any],
        cookies: list[dict[str, Any]] | None = None,
    ) -> None:
        """Persist browser state into the canonical AIO profile files."""

        client = aio_session_manager.get_runtime_client()
        await client.write_text_file(
            runtime.state_path,
            json.dumps(browser_state, ensure_ascii=False, indent=2),
        )
        if cookies is not None:
            await client.write_text_file(
                runtime.cookies_path,
                json.dumps(cookies, ensure_ascii=False, indent=2),
            )
        await aio_session_manager.mark_platform_state_saved(
            session_id=runtime.session_id,
            task_id=self._derive_task_id(runtime),
            platform=runtime.platform,
        )

    async def persist_extraction(
        self,
        runtime: AioVisibleRuntime,
        *,
        payload: dict[str, Any],
    ) -> None:
        """Persist one extraction artifact under the task-scoped run_root."""

        await aio_session_manager.get_runtime_client().write_text_file(
            runtime.extraction_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    async def read_extraction(
        self,
        runtime: AioVisibleRuntime,
    ) -> dict[str, Any] | None:
        """Read the current extraction artifact, if any."""

        result = await aio_session_manager.get_runtime_client().read_text_file(
            runtime.extraction_path,
            missing_ok=True,
        )
        if result is None or not result.content.strip():
            return None
        try:
            payload = json.loads(result.content)
        except json.JSONDecodeError as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.STATE_INVALID.value,
                recover_hint="inspect_extraction_artifact",
                transport_used="rest",
                retryable=False,
                detail=f"Invalid extraction.json: {exc}",
            ) from exc
        return payload if isinstance(payload, dict) else None

    async def execute_internal_code(
        self,
        *,
        language: str,
        code: str,
        timeout_seconds: int | None = None,
    ) -> AioCodeExecuteResult:
        """Internal-only code execution helper for controlled extraction logic."""

        return await aio_session_manager.get_runtime_client().execute_code(
            language=language,
            code=code,
            timeout_seconds=timeout_seconds,
        )

    @staticmethod
    def _derive_task_id(runtime: AioVisibleRuntime) -> str:
        parts = runtime.run_root.rstrip("/").split("/")
        if len(parts) >= 4:
            return parts[-3]
        return "unknown"
