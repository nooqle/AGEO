"""Unit tests for the node contract registry (blueprint §2.2)."""

from app.workflow.node_contracts import (
    AMWAY_NODE_CONTRACTS,
    AMWAY_PLATFORM_IDS,
    CANVAS_TO_TOOL,
    TOOL_TO_CANVAS,
    FlowTopology,
    accepted_input_types,
    get_contract,
    is_schedulable,
    output_type_of,
)


def test_builtin_canvas_nodes_are_registered():
    for node_id in (
        "question-set",
        "lexicon",
        "fetch",
        "extract",
        "projection",
        "report",
    ):
        assert node_id in AMWAY_NODE_CONTRACTS, node_id


def test_custom_node_types_are_registered():
    for node_type in ("analysis", "content"):
        contract = AMWAY_NODE_CONTRACTS.get(node_type)
        assert contract is not None
        assert contract.outputs, node_type


def test_port_types_match_frontend_canvas():
    """Mirror of frontend BUILTIN_OUTPUT_TYPE / BUILTIN_ACCEPTED_INPUTS."""
    assert output_type_of("question-set") == "questions"
    assert output_type_of("lexicon") == "lexicon"
    assert output_type_of("fetch") == "answers"
    assert output_type_of("extract") == "entities"
    assert output_type_of("projection") == "entity_graph"
    assert output_type_of("report") == "report"
    assert accepted_input_types("fetch") == ("questions",)
    assert accepted_input_types("extract") == ("lexicon", "answers")
    assert accepted_input_types("projection") == ("entities",)
    assert accepted_input_types("report") == ("entity_graph",)
    assert set(accepted_input_types("analysis")) == {"entity_graph", "report"}
    assert set(accepted_input_types("content")) == {"lexicon", "analysis"}


def test_schedulability_reflects_embedding():
    """3b-1.2 extract/projection + 3b-1.5 analysis/content 均可独立调度。"""
    assert is_schedulable("fetch") is True
    assert is_schedulable("report") is True
    assert is_schedulable("extract") is True
    assert is_schedulable("projection") is True
    assert is_schedulable("analysis") is True  # 3b-1.5
    assert is_schedulable("content") is True  # 3b-1.5
    assert is_schedulable("unknown-node") is False


def test_tool_mapping_is_bijective():
    assert CANVAS_TO_TOOL == {
        "fetch": "answer_fetch",
        "extract": "amway_entity_extract",
        "projection": "amway_circle_projection",
        "report": "analysis_report_skill",
        "analysis": "amway_secondary_analysis",
        "content": "amway_content_draft",
    }
    assert TOOL_TO_CANVAS["answer_fetch"] == "fetch"
    assert TOOL_TO_CANVAS["amway_entity_extract"] == "extract"
    assert TOOL_TO_CANVAS["amway_circle_projection"] == "projection"
    assert TOOL_TO_CANVAS["analysis_report_skill"] == "report"
    assert TOOL_TO_CANVAS["amway_secondary_analysis"] == "analysis"
    assert TOOL_TO_CANVAS["amway_content_draft"] == "content"


def test_platform_ids_match_frontend_meta():
    assert set(AMWAY_PLATFORM_IDS) == {"deepseek", "kimi", "doubao", "hunyuan"}


def test_topology_from_dict_tolerates_garbage():
    assert FlowTopology.from_dict(None) == FlowTopology()
    assert FlowTopology.from_dict({"customNodes": "bad"}) == FlowTopology()
    topo = FlowTopology.from_dict(
        {
            "version": 1,
            "customNodes": [
                {
                    "id": "custom-analysis-x",
                    "type": "analysis",
                    "position": {"x": 1, "y": 2},
                    "config": {"label": "A"},
                },
                {"id": "", "type": "analysis"},  # dropped: missing id
                {"id": "no-type"},  # dropped: missing type
            ],
            "customEdges": [
                {"id": "e1", "source": "projection", "target": "custom-analysis-x"},
                {"id": "e2", "source": "", "target": "custom-analysis-x"},  # dropped
            ],
            "removedEdgeIds": ["e-fetch-extract", 42],
        }
    )
    assert len(topo.custom_nodes) == 1
    assert topo.custom_nodes[0].config["label"] == "A"
    assert len(topo.custom_edges) == 1
    assert topo.removed_edge_ids == ("e-fetch-extract",)


def test_custom_node_port_resolution():
    topo = FlowTopology.from_dict(
        {"customNodes": [{"id": "custom-analysis-abc", "type": "analysis"}]}
    )
    assert output_type_of("custom-analysis-abc", topo.custom_nodes) == "analysis"
    assert set(accepted_input_types("custom-analysis-abc", topo.custom_nodes)) == {
        "entity_graph",
        "report",
    }
    assert output_type_of("platform-doubao") == "answers"


def test_contracts_have_descriptions_for_llm():
    for contract in AMWAY_NODE_CONTRACTS.values():
        assert contract.description, f"{contract.id} missing LLM-readable description"
    assert get_contract("nope") is None
