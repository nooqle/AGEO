from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.services.output_service import OutputService


@pytest.mark.asyncio
async def test_get_outputs_appends_synthetic_fetch_results_when_output_message_missing(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = uuid4()
    task_run_id = uuid4()
    now = datetime.now(timezone.utc)

    class FakeScalars:
        def all(self):
            return []

    class FakeResult:
        def scalars(self):
            return FakeScalars()

    class FakeDb:
        async def execute(self, _query):
            return FakeResult()

    async def fake_list_latest_for_session(_self, _session_id):
        assert _session_id == session_id
        return [
            SimpleNamespace(
                task_run_id=task_run_id,
                platform="yuanbao",
                status="succeeded",
                auth_state="authenticated",
                artifact_write_status="written",
                error_message=None,
                timing_json={"total_ms": 1200},
                latest_packet={
                    "stats": {"completed": 1, "total": 1, "mentions": 1},
                    "question_results": [
                        {
                            "question_id": "q-1",
                            "question_text": "测试问题",
                            "packet": {
                                "platform": "yuanbao",
                                "status": "result",
                                "answer": {"has_brand_mention": True},
                            },
                            "legacy_result": {
                                "platform": "hunyuan",
                                "success": True,
                                "answer": "已抓取",
                            },
                        }
                    ],
                },
                updated_at=now,
                created_at=now,
            )
        ]

    monkeypatch.setattr(
        "app.services.fetch_run_platform_state_service.FetchRunPlatformStateService.list_latest_for_session",
        fake_list_latest_for_session,
    )

    service = OutputService(FakeDb())  # type: ignore[arg-type]
    outputs = await service.get_outputs(session_id)

    assert len(outputs) == 1
    synthetic = outputs[0]
    assert synthetic["type"] == "fetchResults"
    assert synthetic["metadata"]["synthetic"] is True
    assert synthetic["metadata"]["source"] == "fetch_run_platform_states"
    assert synthetic["data"]["fetchResults"][0]["question_id"] == "q-1"
    assert synthetic["data"]["platformStatus"]["platform_statuses"]["yuanbao"] == "success"
    assert synthetic["data"]["timingSummary"]["platforms"]["yuanbao"]["total_ms"] == 1200


@pytest.mark.asyncio
async def test_get_outputs_keeps_existing_fetch_results_when_no_authoritative_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    session_id = uuid4()
    message_id = uuid4()
    now = datetime.now(timezone.utc)

    class FakeScalars:
        def __init__(self, rows):
            self._rows = rows

        def all(self):
            return self._rows

    class FakeResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return FakeScalars(self._rows)

    class FakeDb:
        async def execute(self, _query):
            return FakeResult(
                [
                    SimpleNamespace(
                        id=message_id,
                        session_id=session_id,
                        type="output",
                        output_type="fetchResults",
                        content="AI答案抓取结果",
                        output_data='{"fetchResults":[{"question_id":"q-1"}]}',
                        extra_metadata='{"output_id":"artifact-fetch"}',
                        created_at=now,
                    )
                ]
            )

    async def fake_list_latest_for_session(_self, _session_id):
        assert _session_id == session_id
        return []

    monkeypatch.setattr(
        "app.services.fetch_run_platform_state_service.FetchRunPlatformStateService.list_latest_for_session",
        fake_list_latest_for_session,
    )

    service = OutputService(FakeDb())  # type: ignore[arg-type]
    outputs = await service.get_outputs(session_id)

    assert len(outputs) == 1
    assert outputs[0]["artifact_id"] == "artifact-fetch"
    assert outputs[0]["data"]["fetchResults"][0]["question_id"] == "q-1"
