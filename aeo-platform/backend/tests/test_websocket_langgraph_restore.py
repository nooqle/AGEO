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
    monkeypatch.setattr(
        websocket_langgraph, "AsyncSessionLocal", _FakeAsyncSessionLocal
    )
    monkeypatch.setattr(websocket_langgraph, "MessageService", _FakeMessageService)
    monkeypatch.setattr(websocket_langgraph, "TaskService", _FakeTaskService)

    state = await websocket_langgraph.rebuild_state_from_db(str(uuid4()))

    assert _FakeMessageService.compact_output_seen is False
    assert state["simulated_questions"]["generation_mode"] == "brand_panorama"
    assert state["questions"][0]["id"] == "q1"


def test_stream_finished_fallback_closes_non_waiting_local_run():
    task_id = uuid4()
    run_id = uuid4()

    transition = websocket_langgraph._build_stream_finished_fallback_transition(
        {
            "task_id": str(task_id),
            "run_id": str(run_id),
            "execution_status": "running",
            "current_step": "",
            "progress_message": "等待开始...",
            "awaiting_user": False,
            "pending_confirmation": None,
            "next_required_action": None,
        },
        reason="test_stream_finished",
    )

    assert transition is not None
    assert transition.task_id == task_id
    assert transition.run_id == run_id
    assert transition.status == "completed"
    assert transition.stage == "orchestrator"
    assert transition.message == "分析完成"


def test_stream_finished_fallback_does_not_close_waiting_user_run():
    transition = websocket_langgraph._build_stream_finished_fallback_transition(
        {
            "task_id": str(uuid4()),
            "run_id": str(uuid4()),
            "execution_status": "running",
            "awaiting_user": True,
        },
        reason="test_stream_finished",
    )

    assert transition is None


def test_resolve_task_label_prefers_dashboard_brand_over_instruction_prompt():
    label = websocket_langgraph._resolve_task_label(
        brand_name="",
        content="请基于当前品牌对象世界推进「先建立可执行的问题池」。",
        attachments=[],
        dashboard_context={"brand": "理想汽车"},
    )

    assert label == "理想汽车"


def test_resolve_task_label_prefers_explicit_brand_over_dashboard_context():
    label = websocket_langgraph._resolve_task_label(
        brand_name="雅姿",
        content="请继续推进当前任务。",
        attachments=[],
        dashboard_context={"brand": "理想汽车"},
    )

    assert label == "雅姿"


def test_extract_dashboard_context_accepts_top_level_payload():
    dashboard_context = websocket_langgraph._extract_dashboard_context(
        {
            "entity_id": "entity-1",
            "brand": "理想汽车",
            "dashboard_context": {
                "entry_source": "dashboard_command_bar",
                "brand": "理想汽车",
            },
        },
        context=[],
    )

    assert dashboard_context == {
        "entry_source": "dashboard_command_bar",
        "brand": "理想汽车",
        "entity_id": "entity-1",
    }


def test_extract_dashboard_context_prefers_structured_context_data():
    dashboard_context = websocket_langgraph._extract_dashboard_context(
        {
            "entity_id": "entity-from-top-level",
            "brand": "旧品牌",
            "dashboard_context": {
                "entry_source": "top_level",
                "brand": "旧品牌",
            },
        },
        context=[
            {
                "type": "intent",
                "label": "Dashboard结构化上下文",
                "data": {
                    "entry_source": "dashboard_command_bar",
                    "entity_id": "entity-from-context",
                    "brand": "理想汽车",
                },
            }
        ],
    )

    assert dashboard_context == {
        "entry_source": "dashboard_command_bar",
        "brand": "理想汽车",
        "entity_id": "entity-from-context",
    }


def test_dashboard_intelligence_question_supersedes_waiting_flow():
    assert websocket_langgraph._should_supersede_waiting_flow_for_follow_up(
        content="为什么官网引用转化率为 0？这个结论由哪些对象支撑？",
        context=[
            {
                "type": "intent",
                "label": "情报研判：按结论、证据、对象关系、影响回答",
            }
        ],
        dashboard_context={
            "entry_source": "dashboard_command_bar",
            "entity_id": str(uuid4()),
            "brand": "理想汽车",
        },
    )


def test_dashboard_confirmation_text_keeps_waiting_flow():
    assert not websocket_langgraph._should_supersede_waiting_flow_for_follow_up(
        content="确认，继续快速采集。",
        context=[
            {
                "type": "intent",
                "label": "情报研判：按结论、证据、对象关系、影响回答",
            }
        ],
        dashboard_context={
            "entry_source": "dashboard_command_bar",
            "entity_id": str(uuid4()),
            "brand": "理想汽车",
        },
    )
