"""Summary generation module for Specta AI workflow.

This module provides formatted human-readable summaries for each agent step (A1-A5).
These summaries are displayed in the TPAOR response phase.
"""

def generate_a1_summary(
    brand_profile: dict | None,
    competitors: list | None,
    competitive_landscape: dict | None,
) -> str:
    """Generate summary for A1 (Brand Competition Analysis).

    Args:
        brand_profile: Brand profile data
        competitors: List of competitors
        competitive_landscape: Competitive landscape analysis

    Returns:
        Human-readable summary string
    """
    if not brand_profile:
        return "品牌分析完成，但未获取到品牌档案信息。"

    brand_name = brand_profile.get("brand_name", "未知品牌")
    industry = brand_profile.get("industry", "未知行业")
    competitor_count = len(competitors) if competitors else 0

    # Get competition intensity if available
    intensity = ""
    if competitive_landscape:
        intensity_val = competitive_landscape.get("competition_intensity", "")
        if intensity_val:
            intensity = f"，竞争强度{intensity_val}"

    return f"已完成品牌分析：识别品牌「{brand_name}」（{industry}），发现{competitor_count}个主要竞品{intensity}"


def generate_a2_summary(marketing_personas: dict | None) -> str:
    """Generate summary for A2 (Marketing Persona Generation).

    Args:
        marketing_personas: Marketing personas data

    Returns:
        Human-readable summary string
    """
    if not marketing_personas:
        return "用户画像生成完成，但未获取到画像数据。"

    personas = marketing_personas.get("user_personas", [])
    persona_count = len(personas)

    # Count total usage scenarios
    total_scenarios = 0
    for persona in personas:
        scenarios = persona.get("usage_scenarios", [])
        total_scenarios += len(scenarios)

    return f"已生成{persona_count}个用户画像，覆盖{total_scenarios}个使用场景"


def generate_a3_summary(
    simulated_questions: dict | None,
    questions: list | None,
) -> str:
    """Generate summary for A3 (Simulated Question Generation).

    Args:
        simulated_questions: Simulated questions data
        questions: Flattened questions list

    Returns:
        Human-readable summary string
    """
    if not simulated_questions and not questions:
        return "问题模拟生成完成，但未获取到问题数据。"

    # Get generation mode
    mode = ""
    if simulated_questions:
        gen_mode = simulated_questions.get("generation_mode", "")
        if gen_mode == "品牌全景模式":
            mode = "（品牌全景模式）"
        elif gen_mode == "画像聚焦模式":
            mode = "（画像聚焦模式）"

    # Count questions
    if questions:
        question_count = len(questions)
    elif simulated_questions:
        qs = simulated_questions.get("simulated_questions", [])
        question_count = len(qs)
        # Count variants
        variant_count = 0
        for q in qs:
            variants = q.get("question_variants", {})
            variant_count += len(variants)
        return f"已生成{question_count}组模拟问题，共{variant_count}个问题变体{mode}"
    else:
        question_count = 0

    return f"已生成{question_count}个模拟问题{mode}"


def generate_a4_summary(fetch_results: list | None) -> str:
    """Generate summary for A4 (Answer Fetching).

    Args:
        fetch_results: List of fetch results

    Returns:
        Human-readable summary string
    """
    if not fetch_results:
        return "答案抓取完成，但未获取到抓取结果。"

    # Count successful fetches across all platforms
    total_fetches = 0
    successful_fetches = 0
    platform_stats = {}

    for result in fetch_results:
        platform_results = result.get("platform_results", [])
        for pr in platform_results:
            total_fetches += 1
            platform = pr.get("platform", "unknown")
            if platform not in platform_stats:
                platform_stats[platform] = {"total": 0, "success": 0}
            platform_stats[platform]["total"] += 1
            if pr.get("success"):
                successful_fetches += 1
                platform_stats[platform]["success"] += 1

    success_rate = (successful_fetches / total_fetches * 100) if total_fetches > 0 else 0
    platform_count = len(platform_stats)

    return f"已完成{platform_count}个平台的答案抓取，成功率{success_rate:.0f}%（{successful_fetches}/{total_fetches}）"


def generate_a5_summary(
    metrics: dict | None,
    report: dict | None,
) -> str:
    """Generate summary for A5 (Analytics & Report).

    Args:
        metrics: Analytics metrics
        report: Final report

    Returns:
        Human-readable summary string
    """
    if not metrics and not report:
        return "分析报告生成完成，但未获取到分析数据。"

    summary_metrics = (report.get("summary_metrics", {}) if report else {}) or (metrics.get("summary_metrics", {}) if metrics else {})

    # Get mention rate
    mention_rate = 0.0
    if summary_metrics:
        mention_rate = float(summary_metrics.get("brand_mention_rate", 0) or 0) * 100
    elif metrics:
        mention_rate = float(metrics.get("mention_rate", 0) or 0) * 100

    content_citation_rate = float(summary_metrics.get("content_citation_rate", 0) or 0) * 100
    scenario_hit_count = summary_metrics.get("scenario_hit_count")
    scenario_total = summary_metrics.get("scenario_total")
    accuracy_score = summary_metrics.get("accuracy_score")
    accuracy_status = summary_metrics.get("accuracy_status")

    # Get key findings count
    key_findings_count = 0
    if report:
        key_findings = report.get("key_findings", [])
        key_findings_count = len(key_findings)

    summary = "分析报告已生成"
    details = []
    if mention_rate > 0:
        details.append(f"品牌提及率 {mention_rate:.1f}%")
    if content_citation_rate > 0:
        details.append(f"内容引用率 {content_citation_rate:.1f}%")
    if scenario_hit_count is not None and scenario_total is not None:
        details.append(f"已覆盖 {scenario_hit_count}/{scenario_total} 个场景")
    if accuracy_score is not None:
        details.append(f"答案正确率 {float(accuracy_score) * 100:.1f}%")
    elif accuracy_status == "pending":
        details.append("答案正确率待事实库补充后再评估")
    if key_findings_count > 0:
        details.append(f"{key_findings_count}项发现")
    if details:
        summary += "，" + "，".join(details)
    summary += "。完整报告见右侧。"

    return summary
