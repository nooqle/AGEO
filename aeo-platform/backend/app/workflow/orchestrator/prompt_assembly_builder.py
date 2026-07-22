"""Orchestrator prompt assembly construction (Phase B close)."""

from __future__ import annotations

from textwrap import dedent
from typing import Any, Mapping

from app.workflow.orchestrator_context_packets import (
    build_orchestrator_context_packets,
    render_active_skill_packet,
    render_dashboard_context_packet,
    render_entity_context_packet,
    render_history_availability_packet,
    render_ontology_action_plan_packet,
    render_ontology_world_packet,
    render_pending_decision_packet,
    render_session_status_packet,
)
from app.workflow.orchestrator_instruction_defense import (
    INSTRUCTION_SECURITY_POLICY,
    build_instruction_defense_context,
    render_instruction_defense_reminder,
)
from app.workflow.prompt_assembly import PromptAssembly, PromptSection
from app.workflow.orchestrator.knowledge_fallback import (
    _build_knowledge_planning_hint,
)
from app.workflow.orchestrator.misc_pure import _build_static_public_skill_index
from app.workflow.orchestrator.prompt_bundle import (
    OrchestratorPromptBundle,
    _build_orchestrator_prompt_bundle_from_assembly,
)
from app.workflow.orchestrator.prompt_context import (
    _build_context_summary,
    _build_contextual_tool_surface_note,
    _build_public_skill_index,
)
from app.workflow.orchestrator.prompt_evidence import (
    _render_recent_evidence_for_prompt,
    _should_render_history_availability,
    _should_render_instruction_defense,
)
from app.workflow.orchestrator.session_tool_surface import (
    _get_contextual_hidden_tool_names,
)
from app.workflow.orchestrator.text_normalize import _compact_text

def build_orchestrator_prompt_assembly(state: Mapping[str, Any]) -> PromptAssembly:
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
    dashboard_context = render_dashboard_context_packet(
        context_packets.dashboard_context
    )
    pending_decision = render_pending_decision_packet(context_packets.pending_decision)
    ontology_world = render_ontology_world_packet(context_packets.ontology_world)
    ontology_action_plan = render_ontology_action_plan_packet(
        context_packets.ontology_action_plan
    )
    recent_evidence = _render_recent_evidence_for_prompt(
        context_packets.recent_evidence
    )
    context_summary = _compact_text(_build_context_summary(state), 500)
    knowledge_hint = _build_knowledge_planning_hint(state)
    contextual_tool_surface_note = _build_contextual_tool_surface_note(state)
    dynamic_public_skill_index = _build_public_skill_index(state)
    static_public_skill_index = _build_static_public_skill_index()
    instruction_defense = (
        render_instruction_defense_reminder(
            build_instruction_defense_context(state, context_packets.recent_evidence)
        )
        if _should_render_instruction_defense(state, context_packets.recent_evidence)
        else ""
    )

    def _default_section_metadata(group: str) -> dict[str, Any]:
        if group == "base_policy_sections":
            return {
                "cache_layer": "static_policy",
                "volatility": "release_static",
                "source": "orchestrator_policy",
            }
        if group == "skill_sections":
            return {
                "cache_layer": "static_skill_surface",
                "volatility": "deployment_static",
                "source": "skill_registry",
            }
        if group == "runtime_context_sections":
            return {
                "cache_layer": "dynamic_context",
                "volatility": "per_turn",
                "source": "agent_state",
            }
        if group == "runtime_reminder_sections":
            return {
                "cache_layer": "ephemeral_runtime_guard",
                "volatility": "per_turn",
                "source": "runtime_policy",
            }
        return {
            "cache_layer": "unknown",
            "volatility": "unspecified",
            "source": "",
        }

    def _section(
        *,
        key: str,
        title: str,
        body: str | None,
        group: str,
        priority: int,
        drop_policy: str = "compress",
        budget_cost: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> PromptSection:
        section_metadata = _default_section_metadata(group)
        section_metadata.update(metadata or {})
        return PromptSection(
            key=key,
            title=title,
            body=body or "",
            group=group,
            priority=priority,
            drop_policy=drop_policy,
            budget_cost=budget_cost,
            metadata=section_metadata,
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
                - A1 完成后，优先先汇报结果；如果用户还没有明确下一步，再用 ask_user 帮助其做选择，而不是默认直接调用 persona_generation 或 question_simulation。
                - A1 后调用 ask_user 时，选项 id 必须使用固定值：panorama 或 panorama_fast 或 panorama_full（品牌全景分析）、persona_first（先做用户画像/场景细化）、ask（直接提问）。不要自创 continue_panorama、scenario_first、ask_questions 这类新 id。
                - 尚无品牌全景分析时，默认优先按 question_simulation(mode="baseline_dynamic") -> answer_fetch -> analysis_report_skill(report_type="panorama") 推进，但仍要尊重用户当前意图。
                - 已有品牌全景分析时，用户可进入引用置信度评估、场景细化、重跑品牌全景分析或直接提问。

                场景细化流程：
                - 用户选择场景细化时：persona_generation -> 用户选择画像 -> question_simulation(mode="persona_focused") -> answer_fetch -> analysis_report_skill(report_type="scenario")。
                - 如果用户明确要求“以某个身份 / 职业 / 角色生成问题”，仍调用 question_simulation，并通过 identity 传入该身份；若用户未明确要求，默认消费者视角，不要擅自加身份。
                - 如果用户明确要求围绕关键词、主题或概念生成“全景问题 / 问题集 / 用户关心的问题”，调用 question_simulation(mode="baseline_dynamic", topic_keywords=[用户给出的关键词], topic_description=用户原始需求)。这类请求可以没有品牌档案，不要先强制调用 brand_analysis，也不要把关键词当成品牌名。
                - 如果用户只要求“生成/重新生成/模拟问题”，question_simulation 必须传 question_only=true；完成 A3 后停止在问题列表，不自动调用 answer_fetch，也不自动生成报告。

                其他固定路径：
                - 用户说“重跑品牌全景分析”时：question_simulation(mode="baseline_dynamic") -> answer_fetch -> analysis_report_skill(report_type="panorama")。
                - 用户明确要检查引用可信度时：confidence_analysis_skill。
                - 用户基于已有结果要求深入分析、历次对比、解释原因、提炼风险时：post_analysis_skill。
                - 用户要求重新抓取、重跑部分平台、全量重跑、或从 API 改为浏览器模式时：统一走 answer_fetch，不要再发明 refetch 类能力名。
                - 用户选择“直接提问”时，禁止再次 ask_user 给子选项；直接自然语言引导用户在输入框中继续追问。
                - 只有用户明确在问过往资料、历史月份、导出记录、最近两次变化时，才优先考虑 knowledge_*。
                - 围绕过往品牌/竞品/回答/引用时，优先考虑 knowledge_lookup；围绕过往汇总时，优先考虑 knowledge_aggregate；明确导出时，优先考虑 knowledge_export；比较最近两轮变化时，优先考虑 knowledge_compare。
                - 当用户在问“上一轮 / 最近一轮 / 上次抓取”的成功率、失败数、失败平台、失败问题或补采对象时，不能直接复述历史对话里的旧数字；必须先调用 knowledge_aggregate 或 knowledge_lookup 刷新权威结果，再回复。
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
                - 如果用户只是闲聊，或当前意图不属于任何工具合同，直接使用你的大模型对话能力自然语言回复，不调用工具，也不要为了凑流程而调用 ask_user。
                - 画像生成完成后，若用户尚未明确后续范围，优先 ask_user 引导其选画像；问题生成完成后，若用户尚未明确采集模式，优先 ask_user 请求确认；答案抓取完成后通常继续进入 analysis_report_skill，但如果最新 A4 observation 明确要求用户先做选择（例如补采后仍有失败项），必须先 ask_user，再决定是否进入 analysis_report_skill；分析报告完成后，若用户尚未明确下一步，再 ask_user 帮助其决定是否做引用置信度评估或继续后续分析。
                - 如果用户请求不明确，用自然语言追问，不要调用 ask_user。
                - 步骤完成后的回复应包含 1 个具体数据点或风险发现，不要只报“完成了”。
                - 如果用户直接提供问题文本并要求抓取答案，可通过 answer_fetch 的 custom_questions 传入，无需先调用 question_simulation，但仍需明确 fetch_mode。
                - “完整模式/full 模式/完整采集”指 answer_fetch(fetch_mode="full")，不是重新生成问题。question_simulation 完成后，应先 answer_fetch 或 ask_user，不要再次 question_simulation。
                - 当条件不足、步骤失败或路由受限时，不要只说“无法完成/不能执行”；必须同时说明原因，并给出至少一个可执行的下一步方案。

                ask_user 使用限制：
                - 只允许在表格导入确认、品牌/竞品识别后确认基线、基线或分析报告完成后选下一步、画像生成后选画像、问题生成后选采集模式、答案抓取后需确认是否补采剩余失败项、步骤失败恢复这几类场景使用。
                - 除这些场景外，所有其他情况都直接自然语言回复，绝不调用 ask_user。
                - 调用 ask_user 时必须显式传入 message 和 options。对于答案抓取后的补采确认，必须提供“补采失败项（浏览器）/继续补采剩余失败项（浏览器）”与“先用当前结果继续分析”这类明确选项。
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
                - 当用户首次提供品牌名称且系统没有足够过往事实时，必须调用 brand_analysis 获取真实数据。
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
                    metadata={
                        "static_prompt": False,
                        "cache_layer": "dynamic_tool_surface",
                        "volatility": "per_turn",
                        "source": "tool_surface_gate",
                    },
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
            body=dynamic_public_skill_index,
            metadata={
                "static_body": static_public_skill_index,
                "runtime_body": dynamic_public_skill_index,
                "static_cache_layer": "static_skill_surface",
                "runtime_cache_layer": "dynamic_tool_surface",
                "runtime_priority": 9,
                "runtime_drop_policy": "compress",
                "source": "skill_registry",
            },
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
                metadata={
                    "cache_layer": "dynamic_session_state",
                    "source": "agent_state.session_status",
                },
            ),
            _section(
                key="entity_context",
                title="实体上下文",
                group="runtime_context_sections",
                priority=1,
                body=entity_context,
                metadata={
                    "cache_layer": "dynamic_entity_context",
                    "source": "agent_state.entity_context",
                },
            ),
            _section(
                key="active_skill_context",
                title="当前技能上下文",
                group="runtime_context_sections",
                priority=4,
                body=active_skill_context,
                metadata={
                    "cache_layer": "dynamic_skill_context",
                    "source": "skill_registry.active_skill",
                },
            ),
            _section(
                key="dashboard_context",
                title="Dashboard入口上下文",
                group="runtime_context_sections",
                priority=2,
                body=dashboard_context,
                metadata={
                    "cache_layer": "dynamic_dashboard_context",
                    "volatility": "per_turn",
                    "source": "agent_state.dashboard_context",
                },
            ),
            _section(
                key="ontology_world",
                title="品牌情报状态",
                group="runtime_context_sections",
                priority=3,
                body=ontology_world,
                metadata={
                    "cache_layer": "dynamic_object_world",
                    "volatility": "per_entity_object_state",
                    "source": "ontology_world",
                },
            ),
            _section(
                key="ontology_action_plan",
                title="行动建议",
                group="runtime_context_sections",
                priority=2,
                body=ontology_action_plan,
                metadata={
                    "cache_layer": "dynamic_object_action_plan",
                    "volatility": "per_entity_object_state",
                    "source": "ontology_action_planner",
                },
            ),
            _section(
                key="pending_decision",
                title="待处理决策",
                group="runtime_context_sections",
                priority=1,
                body=pending_decision,
                metadata={
                    "cache_layer": "ephemeral_human_gate",
                    "source": "agent_state.pending_decision",
                },
            ),
            _section(
                key="context_summary",
                title="当前会话摘要",
                group="runtime_context_sections",
                priority=6,
                body=context_summary,
                metadata={
                    "cache_layer": "dynamic_session_summary",
                    "source": "agent_state.context_summary",
                },
            ),
            _section(
                key="history_availability",
                title="过往资料可用性",
                group="runtime_context_sections",
                priority=8,
                drop_policy="drop",
                body=history_availability,
                metadata={
                    "cache_layer": "dynamic_history_manifest",
                    "source": "knowledge_manifest",
                },
            ),
            _section(
                key="recent_evidence_packet",
                title="最近证据包",
                group="runtime_context_sections",
                priority=7,
                body=recent_evidence,
                metadata={
                    "cache_layer": "dynamic_evidence_context",
                    "source": "recent_evidence_packet",
                },
            ),
        )
        if section.normalized_body()
    )

    runtime_reminder_sections = tuple(
        section
        for section in (
            _section(
                key="knowledge_planning_hint",
                title="过往资料规划提示",
                group="runtime_reminder_sections",
                priority=1,
                drop_policy="drop",
                body=knowledge_hint,
                metadata={
                    "cache_layer": "ephemeral_planning_hint",
                    "source": "knowledge_manifest",
                },
            ),
            _section(
                key="instruction_defense_reminder",
                title="指令防守提醒",
                group="runtime_reminder_sections",
                priority=0,
                drop_policy="drop",
                body=instruction_defense,
                metadata={
                    "cache_layer": "ephemeral_security_guard",
                    "source": "instruction_defense",
                },
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

def build_orchestrator_prompt_bundle(state: Mapping[str, Any]) -> OrchestratorPromptBundle:
    return _build_orchestrator_prompt_bundle_from_assembly(
        build_orchestrator_prompt_assembly(state)
    )

def build_orchestrator_system_prompt(state: Mapping[str, Any]) -> str:
    """Build dynamic system prompt based on current state."""

    return build_orchestrator_prompt_bundle(state).system_prompt

