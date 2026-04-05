# AGEO Claude Code 参考改造 Phase 7：Step 5 Current Session Evidence Sources（2026-04-04）

> 状态：Active
> 适用分支：`codex/validation-retro-harness`
> 依赖前提：Phase 7 Step 1-3 与 Phase 7.5 最小防守已接入

---

## 1. 目标

Step 4 的目标是把 orchestrator 的 `RecentEvidencePacket` 从“只理解历史知识工具结果”，扩展成“也能理解当前会话真实证据”。

这一步优先覆盖：

1. `A4 current_fetch`
2. `A5 current_artifact`
3. `A7 current_artifact`

不覆盖：

1. AIO / browser trace
2. 上传文件原文全文
3. 全量 artifact 正文回灌

---

## 2. 为什么要做

当前 orchestrator 已经能看到：

- `knowledge_lookup / aggregate / compare / export`

但它还不能同样结构化地看到：

- 当前会话刚抓回来的答案与引用
- 当前会话刚生成的报告摘要
- 当前会话刚生成的置信度摘要

这会导致：

1. A0 知道“有 fetch_results / report”，但不知道最近的高价值证据是什么
2. follow-up 场景仍偏依赖 summary string，而不是 evidence packet
3. 历史材料 packet 比当前会话 packet 反而更完整，优先级容易失真

---

## 3. 实现范围

### 3.1 A4 Current Fetch Evidence

从 `fetch_results` 中抽取少量高价值 evidence item：

1. `fetch_answer`
   - 问题
   - 平台
   - 回答内容摘要
2. `fetch_citation`
   - 问题
   - 平台
   - 引用标题 / 域名 / 摘要

固定 provenance：

- `source = current_fetch`
- `source_type = fetch_answer | fetch_citation`
- `freshness = latest`
- `trust_level = external_untrusted`
- `instruction_authority = false`

### 3.2 A5 Current Artifact Evidence

从 `report + metrics` 中抽取报告摘要：

固定 provenance：

- `source = current_artifact`
- `source_type = report_summary`
- `freshness = latest`
- `trust_level = derived_summary`
- `instruction_authority = false`

内容只取：

1. `executive_summary` 摘要
2. 关键指标（如 mention_rate / content_citation_rate）

### 3.3 A7 Current Artifact Evidence

新增轻量 `confidence_signal_summary` state 字段，不把整份 confidence artifact 写回 state。

固定 provenance：

- `source = current_artifact`
- `source_type = confidence_summary`
- `freshness = latest`
- `trust_level = derived_summary`
- `instruction_authority = false`

内容只取：

1. `overall_conclusion`
2. `我方 / 竞品平均置信度`
3. `评估来源数`

---

## 4. 组装策略

`RecentEvidencePacket` 的组装顺序改为：

1. 先取 `current_fetch/current_artifact`
2. 若当前没有会话证据，再 fallback 到 `knowledge_*`
3. 若当前是 assistant 紧接着完成一次 `knowledge_*`，可保留该历史 evidence 的优先展示

原则：

- 当前会话 follow-up 默认优先看“本次证据”
- 历史材料仍保留为 fallback / 历史任务场景

---

## 5. 验证方式

至少覆盖：

1. `current_fetch` contract test
2. `current_artifact` contract test
3. injection-aware evidence rendering test
4. prompt assembly test
5. A7 summary writeback test

---

## 6. 非目标

1. 不把整份 report / confidence artifact 原文送进 orchestrator
2. 不做来源时间戳排序引擎
3. 不做跨 session evidence ranking
4. 不做 AIO 证据协议
