"""Topology-aware orchestration resolver (blueprint 3b-1.3).

The canvas topology (``flow_topologies`` table, authoritative since 3b-1.4)
declares which builtin edges the user has disconnected. This module translates
a :class:`FlowTopology` into runtime gating decisions for the headless
orchestration chain:

- platform gate: a removed ``fetch → platform-{p}`` edge skips that platform's
  answer fetch;
- fetch chain gate: a removed ``question-set → fetch`` edge stops A3 from
  chaining into A4;
- report chain gate: a removed ``projection → report`` edge stops A4 from
  chaining into A5.

No topology record (or any load error) yields an empty ``FlowTopology`` —
every builtin edge active — which reproduces the pre-3b hardcoded behavior.
"""

from __future__ import annotations

import logging
from typing import Any

from app.workflow.node_contracts import FlowTopology

logger = logging.getLogger(__name__)

# Canvas platform ids double as A4 executor keys for all four platforms
# (canvas "hunyuan" == executor "hunyuan" == public "yuanbao").
# Must stay in sync with frontend AmwayFlowCanvas PLATFORM_META.
CANVAS_PLATFORM_IDS: tuple[str, ...] = ("deepseek", "kimi", "doubao", "hunyuan")

# Builtin canvas edge ids — must stay in sync with frontend
# AmwayFlowCanvas EDGE_DEFS.
EDGE_QUESTIONS_FETCH = "e-questions-fetch"
EDGE_LEXICON_EXTRACT = "e-lexicon-extract"
EDGE_FETCH_EXTRACT = "e-fetch-extract"
EDGE_EXTRACT_PROJECTION = "e-extract-projection"
EDGE_PROJECTION_REPORT = "e-projection-report"


def platform_edge_id(platform: str) -> str:
    return f"e-fetch-{platform}"


BUILTIN_EDGE_IDS: tuple[str, ...] = (
    EDGE_QUESTIONS_FETCH,
    EDGE_LEXICON_EXTRACT,
    EDGE_FETCH_EXTRACT,
    EDGE_EXTRACT_PROJECTION,
    EDGE_PROJECTION_REPORT,
    *(platform_edge_id(platform) for platform in CANVAS_PLATFORM_IDS),
)


async def load_flow_topology(entity_id: Any) -> FlowTopology:
    """Load the authoritative topology for an entity.

    Missing entity id, missing row, or any storage error degrades to the
    empty topology (all builtin edges active) — orchestration never fails
    because of topology persistence.
    """
    raw = str(entity_id or "").strip()
    if not raw:
        return FlowTopology()
    try:
        from app.core.database import AsyncSessionLocal
        from app.models.flow_topology import FlowTopologyRecord
        from sqlalchemy import select

        async with AsyncSessionLocal() as db:
            row = (
                await db.execute(
                    select(FlowTopologyRecord.topology).where(
                        FlowTopologyRecord.entity_id == raw
                    )
                )
            ).scalar_one_or_none()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[topology] load failed for entity %s: %s", raw, exc)
        return FlowTopology()
    if not row:
        return FlowTopology()
    return FlowTopology.from_dict(row)


def is_edge_active(topology: FlowTopology, edge_id: str) -> bool:
    """A builtin edge is active unless explicitly disconnected on the canvas."""
    return edge_id not in topology.removed_edge_ids


def disabled_platform_ids(topology: FlowTopology) -> frozenset[str]:
    """Platforms whose ``fetch → platform-{p}`` edge the user disconnected."""
    return frozenset(
        platform
        for platform in CANVAS_PLATFORM_IDS
        if not is_edge_active(topology, platform_edge_id(platform))
    )


def fetch_chain_enabled(topology: FlowTopology) -> bool:
    """Whether A3 may chain into A4 (question-set → fetch edge active)."""
    return is_edge_active(topology, EDGE_QUESTIONS_FETCH)


def extract_chain_enabled(topology: FlowTopology) -> bool:
    """Whether A4 may chain into entity extraction (fetch → extract edge active)."""
    return is_edge_active(topology, EDGE_FETCH_EXTRACT)


def projection_chain_enabled(topology: FlowTopology) -> bool:
    """Whether extraction may chain into circle projection (extract → projection)."""
    return is_edge_active(topology, EDGE_EXTRACT_PROJECTION)


def report_chain_enabled(topology: FlowTopology) -> bool:
    """Whether projection/A4 may chain into the report (projection → report)."""
    return is_edge_active(topology, EDGE_PROJECTION_REPORT)


def apply_platform_gate(
    topology: FlowTopology,
    platform_filter: list[str] | None,
) -> tuple[list[str] | None, frozenset[str]]:
    """Gate a platform filter through the topology.

    Returns ``(effective_filter, disabled)``. ``effective_filter`` semantics:

    - no edges removed → the input filter verbatim (``None`` keeps the legacy
      "all platforms" meaning);
    - edges removed and input ``None`` → explicit list of surviving platforms;
    - edges removed and input explicit → intersection;
    - **``None`` in the result when anything was removed means "no platform
      survives" — the caller MUST short-circuit the fetch, never pass it on
      (downstream treats ``None`` as "all platforms").**
    """
    disabled = disabled_platform_ids(topology)
    if not disabled:
        return platform_filter, frozenset()
    if platform_filter:
        gated = [p for p in platform_filter if p not in disabled]
    else:
        gated = [p for p in CANVAS_PLATFORM_IDS if p not in disabled]
    return (gated or None), disabled
