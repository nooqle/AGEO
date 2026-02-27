"""A3 Node: Simulated Question Generation.

This module contains the A3 node implementation for generating simulated user questions.
All modes use LLM-driven generation:
  - "brand" (default): LLM generates brand panorama questions
  - "persona": LLM generates questions focused on selected user personas
  - "baseline_dynamic": LLM generates industry baseline panorama questions
"""

import logging
from datetime import datetime

logger = logging.getLogger(__name__)

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_tpaor_event,
    send_action_log_event,
    send_error_event,
    save_and_send_artifact,
    send_stage_result,
)
from app.workflow.nodes_streaming import call_llm_streaming
from app.workflow.nodes import _get_fast_model
from app.core.utils import extract_json_from_content

from app.core.constants import PlatformConstants, WorkflowConstants

# Platforms to distribute questions across
_PLATFORMS = PlatformConstants.SUPPORTED_PLATFORMS
# Hard limit on total questions
_MAX_QUESTIONS = WorkflowConstants.MAX_QUESTIONS
# Questions per persona in persona mode
_QUESTIONS_PER_PERSONA = WorkflowConstants.QUESTIONS_PER_PERSONA


async def a3_question_node(state: AgentState) -> Command:
    """A3: Generate simulated questions.

    Routes to brand panorama mode (template) or persona focused mode (LLM)
    based on user_decisions.a3_mode.
    """
    session_id = state["session_id"]
    user_decisions = state.get("user_decisions", {})
    a3_mode = user_decisions.get("a3_mode", "brand")

    logger.info(f"[A3] Starting question generation in '{a3_mode}' mode")

    if a3_mode == "baseline_dynamic":
        return await _a3_baseline_dynamic_mode(state)
    elif a3_mode == "persona":
        return await _a3_persona_focused_mode(state)
    else:
        return await _a3_brand_panorama_mode(state)


# ============================================================================
# Brand Panorama Mode (LLM-driven)
# ============================================================================


async def _a3_brand_panorama_mode(state: AgentState) -> Command:
    """A3 brand panorama mode: LLM generates brand panorama questions."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    competitors = state.get("competitors") or []
    brand_name = _extract_brand_name(brand_profile, state)

    await send_progress_event(
        session_id=session_id,
        step="A3",
        step_name="问题模拟生成",
        progress=0.45,
        message="品牌全景模式：正在通过 LLM 生成问题",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在为「{brand_name}」生成品牌全景问题，覆盖品牌认知、产品特性、竞品对比等维度...",
    )

    try:
        system_prompt = _build_baseline_system_prompt()
        user_content = _build_baseline_user_content(brand_profile, competitors)

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="A3",
            step_name="问题模拟生成",
            progress_start=0.5,
            progress_end=0.85,
        )

        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_from_content(content)

        if not data or "questions" not in data:
            raise ValueError(
                f"LLM returned invalid JSON for brand panorama. "
                f"Keys: {list(data.keys()) if data else 'None'}"
            )

        raw_questions = data["questions"]
        if not isinstance(raw_questions, list) or not raw_questions:
            raise ValueError("LLM returned empty questions for brand panorama")

        raw_questions = raw_questions[:_MAX_QUESTIONS]

        # Build simulated_questions and flattened_questions
        simulated_questions = []
        flattened_questions = []
        platform_idx = 0

        for i, q in enumerate(raw_questions):
            q_id = q.get("question_id", f"bp_{i+1:03d}")
            core_question = q.get("core_question", q.get("question", ""))
            if not core_question:
                continue

            platform = _PLATFORMS[platform_idx % len(_PLATFORMS)]
            platform_idx += 1

            question_obj = {
                "question_id": q_id,
                "category": q.get("category", "品牌全景"),
                "core_question": core_question,
                "user_intent": q.get("user_intent", ""),
                "decision_stage": q.get("decision_stage", ""),
                "platform": platform,
            }
            simulated_questions.append(question_obj)

            flattened_questions.append({
                "id": q_id,
                "text": core_question,
                "category": q.get("category", "品牌全景"),
                "intent": q.get("user_intent", ""),
                "stage": q.get("decision_stage", ""),
                "platform": platform,
            })

        question_count = len(simulated_questions)

        await send_progress_event(
            session_id=session_id,
            step="A3",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"品牌全景模式：生成 {question_count} 个问题",
            status="completed",
        )

        detailed_response = f"已为「{brand_name}」生成 {question_count} 个模拟问题，详见右侧问题列表。"

        await send_action_log_event(
            session_id, "agent_summary", detailed_response, step="A3", is_complete=True
        )

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="模拟问题列表",
            data={
                "simulatedQuestions": {"simulated_questions": simulated_questions},
                "questions": flattened_questions,
                "generationMode": "品牌全景模式（LLM生成）",
            },
        )

        categories = list(set(q.get("category", "") for q in simulated_questions if q.get("category")))
        stage_result_data = {
            "count": question_count,
            "categories": categories,
            "examples": [q.get("core_question", "")[:50] for q in simulated_questions[:3]],
        }
        await send_stage_result(
            session_id, "A3", "问题生成",
            result_type="questions",
            data=stage_result_data,
        )

        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.append_stage_result(_UUID(task_id), {
                        "stage": "A3",
                        "result_type": "questions",
                        "data": stage_result_data,
                        "stage_name": "问题生成",
                    })
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)

        return Command(
            update={
                "simulated_questions": {"simulated_questions": simulated_questions},
                "questions": flattened_questions,
                "current_step": "A3",
                "progress": 0.5,
            },
        )

    except Exception as e:
        logger.error(f"[A3] Brand panorama LLM failed: {e}", exc_info=True)
        await send_error_event(session_id, "A3", str(e), recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="A3",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"问题生成失败: {str(e)[:100]}",
            status="error",
        )

        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.fail_task(
                        _UUID(task_id),
                        error_message=str(e),
                        error_stage="A3",
                    )
            except Exception as te:
                logger.warning("[A3] TaskService fail_task failed: %s", te)

        return Command(
            update={
                "error_info": {
                    "step": "A3",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
                "questions": [],
                "current_step": "A3",
            },
        )


# ============================================================================
# Persona Focused Mode (LLM-driven)
# ============================================================================


async def _a3_persona_focused_mode(state: AgentState) -> Command:
    """A3 persona focused mode: LLM generates questions based on selected personas."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    if not brand_name:
        brand_name = state.get("brand_name", "")
    if not brand_name:
        brand_name = "品牌"
        logger.warning(f"[A3] brand_name is empty, falling back to '品牌'. brand_profile keys: {list(brand_profile.keys())}")
    user_decisions = state.get("user_decisions", {})
    selected_ids = user_decisions.get("selected_persona_ids", [])
    marketing_personas = state.get("marketing_personas") or {}

    all_personas = marketing_personas.get("user_personas", [])

    # Match selected personas by name/persona_name
    if selected_ids:
        selected_personas = [
            p for p in all_personas
            if p.get("name") in selected_ids
            or p.get("persona_name") in selected_ids
        ]
    else:
        # No selection — use all personas
        selected_personas = all_personas

    if not selected_personas:
        logger.warning("[A3] No matching personas found, falling back to brand mode")
        return await _a3_brand_panorama_mode(state)

    await send_progress_event(
        session_id=session_id,
        step="A3",
        step_name="问题模拟生成",
        progress=0.45,
        message=f"画像聚焦模式：为 {len(selected_personas)} 个画像生成问题",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在基于 {len(selected_personas)} 个选中画像生成针对性问题...",
    )

    try:
        # Build LLM prompt
        system_prompt = _build_persona_system_prompt()
        user_content = _build_persona_user_content(
            brand_profile, selected_personas
        )

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="A3",
            step_name="问题模拟生成",
            progress_start=0.5,
            progress_end=0.85,
        )

        # Parse LLM response
        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_from_content(content)

        if not data or "questions" not in data:
            logger.warning(
                f"[A3] Persona mode JSON parse failed, falling back to brand mode. "
                f"Keys: {list(data.keys()) if data else 'None'}"
            )
            return await _a3_brand_panorama_mode(state)

        raw_questions = data["questions"]
        if not isinstance(raw_questions, list) or not raw_questions:
            logger.warning("[A3] Empty questions from LLM, falling back to brand mode")
            return await _a3_brand_panorama_mode(state)

        # Enforce hard limit
        raw_questions = raw_questions[:_MAX_QUESTIONS]

        # Build simulated_questions and flattened_questions
        simulated_questions = []
        flattened_questions = []
        platform_idx = 0

        for i, q in enumerate(raw_questions):
            q_id = q.get("question_id", f"pq_{i+1:03d}")
            core_question = q.get("core_question", q.get("question", ""))
            if not core_question:
                continue

            platform = _PLATFORMS[platform_idx % len(_PLATFORMS)]
            platform_idx += 1

            question_obj = {
                "question_id": q_id,
                "category": q.get("category", "画像聚焦"),
                "core_question": core_question,
                "user_intent": q.get("user_intent", ""),
                "decision_stage": q.get("decision_stage", ""),
                "platform": platform,
                "source_persona": q.get("source_persona", ""),
            }
            simulated_questions.append(question_obj)

            flattened_questions.append({
                "id": q_id,
                "text": core_question,
                "category": q.get("category", "画像聚焦"),
                "intent": q.get("user_intent", ""),
                "stage": q.get("decision_stage", ""),
                "platform": platform,
                "source_persona": q.get("source_persona", ""),
            })

        question_count = len(simulated_questions)
        persona_names = [
            p.get("persona_name", p.get("name", ""))
            for p in selected_personas
        ]

        await send_progress_event(
            session_id=session_id,
            step="A3",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"画像聚焦模式：生成 {question_count} 个问题",
            status="completed",
        )

        detailed_response = f"已基于「{', '.join(persona_names)}」生成 {question_count} 个聚焦问题，详见右侧问题列表。"

        await send_action_log_event(
            session_id, "agent_summary", detailed_response, step="A3", is_complete=True
        )

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="模拟问题列表",
            data={
                "simulatedQuestions": {"simulated_questions": simulated_questions},
                "questions": flattened_questions,
                "generationMode": "画像聚焦模式（LLM生成）",
                "selectedPersonas": persona_names,
            },
        )

        # Stage result: 让用户在等待期间看到问题生成阶段性产出 (persona mode)
        p_categories = list(set(q.get("category", "") for q in simulated_questions if q.get("category")))
        p_stage_result_data = {
            "count": question_count,
            "categories": p_categories,
            "examples": [q.get("core_question", "")[:50] for q in simulated_questions[:3]],
        }
        await send_stage_result(
            session_id, "A3", "问题生成",
            result_type="questions",
            data=p_stage_result_data,
        )

        # Persist stage result for reconnection replay (persona mode)
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.append_stage_result(_UUID(task_id), {
                        "stage": "A3",
                        "result_type": "questions",
                        "data": p_stage_result_data,
                        "stage_name": "问题生成",
                    })
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)

        return Command(
            update={
                "simulated_questions": {"simulated_questions": simulated_questions},
                "questions": flattened_questions,
                "current_step": "A3",
                "progress": 0.5,
            },
        )

    except Exception as e:
        logger.error(f"[A3] Persona mode exception: {e}", exc_info=True)
        logger.info("[A3] Falling back to brand panorama mode")
        try:
            return await _a3_brand_panorama_mode(state)
        except Exception as fallback_err:
            logger.error(f"[A3] Fallback also failed: {fallback_err}", exc_info=True)
            await send_error_event(session_id, "A3", str(e), recoverable=True)
            await send_progress_event(
                session_id=session_id,
                step="A3",
                step_name="问题模拟生成",
                progress=1.0,
                message=f"问题生成失败: {str(e)[:100]}",
                status="error",
            )
            return Command(
                update={
                    "error_info": {
                        "step": "A3",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "execution_status": "error",
                    "questions": [],
                    "current_step": "A3",
                },
            )


# ============================================================================
# Shared Helpers
# ============================================================================


def _build_persona_system_prompt() -> str:
    """System prompt for persona-focused question generation."""
    platform_list = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(p, p) for p in _PLATFORMS
    )
    return f"""你是一个资深的AI搜索行为分析专家。你的任务是根据品牌信息和用户画像，生成这些用户可能在AI搜索引擎（如{platform_list}）中提出的真实问题。

## 输出格式
请严格输出以下 JSON 格式，不要有其他文字：

{{
  "questions": [
    {{
      "question_id": "pq_001",
      "core_question": "用户会在AI搜索中问的完整问题",
      "category": "必须从以下4个值中选择：画像痛点场景 | 品牌直接问题 | 品类选购对比 | 行业趋势认知",
      "user_intent": "用户提问的潜在意图",
      "decision_stage": "认知/兴趣/评估/决策/验证",
      "source_persona": "对应画像名称"
    }}
  ]
}}

## 问题分类比例（严格遵守，这是最高优先级的规则）
生成问题时，必须按以下数量分配（以12个问题为例）：
- 品牌直接问题：至少 3-4 个（约30%）— 必须在问题中直接提及品牌名称
- 画像痛点场景：约 4 个（约35%）— 基于画像痛点，不包含品牌名
- 品类选购对比：约 2-3 个（约20%）— 品类层面选购/对比
- 行业趋势认知：约 1-2 个（约15%）— 行业宏观趋势

⚠ 请先生成品牌直接问题，确保数量达标，再生成其他类型。

## 生成规则
1. 每个画像生成 10-15 个问题
2. 问题必须覆盖决策全路径：认知 → 兴趣 → 评估 → 决策 → 验证
3. 不需要指定平台，系统会自动在 {platform_list} 之间轮转分配
4. 问题要贴合该画像人群的真实表达方式和关注点
5. 避免重复或过于笼统的问题
6. 总问题数不超过 40 个
7. **最高优先级**：品牌直接问题必须占总数的 30%（如12题中至少3-4个）。
   生成完毕后请自检各分类数量。category 字段只能使用上述4个固定值。"""


def _build_persona_user_content(
    brand_profile: dict,
    selected_personas: list,
) -> str:
    """Build user content for persona-focused question generation."""
    brand_name = brand_profile.get("brand_name", "")
    industry = brand_profile.get("industry", "")
    description = brand_profile.get("description", "")
    products = ", ".join(brand_profile.get("core_products", []))

    persona_blocks = []
    for p in selected_personas:
        name = p.get("persona_name", p.get("name", ""))
        desc = p.get("persona_description", p.get("description", ""))
        key_qs = p.get("key_questions", [])
        scenarios = p.get("usage_scenarios", [])

        # Build demographics context if available
        demographics = p.get("demographics")
        demo_text = ""
        if demographics and isinstance(demographics, dict):
            demo_parts = []
            if demographics.get("age_range"):
                demo_parts.append(f"年龄: {demographics['age_range']}")
            if demographics.get("gender"):
                demo_parts.append(f"性别: {demographics['gender']}")
            if demographics.get("city_tier"):
                demo_parts.append(f"城市: {demographics['city_tier']}")
            if demographics.get("income"):
                demo_parts.append(f"收入: {demographics['income']}")
            if demographics.get("occupation"):
                demo_parts.append(f"职业: {demographics['occupation']}")
            if demo_parts:
                demo_text = f"- 人口统计: {', '.join(demo_parts)}"

        # Build psychographics context if available
        psychographics = p.get("psychographics")
        psycho_text = ""
        if psychographics and isinstance(psychographics, dict):
            psycho_parts = []
            if psychographics.get("lifestyle"):
                psycho_parts.append(f"生活方式: {psychographics['lifestyle']}")
            if psychographics.get("values"):
                psycho_parts.append(f"价值观: {psychographics['values']}")
            pain_points = psychographics.get("pain_points", [])
            if pain_points:
                psycho_parts.append(f"痛点: {', '.join(pain_points)}")
            if psycho_parts:
                psycho_text = f"- 心理画像: {'; '.join(psycho_parts)}"

        scenario_text = ""
        if scenarios:
            scenario_lines = []
            for s in scenarios:
                if isinstance(s, dict):
                    line = f"  - {s.get('scenario_name', '')}: {s.get('scenario_description', '')}"
                    # Include search intents if available
                    intents = s.get("brand_interaction_intents", s.get("likely_search_intents", []))
                    if intents:
                        line += f" (互动意图: {', '.join(intents)})"
                    scenario_lines.append(line)
                elif isinstance(s, str):
                    scenario_lines.append(f"  - {s}")
            scenario_text = "\n".join(scenario_lines)

        block = f"""### {name}
- 描述: {desc}
{demo_text}
{psycho_text}
- 关注问题: {', '.join(key_qs) if key_qs else '无'}
- 使用场景:
{scenario_text if scenario_text else '  - 无'}""".strip()
        persona_blocks.append(block)

    return f"""请为以下品牌的目标用户画像生成AI搜索模拟问题。

## 品牌信息
- 品牌名称: {brand_name}
- 行业: {industry}
- 品牌描述: {description}
- 核心产品: {products}

## 选中画像（为每个画像生成 10-15 个问题）

{chr(10).join(persona_blocks)}

## 比例要求（最高优先级，务必遵守）
请严格按照以下比例和数量生成问题：
- 品牌直接问题（约30%，"{brand_name}"必须出现在问题中）：如果总共12题，至少3-4个
- 画像痛点场景（约35%，不包含品牌名"{brand_name}"）
- 品类选购对比（约20%）：围绕{industry}品类的选购、对比、推荐
- 行业趋势认知（约15%）：{industry}行业的趋势、技术、市场变化

⚠ category 字段必须使用以上4个固定名称，不要自创分类。
⚠ 先生成品牌直接问题确保达标，再生成其他类型。

请直接输出 JSON，不要有其他文字。"""


# ============================================================================
# Baseline Dynamic Mode (LLM-driven, Issue #4)
# ============================================================================


def _extract_brand_name(brand_profile: dict, state: AgentState) -> str:
    """Extract brand_name from brand_profile or state fallback."""
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    if not brand_name:
        brand_name = state.get("brand_name", "")
    if not brand_name:
        brand_name = "品牌"
        logger.warning(
            "[A3] brand_name is empty, falling back to '品牌'. "
            f"brand_profile keys: {list(brand_profile.keys())}"
        )
    return brand_name


async def _a3_baseline_dynamic_mode(state: AgentState) -> Command:
    """A3 baseline dynamic mode: LLM generates industry panorama questions."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    competitors = state.get("competitors") or []
    brand_name = _extract_brand_name(brand_profile, state)

    await send_progress_event(
        session_id=session_id,
        step="A3",
        step_name="问题模拟生成",
        progress=0.45,
        message="基线全景模式：正在生成行业全景问题",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在为「{brand_name}」生成行业全景基线问题，覆盖品类需求、场景选购、竞品对比等维度...",
    )

    try:
        # Build LLM prompt
        system_prompt = _build_baseline_system_prompt()
        user_content = _build_baseline_user_content(brand_profile, competitors)

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="A3",
            step_name="问题模拟生成",
            progress_start=0.5,
            progress_end=0.85,
        )

        # Parse LLM response
        content = response.content if hasattr(response, "content") else str(response)
        data = extract_json_from_content(content)

        if not data or "questions" not in data:
            logger.warning(
                f"[A3] Baseline dynamic JSON parse failed, falling back to brand mode. "
                f"Keys: {list(data.keys()) if data else 'None'}"
            )
            return await _a3_brand_panorama_mode(state)

        raw_questions = data["questions"]
        if not isinstance(raw_questions, list) or not raw_questions:
            logger.warning("[A3] Empty questions from baseline LLM, falling back to brand mode")
            return await _a3_brand_panorama_mode(state)

        # Enforce hard limit
        raw_questions = raw_questions[:_MAX_QUESTIONS]

        # Validate brand question ratio
        _validate_baseline_questions(raw_questions, brand_name)

        # Build simulated_questions and flattened_questions
        simulated_questions = []
        flattened_questions = []
        platform_idx = 0

        for i, q in enumerate(raw_questions):
            q_id = q.get("question_id", f"bl_{i+1:03d}")
            core_question = q.get("core_question", q.get("question", ""))
            if not core_question:
                continue

            platform = _PLATFORMS[platform_idx % len(_PLATFORMS)]
            platform_idx += 1

            question_obj = {
                "question_id": q_id,
                "category": q.get("category", "行业全景"),
                "core_question": core_question,
                "user_intent": q.get("user_intent", ""),
                "decision_stage": q.get("decision_stage", ""),
                "platform": platform,
                "covers_product": q.get("covers_product", ""),
            }
            simulated_questions.append(question_obj)

            flattened_questions.append({
                "id": q_id,
                "text": core_question,
                "category": q.get("category", "行业全景"),
                "intent": q.get("user_intent", ""),
                "stage": q.get("decision_stage", ""),
                "platform": platform,
            })

        question_count = len(simulated_questions)

        await send_progress_event(
            session_id=session_id,
            step="A3",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"基线全景模式：生成 {question_count} 个行业全景问题",
            status="completed",
        )

        detailed_response = (
            f"已为「{brand_name}」生成 {question_count} 个行业全景基线问题，"
            f"详见右侧问题列表。"
        )

        await send_action_log_event(
            session_id, "agent_summary", detailed_response, step="A3", is_complete=True
        )

        # Save and send artifact to Canvas
        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="基线问题列表",
            data={
                "simulatedQuestions": {"simulated_questions": simulated_questions},
                "questions": flattened_questions,
                "generationMode": "基线全景模式（LLM生成）",
            },
        )

        # Stage result
        categories = list(set(
            q.get("category", "") for q in simulated_questions if q.get("category")
        ))
        stage_result_data = {
            "count": question_count,
            "categories": categories,
            "examples": [q.get("core_question", "")[:50] for q in simulated_questions[:3]],
        }
        await send_stage_result(
            session_id, "A3", "问题生成",
            result_type="questions",
            data=stage_result_data,
        )

        # Persist stage result for reconnection replay
        task_id = state.get("task_id")
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    task_svc = TaskService(db)
                    await task_svc.append_stage_result(_UUID(task_id), {
                        "stage": "A3",
                        "result_type": "questions",
                        "data": stage_result_data,
                        "stage_name": "问题生成",
                    })
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)

        # Dual-write: baseline_questions + questions
        return Command(
            update={
                "simulated_questions": {"simulated_questions": simulated_questions},
                "baseline_questions": flattened_questions,  # Baseline channel (long-term)
                "questions": flattened_questions,            # Standard channel (A4 reads this)
                "current_step": "A3",
                "progress": 0.5,
            },
        )

    except Exception as e:
        logger.error(f"[A3] Baseline dynamic mode failed: {e}", exc_info=True)
        logger.info("[A3] Falling back to brand panorama mode")
        try:
            return await _a3_brand_panorama_mode(state)
        except Exception as fallback_err:
            logger.error(f"[A3] Fallback also failed: {fallback_err}", exc_info=True)
            await send_error_event(session_id, "A3", str(e), recoverable=True)
            await send_progress_event(
                session_id=session_id,
                step="A3",
                step_name="问题模拟生成",
                progress=1.0,
                message=f"问题生成失败: {str(e)[:100]}",
                status="error",
            )
            return Command(
                update={
                    "error_info": {
                        "step": "A3",
                        "error": str(e),
                        "timestamp": datetime.now().isoformat(),
                    },
                    "execution_status": "error",
                    "questions": [],
                    "current_step": "A3",
                },
            )


def _build_baseline_system_prompt() -> str:
    """System prompt for baseline dynamic question generation."""
    platform_list = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(p, p) for p in _PLATFORMS
    )
    return f"""你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，生成模拟用户在 AI 搜索引擎（如 {platform_list}）中会提问的**行业全景问题**。

## 核心规则
1. 问题必须是**用户视角**，模拟真实消费者的搜索行为
2. 直接提及目标品牌的问题**不超过总数的 10%**
3. 问题必须覆盖品牌的**主要产品领域**
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 搜索中输入的

## 问题分类比例
- 品类需求咨询 (30%)
- 场景化选购 (25%)
- 品类对比排名 (20%)
- 行业趋势探索 (15%)
- 品牌直接问题 (10% 上限)

## 输出格式 (JSON)
请严格输出以下 JSON 格式，不要有其他文字：

{{
  "questions": [
    {{
      "question_id": "bl_001",
      "core_question": "问题文本",
      "category": "品类需求咨询|场景化选购|品类对比排名|行业趋势探索|品牌直接问题",
      "user_intent": "用户意图",
      "decision_stage": "认知|兴趣|评估|决策",
      "covers_product": "对应的产品线(可选)"
    }}
  ]
}}

## 生成规则
1. 总问题数：10-15 个
2. 不需要指定平台，系统会自动在 {platform_list} 之间轮转分配
3. 问题要覆盖品牌的核心产品线
4. 避免重复或过于笼统的问题
5. 竞品名称可以出现在对比类问题中"""


def _build_baseline_user_content(
    brand_profile: dict,
    competitors: list,
) -> str:
    """Build user content for baseline dynamic question generation."""
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    industry = brand_profile.get("industry", "")
    description = brand_profile.get("description", "")
    products = ", ".join(brand_profile.get("core_products", []))

    competitor_text = "无"
    if competitors:
        comp_names = []
        for c in competitors:
            if isinstance(c, dict):
                comp_names.append(c.get("name", c.get("brand_name", str(c))))
            else:
                comp_names.append(str(c))
        competitor_text = ", ".join(comp_names)

    return f"""请为以下品牌生成行业全景基线问题。

## 品牌信息
- 品牌名称: {brand_name}
- 行业: {industry}
- 品牌描述: {description}
- 核心产品: {products}

## 竞品列表
{competitor_text}

## 要求
- 生成 10-15 个行业全景问题
- 直接提及「{brand_name}」的问题不超过总数的 10%
- 覆盖核心产品线: {products}
- 问题要口语化，像真实用户会搜索的

请直接输出 JSON，不要有其他文字。"""


def _validate_baseline_questions(
    questions: list[dict], brand_name: str
) -> None:
    """Validate baseline question quality. Logs warning if brand ratio exceeds threshold."""
    if not questions:
        return

    total = len(questions)
    brand_direct_count = sum(
        1 for q in questions
        if brand_name.lower() in q.get("core_question", "").lower()
        or q.get("category", "") == "品牌直接问题"
    )
    brand_ratio = brand_direct_count / total if total > 0 else 0

    if brand_ratio > 0.15:  # 10% target + 5% tolerance
        logger.warning(
            "[A3] Baseline questions brand_ratio=%.1f%% exceeds 15%% threshold "
            "(%d/%d). Proceeding anyway.",
            brand_ratio * 100, brand_direct_count, total,
        )
