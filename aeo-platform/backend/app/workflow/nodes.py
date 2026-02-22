"""LangGraph nodes for Specta AI workflow.

This module defines the node functions for each step (A1-A5) in the workflow.
Each node wraps the corresponding agent logic and handles state updates.
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
    send_confirmation_request,
    send_error_event,
    send_stage_result,
)
from app.workflow.nodes_streaming import call_llm_streaming
from app.workflow.summaries import generate_a1_summary
from app.core.llm import get_llm_model, BaseLLMModel
from app.core.utils import (
    extract_json_from_content,
    load_prompt_template,
    render_prompt,
)


# ============================================================================
# Helper Functions
# ============================================================================


def get_llm_model_compat() -> BaseLLMModel:
    """Get LLM model instance (thin wrapper for backward compat)."""
    return get_llm_model()


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
        existing_data += f"\n已有的品牌信息（请在此基础上补充完善）:\n"
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
        step="A1",
        step_name="品牌信息采集",
        progress=0.15,
        message=f"开始分析品牌: {brand_name}",
        status="running",
    )

    await send_tpaor_event(
        session_id, "thought", f"正在分析品牌 '{brand_name}' 的信息和竞品数据..."
    )

    # Task milestone: A1 started (Cycle 3, Module 1)
    task_id = state.get("task_id")
    if task_id:
        try:
            from app.core.database import AsyncSessionLocal
            from app.services.task_service import TaskService
            from uuid import UUID as _UUID
            async with AsyncSessionLocal() as db:
                ts = TaskService(db)
                await ts.update_progress(
                    _UUID(task_id), stage="A1", progress=0.05,
                    message=f"开始分析品牌: {brand_name}",
                )
        except Exception as te:
            logger.warning("[A1] TaskService update_progress failed: %s", te)

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
        # GLM5 web_search: server-side search, no tool_calls returned
        # MiniMax: ignores non-function tool types gracefully
        GLM5_WEB_SEARCH_TOOL = {
            "type": "web_search",
            "web_search": {"enable": True, "search_engine": "search_std"},
        }

        model = get_llm_model_compat()
        response = await call_llm_streaming(
            session_id=session_id,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            step="A1",
            step_name="品牌信息采集",
            progress_start=0.35,
            progress_end=0.8,
            tools=[GLM5_WEB_SEARCH_TOOL],
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
            }

        if "brand_profile" not in data:
            raise ValueError(f"Missing 'brand_profile' in response. Available keys: {list(data.keys())}")

        if "competitors" not in data:
            raise ValueError(f"Missing 'competitors' in response. Available keys: {list(data.keys())}")

        # Cycle 3 Module 3: A1 Quality Hardening
        # Step 1: Normalize field names (e.g., main_products → core_products)
        data["brand_profile"] = _normalize_a1_fields(data["brand_profile"])
        data["competitors"] = _normalize_competitors(data.get("competitors", []))

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
                    step="A1",
                    step_name="品牌信息采集(重试)",
                    progress_start=0.8,
                    progress_end=0.95,
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

        # Send completion event
        await send_progress_event(
            session_id=session_id,
            step="A1",
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
            session_id, "agent_summary", summary, step="A1", is_complete=True
        )

        # Save and send artifact to Canvas
        from app.workflow.events import save_and_send_artifact
        await save_and_send_artifact(
            session_id=session_id,
            output_type="report",
            title="品牌分析报告",
            data={
                "brandProfile": data["brand_profile"],
                "brand_profile": data["brand_profile"],
                "competitors": data["competitors"],
                "competitive_landscape": data.get("competitive_landscape"),
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
                    await ts.update_progress(
                        _UUID(task_id), stage="A1", progress=0.15,
                        message=f"品牌分析完成: {brand_name}",
                    )
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

        return Command(
            update={
                "brand_profile": data["brand_profile"],
                "competitors": data["competitors"],
                "competitive_landscape": data.get("competitive_landscape"),
                "current_step": "A1",
                "progress": 0.2,
                "entity_id": resolved_entity_id,
            },
        )

    except Exception as e:
        await send_error_event(session_id, "A1", str(e), recoverable=False)

        # Task milestone: A1 failed
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
                        error_stage="A1",
                    )
            except Exception as te:
                logger.warning("[A1] TaskService fail_task failed: %s", te)

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
  }
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
    competitors = state.get("competitors")

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
        step="A2",
        step_name="用户画像生成",
        progress=0.25,
        message=f"开始生成用户画像: {brand_profile.get('brand_name', '')}",
    )

    try:
        model = get_llm_model_compat()
        user_content = _build_a2_user_content(brand_profile, competitors)

        # --- Attempt 1: standard simplified prompt ---
        data = await _a2_call_and_parse(
            session_id=session_id,
            model=model,
            system_prompt=_get_a2_system_prompt(),
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
                step="A2",
                step_name="用户画像生成",
                progress=0.5,
                message="首次生成失败，正在重试...",
                status="running",
            )
            data = await _a2_call_and_parse(
                session_id=session_id,
                model=model,
                system_prompt=_get_a2_retry_prompt(),
                user_content=user_content,
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

        await send_progress_event(
            session_id=session_id,
            step="A2",
            step_name="用户画像生成",
            progress=1.0,
            message=f"成功生成 {persona_count} 个用户画像",
            status="completed",
        )

        await send_action_log_event(
            session_id,
            "agent_complete",
            f"用户画像生成完成，共 {persona_count} 个画像",
            step="A2",
            is_complete=True,
        )

        # Build selection items for inline persona picker
        _priority_zh_to_en = {
            "核心人群": "core",
            "增长人群": "growth",
            "机会人群": "opportunity",
        }
        selection_items = []
        for p in personas:
            raw_priority = p.get("persona_priority", p.get("priority", ""))
            priority_en = _priority_zh_to_en.get(raw_priority, raw_priority)
            selection_items.append({
                "id": p.get("persona_name", p.get("name", "")),
                "name": p.get("persona_name", p.get("name", "")),
                "description": p.get("persona_description", p.get("description", ""))[:120],
                "priority": priority_en,
                "scenarios": [
                    s.get("scenario_name", s) if isinstance(s, dict) else str(s)
                    for s in p.get("usage_scenarios", [])
                ],
            })

        # Send persona selection artifact (A2 deliverable)
        from app.workflow.events import save_and_send_artifact
        await save_and_send_artifact(
            session_id=session_id,
            output_type="selection",
            title="用户画像选择",
            data={
                "personas": selection_items,
                "maxSelection": 3,
                "minSelection": 1,
                "description": "请选择您希望重点分析的用户画像（可多选）",
            },
        )

        # Stage result: 让用户在等待期间看到画像阶段性产出
        stage_result_data = {
            "count": len(personas),
            "personas": [
                p.get("persona_name", p.get("name", "")) for p in personas[:4]
            ],
        }
        await send_stage_result(
            session_id, "A2", "用户画像",
            result_type="personas",
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
                        "stage": "A2",
                        "result_type": "personas",
                        "data": stage_result_data,
                        "stage_name": "用户画像",
                    })
            except Exception as e:
                logger.warning("[A2] Failed to persist stage_result: %s", e)

        return Command(
            update={
                "marketing_personas": data,
                "current_step": "A2",
                "progress": 0.4,
            },
        )

    except Exception as e:
        logger.error(f"[A2] Failed: {e}")

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

        # Task milestone: A2 failed (blocking path only)
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
                        error_stage="A2",
                    )
            except Exception as te:
                logger.warning("[A2] TaskService fail_task failed: %s", te)

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
            step="A2",
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

        # Validate: must have user_personas or userPersonas
        has_personas = (
            "user_personas" in data or "userPersonas" in data
        )
        if not has_personas:
            logger.warning(
                f"[A2] Attempt {attempt}: Missing user_personas key. "
                f"Available keys: {list(data.keys())}"
            )
            return None

        logger.info(f"[A2] Attempt {attempt}: Successfully parsed {len(data.get('user_personas', data.get('userPersonas', [])))} personas")
        return data

    except Exception as e:
        logger.warning(f"[A2] Attempt {attempt}: Exception during LLM call: {e}")
        return None


def _get_a2_system_prompt() -> str:
    """Get simplified A2 system prompt.

    Key change: JSON Schema reduced from 6 nested blocks / 30+ fields per persona
    to ~8-10 flat fields per persona. Includes persona_priority and usage_scenarios
    for downstream touchpoint tree building.
    """
    return """你是一个资深的消费者洞察专家。根据品牌档案信息，生成 4 个差异化的用户画像。

## 输出格式
请严格按照以下 JSON 格式输出（不要添加任何额外字段）：

{
  "brand_summary": {
    "brand_name": "品牌名",
    "core_value": "品牌核心价值（一句话）",
    "category": "主要品类"
  },
  "user_personas": [
    {
      "name": "画像昵称（如：精致妈妈、职场新贵）",
      "description": "一句话概括该人群（30字以内）",
      "demographics": {
        "age_range": "25-35",
        "gender": "女性为主",
        "city_tier": "一二线城市",
        "income": "月入1.5-3万",
        "occupation": "互联网/金融从业者"
      },
      "psychographics": {
        "lifestyle": "注重品质生活，追求效率与美感",
        "values": "品质优先，愿意为好产品付溢价",
        "pain_points": ["选择困难", "信息过载", "品质参差不齐"]
      },
      "priority": "核心人群/增长人群/机会人群",
      "key_questions": ["这类用户可能在AI搜索中问的问题1", "问题2", "问题3"],
      "usage_scenarios": [
        {
          "scenario_name": "场景名",
          "scenario_description": "该人群触发品牌需求的具体情境（30-50字）",
          "brand_interaction_intents": ["用户在此场景下与品牌互动的意图1（如：了解产品、比较方案、寻求建议、尝鲜体验、复购囤货）", "意图2"],
          "relevant_competitors": ["此场景下用户可能对比的竞品1", "竞品2"]
        }
      ]
    }
  ],
  "marketing_scenarios": [
    "场景1描述（包含人群、时间、地点、触发需求的情境，50-80字）",
    "场景2描述",
    "场景3描述"
  ]
}

## 画像要求
- 生成 4 个画像，覆盖：核心人群（2个）、增长人群（1个）、机会人群（1个）
- description 字段为一句话概括（30字以内），详细人口统计放在 demographics 中
- demographics 必须包含 age_range, gender, city_tier, income, occupation
- psychographics 必须包含 lifestyle, values, pain_points（数组）
- 每个画像的 key_questions 要贴合真实用户在 AI 搜索引擎中的提问习惯
- 每个画像的 priority 必须是 "核心人群"、"增长人群"、"机会人群" 之一
- 每个画像包含 2-3 个 usage_scenarios
- 每个 usage_scenario 必须包含 brand_interaction_intents（2-3个，描述用户与品牌/产品互动的意图，如咨询、比较、试用、购买、复购）和 relevant_competitors（1-3个）
- marketing_scenarios 生成 4-6 个场景

⚠️ 重要：直接以 { 开头输出 JSON，不要有任何解释或 Markdown 标记。"""


def _get_a2_retry_prompt() -> str:
    """Even simpler A2 prompt for retry attempt."""
    return """根据品牌信息，生成 4 个用户画像。直接输出以下 JSON 格式，不要有其他文字：

{
  "user_personas": [
    {"name": "画像名称", "description": "一句话概括（30字以内）", "demographics": {"age_range": "25-35", "gender": "女性为主", "city_tier": "一二线", "income": "月入1-2万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "核心人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["了解产品"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "30-45", "gender": "男性为主", "city_tier": "一二线", "income": "月入2-5万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "核心人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["比较方案"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "20-30", "gender": "不限", "city_tier": "二三线", "income": "月入0.5-1万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "增长人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["尝鲜体验"], "relevant_competitors": ["竞品1"]}]},
    {"name": "画像名称", "description": "一句话概括", "demographics": {"age_range": "35-50", "gender": "不限", "city_tier": "各线", "income": "月入1-3万", "occupation": "职业"}, "psychographics": {"lifestyle": "生活方式", "values": "价值观", "pain_points": ["痛点1"]}, "priority": "机会人群", "key_questions": ["问题1", "问题2"], "usage_scenarios": [{"scenario_name": "场景名", "scenario_description": "场景描述", "brand_interaction_intents": ["寻求建议"], "relevant_competitors": ["竞品1"]}]}
  ],
  "marketing_scenarios": ["场景1", "场景2", "场景3"]
}"""


def _build_pipeline_data(personas: list[dict]) -> dict:
    """Build 3-column pipeline data from A2 persona output for touchpoint map visualization.

    Columns: User Profile -> Usage Scenario -> Brand Interaction Intent
    """
    profiles = []
    scenarios = []
    intents = []
    edges = []
    intent_dedup: dict[str, str] = {}  # text -> id
    scenario_dedup: dict[str, str] = {}  # name -> id

    for pi, p in enumerate(personas):
        p_name = p.get("persona_name", p.get("name", f"画像{pi+1}"))
        p_id = f"profile_{pi}"

        pain_points = []
        psycho = p.get("psychographics", {})
        if isinstance(psycho, dict):
            pain_points = psycho.get("pain_points", [])
            if isinstance(pain_points, str):
                pain_points = [pain_points]

        values_text = psycho.get("values", "") if isinstance(psycho, dict) else ""
        occupation = ""
        demo = p.get("demographics", {})
        if isinstance(demo, dict):
            occupation = demo.get("occupation", "")

        profiles.append({
            "id": p_id,
            "label": p_name,
            "subtitle": p.get("persona_description", p.get("description", "")),
            "tags": {
                "痛点": pain_points[:3] if pain_points else [],
                "核心诉求": values_text,
                "职业": occupation,
            },
            "priority": p.get("persona_priority", p.get("priority", "")),
        })

        for si, s in enumerate(p.get("usage_scenarios", [])):
            if not isinstance(s, dict):
                continue
            s_name = s.get("scenario_name", f"场景{si+1}")
            s_desc = s.get("scenario_description", "")

            # Dedup scenarios by name across personas
            if s_name in scenario_dedup:
                s_id = scenario_dedup[s_name]
            else:
                s_id = f"scenario_{len(scenario_dedup)}"
                scenario_dedup[s_name] = s_id
                scenarios.append({
                    "id": s_id,
                    "label": s_name,
                    "tags": {
                        "任务目标": s_desc,
                    },
                })

            edges.append({"source": p_id, "target": s_id})

            # Use new field name with fallback
            interaction_intents = s.get("brand_interaction_intents", s.get("likely_search_intents", []))
            if isinstance(interaction_intents, str):
                interaction_intents = [interaction_intents]

            for intent_text in interaction_intents:
                if not intent_text:
                    continue
                if intent_text not in intent_dedup:
                    i_id = f"intent_{len(intent_dedup)}"
                    intent_dedup[intent_text] = i_id
                    intents.append({
                        "id": i_id,
                        "label": intent_text,
                    })
                edges.append({"source": s_id, "target": intent_dedup[intent_text]})

    return {
        "columns": [
            {"key": "profile", "label": "用户画像", "color": "purple", "nodes": profiles},
            {"key": "scenario", "label": "使用场景", "color": "blue", "nodes": scenarios},
            {"key": "intent", "label": "互动意图", "color": "orange", "nodes": intents},
        ],
        "edges": edges,
    }


def _build_a2_user_content(brand_profile: dict, competitors: list) -> str:
    """Build user content for A2."""
    content = f"""请基于以下品牌档案信息，生成 4 组【用户画像 + 使用场景 + 营销痛点】：

## 品牌档案
- 品牌中文名：{brand_profile.get('brand_name', '')}
- 品牌英文名：{brand_profile.get('brand_name_en', '')}
- 成立年份：{brand_profile.get('founded_year', '')}
- 核心领域：{brand_profile.get('industry', '')}
- 核心产品：{', '.join(brand_profile.get('core_products', []))}
- 品牌理念：{brand_profile.get('brand_positioning', '')}
- 品牌描述：{brand_profile.get('description', '')}
- 目标市场：{brand_profile.get('target_audience', '')}
- 价格定位：{brand_profile.get('price_positioning', '')}

## 竞争环境参考
- 主要竞品：{', '.join([c.get('name', '') for c in competitors[:5]])}
- 市场竞争格局：{len(competitors)} 个主要竞品
"""
    return content
