"""Unit tests for Kimi Connect protocol parser.

Tests KimiConnectParser using synthetic Connect payloads
that match the real format observed via network sniffing.
"""

import json
import struct

import pytest

from app.core.fetchers.browser.parsers.connect import (
    KimiConnectParser,
    decode_binary_frames,
)


# ------------------------------------------------------------------ helpers


def _make_binary_frame(payload: str) -> bytes:
    """Build a single Connect protocol binary frame.

    Frame format: 1 byte flag (0x00) + 4 bytes BE length + payload.
    """
    payload_bytes = payload.encode("utf-8")
    return b"\x00" + struct.pack(">I", len(payload_bytes)) + payload_bytes


def _make_connect_body(
    text_chars: str = "",
    web_pages: list[dict] | None = None,
    include_heartbeat: bool = True,
) -> bytes:
    """Build a synthetic Kimi Connect protocol binary body."""
    frames = []

    # Heartbeat
    if include_heartbeat:
        frames.append(_make_binary_frame('{"heartbeat":{}}'))

    # Assistant message set
    frames.append(_make_binary_frame(json.dumps({
        "op": "set", "mask": "message", "eventOffset": 1,
        "message": {
            "id": "test_msg_1", "parentId": "test_msg_0",
            "role": "assistant", "status": "MESSAGE_STATUS_GENERATING",
        },
    })))

    # Search keywords
    if web_pages:
        frames.append(_make_binary_frame(json.dumps({
            "op": "append", "mask": "block.search.keywords",
            "eventOffset": 2,
            "block": {"id": "0_0", "search": {"keywords": ["test query"]}},
        })))

    # Search web pages
    if web_pages:
        for i, page_batch in enumerate(web_pages):
            frames.append(_make_binary_frame(json.dumps({
                "op": "append", "mask": "block.search.webPages",
                "eventOffset": 3 + i,
                "block": {"id": "0_0", "search": {"webPages": [page_batch]}},
            })))

    # Initialize text block
    frames.append(_make_binary_frame(json.dumps({
        "op": "set", "mask": "block.text.content",
        "eventOffset": 10,
        "block": {"id": "0_1", "text": {}},
    })))

    # Append text characters
    for i, char in enumerate(text_chars):
        frames.append(_make_binary_frame(json.dumps({
            "op": "append", "mask": "block.text.content",
            "eventOffset": 11 + i,
            "block": {"id": "0_1", "parentId": "", "text": {"content": char}},
        })))

    return b"".join(frames)


def _make_connect_text(
    text_chars: str = "",
    web_pages: list[dict] | None = None,
) -> str:
    """Build a synthetic Connect body as newline-separated JSON strings.

    This simulates pre-decoded frames for direct parser testing.
    """
    lines = []

    lines.append('{"heartbeat":{}}')

    if web_pages:
        for page in web_pages:
            lines.append(json.dumps({
                "op": "append", "mask": "block.search.webPages",
                "block": {"id": "0_0", "search": {"webPages": [page]}},
            }))

    # Initialize text block
    lines.append(json.dumps({
        "op": "set", "mask": "block.text.content",
        "block": {"id": "0_1", "text": {}},
    }))

    # Append text
    for char in text_chars:
        lines.append(json.dumps({
            "op": "append", "mask": "block.text.content",
            "block": {"id": "0_1", "text": {"content": char}},
        }))

    return "\n".join(lines)


# ------------------------------------------------------------------ decode_binary_frames


class TestDecodeBinaryFrames:
    def test_single_frame(self):
        payload = '{"heartbeat":{}}'
        data = _make_binary_frame(payload)
        frames = decode_binary_frames(data)
        assert len(frames) == 1
        assert frames[0] == payload

    def test_multiple_frames(self):
        data = (
            _make_binary_frame('{"heartbeat":{}}')
            + _make_binary_frame('{"op":"set","mask":"message"}')
        )
        frames = decode_binary_frames(data)
        assert len(frames) == 2
        assert "heartbeat" in frames[0]
        assert "message" in frames[1]

    def test_empty_data(self):
        assert decode_binary_frames(b"") == []

    def test_partial_frame(self):
        """Incomplete frame should not crash."""
        data = b"\x00\x00\x00\x00\x05He"  # length says 5 but only 2 bytes
        frames = decode_binary_frames(data)
        assert len(frames) == 1
        assert "He" in frames[0]

    def test_chinese_text(self):
        payload = '{"op":"append","block":{"text":{"content":"你好"}}}'
        data = _make_binary_frame(payload)
        frames = decode_binary_frames(data)
        assert len(frames) == 1
        obj = json.loads(frames[0])
        assert obj["block"]["text"]["content"] == "你好"

    def test_real_world_frame_sizes(self):
        """Verify we handle frames of varying sizes correctly."""
        small = _make_binary_frame('{"a":1}')
        medium = _make_binary_frame('{"data":"' + "x" * 500 + '"}')
        large = _make_binary_frame('{"data":"' + "x" * 5000 + '"}')
        data = small + medium + large
        frames = decode_binary_frames(data)
        assert len(frames) == 3


# ------------------------------------------------------------------ KimiConnectParser


class TestKimiConnectParser:
    def setup_method(self):
        self.parser = KimiConnectParser()

    def test_parse_text_newline_format(self):
        """Parse pre-decoded newline-separated JSON."""
        body = _make_connect_text(
            text_chars="AEO是答案引擎优化的缩写，用于提升品牌在AI搜索中的可见度。"
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text
        assert "答案引擎优化" in result.answer_text

    def test_parse_text_with_refs(self):
        web_pages = [
            {"title": "AEO Guide", "url": "https://example.com/aeo",
             "siteName": "Example", "snippet": "AEO is..."},
            {"title": "SEO vs AEO", "url": "https://blog.test.com/seo-aeo",
             "siteName": "Test Blog", "snippet": "Comparison..."},
        ]
        body = _make_connect_text(
            text_chars="AEO优化是一种新兴的数字营销策略，旨在让品牌被AI搜索引擎引用。",
            web_pages=web_pages,
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert len(result.references) == 2
        assert result.references[0].url == "https://example.com/aeo"
        assert result.references[0].site_name == "Example"
        assert result.references[1].title == "SEO vs AEO"

    def test_empty_body(self):
        result = self.parser.parse("")
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_heartbeat_only(self):
        body = '{"heartbeat":{}}\n{"heartbeat":{}}'
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_character_concatenation(self):
        """Verify character-by-character text assembly."""
        body = _make_connect_text(text_chars="ABCDEFGHIJ这是一个足够长的测试文本。")
        result = self.parser.parse(body)
        assert "ABCDEFGHIJ" in result.answer_text
        assert "测试文本" in result.answer_text

    def test_dedup_references(self):
        """Same URL should not produce duplicate references."""
        pages = [
            {"title": "Page A", "url": "https://dup.com/page",
             "siteName": "Dup", "snippet": "s1"},
            {"title": "Page B", "url": "https://dup.com/page",
             "siteName": "Dup", "snippet": "s2"},
            {"title": "Unique", "url": "https://unique.com/page",
             "siteName": "Uni", "snippet": "s3"},
        ]
        body = _make_connect_text(
            text_chars="一段足够长的文本，用于通过解析器的验证检查。",
            web_pages=pages,
        )
        result = self.parser.parse(body)
        assert len(result.references) == 2  # deduped

    def test_null_byte_delimited_body(self):
        """Simulate response.text() on binary Connect data."""
        # Build something like what response.text() returns from binary data:
        # null bytes mixed with JSON
        body = (
            '\x00\x00\x00\x00\x10{"heartbeat":{}}'
            '\x00\x00\x00\x00Z{"op":"set","mask":"block.text.content","block":{"id":"0_1","text":{}}}'
            '\x00\x00\x00\x00Y{"op":"append","mask":"block.text.content","block":{"id":"0_1","text":{"content":"这是一段测试内容用于验证空字节分割的解析逻辑是否正常工作。"}}}'
        )
        result = self.parser.parse(body)
        assert "测试内容" in result.answer_text

    def test_missing_site_name_fallback(self):
        """siteName falls back to domain extracted from URL."""
        pages = [
            {"title": "No Site", "url": "https://www.fallback-test.com/page"},
        ]
        body = _make_connect_text(
            text_chars="一段足够长的文本来通过验证。足够长了应该可以通过验证检查。",
            web_pages=pages,
        )
        result = self.parser.parse(body)
        assert len(result.references) == 1
        assert result.references[0].site_name == "fallback-test.com"

    def test_refs_search_chunks_format(self):
        """Parse refs from message.refs.searchChunks (primary format, 2026-03)."""
        lines = ['{"heartbeat":{}}']
        # Text
        lines.append(json.dumps({
            "op": "set", "mask": "block.text.content",
            "block": {"id": "0_1", "text": {}},
        }))
        for ch in "这是一段足够长的测试文本，用于验证searchChunks引用提取是否正常。":
            lines.append(json.dumps({
                "op": "append", "mask": "block.text.content",
                "block": {"id": "0_1", "text": {"content": ch}},
            }))
        # searchChunks — real format: message.refs.searchChunks[].base.{...}
        lines.append(json.dumps({
            "op": "append", "mask": "message.refs.searchChunks",
            "eventOffset": 78,
            "message": {"refs": {"searchChunks": [
                {"id": "1", "base": {
                    "title": "AEO优化指南", "url": "https://example.com/aeo",
                    "siteName": "Example", "snippet": "AEO is answer engine optimization",
                }},
                {"id": "2", "base": {
                    "title": "品牌分析报告", "url": "https://blog.test.com/brand",
                    "siteName": "Test Blog", "snippet": "Brand analysis...",
                }},
            ]}},
        }))
        # usedSearchChunks
        lines.append(json.dumps({
            "op": "set", "mask": "message.refs.usedSearchChunks",
            "eventOffset": 79,
            "message": {"refs": {"usedSearchChunks": [
                {"id": "1", "base": {
                    "title": "AEO优化指南", "url": "https://example.com/aeo",
                    "siteName": "Example", "snippet": "AEO is answer engine optimization",
                }},
            ]}},
        }))

        body = "\n".join(lines)
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert len(result.references) == 2  # deduped across searchChunks + usedSearchChunks
        assert result.references[0].url == "https://example.com/aeo"
        assert result.references[0].site_name == "Example"
        assert result.references[1].url == "https://blog.test.com/brand"


# ------------------------------------------------------------------ binary + parser integration


class TestBinaryFrameIntegration:
    """Test decode_binary_frames + KimiConnectParser together."""

    def setup_method(self):
        self.parser = KimiConnectParser()

    def test_full_pipeline(self):
        """Binary bytes → decode → parse → validate."""
        binary_body = _make_connect_body(
            text_chars="AEO是Answer Engine Optimization的缩写，即答案引擎优化。",
            web_pages=[
                {"title": "CSDN AEO Guide", "url": "https://blog.csdn.net/aeo",
                 "siteName": "CSDN博客", "snippet": "AEO优化指南"},
            ],
        )
        frames = decode_binary_frames(binary_body)
        body = "\n".join(frames)
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text
        assert "Answer Engine Optimization" in result.answer_text
        assert len(result.references) == 1
        assert result.references[0].site_name == "CSDN博客"

    def test_binary_no_text(self):
        """Binary body with only heartbeats and metadata."""
        frames_data = (
            _make_binary_frame('{"heartbeat":{}}')
            + _make_binary_frame('{"op":"set","mask":"chat.name","chat":{"name":"test"}}')
        )
        frames = decode_binary_frames(frames_data)
        body = "\n".join(frames)
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert not result.parse_ok
