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

from app.workflow.node_contracts import FlowTopology, TopologyNode

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


def custom_nodes_of_type(
    topology: FlowTopology, node_type: str
) -> tuple[TopologyNode, ...]:
    """Custom canvas nodes of a given contract type (analysis / content / ...)."""
    wanted = str(node_type or "").strip()
    return tuple(node for node in topology.custom_nodes if node.type == wanted)


def custom_incoming_sources(topology: FlowTopology, node_id: str) -> frozenset[str]:
    """Sources of custom edges targeting ``node_id``."""
    target = str(node_id or "").strip()
    return frozenset(
        edge.source for edge in topology.custom_edges if edge.target == target
    )


def analysis_nodes_schedulable(topology: FlowTopology) -> tuple[TopologyNode, ...]:
    """Analysis custom nodes wired from projection and/or report.

    Auto-run only when the user explicitly connected an input edge — a node
    dropped on the canvas with no edges stays manual-only (panel button / API).
    """
    ready: list[TopologyNode] = []
    for node in custom_nodes_of_type(topology, "analysis"):
        sources = custom_incoming_sources(topology, node.id)
        if sources & {"projection", "report"}:
            ready.append(node)
    return tuple(ready)


def content_nodes_schedulable(topology: FlowTopology) -> tuple[TopologyNode, ...]:
    """Content custom nodes wired from lexicon and/or analysis nodes."""
    analysis_ids = {node.id for node in custom_nodes_of_type(topology, "analysis")}
    ready: list[TopologyNode] = []
    for node in custom_nodes_of_type(topology, "content"):
        sources = custom_incoming_sources(topology, node.id)
        if "lexicon" in sources or (sources & analysis_ids):
            ready.append(node)
    return tuple(ready)


# Builtin canvas ids that can seed a partial branch run (3b-1.6).
BRANCH_SEED_NODE_IDS: frozenset[str] = frozenset(
    {"projection", "report", "lexicon", "extract", "fetch"}
)
CUSTOM_EXECUTOR_TYPES: frozenset[str] = frozenset({"analysis", "content"})


def custom_outgoing_targets(topology: FlowTopology, node_id: str) -> frozenset[str]:
    """Targets of custom edges leaving ``node_id``."""
    source = str(node_id or "").strip()
    return frozenset(
        edge.target for edge in topology.custom_edges if edge.source == source
    )


def _custom_node_index(topology: FlowTopology) -> dict[str, TopologyNode]:
    return {node.id: node for node in topology.custom_nodes}


def branch_custom_executors(
    topology: FlowTopology,
    from_node_id: str,
    *,
    mode: str = "downstream",
) -> tuple[TopologyNode, ...]:
    """Resolve the ordered custom executors for a partial branch run (3b-1.6).

    ``from_node_id`` may be:
    - a custom analysis/content node id
    - a builtin seed (``projection`` / ``report`` / ``lexicon`` / ...)

    Modes:
    - ``node_only``: only the start custom node (builtin seeds yield empty —
      builtins themselves are not re-executed by this path)
    - ``downstream``: start custom node (if any) plus all reachable custom
      executors via custom edges, in topological order (analysis before content)
    """
    start = str(from_node_id or "").strip()
    if not start:
        return ()
    by_id = _custom_node_index(topology)
    normalized_mode = str(mode or "downstream").strip().lower()
    if normalized_mode not in {"node_only", "downstream"}:
        normalized_mode = "downstream"

    start_custom = by_id.get(start)
    if start_custom is not None and start_custom.type not in CUSTOM_EXECUTOR_TYPES:
        return ()

    if normalized_mode == "node_only":
        if start_custom is not None and start_custom.type in CUSTOM_EXECUTOR_TYPES:
            return (start_custom,)
        return ()

    # Seed set for BFS over custom edges.
    frontier: list[str] = []
    if start_custom is not None:
        frontier.append(start)
    elif start in BRANCH_SEED_NODE_IDS:
        frontier.extend(sorted(custom_outgoing_targets(topology, start)))
    else:
        # Unknown id — no branch
        return ()

    reached: set[str] = set()
    queue = list(frontier)
    while queue:
        current = queue.pop(0)
        node = by_id.get(current)
        if node is None or node.type not in CUSTOM_EXECUTOR_TYPES:
            # Walk through non-executor hop if present (shouldn't happen often)
            for target in custom_outgoing_targets(topology, current):
                if target not in reached:
                    queue.append(target)
            continue
        if current in reached:
            continue
        reached.add(current)
        for target in custom_outgoing_targets(topology, current):
            if target not in reached:
                queue.append(target)

    if not reached:
        return ()

    # Topological order on the reached subgraph (Kahn). Analysis naturally
    # precedes content when edges connect them; otherwise analysis first.
    indegree: dict[str, int] = {nid: 0 for nid in reached}
    for edge in topology.custom_edges:
        if edge.source in reached and edge.target in reached:
            indegree[edge.target] = indegree.get(edge.target, 0) + 1
    ready = sorted(
        [nid for nid, deg in indegree.items() if deg == 0],
        key=lambda nid: (0 if by_id[nid].type == "analysis" else 1, nid),
    )
    ordered: list[TopologyNode] = []
    while ready:
        nid = ready.pop(0)
        ordered.append(by_id[nid])
        for target in sorted(custom_outgoing_targets(topology, nid)):
            if target not in indegree:
                continue
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort(
                    key=lambda x: (0 if by_id[x].type == "analysis" else 1, x)
                )
    # Cycles / leftovers: append remaining stably
    remaining = [by_id[nid] for nid in sorted(reached) if nid not in {n.id for n in ordered}]
    remaining.sort(key=lambda n: (0 if n.type == "analysis" else 1, n.id))
    ordered.extend(remaining)
    return tuple(ordered)


def build_execution_plan_summary(
    topology: FlowTopology,
    *,
    enabled_platforms: list[str] | None = None,
) -> dict[str, Any]:
    """Deterministic plan projection for canvas topology (blueprint 3b-2.1).

    Mirrors frontend ``buildAmwayFlowExecutionPlan`` at the gate level:
    which platforms and chain hops will run, plus scheduled custom nodes.
    Does not assign runtime active/done status (that is UI-side).
    """
    platforms = list(enabled_platforms or list(CANVAS_PLATFORM_IDS))
    steps: list[dict[str, Any]] = []
    active_edge_ids: list[str] = []

    fetch_ok = fetch_chain_enabled(topology)
    extract_ok = extract_chain_enabled(topology)
    projection_ok = projection_chain_enabled(topology)
    report_ok = report_chain_enabled(topology)
    disabled = disabled_platform_ids(topology)

    def add(
        node_id: str,
        label: str,
        *,
        skipped: bool = False,
        reason: str | None = None,
    ) -> None:
        steps.append(
            {
                "node_id": node_id,
                "label": label,
                "status": "skipped" if skipped else "pending",
                "skip_reason": reason,
            }
        )

    add(
        "question-set",
        "问题集",
        skipped=not fetch_ok,
        reason=None if fetch_ok else "已断开「问题集 → 采集」",
    )
    if fetch_ok:
        active_edge_ids.append(EDGE_QUESTIONS_FETCH)
    add("fetch", "答案采集", skipped=not fetch_ok, reason=None if fetch_ok else "采集链未启用")

    planned_platforms: list[str] = []
    for platform in CANVAS_PLATFORM_IDS:
        edge_on = is_edge_active(topology, platform_edge_id(platform))
        switch_on = platform in platforms
        skipped = (not fetch_ok) or (not edge_on) or (not switch_on) or (platform in disabled)
        reason = None
        if not fetch_ok:
            reason = "采集链未启用"
        elif not edge_on or platform in disabled:
            reason = "画布已断开该平台连线"
        elif not switch_on:
            reason = "平台开关已关闭"
        else:
            planned_platforms.append(platform)
            active_edge_ids.append(platform_edge_id(platform))
        add(
            f"platform-{platform}",
            platform,
            skipped=skipped,
            reason=reason,
        )

    extract_planned = fetch_ok and extract_ok and bool(planned_platforms)
    add(
        "extract",
        "实体抽取",
        skipped=not extract_planned,
        reason=None
        if extract_planned
        else (
            "已断开「采集 → 抽取」"
            if not extract_ok
            else "无可用采集平台"
        ),
    )
    if extract_planned:
        active_edge_ids.append(EDGE_FETCH_EXTRACT)

    projection_planned = extract_planned and projection_ok
    add(
        "projection",
        "图谱构建",
        skipped=not projection_planned,
        reason=None
        if projection_planned
        else ("已断开「抽取 → 图谱」" if not projection_ok else "上游抽取未计划"),
    )
    if projection_planned:
        active_edge_ids.append(EDGE_EXTRACT_PROJECTION)

    report_planned = projection_planned and report_ok
    add(
        "report",
        "报告生成",
        skipped=not report_planned,
        reason=None
        if report_planned
        else ("已断开「图谱 → 报告」" if not report_ok else "上游图谱未计划"),
    )
    if report_planned:
        active_edge_ids.append(EDGE_PROJECTION_REPORT)

    for node in analysis_nodes_schedulable(topology):
        # analysis_nodes_schedulable only checks wiring; also require upstream
        sources = custom_incoming_sources(topology, node.id)
        ok = ("projection" in sources and projection_planned) or (
            "report" in sources and report_planned
        )
        add(
            node.id,
            str((node.config or {}).get("label") or "数据分析"),
            skipped=not ok,
            reason=None if ok else "上游图谱/报告未计划",
        )
        if ok:
            for edge in topology.custom_edges:
                if edge.target == node.id:
                    active_edge_ids.append(edge.id)

    planned_analysis = {
        s["node_id"]
        for s in steps
        if s["status"] != "skipped"
        and any(n.id == s["node_id"] and n.type == "analysis" for n in topology.custom_nodes)
    }
    for node in content_nodes_schedulable(topology):
        sources = custom_incoming_sources(topology, node.id)
        ok = ("lexicon" in sources and extract_planned) or bool(
            sources & planned_analysis
        )
        add(
            node.id,
            str((node.config or {}).get("label") or "内容创作"),
            skipped=not ok,
            reason=None if ok else "上游未计划",
        )
        if ok:
            for edge in topology.custom_edges:
                if edge.target == node.id:
                    active_edge_ids.append(edge.id)

    planned = [s for s in steps if s["status"] != "skipped"]
    return {
        "steps": steps,
        "active_edge_ids": list(dict.fromkeys(active_edge_ids)),
        "planned_platforms": planned_platforms,
        "summary": (
            f"将执行 {len(planned)} 步"
            + (f" · 平台：{','.join(planned_platforms)}" if planned_platforms else "")
        ),
    }


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
