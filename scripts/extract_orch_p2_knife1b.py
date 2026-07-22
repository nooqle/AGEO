"""P2 knife 1b: extract more pure ontology + thought stream helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

EXTRACT = {
    "ontology_format": [
        "_ontology_status_label",
        "_ontology_int",
        "_ontology_float",
        "_ontology_brand_label",
        "_ontology_object_summaries",
        "_source_domain_sort_key",
        "_relationship_is_core",
        "_action_readiness_label",
        "_ontology_payload_has_value",
        "_normalize_ontology_action_feedback_type",
        "_ontology_tool_arg_key_for_input",
    ],
    "thought_stream": [
        "_localize_visible_terms",
        "_normalize_thought_text_for_stream",
    ],
}


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    funcs: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = (node.lineno, node.end_lineno)

    # Find _VISIBLE_TOOL_NAME_LABELS assignment for thought_stream
    # We'll import from orchestrator_node would cycle - copy constant if small
    visible_labels = None
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "_VISIBLE_TOOL_NAME_LABELS":
                    visible_labels = ast.get_source_segment(text, node)
    if not visible_labels:
        # try AnnAssign
        for node in tree.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                if node.target.id == "_VISIBLE_TOOL_NAME_LABELS":
                    visible_labels = ast.get_source_segment(text, node)

    missing = [n for names in EXTRACT.values() for n in names if n not in funcs]
    if missing:
        raise SystemExit(f"missing: {missing}")

    headers = {
        "ontology_format": (
            '"""Ontology display/format pure helpers (P2 knife 1b)."""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any\n\n"
        ),
        "thought_stream": (
            '"""Thought stream localization helpers (P2 knife 1b)."""\n\n'
            "from __future__ import annotations\n\n"
            "from app.workflow.orchestrator.text_normalize import _is_english_dominant_text\n\n"
        ),
    }

    spans: list[tuple[int, int]] = []
    for mod, names in EXTRACT.items():
        parts: list[str] = []
        if mod == "thought_stream":
            if not visible_labels:
                # fallback minimal
                parts.append(
                    "_VISIBLE_TOOL_NAME_LABELS = {\n"
                    '    "brand_analysis": "品牌分析",\n'
                    '    "question_simulation": "问题模拟",\n'
                    '    "answer_fetch": "答案抓取",\n'
                    '    "data_analytics": "数据分析",\n'
                    "}\n\n"
                )
            else:
                parts.append(visible_labels.rstrip() + "\n\n")
        for n in names:
            start, end = funcs[n]
            chunk = "".join(lines[start - 1 : end])
            parts.append(chunk.rstrip() + "\n\n")
            spans.append((start, end))
        (PKG / f"{mod}.py").write_text(headers[mod] + "".join(parts), encoding="utf-8")
        print(f"wrote {mod}.py")

    spans.sort(reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    marker = "from app.workflow.orchestrator.text_normalize import ("
    # extend existing text_normalize import block with thought + ontology imports after AgentState inject area
    inject_after = "from app.workflow.orchestrator.text_normalize import (\n    _compact_text,\n    _contains_non_negated_keyword,\n    _extract_exact_datetime_scope_text,\n    _is_english_dominant_text,\n    _normalize_internal_analysis_mode,\n    _normalize_public_knowledge_text,\n    _normalize_public_report_kind,\n)\n"
    extra = inject_after + (
        "from app.workflow.orchestrator.ontology_format import (\n"
        "    _action_readiness_label,\n"
        "    _normalize_ontology_action_feedback_type,\n"
        "    _ontology_brand_label,\n"
        "    _ontology_float,\n"
        "    _ontology_int,\n"
        "    _ontology_object_summaries,\n"
        "    _ontology_payload_has_value,\n"
        "    _ontology_status_label,\n"
        "    _ontology_tool_arg_key_for_input,\n"
        "    _relationship_is_core,\n"
        "    _source_domain_sort_key,\n"
        ")\n"
        "from app.workflow.orchestrator.thought_stream import (\n"
        "    _localize_visible_terms,\n"
        "    _normalize_thought_text_for_stream,\n"
        ")\n"
    )
    if inject_after not in join_text:
        raise SystemExit("expected text_normalize import block missing")
    join_text = join_text.replace(inject_after, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"lines now {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
