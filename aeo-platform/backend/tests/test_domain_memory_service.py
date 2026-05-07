from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.core.domain_normalization import normalize_domain
from app.services.domain_memory_service import DomainMemoryService
from app.services.url_intelligence_skill import DomainIntelligenceResult
from app.services.url_intelligence_skill import URLIntelligenceSkill
from app.services.url_intelligence_skill import _SYSTEM_PROMPT as URL_SYSTEM_PROMPT


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def first(self):
        return self._value


class _FakeDb:
    def __init__(self, *values):
        self._values = list(values)

    async def execute(self, _statement):
        value = self._values.pop(0) if self._values else None
        return _ScalarResult(value)


def test_normalize_domain_strips_port():
    assert normalize_domain("samr.gov.cn:8007") == "samr.gov.cn"
    assert normalize_domain("https://www.samr.gov.cn:8007/foo") == "samr.gov.cn"


@pytest.mark.asyncio
async def test_resolve_citation_domain_fast_uses_site_name_without_model(monkeypatch):
    def fail_model_call():
        raise AssertionError("fast domain resolution must not call the LLM")

    monkeypatch.setattr(
        "app.services.domain_memory_service.get_llm_model",
        fail_model_call,
    )
    service = DomainMemoryService(_FakeDb(None, None))  # type: ignore[arg-type]

    resolution = await service.resolve_citation_domain_fast(
        url="https://health.baidu.com/example",
        raw_domain="health.baidu.com",
        title="",
        snippet="",
        site_name="百度健康",
        brand_name="纽崔莱",
        entity_id=None,
        official_domains=["amway.com.cn"],
        platform="doubao",
    )

    assert resolution.canonical_domain == "health.baidu.com"
    assert resolution.display_name == "百度健康"
    assert resolution.source_type == "other"
    assert resolution.relation_type == "unknown"
    assert resolution.status == "fast_fallback"
    assert resolution.resolved_by == "fast_fallback"


@pytest.mark.asyncio
async def test_resolve_citation_domain_fast_detects_official_domain():
    service = DomainMemoryService(_FakeDb(None, None))  # type: ignore[arg-type]

    resolution = await service.resolve_citation_domain_fast(
        url="https://www.amway.com.cn/product",
        raw_domain="www.amway.com.cn",
        title=None,
        snippet=None,
        site_name="安利",
        brand_name="纽崔莱",
        entity_id="entity-1",
        official_domains=["amway.com.cn"],
        platform="doubao",
    )

    assert resolution.canonical_domain == "amway.com.cn"
    assert resolution.display_name == "安利"
    assert resolution.source_type == "official"
    assert resolution.relation_type == "official"
    assert resolution.is_official is True
    assert resolution.status == "resolved"
    assert resolution.resolved_by == "deterministic_official_domain"


@pytest.mark.asyncio
async def test_resolve_citation_domain_fast_uses_existing_memory():
    identity = SimpleNamespace(
        display_name="民福康",
        owner_name="民福康",
        source_type="vertical_media",
        site_category="健康医疗",
        confidence=0.92,
        status="resolved",
        resolved_by="llm",
    )
    relation = SimpleNamespace(
        relation_type="media_reference",
        confidence=0.74,
        status="resolved",
        resolved_by="manual",
    )
    service = DomainMemoryService(_FakeDb(identity, relation))  # type: ignore[arg-type]

    resolution = await service.resolve_citation_domain_fast(
        url="https://mfk.com/article",
        raw_domain="mfk.com",
        title=None,
        snippet=None,
        site_name=None,
        brand_name="纽崔莱",
        entity_id="entity-1",
        official_domains=["amway.com.cn"],
        platform="doubao",
    )

    assert resolution.display_name == "民福康"
    assert resolution.owner_name == "民福康"
    assert resolution.source_type == "vertical_media"
    assert resolution.site_category == "健康医疗"
    assert resolution.relation_type == "media_reference"
    assert resolution.confidence == 0.92
    assert resolution.status == "resolved"
    assert resolution.resolved_by == "manual"


@pytest.mark.asyncio
async def test_url_intelligence_skill_calls_llm_and_returns_compact_mapping(
    monkeypatch,
):
    class _FakeResponse:
        content = '{"health.baidu.com":["百度健康","健康医疗/垂直内容"]}'

    class _FakeModel:
        async def async_call(self, **kwargs):
            messages = kwargs["messages"]
            assert "Domain Intelligence Analyst" in messages[0]["content"]
            assert "health.baidu.com" in messages[1]["content"]
            assert "confidence" not in messages[0]["content"]
            assert "brief" not in messages[0]["content"]
            assert kwargs["response_format"] == {"type": "json_object"}
            return _FakeResponse()

    monkeypatch.setattr(
        "app.services.url_intelligence_skill.get_settings",
        lambda: SimpleNamespace(
            URL_INTELLIGENCE_TIMEOUT_SECONDS=45.0,
        ),
    )
    calls = []
    monkeypatch.setattr(
        "app.services.url_intelligence_skill.get_text_light_llm_model",
        lambda **kwargs: calls.append(kwargs) or _FakeModel(),
    )

    result = await URLIntelligenceSkill().analyze_domains(["health.baidu.com"])

    assert result["health.baidu.com"].site_name == "百度健康"
    assert result["health.baidu.com"].category == "健康医疗/垂直内容"
    assert calls == [{"task_name": "url_intelligence_skill"}]


def test_url_intelligence_prompt_contains_common_domain_examples():
    assert 'jd.com -> ["京东", "电商平台"]' in URL_SYSTEM_PROMPT
    assert 'post.smzdm.com -> ["什么值得买", "消费社区"]' in URL_SYSTEM_PROMPT
    assert 'mp.weixin.qq.com -> ["微信公众号", "内容平台"]' in URL_SYSTEM_PROMPT
    assert 'uland.taobao.com -> ["淘宝", "电商平台"]' in URL_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_url_intelligence_skill_retries_once_on_empty_json(monkeypatch):
    class _FakeResponse:
        def __init__(self, content):
            self.content = content

    class _FakeModel:
        def __init__(self):
            self.max_tokens = []

        async def async_call(self, **kwargs):
            self.max_tokens.append(kwargs["max_tokens"])
            if len(self.max_tokens) == 1:
                return _FakeResponse("")
            return _FakeResponse('{"example.com":["Example","SaaS"]}')

    fake_model = _FakeModel()
    monkeypatch.setattr(
        "app.services.url_intelligence_skill.get_settings",
        lambda: SimpleNamespace(
            URL_INTELLIGENCE_TIMEOUT_SECONDS=45.0,
        ),
    )
    monkeypatch.setattr(
        "app.services.url_intelligence_skill.get_text_light_llm_model",
        lambda **_kwargs: fake_model,
    )

    result = await URLIntelligenceSkill().analyze_domains(["example.com"])

    assert result["example.com"].site_name == "Example"
    assert result["example.com"].category == "SaaS"
    assert len(fake_model.max_tokens) == 2
    assert fake_model.max_tokens[1] > fake_model.max_tokens[0]


@pytest.mark.asyncio
async def test_url_intelligence_batches_domains_and_keeps_partial_success(
    monkeypatch,
):
    calls = []

    async def fake_analyze_once(self, domains):
        calls.append(list(domains))
        if "bad.example" in domains:
            raise RuntimeError("simulated batch failure")
        return {
            domain: DomainIntelligenceResult(
                domain=domain,
                site_name=f"site:{domain}",
                category="内容平台",
            )
            for domain in domains
        }

    monkeypatch.setattr(
        URLIntelligenceSkill,
        "_analyze_domains_once",
        fake_analyze_once,
    )

    result = await URLIntelligenceSkill(batch_size=2).analyze_domains(
        [
            "a.example",
            "b.example",
            "bad.example",
            "c.example",
            "d.example",
        ]
    )

    assert calls == [
        ["a.example", "b.example"],
        ["bad.example", "c.example"],
        ["d.example"],
    ]
    assert result["a.example"].category == "内容平台"
    assert result["d.example"].category == "内容平台"
    assert result["bad.example"].category == "缺乏特征，无法识别"
    assert result["c.example"].category == "缺乏特征，无法识别"


@pytest.mark.asyncio
async def test_resolve_citation_domain_fast_uses_url_intelligence_category():
    service = DomainMemoryService(_FakeDb(None, None))  # type: ignore[arg-type]

    resolution = await service.resolve_citation_domain_fast(
        url="https://health.baidu.com/example",
        raw_domain="health.baidu.com",
        title="",
        snippet="",
        site_name="",
        brand_name="纽崔莱",
        entity_id=None,
        official_domains=["amway.com.cn"],
        platform="doubao",
        url_intelligence={
            "domain": "health.baidu.com",
            "site_name": "百度健康",
            "category": "健康医疗/垂直内容",
        },
    )

    assert resolution.display_name == "百度健康"
    assert resolution.source_type == "健康医疗/垂直内容"
    assert resolution.site_category == "健康医疗/垂直内容"
    assert resolution.status == "resolved"
    assert resolution.resolved_by == "url_intelligence_skill"
    assert resolution.url_intelligence is not None
