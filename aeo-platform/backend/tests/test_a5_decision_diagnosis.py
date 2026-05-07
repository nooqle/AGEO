from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.workflow.a5.canonical import build_canonical_report_artifact
from app.workflow.a5 import diagnosis as diagnosis_module
from app.workflow.a5.diagnosis import (
    REPORT_MODE_BRAND_ENTRY,
    REPORT_MODE_FULL_LANDSCAPE,
    REPORT_MODE_NO_SIGNAL,
    REPORT_MODE_WEAK_SIGNAL,
    build_action_recommendations,
    build_data_audit,
    build_report_route,
    build_risk_concern_analysis,
    build_scenario_diagnostics,
    build_source_intelligence,
    build_structured_report,
    extract_geo_report_diagnosis,
    is_geo_report_topic_judged,
    load_scenario_taxonomy,
    repair_report_artifact,
    require_geo_report_topic_judged,
    validate_report_artifact,
)
from app.services.analytics_service import AnalyticsService
from app.workflow.orchestrator_context_packets import _build_current_artifact_items


def _base_metric_bundle(**overrides):
    data = {
        "total_questions": 4,
        "successful_answers": 16,
        "brand_presence_count": 0,
        "no_brand_rate": 0.75,
        "competitor_pressure": 0.25,
        "official_funnel": {
            "monitor_brand_answer_count": 0,
            "brand_related_link_answer_count": 0,
            "official_link_answer_count": 0,
        },
        "platform_profiles": {
            "deepseek": {"data_status": "ok"},
            "kimi": {"data_status": "ok"},
        },
        "source_summary": {
            "top_domains": [
                {
                    "domain": "pubmed.ncbi.nlm.nih.gov",
                    "display_name": "PubMed",
                    "count": 4,
                    "is_official": False,
                    "sample_titles": ["Nutrition study"],
                },
                {
                    "domain": "iesdouyin.com",
                    "count": 3,
                    "is_official": False,
                    "sample_titles": ["User discussion"],
                },
                {
                    "domain": "docs-share.example",
                    "count": 2,
                    "is_official": False,
                    "sample_titles": ["Copied document"],
                },
            ]
        },
        "sentiment_risk": {
            "top_negative_topics": [
                {
                    "topic": "price",
                    "count": 2,
                    "common_conclusion": "成本高，中型企业难承受",
                },
                {
                    "topic": "deployment",
                    "count": 1,
                    "common_conclusion": "项目周期长，对组织承接要求高",
                },
            ]
        },
        "negative_rate": 0.71,
    }
    data.update(overrides)
    return data


def _input_bundle(industry="管理咨询"):
    return {
        "meta": {"industry": industry},
        "questions": [
            {
                "question_id": "q1",
                "question_text": "数字化转型项目找咨询公司做，是找传统战略咨询公司好，还是找埃森哲这种偏技术落地的好？",
                "intent": "comparison",
                "scene": "其他",
            },
            {
                "question_id": "q2",
                "question_text": "并购后的整合咨询 PMI 具体包含哪些工作内容？",
                "intent": "risk_or_problem",
                "scene": "其他",
            },
            {
                "question_id": "q3",
                "question_text": "ESG 咨询是否实用，还是只是为了写报告？",
                "intent": "trend",
                "scene": "其他",
            },
            {
                "question_id": "q4",
                "question_text": "制造业企业想降本增效，运营优化咨询怎么衡量 ROI？",
                "intent": "how_to_choose",
                "scene": "其他",
            },
        ],
    }


def _analyzer_outputs():
    return {
        "question_coverage_mapper": {
            "question_rows": [
                {
                    "question_id": "q1",
                    "question_text": "数字化转型项目找咨询公司做，是找传统战略咨询公司好，还是找埃森哲这种偏技术落地的好？",
                    "intent": "选项对比",
                    "scene": "其他",
                    "answer_state": "competitor_only",
                    "brand_present": False,
                    "competitors_present": ["埃森哲"],
                },
                {
                    "question_id": "q2",
                    "question_text": "并购后的整合咨询 PMI 具体包含哪些工作内容？",
                    "intent": "风险和顾虑",
                    "scene": "其他",
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                },
                {
                    "question_id": "q3",
                    "question_text": "ESG 咨询是否实用，还是只是为了写报告？",
                    "intent": "趋势判断",
                    "scene": "其他",
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                },
                {
                    "question_id": "q4",
                    "question_text": "制造业企业想降本增效，运营优化咨询怎么衡量 ROI？",
                    "intent": "怎么选",
                    "scene": "其他",
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                },
            ]
        }
    }


def _platform_result(
    platform: str,
    content: str,
    citations=None,
    fetch_method: str | None = None,
):
    return {
        "platform": platform,
        **({"fetch_method": fetch_method} if fetch_method else {}),
        "success": True,
        "answer": {"content": content},
        "citations": citations or [],
    }


def _no_signal_fetch_results():
    return [
        {
            "question_id": "q1",
            "question_text": "数字化转型项目找咨询公司做，是找传统战略咨询公司好，还是找埃森哲这种偏技术落地的好？",
            "platform_results": [
                _platform_result(
                    "deepseek",
                    "这类项目通常先看战略和系统实施边界。埃森哲在技术落地和系统实施方面更常被作为候选。",
                    [
                        {
                            "url": "https://www.accenture.com/cn-zh/services/cloud",
                            "title": "Accenture cloud services",
                        }
                    ],
                    fetch_method="browser",
                )
            ],
        },
        {
            "question_id": "q2",
            "question_text": "并购后的整合咨询 PMI 具体包含哪些工作内容？",
            "platform_results": [
                _platform_result(
                    "kimi",
                    "PMI 通常包括组织、流程、财务、人力和 IT 整合，关键是识别风险和节奏。",
                    [
                        {
                            "url": "https://baike.baidu.com/item/PMI",
                            "title": "PMI 词条",
                        }
                    ],
                    fetch_method="api",
                )
            ],
        },
        {
            "question_id": "q3",
            "question_text": "ESG 咨询是否实用，还是只是为了写报告？",
            "platform_results": [
                _platform_result(
                    "doubao",
                    "ESG 咨询要看监管披露、供应链和融资场景，不能只理解成写报告。",
                    [
                        {
                            "url": "https://www.gov.cn/zhengce/zhengceku/",
                            "title": "监管政策",
                        }
                    ],
                    fetch_method="api",
                )
            ],
        },
        {
            "question_id": "q4",
            "question_text": "制造业企业想降本增效，运营优化咨询怎么衡量 ROI？",
            "platform_results": [
                _platform_result(
                    "yuanbao",
                    "制造业运营优化通常从产线效率、库存周转和质量损耗计算 ROI。",
                    [
                        {
                            "url": "https://docs-share.example/report-copy",
                            "title": "Copied document",
                        }
                    ],
                    fetch_method="api",
                )
            ],
        },
    ]


def _bcg_concern_fetch_results():
    return [
        {
            "question_id": "q1",
            "question_text": "BCG、麦肯锡、贝恩怎么选？",
            "platform_results": [
                _platform_result(
                    "deepseek",
                    "BCG 是顶级战略咨询公司，适合复杂转型和增长战略。但价格高、项目周期长，对组织承接要求复杂，中型企业要评估预算。",
                    [
                        {
                            "url": "https://www.bcg.com/publications",
                            "title": "BCG publications",
                            "canonical_domain": "bcg.com",
                            "site_display_name": "BCG",
                            "site_category": "品牌官网",
                            "source_type": "official",
                            "is_official": True,
                        }
                    ],
                )
            ],
        },
        {
            "question_id": "q2",
            "question_text": "数字化转型项目找 BCG 还是埃森哲？",
            "platform_results": [
                _platform_result(
                    "kimi",
                    "BCG 更偏战略和顶层设计，埃森哲在技术落地上可能更适合。BCG 的交付复杂度和预算门槛较高。",
                    [
                        {
                            "url": "https://www.accenture.com/cn-zh/services",
                            "title": "Accenture services",
                            "canonical_domain": "accenture.com",
                            "site_display_name": "埃森哲",
                            "site_category": "竞品官网",
                            "source_type": "official",
                        }
                    ],
                )
            ],
        },
        {
            "question_id": "q3",
            "question_text": "中型企业预算有限，找 BCG 做组织调整合适吗？",
            "platform_results": [
                _platform_result(
                    "doubao",
                    "BCG 方法论专业，但预算有限和组织承接不足时风险更高，也可能不如本土咨询公司适配。",
                    [
                        {
                            "url": "https://www.mckinsey.com/capabilities",
                            "title": "McKinsey capabilities",
                            "canonical_domain": "mckinsey.com",
                            "site_display_name": "麦肯锡",
                            "site_category": "竞品官网",
                            "source_type": "official",
                        }
                    ],
                )
            ],
        },
    ]


def _weak_signal_fetch_results():
    return [
        {
            "question_id": "s1",
            "question_text": "想给家里老人买蛋白粉增强免疫力，怎么选？",
            "platform_results": [
                _platform_result(
                    "doubao",
                    "可以考虑安利纽崔莱蛋白粉，但要结合老人肠胃耐受、蛋白摄入量和医生建议判断。",
                    [
                        {
                            "url": "https://www.nutrilite.com.cn/protein",
                            "title": "纽崔莱蛋白粉介绍",
                            "canonical_domain": "nutrilite.com.cn",
                            "site_display_name": "纽崔莱官网",
                            "site_category": "品牌官网",
                            "source_type": "official",
                            "is_official": True,
                        }
                    ],
                ),
                _platform_result(
                    "kimi",
                    "老人蛋白粉可以比较汤臣倍健、Swisse 等品牌，重点看蛋白来源和糖分。",
                ),
                _platform_result(
                    "deepseek",
                    "先看日常饮食是否已经足够，再判断是否需要额外补充蛋白粉。",
                ),
            ],
        },
        {
            "question_id": "s2",
            "question_text": "儿童维生素是否需要长期吃？",
            "platform_results": [
                _platform_result(
                    "yuanbao",
                    "儿童维生素不建议长期盲目补充，应先确认饮食、缺乏风险和医生建议。",
                )
            ],
        },
    ]


def _scenario_full_landscape_fetch_results():
    rows = []
    for index in range(1, 11):
        rows.append(
            {
                "question_id": f"scene{index}",
                "question_text": f"高端护肤用户在抗老场景里怎么判断雅姿和其他品牌，第 {index} 题？",
                "platform_results": [
                    _platform_result(
                        "doubao",
                        f"雅姿适合关注抗老、肤感和预算平衡的用户，建议结合兰蔻、SK-II 做成分与价格对比。第 {index} 条。",
                        [
                            {
                                "url": f"https://www.artistry.com.cn/guide/{index}",
                                "title": f"雅姿抗老场景解释 {index}",
                                "canonical_domain": "artistry.com.cn",
                                "site_display_name": "雅姿官网",
                                "site_category": "品牌官网",
                                "source_type": "official",
                                "is_official": True,
                            }
                        ],
                    ),
                    _platform_result(
                        "kimi",
                        f"雅姿可以作为高端护肤候选，重点看敏感肌耐受、功效证据和套装价格。第 {index} 条。",
                    ),
                    _platform_result(
                        "deepseek",
                        f"选择雅姿时应确认抗老诉求、使用频率和预算，并对比竞品的公开评价。第 {index} 条。",
                    ),
                ],
            }
        )
    return rows


def test_data_audit_routes_zero_brand_mentions_to_no_signal():
    audit = build_data_audit(_base_metric_bundle())

    assert audit["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert "sentiment_risk" in audit["blocked_sections"]
    assert "official_conversion" in audit["blocked_sections"]
    assert "platform_preference" in audit["blocked_sections"]
    assert "brand_reputation" in audit["blocked_sections"]
    assert {item["label"] for item in audit["not_judged"]} >= {
        "情感",
        "官网承接",
        "平台偏好",
        "品牌口碑",
    }


def test_scenario_diagnostics_upgrades_question_types_to_business_scenarios():
    diagnostics = build_scenario_diagnostics(_input_bundle(), _analyzer_outputs())
    by_id = {item["question_id"]: item for item in diagnostics["items"]}

    assert by_id["q1"]["decision_scenario"] == "数字化转型咨询选型"
    assert by_id["q1"]["journey_stage"] == "supplier_evaluation"
    assert by_id["q1"]["business_value"] == "high"
    assert by_id["q1"]["brand_status"] == "competitor_only"
    assert by_id["q2"]["decision_scenario"] == "PMI 并购整合"
    assert by_id["q3"]["decision_scenario"] == "ESG 可持续发展"
    assert by_id["q4"]["decision_scenario"] == "制造业降本增效"


def test_scenario_diagnostics_supports_healthcare_supplement_taxonomy():
    bundle = {
        "meta": {"industry": "保健品"},
        "questions": [
            {
                "question_id": "s1",
                "question_text": "想给家里老人买蛋白粉增强免疫力，怎么选？",
                "intent": "how_to_choose",
                "scene": "其他",
            },
            {
                "question_id": "s2",
                "question_text": "儿童维生素是否需要长期吃？",
                "intent": "risk",
                "scene": "其他",
            },
            {
                "question_id": "s3",
                "question_text": "蓝帽子保健品和海外代购安全吗？",
                "intent": "risk",
                "scene": "其他",
            },
            {
                "question_id": "s4",
                "question_text": "预算 500 元给爸妈买什么营养品？",
                "intent": "purchase",
                "scene": "其他",
            },
        ],
    }
    outputs = {
        "question_coverage_mapper": {
            "question_rows": [
                {
                    "question_id": f"s{i}",
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                }
                for i in range(1, 5)
            ]
        }
    }

    diagnostics = build_scenario_diagnostics(bundle, outputs)
    scenarios = {item["decision_scenario"] for item in diagnostics["items"]}

    assert {"老人营养", "儿童营养", "安全合规", "预算选择"} <= scenarios


def test_scenario_taxonomy_covers_core_industry_seed_domains():
    taxonomy = load_scenario_taxonomy()
    all_keywords = {
        keyword
        for industry in taxonomy["industries"]
        for keyword in industry.get("industry_keywords", [])
    }

    assert len(taxonomy["industries"]) >= 12
    assert {
        "新能源汽车",
        "美妆",
        "母婴",
        "消费电子",
        "企业软件",
        "保险",
        "教育",
        "医疗",
        "餐饮",
        "旅游",
        "家装",
        "工业",
    } <= all_keywords


def test_configured_scenarios_work_for_new_core_industries_without_code_changes():
    bundle = {
        "meta": {"industry": "综合测试"},
        "questions": [
            {
                "question_id": "auto1",
                "question_text": "理想L9和问界M9家用SUV怎么选，增程和纯电区别是什么？",
                "intent": "comparison",
                "scene": "其他",
            },
            {
                "question_id": "beauty1",
                "question_text": "敏感肌用修护面霜怎么选，泛红刺痛安全吗？",
                "intent": "risk",
                "scene": "其他",
            },
            {
                "question_id": "saas1",
                "question_text": "历史数据迁移和 API 对接风险怎么评估？SaaS 系统集成前要看什么？",
                "intent": "risk",
                "scene": "其他",
            },
            {
                "question_id": "finance1",
                "question_text": "重疾险和百万医疗险怎么选，理赔是否靠谱？",
                "intent": "comparison",
                "scene": "其他",
            },
            {
                "question_id": "industrial1",
                "question_text": "工厂自动化改造 ROI 怎么算，产能效率提升如何验证？",
                "intent": "value",
                "scene": "其他",
            },
        ],
    }
    outputs = {
        "question_coverage_mapper": {
            "question_rows": [
                {
                    "question_id": question["question_id"],
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                }
                for question in bundle["questions"]
            ]
        }
    }

    diagnostics = build_scenario_diagnostics(bundle, outputs)
    by_id = {item["question_id"]: item for item in diagnostics["items"]}

    assert by_id["auto1"]["decision_scenario"] == "家用 SUV 选型"
    assert by_id["auto1"]["business_value"] == "high"
    assert by_id["beauty1"]["decision_scenario"] == "敏感肌安全"
    assert by_id["saas1"]["decision_scenario"] == "数据迁移与集成"
    assert by_id["finance1"]["decision_scenario"] == "重疾医疗险对比"
    assert by_id["industrial1"]["decision_scenario"] == "降本增效改造"


def test_source_intelligence_uses_a4_url_skill_fields_without_reclassifying():
    source = build_source_intelligence(
        _base_metric_bundle(
            source_summary={
                "total_citations": 72,
                "top_domains": [
                    {
                        "domain": "pcauto.com.cn",
                        "display_name": "太平洋汽车",
                        "count": 35,
                        "is_official": False,
                        "source_type": "other",
                        "site_category": "汽车垂直媒体",
                        "sample_titles": ["增程式与插电混动怎么选"],
                    },
                    {
                        "domain": "abc123x.example",
                        "count": 2,
                        "is_official": False,
                        "source_type": "other",
                        "site_category": "缺乏特征，无法识别",
                        "sample_titles": ["unknown"],
                    },
                ],
            }
        ),
        competitors=[{"name": "Competitor", "website": "https://competitor.com"}],
    )
    by_domain = {item["domain"]: item for item in source["domains"]}

    assert by_domain["pcauto.com.cn"]["source_type_label"] == "汽车垂直媒体"
    assert by_domain["pcauto.com.cn"]["site_name"] == "太平洋汽车"
    assert by_domain["pcauto.com.cn"]["site_display"] == "太平洋汽车（pcauto.com.cn）"
    assert by_domain["abc123x.example"]["source_type"] == "unknown"
    assert by_domain["abc123x.example"]["source_type_label"] == "未知"
    assert "规则库" not in by_domain["abc123x.example"]["recommended_action"]


def test_risk_concern_classifier_remaps_negative_to_decision_concerns():
    risk = build_risk_concern_analysis(_base_metric_bundle(), _analyzer_outputs())
    labels = {item["label"] for item in risk["items"]}

    assert "价格门槛" in labels
    assert "交付复杂度" in labels
    assert "竞争替代风险" in labels
    assert "不一定代表品牌口碑负面" in risk["summary"]["narrative"]


def test_no_signal_report_has_required_structure_and_no_forbidden_copy():
    metrics = _base_metric_bundle()
    audit = build_data_audit(metrics)
    route = build_report_route(audit, report_kind="panorama")
    scenarios = build_scenario_diagnostics(_input_bundle(), _analyzer_outputs())
    source = build_source_intelligence(metrics, competitors=[])
    risk = build_risk_concern_analysis(metrics, _analyzer_outputs())
    recommendations = build_action_recommendations(
        data_audit=audit,
        scenario_diagnostics=scenarios,
        source_intelligence=source,
        risk_concern_analysis=risk,
        metric_bundle=metrics,
        brand_name="波士顿咨询公司",
    )
    report = build_structured_report(
        brand_name="波士顿咨询公司",
        report_kind="panorama",
        metric_bundle=metrics,
        data_audit=audit,
        report_route=route,
        scenario_diagnostics=scenarios,
        source_intelligence=source,
        risk_concern_analysis=risk,
        action_recommendations=recommendations,
    )

    markdown = report["report_markdown"]
    assert "品牌 AI 答案未进入诊断报告" in markdown
    for heading in [
        "### 1. 本轮结论",
        "### 2. 问题触发类型",
        "### 3. 竞品偶发进入",
        "### 4. 内容缺口假设",
        "### 5. 下一轮验证计划",
        "### 6. 暂不判断事项",
    ]:
        assert heading in markdown
    assert "N/A" not in markdown
    assert "官网承接不足" not in markdown
    assert "品牌负面比例不高" not in markdown
    assert "品牌负向提及率" not in markdown
    assert "无法计算官网引用转化率" in markdown

    artifact = {
        "report_markdown": markdown,
        "full_markdown": markdown,
        "data_audit": audit,
        "report_mode": audit["report_mode"],
        "metrics": {"negative_rate": None},
        "action_recommendations": recommendations,
        "executive_summary": report["executive_summary"],
        "executive_summary_text": report["executive_summary"]["one_line_judgment"],
        "operations_diagnosis": report["operations_diagnosis"],
        "diagnostic_conclusions": report["diagnostic_conclusions"],
        "report_sections": report["report_sections"],
    }
    result = validate_report_artifact(artifact)
    assert result["pass"], result


def test_canonical_artifact_routes_no_signal_into_single_geo_report():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-no-signal",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "波士顿咨询公司",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["BCG", "波士顿咨询"],
        },
        competitors=[
            {"name": "埃森哲", "website": "https://www.accenture.com"},
            {"name": "麦肯锡", "website": "https://www.mckinsey.com"},
        ],
        fetch_results=_no_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    markdown = artifact["report_markdown"]
    assert artifact["artifact_kind"] == "geo_report"
    assert artifact["report_kind"] == "panorama"
    assert artifact["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert artifact["metric_bundle"]["brand_presence_count"] == 0
    assert artifact["validator_result"]["pass"] is True
    assert isinstance(artifact["executive_summary"], dict)
    assert isinstance(artifact["executive_summary_text"], str)
    assert artifact["executive_summary_text"]
    assert len(artifact["report_sections"]) == 2
    assert {section["section_name"] for section in artifact["report_sections"]} == {
        "executive_summary",
        "operations_diagnosis",
    }
    assert artifact["diagnosis_modules"]["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert "品牌 AI 答案未进入诊断报告" in markdown
    for heading in [
        "### 1. 本轮结论",
        "### 2. 问题触发类型",
        "### 3. 竞品偶发进入",
        "### 4. 内容缺口假设",
        "### 5. 下一轮验证计划",
        "### 6. 暂不判断事项",
    ]:
        assert heading in markdown
    assert "N/A" not in markdown
    assert "官网承接不足" not in markdown
    assert "品牌负面比例不高" not in markdown
    assert "品牌负向提及率" not in markdown
    assert "无法计算官网引用转化率" in markdown
    assert {item["label"] for item in artifact["data_audit"]["not_judged"]} >= {
        "情感",
        "官网承接",
        "平台偏好",
        "品牌口碑",
    }
    for field in [
        "data_audit",
        "report_route",
        "scenario_diagnostics",
        "source_intelligence",
        "risk_concern_analysis",
        "action_recommendations",
        "executive_report",
        "executive_summary_text",
        "report_sections",
        "diagnostic_conclusions",
        "operations_diagnosis",
        "validator_result",
    ]:
        assert field in artifact


def test_canonical_artifact_remaps_high_negative_samples_to_risk_concerns():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-risk-concern",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "BCG",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["波士顿咨询公司", "波士顿咨询"],
        },
        competitors=[
            {"name": "埃森哲", "website": "https://www.accenture.com"},
            {"name": "麦肯锡", "website": "https://www.mckinsey.com"},
        ],
        fetch_results=_bcg_concern_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    labels = {item["label"] for item in artifact["risk_concern_analysis"]["items"]}
    assert "价格门槛" in labels
    assert "交付复杂度" in labels
    assert "适配边界" in labels
    assert "竞争替代风险" in labels
    assert artifact["validator_result"]["pass"] is True
    assert "负面信息比例不高" not in artifact["report_markdown"]
    assert "不一定代表品牌口碑负面" in artifact["report_markdown"]
    assert "引用来源分析" in artifact["report_markdown"]
    assert "来源证据权" not in artifact["report_markdown"]
    assert "推荐动作" in artifact["report_markdown"]


def test_operational_report_keeps_legacy_detail_density_in_new_structure():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-operational-density",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "BCG",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["波士顿咨询公司", "波士顿咨询"],
        },
        competitors=[
            {"name": "埃森哲", "website": "https://www.accenture.com"},
            {"name": "麦肯锡", "website": "https://www.mckinsey.com"},
        ],
        fetch_results=_bcg_concern_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    markdown = artifact["report_markdown"]
    operations = artifact["operations_diagnosis"]

    assert "进入拆解" in markdown
    assert "### 核心指标" in markdown
    assert "品牌可见度" in markdown
    assert "官网引用转化率" in markdown
    assert "正向情绪占比" in markdown
    assert "中性情绪占比" in markdown
    assert "负向/风险顾虑信号占比" in markdown
    assert "来源类型结构" in markdown
    assert "高频来源网站" in markdown
    assert "埃森哲（accenture.com）" in markdown
    assert "麦肯锡（mckinsey.com）" in markdown
    assert "### 5. 情绪探查" in markdown
    assert "情绪分布：正向" in markdown
    assert "负向信号对应的决策顾虑" in markdown
    assert "负向/顾虑样本定位" in markdown
    assert "问题：BCG、麦肯锡、贝恩怎么选？" in markdown
    assert "答案结论：" in markdown
    assert "答案结论：暂无摘录" not in markdown
    assert "负向信号来源：模型自身归纳 100.0%" not in markdown
    assert "### 7. 平台差异" in markdown
    assert "友好场景：其他" not in markdown
    assert "易缺席场景：其他" not in markdown
    assert "引用偏好：其他" not in markdown
    assert "引用偏好：官网/官方文档/白皮书、其他" not in markdown
    assert "高风险/需复盘问题" in markdown
    assert "缺席/同台问题样本" in markdown
    assert artifact["executive_summary"]["core_metrics"]
    assert operations["core_metrics"]
    assert operations["sentiment_probe"]["distribution"]
    assert operations["scenario_summary"]
    assert operations["scenario_summary"][0]["brand_entry_rate"] is not None
    assert operations["platform_diagnostics"]["items"]
    assert operations["sample_appendix"]["high_risk_questions"]
    assert operations["sample_appendix"]["source_samples"]


def _structured_report_for_mode(report_mode: str):
    brand_presence = {
        REPORT_MODE_NO_SIGNAL: 0,
        REPORT_MODE_WEAK_SIGNAL: 2,
        REPORT_MODE_BRAND_ENTRY: 6,
        REPORT_MODE_FULL_LANDSCAPE: 12,
    }[report_mode]
    successful_answers = 40 if report_mode == REPORT_MODE_FULL_LANDSCAPE else 16
    metrics = _base_metric_bundle(
        brand_presence_count=brand_presence,
        successful_answers=successful_answers,
        brand_visibility=(
            brand_presence / successful_answers if successful_answers else 0
        ),
        official_conversion_rate=0.15 if brand_presence else None,
        official_funnel={
            "monitor_brand_answer_count": brand_presence,
            "brand_related_link_answer_count": max(brand_presence, 0),
            "official_link_answer_count": 1 if brand_presence else 0,
        },
    )
    audit = build_data_audit(metrics)
    assert audit["report_mode"] == report_mode
    route = build_report_route(audit, report_kind="panorama")
    scenarios = build_scenario_diagnostics(_input_bundle(), _analyzer_outputs())
    source = build_source_intelligence(metrics, competitors=[])
    risk = build_risk_concern_analysis(metrics, _analyzer_outputs())
    recommendations = build_action_recommendations(
        data_audit=audit,
        scenario_diagnostics=scenarios,
        source_intelligence=source,
        risk_concern_analysis=risk,
        metric_bundle=metrics,
        brand_name="BCG",
    )
    return build_structured_report(
        brand_name="BCG",
        report_kind="panorama",
        metric_bundle=metrics,
        data_audit=audit,
        report_route=route,
        scenario_diagnostics=scenarios,
        source_intelligence=source,
        risk_concern_analysis=risk,
        action_recommendations=recommendations,
    )


def test_structured_report_generation_covers_all_report_modes():
    expected_headings = {
        REPORT_MODE_NO_SIGNAL: "### 1. 本轮结论",
        REPORT_MODE_WEAK_SIGNAL: "### 1. 数据状态",
        REPORT_MODE_BRAND_ENTRY: "### 1. 数据状态",
        REPORT_MODE_FULL_LANDSCAPE: "### 1. 数据状态",
    }

    for mode, heading in expected_headings.items():
        report = _structured_report_for_mode(mode)
        markdown = report["report_markdown"]
        assert heading in markdown
        assert "## 高管版摘要" in markdown
        assert "## 运营版诊断" in markdown
        assert len(report["report_sections"]) == 2
        assert report["operations_diagnosis"]["mode"] == mode
        for conclusion in report["diagnostic_conclusions"]:
            assert {"fact", "detail"} <= set(conclusion)
            assert conclusion["fact"]
            assert conclusion["detail"]


def test_weak_signal_report_does_not_use_strong_claim_language():
    report = _structured_report_for_mode(REPORT_MODE_WEAK_SIGNAL)
    markdown = report["report_markdown"]

    assert "稳定口碑" not in markdown
    assert "明确平台偏好" not in markdown
    assert "长期趋势" not in markdown
    assert "当前仍不能写成稳定声誉结论" not in markdown


def test_weak_signal_key_findings_use_evidence_detail_not_empty_claims():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-weak-signal-detail",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "安利纽崔莱",
            "industry": "保健品",
            "official_website": "https://www.nutrilite.com.cn",
            "brand_keywords": ["纽崔莱", "Nutrilite"],
        },
        competitors=[
            {"name": "汤臣倍健", "website": "https://www.by-health.com"},
            {"name": "Swisse", "website": "https://www.swisse.com"},
        ],
        fetch_results=_weak_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    markdown = artifact["report_markdown"]
    data_status = next(
        item
        for item in artifact["diagnostic_conclusions"]
        if item.get("code") == "data_status"
    )

    assert artifact["report_mode"] == REPORT_MODE_WEAK_SIGNAL
    assert "**详解**" in markdown
    assert "**解释**" not in markdown
    assert "**边界**" not in markdown
    assert "**动作**" not in markdown
    assert "按报告模式推进场景" not in markdown
    assert "豆包" in data_status["detail"]
    assert "想给家里老人买蛋白粉增强免疫力，怎么选？" in data_status["detail"]
    assert "安利纽崔莱蛋白粉" in data_status["detail"]


def test_structured_report_localizes_internal_codes_for_readers():
    report = _structured_report_for_mode(REPORT_MODE_WEAK_SIGNAL)
    markdown = report["report_markdown"]

    assert "报告模式：弱信号观察" in markdown
    assert "决策阶段 供应商/选项评估" in markdown
    assert "业务价值 高" in markdown
    assert "如果某项指标显示 0.0%" in markdown
    for raw_text in (
        "报告模式：WEAK_SIGNAL",
        "决策阶段 supplier_evaluation",
        "决策阶段 purchase_evaluation",
        "决策阶段 awareness",
        "业务价值 medium",
        "业务价值 high",
        "品牌状态 competitor_only",
    ):
        assert raw_text not in markdown


def test_scenario_full_landscape_artifact_keeps_scenario_report_title():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-scenario-title",
        entity_id=None,
        analysis_mode="scenario",
        brand_profile={
            "brand_name": "雅姿",
            "industry": "高端护肤",
            "official_website": "https://www.artistry.com.cn",
            "brand_keywords": ["Artistry"],
        },
        competitors=[
            {"name": "兰蔻", "website": "https://www.lancome.com.cn"},
            {"name": "SK-II", "website": "https://www.sk-ii.com.cn"},
        ],
        fetch_results=_scenario_full_landscape_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    assert artifact["report_kind"] == "scenario"
    assert artifact["report_mode"] == REPORT_MODE_FULL_LANDSCAPE
    assert artifact["report_route"]["title"] == "用户场景分析报告"
    assert artifact["title"] == "雅姿｜用户场景分析报告"
    assert artifact["headline"] == "雅姿｜用户场景分析报告"
    first_line = artifact["report_markdown"].splitlines()[0]
    assert first_line == "# 雅姿｜用户场景分析报告"
    assert "品牌 GEO 全景诊断报告" not in first_line
    source_stats = artifact["source_intelligence"]["official_source_stats"]
    assert source_stats["citation_count"] == 10
    assert source_stats["distinct_url_count"] == 10
    assert source_stats["answer_count"] == 10
    assert source_stats["question_count"] == 10
    markdown = artifact["report_markdown"]
    assert "### 4. 引用来源分析" in markdown
    assert "官网引用统计：官网链接被引用 10 次" in markdown
    assert "https://www.artistry.com.cn/guide/1" in markdown
    assert "平台：豆包" in markdown
    assert "问题：「高端护肤用户在抗老场景里怎么判断雅姿和其他品牌" in markdown
    assert "答案摘录：「雅姿适合关注抗老、肤感和预算平衡的用户" in markdown


def test_repair_report_artifact_fixes_repairable_copy_only():
    report = _structured_report_for_mode(REPORT_MODE_WEAK_SIGNAL)
    artifact = {
        "report_markdown": (
            report["report_markdown"]
            + "\n官网承接不足。品牌负面比例不高。N/A。稳定口碑。明确平台偏好。长期趋势。"
        ),
        "full_markdown": (
            report["report_markdown"]
            + "\n官网承接不足。品牌负面比例不高。N/A。稳定口碑。明确平台偏好。长期趋势。"
        ),
        "data_audit": {"report_mode": REPORT_MODE_WEAK_SIGNAL},
        "metrics": {"negative_rate": 0.71},
        "action_recommendations": report["operations_diagnosis"][
            "action_recommendations"
        ],
        "executive_summary": report["executive_summary"],
        "executive_summary_text": report["executive_summary"]["one_line_judgment"],
        "operations_diagnosis": report["operations_diagnosis"],
        "diagnostic_conclusions": report["diagnostic_conclusions"],
        "report_sections": report["report_sections"],
        "risk_concern_analysis": {
            "summary": {"narrative": "本轮 AI 回答中的风险信号应按决策顾虑理解。"}
        },
    }

    first = validate_report_artifact(artifact)
    assert not first["pass"]
    repaired = repair_report_artifact(artifact)
    second = validate_report_artifact(repaired)
    assert second["pass"], second
    assert repaired["repair_history"]

    unrecoverable = {
        "report_markdown": "正文",
        "data_audit": {"report_mode": REPORT_MODE_BRAND_ENTRY},
    }
    still_bad = validate_report_artifact(repair_report_artifact(unrecoverable))
    assert not still_bad["pass"]
    assert "executive_summary 必须是结构化对象。" in still_bad["required_fixes"]


def test_extract_geo_report_diagnosis_prefers_structured_modules():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-diagnosis-helper",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "BCG",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["波士顿咨询"],
        },
        competitors=[],
        fetch_results=_bcg_concern_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    diagnosis = extract_geo_report_diagnosis(artifact)
    assert diagnosis["report_mode"] == artifact["report_mode"]
    assert diagnosis["data_audit"] == artifact["data_audit"]
    assert diagnosis["action_recommendations"] == artifact["action_recommendations"]


def test_diagnosis_policy_blocks_not_judged_follow_up_topics():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-policy-helper",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "波士顿咨询公司",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["BCG", "波士顿咨询"],
        },
        competitors=[
            {"name": "埃森哲", "website": "https://www.accenture.com"},
        ],
        fetch_results=_no_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )
    diagnosis = extract_geo_report_diagnosis(artifact)

    assert diagnosis["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert "official_conversion" in diagnosis["blocked_sections"]
    assert diagnosis["metric_eligibility"]["official_conversion"]["judgeable"] is False
    assert is_geo_report_topic_judged(diagnosis, "官网承接") is False
    assert is_geo_report_topic_judged(diagnosis, "平台偏好") is False
    assert is_geo_report_topic_judged(diagnosis, "品牌口碑") is False

    decision = require_geo_report_topic_judged(artifact, "官网引用转化率")
    assert decision["allowed"] is False
    assert decision["topic"] == "official_conversion"
    assert "复测计划" in decision["fallback_action"]


def test_dashboard_projection_exposes_structured_diagnosis_modules():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-dashboard-diagnosis",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "波士顿咨询公司",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["BCG", "波士顿咨询"],
        },
        competitors=[],
        fetch_results=_no_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )
    service = AnalyticsService(db=None)  # type: ignore[arg-type]

    payload = service._extract_v2_payload(artifact)
    home = service._build_dashboard_home_from_projection(artifact)

    assert payload["diagnosis_modules"]["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert payload["diagnosis_modules"]["not_judged"]
    assert home is not None
    assert home["diagnosisModules"]["report_mode"] == REPORT_MODE_NO_SIGNAL
    assert home["latestReport"]["subtitle"] == artifact["executive_summary_text"]
    assert home["latestReport"]["scopeLabel"] == "品牌全景口径"
    assert home["latestReport"]["questionSetLabel"] == "本轮品牌全景问题集"
    assert "4 个问题" in home["latestReport"]["sampleSummary"]
    assert "4 个 AI 来源" in home["latestReport"]["sampleSummary"]
    assert home["latestReport"]["questionPreview"][0].startswith("数字化转型项目")
    ai_sources = {row["platform"] for row in home["platformDiagnosis"]}
    assert {"DeepSeek网页版", "Kimi API", "豆包API", "元宝API"} <= ai_sources
    artifact["input_bundle"]["questions"][0]["scene"] = "brand_direct"
    home_with_internal_scope = service._build_dashboard_home_from_projection(artifact)
    assert home_with_internal_scope is not None
    assert home_with_internal_scope["latestReport"]["questionSetLabel"] == "品牌直问"
    assert (
        "brand_direct"
        not in home_with_internal_scope["latestReport"]["questionSetLabel"]
    )
    risk_evidences = [risk.get("evidence") for risk in home["risks"]]
    assert "其他" not in risk_evidences
    assert "不提任何品牌" in risk_evidences


def test_dashboard_monitor_mode_filter_keeps_panorama_and_scenario_separate():
    service = AnalyticsService(db=None)  # type: ignore[arg-type]

    panorama_output = {"_report_kind": "panorama"}
    legacy_output = {"_report_kind": ""}
    scenario_output = {"_report_kind": "scenario"}
    persona_output = {"_report_kind": "persona"}

    assert service._dashboard_report_kind(persona_output) == "scenario"
    assert service._matches_dashboard_monitor_mode(panorama_output, "panorama")
    assert service._matches_dashboard_monitor_mode(legacy_output, "panorama")
    assert not service._matches_dashboard_monitor_mode(scenario_output, "panorama")

    assert service._matches_dashboard_monitor_mode(scenario_output, "scenario")
    assert service._matches_dashboard_monitor_mode(persona_output, "scenario")
    assert not service._matches_dashboard_monitor_mode(panorama_output, "scenario")


def test_dashboard_home_normalizes_persona_report_kind_for_frontend_mode():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-dashboard-persona",
        entity_id=None,
        analysis_mode="scenario",
        brand_profile={
            "brand_name": "波士顿咨询公司",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["BCG", "波士顿咨询"],
        },
        competitors=[],
        fetch_results=_no_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )
    artifact["meta"]["report_kind"] = "persona"
    artifact["dashboard_projection"]["report_kind"] = "persona"
    service = AnalyticsService(db=None)  # type: ignore[arg-type]

    home = service._build_dashboard_home_from_projection(artifact)

    assert home is not None
    assert home["latestReport"]["reportKind"] == "scenario"
    assert home["latestReport"]["scopeLabel"] == "用户场景口径"


def test_orchestrator_context_summarizes_structured_not_judged_policy():
    artifact = build_canonical_report_artifact(
        session_id="session-a5-context-not-judged",
        entity_id=None,
        analysis_mode="panorama",
        brand_profile={
            "brand_name": "波士顿咨询公司",
            "industry": "管理咨询",
            "official_website": "https://www.bcg.com",
            "brand_keywords": ["BCG", "波士顿咨询"],
        },
        competitors=[],
        fetch_results=_no_signal_fetch_results(),
        simulated_questions=None,
        base_metrics=None,
    )

    items = _build_current_artifact_items({"report": artifact, "metrics": {}})

    assert items
    assert "暂不判断=情感,官网承接,平台偏好,品牌口碑" in items[0].summary


def test_scenario_taxonomy_and_a4_source_fields_drive_report_inputs():
    scenario_taxonomy = load_scenario_taxonomy()

    assert scenario_taxonomy["industries"]

    bundle = {
        "meta": {"industry": "保健品"},
        "questions": [
            {
                "question_id": "cfg1",
                "question_text": "直销品牌和药店品牌区别是什么？",
                "intent": "comparison",
                "scene": "其他",
            }
        ],
    }
    outputs = {
        "question_coverage_mapper": {
            "question_rows": [
                {
                    "question_id": "cfg1",
                    "answer_state": "no_brand",
                    "brand_present": False,
                    "competitors_present": [],
                }
            ]
        }
    }

    diagnostics = build_scenario_diagnostics(bundle, outputs)
    assert diagnostics["items"][0]["decision_scenario"] == "直销信任"

    source = build_source_intelligence(
        _base_metric_bundle(
            source_summary={
                "top_domains": [
                    {
                        "domain": "baike.baidu.com",
                        "count": 3,
                        "is_official": False,
                        "source_type": "other",
                        "site_category": "百科/知识库",
                        "sample_titles": ["百科词条"],
                    }
                ]
            }
        ),
        competitors=[],
    )
    assert source["domains"][0]["source_type_label"] == "百科/知识库"


def test_taxonomy_config_failure_uses_safe_fallback(monkeypatch):
    monkeypatch.setattr(diagnosis_module, "load_scenario_taxonomy", lambda: {})

    diagnostics = build_scenario_diagnostics(_input_bundle(), _analyzer_outputs())
    assert diagnostics["items"][0]["decision_scenario"] == "数字化转型咨询选型"

    source = build_source_intelligence(
        _base_metric_bundle(
            source_summary={
                "top_domains": [
                    {
                        "domain": "pubmed.ncbi.nlm.nih.gov",
                        "count": 1,
                        "is_official": False,
                        "source_type": "other",
                        "site_category": "学术/医学",
                        "sample_titles": ["study"],
                    }
                ]
            }
        ),
        competitors=[],
    )
    assert source["domains"][0]["source_type_label"] == "学术/医学"
