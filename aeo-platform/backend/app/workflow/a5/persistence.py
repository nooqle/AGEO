from typing import Any


def build_report_artifact_data(
    *,
    brand_name: str,
    is_baseline: bool,
    metrics: dict[str, Any],
    report_data: dict[str, Any],
    summary_metrics: dict[str, Any],
    fetch_results_summary: list[dict[str, Any]],
    competitor_metrics: list[dict[str, Any]],
    delta_vs_previous: dict[str, Any] | None,
    report_v2_sections: dict[str, Any],
    scenario_matrix: list[dict[str, Any]],
    source_overview: dict[str, Any],
    mention_sentiment_analysis: dict[str, Any],
) -> dict[str, Any]:
    report_headline = (
        f"{brand_name or '品牌'} 基线全景分析报告"
        if is_baseline
        else f"{brand_name or '品牌'} AI 可见性分析报告"
    )
    return {
        'headline': report_headline,
        'subtitle': (
            f"品牌提及率 {summary_metrics.get('brand_mention_rate', 0):.1%} | "
            f"内容引用率 {summary_metrics.get('content_citation_rate', 0):.1%} | "
            f"场景覆盖 {summary_metrics.get('scenario_hit_count', 0)}/{summary_metrics.get('scenario_total', 0)}"
        ),
        'metrics': {
            'brand_mention_rate': summary_metrics.get('brand_mention_rate', 0),
            'content_citation_rate': summary_metrics.get('content_citation_rate', 0),
            'official_citation_rate': summary_metrics.get('official_citation_rate', 0),
            'scenario_hit_count': summary_metrics.get('scenario_hit_count', 0),
            'high_risk_scenario_count': summary_metrics.get('high_risk_scenario_count', 0),
            'accuracy_score': summary_metrics.get('accuracy_score'),
            'accuracy_status': summary_metrics.get('accuracy_status'),
            'total_questions': metrics.get('total_questions', 0),
            'total_mentions': metrics.get('total_mentions', 0),
        },
        'content': report_data.get('executive_summary', ''),
        'executive_summary': report_data.get('executive_summary', ''),
        'report_markdown': report_data.get('report_markdown', ''),
        'key_findings': report_data.get('key_findings', []),
        'fetch_results_summary': fetch_results_summary,
        'competitors': competitor_metrics,
        'metrics_raw': metrics,
        'report_data': report_data,
        'delta_vs_previous': delta_vs_previous,
        'citation_analysis': metrics.get('citation_analysis', {}),
        'summary_metrics': summary_metrics,
        'scenario_matrix': scenario_matrix,
        'source_overview': source_overview,
        'mention_sentiment_analysis': mention_sentiment_analysis,
        'report_summary': report_v2_sections['report_summary'],
        'scenario_coverage': report_v2_sections['scenario_coverage'],
        'source_section': report_v2_sections['source_section'],
        'mentions_section': report_v2_sections['mentions_section'],
        'report_v2': report_v2_sections['report_v2'],
    }
