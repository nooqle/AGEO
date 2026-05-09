"""AICE-Web 9C prompt contract for official-site AI friendliness review."""

from __future__ import annotations

import json
from typing import Any


AICE_WEB_PROMPT_VERSION = "aice_web_v1"
AICE_WEB_EVALUATION_MODE = "AICE-Web"
AICE_MODEL_PROFILE = "TEXT_LIGHT"

AICE_DIMENSIONS: tuple[dict[str, Any], ...] = (
    {
        "code": "C6",
        "label": "C6 覆盖度",
        "max_score": 25,
        "definition": "默认抓取方式能否稳定拿到页面正文、标题、主体结构和关键事实。",
    },
    {
        "code": "C9a",
        "label": "C9a 语义标签",
        "max_score": 10,
        "definition": "页面是否有清晰的 H1/H2/main/article 等语义结构，让模型能识别主题与主体内容。",
    },
    {
        "code": "C9b",
        "label": "C9b 结构化数据",
        "max_score": 10,
        "definition": "页面是否有匹配页面职责的 Schema.org 结构化标记。",
    },
    {
        "code": "C8",
        "label": "C8 时效性",
        "max_score": 15,
        "definition": "页面是否提供发布时间、更新时间或稳定的内容新鲜度线索。",
    },
    {
        "code": "C1",
        "label": "C1 品牌身份",
        "max_score": 10,
        "definition": "页面是否清楚表达品牌、官网身份、业务边界和可信主体。",
    },
    {
        "code": "C4",
        "label": "C4 证据密度",
        "max_score": 10,
        "definition": "页面是否提供可被模型引用的事实、参数、案例、常见问答、来源或证明材料。",
    },
    {
        "code": "C2",
        "label": "C2 主题相关性",
        "max_score": 5,
        "definition": "页面内容是否围绕页面职责展开，避免泛化、跑题或营销空话。",
    },
    {
        "code": "C3",
        "label": "C3 可回答性",
        "max_score": 5,
        "definition": "页面是否能直接回答用户常见问题，尤其是产品、场景、价格、风险和下一步行动。",
    },
    {
        "code": "C5",
        "label": "C5 结构清晰度",
        "max_score": 5,
        "definition": "页面表达是否清楚、段落是否有层次、重点是否能被机器快速提取。",
    },
    {
        "code": "C7",
        "label": "C7 官方可信度",
        "max_score": 5,
        "definition": "页面是否有 HTTPS、联系信息、官方口径、法律/公司信息等基础可信信号。",
    },
)

AICE_DIMENSION_CODES = tuple(item["code"] for item in AICE_DIMENSIONS)
AICE_DIMENSION_MAX_SCORES = {
    str(item["code"]): int(item["max_score"]) for item in AICE_DIMENSIONS
}
AICE_DIMENSION_LABELS = {
    str(item["code"]): str(item["label"]) for item in AICE_DIMENSIONS
}


def stable_json(value: Any) -> str:
    """Return stable UTF-8 JSON for prompt payloads and cache keys."""

    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def build_aice_web_system_prompt() -> str:
    """Build the fixed cache-friendly AICE-Web system prompt."""

    dimensions_json = json.dumps(AICE_DIMENSIONS, ensure_ascii=False, indent=2)
    return f"""你是 Specta AI 的 AICE-Web 官网 AI 友好度审核员。

固定版本：{AICE_WEB_PROMPT_VERSION}

你的任务：
1. 按固定 AICE 9C 矩阵评估官网页面和整站。
2. 页面级评分、整站总分、结论、P0/P1 建议都必须由你生成。
3. 只能使用 user JSON payload 中的事实，不要编造未给出的抓取结果、页面内容或业务事实。
4. 输出必须是单个 JSON object，不要输出解释性正文。
5. 当 user JSON 的 evaluation_scope=site_with_pages 时，必须在一次输出里同时返回整站结果和压缩 pages 结果；不要假设还有页面级二次评估。

报告正文写法：
1. report_markdown 必须使用中文，可保留 AICE code、品牌名、产品名和 URL；不要堆英文维度名。
2. 用户先读结论，再读评分依据和证据，最后读建议。报告要像正式分析报告，不要只写几段摘要。
3. report_markdown 必须包含这些一级结构：
   - ## 结论
   - ## 为什么会得到这个判断
   - ## 直接证据：显著影响评分的页面
   - ## 下一步最高优先级解决的建议
   - ## 附录：本轮纳入评估的页面
   - 如样本不足或有抓取失败，再加 ## 本次结果还需要注意
4. P0/P1 建议必须写成可执行动作，每条都包含：优先页面、当前问题、建议动作、完成标志。
5. 维度在报告正文中写成“C9a 语义标签”“C9b 结构化数据”这类中文短标签，不要写成长串中英混合标题。
6. 不要使用“优化内容”“提升质量”这类空泛建议；每条建议必须能落到页面、字段、结构或可验证指标。
7. 如果写“事实稀疏”，必须紧接着说明稀疏在什么信息上，例如参数、价格/权益、常见问答、案例、时间、来源、引用数字或办理步骤。
8. 不要出现 undefined、N/A、null、A5 快照、内部实现名或英文占位符。
9. 不要在公开文案中写 LLM 不可用、后端降级、降级模式、重新运行完整审核等内部状态；只有当输入明确表示 evaluation_mode 为降级时才说明样本限制。
10. 公开文案不要使用 emoji，也不要写 risk、watch、strong 这类英文分段名；应写“高风险”“需关注”“较稳定”。

输出长度约束：
1. report_markdown 控制在 2200 到 3600 个中文字符之间；不能压缩成只有结论、原因和三条建议。
2. key_findings、low_dimension_analysis、recommendations 各最多 3 条。
3. prioritized_actions 最多 3 条。
4. 每个维度的 reason 不超过 40 个中文字符，evidence 最多 2 条。
5. 每条 recommendation 的 title、action、metric 都写短句，不超过 40 个中文字符。
6. 不要在 report_markdown 中输出完整 9C 评分矩阵大表；维度分数保留在 JSON 字段里即可。
7. 当 evaluation_scope=site_with_pages 时，pages 必须紧凑：每页只写 url、overall_score 和 10 个维度的 score/reason；不要为页面级维度展开长证据和长建议。
8. 不要建议为了达到某个字数而堆正文；建议应写成“补充关键事实块、常见问答、参数、案例、结构化数据或语义标签”这类可验证动作。

固定 9C 矩阵：
{dimensions_json}

分段阈值：
1. overall_score >= 78 时 score_band 必须是 strong。
2. 60 <= overall_score < 78 时 score_band 必须是 watch。
3. overall_score < 60 时 score_band 必须是 risk。
4. report_markdown 中描述强弱区间时必须与上述阈值一致。

硬规则：
1. 页面 crawl_readable=false 时，C6 必须等于 0。
2. 页面缺 H1 或缺 main/article 主体语义区时，C9a 最高 5。
3. 页面没有 schema_types 时，C9b 最高 5。
4. 页面级 overall_score 必须等于 10 个维度 score 的求和，总分满分 100。
5. 必须返回全部 10 个维度，不能新增、缺失或改名。
6. 建议必须具体到页面或维度，不能只写泛泛的“优化内容”。

JSON 输出结构：
1. 当 evaluation_scope=page 时，顶层是页面级对象，字段包括：
   evaluation_mode、overall_score、score_band、dimension_scores、key_findings、recommendations。
2. 当 evaluation_scope=site_with_pages 时，顶层是官网级对象，字段包括：
   evaluation_mode、overall_score、score_band、dimension_scores、conclusion、
   low_dimension_analysis、key_findings、prioritized_actions、executive_summary、
   preview_description、report_summary、report_markdown、pages。
3. 顶层 dimension_scores 必须覆盖全部 10 个维度；每项字段：
   code、label、score、max_score、reason、evidence、recommendation。
4. recommendation 字段固定为：
   priority、title、action、metric。
5. prioritized_actions 每项字段：
   priority、title、summary、target_pages、dimensions、metric。
6. 当 evaluation_scope=site_with_pages 时，pages 每项使用压缩结构：
   url、overall_score、dimension_scores。
7. 压缩页面 dimension_scores 必须是以 10 个维度 code 为 key 的 object；
   每个 code 的值只包含 score 和 reason，例如 C6 的值表示“分数 20，原因：正文可读”。
8. site_with_pages 的 pages 里不要输出 aice_evaluation、evaluation_mode、score_band、
   key_findings、recommendations、label、evidence、recommendation；pages 字段保持紧凑即可。
9. 当 evaluation_scope=page 时，页面级对象仍使用完整页面结构：
   evaluation_mode、overall_score、score_band、dimension_scores、key_findings、recommendations。
"""


def build_page_evaluation_payload(
    *,
    brand_name: str,
    root_domain: str,
    page: dict[str, Any],
    validator_issues: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "prompt_version": AICE_WEB_PROMPT_VERSION,
        "evaluation_scope": "page",
        "brand_name": brand_name,
        "root_domain": root_domain,
        "page": page,
        "validator_issues": validator_issues or [],
    }


def build_site_evaluation_payload(
    *,
    brand_name: str,
    root_domain: str,
    root_url: str,
    coverage_summary: dict[str, Any],
    scan_quality_status: str,
    pages: list[dict[str, Any]],
    validator_issues: list[str] | None = None,
) -> dict[str, Any]:
    compact_pages: list[dict[str, Any]] = []
    for page in pages:
        compact_pages.append(
            {
                "url": page.get("url"),
                "final_url": page.get("final_url"),
                "page_label": page.get("page_label"),
                "page_type": page.get("page_type"),
                "source_hint": page.get("source_hint"),
                "depth": page.get("depth"),
                "http_status": page.get("http_status"),
                "content_type": page.get("content_type"),
                "crawl_readable": page.get("crawl_readable"),
                "fetch_failure_reason": page.get("fetch_failure_reason"),
                "title": page.get("title"),
                "meta_description": page.get("meta_description"),
                "has_h1": page.get("has_h1"),
                "h1_texts": list(page.get("h1_texts") or [])[:3],
                "h1_count": page.get("h1_count"),
                "h2_texts": list(page.get("h2_texts") or [])[:5],
                "h2_count": page.get("h2_count"),
                "has_main": page.get("has_main"),
                "has_article": page.get("has_article"),
                "body_text_length": page.get("body_text_length"),
                "body_text_excerpt": _short_text(page.get("body_text_excerpt"), 700),
                "script_count": page.get("script_count"),
                "has_noscript": page.get("has_noscript"),
                "schema_types": page.get("schema_types") or [],
                "published_at": page.get("published_at"),
                "backend_rule_precheck": page.get("backend_rule_precheck") or {},
            }
        )
    return {
        "prompt_version": AICE_WEB_PROMPT_VERSION,
        "evaluation_scope": "site_with_pages",
        "brand_name": brand_name,
        "root_domain": root_domain,
        "root_url": root_url,
        "coverage_summary": coverage_summary,
        "scan_quality_status": scan_quality_status,
        "pages": compact_pages,
        "output_contract": {
            "one_call_only": True,
            "site_dimension_scores": "Return all 10 dimensions with short reason and at most one evidence item.",
            "page_output": "Use compact pages: url, overall_score, dimension_scores as an object keyed by AICE code. Each value only contains score and reason. Do not nest aice_evaluation.",
            "report_markdown_target_chars": "2200-3600",
            "max_prioritized_actions": 3,
        },
        "validator_issues": validator_issues or [],
    }


def _short_text(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()
