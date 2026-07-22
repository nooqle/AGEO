"""P2 knife 2: history_query + workflow_progress + knowledge_format extract."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

HISTORY = [
    "_contains_positive_continuation_marker",
    "_is_precise_history_query",
    "_is_history_answer_content_query",
    "_is_history_answer_continuation_query",
    "_iter_recent_history_messages",
    "_has_recent_history_answer_followup_invite",
    "_get_recent_history_answer_basis_query",
    "_build_history_answer_export_query",
    "_get_recent_history_answer_result_query",
    "_session_was_recalled",
    "_is_current_report_follow_up",
    "_resolve_bounded_history_answer_query",
    "_is_bounded_history_answer_query_state",
    "_is_latest_run_history_stats_query",
    "_has_authoritative_history_refresh_result",
    "_has_terminal_knowledge_result",
    "_is_explicit_question_generation_only_request",
    "_is_question_generation_only_state",
]

KNOWLEDGE = [
    "_format_knowledge_lookup_match",
    "_format_knowledge_group",
    "_format_knowledge_comparison",
]

WORKFLOW = [
    "_get_tool_name_from_node",
    "_is_completed_question_generation_only_state",
    "_build_workflow_steps",
    "_is_step_skipped",
    "_matches_failed_step",
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
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns[t.id] = (node.lineno, node.end_lineno)
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigns[node.target.id] = (node.lineno, node.end_lineno)

    all_names = HISTORY + KNOWLEDGE + WORKFLOW
    missing = [n for n in all_names if n not in funcs]
    if missing:
        raise SystemExit(f"missing funcs: {missing}")
    if "WORKFLOW_STEPS" not in assigns:
        raise SystemExit("WORKFLOW_STEPS assign not found")

    def body(names: list[str]) -> str:
        parts = []
        for n in names:
            s, e = funcs[n]
            chunk = _chunk(lines, s, e)
            chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            chunk = chunk.replace(
                "state: AgentState | None", "state: Mapping[str, Any] | None"
            )
            parts.append(chunk.rstrip() + "\n\n")
        return "".join(parts)

    # history_query
    (PKG / "history_query.py").write_text(
        '"""History / follow-up query predicates (P2 knife 2)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n"
        "from app.workflow.orchestrator.text_normalize import (\n"
        "    _contains_non_negated_keyword,  # noqa: F401  # reserved for parity\n"
        "    _extract_exact_datetime_scope_text,\n"
        ")\n\n"
        + body(HISTORY).replace(
            "from app.workflow.orchestrator.text_normalize import (\n"
            "    _contains_non_negated_keyword,  # noqa: F401  # reserved for parity\n"
            "    _extract_exact_datetime_scope_text,\n"
            ")\n\n",
            "from app.workflow.orchestrator.text_normalize import (\n"
            "    _extract_exact_datetime_scope_text,\n"
            ")\n"
            "from app.workflow.orchestrator.text_normalize import (\n"
            "    _contains_non_negated_keyword,\n"
            ")\n\n",
            1,
        )
        if False
        else (
            '"""History / follow-up query predicates (P2 knife 2)."""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any, Mapping\n\n"
            "from app.workflow.orchestrator.run_context import _get_latest_user_message\n"
            "from app.workflow.orchestrator.text_normalize import (\n"
            "    _contains_non_negated_keyword,\n"
            "    _extract_exact_datetime_scope_text,\n"
            ")\n\n"
            + body(HISTORY)
        ),
        encoding="utf-8",
    )
    print("wrote history_query.py")

    (PKG / "knowledge_format.py").write_text(
        '"""Knowledge result formatting helpers (P2 knife 2)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any\n\n"
        "from app.workflow.orchestrator.text_normalize import (\n"
        "    _compact_text,\n"
        "    _normalize_public_knowledge_text,\n"
        ")\n\n"
        + body(KNOWLEDGE),
        encoding="utf-8",
    )
    print("wrote knowledge_format.py")

    ws_start, ws_end = assigns["WORKFLOW_STEPS"]
    workflow_const = _chunk(lines, ws_start, ws_end).rstrip() + "\n\n"
    (PKG / "workflow_progress.py").write_text(
        '"""Workflow step progress helpers (P2 knife 2)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.history_query import (\n"
        "    _is_question_generation_only_state,\n"
        ")\n\n"
        + workflow_const
        + body(WORKFLOW),
        encoding="utf-8",
    )
    print("wrote workflow_progress.py")

    # delete extracted ranges (funcs + WORKFLOW_STEPS)
    spans = [funcs[n] for n in all_names] + [assigns["WORKFLOW_STEPS"]]
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    inject_anchor = "from app.workflow.orchestrator.thought_stream import (\n    _localize_visible_terms,\n    _normalize_thought_text_for_stream,\n)\n"
    extra = inject_anchor + (
        "from app.workflow.orchestrator.history_query import (\n"
        "    _build_history_answer_export_query,\n"
        "    _contains_positive_continuation_marker,\n"
        "    _get_recent_history_answer_basis_query,\n"
        "    _get_recent_history_answer_result_query,\n"
        "    _has_authoritative_history_refresh_result,\n"
        "    _has_recent_history_answer_followup_invite,\n"
        "    _has_terminal_knowledge_result,\n"
        "    _is_bounded_history_answer_query_state,\n"
        "    _is_current_report_follow_up,\n"
        "    _is_explicit_question_generation_only_request,\n"
        "    _is_history_answer_content_query,\n"
        "    _is_history_answer_continuation_query,\n"
        "    _is_latest_run_history_stats_query,\n"
        "    _is_precise_history_query,\n"
        "    _is_question_generation_only_state,\n"
        "    _iter_recent_history_messages,\n"
        "    _resolve_bounded_history_answer_query,\n"
        "    _session_was_recalled,\n"
        ")\n"
        "from app.workflow.orchestrator.knowledge_format import (\n"
        "    _format_knowledge_comparison,\n"
        "    _format_knowledge_group,\n"
        "    _format_knowledge_lookup_match,\n"
        ")\n"
        "from app.workflow.orchestrator.workflow_progress import (\n"
        "    WORKFLOW_STEPS,\n"
        "    _build_workflow_steps,\n"
        "    _get_tool_name_from_node,\n"
        "    _is_completed_question_generation_only_state,\n"
        "    _is_step_skipped,\n"
        "    _matches_failed_step,\n"
        ")\n"
    )
    if inject_anchor not in join_text:
        raise SystemExit("thought_stream import anchor missing")
    join_text = join_text.replace(inject_anchor, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
