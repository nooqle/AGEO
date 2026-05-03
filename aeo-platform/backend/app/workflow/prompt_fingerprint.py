"""Stable prompt and tool surface fingerprints for LLM observability."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def fingerprint_text(text: str) -> str:
    """Return a short stable fingerprint for prompt-like text."""

    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def fingerprint_tools(tools: list[dict[str, Any]]) -> str:
    """Return a short stable fingerprint for an LLM tool surface."""

    return fingerprint_text(_stable_json(tools or []))

