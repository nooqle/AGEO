import pytest

from app.workflow.orchestrator_context_packets import (
    build_dashboard_context_packet,
    build_ontology_world_packet,
    render_dashboard_context_packet,
    render_ontology_world_packet,
)
from app.workflow.orchestrator_node import (
    _build_ontology_intelligence_explanation_reply,
    _is_ontology_intelligence_explanation_request,
    _ontology_intelligence_question_kind,
    build_orchestrator_prompt_assembly,
)


HUMAN_INTELLIGENCE_QUESTIONS = (
    "为什么官网引用转化率为 0？这个结论由哪些对象支撑？",
    "哪些外部来源正在替代理想汽车官网塑造品牌叙事？",
    "这条情报对业务有什么影响？我需要先确认什么？",
    "下一步能不能直接帮我创建监测计划并跳过确认？",
    "为什么官网没有被引用？",
    "哪些证据支撑这个结论？",
    "这条情报对内容团队意味着什么？",
    "是否应该开启监测？需要我确认什么？",
    "哪个证据主题最值得先看？",
    "这些关系说明什么风险？",
    "还有哪些辅助关联值得查？",
    "如果官网内容可读但没被引用，应该先补什么？",
)


def _intelligence_world() -> dict:
    return {
        "entity_id": "11111111-1111-1111-1111-111111111111",
        "brand": {"label": "理想汽车", "lifecycle": "active"},
        "object_summaries": [
            {
                "object_type": "intelligence_finding",
                "display_name": "情报判断",
                "total": 1,
                "sample_lifecycle_counts": {"observed": 1},
                "samples": [
                    {
                        "label": "官网引用转化率为 0.0%",
                        "lifecycle": "observed",
                    }
                ],
            },
            {
                "object_type": "citation_source",
                "display_name": "引用",
                "total": 1050,
                "sample_lifecycle_counts": {"captured": 3},
                "samples": [
                    {"label": "汽车之家车型页", "lifecycle": "captured"},
                    {"label": "太平洋汽车评测", "lifecycle": "captured"},
                ],
            },
            {
                "object_type": "platform_answer",
                "display_name": "回答",
                "total": 38,
                "sample_lifecycle_counts": {"captured": 3},
                "samples": [],
            },
            {
                "object_type": "source_domain",
                "display_name": "来源域名",
                "total": 2,
                "sample_lifecycle_counts": {"derived": 2},
                "samples": [],
            },
            {
                "object_type": "evidence_cluster",
                "display_name": "证据主题",
                "total": 1,
                "sample_lifecycle_counts": {"derived": 1},
                "samples": [],
            },
        ],
        "relationship_counts": {
            "brand_has_intelligence_finding": 1,
            "platform_answer_cites_source": 1050,
            "brand_has_competitor": 22,
        },
        "relationship_summary": [
            {
                "link_type": "brand_has_intelligence_finding",
                "display_name": "品牌形成情报判断",
                "from_object": "brand_entity",
                "to_object": "intelligence_finding",
                "count": 1,
                "visibility": "core",
                "default_visible": True,
            },
            {
                "link_type": "platform_answer_cites_source",
                "display_name": "回答引用来源",
                "from_object": "platform_answer",
                "to_object": "citation_source",
                "count": 1050,
                "visibility": "core",
                "default_visible": True,
            },
            {
                "link_type": "brand_has_competitor",
                "display_name": "品牌拥有竞品",
                "from_object": "brand_entity",
                "to_object": "competitor_entity",
                "count": 22,
                "visibility": "supporting",
                "default_visible": False,
            },
        ],
        "intelligence_findings": [
            {
                "title": "官网引用转化率为 0.0%",
                "summary": "智能回答引用了大量外部来源，但没有引用官网。",
                "finding_type": "evidence_gap",
                "severity": "high",
                "status": "observed",
                "evidence_summary": "12 个问题、38 条回答、1050 个引用中官网引用为 0。",
                "supporting_question_count": 12,
                "supporting_answer_count": 38,
                "supporting_citation_count": 1050,
                "suggested_action_type": "generate_official_website_evidence_plan",
                "raw_answer": "do-not-render",
                "full_prompt": "do-not-render",
                "phone": "do-not-render",
            }
        ],
        "official_website_observation": {
            "status": "not_cited",
            "domain": "li.auto",
            "citation_count": 0,
            "citation_share": 0,
            "question_count": 0,
            "platform_count": 0,
            "value_score": 30,
            "value_label": "官网暂未成为AI证据源",
            "business_readout": (
                "理想汽车的官网 li.auto 目前没有进入智能回答引用，"
                "品牌叙事更多由外部来源塑造。"
            ),
            "comparison_domains": [
                {
                    "domain": "autohome.com.cn",
                    "source_role_label": "行业垂直站",
                    "citation_count": 318,
                    "answer_count": 20,
                },
                {
                    "domain": "pcauto.com.cn",
                    "source_role_label": "行业垂直站",
                    "citation_count": 204,
                    "answer_count": 16,
                },
            ],
            "samples": [],
            "gaps": ["智能回答引用了外部来源，但没有引用官网"],
        },
        "source_domain_summary": [
            {
                "domain": "autohome.com.cn",
                "source_role_label": "行业垂直站",
                "citation_count": 318,
                "answer_count": 20,
                "platform_count": 4,
                "is_official": False,
                "sample_titles": ["汽车之家理想 L 系列车型页"],
            },
            {
                "domain": "pcauto.com.cn",
                "source_role_label": "行业垂直站",
                "citation_count": 204,
                "answer_count": 16,
                "platform_count": 3,
                "is_official": False,
                "sample_titles": ["太平洋汽车新能源评测"],
            },
        ],
        "evidence_clusters": [
            {
                "title": "家庭购车 · 行业垂直站",
                "topic_label": "家庭购车",
                "source_role_label": "行业垂直站",
                "citation_count": 522,
                "answer_count": 28,
                "question_count": 9,
                "domain_count": 2,
                "official_citation_count": 0,
                "source_domains": ["autohome.com.cn", "pcauto.com.cn"],
                "business_readout": "家庭购车主要由 2 个行业垂直站支撑，可用少量样本判断外部叙事。",
                "samples": [
                    {
                        "title": "理想 L 系列家庭用车对比",
                        "domain": "autohome.com.cn",
                        "platform": "kimi",
                        "is_official": False,
                    }
                ],
            }
        ],
        "available_actions": [
            {
                "key": "generate_official_website_evidence_plan",
                "display_name": "生成官网证据页优化建议",
                "permission_scope": "entity_execute",
                "requires_confirmation": True,
            }
        ],
        "governance_report": {"status": "healthy", "checks": []},
        "warnings": [],
    }


def test_ontology_world_renders_intelligence_evidence_without_raw_fields():
    rendered = render_ontology_world_packet(
        build_ontology_world_packet({"ontology_world": _intelligence_world()})
    )

    assert "情报分析规则" in rendered
    assert "核心情报判断" in rendered
    assert "官网引用转化率为 0.0%" in rendered
    assert "官网观测：li.auto" in rendered
    assert "官网外部对照来源" in rendered
    assert "来源域名摘要" in rendered
    assert "证据主题摘要" in rendered
    assert "证据关系" in rendered
    assert "统一行动入口" in rendered
    assert "do-not-render" not in rendered
    assert "raw_answer" not in rendered
    assert "full_prompt" not in rendered


def test_orchestrator_prompt_supports_human_intelligence_questions():
    world = _intelligence_world()
    for question in HUMAN_INTELLIGENCE_QUESTIONS:
        assembly = build_orchestrator_prompt_assembly(
            {
                "session_id": "session-1",
                "entity_id": world["entity_id"],
                "brand_name": "理想汽车",
                "official_website": "https://li.auto",
                "orchestrator_history": [{"role": "user", "content": question}],
                "ontology_world": world,
                "ontology_action_plan": {
                    "entity_id": world["entity_id"],
                    "world_phase": "operating_world",
                    "governance_status": "healthy",
                    "gaps": [
                        {
                            "key": "official_website_not_cited",
                            "severity": "warning",
                            "object_type": "official_website_asset",
                            "message": "智能回答引用了外部来源，但没有引用官网。",
                        }
                    ],
                    "recommended_actions": [
                        {
                            "action_key": "generate_official_website_evidence_plan",
                            "display_name": "生成官网证据页优化建议",
                            "readiness": "needs_confirmation",
                            "permission_scope": "entity_execute",
                            "requires_confirmation": True,
                            "missing_inputs": [],
                            "defaulted_inputs": [],
                            "missing_objects": [],
                            "reason": "需要人确认官网优化操作。",
                        }
                    ],
                    "needs_human_confirmation": [],
                    "guardrails": [
                        "requires_confirmation_must_ask_human_first",
                    ],
                },
            }
        )
        ontology_section = next(
            section
            for section in assembly.runtime_context_sections
            if section.key == "ontology_world"
        )
        action_section = next(
            section
            for section in assembly.runtime_context_sections
            if section.key == "ontology_action_plan"
        )

        assert "核心情报判断" in ontology_section.body
        assert "证据关系" in ontology_section.body
        assert "证据缺口" in ontology_section.body
        assert "需确认" in action_section.body
        assert "需确认事项必须先让人确认" in action_section.body


def test_dashboard_context_uses_answer_source_label():
    rendered = render_dashboard_context_packet(
        build_dashboard_context_packet(
            {
                "dashboard_context": {
                    "brand": "理想汽车",
                    "entry_source": "dashboard_command_bar",
                    "ai_sources": ["kimi", "deepseek"],
                }
            }
        )
    )

    assert "回答来源：kimi、deepseek" in rendered
    assert "AI 来源" not in rendered


def test_ontology_intelligence_question_can_be_answered_without_tool_loop():
    world = _intelligence_world()
    state = {
        "latest_user_input": "为什么官网引用转化率为 0？这个结论由哪些对象支撑？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "结论：理想汽车的官网引用转化率为 0" in reply
    assert "官网：li.auto" in reply
    assert "状态是未被引用" in reply
    assert "平台回答：38 条" in reply
    assert "引用来源：1050 个" in reply
    assert "回答引用来源：1050" in reply
    assert "autohome.com.cn" in reply
    assert "不应该自动改官网" in reply
    assert "not_cited" not in reply
    assert "do-not-render" not in reply


def test_source_substitution_question_names_external_domain_objects():
    world = _intelligence_world()
    state = {
        "latest_user_input": "哪些外部来源正在替代理想汽车官网塑造品牌叙事？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    assert _ontology_intelligence_question_kind(state) == "source_substitution"

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "正在替代 li.auto 承接理想汽车品牌叙事" in reply
    assert "来源域名：2 个" in reply
    assert "引用来源：1050 个" in reply
    assert "平台回答：38 条" in reply
    assert "autohome.com.cn" in reply
    assert "pcauto.com.cn" in reply
    assert "品牌声量的证据入口被外部来源掌握" in reply
    assert "do-not-render" not in reply


def test_evidence_cluster_question_explains_denoising_value():
    world = _intelligence_world()
    state = {
        "latest_user_input": "哪个证据簇最重要？为什么它对判断官网价值有帮助？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    assert _ontology_intelligence_question_kind(state) == "evidence_cluster_value"

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "把理想汽车的大量引用降噪成少量可判断主题" in reply
    assert "家庭购车 · 行业垂直站：522 个引用" in reply
    assert "官网引用为 0" in reply
    assert "代表域名是autohome.com.cn、pcauto.com.cn" in reply
    assert "抽少量样本做深读" in reply
    assert "do-not-render" not in reply


def test_relationship_risk_question_explains_object_chain():
    world = _intelligence_world()
    state = {
        "latest_user_input": "这些对象关系说明了什么风险？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    assert _ontology_intelligence_question_kind(state) == "relationship_risk"

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "证据关系暴露的核心风险" in reply
    assert "绕过了官网 li.auto" in reply
    assert "品牌形成情报判断：1" in reply
    assert "回答引用来源：1050" in reply
    assert "官方叙事就很难成为智能回答的默认证据" in reply
    assert "do-not-render" not in reply


def test_supporting_relationship_question_lists_hidden_context_on_demand():
    world = _intelligence_world()
    state = {
        "latest_user_input": "还有哪些其他辅助关联或弱关系？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    assert _ontology_intelligence_question_kind(state) == "supporting_relationships"

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "辅助关联不适合默认放在看板主视图里" in reply
    assert "品牌拥有竞品：22" in reply
    assert "品牌形成情报判断：1" in reply
    assert "回答引用来源：1050" in reply
    assert "do-not-render" not in reply


def test_action_boundary_question_blocks_skipping_confirmation():
    world = _intelligence_world()
    state = {
        "latest_user_input": "下一步能不能直接帮我创建监测计划并跳过确认？",
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
        "ontology_action_plan": {
            "recommended_actions": [
                {
                    "action_key": "generate_official_website_evidence_plan",
                    "display_name": "生成官网证据页优化建议",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "reason": "需要人确认官网优化操作。",
                }
            ]
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    assert _ontology_intelligence_question_kind(state) == "action_boundary"

    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "不能直接跳过确认" in reply
    assert "生成官网证据页优化建议：需要人确认" in reply
    assert "系统只能发起待确认请求" in reply
    assert "创建成功" not in reply
    assert "do-not-render" not in reply


@pytest.mark.parametrize("question", HUMAN_INTELLIGENCE_QUESTIONS)
def test_human_intelligence_questions_keep_business_reply_contract(question):
    world = _intelligence_world()
    state = {
        "latest_user_input": question,
        "brand_name": "理想汽车",
        "dashboard_context": {
            "entity_id": world["entity_id"],
            "brand": "理想汽车",
        },
        "ontology_action_plan": {
            "recommended_actions": [
                {
                    "action_key": "generate_official_website_evidence_plan",
                    "display_name": "生成官网证据页优化建议",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "reason": "需要人确认官网优化操作。",
                }
            ]
        },
    }

    assert _is_ontology_intelligence_explanation_request(state)
    reply = _build_ontology_intelligence_explanation_reply(state, world)

    assert "结论" in reply
    assert "证据" in reply
    assert "影响" in reply
    assert "需要确认" in reply
    assert "下一步建议" in reply
    assert "Ontology" not in reply
    assert "ActionRecord" not in reply
    assert "Orchestrator" not in reply
    assert "do-not-render" not in reply
