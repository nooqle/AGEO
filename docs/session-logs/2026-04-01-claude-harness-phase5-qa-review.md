# Phase 5 QA + Code Review（2026-04-01）

## Context Scope

- 覆盖范围：`Phase 5: A4/AIO 链路接入新 Harness`
- 当前分支实际范围：先接入 `A4` 既有 code path；完整 AIO runtime 不在本分支内

## Findings

1. 无阻塞级问题。
2. 当前分支里可以落地的部分已经完成：
   - selective refetch merge validation
   - A4 completion policy decision
   - A4 异常路径的 harness decision writeback
3. 完整 `AIO takeover / resume gate / relay session state machine` 仍需在 AIO 实现分支继续接入，不能在本分支伪造完成。

## QA Evidence

1. 自动化测试
   - `pytest tests/test_harness_refactor_foundations.py -q`
   - 相关覆盖：
     - `test_a4_merge_validation_and_policy_decision`

2. 静态校验
   - `python -m py_compile app/workflow/nodes_a4.py app/workflow/harness_validation.py`

3. 场景结论
   - 主路径：selective refetch merge 成功时，A4 completion decision 可区分 `complete_step / degraded_continue`
   - 失败路径：merge 未保留未选平台结果时，validation gate 会失败
   - 恢复路径：A4 顶层异常会记录 `retry_step`，不再静默吞掉

## Code Review Conclusion

1. A4 已开始消费 harness policy，而不是只靠 scattered branch logic。
2. 这一阶段没有把 A4 误改成 policy owner，平台异常口径开始向 harness 靠拢。
3. 需要明确标注范围：本次不是完整 AIO 改造，只是把当前分支可见的 A4 主路径接上统一 contract。

## Residual Risks

1. AIO runtime 的 `takeover / resume / relay` 仍缺统一状态机接入。
2. 当前 A4 harness integration 主要覆盖 selective refetch merge 和 completion policy，尚未覆盖所有 browser blocker taxonomy。
