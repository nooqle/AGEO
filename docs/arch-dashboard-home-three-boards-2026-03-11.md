# 架构方案：Dashboard 首页三看板改版

> 角色：Architect  
> 日期：2026-03-11  
> 状态：方案稿  
> 范围：仅 Dashboard 首页改版  
> 硬约束：不破坏 Dashboard 外的其他首页逻辑

## 1. 目标与边界

本次不是重写整个 Dashboard，而是在现有 Dashboard 基础上增加一层新的首页结构：

1. 提及率看板
2. 官网引用率看板
3. 五维雷达看板
4. Monitoring 独立入口

边界明确如下：

1. 不改 Chat 主链路
2. 不改 Canvas 机制
3. 不改系统其他首页
4. 不重写 Monitoring 主逻辑
5. 不一次性推翻现有 Dashboard 二级分析能力

## 2. 推荐实施方式

推荐方案是：

**在现有 Dashboard 上增加一个首页聚合层，而不是立即重写所有下层模块。**

原因：

1. 可回退
2. 风险低
3. 不会破坏现有 Dashboard 以外的逻辑
4. 可以逐步把旧的场景、竞品、风险模块迁入三看板展开报告

## 3. 目标形态

### 首页层

只负责呈现 3 个看板和 Monitoring 入口。

### 展开层

每个看板点击后进入自己的说明报告。

### 细节层

当前已有的场景、竞品争夺、风险与动作、信息源分析等模块，不在首页并列铺开，而作为展开层的内容来源。

## 4. 首页 ViewModel

建议新增一个专门给首页使用的聚合 ViewModel：

```text
DashboardHomeViewModel
  ├── summary
  ├── mentionBoard
  ├── sourceBoard
  ├── radarBoard
  └── monitoringEntry
```

这层只服务于首页，不承担完整明细。

## 5. 三个看板的数据来源

### 5.1 提及率看板

来源建议：

1. `overview.kpis.brandMentionRate`
2. `mention_sentiment_analysis.brand`
3. `mention_sentiment_analysis.competitors`
4. `scenario_matrix`
5. `competitor_battles`

首页聚合输出应包括：

1. 品牌提及率
2. 情绪概览
3. 主要竞品对比摘要
4. 一句话结论

展开报告输出应包括：

1. 被提及问题
2. 情绪
3. 平台
4. 引用来源
5. 场景归纳

### 5.2 官网引用率看板

来源建议：

1. `overview.kpis.officialCitationRate`
2. `source_overview`
3. `citation_analysis`
4. 场景级官网引用信息
5. 后续 AICE 结果

首页聚合输出应包括：

1. 官网引用率
2. 被引用问题数
3. 被引用内容数
4. 一句话结论

展开报告输出应包括：

1. 问题
2. 引用内容
3. 页面标题
4. 第三方替代来源
5. AICE 解释位

### 5.3 五维雷达看板

建议由首页聚合层统一构造，不直接暴露多个散点指标给页面。

五维如下：

1. 行业影响
2. 人群覆盖
3. 场景覆盖
4. 风险大小
5. 积极情绪大小

首页聚合输出应包括：

1. 雷达图数据
2. 最大优势维度
3. 最大短板维度
4. 一句话结论

## 6. 推荐接口

建议新增首页专用接口：

`GET /analytics/v2/dashboard-home`

返回结构建议：

```json
{
  "summary": {
    "headline": "当前品牌已建立部分 AI 提及，但官网引用仍偏弱。"
  },
  "mentionBoard": {},
  "sourceBoard": {},
  "radarBoard": {},
  "monitoringEntry": {}
}
```

这样首页无需继续在前端拼装复杂判断。

## 7. 前端实施建议

建议新增：

1. `DashboardHomeBoards.tsx`
2. `MentionBoard.tsx`
3. `SourceBoard.tsx`
4. `RadarBoard.tsx`
5. `MentionBoardReport.tsx`
6. `SourceBoardReport.tsx`
7. `RadarBoardReport.tsx`

实施原则：

1. 先新增首页层
2. 旧 tab 保留
3. 首页点击后进入展开报告
4. 不直接删除旧能力

## 8. 实施顺序

### Phase 1

1. 新增首页三看板容器
2. 新增首页聚合接口
3. 保留 Monitoring 入口

### Phase 2

1. 完成提及率说明报告
2. 完成官网引用率说明报告
3. 完成五维雷达说明报告

### Phase 3

1. 将旧的场景、竞品争夺、风险动作进一步迁入说明报告内部
2. 逐步降低首页对旧 tab 的依赖

## 9. 架构结论

推荐做法不是“把整个 Dashboard 推翻重来”，而是：

**在当前 Dashboard 上增加一个高密度首页判断层。**

这满足三个条件：

1. 对现有系统侵入小
2. 对用户价值提升大
3. 对后续扩展 AICE 和情绪分析兼容性好
