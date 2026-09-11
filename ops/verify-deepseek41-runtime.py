"""Bounded release verification using the running service's configuration.

Runs small provider probes and read-only database checks. Does not create users,
tokens, tasks, collection runs, or ledger entries. Never emits answers or secrets.
"""

import argparse
import asyncio
import base64
import json
import logging
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import zlib


ROOT = Path("/srv/ageo-deploy")


def emit(section, **values):
    print(json.dumps({"section": section, **values}, ensure_ascii=True), flush=True)


def service_config(expected):
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("expected_release_must_be_full_sha")
    release = (ROOT / "current").resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output(
        ["systemctl", "show", "ageo-backend.service", "--property=MainPID", "--value"], text=True,
    ).strip()
    if not pid.isdigit() or int(pid) <= 0:
        raise ValueError("backend_not_running")
    backend = release / "aeo-platform/backend"
    if Path(f"/proc/{pid}/cwd").resolve() != backend.resolve():
        raise ValueError("service_release_mismatch")
    entries = Path(f"/proc/{pid}/environ").read_bytes().split(b"\0")
    process_env = {key.decode(): value.decode() for item in entries if b"=" in item
                   for key, value in [item.split(b"=", 1)]}
    os.environ.clear()
    os.environ.update(process_env)
    os.chdir(backend)
    sys.path.insert(0, str(backend))
    for name in ("ageo-backend.service", "ageo-frontend.service"):
        state = subprocess.check_output(["systemctl", "is-active", name], text=True).strip()
        if state != "active":
            raise ValueError("service_not_active")
    emit("release", sha=expected, process_matches_release=True, services_active=True)


def sample_image():
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    pixels = b"".join(b"\x00" + bytes([255, 0, 0]) * 64 + bytes([0, 0, 255]) * 64 for _ in range(64))
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 64, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))
    return base64.b64encode(png).decode()


async def verify():
    import httpx
    from sqlalchemy import text
    from app.core.database import AsyncSessionLocal
    from app.core.llm import get_llm_model, task_routing
    from app.core.llm.deepseek import DeepSeekConfig, DeepSeekModel
    from app.core.fetchers.api.deepseek_client import DeepSeekClient
    from app.core.fetchers.api.doubao_client import DoubaoClient
    from app.core.fetchers.api.hunyuan_client import HunyuanClient
    from app.core.fetchers.api.kimi_client import KimiClient
    from app.core.fetchers.browser.browser_agent_loop import _get_browser_agent_llm_model, _browser_observation_content
    from app.schemas.account_admin import ControlPlaneObservabilitySnapshot
    from app.services.control_plane_service import ControlPlaneService
    from app.workflow import brand_search, nodes_a4

    profiles = {
        "global": get_llm_model(), "orchestrator": task_routing.get_orchestrator_llm_model(),
        "a1": task_routing.get_a1_llm_model(), "a2": task_routing.get_a2_llm_model(),
        "a3": task_routing.get_a3_llm_model(), "light": task_routing.get_fast_structured_llm_model(),
        "multimodal": task_routing.get_multimodal_llm_model(), "browser": _get_browser_agent_llm_model(),
    }
    identities = {name: {"provider": type(model.config).__name__, "model": model.config.model_name}
                  for name, model in profiles.items()}
    emit("model_routes", profiles=identities)
    assert all(item["provider"] == "DeepSeekConfig" and item["model"] == "deepseek-flash"
               for item in identities.values()), "model_route_mismatch"

    async with httpx.AsyncClient(timeout=20) as http:
        for url in ("http://127.0.0.1:8000/health", "http://127.0.0.1:3000", "https://imspecta.com"):
            response = await http.get(url)
            emit("health", url=url, status=response.status_code)
            response.raise_for_status()
        response = await http.get("https://demo.imspecta.com", follow_redirects=False)
        assert response.status_code in (301, 302, 307, 308)
        assert response.headers.get("location", "").startswith("https://imspecta.com")
        emit("redirect", status=response.status_code, primary_domain=True)

    vision = DeepSeekModel(DeepSeekConfig(model_name="deepseek-flash", thinking_enabled=False, max_tokens=256))
    content = _browser_observation_content(
        {"instruction": "Return JSON with left and right colors in English."},
        {"image_base64": sample_image(), "content_type": "image/png"},
    )
    visual = await vision.async_call([{"role": "user", "content": content}], response_format={"type": "json_object"})
    colors = json.loads(visual.content)
    assert "red" in str(colors.get("left")).lower() and "blue" in str(colors.get("right")).lower()
    emit("vision", passed=True, usage_present=visual.usage is not None)
    browser_visual = await profiles["browser"].async_call(
        [{"role": "user", "content": content}],
        response_format={"type": "json_object"}, max_tokens=1024,
    )
    browser_colors = json.loads(browser_visual.content)
    assert "red" in str(browser_colors.get("left")).lower() and "blue" in str(browser_colors.get("right")).lower()
    emit("browser_agent_vision", passed=True, usage_present=browser_visual.usage is not None)

    model = DeepSeekModel(DeepSeekConfig(model_name="deepseek-flash", thinking_enabled=True,
                                        reasoning_effort="low", max_tokens=1024))
    tool = {"type": "function", "function": {"name": "lookup", "description": "Look up a value by key.",
            "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}}
    history = [{"role": "user", "content": "Use lookup for alpha, then report the returned value exactly."}]
    first = await model.async_call(history, tools=[tool], tool_choice="auto")
    assert first.tool_calls, "tool_not_executed"
    history.append({"role": "assistant", "content": first.content,
                    "reasoning_content": "".join(block.text for block in first.thinking_blocks),
                    "tool_calls": [{"id": call.id, "type": "function", "function": {
                        "name": call.name, "arguments": json.dumps(call.arguments)}} for call in first.tool_calls]})
    history.extend({"role": "tool", "tool_call_id": call.id,
                    "content": '{"value":"SPECTA_DEPLOY_TOOL_OK"}'} for call in first.tool_calls)
    final = await model.async_call(history, tools=[tool], tool_choice="auto")
    assert "SPECTA_DEPLOY_TOOL_OK" in final.content and not final.tool_calls
    emit("tool_history", passed=True, calls=len(first.tool_calls))

    def stream_probe():
        return list(vision.stream([{"role": "user", "content": "Reply exactly SPECTA_STREAM_OK"}], max_tokens=64))
    chunks = await asyncio.to_thread(stream_probe)
    assert "SPECTA_STREAM_OK" in "".join(chunk.content for chunk in chunks)
    assert any(chunk.usage and chunk.usage.prompt_tokens is not None for chunk in chunks)
    emit("stream_usage", passed=True)

    native = await nodes_a4._fetch_from_deepseek(DeepSeekClient(),
        "Search the official DeepSeek API documentation once. Give its API base URL briefly with a source URL.")
    assert native.get("success") and native.get("web_search_executed") and native.get("citations"), "native_search_failed"
    usage = nodes_a4._llm_usage_from_provider_payload(native["provider_usage"])
    assert usage.prompt_tokens == usage.cached_prompt_tokens + usage.cache_miss_prompt_tokens
    emit("a4_native_search", passed=True, model=native.get("provider_model"), references=len(native["citations"]),
         prompt=usage.prompt_tokens, hit=usage.cached_prompt_tokens, miss=usage.cache_miss_prompt_tokens,
         output=usage.completion_tokens)

    captured = []
    original_recorder = brand_search.record_provider_usage_async
    async def capture_usage(**kwargs):
        captured.append(kwargs["usage"])
    brand_search.record_provider_usage_async = capture_usage
    try:
        synthesis = DeepSeekModel(DeepSeekConfig(model_name="deepseek-flash", thinking_enabled=False, max_tokens=2048))
        result = await brand_search.call_brand_search(messages=[
            {"role": "system", "content": "Return only a short JSON object with name, website and sources. No Markdown."},
            {"role": "user", "content": "Research the DeepSeek company and its official website using native search."},
        ], call_model=synthesis.async_call)
        parsed = json.loads(result.content)
        assert parsed.get("name") and parsed.get("website") and parsed.get("sources") and len(captured) == 1
        assert captured[0].prompt_tokens is not None
        emit("a1_native_synthesis", passed=True, native_usage_events=len(captured), database_writes=False)
    finally:
        brand_search.record_provider_usage_async = original_recorder

    # Other platforms remain their own providers. Report existing credential or
    # endpoint failures independently instead of routing them through DeepSeek.
    for platform, factory in (("kimi", KimiClient), ("doubao", DoubaoClient), ("yuanbao", HunyuanClient)):
        try:
            client = factory()
            answer = await asyncio.wait_for(client.ask_with_search(
                "Search the web and give the official website of DeepSeek in one short sentence with a source URL."), timeout=150)
            emit("platform_api", platform=platform, model=client.model, passed=bool(answer.answer_text),
                 references=len(answer.search_references))
        except Exception as error:
            emit("platform_api", platform=platform, passed=False, error_type=type(error).__name__,
                 status=error.response.status_code if isinstance(error, httpx.HTTPStatusError) else None)

    async with AsyncSessionLocal() as db:
        snapshot = await ControlPlaneService(db).get_observability_snapshot(days=7, limit=10)
        ControlPlaneObservabilitySnapshot.model_validate(snapshot)
        timezone_name = (await db.execute(text("SHOW TIMEZONE"))).scalar_one()
        now = (await db.execute(text("SELECT CURRENT_TIMESTAMP"))).scalar_one()
        assert now.tzinfo is not None
        emit("control_postgres", schema_valid=True, call_count=snapshot["summary"]["call_count"],
             database_timezone=timezone_name, aware_timestamp=True, database_writes=False)
    emit("core_acceptance", passed=True, full_browser_matrix_verified=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    try:
        service_config(args.expected_release)
        asyncio.run(asyncio.wait_for(verify(), timeout=650))
    except Exception as error:
        # Exception messages/provider payloads may contain credentials or inputs.
        emit("verification_failed", error_type=type(error).__name__)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
