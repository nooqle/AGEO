"""One public compatibility probe, not product or remote-egress acceptance.

Protocol references:
https://chromedevtools.github.io/devtools-protocol/tot/Target/
https://chromedevtools.github.io/devtools-protocol/tot/Fetch/
Only raw CDP targets created by this connection are used. No target discovery,
stored credentials, application imports, database, model, or browser shutdown.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import json
import re
import signal
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit


TOTAL_SECONDS = 120
WORK_SECONDS = 100
CLEANUP_SECONDS = 15
COMMAND_SECONDS = 15
MAX_MESSAGE_BYTES = 2 * 1024 * 1024
SEARCH_URL = "https://www.bing.com/search?" + urlencode(
    {"q": "site:example.com Example Domain"}
)
SOURCE_URLS = frozenset({"https://example.com/", "https://www.example.com/"})
ENV_PATH = Path("/srv/ageo-deploy/shared/backend/.env.local")


class ProbeFailure(Exception):
    """Only fixed stage codes are printed, never exception text or remote data."""


def emit(stage: str, **values: object) -> None:
    print(json.dumps({"stage": stage, **values}, ensure_ascii=True), flush=True)


def settings() -> tuple[str, str]:
    selected = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key.strip() in {"AIO_BASE_URL", "AIO_AUTH_TOKEN"}:
            selected[key.strip()] = value.strip().strip("\"'")
    base = selected.get("AIO_BASE_URL", "").rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"}):
        raise ProbeFailure("configuration_rejected")
    return base, selected.get("AIO_AUTH_TOKEN", "")


def cdp_endpoint(base: str, reported: str) -> str:
    trusted = urlsplit(base)
    endpoint = urlsplit(reported)
    if (endpoint.scheme not in {"http", "https", "ws", "wss", ""}
            or endpoint.username or endpoint.password or endpoint.fragment
            or "\\" in reported or any(ord(c) < 33 for c in reported)):
        raise ProbeFailure("cdp_endpoint_rejected")
    # Only AIO's same-origin /cdp proxy is admitted. Metadata aliases never
    # receive credentials, and arbitrary devtools hosts/paths are not followed.
    browser_proxy = re.fullmatch(
        r"/cdp/devtools/browser/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
        r"[0-9a-f]{4}-[0-9a-f]{12}", endpoint.path,
    )
    if endpoint.path not in {"/cdp", "/cdp/"} and browser_proxy is None:
        raise ProbeFailure("cdp_proxy_path_unsupported")
    if endpoint.hostname not in {None, trusted.hostname, "localhost"}:
        try:
            alias = ipaddress.ip_address(endpoint.hostname)
        except ValueError:
            raise ProbeFailure("cdp_alias_rejected") from None
        if not alias.is_private or alias.is_unspecified or alias.is_multicast:
            raise ProbeFailure("cdp_alias_rejected")
    return urlunsplit(("wss" if trusted.scheme == "https" else "ws",
                       trusted.netloc, endpoint.path, endpoint.query, ""))


def public_source(raw: str) -> str | None:
    parsed = urlsplit(raw)
    if parsed.scheme == "https" and parsed.hostname == "www.bing.com" and parsed.path == "/ck/a":
        encoded = parse_qs(parsed.query).get("u", [""])[0]
        if encoded.startswith("a1"):
            try:
                raw = base64.urlsafe_b64decode(encoded[2:] + "=" * (-len(encoded[2:]) % 4)).decode("utf-8")
            except (ValueError, UnicodeError):
                return None
    if raw in SOURCE_URLS:
        return raw
    return None


class PublicHTML(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.text: list[str] = []
        self.skip_depth = 0
        self.result_depth = 0
        self.result_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag in {"script", "style"}:
            self.skip_depth += 1
        if tag == "li":
            if "b_algo" in (values.get("class") or "").split():
                self.result_count += 1
                self.result_depth = 1
            elif self.result_depth:
                self.result_depth += 1
        if tag == "a" and self.result_depth:
            source = public_source(values.get("href") or "")
            if source and source not in self.links:
                self.links.append(source)

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.skip_depth = max(0, self.skip_depth - 1)
        if tag == "li" and self.result_depth:
            self.result_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip_depth:
            self.text.append(data)


class CDP:
    def __init__(self, socket: object) -> None:
        self.socket = socket
        self.next_id = 0
        self.pending: dict[int, asyncio.Future] = {}
        self.session_id = ""
        self.frame_id = ""
        self.document_request_seen = False
        self.allowed_urls = {SEARCH_URL}
        self.allowed_count = 0
        self.blocked_count = 0
        self.loaded = asyncio.Event()
        self.fatal = asyncio.get_running_loop().create_future()
        self.handlers: set[asyncio.Task] = set()
        self.reader = asyncio.create_task(self.read())

    async def command(self, method: str, params: dict | None = None,
                      *, own: bool = False, cleanup: bool = False) -> dict:
        if own and not self.session_id:
            raise ProbeFailure("missing_own_session")
        self.next_id += 1
        command_id = self.next_id
        future = asyncio.get_running_loop().create_future()
        self.pending[command_id] = future
        packet = {"id": command_id, "method": method, "params": params or {}}
        if own:
            packet["sessionId"] = self.session_id
        try:
            await self.socket.send(json.dumps(packet))
            watched = {future} if cleanup else {future, self.fatal}
            done, _ = await asyncio.wait(watched, timeout=COMMAND_SECONDS,
                                         return_when=asyncio.FIRST_COMPLETED)
            if not done or (not cleanup and self.fatal in done):
                raise ProbeFailure("cdp_command_failed")
            response = future.result()
            if "error" in response:
                raise ProbeFailure("required_command_unsupported")
            return response.get("result", {})
        finally:
            self.pending.pop(command_id, None)

    async def request(self, event: dict) -> None:
        params = event.get("params", {})
        request = params.get("request", {})
        allowed = (request.get("url") in self.allowed_urls
                   and request.get("method") == "GET"
                   and params.get("resourceType") == "Document"
                   and bool(self.frame_id) and params.get("frameId") == self.frame_id
                   and not self.document_request_seen and self.allowed_count < 2)
        method = "Fetch.continueRequest" if allowed else "Fetch.failRequest"
        arguments = {"requestId": params["requestId"]}
        if not allowed:
            arguments["errorReason"] = "BlockedByClient"
            self.blocked_count += 1
        else:
            self.document_request_seen = True
            self.allowed_count += 1
        try:
            await self.command(method, arguments, own=True)
        except Exception:
            if not self.fatal.done():
                self.fatal.set_result(True)

    async def read(self) -> None:
        try:
            async for raw in self.socket:
                event = json.loads(raw)
                if "id" in event:
                    future = self.pending.get(event["id"])
                    if future is not None and not future.done():
                        future.set_result(event)
                    continue
                if not self.session_id or event.get("sessionId") != self.session_id:
                    continue
                method = event.get("method")
                if method == "Fetch.requestPaused":
                    task = asyncio.create_task(self.request(event))
                    self.handlers.add(task)
                    task.add_done_callback(self.handlers.discard)
                elif method == "Page.loadEventFired":
                    self.loaded.set()
                elif method in {"Target.attachedToTarget", "Page.javascriptDialogOpening"}:
                    # Unexpected children stay paused; never resume or inspect them.
                    if not self.fatal.done():
                        self.fatal.set_result(True)
        except Exception:
            if not self.fatal.done():
                self.fatal.set_result(True)

    async def document(self, url: str) -> PublicHTML:
        self.allowed_urls = {url}
        self.document_request_seen = False
        self.loaded.clear()
        result = await self.command("Page.navigate", {"url": url}, own=True)
        if result.get("errorText"):
            raise ProbeFailure("navigation_rejected")
        await asyncio.wait_for(self.loaded.wait(), COMMAND_SECONDS)
        tree = await self.command("Page.getFrameTree", own=True)
        if tree.get("frameTree", {}).get("frame", {}).get("url") != url:
            raise ProbeFailure("unexpected_final_url")
        document = await self.command("DOM.getDocument", {"depth": 0}, own=True)
        result = await self.command("DOM.getOuterHTML", {"nodeId": document["root"]["nodeId"]}, own=True)
        html = result.get("outerHTML", "")
        if not isinstance(html, str) or len(html.encode("utf-8")) > MAX_MESSAGE_BYTES:
            raise ProbeFailure("document_limit")
        if re.search(r'b_captcha|g-recaptcha|type=["\']password', html, re.I):
            raise ProbeFailure("human_verification_required")
        parsed = PublicHTML()
        parsed.feed(html)
        return parsed

    async def stop_reader(self) -> None:
        tasks = [self.reader, *self.handlers]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def probe() -> bool:
    # Imports are delayed so missing existing dependencies produce sanitized output.
    import httpx
    from websockets.legacy.client import Connect

    class NoRedirectConnect(Connect):
        def handle_redirect(self, uri: str) -> None:
            raise ProbeFailure("cdp_redirect_rejected")

    cdp = None
    socket = None
    context_id = ""
    cleanup_confirmed = False
    succeeded = False

    async def work() -> None:
        nonlocal cdp, socket, context_id, succeeded
        base, token = settings()
        headers = {"Authorization": "Bearer " + token} if token else {}
        async with httpx.AsyncClient(timeout=COMMAND_SECONDS, follow_redirects=False,
                                     trust_env=False) as client:
            response = await client.get(base + "/v1/browser/info", headers=headers)
            if response.status_code != 200:
                raise ProbeFailure("browser_metadata_unavailable")
            metadata = response.json()
            metadata = metadata.get("data", metadata)
            endpoint = cdp_endpoint(base, metadata.get("cdp_url", ""))
        socket = await NoRedirectConnect(endpoint, extra_headers=headers,
                                         open_timeout=COMMAND_SECONDS, close_timeout=2,
                                         max_size=MAX_MESSAGE_BYTES, ping_interval=None)
        cdp = CDP(socket)
        context = await cdp.command("Target.createBrowserContext", {"disposeOnDetach": True})
        context_id = context.get("browserContextId", "")
        if not isinstance(context_id, str) or not context_id:
            raise ProbeFailure("missing_own_context")
        await cdp.command("Browser.setDownloadBehavior", {
            "behavior": "deny", "browserContextId": context_id,
        })
        target = await cdp.command("Target.createTarget", {
            "url": "about:blank", "browserContextId": context_id, "background": True,
        })
        target_id = target.get("targetId")
        if not isinstance(target_id, str) or not target_id:
            raise ProbeFailure("missing_own_target")
        attached = await cdp.command("Target.attachToTarget", {"targetId": target_id, "flatten": True})
        cdp.session_id = attached.get("sessionId", "")
        if not isinstance(cdp.session_id, str) or not cdp.session_id:
            raise ProbeFailure("missing_own_session")
        for method, params in (
            ("Page.enable", {}),
            ("Emulation.setScriptExecutionDisabled", {"value": True}),
            ("Network.enable", {}),
            ("Network.setBypassServiceWorker", {"bypass": True}),
            ("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": True,
                                      "flatten": True}),
            ("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]}),
        ):
            await cdp.command(method, params, own=True)
        tree = await cdp.command("Page.getFrameTree", own=True)
        cdp.frame_id = tree.get("frameTree", {}).get("frame", {}).get("id", "")
        if not isinstance(cdp.frame_id, str) or not cdp.frame_id:
            raise ProbeFailure("missing_own_frame")
        emit("own_context_ready", javascript=False, downloads=False)
        search = await cdp.document(SEARCH_URL)
        emit("search", results=min(search.result_count, 6), allowed_sources=len(search.links))
        if not search.links:
            raise ProbeFailure("no_allowed_search_result")
        source = search.links[0]
        document = await cdp.document(source)
        body = " ".join(" ".join(document.text).split())[:12000]
        if "Example Domain" not in body:
            raise ProbeFailure("public_source_not_confirmed")
        emit("source", url=source, chars=len(body), sha256=hashlib.sha256(body.encode("utf-8")).hexdigest())
        succeeded = True

    try:
        await asyncio.wait_for(work(), WORK_SECONDS)
    except asyncio.CancelledError:
        emit("probe", status="cancelled")
    except ProbeFailure as exc:
        emit("probe", status="failed", reason=str(exc))
    except Exception:
        emit("probe", status="failed", reason="bounded_operation_failed")
    finally:
        if cdp is not None and isinstance(context_id, str) and context_id:
            try:
                await asyncio.wait_for(cdp.command("Target.disposeBrowserContext", {
                    "browserContextId": context_id,
                }, cleanup=True), CLEANUP_SECONDS)
                cleanup_confirmed = True
            except Exception:
                pass
        if cdp is not None:
            emit("requests", allowed=cdp.allowed_count, blocked=cdp.blocked_count)
            await cdp.stop_reader()
        if socket is not None:
            try:
                await asyncio.wait_for(socket.close(), 2)
            except Exception:
                pass
            finally:
                # Disconnect only our CDP transport, never close the browser.
                if socket.transport is not None:
                    socket.transport.abort()
        emit("cleanup", confirmed=cleanup_confirmed,
             disconnect_fallback=bool(context_id and not cleanup_confirmed))
    return succeeded and cleanup_confirmed


async def main() -> int:
    task = asyncio.current_task()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, task.cancel)
    try:
        return 0 if await asyncio.wait_for(probe(), TOTAL_SECONDS) else 1
    except BaseException:
        emit("probe", status="failed", reason="runtime_unavailable_or_deadline")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
