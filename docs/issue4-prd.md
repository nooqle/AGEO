# Issue #4: 全景基线分析 PRD

> **作者**: Marty Cagan (产品经理)
> **日期**: 2026-02-22
> **状态**: 待用户确认
> **前置依赖**: Issue #3 (已完成), Issue #5 (已完成)
> **参考文档**: [prd-v2-confirmed.md](./prd-v2-confirmed.md), [reform-plan.md](./reform-plan.md), [ux-design-v2.md](./ux-design-v2.md)

---

## 1. 问题陈述与目标

### 1.1 现状问题

当前系统的分析流程是 A1 -> A2(可选) -> A3 -> A4 -> A5 的单一线性流程。所有问题要么来自 YAML 模板（brand 模式），要么来自用户画像驱动（persona 模式）。缺少一个**行业全景基线视角**：

- 用户拿到报告后无法判断"品牌在整个行业中处于什么位置"
- 场景分析缺少参照系：场景 BWVS 42 是好还是差？没有基线对比
- 模板问题固定 12 个且不随品牌/行业变化，无法真实反映用户搜索行为
- 无法追踪品牌在行业中的位置变化趋势

### 1.2 目标

1. 引入**基线分析**概念：品牌创建/确认后自动执行行业全景分析，得到基线 BWVS
2. 基线报告**独立可用**，不依赖用户画像即可交付价值
3. 后续场景分析自动**注入基线上下文**，提供对比参照
4. 基线支持**重跑**，历史版本通过 Issue #5 版本选择器查看
5. **定时监测**功能可推迟到 Phase 4b

### 1.3 成功指标

| 指标 | 目标值 |
|------|--------|
| 基线分析端到端成功率 | >= 70%（仅 API 平台可达 85%+） |
| 基线报告用户满意度 | "报告有行业参考价值" >= 80% |
| 基线问题中直接品牌问题占比 | <= 10% |
| 基线问题覆盖核心产品领域 | 100% |

---

## 2. 用户故事

### US-1: 首次品牌分析 (核心路径)

> 作为品牌分析师，我希望输入品牌名称后，系统自动完成行业全景基线分析，让我快速了解品牌在 AI 搜索中的行业位置。

**验收标准**:
- 用户输入"帮我分析兰蔻"
- A1 完成后展示品牌信息确认卡片（品牌名/行业/竞品/覆盖平台）
- 用户确认后自动启动基线分析 (A3 baseline -> A4 -> A5 baseline)
- 基线报告在 Canvas `report_baseline` Tab 中展示
- 基线完成后展示引导卡片（场景细化/重跑基线/直接提问）

### US-2: 场景细化 (含基线对比)

> 作为品牌分析师，我希望在基线分析完成后，可以选择特定用户群体深入分析，且场景报告能对比基线数据。

**验收标准**:
- 用户点击"开始场景细化"
- A2 生成画像 -> 用户选择 -> A3 persona -> A4 -> A5 persona
- 场景报告在 Canvas `report_persona` Tab 中展示（与基线报告分开）
- 场景报告包含"与基线对比"章节（如：场景 BWVS 51 vs 基线 42，+21%）

### US-3: 重跑基线

> 作为品牌分析师，我希望可以重新执行基线分析，获取最新数据，同时保留历史版本。

**验收标准**:
- 用户说"重新跑一次基线"或点击引导卡片中的"重新运行基线"
- 跳过 A1（复用已有品牌信息），直接 A3 baseline -> A4 -> A5 baseline
- 新报告覆盖 Canvas `report_baseline` Tab
- 旧报告通过版本选择器可查看（Issue #5 机制已就绪）

### US-4: 仅基线 (无场景)

> 作为品牌分析师，我希望基线报告本身就能提供足够的分析价值，不强制要求做场景分析。

**验收标准**:
- 基线分析完成后，用户选择"直接提问"或不做场景分析
- 基线报告包含完整的：总览/行业洞察/平台分析/竞品对比/优化建议/风险提示
- BWVS 基线分数独立计算并存入快照

---

## 3. 完整流程设计

### 3.1 两阶段流程

```
Phase 1: 基线分析 (必选)
==================================================

用户: "帮我分析兰蔻"
    |
    v
[A1] 品牌信息 + 竞品识别
    |
    v
Orchestrator 通过 ask_user 展示品牌信息确认卡片
    |-- 用户: "确认" --> 继续
    |-- 用户: "修改xxx" --> Orchestrator 处理修改后重新确认
    |
    v
Orchestrator 回复: "好的，我先为您做一个全景基线分析..."
    |
    v
Orchestrator 调用 question_simulation(mode="baseline_dynamic")
    |
    v
[A3] 生成基线问题 (10-15 个, 用户视角, 直接品牌问题 <= 10%)
    |
    v
Orchestrator 调用 answer_fetch
    |
    v
[A4] 4 平台抓取
    |
    v
Orchestrator 调用 data_analytics(report_type="baseline")
    |
    v
[A5] 计算基线指标 + 生成基线报告
    |
    v
输出: report_baseline Tab (Canvas)
    |
    v
Orchestrator 通过 ask_user 展示引导卡片:
    - [开始场景细化分析] (推荐)
    - [重新运行基线分析]
    - [直接提问]


Phase 2: 场景分析 (可选)
==================================================

用户选择 "开始场景细化"
    |
    v
Orchestrator 调用 persona_generation
    |
    v
[A2] 生成画像
    |
    v
Orchestrator 通过 ask_user 展示画像选择
    |
    v
Orchestrator 调用 question_simulation(mode="persona_focused")
    |
    v
[A3] 生成场景问题
    |
    v
[A4] 4 平台抓取
    |
    v
Orchestrator 调用 data_analytics(report_type="persona")
    |
    v
[A5] 计算场景指标 + 生成场景报告 (注入基线上下文)
    |
    v
输出: report_persona Tab (Canvas)
```

### 3.2 重跑基线流程

```
用户: "重新跑一次基线" / 引导卡片点击
    |
    v
Orchestrator 判断: 已有 brand_profile --> 跳过 A1
    |
    v
A3(baseline_dynamic) --> A4 --> A5(baseline)
    |
    v
新基线报告覆盖 report_baseline Tab
旧报告自动存入 versions[] (Issue #5 机制)
    |
    v
新快照 (AnalysisSnapshot) 写入数据库
```

### 3.3 Orchestrator 编排策略

**关键原则**: 不新增 graph 节点或 edge。基线编排完全通过 Orchestrator 的 LLM Function Calling 决策实现。

**Orchestrator prompt 需要新增的指导**:

1. 当用户请求品牌分析时，A1 完成后 **必须先用 ask_user 确认品牌信息**
2. 确认后 **自动执行基线分析**（无需用户再次确认）：question_simulation(mode="baseline_dynamic") -> answer_fetch -> data_analytics(report_type="baseline")
3. 基线完成后 **用 ask_user 展示引导卡片**
4. 用户选择场景细化时：persona_generation -> question_simulation(mode="persona_focused") -> answer_fetch -> data_analytics(report_type="persona")

**与现有工具的关系**:

- `question_simulation` 工具新增 `mode` 参数值 `"baseline_dynamic"`
- `data_analytics` 工具新增 `report_type` 参数 (`"baseline"` / `"persona"`)
- 其他工具不变

---

## 4. 基线问题生成规则 (A3 baseline_dynamic)

### 4.1 核心原则

基线问题必须是**用户视角**的行业全景问题，模拟真实用户在 AI 搜索中的搜索行为。直接品牌问题（"xx品牌怎么样"）**最多占 10%**。

### 4.2 问题分类与比例

| 类别 | 比例 | 说明 | 示例 |
|------|------|------|------|
| 品类需求咨询 | 30% | 用户在主要产品领域的需求咨询 | "预算1000元的眼霜怎么选？" |
| 场景化选购 | 25% | 带有预算/场景/用途的选购问题 | "送妈妈什么护肤品比较好？" |
| 品类对比排名 | 20% | 行业排名、对比类问题 | "国产高端护肤品排行榜" |
| 行业趋势探索 | 15% | 行业发展、新趋势类问题 | "2026年护肤品行业有什么新趋势？" |
| 品牌直接问题 | 10% (上限) | 直接提及目标品牌 | "兰蔻和雅诗兰黛哪个好？" |

### 4.3 生成参数

- **总问题数**: 10-15 个（根据品牌产品线数量动态调整）
- **产品线覆盖**: 必须覆盖 `brand_profile.core_products` 中的核心产品
- **竞品引入**: 品类对比排名类问题中自然引入 A1 识别的竞品
- **平台分配**: 每个问题发送到全部 4 个平台
- **口语化**: 问题像真实用户在 AI 搜索中输入的自然语言

### 4.4 实现方式

A3 新增 `baseline_dynamic` 模式，使用 LLM 动态生成。不使用固定模板。

```python
# A3 模式路由 (user_decisions.a3_mode)
a3_mode:
  - "brand"              # 现有: YAML 模板驱动 (保留作为 fallback)
  - "persona"            # 现有: 画像聚焦
  - "baseline_dynamic"   # 新增: 动态基线生成
```

A3 baseline_dynamic prompt 核心约束:

```
你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，
生成模拟用户在 AI 搜索引擎中会提问的**行业全景问题**。

## 核心规则
1. 问题必须是**用户视角**，模拟真实消费者的搜索行为
2. 直接提及目标品牌的问题**不超过总数的 10%**
3. 问题必须覆盖品牌的**主要产品领域**
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 搜索中输入的

## 问题分类比例
- 品类需求咨询 (30%)
- 场景化选购 (25%)
- 品类对比排名 (20%)
- 行业趋势探索 (15%)
- 品牌直接问题 (10% 上限)

## 输出格式 (JSON)
{
  "questions": [
    {
      "question_id": "bl_001",
      "core_question": "问题文本",
      "category": "品类需求咨询|场景化选购|品类对比排名|行业趋势探索|品牌直接问题",
      "user_intent": "用户意图",
      "decision_stage": "认知|兴趣|评估|决策",
      "covers_product": "对应的产品线(可选)"
    }
  ]
}
```

---

## 5. 基线报告内容 (A5 baseline)

### 5.1 基线报告 vs 场景报告

| 维度 | 基线报告 (report_baseline) | 场景报告 (report_persona) |
|------|---------------------------|--------------------------|
| 问题来源 | A3 baseline_dynamic 动态生成 | A3 persona 画像驱动 |
| BWVS 含义 | 行业基线 BWVS | 场景 BWVS |
| 核心价值 | 品牌在行业中的位置 | 品牌在特定场景的表现 |
| 竞品对比 | 行业竞争格局 | 场景竞争态势 |
| 建议导向 | 行业级定位+内容布局 | 场景级内容优化+触点策略 |
| 独立可用 | 是 | 是（但有基线对比更有价值） |
| Canvas Tab | `{sessionId}_report_baseline` | `{sessionId}_report_persona` |

### 5.2 基线报告独有内容

基线报告的 A5 prompt 应强调：

1. **行业定位**: 品牌在整个行业 AI 搜索生态中的位置
2. **行业全景竞品格局**: 哪些竞品在行业通用问题中更常出现
3. **行业级优化建议**: 如何提升品牌在行业搜索中的整体可见性
4. **基线指标**: 作为后续场景分析的参照基准

### 5.3 场景报告注入基线上下文

场景报告的 A5 prompt 需要注入基线数据:

```python
if report_type == "persona" and baseline_report:
    sections.append(
        f"## 基线报告参考\n"
        f"- 基线 BWVS: {baseline_report['bwvs_index']}\n"
        f"- 基线提及率: {baseline_report['mention_rate']}\n"
        f"- 行业竞品格局: {baseline_report['competitor_overview']}\n"
        f"- 基线核心发现: {baseline_report['key_findings']}\n"
        f"\n请在场景报告中对比基线数据，说明该场景表现与行业基线的差异。"
    )
```

---

## 6. MVP 范围 (Phase 4a)

### 6.1 Phase 4a: 基线流程打通 (优先, 3-5 天)

**必须做:**

| # | 工作项 | 涉及文件 |
|---|--------|----------|
| 1 | AgentState 新增 `analysis_mode` 和 `baseline_*` 字段 | `state.py` |
| 2 | A3 新增 `baseline_dynamic` 模式 + 基线问题生成 prompt | `nodes_a3.py` |
| 3 | A5 支持 `report_type` 参数，区分 `baseline` / `persona` | `nodes_a5.py` |
| 4 | A5 场景报告注入基线上下文 | `nodes_a5.py` |
| 5 | Orchestrator prompt 新增基线编排指导 | `general_react_agent.md` |
| 6 | `question_simulation` 工具 mode 参数新增 `baseline_dynamic` | `orchestrator_node.py` |
| 7 | `data_analytics` 工具新增 `report_type` 参数 | `orchestrator_node.py` |
| 8 | `save_and_send_artifact` 传入 `output_type="report_baseline"` / `"report_persona"` | `nodes_a5.py` |
| 9 | 前端 ReportContent 区分基线/场景报告标题和视角 | `ReportContent.tsx` |
| 10 | 快照 (AnalysisSnapshot) 新增 `snapshot_type` 字段 | `snapshot_service.py`, 数据模型 |

**不做 (推迟):**

- 定时监测调度器 (Phase 4b)
- Dashboard 基线/场景双区展示 (Phase 4c)
- BWVS 趋势曲线 (Phase 4c)
- 基线 vs 上次基线的 delta 趋势对比 (Phase 4b)

### 6.2 Phase 4b: 定时监测 + 历史对比 (推迟, 2-3 天)

- 定时任务调度器 (`monitoring_scheduler.py`)
- 快照 `snapshot_type` 过滤查询
- 重跑基线自动生成 delta_vs_previous

### 6.3 Phase 4c: Dashboard 分区 (推迟, 3-5 天)

- 基线/场景 BWVS 双区 Dashboard
- BWVS 趋势曲线
- 基线历史快照浏览

---

## 7. 数据模型变更

### 7.1 AgentState 扩展

```python
class AgentState(TypedDict):
    # ... 现有字段保持不变 ...

    # 新增: 基线分析相关
    analysis_mode: str              # "baseline" / "persona" / "full"
    baseline_questions: list        # 基线问题列表 (A3 baseline_dynamic 输出)
    baseline_fetch_results: list    # 基线抓取结果 (A4 输出)
    baseline_metrics: dict          # 基线指标 (A5 计算)
    baseline_report: dict           # 基线报告 (A5 生成)
```

**注意**: 现有 `baseline_fetch_results` 字段已存在于 state.py（用于 selective_refetch 的"未选中平台结果保存"）。需要评估是否复用或重命名，避免语义冲突。

建议方案：将现有 `baseline_fetch_results` 重命名为 `preserved_fetch_results`（更准确反映其用途），新增的 `baseline_fetch_results` 用于基线分析结果。

### 7.2 AnalysisSnapshot 扩展

快照模型新增 `snapshot_type` 字段:

```python
class AnalysisSnapshot:
    # ... 现有字段 ...
    snapshot_type: str  # "baseline" / "persona" / "legacy"(默认, 向后兼容)
```

### 7.3 A3 输出格式 (baseline_dynamic)

与现有 persona 模式输出格式一致，仅 `category` 值不同:

```json
{
  "simulated_questions": [
    {
      "question_id": "bl_001",
      "category": "品类需求咨询",
      "core_question": "预算1000元的眼霜怎么选？",
      "user_intent": "选购咨询",
      "decision_stage": "评估",
      "platform": "kimi"
    }
  ]
}
```

### 7.4 A5 输入变更

`a5_analytics_node` 需要新增逻辑:
- 从 `state.get("analysis_mode")` 读取当前模式
- 基线模式: 使用 `baseline_questions` + `baseline_fetch_results`
- 场景模式: 使用现有 `questions` + `fetch_results`，并注入 `baseline_report` 作为上下文
- 输出时使用对应的 `output_type`: `report_baseline` 或 `report_persona`

---

## 8. 验收标准

### 8.1 功能验收 (Phase 4a)

| # | 验收项 | 可测试条件 |
|---|--------|-----------|
| AC-1 | 品牌确认后自动执行基线分析 | 输入品牌名 -> A1 -> 确认 -> 自动 A3(baseline)->A4->A5(baseline) |
| AC-2 | 基线问题质量 | 直接品牌问题 <= 10%; 覆盖 core_products; 10-15 个问题; 口语化 |
| AC-3 | 基线报告独立可用 | report_baseline Tab 展示完整 6 个子 Tab (总览/洞察/平台/竞品/建议/风险) |
| AC-4 | 基线报告 BWVS 独立 | 基线 BWVS 写入快照，snapshot_type="baseline" |
| AC-5 | 场景报告注入基线 | 场景报告中包含"与基线对比"数据（BWVS 差值、提及率差值） |
| AC-6 | 基线和场景分 Tab | Canvas 中 report_baseline 和 report_persona 是独立 Tab |
| AC-7 | 重跑基线 | 重跑后新报告覆盖 report_baseline Tab; 旧报告进 versions[] |
| AC-8 | 引导卡片 | 基线完成后展示 3 个选项: 场景细化/重跑基线/直接提问 |
| AC-9 | Orchestrator 编排正确 | 不需要用户手动指定"基线模式"，系统自动按流程执行 |

### 8.2 非功能验收

| # | 验收项 | 条件 |
|---|--------|------|
| NF-1 | 基线分析耗时 | API-first 模式下 <= 3 分钟 |
| NF-2 | 无回归 | 现有 persona 模式、brand 模式正常工作 |
| NF-3 | 容错 | A3 baseline_dynamic 失败时 fallback 到 brand 模板模式 |

---

## 9. 风险与缓解措施

| 风险 | 严重度 | 概率 | 缓解措施 |
|------|--------|------|----------|
| A3 baseline_dynamic LLM 生成的问题质量不稳定 | 中 | 中 | 增加输出验证（问题数量/分类比例/品牌问题占比检查）；失败时 fallback 到 brand 模板模式 |
| `baseline_fetch_results` 字段名与现有 selective_refetch 的 `baseline_fetch_results` 冲突 | 高 | 确定 | 重命名现有字段为 `preserved_fetch_results`（需同步修改 selective_refetch 相关代码） |
| Orchestrator prompt 过长导致 LLM 决策质量下降 | 中 | 低 | 基线编排指导保持简洁；使用分段式 prompt（仅在对应阶段注入对应指导） |
| 基线和场景共用 A4/A5 时 state 数据互相覆盖 | 高 | 中 | 基线结果存入 `baseline_*` 字段，场景结果存入现有字段；A4/A5 根据 `analysis_mode` 决定读写哪组字段 |
| 基线 A5 和场景 A5 使用不同 prompt 导致报告风格不一致 | 低 | 低 | 共用核心 prompt，仅在开头注入 report_type 上下文（"本次为行业基线分析" vs "本次为场景分析"） |
| 前端已实现的版本选择器可能因 output_type 变化需要适配 | 低 | 低 | Issue #5 版本合并基于固定 `{sessionId}_{outputType}` ID，report_baseline 和 report_persona 天然分 Tab，无需额外适配 |

---

## 10. 与已完成工作的对齐

### 10.1 Issue #3 (报告质量重构) 的影响

- A5 的 `_calculate_competitor_metrics()` 已在 A5 LLM 调用前执行，竞品指标提前计算 -- 基线报告可直接使用
- 报告 6 个 Tab 的字段映射已对齐 -- 基线报告和场景报告共用同一 ReportContent 渲染组件
- EEAT 三段式优化建议已实现 -- 基线报告的优化建议自动采用此格式

### 10.2 Issue #5 (交付物导航合并) 的影响

- `save_and_send_artifact()` 已使用固定 `{session_id}_{output_type}` 格式 -- 基线报告传入 `output_type="report_baseline"`，场景报告传入 `output_type="report_persona"`，自动分 Tab
- 版本合并 (`canvasStore.addContent`) 和版本选择器已实现 -- 重跑基线时，旧报告自动存入 `versions[]`
- `linkedMessageId` 已支持 -- 对话跳转无需额外开发

### 10.3 不需要改动的部分

- Canvas 类型定义 (`types/canvas.ts`): ContentVersion 已支持
- 前端 canvasStore: addContent 版本合并逻辑已就绪
- 后端 events.py: save_and_send_artifact 固定 ID 已就绪
- 版本选择器 UI: 已由 Issue #5 完成

---

## 11. 实施清单 (Phase 4a)

### 11.1 后端

| # | 文件 | 修改内容 | 估时 |
|---|------|---------|------|
| B-1 | `state.py` | 新增 `analysis_mode`, `baseline_questions`, `baseline_metrics`, `baseline_report` 字段; 重命名 `baseline_fetch_results` -> `preserved_fetch_results` | 0.5h |
| B-2 | `nodes_a3.py` | 新增 `_a3_baseline_dynamic_mode()` 函数 + baseline prompt; A3 路由新增 `baseline_dynamic` 分支 | 3h |
| B-3 | `nodes_a5.py` | 支持 `report_type` 参数; 基线模式读写 `baseline_*` 字段; 场景模式注入 `baseline_report` 上下文; `save_and_send_artifact` 使用对应 output_type | 3h |
| B-4 | `orchestrator_node.py` | `question_simulation` 工具 mode 新增 `baseline_dynamic`; `data_analytics` 工具新增 `report_type` 参数 | 1h |
| B-5 | `general_react_agent.md` | 新增基线编排指导段落 | 1h |
| B-6 | `nodes_followup.py` | `selective_refetch_node` 中 `baseline_fetch_results` -> `preserved_fetch_results` | 0.5h |
| B-7 | `snapshot_service.py` + 数据模型 | AnalysisSnapshot 新增 `snapshot_type` 字段; 写入时传入类型 | 1h |

### 11.2 前端

| # | 文件 | 修改内容 | 估时 |
|---|------|---------|------|
| F-1 | `ReportContent.tsx` | 根据 output_type 区分基线/场景报告标题 ("行业基线分析报告" vs "场景分析报告") | 1h |

### 11.3 总计

- 后端: ~10h
- 前端: ~1h
- 测试 + 联调: ~4h
- **总计: ~15h (约 2-3 天)**
