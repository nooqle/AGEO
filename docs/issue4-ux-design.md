# Issue #4: 全景基线分析 — 交互设计细化文档

**设计师**: Don Norman
**日期**: 2026-02-22
**状态**: 细化设计 — 待用户确认
**前置文档**: `ux-design-v2.md` (初版), `prd-v2-confirmed.md` (PRD)

---

## 目录

1. [设计概述与原则](#1-设计概述与原则)
2. [品牌信息确认卡片](#2-品牌信息确认卡片)
3. [基线分析等待体验](#3-基线分析等待体验)
4. [基线报告完成引导](#4-基线报告完成引导)
5. [重跑基线](#5-重跑基线)
6. [基线 vs 场景报告在 Canvas 中的区分](#6-基线-vs-场景报告在-canvas-中的区分)
7. [组件复用与新建清单](#7-组件复用与新建清单)
8. [数据流与事件设计](#8-数据流与事件设计)

---

## 1. 设计概述与原则

### 1.1 设计目标

Issue #4 全景基线分析是用户进入 Specta AI 后的**首次核心体验**。用户从 Dashboard 创建品牌后跳转到 Chat，交互流程为：

```
品牌创建 → Chat 打开 → 品牌信息确认 → 自动基线分析 → 报告完成引导
```

设计需要解决：
- 让用户清晰了解系统正在做什么（透明感）
- 15-20 分钟的等待不焦虑（进度可视化）
- 完成后引导下一步（不留用户迷茫）

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **Chat-first** | 所有交互在对话流中自然发生，不使用弹窗或跳转页面 |
| **渐进展示** | 信息分阶段逐步出现，避免一次性信息过载 |
| **可离开** | 长时间分析过程中，用户可以安全离开页面 |
| **CSS 变量** | 所有颜色使用 `--bg-primary`, `--text-secondary` 等变量，不硬编码 |
| **复用优先** | 优先复用 ConfirmationBlock、StageResultCard、MiniProgress 等现有组件 |

---

## 2. 品牌信息确认卡片

### 2.1 触发时机

用户从 Dashboard 创建品牌后，自动跳转到 Chat 页面。系统发送第一条 Agent 消息，包含品牌信息确认卡片。

### 2.2 交互流程

```
用户创建品牌（Dashboard）
      |
      v
跳转 Chat → Agent 发送欢迎消息 + 品牌确认卡片
      |
      +---> 用户点击 [确认并开始] → 触发基线分析
      |
      +---> 用户点击 [修改信息] → 输入框获焦，用户输入修改内容
      |                          → Agent 回复已更新，再次展示确认卡片
      |
      +---> 用户直接在输入框输入 → 视为修改请求，Agent 理解并更新
```

### 2.3 界面线框图

```
+--------------------------------------------------------------------+
|  Chat 消息流                                                         |
|                                                                      |
|  +----------------------------------------------------------------+  |
|  |  Specta AI                                                      |  |
|  |                                                                 |  |
|  |  您好！我将为您分析「兰蔻」在 AI 搜索引擎中的品牌可见性。         |  |
|  |  请确认以下品牌信息：                                              |  |
|  |                                                                 |  |
|  |  +-----------------------------------------------------------+  |  |
|  |  |                                                           |  |  |
|  |  |  品牌名称    兰蔻 (Lancome)                                |  |  |
|  |  |  所属行业    美妆护肤                                       |  |  |
|  |  |  官方域名    lancome.com.cn                                |  |  |
|  |  |  核心产品    小黑瓶精华、菁纯面霜、大眼精华                  |  |  |
|  |  |  主要竞品    雅诗兰黛、SK-II、资生堂                         |  |  |
|  |  |                                                           |  |  |
|  |  |  分析覆盖平台:                                              |  |  |
|  |  |  [DeepSeek] [Kimi] [豆包] [混元]                           |  |  |
|  |  |                                                           |  |  |
|  |  +-----------------------------------------------------------+  |  |
|  |                                                                 |  |
|  |  [===确认并开始基线分析===]    [修改信息]                         |  |
|  |                                                                 |  |
|  |  Enter 确认  |  您也可以直接输入修改内容                          |  |
|  +----------------------------------------------------------------+  |
|                                                                      |
+--------------------------------------------------------------------+
```

### 2.4 实现方案：复用 ConfirmationBlock

品牌信息确认卡片**复用现有的 `ConfirmationBlock` 组件**（`src/components/chat/Message/ConfirmationBlock.tsx`），通过后端发送 `inline_confirmation` 事件，type 设为 `brand_info`。

**后端事件格式**：
```json
{
  "type": "inline_confirmation",
  "data": {
    "requestId": "confirm_brand_001",
    "type": "brand_info",
    "message": "请确认以下品牌信息...",
    "stepName": "品牌信息确认",
    "options": [
      { "id": "confirm", "label": "确认并开始基线分析", "recommended": true },
      { "id": "modify", "label": "修改信息" }
    ],
    "allowTextInput": true
  }
}
```

**品牌信息展示**：作为 `message` 字段中的结构化文本，由 MarkdownContent 渲染。品牌信息使用表格格式（Markdown table），确保在消息流中清晰可读。

**与单独卡片组件的权衡**：
- 方案 A（当前选择）：复用 ConfirmationBlock，品牌信息嵌入 message 文本 → 零新组件，但信息展示自由度受限于 Markdown
- 方案 B：新建 BrandConfirmCard 组件，结构化展示品牌信息 → 视觉效果更好，但增加一个新组件
- **建议**：Phase 1 先用方案 A 快速实现，如果用户反馈信息展示不够清晰，Phase 2 升级为方案 B

### 2.5 修改信息流程

```
用户点击 [修改信息]
      |
      v
输入框自动获焦（现有行为），placeholder 变为 "请输入要修改的内容..."
      |
      v
用户输入: "竞品改成兰蔻、Dior、Helena Rubinstein"
      |
      v
Agent 解析修改请求，更新品牌信息
      |
      v
再次展示确认卡片（新的 ConfirmationBlock），信息已更新
      |
      v
用户确认 → 进入基线分析
```

### 2.6 状态管理

确认卡片的状态通过现有的 `InlineConfirmation` 机制管理：

| 状态 | 视觉表现 |
|------|----------|
| 等待确认 | 按钮可点击，品牌色高亮 |
| 已确认 | 按钮变为已选择态（品牌色描边 + 对勾），不可再点击 |
| 修改中 | 原卡片按钮禁用，新消息（用户修改内容）出现在下方 |

---

## 3. 基线分析等待体验

### 3.1 设计策略

基线分析（A1 → A3 → A4 → A5）预计耗时 15-20 分钟（含浏览器抓取）。等待体验设计分为两个维度：

| 维度 | 组件 | 信息层次 |
|------|------|----------|
| **进度总览** | MiniProgress（复用） | 总进度百分比 + 预估剩余时间 |
| **阶段结果** | StageResultCard（复用） | 每个阶段完成后展示摘要卡片 |

### 3.2 Chat 区域等待体验

```
+--------------------------------------------------------------------+
|  Chat 消息流                                                         |
|                                                                      |
|  +----------------------------------------------------------------+  |
|  |  Specta AI                                                      |  |
|  |                                                                 |  |
|  |  好的，正在为「兰蔻」执行全景基线分析。                             |  |
|  |  这将帮助我们了解品牌在 AI 平台上的基础表现。                       |  |
|  |  预计需要 15-20 分钟，您可以安全离开此页面。                          |  |
|  +----------------------------------------------------------------+  |
|                                                                      |
|  +--- StageResultCard (A1) ---+                                      |
|  | # 品牌识别                                      已完成            |
|  | 品牌: 兰蔻 | 行业: 美妆 | 竞品: 3                                 |
|  +-----------------------------+                                     |
|                                                                      |
|  +--- StageResultCard (A3) ---+                                      |
|  | # 生成全景问题                                  已完成            |
|  | 已生成 12 个行业通用问题                                           |
|  | 品类需求(4) 场景选购(3) 对比排名(2) 趋势(2) 品牌(1)                |
|  +-----------------------------+                                     |
|                                                                      |
|  +--- StageResultCard (A4) ---+                                      |
|  | # AI 平台抓取                             进行中 3/4              |
|  | DeepSeek [ok] | Kimi [..] | 豆包 [ok] | 混元 [-]                  |
|  +-----------------------------+                                     |
|                                                                      |
|  +--- MiniProgress ---+                                              |
|  | [..] 正在分析... . 3/4 (约 2 分钟)                                |
|  | ==========================---------- 72%                          |
|  +---------------------+                                             |
|                                                                      |
+--------------------------------------------------------------------+
```

### 3.3 阶段事件映射

基线分析各阶段与 StageResultCard 的映射关系：

| 阶段 | resultType | stageName | 数据内容 |
|------|-----------|-----------|----------|
| A1 品牌识别 | `brand_profile` | "品牌识别" | 品牌名、行业、竞品数量 |
| A3 问题生成 | `questions` | "生成全景问题" | 问题数量、分类分布、示例 |
| A4 平台抓取 | `platform_status` | "AI 平台抓取" | 4 个平台抓取状态 |
| A5 数据分析 | `metrics_preview` | "基线分析" | BWVS 分数、得分段 |

**注意**：基线流程跳过 A2（画像生成），因此 StageResultCard 不会出现 `personas` 类型。

### 3.4 MiniProgress 基线专属步骤

```typescript
// 基线分析的 MiniProgress steps
const BASELINE_STEPS: ProgressStep[] = [
  { id: 'a1_brand', label: '品牌识别', status: 'pending' },
  { id: 'a3_question', label: '问题生成', status: 'pending' },
  { id: 'a4_fetch', label: 'AI 平台抓取', status: 'pending' },
  { id: 'a5_analytics', label: '数据分析', status: 'pending' },
];
// 注意：没有 a2_persona 步骤
```

**复用现有 MiniProgress**，不需要修改组件本身。步骤列表由后端事件驱动，前端根据 `plan_update` 事件动态构建。

### 3.5 Canvas 区域等待体验

| 阶段 | Canvas 状态 |
|------|------------|
| 分析开始前 | 空状态 / 显示"分析即将开始" |
| A1 完成后 | WorkflowContent 展示品牌分析卡片（现有行为） |
| A4 进行中 | 如果有 fetchResults 产出，可提前展示（可选） |
| A5 完成后 | 自动切换到基线报告 Tab |

### 3.6 离开与回来

用户离开页面再回来时：
- WebSocket 重连后，后端回放缓存的 stage_result 事件
- StageResultCard 带 `isReplay` 标记（现有机制），不触发动画
- MiniProgress 恢复到当前实际进度
- 如果分析已完成，直接展示完成引导卡片

---

## 4. 基线报告完成引导

### 4.1 触发时机

A5 完成后，后端发送 `execution_complete` 事件。前端在 Chat 中渲染完成引导卡片。

### 4.2 完成引导卡片线框图

```
+--------------------------------------------------------------------+
|                                                                      |
|  +--- StageResultCard (A5 metrics_preview) ---+                      |
|  | # 基线分析                                              已完成   |
|  | BWVS: 42.0                                                        |
|  +---------------------------------------------+                    |
|                                                                      |
|  +----------------------------------------------------------------+  |
|  |  Specta AI                                                      |  |
|  |                                                                 |  |
|  |  基线分析已完成！以下是「兰蔻」的关键发现：                         |  |
|  |                                                                 |  |
|  |  +----------------------------------------------------------+   |  |
|  |  |           BWVS 基线得分                                    |   |  |
|  |  |                                                          |   |  |
|  |  |              42 / 100                                     |   |  |
|  |  |          ============================----------          |   |  |
|  |  |                                                          |   |  |
|  |  |  . DeepSeek 表现最好，提及率 58%                          |   |  |
|  |  |  . Kimi 提及率偏低，仅 22%                                |   |  |
|  |  |  . 竞品「雅诗兰黛」在多数平台排名更高                      |   |  |
|  |  +----------------------------------------------------------+   |  |
|  |                                                                 |  |
|  |  接下来您可以：                                                   |  |
|  |                                                                 |  |
|  |  +----------------------------------------------------------+   |  |
|  |  | A  开始场景细化分析                            [推荐]     |   |  |
|  |  |    基于目标用户画像，深入分析特定使用场景下的品牌表现         |   |  |
|  |  +----------------------------------------------------------+   |  |
|  |                                                                 |  |
|  |  +----------------------------------------------------------+   |  |
|  |  | B  重新运行基线分析                                        |   |  |
|  |  |    使用最新数据重新评估品牌基线表现                          |   |  |
|  |  +----------------------------------------------------------+   |  |
|  |                                                                 |  |
|  |  +----------------------------------------------------------+   |  |
|  |  | C  直接提问                                                |   |  |
|  |  |    在输入框中输入您想了解的问题                              |   |  |
|  |  +----------------------------------------------------------+   |  |
|  |                                                                 |  |
|  +----------------------------------------------------------------+  |
|                                                                      |
+--------------------------------------------------------------------+
```

### 4.3 实现方案：Agent 消息 + GuidedOptions

完成引导卡片由两部分组成：

**Part 1 — BWVS 摘要**：作为 Agent 消息的 `content` 字段，使用 MarkdownContent 渲染。包含 BWVS 分数和 3 条关键发现。

**Part 2 — 下一步引导**：复用 `GuidedOptions` 组件（`src/components/chat/Message/GuidedOptions.tsx`），通过 `inline_confirmation` 事件渲染为选项卡片。

**后端事件格式**：
```json
{
  "type": "inline_confirmation",
  "data": {
    "requestId": "baseline_complete_guide",
    "type": "action_choice",
    "message": "接下来您可以：",
    "options": [
      {
        "id": "start_scenario",
        "label": "开始场景细化分析",
        "description": "基于目标用户画像，深入分析特定使用场景下的品牌表现",
        "recommended": true
      },
      {
        "id": "rerun_baseline",
        "label": "重新运行基线分析",
        "description": "使用最新数据重新评估品牌基线表现"
      },
      {
        "id": "free_chat",
        "label": "直接提问",
        "description": "在输入框中输入您想了解的问题"
      }
    ],
    "allowTextInput": true
  }
}
```

### 4.4 BWVS 分数展示

BWVS 分数在完成消息中以 Markdown 格式嵌入（不需要新组件）：

```markdown
基线分析已完成！以下是「兰蔻」的关键发现：

**BWVS 基线得分：42 / 100**

- DeepSeek 表现最好，提及率 58%
- Kimi 提及率偏低，仅 22%
- 竞品「雅诗兰黛」在多数平台排名更高

> 完整报告已在右侧面板中展示。
```

同时，`StageResultCard` 的 `metrics_preview` 类型已经支持 BWVS 大号数字展示（现有组件，见 `StageResultCard.tsx:199-221`），所以分数也会在 StageResultCard 中呈现。

### 4.5 用户选择后的行为

| 用户选择 | 系统行为 |
|----------|----------|
| [开始场景细化] | Orchestrator 调用 A2 生成画像，Chat 中出现画像选择卡片 |
| [重新运行基线] | 触发重跑流程（见第 5 节） |
| [直接提问] | 输入框获焦，用户自由提问。Agent 可以基于基线数据回答 |

### 4.6 Canvas 自动展示

A5 完成后，后端通过 `output_ready` 事件推送基线报告到 Canvas。Canvas 自动：
1. 创建"基线报告" Tab（id: `{sessionId}_report_baseline`）
2. 切换到该 Tab 展示报告
3. CanvasHeader 显示标题"基线全景分析报告"

---

## 5. 重跑基线

### 5.1 触发方式

两种触发方式：

| 方式 | 入口 |
|------|------|
| 对话中选择 | 完成引导卡片中点击 [重新运行基线分析] |
| 自由输入 | 用户在输入框输入"重新分析"/"重跑基线"等 |

### 5.2 重跑确认交互

```
用户: "重新跑一次基线"
      |
      v
+----------------------------------------------------------------+
|  Specta AI                                                      |
|                                                                 |
|  将重新执行基线分析。新结果将替换当前基线数据，                      |
|  旧数据将保存为历史版本。确认继续？                                 |
|                                                                 |
|  [===确认重跑===]    [取消]                                      |
+----------------------------------------------------------------+
      |
      v (用户确认)
重跑 A3 → A4 → A5（跳过 A1，复用现有品牌信息）
      |
      v
新基线报告覆盖 Canvas，旧报告存入版本历史
```

### 5.3 确认卡片实现

复用 `ConfirmationCard` 组件（`src/components/chat/ConfirmationCard.tsx`），通过 `inline_confirmation` 事件：

```json
{
  "type": "inline_confirmation",
  "data": {
    "requestId": "rerun_baseline_confirm",
    "type": "step_confirmation",
    "message": "将重新执行基线分析。新结果将替换当前基线数据，旧数据将保存为历史版本。确认继续？",
    "stepName": "重跑基线",
    "options": [
      { "id": "confirm", "label": "确认重跑", "recommended": true },
      { "id": "cancel", "label": "取消" }
    ],
    "allowTextInput": false
  }
}
```

### 5.4 版本管理与 Issue #5 集成

重跑基线后，版本管理依赖 Issue #5 已实现的 CanvasHeader 版本选择器：

**数据流**：
```
A5 新报告 → output_ready 事件 (id: {sessionId}_report_baseline)
      |
      v
canvasStore.addContent() → 检测同 ID 已存在
      |
      v
旧 data 存入 versions[] → 新 data 覆盖当前 data
      |
      v
CanvasHeader 版本选择器自动显示 v1(旧) + v2(新，最新)
```

**版本选择器展示**：
```
+-----------------------------------------------+
|  基线全景分析报告                                |
|  +-----------------------------------+         |
|  | v2 (最新)  2/22 16:30  BWVS 45   v|         |
|  +-----------------------------------+         |
|                                                 |
|  下拉展开:                                       |
|  +-----------------------------------+         |
|  | * v2  2/22 16:30  BWVS 45  [最新]  |         |
|  |   v1  2/22 14:00  BWVS 42         |         |
|  |              [跳转到对话]           |         |
|  +-----------------------------------+         |
+-----------------------------------------------+
```

### 5.5 重跑 vs 首次的差异

| 维度 | 首次基线 | 重跑基线 |
|------|---------|---------|
| A1 | 执行 | 跳过（复用品牌信息） |
| 确认步骤 | 品牌信息确认 | 重跑确认 |
| StageResultCard 步骤 | 4 步（A1+A3+A4+A5） | 3 步（A3+A4+A5） |
| 报告输出 | 创建新 Tab | 覆盖现有 Tab + 版本历史 |
| 完成引导 | 展示完整引导（场景细化/重跑/提问） | 展示简化引导（对比上次 + 场景细化） |

### 5.6 重跑完成引导

重跑完成后的引导消息增加**与上一次的对比信息**：

```markdown
基线重跑完成！与上次对比：

**BWVS: 42.0 -> 45.2 (+3.2)**

- DeepSeek 提及率提升：58% -> 63%
- Kimi 提及率略有下降：22% -> 20%
- 新增竞品「赫莲娜」出现在 2 个问题中

> 您可以在右侧面板的版本选择器中查看历史版本对比。
```

此对比信息由后端 A5 在基线报告中计算 `delta_vs_previous` 字段，前端 Agent 消息直接渲染。

---

## 6. 基线 vs 场景报告在 Canvas 中的区分

### 6.1 Tab 分类策略

基线报告和场景报告使用**不同的固定 Tab ID**，在 Canvas 中独立展示：

| 报告类型 | Tab ID 规则 | Tab 标题 | 图标颜色 |
|----------|------------|---------|----------|
| 基线报告 | `{sessionId}_report_baseline` | 基线全景分析报告 | `--brand-primary` (Indigo) |
| 场景报告 | `{sessionId}_report_persona` | AI 可见性分析报告 | `--brand-primary` (Indigo) |
| 基线问题 | `{sessionId}_questionList_baseline` | 基线问题列表 | Sky |
| 场景问题 | `{sessionId}_questionList_persona` | 场景问题列表 | Sky |
| 抓取结果 | `{sessionId}_fetchResults` | 抓取结果 | Teal |

### 6.2 报告标题区分

CanvasHeader 中通过报告标题和副标题区分两种报告：

```
基线报告:
+--------------------------------------------------------------------+
|  [报告图标] 基线全景分析报告                                          |
|  全景分析 . 行业视角                                                 |
|  v2 (最新)  2/22 16:30                         [复制] [导出] [x]    |
+--------------------------------------------------------------------+

场景报告:
+--------------------------------------------------------------------+
|  [报告图标] AI 可见性分析报告                                         |
|  分析报告 . 25-35岁都市白领                                          |
|  v1 (最新)  2/22 18:00                         [复制] [导出] [x]    |
+--------------------------------------------------------------------+
```

### 6.3 报告内容差异

两种报告共用 `ReportContent.tsx` 组件渲染，但通过 `category` 字段区分内容：

| 报告 Tab | 基线报告 | 场景报告 |
|----------|---------|---------|
| 总览 | 行业基线 BWVS + 品牌行业定位 | 场景 BWVS + 基线对比 delta |
| 行业洞察 | 行业全景观察 | 场景特定洞察 |
| 平台分析 | 各平台基线表现 | 各平台场景表现 |
| 竞品对比 | 行业竞品格局 | 场景竞品对比 |
| 优化建议 | 行业级定位策略 | 场景级内容优化 |
| 风险提示 | 行业风险 | 场景风险 |

**场景报告新增**：在总览 Tab 中展示与基线的对比：

```
+--------------------------------------------------+
|  场景 BWVS: 51.2                                   |
|  vs 基线: 42.0 (+9.2)                              |
|                                                    |
|  该场景下品牌表现优于行业基线，                       |
|  25-35岁都市白领群体对品牌认知度较高。                |
+--------------------------------------------------+
```

### 6.4 CanvasContentType 扩展

现有的 `CanvasContentType` 不需要修改。通过在 `output_ready` 事件中传递 `category` 字段来区分：

```typescript
// output_ready 事件新增字段
{
  type: "output_ready",
  id: "{sessionId}_report_baseline",
  output_type: "report",            // 复用现有 type
  title: "基线全景分析报告",
  category: "baseline",             // 新增: "baseline" | "scenario"
  scenario_label: null,             // 基线无场景标签
  linked_message_id: "msg_xxx",
  data: { ... }
}
```

前端 `CanvasContent` 类型扩展：
```typescript
// 在 CanvasContent 联合类型中添加可选字段
{
  // ...existing fields
  category?: 'baseline' | 'scenario';  // 新增
  scenarioLabel?: string;               // 场景标签（仅 scenario 时有值）
}
```

### 6.5 版本选择器中的区分

当用户在版本选择器中浏览时，基线和场景报告的版本是独立管理的：
- 基线报告的版本选择器只展示基线版本（v1, v2, v3...）
- 场景报告的版本选择器可能展示不同画像的报告版本

版本选择器下拉项格式：

```
基线报告版本选择器:
+---------------------------------------+
| * v2  2/22 16:30  BWVS 45.2   [最新]  |
|   v1  2/22 14:00  BWVS 42.0           |
+---------------------------------------+

场景报告版本选择器:
+----------------------------------------------------+
| * 25-35岁都市白领  2/22 18:00  BWVS 51.2    [最新]  |
|   18-24岁学生群体  2/22 19:00  BWVS 35.8           |
+----------------------------------------------------+
```

**实现**：CanvasHeader 版本选择器已支持显示版本列表。场景报告的 `scenarioLabel` 可作为版本名称显示。

---

## 7. 组件复用与新建清单

### 7.1 可复用的现有组件

| 组件 | 位置 | 用于 | 复用方式 |
|------|------|------|----------|
| **ConfirmationBlock** | `chat/Message/ConfirmationBlock.tsx` | 品牌信息确认、重跑确认 | 直接复用，type 设为 `brand_info` / `step_confirmation` |
| **GuidedOptions** | `chat/Message/GuidedOptions.tsx` | 完成引导（场景细化/重跑/提问） | 直接复用，通过 `inline_confirmation` type=`action_choice` |
| **StageResultCard** | `chat/StageResultCard.tsx` | 基线各阶段结果展示 | 直接复用，resultType 已涵盖所需类型 |
| **MiniProgress** | `chat/MiniProgress.tsx` | 基线总进度 | 直接复用，步骤列表由事件驱动 |
| **CanvasHeader** | `canvas/CanvasHeader.tsx` | 版本选择器 + 对话跳转 | 直接复用（Issue #5 已实现） |
| **MarkdownContent** | `chat/Message/MarkdownContent.tsx` | BWVS 摘要文本渲染 | 直接复用 |
| **OutputCard** | `chat/Message/OutputCard.tsx` | 报告完成时的 Canvas 入口卡片 | 直接复用 |

### 7.2 需要修改的现有组件

| 组件 | 修改内容 | 改动量 |
|------|----------|--------|
| **ReportContent** | 1. 识别 `category` 字段，基线/场景展示不同标题 <br> 2. 场景报告总览 Tab 增加基线对比区域 | 小 (~30 行) |
| **CanvasHeader** | 场景报告的版本选择器展示 `scenarioLabel` 作为版本名称 | 极小 (~10 行) |

### 7.3 需要新建的组件

**结论：Phase 1 不需要新建任何前端组件。**

所有交互均可通过现有组件实现：
- 品牌确认 → ConfirmationBlock
- 进度展示 → StageResultCard + MiniProgress
- 完成引导 → GuidedOptions
- 重跑确认 → ConfirmationBlock
- 版本管理 → CanvasHeader 版本选择器

**Phase 2 可选新建**（视用户反馈）：
| 组件 | 用途 | 触发条件 |
|------|------|----------|
| `BrandConfirmCard` | 品牌信息结构化展示（替代 Markdown 表格） | 如果用户反馈信息展示不够清晰 |
| `BwvsScoreCard` | BWVS 分数可视化组件（环形图 + 得分段） | 如果用户希望更直观的分数展示 |
| `BaselineDeltaCard` | 基线对比卡片（新旧 BWVS 对比 + 变化趋势） | 重跑基线时，增强对比体验 |

---

## 8. 数据流与事件设计

### 8.1 完整事件序列

基线分析的完整 WebSocket 事件序列：

```
1. 用户确认品牌信息
   <- inline_confirmation (type: brand_info)
   -> user_confirmation (optionId: "confirm")

2. 基线分析启动
   <- plan_update (steps: [a1, a3, a4, a5])
   <- thought_delta (Orchestrator 思考)
   <- reply_delta ("正在执行全景基线分析...")

3. A1 品牌识别 (如果首次)
   <- action_log (agent_call: A1)
   <- stage_result (resultType: brand_profile)
   <- output_ready (type: workflow, id: {sessionId}_workflow)

4. A3 基线问题生成
   <- action_log (agent_call: A3, mode: baseline_dynamic)
   <- stage_result (resultType: questions)
   <- output_ready (type: questionList, id: {sessionId}_questionList_baseline)

5. A4 平台抓取
   <- action_log (agent_call: A4)
   <- stage_result (resultType: platform_status, 多次更新)
   <- output_ready (type: fetchResults, id: {sessionId}_fetchResults)

6. A5 数据分析
   <- action_log (agent_call: A5, mode: baseline)
   <- stage_result (resultType: metrics_preview)
   <- output_ready (type: report, id: {sessionId}_report_baseline, category: baseline)

7. 完成引导
   <- reply_delta ("基线分析已完成！...")
   <- inline_confirmation (type: action_choice, 三个选项)
   <- execution_complete
```

### 8.2 后端 output_ready 事件扩展

```python
# events.py - save_and_send_artifact() 扩展
await send_ws_event(session_id, "output_ready", {
    "id": f"{session_id}_report_baseline",
    "type": "report",
    "title": "基线全景分析报告",
    "category": "baseline",           # 新增
    "scenario_label": None,           # 新增（基线时为 None）
    "linked_message_id": message_id,
    "timestamp": datetime.now().isoformat(),
    "data": report_data,
})
```

### 8.3 前端 Store 处理

`canvasStore.ts` 的 `addContent()` 方法已支持同 ID 覆盖+版本历史（Issue #5）。需要新增处理 `category` 和 `scenarioLabel` 字段：

```typescript
// canvasStore.ts addContent() 扩展
addContent: (content) => {
  // ...existing version merge logic

  // 新增: 保存 category 和 scenarioLabel
  if (content.category) {
    newContent.category = content.category;
  }
  if (content.scenarioLabel) {
    newContent.scenarioLabel = content.scenarioLabel;
  }
}
```

---

## 附录 A: 关键设计决策记录

| 决策 | 选项 | 选择 | 理由 |
|------|------|------|------|
| 品牌确认方式 | 新组件 vs 复用 ConfirmationBlock | 复用 ConfirmationBlock | 零新组件，快速实现，可后续升级 |
| 完成引导方式 | 弹窗 vs Chat 内卡片 | Chat 内卡片（GuidedOptions） | Chat-first 原则 |
| BWVS 展示 | 新图表组件 vs Markdown + StageResultCard | Markdown + StageResultCard | StageResultCard 已支持 metrics_preview |
| 基线/场景 Tab 区分 | 新 CanvasContentType vs category 字段 | category 字段 | 不改变现有类型体系，影响最小 |
| 重跑确认 | 自动重跑 vs 二次确认 | 二次确认 | 防误操作，重跑耗时 15-20 分钟 |

## 附录 B: 与其他 Issue 的依赖关系

| Issue | 依赖方向 | 具体依赖点 |
|-------|----------|-----------|
| Issue #3 报告质量 | Issue #4 依赖 #3 | 基线报告复用 ReportContent 的重构结果 |
| Issue #5 版本合并 | Issue #4 依赖 #5 | 重跑基线需要版本选择器和同 ID 覆盖机制 |
| Issue #6 浅色模式 | 双向 | 所有组件使用 CSS 变量，自动适配深浅模式 |

## 附录 C: 验收标准（UX 视角）

- [ ] 品牌信息确认卡片在 Chat 中正确展示，包含品牌名称、行业、竞品等信息
- [ ] 点击 [确认] 后按钮变为已选择态，基线分析自动启动
- [ ] 点击 [修改信息] 后输入框获焦，用户可输入修改内容
- [ ] 基线分析过程中，StageResultCard 逐步出现（品牌识别 → 问题生成 → 平台抓取 → 数据分析）
- [ ] MiniProgress 显示总进度百分比和预估剩余时间
- [ ] 基线完成后展示 BWVS 分数和 3 条关键发现
- [ ] 完成引导提供 3 个下一步选项（场景细化/重跑/提问），场景细化为推荐选项
- [ ] 重跑基线有二次确认，确认后跳过 A1
- [ ] 重跑完成后展示与上次的对比信息
- [ ] Canvas 中基线报告和场景报告有独立 Tab，不互相覆盖
- [ ] CanvasHeader 版本选择器正确管理基线报告的多个版本
- [ ] 用户离开页面再回来后，进度状态正确恢复
