"""Base classes for response parsers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.schemas.fetch import SearchReference


@dataclass
class ParsedResponse:
    """Result of parsing an intercepted HTTP response."""

    answer_text: str = ""
    references: list[SearchReference] = field(default_factory=list)
    raw_body: str = ""  # First 2000 chars for debugging
    parse_ok: bool = False
    error: str = ""


@dataclass
class InterceptConfig:
    """Configuration for which HTTP response to intercept."""

    url_pattern: str  # Regex, e.g. r"/api/v0/chat/completion"
    method: str = "POST"
    content_type_contains: str = ""  # e.g. "event-stream"
    timeout: float = 60.0


class BaseResponseParser(ABC):
    """Base class for HTTP response body parsers."""

    @abstractmethod
    def parse(self, body: str, url: str = "") -> ParsedResponse:
        """Parse the full response body into structured data."""
        ...

    def validate(self, result: ParsedResponse) -> ParsedResponse:
        """Post-parse validation. Override for platform-specific checks."""
        if result.answer_text and len(result.answer_text.strip()) >= 10:
            result.parse_ok = True
        else:
            result.parse_ok = False
            if not result.error:
                result.error = f"Answer too short ({len(result.answer_text)} chars)"
        return result
