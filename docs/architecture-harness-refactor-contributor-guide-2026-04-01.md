# AGEO Harness Refactor Contributor Guide（2026-04-01）

> 状态：Active
> 适用分支：`codex/validation-retro-harness`

## 背景

本轮改造参考 Claude Code 的分层方式，但不照搬其文案。目标是把 AGEO 从“越来越大的 orchestrator prompt”收敛成一个更清晰的 `Agent + Skill + Tool + Harness` 系统。

## 五层边界

1. `Orchestrator`
   - 负责意图识别、前置条件判断、选 skill、选 executor、决定继续/暂停/追问。
   - 不负责承载完整 pipeline 细节，也不替代 executor。

2. `Agent / Executor`
   - 负责专项执行。
   - 当前试点：`A5`、`A7` 仍然是 executor；`A4` 继续是执行控制节点。

3. `Skill`
   - 负责 public capability contract。
   - 当前试点：`analysis_report_skill`、`confidence_signal_skill`、`post_analysis_skill`。

4. `Tool`
   - 负责原子动作能力。
   - 通过 `ToolCapabilityMatrix` 明确调用者、风险等级、写回目标、确认策略。

5. `Harness`
   - 负责 prompt assembly、validation gate、harness decision、artifact writeback validation、resume/recovery 语义。
   - 不再只做 state 记录层。

## 已落地的核心接口

1. `PromptAssembly`
   - 路径：`aeo-platform/backend/app/workflow/prompt_assembly.py`
   - 用于 section 化 orchestrator prompt。

2. `SkillContract`
   - 路径：`aeo-platform/backend/app/services/skill_contracts.py`
   - 用于描述 public skill 的正式合同。

3. `ToolCapabilityMatrix`
   - 路径：`aeo-platform/backend/app/services/tool_capability_matrix.py`
   - 用于统一 tool capability 元数据与 caller 校验。

4. `HarnessDecision / ValidationGateResult`
   - 路径：`aeo-platform/backend/app/workflow/harness_validation.py`
   - 用于记录 pre/postcondition、artifact writeback、A4 completion policy 等治理结果。

## 当前 rollout 状态

1. `Phase 1`
   - Orchestrator prompt 已改成 sectioned assembly。

2. `Phase 2`
   - `A5/A7` 已接入 `SkillContract + precondition/postcondition/artifact writeback gate`。

3. `Phase 3`
   - `ToolCapabilityMatrix` 已落地。
   - A3 的 question generation 已下沉到内部 tool。

4. `Phase 4`
   - A5/A7 的 harness gate 与 decision chain 已落地。

5. `Phase 5`
   - 当前分支可见的 A4 code path 已接入 selective refetch merge validation 和 completion policy。
   - 完整 AIO runtime 仍待后续分支继续接入。

6. `Phase 6`
   - capability caller 校验已接入 orchestrator / post-analysis executor。
   - A3 节点内已删除遗留 prompt helper，避免重新回流到 node 内拼 prompt。

## 新增能力时的接入规则

1. 先判断它属于哪一层：
   - 用户意图能力：`Skill`
   - 原子动作：`Tool`
   - 局部执行：`Executor`
   - 统一治理：`Harness`

2. 不要让以下边界回退：
   - `Skill` 重新变成 prompt patch
   - `Tool` 重新变成业务能力名
   - `Harness` 重新只剩状态记录
   - `Orchestrator` 重新长回总说明书

3. 新增 public skill 时，至少补齐：
   - `intent_scope`
   - `preconditions`
   - `allowed_tools`
   - `expected_outputs`
   - `artifact_writeback_rules`
   - `postconditions`

4. 新增 tool 时，至少补齐：
   - `capability_type`
   - `allowed_callers`
   - `side_effect_level`
   - `artifact_writeback_target`
   - `confirmation_policy`

## QA / Review 基线

每个后续 PR 至少要回答这四个问题：

1. 这次改动属于哪一层？
2. 新接口或 contract 有什么变化？
3. 自动化测试和失败路径证据是什么？
4. 是否造成边界回退？
