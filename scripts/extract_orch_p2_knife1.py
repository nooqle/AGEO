"""One-shot: extract pure orchestrator helpers into app.workflow.orchestrator (P2 knife 1)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    funcs: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = (node.lineno, node.end_lineno)

    extract_map = {
        "text_normalize": [
            "_normalize_public_report_kind",
            "_normalize_internal_analysis_mode",
            "_compact_text",
            "_normalize_public_knowledge_text",
            "_extract_exact_datetime_scope_text",
            "_contains_non_negated_keyword",
            "_is_english_dominant_text",
        ],
        "run_context": [
            "_get_latest_user_message",
        ],
        "report_state": [
            "_is_completed_analysis_report_state",
        ],
        "message_builders": [
            "_build_orchestrator_assistant_message",
            "_inject_runtime_reminder_message",
        ],
    }

    missing = [n for names in extract_map.values() for n in names if n not in funcs]
    if missing:
        raise SystemExit(f"missing funcs: {missing}")

    PKG.mkdir(parents=True, exist_ok=True)

    headers = {
        "text_normalize": (
            '"""Pure text/normalization helpers for orchestrator (P2 knife 1)."""\n\n'
            "from __future__ import annotations\n\n"
            "import re\n"
            "from typing import Any\n\n"
        ),
        "run_context": (
            '"""Run/session context helpers for orchestrator (P2 knife 1)."""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any, Mapping\n\n"
        ),
        "report_state": (
            '"""Report completion predicates for orchestrator (P2 knife 1)."""\n\n'
            "from __future__ import annotations\n\n"
            "from typing import Any, Mapping\n\n"
        ),
        "message_builders": (
            '"""Message construction helpers for orchestrator (P2 knife 1)."""\n\n'
            "from __future__ import annotations\n\n"
            "import json\n"
            "from typing import Any\n\n"
        ),
    }

    extracted_spans: list[tuple[int, int, str]] = []
    for mod, names in extract_map.items():
        body_parts: list[str] = []
        for n in names:
            start, end = funcs[n]
            chunk = "".join(lines[start - 1 : end])
            if mod in {"run_context", "report_state"}:
                chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
            body_parts.append(chunk.rstrip() + "\n\n")
            extracted_spans.append((start, end, n))
        (PKG / f"{mod}.py").write_text(headers[mod] + "".join(body_parts), encoding="utf-8")
        print(f"wrote {mod}.py ({len(names)} funcs)")

    run_extra = '''

def parse_recipe_meta_from_mapping(scope: Any) -> dict[str, str | None]:
    """Extract visible recipe metadata from input_scope / dashboard-like dicts."""
    if not isinstance(scope, dict):
        return {"recipe_id": None, "recipe_name": None}
    rid = scope.get("recipe_id") or scope.get("recipeId")
    rname = scope.get("recipe_name") or scope.get("recipeName")
    return {
        "recipe_id": str(rid).strip() if rid not in (None, "") else None,
        "recipe_name": str(rname).strip() if rname not in (None, "") else None,
    }


def get_input_scope(state: Mapping[str, Any]) -> dict[str, Any]:
    raw = state.get("input_scope")
    return raw if isinstance(raw, dict) else {}


def get_recipe_meta_from_state(state: Mapping[str, Any]) -> dict[str, str | None]:
    return parse_recipe_meta_from_mapping(get_input_scope(state))
'''
    rc = PKG / "run_context.py"
    rc.write_text(rc.read_text(encoding="utf-8") + run_extra, encoding="utf-8")

    (PKG / "__init__.py").write_text(
        '''"""Orchestrator package — extracted modules (P2 split).

Public entry remains ``app.workflow.orchestrator_node`` for graph wiring.
"""

from app.workflow.orchestrator.message_builders import (
    _build_orchestrator_assistant_message,
    _inject_runtime_reminder_message,
)
from app.workflow.orchestrator.report_state import _is_completed_analysis_report_state
from app.workflow.orchestrator.run_context import (
    _get_latest_user_message,
    get_input_scope,
    get_recipe_meta_from_state,
    parse_recipe_meta_from_mapping,
)
from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _contains_non_negated_keyword,
    _extract_exact_datetime_scope_text,
    _is_english_dominant_text,
    _normalize_internal_analysis_mode,
    _normalize_public_knowledge_text,
    _normalize_public_report_kind,
)

__all__ = [
    "_build_orchestrator_assistant_message",
    "_compact_text",
    "_contains_non_negated_keyword",
    "_extract_exact_datetime_scope_text",
    "_get_latest_user_message",
    "_inject_runtime_reminder_message",
    "_is_completed_analysis_report_state",
    "_is_english_dominant_text",
    "_normalize_internal_analysis_mode",
    "_normalize_public_knowledge_text",
    "_normalize_public_report_kind",
    "get_input_scope",
    "get_recipe_meta_from_state",
    "parse_recipe_meta_from_mapping",
]
''',
        encoding="utf-8",
    )

    extracted_spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end, _name in extracted_spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    marker = "from app.workflow.state import AgentState\n"
    inject = """from app.workflow.state import AgentState
from app.workflow.orchestrator.message_builders import (
    _build_orchestrator_assistant_message,
    _inject_runtime_reminder_message,
)
from app.workflow.orchestrator.report_state import _is_completed_analysis_report_state
from app.workflow.orchestrator.run_context import _get_latest_user_message
from app.workflow.orchestrator.text_normalize import (
    _compact_text,
    _contains_non_negated_keyword,
    _extract_exact_datetime_scope_text,
    _is_english_dominant_text,
    _normalize_internal_analysis_mode,
    _normalize_public_knowledge_text,
    _normalize_public_report_kind,
)
"""
    if marker not in join_text:
        raise SystemExit("import marker not found")
    join_text = join_text.replace(marker, inject, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(
        f"orchestrator_node lines: {len(lines)} -> {len(join_text.splitlines())} "
        f"(delta {len(join_text.splitlines()) - len(lines)})"
    )


if __name__ == "__main__":
    main()
