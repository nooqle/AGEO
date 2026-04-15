from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services.fetch_run_platform_state_service import FetchRunPlatformStateService


def test_normalize_status_treats_result_as_succeeded():
    assert FetchRunPlatformStateService._normalize_status("result") == "succeeded"
    assert FetchRunPlatformStateService._derive_status_from_packet({"status": "result"}) == "succeeded"


def test_canonicalize_platform_unifies_hunyuan_to_yuanbao():
    assert FetchRunPlatformStateService.canonicalize_platform("hunyuan") == "yuanbao"
    assert FetchRunPlatformStateService.canonicalize_platform("yuanbao") == "yuanbao"


def test_build_summary_projection_projects_platform_and_fetch_results_consistently():
    service = FetchRunPlatformStateService(db=None)  # type: ignore[arg-type]
    rows = [
        SimpleNamespace(
            platform="yuanbao",
            status="succeeded",
            auth_state="authenticated",
            artifact_write_status="written",
            error_message=None,
            timing_json={"total_ms": 1000},
            latest_packet={
                "stats": {"completed": 1, "total": 1, "mentions": 1},
                "question_results": [
                    {
                        "question_id": "q1",
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
        ),
        SimpleNamespace(
            platform="kimi",
            status="skipped",
            auth_state="skipped",
            artifact_write_status="written",
            error_message=None,
            timing_json={},
            latest_packet={
                "stats": {"completed": 0, "total": 1, "mentions": 0},
                "question_results": [
                    {
                        "question_id": "q1",
                        "question_text": "测试问题",
                        "packet": {
                            "platform": "kimi",
                            "status": "skipped",
                            "skipped_by_user": True,
                        },
                        "legacy_result": {
                            "platform": "kimi",
                            "success": False,
                            "status": "skipped",
                        },
                    }
                ],
            },
        ),
    ]

    projection = service.build_summary_projection(rows)
    fetch_results = projection["fetch_results"]
    assert len(fetch_results) == 1
    assert fetch_results[0]["question_id"] == "q1"
    assert {packet["platform"] for packet in fetch_results[0]["aio_platform_packets"]} == {
        "yuanbao",
        "kimi",
    }
    assert {
        FetchRunPlatformStateService.canonicalize_platform(result["platform"])
        for result in fetch_results[0]["platform_results"]
    } == {"yuanbao", "kimi"}

    platform_status = projection["platform_status"]
    assert platform_status["platform_statuses"]["yuanbao"] == "success"
    assert platform_status["platform_statuses"]["kimi"] == "skipped"
    assert projection["success_count"] == 1
    assert projection["skipped_count"] == 1
    assert projection["fail_count"] == 0


def test_build_summary_projection_prefers_skipped_over_failed_in_status_rollup():
    service = FetchRunPlatformStateService(db=None)  # type: ignore[arg-type]
    rows = [
        SimpleNamespace(
            platform="kimi",
            status="skipped",
            auth_state="skipped",
            artifact_write_status="written",
            error_message=None,
            timing_json={"total_ms": 3200},
            latest_packet={
                "stats": {"completed": 0, "total": 12, "mentions": 0},
                "question_results": [],
            },
            updated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        ),
        SimpleNamespace(
            platform="yuanbao",
            status="succeeded",
            auth_state="authenticated",
            artifact_write_status="written",
            error_message=None,
            timing_json={"total_ms": 2500},
            latest_packet={
                "stats": {"completed": 11, "total": 12, "mentions": 5},
                "question_results": [],
            },
            updated_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        ),
    ]

    projection = service.build_summary_projection(rows)
    assert projection["platform_status"]["platform_statuses"]["kimi"] == "skipped"
    assert projection["platform_status"]["platform_statuses"]["yuanbao"] == "success"
    assert projection["skipped_count"] == 1
    assert projection["fail_count"] == 0
    assert projection["timing_summary"]["platforms"]["kimi"]["total_ms"] == 3200
    assert projection["timing_summary"]["platforms"]["yuanbao"]["total_ms"] == 2500
    assert projection["timing_summary"]["stage_totals_ms"]["total_ms"] == 5700


def test_latest_run_selection_should_follow_update_time_not_uuid_sorting():
    newer = datetime.now(timezone.utc)
    older = newer - timedelta(minutes=5)
    rows = [
        SimpleNamespace(
            task_run_id="older-run",
            updated_at=older,
            created_at=older,
        ),
        SimpleNamespace(
            task_run_id="newer-run",
            updated_at=newer,
            created_at=newer,
        ),
    ]

    rows.sort(
        key=lambda row: (row.updated_at, row.created_at, row.task_run_id),
        reverse=True,
    )

    assert rows[0].task_run_id == "newer-run"


def test_build_summary_projection_emits_total_timing_window():
    service = FetchRunPlatformStateService(db=None)  # type: ignore[arg-type]
    started_at = datetime.now(timezone.utc)
    rows = [
        SimpleNamespace(
            platform="doubao",
            status="succeeded",
            auth_state="authenticated",
            artifact_write_status="written",
            error_message=None,
            timing_json={"preflight_ms": 100, "total_ms": 1400},
            latest_packet={"stats": {"completed": 1, "total": 1, "mentions": 0}},
            started_at=started_at,
            finished_at=started_at + timedelta(milliseconds=1400),
            updated_at=started_at + timedelta(milliseconds=1400),
            created_at=started_at,
        ),
        SimpleNamespace(
            platform="deepseek",
            status="failed",
            auth_state="needs_verify",
            artifact_write_status="written",
            error_message="timeout",
            timing_json={"wait_ms": 800, "total_ms": 2200},
            latest_packet={"stats": {"completed": 0, "total": 1, "mentions": 0}},
            started_at=started_at + timedelta(milliseconds=200),
            finished_at=started_at + timedelta(milliseconds=2500),
            updated_at=started_at + timedelta(milliseconds=2500),
            created_at=started_at + timedelta(milliseconds=200),
        ),
    ]

    projection = service.build_summary_projection(rows)

    assert projection["timing_summary"]["total_ms"] == 2500
    assert projection["timing_summary"]["stage_totals_ms"]["preflight_ms"] == 100
    assert projection["timing_summary"]["stage_totals_ms"]["wait_ms"] == 800


def test_build_rows_from_fetch_results_aggregates_packet_timing_across_questions():
    service = FetchRunPlatformStateService(db=None)  # type: ignore[arg-type]
    task_run_id = uuid4()
    task_id = uuid4()
    session_id = uuid4()
    entity_id = uuid4()
    user_id = uuid4()

    fetch_results = [
        {
            "question_id": "q1",
            "question_text": "问题1",
            "aio_platform_packets": [
                {
                    "platform": "yuanbao",
                    "status": "result",
                    "timing_json": {
                        "preflight_ms": 100,
                        "wait_ms": 300,
                        "total_ms": 900,
                    },
                }
            ],
            "platform_results": [],
        },
        {
            "question_id": "q2",
            "question_text": "问题2",
            "aio_platform_packets": [
                {
                    "platform": "hunyuan",
                    "status": "result",
                    "duration": 1.2,
                    "timing_json": {
                        "preflight_ms": 80,
                        "extract_ms": 120,
                    },
                }
            ],
            "platform_results": [],
        },
    ]

    rows = service._build_rows_from_fetch_results(
        task_run_id=task_run_id,
        task_id=task_id,
        session_id=session_id,
        entity_id=entity_id,
        user_id=user_id,
        fetch_results=fetch_results,
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["platform"] == "yuanbao"
    assert row["timing_json"]["preflight_ms"] == 180
    assert row["timing_json"]["wait_ms"] == 300
    assert row["timing_json"]["extract_ms"] == 120
    assert row["timing_json"]["total_ms"] == 2100
    assert row["latest_packet"]["stats"]["completed"] == 2
    assert row["latest_packet"]["stats"]["total"] == 2


def test_build_rows_from_fetch_results_does_not_fabricate_timestamps_without_source_times():
    service = FetchRunPlatformStateService(db=None)  # type: ignore[arg-type]

    rows = service._build_rows_from_fetch_results(
        task_run_id=uuid4(),
        task_id=uuid4(),
        session_id=uuid4(),
        entity_id=uuid4(),
        user_id=uuid4(),
        fetch_results=[
            {
                "question_id": "q1",
                "question_text": "问题1",
                "aio_platform_packets": [
                    {
                        "platform": "kimi",
                        "status": "skipped",
                        "timing_json": {"total_ms": 500},
                        "skipped_by_user": True,
                    }
                ],
                "platform_results": [],
            }
        ],
    )

    assert len(rows) == 1
    row = rows[0]
    assert row["started_at"] is None
    assert row["finished_at"] is None
    assert row["status"] == "skipped"


def test_resolve_finished_at_returns_none_when_terminal_without_real_finish_time():
    assert (
        FetchRunPlatformStateService._resolve_finished_at(
            merged_status="succeeded",
            current_finished_at=None,
            incoming_finished_at=None,
        )
        is None
    )
