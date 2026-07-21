# 安利品牌圈层持续追踪数据结构设计

日期：2026-06-22  
状态：草案  
关联文档：`docs/amwaychina-cumulative-tracking-design-2026-06-22.md`  
适用入口：`/amwaychina`

## 1. 设计原则

1. `BrandIntelligenceRun` 继续承担工作流运行态：任务启动、进度、失败、A3/A4/A5 串联。
2. 安利持续追踪新增业务快照表：按轮沉淀题目、回答、抽取、校准、图谱、报告和导出。
3. 题库继续复用 `monitoring_question_sets`，实体词库继续复用 `amway_entity_lexicon_overrides`。
4. 前台只暴露时间周期视角；单轮、累计、对比都作为内部结构化快照能力，前端不重新计算远近、轨道和风险归因。
5. A5 只读取 `report_input` 写报告，抽取、校准、累计和对比在 A5 之前完成。
6. 所有结论必须能追溯到 `run_id -> answer_id -> mention_id/evidence_id -> 原文片段`。

## 1.1 Review 后的前台查询契约

用户不直接选择 `run / cumulative / compare`。前台只传时间周期：

```json
{
  "period_type": "latest_run | last_7_days | last_14_days | last_30_days | custom",
  "start_at": "2026-01-01T00:00:00Z",
  "end_at": "2026-06-30T23:59:59Z"
}
```

服务端负责推导：

- `current_period`：用户选择的当前周期。
- `previous_period`：相邻上一周期；没有可用 run 时为空。
- `question_set_changed`：当前周期与上一周期的 `question_signature` 是否不同。
- `comparison_notice`：仅供报告展示的一句提示。

报告规则保持最小：

- 没有 `previous_period`：不生成变化 Top 5，只提示本期作为基线。
- 有 `previous_period` 且题库一致：生成变化 Top 5。
- 有 `previous_period` 但题库不同：生成变化 Top 5，并在该节前声明仅作参考。

## 2. 现有结构复用

### 2.1 `brand_intelligence_runs`

用途：工作流层运行态。

继续保留：

- `analysis_mode = brand_association_circle`
- `input_scope.uploaded_questions`
- `input_scope.center_terms`
- `sample_scope`
- `output_refs`
- `status / stage / progress`

新增关联建议：

- `output_refs.amway_circle_run_id`
- `output_refs.latest_projection_id`
- `output_refs.latest_report_id`

### 2.2 `monitoring_question_sets`

用途：题库历史。

继续保留：

- `source = amwaychina_upload`
- `questions`
- `question_count`
- `extra_metadata.center_terms`
- `extra_metadata.source_file_name`

新增 `extra_metadata` 建议：

```json
{
  "question_set_version": "uploaded_amway_gravity_circle_v1",
  "question_schema_version": "amway_question_v2",
  "default_platforms": ["DeepSeek", "Kimi", "豆包", "元宝"],
  "strategy_scope": ["有健康", "有陪伴", "有保障", "有价值"]
}
```

### 2.3 `amway_entity_lexicon_overrides`

用途：实体词库编辑覆盖层。

继续保留：

- `lexicon_entity_id`
- `canonical_name`
- `entity_type`
- `aliases`
- `graph_policy`
- `review_status`
- `is_deleted`

新增使用方式：

- 抽取时以默认 ontology + override 合并后的词库为准。
- 每一轮 run 保存 `lexicon_version` 和 `lexicon_hash`，保证后续复盘知道当时使用了哪版词库。

## 3. 新增表总览

建议新增 9 张表：

1. `amway_circle_runs`：每轮业务快照主表。
2. `amway_circle_answers`：每轮平台回答归档。
3. `amway_circle_entity_mentions`：逐条回答抽取出的实体命中。
4. `amway_circle_evidence`：可引用证据片段。
5. `amway_circle_node_snapshots`：本轮校准后的图谱节点。
6. `amway_circle_edge_snapshots`：本轮校准后的图谱关系。
7. `amway_circle_projections`：前端读取的图谱 projection。
8. `amway_circle_reports`：A5 报告版本。
9. `amway_circle_exports`：HTML/PDF/JSON 导出记录。

可选新增 1 张表：

10. `amway_circle_runtime_events`：抓取和抽取过程中的动态事件。

## 4. 表结构

### 4.1 `amway_circle_runs`

一轮安利圈层采集与分析的业务快照。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `entity_id` | UUID | 是 | 安利实体 |
| `organization_id` | UUID | 否 | 组织，用于权限和后台管理 |
| `created_by_user_id` | UUID | 否 | 启动人 |
| `brand_intelligence_run_id` | UUID | 否 | 关联工作流运行态 |
| `analysis_task_id` | UUID | 否 | 关联任务 |
| `question_set_id` | UUID | 否 | 关联题库 |
| `run_sequence` | Integer | 是 | 同一实体下第几轮 |
| `run_label` | String(160) | 是 | 展示名，例如 `2026-06-22 四平台采集` |
| `status` | String(32) | 是 | `pending/running/partial/completed/failed/cancelled` |
| `center_term` | String(80) | 是 | 当前中心品牌，单次图谱中心只能是一个品牌 |
| `center_terms` | JSON | 是 | 可选中心品牌组 |
| `platforms_requested` | JSON | 是 | 计划抓取平台 |
| `platforms_completed` | JSON | 是 | 成功返回平台 |
| `question_count` | Integer | 是 | 题目数 |
| `expected_answer_count` | Integer | 是 | 预计回答数 |
| `valid_answer_count` | Integer | 是 | 有效回答数 |
| `failed_answer_count` | Integer | 是 | 失败回答数 |
| `answer_scope` | JSON | 是 | 平台、题目、失败原因汇总 |
| `question_signature` | String(80) | 是 | 题库 hash |
| `lexicon_version` | String(80) | 是 | 实体词库版本 |
| `lexicon_hash` | String(80) | 是 | 实体词库 hash |
| `extraction_version` | String(80) | 是 | 抽取逻辑版本 |
| `calibration_version` | String(80) | 是 | 校准逻辑版本 |
| `projection_version` | String(80) | 是 | projection schema 版本 |
| `include_in_cumulative` | Boolean | 是 | 是否进入累计 |
| `excluded_reason` | Text | 否 | 排除累计原因 |
| `started_at` | DateTime | 否 | 开始时间 |
| `completed_at` | DateTime | 否 | 完成时间 |
| `created_at` | DateTime | 是 | 创建时间 |
| `updated_at` | DateTime | 是 | 更新时间 |

索引：

- `ix_amway_circle_runs_entity_created(entity_id, created_at)`
- `ix_amway_circle_runs_entity_sequence(entity_id, run_sequence)`
- `ix_amway_circle_runs_status(status)`
- `ix_amway_circle_runs_question_set(question_set_id)`
- `uq_amway_circle_runs_entity_sequence(entity_id, run_sequence)`
- `uq_amway_circle_runs_bi_run(brand_intelligence_run_id)`

### 4.2 `amway_circle_answers`

一轮里每个平台对每道题的回答归档。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | 关联 `amway_circle_runs` |
| `entity_id` | UUID | 是 | 冗余实体，便于查询 |
| `question_set_id` | UUID | 否 | 题库 |
| `question_id` | String(120) | 是 | 上传题目 ID |
| `question_hash` | String(80) | 是 | 题干标准化 hash，用于跨轮识别同一道题 |
| `question_index` | Integer | 是 | 题目顺序 |
| `question_text` | Text | 是 | 题目原文 |
| `question_metadata` | JSON | 是 | 人群、场景、探针、战略词等标签 |
| `platform` | String(40) | 是 | DeepSeek/Kimi/豆包/元宝 |
| `platform_model` | String(120) | 否 | 平台返回的模型版本，抓不到则为空 |
| `fetch_agent_version` | String(80) | 是 | 本轮抓取实现版本 |
| `fetch_status` | String(32) | 是 | `success/failed/timeout/skipped` |
| `answer_text` | Text | 否 | 回答全文 |
| `answer_excerpt` | Text | 否 | 展示摘要 |
| `answer_hash` | String(80) | 否 | 回答 hash |
| `mentions_center` | Boolean | 是 | 是否提到当前中心品牌 |
| `center_context_type` | String(32) | 是 | `direct/nearby/implicit/none` |
| `answer_quality` | String(32) | 是 | `valid/empty/refused/error/duplicate` |
| `raw_payload` | JSON | 否 | A4 原始抓取结构 |
| `error_code` | String(80) | 否 | 失败码 |
| `error_message` | Text | 否 | 失败信息 |
| `fetched_at` | DateTime | 否 | 抓取时间 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_circle_answers_run_platform(circle_run_id, platform)`
- `ix_amway_circle_answers_run_question(circle_run_id, question_id)`
- `ix_amway_circle_answers_run_question_hash(circle_run_id, question_hash)`
- `ix_amway_circle_answers_entity_platform(entity_id, platform)`
- `uq_amway_circle_answers_run_question_platform(circle_run_id, question_id, platform)`

`question_metadata` 标准结构：

```json
{
  "audience_segment": "retiring_midlife",
  "core_anxiety": "circle_shrink_after_retirement",
  "life_scene": "retirement_transition",
  "opportunity_point": "good_relationship",
  "probe_type": "non_branded_scene",
  "mentions_amway": "no",
  "strategy_terms": ["有陪伴", "良好关系"],
  "center_terms": ["安利"],
  "question_set_version": "uploaded_amway_gravity_circle_v1",
  "metadata_status": "uploaded"
}
```

### 4.3 `amway_circle_entity_mentions`

每条回答里抽取出的实体命中。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | 关联 run |
| `answer_id` | UUID | 是 | 关联回答 |
| `entity_id` | UUID | 是 | 品牌实体 |
| `lexicon_entity_id` | String(120) | 否 | 词库实体 ID |
| `canonical_name` | String(160) | 是 | 标准名 |
| `entity_type` | String(80) | 是 | Brand/Solution/Risk/Strategy 等 |
| `source_type` | String(32) | 是 | `lexicon/default/custom/llm_candidate` |
| `matched_text` | String(240) | 是 | 命中文本 |
| `matched_alias` | String(240) | 否 | 命中的别名 |
| `context_text` | Text | 是 | 命中上下文 |
| `evidence_text` | Text | 是 | 可引用证据 |
| `relation_type` | String(80) | 是 | 关系类型 |
| `amway_anchor` | String(32) | 是 | `direct/nearby/question_only/none` |
| `sentiment_context` | String(32) | 是 | `positive/neutral/clarification/risk_prompt/negative/unrelated` |
| `risk_context` | String(32) | 否 | `none/positive_clarification/risk_warning/negative_binding/unrelated_hit` |
| `confidence_score` | Float | 是 | 0-1 |
| `extractor_version` | String(80) | 是 | 抽取版本 |
| `dedupe_key` | String(160) | 是 | 去重键 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_mentions_run_entity(circle_run_id, canonical_name)`
- `ix_amway_mentions_answer(answer_id)`
- `ix_amway_mentions_entity_type(entity_type)`
- `ix_amway_mentions_risk_context(risk_context)`
- `uq_amway_mentions_dedupe(circle_run_id, answer_id, dedupe_key)`
- `uq_amway_mentions_id_run(id, circle_run_id)`
- FK：`(answer_id, circle_run_id)` 指向同一 run 的 answer。

重要规则：

- `直销/KOC/ABO/安利事业机会` 进入内部体系实体或事业实体，默认 `risk_context = none`。
- 只有 `risk_warning` 和 `negative_binding` 可以进入风险关系图。
- `positive_clarification` 进入信任修复证据。
- `unrelated_hit` 保留为抽取记录，校准时从图谱结论里排除。

### 4.4 `amway_circle_evidence`

被图谱、报告、节点浮层引用的证据片段。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | 关联 run |
| `answer_id` | UUID | 是 | 关联回答 |
| `mention_id` | UUID | 否 | 关联实体命中 |
| `evidence_ref` | String(80) | 是 | 展示引用 ID，例如 `ev_20260622_0016` |
| `platform` | String(40) | 是 | 平台 |
| `question_id` | String(120) | 是 | 题目 ID |
| `question_text` | Text | 是 | 题目原文 |
| `quote_text` | Text | 是 | 原文片段 |
| `quote_type` | String(40) | 是 | `support/risk/competitor/clarification/neutral` |
| `entity_names` | JSON | 是 | 涉及实体 |
| `strategy_terms` | JSON | 是 | 涉及战略词 |
| `scenario_tags` | JSON | 是 | 场景标签 |
| `source_rank` | Integer | 是 | 同节点证据排序 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_evidence_run_ref(circle_run_id, evidence_ref)`
- `ix_amway_evidence_answer(answer_id)`
- `ix_amway_evidence_platform(platform)`
- `ix_amway_evidence_quote_type(quote_type)`
- `uq_amway_evidence_run_ref(circle_run_id, evidence_ref)`
- FK：`(answer_id, circle_run_id)` 指向同一 run 的 answer。
- FK：`(mention_id, circle_run_id)` 指向同一 run 的 mention。

### 4.5 `amway_circle_node_snapshots`

本轮校准后的图谱节点。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | 关联 run |
| `entity_id` | UUID | 是 | 品牌实体 |
| `node_id` | String(160) | 是 | 稳定节点 ID |
| `lexicon_entity_id` | String(120) | 否 | 词库实体 ID，用于跨轮追踪改名后的同一实体 |
| `canonical_name` | String(160) | 是 | 节点名 |
| `entity_type` | String(80) | 是 | 实体类型 |
| `source_type` | String(32) | 是 | `strategy_term/answer_entity/risk/competitor` |
| `track` | String(32) | 是 | `stable/opportunity/watch/risk` |
| `track_reason` | Text | 是 | 进入轨道原因 |
| `mention_answer_count` | Integer | 是 | 提及回答数 |
| `question_count` | Integer | 是 | 覆盖题目数 |
| `platform_count` | Integer | 是 | 覆盖平台数 |
| `evidence_count` | Integer | 是 | 证据数 |
| `center_anchor_count` | Integer | 是 | 安利上下文命中数 |
| `amway_anchor_ratio` | Float | 是 | 安利上下文占比 |
| `gravity_score` | Float | 是 | 越高越贴近 |
| `distance_score` | Float | 是 | 越高越远 |
| `stability_score` | Float | 是 | 本轮稳定性 |
| `risk_score` | Float | 是 | 风险强度 |
| `position_x` | Float | 是 | 前端图谱坐标 |
| `position_y` | Float | 是 | 前端图谱坐标 |
| `node_size` | Float | 是 | 节点大小 |
| `display_priority` | Integer | 是 | 前端默认显示优先级 |
| `platform_summary` | JSON | 是 | 平台统计 |
| `question_summary` | JSON | 是 | 问题统计 |
| `evidence_refs` | JSON | 是 | 证据 ID。累计/对比 projection 使用 `circle_run_id:evidence_ref` |
| `calibration_payload` | JSON | 是 | 校准细节 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_nodes_run_track(circle_run_id, track)`
- `ix_amway_nodes_run_type(circle_run_id, entity_type)`
- `ix_amway_nodes_run_lexicon(circle_run_id, lexicon_entity_id)`
- `ix_amway_nodes_run_priority(circle_run_id, display_priority)`
- `uq_amway_nodes_run_node(circle_run_id, node_id)`
- `uq_amway_nodes_id_run(id, circle_run_id)`

### 4.6 `amway_circle_edge_snapshots`

本轮校准后的关系边。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | 关联 run |
| `edge_id` | String(180) | 是 | 稳定边 ID |
| `source_node_id` | String(160) | 是 | 起点 |
| `target_node_id` | String(160) | 是 | 终点 |
| `relation_type` | String(80) | 是 | `associated_with/competes_with/risk_of/supports_strategy` |
| `relation_label` | String(160) | 是 | 前端展示标签 |
| `strength_score` | Float | 是 | 关系强度 |
| `risk_context` | String(32) | 否 | 风险上下文 |
| `evidence_count` | Integer | 是 | 证据数 |
| `platform_count` | Integer | 是 | 平台数 |
| `question_count` | Integer | 是 | 问题数 |
| `evidence_refs` | JSON | 是 | 证据 ID。累计/对比 projection 使用 `circle_run_id:evidence_ref` |
| `edge_payload` | JSON | 是 | 关系解释 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_edges_run_source(circle_run_id, source_node_id)`
- `ix_amway_edges_run_target(circle_run_id, target_node_id)`
- `ix_amway_edges_relation(relation_type)`
- `uq_amway_edges_run_edge(circle_run_id, edge_id)`
- FK：`(circle_run_id, source_node_id)` 与 `(circle_run_id, target_node_id)` 必须指向同一 run 的 node snapshot。

### 4.7 `amway_circle_projections`

前端、报告和导出读取的完整 projection。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `entity_id` | UUID | 是 | 安利实体 |
| `circle_run_id` | UUID | 否 | 单轮 projection 关联 run |
| `base_run_id` | UUID | 否 | 对比基准 run |
| `target_run_id` | UUID | 否 | 对比目标 run |
| `as_of_run_id` | UUID | 否 | 累计 projection 截止到哪一轮 |
| `projection_scope` | String(32) | 是 | `run/cumulative/compare` |
| `projection_version` | String(80) | 是 | schema 版本 |
| `status` | String(32) | 是 | `ready/building/failed` |
| `is_latest` | Boolean | 是 | 当前实体下该 scope 的最新 projection |
| `source_run_ids` | JSON | 是 | 本 projection 使用的 run 清单 |
| `source_run_count` | Integer | 是 | 本 projection 使用的 run 数 |
| `source_run_hash` | String(80) | 是 | run 清单 hash，用于复盘和防重复 |
| `sample_scope` | JSON | 是 | 样本口径 |
| `association_circle_projection` | JSON | 是 | 前端图谱结构 |
| `report_input` | JSON | 是 | A5 报告输入 |
| `compare_summary` | JSON | 否 | 对比摘要 |
| `data_quality` | JSON | 是 | 样本不足、平台失败等质量信息 |
| `built_at` | DateTime | 是 | 生成时间 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_projections_entity_scope(entity_id, projection_scope, is_latest)`
- `ix_amway_projections_run(circle_run_id)`
- `ix_amway_projections_as_of(as_of_run_id)`
- `ix_amway_projections_compare(base_run_id, target_run_id)`
- `uq_amway_latest_projection_scope(entity_id, projection_scope)`，仅约束 `is_latest = true`
- `uq_amway_projection_source_hash(entity_id, projection_scope, projection_version, source_run_hash)`，仅约束非空 `source_run_hash`
- FK：`circle_run_id/base_run_id/target_run_id/as_of_run_id` 与 `entity_id` 组合必须指向同一品牌实体下的 run。

`association_circle_projection` 标准结构：

```json
{
  "schema_version": "amway_circle_projection_v2",
  "view_scope": "cumulative",
  "entity_id": "faf399ab-4d43-40dc-86fe-7847fd04947f",
  "center": {
    "center_term": "安利",
    "center_terms": ["安利", "安利中国", "纽崔莱"],
    "display_name": "安利"
  },
  "sample_scope": {
    "run_count": 5,
    "question_count": 32,
    "valid_answer_count": 580,
    "platforms": ["DeepSeek", "Kimi", "豆包", "元宝"],
    "latest_run_id": "..."
  },
  "tracks": [
    {
      "track_id": "stable",
      "label": "稳定轨",
      "meaning": "已经被平台稳定带回安利的资产",
      "node_count": 13
    }
  ],
  "nodes": [],
  "edges": [],
  "risk_cluster": {
    "node_count": 8,
    "top_nodes": [],
    "entry_node_id": "risk_cluster"
  },
  "platform_summary": {},
  "strategy_validation": {},
  "compare_summary": null,
  "updated_at": "2026-06-22T10:42:00Z"
}
```

### 4.8 `amway_circle_reports`

A5 生成的报告版本。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `entity_id` | UUID | 是 | 安利实体 |
| `projection_id` | UUID | 是 | 关联 projection |
| `circle_run_id` | UUID | 否 | 单轮报告关联 run |
| `report_scope` | String(32) | 是 | `run/cumulative/compare` |
| `report_version` | String(80) | 是 | 报告模板版本 |
| `title` | String(240) | 是 | 标题 |
| `status` | String(32) | 是 | `draft/ready/failed` |
| `markdown_body` | Text | 是 | Markdown 正文 |
| `structured_body` | JSON | 是 | 分章节结构 |
| `source_report_input` | JSON | 是 | A5 输入快照 |
| `source_projection_hash` | String(80) | 是 | projection hash |
| `created_by_user_id` | UUID | 否 | 触发人 |
| `created_at` | DateTime | 是 | 创建时间 |
| `updated_at` | DateTime | 是 | 更新时间 |

索引：

- `ix_amway_reports_entity_scope(entity_id, report_scope)`
- `ix_amway_reports_projection(projection_id)`
- `ix_amway_reports_run(circle_run_id)`

### 4.9 `amway_circle_exports`

导出记录。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `entity_id` | UUID | 是 | 安利实体 |
| `projection_id` | UUID | 是 | projection |
| `report_id` | UUID | 否 | 报告 |
| `circle_run_id` | UUID | 否 | run |
| `export_type` | String(32) | 是 | `html/pdf/json/xlsx` |
| `export_scope` | String(32) | 是 | `run/cumulative/compare` |
| `file_name` | String(255) | 是 | 文件名 |
| `storage_path` | Text | 是 | 存储路径 |
| `content_hash` | String(80) | 是 | 文件 hash |
| `include_graph` | Boolean | 是 | 是否包含图谱 |
| `include_answer_appendix` | Boolean | 是 | 是否包含答案附录 |
| `created_by_user_id` | UUID | 否 | 导出人 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_exports_entity_created(entity_id, created_at)`
- `ix_amway_exports_projection(projection_id)`

### 4.10 `amway_circle_runtime_events`

可选表。用于动态图谱过程展示，也便于排查 A4/抽取过程。

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `id` | UUID | 是 | 主键 |
| `circle_run_id` | UUID | 是 | run |
| `sequence` | Integer | 是 | 顺序 |
| `event_type` | String(80) | 是 | `answer_saved/entity_extracted/node_candidate/calibration_started/projection_ready/report_ready` |
| `stage` | String(80) | 是 | `a4/extraction/calibration/a5/export` |
| `payload` | JSON | 是 | 事件内容 |
| `created_at` | DateTime | 是 | 创建时间 |

索引：

- `ix_amway_events_run_sequence(circle_run_id, sequence)`
- `ix_amway_events_type(event_type)`

## 5. 枚举定义

### 5.1 Run Status

```ts
type AmwayCircleRunStatus =
  | 'pending'
  | 'running'
  | 'partial'
  | 'completed'
  | 'failed'
  | 'cancelled';
```

### 5.2 Projection Scope

```ts
type AmwayProjectionScope = 'run' | 'cumulative' | 'compare';
```

### 5.3 Track

```ts
type AmwayOrbitTrack = 'stable' | 'opportunity' | 'watch' | 'risk';
```

### 5.4 Entity Type

实体类型来自 ontology，前端至少需要识别：

```ts
type AmwayEntityType =
  | 'Brand'
  | 'Brand_Strategy'
  | 'Solution'
  | 'ProductFeature'
  | 'HealthyLifestyle'
  | 'SubscriptionPlan'
  | 'TransformationStory'
  | 'Regulation'
  | 'Certification'
  | 'Research'
  | 'Authority'
  | 'Competitor'
  | 'Risk'
  | 'Scene'
  | 'Audience';
```

### 5.5 Risk Context

```ts
type AmwayRiskContext =
  | 'none'
  | 'positive_clarification'
  | 'risk_warning'
  | 'negative_binding'
  | 'unrelated_hit';
```

### 5.6 Change Type

```ts
type AmwayNodeChangeType =
  | 'strengthened'
  | 'weakened'
  | 'new'
  | 'dropped'
  | 'track_moved'
  | 'stable';
```

## 6. 前端 TypeScript 结构

### 6.1 Run 列表

```ts
export interface AmwayCircleRunSummary {
  id: string;
  entity_id: string;
  run_sequence: number;
  run_label: string;
  status: AmwayCircleRunStatus;
  center_term: string;
  platforms_requested: string[];
  platforms_completed: string[];
  question_count: number;
  expected_answer_count: number;
  valid_answer_count: number;
  failed_answer_count: number;
  include_in_cumulative: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  latest_projection_id?: string | null;
  latest_report_id?: string | null;
}
```

### 6.2 Projection 响应

```ts
export interface AmwayCircleProjectionResponse {
  id: string;
  entity_id: string;
  projection_scope: AmwayProjectionScope;
  circle_run_id?: string | null;
  base_run_id?: string | null;
  target_run_id?: string | null;
  status: 'ready' | 'building' | 'failed';
  sample_scope: AmwaySampleScope;
  association_circle_projection: AmwayAssociationCircleProjection;
  compare_summary?: AmwayCompareSummary | null;
  data_quality: AmwayDataQuality;
  built_at: string;
}
```

### 6.3 图谱节点

```ts
export interface AmwayCircleNode {
  node_id: string;
  canonical_name: string;
  display_name: string;
  entity_type: AmwayEntityType;
  source_type: 'strategy_term' | 'answer_entity' | 'risk' | 'competitor';
  track: AmwayOrbitTrack;
  track_reason: string;
  mention_answer_count: number;
  question_count: number;
  platform_count: number;
  evidence_count: number;
  center_anchor_count: number;
  amway_anchor_ratio: number;
  gravity_score: number;
  distance_score: number;
  stability_score: number;
  risk_score: number;
  position: {
    x: number;
    y: number;
  };
  node_size: number;
  display_priority: number;
  platform_summary: Record<string, AmwayNodePlatformStats>;
  evidence_refs: string[];
  change?: AmwayNodeChange | null;
}
```

### 6.4 节点变化

```ts
export interface AmwayNodeChange {
  change_type: AmwayNodeChangeType;
  gravity_delta: number;
  distance_delta: number;
  mention_delta: number;
  platform_delta: number;
  track_from?: AmwayOrbitTrack | null;
  track_to?: AmwayOrbitTrack | null;
  explanation: string;
  evidence_refs: string[];
}
```

### 6.5 节点浮层

```ts
export interface AmwayNodeInsight {
  node_id: string;
  title: string;
  role_label: string;
  relationship_to_center: string;
  brand_meaning: string;
  evidence_summary: {
    question_count: number;
    answer_count: number;
    platform_count: number;
    top_platforms: Array<{ platform: string; count: number; tendency: string }>;
  };
  representative_quotes: AmwayEvidenceQuote[];
  next_action: string;
}
```

### 6.6 证据

```ts
export interface AmwayEvidenceQuote {
  evidence_ref: string;
  platform: string;
  question_id: string;
  question_text: string;
  quote_text: string;
  quote_type: 'support' | 'risk' | 'competitor' | 'clarification' | 'neutral';
  entity_names: string[];
  strategy_terms: string[];
}
```

## 7. `report_input` 标准结构

A5 只读取 `report_input`。

```json
{
  "schema_version": "amway_report_input_v2",
  "view_scope": "cumulative",
  "entity": {
    "entity_id": "...",
    "center_term": "安利",
    "center_terms": ["安利", "安利中国", "纽崔莱"]
  },
  "question_scope": {
    "question_set_id": "...",
    "question_count": 32,
    "question_strategy_distribution": {
      "有健康": 8,
      "有陪伴": 8,
      "有保障": 8,
      "有价值": 8
    }
  },
  "platform_scope": {
    "platforms": ["DeepSeek", "Kimi", "豆包", "元宝"],
    "valid_answer_count": 116,
    "failed_answer_count": 12,
    "platform_status": {}
  },
  "association_map": {
    "top_stable_nodes": [],
    "top_opportunity_nodes": [],
    "top_watch_nodes": []
  },
  "strategy_validation": {
    "有健康": {
      "status": "validated",
      "lead_nodes": ["纽崔莱", "体重管理", "营养补充"],
      "gap_story": "被接住，但主要停留在产品层。",
      "evidence_refs": []
    }
  },
  "risk_summary": {
    "risk_nodes": [],
    "clarification_evidence": [],
    "negative_binding_evidence": [],
    "risk_warning_evidence": []
  },
  "competitor_summary": {
    "competitor_nodes": [],
    "replacement_scenarios": []
  },
  "compare_summary": {
    "top_changes": []
  },
  "evidence_findings": [],
  "source_appendix": []
}
```

## 8. API 数据结构

### 8.1 历史 run

```http
GET /api/v1/amwaychina/entities/{entity_id}/circle-runs?limit=30
```

响应：

```json
{
  "runs": [],
  "total": 5
}
```

### 8.2 Projection

```http
GET /api/v1/amwaychina/entities/{entity_id}/circle-projection?scope=cumulative
GET /api/v1/amwaychina/entities/{entity_id}/circle-projection?scope=run&run_id=...
GET /api/v1/amwaychina/entities/{entity_id}/circle-projection?scope=compare&base_run_id=...&target_run_id=...
```

响应使用 `AmwayCircleProjectionResponse`。

### 8.3 节点详情

```http
GET /api/v1/amwaychina/entities/{entity_id}/circle-node-insight?projection_id=...&node_id=...
```

响应使用 `AmwayNodeInsight`。

### 8.4 生成报告

```http
POST /api/v1/amwaychina/entities/{entity_id}/reports
```

请求：

```json
{
  "projection_id": "...",
  "report_scope": "compare"
}
```

响应：

```json
{
  "report_id": "...",
  "status": "ready",
  "title": "安利品牌圈层持续追踪报告",
  "markdown_body": "...",
  "structured_body": {}
}
```

### 8.5 导出

```http
POST /api/v1/amwaychina/entities/{entity_id}/exports
```

请求：

```json
{
  "projection_id": "...",
  "report_id": "...",
  "export_type": "html",
  "include_graph": true,
  "include_answer_appendix": true
}
```

响应：

```json
{
  "export_id": "...",
  "download_url": "...",
  "file_name": "amway-circle-cumulative-report-2026-06-22.html"
}
```

## 9. 动态事件结构

用于抓取和抽取过程的前端动效。

```json
{
  "event_id": "evt_000128",
  "circle_run_id": "...",
  "sequence": 128,
  "event_type": "entity_extracted",
  "stage": "extraction",
  "payload": {
    "answer_id": "...",
    "question_id": "Q08",
    "platform": "豆包",
    "signals": [
      {
        "canonical_name": "社群陪伴",
        "entity_type": "Brand_Strategy",
        "relation_type": "supports_strategy",
        "amway_anchor": "direct",
        "risk_context": "none",
        "evidence_text": "..."
      }
    ]
  },
  "created_at": "2026-06-22T10:18:00Z"
}
```

事件类型：

- `run_started`
- `question_loaded`
- `answer_saved`
- `answer_failed`
- `entity_extracted`
- `candidate_node_updated`
- `calibration_started`
- `projection_ready`
- `report_ready`
- `export_ready`

## 10. 累计与对比计算输入

### 10.1 累计输入

累计 aggregation 读取：

- `amway_circle_runs` 中 `include_in_cumulative = true` 的成功或部分成功 run。
- 每个 run 的 `amway_circle_node_snapshots`。
- 每个 run 的 `amway_circle_edge_snapshots`。
- 每个 run 的 `amway_circle_evidence`。

### 10.2 累计输出

输出到 `amway_circle_projections`：

- `projection_scope = cumulative`
- `circle_run_id = null`
- `association_circle_projection`
- `report_input`

### 10.3 对比输入

对比 aggregation 读取：

- `base_run_id`
- `target_run_id`
- 两轮 node snapshots
- 两轮 evidence

### 10.4 对比输出

输出到 `amway_circle_projections`：

- `projection_scope = compare`
- `base_run_id`
- `target_run_id`
- `compare_summary`
- 节点 `change` 字段

## 11. 数据保留与排除累计

历史 run 默认保留。

管理员可以把某轮标记为排除累计：

```json
{
  "include_in_cumulative": false,
  "excluded_reason": "本轮 Kimi 和 DeepSeek 大面积失败，样本口径不足。"
}
```

排除累计后：

- 单轮 run 仍可查看。
- 原始回答、抽取、报告仍保留。
- 累计 projection 下次重建时跳过该 run。

## 12. 第一版落地顺序

### Step 1：建主表和回答归档

- `amway_circle_runs`
- `amway_circle_answers`
- `amway_circle_runtime_events`

### Step 2：建抽取和证据表

- `amway_circle_entity_mentions`
- `amway_circle_evidence`

### Step 3：建图谱快照表

- `amway_circle_node_snapshots`
- `amway_circle_edge_snapshots`
- `amway_circle_projections`

### Step 4：建报告和导出表

- `amway_circle_reports`
- `amway_circle_exports`

### Step 5：补 API 和前端类型

- `AmwayCircleRunSummary`
- `AmwayCircleProjectionResponse`
- `AmwayCircleNode`
- `AmwayNodeInsight`
- `AmwayEvidenceQuote`

## 13. 开发验收

1. 上传同一批 32 题后，每轮都有独立 `amway_circle_runs` 记录。
2. 32 x 4 的抓取结果能在 `amway_circle_answers` 中按平台和题目查到。
3. 每条实体命中能追溯到回答和证据片段。
4. 风险节点只由上下文判断进入风险关系图。
5. 单轮 projection、累计 projection、对比 projection 能分别读取。
6. A5 报告输入只来自 `amway_circle_projections.report_input`。
7. HTML 导出能绑定对应 projection 和 report。
8. 前端图谱不自行重算轨道、距离和节点大小。
