"""A3 Tool - Question Simulation.

Pure function implementation for simulating user questions.
"""

from typing import Any


async def simulate_questions(
    brand_profile: dict,
    competitors: list,
    personas: dict | None = None,
    mode: str = "brand",
) -> dict[str, Any]:
    """Simulate user questions.

    Args:
        brand_profile: Brand profile data
        competitors: Competitors list
        personas: Optional personas data for persona mode
        mode: "brand" or "persona"

    Returns:
        Dictionary containing simulated_questions data
    """
    # This is implemented in nodes_a3.py for now
    raise NotImplementedError("A3 is implemented directly in workflow nodes")


# Backward compatibility
QuestionSimulationTool = simulate_questions
