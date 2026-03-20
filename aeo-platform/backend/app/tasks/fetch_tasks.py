"""Celery tasks for answer fetching (A4).

Legacy compatibility note:
The current production A4 path runs inside the LangGraph/manual runtime flow.
This Celery task is retained for compatibility experiments and is not wired into
the active TaskRun orchestration path yet.
"""

import asyncio
import importlib
from typing import Any, Optional

from app.core.celery_config import celery_app
from app.core.constants import WorkflowConstants, PlatformConstants
from app.workflow.brand_mentions import content_mentions_brand

celery_exceptions = importlib.import_module("celery.exceptions")
MaxRetriesExceededError = celery_exceptions.MaxRetriesExceededError


@celery_app.task(
    bind=True,
    max_retries=WorkflowConstants.MAX_RETRIES,
    default_retry_delay=WorkflowConstants.RETRY_DELAY,
    time_limit=WorkflowConstants.FETCH_TIMEOUT_BROWSER * 2,
)
def fetch_answers_task(
    self,
    session_id: str,
    questions: list[dict],
    brand_profile: dict,
    platforms: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Celery task for fetching answers from AI platforms.

    Args:
        session_id: Session ID for tracking
        questions: List of questions to fetch answers for
        brand_profile: Brand profile data
        platforms: List of platform names to fetch from

    Returns:
        Dictionary containing fetch results
    """
    platforms = platforms or PlatformConstants.API_PLATFORMS

    try:
        # Run async fetch in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        results = loop.run_until_complete(
            _fetch_all_answers(questions, brand_profile, platforms)
        )

        loop.close()

        return {
            "status": "success",
            "session_id": session_id,
            "results": results,
            "total_questions": len(questions),
            "total_platforms": len(platforms),
        }

    except Exception as exc:
        # Retry on failure
        try:
            self.retry(exc=exc)
            return {
                "status": "retrying",
                "session_id": session_id,
                "error": str(exc),
                "results": [],
            }
        except MaxRetriesExceededError:
            return {
                "status": "error",
                "session_id": session_id,
                "error": str(exc),
                "results": [],
            }


async def _fetch_all_answers(
    questions: list[dict], brand_profile: dict, platforms: list[str]
) -> list[dict]:
    """Fetch answers from all platforms for all questions."""
    from app.core.fetchers.api.doubao_client import DoubaoClient
    from app.core.fetchers.api.hunyuan_client import HunyuanClient
    from typing import Union

    results = []

    # Initialize clients
    clients: dict[str, Union[DoubaoClient, HunyuanClient]] = {}
    if "doubao" in platforms:
        clients["doubao"] = DoubaoClient()
    if "hunyuan" in platforms:
        clients["hunyuan"] = HunyuanClient()

    for question in questions:
        question_id = question.get("id", "")
        question_text = question.get("text", "")

        platform_results = []

        for platform_name, client in clients.items():
            try:
                response = await client.ask(question_text)
                platform_results.append(
                    {
                        "platform": platform_name,
                        "success": True,
                        "answer": {
                            "content": response.get("content", ""),
                            "has_brand_mention": _check_brand_mention(
                                response.get("content", ""),
                                brand_profile,
                            ),
                        },
                    }
                )
            except Exception as e:
                platform_results.append(
                    {
                        "platform": platform_name,
                        "success": False,
                        "error": str(e),
                    }
                )

        results.append(
            {
                "question_id": question_id,
                "question_text": question_text,
                "platform_results": platform_results,
            }
        )

        # Small delay to avoid rate limiting
        await asyncio.sleep(0.5)

    return results


def _check_brand_mention(content: str, brand_profile: dict[str, Any]) -> bool:
    """Check if brand is mentioned in content."""
    return content_mentions_brand(content, brand_profile)
