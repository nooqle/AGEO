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
    competitor_battles: list[dict[str, Any]],
    risk_map: list[dict[str, Any]],
    action_queue: list[dict[str, Any]],
    source_overview: dict[str, Any],
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
            f"官网引用率 {summary_metrics.get('official_citation_rate', 0):.1%} | "
            f"有效场景 {summary_metrics.get('scenario_hit_count', 0)}/{summary_metrics.get('scenario_total', 0)}"
        ),
        'overallScore': metrics.get('bwvs_index', 0),
        'bwvs_breakdown': metrics.get('bwvs_breakdown', {}),
        'scoreBand': (
            '优秀' if metrics.get('bwvs_index', 0) >= 70
            else '良好' if metrics.get('bwvs_index', 0) >= 40
            else '需改进'
        ),
        'metrics': {
            'brand_mention_rate': summary_metrics.get('brand_mention_rate', 0),
            'official_citation_rate': summary_metrics.get('official_citation_rate', 0),
            'scenario_hit_count': summary_metrics.get('scenario_hit_count', 0),
            'missing_high_value_scenario_count': summary_metrics.get('missing_high_value_scenario_count', 0),
            'high_risk_scenario_count': summary_metrics.get('high_risk_scenario_count', 0),
            'total_questions': metrics.get('total_questions', 0),
            'total_mentions': metrics.get('total_mentions', 0),
        },
        'insights': [
            {
                'type': 'strength',
                'title': (s.get('title', str(s)) if isinstance(s, dict) else str(s)),
                'description': (s.get('evidence', s.get('title', str(s))) if isinstance(s, dict) else str(s)),
            }
            for s in report_data.get('strengths', [])
        ] + [
            {
                'type': 'weakness',
                'title': (w.get('title', str(w)) if isinstance(w, dict) else str(w)),
                'description': (w.get('evidence', w.get('title', str(w))) if isinstance(w, dict) else str(w)),
            }
            for w in report_data.get('weaknesses', [])
        ] + [
            {'type': 'opportunity', 'title': o, 'description': o}
            for o in report_data.get('opportunities', [])
        ],
        'recommendations': [
            {
                'priority': idx + 1,
                'title': r.get('title', ''),
                'rationale': r.get('action', r.get('improvement_area', '')),
                'eeat_dimension': r.get('eeat_dimension', ''),
                'current_strength': r.get('current_strength', ''),
                'expected_impact': r.get('expected_impact', ''),
                'difficulty': r.get('difficulty', ''),
                'timeline': r.get('timeline', ''),
            }
            for idx, r in enumerate(report_data.get('actionable_recommendations', []))
        ],
        'content': report_data.get('executive_summary', ''),
        'executive_summary': report_data.get('executive_summary', ''),
        'key_findings': report_data.get('key_findings', []),
        'strengths': report_data.get('strengths', []),
        'weaknesses': report_data.get('weaknesses', []),
        'opportunities': report_data.get('opportunities', []),
        'threats': report_data.get('threats', []),
        'action_plan': report_data.get('action_plan', {}),
        'platform_breakdown': metrics.get('platform_breakdown', {}),
        'sentiment_distribution': metrics.get('sentiment_distribution', {}),
        'fetch_results_summary': fetch_results_summary,
        'competitors': competitor_metrics,
        'metrics_raw': metrics,
        'report_data': report_data,
        'delta_vs_previous': delta_vs_previous,
        'industry_insights': report_data.get('industry_insights'),
        'platform_analysis': report_data.get('platform_analysis', []),
        'competitor_deep_analysis': report_data.get('competitor_deep_analysis'),
        'actionable_recommendations': report_data.get('actionable_recommendations', []),
        'risk_alerts': report_data.get('risk_alerts', []),
        'citation_analysis': metrics.get('citation_analysis', {}),
        'keyword_analysis': metrics.get('keyword_analysis', {}),
        'summary_metrics': summary_metrics,
        'scenario_matrix': scenario_matrix,
        'competitor_battles': competitor_battles,
        'risk_map': risk_map,
        'action_queue': action_queue,
        'source_overview': source_overview,
        'report_summary': report_v2_sections['report_summary'],
        'scenario_coverage': report_v2_sections['scenario_coverage'],
        'competitor_battle': report_v2_sections['competitor_battle'],
        'risk_section': report_v2_sections['risk_section'],
        'source_section': report_v2_sections['source_section'],
        'action_queue_section': report_v2_sections['action_queue_section'],
        'report_v2': report_v2_sections['report_v2'],
    }
