"""P2 knife 4 (cautious): ontology_action_feedback + misc_pure only."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

FEEDBACK_FUNCS = [
    "_ontology_action_feedback_for_key",
    "_ontology_feedback_covers_missing_inputs",
    "_ontology_feedback_provided_inputs",
    "_ontology_confirmed_action_for_tool",
    "_ontology_action_feedback_for_tool",
    "_merge_ontology_provided_inputs_into_tool_args",
    "_find_ontology_action_plan_item",
    "_ontology_action_gate_message",
    "_ontology_action_gate_options",
]

MISC_FUNCS = [
    "_normalize_sentiment_followup_value",
    "_format_tool_args_for_suggestion",
    "_infer_current_import_query",
    "_build_static_public_skill_index",
]


def _chunk(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    funcs: dict[str, tuple[int, int]] = {}
    assigns: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns[t.id] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigns[node.target.id] = (node.lineno, node.end_lineno)

    for n in FEEDBACK_FUNCS + MISC_FUNCS:
        if n not in funcs:
            raise SystemExit(f"missing {n}")
    if "ONTOLOGY_TOOL_ACTION_MAP" not in assigns:
        raise SystemExit("ONTOLOGY_TOOL_ACTION_MAP missing")

    def bodies(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = funcs[n]
            chunk = _chunk(lines, s, e)
            chunk = chunk.replace(
                "state: AgentState | dict[str, Any] | None",
                "state: Mapping[str, Any] | dict[str, Any] | None",
            )
            chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            out.append(chunk.rstrip() + "\n\n")
        return "".join(out)

    map_s, map_e = assigns["ONTOLOGY_TOOL_ACTION_MAP"]
    tool_map = _chunk(lines, map_s, map_e).rstrip() + "\n\n"

    (PKG / "ontology_action_feedback.py").write_text(
        '"""Ontology action feedback pure helpers (P2 knife 4, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.ontology_format import (\n"
        "    _normalize_ontology_action_feedback_type,\n"
        "    _ontology_payload_has_value,\n"
        "    _ontology_tool_arg_key_for_input,\n"
        ")\n\n"
        + tool_map
        + bodies(FEEDBACK_FUNCS),
        encoding="utf-8",
    )
    print("wrote ontology_action_feedback.py")

    (PKG / "misc_pure.py").write_text(
        '"""Small pure helpers (P2 knife 4, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.services.skill_registry_service import build_builtin_skill_tool_definitions\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n"
        "from app.workflow.orchestrator.text_normalize import _compact_text\n\n"
        + bodies(MISC_FUNCS),
        encoding="utf-8",
    )
    print("wrote misc_pure.py")

    spans = [assigns["ONTOLOGY_TOOL_ACTION_MAP"]] + [
        funcs[n] for n in FEEDBACK_FUNCS + MISC_FUNCS
    ]
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.prompt_bundle import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("prompt_bundle import block not found")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.ontology_action_feedback import (\n"
        "    ONTOLOGY_TOOL_ACTION_MAP,\n"
        "    _find_ontology_action_plan_item,\n"
        "    _merge_ontology_provided_inputs_into_tool_args,\n"
        "    _ontology_action_feedback_for_key,\n"
        "    _ontology_action_feedback_for_tool,\n"
        "    _ontology_action_gate_message,\n"
        "    _ontology_action_gate_options,\n"
        "    _ontology_confirmed_action_for_tool,\n"
        "    _ontology_feedback_covers_missing_inputs,\n"
        "    _ontology_feedback_provided_inputs,\n"
        ")\n"
        "from app.workflow.orchestrator.misc_pure import (\n"
        "    _build_static_public_skill_index,\n"
        "    _format_tool_args_for_suggestion,\n"
        "    _infer_current_import_query,\n"
        "    _normalize_sentiment_followup_value,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
