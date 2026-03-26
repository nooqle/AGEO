"""Prompt builders for A5 analytics generation."""

import json
from typing import Any

def _get_a5_report_context_intro(report_type: str) -> str:
    """Get context intro section based on report type."""
    if report_type == "baseline":
        return """## 报告类型：行业全景基线分析
本次分析是品牌的行业全景基线分析。问题来源是行业通用的用户搜索问题（非特定画像）。
请从行业全景视角分析品牌的 AI 平台可见性。

"""
    return """## 报告类型：场景分析报告
本次分析基于特定用户画像/场景。请从目标用户群体视角分析品牌表现。
如果提供了基线参考数据，请在报告中对比场景表现与行业基线的差异。

"""


def _get_a5_core_prompt(report_type: str = "persona") -> str:
    """A5 system prompt for the customer-facing report payload."""
    return _get_a5_report_context_intro(report_type) + """You are Specta AI's analytics expert.
Generate a fact-first A5 report from the provided A4 fetch results and structured evidence.

## Report goal
- Write for brand operators who care about concrete brand performance, not internal scoring logic.
- The main deliverable is a Markdown document. It should read like a client-ready report, not a raw data dump.
- Do not lead with composite scores, platform scores, or abstract methodology.
- Every statement must be traceable to provided structured facts.
- If there is not enough evidence, say so briefly instead of inventing.

## Mandatory Markdown framework
Your `report_markdown` must follow this exact section structure:
1. `## 摘要信息`
2. `## 一、提及率指标`
3. `## 二、答案引用信息分布`
4. `## 三、业务主题覆盖`
5. `## 四、进一步建议`

## What each section must answer
- `摘要信息`:
  - Give the overall diagnosis in customer language.
  - Summarize the brand's current AI visibility, biggest risk, and most important next move.
- `一、提及率指标`:
  - Brand mention rate.
  - How many questions/scenarios mention the brand.
  - Whether those mentions are positive / neutral / negative.
  - What the negative mentions are about.
  - Which competitors are threatening because their mention rate is close to or above the brand.
- `二、答案引用信息分布`:
  - Overall citation/source distribution.
  - Distribution of citation sources specifically when the brand is mentioned.
  - Whether the official website appeared and how many times.
  - Source preference of the four AI platforms.
  - Especially highlight source preference in answers that mention the brand.
- `三、业务主题覆盖`:
  - How many business topics/scenarios were covered in this run.
  - Which topics the brand is recommended in.
  - Which topics the brand is being marginalized in.
  - Which topics the brand does not appear in.
- `四、进一步建议`:
  - What to do by topic and by platform.
  - Which deeper follow-up analyses should be done next to uncover root causes.

## Output rules
- `executive_summary` must still follow: facts -> risks -> actions
- `key_findings` must contain 3-5 factual findings, each grounded in scenario labels, mention counts, citation counts, platform preferences, or source examples
- `report_markdown` is the primary customer-facing body and must be at least 5 short sections with concrete facts
- Use short paragraphs and bullet lists where helpful
- Prefer concrete counts, rates, scenario labels, platform names, and source domains
- Never output internal reasoning, self-corrections, or analysis notes
- Do not output competitor_battle, risk_section, action_queue, strengths, weaknesses, opportunities, threats, industry_insights, platform_analysis, competitor_deep_analysis, or actionable_recommendations
- Do not mention BWVS, overall score, score band, or any synthetic scoring headline

## Output JSON
{
  "executive_summary": "至少 120 字，顺序必须是事实 -> 风险 -> 动作。",
  "key_findings": [
    "发现 1：必须包含具体场景、问题数、来源或引用事实。",
    "发现 2",
    "发现 3"
  ],
  "report_markdown": "严格按指定 Markdown 章节输出的客户报告正文。"
}

Output raw JSON only. Start directly with { and do not include Markdown fences or explanations."""


def _get_a5_supplementary_prompt(report_type: str = "persona") -> str:
    """Deprecated supplementary prompt kept for compatibility."""
    return _get_a5_report_context_intro(report_type) + """Return an empty JSON object.

Output raw JSON only. Start directly with { and do not include Markdown fences or explanations."""


def _get_a5_system_prompt(report_type: str = "persona") -> str:
    """Legacy single-call prompt — kept for reference but no longer used by default."""
    return _get_a5_core_prompt(report_type)


def _build_a5_user_content(
    brand_profile: dict,
    metrics: dict,
    fetch_results: list,
    competitors: list,
    marketing_personas: dict | None = None,
    previous_snapshot: dict | None = None,
    competitor_metrics: list | None = None,
    analysis_mode: str = "persona",
    baseline_metrics: dict | None = None,
    baseline_report: dict | None = None,
    summary_metrics: dict | None = None,
    scenario_matrix: list | None = None,
    source_overview: dict | None = None,
    mention_sentiment_analysis: dict | None = None,
) -> str:
    """Build enhanced user content for A5 with structured tables for LLM."""
    sections = []

    # 1. Brand info
    sections.append(
        f"## 品牌信息\n"
        f"- 品牌名称: {brand_profile.get('brand_name', '')}\n"
        f"- 行业: {brand_profile.get('industry', '')}\n"
        f"- 核心产品: {', '.join(brand_profile.get('core_products', []))}\n"
        f"- 品牌定位: {brand_profile.get('brand_positioning', '')}\n"
        f"- 目标受众: {brand_profile.get('target_audience', '')}"
    )

    # 2. Core metrics — platform_breakdown as readable table
    platform_breakdown = metrics.get("platform_breakdown", {})
    if platform_breakdown:
        platform_table_lines = [
            "| 平台 | 总问题数 | 成功获取 | 品牌提及数 | 提及率 |",
            "|------|---------|---------|-----------|--------|",
        ]
        for platform, stats in platform_breakdown.items():
            total = stats.get("total", 0)
            success = stats.get("success", 0)
            mentions_count = stats.get("mentions", 0)
            rate = f"{mentions_count / total:.1%}" if total > 0 else "0.0%"
            platform_table_lines.append(
                f"| {platform} | {total} | {success} | {mentions_count} | {rate} |"
            )
        platform_table = "\n".join(platform_table_lines)
    else:
        platform_table = "暂无平台数据"

    sentiment_dist = metrics.get("sentiment_distribution", {})
    sections.append(
        f"## 核心指标\n"
        f"- 提及率: {metrics.get('mention_rate', 0):.2%}\n"
        f"- 内容引用率: {(summary_metrics or {}).get('content_citation_rate', 0):.2%}\n"
        f"- 场景覆盖数: {(summary_metrics or {}).get('scenario_hit_count', 0)}/{(summary_metrics or {}).get('scenario_total', 0)}\n"
        f"- 总问题数: {metrics.get('total_questions', 0)}\n"
        f"- 总提及数: {metrics.get('total_mentions', 0)}\n\n"
        f"### 各平台详细表现\n{platform_table}\n\n"
        f"### 情感分布\n"
        f"- 正面: {sentiment_dist.get('positive', 0)}, "
        f"中性: {sentiment_dist.get('neutral', 0)}, "
        f"负面: {sentiment_dist.get('negative', 0)}"
    )

    if summary_metrics or scenario_matrix or source_overview:
        scenario_rows = list(scenario_matrix or [])
        source_summary = source_overview or {}

        top_missing = [
            row for row in scenario_rows
            if isinstance(row, dict) and row.get("battle_status") == "missing"
        ][:6]
        top_contested = [
            row for row in scenario_rows
            if isinstance(row, dict) and row.get("battle_status") == "contested"
        ][:6]

        sections.append(
            "## Scenario-first structured diagnostics\n"
            "Use this section as the primary evidence base. Focus on scenarios, mention facts, and source facts instead of composite scores.\n\n"
            + json.dumps({
                "summary_metrics": summary_metrics or {},
                "source_overview": source_summary,
                "scenario_matrix_sample": scenario_rows[:12],
                "top_missing_scenarios": top_missing,
                "top_contested_scenarios": top_contested,
            }, ensure_ascii=False, indent=2)
        )

        sections.append(
            "## Compatibility field rules\n"
            "- headline must be a diagnosis title, never a score headline.\n"
            "- subtitle must summarize mention rate / content citation rate / scenario coverage.\n"
            "- content and executive_summary must use facts -> risks -> actions.\n"
            "- Never write BWVS, overall score, score_band, 综合分, 品牌AI可见度指数 in headline/subtitle/content/executive_summary.\n"
            "- If official_top_titles exists, treat it as concrete evidence for official-page title samples used by AI citations.\n"
            "- If some value is missing, keep it null/empty instead of inventing explanatory prose.\n"
        )

    if mention_sentiment_analysis:
        sections.append(
            "## 品牌与竞品提及情绪分析\n"
            + json.dumps(mention_sentiment_analysis, ensure_ascii=False, indent=2)
        )

    # 3. Platform answer samples
    platform_samples = _extract_platform_samples(fetch_results, max_per_platform=3)
    if platform_samples:
        sections.append(
            "## 各平台回答样本\n"
            "（字段说明：answer_excerpt=回答摘录, has_brand_mention=是否提及品牌, "
            "citations_count=引用总数, citation_samples=前3条实际引用链接[url+title]）\n"
            + json.dumps(platform_samples, ensure_ascii=False, indent=2)
        )

    # 4. Competitors — structured quantitative table
    brand_mention_rate = metrics.get("mention_rate", 0)
    if competitor_metrics:
        comp_lines = [
            "## 竞品量化数据",
            f"（本品牌提及率: {brand_mention_rate:.1%}）",
            "",
            "| 竞品名称 | 提及率 | 与本品牌对比 | 情感倾向 | 出现排名 |",
            "|---------|--------|------------|---------|---------|",
        ]
        for cm in competitor_metrics:
            name = cm.get("name", "")
            mr = cm.get("mention_rate", 0)
            sentiment = cm.get("sentiment", 0)
            ranking = cm.get("avg_ranking", 0)
            vs = "高于" if mr > brand_mention_rate else ("低于" if mr < brand_mention_rate else "持平")
            sent_label = "正面" if sentiment > 0.2 else ("负面" if sentiment < -0.2 else "中性")
            comp_lines.append(
                f"| {name} | {mr:.1%} | {vs} | {sent_label}({sentiment:+.2f}) | #{ranking} |"
            )

        # Append appeared_in details
        for cm in competitor_metrics:
            appeared = cm.get("appeared_in", [])
            if appeared:
                comp_lines.append(f"\n**{cm['name']}** 出现在以下问题中：")
                for a in appeared:
                    comp_lines.append(f"  - [{a['platform']}] {a['question']}")

        sections.append("\n".join(comp_lines))
    elif competitors:
        comp_summary = [
            {"name": c.get("name", ""), "relevance_score": c.get("relevance_score", 0)}
            for c in competitors[:8]
        ]
        sections.append(
            f"## 竞品数据\n{json.dumps(comp_summary, ensure_ascii=False, indent=2)}"
        )

    # 5. User personas (if A2 succeeded)
    if marketing_personas:
        personas = marketing_personas.get("user_personas", [])
        if personas:
            persona_summary = [
                {
                    "name": p.get("persona_name", p.get("name", "")),
                    "description": p.get("persona_description", p.get("description", "")),
                    "priority": p.get("persona_priority", p.get("priority", "")),
                }
                for p in personas[:4]
            ]
            sections.append(
                f"## 目标用户画像\n"
                f"{json.dumps(persona_summary, ensure_ascii=False, indent=2)}"
            )

    # 6. Previous snapshot for comparison
    if previous_snapshot:
        sections.append(
            f"## 上次分析数据 (日期: {previous_snapshot.get('date', 'N/A')})\n"
            f"{json.dumps(previous_snapshot, ensure_ascii=False, indent=2)}"
        )

    # Inject baseline context for persona mode comparison
    if analysis_mode == "persona" and baseline_metrics:
        baseline_mention = baseline_metrics.get("mention_rate", 0)
        baseline_content_citation = (baseline_metrics.get("summary_metrics", {}) or {}).get("content_citation_rate", 0)
        baseline_findings = ""
        if baseline_report:
            findings = baseline_report.get("key_findings", [])[:3]
            if findings:
                baseline_findings = "\n".join(f"- {f}" for f in findings)
        sections.append(
            f"## 基线报告参考数据\n"
            f"- 基线提及率: {baseline_mention:.1%}\n"
            f"- 基线内容引用率: {baseline_content_citation:.1%}\n"
            f"- 基线核心发现:\n{baseline_findings}\n\n"
            f"请在场景报告中对比基线数据，说明该场景表现与行业基线的差异。"
            f"重点比较场景覆盖、内容引用和竞品提及事实，不要输出综合分数对比。"
        )

    sections.append(
        "\nPlease generate a fact-first A5 report. Prioritize brand mention rate, content citation rate, scenario coverage, mention facts, and source structure."
    )

    return "\n\n".join(sections)


def _extract_platform_samples(
    fetch_results: list, max_per_platform: int = 3
) -> dict[str, list[dict]]:
    """从 fetch_results 中提取各平台的回答样本。

    每个平台最多 max_per_platform 条，避免 context 过长。
    优先选取品牌被提及的回答。
    """
    platform_samples: dict[str, list[dict]] = {}

    for fr in fetch_results:
        question_text = fr.get("question_text", "")
        for pr in fr.get("platform_results", []):
            platform = pr.get("platform", "unknown")
            if platform not in platform_samples:
                platform_samples[platform] = []

            if len(platform_samples[platform]) >= max_per_platform:
                continue

            if pr.get("success"):
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                has_mention = answer.get("has_brand_mention", False) if isinstance(answer, dict) else False

                # Truncate long answers
                if len(content) > 500:
                    content = content[:500] + "..."

                citations = pr.get("citations", [])
                # Provide first 3 citation URLs/titles so A5 prompt can reference
                # actual sources when evaluating Authoritativeness (EEAT-A)
                sample_citations = [
                    {
                        "url": c.get("url", ""),
                        "title": c.get("title", "")[:60],
                    }
                    for c in citations[:3]
                    if isinstance(c, dict) and c.get("url")
                ]
                platform_samples[platform].append({
                    "question": question_text[:80],
                    "answer_excerpt": content,
                    "has_brand_mention": has_mention,
                    "citations_count": len(citations),
                    "citation_samples": sample_citations,  # 实际引用链接样本
                })

    return platform_samples



