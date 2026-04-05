# AGEO Claude Code 参考改造实施约束（2026-04-01）

> 状态：Active
> 适用分支：`codex/validation-retro-harness`

## 目标边界

本轮改造统一以以下五层边界为准：

1. `Orchestrator`
   - 只负责意图识别、前置条件判断、选 skill、选 executor、决定继续或暂停。
2. `Agent / Executor`
   - 负责专项执行，不承担全局路由。
3. `Skill`
   - 负责 public capability contract，不是 node 别名。
4. `Tool`
   - 负责原子动作能力，不承载粗粒度业务语义。
5. `Harness`
   - 负责 context、state、validation、recovery、artifact writeback。

## 本轮固定共识

1. `A5` 仍然是 executor，`analysis_report_skill` 是 public skill。
2. `A7` 仍然是 executor，`confidence_signal_skill` 是 public skill。
3. `post_analysis_skill` 是 follow-up capability contract，不是 follow-up node 的别名。
4. `A3` 当前仍混合角色、动作、节点三层语义；本轮只先建立 capability matrix 和 contract 边界，不一次性重写 A3。
5. `general_react_agent.md` 继续保留为 orchestrator 设计基线，但运行时 prompt 以 `orchestrator_node.py` 的 sectioned assembly 为准。

## 本轮实现切口

1. Phase 0
   - 写回实施约束和安全检查点。
2. Phase 1
   - 引入 `PromptAssembly`，把 orchestrator prompt 改成 sectioned runtime assembly。
3. Phase 2
   - 引入 `SkillContract`，先覆盖 `analysis_report_skill`、`confidence_signal_skill`、`post_analysis_skill`。
   - A5/A7 接入 `precondition gate` 和 `artifact writeback gate`。
4. Phase 3 以后
   - 再推进 capability matrix、A3 拆层、A4/AIO harness policy、全链路推广。
5. Phase 6 稳定化补丁
   - 已收口 `post_analysis_skill / answer_fetch` 边界：
     - `post_analysis_skill` 只做已有结果分析
     - `answer_fetch` 成为唯一采集入口
     - `refetch/selective_refetch` 不再作为 public capability 存在
   - 已补强 orchestrator 的方案优先策略：
     - 遇到条件不足或失败时，不再停在“无法完成/不能执行”
     - 默认补出原因与下一步可执行方案
   - 已补强用户可见中文策略：
     - 去除 `Skill` 等英文展示尾巴
     - 用户可见思考流不再透传英文主导文本
6. Phase 7
   - 推进 orchestrator context protocol。
   - 目标不是继续扩 A0 prompt，而是把 orchestrator context 从 summary-first 升级为 packet-first。
   - 当前已完成 Step 1：`SessionStatusPacket / EntityContextPacket / HistoryAvailabilityPacket` 与 prompt assembly 接线。
   - 当前已接入 Step 2 / Step 3：`RecentEvidencePacket`、`PendingDecisionPacket`、`ActiveSkillPacket`。
   - 当前已接入 Step 5：`A4 current_fetch`、`A5 current_artifact`、`A7 current_artifact`。
   - 当前已接入 Step 6：`uploaded_input evidence packet`、`current session evidence relevance/ranking`、model-visible 中文化、orchestrator thinking 英文兜底。
7. Phase 7.5
   - 推进 instruction provenance 与 prompt defense。
   - 当前范围：prompt disclosure refusal policy、injection-aware evidence rendering、untrusted external content tagging、最小检测与测试。
   - 当前已接入：prompt disclosure 拒绝、注入感知证据渲染、untrusted external content tagging、最小测试闭环。

## 非目标

1. 本轮不重写 A4/AIO runtime。
2. 本轮不清理全部 legacy alias。
3. 本轮不做数据库 schema 迁移。
4. 本轮不把所有 node 一次性 skill 化。

## QA / Review 闸门

每个后续阶段都必须补：

1. 至少 1 组单元层验证。
2. 至少 1 条失败路径或 gate 路径验证。
3. findings-first code review 结论。
4. 残余风险清单。
