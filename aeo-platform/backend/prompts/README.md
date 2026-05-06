# Backend Prompt Inventory

This directory no longer represents all runtime prompts.

## Runtime Prompt

- `brand_competition_agent.md`
  - Used by A1 brand competition paths through
    `load_prompt_template("brand_competition_agent")`.

## Legacy Reference

- `general_react_agent.md`
  - Kept only as a historical A0 design baseline.
  - Runtime orchestrator prompt is assembled in `app/workflow/orchestrator_node.py`,
    `app/workflow/prompt_assembly.py`, and
    `app/workflow/orchestrator_context_packets.py`.

## Removed Legacy Prompts

These old prompt files were removed because runtime code no longer loaded them:

- `data_analytics_agent.md`
- `fetch_agent.md`
- `marketing_persona_agent.md`
- `question_simulation_agent.md`
- `question_templates.yaml`

Current executor prompts and rules live next to the active executor code. See
`docs/architecture-agent-workflow-skill-vocabulary-2026-05-06.md` for the current
Agent / Workflow / Skill terminology.
