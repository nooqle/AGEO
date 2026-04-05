# Phase 6 QA + Code Review（2026-04-01）

## Context Scope

- 覆盖范围：`Phase 6: 推广、清理与稳定化`
- 当前落地点：
  - capability caller enforcement
  - A3 遗留 helper 清理
  - repo-level contributor doc
  - PR template

## Findings

1. 已修复一个真实回归点：`post_analysis_executor_node` 之前默认要求 `session_id` 必填，新增 capability 校验后暴露出该隐式假设；现已改为兼容无 `session_id` 的单测调用。
2. 已修复一个实现错误：`build_harness_decision_update` 的调用缺少 `state` 参数，导致 follow-up capability block 路径不能正确写回 harness decision。
3. 当前无新的阻塞级问题。

## QA Evidence

1. 自动化测试
   - `pytest tests/test_harness_refactor_foundations.py -q`
   - 结果：`14 passed`
   - Phase 6 新增覆盖：
     - `test_tool_capability_matrix_rejects_disallowed_caller`
     - `test_post_analysis_executor_blocks_invalid_capability`

2. 静态校验
   - `python -m py_compile app/services/tool_capability_matrix.py app/workflow/orchestrator_node.py app/workflow/nodes_followup.py app/workflow/nodes_a3.py tests/test_harness_refactor_foundations.py`

3. 场景结论
   - 主路径：`post_analysis_executor` 仍能依据 capability payload 正常路由到 selective refetch
   - 失败路径：不允许的 capability caller 会被运行时策略直接拦截
   - 稳定化：A3 节点内不再保留已迁移至 `question_generation` 的旧 prompt helper，避免语义回流

## Code Review Conclusion

1. `ToolCapabilityMatrix` 已从“说明性元数据”升级为“实际 enforcement”。
2. A3 的 prompt / 生成逻辑边界比改造前清晰，节点继续保留 stage 责任，纯生成逻辑留在内部 tool。
3. `Harness` 没有回退成单纯记录层，反而在 follow-up 路径新增了 capability policy block 的 writeback。

## Residual Risks

1. capability enforcement 目前主要接入 orchestrator 与 post-analysis executor，尚未覆盖所有内部 caller。
2. `LEGACY_SKILL_TOOL_ALIASES` 仍存在，用于兼容旧调用；后续需要在更大范围回归后再逐步收缩。
