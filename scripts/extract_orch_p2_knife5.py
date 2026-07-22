"""P2 knife 5 (cautious): session_tool_surface + reply_text + prompt_evidence."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

SURFACE_CONSTS = [
    "_CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES",
    "_SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES",
    "_KNOWLEDGE_TOOL_NAMES",
]
SURFACE_FUNCS = [
    "_infer_current_session_followup_tool",
    "_infer_authoritative_history_refresh_tool",
    "_stable_tool_surface_enabled",
    "_get_contextual_hidden_tool_names",
    "_should_force_fetch_recovery_confirmation",
]
REPLY_FUNCS = [
    "_build_knowledge_export_completion_reply",
    "_build_ask_user_fallback_reply",
]
EVIDENCE_CONSTS = ["_RECENT_EVIDENCE_PROMPT_PRIORITY"]
EVIDENCE_FUNCS = [
    "_render_recent_evidence_for_prompt",
    "_should_render_history_availability",
    "_should_render_instruction_defense",
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

    for n in SURFACE_FUNCS + REPLY_FUNCS + EVIDENCE_FUNCS:
        if n not in funcs:
            raise SystemExit(f"missing func {n}")
    for n in SURFACE_CONSTS + EVIDENCE_CONSTS:
        if n not in assigns:
            raise SystemExit(f"missing const {n}")

    def bodies(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = funcs[n]
            chunk = _chunk(lines, s, e)
            chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            chunk = chunk.replace(
                "state: AgentState | None", "state: Mapping[str, Any] | None"
            )
            out.append(chunk.rstrip() + "\n\n")
        return "".join(out)

    def consts(names: list[str]) -> str:
        out = []
        for n in names:
            s, e = assigns[n]
            out.append(_chunk(lines, s, e).rstrip() + "\n\n")
        return "".join(out)

    (PKG / "session_tool_surface.py").write_text(
        '"""Session follow-up / hidden tool surface (P2 knife 5, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.config import get_settings\n"
        "from app.workflow.orchestrator.history_query import (\n"
        "    _has_authoritative_history_refresh_result,\n"
        "    _is_current_report_follow_up,\n"
        "    _is_latest_run_history_stats_query,\n"
        "    _session_was_recalled,\n"
        ")\n"
        "from app.workflow.orchestrator.misc_pure import _normalize_sentiment_followup_value\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n\n"
        + consts(SURFACE_CONSTS)
        + bodies(SURFACE_FUNCS),
        encoding="utf-8",
    )
    print("wrote session_tool_surface.py")

    (PKG / "reply_text.py").write_text(
        '"""Deterministic reply builders (P2 knife 5, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.text_normalize import _normalize_public_knowledge_text\n\n"
        + bodies(REPLY_FUNCS),
        encoding="utf-8",
    )
    print("wrote reply_text.py")

    (PKG / "prompt_evidence.py").write_text(
        '"""Prompt evidence rendering helpers (P2 knife 5, cautious)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator_context_packets import (\n"
        "    RecentEvidencePacket,\n"
        "    render_recent_evidence_packet,\n"
        ")\n"
        "from app.workflow.orchestrator_instruction_defense import (\n"
        "    build_instruction_defense_context,\n"
        "    detect_instruction_injection,\n"
        ")\n"
        "from app.workflow.orchestrator.history_query import _session_was_recalled\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n"
        "from app.workflow.orchestrator.session_tool_surface import _KNOWLEDGE_TOOL_NAMES\n\n"
        + consts(EVIDENCE_CONSTS)
        + bodies(EVIDENCE_FUNCS),
        encoding="utf-8",
    )
    print("wrote prompt_evidence.py")

    spans: list[tuple[int, int]] = []
    for n in SURFACE_CONSTS + EVIDENCE_CONSTS:
        spans.append(assigns[n])
    for n in SURFACE_FUNCS + REPLY_FUNCS + EVIDENCE_FUNCS:
        spans.append(funcs[n])
    spans.sort(key=lambda x: x[0], reverse=True)

    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.misc_pure import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("misc_pure import block missing")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.session_tool_surface import (\n"
        "    _CURRENT_SESSION_FOLLOWUP_HIDDEN_TOOL_NAMES,\n"
        "    _KNOWLEDGE_TOOL_NAMES,\n"
        "    _SPECIFIC_DRILL_DOWN_HIDDEN_TOOL_NAMES,\n"
        "    _get_contextual_hidden_tool_names,\n"
        "    _infer_authoritative_history_refresh_tool,\n"
        "    _infer_current_session_followup_tool,\n"
        "    _should_force_fetch_recovery_confirmation,\n"
        "    _stable_tool_surface_enabled,\n"
        ")\n"
        "from app.workflow.orchestrator.reply_text import (\n"
        "    _build_ask_user_fallback_reply,\n"
        "    _build_knowledge_export_completion_reply,\n"
        ")\n"
        "from app.workflow.orchestrator.prompt_evidence import (\n"
        "    _RECENT_EVIDENCE_PROMPT_PRIORITY,\n"
        "    _render_recent_evidence_for_prompt,\n"
        "    _should_render_history_availability,\n"
        "    _should_render_instruction_defense,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
