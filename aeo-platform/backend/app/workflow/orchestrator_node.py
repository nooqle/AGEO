"""LLM-driven orchestrator node for Specta AI workflow.

This module implements the core orchestrator that uses LLM Function Calling
to dynamically decide which Agent to invoke, replacing the hardcoded pipeline.
"""

import json
import logging
from datetime import datetime
from typing import Any

from langgraph.graph import END
from langgraph.types import Command

from app.workflow.state import AgentState
from app.core.llm import get_llm_model
from app.core.websocket_server import manager
from app.workflow.events import (
    send_reply_event,
    send_plan_event,
    send_action_log_event,
    send_thought_event,
    send_confirmation_request,
)
from app.workflow.nodes_streaming import async_wrap_sync_gen
from app.core.constants import PlatformConstants

logger = logging.getLogger(__name__)


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
            "模拟用户可能向AI搜索引擎提出的问题。"
            "可基于品牌全景模式或画像聚焦模式生成。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "mode": {
                    "type": "string",
                    "enum": ["brand_panorama", "persona_focused", "baseline_dynamic"],
                    "description": "生成模式：brand_panorama=品牌全景, persona_focused=画像聚焦, baseline_dynamic=行业基线全景",
                },
                "persona_id": {
                    "type": "string",
                    "description": "聚焦的画像ID（persona_focused模式时需要）",
                },
            },
        },
    },
    {
        "name": "answer_fetch",
        "description": (
            "从多个AI平台（豆包、混元、Kimi、DeepSeek）抓取对模拟问题的回答。"
            "前置条件：1) 问题模拟已完成（或提供了 custom_questions）；2) 用户已明确选择 fetch_mode（fast 或 full）。"
            "如果用户尚未选择采集模式，此工具无法执行。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "fetch_mode": {
                    "type": "string",
                    "enum": ["fast", "full"],
                    "description": (
                        "采集模式（必须由用户选择）：\n"
                        "fast=通过API调用豆包、混元和Kimi，并通过浏览器采集DeepSeek，约3-5分钟，快速建立品牌AI表现的初步观感，但API返回内容与真实用户网页端体验可能存在差异；\n"
                        "full=4平台全部通过浏览器模拟真实用户访问，约8-15分钟，完全还原用户真实体验，数据最准确，是深度AEO分析的最佳选择"
                    ),
                },
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要抓取的平台列表（可选，默认全部）",
                },
                "custom_questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "用户自定义问题文本列表（可选）。当用户直接提供问题时使用，将覆盖 A3 生成的问题。",
                },
            },
            "required": ["fetch_mode"],
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
            "示例消息：'定期监测可以帮助您持续跟踪品牌在AI搜索中的表现变化。我建议为「小米」设置以下监测计划：\n\n"
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
        "name": "selective_refetch",
        "description": (
            "仅对指定平台重新抓取数据，保留其他平台的原有结果，然后重新生成报告。"
            "例如：'重新分析Kimi的结果'、'再抓取一次DeepSeek'。"
            "前置条件：当前会话中必须已有模拟问题（simulated_questions）。"
            "如果没有先前分析数据，不要调用此工具，提示用户先运行完整分析。"
            "会运行 A4(仅指定平台) → A5(重新生成报告)。"
            "注意：如果用户要求用 Full 模式重跑全部平台，应使用 answer_fetch(fetch_mode='full')，而非此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要重新抓取的平台列表: 'kimi', 'deepseek', 'doubao', 'hunyuan'",
                },
                "fetch_mode": {
                    "type": "string",
                    "enum": ["fast", "full"],
                    "description": "采集模式（可选，默认fast）。full=全浏览器模式",
                },
            },
            "required": ["platforms"],
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
                    "description": "等待提示（仅在用户确认后将立即执行耗时操作时提供，如AI答案抓取预计8-12分钟。普通确认或选择场景不要填写此字段）",
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


def build_agent_tools() -> list[dict[str, Any]]:
    """Build LLM tools format from AGENT_REGISTRY."""
    return [
        {"type": "function", "function": agent}
        for agent in AGENT_REGISTRY
    ]


# =============================================================================
# System Prompt Builder
# =============================================================================

def _build_context_summary(state: AgentState) -> str:
    """Build a summary of what data exists in the current session.

    Includes tool availability hints (Review C4) to help LLM
    distinguish between 9 tools and avoid misrouting.
    """
    parts = []
    available_tools = []
    unavailable_tools = []

    if state.get("brand_profile"):
        brand = state["brand_profile"]
        parts.append(f"- 已分析品牌: {brand.get('brand_name', '未知')}")
        parts.append(f"- 行业: {brand.get('industry', '未知')}")

    if state.get("competitors"):
        names = [c.get("name", "") for c in state["competitors"][:5]]
        parts.append(f"- 已识别竞品: {', '.join(names)}")

    if state.get("fetch_results"):
        parts.append(f"- 抓取结果: {len(state['fetch_results'])} 组问题")
        available_tools.append("drill_down_analysis (可深入分析已有结果)")
        available_tools.append("selective_refetch (可重新抓取指定平台)")
    else:
        unavailable_tools.append("drill_down_analysis (尚无抓取结果)")
        unavailable_tools.append("selective_refetch (尚无先前分析)")

    if state.get("metrics"):
        m = state["metrics"]
        parts.append(f"- 品牌提及率: {m.get('mention_rate', 'N/A')}")

    if state.get("baseline_metrics"):
        bm = state["baseline_metrics"]
        parts.append(f"- 基线提及率: {bm.get('mention_rate', 'N/A')}")
        parts.append("- 基线报告: 已完成")

    if state.get("entity_id"):
        parts.append(f"- 品牌实体ID: {state['entity_id']} (有历史快照)")
        available_tools.append("compare_snapshots (可与历史分析对比)")
        available_tools.append("create_monitoring_schedule (可创建定时监测计划)")
    else:
        unavailable_tools.append("compare_snapshots (尚无品牌实体)")
        unavailable_tools.append("create_monitoring_schedule (尚无品牌实体)")

    if not parts:
        summary = "\n当前会话数据: 尚无分析数据。"
    else:
        summary = "\n当前会话数据:\n" + "\n".join(parts)

    # Tool availability hints (Review C4)
    if available_tools:
        summary += "\n\n可用的追问工具:\n" + "\n".join(f"  - {t}" for t in available_tools)
    if unavailable_tools:
        summary += "\n\n不可用的工具（缺少前置数据）:\n" + "\n".join(f"  - {t}" for t in unavailable_tools)

    return summary


# =============================================================================
# Post-Agent Action Directives (共享常量)
# 这些文本同时被 system prompt 和 _build_agent_result_summary 引用
# 修改时请确保两处语义一致
# =============================================================================

DIRECTIVE_A1_HAS_BASELINE = (
    "【强制操作】你必须先用 3-5 句话向用户汇报品牌分析结果（包含至少1个具体洞察），"
    "然后在消息末尾用自然语言列出选项：\n"
    "1. 生成用户画像，进入场景细化分析（推荐）— 基于不同用户群体深入分析品牌在各场景下的AI曝光表现\n"
    "2. 重新运行基线分析 — 使用最新数据重新评估品牌在各AI平台上的基线表现\n"
    "3. 直接提问 — 针对已有数据自由提问\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
    "不要跳过 ask_user，不要自行决定下一步。"
)

DIRECTIVE_A1_NO_BASELINE = (
    '【强制操作】当前仅完成了品牌分析，还没有建立行业基线。\\n'
    '你必须先向用户说明：“基线分析会用行业通用问题建立品牌在各个AI平台的全景基线，后续画像和场景分析都会基于它进行对比。”\\n'
    '1) 基线分析会采集行业通用问题的AI回答，建立品牌全局基线\\n'
    '2) 基线分析完成后，再生成用户画像可以做场景对比\\n'
    '3) 完整采集模式下需要约8-12分钟\\n'
    '请向用户给出两个选择：\\n'
    '1. 先运行基线分析\\n'
    '2. 暂不\\n'
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
    "1. 快速采集（推荐）— 通过 API 调用豆包、混元和 Kimi，并通过浏览器采集 DeepSeek，约 3-5 分钟。"
    "能快速建立品牌在 AI 搜索中的初步观感，但 API 返回的内容与真实用户在网页端看到的可能存在差异\n"
    "2. 完整采集 — 4 个平台全部通过浏览器模拟真实用户访问，约 8-15 分钟。"
    "完全还原用户在网页端的真实体验，采集到的回答、引用来源和品牌提及最为准确，是深度 AEO 分析的最佳选择\n"
    "3. 重新生成问题 — 如果对当前问题不满意\n"
    "您可以回复序号，或者直接说您的想法。\n"
    "然后调用 ask_user(message='请回复序号或输入您的想法')，不要传 options 参数。"
    "不要逐条列出问题内容（UI 已经展示了）。"
    "用户选择 1 后调用 answer_fetch(fetch_mode='fast')，选择 2 后调用 answer_fetch(fetch_mode='full')。"
)


def build_orchestrator_system_prompt(state: AgentState) -> str:
    """Build dynamic system prompt based on current state."""
    data_status = []
    if state.get("brand_profile"):
        bp = state["brand_profile"]
        data_status.append(
            f"✓ 品牌信息已获取：{bp.get('brand_name', '未知')}"
            f"（{bp.get('industry', '未知行业')}）"
        )
    if state.get("competitors"):
        data_status.append(f"✓ 已识别 {len(state['competitors'])} 个竞品")
    if state.get("marketing_personas"):
        personas = state["marketing_personas"].get("user_personas", [])
        data_status.append(f"✓ 已生成 {len(personas)} 个用户画像")
    if state.get("simulated_questions"):
        qs = state["simulated_questions"].get("simulated_questions", [])
        a3_mode = state.get("user_decisions", {}).get("a3_mode", "brand")
        mode_label = {"brand": "品牌全景模式", "baseline_dynamic": "基线全景模式", "persona": "画像聚焦模式"}.get(a3_mode, "画像聚焦模式")
        data_status.append(f"✓ 已生成 {len(qs)} 组模拟问题（{mode_label}）— 用户可要求以不同模式/画像重新生成")
    if state.get("fetch_results"):
        data_status.append(
            f"✓ 已抓取 {len(state['fetch_results'])} 条AI回答"
        )
    if state.get("baseline_metrics"):
        baseline_summary = state["baseline_metrics"].get("summary_metrics", {}) if isinstance(state["baseline_metrics"], dict) else {}
        mention_rate = baseline_summary.get("brand_mention_rate")
        if isinstance(mention_rate, (int, float)):
            data_status.append(f"✓ 基线分析已完成，基线提及率={mention_rate:.1%}")
        else:
            data_status.append("✓ 基线分析已完成")
    elif state.get("brand_profile") and not state.get("baseline_questions") and not state.get("marketing_personas"):
        # Only warn about pending baseline if personas haven't been generated yet.
        # Once A2 has produced personas, the user has moved past the baseline stage.
        data_status.append("⚠ 基线分析待执行 — 必须先执行基线分析流程（question_simulation mode=baseline_dynamic → answer_fetch → data_analytics report_type=baseline）")
    if state.get("metrics"):
        summary_metrics = state["metrics"].get("summary_metrics", {}) if isinstance(state["metrics"], dict) else {}
        mention_rate = summary_metrics.get("brand_mention_rate")
        high_risk_count = summary_metrics.get("high_risk_scenario_count")
        if isinstance(mention_rate, (int, float)) and isinstance(high_risk_count, (int, float)):
            data_status.append(f"✓ 分析报告已生成，品牌提及率={mention_rate:.1%}，高风险场景={int(high_risk_count)}")
        else:
            data_status.append("✓ 分析报告已生成")

    status_text = "\n".join(data_status) if data_status else "尚无数据"

    # Entity context
    entity_info = [f"品牌名称：{state.get('brand_name', '未指定')}"]
    if state.get("official_website"):
        entity_info.append(f"官方网站：{state['official_website']}")
    if state.get("industry_hint"):
        entity_info.append(f"所属行业：{state['industry_hint']}")
    entity_context = "\n".join(entity_info)

    return f"""你是 Specta AI 的智能编排助手。你的职责是：
1. 理解用户的品牌分析需求
2. 规划分析步骤并向用户解释你的计划
3. 调用合适的分析工具执行任务
4. 汇报结果并建议下一步

当前分析状态：
{status_text}

{entity_context}

A1 完成后的流程（最高优先级）：
品牌分析（A1）完成后，你必须在消息中用自然语言向用户汇报结果并列出编号选项（如 1. 确认 2. 暂不），然后调用 ask_user 等待用户回复，不传 options 参数。
绝不直接调用 persona_generation 或 question_simulation，必须先 ask_user。之后根据是否已有基线分析决定下一步：

【情况A：尚无基线分析（baseline_metrics 为空）】
用户确认品牌信息后，必须按以下顺序执行基线分析，不可跳过：
  1. question_simulation(mode="baseline_dynamic") 生成行业全景问题
  2. answer_fetch 抓取AI平台回答
  3. data_analytics(report_type="baseline") 生成基线报告
基线分析全部完成后，在消息中用自然语言列出编号选项（包含简要说明），然后调用 ask_user 等待回复，不传 options：
  1. 开始场景细化分析（推荐）— 基于不同用户群体深入分析品牌在各场景下的AI曝光表现
  2. 重新运行基线分析 — 使用最新数据重新评估品牌在各AI平台上的基线表现
  3. 直接提问 — 针对已有数据自由提问，深入了解特定方面
⚠ 绝对不可以在基线分析完成前调用 persona_generation（A2）

【情况B：已有基线分析（baseline_metrics 已有值）】
在消息中用自然语言列出编号选项（包含简要说明），然后调用 ask_user 等待回复，不传 options：
  1. 生成用户画像，进入场景细化分析（推荐）— 基于不同用户群体深入分析品牌在各场景下的AI曝光表现
  2. 重新运行基线分析 — 使用最新数据重新评估品牌在各AI平台上的基线表现
  3. 直接提问 — 针对已有数据自由提问，深入了解特定方面

场景细化流程：用户选择"场景细化"时：persona_generation → 用户选择画像 → question_simulation(mode="persona_focused") → answer_fetch → data_analytics(report_type="persona")
重跑基线流程：用户说"重跑基线"时：跳过A1，直接 question_simulation(mode="baseline_dynamic") → answer_fetch → data_analytics(report_type="baseline")
直接提问流程：用户选择"直接提问"时，【禁止】再次调用 ask_user 给子选项。直接用自然语言回复，告诉用户可以在输入框中自由提问，并举几个他们可能感兴趣的方向作为启发（不是按钮选项）。例如：
"没问题！您可以直接在输入框中提问，比如：某个具体平台上品牌表现如何？竞品在AI搜索中的优势是什么？某类用户场景下的推荐逻辑是怎样的？——任何和品牌AEO相关的问题我都可以为您深入分析。"

行为准则：
- 始终用温暖、自然、专业的语言与用户交流，像一位真正了解品牌营销的顾问
- 在回复中说明你打算做什么（规划），然后调用对应工具
- 不要一次调用多个工具，每轮只执行一个步骤
- 执行完一个步骤后，根据步骤特性决定下一步：
  - 品牌分析（A1）完成后：见上方"A1 完成后的流程"
  - 用户画像（A2）完成后：必须调用 ask_user 引导用户在画布管道图中选择画像，不可自行决定，不可直接调用 question_simulation
  - 问题模拟（A3）完成后：必须调用 ask_user 让用户选择采集模式（快速/完整/重新生成），用户选择后根据其选择调用 answer_fetch(fetch_mode=对应模式)，不可直接调用
  - 其他步骤：直接建议或执行下一步
- 如果用户的请求不明确，用自然语言追问，不要调用 ask_user

ask_user 使用限制（非常重要）：
ask_user 只允许在以下场景使用，其他任何场景都【禁止】调用 ask_user：
  1. A1 完成后 → 确认开始基线分析
  2. 基线分析完成后 / 已有基线 → 选择下一步路径（场景细化/重跑基线/直接提问）
  3. A2 完成后 → 引导用户选择画像
  4. A3 完成后 → 让用户选择采集模式（快速采集/完整采集/重新生成问题），用户选择后才能调用 answer_fetch(fetch_mode=对应模式)
  5. 步骤执行失败 → 提供恢复选项（重试/跳过/手动输入）
除以上 5 种场景外，所有其他情况（包括闲聊、查询结果、用户提问、不确定时）都必须直接用自然语言回复，绝不调用 ask_user。用户随时可以在输入框中自由打字与你对话，不需要通过选项按钮。
- 回复风格要求（非常重要，你的回复代表品牌的专业形象）：
  - 你是一位资深品牌营销顾问，每一句话都应体现专业洞察，而不仅仅是传达状态
  - 开始执行时：先说明分析思路和价值（为什么要做这一步、能带来什么洞察），让用户理解分析的意义
  - 步骤完成后：用 3-5 句话汇报结果，必须包含至少 1 个具体的数据洞察或发现，让用户觉得"这个分析确实有价值"
  - 展示选项时：在消息中清晰列出编号选项，每个选项附一句话说明其含义和预期收益
  - 不要重复 Agent 已通过 UI 卡片展示的详细内容（如完整画像列表、品牌信息表格），但可以提炼 2-3 个关键洞察点加入对话
  - 例如好的回复：「品牌调研完成！XX品牌在YY行业中定位为ZZ，目前主要竞品有A和B。有意思的是，该品牌在AI搜索中的竞争格局与传统搜索有明显差异。接下来我将启动基线分析，看看各大 AI 搜索引擎对这个品牌的真实认知是什么。」（注意：此处XX/YY/ZZ/A/B请替换为实际数据）
  - 例如不好的回复：「品牌分析完成，共识别出 5 个竞品。」（过于简短，缺乏价值感）
  - 例如不好的回复：「好的，我来帮您设置定期监测计划。」+「确认设置 / 自定义参数」（没有解释任何内容，用户不知道要设置什么）
- 如果所有分析步骤都已完成，总结分析结果并告知用户可以做什么
- 向用户展示选项时的要求（重要）：
  - 在消息文本中用自然语言列出编号选项（1. 2. 3.），每个选项附简要说明，让用户理解每个选择的含义和区别
  - 调用 ask_user 时不传 options 参数，只传 message='请回复序号或输入您的想法'
  - 不要给出用户无法理解的选项（如"自定义参数"但不说明有哪些参数可以自定义）
  - 如果选项涉及配置（如定期监测），必须在消息中先说明默认配置是什么、有哪些可调参数、推荐配置是什么
- 如果用户直接提供了问题文本并要求抓取答案，可通过 answer_fetch 的 custom_questions 参数传入，无需先调用 question_simulation。仍需确认 fetch_mode。
- 即使已有模拟问题，如果用户要求以不同画像或模式重新生成，仍然应该再次调用 question_simulation
- 【重要】"完整模式"/"full模式"/"完整采集" 指 answer_fetch(fetch_mode="full") 的参数，不是重新生成问题。question_simulation 成功后，绝不再次调用 question_simulation，必须先调用 answer_fetch 或 ask_user。
- 如果某个Agent执行后返回"未获取到有效数据"，友好地告知用户该步骤未成功，说明可能原因，并提供建设性的替代选项。如果用户要求重试，可以再次调用同一个Agent。

绝对禁止（违反这些规则会导致严重错误）：
- 你没有实时数据，不要自行编造品牌信息、竞品数据或用户画像
- 当用户提供品牌名称时，你必须调用 brand_analysis 工具获取真实数据
- 不要在回复中直接给出"品牌分析结果"——所有分析数据必须通过工具获取
- 如果你不确定该做什么，用自然语言向用户提问澄清，不要调用 ask_user
- 不要在回复中编造具体的时间估计（如"约15秒"、"大约3分钟"、"第3/4步"等）。如需提及耗时，仅使用工具描述中给出的时间范围（如answer_fetch约8-12分钟）。其他步骤不要预估时间，使用"请稍候"即可

失败处理（重要）：
- 绝对不要提供"停止分析"或"取消分析"作为选项。我们的目标是引导用户完成分析，而不是放弃。
- 当某个步骤失败时，使用 ask_user 向用户提供以下建设性选项：
  1. 重新尝试（用不同参数或方式）
  2. 跳过此步骤继续下一步（说明替代方案，如品牌全景模式）
  3. 手动提供数据（引导用户描述所需信息，如"请描述您的目标用户群体"）
- 举例：画像生成失败时，选项应为："重新尝试生成" / "跳过，使用品牌全景模式" / "手动描述目标用户"
- 永远保持积极的态度，帮助用户找到可行方案
- 【A4 失败特别规则】answer_fetch 失败后，绝对禁止自动调用 question_simulation 重新生成问题。问题已在之前步骤生成且仍然有效，只需重试 answer_fetch 即可。必须使用 ask_user 让用户选择：重试抓取/换模式重试/仅重试部分平台。

{_build_context_summary(state)}"""


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
            summary += DIRECTIVE_A1_HAS_BASELINE if has_baseline else DIRECTIVE_A1_NO_BASELINE
            return summary
        return "品牌分析执行完成，但未获取到有效数据。"

    if tool_name == "persona_generation":
        mp = state.get("marketing_personas")
        if mp:
            personas = mp.get("user_personas", [])
            if not personas:
                return "画像生成未获取到数据，请提供建设性选项帮助用户继续。"
            persona_names = [p.get("persona_name", p.get("name", f"画像{i+1}"))
                             for i, p in enumerate(personas[:6])]
            names_str = "、".join(persona_names)
            return (
                f"用户画像生成完成，共 {len(personas)} 个画像：{names_str}。"
                f"{DIRECTIVE_A2_ASK_PATH}"
            )
        return "画像未获取到数据，请提供建设性选项帮助用户继续。"

    if tool_name == "question_simulation":
        sq = state.get("simulated_questions")
        if sq:
            qs = sq.get("simulated_questions", [])
            summary = f"问题模拟完成。共生成 {len(qs)} 组模拟问题。{DIRECTIVE_A3_NEXT_FETCH}"
            logger.info("[Orchestrator] A3 tool_result directive (first 300 chars): %s", summary[:300])
            return summary
        return (
            "问题模拟未获取到有效数据，流程中止。"
            "【强制操作】直接告知用户问题模拟失败、未能生成有效问题，"
            "并提供两个选项：1) 重试问题模拟；2) 换一种方式描述需求。"
            "不要继续调用 answer_fetch，等待用户指示。"
        )

    if tool_name == "answer_fetch":
        fr = state.get("fetch_results")
        if fr:
            return f"AI答案抓取完成。共抓取 {len(fr)} 条结果。"
        return (
            "AI答案抓取完成，但未获取到有效数据。"
            "【强制操作】你必须使用 ask_user 向用户说明抓取失败，并提供以下选项："
            "1) 重新尝试抓取（可换模式，如 fast→full）；"
            "2) 仅重试部分平台（selective_refetch）；"
            "3) 手动提供问题重新抓取。"
            "【绝对禁止】不要调用 question_simulation 重新生成问题。"
            "问题已经在之前的步骤中生成，无需重新生成。"
        )

        current_mode = state.get("analysis_mode", "persona")
        if current_mode == "baseline":
            metrics = state.get("baseline_metrics") or state.get("metrics")
        else:
            metrics = state.get("metrics")
        if metrics:
            mention_rate = float(metrics.get("mention_rate", 0) or 0) * 100
            official_citation_rate = float(metrics.get("official_citation_rate", 0) or 0) * 100
            high_risk_count = metrics.get("high_risk_scenario_count", 0)
            mode_label = "基线" if current_mode == "baseline" else "场景"
            return (
                f"{mode_label}数据分析完成。"
                f"品牌提及率：{mention_rate:.1f}％，"
                f"官网引用率：{official_citation_rate:.1f}％，"
                f"高风险场景：{high_risk_count} 个。"
            )
        return "数据分析完成，但未获取到有效数据。"

    if tool_name == "drill_down_analysis":
        reply = state.get("orchestrator_reply", "")
        return f"drill_down completed: {reply[:200]}"

    if tool_name == "compare_snapshots":
        reply = state.get("orchestrator_reply", "")
        return f"snapshot comparison completed: {reply[:200]}"

    if tool_name == "selective_refetch":
        fr = state.get("fetch_results", [])
        platforms = state.get("platform_filter") or []
        return (
            f"selective refetch completed for platforms: {', '.join(platforms)}. "
            f"{len(fr)} questions re-fetched. "
            "IMPORTANT: You MUST now call a5_analytics to re-analyze the updated "
            "data and generate a new report. Do not ask the user - proceed directly."
        )

    if tool_name == "create_monitoring_schedule":
        reply = state.get("orchestrator_reply", "")
        return f"monitoring schedule creation completed: {reply[:200]}"

    return f"工具 {tool_name} 执行完成。"


def _get_tool_name_from_node(node_name: str) -> str | None:
    """Reverse lookup: node name → tool name."""
    node_to_tool = {v: k for k, v in TOOL_TO_NODE.items()}
    return node_to_tool.get(node_name)


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
    defense_msg = "问题模拟已完成，请选择采集模式："
    await manager.emit_to_session(
        session_id,
        "inline_confirmation",
        {
            "message": defense_msg,
            "options": defense_options,
            "type": "simple",
        },
    )
    await manager.emit_to_session(session_id, "confirmation_request", {
        "request_id": request_id,
        "type": "step_confirmation",
        "message": defense_msg,
        "options": defense_options,
        "allow_text_input": True,
        "step_id": "orchestrator",
        "step_name": "选择采集模式",
    })

    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["fetch_mode_pending"] = True
    new_history.append({
        "role": "tool",
        "content": "等待用户选择采集模式...",
        "tool_call_id": request_id,
    })
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


# =============================================================================
# Tool Call → Node Mapping
# =============================================================================

TOOL_TO_NODE: dict[str, str] = {
    "brand_analysis": "a1_brand",
    "persona_generation": "a2_persona",
    "question_simulation": "a3_question",
    "data_analytics": "a5_analytics",
    # Follow-up tools (Cycle 3)
    "drill_down_analysis": "drill_down",
    "compare_snapshots": "compare_snapshots",
    "selective_refetch": "selective_refetch",
    # Monitoring tools (Cycle 4)
    "create_monitoring_schedule": "create_monitoring",
}

TOOL_DISPLAY_NAMES: dict[str, str] = {
    "brand_analysis": "品牌竞品分析",
    "persona_generation": "用户画像生成",
    "question_simulation": "问题模拟生成",
    "answer_fetch": "AI答案抓取",
    "data_analytics": "数据分析报告",
    # Follow-up tools (Cycle 3)
    "drill_down_analysis": "深入分析",
    "compare_snapshots": "快照对比",
    "selective_refetch": "选择性重新抓取",
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
            last_content = last_msg.get("content", "") if last_msg.get("role") == "user" else ""
            if any(kw in last_content for kw in retry_keywords):
                retry_detected = True

    if retry_detected:
        logger.info("[Orchestrator] User retry intent detected, resetting agent_retry_counts")
        state = {**state, "agent_retry_counts": {}}

    current_retry_counts = dict(state.get("agent_retry_counts", {}) or {})

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
        all_done = (completed_count + skipped_count) == total_count and not is_baseline_phase
        from app.workflow.events import send_progress_event
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

    # Build orchestrator call
    system_prompt = build_orchestrator_system_prompt(state)
    messages = build_orchestrator_messages(state)
    tools = build_agent_tools()

    # Stream LLM response
    model = get_llm_model()

    reply_text = ""
    thinking_text = ""
    tool_call_result = None
    is_first_reply_chunk = True
    last_finish_reason: str | None = None

    try:
        async for chunk in async_wrap_sync_gen(lambda: model.stream(
            messages=[
                {"role": "system", "content": system_prompt},
                *messages,
            ],
            tools=tools,
            temperature=0.3,
            tool_choice="auto",
        )):
            # Tool calls arrive at end of stream.
            # IMPORTANT: The final chunk with tool_calls also contains the
            # full accumulated content_buffer and reasoning_buffer (not deltas),
            # so we must skip content/thinking processing for that chunk.
            if chunk.finish_reason:
                last_finish_reason = chunk.finish_reason
            if chunk.tool_calls:
                tool_call_result = chunk.tool_calls[0]
                continue

            # Stream main reply (Layer 1)
            if chunk.content:
                reply_text += chunk.content
                await send_reply_event(
                    session_id, chunk.content, is_delta=True,
                    is_new_round=is_first_reply_chunk,
                )
                is_first_reply_chunk = False

            # Stream thinking process
            if chunk.thinking_blocks:
                for block in chunk.thinking_blocks:
                    if block.text:
                        thinking_text += block.text
                        await send_thought_event(
                            session_id, block.text, is_delta=True
                        )

        # Mark reply as complete
        await send_reply_event(session_id, "", is_complete=True)

        if thinking_text:
            await send_thought_event(session_id, "", is_complete=True)

        # Check finish_reason for abnormal termination
        if last_finish_reason == "sensitive":
            logger.warning("[Orchestrator] Response blocked by content safety filter")
            from app.workflow.events import send_error_event
            await send_error_event(
                session_id, "orchestrator", "内容被安全审核拦截，请调整输入后重试", recoverable=True
            )
        elif last_finish_reason == "length":
            logger.warning("[Orchestrator] Response truncated due to max_tokens")
            from app.workflow.events import send_error_event
            await send_error_event(
                session_id, "orchestrator",
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
            assistant_msg["tool_calls"] = [{
                "id": tool_call_result.id or "call_1",
                "type": "function",
                "function": {
                    "name": tool_call_result.name,
                    "arguments": json.dumps(
                        tool_call_result.arguments, ensure_ascii=False
                    ),
                },
            }]
        new_history.append(assistant_msg)

        if tool_call_result:
            return await _handle_tool_call(
                state, session_id, tool_call_result, reply_text, new_history
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
                state=state,
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
            error_msg = error_info.get("error", "未知错误")
            logger.warning(
                f"[Orchestrator] Error state detected (step={failed_step}), "
                f"redirecting to user confirmation instead of END"
            )
            await send_confirmation_request(
                session_id=session_id,
                step_id="error_recovery",
                step_name=f"{failed_step} 执行失败",
                message=(
                    f"步骤 {failed_step} 执行遇到问题：{error_msg[:100]}。"
                    f"请选择后续操作："
                ),
                options=[
                    {
                        "id": "retry",
                        "label": "重新尝试",
                        "description": f"再次执行 {failed_step}",
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
                        "step_name": f"{failed_step} 执行失败",
                        "message": f"步骤 {failed_step} 执行遇到问题",
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
        # Hard filter: remove any "stop/cancel" options
        BANNED_KEYWORDS = ["停止", "取消", "放弃", "终止"]
        options = [
            opt for opt in options
            if not any(kw in (opt.get("label", "") + opt.get("description", "")) for kw in BANNED_KEYWORDS)
        ]

        # ---- Headless mode: auto-confirm with first option, skip wait ----
        if state.get("headless_mode"):
            auto_choice = options[0] if options else {"id": "confirm", "label": "确认"}
            auto_reply = f"[自动确认] {auto_choice.get('label', '确认')}"
            logger.info(
                "[Orchestrator] Headless mode: auto-confirming ask_user "
                "with option '%s'", auto_choice.get("id"),
            )
            # Inject tool result with auto-confirm into history
            new_history.append({
                "role": "tool",
                "content": auto_reply,
                "tool_call_id": tool_call.id or "call_1",
            })
            # Append user message so orchestrator sees the "reply"
            new_history.append({
                "role": "user",
                "content": auto_reply,
            })
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
            and state.get("simulated_questions")
            and _get_tool_name_from_node(state.get("next_action", "") or "") == "question_simulation"
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
        await manager.emit_to_session(session_id, "inline_confirmation", payload)

        # Also emit confirmation_request so SelectionContent's pendingConfirmation
        # guard is satisfied — that component reads pendingConfirmation.requestId
        # which is only set by the setPendingConfirmation handler, triggered by this
        # separate event. Both events are required: inline_confirmation drives the
        # per-message UI layer, confirmation_request drives the store-level guard.
        await manager.emit_to_session(session_id, "confirmation_request", {
            "request_id": request_id,
            "type": "step_confirmation",
            "message": msg,
            "options": options,
            "allow_text_input": True,
            "step_id": "orchestrator",
            "step_name": "等待用户确认",
        })

        # Add tool result placeholder to history
        new_history.append({
            "role": "tool",
            "content": "等待用户回复...",
            "tool_call_id": tool_call.id or "call_1",
        })

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

    node_name = TOOL_TO_NODE.get(tool_name)
    if node_name:
        display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)

        # Hard block: when simulated_questions already exist, block re-invocation
        # unless the user just triggered a retry (retry_counts reset to 0).
        if tool_name == "question_simulation" and state.get("simulated_questions"):
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
                new_history.append({
                    "role": "tool",
                    "content": block_msg,
                    "tool_call_id": tool_call.id or "call_1",
                    "name": tool_name,
                })
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
        current_count = retry_counts.get(tool_name, 0)
        if current_count >= 2:
            logger.warning(
                f"[Orchestrator] Tool {tool_name} already called {current_count} times, blocking retry"
            )
            # Inject a tool_result error into history so LLM knows to offer alternatives
            error_msg = (
                f"{display_name}已尝试执行 {current_count} 次但未成功。"
                f"请使用 ask_user 向用户提供建设性替代选项："
                f"1) 跳过此步骤继续下一步 2) 手动提供所需数据 3) 用不同参数再次尝试。"
                f"绝对不要提供'停止分析'或'取消分析'选项。"
            )
            new_history.append({
                "role": "tool",
                "content": error_msg,
                "tool_call_id": tool_call.id or "call_1",
                "name": tool_name,
            })
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
        retry_counts[tool_name] = current_count + 1

        # Send progress event with steps
        from app.workflow.events import send_progress_event
        tool_to_step_id = {
            "brand_analysis": "A1",
            "persona_generation": "A2",
            "question_simulation": "A3",
            "answer_fetch": "A4",
            "data_analytics": "A5",
        }
        workflow_steps = _build_workflow_steps(state)
        current_step_id = tool_to_step_id.get(tool_name)
        for s in workflow_steps:
            if s["id"] == current_step_id:
                s["status"] = "in_progress"
        completed_count = sum(1 for s in workflow_steps if s["status"] == "completed")
        total_count = len(workflow_steps)
        await send_progress_event(
            session_id,
            step=tool_name,
            step_name=display_name,
            progress=completed_count / total_count,
            message=f"正在执行：{display_name}",
            status="running",
            steps=workflow_steps,
        )

        # Fallback: if LLM produced no reply text, emit a short status line
        # so the user sees something before the long-running agent starts.
        if not reply_text.strip():
            _all_names = "、".join(
                PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
                for p in PlatformConstants.SUPPORTED_PLATFORMS
            )
            _current_fetch_mode = tool_args.get("fetch_mode", "fast") if tool_name == "answer_fetch" else state.get("fetch_mode", "fast")
            if _current_fetch_mode == "full":
                _fetch_fallback = (
                    f"正在向{_all_names}平台提问（完整采集模式，全浏览器），抓取各平台对品牌的真实回答。"
                    f"4 条浏览器流水线并行，预计总耗时约 10-20 分钟。"
                    "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
                )
            else:
                _api_names = "/".join(
                    PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
                    for p in PlatformConstants.API_PLATFORMS
                )
                _browser_names = "/".join(
                    PlatformConstants.PLATFORM_DISPLAY_NAMES[p]
                    for p in PlatformConstants.BROWSER_PLATFORMS
                )
                _fetch_fallback = (
                    f"正在向{_all_names}平台提问，抓取各平台对品牌的真实回答。"
                    f"API 平台（{_api_names}）并行抓取约 30 秒，"
                    f"浏览器平台（{_browser_names}）各需 3-5 分钟，总计约 8-12 分钟。"
                    "请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。"
                )
            FALLBACK_TEXTS = {
                "brand_analysis": "正在收集品牌基本信息和竞品格局，请稍候...",
                "persona_generation": "正在根据品牌特征生成用户画像，请稍候...",
                "question_simulation": "正在模拟真实用户可能在 AI 搜索中提出的问题，请稍候...",
                "answer_fetch": _fetch_fallback,
                "data_analytics": "正在整理场景、风险与优先动作建议，请稍候…",
            }
            fallback_text = FALLBACK_TEXTS.get(tool_name, f"正在执行：{display_name}，请稍候...")
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
            step=tool_name,
            is_complete=False,
        )

        # Pass brand_name from tool_args if brand_analysis
        extra_updates: dict[str, Any] = {}
        if tool_name == "brand_analysis" and tool_args.get("brand_name"):
            extra_updates["brand_name"] = tool_args["brand_name"]

        # Store user_decisions for a3 mode
        if tool_name == "question_simulation":
            user_decisions = dict(state.get("user_decisions", {}))
            # Reset fetch_mode guard flags when re-running A3
            user_decisions.pop("fetch_mode_confirmed", None)
            user_decisions.pop("fetch_mode_pending", None)
            mode = tool_args.get("mode", "")

            if mode == "baseline_dynamic":
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
                defense_msg = "请选择问题模拟的分析路径："
                await manager.emit_to_session(
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
                await manager.emit_to_session(session_id, "confirmation_request", {
                    "request_id": defense_request_id,
                    "type": "step_confirmation",
                    "message": defense_msg,
                    "options": ask_options,
                    "allow_text_input": True,
                    "step_id": "orchestrator",
                    "step_name": "选择分析路径",
                })
                # Inject tool_result placeholder so MiniMax history stays consistent
                new_history.append({
                    "role": "tool",
                    "content": "等待用户选择分析路径...",
                    "tool_call_id": tool_call.id or "call_1",
                })
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
        if tool_name == "answer_fetch":
            extra_updates["fetch_mode"] = tool_args.get("fetch_mode", "fast")

            # Fix 2B: Inject custom_questions into state as questions
            custom_qs = tool_args.get("custom_questions")
            if custom_qs and isinstance(custom_qs, list):
                formatted = [
                    {"id": f"custom_{i+1}", "text": q, "category": "用户自定义"}
                    for i, q in enumerate(custom_qs)
                    if isinstance(q, str) and q.strip()
                ]
                if formatted:
                    extra_updates["questions"] = formatted

            # Fix 3: Code-level guard — force fetch_mode confirmation
            # Skip guard when:
            #   - LLM explicitly passed fetch_mode (user intent is clear)
            #   - custom_questions provided
            #   - headless mode
            #   - already confirmed/pending
            user_decisions = dict(state.get("user_decisions", {}))
            has_questions = bool(state.get("questions")) or bool(custom_qs)
            is_headless = state.get("headless", False)
            already_confirmed = user_decisions.get("fetch_mode_confirmed", False)
            already_pending = user_decisions.get("fetch_mode_pending", False)
            is_custom = bool(custom_qs and isinstance(custom_qs, list) and any(
                isinstance(q, str) and q.strip() for q in custom_qs
            ))
            # If LLM explicitly set fetch_mode in tool args, the user's intent
            # has already been captured — no need to re-ask.
            explicit_mode = bool(tool_args.get("fetch_mode"))

            if (
                has_questions
                and not is_headless
                and not already_confirmed
                and not already_pending
                and not is_custom
                and not explicit_mode
            ):
                # LLM called answer_fetch without specifying fetch_mode — force selection
                logger.warning(
                    "[Orchestrator] answer_fetch called without explicit fetch_mode. "
                    "Forcing user selection."
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
                defense_msg = "问题模拟已完成，请选择采集模式："
                await manager.emit_to_session(
                    session_id,
                    "inline_confirmation",
                    {
                        "message": defense_msg,
                        "options": defense_options,
                        "type": "simple",
                    },
                )
                await manager.emit_to_session(session_id, "confirmation_request", {
                    "request_id": defense_request_id,
                    "type": "step_confirmation",
                    "message": defense_msg,
                    "options": defense_options,
                    "allow_text_input": True,
                    "step_id": "orchestrator",
                    "step_name": "选择采集模式",
                })
                # Mark pending so next call passes through
                user_decisions["fetch_mode_pending"] = True
                # Inject tool_result placeholder for MiniMax history consistency
                new_history.append({
                    "role": "tool",
                    "content": "等待用户选择采集模式...",
                    "tool_call_id": tool_call.id or "call_1",
                })
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

            # If pending (guard fired once), mark as confirmed and proceed
            if already_pending and not already_confirmed:
                user_decisions["fetch_mode_confirmed"] = True
                extra_updates["user_decisions"] = user_decisions

        # Pass report_type as analysis_mode for A5
        if tool_name == "data_analytics":
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
