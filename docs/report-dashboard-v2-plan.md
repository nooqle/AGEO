# Dashboard V2 设计规划

> 日期：2026-03-07
> 负责人：UX
> 协作：PM
> 影响文件：`frontend/src/components/dashboard/DashboardPage.tsx`、`frontend/src/components/dashboard/MonitoringTab.tsx`
> 目标：把 Dashboard 从“分数中心”改成“诊断 + 监测”面板

## 1. 本轮范围

本轮只冻结 Dashboard V2 的信息架构、KPI 定义、tab 结构和数据需求，不处理后端最终实现、监测引擎重构、快照 schema 迁移。

本轮必须完成：

1. 定义一级 tab：`总览`、`场景`、`竞品争夺`、`信息源`、`风险与动作`、`监测`
2. 重做顶部 KPI 说明，移除 `BWVS` / `声量份额` 的首页主叙事
3. 定义 `场景` tab 的表格列结构
4. 定义 `竞品争夺` tab 的矩阵结构
5. 定义 `风险与动作` tab 的卡片结构
6. 确认 `MonitoringTab` 保持原职责，只调整入口与上下文

## 2. 当前实现与改造原因

当前 `DashboardPage.tsx` 仍是旧版结构：

- 一级 tab：`可见度`、`平台对比`、`来源分布`、`AEO 指标`、`优化建议`、`监测`
- 顶部 KPI：`品牌可见度(BWVS)`、`提及率`、`声量份额`、`品牌数量`
- 主问题导向仍然是“分数是多少”，不是“哪里有问题、该做什么”

当前 `MonitoringTab.tsx` 已经是独立监测面板，包含：

- 计划状态
- baseline 信息
- 趋势图
- 指标变化
- 告警
- 运行历史

因此 V2 的正确做法不是重写监测，而是：

- 在 Dashboard 首页把“诊断”放到前面
- 让 Monitoring 变成“持续跟踪入口”
- 只调整 `MonitoringTab` 的文案和上下文，不改其核心职责

## 3. Dashboard IA

Dashboard V2 一级 tab 顺序冻结如下：

| 顺序 | Tab | 角色 | 用户问题 |
| --- | --- | --- | --- |
| 1 | `总览` | 首页诊断摘要 | 现在整体状态如何，先看什么 |
| 2 | `场景` | 主工作面 | 哪些场景有效，哪些场景缺席 |
| 3 | `竞品争夺` | 竞争占位分析 | 哪些竞品正在抢走关键场景 |
| 4 | `信息源` | 引用结构分析 | AI 在引用谁，官网有没有进入答案 |
| 5 | `风险与动作` | 决策与执行面 | 当前最大风险是什么，下一步做什么 |
| 6 | `监测` | 持续跟踪 | 后续如何定时追踪变化和告警 |

### 3.1 总体页面结构

Dashboard 首页从上到下建议为：

1. Hero / 品牌上下文
2. 顶部 KPI 区
3. `总览` tab 默认首屏
4. 其他 tab 作为二级工作区切换

### 3.2 总览 tab 内部模块

`总览` tab 不是旧版 KPI 的重复展示，而是 4 个模块：

1. `当前诊断摘要`
2. `重点场景机会`
3. `主要竞品压力`
4. `建议优先动作`

## 4. 顶部 KPI 卡定义

顶部 KPI 固定为 5 张卡，顺序不可变。

| 顺序 | 卡片标题 | 指标 ID | 回答的问题 | 主展示 | 辅助说明 | 趋势 | 点击后去向 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 品牌提及率 | `brand_mention_rate` | 品牌在 AI 回答中被提到的频率是多少 | 百分比 | 样本周期内被提及 / 总回答数 | 支持 | `场景` |
| 2 | 官网引用率 | `official_citation_rate` | AI 回答中引用官网的频率是多少 | 百分比 | 官网域名被引用 / 总回答数 | 支持 | `信息源` |
| 3 | 有效场景数 | `scenario_hit_count` | 当前已有哪些场景打进回答 | 数值 | 品牌出现的场景数 / 总场景数 | 支持 | `场景` |
| 4 | 缺席高价值场景数 | `missing_high_value_scenario_count` | 有多少高价值场景仍然缺席 | 数值 | 高价值且品牌缺席的场景数 | 支持 | `风险与动作` |
| 5 | 高风险场景数 | `high_risk_scenario_count` | 当前最需要优先处理的风险有多少 | 数值 | 严重度为 high 的场景数 | 支持 | `风险与动作` |

### 4.1 KPI 设计规则

1. KPI 标题用业务语言，不出现模型内部名词。
2. 首页不再展示 `BWVS` 为主卡；如需保留，只能作为 tooltip、二级详情或监测维度。
3. 每张 KPI 都要能指向一个后续工作面，避免“只看分不行动”。
4. subtitle 只解释口径，不做“优秀 / 良好 / 较差”标签。

### 4.2 KPI 映射到当前实现

`DashboardPage.tsx` 当前卡片里：

- `提及率` 可保留，但文案需改成 `品牌提及率`
- `BWVS` 主卡要降级
- `声量份额` 要从首页主 KPI 移除
- `品牌数量` 不属于诊断 KPI，应从顶部 KPI 区移出

## 5. 各 Tab 数据需求表

以下表格用于 UX、PM、前端和后端对齐字段。`现状` 仅标记当前前端/接口是否已有近似数据，不代表最终字段已满足。

### 5.1 总览

#### 信息结构

`总览` tab 展示 4 个区块：

1. 诊断摘要条
2. 重点场景列表
3. 竞品压力摘要
4. 动作建议摘要

#### 数据需求表

| 区块 | 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- | --- |
| 诊断摘要条 | `brand_mention_rate` | 是 | 已有近似值 | 对应当前 `kpi.mentionRate` |
| 诊断摘要条 | `official_citation_rate` | 是 | 缺失 | 需要新增官网引用口径 |
| 诊断摘要条 | `scenario_hit_count` | 是 | 缺失 | 需要场景聚合 |
| 诊断摘要条 | `missing_high_value_scenario_count` | 是 | 缺失 | 需要高价值场景标记 |
| 诊断摘要条 | `high_risk_scenario_count` | 是 | 缺失 | 需要风险聚合 |
| 重点场景列表 | `scenario_id` | 是 | 缺失 | 场景唯一标识 |
| 重点场景列表 | `scenario_label` | 是 | 缺失 | 场景名称 |
| 重点场景列表 | `scenario_priority` | 是 | 缺失 | high / medium / low |
| 重点场景列表 | `brand_present` | 是 | 缺失 | 是否出现 |
| 重点场景列表 | `official_citation_present` | 是 | 缺失 | 是否出现官网引用 |
| 重点场景列表 | `battle_status` | 是 | 缺失 | advantage / defend / contested / missing |
| 重点场景列表 | `top_competitor` | 否 | 缺失 | 该场景最强竞品 |
| 竞品压力摘要 | `competitor` | 是 | 已有近似值 | 当前 `competitors[]` 可复用部分信息 |
| 竞品压力摘要 | `shared_scenarios` | 是 | 缺失 | 需要场景级统计 |
| 竞品压力摘要 | `competitor_only_scenarios` | 是 | 缺失 | 需要场景级统计 |
| 竞品压力摘要 | `top_conflict_scenarios` | 是 | 缺失 | 用于摘要展示 |
| 动作建议摘要 | `priority` | 是 | 已有弱相关 | 现有 `optimizations[]` 不能直接满足 |
| 动作建议摘要 | `scenario_label` | 是 | 缺失 | 动作必须绑场景 |
| 动作建议摘要 | `action` | 是 | 缺失 | 推荐动作 |
| 动作建议摘要 | `target` | 是 | 缺失 | 目标改善项 |

### 5.2 场景

#### 表格定位

`场景` tab 是 Dashboard V2 的主工作面。默认按 `scenario_priority desc`、`risk_level desc` 排序。

#### 列结构冻结

| 列顺序 | 列名 | 字段 | 类型 | 说明 |
| --- | --- | --- | --- | --- |
| 1 | 场景 | `scenario_label` | 文本 | 主标题，可点击进入详情 |
| 2 | 优先级 | `scenario_priority` | badge | high / medium / low |
| 3 | 品牌出现 | `brand_present` | 布尔状态 | 是 / 否 |
| 4 | 出现平台 | `present_platforms` | tags | DeepSeek / Kimi / 豆包 / 混元 |
| 5 | 官网引用 | `official_citation_present` | 布尔状态 | 是 / 否 |
| 6 | 主要竞品 | `competitors_present` | tags | 最多展示 2-3 个，更多折叠 |
| 7 | 当前胜者 | `winner_brands` | 文本 / tags | 当前最稳定出现品牌 |
| 8 | 场景状态 | `battle_status` | badge | advantage / defend / contested / missing |
| 9 | 风险等级 | `risk_level` | badge | high / medium / low |
| 10 | 建议动作 | `action_hint` | 文本 | 一句话 next step |

#### 行展开详情

点击行后展开：

- `evidence`
- `official_sources`
- `query_examples`
- `recent_changes`

这些字段不进主表，避免表格过宽。

#### 数据需求表

| 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- |
| `scenario_id` | 是 | 缺失 | 场景主键 |
| `scenario_label` | 是 | 缺失 | 场景名称 |
| `scenario_priority` | 是 | 缺失 | 业务优先级 |
| `brand_present` | 是 | 缺失 | 当前品牌是否进入回答 |
| `present_platforms` | 是 | 缺失 | 品牌在哪些平台被提及 |
| `official_citation_present` | 是 | 缺失 | 官网是否被引用 |
| `official_sources` | 否 | 缺失 | 实际引用域名明细 |
| `competitors_present` | 是 | 缺失 | 同场景出现的竞品 |
| `winner_brands` | 是 | 缺失 | 最终胜出品牌 |
| `battle_status` | 是 | 缺失 | 场景状态 |
| `risk_level` | 是 | 缺失 | 风险严重度 |
| `action_hint` | 是 | 缺失 | 一句话建议 |
| `evidence` | 否 | 缺失 | 引用样本 / 解释文案 |
| `query_examples` | 否 | 缺失 | 触发该场景的 query 示例 |
| `recent_changes` | 否 | 缺失 | 和前周期对比变化 |

### 5.3 竞品争夺

#### 矩阵结构冻结

`竞品争夺` tab 采用“两层结构”：

1. 顶部竞品摘要卡
2. 底部场景争夺矩阵

#### 顶部竞品摘要卡

每个竞品一张卡，显示：

- `competitor`
- `shared_scenarios`
- `competitor_only_scenarios`
- `brand_only_scenarios`
- `pressure_level`
- `top_conflict_scenarios`

#### 底部场景争夺矩阵

矩阵定义如下：

- 行：高价值场景，按 `scenario_priority desc` 排序
- 列：`本品牌` + Top N 竞品
- 单元格状态：
  - `win`：该品牌是主要胜者
  - `present`：出现但不是主胜者
  - `absent`：未出现
  - `official_cited`：该品牌官网被引用，作为 cell 角标
- 右侧补充列：
  - `winner_brand`
  - `battle_status`
  - `recommended_focus`

这比单纯排行榜更适合回答“谁在抢哪些场景”。

#### 数据需求表

| 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- |
| `competitor` | 是 | 已有近似值 | 现有 `competitors[]` 只有品牌级聚合，不够 |
| `shared_scenarios` | 是 | 缺失 | 品牌与竞品同时出现的场景数 |
| `competitor_only_scenarios` | 是 | 缺失 | 竞品出现、品牌缺席 |
| `brand_only_scenarios` | 是 | 缺失 | 品牌出现、竞品缺席 |
| `top_conflict_scenarios` | 是 | 缺失 | 需要列出重点争夺场景 |
| `pressure_level` | 否 | 缺失 | 可由计数派生 |
| `scenario_matrix` | 是 | 缺失 | 场景 x 品牌矩阵主数据 |
| `scenario_matrix[].scenario_id` | 是 | 缺失 | 行主键 |
| `scenario_matrix[].scenario_label` | 是 | 缺失 | 行名称 |
| `scenario_matrix[].competitor_states` | 是 | 缺失 | 各品牌在该场景的状态集合 |
| `scenario_matrix[].winner_brand` | 是 | 缺失 | 当前主胜者 |
| `scenario_matrix[].battle_status` | 是 | 缺失 | 场景状态 |
| `scenario_matrix[].recommended_focus` | 否 | 缺失 | 给业务的一句话建议 |

### 5.4 信息源

#### 信息结构

`信息源` tab 保持“来源分析”职责，但从“来源分布”升级为“官网引用能力 + 域名结构分析”。

建议由 3 个区块组成：

1. 官网引用摘要
2. Top domains 列表
3. 平台级引用差异

#### 数据需求表

| 区块 | 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- | --- |
| 官网引用摘要 | `official_citation_rate` | 是 | 缺失 | 首页 KPI 同源 |
| 官网引用摘要 | `official_citation_trend` | 否 | 缺失 | 用于趋势标记 |
| 官网引用摘要 | `official_domain` | 是 | 缺失 | 当前品牌官网域名 |
| Top domains 列表 | `top_domains[].domain` | 是 | 现有弱相关 | 现有 `sources[]` 只有 source/count/percentage |
| Top domains 列表 | `top_domains[].count` | 是 | 已有近似值 | 可由现有数据演进 |
| Top domains 列表 | `top_domains[].percentage` | 是 | 已有近似值 | 可由现有数据演进 |
| Top domains 列表 | `top_domains[].is_official` | 是 | 缺失 | 标记是否官网 |
| 平台级引用差异 | `platform_citation_stats[].platform` | 是 | 缺失 | DeepSeek / Kimi / 豆包 / 混元 |
| 平台级引用差异 | `platform_citation_stats[].official_citation_rate` | 是 | 缺失 | 平台级官网引用率 |
| 平台级引用差异 | `platform_citation_stats[].top_domains` | 是 | 缺失 | 平台常见引用域名 |
| 平台级引用差异 | `platform_citation_stats[].citation_style` | 否 | 缺失 | 例如“偏新闻站/偏百科/偏官网” |

### 5.5 风险与动作

#### 卡片结构冻结

`风险与动作` tab 采用左右两列：

- 左列：风险卡片流
- 右列：动作卡片流

不做大表格，避免用户在决策页回到“读表模式”。

#### 风险卡片结构

每张风险卡必须包含：

1. `severity` badge
2. `risk_type` 标签
3. `scenario_label`
4. `reason`
5. `impact_summary`
6. `evidence`
7. `recommended_action_ref`

推荐风险类型：

- `missing_presence`
- `competitor_substitution`
- `no_official_citation`
- `weak_presence`

#### 动作卡片结构

每张动作卡必须包含：

1. `priority`
2. `scenario_label`
3. `action`
4. `target`
5. `expected_metric`
6. `related_competitors`
7. `status`

动作卡默认按 `priority asc` 排序，并且必须和左侧风险形成关联。

#### 数据需求表

| 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- |
| `risks[]` | 是 | 缺失 | 风险卡片集合 |
| `risks[].risk_id` | 是 | 缺失 | 卡片主键 |
| `risks[].risk_type` | 是 | 缺失 | 风险分类 |
| `risks[].scenario_label` | 是 | 缺失 | 绑定场景 |
| `risks[].severity` | 是 | 缺失 | high / medium / low |
| `risks[].reason` | 是 | 缺失 | 风险解释 |
| `risks[].impact_summary` | 是 | 缺失 | 影响摘要 |
| `risks[].evidence` | 否 | 缺失 | 证据 |
| `risks[].recommended_action_ref` | 否 | 缺失 | 指向动作 ID |
| `actions[]` | 是 | 缺失 | 动作卡片集合 |
| `actions[].action_id` | 是 | 缺失 | 卡片主键 |
| `actions[].priority` | 是 | 缺失 | 1 / 2 / 3 或 high / medium / low |
| `actions[].scenario_label` | 是 | 缺失 | 动作绑定场景 |
| `actions[].action` | 是 | 缺失 | 建议动作 |
| `actions[].target` | 是 | 缺失 | 目标改善点 |
| `actions[].expected_metric` | 否 | 缺失 | 期望改善的指标 |
| `actions[].related_competitors` | 否 | 缺失 | 相关竞品 |
| `actions[].status` | 否 | 缺失 | not_started / in_progress / done |

### 5.6 监测

#### 职责确认

`MonitoringTab` 保持原职责，不重构其内部核心逻辑：

1. 定时运行
2. 趋势追踪
3. 告警
4. 历史记录

#### V2 只做两类调整

1. Dashboard 入口语义调整
2. 文案上下文调整

#### 入口与上下文要求

- tab 名称仍为 `监测`
- 在 IA 上放到最后，表示“持续跟踪”，而不是“先看监测”
- 空态文案从“跟踪 BWVS 分数”改成“跟踪品牌提及率、官网引用率、关键风险与整体可见度变化”
- 如果用户从 `风险与动作` 或 `场景` 跳入监测，可带入当前品牌上下文；不要求场景级联动作为本轮必做

#### 数据需求表

| 区块 | 字段 | 必需 | 现状 | 说明 |
| --- | --- | --- | --- | --- |
| 计划状态 | `schedule` | 是 | 已有 | 当前已实现 |
| baseline 信息 | `baseline_summary` | 是 | 已有 | 当前已实现 |
| 趋势图 | `trendData` | 是 | 已有 | 当前已实现 |
| 趋势摘要 | `trendSummary` | 是 | 已有 | 当前已实现 |
| 指标变化 | `metricDeltas` | 是 | 已有 | 当前已实现 |
| 告警 | `alerts` | 是 | 已有 | 当前已实现 |
| 历史记录 | `runHistory` | 是 | 已有 | 当前已实现 |
| 上下文文案 | `monitoring_context_copy` | 否 | 缺失 | 前端文案层新增即可 |

## 6. 对前端文件的直接影响

### 6.1 `DashboardPage.tsx`

必须修改：

1. `TABS` 常量，替换为 V2 的 6 个 tab
2. `initialTab` 默认值改为 `overview` / `总览`
3. 顶部 KPI 卡内容与顺序
4. tab bar 标题和说明文案
5. 旧 tab 组件的承接策略

建议处理方式：

- `总览`、`场景`、`竞品争夺`、`风险与动作` 需要新组件
- `信息源` 可演进现有 `SourcesTab`
- `监测` 继续使用现有 `MonitoringTab`
- `BWVS` 从首页主卡移除，必要时作为 tooltip 或二级维度保留

### 6.2 `MonitoringTab.tsx`

必须保持：

1. `fetchSchedule`
2. `fetchTrendData`
3. `fetchTrendSummary`
4. `fetchMetricDeltas`
5. `fetchAlerts`
6. `fetchRunHistory`
7. pause / resume / update / delete / clear baseline 逻辑

只建议修改：

1. 空态描述文案
2. 监测 tab 在 Dashboard 中的上层说明
3. 若有需要，趋势维度命名从“分数中心”改成“诊断指标中心”

## 7. 非目标

本轮不处理：

1. `BWVS` 删除
2. 监测引擎重写
3. 后端 API 最终字段实现
4. 快照和 analytics schema 迁移
5. 场景级 drill-down 详情页

## 8. 交付物检查

本规划完成后，UX / PM / 前端应能直接回答以下问题：

1. Dashboard 一级 tab 是什么，顺序是什么
2. 顶部 KPI 为什么改，具体改成什么
3. `场景` tab 的表格每列放什么
4. `竞品争夺` tab 的矩阵怎么画
5. `风险与动作` tab 的卡片怎么组织
6. `MonitoringTab` 哪些保持不动，哪些只改入口和文案

满足以上 6 点，即可进入 UI 设计和前端拆分阶段。

## 9. Report V2 设计目标

> 负责人：UX
> 协作：PM
> 影响文件：`frontend/src/components/canvas/contents/ReportContent.tsx`
> 目标：把新版 Report 设计成“品牌战况报告”

Report V2 不再延续旧版多 tab 分析报告心智，而是切换为单页纵向阅读的战况报告。

本轮必须完成：

1. 定义模块 1 `品牌现状`
2. 定义模块 2 `有效场景`
3. 定义模块 3 `竞品争夺`
4. 定义模块 4 `缺口与风险`
5. 定义模块 5 `信息源分析`
6. 定义模块 6 `下一步优化`
7. 定义各模块的空态、缺数据态、部分数据态
8. 冻结模块标题文案与字段标签

对 `ReportContent.tsx` 的直接约束：

1. 顶部不再用 `BWVS` 作为 hero 开场。
2. 不再保留 `行业洞察`、`平台分析`、`语义词云` 作为主结构。
3. 页面主问题必须变成“现在战况如何、问题在哪、下一步做什么”。
4. 允许继续消费现有数据结构，但前端必须按 V2 模块重新组织。

## 10. 当前 Report 实现与改造原因

当前 `ReportContent.tsx` 仍是旧版多 tab 报告：

- `总览`
- `行业洞察`
- `平台分析`
- `竞品对比`
- `信息源分析`
- `语义词云`
- `优化建议`
- `风险提示`

当前实现存在 4 个问题：

1. 首屏仍由 `BWVS 指数` 驱动，和 V2 的“诊断优先”冲突。
2. 信息被拆散到多个 tab，用户无法顺着“战况 -> 场景 -> 风险 -> 动作”阅读。
3. `优化建议` 与 `风险提示` 分离，导致结论和动作断开。
4. `行业洞察`、`语义词云` 这类研究型内容过强，会稀释客户最关心的战况判断。

因此 Report V2 的正确方向不是继续堆 tab，而是把页面重组为 6 个固定模块。

## 11. Report V2 模块线框

### 11.1 页面级结构

```text
[Header]
- 标题：品牌战况报告
- 副标题：品牌名 + 分析周期 + 平台范围
- 辅助信息：最近更新时间 / 基线标记 / 降级说明

[模块 1 品牌现状]
- 核心战况指标
- 一句话结论
- 战况摘要

[模块 2 有效场景]
- 场景列表 / 卡片
- 回答：品牌是否进入回答、出现在哪些平台、官网是否被引用

[模块 3 竞品争夺]
- 竞品总览
- 关键争夺场景

[模块 4 缺口与风险]
- 风险列表
- 风险原因 + 证据

[模块 5 信息源分析]
- 官网引用率
- 被引用来源排行
- 平台级引用差异

[模块 6 下一步优化]
- 优先动作队列
- 每条动作绑定场景和目标
```

### 11.2 阅读顺序

固定顺序：

1. `品牌现状`
2. `有效场景`
3. `竞品争夺`
4. `缺口与风险`
5. `信息源分析`
6. `下一步优化`

理由：

- 先给总体判断
- 再给已有效的阵地
- 再给被争夺的阵地
- 再给风险暴露点
- 再给证据来源结构
- 最后收束到动作

### 11.3 模块级线框

#### 模块 1：品牌现状

```text
[标题 + 一句话结论]
[品牌提及率] [官网引用率] [覆盖平台数]
[有效场景数] [缺席高价值场景数] [高风险场景数]
[战况摘要说明]
```

#### 模块 2：有效场景

```text
[标题 + 说明]
[筛选：全部 / 已建立优势 / 有官网引用 / 多平台出现]
[场景列表]
- 场景
- 品牌出现
- 出现平台
- 官网被引用
- 判断依据
```

#### 模块 3：竞品争夺

```text
[标题 + 说明]
[竞品摘要卡]
- 共享场景
- 竞品独占场景
- 我方独占场景

[关键争夺场景列表]
- 场景
- 当前战况
- 主要竞品
- 当前占优品牌
- 判断依据
```

#### 模块 4：缺口与风险

```text
[标题 + 风险提示语]
[风险列表]
- 风险类型
- 涉及场景
- 风险等级
- 风险原因
- 证据
```

#### 模块 5：信息源分析

```text
[标题 + 说明]
[官网引用率主卡]
[被引用来源排行]
[平台引用差异]
[数据说明]
```

#### 模块 6：下一步优化

```text
[标题 + 行动说明]
[动作列表]
- 优先级
- 目标场景
- 建议动作
- 优化目标
- 相关竞品
```

## 12. 模块字段清单

### 12.1 模块 1：品牌现状

模块目标：
让用户在 15 秒内理解品牌当前整体战况。

必需字段：

- `brand_mention_rate`
- `official_citation_rate`
- `platform_coverage_count`
- `scenario_total`
- `scenario_hit_count`
- `missing_high_value_scenario_count`
- `high_risk_scenario_count`

派生字段：

- `scenario_effective_rate`
- `status_summary`

字段标签：

- `brand_mention_rate` -> `品牌提及率`
- `official_citation_rate` -> `官网引用率`
- `platform_coverage_count` -> `覆盖平台数`
- `scenario_hit_count` -> `有效场景数`
- `missing_high_value_scenario_count` -> `缺席高价值场景`
- `high_risk_scenario_count` -> `高风险场景`

一句话结论模板：

- `当前品牌已覆盖 {scenario_hit_count}/{scenario_total} 个场景，并在 {platform_coverage_count} 个平台中被提及，但仍有 {missing_high_value_scenario_count} 个高价值场景缺席。`

### 12.2 模块 2：有效场景

模块目标：
明确品牌已经建立有效存在感的场景。

必需字段：

- `scenario_id`
- `scenario_label`
- `brand_present`
- `present_platforms`
- `official_citation_present`
- `evidence`

可选字段：

- `platform_count`
- `official_source_domains`
- `confidence`

字段标签：

- `scenario_label` -> `场景`
- `brand_present` -> `品牌出现`
- `present_platforms` -> `出现平台`
- `official_citation_present` -> `官网被引用`
- `evidence` -> `判断依据`

行级文案：

- `brand_present = true` -> `已进入回答`
- `brand_present = false` -> `未进入回答`
- `official_citation_present = true` -> `有官网引用`
- `official_citation_present = false` -> `无官网引用`

### 12.3 模块 3：竞品争夺

模块目标：
回答哪些关键场景正在被竞品拿走。

必需字段：

- `scenario_label`
- `brand_present`
- `competitors_present`
- `winner_brands`
- `battle_status`
- `evidence`

推荐汇总字段：

- `shared_scenarios`
- `competitor_only_scenarios`
- `brand_only_scenarios`
- `top_conflict_scenarios`

字段标签：

- `competitors_present` -> `主要竞品`
- `winner_brands` -> `当前占优品牌`
- `battle_status` -> `当前战况`
- `evidence` -> `判断依据`

`battle_status` 映射：

- `advantage` -> `我方占优`
- `defend` -> `需要防守`
- `contested` -> `激烈争夺`
- `missing` -> `我方缺席`

### 12.4 模块 4：缺口与风险

模块目标：
快速指出当前最需要关注的问题。

必需字段：

- `risk_type`
- `scenario_label`
- `severity`
- `reason`
- `evidence`

字段标签：

- `risk_type` -> `风险类型`
- `scenario_label` -> `涉及场景`
- `severity` -> `风险等级`
- `reason` -> `风险原因`
- `evidence` -> `证据`

`risk_type` 映射：

- `missing_presence` -> `品牌缺席`
- `competitor_substitution` -> `竞品替代`
- `no_official_citation` -> `官网未被引用`
- `weak_presence` -> `品牌存在感弱`

`severity` 映射：

- `high` -> `高风险`
- `medium` -> `中风险`
- `low` -> `低风险`

### 12.5 模块 5：信息源分析

模块目标：
解释 AI 平台引用了哪些来源来形成判断。

必需字段：

- `official_citation_rate`
- `top_domains`
- `platform_citation_stats`

推荐补充字段：

- `total_citations`
- `unique_domains`
- `official_citations`
- `brand_domain`
- `note`

字段标签：

- `official_citation_rate` -> `官网引用率`
- `top_domains` -> `被引用来源`
- `platform_citation_stats` -> `平台引用差异`
- `official_citations` -> `官网引用次数`
- `unique_domains` -> `独立来源域名`

### 12.6 模块 6：下一步优化

模块目标：
把观察结果收束到明确动作。

必需字段：

- `priority`
- `scenario_label`
- `action`
- `target`
- `related_competitors`

推荐补充字段：

- `owner_hint`
- `expected_impact`
- `difficulty`

字段标签：

- `priority` -> `优先级`
- `scenario_label` -> `目标场景`
- `action` -> `建议动作`
- `target` -> `优化目标`
- `related_competitors` -> `相关竞品`

动作文案要求：

1. 动词开头。
2. 必须绑定具体场景。
3. 必须说明希望改善什么结果。

## 13. 各模块状态定义

### 13.1 全局规则

状态定义：

- 空态：该模块完全没有结构化数据。
- 缺数据态：有模块容器，但关键判断字段缺失。
- 部分数据态：主字段可用，但证据、平台、竞品或引用等补充字段不完整。
- 完整数据态：核心字段齐全，可支撑业务判断。

统一规则：

1. 不隐藏模块标题。
2. 模块顺序不因为数据缺失而变化。
3. 缺数据态和部分数据态都允许继续展示已有内容。
4. 文案优先说业务含义，不暴露技术字段名。

### 13.2 模块 1：品牌现状

空态：

- `本次分析尚未形成品牌现状摘要。`

缺数据态：

- 条件：`brand_mention_rate` 和 `official_citation_rate` 至少缺一。
- 文案：`当前仅拿到部分总览指标，暂时无法判断完整战况。`

部分数据态：

- 条件：核心指标已返回，但风险相关指标缺失。
- 文案：`已生成核心战况指标，风险侧数据仍在补充。`

### 13.3 模块 2：有效场景

空态：

- `暂无可确认的有效场景。完成场景分析后将展示品牌已建立优势的场景。`

缺数据态：

- 条件：只有 `scenario_label`，缺 `brand_present` 或 `present_platforms`。
- 文案：`场景列表已生成，但出现结果还不完整。`

部分数据态：

- 条件：场景和品牌出现结果可用，但官网引用或证据缺失。
- 文案：`已识别品牌出现的场景，官网引用和证据仍在补充。`

### 13.4 模块 3：竞品争夺

空态：

- `暂无可判断的竞品争夺数据。`

缺数据态：

- 条件：只有竞品名或场景名，缺 `battle_status`。
- 文案：`已识别相关竞品，但尚不足以判断争夺态势。`

部分数据态：

- 条件：`battle_status` 已返回，但 `winner_brands` 或 `evidence` 缺失。
- 文案：`已识别关键争夺场景，胜出判断依据仍在补充。`

### 13.5 模块 4：缺口与风险

空态：

- `当前未识别到明确风险，或风险数据尚未返回。`

缺数据态：

- 条件：只有 `risk_type`，缺 `scenario_label` 或 `severity`。
- 文案：`已发现潜在风险信号，但还不能确定风险级别和场景。`

部分数据态：

- 条件：风险类型和等级已返回，但证据缺失。
- 文案：`已定位风险方向，证据链仍在补充。`

### 13.6 模块 5：信息源分析

空态：

- `暂无引用来源数据。完成引用抓取后将展示 AI 平台引用了哪些来源。`

缺数据态：

- 条件：仅有 `official_citation_rate`，缺 `top_domains` 和 `platform_citation_stats`。
- 文案：`已得到官网引用率，但来源结构仍不完整。`

部分数据态：

- 条件：来源排行已返回，但平台差异不完整。
- 文案：`已识别主要引用来源，平台差异数据仍在补充。`

### 13.7 模块 6：下一步优化

空态：

- `暂无可执行优化动作。待风险和场景判断完成后自动生成。`

缺数据态：

- 条件：只有动作文案，缺 `scenario_label` 或 `target`。
- 文案：`已生成初步建议，但还未绑定到明确场景或目标。`

部分数据态：

- 条件：动作与场景已返回，但竞品背景缺失。
- 文案：`已形成动作建议，竞品背景仍在补充。`

## 14. 标题文案与字段标签规范

### 14.1 页面标题

主标题固定：

- `品牌战况报告`

副标题模板：

- `{brand_name} 在 {date_range} 的 AI 品牌战况分析`

辅助信息模板：

- `覆盖平台：{platform_list}`
- `最近更新：{updated_at}`
- `基线报告`

### 14.2 六个模块标题

推荐标题：

1. `品牌现状`
2. `有效场景`
3. `竞品争夺`
4. `缺口与风险`
5. `信息源分析`
6. `下一步优化`

推荐副标题：

1. `先看品牌当前在 AI 回答中的整体战况。`
2. `这些场景里，品牌已经建立了有效存在感。`
3. `这些关键场景里，品牌正在和竞品争夺用户心智。`
4. `这些缺口正在影响品牌被提及和被引用。`
5. `AI 平台正在引用哪些来源来形成回答。`
6. `优先处理这些动作，才能改善接下来的战况。`

### 14.3 文案风格规范

必须遵守：

1. 用业务结果语言，不用模型内部语言。
2. 用“品牌是否进入回答 / 官网是否被引用 / 场景是否被竞品占据”这类判断句。
3. 同一字段只保留一个稳定中文标签。
4. 风险和动作必须直接，不写空泛建议。

禁止用语：

- `综合分`
- `模型表现优秀`
- `算法判断`
- `语义表现`
- `推荐进一步观察`

推荐用语：

- `品牌提及率`
- `官网引用率`
- `我方缺席`
- `竞品占优`
- `高风险场景`
- `优先动作`

### 14.4 字段标签统一表

| 字段 | 固定中文标签 |
| --- | --- |
| `brand_mention_rate` | 品牌提及率 |
| `official_citation_rate` | 官网引用率 |
| `platform_coverage_count` | 覆盖平台数 |
| `scenario_total` | 场景总数 |
| `scenario_hit_count` | 有效场景数 |
| `missing_high_value_scenario_count` | 缺席高价值场景 |
| `high_risk_scenario_count` | 高风险场景 |
| `scenario_label` | 场景 |
| `brand_present` | 品牌出现 |
| `present_platforms` | 出现平台 |
| `official_citation_present` | 官网被引用 |
| `competitors_present` | 主要竞品 |
| `winner_brands` | 当前占优品牌 |
| `battle_status` | 当前战况 |
| `risk_type` | 风险类型 |
| `severity` | 风险等级 |
| `reason` | 风险原因 |
| `evidence` | 判断依据 |
| `top_domains` | 被引用来源 |
| `platform_citation_stats` | 平台引用差异 |
| `priority` | 优先级 |
| `action` | 建议动作 |
| `target` | 优化目标 |
| `related_competitors` | 相关竞品 |

## 15. 对 `ReportContent.tsx` 的落地建议

必须调整：

1. 将旧版 `TABS` 结构改为单页模块渲染。
2. 将旧版 `overview` 中的 `BWVS` hero 从主视图移除。
3. 将旧版 `competitors`、`citations`、`recommendations`、`risks` 数据重组映射到 V2 六模块。
4. 将旧版 `industry`、`platforms`、`semantics` 降级为可选附录或暂时移除。
5. 每个模块先支持“部分渲染”，不等待后端一次性补齐全部字段。

建议映射：

| 当前结构 | V2 去向 |
| --- | --- |
| `overview.metrics` | 模块 1 `品牌现状` |
| `competitor_deep_analysis` | 模块 3 `竞品争夺` |
| `risk_alerts` | 模块 4 `缺口与风险` |
| `citation_analysis` | 模块 5 `信息源分析` |
| `actionable_recommendations` / `action_plan` | 模块 6 `下一步优化` |

本节完成后，UX / PM / 前端应能直接回答：

1. Report 六个模块怎么排，为什么这么排
2. 每个模块具体放什么字段
3. 各模块在空态、缺数据态、部分数据态时怎么展示
4. `ReportContent.tsx` 哪些旧结构要删除、哪些数据可以复用
