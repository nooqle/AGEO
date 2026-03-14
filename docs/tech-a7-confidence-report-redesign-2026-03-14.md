# A7 置信度报告重设计技术方案

> **作者**: Martin Fowler + John Carmack
> **日期**: 2026-03-14
> **状态**: 可实施
> **对应设计**: [design-a7-confidence-report-redesign-2026-03-14.md](/D:/AGEO/docs/design-a7-confidence-report-redesign-2026-03-14.md)

---

## 1. 技术目标

本次改造只重写 `confidence_signal` 的解释层与交付层，不替换现有评分引擎。

必须保持：

1. `report_kind = confidence_signal`
2. A7 继续负责生成 Artifact
3. AICE 继续负责底层评分
4. `extra_evaluate` 继续可用

本次新增的技术目标：

1. 将 `AICE 高分阈值` 设计为可配置参数，而不是写死为 `75`
2. 在后端统一完成阵营分类、象限计算和分析分组
3. 在前端用新的生态矩阵与分析区块替换当前排名页

---

## 2. 总体实现策略

推荐采用“后端扩展 payload，前端重写 renderer”的增量方案。

```text
现有 AICE 打分
  ->
后端 enrich report semantics
  ->
confidence_signal payload 扩展
  ->
前端 ConfidenceSignalContent 重写
```

不做的事：

1. 不新增一级 Canvas 类型
2. 不新增新的 Agent
3. 不新增新的 WebSocket 事件
4. 不重写 `extra_evaluate`

---

## 3. 阈值参数设计

## 3.1 参数目标

用户明确要求 `75` 不能写死。

因此阈值设计必须满足：

1. 当前实现有默认值
2. 后续可以从配置、实验参数或 UI 控件注入
3. 前后端都从同一个 payload 字段读取

## 3.2 推荐字段

在 `confidence_signal` 顶层新增：

```json
{
  "matrix_config": {
    "aice_threshold": 75,
    "frequency_threshold": 2,
    "frequency_threshold_mode": "median"
  }
}
```

含义：

1. `aice_threshold`
   - 高 / 低置信分割线
2. `frequency_threshold`
   - 高频 / 低频分割线
3. `frequency_threshold_mode`
   - 当前如何计算频次阈值

## 3.3 后端参数入口

后端 `build_confidence_signal_report` / `build_confidence_signal_report_async` / `_compose_report_payload` 增加可选参数：

```python
aice_threshold: float | None = None
```

规则：

1. 若未传入，则使用默认值
2. 若 `extra_evaluate` 重建报告，则优先沿用已有 report 内的 `matrix_config.aice_threshold`

这保证后续阈值一旦可调，手动追加评估不会导致象限规则飘移。

---

## 4. 后端改造方案

## 4.1 继续保留现有评分入口

以下函数保留原职责：

1. `_score_url_item`
2. `_score_text_item`
3. `_enrich_url_items`
4. `extract_citations`
5. `append_manual_items_async`

这些函数继续只负责“产生 AICE 分数和 recommendation 原材料”。

## 4.2 在 `_compose_report_payload` 之后新增语义增强

推荐新增一个统一 enrich 层：

```text
scored_items
  ->
semantic enrichment
    - entity classification
    - matrix config
    - quadrant assignment
    - analysis grouping
    - repair action synthesis
  ->
report payload
```

### 4.2.1 阵营分类

新增字段：

```json
{
  "entity_classification": "brand | competitor | general_knowledge"
}
```

当前实现建议先采用后端启发式：

1. `is_official => brand`
2. `brand_keywords` 命中 => `brand`
3. `competitor_names` 命中 => `competitor`
4. 否则 => `general_knowledge`

这是 v1，可先替代当前前端分类。

### 4.2.2 象限计算

新增字段：

```json
{
  "frequency": 3,
  "aice_score": 78.2,
  "quadrant": "q2_false_prosperity",
  "quadrant_label": "虚假繁荣"
}
```

字段映射：

1. `frequency = occurrences`
2. `aice_score = overall_score`

### 4.2.3 原因提炼

新增字段：

```json
{
  "primary_reasons": [
    "C9b 结构化数据完整，机器识别阻力低",
    "C3 证据链较强，事实核查成本低"
  ]
}
```

规则：

1. 第一、第四象限优先抽取高分维度原因
2. 第二、第三象限优先抽取低分维度原因

### 4.2.4 修我动作

新增字段：

```json
{
  "repair_action": "将该页面沉淀为内容模板，并作为后续技术白皮书 SOP。"
}
```

来源：

1. 结合 `entity_classification + quadrant`
2. 结合现有 `recommendations`

---

## 4.3 顶层 payload 扩展

新增顶层字段：

```json
{
  "matrix_config": {},
  "ecosystem_matrix": {},
  "quadrant_overview": [],
  "analysis_blocks": [],
  "general_knowledge_insight": {},
  "repair_actions": []
}
```

### `ecosystem_matrix`

包含：

1. 坐标轴标签
2. 阈值信息
3. 点数量
4. 诊断结论

### `quadrant_overview`

固定 4 项，每项包括：

1. 象限 key
2. 象限名
3. count
4. 阵营分布
5. 说明
6. 行动方向

### `analysis_blocks`

固定输出以下 block：

1. `brand_q1`
2. `competitor_q1`
3. `brand_q2`
4. `competitor_q2`

每个 block 内含：

1. 标题
2. 说明
3. `items`

### `general_knowledge_insight`

包含：

1. summary
2. top_frequency_items
3. top_score_items

### `repair_actions`

固定产出：

1. `P0 立即修缮`
2. `P1 对标固化`
3. `P2 降维覆盖`
4. `P3 战略性忽略`

---

## 5. 前端改造方案

## 5.1 保留入口

以下不改：

1. [ReportContent.tsx](/D:/AGEO/frontend/src/components/canvas/contents/ReportContent.tsx)
2. [CanvasHeader.tsx](/D:/AGEO/frontend/src/components/canvas/CanvasHeader.tsx) 的 `extra_evaluate` 行为

## 5.2 重写 `ConfidenceSignalContent`

旧版核心结构：

1. Hero
2. 摘要卡
3. 发现卡片
4. 品牌高分榜
5. 竞品高分榜

新版核心结构：

1. Hero + 总诊断
2. 生态矩阵
3. 四象限总览
4. 四个深度分析区块
5. 共业观察
6. 修我行动清单

## 5.3 图表方案

生态矩阵采用 `recharts` 的 `ScatterChart` 实现。

原因：

1. 依赖已存在
2. 无需新增图表库
3. 足够支撑 MVP 的散点矩阵交互

## 5.4 类型扩展

在 [canvas.ts](/D:/AGEO/frontend/src/types/canvas.ts) 中新增：

1. `ConfidenceEntityClassification`
2. `ConfidenceQuadrant`
3. `ConfidenceMatrixConfig`
4. `ConfidenceQuadrantOverview`
5. `ConfidenceAnalysisBlock`
6. `ConfidenceRepairAction`
7. `ConfidenceGeneralKnowledgeInsight`

---

## 6. 渐进开发顺序

### Increment 1：后端 payload 扩展

目标：

1. 让后端先返回新字段
2. 旧前端仍能正常工作

### Increment 2：前端渲染器替换

目标：

1. 用新布局替换旧排名页
2. 继续兼容旧字段缺失场景

### Increment 3：命名与文案对齐

目标：

1. 页面内统一使用 `置信度报告`
2. Artifact 标题对齐

---

## 7. 验证方案

后端：

1. `python -m py_compile aeo-platform/backend/app/workflow/a7/confidence_signal.py`

前端：

1. `npx eslint src/components/canvas/contents/ConfidenceSignalContent.tsx src/components/canvas/CanvasHeader.tsx src/types/canvas.ts`

如条件允许，再补：

1. `npm run build`

---

## 8. 实施结论

这次改造是一次典型的“解释层升级”，不是引擎替换。

最关键的技术动作只有两个：

1. 后端把 `confidence_signal` 从“评分列表 payload”升级为“生态报告 payload”
2. 前端把 `ConfidenceSignalContent` 从“排名页”升级为“生态诊断页”

其中 `AICE 阈值参数化` 将作为这次改造的基础能力一并落地，避免未来再返工。
