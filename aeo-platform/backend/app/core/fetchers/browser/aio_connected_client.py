"""Playwright-compatible browser client backed by an AIO CDP endpoint."""

from __future__ import annotations

import json
import logging
from typing import Any
from urllib.parse import urlparse

from patchright.async_api import Browser, BrowserContext

from app.core.config import settings
from app.core.fetchers.browser.playwright_client import PlaywrightBrowserClient
from app.services.aio_runtime_contracts import AioPlatformRoots
from app.services.aio_session_manager import aio_session_manager

logger = logging.getLogger(__name__)


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
        self.platform_roots: AioPlatformRoots | None = None
        self._page_owned_by_client = False
        self._context_owned_by_client = False
        self._storage_state_loaded_into_context = False

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

    async def _ensure_playwright(self):
        """Ensure Patchright is initialized for CDP attachment."""

        if self.playwright is None:
            self.playwright = await self._start_playwright()

    async def _start_playwright(self):
        # Reuse the parent helper via open-coded import path because the parent
        # method also installs browsers if missing.
        return await super()._ensure_playwright() or self.playwright

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
        self.platform_roots = await aio_session_manager.ensure_platform_roots(
            session_id=session.session_id,
            task_id=self.task_id,
            platform=self.platform,
            workspace_id=self.workspace_id,
            auth_scope_id=self.auth_scope_id,
            run_scope_id=self.run_scope_id,
        )
        return await aio_session_manager.get_browser_connection(session.session_id)

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
        try:
            await context.add_init_script(
                """
(() => {
  const language = 'zh-CN';
  const languages = ['zh-CN', 'zh', 'en'];
  try {
    Object.defineProperty(navigator, 'language', {
      configurable: true,
      get: () => language,
    });
    Object.defineProperty(navigator, 'languages', {
      configurable: true,
      get: () => languages,
    });
  } catch (_) {
    // Ignore init-script failures; locale/header settings still apply.
  }
})();
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
                        return candidate

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
            return reusable_contexts[0]
        logger.info(
            "[AIO Browser:%s] creating isolated context for workspace=%s task=%s platform=%s",
            self.session_name,
            self.workspace_id,
            self.task_id,
            self.platform,
        )
        self._context_owned_by_client = True
        context_options: dict[str, Any] = {
            "viewport": {"width": 1280, "height": 720},
            "locale": settings.AIO_BROWSER_LOCALE,
            "timezone_id": settings.AIO_BROWSER_TIMEZONE_ID,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "extra_http_headers": {
                "Accept-Language": settings.AIO_BROWSER_ACCEPT_LANGUAGE,
            },
        }
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
                    logger.info(
                        "[AIO Browser:%s] reusing existing page url=%s target_host=%s",
                        self.session_name,
                        self.page.url,
                        target_host,
                    )
                    return

                self.page = await self.context.new_page()
                self._page_owned_by_client = True
                logger.info(
                    "[AIO Browser:%s] created new page because no existing page matched target_host=%s",
                    self.session_name,
                    target_host,
                )
                return

            self.page = usable[0] if usable else existing_pages[0]
            self._page_owned_by_client = False
            logger.info(
                "[AIO Browser:%s] reusing existing page url=%s target_host=%s",
                self.session_name,
                self.page.url,
                "<none>",
            )
            return

        self.page = await self.context.new_page()
        self._page_owned_by_client = True
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
                    logger.info(
                        "[AIO Browser:%s] synced to live target page url=%s",
                        self.session_name,
                        page_url,
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
                logger.info(
                    "[AIO Browser:%s] navigation complete current_url=%s",
                    self.session_name,
                    self.page.url,
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

    async def close(self) -> dict[str, Any]:
        """Disconnect from remote browser and release the leased session holder."""

        try:
            await self._reset_runtime(preserve_remote_surface=False)
            if self.aio_session_id is not None:
                await aio_session_manager.release_session(
                    self.aio_session_id,
                    task_id=self.task_id,
                    purpose=f"{self.purpose}:{self.platform}",
                )
            return {"success": True}
        except Exception as e:
            return {"error": str(e)}
