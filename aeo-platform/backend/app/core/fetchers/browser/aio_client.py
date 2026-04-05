"""Official AIO Sandbox REST client used by Specta backend adapters."""

from __future__ import annotations

from dataclasses import dataclass
import json
import shlex
from typing import Any

import httpx
import websockets

from app.services.aio_runtime_contracts import AioBlockerCode


@dataclass(frozen=True, slots=True)
class AioSandboxInfo:
    """Runtime metadata returned by GET /v1/sandbox."""

    base_url: str
    version: str | None
    home_dir: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioBrowserInfo:
    """Browser metadata returned by GET /v1/browser/info."""

    cdp_url: str | None
    vnc_url: str | None
    user_agent: str | None
    viewport: dict[str, Any] | None
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioAuthInfo:
    """Auth inspection payload returned by GET /auth."""

    authenticated: bool
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioTicket:
    """One-time ticket returned by POST /tickets."""

    ticket: str
    expires_in: int | None
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioFileReadResult:
    """File payload returned by POST /v1/file/read."""

    file: str
    content: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioFileWriteResult:
    """File payload returned by POST /v1/file/write."""

    file: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioFileListResult:
    """Directory payload returned by POST /v1/file/list."""

    path: str
    files: list[dict[str, Any]]
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioShellCommandResult:
    """Command payload returned by POST /v1/shell/exec."""

    session_id: str | None
    command: str
    status: str | None
    output: str
    exit_code: int | None
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioBrowserActionResult:
    """Browser action payload returned by POST /v1/browser/actions."""

    status: str
    action_performed: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioBrowserConfigResult:
    """Browser configuration payload returned by POST /v1/browser/config."""

    applied: bool
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioBrowserScreenshot:
    """Screenshot bytes and metadata returned by GET /v1/browser/screenshot."""

    content_type: str
    image_bytes: bytes
    screen_width: int | None
    screen_height: int | None
    image_width: int | None
    image_height: int | None


@dataclass(frozen=True, slots=True)
class AioFileReplaceResult:
    """Replace result returned by POST /v1/file/replace."""

    file: str
    replaced_count: int
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioShellSessionInfo:
    """One shell session entry from GET /v1/shell/sessions."""

    session_id: str
    working_dir: str
    created_at: str
    last_used_at: str
    age_seconds: int
    status: str
    current_command: str | None


@dataclass(frozen=True, slots=True)
class AioShellCreateSessionResult:
    """Session creation payload returned by POST /v1/shell/sessions/create."""

    session_id: str
    working_dir: str
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioShellSessionsResult:
    """Shell sessions payload returned by GET /v1/shell/sessions."""

    sessions: dict[str, AioShellSessionInfo]
    detail: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AioCodeExecuteResult:
    """Code execution payload returned by POST /v1/code/execute."""

    language: str
    status: str
    code: str
    stdout: str | None
    stderr: str | None
    exit_code: int | None
    outputs: list[dict[str, Any]]
    detail: dict[str, Any]


class AioBackendError(RuntimeError):
    """Normalized AIO adapter error."""

    def __init__(
        self,
        *,
        error_code: str,
        recover_hint: str,
        transport_used: str,
        retryable: bool,
        detail: str,
        status_code: int | None = None,
    ) -> None:
        super().__init__(detail)
        self.error_code = error_code
        self.recover_hint = recover_hint
        self.transport_used = transport_used
        self.retryable = retryable
        self.detail = detail
        self.status_code = status_code

    def to_dict(self) -> dict[str, Any]:
        """Serialize the normalized error payload for HTTP responses."""

        return {
            "error_code": self.error_code,
            "recover_hint": self.recover_hint,
            "transport_used": self.transport_used,
            "retryable": self.retryable,
            "detail": self.detail,
            "status_code": self.status_code,
        }


class AioSandboxClient:
    """Thin async REST client for official AIO endpoints.

    The client intentionally stays REST-first. Higher-level policy, retries and
    takeover orchestration live elsewhere.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_token: str | None = None,
        timeout_seconds: float = 20.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        return headers

    @staticmethod
    def _is_internal_browser_page(url: str | None) -> bool:
        if not url:
            return True
        lowered = url.lower()
        return lowered.startswith(
            ("chrome://", "chrome-untrusted://", "devtools://")
        )

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    json=json_body,
                    params=params,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="check_runtime_health",
                transport_used="rest",
                retryable=True,
                detail=f"AIO request timed out: {method} {path}",
            ) from exc
        except httpx.ConnectError as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="check_runtime_health",
                transport_used="rest",
                retryable=True,
                detail=f"AIO runtime is unreachable: {method} {path}",
            ) from exc
        except httpx.HTTPStatusError as exc:
            recover_hint = (
                "check_runtime_auth"
                if exc.response.status_code in {401, 403}
                else "inspect_runtime_response"
            )
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint=recover_hint,
                transport_used="rest",
                retryable=exc.response.status_code >= 500,
                detail=f"AIO request failed: {method} {path} -> {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

        payload = response.json()
        if not isinstance(payload, dict):
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="inspect_runtime_response",
                transport_used="rest",
                retryable=False,
                detail=f"AIO returned non-object payload for {method} {path}",
                status_code=response.status_code,
            )
        return payload

    async def _request_bytes(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> tuple[bytes, httpx.Headers]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.request(
                    method,
                    url,
                    headers=self._headers(),
                    params=params,
                )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="check_runtime_health",
                transport_used="rest",
                retryable=True,
                detail=f"AIO request timed out: {method} {path}",
            ) from exc
        except httpx.ConnectError as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="check_runtime_health",
                transport_used="rest",
                retryable=True,
                detail=f"AIO runtime is unreachable: {method} {path}",
            ) from exc
        except httpx.HTTPStatusError as exc:
            recover_hint = (
                "check_runtime_auth"
                if exc.response.status_code in {401, 403}
                else "inspect_runtime_response"
            )
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint=recover_hint,
                transport_used="rest",
                retryable=exc.response.status_code >= 500,
                detail=f"AIO request failed: {method} {path} -> {exc.response.status_code}",
                status_code=exc.response.status_code,
            ) from exc

        return response.content, response.headers

    @staticmethod
    def _unwrap_data(payload: dict[str, Any]) -> dict[str, Any]:
        """Return the official nested data payload when present."""

        data = payload.get("data")
        if isinstance(data, dict):
            return data
        return payload

    @staticmethod
    def _parse_exit_code(value: Any) -> int | None:
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.lstrip("-").isdigit():
            return int(value)
        return None

    async def get_sandbox_info(self) -> AioSandboxInfo:
        payload = await self._request_json("GET", "/v1/sandbox")
        data = self._unwrap_data(payload)
        home_dir = str(payload.get("home_dir") or data.get("home_dir") or "").strip()
        if not home_dir:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="inspect_runtime_response",
                transport_used="rest",
                retryable=False,
                detail="AIO sandbox payload missing home_dir",
            )
        return AioSandboxInfo(
            base_url=self.base_url,
            version=payload.get("version"),
            home_dir=home_dir,
            detail=(
                payload.get("detail")
                if isinstance(payload.get("detail"), dict)
                else payload
            ),
        )

    async def get_browser_info(self) -> AioBrowserInfo:
        payload = await self._request_json("GET", "/v1/browser/info")
        data = self._unwrap_data(payload)
        return AioBrowserInfo(
            cdp_url=data.get("cdp_url"),
            vnc_url=data.get("vnc_url"),
            user_agent=data.get("user_agent"),
            viewport=data.get("viewport"),
            detail=payload,
        )

    async def get_auth_info(self) -> AioAuthInfo:
        payload = await self._request_json("GET", "/auth")
        data = self._unwrap_data(payload)
        return AioAuthInfo(
            authenticated=bool(
                payload.get("authenticated", data.get("authenticated", True))
            ),
            detail=payload,
        )

    async def create_ticket(self) -> AioTicket:
        payload = await self._request_json("POST", "/tickets")
        data = self._unwrap_data(payload)
        ticket = str(payload.get("ticket") or data.get("ticket") or "").strip()
        if not ticket:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="inspect_runtime_response",
                transport_used="rest",
                retryable=False,
                detail="AIO ticket payload missing ticket",
            )

        raw_expires = payload.get("expires_in", data.get("expires_in"))
        expires_in: int | None
        if isinstance(raw_expires, int):
            expires_in = raw_expires
        elif isinstance(raw_expires, str) and raw_expires.isdigit():
            expires_in = int(raw_expires)
        else:
            expires_in = None

        return AioTicket(ticket=ticket, expires_in=expires_in, detail=payload)

    async def read_text_file(
        self,
        file_path: str,
        *,
        start_line: int | None = None,
        end_line: int | None = None,
        sudo: bool = False,
        missing_ok: bool = False,
    ) -> AioFileReadResult | None:
        body: dict[str, Any] = {"file": file_path, "sudo": sudo}
        if start_line is not None:
            body["start_line"] = start_line
        if end_line is not None:
            body["end_line"] = end_line

        try:
            payload = await self._request_json("POST", "/v1/file/read", json_body=body)
        except AioBackendError as exc:
            if missing_ok and exc.status_code == 404:
                return None
            raise

        data = self._unwrap_data(payload)
        return AioFileReadResult(
            file=str(data.get("file") or file_path),
            content=str(data.get("content") or ""),
            detail=payload,
        )

    async def write_text_file(
        self,
        file_path: str,
        content: str,
        *,
        append: bool = False,
        leading_newline: bool = False,
        trailing_newline: bool = False,
        sudo: bool = False,
    ) -> AioFileWriteResult:
        payload = await self._request_json(
            "POST",
            "/v1/file/write",
            json_body={
                "file": file_path,
                "content": content,
                "encoding": "utf-8",
                "append": append,
                "leading_newline": leading_newline,
                "trailing_newline": trailing_newline,
                "sudo": sudo,
            },
        )
        data = self._unwrap_data(payload)
        return AioFileWriteResult(
            file=str(data.get("file") or file_path),
            detail=payload,
        )

    async def list_path(
        self,
        path: str,
        *,
        recursive: bool = False,
        max_depth: int | None = None,
        show_hidden: bool = True,
    ) -> AioFileListResult:
        body: dict[str, Any] = {
            "path": path,
            "recursive": recursive,
            "show_hidden": show_hidden,
        }
        if max_depth is not None:
            body["max_depth"] = max_depth
        payload = await self._request_json("POST", "/v1/file/list", json_body=body)
        data = self._unwrap_data(payload)
        files = data.get("files")
        return AioFileListResult(
            path=str(data.get("path") or path),
            files=files if isinstance(files, list) else [],
            detail=payload,
        )

    async def exec_shell(
        self,
        command: str,
        *,
        session_id: str | None = None,
        exec_dir: str | None = None,
        timeout_seconds: float | None = None,
        async_mode: bool = False,
    ) -> AioShellCommandResult:
        body: dict[str, Any] = {
            "command": command,
            "async_mode": async_mode,
        }
        if session_id:
            body["id"] = session_id
        if exec_dir:
            body["exec_dir"] = exec_dir
        if timeout_seconds is not None:
            body["timeout"] = timeout_seconds

        payload = await self._request_json("POST", "/v1/shell/exec", json_body=body)
        data = self._unwrap_data(payload)
        return AioShellCommandResult(
            session_id=(
                str(data.get("session_id"))
                if data.get("session_id") is not None
                else None
            ),
            command=str(data.get("command") or command),
            status=str(data.get("status")) if data.get("status") is not None else None,
            output=str(data.get("output") or ""),
            exit_code=self._parse_exit_code(data.get("exit_code")),
            detail=payload,
        )

    async def ensure_directories(self, *paths: str) -> AioShellCommandResult | None:
        normalized_paths = [path.strip() for path in paths if path and path.strip()]
        if not normalized_paths:
            return None
        mkdir_args = " ".join(shlex.quote(path) for path in normalized_paths)
        return await self.exec_shell(f"mkdir -p {mkdir_args}")

    async def execute_browser_action(
        self,
        action_payload: dict[str, Any],
    ) -> AioBrowserActionResult:
        payload = await self._request_json(
            "POST",
            "/v1/browser/actions",
            json_body=action_payload,
        )
        return AioBrowserActionResult(
            status=str(payload.get("status") or ""),
            action_performed=str(payload.get("action_performed") or ""),
            detail=payload,
        )

    async def set_browser_config(
        self,
        *,
        width: int | None = None,
        height: int | None = None,
    ) -> AioBrowserConfigResult:
        body: dict[str, Any] = {}
        if width is not None and height is not None:
            body["resolution"] = {"width": width, "height": height}
        payload = await self._request_json(
            "POST",
            "/v1/browser/config",
            json_body=body,
        )
        return AioBrowserConfigResult(
            applied=bool(payload.get("success", True)),
            detail=payload,
        )

    async def take_browser_screenshot(self) -> AioBrowserScreenshot:
        content, headers = await self._request_bytes("GET", "/v1/browser/screenshot")

        def _header_int(name: str) -> int | None:
            raw = headers.get(name)
            if raw is None:
                return None
            return int(raw) if raw.isdigit() else None

        return AioBrowserScreenshot(
            content_type=headers.get("content-type", "application/octet-stream"),
            image_bytes=content,
            screen_width=_header_int("x-screen-width"),
            screen_height=_header_int("x-screen-height"),
            image_width=_header_int("x-image-width"),
            image_height=_header_int("x-image-height"),
        )

    async def replace_in_file(
        self,
        file_path: str,
        *,
        old_str: str,
        new_str: str,
        sudo: bool = False,
    ) -> AioFileReplaceResult:
        payload = await self._request_json(
            "POST",
            "/v1/file/replace",
            json_body={
                "file": file_path,
                "old_str": old_str,
                "new_str": new_str,
                "sudo": sudo,
            },
        )
        data = self._unwrap_data(payload)
        replaced_count = data.get("replaced_count", 0)
        if isinstance(replaced_count, str) and replaced_count.isdigit():
            replaced_count = int(replaced_count)
        if not isinstance(replaced_count, int):
            replaced_count = 0
        return AioFileReplaceResult(
            file=str(data.get("file") or file_path),
            replaced_count=replaced_count,
            detail=payload,
        )

    async def create_shell_session(
        self,
        *,
        exec_dir: str | None = None,
        session_id: str | None = None,
    ) -> AioShellCreateSessionResult:
        body: dict[str, Any] = {}
        if session_id:
            body["id"] = session_id
        if exec_dir:
            body["exec_dir"] = exec_dir
        payload = await self._request_json(
            "POST",
            "/v1/shell/sessions/create",
            json_body=body,
        )
        data = self._unwrap_data(payload)
        resolved_session_id = str(data.get("session_id") or "").strip()
        working_dir = str(data.get("working_dir") or exec_dir or "").strip()
        if not resolved_session_id or not working_dir:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="inspect_runtime_response",
                transport_used="rest",
                retryable=False,
                detail="AIO shell session payload missing session_id or working_dir",
            )
        return AioShellCreateSessionResult(
            session_id=resolved_session_id,
            working_dir=working_dir,
            detail=payload,
        )

    async def list_shell_sessions(self) -> AioShellSessionsResult:
        payload = await self._request_json("GET", "/v1/shell/sessions")
        data = self._unwrap_data(payload)
        raw_sessions = data.get("sessions")
        sessions: dict[str, AioShellSessionInfo] = {}
        if isinstance(raw_sessions, dict):
            for session_id, info in raw_sessions.items():
                if not isinstance(info, dict):
                    continue
                sessions[str(session_id)] = AioShellSessionInfo(
                    session_id=str(session_id),
                    working_dir=str(info.get("working_dir") or ""),
                    created_at=str(info.get("created_at") or ""),
                    last_used_at=str(info.get("last_used_at") or ""),
                    age_seconds=self._parse_exit_code(info.get("age_seconds")) or 0,
                    status=str(info.get("status") or ""),
                    current_command=(
                        str(info.get("current_command"))
                        if info.get("current_command") is not None
                        else None
                    ),
                )
        return AioShellSessionsResult(sessions=sessions, detail=payload)

    async def cleanup_shell_session(self, session_id: str) -> dict[str, Any]:
        return await self._request_json(
            "DELETE",
            f"/v1/shell/sessions/{session_id}",
        )

    async def get_shell_terminal_url(self) -> str | None:
        payload = await self._request_json("GET", "/v1/shell/terminal-url")
        data = self._unwrap_data(payload)
        terminal_url = data if isinstance(data, str) else payload.get("data")
        return str(terminal_url) if terminal_url else None

    async def execute_code(
        self,
        *,
        language: str,
        code: str,
        timeout_seconds: int | None = None,
    ) -> AioCodeExecuteResult:
        body: dict[str, Any] = {
            "language": language,
            "code": code,
        }
        if timeout_seconds is not None:
            body["timeout"] = timeout_seconds
        payload = await self._request_json(
            "POST",
            "/v1/code/execute",
            json_body=body,
        )
        data = self._unwrap_data(payload)
        outputs = data.get("outputs")
        return AioCodeExecuteResult(
            language=str(data.get("language") or language),
            status=str(data.get("status") or ""),
            code=str(data.get("code") or code),
            stdout=str(data.get("stdout")) if data.get("stdout") is not None else None,
            stderr=str(data.get("stderr")) if data.get("stderr") is not None else None,
            exit_code=self._parse_exit_code(data.get("exit_code")),
            outputs=outputs if isinstance(outputs, list) else [],
            detail=payload,
        )

    async def stabilize_browser_surface(
        self,
        *,
        preferred_url: str = "about:blank",
    ) -> dict[str, Any]:
        """Ensure the browser has at least one usable page target for takeover UI.

        This is intentionally narrow: only when the current browser surface
        contains internal Chrome pages (for example ``chrome://newtab``) do we
        replace them with a normal page target. If a real page already exists,
        we leave the runtime untouched.
        """

        browser = await self.get_browser_info()
        cdp_url = browser.cdp_url
        if not cdp_url:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="inspect_runtime_response",
                transport_used="cdp",
                retryable=False,
                detail="AIO browser payload missing cdp_url",
            )

        try:
            async with websockets.connect(
                cdp_url,
                ping_interval=None,
                max_size=None,
            ) as ws:
                next_id = 0

                async def send_command(
                    method: str,
                    params: dict[str, Any] | None = None,
                ) -> dict[str, Any]:
                    nonlocal next_id
                    next_id += 1
                    message_id = next_id
                    await ws.send(
                        json.dumps(
                            {
                                "id": message_id,
                                "method": method,
                                "params": params or {},
                            }
                        )
                    )
                    while True:
                        raw = await ws.recv()
                        payload = json.loads(raw)
                        if payload.get("id") != message_id:
                            continue
                        if "error" in payload:
                            raise AioBackendError(
                                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                                recover_hint="inspect_runtime_response",
                                transport_used="cdp",
                                retryable=True,
                                detail=(
                                    f"CDP command failed: {method} -> "
                                    f"{payload['error']}"
                                ),
                            )
                        result = payload.get("result")
                        return result if isinstance(result, dict) else {}

                targets = (
                    await send_command("Target.getTargets")
                ).get("targetInfos", [])
                page_targets = [
                    target
                    for target in targets
                    if target.get("type") == "page"
                ]
                usable_pages = [
                    target
                    for target in page_targets
                    if not self._is_internal_browser_page(target.get("url"))
                ]
                if usable_pages:
                    return {
                        "action": "reused_existing_page",
                        "target_id": usable_pages[0].get("targetId"),
                        "page_count": len(page_targets),
                    }

                created = await send_command(
                    "Target.createTarget",
                    {"url": preferred_url},
                )
                return {
                    "action": "created_page_target",
                    "target_id": created.get("targetId"),
                    "preferred_url": preferred_url,
                    "page_count": len(page_targets) + 1,
                }
        except AioBackendError:
            raise
        except Exception as exc:
            raise AioBackendError(
                error_code=AioBlockerCode.RUNTIME_UNAVAILABLE.value,
                recover_hint="check_runtime_health",
                transport_used="cdp",
                retryable=True,
                detail=f"Failed to stabilize AIO browser surface: {exc}",
            ) from exc
