from __future__ import annotations

import os
from uuid import uuid4

import pytest

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.api.v1 import websocket_langgraph


class _FakeAsyncSessionLocal:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _FakeMessageService:
    compact_output_seen: bool | None = None

    def __init__(self, db):
        self.db = db

    async def get_messages(
        self,
        *,
        session_id,
        limit=50,
        before=None,
        compact_output=True,
    ):
        _FakeMessageService.compact_output_seen = compact_output
        return [
            {
                "role": "user",
                "type": "text",
                "content": "Li Auto panorama",
                "sequence": 1,
                "metadata": {},
            },
            {
                "role": "agent",
                "type": "output",
                "content": "",
                "sequence": 2,
                "metadata": {},
                "output_type": "questionList",
                "output_data": {
                    "simulatedQuestions": {
                        "simulated_questions": [
                            {
                                "question_id": "q1",
                                "core_question": "Which car should I buy?",
                            }
                        ],
                        "generation_mode": "brand_panorama",
                    },
                    "questions": [
                        {
                            "id": "q1",
                            "text": "Which car should I buy?",
                            "category": "purchase",
                        }
                    ],
                },
            },
        ]


class _FakeTaskService:
    def __init__(self, db):
        self.db = db

    async def get_session_active_task(self, session_id):
        return None


@pytest.mark.asyncio
async def test_rebuild_state_from_db_reads_full_artifacts(monkeypatch):
    _FakeMessageService.compact_output_seen = None
    monkeypatch.setattr(websocket_langgraph, "AsyncSessionLocal", _FakeAsyncSessionLocal)
    monkeypatch.setattr(websocket_langgraph, "MessageService", _FakeMessageService)
    monkeypatch.setattr(websocket_langgraph, "TaskService", _FakeTaskService)

    state = await websocket_langgraph.rebuild_state_from_db(str(uuid4()))

    assert _FakeMessageService.compact_output_seen is False
    assert state["simulated_questions"]["generation_mode"] == "brand_panorama"
    assert state["questions"][0]["id"] == "q1"
