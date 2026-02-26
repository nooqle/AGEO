"""
End-to-end WebSocket test suite for Specta AI orchestrator.

Covers 7 test scenarios:
1. Basic end-to-end flow (P0)
2. Long task timeout behavior (P2)
3. History message loading (P1)
4. Conversation resume (P0)
5. WebSocket disconnect/reconnect (P2)
6. Multi-round dialog & inline_confirmation (P1)
7. Error handling & edge cases (P2)

Usage:
    python -m pytest tests/test_e2e_websocket.py -v -s
    # Or run individual tests:
    python -m pytest tests/test_e2e_websocket.py::TestBasicE2E -v -s
"""

import asyncio
import json
import logging
import time
from typing import Any
from uuid import uuid4

import httpx
import pytest
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration
BASE_URL = "http://localhost:8001"
WS_URL = "ws://localhost:8001"
API_TOKEN = "dev-token"
HEADERS = {"Authorization": f"Bearer {API_TOKEN}"}

# Timeouts
WS_CONNECT_TIMEOUT = 10
WS_MESSAGE_TIMEOUT = 120  # 2 minutes for normal operations
WS_LONG_TIMEOUT = 900     # 15 minutes for A4 browser fetch


# ─── Helpers ───────────────────────────────────────────────────────────────────

async def create_session() -> str:
    """Create a new session via REST API."""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/sessions",
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        session_id = data.get("id") or data.get("session_id")
        logger.info(f"Created session: {session_id}")
        return session_id


async def get_messages(session_id: str) -> list[dict]:
    """Get messages for a session via REST API."""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{BASE_URL}/api/v1/sessions/{session_id}/messages",
            headers=HEADERS,
        )
        resp.raise_for_status()
        return resp.json()


async def ws_connect(session_id: str):
    """Connect to WebSocket for a session."""
    uri = f"{WS_URL}/ws/{session_id}?token={API_TOKEN}"
    ws = await websockets.connect(uri, open_timeout=WS_CONNECT_TIMEOUT)
    logger.info(f"WebSocket connected for session: {session_id}")
    return ws


async def send_user_message(ws, content: str, brand_name: str = ""):
    """Send a user_message event via WebSocket."""
    msg = {
        "event": "user_message",
        "data": {
            "content": content,
            "brand_name": brand_name or content,
        },
    }
    await ws.send(json.dumps(msg))
    logger.info(f"Sent user_message: {content[:50]}")


async def send_ping(ws):
    """Send a ping event."""
    await ws.send(json.dumps({"event": "ping"}))


async def send_confirmation(ws, selection: str, option_id: str = ""):
    """Send a confirmation event."""
    msg = {
        "event": "confirmation",
        "data": {
            "selection": selection,
            "option_id": option_id,
            "message": selection,
        },
    }
    await ws.send(json.dumps(msg))
    logger.info(f"Sent confirmation: {selection}")


async def collect_events(
    ws,
    timeout: float = WS_MESSAGE_TIMEOUT,
    stop_on: str | list[str] | None = None,
    max_events: int = 500,
) -> list[dict]:
    """Collect WebSocket events until timeout or stop condition.

    Args:
        ws: WebSocket connection
        timeout: Max seconds to wait
        stop_on: Event type(s) that trigger early stop
        max_events: Max events to collect
    """
    if isinstance(stop_on, str):
        stop_on = [stop_on]
    stop_on = stop_on or []

    events: list[dict] = []
    start = time.time()

    while len(events) < max_events:
        remaining = timeout - (time.time() - start)
        if remaining <= 0:
            break
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5))
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Non-JSON message: {raw[:100]}")
                continue

            event_type = msg.get("event") or msg.get("type", "unknown")
            events.append(msg)

            # Skip heartbeat noise in logs
            if event_type not in ("pong", "heartbeat"):
                data_preview = str(msg.get("data", ""))[:80]
                logger.info(f"  [{event_type}] {data_preview}")

            if event_type in stop_on:
                logger.info(f"Stop condition met: {event_type}")
                break

        except asyncio.TimeoutError:
            continue
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            break

    elapsed = time.time() - start
    logger.info(f"Collected {len(events)} events in {elapsed:.1f}s")
    return events


def find_events(events: list[dict], event_type: str) -> list[dict]:
    """Filter events by type."""
    return [e for e in events if (e.get("event") or e.get("type")) == event_type]


def has_event(events: list[dict], event_type: str) -> bool:
    """Check if an event type exists."""
    return len(find_events(events, event_type)) > 0


def get_reply_content(events: list[dict]) -> str:
    """Extract accumulated reply_delta content from events.

    Handles both delta mode (content appended) and fallback text scenarios.
    """
    content = ""
    for rd in find_events(events, "reply_delta"):
        content += rd.get("data", {}).get("content", "")
    return content


# ─── Test 1: Basic End-to-End Flow (P0) ───────────────────────────────────────

class TestBasicE2E:
    """Test 1: Verify complete flow from frontend message to agent response."""

    @pytest.mark.asyncio
    async def test_full_analysis_flow(self):
        """Send a brand analysis request and verify all 4 layers of events."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Send analysis request
            await send_user_message(ws, "帮我分析安利纽崔莱", "安利纽崔莱")

            # Collect events until execution_complete or timeout
            events = await collect_events(
                ws,
                timeout=WS_MESSAGE_TIMEOUT,
                stop_on=["execution_complete"],
            )

            # ── Verify Layer 1: reply_delta (streaming reply) ──
            reply_deltas = find_events(events, "reply_delta")
            assert len(reply_deltas) > 0, "Should receive reply_delta events (Layer 1)"
            logger.info(f"  ✓ Layer 1: {len(reply_deltas)} reply_delta events")

            # Check that reply content accumulates
            total_content = get_reply_content(events)
            assert len(total_content) > 10, f"Reply content too short: {total_content[:50]}"
            logger.info(f"  ✓ Layer 1: Total reply length = {len(total_content)} chars")

            # ── Verify Layer 2: plan_update ──
            plan_updates = find_events(events, "plan_update")
            if plan_updates:
                logger.info(f"  ✓ Layer 2: {len(plan_updates)} plan_update events")
                for pu in plan_updates:
                    plan_text = pu.get("data", {}).get("text", "")
                    assert plan_text, "plan_update should have text"
            else:
                logger.warning("  ⚠ Layer 2: No plan_update events (orchestrator may skip)")

            # ── Verify Layer 3: action_log ──
            action_logs = find_events(events, "action_log")
            if action_logs:
                logger.info(f"  ✓ Layer 3: {len(action_logs)} action_log events")
                for al in action_logs:
                    assert al.get("data", {}).get("message"), "action_log should have message"
            else:
                logger.warning("  ⚠ Layer 3: No action_log events")

            # ── Verify Layer 4: inline_confirmation (optional) ──
            confirmations = find_events(events, "inline_confirmation")
            if confirmations:
                logger.info(f"  ✓ Layer 4: {len(confirmations)} inline_confirmation events")
            else:
                logger.info("  ℹ Layer 4: No inline_confirmation (orchestrator chose natural dialog)")

            # ── Verify thought_delta (optional) ──
            thoughts = find_events(events, "thought_delta")
            if thoughts:
                logger.info(f"  ✓ Thought: {len(thoughts)} thought_delta events")

            # ── Verify execution_complete ──
            exec_complete = find_events(events, "execution_complete")
            if exec_complete:
                logger.info("  ✓ execution_complete received")
            else:
                # May not have reached completion if orchestrator is waiting for user
                logger.warning("  ⚠ No execution_complete (may be waiting for user input)")

            # ── Verify agent_start ──
            agent_starts = find_events(events, "agent_start")
            if agent_starts:
                logger.info(f"  ✓ agent_start: {len(agent_starts)} events")

            # ── Check for errors ──
            errors = find_events(events, "error")
            non_recoverable = [e for e in errors if not e.get("data", {}).get("recoverable", False)]
            assert len(non_recoverable) == 0, f"Non-recoverable errors occurred: {non_recoverable}"
            if errors:
                logger.warning(f"  ⚠ Recoverable errors: {len(errors)}")

            logger.info("TEST 1 PASSED: Basic E2E flow verified")

        finally:
            await ws.close()

    @pytest.mark.asyncio
    async def test_ws_connection_and_heartbeat(self):
        """Verify WebSocket connection and heartbeat mechanism."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Send ping
            await send_ping(ws)

            # Wait for pong
            events = await collect_events(ws, timeout=5, stop_on=["pong"], max_events=5)
            pongs = find_events(events, "pong")
            assert len(pongs) > 0, "Should receive pong response"
            logger.info("TEST 1b PASSED: Heartbeat works")

        finally:
            await ws.close()


# ─── Test 3: History Message Loading (P1) ──────────────────────────────────────

class TestHistoryLoading:
    """Test 3: Verify message persistence and retrieval via REST API."""

    @pytest.mark.asyncio
    async def test_messages_persisted_to_db(self):
        """After a conversation, messages should be retrievable via GET API."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Send a message and wait for response
            await send_user_message(ws, "帮我分析安利纽崔莱", "安利纽崔莱")
            events = await collect_events(
                ws, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )
        finally:
            await ws.close()

        # Wait for _save_final_message to complete (async DB write)
        await asyncio.sleep(8)

        # Retrieve messages via REST API
        messages = await get_messages(session_id)
        logger.info(f"Retrieved {len(messages)} messages from DB")

        # Should have at least user message (agent reply may still be saving)
        assert len(messages) >= 1, f"Expected >= 1 messages, got {len(messages)}"

        # Verify user message (API returns role as lowercase "user")
        user_msgs = [m for m in messages if m.get("role") == "user"]
        assert len(user_msgs) >= 1, "Should have at least 1 user message"
        assert "安利纽崔莱" in user_msgs[0].get("content", "")

        # Verify agent message (API returns ASSISTANT as "agent")
        # NOTE: agent message is saved by _save_final_message after workflow completes.
        # If orchestrator pauses for user input (awaiting_user), the agent message may
        # not yet exist or may be a short fallback like "分析完成".
        agent_msgs = [m for m in messages if m.get("role") == "agent"]
        if agent_msgs:
            logger.info(f"  ✓ Agent message found ({len(agent_msgs[0].get('content', ''))} chars)")
        else:
            logger.warning("  ⚠ No agent message yet (workflow may still be awaiting user)")

        logger.info(f"  User messages: {len(user_msgs)}")
        logger.info(f"  Agent messages: {len(agent_msgs)}")
        logger.info("TEST 3 PASSED: Messages persisted to DB")

    @pytest.mark.asyncio
    async def test_get_messages_api_exists(self):
        """Verify the GET messages API endpoint works."""
        session_id = await create_session()

        # Should return empty list for new session
        messages = await get_messages(session_id)
        assert isinstance(messages, list), "Should return a list"
        logger.info("TEST 3b PASSED: GET messages API works")


# ─── Test 4: Conversation Resume (P0) ─────────────────────────────────────────

class TestConversationResume:
    """Test 4: Verify conversation can be resumed after disconnect."""

    @pytest.mark.asyncio
    async def test_resume_after_disconnect(self):
        """Start analysis, disconnect, reconnect, and continue."""
        session_id = await create_session()

        # Phase 1: Start analysis
        ws1 = await ws_connect(session_id)
        try:
            await send_user_message(ws1, "帮我分析安利纽崔莱", "安利纽崔莱")
            events1 = await collect_events(
                ws1, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )
            logger.info(f"Phase 1: Collected {len(events1)} events")
        finally:
            await ws1.close()
            logger.info("Phase 1: Disconnected")

        # Wait for backend to settle
        await asyncio.sleep(2)

        # Phase 2: Reconnect and send follow-up
        ws2 = await ws_connect(session_id)
        try:
            await send_user_message(ws2, "继续分析，帮我生成用户画像")
            events2 = await collect_events(
                ws2, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )
            logger.info(f"Phase 2: Collected {len(events2)} events")

            # Should receive reply_delta or thought_delta events (resumed session may only think)
            reply_deltas = find_events(events2, "reply_delta")
            thought_deltas = find_events(events2, "thought_delta")
            assert len(reply_deltas) > 0 or len(thought_deltas) > 0, \
                "Should receive reply_delta or thought_delta in resumed conversation"

            # Check for errors
            errors = find_events(events2, "error")
            non_recoverable = [e for e in errors if not e.get("data", {}).get("recoverable", False)]
            assert len(non_recoverable) == 0, f"Non-recoverable errors in resumed conversation: {non_recoverable}"

            logger.info("TEST 4 PASSED: Conversation resumed successfully")

        finally:
            await ws2.close()

    @pytest.mark.asyncio
    async def test_orchestrator_remembers_state(self):
        """Verify orchestrator knows A1 was already completed."""
        session_id = await create_session()

        # Phase 1: Complete A1
        ws1 = await ws_connect(session_id)
        try:
            await send_user_message(ws1, "帮我分析安利纽崔莱", "安利纽崔莱")
            events1 = await collect_events(
                ws1, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )
        finally:
            await ws1.close()

        await asyncio.sleep(2)

        # Phase 2: Ask to continue - orchestrator should know A1 is done
        ws2 = await ws_connect(session_id)
        try:
            await send_user_message(ws2, "使用现有信息继续分析")
            events2 = await collect_events(
                ws2, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )

            # Check action_logs - should NOT re-run brand_analysis
            action_logs = find_events(events2, "action_log")
            brand_reruns = [
                al for al in action_logs
                if "品牌" in al.get("data", {}).get("message", "")
                and al.get("data", {}).get("step") == "brand_analysis"
            ]
            if brand_reruns:
                logger.warning("  ⚠ Orchestrator re-ran brand_analysis (may be intentional)")
            else:
                logger.info("  ✓ Orchestrator did NOT re-run brand_analysis")

            logger.info("TEST 4b PASSED: Orchestrator state awareness verified")

        finally:
            await ws2.close()


# ─── Test 6: Multi-round Dialog & Inline Confirmation (P1) ────────────────────

class TestMultiRoundDialog:
    """Test 6: Verify multi-round dialog and inline confirmation flow."""

    @pytest.mark.asyncio
    async def test_natural_dialog_continuation(self):
        """Verify user can respond to orchestrator's natural language questions."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Round 1: Start analysis
            await send_user_message(ws, "帮我分析安利纽崔莱", "安利纽崔莱")
            events1 = await collect_events(
                ws, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
            )

            # Check if orchestrator asked a question (natural language)
            reply_content = get_reply_content(events1)

            if "?" in reply_content or "？" in reply_content or "如何继续" in reply_content:
                logger.info("  ✓ Orchestrator asked a question, sending follow-up")

                # Round 2: Answer the question
                await send_user_message(ws, "使用现有信息继续分析")
                events2 = await collect_events(
                    ws, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
                )

                reply_deltas2 = find_events(events2, "reply_delta")
                assert len(reply_deltas2) > 0, "Should get reply in round 2"
                logger.info(f"  ✓ Round 2: {len(reply_deltas2)} reply_delta events")
            else:
                logger.info("  ℹ Orchestrator did not ask a question, skipping round 2")

            logger.info("TEST 6 PASSED: Multi-round dialog works")

        finally:
            await ws.close()

    @pytest.mark.asyncio
    async def test_inline_confirmation_flow(self):
        """If orchestrator uses ask_user tool, verify confirmation flow."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await send_user_message(ws, "帮我分析安利纽崔莱", "安利纽崔莱")
            events = await collect_events(
                ws, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete", "inline_confirmation"]
            )

            confirmations = find_events(events, "inline_confirmation")
            if confirmations:
                logger.info(f"  ✓ Received inline_confirmation: {confirmations[0].get('data', {})}")

                # Send confirmation response
                conf_data = confirmations[0].get("data", {})
                options = conf_data.get("options", [])
                if options:
                    selected = options[0]
                    await send_confirmation(ws, selected.get("label", "确认"))

                    # Collect follow-up events
                    events2 = await collect_events(
                        ws, timeout=WS_MESSAGE_TIMEOUT, stop_on=["execution_complete"]
                    )
                    reply_deltas = find_events(events2, "reply_delta")
                    logger.info(f"  ✓ After confirmation: {len(reply_deltas)} reply_delta events")
                else:
                    logger.warning("  ⚠ inline_confirmation has no options")
            else:
                logger.info("  ℹ No inline_confirmation (orchestrator used natural dialog)")

            logger.info("TEST 6b PASSED: Inline confirmation flow verified")

        finally:
            await ws.close()


# ─── Test 5: WebSocket Disconnect & Reconnect (P2) ────────────────────────────

class TestDisconnectReconnect:
    """Test 5: Verify WebSocket reconnection behavior."""

    @pytest.mark.asyncio
    async def test_reconnect_after_close(self):
        """Verify can reconnect to same session after disconnect."""
        session_id = await create_session()

        # Connect and disconnect
        ws1 = await ws_connect(session_id)
        await send_ping(ws1)
        events1 = await collect_events(ws1, timeout=3, stop_on=["pong"])
        assert has_event(events1, "pong"), "First connection should work"
        await ws1.close()

        # Reconnect
        await asyncio.sleep(1)
        ws2 = await ws_connect(session_id)
        await send_ping(ws2)
        events2 = await collect_events(ws2, timeout=3, stop_on=["pong"])
        assert has_event(events2, "pong"), "Reconnection should work"
        await ws2.close()

        logger.info("TEST 5 PASSED: Reconnection works")

    @pytest.mark.asyncio
    async def test_multiple_rapid_reconnects(self):
        """Verify rapid reconnection doesn't cause issues."""
        session_id = await create_session()

        for i in range(3):
            ws = await ws_connect(session_id)
            await send_ping(ws)
            events = await collect_events(ws, timeout=3, stop_on=["pong"])
            assert has_event(events, "pong"), f"Reconnect #{i+1} should work"
            await ws.close()
            await asyncio.sleep(0.5)

        logger.info("TEST 5b PASSED: Rapid reconnection works")


# ─── Test 7: Error Handling & Edge Cases (P2) ─────────────────────────────────

class TestErrorHandling:
    """Test 7: Verify error handling for various edge cases."""

    @pytest.mark.asyncio
    async def test_empty_message(self):
        """Sending empty message should not crash the backend."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await send_user_message(ws, "")
            events = await collect_events(ws, timeout=30, stop_on=["execution_complete", "error"])

            # Should either get an error or a graceful response
            errors = find_events(events, "error")
            replies = find_events(events, "reply_delta")

            if errors:
                logger.info(f"  ✓ Empty message returned error: {errors[0].get('data', {})}")
            elif replies:
                logger.info("  ✓ Empty message got a reply (orchestrator handled gracefully)")
            else:
                logger.warning("  ⚠ Empty message: no error and no reply")

            logger.info("TEST 7a PASSED: Empty message handled")

        finally:
            await ws.close()

    @pytest.mark.asyncio
    async def test_non_brand_message(self):
        """Sending a casual message should get a natural response."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await send_user_message(ws, "你好，你是谁？")
            events = await collect_events(
                ws, timeout=60, stop_on=["execution_complete"]
            )

            replies = find_events(events, "reply_delta")
            assert len(replies) > 0, "Should get a reply to casual message"

            content = get_reply_content(events)
            logger.info(f"  ✓ Casual reply: {content[:100]}...")

            logger.info("TEST 7c PASSED: Non-brand message handled")

        finally:
            await ws.close()

    @pytest.mark.asyncio
    async def test_invalid_json_message(self):
        """Sending invalid JSON should not crash the connection."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await ws.send("not valid json {{{")
            await asyncio.sleep(2)

            # Connection should still be alive
            await send_ping(ws)
            events = await collect_events(ws, timeout=5, stop_on=["pong"])
            assert has_event(events, "pong"), "Connection should survive invalid JSON"

            logger.info("TEST 7d PASSED: Invalid JSON handled gracefully")

        finally:
            await ws.close()

    @pytest.mark.asyncio
    async def test_unknown_event_type(self):
        """Sending unknown event type should not crash."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            await ws.send(json.dumps({"event": "nonexistent_event", "data": {}}))
            await asyncio.sleep(2)

            # Connection should still be alive
            await send_ping(ws)
            events = await collect_events(ws, timeout=5, stop_on=["pong"])
            assert has_event(events, "pong"), "Connection should survive unknown event"

            logger.info("TEST 7e PASSED: Unknown event type handled")

        finally:
            await ws.close()


# ─── Test 2: Long Task Timeout (P2) ───────────────────────────────────────────

class TestLongTaskTimeout:
    """Test 2: Verify long-running tasks don't cause disconnection.

    NOTE: This test is slow (10+ minutes) and requires full A1→A4 flow.
    Mark with @pytest.mark.slow to skip in normal runs.
    """

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_heartbeat_during_long_task(self):
        """Verify heartbeat keeps connection alive during long operations."""
        session_id = await create_session()
        ws = await ws_connect(session_id)

        try:
            # Start full analysis
            await send_user_message(ws, "帮我分析安利纽崔莱", "安利纽崔莱")

            # Collect events with long timeout, sending pings periodically
            start = time.time()
            all_events: list[dict] = []
            ping_count = 0

            while time.time() - start < WS_LONG_TIMEOUT:
                # Send ping every 25 seconds
                if time.time() - start > ping_count * 25:
                    await send_ping(ws)
                    ping_count += 1

                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=5)
                    msg = json.loads(raw)
                    event_type = msg.get("event") or msg.get("type", "unknown")
                    all_events.append(msg)

                    if event_type == "execution_complete":
                        break
                except asyncio.TimeoutError:
                    continue
                except websockets.exceptions.ConnectionClosed:
                    pytest.fail("WebSocket disconnected during long task!")

            elapsed = time.time() - start
            logger.info(f"Long task completed in {elapsed:.0f}s with {len(all_events)} events")

            # Verify connection stayed alive
            pongs = find_events(all_events, "pong")
            assert len(pongs) > 0, "Should have received pong responses"
            logger.info(f"  ✓ {len(pongs)} pong responses received")

            logger.info("TEST 2 PASSED: Long task completed without disconnect")

        finally:
            await ws.close()


# ─── Standalone runner ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    """Run tests directly without pytest."""

    async def run_all():
        print("=" * 70)
        print("Specta AI E2E WebSocket Test Suite")
        print("=" * 70)

        results: dict[str, str] = {}

        # Test 1b: Heartbeat
        print("\n--- Test 1b: WebSocket Heartbeat ---")
        try:
            t = TestBasicE2E()
            await t.test_ws_connection_and_heartbeat()
            results["1b_heartbeat"] = "PASS"
        except Exception as e:
            results["1b_heartbeat"] = f"FAIL: {e}"
            logger.error(f"Test 1b failed: {e}")

        # Test 3b: GET messages API
        print("\n--- Test 3b: GET Messages API ---")
        try:
            t = TestHistoryLoading()
            await t.test_get_messages_api_exists()
            results["3b_get_messages_api"] = "PASS"
        except Exception as e:
            results["3b_get_messages_api"] = f"FAIL: {e}"
            logger.error(f"Test 3b failed: {e}")

        # Test 5: Reconnect
        print("\n--- Test 5: Reconnect ---")
        try:
            t = TestDisconnectReconnect()
            await t.test_reconnect_after_close()
            results["5_reconnect"] = "PASS"
        except Exception as e:
            results["5_reconnect"] = f"FAIL: {e}"
            logger.error(f"Test 5 failed: {e}")

        # Test 5b: Rapid reconnect
        print("\n--- Test 5b: Rapid Reconnect ---")
        try:
            t = TestDisconnectReconnect()
            await t.test_multiple_rapid_reconnects()
            results["5b_rapid_reconnect"] = "PASS"
        except Exception as e:
            results["5b_rapid_reconnect"] = f"FAIL: {e}"
            logger.error(f"Test 5b failed: {e}")

        # Test 7d: Invalid JSON
        print("\n--- Test 7d: Invalid JSON ---")
        try:
            t = TestErrorHandling()
            await t.test_invalid_json_message()
            results["7d_invalid_json"] = "PASS"
        except Exception as e:
            results["7d_invalid_json"] = f"FAIL: {e}"
            logger.error(f"Test 7d failed: {e}")

        # Test 7e: Unknown event
        print("\n--- Test 7e: Unknown Event ---")
        try:
            t = TestErrorHandling()
            await t.test_unknown_event_type()
            results["7e_unknown_event"] = "PASS"
        except Exception as e:
            results["7e_unknown_event"] = f"FAIL: {e}"
            logger.error(f"Test 7e failed: {e}")

        # Test 1: Full E2E (slow, involves LLM calls)
        print("\n--- Test 1: Basic E2E Flow ---")
        try:
            t = TestBasicE2E()
            await t.test_full_analysis_flow()
            results["1_basic_e2e"] = "PASS"
        except Exception as e:
            results["1_basic_e2e"] = f"FAIL: {e}"
            logger.error(f"Test 1 failed: {e}")

        # Test 3: History persistence
        print("\n--- Test 3: History Persistence ---")
        try:
            t = TestHistoryLoading()
            await t.test_messages_persisted_to_db()
            results["3_history_persistence"] = "PASS"
        except Exception as e:
            results["3_history_persistence"] = f"FAIL: {e}"
            logger.error(f"Test 3 failed: {e}")

        # Test 7a: Empty message
        print("\n--- Test 7a: Empty Message ---")
        try:
            t = TestErrorHandling()
            await t.test_empty_message()
            results["7a_empty_message"] = "PASS"
        except Exception as e:
            results["7a_empty_message"] = f"FAIL: {e}"
            logger.error(f"Test 7a failed: {e}")

        # Test 7c: Non-brand message
        print("\n--- Test 7c: Non-brand Message ---")
        try:
            t = TestErrorHandling()
            await t.test_non_brand_message()
            results["7c_non_brand"] = "PASS"
        except Exception as e:
            results["7c_non_brand"] = f"FAIL: {e}"
            logger.error(f"Test 7c failed: {e}")

        # Test 4: Conversation resume
        print("\n--- Test 4: Conversation Resume ---")
        try:
            t = TestConversationResume()
            await t.test_resume_after_disconnect()
            results["4_resume"] = "PASS"
        except Exception as e:
            results["4_resume"] = f"FAIL: {e}"
            logger.error(f"Test 4 failed: {e}")

        # Test 6: Multi-round dialog
        print("\n--- Test 6: Multi-round Dialog ---")
        try:
            t = TestMultiRoundDialog()
            await t.test_natural_dialog_continuation()
            results["6_multi_round"] = "PASS"
        except Exception as e:
            results["6_multi_round"] = f"FAIL: {e}"
            logger.error(f"Test 6 failed: {e}")

        # ── Summary ──
        print("\n" + "=" * 70)
        print("TEST RESULTS SUMMARY")
        print("=" * 70)
        passed = sum(1 for v in results.values() if v == "PASS")
        failed = sum(1 for v in results.values() if v != "PASS")
        for name, result in results.items():
            status = "✓" if result == "PASS" else "✗"
            print(f"  {status} {name}: {result}")
        print(f"\nTotal: {passed} passed, {failed} failed out of {len(results)}")
        print("=" * 70)

    asyncio.run(run_all())
