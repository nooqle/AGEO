"""Deterministic topology ops apply (blueprint 3c-B).

No LLM. Produces a next topology document from a base + ops list, then callers
must run ``validate_topology_document``. Preset intent_id expand to ops for
the no-NL vertical slice.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.workflow.topology_resolver import (
    BUILTIN_EDGE_IDS,
    CANVAS_PLATFORM_IDS,
    platform_edge_id,
)

ALLOWED_CUSTOM_NODE_TYPES = frozenset({"analysis", "content"})
ALLOWED_OPS = frozenset(
    {
        "disable_platform",
        "enable_platform",
        "remove_builtin_edge",
        "restore_builtin_edge",
        "add_custom_node",
        "remove_custom_node",
        "add_custom_edge",
        "remove_custom_edge",
        "patch_node_config",
    }
)

# Deterministic presets (3c-B). C will map NL → intent_id or raw ops.
PRESET_INTENTS: dict[str, str] = {
    "skip_doubao": "跳过豆包采集",
    "enable_all_platforms": "恢复全部平台连线",
    "add_projection_analysis": "在图谱后挂一个分析节点",
}


def expand_intent(intent_id: str, base: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Expand a preset intent_id into concrete ops (may depend on base for ids)."""
    key = str(intent_id or "").strip()
    if key == "skip_doubao":
        return [{"op": "disable_platform", "platform": "doubao"}]
    if key == "enable_all_platforms":
        return [{"op": "enable_platform", "platform": p} for p in CANVAS_PLATFORM_IDS]
    if key == "add_projection_analysis":
        base = base if isinstance(base, dict) else {}
        existing_ids = {
            str(n.get("id"))
            for n in (base.get("customNodes") or [])
            if isinstance(n, dict) and n.get("id")
        }
        # Deterministic ids only (F1): preview and apply must expand to the same
        # ops for the same base. Never use random UUID here.
        node_id = "custom-analysis-3c-preset"
        if node_id in existing_ids:
            n = 2
            while f"custom-analysis-3c-preset-{n}" in existing_ids:
                n += 1
            node_id = f"custom-analysis-3c-preset-{n}"
        edge_id = f"e-{node_id}"
        return [
            {
                "op": "add_custom_node",
                "node": {
                    "id": node_id,
                    "type": "analysis",
                    "position": {"x": 720, "y": 420},
                    "config": {"label": "图谱解读"},
                },
            },
            {
                "op": "add_custom_edge",
                "edge": {
                    "id": edge_id,
                    "source": "projection",
                    "target": node_id,
                },
            },
        ]
    raise ValueError(f"未知预设意图：{key}")


def _as_topology_dict(raw: dict[str, Any] | None) -> dict[str, Any]:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "version": int(raw.get("version") or 1),
        "customNodes": [
            dict(n)
            for n in (raw.get("customNodes") or [])
            if isinstance(n, dict) and n.get("id") and n.get("type")
        ],
        "customEdges": [
            dict(e)
            for e in (raw.get("customEdges") or [])
            if isinstance(e, dict) and e.get("source") and e.get("target")
        ],
        "removedEdgeIds": [
            str(r) for r in (raw.get("removedEdgeIds") or []) if isinstance(r, str)
        ],
    }


def _summary_delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_nodes = {str(n["id"]) for n in before["customNodes"]}
    after_nodes = {str(n["id"]) for n in after["customNodes"]}
    before_edges = {str(e.get("id") or f"{e['source']}->{e['target']}") for e in before["customEdges"]}
    after_edges = {str(e.get("id") or f"{e['source']}->{e['target']}") for e in after["customEdges"]}
    before_removed = set(before["removedEdgeIds"])
    after_removed = set(after["removedEdgeIds"])
    nodes_added = sorted(after_nodes - before_nodes)
    nodes_removed = sorted(before_nodes - after_nodes)
    edges_added = sorted(after_edges - before_edges)
    edges_removed = sorted(before_edges - after_edges)
    removed_added = sorted(after_removed - before_removed)
    removed_restored = sorted(before_removed - after_removed)
    parts: list[str] = []
    if removed_added:
        parts.append("断开：" + ", ".join(removed_added))
    if removed_restored:
        parts.append("恢复：" + ", ".join(removed_restored))
    if nodes_added:
        parts.append("新增节点：" + ", ".join(nodes_added))
    if nodes_removed:
        parts.append("删除节点：" + ", ".join(nodes_removed))
    if edges_added:
        parts.append("新增连线：" + ", ".join(edges_added))
    if edges_removed:
        parts.append("删除连线：" + ", ".join(edges_removed))
    text = "；".join(parts) if parts else "无实质变更"
    return {
        "text": text,
        "nodes_added": nodes_added,
        "nodes_removed": nodes_removed,
        "edges_added": edges_added,
        "edges_removed": edges_removed,
        "removed_edge_ids_added": removed_added,
        "removed_edge_ids_restored": removed_restored,
    }


def apply_topology_ops(
    base: dict[str, Any] | None,
    ops: list[dict[str, Any]] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Apply ops to base topology. Returns (proposed_raw, summary).

    Does **not** call validate_topology_document — caller must.
    """
    if not isinstance(ops, list) or not ops:
        raise ValueError("ops 不能为空")
    current = _as_topology_dict(base)
    before = deepcopy(current)
    nodes_by_id: dict[str, dict[str, Any]] = {
        str(n["id"]): n for n in current["customNodes"]
    }
    edges_by_id: dict[str, dict[str, Any]] = {}
    for e in current["customEdges"]:
        eid = str(e.get("id") or f"{e['source']}->{e['target']}")
        e = {**e, "id": eid}
        edges_by_id[eid] = e
    removed: set[str] = set(current["removedEdgeIds"])

    for i, raw_op in enumerate(ops):
        if not isinstance(raw_op, dict):
            raise ValueError(f"ops[{i}] 必须是对象")
        op = str(raw_op.get("op") or "").strip()
        if op not in ALLOWED_OPS:
            raise ValueError(f"未知 op：{op or '(empty)'}")

        if op == "disable_platform":
            platform = str(raw_op.get("platform") or "").strip()
            if platform not in CANVAS_PLATFORM_IDS:
                raise ValueError(f"无效平台：{platform}")
            removed.add(platform_edge_id(platform))
        elif op == "enable_platform":
            platform = str(raw_op.get("platform") or "").strip()
            if platform not in CANVAS_PLATFORM_IDS:
                raise ValueError(f"无效平台：{platform}")
            removed.discard(platform_edge_id(platform))
        elif op == "remove_builtin_edge":
            edge_id = str(raw_op.get("edge_id") or "").strip()
            if edge_id not in BUILTIN_EDGE_IDS:
                raise ValueError(f"非内置边：{edge_id}")
            removed.add(edge_id)
        elif op == "restore_builtin_edge":
            edge_id = str(raw_op.get("edge_id") or "").strip()
            if edge_id not in BUILTIN_EDGE_IDS:
                raise ValueError(f"非内置边：{edge_id}")
            removed.discard(edge_id)
        elif op == "add_custom_node":
            node = raw_op.get("node")
            if not isinstance(node, dict):
                raise ValueError("add_custom_node 需要 node 对象")
            nid = str(node.get("id") or "").strip()
            ntype = str(node.get("type") or "").strip()
            if not nid:
                raise ValueError("自定义节点 id 不能为空")
            if ntype not in ALLOWED_CUSTOM_NODE_TYPES:
                raise ValueError(f"不支持的节点类型：{ntype}")
            pos = node.get("position") if isinstance(node.get("position"), dict) else {}
            cfg = node.get("config") if isinstance(node.get("config"), dict) else {}
            # Same id: overwrite position/config/type (idempotent upsert)
            nodes_by_id[nid] = {
                "id": nid,
                "type": ntype,
                "position": {
                    "x": float(pos.get("x") or 0),
                    "y": float(pos.get("y") or 0),
                },
                "config": dict(cfg),
            }
        elif op == "remove_custom_node":
            nid = str(raw_op.get("node_id") or "").strip()
            if not nid:
                raise ValueError("remove_custom_node 需要 node_id")
            nodes_by_id.pop(nid, None)
            edges_by_id = {
                eid: e
                for eid, e in edges_by_id.items()
                if e.get("source") != nid and e.get("target") != nid
            }
        elif op == "add_custom_edge":
            edge = raw_op.get("edge")
            if not isinstance(edge, dict):
                raise ValueError("add_custom_edge 需要 edge 对象")
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            eid = str(edge.get("id") or f"{source}->{target}").strip()
            if not source or not target:
                raise ValueError("自定义连线 source/target 不能为空")
            if not eid:
                raise ValueError("自定义连线 id 不能为空")
            # Same id: overwrite endpoints
            edges_by_id[eid] = {"id": eid, "source": source, "target": target}
        elif op == "remove_custom_edge":
            eid = str(raw_op.get("edge_id") or "").strip()
            if not eid:
                raise ValueError("remove_custom_edge 需要 edge_id")
            edges_by_id.pop(eid, None)
        elif op == "patch_node_config":
            nid = str(raw_op.get("node_id") or "").strip()
            patch = raw_op.get("config")
            if not nid:
                raise ValueError("patch_node_config 需要 node_id")
            if not isinstance(patch, dict):
                raise ValueError("patch_node_config 需要 config 对象")
            if nid not in nodes_by_id:
                raise ValueError(f"节点不存在：{nid}")
            merged = dict(nodes_by_id[nid].get("config") or {})
            merged.update(patch)
            nodes_by_id[nid] = {**nodes_by_id[nid], "config": merged}

    proposed = {
        "version": current["version"],
        "customNodes": [nodes_by_id[k] for k in sorted(nodes_by_id.keys())],
        "customEdges": [edges_by_id[k] for k in sorted(edges_by_id.keys())],
        "removedEdgeIds": sorted(removed),
    }
    return proposed, _summary_delta(before, proposed)


def resolve_ops_payload(
    *,
    intent_id: str | None,
    ops: list[dict[str, Any]] | None,
    base: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """B rule: intent_id XOR ops (exactly one)."""
    has_intent = bool(str(intent_id or "").strip())
    has_ops = isinstance(ops, list) and len(ops) > 0
    if has_intent and has_ops:
        raise ValueError("intent_id 与 ops 只能二选一")
    if not has_intent and not has_ops:
        raise ValueError("必须提供 intent_id 或 ops")
    if has_intent:
        return expand_intent(str(intent_id).strip(), base)
    return list(ops or [])
