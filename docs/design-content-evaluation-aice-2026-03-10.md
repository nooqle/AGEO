# 内容评估能力设计方案（PM + UX 联合结论）

> **作者**: Marty Cagan + Don Norman + Martin Fowler
> **日期**: 2026-03-10
> **状态**: 方案初稿
> **参考输入**: `Doc/Agent design/AICE Agent.md`
> **目标**: 在不打破现有 Specta AI Chat + Canvas + Artifact 框架的前提下，新增“内容评估与修改建议”能力

---

## 1. 需求定义

用户希望在现有平台内，对以下三类内容进行评估、打分，并生成修改建议与评估报告：

1. A4 抓取回来的答案中，引用链接对应的网页内容
2. 用户主动输入的网页 URL
3. 用户主动输入的文本内容

目标不是新增一个独立工具页，而是在现有工作台中，让“评估内容质量”成为一种自然的新分析任务。

---

## 2. PM 与 UX 讨论结论

### 2.1 先回答“该不该做”

PM 结论：

- 这项能力和 Specta AI 当前“品牌在 AI 搜索中的可见性分析”高度相关，因为引用来源质量、页面可信度、文本客观性，直接影响 AI 采信概率。
- 它不是一个泛泛的 SEO 审核工具，而应被定义为“AI 采信友好度评估”。
- 最有价值的场景不是单纯给网页打分，而是回答两个问题：
  1. 为什么这段内容/这个页面容易被 AI 引用或忽略？
  2. 我应该怎么改，才能提高被 AI 采信的概率？

因此，这个需求值得做，而且是对现有 AEO 价值链的自然延伸。

### 2.2 先回答“该放在哪里”

UX 结论：

- 不建议新开独立页面，也不建议在 Dashboard 再长一个新模块。
- 最符合当前用户心智的入口仍然是 Chat。
- 最符合当前交付方式的结果承载仍然是 Canvas Artifact。
- 用户应该把它理解为“发起一类新的分析任务”，而不是“离开当前工作台去用另一个工具”。

最终共识：

1. **Chat 是发起入口**
2. **Canvas 是报告承载区**
3. **Artifact Nav 继续作为交付物导航**
4. **评估报告复用现有 `report` 渲染体系扩展，不额外创造一套平行 UI**

### 2.3 先回答“自动还是手动”

PM 关注：

- 如果默认对所有引用链接自动评估，成本高、时延长、噪声大
- 用户真正关心的是“重点引用值不值得信”“我自己的稿子/页面怎么改”

UX 关注：

- 自动跑全量会让流程变重，用户对系统在做什么也不容易建立预期
- 评估动作最好是显式触发，且要让用户知道当前评估的是哪一个来源

最终共识：

- **MVP 采用显式触发**
- 支持 3 个入口：
  1. 在抓取结果/引用卡片上点击“评估此引用”
  2. 在 Chat 中直接粘贴 URL 并要求评估
  3. 在 Chat 中直接粘贴文本并要求评估
- “批量评估全部引用”作为 Phase 2，而不是 MVP 默认行为

---

## 3. 设计原则

### 3.1 必须满足的约束

1. 不打破当前 `ChatLayout -> ChatPanel + CanvasPanel` 的结构
2. 不引入新的一级导航
3. 不破坏现有 WebSocket 编排、Artifact 输出、版本选择器能力
4. 结果必须能像现有报告一样被复制、导出、回看、版本化

### 3.2 体验原则

1. **Chat-first**：发起、确认、补充输入都在对话流里完成
2. **Artifact-first**：正式结果进入 Canvas，不挤占聊天正文
3. **Recognition over recall**：用户要看到“正在评估哪个来源”
4. **Progressive disclosure**：先给总分和结论，再展开维度明细和修改建议
5. **Actionable over descriptive**：报告重点是“可执行修改建议”，不是泛泛评论

---

## 4. 方案概览

### 4.1 能力名称

建议对外命名：

- 中文：**AI 采信评估**
- 英文内部名：**Content Evaluation / AICE Evaluation**

### 4.2 新能力在系统中的定位

建议新增一个新的专用 Agent：

- **A7 Content Evaluation Agent**

职责：

1. 识别输入源类型
2. 抽取评估对象内容
3. 按 AICE 规则评分
4. 产出“易被采信原因 / 需审慎原因 / 修改建议”
5. 输出结构化评估报告 Artifact

### 4.3 输入源类型

| 输入类型 | 来源 | MVP 支持 | 说明 |
| :--- | :--- | :--- | :--- |
| `citation_url` | A4 抓取结果中的引用链接 | 是 | 通过引用卡片快捷触发 |
| `user_url` | 用户在 Chat 中输入网页 URL | 是 | 公开网页 |
| `user_text` | 用户在 Chat 中粘贴文本 | 是 | 直接评估文案本身 |
| `file_text` | 用户上传 txt/pdf/docx 后抽取文本 | 否（Phase 2） | 当前上传链路未真正接入消息主链路 |

---

## 5. 与现有平台的契合方式

### 5.1 推荐入口

#### 入口 A：抓取结果中的引用卡片

在 `FetchResultsContent` 的每条 citation 行新增轻量操作：

- `评估此引用`
- Phase 2 再加：`加入批量评估`

点击后行为：

1. 将 citation URL 作为结构化上下文回填到 Chat
2. Chat 中出现一条用户消息，例如“评估这个引用来源”
3. 系统开始执行 A7

#### 入口 B：Chat 直接输入 URL

用户示例：

```text
帮我评估这个网页是否容易被 AI 采信：https://example.com/article
```

系统自动识别 URL，进入网页评估流程。

#### 入口 C：Chat 直接输入文本

用户示例：

```text
帮我评估下面这段品牌介绍，并给出修改建议：
...
```

系统识别为文本评估，不要求跳出当前对话。

### 5.2 推荐结果承载

结果仍走现有 Artifact 机制：

1. Chat 中给一段简洁结论
2. 同时推送 Canvas Artifact
3. Artifact Nav 出现新的交付物标签

建议不新增新的一级 Canvas 类型，而是：

- 继续复用 `report`
- 在 `report.data` 中新增 `report_kind: "content_evaluation"`

理由：

1. 现有 `CanvasHeader`、导出、复制、版本选择器都能直接复用
2. 对 `CanvasContentType`、OutputCard、ArtifactNav 的改动最小
3. 只需要在 `ReportContent.tsx` 中按 `report_kind` 切换渲染器

### 5.3 为什么不建议新建独立页面

不推荐方案：新增“内容评估页”

原因：

1. 打破当前 Chat 发起任务的主心智
2. 需要单独维护页面入口、状态、结果页、历史页
3. 与现有 Artifact 和多轮对话关系变弱
4. 技术实现成本更高，且可逆性更差

---

## 6. PM 推荐的产品边界

### 6.1 MVP 范围

MVP 做：

1. 单条引用 URL 评估
2. 用户输入 URL 评估
3. 用户粘贴文本评估
4. 输出结构化评估报告
5. 输出可执行修改建议

MVP 不做：

1. 自动评估全部引用
2. 文件上传文本评估
3. 批量 10+ 页面并发评估
4. Dashboard 聚合视图
5. 自动生成改写稿

### 6.2 成功指标

| 指标 | 目标 |
| :--- | :--- |
| 单次评估可交付率 | >= 90% |
| 用户能明确看懂“为什么被扣分” | >= 80% 主观反馈 |
| 用户能直接拿去改文案/改页面 | >= 70% 主观反馈 |
| 单页评估平均完成时间 | URL 模式 <= 90s，文本模式 <= 30s |

### 6.3 风险边界

1. 这不是事实真伪的绝对裁判
2. 这不是 SEO 全栈审计器
3. 这不是一键改稿器
4. 它的核心价值是“AI 采信友好度判断 + 修改方向”

---

## 7. UX 交互方案

### 7.1 主流程

```text
用户触发评估
  ->
系统识别输入源类型
  ->
Chat 中展示“评估对象确认”
  ->
执行 A7：抽取内容 -> 评分 -> 生成建议
  ->
Chat 返回摘要
  ->
Canvas 打开“内容评估报告”
```

### 7.2 评估对象确认

为了避免用户不知道当前在评估什么，建议在执行前通过轻量 Agent 消息确认：

#### URL 模式

```text
将评估以下网页：
- 来源类型：引用网页
- 域名：example.com
- 页面标题：How to choose ...

评估维度将包括：可访问性、结构化、时效性、可信度、可核查性、AI 采信风险。
```

#### 文本模式

```text
将评估您刚输入的文本内容：
- 来源类型：用户文本
- 长度：约 860 字
- 评估模式：文本适配版 AICE
```

这里不一定需要额外按钮确认。MVP 可以直接进入执行，只要对象说明清楚即可。

### 7.3 执行中反馈

复用现有 Action Log / Progress 体系，建议阶段如下：

| 阶段 | 用户可见文案 |
| :--- | :--- |
| `source_parse` | 正在识别输入源与抽取正文 |
| `content_extract` | 正在提取页面结构/引用证据 |
| `aice_score` | 正在按 AICE 维度评分 |
| `report_generate` | 正在生成评估报告与修改建议 |

### 7.4 报告信息架构

Canvas 中的评估报告建议沿用现有大卡片 + 分节布局，但内容改为以下结构：

#### 顶部摘要区

展示：

1. 报告标题：`内容评估报告`
2. 评估对象：来源标题 / URL / 文本摘要
3. 总分：`AI 采信友好度指数`
4. 评分档位：`高 / 中 / 低`
5. 一句话结论

#### Section 1：算式验证区块

严格承接 AICE 设计：

```text
C6 + C9a + C9b + C8 + C1 + C4 + C2 + C3 + C5 + C7 = 总分
```

这是用户建立信任的关键，不能省略。

#### Section 2：维度得分表

表格字段：

| 维度 | 满分 | 得分 | 发现 | 风险等级 |

该区是整个报告的“证据骨架”。

#### Section 3：容易被 AI 采信的原因

展示 2-4 条高置信原因，配证据片段。

#### Section 4：需审慎对待的原因

展示技术、时效、宣传、引用链不足等风险。

#### Section 5：优化与修改建议

这是 UX 重点区，必须改成任务导向：

| 问题 | 操作建议 | 示例改写/代码 | 预期提升维度 |

用户读完后应该知道“下一步怎么改”，而不是只知道“有问题”。

#### Section 6：证据与原文锚点

对网页评估，建议给出：

1. 页面标题
2. 域名
3. 发布时间
4. 抽取到的 H1 / Schema / 外部引用数量
5. 关键证据摘录

### 7.5 报告样式如何嵌入现有 UI

建议复用现有 `ReportContent` 外层样式：

1. 顶部 Hero 区保持当前 Report Artifact 风格
2. Section 卡片继续使用圆角边框卡片
3. 指标卡继续使用当前 summary metric 视觉语言
4. 仅替换中间内容，不重新发明皮肤

这样能保证：

1. 视觉上仍是同一平台产物
2. 不会出现“另一个产品”的割裂感
3. 前端开发量最小

---

## 8. AICE 评分适配策略

### 8.1 网页 / 引用链接：使用 AICE-Web

直接遵循参考文档中的 9C 细化加权评分：

1. C6 Coverage
2. C9a Semantic Tagging
3. C9b Schema Usage
4. C8 Timeliness
5. C1 Credibility
6. C4 Claim Balance
7. C2 Consistency
8. C3 Checkability
9. C5 Clarity
10. C7 Intent Match

### 8.2 用户文本：使用 AICE-Text 适配版

问题在于用户直接输入文本时，没有网页 DOM，也没有 Schema。

如果仍按网页标准硬扣，会让结果失真。建议做“同框架映射”，而不是假装它是网页。

建议映射如下：

| 原维度 | 文本适配解释 |
| :--- | :--- |
| C6 Coverage | 输入材料完整度，是否具备标题、主体、来源说明 |
| C9a Semantic Tagging | 文本结构化程度，是否有标题、小节、列表、清晰段落 |
| C9b Schema Usage | 来源元信息完整度，是否标明作者、机构、日期、引用出处 |
| 其余维度 | 保持原义 |

这样可以实现：

1. 仍然保留 100 分制
2. 用户能理解为什么文本也会有“结构”和“出处”得分
3. 页面与文本报告结构保持一致

### 8.3 报告中必须显示“评分模式”

顶部摘要区必须明确显示：

- `评分模式：AICE-Web`
或
- `评分模式：AICE-Text（适配版）`

避免用户误以为两类输入完全同标尺。

---

## 9. 数据与技术方案

### 9.1 推荐输出契约

建议新增 `report_kind = "content_evaluation"` 的 report payload：

```json
{
  "report_kind": "content_evaluation",
  "headline": "内容评估报告",
  "subtitle": "example.com / 2026-03-10",
  "overallScore": 76,
  "scoreBand": "中高",
  "evaluation_mode": "aice_web",
  "overall_confidence": 0.88,
  "source": {
    "source_type": "citation_url",
    "title": "How to choose ...",
    "url": "https://example.com/...",
    "domain": "example.com",
    "captured_at": "2026-03-10T10:00:00Z"
  },
  "formula": {
    "items": [
      { "code": "C6", "score": 25 },
      { "code": "C9a", "score": 5 }
    ],
    "expression": "25 + 5 + ... = 76"
  },
  "dimension_scores": [],
  "trusted_reasons": [],
  "caution_reasons": [],
  "recommendations": [],
  "evidence": []
}
```

### 9.2 前端推荐改动点

| 模块 | 建议改动 |
| :--- | :--- |
| `FetchResultsContent.tsx` | 新增 citation 快捷操作“评估此引用” |
| `ChatPanel.tsx` | 允许发送结构化评估请求 |
| `useWebSocket.ts` | 支持发送 `evaluation_request` 或扩展 `user_message` data |
| `ReportContent.tsx` | 根据 `report_kind` 分流到 `EvaluationReportContent` |
| 新组件 `EvaluationReportContent.tsx` | 负责评估报告正文渲染 |

### 9.3 后端推荐改动点

| 模块 | 建议改动 |
| :--- | :--- |
| Orchestrator | 新增“内容评估”意图识别与路由 |
| 新 Agent / Service | A7 Content Evaluation Agent |
| 内容抽取层 | 支持 URL 正文抽取、HTML 结构检查、Schema 检查 |
| `events.py` | 支持自定义 artifact id，避免所有评估都挤到同一个 Tab |
| `message_service.py` | 用户消息 metadata 中记录评估对象 |

### 9.4 一个关键架构点：Artifact ID 不能只按 output_type 固定

当前 `save_and_send_artifact()` 默认使用：

```text
{session_id}_{output_type}
```

这适合“基线报告覆盖旧版本”的场景，但不适合“同一会话内评估多个不同来源”的场景。

因此推荐：

1. 为评估报告引入可选 `artifact_id`
2. 格式建议：`{session_id}_report_eval_{source_hash}`

这样同一会话中可以并存：

1. 多个不同来源的评估报告 Tab
2. 同一来源再次评估时仍可走版本历史

这是本方案最关键的技术细节之一。

### 9.5 A7 Agent Prompt 设计

这里补的是**真正可落地的 Prompt 结构**，用于 Orchestrator 路由和 A7 评估执行。

#### 9.5.1 Orchestrator 路由 Prompt 增量

Orchestrator 需要新增一段明确的路由规则：

```text
当用户要求“评估网页/评估文案/评估引用来源/判断是否容易被 AI 采信/给出修改建议”时，
优先识别为 content_evaluation 意图，而不是通用问答。

如果输入中包含：
- 单个 URL：走 single_content_evaluation(source_type=user_url)
- 多个 URL：走 batch_content_evaluation(batch_type=url)
- 单段文本：走 single_content_evaluation(source_type=user_text)
- 多段文本：走 batch_content_evaluation(batch_type=text)
- 来自抓取结果的 citation 上下文：走 single_content_evaluation(source_type=citation_url)

输出要求：
1. 先给用户一条简短说明，明确当前评估对象与评分模式
2. 然后调用 A7 生成结构化评估结果
3. 将结果保存为 Artifact，并在聊天中给出摘要结论
```

#### 9.5.2 A7 System Prompt 骨架

A7 的系统 Prompt 建议按“角色 + 输入识别 + 评分规则 + 输出约束”四段组织。

```text
你是一名专业的 AI 采信评估 Agent（A7 Content Evaluation Agent）。
你的任务是对网页内容、引用来源或用户输入文本进行 AI 采信友好度评估，
并输出结构化评分、风险原因、证据锚点和可执行修改建议。

## 输入类型
你会收到以下之一：
1. citation_url
2. user_url
3. user_text
4. batch_url
5. batch_text

## 评分模式
- citation_url / user_url: 使用 AICE-Web
- user_text: 使用 AICE-Text
- batch_url: 对每一项使用 AICE-Web，再聚合
- batch_text: 对每一项使用 AICE-Text，再聚合

## AICE-Web 维度
C6, C9a, C9b, C8, C1, C4, C2, C3, C5, C7

## AICE-Text 映射
- C6 = 内容完整度
- C9a = 文本结构化程度
- C9b = 来源元信息完整度
- 其余维度保持原义

## 输出硬性要求
1. 必须给出每个维度分数
2. 必须给出总分求和算式
3. 必须区分“容易被 AI 采信”与“需审慎对待”
4. 必须给出至少 2 条可执行修改建议
5. 修改建议必须包含：问题、动作、示例、原因
6. 若网页抽取失败，必须返回可访问性风险与降级说明
7. 输出必须是严格 JSON，不输出额外解释
```

#### 9.5.2.1 必须内嵌到 Prompt 的 9C 评分矩阵

A7 不是“参考”这张表，而是必须把这张表作为评分约束直接写入 Prompt：

| 评估维度 (C#) | 评估内容 | 权重 (%) | 满分 | 扣分/评分机制简述 |
| :--- | :--- | :--- | :--- | :--- |
| **C6: Coverage** | 技术可访问性/核心路径权重 | 25% | 25 | **C6a**: 爬虫不可读则 `C6=0`；核心路径且可访问时取高分 |
| **C9a: Semantic Tagging** | H1-H6, article, main 等语义标签 | 10% | 10 | **硬扣**: 缺失 H1 或关键结构标签，直接 `-5` |
| **C9b: Schema Usage** | Schema.org 结构化数据 | 10% | 10 | **硬扣**: 未发现 Schema 标记，直接 `-5` |
| **C8: Timeliness** | 日期清晰度与内容寿命 | 15% | 15 | 日期清晰且内容高寿命高分；过期内容重扣 |
| **C1: Credibility** | 发布主体可信度 | 10% | 10 | 官方/权威高分，商业站点基准，非权威低分 |
| **C4: Claim Balance** | 宣传平衡性 | 10% | 10 | 主观夸大、绝对化宣称越多，得分越低 |
| **C2: Consistency** | 与主流事实吻合度 | 5% | 5 | 与行业共识/规范一致则高分 |
| **C3: Checkability** | 数据与外链可核查性 | 5% | 5 | 官方公告、DOI、权威链接越充分分越高 |
| **C5: Clarity** | 结构清晰度 | 5% | 5 | 逻辑清楚、重点明确则高分 |
| **C7: Intent Match** | 查询意图匹配度 | 5% | 5 | 与高频大众查询意图匹配则高分 |

#### 9.5.2.2 Prompt 中必须明确的硬性规则

为了避免模型自由发挥，Prompt 必须写成硬规则，而不是建议语气：

```text
你必须严格执行以下规则：
1. 如果页面不可读或正文无法抽取，则 C6 = 0，不得给更高分。
2. 如果缺失 H1，或缺失 main/article 等关键结构标签，则 C9a 至少扣 5 分。
3. 如果未发现 Schema.org 标记，则 C9b 至少扣 5 分。
4. 你必须输出每个维度的评分逻辑与扣分原因。
5. 你必须输出完整求和算式，并确保各维度分数之和等于 overallScore。
6. 如果证据不足，允许降低 confidence，但不得跳过维度评分。
7. 如果某项判断来自推断而不是直接证据，必须在 finding 中标明“推断”。
```

#### 9.5.2.3 置信度评估机制

你指出的“怎么保证 Agent 做置信度评估”，关键不是再加一句“请评估置信度”，而是把置信度拆成独立字段和生成规则。

A7 的置信度建议分两层：

1. **维度置信度** `dimension_confidence`
2. **整体结论置信度** `overall_confidence`

Prompt 中必须写明：

```text
你必须为每个维度输出 confidence，取值范围 0-1。
confidence 代表“该维度评分结论的证据充分程度”，不是好坏分数。

高置信度（0.85-1.0）：
- 结构/Schema/可访问性等有直接机器证据
- 来源主体可被明确识别
- 日期、外链、结构信息清晰完整

中置信度（0.60-0.84）：
- 能从正文与部分元信息推断，但证据不完整
- 一致性或意图匹配需要一定语义判断

低置信度（<0.60）：
- 页面抽取不完整
- 发布时间、主体、出处缺失
- 一致性或可核查性只能弱推断
```

此外，整体置信度不应是模型随手给的主观值，建议按以下方式生成：

```text
overall_confidence =
  0.35 * extract_quality +
  0.35 * evidence_completeness +
  0.30 * avg(dimension_confidence)
```

其中：

- `extract_quality`：正文抽取、DOM 解析、结构信息获取是否完整
- `evidence_completeness`：日期、来源、外链、Schema 等是否充分
- `avg(dimension_confidence)`：各维度 confidence 平均值

#### 9.5.2.4 为什么这样能保证 Agent 不跑偏

保证机制不是单靠 Prompt，而是三层：

1. **特征先抽取**：先由程序给 A7 提供 `crawl_readable`、`has_h1`、`has_main`、`schema_types`、`published_at`、`external_links_count` 等特征
2. **Prompt 强约束**：在 Prompt 里写死 9C 权重、硬扣规则、算式输出和 confidence 规则
3. **输出校验**：后处理阶段检查总分求和、硬扣规则是否命中、字段是否完整，不合法则重试或降级

#### 9.5.3 单条网页/文本评估 User Prompt 模板

```json
{
  "task": "single_content_evaluation",
  "source_type": "user_url",
  "evaluation_mode": "aice_web",
  "overall_confidence": 0.88,
  "source": {
    "url": "https://example.com/article",
    "title": "Example Article",
    "domain": "example.com"
  },
  "content_bundle": {
    "main_text": "...",
    "h1": "...",
    "headings": ["..."],
    "published_at": "2025-11-01",
    "schema_types": ["Article"],
    "external_links": ["..."]
  },
  "instruction": "请输出结构化评估报告数据。"
}
```

```json
{
  "task": "single_content_evaluation",
  "source_type": "user_text",
  "evaluation_mode": "aice_text",
  "source": {
    "label": "用户输入文本"
  },
  "content_bundle": {
    "text": "这里是用户输入的文案正文..."
  },
  "instruction": "请输出结构化评估报告数据。"
}
```

#### 9.5.4 批量聚合 Prompt 模板

批量不建议让一个 Prompt 同时负责抽取、逐条评分、聚合汇总。推荐拆成两层：

1. **item evaluator prompt**：逐条输出标准化 item result
2. **batch aggregator prompt**：读取 item result 列表，输出批量总览报告和明细表

批量聚合 Prompt 示例：

```json
{
  "task": "batch_content_aggregation",
  "batch_type": "url",
  "items": [
    {
      "item_id": "item_001",
      "status": "success",
      "overall_score": 61,
      "score_band": "medium",
      "top_risk_dimension": "C9b",
      "dimension_scores": [...],
      "recommendations": [...]
    },
    {
      "item_id": "item_002",
      "status": "failed",
      "failure_reason": "content_extract_failed"
    }
  ],
  "instruction": "请输出批量总览报告与明细表数据。"
}
```

### 9.6 单条报告数据形式

单条报告建议继续复用 `report` Artifact，关键是 `report_kind = content_evaluation`。

#### 9.6.1 单条报告 JSON 结构

```json
{
  "report_kind": "content_evaluation",
  "headline": "内容评估报告",
  "subtitle": "example.com / AICE-Web",
  "overallScore": 76,
  "scoreBand": "medium_high",
  "evaluation_mode": "aice_web",
  "overall_confidence": 0.88,
  "summary": {
    "one_line": "基础可信度较好，但结构化和可核查性仍不足。",
    "status": "needs_improvement"
  },
  "source": {
    "source_type": "citation_url",
    "title": "How to choose skincare products",
    "url": "https://example.com/article",
    "domain": "example.com",
    "captured_at": "2026-03-11T10:00:00Z"
  },
  "formula": {
    "items": [
      { "code": "C6", "score": 25 },
      { "code": "C9a", "score": 5 },
      { "code": "C9b", "score": 5 },
      { "code": "C8", "score": 10 },
      { "code": "C1", "score": 8 },
      { "code": "C4", "score": 6 },
      { "code": "C2", "score": 5 },
      { "code": "C3", "score": 4 },
      { "code": "C5", "score": 4 },
      { "code": "C7", "score": 4 }
    ],
    "expression": "25 + 5 + 5 + 10 + 8 + 6 + 5 + 4 + 4 + 4 = 76"
  },
  "dimension_scores": [
    {
      "code": "C9b",
      "label": "Schema Usage",
      "max_score": 10,
      "score": 5,
      "severity": "medium",
      "confidence": 0.93,
      "finding": "未发现充分的结构化数据标记。"
    }
  ],
  "trusted_reasons": [
    {
      "title": "来源域名具有基础可信度",
      "dimensions": ["C1", "C2"],
      "evidence": "页面内容与行业常识基本一致。"
    }
  ],
  "caution_reasons": [
    {
      "title": "结构化数据不足",
      "dimensions": ["C9b"],
      "evidence": "未发现 JSON-LD Article 标记。"
    }
  ],
  "recommendations": [
    {
      "dimension": "C9b",
      "issue": "缺少结构化数据",
      "action": "在 head 中补充 JSON-LD Article 标记",
      "example": "<script type=\"application/ld+json\">...</script>",
      "reason": "帮助 AI 和搜索系统识别页面主体信息"
    }
  ],
  "evidence": [
    {
      "type": "heading",
      "label": "H1",
      "value": "How to choose skincare products"
    }
  ],
  "degradation_note": null
}
```

#### 9.6.2 字段说明

| 字段 | 说明 |
| :--- | :--- |
| `report_kind` | 前端分流渲染的关键字段 |
| `evaluation_mode` | `aice_web` 或 `aice_text` |
| `formula` | 供“算式验证区块”直接展示 |
| `dimension_scores` | 维度明细表数据源 |
| `trusted_reasons` | “容易被 AI 采信”区块数据源 |
| `caution_reasons` | “需审慎对待”区块数据源 |
| `recommendations` | 修改建议表数据源 |
| `evidence` | 证据锚点区块数据源 |

### 9.7 批量报告数据形式

批量至少需要 2 个主产物：

1. `report_kind = content_evaluation_batch`
2. `dataTable` 明细表

#### 9.7.1 批量总览报告 JSON 结构

```json
{
  "report_kind": "content_evaluation_batch",
  "headline": "批量内容评估总览",
  "subtitle": "12 个网页 / AICE-Web",
  "overallScore": 64,
  "scoreBand": "medium",
  "batch_summary": {
    "batch_id": "batch_001",
    "batch_type": "url",
    "total_items": 12,
    "success_count": 9,
    "failed_count": 3,
    "average_score": 64,
    "median_score": 66,
    "lowest_score": 38,
    "high_risk_count": 4
  },
  "dimension_distribution": [
    { "code": "C9a", "low_score_count": 6 },
    { "code": "C9b", "low_score_count": 7 },
    { "code": "C3", "low_score_count": 5 }
  ],
  "top_risks": [
    {
      "item_id": "item_004",
      "title": "Landing Page A",
      "overall_score": 38,
      "top_risk_dimension": "C4"
    }
  ],
  "batch_recommendations": [
    {
      "title": "优先统一补齐结构化数据",
      "reason": "C9b 在本批次中是最普遍短板"
    }
  ]
}
```

#### 9.7.2 批量明细表 JSON 结构

```json
{
  "columns": [
    { "key": "index", "label": "序号" },
    { "key": "source_type", "label": "类型" },
    { "key": "title_or_excerpt", "label": "标题/摘要" },
    { "key": "overall_score", "label": "总分" },
    { "key": "score_band", "label": "档位" },
    { "key": "top_risk_dimension", "label": "最高风险维度" },
    { "key": "status", "label": "状态" },
    { "key": "detail_artifact_id", "label": "详情" }
  ],
  "rows": [
    {
      "index": 1,
      "item_id": "item_001",
      "source_type": "url",
      "title_or_excerpt": "How to choose skincare products",
      "overall_score": 61,
      "score_band": "medium",
      "top_risk_dimension": "C9b",
      "status": "success",
      "detail_artifact_id": "session_x_report_eval_item_item_001"
    },
    {
      "index": 2,
      "item_id": "item_002",
      "source_type": "text",
      "title_or_excerpt": "我们是全球领先的品牌...",
      "overall_score": 44,
      "score_band": "low",
      "top_risk_dimension": "C4",
      "status": "success",
      "detail_artifact_id": "session_x_report_eval_item_item_002"
    },
    {
      "index": 3,
      "item_id": "item_003",
      "source_type": "url",
      "title_or_excerpt": "example.com/page",
      "overall_score": null,
      "score_band": null,
      "top_risk_dimension": null,
      "status": "failed",
      "failure_reason": "content_extract_failed",
      "detail_artifact_id": null
    }
  ]
}
```

#### 9.7.3 单项结果标准化结构

为了便于批量聚合，建议 A7 对每一项先输出统一 item result：

```json
{
  "item_id": "item_001",
  "source_type": "url",
  "status": "success",
  "evaluation_mode": "aice_web",
  "overall_confidence": 0.88,
  "overall_score": 61,
  "score_band": "medium",
  "top_risk_dimension": "C9b",
  "formula": {
    "expression": "... = 61"
  },
  "dimension_scores": [],
  "recommendations": [],
  "detail_artifact_id": "session_x_report_eval_item_item_001"
}
```

---

## 10. 推荐交互形态

### 10.1 单来源评估

最推荐的 MVP 形态：

1. 用户点击一个引用，或输入一个 URL / 一段文本
2. 系统产出一个独立的评估报告 Artifact
3. 该 Artifact 可被重复评估并进入 versions

### 10.2 批量评估总原则

批量评估不建议做成“一个超长报告”，而建议采用：

1. **一个批量总览报告**：用于看整体风险、平均分、优先级
2. **一个批量明细表**：用于逐条查看评分结果
3. **多个单项详情报告**：仅对用户点开或低分项生成

这样做的原因：

1. 更契合现有 `report + dataTable + report` 的 Artifact 结构
2. 能复用现有 Canvas 多交付物导航
3. 用户既能总览，也能按条追查，不会被一个大报告淹没

### 10.3 批量输入方式

建议支持 3 种输入方式，并统一进入 `batch_evaluation` 流程：

1. **批量 URL**：用户在 Chat 中一次输入多条 URL，一行一个
2. **批量文本**：用户一次粘贴多段文本，使用固定分隔符拆分
3. **结构化文件导入**：Phase 2 支持上传 `csv/txt/json`

推荐的输入协议：

```text
请批量评估下面这些网页：
https://a.com/1
https://b.com/2
https://c.com/3
```

```text
请批量评估下面 3 段文案：
===ITEM===
文案 1
===ITEM===
文案 2
===ITEM===
文案 3
```

系统侧统一规范为：

```json
{
  "batch_id": "batch_xxx",
  "items": [
    {
      "item_id": "item_001",
      "source_type": "user_url",
      "url": "https://a.com/1"
    },
    {
      "item_id": "item_002",
      "source_type": "user_text",
      "text": "..."
    }
  ]
}
```

### 10.4 批量结果结构

批量任务完成后，建议至少输出两个主 Artifact：

1. **批量总览报告** `report`
2. **批量评分明细表** `dataTable`

如用户点击某一行的“查看详情”，再打开该条对应的单项 `report`。

#### 批量总览报告应包含

1. 平均分 / 中位分 / 最低分
2. 高风险项数量
3. 按维度的低分分布
4. 最值得优先处理的 Top N 页面/文本
5. 批量修改建议摘要

#### 批量评分明细表应包含

| 项目 | 类型 | 标题/摘要 | 总分 | 档位 | 最高风险维度 | 状态 | 操作 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| item_001 | url | 页面标题 | 61 | 中 | C9b | success | 查看详情 |
| item_002 | text | 文本前 40 字 | 44 | 低 | C4 | success | 查看详情 |
| item_003 | url | example.com/... | - | 失败 | 抽取失败 | failed | 重试 |

### 10.5 批量执行与并发策略

批量流程建议拆成 5 步：

1. `batch_parse`
2. `content_extract`
3. `aice_score`
4. `aggregate`
5. `report_generate`

其中 URL 与文本的执行策略不同：

- **批量文本**：优先支持，可较高并发
- **批量网页**：后做，建议限流并发 `3-5`

必须处理以下三类状态：

1. 成功
2. 部分成功
3. 单项失败但批量任务整体完成

批量任务的用户心智应该是：

- “这一批已经跑完，但其中有几条失败了”
- 而不是“只要有一条失败，整个任务就失败”

### 10.6 批量 Artifact ID 规则

批量场景下，不能继续只按 `{session_id}_{output_type}` 生成 Artifact ID。

建议规则：

1. 批量总览：`{session_id}_report_eval_batch_{batch_id}`
2. 批量表格：`{session_id}_datatable_eval_batch_{batch_id}`
3. 单项详情：`{session_id}_report_eval_item_{item_id}`

这样可以保证：

1. 同一会话可并存多批任务
2. 同一批中的不同项不会互相覆盖
3. 同一项重复评估时仍可进入版本历史

---

## 11. 用户流程示例

### 11.1 场景一：评估抓取回来的引用

```text
用户在抓取结果里看到一个 citation
  ->
点击“评估此引用”
  ->
Chat 中出现“正在评估 example.com 这条引用来源”
  ->
A7 执行
  ->
Canvas 打开 内容评估报告
  ->
用户查看扣分项和修改建议
```

### 11.2 场景二：评估用户自己的网页

```text
用户输入 URL
  ->
系统识别为 user_url
  ->
执行 AICE-Web
  ->
输出报告
```

### 11.3 场景三：评估用户自己的文案

```text
用户粘贴文案
  ->
系统识别为 user_text
  ->
执行 AICE-Text
  ->
输出报告 + 文案层面的修改建议
```

### 11.4 场景四：批量评估多个网页

```text
用户一次输入 10 条 URL
  ->
系统创建 batch_evaluation 任务
  ->
逐条抽取正文并评分
  ->
Canvas 输出：批量总览报告 + 批量评分明细表
  ->
用户点击低分项“查看详情”
  ->
打开该项单独评估报告
```

### 11.5 场景五：批量评估多段文本

```text
用户一次输入多段文案
  ->
系统按分隔符切分为多个 item
  ->
逐条执行 AICE-Text
  ->
输出批量总览报告 + 明细表
  ->
用户根据明细表筛选出最差的 3 条优先修改
```

---

## 12. 分期建议

### Phase 1：单来源 MVP

1. 单条引用 URL 评估
2. 用户 URL 评估
3. 用户文本评估
4. `report_kind = content_evaluation`
5. 独立评估报告 Artifact

### Phase 1.5：批量文本 MVP

1. 支持一次输入多段文本
2. 输出批量总览报告
3. 输出批量评分明细表
4. 支持从明细表打开单项详情

### Phase 2：批量网页增强版

1. 支持一次输入多条 URL
2. 支持限流并发抓取与失败重试
3. 支持部分成功状态汇总
4. 支持批量任务中的单项重跑

### Phase 3：文件导入与闭环优化

1. 上传 `csv/txt/json` 批量导入
2. 一键复制修改建议
3. 从评估报告直接生成“优化后版本”
4. 将评估结果回写到品牌优化任务队列
5. 在 Dashboard 上展示“内容资产 AI 采信健康度”

---

## 13. 风险与缓解

| 风险 | 影响 | 缓解 |
| :--- | :--- | :--- |
| URL 页面抽取失败或被反爬 | 无法完整评分 | 降级为“可访问性风险”并在报告中说明 |
| 文本模式与网页模式分数可比性被误解 | 用户理解偏差 | 顶部必须展示评分模式 |
| 同一会话评估多个来源导致报告覆盖 | 交付物混乱 | 引入 `artifact_id` 覆盖策略 |
| 文件上传链路当前未接入主分析链路 | MVP 范围不稳 | MVP 先只做 URL + 粘贴文本 |
| 批量 URL 并发过高导致超时/封禁 | 任务稳定性下降 | 对 URL 抽取设置并发上限与退避重试 |
| 批量任务中单项失败拖垮整批 | 用户体验差 | 采用“部分成功”模型，单项失败单独标记 |
| 批量结果过长难以消费 | 用户找不到重点 | 固定为“总览报告 + 明细表 + 按需详情”三层结构 |

---

## 14. 最终推荐方案

### 推荐结论

**做，而且应该做成“现有 Chat 工作台中的新分析任务”，而不是新页面。**

### 最终形态

1. 新增 **A7 Content Evaluation Agent**
2. 入口放在 **Fetch Results 引用操作 + Chat URL/文本输入**
3. 结果承载在 **现有 Canvas Artifact**
4. 报告类型复用 **`report` + `report_kind = content_evaluation`**
5. 网页走 **AICE-Web**，文本走 **AICE-Text 适配版**
6. 演进路径采用 **单来源 -> 批量文本 -> 批量网页 -> 文件导入**

### 这是最适合当前平台的原因

1. 符合现在的 Chat-first 工作流
2. 保留现有 Canvas / OutputCard / 版本历史机制
3. 能自然扩展到批量任务，而不需要重做页面框架
4. 用户几乎不用重新学习平台

---

## 15. 实施清单

### 后端

1. 新增 A7 Content Evaluation Agent
2. 新增 URL / 文本输入识别与路由
3. 新增 AICE-Web / AICE-Text 评分器
4. 扩展 Artifact 保存逻辑，支持自定义 `artifact_id`
5. 输出 `report_kind = content_evaluation`
6. 新增 `batch_evaluation` 聚合流程与部分成功模型
7. 为 URL 批量任务增加并发控制与失败重试

### 前端

1. `FetchResultsContent` 新增“评估此引用”操作
2. `ReportContent` 增加 `content_evaluation` 分支
3. 新建 `EvaluationReportContent`
4. 新增批量评分 `dataTable` 渲染与跳转详情能力
5. 在 Artifact Nav 中沿用现有 `report` / `dataTable` 导航，不新增一级类型

### 联调验收

1. URL 评估能正确出报告
2. 文本评估能正确出报告
3. 单来源重复评估能进入版本历史
4. 同一会话多个来源评估不会互相覆盖
5. 批量文本能输出总览报告与明细表
6. 批量网页出现部分失败时，任务仍能交付可用结果

---

## 16. 补充：主 LLM 的意图判断策略

### 16.1 先说结论

不要新增一套独立的、前置的 intent classifier 来替代主 LLM。

推荐方案是：

```text
入口上下文约束 -> 轻量信号抽取 -> 主 LLM 受限工具选择 -> Guard 校验 -> 模糊确认
```

### 16.2 判断目标要拆成两个字段

主 LLM 不应该输出一个开放式“用户总意图”，而应该只在给定上下文内判断：

1. `task_family`
   - `content_evaluation`
   - `answer_fetch`
   - `question_simulation`
   - `brand_analysis`
   - `ambiguous`

2. `source_type`
   - `citation_url`
   - `user_url`
   - `user_text`
   - `custom_questions`
   - `mixed`

### 16.3 轻量信号抽取先吃掉确定性高的输入

在调用主 LLM 前，程序先抽取：

1. citation 触发上下文
2. URL 数量
3. 是否存在长正文
4. 是否存在多行问题列表
5. 是否命中评估类动作词
6. 是否命中抓取类动作词

建议直接短路的情况：

1. citation 点击 -> `content_evaluation:citation_url`
2. 单个 URL + 评估词 -> `content_evaluation:user_url`
3. 长文本 + 评估词 -> `content_evaluation:user_text`
4. 多行问题 + 抓取词 -> `answer_fetch:custom_questions`

### 16.4 主 LLM 只做受限工具选择

推荐主 LLM 输出：

```json
{
  "task_family": "content_evaluation",
  "source_type": "user_url",
  "confidence": 0.89,
  "reason_codes": ["has_single_url", "contains_evaluation_verbs"],
  "needs_confirmation": false
}
```

主 LLM 不能自创分类名称，也不能跳出当前入口允许的工具边界。

如果入口来自 `置信度信号` 交付物中的 `额外评估` 输入框，则默认应带上：

```json
{
  "entrypoint": "confidence_signal_extra_eval",
  "allowed_tools": ["a7_extra_evaluate"],
  "allowed_input_types": ["url", "text"]
}
```

此时主 LLM 的职责不再是判断“是不是评估”，而是判断：

1. 输入是链接还是文本
2. 是否可以直接驱动 A7 做一次额外评估
3. 是否需要 ask_user 澄清

### 16.5 低置信度就 ask_user

以下情况不要继续猜：

1. `confidence < 0.75`
2. `source_type = mixed`
3. `task_family = ambiguous`
4. 同时命中评估词和抓取词
5. 同时存在长正文和问题列表

推荐只给两个确认动作：

1. `评估这篇内容并给出修改建议`
2. `把这些问题拿去抓 AI 回答`

### 16.6 对 A7 的边界价值

经过这层路由后，A7 只接三类稳定输入：

1. `content_evaluation:citation_url`
2. `content_evaluation:user_url`
3. `content_evaluation:user_text`

而 `answer_fetch:custom_questions` 继续进入 A4。

这样可以把“文章分析”和“自定义问题”稳定分开，同时保留“由主 LLM 驱动 A7”的架构方向，而不是额外引入一套刻意的意图判断模块。





