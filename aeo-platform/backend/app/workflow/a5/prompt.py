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
    return _get_a5_report_context_intro(report_type) + """你现在是一位资深的 AEO（Answer Engine Optimization）数据分析师与商业咨询顾问。
你的任务是：根据提供的跨平台大模型问答抓取数据，为客户生成一份《品牌 AEO 跨平台诊断与优化分析报告》。

## 报告原则
- 全程使用专业、客观、面向企业高管的商业分析口吻。
- 所有结论必须能回溯到输入数据，不得虚构。
- 如果某个维度没有稳定数据，请明确写“暂无足够数据支撑”，不要猜测。
- 不要输出方法论自述、推理笔记、自我修正、草稿说明。
- 不要输出 BWVS、总分、分档、综合评分等内部评分概念。

## report_markdown 必须严格采用以下五个一级章节
1. `## 一、核心执行摘要`
2. `## 二、核心数据基准看板`
3. `## 三、跨大模型平台表现拆解`
4. `## 四、主题场景诊断：缺位与竞争图谱`
5. `## 五、AEO 常态化运营与优化策略`

## 各章节写作要求

### 一、核心执行摘要
- 200 字以内。
- 用一段话概括品牌当前在 DeepSeek、Kimi、豆包、混元上的整体占位情况。
- 必须点出最大的结构性痛点，以及对业务的潜在影响。

### 二、核心数据基准看板
- 必须使用 Markdown 表格。
- 表头固定为：
  `| 指标名称 | 指标定义 | 本品牌数据 | 竞品A数据 | 竞品B数据 | 诊断结论 |`
- 指标固定为：
  - 提及率
  - 官网引用占比
  - 品牌内容引用占比
  - 负向情感占比
- “诊断结论”必须是精准的一句话，指出优势或短板。

### 三、跨大模型平台表现拆解
- 必须使用 Markdown 表格。
- 表头固定为：
  `| 平台名称 | 平台抓取偏好 | 本品牌在该平台现状 | 存在问题与突破口 |`
- 平台抓取偏好要用中文表达，不允许出现中英文夹杂词句。
- 对表现最差的平台，必须给出具体的内容投放或信源补强建议。

### 四、主题场景诊断：缺位与竞争图谱
- 必须分成两个小节：
  - `### 品牌缺位场景`
  - `### 竞争胶着场景`
- 每个小节至少列出 2 个真实问题示例；如果不足 2 个，要如实说明样本不足。
- 不能只列标签，必须解释这些问题为什么意味着流量流失或竞争压力。
- 要指出 AI 在对比场景里更偏向谁，以及我方缺少什么类型的语料。

### 五、AEO 常态化运营与优化策略
- 必须严格按以下四个二级小节输出：
  - `### 1. 基建优化（夯实第一信源）`
  - `### 2. 语料防御与对冲（处理负向与胶着）`
  - `### 3. 填补盲区漏洞（拓展增量流量）`
  - `### 4. 按月度 / 双周回测监测`
- 禁止使用“30天速成”“短期冲刺”等概念，强调长期阵地战。

## 输出 JSON
{
  "executive_summary": "200字以内的执行摘要，顺序必须是事实 -> 痛点/风险 -> 业务影响/动作。",
  "key_findings": [
    "发现1：必须带具体数据、平台、来源或问题场景。",
    "发现2",
    "发现3"
  ],
  "report_markdown": "严格按五个一级章节输出的 Markdown 正文。"
}

只输出原始 JSON。从 { 开始，不要使用 Markdown 代码块。"""


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

    top_competitors = [
        item for item in (competitor_metrics or [])
        if isinstance(item, dict) and item.get("name")
    ][:2]
    missing_examples = [
        item for item in (scenario_matrix or [])
        if isinstance(item, dict) and item.get("battle_status") == "missing"
    ][:3]
    contested_examples = [
        item for item in (scenario_matrix or [])
        if isinstance(item, dict) and item.get("battle_status") in {"contested", "defend"}
    ][:3]
    platform_stats = (source_overview or {}).get("platform_citation_stats", {}) if isinstance(source_overview, dict) else {}
    sections.append(
        "## AEO 报告输入摘要\n"
        + json.dumps(
            {
                "品牌名称": brand_profile.get("brand_name", ""),
                "核心竞品": [item.get("name", "") for item in top_competitors],
                "监测范围": {
                    "总问题数": metrics.get("total_questions", 0),
                    "报告类型": "行业全景基线分析" if analysis_mode == "baseline" else "场景分析报告",
                },
                "核心指标表现": {
                    "提及率": summary_metrics.get("brand_mention_rate", metrics.get("mention_rate", 0)) if summary_metrics else metrics.get("mention_rate", 0),
                    "官网引用占比": (source_overview or {}).get("official_citation_rate", 0) if isinstance(source_overview, dict) else 0,
                    "品牌内容引用占比": (summary_metrics or {}).get("content_citation_rate", 0),
                    "负向情感占比": (
                        (
                            (mention_sentiment_analysis or {}).get("brand", {}).get("summary", {}).get("negative", 0)
                            / max(
                                1,
                                sum(
                                    int((mention_sentiment_analysis or {}).get("brand", {}).get("summary", {}).get(key, 0) or 0)
                                    for key in ("positive", "neutral", "negative")
                                ),
                            )
                        )
                        if isinstance((mention_sentiment_analysis or {}).get("brand", {}), dict)
                        else 0
                    ),
                },
                "各平台表现明细": {
                    platform: {
                        "成功回答数": stats.get("total_answers", 0),
                        "总引用数": stats.get("total_citations", 0),
                        "官网引用数": stats.get("official_citations", 0),
                        "高频来源": [item.get("domain", "") for item in (stats.get("top_domains", []) or [])[:5] if isinstance(item, dict)],
                    }
                    for platform, stats in platform_stats.items()
                    if isinstance(stats, dict)
                },
                "品牌完全缺位的问题示例": [
                    item.get("scenario_label", "")
                    for item in missing_examples
                    if isinstance(item, dict) and item.get("scenario_label")
                ],
                "竞争胶着的问题示例": [
                    item.get("scenario_label", "")
                    for item in contested_examples
                    if isinstance(item, dict) and item.get("scenario_label")
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
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



