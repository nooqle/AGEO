from __future__ import annotations

import asyncio
import json
import os
from types import SimpleNamespace

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret")

from app.core.llm import LLMResponse, LLMUsage
from app.services import aice_evaluation_service as service_module
from app.services import page_feature_service as page_feature_module
from app.services.aice_evaluation_service import AICEEvaluationService
from app.services.aice_prompt_contract import (
    AICE_DIMENSION_CODES,
    AICE_DIMENSION_LABELS,
    AICE_DIMENSION_MAX_SCORES,
)
from app.workflow.site_confidence_assessment import (
    DiscoveredPage,
    build_site_confidence_report,
    _build_actions,
    _build_report_markdown,
    _classify_exclusion,
    _page_confidence_summary,
)
from app.workflow import site_confidence_assessment as site_module


class _FakeModel:
    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0
        self.requests = []
        self.config = SimpleNamespace(model_name="deepseek-v4-flash")

    async def async_call(self, **kwargs):
        self.calls += 1
        self.requests.append(kwargs)
        if self.responses:
            content = self.responses.pop(0)
        else:
            content = "{}"
        return LLMResponse(
            content=content,
            usage=LLMUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            latency_ms=12,
        )


@pytest.fixture(autouse=True)
def _clear_aice_cache():
    service_module._page_aice_cache.clear()
    yield
    service_module._page_aice_cache.clear()


@pytest.fixture(autouse=True)
def _disable_usage_record(monkeypatch):
    async def _noop(**kwargs):
        return None

    monkeypatch.setattr(service_module, "record_llm_usage_async", _noop)


def _page_facts(**overrides):
    data = {
        "url": "https://brand.example/product",
        "final_url": "https://brand.example/product",
        "page_type": "product",
        "page_label": "产品页",
        "source_hint": "homepage_link",
        "depth": 1,
        "http_status": 200,
        "content_type": "text/html",
        "crawl_readable": True,
        "fetch_failure_reason": "",
        "title": "产品页",
        "meta_description": "产品说明",
        "has_h1": True,
        "h1_texts": ["产品页"],
        "h1_count": 1,
        "h2_texts": ["核心能力"],
        "h2_count": 1,
        "has_main": True,
        "has_article": False,
        "body_text_length": 1200,
        "body_text_excerpt": "这是一段可被引用的产品说明。",
        "script_count": 4,
        "has_noscript": False,
        "schema_types": ["Product"],
        "published_at": "2026-05-01",
    }
    data.update(overrides)
    return data


def _dimension_payload(score_overrides: dict[str, float] | None = None):
    scores = {
        "C6": 20,
        "C9a": 8,
        "C9b": 8,
        "C8": 12,
        "C1": 8,
        "C4": 8,
        "C2": 4,
        "C3": 4,
        "C5": 4,
        "C7": 4,
    }
    scores.update(score_overrides or {})
    return [
        {
            "code": code,
            "label": AICE_DIMENSION_LABELS[code],
            "score": scores[code],
            "max_score": AICE_DIMENSION_MAX_SCORES[code],
            "reason": f"{code} reason",
            "evidence": [f"{code} evidence"],
            "recommendation": {
                "priority": "P0" if code == "C6" else "P1",
                "title": f"{code} fix",
                "action": f"修复 {code}",
                "metric": f"{code} 提升",
            },
        }
        for code in AICE_DIMENSION_CODES
    ]


def _page_response(score_overrides: dict[str, float] | None = None):
    dimensions = _dimension_payload(score_overrides)
    return json.dumps(
        {
            "evaluation_mode": "AICE-Web",
            "overall_score": sum(float(item["score"]) for item in dimensions),
            "score_band": "strong",
            "dimension_scores": dimensions,
            "key_findings": ["页面结构清楚。"],
            "recommendations": ["继续补齐证据。"],
        },
        ensure_ascii=False,
    )


def _site_response(
    score_overrides: dict[str, float] | None = None,
    *,
    pages: list[dict] | None = None,
):
    dimensions = _dimension_payload(score_overrides)
    return json.dumps(
        {
            "evaluation_mode": "AICE-Web",
            "overall_score": sum(float(item["score"]) for item in dimensions),
            "score_band": "strong",
            "dimension_scores": dimensions,
            "conclusion": "官网整体可读。",
            "low_dimension_analysis": ["C9b 仍需加强。"],
            "key_findings": ["官网页面能形成判断。"],
            "prioritized_actions": [
                {
                    "priority": "P0",
                    "title": "补齐结构化数据",
                    "summary": "先处理 Schema。",
                    "target_pages": ["产品页"],
                    "dimensions": ["C9b"],
                    "metric": "C9b 提升",
                }
            ],
            "executive_summary": "官网整体可读。",
            "preview_description": "官网整体可读。",
            "report_summary": "AICE-Web 报告",
            "report_markdown": "## 结论\n\n官网整体可读。",
            "pages": pages or [],
        },
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_page_aice_json_complete_passes(monkeypatch):
    model = _FakeModel([_page_response()])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=_page_facts(),
    )

    assert model.calls == 1
    assert result["evaluation_mode"] == "AICE-Web"
    assert result["overall_score"] == 80
    assert len(result["dimension_scores"]) == 10
    assert result["metadata"]["aice_model_profile"] == "TEXT_LIGHT"
    assert result["metadata"]["cache_hit"] is False


@pytest.mark.asyncio
async def test_markdown_wrapped_json_parses_and_page_cache_hits(monkeypatch):
    model = _FakeModel([f"```json\n{_page_response()}\n```"])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )
    evaluator = AICEEvaluationService()
    facts = _page_facts()

    first = await evaluator.evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=facts,
    )
    second = await evaluator.evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=facts,
    )

    assert model.calls == 1
    assert first["overall_score"] == second["overall_score"]
    assert second["metadata"]["cache_hit"] is True


@pytest.mark.asyncio
async def test_prose_wrapped_json_object_parses(monkeypatch):
    model = _FakeModel([f"下面是 JSON 结果：\n{_page_response()}\n以上为最终结果。"])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=_page_facts(),
    )

    assert model.calls == 1
    assert result["evaluation_mode"] == "AICE-Web"
    assert result["overall_score"] == 80


@pytest.mark.asyncio
async def test_page_hard_rule_violation_retries_then_repairs(monkeypatch):
    invalid = _page_response({"C9b": 9})
    model = _FakeModel([invalid, invalid])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=_page_facts(schema_types=[]),
    )

    c9b = next(item for item in result["dimension_scores"] if item["code"] == "C9b")
    assert model.calls == 2
    assert c9b["score"] == 5
    assert result["overall_score"] == 77
    assert result["metadata"]["validator_repaired"] is True
    assert "无 Schema" in ";".join(result["metadata"]["validator_issues"])


@pytest.mark.asyncio
async def test_invalid_json_degrades_without_pretending_full_audit(monkeypatch):
    model = _FakeModel(["not json", "still not json"])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=_page_facts(),
    )

    assert model.calls == 2
    assert result["evaluation_mode"] == "AICE-Web degraded"
    assert result["metadata"]["degraded"] is True
    public_text = json.dumps(
        {
            "dimension_scores": result["dimension_scores"],
            "findings": result.get("findings", []),
            "recommended_actions": result.get("recommended_actions", []),
        },
        ensure_ascii=False,
    )
    assert "LLM不可用" not in public_text
    assert "LLM 不可用" not in public_text
    assert "降级分" not in public_text
    assert "重新运行" not in public_text


@pytest.mark.asyncio
async def test_missing_or_unknown_dimension_degrades_after_retry(monkeypatch):
    payload = json.loads(_page_response())
    payload["dimension_scores"] = payload["dimension_scores"][:-1]
    payload["dimension_scores"].append(
        {
            "code": "C10",
            "label": "unknown",
            "score": 1,
            "max_score": 1,
            "reason": "bad",
            "evidence": [],
            "recommendation": {},
        }
    )
    payload["overall_score"] = sum(
        float(item.get("score") or 0) for item in payload["dimension_scores"]
    )
    model = _FakeModel([json.dumps(payload, ensure_ascii=False)] * 2)
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_page(
        brand_name="Brand",
        root_domain="brand.example",
        page_facts=_page_facts(),
    )

    assert model.calls == 2
    assert result["evaluation_mode"] == "AICE-Web degraded"
    assert result["metadata"]["degraded"] is True


@pytest.mark.asyncio
async def test_site_aice_json_complete_passes(monkeypatch):
    model = _FakeModel([_site_response()])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_site(
        brand_name="Brand",
        root_domain="brand.example",
        root_url="https://brand.example",
        coverage_summary={"evaluated_page_count": 1},
        scan_quality_status="healthy",
        page_evaluations=[],
    )

    assert model.calls == 1
    assert result["evaluation_mode"] == "AICE-Web"
    assert result["overall_score"] == 80
    assert result["report_markdown"].startswith("## 结论")
    assert result["prioritized_actions"][0]["priority"] == "P0"


@pytest.mark.asyncio
async def test_site_with_pages_uses_one_llm_call_and_rule_precheck(monkeypatch):
    facts = _page_facts()
    model = _FakeModel(
        [
            _site_response(
                pages=[
                    {
                        "url": facts["url"],
                        "aice_evaluation": json.loads(_page_response()),
                    }
                ]
            )
        ]
    )
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_site(
        brand_name="Brand",
        root_domain="brand.example",
        root_url="https://brand.example",
        coverage_summary={"evaluated_page_count": 1},
        scan_quality_status="healthy",
        pages=[facts],
    )

    user_payload = json.loads(model.requests[0]["messages"][1]["content"])
    assert model.calls == 1
    assert model.requests[0]["max_tokens"] == 80000
    assert user_payload["evaluation_scope"] == "site_with_pages"
    assert "backend_rule_precheck" in user_payload["pages"][0]
    assert result["pages"][0]["url"] == facts["url"]
    assert result["pages"][0]["aice_evaluation"]["overall_score"] == 80
    assert (
        result["pages"][0]["aice_evaluation"]["metadata"]["evaluation_scope"]
        == "page_in_site"
    )


@pytest.mark.asyncio
async def test_site_with_pages_accepts_compact_page_output(monkeypatch):
    facts = _page_facts()
    compact_page = {
        "url": facts["url"],
        "overall_score": 80,
        "dimension_scores": {
            item["code"]: {
                "score": item["score"],
                "reason": item["reason"],
            }
            for item in _dimension_payload()
        },
    }
    model = _FakeModel([_site_response(pages=[compact_page])])
    monkeypatch.setattr(
        service_module,
        "get_text_light_llm_model",
        lambda *, task_name: model,
    )

    result = await AICEEvaluationService().evaluate_site(
        brand_name="Brand",
        root_domain="brand.example",
        root_url="https://brand.example",
        coverage_summary={"evaluated_page_count": 1},
        scan_quality_status="healthy",
        pages=[facts],
    )

    page_result = result["pages"][0]["aice_evaluation"]
    user_payload = json.loads(model.requests[0]["messages"][1]["content"])

    assert model.calls == 1
    assert "compact pages" in user_payload["output_contract"]["page_output"]
    assert result["metadata"]["validator_repaired"] is False
    assert page_result["overall_score"] == 80
    assert len(page_result["dimension_scores"]) == 10
    assert page_result["dimension_scores"][0]["label"] == AICE_DIMENSION_LABELS["C6"]
    assert page_result["dimension_scores"][0]["evidence"] == []


def test_site_confidence_page_summary_keeps_compat_fields_from_aice():
    page = DiscoveredPage(
        url="https://brand.example/product",
        page_type="product",
        source_hint="homepage_link",
        label="产品页",
        depth=1,
    )
    features = {
        "crawl_readable": True,
        "http_status": 200,
        "fetch_failure_reason": "",
        "fetched_title": "产品页",
        "meta_description": "产品说明",
        "has_h1": True,
        "h1_texts": ["产品页"],
        "h1_count": 1,
        "h2_texts": ["核心能力"],
        "h2_count": 1,
        "has_main": True,
        "has_article": False,
        "body_text_length": 1200,
        "script_count": 4,
        "schema_types": ["Product"],
        "published_at": "2026-05-01",
    }
    summary = _page_confidence_summary(
        page,
        features,
        json.loads(_page_response()),
    )

    assert summary["confidence_score"] == 80
    assert summary["aice_evaluation"]["evaluation_mode"] == "AICE-Web"
    assert len(summary["dimension_scores"]) == 10
    assert summary["dimension_scores"][0]["id"] == "C6"
    assert summary["dimension_scores"][0]["raw_score"] == 20


def test_degraded_scan_without_unreadable_pages_does_not_claim_fetch_failure():
    pages = [
        {
            "url": "https://brand.example",
            "page_type": "homepage",
            "page_label": "首页",
            "title": "首页",
            "crawl_readable": True,
            "has_h1": True,
            "has_main": True,
            "has_article": False,
            "schema_types": ["WebPage"],
            "body_text_length": 800,
            "published_at": "",
            "confidence_score": 70,
        }
    ]

    actions = _build_actions(pages, "degraded")

    assert actions[0]["title"] == "补齐本轮样本覆盖"
    assert all(action["title"] != "先修抓取失败页面" for action in actions)


def test_report_markdown_escapes_table_pipe_in_page_title():
    page = {
        "url": "https://brand.example/help.html",
        "page_type": "docs",
        "page_label": "帮助",
        "title": "品牌 | 帮助中心",
        "crawl_readable": True,
        "has_h1": False,
        "has_main": False,
        "has_article": False,
        "schema_types": [],
        "body_text_length": 24,
        "published_at": "",
        "confidence_score": 42,
        "page_status": "risk",
        "dimension_scores": [],
        "gate_scores": {"failed_gates": []},
    }

    markdown = _build_report_markdown(
        headline="官网 AI 友好度",
        root_url="https://brand.example",
        root_domain="brand.example",
        overall_score=42,
        scan_quality_status="degraded",
        coverage_summary={
            "fetched_page_count": 1,
            "evaluated_page_count": 1,
            "eligible_url_count": 1,
            "page_budget": 3,
        },
        findings=["样本有限。"],
        actions=[{"priority": "P1", "title": "补齐本轮样本覆盖", "summary": "补齐页面。"}],
        page_summaries=[page],
        dimension_summary={"dimensions": []},
    )

    assert "品牌 \\| 帮助中心" in markdown


def test_report_markdown_expands_sparse_fact_density():
    page = {
        "url": "https://brand.example/product",
        "page_type": "product",
        "page_label": "产品页",
        "title": "产品页",
        "crawl_readable": True,
        "has_h1": True,
        "has_main": True,
        "has_article": False,
        "h2_count": 0,
        "schema_types": [],
        "body_text_length": 160,
        "published_at": "",
        "confidence_score": 45,
        "page_status": "risk",
        "dimension_scores": [
            {
                "id": "C4",
                "label": "C4 证据密度",
                "score": 2,
                "raw_score": 2,
                "max_score": 10,
                "assessment": "页面事实稀疏。",
            }
        ],
        "aice_evaluation": {
            "dimension_scores": [
                {
                    "code": "C4",
                    "label": "C4 证据密度",
                    "score": 2,
                    "max_score": 10,
                    "reason": "页面事实稀疏。",
                    "recommendation": {
                        "action": "补充可引用的参数、事实、常见问答、案例或官方说明块。"
                    },
                }
            ]
        },
        "gate_scores": {"failed_gates": []},
    }

    markdown = _build_report_markdown(
        headline="官网 AI 友好度",
        root_url="https://brand.example",
        root_domain="brand.example",
        overall_score=45,
        scan_quality_status="healthy",
        coverage_summary={
            "fetched_page_count": 1,
            "evaluated_page_count": 1,
            "eligible_url_count": 1,
            "page_budget": 3,
        },
        findings=["页面事实稀疏。"],
        actions=[{"priority": "P1", "title": "补齐事实块", "summary": "补齐参数。"}],
        page_summaries=[page],
        dimension_summary={
            "dimensions": [
                {
                    "id": "C4",
                    "label": "C4 证据密度",
                    "raw_score": 2,
                    "max_score": 10,
                    "assessment": "页面事实稀疏。",
                }
            ]
        },
    )

    assert "具体稀疏在" in markdown
    assert "产品/转化页未稳定看到车型参数、价格权益、配置对比、购买流程或常见问答" in markdown
    assert "1 个页面没有结构化数据" in markdown


def test_license_page_is_excluded_from_site_discovery():
    assert (
        _classify_exclusion(
            "https://brand.example/picture/preview.html",
            "广播电视节目制作经营许可证（京）字第18667号",
        )
        == "legal"
    )


@pytest.mark.asyncio
async def test_page_feature_fetch_uses_five_second_wall_clock_timeout(monkeypatch):
    page_feature_module._page_feature_cache.clear()
    monkeypatch.setattr(page_feature_module, "PAGE_FEATURE_TIMEOUT_SECONDS", 0.01)

    class _SlowClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url):
            await asyncio.sleep(1)
            return None

    monkeypatch.setattr(page_feature_module.httpx, "AsyncClient", _SlowClient)

    result = await page_feature_module.fetch_page_features("https://slow.example")

    assert page_feature_module.PAGE_FEATURE_TIMEOUT_SECONDS == 0.01
    assert result["crawl_readable"] is False
    assert result["fetch_failure_reason"] == "request_timeout"


@pytest.mark.asyncio
async def test_discovery_supplements_news_and_product_detail_pages(monkeypatch):
    root_html = """
    <html><title>Brand</title><body>
      <a href="/news.html">媒体中心</a>
      <a href="/L7">理想L7</a>
      <a href="/privacy.html">隐私政策</a>
    </body></html>
    """
    news_html = """
    <html><title>媒体中心</title><body>
      <a href="/news/155.html">理想汽车2026年4月交付34,085辆</a>
      <a href="/news/154.html">理想汽车2026年3月交付41,053辆</a>
      <a href="/news/153.html">理想汽车2026年2月交付26,421辆</a>
      <a href="/one">理想ONE</a>
      <a href="/vis/pic/pc">VR看车</a>
    </body></html>
    """
    product_html = """
    <html><title>理想L7</title><body>
      <a href="/L7/spec.html">配置参数</a>
    </body></html>
    """

    async def _fake_fetch_html(url):
        normalized = url.rstrip("/")
        html = ""
        title = ""
        if normalized == "https://brand.example":
            html = root_html
            title = "Brand"
        elif normalized.endswith("/news.html"):
            html = news_html
            title = "媒体中心"
        elif normalized.endswith("/L7"):
            html = product_html
            title = "理想L7"
        return {
            "url": url,
            "final_url": normalized,
            "status_code": 200,
            "html": html,
            "title": title,
            "content_type": "text/html",
        }

    async def _fake_sitemap_urls(root_url, root_domain):
        return []

    monkeypatch.setattr(site_module, "_fetch_html", _fake_fetch_html)
    monkeypatch.setattr(site_module, "_fetch_sitemap_urls", _fake_sitemap_urls)

    pages, summary = await site_module.discover_site_pages(
        "https://brand.example",
        max_pages=20,
    )

    urls = [page.url for page in pages]
    assert "https://brand.example/news/155.html" in urls
    assert "https://brand.example/news/154.html" in urls
    assert "https://brand.example/news/153.html" not in urls
    assert "https://brand.example/L7/spec.html" in urls
    assert "https://brand.example/vis/pic/pc" in urls
    assert "https://brand.example/privacy.html" not in urls
    assert summary["eligible_url_count"] == len(pages)
    assert dict(summary["discovery_sources"])["news_detail_link"] == 2
    assert dict(summary["discovery_sources"])["product_detail_link"] == 2


@pytest.mark.asyncio
async def test_build_site_confidence_report_preserves_artifact_contract(monkeypatch):
    page = DiscoveredPage(
        url="https://brand.example/product",
        page_type="product",
        source_hint="homepage_link",
        label="产品页",
        depth=1,
    )

    async def _fake_discover(root_url, *, max_pages):
        return [
            page
        ], {
            "resolved_root_url": "https://brand.example",
            "root_domain": "brand.example",
            "discovered_url_count": 1,
            "candidate_url_count": 1,
            "eligible_url_count": 1,
            "max_pages_applied": max_pages,
            "excluded_url_count": 0,
            "excluded_reason_counts": {},
            "discovery_sources": {},
        }

    async def _fake_governance(**kwargs):
        return {
            "id": "crawl_governance",
            "label": "抓取治理",
            "score": 8,
            "sitemap_present": True,
            "robots_present": True,
            "blocked_key_page_count": 0,
        }

    async def _fake_features(url):
        return {
            "crawl_readable": True,
            "http_status": 200,
            "content_type": "text/html",
            "fetch_failure_reason": "",
            "fetched_title": "产品页",
            "meta_description": "产品说明",
            "has_h1": True,
            "h1_texts": ["产品页"],
            "h1_count": 1,
            "h2_texts": ["核心能力"],
            "h2_count": 1,
            "has_main": True,
            "has_article": False,
            "body_text_length": 1200,
            "body_text_excerpt": "这是一段可被引用的产品说明。",
            "script_count": 4,
            "schema_types": ["Product"],
            "published_at": "2026-05-01",
        }

    class _FakeAICE:
        static_prompt_hash = "prompt-hash"

        async def evaluate_page(self, **kwargs):
            raise AssertionError("build_site_confidence_report must not call evaluate_page")

        async def evaluate_site(self, **kwargs):
            page_results = [
                {
                    "url": page["url"],
                    "aice_evaluation": json.loads(_page_response()),
                }
                for page in kwargs.get("pages", [])
            ]
            result = json.loads(_site_response(pages=page_results))
            result["metadata"] = {
                "model_name": "deepseek-v4-flash",
                "static_prompt_hash": "prompt-hash",
                "cache_hit": False,
                "validator_repaired": False,
                "degraded": False,
                "validator_issues": [],
            }
            for page in result["pages"]:
                page["aice_evaluation"]["metadata"] = result["metadata"]
            return result

    monkeypatch.setattr(site_module, "discover_site_pages", _fake_discover)
    monkeypatch.setattr(site_module, "_inspect_crawl_governance", _fake_governance)
    monkeypatch.setattr(site_module, "fetch_page_features", _fake_features)
    monkeypatch.setattr(site_module, "AICEEvaluationService", _FakeAICE)

    report = await build_site_confidence_report(
        root_url="https://brand.example",
        brand_name="Brand",
        session_id="session-1",
        task_id="task-1",
    )

    assert report["report_kind"] == "site_confidence_report"
    assert report["artifact_kind"] == "site_confidence_report"
    assert report["evaluation_mode"] == "AICE-Web"
    assert report["aice_prompt_version"] == "aice_web_v1"
    assert report["aice_model_profile"] == "TEXT_LIGHT"
    assert report["aice_model_name"] == "deepseek-v4-flash"
    assert report["aice_static_prompt_hash"] == "prompt-hash"
    assert report["overall_score"] == 80
    assert report["pages"][0]["aice_evaluation"]["overall_score"] == 80
    assert report["report_markdown"].startswith("## 结论")
    assert "## AICE 9C 评分矩阵" not in report["report_markdown"]
    assert "| 评分项 | 得分 | 判断 |" not in report["report_markdown"]
    assert "## 直接证据：显著影响评分的页面" in report["report_markdown"]
    assert "## 附录：本轮纳入评估的页面" in report["report_markdown"]
    assert "站点总分 = 本轮纳入评估页面的单页分数平均值" not in report["report_markdown"]
    assert "Semantic Tagging" not in report["report_markdown"]
