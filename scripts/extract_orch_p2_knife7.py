"""P2 knife 7 (cautious): knowledge_fallback + command_helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

KNOWLEDGE = [
    "_build_recent_knowledge_context",
    "_build_knowledge_planning_hint",
    "_infer_knowledge_fallback_tool",
    "_should_stream_thoughts",
]
COMMAND = [
    "_build_error_recovery_message",
    "_sanitize_runtime_policy_state",
    "_merge_command_update",
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

    for n in KNOWLEDGE + COMMAND:
        if n not in funcs:
            raise SystemExit(f"missing {n}")

    def bodies(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = funcs[n]
            chunk = _chunk(lines, s, e)
            chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            out.append(chunk.rstrip() + "\n\n")
        return "".join(out)

    (PKG / "knowledge_fallback.py").write_text(
        '"""Knowledge planning/fallback pure helpers (P2 knife 7, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.history_query import (\n"
        "    _has_terminal_knowledge_result,\n"
        "    _is_current_report_follow_up,\n"
        "    _is_precise_history_query,\n"
        "    _resolve_bounded_history_answer_query,\n"
        "    _session_was_recalled,\n"
        ")\n"
        "from app.workflow.orchestrator.knowledge_format import (\n"
        "    _format_knowledge_comparison,\n"
        "    _format_knowledge_group,\n"
        "    _format_knowledge_lookup_match,\n"
        ")\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n"
        "from app.workflow.orchestrator.session_tool_surface import (\n"
        "    _infer_authoritative_history_refresh_tool,\n"
        ")\n"
        "from app.workflow.orchestrator.text_normalize import (\n"
        "    _contains_non_negated_keyword,\n"
        ")\n\n"
        + bodies(KNOWLEDGE),
        encoding="utf-8",
    )
    print("wrote knowledge_fallback.py")

    (PKG / "command_helpers.py").write_text(
        '"""Command/update helpers (P2 knife 7, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from langgraph.types import Command\n\n"
        "from app.workflow.runtime_policy_executor import (\n"
        "    clear_runtime_policy_fields,\n"
        "    get_user_visible_runtime_label,\n"
        "    summarize_alternative_actions,\n"
        ")\n\n"
        + bodies(COMMAND),
        encoding="utf-8",
    )
    print("wrote command_helpers.py")

    spans = [funcs[n] for n in KNOWLEDGE + COMMAND]
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.prompt_context import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("prompt_context import missing")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.knowledge_fallback import (\n"
        "    _build_knowledge_planning_hint,\n"
        "    _build_recent_knowledge_context,\n"
        "    _infer_knowledge_fallback_tool,\n"
        "    _should_stream_thoughts,\n"
        ")\n"
        "from app.workflow.orchestrator.command_helpers import (\n"
        "    _build_error_recovery_message,\n"
        "    _merge_command_update,\n"
        "    _sanitize_runtime_policy_state,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
