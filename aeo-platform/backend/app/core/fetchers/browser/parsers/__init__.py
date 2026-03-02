"""Response parsers for browser handler network interception.

Provides SSE and Connect protocol parsers that extract structured data
from intercepted HTTP responses, replacing fragile DOM scraping.
"""

from app.core.fetchers.browser.parsers.base import (
    BaseResponseParser,
    InterceptConfig,
    ParsedResponse,
)
from app.core.fetchers.browser.parsers.connect import KimiConnectParser

__all__ = [
    "BaseResponseParser",
    "InterceptConfig",
    "KimiConnectParser",
    "ParsedResponse",
]
