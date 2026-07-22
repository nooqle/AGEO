"""LLM-driven orchestrator node for Specta AI workflow.

This module implements the core orchestrator that uses LLM Function Calling
to dynamically decide which Agent to invoke, replacing the hardcoded pipeline.
"""

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from textwrap import dedent
from time import perf_counter
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from langgraph.graph import END
from langgraph.types import Command

from app.config import get_settings
from app.core.database import AsyncSessionLocal
from app.core.llm.task_routing import get_orchestrator_llm_model
from app.services.brand_ontology_action_planner_service import (
    BrandOntologyActionPlannerService,
)
from app.services.brand_ontology_world_service import BrandOntologyWorldService
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.services.session_event_publisher import session_event_publisher
from app.services.skill_invocation_service import (
    SkillInvocationPlan,
    SkillInvocationService,
)
from app.services.skill_registry_service import (
    SkillRegistryService,
    SkillScopeContext,
    build_builtin_skill_tool_definitions,
)
from app.services.tool_capability_matrix import (
    ToolAvailabilityConstraint,
    get_tool_capability,
    validate_tool_capability_access,
)
from app.workflow.confirmation import build_table_import_confirmation_payload
from app.workflow.events import (
    send_action_log_event,
    send_confirmation_request,
    send_plan_event,
    send_reply_event,
    send_thought_event,
)
from app.workflow.fetch_recovery import (
    extract_base_fetch_results_from_state,
    extract_latest_fetch_recovery_plan_from_state,
    is_supplemental_fetch_request,
    normalize_question_targets,
    prefers_browser_fetch_mode,
    resolve_supplemental_fetch_mode,
)
from app.workflow.nodes_streaming import async_wrap_sync_gen
from app.workflow.orchestrator_context_packets import (
    RecentEvidencePacket,
    build_entity_context_packet,
    build_orchestrator_context_packets,
    build_session_status_packet,
    render_active_skill_packet,
    render_dashboard_context_packet,
    render_entity_context_packet,
    render_history_availability_packet,
    render_ontology_action_plan_packet,
    render_ontology_world_packet,
    render_pending_decision_packet,
    render_recent_evidence_packet,
    render_session_status_packet,
)
from app.workflow.orchestrator_instruction_defense import (
    INSTRUCTION_SECURITY_POLICY,
    build_instruction_defense_context,
    detect_instruction_injection,
    render_instruction_defense_reminder,
)
from app.workflow.prompt_assembly import PromptAssembly, PromptSection
from app.workflow.prompt_fingerprint import fingerprint_text, fingerprint_tools
from app.workflow.runtime_policy_executor import (
    build_alternative_action_catalog,
    build_next_required_action,
    clear_runtime_policy_fields,
    get_user_visible_runtime_label,
    parse_next_required_action,
    resolve_answer_fetch_mode_policy,
    summarize_alternative_actions,
)
from app.workflow.state import AgentState
from app.workflow.orchestrator.message_builders import (
    _build_orchestrator_assistant_message,
    _inject_runtime_reminder_message,
)
from app.workflow.orchestrator.report_state import _is_completed_analysis_report_state
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _contains_non_negated_keyword,
    _extract_exact_datetime_scope_text,
    _is_english_dominant_text,
    _normalize_internal_analysis_mode,
    _normalize_public_knowledge_text,
    _normalize_public_report_kind,
)
from app.workflow.orchestrator.ontology_format import (
    ONTOLOGY_ACTION_INPUT_TOOL_ARG_ALIASES,
    _action_readiness_label,
    _normalize_ontology_action_feedback_type,
    _ontology_brand_label,
    _ontology_float,
    _ontology_int,
    _ontology_object_summaries,
    _ontology_payload_has_value,
    _ontology_status_label,
    _ontology_tool_arg_key_for_input,
    _relationship_is_core,
    _source_domain_sort_key,
)
from app.workflow.orchestrator.thought_stream import (
    _localize_visible_terms,
    _normalize_thought_text_for_stream,
)
from app.workflow.orchestrator.history_query import (
    _build_history_answer_export_query,
    _contains_positive_continuation_marker,
    _get_recent_history_answer_basis_query,
    _get_recent_history_answer_result_query,
    _has_authoritative_history_refresh_result,
    _has_recent_history_answer_followup_invite,
    _has_terminal_knowledge_result,
    _is_bounded_history_answer_query_state,
    _is_current_report_follow_up,
    _is_explicit_question_generation_only_request,
    _is_history_answer_content_query,
    _is_history_answer_continuation_query,
    _is_latest_run_history_stats_query,
    _is_precise_history_query,
    _is_question_generation_only_state,
    _iter_recent_history_messages,
    _resolve_bounded_history_answer_query,
    _session_was_recalled,
)
from app.workflow.orchestrator.knowledge_format import (
    _format_knowledge_comparison,
    _format_knowledge_group,
    _format_knowledge_lookup_match,
)
from app.workflow.orchestrator.workflow_progress import (
    WORKFLOW_STEPS,
    _build_workflow_steps,
    _get_tool_name_from_node,
    _is_completed_question_generation_only_state,
    _is_step_skipped,
    _matches_failed_step,
)
from app.workflow.orchestrator.ontology_intelligence import (
    CORE_RELATIONSHIP_TYPES,
    _action_reply_line,
    _available_action_items,
    _build_action_boundary_reply,
    _build_evidence_cluster_value_reply,
    _build_official_website_gap_reply,
    _build_ontology_intelligence_explanation_reply,
    _build_relationship_risk_reply,
    _build_source_substitution_reply,
    _build_supporting_relationships_reply,
    _evidence_cluster_reply_line,
    _evidence_cluster_sort_key,
    _format_relationships_for_reply,
    _format_source_domains_for_reply,
    _is_ontology_intelligence_explanation_request,
    _ontology_intelligence_question_kind,
    _ontology_object_total,
    _sorted_evidence_clusters,
    _sorted_source_domains,
    _source_domain_reply_line,
    _with_intelligence_reply_closure,
)
from app.workflow.orchestrator.seed_surface import (
    _build_panorama_step_intro,
    _extract_site_confidence_root_url,
    _has_persona_prerequisites,
    _infer_brand_seed_candidate,
    _is_site_confidence_request,
    _looks_like_keyword_list,
    _normalize_tool_topic_keywords,
    _resolve_brand_name_for_dependency_rebuild,
)
from app.workflow.orchestrator.prompt_bundle import (
    OrchestratorPromptBundle,
    _build_orchestrator_prompt_bundle_from_assembly,
    _runtime_reminder_message_enabled,
    _wrap_runtime_reminder_message,
)
from app.workflow.orchestrator.ontology_action_feedback import (
    ONTOLOGY_TOOL_ACTION_MAP,
    _find_ontology_action_plan_item,
    _merge_ontology_provided_inputs_into_tool_args,
    _ontology_action_feedback_for_key,
    _ontology_action_feedback_for_tool,
    _ontology_action_gate_message,
    _ontology_action_gate_options,
    _ontology_confirmed_action_for_tool,
    _ontology_feedback_covers_missing_inputs,
    _ontology_feedback_provided_inputs,
)
from app.workflow.orchestrator.misc_pure import (
    _build_static_public_skill_index,
    _format_tool_args_for_suggestion,
    _infer_current_import_query,
    _normalize_sentiment_followup_value,
)
from app.workflow.orchestrator.session_tool_surface import (
    _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES,
    _KNOWLEDGE_TOOL_NAMES,
    _SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES,
    _get_contextual_hidden_tool_names,
    _infer_authoritative_history_refresh_tool,
    _infer_current_session_followup_tool,
    _should_force_fetch_recovery_confirmation,
    _stable_tool_surface_enabled,
)
from app.workflow.orchestrator.reply_text import (
    _build_ask_user_fallback_reply,
    _build_knowledge_export_completion_reply,
)
from app.workflow.orchestrator.prompt_evidence import (
    _RECENT_EVIDENCE_PROMPT_PRIORITY,
    _render_recent_evidence_for_prompt,
    _should_render_history_availability,
    _should_render_instruction_defense,
)
from app.workflow.orchestrator.tool_gate import (
    validate_tool_available_in_current_state,
)
from app.workflow.orchestrator.prompt_context import (
    _build_context_summary,
    _build_contextual_tool_surface_note,
    _build_orchestrator_data_status,
    _build_orchestrator_entity_context,
    _build_public_skill_index,
)
from app.workflow.orchestrator.knowledge_fallback import (
    _build_knowledge_planning_hint,
    _build_recent_knowledge_context,
    _infer_knowledge_fallback_tool,
    _should_stream_thoughts,
)
from app.workflow.orchestrator.command_helpers import (
    _build_error_recovery_message,
    _merge_command_update,
    _sanitize_runtime_policy_state,
)
from app.workflow.orchestrator.agent_result_summary import (
    DIRECTIVE_A1_HAS_BASELINE,
    DIRECTIVE_A1_NO_BASELINE,
    DIRECTIVE_A2_ASK_PATH,
    DIRECTIVE_A3_NEXT_FETCH,
    DIRECTIVE_A5_BASELINE_NEXT,
    DIRECTIVE_A5_PERSONA_NEXT,
    _build_agent_result_summary,
)
from app.workflow.orchestrator.ontology_action_gate import (
    _ontology_action_gate_decision,
)
from app.workflow.orchestrator.orchestrator_messages import (
    build_orchestrator_messages,
)
from app.workflow.orchestrator.prompt_assembly_builder import (
    build_orchestrator_prompt_assembly,
    build_orchestrator_prompt_bundle,
    build_orchestrator_system_prompt,
)
from app.workflow.orchestrator.tool_gate_command import (
    _build_tool_gate_block_command,
)
from app.workflow.orchestrator.ontology_action_plan import (
    _build_ontology_action_plan,
)

logger = logging.getLogger(__name__)


SKILLIZED_TOOL_NAMES = {
    "data_analytics",
    "drill_down_analysis",
    "compare_snapshots",
}

_VISIBLE_TOOL_NAME_LABELS: dict[str, str] = {
    "brand_analysis": "品牌分析",
    "persona_generation": "画像生成",
    "question_simulation": "问题模拟",
    "answer_fetch": "答案抓取",
    "amway_entity_extract": "实体抽取",
    "amway_circle_projection": "图谱构建",
    "amway_secondary_analysis": "数据分析",
    "amway_content_draft": "内容创作",
    "analysis_report_skill": "分析报告",
    "data_analytics": "分析报告",
    "confidence_analysis_skill": "引用置信度评估",
    "confidence_signal_skill": "引用置信度评估",
    "citation_confidence_analysis": "引用置信度评估",
    "site_confidence_assessment_skill": "官网 AI 友好度",
    "post_analysis_skill": "后续分析",
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    "knowledge_lookup": "过往资料检索",
    "knowledge_aggregate": "过往资料整理",
    "knowledge_compare": "过往资料对比",
    "knowledge_export": "过往资料表",
    "ask_user": "用户确认",
    "fast": "快速采集",
    "full": "完整采集",
}


# =============================================================================
# Agent Tool Registry
# =============================================================================

AGENT_REGISTRY: list[dict[str, Any]] = [
    {
        "name": "brand_analysis",
        "description": (
            "分析品牌基本信息、竞品格局。需要品牌名称作为输入。"
            "输出品牌画像和竞品列表。这是分析流程的第一步。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "brand_name": {
                    "type": "string",
                    "description": "要分析的品牌名称",
                },
                "focus_areas": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "重点分析方向（可选）",
                },
            },
            "required": ["brand_name"],
        },
    },
    {
        "name": "persona_generation",
        "description": (
            "基于品牌信息生成营销用户画像。需要先完成品牌分析。"
            "输出6-8个差异化的用户画像。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "persona_count": {
                    "type": "integer",
                    "description": "生成画像数量（默认6-8个）",
                },
            },
        },
    },
    {
        "name": "question_simulation",
        "description": (
            "模拟用户可能向 AI 平台提出的问题。"
            "默认按消费者视角生成；当用户明确要求某个身份/角色时，可通过 identity 传入显式视角覆盖。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": [
                        "brand_panorama",
                        "persona_focused",
                        "baseline_dynamic",
                        "uploaded_list",
                    ],
                    "description": "生成模式：brand_panorama=品牌全景, persona_focused=画像聚焦, baseline_dynamic=品牌全景问题, uploaded_list=导入用户上传的问题列表",
                },
                "persona_id": {
                    "type": "string",
                    "description": "聚焦的画像ID（persona_focused模式时需要）",
                },
                "identity": {
                    "type": "string",
                    "description": "可选身份视角覆盖。仅当用户明确要求“以某个身份/视角生成问题”时传入，例如“采购经理”“品牌经理”。未明确要求时不要传。",
                },
                "topic_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户明确给出的主题/关键词，用于生成新的全景问题，例如“细胞”“抗衰”。仅当用户要求围绕关键词/主题生成问题时传入。",
                },
                "topic_description": {
                    "type": "string",
                    "description": "用户对主题全景问题的原始需求或补充说明。与 topic_keywords 一起使用，帮助 A3 生成更贴合的提示词。",
                },
                "question_only": {
                    "type": "boolean",
                    "description": "仅生成/更新问题集，不自动进入答案抓取或报告分析。用户明确说生成问题、重新生成问题、模拟问题集时应为 true。",
                },
            },
        },
    },
    {
        "name": "answer_fetch",
        "description": (
            "从多个AI平台（豆包、元宝、Kimi、DeepSeek）抓取对模拟问题的回答。"
            "前置条件：1) 问题模拟已完成（或提供了 custom_questions）。"
            "如果用户明确指定快速/完整/浏览器模式，请显式传入 fetch_mode。"
            "若用户没有明确指定，runtime 会优先复用已有模式，或默认按 fast 继续。"
            "如果用户要求只重跑部分平台、全量重跑、或从 API 改为浏览器模式，也统一使用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fetch_mode": {
                    "type": "string",
                    "enum": ["fast", "full"],
                    "description": (
                        "采集模式（必须由用户选择）：\n"
                        "fast=通过API调用豆包、元宝和Kimi，并通过浏览器采集DeepSeek，约3-5分钟，快速建立品牌AI表现的初步观感，但API返回内容与真实用户网页端体验可能存在差异；\n"
                        "full=4平台全部通过浏览器模拟真实用户访问，约10-20分钟，完全还原用户真实体验，数据最准确，是深度AEO分析的最佳选择"
                    ),
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要抓取的平台列表（可选，默认全部）。可用于局部重跑或仅抓取指定平台。",
                },
                "custom_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户自定义问题文本列表（可选）。当用户直接提供问题时使用，将覆盖 A3 生成的问题。",
                },
                "question_targets": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "question_id": {"type": "string"},
                            "question_text": {"type": "string"},
                            "platforms": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["question_id", "question_text", "platforms"],
                    },
                    "description": "定向补采时使用。每个问题只重跑指定失败平台，并保留已成功结果。",
                },
            },
        },
    },
    {
        "name": "data_analytics",
        "description": (
            "基于抓取结果生成品牌战况报告。"
            "需要先完成答案抓取。这是分析流程的最后一步。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "report_focus": {
                    "type": "string",
                    "description": "报告重点方向（可选）",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["panorama", "scenario"],
                    "description": "报告类型：panorama=品牌全景分析报告, scenario=场景分析报告（默认）",
                },
            },
        },
    },
    {
        "name": "knowledge_lookup",
        "description": (
            "查询同一品牌过往分析中已经沉淀的事实资料。"
            "适用于品牌信息、竞品信息、过往抓取回答、过往引用来源、"
            "以及基于已有材料的问答、分析和导出任务。"
            "这是低成本优先路径：当用户问题明显围绕过往资料展开时，应优先尝试此工具。"
            "如果返回 miss 或证据不足，再考虑 brand_analysis、answer_fetch 或 ask_user。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要查询的过往事实、分析主题或导出主题",
                },
                "source_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "brand_profile",
                            "competitor_profile",
                            "fetch_answer",
                            "fetch_citation",
                        ],
                    },
                    "description": "限制知识来源类型（可选）",
                },
                "platform": {
                    "type": "string",
                    "description": "限制平台（可选）",
                },
                "competitor_name": {
                    "type": "string",
                    "description": "限制竞品名称（可选）",
                },
                "domain": {
                    "type": "string",
                    "description": "限制引用域名（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少条命中（默认 8）",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "knowledge_aggregate",
        "description": (
            "按时间、平台、竞品、问题或域名聚合过往事实资料。"
            "适用于导出、汇总、盘点和基于过往资料的结构化分析。"
            "当用户要求导出某一时间范围内的信息、统计某类资料、或按某个维度做过往汇总时优先使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "聚合主题或筛选提示（可为空）",
                },
                "source_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "brand_profile",
                            "competitor_profile",
                            "fetch_answer",
                            "fetch_citation",
                        ],
                    },
                    "description": "限制知识来源类型（可选）",
                },
                "group_by": {
                    "type": "string",
                    "enum": [
                        "source_type",
                        "platform",
                        "competitor",
                        "domain",
                        "question",
                        "month",
                    ],
                    "description": "聚合维度",
                },
                "platform": {
                    "type": "string",
                    "description": "限制平台（可选）",
                },
                "competitor_name": {
                    "type": "string",
                    "description": "限制竞品名称（可选）",
                },
                "domain": {
                    "type": "string",
                    "description": "限制域名（可选）",
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，支持 YYYY-MM 或 YYYY-MM-DD（可选）",
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，支持 YYYY-MM 或 YYYY-MM-DD（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少个分组（默认 20）",
                },
            },
        },
    },
    {
        "name": "knowledge_compare",
        "description": (
            "对同一品牌最近两次过往资料窗口做对比。"
            "适用于历次分析对比、变化解释、平台差异和对比汇总。"
            "当用户要求比较最近两轮分析、看哪些平台/竞品/域名变化最大时优先使用。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "compare_by": {
                    "type": "string",
                    "enum": [
                        "source_type",
                        "platform",
                        "competitor",
                        "domain",
                        "question",
                    ],
                    "description": "对比维度",
                },
                "source_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "brand_profile",
                            "competitor_profile",
                            "fetch_answer",
                            "fetch_citation",
                        ],
                    },
                    "description": "限制知识来源类型（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少条变化项（默认 12）",
                },
            },
        },
    },
    {
        "name": "knowledge_export",
        "description": (
            "把过往资料整理成可交付的数据表。"
            "适用于用户明确要求导出、下载、生成文件、拉清单或交付过往资料。"
            "执行后会生成一个可在前端继续导出为 md/pdf 的数据表。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "导出主题或筛选提示（可为空）",
                },
                "source_types": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": [
                            "brand_profile",
                            "competitor_profile",
                            "fetch_answer",
                            "fetch_citation",
                        ],
                    },
                    "description": "限制知识来源类型（可选）",
                },
                "platform": {
                    "type": "string",
                    "description": "限制平台（可选）",
                },
                "competitor_name": {
                    "type": "string",
                    "description": "限制竞品名称（可选）",
                },
                "domain": {
                    "type": "string",
                    "description": "限制域名（可选）",
                },
                "start_date": {
                    "type": "string",
                    "description": "开始日期，支持 YYYY-MM 或 YYYY-MM-DD（可选）",
                },
                "end_date": {
                    "type": "string",
                    "description": "结束日期，支持 YYYY-MM 或 YYYY-MM-DD（可选）",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多导出多少条记录（默认 200，最大 500）",
                },
            },
        },
    },
    # --- Monitoring tools (Cycle 4) ---
    {
        "name": "manage_monitoring_schedule",
        "description": (
            "查询、创建、启用、更新、暂停或删除当前品牌的周期监测计划。"
            "例如：'查看当前监测计划'、'每周监控小米'、'调整为每月 11 点'、'暂停周期监测'。"
            "前置条件：当前会话中必须有 entity_id（品牌至少已分析过一次）。"
            "如果没有 entity_id，不要调用此工具，提示用户先运行完整分析。"
            "当用户要求调整已有计划时，必须用 action=update 或 upsert，不能回答'只能创建、无法修改'。"
            "当用户只想查看当前配置时，使用 action=get。"
            "当用户已明确给出频率、时间或告警阈值时，可以直接调用工具更新。"
            "当用户只是泛泛说'开启周期监测'且尚未给出配置时，先用自然语言说明周期监测的含义和可配置参数，再调用 ask_user 让用户确认。"
            "说明内容包括：1) 周期监测会按设定频率自动重新运行品牌分析流程，生成最新报告并与历史数据对比；"
            "2) 可配置参数及默认值——监测频率（每天/每周/双周/每月，推荐每周）、执行时间（默认上午11:00）、"
            "告警阈值（当品牌提及率、官网引用率或高风险场景数量出现明显变化时通知用户，默认 10）；"
            "3) 基于看板上下文中的品牌、问题集、平台来源给出推荐配置。"
            "注意：当前调度字段支持频率和小时，不支持固定'每月第几日'；不要承诺每月 1 日这种后台尚未支持的精确日期。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["get", "upsert", "update", "pause", "resume", "delete"],
                    "description": "要执行的操作。已有计划调整用 update 或 upsert；查看用 get；新建或启用用 upsert。",
                },
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "weekly", "biweekly", "monthly"],
                    "description": "监测频率。用户未指定时不要臆造；新建默认 weekly。",
                },
                "preferred_hour": {
                    "type": "integer",
                    "description": "每天的执行小时（0-23，Asia/Shanghai），用户说上午11点则传 11。",
                },
                "alert_threshold": {
                    "type": "number",
                    "description": "监测变化告警阈值（用于提及率、官网引用率、高风险场景等变化提醒），默认 10.0",
                },
                "monitor_mode": {
                    "type": "string",
                    "enum": [
                        "panorama",
                        "scenario",
                        "panorama_monitoring",
                        "scenario_monitoring",
                    ],
                    "description": "监测视图。Dashboard 上下文已有时优先沿用。",
                },
                "monitoring_plan_id": {
                    "type": "string",
                    "description": "已有新版监测计划 ID。Dashboard 上下文已有时可传入。",
                },
                "schedule_id": {
                    "type": "string",
                    "description": "已有周期任务 ID。只有明确知道时才传。",
                },
                "question_set_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要绑定的问题集 ID。Dashboard 或当前流程已有时可传入。",
                },
                "endpoint_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要绑定的平台来源 ID，例如 doubao_api、yuanbao_api、kimi_api、deepseek_browser。",
                },
            },
        },
    },
    # --- Follow-up tools (Cycle 3, Module 2) ---
    {
        "name": "drill_down_analysis",
        "description": (
            "对当前会话中已有的分析结果进行深入分析。"
            "例如：'详细分析DeepSeek的结果'、'分析产品推荐类问题'、'竞品华为的表现如何'。"
            "前置条件：当前会话中必须已有完整分析结果（fetch_results）。"
            "如果没有分析数据，不要调用此工具，提示用户先运行完整分析。"
            "使用已有的fetch_results数据，不会重新运行分析流程。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "focus_dimension": {
                    "type": "string",
                    "description": "分析维度: 'platform'(按平台), 'question_category'(按问题类别), 'competitor'(按竞品), 'sentiment'(按情感)",
                },
                "focus_value": {
                    "type": "string",
                    "description": "具体值 (如 'deepseek', 'kimi', '华为', 'positive')",
                },
            },
            "required": ["focus_dimension"],
        },
    },
    {
        "name": "compare_snapshots",
        "description": (
            "将当前分析结果与上一次分析结果进行对比。"
            "例如：'和上次比怎么样'、'分数变化了吗'、'显示趋势'。"
            "前置条件：同一品牌至少需要2次分析记录（entity_id必须存在）。"
            "如果只有1次或0次分析，不要调用此工具，告知用户需要更多数据。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "comparison_type": {
                    "type": "string",
                    "description": "'vs_previous'(与上次对比，默认) 或 'vs_specific'(指定快照对比)",
                },
            },
        },
    },
    {
        "name": "ask_user",
        "description": (
            "当需要用户确认或选择时调用。向用户展示选项并等待回复。"
            "例如：确认品牌信息、选择分析模式、确认是否继续下一步。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "向用户展示的确认消息",
                },
                "options": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                            "description": {"type": "string"},
                        },
                        "required": ["id", "label"],
                    },
                    "description": "用户可选择的选项",
                },
                "type": {
                    "type": "string",
                    "enum": ["simple", "guided"],
                    "description": "展示类型：simple=按钮（默认），guided=A/B/C卡片",
                },
                "waiting_tips": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "等待提示（仅在用户确认后将立即执行耗时操作时提供，如AI答案抓取预计10-20分钟。普通确认或选择场景不要填写此字段）",
                },
                "checklist": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "label": {"type": "string"},
                            "checked": {"type": "boolean"},
                        },
                        "required": ["id", "label"],
                    },
                    "description": "完成清单（可选，展示需要确认的项目列表）",
                },
            },
            "required": ["message", "options"],
        },
    },
]


async def build_agent_tools(state: AgentState | None = None) -> list[dict[str, Any]]:
    """Build LLM tools format from static tools + dynamic public skills."""
    if _stable_tool_surface_enabled():
        hidden_tool_names = set()
    else:
        hidden_tool_names = _get_contextual_hidden_tool_names(state)
    base_tools = [
        agent
        for agent in AGENT_REGISTRY
        if agent["name"] not in SKILLIZED_TOOL_NAMES
        and agent["name"] not in hidden_tool_names
    ]
    skill_tools: list[dict[str, Any]] = []
    try:
        async with AsyncSessionLocal() as db:
            service = SkillRegistryService(db)
            scope_context = SkillScopeContext(
                workspace_ref=(
                    str(state.get("user_id"))
                    if state and state.get("user_id")
                    else None
                ),
                entity_ref=(
                    str(state.get("entity_id"))
                    if state and state.get("entity_id")
                    else None
                ),
            )
            skill_tools = await service.get_tool_definitions(
                scope_context=scope_context
            )
    except Exception as exc:
        logger.warning(
            "[Orchestrator] Failed to load dynamic skill tools, falling back to builtins: %s",
            exc,
        )
        skill_tools = build_builtin_skill_tool_definitions()
    skill_tools = [
        definition
        for definition in skill_tools
        if str(definition.get("name") or "") not in hidden_tool_names
    ]
    return [
        {"type": "function", "function": agent} for agent in [*base_tools, *skill_tools]
    ]


# =============================================================================
# System Prompt Builder
# =============================================================================


async def _route_site_confidence_request_without_llm(
    state: AgentState,
    session_id: str,
) -> Command | None:
    if not _is_site_confidence_request(state):
        return None

    tool_args: dict[str, Any] = {"scan_mode": "standard"}
    root_url = _extract_site_confidence_root_url(state)
    if root_url:
        tool_args["root_url"] = root_url

    tool_call = SimpleNamespace(
        name="site_confidence_assessment_skill",
        arguments=tool_args,
        id=f"det_site_confidence_{int(datetime.now().timestamp() * 1000)}",
    )
    new_history = list(state.get("orchestrator_history") or [])
    new_history.append(
        _build_orchestrator_assistant_message(
            reply_text="",
            tool_call_result=tool_call,
            raw_thinking_text="",
        )
    )
    logger.info(
        "[Orchestrator] Deterministically routing site confidence request: %s",
        tool_args,
    )
    return await _handle_tool_call(
        state,
        session_id,
        tool_call,
        "",
        new_history,
    )


# =============================================================================
# Post-Agent Action Directives (共享常量)
# 这些文本同时被 system prompt 和 _build_agent_result_summary 引用
# 修改时请确保两处语义一致
# =============================================================================


async def _complete_standalone_skill_without_llm(
    *,
    state: AgentState,
    session_id: str,
    last_tool: str | None,
) -> Command | None:
    if last_tool != "site_confidence_assessment_skill":
        return None
    if str(state.get("execution_status") or "").lower() != "completed":
        return None

    site_confidence_reply = str(
        state.get("site_confidence_report_message") or ""
    ).strip()
    if not site_confidence_reply:
        return None

    from app.workflow.events import send_execution_complete

    reply_text = _build_agent_result_summary(state, last_tool).strip()
    await send_reply_event(
        session_id,
        reply_text,
        is_delta=True,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)
    await send_execution_complete(session_id, "官网 AI 友好度已完成")

    new_history = list(state.get("orchestrator_history") or [])
    if not (
        new_history
        and isinstance(new_history[-1], dict)
        and new_history[-1].get("role") == "assistant"
        and str(new_history[-1].get("content") or "").strip() == reply_text
    ):
        new_history.append({"role": "assistant", "content": reply_text})

    logger.info(
        "[Orchestrator] Completed site confidence skill without follow-up LLM for session %s",
        session_id,
    )
    return Command(
        goto=END,
        update={
            "execution_status": "completed",
            "awaiting_user": False,
            "pending_confirmation": None,
            "pending_question_set_confirmation": None,
            "next_required_action": None,
            "orchestrator_reply": reply_text,
            "site_confidence_report_message": reply_text,
            "orchestrator_history": new_history,
        },
    )


async def _force_fetch_recovery_confirmation(
    *,
    state: AgentState,
    session_id: str,
    reply_text: str,
    new_history: list[dict[str, Any]],
    request_id: str,
    current_retry_counts: dict[str, int],
) -> Command:
    fetch_mode = resolve_supplemental_fetch_mode(state)
    mode_label = "快速/API" if fetch_mode == "fast" else "完整/浏览器"
    defense_options = [
        {
            "id": "run_supplemental_fetch",
            "label": f"补采失败项（{mode_label}）",
            "description": "沿用上一轮采集模式，仅补采上一轮失败的问题和平台，并保留已有成功结果",
        },
        {
            "id": "run_analysis_report",
            "label": "先用当前结果继续分析",
            "description": "接受当前缺口，直接继续生成分析报告",
        },
    ]
    defense_msg = (
        "上一轮采集仍有失败项。"
        "您可以先补采失败的平台与问题，或者直接基于当前成功样本继续生成分析报告。"
        "请选择下一步："
    )
    visible_reply = reply_text.strip() or defense_msg
    if visible_reply and not reply_text.strip():
        await send_reply_event(
            session_id,
            visible_reply,
            is_delta=True,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)

    await session_event_publisher.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "message": defense_msg,
            "options": defense_options,
            "type": "simple",
        },
    )
    await session_event_publisher.emit_to_session(
        session_id,
        "confirmation_request",
        {
            "request_id": request_id,
            "type": "step_confirmation",
            "message": defense_msg,
            "options": defense_options,
            "allow_text_input": True,
            "step_id": "orchestrator",
            "step_name": "选择补采策略",
        },
    )

    new_history.append(
        {
            "role": "tool",
            "content": "等待用户确认是否补采失败项...",
            "tool_call_id": request_id,
        }
    )
    return Command(
        goto="wait_for_user",
        update={
            "awaiting_user": True,
            "orchestrator_reply": visible_reply,
            "orchestrator_history": new_history,
            "pending_confirmation": {
                "step_id": "orchestrator",
                "step_name": "选择补采策略",
                "message": defense_msg,
                "options": defense_options,
            },
            "agent_retry_counts": current_retry_counts,
        },
    )


async def _force_fetch_mode_confirmation(
    *,
    state: AgentState,
    session_id: str,
    reply_text: str,
    new_history: list[dict[str, Any]],
    request_id: str,
    current_retry_counts: dict[str, int],
) -> Command:
    """Deterministically ask for fetch mode after A3.

    This is the hard guard for the A3 -> A4 handoff. It prevents the flow from
    silently ending when the LLM forgets to call ask_user or returns a pure
    natural-language reply after simulated questions are ready.
    """
    defense_options = [
        {
            "id": "fast",
            "label": "快速采集（推荐）",
            "description": "API + 浏览器混合，约 5-10 分钟",
        },
        {
            "id": "full",
            "label": "完整采集",
            "description": "全浏览器模拟真实用户，约 10-20 分钟，数据最准",
        },
        {
            "id": "regenerate",
            "label": "重新生成问题",
            "description": "对模拟问题不满意，返回重新生成",
        },
    ]
    defense_msg = (
        "品牌全景分析的问题准备已完成。接下来可以进入答案抓取："
        "您会得到各平台对同一组问题的回答、引用来源与品牌提及情况，"
        "后续还可以继续生成分析报告。请选择采集模式："
    )
    visible_reply = reply_text.strip() or _build_ask_user_fallback_reply(
        state,
        "question_simulation",
        defense_msg,
    )
    if visible_reply and not reply_text.strip():
        await send_reply_event(
            session_id,
            visible_reply,
            is_delta=True,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)

    await session_event_publisher.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "message": defense_msg,
            "options": defense_options,
            "type": "simple",
        },
    )
    await session_event_publisher.emit_to_session(
        session_id,
        "confirmation_request",
        {
            "request_id": request_id,
            "type": "step_confirmation",
            "message": defense_msg,
            "options": defense_options,
            "allow_text_input": True,
            "step_id": "orchestrator",
            "step_name": "选择采集模式",
        },
    )

    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["fetch_mode_pending"] = True
    new_history.append(
        {
            "role": "tool",
            "content": "等待用户选择采集模式...",
            "tool_call_id": request_id,
        }
    )
    return Command(
        goto="wait_for_user",
        update={
            "awaiting_user": True,
            "orchestrator_reply": visible_reply,
            "orchestrator_history": new_history,
            "user_decisions": user_decisions,
            "pending_confirmation": {
                "step_id": "orchestrator",
                "step_name": "选择采集模式",
                "message": defense_msg,
                "options": defense_options,
            },
            "agent_retry_counts": current_retry_counts,
        },
    )


async def _force_table_import_confirmation(
    *,
    state: AgentState,
    session_id: str,
    reply_text: str,
    new_history: list[dict[str, Any]],
    request_id: str,
    current_retry_counts: dict[str, int],
) -> Command:
    """Deterministically ask for confirmation after table intake."""

    result = state.get("table_intake_result") or {}
    defense_msg, defense_options, step_name = build_table_import_confirmation_payload(
        result
    )

    visible_reply = reply_text.strip() or _build_ask_user_fallback_reply(
        state,
        "table_intake_skill",
        defense_msg,
    )
    if visible_reply and not reply_text.strip():
        await send_reply_event(
            session_id,
            visible_reply,
            is_delta=True,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)

    await session_event_publisher.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "request_id": request_id,
            "message": defense_msg,
            "options": defense_options,
            "type": "simple",
        },
    )
    await session_event_publisher.emit_to_session(
        session_id,
        "confirmation_request",
        {
            "request_id": request_id,
            "type": "step_confirmation",
            "message": defense_msg,
            "options": defense_options,
            "allow_text_input": True,
            "step_id": "orchestrator",
            "step_name": step_name,
        },
    )

    new_history.append(
        {
            "role": "tool",
            "content": "等待用户确认表格导入...",
            "tool_call_id": request_id,
        }
    )
    return Command(
        goto="wait_for_user",
        update={
            "awaiting_user": True,
            "orchestrator_reply": visible_reply,
            "orchestrator_history": new_history,
            "pending_confirmation": {
                "request_id": request_id,
                "step_id": "orchestrator",
                "step_name": step_name,
                "message": defense_msg,
                "options": defense_options,
            },
            "agent_retry_counts": current_retry_counts,
        },
    )


async def _hydrate_knowledge_manifest(state: AgentState) -> dict[str, Any] | None:
    """Load a lightweight history-availability summary for planning."""

    brand_name = (
        (state.get("brand_profile") or {}).get("brand_name")
        or state.get("brand_name")
        or None
    )
    entity_id = state.get("entity_id")
    if not entity_id and not brand_name:
        return None

    try:
        async with AsyncSessionLocal() as db:
            service = KnowledgeWorkspaceService(db)
            return await service.get_manifest(
                entity_id=entity_id,
                brand_name=brand_name,
            )
    except Exception as exc:
        logger.warning("[Orchestrator] Failed to load knowledge manifest: %s", exc)
        return None


async def _hydrate_ontology_world(state: AgentState) -> dict[str, Any] | None:
    """Load a compact durable object-world summary for planning."""

    raw_entity_id = state.get("entity_id")
    if not raw_entity_id:
        return None
    try:
        entity_uuid = UUID(str(raw_entity_id))
    except (TypeError, ValueError):
        return None

    actor_uuid: UUID | None = None
    raw_actor_id = state.get("user_id") or state.get("actor_id")
    if raw_actor_id:
        try:
            actor_uuid = UUID(str(raw_actor_id))
        except (TypeError, ValueError):
            actor_uuid = None

    try:
        async with AsyncSessionLocal() as db:
            service = BrandOntologyWorldService(db)
            return await service.build_dashboard_summary(
                entity_id=entity_uuid,
                actor_id=actor_uuid,
                include_action_input_values=True,
                include_official_content_audit=False,
            )
    except Exception as exc:
        logger.warning("[Orchestrator] Failed to load ontology world: %s", exc)
        return None


async def _route_ontology_intelligence_explanation_without_llm(
    *,
    state: AgentState,
    session_id: str,
    ontology_world: dict[str, Any] | None,
) -> Command | None:
    if not ontology_world:
        return None
    if not _is_ontology_intelligence_explanation_request(state):
        return None

    from app.workflow.events import send_execution_complete

    reply_text = _build_ontology_intelligence_explanation_reply(state, ontology_world)
    await send_reply_event(
        session_id,
        reply_text,
        is_delta=True,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)
    await send_execution_complete(session_id, "情报解释完成")

    new_history = list(state.get("orchestrator_history") or [])
    new_history.append({"role": "assistant", "content": reply_text})
    return Command(
        goto=END,
        update={
            "execution_status": "completed",
            "awaiting_user": False,
            "pending_confirmation": None,
            "orchestrator_reply": reply_text,
            "orchestrator_history": new_history,
            "ontology_world": ontology_world,
        },
    )


async def _resolve_skill_tool(
    tool_name: str,
    *,
    tool_args: dict[str, Any] | None = None,
    state: AgentState | None = None,
) -> SkillInvocationPlan | None:
    """Resolve a tool call into an enabled public skill definition."""

    try:
        async with AsyncSessionLocal() as db:
            service = SkillInvocationService(db)
            scope_context = SkillScopeContext(
                workspace_ref=(
                    str(state.get("user_id"))
                    if state and state.get("user_id")
                    else None
                ),
                entity_ref=(
                    str(state.get("entity_id"))
                    if state and state.get("entity_id")
                    else None
                ),
            )
            return await service.resolve_invocation(
                tool_name=tool_name,
                tool_args=dict(tool_args or {}),
                scope_context=scope_context,
            )
    except Exception as exc:
        logger.warning(
            "[Orchestrator] Failed to resolve skill tool %s: %s", tool_name, exc
        )
        return None


# =============================================================================
# Tool Call → Node Mapping
# =============================================================================

TOOL_TO_NODE: dict[str, str] = {
    "brand_analysis": "a1_brand",
    "persona_generation": "a2_persona",
    "question_simulation": "a3_question",
    "answer_fetch": "a4_fetch",
    # 3b-1.2: amway 实体抽取/圈层图谱独立节点（拓扑感知编排）
    "amway_entity_extract": "amway_extract",
    "amway_circle_projection": "amway_projection",
    "amway_secondary_analysis": "amway_analysis",
    "amway_content_draft": "amway_content",
    "table_intake_skill": "table_intake",
    "analysis_report_skill": "a5_analytics",
    "data_analytics": "a5_analytics",
}

# Remaining static tools (non-amway registry surface)
TOOL_TO_NODE.update(
    {
        "knowledge_lookup": "knowledge_lookup",
        "knowledge_aggregate": "knowledge_aggregate",
        "knowledge_compare": "knowledge_compare",
        "knowledge_export": "knowledge_export",
        "confidence_analysis_skill": "confidence_analysis_executor",
        "site_confidence_assessment_skill": "site_confidence_assessment_executor",
        "post_analysis_skill": "post_analysis_executor",
        "drill_down_analysis": "drill_down",
        "compare_snapshots": "compare_snapshots",
        # Monitoring tools (Cycle 4)
        "manage_monitoring_schedule": "create_monitoring",
        "create_monitoring_schedule": "create_monitoring",
    }
)

# P1-8: overlay registry-driven tool→graph mappings (registry wins when present)
try:
    from app.workflow.node_contracts import (
        CANVAS_TO_TOOL as _REGISTRY_CANVAS_TO_TOOL,
        get_contract as _get_contract,
    )

    for _canvas_id, _tool in _REGISTRY_CANVAS_TO_TOOL.items():
        _c = _get_contract(_canvas_id)
        if _c and _c.graph_node and _tool:
            TOOL_TO_NODE[_tool] = _c.graph_node
except Exception:  # pragma: no cover - registry optional at import
    pass

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "brand_analysis": "品牌竞品分析",
    "persona_generation": "用户画像生成",
    "question_simulation": "问题模拟生成",
    "answer_fetch": "AI答案抓取",
    "amway_entity_extract": "实体关系抽取",
    "amway_circle_projection": "圈层图谱构建",
    "amway_secondary_analysis": "数据分析节点",
    "amway_content_draft": "内容创作节点",
    "table_intake_skill": "表格导入理解",
    "analysis_report_skill": "完整分析报告",
    "data_analytics": "数据分析报告",
    "knowledge_lookup": "过往资料检索",
    "knowledge_aggregate": "过往资料整理",
    "knowledge_compare": "过往资料对比",
    "knowledge_export": "过往资料表",
    "confidence_signal_skill": "引用置信度评估",
    "citation_confidence_analysis": "引用内容置信度评估",
    "confidence_analysis_skill": "引用置信度评估",
    "site_confidence_assessment_skill": "官网 AI 友好度",
    "post_analysis_skill": "后续分析",
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    # Monitoring tools (Cycle 4)
    "manage_monitoring_schedule": "管理监测计划",
    "create_monitoring_schedule": "创建监测计划",
}

# Step definitions for workflow progress tracking


async def _execute_runtime_policy_action(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    raw_action = state.get("next_required_action")
    action = parse_next_required_action(raw_action)
    if action is None:
        if raw_action:
            logger.warning(
                "[Orchestrator] Ignoring next_required_action without recognized authority: %s",
                raw_action,
            )
        return None

    logger.info(
        "[Orchestrator] Consuming next_required_action: tool=%s authority=%s source=%s reason=%s",
        action.tool_name,
        action.authority,
        action.source_step or "unknown",
        action.reason,
    )
    sanitized_state = _sanitize_runtime_policy_state(state)
    history = build_orchestrator_messages(sanitized_state)
    if action.reply_text:
        history.append({"role": "assistant", "content": action.reply_text})
        await send_reply_event(
            session_id,
            action.reply_text,
            is_delta=False,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)

    synthetic_tool_call = SimpleNamespace(
        name=action.tool_name,
        arguments=dict(action.tool_args or {}),
        id=f"runtime_policy_{action.tool_name}",
    )
    command = await _handle_tool_call(
        sanitized_state,
        session_id,
        synthetic_tool_call,
        action.reply_text,
        history,
    )
    return _merge_command_update(
        command,
        {
            **clear_runtime_policy_fields(),
            "error_info": None,
        },
    )


async def _route_brand_seed_without_llm(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    brand_seed = _infer_brand_seed_candidate(state)
    if not brand_seed:
        return None

    seeded_state: AgentState = {**state, "brand_name": brand_seed}
    manifest = await _hydrate_knowledge_manifest(seeded_state)
    if manifest is not None:
        seeded_state = {**seeded_state, "knowledge_manifest": manifest}

    available_sources = (manifest or {}).get("available_sources") or {}
    has_history_materials = not _session_was_recalled(seeded_state) and any(
        bool(value) for value in available_sources.values()
    )

    if has_history_materials:
        reply_text = (
            f"我先查看过往资料里和「{brand_seed}」相关的记录，"
            "如果已有品牌档案、竞品信息或过往抓取结果，就优先复用这些事实继续分析。"
        )
        tool_name = "knowledge_lookup"
        tool_args = {
            "query": brand_seed,
            "limit": 6,
        }
    else:
        reply_text = (
            f"我先补充「{brand_seed}」的品牌信息和竞品格局，"
            "拿到真实品牌事实后再继续后续分析。"
        )
        tool_name = "brand_analysis"
        tool_args = {
            "brand_name": brand_seed,
        }

    logger.info(
        "[Orchestrator] Applying brand-seed routing for '%s' via %s",
        brand_seed,
        tool_name,
    )

    history = build_orchestrator_messages(_sanitize_runtime_policy_state(seeded_state))
    history.append({"role": "assistant", "content": reply_text})

    await send_reply_event(
        session_id,
        reply_text,
        is_delta=False,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)

    synthetic_tool_call = SimpleNamespace(
        name=tool_name,
        arguments=tool_args,
        id=f"brand_seed_{tool_name}",
    )
    command = await _handle_tool_call(
        seeded_state,
        session_id,
        synthetic_tool_call,
        reply_text,
        history,
    )
    extra_update: dict[str, Any] = {"brand_name": brand_seed}
    if manifest is not None:
        extra_update["knowledge_manifest"] = manifest
    return _merge_command_update(command, extra_update)


async def _route_current_import_query_without_llm(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    query = _infer_current_import_query(state)
    if not query:
        return None

    reply_text = "我先只查看本次上传表格里识别出的内容，不混入历史资料。"
    history = build_orchestrator_messages(_sanitize_runtime_policy_state(state))
    history.append({"role": "assistant", "content": reply_text})

    await send_reply_event(
        session_id,
        reply_text,
        is_delta=False,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)

    synthetic_tool_call = SimpleNamespace(
        name="knowledge_export",
        arguments={
            "query": query,
            "source_scope": "current_import_artifact",
            "limit": 200,
        },
        id="current_import_knowledge_export",
    )
    return await _handle_tool_call(
        state,
        session_id,
        synthetic_tool_call,
        reply_text,
        history,
    )


async def _route_history_answer_query_without_llm(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    resolved_query = _resolve_bounded_history_answer_query(state)
    if not resolved_query:
        return None

    latest_user_message = _get_latest_user_message(state)
    if _is_history_answer_continuation_query(latest_user_message):
        reply_text = "我直接展开刚才那组历史回答的完整内容，不再重新拆成多轮检索。"
    else:
        reply_text = "我先按历史回答内容做一次定向筛选，再整理出你要看的具体回答，不拆成多轮重复检索。"
    history = build_orchestrator_messages(_sanitize_runtime_policy_state(state))
    history.append({"role": "assistant", "content": reply_text})

    await send_reply_event(
        session_id,
        reply_text,
        is_delta=False,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)

    synthetic_tool_call = SimpleNamespace(
        name="knowledge_export",
        arguments={
            "query": resolved_query,
            "source_types": ["fetch_answer"],
            "limit": 200,
        },
        id="bounded_history_answer_export",
    )
    return await _handle_tool_call(
        state,
        session_id,
        synthetic_tool_call,
        reply_text,
        history,
    )


async def _route_history_answer_export_completion_without_llm(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    resolved_query = _resolve_bounded_history_answer_query(state)
    if not resolved_query:
        return None

    result = state.get("knowledge_export_result") or {}
    if (
        not isinstance(result, dict)
        or result.get("status") != "hit"
        or str(result.get("source_scope") or "").strip() == "current_import_artifact"
        or str(result.get("query") or "").strip() != resolved_query
    ):
        return None

    reply_text = _build_knowledge_export_completion_reply(result)
    history = build_orchestrator_messages(_sanitize_runtime_policy_state(state))
    history.append({"role": "assistant", "content": reply_text})

    await send_reply_event(
        session_id,
        reply_text,
        is_delta=False,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)
    from app.workflow.events import send_execution_complete

    await send_execution_complete(session_id, "过往资料查询完成")
    return Command(
        goto=END,
        update={
            "execution_status": "completed",
            "orchestrator_reply": reply_text,
            "orchestrator_history": history,
        },
    )


async def _route_agent_error_without_llm(
    state: AgentState,
    session_id: str,
    current_retry_counts: dict[str, int],
) -> Command:
    error_info = dict(state.get("error_info") or {})
    failed_step = str(error_info.get("step", "未知"))
    blocker_code = str(
        ((state.get("last_harness_decision") or {}).get("metadata") or {}).get(
            "blocker_code"
        )
        or ""
    ).strip()
    recovery_options = build_alternative_action_catalog(
        state,
        failed_step=failed_step,
        blocker_code=blocker_code,
    )
    recovery_message = _build_error_recovery_message(
        error_info,
        recovery_options,
    )

    await send_reply_event(
        session_id,
        recovery_message,
        is_delta=True,
        is_new_round=True,
    )
    await send_reply_event(session_id, "", is_complete=True)
    await send_confirmation_request(
        session_id=session_id,
        step_id="error_recovery",
        step_name=f"{failed_step} 执行失败",
        message=recovery_message,
        options=recovery_options,
    )

    new_history = build_orchestrator_messages(state)
    new_history.append({"role": "assistant", "content": recovery_message})

    return Command(
        goto="wait_for_user",
        update={
            "awaiting_user": True,
            "orchestrator_reply": recovery_message,
            "orchestrator_history": new_history,
            "pending_confirmation": {
                "step_id": "error_recovery",
                "step_name": f"{failed_step} 执行失败",
                "message": recovery_message,
                "options": recovery_options,
            },
            "agent_retry_counts": current_retry_counts,
        },
    )


# =============================================================================
# Orchestrator Node
# =============================================================================


async def orchestrator_node(state: AgentState) -> Command:
    """Main orchestrator node: uses LLM Function Calling to decide next action.

    The LLM's content field is the natural language reply (Layer 1 + Layer 2),
    and tool_calls are the structured decisions (which Agent to invoke).
    """
    session_id = state["session_id"]

    # 检测用户重试意图 — 重置 agent_retry_counts
    # 同时检查 messages 和 orchestrator_history，因为 confirmation 路径只更新 orchestrator_history
    retry_detected = False
    retry_keywords = ["重试", "再试", "再来", "重新生成", "retry", "again", "redo"]

    # 检查 orchestrator_history 最后一条 user 消息（两种路径都会更新）
    orch_history = state.get("orchestrator_history", [])
    for msg in reversed(orch_history):
        if msg.get("role") == "user":
            if any(kw in msg.get("content", "") for kw in retry_keywords):
                retry_detected = True
            break

    # 备选：也检查 messages 最后一条
    if not retry_detected:
        user_messages = state.get("messages", [])
        if user_messages:
            last_msg = user_messages[-1] if isinstance(user_messages[-1], dict) else {}
            last_content = (
                last_msg.get("content", "") if last_msg.get("role") == "user" else ""
            )
            if any(kw in last_content for kw in retry_keywords):
                retry_detected = True

    if retry_detected:
        logger.info(
            "[Orchestrator] User retry intent detected, resetting agent_retry_counts"
        )
        state = {**state, "agent_retry_counts": {}}

    current_retry_counts = dict(state.get("agent_retry_counts", {}) or {})
    error_info = state.get("error_info")
    exec_status = state.get("execution_status")
    has_agent_error = bool(error_info and exec_status != "completed")

    # If returning from an Agent, send step completion event
    last_tool = _get_tool_name_from_node(state.get("next_action", "") or "")
    if last_tool and last_tool in TOOL_TO_NODE:
        display_name = TOOL_DISPLAY_NAMES.get(last_tool, last_tool)
        workflow_steps = _build_workflow_steps(state)
        completed_count = sum(1 for s in workflow_steps if s["status"] == "completed")
        skipped_count = sum(1 for s in workflow_steps if s["status"] == "skipped")
        total_count = len(workflow_steps)
        is_standalone_skill_complete = exec_status == "completed" and last_tool in {
            "site_confidence_assessment_skill",
            "confidence_analysis_skill",
            "post_analysis_skill",
            "drill_down_analysis",
            "compare_snapshots",
        }
        # In baseline mode, Phase 1 completion is not "all done" — Phase 2 may follow
        is_baseline_phase = state.get("analysis_mode") == "baseline"
        all_done = (
            completed_count + skipped_count
        ) == total_count and not is_baseline_phase
        completion_progress = (
            1.0 if is_standalone_skill_complete else completed_count / total_count
        )
        from app.workflow.events import send_progress_event

        if has_agent_error and _matches_failed_step(
            last_tool, str((error_info or {}).get("step", ""))
        ):
            await send_progress_event(
                session_id,
                step=last_tool,
                step_name=display_name,
                progress=completed_count / total_count,
                message=f"执行失败：{display_name}",
                status="error",
                steps=workflow_steps,
            )
            await send_action_log_event(
                session_id,
                "generic",
                f"{display_name} 执行失败",
                step=last_tool,
                is_complete=True,
            )
        else:
            await send_progress_event(
                session_id,
                step=last_tool,
                step_name=display_name,
                progress=completion_progress,
                message=f"完成：{display_name}",
                status=(
                    "completed"
                    if all_done or is_standalone_skill_complete
                    else "running"
                ),
                steps=workflow_steps,
            )
            await send_action_log_event(
                session_id,
                "agent_complete",
                f"{display_name} 完成",
                step=last_tool,
                is_complete=True,
            )
            await send_plan_event(
                session_id,
                f"已完成：{display_name}",
            )

    completed_standalone_command = await _complete_standalone_skill_without_llm(
        state=state,
        session_id=session_id,
        last_tool=last_tool,
    )
    if completed_standalone_command is not None:
        return completed_standalone_command

    if _is_completed_analysis_report_state(state):
        logger.info(
            "[Orchestrator] Final analysis report completed; ending run for session %s",
            session_id,
        )
        from app.workflow.events import send_execution_complete

        await send_execution_complete(session_id, "分析完成")
        return Command(
            goto=END,
            update={
                "execution_status": "completed",
                "awaiting_user": False,
                "pending_confirmation": None,
                "pending_question_set_confirmation": None,
                "next_required_action": None,
                "progress": 1.0,
                "progress_message": "分析完成",
            },
        )

    if _is_completed_question_generation_only_state(state):
        logger.info(
            "[Orchestrator] Question-only A3 completed; ending run for session %s",
            session_id,
        )
        from app.workflow.events import send_execution_complete

        brand_name = (
            str((state.get("brand_profile") or {}).get("brand_name") or "").strip()
            or str(state.get("brand_name") or "").strip()
            or "当前品牌"
        )
        await send_execution_complete(
            session_id,
            "问题生成完成",
            follow_up_suggestions=[
                {
                    "id": "continue-fetch-answers",
                    "label": "继续抓取答案",
                    "message": (
                        f"请基于刚生成的问题列表，继续抓取「{brand_name}」在 AI 平台里的回答，"
                        "并完成品牌情报分析。重点输出 AI 提及率、提及排名、官网引用率和语气性质。"
                    ),
                    "type": "refetch",
                },
                {
                    "id": "adjust-question-scope",
                    "label": "调整问题范围",
                    "message": (
                        f"请先帮我调整「{brand_name}」的问题范围，再继续抓取 AI 平台回答。"
                    ),
                    "type": "general",
                },
            ],
        )
        return Command(
            goto=END,
            update={
                "execution_status": "completed",
                "awaiting_user": False,
                "pending_confirmation": None,
                "pending_question_set_confirmation": None,
                "next_required_action": None,
                "progress": 1.0,
                "progress_message": "问题生成完成",
            },
        )

    if has_agent_error:
        logger.warning(
            "[Orchestrator] Short-circuiting error recovery for session %s: step=%s category=%s",
            session_id,
            (error_info or {}).get("step"),
            (error_info or {}).get("category"),
        )
        return await _route_agent_error_without_llm(
            state=state,
            session_id=session_id,
            current_retry_counts=current_retry_counts,
        )

    confirmed_import_action = dict(state.get("confirmed_import_action") or {})
    confirmed_table_kind = str(confirmed_import_action.get("table_kind") or "")
    import_confirmed = bool(
        (state.get("user_decisions") or {}).get("table_import_confirmed")
    )
    if confirmed_table_kind == "question_list" and import_confirmed:
        uploaded_ready = (state.get("simulated_questions") or {}).get(
            "generation_mode"
        ) == "uploaded_list"
        if not uploaded_ready:
            user_decisions = dict(state.get("user_decisions", {}))
            user_decisions["a3_mode"] = "uploaded_list"
            return Command(
                goto="a3_question",
                update={
                    "next_action": "a3_question",
                    "analysis_mode": "persona",
                    "user_decisions": user_decisions,
                },
            )
    elif confirmed_table_kind in {"brand_competitor_info", "link_list"}:
        return Command(
            goto="table_import_apply",
            update={"next_action": "table_import_apply"},
        )

    runtime_policy_command = await _execute_runtime_policy_action(
        state=state,
        session_id=session_id,
    )
    if runtime_policy_command is not None:
        return runtime_policy_command

    brand_seed_command = await _route_brand_seed_without_llm(
        state=state,
        session_id=session_id,
    )
    if brand_seed_command is not None:
        return brand_seed_command

    current_import_command = await _route_current_import_query_without_llm(
        state=state,
        session_id=session_id,
    )
    if current_import_command is not None:
        return current_import_command

    history_answer_completion_command = (
        await _route_history_answer_export_completion_without_llm(
            state=state,
            session_id=session_id,
        )
    )
    if history_answer_completion_command is not None:
        return history_answer_completion_command

    history_answer_command = await _route_history_answer_query_without_llm(
        state=state,
        session_id=session_id,
    )
    if history_answer_command is not None:
        return history_answer_command

    site_confidence_command = await _route_site_confidence_request_without_llm(
        state=state,
        session_id=session_id,
    )
    if site_confidence_command is not None:
        return site_confidence_command

    working_state = state
    state_updates: dict[str, Any] = {}
    manifest = await _hydrate_knowledge_manifest(state)
    if manifest is not None:
        state_updates["knowledge_manifest"] = manifest
    ontology_world = await _hydrate_ontology_world(state)
    if ontology_world is not None:
        state_updates["ontology_world"] = ontology_world
        ontology_action_plan = _build_ontology_action_plan(
            {**state, **state_updates},
            ontology_world,
        )
        if ontology_action_plan is not None:
            state_updates["ontology_action_plan"] = ontology_action_plan
    if state_updates:
        working_state = {**state, **state_updates}

    ontology_explanation_command = (
        await _route_ontology_intelligence_explanation_without_llm(
            state=working_state,
            session_id=session_id,
            ontology_world=working_state.get("ontology_world"),
        )
    )
    if ontology_explanation_command is not None:
        return ontology_explanation_command

    llm_state = _sanitize_runtime_policy_state(working_state)

    # Build orchestrator call
    prompt_assembly = build_orchestrator_prompt_assembly(llm_state)
    prompt_bundle = _build_orchestrator_prompt_bundle_from_assembly(prompt_assembly)
    system_prompt = prompt_bundle.system_prompt
    runtime_reminder_source = prompt_assembly.render_runtime_reminder_message()
    messages = build_orchestrator_messages(
        llm_state,
        runtime_reminder_message=prompt_bundle.runtime_reminder_message,
    )
    tools = await build_agent_tools(llm_state)

    # Stream LLM response
    model = get_orchestrator_llm_model()

    reply_text = ""
    thinking_text = ""
    raw_thinking_text = ""
    tool_call_result = None
    is_first_reply_chunk = True
    last_finish_reason: str | None = None
    last_usage = None
    stream_started_at = perf_counter()
    stream_thoughts = _should_stream_thoughts(llm_state)
    thinking_placeholder_sent = False
    first_chunk_logged = False

    logger.info(
        "[Orchestrator] Stream started for session %s: messages=%d tools=%d current_skill=%s next_action=%s",
        session_id,
        len(messages) + 1,
        len(tools),
        state.get("current_skill"),
        state.get("next_action"),
    )
    logger.info(
        "[Orchestrator] Stream payload summary for session %s: roles=%s",
        session_id,
        [
            {
                "role": item.get("role"),
                "has_tool_calls": bool(item.get("tool_calls")),
                "has_tool_call_id": bool(item.get("tool_call_id")),
                "content_len": len(str(item.get("content") or "")),
            }
            for item in (
                [{"role": "system", "content": system_prompt}, *messages][-12:]
            )
        ],
    )

    try:
        async for chunk in async_wrap_sync_gen(
            lambda: model.stream(
                messages=[
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
                tools=tools,
                temperature=0.3,
                tool_choice="auto",
            )
        ):
            if not first_chunk_logged:
                logger.info(
                    "[Orchestrator] First stream chunk received for session %s: has_content=%s has_thinking=%s has_tool_calls=%s finish=%s",
                    session_id,
                    bool(chunk.content),
                    bool(chunk.thinking_blocks),
                    bool(chunk.tool_calls),
                    chunk.finish_reason,
                )
                first_chunk_logged = True
            # Tool calls arrive at end of stream.
            # IMPORTANT: The final chunk with tool_calls also contains the
            # full accumulated content_buffer and reasoning_buffer (not deltas),
            # so we must skip content/thinking processing for that chunk.
            if chunk.finish_reason:
                last_finish_reason = chunk.finish_reason
            if chunk.usage:
                last_usage = chunk.usage
            if chunk.tool_calls:
                if chunk.thinking_blocks and not raw_thinking_text:
                    raw_thinking_text = "".join(
                        block.text for block in chunk.thinking_blocks if block.text
                    )
                logger.warning(
                    "[Orchestrator] Stream tool_calls captured for session %s: %s finish=%s",
                    session_id,
                    [
                        {
                            "name": tc.name,
                            "arguments": tc.arguments,
                            "id": tc.id,
                        }
                        for tc in chunk.tool_calls
                    ],
                    chunk.finish_reason,
                )
                tool_call_result = chunk.tool_calls[0]
                continue

            # Stream main reply (Layer 1)
            if chunk.content:
                reply_text += chunk.content
                await send_reply_event(
                    session_id,
                    chunk.content,
                    is_delta=True,
                    is_new_round=is_first_reply_chunk,
                )
                is_first_reply_chunk = False

            # Stream thinking process
            if chunk.thinking_blocks:
                for block in chunk.thinking_blocks:
                    if block.text:
                        raw_thinking_text += block.text
                        if stream_thoughts:
                            streamed_thought, thinking_placeholder_sent = (
                                _normalize_thought_text_for_stream(
                                    block.text,
                                    placeholder_sent=thinking_placeholder_sent,
                                )
                            )
                            if streamed_thought:
                                thinking_text += streamed_thought
                                await send_thought_event(
                                    session_id, streamed_thought, is_delta=True
                                )

        # Mark reply as complete
        await send_reply_event(session_id, "", is_complete=True)

        if stream_thoughts and thinking_text:
            await send_thought_event(session_id, "", is_complete=True)

        logger.warning(
            "[Orchestrator] Stream completed for session %s: reply_len=%d thinking_len=%d finish=%s saw_tool=%s",
            session_id,
            len(reply_text),
            len(thinking_text),
            last_finish_reason,
            bool(tool_call_result),
        )

        if last_usage:
            from app.services.llm_usage_service import (
                record_llm_usage_async,
                resolve_llm_model_identity,
            )

            await record_llm_usage_async(
                session_id=session_id,
                task_id=state.get("task_id"),
                skill_key=None,
                step="orchestrator",
                step_name="编排决策",
                model=model,
                usage=last_usage,
                latency_ms=max(int((perf_counter() - stream_started_at) * 1000), 0),
                extra_metadata={
                    "streaming": True,
                    "message_count": len(messages) + 1,
                    "tool_count": len(tools),
                    "static_prompt_hash": prompt_bundle.static_prompt_hash,
                    "runtime_reminder_hash": prompt_bundle.runtime_reminder_hash,
                    "tool_surface_hash": fingerprint_tools(tools),
                    "system_prompt_length": len(system_prompt),
                    "runtime_context_size": len(runtime_reminder_source),
                    "prompt_layer_manifest": prompt_bundle.prompt_layer_manifest,
                    "model_identity": resolve_llm_model_identity(model),
                    "runtime_reminder_enabled": (
                        prompt_bundle.runtime_reminder_enabled
                    ),
                    "stable_tool_surface_enabled": _stable_tool_surface_enabled(),
                    "stable_skill_tool_description_enabled": bool(
                        getattr(
                            get_settings(),
                            "STABLE_SKILL_TOOL_DESCRIPTION_ENABLED",
                            False,
                        )
                    ),
                },
            )

        # Check finish_reason for abnormal termination
        if last_finish_reason == "sensitive":
            logger.warning("[Orchestrator] Response blocked by content safety filter")
            from app.workflow.events import send_error_event

            await send_error_event(
                session_id,
                "orchestrator",
                "内容被安全审核拦截，请调整输入后重试",
                recoverable=True,
            )
        elif last_finish_reason == "length":
            logger.warning("[Orchestrator] Response truncated due to max_tokens")
            from app.workflow.events import send_error_event

            await send_error_event(
                session_id,
                "orchestrator",
                "回复被截断（达到最大token限制），结果可能不完整",
                recoverable=True,
            )

        # Build updated orchestrator history
        new_history = list(messages)
        assistant_msg = _build_orchestrator_assistant_message(
            reply_text=reply_text,
            tool_call_result=tool_call_result,
            raw_thinking_text=raw_thinking_text,
        )
        new_history.append(assistant_msg)

        if tool_call_result:
            logger.info(
                "[Orchestrator] Routing captured tool call for session %s: %s",
                session_id,
                tool_call_result.name,
            )
            return await _handle_tool_call(
                llm_state, session_id, tool_call_result, reply_text, new_history
            )

        knowledge_fallback = _infer_knowledge_fallback_tool(llm_state)
        if knowledge_fallback is not None:
            fallback_tool_name, fallback_tool_args = knowledge_fallback
            logger.info(
                "[Orchestrator] No tool call after stream; heuristic candidate=%s args=%s (not auto-forced)",
                fallback_tool_name,
                fallback_tool_args,
            )

        table_result = state.get("table_intake_result") or {}
        if (
            last_tool == "table_intake_skill"
            and table_result.get("table_kind")
            in {"question_list", "brand_competitor_info", "link_list"}
            and not dict(state.get("user_decisions", {})).get("table_import_confirmed")
        ):
            logger.warning(
                "[Orchestrator] No tool call after table_intake_skill; forcing import confirmation."
            )
            return await _force_table_import_confirmation(
                state=llm_state,
                session_id=session_id,
                reply_text=reply_text,
                new_history=new_history,
                request_id=f"defense_table_import_{int(datetime.now().timestamp() * 1000)}",
                current_retry_counts=current_retry_counts,
            )

        user_decisions = dict(state.get("user_decisions", {}))
        selected_fetch_mode = str(state.get("fetch_mode") or "").strip().lower()
        if (
            last_tool == "question_simulation"
            and state.get("simulated_questions")
            and not _is_question_generation_only_state(llm_state)
            and not user_decisions.get("fetch_mode_confirmed", False)
            and not user_decisions.get("fetch_mode_pending", False)
            and selected_fetch_mode not in {"fast", "full"}
        ):
            logger.warning(
                "[Orchestrator] No tool call after A3 completion; "
                "forcing fetch-mode confirmation instead of ending run."
            )
            return await _force_fetch_mode_confirmation(
                state=llm_state,
                session_id=session_id,
                reply_text=reply_text,
                new_history=new_history,
                request_id=f"defense_fetch_{int(datetime.now().timestamp() * 1000)}",
                current_retry_counts=current_retry_counts,
            )

        if (
            last_tool == "knowledge_aggregate"
            and _should_force_fetch_recovery_confirmation(llm_state)
        ):
            logger.warning(
                "[Orchestrator] No tool call after latest-run failure summary; forcing supplemental fetch confirmation."
            )
            return await _force_fetch_recovery_confirmation(
                state=llm_state,
                session_id=session_id,
                reply_text=reply_text,
                new_history=new_history,
                request_id=f"defense_fetch_recovery_{int(datetime.now().timestamp() * 1000)}",
                current_retry_counts=current_retry_counts,
            )

        # No tool call — check if we're in an error state before ending
        error_info = state.get("error_info")
        exec_status = state.get("execution_status")
        if error_info and exec_status != "completed":
            # Agent failed but LLM didn't call a tool — offer user choices
            failed_step = error_info.get("step", "未知")
            failed_step_label = get_user_visible_runtime_label(failed_step)
            error_msg = error_info.get("error", "未知错误")
            logger.warning(
                f"[Orchestrator] Error state detected (step={failed_step}), "
                f"redirecting to user confirmation instead of END"
            )
            await send_confirmation_request(
                session_id=session_id,
                step_id="error_recovery",
                step_name=f"{failed_step_label}执行失败",
                message=(
                    f"{failed_step_label}遇到问题：{error_msg[:100]}。"
                    f"请选择后续操作："
                ),
                options=[
                    {
                        "id": "retry",
                        "label": "重新尝试",
                        "description": f"再次执行{failed_step_label}",
                    },
                    {
                        "id": "skip",
                        "label": "跳过此步骤",
                        "description": "跳过此步骤，继续后续分析",
                    },
                    {
                        "id": "manual",
                        "label": "手动提供数据",
                        "description": "由您手动描述所需信息",
                    },
                ],
            )
            return Command(
                goto="wait_for_user",
                update={
                    "awaiting_user": True,
                    "orchestrator_reply": reply_text,
                    "orchestrator_history": new_history,
                    "pending_confirmation": {
                        "step_id": "error_recovery",
                        "step_name": f"{failed_step_label}执行失败",
                        "message": f"{failed_step_label}遇到问题",
                        "options": [
                            {"id": "retry", "label": "重新尝试"},
                            {"id": "skip", "label": "跳过此步骤"},
                            {"id": "manual", "label": "手动提供数据"},
                        ],
                    },
                },
            )

        # Pure conversation reply, execution complete
        from app.workflow.events import send_execution_complete

        await send_execution_complete(session_id, "对话完成")
        return Command(
            goto=END,
            update={
                "execution_status": "completed",
                "orchestrator_reply": reply_text,
                "orchestrator_history": new_history,
            },
        )

    except TimeoutError as e:
        logger.error(
            "[Orchestrator] Stream timed out for session %s: %s", session_id, e
        )
        from app.workflow.events import send_error_event

        await send_error_event(session_id, "orchestrator", str(e), recoverable=True)
        return Command(
            goto=END,
            update={
                "execution_status": "error",
                "error_info": {
                    "step": "orchestrator",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
            },
        )
    except Exception as e:
        logger.error(
            "[Orchestrator] Error for session %s: %s payload_roles=%s",
            session_id,
            e,
            [
                {
                    "role": item.get("role"),
                    "has_tool_calls": bool(item.get("tool_calls")),
                    "has_tool_call_id": bool(item.get("tool_call_id")),
                    "content_len": len(str(item.get("content") or "")),
                }
                for item in (
                    [{"role": "system", "content": system_prompt}, *messages][-12:]
                )
            ],
            exc_info=True,
        )
        from app.workflow.events import send_error_event

        await send_error_event(session_id, "orchestrator", str(e), recoverable=False)
        return Command(
            goto=END,
            update={
                "execution_status": "error",
                "error_info": {
                    "step": "orchestrator",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
            },
        )


async def _build_ontology_action_gate_command(
    *,
    state: AgentState,
    session_id: str,
    tool_call,
    reply_text: str,
    new_history: list[dict[str, Any]],
    current_retry_counts: dict[str, Any],
    decision: dict[str, Any],
    display_name: str,
) -> Command:
    action_item = decision.get("action") or {}
    action_name = str(action_item.get("display_name") or display_name).strip()
    kind = str(decision.get("kind") or "blocked")
    message = _ontology_action_gate_message(
        kind=kind,
        action_name=action_name,
        action_item=action_item,
        reason=str(decision.get("reason") or ""),
    )
    tool_call_id = getattr(tool_call, "id", None) or "call_1"

    if state.get("headless_mode") or kind == "blocked":
        new_history.append(
            {
                "role": "tool",
                "content": message,
                "tool_call_id": tool_call_id,
                "name": getattr(tool_call, "name", display_name),
            }
        )
        return Command(
            goto="orchestrator",
            update={
                "orchestrator_reply": reply_text,
                "orchestrator_history": new_history,
                "agent_retry_counts": current_retry_counts,
                "last_validation_result": {
                    "gate_name": "ontology_action_gate",
                    "passed": False,
                    "tool_name": getattr(tool_call, "name", display_name),
                    "action_key": decision.get("action_key"),
                    "reason": message,
                },
            },
        )

    if not reply_text.strip():
        await send_reply_event(
            session_id,
            message,
            is_delta=True,
            is_new_round=True,
        )
        await send_reply_event(session_id, "", is_complete=True)
        reply_text = message

    request_id = f"ontology_{decision.get('action_key')}_{tool_call_id}"
    options = _ontology_action_gate_options(kind, action_item)
    await session_event_publisher.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "request_id": request_id,
            "message": message,
            "options": options,
            "type": "simple",
        },
    )
    await session_event_publisher.emit_to_session(
        session_id,
        "confirmation_request",
        {
            "request_id": request_id,
            "type": "step_confirmation",
            "message": message,
            "options": options,
            "allow_text_input": True,
            "step_id": "ontology_action_gate",
            "step_name": "确认行动",
        },
    )
    new_history.append(
        {
            "role": "tool",
            "content": "等待用户补充信息或确认行动。",
            "tool_call_id": tool_call_id,
            "name": getattr(tool_call, "name", display_name),
        }
    )
    return Command(
        goto="wait_for_user",
        update={
            "awaiting_user": True,
            "orchestrator_reply": reply_text,
            "orchestrator_history": new_history,
            "pending_confirmation": {
                "request_id": request_id,
                "step_id": "ontology_action_gate",
                "step_name": "确认行动",
                "message": message,
                "options": options,
            },
            "agent_retry_counts": current_retry_counts,
            "last_validation_result": {
                "gate_name": "ontology_action_gate",
                "passed": False,
                "tool_name": getattr(tool_call, "name", display_name),
                "action_key": decision.get("action_key"),
                "reason": message,
            },
        },
    )


async def _handle_tool_call(
    state: AgentState,
    session_id: str,
    tool_call,
    reply_text: str,
    new_history: list[dict[str, Any]],
) -> Command:
    """Handle LLM's tool call decision."""
    tool_name = tool_call.name
    tool_args = tool_call.arguments or {}
    # F8: Extract retry counts once; propagate through all return paths
    current_retry_counts = dict(state.get("agent_retry_counts", {}) or {})

    logger.info(f"[Orchestrator] Tool call: {tool_name}, args: {tool_args}")

    if _stable_tool_surface_enabled():
        constraint = validate_tool_available_in_current_state(tool_name, state)
        if constraint.blocked:
            logger.warning(
                "[Orchestrator] Tool availability gate blocked %s: %s",
                tool_name,
                constraint.reason,
            )
            return _build_tool_gate_block_command(
                state=state,
                tool_call=tool_call,
                reply_text=reply_text,
                new_history=new_history,
                current_retry_counts=current_retry_counts,
                constraint=constraint,
            )

    if tool_name == "ask_user":
        # Layer 4: inline confirmation (simple or guided)
        msg = tool_args.get("message", "请确认")
        options = tool_args.get("options", [])
        last_tool_name = _get_tool_name_from_node(state.get("next_action", "") or "")
        # Hard filter: remove any "stop/cancel" options
        BANNED_KEYWORDS = ["停止", "取消", "放弃", "终止"]
        options = [
            opt
            for opt in options
            if not any(
                kw in (opt.get("label", "") + opt.get("description", ""))
                for kw in BANNED_KEYWORDS
            )
        ]

        # ---- Headless scheduled tasks must never wait for or auto-confirm ask_user ----
        if state.get("headless_mode"):
            logger.info(
                "[Orchestrator] Headless mode blocked ask_user; resolving deterministically."
            )
            a4_observation = state.get("a4_completion_observation") or {}
            if bool(a4_observation.get("artifact_write_validated", False)):
                new_history.append(
                    {
                        "role": "tool",
                        "content": "[headless_mode] ask_user 已被阻止，改为继续生成分析报告。",
                        "tool_call_id": tool_call.id or "call_1",
                    }
                )
                return Command(
                    goto="orchestrator",
                    update={
                        "awaiting_user": False,
                        "orchestrator_reply": reply_text,
                        "orchestrator_history": new_history,
                        "pending_confirmation": None,
                        "agent_retry_counts": current_retry_counts,
                        "next_required_action": build_next_required_action(
                            tool_name="analysis_report_skill",
                            authority="authoritative_resume",
                            reason="Headless scheduled monitoring cannot wait for ask_user; continue directly to A5 after A4 completion.",
                            tool_args={
                                "report_type": (
                                    "panorama"
                                    if str(state.get("analysis_mode") or "")
                                    .strip()
                                    .lower()
                                    == "baseline"
                                    else "scenario"
                                )
                            },
                            source_step="orchestrator_headless_ask_user_guard",
                            metadata={
                                "headless_mode": True,
                                "fallback_from": "ask_user",
                            },
                        ),
                    },
                )
            return Command(
                goto=END,
                update={
                    "execution_status": "error",
                    "error_info": {
                        "step": "orchestrator",
                        "error": "Headless scheduled task attempted ask_user without a deterministic continuation.",
                        "timestamp": datetime.now().isoformat(),
                    },
                    "awaiting_user": False,
                    "pending_confirmation": None,
                    "orchestrator_history": new_history,
                    "agent_retry_counts": current_retry_counts,
                },
            )

        confirm_type = tool_args.get("type", "simple")
        waiting_tips = tool_args.get("waiting_tips", [])
        checklist = tool_args.get("checklist", [])
        request_id = tool_call.id or f"ask_user_{id(tool_call)}"

        if state.get("table_intake_result") and last_tool_name == "table_intake_skill":
            result = state.get("table_intake_result") or {}
            msg, options, step_name = build_table_import_confirmation_payload(result)

        if (
            not options
            and state.get("simulated_questions")
            and last_tool_name == "question_simulation"
        ):
            logger.warning(
                "[Orchestrator] ask_user called without options after A3; "
                "injecting deterministic fetch-mode confirmation."
            )
            return await _force_fetch_mode_confirmation(
                state=state,
                session_id=session_id,
                reply_text=reply_text,
                new_history=new_history,
                request_id=request_id,
                current_retry_counts=current_retry_counts,
            )

        if not reply_text.strip():
            fallback_reply = _build_ask_user_fallback_reply(state, last_tool_name, msg)
            await send_reply_event(
                session_id,
                fallback_reply,
                is_delta=True,
                is_new_round=True,
            )
            await send_reply_event(session_id, "", is_complete=True)
            reply_text = fallback_reply

        # Enhanced inline confirmation with type, tips, and checklist
        payload: dict[str, Any] = {
            "request_id": request_id,
            "message": msg,
            "options": options,
            "type": confirm_type,
        }
        if waiting_tips:
            payload["waiting_tips"] = waiting_tips
        if checklist:
            payload["checklist"] = checklist
        await session_event_publisher.emit_to_session(
            session_id, "inline_confirmation", payload
        )

        # Also emit confirmation_request so SelectionContent's pendingConfirmation
        # guard is satisfied — that component reads pendingConfirmation.requestId
        # which is only set by the setPendingConfirmation handler, triggered by this
        # separate event. Both events are required: inline_confirmation drives the
        # per-message UI layer, confirmation_request drives the store-level guard.
        await session_event_publisher.emit_to_session(
            session_id,
            "confirmation_request",
            {
                "request_id": request_id,
                "type": "step_confirmation",
                "message": msg,
                "options": options,
                "allow_text_input": True,
                "step_id": "orchestrator",
                "step_name": "等待用户确认",
            },
        )

        # Add tool result placeholder to history
        new_history.append(
            {
                "role": "tool",
                "content": "等待用户回复...",
                "tool_call_id": tool_call.id or "call_1",
            }
        )

        return Command(
            goto="wait_for_user",
            update={
                "awaiting_user": True,
                "orchestrator_reply": reply_text,
                "orchestrator_history": new_history,
                "pending_confirmation": {
                    "request_id": request_id,
                    "step_id": "orchestrator",
                    "step_name": "等待用户确认",
                    "message": msg,
                    "options": options,
                },
                "agent_retry_counts": current_retry_counts,
            },
        )

    resolved_skill = await _resolve_skill_tool(
        tool_name,
        tool_args=tool_args,
        state=state,
    )
    effective_tool_name = tool_name
    skill_key = None
    skill_family_key = None
    selected_skill_package_key = None
    selected_skill_package_name = None
    selected_skill_package_description = None
    selected_skill_package_path = None
    selected_skill_package_context = None
    selected_skill_prompt_overlay = None
    selected_skill_profiles = None
    selected_skill_contract = None
    selected_skill_prompt_sections = None
    selected_tool_capability = None
    display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)

    if resolved_skill is not None:
        skill_key = resolved_skill.skill_key
        skill_family_key = resolved_skill.family_skill_key or skill_key
        effective_tool_name = resolved_skill.effective_tool_name
        display_name = resolved_skill.display_name
        selected_skill_package_key = resolved_skill.package_key
        selected_skill_package_name = resolved_skill.package_display_name
        selected_skill_package_description = resolved_skill.package_description
        selected_skill_package_path = resolved_skill.package_path
        selected_skill_package_context = resolved_skill.package_body
        selected_skill_prompt_overlay = resolved_skill.prompt_overlay
        selected_skill_profiles = list(resolved_skill.profiles)
        selected_skill_contract = resolved_skill.skill_contract.to_state_payload()
        selected_skill_prompt_sections = selected_skill_contract.get("prompt_sections")
        node_name = resolved_skill.node_name
        tool_args = dict(resolved_skill.merged_tool_args)
    else:
        node_name = TOOL_TO_NODE.get(tool_name)

    if effective_tool_name == "persona_generation" and not _has_persona_prerequisites(
        state
    ):
        brand_name = _resolve_brand_name_for_dependency_rebuild(state, tool_args)
        if brand_name:
            logger.warning(
                "[Orchestrator] Rerouting persona_generation to brand_analysis: "
                "missing complete A1 context (has_brand_profile=%s, competitors_type=%s)",
                isinstance(state.get("brand_profile"), dict),
                type(state.get("competitors")).__name__,
            )
            effective_tool_name = "brand_analysis"
            tool_name = "brand_analysis"
            node_name = TOOL_TO_NODE["brand_analysis"]
            display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)
            tool_args = {"brand_name": brand_name}
            resolved_skill = None
        else:
            new_history.append(
                {
                    "role": "tool",
                    "content": "生成用户画像前需要先完成品牌竞品分析，但当前缺少品牌名称。请先让用户补充品牌名称或官网。",
                    "tool_call_id": tool_call.id or "call_1",
                    "name": tool_name,
                }
            )
            return Command(
                goto="orchestrator",
                update={
                    "orchestrator_reply": reply_text,
                    "orchestrator_history": new_history,
                    "agent_retry_counts": current_retry_counts,
                },
            )

    ontology_gate_decision = _ontology_action_gate_decision(
        state,
        effective_tool_name,
        tool_args,
    )
    if ontology_gate_decision is not None:
        logger.warning(
            "[Orchestrator] Ontology action gate blocked %s: %s",
            effective_tool_name,
            ontology_gate_decision.get("reason"),
        )
        return await _build_ontology_action_gate_command(
            state=state,
            session_id=session_id,
            tool_call=tool_call,
            reply_text=reply_text,
            new_history=new_history,
            current_retry_counts=current_retry_counts,
            decision=ontology_gate_decision,
            display_name=display_name,
        )
    ontology_action_feedback = _ontology_action_feedback_for_tool(
        state,
        effective_tool_name,
    )
    if ontology_action_feedback is not None:
        tool_args = _merge_ontology_provided_inputs_into_tool_args(
            action_key=str(ontology_action_feedback["action_key"]),
            tool_args=tool_args,
            provided_inputs=ontology_action_feedback.get("provided_inputs") or {},
        )

    capability = get_tool_capability(tool_name) or get_tool_capability(
        effective_tool_name
    )
    capability, capability_error = validate_tool_capability_access(
        caller="orchestrator",
        capability=capability,
    )
    if capability is not None:
        selected_tool_capability = capability.to_state_payload()
    if capability_error:
        logger.warning("[Orchestrator] Capability access blocked: %s", capability_error)
        new_history.append(
            {
                "role": "tool",
                "content": capability_error,
                "tool_call_id": tool_call.id or "call_1",
                "name": tool_name,
            }
        )
        return Command(
            goto="orchestrator",
            update={
                "orchestrator_reply": reply_text,
                "orchestrator_history": new_history,
                "agent_retry_counts": current_retry_counts,
            },
        )

    if node_name:
        suppress_history_query_progress = (
            effective_tool_name in _KNOWLEDGE_TOOL_NAMES
            or effective_tool_name == "post_analysis_skill"
        ) and _is_bounded_history_answer_query_state(state)
        requested_question_mode = tool_args.get("mode", "")
        if effective_tool_name == "question_simulation":
            topic_keywords = _normalize_tool_topic_keywords(
                tool_args.get("topic_keywords")
            )
            if topic_keywords:
                tool_args = {**tool_args, "topic_keywords": topic_keywords}
                if not str(tool_args.get("topic_description") or "").strip():
                    latest_user_message = _get_latest_user_message(state).strip()
                    if latest_user_message:
                        tool_args["topic_description"] = latest_user_message
                requested_question_mode = str(tool_args.get("mode") or "").strip()
                if requested_question_mode in {"", "brand_panorama"}:
                    tool_args["mode"] = "baseline_dynamic"
                    requested_question_mode = "baseline_dynamic"
            latest_user_message = _get_latest_user_message(state)
            if tool_args.get(
                "question_only"
            ) or _is_explicit_question_generation_only_request(latest_user_message):
                early_user_decisions = dict(state.get("user_decisions", {}) or {})
                early_user_decisions["question_generation_only"] = True
                tool_args = {**tool_args, "question_only": True}
                progress_state: AgentState = {
                    **state,
                    "tool_call_args": tool_args,
                    "question_generation_only": True,
                    "user_decisions": early_user_decisions,
                }
            else:
                progress_state = state
        else:
            progress_state = state

        if (
            effective_tool_name == "question_simulation"
            and state.get("user_decisions", {}).get("table_import_confirmed")
            and state.get("user_decisions", {}).get("confirmed_table_kind")
            == "question_list"
            and not requested_question_mode
        ):
            logger.info(
                "[Orchestrator] Overriding question_simulation mode to uploaded_list after confirmed table import"
            )
            tool_args = {**tool_args, "mode": "uploaded_list"}
            requested_question_mode = "uploaded_list"

        # Hard block: when simulated_questions already exist, block re-invocation
        # unless the user just triggered a retry (retry_counts reset to 0).
        if (
            effective_tool_name == "question_simulation"
            and not requested_question_mode
            and state.get("simulated_questions")
        ):
            is_fresh_retry = current_retry_counts.get("question_simulation", 0) == 0
            if not is_fresh_retry:
                logger.warning(
                    "[Orchestrator] BLOCKED: question_simulation called again. "
                    "Questions already exist, redirecting."
                )
                block_msg = (
                    "问题已成功生成，无需重新生成。"
                    "请直接调用 answer_fetch 进行数据抓取，或调用 ask_user 询问用户下一步操作。"
                )
                new_history.append(
                    {
                        "role": "tool",
                        "content": block_msg,
                        "tool_call_id": tool_call.id or "call_1",
                        "name": tool_name,
                    }
                )
                return Command(
                    goto="orchestrator",
                    update={
                        "orchestrator_reply": reply_text,
                        "orchestrator_history": new_history,
                        "agent_retry_counts": current_retry_counts,
                    },
                )

        # Check retry count — block if same tool called >= 2 times
        retry_counts = dict(state.get("agent_retry_counts", {}) or {})
        retry_key = skill_key or effective_tool_name
        if effective_tool_name == "answer_fetch":
            targeted_question_targets = normalize_question_targets(
                tool_args.get("question_targets")
            )
            if tool_args.get("retry_failed_only") or targeted_question_targets:
                retry_key = "answer_fetch_retry_failed_only"
        current_count = retry_counts.get(retry_key, 0)
        if current_count >= 2:
            logger.warning(
                f"[Orchestrator] Tool {retry_key} already called {current_count} times, blocking retry"
            )
            # Inject a tool_result error into history so LLM knows to offer alternatives
            if suppress_history_query_progress:
                error_msg = (
                    f"{display_name}已达到重复检索上限。"
                    "不要再继续调用 knowledge_* 或 post_analysis_skill。"
                    "请直接基于已经拿到的历史结果整理并回答用户；"
                    "如果仍需更精确，请只要求用户补充平台、时间或问题范围。"
                )
            else:
                error_msg = (
                    f"{display_name}已尝试执行 {current_count} 次但未成功。"
                    f"请使用 ask_user 向用户提供建设性替代选项："
                    f"1) 跳过此步骤继续下一步 2) 手动提供所需数据 3) 用不同参数再次尝试。"
                    f"绝对不要提供'停止分析'或'取消分析'选项。"
                )
            new_history.append(
                {
                    "role": "tool",
                    "content": error_msg,
                    "tool_call_id": tool_call.id or "call_1",
                    "name": tool_name,
                }
            )
            # Return to orchestrator to let LLM decide next step
            return Command(
                goto="orchestrator",
                update={
                    "orchestrator_reply": reply_text,
                    "orchestrator_history": new_history,
                    "agent_retry_counts": current_retry_counts,
                },
            )

        # Increment retry count
        retry_counts[retry_key] = current_count + 1

        # Send progress event with steps
        from app.workflow.events import send_progress_event

        tool_to_step_id = {
            "brand_analysis": "A1",
            "persona_generation": "A2",
            "question_simulation": "A3",
            "answer_fetch": "A4",
            "analysis_report_skill": "A5",
            "data_analytics": "A5",
            "confidence_analysis_skill": "A7",
            "site_confidence_assessment_skill": "A7",
        }
        workflow_steps = _build_workflow_steps(progress_state)
        current_step_id = tool_to_step_id.get(effective_tool_name)
        if current_step_id is None and resolved_skill is not None:
            current_step_id = {
                "a5_data_analytics": "A5",
                "confidence_analysis_executor": "A7",
                "a7_confidence_signal": "A7",
                "site_confidence_assessment_executor": "A7",
            }.get(resolved_skill.executor_ref)
        for s in workflow_steps:
            if s["id"] == current_step_id:
                s["status"] = "in_progress"
        completed_count = sum(1 for s in workflow_steps if s["status"] == "completed")
        total_count = len(workflow_steps)
        if not suppress_history_query_progress:
            await send_progress_event(
                session_id,
                step=effective_tool_name,
                step_name=display_name,
                progress=completed_count / total_count,
                message=f"正在执行：{display_name}",
                status="running",
                steps=workflow_steps,
            )

        panorama_intro = _build_panorama_step_intro(
            effective_tool_name,
            tool_args,
            reply_text,
            progress_state,
        )
        if panorama_intro:
            await send_reply_event(
                session_id,
                panorama_intro,
                is_delta=False,
                is_new_round=True,
            )
            await send_reply_event(session_id, "", is_complete=True)

        # Fallback: if LLM produced no reply text, emit a short status line
        # so the user sees something before the long-running agent starts.
        if (
            not suppress_history_query_progress
            and not reply_text.strip()
            and effective_tool_name != "answer_fetch"
        ):
            FALLBACK_TEXTS = {
                "brand_analysis": "正在收集品牌基本信息和竞品格局，请稍候...",
                "persona_generation": "正在根据品牌特征生成用户画像，请稍候...",
                "question_simulation": "正在模拟真实用户可能在 AI 平台中提出的问题，请稍候...",
                "analysis_report_skill": "正在整理场景、风险与优先建议，请稍候…",
                "data_analytics": "正在整理场景、风险与优先建议，请稍候…",
                "confidence_analysis_skill": "正在评估当前引用来源的可信度和结构化质量，请稍候...",
                "site_confidence_assessment_skill": "正在评估官网 AI 友好度，请稍候...",
                "post_analysis_skill": "正在基于已有结果执行后续分析，请稍候...",
            }
            fallback_text = FALLBACK_TEXTS.get(effective_tool_name)
            if fallback_text is None and resolved_skill is not None:
                fallback_text = {
                    "a5_data_analytics": FALLBACK_TEXTS["analysis_report_skill"],
                    "confidence_analysis_executor": FALLBACK_TEXTS[
                        "confidence_analysis_skill"
                    ],
                    "a7_confidence_signal": FALLBACK_TEXTS["confidence_analysis_skill"],
                    "site_confidence_assessment_executor": FALLBACK_TEXTS[
                        "site_confidence_assessment_skill"
                    ],
                    "post_analysis_executor": FALLBACK_TEXTS["post_analysis_skill"],
                }.get(resolved_skill.executor_ref)
            fallback_text = fallback_text or f"正在执行：{display_name}，请稍候..."
            await send_reply_event(
                session_id, fallback_text, is_delta=True, is_new_round=True
            )
            await send_reply_event(session_id, "", is_complete=True)

        # Layer 2: plan event
        if not suppress_history_query_progress:
            await send_plan_event(
                session_id,
                f"正在执行：{display_name}",
            )

        # Layer 3: action log
        if not suppress_history_query_progress:
            await send_action_log_event(
                session_id,
                "agent_call",
                f"调用 {display_name}...",
                step=effective_tool_name,
                is_complete=False,
            )

        # Pass brand_name from tool_args if brand_analysis
        extra_updates: dict[str, Any] = {}
        if ontology_action_feedback is not None:
            extra_updates["latest_user_action_record_id"] = ontology_action_feedback[
                "action_record_id"
            ]
            extra_updates["ontology_action_feedback"] = ontology_action_feedback
            if ontology_action_feedback.get("feedback_type") == "confirm":
                extra_updates["ontology_confirmed_action"] = ontology_action_feedback
        if effective_tool_name == "brand_analysis" and tool_args.get("brand_name"):
            extra_updates["brand_name"] = tool_args["brand_name"]

        # Store user_decisions for a3 mode
        if effective_tool_name == "question_simulation":
            user_decisions = dict(state.get("user_decisions", {}))
            selected_fetch_mode = str(state.get("fetch_mode") or "").strip().lower()
            latest_user_message = _get_latest_user_message(state)
            question_only = bool(
                tool_args.get("question_only")
                or _is_explicit_question_generation_only_request(latest_user_message)
            )
            if question_only:
                tool_args = {**tool_args, "question_only": True}
                user_decisions["question_generation_only"] = True
                user_decisions.pop("fetch_mode_confirmed", None)
                user_decisions.pop("fetch_mode_pending", None)
                user_decisions.pop("fetch_mode", None)
                selected_fetch_mode = ""
                extra_updates["fetch_mode"] = None
                extra_updates["question_generation_only"] = True
            else:
                user_decisions.pop("question_generation_only", None)
                extra_updates["question_generation_only"] = False
            # Reset fetch-mode guard flags only for a fresh A3 run. When the user
            # picked panorama_fast/panorama_full, A3 must preserve that intent so
            # it can continue directly to A4 after generating questions.
            if selected_fetch_mode not in {"fast", "full"}:
                user_decisions.pop("fetch_mode_confirmed", None)
                user_decisions.pop("fetch_mode_pending", None)
            mode = tool_args.get("mode", "")

            if mode == "uploaded_list":
                user_decisions["a3_mode"] = "uploaded_list"
                extra_updates["user_decisions"] = user_decisions
                extra_updates["analysis_mode"] = "persona"
                extra_updates["confirmed_import_action"] = {
                    "target_step": "A3",
                    "table_kind": "question_list",
                    "artifact_type": "questionList",
                    "resume_from": "A3",
                    "source_file_id": (
                        (
                            (state.get("table_intake_result") or {}).get("source_file")
                            or {}
                        ).get("file_id")
                    ),
                    "import_mode": (
                        (
                            (state.get("table_intake_result") or {}).get(
                                "import_intent"
                            )
                            or {}
                        ).get("mode")
                    ),
                }
            elif mode == "baseline_dynamic":
                # Baseline mode: set directly, no user confirmation needed
                user_decisions["a3_mode"] = "baseline_dynamic"
                extra_updates["user_decisions"] = user_decisions
                extra_updates["analysis_mode"] = "baseline"
            elif mode:
                user_decisions["a3_mode"] = (
                    "brand" if mode == "brand_panorama" else "persona"
                )
                extra_updates["analysis_mode"] = "persona"
            else:
                # LLM called question_simulation without prior user confirmation.
                # Silently defaulting here means the user never saw the choice —
                # force an ask_user confirmation instead of picking for them.
                logger.warning(
                    "[Orchestrator] question_simulation called without user_decisions['a3_mode']. "
                    "Redirecting to ask_user to get explicit user selection."
                )
                ask_options = [
                    {
                        "id": "persona_focused",
                        "label": "聚焦画像分析",
                        "description": "从已生成画像中选择重点分析",
                    },
                    {
                        "id": "brand_panorama",
                        "label": "品牌全景分析",
                        "description": "覆盖所有用户群体，不针对特定画像",
                    },
                ]
                defense_request_id = tool_call.id or f"defense_a3_{id(tool_call)}"
                defense_msg = (
                    "品牌全景分析会先梳理品牌定位、核心产品与主要竞品，"
                    "再生成一组可用于后续抓取的行业全景问题。"
                    "您会先得到品牌档案和问题列表，后续还可以继续做答案抓取、对比分析和报告生成。"
                    "请选择分析路径："
                )
                await session_event_publisher.emit_to_session(
                    session_id,
                    "inline_confirmation",
                    {
                        "message": defense_msg,
                        "options": ask_options,
                        "type": "simple",
                    },
                )
                # Mirror the same confirmation_request event that the normal ask_user
                # path now emits, so SelectionContent's pendingConfirmation guard is
                # satisfied identically regardless of which path triggered the prompt.
                await session_event_publisher.emit_to_session(
                    session_id,
                    "confirmation_request",
                    {
                        "request_id": defense_request_id,
                        "type": "step_confirmation",
                        "message": defense_msg,
                        "options": ask_options,
                        "allow_text_input": True,
                        "step_id": "orchestrator",
                        "step_name": "选择分析路径",
                    },
                )
                # Inject tool_result placeholder so MiniMax history stays consistent
                new_history.append(
                    {
                        "role": "tool",
                        "content": "等待用户选择分析路径...",
                        "tool_call_id": tool_call.id or "call_1",
                    }
                )
                return Command(
                    goto="wait_for_user",
                    update={
                        "awaiting_user": True,
                        "orchestrator_reply": reply_text,
                        "orchestrator_history": new_history,
                        "pending_confirmation": {
                            "step_id": "orchestrator",
                            "step_name": "选择分析路径",
                            "message": defense_msg,
                            "options": ask_options,
                        },
                        "agent_retry_counts": current_retry_counts,
                    },
                )
            if tool_args.get("persona_id"):
                selected_ids = list(user_decisions.get("selected_persona_ids") or [])
                selected_names = list(
                    user_decisions.get("selected_persona_names") or []
                )
                persona_id = str(tool_args["persona_id"]).strip()
                if not selected_ids and not selected_names and persona_id:
                    user_decisions["selected_persona_ids"] = [persona_id]
                elif persona_id:
                    logger.info(
                        "[Orchestrator] Ignoring LLM persona_id=%s because user-selected personas already exist",
                        persona_id,
                    )
            extra_updates["user_decisions"] = user_decisions

        # Pass fetch_mode for A4 + custom_questions + ask_user guard
        if effective_tool_name == "answer_fetch":
            latest_user_message = _get_latest_user_message(state)
            recovery_plan = extract_latest_fetch_recovery_plan_from_state(state)
            if (
                is_supplemental_fetch_request(latest_user_message)
                and recovery_plan
                and recovery_plan.get("question_targets")
            ):
                supplemental_fetch_mode = resolve_supplemental_fetch_mode(
                    state,
                    recovery_plan,
                )
                base_fetch_results = extract_base_fetch_results_from_state(state)
                tool_args = {
                    **tool_args,
                    "fetch_mode": supplemental_fetch_mode,
                    "retry_failed_only": True,
                    "question_targets": list(
                        recovery_plan.get("question_targets") or []
                    ),
                    "platforms": list(recovery_plan.get("platforms") or []),
                    "failed_task_id": recovery_plan.get("task_id"),
                    "base_fetch_results": base_fetch_results,
                }
                if prefers_browser_fetch_mode(latest_user_message):
                    tool_args["fetch_mode"] = "full"
            question_targets = normalize_question_targets(
                tool_args.get("question_targets")
            )
            if question_targets:
                # Supplemental fetch must keep the previous full question set in
                # state so A4 can merge the scoped overlay back into the full
                # canonical matrix. The scoped targets travel only in tool_args.
                tool_args = {**tool_args, "question_targets": question_targets}
            custom_qs = tool_args.get("custom_questions")
            if not question_targets and custom_qs and isinstance(custom_qs, list):
                formatted = [
                    {"id": f"custom_{i+1}", "text": q, "category": "用户自定义"}
                    for i, q in enumerate(custom_qs)
                    if isinstance(q, str) and q.strip()
                ]
                if formatted:
                    extra_updates["questions"] = formatted

            user_decisions = dict(state.get("user_decisions", {}))
            resolved_fetch_mode, fetch_mode_policy = resolve_answer_fetch_mode_policy(
                state,
                tool_args,
            )
            if resolved_fetch_mode in {"fast", "full"}:
                tool_args = {**tool_args, "fetch_mode": resolved_fetch_mode}
                extra_updates["fetch_mode"] = resolved_fetch_mode
                user_decisions["fetch_mode_pending"] = False
                user_decisions["fetch_mode_confirmed"] = True
                extra_updates["user_decisions"] = user_decisions
                logger.info(
                    "[Orchestrator] answer_fetch mode resolved by runtime policy: %s (%s)",
                    resolved_fetch_mode,
                    fetch_mode_policy,
                )
            else:
                logger.warning(
                    "[Orchestrator] answer_fetch still requires explicit confirmation (%s)",
                    fetch_mode_policy,
                )
                defense_options = [
                    {
                        "id": "fast",
                        "label": "快速采集（推荐）",
                        "description": "API + 浏览器混合，约 5-10 分钟",
                    },
                    {
                        "id": "full",
                        "label": "完整采集",
                        "description": "全浏览器模拟真实用户，约 10-20 分钟，数据最准",
                    },
                    {
                        "id": "regenerate",
                        "label": "重新生成问题",
                        "description": "对模拟问题不满意，返回重新生成",
                    },
                ]
                defense_request_id = tool_call.id or f"defense_fetch_{id(tool_call)}"
                defense_msg = (
                    "品牌全景分析的问题准备已完成。接下来可以进入答案抓取："
                    "您会得到各平台对同一组问题的回答、引用来源与品牌提及情况，"
                    "后续还可以继续生成分析报告。请选择采集模式："
                )
                await session_event_publisher.emit_to_session(
                    session_id,
                    "inline_confirmation",
                    {
                        "message": defense_msg,
                        "options": defense_options,
                        "type": "simple",
                    },
                )
                await session_event_publisher.emit_to_session(
                    session_id,
                    "confirmation_request",
                    {
                        "request_id": defense_request_id,
                        "type": "step_confirmation",
                        "message": defense_msg,
                        "options": defense_options,
                        "allow_text_input": True,
                        "step_id": "orchestrator",
                        "step_name": "选择采集模式",
                    },
                )
                # Mark pending so next call passes through
                user_decisions["fetch_mode_pending"] = True
                # Inject tool_result placeholder for MiniMax history consistency
                new_history.append(
                    {
                        "role": "tool",
                        "content": "等待用户选择采集模式...",
                        "tool_call_id": tool_call.id or "call_1",
                    }
                )
                return Command(
                    goto="wait_for_user",
                    update={
                        "awaiting_user": True,
                        "orchestrator_reply": reply_text,
                        "orchestrator_history": new_history,
                        "user_decisions": user_decisions,
                        "pending_confirmation": {
                            "step_id": "orchestrator",
                            "step_name": "选择采集模式",
                            "message": defense_msg,
                            "options": defense_options,
                        },
                        "agent_retry_counts": current_retry_counts,
                    },
                )

        # Pass report_type as analysis_mode for A5
        if effective_tool_name in {"data_analytics", "analysis_report_skill"} or (
            resolved_skill is not None
            and resolved_skill.executor_ref == "a5_data_analytics"
        ):
            report_type = _normalize_public_report_kind(
                tool_args.get("report_type", "scenario")
            )
            tool_args["report_type"] = report_type
            extra_updates["analysis_mode"] = _normalize_internal_analysis_mode(
                report_type
            )

        return Command(
            goto=node_name,
            update={
                "next_action": node_name,
                "orchestrator_reply": reply_text,
                "orchestrator_history": new_history,
                "tool_call_args": tool_args,
                "tool_call_id": tool_call.id or "call_1",
                "current_skill": skill_key,
                "current_skill_family": skill_family_key,
                "current_skill_package_key": selected_skill_package_key,
                "current_skill_package_name": selected_skill_package_name,
                "current_skill_package_description": selected_skill_package_description,
                "current_skill_package_path": selected_skill_package_path,
                "current_skill_package_context": selected_skill_package_context,
                "current_skill_prompt_overlay": selected_skill_prompt_overlay,
                "current_skill_profiles": selected_skill_profiles,
                "current_skill_contract": selected_skill_contract,
                "current_skill_prompt_sections": selected_skill_prompt_sections,
                "current_tool_capability": selected_tool_capability,
                "agent_retry_counts": retry_counts,
                "error_info": None,
                **extra_updates,
            },
        )

    # Unknown tool
    logger.warning(f"[Orchestrator] Unknown tool: {tool_name}")
    return Command(
        goto=END,
        update={
            "execution_status": "completed",
            "orchestrator_history": new_history,
            "agent_retry_counts": current_retry_counts,
        },
    )


# =============================================================================
# Wait for User Node
# =============================================================================


async def wait_for_user_node(state: AgentState) -> Command:
    """Node that terminates the workflow to wait for user input.

    When the user responds, the workflow is re-invoked from orchestrator.
    """
    # This node simply ends the current workflow run.
    # The websocket handler will re-invoke the workflow when user responds.
    return Command(
        goto=END,
        update={
            "execution_status": "awaiting_user",
        },
    )
