from unittest.mock import AsyncMock

import pytest

from app.workflow import nodes_a3


@pytest.mark.asyncio
async def test_question_set_confirmation_skips_when_fetch_mode_preselected(
    monkeypatch,
) -> None:
    send_confirmation = AsyncMock()
    monkeypatch.setattr(nodes_a3, "send_confirmation_request", send_confirmation)

    update = await nodes_a3._question_set_confirmation_update(
        {
            "session_id": "session-a3",
            "fetch_mode": "fast",
            "user_decisions": {"fetch_mode_confirmed": True},
        },
        question_set_id="question-set-1",
        monitor_mode="panorama",
        question_count=13,
    )

    send_confirmation.assert_not_awaited()
    assert update["awaiting_user"] is False
    assert update["pending_confirmation"] is None
    assert update["pending_question_set_confirmation"] is None
    assert update["fetch_mode"] == "fast"

    action = update["next_required_action"]
    assert action["tool_name"] == "answer_fetch"
    assert action["tool_args"] == {"fetch_mode": "fast"}
    assert action["authority"] == "authoritative_resume"


@pytest.mark.asyncio
async def test_question_set_confirmation_still_asks_without_fetch_mode(
    monkeypatch,
) -> None:
    send_confirmation = AsyncMock()
    monkeypatch.setattr(nodes_a3, "send_confirmation_request", send_confirmation)

    update = await nodes_a3._question_set_confirmation_update(
        {"session_id": "session-a3"},
        question_set_id="question-set-1",
        monitor_mode="panorama",
        question_count=13,
    )

    send_confirmation.assert_awaited_once()
    assert update["awaiting_user"] is True
    assert update["pending_confirmation"]["type"] == "question_set_confirmation"
