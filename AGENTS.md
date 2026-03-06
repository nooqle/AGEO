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

Guidelines:
- Follow the style and depth of existing files in `docs/daily-retro/`.
- Be concrete; include evidence from actual work done in the workspace.
- If there is little progress on a given day, explicitly state what blocked progress and why.
- Add `Tomorrow's Priority` with 1-3 actionable items.


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
