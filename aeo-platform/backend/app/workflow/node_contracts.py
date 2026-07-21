"""Node contract registry — the platform-level foundation of topology-aware orchestration.

Blueprint: docs/specta-agentic-infrastructure-blueprint-2026-07-21.md (§2.2)

Design rules (命根子原则):
1. Contracts are domain-agnostic: only id/kind/inputs/outputs/config/executor live
   here. Business semantics (brand, circle, lexicon wording) stay in node
   implementations and prompts — never leak into this layer.
2. Single source of truth: the canvas (frontend), config panels, and the
   orchestrator all read the same registry. The frontend keeps a mirror of the
   port types; any change here must be reflected there
   (frontend AmwayFlowCanvas BUILTIN_OUTPUT_TYPE / BUILTIN_ACCEPTED_INPUTS).
3. LLM-readable: `description` doubles as the tool description an orchestrator
   can consume when planning over the registry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

NodeKind = Literal["asset", "executor", "producer"]


@dataclass(frozen=True)
class PortSpec:
    """A typed data port. `type` is the domain-agnostic artifact type used for
    connection validation (questions/lexicon/answers/entities/circle/report/...)."""

    type: str
    required: bool = True


@dataclass(frozen=True)
class ConfigField:
    """One configurable knob of a node, shared by the config panel and the
    orchestrator (which may set it from user intent)."""

    name: str
    value_type: str  # 'string' | 'number' | 'boolean' | 'string[]' | 'object'
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class NodeContract:
    """Self-description of a canvas node / execution unit."""

    id: str  # canvas node id, e.g. 'fetch', 'analysis'
    kind: NodeKind
    inputs: tuple[PortSpec, ...] = ()
    outputs: tuple[PortSpec, ...] = ()
    config_schema: tuple[ConfigField, ...] = ()
    # Execution wiring (None for assets / not-yet-executable nodes):
    graph_node: str | None = None  # LangGraph node name, e.g. 'a4_fetch'
    tool_name: str | None = None  # orchestrator tool key, e.g. 'answer_fetch'
    stage_code: str | None = None  # run stage reported to UI, e.g. 'fetching_answers'
    # If this node's logic currently lives inside another node, name the host.
    # Such nodes are visible on canvas but not independently schedulable until
    # extracted (3b-1.2).
    embedded_in: str | None = None
    description: str = ""


# ---------------------------------------------------------------------------
# Flow topology model (shared by DB persistence 3b-1.4 and the resolver 3b-1.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TopologyNode:
    id: str
    type: str  # NodeContract.id for custom nodes
    position: dict[str, float] = field(default_factory=dict)
    config: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TopologyEdge:
    id: str
    source: str
    target: str


@dataclass(frozen=True)
class FlowTopology:
    """User-authored orchestration: custom nodes/edges plus builtin edges the
    user disconnected. Mirrors the frontend FlowTopology (version 1)."""

    version: int = 1
    custom_nodes: tuple[TopologyNode, ...] = ()
    custom_edges: tuple[TopologyEdge, ...] = ()
    removed_edge_ids: tuple[str, ...] = ()

    @staticmethod
    def from_dict(raw: dict[str, Any] | None) -> "FlowTopology":
        if not isinstance(raw, dict):
            return FlowTopology()
        nodes = tuple(
            TopologyNode(
                id=str(n.get("id") or ""),
                type=str(n.get("type") or ""),
                position=dict(n.get("position") or {}),
                config=dict(n.get("config") or {}),
            )
            for n in (raw.get("customNodes") or [])
            if isinstance(n, dict) and n.get("id") and n.get("type")
        )
        edges = tuple(
            TopologyEdge(
                id=str(e.get("id") or ""),
                source=str(e.get("source") or ""),
                target=str(e.get("target") or ""),
            )
            for e in (raw.get("customEdges") or [])
            if isinstance(e, dict) and e.get("source") and e.get("target")
        )
        removed = tuple(
            str(r) for r in (raw.get("removedEdgeIds") or []) if isinstance(r, str)
        )
        return FlowTopology(
            version=int(raw.get("version") or 1),
            custom_nodes=nodes,
            custom_edges=edges,
            removed_edge_ids=removed,
        )


# ---------------------------------------------------------------------------
# AmwayChina registry (first instantiation of the platform contract layer)
# ---------------------------------------------------------------------------

# Builtin canvas edge ids (must match frontend AmwayFlowCanvas EDGE_DEFS;
# canonical copies live in app.workflow.topology_resolver):
#   e-questions-fetch / e-lexicon-extract / e-fetch-extract /
#   e-extract-projection / e-projection-report / e-fetch-{platform}

AMWAY_NODE_CONTRACTS: dict[str, NodeContract] = {
    "question-set": NodeContract(
        id="question-set",
        kind="asset",
        outputs=(PortSpec("questions"),),
        config_schema=(
            ConfigField("source", "string", "default", "default | uploaded | history"),
            ConfigField("question_set_id", "string", None, "bound history set id"),
        ),
        description="题目来源资产：本轮采集使用的问题集（默认生成/上传/历史集）。",
    ),
    "lexicon": NodeContract(
        id="lexicon",
        kind="asset",
        outputs=(PortSpec("lexicon"),),
        description="实体识别范围资产：品牌实体词库，供抽取校准使用。",
    ),
    "fetch": NodeContract(
        id="fetch",
        kind="executor",
        inputs=(PortSpec("questions"),),
        outputs=(PortSpec("answers"),),
        config_schema=(
            ConfigField("platforms", "string[]", None, "enabled platform ids"),
            ConfigField("fetch_mode", "string", "browser", "browser | api"),
        ),
        graph_node="a4_fetch",
        tool_name="answer_fetch",
        stage_code="fetching_answers",
        description="把问题逐条投给各 AI 平台并采集回答原文。",
    ),
    "extract": NodeContract(
        id="extract",
        kind="executor",
        inputs=(PortSpec("lexicon"), PortSpec("answers")),
        outputs=(PortSpec("entities"),),
        graph_node="amway_extract",
        tool_name="amway_entity_extract",
        stage_code="extracting_entities",
        description="从回答原文识别品牌实体并按样本量校准置信度。",
    ),
    "projection": NodeContract(
        id="projection",
        kind="executor",
        inputs=(PortSpec("entities"),),
        outputs=(PortSpec("circle"),),
        graph_node="amway_projection",
        tool_name="amway_circle_projection",
        stage_code="building_circle",
        description="把校准后的实体按与品牌的距离排布成圈层图谱。",
    ),
    "report": NodeContract(
        id="report",
        kind="executor",
        inputs=(PortSpec("circle"),),
        outputs=(PortSpec("report"),),
        graph_node="a5_analytics",
        tool_name="analysis_report_skill",
        stage_code="analyzing_metrics",
        description="基于图谱与原文证据生成可交付的解读报告。",
    ),
    # Custom node types (created from the node library):
    "analysis": NodeContract(
        id="analysis",
        kind="executor",
        inputs=(PortSpec("circle", required=False), PortSpec("report", required=False)),
        outputs=(PortSpec("analysis"),),
        config_schema=(
            ConfigField("label", "string", "", "display name"),
            ConfigField("dimensions", "string[]", None, "analysis dimension ids"),
            ConfigField("prompt", "string", "", "custom interpretation prompt"),
        ),
        # executor wired in 3b-1.5 (LLM second-pass interpretation)
        description="对圈层/报告做二级解读，产出分析结论卡片。",
    ),
    "content": NodeContract(
        id="content",
        kind="executor",
        inputs=(
            PortSpec("lexicon", required=False),
            PortSpec("analysis", required=False),
        ),
        outputs=(PortSpec("content"),),
        config_schema=(
            ConfigField("label", "string", "", "display name"),
            ConfigField("promptTemplate", "string", "", "content prompt template"),
        ),
        # executor wired in 3b-1.5
        description="基于词库与分析结论起草内容文案。",
    ),
}

# Platform sub-nodes hang off `fetch`; their enablement is consumed as
# platform_filter by the fetch executor (nodes_a4.py).
AMWAY_PLATFORM_IDS: tuple[str, ...] = ("deepseek", "kimi", "doubao", "hunyuan")

# Canvas node id -> orchestrator tool key (only directly schedulable nodes).
CANVAS_TO_TOOL: dict[str, str] = {
    contract.id: contract.tool_name
    for contract in AMWAY_NODE_CONTRACTS.values()
    if contract.tool_name
}

TOOL_TO_CANVAS: dict[str, str] = {v: k for k, v in CANVAS_TO_TOOL.items()}


def get_contract(node_id: str) -> NodeContract | None:
    """Look up a contract by canvas id or custom node type."""
    return AMWAY_NODE_CONTRACTS.get(node_id)


def output_type_of(
    node_id: str, custom_nodes: tuple[TopologyNode, ...] = ()
) -> str | None:
    """Output port type of a node (builtin by id, custom by its type)."""
    contract = AMWAY_NODE_CONTRACTS.get(node_id)
    if contract and contract.outputs:
        return contract.outputs[0].type
    for node in custom_nodes:
        if node.id == node_id:
            custom = AMWAY_NODE_CONTRACTS.get(node.type)
            if custom and custom.outputs:
                return custom.outputs[0].type
    if node_id.startswith("platform-"):
        return "answers"
    return None


def accepted_input_types(
    node_id: str, custom_nodes: tuple[TopologyNode, ...] = ()
) -> tuple[str, ...]:
    """Accepted input port types of a node (builtin by id, custom by its type)."""
    contract = AMWAY_NODE_CONTRACTS.get(node_id)
    if contract is None:
        for node in custom_nodes:
            if node.id == node_id:
                contract = AMWAY_NODE_CONTRACTS.get(node.type)
                break
    if contract is None:
        return ()
    return tuple(port.type for port in contract.inputs)


def is_schedulable(node_id: str) -> bool:
    """Whether the node can be dispatched as an independent execution unit today."""
    contract = AMWAY_NODE_CONTRACTS.get(node_id)
    return bool(contract and contract.graph_node and not contract.embedded_in)
