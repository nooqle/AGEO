"""Shared AIO runtime contracts for Specta.

This module is the code counterpart of docs/design-aio-runtime-contracts-2026-04-01.md.
It centralizes canonical enums and path derivation so backend code does not
invent parallel state words or path layouts.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import PurePosixPath
import re


class AioBlockerCode(str, Enum):
    """Canonical blocker classification for AIO-backed execution."""

    LOGIN_REQUIRED = "login_required"
    CAPTCHA_REQUIRED = "captcha_required"
    UI_DRIFT = "ui_drift"
    STATE_INVALID = "state_invalid"
    NAVIGATION_FAILED = "navigation_failed"
    ELEMENT_NOT_FOUND = "element_not_found"
    PROXY_OR_REGION_BLOCKED = "proxy_or_region_blocked"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"


class AioPolicyDecision(str, Enum):
    """Harness policy result for a normalized blocker."""

    RETRY = "retry"
    AUTO_RECOVER = "auto_recover"
    REQUEST_TAKEOVER = "request_takeover"
    SKIP_PLATFORM = "skip_platform"
    FAIL_PLATFORM = "fail_platform"
    FAIL_SESSION = "fail_session"


class AioResumeGateResult(str, Enum):
    """Resume gate decision after human takeover."""

    PASS = "pass"
    FAIL_LOGIN_REQUIRED = "fail_login_required"
    FAIL_CAPTCHA_REQUIRED = "fail_captcha_required"
    FAIL_UI_NOT_READY = "fail_ui_not_ready"
    FAIL_STATE_CORRUPT = "fail_state_corrupt"
    FAIL_UNKNOWN = "fail_unknown"


class AioSessionState(str, Enum):
    """Authoritative lifecycle for an AIO-backed Specta session."""

    PROVISIONING = "provisioning"
    READY = "ready"
    LEASED = "leased"
    TAKEOVER_FROZEN = "takeover_frozen"
    IDLE = "idle"
    DRAINING = "draining"
    FAILED = "failed"
    DESTROYED = "destroyed"


class AioTakeoverState(str, Enum):
    """Authoritative lifecycle for a takeover flow."""

    REQUESTED = "requested"
    ISSUED = "issued"
    ACTIVE = "active"
    RESOLVED = "resolved"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    RESUME_FAILED = "resume_failed"


class AioTakeoverMode(str, Enum):
    """Canonical access modes for human takeover surfaces."""

    CANVAS_CDP = "canvas_cdp"
    VNC_FALLBACK = "vnc_fallback"


@dataclass(frozen=True, slots=True)
class AioPlatformRoots:
    """Derived runtime roots for one workspace/task/platform tuple."""

    profile_root: str
    run_root: str
    cookies_path: str
    state_path: str
    session_meta_path: str
    checkpoint_root: str
    snapshot_root: str
    download_root: str
    extraction_path: str
    auth_context_key: str
    run_context_key: str
    legacy_profile_root: str
    legacy_cookies_path: str
    legacy_state_path: str
    legacy_session_meta_path: str


def derive_data_root(home_dir: str) -> str:
    """Derive the canonical persistent data root from AIO home_dir."""

    return str(PurePosixPath(home_dir) / "data")


def normalize_takeover_mode(value: str | None) -> str:
    """Normalize legacy/env aliases into the canonical takeover mode contract."""

    normalized = (value or "").strip().lower()
    if normalized in {"canvas", "canvas_cdp", "canvas-cdp"}:
        return AioTakeoverMode.CANVAS_CDP.value
    if normalized in {"vnc", "vnc_fallback", "vnc-fallback"}:
        return AioTakeoverMode.VNC_FALLBACK.value
    return AioTakeoverMode.CANVAS_CDP.value


def _safe_path_segment(value: str | None, fallback: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raw = fallback
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", raw)
    normalized = normalized.strip("._-:")
    return normalized or fallback


def derive_platform_roots(
    *,
    data_root: str,
    workspace_id: str,
    task_id: str,
    platform: str,
    auth_scope_id: str | None = None,
    run_scope_id: str | None = None,
    environment: str | None = None,
) -> AioPlatformRoots:
    """Derive canonical profile_root and run_root paths.

    profile_root stores long-lived login state per env/user/platform.
    run_root stores per-task snapshots, checkpoints and extracted artifacts.
    """

    normalized_platform = _safe_path_segment(platform.lower(), "unknown_platform")
    normalized_workspace = _safe_path_segment(workspace_id, "anonymous")
    normalized_task = _safe_path_segment(task_id, "unknown_task")
    normalized_auth_scope = _safe_path_segment(
        auth_scope_id or workspace_id,
        "anonymous",
    )
    normalized_run_scope = _safe_path_segment(
        run_scope_id or workspace_id,
        normalized_workspace,
    )
    normalized_env = _safe_path_segment(environment, "default")
    auth_context_key = f"{normalized_env}/{normalized_auth_scope}/{normalized_platform}"
    run_context_key = f"{normalized_run_scope}/{normalized_task}/{normalized_platform}"
    profile_root = (
        PurePosixPath(data_root)
        / "auth"
        / normalized_env
        / normalized_auth_scope
        / normalized_platform
        / "profile"
    )
    run_root = (
        PurePosixPath(data_root)
        / "runs"
        / normalized_run_scope
        / normalized_task
        / normalized_platform
        / "run"
    )
    legacy_profile_root = (
        PurePosixPath(data_root) / normalized_workspace / normalized_platform / "profile"
    )
    return AioPlatformRoots(
        profile_root=str(profile_root),
        run_root=str(run_root),
        cookies_path=str(profile_root / "cookies.json"),
        state_path=str(profile_root / "browser_state.json"),
        session_meta_path=str(profile_root / "session_meta.json"),
        checkpoint_root=str(run_root / "checkpoints"),
        snapshot_root=str(run_root / "snapshots"),
        download_root=str(run_root / "downloads"),
        extraction_path=str(run_root / "extraction.json"),
        auth_context_key=auth_context_key,
        run_context_key=run_context_key,
        legacy_profile_root=str(legacy_profile_root),
        legacy_cookies_path=str(legacy_profile_root / "cookies.json"),
        legacy_state_path=str(legacy_profile_root / "browser_state.json"),
        legacy_session_meta_path=str(legacy_profile_root / "session_meta.json"),
    )
