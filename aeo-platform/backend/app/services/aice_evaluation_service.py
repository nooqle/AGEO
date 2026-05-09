"""Internal AICE-Web 9C LLM evaluation service."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import json
import logging
import re
import time
from typing import Any

from app.core.llm import BaseLLMModel, LLMResponse
from app.core.llm.task_routing import get_text_light_llm_model
from app.core.utils import repair_truncated_json
from app.services.aice_prompt_contract import (
    AICE_DIMENSION_CODES,
    AICE_DIMENSION_LABELS,
    AICE_DIMENSION_MAX_SCORES,
    AICE_MODEL_PROFILE,
    AICE_WEB_EVALUATION_MODE,
    AICE_WEB_PROMPT_VERSION,
    build_aice_web_system_prompt,
    build_page_evaluation_payload,
    build_site_evaluation_payload,
    stable_json,
)
from app.services.llm_usage_service import record_llm_usage_async
from app.workflow.prompt_fingerprint import fingerprint_text

logger = logging.getLogger(__name__)

PAGE_AICE_CACHE_TTL_SECONDS = 1800
PAGE_AICE_CACHE_MAX_ENTRIES = 512
SITE_AICE_MAX_TOKENS = 80000

_PUBLIC_REPORT_FORBIDDEN_PATTERNS: tuple[str, ...] = (
    "LLM不可用",
    "LLM 不可用",
    "LLM审核降级",
    "LLM 审核降级",
    "降级模式",
    "后端降级",
    "后端规则",
    "后端事实",
    "重新运行完整AICE审核",
    "重新运行完整 AICE 审核",
    "实际分数可能偏低",
)

_PUBLIC_REPORT_EMOJI_RE = re.compile(
    r"[\U0001f300-\U0001faff\u2600-\u27bf]",
    flags=re.UNICODE,
)

_SITE_SCORE_TEXT_RE = re.compile(
    r"(?:评分为|总分|综合评分|评分)\s*(\d+(?:\.\d+)?)\s*(?:分|/ ?100)?"
)

_page_aice_cache: dict[str, tuple[float, dict[str, Any]]] = {}


class AICEValidationError(ValueError):
    """Raised when an AICE LLM payload violates the contract."""

    def __init__(self, issues: list[str]):
        self.issues = [str(issue) for issue in issues if str(issue).strip()]
        super().__init__("; ".join(self.issues) or "AICE validation failed")


@dataclass(frozen=True)
class AICECallContext:
    session_id: str | None = None
    task_id: str | None = None
    skill_key: str = "site_confidence_assessment_skill"


class AICEEvaluationService:
    """LLM-backed AICE-Web evaluator with validation and page-result cache."""

    def __init__(self) -> None:
        self.system_prompt = build_aice_web_system_prompt()
        self.static_prompt_hash = fingerprint_text(self.system_prompt)

    def build_page_rule_precheck(self, page_facts: dict[str, Any]) -> dict[str, Any]:
        dimensions = self._fallback_dimensions_from_page(page_facts)
        score = round(sum(float(item["score"]) for item in dimensions), 1)
        crawl_readable = bool(page_facts.get("crawl_readable"))
        has_h1 = bool(page_facts.get("has_h1"))
        has_semantic_root = bool(
            page_facts.get("has_main") or page_facts.get("has_article")
        )
        has_schema = bool(page_facts.get("schema_types") or [])
        return {
            "rule_mode": "backend_precheck",
            "precheck_score": score,
            "hard_rules": {
                "c6_must_be_zero": not crawl_readable,
                "c9a_max_score": 5 if (not has_h1 or not has_semantic_root) else 10,
                "c9b_max_score": 5 if not has_schema else 10,
            },
            "dimension_scores": dimensions,
        }

    async def evaluate_page(
        self,
        *,
        brand_name: str,
        root_domain: str,
        page_facts: dict[str, Any],
        context: AICECallContext | None = None,
    ) -> dict[str, Any]:
        context = context or AICECallContext()
        try:
            model = get_text_light_llm_model(task_name="aice_web_evaluation")
        except Exception as exc:
            logger.warning("[AICE-Web] page model unavailable: %s", exc)
            return self._fallback_page_evaluation(page_facts, f"model_unavailable:{exc}")

        model_identity = self._model_identity(model)
        cache_key = self._page_cache_key(page_facts, model_identity)
        cached = self._read_page_cache(cache_key)
        if cached is not None:
            cached.setdefault("metadata", {})
            cached["metadata"]["cache_hit"] = True
            cached["metadata"]["cache_key"] = cache_key
            return cached

        validator_issues: list[str] = []
        last_raw: dict[str, Any] | None = None
        for attempt in range(1, 3):
            payload = build_page_evaluation_payload(
                brand_name=brand_name,
                root_domain=root_domain,
                page=page_facts,
                validator_issues=validator_issues,
            )
            try:
                raw = await self._call_llm_json(
                    model=model,
                    payload=payload,
                    context=context,
                    evaluation_scope="page",
                    cache_key=cache_key,
                    max_tokens=6000,
                )
                last_raw = raw
                normalized = self._normalize_page_evaluation(
                    raw,
                    page_facts=page_facts,
                    repair=False,
                )
                self._attach_metadata(
                    normalized,
                    model=model,
                    model_identity=model_identity,
                    cache_key=cache_key,
                    evaluation_scope="page",
                    attempts=attempt,
                    validator_issues=[],
                    repaired=False,
                    cache_hit=False,
                )
                self._write_page_cache(cache_key, normalized)
                return normalized
            except AICEValidationError as exc:
                validator_issues = exc.issues
                logger.warning("[AICE-Web] page validation retry %s: %s", attempt, exc)
            except Exception as exc:
                validator_issues = [str(exc)]
                logger.warning("[AICE-Web] page call retry %s failed: %s", attempt, exc)

        if last_raw is not None:
            try:
                repaired = self._normalize_page_evaluation(
                    last_raw,
                    page_facts=page_facts,
                    repair=True,
                )
                self._attach_metadata(
                    repaired,
                    model=model,
                    model_identity=model_identity,
                    cache_key=cache_key,
                    evaluation_scope="page",
                    attempts=2,
                    validator_issues=validator_issues,
                    repaired=True,
                    cache_hit=False,
                )
                self._write_page_cache(cache_key, repaired)
                return repaired
            except Exception as exc:
                validator_issues.append(str(exc))

        return self._fallback_page_evaluation(
            page_facts,
            "llm_unavailable_or_invalid:" + ";".join(validator_issues),
        )

    async def evaluate_site(
        self,
        *,
        brand_name: str,
        root_domain: str,
        root_url: str,
        coverage_summary: dict[str, Any],
        scan_quality_status: str,
        pages: list[dict[str, Any]] | None = None,
        page_evaluations: list[dict[str, Any]] | None = None,
        context: AICECallContext | None = None,
    ) -> dict[str, Any]:
        context = context or AICECallContext()
        page_facts = [dict(page) for page in (pages or page_evaluations or [])]
        prechecked_pages = [
            {
                **page,
                "backend_rule_precheck": self.build_page_rule_precheck(page),
            }
            for page in page_facts
        ]
        try:
            model = get_text_light_llm_model(task_name="aice_web_evaluation")
        except Exception as exc:
            logger.warning("[AICE-Web] site model unavailable: %s", exc)
            return self._fallback_site_evaluation(
                brand_name=brand_name,
                root_domain=root_domain,
                pages=page_facts,
                reason=f"model_unavailable:{exc}",
        )

        model_identity = self._model_identity(model)
        validator_issues: list[str] = []
        payload = build_site_evaluation_payload(
            brand_name=brand_name,
            root_domain=root_domain,
            root_url=root_url,
            coverage_summary=coverage_summary,
            scan_quality_status=scan_quality_status,
            pages=prechecked_pages,
            validator_issues=validator_issues,
        )
        try:
            raw = await self._call_llm_json(
                model=model,
                payload=payload,
                context=context,
                evaluation_scope="site_with_pages",
                cache_key=None,
                max_tokens=SITE_AICE_MAX_TOKENS,
            )
            try:
                normalized = self._normalize_site_evaluation(
                    raw,
                    page_facts=page_facts,
                    repair=False,
                )
                self._attach_metadata(
                    normalized,
                    model=model,
                    model_identity=model_identity,
                    cache_key=None,
                    evaluation_scope="site_with_pages",
                    attempts=1,
                    validator_issues=[],
                    repaired=False,
                    cache_hit=False,
                )
                return normalized
            except AICEValidationError as exc:
                validator_issues = exc.issues
                logger.warning(
                    "[AICE-Web] site validation repaired without LLM retry: %s",
                    exc,
                )
                repaired = self._normalize_site_evaluation(
                    raw,
                    page_facts=page_facts,
                    repair=True,
                )
                self._attach_metadata(
                    repaired,
                    model=model,
                    model_identity=model_identity,
                    cache_key=None,
                    evaluation_scope="site_with_pages",
                    attempts=1,
                    validator_issues=validator_issues,
                    repaired=True,
                    cache_hit=False,
                )
                return repaired
        except Exception as exc:
            validator_issues.append(str(exc))
            logger.warning("[AICE-Web] site call failed: %s", exc)

        return self._fallback_site_evaluation(
            brand_name=brand_name,
            root_domain=root_domain,
            pages=page_facts,
            reason="llm_unavailable_or_invalid:" + ";".join(validator_issues),
        )

    async def _call_llm_json(
        self,
        *,
        model: BaseLLMModel,
        payload: dict[str, Any],
        context: AICECallContext,
        evaluation_scope: str,
        cache_key: str | None,
        max_tokens: int,
    ) -> dict[str, Any]:
        response: LLMResponse = await model.async_call(
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": stable_json(payload)},
            ],
            temperature=0,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
            thinking_enabled=False,
            timeout=90,
        )
        await record_llm_usage_async(
            session_id=context.session_id,
            task_id=context.task_id,
            skill_key=context.skill_key,
            step="A7",
            step_name="官网 AI 友好度",
            model=model,
            usage=response.usage,
            latency_ms=response.latency_ms,
            extra_metadata={
                "prompt_version": AICE_WEB_PROMPT_VERSION,
                "static_prompt_hash": self.static_prompt_hash,
                "cache_key": cache_key,
                "evaluation_scope": evaluation_scope,
                "aice_model_profile": AICE_MODEL_PROFILE,
            },
        )
        content = response.content
        parsed = (
            content
            if isinstance(content, dict)
            else self._parse_json_response(str(content or ""))
        )
        if not isinstance(parsed, dict):
            raise AICEValidationError(
                [
                    "LLM 输出不是可解析的 JSON object"
                    f" (finish_reason={response.finish_reason or 'unknown'},"
                    f" chars={len(str(content or ''))})"
                ]
            )
        return parsed

    def _parse_json_response(self, content: str) -> dict[str, Any] | None:
        text = str(content or "").strip()
        if not text:
            return None

        for candidate in self._json_response_candidates(text):
            if not candidate:
                continue
            for payload in (candidate, repair_truncated_json(candidate)):
                if not payload:
                    continue
                try:
                    parsed = json.loads(payload)
                except json.JSONDecodeError:
                    continue
                if isinstance(parsed, dict):
                    return parsed
        return None

    def _json_response_candidates(self, text: str) -> list[str]:
        candidates: list[str] = []
        seen: set[str] = set()

        def add(value: str | None) -> None:
            candidate = str(value or "").strip()
            if not candidate or candidate in seen:
                return
            seen.add(candidate)
            candidates.append(candidate)

        add(text)
        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].strip().startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            add("\n".join(lines).strip())

        for match in re.finditer(
            r"```(?:json)?\s*(.*?)```",
            text,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            add(match.group(1))

        for candidate in self._json_object_candidates(text):
            add(candidate)
            if len(candidates) >= 8:
                break

        return candidates

    @staticmethod
    def _json_object_candidates(text: str) -> list[str]:
        candidates: list[str] = []
        for start_match in re.finditer(r"\{", text):
            start = start_match.start()
            depth = 0
            in_string = False
            escape_next = False
            for index in range(start, len(text)):
                char = text[index]
                if escape_next:
                    escape_next = False
                    continue
                if char == "\\" and in_string:
                    escape_next = True
                    continue
                if char == '"':
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if char == "{":
                    depth += 1
                    continue
                if char == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : index + 1])
                        break
            else:
                candidates.append(text[start:])
            if len(candidates) >= 4:
                break
        return candidates

    def _normalize_page_evaluation(
        self,
        raw: dict[str, Any],
        *,
        page_facts: dict[str, Any],
        repair: bool,
    ) -> dict[str, Any]:
        result = self._normalize_common_evaluation(raw, repair=repair)
        self._validate_page_hard_rules(result, page_facts, repair=repair)
        return result

    def _normalize_site_evaluation(
        self,
        raw: dict[str, Any],
        *,
        page_facts: list[dict[str, Any]],
        repair: bool,
    ) -> dict[str, Any]:
        site_raw = (
            raw.get("site_evaluation")
            if isinstance(raw.get("site_evaluation"), dict)
            else raw
        )
        result = self._normalize_common_evaluation(site_raw, repair=repair)
        raw_pages = raw.get("pages")
        if raw_pages is None:
            raw_pages = site_raw.get("pages")
        if raw_pages is None:
            raw_pages = raw.get("page_evaluations")
        result["pages"] = self._normalize_site_page_evaluations(
            raw_pages,
            page_facts=page_facts,
            repair=repair,
        )
        result["conclusion"] = str(site_raw.get("conclusion") or "").strip()
        result["low_dimension_analysis"] = self._string_list(
            site_raw.get("low_dimension_analysis")
        )
        result["key_findings"] = self._string_list(site_raw.get("key_findings"))
        result["prioritized_actions"] = self._normalize_actions(
            site_raw.get("prioritized_actions")
        )
        result["executive_summary"] = str(
            site_raw.get("executive_summary") or ""
        ).strip()
        result["preview_description"] = str(
            site_raw.get("preview_description") or ""
        ).strip()
        result["report_summary"] = str(site_raw.get("report_summary") or "").strip()
        result["report_markdown"] = str(site_raw.get("report_markdown") or "").strip()

        issues: list[str] = []
        if len(result["pages"]) != len(page_facts):
            issues.append("官网级 pages 数量与输入页面数量不一致")
        if not result["report_markdown"]:
            issues.append("官网级 report_markdown 为空")
        if not result["prioritized_actions"]:
            issues.append("官网级 prioritized_actions 为空")
        issues.extend(self._validate_public_site_text(result))
        if issues and not repair:
            raise AICEValidationError(issues)
        if repair:
            if not result["report_markdown"]:
                result["report_markdown"] = self._build_minimal_site_markdown(result)
            if not result["prioritized_actions"]:
                result["prioritized_actions"] = self._actions_from_dimensions(result)
            self._repair_public_site_text(result)
        return result

    def _normalize_site_page_evaluations(
        self,
        raw_pages: Any,
        *,
        page_facts: list[dict[str, Any]],
        repair: bool,
    ) -> list[dict[str, Any]]:
        issues: list[str] = []
        if not isinstance(raw_pages, list):
            if page_facts and not repair:
                raise AICEValidationError(["官网级 pages 必须是数组"])
            raw_pages = []

        by_url: dict[str, dict[str, Any]] = {}
        indexed: list[dict[str, Any]] = []
        for item in raw_pages:
            if not isinstance(item, dict):
                issues.append("pages 中存在非 object 项")
                continue
            indexed.append(item)
            url = str(item.get("url") or "").strip()
            if url:
                by_url[url] = item

        normalized_pages: list[dict[str, Any]] = []
        for index, facts in enumerate(page_facts):
            url = str(facts.get("url") or facts.get("final_url") or "").strip()
            raw_page = by_url.get(url)
            if raw_page is None and index < len(indexed):
                raw_page = indexed[index]
            raw_evaluation = self._extract_page_aice_payload(raw_page)
            if not raw_evaluation:
                issue = f"页面 {url or index} 缺少 aice_evaluation"
                issues.append(issue)
                if repair:
                    normalized = self._fallback_page_evaluation(facts, issue)
                else:
                    continue
            else:
                try:
                    normalized = self._normalize_page_evaluation(
                        raw_evaluation,
                        page_facts=facts,
                        repair=repair,
                    )
                except AICEValidationError as exc:
                    prefixed = [
                        f"页面 {url or index}: {issue}" for issue in exc.issues
                    ]
                    issues.extend(prefixed)
                    if repair:
                        try:
                            normalized = self._normalize_page_evaluation(
                                raw_evaluation,
                                page_facts=facts,
                                repair=True,
                            )
                        except Exception:
                            normalized = self._fallback_page_evaluation(
                                facts,
                                ";".join(prefixed),
                            )
                    else:
                        continue
            normalized_pages.append(
                {
                    "url": url,
                    "aice_evaluation": normalized,
                }
            )

        if issues and not repair:
            raise AICEValidationError(issues)
        return normalized_pages

    @staticmethod
    def _extract_page_aice_payload(raw_page: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(raw_page, dict):
            return {}
        nested = raw_page.get("aice_evaluation")
        if isinstance(nested, dict):
            return AICEEvaluationService._expand_compact_evaluation_payload(nested)
        if isinstance(raw_page.get("dimension_scores"), (dict, list)):
            return AICEEvaluationService._expand_compact_evaluation_payload(raw_page)
        return {}

    @staticmethod
    def _expand_compact_evaluation_payload(raw: dict[str, Any]) -> dict[str, Any]:
        payload = dict(raw)
        dimensions = payload.get("dimension_scores")
        if isinstance(dimensions, dict):
            expanded = AICEEvaluationService._dimension_dict_to_list(dimensions)
            payload["dimension_scores"] = expanded
            if payload.get("overall_score") in (None, ""):
                payload["overall_score"] = round(
                    sum(
                        AICEEvaluationService._coerce_float(item.get("score"), 0.0)
                        for item in expanded
                    ),
                    1,
                )
        return payload

    def _normalize_common_evaluation(
        self,
        raw: dict[str, Any],
        *,
        repair: bool,
    ) -> dict[str, Any]:
        issues: list[str] = []
        dimensions = self._normalize_dimensions(raw.get("dimension_scores"), issues)
        score = self._optional_float(raw.get("overall_score"))
        expected_score = round(sum(float(item["score"]) for item in dimensions), 1)
        if score is None:
            issues.append("overall_score 缺失或不是数字")
            score = expected_score if repair else 0.0
        score = round(max(0.0, min(100.0, float(score))), 1)
        if abs(score - expected_score) > 0.1:
            issues.append(
                f"overall_score {score} 不等于维度求和 {expected_score}"
            )
            if repair:
                score = expected_score
        if issues and not repair:
            raise AICEValidationError(issues)
        return {
            "evaluation_mode": AICE_WEB_EVALUATION_MODE,
            "overall_score": score,
            "score_band": self._score_band(score),
            "dimension_scores": dimensions,
            "key_findings": self._string_list(raw.get("key_findings")),
            "recommendations": self._string_list(raw.get("recommendations")),
        }

    def _normalize_dimensions(
        self,
        raw_dimensions: Any,
        issues: list[str],
    ) -> list[dict[str, Any]]:
        if isinstance(raw_dimensions, dict):
            raw_dimensions = self._dimension_dict_to_list(raw_dimensions)
        if not isinstance(raw_dimensions, list):
            raise AICEValidationError(["dimension_scores 必须是数组"])
        seen: set[str] = set()
        normalized: list[dict[str, Any]] = []
        for item in raw_dimensions:
            if not isinstance(item, dict):
                issues.append("dimension_scores 中存在非 object 项")
                continue
            code = str(item.get("code") or "").strip()
            if code not in AICE_DIMENSION_CODES:
                issues.append(f"未知维度：{code or '<empty>'}")
                continue
            if code in seen:
                issues.append(f"重复维度：{code}")
                continue
            seen.add(code)
            max_score = AICE_DIMENSION_MAX_SCORES[code]
            score = self._coerce_float(item.get("score"), 0.0)
            if score < 0 or score > max_score:
                issues.append(f"{code} 分数 {score} 超出 0..{max_score}")
            score = round(max(0.0, min(float(max_score), score)), 1)
            recommendation = item.get("recommendation") or {}
            if not isinstance(recommendation, dict):
                recommendation = {}
            normalized.append(
                {
                    "code": code,
                    "label": AICE_DIMENSION_LABELS[code],
                    "score": score,
                    "max_score": max_score,
                    "reason": str(item.get("reason") or "").strip(),
                    "evidence": self._string_list(item.get("evidence"))[:5],
                    "recommendation": {
                        "priority": str(
                            recommendation.get("priority") or "P1"
                        ).upper(),
                        "title": str(recommendation.get("title") or "").strip(),
                        "action": str(recommendation.get("action") or "").strip(),
                        "metric": str(recommendation.get("metric") or "").strip(),
                    },
                }
            )
        missing = [code for code in AICE_DIMENSION_CODES if code not in seen]
        if missing:
            issues.append(f"缺失维度：{','.join(missing)}")
        if issues:
            raise AICEValidationError(issues)
        normalized.sort(key=lambda item: AICE_DIMENSION_CODES.index(item["code"]))
        return normalized

    @staticmethod
    def _dimension_dict_to_list(raw_dimensions: dict[str, Any]) -> list[dict[str, Any]]:
        dimensions: list[dict[str, Any]] = []
        for code, raw_value in raw_dimensions.items():
            if isinstance(raw_value, dict):
                score = raw_value.get("score")
                reason = str(raw_value.get("reason") or "").strip()
            else:
                score = raw_value
                reason = ""
            dimensions.append(
                {
                    "code": str(code),
                    "score": score,
                    "max_score": AICE_DIMENSION_MAX_SCORES.get(str(code)),
                    "reason": reason,
                }
            )
        return dimensions

    def _validate_page_hard_rules(
        self,
        result: dict[str, Any],
        page_facts: dict[str, Any],
        *,
        repair: bool,
    ) -> None:
        issues: list[str] = []
        dimensions = {item["code"]: item for item in result.get("dimension_scores") or []}
        crawl_readable = bool(page_facts.get("crawl_readable"))
        has_h1 = bool(page_facts.get("has_h1"))
        has_semantic_root = bool(
            page_facts.get("has_main") or page_facts.get("has_article")
        )
        has_schema = bool(page_facts.get("schema_types") or [])

        if not crawl_readable and float(dimensions["C6"]["score"]) != 0.0:
            issues.append("crawl_readable=false 时 C6 必须为 0")
            if repair:
                dimensions["C6"]["score"] = 0.0
        if (not has_h1 or not has_semantic_root) and float(
            dimensions["C9a"]["score"]
        ) > 5:
            issues.append("缺 H1 或缺 main/article 时 C9a 最高为 5")
            if repair:
                dimensions["C9a"]["score"] = 5.0
        if not has_schema and float(dimensions["C9b"]["score"]) > 5:
            issues.append("无 Schema 时 C9b 最高为 5")
            if repair:
                dimensions["C9b"]["score"] = 5.0
        if issues and not repair:
            raise AICEValidationError(issues)
        if repair and issues:
            score = round(
                sum(float(item["score"]) for item in result["dimension_scores"]), 1
            )
            result["overall_score"] = score
            result["score_band"] = self._score_band(score)

    def _fallback_page_evaluation(
        self,
        page_facts: dict[str, Any],
        reason: str,
    ) -> dict[str, Any]:
        dimensions = self._fallback_dimensions_from_page(page_facts)
        score = round(sum(float(item["score"]) for item in dimensions), 1)
        result = {
            "evaluation_mode": "AICE-Web degraded",
            "overall_score": score,
            "score_band": self._score_band(score),
            "dimension_scores": dimensions,
            "key_findings": [
                "本页 AICE LLM 审核不可用，当前只保留后端事实抽取和硬规则降级结果。"
            ],
            "recommendations": [
                "重新运行官网 AI 友好度审核，确认 LLM 页面级评分和建议。"
            ],
        }
        result["metadata"] = self._base_metadata(
            provider="TEXT_LIGHT",
            model_name="unavailable",
            cache_key=None,
            evaluation_scope="page",
            attempts=0,
            validator_issues=[reason],
            repaired=False,
            cache_hit=False,
            degraded=True,
        )
        return result

    def _fallback_site_evaluation(
        self,
        *,
        brand_name: str,
        root_domain: str,
        pages: list[dict[str, Any]],
        reason: str,
    ) -> dict[str, Any]:
        page_results = [
            {
                "url": str(page.get("url") or page.get("final_url") or ""),
                "aice_evaluation": self._fallback_page_evaluation(page, reason),
            }
            for page in pages
        ]
        dimensions = self._average_site_dimensions(page_results)
        score = round(sum(float(item["score"]) for item in dimensions), 1)
        report_markdown = (
            "## 结论\n\n"
            f"本次官网 AI 友好度进入降级模式，当前只保留页面事实抽取和硬规则校验结果。"
            f"降级原因：{reason}。\n\n"
            "## 下一步\n\n"
            "重新运行官网 AI 友好度审核，确保 AICE-Web 9C 的页面级评分、官网级结论和 P0/P1 建议由 LLM 完成。"
        )
        result = {
            "evaluation_mode": "AICE-Web degraded",
            "overall_score": score,
            "score_band": self._score_band(score),
            "dimension_scores": dimensions,
            "conclusion": "AICE LLM 官网级审核不可用，本次结果不能视为完整审核。",
            "low_dimension_analysis": [],
            "key_findings": [
                "官网级 AICE LLM 审核不可用，报告处于降级模式。"
            ],
            "prioritized_actions": [
                {
                    "priority": "P0",
                    "title": "重新运行 AICE-Web 审核",
                    "summary": "恢复 LLM 页面级评分和官网级建议后，再使用该报告做决策。",
                    "target_pages": [root_domain or brand_name],
                    "dimensions": list(AICE_DIMENSION_CODES),
                    "metric": "报告 evaluation_mode 恢复为 AICE-Web。",
                }
            ],
            "executive_summary": "本次只产出降级结果，不能代替完整 AICE-Web 审核。",
            "preview_description": "AICE-Web LLM 审核不可用，本次为降级报告。",
            "report_summary": "降级报告",
            "report_markdown": report_markdown,
            "pages": page_results,
        }
        result["metadata"] = self._base_metadata(
            provider="TEXT_LIGHT",
            model_name="unavailable",
            cache_key=None,
            evaluation_scope="site_with_pages",
            attempts=0,
            validator_issues=[reason],
            repaired=False,
            cache_hit=False,
            degraded=True,
        )
        return result

    def _fallback_dimensions_from_page(
        self,
        page_facts: dict[str, Any],
    ) -> list[dict[str, Any]]:
        body_length = int(page_facts.get("body_text_length") or 0)
        crawl_readable = bool(page_facts.get("crawl_readable"))
        has_h1 = bool(page_facts.get("has_h1"))
        has_semantic_root = bool(
            page_facts.get("has_main") or page_facts.get("has_article")
        )
        has_schema = bool(page_facts.get("schema_types") or [])
        has_time = bool(page_facts.get("published_at"))
        https = str(page_facts.get("url") or "").startswith("https://")

        raw_scores = {
            "C6": 0 if not crawl_readable else 20 if body_length >= 180 else 12,
            "C9a": 8 if has_h1 and has_semantic_root else 5 if has_h1 or has_semantic_root else 2,
            "C9b": 8 if has_schema else 5,
            "C8": 12 if has_time else 8,
            "C1": 6 if crawl_readable else 3,
            "C4": 7 if body_length >= 800 else 5 if body_length >= 180 else 2,
            "C2": 4 if page_facts.get("title") else 2,
            "C3": 3 if body_length >= 180 else 1,
            "C5": 4 if has_h1 and body_length >= 180 else 2,
            "C7": 4 if https else 2,
        }
        fallback_reason = (
            "页面默认抓取不可读，无法可靠判断该项。"
            if not crawl_readable
            else "本页可抽取信息不足，当前只能按已抓取页面事实保守判断。"
        )
        fallback_recommendation = (
            {
                "priority": "P0",
                "title": "恢复页面默认可读性",
                "action": "排查页面返回状态、重定向、超时和访问限制，确保默认抓取能拿到 200 正文。",
                "metric": "页面返回 200 且正文可被稳定抓取。",
            }
            if not crawl_readable
            else {
                "priority": "P1",
                "title": "补充可判断的页面事实",
                "action": "补充清晰标题、正文结构、关键事实、常见问答和结构化数据，降低机器判断的不确定性。",
                "metric": "页面正文、语义标签和结构化事实可以被稳定抽取。",
            }
        )
        dimensions: list[dict[str, Any]] = []
        for code in AICE_DIMENSION_CODES:
            score = round(
                max(0.0, min(float(AICE_DIMENSION_MAX_SCORES[code]), raw_scores[code])),
                1,
            )
            dimensions.append(
                {
                    "code": code,
                    "label": AICE_DIMENSION_LABELS[code],
                    "score": score,
                    "max_score": AICE_DIMENSION_MAX_SCORES[code],
                    "reason": fallback_reason,
                    "evidence": [],
                    "recommendation": fallback_recommendation,
                }
            )
        return dimensions

    def _average_site_dimensions(
        self,
        page_evaluations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        totals = {code: 0.0 for code in AICE_DIMENSION_CODES}
        counts = {code: 0 for code in AICE_DIMENSION_CODES}
        for page in page_evaluations:
            evaluation = page.get("aice_evaluation") or {}
            for dimension in evaluation.get("dimension_scores") or []:
                code = str(dimension.get("code") or "")
                if code not in totals:
                    continue
                max_score = max(float(dimension.get("max_score") or 1), 1)
                ratio = float(dimension.get("score") or 0.0) / max_score
                totals[code] += ratio * AICE_DIMENSION_MAX_SCORES[code]
                counts[code] += 1
        dimensions: list[dict[str, Any]] = []
        for code in AICE_DIMENSION_CODES:
            score = (
                round(totals[code] / counts[code], 1)
                if counts[code]
                else 0.0
            )
            dimensions.append(
                {
                    "code": code,
                    "label": AICE_DIMENSION_LABELS[code],
                    "score": score,
                    "max_score": AICE_DIMENSION_MAX_SCORES[code],
                    "reason": "按页面级 AICE 结果聚合的降级站点分。",
                    "evidence": [],
                    "recommendation": {
                        "priority": "P1",
                        "title": "复核站点级建议",
                        "action": "恢复官网级 LLM 审核后生成正式建议。",
                        "metric": "站点 evaluation_mode 恢复为 AICE-Web。",
                    },
                }
            )
        return dimensions

    def _validate_public_site_text(self, result: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        public_fields = {
            "conclusion": result.get("conclusion"),
            "executive_summary": result.get("executive_summary"),
            "preview_description": result.get("preview_description"),
            "report_summary": result.get("report_summary"),
            "report_markdown": result.get("report_markdown"),
        }
        joined = "\n".join(str(value or "") for value in public_fields.values())
        if not joined.strip():
            return ["官网级公开文案为空"]

        for field, value in public_fields.items():
            text = str(value or "")
            if not text:
                continue
            if any(pattern in text for pattern in _PUBLIC_REPORT_FORBIDDEN_PATTERNS):
                issues.append(f"{field} 包含内部降级或后端实现文案")
            if _PUBLIC_REPORT_EMOJI_RE.search(text):
                issues.append(f"{field} 包含不允许的 emoji")

        if re.search(r"\b(risk|watch|strong)\b", joined, flags=re.IGNORECASE):
            issues.append("公开文案包含英文分段名")

        score = self._optional_float(result.get("overall_score"))
        if score is not None:
            for match in _SITE_SCORE_TEXT_RE.finditer(joined):
                mentioned_score = self._optional_float(match.group(1))
                if mentioned_score is not None and abs(mentioned_score - score) > 0.1:
                    issues.append(
                        f"公开文案分数 {mentioned_score} 与实际总分 {score} 不一致"
                    )
                    break
        return issues[:8]

    def _repair_public_site_text(self, result: dict[str, Any]) -> None:
        if not self._validate_public_site_text(result):
            return

        score = round(float(result.get("overall_score") or 0.0), 1)
        band_label = self._public_score_band_label(score)
        low_dimensions = self._low_dimensions(result, limit=3)
        low_labels = "、".join(
            f"{item['code']} {self._public_dimension_name(item['code'])}"
            for item in low_dimensions
        )
        if not low_labels:
            low_labels = "官网结构、可读性和可回答性"

        result["conclusion"] = (
            f"官网 AI 友好度为 {score:.1f} / 100，处于{band_label}区间。"
            f"主要影响项集中在{low_labels}。"
        )
        result["executive_summary"] = (
            f"官网 AI 友好度 {score:.1f} / 100，当前处于{band_label}区间；"
            f"优先处理{low_labels}。"
        )
        result["preview_description"] = (
            f"官网 AI 友好度 {score:.1f} / 100，主要短板是{low_labels}。"
        )
        result["report_summary"] = (
            f"整站评分 {score:.1f} / 100，处于{band_label}区间，优先修复{low_labels}。"
        )
        result["report_markdown"] = self._build_minimal_site_markdown(result)

    def _low_dimensions(
        self, result: dict[str, Any], *, limit: int
    ) -> list[dict[str, Any]]:
        return sorted(
            result.get("dimension_scores") or [],
            key=lambda item: float(item.get("score") or 0)
            / max(float(item.get("max_score") or 1), 1),
        )[:limit]

    @staticmethod
    def _public_score_band_label(score: float) -> str:
        if score >= 78:
            return "较稳定"
        if score >= 60:
            return "需关注"
        return "高风险"

    @staticmethod
    def _public_dimension_name(code: str) -> str:
        names = {
            "C6": "抓取覆盖",
            "C9a": "语义标签",
            "C9b": "结构化数据",
            "C8": "时效线索",
            "C1": "品牌身份",
            "C4": "证据密度",
            "C2": "主题相关",
            "C3": "可回答性",
            "C5": "结构清晰度",
            "C7": "官方可信度",
        }
        return names.get(code, code)

    def _normalize_actions(self, raw_actions: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_actions, list):
            return []
        actions: list[dict[str, Any]] = []
        for item in raw_actions:
            if not isinstance(item, dict):
                continue
            actions.append(
                {
                    "priority": str(item.get("priority") or "P1").upper(),
                    "title": str(item.get("title") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "target_pages": self._string_list(item.get("target_pages")),
                    "dimensions": [
                        code
                        for code in self._string_list(item.get("dimensions"))
                        if code in AICE_DIMENSION_CODES
                    ],
                    "metric": str(item.get("metric") or "").strip(),
                }
            )
        return actions[:6]

    def _actions_from_dimensions(self, result: dict[str, Any]) -> list[dict[str, Any]]:
        low_dimensions = sorted(
            result.get("dimension_scores") or [],
            key=lambda item: float(item.get("score") or 0)
            / max(float(item.get("max_score") or 1), 1),
        )[:2]
        actions: list[dict[str, Any]] = []
        for index, dimension in enumerate(low_dimensions):
            recommendation = dimension.get("recommendation") or {}
            actions.append(
                {
                    "priority": "P0" if index == 0 else "P1",
                    "title": recommendation.get("title")
                    or f"修复 {dimension.get('label')}",
                    "summary": recommendation.get("action")
                    or str(dimension.get("reason") or "").strip(),
                    "target_pages": [],
                    "dimensions": [dimension.get("code")],
                    "metric": recommendation.get("metric") or "下次审核该维度得分提升。",
                }
            )
        return actions

    def _build_minimal_site_markdown(self, result: dict[str, Any]) -> str:
        score = round(float(result.get("overall_score") or 0.0), 1)
        band_label = self._public_score_band_label(score)
        low_dimensions = self._low_dimensions(result, limit=3)
        reason_items = []
        for dimension in low_dimensions:
            code = str(dimension.get("code") or "")
            reason = str(dimension.get("reason") or "").strip()
            if not code:
                continue
            reason_items.append(
                f"{code} {self._public_dimension_name(code)}：{reason or '得分偏低'}"
            )
        page_items = []
        for page in sorted(
            result.get("pages") or [],
            key=lambda item: float(
                ((item.get("aice_evaluation") or {}).get("overall_score") or 0)
            ),
        )[:3]:
            evaluation = page.get("aice_evaluation") or {}
            dimensions = self._low_dimensions(evaluation, limit=1)
            reason = ""
            if dimensions:
                dimension = dimensions[0]
                reason = (
                    f"{dimension.get('code')} "
                    f"{self._public_dimension_name(str(dimension.get('code') or ''))}"
                    f"{str(dimension.get('reason') or '').strip()}"
                ).strip()
            page_items.append(
                f"- {page.get('url')}：页面分 {float(evaluation.get('overall_score') or 0.0):.1f}"
                + (f"，{reason}。" if reason else "。")
            )

        lines = [
            "## 结论",
            "",
            (
                str(result.get("conclusion") or "").strip()
                or f"官网 AI 友好度为 {score:.1f} / 100，处于{band_label}区间。"
            ),
            "",
            "## 为什么会得到这个判断",
            "",
            "；".join(reason_items) or "主要扣分来自抓取覆盖、语义结构和可回答性。",
            "",
            "## 直接证据：显著影响评分的页面",
            "",
            *(page_items or ["- 本轮没有足够页面证据可展开。"]),
            "",
            "## 下一步最高优先级解决的建议",
            "",
        ]
        actions = result.get("prioritized_actions") or self._actions_from_dimensions(result)
        for action in actions[:3]:
            priority = str(action.get("priority") or "P1").upper()
            title = str(action.get("title") or "处理低分项").strip()
            summary = str(action.get("summary") or "").strip()
            metric = str(action.get("metric") or "").strip()
            line = f"- **{priority}：{title}**"
            if summary:
                line += f"。{summary}"
            if metric:
                line += f"完成标志：{metric}"
            lines.append(line)
        return "\n".join(lines).strip()

    def _attach_metadata(
        self,
        result: dict[str, Any],
        *,
        model: BaseLLMModel,
        model_identity: dict[str, str],
        cache_key: str | None,
        evaluation_scope: str,
        attempts: int,
        validator_issues: list[str],
        repaired: bool,
        cache_hit: bool,
    ) -> None:
        metadata = self._base_metadata(
            provider=model_identity["provider"],
            model_name=model_identity["model_name"],
            cache_key=cache_key,
            evaluation_scope=evaluation_scope,
            attempts=attempts,
            validator_issues=validator_issues,
            repaired=repaired,
            cache_hit=cache_hit,
            degraded=False,
        )
        result["metadata"] = metadata
        if evaluation_scope == "site_with_pages":
            for page in result.get("pages") or []:
                evaluation = (page or {}).get("aice_evaluation")
                if isinstance(evaluation, dict):
                    evaluation["metadata"] = {
                        **metadata,
                        "evaluation_scope": "page_in_site",
                        "validator_issues": [],
                        "validator_repaired": False,
                    }

    def _base_metadata(
        self,
        *,
        provider: str,
        model_name: str,
        cache_key: str | None,
        evaluation_scope: str,
        attempts: int,
        validator_issues: list[str],
        repaired: bool,
        cache_hit: bool,
        degraded: bool,
    ) -> dict[str, Any]:
        return {
            "prompt_version": AICE_WEB_PROMPT_VERSION,
            "static_prompt_hash": self.static_prompt_hash,
            "aice_model_profile": AICE_MODEL_PROFILE,
            "provider": provider,
            "model_name": model_name,
            "cache_key": cache_key,
            "evaluation_scope": evaluation_scope,
            "attempts": attempts,
            "validator_issues": validator_issues,
            "validator_repaired": repaired,
            "cache_hit": cache_hit,
            "degraded": degraded,
        }

    def _read_page_cache(self, cache_key: str) -> dict[str, Any] | None:
        now = time.time()
        stale_keys = [
            key
            for key, (cached_at, _) in _page_aice_cache.items()
            if now - cached_at > PAGE_AICE_CACHE_TTL_SECONDS
        ]
        for key in stale_keys:
            _page_aice_cache.pop(key, None)
        cached = _page_aice_cache.get(cache_key)
        if not cached:
            return None
        cached_at, value = cached
        if now - cached_at > PAGE_AICE_CACHE_TTL_SECONDS:
            _page_aice_cache.pop(cache_key, None)
            return None
        return deepcopy(value)

    def _write_page_cache(self, cache_key: str, value: dict[str, Any]) -> None:
        if len(_page_aice_cache) >= PAGE_AICE_CACHE_MAX_ENTRIES:
            oldest_key = min(_page_aice_cache.items(), key=lambda item: item[1][0])[0]
            _page_aice_cache.pop(oldest_key, None)
        _page_aice_cache[cache_key] = (time.time(), deepcopy(value))

    def _page_cache_key(
        self,
        page_facts: dict[str, Any],
        model_identity: dict[str, str],
    ) -> str:
        content_hash = hashlib.sha256(
            stable_json(page_facts).encode("utf-8")
        ).hexdigest()[:24]
        url = str(page_facts.get("url") or page_facts.get("final_url") or "")
        key_payload = {
            "url": url,
            "content_hash": content_hash,
            "prompt_version": AICE_WEB_PROMPT_VERSION,
            "provider": model_identity["provider"],
            "model_name": model_identity["model_name"],
        }
        return hashlib.sha256(stable_json(key_payload).encode("utf-8")).hexdigest()[
            :32
        ]

    def _model_identity(self, model: BaseLLMModel) -> dict[str, str]:
        config = getattr(model, "config", None)
        model_name = str(
            getattr(config, "model_name", None) or model.__class__.__name__
        )
        provider = model.__class__.__name__.replace("Model", "").lower()
        return {"provider": provider, "model_name": model_name}

    @staticmethod
    def _optional_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return float(default)

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _score_band(score: float) -> str:
        if score >= 78:
            return "strong"
        if score >= 60:
            return "watch"
        return "risk"
