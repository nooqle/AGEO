# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Specta AI - An intelligent brand analysis platform using multi-agent AI systems to analyze brand visibility across AI search engines (DeepSeek, Kimi, GPT, etc.).

## Development Commands

### Initial Setup

**First-time setup** (required before running the backend):

```bash
# Backend dependencies
cd aeo-platform/backend
pip install -r requirements.txt

# Install Playwright browser (required for Browser Agent)
# Windows:
scripts\install_playwright.bat

# Linux/macOS:
chmod +x scripts/install_playwright.sh
./scripts/install_playwright.sh

# Or manually:
python -m playwright install chromium
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
pytest -k "test_name"       # Run specific test

# Code quality
black .                     # Format code
isort .                     # Sort imports
ruff check .                # Lint
mypy .                      # Type check

# Database migrations
alembic upgrade head                           # Apply migrations
alembic revision --autogenerate -m "message"   # Create migration
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

- **General ReAct Agent (A0)**: Main controller that coordinates all specialized agents
- **Brand Competition Agent (A1)**: Brand profile and competitor analysis
- **Marketing Persona Agent (A2)**: User persona and scenario generation
- **Question Simulation Agent (A3)**: Generates simulated user questions
- **Answer Fetch Agent (A4)**: Retrieves answers from public AI models
- **Data Analytics Agent (A5)**: Metrics calculation and report generation
- **Browser Agent (A6)**: Web automation via Playwright

Agent prompts are in `aeo-platform/backend/prompts/`.

### Backend Structure (FastAPI)
- `app/agents/` - Agent implementations
- `app/api/v1/` - REST API routes (sessions, messages, outputs)
- `app/core/` - Core utilities (database, WebSocket, MiniMax LLM wrapper)
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

**Frontend**: Next.js 16, React 19, TypeScript, Zustand, Tailwind CSS, Radix UI, Recharts, socket.io-client

## Code Style

**Python**: PEP 8, Black (line-length=88), isort, ruff, mypy strict

**TypeScript**: ESLint, strict mode, functional components with hooks

**Naming**: snake_case (Python), camelCase (TypeScript), PascalCase (classes/components), kebab-case (API routes)

**Commits**: `<type>(<scope>): <subject>` (e.g., `feat(agents): implement BrandCompetition Agent`)

## Configuration

Backend env: `aeo-platform/backend/.env.local` (copy from `.env.local.example`)
Frontend env: `frontend/.env.local` (copy from `.env.local.example`)

Required API keys: MiniMax API key, optionally DashScope for backup LLM.

## 工作准则（重要）

**代码修改流程**：当发现问题需要修改代码时，必须遵循以下流程：

1. **分析问题根因**：深入分析问题的根本原因
2. **检查类似问题**：检查代码库中其他地方是否有类似问题
3. **汇报分析结果**：向用户说明：
   - 问题的根本原因
   - 其他受影响的位置
   - 建议的修改方案
   - 修改的影响范围
4. **等待用户确认**：在用户明确同意后才能进行代码修改
5. **执行修改**：按照确认的方案进行修改

**禁止行为**：
- 不要在未经用户确认的情况下直接修改代码
- 不要假设用户会同意修改

**语言要求**：
- 使用中文与用户沟通

## 多智能体协作规范

**禁止使用 Agent Teams / SendMessage**（Windows 通信 bug 未修复）

### 并行任务标准流程
1. 通过 Task 工具并行启动多个 Subagent
2. 每个 Subagent 完成后将结果写入 `.claude/outputs/{角色}_result.md`
3. 所有角色必须有 Write 权限（在 agent 定义中明确包含 Write 工具）
4. 全部完成后 Lead 读取所有文件汇总

### 输出文件格式
\`\`\`
### RESULT ###
（结果正文）
### END ###
\`\`\`