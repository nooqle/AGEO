from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.domain_memory_service import DomainMemoryService


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
