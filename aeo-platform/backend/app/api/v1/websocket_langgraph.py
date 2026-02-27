"""WebSocket handlers for LangGraph workflow integration.

This module provides WebSocket endpoints that integrate with the LangGraph workflow.
Adapted for orchestrator-based dynamic routing (no hardcoded EXECUTION_STEPS).
"""

import json
import logging
from typing import Any, Literal, TypedDict
from uuid import UUID

from fastapi import APIRouter, WebSocket
from langchain_core.messages import HumanMessage, AIMessage

from app.workflow.graph import get_compiled_workflow
from app.workflow.state import AgentState
from app.core.database import AsyncSessionLocal
from app.core.websocket_server import manager as ws_session_manager
from app.services.message_service import MessageService
from app.services.entity_service import EntityService
from app.models.session import Session

from sqlalchemy import select

logger = logging.getLogger(__name__)
router = APIRouter()

# Sessions that have been recalled — forces next handle_user_message to
# bypass stale checkpointer state and rebuild from DB instead.
# NOTE: Module-level set — NOT shared across workers in multi-process deployments
# (e.g. gunicorn with multiple workers). For production, consider Redis or shared cache.
_recalled_sessions: set[str] = set()


# ---------------------------------------------------------------------------
# Confirmation Protocol Types
# ---------------------------------------------------------------------------
# These TypedDicts define the structured selection payloads sent by the
# frontend via the ``confirmation`` WebSocket event.  The ``type`` field
# discriminates between variants.

class PersonaPathSelection(TypedDict):
    """Frontend sends this when the user selects personas from the pipeline."""
    type: Literal["persona_path_selection"]
    selectedPersonaIds: list[str]
    selectedPersonaNames: list[str]


class SkipSelection(TypedDict):
    """Frontend sends this when the user clicks 'skip' on persona selection."""
    type: Literal["skip"]


# Union of all structured confirmation payloads
ConfirmationSelection = PersonaPathSelection | SkipSelection


# Step progression for inferring progress from restored state
_STEP_PROGRESS: dict[str, float] = {
    "A1": 0.2,
    "A2": 0.35,
    "A3": 0.5,
    "A4": 0.6,
    "A5": 0.9,
}


async def rebuild_state_from_db(
    session_id: str, entity_id: str | None = None
) -> dict[str, Any]:
    """Rebuild AgentState from database messages when MemorySaver state is lost.

    Scans all OUTPUT messages for the session and reconstructs agent outputs
    (brand_profile, competitors, personas, questions, fetch_results, metrics, report).
    Also rebuilds orchestrator_history from user/agent message pairs.

    Returns:
        A dict compatible with AgentState fields.
    """
    state: dict[str, Any] = {
        "session_id": session_id,
        "entity_id": entity_id,
        "messages": [],
        "brand_name": "",
        "official_website": "",
        "industry_hint": "",
        # A1
        "brand_profile": None,
        "competitors": None,
        "competitive_landscape": None,
        # A2
        "marketing_personas": None,
        # A3
        "simulated_questions": None,
        "questions": None,
        # A4
        "fetch_results": None,
        # A5
        "metrics": None,
        "report": None,
        # Execution control
        "current_step": "",
        "execution_status": "running",
        "progress": 0.0,
        "progress_message": "恢复中...",
        # Human-in-loop
        "pending_confirmation": None,
        "user_decisions": {},
        # Error
        "error_info": None,
        # Orchestrator
        "orchestrator_history": [],
        "orchestrator_reply": None,
        "next_action": None,
        "awaiting_user": False,
        "tool_call_args": None,
        "tool_call_id": None,
        "agent_retry_counts": {},
        # Execution control flags
        "auto_trigger_a5": False,
        "headless_mode": False,
        # Cycle 3 fields
        "task_id": None,
        "platform_filter": None,
        "preserved_fetch_results": None,
        # Baseline Analysis (Issue #4)
        "analysis_mode": None,
        "baseline_questions": None,
        "baseline_fetch_results": None,
        "baseline_metrics": None,
        "baseline_report": None,
    }

    async with AsyncSessionLocal() as db:
        # 1. Fetch entity info for brand_name / domain / industry
        if entity_id:
            try:
                entity_service = EntityService(db)
                entity_data = await entity_service.get_entity(entity_id)
                if entity_data:
                    state["brand_name"] = entity_data.get("name", "")
                    state["official_website"] = entity_data.get("domain", "")
                    state["industry_hint"] = entity_data.get("industry", "")
            except Exception as e:
                logger.warning(f"[Restore] Failed to load entity: {e}")

        # 2. Fetch all messages for this session
        message_service = MessageService(db)
        messages = await message_service.get_messages(
            session_id=UUID(session_id), limit=500
        )

    highest_step = ""

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        msg_type = msg.get("type", "text")

        # Rebuild orchestrator_history from user/agent text messages
        if role == "user":
            state["orchestrator_history"].append({"role": "user", "content": content})
            state["messages"].append(HumanMessage(content=content))
        elif role == "agent" and msg_type == "text" and content:
            state["orchestrator_history"].append(
                {"role": "assistant", "content": content}
            )
            state["messages"].append(AIMessage(content=content))

        # Extract artifacts from OUTPUT messages
        if msg_type == "output":
            output_type = msg.get("output_type", "")
            output_data = msg.get("output_data")
            if not output_data:
                continue
            # output_data may be a dict (already parsed) or a JSON string
            if isinstance(output_data, str):
                try:
                    output_data = json.loads(output_data)
                except (json.JSONDecodeError, TypeError):
                    continue
            if not isinstance(output_data, dict):
                continue

            if output_type == "workflow":
                current_step = output_data.get("currentStep", "")
                # A1 workflow output
                bp = output_data.get("brandProfile") or output_data.get(
                    "brand_profile"
                )
                if bp:
                    state["brand_profile"] = bp
                comps = output_data.get("competitors")
                if comps:
                    state["competitors"] = comps
                cl = output_data.get("competitive_landscape")
                if cl:
                    state["competitive_landscape"] = cl
                # A2 workflow output
                personas = output_data.get("personas") or output_data.get(
                    "user_personas"
                )
                mp = output_data.get("marketingPersonas") or output_data.get(
                    "marketing_personas"
                )
                if personas or mp:
                    state["marketing_personas"] = mp or {"user_personas": personas}
                # Track highest step
                if current_step and current_step > highest_step:
                    highest_step = current_step

            elif output_type == "questionList":
                sq = output_data.get("simulatedQuestions") or output_data.get(
                    "simulated_questions"
                )
                if sq:
                    state["simulated_questions"] = sq
                q = output_data.get("questions")
                if q:
                    state["questions"] = q
                # Baseline mode questions
                if state.get("analysis_mode") == "baseline":
                    state["baseline_questions"] = q or sq
                if "A3" > highest_step:
                    highest_step = "A3"

            elif output_type == "fetchResults":
                fr = output_data.get("fetchResults") or output_data.get(
                    "fetch_results"
                )
                if fr:
                    state["fetch_results"] = fr
                if "A4" > highest_step:
                    highest_step = "A4"

            elif output_type == "report":
                state["metrics"] = output_data.get("metrics") or {
                    "bwvs_index": output_data.get("overallScore", 0),
                }
                state["report"] = {
                    "executive_summary": output_data.get("executive_summary", ""),
                    "key_findings": output_data.get("key_findings", []),
                    "strengths": output_data.get("strengths", []),
                    "weaknesses": output_data.get("weaknesses", []),
                    "opportunities": output_data.get("opportunities", []),
                    "threats": output_data.get("threats", []),
                    "recommendations": output_data.get("recommendations", []),
                    "action_plan": output_data.get("action_plan", {}),
                }
                if "A5" > highest_step:
                    highest_step = "A5"

            elif output_type == "report_baseline":
                state["analysis_mode"] = "baseline"
                state["baseline_metrics"] = output_data.get("metrics_raw") or {
                    "bwvs_index": output_data.get("overallScore", 0),
                }
                state["baseline_report"] = {
                    "executive_summary": output_data.get("executive_summary", ""),
                    "key_findings": output_data.get("key_findings", []),
                    "strengths": output_data.get("strengths", []),
                    "weaknesses": output_data.get("weaknesses", []),
                }
                if "A5" > highest_step:
                    highest_step = "A5"

    # Set progress based on highest completed step
    if highest_step:
        state["current_step"] = highest_step
        state["progress"] = _STEP_PROGRESS.get(highest_step, 0.0)
        state["progress_message"] = f"已完成 {highest_step} 阶段"

    logger.info(
        f"[Restore] Rebuilt state for session {session_id}: "
        f"step={highest_step}, history_len={len(state['orchestrator_history'])}, "
        f"has_brand={state['brand_profile'] is not None}, "
        f"has_competitors={state['competitors'] is not None}"
    )

    return state


async def handle_user_message_langgraph(
    websocket: WebSocket, session_id: str, data: dict
):
    """Handle user message using LangGraph workflow.

    For new conversations: initializes state and starts orchestrator.
    For continued conversations (after user confirmation): adds user message
    to orchestrator_history and restarts from orchestrator.
    """
    content = data.get("content", "")
    context = data.get("context", [])
    brand_name = data.get("brand_name", "")
    official_website = data.get("official_website", "")
    industry_hint = data.get("industry_hint", "")

    # Build context-enhanced content for orchestrator
    enhanced_content = content
    if context:
        context_parts = []
        type_names = {"profile": "用户画像", "scenario": "使用场景", "intent": "互动意图"}
        for ctx in context:
            ctx_type = ctx.get("type", "")
            ctx_label = ctx.get("label", "")
            context_parts.append(f"[{type_names.get(ctx_type, ctx_type)}: {ctx_label}]")
        enhanced_content = content + "\n\n附加上下文: " + " ".join(context_parts)

    logger.info(
        f"[LangGraph] Processing message for session {session_id}: {content[:50]}..."
    )

    # Immediate acknowledgement — reduce perceived latency
    await ws_session_manager.emit_to_session(session_id, "thought_delta", {
        "content": "正在理解您的需求...",
        "is_delta": False,
        "is_complete": False,
    })

    # Save user message to database + lookup entity from session
    entity_id: str | None = None
    async with AsyncSessionLocal() as db:
        message_service = MessageService(db)
        try:
            saved = await message_service.save_message(
                session_id=UUID(session_id),
                role="user",
                content=content,
            )
            # Send DB UUID back so frontend can sync its local message ID
            await ws_session_manager.emit_to_session(
                session_id, "user_message_ack",
                {"message_id": str(saved["id"]), "content": content},
            )
        except Exception as e:
            logger.error(f"[LangGraph] Error saving user message: {e}")

        # Look up session's associated entity to auto-inject brand info
        try:
            result = await db.execute(
                select(Session).where(Session.id == UUID(session_id))
            )
            session_obj = result.scalar_one_or_none()
            if session_obj and session_obj.entity_id:
                entity_id = str(session_obj.entity_id)
                entity_service = EntityService(db)
                entity_data = await entity_service.get_entity(entity_id)
                if entity_data:
                    # Auto-inject brand info from entity (if not provided by client)
                    if not brand_name:
                        brand_name = entity_data.get("name", "")
                    if not official_website:
                        official_website = entity_data.get("domain", "")
                    if not industry_hint:
                        industry_hint = entity_data.get("industry", "")
                    logger.info(
                        f"[LangGraph] Auto-injected entity info: "
                        f"brand={brand_name}, domain={official_website}, "
                        f"industry={industry_hint}"
                    )
        except Exception as e:
            logger.error(f"[LangGraph] Error looking up entity: {e}")

    # Reset layer accumulator for this execution round
    from app.workflow.events import reset_session_layers
    reset_session_layers(session_id)

    workflow = None
    config = None
    try:
        # Get compiled workflow
        workflow = await get_compiled_workflow()

        # Configure thread (using session_id as thread_id)
        config = {
            "configurable": {
                "thread_id": session_id,
            }
        }

        # Check if there's an existing state (continued conversation)
        # If this session was just recalled, bypass stale checkpointer state
        # and force rebuild from DB (which reflects the post-recall reality).
        existing_state = None
        if session_id in _recalled_sessions:
            _recalled_sessions.discard(session_id)
            logger.info(f"[LangGraph] Session {session_id} was recalled, bypassing checkpointer")
        else:
            try:
                existing_state = workflow.get_state(config)
            except Exception:
                pass

        if (
            existing_state
            and existing_state.values
            and existing_state.values.get("orchestrator_history")
        ):
            # Continued conversation: add user message to orchestrator history
            state_values = dict(existing_state.values)
            history = list(state_values.get("orchestrator_history", []))
            history.append({
                "role": "user",
                "content": enhanced_content,
            })

            # Set A3 mode based on context profiles
            user_decisions = dict(state_values.get("user_decisions", {}))
            profile_contexts = [c for c in context if c.get("type") == "profile"]
            if profile_contexts:
                user_decisions["a3_mode"] = "persona"
                user_decisions["selected_persona_ids"] = [
                    c.get("label", "") for c in profile_contexts
                ]

            # Restart from orchestrator with updated history
            update_state: dict[str, Any] = {
                "orchestrator_history": history,
                "user_decisions": user_decisions,
                "awaiting_user": False,
                "messages": list(state_values.get("messages", []))
                + [HumanMessage(content=enhanced_content)],
            }

            # Stream workflow execution from orchestrator
            async for event in workflow.astream(update_state, config=config):
                await _process_langgraph_event(session_id, event)
        else:
            # MemorySaver has no state — try restoring from DB
            try:
                restored = await rebuild_state_from_db(session_id, entity_id)
                if restored.get("orchestrator_history"):
                    logger.info(
                        f"[LangGraph] Restored state from DB for session {session_id}"
                    )
                    restored["orchestrator_history"].append(
                        {"role": "user", "content": enhanced_content}
                    )
                    restored["messages"] = list(restored.get("messages", [])) + [
                        HumanMessage(content=enhanced_content)
                    ]
                    # Set A3 mode based on context profiles
                    profile_contexts = [c for c in context if c.get("type") == "profile"]
                    if profile_contexts:
                        user_decisions = dict(restored.get("user_decisions", {}))
                        user_decisions["a3_mode"] = "persona"
                        user_decisions["selected_persona_ids"] = [
                            c.get("label", "") for c in profile_contexts
                        ]
                        restored["user_decisions"] = user_decisions
                    async for event in workflow.astream(restored, config=config):
                        await _process_langgraph_event(session_id, event)
                    return
            except Exception as e:
                logger.warning(f"[LangGraph] DB state restoration failed: {e}")

            # Cycle 3, Module 1: Create AnalysisTask before starting workflow
            created_task_id: str | None = None
            try:
                # Look up user_id from session
                async with AsyncSessionLocal() as db:
                    result = await db.execute(
                        select(Session).where(Session.id == UUID(session_id))
                    )
                    session_obj = result.scalar_one_or_none()
                    if session_obj:
                        from app.services.task_service import TaskService
                        task_service = TaskService(db)
                        task = await task_service.create_task(
                            user_id=session_obj.user_id,
                            session_id=UUID(session_id),
                            brand_name=brand_name or content,
                            entity_id=UUID(entity_id) if entity_id else None,
                        )
                        created_task_id = str(task.id)
                        await task_service.start_task(task.id)
                        logger.info(
                            "[LangGraph] Created AnalysisTask %s for session %s",
                            created_task_id, session_id,
                        )
            except Exception as task_err:
                logger.warning(
                    "[LangGraph] Failed to create AnalysisTask: %s", task_err
                )

            # New conversation: initialize full state
            initial_state: AgentState = {
                "session_id": session_id,
                "entity_id": entity_id,
                "messages": [HumanMessage(content=enhanced_content)],
                "brand_name": brand_name or content,
                "official_website": official_website,
                "industry_hint": industry_hint,
                # A1 outputs
                "brand_profile": None,
                "competitors": None,
                "competitive_landscape": None,
                # A2 outputs
                "marketing_personas": None,
                # A3 outputs
                "simulated_questions": None,
                "questions": None,
                # A4 outputs
                "fetch_results": None,
                # A5 outputs
                "metrics": None,
                "report": None,
                # Execution control
                "current_step": "",
                "execution_status": "running",
                "progress": 0.0,
                "progress_message": "开始分析...",
                # Human-in-loop (legacy, kept for compatibility)
                "pending_confirmation": None,
                "user_decisions": {},
                # Error handling
                "error_info": None,
                # Orchestrator state
                "orchestrator_history": [
                    {"role": "user", "content": enhanced_content},
                ],
                "orchestrator_reply": None,
                "next_action": None,
                "awaiting_user": False,
                "tool_call_args": None,
                "tool_call_id": None,
                # Cycle 3: Task persistence + multi-turn
                "task_id": created_task_id,
                "platform_filter": None,
                "preserved_fetch_results": None,
                # Baseline Analysis (Issue #4)
                "analysis_mode": None,
                "baseline_questions": None,
                "baseline_fetch_results": None,
                "baseline_metrics": None,
                "baseline_report": None,
                # Execution control flags
                "auto_trigger_a5": False,
                "headless_mode": False,
                "agent_retry_counts": {},
            }

            # Stream workflow execution
            async for event in workflow.astream(initial_state, config=config):
                await _process_langgraph_event(session_id, event)

    except Exception as e:
        import traceback

        error_msg = str(e) or repr(e) or "未知错误"
        error_type = type(e).__name__
        logger.error(
            f"[LangGraph] Error processing message: [{error_type}] {error_msg}"
        )
        traceback.print_exc()

        await ws_session_manager.emit_to_websocket(
            websocket,
            "error",
            {
                "step": "workflow",
                "error": f"处理消息时出错: {error_msg}",
                "recoverable": True,
            },
        )
    finally:
        # Always save final agent message, even if astream raised an exception
        if workflow and config:
            try:
                await _save_final_message(session_id, workflow, config)
            except Exception as save_err:
                logger.error(f"[LangGraph] Error saving final message: {save_err}")


async def _process_langgraph_event(session_id: str, event: dict):
    """Process a LangGraph event.

    With the new orchestrator architecture, most events are sent directly
    via the events module (send_reply_event, send_action_log_event, etc.)
    from within the nodes themselves. This handler only processes
    high-level LangGraph lifecycle events.
    """
    # LangGraph astream returns node output dicts like {"orchestrator": {...}}
    # We mainly log these for debugging; actual WebSocket events are sent
    # from within the nodes via the events module.
    for node_name, node_output in event.items():
        logger.debug(f"[LangGraph] Node '{node_name}' completed")

        # Check if workflow reached an error state
        if isinstance(node_output, dict):
            error_info = node_output.get("error_info")
            if error_info:
                logger.warning(
                    f"[LangGraph] Error in {error_info.get('step', '?')}: "
                    f"{error_info.get('error', 'unknown')}"
                )


async def _save_final_message(session_id: str, workflow, config: dict):
    """Save final agent message to database, including accumulated layers."""
    from app.workflow.events import pop_accumulated_layers

    # Always pop layers to prevent memory leak, regardless of final_state
    layers = pop_accumulated_layers(session_id)

    try:
        # Get final state
        final_state = workflow.get_state(config)

        if final_state and final_state.values:
            state_values = final_state.values

            # Build content from orchestrator reply or report summary
            orchestrator_reply = state_values.get("orchestrator_reply", "")
            report = state_values.get("report") or {}
            metrics = state_values.get("metrics") or {}

            if orchestrator_reply:
                content = orchestrator_reply
            elif report:
                summary = report.get("executive_summary", "分析完成")
                bwvs = metrics.get("bwvs_index", 0)
                content = f"{summary}\n\nBWVS指数: {bwvs:.1f}"
            else:
                content = "分析完成"

            logger.info(f"[LangGraph] Saving agent message ({len(content)} chars) for session {session_id}")

            async with AsyncSessionLocal() as db:
                message_service = MessageService(db)
                await message_service.save_message(
                    session_id=UUID(session_id),
                    role="agent",
                    content=content,
                    metadata={
                        "metrics": metrics,
                        "report_summary": report.get("key_findings", []),
                        "layers": layers,
                    },
                )
            logger.info(f"[LangGraph] Agent message saved for session {session_id}")
        else:
            logger.warning(f"[LangGraph] No final state to save for session {session_id}")
    except Exception as e:
        logger.error(f"[LangGraph] Error saving final message: {e}")


async def handle_confirmation_langgraph(
    websocket: WebSocket, session_id: str, data: dict
):
    """Handle user confirmation/selection for LangGraph workflow.

    With the orchestrator architecture, confirmations are handled by adding
    the user's selection to orchestrator_history and restarting the workflow.
    """
    selection = data.get("selection", "")
    option_id = data.get("option_id", "")
    message = data.get("message", "")

    # Build a user message from the confirmation
    # selection can be a string (inline button label) or dict (structured selection)
    if isinstance(selection, dict):
        # Extract readable text from structured selection
        user_content = (
            message
            or selection.get("label", "")
            or selection.get("optionId", "")
            or option_id
            or "确认继续"
        )
    else:
        user_content = message or selection or option_id or "确认继续"

    logger.info(
        f"[LangGraph] Received confirmation for session {session_id}: "
        f"user_content={user_content!r}, selection={selection!r}"
    )

    # Persist the user's confirmation as a chat message so it survives page refresh
    async with AsyncSessionLocal() as db:
        message_service = MessageService(db)
        try:
            saved = await message_service.save_message(
                session_id=UUID(session_id),
                role="user",
                content=user_content,
            )
            await ws_session_manager.emit_to_session(
                session_id, "user_message_ack",
                {"message_id": str(saved["id"]), "content": user_content},
            )
        except Exception as e:
            logger.error(f"[LangGraph] Error saving confirmation message: {e}")

    workflow = None
    config = None
    try:
        workflow = await get_compiled_workflow()
        config = {
            "configurable": {
                "thread_id": session_id,
            }
        }

        # Get current state
        current_state = workflow.get_state(config)
        if not current_state or not current_state.values:
            await ws_session_manager.emit_to_websocket(
                websocket,
                "error",
                {"message": "无法获取当前工作流状态"},
            )
            return

        state_values = dict(current_state.values)
        history = list(state_values.get("orchestrator_history", []))
        user_decisions = dict(state_values.get("user_decisions", {}))

        # Parse structured selection — see ConfirmationSelection type above
        if isinstance(selection, dict) and selection.get("type") == "persona_path_selection":
            sel: PersonaPathSelection = selection  # type: ignore[assignment]
            selected_ids = sel.get("selectedPersonaIds", [])
            selected_names = sel.get("selectedPersonaNames", [])
            user_content = f"用户选择了以下画像进行聚焦分析：{', '.join(selected_names)}"
            user_decisions["a3_mode"] = "persona"
            user_decisions["selected_persona_ids"] = selected_names  # Use names for A3 matching
            user_decisions["selected_persona_names"] = selected_names
            logger.info(
                f"[LangGraph] Persona selection: ids={selected_ids}, names={selected_names}"
            )
        elif isinstance(selection, dict) and selection.get("type") == "skip":
            user_content = "用户选择跳过画像聚焦，使用品牌全景模式生成问题"
            user_decisions["a3_mode"] = "brand"
            logger.info("[LangGraph] User skipped persona selection, using brand mode")
        elif isinstance(selection, dict) and selection.get("optionId"):
            # Inline confirmation sends { optionId: "persona_focused" } or { optionId: "brand_panorama" }
            opt_id = selection["optionId"]
            if opt_id == "persona_focused":
                user_content = "用户选择聚焦画像分析"
                user_decisions["a3_mode"] = "persona"
                logger.info("[LangGraph] Inline confirmation: persona_focused mode")
            elif opt_id == "brand_panorama":
                user_content = "用户选择品牌全景分析"
                user_decisions["a3_mode"] = "brand"
                logger.info("[LangGraph] Inline confirmation: brand_panorama mode")
            else:
                user_content = selection.get("label", opt_id)
                logger.info(f"[LangGraph] Inline confirmation: optionId={opt_id}")
        elif isinstance(selection, str) and selection in ("聚焦画像分析", "开始场景细化分析"):
            # Plain text label from inline confirmation button click
            user_decisions["a3_mode"] = "persona"
            user_content = selection
            logger.info(f"[LangGraph] Text confirmation mapped to persona mode: {selection}")
        elif isinstance(selection, str) and selection in ("品牌全景分析",):
            user_decisions["a3_mode"] = "brand"
            user_content = selection
            logger.info(f"[LangGraph] Text confirmation mapped to brand mode: {selection}")

        history.append({
            "role": "user",
            "content": user_content,
        })

        # Restart workflow from orchestrator
        update_state: dict[str, Any] = {
            "orchestrator_history": history,
            "user_decisions": user_decisions,
            "awaiting_user": False,
        }

        async for event in workflow.astream(update_state, config=config):
            await _process_langgraph_event(session_id, event)

    except Exception as e:
        import traceback

        error_msg = str(e) or repr(e) or "未知错误"
        error_type = type(e).__name__
        logger.error(
            f"[LangGraph] Error handling confirmation: [{error_type}] {error_msg}"
        )
        traceback.print_exc()

        # Use consistent error format matching events.py send_error_event
        await ws_session_manager.emit_to_websocket(
            websocket,
            "error",
            {
                "step": "confirmation",
                "error": f"处理确认时出错: {error_msg}",
                "recoverable": True,
            },
        )
    finally:
        # Always save final agent message after confirmation workflow
        if workflow and config:
            try:
                await _save_final_message(session_id, workflow, config)
            except Exception as save_err:
                logger.error(f"[LangGraph] Error saving final message after confirmation: {save_err}")


async def handle_recall_langgraph(
    websocket: WebSocket, session_id: str, data: dict
) -> None:
    """Handle recall: delete target message and everything after it.

    Pure DB deletion — no automatic re-execution. The user will edit
    the message content in the input box and manually re-send, which
    goes through the normal handle_user_message path.
    """
    message_id = data.get("message_id")
    if not message_id:
        await ws_session_manager.emit_to_websocket(
            websocket, "error", {"message": "缺少 message_id"}
        )
        return

    # 1. Delete target message and everything after in DB
    async with AsyncSessionLocal() as db:
        svc = MessageService(db)
        result = await svc.rollback_from(UUID(session_id), UUID(message_id))

    if result.get("status") == "not_found":
        await ws_session_manager.emit_to_websocket(
            websocket, "error", {
                "message": "回退失败：消息不存在或无权限",
                "recoverable": True,
            }
        )
        return

    deleted = result.get("deleted_count", 0)
    logger.info(f"[Recall] Deleted {deleted} messages from session {session_id}")

    # 2. Mark session so next handle_user_message bypasses stale checkpointer
    _recalled_sessions.add(session_id)

    # 3. Notify frontend
    await ws_session_manager.emit_to_websocket(
        websocket,
        "recall_complete",
        {"message_id": message_id, "deleted_count": deleted},
    )


# Export for use in main websocket server
__all__ = [
    "handle_user_message_langgraph",
    "handle_confirmation_langgraph",
    "handle_recall_langgraph",
]
