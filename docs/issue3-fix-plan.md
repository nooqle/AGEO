# Issue #3 技术修改计划：报告质量修复

> **作者**: Martin Fowler (架构师)
> **日期**: 2026-02-22
> **状态**: 实施方案（等待开发 pick up）

---

## 问题总结

A5 报告存在三个质量缺陷：
1. 平台分析章节 (`platform_analysis`) 为空
2. 竞品对比表 (`competitor_deep_analysis`) 为空
3. 优化建议 (`actionable_recommendations`) 泛泛而谈

根因已在 `docs/arch-analysis-issues.md` 中分析，本文档聚焦**具体修改方案**。

---

## 修改清单

### 修改 1: 竞品指标计算提前 (P0, 核心修复)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`

**问题**: `_calculate_competitor_metrics()` 在第 277 行调用（LLM 调用之后），但 LLM prompt 在第 192 行就已发出，导致 LLM 拿不到竞品的量化数据。

**当前调用顺序** (a5_analytics_node 内):
```
L120: metrics = _calculate_metrics(...)
L192: user_content = _build_a5_user_content(brand_profile, metrics, fetch_results, competitors, ...)
L199: response = await call_llm_streaming(...)  ← LLM 调用
L277: competitor_metrics = _calculate_competitor_metrics(fetch_results, competitors)  ← 太晚了！
```

**修改方案**: 将 `_calculate_competitor_metrics()` 提前到 LLM 调用之前，并传入 `_build_a5_user_content()`。

**具体改动**:

#### 步骤 1a: 提前计算竞品指标

在 `a5_analytics_node()` 中，第 120 行（`_calculate_metrics` 调用）之后，立即计算竞品指标：

```python
# 当前 L120:
metrics = _calculate_metrics(fetch_results, brand_profile)

# 新增（在 L120 之后，L122 之前）:
competitor_metrics = _calculate_competitor_metrics(fetch_results, competitors)
```

#### 步骤 1b: 修改 `_build_a5_user_content` 签名和调用

**文件**: `nodes_a5.py`, L913 函数签名 + L192 调用处

函数签名新增参数：
```python
def _build_a5_user_content(
    brand_profile: dict,
    metrics: dict,
    fetch_results: list,
    competitors: list,
    marketing_personas: dict | None = None,
    previous_snapshot: dict | None = None,
    competitor_metrics: list | None = None,  # 新增
) -> str:
```

调用处（L192-196）相应修改：
```python
user_content = _build_a5_user_content(
    brand_profile, metrics, fetch_results, competitors,
    marketing_personas=marketing_personas,
    previous_snapshot=previous_snapshot_data,
    competitor_metrics=competitor_metrics,  # 新增
)
```

#### 步骤 1c: 删除 L277 原有的重复调用

```python
# 删除 L277:
# competitor_metrics = _calculate_competitor_metrics(fetch_results, competitors)
```

此时 `competitor_metrics` 变量已在 L120 之后定义，后续使用（L294 snapshot 写入、L380 artifact 传递）不受影响。

---

### 修改 2: 竞品数据在 prompt 中结构化展示 (P0)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`, `_build_a5_user_content()` 函数

**当前代码** (L957-963):
```python
if competitors:
    comp_summary = [
        {"name": c.get("name", ""), "relevance_score": c.get("relevance_score", 0)}
        for c in competitors[:8]
    ]
    sections.append(f"## 竞品数据\n{json.dumps(comp_summary, ensure_ascii=False, indent=2)}")
```

**问题**: 只传了竞品名称和 relevance_score，没有传 mention_rate、sentiment 等真实数据。

**修改方案**: 替换为结构化竞品对比表，使用修改 1 中传入的 `competitor_metrics`。

```python
# 替换 L957-963
if competitor_metrics:
    # 构建可读的竞品对比表
    brand_mention_rate = metrics.get("mention_rate", 0)
    comp_lines = [
        "## 竞品量化数据",
        f"（本品牌提及率: {brand_mention_rate:.1%}）",
        "",
        "| 竞品名称 | 提及率 | 与本品牌对比 | 情感倾向 | 出现排名 |",
        "|---------|--------|------------|---------|---------|",
    ]
    for cm in competitor_metrics:
        name = cm.get("name", "")
        mr = cm.get("mention_rate", 0)
        sentiment = cm.get("sentiment", 0)
        ranking = cm.get("avg_ranking", 0)
        vs = "高于" if mr > brand_mention_rate else ("低于" if mr < brand_mention_rate else "持平")
        sent_label = "正面" if sentiment > 0.2 else ("负面" if sentiment < -0.2 else "中性")
        comp_lines.append(
            f"| {name} | {mr:.1%} | {vs} | {sent_label}({sentiment:+.2f}) | #{ranking} |"
        )
    sections.append("\n".join(comp_lines))
elif competitors:
    # fallback: 如果 competitor_metrics 为空但有 competitors 列表
    comp_summary = [
        {"name": c.get("name", ""), "relevance_score": c.get("relevance_score", 0)}
        for c in competitors[:8]
    ]
    sections.append(f"## 竞品数据\n{json.dumps(comp_summary, ensure_ascii=False, indent=2)}")
```

---

### 修改 3: platform_breakdown 格式化为可读表格 (P0)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`, `_build_a5_user_content()` L934-943

**当前代码**:
```python
sections.append(
    f"## 核心指标\n"
    ...
    f"- 平台表现:\n{json.dumps(metrics.get('platform_breakdown', {}), ensure_ascii=False, indent=2)}\n"
    ...
)
```

**问题**: platform_breakdown 是嵌套 JSON `{"doubao": {"total": 10, "mentions": 7, "success": 9}}`，LLM 经常忽略这些数字。

**修改方案**: 将嵌套 JSON 替换为可读表格。

```python
# 替换 L941 的 json.dumps 行
# 构建平台表格
platform_breakdown = metrics.get("platform_breakdown", {})
if platform_breakdown:
    platform_table_lines = [
        "| 平台 | 总问题数 | 成功获取 | 品牌提及数 | 提及率 |",
        "|------|---------|---------|-----------|--------|",
    ]
    for platform, stats in platform_breakdown.items():
        total = stats.get("total", 0)
        success = stats.get("success", 0)
        mentions = stats.get("mentions", 0)
        rate = f"{mentions/total:.1%}" if total > 0 else "0.0%"
        platform_table_lines.append(
            f"| {platform} | {total} | {success} | {mentions} | {rate} |"
        )
    platform_table = "\n".join(platform_table_lines)
else:
    platform_table = "暂无平台数据"

sections.append(
    f"## 核心指标\n"
    f"- 提及率: {metrics.get('mention_rate', 0):.2%}\n"
    f"- BWVS指数: {metrics.get('bwvs_index', 0):.2f}\n"
    f"- 总问题数: {metrics.get('total_questions', 0)}\n"
    f"- 总提及数: {metrics.get('total_mentions', 0)}\n"
    f"- BWVS各维度: 提及={metrics.get('bwvs_breakdown', {}).get('mention_score', 0):.1f}, "
    f"情感={metrics.get('bwvs_breakdown', {}).get('sentiment_score', 0):.1f}, "
    f"覆盖={metrics.get('bwvs_breakdown', {}).get('coverage_score', 0):.1f}, "
    f"引用={metrics.get('bwvs_breakdown', {}).get('citation_score', 0):.1f}\n\n"
    f"### 各平台详细表现\n{platform_table}\n\n"
    f"### 情感分布\n{json.dumps(metrics.get('sentiment_distribution', {}), ensure_ascii=False)}"
)
```

---

### 修改 4: 加强 LLM 输出验证 (P1)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`, L217-227

**当前代码**:
```python
if report_data:
    executive_summary = report_data.get("executive_summary", "")
    actionable_recs = report_data.get("actionable_recommendations", [])
    if len(executive_summary) < 80 or not actionable_recs:
        report_data = None
```

**修改方案**: 增加对 `platform_analysis` 和 `competitor_deep_analysis` 的校验。

```python
if report_data:
    executive_summary = report_data.get("executive_summary", "")
    actionable_recs = report_data.get("actionable_recommendations", [])
    platform_analysis = report_data.get("platform_analysis", [])
    competitor_analysis = report_data.get("competitor_deep_analysis")

    validation_failures = []
    if len(executive_summary) < 80:
        validation_failures.append(
            f"executive_summary 过短 ({len(executive_summary)} chars < 80)"
        )
    if not actionable_recs:
        validation_failures.append("actionable_recommendations 为空")
    if not platform_analysis:
        validation_failures.append("platform_analysis 为空")
    # competitor_deep_analysis 仅在有竞品数据时校验
    if competitors and not competitor_analysis:
        validation_failures.append("competitor_deep_analysis 为空（有竞品数据但未分析）")

    if validation_failures:
        logger.warning(
            "[A5] LLM output validation failed: %s",
            "; ".join(validation_failures),
        )
        report_data = None  # 触发 fallback
```

---

### 修改 5: max_tokens 提升 (P1)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`, L210

**当前**: `max_tokens=8192`

**修改**: `max_tokens=12288`

7 章节报告 + 竞品对比表 + 平台逐一分析，8192 tokens 容易被截断。12288 给予充分空间。

---

### 修改 6: 竞品出现位置追踪 (P1, 用户要求)

**文件**: `aeo-platform/backend/app/workflow/nodes_a5.py`, `_calculate_competitor_metrics()` + `_build_a5_user_content()`

**用户要求**: "告知本次抓取中哪些竞品出现了、出现在哪些问题中、为什么能出现"

**修改方案**: `_calculate_competitor_metrics()` 返回结果增加 `appeared_in_questions` 字段。

```python
# 在 _calculate_competitor_metrics() 的循环中（L740-743），记录出现的问题
for answer_text in all_answers:
    if name.lower() in answer_text.lower():
        mentions += 1
        sentiment_scores.append(_analyze_sentiment(answer_text))
```

**问题**: 当前循环遍历的是 `all_answers`（纯文本列表），已丢失了问题来源信息。

**修改方案**: 重构 `_calculate_competitor_metrics()` 的输入，使用 `fetch_results` 的完整结构而非扁平化的 `all_answers`：

```python
def _calculate_competitor_metrics(
    fetch_results: list, competitors: list
) -> list[dict[str, Any]]:
    # ... (前置检查不变)

    # 遍历 fetch_results 保留问题上下文
    for c in competitors:
        name = c.get("name", "")
        if not name:
            # ... (不变)
            continue

        mentions = 0
        sentiment_scores: list[str] = []
        appeared_questions: list[dict] = []  # 新增：记录出现的问题

        for result in fetch_results:
            question_text = result.get("question_text", "")
            question_id = result.get("question_id", "")
            for pr in result.get("platform_results", []):
                if not pr.get("success"):
                    continue
                answer = pr.get("answer", {})
                content = answer.get("content", "") if isinstance(answer, dict) else str(answer)
                if content and name.lower() in content.lower():
                    mentions += 1
                    sentiment_scores.append(_analyze_sentiment(content))
                    appeared_questions.append({
                        "question": question_text[:60],
                        "platform": pr.get("platform", ""),
                    })

        total_answers = sum(
            1 for r in fetch_results
            for pr in r.get("platform_results", [])
            if pr.get("success")
        )
        mention_rate = mentions / total_answers if total_answers > 0 else 0
        mention_counts.append((mentions, name))

        # ... (sentiment_value 计算不变)

        competitor_metrics.append({
            "name": name,
            "relevance_score": c.get("relevance_score", 0),
            "mention_rate": round(mention_rate, 4),
            "avg_ranking": 0,
            "sentiment": round(sentiment_value, 2),
            "appeared_in": appeared_questions[:5],  # 新增：最多5条
        })

    # ... (ranking 计算不变)
    return competitor_metrics
```

在 `_build_a5_user_content()` 的竞品表格中追加出现位置信息：

```python
# 在竞品表格之后追加详细出现记录
for cm in competitor_metrics:
    appeared = cm.get("appeared_in", [])
    if appeared:
        comp_lines.append(f"\n**{cm['name']}** 出现在以下问题中：")
        for a in appeared:
            comp_lines.append(f"  - [{a['platform']}] {a['question']}")
```

---

## 不需要改动的文件

| 文件 | 原因 |
|------|------|
| `graph.py` | Graph 拓扑不变 |
| `orchestrator_node.py` | 编排逻辑不变 |
| `nodes_a3.py` | 问题生成逻辑不变 |
| `nodes_a4.py` | 抓取逻辑不变 |
| `state.py` | State 字段不变 |
| 前端所有文件 | A5 artifact data 结构兼容（新字段为新增，不破坏现有渲染） |
| DB 迁移 | 不需要 |

---

## 修改影响评估

| 修改项 | 文件 | 改动行数 | 风险 | 影响范围 |
|--------|------|---------|------|---------|
| 1. 竞品指标提前 | nodes_a5.py | ~5 行移动 | 极低 | A5 内部调用顺序 |
| 2. 竞品表格化 | nodes_a5.py | ~25 行新增 | 低 | LLM prompt 内容 |
| 3. 平台表格化 | nodes_a5.py | ~20 行替换 | 低 | LLM prompt 内容 |
| 4. 输出验证增强 | nodes_a5.py | ~15 行替换 | 低 | fallback 触发条件 |
| 5. max_tokens | nodes_a5.py | 1 行 | 极低 | LLM 调用参数 |
| 6. 竞品出现追踪 | nodes_a5.py | ~30 行重构 | 中 | _calculate_competitor_metrics 返回值 |

**总计**: 仅修改 `nodes_a5.py` 一个文件，约 ~95 行改动。

---

## 定时任务监测更新 — 架构影响评估

### 现有监测架构

已有完整的定时监测框架：

1. **MonitoringSchedule 模型** (`models/monitoring_schedule.py`):
   - 支持 daily/weekly/biweekly/monthly 频率
   - `next_run_at` 字段调度执行时间
   - `baseline_data` 字段（JSONText）已在 migration 005 中添加，存储 A1+A3 输出
   - `consecutive_failures` + `max_failures` 容错

2. **创建监测节点** (`nodes_monitoring.py`):
   - 通过 orchestrator 的 `create_monitoring_schedule` 工具调用
   - 创建 MonitoringSchedule 记录

3. **Headless 执行模式** (`state.py` L254):
   - `headless_mode: bool` 字段已存在
   - Orchestrator 中 `ask_user` 遇到 headless 时自动确认

### 缺失部分（需要新增）

**调度器进程**还没有实现。当前只有：
- 创建 schedule 的逻辑
- baseline_data 的 DB 列

但没有：
- 周期扫描 `next_run_at <= now()` 的定时任务
- 触发 Graph 执行的调度逻辑
- 执行完成后更新 `last_run_at`、`next_run_at`、`total_runs` 的逻辑

### 是否需要新增调度模块

**需要，但与 Issue #3 解耦。** 调度模块属于 Issue #4 / P2 范畴。

**建议的调度方案**（仅做架构说明，不在 Issue #3 中实施）：

```
app/
  scheduler/
    __init__.py
    runner.py          # 主循环: 每分钟扫描 next_run_at <= now()
    executor.py        # 触发 headless Graph 执行
```

实现方式有两种选择：

| 方式 | Pros | Cons |
|------|------|------|
| **APScheduler** (进程内) | 简单，与 FastAPI 集成好 | 单进程，重启丢失 |
| **Celery Beat** (独立进程) | 可靠，支持分布式 | 依赖 Redis，运维复杂 |

**建议**: P2 先用 APScheduler（`celery_config.py` 已存在但未激活），预留 Celery 切换能力。

### 基线报告支持定时更新 — 影响分析

用户要求"基线报告独立可用，支持定时任务监测更新"。这需要：

1. **基线快照持久化**: 方案 C 中 `analysis_snapshots.snapshot_type = 'baseline'` 已覆盖
2. **定时任务复用基线**: `monitoring_schedules.baseline_data` 已存在（migration 005），存储 A1+A3 输出。定时任务读取此数据，跳过 A1-A3，只跑 A4+A5
3. **重跑基线**: 用户说"重新做基线分析"时，orchestrator 调用 `start_scenario_analysis` 工具（Issue #4 实现）的前置步骤
4. **历史基线查看**: 前端通过 snapshot list API 按 `snapshot_type='baseline'` 筛选，此 API 已有（`/api/v1/snapshots`），只需加 query param

**结论**: 定时任务监测更新不需要额外架构变化，现有 `baseline_data` + `headless_mode` + Snapshot 模型已覆盖。唯一缺失的是调度器进程本身（属于 Issue #4/P2）。

---

## 实施顺序建议

```
Phase 1 (开发者可立即开始):
  修改 1 (竞品提前)  ──┐
  修改 3 (平台表格化) ──┼── 并行修改，全在 nodes_a5.py
  修改 5 (max_tokens) ──┘

Phase 2 (Phase 1 合并后):
  修改 2 (竞品表格化)  ── 依赖修改 1 的新参数
  修改 6 (竞品出现追踪) ── 依赖修改 1 的新参数

Phase 3 (最后):
  修改 4 (输出验证增强) ── 等 Phase 1+2 确认 LLM 输出改善后再调整阈值
```

---

## 测试验证

修改后通过以下方式验证：

1. **E2E 测试**: 运行 `e2e_full_pipeline.py`，检查 A5 输出的 `report_data` 中：
   - `platform_analysis` 非空且包含每个平台的 `mention_count`
   - `competitor_deep_analysis.comparison_matrix` 非空且每个竞品有 `competitor_mention_rate`
   - `actionable_recommendations` 至少 3 条且引用具体数字

2. **Prompt 对比**: 在修改前后各运行一次，对比 `_build_a5_user_content()` 的输出长度和结构

3. **Fallback 测试**: 故意传入极少的 fetch_results（如 1 条），验证输出验证能正确触发 fallback
