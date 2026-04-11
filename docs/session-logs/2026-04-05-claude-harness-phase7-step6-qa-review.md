# 2026-04-05 Claude Harness Phase 7 Step 6 QA / Code Review

## Scope

- `uploaded_input` evidence packet
- `current session evidence relevance/ranking`
- orchestrator model-visible 中文化
- orchestrator thinking 英文兜底防守
- `post_analysis_skill` 合同与 follow-up tool 命名一致性修正

## Findings First Review

### P1

1. `post_analysis_skill` 合同里 `snapshot_comparison` 与运行时 `compare_snapshots` 命名不一致，已修正到合同层。

### P2

1. orchestrator 的 model-visible section title 和 evidence render 之前仍有英文标签，已统一收回中文。
2. orchestrator thinking stream 之前会原样透出英文思考块，已增加最小英文兜底防守。

## QA

### 自动化验证

1. `python -m py_compile ...`
   - 结果：通过
2. `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
   - 结果：`28 passed`

### 本轮重点覆盖

1. `uploaded_input` 证据来源纳入 `RecentEvidencePacket`
2. `current session evidence` relevance/ranking
3. 中文 section title / 中文 render
4. 英文 thinking guard
5. `post_analysis_skill` 合同命名一致性

## Code Review Conclusion

本轮改动可放行。

原因：

1. 新增的 evidence 来源仍然走统一 provenance 协议，没有绕开 `instruction_authority=false`
2. relevance/ranking 只做轻量排序，没有把 routing 所有权重新塞回 prompt
3. `selective_refetch` 继续保留在 `post_analysis_skill` 下是合理的：它属于已有结果基础上的 follow-up capability，不是独立 public skill
4. `post_analysis_skill` 的真实问题不是能力归位，而是合同命名不一致；该问题已修正

## Residual Risks

1. 当前 relevance/ranking 还是关键词启发式，不是 semantic ranking
2. `uploaded_input` 目前只覆盖表格/问题列表/链接清单，还没覆盖更多上传输入类型
3. thinking guard 采用最小英文占位策略，后续如果需要更细粒度中文化，可以再收紧
