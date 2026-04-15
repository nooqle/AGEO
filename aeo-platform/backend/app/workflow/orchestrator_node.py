"""LLM-driven orchestrator node for Specta AI workflow.

This module implements the core orchestrator that uses LLM Function Calling
to dynamically decide which Agent to invoke, replacing the hardcoded pipeline.
"""

import json
import logging
from datetime import datetime
from textwrap import dedent
from time import perf_counter
from types import SimpleNamespace
from typing import Any

from langgraph.graph import END
from langgraph.types import Command

from app.workflow.state import AgentState
from app.core.database import AsyncSessionLocal
from app.core.llm import get_llm_model
from app.services.knowledge_workspace_service import KnowledgeWorkspaceService
from app.services.skill_registry_service import (
    build_builtin_skill_tool_definitions,
    SkillScopeContext,
)
from app.services.skill_registry_service import SkillRegistryService
from app.services.skill_invocation_service import (
    SkillInvocationPlan,
    SkillInvocationService,
)
from app.services.tool_capability_matrix import (
    get_tool_capability,
    validate_tool_capability_access,
)
from app.services.session_event_publisher import session_event_publisher
from app.workflow.events import (
    send_reply_event,
    send_plan_event,
    send_action_log_event,
    send_thought_event,
    send_confirmation_request,
)
from app.workflow.orchestrator_context_packets import (
    RecentEvidencePacket,
    build_entity_context_packet,
    build_orchestrator_context_packets,
    build_session_status_packet,
    render_active_skill_packet,
    render_entity_context_packet,
    render_history_availability_packet,
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
from app.workflow.runtime_policy_executor import (
    build_alternative_action_catalog,
    clear_runtime_policy_fields,
    get_user_visible_runtime_label,
    parse_next_required_action,
    resolve_answer_fetch_mode_policy,
    summarize_alternative_actions,
)
from app.workflow.nodes_streaming import async_wrap_sync_gen
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
    "analysis_report_skill": "分析报告",
    "data_analytics": "分析报告",
    "confidence_analysis_skill": "引用置信度评估",
    "confidence_signal_skill": "引用置信度评估",
    "citation_confidence_analysis": "引用置信度评估",
    "post_analysis_skill": "后续分析",
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    "knowledge_lookup": "历史知识检索",
    "knowledge_aggregate": "历史知识聚合",
    "knowledge_compare": "历史知识对比",
    "knowledge_export": "历史知识导出",
    "ask_user": "用户确认",
    "fast": "快速采集",
    "full": "完整采集",
}

_CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES = frozenset(
    {
        "knowledge_lookup",
        "knowledge_aggregate",
        "knowledge_compare",
        "knowledge_export",
    }
)

_SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES = frozenset(
    {
        "post_analysis_skill",
        "compare_snapshots",
    }
)

_KNOWLEDGE_TOOL_NAMES = frozenset(
    {
        "knowledge_lookup",
        "knowledge_aggregate",
        "knowledge_compare",
        "knowledge_export",
    }
)
_RECENT_EVIDENCE_PROMPT_PRIORITY: dict[str, int] = {
    "uploaded_input": 0,
    "current_fetch": 1,
    "current_artifact": 2,
    "knowledge_lookup": 3,
    "knowledge_compare": 4,
    "knowledge_aggregate": 5,
    "knowledge_export": 6,
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
                    "description": "生成模式：brand_panorama=品牌全景, persona_focused=画像聚焦, baseline_dynamic=行业基线全景, uploaded_list=导入用户上传的问题列表",
                },
                "persona_id": {
                    "type": "string",
                    "description": "聚焦的画像ID（persona_focused模式时需要）",
                },
                "identity": {
                    "type": "string",
                    "description": "可选身份视角覆盖。仅当用户明确要求“以某个身份/视角生成问题”时传入，例如“采购经理”“品牌经理”。未明确要求时不要传。",
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
                    "enum": ["baseline", "persona"],
                    "description": "报告类型：baseline=行业基线报告, persona=场景分析报告（默认）",
                },
            },
        },
    },
    {
        "name": "knowledge_lookup",
        "description": (
            "查询同一品牌跨历史分析中已经沉淀的事实材料。"
            "适用于品牌信息、竞品信息、历史抓取答案、历史引用来源、"
            "以及基于已有材料的问答、分析和导出任务。"
            "这是低成本优先路径：当用户问题明显围绕历史材料展开时，应优先尝试此工具。"
            "如果返回 miss 或证据不足，再考虑 brand_analysis、answer_fetch 或 ask_user。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要查询的历史事实、分析主题或导出主题",
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
            "按时间、平台、竞品、问题或域名聚合历史事实材料。"
            "适用于导出、汇总、盘点和基于历史材料的结构化分析。"
            "当用户要求导出某一时间范围内的信息、统计某类材料、或按某个维度做历史汇总时优先使用。"
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
            "对同一品牌最近两次历史材料窗口做对比。"
            "适用于跨历史分析、变化解释、平台差异和对比汇总。"
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
            "把历史知识材料整理成可交付的数据表 artifact。"
            "适用于用户明确要求导出、下载、生成文件、拉清单或交付历史材料。"
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
        "name": "create_monitoring_schedule",
        "description": (
            "为指定品牌创建定时自动分析计划。"
            "例如：'每周监控小米'、'帮我设置华为的月度监测'。"
            "前置条件：当前会话中必须有 entity_id（品牌至少已分析过一次）。"
            "如果没有 entity_id，不要调用此工具，提示用户先运行完整分析。"
            "创建成功后会自动按照设定频率运行分析流程。"
            "【重要】不要直接调用此工具。你必须先用自然语言向用户详细说明定期监测的含义和可配置参数，然后调用 ask_user 让用户确认。"
            "说明内容必须包括：1) 定期监测的作用——系统会按设定频率自动重新运行品牌分析流程，生成最新报告并与历史数据对比；"
            "2) 可配置参数及默认值——监测频率（每天/每周/双周/每月，推荐每周）、执行时间（默认上午11:00）、"
            "告警阈值（当品牌提及率、官网引用率或高风险场景数量出现明显变化时通知用户，默认 10）；"
            "3) 推荐配置——给出针对该品牌的推荐配置及理由。"
            "示例消息：'定期监测可以帮助您持续跟踪品牌在 AI 平台中的表现变化。我建议为「小米」设置以下监测计划：\n\n"
            "- **监测频率**：每周（适合快速变化的科技行业）\n"
            "- **执行时间**：每周一上午 11:00\n"
            "- **告警阈值**：当品牌提及率、官网引用率或高风险场景变化超过设定阈值时通知您\n\n"
            "如果这个方案可以，请点击确认；或者告诉我您想调整哪些参数。'"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "weekly", "biweekly", "monthly"],
                    "description": "监测频率，默认 weekly",
                },
                "preferred_hour": {
                    "type": "integer",
                    "description": "每天的执行时间（0-23，用户所在时区），默认 11",
                },
                "alert_threshold": {
                    "type": "number",
                    "description": "监测变化告警阈值（用于提及率、官网引用率、高风险场景等变化提醒），默认 10.0",
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


def _compact_text(value: Any, limit: int = 140) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_knowledge_lookup_match(match: dict[str, Any]) -> str:
    parts = [f"类型={match.get('source_type', 'unknown')}"]
    if match.get("platform"):
        parts.append(f"平台={match['platform']}")
    if match.get("competitor_name"):
        parts.append(f"竞品={match['competitor_name']}")
    if match.get("domain"):
        parts.append(f"域名={match['domain']}")
    if match.get("question_text"):
        parts.append(f"问题={_compact_text(match['question_text'], 48)}")
    snippet = _compact_text(match.get("snippet"), 120)
    title = _compact_text(match.get("title"), 48)
    return f"- {title}（{'，'.join(parts)}）: {snippet}"


def _format_knowledge_group(group: dict[str, Any]) -> str:
    sample_titles = list(group.get("sample_titles") or [])
    if not sample_titles:
        sample_titles = [
            item.get("title", "")
            for item in (group.get("sample_records") or [])[:2]
            if item.get("title")
        ]
    samples = "；".join(_compact_text(item, 32) for item in sample_titles[:2])
    sample_suffix = f"；样例={samples}" if samples else ""
    return (
        f"- {group.get('group_key', 'unknown')}：{group.get('count', 0)} 条"
        f"；来源={','.join(group.get('source_types') or [])}{sample_suffix}"
    )


def _format_knowledge_comparison(item: dict[str, Any]) -> str:
    examples = [
        example.get("title", "")
        for example in (item.get("latest_examples") or [])[:1]
        if example.get("title")
    ]
    example_suffix = f"；最新样例={_compact_text(examples[0], 28)}" if examples else ""
    return (
        f"- {item.get('group_key', 'unknown')}：最新 {item.get('latest_count', 0)}，"
        f"上次 {item.get('previous_count', 0)}，变化 {item.get('delta', 0):+d}"
        f"{example_suffix}"
    )


def _build_recent_knowledge_context(state: AgentState) -> str:
    """Expose the latest knowledge tool output back to the orchestrator.

    Only surface this when the orchestrator is resuming immediately after a tool
    run. On a brand-new user turn we avoid carrying stale evidence into the
    system prompt and instead rely on history + fresh planning.
    """
    history = state.get("orchestrator_history") or []
    if history and history[-1].get("role") == "user":
        return ""

    lookup_result = state.get("knowledge_lookup_result") or {}
    if lookup_result.get("status") == "hit":
        matches = lookup_result.get("matches") or []
        lines = [_format_knowledge_lookup_match(match) for match in matches[:3]]
        if lines:
            return "\n最近一次历史检索结果:\n" + "\n".join(lines)

    aggregate_result = state.get("knowledge_aggregate_result") or {}
    if aggregate_result.get("status") == "hit":
        groups = aggregate_result.get("groups") or []
        lines = [_format_knowledge_group(group) for group in groups[:4]]
        if lines:
            return (
                "\n最近一次历史聚合结果"
                f"（group_by={aggregate_result.get('group_by', 'source_type')}）:\n"
                + "\n".join(lines)
            )

    export_result = state.get("knowledge_export_result") or {}
    if export_result.get("status") == "hit":
        return (
            "\n最近一次历史导出结果:\n"
            f"- 标题={export_result.get('title', '历史知识导出')}；"
            f"记录数={export_result.get('item_count', 0)}；"
            f"artifact={export_result.get('artifact_id', 'unknown')}"
        )

    compare_result = state.get("knowledge_compare_result") or {}
    if compare_result.get("status") == "hit":
        comparisons = compare_result.get("comparisons") or []
        lines = [_format_knowledge_comparison(item) for item in comparisons[:4]]
        if lines:
            return (
                "\n最近一次历史对比结果"
                f"（{compare_result.get('previous_label', 'previous')} -> "
                f"{compare_result.get('latest_label', 'latest')}）:\n"
                + "\n".join(lines)
            )

    return ""


def _get_latest_user_message(state: AgentState) -> str:
    history = state.get("orchestrator_history") or []
    for item in reversed(history):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def _infer_brand_seed_candidate(state: AgentState) -> str | None:
    """Treat a bare brand-name turn as an implicit analysis seed, not an ambiguity."""

    if state.get("awaiting_user") or state.get("pending_confirmation"):
        return None
    if state.get("pending_table_intake"):
        return None
    if state.get("brand_profile") or state.get("brand_name") or state.get("entity_id"):
        return None
    if state.get("fetch_results") or state.get("report") or state.get("metrics"):
        return None

    latest_user_message = _get_latest_user_message(state).strip()
    if not latest_user_message or "\n" in latest_user_message:
        return None

    candidate = latest_user_message.strip(
        " \t\r\n,，。.!！？?：:；;、\"'“”‘’()（）[]【】<>《》"
    )
    if not candidate or len(candidate) > 24:
        return None

    lowered = candidate.lower()
    intent_keywords = (
        "分析",
        "报告",
        "导出",
        "下载",
        "对比",
        "比较",
        "变化",
        "趋势",
        "抓取",
        "重抓",
        "重跑",
        "引用",
        "官网",
        "画像",
        "问题",
        "回答",
        "结果",
        "历史",
        "怎么",
        "如何",
        "为什么",
        "有没有",
        "是否",
        "查询",
        "监测",
        "fast",
        "full",
        "browser",
        "api",
    )
    if any(keyword in lowered for keyword in intent_keywords):
        return None

    return candidate


def _is_current_report_follow_up(state: AgentState) -> bool:
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return False
    if not (state.get("fetch_results") or state.get("report") or state.get("metrics")):
        return False

    current_markers = [
        "这份报告",
        "当前报告",
        "本次报告",
        "这个报告",
        "基于这份报告",
        "基于当前报告",
        "当前结果",
        "本次抓取",
        "这次抓取",
        "当前分析",
    ]
    history_markers = [
        "历史",
        "上次",
        "最近两次",
        "之前",
        "月份",
        "导出",
        "下载",
        "清单",
        "表格",
        "过去",
        "过往",
    ]
    return (
        any(marker in latest_user_message for marker in current_markers)
        and not any(marker in latest_user_message for marker in history_markers)
    )


def _has_terminal_knowledge_result(state: AgentState) -> bool:
    for key in (
        "knowledge_lookup_result",
        "knowledge_aggregate_result",
        "knowledge_compare_result",
        "knowledge_export_result",
    ):
        result = state.get(key) or {}
        if isinstance(result, dict) and result.get("status") == "miss":
            return True
    return False


def _build_knowledge_planning_hint(state: AgentState) -> str:
    """Provide a lightweight planning hint without hard-forcing tool choice."""
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return ""
    if _is_current_report_follow_up(state) or _has_terminal_knowledge_result(state):
        return ""

    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    history_info = manifest.get("history") or {}
    has_materials = any(bool(value) for value in available_sources.values())
    if not has_materials:
        return ""

    text = latest_user_message.lower()
    compare_keywords = [
        "对比",
        "比较",
        "变化",
        "趋势",
        "最近两次",
        "上次",
        "这次",
    ]
    export_keywords = [
        "导出",
        "下载",
        "文件",
        "表格",
        "清单",
        "csv",
        "excel",
        "pdf",
        "md",
    ]
    aggregate_keywords = [
        "汇总",
        "统计",
        "盘点",
        "列表",
        "所有",
        "全部",
        "按平台",
        "按月份",
        "3月",
        "4月",
        "5月",
    ]
    lookup_keywords = [
        "品牌",
        "竞品",
        "答案",
        "引用",
        "官网",
        "来源",
        "历史",
        "差距",
        "为什么",
    ]

    if int(history_info.get("analysis_window_count") or 0) >= 2 and any(
        keyword in text for keyword in compare_keywords
    ):
        return (
            "\n当前用户请求明显属于“历史对比/变化解释”任务。"
            "优先考虑 knowledge_compare；若结果不足，再决定是否补抓。"
        )

    if any(keyword in text for keyword in export_keywords):
        return (
            "\n当前用户请求明显属于“历史材料导出/交付”任务。"
            "优先考虑 knowledge_export；必要时再用 knowledge_lookup 或 knowledge_aggregate 补证据。"
        )

    if any(keyword in text for keyword in aggregate_keywords):
        return (
            "\n当前用户请求明显属于“历史汇总/导出/盘点”任务。"
            "优先考虑 knowledge_aggregate；必要时再结合 knowledge_lookup 补证据。"
        )

    if any(keyword in text for keyword in lookup_keywords):
        return (
            "\n当前用户请求明显围绕“历史事实/答案/引用”展开。"
            "优先考虑 knowledge_lookup；如果命中不足，再决定是否调用 brand_analysis 或 answer_fetch。"
        )

    return ""


def _normalize_sentiment_followup_value(text: str) -> str | None:
    raw = str(text or "").lower()
    if any(keyword in raw for keyword in ["负向", "负面", "消极", "negative"]):
        return "negative"
    if any(keyword in raw for keyword in ["正向", "正面", "积极", "positive"]):
        return "positive"
    if any(keyword in raw for keyword in ["中性", "neutral"]):
        return "neutral"
    return None


def _infer_current_session_followup_tool(
    state: AgentState,
) -> tuple[str, dict[str, Any]] | None:
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None

    if not state.get("fetch_results"):
        return None

    lowered = latest_user_message.lower()
    history_keywords = [
        "历史",
        "上次",
        "最近两次",
        "变化",
        "趋势",
        "导出",
        "汇总",
        "按月",
        "3月",
        "4月",
        "5月",
    ]
    if any(keyword in latest_user_message for keyword in history_keywords):
        return None

    sentiment_value = _normalize_sentiment_followup_value(latest_user_message)
    if sentiment_value is not None:
        return (
            "drill_down_analysis",
            {
                "focus_dimension": "sentiment",
                "focus_value": sentiment_value,
            },
        )

    platform_aliases = {
        "deepseek": ["deepseek", "深度求索"],
        "kimi": ["kimi"],
        "doubao": ["豆包"],
        "hunyuan": ["元宝", "hunyuan", "腾讯元宝"],
    }
    for platform_key, aliases in platform_aliases.items():
        if any(alias.lower() in lowered for alias in aliases):
            return (
                "drill_down_analysis",
                {
                    "focus_dimension": "platform",
                    "focus_value": platform_key,
                },
            )

    return None


def _get_contextual_hidden_tool_names(state: AgentState | None) -> set[str]:
    if not state:
        return set()

    hidden: set[str] = set()
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    if preferred_followup_tool is not None:
        hidden.update(_CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES)
        if preferred_followup_tool[0] == "drill_down_analysis":
            hidden.update(_SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES)
    return hidden


def _infer_knowledge_fallback_tool(
    state: AgentState,
) -> tuple[str, dict[str, Any]] | None:
    """Fallback only when LLM produced no tool call for a clear history task."""
    latest_user_message = _get_latest_user_message(state)
    if not latest_user_message:
        return None
    if _is_current_report_follow_up(state):
        return None
    if _has_terminal_knowledge_result(state):
        return None

    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    history_info = manifest.get("history") or {}
    has_materials = any(bool(value) for value in available_sources.values())
    if not has_materials:
        return None

    text = latest_user_message.lower()
    compare_keywords = ["对比", "比较", "变化", "趋势", "最近两次", "上次", "这次"]
    export_keywords = [
        "导出",
        "下载",
        "文件",
        "表格",
        "清单",
        "csv",
        "excel",
        "pdf",
        "md",
    ]
    aggregate_keywords = [
        "汇总",
        "统计",
        "盘点",
        "列表",
        "所有",
        "全部",
        "按平台",
        "按月份",
        "3月",
        "4月",
        "5月",
    ]
    lookup_keywords = [
        "品牌",
        "竞品",
        "答案",
        "引用",
        "官网",
        "来源",
        "历史",
        "差距",
        "为什么",
    ]

    if int(history_info.get("analysis_window_count") or 0) >= 2 and any(
        keyword in text for keyword in compare_keywords
    ):
        compare_by = "platform"
        if "竞品" in latest_user_message:
            compare_by = "competitor"
        elif "引用" in latest_user_message or "域名" in latest_user_message:
            compare_by = "domain"
        elif "问题" in latest_user_message:
            compare_by = "question"
        return ("knowledge_compare", {"compare_by": compare_by, "limit": 8})

    if any(keyword in text for keyword in export_keywords):
        return (
            "knowledge_export",
            {
                "query": latest_user_message,
                "limit": 200,
            },
        )

    if any(keyword in text for keyword in aggregate_keywords):
        group_by = "source_type"
        if "平台" in latest_user_message:
            group_by = "platform"
        elif "竞品" in latest_user_message:
            group_by = "competitor"
        elif (
            "引用" in latest_user_message
            or "域名" in latest_user_message
            or "官网" in latest_user_message
            or "来源" in latest_user_message
        ):
            group_by = "domain"
        elif "问题" in latest_user_message:
            group_by = "question"
        elif any(
            month in latest_user_message
            for month in [
                "1月",
                "2月",
                "3月",
                "4月",
                "5月",
                "6月",
                "7月",
                "8月",
                "9月",
                "10月",
                "11月",
                "12月",
            ]
        ):
            group_by = "month"
        return (
            "knowledge_aggregate",
            {
                "query": latest_user_message,
                "group_by": group_by,
                "limit": 12,
            },
        )

    if any(keyword in text for keyword in lookup_keywords):
        source_types = None
        answer_detail_keywords = [
            "答案",
            "回答",
            "怎么回答",
            "提及",
            "负向",
            "负面",
            "正向",
            "正面",
            "中性",
            "情感",
            "证据",
        ]
        if any(keyword in latest_user_message for keyword in answer_detail_keywords):
            source_types = ["fetch_answer", "fetch_citation"]
        elif (
            "引用" in latest_user_message
            or "官网" in latest_user_message
            or "来源" in latest_user_message
        ):
            source_types = ["fetch_citation", "fetch_answer"]
        elif "竞品" in latest_user_message:
            source_types = ["competitor_profile", "fetch_answer"]
        elif any(
            keyword in latest_user_message
            for keyword in ["品牌档案", "品牌信息", "品牌定位", "品牌介绍", "核心产品", "目标受众"]
        ):
            source_types = ["brand_profile", "competitor_profile"]
        elif "答案" in latest_user_message:
            source_types = ["fetch_answer"]
        args: dict[str, Any] = {
            "query": latest_user_message,
            "limit": 8,
        }
        if source_types:
            args["source_types"] = source_types
        return ("knowledge_lookup", args)

    return None


def _should_stream_thoughts(state: AgentState) -> bool:
    """Mute low-value reasoning streams for obvious history-export tasks."""

    fallback = _infer_knowledge_fallback_tool(state)
    if fallback and fallback[0] == "knowledge_export":
        return False
    return True


def _is_english_dominant_text(text: str) -> bool:
    stripped = str(text or "").strip()
    if not stripped:
        return False
    ascii_letters = sum(1 for ch in stripped if ch.isascii() and ch.isalpha())
    cjk_chars = sum(1 for ch in stripped if "\u4e00" <= ch <= "\u9fff")
    if ascii_letters >= 8 and cjk_chars == 0:
        return True
    return ascii_letters >= 12 and ascii_letters > max(1, cjk_chars * 2)


def _localize_visible_terms(text: str) -> str:
    localized = str(text or "")
    for source, target in _VISIBLE_TOOL_NAME_LABELS.items():
        localized = localized.replace(source, target)
    return localized


def _normalize_thought_text_for_stream(
    text: str,
    *,
    placeholder_sent: bool,
) -> tuple[str | None, bool]:
    stripped = _localize_visible_terms(text).strip()
    if not stripped:
        return None, placeholder_sent
    if _is_english_dominant_text(stripped):
        return None, placeholder_sent
    return stripped, placeholder_sent


def _build_context_summary(state: AgentState) -> str:
    """Build a summary of what data exists in the current session.

    Includes tool availability hints (Review C4) to help LLM
    distinguish between 9 tools and avoid misrouting.
    """
    parts = []
    available_tools = []
    unavailable_tools = []
    manifest = state.get("knowledge_manifest") or {}
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    preferred_followup_tool = _infer_current_session_followup_tool(state)

    if state.get("brand_profile"):
        brand = state["brand_profile"]
        parts.append(f"- 已分析品牌: {brand.get('brand_name', '未知')}")
        parts.append(f"- 行业: {brand.get('industry', '未知')}")

    if state.get("competitors"):
        names = [c.get("name", "") for c in state["competitors"][:5]]
        parts.append(f"- 已识别竞品: {', '.join(names)}")

    if state.get("fetch_results"):
        parts.append(f"- 抓取结果: {len(state['fetch_results'])} 组问题")
        if "post_analysis_skill" not in hidden_tool_names:
            available_tools.append(
                "post_analysis_skill (可对已有结果做深挖、对比、解释或风险提取)"
            )
        if preferred_followup_tool and preferred_followup_tool[0] == "drill_down_analysis":
            parts.append("- 当前问题命中本次结果深挖场景，优先使用 drill_down_analysis")
            if "post_analysis_skill" in hidden_tool_names:
                parts.append(
                    "- 当前回合已收敛到 drill_down_analysis，泛化后续分析入口已从工具面隐藏"
                )
    else:
        unavailable_tools.append("post_analysis_skill (尚无先前分析结果)")

    if state.get("metrics"):
        m = state["metrics"]
        parts.append(f"- 品牌提及率: {m.get('mention_rate', 'N/A')}")
        if m.get("mention_sentiment_analysis") or (state.get("report") or {}).get(
            "mention_sentiment_analysis"
        ):
            parts.append("- 当前报告已包含提及情感证据，可直接追问正向/负向提及细节")

    if state.get("baseline_metrics"):
        bm = state["baseline_metrics"]
        parts.append(f"- 基线提及率: {bm.get('mention_rate', 'N/A')}")
        parts.append("- 基线报告: 已完成")

    if state.get("entity_id"):
        parts.append(f"- 品牌实体ID: {state['entity_id']} (有历史快照)")
        available_tools.append("create_monitoring_schedule (可创建定时监测计划)")
    else:
        unavailable_tools.append("create_monitoring_schedule (尚无品牌实体)")

    if manifest:
        available_sources = manifest.get("available_sources", {})
        history_info = manifest.get("history", {})
        available_labels = [
            label
            for key, label in [
                ("brand_profile", "品牌档案"),
                ("competitor_profile", "竞品档案"),
                ("fetch_answer", "历史答案"),
                ("fetch_citation", "历史引用"),
            ]
            if available_sources.get(key)
        ]
        if available_labels:
            if "knowledge_lookup" not in hidden_tool_names:
                available_tools.append("knowledge_lookup (可查询跨历史事实材料)")
            if "knowledge_aggregate" not in hidden_tool_names:
                available_tools.append("knowledge_aggregate (可汇总历史材料)")
            if "knowledge_export" not in hidden_tool_names:
                available_tools.append("knowledge_export (可导出历史材料数据表)")
            if "knowledge_compare" not in hidden_tool_names:
                if int(history_info.get("analysis_window_count") or 0) >= 2:
                    available_tools.append("knowledge_compare (可对比最近历史变化)")
                else:
                    unavailable_tools.append("knowledge_compare (历史轮次不足，暂不可对比)")
        else:
            if "knowledge_lookup" not in hidden_tool_names:
                unavailable_tools.append("knowledge_lookup (当前尚无历史材料可复用)")
            if "knowledge_aggregate" not in hidden_tool_names:
                unavailable_tools.append("knowledge_aggregate (当前尚无历史材料可汇总)")
            if "knowledge_export" not in hidden_tool_names:
                unavailable_tools.append("knowledge_export (当前尚无历史材料可导出)")
            if "knowledge_compare" not in hidden_tool_names:
                unavailable_tools.append("knowledge_compare (当前尚无历史材料可对比)")

    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        parts.append("- 当前问题属于本次结果追问，历史知识工具已从可用工具面隐藏")

    if not parts:
        summary = "\n当前会话数据: 尚无分析数据。"
    else:
        summary = "\n当前会话数据:\n" + "\n".join(parts)

    # Tool availability hints (Review C4)
    if available_tools:
        summary += "\n\n可用的追问工具:\n" + "\n".join(
            f"  - {t}" for t in available_tools
        )
    if unavailable_tools:
        summary += "\n\n不可用的工具（缺少前置数据）:\n" + "\n".join(
            f"  - {t}" for t in unavailable_tools
        )

    return summary


# =============================================================================
# Post-Agent Action Directives (共享常量)
# 这些文本同时被 system prompt 和 _build_agent_result_summary 引用
# 修改时请确保两处语义一致
# =============================================================================

DIRECTIVE_A1_HAS_BASELINE = (
    "【强制操作】你必须先用 3-5 句话向用户汇报品牌分析结果（包含至少1个具体洞察），"
    "然后在消息末尾用自然语言列出选项：\n"
    "1. 做一次引用内容置信度评估（可选）— 检查当前引用来源的可信度、结构化质量与可核查性\n"
    "2. 生成用户画像，进入场景细化分析（推荐）— 基于不同用户群体深入分析品牌在各场景下的AI曝光表现\n"
    "3. 重新运行基线分析 — 使用最新数据重新评估品牌在各AI平台上的基线表现\n"
    "4. 直接提问 — 针对已有数据自由提问\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
    "不要跳过 ask_user，不要自行决定下一步。"
)

DIRECTIVE_A1_NO_BASELINE = (
    "【强制操作】当前仅完成了品牌分析，还没有建立行业基线。\\n"
    "你必须先向用户说明：“基线分析会用行业通用问题建立品牌在各个AI平台的全景基线，后续画像和场景分析都会基于它进行对比。”\\n"
    "1) 基线分析会采集行业通用问题的AI回答，建立品牌全局基线\\n"
    "2) 基线分析完成后，再生成用户画像可以做场景对比\\n"
    "3) 完整采集模式下需要约10-20分钟\\n"
    "请向用户给出两个选择：\\n"
    "1. 先运行基线分析\\n"
    "2. 暂不\\n"
    "然后调用 ask_user(message='是否先运行基线分析？')，不要传 options 参数。不要跳过这一确认步骤。"
)

DIRECTIVE_A2_ASK_PATH = (
    "【强制操作】画像已生成并展示在右侧画布（Canvas）的管道图中。"
    "你必须在消息中引导用户：\n"
    "'用户画像已生成，请在右侧画布的管道图中勾选您希望重点分析的画像（可多选），然后点击确认选择按钮。'\n"
    "然后在消息末尾列出选项：\n"
    "1. 我已在画布中选好画像 — 请先在右侧画布中勾选画像，再回复此选项\n"
    "2. 跳过，品牌全景分析 — 覆盖所有用户群体，不针对特定画像\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
    "不要调用 question_simulation，必须等用户操作后再继续。"
)

DIRECTIVE_A3_NEXT_FETCH = (
    "【强制操作】用 2-3 句话友好地向用户说明问题已生成（可提及问题数量、覆盖的主题方向），"
    "在消息中说明问题列表已在右侧画布中展示。然后在消息末尾用自然语言列出以下选项，每个选项必须包含说明文字：\n"
    "1. 快速采集（推荐）— 通过 API 调用豆包、元宝和 Kimi，并通过浏览器采集 DeepSeek，约 3-5 分钟。"
    "能快速建立品牌在 AI 平台中的初步观感，但 API 返回的内容与真实用户在网页端看到的可能存在差异\n"
    "2. 完整采集 — 4 个平台全部通过浏览器模拟真实用户访问，约 10-20 分钟。"
    "完全还原用户在网页端的真实体验，采集到的回答、引用来源和品牌提及最为准确，是深度 AEO 分析的最佳选择\n"
    "3. 重新生成问题 — 如果对当前问题不满意\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
    "不要逐条列出问题内容（UI 已经展示了）。"
    "用户选择 1 后调用 answer_fetch(fetch_mode='fast')，选择 2 后调用 answer_fetch(fetch_mode='full')。"
)

DIRECTIVE_A5_BASELINE_NEXT = (
    "【强制操作】你必须先用 3-5 句话向用户汇报基线报告结果，至少包含 1 个具体指标或风险发现。"
    "然后在消息末尾用自然语言列出以下编号选项，每个选项都要说明作用：\n"
    "1. 做一次引用内容置信度评估（可选）— 检查当前报告中引用来源的可信度、结构化质量和可核查性\n"
    "2. 生成用户画像，进入场景细化分析（推荐）— 在基线之上继续看不同人群场景中的品牌表现\n"
    "3. 重新运行基线分析 — 用新的问题或新的采集结果重建当前基线\n"
    "4. 直接提问 — 基于当前报告继续追问任何具体问题\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
)

DIRECTIVE_A5_PERSONA_NEXT = (
    "【强制操作】你必须先用 3-5 句话向用户汇报场景分析报告结果，至少包含 1 个具体指标或风险发现。"
    "然后在消息末尾用自然语言列出以下编号选项，每个选项都要说明作用：\n"
    "1. 做一次引用内容置信度评估（可选）— 检查当前报告中引用来源的可信度、结构化质量和可核查性\n"
    "2. 深入分析当前报告 — 继续围绕某个平台、问题场景或竞品展开分析\n"
    "3. 直接提问 — 针对当前报告继续追问任何具体问题\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
)


def _build_orchestrator_data_status(state: AgentState) -> str:
    return render_session_status_packet(build_session_status_packet(state))


def _build_orchestrator_entity_context(state: AgentState) -> str:
    return render_entity_context_packet(build_entity_context_packet(state))


def _build_public_skill_index(state: AgentState) -> str:
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    lines: list[str] = []
    note_lines: list[str] = []
    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        note_lines.append("- 当前问题属于本次结果追问，历史知识工具已从本轮公共技能面隐藏。")
    if preferred_followup_tool and preferred_followup_tool[0] == "drill_down_analysis":
        note_lines.append("- 当前回合已收敛到 drill_down_analysis，不再暴露泛化的后续分析入口。")
    if note_lines:
        note_lines.append("- 以下仅列出当前回合真实可调用的公共技能。")
    for definition in build_builtin_skill_tool_definitions():
        name = str(definition.get("name") or "")
        if name in hidden_tool_names:
            continue
        description = _compact_text(definition.get("description"), 56)
        availability = "当前可用"
        if name == "post_analysis_skill" and not state.get("fetch_results"):
            availability = "需已有抓取结果或报告"
        elif name == "analysis_report_skill" and not state.get("fetch_results"):
            availability = "需先完成答案抓取"
        elif name == "confidence_analysis_skill" and not state.get("fetch_results"):
            availability = "需先有可评估的抓取结果"
        lines.append(f"- {name}: {description}；{availability}")
        if len(lines) >= 6:
            break
    return "\n".join([*note_lines, *lines])


def _build_contextual_tool_surface_note(state: AgentState) -> str | None:
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    preferred_followup_tool = _infer_current_session_followup_tool(state)
    lines: list[str] = []

    if hidden_tool_names & _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES:
        lines.append("- 当前问题属于本次结果追问，历史知识工具已从当前回合工具面隐藏。")

    if preferred_followup_tool and preferred_followup_tool[0] == "drill_down_analysis":
        focus_args = preferred_followup_tool[1] or {}
        focus_dimension = str(focus_args.get("focus_dimension") or "").strip()
        focus_value = str(focus_args.get("focus_value") or "").strip()
        if focus_dimension == "platform" and focus_value:
            lines.append(
                f"- 当前回合应直接使用 drill_down_analysis，聚焦平台维度：{focus_value}。"
            )
        elif focus_dimension == "sentiment" and focus_value:
            lines.append(
                f"- 当前回合应直接使用 drill_down_analysis，聚焦情感维度：{focus_value}。"
            )
        else:
            lines.append("- 当前回合应直接使用 drill_down_analysis 处理本次结果追问。")
        lines.append("- 不要再先走 post_analysis_skill 或 knowledge_*。")

    if not lines:
        return None
    return "\n".join(lines)


def _render_recent_evidence_for_prompt(packet: RecentEvidencePacket) -> str:
    if not packet.items:
        return ""

    ranked_items = sorted(
        packet.items,
        key=lambda item: (
            _RECENT_EVIDENCE_PROMPT_PRIORITY.get(item.source, 99),
            -int(item.relevance_score),
            item.title,
        ),
    )
    top_items = tuple(ranked_items[:3])
    if not top_items:
        return ""
    return render_recent_evidence_packet(RecentEvidencePacket(items=top_items))


def _should_render_history_availability(
    state: AgentState,
    hidden_tool_names: set[str],
) -> bool:
    if _KNOWLEDGE_TOOL_NAMES.issubset(hidden_tool_names):
        return False
    manifest = state.get("knowledge_manifest") or {}
    available_sources = manifest.get("available_sources") or {}
    return any(bool(value) for value in available_sources.values())


def _should_render_instruction_defense(
    state: AgentState,
    recent_evidence_packet: RecentEvidencePacket,
) -> bool:
    defense_context = build_instruction_defense_context(state, recent_evidence_packet)
    if defense_context.prompt_disclosure_request or defense_context.suspicious_evidence_count:
        return True
    latest_user_message = _get_latest_user_message(state)
    return detect_instruction_injection(latest_user_message)


def build_orchestrator_prompt_assembly(state: AgentState) -> PromptAssembly:
    """Build the orchestrator prompt as structured sections."""

    context_packets = build_orchestrator_context_packets(state)
    hidden_tool_names = _get_contextual_hidden_tool_names(state)
    status_text = render_session_status_packet(context_packets.session_status)
    entity_context = render_entity_context_packet(context_packets.entity_context)
    history_availability = (
        render_history_availability_packet(context_packets.history_availability)
        if _should_render_history_availability(state, hidden_tool_names)
        else ""
    )
    active_skill_context = render_active_skill_packet(context_packets.active_skill)
    pending_decision = render_pending_decision_packet(
        context_packets.pending_decision
    )
    recent_evidence = _render_recent_evidence_for_prompt(context_packets.recent_evidence)
    context_summary = _compact_text(_build_context_summary(state), 500)
    knowledge_hint = _build_knowledge_planning_hint(state)
    contextual_tool_surface_note = _build_contextual_tool_surface_note(state)
    instruction_defense = (
        render_instruction_defense_reminder(
            build_instruction_defense_context(state, context_packets.recent_evidence)
        )
        if _should_render_instruction_defense(state, context_packets.recent_evidence)
        else ""
    )

    def _section(
        *,
        key: str,
        title: str,
        body: str | None,
        group: str,
        priority: int,
        drop_policy: str = "compress",
        budget_cost: int = 0,
    ) -> PromptSection:
        return PromptSection(
            key=key,
            title=title,
            body=body or "",
            group=group,
            priority=priority,
            drop_policy=drop_policy,
            budget_cost=budget_cost,
        )

    base_policy_sections = (
        _section(
            key="role_policy",
            title="角色与核心职责",
            group="base_policy_sections",
            priority=0,
            drop_policy="keep",
            body=dedent(
                """
                你是 Specta AI 的智能编排助手。
                你的职责是：
                1. 理解用户的品牌分析需求
                2. 规划分析步骤并向用户解释计划
                3. 调用合适的分析工具执行任务
                4. 汇报结果并建议下一步
                5. 所有对用户可见的回复、计划、解释与思考流必须使用中文
                """
            ).strip(),
        ),
        _section(
            key="attachment_intake_policy",
            title="附件导入与理解路由",
            group="base_policy_sections",
            priority=1,
            body=dedent(
                """
                附件导入规则（高优先级）：
                - 当 state 中存在 pending_table_intake 且还没有 table_intake_result 时，必须优先调用 table_intake_skill。
                - table_intake_skill 只负责理解附件，不负责直接推进流程。执行后必须先解释判断，再调用 ask_user 请求确认。
                - 如果识别结果是 question_list：未确认前先 ask_user；确认后必须调用 question_simulation(mode="uploaded_list") 更新 A3 交付物。
                - 如果识别结果是 brand_competitor_info：先 ask_user 确认是否用于更新 A1 相关上下文，不可自动覆盖。
                - 如果识别结果是 link_list：先 ask_user 确认是否作为链接清单继续分析，不可自动套用到其他流程。
                - 如果用户没有文本消息，只上传了表格：也要基于 context + table_intake_skill 结果给出初步判断，并 ask_user 确认。
                - 如果 user_decisions.table_import_confirmed=true 且 confirmed_table_kind=question_list，而当前还没有新的 A3 结果，必须立即调用 question_simulation(mode="uploaded_list")。
                - 如果链接清单已经导入并生成交付物：先告诉用户链接清单已整理完成，再根据后续说明继续；当前不要自动调用 confidence_analysis_skill。
                """
            ).strip(),
        ),
        _section(
            key="workflow_routing_policy",
            title="流程路由规则",
            group="base_policy_sections",
            priority=2,
            body=dedent(
                """
                A1 完成后的流程（最高优先级）：
                - A1 完成后，必须先汇报结果并 ask_user，绝不直接调用 persona_generation 或 question_simulation。
                - 尚无基线分析时，必须按 question_simulation(mode="baseline_dynamic") -> answer_fetch -> analysis_report_skill(report_type="baseline") 执行。
                - 已有基线分析时，用户可进入引用置信度评估、场景细化、重跑基线或直接提问。

                场景细化流程：
                - 用户选择场景细化时：persona_generation -> 用户选择画像 -> question_simulation(mode="persona_focused") -> answer_fetch -> analysis_report_skill(report_type="persona")。
                - 如果用户明确要求“以某个身份 / 职业 / 角色生成问题”，仍调用 question_simulation，并通过 identity 传入该身份；若用户未明确要求，默认消费者视角，不要擅自加身份。

                其他固定路径：
                - 用户说“重跑基线”时：question_simulation(mode="baseline_dynamic") -> answer_fetch -> analysis_report_skill(report_type="baseline")。
                - 用户明确要检查引用可信度时：confidence_analysis_skill。
                - 用户基于已有结果要求深入分析、历史对比、解释原因、提炼风险时：post_analysis_skill。
                - 用户要求重新抓取、重跑部分平台、全量重跑、或从 API 改为浏览器模式时：统一走 answer_fetch，不要再发明 refetch 类能力名。
                - 用户选择“直接提问”时，禁止再次 ask_user 给子选项；直接自然语言引导用户在输入框中继续追问。
                - 只有用户明确在问跨历史材料、历史月份、历史导出、最近两次变化时，才优先使用 knowledge_*。
                - 围绕历史品牌/竞品/答案/引用时，优先 knowledge_lookup；围绕历史汇总时，优先 knowledge_aggregate；明确导出时，优先 knowledge_export；比较最近两轮变化时，优先 knowledge_compare。
                """
            ).strip(),
        ),
        _section(
            key="behavior_policy",
            title="行为与 ask_user 规则",
            group="base_policy_sections",
            priority=3,
            body=dedent(
                """
                行为准则：
                - 始终用温暖、自然、专业的语言交流，像真正了解品牌营销的顾问。
                - 所有对用户可见的回复、计划、提示、说明和思考流都必须使用中文；不要输出英文草稿或英文推理片段。
                - 在回复中说明打算做什么，然后调用对应工具。
                - 不要一次调用多个工具，每轮只执行一个步骤。
                - 画像生成完成后必须 ask_user 引导用户选画像；问题生成完成后必须 ask_user 让用户选择采集模式；答案抓取完成后不要 ask_user，必须立即调用 analysis_report_skill；分析报告完成后必须 ask_user 让用户决定是否做引用置信度评估或继续后续分析。
                - 如果用户请求不明确，用自然语言追问，不要调用 ask_user。
                - 步骤完成后的回复应包含 1 个具体数据点或风险发现，不要只报“完成了”。
                - 如果用户直接提供问题文本并要求抓取答案，可通过 answer_fetch 的 custom_questions 传入，无需先调用 question_simulation，但仍需明确 fetch_mode。
                - “完整模式/full 模式/完整采集”指 answer_fetch(fetch_mode="full")，不是重新生成问题。question_simulation 完成后，应先 answer_fetch 或 ask_user，不要再次 question_simulation。
                - 当条件不足、步骤失败或路由受限时，不要只说“无法完成/不能执行”；必须同时说明原因，并给出至少一个可执行的下一步方案。

                ask_user 使用限制：
                - 只允许在表格导入确认、品牌/竞品识别后确认基线、基线或分析报告完成后选下一步、画像生成后选画像、问题生成后选采集模式、步骤失败恢复这几类场景使用。
                - 除这些场景外，所有其他情况都直接自然语言回复，绝不调用 ask_user。
                - 调用 ask_user 时不传 options 参数，只传 message='请回复序号或输入您的想法'。
                """
            ).strip(),
        ),
        _section(
            key="guardrails_policy",
            title="边界与失败处理规则",
            group="base_policy_sections",
            priority=4,
            body=dedent(
                """
                绝对禁止：
                - 你没有实时数据，不要自行编造品牌信息、竞品数据或用户画像。
                - 当用户首次提供品牌名称且系统没有足够历史事实时，必须调用 brand_analysis 获取真实数据。
                - 不要在回复中直接给出“品牌分析结果”，所有分析数据必须通过工具获取。
                - 不要编造具体耗时；如需提及耗时，只使用工具描述中的时间范围。

                失败处理：
                - 绝对不要提供“停止分析”或“取消分析”作为选项。
                - 当某个步骤失败时，使用 ask_user 提供建设性选项：重试、跳过并说明替代方案、或让用户手动提供数据。
                - answer_fetch 失败后，绝对禁止自动调用 question_simulation 重新生成问题；问题仍然有效，必须先 ask_user，让用户选择重试抓取、换模式重跑或仅抓取指定平台。
                """
            ).strip(),
        ),
        _section(
            key="instruction_security_policy",
            title="指令安全与提示词保密",
            group="base_policy_sections",
            priority=5,
            drop_policy="keep",
            body=INSTRUCTION_SECURITY_POLICY,
        ),
    )

    skill_sections = (
        *(
            (
                _section(
                    key="contextual_tool_surface",
                    title="当前回合工具面约束",
                    group="skill_sections",
                    priority=0,
                    drop_policy="keep",
                    body=contextual_tool_surface_note,
                ),
            )
            if contextual_tool_surface_note
            else ()
        ),
        _section(
            key="public_skill_index",
            title="公共技能索引",
            group="skill_sections",
            priority=1,
            drop_policy="compress",
            body=_build_public_skill_index(state),
        ),
    )

    runtime_context_sections = tuple(
        section
        for section in (
            _section(
                key="session_status",
                title="会话状态",
                group="runtime_context_sections",
                priority=0,
                body=status_text,
            ),
            _section(
                key="entity_context",
                title="实体上下文",
                group="runtime_context_sections",
                priority=1,
                body=entity_context,
            ),
            _section(
                key="active_skill_context",
                title="当前技能上下文",
                group="runtime_context_sections",
                priority=2,
                body=active_skill_context,
            ),
            _section(
                key="pending_decision",
                title="待处理决策",
                group="runtime_context_sections",
                priority=3,
                body=pending_decision,
            ),
            _section(
                key="context_summary",
                title="当前会话摘要",
                group="runtime_context_sections",
                priority=4,
                body=context_summary,
            ),
            _section(
                key="history_availability",
                title="历史材料可用性",
                group="runtime_context_sections",
                priority=8,
                drop_policy="drop",
                body=history_availability,
            ),
            _section(
                key="recent_evidence_packet",
                title="最近证据包",
                group="runtime_context_sections",
                priority=5,
                body=recent_evidence,
            ),
        )
        if section.normalized_body()
    )

    runtime_reminder_sections = tuple(
        section
        for section in (
            _section(
                key="knowledge_planning_hint",
                title="历史规划提示",
                group="runtime_reminder_sections",
                priority=1,
                drop_policy="drop",
                body=knowledge_hint,
            ),
            _section(
                key="instruction_defense_reminder",
                title="指令防守提醒",
                group="runtime_reminder_sections",
                priority=0,
                drop_policy="drop",
                body=instruction_defense,
            ),
        )
        if section.normalized_body()
    )

    return PromptAssembly(
        base_policy_sections=base_policy_sections,
        skill_sections=skill_sections,
        runtime_context_sections=runtime_context_sections,
        runtime_reminder_sections=runtime_reminder_sections,
    )


def build_orchestrator_system_prompt(state: AgentState) -> str:
    """Build dynamic system prompt based on current state."""

    return build_orchestrator_prompt_assembly(state).render()


def _build_agent_result_summary(state: AgentState, tool_name: str) -> str:
    """Build a concise summary of agent results for the tool_result message."""
    if tool_name == "brand_analysis":
        bp = state.get("brand_profile")
        comps = state.get("competitors", [])
        if bp:
            comp_names = [c.get("name", "?") for c in (comps or [])]
            summary = (
                f"品牌分析完成。品牌：{bp.get('brand_name', '未知')}，"
                f"行业：{bp.get('industry', '未知')}，"
                f"定位：{bp.get('brand_positioning', '未知')}。"
                f"识别出 {len(comps or [])} 个竞品：{', '.join(comp_names[:5])}。"
            )
            has_baseline = bool(state.get("baseline_metrics"))
            summary += (
                DIRECTIVE_A1_HAS_BASELINE if has_baseline else DIRECTIVE_A1_NO_BASELINE
            )
            return summary
        return (
            "品牌分析暂未拿到有效结果。"
            "请先核对品牌名称是否准确，或补充官网/行业线索后让我重试品牌分析。"
        )

    if tool_name == "persona_generation":
        mp = state.get("marketing_personas")
        if mp:
            personas = mp.get("user_personas", [])
            if not personas:
                return (
                    "画像生成暂未拿到有效结果。"
                    "更合适的下一步是先补充品牌信息，或先运行基线分析后再重新生成画像。"
                )
            persona_names = [
                p.get("persona_name", p.get("name", f"画像{i+1}"))
                for i, p in enumerate(personas[:6])
            ]
            names_str = "、".join(persona_names)
            return (
                f"用户画像生成完成，共 {len(personas)} 个画像：{names_str}。"
                f"{DIRECTIVE_A2_ASK_PATH}"
            )
        return (
            "画像生成暂未成功。"
            "请告诉用户可以先补充品牌信息、先运行基线分析，或稍后重新尝试画像生成。"
        )

    if tool_name == "table_intake_skill":
        result = state.get("table_intake_result") or {}
        table_kind = result.get("table_kind", "unknown")
        summary = result.get("summary") or "表格理解完成。"
        if table_kind == "question_list":
            return (
                f"{summary}"
                "【强制操作】请先用自然语言告诉用户你识别到这是一份问题列表，并说明将挂接到 A3。"
                "然后调用 ask_user，请用户确认是否作为 A3 问题列表导入。"
                "推荐选项：1. 作为 A3 问题列表导入 2. 暂不导入。"
            )
        if table_kind == "brand_competitor_info":
            return (
                f"{summary}"
                "【强制操作】请先说明这份表格更适合作为 A1 的品牌/竞品信息输入，"
                "然后调用 ask_user，请用户确认是否更新当前品牌/竞品上下文。"
            )
        if table_kind == "link_list":
            return (
                f"{summary}"
                "【强制操作】请先说明这是一份链接清单，适合作为来源/链接清单继续分析，"
                "然后调用 ask_user，请用户确认是否继续。"
            )
        return (
            f"{summary}"
            "【强制操作】请告诉用户我暂时还不能稳定判断这份表格的用途，"
            "并补充可执行方案：重新上传单个 CSV/XLSX、说明希望挂接到哪个步骤、或拆分文件后再试。"
            "随后调用 ask_user 请求用户选择下一步。"
        )

    if tool_name == "question_simulation":
        sq = state.get("simulated_questions")
        if sq:
            qs = sq.get("simulated_questions", [])
            summary = (
                f"问题模拟完成。共生成 {len(qs)} 组模拟问题。{DIRECTIVE_A3_NEXT_FETCH}"
            )
            logger.info(
                "[Orchestrator] A3 tool_result directive (first 300 chars): %s",
                summary[:300],
            )
            return summary
        return (
            "问题模拟暂未生成有效问题。"
            "【强制操作】直接告知用户当前问题集不足以继续抓取，"
            "并提供两个选项：1) 重新生成问题；2) 换一种方式描述需求或改用上传问题列表。"
            "不要继续调用 answer_fetch，等待用户指示。"
        )

    if tool_name == "answer_fetch":
        fr = state.get("fetch_results")
        if fr:
            report_type = (
                "baseline"
                if (state.get("analysis_mode") or "persona") == "baseline"
                else "persona"
            )
            report_label = (
                "基线分析报告" if report_type == "baseline" else "场景分析报告"
            )
            return (
                f"AI答案抓取完成。共抓取 {len(fr)} 组问题结果。"
                f"【强制操作】不要调用 ask_user，不要等待用户确认。"
                f"你必须立即调用 analysis_report_skill(report_type='{report_type}') 生成{report_label}。"
            )
        return (
            "AI答案抓取完成，但未获取到有效数据。"
            "【强制操作】你必须使用 ask_user 向用户说明抓取失败，并提供以下选项："
            "1) 重新尝试抓取（可换模式，如 fast→full）；"
            "2) 仅抓取指定平台（继续走 answer_fetch，并通过 platforms 指定平台）；"
            "3) 手动提供问题重新抓取。"
            "【绝对禁止】不要调用 question_simulation 重新生成问题。"
            "问题已经在之前的步骤中生成，无需重新生成。"
        )

    if tool_name in {"data_analytics", "analysis_report_skill"}:
        current_mode = state.get("analysis_mode", "persona")
        if current_mode == "baseline":
            metrics = state.get("baseline_metrics") or state.get("metrics")
        else:
            metrics = state.get("metrics")
        if metrics:
            summary_metrics = (
                metrics.get("summary_metrics", {}) if isinstance(metrics, dict) else {}
            )
            mention_rate = (
                float(
                    summary_metrics.get(
                        "brand_mention_rate",
                        (
                            metrics.get("mention_rate", 0)
                            if isinstance(metrics, dict)
                            else 0
                        ),
                    )
                    or 0
                )
                * 100
            )
            official_citation_rate = (
                float(summary_metrics.get("official_citation_rate", 0) or 0) * 100
            )
            high_risk_count = int(
                summary_metrics.get("high_risk_scenario_count", 0) or 0
            )
            mode_label = "基线" if current_mode == "baseline" else "场景"
            summary = (
                f"{mode_label}数据分析完成。"
                f"品牌提及率：{mention_rate:.1f}％，"
                f"官网引用率：{official_citation_rate:.1f}％，"
                f"高风险场景：{high_risk_count} 个。"
            )
            if current_mode == "baseline":
                return summary + DIRECTIVE_A5_BASELINE_NEXT
            return summary + DIRECTIVE_A5_PERSONA_NEXT
        return (
            "分析报告暂未生成有效结果。"
            "请结合当前抓取结果说明缺口，并优先给出可执行方案：补抓缺失平台、重试当前模式，或确认是否先基于现有结果继续。"
        )

    if tool_name == "knowledge_lookup":
        result = state.get("knowledge_lookup_result") or {}
        matches = result.get("matches", [])
        if matches:
            top = matches[0]
            evidence_lines = "\n".join(
                _format_knowledge_lookup_match(match) for match in matches[:3]
            )
            return (
                f"历史知识检索完成，共命中 {len(matches)} 条材料。"
                f"最高相关来源类型：{top.get('source_type', 'unknown')}。"
                "\n可直接使用的证据如下：\n"
                f"{evidence_lines}\n"
                "请优先基于这些证据继续回答、分析、导出；"
                "只有当证据仍然不足时，再决定是否调用 brand_analysis / answer_fetch。"
            )
        return (
            "历史知识检索未命中足够材料。"
            "如果用户的问题仍需真实数据，请根据问题类型决定是否调用 brand_analysis 或 answer_fetch；"
            "如果该动作链路较长或模式不明确，再使用 ask_user。"
        )

    if tool_name == "knowledge_aggregate":
        result = state.get("knowledge_aggregate_result") or {}
        groups = result.get("groups", [])
        if groups:
            top = groups[0]
            group_lines = "\n".join(
                _format_knowledge_group(group) for group in groups[:5]
            )
            return (
                f"历史知识聚合完成，共统计 {result.get('total_records', 0)} 条材料，"
                f"得到 {len(groups)} 个分组。"
                f"当前最大分组是 {top.get('group_key', 'unknown')}，数量 {top.get('count', 0)}。"
                "\n关键分组如下：\n"
                f"{group_lines}\n"
                "请基于这些分组继续汇总、分析、导出或生成交付结果。"
            )
        return (
            "历史知识聚合未得到有效分组。"
            "如果用户仍需要结果，请判断是缩小筛选条件、改用 knowledge_lookup，"
            "还是通过 brand_analysis / answer_fetch 先补齐缺失材料。"
        )

    if tool_name == "knowledge_export":
        result = state.get("knowledge_export_result") or {}
        if result.get("status") == "hit":
            return (
                f"历史知识导出已完成，共整理 {result.get('item_count', 0)} 条记录。"
                f"交付物标题：{result.get('title', '历史知识导出')}。"
                "数据表 artifact 已经生成，请向用户说明已可查看并继续导出为 md/pdf，"
                "同时用 1-2 句话概括本次导出的范围。"
            )
        return (
            "历史知识导出未生成有效结果。"
            "请判断是缩小导出范围、先用 knowledge_lookup / knowledge_aggregate 查看材料，"
            "还是先通过 brand_analysis / answer_fetch 补齐缺失材料。"
        )

    if tool_name == "knowledge_compare":
        result = state.get("knowledge_compare_result") or {}
        comparisons = result.get("comparisons", [])
        if comparisons:
            top = comparisons[0]
            comparison_lines = "\n".join(
                _format_knowledge_comparison(item) for item in comparisons[:5]
            )
            return (
                f"历史知识对比完成。"
                f"已比较 {result.get('latest_label', 'latest')} 与 {result.get('previous_label', 'previous')}。"
                f"变化最大项是 {top.get('group_key', 'unknown')}，增量 {top.get('delta', 0)}。"
                "\n关键变化如下：\n"
                f"{comparison_lines}\n"
                "请基于这些变化继续解释趋势、给出分析结论或建议下一步动作。"
            )
        return (
            "历史知识对比未得到有效变化结果。"
            "如果是因为历史轮次不足，请直接向用户说明；"
            "如果是因为材料不足，请考虑先补齐 brand_analysis 或 answer_fetch。"
        )

    if tool_name == "confidence_analysis_skill":
        return (
            "引用内容置信度评估已完成。"
            "结果已经展示在画布中，您可以继续查看各引用来源的可信度、结构化质量和可核查性差异。"
        )

    if tool_name in {
        "post_analysis_skill",
        "drill_down_analysis",
        "compare_snapshots",
    }:
        last_skill_result = state.get("last_skill_result") or {}
        if last_skill_result.get("summary"):
            return str(last_skill_result["summary"])
        reply = state.get("orchestrator_reply", "")
        return f"后续分析已完成。{reply[:200]}"

    current_skill = state.get("current_skill")
    last_skill_result = state.get("last_skill_result") or {}
    if current_skill and tool_name == current_skill:
        summary = str(last_skill_result.get("summary") or "").strip()
        if summary:
            return summary

    if tool_name == "create_monitoring_schedule":
        reply = state.get("orchestrator_reply", "")
        return f"监测计划创建已完成。{reply[:200]}"

    return f"工具 {tool_name} 执行完成。"


def _build_knowledge_export_completion_reply(result: dict[str, Any]) -> str:
    """Build a deterministic close-out reply for successful knowledge exports."""

    item_count = int(result.get("item_count") or 0)
    period = str(result.get("analysis_period") or "").strip()
    description = str(result.get("description") or "").strip()
    summary_metrics = result.get("summary_metrics") or {}
    platform_count = summary_metrics.get("覆盖平台数")
    source_type_count = summary_metrics.get("来源类型")

    detail_parts: list[str] = []
    if period:
        detail_parts.append(f"范围覆盖 {period}")
    if platform_count:
        detail_parts.append(f"{platform_count} 个平台")
    if source_type_count:
        detail_parts.append(f"{source_type_count} 类材料")
    detail_text = "，".join(detail_parts)

    reply = f"已完成导出，当前数据表共整理 {item_count} 条记录。"
    if detail_text:
        reply += f" 本次{detail_text}。"
    if description:
        reply += f" {description}"
    if result.get("truncated"):
        reply += (
            f" 当前结果较多，仅展示前 {int(result.get('export_limit') or item_count)} 条记录，"
            "如需完整导出请缩小筛选范围后重试。"
        )
    reply += " 您可以直接在右侧继续导出为 md 或 pdf。"
    return reply


def _get_tool_name_from_node(node_name: str) -> str | None:
    """Reverse lookup: node name → tool name."""
    preferred = {
        "a5_analytics": "analysis_report_skill",
        "confidence_analysis_executor": "confidence_analysis_skill",
        "a7_confidence_signal": "confidence_analysis_skill",
        "post_analysis_executor": "post_analysis_skill",
    }
    if node_name in preferred:
        return preferred[node_name]
    node_to_tool = {v: k for k, v in TOOL_TO_NODE.items()}
    return node_to_tool.get(node_name)


def _build_ask_user_fallback_reply(
    state: AgentState,
    tool_name: str | None,
    message: str,
) -> str:
    """Build a deterministic user-facing reply when LLM omits natural language."""
    if tool_name == "brand_analysis":
        has_baseline = bool(state.get("baseline_metrics"))
        brand_name = (
            (state.get("brand_profile", {}) or {}).get("brand_name")
            or state.get("brand_name")
            or "该品牌"
        )
        if has_baseline:
            return (
                f"{brand_name}的品牌分析已完成，我已经整理出品牌画像和竞品格局。"
                "接下来您可以先做一次引用内容置信度评估，"
                "也可以继续生成用户画像做场景细化分析、重新运行基线分析，"
                "或者直接基于已有结果提问。"
            )
        return (
            f"{brand_name}的品牌分析已完成，但当前还没有行业基线。"
            "建议先运行基线分析，建立各 AI 平台对该品牌的全景认知基线，"
            "后续再做画像和场景分析会更有对照价值。"
        )

    if tool_name == "persona_generation":
        return (
            "用户画像已生成并展示在右侧画布中。"
            "请先在画布里勾选您想重点分析的画像，然后回复我继续；"
            "如果不想限定画像，也可以直接告诉我走品牌全景分析。"
        )

    if tool_name == "question_simulation":
        return (
            "问题模拟已完成，相关问题已经展示在右侧画布中。"
            "您现在可以告诉我选择快速采集、完整采集，或要求我重新生成问题。"
        )

    if tool_name == "table_intake_skill":
        result = state.get("table_intake_result") or {}
        summary = result.get("summary") or "表格理解完成。"
        return f"{summary} 请确认是否按我识别的用途继续。"

    if tool_name == "answer_fetch":
        return (
            "答案抓取已完成。"
            "我会基于当前抓取结果立即继续生成分析报告，"
            "报告出来后您再决定是否继续做引用内容置信度评估或进入后续分析。"
        )

    if tool_name in {"data_analytics", "analysis_report_skill"}:
        return (
            "分析报告已生成。"
            "您现在可以选择继续做一次引用内容置信度评估，"
            "或者基于当前报告进入下一步画像分析、深入分析或直接提问。"
        )

    if tool_name == "confidence_analysis_skill":
        return (
            "引用内容置信度评估已完成。"
            "您现在可以继续基于这份评估追问具体来源问题，"
            "或者回到主报告继续后续分析。"
        )

    return message or "请继续告诉我您的选择。"


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
    table_kind = result.get("table_kind")
    if table_kind == "question_list":
        import_intent = (result.get("import_intent") or {}).get("mode")
        if import_intent == "unspecified":
            defense_msg = "我识别到这是一份问题列表，且当前会话里已有上传问题。请先确认本次是整合到上一版，还是替换上一版。"
            defense_options = [
                {
                    "id": "table_import_question_list_merge",
                    "label": "整合导入",
                    "description": "保留上一版上传问题，并追加本次新问题",
                },
                {
                    "id": "table_import_question_list_replace",
                    "label": "替换导入",
                    "description": "放弃上一版上传问题，只保留本次新问题",
                },
                {
                    "id": "table_import_cancel",
                    "label": "暂不导入",
                    "description": "保留当前结果，不执行本次导入",
                },
            ]
        else:
            defense_msg = (
                "我识别到这是一份问题列表，准备作为 A3 问题列表导入。是否继续？"
            )
            defense_options = [
                {
                    "id": "table_import_question_list",
                    "label": "作为 A3 问题列表导入",
                    "description": "先更新 A3 交付物，再继续后续抓取流程",
                },
                {
                    "id": "table_import_cancel",
                    "label": "暂不导入",
                    "description": "保留当前结果，不执行本次导入",
                },
            ]
        step_name = "确认问题列表导入"
    elif table_kind == "brand_competitor_info":
        defense_msg = (
            "我识别到这是一份品牌/竞品信息表，准备更新当前 A1 相关上下文。是否继续？"
        )
        defense_options = [
            {
                "id": "table_import_brand_info",
                "label": "更新品牌/竞品信息",
                "description": "先更新 A1 交付物，再回到后续流程",
            },
            {
                "id": "table_import_cancel",
                "label": "暂不更新",
                "description": "保留当前上下文，不执行本次导入",
            },
        ]
        step_name = "确认品牌信息导入"
    else:
        defense_msg = "我识别到这是一份链接清单，准备整理为后续来源分析输入。是否继续？"
        defense_options = [
            {
                "id": "table_import_link_list",
                "label": "作为链接清单继续",
                "description": "先生成链接清单交付物，再继续后续分析",
            },
            {
                "id": "table_import_cancel",
                "label": "暂不继续",
                "description": "保留当前流程，不执行本次导入",
            },
        ]
        step_name = "确认链接清单导入"

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
            "content": "等待用户确认表格导入动作...",
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
                "step_name": step_name,
                "message": defense_msg,
                "options": defense_options,
            },
            "agent_retry_counts": current_retry_counts,
        },
    )


def build_orchestrator_messages(state: AgentState) -> list[dict[str, Any]]:
    """Build message history for the orchestrator LLM call.

    If the last message in history is an assistant message with tool_calls
    but no matching tool result, inject one from the agent's output in state.
    """
    history = state.get("orchestrator_history", [])
    if not history:
        # First call: use the user's original message with full brand context
        brand_name = state.get("brand_name", "")
        industry = state.get("industry_hint", "")
        website = state.get("official_website", "")
        context_parts = [f"请帮我分析品牌：{brand_name}"]
        if industry:
            context_parts.append(f"（行业：{industry}）")
        if website:
            context_parts.append(f"（官网：{website}）")
        return [{"role": "user", "content": "".join(context_parts)}]

    # Limit history to last 20 messages to prevent context growth
    MAX_HISTORY = 20
    if len(history) > MAX_HISTORY:
        history = history[-MAX_HISTORY:]

    messages = list(history)

    # Check if the last message is an assistant with tool_calls but no tool result follows
    if (
        messages
        and messages[-1].get("role") == "assistant"
        and messages[-1].get("tool_calls")
    ):
        # Missing tool result — inject one
        tool_calls = messages[-1]["tool_calls"]
        tc = tool_calls[0]
        tc_id = tc.get("id", state.get("tool_call_id", "call_1"))
        tc_name = tc.get("function", {}).get("name", "")

        summary = _build_agent_result_summary(state, tc_name)
        tool_msg: dict[str, Any] = {
            "role": "tool",
            "content": summary,
            "tool_call_id": tc_id,
        }
        if tc_name:
            tool_msg["name"] = tc_name
        messages.append(tool_msg)
        logger.info(
            f"[Orchestrator] Injected tool result for {tc_name} "
            f"(tool_call_id={tc_id}): {summary[:80]}..."
        )

    return messages


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
    "table_intake_skill": "table_intake",
    "analysis_report_skill": "a5_analytics",
    "data_analytics": "a5_analytics",
    "knowledge_lookup": "knowledge_lookup",
    "knowledge_aggregate": "knowledge_aggregate",
    "knowledge_compare": "knowledge_compare",
    "knowledge_export": "knowledge_export",
    "confidence_analysis_skill": "confidence_analysis_executor",
    "post_analysis_skill": "post_analysis_executor",
    "drill_down_analysis": "drill_down",
    "compare_snapshots": "compare_snapshots",
    # Monitoring tools (Cycle 4)
    "create_monitoring_schedule": "create_monitoring",
}

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "brand_analysis": "品牌竞品分析",
    "persona_generation": "用户画像生成",
    "question_simulation": "问题模拟生成",
    "answer_fetch": "AI答案抓取",
    "table_intake_skill": "表格导入理解",
    "analysis_report_skill": "完整分析报告",
    "data_analytics": "数据分析报告",
    "knowledge_lookup": "历史知识检索",
    "knowledge_aggregate": "历史知识聚合",
    "knowledge_compare": "历史知识对比",
    "knowledge_export": "历史知识导出",
    "confidence_signal_skill": "引用置信度评估",
    "citation_confidence_analysis": "引用内容置信度评估",
    "confidence_analysis_skill": "引用置信度评估",
    "post_analysis_skill": "后续分析",
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    # Monitoring tools (Cycle 4)
    "create_monitoring_schedule": "创建监测计划",
}

# Step definitions for workflow progress tracking
WORKFLOW_STEPS = [
    ("A1", "品牌信息采集", "brand_profile"),
    ("A2", "用户画像生成", "marketing_personas"),
    ("A3", "问题模拟生成", "simulated_questions"),
    ("A4", "AI答案抓取", "fetch_results"),
    ("A5", "数据分析报告", "metrics"),
]


def _build_workflow_steps(state: AgentState) -> list[dict[str, str]]:
    """Build workflow steps list with completion status from state."""
    user_decisions = state.get("user_decisions", {})
    analysis_mode = state.get("analysis_mode", "persona")
    steps = []
    for step_id, label, state_key in WORKFLOW_STEPS:
        # A5 completion check depends on analysis_mode:
        # baseline mode writes to baseline_metrics; persona/default to metrics.
        if step_id == "A5":
            if analysis_mode == "baseline":
                completed = bool(state.get("baseline_metrics"))
            else:
                completed = bool(state.get("metrics"))
        else:
            completed = bool(state.get(state_key))

        if completed:
            status = "completed"
        elif _is_step_skipped(step_id, state, user_decisions):
            status = "skipped"
        else:
            status = "pending"
        steps.append({"id": step_id, "label": label, "status": status})
    return steps


def _is_step_skipped(step_id: str, state: AgentState, user_decisions: dict) -> bool:
    """Determine if a step was intentionally skipped."""
    analysis_mode = state.get("analysis_mode")
    if step_id == "A1":
        # A1 is skipped in baseline mode (re-run baseline skips brand analysis)
        if analysis_mode == "baseline":
            return True
    if step_id == "A2":
        # A2 is skipped in baseline mode
        if analysis_mode == "baseline":
            return True
        if user_decisions.get("a3_mode") == "brand":
            return True
        if state.get("simulated_questions") and not state.get("marketing_personas"):
            return True
    return False


def _matches_failed_step(tool_name: str, failed_step: str) -> bool:
    step_id_map = {
        "brand_analysis": "A1",
        "persona_generation": "A2",
        "question_simulation": "A3",
        "answer_fetch": "A4",
        "analysis_report_skill": "A5",
        "data_analytics": "A5",
        "confidence_analysis_skill": "A7",
    }
    expected_step = step_id_map.get(tool_name, "")
    return failed_step in {tool_name, expected_step}


def _build_error_recovery_message(
    error_info: dict[str, Any],
    alternative_options: list[dict[str, Any]] | None = None,
) -> str:
    failed_step = str(error_info.get("step", "未知"))
    error_msg = str(error_info.get("error", "未知错误")).strip()
    error_category = str(error_info.get("category", "")).strip()
    alternative_preview = summarize_alternative_actions(alternative_options or [])

    if failed_step == "A5":
        if error_category == "system_persistence":
            message = (
                "分析结果已经生成，但在保存最终报告产物时发生了系统错误。"
                "这不是抓取数据质量问题，通常不需要重新抓取。"
                "建议直接重新尝试生成报告。"
            )
            if alternative_preview:
                message += f" 当前优先方案：{alternative_preview}。"
            return message
        if error_category == "system":
            message = (
                "报告生成遇到了系统处理问题，当前失败并不等于抓取数据不可用。"
                "建议先重新尝试生成报告；如果仍失败，再检查当前结果结构。"
            )
            if alternative_preview:
                message += f" 当前优先方案：{alternative_preview}。"
            return message
        message = (
            "报告生成遇到了处理问题。"
            "当前失败不一定来自抓取数据本身，建议先重新尝试生成报告。"
        )
        if alternative_preview:
            message += f" 当前优先方案：{alternative_preview}。"
        return message

    failed_step_label = get_user_visible_runtime_label(failed_step)
    clipped_error = error_msg[:100] if error_msg else "未知错误"
    message = f"{failed_step_label}遇到问题：{clipped_error}。"
    if alternative_preview:
        message += f" 建议优先：{alternative_preview}。"
    message += "请选择后续操作。"
    return message


def _sanitize_runtime_policy_state(state: AgentState) -> AgentState:
    """Drop consumed runtime policy artifacts before asking the model again."""

    return {
        **state,
        **clear_runtime_policy_fields(),
    }


def _merge_command_update(command: Command, extra_update: dict[str, Any]) -> Command:
    return Command(
        goto=command.goto,
        update={
            **dict(command.update or {}),
            **extra_update,
        },
    )


async def _execute_runtime_policy_action(
    *,
    state: AgentState,
    session_id: str,
) -> Command | None:
    action = parse_next_required_action(state.get("next_required_action"))
    if action is None:
        return None

    logger.info(
        "[Orchestrator] Consuming next_required_action: tool=%s source=%s reason=%s",
        action.tool_name,
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

    available_sources = ((manifest or {}).get("available_sources") or {})
    has_history_materials = any(bool(value) for value in available_sources.values())

    if has_history_materials:
        reply_text = (
            f"我先查看历史里和「{brand_seed}」相关的材料，"
            "如果已有品牌档案、竞品信息或历史抓取结果，就优先复用这些事实继续分析。"
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
        # In baseline mode, Phase 1 completion is not "all done" — Phase 2 may follow
        is_baseline_phase = state.get("analysis_mode") == "baseline"
        all_done = (
            completed_count + skipped_count
        ) == total_count and not is_baseline_phase
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
                progress=completed_count / total_count,
                message=f"完成：{display_name}",
                status="completed" if all_done else "running",
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

    if last_tool == "knowledge_export":
        export_result = state.get("knowledge_export_result") or {}
        if export_result.get("status") == "hit" and export_result.get("artifact_id"):
            completion_reply = _build_knowledge_export_completion_reply(export_result)
            history_with_reply = list(state.get("orchestrator_history", []) or [])
            history_with_reply.append(
                {"role": "assistant", "content": completion_reply}
            )

            from app.workflow.events import send_execution_complete

            await send_reply_event(
                session_id,
                completion_reply,
                is_delta=False,
                is_new_round=True,
            )
            await send_reply_event(session_id, "", is_complete=True)
            await send_execution_complete(session_id, "历史知识导出完成")

            return Command(
                goto=END,
                update={
                    "execution_status": "completed",
                    "awaiting_user": False,
                    "pending_confirmation": None,
                    "orchestrator_reply": completion_reply,
                    "orchestrator_history": history_with_reply,
                },
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

    working_state = state
    manifest = await _hydrate_knowledge_manifest(state)
    if manifest is not None:
        working_state = {**state, "knowledge_manifest": manifest}
    llm_state = _sanitize_runtime_policy_state(working_state)

    # Build orchestrator call
    system_prompt = build_orchestrator_system_prompt(llm_state)
    messages = build_orchestrator_messages(llm_state)
    tools = await build_agent_tools(llm_state)

    # Stream LLM response
    model = get_llm_model()

    reply_text = ""
    thinking_text = ""
    tool_call_result = None
    is_first_reply_chunk = True
    last_finish_reason: str | None = None
    last_usage = None
    stream_started_at = perf_counter()
    stream_thoughts = _should_stream_thoughts(llm_state)
    thinking_placeholder_sent = False

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
            # Tool calls arrive at end of stream.
            # IMPORTANT: The final chunk with tool_calls also contains the
            # full accumulated content_buffer and reasoning_buffer (not deltas),
            # so we must skip content/thinking processing for that chunk.
            if chunk.finish_reason:
                last_finish_reason = chunk.finish_reason
            if chunk.usage:
                last_usage = chunk.usage
            if chunk.tool_calls:
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
            from app.services.llm_usage_service import record_llm_usage_async

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
        assistant_msg: dict[str, Any] = {
            "role": "assistant",
            "content": reply_text,
        }
        if tool_call_result:
            assistant_msg["tool_calls"] = [
                {
                    "id": tool_call_result.id or "call_1",
                    "type": "function",
                    "function": {
                        "name": tool_call_result.name,
                        "arguments": json.dumps(
                            tool_call_result.arguments, ensure_ascii=False
                        ),
                    },
                }
            ]
        new_history.append(assistant_msg)

        if tool_call_result:
            return await _handle_tool_call(
                llm_state, session_id, tool_call_result, reply_text, new_history
            )

        knowledge_fallback = _infer_knowledge_fallback_tool(llm_state)
        if knowledge_fallback is not None:
            fallback_tool_name, fallback_tool_args = knowledge_fallback
            logger.warning(
                "[Orchestrator] No tool call for clear history task; forcing %s with args=%s",
                fallback_tool_name,
                fallback_tool_args,
            )
            return await _handle_tool_call(
                llm_state,
                session_id,
                SimpleNamespace(
                    name=fallback_tool_name,
                    arguments=fallback_tool_args,
                    id=f"fallback_{fallback_tool_name}_{int(datetime.now().timestamp() * 1000)}",
                ),
                reply_text,
                new_history,
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
        if (
            last_tool == "question_simulation"
            and state.get("simulated_questions")
            and not user_decisions.get("fetch_mode_confirmed", False)
            and not user_decisions.get("fetch_mode_pending", False)
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

    except Exception as e:
        logger.error(f"[Orchestrator] Error: {e}", exc_info=True)
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

        # ---- Headless mode: auto-confirm with first option, skip wait ----
        if state.get("headless_mode"):
            auto_choice = options[0] if options else {"id": "confirm", "label": "确认"}
            auto_reply = f"[自动确认] {auto_choice.get('label', '确认')}"
            logger.info(
                "[Orchestrator] Headless mode: auto-confirming ask_user "
                "with option '%s'",
                auto_choice.get("id"),
            )
            # Inject tool result with auto-confirm into history
            new_history.append(
                {
                    "role": "tool",
                    "content": auto_reply,
                    "tool_call_id": tool_call.id or "call_1",
                }
            )
            # Append user message so orchestrator sees the "reply"
            new_history.append(
                {
                    "role": "user",
                    "content": auto_reply,
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
                },
            )

        confirm_type = tool_args.get("type", "simple")
        waiting_tips = tool_args.get("waiting_tips", [])
        checklist = tool_args.get("checklist", [])
        request_id = tool_call.id or f"ask_user_{id(tool_call)}"

        if (
            not options
            and state.get("table_intake_result")
            and last_tool_name == "table_intake_skill"
        ):
            result = state.get("table_intake_result") or {}
            table_kind = result.get("table_kind")
            if table_kind == "question_list":
                import_intent = (result.get("import_intent") or {}).get("mode")
                if import_intent == "unspecified":
                    options = [
                        {
                            "id": "table_import_question_list_merge",
                            "label": "整合导入",
                            "description": "保留上一版上传问题，并追加本次新问题",
                        },
                        {
                            "id": "table_import_question_list_replace",
                            "label": "替换导入",
                            "description": "放弃上一版上传问题，只保留本次新问题",
                        },
                        {
                            "id": "table_import_cancel",
                            "label": "暂不导入",
                            "description": "保留当前结果，不执行本次导入",
                        },
                    ]
                else:
                    options = [
                        {
                            "id": "table_import_question_list",
                            "label": "作为 A3 问题列表导入",
                            "description": "先更新 A3 交付物，再继续后续抓取流程",
                        },
                        {
                            "id": "table_import_cancel",
                            "label": "暂不导入",
                            "description": "保留当前结果，不执行本次导入",
                        },
                    ]
            elif table_kind == "brand_competitor_info":
                options = [
                    {
                        "id": "table_import_brand_info",
                        "label": "更新品牌/竞品信息",
                        "description": "将表格作为 A1 的结构化补充输入",
                    },
                    {
                        "id": "table_import_cancel",
                        "label": "暂不更新",
                        "description": "保留当前上下文，不执行本次导入",
                    },
                ]
            elif table_kind == "link_list":
                options = [
                    {
                        "id": "table_import_link_list",
                        "label": "作为链接清单继续",
                        "description": "将表格作为来源/链接清单继续分析",
                    },
                    {
                        "id": "table_import_cancel",
                        "label": "暂不继续",
                        "description": "保留当前流程，不执行本次导入",
                    },
                ]

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
    selected_skill_package_path = None
    selected_skill_package_context = None
    selected_skill_prompt_overlay = None
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
        selected_skill_package_path = resolved_skill.package_path
        selected_skill_package_context = resolved_skill.package_body
        selected_skill_prompt_overlay = resolved_skill.prompt_overlay
        selected_skill_contract = resolved_skill.skill_contract.to_state_payload()
        selected_skill_prompt_sections = selected_skill_contract.get(
            "prompt_sections"
        )
        node_name = resolved_skill.node_name
        tool_args = dict(resolved_skill.merged_tool_args)
    else:
        node_name = TOOL_TO_NODE.get(tool_name)

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
        requested_question_mode = tool_args.get("mode", "")
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
        current_count = retry_counts.get(retry_key, 0)
        if current_count >= 2:
            logger.warning(
                f"[Orchestrator] Tool {retry_key} already called {current_count} times, blocking retry"
            )
            # Inject a tool_result error into history so LLM knows to offer alternatives
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
        }
        workflow_steps = _build_workflow_steps(state)
        current_step_id = tool_to_step_id.get(effective_tool_name)
        if current_step_id is None and resolved_skill is not None:
            current_step_id = {
                "a5_data_analytics": "A5",
                "confidence_analysis_executor": "A7",
                "a7_confidence_signal": "A7",
            }.get(resolved_skill.executor_ref)
        for s in workflow_steps:
            if s["id"] == current_step_id:
                s["status"] = "in_progress"
        completed_count = sum(1 for s in workflow_steps if s["status"] == "completed")
        total_count = len(workflow_steps)
        await send_progress_event(
            session_id,
            step=effective_tool_name,
            step_name=display_name,
            progress=completed_count / total_count,
            message=f"正在执行：{display_name}",
            status="running",
            steps=workflow_steps,
        )

        # Fallback: if LLM produced no reply text, emit a short status line
        # so the user sees something before the long-running agent starts.
        if not reply_text.strip() and effective_tool_name != "answer_fetch":
            FALLBACK_TEXTS = {
                "brand_analysis": "正在收集品牌基本信息和竞品格局，请稍候...",
                "persona_generation": "正在根据品牌特征生成用户画像，请稍候...",
                "question_simulation": "正在模拟真实用户可能在 AI 平台中提出的问题，请稍候...",
                "analysis_report_skill": "正在整理场景、风险与优先动作建议，请稍候…",
                "data_analytics": "正在整理场景、风险与优先动作建议，请稍候…",
                "confidence_analysis_skill": "正在评估当前引用来源的可信度和结构化质量，请稍候...",
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
                    "post_analysis_executor": FALLBACK_TEXTS["post_analysis_skill"],
                }.get(resolved_skill.executor_ref)
            fallback_text = fallback_text or f"正在执行：{display_name}，请稍候..."
            await send_reply_event(
                session_id, fallback_text, is_delta=True, is_new_round=True
            )
            await send_reply_event(session_id, "", is_complete=True)

        # Layer 2: plan event
        await send_plan_event(
            session_id,
            f"正在执行：{display_name}",
        )

        # Layer 3: action log
        await send_action_log_event(
            session_id,
            "agent_call",
            f"调用 {display_name}...",
            step=effective_tool_name,
            is_complete=False,
        )

        # Pass brand_name from tool_args if brand_analysis
        extra_updates: dict[str, Any] = {}
        if effective_tool_name == "brand_analysis" and tool_args.get("brand_name"):
            extra_updates["brand_name"] = tool_args["brand_name"]

        # Store user_decisions for a3 mode
        if effective_tool_name == "question_simulation":
            user_decisions = dict(state.get("user_decisions", {}))
            # Reset fetch_mode guard flags when re-running A3
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
                user_decisions["selected_persona_ids"] = [tool_args["persona_id"]]
            extra_updates["user_decisions"] = user_decisions

        # Pass fetch_mode for A4 + custom_questions + ask_user guard
        if effective_tool_name == "answer_fetch":
            custom_qs = tool_args.get("custom_questions")
            if custom_qs and isinstance(custom_qs, list):
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
            report_type = tool_args.get("report_type", "persona")
            extra_updates["analysis_mode"] = report_type

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
                "current_skill_package_path": selected_skill_package_path,
                "current_skill_package_context": selected_skill_package_context,
                "current_skill_prompt_overlay": selected_skill_prompt_overlay,
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
