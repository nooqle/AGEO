# Dashboard + 自动监测 + Chat 闭环设计讨论备忘

Date: 2026-04-30

## 1. 背景

近期围绕 A5 报告、Dashboard、自动监测和 Chat 的讨论，逐步形成了一个更清晰的产品方向：

Specta 不应该只把 Dashboard 当作“最近一份报告的摘要页”，也不应该只把自动监测当作一个定时跑报告的任务。更合理的产品形态是：

> Dashboard 是品牌在 AI 答案中的持续监测反馈界面；自动监测是按计划稳定采集和计算的后台执行能力；Chat 是配置、解释和干预这些监测能力的智能入口。

这份文档用于沉淀当前讨论结论，作为后续 Dashboard 和自动监测重构的设计依据。

## 2. 外部 GEO 监控大盘观察

用户提供的外部 GEO 监控平台截图体现出一个核心逻辑：

> 它展示的不是一份报告，而是一个固定监测口径下的周期数据反馈。

页面主要结构包括：

1. 顶部筛选条件
   - 品牌或监测对象
   - 时间范围
   - 平台范围
   - 问题来源或问题集范围

2. 顶部总览指标
   - 品牌得分
   - 对话次数
   - 提及次数
   - 提及率
   - 品牌曝光次数
   - Top1 / Top3 / Top10 提及率
   - 平均提及排名
   - 品牌推荐竞品

3. 平台表现卡
   - 每个 AI 平台或终端类型一张卡
   - 展示该平台内的对话次数、提及率、排名、提及好感度等
   - 用于判断哪个平台表现好，哪个平台需要治理

4. 趋势图表
   - 品牌得分趋势
   - 平均提及排名趋势
   - 品牌提及率趋势
   - 品牌提及次数趋势

5. 证据追溯
   - 引用来源
   - AI 对话记录

这类 Dashboard 的重点不是“本次报告写了什么”，而是回答：

- 当前周期内品牌有没有进入 AI 答案
- 进入频率高不高
- 排名靠不靠前
- 哪些平台更友好
- 是否出现竞品压制
- 数据变化趋势如何
- 原始证据在哪里

## 3. 当前 Specta Dashboard 的核心问题

当前 Dashboard 已经可以展示最近一轮报告，但存在一个产品定义问题：

> 最近一轮报告可能是品牌全景分析，也可能是用户场景分析。两者的问题集、样本口径和业务含义不同，如果只展示“最近报告”的指标，用户会不清楚这些数据代表什么。

已识别的问题：

1. Dashboard 的主对象不稳定
   - 当前页面容易让用户误以为“最近一份报告”就是品牌当前状态。
   - 但报告可能来自不同模式、不同问题集、不同平台范围。

2. 全景分析与用户场景分析不应混算
   - 全景分析更像品牌整体 AI 可见度健康度。
   - 用户场景分析更像某类业务决策场景下的品牌进入能力。
   - 两者指标可以有重叠，但解释不能混用。

3. 用户不知道指标从哪些问题来
   - 只看到提及率、官网引用率、风险顾虑等指标，不知道样本问题是什么。
   - 缺少“问题集 / 采样平台 / 时间周期 / 有效回答数”的上下文。

4. Dashboard 与自动监测尚未完全闭环
   - 自动监测应产出可聚合的监测快照，而不是只产出一份报告。
   - Dashboard 应能按时间范围统计多轮监测结果。

## 4. 产品目标

Dashboard 的目标应从：

> 展示最近一次 A5 报告

升级为：

> 展示某个品牌在某个周期、某个问题集、某些 AI 平台上的持续监测结果。

自动监测的目标应从：

> 定时触发一次分析

升级为：

> 按固定 Monitoring Plan 持续采集、计算、归档和告警。

Chat 的目标应从：

> 用户临时发起分析的对话入口

升级为：

> 创建监测计划、解释监测结果、调整问题集和触发复测的智能操作入口。

## 5. Dashboard 设计方向

### 5.1 主对象：周期监测结果

Dashboard 首页不应再以“最近报告”为核心定义，而应以“监测周期统计”为核心定义。

默认视图应表达：

- 当前品牌
- 当前分析模式
- 当前时间范围
- 当前平台范围
- 当前问题集
- 当前有效样本数
- 当前周期内的核心指标均值和趋势

最近报告仍然保留，但它应该是：

- 当前周期内某一次分析的入口
- 深度诊断报告的入口
- Dashboard 指标的证据来源之一

而不是 Dashboard 本身的定义。

### 5.2 全景监测与用户场景监测分离

建议在 Dashboard 内提供一级切换：

1. 全景监测
2. 用户场景监测

二者共用页面框架，但指标含义不同，不应混算。

全景监测侧重：

- 品牌提及率
- 平均推荐排名
- Top1 / Top3 / Top10 推荐率
- 官网引用率
- 竞品共现率
- 风险顾虑率
- 平台覆盖情况

用户场景监测侧重：

- 场景进入率
- 场景缺席率
- 哪些问题触发竞品
- 哪些问题触发风险顾虑
- 哪些场景适合优先建设内容资产
- 场景维度的官网引用率
- 场景维度的复测变化

### 5.3 顶部筛选与口径说明

Dashboard 顶部应固定展示或支持筛选：

- 品牌
- 分析模式：全景 / 用户场景
- 时间范围：近 7 天、近 30 天、自定义
- AI 来源范围：豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi网页版等
- 问题集：当前监测问题集
- 样本量：问题数、平台数、有效回答数

这能解决用户不知道“这些指标是什么问题问出来的”的问题。

### 5.4 核心指标区

全景监测下建议展示：

- 提及率
- 平均排名
- Top 推荐率
- 官网引用率
- 竞品压力
- 风险顾虑率

用户场景监测下建议展示：

- 场景进入率
- 高价值场景进入数
- 缺席高价值场景数
- 竞品替代场景数
- 风险顾虑场景数
- 官网引用覆盖率

指标应支持周期统计，优先用均值、最新值和趋势组合表达。

### 5.5 AI 平台表现区

每个平台应独立展示周期内表现，例如：

- 样本数
- 品牌提及率
- 平均排名
- 官网引用率
- 正向信号
- 风险顾虑
- 竞品共现
- 平台状态：优势 / 观察 / 风险 / 待观察

平台卡的价值是帮助用户快速判断：

- 哪个平台最值得优先优化
- 哪个平台已经建立优势
- 哪个平台存在品牌缺席或竞品替代

### 5.6 问题与场景表现区

Dashboard 应展示问题级和场景级反馈，而不是只展示抽象指标。

建议保留：

- 高风险问题
- 优势场景
- 品牌缺席问题
- 竞品替代问题
- 需要复测的问题

每个问题卡至少应包含：

- 触发问题
- 平台
- 场景
- 品牌状态
- 主要顾虑或缺席原因

### 5.7 趋势与证据追溯

周期监测 Dashboard 需要趋势能力：

- 提及率趋势
- 排名趋势
- 官网引用趋势
- 风险顾虑趋势
- 竞品共现趋势

同时需要证据追溯：

- 原始 AI 对话
- 引用来源
- 来源类型
- 问题样本
- 报告 artifact

## 6. 自动监测设计方向

### 6.1 自动监测不是一次 Chat 消息

自动监测不应被实现成“系统自动发起一条 Chat 消息”。

原因：

- 自动监测需要可重复
- 需要可暂停、修改、恢复
- 需要按固定计划执行
- 需要可审计
- 需要可被 Dashboard 聚合
- 不应依赖某一次 Chat 上下文是否还存在

因此自动监测应是独立的后台任务系统，但由 Chat 创建、解释和调整。

### 6.2 Monitoring Plan

建议引入或强化 Monitoring Plan 概念。

Monitoring Plan 应包含：

```json
{
  "brand_id": "brand_x",
  "monitor_mode": "panorama_monitoring | scenario_monitoring",
  "question_set_id": "question_set_x",
  "question_limit": 30,
  "platform_endpoints": [
    {
      "provider": "deepseek",
      "channel": "browser",
      "endpoint_id": "deepseek_browser",
      "display_name": "DeepSeek网页版"
    },
    {
      "provider": "doubao",
      "channel": "api",
      "endpoint_id": "doubao_api",
      "display_name": "豆包API"
    },
    {
      "provider": "doubao",
      "channel": "browser",
      "endpoint_id": "doubao_browser",
      "display_name": "豆包网页版"
    },
    {
      "provider": "yuanbao",
      "channel": "api",
      "endpoint_id": "yuanbao_api",
      "display_name": "元宝API"
    },
    {
      "provider": "yuanbao",
      "channel": "browser",
      "endpoint_id": "yuanbao_browser",
      "display_name": "元宝网页版"
    },
    {
      "provider": "kimi",
      "channel": "api",
      "endpoint_id": "kimi_api",
      "display_name": "Kimi API"
    },
    {
      "provider": "kimi",
      "channel": "browser",
      "endpoint_id": "kimi_browser",
      "display_name": "Kimi网页版"
    }
  ],
  "frequency": "daily | weekly | manual",
  "run_policy": "quick | full_browser",
  "generate_report": true,
  "alert_thresholds": {
    "mention_rate_drop": 0.15,
    "official_citation_drop": 0.2,
    "competitor_entry": true,
    "risk_concern_spike": true
  }
}
```

### 6.3 监测问题集

自动监测需要绑定明确的问题集。

问题集来源可以有三种：

1. 用户手动选择已有问题
2. Chat 根据品牌、行业和目标自动生成
3. 基于历史表现由系统建议新增或替换

Chat 自动生成的问题集必须经过用户确认后才能启用为正式 Monitoring Plan。确认前可以作为草稿问题集存在。

如果用户认为问题数量不足，Chat 应支持继续生成补充问题，并让用户选择追加、替换或合并。系统需要在保存计划前提示问题数量和预计执行成本。

单个 Monitoring Plan 的问题数量需要设置上限，当前建议暂定为 30 个问题。原因是自动监测会按问题数、AI 来源数和访问通道放大执行量，过大的问题集会增加超时、失败重试和报告生成压力。

问题集应分类型：

- 全景问题集
- 用户场景问题集

全景问题集用于监测品牌整体可见度。

用户场景问题集用于监测某类业务决策场景，例如：

- 家用 SUV 选型
- 数字化转型咨询选型
- 老人营养补充品选择
- 安全合规顾虑

### 6.4 快速监测、完整监测与前台 AI 来源名称

为了兼顾速度和完整性，自动监测可以支持两种执行策略：

1. 快速监测
   - 成本低
   - 速度快
   - 适合高频观察和内容调整后的快速复测
   - 可使用 API 通道和 DeepSeek 浏览器通道

2. 完整监测
   - 覆盖 DeepSeek、Kimi、豆包、元宝等目标平台
   - 以浏览器通道为主，尽量模拟真实用户在各 AI 产品中的问答结果
   - 适合正式周期报告和客户交付
   - 适合进入 Dashboard 的主周期统计

这两种策略应共享同一套 Monitoring Plan 和 Snapshot 结构，但 Snapshot 必须记录到具体 AI 来源，不能只记录平台名。

这里需要区分内部实现语言和用户可见语言。

内部可以记录：

- `provider`
- `channel`
- `endpoint_id`
- `display_name`

但 Dashboard 前台、筛选器、趋势图图例、平台表现卡和报告说明里，不应展示 `provider`、`channel`、`endpoint`、`browser` 这类内部语言。用户可见名称应使用清晰的 AI 来源标签，例如：

- 豆包API
- 豆包网页版
- DeepSeek网页版
- 元宝API
- 元宝网页版
- Kimi API
- Kimi网页版

这样趋势图和平台表现卡可以把“豆包API”和“豆包网页版”拆开展示，也可以在需要时按“豆包”汇总。默认不应把 API 与网页版结果混算后伪装成同一个来源，因为两者回答、引用和排名可能不同。

### 6.5 Monitoring Run 与 Snapshot

每次自动监测执行应产生：

- Monitoring Run：一次执行记录
- Monitoring Snapshot：可被 Dashboard 聚合的指标快照
- A5 Report Artifact：可打开查看的深度诊断报告
- Evidence Records：原始问题、平台回答、引用来源

Dashboard 优先读取 Snapshot 和结构化 artifact 字段，不应解析 Markdown。

## 7. Chat 与自动监测的关系

### 7.1 职责分工

Chat 的职责：

- 理解用户想监测什么
- 生成或修改监测问题集
- 解释为什么选这些问题
- 确认平台、周期、模式
- 创建或更新 Monitoring Plan
- 触发一次临时监测
- 解读监测结果
- 根据 Dashboard 异常继续追问分析

自动监测的职责：

- 按计划执行
- 调用 AI 平台采集答案
- 计算指标
- 写入 Snapshot
- 生成 Artifact
- 触发异常提醒
- 给 Dashboard 提供周期统计数据

Dashboard 的职责：

- 展示周期统计
- 展示平台差异
- 展示趋势变化
- 暴露异常和证据入口

报告的职责：

- 对单次或某周期结果进行深度诊断
- 输出高管版摘要和运营版诊断
- 提供行动建议

### 7.2 标准闭环

```text
Chat 对话
  ↓
生成 / 修改监测计划
  ↓
保存为 Monitoring Plan
  ↓
自动监测按计划执行
  ↓
生成 Monitoring Run + Snapshot + Artifact
  ↓
Dashboard 展示周期统计
  ↓
用户在 Chat 中追问、调整、复测
```

### 7.3 Chat 不是事实来源

Chat 不能直接凭对话上下文生成监测结论。

Chat 回答监测相关问题时，应优先读取：

- Monitoring Plan
- Monitoring Runs
- Monitoring Snapshots
- A5 Artifact 结构化字段
- 原始 AI 回答证据

例如用户问：

> 为什么这周 DeepSeek 提及率下降了？

Chat 应基于本周与上周的 Snapshot、问题集、平台回答、竞品进入情况和引用来源变化回答，而不是重新主观判断。

## 8. 当前共识原则

本阶段先形成产品共识，再进入实现。当前讨论已经形成以下原则：

1. Dashboard 应成为用户日常查看监测状态的主界面。

2. Chat 仍然是必要入口。新建品牌必须继续走现有 Chat 循环，完成品牌信息收集、分析目标确认和问题集生成确认。

3. Dashboard 不替代 Chat 的品牌创建和确认流程。Dashboard 的职责是承接已有品牌和已有监测上下文的日常查看、追问和干预入口。

4. 用户首次建立品牌监测时，应通过 Chat 完成关键确认，包括品牌、监测模式、问题集、AI 来源范围、频率和报告生成策略。

5. Dashboard 顶部可以提供 Chat 快速输入入口，但这个入口应绑定当前选中的品牌和监测上下文。

6. Dashboard 上的输入框不是内嵌聊天窗口，而是一个轻量 Command Bar。用户开始输入或提交后，页面进入完整 Chat 界面，并携带当前 Dashboard 上下文。

7. Chat 的监测回答必须基于 Monitoring Plan、Monitoring Run、Snapshot、A5 Artifact 和 Evidence Records，不能把对话上下文当作事实来源。

8. Dashboard 默认展示全景监测；如果品牌存在用户场景监测，Dashboard 应提供清晰切换能力。

9. DeepSeek 监测结果应进入 Dashboard 主指标，同时保留运行策略和平台来源标识，避免用户混淆快速监测与完整周期监测。

10. 自动监测每次运行都应生成完整 A5 报告。异常不替代报告，而是提示用户查看诊断、让 Chat 解释、调整问题集或触发复测。

11. 最近报告应改为“最新诊断报告”或类似入口，作为 Monitoring Run 的诊断详情，而不是 Dashboard 的主定义。

## 9. Dashboard 顶部 Chat 快速入口

### 9.1 产品定位

Dashboard 顶部输入框的定位应是：

> 针对当前品牌和当前监测视图发起一次智能操作。

它不是通用 AI 助手，也不是 Dashboard 内部的完整聊天区。它的价值是让用户在看到监测结果、趋势或异常时，可以快速把问题带入 Chat。

这个入口只服务于已有 Dashboard 上下文。对于新建品牌，Dashboard 不应绕过 Chat 循环直接创建监测计划，而应把用户带入现有 Chat 品牌创建流程。

建议微文案示例：

- `针对「理想汽车 · 全景监测」提问或调整监测...`
- `询问「家庭用车场景」的变化原因...`
- `让 Specta 解释当前监测异常...`

如果当前没有品牌或没有可用监测计划，输入区应切换成创建引导，例如：

- `先通过 Chat 建立品牌监测`
- `补充品牌信息并生成监测问题`
- `继续完成品牌监测设置`

### 9.2 页面位置

可以将当前 Dashboard 概览区域升级为“监测上下文 + 快速输入”区域。

该区域建议包含：

- 当前品牌或品牌选择器
- 当前监测模式：全景监测 / 用户场景监测
- 当前场景问题集（仅用户场景监测时展示）
- 时间范围和平台范围的轻量上下文
- Chat 快速输入框
- 少量快捷操作，例如解释变化、调整问题集、触发复测、创建场景监测

这样顶部区域不再只是展示“已管理几个品牌、完成几次分析”的静态统计，而是成为进入监测闭环的操作入口。

如果用户选择“新建品牌”或当前没有品牌，顶部区域应展示进入 Chat 的创建入口，而不是展示监测指标。新品牌必须先完成 Chat 循环，至少收集品牌信息，并让用户确认生成的问题集后，才能启用监测计划。

### 9.3 上下文传递

当用户从 Dashboard 输入并进入 Chat 时，Chat 应自动携带：

- `brand_id`
- `monitor_mode`
- `monitoring_plan_id`
- `question_set_id`
- `time_range`
- `platform_endpoints`
- 当前选中的指标、异常或问题卡上下文（如果由具体卡片触发）
- 用户在 Dashboard 输入的原始文本

进入 Chat 后，系统不应重新询问已知上下文。Chat 首条响应应明确它正在基于哪个品牌、模式、时间范围和平台范围工作。

如果是新建品牌入口，则不传伪造的监测上下文，只传入口来源和用户原始意图，让现有 Chat 循环按品牌创建逻辑继续推进。

### 9.4 与异常卡的关系

Dashboard 中的异常卡、平台卡、问题卡和报告入口，都可以复用同一条 Chat 进入路径。

示例：

- 用户点击 DeepSeek 提及率下降异常的“让 Chat 分析”
- 系统进入 Chat，并携带 `alert_id`、指标名称、当前周期、对比周期和相关 Evidence Records
- Chat 基于事实解释原因，并给出可执行处理建议

这能保持一个统一原则：

> Dashboard 暴露事实和异常，Chat 承接解释和操作。

### 9.5 不应做成什么

该入口不应做成：

- Dashboard 内展开的完整聊天窗口
- 与当前品牌无关的通用 Ask anything
- 只把用户文本传给 Chat、不传 Dashboard 上下文的跳转入口
- 用 Chat 临时生成监测结论、绕过 Snapshot 和 Evidence 的捷径

## 10. 建议实施路径

### P0：先修 Dashboard 定义

目标：让 Dashboard 不再只代表“最近报告”。

建议事项：

- 增加全景 / 用户场景切换
- 增加时间范围筛选
- 增加平台筛选
- 明确展示当前问题集与样本量
- 顶部增加绑定当前品牌和监测上下文的 Chat 快速输入入口
- 最近报告改为最新诊断报告入口，不作为页面主定义
- 后端提供周期聚合接口或扩展现有 Dashboard Home 数据结构

### P1：强化自动监测计划

目标：让自动监测从定时任务升级为可配置 Monitoring Plan。

建议事项：

- 支持问题集选择
- 支持 Chat 生成监测问题集
- 自动生成的问题集必须经用户确认后启用
- 支持继续生成补充问题，并追加、替换或合并到问题集
- 单个 Monitoring Plan 暂定最多支持 30 个问题
- 支持快速监测和完整浏览器监测
- 支持按内部来源字段记录数据，但前台展示为豆包API、豆包网页版等用户可读名称
- 每次运行写入 Monitoring Run 和 Snapshot
- 自动监测结果进入 Dashboard 周期统计

### P2：趋势、告警和 Chat 追问

目标：形成完整监控闭环。

建议事项：

- 提及率下降告警
- 官网引用下降告警
- 竞品突然进入告警
- 风险顾虑上升告警
- 异常卡支持一键进入带上下文的 Chat 解释
- Chat 支持解释异常原因
- Chat 支持建议新增问题或调整问题集

## 11. 关键产品判断

1. Dashboard 的主对象应是“周期监测结果”，不是“最近报告”。

2. 全景监测和用户场景监测应在同一 Dashboard 框架下切换，但数据不能混算。

3. 自动监测的核心不是定时跑 A5，而是按 Monitoring Plan 持续生成 Snapshot 和 Artifact。

4. Chat 是监测能力的智能入口，不是自动监测的执行载体。

5. 报告仍然重要，但应成为单次深度诊断，而不是持续监测大盘本身。

6. Dashboard 顶部可以放置 Chat 快速输入框，但其职责是把当前品牌和监测上下文带入完整 Chat。

7. DeepSeek 应纳入 Dashboard 主指标，同时保留平台和运行策略来源。

8. 自动监测每次都生成完整 A5 报告，异常用于提醒用户处理，不替代报告。

9. 自动生成的问题集必须由用户确认后才能启用；用户可以要求继续生成补充问题。

10. Dashboard 指标来源内部应记录到具体来源粒度，但前台必须展示为用户可读的 AI 来源名称，例如豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi网页版。

11. 单个 Monitoring Plan 可以独立承载一个问题集，也可以合并多个场景问题集，但需要问题数量上限，当前暂定最多 30 个问题。

## 12. 已定结论与待决策问题

### 12.1 已定结论

1. Dashboard 默认进入全景监测。

2. 如果存在用户场景监测，Dashboard 应允许用户切换查看；多个场景问题集应在用户场景监测下继续选择。

3. DeepSeek 快速监测数据进入 Dashboard 主指标，但需要保留来源标识和运行策略说明。

4. 自动监测每次都生成完整 A5 报告。

5. “最近一轮分析”应改名为“最新诊断报告”或类似表达，并降级为 Monitoring Run 的详情入口。

6. 自动监测生成的问题集必须经过用户确认后才能启用；用户可以让 Chat 继续生成补充问题。

7. 快速监测与完整监测不只用运行策略区分，还要在 Dashboard 指标中拆分 AI 来源；前台展示名称应是豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi网页版这类用户语言。

8. 快速监测当前定义为 API 通道 + DeepSeek 浏览器通道；完整监测当前定义为全浏览器通道。

9. 用户场景监测的多个问题集既可以独立建立 Monitoring Plan，也可以合并到同一个 Monitoring Plan。合并时受单个计划问题数量上限约束，当前暂定最多 30 个问题。

10. Dashboard 顶部输入框允许用户先输入一行内容，再带着该输入和当前 Dashboard 上下文进入 Chat，并直接开始回复。

11. Chat 完成复测、问题集调整或计划更新后，暂不改变现有 Chat 流程，不强制自动返回 Dashboard。

### 12.2 仍待细化问题

1. 单个 Monitoring Plan 的 30 题上限是否需要按执行端点数量动态降低，例如浏览器端点较多时限制更低。

2. Dashboard 默认展示各 AI 来源名称，还是先按 AI 产品汇总、点击后展开 API / 网页版明细。

3. 快速监测产生的 API 数据与完整监测产生的浏览器数据，在同一趋势图中是否默认同屏展示，还是通过筛选控制。

4. 问题集确认界面需要展示哪些成本预估字段，例如预计问题数、端点数、预计耗时、可能超时风险。

## 13. 落地实施计划

### 13.1 总体落地原则

落地时必须先守住两个边界：

1. 新建品牌仍然必须走现有 Chat 循环。
   - 用户至少需要在 Chat 中补充品牌信息。
   - Chat 生成的问题集必须给用户确认。
   - 用户可以要求继续生成补充问题。
   - 用户确认后，问题集才能进入正式 Monitoring Plan。

2. Dashboard 第一阶段只做监测工作台和 Chat 交接棒，不重写 Chat 主流程。
   - Dashboard 负责展示已有品牌和已有监测上下文。
   - Dashboard 负责把用户的提问、异常、指标上下文交给 Chat。
   - Chat 继续负责品牌创建、问题集确认、计划调整、复测触发和解释。

### 13.2 Dashboard 与 Chat 的交接棒设计

Dashboard 到 Chat 的入口应分成四类：

1. 无品牌或新建品牌入口
   - Dashboard 展示“通过 Chat 建立品牌监测”。
   - 点击后进入现有 Chat 品牌创建循环。
   - 不传监测计划上下文，因为此时还没有正式 Plan。
   - Chat 继续收集品牌信息、生成问题集草稿、等待用户确认。

2. 已有品牌但没有监测计划
   - Dashboard 展示品牌已存在，但尚未建立监测计划。
   - CTA 进入 Chat，携带 `brand_id` 和入口来源。
   - Chat 基于该品牌继续生成或确认监测问题集，并创建 Monitoring Plan。

3. 已有品牌且已有监测计划
   - Dashboard 顶部展示 Chat 快速输入框。
   - 用户可以先输入一句话，再带着当前品牌、监测模式、问题集、时间范围和 AI 来源进入 Chat。
   - Chat 进入后直接基于上下文回复，不重复询问已知信息。

4. 从异常、指标、问题卡或报告入口进入 Chat
   - Dashboard 携带更精确的 `metric_context`、`alert_id`、`report_id` 或问题上下文。
   - Chat 基于 Snapshot、Artifact 和 Evidence Records 解释原因。
   - Chat 可以建议调整问题集、触发复测或查看最新诊断报告。

建议交接上下文包含：

```json
{
  "entry_source": "dashboard_command_bar | dashboard_alert | dashboard_metric | dashboard_report | dashboard_empty_state",
  "user_input": "为什么这周 DeepSeek网页版提及率下降了？",
  "brand_id": "brand_x",
  "monitor_mode": "panorama_monitoring | scenario_monitoring",
  "monitoring_plan_id": "plan_x",
  "question_set_id": "question_set_x",
  "time_range": "last_30_days",
  "ai_sources": ["豆包API", "豆包网页版", "DeepSeek网页版"],
  "metric_context": {
    "metric": "mention_rate",
    "current_value": 0.42,
    "previous_value": 0.56
  },
  "alert_id": "alert_x",
  "report_id": "artifact_x"
}
```

对于新建品牌入口，只传 `entry_source` 和 `user_input`，或最多携带用户选择的品牌名称草稿；不要伪造 `monitoring_plan_id`、`question_set_id` 或监测结果上下文。

### 13.3 Dashboard 第一阶段明确增加什么

P0 Dashboard 第一阶段建议增加以下能力：

1. 监测上下文头部
   - 当前品牌
   - 当前监测模式：全景监测 / 用户场景监测
   - 当前问题集
   - 当前时间范围
   - 当前 AI 来源范围，使用豆包API、豆包网页版、DeepSeek网页版等前台名称
   - 样本量：问题数、AI 来源数、有效回答数

2. 全景监测 / 用户场景监测切换
   - 默认进入全景监测。
   - 如果存在用户场景监测，允许切换查看。
   - 如果用户场景下有多个问题集，提供问题集选择。

3. Dashboard 顶部 Chat 快速输入框
   - 只在已有品牌和可用上下文时展示为提问输入框。
   - 用户可以输入一句话后进入 Chat。
   - 跳转时携带当前 Dashboard 上下文。
   - 没有品牌或没有计划时，改为进入 Chat 创建流程的 CTA。

4. 最新诊断报告入口
   - 将“最近一轮分析”改为“最新诊断报告”。
   - 作为 Monitoring Run / A5 Artifact 的详情入口。
   - 不再作为 Dashboard 主定义。

5. AI 来源展示规范
   - 前台展示豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi网页版。
   - 筛选器、图例、平台表现卡、报告说明统一使用这些用户语言。
   - 内部字段可以保留实现语义，但不能直接暴露给用户。

6. 异常和指标进入 Chat 的入口
   - 指标卡、异常卡、问题卡可以提供“让 Chat 分析”。
   - 入口必须携带具体指标或异常上下文。
   - Chat 解释时基于结构化事实和证据，不基于主观对话推断。

### 13.4 Dashboard 第一阶段明确不做什么

P0 Dashboard 第一阶段不做以下事情：

1. 不替代新建品牌的 Chat 循环。
   - Dashboard 不能直接创建完整品牌监测计划。
   - Dashboard 不能绕过品牌信息收集和问题集确认。

2. 不在 Dashboard 内嵌完整聊天窗口。
   - Dashboard 只提供快速输入和跳转入口。
   - 长对话仍进入现有 Chat 页面。

3. 不重写现有 Chat 主流程。
   - Chat 完成复测、问题集调整或计划更新后，暂不强制自动返回 Dashboard。
   - 可以保留现有 Chat 行为，只增加必要上下文接收能力。

4. 不在 P0 完成完整自动调度系统。
   - P0 可以先复用现有分析和报告数据映射 Dashboard 监测口径。
   - Monitoring Plan、Run、Snapshot 可在后续阶段逐步补齐。

5. 不混算 API 和网页版来源。
   - 豆包API和豆包网页版可以汇总展示，但底层和明细必须可拆分。
   - 不把 API 与网页版结果混成一个无法追溯的“豆包”指标。

6. 不让 Chat 凭空生成 Dashboard 结论。
   - Chat 解释必须读取 Snapshot、Artifact、Evidence 或当前已有结构化数据。
   - 如果数据不足，Chat 应说明缺少什么，而不是补造结论。

### 13.5 分阶段实施

#### Phase 1：Dashboard 交接棒与信息架构

目标：先把 Dashboard 和 Chat 的关系变正确。

主要工作：

- 改造 Dashboard 顶部为监测上下文区。
- 增加全景监测 / 用户场景监测切换。
- 增加 AI 来源展示和筛选，使用用户可见名称。
- 增加顶部 Chat 快速输入框。
- 支持无品牌、无计划、已有计划三种入口状态。
- 将最近报告入口改为最新诊断报告。
- Chat 跳转时携带 Dashboard 上下文。

验收标准：

- 新建品牌入口仍进入现有 Chat 品牌创建循环。
- 已有品牌输入一句话后能进入 Chat，并带上品牌和监测上下文。
- Dashboard 页面不再表达为“最近报告摘要页”。

#### Phase 2：Dashboard 数据结构与适配层

目标：让 Dashboard 有稳定的监测口径数据结构。

主要工作：

- 扩展 Dashboard Home 数据结构。
- 增加 `monitor_mode`、`question_set`、`ai_sources`、`sample_count`、`latest_report` 等字段。
- 把现有 A5 / 报告数据映射到新的 Dashboard 结构。
- 保证前台使用 `display_name` 展示 AI 来源。

验收标准：

- Dashboard 不需要解析 Markdown 报告才能展示核心口径。
- API / 网页版来源在数据上可拆分，前台名称可控。

#### Phase 3：Monitoring Plan 与问题集确认

目标：把 Chat 生成问题集和用户确认机制沉淀为正式计划。

主要工作：

- 增加或强化 Monitoring Plan / Question Set 数据模型。
- Chat 生成的问题集先进入草稿状态。
- 用户确认后启用。
- 支持继续生成补充问题。
- 单个计划最多 30 个问题。
- 展示问题数、AI 来源数、预计耗时和超时风险。

验收标准：

- 未确认的问题集不能进入自动监测。
- 用户能追加、替换或合并问题。
- 超过问题上限时系统阻止保存并解释原因。

#### Phase 4：自动监测执行与 Snapshot

目标：让自动监测按 Plan 生成可聚合结果。

主要工作：

- 支持快速监测：API + DeepSeek网页版。
- 支持完整监测：全浏览器。
- 每次运行生成 Monitoring Run。
- 每次运行生成 Monitoring Snapshot。
- 每次运行生成完整 A5 报告。
- 异常进入 Dashboard，并可跳转 Chat 解释。

验收标准：

- Dashboard 能按周期读取 Snapshot。
- 每个 Run 都有关联的 A5 报告。
- 异常解释能够追溯到证据。

#### Phase 5：趋势、异常与复测闭环

目标：把 Dashboard 从状态页升级为长期监控工作台。

主要工作：

- 增加提及率、排名、官网引用、竞品共现、风险顾虑趋势。
- 支持按 AI 来源拆分或汇总。
- 支持异常提醒。
- 支持从异常进入 Chat 分析。
- 支持 Chat 建议调整问题集或触发复测。

验收标准：

- 用户能回答“哪个 AI 来源变差了、为什么、证据在哪里、下一步怎么处理”。
- Dashboard 和 Chat 形成可追溯闭环。

## 14. 当前 Phase 1 实现状态与 Review

### 14.1 已完成到代码的部分

当前实现先覆盖 Phase 1 的 Dashboard 和 Chat 交接棒，不改写 Chat 主流程。

已落地内容：

1. Dashboard 顶部从静态概览升级为监测上下文区。
   - 展示当前品牌。
   - 展示当前监测模式。
   - 展示问题集、样本量和 AI 来源。
   - AI 来源使用用户语言，例如豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi 网页版。

2. Dashboard 默认进入全景监测，并提供全景监测 / 用户场景监测切换。
   - Dashboard Home API 已支持 `monitor_mode=panorama|scenario`。
   - 前端请求和 cache key 已纳入监测模式。
   - 如果所选模式没有数据，不展示另一种模式的数据，而是引导进入 Chat 补齐该模式的监测计划。

3. Dashboard 顶部增加 Chat 快速输入入口。
   - 已有监测上下文时，用户可以输入一句话进入 Chat。
   - 跳转到 Chat 时带上品牌、监测模式、问题集、样本和 AI 来源的上下文。
   - 当前复用现有 Chat 的 `draft + autosend` 机制，不新增 Chat 主流程。
   - URL 同时保留 `entry_source`、`monitor_mode`、`question_set_label`、`sample_summary`、`ai_sources` 等结构化上下文字段。
   - Chat 自动发送时会把这些字段转成现有 WebSocket `context`，进入后端编排输入。

4. 新建品牌路径接回 Chat。
   - Dashboard 新建品牌仍先收集基础品牌信息。
   - 品牌创建后自动进入该品牌 Chat。
   - Chat 收到“建立品牌监测、生成问题集并让用户确认”的初始意图。

5. “最近一轮分析”改为“周期监测结果 / 最新诊断报告”的表达。
   - Dashboard 不再把最近报告当作页面主定义。
   - 最新诊断报告保留为可打开的深度报告入口。

6. 指标卡增加“让 Chat 分析”入口。
   - 指标解释进入同一条 Chat 交接路径。
   - 当前通过可见 draft 文案携带指标上下文。

### 14.2 部分完成但还不是最终形态的部分

1. Chat 上下文传递已进入现有 `context` 通道，但还不是正式 Dashboard Context Contract。
   - 优点是复用现有 Chat 机制，改动小。
   - 结构化字段已不只停留在 URL，会随自动发送进入编排输入。
   - 后续仍需要把 Dashboard Context 做成明确 schema，而不是只作为上下文标签附加到用户消息。

2. AI 来源名称已补齐 API / 网页版维度，但长期还需要进入 Monitoring Plan schema。
   - 能避免直接展示 provider、channel、browser、endpoint 等内部语言。
   - A5 canonical 已保存 `fetch_method`，Dashboard 后端投影会按 `platform + fetch_method` 返回用户语言。
   - 前端仍保留兜底归一化，避免旧报告没有 `fetch_method` 时展示内部语言。

3. Dashboard 内的新建品牌入口已接回 Chat，但后续新增入口仍需要沿用同一 helper。
   - 当前主页面、品牌卡片、品牌管理弹窗和品牌选择弹窗都应在创建后进入 Chat。
   - 原则是：可以先收集品牌基础信息，但创建后必须进入 Chat 完成监测问题集确认。

### 14.3 尚未实现的部分

1. Monitoring Plan / Question Set 正式数据模型。
   - 问题集草稿。
   - 用户确认后启用。
   - 继续生成补充问题。
   - 追加、替换、合并。
   - 单个 Plan 最多 30 个问题。

2. 自动监测执行体系。
   - 快速监测：API + DeepSeek网页版。
   - 完整监测：全浏览器。
   - 每次运行生成 Monitoring Run、Snapshot、A5 Report Artifact 和 Evidence Records。

3. Dashboard 周期聚合和趋势。
   - 当前仍以最新可用报告投影为主。
   - 还没有按时间范围聚合多轮 Snapshot。
   - 还没有按 AI 来源拆分趋势图。

4. 异常告警闭环。
   - 当前指标能进入 Chat 分析。
   - 但还没有正式 alert 模型、阈值、异常卡和证据链。

### 14.4 当前主要漏洞与冲突

1. “用户场景监测有多个问题集”目前还没有选择器。
   - 当前只展示 latest report 的 `question_set_label`。
   - 真正的多个问题集切换必须依赖 Question Set 和 Monitoring Plan 数据结构。

2. “Chat 不能凭空生成监测结论”目前还依赖 Chat 后续实现约束。
   - Dashboard 已经把上下文传给 Chat。
   - 但 Chat 侧还需要基于 Snapshot、Artifact、Evidence 读取事实，而不是只根据 draft/context 文本回答。

3. “每次自动监测都生成完整 A5 报告”还没有执行层保障。
   - 目前 Dashboard 只把已有报告作为最新诊断报告入口展示。
   - 后续 Monitoring Run 创建时必须强制产出 A5 Artifact。

4. “DeepSeek 纳入 Dashboard 指标”当前依赖现有报告或答案数据中是否有 DeepSeek。
   - 前端已能展示 DeepSeek网页版。
   - 后端还需要在自动监测端点配置中保证 DeepSeek 被纳入计划和运行。

### 14.5 下一步建议

下一步优先进入 Monitoring Plan 和 Question Set 的正式模型设计与实现：

1. 建立问题集草稿、确认、追加、替换、合并状态。
2. 建立 Monitoring Plan 与 `monitor_mode`、AI 来源、频率、问题上限的正式关联。
3. 后端返回 AI 来源 `display_name`，前端保留兜底归一化。
4. 再进入 Monitoring Run / Snapshot / A5 Artifact 的自动监测执行闭环。

## 15. Phase 2 实现闭环记录

本轮已把 Phase 1 的 Dashboard/Chat 交接棒推进到可执行的监测基础闭环。

### 15.1 已完成

1. 后端新增正式监测领域模型。
   - `MonitoringQuestionSet`：支持 `draft/confirmed/archived`，按品牌和 `panorama/scenario` 归属。
   - `MonitoringPlan`：支持 `draft/active/paused/archived`，关联多个问题集、AI 来源、频率和运行策略。
   - `MonitoringRun`：记录计划运行、任务、TaskRun、Snapshot、失败原因和状态。
   - `MonitoringEvidenceRecord`：为自动监测运行保留 A4 证据行基础。
   - Alembic migration：`019_add_monitoring_plan_question_sets.py`。

2. 用户确认规则已进入执行层。
   - A3 生成问题后写入 `QuestionSet(draft)`。
   - A4 在用户确认快速采集后，将最近的问题集确认并激活 `MonitoringPlan(active)`。
   - Draft 问题集不能创建 active Plan。
   - 一个 Plan 合并后的问题上限固定为 30 个，超出会阻断。
   - 完整浏览器自动监测在 v1 被策略校验前置拦截，不会留下“问题集已确认但 Plan 未创建”的半完成状态。
   - Chat 桥接激活 Plan 前会校验问题集所属品牌和监测模式，避免跨品牌或跨模式挂载。

3. AI 来源以用户语言纳入 Plan。
   - 快速监测默认来源为：豆包API、元宝API、Kimi API、DeepSeek网页版。
   - 可展示来源清单包含：豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi 网页版。
   - Dashboard、Plan、Schedule 都返回 endpoint labels，避免暴露内部 provider / method 名称。

4. 自动监测链路接入现有 scheduler。
   - Plan 激活后会创建或复用 `MonitoringSchedule`。
   - Schedule 增加 `monitor_mode`、`question_set_ids`、`endpoint_ids`、`run_policy`、`monitoring_plan_id`。
   - scheduler 按 schedule 的监测模式决定 A5 报告类型：全景走 baseline，用户场景走 persona。
   - run 成功后更新 `MonitoringRun` 并写 Snapshot / A5 report artifact；失败会记录 error message 和 stage。
   - scheduler 在启动前置校验失败时也会同步失败 `MonitoringRun`，避免 Plan run 长期停在 pending。

5. Dashboard 聚合与 Chat 桥接升级。
   - Dashboard Home 返回 `monitoringPlan`，即使还没有报告，也能展示计划上下文。
   - Dashboard 顶部输入框会把 `monitoring_plan_id`、`question_set_ids`、`endpoint_ids`、AI 来源、问题集标签带入 Chat。
   - Chat 自动发送时把 Dashboard 上下文作为结构化 `context.data` 进入 WebSocket。
   - 后端保存用户消息 metadata 中的 `dashboard_context`，并把它写入 workflow state。

6. Monitoring Tab 增加轻量 Plan 展示。
   - 展示 Plan 状态、问题数和 AI 来源。
   - active Plan 可触发快速复测。
   - 未建立 Plan 时引导回 Chat，而不是绕到设置页。

### 15.2 验证结果

已完成验证：

1. `pytest tests/test_monitoring_plan_service.py tests/test_a5_decision_diagnosis.py -q`
   - 27 passed。
   - 覆盖 draft 不能激活、完整浏览器策略拦截不确认 draft、跨品牌问题集拦截不确认 draft、确认后创建 active Plan + schedule、30 问题限制、AI 来源展示名、A5 source method 投影。

2. `npm run lint`
   - 通过，保留既有 3 个 warning：`TPAORBlock.defaultExpanded`、`BrandAvatar img`、`ThemedLogo img`。

3. `npm run build`
   - 通过。

4. `python scripts\validate_change.py`
   - PASS。

5. Source integrity。
   - 已扫描 changed + untracked 文件，无新增三连问号占位符。
   - 已扫描前端旧 AI 色彩/效果词，无命中。
   - `git diff --check` 仅有 Windows LF/CRLF warning。

### 15.3 与设计的偏差

1. 完整浏览器监测还没有启用自动执行。
   - schema 已支持 `full_browser`。
   - 当前 active 自动监测只允许 quick。
   - 这是有意限制，避免在没有稳定运行验证前把“全浏览器自动监测”说成已完成。

2. Chat 的“确认问题集”仍复用现有采集确认节点。
   - 当前实现是在 A4 用户确认采集时激活 Plan。
   - 后续更理想形态是：A3 问题集确认本身成为明确的 Chat confirmation contract，再由 orchestrator 显式创建或更新 Plan。

3. Dashboard 趋势仍主要复用现有 Snapshot 趋势。
   - Plan 和 Run 已经接入。
   - 但按 endpoint / question set 分层的趋势聚合还没完成。

4. 异常处理已记录 Run failure，但 Dashboard 异常卡闭环还未完成。
   - 失败原因可写入 `MonitoringRun`。
   - 前端还没有完整的“异常 -> 处理 -> Chat”专用卡片。

### 15.4 剩余风险

1. 当前分支仍落后 `origin/main` 4 个提交。
   - 涉及 DeepSeek orchestrator history 和 domain citation enrichment。
   - 进入合并前需要先同步 main，再重跑上述验证，重点检查 A4/A5/analytics_service 冲突。

2. `MonitoringRun` 的真实运行 smoke 还需要在本地 runtime 或 demo 环境跑一遍。
   - 本轮已验证模型、API、构建和单元行为。
   - 尚未声明“新品牌 Chat -> quick run -> Dashboard 出报告”的端到端真实运行已完成。

3. EvidenceRecord 当前从 final_state.fetch_results 抽取基础证据。
   - 足够支撑后续证据链扩展。
   - 还需要补充更细的引用类型、官方/非官方来源、异常证据分类。

## 16. Phase 3 实现闭环记录：周期聚合、分层趋势、独立确认与异常卡

本轮目标是补齐上一轮留下的五个缺口：Dashboard 多轮 Snapshot 周期聚合、趋势分层、独立问题集确认、异常卡闭环、真实 E2E 验证入口。

### 16.1 Done

1. Dashboard Home 已优先使用近 30 天 Snapshot 周期聚合。
   - `/analytics/v2/dashboard-home` 增加 `date_range`。
   - 按品牌、监测模式和时间范围查询多轮 `AnalysisSnapshot`。
   - 返回 `periodSummary`、`dataPointCount`、核心指标最新值、均值、变化和趋势点。
   - 没有可聚合 Snapshot 时仍回退 latest report projection，不解析 Markdown，不伪造缺失指标。

2. 新增分层趋势接口。
   - `/analytics/v2/monitoring-trends` 支持 `group_by=overall|endpoint|question_set`。
   - `overall` 使用 Snapshot 指标列和 raw metrics。
   - `endpoint` 使用 `MonitoringEvidenceRecord`，并按 endpoint_id 独立聚合。
   - `question_set` 使用 `MonitoringRun.question_set_ids` 过滤对应 Snapshot。
   - 用户可见 AI 来源保持为：豆包API、豆包网页版、DeepSeek网页版、元宝API、元宝网页版、Kimi API、Kimi 网页版。

3. Monitoring Tab 趋势图已支持分层切换。
   - 前端增加“总览 / AI 来源 / 问题集”切换。
   - 多来源返回多折线。
   - 切换分层时保留当前指标，不会把用户正在看的指标误切回提及率。

4. Chat 问题集确认独立成 contract。
   - A3 生成问题后保存 `QuestionSet(draft)`。
   - A3 发出 `question_set_confirmation`。
   - 选项固定为：确认并启用快速监测、继续补充问题、暂不启用。
   - 用户确认后直接 `confirm_question_set_and_activate_quick_plan`，创建或更新 `MonitoringPlan(active)`。
   - A4 原有激活逻辑保留为 legacy/idempotent fallback，不再是主路径。
   - 继续补充和暂不启用不会激活 Plan；追加超过 30 个问题会被拦截。

5. Dashboard 异常卡闭环已落地到 Home 和 Monitoring Tab。
   - Dashboard Home 返回最近 failed/stale run 的 `recentIssue`。
   - Monitoring Tab 从 Plan runs 展示失败或 stale run。
   - 异常卡展示失败阶段、失败原因、问题数、AI 来源和 Plan 关联。
   - CTA 固定为“AI 对话处理”和“重新触发快速复测”。
   - 进入 Chat 时携带 `monitoring_run_id`、`monitoring_plan_id`、`error_stage`、`error_message`、`monitor_mode`、`endpoint_ids`、`question_set_ids`。

### 16.2 Partial

1. Dashboard 周期聚合已经接入 Snapshot，但指标体系仍是 v1 核心指标。
   - 已覆盖提及率、品牌可见度、情感倾向、平台覆盖、内容引用率、官网转化率。
   - 平均排名、Top1/Top3/Top10、竞品共现、风险顾虑率仍需要后续在 A5 canonical metrics 中稳定产出。

2. 异常处理已能进入 Chat，但 Chat 侧“只基于 Run/Snapshot/Evidence 事实回答”的强约束还需要继续收紧。
   - 结构化上下文已经带入。
   - 后续应增加 Dashboard Context Contract 和事实读取节点，避免仅凭 draft 文案解释。

3. endpoint 趋势目前基于 EvidenceRecord 的基础证据字段。
   - 可以区分 API 和网页版。
   - 需要继续补充官方引用、竞品共现、风险顾虑等更细粒度 evidence 字段。

### 16.3 Pending

1. Full browser 自动监测仍未启用。
   - 本轮仍只覆盖 quick monitoring：豆包API、元宝API、Kimi API、DeepSeek网页版。

2. 新品牌全真实 E2E 尚未声明通过。
   - 已完成单元、lint、build 和本地验证入口准备。
   - 真实 E2E 必须使用共享 env、真实 LLM/浏览器登录和本地运行服务；如果凭据或 DeepSeek 登录不可用，只能标记 blocked。

3. 合并前仍需要同步 `origin/main` 并重跑验证。
   - 当前分支落后 main，合并前必须处理漂移。

### 16.4 Review 结果

本轮自查未发现新的 P0/P1/P2 问题。已在 review 中修复两处行为风险：

1. endpoint 趋势只聚合 `completed/partial` run，避免 pending/failed run 的 evidence 被误算入趋势。
2. 前端趋势分层切换会携带当前指标，避免用户从“内容引用率”切到“AI 来源”后实际请求变成“提及率”。

### 16.5 本轮验证记录

已通过：

1. `pytest tests/test_monitoring_plan_service.py tests/test_dashboard_monitoring_analytics.py tests/test_a5_decision_diagnosis.py -q`
   - 33 passed。
   - 覆盖 Plan contract、append 超限、decline 不启用、Dashboard 周期聚合、endpoint API/Web 分离、question_set 过滤和 A5 source method 投影。

2. `npm run lint`
   - 通过。
   - 保留既有 3 个 warning：`TPAORBlock.defaultExpanded`、`BrandAvatar img`、`ThemedLogo img`。

3. `npm run build`
   - 通过。

4. Source integrity。
   - 已扫描本轮改动前端文件，无旧 AI 视觉词命中。
   - 已扫描本轮改动前后端文件，无新增三连问号占位符。

5. `git diff --check`
   - 无 whitespace error。
   - 仅有 Windows LF/CRLF warning。

### 16.6 本机真实 E2E 状态

状态：blocked，未声明通过。

已确认：

1. 当前 worktree 后端可以在 `127.0.0.1:8011` 启动，`/health` 返回 healthy。
2. 曾误以为当前 worktree 前端在 `127.0.0.1:3011`；后续验证发现该端口实际来自另一个 worktree。
3. 共享 backend env 可用，但当前 worktree 没有独立 `.env.local`。

阻塞点：

1. 共享本地数据库的 Alembic 状态不一致。
   - `alembic current` 返回 `017`。
   - `alembic upgrade head` 尝试执行 018 时失败，因为 `fetch_run_platform_states` 表已经存在。
   - 因此无法安全推进到本分支新增的 019 migration。

2. 由于 019 未应用，当前分支后端 scheduler 查询 `monitoring_schedules.monitoring_plan_id` 时会报列不存在。
   - 这会影响真实 `new brand -> Chat -> QuestionSet confirmed -> Plan active -> quick run -> Snapshot/A5/Evidence -> Dashboard` 链路。

结论：

- 本轮没有把真实 E2E 伪装成通过。
- 下一步需要先修复本地共享数据库 migration history，例如明确处理 018 已存在但版本仍停在 017 的状态，再应用 019 并重跑真实 E2E。

## 17. Dashboard 首页布局与待办规则收口记录

本轮基于产品评审后的原型方向，把 Dashboard 首页从“品牌卡片区 + Chat 说明卡”收敛为更轻的工作台结构：左侧品牌栏、顶部品牌信息与 AI 对话入口、单条待办、周期监测。

### 17.1 Done

1. 左侧品牌栏改为基本信息列表。
   - 只展示品牌名称、官网和管理入口。
   - 不再出现“监测对象”等内部或抽象词。
   - 品牌操作能力保留在品牌管理弹窗和主页面入口中。

2. 顶部品牌卡简化。
   - 只保留当前品牌信息、状态标签和 AI 对话输入入口。
   - 状态标签统一为：待监测、正在监测、暂停监测。
   - 用户可见按钮和错误文案不再使用“进入 Chat”，统一使用“AI 对话”。
   - 输入框占位为“输入您的问题...”，不再预设“补充监测要求”等窄场景文案。

3. 待办条改为后端 contract。
   - Dashboard Home 返回 `todoItems`。
   - 前端只展示第一条有效待办；没有待办时整条不显示。
   - v1 固定三条规则：
     - 未完成分析的基本信息、问题生成。
     - 未完成监测计划的设置。
     - 有新的报告尚未查看。

4. 周期监测区改为默认可见。
   - 没有 Snapshot 时也展示指标卡、AI 来源卡、时间范围和分析类型切换。
   - 去掉“表格视图 / 卡片视图”切换，只保留卡片视图。
   - 顶部不再出现“增加品牌监测”。
   - 原“全部平台”入口改为“全景分析 / 用户场景分析”切换。

### 17.2 实现说明

1. 后端规则集中在 `AnalyticsService._build_dashboard_todo_items`。
   - 新品牌且无报告、无 Plan、无周期样本：返回 `analysis_setup_incomplete`。
   - 有问题集或分析上下文但 Plan 未 active：返回 `monitoring_plan_incomplete`。
   - active Plan 且有可打开报告引用：返回 `unread_latest_report`。

2. 前端新增三个 Dashboard 组件。
   - `DashboardBrandSidebar`：左侧品牌栏。
   - `DashboardTodoStrip`：单条待办。
   - `DashboardPeriodMonitoring`：周期监测卡片区。

3. 报告待办使用本地已读标记。
   - `unread_latest_report` 打开后写入 localStorage。
   - 同一个品牌、同一个报告引用不重复提示。

### 17.3 验证结果

已通过：

1. `python -m pytest aeo-platform/backend/tests/test_dashboard_monitoring_analytics.py -q`
   - 6 passed。
   - 覆盖周期聚合、endpoint 分层、question_set 分层和三条待办规则。

2. `python -m pytest aeo-platform/backend/tests/test_monitoring_plan_service.py aeo-platform/backend/tests/test_dashboard_monitoring_analytics.py -q`
   - 14 passed。

3. `npm run lint`
   - 0 error，保留既有 3 个 warning。

4. `npm run build`
   - 通过。

5. `python scripts\validate_change.py`
   - PASS。

6. Source integrity。
   - Dashboard 相关前端文件无新增 `???`。
   - Dashboard 相关前端文件无旧 AI 视觉词命中。
   - Dashboard 相关前端文件无“进入 Chat / 监测对象 / 全部平台 / 表格视图 / 卡片视图 / 增加品牌监测”等冲突文案。

7. 本地端口核查。
   - `127.0.0.1:3011` 实际属于 `D:\AGEO-worktrees\a5-source-taxonomy-cleanup`，不是当前分支。
   - 当前分支前端已启动在 `127.0.0.1:3012`，指向当前分支后端 `127.0.0.1:8011`。

### 17.4 Partial / Risk

1. 真实登录态视觉 smoke 未完成。
   - Headless Playwright 访问 `127.0.0.1:3012/dashboard` 会因无登录态跳转到 `/auth?next=/dashboard`。
   - 未读取或复用用户浏览器 Cookie。
   - 需要用户在已登录浏览器打开 `http://127.0.0.1:3012/dashboard` 做最终视觉确认。

2. 3011 端口存在 worktree 漂移风险。
   - 后续讨论和验收需要明确使用当前分支地址 `3012`，或先关闭旧 worktree 服务后再回到 `3011`。
