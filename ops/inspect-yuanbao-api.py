"""Read-only bounded Yuanbao API diagnostics using existing service credentials."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


ROOT = Path("/srv/ageo-deploy")
LEGACY_HOST = "api.hunyuan.cloud.tencent.com"
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}")
ERROR_KEYS = {"code", "type", "source", "upstream_status", "status", "status_code"}


def retirement_indicator(response):
    try:
        body = response.json()
        error = body.get("error", {}) if isinstance(body, dict) else {}
        message = str(error.get("message") or "") + str(error.get("message_zh") or "")
        return any(term in message.lower() for term in ("retired", "deprecated", "offline", "\u4e0b\u7ebf"))
    except (ValueError, TypeError, AttributeError):
        return False


def emit(section, **values):
    print(json.dumps({"section": section, **values}, ensure_ascii=True), flush=True)


def service_config(expected):
    if not re.fullmatch(r"[0-9a-f]{40}", expected):
        raise ValueError("invalid_expected_release")
    release = (ROOT / "current").resolve()
    if (release / ".release-sha").read_text().strip() != expected:
        raise ValueError("release_mismatch")
    pid = subprocess.check_output(
        ["systemctl", "show", "ageo-backend.service", "--property=MainPID", "--value"],
        text=True, timeout=15,
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
    emit("release", sha=expected, process_matches_release=True)


def safe_identifier(value, secret):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value)
    if (not IDENTIFIER.fullmatch(text) or text.lower().startswith(("sk-", "bearer"))
            or (secret and (secret in text or text in secret))):
        return None
    return text


def endpoint_summary(endpoint, secret):
    parsed = urlsplit(endpoint)
    path = parsed.path or "/"
    if not re.fullmatch(r"/[A-Za-z0-9_./-]{0,159}", path) or (secret and secret in path):
        path = None
    return {"host": safe_identifier(parsed.hostname or "", secret), "path": path}


def structured_error(response, secret):
    """Do not emit messages, arbitrary fields, response bodies, or request headers."""
    try:
        body = response.json()
    except (ValueError, TypeError):
        return []
    found = []
    pending = [("root", body, 0)]
    while pending:
        location, node, depth = pending.pop()
        if not isinstance(node, dict):
            continue
        fields = {}
        for key, value in node.items():
            if not isinstance(key, str):
                continue
            normalized = key.lower()
            if normalized in ERROR_KEYS:
                safe = safe_identifier(value, secret)
                if safe is not None:
                    fields[normalized] = safe
            if depth < 2 and normalized in {"error", "response", "upstream", "details"}:
                pending.append((location + "." + normalized, value, depth + 1))
        if fields:
            found.append({"location": location, **fields})
    return found


async def inspect():
    import httpx
    from dotenv import dotenv_values
    from app.core.config import settings
    from app.core.fetchers.api.hunyuan_client import HunyuanClient

    key = (settings.HUNYUAN_API_KEY or "").strip()
    shared = dotenv_values(ROOT / "shared/backend/.env.local")
    emit("existing_credential_slots", present={
        name: bool(os.environ.get(name) or shared.get(name))
        for name in ("TOKENHUB_API_KEY", "TENCENT_TOKENHUB_API_KEY", "HUNYUAN_API_KEY")
    })
    del shared
    configured_url = (settings.HUNYUAN_BASE_URL or "").strip()
    configured_model = settings.HUNYUAN_FAST_MODEL or settings.HUNYUAN_MODEL
    configured = endpoint_summary(configured_url, key)
    configured["model"] = safe_identifier(configured_model, key)
    client = HunyuanClient(model=settings.HUNYUAN_FAST_MODEL or None) if key else None
    effective = endpoint_summary(client.endpoint, key) if client else None
    if effective is not None:
        effective["model"] = safe_identifier(client.model, key)
    emit("configuration", configured=configured, effective=effective,
         key_present=bool(key),
         legacy_configuration=HunyuanClient.has_legacy_configuration(
             configured_url, configured_model))
    if client is None:
        emit("current_client", skipped="key_missing")
        return
    try:
        result = await asyncio.wait_for(
            client.ask_with_search("What is Tencent? Answer briefly."), timeout=70,
        )
        emit("current_client", http_status=200, answer_present=bool(result.answer_text),
             references=len(result.search_references or []))
    except httpx.HTTPStatusError as error:
        emit("current_client", http_status=error.response.status_code,
             error_fields=structured_error(error.response, key))
    except Exception as error:
        emit("current_client", failure_type=type(error).__name__)

    parsed = urlsplit(configured_url)
    if parsed.hostname != LEGACY_HOST:
        emit("original_endpoint", skipped="configured_host_is_not_official_legacy")
        return
    if (parsed.scheme != "https" or parsed.port not in (None, 443)
            or parsed.username or parsed.password or parsed.query or parsed.fragment):
        emit("original_endpoint", skipped="unsupported_endpoint_shape")
        return
    endpoint = configured_url.rstrip("/")
    if not endpoint.endswith("/chat/completions"):
        endpoint += "/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as http:
            response = await http.post(
                endpoint, headers={"Authorization": "Bearer " + key},
                json={"model": configured_model, "stream": False, "max_tokens": 32,
                      "messages": [{"role": "user", "content": "Reply OK."}]},
            )
        emit("original_endpoint", endpoint=endpoint_summary(endpoint, key),
             model=safe_identifier(configured_model, key),
             http_status=response.status_code,
             retirement_mentioned=retirement_indicator(response),
             error_fields=structured_error(response, key) if response.status_code >= 400 else [])
    except Exception as error:
        emit("original_endpoint", failure_type=type(error).__name__)

    # Test HY3 on the same verified original gateway without client URL/model rewriting.
    try:
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as http:
            response = await asyncio.wait_for(
                http.post(
                    endpoint, headers={"Authorization": "Bearer " + key},
                    json={"model": "hy3", "stream": False, "max_tokens": 32,
                          "messages": [{"role": "user", "content": "Reply OK."}]},
                ),
                timeout=25,
            )
        answer_present = False
        if response.status_code == 200:
            try:
                answer_present = bool(client._extract_answer(response.json()).strip())
            except (ValueError, TypeError):
                pass
        emit("original_endpoint_hy3", model="hy3", http_status=response.status_code,
             answer_present=answer_present,
             error_fields=structured_error(response, key) if response.status_code >= 400 else [])
    except Exception as error:
        emit("original_endpoint_hy3", model="hy3", answer_present=False,
             failure_type=type(error).__name__)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-release", required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    service_config(args.expected_release)
    asyncio.run(inspect())


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        emit("failure", failure_type=type(error).__name__)
        raise SystemExit(1)
