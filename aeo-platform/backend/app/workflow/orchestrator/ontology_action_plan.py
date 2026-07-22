"""Ontology action plan thin helper (Phase B close)."""

from __future__ import annotations

import logging
from typing import Any, Mapping

from app.services.brand_ontology_action_planner_service import (
    BrandOntologyActionPlannerService,
)

logger = logging.getLogger(__name__)

def _build_ontology_action_plan(
    state: Mapping[str, Any],
    ontology_world: dict[str, Any],
) -> dict[str, Any] | None:
    """Derive deterministic action advice from the durable object world."""

    try:
        planner = BrandOntologyActionPlannerService()
        return planner.build_plan(ontology_world=ontology_world, state=state)
    except Exception as exc:
        logger.warning("[Orchestrator] Failed to build ontology action plan: %s", exc)
        return None

