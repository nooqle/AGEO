"""A3 Node: Simulated Question Generation.

The workflow stage is responsible for routing, progress, artifacts, and validation.
Pure question-generation logic is delegated to the internal `question_generation` tool.
"""

import logging
from datetime import datetime
from uuid import UUID

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_tpaor_event,
    send_action_log_event,
    send_error_event,
    save_and_send_artifact,
    send_stage_result,
    send_confirmation_request,
)
from app.workflow.nodes_streaming import call_llm_streaming
from app.core.llm import BaseLLMModel
from app.core.llm.task_routing import get_a3_llm_model
from app.core.utils import extract_json_from_content
from app.tools.question_generation import (
    QuestionGenerationTool,
    extract_brand_name as generate_brand_name,
    fix_persona_categories as normalize_persona_questions,
    merge_uploaded_questions as merge_uploaded_question_payload,
    normalize_topic_keywords,
    normalize_uploaded_question_payload as normalize_uploaded_questions,
    sanitize_panorama_questions as sanitize_generated_panorama_questions,
    validate_baseline_questions as validate_generated_baseline_questions,
)
from app.workflow.brand_state import build_effective_brand_profile

from app.core.constants import PlatformConstants, WorkflowConstants
from app.workflow.runtime_policy_executor import build_next_required_action

logger = logging.getLogger(__name__)

# Platforms to distribute questions across
_PLATFORMS = PlatformConstants.SUPPORTED_PLATFORMS
# Hard limit on total questions
_MAX_QUESTIONS = WorkflowConstants.MAX_QUESTIONS


def _get_a3_model() -> BaseLLMModel:
    """Return the dedicated A3 model without inheriting A1/A2/global routing."""

    return get_a3_llm_model()


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


def _get_topic_focus(state: AgentState) -> dict[str, object]:
    tool_args = state.get("tool_call_args") or {}
    keywords = normalize_topic_keywords(tool_args.get("topic_keywords"))
    description = str(tool_args.get("topic_description") or "").strip()
    return {
        "topic_keywords": keywords,
        "topic_description": description or None,
    }


def _format_topic_label(topic_focus: dict[str, object] | None) -> str:
    keywords = list((topic_focus or {}).get("topic_keywords") or [])
    if not keywords:
        return ""
    return "、".join(str(keyword) for keyword in keywords[:4])


def _is_question_generation_only(state: AgentState) -> bool:
    tool_args = state.get("tool_call_args") or {}
    user_decisions = state.get("user_decisions") or {}
    simulated_questions = state.get("simulated_questions") or {}
    generation_context = (
        simulated_questions.get("generation_context")
        if isinstance(simulated_questions, dict)
        else {}
    ) or {}
    return bool(
        tool_args.get("question_only")
        or state.get("question_generation_only")
        or (
            isinstance(user_decisions, dict)
            and user_decisions.get("question_generation_only")
        )
        or (
            isinstance(generation_context, dict)
            and generation_context.get("question_only")
        )
    )


def _build_generation_context(
    identity: str | None,
    topic_focus: dict[str, object] | None = None,
    *,
    question_only: bool = False,
) -> dict[str, object | None]:
    context: dict[str, object | None] = {
        "identity": identity,
        "perspective_source": "user_explicit" if identity else "default_consumer",
    }
    keywords = list((topic_focus or {}).get("topic_keywords") or [])
    if keywords:
        context.update(
            {
                "topic_keywords": keywords,
                "topic_description": (topic_focus or {}).get("topic_description"),
                "focus_source": "user_keywords",
                "question_focus": "topic_panorama",
            }
        )
    if question_only:
        context["question_only"] = True
    return context


def _identity_suffix(identity: str | None) -> str:
    return f"（以“{identity}”身份视角）" if identity else ""


def _monitor_mode_from_a3_mode(a3_mode: str | None) -> str:
    return "scenario" if str(a3_mode or "").strip().lower() == "persona" else "panorama"


def _selected_fetch_mode_from_state(state: AgentState) -> str | None:
    fetch_mode = str(state.get("fetch_mode") or "").strip().lower()
    if fetch_mode in {"fast", "full"}:
        return fetch_mode

    user_decisions = state.get("user_decisions") or {}
    if not isinstance(user_decisions, dict):
        return None

    decision_mode = str(user_decisions.get("fetch_mode") or "").strip().lower()
    if decision_mode in {"fast", "full"}:
        return decision_mode

    if (
        user_decisions.get("fetch_mode_confirmed") is True
        and user_decisions.get("fetch_mode_pending") is not True
    ):
        return "fast"

    return None


async def _persist_draft_question_set(
    state: AgentState,
    *,
    flattened_questions: list[dict],
    title: str,
    monitor_mode: str,
    source: str = "chat_generated",
) -> str | None:
    """Persist A3 output as a draft question set for later user confirmation."""
    user_id = state.get("user_id")
    entity_id = state.get("entity_id")
    if not user_id or not entity_id or not flattened_questions:
        return None
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.monitoring_plan_service import MonitoringPlanService

        async with AsyncSessionLocal() as db:
            service = MonitoringPlanService(db)
            question_set = await service.create_question_set(
                user_id=UUID(str(user_id)),
                entity_id=UUID(str(entity_id)),
                monitor_mode=monitor_mode,
                title=title,
                questions=flattened_questions,
                source=source,
                source_session_id=UUID(str(state["session_id"])),
                source_task_id=(
                    UUID(str(state["task_id"])) if state.get("task_id") else None
                ),
                extra_metadata={
                    "a3_mode": (state.get("user_decisions") or {}).get("a3_mode"),
                },
            )
            return str(question_set.id)
    except Exception as exc:
        logger.warning("[A3] Failed to persist draft question set: %s", exc)
        return None


def _uuid_or_none(value: object) -> UUID | None:
    try:
        return UUID(str(value)) if value else None
    except (TypeError, ValueError):
        return None


async def _persist_brand_intelligence_questions(
    state: AgentState,
    *,
    payload: dict,
) -> None:
    """Dual-write A3 questions into the durable brand intelligence layer."""

    entity_uuid = _uuid_or_none(state.get("entity_id"))
    if entity_uuid is None:
        return
    session_uuid = _uuid_or_none(state.get("session_id"))
    try:
        from app.core.database import AsyncSessionLocal
        from app.services.brand_action_service import BrandActionService
        from app.services.brand_intelligence_projection_service import (
            BrandIntelligenceProjectionService,
        )

        async with AsyncSessionLocal() as db:
            action_service = BrandActionService(db)
            action_record = await action_service.start_action(
                entity_id=entity_uuid,
                session_id=session_uuid,
                user_id=_uuid_or_none(state.get("user_id")),
                parent_action_record_id=_uuid_or_none(
                    state.get("latest_user_action_record_id")
                ),
                actor_type="agent",
                origin_surface="workflow_node",
                origin_event_id=str(state.get("run_id") or "") or None,
                action_type="generate_question_set",
                input_payload={
                    "generation_mode": payload.get("generation_mode")
                    or "workflow_generated",
                    "question_count": len(payload.get("simulated_questions") or []),
                },
            )
            service = BrandIntelligenceProjectionService(db)
            try:
                rows = await service.persist_questions(
                    entity_id=entity_uuid,
                    session_id=session_uuid,
                    payload=payload,
                )
                await action_service.complete_action(
                    action_record,
                    output_payload={"questions": len(rows)},
                )
                await db.commit()
            except Exception as inner_exc:
                await action_service.fail_action(
                    action_record,
                    error_message=str(inner_exc),
                )
                await db.commit()
                raise
        logger.info("[A3] Brand intelligence questions projected: %d", len(rows))
    except Exception as exc:
        logger.warning("[A3] Brand intelligence question projection failed: %s", exc)


async def _question_set_confirmation_update(
    state: AgentState,
    *,
    question_set_id: str | None,
    monitor_mode: str,
    question_count: int,
) -> dict:
    """Build the independent A3 question set confirmation checkpoint."""
    if _is_question_generation_only(state):
        return {
            "awaiting_user": False,
            "execution_status": "completed",
            "pending_confirmation": None,
            "pending_question_set_confirmation": None,
            "next_required_action": None,
            "progress_message": (
                f"问题集已生成，共 {question_count} 个问题，未自动进入答案抓取。"
            ),
        }

    selected_fetch_mode = _selected_fetch_mode_from_state(state)
    if selected_fetch_mode:
        mode_label = "快速采集" if selected_fetch_mode == "fast" else "完整采集"
        return {
            "awaiting_user": False,
            "execution_status": "running",
            "pending_confirmation": None,
            "pending_question_set_confirmation": None,
            "fetch_mode": selected_fetch_mode,
            "progress_message": (f"问题集已生成，按已选择的{mode_label}继续抓取答案。"),
            "next_required_action": build_next_required_action(
                tool_name="answer_fetch",
                authority="authoritative_resume",
                tool_args={"fetch_mode": selected_fetch_mode},
                reason="A3 已完成，且用户此前已确认采集模式，继续执行 A4。",
                source_step="question_set_confirmation",
                metadata={
                    "question_set_id": question_set_id,
                    "monitor_mode": monitor_mode,
                    "question_count": question_count,
                    "preselected_fetch_mode": selected_fetch_mode,
                },
            ),
        }

    if (
        not question_set_id
        or state.get("headless_mode")
        or state.get("monitoring_schedule_id")
    ):
        return {}

    session_id = state.get("session_id")
    if not session_id:
        return {}

    request_id = f"question_set_confirmation_{question_set_id}"
    mode_label = "用户场景监测" if monitor_mode == "scenario" else "全景监测"
    message = (
        f"已生成「{mode_label}」问题集，共 {question_count} 个问题。"
        "请确认是否启用快速监测。"
    )
    options = [
        {
            "id": "confirm_question_set_enable_quick",
            "label": "确认并启用快速监测",
            "description": "确认当前问题集，并创建或更新快速监测计划",
        },
        {
            "id": "append_question_set_questions",
            "label": "继续补充问题",
            "description": "先补充更多问题，确认后再启用监测",
        },
        {
            "id": "decline_question_set_enable",
            "label": "暂不启用",
            "description": "保留为草稿，不启动自动监测",
        },
    ]
    await send_confirmation_request(
        session_id=session_id,
        step_id="question_set_confirmation",
        step_name="确认监测问题集",
        message=message,
        options=options,
    )
    pending_confirmation = {
        "request_id": request_id,
        "type": "question_set_confirmation",
        "step_id": "question_set_confirmation",
        "step_name": "确认监测问题集",
        "message": message,
        "options": options,
        "question_set_id": question_set_id,
        "monitor_mode": monitor_mode,
        "question_count": question_count,
    }
    return {
        "awaiting_user": True,
        "execution_status": "awaiting_user",
        "pending_confirmation": pending_confirmation,
        "pending_question_set_confirmation": pending_confirmation,
        "progress_message": message,
    }


async def a3_question_node(state: AgentState) -> Command:
    """A3: Generate simulated questions.

    Routes to brand panorama mode (template) or persona focused mode (LLM)
    based on user_decisions.a3_mode.
    """
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


def _normalize_persona_refs(value) -> set[str]:
    if isinstance(value, str):
        values = [value]
    elif isinstance(value, list):
        values = value
    else:
        values = []
    return {str(item).strip() for item in values if str(item or "").strip()}


def _persona_matches_refs(persona: dict, index: int, refs: set[str]) -> bool:
    if not refs:
        return False

    candidates = {
        str(persona.get("id") or "").strip(),
        str(persona.get("name") or "").strip(),
        str(persona.get("persona_name") or "").strip(),
        f"persona_{index + 1}",
        f"profile_{index}",
    }
    candidates.discard("")
    return bool(candidates & refs)


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
    latest_question_set_id = await _persist_draft_question_set(
        state,
        flattened_questions=flattened_questions,
        title=f"上传问题列表（{import_mode_label}）",
        monitor_mode=_monitor_mode_from_a3_mode(user_decisions.get("a3_mode")),
        source="imported",
    )
    monitor_mode = _monitor_mode_from_a3_mode(user_decisions.get("a3_mode"))
    confirmation_update = await _question_set_confirmation_update(
        state,
        question_set_id=latest_question_set_id,
        monitor_mode=monitor_mode,
        question_count=len(flattened_questions),
    )
    await _persist_brand_intelligence_questions(state, payload=result_payload)

    return Command(
        update={
            "simulated_questions": result_payload,
            "questions": flattened_questions,
            "latest_question_set_id": latest_question_set_id,
            "question_set_ids": (
                [latest_question_set_id] if latest_question_set_id else []
            ),
            "current_step": "A3",
            "progress": 0.5,
            "error_info": None,
            "user_decisions": user_decisions,
            "confirmed_import_action": None,
            **confirmation_update,
        }
    )


async def _a3_brand_panorama_mode(state: AgentState) -> Command:
    """A3 brand panorama mode: LLM generates brand panorama questions."""
    session_id = state["session_id"]
    brand_profile = build_effective_brand_profile(state)
    competitors = state.get("competitors") or []
    brand_name = _extract_brand_name(brand_profile, state)
    identity = _get_identity_override(state)
    question_only = _is_question_generation_only(state)

    # Defensive check: refuse to generate if industry is unknown
    industry = brand_profile.get("industry", "")
    if not industry or not industry.strip():
        industry = state.get("industry_hint", "")
    if not industry or not industry.strip():
        logger.error(
            "[A3] brand_profile.industry is empty, cannot generate relevant questions"
        )
        return Command(
            update={
                "error_info": {
                    "step": "A3",
                    "error": "品牌行业信息缺失，无法生成相关问题。请先完成品牌分析(A1)。",
                },
                "current_step": "A3",
                "simulated_questions": None,
            }
        )

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题模拟生成",
        progress=0.45,
        message=f"品牌全景分析：正在生成问题{_identity_suffix(identity)}",
    )

    await send_tpaor_event(
        session_id,
        "thought",
        f"正在为「{brand_name}」整理品牌全景问题{_identity_suffix(identity)}，覆盖品牌认知、产品特性、使用场景与后续抓取方向...",
    )

    try:
        system_prompt, user_content = QuestionGenerationTool(
            mode="brand_panorama",
            brand_profile=brand_profile,
            competitors=competitors,
            platforms=_PLATFORMS,
            identity=identity,
        )

        model = _get_a3_model()
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
        raw_questions = sanitize_generated_panorama_questions(
            raw_questions,
            brand_name,
            competitors,
        )

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

            flattened_questions.append(
                {
                    "id": q_id,
                    "text": core_question,
                    "category": q.get("category", "品牌全景"),
                    "intent": q.get("user_intent", ""),
                    "stage": q.get("decision_stage", ""),
                    "platform": platform,
                }
            )

        question_count = len(simulated_questions)

        await send_progress_event(
            session_id=session_id,
            step="question_simulation",
            step_name="问题模拟生成",
            progress=1.0,
            message=f"品牌全景分析：已生成 {question_count} 个问题",
            status="completed",
        )

        detailed_response = f"已为「{brand_name}」完成品牌全景问题整理，共 {question_count} 个问题，详见右侧问题列表。"

        await send_action_log_event(
            session_id,
            "agent_summary",
            detailed_response,
            step="question_simulation",
            is_complete=True,
        )

        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "brand_panorama",
            "generation_context": _build_generation_context(
                identity,
                question_only=question_only,
            ),
        }

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="品牌全景问题列表",
            data={
                "simulatedQuestions": generated_payload,
                "questions": flattened_questions,
                "generationMode": "品牌全景分析",
            },
        )

        categories = list(
            set(q.get("category", "") for q in simulated_questions if q.get("category"))
        )
        stage_result_data = {
            "count": question_count,
            "categories": categories,
            "examples": [
                q.get("core_question", "")[:50] for q in simulated_questions[:3]
            ],
        }
        await send_stage_result(
            session_id,
            "A3",
            "问题生成",
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
                    await task_svc.append_stage_result(
                        _UUID(task_id),
                        {
                            "stage": "A3",
                            "result_type": "questions",
                            "data": stage_result_data,
                            "stage_name": "问题生成",
                        },
                    )
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)
        latest_question_set_id = await _persist_draft_question_set(
            state,
            flattened_questions=flattened_questions,
            title="品牌全景问题集",
            monitor_mode="panorama",
        )
        confirmation_update = await _question_set_confirmation_update(
            state,
            question_set_id=latest_question_set_id,
            monitor_mode="panorama",
            question_count=len(flattened_questions),
        )
        await _persist_brand_intelligence_questions(state, payload=generated_payload)

        return Command(
            update={
                "brand_profile": brand_profile,
                "simulated_questions": generated_payload,
                "questions": flattened_questions,
                "latest_question_set_id": latest_question_set_id,
                "question_set_ids": (
                    [latest_question_set_id] if latest_question_set_id else []
                ),
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
                **confirmation_update,
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
    brand_profile = build_effective_brand_profile(state)
    identity = _get_identity_override(state)
    question_only = _is_question_generation_only(state)
    brand_name = brand_profile.get("brand_name", "") or brand_profile.get("name", "")
    if not brand_name:
        brand_name = state.get("brand_name", "")
    if not brand_name:
        brand_name = "品牌"
        logger.warning(
            f"[A3] brand_name is empty, falling back to '品牌'. brand_profile keys: {list(brand_profile.keys())}"
        )
    user_decisions = state.get("user_decisions", {})
    selected_ids = user_decisions.get("selected_persona_ids", [])
    selected_names = user_decisions.get("selected_persona_names", [])
    selected_refs = _normalize_persona_refs(selected_ids) | _normalize_persona_refs(
        selected_names
    )
    marketing_personas = state.get("marketing_personas") or {}

    all_personas = marketing_personas.get("user_personas", [])

    # Debug: log what we're matching against
    persona_keys = [
        {"name": p.get("name"), "persona_name": p.get("persona_name")}
        for p in all_personas
    ]
    logger.info(
        f"[A3] Persona matching: selected_refs={sorted(selected_refs)}, "
        f"available personas={persona_keys}"
    )

    # Match selected personas by name/persona_name
    if selected_refs & {"all", "all_personas"}:
        selected_personas = all_personas
    elif selected_refs:
        selected_personas = [
            p
            for index, p in enumerate(all_personas)
            if isinstance(p, dict) and _persona_matches_refs(p, index, selected_refs)
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
        session_id,
        "thought",
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

        model = _get_a3_model()
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

            flattened_questions.append(
                {
                    "id": q_id,
                    "text": core_question,
                    "category": category,
                    "intent": q.get("user_intent", ""),
                    "stage": q.get("decision_stage", ""),
                    "platform": platform,
                    "source_persona": q.get("source_persona", ""),
                }
            )

        question_count = len(simulated_questions)
        persona_names = [
            p.get("persona_name", p.get("name", "")) for p in selected_personas
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
            session_id,
            "agent_summary",
            detailed_response,
            step="question_simulation",
            is_complete=True,
        )

        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "persona_focused",
            "generation_context": _build_generation_context(
                identity,
                question_only=question_only,
            ),
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
        p_categories = list(
            set(q.get("category", "") for q in simulated_questions if q.get("category"))
        )
        p_stage_result_data = {
            "count": question_count,
            "categories": p_categories,
            "examples": [
                q.get("core_question", "")[:50] for q in simulated_questions[:3]
            ],
        }
        await send_stage_result(
            session_id,
            "A3",
            "问题生成",
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
                    await task_svc.append_stage_result(
                        _UUID(task_id),
                        {
                            "stage": "A3",
                            "result_type": "questions",
                            "data": p_stage_result_data,
                            "stage_name": "问题生成",
                        },
                    )
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)
        latest_question_set_id = await _persist_draft_question_set(
            state,
            flattened_questions=flattened_questions,
            title="用户场景问题集",
            monitor_mode="scenario",
        )
        confirmation_update = await _question_set_confirmation_update(
            state,
            question_set_id=latest_question_set_id,
            monitor_mode="scenario",
            question_count=len(flattened_questions),
        )
        await _persist_brand_intelligence_questions(state, payload=generated_payload)

        return Command(
            update={
                "brand_profile": brand_profile,
                "simulated_questions": generated_payload,
                "questions": flattened_questions,
                "latest_question_set_id": latest_question_set_id,
                "question_set_ids": (
                    [latest_question_set_id] if latest_question_set_id else []
                ),
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
                **confirmation_update,
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


def _get_explicit_brand_name(brand_profile: dict, state: AgentState) -> str:
    brand_name = (
        str(brand_profile.get("brand_name") or brand_profile.get("name") or "").strip()
        or str(state.get("brand_name") or "").strip()
    )
    return "" if brand_name == "品牌" else brand_name


async def _a3_baseline_dynamic_mode(state: AgentState) -> Command:
    """A3 baseline dynamic mode: LLM generates industry panorama questions."""
    session_id = state["session_id"]
    brand_profile = build_effective_brand_profile(state)
    competitors = state.get("competitors") or []
    explicit_brand_name = _get_explicit_brand_name(brand_profile, state)
    topic_focus = _get_topic_focus(state)
    topic_label = _format_topic_label(topic_focus)
    brand_name = explicit_brand_name or topic_label or "主题"
    identity = _get_identity_override(state)
    question_only = _is_question_generation_only(state)

    # Defensive check: refuse to generate if industry is unknown
    industry = brand_profile.get("industry", "")
    if not industry or not industry.strip():
        industry = state.get("industry_hint", "")
    topic_keywords = list(topic_focus.get("topic_keywords") or [])
    if (not industry or not industry.strip()) and not topic_keywords:
        logger.error(
            "[A3] brand_profile.industry is empty, cannot generate relevant questions"
        )
        return Command(
            update={
                "error_info": {
                    "step": "A3",
                    "error": "品牌行业信息缺失，无法生成相关问题。请先完成品牌分析(A1)。",
                },
                "current_step": "A3",
                "simulated_questions": None,
            }
        )

    await send_progress_event(
        session_id=session_id,
        step="question_simulation",
        step_name="问题模拟生成",
        progress=0.45,
        message=(
            f"正在围绕「{topic_label}」生成全景问题{_identity_suffix(identity)}"
            if topic_label
            else f"品牌全景分析：正在生成行业全景问题{_identity_suffix(identity)}"
        ),
    )

    await send_tpaor_event(
        session_id,
        "thought",
        (
            f"正在围绕「{topic_label}」整理全景问题{_identity_suffix(identity)}，覆盖用户需求、场景选购、风险顾虑与趋势判断..."
            if topic_label
            else f"正在为「{brand_name}」整理行业全景问题{_identity_suffix(identity)}，覆盖品类需求、场景选购、产品比较与后续抓取方向..."
        ),
    )

    try:
        # Build LLM prompt
        system_prompt, user_content = QuestionGenerationTool(
            mode="baseline_dynamic",
            brand_profile=brand_profile,
            competitors=competitors,
            platforms=_PLATFORMS,
            identity=identity,
            topic_keywords=topic_focus.get("topic_keywords"),
            topic_description=topic_focus.get("topic_description"),
        )

        model = _get_a3_model()
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
            logger.warning(
                "[A3] Empty questions from baseline LLM, falling back to brand mode"
            )
            return await _a3_brand_panorama_mode(state)

        # Enforce hard limit
        raw_questions = raw_questions[:_MAX_QUESTIONS]
        raw_questions = sanitize_generated_panorama_questions(
            raw_questions,
            explicit_brand_name,
            competitors,
        )

        # Validate brand question ratio
        if explicit_brand_name:
            validate_generated_baseline_questions(raw_questions, explicit_brand_name)

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

            flattened_questions.append(
                {
                    "id": q_id,
                    "text": core_question,
                    "category": q.get("category", "行业全景"),
                    "intent": q.get("user_intent", ""),
                    "stage": q.get("decision_stage", ""),
                    "platform": platform,
                }
            )

        question_count = len(simulated_questions)

        await send_progress_event(
            session_id=session_id,
            step="question_simulation",
            step_name="问题模拟生成",
            progress=1.0,
            message=(
                f"已围绕「{topic_label}」生成 {question_count} 个全景问题"
                if topic_label
                else f"品牌全景分析：已生成 {question_count} 个行业全景问题"
            ),
            status="completed",
        )

        detailed_response = (
            f"已围绕「{topic_label}」生成 {question_count} 个全景问题，详见右侧问题列表。"
            if topic_label
            else f"已为「{brand_name}」生成 {question_count} 个行业全景问题，详见右侧问题列表。"
        )

        await send_action_log_event(
            session_id,
            "agent_summary",
            detailed_response,
            step="question_simulation",
            is_complete=True,
        )

        # Save and send artifact to Canvas
        generated_payload = {
            "simulated_questions": simulated_questions,
            "generation_mode": "baseline_dynamic",
            "generation_context": _build_generation_context(
                identity,
                topic_focus,
                question_only=question_only,
            ),
        }

        await save_and_send_artifact(
            session_id=session_id,
            output_type="questionList",
            title="主题全景问题列表" if topic_label else "品牌全景问题列表",
            data={
                "simulatedQuestions": generated_payload,
                "questions": flattened_questions,
                "generationMode": (
                    "主题全景问题" if topic_label else "品牌全景分析（行业全景问题）"
                ),
            },
        )

        # Stage result
        categories = list(
            set(q.get("category", "") for q in simulated_questions if q.get("category"))
        )
        stage_result_data = {
            "count": question_count,
            "categories": categories,
            "examples": [
                q.get("core_question", "")[:50] for q in simulated_questions[:3]
            ],
        }
        await send_stage_result(
            session_id,
            "A3",
            "问题生成",
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
                    await task_svc.append_stage_result(
                        _UUID(task_id),
                        {
                            "stage": "A3",
                            "result_type": "questions",
                            "data": stage_result_data,
                            "stage_name": "问题生成",
                        },
                    )
            except Exception as e:
                logger.warning("[A3] Failed to persist stage_result: %s", e)
        latest_question_set_id = await _persist_draft_question_set(
            state,
            flattened_questions=flattened_questions,
            title=f"{topic_label}全景问题集" if topic_label else "品牌全景问题集",
            monitor_mode="panorama",
        )
        confirmation_update = await _question_set_confirmation_update(
            state,
            question_set_id=latest_question_set_id,
            monitor_mode="panorama",
            question_count=len(flattened_questions),
        )
        await _persist_brand_intelligence_questions(state, payload=generated_payload)

        # Dual-write: baseline_questions + questions
        return Command(
            update={
                "brand_profile": brand_profile,
                "simulated_questions": generated_payload,
                "baseline_questions": flattened_questions,  # Baseline channel (long-term)
                "questions": flattened_questions,  # Standard channel (A4 reads this)
                "latest_question_set_id": latest_question_set_id,
                "question_set_ids": (
                    [latest_question_set_id] if latest_question_set_id else []
                ),
                "current_step": "A3",
                "progress": 0.5,
                "confirmed_import_action": None,
                "user_decisions": _clear_question_import_state(state),
                **confirmation_update,
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
