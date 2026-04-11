# Claude Code 参考改造架构复审（2026-04-01）

> 版本：v1.0
> 日期：2026-04-01
> 状态：Review Passed with Residual Risks
> 范围：`codex/validation-retro-harness`
> 说明：本复审明确排除尚未合流完成的 `AIO / takeover / relay / resume state machine` 实现，只评审当前分支中已经落地的 Claude Code 参考改造。

---

## 1. 复审目的

这份文档回答三个问题：

1. 这轮改造到底改了哪些结构，而不只是改了几句 prompt
2. 它与此前总结的 Claude Code 设计相比，已经对齐了哪些核心点
3. 除 AIO 之外，当前还剩哪些明确的架构债

本复审基于以下输入：

1. 已落地代码
2. 分阶段 QA / Code Review 记录
3. 已写回的边界设计文档与 contributor guide

---

## 2. 结论先行

结论很明确：

`除 AIO 未合流部分外，这轮改造已经把 AGEO 从“以大 orchestrator prompt 为中心的多节点系统”，推进到了“以 contract + runtime guard 为中心的 agent system 雏形”。`

更具体地说，这次不是“优化文案”，而是完成了下面 5 个结构性变化：

1. `Orchestrator prompt` 从单体说明书改成了 sectioned assembly
2. `public skill` 从 prompt overlay 升级成了正式 contract
3. `A5 / A7` 从“节点直接执行”升级成了 `Skill -> Executor -> Artifact -> Harness Gate`
4. `ToolCapabilityMatrix` 从元数据文档升级成了运行时 enforcement
5. `A3` 开始把“stage / role / generation primitive”三层语义拆开

这 5 件事，正对应 Claude Code 最值得借鉴的核心：  
不是让 prompt 更强势，而是让 `Orchestrator / Skill / Tool / Harness` 四层边界更清晰。

---

## 3. 复审范围

本次纳入复审的主要实现包括：

1. Orchestrator prompt 收缩与 section 化
2. Skill contract 正式化
3. A5 / A7 harness gate 接入
4. Tool capability matrix 与 caller enforcement
5. A3 内部 question generation 下沉
6. A4 当前分支可见路径上的 harness 补强
7. repo-level contributor guide 与 PR template

明确不纳入本次完成结论的部分：

1. 完整 `AIO runtime`
2. `takeover / relay / resume` 的统一状态机
3. 浏览器接管相关的完整 harness policy

---

## 4. 对照 Claude Code：本轮真正借鉴了什么

此前我们对 Claude Code 的判断，不是“它 prompt 写得凶”，而是它在系统上做对了几件事：

1. `Prompt` 只做 policy，不做万能控制器
2. `Skill` 是能力合同，不等于 agent 或 tool
3. `Tool` 是带 contract 的动作原语，不是随便调的函数
4. `Harness` 负责上下文、状态、验证、恢复、写回，而不只是记录

本轮改造真正借到的，就是这 4 件事。

没有照抄的内容包括：

1. Claude Code 的 coding CLI 细节
2. Git / PR / shell 约束文案
3. 针对编码任务的微观行为规则

因此，这轮改造的价值不在于“把 AGEO prompt 写得更像 Claude Code”，而在于：

`把 Claude Code 的分层方式翻译成了适合 AGEO 的 Agent System 结构。`

---

## 5. 本轮实际改动的结构映射

### 5.1 Orchestrator：从大 prompt 说明书走向 sectioned assembly

已落地：

1. 新增 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/prompt_assembly.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/prompt_assembly.py)
2. 在 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/orchestrator_node.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/orchestrator_node.py) 中引入 `build_orchestrator_prompt_assembly`
3. 重写 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/prompts/general_react_agent.md](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/prompts/general_react_agent.md)，将其重新定义为 A0 baseline，而不是运行时总说明书

这意味着：

1. A0 prompt 已经不再是“所有内容都塞在一份文件里”
2. runtime 已经具备了 `base policy / skill index / dynamic context / runtime reminder` 的拆分能力
3. orchestrator 的职责更接近控制器，而不是业务手册背诵器

架构判断：

`这一步是成功的，而且是这轮改造最核心的结构变化。`

---

### 5.2 Skill：从 prompt overlay 升级成正式 contract

已落地：

1. 新增 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/skill_contracts.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/skill_contracts.py)
2. `SkillInvocationPlan` 扩展为包含正式 `skill_contract`，见 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/skill_invocation_service.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/skill_invocation_service.py)
3. `skill_state` 开始优先消费结构化 section，而不是简单拼接字符串，见 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/skill_state.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/skill_state.py)

当前 public skill 试点：

1. `analysis_report_skill`
2. `confidence_signal_skill`
3. `post_analysis_skill`

这一步最大的意义是：

1. `Skill` 终于不再只是“executor 前附一段 prompt”
2. `Skill` 开始具备了输入、前置条件、输出预期、artifact writeback 规则等正式语义
3. `A5 / A7 / Follow-up` 的产品层能力名与实现层执行者开始真正解耦

架构判断：

`这一步对齐了 Claude Code 最重要的设计思想之一：Skill 是能力合同，不是节点别名。`

---

### 5.3 A5 / A7：Skill -> Executor -> Artifact -> Harness Gate

已落地：

1. [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a5.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a5.py)
2. [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a7.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a7.py)
3. [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/harness_validation.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/harness_validation.py)

当前 A5 / A7 已具备：

1. `precondition gate`
2. `artifact writeback validation`
3. `postcondition gate`
4. `harness decision writeback`

这意味着：

1. 完成不再由 LLM “自称成功”决定
2. 关键 artifact 是否真实写回，已经进入 runtime 校验链
3. `A5/A7` 没有因为 skill 化而丢掉 executor 身份

架构判断：

`这是从“模型驱动完成”走向“系统驱动完成”的关键一步。`

---

### 5.4 Tool：从能力名混用走向 capability contract

已落地：

1. 新增 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/tool_capability_matrix.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/services/tool_capability_matrix.py)
2. 引入 caller 校验 `validate_tool_capability_access`
3. orchestrator 与 post-analysis executor 已开始实际消费该校验

这一步的重要变化不是“多了一张表”，而是：

1. `Tool` 开始拥有 `allowed_callers / side_effect_level / artifact_writeback_target / confirmation_policy`
2. `ToolCapabilityMatrix` 已从说明性元数据变成 enforcement
3. follow-up 路径已经能在运行时阻止不允许的 capability caller

架构判断：

`这一步虽然还没有铺满全系统，但已经把 Tool 从“命名习惯”提升成了 contract 层。`

---

### 5.5 A3：开始拆 stage / role / generation primitive

已落地：

1. 新增 [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/tools/question_generation.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/tools/question_generation.py)
2. [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a3.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a3.py) 已将纯问题生成逻辑下沉到内部 tool
3. 已删除节点内遗留的大量旧 prompt helper，避免语义回流

这意味着：

1. `A3 stage` 继续保留为 workflow stage
2. 纯 `question generation` 更明确地变成内部 primitive
3. `A3` 的语义混层开始被拆开，而不是继续在一个节点里叠加

架构判断：

`这一步还不是 A3 的最终形态，但方向正确，且已经减少了语义反复回流的风险。`

---

### 5.6 A4：当前分支可见路径上的 harness 补强

已落地：

1. [D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a4.py](D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/workflow/nodes_a4.py)
2. `selective_refetch merge validation`
3. `A4 completion policy decision`
4. 顶层异常路径的 harness decision writeback

这一步的正确结论应是：

1. `A4` 已开始向统一 harness contract 靠拢
2. 但当前只是当前分支可见代码路径的部分接入
3. 不能把它表述成“完整 AIO / takeover / resume 已完成”

架构判断：

`方向对，但范围必须严格标注为 partial integration。`

---

## 6. 本轮新增的系统层资产

除代码外，本轮还新增了两类重要系统资产：

1. 边界与贡献约束文档
   - [D:/AGEO-worktrees/validation-retro-harness/docs/design-harness-implementation-constraints-2026-04-01.md](D:/AGEO-worktrees/validation-retro-harness/docs/design-harness-implementation-constraints-2026-04-01.md)
   - [D:/AGEO-worktrees/validation-retro-harness/docs/architecture-harness-refactor-contributor-guide-2026-04-01.md](D:/AGEO-worktrees/validation-retro-harness/docs/architecture-harness-refactor-contributor-guide-2026-04-01.md)

2. 阶段化 QA / Code Review 记录
   - [D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase4-qa-review.md](D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase4-qa-review.md)
   - [D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase5-qa-review.md](D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase5-qa-review.md)
   - [D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase6-qa-review.md](D:/AGEO-worktrees/validation-retro-harness/docs/session-logs/2026-04-01-claude-harness-phase6-qa-review.md)

以及 repo-level PR 约束：

- [D:/AGEO-worktrees/validation-retro-harness/.github/pull_request_template.md](D:/AGEO-worktrees/validation-retro-harness/.github/pull_request_template.md)

这说明本轮不只是做了代码重构，也开始把“如何继续按这套边界演进”写回仓库。

---

## 7. QA 结果与稳定性判断

当前可确认的验证结果：

1. `pytest tests/test_harness_refactor_foundations.py -q`
   - 结果：`14 passed`
2. `python -m py_compile ...`
   - 覆盖本轮改动文件，已通过
3. 中文文档 / prompt 写回后的问号污染扫描
   - 未发现编码损坏

这说明：

1. 这次改造不是“只改结构，不看回归”
2. 至少在当前试点范围内，已经有基础回归闭环
3. QA 与 Code Review 闸门已经开始真正发挥作用

---

## 8. 剩余架构债

### 8.1 兼容层仍在，边界尚未完全冻结

当前仍保留：

1. `LEGACY_SKILL_TOOL_ALIASES`
2. state 中若干过渡字段
3. 旧调用路径的兼容口径

这意味着：

1. 系统目前处于可控的双轨期
2. 不是最终边界状态
3. 后续需要在更大范围回归后逐步收缩兼容层

---

### 8.2 Harness 还没有全局铺满

当前 harness 治理较完整的链路：

1. `A5`
2. `A7`
3. `post_analysis_executor` 的 capability enforcement
4. `A4` 的部分 completion / merge validation

但尚未全局统一覆盖：

1. 所有 executor 的 pre/postcondition
2. 所有关键 artifact 的 writeback gate
3. 所有 tool caller 的 capability enforcement
4. 更完整的 resume / retry / recovery semantics

这意味着：

`Harness 已从记录层进化成治理层试点，但还不是系统级完全一致的治理层。`

---

### 8.3 A4/AIO 仍需等待实现分支合流

这一点必须单独强调：

1. 当前 A4 部分 integration 不代表完整 AIO 改造完成
2. `takeover / relay / resume / session state machine` 仍是后续工作
3. 这块不能在当前文档里被说成“已完成”

因此后续与 AIO 合流时，应该把重点放在：

1. harness policy 接入
2. session / resume gate 接入
3. blocker taxonomy 接入
4. artifact merge validation 与 A4 policy 统一

---

## 9. 架构师判断

如果从架构质量角度给出一句结论，我的判断是：

`这轮改造已经构成“结构发生变化”的架构演进，而不是命名整理或 prompt 优化。`

理由如下：

1. 核心边界已经开始从概念转为代码结构
2. 关键 contract 已经存在，并被 runtime 消费
3. QA / Review 已经按阶段写回，不再只是口头承诺
4. contributor guide 与 PR template 已把这套边界转成团队可执行约束

如果要用更直白的话说：

你们现在已经不只是“知道 Claude Code 好在哪”，而是已经把其中最值得借的那部分，翻译成了 AGEO 自己的系统骨架。

---

## 10. 后续建议

### 10.1 AIO 合流前

建议不要再大规模扩边界，而是保持当前收口：

1. 保持 `Orchestrator / Skill / Tool / Harness` 术语稳定
2. 不再把新的粗粒度能力直接塞回 A0 prompt
3. 不再让 A3 的旧 helper 回流到 node 内
4. 不急于移除所有 legacy alias，但禁止继续新增新的 alias 债务

### 10.2 AIO 合流时

优先补：

1. `A4/AIO` 的 harness state machine
2. `takeover / resume` 的 validation gate
3. blocker -> policy decision 的统一 contract
4. browser runtime 侧的 postcondition / merge validation

### 10.3 AIO 合流后

再考虑：

1. 缩减兼容层
2. 全局推广 capability enforcement
3. 进一步压缩 state 中的过渡字段
4. 把更多 executor 接入统一 harness gate

---

## 11. 最终结论

本轮 Claude Code 参考改造，在不考虑尚未合流的 AIO runtime 前提下，可以给出如下正式结论：

1. `Orchestrator` 已开始从大 prompt 控制器转向 sectioned decision layer
2. `Skill` 已开始从 prompt overlay 转向 formal contract
3. `A5 / A7` 已形成 `Skill -> Executor -> Artifact -> Harness Gate` 的试点闭环
4. `Tool` 已拥有 capability contract，并开始运行时 enforcement
5. `Harness` 已不再只是记录 state，而是开始承担治理职责

因此：

`AGEO 当前已经具备继续向“Claude Code 风格的 Agent System”演进的稳定骨架。`

剩余工作不再是“方向不清”，而是把这套骨架继续铺到 AIO 和其他剩余路径上。
