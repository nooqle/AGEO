# Claude Harness Refactor Phase 0-2 QA / Code Review

## Scope

- Worktree: `D:\AGEO-worktrees\validation-retro-harness`
- Branch: `codex/validation-retro-harness`
- Covered phases:
  - Phase 0: 分层冻结与工作树预备
  - Phase 1: Orchestrator Prompt 收缩与 Section 化
  - Phase 2: Skill Contract 正式化（A5/A7 试点）

## Goals Checked

1. A0 prompt 是否完成 section 化，而不是继续只靠单块长 prompt
2. public skill 是否从弱 prompt patch 升级为结构化合同
3. A5/A7 是否开始显式校验 precondition / artifact writeback
4. skill context 注入是否从字符串 append 升级为 section 组合

## QA Evidence

### Static Validation

- `python -m py_compile` passed:
  - `aeo-platform/backend/app/workflow/orchestrator_node.py`
  - `aeo-platform/backend/app/workflow/nodes_a7.py`
  - `aeo-platform/backend/tests/test_harness_refactor_foundations.py`

### Automated Tests

- Command:
  - `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
- Result:
  - `7 passed`

### Scenarios Covered

1. Main path:
   - Orchestrator prompt assembly exposes structured sections and preserves uploaded question-list routing hint
2. Main path:
   - A7 成功路径会记录 `last_skill_result` 和 `last_validation_result`
3. Failure / recovery path:
   - A5 在缺少 `fetch_results_required` 时被 precondition gate 拦截
4. Failure / recovery path:
   - A7 在 artifact writeback 缺少 message id 时返回 error，而不是假装完成

### Runtime Smoke

- Reused shared env from:
  - `D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local`
- Started current branch backend on:
  - `http://localhost:8001`
- Verified:
  - `POST /api/v1/sessions` returned `200`

## Code Review Result

### Blocking Findings

- None in the current Phase 0-2 diff after patching compatibility gaps.

### Fixed During Review

1. Restored the uploaded table auto-routing reminder:
   - `user_decisions.table_import_confirmed=true` + `confirmed_table_kind=question_list`
   - must immediately route to `question_simulation(mode="uploaded_list")`
2. Restored stricter A4 failure wording:
   - `answer_fetch` failure must not regenerate questions
   - must ask user to choose retry / mode retry / partial-platform retry
3. Normalized A7 error updates:
   - now writes `current_step="A7"` and `execution_status="error"` for failure paths
4. Synced `general_react_agent.md` to the new sectioned A0 boundary:
   - file now acts as policy/routing baseline, not legacy giant pipeline doc

## Residual Risks

1. A0 sectioned prompt is intentionally shorter than the historical monolith.
   - High-probability paths are covered by unit tests.
   - Long-tail conversational routing still needs later real E2E validation with a running backend + live LLM path.
2. `test_routing_matrix.py` initially failed because no backend was listening on `8001`.
   - This was an environment issue, not a code regression from this phase.
3. Shared-env backend startup exposed an unrelated scheduler error:
   - `app.services.scheduler` raised `UnboundLocalError: monitoring_service`
   - This was observed in runtime logs and should be treated as a separate backlog item.

## Gate Decision

- Phase 0: pass
- Phase 1: pass
- Phase 2: pass

Allowed next step:
- enter Phase 3 (`Tool` 边界收缩与 `A3` 语义拆分)
