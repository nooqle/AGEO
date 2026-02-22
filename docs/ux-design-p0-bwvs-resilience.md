# UX 设计方案: P0 韧性模型 + BWVS v2 展示

> **文档状态**: 设计提案，待团队评审
> **设计负责人**: Don Norman (UX Lead)
> **日期**: 2026-02-20
> **关联**: `D:\AGEO\docs\reform-plan.md` P0 + P2-3
> **涉及文件**:
> - `D:\AGEO\frontend\src\components\dashboard\KPICard.tsx`
> - `D:\AGEO\frontend\src\components\canvas\contents\ReportContent.tsx`
> - `D:\AGEO\frontend\src\components\chat\Message\SystemMessage.tsx`
> - `D:\AGEO\frontend\src\components\chat\Message\AgentMessage.tsx`
> - `D:\AGEO\frontend\src\app\globals.css`

---

## 设计原则（贯穿所有场景）

1. **反馈即信任**: 系统降级时，用户不应该猜测发生了什么。诚实的反馈比沉默更能建立信任。
2. **非模态、不打断**: 降级通知嵌入消息流，不弹窗、不阻塞，用户可以继续操作。
3. **信息层级分明**: 总分最突出，分项次之，权重说明最末。用户扫一眼就能抓住重点。
4. **认知负荷最小化**: 四个维度用颜色+进度条传达好/中/差，不需要用户记忆分值区间含义。
5. **与现有设计系统一致**: 使用 globals.css 中已定义的变量，保持深色主题统一性。

---

## 场景 A: Dashboard KPICard BWVS 四维 Tooltip

### 用户场景

用户在 Dashboard 看到 BWVS 总分（如 35.4），心里想："这个分数由什么组成？哪方面好哪方面差？" 于是把鼠标悬停在 KPICard 右上角的 "?" 图标上。

### 设计决策

当前 KPICard 的 tooltip 只显示纯文本说明。为了展示四维分项，需要将 tooltip 升级为**结构化 Rich Tooltip**。这不是新组件，而是对现有 tooltip 渲染逻辑的扩展：当传入结构化数据时，渲染分项布局；否则仍渲染纯文本。

### ASCII 布局

```
+------------------------------------------+
|  BWVS 品牌可见度指数            35.4/100  |
|  ----------------------------------------|
|                                           |
|  提及率 (40%)                             |
|  [==============                ] 42.0    |
|                                           |
|  情感倾向 (25%)                           |
|  [========                      ] 28.5    |
|                                           |
|  引用质量 (20%)                           |
|  [==========                    ] 35.0    |
|                                           |
|  平台覆盖 (15%)                           |
|  [============                  ] 40.0    |
|                                           |
|  ----------------------------------------|
|  综合加权得分 | 数据来源: 最近一次分析      |
+------------------------------------------+
```

**未配置品牌域名时（无引用质量数据）:**

```
+------------------------------------------+
|  BWVS 品牌可见度指数            32.1/100  |
|  ----------------------------------------|
|                                           |
|  提及率 (40%)                             |
|  [==============                ] 42.0    |
|                                           |
|  情感倾向 (25%)                           |
|  [========                      ] 28.5    |
|                                           |
|  引用质量 (20%)                           |
|  [                              ]  --     |
|  (i) 配置品牌域名后可计算此项              |
|                                           |
|  平台覆盖 (15%)                           |
|  [============                  ] 40.0    |
|                                           |
|  ----------------------------------------|
|  综合加权得分 | 引用质量未纳入计算          |
+------------------------------------------+
```

### 视觉规格

| 元素 | 规格 |
|------|------|
| **Tooltip 容器** | `background: #1A1A1A` (var(--bg-secondary)), `border: 1px solid #333333` (var(--border-default)), `border-radius: 12px`, `padding: 16px`, `min-width: 300px`, `max-width: 340px`, `box-shadow: 0 8px 24px rgba(0,0,0,0.5)` |
| **标题行** | 左侧: "BWVS 品牌可见度指数" -- `font-size: 12px`, `color: #A3A3A3` (var(--text-secondary)); 右侧: 总分 -- `font-size: 14px`, `font-weight: 700`, `color: #FFFFFF` (var(--text-primary)) |
| **分隔线** | `border-top: 1px solid #333333` (var(--border-default)), `margin: 8px 0` |
| **维度名称 + 权重** | `font-size: 11px`, `color: #8A8A8A` (var(--text-tertiary)), 权重用括号包裹 |
| **进度条轨道** | `height: 6px`, `background: #262626` (var(--bg-tertiary)), `border-radius: 3px` |
| **进度条填充** | `border-radius: 3px`, `transition: width 300ms ease-out` |
| **进度条颜色** | 得分 >= 60: `#22C55E` (var(--success) emerald); 30-59: `#F59E0B` (var(--warning) amber); < 30: `#EF4444` (var(--error) red) |
| **分值数字** | `font-size: 12px`, `font-weight: 600`, `color: #E5E5E5`, 右对齐 |
| **缺失项提示** | `font-size: 10px`, `color: #6B6B6B` (var(--text-muted)), 前缀 (i) 图标用 `RiInformationLine` 12px |
| **底部注释** | `font-size: 10px`, `color: #525252` (var(--text-disabled)) |

### 交互说明

1. **触发方式**: `onMouseEnter` / `onMouseLeave`，与现有 KPICard tooltip 机制一致。
2. **定位**: tooltip 出现在 "?" 图标正上方居中，底部箭头指向图标。若空间不足则自动翻转到下方。
3. **出现动画**: `opacity 0 -> 1`, `translateY(4px) -> 0`, `duration: 150ms`，与 `var(--transition-fast)` 一致。
4. **指针事件**: `pointer-events: none`（与现有 tooltip 一致），用户无法在 tooltip 内交互。
5. **数据来源**: 需新增 `bwvsBreakdown` prop（可选）传入 KPICard，格式:

```typescript
interface BwvsBreakdown {
  mentionRate: { score: number; weight: number };     // 提及率
  sentimentBias: { score: number; weight: number };   // 情感倾向
  citationQuality: { score: number | null; weight: number }; // 引用质量 (null=未配置)
  platformCoverage: { score: number; weight: number }; // 平台覆盖
}
```

### 四维说明

| 维度 | 含义 | 权重 | 数据来源 |
|------|------|------|---------|
| 提及率 | 品牌在 AI 回答中被提及的比例 | 40% | A4 fetch_results 计算 |
| 情感倾向 | AI 回答中品牌相关内容的情感正面程度 | 25% | A5 sentiment_distribution |
| 引用质量 | AI 回答是否引用/链接了品牌官方内容 | 20% | A4 citations 分析（需品牌域名） |
| 平台覆盖 | 品牌被提及覆盖了多少个 AI 平台 | 15% | A4 platform_breakdown |

---

## 场景 B: A5 报告中的 BWVS Breakdown 区块

### 用户场景

用户在 Canvas 面板查看 A5 生成的分析报告。在"总览"tab 中，当前只看到一个大数字 BWVS 总分和一条进度条。用户想深入了解：每个维度表现如何？如果有竞品，能不能对比？

### 设计决策

- **选择水平条形图（Horizontal Bar）而非雷达图**: 理由如下：
  - 雷达图在只有 4 个维度时，面积感知容易产生误导（认知科学研究已证实）
  - 雷达图在深色主题上可读性差，网格线和标签容易看不清
  - 水平条形图：数值精确可读，颜色编码直观传达好/中/差，与 KPICard tooltip 一致
  - 用 Recharts 的 BarChart 组件即可实现，已在项目依赖中

- **视觉层级**: 总分最大最突出 -> 四个分项条形图 -> 底部权重说明
- **竞品对比**: 如果有竞品 BWVS 数据，在同一维度的条形图上叠加竞品的半透明条

### ASCII 布局 -- 基本模式（无竞品）

```
+-------------------------------------------------------------------+
|  品牌可见度分析报告                                                  |
|  提及率: 42.0%  (BWVS指数: 35.4)                                   |
+-------------------------------------------------------------------+

+-------------------------------------------------------------------+
|                    BWVS 指数构成                                    |
|  -----------------------------------------------------------------|
|                                                                    |
|     35.4       综合评分                                             |
|    [大字体]    ==========[进度条]================                   |
|               需改进                                                |
|                                                                    |
|  -----------------------------------------------------------------|
|                                                                    |
|   提及率         [==============              ] 42.0  (权重 40%)   |
|                                                                    |
|   情感倾向       [========                    ] 28.5  (权重 25%)   |
|                                                                    |
|   引用质量       [==========                  ] 35.0  (权重 20%)   |
|                                                                    |
|   平台覆盖       [============                ] 40.0  (权重 15%)   |
|                                                                    |
|  -----------------------------------------------------------------|
|   BWVS = 42.0x0.4 + 28.5x0.25 + 35.0x0.2 + 40.0x0.15 = 35.4    |
+-------------------------------------------------------------------+
```

### ASCII 布局 -- 竞品对比模式

```
+-------------------------------------------------------------------+
|                    BWVS 指数构成                                    |
|  -----------------------------------------------------------------|
|                                                                    |
|     35.4       综合评分           vs  竞品均值  48.2               |
|    [大字体]    ==========[半透明叠加]==========                     |
|               需改进                  良好                          |
|                                                                    |
|  -----------------------------------------------------------------|
|                                   [我的品牌]  [竞品均值]            |
|                                                                    |
|   提及率         [==============   |=====     ] 42.0 vs 52.3      |
|                                                                    |
|   情感倾向       [========         |=======   ] 28.5 vs 45.1      |
|                                                                    |
|   引用质量       [==========       |===       ] 35.0 vs 38.0      |
|                                                                    |
|   平台覆盖       [============     |=====     ] 40.0 vs 60.0      |
|                                                                    |
|  -----------------------------------------------------------------|
|   (i) 竞品均值基于已配置竞品的平均数据计算                           |
+-------------------------------------------------------------------+
```

### 视觉规格

| 元素 | 规格 |
|------|------|
| **区块容器** | 与现有 Score Card 一致: `p-5 bg-[#1A1A1A] border border-[#262626] rounded-xl` |
| **区块标题** | "BWVS 指数构成" -- `font-size: 14px`, `font-weight: 600`, `color: #E5E5E5` |
| **总分数字** | `font-size: 36px` (text-4xl), `font-weight: 700`, 颜色跟随评级: >= 70 emerald-400 / >= 40 amber-400 / < 40 red-400 |
| **评级标签** | "优秀/良好/需改进" -- `font-size: 12px`, `color: #A3A3A3` |
| **维度标签** | `font-size: 13px`, `font-weight: 500`, `color: #E5E5E5`, 固定宽度 `w-20` 左对齐 |
| **分项进度条轨道** | `height: 10px`, `background: #262626`, `border-radius: 5px`, `flex: 1` |
| **分项进度条填充（品牌）** | 颜色同场景 A 规则 (>= 60 emerald / 30-59 amber / < 30 red), `border-radius: 5px` |
| **分项进度条填充（竞品叠加）** | `opacity: 0.35`, `border: 1px dashed` 同色系, 叠加在品牌条上方 |
| **分值数字** | `font-size: 13px`, `font-weight: 600`, `color: #E5E5E5`, 右侧固定宽度 `w-24` |
| **权重标注** | `font-size: 11px`, `color: #6B6B6B` (var(--text-muted)) |
| **公式行** | `font-size: 11px`, `font-family: monospace`, `color: #525252` (var(--text-disabled)), `border-top: 1px solid #262626`, `padding-top: 12px` |

### 交互说明

1. **无需额外交互**: 此区块为静态展示，随 ReportContent "总览" tab 直接渲染。
2. **位置**: 插入到现有 Score Card（总分 + 进度条）的下方，Metrics Grid 的上方。
3. **竞品模式自动切换**: 如果 `data.competitors` 存在且至少有 1 个竞品有 BWVS 数据，自动显示对比模式。否则显示基本模式。
4. **动画**: 进度条使用 CSS transition `width 500ms ease-out`，页面加载时从 0 增长到目标值，给用户"计算完成"的反馈感。

### 数据结构扩展

需要 A5 在 artifact data 中新增 `bwvs_breakdown` 字段:

```typescript
interface BwvsBreakdown {
  total: number;          // 综合得分 0-100
  dimensions: {
    mention_rate: number;       // 0-100
    sentiment_bias: number;     // 0-100
    citation_quality: number | null;  // 0-100 或 null
    platform_coverage: number;  // 0-100
  };
  weights: {
    mention_rate: number;       // 0.4
    sentiment_bias: number;     // 0.25
    citation_quality: number;   // 0.2
    platform_coverage: number;  // 0.15
  };
  competitor_avg?: {       // 可选: 竞品均值
    total: number;
    dimensions: {
      mention_rate: number;
      sentiment_bias: number;
      citation_quality: number | null;
      platform_coverage: number;
    };
  };
}
```

---

## 场景 C: A2 降级通知（全景模式 Fallback）

### 用户场景

用户输入"帮我分析一下小米的品牌可见度"。系统执行 A1 -> A2。A2 用户画像生成失败（JSON 截断等原因），系统自动降级为"全景模式"（不按用户画像细分，直接用通用问题模板），然后继续 A3 -> A4 -> A5。

用户需要知道：(1) 发生了什么，(2) 对结果有什么影响，(3) 是否需要做什么。

### 设计决策

- **嵌入消息流**（不是顶部 banner）: 理由:
  - 降级发生在流水线执行过程中，用户的注意力在消息流里
  - 顶部 banner 容易被忽略，且会与其他全局通知冲突
  - 嵌入消息流保持了时间线叙事的连贯性："系统做了什么 -> 遇到了什么问题 -> 怎么处理的"

- **通知类型**: Warning（琥珀色），不是 Error（红色）。因为系统已经自愈，分析会继续进行。

- **不需要用户操作**: 这是纯信息性通知。用户无需点击任何按钮。分析自动继续。

### ASCII 布局

```
    [Agent 消息: "正在生成用户画像..."]
    [ActionLog: A2 用户画像生成]

    +-- 系统通知（嵌入消息流）-----------------------------------------+
    |                                                                    |
    |  /!\  用户画像生成未完成，已切换为全景分析模式                       |
    |                                                                    |
    |  用户画像数据生成超时。系统已自动切换为全景分析模式，                 |
    |  将使用通用问题模板覆盖所有常见搜索场景。                            |
    |                                                                    |
    |  对结果的影响:                                                      |
    |  分析结果覆盖面更广，但不会按细分用户群体区分。                       |
    |  您可以在分析完成后输入"重新生成画像"来补充此步骤。                   |
    |                                                                    |
    +-------------------------------------------------------------------+

    [ActionLog: A3 问题生成（全景模式）]
```

### 视觉规格

| 元素 | 规格 |
|------|------|
| **通知容器** | `background: rgba(245, 158, 11, 0.08)` (amber 半透明), `border: 1px solid rgba(245, 158, 11, 0.2)`, `border-radius: 12px`, `padding: 12px 16px`, `margin: 8px 0` |
| **图标** | `RiAlertLine` (Remix Icon), `width: 16px`, `height: 16px`, `color: #F59E0B` (var(--warning)), 左上角对齐标题 |
| **标题** | `font-size: 13px`, `font-weight: 600`, `color: #FCD34D` (amber-300), 与图标同行 |
| **正文** | `font-size: 12px`, `color: #D4D4D4`, `line-height: 1.6`, `margin-top: 6px` |
| **"对结果的影响"小标题** | `font-size: 11px`, `font-weight: 600`, `color: #A3A3A3`, `margin-top: 8px` |
| **影响说明文字** | `font-size: 12px`, `color: #A3A3A3`, `line-height: 1.5` |
| **入场动画** | `animate-fade-in` (已定义在 globals.css), `duration: 300ms` |

### 文案设计

**标题**: "用户画像生成未完成，已切换为全景分析模式"

**正文**:
> 用户画像数据生成超时。系统已自动切换为全景分析模式，将使用通用问题模板覆盖所有常见搜索场景。

**影响说明**:
> 分析结果覆盖面更广，但不会按细分用户群体区分。您可以在分析完成后输入"重新生成画像"来补充此步骤。

### 实现方式

通过 WebSocket `degradation_notice` 事件（新事件类型）从后端推送，前端在 AgentMessage 的消息流中渲染为新的 `DegradationNotice` 子组件。

```typescript
// 新增 WebSocket 事件
interface DegradationNoticeEvent {
  type: 'degradation_notice';
  data: {
    agent: string;           // "A2"
    title: string;           // 标题
    description: string;     // 正文
    impact: string;          // 影响说明
    level: 'warning' | 'info'; // warning=琥珀色, info=蓝色
  };
}
```

---

## 场景 D: A4 部分平台失败通知

### 用户场景

A4 数据抓取阶段，系统同时向 4 个平台发起请求。DeepSeek 和豆包成功返回，但 Kimi 超时、混元 API 报错。系统使用已成功的 2 个平台数据继续分析。

用户需要知道：哪些平台成功了，哪些失败了，最终用了多少平台的数据。

### 设计决策

- **嵌入消息流**，紧跟在 A4 ActionLog 之后。
- **Level**: Info（蓝色）而非 Warning，因为部分平台失败是常见且可接受的。只要 >= 2 个平台成功，结果就有参考价值。
- **关键信息前置**: "3/4 平台数据获取成功"放在第一行，一目了然。

### ASCII 布局

```
    [ActionLog: A4 数据抓取]

    +-- 平台状态通知 ------------------------------------------------+
    |                                                                  |
    |  (i)  3/4 平台数据获取成功                                       |
    |                                                                  |
    |  [v] DeepSeek    成功  12/12 问题已获取                          |
    |  [v] 豆包        成功  12/12 问题已获取                          |
    |  [v] 混元        成功  10/12 问题已获取                          |
    |  [x] Kimi        失败  连接超时                                  |
    |                                                                  |
    |  已使用 3 个平台的数据继续分析。                                   |
    |                                                                  |
    +------------------------------------------------------------------+
```

**所有平台成功时（不显示此通知，只在 ActionLog 中标记完成）。**

**仅 1 个平台成功时（Warning 级别）:**

```
    +-- 平台状态通知 ------------------------------------------------+
    |                                                                  |
    |  /!\  仅 1/4 平台数据获取成功                                    |
    |                                                                  |
    |  [v] 豆包        成功  12/12 问题已获取                          |
    |  [x] DeepSeek    失败  API 限流                                  |
    |  [x] Kimi        失败  连接超时                                  |
    |  [x] 混元        失败  服务暂不可用                               |
    |                                                                  |
    |  分析结果基于单一平台，覆盖面有限。                                |
    |  建议稍后重试以获取更全面的数据。                                   |
    |                                                                  |
    +------------------------------------------------------------------+
```

### 视觉规格

| 元素 | 规格 |
|------|------|
| **容器（>= 2 平台成功）** | `background: rgba(59, 130, 246, 0.06)` (blue 半透明), `border: 1px solid rgba(59, 130, 246, 0.15)`, `border-radius: 12px`, `padding: 12px 16px` |
| **容器（仅 1 平台成功）** | `background: rgba(245, 158, 11, 0.08)` (amber 半透明), `border: 1px solid rgba(245, 158, 11, 0.2)`, `border-radius: 12px`, `padding: 12px 16px` |
| **容器（0 平台成功 -- 全失败）** | `background: rgba(239, 68, 68, 0.08)` (red 半透明), `border: 1px solid rgba(239, 68, 68, 0.2)`, `border-radius: 12px`, `padding: 12px 16px` |
| **标题图标（>= 2 成功）** | `RiInformationLine`, `color: #3B82F6` (var(--info)) |
| **标题图标（1 成功）** | `RiAlertLine`, `color: #F59E0B` (var(--warning)) |
| **标题图标（0 成功）** | `RiErrorWarningLine`, `color: #EF4444` (var(--error)) |
| **标题文字** | `font-size: 13px`, `font-weight: 600`, 颜色跟随级别 |
| **平台行** | 网格布局: `grid-template-columns: 20px 80px 48px 1fr`, 行高 `28px` |
| **成功图标** | `RiCheckLine`, `width: 14px`, `color: #22C55E` (var(--success)) |
| **失败图标** | `RiCloseLine`, `width: 14px`, `color: #EF4444` (var(--error)) |
| **平台名称** | `font-size: 12px`, `color: #E5E5E5` |
| **状态标签** | 成功: `font-size: 11px`, `color: #22C55E`; 失败: `font-size: 11px`, `color: #EF4444` |
| **详情文字** | `font-size: 11px`, `color: #8A8A8A` |
| **底部说明** | `font-size: 12px`, `color: #A3A3A3`, `border-top: 1px solid` 对应色系 `0.1 opacity`, `padding-top: 8px`, `margin-top: 8px` |

### 交互说明

1. **触发条件**: 仅当至少 1 个平台失败时才显示此通知。所有平台成功时不显示。
2. **展示时机**: 在 A4 所有平台请求完成后统一展示，而非每个平台失败时逐条展示（避免信息轰炸）。
3. **无操作按钮**: 纯信息展示，系统已自动处理。
4. **折叠**: 如果平台数 > 4（未来扩展），默认只展示标题行（如"3/6 平台成功"），点击展开查看详情。当前 4 平台固定全展开。

### 数据结构

```typescript
interface PlatformStatusEvent {
  type: 'platform_status';
  data: {
    total: number;
    succeeded: number;
    platforms: Array<{
      name: string;              // "DeepSeek", "Kimi", "豆包", "混元"
      status: 'success' | 'failed' | 'skipped'; // skipped = 被熔断跳过
      questionsTotal: number;    // 总问题数
      questionsCompleted: number; // 成功获取的问题数
      errorReason?: string;      // 失败原因
    }>;
    message: string;             // 底部说明文字
  };
}
```

---

## 场景 E: A4 熔断器生效通知

### 用户场景

Kimi 平台在过去 10 分钟内连续 3 次请求超时，触发了熔断器。系统决定跳过 Kimi，不再尝试。用户看到平台状态通知中 Kimi 被标记为"已跳过"。

### 设计决策

熔断器跳过是场景 D 平台状态通知的一个子状态。不需要单独的 UI 组件，而是在平台状态行中体现：

- 状态从 "失败" 变为 "已跳过（熔断保护）"
- 用不同的图标和颜色区分 "主动跳过" vs "请求失败"

### ASCII 布局（集成在场景 D 的通知中）

```
    +-- 平台状态通知 ------------------------------------------------+
    |                                                                  |
    |  (i)  2/4 平台数据获取成功                                       |
    |                                                                  |
    |  [v] DeepSeek    成功    12/12 问题已获取                        |
    |  [v] 豆包        成功    12/12 问题已获取                        |
    |  [-] Kimi        已跳过  近期多次超时，暂时熔断保护               |
    |  [x] 混元        失败    API 限流                                |
    |                                                                  |
    |  已使用 2 个平台的数据继续分析。                                   |
    |  Kimi 平台将在 10 分钟后自动恢复尝试。                             |
    |                                                                  |
    +------------------------------------------------------------------+
```

### 视觉规格（增量，基于场景 D）

| 元素 | 规格 |
|------|------|
| **跳过图标** | `RiSkipForwardLine` 或 `RiShieldLine`, `width: 14px`, `color: #8A8A8A` (var(--text-tertiary)) |
| **"已跳过"标签** | `font-size: 11px`, `color: #8A8A8A` (var(--text-tertiary)), 不用红色（因为这是主动保护，不是错误） |
| **跳过原因** | `font-size: 11px`, `color: #6B6B6B` (var(--text-muted)), 措辞强调"保护"而非"错误" |
| **恢复时间提示** | 在底部说明中追加: "X 平台将在 Y 分钟后自动恢复尝试。" -- `color: #8A8A8A` |

### 文案设计原则

熔断器是为了保护系统稳定性。文案应该传达"这是一个聪明的决定"，而不是"系统出了问题"：

- 用 "已跳过" 而非 "已熔断"（用户不需要知道技术术语）
- 用 "近期多次超时，暂时熔断保护" 而非 "CircuitBreaker OPEN"
- 用 "将在 X 分钟后自动恢复尝试" 给用户确定性预期

---

## 组件实现清单

### 新增组件

| 组件 | 文件路径 | 职责 |
|------|---------|------|
| `BwvsBreakdownTooltip` | `frontend/src/components/dashboard/BwvsBreakdownTooltip.tsx` | KPICard BWVS 四维 tooltip（场景 A） |
| `BwvsBreakdownSection` | `frontend/src/components/canvas/contents/BwvsBreakdownSection.tsx` | ReportContent 中的 BWVS 分项区块（场景 B） |
| `DegradationNotice` | `frontend/src/components/chat/Message/DegradationNotice.tsx` | 降级/平台状态通知（场景 C/D/E 统一组件） |

### 修改组件

| 组件 | 修改内容 |
|------|---------|
| `KPICard.tsx` | 新增 `bwvsBreakdown` 可选 prop；tooltip 渲染逻辑分支：纯文本 vs 结构化 |
| `ReportContent.tsx` | 在 overview tab 的 Score Card 下方插入 `BwvsBreakdownSection` |
| `AgentMessage.tsx` | 在 ActionLog 之后、主内容之前，渲染 `DegradationNotice`（如有） |
| Message types (`types/message.ts`) | 新增 `degradationNotices` 字段到 Message 类型 |

### 后端事件

| 事件类型 | 触发场景 | 数据 |
|---------|---------|------|
| `degradation_notice` | A2 降级时 | agent, title, description, impact, level |
| `platform_status` | A4 完成时 | total, succeeded, platforms[], message |

---

## 认知负荷分析

### 场景 A (Tooltip)

- **信息量**: 4 维度 x (名称 + 分值 + 进度条 + 权重) = 16 个信息单元
- **分组**: 进度条颜色把 16 个单元压缩为 4 个"好/中/差"的感知分组，符合 4 < 7+/-2 的工作记忆限制
- **扫视路径**: 标题(总分) -> 逐行扫视进度条颜色(快速判断好坏) -> 如需要再看具体分值
- **风险**: tooltip 信息量比一般 tooltip 大。通过 300px 固定宽度和清晰的视觉层级缓解。

### 场景 C/D/E (降级通知)

- **信息量**: 标题(1句) + 正文(1-2句) + 影响(1-2句) = 4-5 句话
- **扫视路径**: 图标颜色(严重程度) -> 标题(发生了什么) -> 如有兴趣再看正文
- **风险**: 用户可能完全忽略通知。但这是可接受的 -- 系统已自愈，用户不看也不影响后续操作。

---

## 可访问性考虑

1. **颜色不是唯一编码**: 进度条除了颜色，分值数字也可传达好/中/差。色盲用户可依赖数字。
2. **文字对比度**: 所有文字在深色背景上的对比度 >= 4.5:1 (WCAG AA)。
   - `#E5E5E5` on `#1A1A1A` = 11.6:1 (通过)
   - `#A3A3A3` on `#1A1A1A` = 6.3:1 (通过)
   - `#8A8A8A` on `#1A1A1A` = 4.5:1 (通过)
3. **键盘可达**: KPICard 的 "?" 图标已有 `cursor-help`，应确保 `tabIndex=0` 可聚焦，`onFocus` 也能触发 tooltip。
4. **ARIA**: tooltip 添加 `role="tooltip"`, `aria-describedby` 关联到触发元素。

---

## 设计验证清单

- [ ] 新用户第一次看到 BWVS tooltip，不需要说明就能理解四个维度的含义？
- [ ] 色盲用户仅通过数字（不看颜色），能判断哪个维度好、哪个差？
- [ ] 降级通知在消息流中是否过于醒目（抢了主内容的视觉焦点）？通过降低不透明度和小字体缓解。
- [ ] 平台状态通知在所有 4 平台成功时不显示 -- 减少"噪音"。
- [ ] 降级通知文案是否让用户焦虑？用"已自动切换"、"保护"等正向措辞。
- [ ] tooltip 在窄屏（< 1024px）下是否溢出？需要设置 `max-width` 和边界检测。
- [ ] 竞品对比条形图在竞品数据为空时是否优雅降级为基本模式？
