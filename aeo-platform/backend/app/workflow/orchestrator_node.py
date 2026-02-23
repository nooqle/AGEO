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
            "耗时较长（5-10分钟），需要先完成问题模拟。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要抓取的平台列表（可选，默认全部）",
                },
            },
        },
    },
    {
        "name": "data_analytics",
        "description": (
            "基于抓取结果计算品牌可见度指标（BWVS）并生成分析报告。"
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
            "【重要】不要直接调用此工具。你必须先使用 ask_user 向用户展示即将设置的参数摘要"
            "（包括品牌名称、监测频率、执行时间、告警阈值），等用户明确确认后再调用此工具。"
            "示例确认消息：'我将为「小米」设置每周监测，每周一上午11:00执行，"
            "BWVS变化超过10分时通知您。确认设置？'"
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
                    "description": "BWVS 变化告警阈值（绝对值），默认 10.0",
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
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "要重新抓取的平台列表: 'kimi', 'deepseek', 'doubao', 'hunyuan'",
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
                    "description": "等待提示（仅在用户确认后将立即执行耗时操作时提供，如AI答案抓取预计5-10分钟。普通确认或选择场景不要填写此字段）",
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
        parts.append(f"- BWVS分数: {m.get('bwvs_index', 'N/A')}")

    if state.get("baseline_metrics"):
        bm = state["baseline_metrics"]
        parts.append(f"- 基线 BWVS: {bm.get('bwvs_index', 'N/A')}")
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
    "【强制操作】你必须先用一句话向用户汇报品牌分析结果，"
    "然后立即调用 ask_user 工具让用户选择下一步。"
    "选项包含：1) 生成用户画像，进入场景细化分析(推荐) "
    "2) 重新运行基线分析 3) 直接提问。"
    "不要跳过 ask_user，不要自行决定下一步。"
)

DIRECTIVE_A1_NO_BASELINE = (
    "【强制操作】该品牌尚无基线分析，你必须先用一句话向用户汇报品牌分析结果，"
    "然后立即调用 ask_user 工具展示品牌信息让用户确认。"
    "用户确认后，必须执行基线分析流程："
    "question_simulation(mode='baseline_dynamic') → answer_fetch → "
    "data_analytics(report_type='baseline')。"
    "不要跳过基线分析，不要直接调用 persona_generation。"
)

DIRECTIVE_A2_ASK_PATH = (
    "【强制操作】你必须立即调用 ask_user 工具，让用户选择问题模拟路径。"
    "选项必须包含：1) id='persona_focused' label='聚焦画像分析' "
    "description='从已生成画像中选择重点分析'，"
    "2) id='brand_panorama' label='品牌全景分析' "
    "description='覆盖所有用户群体，不针对特定画像'。"
    "不要调用 question_simulation，不要自行决定模式，必须等用户选择后再继续。"
)

DIRECTIVE_A3_NEXT_FETCH = (
    "【强制操作】用 2-3 句话友好地向用户说明问题已生成（可提及问题数量、覆盖的主题方向），"
    "然后直接调用 answer_fetch 工具执行下一步，不要询问用户。"
    "不要逐条列出问题内容（UI 已经展示了），重点说明接下来 answer_fetch 的意义。"
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
        bwvs = state["baseline_metrics"].get("bwvs_index", 0)
        data_status.append(f"✓ 基线分析已完成，基线BWVS={bwvs:.1f}")
    elif state.get("brand_profile") and not state.get("baseline_questions"):
        data_status.append("⚠ 基线分析待执行 — 必须先执行基线分析流程（question_simulation mode=baseline_dynamic → answer_fetch → data_analytics report_type=baseline）")
    if state.get("metrics"):
        bwvs = state["metrics"].get("bwvs_index", 0)
        data_status.append(f"✓ 分析报告已生成，BWVS={bwvs:.1f}")

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
品牌分析（A1）完成后，你必须立即调用 ask_user，使用以下固定消息请求用户确认开始基线分析（不要展示品牌信息，不要自行改写消息内容）：
消息："品牌与竞品信息已调研完毕，接下来，我将做一次品牌的基线公域大模型分析，这个分析会自动持续化运行较长时间，请你确认。"
选项：确认，开始分析（推荐）/ 取消
绝不直接调用 persona_generation 或 question_simulation，必须先 ask_user。之后根据是否已有基线分析决定下一步：

【情况A：尚无基线分析（baseline_metrics 为空）】
用户确认品牌信息后，必须按以下顺序执行基线分析，不可跳过：
  1. question_simulation(mode="baseline_dynamic") 生成行业全景问题
  2. answer_fetch 抓取AI平台回答
  3. data_analytics(report_type="baseline") 生成基线报告
基线分析全部完成后，用 ask_user(type="guided") 展示引导选项：
  选项A: 开始场景细化分析(推荐) / 选项B: 重新运行基线分析 / 选项C: 直接提问
⚠ 绝对不可以在基线分析完成前调用 persona_generation（A2）

【情况B：已有基线分析（baseline_metrics 已有值）】
用 ask_user 展示选项：
  选项A: 生成用户画像，进入场景细化分析(推荐) / 选项B: 重新运行基线分析 / 选项C: 直接提问

场景细化流程：用户选择"场景细化"时：persona_generation → 用户选择画像 → question_simulation(mode="persona_focused") → answer_fetch → data_analytics(report_type="persona")
重跑基线流程：用户说"重跑基线"时：跳过A1，直接 question_simulation(mode="baseline_dynamic") → answer_fetch → data_analytics(report_type="baseline")

行为准则：
- 始终用温暖、自然、专业的语言与用户交流，像一位真正了解品牌营销的顾问
- 在回复中说明你打算做什么（规划），然后调用对应工具
- 如果某个步骤需要用户确认或选择，使用 ask_user 工具
- 不要一次调用多个工具，每轮只执行一个步骤
- 执行完一个步骤后，根据步骤特性决定下一步：
  - 品牌分析（A1）完成后：见上方"A1 完成后的流程"
  - 用户画像（A2）完成后：必须调用 ask_user 让用户选择分析路径（聚焦画像 or 品牌全景），不可自行决定，不可直接调用 question_simulation
  - 问题模拟（A3）完成后：直接建议执行 answer_fetch
  - 其他步骤：直接建议或执行下一步
- 如果用户的请求不明确，先询问再行动
- 回复风格要求（重要）：
  - 开始执行时：用 2-3 句话说明你的分析计划和思路，让用户感受到专业感（而非"开始执行"这种干巴巴的话）
  - 步骤完成后：用 2-4 句话友好地汇报结果的亮点或意义，让用户理解数据价值，而不仅仅是"已完成"
  - 不要重复 Agent 已通过 UI 卡片展示的详细内容（如完整画像列表、品牌信息表格），但可以提炼 1-2 个关键洞察点加入对话
  - 例如好的回复（仅作格式参考，数据请从实际结果中提取）：「品牌调研完成！这个品牌在细分领域有独特定位，竞争格局也比较清晰。接下来我将启动基线分析，看看各大 AI 搜索引擎对这个品牌的真实认知是什么。」
  - 例如不好的回复：「品牌分析完成，共识别出 5 个竞品。」（过于简短，缺乏价值感）
- 如果所有分析步骤都已完成，总结分析结果并告知用户可以做什么
- 即使已有模拟问题，如果用户要求以不同画像或模式重新生成，仍然应该再次调用 question_simulation
- 如果某个Agent执行后返回"未获取到有效数据"，友好地告知用户该步骤未成功，说明可能原因，并提供建设性的替代选项。如果用户要求重试，可以再次调用同一个Agent。

绝对禁止（违反这些规则会导致严重错误）：
- 你没有实时数据，不要自行编造品牌信息、竞品数据或用户画像
- 当用户提供品牌名称时，你必须调用 brand_analysis 工具获取真实数据
- 不要在回复中直接给出"品牌分析结果"——所有分析数据必须通过工具获取
- 如果你不确定该做什么，调用 ask_user 询问用户，而不是自己猜测

失败处理（重要）：
- 绝对不要提供"停止分析"或"取消分析"作为选项。我们的目标是引导用户完成分析，而不是放弃。
- 当某个步骤失败时，使用 ask_user 向用户提供以下建设性选项：
  1. 重新尝试（用不同参数或方式）
  2. 跳过此步骤继续下一步（说明替代方案，如品牌全景模式）
  3. 手动提供数据（引导用户描述所需信息，如"请描述您的目标用户群体"）
- 举例：画像生成失败时，选项应为："重新尝试生成" / "跳过，使用品牌全景模式" / "手动描述目标用户"
- 永远保持积极的态度，帮助用户找到可行方案

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
            return f"问题模拟完成。共生成 {len(qs)} 组模拟问题。{DIRECTIVE_A3_NEXT_FETCH}"
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
        return "AI答案抓取完成，但未获取到有效数据。"

    if tool_name == "data_analytics":
        current_mode = state.get("analysis_mode", "persona")
        if current_mode == "baseline":
            metrics = state.get("baseline_metrics") or state.get("metrics")
        else:
            metrics = state.get("metrics")
        if metrics:
            bwvs = metrics.get("bwvs_index", 0)
            mode_label = "基线" if current_mode == "baseline" else "场景"
            return (
                f"{mode_label}数据分析完成。BWVS指数：{bwvs:.1f}，"
                f"总提及率：{metrics.get('mention_rate', 0):.1%}。"
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


def build_orchestrator_messages(state: AgentState) -> list[dict[str, Any]]:
    """Build message history for the orchestrator LLM call.

    If the last message in history is an assistant message with tool_calls
    but no matching tool result, inject one from the agent's output in state.
    """
    history = state.get("orchestrator_history", [])
    if not history:
        # First call: use the user's original message
        brand_name = state.get("brand_name", "")
        return [{"role": "user", "content": f"请帮我分析品牌：{brand_name}"}]

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
    "answer_fetch": "a4_fetch",
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
                },
            )

        confirm_type = tool_args.get("type", "simple")
        waiting_tips = tool_args.get("waiting_tips", [])
        checklist = tool_args.get("checklist", [])

        # Enhanced inline confirmation with type, tips, and checklist
        request_id = tool_call.id or f"ask_user_{id(tool_call)}"
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
            "allow_text_input": False,
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
            },
        )

    node_name = TOOL_TO_NODE.get(tool_name)
    if node_name:
        display_name = TOOL_DISPLAY_NAMES.get(tool_name, tool_name)

        # Check retry count — block if same tool called >= 2 times
        retry_counts = dict(state.get("agent_retry_counts", {}) or {})
        current_count = retry_counts.get(tool_name, 0)
        if current_count >= 3:
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
            FALLBACK_TEXTS = {
                "brand_analysis": "正在收集品牌基本信息和竞品格局，请稍候...",
                "persona_generation": "正在根据品牌特征生成用户画像，请稍候...",
                "question_simulation": "正在模拟真实用户可能在 AI 搜索中提出的问题，通常需要 10-20 秒...",
                "answer_fetch": "正在向豆包、混元、Kimi、DeepSeek 四个平台提问，抓取各平台对品牌的真实回答。此过程约需 15 分钟，请保持页面打开，可以切换到其他标签页做别的事，完成后将自动继续。",
                "data_analytics": "正在分析各平台回答数据，计算品牌曝光率、情感分布和 BWVS 指数，即将完成...",
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
            mode = tool_args.get("mode", "")

            if mode == "baseline_dynamic":
                # Baseline mode: set directly, no user confirmation needed
                user_decisions["a3_mode"] = "baseline_dynamic"
                extra_updates["user_decisions"] = user_decisions
                extra_updates["analysis_mode"] = "baseline"
            elif "a3_mode" in user_decisions:
                pass  # User already chose via confirmation — never override
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
                    "allow_text_input": False,
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
                    },
                )
            if tool_args.get("persona_id"):
                user_decisions["selected_persona_ids"] = [tool_args["persona_id"]]
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
