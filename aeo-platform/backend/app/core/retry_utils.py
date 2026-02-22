"""Retry utilities for LLM calls."""

import logging
from functools import wraps
from typing import Callable, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
from openai import APIError, APITimeoutError, RateLimitError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_llm_call(func: Callable[..., T]) -> Callable[..., T]:
    """Decorator to retry LLM calls with exponential backoff.

    Retries up to 3 times on timeout, rate limit, or API errors.
    Uses exponential backoff: 1s, 2s, 4s, up to 10s max.
    """

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((APITimeoutError, RateLimitError, APIError)),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper
