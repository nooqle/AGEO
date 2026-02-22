# Specta AI 产品分析报告 — Issue #3 / #4 / #5

> **作者**: Marty Cagan (产品经理)
> **日期**: 2026-02-22
> **状态**: 待用户确认
> **关联文档**: [reform-plan.md](./reform-plan.md)

---

## 目录

1. [Issue #3: 报告质量全面提升](#issue-3-报告质量全面提升)
2. [Issue #4: 全景基线分析（新需求）](#issue-4-全景基线分析新需求)
3. [Issue #5: 交付物导航合并](#issue-5-交付物导航合并)
4. [分阶段实施计划](#分阶段实施计划)
5. [需要向用户确认的问题](#需要向用户确认的问题)

---

## Issue #3: 报告质量全面提升

### 3.1 问题分析

用户反馈了三个核心问题：

**问题 A: 平台分析全是空的，只有"成功"标签**

- **根因**: 前端 `ReportContent.tsx` 的"平台分析"Tab 依赖 `platform_analysis` 数组（由 A5 LLM 生成的 7 章节报告中的第 3 章）。但该数据来自 LLM 输出，不是从 `platform_breakdown`（真实计算数据）派生的。如果 LLM 未生成或生成质量差，前端 fallback 到 legacy `platform_breakdown` 视图，后者只展示"成功/总数"和"提及率%"进度条 — 缺少引用数、回答内容、具体分析。
- **现状**: `_get_a5_system_prompt()` 已要求每个平台包含 `mention_count`, `avg_citations`, `answer_length_range`, `actual_quotes`, `optimization_tips` 等字段，但 LLM 输出的 `platform_analysis` 字段结构和前端渲染的数据模型存在 **字段名不匹配** — 前端读取的是 `mention_rate`, `sentiment`, `total_questions`, `mentions`, `summary`, `status`，而 A5 prompt 要求的是 `mention_count`, `avg_citations`, `actual_quotes`, `performance_summary` 等。

**问题 B: 竞品对比表格为空**

- **根因**: 竞品对比 Tab 读取 `competitor_deep_analysis.comparison_matrix`，但表头期望的字段是 `name/brand`, `bwvs`, `mention_rate`, `sentiment`, `coverage`，而 A5 prompt 要求的字段是 `competitor`, `brand_mention_rate`, `competitor_mention_rate`, `vs_brand`, `advantage_reasons`, `learnings` — **前后端字段完全不匹配**。
- **后果**: 前端找不到任何匹配字段，所有列显示 `--`，看起来"全是空的"。

**问题 C: 优化建议过于泛泛**

- **根因**: 前端"优化建议"Tab 读取的是 `data.recommendations`（老格式: `{priority, title, rationale}`），而 A5 prompt 新输出的是 `actionable_recommendations`（新格式: `{priority, title, eeat_dimension, current_strength, improvement_area, action, expected_impact, ...}`）。前端根本没有渲染 `actionable_recommendations` 字段。
- **用户期望**: 建议应重构为"做得好的" + "做得不好的" + "基于此的具体建议"，并围绕 EEAT 原则。

### 3.2 产品方案

#### 3.2.1 平台分析 Tab 重构

**信息架构**:

```
平台分析 Tab
├── 平台总览卡片 (每个平台一张)
│   ├── 平台名称 + 状态标签(成功/失败)
│   ├── 核心指标行: 提及次数 | 提及率% | 引用数 | 回答字数范围
│   ├── 品牌提及实际引用片段 (actual_quotes)
│   ├── 平台内容偏好说明
│   ├── 优势列表 (strengths)
│   ├── 短板列表 (weaknesses)
│   └── 优化建议 (optimization_tips)
└── 数据来源说明: "数据基于 N 个问题的实际 AI 回答分析"
```

**数据流修复**:
1. 前端适配 A5 prompt 要求的 `platform_analysis` 字段名
2. 后端在 `_normalize_report_data()` 中确保 `platform_analysis` 有合理默认值
3. 当 LLM 生成失败时，从 `platform_breakdown`（真实指标）+ `fetch_results_summary` 自动构建 fallback 平台分析卡片

#### 3.2.2 竞品对比 Tab 重构

**信息架构**:

```
竞品对比 Tab
├── 竞品概览 (overview 文字说明)
├── 量化对照表 (comparison_matrix)
│   ├── 列: 品牌名 | 提及率 | 情感 | 排名 | vs 本品牌 | 差异原因
│   └── 本品牌行高亮显示
├── 可借鉴之处 (learnings)
└── 差异化策略 (differentiation_strategy)
```

**数据流修复**:
1. 前端表格列适配 A5 prompt 的 `comparison_matrix` 字段: `competitor`, `brand_mention_rate`, `competitor_mention_rate`, `vs_brand`, `advantage_reasons`, `learnings`
2. 后端 `_calculate_competitor_metrics()` 已能从 fetch_results 计算真实竞品指标 — 这些数据应作为 `comparison_matrix` 的"基础行"传入 LLM prompt
3. 当 LLM 未生成 `competitor_deep_analysis` 时，fallback 使用 `_calculate_competitor_metrics()` 的真实数据直接展示

#### 3.2.3 优化建议 Tab 重构

**信息架构** (按用户要求的三段式):

```
优化建议 Tab
├── 做得好的 (current_strengths)
│   └── 列表: 具体特征 + 数据支撑 + 占领了哪些用户心智/渠道
├── 做得不好的 (improvement_areas)
│   └── 列表: 缺失点 + 缺少哪些渠道推广 + EEAT 维度标签
├── 具体建议 (actionable_recommendations)
│   ├── 每条: EEAT 维度标签 | 标题 | 行动步骤 | 预期效果 | 难度 | 时间线
│   └── 按优先级排序 (P0 → P1 → P2)
└── 行动计划时间线 (action_plan)
    ├── 短期 (1-3个月)
    ├── 中期 (3-6个月)
    └── 长期 (6-12个月)
```

**数据流修复**:
1. 前端增加 `actionable_recommendations` 渲染组件，展示 EEAT 维度、current_strength、improvement_area、action、expected_impact
2. 从 `actionable_recommendations` 数组中提取 `current_strength` 汇总为"做得好的"板块
3. 从 `actionable_recommendations` 数组中提取 `improvement_area` 汇总为"做得不好的"板块
4. 保留 `recommendations` + `action_plan` 作为兼容/补充

#### 3.2.4 实施范围

| 模块 | 修改内容 | 影响文件 | 复杂度 |
|------|---------|---------|--------|
| 前端平台分析 | 适配新字段名，增强卡片布局 | `ReportContent.tsx` | 中 |
| 前端竞品对比 | 适配 comparison_matrix 字段，表格重构 | `ReportContent.tsx` | 中 |
| 前端优化建议 | 三段式布局，EEAT 标签渲染 | `ReportContent.tsx` | 中 |
| 后端 A5 fallback | platform_analysis 和 competitor fallback | `nodes_a5.py` | 低 |

**预估工作量**: 前端 1-2 天，后端 0.5 天

---

## Issue #4: 全景基线分析（新需求）

### 4.1 需求分析

这是用户提出的最重要需求，涉及产品定位的根本变化。

**核心概念**:
- **基线 (Baseline)** = 品牌在大众/行业全景视角中的位置
- **基线问题**示例: "现在抗衰最好的晚霜产品有哪些？" — 不带特定画像/场景，是行业级全景问题
- **场景细分** = 当前 A2→A3 生成的画像+场景驱动的问题

**用户期望的新流程**:

```
用户输入品牌名
    │
    ▼
[A1] 品牌信息 + 竞品识别
    │
    ▼
[基线分析流程] ← 新增，强制/自动执行
├── A3-baseline: 生成全景基线问题（不依赖画像）
├── A4-baseline: 抓取全景问题的 AI 回答
└── A5-baseline: 生成基线报告（品牌在行业中的位置）
    │
    ▼
[场景细分流程] ← 现有流程，参考基线结果
├── A2: 画像生成
├── A3-persona: 生成画像驱动的问题
├── A4-persona: 抓取场景问题的 AI 回答
└── A5-persona: 生成场景细分报告
```

### 4.2 对现有架构的影响评估

#### 4.2.1 影响程度: **中等** (可渐进实施，不需要推翻重建)

**好消息** — 现有架构已部分支持：
1. A3 prompt 已有 `baseline` 模式（问题模拟的"品牌全景模式"），可直接复用
2. A4/A5 是通用的，不关心问题来源（基线 or 画像），天然支持
3. Orchestrator 星型拓扑支持动态路由，可以按顺序调用"基线流 → 场景流"
4. `question_templates.yaml` 中的 12 个模板问题本质上就是"基线问题"

**需要新增的能力**:
1. 状态管理中区分 `baseline_fetch_results` 和 `persona_fetch_results`
2. A5 需要支持两种报告模式: 基线报告 vs 场景细分报告
3. 前端 Dashboard/Canvas 需要区分基线数据和场景数据
4. Orchestrator prompt 需要调整，支持两阶段执行流程

#### 4.2.2 架构变更清单

| 变更项 | 详情 | 复杂度 |
|--------|------|--------|
| State 扩展 | 新增 `baseline_questions`, `baseline_fetch_results`, `baseline_metrics`, `baseline_report` | 低 |
| A3 基线调用 | Orchestrator 调用 A3 时传入 `mode=baseline`，A3 已支持 | 低 |
| A5 双报告 | A5 接收 `report_type=baseline/persona` 参数，生成不同侧重的报告 | 中 |
| Orchestrator 两阶段 | 修改编排 prompt，先跑基线(A1→A3→A4→A5)，再问用户是否深入场景 | 中 |
| 前端报告分离 | Canvas 中区分"基线报告"和"场景报告"两个交付物 | 中 |
| Dashboard 分区 | 概览页分为"基线指标"和"场景指标"两个区域 | 中 |

### 4.3 产品方案

#### 4.3.1 流程设计

**方案: 自动基线 + 引导场景**

```
用户: "帮我分析观夏"
    │
    ▼
系统: "好的，我先帮您做一个全景基线分析，看看观夏在整个香氛行业中的位置。"
    │
    ▼
自动执行: A1 → A3(baseline) → A4 → A5(baseline)
    │
    ▼
系统: "基线分析完成！观夏的行业 BWVS 基线分为 35.4。
       您想深入某个用户群体的场景分析吗？
       比如可以看看：
       - 25-35岁都市女性对观夏的认知
       - 送礼场景下观夏的推荐率
       - 或者直接告诉我您关注的人群"
    │
    ├── 用户: "看看送礼场景" → A2 → A3(persona) → A4 → A5(persona)
    ├── 用户: "不用了" → 结束
    └── 用户: "继续" → 自动跑默认画像流程
```

**选择理由**:
1. **强制基线**满足用户"尽可能引导"的要求
2. **引导场景**而非强制，给用户选择权
3. **基线先行**确保用户第一时间看到有价值的行业定位数据
4. 符合 reform-plan 的"Chat-first"原则

#### 4.3.2 基线报告 vs 场景报告内容差异

| 维度 | 基线报告 | 场景报告 |
|------|---------|---------|
| 问题类型 | 行业全景问题（不带画像） | 画像/场景驱动问题 |
| 核心价值 | 品牌在行业中的位置 | 在特定人群/场景中的表现 |
| 竞品对比 | 全行业竞品排名 | 特定场景下的竞品对比 |
| 建议导向 | 行业级定位策略 | 场景级内容优化 |
| BWVS 含义 | 行业基线 BWVS | 场景 BWVS |

#### 4.3.3 基线问题生成策略

基线问题应覆盖以下维度（不依赖画像，纯行业视角）:

1. **品类全景**: "现在最好的{品类}有哪些？" / "{品类}推荐排行榜"
2. **品牌认知**: "{品牌}怎么样？" / "{品牌}口碑好吗？"
3. **竞品格局**: "{品牌}和{竞品}哪个好？" / "{品类}哪个品牌最好？"
4. **购买决策**: "{品牌}值得买吗？" / "{品类}性价比最高的是哪个？"
5. **行业趋势**: "{行业}未来趋势是什么？" / "AI搜索中{品类}的推荐格局"

这些与 A3 已有的 `baseline` 模式高度吻合。`question_templates.yaml` 中的 12 个模板也基本属于基线问题。

#### 4.3.4 Dashboard 信息架构

```
Dashboard 概览页
├── 基线数据区
│   ├── 行业 BWVS 基线分
│   ├── 行业提及率
│   ├── 行业竞品排名
│   └── 行业情感分布
├── 场景数据区 (如果有)
│   ├── 场景 BWVS 平均分
│   ├── 各场景提及率对比
│   └── 场景-画像热力图
└── 趋势区
    ├── 基线 BWVS 变化趋势
    └── 场景 BWVS 变化趋势
```

### 4.4 分阶段实施

考虑到这是最重要且影响面最广的需求，建议分 3 个子阶段:

**Phase 4a: 基线流程打通 (3-5天)**
- State 扩展（区分 baseline/persona 数据）
- Orchestrator prompt 调整（自动先跑基线）
- A5 支持 `report_type=baseline` 参数
- 前端 Canvas 区分基线报告和场景报告

**Phase 4b: 基线报告定制 (2-3天)**
- A5 基线 prompt 定制（行业定位视角）
- 基线报告前端渲染优化
- 基线竞品排名可视化

**Phase 4c: Dashboard 分区 (3-5天)**
- Dashboard 分为基线/场景两个数据区
- 基线 vs 场景 BWVS 趋势对比
- 跨场景热力图

---

## Issue #5: 交付物导航合并

### 5.1 问题分析

**当前行为**: 每次执行分析（A4 抓取 + A5 报告），系统都会在 Canvas 中创建新的 Tab 导航项。多次运行后，用户会看到：
- "品牌可见度分析报告" (第1次)
- "品牌可见度分析报告" (第2次)
- "品牌可见度分析报告" (第3次)
- ...

用户无法区分哪个是哪次的结果。

**根因分析**:
1. `canvasStore.addContent()` 使用 `content.id` 做去重，但后端 `save_and_send_artifact()` 每次生成不同的 `id`
2. 没有"同类型交付物合并"的机制
3. 没有历史记录浏览和对话上下文跳转功能

### 5.2 产品方案

#### 5.2.1 合并策略

**方案: 同类型交付物覆盖 + 历史版本浏览**

```
Canvas Tab 区域
├── "分析报告" (1个固定Tab)
│   ├── 顶部: 版本选择器 [v3 最新 ▼]
│   │   ├── v3 - 2026-02-22 14:30 (最新)
│   │   ├── v2 - 2026-02-21 10:15
│   │   └── v1 - 2026-02-20 09:00
│   ├── 当前版本的报告内容
│   └── 底部: "跳转到对话上下文" 链接
├── "抓取结果" (1个固定Tab，同理)
└── "问题列表" (1个固定Tab，同理)
```

**核心规则**:
1. 同一 session 内，同一 `output_type` 的交付物只保留一个 Tab
2. 新结果覆盖旧结果，但旧结果存入历史
3. Tab 标题固定（不带序号），内部通过版本选择器切换
4. 每个版本关联到对应的对话消息 ID，支持"跳转到对话上下文"

#### 5.2.2 数据模型变更

```typescript
// 现有
interface CanvasContent {
  id: string;          // 每次不同
  type: string;        // "report" | "fetchResults" | ...
  title: string;
  data: Record<string, unknown>;
}

// 新增
interface CanvasContent {
  id: string;          // 改为固定: `${sessionId}_${type}`
  type: string;
  title: string;
  data: Record<string, unknown>;
  versions?: ContentVersion[];   // 历史版本
  currentVersion?: number;       // 当前显示版本
  linkedMessageId?: string;      // 对应的对话消息ID
}

interface ContentVersion {
  versionId: string;
  timestamp: string;
  data: Record<string, unknown>;
  linkedMessageId?: string;
}
```

#### 5.2.3 实施范围

| 模块 | 修改内容 | 影响文件 | 复杂度 |
|------|---------|---------|--------|
| 后端 | artifact ID 改为 `{session}_{type}` 格式 | `events.py` | 低 |
| 前端 Store | `addContent` 支持版本合并逻辑 | `canvasStore.ts` | 中 |
| 前端 UI | 版本选择器组件 + 跳转链接 | `CanvasHeader.tsx`, `ReportContent.tsx` 等 | 中 |
| 前端对话 | 消息 ID 锚点跳转 | `ChatPanel.tsx` | 低 |

**预估工作量**: 2-3 天

---

## 分阶段实施计划

综合三个 Issue 的优先级和依赖关系：

```
Phase 1: Issue #3 报告质量 (2-3天) ← 最紧急，用户体验直接受损
├── 平台分析 Tab 字段适配 + 增强渲染
├── 竞品对比 Tab 字段适配 + 表格重构
├── 优化建议 Tab 三段式重构 (做得好/做得不好/具体建议)
└── A5 fallback 增强

Phase 2: Issue #5 交付物合并 (2-3天) ← 体验痛点，影响可用性
├── artifact ID 固定化
├── canvasStore 版本合并逻辑
├── 版本选择器 UI
└── 对话上下文跳转

Phase 3: Issue #4 基线分析 (8-13天) ← 最重要但最大，分子阶段
├── Phase 4a: 基线流程打通 (3-5天)
├── Phase 4b: 基线报告定制 (2-3天)
└── Phase 4c: Dashboard 分区 (3-5天)
```

**总预估**: 12-19 天

### 优先级排序理由

1. **Issue #3 最先**: 报告是产品的核心交付物，质量差 = 产品不可用。且修复范围清晰，主要是前后端字段对齐。
2. **Issue #5 其次**: 多次分析后导航混乱影响可用性，修复后为 Issue #4 的"基线报告 vs 场景报告"奠定基础。
3. **Issue #4 最后**: 需求最重要但范围最大，需要 Issue #3 的报告质量和 Issue #5 的版本管理作为基础。

---

## 需要向用户确认的问题

### 关于 Issue #3

1. **竞品对比表格的字段**: 用户希望看到哪些列？建议方案是: 品牌名 | 提及率 | 情感 | 排名 | 与本品牌对比 | 可借鉴之处。是否还需要其他维度？

2. **"做得好的/做得不好的"分类标准**: 建议基于 EEAT 四个维度 (Experience/Expertise/Authoritativeness/Trustworthiness) 进行分类。用户是否同意？还是希望用其他分类框架？

### 关于 Issue #4

3. **基线分析是否强制执行**: 用户说"尽可能强制引导，或自动跑"。建议方案是: **用户输入品牌名后自动执行基线分析**（不需要确认），基线完成后引导用户选择是否做场景细分。用户是否同意这个流程？

4. **基线问题数量**: 现有模板是 12 个基线问题。基线分析是否使用这 12 个问题，还是需要 LLM 动态生成更多？更多问题 = 更全面但耗时更长。

5. **基线和场景的 BWVS 是否独立计算**: 建议基线和场景各自有独立的 BWVS 分数（因为问题集不同，指标含义不同）。Dashboard 上同时展示两个分数。用户是否同意？

6. **场景细分是否参考基线报告**: 用户提到"场景细分分析时应参考基线报告"。建议在 A5 场景报告的 LLM prompt 中注入基线报告摘要作为上下文。用户是否认可这个实现方式？

### 关于 Issue #5

7. **历史版本保留策略**: 建议同一 session 内最多保留 10 个历史版本，超出后淘汰最旧版本。是否合理？

8. **跳转到对话上下文**: 点击"跳转"后，是否只需要滚动到对应消息位置并高亮？还是需要更复杂的交互（比如展开上下文、折叠中间消息等）？

### 跨 Issue 优先级

9. **实施顺序确认**: 建议顺序为 Issue #3 → Issue #5 → Issue #4。用户是否同意？或者是否希望 Issue #4 的基线流程更优先？

---

## 附录: 关键代码位置参考

| 功能 | 文件路径 | 行号 |
|------|---------|------|
| A5 系统 prompt (7章节报告) | `aeo-platform/backend/app/workflow/nodes_a5.py` | 773-910 |
| A5 指标计算 | `aeo-platform/backend/app/workflow/nodes_a5.py` | 509-673 |
| A5 竞品指标计算 | `aeo-platform/backend/app/workflow/nodes_a5.py` | 676-770 |
| A5 报告数据规范化 | `aeo-platform/backend/app/workflow/nodes_a5.py` | 1045-1068 |
| 前端报告渲染 | `frontend/src/components/canvas/contents/ReportContent.tsx` | 1-723 |
| Canvas Store | `frontend/src/stores/canvasStore.ts` | 1-118 |
| A3 基线模式 prompt | `aeo-platform/backend/prompts/question_simulation_agent.md` | 16-47 |
| 工作流图定义 | `aeo-platform/backend/app/workflow/graph.py` | 32-86 |
| Orchestrator 路由 | `aeo-platform/backend/app/workflow/orchestrator_node.py` | - |
