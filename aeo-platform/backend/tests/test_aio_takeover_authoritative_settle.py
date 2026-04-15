from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest

import app.api.v1.aio as aio_api


class _FakeAsyncSession:
    def __init__(self, recorder: dict[str, object]) -> None:
        self._recorder = recorder

    async def __aenter__(self):
        self._recorder["entered"] = True
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._recorder["exited"] = True
        return False

    async def commit(self) -> None:
        self._recorder["committed"] = True


@pytest.mark.asyncio
async def test_settle_takeover_request_updates_authoritative_state(monkeypatch):
    run_id = str(uuid4())
    takeover = SimpleNamespace(
        takeover_id="takeover_1",
        request_id="request_1",
        run_id=run_id,
        platform="hunyuan",
    )
    recorder: dict[str, object] = {}

    async def _fake_resolve_browser_action_request(request_id: str, resolution: str):
        recorder["runtime_request_id"] = request_id
        recorder["runtime_resolution"] = resolution
        return object()

    class _FakeService:
        def __init__(self, db) -> None:
            recorder["db"] = db

        async def mark_browser_action_resolution(
            self,
            *,
            task_run_id,
            platform,
            resolution,
            request_id=None,
            auth_state=None,
            timing_json=None,
        ):
            recorder["task_run_id"] = task_run_id
            recorder["platform"] = platform
            recorder["resolution"] = resolution
            recorder["request_id"] = request_id
            recorder["auth_state"] = auth_state
            recorder["timing_json"] = timing_json
            return object()

    monkeypatch.setattr(
        aio_api,
        "resolve_browser_action_request",
        _fake_resolve_browser_action_request,
    )
    monkeypatch.setattr(
        aio_api,
        "AsyncSessionLocal",
        lambda: _FakeAsyncSession(recorder),
    )
    monkeypatch.setattr(aio_api, "FetchRunPlatformStateService", _FakeService)

    await aio_api._settle_takeover_request(takeover, resolution="completed")

    assert recorder["runtime_request_id"] == "request_1"
    assert recorder["runtime_resolution"] == "completed"
    assert str(recorder["task_run_id"]) == run_id
    assert recorder["platform"] == "hunyuan"
    assert recorder["resolution"] == "completed"
    assert recorder["request_id"] == "request_1"
    assert recorder["committed"] is True


@pytest.mark.asyncio
async def test_settle_takeover_request_skips_authoritative_update_without_run_id(
    monkeypatch,
):
    takeover = SimpleNamespace(
        takeover_id="takeover_2",
        request_id="request_2",
        run_id=None,
        platform="kimi",
    )
    recorder: dict[str, object] = {}

    async def _fake_resolve_browser_action_request(request_id: str, resolution: str):
        recorder["runtime_request_id"] = request_id
        recorder["runtime_resolution"] = resolution
        return object()

    class _UnexpectedService:
        def __init__(self, db) -> None:
            raise AssertionError("authoritative service should not initialize")

    monkeypatch.setattr(
        aio_api,
        "resolve_browser_action_request",
        _fake_resolve_browser_action_request,
    )
    monkeypatch.setattr(aio_api, "FetchRunPlatformStateService", _UnexpectedService)

    await aio_api._settle_takeover_request(takeover, resolution="skip")

    assert recorder["runtime_request_id"] == "request_2"
    assert recorder["runtime_resolution"] == "skip"
