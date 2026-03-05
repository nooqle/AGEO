"""SSE (Server-Sent Events) response parser.

Parses text/event-stream responses from DeepSeek, Doubao, and Yuanbao.
Each platform has a dedicated parser class since the SSE payload formats
differ significantly.
"""

import json
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

from app.core.fetchers.browser.parsers.base import BaseResponseParser, ParsedResponse
from app.schemas.fetch import SearchReference

logger = logging.getLogger(__name__)


def _iter_sse_events(body: str):
    """Yield (event_type, data_dict) tuples from SSE body.

    event_type is "" for default events, or the value from the preceding
    'event:' line (e.g. "STREAM_ERROR", "SSE_HEARTBEAT").
    This preserves error/rate_limit events that were previously invisible.
    """
    current_event = ""
    for line in body.split("\n"):
        line = line.strip()
        if not line:
            current_event = ""  # blank line resets SSE event type
            continue
        if line.startswith("event:"):
            current_event = line[6:].strip()
            continue
        if line.startswith("id:"):
            continue
        if line.startswith("data:"):
            payload = line[5:].strip()
            if not payload or payload == "{}":
                continue
            try:
                yield current_event, json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                continue


def _iter_sse_data(body: str):
    """Yield parsed JSON objects from SSE data: lines (legacy compat).

    Wraps _iter_sse_events, discarding event type.
    """
    for _event_type, data in _iter_sse_events(body):
        yield data


def _domain_from_url(url: str) -> str:
    """Extract clean domain from URL for use as fallback title."""
    try:
        host = urlparse(url).hostname or url[:60]
        return host.removeprefix("www.")
    except Exception:
        return url[:60]


# ------------------------------------------------------------------ DeepSeek


class DeepSeekSSEParser(BaseResponseParser):
    """Parse DeepSeek's SSE stream from /api/v0/chat/completion.

    Format: JSON Patch-like operations.
    - Full response object in first data event (no "p" key)
    - Patches with "p" (path), "v" (value), "o" (operation: "APPEND")
    - References in fragments[].results[] (SEARCH fragment)
    - Text content via APPEND on fragments (TEXT fragment content)
    """

    def parse(self, body: str, url: str = "") -> ParsedResponse:
        text_parts: list[str] = []
        references: list[SearchReference] = []
        seen_urls: set[str] = set()
        error_info = ""
        error_type = ""

        for event_type, data in _iter_sse_events(body):
            # Detect error events (uses base class classify_error)
            err_info, err_type = self.classify_error(event_type, data)
            if err_type:
                error_info, error_type = err_info, err_type
                logger.warning("[DeepSeekSSE] Error event: %s", error_info)
                continue

            path = data.get("p", "")
            op = data.get("o", "")
            val = data.get("v")

            # --- Extract references ---
            if not path and isinstance(val, dict):
                resp = val.get("response", {})
                for frag in resp.get("fragments", []):
                    for result in frag.get("results", []):
                        self._add_ref(result, references, seen_urls)

            if path.endswith("/results") and isinstance(val, list):
                for result in val:
                    if isinstance(result, dict) and result.get("url"):
                        self._add_ref(result, references, seen_urls)

            # --- Extract text content ---
            if "content" in path and isinstance(val, str):
                text_parts.append(val)

            if op == "APPEND" and isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        content = item.get("content")
                        if isinstance(content, str) and content:
                            text_parts.append(content)

        result = ParsedResponse(
            answer_text="".join(text_parts),
            references=references,
            raw_body=body[:2000],
            error=error_info,
            error_type=error_type,
        )
        return self.validate(result)

    def _add_ref(
        self,
        item: dict,
        refs: list[SearchReference],
        seen: set[str],
    ) -> None:
        url = item.get("url", "")
        if not url or url in seen:
            return
        seen.add(url)
        refs.append(SearchReference(
            index=item.get("cite_index", len(refs) + 1),
            title=item.get("title") or _domain_from_url(url),
            url=url,
            snippet=item.get("snippet"),
            site_name=item.get("site_name"),
            is_official=False,
        ))


# ------------------------------------------------------------------ Yuanbao


class YuanbaoSSEParser(BaseResponseParser):
    """Parse Yuanbao's SSE stream from /api/chat/{id}.

    Format: JSON objects with "type" field.
    - type: "text" (no msg)  — marker event, ignored
    - type: "text" (with msg) — answer token delta (concatenate all)
    - type: "step"           — status messages ("正在搜索资料"), ignored
    - type: "searchGuid"     — contains docs[] with references
    - type: "replace"        — media/UI replacement (not answer text), ignored
    - type: "meta"           — metadata, ignored
    - type: "hint_v2_tip"    — UI hints, ignored

    Answer tokens arrive as "text" events with a "msg" field containing
    short text fragments (1-3 chars each).  Concatenate all to get the
    complete answer.
    """

    def parse(self, body: str, url: str = "") -> ParsedResponse:
        text_parts: list[str] = []
        references: list[SearchReference] = []
        seen_urls: set[str] = set()
        seen_types: set[str] = set()
        error_info = ""
        error_type = ""

        for event_type, data in _iter_sse_events(body):
            # Detect error events (uses base class classify_error)
            err_info, err_type = self.classify_error(event_type, data)
            if err_type:
                error_info, error_type = err_info, err_type
                logger.warning("[YuanbaoSSE] Error event: %s", error_info)
                continue

            msg_type = data.get("type", "")
            seen_types.add(msg_type or "(empty)")

            # Check for error in data-level type field
            if msg_type in ("error", "ERROR"):
                error_info = f"data_error: {data}"
                error_type = "server_error"
                logger.warning("[YuanbaoSSE] Data-level error: %s", data)
                continue

            # References from searchGuid events
            if msg_type == "searchGuid":
                for doc in data.get("docs", []):
                    doc_url = doc.get("url", "")
                    if doc_url and doc_url not in seen_urls:
                        seen_urls.add(doc_url)
                        references.append(SearchReference(
                            index=doc.get("index", len(references) + 1),
                            title=doc.get("title") or _domain_from_url(doc_url),
                            url=doc_url,
                            snippet=doc.get("quote"),
                            site_name=doc.get("web_site_name"),
                            is_official=False,
                        ))
                continue

            # Answer text from "text" events with "msg" field (delta tokens)
            if msg_type == "text" and "msg" in data:
                msg = data["msg"]
                if isinstance(msg, str) and msg:
                    text_parts.append(msg)

        if seen_types:
            logger.debug("[YuanbaoSSE] Event types seen: %s", seen_types)

        result = ParsedResponse(
            answer_text="".join(text_parts),
            references=references,
            raw_body=body[:2000],
            error=error_info,
            error_type=error_type,
        )
        return self.validate(result)


# ------------------------------------------------------------------ Doubao


class DoubaoSSEParser(BaseResponseParser):
    """Parse Doubao's SSE stream from /chat/completion.

    Format: SSE with event types (SSE_HEARTBEAT, SSE_ACK, STREAM_MSG_NOTIFY, etc.)

    IMPORTANT: Doubao double-serializes JSON — the ``content``, ``message``,
    and ``patch_op`` fields are JSON **strings**, not objects.  Each must be
    decoded with ``json.loads()`` before accessing nested structures.

    After decoding:
    - content_block[] arrays contain the actual payload
    - block_type 10000 = text block (text_block.text)
    - block_type 10101 = loading block (skip)
    - patch_op[] arrays carry incremental updates (CHUNK_DELTA events)
    """

    def classify_error(self, event_type: str, data: dict) -> tuple[str, str]:
        """Doubao-specific error classification with rate_limit/verify detection."""
        if event_type not in self.ERROR_EVENT_TYPES:
            return "", ""
        error_code = data.get("error_code", "")
        error_msg = data.get("error_message", "") or data.get("msg", "")
        err_type_field = data.get("type", "")
        error_info = f"{event_type}: code={error_code} msg={error_msg}"
        if "rate_limit" in str(error_code) or "rate_limit" in error_msg.lower() or error_code == 710022004:
            return error_info, "rate_limit"
        if err_type_field == "verify" or "verify" in error_msg.lower():
            return error_info, "verify"
        return error_info, "server_error"

    def parse(self, body: str, url: str = "") -> ParsedResponse:
        # Primary: CHUNK_DELTA text tokens — the AI's streaming answer
        delta_parts: list[str] = []
        # Fallback: content_block text (from STREAM_MSG_NOTIFY, etc.)
        block_parts: list[str] = []
        references: list[SearchReference] = []
        seen_urls: set[str] = set()
        seen_block_ids: set[str] = set()
        error_info = ""
        error_type = ""

        for event_type, data in _iter_sse_events(body):
            # Detect error events (uses Doubao-specific classify_error override)
            err_info, err_type = self.classify_error(event_type, data)
            if err_type:
                error_info, error_type = err_info, err_type
                logger.warning("[DoubaoSSE] Error event: %s (type=%s)", error_info, error_type)
                continue

            # CHUNK_DELTA events: simple {"text": "..."} tokens
            chunk_text = data.get("text")
            if isinstance(chunk_text, str) and chunk_text:
                delta_parts.append(chunk_text)
                continue

            # STREAM_CHUNK / STREAM_MSG_NOTIFY: structured content_block
            for blocks in self._extract_block_lists(data):
                self._process_blocks(
                    blocks, block_parts, references,
                    seen_urls, seen_block_ids,
                )

        # Prefer CHUNK_DELTA text (AI answer); fall back to block text
        answer = "".join(delta_parts) if delta_parts else "".join(block_parts)

        result = ParsedResponse(
            answer_text=answer,
            references=references,
            raw_body=body[:2000],
            error=error_info,
            error_type=error_type,
        )
        return self.validate(result)

    # -- internal helpers --------------------------------------------------

    @staticmethod
    def _try_parse_json(value) -> object:
        """Decode a JSON string; return as-is if already decoded or not a string."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, ValueError):
                return value
        return value

    def _extract_block_lists(self, data: dict):
        """Yield content_block lists from all known locations in a data event.

        Doubao sends blocks in three places (all double-encoded):
        1. data.content  → {"content_block": [...]}
        2. data.message  → {"content": "[{...}]"}  (triple-encoded content)
        3. data.patch_op → [{"patch_value": {"content_block": [...]}}]
        """
        # Path 1: STREAM_MSG_NOTIFY — data.content is a JSON string
        raw_content = data.get("content")
        if raw_content is not None:
            content_obj = self._try_parse_json(raw_content)
            if isinstance(content_obj, dict):
                blocks = content_obj.get("content_block", [])
                if isinstance(blocks, list) and blocks:
                    yield blocks

        # Path 2: FULL_MSG_NOTIFY — data.message is a JSON string
        #   whose "content" field is ALSO a JSON string (triple-encoded)
        raw_message = data.get("message")
        if raw_message is not None:
            msg_obj = self._try_parse_json(raw_message)
            if isinstance(msg_obj, dict):
                inner_content = self._try_parse_json(msg_obj.get("content"))
                if isinstance(inner_content, list):
                    yield inner_content
                elif isinstance(inner_content, dict):
                    blocks = inner_content.get("content_block", [])
                    if isinstance(blocks, list) and blocks:
                        yield blocks

        # Path 3: CHUNK_DELTA — data.patch_op is a JSON string (array)
        raw_patch = data.get("patch_op")
        if raw_patch is not None:
            patch_list = self._try_parse_json(raw_patch)
            if isinstance(patch_list, list):
                for patch in patch_list:
                    if not isinstance(patch, dict):
                        continue
                    pv = patch.get("patch_value", {})
                    if isinstance(pv, dict):
                        blocks = pv.get("content_block", [])
                        if isinstance(blocks, list) and blocks:
                            yield blocks

    def _process_blocks(
        self,
        blocks: list,
        text_parts: list[str],
        references: list[SearchReference],
        seen_urls: set[str],
        seen_block_ids: set[str],
    ) -> None:
        """Extract text and references from a content_block list."""
        for block in blocks:
            if not isinstance(block, dict):
                continue

            block_type = block.get("block_type", 0)
            block_id = block.get("block_id", "")
            block_content = block.get("content", {})
            if isinstance(block_content, str):
                block_content = self._try_parse_json(block_content)
            if not isinstance(block_content, dict):
                continue

            # Text block (type 10000)
            if block_type == 10000:
                text_block = block_content.get("text_block", {})
                if isinstance(text_block, dict):
                    text = text_block.get("text", "")
                    if text and block_id not in seen_block_ids:
                        seen_block_ids.add(block_id)
                        text_parts.append(text)

            # Reference/search blocks — two known formats
            # Format 1: search_block.results[] (legacy)
            search_block = block_content.get("search_block", {})
            if isinstance(search_block, dict):
                for item in search_block.get("results", []):
                    item_url = item.get("url", "")
                    if item_url and item_url not in seen_urls:
                        seen_urls.add(item_url)
                        references.append(SearchReference(
                            index=len(references) + 1,
                            title=item.get("title") or _domain_from_url(item_url),
                            url=item_url,
                            snippet=item.get("snippet"),
                            site_name=item.get("site_name"),
                            is_official=False,
                        ))

            # Format 2: search_query_result_block (block_type 10025, 2026-03 confirmed)
            # results[].text_card.{url, title, sitename, summary}
            if block_type == 10025:
                sqrb = block_content.get("search_query_result_block", {})
                if isinstance(sqrb, dict):
                    for item in sqrb.get("results", []):
                        card = item.get("text_card", {}) if isinstance(item, dict) else {}
                        card_url = card.get("url", "")
                        if card_url and card_url not in seen_urls:
                            seen_urls.add(card_url)
                            references.append(SearchReference(
                                index=len(references) + 1,
                                title=card.get("title") or _domain_from_url(card_url),
                                url=card_url,
                                snippet=card.get("summary"),
                                site_name=card.get("sitename"),
                                is_official=False,
                            ))
