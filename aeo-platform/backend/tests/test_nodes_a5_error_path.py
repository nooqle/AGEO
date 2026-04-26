from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.workflow.nodes_a5 as nodes_a5
from app.workflow.harness_validation import validate_a4_canonical_result


@pytest.mark.asyncio
async def test_a5_error_path_keeps_current_step_at_a5(monkeypatch):
    monkeypatch.setattr(
        nodes_a5,
        "_calculate_metrics",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(nodes_a5, "send_error_event", AsyncMock())
    monkeypatch.setattr(nodes_a5, "send_progress_event", AsyncMock())

    command = await nodes_a5.a5_analytics_node(
        {
            "session_id": "session-a5-error",
            "brand_profile": {"brand_name": "安利"},
            "fetch_results": [{"question_text": "Q1", "platform_results": []}],
        }
    )

    assert command.update["current_step"] == "A5"
    assert command.update["error_info"]["step"] == "A5"


def test_a5_rejects_partial_supplemental_canonical_result():
    result = validate_a4_canonical_result(
        {
            "a4_canonical_result": {
                "fetch_results": [
                    {
                        "question_id": "q1",
                        "platform_results": [{"platform": "kimi"}],
                    }
                ],
                "validation": {"passed": True},
                "merge_metadata": {
                    "source": "supplemental_fetch_workflow",
                    "base_pair_count": 4,
                    "merged_pair_count": 1,
                },
            }
        }
    )

    assert not result.passed
    assert result.metadata["blocker_code"] == "supplemental_fetch_partial_result"
