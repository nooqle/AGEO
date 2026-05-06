"""LLM-backed domain intelligence skill for A4 citation enrichment."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.core.domain_normalization import normalize_domain
from app.core.llm.task_routing import get_text_light_llm_model

logger = logging.getLogger(__name__)

SKILL_KEY = "url_intelligence_skill"
UNKNOWN_SITE_NAME = "缺乏特征，无法识别"
UNKNOWN_CATEGORY = "缺乏特征，无法识别"


@dataclass(frozen=True)
class DomainIntelligenceResult:
    domain: str
    site_name: str
    category: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "skill_key": SKILL_KEY,
            "domain": self.domain,
            "site_name": self.site_name,
            "category": self.category,
        }


URLIntelligenceResult = DomainIntelligenceResult


class URLIntelligenceSkill:
    """Analyze citation domains with a single compact LLM call."""

    def __init__(self, *, batch_size: int | None = None):
        del batch_size

    async def analyze_domains(
        self,
        domains: list[str],
    ) -> dict[str, DomainIntelligenceResult]:
        normalized_domains = _dedupe_domains(domains)
        if not normalized_domains:
            return {}

        try:
            return await self._analyze_domains_once(normalized_domains)
        except Exception as exc:
            logger.warning(
                "[%s] domain analysis failed; using unknown fallback for %d domains: %s",
                SKILL_KEY,
                len(normalized_domains),
                exc,
            )
            return {domain: _unknown_result(domain) for domain in normalized_domains}

    async def analyze_urls(
        self,
        urls: list[str],
    ) -> dict[str, DomainIntelligenceResult]:
        """Compatibility wrapper for callers that still pass URLs."""

        domains = [domain for item in urls if (domain := normalize_domain(item))]
        return await self.analyze_domains(domains)

    async def _analyze_domains_once(
        self,
        domains: list[str],
    ) -> dict[str, DomainIntelligenceResult]:
        settings = get_settings()
        model = _get_url_intelligence_model()
        token_budget = max(500, min(3000, 60 * len(domains)))
        rows = await _call_and_parse_domain_mapping(
            model=model,
            domains=domains,
            token_budgets=[
                token_budget,
                min(6000, max(token_budget * 2, token_budget + 1000)),
            ],
            timeout_seconds=float(
                getattr(settings, "URL_INTELLIGENCE_TIMEOUT_SECONDS", 45.0) or 45.0
            ),
        )
        parsed: dict[str, DomainIntelligenceResult] = {}
        for raw_domain, value in rows.items():
            domain = normalize_domain(raw_domain)
            if not domain:
                continue
            parsed[domain] = _coerce_mapping_result(domain, value)
        for domain in domains:
            parsed.setdefault(domain, _unknown_result(domain))
        return parsed


def _get_url_intelligence_model() -> Any:
    return get_text_light_llm_model(task_name=SKILL_KEY)


async def _call_and_parse_domain_mapping(
    *,
    model: Any,
    domains: list[str],
    token_budgets: list[int],
    timeout_seconds: float,
) -> dict[str, Any]:
    last_error: Exception | None = None
    for index, max_tokens in enumerate(token_budgets):
        response = await model.async_call(
            messages=[
                {
                    "role": "system",
                    "content": _SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "skill_key": SKILL_KEY,
                            "input_domains": domains,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            thinking_enabled=False,
            timeout=timeout_seconds,
        )
        try:
            return _parse_domain_mapping(str(response.content or ""))
        except (json.JSONDecodeError, ValueError) as exc:
            last_error = exc
            if index < len(token_budgets) - 1:
                logger.warning(
                    "[%s] invalid JSON response, retrying once with larger budget: %s",
                    SKILL_KEY,
                    exc,
                )
                continue
    raise ValueError("Domain intelligence response JSON parse failed") from last_error


def _dedupe_domains(domains: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for raw in domains:
        domain = normalize_domain(str(raw or ""))
        if not domain or domain in seen:
            continue
        deduped.append(domain)
        seen.add(domain)
    return deduped


def _coerce_mapping_result(domain: str, value: Any) -> DomainIntelligenceResult:
    site_name = ""
    category = ""
    if isinstance(value, dict):
        site_name = str(value.get("site_name") or "").strip()
        category = str(value.get("category") or "").strip()
    elif isinstance(value, (list, tuple)):
        if len(value) >= 1:
            site_name = str(value[0] or "").strip()
        if len(value) >= 2:
            category = str(value[1] or "").strip()
    if not site_name:
        site_name = UNKNOWN_SITE_NAME
    if not category:
        category = UNKNOWN_CATEGORY
    return DomainIntelligenceResult(
        domain=domain,
        site_name=site_name,
        category=category,
    )


def _unknown_result(domain: str) -> DomainIntelligenceResult:
    return DomainIntelligenceResult(
        domain=domain,
        site_name=UNKNOWN_SITE_NAME,
        category=UNKNOWN_CATEGORY,
    )


def _parse_domain_mapping(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("Domain intelligence response is not a JSON object")
    return data


_SYSTEM_PROMPT = """# Role: Domain Intelligence Analyst (网站情报分析专家)

## Task
你负责仅根据 domain 快速识别网站实体和网站类型。

## Rules
1. 严禁虚构：如果 domain 缺乏有效特征，请返回“缺乏特征，无法识别”。
2. 优先识别已知互联网实体，例如媒体、社交平台、电商、政府、高校、品牌官网、医疗健康站点。
3. 只输出 site_name 和 category 两个识别值，不要输出解释、置信度或长描述。
4. 输出对象的 key 必须是输入 domain 原文。

## 分类定义
- 电商平台：综合电商、平台店铺、导购跳转、联盟返利、平台精选页。
- 消费社区：用户评测、导购内容、消费经验、折扣爆料、社区帖子。
- 内容平台：公众号、短视频、资讯、图文内容分发平台。

## 示例
- jd.com -> ["京东", "电商平台"]
- jingfen.jd.com -> ["京东", "电商平台"]
- smzdm.com -> ["什么值得买", "消费社区"]
- post.smzdm.com -> ["什么值得买", "消费社区"]
- mp.weixin.qq.com -> ["微信公众号", "内容平台"]
- uland.taobao.com -> ["淘宝", "电商平台"]

## Output Format
请严格返回 JSON object，不可包含其他解释性文字：
{
  "example.com": ["网站名", "行业/功能分类"]
}
"""
