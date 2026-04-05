"""A3 Node: Simulated Question Generation.

The workflow stage is responsible for routing, progress, artifacts, and validation.
Pure question-generation logic is delegated to the internal `question_generation` tool.
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
from app.tools.question_generation import (
    QuestionGenerationTool,
    extract_brand_name as generate_brand_name,
    fix_persona_categories as normalize_persona_questions,
    merge_uploaded_questions as merge_uploaded_question_payload,
    normalize_uploaded_question_payload as normalize_uploaded_questions,
    validate_baseline_questions as validate_generated_baseline_questions,
)

from app.core.constants import PlatformConstants, WorkflowConstants

# Platforms to distribute questions across
_PLATFORMS = PlatformConstants.SUPPORTED_PLATFORMS
# Hard limit on total questions
_MAX_QUESTIONS = WorkflowConstants.MAX_QUESTIONS


def _clear_question_import_state(state: AgentState) -> dict:
    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["table_import_confirmed"] = False
    user_decisions.pop("confirmed_table_kind", None)
    user_decisions.pop("question_import_mode", None)
    return user_decisions


def _normalize_uploaded_question_payload(
    questions: list[dict],
    *,
    start_index: int = 1,
) -> tuple[list[dict], list[dict]]:
    return normalize_uploaded_questions(questions, start_index=start_index)


def _merge_uploaded_questions(
    existing_questions: list[dict],
    incoming_questions: list[dict],
) -> list[dict]:
    return merge_uploaded_question_payload(existing_questions, incoming_questions)


def _get_identity_override(state: AgentState) -> str | None:
    tool_args = state.get("tool_call_args") or {}
    identity = str(tool_args.get("identity") or "").strip()
    return identity or None


def _build_generation_context(identity: str | None) -> dict[str, str | None]:
    return {
        "identity": identity,
        "perspective_source": "user_explicit" if identity else "default_consumer",
    }


def _identity_suffix(identity: str | None) -> str:
    return f"（以“{identity}”身份视角）" if identity else ""


async def a3_question_node(state: AgentState) -> Command:
    """A3: Generate simulated questions.

    Routes to brand panorama mode (template) or persona focused mode (LLM)
    based on user_decisions.a3_mode.
    """
    session_id = state["session_id"]
    user_decisions = state.get("user_decisions", {})
    a3_mode = user_decisions.get("a3_mode", "brand")

    logger.info(f"[A3] Starting question generation in '{a3_mode}' mode")

    if a3_mode == "uploaded_list":
        return await _a3_uploaded_list_mode(state)
    if a3_mode == "baseline_dynamic":
        return await _a3_baseline_dynamic_mode(state)
    elif a3_mode == "persona":
        return await _a3_persona_focused_mode(state)
    else:
        return await _a3_brand_panorama_mode(state)


# ============================================================================
# Brand Panorama Mode (LLM-driven)
# ============================================================================


async def _a3_uploaded_list_mode(state: AgentState) -> Command:
    """A3 uploaded list mode: convert uploaded table payload into A3 artifact."""

    session_id = state["session_id"]
    table_intake_result = state.get("table_intake_result") or {}
    normalized_payload = table_intake_result.get("normalized_payload") or {}
    uploaded_questions = normalized_payload.get("questions") or []
    import_intent = table_intake_result.get("import_intent") or {}
    confirmed_import_action = state.get("confirmed_import_action") or {}
    import_mode = (
        confirmed_import_action.get("import_mode")
        or import_intent.get("mode")
        or "replace"
    )

    if not uploaded_questions:
        message = "上传的问题表未解析到有效问题，无法生成 A3 问题列表。"
        logger.error("[A3] uploaded_list has no questions")
        await send_error_event(session_id, "A3", message, recoverable=True)
        return Command(
            update={
                "error_info": {
                    "step": "A3",
                    "error": message,
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
                "questions": [],
                "simulated_questions": None,
                "current_step": "A3",
            }
        )

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题列表导入",
        progress=0.65,
        message=f"正在将上传表格映射为 A3 问题列表，共 {len(uploaded_questions)} 条问题...",
    )

    existing_uploaded_questions = []
    if import_mode == "merge":
        existing_uploaded_questions = [
            question
            for question in list(state.get("questions") or [])
            if isinstance(question, dict) and question.get("source") == "uploaded_table"
        ]
        uploaded_questions = _merge_uploaded_questions(
            existing_uploaded_questions,
            uploaded_questions,
        )

    simulated_questions, flattened_questions = _normalize_uploaded_question_payload(
        uploaded_questions,
        start_index=1,
    )

    import_mode_label = {
        "merge": "整合导入",
        "replace": "替换导入",
        "create": "首次导入",
    }.get(import_mode, "替换导入")

    result_payload = {
        "generation_mode": "uploaded_list",
        "generation_context": {
            "source_file": table_intake_result.get("source_file"),
            "source_table_kind": table_intake_result.get("table_kind"),
            "warnings": table_intake_result.get("warnings", []),
            "import_mode": import_mode,
            "existing_uploaded_question_count": len(existing_uploaded_questions),
        },
        "simulated_questions": simulated_questions,
    }
    user_decisions = dict(state.get("user_decisions", {}))
    user_decisions["a3_mode"] = "uploaded_list"
    user_decisions["table_import_confirmed"] = False
    user_decisions.pop("confirmed_table_kind", None)
    user_decisions.pop("question_import_mode", None)

    await save_and_send_artifact(
        session_id=session_id,
        output_type="questionList",
        title="问题列表",
        data={
            "simulatedQuestions": result_payload,
            "questions": flattened_questions,
            "generationMode": f"上传问题列表（{import_mode_label}）",
            "sourceFile": table_intake_result.get("source_file"),
        },
    )

    stage_result_data = {
        "count": len(flattened_questions),
        "categories": list(
            {q.get("category", "") for q in flattened_questions if q.get("category")}
        ),
        "examples": [q.get("text", "")[:50] for q in flattened_questions[:3]],
        "source": "uploaded_table",
        "import_mode": import_mode,
    }
    await send_stage_result(
        session_id,
        "A3",
        "问题导入",
        result_type="questions",
        data=stage_result_data,
    )

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题列表导入",
        progress=1.0,
        message=f"已按{import_mode_label}更新 A3 问题列表，共 {len(flattened_questions)} 条问题",
        status="completed",
    )

    return Command(
        update={
            "simulated_questions": result_payload,
            "questions": flattened_questions,
            "current_step": "A3",
            "progress": 0.5,
            "error_info": None,
            "user_decisions": user_decisions,
            "confirmed_import_action": None,
        }
    )


async def _a3_brand_panorama_mode(state: AgentState) -> Command:
    """A3 brand panorama mode: LLM generates brand panorama questions."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    competitors = state.get("competitors") or []
    brand_name = _extract_brand_name(brand_profile, state)
    identity = _get_identity_override(state)

    # Defensive check: refuse to generate if industry is unknown
    industry = brand_profile.get("industry", "")
    if not industry or not industry.strip():
        industry = state.get("industry_hint", "")
    if not industry or not industry.strip():
        logger.error("[A3] brand_profile.industry is empty, cannot generate relevant questions")
        return Command(update={
            "error_info": {"step": "A3", "error": "品牌行业信息缺失，无法生成相关问题。请先完成品牌分析(A1)。"},
            "current_step": "A3",
            "simulated_questions": None,
        })

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题模拟生成",
        progress=0.45,
        message=f"品牌全景模式：正在通过 LLM 生成问题{_identity_suffix(identity)}",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在为「{brand_name}」生成品牌全景问题{_identity_suffix(identity)}，覆盖品牌认知、产品特性、竞品对比等维度...",
    )

    try:
        system_prompt, user_content = QuestionGenerationTool(
            mode="brand_panorama",
            brand_profile=brand_profile,
            competitors=competitors,
            platforms=_PLATFORMS,
            identity=identity,
        )

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="question_simulation",
            step_name="问题模拟生成",
            task_id=state.get("task_id"),
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
            step="question_simulation",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"品牌全景模式：生成 {question_count} 个问题",
            status="completed",
        )

        detailed_response = f"已为「{brand_name}」生成 {question_count} 个模拟问题，详见右侧问题列表。"

        await send_action_log_event(
            session_id, "agent_summary", detailed_response, step="question_simulation", is_complete=True
        )

        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "brand_panorama",
            "generation_context": _build_generation_context(identity),
        }

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="模拟问题列表",
            data={
                "simulatedQuestions": generated_payload,
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
                "simulated_questions": generated_payload,
                "questions": flattened_questions,
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
            },
        )

    except Exception as e:
        logger.error(f"[A3] Brand panorama LLM failed: {e}", exc_info=True)
        await send_error_event(session_id, "A3", str(e), recoverable=True)
        await send_progress_event(
            session_id=session_id,
            step="question_simulation",
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
                "simulated_questions": None,
            },
        )


# ============================================================================
# Persona Focused Mode (LLM-driven)
# ============================================================================


async def _a3_persona_focused_mode(state: AgentState) -> Command:
    """A3 persona focused mode: LLM generates questions based on selected personas."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    identity = _get_identity_override(state)
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

    # Debug: log what we're matching against
    persona_keys = [
        {"name": p.get("name"), "persona_name": p.get("persona_name")}
        for p in all_personas
    ]
    logger.info(
        f"[A3] Persona matching: selected_ids={selected_ids}, "
        f"available personas={persona_keys}"
    )

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
        step="question_simulation",
        step_name="问题模拟生成",
        progress=0.45,
        message=f"画像聚焦模式：为 {len(selected_personas)} 个画像生成问题{_identity_suffix(identity)}",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在基于 {len(selected_personas)} 个选中画像生成针对性问题{_identity_suffix(identity)}...",
    )

    try:
        # Build LLM prompt
        system_prompt, user_content = QuestionGenerationTool(
            mode="persona_focused",
            brand_profile=brand_profile,
            selected_personas=selected_personas,
            platforms=_PLATFORMS,
            identity=identity,
        )

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="question_simulation",
            step_name="问题模拟生成",
            task_id=state.get("task_id"),
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

        # Validate and fix categories + brand ratio
        raw_questions = _fix_persona_categories(raw_questions, brand_name)

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

            category = q.get("category", "画像痛点场景")

            question_obj = {
                "question_id": q_id,
                "category": category,
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
                "category": category,
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
            step="question_simulation",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"画像聚焦模式：生成 {question_count} 个问题",
            status="completed",
        )

        detailed_response = f"已基于「{', '.join(persona_names)}」生成 {question_count} 个聚焦问题，详见右侧问题列表。"

        await send_action_log_event(
            session_id, "agent_summary", detailed_response, step="question_simulation", is_complete=True
        )

        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "persona_focused",
            "generation_context": _build_generation_context(identity),
        }

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="模拟问题列表",
            data={
                "simulatedQuestions": generated_payload,
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
                "simulated_questions": generated_payload,
                "questions": flattened_questions,
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
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
                step="question_simulation",
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
                    "simulated_questions": None,
                },
            )


# ============================================================================
# Shared Helpers
# ============================================================================

def _fix_persona_categories(
    questions: list[dict],
    brand_name: str,
    min_brand_ratio: float = 0.25,
) -> list[dict]:
    """Normalize categories and enforce brand-direct question ratio (≥25%)."""
    questions = normalize_persona_questions(
        questions,
        brand_name,
        min_brand_ratio=min_brand_ratio,
    )
    from collections import Counter
    dist = Counter(q["category"] for q in questions)
    logger.info(
        f"[A3] Persona category distribution (total={len(questions)}): "
        + ", ".join(f"{k}={v}" for k, v in sorted(dist.items()))
    )

    return questions


# ============================================================================
# Baseline Dynamic Mode (LLM-driven, Issue #4)
# ============================================================================


def _extract_brand_name(brand_profile: dict, state: AgentState) -> str:
    """Extract brand_name from brand_profile or state fallback."""
    brand_name = generate_brand_name(brand_profile, state)
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
    identity = _get_identity_override(state)

    # Defensive check: refuse to generate if industry is unknown
    industry = brand_profile.get("industry", "")
    if not industry or not industry.strip():
        industry = state.get("industry_hint", "")
    if not industry or not industry.strip():
        logger.error("[A3] brand_profile.industry is empty, cannot generate relevant questions")
        return Command(update={
            "error_info": {"step": "A3", "error": "品牌行业信息缺失，无法生成相关问题。请先完成品牌分析(A1)。"},
            "current_step": "A3",
            "simulated_questions": None,
        })

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题模拟生成",
        progress=0.45,
        message=f"基线全景模式：正在生成行业全景问题{_identity_suffix(identity)}",
    )

    await send_tpaor_event(
        session_id, "thought",
        f"正在为「{brand_name}」生成行业全景基线问题{_identity_suffix(identity)}，覆盖品类需求、场景选购、竞品对比等维度...",
    )

    try:
        # Build LLM prompt
        system_prompt, user_content = QuestionGenerationTool(
            mode="baseline_dynamic",
            brand_profile=brand_profile,
            competitors=competitors,
            platforms=_PLATFORMS,
            identity=identity,
        )

        model = _get_fast_model()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="question_simulation",
            step_name="问题模拟生成",
            task_id=state.get("task_id"),
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
        validate_generated_baseline_questions(raw_questions, brand_name)

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
            step="question_simulation",
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
            session_id, "agent_summary", detailed_response, step="question_simulation", is_complete=True
        )

        # Save and send artifact to Canvas
        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "baseline_dynamic",
            "generation_context": _build_generation_context(identity),
        }

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="基线问题列表",
            data={
                "simulatedQuestions": generated_payload,
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
                "simulated_questions": generated_payload,
                "baseline_questions": flattened_questions,  # Baseline channel (long-term)
                "questions": flattened_questions,            # Standard channel (A4 reads this)
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
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
                step="question_simulation",
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
                    "simulated_questions": None,
                },
            )


def _build_baseline_system_prompt() -> str:
    """System prompt for baseline dynamic question generation."""
    platform_list = "、".join(
        PlatformConstants.PLATFORM_DISPLAY_NAMES.get(p, p) for p in _PLATFORMS
    )
    return f"""你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，生成模拟用户在 AI 平台（如 {platform_list}）中会提问的**行业全景问题**。

## 核心规则
1. 问题必须是**用户视角**，模拟真实消费者的搜索行为
2. **绝对禁止**在问题中直接提及目标品牌名称
3. 所有问题都必须明确围绕品牌所在行业的**核心产品、价格带、优势场景或关键卖点**
4. 问题必须覆盖品牌的**主要产品领域**
5. 包含预算、场景、用途等真实决策因素
6. 问题要口语化，像真实用户会在 AI 平台中输入的
7. 可以出现竞品名称用于对比，但不能出现目标品牌名称

## 问题分类比例
- 品类需求咨询 (35%)
- 场景化选购 (30%)
- 品类对比排名 (25%)
- 行业趋势探索 (10%)

## 输出格式 (JSON)
请严格输出以下 JSON 格式，不要有其他文字：

{{
  "questions": [
    {{
      "question_id": "bl_001",
      "core_question": "问题文本",
      "category": "品类需求咨询|场景化选购|品类对比排名|行业趋势探索",
      "user_intent": "用户意图",
      "decision_stage": "认知|兴趣|评估|决策",
      "covers_product": "对应的产品线(可选)"
    }}
  ]
}}

## 生成规则
1. 总问题数：10-15 个
2. 不需要指定平台，系统会自动在 {platform_list} 之间轮转分配
3. 问题要覆盖品牌的核心产品线，并尽量贴近品牌已有优势产品/能力
4. 避免重复或过于笼统的问题
5. 竞品名称可以出现在对比类问题中
6. 所有问题都必须避免出现目标品牌名称本身
7. 即使不提品牌名，也要让问题足够贴近品牌产品与使用场景，避免泛行业空问题"""


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
- 【强制约束】所有问题必须严格围绕「{industry}」行业，禁止生成其他行业的问题
- 【强制约束】任何问题都**不要直接出现「{brand_name}」这个品牌名**
- 所有问题都要显式绑定核心产品线、价格带、优势场景或关键卖点，不能退化成泛行业空问题
- 覆盖核心产品线: {products}
- 允许出现竞品名称做对比，但不要把目标品牌名写进问题
- 问题要口语化，像真实用户会搜索的

请直接输出 JSON，不要有其他文字。"""


def _validate_baseline_questions(
    questions: list[dict], brand_name: str
) -> None:
    """Validate baseline question quality for pure industry-baseline mode."""
    if not questions:
        return

    total = len(questions)
    brand_direct_count = sum(
        1 for q in questions
        if brand_name.lower() in q.get("core_question", "").lower()
        or q.get("category", "") == "品牌直接问题"
    )
    if brand_direct_count > 0:
        logger.warning(
            "[A3] Baseline questions contain direct brand mentions "
            "(%d/%d). Pure industry-baseline mode should avoid the target brand name.",
            brand_direct_count,
            total,
        )

