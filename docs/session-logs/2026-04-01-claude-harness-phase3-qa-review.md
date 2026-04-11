# Claude Harness Refactor Phase 3 QA / Code Review

## Scope

- Worktree: `D:\AGEO-worktrees\validation-retro-harness`
- Branch: `codex/validation-retro-harness`
- Covered phase:
  - Phase 3: Tool 边界收缩与 A3 语义拆分

## Goals Checked

1. 是否新增统一 `ToolCapabilityMatrix`
2. follow-up 路由是否开始消费 capability payload，而不只靠 legacy alias 文本
3. A3 是否把纯 question-generation 逻辑下沉到 internal tool
4. 旧的 `QuestionSimulationTool` async 兼容层是否仍然可用

## QA Evidence

### Static Validation

- `python -m py_compile` passed:
  - `aeo-platform/backend/app/services/tool_capability_matrix.py`
  - `aeo-platform/backend/app/tools/question_generation.py`
  - `aeo-platform/backend/app/workflow/orchestrator_node.py`
  - `aeo-platform/backend/app/workflow/nodes_followup.py`
  - `aeo-platform/backend/app/workflow/nodes_a3.py`
  - `aeo-platform/backend/app/tools/a3_question_simulation.py`
  - `aeo-platform/backend/tests/test_harness_refactor_foundations.py`

### Automated Tests

- Command:
  - `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
- Result:
  - `11 passed`

### Scenarios Covered

1. Main path:
   - capability matrix 区分 `question_simulation(workflow_stage)` 与 `question_generation(generation_tool)`
2. Main path:
   - `QuestionGenerationTool` 能为 persona / baseline 两类模式生成稳定 prompt contract
3. Main path:
   - `post_analysis_executor_node` 在没有 `analysis_mode` 时，会优先读取 `current_tool_capability`
4. Compatibility:
   - legacy `QuestionSimulationTool` 仍然保持 async 调用契约

## Code Review Result

### Blocking Findings

- None after fixing compatibility regression.

### Fixed During Review

1. Restored async compatibility for `QuestionSimulationTool`
   - Initial refactor accidentally replaced an async wrapper with a direct sync alias
   - This would have broken any legacy caller still doing `await QuestionSimulationTool(...)`
   - Fixed by restoring an explicit async compatibility wrapper in:
     - [a3_question_simulation.py](/D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/tools/a3_question_simulation.py)

## Residual Risks

1. A3 still retains some legacy local helper definitions in `nodes_a3.py`
   - Primary call path already switched to `QuestionGenerationTool`
   - Remaining dead/legacy helpers should be cleaned in later stabilization work
2. Capability matrix is currently consumed by orchestrator + follow-up routing
   - It is not yet globally enforced across all executors
   - Phase 4/5 should continue turning it from metadata into runtime policy input

## Gate Decision

- Phase 3: pass

Allowed next step:
- enter Phase 4 (`Harness` 治理层补强)
