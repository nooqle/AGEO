"""Compatibility layer for A3 question-generation primitives.

`question_simulation` remains a workflow stage in `nodes_a3.py`.
Pure prompt-building and normalization logic now lives in `question_generation.py`.
"""

from app.tools.question_generation import (
    QuestionGenerationTool,
    build_question_generation_messages,
)


async def simulate_questions(
    brand_profile: dict,
    competitors: list,
    personas: list | None = None,
    mode: str = "brand",
    identity: str | None = None,
) -> dict:
    """Backward-compatible async wrapper for legacy A3 tool callers."""

    normalized_mode = {
        "persona": "persona_focused",
        "persona_focused": "persona_focused",
        "baseline_dynamic": "baseline_dynamic",
        "brand": "brand_panorama",
        "brand_panorama": "brand_panorama",
    }.get(mode, "brand_panorama")
    system_prompt, user_content = build_question_generation_messages(
        mode=normalized_mode,
        brand_profile=brand_profile,
        competitors=competitors,
        selected_personas=personas or [],
        platforms=("kimi", "deepseek", "doubao", "hunyuan"),
        identity=identity,
    )
    return {
        "system_prompt": system_prompt,
        "user_content": user_content,
        "mode": normalized_mode,
    }

# Backward compatibility
QuestionSimulationTool = simulate_questions
