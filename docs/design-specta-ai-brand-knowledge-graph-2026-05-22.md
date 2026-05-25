# Specta AI 品牌知识图谱设计（2026-05-22）

> 状态：Draft
> 目标：把“AI 品牌情报系统”从页面展示重新收敛到知识图谱模型，明确 `简要情报`、`情报来源`、`品牌世界`、`跟进反馈` 四个页签的职责、数据来源和前端表达边界。
> 重要约束：前端页面不允许出现自说自话文案，不允许把 Ontology、对象图、ActionRecord、Orchestrator 等内部概念暴露给用户。

## 一句话结论

Specta 的核心不是展示一堆对象，而是回答品牌团队真正会买单的问题：

```text
我的品牌在 AI 回答里表现如何？
这个判断从哪些平台、问题、回答和来源得来？
我和竞品的关系是什么？
下一步应该补什么内容、监测什么变化、优化什么来源？
```

知识图谱不是视觉上的环形布局。知识图谱是可查询、可追溯、可计算、可行动的事实网络：

```text
品牌
  <- 被提及事实 <- AI 回答 <- 用户问题
  <- 被提及事实 <- AI 回答 <- AI 平台
  -> 竞品对照 -> 竞品品牌
  -> 官方域名 -> 来源域名
  <- 指标衡量 <- 指标快照
  <- 证据支撑 <- 情报判断
  -> 跟进建议 / 监测计划
```

前端四个页签只是同一个图谱的四种投影：

1. `简要情报`：经营层摘要。
2. `情报来源`：从指标反查证据。
3. `品牌世界`：用图谱展示对象和强关系。
4. `跟进反馈`：把图谱缺口转成可执行建议。

## 官方依据

Palantir 文档给 Specta 的借鉴点是：Ontology 不是普通数据目录，而是组织的运营层，位于数据集、虚拟表和模型之上，把数字资产连接到现实世界对象，并包含对象、属性、关系、动作、函数和安全等元素。见 [Palantir Ontology overview](https://www.palantir.com/docs/foundry/ontology/overview)。

Palantir Core Concepts 明确区分对象、属性、关系和动作：对象代表现实实体或事件；属性描述对象；关系连接两个对象；动作定义对象如何被修改。见 [Palantir Core concepts](https://www.palantir.com/docs/foundry/ontology/core-concepts)。

Palantir Object Backend 强调对象后端负责对象查询、搜索、聚合和动作写入编排。对 Specta 来说，这对应“从品牌对象读取世界”和“通过受控动作更新世界”。见 [Object Backend overview](https://www.palantir.com/docs/foundry/object-backend/overview)。

Neo4j 的属性图模型强调：图由节点、关系、标签和属性组成；关系有方向和类型；节点和关系都能带属性。见 [Neo4j GraphAcademy fundamentals](https://graphacademy.neo4j.com/courses/workshop-fundamentals/1-neo4j-fundamentals/1-what-is-neo4j/)。

Neo4j 数据建模课程强调：关系来自用例中的动词，关系命名必须让业务和开发都直观理解；关系属性用于描述两个节点“如何相关”。见 [Neo4j Modeling Relationships](https://graphacademy.neo4j.com/courses/modeling-fundamentals/3-defining-relationships/1-defining-relationships/)。

Neo4j 还指出，当一个关系需要连接更多上下文，或需要被其他对象继续引用时，应把它提升为中间节点。见 [Neo4j Intermediate Nodes](https://graphacademy.neo4j.com/courses/modeling-fundamentals/8-adding-intermediate-nodes/1-intermediate-nodes/)。

## 设计原则

### 1. 先定义用户问题，再定义图谱

图谱不是为了把已有数据库表画出来。图谱必须能回答明确问题：

1. AI 提及率是多少，怎么算出来的？
2. 哪些平台、哪些问题、哪些回答提到了品牌？
3. 与竞品相比排第几，差距在哪？
4. AI 对品牌的语气是正向、中性还是负向？
5. 官网有没有成为 AI 回答的依据？
6. 外部来源里，哪些域名最影响 AI 对品牌的描述？
7. 当前最应该补官网、补第三方内容、补竞品样本，还是开启监测？

每个节点、关系、属性和指标都必须服务这些问题。

### 2. 节点是名词，关系是动词，指标是计算结果

不要把所有东西都当成节点平铺。

| 类型 | 示例 | 判断规则 |
| --- | --- | --- |
| 节点 | 品牌、AI 平台、用户问题、AI 回答、引用来源、竞品、情报判断、建议 | 可以独立存在、被查询、被复用 |
| 关系 | 回答了、来自、提及、引用、对比、支撑、回应 | 描述两个节点如何连接 |
| 关系属性 | 语气、原文片段、位置、置信度、采集时间 | 只属于这两个节点之间的事实 |
| 指标快照 | 提及率、排名、官网引用率、语气分布 | 从一批节点和关系计算得出，有时间和样本范围 |

### 3. 复杂关系要升格为中间节点

`AIAnswer -> MENTIONS -> Brand` 表面上够用，但不能支撑商业分析。因为“提及”本身还要连接：

1. 语气性质。
2. 原文片段。
3. 所属问题。
4. 所属平台。
5. 引用来源。
6. 支撑的情报判断。
7. 用户反馈。

因此应建模为：

```text
AIAnswer -[:HAS_MENTION]-> BrandMention
BrandMention -[:MENTIONS_BRAND]-> Brand
BrandMention -[:ABOUT_QUESTION]-> Question
BrandMention -[:SUPPORTED_BY_CITATION]-> CitationSource
```

`BrandMention` 是一条可追溯的品牌提及事实，不是 UI 展示技巧。

### 4. 前端只讲业务，不讲系统

禁止出现在前端的表达：

```text
这里解释...
品牌世界不是...
对象关系...
ActionRecord
Orchestrator
Ontology
弱关系
世界主链
证据链是当前检查点
最后压缩成可行动判断
这些结论怎么来的
看重点
处理反馈项
创建监测计划（作为情报来源或结论出现）
```

允许出现的表达：

```text
AI 提及率
提及排名
官网引用率
语气性质
回答样本
引用来源
竞品对照
优化建议
开启监测
查看回答
查看来源
解释这个指标
```

## 图谱数据模型 v0.1

### 节点

| 节点 | 含义 | 关键属性 |
| --- | --- | --- |
| `Brand` | 品牌，包含当前品牌和竞品 | name, normalizedName, domain, industry |
| `AIPlatform` | AI 回答平台 | name, provider, fetchMethod |
| `Question` | 用户问题或场景问题 | text, scenario, intent, priority |
| `AIAnswer` | 某平台对某问题的一次回答 | answerText, answerPreview, capturedAt, status |
| `BrandMention` | 回答中提及某品牌的事实 | sentiment, quote, position, confidence |
| `CitationSource` | 回答引用或可归因的来源页面 | url, title, snippet, sourceType |
| `SourceDomain` | 来源域名 | domain, displayName, isOfficial, sourceRole |
| `AnalysisRun` | 一次采集与分析批次 | runId, startedAt, platformCount, questionCount |
| `MetricSnapshot` | 某次分析形成的指标 | metricKey, value, numerator, denominator, period |
| `Finding` | 情报判断 | title, findingType, severity, confidence |
| `Recommendation` | 跟进建议 | title, targetMetric, actionType, priority |
| `MonitoringPlan` | 监测计划 | cadence, platforms, questionScope, status |

### 关系

| 关系 | 起点 | 终点 | 关系属性 |
| --- | --- | --- | --- |
| `INCLUDES_QUESTION` | AnalysisRun | Question | order, source |
| `USES_PLATFORM` | AnalysisRun | AIPlatform | endpointId |
| `ANSWERED_BY` | Question | AIAnswer | capturedAt |
| `FROM_PLATFORM` | AIAnswer | AIPlatform | fetchMethod |
| `HAS_MENTION` | AIAnswer | BrandMention | detectedBy |
| `MENTIONS_BRAND` | BrandMention | Brand | aliasMatched |
| `ABOUT_QUESTION` | BrandMention | Question | scenario |
| `CITES` | AIAnswer | CitationSource | rank, quote |
| `BELONGS_TO_DOMAIN` | CitationSource | SourceDomain | normalizedDomain |
| `HAS_OFFICIAL_DOMAIN` | Brand | SourceDomain | verified |
| `COMPETES_WITH` | Brand | Brand | competitorSource, confidence |
| `MEASURES` | MetricSnapshot | Brand | metricKey |
| `BASED_ON_RUN` | MetricSnapshot | AnalysisRun | sampleScope |
| `USES_MENTION` | MetricSnapshot | BrandMention | contribution |
| `USES_CITATION` | MetricSnapshot | CitationSource | contribution |
| `SUPPORTED_BY` | Finding | MetricSnapshot / BrandMention / CitationSource | evidenceRole |
| `RESPONDS_TO` | Recommendation | Finding | reason |
| `TARGETS` | Recommendation | Brand / Question / SourceDomain / MonitoringPlan | targetReason |
| `TRACKS` | MonitoringPlan | Brand | cadence |
| `SAMPLES` | MonitoringPlan | Question / AIPlatform | samplePolicy |

## 指标计算口径

### AI 提及率

定义：

```text
AI 提及率 = 提及当前品牌的有效回答数 / 全部有效回答数
```

图谱路径：

```text
AnalysisRun
  -> Question
  -> AIAnswer
  -> BrandMention
  -> Brand
```

必要字段：

| 字段 | 来源 |
| --- | --- |
| 分母 | AnalysisRun 下全部有效 AIAnswer |
| 分子 | AIAnswer 下存在 BrandMention 且 MENTIONS_BRAND 指向当前 Brand |
| 平台拆分 | AIAnswer -> FROM_PLATFORM |
| 问题拆分 | Question -> ANSWERED_BY -> AIAnswer |
| 回答样本 | AIAnswer.answerPreview + BrandMention.quote |

前端展示：

```text
AI 提及率 73.7%
3 个平台，96 条回答，70 条提到理想汽车
```

禁止展示：

```text
先看品牌有没有进入 AI 回答
这里解释简要情报背后的探查路径
```

### 提及排名

定义：

```text
同一批问题、同一批平台、同一批分析批次下，各品牌提及率的排序
```

图谱路径：

```text
AnalysisRun
  -> AIAnswer
  -> BrandMention
  -> Brand
Brand -[:COMPETES_WITH]-> Brand
```

必要字段：

| 字段 | 来源 |
| --- | --- |
| 品牌列表 | 当前 Brand + COMPETES_WITH 竞品 |
| 每个品牌提及次数 | BrandMention 聚合 |
| 每个品牌提及率 | mentionCount / answerCount |
| 排名 | 按 mentionRate 降序 |

前端展示：

```text
提及排名 第 1 / 5
理想汽车 73.7%，小米汽车 61.4%，腾势 42.1%
```

### 官网引用率

定义：

```text
官网引用率 = 指向品牌官方域名的引用数 / 全部引用数
```

图谱路径：

```text
AIAnswer
  -> CitationSource
  -> SourceDomain
Brand
  -> HAS_OFFICIAL_DOMAIN
  -> SourceDomain
```

必要字段：

| 字段 | 来源 |
| --- | --- |
| 官方域名 | Brand -> HAS_OFFICIAL_DOMAIN |
| 官网引用次数 | CitationSource -> SourceDomain where isOfficial |
| 外部域名排行 | CitationSource -> SourceDomain where not official |
| 平台拆分 | AIAnswer -> AIPlatform |

前端展示：

```text
官网引用率 0.0%
官网未进入本轮 AI 回答引用；外部来源首位为 dongchedi.com
```

### 语气性质

定义：

```text
品牌被提及时，回答对品牌的语气分布
```

图谱路径：

```text
AIAnswer
  -> BrandMention {sentiment, quote}
  -> Brand
```

必要字段：

| 字段 | 来源 |
| --- | --- |
| 正向数 | BrandMention.sentiment = positive |
| 中性数 | BrandMention.sentiment = neutral |
| 负向数 | BrandMention.sentiment = negative |
| 原文片段 | BrandMention.quote |
| 平台拆分 | AIAnswer -> AIPlatform |

前端展示：

```text
正向 42 条，中性 26 条，负向 2 条
主要正向语气集中在增程、家庭用车和智能座舱场景
```

## 四个页签的产品定义

### 1. 简要情报

职责：给经营层看当前 AI 品牌表现。

回答问题：

1. AI 有没有提到我？
2. 我排第几？
3. AI 说我是好是坏？
4. AI 的依据靠官网还是外部来源？
5. 当前最值得关注的风险或机会是什么？

页面结构：

```text
顶部摘要
  当前品牌 + 时间范围 + 样本范围

核心指标
  AI 提及率
  提及排名
  官网引用率
  语气性质

当前判断
  一条最重要的机会
  一条最重要的风险

入口
  查看来源
  查看品牌世界
  查看建议
```

文案风格：

```text
理想汽车本轮 AI 提及率 73.7%，在 96 条有效回答中被提到 70 次。
官网引用率 0.0%，AI 回答主要依赖汽车垂直站和媒体来源。
```

禁止：

```text
这条判断已经从对象中沉淀出来
证据链支撑当前检查点
人类只需要观察和反馈
```

### 2. 情报来源

职责：从指标反查证据。

回答问题：

1. 73.7% 是怎么算出来的？
2. 哪些平台贡献了提及？
3. 哪些回答提到了我，原文怎么说？
4. 排名里的竞品是谁，各自提及率多少？
5. 官网为什么没被引用？
6. 语气判断来自哪些回答？

页面结构：

```text
指标切换
  提及率
  提及排名
  官网引用
  语气性质

指标说明
  分子
  分母
  时间范围
  平台范围

证据表
  平台 / 问题 / 回答 / 是否提及 / 语气 / 引用来源

样本抽屉
  原始回答
  提及片段
  引用 URL
```

前端不显示“探查路径”这个抽象概念。可以显示：

```text
计算口径
样本范围
回答样本
来源域名
```

### 3. 品牌世界

职责：展示品牌知识图谱，不展示内部对象清单。

回答问题：

1. 当前品牌和哪些问题、平台、回答、来源、竞品发生了关系？
2. 哪些关系支撑了当前指标？
3. 哪些节点是缺口？
4. 哪些节点会被监测继续更新？

页面结构：

```text
图谱画布
  默认从 Brand 节点展开强关系

右侧详情
  选中节点的属性、相邻节点、证据、可追问入口

关系筛选
  提及
  引用
  竞品
  指标
  建议

展开策略
  点品牌：显示问题、平台、竞品、官网、指标
  点提及事实：显示回答、语气、原文、引用
  点指标：显示样本、分子分母、贡献节点
  点来源域名：显示被哪些回答引用
  点建议：显示回应哪个判断、由哪些证据支撑
```

注意：`提及率` 本身不是品牌旁边的装饰节点。它是 `MetricSnapshot`，必须能沿关系回到 `AnalysisRun`、`AIAnswer`、`BrandMention`。

### 4. 跟进反馈

职责：把图谱缺口转为可执行建议。

回答问题：

1. 现在最应该优化什么？
2. 为什么是这个建议？
3. 它会影响哪个指标？
4. 需要补什么内容或来源？
5. 是否需要进入周期监测？

建议类型：

| 建议 | 触发条件 | 支撑图谱路径 |
| --- | --- | --- |
| 补官网内容 | 官网引用率低 | MetricSnapshot -> CitationSource -> SourceDomain |
| 补竞品对照 | 排名样本不足 | MetricSnapshot -> BrandMention -> Brand |
| 补场景文章 | 某些问题未提及品牌 | Question -> AIAnswer without BrandMention |
| 优化外部来源 | 外部域名强依赖 | CitationSource -> SourceDomain |
| 开启监测 | 指标需要持续观察 | Recommendation -> MonitoringPlan |

前端展示：

```text
补官网证据页
官网引用率为 0.0%。优先补充增程技术、家庭用车、智能座舱和售后服务页面，让 AI 回答有可引用的品牌自有来源。

优先覆盖高频外部来源
本轮外部来源集中在 dongchedi.com、pcauto.com.cn。下一步应检查这些来源中是否准确呈现核心优势。
```

禁止：

```text
行动判断
创建监测计划（作为结论）
系统可执行
待确认对象
由 ActionRecord 触发
```

监测只能作为建议的可执行入口：

```text
开启周期监测
跟踪提及率、排名、官网引用率和语气变化。
```

点击后进入设置里的监测功能，不跳 Chat 完成监测。

## Chat 的定位

Chat 不是主流程主页，不承担“从零开始推进所有事情”的唯一入口。

Chat 是选中情报后的解释入口：

```text
解释这个提及率
列出提到理想汽车的回答
为什么官网没被引用
这个竞品为什么排名更高
哪些负向回答最需要处理
这个建议会影响哪个指标
```

Chat 上下文必须来自当前选中的图谱节点和相邻关系，不能把完整原始 prompt、内部对象名或动作记录暴露给用户。

回答结构固定：

```text
结论
证据
影响
需要确认什么
下一步建议
```

## 后端投影要求

为了支持前端四个页签，后端 `world` 接口不应只返回对象数量。它需要返回四类投影：

### 1. Summary Projection

给 `简要情报`：

```json
{
  "brand": {},
  "sample_scope": {},
  "metrics": {
    "mention_rate": {},
    "mention_ranking": {},
    "official_citation_rate": {},
    "sentiment_distribution": {}
  },
  "top_opportunity": {},
  "top_risk": {}
}
```

### 2. Evidence Projection

给 `情报来源`：

```json
{
  "mention_rate_detail": {
    "numerator": 70,
    "denominator": 96,
    "platform_rows": [],
    "answer_samples": []
  },
  "ranking_detail": {
    "brands": []
  },
  "official_citation_detail": {
    "official_domain": "lixiang.com",
    "official_citation_count": 0,
    "top_external_domains": []
  },
  "sentiment_detail": {
    "positive": [],
    "neutral": [],
    "negative": []
  }
}
```

### 3. Graph Projection

给 `品牌世界`：

```json
{
  "nodes": [
    { "id": "brand:lixiang", "label": "理想汽车", "type": "Brand" }
  ],
  "edges": [
    {
      "id": "mention:answer1:lixiang",
      "type": "HAS_MENTION",
      "from": "answer:1",
      "to": "mention:1",
      "strength": "strong"
    }
  ],
  "default_focus": "brand:lixiang",
  "expand_rules": []
}
```

### 4. Recommendation Projection

给 `跟进反馈`：

```json
{
  "recommendations": [
    {
      "title": "补官网证据页",
      "target_metric": "official_citation_rate",
      "reason": "官网引用率为 0.0%",
      "evidence_refs": [],
      "next_action": "open_monitoring_settings"
    }
  ]
}
```

## 验收标准

### 产品验收

1. 用户无需理解 Ontology，也能理解四个页签。
2. `简要情报` 一屏能回答品牌 AI 表现。
3. `情报来源` 能解释每个指标的分子、分母、平台、答案和来源。
4. `品牌世界` 是可遍历图谱，不是对象卡片列表。
5. `跟进反馈` 只展示业务建议和证据支撑，不展示内部任务流。
6. 监测入口进入设置里的监测功能。

### 文案验收

所有前端可见文案必须通过以下检查：

1. 是否用户关心。
2. 是否能指向一个指标、证据、来源、竞品或建议。
3. 是否删除后不影响理解。
4. 是否出现内部技术词。
5. 是否在解释系统自己，而不是解释品牌表现。

任何没有通过第 1、2 条的文案都应删除。

### 图谱验收

每个前端节点必须能回答：

1. 它是什么业务对象？
2. 它通过什么关系连接到品牌？
3. 它支撑哪个指标或判断？
4. 它能展开到哪些证据？
5. 它是否能触发一个业务建议？

每条边必须能回答：

1. 起点是什么？
2. 终点是什么？
3. 关系动词是什么？
4. 方向是否有业务意义？
5. 是否需要关系属性，还是应该升格成中间节点？

## 实施顺序

### P0：冻结前端自说自话文案

先删除或替换以下可见表达：

```text
这里解释
这些结论怎么来的
对象关系
品牌世界不是
世界主链
行动判断
处理反馈项
创建监测计划（作为情报来源或结论）
```

### P1：补后端四类投影

优先补：

1. mention rate detail。
2. ranking detail。
3. official citation detail。
4. sentiment detail。
5. graph projection。
6. recommendation projection。

### P2：重做四个页签

1. `简要情报`：经营摘要。
2. `情报来源`：指标展开。
3. `品牌世界`：图谱画布。
4. `跟进反馈`：建议和证据。

### P3：Chat 绑定图谱节点

Chat 入口必须携带：

```text
selected_node_id
selected_metric_key
evidence_refs
neighbor_scope
```

Chat 不从空白上下文解释品牌世界。

## 当前决策

1. `BrandMention` 必须成为一等节点。
2. `MetricSnapshot` 必须能追溯到样本范围、分子、分母和贡献节点。
3. `品牌世界` 必须是图谱投影，不是对象列表。
4. `情报来源` 必须围绕指标展开，不展示抽象探查路径。
5. `跟进反馈` 必须以建议为主，监测只是建议之一。
6. 前端禁止出现内部技术语言和自说自话文案。
