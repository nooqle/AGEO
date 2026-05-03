"""Unit tests for SSE response parsers.

Tests DeepSeek, Yuanbao, and Doubao SSE parsers using synthetic SSE payloads
that match the real format observed via network sniffing.
"""

import json

from app.core.fetchers.browser.parsers.sse import (
    DeepSeekSSEParser,
    DoubaoSSEParser,
    YuanbaoSSEParser,
    _domain_from_url,
    _iter_sse_data,
)


# ------------------------------------------------------------------ helpers


class TestIterSSEData:
    """Test the SSE data line iterator."""

    def test_basic_data_lines(self):
        body = 'data: {"key": "val1"}\n\ndata: {"key": "val2"}\n\n'
        items = list(_iter_sse_data(body))
        assert len(items) == 2
        assert items[0] == {"key": "val1"}
        assert items[1] == {"key": "val2"}

    def test_skips_event_and_id_lines(self):
        body = (
            "event: ready\n"
            "data: {\"type\": \"ready\"}\n\n"
            "id: 5\n"
            "event: STREAM_MSG\n"
            "data: {\"type\": \"msg\"}\n\n"
        )
        items = list(_iter_sse_data(body))
        assert len(items) == 2
        assert items[0]["type"] == "ready"
        assert items[1]["type"] == "msg"

    def test_skips_empty_data(self):
        body = "data: {}\n\ndata: \n\ndata: {\"ok\": true}\n\n"
        items = list(_iter_sse_data(body))
        assert len(items) == 1
        assert items[0] == {"ok": True}

    def test_skips_invalid_json(self):
        body = 'data: not-json\n\ndata: {"valid": true}\n\n'
        items = list(_iter_sse_data(body))
        assert len(items) == 1
        assert items[0] == {"valid": True}

    def test_empty_body(self):
        assert list(_iter_sse_data("")) == []
        assert list(_iter_sse_data("\n\n\n")) == []


class TestDomainFromUrl:
    def test_normal_url(self):
        assert _domain_from_url("https://www.example.com/path") == "example.com"

    def test_no_www(self):
        assert _domain_from_url("https://blog.csdn.net/article") == "blog.csdn.net"

    def test_invalid_url(self):
        result = _domain_from_url("not-a-url")
        assert isinstance(result, str)
        assert len(result) > 0


# ------------------------------------------------------------------ DeepSeek


def _make_deepseek_sse(
    text_chunks: list[str] | None = None,
    references: list[dict] | None = None,
) -> str:
    """Build a synthetic DeepSeek SSE body for testing."""
    lines = []

    # Ready event
    lines.append('event: ready')
    lines.append('data: {"request_message_id":1,"response_message_id":2}')
    lines.append('')

    # Initial response with SEARCH fragment
    initial = {
        "v": {
            "response": {
                "message_id": 2,
                "fragments": [{
                    "id": 1,
                    "type": "SEARCH",
                    "status": "WIP",
                    "results": [],
                }],
            }
        }
    }
    lines.append(f'data: {json.dumps(initial)}')
    lines.append('')

    # Patch: add search results
    if references:
        patch = {"p": "response/fragments/-1/results", "v": references}
        lines.append(f'data: {json.dumps(patch)}')
        lines.append('')

    # Patch: search done
    lines.append('data: {"p":"response/fragments/-1/status","v":"FINISHED"}')
    lines.append('')

    # APPEND new TEXT fragment
    lines.append('data: {"p":"response/fragments","o":"APPEND","v":[{"id":2,"type":"TEXT","status":"WIP","content":""}]}')
    lines.append('')

    # Patch: append text chunks
    if text_chunks:
        for chunk in text_chunks:
            patch = {"p": "response/fragments/-1/content", "o": "APPEND", "v": chunk}
            lines.append(f'data: {json.dumps(patch)}')
            lines.append('')

    # Patch: text done
    lines.append('data: {"p":"response/fragments/-1/status","v":"FINISHED"}')
    lines.append('')

    return '\n'.join(lines)


class TestDeepSeekSSEParser:
    def setup_method(self):
        self.parser = DeepSeekSSEParser()

    def test_parse_text_and_refs(self):
        refs = [
            {"url": "https://example.com/1", "title": "Example 1", "snippet": "snippet1", "cite_index": 1, "site_name": "example.com"},
            {"url": "https://example.com/2", "title": "Example 2", "snippet": "snippet2", "cite_index": 2, "site_name": "example.com"},
        ]
        body = _make_deepseek_sse(
            text_chunks=["AEO是答案引擎优化", "（Answer Engine Optimization）的缩写。"],
            references=refs,
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text
        assert "Answer Engine Optimization" in result.answer_text
        assert len(result.references) == 2
        assert result.references[0].url == "https://example.com/1"
        assert result.references[0].title == "Example 1"
        assert result.references[1].index == 2

    def test_parse_text_only(self):
        body = _make_deepseek_sse(
            text_chunks=["这是一个足够长的测试文本，用于验证解析器能正确工作。"],
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "测试文本" in result.answer_text
        assert len(result.references) == 0

    def test_empty_body(self):
        result = self.parser.parse("")
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_refs_deduplication(self):
        refs = [
            {"url": "https://example.com/dup", "title": "Dup 1", "cite_index": 1},
            {"url": "https://example.com/dup", "title": "Dup 2", "cite_index": 2},
            {"url": "https://example.com/unique", "title": "Unique", "cite_index": 3},
        ]
        body = _make_deepseek_sse(text_chunks=["足够长的回答文本，这段文字超过十个字符。"], references=refs)
        result = self.parser.parse(body)
        assert len(result.references) == 2  # deduped

    def test_done_event_only(self):
        """Body with only non-content events should return empty."""
        body = (
            'event: ready\n'
            'data: {"request_message_id":1}\n\n'
            'event: update_session\n'
            'data: {"updated_at":1234}\n\n'
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_refs_from_initial_response(self):
        """References embedded in the initial full response object."""
        initial = {
            "v": {
                "response": {
                    "fragments": [{
                        "id": 1,
                        "type": "SEARCH",
                        "status": "FINISHED",
                        "results": [
                            {"url": "https://a.com", "title": "A", "cite_index": 1, "snippet": "aaa"},
                            {"url": "https://b.com", "title": "B", "cite_index": 2, "snippet": "bbb"},
                        ],
                    }],
                }
            }
        }
        body = f'data: {json.dumps(initial)}\n\n'
        body += 'data: {"p":"response/fragments","o":"APPEND","v":[{"id":2,"type":"TEXT","content":"一段足够长的文本，用于通过验证检查。"}]}\n\n'

        result = self.parser.parse(body)
        assert len(result.references) == 2
        assert result.references[0].url == "https://a.com"


# ------------------------------------------------------------------ Yuanbao


def _make_yuanbao_sse(
    text_content: str = "",
    docs: list[dict] | None = None,
    step_msgs: list[str] | None = None,
) -> str:
    """Build a synthetic Yuanbao SSE body.

    Yuanbao uses "text" events with "msg" field for answer tokens (delta,
    concatenate all), "searchGuid" for references, and "step" for status.
    """
    lines = []

    # Text marker (always first, no msg field)
    lines.append('data: {"type":"text"}')
    lines.append('')

    # Step events (status messages)
    if step_msgs:
        for msg in step_msgs:
            lines.append(f'data: {json.dumps({"type": "step", "msg": msg}, ensure_ascii=False)}')
            lines.append('')

    # SearchGuid with docs
    if docs:
        sg = {"type": "searchGuid", "title": "引用资料", "docs": docs}
        lines.append(f'data: {json.dumps(sg, ensure_ascii=False)}')
        lines.append('')

    # Text events with msg field — simulate token-by-token streaming
    if text_content:
        # Simulate real streaming: short token chunks (1-4 chars each)
        i = 0
        while i < len(text_content):
            chunk_len = min(3, len(text_content) - i)  # 1-3 chars per token
            token = text_content[i:i+chunk_len]
            lines.append(f'data: {json.dumps({"type": "text", "msg": token}, ensure_ascii=False)}')
            lines.append('')
            i += chunk_len

    return '\n'.join(lines)


class TestYuanbaoSSEParser:
    def setup_method(self):
        self.parser = YuanbaoSSEParser()

    def test_parse_text_and_refs(self):
        docs = [
            {"index": 1, "title": "百度百科 AEO", "url": "https://baike.baidu.com/item/AEO", "web_site_name": "百度百科", "quote": "AEO是..."},
            {"index": 2, "title": "新浪财经", "url": "https://cj.sina.cn/article/1", "web_site_name": "财经头条", "quote": "答案引擎..."},
        ]
        body = _make_yuanbao_sse(
            text_content="AEO（Answer Engine Optimization，答案引擎优化）是搜索引擎优化的进化版。",
            docs=docs,
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text
        assert "进化版" in result.answer_text
        assert len(result.references) == 2
        assert result.references[0].site_name == "百度百科"

    def test_empty_body(self):
        result = self.parser.parse("")
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_refs_only(self):
        docs = [{"index": 1, "title": "Test", "url": "https://test.com", "quote": "q"}]
        body = _make_yuanbao_sse(docs=docs)
        result = self.parser.parse(body)
        assert len(result.references) == 1
        assert not result.parse_ok  # no text content

    def test_text_tokens_concatenated(self):
        """All text event msg tokens are concatenated into the full answer."""
        body = (
            'data: {"type":"text"}\n\n'
            'data: {"type":"text","msg":"针对"}\n\n'
            'data: {"type":"text","msg":"您"}\n\n'
            'data: {"type":"text","msg":"的"}\n\n'
            'data: {"type":"text","msg":"皮肤"}\n\n'
            'data: {"type":"text","msg":"问题"}\n\n'
            'data: {"type":"text","msg":"，"}\n\n'
            'data: {"type":"text","msg":"建议"}\n\n'
            'data: {"type":"text","msg":"使用温和的护肤品。"}\n\n'
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert result.answer_text == "针对您的皮肤问题，建议使用温和的护肤品。"

    def test_inline_rendering_markers_are_cleaned(self):
        body = _make_yuanbao_sse(
            text_content=(
                "[](@mark_underline=1)### 标题[citation:1]\n"
                "正文[](@mark_underline=2)[citation:2][](@mark_underline=3)继续。"
            )
        )

        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "mark_underline" not in result.answer_text
        assert "[citation:" not in result.answer_text
        assert result.answer_text == "### 标题\n正文继续。"

    def test_step_events_ignored(self):
        """Step events (status messages) should not appear in answer text."""
        body = _make_yuanbao_sse(
            text_content="AEO是答案引擎优化的缩写，这是一种面向AI搜索的策略。",
            step_msgs=["正在搜索资料", "正在整理答案"],
        )
        result = self.parser.parse(body)
        assert "正在搜索" not in result.answer_text
        assert "AEO" in result.answer_text

    def test_replace_events_ignored(self):
        """Replace events (media/UI) should not appear in answer text."""
        body = (
            'data: {"type":"text","msg":"答案文本"}\n\n'
            'data: {"type":"text","msg":"，继续"}\n\n'
            'data: {"type":"text","msg":"更多内容在这里。"}\n\n'
            'data: {"type":"replace","replace":{"id":"0","display":"videoBoxV2"}}\n\n'
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert result.answer_text == "答案文本，继续更多内容在这里。"

    def test_realistic_event_sequence(self):
        """Simulates real Yuanbao SSE: text marker → steps → searchGuid → text tokens."""
        lines = []
        # 1. Text marker (no msg)
        lines.extend(['data: {"type":"text"}', ''])
        # 2. Speech type event (non-JSON, skipped by _iter_sse_data)
        lines.extend(['event: speech_type', 'data: status', ''])
        # 3. Step events
        lines.extend([f'data: {json.dumps({"type":"step","msg":"正在搜索资料","scene":"ai_search_light","index":0})}', ''])
        lines.extend([f'data: {json.dumps({"type":"step","msg":"正在搜索资料","scene":"ai_search_light","index":2})}', ''])
        # 4. Speech type change
        lines.extend(['event: speech_type', 'data: search_with_text', ''])
        # 5. SearchGuid with docs
        sg = {"type": "searchGuid", "title": "引用 2 篇资料", "docs": [
            {"index": 1, "title": "百度百科", "url": "https://baike.baidu.com/item/AEO", "web_site_name": "百度百科", "quote": "AEO介绍"},
            {"index": 2, "title": "新浪财经", "url": "https://cj.sina.cn/aeo", "web_site_name": "财经头条", "quote": "AI搜索"},
        ]}
        lines.extend([f'data: {json.dumps(sg, ensure_ascii=False)}', ''])
        # 6. Answer text tokens (type: "text" with msg field)
        for token in ["AEO", "（", "Answer", " Engine", " Optimization", "，", "答案引擎优化", "）", "是", "搜索引擎优化的进化版本。"]:
            lines.extend([f'data: {json.dumps({"type":"text","msg":token})}', ''])
        # 7. Meta event
        meta_evt = json.dumps({"type": "meta", "metadata": {}})
        lines.extend([f'data: {meta_evt}', ''])
        # 8. Replace event (media, not answer text)
        lines.extend([f'data: {json.dumps({"type":"replace","replace":{"id":"0","display":"videoBoxV2"}})}', ''])
        body = '\n'.join(lines)

        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert result.answer_text == "AEO（Answer Engine Optimization，答案引擎优化）是搜索引擎优化的进化版本。"
        assert len(result.references) == 2
        assert result.references[0].url == "https://baike.baidu.com/item/AEO"


# ------------------------------------------------------------------ Doubao


def _make_doubao_sse(
    text_blocks: list[dict] | None = None,
    search_results: list[dict] | None = None,
    chunk_delta_tokens: list[str] | None = None,
) -> str:
    """Build a synthetic Doubao SSE body.

    Args:
        text_blocks: content_block text (STREAM_MSG_NOTIFY format, fallback path)
        search_results: search references (STREAM_CHUNK patch_op format)
        chunk_delta_tokens: CHUNK_DELTA text tokens (primary answer path)
    """
    lines = []

    # Heartbeat
    lines.append('id: 0')
    lines.append('event: SSE_HEARTBEAT')
    lines.append('data: {}')
    lines.append('')

    # ACK
    lines.append('id: 0')
    lines.append('event: SSE_ACK')
    lines.append('data: {"query_list": []}')
    lines.append('')

    # CHUNK_DELTA tokens (primary answer text path)
    if chunk_delta_tokens:
        for i, token in enumerate(chunk_delta_tokens):
            lines.append(f'id: {i+1}')
            lines.append('event: CHUNK_DELTA')
            lines.append(f'data: {json.dumps({"text": token})}')
            lines.append('')

    # Stream message with content blocks (fallback path)
    if text_blocks:
        for i, tb in enumerate(text_blocks):
            block = {
                "block_type": 10000,
                "block_id": f"text_{i}",
                "content": {"text_block": {"text": tb["text"]}},
                "is_finish": tb.get("is_finish", False),
            }
            msg = {"content": {"content_block": [block]}}
            lines.append(f'id: {i+100}')
            lines.append('event: STREAM_MSG_NOTIFY')
            lines.append(f'data: {json.dumps(msg)}')
            lines.append('')

    # Search results in STREAM_CHUNK patch_op
    if search_results:
        block = {
            "block_type": 10102,
            "block_id": "search_0",
            "content": {
                "search_block": {"results": search_results}
            },
        }
        patch_op = [{"patch_object": 1, "patch_type": 1, "patch_value": {"content_block": [block]}}]
        msg = {"message_id": "msg_1", "patch_op": patch_op}
        lines.append('id: 99')
        lines.append('event: STREAM_CHUNK')
        lines.append(f'data: {json.dumps(msg)}')
        lines.append('')

    return '\n'.join(lines)


class TestDoubaoSSEParser:
    def setup_method(self):
        self.parser = DoubaoSSEParser()

    # -- CHUNK_DELTA (primary answer path) --

    def test_chunk_delta_text(self):
        """CHUNK_DELTA tokens are the primary answer text source."""
        body = _make_doubao_sse(
            chunk_delta_tokens=["AEO是", "答案引擎优化", "的缩写，", "这是一种新兴的数字营销策略。"],
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert result.answer_text == "AEO是答案引擎优化的缩写，这是一种新兴的数字营销策略。"

    def test_chunk_delta_with_refs(self):
        """CHUNK_DELTA text + STREAM_CHUNK search references."""
        refs = [
            {"url": "https://example.com/1", "title": "Ref 1", "snippet": "s1", "site_name": "example"},
            {"url": "https://example.com/2", "title": "Ref 2", "snippet": "s2", "site_name": "example"},
        ]
        body = _make_doubao_sse(
            chunk_delta_tokens=["AEO是答案引擎优化", "（Answer Engine Optimization）", "的缩写。"],
            search_results=refs,
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text
        assert len(result.references) == 2

    def test_chunk_delta_preferred_over_blocks(self):
        """When both CHUNK_DELTA and content_block exist, CHUNK_DELTA wins."""
        body = _make_doubao_sse(
            chunk_delta_tokens=["正确的AI答案文本，包含详细的护肤品推荐信息。"],
            text_blocks=[{"text": "这是用户的问题回显，不应该出现在最终答案中。"}],
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "正确的AI答案" in result.answer_text
        assert "用户的问题回显" not in result.answer_text

    # -- content_block fallback path --

    def test_content_block_fallback(self):
        """content_block text is used when no CHUNK_DELTA tokens exist."""
        body = _make_doubao_sse(
            text_blocks=[
                {"text": "AEO是答案引擎优化的缩写，这是一种新兴的数字营销策略。"},
            ],
        )
        result = self.parser.parse(body)
        result = self.parser.validate(result)

        assert result.parse_ok
        assert "AEO" in result.answer_text

    def test_empty_body(self):
        result = self.parser.parse("")
        result = self.parser.validate(result)
        assert not result.parse_ok

    def test_skips_loading_blocks(self):
        """Loading blocks (type 10101) should be ignored."""
        body = (
            'id: 1\n'
            'event: STREAM_MSG_NOTIFY\n'
            'data: {"content":{"content_block":[{"block_type":10101,"block_id":"load_1","content":{"loading_block":{"scene":2}}}]}}\n\n'
        )
        result = self.parser.parse(body)
        assert result.answer_text == ""

    def test_dedup_blocks(self):
        """Same block_id should not be counted twice in fallback path."""
        body = _make_doubao_sse(text_blocks=[
            {"text": "Hello"},
            {"text": "Hello"},  # same text but different block_id
        ])
        result = self.parser.parse(body)
        # Both should be included since they have different block_ids
        assert result.answer_text.count("Hello") == 2

    def test_double_encoded_content(self):
        """Doubao sends content as a JSON string, not an object (production format)."""
        inner = json.dumps({
            "content_block": [{
                "block_type": 10000,
                "block_id": "blk_1",
                "content": {"text_block": {"text": "AEO是答案引擎优化的缩写，它是一种面向AI搜索的营销策略。"}},
            }]
        })
        # content field is a JSON *string*
        body = f'id: 1\nevent: STREAM_MSG_NOTIFY\ndata: {json.dumps({"content": inner})}\n\n'
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert "AEO" in result.answer_text

    def test_double_encoded_message(self):
        """FULL_MSG_NOTIFY: message is a JSON string whose content is also a JSON string."""
        content_list = json.dumps([{
            "block_type": 10000,
            "block_id": "blk_2",
            "content": {"text_block": {"text": "这是一段足够长的回答文本，用于验证三重序列化的解码逻辑。"}},
        }])
        message_str = json.dumps({
            "conversation_id": "123",
            "message_id": "456",
            "content": content_list,  # triple-encoded: string inside string
        })
        body = f'id: 2\nevent: FULL_MSG_NOTIFY\ndata: {json.dumps({"message": message_str})}\n\n'
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert "三重序列化" in result.answer_text

    def test_double_encoded_patch_op(self):
        """STREAM_CHUNK: patch_op is a JSON string containing content_block updates."""
        patch = json.dumps([{
            "patch_object": 1,
            "patch_type": 1,
            "patch_value": {
                "content_block": [{
                    "block_type": 10000,
                    "block_id": "blk_3",
                    "content": {"text_block": {"text": "增量更新的文本内容，这是通过patch_op传递的数据。"}},
                }]
            },
        }])
        body = f'id: 3\nevent: STREAM_CHUNK\ndata: {json.dumps({"message_id": "789", "patch_op": patch})}\n\n'
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert "patch_op" in result.answer_text

    def test_double_encoded_with_search_refs(self):
        """Double-encoded content with search_block references."""
        inner = json.dumps({
            "content_block": [
                {
                    "block_type": 10000,
                    "block_id": "blk_txt",
                    "content": {"text_block": {"text": "关于护肤品的AEO优化策略需要考虑多个维度的因素。"}},
                },
                {
                    "block_type": 10102,
                    "block_id": "blk_search",
                    "content": {
                        "search_block": {
                            "results": [
                                {"url": "https://example.com/skincare", "title": "护肤品指南", "snippet": "s1", "site_name": "Example"},
                                {"url": "https://blog.test.com/aeo", "title": "AEO策略", "snippet": "s2", "site_name": "Test"},
                            ]
                        }
                    },
                },
            ]
        })
        body = f'id: 1\nevent: STREAM_MSG_NOTIFY\ndata: {json.dumps({"content": inner})}\n\n'
        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert "护肤品" in result.answer_text
        assert len(result.references) == 2
        assert result.references[0].url == "https://example.com/skincare"

    def test_realistic_production_flow(self):
        """Simulates real Doubao SSE: user echo + loading + CHUNK_DELTA tokens + search refs."""
        lines = []
        # 1. Heartbeat
        lines.extend(['id: 0', 'event: SSE_HEARTBEAT', 'data: {}', ''])
        # 2. FULL_MSG_NOTIFY: user message echo (should be ignored for answer)
        user_content = json.dumps([{
            "block_type": 10000,
            "block_id": "user_blk",
            "content": {"text_block": {"text": "哪个牌子的护肤品效果好？"}},
        }])
        user_msg = json.dumps({"content": user_content, "user_type": 1})
        lines.extend(['id: 1', 'event: FULL_MSG_NOTIFY', f'data: {json.dumps({"message": user_msg})}', ''])
        # 3. Loading block
        lines.extend([
            'id: 2', 'event: STREAM_MSG_NOTIFY',
            'data: {"content":{"content_block":[{"block_type":10101,"block_id":"load_1","content":{"loading_block":{"scene":2}}}]}}',
            '',
        ])
        # 4. CHUNK_DELTA tokens (AI answer)
        for i, token in enumerate(["赫莲娜", "黑绷带面霜", "是高端", "抗皱产品", "，含30%玻色因。"]):
            lines.extend([f'id: {10+i}', 'event: CHUNK_DELTA', f'data: {json.dumps({"text": token})}', ''])
        # 5. Search refs in STREAM_CHUNK
        ref_block = {"block_type": 10102, "block_id": "s1", "content": {"search_block": {"results": [
            {"url": "https://hr.com", "title": "赫莲娜官网", "snippet": "...", "site_name": "HR"},
        ]}}}
        patch = [{"patch_object": 1, "patch_type": 1, "patch_value": {"content_block": [ref_block]}}]
        lines.extend(['id: 99', 'event: STREAM_CHUNK', f'data: {json.dumps({"message_id": "m1", "patch_op": patch})}', ''])
        body = '\n'.join(lines)

        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert result.answer_text == "赫莲娜黑绷带面霜是高端抗皱产品，含30%玻色因。"
        assert "哪个牌子" not in result.answer_text  # user echo excluded
        assert len(result.references) == 1
        assert result.references[0].url == "https://hr.com"

    def test_search_query_result_block(self):
        """block_type 10025 with search_query_result_block (primary format, 2026-03)."""
        lines = []
        lines.extend(['id: 0', 'event: SSE_HEARTBEAT', 'data: {}', ''])
        # CHUNK_DELTA tokens (answer)
        for i, token in enumerate(["雅诗兰黛", "小棕瓶", "主打", "夜间修护"]):
            lines.extend([f'id: {10+i}', 'event: CHUNK_DELTA', f'data: {json.dumps({"text": token})}', ''])
        # search_query_result_block in patch_op
        search_block = {
            "block_type": 10025,
            "block_id": "sqrb_1",
            "content": {"search_query_result_block": {
                "summary": "搜索 2 个关键词，参考 3 篇资料",
                "queries": ["雅诗兰黛小棕瓶"],
                "results": [
                    {"text_card": {
                        "id": 1, "title": "小棕瓶评测_搜狐网", "sitename": "搜狐",
                        "url": "https://m.sohu.com/a/123", "summary": "小棕瓶功效...",
                    }},
                    {"text_card": {
                        "id": 2, "title": "抗老精华对比_头条", "sitename": "头条",
                        "url": "http://m.toutiao.com/group/456", "summary": "精华对比...",
                    }},
                    {"text_card": {
                        "id": 3, "title": "护肤推荐_什么值得买", "sitename": "什么值得买",
                        "url": "https://post.smzdm.com/p/abc", "summary": "护肤推荐...",
                    }},
                ],
            }},
        }
        patch = [{"patch_object": 1, "patch_type": 1, "patch_value": {"content_block": [search_block]}}]
        lines.extend([
            'id: 50', 'event: STREAM_CHUNK',
            f'data: {json.dumps({"message_id": "m1", "patch_op": json.dumps(patch)})}',
            '',
        ])
        body = '\n'.join(lines)

        result = self.parser.parse(body)
        result = self.parser.validate(result)
        assert result.parse_ok
        assert result.answer_text == "雅诗兰黛小棕瓶主打夜间修护"
        assert len(result.references) == 3
        assert result.references[0].url == "https://m.sohu.com/a/123"
        assert result.references[0].title == "小棕瓶评测_搜狐网"
        assert result.references[0].site_name == "搜狐"
        assert result.references[0].snippet == "小棕瓶功效..."
        assert result.references[2].url == "https://post.smzdm.com/p/abc"


# ------------------------------------------------------------------ ParsedResponse validation


class TestValidation:
    def test_short_answer_fails(self):
        parser = DeepSeekSSEParser()
        body = 'data: {"p":"response/fragments/-1/content","o":"APPEND","v":"短"}\n\n'
        result = parser.parse(body)
        result = parser.validate(result)
        assert not result.parse_ok
        assert "too short" in result.error

    def test_raw_body_truncated(self):
        parser = DeepSeekSSEParser()
        long_body = "data: " + json.dumps({"v": "x" * 5000}) + "\n\n"
        result = parser.parse(long_body)
        assert len(result.raw_body) <= 2000
