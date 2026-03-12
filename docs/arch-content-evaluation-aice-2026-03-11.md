# 内容评估能力技术实施方案

**架构师**: Martin Fowler
**日期**: 2026-03-11
**状态**: 可评审
**关联文档**:
- `docs/design-content-evaluation-aice-2026-03-10.md`
- `docs/prd-content-evaluation-aice-2026-03-11.md`
- `docs/ux-design-content-evaluation-aice-2026-03-11.md`

---

## 1. 背景与目标

本需求要在现有 Specta AI 平台内新增一条内容评估能力链路，支持：

1. 评估 A4 抓取答案里的 citation URL
2. 评估用户主动输入的 URL
3. 评估用户主动输入的文本
4. 支持后续扩展到批量 URL / 批量文本

这里的核心目标不是“再造一个工具页”，而是在现有 `Chat -> Orchestrator -> Artifact -> Canvas` 框架里，增加一个低侵入、可演进、可批量扩展的新分析任务。

---

## 2. 现状约束

基于当前代码，内容评估能力必须适配下面这些既有约束：

### 2.1 前端约束

1. 主工作台固定为 `ChatLayout -> ChatPanel + CanvasPanel`
2. Canvas 类型是固定枚举：
   - `report`
   - `dataTable`
   - `chart`
   - `pipeline`
   - `workflow`
   - `questionList`
   - `fetchResults`
3. `ReportContent.tsx` 目前只渲染品牌分析报告结构
4. `DataTableContent.tsx` 已具备通用表格能力，可复用做批量明细
5. `buildOutputReadyPayload()` 会把 `report_baseline` / `report_persona` 这类类型折叠为 `report`

### 2.2 后端约束

1. 主流程由 `orchestrator_node.py` 通过 tool calling 路由
2. A1-A6 主链路围绕品牌分析状态字段组织，不适合直接复用做内容评估状态承载
3. `save_and_send_artifact()` 当前将 artifact 固定为：

```text
{session_id}_{output_type}
```

4. `output_service.py` 在恢复历史 artifact 时也使用同样规则
5. 现有文件上传链路已存在，但附件尚未真正进入内容分析主链路

### 2.3 产品约束

1. 不新增一级页面
2. 不破坏现有 Canvas、ArtifactNav、版本切换和导出机制
3. 需要同时兼容单条和批量
4. 评估报告必须支持 AICE 9C 固定矩阵、硬扣规则和置信度输出

---

## 3. 架构评审

### 3.1 方案 A：新开独立“内容评估”页面

**做法**

- 新增单独 route
- 新建专用表单、结果页、历史页
- 与 Chat 平台松耦合

**优点**

- 产品语义清晰
- 独立演进空间大

**问题**

1. 打破现有 Chat-first 主心智
2. 需要重复建设状态管理、结果承载、历史恢复
3. 与引用卡片触发链路割裂
4. 可逆性差，成本最高

**结论**

不推荐。它解决的是“单独工具”问题，不是“嵌入现有工作台”的问题。

### 3.2 方案 B：新增一种 Canvas 一级类型，例如 `evaluation`

**做法**

- 扩展 `CanvasContentType`
- 新增 `EvaluationContent.tsx`
- 保持 Chat 入口不变

**优点**

- 报告结构可以自由定义
- 前端渲染器隔离度高

**问题**

1. 会改动 `VALID_OUTPUT_TYPES`、`ArtifactNav`、WebSocket 归一化、历史恢复等一整条链
2. 为一个本质上仍是“报告 + 明细表”的能力新增一级类型，抽象层级过高
3. 与现有导出、报告心智不一致

**结论**

不推荐作为首选。若后续评估能力演化成大型产品模块，再考虑抽离。

### 3.3 方案 C：复用 `report` + `dataTable`，通过 `report_kind` 和 `artifact_key` 扩展

**做法**

- 单条结果走 `report`
- 批量总览走 `report`
- 批量明细走 `dataTable`
- 在 `report.data.report_kind = "content_evaluation"` 下分支渲染
- 引入 `artifact_key` 解决同一会话多份评估结果冲突

**优点**

1. 与现有平台最契合
2. 复用现有 Canvas 能力最多
3. 风险集中在少数关键边界
4. 可逐步演进，回滚成本低

**问题**

1. `artifact_key` 需要前后端一起改
2. `ReportContent` 需要做 report-kind 分发
3. 需要为 A7 设计独立状态域，避免污染品牌分析状态

**结论**

推荐。这是最符合“演进式架构”的方案。

---

## 4. 推荐架构

### 4.1 总体原则

我建议把 A7 定义成一条**旁路分析链**，而不是嵌入 A1-A6 主分析通道。

也就是：

```text
用户输入 / citation 操作
  -> Orchestrator 识别为 content_evaluation
  -> A7 Content Evaluation Agent
  -> Artifact 输出 report / dataTable
  -> Canvas 展示
```

而不是：

```text
用户输入
  -> 复用 A1-A6 某一条已有品牌分析主链
```

原因很直接：内容评估的输入对象、状态语义、输出结构、执行时长都和品牌分析主链不同。硬塞进去会造成状态含义混乱。

### 4.2 模块边界

建议新增 5 个职责边界：

1. `Evaluation Intent Router`
   - 判断这是 citation、单 URL、单文本、批量 URL、批量文本中的哪一类
   - 生成统一 `evaluation_request`

2. `Content Extractor`
   - 对 URL 做抓取、清洗、正文抽取、结构特征提取
   - 对文本做规范化、分段、长度控制

3. `Feature Builder`
   - 生成评分所需结构化特征
   - 例如 `crawl_readable`、`has_h1`、`schema_types`、`published_at`

4. `A7 Evaluation Agent`
   - 按固定 Prompt 和 9C 规则生成维度评分、证据、建议、置信度

5. `Score Validator + Artifact Builder`
   - 校验硬扣规则、总分求和、字段完整性
   - 输出单条 report、批量 report、批量 dataTable

### 4.3 推荐数据流

```text
Input
  -> evaluation_request
  -> extractor_result
  -> evaluation_features
  -> llm_scoring_result
  -> validated_evaluation_result
  -> artifact_payload
```

这条数据流里，`extractor_result` 和 `evaluation_features` 是关键。没有这两层，模型会退化成“只看文本印象打分”，无法保证置信度和硬规则。

---

## 5. 状态设计

### 5.1 不推荐复用现有品牌分析字段

不要把内容评估塞进：

- `questions`
- `fetch_results`
- `metrics`
- `report`

这些字段是品牌分析语义，会给历史恢复、重跑、对比和调度带来混乱。

### 5.2 建议新增独立状态域

建议在 `AgentState` 增加以下字段：

```python
evaluation_request: dict | None
evaluation_batch: dict | None
evaluation_results: list | None
evaluation_summary: dict | None
evaluation_artifacts: list | None
```

字段语义：

| 字段 | 用途 |
| :--- | :--- |
| `evaluation_request` | 单条评估的统一输入 |
| `evaluation_batch` | 批量任务元信息 |
| `evaluation_results` | 单条或批量 item 级标准化结果 |
| `evaluation_summary` | 批量总览统计 |
| `evaluation_artifacts` | 本轮已生成 artifact 元数据，供恢复和追踪 |

### 5.3 `evaluation_request` 推荐结构

```json
{
  "request_id": "eval_20260311_001",
  "mode": "single",
  "source_type": "citation_url",
  "evaluation_mode": "AICE-Web",
  "source": {
    "url": "https://example.com/article",
    "title": "Example article",
    "citation_context": "..."
  },
  "trigger": {
    "from_message_id": "xxx",
    "from_artifact_id": "xxx"
  }
}
```

### 5.4 `evaluation_batch` 推荐结构

```json
{
  "batch_id": "batch_20260311_001",
  "mode": "batch",
  "batch_type": "mixed",
  "items": [
    {
      "item_id": "item_001",
      "source_type": "user_url",
      "url": "https://example.com/a"
    }
  ]
}
```

---

## 6. A7 评分架构

### 6.1 评分不应完全交给 LLM

我会明确反对“把整张网页直接扔给模型，让它自己给分”的方案。原因是：

1. 可重复性差
2. 硬扣规则难以稳定执行
3. `confidence` 没有客观基础
4. 批量时成本和不稳定性都会上升

### 6.2 推荐分层评分机制

评分应拆成三层：

#### 第一层：机器特征判定

由程序直接产出：

- `crawl_readable`
- `http_status`
- `content_length`
- `has_h1`
- `heading_count`
- `has_main`
- `has_article`
- `schema_types`
- `published_at`
- `updated_at`
- `external_links_count`
- `official_domain_match`
- `source_domain`

#### 第二层：LLM 语义判断

由 A7 负责：

- `C1 Credibility`
- `C2 Consistency`
- `C4 Claim Balance`
- `C5 Clarity`
- `C7 Intent Match`
- `C8 Timeliness` 的语义部分

#### 第三层：规则校验与修正

由程序在结果返回后强制执行：

- `crawl_readable = false` 时，`C6 = 0`
- 缺失 H1 或关键结构标签时，`C9a <= 5`
- 无 Schema 时，`C9b <= 5`
- 所有维度之和必须等于 `overallScore`
- 每个维度都必须有 `reasoning` 和 `confidence`

### 6.3 `confidence` 的来源

`confidence` 不是“模型有多自信”，而是“证据是否充分”。

建议拆成三层：

1. `extract_quality`
   - 抽取是否完整、是否正文足够、是否命中关键结构

2. `evidence_completeness`
   - 是否有日期、结构标签、Schema、外链、域名信息等客观证据

3. `dimension_confidence`
   - 每个维度自己的置信度

推荐整体计算：

```text
overall_confidence
= 0.35 * extract_quality
+ 0.35 * evidence_completeness
+ 0.30 * average(dimension_confidence)
```

这部分应该在后端做，不建议完全信任 LLM 直接给一个 overall confidence。

---

## 7. Artifact 设计

### 7.1 当前问题

当前 artifact 使用固定 key：

```text
{session_id}_{output_type}
```

这在品牌报告里成立，因为同一类报告通常希望收敛到一个 tab。

但在内容评估里会立即出错：

1. 同一会话评估两个 URL，会互相覆盖
2. 批量总览和批量明细无法稳定共存
3. 单项详情无法在历史恢复时准确还原

### 7.2 推荐改法

将 `save_and_send_artifact()` 签名扩展为：

```python
async def save_and_send_artifact(
    session_id: str,
    output_type: str,
    title: str,
    data: dict,
    related_message_id: str | None = None,
    category: str | None = None,
    scenario_label: str | None = None,
    artifact_key: str | None = None,
) -> str:
```

规则：

```text
artifact_id = artifact_key or f"{session_id}_{output_type}"
```

同时，持久化时要把 `artifact_key` 写入 message metadata 或单独字段，否则刷新后前端恢复时仍会丢失。

### 7.3 推荐 Artifact ID 规则

单条：

```text
{session_id}_report_eval_{source_hash}
```

批量总览：

```text
{session_id}_report_eval_batch_{batch_id}
```

批量明细：

```text
{session_id}_datatable_eval_batch_{batch_id}
```

单项详情：

```text
{session_id}_report_eval_item_{item_id}
```

### 7.4 输出类型策略

保持现有一级类型不变：

| 产物 | output_type | data 标识 |
| :--- | :--- | :--- |
| 单条评估报告 | `report` | `report_kind = content_evaluation` |
| 批量总览报告 | `report` | `report_kind = content_evaluation_batch` |
| 批量明细表 | `dataTable` | `table_kind = content_evaluation_batch` |
| 单项详情报告 | `report` | `report_kind = content_evaluation` |

---

## 8. 前端架构调整

### 8.1 推荐改动范围

#### 必改

1. `frontend/src/components/canvas/contents/ReportContent.tsx`
   - 增加 `report_kind` 分发
   - 品牌报告继续走现有渲染器
   - 内容评估报告走新渲染器

2. `frontend/src/hooks/websocket/canvas.ts`
   - 允许透传 `report_kind`、`table_kind`、`overall_confidence` 等字段

3. `frontend/src/hooks/websocket/output.ts`
   - 保持 `report` / `dataTable` 归一化不变
   - 但要支持服务端下发的自定义 `output_id`

4. `frontend/src/components/chat/ChatPanel.tsx`
   - 历史恢复时不能再假设同类型 artifact 必然合并为一个

#### 新增

1. `EvaluationReportContent.tsx`
2. `EvaluationDimensionTable.tsx`
3. `EvaluationEvidencePanel.tsx`
4. `BatchEvaluationSummary.tsx`

### 8.2 为什么前端不要新建一级类型

因为用户看到的仍然是“一个报告”或者“一张明细表”。前端真正需要的是渲染分支，不是架构层面的新物种。

这属于典型的“保留稳定抽象，在数据层扩展语义”。

### 8.3 引用卡片入口

推荐在 citation 卡片增加轻操作：

- `评估此引用`
- Phase 2 增加 `加入批量评估`

点击后不直接绕过 Chat，而是向 Chat 注入一条结构化任务请求，让整个平台仍然保持“由对话发起任务”的一致心智。

---

## 9. 后端架构调整

### 9.1 Orchestrator

建议新增一个 tool：

```text
content_evaluation
```

参数建议：

```json
{
  "mode": "single|batch",
  "source_type": "citation_url|user_url|user_text|batch_url|batch_text",
  "source_payload": {},
  "report_focus": "optional"
}
```

Orchestrator 只负责识别和路由，不负责评分本身。

### 9.2 A7 节点

建议新增：

- `app/workflow/nodes_a7.py`
- `app/workflow/a7/`
  - `extractor.py`
  - `features.py`
  - `prompt.py`
  - `validator.py`
  - `artifacts.py`

推荐职责：

| 模块 | 职责 |
| :--- | :--- |
| `extractor.py` | URL 抓取、正文抽取、文本清洗 |
| `features.py` | 计算结构化评分特征 |
| `prompt.py` | A7 system/user prompt 模板 |
| `validator.py` | 9C 规则校验、置信度和总分校验 |
| `artifacts.py` | 报告、表格 payload 构建 |

### 9.3 抽取器策略

URL 模式建议两级退化：

1. 首选正文抽取器
2. 失败时退化为页面原始文本清洗

如果最终 `crawl_readable = false`，直接进入降级评估：

- `C6 = 0`
- `overall_confidence` 降低
- 报告明确说明“由于页面不可稳定读取，本次评估可信度受限”

### 9.4 批量执行器

不要把批量简单实现成 for-loop + 一个超长 prompt。

建议：

1. 每条 item 独立执行抽取和评分
2. 并发控制在 3-5
3. item 级结果先落标准结构
4. 再做 batch summary 聚合

这样有三个好处：

1. 单条失败不会拖死整批
2. 支持 item 级重试
3. 易于后续迁移到后台任务或队列

### 9.5 输出恢复

`output_service.py` 需要与 `save_and_send_artifact()` 保持一致。

也就是说，历史恢复时的 artifact id 不能再靠：

```python
f"{message.session_id}_{message.output_type}"
```

而要优先读取持久化的 `artifact_key`。

否则：

1. WebSocket 里是正确多实例
2. 刷新后历史恢复又塌缩成一个 tab

这是一个必须一次性修正的架构点。

---

## 10. 技术执行步骤

### Phase 0：打通最小骨架

目标：先证明 A7 能被当前平台调用并产出单条报告。

步骤：

1. 在 Orchestrator 增加 `content_evaluation` tool 定义
2. 新增 `evaluation_*` 状态字段
3. 新增 `nodes_a7.py`
4. 先只支持 `user_text`
5. 输出单条 `report`
6. 前端通过 `report_kind = content_evaluation` 渲染最小报告

验收标准：

1. 在 Chat 输入一段文本可以触发 A7
2. Canvas 正常打开评估报告
3. 报告中有 9C 维度、总分、建议、置信度

### Phase 1：单条 URL / citation

目标：支持网页评估，并接入 citation 入口。

步骤：

1. 新增 URL extractor
2. 产出网页结构特征
3. 接入 AICE-Web 评分
4. 在 citation 卡片加 `评估此引用`
5. Chat 注入结构化 citation 任务
6. 打通硬扣规则和后处理校验

验收标准：

1. citation URL 和用户输入 URL 都可评估
2. `C6 / C9a / C9b` 规则稳定生效
3. 报告中能展示证据来源和扣分原因

### Phase 1.5：Artifact 身份治理

目标：解决多评估结果共存问题。

步骤：

1. `save_and_send_artifact()` 增加 `artifact_key`
2. `output_service.py` 支持恢复自定义 artifact id
3. 前端验证历史恢复、多 tab、版本切换

验收标准：

1. 同一会话内评 2 个 URL 不互相覆盖
2. 刷新页面后 artifact 仍一一对应

### Phase 2：批量文本

目标：先做低风险批量能力。

步骤：

1. 统一 batch request 结构
2. 支持多段文本解析
3. item 级独立评估
4. 生成 batch summary report + detail dataTable
5. 支持从明细进入单项详情

验收标准：

1. 批量 5-20 条文本可稳定执行
2. 单项失败不影响整批完成
3. 总览和明细都可恢复

### Phase 3：批量 URL

目标：引入抓取并发、重试和降级。

步骤：

1. URL batch extractor
2. 并发池控制
3. 超时 / 反爬失败降级
4. item 级重试
5. 失败态在表格中透出

验收标准：

1. 失败项可见、可重试
2. 批量平均时延可控
3. 不因单个网页失败导致整批中断

---

## 11. 测试策略

### 11.1 后端

必须覆盖：

1. intent 路由测试
2. 9C 硬扣规则测试
3. `overallScore` 求和一致性测试
4. `artifact_key` 持久化 / 恢复测试
5. 批量部分成功 / 部分失败测试

### 11.2 前端

必须覆盖：

1. `report_kind` 分支渲染
2. 批量 `dataTable` 展示
3. 多 artifact 共存
4. 刷新后恢复一致性
5. citation 入口触发链路

### 11.3 人工验收

重点关注：

1. 用户是否清楚当前评估对象是谁
2. 扣分原因是否可解释
3. `confidence` 是否与证据充分度一致
4. 批量结果是否有明确优先级

---

## 12. 风险与回滚点

### 12.1 主要风险

1. URL 抽取稳定性不足，导致评分波动
2. `artifact_key` 改造不完整，出现刷新前后不一致
3. Prompt 与规则校验边界不清，导致“看起来按 9C，实际上没按”
4. 批量执行没有隔离好，出现长尾任务拖垮体验

### 12.2 回滚策略

1. `report_kind` 分支可独立关闭，不影响品牌报告
2. `content_evaluation` tool 可从 Orchestrator 中下线
3. batch 能力可在单条稳定前完全关闭
4. URL 评估不稳定时，可只保留文本评估

### 12.3 需要重点观察的信号

如果出现以下信号，应立即复盘：

1. 相同页面多次评分波动过大
2. 刷新后 artifact 合并错乱
3. 批量任务平均完成时间明显超出预期
4. 用户持续追问“为什么这样打分”，说明报告解释力不足

---

## 13. 架构结论

我对这条需求的架构评估结论是：

1. 需求本身适合接入当前平台，不需要新开页面
2. 最合理的做法是新增 A7 旁路分析链，而不是复用 A1-A6 主品牌分析通道
3. 最关键的架构改动不是 Prompt，而是 `artifact_key` 和评估状态域的独立化
4. 单条文本评估应该作为 walking skeleton 先落地
5. 批量能力必须建立在 item 级独立执行和可恢复 artifact 之上

如果只允许先做一个最小可验证版本，我会选：

```text
Chat 输入文本
  -> Orchestrator 路由到 A7
  -> A7 输出单条 report
  -> Canvas 通过 report_kind 渲染
```

因为这是验证整条新架构是否成立的最小骨架，且改动最可控。

---

## 14. 补充：主 LLM 意图路由设计

### 14.1 为什么这里复杂

内容评估能力接入后，主 LLM 需要区分的已经不再只是“要不要分析品牌”，而是至少要回答两个问题：

1. 用户给的对象是什么
2. 用户希望系统对这个对象做什么

在这个场景里，最容易混淆的就是：

- `文章/网页评估`
- `自定义问题抓取`

例如：

- “帮我评估这个网页是否容易被 AI 引用”
- “用下面这几个问题去 Kimi 和 DeepSeek 抓回答”
- “分析一下下面这些内容”

第三类输入本身就是模糊的。如果把这件事完全交给主 LLM 自由理解，误判率会很高。

### 14.2 推荐原则

不要设计成：

```text
用户输入 -> 独立意图分类器/规则树 -> 再调用主 LLM -> 执行
```

推荐改成：

```text
用户输入
  -> Context Bias（入口上下文约束）
  -> Signal Extraction（轻量输入特征抽取）
  -> LLM Tool Choice（主 LLM 做受限工具选择）
  -> Guard Validation（输入校验 / 低置信度确认）
  -> Orchestrator 执行
```

这意味着主 LLM 不是“自由发挥的解释器”，而是**受限上下文中的主路由器**；程序只负责输入验证和 guardrail，不再单独造一个产品层的 intent classifier。

### 14.3 先识别对象，再识别动作

建议把用户输入先拆成两个维度：

#### 维度 A：对象类型 `source_type`

- `citation_url`
- `user_url`
- `user_text`
- `custom_questions`
- `mixed`

#### 维度 B：动作类型 `task_family`

- `content_evaluation`
- `answer_fetch`
- `question_simulation`
- `brand_analysis`
- `ambiguous`

主 LLM 真正要判定的，不是一个大而泛的“用户总意图”，而是这两个字段的组合，并据此选择可用工具。

### 14.4 Signal Extraction 先抽强信号

在进入主 LLM 前，程序只抽取少量强信号，作为路由辅助，而不是直接决定业务分流：

1. 是否来自 citation 卡片点击
2. 是否包含 URL
3. URL 数量是 1 个还是多个
4. 是否存在长文本块
5. 是否是多行短句列表
6. 是否显著像问题列表
7. 是否命中评估类动作词
8. 是否命中抓取类动作词

推荐词表：

#### 评估类动作词

- `评估`
- `打分`
- `分析网页`
- `分析文章`
- `修改建议`
- `AI 采信`
- `可信度`
- `覆盖度`

#### 抓取类动作词

- `抓取回答`
- `跑这些问题`
- `去问`
- `问一下`
- `自定义问题`
- `用这些问题测试`

#### 问题列表判定启发式

如果同时满足以下 3 条中的 2 条，可初步判为 `custom_questions`：

1. 多行输入不少于 2 行
2. 至少 50% 行以 `?`、`？`、`如何`、`为什么`、`怎么`、`是否`、`哪种` 等问句形式出现
3. 单行长度普遍较短，明显不是段落正文

### 14.5 主 LLM 做受限工具选择

主 LLM 不应该直接生成开放式解释，而应该在受限上下文里输出严格 JSON，例如：

```json
{
  "task_family": "content_evaluation",
  "source_type": "user_url",
  "confidence": 0.91,
  "reason_codes": [
    "has_single_url",
    "contains_evaluation_verbs"
  ],
  "needs_confirmation": false
}
```

推荐枚举：

```text
task_family:
- content_evaluation
- answer_fetch
- question_simulation
- brand_analysis
- ambiguous

source_type:
- citation_url
- user_url
- user_text
- custom_questions
- mixed
```

这里的关键点是：主 LLM 只能在给定枚举和工具边界内路由，不能自己创造意图名称，也不能跳出当前入口允许的能力范围。

### 14.6 Guard Rules 只覆盖高确定性场景

主 LLM 输出之后，再由程序做一层硬修正。

推荐规则：

1. citation 卡片点击
   - 直接强制 `task_family = content_evaluation`
   - `source_type = citation_url`

2. 单个 URL + 命中评估词
   - 强制 `content_evaluation:user_url`

3. 多个 URL + 命中评估词
   - 强制 `content_evaluation`，并标记 `batch_candidate = true`

4. 长文本块 + 命中评估词或“修改建议”
   - 强制 `content_evaluation:user_text`

5. 多行问题列表 + 命中抓取词
   - 强制 `answer_fetch:custom_questions`

6. 同时命中评估词和抓取词
   - 强制 `task_family = ambiguous`

7. `mixed`
   - 强制 ask_user，不直接执行

这些规则的目的不是替代 LLM 判断，而是防止明显错误和保证高确定性场景稳定落入正确工具。

### 14.7 低置信度与歧义确认

以下情况不要继续猜，直接 ask_user：

1. `confidence < 0.75`
2. `source_type = mixed`
3. `task_family = ambiguous`
4. 同时包含长正文和问题列表
5. 同时出现“评估”和“抓取”

推荐确认文案尽量短，只问动作，不重新问一遍全部上下文：

- `评估这篇内容并给出修改建议`
- `把这些问题拿去抓 AI 回答`

### 14.7.1 在 `置信度信号` 交付物中的特殊处理

如果入口来自 `confidence_signal` Artifact 内的 `额外评估` 输入框，则应额外注入上下文：

```json
{
  "entrypoint": "confidence_signal_extra_eval",
  "allowed_tools": ["a7_extra_evaluate"],
  "allowed_input_types": ["url", "text"],
  "artifact_id": "..."
}
```

在这个上下文里，主 LLM 不需要再判断“是不是评估类任务”，而只需要判断：

1. 输入是 URL 还是文本
2. 是否可以直接调用 `a7_extra_evaluate`
3. 是否需要澄清

这会把复杂度从“全局意图判断”降成“局部工具选择”。

### 14.8 Orchestrator 的执行分流

对于这条新能力，建议只新增以下 4 条一阶分流：

1. `content_evaluation:user_url`
2. `content_evaluation:user_text`
3. `content_evaluation:citation_url`
4. `answer_fetch:custom_questions`

前三类进入 A7，最后一类进入 A4。

换句话说，主 LLM 不需要理解一个复杂的开放世界任务集合，它只需要把输入压缩到这 4 条稳定分流上。

### 14.9 路由状态机

```text
START
  -> attach_entrypoint_context
  -> extract_input_signals
  -> llm_choose_tool
  -> apply_guard_rules
  -> if unsupported or ambiguous or low_confidence:
       ask_user
     else:
       dispatch
```

### 14.10 伪代码

```python
def route_user_request(user_input: str, trigger_context: dict | None) -> dict:
    context = build_entrypoint_context(trigger_context)
    signals = extract_input_signals(user_input, context)

    if signals.from_citation:
        return {
            "task_family": "content_evaluation",
            "source_type": "citation_url",
            "needs_confirmation": False,
        }

    llm_result = choose_tool_with_llm(
        user_input=user_input,
        signals=signals,
        context=context,
    )

    routed = apply_guard_rules(signals, llm_result)

    if (
        routed["task_family"] == "ambiguous"
        or routed["source_type"] == "mixed"
        or routed["confidence"] < 0.75
    ):
        return {
            **routed,
            "needs_confirmation": True,
        }

    return routed
```

### 14.11 典型样例

| 用户输入 | 路由结果 |
| :--- | :--- |
| “帮我评估这个网页是否容易被 AI 引用：https://example.com” | `content_evaluation:user_url` |
| “帮我评估下面这段品牌介绍，并给出修改建议：...” | `content_evaluation:user_text` |
| “用下面这几个问题去 Kimi 和 DeepSeek 跑一下” | `answer_fetch:custom_questions` |
| “分析一下下面这些内容” | `ambiguous -> ask_user` |
| citation 卡片上的“评估此引用”点击事件 | `content_evaluation:citation_url` |

### 14.12 结论

主 LLM 应该承担路由职责，但不应该在无约束上下文中自由发挥。

正确做法是：

1. 入口先提供上下文约束
2. 主 LLM 在约束内做工具选择
3. 程序做最小 guardrail 和输入校验
4. 模糊时 ask_user

这样才能把“文章分析”和“自定义问题”这类高相似输入稳定分开。
