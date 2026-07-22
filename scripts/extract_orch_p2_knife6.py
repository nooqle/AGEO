"""P2 knife 6 (cautious): tool_gate + prompt_context."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

TOOL_GATE = ["validate_tool_available_in_current_state"]
PROMPT_CTX = [
    "_build_context_summary",
    "_build_public_skill_index",
    "_build_contextual_tool_surface_note",
    "_build_orchestrator_data_status",
    "_build_orchestrator_entity_context",
]


def _chunk(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    funcs: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = (node.lineno, node.end_lineno)

    for n in TOOL_GATE + PROMPT_CTX:
        if n not in funcs:
            raise SystemExit(f"missing {n}")

    def bodies(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = funcs[n]
            chunk = _chunk(lines, s, e)
            chunk = chunk.replace(
                "state: AgentState | None", "state: Mapping[str, Any] | None"
            )
            chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            out.append(chunk.rstrip() + "\n\n")
        return "".join(out)

    (PKG / "tool_gate.py").write_text(
        '"""Tool availability gate (P2 knife 6, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.services.tool_capability_matrix import ToolAvailabilityConstraint\n"
        "from app.workflow.orchestrator.history_query import _session_was_recalled\n"
        "from app.workflow.orchestrator.misc_pure import _format_tool_args_for_suggestion\n"
        "from app.workflow.orchestrator.session_tool_surface import (\n"
        "    _KNOWLEDGE_TOOL_NAMES,\n"
        "    _get_contextual_hidden_tool_names,\n"
        "    _infer_current_session_followup_tool,\n"
        ")\n\n"
        + bodies(TOOL_GATE),
        encoding="utf-8",
    )
    print("wrote tool_gate.py")

    (PKG / "prompt_context.py").write_text(
        '"""Prompt context summary helpers (P2 knife 6, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.services.skill_registry_service import build_builtin_skill_tool_definitions\n"
        "from app.workflow.orchestrator_context_packets import (\n"
        "    build_entity_context_packet,\n"
        "    build_session_status_packet,\n"
        "    render_entity_context_packet,\n"
        "    render_session_status_packet,\n"
        ")\n"
        "from app.workflow.orchestrator.session_tool_surface import (\n"
        "    _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES,\n"
        "    _get_contextual_hidden_tool_names,\n"
        "    _infer_current_session_followup_tool,\n"
        "    _stable_tool_surface_enabled,\n"
        ")\n"
        "from app.workflow.orchestrator.text_normalize import _compact_text\n\n"
        + bodies(PROMPT_CTX),
        encoding="utf-8",
    )
    print("wrote prompt_context.py")

    spans = [funcs[n] for n in TOOL_GATE + PROMPT_CTX]
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.prompt_evidence import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("prompt_evidence import missing")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.tool_gate import (\n"
        "    validate_tool_available_in_current_state,\n"
        ")\n"
        "from app.workflow.orchestrator.prompt_context import (\n"
        "    _build_context_summary,\n"
        "    _build_contextual_tool_surface_note,\n"
        "    _build_orchestrator_data_status,\n"
        "    _build_orchestrator_entity_context,\n"
        "    _build_public_skill_index,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
