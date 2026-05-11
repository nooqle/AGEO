"""LangGraph nodes for Specta AI workflow.

This module defines the node functions for each step (A1-A5) in the workflow.
Each node wraps the corresponding agent logic and handles state updates.
"""

import logging
from datetime import datetime
from uuid import uuid4

from langgraph.types import Command

from app.workflow.state import AgentState
from app.workflow.events import (
    send_progress_event,
    send_tpaor_event,
    send_action_log_event,
    send_confirmation_request,
    send_error_event,
    send_stage_result,
)
from app.workflow.nodes_streaming import call_llm_streaming
from app.workflow.summaries import generate_a1_summary
from app.core.llm import BaseLLMModel
from app.core.llm.task_routing import get_a1_llm_model, get_a2_llm_model
from app.core.utils import (
    extract_json_from_content,
    load_prompt_template,
    render_prompt,
)
from app.tools.persona_generation import (
    PersonaGenerationTool,
    build_persona_pipeline_data,
    build_persona_retry_messages,
    normalize_persona_payload,
    validate_persona_payload,
)
from app.tools.a1_evidence import (
    build_a1_web_search_tool,
    normalize_evidence_sources,
    repair_a1_website_fields,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Helper Functions
# ============================================================================


def get_llm_model_compat() -> BaseLLMModel:
    """Get LLM model instance (thin wrapper for backward compat)."""
    return get_a1_llm_model()


def _get_a2_model() -> BaseLLMModel:
    """Get A2 persona generation model from the canonical routing profile."""

    return get_a2_llm_model()


def parse_llm_response(response) -> dict | None:
    """Parse MiniMax response and extract JSON data."""
    content = response.content if hasattr(response, "content") else str(response)
    return extract_json_from_content(content)


# ============================================================================
# A1 Quality Hardening (Cycle 3, Module 3)
# ============================================================================

# Field alias mapping for normalization
_A1_FIELD_ALIASES = {
    "core_products": ["main_products", "products", "key_products", "product_list"],
    "brand_keywords": ["keywords", "key_words", "brand_tags"],
    "brand_positioning": ["positioning", "market_positioning"],
    "brand_name_en": ["english_name", "name_en", "en_name"],
    "description": ["brand_description", "desc", "overview"],
}


def _validate_a1_output(
    brand_profile: dict, competitors: list
) -> tuple[bool, list[str]]:
    """Validate A1 output against required schema.

    Returns:
        (is_valid, list_of_issues)
    """
    issues: list[str] = []

    # Validate brand_profile required fields
    required_str_fields = ["brand_name", "industry", "brand_positioning"]
    for field in required_str_fields:
        value = brand_profile.get(field)
        if not value or (isinstance(value, str) and not value.strip()):
            issues.append(f"brand_profile.{field} 为空")

    # description should be at least 20 chars
    desc = brand_profile.get("description", "")
    if not desc or (isinstance(desc, str) and len(desc.strip()) < 20):
        issues.append(
            f"brand_profile.description 过短 ({len(desc) if desc else 0} 字符，至少需要20)"
        )

    # core_products should be a non-empty list
    cp = brand_profile.get("core_products")
    if not cp or not isinstance(cp, list) or len(cp) == 0:
        issues.append("brand_profile.core_products 为空列表")

    # brand_keywords should have at least 3 items
    kw = brand_profile.get("brand_keywords")
    if not kw or not isinstance(kw, list) or len(kw) < 3:
        issues.append(
            f"brand_profile.brand_keywords 不足 ({len(kw) if isinstance(kw, list) else 0} 个，至少需要3)"
        )

    # Validate competitors: need at least 3
    MIN_COMPETITORS = 3
    if len(competitors) < MIN_COMPETITORS:
        issues.append(f"仅找到 {len(competitors)} 个竞品 (至少需要 {MIN_COMPETITORS})")

    for i, comp in enumerate(competitors):
        if not comp.get("name"):
            issues.append(f"competitor[{i}].name 为空")
        if not comp.get("description"):
            issues.append(f"competitor[{i}].description 为空")

    return (len(issues) == 0, issues)


def _normalize_a1_fields(data: dict) -> dict:
    """Normalize A1 brand_profile field names and fill defaults.

    Handles common LLM output inconsistencies like 'main_products' vs 'core_products'.
    """
    normalized = dict(data)

    for canonical, aliases in _A1_FIELD_ALIASES.items():
        if not normalized.get(canonical):
            for alias in aliases:
                if normalized.get(alias):
                    normalized[canonical] = normalized.pop(alias)
                    break

    # Fill remaining empty required fields with safe defaults
    normalized.setdefault("core_products", [])
    normalized.setdefault("brand_keywords", [])
    normalized.setdefault("brand_positioning", "")
    normalized.setdefault("description", "")
    normalized.setdefault("brand_name_en", "")
    normalized.setdefault("industry", "")

    return normalized


def _normalize_competitors(competitors: list) -> list:
    """Normalize competitor data and ensure minimum quality."""
    normalized = []
    for comp in competitors:
        c = dict(comp)
        c.setdefault("name", "")
        c.setdefault("description", "")
        c.setdefault("relevance_score", 50)
        c.setdefault("competition_type", "direct")
        c.setdefault("core_products", [])
        if c["name"]:  # Only keep competitors with names
            normalized.append(c)
    return normalized


def _build_a1_retry_prompt(
    brand_name: str,
    issues: list[str],
    existing_profile: dict,
    existing_competitors: list,
) -> str:
    """Build a focused retry prompt addressing specific validation issues."""
    issues_text = "\n".join(f"  - {issue}" for issue in issues)

    existing_data = ""
    if existing_profile:
        existing_data += "\n已有的品牌信息（请在此基础上补充完善）:\n"
        existing_data += f"  品牌名: {existing_profile.get('brand_name', brand_name)}\n"
        existing_data += f"  行业: {existing_profile.get('industry', '未知')}\n"
        existing_data += f"  描述: {existing_profile.get('description', '')[:100]}\n"

    if existing_competitors:
        comp_names = [c.get("name", "") for c in existing_competitors if c.get("name")]
        existing_data += f"  已有竞品: {', '.join(comp_names)}\n"

    return f"""你之前的品牌分析输出存在以下质量问题:
{issues_text}

{existing_data}

请重新输出完整的品牌分析JSON，特别注意修正上述问题。

必须确保:
1. brand_profile 包含所有字段: brand_name, brand_name_en, industry, description(至少50字),
   core_products(至少1个), brand_keywords(至少3个), brand_positioning
2. competitors 至少包含3个直接竞品，每个竞品必须有 name, description, relevance_score
3. 行业分类要具体（如"消费电子"而非"科技"）
4. 字段名使用规范名称: core_products(不是main_products), brand_keywords(不是keywords)

品牌: {brand_name}

⚠️ 直接以 {{ 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


# ============================================================================
# A1 Node: Brand Competition Analysis
# ============================================================================


async def a1_brand_node(state: AgentState) -> Command:
    """A1: Brand profile and competitor analysis.

    Analyzes the brand to create a comprehensive profile and identify competitors.
    """
    session_id = state["session_id"]
    brand_name = state.get("brand_name")

    if not brand_name:
        return Command(
            update={
                "error_info": {
                    "step": "A1",
                    "error": "Brand name is required",
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
            },
        )

    # Send progress event
    await send_progress_event(
        session_id=session_id,
        step="brand_analysis",
        step_name="品牌信息采集",
        progress=0.15,
        message=f"开始分析品牌: {brand_name}",
        status="running",
    )

    await send_tpaor_event(
        session_id, "thought", f"正在分析品牌 '{brand_name}' 的信息和竞品数据..."
    )

    task_id = state.get("task_id")

    try:
        # Load system prompt
        try:
            system_prompt = load_prompt_template("brand_competition_agent")
        except FileNotFoundError:
            # Fallback prompt
            system_prompt = _get_a1_fallback_prompt()

        # Build user content
        user_content = render_prompt(
            "请分析以下品牌：\n\n"
            "品牌名称: {{brand_name}}\n"
            "{% if official_website %}官网: {{official_website}}\n{% endif %}"
            "{% if industry_hint %}行业提示: {{industry_hint}}\n{% endif %}\n"
            "任务: 请分析这个品牌，收集其档案信息，并识别8-12个主要竞品。",
            {
                "brand_name": brand_name,
                "official_website": state.get("official_website"),
                "industry_hint": state.get("industry_hint"),
            },
        )

        # Call LLM with streaming and TPAOR events
        # GLM5 web_search: server-side search, no tool_calls returned.
        # MiniMax ignores non-function tool types gracefully.
        a1_web_search_tool = build_a1_web_search_tool()

        model = get_llm_model_compat()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="brand_analysis",
            step_name="品牌信息采集",
            task_id=state.get("task_id"),
            progress_start=0.35,
            progress_end=0.8,
            tools=[a1_web_search_tool],
        )

        # Parse response
        data = parse_llm_response(response)

        if not data:
            raise ValueError(f"Failed to parse LLM response. Raw content: {response.content[:500] if hasattr(response, 'content') else 'N/A'}...")

        # Handle both nested format (with brand_profile/competitors keys) and flat format
        # Flat format: data directly contains brand fields
        # Nested format: data["brand_profile"] contains brand fields
        if "brand_profile" not in data and "competitors" not in data:
            # Assume flat format - wrap it
            logger.info("[A1] Converting flat format to nested format")
            brand_profile = {
                "brand_name": data.get("brand_name", brand_name),
                "brand_name_en": data.get("brand_name_en", ""),
                "official_website": data.get("official_website", ""),
                "industry": data.get("industry", ""),
                "description": data.get("description", ""),
                "core_products": data.get("core_products", []),
                "brand_keywords": data.get("brand_keywords", []),
                "brand_positioning": data.get("brand_positioning", ""),
                "target_audience": data.get("target_audience", ""),
                "founded_year": data.get("founded_year", ""),
                "price_positioning": data.get("price_positioning", ""),
            }
            competitors = data.get("competitors", [])
            competitive_landscape = data.get("competitive_landscape")
            data = {
                "brand_profile": brand_profile,
                "competitors": competitors,
                "competitive_landscape": competitive_landscape,
                "evidence_sources": data.get("evidence_sources", []),
            }

        if "brand_profile" not in data:
            raise ValueError(f"Missing 'brand_profile' in response. Available keys: {list(data.keys())}")

        if "competitors" not in data:
            raise ValueError(f"Missing 'competitors' in response. Available keys: {list(data.keys())}")

        # Cycle 3 Module 3: A1 Quality Hardening
        # Step 1: Normalize field names (e.g., main_products → core_products)
        data["brand_profile"] = _normalize_a1_fields(data["brand_profile"])
        data["competitors"] = _normalize_competitors(data.get("competitors", []))
        data["evidence_sources"] = normalize_evidence_sources(
            data.get("evidence_sources")
        )

        # Step 2: Validate output quality
        is_valid, issues = _validate_a1_output(
            data["brand_profile"], data["competitors"]
        )

        # Step 3: Retry once with focused prompt if validation fails
        if not is_valid:
            logger.warning(f"[A1] Validation failed ({len(issues)} issues): {issues}")

            retry_prompt = _build_a1_retry_prompt(
                brand_name, issues, data["brand_profile"], data["competitors"]
            )

            try:
                retry_response = await call_llm_streaming(
                    session_id=session_id,
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": retry_prompt},
                    ],
                    step="brand_analysis",
                    step_name="品牌信息采集(重试)",
                    task_id=state.get("task_id"),
                    progress_start=0.8,
                    progress_end=0.95,
                    tools=[a1_web_search_tool],
                )
                retry_data = parse_llm_response(retry_response)
                if retry_data:
                    # Apply normalization to retry output
                    retry_bp = retry_data.get("brand_profile", retry_data)
                    retry_comps = retry_data.get("competitors", [])

                    if "brand_profile" not in retry_data:
                        # Flat format from retry
                        retry_bp = _normalize_a1_fields(retry_data)
                        retry_comps = _normalize_competitors(retry_data.get("competitors", []))
                    else:
                        retry_bp = _normalize_a1_fields(retry_bp)
                        retry_comps = _normalize_competitors(retry_comps)

                    retry_valid, retry_issues = _validate_a1_output(retry_bp, retry_comps)

                    if retry_valid:
                        logger.info("[A1] Retry succeeded, using retry data")
                        data["brand_profile"] = retry_bp
                        data["competitors"] = retry_comps
                        if "competitive_landscape" in retry_data:
                            data["competitive_landscape"] = retry_data["competitive_landscape"]
                        retry_sources = normalize_evidence_sources(
                            retry_data.get("evidence_sources")
                        )
                        if retry_sources:
                            data["evidence_sources"] = retry_sources
                        is_valid = True
                    else:
                        logger.warning(
                            f"[A1] Retry still has {len(retry_issues)} issues, using best-effort data"
                        )
                        # Merge: prefer retry data if it's better
                        if len(retry_issues) < len(issues):
                            data["brand_profile"] = retry_bp
                            data["competitors"] = retry_comps
            except Exception as retry_err:
                logger.warning(f"[A1] Retry LLM call failed: {retry_err}")

        # Ensure brand_name is always populated
        if not data["brand_profile"].get("brand_name"):
            data["brand_profile"]["brand_name"] = brand_name

        data["brand_profile"], data["competitors"] = await repair_a1_website_fields(
            data["brand_profile"],
            data["competitors"],
            data.get("evidence_sources", []),
        )

        # Send completion event
        await send_progress_event(
            session_id=session_id,
            step="brand_analysis",
            step_name="品牌信息采集",
            progress=1.0,
            message=f"成功分析品牌 '{brand_name}'，识别出 {len(data.get('competitors', []))} 个竞品",
            status="completed",
        )

        summary = generate_a1_summary(
            data.get("brand_profile"),
            data.get("competitors"),
            data.get("competitive_landscape"),
        )

        await send_action_log_event(
            session_id, "agent_summary", summary, step="brand_analysis", is_complete=True
        )

        # Save and send brand profile artifact to Canvas
        from app.workflow.events import save_and_send_artifact
        await save_and_send_artifact(
            session_id=session_id,
            output_type="workflow",
            title="品牌档案",
            data={
                "brandProfile": data["brand_profile"],
                "brand_profile": data["brand_profile"],
                "competitors": data["competitors"],
                "competitive_landscape": data.get("competitive_landscape"),
                "evidence_sources": data.get("evidence_sources", []),
                "currentStep": "A1",
                "executionStatus": "completed",
                "completedSteps": ["A1"],
            },
        )

        # Stage result: 让用户在等待期间看到品牌分析阶段性产出
        await send_stage_result(
            session_id, "A1", "品牌分析",
            result_type="brand_profile",
            data={
                "brand_name": data["brand_profile"].get("brand_name", ""),
                "industry": data["brand_profile"].get("industry", ""),
                "competitors": [c.get("name", "") for c in data.get("competitors", [])[:5]],
                "key_products": ", ".join(data["brand_profile"].get("core_products", []))[:100],
            },
        )

        # Task milestone: A1 completed (Cycle 3, Module 1)
        if task_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.task_service import TaskService
                from uuid import UUID as _UUID
                async with AsyncSessionLocal() as db:
                    ts = TaskService(db)
                    await ts.append_stage_result(_UUID(task_id), {
                        "stage": "A1",
                        "stage_name": "品牌分析",
                        "result_type": "brand_profile",
                        "data": {
                            "brand_name": data["brand_profile"].get("brand_name", ""),
                            "industry": data["brand_profile"].get("industry", ""),
                            "competitors": [c.get("name", "") for c in data.get("competitors", [])[:5]],
                        },
                    })
            except Exception as te:
                logger.warning("[A1] TaskService milestone failed: %s", te)

        # Resolve entity_id: look up or create entity from brand profile
        resolved_entity_id = state.get("entity_id")
        if not resolved_entity_id:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.entity_service import EntityService
                async with AsyncSessionLocal() as db:
                    entity_service = EntityService(db)
                    # Try to find existing entity by brand name
                    bp = data["brand_profile"]
                    entities = await entity_service.list_entities()
                    for ent in entities:
                        if ent.get("name") == bp.get("brand_name"):
                            resolved_entity_id = str(ent["id"])
                            break
            except Exception as ent_err:
                logger.warning(f"[A1] Failed to resolve entity_id: {ent_err}")

        # Write A1 materials into Knowledge Workspace for future retrieval.
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.knowledge_workspace_service import (
                KnowledgeWorkspaceService,
            )

            async with AsyncSessionLocal() as db:
                knowledge_service = KnowledgeWorkspaceService(db)
                await knowledge_service.ingest_a1_facts(
                    entity_id=resolved_entity_id,
                    session_id=session_id,
                    task_id=task_id,
                    run_id=state.get("run_id"),
                    brand_profile=data["brand_profile"],
                    competitors=data["competitors"],
                )
        except Exception as knowledge_err:
            logger.warning("[A1] Knowledge write-back failed: %s", knowledge_err)

        return Command(
            update={
                "brand_profile": data["brand_profile"],
                "competitors": data["competitors"],
                "competitive_landscape": data.get("competitive_landscape"),
                "a1_evidence_sources": data.get("evidence_sources", []),
                "current_step": "A1",
                "progress": 0.2,
                "entity_id": resolved_entity_id,
            },
        )

    except Exception as e:
        await send_error_event(session_id, "A1", str(e), recoverable=False)

        return Command(
            update={
                "error_info": {
                    "step": "A1",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                "execution_status": "error",
            },
        )


def _get_a1_fallback_prompt() -> str:
    """Fallback system prompt for A1."""
    return """你是 Specta AI 平台的品牌竞品分析专家。你的任务是通过搜索和分析，为目标品牌建立完整的品牌档案，并识别出 8-12 个主要竞品。

## 核心职责

1. **品牌档案收集**：收集目标品牌的基础信息、核心产品、品牌定位等
2. **行业识别**：准确识别品牌所属行业和市场定位
3. **竞品识别**：找出 8-12 个相关竞品
4. **竞争格局分析**：分析整体市场竞争态势

## 输出格式

你必须以 JSON 格式输出分析结果：

{
  "brand_profile": {
    "brand_name": "品牌中文名",
    "brand_name_en": "品牌英文名",
    "official_website": "官网地址",
    "industry": "所属行业",
    "description": "品牌描述",
    "core_products": ["产品1", "产品2"],
    "brand_keywords": ["关键词1", "关键词2"],
    "brand_positioning": "品牌定位",
    "target_audience": "目标受众",
    "founded_year": "成立年份",
    "price_positioning": "价格定位"
  },
  "competitors": [
    {
      "name": "竞品名称",
      "name_en": "竞品英文名",
      "website": "竞品官网",
      "description": "竞品描述",
      "relevance_score": 8,
      "competition_type": "直接竞争/间接竞争/潜在竞争",
      "core_products": ["产品1"],
      "competitive_advantage": "核心优势"
    }
  ],
  "competitive_landscape": {
    "market_overview": "市场整体概况",
    "competition_intensity": "高/中/低",
    "key_battlegrounds": ["竞争维度1", "竞争维度2"]
  },
  "evidence_sources": [
    {
      "title": "来源标题",
      "link": "来源链接",
      "media": "媒体/站点名称",
      "publish_date": "发布日期",
      "refer": "引用编号",
      "usage": "用于核验官网/核心产品/竞品"
    }
  ]
}

⚠️ 重要：直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


# ============================================================================
# A2 Decision Node: Human-in-loop for A2
# ============================================================================


async def a2_decision_node(state: AgentState) -> Command:
    """Decision point for A2: Ask user if they want to generate personas.

    Uses state machine pattern:
    1. If no pending confirmation, send request and wait
    2. If pending confirmation exists, check if user responded
    3. Route based on user decision
    """
    session_id = state["session_id"]
    user_decisions = state.get("user_decisions", {})
    pending_confirmation = state.get("pending_confirmation")

    # Check if user already made a decision
    if "skip_a2" in user_decisions:
        if user_decisions["skip_a2"]:
            # Skip A2, go directly to A3 decision
            return Command(goto="a3_decision")
        else:
            # User wants to run A2
            return Command(goto="a2_persona")

    # Check if we have a pending confirmation with response
    if pending_confirmation and pending_confirmation.get("step_id") == "A2":
        user_response = pending_confirmation.get("user_response")
        if user_response:
            # User has responded, process the decision
            selection = user_response.get("selection", "continue")
            if selection == "skip":
                return Command(
                    goto="a3_decision",
                    update={
                        "user_decisions": {**user_decisions, "skip_a2": True},
                        "pending_confirmation": None,
                        "progress": 0.3,
                    },
                )
            else:
                return Command(
                    goto="a2_persona",
                    update={
                        "user_decisions": {**user_decisions, "skip_a2": False},
                        "pending_confirmation": None,
                    },
                )

    brand_name = (state.get("brand_profile") or {}).get("brand_name", "")
    brand_prefix = f"品牌「{brand_name}」" if brand_name else "当前品牌"

    # Send confirmation request
    await send_confirmation_request(
        session_id=session_id,
        step_id="A2",
        step_name="用户画像生成",
        message=f"{brand_prefix}是否需要生成用户画像？继续将生成画像以提升问题模拟精准度，跳过将直接基于品牌信息生成问题。",
        options=[
            {
                "id": "continue",
                "label": "继续 - 生成画像",
                "description": "基于品牌信息生成详细的用户画像",
            },
            {
                "id": "skip",
                "label": "跳过 - 直接生成问题",
                "description": "跳过画像，直接生成模拟问题",
            },
        ],
    )

    # Set pending confirmation and return to wait for user response
    # The workflow will re-enter this node when user responds
    return Command(
        goto="a2_decision",  # Loop back to this node to check for response
        update={
            "pending_confirmation": {
                "step_id": "A2",
                "step_name": "用户画像生成",
                "message": f"等待用户确认是否为{brand_prefix}生成画像",
                "options": [
                    {"id": "continue", "label": "继续 - 生成画像"},
                    {"id": "skip", "label": "跳过 - 直接生成问题"},
                ],
            },
        },
    )


# ============================================================================
# A2 Node: Marketing Persona Generation
# ============================================================================


async def a2_persona_node(state: AgentState) -> Command:
    """A2: Generate marketing personas with simplified structure.

    Uses a simplified JSON Schema to avoid LLM output truncation.
    Includes retry logic: first attempt with standard prompt, retry with
    even simpler prompt if parsing fails or output is truncated.
    """
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile")
    competitors = state.get("competitors") or []

    if brand_profile is None:
        logger.warning("[A2] Skipped: brand_profile is None")
        return Command(
            update={
                "current_step": "A2",
                "marketing_personas": None,
            },
        )

    await send_progress_event(
        session_id=session_id,
        step="persona_generation",
        step_name="用户画像生成",
        progress=0.25,
        message=f"开始生成用户画像: {brand_profile.get('brand_name', '')}",
    )

    try:
        model = _get_a2_model()
        system_prompt, user_content = PersonaGenerationTool(
            brand_profile,
            competitors,
        )

        # --- Attempt 1: standard simplified prompt ---
        data = await _a2_call_and_parse(
            session_id=session_id,
            model=model,
            system_prompt=system_prompt,
            user_content=user_content,
            progress_start=0.3,
            progress_end=0.7,
            attempt=1,
        )

        # --- Attempt 2: retry with minimal prompt if first attempt failed ---
        if data is None:
            logger.warning("[A2] Attempt 1 failed, retrying with minimal prompt...")
            await send_progress_event(
                session_id=session_id,
                step="persona_generation",
                step_name="用户画像生成",
                progress=0.5,
                message="首次生成失败，正在重试...",
                status="running",
            )
            retry_system_prompt, retry_user_content = build_persona_retry_messages(
                brand_profile,
                competitors,
            )
            data = await _a2_call_and_parse(
                session_id=session_id,
                model=model,
                system_prompt=retry_system_prompt,
                user_content=retry_user_content,
                progress_start=0.7,
                progress_end=0.9,
                attempt=2,
            )

        if data is None:
            raise RuntimeError(
                "[A2] 用户画像生成失败：两次尝试均未能获取有效的 JSON 数据。"
                "可能原因：LLM 输出截断或格式异常。"
            )

        # Normalize field names (camelCase → snake_case)
        if "userPersonas" in data and "user_personas" not in data:
            data["user_personas"] = data["userPersonas"]
        if "marketingScenarios" in data and "marketing_scenarios" not in data:
            data["marketing_scenarios"] = data["marketingScenarios"]

        personas = data.get("user_personas", [])

        # Add backward-compatible field names for downstream consumers
        # (orchestrator_node, touchpoint_service, frontend use persona_name/persona_description)
        for p in personas:
            if "name" in p and "persona_name" not in p:
                p["persona_name"] = p["name"]
            if "description" in p and "persona_description" not in p:
                p["persona_description"] = p["description"]
            if "priority" in p and "persona_priority" not in p:
                p["persona_priority"] = p["priority"]

        persona_count = len(personas)

        try:
            await send_progress_event(
                session_id=session_id,
                step="persona_generation",
                step_name="用户画像生成",
                progress=1.0,
                message=f"成功生成 {persona_count} 个用户画像",
                status="completed",
            )
        except Exception as e:
            logger.warning("[A2] Failed to send completion progress: %s", e)

        try:
            await send_action_log_event(
                session_id,
                "agent_complete",
                f"用户画像生成完成，共 {persona_count} 个画像",
                step="persona_generation",
                is_complete=True,
            )
        except Exception as e:
            logger.warning("[A2] Failed to send completion action log: %s", e)

        request_id = f"a2_persona_selection_{uuid4().hex}"

        # Build pipeline data (3-column: profile → scenario → intent)
        try:
            pipeline_data = build_persona_pipeline_data(personas)
        except Exception as e:
            logger.warning("[A2] Failed to build pipeline data: %s", e)
            pipeline_data = build_persona_pipeline_data([])

        # Send pipeline artifact with selection capability (A2 deliverable)
        from app.workflow.events import save_and_send_artifact
        await save_and_send_artifact(
            session_id=session_id,
            output_type="pipeline",
            title="营销触点地图",
            data={
                "pipeline": pipeline_data,
                "requestId": request_id,
                "marketing_personas": data,  # Persist for state rebuild after restart
                "maxSelection": 3,
                "minSelection": 1,
                "description": "请在管道图中选择您希望重点分析的用户画像（可多选）",
            },
        )

        # Stage result: 让用户在等待期间看到画像阶段性产出
        stage_result_data = {
            "count": len(personas),
            "personas": [
                p.get("persona_name", p.get("name", "")) for p in personas[:4]
            ],
        }
        try:
            await send_stage_result(
                session_id, "A2", "用户画像",
                result_type="personas",
                data=stage_result_data,
            )
        except Exception as e:
            logger.warning("[A2] Failed to send stage_result: %s", e)

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
                        "stage": "A2",
                        "result_type": "personas",
                        "data": stage_result_data,
                        "stage_name": "用户画像",
                    })
            except Exception as e:
                logger.warning("[A2] Failed to persist stage_result: %s", e)

        return Command(
            goto="wait_for_user",
            update={
                "marketing_personas": data,
                "current_step": "A2",
                "progress": 0.4,
                "awaiting_user": True,
                "execution_status": "awaiting_user",
                "pending_confirmation": {
                    "step_id": "A2_PERSONA_SELECTION",
                    "step_name": "选择用户画像",
                    "message": "请在营销触点地图中选择您希望重点分析的用户画像。",
                    "request_id": request_id,
                    "options": [
                        {"id": "persona_path_selection", "label": "确认选择画像"},
                        {"id": "skip", "label": "全景分析所有画像"},
                    ],
                },
            },
        )

    except Exception as e:
        logger.error("[A2] Failed: %s", e, exc_info=True)

        # Layer 2 degradation: A2 failure does not block pipeline
        from app.workflow.resilience import DegradationRegistry

        if not DegradationRegistry.should_block_pipeline("A2"):
            logger.info("[A2] Degrading to brand panorama mode")
            await DegradationRegistry.send_degradation_notice(session_id, "A2")

            # Immutable merge into existing user_decisions
            existing_decisions = state.get("user_decisions") or {}
            merged_decisions = {**existing_decisions, "a3_mode": "brand", "a2_degraded": True}

            return Command(
                update={
                    "current_step": "A2",
                    "marketing_personas": None,
                    "user_decisions": merged_decisions,
                    # No error_info / execution_status="error" -- let
                    # Orchestrator know A2 finished (without data)
                },
            )

        # Fallback: if strategy says block (currently unreachable)
        await send_error_event(session_id, "A2", str(e), recoverable=True)

        return Command(
            update={
                "error_info": {
                    "step": "A2",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                },
                "current_step": "A2",
                "marketing_personas": None,
            },
        )


async def _a2_call_and_parse(
    session_id: str,
    model: BaseLLMModel,
    system_prompt: str,
    user_content: str,
    progress_start: float,
    progress_end: float,
    attempt: int,
) -> dict | None:
    """Call LLM for A2 and parse the response. Returns parsed dict or None."""
    try:
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="persona_generation",
            step_name="用户画像生成",
            progress_start=progress_start,
            progress_end=progress_end,
            max_tokens=8192,
        )

        # Check for truncation — do not try to parse truncated JSON
        if hasattr(response, "finish_reason") and response.finish_reason == "length":
            content_len = len(response.content) if hasattr(response, "content") else 0
            logger.warning(
                f"[A2] Attempt {attempt}: LLM output truncated "
                f"(finish_reason=length, content_len={content_len})"
            )
            return None

        data = parse_llm_response(response)

        if not data:
            logger.warning(f"[A2] Attempt {attempt}: JSON parse returned None")
            return None

        data = normalize_persona_payload(data)

        if not validate_persona_payload(data):
            logger.warning(
                f"[A2] Attempt {attempt}: Missing user_personas key. "
                f"Available keys: {list(data.keys())}"
            )
            return None

        logger.info(
            "[A2] Attempt %s: Successfully parsed %s personas",
            attempt,
            len(data.get("user_personas", [])),
        )
        return data

    except Exception as e:
        logger.warning(f"[A2] Attempt {attempt}: Exception during LLM call: {e}")
        return None
