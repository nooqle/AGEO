"""3c-C2: hybrid rule + LLM NL compile (LLM path mocked)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.api.v1.amwaychina import _EMPTY_TOPOLOGY, _normalize_topology
from app.workflow.node_contracts import FlowTopology
from app.workflow.topology_nl_llm import (
    compact_topology_for_compiler,
    compile_nl_auto,
    compile_nl_with_llm,
)
from app.workflow.topology_resolver import build_execution_plan_summary


@pytest.mark.asyncio
async def test_compile_auto_prefers_rule_without_llm():
    result = await compile_nl_auto("跳过豆包", _EMPTY_TOPOLOGY, allow_llm=True)
    assert result.mode == "rule"
    assert result.intent_id == "skip_doubao"


@pytest.mark.asyncio
async def test_compile_auto_llm_fallback(monkeypatch):
    async def fake_llm(text, base=None):
        return __import__(
            "app.workflow.topology_nl_compiler", fromlist=["CompileResult"]
        ).CompileResult(
            ops=[{"op": "disable_platform", "platform": "kimi"}],
            mode="llm",
            matched="mock",
            intent_id=None,
            confidence=0.7,
        )

    monkeypatch.setattr(
        "app.workflow.topology_nl_llm.compile_nl_with_llm",
        fake_llm,
    )
    result = await compile_nl_auto("请别用月之暗面那个平台了", _EMPTY_TOPOLOGY)
    assert result.mode == "llm"
    assert result.ops[0]["platform"] == "kimi"


@pytest.mark.asyncio
async def test_compile_with_llm_parses_and_validates(monkeypatch):
    class _Model:
        async def async_call(self, **kwargs):
            # Stable system must be first message
            assert kwargs["messages"][0]["role"] == "system"
            assert "Allowed ops" in kwargs["messages"][0]["content"] or "ops" in kwargs[
                "messages"
            ][0]["content"].lower()
            user = kwargs["messages"][1]["content"]
            assert "instruction" in user
            assert "topology" in user
            return SimpleNamespace(
                content='{"ops":[{"op":"disable_platform","platform":"doubao"}],'
                '"rationale_short":"skip doubao"}'
            )

    monkeypatch.setattr(
        "app.core.llm.get_llm_model",
        lambda **kwargs: _Model(),
    )
    # load_prompt_template may fail in some envs — patch stable prompt
    monkeypatch.setattr(
        "app.workflow.topology_nl_llm._load_stable_system_prompt",
        lambda: "# Topology Ops Compiler\n\nAllowed ops only\n",
    )
    result = await compile_nl_with_llm("别抓豆包", _EMPTY_TOPOLOGY)
    assert result.mode == "llm"
    proposed = __import__(
        "app.workflow.topology_patch", fromlist=["apply_topology_ops"]
    ).apply_topology_ops(_EMPTY_TOPOLOGY, result.ops)[0]
    plan = build_execution_plan_summary(
        FlowTopology.from_dict(_normalize_topology(proposed))
    )
    assert "doubao" not in (plan.get("planned_platforms") or [])


@pytest.mark.asyncio
async def test_compile_llm_rejects_empty_ops(monkeypatch):
    class _Model:
        async def async_call(self, **kwargs):
            return SimpleNamespace(content='{"ops":[],"error":"cannot_compile"}')

    monkeypatch.setattr("app.core.llm.get_llm_model", lambda **kwargs: _Model())
    monkeypatch.setattr(
        "app.workflow.topology_nl_llm._load_stable_system_prompt",
        lambda: "stable",
    )
    with pytest.raises(ValueError):
        await compile_nl_with_llm("随便聊聊", _EMPTY_TOPOLOGY)


def test_compact_topology_is_small():
    digest = compact_topology_for_compiler(
        {
            "removedEdgeIds": ["e-fetch-doubao"],
            "customNodes": [
                {
                    "id": "a1",
                    "type": "analysis",
                    "config": {"label": "x" * 100},
                }
            ],
            "customEdges": [{"id": "e1", "source": "projection", "target": "a1"}],
        }
    )
    assert digest["removedEdgeIds"] == ["e-fetch-doubao"]
    assert len(digest["customNodes"][0]["label"]) <= 40
