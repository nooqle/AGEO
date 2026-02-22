"""A4 Tool - Answer Fetching.

Pure function implementation for fetching answers from AI platforms.
"""


async def fetch_answers(
    questions: list, brand_profile: dict, platforms: list[str] | None = None
) -> list[dict]:
    """Fetch answers from AI platforms.

    Args:
        questions: List of questions to fetch answers for
        brand_profile: Brand profile data
        platforms: List of platform names to fetch from

    Returns:
        List of fetch results
    """
    # This is implemented in nodes_a4.py for now
    raise NotImplementedError("A4 is implemented directly in workflow nodes")


# Backward compatibility
FetchAgentTool = fetch_answers
