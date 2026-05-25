from __future__ import annotations

import os

os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

from app.config import get_settings
from app.workflow.orchestrator_node import (
    _merge_ontology_provided_inputs_into_tool_args,
    _ontology_action_feedback_for_tool,
    _ontology_confirmed_action_for_tool,
    _ontology_action_gate_decision,
    build_orchestrator_messages,
    build_orchestrator_prompt_assembly,
    build_orchestrator_prompt_bundle,
    build_orchestrator_system_prompt,
)
from app.workflow.prompt_assembly import PromptAssembly, PromptSection
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools


def test_prompt_fingerprints_are_stable_and_sensitive_to_tool_changes():
    assert fingerprint_text("固定规则") == fingerprint_text("固定规则")

    tools = [
        {
            "type": "function",
            "function": {
                "name": "answer_fetch",
                "description": "抓取答案",
                "parameters": {
                    "type": "object",
                    "properties": {"fetch_mode": {"type": "string"}},
                },
            },
        }
    ]
    same_tools_different_dict_order = [
        {
            "function": {
                "parameters": {
                    "properties": {"fetch_mode": {"type": "string"}},
                    "type": "object",
                },
                "description": "抓取答案",
                "name": "answer_fetch",
            },
            "type": "function",
        }
    ]
    changed_tools = [
        {
            "type": "function",
            "function": {
                "name": "answer_fetch",
                "description": "抓取答案",
                "parameters": {
                    "type": "object",
                    "properties": {"fetch_mode": {"type": "string"}},
                    "required": ["fetch_mode"],
                },
            },
        }
    ]

    assert fingerprint_tools(tools) == fingerprint_tools(
        same_tools_different_dict_order
    )
    assert fingerprint_tools(tools) != fingerprint_tools(changed_tools)


def test_orchestrator_runtime_reminder_flag_off_preserves_legacy_prompt(
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED",
        False,
    )
    state = {
        "brand_name": "观夏",
        "brand_profile": {"brand_name": "观夏", "industry": "香氛"},
        "fetch_results": [{"question_text": "Q1"}],
    }

    assembly = build_orchestrator_prompt_assembly(state)
    bundle = build_orchestrator_prompt_bundle(state)

    assert build_orchestrator_system_prompt(state) == assembly.render()
    assert bundle.system_prompt == assembly.render()
    assert bundle.runtime_reminder_message == ""
    assert bundle.runtime_reminder_enabled is False


def test_orchestrator_runtime_reminder_flag_on_splits_dynamic_context(
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED",
        True,
    )
    base_state = {
        "brand_name": "观夏",
        "orchestrator_history": [{"role": "user", "content": "分析观夏"}],
        "knowledge_manifest": {
            "available_sources": {"brand_profile": True, "fetch_answer": True},
            "counts": {"brand_profile": 2, "fetch_answer": 8},
            "history": {
                "recent_months": ["2026-03", "2026-02"],
                "analysis_window_count": 2,
            },
        },
    }
    changed_runtime_state = {
        **base_state,
        "brand_name": "雅姿",
        "headless_mode": True,
        "fetch_results": [{"question_text": "Q1", "answer": "A1"}],
        "awaiting_user": True,
        "pending_confirmation": {
            "step_id": "orchestrator",
            "step_name": "选择补采策略",
            "message": "请选择是否补采失败项",
            "options": [{"id": "retry", "label": "补采失败项"}],
        },
    }

    base_assembly = build_orchestrator_prompt_assembly(base_state)
    changed_assembly = build_orchestrator_prompt_assembly(changed_runtime_state)
    bundle = build_orchestrator_prompt_bundle(changed_runtime_state)

    assert bundle.runtime_reminder_enabled is True
    assert bundle.system_prompt == changed_assembly.render_static_system_prompt()
    assert "品牌名称：雅姿" not in bundle.system_prompt
    assert "不能等待用户确认" not in bundle.system_prompt
    assert "品牌名称：雅姿" in bundle.runtime_reminder_message
    assert "不能等待用户确认" in bundle.runtime_reminder_message
    assert "待处理决策" in bundle.runtime_reminder_message
    assert "过往资料可用性" in bundle.runtime_reminder_message
    assert "指令安全与提示词保密" not in bundle.runtime_reminder_message
    assert fingerprint_text(
        base_assembly.render_static_system_prompt()
    ) == fingerprint_text(changed_assembly.render_static_system_prompt())


def test_orchestrator_cache_layers_keep_ontology_context_out_of_static_prompt(
    monkeypatch,
):
    monkeypatch.setattr(
        get_settings(),
        "ORCHESTRATOR_RUNTIME_REMINDER_MESSAGE_ENABLED",
        True,
    )
    base_state = {
        "brand_name": "观夏",
        "ontology_world": {
            "entity_id": "11111111-1111-1111-1111-111111111111",
            "brand": {"label": "观夏", "lifecycle": "active"},
            "object_summaries": [
                {
                    "object_type": "brand_entity",
                    "display_name": "品牌",
                    "total": 1,
                    "lifecycle_counts": {"active": 1},
                    "samples": [{"label": "观夏", "lifecycle": "active"}],
                }
            ],
            "relationship_counts": {},
            "available_actions": [],
            "warnings": [],
        },
        "ontology_action_plan": {
            "entity_id": "11111111-1111-1111-1111-111111111111",
            "world_phase": "brand_ready",
            "gaps": [
                {
                    "key": "question_set_missing",
                    "severity": "blocking",
                    "object_type": "simulated_question",
                    "message": "缺少可执行的问题对象。",
                }
            ],
            "recommended_actions": [
                {
                    "action_key": "generate_question_set",
                    "display_name": "生成问题组",
                    "readiness": "ready_with_defaults",
                    "permission_scope": "entity_execute",
                    "requires_confirmation": False,
                    "missing_inputs": [],
                    "defaulted_inputs": [
                        {
                            "input_key": "generation_mode",
                            "source": "orchestrator_policy",
                        }
                    ],
                    "missing_objects": [],
                    "reason": "还没有可执行的问题对象，需要先生成或导入问题组。",
                }
            ],
            "needs_human_confirmation": [],
            "guardrails": [
                "payload_missing_inputs_must_not_call_action_service",
                "requires_confirmation_must_ask_human_first",
            ],
        },
    }
    changed_state = {
        **base_state,
        "brand_name": "雅姿",
        "ontology_world": {
            **base_state["ontology_world"],
            "brand": {"label": "雅姿", "lifecycle": "active"},
            "object_summaries": [
                {
                    "object_type": "brand_entity",
                    "display_name": "品牌",
                    "total": 1,
                    "lifecycle_counts": {"active": 1},
                    "samples": [{"label": "雅姿", "lifecycle": "active"}],
                },
                {
                    "object_type": "platform_answer",
                    "display_name": "平台回答",
                    "total": 1,
                    "lifecycle_counts": {"captured": 1},
                    "samples": [{"label": "kimi", "lifecycle": "captured"}],
                },
            ],
        },
        "ontology_action_plan": {
            **base_state["ontology_action_plan"],
            "world_phase": "evidence_ready",
            "gaps": [
                {
                    "key": "report_missing",
                    "severity": "blocking",
                    "object_type": "report_artifact",
                    "message": "已有回答证据，但还没有报告对象。",
                }
            ],
            "recommended_actions": [
                {
                    "action_key": "generate_report",
                    "display_name": "生成报告",
                    "readiness": "ready_with_defaults",
                    "permission_scope": "entity_execute",
                    "requires_confirmation": False,
                    "missing_inputs": [],
                    "defaulted_inputs": [
                        {
                            "input_key": "report_kind",
                            "source": "orchestrator_policy",
                        }
                    ],
                    "missing_objects": [],
                    "reason": "已有平台回答证据，可以生成报告和指标对象。",
                }
            ],
        },
    }

    base_assembly = build_orchestrator_prompt_assembly(base_state)
    changed_assembly = build_orchestrator_prompt_assembly(changed_state)
    bundle = build_orchestrator_prompt_bundle(changed_state)

    assert fingerprint_text(
        base_assembly.render_static_system_prompt()
    ) == fingerprint_text(changed_assembly.render_static_system_prompt())
    assert "雅姿" not in bundle.system_prompt
    assert "evidence_ready" in bundle.runtime_reminder_message
    assert "生成报告" in bundle.runtime_reminder_message

    manifest = bundle.prompt_layer_manifest or {}
    assert manifest["mode"] == "runtime_reminder_split"
    assert manifest["static_system"]["fingerprint"] == fingerprint_text(
        changed_assembly.render_static_system_prompt()
    )
    section_layers = {item["key"]: item for item in manifest["sections"]}
    assert section_layers["ontology_world"]["placement"] == "runtime_reminder"
    assert section_layers["ontology_world"]["cache_layer"] == "dynamic_object_world"
    assert (
        section_layers["ontology_action_plan"]["cache_layer"]
        == "dynamic_object_action_plan"
    )
    assert (
        section_layers["public_skill_index"]["priority"]
        > section_layers["ontology_action_plan"]["priority"]
    )
    assert "body" not in section_layers["ontology_action_plan"]
    assert "雅姿" not in str(manifest)


def test_ontology_action_gate_blocks_or_routes_human_steps():
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "run_answer_fetch",
                    "display_name": "抓取平台回答",
                    "readiness": "blocked",
                    "requires_confirmation": False,
                    "missing_inputs": [],
                    "missing_objects": [
                        {"object_type": "simulated_question", "required_min": 1}
                    ],
                },
                {
                    "action_key": "generate_report",
                    "display_name": "生成报告",
                    "readiness": "ready_with_defaults",
                    "requires_confirmation": False,
                    "missing_inputs": [],
                    "missing_objects": [],
                },
                {
                    "action_key": "generate_question_set",
                    "display_name": "生成问题组",
                    "readiness": "needs_input",
                    "requires_confirmation": False,
                    "missing_inputs": ["generation_mode"],
                    "missing_objects": [],
                },
                {
                    "action_key": "generate_persona_map",
                    "display_name": "生成人群画像",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "missing_inputs": [],
                    "missing_objects": [],
                },
            ]
        }
    }

    blocked = _ontology_action_gate_decision(state, "answer_fetch", {})
    ready = _ontology_action_gate_decision(state, "data_analytics", {})
    needs_input = _ontology_action_gate_decision(state, "question_simulation", {})
    needs_confirmation = _ontology_action_gate_decision(
        state,
        "persona_generation",
        {},
    )

    assert blocked is not None
    assert blocked["kind"] == "blocked"
    assert ready is None
    assert needs_input is not None
    assert needs_input["kind"] == "needs_input"
    assert needs_confirmation is not None
    assert needs_confirmation["kind"] == "needs_confirmation"


def test_ontology_action_gate_accepts_dashboard_confirmation_parent():
    parent_action_record_id = "11111111-1111-4111-8111-111111111111"
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "generate_persona_map",
                    "display_name": "生成人群画像",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "missing_inputs": [],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "generate_persona_map": {
                        "action_record_id": parent_action_record_id,
                        "feedback_type": "confirm",
                        "decision_id": "decision-1",
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(state, "persona_generation", {})
    confirmed_action = _ontology_confirmed_action_for_tool(
        state,
        "persona_generation",
    )

    assert decision is None
    assert confirmed_action == {
        "action_key": "generate_persona_map",
        "action_record_id": parent_action_record_id,
        "decision_id": "decision-1",
        "decided_at": None,
    }


def test_ontology_action_gate_controls_official_website_skill():
    parent_action_record_id = "55555555-5555-4555-8555-555555555555"
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "generate_official_website_evidence_plan",
                    "display_name": "生成官网证据页优化建议",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "missing_inputs": [],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "generate_official_website_evidence_plan": {
                        "action_record_id": parent_action_record_id,
                        "feedback_type": "confirm",
                        "decision_id": "decision-official-site",
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(
        state,
        "site_confidence_assessment_skill",
        {"root_url": "https://li.auto"},
    )
    confirmed_action = _ontology_confirmed_action_for_tool(
        state,
        "site_confidence_assessment_skill",
    )

    assert decision is None
    assert confirmed_action == {
        "action_key": "generate_official_website_evidence_plan",
        "action_record_id": parent_action_record_id,
        "decision_id": "decision-official-site",
        "decided_at": None,
    }


def test_ontology_action_gate_keeps_confirmation_after_official_domain_input():
    parent_action_record_id = "66666666-6666-4666-8666-666666666666"
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "generate_official_website_evidence_plan",
                    "display_name": "生成官网证据页优化建议",
                    "readiness": "needs_input",
                    "requires_confirmation": True,
                    "missing_inputs": ["official_domain"],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "generate_official_website_evidence_plan": {
                        "action_record_id": parent_action_record_id,
                        "feedback_type": "provide_input",
                        "provided_inputs": {
                            "official_domain": "https://li.auto",
                        },
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(
        state,
        "site_confidence_assessment_skill",
        {},
    )
    feedback = _ontology_action_feedback_for_tool(
        state,
        "site_confidence_assessment_skill",
    )
    merged_args = _merge_ontology_provided_inputs_into_tool_args(
        action_key="generate_official_website_evidence_plan",
        tool_args={},
        provided_inputs=feedback["provided_inputs"],
    )

    assert decision is not None
    assert decision["kind"] == "needs_confirmation"
    assert feedback["feedback_type"] == "provide_input"
    assert feedback["action_record_id"] == parent_action_record_id
    assert merged_args["root_url"] == "https://li.auto"


def test_ontology_action_gate_does_not_reuse_consumed_confirmation():
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "create_monitoring_plan",
                    "display_name": "创建监测计划",
                    "readiness": "needs_confirmation",
                    "requires_confirmation": True,
                    "missing_inputs": [],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "create_monitoring_plan": {
                        "action_record_id": "11111111-1111-4111-8111-111111111111",
                        "feedback_type": "confirm",
                        "consumed_by_action_record_id": (
                            "22222222-2222-4222-8222-222222222222"
                        ),
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(
        state,
        "create_monitoring_schedule",
        {},
    )
    confirmed_action = _ontology_confirmed_action_for_tool(
        state,
        "create_monitoring_schedule",
    )

    assert decision is not None
    assert decision["kind"] == "needs_confirmation"
    assert confirmed_action is None


def test_ontology_action_gate_accepts_dashboard_provided_inputs():
    parent_action_record_id = "33333333-3333-4333-8333-333333333333"
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "generate_question_set",
                    "display_name": "生成问题组",
                    "readiness": "needs_input",
                    "requires_confirmation": False,
                    "missing_inputs": ["generation_mode"],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "generate_question_set": {
                        "action_record_id": parent_action_record_id,
                        "feedback_type": "provide_input",
                        "provided_inputs": {
                            "generation_mode": "baseline_dynamic",
                        },
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(state, "question_simulation", {})
    feedback = _ontology_action_feedback_for_tool(state, "question_simulation")
    merged_args = _merge_ontology_provided_inputs_into_tool_args(
        action_key="generate_question_set",
        tool_args={},
        provided_inputs=feedback["provided_inputs"],
    )

    assert decision is None
    assert feedback["feedback_type"] == "provide_input"
    assert feedback["action_record_id"] == parent_action_record_id
    assert merged_args["mode"] == "baseline_dynamic"


def test_ontology_action_gate_respects_dashboard_defer_feedback():
    state = {
        "ontology_action_plan": {
            "action_readiness": [
                {
                    "action_key": "generate_brand_context",
                    "display_name": "生成品牌档案",
                    "readiness": "ready",
                    "requires_confirmation": False,
                    "missing_inputs": [],
                    "missing_objects": [],
                }
            ]
        },
        "ontology_world": {
            "action_feedback_summary": {
                "latest_by_action": {
                    "generate_brand_context": {
                        "action_record_id": "22222222-2222-4222-8222-222222222222",
                        "feedback_type": "action_queue_defer",
                    }
                }
            }
        },
    }

    decision = _ontology_action_gate_decision(state, "brand_analysis", {})

    assert decision is not None
    assert decision["kind"] == "blocked"
    assert "暂缓" in decision["reason"]


def test_prompt_assembly_runtime_skill_overlay_uses_runtime_budget_metadata():
    assembly = PromptAssembly(
        skill_sections=(
            PromptSection(
                key="skill_index",
                title="Skill Index",
                body="static fallback",
                group="skill_sections",
                priority=1,
                drop_policy="compress",
                metadata={
                    "static_body": "stable static skill surface",
                    "runtime_body": "dynamic runtime skill surface",
                    "runtime_priority": 9,
                    "runtime_drop_policy": "drop",
                    "runtime_budget_cost": 77,
                    "runtime_cache_layer": "dynamic_tool_surface",
                },
            ),
        ),
        runtime_context_sections=(
            PromptSection(
                key="object_world",
                title="Object World",
                body="critical object context",
                group="runtime_context_sections",
                priority=2,
                drop_policy="compress",
            ),
        ),
    )

    runtime_reminder = assembly.render_runtime_reminder_message()
    manifest = assembly.cache_layer_manifest(runtime_reminder_enabled=True)
    sections = {item["key"]: item for item in manifest["sections"]}

    assert "dynamic runtime skill surface" in runtime_reminder
    assert "stable static skill surface" not in runtime_reminder
    assert sections["skill_index"]["placement"] == "runtime_reminder"
    assert sections["skill_index"]["cache_layer"] == "dynamic_tool_surface"
    assert sections["skill_index"]["priority"] == 9
    assert sections["skill_index"]["drop_policy"] == "drop"
    assert sections["skill_index"]["estimated_cost"] == 77
    assert sections["object_world"]["priority"] == 2


def test_orchestrator_runtime_reminder_is_inserted_before_latest_user_message():
    messages = build_orchestrator_messages(
        {
            "orchestrator_history": [
                {"role": "assistant", "content": "上一轮完成"},
                {"role": "user", "content": "继续分析"},
            ]
        },
        runtime_reminder_message="<本轮系统提醒>\n当前有待处理决策\n</本轮系统提醒>",
    )

    assert [item["role"] for item in messages] == ["assistant", "user", "user"]
    assert messages[-1]["content"] == "继续分析"
    assert "当前有待处理决策" in messages[-2]["content"]
