"""Wave B orchestration event dict shape (DB-free)."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from app.services.flow_orchestration_event_service import event_to_dict


def test_event_to_dict():
    row = SimpleNamespace(
        id=uuid4(),
        entity_id=uuid4(),
        event_type="apply_recipe",
        summary="套用配方「日常」",
        payload={"recipe_id": "x"},
        created_by_user_id=None,
        created_at=None,
    )
    d = event_to_dict(row)  # type: ignore[arg-type]
    assert d["event_type"] == "apply_recipe"
    assert "日常" in d["summary"]
