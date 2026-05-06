"""Compatibility layer for A2 persona-generation primitives.

`persona_generation` remains a workflow stage in `nodes.py`.
Pure prompt-building and normalization logic lives in `persona_generation.py`.
"""

from typing import Any

from app.tools.persona_generation import build_persona_generation_messages


async def generate_marketing_personas(
    brand_profile: dict, competitors: list
) -> dict[str, Any]:
    """Backward-compatible async wrapper for legacy A2 tool callers."""

    system_prompt, user_content = build_persona_generation_messages(
        brand_profile,
        competitors,
    )
    return {
        "system_prompt": system_prompt,
        "user_content": user_content,
    }


# Backward compatibility
MarketingPersonaTool = generate_marketing_personas
