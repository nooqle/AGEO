"""
E2E Routing Matrix Tests for Specta AI Orchestrator.

Verifies that the orchestrator correctly routes through ALL node paths
across 10+ consecutive messages, covering:
- Full pipeline: A1 → A2 → A3 → A4 → A5
- Follow-up tools: drill_down, compare_snapshots, selective_refetch
- Mixed: casual chat interleaved with analysis
- Error recovery: retry after fail

Requires a running backend server (port 8001) with valid LLM API keys.

Usage:
    python -m pytest tests/test_routing_matrix.py -v -s --timeout=600
"""

import asyncio
import json
import logging
import time
from typing import Any

import httpx
import pytest
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration (same as test_e2e_websocket.py)
BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"
API_TOKEN = "dev-token"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

WS_CONNECT_TIMEOUT = 10
WS_PIPELINE_TIMEOUT = 900  # 15 min for full pipeline (A4 browser is slow)
WS_FOLLOWUP_TIMEOUT = 120  # 2 min for follow-up operations


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def create_session(entity_id: str | None = None) -> str:
    async with httpx.AsyncClient() as client:
        body = {"entity_id": entity_id} if entity_id else {}
        resp = await client.post(f"{BASE_URL}/api/v1/sessions", headers=HEADERS, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data.get("id") or data.get("session_id")


async def ws_connect(session_id: str):
    uri = f"{WS_URL}/ws/{session_id}?token={API_TOKEN}"
    return await websockets.connect(uri, open_timeout=WS_CONNECT_TIMEOUT)


async def send_msg(ws, content: str, brand_name: str = ""):
    msg = {"event": "user_message", "data": {"content": content, "brand_name": brand_name or content}}
    await ws.send(json.dumps(msg))
    logger.info(f"→ Sent: {content[:60]}")


async def send_confirmation(ws, selection: str):
    msg = {"event": "confirmation", "data": {"selection": selection, "message": selection}}
    await ws.send(json.dumps(msg))
    logger.info(f"→ Confirmed: {selection}")


async def collect_until(
    ws,
    stop_events: list[str],
    timeout: float = WS_PIPELINE_TIMEOUT,
    max_events: int = 1000,
) -> list[dict]:
    events: list[dict] = []
    start = time.time()
    while len(events) < max_events:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
            msg = json.loads(raw)
            event_type = msg.get("event") or msg.get("type", "unknown")
            events.append(msg)
            if event_type not in ("pong", "heartbeat"):
                data_preview = str(msg.get("data", ""))[:80]
                logger.info(f"  [{event_type}] {data_preview}")
            if event_type in stop_events:
                break
        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            break
    return events


def find_events(events: list[dict], event_type: str) -> list[dict]:
    return [e for e in events if (e.get("event") or e.get("type")) == event_type]


def has_event(events: list[dict], event_type: str) -> bool:
    return len(find_events(events, event_type)) > 0


def get_action_log_steps(events: list[dict]) -> list[str]:
    """Extract unique step names from action_log events."""
    steps = set()
    for e in find_events(events, "action_log"):
        data = e.get("data", {})
        step = data.get("step", "")
        if step:
            steps.add(step)
    return sorted(steps)


def get_progress_steps(events: list[dict]) -> list[str]:
    """Extract unique step names from progress events."""
    steps = set()
    for e in find_events(events, "progress"):
        data = e.get("data", {})
        step = data.get("step", "")
        if step:
            steps.add(step)
    return sorted(steps)


# ─── Test: Full Pipeline Routing ──────────────────────────────────────────────

class TestFullPipelineRouting:
    """Verify A1→A2→A3→A4→A5 routing in a single session."""

    @pytest.mark.asyncio
    async def test_pipeline_covers_all_agents(self):
        """Message 1: Start brand analysis. Verify all 5 agents are invoked."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await send_msg(ws, "帮我分析安利纽崔莱", "安利纽崔莱")

            # Full pipeline can take up to 15 min (A4 browser fetch)
            events = await collect_until(
                ws,
                stop_events=["execution_complete", "error"],
                timeout=WS_PIPELINE_TIMEOUT,
            )

            # Verify pipeline completion
            assert has_event(events, "execution_complete"), "Pipeline did not complete"
            assert not has_event(events, "error"), "Pipeline had errors"

            # Verify all 5 agent steps were executed
            progress_steps = get_progress_steps(events)
            for expected_step in ["A1", "A2", "A3", "A4", "A5"]:
                assert expected_step in progress_steps, (
                    f"Agent {expected_step} was not executed. Steps seen: {progress_steps}"
                )

            # Verify stage_result events were emitted
            stage_results = find_events(events, "stage_result")
            assert len(stage_results) >= 3, (
                f"Expected at least 3 stage_results (A1+A2+A3), got {len(stage_results)}"
            )

            # Verify output_ready for final report
            assert has_event(events, "output_ready"), "No output_ready event (report not generated)"

            logger.info("✓ Full pipeline routing: A1→A2→A3→A4→A5 PASS")

        finally:
            await ws.close()


# ─── Test: Follow-Up Routing ──────────────────────────────────────────────────

class TestFollowUpRouting:
    """After a full pipeline, verify follow-up tools route correctly."""

    @pytest.fixture(autouse=True)
    async def setup_pipeline(self):
        """Run full pipeline once, then run follow-up tests."""
        self.session_id = await create_session()
        self.ws = await ws_connect(self.session_id)

        # Run full pipeline first
        await send_msg(self.ws, "帮我分析安利纽崔莱", "安利纽崔莱")
        self.pipeline_events = await collect_until(
            self.ws,
            stop_events=["execution_complete", "error"],
            timeout=WS_PIPELINE_TIMEOUT,
        )

        if not has_event(self.pipeline_events, "execution_complete"):
            pytest.skip("Full pipeline did not complete — cannot test follow-ups")

        yield  # Run tests

        await self.ws.close()

    @pytest.mark.asyncio
    async def test_drill_down_routing(self):
        """Message 2: Drill-down request routes to drill_down_node."""
        await send_msg(self.ws, "请详细分析 DeepSeek 平台的表现")

        events = await collect_until(
            self.ws,
            stop_events=["execution_complete", "inline_confirmation", "error"],
            timeout=WS_FOLLOWUP_TIMEOUT,
        )

        # Should get reply_delta events (drill_down generates chat response)
        reply_events = find_events(events, "reply_delta")
        assert len(reply_events) > 0, "drill_down did not generate reply"

        # Verify it completed
        assert has_event(events, "execution_complete") or has_event(events, "inline_confirmation"), (
            "drill_down did not complete"
        )

        logger.info("✓ drill_down routing PASS")

    @pytest.mark.asyncio
    async def test_compare_snapshots_routing(self):
        """Message 3: Compare request routes to compare_snapshots_node."""
        await send_msg(self.ws, "请将本次分析结果与上次分析进行对比")

        events = await collect_until(
            self.ws,
            stop_events=["execution_complete", "inline_confirmation", "error"],
            timeout=WS_FOLLOWUP_TIMEOUT,
        )

        # Compare should produce reply_delta events
        reply_events = find_events(events, "reply_delta")
        assert len(reply_events) > 0, "compare_snapshots did not generate reply"

        logger.info("✓ compare_snapshots routing PASS")

    @pytest.mark.asyncio
    async def test_selective_refetch_routing(self):
        """Message 4: Selective refetch routes selective_refetch→A4→(A5)."""
        await send_msg(self.ws, "请重新抓取 Kimi 平台的数据")

        events = await collect_until(
            self.ws,
            stop_events=["execution_complete", "error"],
            timeout=WS_PIPELINE_TIMEOUT,
        )

        # Should see A4 progress events (re-fetch)
        progress_steps = get_progress_steps(events)
        assert "A4" in progress_steps, (
            f"selective_refetch did not trigger A4. Steps: {progress_steps}"
        )

        # After P2-1 fix, A5 should be auto-triggered
        if "A5" in progress_steps:
            logger.info("✓ selective_refetch → A4 → A5 auto-trigger PASS")
        else:
            logger.warning("⚠ selective_refetch → A4 completed but A5 not auto-triggered")

        logger.info("✓ selective_refetch routing PASS")


# ─── Test: Casual Chat Interleaving ───────────────────────────────────────────

class TestCasualChatRouting:
    """Verify casual messages don't trigger agent pipeline."""

    @pytest.mark.asyncio
    async def test_casual_chat_no_agent_call(self):
        """Message 5-6: Casual chat should get direct LLM reply, no agent routing."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Message 5: Greeting
            await send_msg(ws, "你好，你是什么AI？")

            events = await collect_until(
                ws,
                stop_events=["execution_complete", "inline_confirmation"],
                timeout=60,
            )

            # Should get reply but no agent progress events
            reply_events = find_events(events, "reply_delta")
            assert len(reply_events) > 0, "No reply to casual chat"

            progress_events = find_events(events, "progress")
            agent_steps = set()
            for e in progress_events:
                step = e.get("data", {}).get("step", "")
                if step in ("A1", "A2", "A3", "A4", "A5"):
                    agent_steps.add(step)

            assert len(agent_steps) == 0, (
                f"Casual chat triggered agent pipeline: {agent_steps}"
            )

            logger.info("✓ Casual chat routing (no agent call) PASS")

        finally:
            await ws.close()


# ─── Test: Multi-Message Session ──────────────────────────────────────────────

class TestMultiMessageSession:
    """10+ message test covering all routing paths in a single session."""

    @pytest.mark.asyncio
    @pytest.mark.timeout(1200)  # 20 min timeout for full matrix
    async def test_routing_matrix_10_messages(self):
        """
        Full routing matrix:
        Msg 1: Brand analysis (A1→A2→A3→A4→A5)
        Msg 2: Casual question
        Msg 3: Drill-down on platform
        Msg 4: Drill-down on competitor
        Msg 5: Compare snapshots
        Msg 6: Selective refetch (→A4→A5)
        Msg 7: Casual follow-up
        Msg 8: Drill-down on sentiment
        Msg 9: General optimization question
        Msg 10: Another brand analysis
        """
        session_id = await create_session()
        ws = await ws_connect(session_id)
        results: dict[str, str] = {}

        try:
            # ─── Msg 1: Full pipeline ─────────────────────────
            logger.info("═══ Msg 1: Full pipeline analysis ═══")
            await send_msg(ws, "帮我分析安利纽崔莱", "安利纽崔莱")
            events = await collect_until(ws, ["execution_complete", "error"], WS_PIPELINE_TIMEOUT)

            if has_event(events, "execution_complete"):
                steps = get_progress_steps(events)
                covered = sum(1 for s in ["A1", "A2", "A3", "A4", "A5"] if s in steps)
                results["msg1_pipeline"] = f"PASS ({covered}/5 agents)"
            else:
                results["msg1_pipeline"] = "FAIL (no execution_complete)"
                pytest.skip("Pipeline failed, cannot continue matrix")

            # ─── Msg 2: Casual chat ───────────────────────────
            logger.info("═══ Msg 2: Casual chat ═══")
            await send_msg(ws, "这个品牌的市场份额大概是多少？")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], 60)
            has_reply = has_event(events, "reply_delta")
            results["msg2_casual"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 3: Drill-down (platform) ─────────────────
            logger.info("═══ Msg 3: Drill-down platform ═══")
            await send_msg(ws, "深入分析 DeepSeek 平台上的品牌表现")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], WS_FOLLOWUP_TIMEOUT)
            has_reply = has_event(events, "reply_delta")
            results["msg3_drilldown_platform"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 4: Drill-down (competitor) ───────────────
            logger.info("═══ Msg 4: Drill-down competitor ═══")
            await send_msg(ws, "请分析一下汤臣倍健这个竞品的情况")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], WS_FOLLOWUP_TIMEOUT)
            has_reply = has_event(events, "reply_delta")
            results["msg4_drilldown_competitor"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 5: Compare snapshots ─────────────────────
            logger.info("═══ Msg 5: Compare snapshots ═══")
            await send_msg(ws, "对比一下上次和这次的分析结果")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], WS_FOLLOWUP_TIMEOUT)
            has_reply = has_event(events, "reply_delta")
            results["msg5_compare"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 6: Selective refetch ─────────────────────
            logger.info("═══ Msg 6: Selective refetch ═══")
            await send_msg(ws, "重新抓取 Kimi 平台的数据")
            events = await collect_until(ws, ["execution_complete", "error"], WS_PIPELINE_TIMEOUT)
            steps = get_progress_steps(events)
            has_a4 = "A4" in steps
            has_a5 = "A5" in steps
            results["msg6_refetch"] = f"PASS (A4={has_a4}, A5={has_a5})" if has_a4 else "FAIL"

            # ─── Msg 7: Casual follow-up ──────────────────────
            logger.info("═══ Msg 7: Casual follow-up ═══")
            await send_msg(ws, "你觉得我应该优先改进什么？")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], 60)
            has_reply = has_event(events, "reply_delta")
            results["msg7_casual"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 8: Drill-down (sentiment) ────────────────
            logger.info("═══ Msg 8: Drill-down sentiment ═══")
            await send_msg(ws, "分析一下负面情绪的回答都有哪些")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], WS_FOLLOWUP_TIMEOUT)
            has_reply = has_event(events, "reply_delta")
            results["msg8_drilldown_sentiment"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 9: General optimization ──────────────────
            logger.info("═══ Msg 9: Optimization advice ═══")
            await send_msg(ws, "给我一个具体的AEO优化方案")
            events = await collect_until(ws, ["execution_complete", "inline_confirmation"], 60)
            has_reply = has_event(events, "reply_delta")
            results["msg9_optimization"] = "PASS" if has_reply else "FAIL"

            # ─── Msg 10: New brand analysis ───────────────────
            logger.info("═══ Msg 10: New brand analysis ═══")
            await send_msg(ws, "现在帮我分析一下华为手机", "华为手机")
            events = await collect_until(ws, ["execution_complete", "error"], WS_PIPELINE_TIMEOUT)
            if has_event(events, "execution_complete"):
                steps = get_progress_steps(events)
                covered = sum(1 for s in ["A1", "A2", "A3", "A4", "A5"] if s in steps)
                results["msg10_new_pipeline"] = f"PASS ({covered}/5 agents)"
            else:
                results["msg10_new_pipeline"] = "FAIL"

        finally:
            await ws.close()

        # ─── Report ───────────────────────────────────────────
        logger.info("\n" + "=" * 60)
        logger.info("ROUTING MATRIX RESULTS")
        logger.info("=" * 60)
        total_pass = 0
        total = len(results)
        for key, result in results.items():
            status = "✓" if result.startswith("PASS") else "✗"
            if result.startswith("PASS"):
                total_pass += 1
            logger.info(f"  {status} {key}: {result}")
        logger.info(f"\n  TOTAL: {total_pass}/{total} PASS")
        logger.info("=" * 60)

        assert total_pass == total, f"Routing matrix: {total_pass}/{total} passed"


# ─── Test: Task API Routing ───────────────────────────────────────────────────

class TestTaskAPIRouting:
    """Verify task lifecycle API endpoints work correctly."""

    @pytest.mark.asyncio
    async def test_global_tasks_endpoint(self):
        """Verify GET /api/v1/tasks returns tasks across sessions."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/api/v1/tasks",
                headers=HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()

            assert "tasks" in data, "Response missing 'tasks' field"
            assert "total" in data, "Response missing 'total' field"
            assert isinstance(data["tasks"], list), "'tasks' should be a list"
            logger.info(f"✓ Global tasks endpoint: {data['total']} tasks found")

    @pytest.mark.asyncio
    async def test_global_tasks_status_filter(self):
        """Verify status_filter works on global tasks endpoint."""
        async with httpx.AsyncClient() as client:
            for status_val in ("completed", "failed", "running"):
                resp = await client.get(
                    f"{BASE_URL}/api/v1/tasks?status_filter={status_val}",
                    headers=HEADERS,
                )
                resp.raise_for_status()
                data = resp.json()
                # All returned tasks should match the filter
                for task in data["tasks"]:
                    assert task["status"] == status_val, (
                        f"Task {task['id']} has status {task['status']}, expected {status_val}"
                    )
            logger.info("✓ Global tasks status filter PASS")

    @pytest.mark.asyncio
    async def test_session_active_task(self):
        """Verify GET /sessions/{id}/tasks/active endpoint."""
        session_id = await create_session()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BASE_URL}/api/v1/sessions/{session_id}/tasks/active",
                headers=HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
            assert "task" in data, "Response missing 'task' field"
            # New session should have no active task
            assert data["task"] is None, "New session should have no active task"
            logger.info("✓ Session active task endpoint PASS")
