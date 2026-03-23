# Skill Contract 与 Settings Create Skill 设计文档

> 版本：v1.0
> 日期：2026-03-21
> 状态：Draft
> 目的：作为 TODO 4「A5 / A7 / Follow-up 能力进一步 Skill 化」的设计依据，并为后续在设置页提供 `Create Skill` 能力打基础。

---

## 1. 一句话定义

本阶段不是把系统拆成很多零碎 skill，而是：

`把现有已经稳定、可复用、可交付的能力单元（A5 / A7 / Post Analysis）收敛成粗粒度 skill，并为后续在设置页创建新 skill 预留统一 contract。`

---

## 2. 为什么现在做 TODO 4

当前路线图前 3 项已经基本成立：

1. `Token / Cost / Latency 统一观测` 已上线主干。
2. `统一 Job Runtime` 已形成 durable task / run 主链。
3. `Knowledge Workspace` 已能支撑历史事实的检索、汇总、对比和导出。

因此现在最合理的下一步，就是把分析能力从“节点实现”提升成“平台能力单元”。

这一步的目标不是重写 A5/A7，而是：

1. 让 orchestrator 面向 skill 编排，而不是面向 node 名称编排。
2. 让后续客户后台可以配置“哪些客户启用哪些分析能力”。
3. 让未来新增能力以 skill 为单位进入系统，而不是继续把每个能力硬编码进 orchestrator。

---

## 3. 当前代码现状

### 3.1 A5 已经是半 Skill 化实现

现状：

1. 对外暴露能力名仍然是 `data_analytics`。
2. 对内已经拆出多个职责模块：
   - `metrics`
   - `prompt`
   - `contract`
   - `postprocess`
   - `sanitizer`
   - `persistence`

关键代码：

1. A5 主节点：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_a5.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_a5.py)
2. A5 内部模块：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/metrics.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/metrics.py)
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/prompt.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/prompt.py)
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/contract.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/contract.py)
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/postprocess.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/postprocess.py)
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/persistence.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a5/persistence.py)

结论：

`A5 不是没有 skill 基础，而是还没有被平台显式定义为 skill。`

### 3.2 A7 已经是独立分析能力

现状：

1. A7 不依赖重新抓取，只消费已有 A4 结果。
2. A7 已经是一个非常接近 skill 的独立能力单元。

关键代码：

1. A7 主节点：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_a7.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_a7.py)
2. A7 核心逻辑：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a7/confidence_signal.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/a7/confidence_signal.py)

结论：

`A7 非常适合作为一个独立 public skill。`

### 3.3 Follow-up 已经具备“后续任务”特征

现状：

1. Follow-up 并不是重新跑整条主链。
2. 它本质上是在已有结果上继续执行二次任务。
3. 目前包含：
   - `drill_down`
   - `compare_snapshots`
   - `selective_refetch`

关键代码：

1. Follow-up 节点：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_followup.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/nodes_followup.py)

结论：

`Follow-up 不适合继续以“散节点”存在，更适合被收敛为一个粗粒度的 post-analysis skill。`

### 3.4 当前 orchestrator 仍然直接耦合工具名与节点名

现状：

1. tool registry 写在 orchestrator 内部。
2. 当前工具名本质上仍然直接映射到节点实现。
3. skill metadata 还没有独立成平台对象。

关键代码：

1. orchestrator registry 与 routing：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/orchestrator_node.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/orchestrator_node.py)
2. workflow graph：
   - [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/graph.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/graph.py)

结论：

`现有系统已经有“能力编排”雏形，但还没有显式的 skill contract 层。`

---

## 4. 设计原则

### 原则 1：Skill 要粗粒度，不要碎

Skill 应该是：

1. 用户能理解的业务能力
2. orchestrator 容易选择的能力
3. 后台易于配置和观测的能力

Skill 不应该是：

1. 内部实现模块
2. prompt 片段
3. 数据清洗步骤
4. 每个细小工具函数

因此第一阶段不采用：

- `metrics_skill`
- `prompt_skill`
- `sanitizer_skill`
- `citation_domain_skill`

这种过度细化的定义。

### 原则 2：Public Skill 与 Private Substep 分层

第一阶段采用两层结构：

1. `Public Skills`
   orchestrator、设置页、后续后台直接看到和配置的能力。
2. `Private Substeps`
   skill 内部执行阶段，不对 orchestrator 直接暴露。

### 原则 3：Knowledge Workspace 是能力底座，不是第一阶段 public skill

`knowledge_lookup / aggregate / compare / export` 当前更像：

1. orchestrator 的材料操作层
2. skill 的事实读取层

它们不应在第一阶段就全部提升成 public skill，否则能力空间会再次碎片化。

### 原则 4：Create Skill 第一阶段不是自由代码执行

设置页里的 `Create Skill` 不应一开始就支持：

1. 任意 Python
2. 任意 workflow graph
3. 任意系统级工具组合

第一阶段只支持：

1. 在现有 skill executor 之上创建“配置化 skill”
2. 通过参数、适用范围、提示语、默认策略去扩展能力

---

## 5. 第一阶段建议的 Public Skills

第一阶段先只定义 3 个 public skill。

### 5.1 `analysis_report_skill`

对应现有：

- A5 / `data_analytics`

作用：

1. 基于已有抓取结果生成完整分析报告
2. 产出结构化 report artifact
3. 为 dashboard 和后续 post-analysis 提供分析基座

内部 substeps：

1. 确定性 metrics 计算
2. prompt 组装
3. LLM 报告生成
4. report postprocess / sanitize
5. artifact persistence

### 5.2 `confidence_signal_skill`

对应现有：

- A7 / `citation_confidence_analysis`

作用：

1. 基于已有引用和抓取结果生成置信度分析
2. 产出 confidence signal artifact

内部 substeps：

1. citation feature gathering
2. AICE 评分
3. confidence signal artifact 组装
4. artifact persistence

### 5.3 `post_analysis_skill`

对应现有：

- follow-up nodes

作用：

1. 在已有分析结果之上继续做任务
2. 适用于深挖、对比、局部重抓、后续解释

内部 substeps：

1. `drill_down`
2. `compare_snapshots`
3. `selective_refetch`

说明：

这里不再使用 `follow-up` 作为对外 skill 名称，因为它语义太泛。

---

## 6. Skill Contract 设计

第一阶段先定义统一 contract，但不要求一次性做成完整后台配置系统。

建议 skill contract 至少包含：

```json
{
  "skill_key": "analysis_report_skill",
  "display_name": "分析报告",
  "description": "基于已有抓取结果生成完整分析报告",
  "executor_kind": "builtin",
  "executor_ref": "a5_data_analytics",
  "intent_signals": ["生成报告", "整体分析", "完整总结"],
  "prerequisites": {
    "requires_fetch_results": true
  },
  "artifact_types": ["report"],
  "cost_class": "medium",
  "latency_class": "medium",
  "confirmation_policy": "auto",
  "enabled": true,
  "version": 1
}
```

### 必备字段

1. `skill_key`
   系统唯一标识
2. `display_name`
   用户和后台可见名称
3. `description`
   用于 orchestrator 选择和后台展示
4. `executor_kind`
   第一阶段先只支持 `builtin`
5. `executor_ref`
   绑定现有 executor，如 `a5_data_analytics`
6. `intent_signals`
   供 orchestrator 规划时参考的语义描述
7. `prerequisites`
   如是否要求 `fetch_results`、是否要求已有 report
8. `artifact_types`
   可能产出的 artifact 类型
9. `cost_class`
10. `latency_class`
11. `confirmation_policy`
12. `enabled`
13. `version`

### 第二阶段可扩展字段

1. `tenant_overrides`
2. `entity_scope`
3. `default_args`
4. `prompt_overlay`
5. `degradation_policy`
6. `allowed_models`

---

## 7. Orchestrator 如何选择 Skill

第一阶段不需要让 orchestrator 直接理解很多 skill。

目标是：

1. skill 数量少
2. skill 描述清晰
3. orchestrator 先选粗粒度 skill
4. skill 内部再决定具体子动作

### 路由逻辑

建议顺序：

1. 用户意图判断
2. 当前状态摘要
3. skill 选择
4. skill executor 内部分发

例如：

1. “给我出一份完整报告”
   - `analysis_report_skill`
2. “这些引用靠不靠谱”
   - `confidence_signal_skill`
3. “最近两次哪些平台变化最大”
   - `post_analysis_skill`
4. “只重抓 DeepSeek”
   - `post_analysis_skill`

### 关键点

`post_analysis_skill` 不要求 orchestrator 知道内部到底是 compare、drill_down 还是 selective_refetch。

外层只需判断：

`这是一次已有分析结果上的后续任务。`

然后 skill 内部再进行子路径判断。

---

## 8. 第一阶段建议的技术实现

### 8.1 不推翻现有节点

第一阶段不重写：

1. A5 node
2. A7 node
3. follow-up nodes
4. graph 主结构

而是在它们外面补一层：

1. `skill_registry`
2. `skill_contract`
3. `skill_router`

### 8.2 映射关系

建议：

- `analysis_report_skill` -> `a5_analytics`
- `confidence_signal_skill` -> `a7_confidence_signal`
- `post_analysis_skill` -> follow-up executor

其中：

- A5 / A7 先直接绑定现有 node
- `post_analysis_skill` 内部再基于 args 映射：
  - `drill_down`
  - `compare_snapshots`
  - `selective_refetch`

### 8.3 状态层不立即大改

当前 [D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/state.py](D:/AGEO/.codex-main-merge/aeo-platform/backend/app/workflow/state.py) 仍然是 node-output 导向。

第一阶段不建议重写整套 state。

建议做法：

1. 先增加 skill 执行元信息：
   - `current_skill`
   - `last_skill_result`
   - `skill_history`
2. 现有 `metrics / report / knowledge_*_result` 先保留
3. 第二阶段再逐步把 node-output 抬升成 skill-output

---

## 9. Settings 中的 Create Skill

### 9.1 定位

你提出的方向是正确的：

`Create Skill` 可以先放在当前设置页，作为轻量 control plane 入口，后续再迁移到大后台。`

这意味着第一阶段 Settings 不是完整后台，但可以承担：

1. skill 列表查看
2. 开关启停
3. 新建 skill
4. 版本管理的最小闭环

### 9.2 为什么先放设置页

原因：

1. 当前已经有设置页入口：
   - [D:/AGEO/.codex-main-merge/frontend/src/app/settings/page.tsx](D:/AGEO/.codex-main-merge/frontend/src/app/settings/page.tsx)
2. 第一期的 skill 管理不需要完整客户运营后台也能成立
3. 这能提前验证：
   - skill contract 是否合理
   - 配置化 skill 是否好用
   - orchestrator 是否能消费配置化 skill

### 9.3 第一阶段 Create Skill 能做什么

第一阶段建议只支持“基于现有 executor 的配置化新 skill”。

允许：

1. 选择一个基础 executor
   - `analysis_report_skill`
   - `confidence_signal_skill`
   - `post_analysis_skill`
2. 定义 skill 名称
3. 定义 skill 描述
4. 设定默认参数
5. 设定适用范围
6. 设定是否启用
7. 设定提示语增强（prompt overlay）

不允许：

1. 任意代码
2. 任意系统命令
3. 任意 graph 编排
4. 自定义数据库读写逻辑

### 9.4 为什么不支持自由代码

因为第一阶段目标是：

1. 扩展能力
2. 保持稳定
3. 保持可观测
4. 保持可审计

自由代码会立刻带来：

1. 安全风险
2. runtime 风险
3. 观测失真
4. skill 边界失控

因此第一阶段 Create Skill 应该理解为：

`基于现有能力模板创建新 skill，而不是脚本市场。`

### 9.5 建议的数据模型

建议至少有 3 张表：

1. `skill_definitions`
   - skill 的逻辑定义
2. `skill_versions`
   - 每次变更后的版本快照
3. `skill_assignments`
   - 哪个客户 / 哪个 entity / 哪个 workspace 启用了哪些 skill

第一阶段字段示例：

#### `skill_definitions`

1. `id`
2. `skill_key`
3. `display_name`
4. `description`
5. `base_executor_ref`
6. `enabled`
7. `created_by`
8. `created_at`
9. `updated_at`

#### `skill_versions`

1. `id`
2. `skill_id`
3. `version`
4. `contract_json`
5. `prompt_overlay`
6. `default_args_json`
7. `change_note`
8. `created_at`

#### `skill_assignments`

1. `id`
2. `skill_id`
3. `scope_type`
4. `scope_ref`
5. `enabled`
6. `created_at`

### 9.6 Settings 页的 UI 建议

第一阶段先做一个轻量 section：

`设置 -> Skills`

建议包含：

1. `Skill 列表`
   - 名称
   - 说明
   - 基础 executor
   - 当前版本
   - 启用状态
2. `Create Skill`
   - 选择基础 skill 模板
   - 输入 skill 名称
   - 输入 skill 描述
   - 配置默认参数
   - 配置 prompt overlay
3. `Publish / Disable`
4. `View Version`

---

## 10. 第一阶段实施顺序

### Phase 4.1：先建立 Skill Contract 层

目标：

1. 定义 `skill_registry`
2. 把 A5 / A7 / post-analysis 映射进去
3. 不改用户行为

### Phase 4.2：让 orchestrator 选 skill

目标：

1. orchestrator 先面向粗粒度 skill 选择
2. skill executor 再路由到现有 node

### Phase 4.3：设置页加入 Skills Section

目标：

1. 查看 skill
2. 创建配置化 skill
3. 启停 skill

### Phase 4.4：为未来后台迁移留接口

目标：

1. skill 定义不绑定 settings page
2. settings 只是第一阶段 UI 壳
3. 后续大后台可直接接管 skill definition

---

## 11. 风险与边界

### 风险 1：过度细化

如果 skill 拆太细，会导致：

1. orchestrator 选择困难
2. prompt/context 膨胀
3. 后台配置失控

因此第一阶段强制只保留 3 个 public skills。

### 风险 2：Create Skill 过早自由化

如果第一阶段允许自由代码 / 自由 graph：

1. 系统稳定性会快速下降
2. 控制面会在后台出现大量不可控配置

因此必须从“模板化、配置化”起步。

### 风险 3：state 与 skill 输出长期分裂

如果 skill contract 建了，但 state 还是完全 node-output 导向，后面会有双轨系统。

因此第一阶段虽然不重写 state，但需要预留 `current_skill / skill_history / last_skill_result` 这类字段。

---

## 12. 验收标准

第一阶段验收标准建议如下：

1. orchestrator 可以面向 `analysis_report_skill / confidence_signal_skill / post_analysis_skill` 做选择。
2. 现有 A5/A7/follow-up 行为不回退。
3. Skill registry 可独立定义这 3 个 public skills。
4. Settings 页中可看到 skill 列表。
5. Settings 页可以基于已有 executor 创建一个新的配置化 skill。
6. skill 的启停、版本和默认参数能够持久化。
7. skill 级别的观测（调用次数、token、耗时、成本）能够复用现有 observability 基础。

---

## 13. 当前建议结论

当前推荐路线是：

1. 不把 skill 拆细。
2. 第一阶段只定义 3 个 public skills：
   - `analysis_report_skill`
   - `confidence_signal_skill`
   - `post_analysis_skill`
3. A5 / A7 / Follow-up 保持现有实现，先加 contract 和 registry。
4. `Create Skill` 先放到 Settings，做轻量 control plane。
5. 第一阶段的 Create Skill 只支持“基于已有 executor 的配置化 skill”，不支持自由代码。

这条路线既不会推翻已有代码，也能为后续客户后台和更丰富的 skill 扩展打下平台基础。
