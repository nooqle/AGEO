# Issue #4: 全景基线分析 — 技术实施方案

**架构师**: Martin Fowler
**日期**: 2026-02-22
**状态**: 待用户确认
**输入文档**: `issue4-prd.md`, `issue4-ux-design.md`, `prd-v2-confirmed.md`

---

## 目录

1. [字段冲突解决方案](#1-字段冲突解决方案)
2. [AgentState 扩展](#2-agentstate-扩展)
3. [A3 baseline_dynamic 模式](#3-a3-baseline_dynamic-模式)
4. [A5 双报告支持](#4-a5-双报告支持)
5. [Orchestrator 两阶段编排](#5-orchestrator-两阶段编排)
6. [前端变更清单](#6-前端变更清单)
7. [实施顺序](#7-实施顺序)
8. [风险点和验证方案](#8-风险点和验证方案)

---

## 1. 字段冲突解决方案

### 1.1 问题分析

现有 `baseline_fetch_results` 字段定义在 `state.py:248`:

```python
baseline_fetch_results: list | None  # Unselected platform results to preserve
```

该字段用于 **selective_refetch** 流程（Cycle 3, Module 2），存储"未被选中重新抓取的平台的旧结果"，在 A4 完成后与新结果合并。

使用该字段的位置（共 6 处）：
| 文件 | 行号 | 用途 |
|------|------|------|
| `state.py:248` | 定义 | 字段声明 |
| `nodes_followup.py:518` | 写入 | `selective_refetch_node` 将未选中平台结果存入 |
| `nodes_a4.py:618` | 读取 | A4 完成后读取 baseline 进行合并 |
| `nodes_a4.py:688` | 清除 | 合并完成后置 None |
| `websocket_langgraph.py:94` | 初始化 | 新会话默认 None |
| `websocket_langgraph.py:461` | 初始化 | 重新运行时重置 |
| `scheduler.py:291` | 初始化 | 定时任务初始化 |

### 1.2 重命名方案

将现有字段 `baseline_fetch_results` → `preserved_fetch_results`，语义更准确地描述"为合并而保留的旧平台结果"。

**修改清单**（全部为简单的 find-replace）：

| 文件 | 修改内容 |
|------|---------|
| `state.py:248` | 字段名 + 注释 |
| `nodes_followup.py:518` | key name |
| `nodes_a4.py:618` | `state.get("baseline_fetch_results")` → `state.get("preserved_fetch_results")` |
| `nodes_a4.py:688` | key name |
| `websocket_langgraph.py:94` | key name |
| `websocket_langgraph.py:461` | key name |
| `scheduler.py:291` | key name |

**风险评估**：纯重命名操作，不改变任何逻辑。所有 7 处引用已完整列出，无遗漏风险。重命名后 `baseline_*` 前缀专用于基线分析。

---

## 2. AgentState 扩展

### 2.1 新增字段

在 `state.py` 的 `AgentState` 类末尾新增一个段落：

```python
# =========================================================================
# Baseline Analysis (Issue #4, Phase 4a)
# =========================================================================
analysis_mode: str | None           # "baseline" / "persona" — 当前 A3→A4→A5 执行的模式
baseline_questions: list | None     # A3 baseline_dynamic 输出的问题列表（与 questions 结构相同）
baseline_fetch_results: list | None # A4 基线抓取结果（与 fetch_results 结构相同）
baseline_metrics: dict | None       # A5 基线指标（与 metrics 结构相同）
baseline_report: dict | None        # A5 基线报告（与 report 结构相同）
```

### 2.2 字段语义说明

| 字段 | 写入时机 | 读取时机 | 生命周期 |
|------|---------|---------|---------|
| `analysis_mode` | Orchestrator 在调用 A3 前设置 | A3/A4/A5 据此决定读写哪组字段 | 每次 A3→A5 周期内有效 |
| `baseline_questions` | A3 baseline_dynamic 模式完成后 | A4 读取（当 analysis_mode="baseline"）| 基线数据，长期保留 |
| `baseline_fetch_results` | A4 基线抓取完成后 | A5 读取（当 analysis_mode="baseline"）| 基线数据，长期保留 |
| `baseline_metrics` | A5 基线分析完成后 | 场景 A5 读取（注入基线上下文）| 基线数据，重跑时覆盖 |
| `baseline_report` | A5 基线分析完成后 | 场景 A5 读取（注入基线上下文）| 基线数据，重跑时覆盖 |

### 2.3 与现有字段的关系

**两组并行数据通道**：

```
基线通道:  baseline_questions → baseline_fetch_results → baseline_metrics / baseline_report
场景通道:  questions → fetch_results → metrics / report  (现有字段不变)
```

A3/A4/A5 根据 `analysis_mode` 决定写入哪组字段。Orchestrator 在调用 `question_simulation` 时设置 `analysis_mode`。

### 2.4 初始化变更

以下文件需要在 state 初始化时新增这些字段的默认值（全部为 `None`）：

| 文件 | 行号 | 新增 |
|------|------|------|
| `websocket_langgraph.py:94` | 新会话初始化 | `"analysis_mode": None, "baseline_questions": None, "baseline_fetch_results": None, "baseline_metrics": None, "baseline_report": None` |
| `websocket_langgraph.py:461` | 重新运行初始化 | 同上（注意：重跑基线时不清除 baseline_* 字段，仅清除场景字段）|
| `scheduler.py:291` | 定时任务初始化 | 同上 |

---

## 3. A3 baseline_dynamic 模式

### 3.1 路由变更

**文件**: `nodes_a3.py:39-54`

当前 A3 入口仅支持 `"brand"` 和 `"persona"` 两种模式。需新增 `"baseline_dynamic"` 分支：

```python
async def a3_question_node(state: AgentState) -> Command:
    session_id = state["session_id"]
    user_decisions = state.get("user_decisions", {})
    a3_mode = user_decisions.get("a3_mode", "brand")

    if a3_mode == "baseline_dynamic":
        return await _a3_baseline_dynamic_mode(state)
    elif a3_mode == "persona":
        return await _a3_persona_focused_mode(state)
    else:
        return await _a3_brand_panorama_mode(state)
```

### 3.2 新增函数 `_a3_baseline_dynamic_mode()`

**位置**: `nodes_a3.py`，在 `_a3_persona_focused_mode()` 之后新增

**核心逻辑**：

```python
async def _a3_baseline_dynamic_mode(state: AgentState) -> Command:
    """A3 baseline dynamic mode: LLM generates industry panorama questions."""
    session_id = state["session_id"]
    brand_profile = state.get("brand_profile") or {}
    competitors = state.get("competitors") or []
    brand_name = _extract_brand_name(brand_profile, state)

    # 1. Build prompt
    system_prompt = _build_baseline_system_prompt()
    user_content = _build_baseline_user_content(brand_profile, competitors)

    # 2. Call LLM
    model = get_llm_model()
    response = await call_llm_streaming(...)

    # 3. Parse + validate
    data = extract_json_from_content(response.content)
    questions = data.get("questions", [])

    # 4. Validate: 直接品牌问题 <= 10%
    _validate_baseline_questions(questions, brand_name)

    # 5. Build simulated_questions + flattened
    simulated_questions, flattened_questions = _build_question_lists(questions)

    # 6. Emit events (stage_result, artifact)
    await save_and_send_artifact(
        session_id=session_id,
        output_type="questionList",  # 使用固定 Tab ID: {sessionId}_questionList
        title="基线问题列表",
        data={...},
    )

    # 7. 写入 baseline_questions（而非 questions）
    return Command(
        update={
            "simulated_questions": {"simulated_questions": simulated_questions},
            "baseline_questions": flattened_questions,  # 基线通道
            "questions": flattened_questions,           # 同时写入 questions 供 A4 使用
            "current_step": "A3",
            "progress": 0.5,
        },
    )
```

**关键设计决策**：
- `baseline_questions` 和 `questions` **同时写入**。原因是 A4 节点始终从 `questions` 读取，改动最小。`baseline_questions` 作为长期保留的副本，供重跑基线时的 A5 使用。
- A4 不需要感知 `analysis_mode`，它只关心 `questions` 和 `fetch_results`。

### 3.3 Baseline Prompt

**新增函数**: `_build_baseline_system_prompt()` 和 `_build_baseline_user_content()`

System prompt 核心约束（来自 PRD 4.1-4.4）：

```
你是一个消费者行为研究专家。请基于以下品牌信息和竞品列表，
生成模拟用户在 AI 搜索引擎中会提问的**行业全景问题**。

## 核心规则
1. 问题必须是**用户视角**，模拟真实消费者的搜索行为
2. 直接提及目标品牌的问题**不超过总数的 10%**
3. 问题必须覆盖品牌的**主要产品领域**
4. 包含预算、场景、用途等真实决策因素
5. 问题要口语化，像真实用户会在 AI 搜索中输入的

## 问题分类比例
- 品类需求咨询 (30%)
- 场景化选购 (25%)
- 品类对比排名 (20%)
- 行业趋势探索 (15%)
- 品牌直接问题 (10% 上限)

## 输出格式 (JSON)
{
  "questions": [
    {
      "question_id": "bl_001",
      "core_question": "问题文本",
      "category": "品类需求咨询|场景化选购|品类对比排名|行业趋势探索|品牌直接问题",
      "user_intent": "用户意图",
      "decision_stage": "认知|兴趣|评估|决策",
      "covers_product": "对应的产品线(可选)"
    }
  ]
}
```

User content 包含：
- 品牌名称、行业、核心产品（来自 `brand_profile`）
- 竞品列表（来自 `competitors`，供品类对比排名类问题引入）
- 总问题数要求：10-15 个

### 3.4 问题质量验证函数

```python
def _validate_baseline_questions(
    questions: list[dict], brand_name: str
) -> None:
    """验证基线问题质量，不合格时 log warning（不阻断流程）。"""
    if not questions:
        return

    total = len(questions)
    brand_direct_count = sum(
        1 for q in questions
        if brand_name.lower() in q.get("core_question", "").lower()
        or q.get("category", "") == "品牌直接问题"
    )
    brand_ratio = brand_direct_count / total if total > 0 else 0

    if brand_ratio > 0.15:  # 允许 15% 的容差（10% 目标 + 5% 容差）
        logger.warning(
            "[A3] Baseline questions brand_ratio=%.1f%% exceeds 15%% threshold "
            "(%d/%d). Proceeding anyway.",
            brand_ratio * 100, brand_direct_count, total,
        )
```

### 3.5 Fallback 策略

如果 `baseline_dynamic` 模式的 LLM 调用失败或输出解析失败，fallback 到 `brand` 模板模式。这与 persona 模式的现有 fallback 策略一致。

```python
except Exception as e:
    logger.error(f"[A3] Baseline dynamic mode failed: {e}", exc_info=True)
    logger.info("[A3] Falling back to brand panorama mode")
    # 设置 a3_mode 回退标记，但保留 analysis_mode="baseline" 不变
    return await _a3_brand_panorama_mode(state)
```

---

## 4. A5 双报告支持

### 4.1 A5 入口路由

**文件**: `nodes_a5.py:97-110`

A5 需要根据 `analysis_mode` 决定：
1. 读取哪组输入数据（baseline_* vs 现有字段）
2. 输出到哪组字段
3. 使用什么 `output_type` 发送到 Canvas
4. 是否注入基线上下文

```python
async def a5_analytics_node(state: AgentState) -> Command:
    session_id = state["session_id"]
    analysis_mode = state.get("analysis_mode") or "persona"  # 默认兼容旧行为

    if analysis_mode == "baseline":
        return await _a5_baseline_report(state)
    else:
        return await _a5_persona_report(state)
```

### 4.2 基线报告函数 `_a5_baseline_report()`

**核心差异点**：

| 维度 | 基线报告 | 场景报告（现有） |
|------|---------|---------------|
| 数据来源 | `state["fetch_results"]`（A4 输出）| `state["fetch_results"]`（同，A4 不区分） |
| 指标写入 | `baseline_metrics`, `baseline_report` | `metrics`, `report` |
| artifact output_type | `"report_baseline"` | `"report_persona"` |
| artifact title | `"基线全景分析报告"` | `"AI可见性分析报告"` |
| artifact category | `"baseline"` | `"scenario"` |
| System prompt | 强调行业全景视角 | 强调场景/画像视角 |
| 基线上下文注入 | 否 | 是（注入 `baseline_report`）|

**数据写回**：

```python
# 基线模式写入
return Command(
    update={
        "metrics": metrics,            # 也写入 metrics（兼容现有逻辑）
        "report": report_data,         # 也写入 report（兼容现有逻辑）
        "baseline_metrics": metrics,   # 基线专属副本
        "baseline_report": report_data,# 基线专属副本
        "current_step": "A5",
        "progress": 0.95,
    },
)
```

**设计决策**：基线模式同时写入 `metrics/report` 和 `baseline_metrics/baseline_report`。原因是：
1. `metrics` 被 orchestrator 的 `_build_agent_result_summary` 和 `_build_context_summary` 读取
2. `report` 被 orchestrator 的上下文构建读取
3. 如果只写 `baseline_*`，orchestrator 会认为"A5 未产出数据"

### 4.3 场景报告注入基线上下文

**文件**: `nodes_a5.py:918-1055`（`_build_a5_user_content` 函数）

在现有函数末尾（`sections.append("请生成完整的 7 章节...")` 之前）新增：

```python
# 注入基线上下文（仅场景模式且有基线数据时）
baseline_report = state.get("baseline_report")
baseline_metrics = state.get("baseline_metrics")
if analysis_mode == "persona" and baseline_metrics:
    baseline_bwvs = baseline_metrics.get("bwvs_index", 0)
    baseline_mention = baseline_metrics.get("mention_rate", 0)
    baseline_findings = ""
    if baseline_report:
        baseline_findings = "\n".join(
            f"- {f}" for f in baseline_report.get("key_findings", [])[:3]
        )
    sections.append(
        f"## 基线报告参考数据\n"
        f"- 基线 BWVS: {baseline_bwvs:.1f}\n"
        f"- 基线提及率: {baseline_mention:.1%}\n"
        f"- 基线核心发现:\n{baseline_findings}\n\n"
        f"请在场景报告中对比基线数据，说明该场景表现与行业基线的差异。"
        f"在总览部分增加 '场景 BWVS vs 基线 BWVS' 的对比数据。"
    )
```

**注意**：`_build_a5_user_content` 的签名需要新增 `analysis_mode` 和 `state` 参数（或直接传入 `baseline_metrics/baseline_report`），这是对现有函数的增量扩展。

### 4.4 save_and_send_artifact 变更

基线报告使用 `output_type="report_baseline"`，场景报告使用 `output_type="report_persona"`。

**文件**: `events.py:175-237`（`save_and_send_artifact`）

当前 `save_and_send_artifact` 的 artifact ID 格式为 `{session_id}_{output_type}`。因此：
- 基线报告 Tab ID: `{session_id}_report_baseline`
- 场景报告 Tab ID: `{session_id}_report_persona`

两者 **天然分 Tab**，无需额外处理。Issue #5 的版本合并机制自动生效：重跑基线时新报告覆盖同 Tab，旧报告进 `versions[]`。

**`send_output_ready` 扩展**：`output_ready` 事件需新增 `category` 字段，让前端知道报告类型。

```python
# events.py send_output_ready() 新增参数
async def send_output_ready(
    session_id: str,
    output_type: str,
    data: dict[str, Any],
    title: str | None = None,
    output_id: str | None = None,
    related_message_id: str | None = None,
    linked_message_id: str | None = None,
    category: str | None = None,        # 新增
    scenario_label: str | None = None,   # 新增
) -> None:
    payload = {
        ...existing fields...
    }
    if category:
        payload["category"] = category
    if scenario_label:
        payload["scenario_label"] = scenario_label
    ...
```

相应地，`save_and_send_artifact` 也需要透传这两个参数。

### 4.5 A5 System Prompt 变更

基线模式的 A5 prompt 与场景模式共享核心结构（7 章节），但在开头注入不同的上下文说明：

```python
def _get_a5_system_prompt(report_type: str = "persona") -> str:
    """Get A5 system prompt. report_type: 'baseline' or 'persona'."""

    context_intro = ""
    if report_type == "baseline":
        context_intro = """
## 报告类型：行业全景基线分析
本次分析是品牌的行业全景基线分析。问题来源是行业通用的用户搜索问题（非特定画像）。
请从行业全景视角分析品牌的 AI 搜索可见性：
- 品牌在整个行业 AI 搜索生态中的位置
- 哪些竞品在行业通用问题中更常被提及
- 行业级别的内容优化建议
- 所有指标和建议以"行业基线"为参照系

"""
    else:
        context_intro = """
## 报告类型：场景分析报告
本次分析基于特定用户画像/场景。请从目标用户群体视角分析品牌表现。
如果提供了基线参考数据，请在报告中对比场景表现与行业基线的差异。

"""

    return context_intro + _EXISTING_SYSTEM_PROMPT_BODY
```

### 4.6 Snapshot 扩展

**文件**: `app/models/snapshot.py`

新增 `snapshot_type` 字段：

```python
snapshot_type: Mapped[str] = mapped_column(
    String(20), default="legacy", nullable=False, index=True
)
# Values: "baseline" / "persona" / "legacy"
```

**Alembic 迁移**：新增列 `snapshot_type VARCHAR(20) DEFAULT 'legacy' NOT NULL`，加索引。

**SnapshotService 变更**：
- `create_completed_snapshot()` 新增 `snapshot_type` 参数
- `get_previous_snapshot()` 新增可选 `snapshot_type` 过滤
- `_snapshot_to_dict()` 输出新增 `snapshot_type` 字段

---

## 5. Orchestrator 两阶段编排

### 5.1 Tool Registry 变更

**文件**: `orchestrator_node.py:78-93`（`question_simulation` 工具）

`question_simulation` 的 `mode` enum 新增 `"baseline_dynamic"`：

```python
{
    "name": "question_simulation",
    "parameters": {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "enum": ["brand_panorama", "persona_focused", "baseline_dynamic"],
                "description": "生成模式：brand_panorama=品牌全景, persona_focused=画像聚焦, baseline_dynamic=行业基线全景",
            },
            ...
        },
    },
}
```

**文件**: `orchestrator_node.py:111-126`（`data_analytics` 工具）

`data_analytics` 新增 `report_type` 参数：

```python
{
    "name": "data_analytics",
    "parameters": {
        "type": "object",
        "properties": {
            "report_focus": {
                "type": "string",
                "description": "报告重点方向（可选）",
            },
            "report_type": {
                "type": "string",
                "enum": ["baseline", "persona"],
                "description": "报告类型：baseline=行业基线报告, persona=场景分析报告",
            },
        },
    },
}
```

### 5.2 Tool Call 处理变更

**文件**: `orchestrator_node.py:1073-1148`（`_handle_tool_call` 中 `question_simulation` 处理）

当 `mode="baseline_dynamic"` 时：
1. 设置 `user_decisions["a3_mode"] = "baseline_dynamic"`
2. 设置 `analysis_mode = "baseline"`
3. **不触发** `ask_user` 确认（基线模式由 Orchestrator 自动触发，无需用户选择路径）

```python
if tool_name == "question_simulation":
    user_decisions = dict(state.get("user_decisions", {}))
    mode = tool_args.get("mode", "")

    if mode == "baseline_dynamic":
        user_decisions["a3_mode"] = "baseline_dynamic"
        extra_updates["user_decisions"] = user_decisions
        extra_updates["analysis_mode"] = "baseline"
    elif "a3_mode" in user_decisions:
        pass  # User already chose via confirmation
    elif mode:
        user_decisions["a3_mode"] = (
            "brand" if mode == "brand_panorama" else "persona"
        )
        extra_updates["user_decisions"] = user_decisions
        extra_updates["analysis_mode"] = "persona"
    else:
        # 无模式指定 — 触发 ask_user（现有逻辑）
        ...
```

**`data_analytics` 处理**：

```python
if tool_name == "data_analytics":
    report_type = tool_args.get("report_type", "persona")
    extra_updates["analysis_mode"] = report_type
```

### 5.3 Orchestrator System Prompt 变更

**文件**: `orchestrator_node.py:345-425`（`build_orchestrator_system_prompt`）

在 "行为准则" 段落中新增基线编排指导：

```
基线分析流程（重要）：
- 当用户请求品牌分析时（如"帮我分析兰蔻"），A1 完成后必须先用 ask_user 展示品牌信息确认
- 用户确认品牌信息后，自动执行基线分析：
  1. 调用 question_simulation(mode="baseline_dynamic") 生成行业全景问题
  2. 调用 answer_fetch 抓取 AI 平台回答
  3. 调用 data_analytics(report_type="baseline") 生成基线报告
- 基线分析完成后，用 ask_user(type="guided") 展示引导卡片：
  选项：开始场景细化分析(推荐) / 重新运行基线分析 / 直接提问
- 用户选择"开始场景细化"时：
  1. 调用 persona_generation 生成画像
  2. 用户选择画像后，调用 question_simulation(mode="persona_focused")
  3. 调用 answer_fetch
  4. 调用 data_analytics(report_type="persona")
- 用户说"重新跑基线"时：跳过 A1（复用已有品牌信息），直接 question_simulation(mode="baseline_dynamic") → answer_fetch → data_analytics(report_type="baseline")
```

### 5.4 Context Summary 变更

**文件**: `orchestrator_node.py:292-342`（`_build_context_summary`）

新增基线数据状态显示：

```python
if state.get("baseline_metrics"):
    bm = state["baseline_metrics"]
    parts.append(f"- 基线 BWVS: {bm.get('bwvs_index', 'N/A')}")
    parts.append("- 基线报告: 已完成")
```

### 5.5 Agent Result Summary 变更

**文件**: `orchestrator_node.py:428-506`（`_build_agent_result_summary`）

`data_analytics` 分支需区分 baseline/persona：

```python
if tool_name == "data_analytics":
    analysis_mode = state.get("analysis_mode", "persona")
    if analysis_mode == "baseline":
        metrics = state.get("baseline_metrics") or state.get("metrics")
    else:
        metrics = state.get("metrics")
    if metrics:
        bwvs = metrics.get("bwvs_index", 0)
        mode_label = "基线" if analysis_mode == "baseline" else "场景"
        return (
            f"{mode_label}数据分析完成。BWVS指数：{bwvs:.1f}，"
            f"总提及率：{metrics.get('mention_rate', 0):.1%}。"
        )
    return "数据分析完成，但未获取到有效数据。"
```

### 5.6 Workflow Steps 变更

**文件**: `orchestrator_node.py:596-617`（`WORKFLOW_STEPS`）

基线流程跳过 A2，但当前 WORKFLOW_STEPS 是固定的 5 步。需要让前端根据 `plan_update` 事件动态构建步骤列表（UX 设计已确认这一点）。

**方案**：不修改 `WORKFLOW_STEPS` 常量。当 `analysis_mode="baseline"` 时，`_is_step_skipped` 函数将 A2 标记为 skipped：

```python
def _is_step_skipped(step_id: str, state: AgentState, user_decisions: dict) -> bool:
    if step_id == "A2":
        # 基线模式跳过 A2
        if state.get("analysis_mode") == "baseline":
            return True
        if user_decisions.get("a3_mode") == "brand":
            return True
        if state.get("simulated_questions") and not state.get("marketing_personas"):
            return True
    return False
```

---

## 6. 前端变更清单

### 6.1 Phase 1 变更（零新组件方案）

| 文件 | 行号/区域 | 修改内容 | 改动量 |
|------|---------|---------|--------|
| `types/canvas.ts:3-10` | `CanvasContentType` | 无需修改。`report_baseline`/`report_persona` 作为 `output_type` 传入，映射到 `type: 'report'` | 0 行 |
| `types/canvas.ts:261-339` | `CanvasContent` 联合类型 | 每个分支新增可选字段 `category?: 'baseline' \| 'scenario'` 和 `scenarioLabel?: string` | ~14 行 |
| `stores/canvasStore.ts:54-93` | `addContent` | 保存 `category` 和 `scenarioLabel` 到 content 对象 | ~6 行 |
| `components/canvas/contents/ReportContent.tsx` | 报告标题区域 | 根据 `category` 字段显示不同标题："基线全景分析报告" vs "AI可见性分析报告" | ~15 行 |
| `components/canvas/CanvasHeader.tsx` | 版本选择器 | 场景报告版本显示 `scenarioLabel` 作为版本名称 | ~10 行 |
| WebSocket 事件处理 | `output_ready` handler | 解析 `category` 和 `scenario_label` 字段，传入 `addContent` | ~5 行 |

**总改动量**: ~50 行，0 个新组件。

### 6.2 前端事件处理变更

`output_ready` 事件处理（通常在 `useSocketEvents.ts` 或类似文件中）：

```typescript
// 处理 output_ready 事件时
const outputType = data.type;  // "report_baseline" / "report_persona" / "report"
const category = data.category;  // "baseline" | "scenario" | undefined

// 映射 output_type 到 Canvas type
// report_baseline 和 report_persona 的 Canvas type 都是 "report"
const canvasType = outputType.startsWith("report") ? "report" : outputType;

canvasStore.addContent({
  id: data.id,            // "{sessionId}_report_baseline"
  type: canvasType,
  title: data.title,
  data: data.data,
  category: category,
  scenarioLabel: data.scenario_label,
  ...
});
```

### 6.3 CanvasContent 类型扩展详情

在 `types/canvas.ts` 中，给 CanvasContent 联合类型的每个 report 分支新增可选字段：

```typescript
// 在 report 分支中
| {
    id: string;
    type: 'report';
    title: string;
    data: ReportCanvasData;
    createdAt: Date;
    relatedMessageId: string;
    versions: ContentVersion[];
    currentVersionIndex: number;
    linkedMessageId?: string;
    category?: 'baseline' | 'scenario';     // 新增
    scenarioLabel?: string;                  // 新增
  }
```

**设计决策**：`category` 放在 CanvasContent 层级（而非 data 层级），因为它影响 Tab 标题和版本选择器的展示，属于 Canvas 框架关注的元数据。

---

## 7. 实施顺序

按依赖关系排序的步骤列表，后续步骤依赖前置步骤的产出：

### Step 1: 字段重命名 + AgentState 扩展 (0.5-1h)

**文件**:
- `state.py` — 重命名 `baseline_fetch_results` → `preserved_fetch_results` + 新增 5 个基线字段
- `nodes_followup.py:518` — 重命名
- `nodes_a4.py:618,688` — 重命名
- `websocket_langgraph.py:94,461` — 重命名 + 新增初始化
- `scheduler.py:291` — 重命名 + 新增初始化

**验证**: 运行现有 E2E 测试（`casual_chat`, `a1_brand`, `full_pipeline`），确认无回归。

### Step 2: A3 baseline_dynamic 模式 (2-3h)

**文件**:
- `nodes_a3.py` — 新增路由分支 + `_a3_baseline_dynamic_mode()` + prompt 函数 + 验证函数

**依赖**: Step 1（`baseline_questions` 字段必须已声明）

**验证**: 单独测试 A3 baseline_dynamic 模式，检查输出格式和品牌问题占比。

### Step 3: A5 双报告支持 (3-4h)

**文件**:
- `nodes_a5.py` — 入口路由 + `_a5_baseline_report()` + prompt 变更 + 基线上下文注入 + `save_and_send_artifact` 使用不同 output_type
- `events.py` — `send_output_ready` 和 `save_and_send_artifact` 新增 `category`/`scenario_label` 参数

**依赖**: Step 1（`baseline_metrics/baseline_report` 字段）

**验证**: 单独测试 A5 baseline 模式和 persona 模式，检查报告标题、output_type、category 字段。

### Step 4: Orchestrator 编排逻辑 (2-3h)

**文件**:
- `orchestrator_node.py` — Tool Registry 变更 + tool call 处理 + system prompt 变更 + context summary 变更 + result summary 变更 + `_is_step_skipped` 变更

**依赖**: Step 2 + Step 3（Orchestrator 需要调用已实现的 A3 baseline 和 A5 baseline）

**验证**: E2E 测试完整基线流程（品牌输入 → A1 → 确认 → A3 baseline → A4 → A5 baseline → 引导卡片）。

### Step 5: Orchestrator Prompt 更新 (0.5-1h)

**文件**:
- `prompts/general_react_agent.md` — 新增基线编排指导段落

**依赖**: Step 4

**验证**: 人工测试对话流程，验证 Orchestrator 按基线流程执行。

### Step 6: Snapshot 扩展 (1-1.5h)

**文件**:
- `app/models/snapshot.py` — 新增 `snapshot_type` 列
- `app/services/snapshot_service.py` — 参数/查询扩展
- Alembic migration — 新增列

**依赖**: Step 3（A5 调用 SnapshotService 时传入 snapshot_type）

**验证**: 检查数据库 migration，测试 snapshot 写入和查询。

### Step 7: 前端适配 (1-2h)

**文件**:
- `types/canvas.ts` — CanvasContent 新增 `category`/`scenarioLabel` 可选字段
- `stores/canvasStore.ts` — `addContent` 透传新字段
- `components/canvas/contents/ReportContent.tsx` — 根据 category 显示不同标题
- `components/canvas/CanvasHeader.tsx` — scenarioLabel 在版本选择器中显示
- WebSocket 事件处理文件 — 解析新字段

**依赖**: Step 3（后端 output_ready 事件已携带 category）

**验证**: 手动测试基线报告和场景报告的 Canvas 展示。

### 工作量总结

| Step | 内容 | 预估工时 |
|------|------|---------|
| 1 | 字段重命名 + State 扩展 | 0.5-1h |
| 2 | A3 baseline_dynamic 模式 | 2-3h |
| 3 | A5 双报告支持 | 3-4h |
| 4 | Orchestrator 编排逻辑 | 2-3h |
| 5 | Orchestrator Prompt | 0.5-1h |
| 6 | Snapshot 扩展 | 1-1.5h |
| 7 | 前端适配 | 1-2h |
| - | 联调 + E2E 测试 | 3-4h |
| **总计** | | **13.5-19.5h (约 2-3 天)** |

---

## 8. 风险点和验证方案

### Risk 1: A3 baseline_dynamic LLM 生成质量不稳定

**严重度**: 中 | **概率**: 中

**具体风险**:
- LLM 生成的问题中直接品牌问题超过 10%
- 问题不覆盖 `core_products` 中的核心产品
- 问题不够口语化，像模板而非真实用户搜索

**验证方案**:
1. 单元测试：Mock LLM 返回，验证 `_validate_baseline_questions()` 函数
2. 集成测试：对 3 个不同行业品牌（护肤/科技/食品）运行 A3 baseline_dynamic，人工检查问题质量
3. 监控：在 log 中输出品牌问题占比，添加 Prometheus metric（可选 P1）

**缓解措施**:
- prompt 中强调比例约束
- `_validate_baseline_questions()` 输出 warning（不阻断，记录供后续优化）
- fallback 到 brand 模板模式

### Risk 2: A4/A5 state 数据互相覆盖

**严重度**: 高 | **概率**: 中

**具体风险**: 基线和场景共用 A4/A5 节点，如果 `analysis_mode` 没有正确设置，场景数据可能覆盖基线数据（或反之）。

**验证方案**:
1. E2E 测试完整两阶段流程：基线完成 → 场景完成 → 验证 `baseline_metrics` 和 `metrics` 是不同的值
2. 断言测试：基线完成后 `baseline_metrics.bwvs_index` 有值；场景完成后 `metrics.bwvs_index` 有值且 `baseline_metrics` 不变

**缓解措施**:
- A3/A5 入口处 assert `analysis_mode` 值合法
- 基线数据写入 `baseline_*` 字段同时也写入 `metrics/report`（双写保险）

### Risk 3: Orchestrator prompt 过长导致 LLM 决策质量下降

**严重度**: 中 | **概率**: 低

**具体风险**: 新增基线编排指导后，system prompt 总 token 数增加约 200-300 tokens，可能干扰 LLM 对其他场景的判断。

**验证方案**:
1. 计算更新后 system prompt 的 token 数，确认不超过 2000 tokens
2. 回归测试：运行现有 E2E 测试（casual_chat, a1_brand, full_pipeline），确认无行为变化

**缓解措施**:
- 基线编排指导控制在 150 词以内
- 使用分段式结构，LLM 只在相关阶段参考对应段落

### Risk 4: `baseline_fetch_results` 重命名遗漏

**严重度**: 高 | **概率**: 低

**具体风险**: 重命名后遗漏某处引用，导致 selective_refetch 流程运行时 KeyError 或数据丢失。

**验证方案**:
1. grep 全局搜索确认 0 处残留的 `baseline_fetch_results`
2. 运行 selective_refetch E2E 测试

**缓解措施**:
- 已在 1.2 节中完整列出所有 7 处引用（来自 grep 搜索结果）
- 重命名为一次性原子操作

### Risk 5: 前端 output_type 映射

**严重度**: 低 | **概率**: 低

**具体风险**: `output_type="report_baseline"` 在前端可能无法正确映射到 `type: 'report'` 的 Canvas 渲染组件。

**验证方案**:
1. 确认前端 output_ready 事件处理代码使用 `type` 字段（来自后端 `send_output_ready`）而非自行解析 `output_type`
2. 手动测试：基线报告到达后确认 ReportContent 正确渲染

**缓解措施**:
- `send_output_ready` 发送的 `type` 字段固定为 `"report"`（不是 `"report_baseline"`），`output_type` 仅用于 artifact ID。前端根据 `type` 决定渲染组件，根据 `category` 决定标题。

### Risk 6: 数据库 Migration 兼容性

**严重度**: 低 | **概率**: 低

**具体风险**: `snapshot_type` 列新增 migration 在生产环境执行时可能失败。

**验证方案**:
1. 在开发环境运行 `alembic upgrade head`
2. 确认 `DEFAULT 'legacy'` 正确应用到已有行

**缓解措施**:
- 使用 `nullable=False, default="legacy"` 确保向后兼容
- Migration 使用 `server_default='legacy'` 处理已有数据

---

## 附录 A: 不修改的部分

以下部分**无需修改**（确认了 Issue #5 的基础设施已就绪）：

| 组件 | 原因 |
|------|------|
| `canvasStore.addContent` 版本合并逻辑 | 已支持同 ID 覆盖 + versions[] |
| CanvasHeader 版本选择器 | 已由 Issue #5 实现 |
| `save_and_send_artifact` 固定 ID 格式 | 已使用 `{session_id}_{output_type}` |
| LangGraph graph 定义 (`graph.py`) | 不新增节点或边 |
| A4 节点 | 不感知 analysis_mode，直接读 questions / 写 fetch_results |
| WebSocket 事件类型 | 不新增事件类型，复用现有 output_ready/stage_result/inline_confirmation |

## 附录 B: 关键代码位置索引

| 功能 | 文件 | 行号 |
|------|------|------|
| AgentState 定义 | `state.py` | 32-255 |
| Orchestrator tool registry | `orchestrator_node.py` | 34-277 |
| Orchestrator system prompt | `orchestrator_node.py` | 345-425 |
| Orchestrator tool call handler | `orchestrator_node.py` | 883-1171 |
| A3 mode routing | `nodes_a3.py` | 39-54 |
| A3 persona mode | `nodes_a3.py` | 249-469 |
| A5 main node | `nodes_a5.py` | 97-494 |
| A5 system prompt | `nodes_a5.py` | 778-915 |
| A5 user content builder | `nodes_a5.py` | 918-1055 |
| save_and_send_artifact | `events.py` | 175-237 |
| send_output_ready | `events.py` | 149-172 |
| Snapshot model | `models/snapshot.py` | 56-133 |
| Snapshot service | `services/snapshot_service.py` | 1-318 |
| selective_refetch (旧 baseline_fetch_results) | `nodes_followup.py` | ~518 |
| A4 merge logic (旧 baseline_fetch_results) | `nodes_a4.py` | 618-688 |
| Canvas types | `frontend/src/types/canvas.ts` | 1-348 |
| Canvas store | `frontend/src/stores/canvasStore.ts` | 1-145 |
| ReportContent component | `frontend/src/components/canvas/contents/ReportContent.tsx` | - |
