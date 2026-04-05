# Claude Harness Phase 7 / 7.5 QA + Code Review（2026-04-04）

## Scope

本轮覆盖：

1. Phase 7 / Step 2
   - `RecentEvidencePacket`
2. Phase 7 / Step 3
   - `PendingDecisionPacket`
   - `ActiveSkillPacket`
3. Phase 7.5
   - prompt disclosure refusal policy
   - injection-aware evidence rendering
   - untrusted external content tagging

不包含：

1. AIO runtime / takeover / relay
2. A4 blocker taxonomy 重构
3. 全量上传文件扫描

## QA Evidence

执行结果：

1. `python -m py_compile aeo-platform/backend/app/workflow/orchestrator_instruction_defense.py aeo-platform/backend/app/workflow/orchestrator_context_packets.py aeo-platform/backend/app/workflow/orchestrator_node.py aeo-platform/backend/tests/test_harness_refactor_foundations.py`
   - 结果：通过
2. 复用 `D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local` 运行：
   - `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
   - 结果：`21 passed`
3. 对本轮变更文件执行问号污染扫描
   - 结果：未发现编码损坏

## Code Review Findings

本轮自审未发现阻塞级问题。

已在提交前修正的非阻塞问题：

1. `pending_confirmation.options` 不保证一定是 dict
2. `knowledge_lookup_result.metadata` 不保证一定是 dict

对应修复已补入 `orchestrator_context_packets.py`。

## Boundary Check

本轮确认未发生以下边界回退：

1. `Skill` 没有重新退化成 prompt patch
2. `Tool` 没有重新退化成粗粒度能力名
3. `Harness` 没有只剩状态记录
4. 安全防守没有散落成单条 prompt 文案，而是进入独立模块与 packet/render 流程

## Residual Risks

1. `RecentEvidencePacket` 目前只覆盖最近一次 `knowledge_*` 结果，尚未覆盖上传文件或 AIO/browser 证据来源。
2. prompt disclosure / injection 检测仍是最小规则集，不是完整分类器。
3. `ActiveSkillPacket` 当前仍依赖兼容期 skill state 字段，待后续 skill 双轨收口后可进一步简化。

## Conclusion

本轮可以作为 `Phase 7 Step 2 / Step 3 + Phase 7.5` 的最小闭环放行。
