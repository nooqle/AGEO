"""DeepSeek browser handler.

NOTE: All eval() calls in this module are Playwright's page.evaluate() API,
which executes JavaScript in the browser context for DOM interaction.
This is the standard Playwright pattern, not Python's built-in eval().
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator

from app.core.config import settings
from app.core.fetchers.browser.base_handler import BaseBrowserHandler
from app.core.fetchers.browser.browser_executor import (
    BrowserAnswerExecutionPlan,
    execute_post_submit_capture_flow,
)
from app.core.fetchers.browser.failure_observability import build_failure_contract
from app.core.fetchers.browser.parsers.base import BaseResponseParser
from app.core.fetchers.browser.parsers.sse import DeepSeekSSEParser
from app.schemas.fetch import (
    BrowserEvent,
    BrowserState,
    Platform,
    SearchReference,
)

logger = logging.getLogger(__name__)


class DeepSeekHandler(BaseBrowserHandler):
    """DeepSeek browser-based handler.

    Uses Playwright to interact with DeepSeek Web UI.
    """

    URL = "https://chat.deepseek.com/"
    PLATFORM = Platform.DEEPSEEK
    PLATFORM_KEY = "deepseek"
    BROWSER_READY_URL_PATTERNS = ("chat.deepseek.com",)
    BROWSER_LOGIN_URL_PATTERNS = ("sign_in", "login", "auth")
    BROWSER_READY_HINTS = ("联网搜索", "new chat", "textarea")
    BROWSER_LOGIN_HINTS = (
        "scan with wechat to login",
        "send code",
        "phone number",
        "verification code",
        "二维码",
        "手机号",
    )
    BROWSER_LATE_BLOCKER_HINTS = (
        "scan with wechat to login",
        "verification",
        "人机验证",
        "安全验证",
    )
    RISK_CONTROL_MARKERS = (
        "请检查网络后重试",
        "浏览器运行环境异常",
        "当前浏览器运行环境异常",
        "运行环境",
        "switch execution environments and try again",
    )
    PAGE_RUNTIME_RISK_FAILURE_REASON = "page_runtime_retry_or_risk_control"

    _DEFAULTS: dict = {
        "input": "textarea",
        "input_ready": "textarea, [contenteditable='true']",
        "answer": "div.ds-markdown",
        "reference_links": [
            "[class*='reference'] a[href^='http']",
            ".search-result a[href^='http']",
        ],
        "citation_strip": "[class*='cite'], [class*='citation'], [class*='ref-num'], sup, a.ds-markdown-cite, a[data-index]",
        "new_chat_text": "新对话",
        "web_search_texts": ["联网搜索", "联网"],
        "reference_expand_texts": ["引用", "来源", "References", "Sources"],
    }

    def _resolve_interaction_mode(self) -> str:
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

    def _should_use_aio_gui_actions(self) -> bool:
        return (
            self._resolve_interaction_mode() == "gui_actions"
            and bool(getattr(self.client, "aio_session_id", None))
        )

    def _interaction_metadata(self) -> dict[str, Any]:
        configured_mode = self._resolve_interaction_mode()
        return {
            "interaction_mode": (
                "gui_actions" if self._should_use_aio_gui_actions() else "cdp_dom"
            ),
            "configured_interaction_mode": configured_mode,
            "aio_gui_actions_available": bool(
                getattr(self.client, "aio_session_id", None)
            ),
        }

    def _build_runtime_diagnostics_metadata(self) -> dict[str, Any]:
        metadata = super()._build_runtime_diagnostics_metadata()
        metadata.update(self._interaction_metadata())
        return metadata

    def _get_response_parser(self) -> BaseResponseParser | None:
        return DeepSeekSSEParser()

    # DeepSeek uses a single selector for answer, override content_check_js
    def _content_check_js(self) -> str:
        """DeepSeek uses single 'answer' selector (div.ds-markdown)."""
        answer_sel = json.dumps(self._sel("answer"), ensure_ascii=False)
        return f"""() => {{
            const msgs = document.querySelectorAll({answer_sel});
            const last = msgs[msgs.length - 1];
            return last ? String(last.textContent.length) : '0';
        }}"""

    async def fetch(self, question: str) -> AsyncGenerator:
        """Fetch answer from DeepSeek Web."""
        self._refresh_selectors()
        try:
            # Step 1: Initializing
            yield self._create_event(BrowserState.INITIALIZING, "初始化浏览器...", progress=0.1)

            # Step 2: Navigate or start new chat
            yield self._create_event(BrowserState.NAVIGATING, f"正在访问 {self.URL}...", progress=0.2)
            page = self.client.page
            fast_path_ok = False
            if page is not None and "chat.deepseek.com" in (page.url or ""):
                try:
                    new_chat_text = self._sel("new_chat_text")
                    new_chat = page.get_by_text(new_chat_text, exact=False).first
                    if await new_chat.count() > 0:
                        old_url = page.url
                        await new_chat.click()
                        # Verify URL change instead of blind sleep
                        for _ in range(4):
                            await asyncio.sleep(0.5)
                            if page.url != old_url:
                                break
                        fast_path_ok = True
                        logger.info("[DeepSeek] Fast path: clicked %s (url_changed=%s)", new_chat_text, page.url != old_url)
                except Exception as e:
                    logger.debug("[DeepSeek] %s click failed (%s), falling back to navigate",
                                 self._sel("new_chat_text"), e)

            if not fast_path_ok and await self._reuse_existing_aio_surface(self.URL):
                fast_path_ok = True

            if not fast_path_ok:
                open_result = await self.client.open(self.URL, headed=False)
                if not open_result.get("success"):
                    yield self._create_event(
                        BrowserState.ERROR,
                        f"浏览器打开失败: {open_result.get('error', '未知错误')}",
                        progress=0,
                    )
                    return
                await asyncio.sleep(3)

            if self.client.page:
                logger.info("[DeepSeek] Page URL: %s", self.client.page.url)

            preflight_events, should_abort = await self._run_browser_agent_preflight(
                progress=0.28,
                url=self.URL,
            )
            for event in preflight_events:
                yield event
            if should_abort:
                return

            # Step 3: Ensure web search is ON
            yield self._create_event(BrowserState.ENABLING_SEARCH, "确认联网搜索已开启...", progress=0.5)
            if self.client.page is not None:
                if self._should_use_aio_gui_actions():
                    await self._ensure_web_search_on_via_aio_gui_actions()
                else:
                    await self._ensure_web_search_on()

            # Step 5: Start network interception (before submit)
            yield self._create_event(BrowserState.SUBMITTING, f"提交问题: {question[:30]}...", progress=0.6)
            intercept_config = self._get_intercept_config()
            parser = self._get_response_parser()
            intercept_task = None
            if intercept_config and parser and self.client.page:
                intercept_task = asyncio.create_task(
                    self._intercept_and_wait(intercept_config, parser)
                )

            # Step 5b: Submit question
            submitted = False
            baseline_probe = await self._capture_submission_probe()
            using_gui_actions = self._should_use_aio_gui_actions()
            if using_gui_actions:
                submitted = await self._submit_question_via_aio_gui_actions(
                    question,
                    baseline_probe,
                )
            elif self.client.page is not None:
                try:
                    editor = self.client.page.locator(self._sel("input")).last
                    if await editor.count() > 0:
                        await editor.click()
                        await asyncio.sleep(0.2)
                        await editor.fill(question)
                        await asyncio.sleep(0.2)
                        await editor.press("Enter")
                        submitted = await self._submission_looks_started(
                            baseline_probe, question
                        )
                        logger.info(
                            "[DeepSeek] Question submitted via locator Enter (confirmed=%s)",
                            submitted,
                        )
                except Exception as e:
                    logger.debug("[DeepSeek] Direct locator submit failed: %s", e)

            if not submitted and not using_gui_actions:
                snapshot = await self.client.snapshot(interactive_only=True)
                textarea_ref = self._find_textarea_ref(snapshot)
                if textarea_ref:
                    await self.client.fill(textarea_ref, question)
                    await asyncio.sleep(0.3)
                    await self.client.press("Enter")
                    submitted = await self._submission_looks_started(
                        baseline_probe, question
                    )
                    logger.info(
                        "[DeepSeek] Question submitted via snapshot ref %s (confirmed=%s)",
                        textarea_ref,
                        submitted,
                    )

            if (
                not submitted
                and not using_gui_actions
                and await self._click_send_button_near_input()
            ):
                submitted = await self._submission_looks_started(
                    baseline_probe, question
                )
                logger.info(
                    "[DeepSeek] Question submitted via send-button fallback (confirmed=%s)",
                    submitted,
                )

            if not submitted:
                logger.warning(
                    "[DeepSeek] Submission could not be confirmed; skipping DOM wait for this question"
                )
                evidence_ref = await self._capture_failure_evidence(
                    failure_reason="submission_not_confirmed",
                    execution_stage="submit_question",
                    extra_metadata={
                        "answer_length": 0,
                        **self._interaction_metadata(),
                    },
                )
                yield self._create_event(
                    BrowserState.ERROR,
                    "提交后页面未进入回答状态，本题已跳过",
                    progress=0,
                    error_type="submission_not_confirmed",
                    **build_failure_contract(
                        failure_reason="submission_not_confirmed",
                        execution_stage="submit_question",
                        retryable=False,
                        needs_handoff=False,
                        failure_layer="adapter",
                        evidence_ref=evidence_ref,
                    ),
                )
                return

            yield self._create_event(BrowserState.WAITING_RESPONSE, "等待 AI 回复...", progress=0.7)
            fetch_result, events = await execute_post_submit_capture_flow(
                self,
                BrowserAnswerExecutionPlan(
                    question=question,
                    intercept_task=intercept_task,
                    fallback_url=self.URL,
                    max_wait=50,
                    poll_interval=3,
                    min_content_len=0,
                    stable_rounds=2,
                    blocker_check_after_seconds=9,
                    dump_keywords=["ds-"],
                    extract_references=self._extract_references,
                ),
            )
            for event in events:
                yield event
            if fetch_result is None:
                return

            yield self._create_event(BrowserState.COMPLETED, "抓取完成", progress=1.0, data=fetch_result)

        except Exception as e:
            yield self._create_event(BrowserState.ERROR, f"抓取失败: {str(e)}", progress=0)

    # ------------------------------------------------------------------ DeepSeek-specific

    async def _detect_risk_control_marker(self) -> tuple[str | None, str | None]:
        text_snapshot = await self._browser_agent_text_snapshot_provider()
        normalized_text = " ".join(str(text_snapshot or "").split())
        if not normalized_text:
            return None, None
        lower_text = normalized_text.lower()
        for marker in self.RISK_CONTROL_MARKERS:
            if marker.lower() in lower_text:
                return marker, normalized_text[:600]
        return None, None

    async def _handle_browser_agent_empty_answer(
        self,
        answer_text: str | None,
        *,
        progress: float,
        fallback_url: str | None = None,
    ) -> tuple[list[BrowserEvent], bool]:
        if answer_text and len(answer_text.strip()) >= 10:
            return [], False

        risk_control_marker, page_excerpt = await self._detect_risk_control_marker()
        if not risk_control_marker:
            return await super()._handle_browser_agent_empty_answer(
                answer_text,
                progress=progress,
                fallback_url=fallback_url,
            )

        evidence_ref = await self._capture_failure_evidence(
            failure_reason=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
            execution_stage="extract_answer",
            extra_metadata={
                "answer_length": len(answer_text or ""),
                "risk_control_marker": risk_control_marker,
                "page_excerpt": page_excerpt,
                **self._interaction_metadata(),
            },
        )
        return [
            self._create_event(
                BrowserState.ERROR,
                "DeepSeek 页面返回运行环境/重试提示，当前运行时未获得有效回答",
                progress=0,
                error_type=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
                **build_failure_contract(
                    failure_reason=self.PAGE_RUNTIME_RISK_FAILURE_REASON,
                    execution_stage="extract_answer",
                    retryable=False,
                    needs_handoff=False,
                    failure_layer="adapter",
                    evidence_ref=evidence_ref,
                ),
            )
        ], True

    async def _capture_submission_probe(self) -> dict[str, Any]:
        if self.client.page is None:
            return {"message_count": 0, "answer_count": 0, "input_len": 0}
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        probe = await self.client.page.evaluate(
            f"""() => {{
                const textarea = document.querySelector({input_sel});
                const readValue = textarea
                    ? String(textarea.value || textarea.textContent || '').trim()
                    : '';
                return {{
                    message_count: document.querySelectorAll('.ds-message').length,
                    answer_count: document.querySelectorAll('div.ds-markdown').length,
                    input_len: readValue.length,
                }};
            }}"""
        )
        return probe if isinstance(probe, dict) else {}

    async def _submission_looks_started(
        self,
        baseline_probe: dict[str, Any],
        question: str,
        *,
        timeout_seconds: float = 4.0,
    ) -> bool:
        if self.client.page is None:
            return False
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        question_prefix = json.dumps(question[:16], ensure_ascii=False)
        waited = 0.0
        while waited <= timeout_seconds:
            await asyncio.sleep(0.5)
            waited += 0.5
            probe = await self.client.page.evaluate(
                f"""() => {{
                    const textarea = document.querySelector({input_sel});
                    const readValue = textarea
                        ? String(textarea.value || textarea.textContent || '').trim()
                        : '';
                    const bodyText = String(document.body?.innerText || '');
                    return {{
                        message_count: document.querySelectorAll('.ds-message').length,
                        answer_count: document.querySelectorAll('div.ds-markdown').length,
                        input_len: readValue.length,
                        body_has_prefix: bodyText.includes({question_prefix}),
                    }};
                }}"""
            )
            if not isinstance(probe, dict):
                continue
            if int(probe.get("message_count") or 0) > int(
                baseline_probe.get("message_count") or 0
            ):
                return True
            if int(probe.get("answer_count") or 0) > int(
                baseline_probe.get("answer_count") or 0
            ):
                return True
        return False

    async def _click_send_button_near_input(self) -> bool:
        if self.client.page is None:
            return False
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        clicked = await self.client.page.evaluate(
            f"""() => {{
                const textarea = document.querySelector({input_sel});
                if (!textarea) return false;
                const interactive = [
                    "button",
                    "[role='button']",
                    "div[class*='icon-button']",
                ].join(", ");
                let container = textarea.parentElement;
                while (container && container !== document.body) {{
                    const candidates = Array.from(container.querySelectorAll(interactive));
                    const enabled = candidates.filter((el) => {{
                        const cls = String(el.className || '').toLowerCase();
                        const aria = String(el.getAttribute('aria-label') || '').toLowerCase();
                        const title = String(el.getAttribute('title') || '').toLowerCase();
                        const text = String(el.textContent || '').trim().toLowerCase();
                        const disabled = el.hasAttribute('disabled')
                            || el.getAttribute('aria-disabled') === 'true'
                            || cls.includes('disabled');
                        if (disabled) return false;
                        return (
                            aria.includes('send')
                            || aria.includes('发送')
                            || title.includes('send')
                            || title.includes('发送')
                            || text.includes('send')
                            || text.includes('发送')
                            || cls.includes('send')
                            || cls.includes('submit')
                            || cls.includes('icon-button')
                        );
                    }});
                    if (enabled.length > 0) {{
                        enabled[enabled.length - 1].click();
                        return true;
                    }}
                    container = container.parentElement;
                }}
                return false;
            }}"""
        )
        return bool(clicked)

    async def _execute_aio_gui_action(self, action_payload: dict[str, Any]) -> bool:
        try:
            result = await self._aio_backend.execute_action(
                action_payload=action_payload
            )
        except Exception as exc:
            logger.warning("[DeepSeek] AIO GUI action failed: %s", exc)
            return False

        detail = result.get("detail") if isinstance(result, dict) else None
        if isinstance(detail, dict) and detail.get("success") is False:
            logger.warning("[DeepSeek] AIO GUI action rejected: %s", detail)
            return False

        status = str(
            (result.get("status") if isinstance(result, dict) else "") or ""
        ).lower()
        if status in {"error", "failed", "failure"}:
            logger.warning("[DeepSeek] AIO GUI action returned status=%s", status)
            return False
        return True

    async def _aio_gui_click_rect(self, rect: dict[str, Any]) -> bool:
        try:
            x = int(round(float(rect["gui_x"])))
            y = int(round(float(rect["gui_y"])))
        except (KeyError, TypeError, ValueError):
            return False

        moved = await self._execute_aio_gui_action(
            {"action_type": "MOVE_TO", "x": x, "y": y}
        )
        clicked = await self._execute_aio_gui_action(
            {"action_type": "CLICK", "x": x, "y": y}
        )
        return moved and clicked

    async def _deepseek_input_rect_for_gui_actions(self) -> dict[str, Any] | None:
        if self.client.page is None:
            return None
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        result = await self.client.page.evaluate(
            f"""() => {{
                const elements = Array.from(document.querySelectorAll({input_sel}));
                const el = elements.reverse().find((candidate) => {{
                    const rect = candidate.getBoundingClientRect();
                    return rect.width > 20 && rect.height > 10;
                }});
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                const chromeOffsetX = Math.max(0, Math.round((window.outerWidth - window.innerWidth) / 2));
                const chromeOffsetY = Math.max(0, Math.round(window.outerHeight - window.innerHeight));
                return {{
                    page_x: rect.left + rect.width / 2,
                    page_y: rect.top + rect.height / 2,
                    gui_x: rect.left + rect.width / 2 + chromeOffsetX,
                    gui_y: rect.top + rect.height / 2 + chromeOffsetY,
                    width: rect.width,
                    height: rect.height,
                    chrome_offset_x: chromeOffsetX,
                    chrome_offset_y: chromeOffsetY,
                }};
            }}"""
        )
        return result if isinstance(result, dict) else None

    async def _submit_question_via_aio_gui_actions(
        self,
        question: str,
        baseline_probe: dict[str, Any],
    ) -> bool:
        rect = await self._deepseek_input_rect_for_gui_actions()
        if not rect:
            logger.warning("[DeepSeek] AIO GUI submit failed: input rect unavailable")
            return False

        if not await self._aio_gui_click_rect(rect):
            return False
        await asyncio.sleep(0.2)

        await self._execute_aio_gui_action(
            {"action_type": "HOTKEY", "keys": ["ctrl", "a"]}
        )
        await asyncio.sleep(0.1)
        typed = await self._execute_aio_gui_action(
            {
                "action_type": "TYPING",
                "text": question,
                "use_clipboard": True,
            }
        )
        if not typed:
            return False
        await asyncio.sleep(0.2)

        pressed = await self._execute_aio_gui_action(
            {"action_type": "PRESS", "key": "Enter"}
        )
        if not pressed:
            return False

        submitted = await self._submission_looks_started(baseline_probe, question)
        logger.info(
            "[DeepSeek] Question submitted via AIO GUI actions (confirmed=%s)",
            submitted,
        )
        return submitted

    async def _ensure_web_search_on_via_aio_gui_actions(self) -> None:
        if self.client.page is None:
            return
        try:
            input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
            info = await self.client.page.evaluate(
                f"""() => {{
                    const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                    const textarea = document.querySelector({input_sel});
                    const chromeOffsetX = Math.max(0, Math.round((window.outerWidth - window.innerWidth) / 2));
                    const chromeOffsetY = Math.max(0, Math.round(window.outerHeight - window.innerHeight));
                    const descEl = (el) => {{
                        const rect = el.getBoundingClientRect();
                        return {{
                            tag: el.tagName,
                            pressed: el.getAttribute('aria-pressed') || '',
                            checked: el.getAttribute('aria-checked') || '',
                            state: el.getAttribute('data-state') || '',
                            label: el.getAttribute('aria-label') || '',
                            title: el.getAttribute('title') || '',
                            cls: (el.className || '').slice(0, 80),
                            txt: (el.innerText || el.textContent || '').trim().slice(0, 40),
                            rect: {{
                                page_x: rect.left + rect.width / 2,
                                page_y: rect.top + rect.height / 2,
                                gui_x: rect.left + rect.width / 2 + chromeOffsetX,
                                gui_y: rect.top + rect.height / 2 + chromeOffsetY,
                                width: rect.width,
                                height: rect.height,
                                chrome_offset_x: chromeOffsetX,
                                chrome_offset_y: chromeOffsetY,
                            }},
                        }};
                    }};
                    let toolbarEls = null;
                    if (textarea) {{
                        let c = textarea.parentElement;
                        while (c && c !== document.body) {{
                            const els = Array.from(c.querySelectorAll(INTERACTIVE));
                            if (els.length >= 1 && els.length <= 8) {{
                                toolbarEls = els;
                                break;
                            }}
                            c = c.parentElement;
                        }}
                    }}
                    return {{
                        toolbarBtns: toolbarEls ? toolbarEls.map(descEl) : [],
                    }};
                }}"""
            )

            toolbar = info.get("toolbarBtns") if isinstance(info, dict) else []
            if not isinstance(toolbar, list) or not toolbar:
                logger.warning("[DeepSeek] AIO GUI search toggle: no toolbar found")
                return

            search_idx = self._find_web_search_index(toolbar)
            if search_idx is None or search_idx >= len(toolbar):
                logger.warning("[DeepSeek] AIO GUI search toggle not identified")
                return

            button = toolbar[search_idx]
            pressed = button.get("pressed", "")
            cls = button.get("cls", "")
            if pressed == "true" or "--selected" in cls:
                logger.info("[DeepSeek] Web search already ON via GUI probe")
                return

            rect = button.get("rect")
            if isinstance(rect, dict) and await self._aio_gui_click_rect(rect):
                logger.info("[DeepSeek] Enabled web search via AIO GUI actions")
                await asyncio.sleep(0.5)
        except Exception as exc:
            logger.warning(
                "[DeepSeek] _ensure_web_search_on_via_aio_gui_actions failed: %s",
                exc,
            )

    async def _ensure_web_search_on(self) -> None:
        """Ensure the web search toggle is ON in the input toolbar.

        DeepSeek renders toolbar toggles as pure SVG icon-buttons with no
        visible text or aria-label.
        """
        try:
            input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
            # Playwright page.evaluate() — runs JS in browser context
            info = await self.client.page.evaluate(f"""() => {{
                const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
                const textarea = document.querySelector({input_sel});
                let toolbarEls = null;
                let toolbarContainerCls = '';
                if (textarea) {{
                    let c = textarea.parentElement;
                    while (c && c !== document.body) {{
                        const els = Array.from(c.querySelectorAll(INTERACTIVE));
                        if (els.length >= 1 && els.length <= 8) {{
                            toolbarEls = els;
                            toolbarContainerCls = (c.className || '').slice(0, 80);
                            break;
                        }}
                        c = c.parentElement;
                    }}
                }}
                const descEl = el => ({{
                    tag: el.tagName,
                    pressed: el.getAttribute('aria-pressed') || '',
                    checked: el.getAttribute('aria-checked') || '',
                    state:   el.getAttribute('data-state')   || '',
                    label:   el.getAttribute('aria-label')   || '',
                    title:   el.getAttribute('title')        || '',
                    cls:    (el.className || '').slice(0, 80),
                    txt:    (el.innerText || el.textContent || '').trim().slice(0, 40),
                }});
                const allToggles = Array.from(
                    document.querySelectorAll('[aria-pressed], [aria-checked], [role="switch"]')
                ).map(descEl);
                return {{
                    toolbarBtns: toolbarEls ? toolbarEls.map(descEl) : null,
                    toolbarContainerCls,
                    allToggles,
                }};
            }}""")

            toolbar = info.get("toolbarBtns") or []
            all_toggles = info.get("allToggles") or []
            logger.info("[DeepSeek] Toolbar buttons (%d): %s | All toggles (%d): %s",
                        len(toolbar), toolbar, len(all_toggles), all_toggles)

            if not toolbar:
                if not all_toggles:
                    logger.warning("[DeepSeek] No toolbar or toggle elements found near textarea")
                await self._try_text_based_search_toggle()
                return

            search_idx = self._find_web_search_index(toolbar)
            if search_idx is None:
                logger.warning("[DeepSeek] Could not identify WebSearch toggle in toolbar")
                await self._try_text_based_search_toggle()
                return

            btn = toolbar[search_idx]
            pressed = btn.get("pressed", "")
            cls = btn.get("cls", "")

            if pressed == "true":
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], pressed=true)", search_idx)
                return
            if pressed == "false":
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (pressed false→true)", search_idx)
                return

            if "--selected" in cls:
                logger.info("[DeepSeek] Web search already ON (toolbar[%d], --selected)", search_idx)
            else:
                await self._click_toolbar_button(search_idx)
                logger.info("[DeepSeek] Enabled web search toolbar[%d] (was OFF)", search_idx)

        except Exception as e:
            logger.warning("[DeepSeek] _ensure_web_search_on failed: %s", e)

    def _browser_agent_stage_note(
        self,
        *,
        stage: str,
        action_type: str | None = None,
    ) -> str | None:
        note = super()._browser_agent_stage_note(stage=stage, action_type=action_type)
        if stage == "resume_probe" and action_type == "login":
            return (
                f"{note} DeepSeek 的就绪信号通常是已经进入聊天页，可见输入区和工具栏；"
                "如果仍停留在 sign_in/login 页面、手机号/验证码表单、二维码登录或安全验证页面，则不要放行。"
            )
        if stage == "wait_gate":
            return (
                f"{note} DeepSeek 可能在提交后转入登录页或验证页；如果 URL 或页面文案显示 sign_in/login/验证码，应及时识别为 blocker。"
            )
        return note

    def _find_web_search_index(self, toolbar: list[dict]) -> int | None:
        """Find the index of the WebSearch toggle button in the toolbar."""
        for i, btn in enumerate(toolbar):
            txt = btn.get("txt", "").lower()
            if "search" in txt or "联网" in txt:
                return i

        toggle_keywords = ("toggle", "switch", "ds-toggle")
        toggle_indices = []
        for i, btn in enumerate(toolbar):
            cls = btn.get("cls", "").lower()
            if any(kw in cls for kw in toggle_keywords):
                toggle_indices.append(i)

        if len(toggle_indices) >= 2:
            return toggle_indices[1]

        for i, btn in enumerate(toolbar):
            if btn.get("pressed") in ("true", "false"):
                txt = btn.get("txt", "").lower()
                if "think" in txt or "深度" in txt or "思考" in txt:
                    continue
                return i

        if toggle_indices:
            return toggle_indices[0]

        logger.warning("[DeepSeek] _find_web_search_index: no toggle found")
        return None

    async def _click_toolbar_button(self, index: int) -> None:
        """Click a toolbar button by index (re-locating from textarea)."""
        input_sel = json.dumps(self._sel("input"), ensure_ascii=False)
        # Playwright page.evaluate() — runs JS in browser context
        await self.client.page.evaluate(f"""() => {{
            const INTERACTIVE = 'button, [role="button"], [role="switch"], [aria-pressed], [aria-checked]';
            const textarea = document.querySelector({input_sel});
            let c = textarea && textarea.parentElement;
            while (c && c !== document.body) {{
                const els = Array.from(c.querySelectorAll(INTERACTIVE));
                if (els.length >= 1 && els.length <= 8) {{
                    els[{index}] && els[{index}].click();
                    return 'clicked';
                }}
                c = c.parentElement;
            }}
            return 'not found';
        }}""")
        await asyncio.sleep(0.5)

    async def _try_text_based_search_toggle(self) -> None:
        """Fallback: enable web search by clicking element containing '联网' text."""
        if not self.client.page:
            return
        try:
            web_search_texts = self._sel("web_search_texts")
            for text in web_search_texts:
                locator = self.client.page.get_by_text(text, exact=False).first
                if await locator.count() > 0:
                    await locator.click()
                    await asyncio.sleep(0.5)
                    logger.info("[DeepSeek] Enabled web search via text-based fallback ('%s')", text)
                    return
            logger.warning("[DeepSeek] Text-based search toggle fallback: no matching element found")
        except Exception as e:
            logger.warning("[DeepSeek] Text-based search toggle fallback failed: %s", e)

    async def _extract_references(self) -> list[SearchReference]:
        """Extract search references with DeepSeek-specific citation link extraction."""
        # Phase 1: DeepSeek-specific citation links
        refs = await self._extract_citation_links()
        if refs:
            logger.info("[DeepSeek] Extracted %d references via citation links", len(refs))
            return refs

        # Phase 2+3: Generic extraction from base
        return await self._extract_references_dom()

    async def _extract_citation_links(self) -> list[SearchReference]:
        """Extract citation links from the last answer with smart title resolution.

        DeepSeek renders inline citation markers as <a> tags whose textContent
        is just a number. This extracts the href and resolves a meaningful title.

        Uses Playwright's page.evaluate() — runs JS in browser context, not Python eval().
        """
        try:
            answer_sel = json.dumps(self._sel("answer"), ensure_ascii=False)
            result = await self.client.eval(f"""() => {{
                const messages = document.querySelectorAll({answer_sel});
                const lastMsg = messages[messages.length - 1];
                if (!lastMsg) return '[]';

                const links = Array.from(lastMsg.querySelectorAll('a[href^="http"]'));
                const seen = new Set();
                const refs = [];

                for (const a of links) {{
                    const url = a.href;
                    if (!url || seen.has(url)) continue;
                    seen.add(url);

                    let title = (a.getAttribute('title') || '').trim();
                    if (!title) title = (a.getAttribute('aria-label') || '').trim();
                    if (!title) title = (a.getAttribute('data-title') || '').trim();
                    if (!title) {{
                        const parent = a.closest('[class*="tooltip"], [class*="popup"], [class*="citation-content"]');
                        if (parent) {{
                            const pText = (parent.textContent || '').trim();
                            if (pText.length > 5) title = pText.slice(0, 200);
                        }}
                    }}
                    if (!title || /^[-\\d\\s.]+$/.test(title)) {{
                        try {{
                            title = new URL(url).hostname.replace(/^www\\./, '');
                        }} catch {{
                            title = url.slice(0, 60);
                        }}
                    }}

                    refs.push({{ index: refs.length + 1, title, url }});
                }}
                return JSON.stringify(refs);
            }}""")
            data = json.loads(result.get("output", "[]") or "[]")
            if not data:
                return []
            return [
                SearchReference(
                    index=item["index"],
                    title=item["title"],
                    url=item["url"],
                    snippet=None,
                    site_name=None,
                    is_official=False,
                )
                for item in data
                if item.get("url")
            ]
        except Exception as e:
            logger.debug("[DeepSeek] _extract_citation_links failed: %s", e)
            return []
