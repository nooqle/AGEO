from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime, time
from enum import Enum, EnumMeta
from pathlib import Path
from typing import Any, Mapping
from uuid import UUID

from pydantic import BaseModel


def to_json_compatible(value: Any) -> Any:
    """Recursively normalize runtime values into JSON-safe primitives."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, EnumMeta):
        return value.__name__
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, BaseModel):
        return to_json_compatible(value.model_dump())
    if is_dataclass(value):
        return to_json_compatible(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(to_json_compatible(key)): to_json_compatible(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_json_compatible(item) for item in value]
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return to_json_compatible(model_dump())
    dict_method = getattr(value, "dict", None)
    if callable(dict_method):
        return to_json_compatible(dict_method())
    return str(value)
