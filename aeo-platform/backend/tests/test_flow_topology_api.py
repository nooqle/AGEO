"""Tests for the flow-topology API payload normalization (3b-1.4).

DB round-trip is covered by API-level integration elsewhere; here we pin the
normalization contract that both endpoints rely on.
"""

from app.api.v1.amwaychina import _EMPTY_TOPOLOGY, _normalize_topology


def test_normalize_topology_garbage_yields_empty():
    assert _normalize_topology(None) == _EMPTY_TOPOLOGY
    assert _normalize_topology("junk") == _EMPTY_TOPOLOGY
    assert _normalize_topology({"customNodes": "bad"}) == _EMPTY_TOPOLOGY


def test_normalize_topology_canonicalizes_shape():
    normalized = _normalize_topology(
        {
            "version": 1,
            "customNodes": [
                {
                    "id": "custom-analysis-a1",
                    "type": "analysis",
                    "position": {"x": 100, "y": 200},
                    "config": {"label": "竞品解读"},
                },
                {"id": "", "type": "analysis"},  # dropped
            ],
            "customEdges": [
                {"id": "e-custom-1", "source": "projection", "target": "custom-analysis-a1"},
                {"id": "e-bad", "source": "", "target": "x"},  # dropped
            ],
            "removedEdgeIds": ["e-fetch-extract"],
        }
    )
    assert normalized["version"] == 1
    assert normalized["customNodes"] == [
        {
            "id": "custom-analysis-a1",
            "type": "analysis",
            "position": {"x": 100, "y": 200},
            "config": {"label": "竞品解读"},
        }
    ]
    assert normalized["customEdges"] == [
        {"id": "e-custom-1", "source": "projection", "target": "custom-analysis-a1"}
    ]
    assert normalized["removedEdgeIds"] == ["e-fetch-extract"]
