# 2026-04-05 post_analysis_skill / answer_fetch 边界修正 QA / Code Review

## Scope

- `post_analysis_skill` 收缩为只读分析能力
- `answer_fetch` 收口为唯一采集入口
- 移除 `refetch/selective_refetch` 作为 public capability 的残留
- orchestrator 失败表达从“阻塞优先”收口到“方案优先”
- orchestrator 用户可见中文化补强

## Findings First Review

### P1

1. `post_analysis_skill` 与 `answer_fetch` 的边界此前确实混乱，导致“分析已有结果”和“重新拿数据”被建模成同一层能力，容易让 orchestrator 错路由。

### P2

1. orchestrator 与 follow-up 执行链中仍有少量 `Skill`、`answer_fetch` 等英文或内部实现名直接出现在用户可见摘要里，已收口为中文表达。
2. `selective_refetch` 虽已从主流程移出，但测试和兼容路径仍有残留命名，已继续清理。

## 本轮改动结论

1. `post_analysis_skill`
   - 现在只负责：
     - 深入分析
     - 快照对比
     - 结论解释
     - 风险提取
   - 不再承担任何重新采集数据的能力语义。

2. `answer_fetch`
   - 现在是唯一采集入口：
     - 首次抓取
     - 局部重跑
     - 全量重跑
     - `fast -> full`
     - `API -> 浏览器`

3. `refetch/selective_refetch`
   - 已从本轮改动覆盖的 source/tests 中移除，不再作为 public capability 存在。

4. orchestrator
   - 已增加“原因 + 下一步方案”的默认要求。
   - 用户可见思考流不再透传英文主导文本。

## QA

### 自动化验证

1. `python -m py_compile ...`
   - 结果：通过

2. 复用 `D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local` 注入环境后执行：
   - `pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q`
   - 结果：`29 passed`

3. `test_routing_matrix.py`
   - 结果：已做语法检查通过
   - 说明：该文件依赖运行中的后端与 LLM 环境，本轮未伪造 E2E 通过结论

4. 目标文件 `???` 污染扫描
   - 结果：通过

5. `selective_refetch` 残留扫描
   - 结果：在本轮修改覆盖的 source/tests 中已清除

## Code Review Conclusion

本轮改动可放行。

原因：

1. 能力边界比改造前明显更干净：
   - `post_analysis_skill` 只读
   - `answer_fetch` 唯一采集

2. 这次不是单纯改 prompt，而是把：
   - skill contract
   - follow-up executor
   - orchestrator routing
   - user-visible wording
   一起收口了。

3. 中文输出策略也更稳：
   - 去掉用户可见的英文 `Skill` 尾巴
   - 英文主导 thought stream 不再透传

## Residual Risks

1. 历史文档中仍有大量 `selective_refetch` 旧设计描述；这些历史稿未在本轮统一清理。
2. `test_routing_matrix.py` 虽已改成 `answer_fetch` 语义，但没有在真实后端上跑 E2E。
3. orchestrator 的“方案优先”目前仍主要靠 prompt policy 和少量 fallback 文案，后续还可继续下沉到更明确的 runtime recovery policy。

## Phase Status Update

- `Phase 0-4`：完成
- `Phase 5`：partial，AIO 继续排除
- `Phase 6`：主体完成；本轮已补上 `post_analysis_skill / answer_fetch` 边界收口与方案优先策略
- `Phase 7`：`Step 1 / 2 / 3 / 5 / 6` 完成
- `Phase 7.5`：最小提示词保密与注入防守已接入
