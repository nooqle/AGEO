# Specta 品牌情报任务中枢设计（2026-05-25）

> 状态：Confirmed for implementation
> 目标：解决 Dashboard、Chat、后台执行之间的流程断点，把 Specta 从“Chat 驱动的一次性分析”升级为“品牌情报任务驱动的持续工作台”。
> 非目标：本文档不直接改 UI 细节、不设计完整任务表迁移、不替代品牌知识图谱设计；它定义任务主线和产品边界，后续开发按本文拆阶段落地。

## 已确认决策

1. 新增 `brand_intelligence_runs` 表，`BrandIntelligenceRun` 是 Dashboard 看到的任务状态真相源。
2. Dashboard 的“开始分析 / 继续采集”默认后台执行，不默认打开 Chat。
3. 右下角 Chat 气泡是统一的上下文入口；它携带 `runId / entityId / intent / handoffId` 进入 Chat。
4. Dashboard 内部监测看板永久移除；监测配置统一进入 Settings。
5. 用户点击气泡只是进入解释和确认语境时，可以创建 `not_started` 的上下文 run，但不能误显示为后台正在执行。

## 一句话结论

Specta 需要新增一个产品和系统层面的核心对象：

```text
BrandIntelligenceRun = 一次品牌情报任务
```

它负责把“分析这个品牌在 AI 世界里的表现”拆成可持续执行的流程，并持久记录：

1. 当前任务是什么。
2. 现在做到哪一步。
3. 已经产出什么。
4. 是否需要用户确认。
5. 后台是否会继续推进。
6. 最终沉淀到哪些情报、证据、品牌世界和建议。

Dashboard 是这个任务的主界面。
Chat 是解释、追问、确认、调整范围的入口。
Orchestrator 是后台执行者。
品牌知识图谱是任务结果沉淀后的事实网络。

## 为什么必须做这个

当前产品有一个根问题：

```text
用户在 Chat 里发起分析，退出 Chat 后，Dashboard 不知道这轮分析是否还在继续；
Dashboard 看到样本不足，但不知道应该自动推进、让用户确认，还是停在那里；
跟进反馈可能在样本没形成前出现，导致建议无效；
Chat 和 Dashboard 像两个断开的产品。
```

只加一个“回到 Chat”按钮不够。因为用户真正需要的不是回到对话，而是知道：

```text
我的品牌情报任务现在是什么状态？
系统会不会继续做？
如果卡住了，我应该处理什么？
如果完成了，我应该看哪个判断和证据？
```

所以缺失的是任务中枢，不是页面跳转。

## 产品定位

### 1. Dashboard 的定位

Dashboard 是品牌情报任务和情报结果的主界面。

它负责展示：

- 当前品牌。
- 当前情报任务状态。
- 样本口径。
- AI 提及率、提及排名、官网引用率、语气性质。
- 情报来源。
- 品牌世界。
- 跟进建议。
- 需要用户处理的确认事项。

Dashboard 不应该让用户猜下一步，也不应该在样本不足时展示商业化建议。

### 2. Chat 的定位

Chat 不是唯一主线发动机。

Chat 负责：

- 解释某个指标。
- 追问某条证据。
- 调整分析范围。
- 处理需要自然语言交互的确认。
- 让用户补充业务背景。
- 对已经形成的情报继续分析。

Chat 可以发起任务，也可以接管任务中的确认，但任务本身必须独立存在。

Chat 的入口只有两类：

1. `携带上下文`：来自 Dashboard 的指标、证据、建议、确认项或当前任务状态。
2. `自然发言`：用户在 Chat 中直接表达新问题或新需求。

两类入口最终都必须落到同一个任务模型：

```text
携带上下文 -> 识别 run / entity / intent -> 解释、确认或继续任务
自然发言 -> 识别品牌情报意图 -> 创建或复用 BrandIntelligenceRun
```

这能保留 Chat 的自然对话能力，同时避免 Dashboard 到 Chat 的上下文丢失。

### 3. Orchestrator 的定位

Orchestrator 负责推进任务状态。

它负责：

- 生成问题。
- 抓取 AI 回答。
- 计算指标。
- 生成品牌世界。
- 生成建议。
- 判断是否需要用户确认。
- 把每一步结果写回 `BrandIntelligenceRun`。

Orchestrator 不应该把任务状态只藏在 Chat session 里。

### 4. 品牌知识图谱的定位

品牌知识图谱是任务结果沉淀后的长期事实层。

它负责回答：

- 品牌和问题、回答、平台、来源、竞品之间是什么关系。
- 某个指标由哪些回答和引用支撑。
- 哪些建议来自哪些证据缺口。
- 后续监测如何让品牌世界持续更新。

`BrandIntelligenceRun` 是一次任务过程。
品牌知识图谱是长期沉淀结果。
两者不能混为一谈。

## 用户主路径

### 路径 A：从 Dashboard 开始

```text
Dashboard 选择品牌
  -> 点击“开始品牌情报分析”
  -> 创建 BrandIntelligenceRun
  -> 后台生成问题
  -> 后台抓取 AI 回答
  -> 后台计算指标
  -> Dashboard 自动刷新任务状态和结果
  -> 用户查看简要情报、情报来源、品牌世界、跟进建议
```

如果执行中不需要用户确认，系统应该后台继续推进。

### 路径 B：从 Chat 开始

```text
用户在 Chat 里说：分析理想汽车在 AI 平台里的表现
  -> Orchestrator 创建 BrandIntelligenceRun
  -> Chat 展示任务已开始
  -> 用户可以退出 Chat
  -> Dashboard 继续展示任务进度
  -> 任务完成后 Dashboard 展示情报结果
```

用户退出 Chat 后，任务不能断。

### 路径 C：任务需要用户确认

```text
任务执行中发现需要确认
  -> BrandIntelligenceRun 进入 waiting_user
  -> Dashboard 顶部显示“需要确认”
  -> 用户点击“处理确认”
  -> 打开 Chat 或内联确认面板
  -> 用户确认后 Orchestrator 继续执行
```

确认项可以是：

- 选择 AI 平台。
- 确认抓取范围。
- 处理登录或浏览器接管。
- 确认是否创建监测计划。
- 选择失败后的重试策略。

### 路径 D：样本不足

样本不足不是最终状态，而是任务过程中的状态。

正确处理：

```text
没有问题样本
  -> 自动生成问题，或让用户确认问题范围

有问题但没有回答
  -> 自动抓取 AI 回答，或让用户确认平台范围

有回答但样本不够排名
  -> 明确显示“排名暂不成立”
  -> 给出补样本建议
  -> 不展示虚假的第几名

有回答但分析失败
  -> 显示失败原因和重试入口
```

禁止处理：

```text
样本不足时直接展示官网内容建议、竞品内容建议、监测任务表单。
```

这些建议必须等指标和证据形成后再出现。

## BrandIntelligenceRun 数据模型

### 核心字段

| 字段 | 含义 |
| --- | --- |
| `id` | 任务 ID |
| `entity_id` | 品牌 ID |
| `created_by_user_id` | 发起人 |
| `origin_surface` | 来源：dashboard、chat、monitoring、system |
| `origin_session_id` | 如果从 Chat 发起，记录 session |
| `run_goal` | 任务目标 |
| `analysis_mode` | 全景分析、场景分析、周期监测 |
| `status` | 当前任务状态 |
| `stage` | 当前阶段 |
| `progress` | 进度 |
| `requires_user_action` | 是否需要用户处理 |
| `user_action_type` | 需要处理的动作类型 |
| `blocking_reason` | 卡住原因 |
| `sample_scope` | 样本口径 |
| `input_scope` | 用户或默认配置的分析范围 |
| `output_refs` | 问题、回答、报告、图谱、建议等结果引用 |
| `started_at` | 开始时间 |
| `completed_at` | 完成时间 |
| `failed_at` | 失败时间 |
| `last_activity_at` | 最近活动时间 |

### input_scope

```json
{
  "brand_name": "理想汽车",
  "platforms": ["doubao", "yuanbao", "kimi", "deepseek"],
  "question_scope": "全景品牌表现",
  "competitors": ["小米汽车", "问界", "腾势"],
  "question_count_target": 12,
  "answer_count_target": 96,
  "source_policy": "official_and_external"
}
```

### sample_scope

```json
{
  "platform_count": 3,
  "question_count": 12,
  "answer_count": 96,
  "valid_answer_count": 95,
  "excluded_answer_count": 1,
  "citation_count": 1066,
  "mention_count": 70,
  "captured_from": "2026-05-25T10:00:00Z",
  "captured_to": "2026-05-25T10:18:00Z"
}
```

### output_refs

```json
{
  "question_set_id": "...",
  "fetch_result_artifact_id": "...",
  "report_artifact_id": "...",
  "world_projection_version": 6,
  "metric_snapshot_ids": ["..."],
  "finding_ids": ["..."],
  "recommendation_ids": ["..."]
}
```

## 状态机

| 状态 | 用户看到什么 | 系统行为 | 用户动作 |
| --- | --- | --- | --- |
| `not_started` | 尚未开始分析 | 等待发起 | 开始分析 |
| `planning_questions` | 正在生成问题 | A3 生成问题 | 可查看问题范围 |
| `waiting_scope_confirmation` | 需要确认分析范围 | 暂停 | 确认平台、问题、竞品 |
| `fetching_answers` | 正在抓取 AI 回答 | A4 抓取答案 | 可查看进度 |
| `waiting_takeover` | 需要处理登录或接管 | 暂停 | 处理接管 |
| `analyzing_metrics` | 正在计算指标 | A5 或投影服务计算 | 无需操作 |
| `building_world` | 正在生成品牌世界 | 写入图谱和投影 | 无需操作 |
| `generating_recommendations` | 正在生成建议 | 根据指标和证据缺口生成建议 | 无需操作 |
| `completed` | 情报已生成 | 等待查看或监测 | 查看情报、解释指标、开启监测 |
| `waiting_user` | 需要确认后继续 | 暂停 | 处理确认 |
| `failed` | 分析失败 | 等待重试或降级 | 重试、调整范围 |
| `cancelled` | 已取消 | 停止执行 | 可重新开始 |

## 自动推进规则

默认原则：

```text
只要用户已经明确发起品牌情报分析，且系统有足够默认配置，就应该后台继续推进。
```

允许自动推进：

- 生成问题。
- 使用默认平台抓取答案。
- 对已抓取答案计算指标。
- 更新品牌世界。
- 在指标成型后生成建议。

必须请求用户确认：

- 没有默认平台范围。
- 需要登录或浏览器接管。
- 会产生明显成本或长时间任务。
- 要创建周期监测计划。
- 用户要求改变品牌、竞品或问题范围。
- 抓取失败，需要选择重试策略。

失败处理：

- 可恢复失败：显示原因，提供重试。
- 部分失败：保留已成功样本，明确哪些平台或问题缺失。
- 不可恢复失败：停止任务，提示用户调整范围或稍后重试。

## Dashboard 设计

### 顶部增加“当前情报任务”

Dashboard 首屏应展示一个任务状态区，位置在品牌事实和核心指标之前或合并到顶部。

它只回答五件事：

1. 当前任务是什么。
2. 现在做到哪一步。
3. 已经产出什么。
4. 是否需要用户处理。
5. 下一步会发生什么。

示例：

```text
正在分析理想汽车在 AI 平台里的表现
已生成 12 个问题，正在抓取 AI 回答
抓取完成后将生成 AI 提及率、提及排名、官网引用率和语气性质
```

如果需要用户：

```text
需要确认抓取平台
选择平台后继续抓取 AI 回答
```

如果失败：

```text
AI 回答抓取失败
3 个平台中 1 个失败，可重试失败平台
```

### 右下角对话气泡

Dashboard 应提供一个轻量、持续存在的右下角对话气泡，用于承接 Chat，而不是在页面里散落“去 Chat”入口。

气泡职责：

- 显示当前是否有需要用户处理的确认。
- 显示后台任务是否卡住。
- 作为解释、追问、处理确认的统一入口。
- 在需要浏览器接管、平台确认、失败重试时给出动态提醒。

气泡不负责展示完整情报结果，也不替代任务状态区。

气泡状态：

| 状态 | 展示 |
| --- | --- |
| 空闲 | 小型对话入口 |
| 后台运行 | 轻量进度提示，不打断用户 |
| 需要确认 | 明确提醒，点击进入确认上下文 |
| 执行失败 | 提示可重试 |
| 有新结果 | 提示情报已更新 |

点击气泡进入 Chat 时，必须携带结构化上下文，包括 `run_id`、`entity_id`、`intent` 和当前任务状态。

禁止：

```text
页面底部再放一个“监测与样本”入口，点开 Dashboard 内部第二套监测看板。
```

监测计划和监测设置应留在 Settings 的监测功能中；Dashboard 只展示品牌情报任务和结果。

### 简要情报

只展示已经成立的指标：

- AI 提及率。
- 提及排名。
- 官网引用率。
- 语气性质。

如果指标未成立：

- 显示等待状态。
- 说明缺少什么样本。
- 不显示虚假的 0 或排名。

### 情报来源

围绕指标展开证据：

- 提及率：平台、问题、提及答案、未提及答案。
- 排名：目标品牌与竞品的提及率和样本数。
- 官网引用率：官网引用样本、外部来源贡献。
- 语气性质：正向、中性、负向分布和代表回答。

### 品牌世界

展示任务结果沉淀后的图谱：

```text
中心：当前品牌
第一圈：提及率、排名、官网引用率、语气性质、竞品、AI 平台、引用来源、建议
第二圈：点击节点后展开对应平台、竞品、域名、回答样本
```

品牌世界回答：

```text
这个品牌在 AI 世界里的位置、证据、关系和变化入口是什么？
```

### 跟进反馈

只有在指标成型后展示。

建议应来自真实证据缺口：

- 官网引用率低：补官网证据页。
- 竞品提及更强：补竞品对照内容。
- 负向语气明显：处理负向场景内容。
- 某平台依赖外部来源：优先治理该平台偏好的内容源。
- 样本波动大：开启周期监测。

样本不足时，只显示任务进度和补样本入口，不显示建议表单。

## Chat 设计

### Chat 与 Dashboard 的交互原则

Dashboard 和 Chat 的关系不是“跳转到另一个产品”，而是同一个品牌情报任务的两种操作方式。

Dashboard 是主场，负责让用户看到任务状态、情报结果、证据和下一步。
Chat 是自然展开，负责解释、追问、调整范围和处理确认。

硬原则：

1. 用户永远围绕同一个 `BrandIntelligenceRun` 操作。
2. Dashboard 不把 Chat 当逃生通道。
3. Chat 不要求用户重新描述 Dashboard 上已经知道的上下文。
4. Chat 的输出必须回写任务、情报结果、用户确认或品牌世界。
5. 后台可自动执行的流程不依赖 Chat 常驻。

Chat 的交互入口分两类：

1. 自然发言：用户主动输入问题，系统理解意图后创建或复用任务。
2. 上下文进入：用户从 Dashboard 的指标、证据、气泡、确认项进入，Chat 必须先展示上下文卡片。

上下文进入时，Chat 应像当前页面的展开层，而不是一个新的空白会话。

错误交互：

```text
Dashboard 显示样本不足
  -> 用户点击“去 Chat”
  -> 用户不知道该说什么
  -> Chat 重新开始猜意图
```

正确交互：

```text
Dashboard 显示“需要补齐 AI 回答”
  -> 用户点击“继续抓取答案”
  -> 系统直接创建或恢复 BrandIntelligenceRun
  -> 后台开始抓取
  -> Chat 只在需要解释或确认时打开
```

如果用户点击“解释这个指标”：

```text
Dashboard 上的 AI 提及率
  -> Chat 打开
  -> 自动带入品牌、指标、样本口径、证据摘要、当前 run
  -> 用户看到的是围绕这条指标的解释，而不是空白对话
```

### 从 Dashboard 进入 Chat

按钮文案不应该是“去 Chat”。

应根据场景表达：

- 解释这个指标。
- 追问证据。
- 调整分析范围。
- 处理确认。
- 查看执行细节。

进入 Chat 后，Chat 顶部应显示任务上下文：

```text
当前任务：理想汽车 AI 品牌情报分析
状态：正在抓取 AI 回答
样本：12 个问题，0 条回答
```

### 从 Chat 发起任务

当用户在 Chat 发起品牌情报分析时：

1. 创建或复用 `BrandIntelligenceRun`。
2. Chat 告诉用户任务已开始。
3. Dashboard 同步出现任务状态。
4. 用户退出 Chat 后任务继续。

### Chat 不能再承担的职责

Chat 不应该是唯一的执行状态容器。

禁止：

- 任务状态只存在于 Chat 内存。
- 前端靠默认建议猜下一步。
- 用户退出 Chat 后任务不可见。
- Dashboard 样本不足时只给一个跳 Chat 按钮。

## Chat 承接层健壮性

`BrandIntelligenceRun` 会让 Dashboard、指标、证据、建议、确认项都能自然打开 Chat。
这意味着 Chat 不能再假设只有一个线性的入口。它必须能承接大量分散入口，并且打开稳定、上下文稳定、历史稳定。

如果 Chat 打开慢、卡住、丢历史消息、丢 handoff 上下文，那么任务中枢会变成更大的故障放大器。

### 设计目标

Chat 承接层必须满足：

1. 打开快：从 Dashboard 点击到可见 Chat shell 不应依赖完整消息加载完成。
2. 上下文稳：Dashboard handoff、run id、entity id、metric key、evidence refs 必须可靠进入 Chat。
3. 历史不丢：历史消息加载失败不能导致当前任务上下文丢失。
4. 可恢复：刷新、返回、重复点击、网络慢时，不能生成多个互相冲突的任务。
5. 可降级：Chat 历史不可用时，仍能显示当前任务卡片和操作。
6. 幂等：同一个 Dashboard 操作重复点击，不应创建重复 run 或重复自动发送。

### Chat 打开分层

Chat 打开应分成三层，而不是等所有数据都回来才渲染。

```text
Layer 1: Chat Shell
  - 立即显示页面、输入框、当前品牌、任务卡片骨架

Layer 2: Handoff Context
  - 加载 Dashboard 传入的 BrandIntelligenceRun、指标、证据摘要、待确认动作
  - 这是当前操作的最低可用上下文

Layer 3: Message History
  - 异步加载历史消息
  - 失败时可重试，不影响当前任务上下文
```

结论：

```text
Chat 可用性的最低单位不是历史消息，而是当前任务上下文。
```

### Handoff 协议

Dashboard 打开 Chat 时，不应该只塞一段自然语言 draft。
必须传一个结构化 handoff。

建议字段：

| 字段 | 含义 |
| --- | --- |
| `handoff_id` | 一次跳转的唯一 ID，用于幂等 |
| `run_id` | 当前 BrandIntelligenceRun |
| `entity_id` | 品牌 |
| `intent` | explain_metric / inspect_evidence / confirm_action / adjust_scope / continue_run |
| `metric_key` | 如果来自指标 |
| `evidence_refs` | 如果来自证据 |
| `recommendation_id` | 如果来自建议 |
| `confirmation_id` | 如果来自确认 |
| `autosend` | 是否自动发送 |
| `created_at` | 创建时间 |
| `expires_at` | 过期时间 |

handoff 应同时写入：

1. URL 安全查询参数：只放非敏感索引字段。
2. sessionStorage：放结构化 payload。
3. 后端可选短期记录：关键动作可落库，避免刷新丢失。

如果 sessionStorage 丢失，Chat 应能用 URL 中的 `run_id/entity_id/intent` 从后端恢复最低上下文。

### 历史消息加载规则

历史消息是增强，不是任务执行前提。

规则：

- 历史消息加载中，Chat 可以先显示当前任务卡片。
- 历史消息加载失败，显示“历史消息暂时无法读取”，但保留当前任务操作。
- 历史消息为空，不代表没有任务上下文。
- 不允许因为历史消息失败而跳回登录、清空输入、丢失 handoff。
- 分页加载历史，避免一次性拉太多导致卡住。
- 历史消息和当前 handoff 合并时，handoff 的当前任务优先。

### 自动发送规则

`autosend` 只能用于明确的任务动作，不能用于普通解释类入口。

允许自动发送：

- 继续抓取答案。
- 开始品牌情报分析。
- 重试失败平台。
- 继续当前 run。

不建议自动发送：

- 解释指标。
- 追问证据。
- 调整范围。

这些入口应该先打开 Chat，展示上下文卡片和预填问题，让用户确认后发送。

### 防重复规则

需要防止这些情况：

- 用户连续点击两次“开始分析”。
- Dashboard 网络慢，重复创建 run。
- Chat 打开后重复消费同一个 handoff。
- 自动发送刷新后再次执行。

规则：

- `handoff_id` 只能消费一次。
- `run_id + intent + origin_event_id` 必须幂等。
- 如果同品牌已有 active run，默认恢复该 run，而不是创建新 run。
- 自动发送成功后，handoff 标记为 consumed。
- 刷新 Chat 时，不重复自动发送已 consumed 的 handoff。

### Chat 性能门禁

后续实现必须增加这些门禁：

| 场景 | 标准 |
| --- | --- |
| Dashboard 点击打开 Chat | 1 秒内出现 Chat shell 和任务卡片 |
| 历史消息慢 | 不阻塞任务卡片 |
| 历史消息失败 | 可重试，不丢 handoff |
| 重复点击入口 | 不创建重复 run |
| 刷新 Chat | run 上下文仍在 |
| sessionStorage 丢失 | 可从后端恢复最低上下文 |
| autosend | 只执行一次 |

### Chat 不稳定时的降级

如果 Chat 无法打开或历史加载失败，Dashboard 不能让用户卡死。

Dashboard 应提供：

- 当前任务状态。
- 继续执行按钮。
- 取消或重试按钮。
- 处理确认的内联入口。

也就是说：

```text
Chat 失败不能阻断 BrandIntelligenceRun。
```

Chat 是自然展开，不是唯一操作通道。

## Orchestrator 设计

Orchestrator 要围绕 `BrandIntelligenceRun` 执行。

### 创建任务

触发来源：

- Dashboard 开始分析。
- Chat 用户请求分析品牌。
- 自动监测周期触发。
- 用户要求补样本或重试。

创建后立即写入：

```text
status = planning_questions
stage = A3
progress = 0.1
```

### 推进任务

每个节点完成后，Orchestrator 必须更新任务状态：

```text
A3 完成 -> fetching_answers
A4 完成 -> analyzing_metrics
A5 完成 -> building_world
图谱投影完成 -> generating_recommendations
建议生成完成 -> completed
```

### 等待用户

如果需要确认：

```text
status = waiting_user
requires_user_action = true
user_action_type = platform_confirmation / browser_takeover / retry_strategy / monitoring_confirmation
```

用户确认后：

```text
status = running
继续上一个 stage 或进入下一个 stage
```

### 写入结果

每个阶段产物都必须进入 `output_refs`，不要只挂在 Chat message 上。

## API 设计草案

### 查询当前品牌任务

```http
GET /api/v1/intelligence-runs/entities/{entity_id}/active
```

返回：

```json
{
  "run": {
    "id": "...",
    "entity_id": "...",
    "status": "fetching_answers",
    "stage": "A4",
    "progress": 0.42,
    "message": "正在抓取 AI 回答",
    "sample_scope": {
      "question_count": 12,
      "answer_count": 24,
      "platform_count": 3
    },
    "requires_user_action": false,
    "next_step": "抓取完成后生成提及率、排名、官网引用率和语气性质"
  }
}
```

### 创建任务

```http
POST /api/v1/intelligence-runs/entities/{entity_id}
```

请求：

```json
{
  "run_goal": "分析当前品牌在 AI 平台里的表现",
  "analysis_mode": "panorama",
  "platforms": ["doubao", "yuanbao", "kimi", "deepseek"],
  "question_scope": "全景品牌表现",
  "origin_surface": "dashboard"
}
```

### 继续任务

```http
POST /api/v1/intelligence-runs/{run_id}/resume
```

### 取消任务

```http
POST /api/v1/intelligence-runs/{run_id}/cancel
```

### 处理确认

```http
POST /api/v1/intelligence-runs/{run_id}/confirm
```

### 与 world API 的关系

`world` API 继续提供结果投影：

```http
GET /api/v1/ontology/entities/{entity_id}/world
```

但 Dashboard 顶部任务状态不应该只依赖 world。

建议 Dashboard 并行读取：

```text
active intelligence run
ontology world
dashboard home
```

其中：

- run 负责“现在在做什么”。
- world 负责“已经沉淀了什么”。
- dashboard home 负责“监测和报告摘要”。

## 与现有系统的迁移关系

### 现有 Chat session

保留。

但新增关系：

```text
ChatSession -> BrandIntelligenceRun
```

一个 Chat 可以触发多个 run。
一个 run 可以被多个 Chat 继续解释或确认。

### 现有 AnalysisTask / TaskRun

短期可以复用作为执行记录。

但 `BrandIntelligenceRun` 应该是品牌情报产品语义层，不应该让 Dashboard 直接读底层 task 表猜业务状态。

### 现有 ontology world

保留。

`BrandIntelligenceRun` 完成后刷新：

- `summary_projection`
- `evidence_projection`
- `graph_projection`
- `recommendation_projection`

### 现有 recommendation task

保留。

但规则调整：

```text
只有 BrandIntelligenceRun 已完成，且指标样本成立，才允许生成推荐任务。
```

## 分阶段落地计划

### Phase 1：任务中枢最小闭环

目标：先让 Dashboard 和 Chat 不断。

范围：

- 新增 `BrandIntelligenceRun` 数据模型。
- Dashboard 查询当前 active run。
- Dashboard 显示当前任务状态。
- Chat 发起分析时创建 run。
- Dashboard 发起分析时创建 run 并进入后台执行。
- 样本不足时不展示建议，只展示 run 状态和下一步。

验收：

- 用户从 Chat 退出后，Dashboard 能看到任务还在进行。
- 用户从 Dashboard 开始分析后，不需要手动找 Chat。
- 无问题样本时进入生成问题。
- 有问题无答案时进入抓取答案。
- 需要确认时 Dashboard 显示明确确认入口。

### Phase 2：Orchestrator 后台推进

目标：让任务真正自动跑完。

范围：

- Orchestrator 按 run stage 推进 A3/A4/A5。
- 每个阶段写回 status、stage、progress、output_refs。
- 支持失败重试。
- 支持用户确认后 resume。

验收：

- run 可以从 `planning_questions` 自动推进到 `completed`。
- 刷新页面后状态不丢。
- Chat 关闭后任务继续执行。
- 失败后可重试。

### Phase 3：Dashboard 任务体验完整化

目标：让用户不用理解后台，也能知道下一步。

范围：

- 当前情报任务区。
- 任务 timeline。
- 需要确认 banner。
- 失败和部分失败状态。
- 指标未成立状态。
- 任务完成后跳转到简要情报。

验收：

- 新用户能看懂当前任务是否还在跑。
- 样本不足不会被误解为产品无能力。
- 需要用户处理时，操作入口明确。

### Phase 4：监测与长期品牌世界连接

目标：让一次分析升级为持续监测。

范围：

- 从 completed run 创建监测计划。
- 监测计划周期触发新的 run。
- 趋势图使用多个 run 的指标快照。
- 品牌世界展示不同 run 的变化。

验收：

- 用户能从一次情报分析进入周期监测。
- 监测结果持续刷新品牌世界。
- Dashboard 能区分“一次分析结果”和“周期监测趋势”。

## 关键产品规则

### 规则 1：样本不足不等于建议

样本不足时，系统只能告诉用户缺什么样本，以及系统是否会继续补齐。

### 规则 2：Chat 不是任务状态真相源

Chat 可以解释和确认，但任务状态必须在 `BrandIntelligenceRun`。

### 规则 3：Dashboard 永远显示下一步

无论未开始、运行中、等待确认、失败、完成，Dashboard 都必须显示下一步。

### 规则 4：后台能做的不要让用户手动做

如果系统有默认平台、默认问题范围、默认竞品范围，就自动推进。

### 规则 5：需要用户时必须说清原因

不能只显示“需要确认”。必须说明：

- 为什么需要确认。
- 用户确认什么。
- 确认后系统会做什么。

## 用户可见文案原则

允许：

```text
开始品牌情报分析
正在生成问题
正在抓取 AI 回答
正在生成品牌情报
需要确认抓取平台
继续抓取答案
重试失败平台
解释这个指标
追问证据
调整分析范围
```

禁止：

```text
回到 Chat
调用 Orchestrator
对象状态未完成
Ontology 投影缺失
ActionRecord 待处理
创建监测计划（在样本不足时作为建议出现）
```

## 风险与取舍

### 风险 1：新增任务层会扩大后端改造面

取舍：

先做最小 `BrandIntelligenceRun`，不要一开始做复杂调度系统。

### 风险 2：和现有 AnalysisTask 重叠

取舍：

`AnalysisTask` 是执行技术层，`BrandIntelligenceRun` 是品牌情报产品层。短期可以建立引用关系，不强行替换。

### 风险 3：后台自动推进可能误跑

取舍：

只有用户明确发起分析，且默认范围明确，才自动推进。成本、登录、监测计划必须确认。

### 风险 4：Dashboard 变复杂

取舍：

首屏只增加一个“当前情报任务”区域，不新增复杂任务管理页。任务历史和高级调度放后续阶段。

## 验收标准

### 产品验收

- 用户从 Chat 发起分析后，退出 Chat，Dashboard 仍能看到任务进度。
- 用户从 Dashboard 发起分析后，系统能后台推进，不要求用户手动找 Chat。
- 样本不足时，页面明确显示缺问题、缺答案、缺平台还是缺竞品样本。
- 样本不足时不出现无效商业化建议。
- 任务完成后，Dashboard 能展示 AI 提及率、提及排名、官网引用率、语气性质。
- 用户可以从任一指标进入 Chat 追问证据。

### 技术验收

- `BrandIntelligenceRun` 状态刷新后不丢。
- Chat session 关闭不影响 run 执行。
- Orchestrator 每个阶段写回 run 状态。
- 失败、等待确认、取消、重试都有明确状态。
- world projection 使用 completed run 的结果刷新。
- 推荐任务只从 completed run 且样本成立的结果生成。

### UI 验收

- Dashboard 首屏能看出任务状态。
- 不出现内部工程词。
- 不出现虚假 0 值。
- 不出现样本不足时的跟进建议表单。
- 移动端也能看到任务状态和下一步。

## 待确认问题

1. `BrandIntelligenceRun` 是否作为新表落地，还是先复用 `AnalysisTask.metadata` 做过渡？
2. Dashboard 是否只显示当前 active run，还是同时显示最近 completed run？
3. 自动推进默认平台范围用当前设置里的监测平台，还是品牌分析默认平台？
4. 如果用户从 Chat 连续发起两次同品牌分析，是新建 run，还是复用未完成 run？
5. 任务进行中，用户切换品牌时，是否在左侧品牌列表显示运行状态？
6. 长时间任务是否需要通知中心或浏览器通知？
7. 监测计划触发的 run 是否和人工发起的 run 使用同一状态机？

## 建议确认的产品决策

建议确认以下方向后再开发：

```text
Specta 的主线从 Chat 驱动升级为 BrandIntelligenceRun 驱动。
Dashboard 是任务状态和情报结果主界面。
Chat 是解释、追问、确认、调整范围入口。
后台能继续执行的任务必须继续执行。
样本不足时不展示商业化建议，只展示任务状态和补样本路径。
```
