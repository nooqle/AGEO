"""LangGraph state definition for Specta AI workflow.

This module defines the state structure for the LangGraph workflow,
ensuring compatibility with existing data fields from A1-A5 agents.
"""

from typing import TypedDict, Annotated, Sequence
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


def _merge_error_info(existing: dict | None, new: dict | None) -> dict | None:
    """Reducer for error_info: new value wins if not None, otherwise keep existing."""
    return new if new is not None else existing


def _last_value(existing: str, new: str) -> str:
    """Reducer for simple string fields: last writer wins."""
    return new if new else existing


def _last_float(existing: float, new: float) -> float:
    """Reducer for float fields: last writer wins."""
    return new if new is not None else existing


def _last_bool(existing: bool, new: bool) -> bool:
    """Reducer for bool fields: last writer wins."""
    return new if new is not None else existing


class AgentState(TypedDict):
    """Complete state for the Specta AI analysis workflow.

    This state is persisted across workflow executions and maintains
    all data produced by A1-A5 agents.
    """

    # =========================================================================
    # Session & Message Management
    # =========================================================================
    session_id: str
    user_id: str | None  # Current workspace/user scope for runtime skill resolution
    entity_id: str | None  # Associated brand entity ID
    messages: Annotated[Sequence[BaseMessage], add_messages]

    # =========================================================================
    # User Input (Original)
    # =========================================================================
    brand_name: str | None
    official_website: str | None
    industry_hint: str | None

    # =========================================================================
    # A1 Output: Brand Competition Analysis
    # =========================================================================
    brand_profile: dict | None
    # {
    #   "brand_name": str,
    #   "brand_name_en": str,
    #   "official_website": str,
    #   "industry": str,
    #   "description": str,
    #   "core_products": list[str],
    #   "brand_keywords": list[str],
    #   "brand_positioning": str,
    #   "target_audience": str,
    #   "founded_year": str,
    #   "price_positioning": str
    # }

    competitors: list | None
    # [
    #   {
    #     "name": str,
    #     "name_en": str,
    #     "website": str,
    #     "description": str,
    #     "relevance_score": int,
    #     "competition_type": str,
    #     "core_products": list[str],
    #     "competitive_advantage": str
    #   }
    # ]

    competitive_landscape: dict | None
    # {
    #   "market_overview": str,
    #   "competition_intensity": str,
    #   "key_battlegrounds": list[str]
    # }

    # =========================================================================
    # A2 Output: Marketing Personas (Full Structure)
    # =========================================================================
    marketing_personas: dict | None
    # {
    #   "brand_summary": {
    #     "brand_name": str,
    #     "core_value_proposition": str,
    #     "primary_category": str,
    #     "price_tier": str
    #   },
    #   "user_personas": [
    #     {
    #       "persona_id": str,
    #       "persona_name": str,
    #       "persona_description": str,
    #       "demographics": {...},
    #       "psychographics": {...},
    #       "brand_relationship": {...},
    #       "usage_scenarios": [...],
    #       "marketing_pain_points": [...],
    #       "persona_priority": str,
    #       "estimated_market_size": str,
    #       "acquisition_difficulty": str
    #     }
    #   ],
    #   "cross_persona_insights": {...}
    # }

    # =========================================================================
    # A3 Output: Simulated Questions (Full Structure)
    # =========================================================================
    simulated_questions: dict | None
    # {
    #   "generation_mode": str,  # "品牌全景模式" or "画像聚焦模式"
    #   "generation_context": {...},
    #   "simulated_questions": [
    #     {
    #       "question_id": str,
    #       "category": str,
    #       "subcategory": str,
    #       "user_intent": str,
    #       "decision_stage": str,
    #       "core_question": str,
    #       "question_variants": {
    #         "variant_a": {"type": "直接型", "question": str, "tone": str},
    #         "variant_b": {"type": "场景型", "question": str, "tone": str},
    #         "variant_c": {"type": "对比型", "question": str, "tone": str}
    #       }
    #     }
    #   ],
    #   "question_distribution": {...}
    # }

    # Flattened questions for A4 (convenience)
    questions: list | None
    # [{"id": str, "text": str, "category": str}]

    # =========================================================================
    # A4 Output: Fetch Results
    # =========================================================================
    fetch_results: list | None
    # [
    #   {
    #     "question_id": str,
    #     "question_text": str,
    #     "platform_results": [
    #       {
    #         "platform": str,
    #         "fetch_method": str,
    #         "success": bool,
    #         "answer": {"content": str, "word_count": int, ...},
    #         "citations": [...],
    #         "duration": float
    #       }
    #     ]
    #   }
    # ]

    # =========================================================================
    # A5 Output: Analytics & Report
    # =========================================================================
    metrics: dict | None
    # {
    #   "total_questions": int,
    #   "total_mentions": int,
    #   "mention_rate": float,
    #   "bwvs_index": float,
    #   "sentiment_distribution": {...},
    #   "platform_breakdown": {...}
    # }

    report: dict | None
    # {
    #   "executive_summary": str,
    #   "key_findings": list[str],
    #   "strengths": list[str],
    #   "weaknesses": list[str],
    #   "opportunities": list[str],
    #   "threats": list[str],
    #   "recommendations": [...],
    #   "action_plan": {...}
    # }

    # =========================================================================
    # Execution Control
    # =========================================================================
    current_step: Annotated[
        str, _last_value
    ]  # "A1", "A2", "A3", "A4", "A5", "complete"
    execution_status: Annotated[
        str, _last_value
    ]  # "running", "paused", "completed", "error"

    # =========================================================================
    # Human-in-Loop
    # =========================================================================
    pending_confirmation: Annotated[dict | None, _merge_error_info]
    # {
    #   "step_id": str,
    #   "step_name": str,
    #   "message": str,
    #   "options": list[dict]
    # }

    user_decisions: Annotated[dict, _merge_error_info]
    # {"skip_a2": bool, "use_persona_mode": bool, ...}

    # =========================================================================
    # Error Handling
    # =========================================================================
    error_info: Annotated[dict | None, _merge_error_info]
    # {"step": str, "error": str, "timestamp": str}

    # =========================================================================
    # Progress Tracking
    # =========================================================================
    progress: Annotated[float, _last_float]  # 0.0 - 1.0
    progress_message: Annotated[str, _last_value]

    # =========================================================================
    # Orchestrator State (LLM dynamic orchestration)
    # =========================================================================
    orchestrator_history: list  # [{role, content, tool_calls, tool_results}]
    orchestrator_reply: str | None  # Latest natural language reply from orchestrator
    next_action: str | None  # Next node decided by orchestrator
    awaiting_user: bool  # Whether waiting for user input
    tool_call_args: dict | None  # Arguments passed to Agent from tool call
    tool_call_id: str | None  # ID of the current tool call (for tool result)
    current_skill: str | None  # Currently executing public skill key
    current_skill_family: str | None  # Stable public skill family key
    current_skill_package_key: (
        str | None
    )  # Resolved package key for current skill family
    current_skill_package_name: str | None  # Human-readable package name
    current_skill_package_path: str | None  # Filesystem path to SKILL.md
    current_skill_package_context: str | None  # Loaded package guidance body
    current_skill_prompt_overlay: (
        str | None
    )  # Optional prompt overlay resolved from selected profile
    last_skill_result: dict | None  # Latest skill execution result summary
    skill_history: list  # [{skill_key, tool_name, status, summary, ...}]
    agent_retry_counts: (
        dict  # {tool_name: int} — tracks how many times each tool was called
    )
    fetch_mode: (
        str | None
    )  # "fast" (API+DeepSeek browser) or "full" (4 platforms all browser)
    knowledge_manifest: dict | None  # Lightweight history availability summary
    knowledge_lookup_result: dict | None  # Latest retrieval result for orchestrator
    knowledge_aggregate_result: dict | None  # Latest aggregation result
    knowledge_compare_result: dict | None  # Latest compare result
    knowledge_export_result: dict | None  # Latest export artifact result
    pending_table_intake: Annotated[dict | None, _merge_error_info]
    table_intake_result: Annotated[dict | None, _merge_error_info]
    confirmed_import_action: Annotated[dict | None, _merge_error_info]
    import_source_metadata: Annotated[dict | None, _merge_error_info]

    # =========================================================================
    # Task Persistence (Cycle 3, Module 1)
    # =========================================================================
    task_id: str | None  # UUID of the AnalysisTask tracking this execution
    run_id: str | None  # UUID of the TaskRun tracking this execution attempt

    # =========================================================================
    # Multi-Turn Follow-Up (Cycle 3, Module 2)
    # =========================================================================
    platform_filter: list | None  # Platform names to re-fetch (selective_refetch)
    preserved_fetch_results: (
        list | None
    )  # Unselected platform results to preserve during selective_refetch
    auto_trigger_a5: bool  # True when A4 completed a selective_refetch, signals orchestrator to call A5

    # =========================================================================
    # Headless Execution (Cycle 4 — Scheduler)
    # =========================================================================
    headless_mode: Annotated[
        bool, _last_bool
    ]  # True when running from scheduler without user interaction

    # =========================================================================
    # Baseline Analysis (Issue #4, Phase 4a)
    # =========================================================================
    analysis_mode: str | None  # "baseline" / "persona" — 当前 A3→A4→A5 执行的模式
    baseline_questions: list | None  # A3 baseline_dynamic 输出的问题列表
    baseline_fetch_results: list | None  # A4 基线抓取结果
    baseline_metrics: dict | None  # A5 基线指标
    baseline_report: dict | None  # A5 基线报告
