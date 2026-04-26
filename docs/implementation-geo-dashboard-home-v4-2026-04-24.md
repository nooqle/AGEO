# GEO Dashboard 首页改版开发拆分

日期：2026-04-24

关联文档：

- `docs/prd-geo-dashboard-emotion-redesign-2026-04-23.md`
- `docs/prototype-geo-dashboard-emotion-redesign-2026-04-23-v4.html`
- `docs/state-geo-dashboard-home-v4-2026-04-24.md`

## 1. 开发目标

在不牺牲现有 Dashboard 品牌管理能力的前提下，替换“最近一轮分析”模块的信息架构和数据 contract，让首页同时具备：

- 多品牌监测入口：沿用当前品牌卡片完成品牌切换、进入分析、设置监测、新建品牌、管理全部。
- 单品牌最近报告摘要：当前选中品牌下展示最近一轮分析报告。
- 情绪与问题诊断：展示正负词云、平台诊断、高风险问题、优势场景。
- 提及率排行：展示前十品牌提及率排名，不展示提及份额，不做首位提及率。
- 来源结构：保留官网转化和信源结构判断。

## 2. 当前代码边界

### 2.1 需要保留的首页能力

现有能力主要在以下文件中：

- `frontend/src/components/dashboard/DashboardPage.tsx`
- `frontend/src/components/dashboard/DashboardHomeBoards.tsx`
- `frontend/src/types/dashboard.ts`
- `frontend/src/adapters/dashboardHome.ts`
- `aeo-platform/backend/app/api/v1/analytics.py`
- `aeo-platform/backend/app/services/analytics_service.py`
- `aeo-platform/backend/app/workflow/a5/canonical.py`

`DashboardPage.tsx` 已经负责：

- 拉取实体列表。
- 保存和切换 `selectedBrandId`。
- 拉取当前品牌的 Dashboard 首页数据。
- 打开最近报告。
- 渲染 `BrandCards`、品牌档案、最近一轮分析。

`BrandCards` 已经负责：

- `管理全部`。
- 当前查看品牌状态。
- `进入分析`。
- `设置监测`。
- `新建品牌`。

因此本次不重做品牌管理入口，只在视觉细节上跟随新版首页统一，不改变它的交互职责。

### 2.2 需要替换的首页能力

当前 `DashboardHomeBoards.tsx` 只展示：

- 最近报告标题。
- 3 个指标卡。
- 引用链接分布。
- 关联问题。

这与 v4 原型不一致，需要升级为“最近一轮分析”整行模块，顺序为：

1. 最近报告头部。
2. KPI 行。
3. 正负词云。
4. 平台诊断。
5. 高风险问题。
6. 当前优势场景。
7. 提及率排行榜。
8. 信源结构。

## 3. 数据 Contract 拆分

### 3.1 首页 API 响应新增字段

接口保持：

- `GET /analytics/v2/dashboard-home?brand_id=...`

新增字段建议挂在当前响应根对象下，保持向后兼容：

```ts
interface DashboardHomeV4Data {
  summary: { headline: string };
  latestReport?: DashboardLatestReport;
  metrics: DashboardHomeMetric[];
  wordCloud: DashboardEmotionWordCloud;
  platformDiagnosis: DashboardPlatformDiagnosisRow[];
  risks: DashboardRiskCard[];
  advantages: DashboardAdvantageCard[];
  mentionRanking: DashboardMentionRankingRow[];
  sourceStructure: DashboardSourceStructure;
}
```

旧字段继续保留一段时间：

- `citationDistribution`
- `relatedQuestions`
- `mentionBoard`
- `sourceBoard`
- `radarBoard`
- `monitoringEntry`

保留原因：避免其他监测相邻页面或旧视图在 rollout 期间被破坏。

### 3.2 字段定义

```ts
interface DashboardEmotionWord {
  text: string;
  weight: number;
  sentiment: 'positive' | 'negative';
  count?: number;
  platforms?: string[];
}

interface DashboardEmotionWordCloud {
  positive: DashboardEmotionWord[];
  negative: DashboardEmotionWord[];
}

interface DashboardPlatformDiagnosisRow {
  platform: string;
  status: 'good' | 'watch' | 'risk' | 'unknown';
  answerCount: number;
  brandMentionCount: number;
  positiveCount: number;
  negativeCount: number;
  mainConcern?: string;
}

interface DashboardRiskCard {
  title: string;
  level: 'high' | 'medium' | 'low';
  platform?: string;
  evidence?: string;
}

interface DashboardAdvantageCard {
  title: string;
  platformCount?: number;
  evidence?: string;
}

interface DashboardMentionRankingRow {
  rank: number;
  brand: string;
  mentionRate: number | null;
  mentionCount: number;
  isCurrentBrand?: boolean;
}

interface DashboardSourceStructure {
  officialConversionRate: number | null;
  topDomains: DashboardCitationDomain[];
  sourceTypes: DashboardCitationSourceType[];
}
```

### 3.3 禁止字段和禁止口径

- 不做 `firstMentionRate`。
- 不展示 `mentionShare` / `提及份额`。
- 不把竞品排行切换误做成多品牌监测切换。
- 不用通用 TF-IDF 直接生成正负词云。
- 不在 UI 写自我解释式文案。

## 4. A5 数据来源判断

### 4.1 已有基础

`aeo-platform/backend/app/workflow/a5/canonical.py` 已有以下字段基础：

- `brand_visibility`：可作为提及率。
- `brand_rank`：当前品牌排名。
- `top_brand_ranking`：当前只取前 5，需要扩展到前 10。
- `top_positive_reasons`：正向理由基础。
- `top_negative_topics`：负向主题基础。
- `sentiment_risk`：情绪与风险聚合。
- `platform_profile`：平台侧画像基础。
- `source_summary`：来源结构基础。
- `official_conversion_rate`：官网转化率。

### 4.2 需要补齐

第一阶段需要补齐的确定性投影：

- `dashboard_projection.home_v4.word_cloud`
- `dashboard_projection.home_v4.platform_diagnosis`
- `dashboard_projection.home_v4.risks`
- `dashboard_projection.home_v4.advantages`
- `dashboard_projection.home_v4.mention_ranking`
- `dashboard_projection.home_v4.source_structure`

这些字段应由 A5 结构化数据生成，前端不自行推断核心业务结论。

## 5. 开发阶段拆分

### S0：开发设计与状态对齐

目标：

- 固化开发拆分文档。
- 固化开发 State 文档。
- 明确前端、API、A5 的责任边界。

验收：

- 文档中能看出每个模块的数据来源、落地文件和验证方式。
- 没有与 PRD / v4 原型冲突的开发假设。

### S1：前端类型与适配层

文件：

- `frontend/src/types/dashboard.ts`
- `frontend/src/adapters/dashboardHome.ts`

任务：

- 增加 v4 首页字段类型。
- 增加 response normalize。
- 兼容旧响应为空或缺字段的情况。
- 保持旧 `DashboardHomeData` 字段不删除。

验收：

- 类型能表达 v4 模块。
- 旧接口返回时页面仍可渲染空态。
- 不出现英文 UI 文案。
- 不出现 `提及份额`。

### S2：前端最近一轮分析模块

建议拆成以下组件：

- `DashboardLatestReportHeader`
- `DashboardMetricStrip`
- `DashboardEmotionWordCloud`
- `DashboardPlatformDiagnosis`
- `DashboardRiskCards`
- `DashboardAdvantageCards`
- `DashboardMentionRanking`
- `DashboardSourceStructure`

主要承载文件可继续是：

- `frontend/src/components/dashboard/DashboardHomeBoards.tsx`

如果文件过大，再拆到：

- `frontend/src/components/dashboard/home/`

任务：

- 按 v4 原型顺序重排模块。
- 每个模块整体占一整行或清晰分区，不再堆叠到一个拥挤网格。
- KPI 保持短信息，不写解释性段落。
- 词云作为独立模块。
- 提及率排行榜展示前十。

验收：

- 品牌卡片区域仍可切换监测品牌。
- 最近一轮分析不再承担品牌切换。
- 移动端可读，桌面端信息层级清楚。

### S3：首页 API 投影扩展

文件：

- `aeo-platform/backend/app/services/analytics_service.py`

任务：

- 在 `_build_dashboard_home_from_projection` 中优先读取 `dashboard_projection.home_v4`。
- 没有 `home_v4` 时，从现有 `metric_bundle` / `source_summary` / sections data 做兼容投影。
- 输出 camelCase 字段给前端。
- 保留原有 `latestReport`、`metrics`、`citationDistribution`、`relatedQuestions` 兼容字段。

验收：

- `/analytics/v2/dashboard-home` 对旧报告不报错。
- 对新 A5 报告能返回 v4 字段。
- 当前品牌 `brand_id` 过滤逻辑不变。

### S4：A5 首页投影

文件：

- `aeo-platform/backend/app/workflow/a5/canonical.py`

任务：

- 将 `top_brand_ranking` 从前 5 扩展为前 10。
- 新增 `build_home_v4_projection`。
- 正负词云从 `top_positive_reasons` 和 `top_negative_topics` 生成，不走 `keywords.py` 的通用 TF-IDF。
- 平台诊断基于平台答案数、品牌提及、正负情绪和主要负向主题。
- 风险问题优先来自 `question_diagnostics.risk_rows` 和 `sentiment_risk`。
- 优势场景优先来自品牌进入且正向或高覆盖的场景。
- 信源结构来自 `source_summary`。

验收：

- A5 artifact 中出现 `dashboard_projection.home_v4`。
- 字段能被 `analytics_service` 无损投影到前端。
- 词云结果可解释、可复核，不是纯关键词噪声。

### S5：端到端验证

验证命令：

- `python scripts/validate_change.py`
- `npm run lint`
- `npm run build`
- 后端相关测试或最小 API smoke。
- 扫描改动文件，确认没有异常问号占位符。

验收：

- 静态检查通过。
- 首页能加载。
- 当前品牌切换后最近一轮分析跟随 `brand_id` 变化。
- 新建品牌、设置监测、进入分析入口仍存在。

## 6. 开发顺序建议

推荐按以下顺序执行：

1. S1：先扩展 TypeScript 类型和 adapter，保证前端可以接受新数据。
2. S2：先用兼容数据和空态完成 UI 骨架。
3. S3：扩展 API 投影，让旧报告也能显示尽可能多的 v4 模块。
4. S4：补 A5 正式投影，提升数据质量。
5. S5：统一验证和回归品牌管理能力。

理由：

- 前端和 API contract 先稳定，便于快速验证原型方向。
- A5 是数据质量核心，但不应阻塞 UI 框架落地。
- 旧报告兼容必须先做，否则线上用户可能在没有新 A5 artifact 时看到空页面。

## 7. 风险与控制

| 风险 | 控制方式 |
| --- | --- |
| 改版误删多品牌管理能力 | `DashboardPage` 和 `BrandCards` 不重写，只做必要视觉适配 |
| 前端自行编造分析结论 | 核心结论由 A5 或 API 投影产生，前端只格式化展示 |
| 词云退化为关键词堆砌 | 第一阶段只用正向理由和负向主题聚合，不用通用 TF-IDF |
| 旧报告缺少新字段 | API 兼容投影，前端空态兜底 |
| UI 自说自话 | 文案只保留标题、标签、数据、行动按钮、必要空态 |
| 排行口径错误 | 使用提及率排名，不展示提及份额，不做首位提及率 |

## 8. 开发 State 对齐方式

开发期间以 `docs/state-geo-dashboard-home-v4-2026-04-24.md` 为单一状态板。

每完成一个阶段，更新：

- 当前阶段。
- 已完成文件。
- 当前阻塞。
- 验证命令和结果。
- 下一个开发动作。

如果实现中发现 PRD 或原型需要调整，先更新 State 中的“产品偏差”，再决定是否回写 PRD。
