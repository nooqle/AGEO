"""Kimi Connect protocol response parser.

Kimi uses the Connect protocol (application/connect+json) with binary framing.
Each frame has a 5-byte header: 1 byte flag (0x00) + 4 bytes big-endian payload length.

JSON chunks use op/mask operations:
- op:"append", mask:"block.text.content" — text content (character-by-character)
- op:"append", mask:"block.search.webPages" — search references
- op:"set", mask:"message" — message metadata (skip)
- heartbeat — keep-alive (skip)
"""

import json
import logging
import struct
from urllib.parse import urlparse

from app.core.fetchers.browser.parsers.base import BaseResponseParser, ParsedResponse
from app.schemas.fetch import SearchReference

logger = logging.getLogger(__name__)


def _domain_from_url(url: str) -> str:
    """Extract domain from URL, stripping 'www.' prefix."""
    try:
        host = urlparse(url).hostname or url[:60]
        return host.removeprefix("www.")
    except Exception:
        return url[:60]


def decode_binary_frames(data: bytes) -> list[str]:
    """Decode Connect protocol binary frames into JSON strings.

    Each frame: 1 byte flag + 4 bytes big-endian length + payload.
    Returns a list of decoded JSON string payloads.
    """
    frames = []
    offset = 0
    while offset < len(data):
        if offset + 5 > len(data):
            break
        _flag = data[offset]
        length = struct.unpack(">I", data[offset + 1 : offset + 5])[0]
        offset += 5
        if offset + length > len(data):
            # Partial frame — try to use what we have
            payload = data[offset:]
            if payload:
                try:
                    frames.append(payload.decode("utf-8", errors="replace"))
                except Exception:
                    pass
            break
        payload = data[offset : offset + length]
        offset += length
        try:
            frames.append(payload.decode("utf-8"))
        except Exception:
            continue
    return frames


class KimiConnectParser(BaseResponseParser):
    """Parser for Kimi Connect protocol (application/connect+json)."""

    def parse(self, body: str, url: str = "") -> ParsedResponse:
        """Parse Connect protocol response body.

        The body can be:
        1. Pre-decoded text (from decode_binary_frames) — a newline-joined string
        2. Raw text with embedded null bytes (from response.text() on binary data)

        In both cases, we try to extract JSON objects.
        """
        result = ParsedResponse(raw_body=body[:2000] if body else "")

        if not body or not body.strip():
            return result

        chunks = self._extract_json_chunks(body)
        if not chunks:
            return result

        text_parts: dict[str, list[str]] = {}  # block_id -> [chars]
        seen_urls: set[str] = set()

        for chunk in chunks:
            error = chunk.get("error")
            if isinstance(error, dict):
                error_info, error_type = self._classify_connect_error(error)
                if error_info:
                    result.error = error_info
                    result.error_type = error_type
                    logger.warning(
                        "[KimiConnect] Error frame detected: %s (type=%s)",
                        error_info,
                        error_type,
                    )
                    continue

            op = chunk.get("op", "")
            mask = chunk.get("mask", "")

            # Text content
            if mask == "block.text.content":
                block = chunk.get("block", {})
                block_id = block.get("id", "unknown")
                text_obj = block.get("text", {})
                content = text_obj.get("content", "")

                if op == "append" and content:
                    text_parts.setdefault(block_id, []).append(content)
                elif op == "set" and content:
                    text_parts[block_id] = [content]

            # Search references — two known formats
            # Format 1: block.search.webPages (legacy/rare)
            elif mask == "block.search.webPages":
                block = chunk.get("block", {})
                search = block.get("search", {})
                web_pages = search.get("webPages", [])
                for page in web_pages:
                    self._add_ref(page, result.references, seen_urls)

            # Format 2: message.refs.searchChunks (primary, 2026-03 confirmed)
            # Each chunk has {id, base: {title, url, siteName, snippet, ...}}
            elif mask in ("message.refs.searchChunks", "message.refs.usedSearchChunks"):
                msg = chunk.get("message", {})
                refs_obj = msg.get("refs", {})
                for key in ("searchChunks", "usedSearchChunks"):
                    for item in refs_obj.get(key, []):
                        if isinstance(item, dict):
                            base = item.get("base", {})
                            if isinstance(base, dict) and base.get("url"):
                                self._add_ref(base, result.references, seen_urls)

        # Assemble answer text from all text blocks
        all_text_parts = []
        for block_id in sorted(text_parts.keys()):
            all_text_parts.append("".join(text_parts[block_id]))
        result.answer_text = "\n".join(all_text_parts)

        return result

    @staticmethod
    def _classify_connect_error(error: dict) -> tuple[str, str]:
        details = error.get("details") or []
        for detail in details:
            if not isinstance(detail, dict):
                continue
            debug = detail.get("debug") or {}
            reason = str(debug.get("reason") or "")
            localized = debug.get("localizedMessage") or {}
            message = str(localized.get("message") or "")
            lowered = f"{reason} {message}".lower()
            if "anonymous_require_login" in lowered or "login" in lowered:
                return message or "Please login to continue.", "auth_required"

        code = str(error.get("code") or "")
        if code:
            return code, "server_error"
        return "", ""

    @staticmethod
    def _add_ref(
        item: dict,
        refs: list[SearchReference],
        seen: set[str],
    ) -> None:
        url = item.get("url", "")
        if not url or url in seen:
            return
        seen.add(url)
        refs.append(SearchReference(
            index=len(refs) + 1,
            title=item.get("title") or _domain_from_url(url),
            url=url,
            snippet=item.get("snippet"),
            site_name=item.get("siteName") or _domain_from_url(url),
            is_official=False,
        ))

    def _extract_json_chunks(self, body: str) -> list[dict]:
        """Extract JSON objects from the body.

        Handles both:
        - Newline-separated JSON strings (from decode_binary_frames)
        - Raw text with null-byte delimited JSON (from response.text())
        """
        chunks = []

        # Strategy 1: Try splitting by null bytes (common in Connect protocol text)
        if "\x00" in body:
            # Split by null bytes, filter out empty parts, try to parse each as JSON
            parts = body.split("\x00")
            for part in parts:
                part = part.strip()
                if not part or not part.startswith("{"):
                    # Skip non-JSON parts (length bytes appear as non-printable chars)
                    # Try to find the start of JSON in this part
                    idx = part.find("{")
                    if idx >= 0:
                        part = part[idx:]
                    else:
                        continue
                try:
                    obj = json.loads(part)
                    if isinstance(obj, dict) and obj:
                        chunks.append(obj)
                except json.JSONDecodeError:
                    continue
        else:
            # Strategy 2: Newline-separated JSON
            for line in body.split("\n"):
                line = line.strip()
                if not line or not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj:
                        chunks.append(obj)
                except json.JSONDecodeError:
                    continue

        return chunks
