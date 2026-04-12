# AGEO Harness 分层边界重定义（2026-04-01）

> 版本：v0.1
> 日期：2026-04-01
> 状态：Draft
> 目的：在不推翻现有 AGEO 设计的前提下，重新梳理 `Orchestrator / Agent / Skill / Tool / Harness` 五层边界，并基于 Claude Code 的设计方式校正当前语义混用问题。

---

## 1. 这份文档解决什么问题

当前 AGEO 不是“没有分层”，而是“已经有分层雏形，但层与层之间的语义边界仍然含混”。

最典型的混淆包括：

1. `A5 / A7` 既像 executor，又被提升成了 public skill
2. `A3` 既像“消费者专家”，又像“问题生成器”，又像一个 workflow 节点
3. `Tool` 与 `Skill` 的语义交叉较多
4. `Harness` 当前更强在状态持有和材料沉淀，但在整体确定性治理上仍然偏弱
5. `A0 / General ReAct Agent` 提示词承载了过多流程细节、节点说明和阶段指令

这份文档的目标不是推翻现有路线，而是：

1. 保留已经做对的方向
2. 重新定义五层职责
3. 明确现有模块应归位到哪一层
4. 说明 Claude Code 值得借鉴的不是“文案语气”，而是“分层方式”

---

## 2. 核心结论

AGEO 后续应该以如下关系作为稳定共识：

1. `Orchestrator` 决定现在该做什么
2. `Skill` 定义一类任务应该怎么做
3. `Agent / Executor` 负责具体完成这一类任务
4. `Tool` 提供原子化、确定性的动作能力
5. `Harness` 负责整个系统的上下文、状态、边界、验证、恢复、写回与观测

进一步说：

1. `Agent != Skill`
2. `Skill != Tool`
3. `Orchestrator != Harness`
4. `Prompt` 只是 `Harness` 的一部分
5. `Harness` 不应只负责“记录状态”，还应负责“治理确定性”

### 2.1 AIO Answer Fetch Tool 的归位

AIO 相关能力应作为本分层模型的一个具体样例来理解：

```text
Orchestrator
  -> answer fetch capability
    -> Fetch Answer Agent / A4 executor
      -> AIO Answer Fetch Tool
        -> AIO Runtime
          -> Playwright Browser Agent
          -> Chromium / CDP / VNC
          -> AuthContext / RunContext
      -> Result Packet
    -> Artifact Writeback
```

边界结论：

1. `AIO` 不是新的 public skill。
2. `AIO` 不是前端 Canvas 交付物。
3. `AIO` 也不应该长期只是后端远程连 CDP 的临时技巧。
4. `AIO Answer Fetch Tool` 是 `A4 / Fetch Answer Agent` 调用的 Browser Execution Tool Facade。
5. `AIO Runtime` 内部应承载 Playwright executor、浏览器、VNC 接管、AuthContext、RunContext。
6. Agent 通过 Tool 操作浏览器，但不直接维护 CDP page、tab 或前端 VNC 状态。

完整设计见：

1. [AIO Answer Fetch Tool 架构归位](./architecture-aio-answer-fetch-tool-runtime-2026-04-12.md)
2. [AIO Answer Fetch Tool 生产级架构设计](./design-aio-parallel-playwright-context-2026-04-11.md)

---

## 3. 五层边界定义

### 3.1 Orchestrator

定义：

`Orchestrator` 是任务控制器，负责理解用户意图、检查前置条件、选择能力路径、决定阶段推进与暂停。

应该做的事：

1. 识别当前任务属于完整分析、后续分析、置信度评估还是知识材料操作
2. 根据当前 state / artifact / history 判断前置条件是否满足
3. 选择合适的 `skill`
4. 将任务交给合适的 executor 或 workflow 分支
5. 决定是否需要用户确认、是否可以自动继续、是否应回到用户

不应该做的事：

1. 不应直接承载过多节点级实现细节
2. 不应把所有任务打法都写进一份巨型 prompt
3. 不应直接等价于某个具体分析能力
4. 不应把工具级动作与 skill 级选择混在一起

在 AGEO 中，对应：

1. `A0 / General ReAct Agent`
2. `orchestrator_node.py`
3. `graph.py` 中的主控分支调度逻辑

---

### 3.2 Agent / Executor

定义：

`Agent / Executor` 是在受限职责内执行一类任务的专项执行者。

应该做的事：

1. 接收来自 orchestrator 的任务上下文
2. 消费对应 skill contract
3. 调用所需 tools
4. 产出结构化结果、artifact、fact snapshot 或状态更新

不应该做的事：

1. 不应负责全局路由
2. 不应自己定义产品层 public capability
3. 不应承担系统级验证、权限治理和长上下文治理

在 AGEO 中，当前可视为 executor 的主要对象：

1. `A1` 品牌竞品分析
2. `A2` 营销画像生成
3. `A3` 问题模拟
4. `A4` 答案抓取
5. `A5` 分析报告执行器
6. `A7` 置信度分析执行器

需要特别说明：

1. `A5` 变成 `analysis_report_skill` 不是错
2. 错的是如果因此把 `A5` 从 executor 角色中抹掉
3. 正确关系应为：`analysis_report_skill -> A5 executor`
4. 同理：`confidence_signal_skill -> A7 executor`

---

### 3.3 Skill

定义：

`Skill` 是一类任务的能力合同。它面向的是“意图层”和“产品层”，而不是节点层。

应该做的事：

1. 定义该能力适用于什么任务
2. 定义输入预期和前置条件
3. 定义输出形态和成功标准
4. 定义该能力的打法、策略、默认参数和 guardrails
5. 对 orchestrator 暴露为一个可选择的粗粒度能力单元

不应该做的事：

1. 不应只是 node 的另一个名字
2. 不应只是 prompt append 的临时片段
3. 不应承载原子动作
4. 不应过度碎片化成每个小步骤都是一个 skill

在 AGEO 中，当前明确成立的 public skills：

1. `analysis_report_skill`
2. `confidence_signal_skill`
3. `post_analysis_skill`

当前最重要的边界共识：

1. `Skill` 是“对外能力名”
2. `Executor` 是“对内实现者”
3. `Tool` 是“底层动作”

---

### 3.4 Tool

定义：

`Tool` 是原子化、确定性、低歧义、可复用的动作能力。

应该做的事：

1. 执行抓取、检索、汇总、对比、导出、持久化、生成等具体动作
2. 尽量保证输入输出结构稳定
3. 尽量保持低语义负担，便于多个 skill/executor 复用

不应该做的事：

1. 不应直接承载粗粒度业务能力语义
2. 不应与 public skill 命名处于同一抽象层
3. 不应把“角色”和“动作”混在一起

对 AGEO 的具体判断：

1. `fetch` 更像 tool
2. `knowledge_lookup / aggregate / compare / export` 更像 tool
3. `question generation` 如果只是生成问题，本质更像 tool 或 executor 内部模块
4. “消费者专家”更像角色设定或 executor 视角，而不是 tool
5. `AIO Answer Fetch Tool` 是 A4 使用的浏览器执行 Tool Facade，内部可以拆分为 browser action、takeover、auth state、run artifact 等原子工具

这意味着：

1. `A3` 当前之所以显得混，是因为它同时承担了角色、动作和节点三种语义
2. 后续应逐步拆开，而不是继续在一个名词里叠加三层语义
3. `AIO` 当前之所以容易混，是因为它同时被看成 runtime、前端云电脑、CDP 连接和答案抓取能力；后续必须统一收敛为 Tool / Runtime Capability

---

### 3.5 Harness

定义：

`Harness` 是组织前四层的运行外壳。它不是某一个文件，也不是某一份 prompt，而是一个系统层。

应该做的事：

1. 管理 context assembly
2. 管理 memory / knowledge / artifact / state
3. 管理前置条件和后置条件
4. 管理权限、确认策略、恢复策略、重试边界
5. 管理结果写回和 resume
6. 管理观测、成本、阶段进度、验证闭环

不应该做的事：

1. 不应被等同于 orchestrator
2. 不应被等同于某一份 system prompt
3. 不应只做“状态持有”

对 AGEO 当前现状的判断：

1. 当前 harness 更强在 `state / knowledge workspace / artifact / fact snapshot`
2. 当前 harness 更弱在 `确定性治理`

这里的“确定性治理”主要包括：

1. 阶段前置条件的硬校验
2. 阶段完成后的后置条件校验
3. 禁止跳步与禁止错序执行
4. 幂等性与重入语义
5. 失败恢复规则
6. 结果是否真的完成的验证 gate

一句话总结当前问题：

`AGEO 当前的 Harness 更像记录层，尚未完全成为治理层。`

---

## 4. 对现有 A0 提示词的 Review

当前主控提示词：

- [aeo-platform/backend/prompts/general_react_agent.md](../aeo-platform/backend/prompts/general_react_agent.md)

### 4.1 当前提示词做对了什么

以下方向是成立的，不应轻易推翻：

1. 明确了 `A0` 的主控职责
2. 明确了多阶段分析流程
3. 明确了拟人化交互与渐进式引导
4. 明确了 agent 间的依赖关系和 pipeline 模板
5. 明确了 TPAOR 作为思维组织框架

这些内容说明：

1. AGEO 一开始不是按“单轮问答助手”设计的
2. 而是按“多阶段分析流程协同系统”设计的

这个方向本身是对的。

### 4.2 当前提示词承载过多的部分

当前 `general_react_agent.md` 里，以下内容混在一起：

1. 身份与人设
2. 用户可见语言风格
3. TPAOR 过程组织
4. Agent 清单和依赖图
5. 完整 pipeline 模板
6. 分阶段输出示例
7. 阶段顺序和执行约束

这会导致两个问题：

1. `Prompt` 同时承担了 policy、route、打法、流程说明书、实现清单多种职责
2. orchestrator 会越来越像“背业务手册的人”，而不是“选能力和控流程的人”

### 4.3 对提示词的重定义建议

不建议简单删掉这份提示词，而建议把其职责重分配。

建议将 A0 prompt 后续收敛为 5 类 section：

1. `Identity & Interaction`
   - 角色、人设、语言风格、用户沟通原则
2. `Routing Policy`
   - 什么情况下应该走哪类能力路径
3. `State & Progress Policy`
   - 如何基于当前 artifact/state/history 决定下一步
4. `Risk & Verification Policy`
   - 哪些动作需要确认，哪些结果必须验证
5. `Capability Index`
   - 只暴露能力索引，不在主 prompt 中展开过多 executor 细节

其中：

1. pipeline 详细说明应更多转移到 skill contract 和 runtime guard
2. executor 细节应更多留在 skill package 或 executor prompt
3. 前后置条件应尽量转入 harness/runtime，而不是只写在主 prompt

---

## 5. 对 Claude Code 提示词的 Review

### 5.1 值得借鉴的点

Claude Code 默认 system prompt 值得借鉴的，不是“它写了很多禁止句”，而是它把 prompt 放在了正确的位置。

从源码可见，其 prompt 主要负责：

1. 行为政策
2. 工具使用政策
3. 风险动作政策
4. 结果报告真实性政策
5. 用户沟通风格政策

典型点包括：

1. 不允许猜测验证结果
2. 不允许未读代码就提改动建议
3. 不允许无关重构和过度设计
4. 优先使用 dedicated tools 而不是乱跑 shell
5. 风险动作要确认，失败结果要如实报告

这些都不是“文学风格”，而是在针对真实 failure modes 做 counterweight。

### 5.2 不应直接照抄的点

Claude Code prompt 有很强的“coding CLI 产品”属性，因此不应直接照抄：

1. 代码注释风格限制
2. GitHub/PR/branch/tooling 的大量细节
3. 针对软件工程任务的特定默认假设
4. 面向 CLI tool stack 的微观操作指令

AGEO 不需要复制这些字面内容。

### 5.3 真正应借的，是分层方式

Claude Code 最值得借的是：

1. `Prompt` 只做 policy，不做万能控制器
2. `Skill` 作为按需加载的能力合同，不等于 tool，也不等于 agent
3. `Tool` 有明确 contract，不只是“模型随便调的函数”
4. `Harness` 显式管理 context、memory、side-channel、compaction、permission、verification

---

## 6. 对 Claude Code 实现能力的 Review

### 6.1 Prompt Assembly

Claude Code 不是一份巨型 system prompt，而是分层组装的 prompt system。

这意味着：

1. 身份、系统约束、用户上下文、动态上下文、memory、skill reminder 是可拆分的
2. 可以有静态部分和动态部分
3. 可以针对 cache 和上下文成本做工程化设计

对 AGEO 的启发：

1. `A0` 的 prompt 不应继续无限膨胀
2. 应从“单体说明书”逐步演进到“sectioned harness prompt”

### 6.2 Skill Discovery

Claude Code 不会把所有 skill 正文一次性塞进主 prompt。

它的策略是：

1. 先给相关 skill 的索引提醒
2. 命中时再加载 skill body
3. skill 已加载后避免重复加载

对 AGEO 的启发：

1. public skill 不应只是 executor 前 append 一段文本
2. 应把 `skill contract / package / overlay` 真正变成可选择、可注入、可验证的能力层

### 6.3 Tool Contract

Claude Code 的 tool 不是一个普通函数调用点，而是带有：

1. 权限边界
2. 只读/破坏性标签
3. 输入校验
4. 并发安全

对 AGEO 的启发：

1. tool 应更原子、更确定
2. 对于关键 tool，应增加前置条件、参数约束、结果结构和错误语义
3. 这样 orchestrator 和 executor 才不会靠 prompt 去“猜”工具行为

### 6.4 Context Governance

Claude Code 把上下文治理当成系统级问题，而不是 prompt 文案问题。

对 AGEO 的启发：

1. Knowledge Workspace 很重要，但还不够
2. 还需要更强的：
   - state-to-context 投影策略
   - artifact/latest result 的结构化引用
   - 长链 follow-up 的 resume 规则
   - context 选择与压缩规则

### 6.5 Harness-only vs Model-visible Side Channel

Claude Code 会区分：

1. 给模型看的结构化提醒
2. 只给 harness/UI/runtime 自己看的 side-channel

对 AGEO 的启发：

1. 不是所有系统状态都应交给模型理解
2. 有些状态、提示、验证信息应保留在 runtime/harness 层
3. 有些提醒才适合投影进 prompt/context

---

## 7. AGEO 现有模块重新归位建议

### 7.1 Orchestrator 层

保留为：

1. `A0`
2. `orchestrator_node.py`
3. graph 中的主控路由逻辑

后续主要职责：

1. 选择 `analysis_report_skill / confidence_signal_skill / post_analysis_skill`
2. 判断前置条件是否满足
3. 判断是否继续走 A1/A2/A3/A4 主链
4. 判断是否进入 Knowledge Workspace 路径

不再鼓励它继续直接面向大量 node/tool 细节编排。

### 7.2 Executor 层

建议继续保留：

1. `A1`
2. `A2`
3. `A3`
4. `A4`
5. `A5`
6. `A7`

但应在心智上统一改称：

1. `executors`
2. 或 `specialized agents`

其中：

1. `A5` 是 `analysis_report_skill` 的 executor
2. `A7` 是 `confidence_signal_skill` 的 executor
3. `A4` 更接近 tool-backed executor
4. `A3` 需要后续拆解其角色语义与动作语义

### 7.3 Skill 层

第一阶段继续只保留 3 个 public skills：

1. `analysis_report_skill`
2. `confidence_signal_skill`
3. `post_analysis_skill`

理由：

1. 这 3 个是用户可理解、orchestrator 可选择、后台可配置的粗粒度能力
2. 不宜过早把 knowledge ops 和内部模块提升成 public skill

### 7.4 Tool 层

建议明确归为 tool 的能力包括：

1. `fetch`
2. `knowledge_lookup`
3. `knowledge_aggregate`
4. `knowledge_compare`
5. `knowledge_export`
6. 各类确定性 persistence / normalization / artifact write-back 动作
7. `aio_answer_fetch`
   - 它不是新的 public skill，而是 `A4 / Fetch Answer Agent` 调用的粗粒度 browser execution tool
   - 内部必须统一覆盖豆包、元宝、Kimi、DeepSeek 四个平台
   - 普通弹窗、广告、Cookie、页面恢复应由 AIO Browser Agent 自动处理
   - 登录、验证码、人机验证、账号安全确认才进入 human takeover
   - 返回结构化 result packet 后再由 A4 写入 Artifact

对于 `question generation`，建议暂时保持审慎：

1. 如果它只是生成问题，则应更靠近 tool
2. 如果它承载消费者视角策略，则应由 executor 负责视角，tool 只负责生成动作

### 7.5 Harness 层

AGEO 应显式承认以下内容属于 harness：

1. `graph`
2. `state`
3. `skill registry`
4. `skill invocation plan`
5. `skill package / prompt overlay`
6. `knowledge workspace`
7. `artifact / version / resume`
8. `fact snapshot`
9. `前置条件 / 后置条件 / 恢复规则 / 验证 gate`

其中当前最需要加强的是最后一项。

---

## 8. 近期不建议做的事

1. 不建议把所有 node 都重新命名成 skill
2. 不建议把 every capability 都提升成 public skill
3. 不建议继续把 A0 prompt 做得更长
4. 不建议只靠 prompt 文案修复语义混乱
5. 不建议让 Knowledge Workspace 替代 orchestrator、skill 或 executor

---

## 9. 建议的近期演进方向

### 9.1 第一优先级：固定边界语义

从现在开始统一使用以下说法：

1. `A1/A2/A3/A4/A5/A7` 是 executors
2. `analysis_report_skill / confidence_signal_skill / post_analysis_skill` 是 skills
3. `fetch / lookup / compare / export / generator` 是 tools
4. `A0` 是 orchestrator
5. `state + graph + workspace + artifact + guards` 合起来才叫 harness

### 9.2 第二优先级：把 A0 prompt 缩回 policy 层

目标不是删除，而是收敛职责：

1. 保留角色、人设、交互风格
2. 保留高层 routing policy
3. 减少节点级细节和流程说明书式内容
4. 将打法和边界更多转移到 skill contract 与 harness guard

### 9.3 第三优先级：让 harness 从记录层升级为治理层

至少应逐步补足：

1. skill 前置条件检查
2. skill 完成后的后置条件检查
3. 关键 artifact 是否真正写回的 gate
4. follow-up 路径的 resume / retry / fallback 规则
5. 对工具的输入输出契约检查

---

## 10. 最终共识

对 AGEO 来说，真正要借鉴 Claude Code 的，不是它写了多少“不要猜测”的句子，而是：

1. 让 `Orchestrator` 只负责决策
2. 让 `Skill` 真正成为能力合同
3. 让 `Executor` 负责实现
4. 让 `Tool` 保持原子和确定
5. 让 `Harness` 负责整个系统的上下文、状态、验证与治理

如果要把这份文档压缩成一句话：

`AGEO 后续的目标，不是继续做一个更大的主控 prompt，而是把现有系统收敛成一个边界清晰的 Agent System：orchestrator 选 skill，skill 约束 executor，executor 调用 tool，harness 负责系统确定性。`
