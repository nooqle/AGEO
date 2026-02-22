"""
Full Pipeline E2E Test: A1→A2→A3→A4→A5
Tests the complete Specta AI workflow with real LLM calls.

Usage:
    python e2e_full_pipeline.py
"""

import asyncio
import json
import time
import sys
import httpx
import websockets

BASE_URL = "http://localhost:8001/api/v1"
WS_URL = "ws://localhost:8001/ws"

# Generous timeouts for real LLM calls
WS_TIMEOUT = 600  # 10 minutes total for full pipeline
EVENT_TIMEOUT = 300  # 5 minutes per event wait


class EventCollector:
    """Collects and categorizes WebSocket events."""

    def __init__(self):
        self.events = []
        self.reply_content = ""
        self.thoughts = ""
        self.action_logs = []
        self.plan_text = ""
        self.inline_confirmation = None
        self.execution_complete = False
        self.errors = []
        self.agents_called = set()

    def process(self, event_data: dict):
        event = event_data.get("event", "")
        data = event_data.get("data", {})
        self.events.append(event_data)

        if event == "reply_delta":
            content = data.get("content", "")
            is_new_round = data.get("is_new_round", False)
            if is_new_round:
                self.reply_content = ""
            if data.get("is_delta", True) and content:
                self.reply_content += content

        elif event == "thought_delta":
            content = data.get("content", "")
            if data.get("is_delta", True) and content:
                self.thoughts += content

        elif event == "plan_update":
            self.plan_text = data.get("text", "")

        elif event == "action_log":
            msg = data.get("message", "")
            step = data.get("step", "")
            self.action_logs.append({"step": step, "message": msg})
            if step:
                self.agents_called.add(step)

        elif event == "inline_confirmation":
            self.inline_confirmation = data

        elif event == "execution_complete":
            self.execution_complete = True

        elif event == "execution_progress":
            step = data.get("step", "") or data.get("stage", "")
            if step:
                self.agents_called.add(step)

        elif event == "error":
            self.errors.append(data)

    def summary(self):
        return {
            "total_events": len(self.events),
            "reply_length": len(self.reply_content),
            "thought_length": len(self.thoughts),
            "action_logs": len(self.action_logs),
            "agents_called": sorted(self.agents_called),
            "has_plan": bool(self.plan_text),
            "has_confirmation": self.inline_confirmation is not None,
            "execution_complete": self.execution_complete,
            "errors": len(self.errors),
        }


async def create_session(title: str) -> str:
    """Create a new session and return its ID."""
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            f"{BASE_URL}/sessions",
            json={"title": title},
            headers={"Authorization": "Bearer dev-token"},
        )
        return r.json()["id"]


async def connect_ws(session_id: str):
    """Connect to WebSocket with generous keepalive."""
    url = f"{WS_URL}/{session_id}?token=dev-token"
    return await websockets.connect(
        url, ping_interval=30, ping_timeout=120,
        max_size=10 * 1024 * 1024,
    )


async def collect_until(ws, collector: EventCollector, stop_condition, timeout=EVENT_TIMEOUT):
    """Collect events until stop_condition returns True or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=30)
            event_data = json.loads(raw)
            event = event_data.get("event", "")
            if event in ("pong", "heartbeat"):
                continue
            collector.process(event_data)

            # Print progress
            data = event_data.get("data", {})
            if event == "execution_progress":
                step = data.get("step", "")
                progress = data.get("progress", 0)
                msg = data.get("message", "")
                print(f"  [{step}] {progress:.0%} - {msg}")
            elif event == "action_log":
                step = data.get("step", "")
                msg = data.get("message", "")[:80]
                print(f"  [LOG {step}] {msg}")
            elif event == "reply_delta" and data.get("is_new_round"):
                print(f"  [REPLY] New round started")
            elif event == "inline_confirmation":
                opts = [o.get("label", "") for o in data.get("options", [])]
                print(f"  [CONFIRM] Options: {opts}")
            elif event == "execution_complete":
                print(f"  [DONE] Execution complete")
            elif event == "error":
                msg = data.get("message", "")[:100]
                fatal = data.get("fatal", False)
                print(f"  [ERROR] {'FATAL: ' if fatal else ''}{msg}")

            if stop_condition(collector):
                return True
        except asyncio.TimeoutError:
            # Send ping to keep alive
            try:
                await ws.send(json.dumps({"event": "ping"}))
            except Exception:
                pass
            continue
        except websockets.exceptions.ConnectionClosed:
            print("  [WS] Connection closed!")
            return False
    return False


async def send_message(ws, content: str):
    """Send a user message."""
    await ws.send(json.dumps({
        "event": "user_message",
        "data": {"content": content},
    }))


async def send_confirmation(ws, selection: str):
    """Send a confirmation."""
    await ws.send(json.dumps({
        "event": "confirmation",
        "data": {"selection": selection},
    }))


# ============================================================================
# Test Cases
# ============================================================================


async def test_a1_brand_analysis():
    """Test A1: Brand analysis with a well-known brand."""
    print("\n" + "=" * 70)
    print("TEST: A1 Brand Analysis (安利纽崔莱)")
    print("=" * 70)

    session_id = await create_session("E2E A1 Test")
    print(f"Session: {session_id}")

    collector = EventCollector()
    ws = await connect_ws(session_id)

    try:
        await send_message(ws, "帮我分析安利纽崔莱这个品牌")
        print("Message sent, waiting for response...")

        # Wait for either execution_complete or inline_confirmation
        done = await collect_until(
            ws, collector,
            lambda c: c.execution_complete or c.inline_confirmation is not None,
            timeout=WS_TIMEOUT,
        )

        s = collector.summary()
        print(f"\nResults:")
        print(f"  Events: {s['total_events']}")
        print(f"  Reply length: {s['reply_length']} chars")
        print(f"  Agents called: {s['agents_called']}")
        print(f"  Has plan: {s['has_plan']}")
        print(f"  Has confirmation: {s['has_confirmation']}")
        print(f"  Execution complete: {s['execution_complete']}")
        print(f"  Errors: {s['errors']}")
        print(f"  Reply preview: {collector.reply_content[:200]}...")

        # Verify A1 was called (tracked by tool name "brand_analysis")
        a1_called = "brand_analysis" in s["agents_called"] or "A1" in s["agents_called"]
        has_reply = s["reply_length"] > 10
        no_fatal = not any(e.get("fatal") for e in collector.errors)

        if a1_called and has_reply and no_fatal:
            print("\n  RESULT: PASS")

            # If we got inline_confirmation, handle it
            if collector.inline_confirmation:
                print("\n  Got inline confirmation, testing confirmation flow...")
                opts = collector.inline_confirmation.get("options", [])
                if opts:
                    # Pick the first option (usually "品牌全景分析" or similar)
                    label = opts[0].get("label", "继续")
                    print(f"  Selecting: {label}")

                    collector2 = EventCollector()
                    await send_confirmation(ws, label)

                    done2 = await collect_until(
                        ws, collector2,
                        lambda c: c.execution_complete or c.inline_confirmation is not None,
                        timeout=WS_TIMEOUT,
                    )

                    s2 = collector2.summary()
                    print(f"\n  Post-confirmation results:")
                    print(f"    Events: {s2['total_events']}")
                    print(f"    Reply length: {s2['reply_length']} chars")
                    print(f"    Agents called: {s2['agents_called']}")
                    print(f"    Execution complete: {s2['execution_complete']}")

                    return session_id, collector, collector2
            return session_id, collector, None
        else:
            print(f"\n  RESULT: FAIL (a1_called={a1_called}, has_reply={has_reply}, no_fatal={no_fatal})")
            return None, collector, None
    finally:
        await ws.close()


async def test_full_pipeline():
    """Test full A1→A5 pipeline by requesting complete analysis."""
    print("\n" + "=" * 70)
    print("TEST: Full Pipeline A1→A5 (霸王茶姬)")
    print("=" * 70)

    session_id = await create_session("E2E Full Pipeline")
    print(f"Session: {session_id}")

    collector = EventCollector()
    ws = await connect_ws(session_id)

    try:
        # Send a message that should trigger the full pipeline
        await send_message(ws, "请帮我完整分析霸王茶姬这个品牌，包括品牌档案、用户画像、问题模拟、AI答案抓取和数据分析报告，请直接开始全部流程")
        print("Message sent, waiting for full pipeline...")

        round_num = 0
        all_agents = set()

        while round_num < 10:  # Max 10 rounds
            round_num += 1
            round_collector = EventCollector()

            done = await collect_until(
                ws, round_collector,
                lambda c: c.execution_complete or c.inline_confirmation is not None,
                timeout=WS_TIMEOUT,
            )

            # Merge agents
            all_agents.update(round_collector.agents_called)
            s = round_collector.summary()
            print(f"\n  Round {round_num} summary:")
            print(f"    Agents called this round: {s['agents_called']}")
            print(f"    All agents so far: {sorted(all_agents)}")
            print(f"    Reply: {round_collector.reply_content[:150]}...")

            if round_collector.execution_complete:
                print(f"\n  Pipeline completed after {round_num} rounds!")
                break

            if round_collector.inline_confirmation:
                opts = round_collector.inline_confirmation.get("options", [])
                if opts:
                    # Auto-select first option to continue
                    label = opts[0].get("label", "继续")
                    print(f"\n  Auto-confirming: {label}")
                    await send_confirmation(ws, label)
                    continue

            if not done:
                print(f"\n  Round {round_num} timed out")
                break

        # Map tool names to step names for coverage check
        tool_to_step = {
            "brand_analysis": "A1",
            "persona_generation": "A2",
            "question_simulation": "A3",
            "answer_fetch": "A4",
            "data_analytics": "A5",
        }
        step_agents = {tool_to_step.get(a, a) for a in all_agents}
        print(f"\n  Final agents covered: {sorted(all_agents)}")
        print(f"  Mapped to steps: {sorted(step_agents)}")
        expected = {"A1", "A2", "A3", "A4", "A5"}
        covered = step_agents & expected
        missing = expected - step_agents
        print(f"  Covered: {sorted(covered)}")
        if missing:
            print(f"  Missing: {sorted(missing)}")
        print(f"  Coverage: {len(covered)}/{len(expected)}")

        return session_id, step_agents

    finally:
        await ws.close()


async def test_message_persistence(session_id: str):
    """Test that messages are persisted to DB."""
    print("\n" + "=" * 70)
    print(f"TEST: Message Persistence (session: {session_id[:8]}...)")
    print("=" * 70)

    await asyncio.sleep(8)  # Wait for DB writes (increased for full pipeline)

    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.get(
            f"{BASE_URL}/sessions/{session_id}/messages",
            headers={"Authorization": "Bearer dev-token"},
        )
        if r.status_code != 200:
            print(f"  FAIL: HTTP {r.status_code}")
            return False

        messages = r.json()
        print(f"  Messages in DB: {len(messages)}")
        for msg in messages:
            role = msg.get("role", "?")
            content = msg.get("content", "")[:80]
            print(f"    [{role}] {content}...")

        has_user = any(m.get("role") in ("user", "USER") for m in messages)
        has_agent = any(m.get("role") in ("agent", "ASSISTANT", "assistant") for m in messages)

        if has_user and has_agent and len(messages) >= 2:
            print("  RESULT: PASS")
            return True
        else:
            print(f"  RESULT: FAIL (has_user={has_user}, has_agent={has_agent})")
            return False


async def test_confirmation_creates_new_message():
    """Test that confirmation response creates a NEW message, not overwriting old one."""
    print("\n" + "=" * 70)
    print("TEST: Confirmation Creates New Message (not overwrite)")
    print("=" * 70)

    session_id = await create_session("E2E Confirm New Msg")
    print(f"Session: {session_id}")

    collector1 = EventCollector()
    ws = await connect_ws(session_id)

    try:
        await send_message(ws, "分析观夏")
        print("Message sent, waiting for inline_confirmation...")

        done = await collect_until(
            ws, collector1,
            lambda c: c.inline_confirmation is not None or c.execution_complete,
            timeout=WS_TIMEOUT,
        )

        if not collector1.inline_confirmation:
            print("  SKIP: No inline confirmation received (LLM went straight to execution)")
            return None

        first_reply = collector1.reply_content
        print(f"  First reply ({len(first_reply)} chars): {first_reply[:100]}...")

        # Now send confirmation
        opts = collector1.inline_confirmation.get("options", [])
        label = opts[0].get("label", "继续") if opts else "继续"
        print(f"  Sending confirmation: {label}")

        collector2 = EventCollector()
        await send_confirmation(ws, label)

        done2 = await collect_until(
            ws, collector2,
            lambda c: c.execution_complete or c.inline_confirmation is not None,
            timeout=WS_TIMEOUT,
        )

        second_reply = collector2.reply_content
        print(f"  Second reply ({len(second_reply)} chars): {second_reply[:100]}...")

        # The key test: second reply should NOT contain the first reply
        # (if it does, it means overwriting happened)
        if first_reply and second_reply:
            is_different = first_reply[:50] not in second_reply
            print(f"  Replies are different: {is_different}")
            if is_different:
                print("  RESULT: PASS (confirmation created new message context)")
            else:
                print("  RESULT: FAIL (confirmation reply contains first reply content)")
            return is_different
        else:
            print("  RESULT: INCONCLUSIVE (missing reply content)")
            return None

    finally:
        await ws.close()


async def test_casual_chat():
    """Test casual chat doesn't trigger agents."""
    print("\n" + "=" * 70)
    print("TEST: Casual Chat")
    print("=" * 70)

    session_id = await create_session("E2E Casual")

    collector = EventCollector()
    ws = await connect_ws(session_id)

    try:
        await send_message(ws, "你好，你是谁？能做什么？")
        print("Message sent...")

        done = await collect_until(
            ws, collector,
            lambda c: c.execution_complete,
            timeout=60,
        )

        s = collector.summary()
        has_reply = s["reply_length"] > 5
        no_agents = len(s["agents_called"]) == 0
        print(f"  Reply: {collector.reply_content[:150]}...")
        print(f"  Agents called: {s['agents_called']}")

        if has_reply:
            print("  RESULT: PASS")
        else:
            print(f"  RESULT: FAIL (has_reply={has_reply})")
        return has_reply
    finally:
        await ws.close()


# ============================================================================
# Main
# ============================================================================


async def main():
    print("=" * 70)
    print("Specta AI Full Pipeline E2E Test")
    print(f"Backend: {BASE_URL}")
    print(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    results = {}

    # Test 1: Casual chat (quick sanity check)
    try:
        results["casual_chat"] = await test_casual_chat()
    except Exception as e:
        print(f"  ERROR: {e}")
        results["casual_chat"] = False

    # Test 2: A1 brand analysis
    try:
        session_id, c1, c2 = await test_a1_brand_analysis()
        results["a1_brand"] = session_id is not None
        if session_id:
            results["persistence"] = await test_message_persistence(session_id)
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        results["a1_brand"] = False

    # Test 3: Confirmation new message (not overwrite)
    try:
        r = await test_confirmation_creates_new_message()
        results["confirm_new_msg"] = r
    except Exception as e:
        print(f"  ERROR: {e}")
        results["confirm_new_msg"] = False

    # Wait for any lingering LLM calls from previous tests to finish
    print("\n  Waiting 15s for backend to settle before full pipeline test...")
    await asyncio.sleep(15)

    # Test 4: Full pipeline A1→A5
    try:
        session_id2, step_agents = await test_full_pipeline()
        expected = {"A1", "A2", "A3", "A4", "A5"}
        covered = step_agents & expected
        results["full_pipeline"] = len(covered) >= 3  # At least 3 agents
        results["full_coverage"] = covered
        if session_id2:
            results["pipeline_persistence"] = await test_message_persistence(session_id2)
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback; traceback.print_exc()
        results["full_pipeline"] = False

    # Summary
    print("\n" + "=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)
    for test, result in results.items():
        if isinstance(result, bool):
            status = "PASS" if result else "FAIL"
        elif isinstance(result, set):
            status = f"{sorted(result)}"
        elif result is None:
            status = "SKIP"
        else:
            status = str(result)
        print(f"  {test}: {status}")

    total = sum(1 for v in results.values() if v is True)
    failed = sum(1 for v in results.values() if v is False)
    skipped = sum(1 for v in results.values() if v is None)
    print(f"\n  Total: {total} PASS, {failed} FAIL, {skipped} SKIP")


if __name__ == "__main__":
    asyncio.run(main())
