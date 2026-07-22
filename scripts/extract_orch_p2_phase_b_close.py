"""Close Phase B: prompt assembly builder + tool gate block command."""

from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "aeo-platform/backend/app/workflow/orchestrator_node.py"
PKG = ROOT / "aeo-platform/backend/app/workflow/orchestrator"

FUNCS = [
    "build_orchestrator_prompt_assembly",
    "build_orchestrator_prompt_bundle",
    "build_orchestrator_system_prompt",
    "_build_tool_gate_block_command",
    "_build_ontology_action_plan",
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
    for n in FUNCS:
        if n not in funcs:
            raise SystemExit(f"missing {n}")

    def body(name: str) -> str:
        s, e = funcs[name]
        chunk = _chunk(lines, s, e)
        chunk = chunk.replace("state: AgentState", "state: Mapping[str, Any]")
        return chunk.rstrip() + "\n\n"

    assembly = (
        '"""Orchestrator prompt assembly construction (Phase B close)."""\n\n'
        "from __future__ import annotations\n\n"
        "from textwrap import dedent\n"
        "from typing import Any, Mapping\n\n"
        "from app.workflow.orchestrator_context_packets import (\n"
        "    build_orchestrator_context_packets,\n"
        "    render_active_skill_packet,\n"
        "    render_dashboard_context_packet,\n"
        "    render_entity_context_packet,\n"
        "    render_history_availability_packet,\n"
        "    render_ontology_action_plan_packet,\n"
        "    render_ontology_world_packet,\n"
        "    render_pending_decision_packet,\n"
        "    render_session_status_packet,\n"
        ")\n"
        "from app.workflow.orchestrator_instruction_defense import (\n"
        "    INSTRUCTION_SECURITY_POLICY,\n"
        "    build_instruction_defense_context,\n"
        "    render_instruction_defense_reminder,\n"
        ")\n"
        "from app.workflow.prompt_assembly import PromptAssembly, PromptSection\n"
        "from app.workflow.orchestrator.knowledge_fallback import (\n"
        "    _build_knowledge_planning_hint,\n"
        ")\n"
        "from app.workflow.orchestrator.misc_pure import _build_static_public_skill_index\n"
        "from app.workflow.orchestrator.prompt_bundle import (\n"
        "    OrchestratorPromptBundle,\n"
        "    _build_orchestrator_prompt_bundle_from_assembly,\n"
        ")\n"
        "from app.workflow.orchestrator.prompt_context import (\n"
        "    _build_context_summary,\n"
        "    _build_contextual_tool_surface_note,\n"
        "    _build_public_skill_index,\n"
        ")\n"
        "from app.workflow.orchestrator.prompt_evidence import (\n"
        "    _render_recent_evidence_for_prompt,\n"
        "    _should_render_history_availability,\n"
        "    _should_render_instruction_defense,\n"
        ")\n"
        "from app.workflow.orchestrator.session_tool_surface import (\n"
        "    _get_contextual_hidden_tool_names,\n"
        ")\n"
        "from app.workflow.orchestrator.text_normalize import _compact_text\n\n"
        + body("build_orchestrator_prompt_assembly")
        + body("build_orchestrator_prompt_bundle")
        + body("build_orchestrator_system_prompt")
    )
    (PKG / "prompt_assembly_builder.py").write_text(assembly, encoding="utf-8")
    print("wrote prompt_assembly_builder.py")

    gate_cmd = (
        '"""Tool availability block Command builder (Phase B close)."""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from typing import Any, Mapping\n\n"
        "from langgraph.types import Command\n\n"
        "from app.services.tool_capability_matrix import ToolAvailabilityConstraint\n\n"
        + body("_build_tool_gate_block_command")
    )
    (PKG / "tool_gate_command.py").write_text(gate_cmd, encoding="utf-8")
    print("wrote tool_gate_command.py")

    plan = (
        '"""Ontology action plan thin helper (Phase B close)."""\n\n'
        "from __future__ import annotations\n\n"
        "from typing import Any, Mapping\n\n"
        "from app.services.brand_ontology_action_planner_service import (\n"
        "    BrandOntologyActionPlannerService,\n"
        ")\n\n"
        + body("_build_ontology_action_plan")
    )
    (PKG / "ontology_action_plan.py").write_text(plan, encoding="utf-8")
    print("wrote ontology_action_plan.py")

    spans = [funcs[n] for n in FUNCS]
    spans.sort(key=lambda x: x[0], reverse=True)
    new_lines = lines[:]
    for start, end in spans:
        del new_lines[start - 1 : end]

    join_text = "".join(new_lines)
    m = re.search(
        r"from app\.workflow\.orchestrator\.orchestrator_messages import \(\n(?:.*\n)*?\)\n",
        join_text,
    )
    if not m:
        # fallback: after command_helpers
        m = re.search(
            r"from app\.workflow\.orchestrator\.command_helpers import \(\n(?:.*\n)*?\)\n",
            join_text,
        )
    if not m:
        raise SystemExit("import anchor missing")
    block = m.group(0)
    extra = (
        block
        + "from app.workflow.orchestrator.prompt_assembly_builder import (\n"
        "    build_orchestrator_prompt_assembly,\n"
        "    build_orchestrator_prompt_bundle,\n"
        "    build_orchestrator_system_prompt,\n"
        ")\n"
        "from app.workflow.orchestrator.tool_gate_command import (\n"
        "    _build_tool_gate_block_command,\n"
        ")\n"
        "from app.workflow.orchestrator.ontology_action_plan import (\n"
        "    _build_ontology_action_plan,\n"
        ")\n"
    )
    join_text = join_text.replace(block, extra, 1)
    join_text = re.sub(r"\n{4,}", "\n\n\n", join_text)
    SRC.write_text(join_text, encoding="utf-8")
    print(f"orchestrator_node lines -> {len(join_text.splitlines())}")


if __name__ == "__main__":
    main()
