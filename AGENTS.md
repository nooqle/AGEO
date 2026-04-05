# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project Overview

Specta AI - An intelligent brand analysis platform using multi-agent AI systems to analyze brand visibility across AI search engines (DeepSeek, Kimi, GPT, etc.).

## Development Commands

### Initial Setup

**First-time setup** (required before running the backend):

```bash
# Backend dependencies
cd aeo-platform/backend
pip install -r requirements.txt

# Install browser runtime (required for Browser Agent)
# Preferred in this repo (Patchright):
python -m patchright install chromium
```

**Frontend dependencies**:
```bash
cd frontend
npm install
```

### Unified Development (Recommended)
```bash
./scripts/dev.sh  # Starts both backend (8000) and frontend (3000)
```

### Backend (from aeo-platform/backend/)
```bash
# Development server
uvicorn app.main:socket_app --reload --port 8000

# Testing
pytest
pytest tests/test_agents/  # Run specific test directory
pytest -k "test_name"      # Run specific test

# Code quality
black .
isort .
ruff check .
mypy .

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "message"
```

### Frontend (from frontend/)
```bash
npm run dev      # Development server (port 3000)
npm run build    # Production build
npm run lint     # ESLint
```

## Architecture

### Multi-Agent System
The platform uses a hierarchical agent architecture with TPAOR execution framework (Thought→Plan→Action→Observation→Response):

- General ReAct Agent (A0): Main controller that coordinates all specialized agents
- Brand Competition Agent (A1): Brand profile and competitor analysis
- Marketing Persona Agent (A2): User persona and scenario generation
- Question Simulation Agent (A3): Generates simulated user questions
- Answer Fetch Agent (A4): Retrieves answers from public AI models
- Data Analytics Agent (A5): Metrics calculation and report generation
- Browser Agent (A6): Web automation via Playwright/Patchright

Agent prompts are in `aeo-platform/backend/prompts/`.

### Backend Structure (FastAPI)
- `app/agents/` - Agent implementations
- `app/api/v1/` - REST API routes (sessions, messages, outputs)
- `app/core/` - Core utilities (database, WebSocket, LLM wrappers)
- `app/models/` - SQLAlchemy models
- `app/schemas/` - Pydantic schemas
- `app/services/` - Business logic layer

### Frontend Structure (Next.js App Router)
- `src/app/chat/[sessionId]/` - Main chat interface
- `src/components/canvas/` - Canvas panel for reports/charts
- `src/stores/` - Zustand state management
- `src/services/` - API and WebSocket clients

### Communication
- REST API for CRUD operations
- WebSocket for real-time agent execution progress and user confirmations

## Tech Stack

**Backend**: Python 3.10+, FastAPI, AgentScope, SQLAlchemy 2.0 (async), PostgreSQL, Alembic, MiniMax M2.1 LLM

**Frontend**: Next.js, React, TypeScript, Zustand, Tailwind CSS, Radix UI, Recharts, socket.io-client

## Code Style

**Python**: PEP 8, Black (line-length=88), isort, ruff, mypy strict

**TypeScript**: ESLint, strict mode, functional components with hooks

**Naming**: snake_case (Python), camelCase (TypeScript), PascalCase (classes/components), kebab-case (API routes)

**Commits**: `<type>(<scope>): <subject>`

## Configuration

Backend env: `aeo-platform/backend/.env.local` (copy from `.env.local.example`)
Frontend env: `frontend/.env.local` (copy from `.env.local.example`)

Required API keys: MiniMax API key, optionally DashScope for backup LLM.

## Working Rules (Important)

- Use Chinese when communicating with the user.
- For code fixes, first analyze root cause and affected scope, then explain plan/impact to user before large refactors.
- Do not make broad unrelated changes in one go.
- Prefer minimal, focused edits and verify with relevant lint/tests.

## Agent-First Architecture Principle (Important)

- Treat Specta AI as an `Agent + Skills + Context + Memory + Artifact/Version` system first, not as a collection of one-off hardcoded feature branches.
- For new capabilities, prefer this order:
  1. reuse an existing skill / node contract
  2. extend an existing skill / node contract
  3. add a new coarse-grained skill
  4. only then add scenario-specific hardcoded flow
- Let orchestrator own intent understanding, workflow routing, user confirmation strategy, and step-to-step progression.
- Let code own deterministic mechanics: file parsing, schema validation, normalization, persistence, idempotency, security checks, and artifact/version writes.
- If new input changes a step's official result, update that step's latest artifact/version first, then resume the workflow from that step's downstream logic.
- Do not bypass context/memory/artifact systems with temporary side channels for convenience.
- Avoid scattering business decisions across multiple files with ad-hoc `if/else` branches when the decision should live in orchestrator or a skill contract.
- Default design question for any new feature:
  - should this be a new hardcoded feature, or should it be an Agent capability extension?
- For the full rationale and examples, see:
  - `docs/architecture-agent-first-extension-principles-2026-03-25.md`

## Workspace / Worktree Protocol (Important)

- Treat `D:\AGEO-main` as the only stable `main` baseline directory.
- Do **not** develop new features directly inside `D:\AGEO-main`; use it only to inspect `main`, update `main`, and create new feature worktrees.
- Treat `D:\AGEO` as a legacy worktree. Do **not** start new tasks or new Codex implementation work from this directory.
- Before starting implementation work in this repo, always check:
  1. current directory
  2. current branch
  3. whether the task belongs to an existing feature worktree or requires a new one
- For every new task, create a dedicated feature worktree from `D:\AGEO-main` with a `codex/` branch name, for example:
  - `git worktree add D:\AGEO-worktrees\<task-name> -b codex/<task-name> origin/main`
- Use `D:\AGEO-worktrees\<task-name>` as the actual development directory for that task.
- If the user asks to continue an existing task, prefer its existing feature worktree instead of creating another one.
- Before coding in any AGEO worktree, verify:
  - `git branch --show-current`
  - `git status --short --branch`
- If the current directory is `D:\AGEO`, stop and switch to either:
  - `D:\AGEO-main` for baseline inspection, or
  - the correct feature worktree for implementation
- Do not commit feature work directly on `main` unless the user explicitly requests a main-branch hotfix workflow.

## Runtime Reuse Protocol (Important)

- For AGEO branch startup, dev verification, and E2E, prefer reusing the already proven runtime environment from `D:\AGEO\.codex-main-merge` first, then `D:\AGEO`, before creating a fresh local setup.
- If the current worktree does not have `aeo-platform/backend/.env.local`, first inspect `D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local`; only if needed, fall back to `D:\AGEO\aeo-platform\backend\.env.local`.
- Preferred order:
  1. reuse an already running AGEO service from `D:\AGEO\.codex-main-merge` if it matches the task
  2. reuse `.codex-main-merge` shared env and run the current worktree on alternate ports
  3. if `.codex-main-merge` is unavailable, reuse `D:\AGEO` shared env
  4. only then create a fully separate branch runtime
- When real GLM5 credentials are available in the shared AGEO env, do not replace real runtime/E2E with a fake LLM path by default.


## Encoding Safety Rule (Important)

This repo has had repeated real source corruption on Windows where Chinese text was written into files as literal `?` / `???`, not just displayed incorrectly.

Root cause identified:
- Writing Chinese source text through PowerShell inline scripts / pipelines / here-strings is unsafe in this environment.
- A successful `tsc` / `build` does **not** prove text content is intact.
- The failure mode is source-file corruption, not only console rendering issues.

Mandatory rules for future edits:
- Do **not** use PowerShell inline text replacement to write Chinese source code.
- Prefer `apply_patch` for normal edits.
- If scripting is necessary, use Python with explicit UTF-8 file I/O.
- Prefer ASCII-only script bodies plus `\u` escapes when generating Chinese text programmatically on Windows.
- After any edit involving Chinese UI copy or prompts, always verify all three:
  1. Re-open the edited file and inspect the saved contents
  2. Run a targeted `rg -F "???"` scan on affected files
  3. Run relevant `tsc` / `build` / tests

Scope guidance:
- Treat any newly introduced `?` / `???` in UI strings as a blocking regression.
- When fixing encoding corruption, first repair the source bytes, then validate rendering.


## Commit Scope Rule (User Preference)

When committing by default, do **not** include the following unless the user explicitly asks:

- test scripts
- screenshots/images
- temporary/debug files

Only stage and commit files directly related to the requested functional/code change.

## Multi-Agent Collaboration Note

Do not use Agent Teams / SendMessage workflow in this repo (Windows communication issue). If parallelization is needed, keep outputs explicit and merge results clearly.

## Daily Retrospective Task (Codex)

Run a daily scheduled retrospective in Chinese and write to `docs/daily-retro/YYYY-MM-DD.md`.

Required sections (must include all):
- `Today's Work`: what was done today
- `Findings`: what was discovered today (root causes, risks, insights)
- `Learned / New Skills`: what new skills, methods, or patterns were gained
- `Understanding of User`: updated understanding of user expectations and working style

Preferred front-loaded sections (include whenever relevant, and place them before `Today's Work`):
- `Validation Closure`: what was actually verified, what was written back, and what remains open
- `Failure Samples`: explicit failure patterns with signal, why they survived, kill step, and writeback
- `Collaboration Evolution`: how the user/Codex collaboration changed, what became more explicit, and what still depends too much on one side

Guidelines:
- Follow the style and depth of existing files in `docs/daily-retro/`.
- Be concrete; include evidence from actual work done in the workspace.
- If there is little progress on a given day, explicitly state what blocked progress and why.
- Add `Tomorrow's Priority` with 1-3 actionable items.
- Do not let the retro collapse into a task list; validation quality, failure visibility, and protocol writeback are more important than raw activity volume.
- Prefer using the global skill [$validation-closure-retro](/C:/Users/Administrator/.codex/skills/validation-closure-retro/SKILL.md) when writing or rewriting a retro, and use [$collaboration-harness](/C:/Users/Administrator/.codex/skills/collaboration-harness/SKILL.md) when adjusting the collaboration protocol itself.


## Local Subagent Definitions

Codex can read and use role definitions under `D:\AGEO\.claude\agents\` (e.g. `architect.md`, `developer.md`, `frontend-developer.md`, `pm.md`, `qa.md`, `ux.md`) as execution guidance.

Constraint:
- These files are used as role/playbook references in current Codex workflow.
- Do not directly use Claude Agent Teams / SendMessage runtime mechanism.

## Pre-Compact Archive Protocol

Before automatic context compaction, create a concise archive note under `docs/session-logs/` to preserve key history.

File naming:
- `docs/session-logs/YYYY-MM-DD-<topic>-compact-archive.md`

Minimum required content:
- `Context Scope`: what period/task this archive covers
- `User Goal & Constraints`: target, hard constraints, and non-goals
- `Key Decisions`: major technical/product decisions and why
- `Actions Taken`: important commands/edits/validations already done
- `Open Risks / Unknowns`: what is still uncertain
- `Next Step`: exact next actionable step after compaction

Rules:
- Archive key facts, not full transcript dumps.
- Prefer evidence references (file paths, command outcomes, commit ids).
- Keep it concise and searchable; avoid noise.
