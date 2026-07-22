"""P2 knife 8 (cautious): agent_result_summary + ontology_action_gate_decision + messages."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

DIRECTIVES = [
    "DIRECTIVE_A1_HAS_BASELINE",
    "DIRECTIVE_A1_NO_BASELINE",
    "DIRECTIVE_A2_ASK_PATH",
    "DIRECTIVE_A3_NEXT_FETCH",
    "DIRECTIVE_A5_BASELINE_NEXT",
    "DIRECTIVE_A5_PERSONA_NEXT",
]
SUMMARY_FUNCS = ["_build_agent_result_summary"]
GATE_FUNCS = ["_ontology_action_gate_decision"]
MSG_FUNCS = ["build_orchestrator_messages"]


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

    for n in SUMMARY_FUNCS + GATE_FUNCS + MSG_FUNCS:
        if n not in funcs:
            raise SystemExit(f"missing func {n}")
    for n in DIRECTIVES:
        if n not in assigns:
            raise SystemExit(f"missing const {n}")

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

    def consts(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = assigns[n]
            out.append(_chunk(lines, s, e).rstrip() + "\n\n")
        return "".join(out)

    (PKG / "agent_result_summary.py").write_text(
        '"""Agent tool-result summary builders (P2 knife 8, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.knowledge_fallback import (\n"
        "    _infer_knowledge_fallback_tool,\n"
        ")\n"
        "from app.workflow.orchestrator.text_normalize import (\n"
        "    _normalize_public_knowledge_text,\n"
        ")\n\n"
        + consts(DIRECTIVES)
        + bodies(SUMMARY_FUNCS),
        encoding="utf-8",
    )
    print("wrote agent_result_summary.py")

    # gate decision may only need ontology_action_feedback - check imports in body later
    (PKG / "ontology_action_gate.py").write_text(
        '"""Ontology action gate decision pure helper (P2 knife 8, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.ontology_action_feedback import (\n"
        "    ONTOLOGY_TOOL_ACTION_MAP,\n"
        "    _find_ontology_action_plan_item,\n"
        "    _ontology_action_feedback_for_key,\n"
        "    _ontology_feedback_covers_missing_inputs,\n"
        ")\n"
        "from app.workflow.orchestrator.ontology_format import (\n"
        "    _normalize_ontology_action_feedback_type,\n"
        ")\n\n"
        + bodies(GATE_FUNCS),
        encoding="utf-8",
    )
    print("wrote ontology_action_gate.py")

    (PKG / "orchestrator_messages.py").write_text(
        '"""Build orchestrator LLM message history (P2 knife 8, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "import logging\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.agent_result_summary import (\n"
        "    _build_agent_result_summary,\n"
        ")\n"
        "from app.workflow.orchestrator.message_builders import (\n"
        "    _inject_runtime_reminder_message,\n"
        ")\n\n"
        "logger = logging.getLogger(__name__)\n\n"
        + bodies(MSG_FUNCS),
        encoding="utf-8",
    )
    print("wrote orchestrator_messages.py")

    spans: list[tuple[int, int]] = []
    for n in DIRECTIVES:
        spans.append(assigns[n])
    for n in SUMMARY_FUNCS + GATE_FUNCS + MSG_FUNCS:
        spans.append(funcs[n])
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.command_helpers import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("command_helpers import missing")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.agent_result_summary import (\n"
        "    DIRECTIVE_A1_HAS_BASELINE,\n"
        "    DIRECTIVE_A1_NO_BASELINE,\n"
        "    DIRECTIVE_A2_ASK_PATH,\n"
        "    DIRECTIVE_A3_NEXT_FETCH,\n"
        "    DIRECTIVE_A5_BASELINE_NEXT,\n"
        "    DIRECTIVE_A5_PERSONA_NEXT,\n"
        "    _build_agent_result_summary,\n"
        ")\n"
        "from app.workflow.orchestrator.ontology_action_gate import (\n"
        "    _ontology_action_gate_decision,\n"
        ")\n"
        "from app.workflow.orchestrator.orchestrator_messages import (\n"
        "    build_orchestrator_messages,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
