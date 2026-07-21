# 安利品牌圈层时间周期视角开发设计

日期：2026-07-09  
状态：开发设计稿  
适用入口：`/amwaychina`  
关联文档：

- `docs/amwaychina-cumulative-tracking-design-2026-06-22.md`
- `docs/amwaychina-data-structure-spec-2026-06-22.md`

## 1. 目标

把前台从“本轮 / 累计 / 对比”收敛为一个用户能直接理解的入口：选择时间周期，看这个周期内的品牌圈层图谱和报告。

前台只暴露：

- 最近一次
- 最近 7 天
- 最近 14 天
- 最近 30 天
- 自定义区间

系统内部仍然保留 run、snapshot、projection、report_input，用于追溯数据来源和生成图谱。用户不需要理解这些工程概念。

## 2. 非目标

- 不新增一套独立的分析工作流。
- 不把 A5 重新改成抽词、校准、对比模块。
- 不新增复杂趋势模型。
- 不在报告里扩展额外分析章节，只增加“变化 Top 5”的必要说明。
- 不影响普通品牌 Dashboard。

## 3. 用户旅程

1. 用户进入 `/amwaychina`。
2. 选择中心品牌：安利 / 安利中国 / 纽崔莱。
3. 选择时间周期，默认使用最近 30 天；如果最近 30 天没有数据，降级到最近一次。
4. 页面展示当前周期图谱。
5. 用户点击图谱节点，看节点和品牌的关系、平台分布、代表原文。
6. 用户查看报告，报告解释当前周期内 AI 如何理解品牌。
7. 如果存在可比上一周期，报告增加“相比上一周期变化 Top 5”。
8. 如果不存在可比上一周期，报告只提示本期作为后续追踪基线。

## 4. 周期计算规则

### 4.1 当前周期

| period_type | 当前周期 |
| --- | --- |
| `latest_run` | 最近一轮已完成采集 |
| `last_7_days` | 以最新完成 run 的 `completed_at` 为结束点，向前 7 天 |
| `last_14_days` | 以最新完成 run 的 `completed_at` 为结束点，向前 14 天 |
| `last_30_days` | 以最新完成 run 的 `completed_at` 为结束点，向前 30 天 |
| `custom` | 用户选择的 `start_at` 到 `end_at` |

所有周期只纳入：

- `status in ('completed', 'partial')`
- `include_in_cumulative = true`
- `completed_at` 落在周期内

### 4.2 上一周期

| period_type | 上一周期 |
| --- | --- |
| `latest_run` | 当前 run 的相邻上一轮已完成采集 |
| `last_7_days` | 当前周期前 7 天 |
| `last_14_days` | 当前周期前 14 天 |
| `last_30_days` | 当前周期前 30 天 |
| `custom` | 向前平移同等时长 |

自定义区间如果是完整自然月，上一周期按自然月平移。例如 `2026-01-01` 到 `2026-06-30`，上一周期为 `2025-07-01` 到 `2025-12-31`。

### 4.3 没有上一周期

没有上一周期 run 时：

- 不计算变化 Top 5。
- 报告写：`暂无可比上一周期，本期结果作为后续追踪基线。`

### 4.4 问题集变化

周期内所有 run 的 `question_signature` 形成集合：

- 当前周期集合 = `current_question_signatures`
- 上一周期集合 = `previous_question_signatures`

两个集合完全一致，视为同题库对比。

两个集合不一致，仍可计算变化 Top 5，但报告在该节前写：

`本期与上一周期的问题集不同，以下变化仅作参考，不能直接视为品牌联想的真实趋势。`

不增加其他报告分析逻辑。

## 5. 后端设计

### 5.1 复用现有结构

第一版不新增表，复用：

- `amway_circle_runs`
- `amway_circle_projections`
- `amway_circle_node_snapshots`
- `amway_circle_edge_snapshots`
- `amway_circle_evidence`
- `amway_circle_answers`
- `amway_circle_reports`

### 5.2 新增查询接口

```http
GET /api/v1/amwaychina/entities/{entity_id}/circle-period-view
```

Query：

```ts
period_type: 'latest_run' | 'last_7_days' | 'last_14_days' | 'last_30_days' | 'custom'
start_at?: string
end_at?: string
center_term?: string
```

返回：

```json
{
  "period_type": "last_30_days",
  "current_period": {
    "start_at": "2026-06-01T00:00:00Z",
    "end_at": "2026-06-30T23:59:59Z",
    "run_ids": ["..."],
    "run_count": 3
  },
  "previous_period": {
    "start_at": "2026-05-01T00:00:00Z",
    "end_at": "2026-05-31T23:59:59Z",
    "run_ids": ["..."],
    "run_count": 2
  },
  "question_set_changed": false,
  "comparison_notice": null,
  "projection": {},
  "change_top5": [],
  "report_input": {}
}
```

`previous_period` 可以为 `null`。

### 5.3 服务层

扩展 `AmwayCircleTrackingService`，不新增 service 类。

新增方法：

```py
async def get_period_view(
    self,
    entity_id: UUID,
    *,
    period_type: str,
    start_at: datetime | None,
    end_at: datetime | None,
    center_term: str | None,
) -> dict[str, Any]:
```

内部步骤：

1. 找到最新可用 run，确定 `as_of`。
2. 解析当前周期。
3. 解析上一周期。
4. 查询两个周期内的 run。
5. 基于当前周期 run 汇总周期 projection。
6. 如果上一周期存在，计算变化 Top 5。
7. 生成 `report_input`。

### 5.4 周期 projection 生成

第一版直接从已保存的 run projection / node snapshots 聚合。

节点聚合键优先级：

1. `lexicon_entity_id`
2. `canonical_name + entity_type`
3. `node_id`

节点指标：

- `mention_answer_count`：周期内求和
- `question_count`：周期内去重
- `platform_count`：周期内去重
- `evidence_count`：周期内求和
- `gravity_score`：按 `mention_answer_count` 加权平均
- `distance_score`：按 `mention_answer_count` 加权平均
- `track`：取最新 run 的 track；如果最新 run 没有该节点，取周期内最高证据节点的 track

### 5.5 变化 Top 5

只比较当前周期与上一周期共有或新增的节点。

变化分计算：

```text
change_score =
  abs(gravity_delta) * 0.45
  + abs(mention_delta_normalized) * 0.30
  + abs(platform_delta) * 0.15
  + track_changed_bonus * 0.10
```

输出最多 5 个：

- 新增
- 增强
- 减弱
- 轨道迁移
- 消失

如果上一周期不存在，不输出。

## 6. A5 报告输入

A5 只读 `report_input`。

```json
{
  "period": {},
  "previous_period": {},
  "question_set_changed": false,
  "comparison_notice": null,
  "current_projection_summary": {},
  "change_top5": [],
  "evidence_findings": [],
  "source_appendix": []
}
```

报告只增加一个变化段落：

- 有上一周期：写“相比上一周期变化 Top 5”。
- 有上一周期且题库不同：先写 `comparison_notice`。
- 无上一周期：写基线提示，不写变化 Top 5。

## 7. 前端设计

### 7.1 顶部控件

在 `/amwaychina` 头部增加时间周期选择：

- 最近一次
- 最近 7 天
- 最近 14 天
- 最近 30 天
- 自定义

默认选择最近 30 天。

### 7.2 图谱区域

图谱只显示当前周期 projection。

保留现有：

- 轨道 hover
- 节点点击浮层
- 风险聚焦
- 节点筛选
- HTML 导出

不显示 `run / cumulative / compare` 标签。

### 7.3 报告区域

报告标题显示周期：

```text
安利品牌圈层报告｜最近 30 天
```

如果有上一周期：

```text
对比周期：上一 30 天
```

如果题库变化，在变化 Top 5 前显示说明。

## 8. 导出

HTML 导出包含：

- 当前周期
- 上一周期说明
- 图谱快照
- 报告正文
- 变化 Top 5
- 证据附录

文件名：

```text
amway-circle-period-last-30-days-YYYY-MM-DD.html
amway-circle-period-custom-YYYY-MM-DD.html
```

## 9. 验收标准

### 9.1 后端

- 最近一次能返回最新 run 的周期图谱。
- 最近 7/14/30 天能聚合周期内多个 run。
- 自定义区间能正确找到当前周期和上一周期。
- 无上一周期时 `change_top5 = []`。
- 问题集变化时返回 `comparison_notice`。
- 权限仍沿用 `/amwaychina` 现有权限控制。

### 9.2 前端

- 用户能通过时间控件切换图谱。
- 用户不需要看到 run/cumulative/compare 概念。
- 无上一周期时报告不出现变化 Top 5。
- 问题集变化时报告只增加一句参考说明。
- 图谱导出和页面报告一致。

### 9.3 验证

- 后端 targeted tests：周期解析、上一周期推导、问题集变化、无上一周期。
- 前端 targeted tests：时间控件切换、报告提示、导出内容。
- 由独立 QA/PM/架构 Review 子智能体验收，不把主实现者自测当成最终结论。

## 10. 开发顺序

1. 后端 period view API。
2. 周期 run 查询与上一周期推导。
3. 周期 projection 聚合。
4. 变化 Top 5。
5. A5 `report_input` 对接。
6. 前端时间选择器。
7. 图谱和报告切换。
8. HTML 导出同步。
9. 独立子智能体验收。
