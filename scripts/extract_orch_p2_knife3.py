"""P2 knife 3: ontology_intelligence + seed_surface + prompt_bundle."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

ONTOLOGY_FUNCS = [
    "_is_ontology_intelligence_explanation_request",
    "_format_source_domains_for_reply",
    "_format_relationships_for_reply",
    "_ontology_object_total",
    "_sorted_source_domains",
    "_source_domain_reply_line",
    "_evidence_cluster_sort_key",
    "_sorted_evidence_clusters",
    "_evidence_cluster_reply_line",
    "_available_action_items",
    "_action_reply_line",
    "_ontology_intelligence_question_kind",
    "_build_official_website_gap_reply",
    "_build_source_substitution_reply",
    "_build_evidence_cluster_value_reply",
    "_build_relationship_risk_reply",
    "_build_supporting_relationships_reply",
    "_build_action_boundary_reply",
    "_build_ontology_intelligence_explanation_reply",
    "_with_intelligence_reply_closure",
]

SEED_FUNCS = [
    "_build_panorama_step_intro",
    "_extract_site_confidence_root_url",
    "_is_site_confidence_request",
    "_infer_brand_seed_candidate",
    "_looks_like_keyword_list",
    "_normalize_tool_topic_keywords",
    "_has_persona_prerequisites",
    "_resolve_brand_name_for_dependency_rebuild",
]

PROMPT_FUNCS = [
    "_runtime_reminder_message_enabled",
    "_wrap_runtime_reminder_message",
    "_build_orchestrator_prompt_bundle_from_assembly",
]


def _chunk(lines: list[str], start: int, end: int) -> str:
    return "".join(lines[start - 1 : end])


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    funcs: dict[str, tuple[int, int]] = {}
    assigns: dict[str, tuple[int, int]] = {}
    classes: dict[str, tuple[int, int]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            funcs[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.ClassDef):
            classes[node.name] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    assigns[t.id] = (node.lineno, node.end_lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            assigns[node.target.id] = (node.lineno, node.end_lineno)

    missing = [
        n
        for n in ONTOLOGY_FUNCS + SEED_FUNCS + PROMPT_FUNCS
        if n not in funcs
    ]
    if missing:
        raise SystemExit(f"missing: {missing}")
    if "CORE_RELATIONSHIP_TYPES" not in assigns:
        raise SystemExit("CORE_RELATIONSHIP_TYPES missing")
    if "OrchestratorPromptBundle" not in classes:
        raise SystemExit("OrchestratorPromptBundle missing")

    def bodies(names: list[str]) -> str:
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

    core_s, core_e = assigns["CORE_RELATIONSHIP_TYPES"]
    core_const = _chunk(lines, core_s, core_e).rstrip() + "\n\n"

    (PKG / "ontology_intelligence.py").write_text(
        '"""Ontology intelligence explanation replies (P2 knife 3)."""\n\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.ontology_format import (\n"
        "    _action_readiness_label,\n"
        "    _ontology_brand_label,\n"
        "    _ontology_float,\n"
        "    _ontology_int,\n"
        "    _ontology_object_summaries,\n"
        "    _ontology_status_label,\n"
        "    _relationship_is_core,\n"
        "    _source_domain_sort_key,\n"
        ")\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n\n"
        + core_const
        + bodies(ONTOLOGY_FUNCS),
        encoding="utf-8",
    )
    print("wrote ontology_intelligence.py")

    (PKG / "seed_surface.py").write_text(
        '"""Brand seed / site confidence / panorama intro helpers (P2 knife 3)."""\n\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator.history_query import (\n"
        "    _is_explicit_question_generation_only_request,\n"
        ")\n"
        "from app.workflow.orchestrator.run_context import _get_latest_user_message\n\n"
        + bodies(SEED_FUNCS),
        encoding="utf-8",
    )
    print("wrote seed_surface.py")

    # dataclass may use @dataclass decorator - capture with class lineno including decorator
    # Use class node lineno which is class line, need decorators
    bundle_node = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "OrchestratorPromptBundle"
    )
    # include decorator lines
    dec_start = min([d.lineno for d in bundle_node.decorator_list] + [bundle_node.lineno])
    bundle_cls = _chunk(lines, dec_start, bundle_node.end_lineno).rstrip() + "\n\n"

    (PKG / "prompt_bundle.py").write_text(
        '"""Orchestrator prompt bundle construction (P2 knife 3)."""\n\n'
        "from __future__ import annotations\n\n"
        "from dataclasses import dataclass\n"
        "from typing import Any\n\n"
        "from app.config import get_settings\n"
        "from app.workflow.prompt_assembly import PromptAssembly\n"
        "from app.workflow.prompt_fingerprint import fingerprint_text\n\n"
        + bundle_cls
        + bodies(PROMPT_FUNCS),
        encoding="utf-8",
    )
    print("wrote prompt_bundle.py")

    spans: list[tuple[int, int]] = []
    spans.append((dec_start, bundle_node.end_lineno))
    spans.append((core_s, core_e))
    for n in ONTOLOGY_FUNCS + SEED_FUNCS + PROMPT_FUNCS:
        spans.append(funcs[n])
    spans.sort(key=lambda x: x[0], reverse=True)

    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    # Remove dataclass import if only used by bundle? may still be used - keep

    inject_anchor = "from app.workflow.orchestrator.workflow_progress import (\n"
    # find full workflow_progress import block end
    m = re.search(
        r"from app\.workflow\.orchestrator\.workflow_progress import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        raise SystemExit("workflow_progress import block not found")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.ontology_intelligence import (\n"
        "    CORE_RELATIONSHIP_TYPES,\n"
        "    _action_reply_line,\n"
        "    _available_action_items,\n"
        "    _build_action_boundary_reply,\n"
        "    _build_evidence_cluster_value_reply,\n"
        "    _build_official_website_gap_reply,\n"
        "    _build_ontology_intelligence_explanation_reply,\n"
        "    _build_relationship_risk_reply,\n"
        "    _build_source_substitution_reply,\n"
        "    _build_supporting_relationships_reply,\n"
        "    _evidence_cluster_reply_line,\n"
        "    _evidence_cluster_sort_key,\n"
        "    _format_relationships_for_reply,\n"
        "    _format_source_domains_for_reply,\n"
        "    _is_ontology_intelligence_explanation_request,\n"
        "    _ontology_intelligence_question_kind,\n"
        "    _ontology_object_total,\n"
        "    _sorted_evidence_clusters,\n"
        "    _sorted_source_domains,\n"
        "    _source_domain_reply_line,\n"
        "    _with_intelligence_reply_closure,\n"
        ")\n"
        "from app.workflow.orchestrator.seed_surface import (\n"
        "    _build_panorama_step_intro,\n"
        "    _extract_site_confidence_root_url,\n"
        "    _has_persona_prerequisites,\n"
        "    _infer_brand_seed_candidate,\n"
        "    _is_site_confidence_request,\n"
        "    _looks_like_keyword_list,\n"
        "    _normalize_tool_topic_keywords,\n"
        "    _resolve_brand_name_for_dependency_rebuild,\n"
        ")\n"
        "from app.workflow.orchestrator.prompt_bundle import (\n"
        "    OrchestratorPromptBundle,\n"
        "    _build_orchestrator_prompt_bundle_from_assembly,\n"
        "    _runtime_reminder_message_enabled,\n"
        "    _wrap_runtime_reminder_message,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)

    # If dataclass only for OrchestratorPromptBundle, leave import (other uses?)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
