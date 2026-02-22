# Specta AI PRD v2.0 — 用户确认版

> **作者**: Marty Cagan (产品经理)
> **日期**: 2026-02-22
> **状态**: 用户已确认，可执行
> **前置文档**: [reform-plan.md](./reform-plan.md), [pm-analysis-issues.md](./pm-analysis-issues.md)
> **实施顺序**: Issue #3 → Issue #5 → Issue #4

---

## 目录

1. [Issue #3: 报告质量全面重构 PRD](#issue-3-报告质量全面重构)
2. [Issue #4: 全景基线分析 PRD](#issue-4-全景基线分析)
3. [Issue #5: 交付物导航合并 PRD](#issue-5-交付物导航合并)
4. [总实施计划与验收标准](#总实施计划与验收标准)

---

# Issue #3: 报告质量全面重构

## 1. 概述

### 1.1 问题根因

A5 后端 prompt 输出的字段名与前端 `ReportContent.tsx` 渲染的字段名**不匹配**，导致：

| Tab | A5 输出字段 | 前端读取字段 | 结果 |
|-----|-----------|------------|------|
| 平台分析 | `mention_count`, `actual_quotes`, `optimization_tips` | `mention_rate`, `summary`, `status` | 只显示"成功"标签 |
| 竞品对比 | `competitor`, `brand_mention_rate`, `vs_brand` | `name`, `bwvs`, `coverage` | 全显示 `--` |
| 优化建议 | `actionable_recommendations` (EEAT 格式) | `recommendations` (老格式) | 泛泛之谈 |

### 1.2 目标

- 报告 6 个 Tab 全部展示有意义的数据（总览/行业洞察/平台分析/竞品对比/优化建议/风险提示）
- 前端字段对齐 A5 prompt 的输出结构
- 优化建议按用户要求重构为"做得好的 + 做得不好的 + 具体建议"三段式
- 竞品对比展示实际抓取中出现的竞品信息

## 2. 平台分析 Tab 重构

### 2.1 信息架构

```
平台分析 Tab
├── 平台总览卡片 (每个有数据的平台一张)
│   ├── [平台名称]  [成功 ✓] 或 [失败 ✗]
│   ├── 核心指标行:
│   │   ├── 提及次数: N (来自 mention_count)
│   │   ├── 平均引用数: N.N (来自 avg_citations)
│   │   └── 回答字数: NNN-NNN字 (来自 answer_length_range)
│   ├── 品牌实际引用片段 (来自 actual_quotes)
│   │   └── 若无引用: "样本中未提及品牌"
│   ├── 内容偏好 (来自 content_preference)
│   ├── 优势 (来自 strengths)
│   ├── 短板 (来自 weaknesses)
│   └── 优化建议 (来自 optimization_tips)
└── 页脚: "数据基于 N 个问题的实际 AI 回答分析"
```

### 2.2 前端字段映射

前端从 `platform_analysis` 数组中读取每个平台对象，字段映射如下：

| A5 输出字段 | 前端渲染位置 | 类型 | 说明 |
|------------|------------|------|------|
| `platform` | 卡片标题 | string | 平台标识 (deepseek/kimi/doubao/hunyuan) |
| `platform_name` | 卡片标题显示名 | string | 中文名 |
| `mention_count` | 核心指标 | number | 提及次数 |
| `avg_citations` | 核心指标 | number | 平均引用数 |
| `answer_length_range` | 核心指标 | string | 如 "200-400字" |
| `actual_quotes` | 引用片段区 | string[] | 品牌被提及时的实际文字摘录 |
| `performance_summary` | 概述区 | string | 基于数据的表现概述 |
| `content_preference` | 偏好说明 | string | 该平台内容偏好 |
| `strengths` | 优势列表 | string[] | 品牌在该平台的优势 |
| `weaknesses` | 短板列表 | string[] | 品牌在该平台的短板 |
| `optimization_tips` | 优化建议 | string[] | 具体到内容类型/关键词/结构 |

### 2.3 Fallback 逻辑

当 LLM 未生成 `platform_analysis` 或质量不达标时，从 `platform_breakdown`（真实计算数据）自动构建 fallback 卡片：

```python
# 伪代码
for platform, stats in platform_breakdown.items():
    fallback_card = {
        "platform": platform,
        "platform_name": PLATFORM_NAMES[platform],
        "mention_count": stats["mentions"],
        "avg_citations": 0,  # 无法从 platform_breakdown 获取
        "answer_length_range": "--",
        "actual_quotes": [],
        "performance_summary": f"共 {stats['total']} 个问题，提及 {stats['mentions']} 次",
        "strengths": [],
        "weaknesses": [],
        "optimization_tips": [],
    }
```

## 3. 竞品对比 Tab 重构

### 3.1 用户确认的需求

> 如果之前已列出竞品，应告知本次抓取中哪些竞品出现了、出现在哪些问题、做得好的是什么、为什么能出现在对应问题中

### 3.2 信息架构

```
竞品对比 Tab
├── 竞品概览 (overview 文字说明)
│   └── "本次分析中，在 N 个 AI 回答中检测到以下竞品出现情况..."
│
├── 竞品出现情况表格 (comparison_matrix)
│   ├── 列: 竞品名称 | 提及率 | 出现问题数 | 情感 | vs 本品牌 | 为什么出现
│   ├── 本品牌行高亮显示
│   └── 未出现的竞品标注"样本中未出现"
│
├── 竞品详情卡片 (对提及率 > 0 的竞品展开)
│   ├── 出现在哪些问题 (question list)
│   ├── 做得好的是什么 (advantage_reasons)
│   └── 可借鉴之处 (learnings)
│
└── 差异化策略 (differentiation_strategy)
```

### 3.3 前端字段映射

竞品对比从两个数据源获取：

**数据源 A**: `competitor_deep_analysis`（LLM 生成，定性分析）

| A5 输出字段 | 前端渲染位置 | 类型 |
|------------|------------|------|
| `overview` | 竞品概览文字 | string |
| `comparison_matrix[].competitor` | 表格-竞品名称列 | string |
| `comparison_matrix[].brand_mention_rate` | 表格-本品牌提及率 | number |
| `comparison_matrix[].competitor_mention_rate` | 表格-竞品提及率 | number |
| `comparison_matrix[].vs_brand` | 表格-对比列 | string ("高于"/"低于"/"持平") |
| `comparison_matrix[].advantage_reasons` | 详情卡-为什么出现 | string[] |
| `comparison_matrix[].learnings` | 详情卡-可借鉴之处 | string[] |
| `differentiation_strategy` | 差异化策略 | string |

**数据源 B**: `competitors`（后端 `_calculate_competitor_metrics()` 计算，定量数据）

| 字段 | 用途 | 类型 |
|------|------|------|
| `name` | 竞品名称 | string |
| `mention_rate` | 真实提及率 | number (0-1) |
| `avg_ranking` | 基于提及频率的排名 | number |
| `sentiment` | 情感得分 (-1 ~ 1) | number |

**合并策略**: 优先使用数据源 A（LLM 分析更丰富），数据源 B 作为 fallback 和数据校验。当 LLM 生成的 `competitor_mention_rate` 为 0 但后端计算不为 0 时，以后端数据为准。

### 3.4 竞品出现问题追溯

后端需要新增：在 `_calculate_competitor_metrics()` 中，记录每个竞品出现在哪些问题中。

```python
# 新增返回字段
{
    "name": "竞品A",
    "mention_rate": 0.33,
    "appeared_in_questions": ["Q01", "Q05", "Q09"],  # 新增
    "sample_quotes": ["在Q01回答中：'竞品A凭借...'"],  # 新增
    ...
}
```

## 4. 优化建议 Tab 重构

### 4.1 用户确认的需求

> 基于 EEAT 原则，重构为：做得好的 + 做得不好的 + 具体建议

### 4.2 信息架构

```
优化建议 Tab
│
├── 一、品牌做得好的 (Strengths)
│   ├── 每条包含:
│   │   ├── EEAT 维度标签 [E1 经验] / [E2 专业] / [A 权威] / [T 信任]
│   │   ├── 具体表现描述 (来自 current_strength)
│   │   └── 数据支撑 (引用 fetch_results 的具体数据)
│   └── 说明: "以下特征说明品牌已占领部分用户心智"
│
├── 二、品牌需要改进的 (Improvement Areas)
│   ├── 每条包含:
│   │   ├── EEAT 维度标签
│   │   ├── 缺失点描述 (来自 improvement_area)
│   │   └── 影响说明: "缺少哪些渠道推广"
│   └── 说明: "以下方面用户认知不足，需要加强"
│
├── 三、具体行动建议 (Actionable Recommendations)
│   ├── 按优先级排序: P0 → P1 → P2
│   ├── 每条包含:
│   │   ├── 优先级标签 [P0] / [P1] / [P2]
│   │   ├── EEAT 维度标签
│   │   ├── 标题 (title)
│   │   ├── 具体行动步骤 (action)
│   │   ├── 预期效果 (expected_impact，引用具体指标变化)
│   │   ├── 实施难度 (difficulty: 低/中/高)
│   │   └── 预计时间 (timeline)
│   └── 至少 3 条建议，覆盖不同 EEAT 维度
│
└── 四、行动计划时间线 (Action Plan)
    ├── 短期 (1-3个月)
    ├── 中期 (3-6个月)
    └── 长期 (6-12个月)
```

### 4.3 数据来源

从 `actionable_recommendations` 数组中提取：

```typescript
// 提取 "做得好的"
const strengths = actionableRecs
  .filter(r => r.current_strength && r.current_strength.length > 10)
  .map(r => ({
    eeat: r.eeat_dimension,
    text: r.current_strength,
  }));

// 提取 "需要改进的"
const improvements = actionableRecs
  .filter(r => r.improvement_area && r.improvement_area.length > 10)
  .map(r => ({
    eeat: r.eeat_dimension,
    text: r.improvement_area,
  }));
```

### 4.4 EEAT 维度标签设计

| 维度代码 | 名称 | 颜色 | 说明 |
|---------|------|------|------|
| E1 | 经验 (Experience) | 蓝色 | 品牌/产品的真实使用经验是否在 AI 回答中体现 |
| E2 | 专业性 (Expertise) | 紫色 | AI 回答中是否体现品牌的专业知识和技术实力 |
| A | 权威性 (Authoritativeness) | 橙色 | 品牌官方内容、权威媒体引用是否出现 |
| T | 可信度 (Trustworthiness) | 绿色 | 用户评价、口碑、第三方背书是否被引用 |

## 5. 实施清单

### 5.1 后端修改

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `nodes_a5.py` : `_calculate_competitor_metrics()` | 新增 `appeared_in_questions` 和 `sample_quotes` 字段 | P0 |
| `nodes_a5.py` : `_normalize_report_data()` | 确保 `platform_analysis` 和 `competitor_deep_analysis` 有合理 fallback | P0 |
| `nodes_a5.py` : `a5_analytics_node()` | 将 `competitor_metrics` 数据传入 A5 LLM prompt，让 LLM 基于真实数据生成分析 | P1 |

### 5.2 前端修改

| 文件 | 修改内容 | 优先级 |
|------|---------|--------|
| `ReportContent.tsx` : 平台分析 Tab | 适配 `platform_analysis` 新字段名，增强卡片布局 | P0 |
| `ReportContent.tsx` : 竞品对比 Tab | 适配 `comparison_matrix` 新字段名，新增竞品详情卡片 | P0 |
| `ReportContent.tsx` : 优化建议 Tab | 三段式重构 + EEAT 标签 + `actionable_recommendations` 渲染 | P0 |

### 5.3 验收标准

- [ ] 平台分析 Tab: 每个有数据的平台显示提及次数、引用数、实际引用片段、优化建议
- [ ] 竞品对比 Tab: 表格所有列有数据；展示每个竞品出现在哪些问题中；未出现的标注"样本中未出现"
- [ ] 优化建议 Tab: 分为"做得好的"/"需改进的"/"具体建议"三段；每条有 EEAT 标签；具体建议有 expected_impact 引用数字
- [ ] 所有 Tab 在 LLM 输出缺失时有合理的 fallback（不显示空白）

---

# Issue #4: 全景基线分析

## 1. 概述

### 1.1 核心概念

| 术语 | 定义 | 示例 |
|------|------|------|
| 基线 (Baseline) | 品牌在大众/行业全景视角中的位置 | "抗衰最好的晚霜有哪些？" |
| 基线问题 | 用户视角的行业全景问题，不带特定画像 | "预算1000元眼霜怎么选？" |
| 场景分析 | 特定画像/场景下的品牌表现 | "30岁敏感肌妈妈用什么面霜？" |

### 1.2 用户确认的关键要求

1. **品牌创建后先确认品牌信息**，不是完全自动
2. **基线问题必须是用户视角**：如"预算1000元眼霜选择"、在主要产品领域进行咨询
3. **直接品牌问题最多占 10%**：不要"xx品牌怎么样"这类
4. **基线报告独立可用**
5. **支持定时任务监测更新**
6. **可以重跑基线**，用户看最新报告，也可以看历史
7. **场景报告需要基线上下文**
8. **基线和用户场景 BWVS 分开计算**

## 2. 流程设计

### 2.1 主流程（用户确认版）

```
用户: "帮我分析观夏"
    │
    ▼
[A1] 品牌信息 + 竞品识别
    │
    ▼
系统展示品牌信息摘要，请用户确认
    ├── 用户: "确认" / "修改xxx"
    │
    ▼
系统: "好的，我先为您做一个全景基线分析，
       看看观夏在整个香氛行业中的位置。"
    │
    ▼
自动执行: A3(baseline, 用户视角) → A4 → A5(baseline)
    │
    ▼
输出: 基线报告（Canvas 中展示）
    │
    ▼
系统: "基线分析完成！观夏的行业 BWVS 基线分为 35.4。
       接下来您可以：
       1. 深入某个用户群体/场景（如送礼场景）
       2. 设置定时监测，自动定期更新基线
       3. 查看详细报告"
    │
    ├── 用户选择场景: → A2 → A3(persona) → A4 → A5(persona, 含基线上下文)
    ├── 用户设置监测: → 创建定时任务
    └── 用户: "不用了" → 结束
```

### 2.2 重跑基线流程

```
用户: "重新跑一次基线" / 定时任务自动触发
    │
    ▼
跳过 A1（复用已有品牌信息，除非用户要求更新）
    │
    ▼
A3(baseline) → A4 → A5(baseline)
    │
    ▼
新基线报告覆盖 Canvas Tab，旧报告存入历史版本
    │
    ▼
可对比: 新基线 vs 上次基线（delta_vs_previous）
```

## 3. 基线问题生成规则

### 3.1 核心原则

> 基线问题必须是**用户视角**，模拟真实用户在 AI 搜索中会问的行业/品类问题。
> 直接品牌问题（"xx品牌怎么样"）**最多占 10%**。

### 3.2 问题分类与比例

| 类别 | 比例 | 说明 | 示例 |
|------|------|------|------|
| 品类需求咨询 | 30% | 用户在主要产品领域的需求咨询 | "预算1000元的眼霜怎么选？" / "抗衰最好的晚霜有哪些？" |
| 场景化选购 | 25% | 带有预算/场景/用途的选购问题 | "送妈妈什么护肤品比较好？" / "冬天皮肤干用什么面霜？" |
| 品类对比排名 | 20% | 行业排名、对比类问题 | "国产高端护肤品排行榜" / "哪个品牌的精华液口碑最好？" |
| 行业趋势探索 | 15% | 行业发展、新趋势类问题 | "2026年护肤品行业有什么新趋势？" / "成分党推荐的护肤品有哪些？" |
| 品牌直接问题 | 10% (上限) | 直接提及目标品牌 | "观夏的香薰和气味图书馆比怎么样？" |

### 3.3 问题生成参数

- **总问题数**: 10-15 个核心问题（基于品牌产品线数量动态调整）
- **覆盖产品线**: 必须覆盖品牌的核心产品领域（从 `brand_profile.core_products` 获取）
- **竞品引入**: 在品类对比排名类问题中自然引入 A1 识别的竞品
- **平台分配**: 4 个平台均匀分配（每个问题发送到全部 4 个平台）
- **口语化**: 问题必须像真实用户会问的（参考 A3 prompt 的口语化要求）

### 3.4 动态生成 vs 模板

用户确认：**基于品牌+竞品信息动态生成**（不使用固定模板）。

实现方式：A3 新增 `baseline_dynamic` 模式，使用 LLM 根据品牌档案和竞品列表动态生成基线问题。

```python
# A3 模式路由
a3_mode:
  - "brand"             # 现有：YAML 模板驱动（保留作为 fallback）
  - "persona"           # 现有：画像聚焦
  - "baseline_dynamic"  # 新增：动态基线生成
```

### 3.5 A3 基线 Prompt 核心约束

```
你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，生成模拟用户在 AI 搜索引擎中会提问的**行业全景问题**。

## 核心规则
1. 问题必须是**用户视角**，模拟真实消费者的搜索行为
2. 直接提及目标品牌的问题**不超过总数的 10%**
3. 问题必须覆盖品牌的**主要产品领域**
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 搜索中输入的

## 问题分类比例
- 品类需求咨询 (30%): 在品牌的产品领域内，用户的实际需求咨询
- 场景化选购 (25%): 带有预算/场景/用途的选购问题
- 品类对比排名 (20%): 行业排名、品牌对比
- 行业趋势探索 (15%): 行业趋势、新概念
- 品牌直接问题 (10% 上限): 直接提及目标品牌
```

## 4. 基线报告内容

### 4.1 基线报告 vs 场景报告

| 维度 | 基线报告 | 场景报告 |
|------|---------|---------|
| 问题来源 | 动态生成的行业全景问题 | 画像驱动的场景问题 |
| BWVS 含义 | 行业基线 BWVS（品牌在大众视角的能见度） | 场景 BWVS（品牌在特定人群中的能见度） |
| 核心价值 | "品牌在行业中的位置" | "品牌在特定场景中的表现" |
| 竞品对比 | 哪些竞品在行业问题中出现 → 行业格局 | 哪些竞品在场景问题中出现 → 场景竞争 |
| 建议导向 | 行业级定位策略 + 内容布局 | 场景级内容优化 + 触点策略 |
| 独立可用 | 是 | 需要基线上下文 |

### 4.2 基线报告 A5 prompt 定制要点

场景报告的 A5 prompt 需要注入基线报告摘要（用户确认）：

```python
# 在 _build_a5_user_content() 中新增
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

## 5. 定时监测

### 5.1 定时任务设计

```
用户: "帮我设置每周监测"
    │
    ▼
系统创建定时任务:
  - task_type: "baseline_monitoring"
  - entity_id: 品牌实体 ID
  - frequency: weekly / monthly
  - next_run: 下次执行时间
  - config: { reuse_brand_profile: true, question_mode: "baseline_dynamic" }
    │
    ▼
定时触发: 跳过 A1 → A3(baseline) → A4 → A5(baseline)
    │
    ▼
生成新快照（AnalysisSnapshot）
    │
    ▼
通知用户: "品牌基线监测已更新，BWVS: 35.4 → 38.2 (+2.8)"
```

### 5.2 历史趋势

每次基线分析生成的快照（AnalysisSnapshot）记录：
- `bwvs_index`: 基线 BWVS
- `mention_rate`: 基线提及率
- `sentiment_score`: 情感得分
- `coverage_score`: 平台覆盖度
- `snapshot_type`: "baseline" / "persona"
- `created_at`: 时间戳

Dashboard 可基于快照数据绘制 BWVS 趋势曲线。

## 6. 状态管理变更

### 6.1 AgentState 扩展

```python
class AgentState(TypedDict):
    # 现有字段...
    brand_profile: dict
    competitors: list
    marketing_personas: dict
    simulated_questions: dict
    questions: list
    fetch_results: list
    metrics: dict
    report: dict

    # 新增: 基线相关字段
    analysis_mode: str              # "baseline" / "persona" / "full"
    baseline_questions: list        # 基线问题列表
    baseline_fetch_results: list    # 基线抓取结果
    baseline_metrics: dict          # 基线指标
    baseline_report: dict           # 基线报告
```

### 6.2 Orchestrator 两阶段编排

```
Phase 1 (基线):
  A1 → 用户确认品牌信息 → A3(baseline_dynamic) → A4 → A5(baseline)
  结果存入: baseline_questions, baseline_fetch_results, baseline_metrics, baseline_report

Phase 2 (场景，可选):
  A2 → A3(persona) → A4 → A5(persona, 注入 baseline_report 上下文)
  结果存入: simulated_questions, fetch_results, metrics, report
```

## 7. 实施清单

### 7.1 后端

| 文件 | 修改内容 | 阶段 |
|------|---------|------|
| `state.py` | 新增 `analysis_mode`, `baseline_*` 字段 | Phase 4a |
| `nodes_a3.py` | 新增 `baseline_dynamic` 模式 + 用户视角 prompt | Phase 4a |
| `nodes_a5.py` | 支持 `report_type=baseline/persona` 参数 | Phase 4a |
| `nodes_a5.py` | 场景报告注入基线上下文 | Phase 4a |
| `orchestrator_node.py` | 两阶段编排逻辑 | Phase 4a |
| `general_react_agent.md` | Orchestrator prompt 调整 | Phase 4a |
| 新建 `monitoring_scheduler.py` | 定时任务调度 | Phase 4b |
| `snapshot_service.py` | 支持 `snapshot_type` 过滤 | Phase 4b |

### 7.2 前端

| 文件 | 修改内容 | 阶段 |
|------|---------|------|
| `ReportContent.tsx` | 区分基线报告和场景报告的标题/视角 | Phase 4a |
| Canvas artifact | 基线报告 output_type 标识 | Phase 4a |
| Dashboard | 基线 BWVS 趋势曲线（基于快照） | Phase 4c |

### 7.3 验收标准

- [ ] 用户输入品牌后，A1 完成后展示品牌信息摘要供确认
- [ ] 确认后自动执行基线分析 (A3→A4→A5)
- [ ] 基线问题中直接品牌问题不超过 10%，覆盖品牌核心产品领域
- [ ] 基线报告独立可用，展示行业 BWVS、竞品格局、优化建议
- [ ] 支持重跑基线，新报告覆盖 Canvas，旧报告可通过版本选择器查看
- [ ] 场景报告中包含基线对比数据
- [ ] 支持定时任务（每周/每月）自动更新基线
- [ ] 基线和场景 BWVS 独立计算，Dashboard 分区展示

---

# Issue #5: 交付物导航合并

## 1. 概述

### 1.1 问题

每次分析在 Canvas 中创建新的同名 Tab，用户无法区分多次结果。

### 1.2 解决方案

同类型交付物合并为单个 Tab，内部通过版本选择器浏览历史，支持跳转到对话上下文。

## 2. 合并规则

### 2.1 固定 Tab 列表

| output_type | Tab 标题 | 固定 ID 规则 |
|-------------|---------|-------------|
| `report` | 分析报告 | `{sessionId}_report` |
| `report_baseline` | 基线报告 | `{sessionId}_report_baseline` |
| `report_persona` | 场景报告 | `{sessionId}_report_persona` |
| `questionList` | 问题列表 | `{sessionId}_questionList` |
| `fetchResults` | 抓取结果 | `{sessionId}_fetchResults` |

### 2.2 版本管理

```
新 artifact 到达时:
  1. 查找 Canvas 中是否有同 ID 的 Tab
  2. 如果存在:
     a. 将当前 data 存入 versions[] 历史
     b. 用新 data 覆盖当前 data
     c. 记录 linkedMessageId
  3. 如果不存在:
     a. 创建新 Tab
  4. 自动切换到该 Tab
```

### 2.3 历史版本上限

用户确认: 最多保留 **10 个历史版本**，超出后淘汰最旧版本。

## 3. UI 设计

### 3.1 版本选择器

位于报告内容区顶部，紧跟标题之下：

```
┌─────────────────────────────────────────┐
│  品牌可见度分析报告                         │
│  ┌─────────────────────────────┐         │
│  │ v3 - 2026-02-22 14:30 (最新) ▼│         │
│  └─────────────────────────────┘         │
│                                          │
│  [报告内容...]                            │
│                                          │
│  ─────────────────────────────────────── │
│  📎 跳转到对应对话 →                       │
└─────────────────────────────────────────┘
```

下拉列表:
```
v3 - 2026-02-22 14:30 (最新)  ← 当前
v2 - 2026-02-21 10:15
v1 - 2026-02-20 09:00
```

### 3.2 对话跳转

点击"跳转到对应对话"后：
- 滚动到对应消息位置
- 高亮该消息 3 秒
- 不折叠中间消息（简单实现）

## 4. 数据模型

### 4.1 前端类型

```typescript
interface CanvasContent {
  id: string;                    // 固定: `${sessionId}_${type}`
  type: string;                  // "report" | "report_baseline" | ...
  title: string;
  data: Record<string, unknown>;
  versions: ContentVersion[];    // 历史版本列表（新增）
  currentVersionIndex: number;   // 当前展示版本索引（新增，-1 = 最新）
  linkedMessageId?: string;      // 最新版本对应的对话消息 ID（新增）
}

interface ContentVersion {
  versionNumber: number;         // v1, v2, v3...
  timestamp: string;             // ISO 时间戳
  data: Record<string, unknown>; // 该版本的完整数据
  linkedMessageId?: string;      // 该版本对应的对话消息 ID
}
```

### 4.2 后端变更

`save_and_send_artifact()` 的 artifact ID 改为固定格式：

```python
# 之前: 每次随机 ID
artifact_id = str(uuid4())

# 之后: 固定 ID
artifact_id = f"{session_id}_{output_type}"
```

WebSocket 事件新增 `linkedMessageId` 字段：

```python
await send_ws_event(session_id, "output_ready", {
    "id": artifact_id,
    "type": output_type,
    "title": title,
    "data": data,
    "linkedMessageId": current_message_id,  # 新增
    "timestamp": datetime.now().isoformat(),
})
```

## 5. 实施清单

### 5.1 后端

| 文件 | 修改内容 |
|------|---------|
| `events.py` : `save_and_send_artifact()` | artifact ID 改为 `{session}_{type}` 格式；新增 `linkedMessageId` |
| `nodes_a5.py` | 传入 `output_type="report_baseline"` 或 `"report_persona"` |

### 5.2 前端

| 文件 | 修改内容 |
|------|---------|
| `canvasStore.ts` : `addContent()` | 同 ID 时合并到 versions[]，覆盖 data |
| `canvasStore.ts` | 新增 `setContentVersion(id, versionIndex)` action |
| `CanvasHeader.tsx` 或新组件 | 版本选择器 dropdown |
| `ReportContent.tsx` | 底部"跳转到对话"链接 |
| `ChatPanel.tsx` | `scrollToMessage(messageId)` 方法 + 高亮动画 |
| `types/canvas.ts` | 更新 CanvasContent 类型，新增 ContentVersion |

### 5.3 验收标准

- [ ] 同类型 artifact 不再创建重复 Tab，覆盖更新同一 Tab
- [ ] 版本选择器展示所有历史版本（最多 10 个）
- [ ] 切换版本后报告内容对应更新
- [ ] 点击"跳转到对话"滚动到对应消息并高亮
- [ ] 基线报告和场景报告各有独立 Tab（不互相覆盖）

---

# 总实施计划与验收标准

## 实施顺序（用户确认）

```
Phase 1: Issue #3 报告质量重构 (2-3天)
├── 后端: nodes_a5.py fallback 增强 + competitor 追溯字段
├── 前端: ReportContent.tsx 三个 Tab 重构
│   ├── 平台分析: 适配 platform_analysis 新字段
│   ├── 竞品对比: 适配 comparison_matrix + 详情卡片
│   └── 优化建议: 三段式 + EEAT 标签
└── 验收: 6 个 Tab 全部有数据，建议有 EEAT 标签

Phase 2: Issue #5 交付物合并 (2-3天)
├── 后端: artifact ID 固定化 + linkedMessageId
├── 前端: canvasStore 版本合并 + 版本选择器 + 对话跳转
└── 验收: 多次分析不重复 Tab，版本切换正常

Phase 3: Issue #4 基线分析 (8-13天)
├── Phase 4a: 基线流程打通 (3-5天)
│   ├── State 扩展 + A3 baseline_dynamic 模式
│   ├── A5 双报告 + 场景注入基线上下文
│   ├── Orchestrator 两阶段编排
│   └── 前端区分基线/场景报告 Tab
├── Phase 4b: 定时监测 + 历史版本 (2-3天)
│   ├── 定时任务调度器
│   ├── 快照 snapshot_type 过滤
│   └── 重跑基线 → 版本管理
└── Phase 4c: Dashboard 分区 (3-5天)
    ├── 基线/场景双区展示
    └── BWVS 趋势曲线

总预估: 12-19 天
```

## 关键代码位置参考

| 功能 | 文件路径 |
|------|---------|
| A5 报告生成 + 指标计算 | `aeo-platform/backend/app/workflow/nodes_a5.py` |
| A5 系统 prompt (7章节) | `nodes_a5.py:773-910` (`_get_a5_system_prompt()`) |
| A5 竞品指标计算 | `nodes_a5.py:676-770` (`_calculate_competitor_metrics()`) |
| A5 报告规范化 | `nodes_a5.py:1045-1068` (`_normalize_report_data()`) |
| A3 问题生成 (含 persona 模式) | `aeo-platform/backend/app/workflow/nodes_a3.py` |
| A3 问题模板 | `aeo-platform/backend/prompts/question_templates.yaml` |
| A3 问题生成 prompt | `aeo-platform/backend/prompts/question_simulation_agent.md` |
| 前端报告渲染 | `frontend/src/components/canvas/contents/ReportContent.tsx` |
| Canvas Store | `frontend/src/stores/canvasStore.ts` |
| Canvas 类型定义 | `frontend/src/types/canvas.ts` |
| 工作流图定义 | `aeo-platform/backend/app/workflow/graph.py` |
| Orchestrator 编排 | `aeo-platform/backend/app/workflow/orchestrator_node.py` |
| Orchestrator prompt | `aeo-platform/backend/prompts/general_react_agent.md` |
| 快照服务 | `aeo-platform/backend/app/services/snapshot_service.py` |
| AgentState 定义 | `aeo-platform/backend/app/workflow/state.py` |
