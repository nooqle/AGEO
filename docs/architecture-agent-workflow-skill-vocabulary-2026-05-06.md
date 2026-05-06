# Specta Agent / Workflow / Skill 词典与当前架构梳理（2026-05-06）

> 状态：Draft
> 目的：把 Specta 里已经出现的 Agent、Node、Executor、Skill、Tool、Prompt、Artifact 等概念重新说清楚，避免后续继续改到不生效的旧 prompt 或混用概念。

## 一句话结论

Specta 现在不是标准的“主 Agent + 多个 SubAgent”系统。

更准确地说，它是：

```text
A0 Orchestrator
  + LangGraph Workflow
  + Executor Nodes
  + Skill Registry / Skill Contract
  + Tool / Adapter
  + Artifact / Memory
```

也就是说：

- A0 是主 Agent。
- A1/A2/A3/A4/A5/A7 更像业务阶段，不一定是 SubAgent。
- 每个业务阶段由一个或多个 Executor Node 执行。
- Executor Node 里面可以调用 LLM，也可以运行确定性代码。
- Skill 是对外暴露的能力，不等于某个 prompt 文件。
- `SKILL.md` 是给 LLM看的能力说明，也不等于真正的执行代码。

## 1. 先统一几个词

### Model

Model 是大模型本身，例如 DeepSeek、GLM、Kimi 等。

它负责理解、推理和生成。

当前 Specta 后端运行时按三类模型配置，而不是按每个节点各配一套模型：

| 模型类 | 当前默认 | 主要用途 |
| --- | --- | --- |
| 文本思考模型 | DeepSeek v4 Pro | A0 Orchestrator、长文本、A2、A3 |
| 文本轻模型 | DeepSeek v4 Flash | URL intelligence、短文本轻量分类/结构化任务 |
| 综合多模态模型 | GLM-5 | A1、Browser Agent、多模态或搜索抓取相关任务 |

环境配置也应该优先看这三组：

```text
TEXT_REASONING_LLM_PROVIDER / TEXT_REASONING_MODEL_NAME
TEXT_LIGHT_LLM_PROVIDER / TEXT_LIGHT_MODEL_NAME
MULTIMODAL_LLM_PROVIDER / MULTIMODAL_MODEL_NAME
```

旧的 `ORCHESTRATOR_*`、`A3_*`、`URL_INTELLIGENCE_*` 等 task 级配置只保留兼容字段，不再作为主要运行时口径。

### Prompt

Prompt 是给 Model 的上下文和指令。

Prompt 分三类：

1. Orchestrator Prompt：给 A0 主编排器看的。
2. Executor Prompt：某个执行节点自己调用 LLM 时用的。
3. Skill Guidance：`SKILL.md` 这种能力说明，可能会被注入到 Orchestrator 或部分 Executor。

不要再假设 `prompts/*.md` 都是活的运行时 prompt。现在有很多是历史遗留。

### Tool

Tool 是系统可以调用的一个能力入口。

在 Specta 里，Tool 可以是：

- 业务能力入口，例如 `analysis_report_skill`
- 内部动作，例如问题生成、回答抓取
- 外部服务调用，例如某个平台 API
- 数据库、artifact、memory 写入能力

Tool 的重点是“可被调用”，不是“是否用 LLM”。

### Adapter

Adapter 是连接某类外部平台的实现。

A4 里有不同平台，所以会有不同 adapter：

- DeepSeek
- Kimi
- 豆包
- 元宝
- 浏览器抓取路径
- API 抓取路径

Adapter 不应该被叫成 SubAgent。它只是平台适配器。

### Workflow

Workflow 是业务流程的执行顺序。

当前典型品牌分析流程是：

```text
A1 品牌/竞品
  -> A2 画像/场景
  -> A3 问题模拟
  -> A4 回答采集
  -> A5 分析报告
```

这是一个流程，不是多个自由行动的 Agent 团队。

### Node

Node 是 Workflow 里的一个固定工序。

它的特点是：

```text
读 state
  -> 执行固定逻辑
  -> 写 state / artifact
  -> 返回
```

Node 可以调用 LLM，但它不等于 SubAgent。

### Executor

Executor 是真正执行某个业务能力的代码。

它通常表现为一个 Node，例如：

- `nodes_a5.py`
- `nodes_followup.py`
- `nodes_site_confidence.py`

Executor 负责把输入变成结果，并把结果写回系统。

### SubAgent

SubAgent 应该是一个更独立的小代理。

它应该有：

- 自己的 system prompt
- 自己的上下文窗口
- 自己的工具选择权
- 自己的多步执行循环
- 自己处理失败和重试的能力
- 最后把结果返回给主 Agent

所以 SubAgent 的结构更像：

```text
接收任务
  -> 计划
  -> 调工具 / 观察
  -> 修正
  -> 产出结果
  -> 返回主 Agent
```

A2/A3 现在还不是这个形态。它们更准确叫“会调用 LLM 的 Executor Node”。

### Skill Definition

Skill Definition 是注册表里的能力定义。

它回答：

```text
系统有哪些对外能力？
这些能力叫什么？
用户说什么时可以触发它？
它对应哪个 executor？
```

当前代码位置：

```text
aeo-platform/backend/app/services/skill_registry_service.py
```

### Skill Contract

Skill Contract 是能力执行契约。

它回答：

```text
这个能力需要什么输入？
允许用什么工具？
必须产出什么？
完成前必须写入什么 artifact？
失败时有哪些 blocker？
```

当前代码位置：

```text
aeo-platform/backend/app/services/skill_contracts.py
```

### Skill Guidance / SKILL.md

`SKILL.md` 是给 LLM看的自然语言说明。

它适合写：

- 这个能力应该怎么理解用户意图
- 输出时应该注意什么边界
- 哪些话不要说
- 哪些结果要优先展示

它不适合写：

- 百分比怎么算
- 数据库怎么写
- artifact key 怎么生成
- API 怎么重试

### Skill Package

Skill Package 是一组放在 `skill_packages/` 下的能力说明文件。

当前形态通常是：

```text
skill_packages/<package-name>/SKILL.md
```

并且需要在 `skill_package_service.py` 里映射到某个 skill family。

现在已经映射的是：

```text
analysis_report_skill -> analysis-report
post_analysis_skill -> post-analysis
```

官网 AI 友好度评估目前还没有自己的 package。

### Artifact

Artifact 是系统正式产出的可持久化结果。

例如：

- 分析报告
- Dashboard 数据
- 官网 AI 友好度报告
- 问题集
- 采集结果

Artifact 是后续追问、复盘、对比和展示的基础。

### Memory / RAG

Memory 是系统保存的历史事实和可复用知识。

RAG 是把外部知识或历史结果检索出来，再注入给 Model 使用。

Specta 里类似的东西包括：

- 历史报告
- domain memory
- source/domain intelligence
- 当前 brand profile
- 已有 A4 evidence

### MCP

MCP 是外部工具和数据源的标准通信协议。

当前 Specta 后端主流程里没有把 MCP 作为核心运行时抽象。现阶段更重要的是先把内部 Tool、Skill、Executor、Artifact 的边界理顺。

## 2. Orchestrator 在干什么

A0 Orchestrator 是主 Agent。

它应该负责：

- 理解用户意图
- 判断当前状态
- 选择下一步 skill 或 tool
- 判断是否需要用户确认
- 决定是否继续 workflow
- 把 executor 的结果解释给用户

它不应该负责：

- 算指标
- 抓平台回答
- 写 A5 报告细节
- 判断官网页面分数
- 做 URL 分类细节

## 3. System Prompt 应该怎么分层

Orchestrator 的 prompt 应该分成五层：

```text
1. 固定系统规则
2. 可用工具 / skill 列表
3. 当前 skill 的 guidance / contract 摘要
4. runtime context
5. 用户最新消息
```

其中：

- 固定系统规则应该尽量稳定，方便 prompt cache 命中。
- runtime context 会变化，例如当前品牌、当前阶段、已有结果、待确认事项。
- 用户最新消息必须保持在最后，避免模型忽略用户真实请求。

之前 Phase 0-2 的 prompt cache 改造，核心就是把固定规则和动态上下文拆开。

## 4. 为什么用 Node，而不是一开始全做 SubAgent

Node 适合稳定流程。

例如 A2/A3/A4/A5 都有明确的输入和输出：

- A2 输出画像/场景
- A3 输出问题列表
- A4 输出平台回答和引用
- A5 输出报告和指标

这些结果会被下游消费，所以需要：

- schema 稳定
- 失败边界清楚
- 可重跑
- 可追踪
- 可写 artifact
- 可做验收

这就是 Node 的优势。

SubAgent 更适合不确定、多步骤、自主探索的任务。例如：

- 自己选择多个工具
- 自己处理失败
- 自己决定是否重试
- 自己总结过程
- 自己返回最终结果

所以合理关系应该是：

```text
Workflow Node = 外层流程边界
SubAgent = Node 内部可选的智能执行策略
```

也就是说，未来可以把 A3 内部升级成轻量 SubAgent，但外层仍然应该保留 A3 Node 作为流程边界。

## 5. LLM 和代码分别该做什么

不是所有事情都应该交给 LLM。

LLM 适合做：

- 意图理解
- 场景推理
- 问题生成
- 复杂归纳
- 报告表达
- 多证据综合判断

代码适合做：

- 计数
- 百分比
- 排名
- 去重
- URL 解析
- 域名标准化
- schema 校验
- 数据库写入
- artifact 版本管理
- retry / timeout / rate limit

坏的硬编码是：

- 把业务判断散落在代码里
- 把 prompt 规则藏在多个函数里
- 把用户可见文案到处复制

好的确定性代码是：

- 指标计算
- 结构化校验
- 状态写回
- artifact 生成
- 平台适配

后续要清理的重点不是“消灭所有代码”，而是把业务口径集中管理，不要散落。

## 6. 当前 A1 到 A7 应该怎么理解

### A1

A1 是品牌和竞品分析阶段。

当前它还在使用活的 prompt 文件：

```text
aeo-platform/backend/prompts/brand_competition_agent.md
```

这个文件应该保留。

### A2

A2 是画像和场景生成阶段。

它不是完整 SubAgent，而是 LLM-powered Executor Node。

模型路由：A2 明确使用“文本思考模型”，当前默认是 DeepSeek v4 Pro。后续如果要切到 Flash，应该显式改 A2 路由，而不是继续藏在 `fast structured` 这类模糊名字里。

当前结构已经对齐 A3：

```text
aeo-platform/backend/app/workflow/nodes.py
  -> 负责 A2 workflow 状态、进度、artifact、用户确认和降级

aeo-platform/backend/app/tools/persona_generation.py
  -> 负责画像生成 prompt、retry prompt、payload 标准化、校验和 pipeline 数据结构
```

旧文件 `marketing_persona_agent.md` 不应该再被当成运行时 prompt。

### A3

A3 是问题模拟阶段。

它现在也是 LLM-powered Executor Node。

当前活逻辑在：

```text
aeo-platform/backend/app/tools/question_generation.py
aeo-platform/backend/app/workflow/nodes_a3.py
```

A3 未来最适合升级成轻量 SubAgent，因为它有生成、去重、自检、修正的空间。

但外层仍然应该保留 A3 Node，因为问题集必须写成稳定 artifact。

### A4

A4 是回答采集阶段。

更准确的定义是：

```text
A4 = Answer Acquisition Stage
```

它负责：

- 调不同平台
- 拿回答
- 拿引用
- 记录失败
- 做平台归一化
- 做来源域名解析
- 为 A5 提供结构化 evidence

A4 下面的 DeepSeek、Kimi、豆包、元宝、Browser、API client 是 Adapter，不是 SubAgent。

### A5

A5 是分析和报告编译阶段。

更准确的定义是：

```text
A5 = Analysis & Report Compiler
```

它负责：

- 算指标
- 做诊断
- 生成报告结构
- 输出 dashboard 数据
- 写 report artifact

当前 A5 主报告不是靠 `a5/prompt.py` 生成，而是靠这些活模块：

```text
aeo-platform/backend/app/workflow/a5/metrics.py
aeo-platform/backend/app/workflow/a5/sentiment.py
aeo-platform/backend/app/workflow/a5/diagnosis.py
aeo-platform/backend/app/workflow/a5/canonical.py
aeo-platform/backend/app/workflow/a5/postprocess.py
```

所以要改 A5 报告口径，应该改这些活模块。

### A7 / 官网 AI 友好度评估

现在用户真正使用的是“官网 AI 友好度评估”，不是旧的“引用置信度评估”。

当前活链路是：

```text
site_confidence_assessment_skill
  -> site_confidence_assessment_executor
  -> nodes_site_confidence.py
  -> site_confidence_assessment.py
```

它主要是确定性扫描：

- 发现官网页面
- 抓取 HTML
- 判断默认抓取路径是否能读到页面
- 检查 H1、main/article、正文厚度
- 检查结构化数据
- 检查 sitemap / robots
- 计算页面分数
- 生成官网 AI 友好度报告

旧的 `confidence-signal/SKILL.md` 对应的是旧“引用置信度评估”，不应该继续代表官网 AI 友好度。

## 7. Skill 四层关系

以后讨论 Skill，建议固定使用这四层：

```text
Skill Definition
  -> Skill Contract
  -> Skill Guidance Package
  -> Executor
```

### Skill Definition

在哪里注册这个能力。

当前位置：

```text
aeo-platform/backend/app/services/skill_registry_service.py
```

### Skill Contract

机器可校验的能力合同。

当前位置：

```text
aeo-platform/backend/app/services/skill_contracts.py
```

### Skill Guidance Package

给 LLM看的能力说明。

当前位置：

```text
aeo-platform/backend/skill_packages/*/SKILL.md
```

### Executor

真正干活的代码。

例如：

```text
nodes_a5.py
nodes_followup.py
nodes_site_confidence.py
```

## 8. 当前 Skill 映射现状

当前已注册的主要 public skill：

| Skill | 作用 | Executor | Package 状态 |
| --- | --- | --- | --- |
| `analysis_report_skill` | 完整分析报告 | `a5_data_analytics` | 有 `analysis-report` |
| `post_analysis_skill` | 后续分析/追问/对比 | `post_analysis_executor` | 有 `post-analysis` |
| `site_confidence_assessment_skill` | 官网 AI 友好度评估 | `site_confidence_assessment_executor` | 缺少自己的 package |

当前 package 映射只有：

```text
analysis_report_skill -> analysis-report
post_analysis_skill -> post-analysis
```

建议新增：

```text
site_confidence_assessment_skill -> site-confidence-assessment
```

## 9. 哪些文件已经清理或标记

这些旧文件看起来像运行时 prompt，但运行时代码已经不再加载，已从后端 prompt/package 目录中清理：

```text
aeo-platform/backend/prompts/marketing_persona_agent.md
aeo-platform/backend/prompts/question_simulation_agent.md
aeo-platform/backend/prompts/fetch_agent.md
aeo-platform/backend/prompts/data_analytics_agent.md
aeo-platform/backend/prompts/question_templates.yaml
aeo-platform/backend/app/workflow/a5/prompt.py
aeo-platform/backend/skill_packages/confidence-signal/SKILL.md
```

`general_react_agent.md` 没有删除，因为历史设计文档仍把它当作 A0 设计基线引用。但文件头部已经标记为：

```text
Legacy design baseline only
```

后续不要再把它当作运行时 orchestrator prompt 修改。

## 10. 后续建议

### 第一阶段：先收敛概念

做一张运行时映射表：

```text
能力名 -> Skill Definition -> Skill Contract -> Executor -> 活 prompt/代码 -> Artifact
```

### 第二阶段：清理旧 prompt

把不会被运行时加载的 prompt 文件标记为 legacy 或删除。

### 第三阶段：补官网 AI 友好度 package

新增：

```text
aeo-platform/backend/skill_packages/site-confidence-assessment/SKILL.md
```

并映射：

```text
site_confidence_assessment_skill -> site-confidence-assessment
```

这个 package 要明确：

- 这里评估的是 AI 默认抓取和理解友好度。
- 不是品牌真实可信度。
- 不是事实正确性盖章。
- 不是人工 SEO 审计。

### 第四阶段：修 A5 活路径

正向、中性、负向定义，0% 读数，混合正负事实，应该改在 A5 活模块里：

```text
a5/metrics.py
a5/sentiment.py
a5/diagnosis.py
a5/canonical.py
a5/postprocess.py
```

不要再优先改旧的 `a5/prompt.py`。

### 第五阶段：决定哪些 Node 值得升级成 SubAgent

优先候选：

- A3 问题模拟
- A4 失败恢复
- 后续分析

暂不建议优先升级：

- A2 画像生成
- A5 主报告编译
- 官网 AI 友好度评分

原因是这些更需要稳定 schema、可追踪、可复现，不适合一开始就放给自由 SubAgent。

## 11. 最终约定

以后讨论时建议这样说：

- A0 是 Orchestrator Agent。
- A1/A2/A3/A4/A5/A7 是 Workflow Stage。
- Node 是流程里的执行边界。
- Executor 是真正干活的代码。
- SubAgent 是 Node 内部未来可以采用的一种智能执行方式。
- Skill 是对外能力。
- Contract 是能力合同。
- SKILL.md 是能力说明。
- Tool 是可调用动作。
- Adapter 是平台适配器。
- Artifact 是正式产物。
- Memory/RAG 是历史知识和外部证据注入机制。

这样命名后，后续才不会再出现“改了 prompt，但实际没生效”的问题。
