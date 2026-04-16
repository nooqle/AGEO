from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

import app.workflow.nodes_a5 as nodes_a5


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
