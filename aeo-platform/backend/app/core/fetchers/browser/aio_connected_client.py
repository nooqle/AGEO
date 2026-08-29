"""Playwright-compatible browser client backed by an AIO CDP endpoint."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from patchright.async_api import Browser, BrowserContext, async_playwright

from app.core.config import settings
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.services.aio_runtime_contracts import AioPlatformRoots
from app.services.aio_foreground_lease import (
    AioForegroundLeaseTimeout,
    aio_foreground_lease_manager,
    build_aio_foreground_key,
)
from app.services.aio_session_manager import aio_session_manager

logger = logging.getLogger(__name__)

_CHROME_VERSION_RE = re.compile(r"Chrome/([0-9.]+)")


class AioConnectedBrowserClient(PlaywrightBrowserClient):
    """Remote browser client that reuses the existing Playwright handler surface.

    This client intentionally subclasses ``PlaywrightBrowserClient`` so the
    existing browser handlers can treat it as a Playwright-capable client.
    The only lifecycle change is that it connects to an existing AIO browser
    via CDP instead of launching a new persistent Chromium process locally.
    """

    def __init__(
        self,
        *,
        session_name: str,
        workspace_id: str,
        task_id: str,
        platform: str,
        purpose: str = "a4",
        auth_scope_id: str | None = None,
        run_scope_id: str | None = None,
    ) -> None:
        super().__init__(session_name=session_name)
        self.workspace_id = workspace_id
        self.task_id = task_id
        self.platform = platform
        self.purpose = purpose
        self.auth_scope_id = auth_scope_id or workspace_id
        self.run_scope_id = run_scope_id or workspace_id
        self.browser: Browser | None = None
        self.aio_session_id: str | None = None
        self.browser_info: dict[str, Any] = {}
        self.platform_roots: AioPlatformRoots | None = None
        self.foreground_key: str | None = None
        self._page_owned_by_client = False
        self._context_owned_by_client = False
        self._storage_state_loaded_into_context = False
        self.context_reuse_strategy: str | None = None

    @staticmethod
    def _page_matches_target_host(page_url: str | None, target_url: str | None) -> bool:
        if not page_url or not target_url:
            return False
        page_host = AioConnectedBrowserClient._normalize_host(page_url)
        target_host = AioConnectedBrowserClient._normalize_host(target_url)
        return bool(page_host and target_host and page_host == target_host)

    @staticmethod
    def _normalize_host(url: str | None) -> str:
        host = (urlparse(url or "").netloc or "").lower().strip()
        if host.startswith("www."):
            return host[4:]
        return host

    def _resolved_interaction_mode(self) -> str:
        if self.platform != "deepseek":
            return "cdp_dom"
        raw_mode = str(settings.DEEPSEEK_AIO_INTERACTION_MODE or "").strip().lower()
        aliases = {
            "gui": "gui_actions",
            "visual": "gui_actions",
            "vnc": "gui_actions",
            "cdp": "cdp_dom",
            "dom": "cdp_dom",
            "playwright": "cdp_dom",
        }
        return aliases.get(raw_mode, raw_mode or "cdp_dom")

    def should_request_automation_foreground(self) -> bool:
        """Return true only for automation that uses the visible GUI surface."""

        return self._resolved_interaction_mode() == "gui_actions"

    async def _ensure_playwright(self):
        """Start Patchright for CDP attachment without installing local browsers."""

        if self.playwright is None:
            self.playwright = await self._start_playwright()

    async def _start_playwright(self):
        # AIO connects to a remote Chromium over CDP. It only needs the
        # Patchright driver process, not a locally installed Chromium binary.
        try:
            return await async_playwright().start()
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] async_playwright().start() failed: %s; retrying",
                self.session_name,
                exc,
            )
            await asyncio.sleep(1)
            return await async_playwright().start()

    async def _reset_runtime(self, *, preserve_remote_surface: bool = True) -> None:
        """Detach from the remote browser without killing the AIO runtime."""

        try:
            try:
                await self._persist_storage_state()
            except Exception as persist_error:
                logger.warning(
                    "[AIO Browser:%s] Failed to persist storage state before reset: %s",
                    self.session_name,
                    persist_error,
                )

            if (
                not preserve_remote_surface
                and self.page is not None
                and self._page_owned_by_client
            ):
                try:
                    await self.page.close()
                except Exception:
                    pass
            self.page = None
            self._page_owned_by_client = False

            if self.context is not None and self._context_owned_by_client:
                try:
                    await self.context.close()
                except Exception:
                    pass

            if self.browser is not None:
                try:
                    await self.browser.close()
                except Exception:
                    pass
            self.browser = None
            self.context = None
            self._context_owned_by_client = False
            self._storage_state_loaded_into_context = False

            if self.playwright is not None:
                try:
                    await self.playwright.stop()
                except Exception:
                    pass
            self.playwright = None
        except Exception:
            self.browser = None
            self.context = None
            self.page = None
            self.playwright = None
            self._page_owned_by_client = False
            self._context_owned_by_client = False
            self._storage_state_loaded_into_context = False

    async def _ensure_remote_runtime(self) -> dict[str, Any]:
        session = await aio_session_manager.acquire_session(
            workspace_id=self.workspace_id,
            task_id=self.task_id,
            purpose=f"{self.purpose}:{self.platform}",
            platforms=[self.platform],
        )
        self.aio_session_id = session.session_id
        self.foreground_key = build_aio_foreground_key(
            session.base_url,
            session.sandbox_ref,
        )
        self.platform_roots = await aio_session_manager.ensure_platform_roots(
            session_id=session.session_id,
            task_id=self.task_id,
            platform=self.platform,
            workspace_id=self.workspace_id,
            auth_scope_id=self.auth_scope_id,
            run_scope_id=self.run_scope_id,
        )
        self.browser_info = await aio_session_manager.get_browser_connection(
            session.session_id
        )
        return self.browser_info

    @staticmethod
    def _preferred_languages() -> list[str]:
        preferred: list[str] = []
        locale = str(settings.AIO_BROWSER_LOCALE or "").strip()
        if locale:
            preferred.append(locale)
        for part in str(settings.AIO_BROWSER_ACCEPT_LANGUAGE or "").split(","):
            language = part.split(";", 1)[0].strip()
            if language and language not in preferred:
                preferred.append(language)
        return preferred or ["en-US", "en"]

    @staticmethod
    def _resolve_viewport(viewport: Any) -> dict[str, int]:
        if isinstance(viewport, dict):
            try:
                width = int(viewport.get("width"))
                height = int(viewport.get("height"))
            except (TypeError, ValueError):
                width = 0
                height = 0
            if width > 0 and height > 0:
                return {"width": width, "height": height}
        return {"width": 1280, "height": 720}

    @staticmethod
    def _extract_chrome_version(user_agent: str | None) -> str | None:
        match = _CHROME_VERSION_RE.search(str(user_agent or ""))
        if not match:
            return None
        version = match.group(1).strip()
        return version or None

    def _browser_chrome_version(self) -> str | None:
        raw_version = getattr(self.browser, "version", None)
        if callable(raw_version):
            try:
                raw_version = raw_version()
            except Exception:
                raw_version = None
        version = str(raw_version or "").strip()
        if not version:
            return None
        if version.startswith("Chrome/"):
            return version.split("/", 1)[1].strip() or None
        return version if version[0].isdigit() else None

    def _resolve_context_user_agent(self, browser_info: dict[str, Any]) -> str | None:
        runtime_user_agent = str(browser_info.get("user_agent") or "").strip()
        if "Linux" in runtime_user_agent or "X11" in runtime_user_agent:
            return runtime_user_agent

        chrome_version = self._browser_chrome_version() or self._extract_chrome_version(
            runtime_user_agent
        )
        if not chrome_version:
            return None
        return (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            f"Chrome/{chrome_version} Safari/537.36"
        )

    def _should_reuse_default_context_without_host_match(self) -> bool:
        configured = str(
            settings.AIO_BROWSER_REUSE_DEFAULT_CONTEXT_PLATFORMS or ""
        ).strip()
        if not configured:
            return False
        tokens = {
            token.strip().lower()
            for token in configured.replace(";", ",").split(",")
            if token.strip()
        }
        platform = str(self.platform or "").strip().lower()
        return "*" in tokens or platform in tokens

    async def _load_storage_state(self) -> dict[str, Any] | None:
        if self.platform_roots is None:
            return None

        try:
            runtime_client = aio_session_manager.get_runtime_client()
            file_result = await runtime_client.read_text_file(
                self.platform_roots.state_path,
                missing_ok=True,
            )
            if file_result is None:
                file_result = await runtime_client.read_text_file(
                    self.platform_roots.legacy_state_path,
                    missing_ok=True,
                )
                if file_result is not None:
                    logger.info(
                        "[AIO Browser:%s] Loaded legacy auth state for platform=%s; it will be migrated on next save",
                        self.session_name,
                        self.platform,
                    )
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] Failed to read browser_state.json, continuing without storage restore: %s",
                self.session_name,
                exc,
            )
            return None
        if file_result is None or not file_result.content.strip():
            return None

        try:
            payload = json.loads(file_result.content)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[AIO Browser:%s] Ignoring invalid browser_state.json: %s",
                self.session_name,
                exc,
            )
            return None

        if not isinstance(payload, dict):
            logger.warning(
                "[AIO Browser:%s] Ignoring non-object browser_state.json payload",
                self.session_name,
            )
            return None

        if self.aio_session_id is not None:
            await aio_session_manager.mark_platform_state_loaded(
                session_id=self.aio_session_id,
                task_id=self.task_id,
                platform=self.platform,
            )

        return payload

    async def _persist_storage_state(self) -> None:
        if self.context is None or self.platform_roots is None:
            return

        try:
            state = await self.context.storage_state()
            runtime_client = aio_session_manager.get_runtime_client()
            serialized_state = json.dumps(state, ensure_ascii=False, indent=2)
            await runtime_client.write_text_file(
                self.platform_roots.state_path,
                serialized_state,
            )
            await runtime_client.write_text_file(
                self.platform_roots.cookies_path,
                json.dumps(state.get("cookies", []), ensure_ascii=False, indent=2),
            )
            if self.aio_session_id is not None:
                await aio_session_manager.mark_platform_state_saved(
                    session_id=self.aio_session_id,
                    task_id=self.task_id,
                    platform=self.platform,
                )
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] Failed to persist storage state, continuing without blocking browser reuse: %s",
                self.session_name,
                exc,
            )

    async def persist_runtime_state(self) -> None:
        """Persist the current remote browser state without resetting the session."""

        await self._persist_storage_state()

    async def _create_isolated_remote_context(
        self, context_options: dict[str, Any]
    ) -> BrowserContext:
        if self.browser is None:
            raise RuntimeError("AIO 浏览器未连接")

        self._storage_state_loaded_into_context = False
        try:
            context = await self.browser.new_context(**context_options)
        except Exception as exc:
            if "storage_state" not in context_options:
                raise
            logger.warning(
                "[AIO Browser:%s] Failed to create context with storage_state; "
                "falling back to empty context and page-level restore: %s",
                self.session_name,
                exc,
            )
            fallback_options = dict(context_options)
            fallback_options.pop("storage_state", None)
            context = await self.browser.new_context(**fallback_options)
            await self._apply_language_init_script(context)
            return context

        self._storage_state_loaded_into_context = "storage_state" in context_options
        await self._apply_language_init_script(context)
        return context

    async def _apply_language_init_script(self, context: BrowserContext) -> None:
        locale = json.dumps(str(settings.AIO_BROWSER_LOCALE or "zh-CN"))
        languages = json.dumps(self._preferred_languages(), ensure_ascii=False)
        try:
            await context.add_init_script(
                f"""
(() => {{
  const language = {locale};
  const languages = {languages};
  try {{
    Object.defineProperty(navigator, 'language', {{
      configurable: true,
      get: () => language,
    }});
    Object.defineProperty(navigator, 'languages', {{
      configurable: true,
      get: () => languages,
    }});
  }} catch (_) {{
    // Ignore init-script failures; locale/header settings still apply.
  }}
}})();
"""
            )
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] Failed to add language init script: %s",
                self.session_name,
                exc,
            )

    async def _get_or_create_remote_context(
        self, target_url: str | None = None
    ) -> BrowserContext:
        if self.browser is None:
            raise RuntimeError("AIO 浏览器未连接")

        existing_contexts = list(getattr(self.browser, "contexts", []) or [])
        target_host = self._normalize_host(target_url)
        logger.info(
            "[AIO Browser:%s] remote contexts discovered=%d target_host=%s",
            self.session_name,
            len(existing_contexts),
            target_host or "<none>",
        )
        reusable_contexts = [candidate for candidate in existing_contexts if candidate]
        self.context_reuse_strategy = None
        if reusable_contexts and target_host:
            for candidate in reversed(reusable_contexts):
                existing_pages = [
                    page for page in candidate.pages if not page.is_closed()
                ]
                for page in reversed(existing_pages):
                    page_host = self._normalize_host(page.url)
                    if page_host == target_host:
                        self._context_owned_by_client = False
                        self._storage_state_loaded_into_context = False
                        logger.info(
                            "[AIO Browser:%s] reusing existing remote context matched by target_host=%s page_url=%s",
                            self.session_name,
                            target_host,
                            page.url,
                        )
                        self.context_reuse_strategy = "host_matched_existing_context"
                        return candidate

            if self._should_reuse_default_context_without_host_match():
                self._context_owned_by_client = False
                self._storage_state_loaded_into_context = False
                self.context_reuse_strategy = "platform_default_context_reuse"
                logger.info(
                    "[AIO Browser:%s] reusing default remote context for strict platform=%s without target_host match=%s",
                    self.session_name,
                    self.platform,
                    target_host,
                )
                return reusable_contexts[-1]

            logger.info(
                "[AIO Browser:%s] no existing context matched target_host=%s; creating isolated platform context",
                self.session_name,
                target_host,
            )
        elif reusable_contexts:
            self._context_owned_by_client = False
            self._storage_state_loaded_into_context = False
            logger.info(
                "[AIO Browser:%s] reusing existing remote context because no target host was provided",
                self.session_name,
            )
            self.context_reuse_strategy = "first_existing_context_no_target"
            return reusable_contexts[0]
        logger.info(
            "[AIO Browser:%s] creating isolated context for workspace=%s task=%s platform=%s",
            self.session_name,
            self.workspace_id,
            self.task_id,
            self.platform,
        )
        self._context_owned_by_client = True
        self.context_reuse_strategy = "isolated_context_created"
        browser_info = self.browser_info if isinstance(self.browser_info, dict) else {}
        context_options: dict[str, Any] = {
            "viewport": self._resolve_viewport(browser_info.get("viewport")),
            "locale": settings.AIO_BROWSER_LOCALE,
            "timezone_id": settings.AIO_BROWSER_TIMEZONE_ID,
            "extra_http_headers": {
                "Accept-Language": settings.AIO_BROWSER_ACCEPT_LANGUAGE,
            },
        }
        resolved_user_agent = self._resolve_context_user_agent(browser_info)
        if resolved_user_agent:
            context_options["user_agent"] = resolved_user_agent
        storage_state = await self._load_storage_state()
        if storage_state:
            context_options["storage_state"] = storage_state
        return await self._create_isolated_remote_context(context_options)

    async def _get_or_create_remote_page(self, target_url: str | None = None) -> None:
        if self.context is None:
            raise RuntimeError("AIO 浏览器上下文未初始化")

        existing_pages = [
            candidate for candidate in self.context.pages if not candidate.is_closed()
        ]
        logger.info(
            "[AIO Browser:%s] context pages discovered=%d urls=%s",
            self.session_name,
            len(existing_pages),
            [candidate.url for candidate in existing_pages],
        )
        target_host = self._normalize_host(target_url)
        if existing_pages:
            usable = [
                candidate
                for candidate in existing_pages
                if (candidate.url or "") not in {"", "about:blank"}
            ]
            preferred = None
            if target_host:
                for candidate in usable:
                    candidate_host = self._normalize_host(candidate.url)
                    if candidate_host == target_host:
                        preferred = candidate
                        break
                if preferred is not None:
                    self.page = preferred
                    self._page_owned_by_client = False
                    foreground = await self.bring_to_front_for_automation(
                        reason="reuse_page"
                    )
                    logger.info(
                        "[AIO Browser:%s] reusing existing page url=%s target_host=%s automation_foreground=%s",
                        self.session_name,
                        self.page.url,
                        target_host,
                        bool(foreground.get("success")),
                    )
                    return

                self.page = await self.context.new_page()
                self._page_owned_by_client = True
                await self.bring_to_front_for_automation(reason="new_page")
                logger.info(
                    "[AIO Browser:%s] created new page because no existing page matched target_host=%s",
                    self.session_name,
                    target_host,
                )
                return

            self.page = usable[0] if usable else existing_pages[0]
            self._page_owned_by_client = False
            foreground = await self.bring_to_front_for_automation(
                reason="reuse_any_page"
            )
            logger.info(
                "[AIO Browser:%s] reusing existing page url=%s target_host=%s automation_foreground=%s",
                self.session_name,
                self.page.url,
                "<none>",
                bool(foreground.get("success")),
            )
            return

        self.page = await self.context.new_page()
        self._page_owned_by_client = True
        await self.bring_to_front_for_automation(reason="created_page")
        logger.info(
            "[AIO Browser:%s] created new page in remote context",
            self.session_name,
        )

    async def sync_to_existing_target_page(self, target_url: str | None = None) -> bool:
        """Point this client at the live remote page the user actually used.

        During human takeover the user can switch remote browser tabs directly
        inside the cloud computer. The handler's cached ``self.page`` can then
        be stale even though the correct platform page is already logged in.
        """

        try:
            if self.browser is None:
                await self._ensure_playwright()
                browser_info = await self._ensure_remote_runtime()
                cdp_url = browser_info.get("cdp_url")
                if not cdp_url or self.playwright is None:
                    return False
                self.browser = await self.playwright.chromium.connect_over_cdp(cdp_url)

            if self.browser is None:
                return False

            target_host = self._normalize_host(target_url)
            contexts = list(getattr(self.browser, "contexts", []) or [])
            for context in reversed(contexts):
                pages = [
                    page
                    for page in list(getattr(context, "pages", []) or [])
                    if not page.is_closed()
                ]
                for page in reversed(pages):
                    page_url = page.url or ""
                    if not page_url or page_url == "about:blank":
                        continue
                    page_host = self._normalize_host(page_url)
                    if target_host and page_host != target_host:
                        continue
                    self.context = context
                    self.page = page
                    self._context_owned_by_client = False
                    self._page_owned_by_client = False
                    foreground = await self.bring_to_front_for_automation(
                        reason="sync_live_page"
                    )
                    logger.info(
                        "[AIO Browser:%s] synced to live target page url=%s automation_foreground=%s",
                        self.session_name,
                        page_url,
                        bool(foreground.get("success")),
                    )
                    return True
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] Failed to sync live target page: %s",
                self.session_name,
                exc,
            )
        return False

    async def _apply_storage_state_to_current_page(self, url: str) -> None:
        if self.context is None or self.page is None:
            return

        storage_state = await self._load_storage_state()
        if not storage_state:
            return

        cookies = storage_state.get("cookies")
        if (
            not self._storage_state_loaded_into_context
            and isinstance(cookies, list)
            and cookies
        ):
            try:
                await self.context.add_cookies(cookies)
            except Exception as exc:
                logger.warning(
                    "[AIO Browser:%s] Failed to restore cookies: %s",
                    self.session_name,
                    exc,
                )

        parsed_url = urlparse(url)
        target_origin = f"{parsed_url.scheme}://{parsed_url.netloc}".rstrip("/")
        origin_payload = None
        for candidate in storage_state.get("origins", []) or []:
            if not isinstance(candidate, dict):
                continue
            origin = str(candidate.get("origin") or "").rstrip("/")
            if origin == target_origin:
                origin_payload = candidate
                break

        if origin_payload is None:
            return

        local_storage = origin_payload.get("localStorage")
        if not isinstance(local_storage, list) or not local_storage:
            return

        try:
            await self.page.goto(
                target_origin, wait_until="domcontentloaded", timeout=30000
            )
            await self.page.evaluate(
                """(items) => {
                    for (const item of items) {
                        if (!item || typeof item.name !== "string") continue;
                        localStorage.setItem(item.name, String(item.value ?? ""));
                    }
                }""",
                local_storage,
            )
        except Exception as exc:
            logger.warning(
                "[AIO Browser:%s] Failed to restore localStorage for %s: %s",
                self.session_name,
                target_origin,
                exc,
            )

    async def open(self, url: str, headed: bool = False) -> dict[str, Any]:
        """Attach to AIO browser via CDP and navigate the client-owned page."""

        del headed  # AIO browser UI mode is controlled out-of-band via takeover.

        last_error = ""

        for attempt in range(2):
            try:
                await self._ensure_playwright()
                browser_info = await self._ensure_remote_runtime()
                cdp_url = browser_info.get("cdp_url")
                if not cdp_url:
                    raise RuntimeError("AIO runtime 未返回可用 cdp_url")

                if self.browser is None and self.playwright is not None:
                    self.browser = await self.playwright.chromium.connect_over_cdp(
                        cdp_url
                    )
                    logger.info(
                        "[AIO Browser:%s] Connected over CDP (session=%s)",
                        self.session_name,
                        self.aio_session_id,
                    )

                if self.browser is not None and (
                    self.context is None
                    or self.page is None
                    or not self._page_matches_target_host(
                        getattr(self.page, "url", None), url
                    )
                ):
                    self.context = await self._get_or_create_remote_context(url)

                if self.page is not None and self.page.is_closed():
                    self.page = None

                if self.page is None or not self._page_matches_target_host(
                    getattr(self.page, "url", None), url
                ):
                    await self._get_or_create_remote_page(url)

                await self._apply_storage_state_to_current_page(url)
                logger.info(
                    "[AIO Browser:%s] navigating page from %s to %s",
                    self.session_name,
                    getattr(self.page, "url", None),
                    url,
                )
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                foreground = await self.bring_to_front_for_automation(
                    reason="open_complete"
                )
                logger.info(
                    "[AIO Browser:%s] navigation complete current_url=%s automation_foreground=%s",
                    self.session_name,
                    self.page.url,
                    bool(foreground.get("success")),
                )
                return {"success": True, "url": url}
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}" if str(e) else type(e).__name__
                logger.error(
                    "[AIO Browser:%s] open() failed (attempt %d): %s",
                    self.session_name,
                    attempt + 1,
                    last_error,
                )
                await self._reset_runtime(preserve_remote_surface=True)
                if attempt == 0:
                    continue
                return {"success": False, "error": last_error}

        return {"success": False, "error": last_error or "未知 AIO 浏览器错误"}

    async def bring_to_front(self) -> dict[str, Any]:
        """Best-effort focus inside the remote browser context."""

        try:
            if self.page is None:
                return {"error": "Page not opened"}
            await self.page.bring_to_front()
            return {"success": True}
        except Exception as e:
            logger.debug(
                "[AIO Browser:%s] bring_to_front failed: %s", self.session_name, e
            )
            return {"error": str(e)}

    async def bring_to_front_for_automation(
        self,
        *,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Focus only for automation paths that use GUI/VNC actions."""

        if not self.should_request_automation_foreground():
            logger.debug(
                "[AIO Browser:%s] skip automation foreground platform=%s reason=%s",
                self.session_name,
                self.platform,
                reason or "",
            )
            return {"skipped": True, "reason": "cdp_dom_platform"}

        foreground_key = self.foreground_key or build_aio_foreground_key(
            settings.AIO_BASE_URL
        )
        owner = f"{self.task_id}:{self.platform}:{reason or 'automation_foreground'}"
        try:
            async with aio_foreground_lease_manager.hold(
                key=foreground_key,
                mode="gui_automation",
                platform=self.platform,
                owner=owner,
                reason=reason or "automation_foreground",
                ttl_seconds=settings.AIO_FOREGROUND_GUI_LEASE_TTL_SECONDS,
                timeout_seconds=settings.AIO_FOREGROUND_GUI_LEASE_WAIT_SECONDS,
            ):
                return await self.bring_to_front()
        except AioForegroundLeaseTimeout as exc:
            logger.warning(
                "[AIO Browser:%s] automation foreground blocked platform=%s "
                "reason=%s error=%s",
                self.session_name,
                self.platform,
                reason or "",
                exc,
            )
            return {"error": str(exc), "lease_timeout": True}

    async def close(self) -> dict[str, Any]:
        """Disconnect from remote browser and release the leased session holder."""

        reset_error: Exception | None = None
        release_error: Exception | None = None
        session_id = self.aio_session_id
        try:
            await self._reset_runtime(preserve_remote_surface=False)
        except Exception as exc:
            reset_error = exc
        finally:
            if session_id is not None:
                try:
                    await aio_session_manager.release_session(
                        session_id,
                        task_id=self.task_id,
                        purpose=f"{self.purpose}:{self.platform}",
                    )
                except Exception as exc:
                    release_error = exc
            self.aio_session_id = None

        if reset_error is not None or release_error is not None:
            errors = []
            if reset_error is not None:
                errors.append(f"runtime reset failed: {reset_error}")
            if release_error is not None:
                errors.append(f"session release failed: {release_error}")
            return {"error": "; ".join(errors)}
        return {"success": True}
