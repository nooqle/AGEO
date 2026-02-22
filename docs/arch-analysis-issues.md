# 架构分析报告：Issue #3 / #4 / #5

> **作者**: Martin Fowler (架构师)
> **日期**: 2026-02-22
> **状态**: 架构评估（供团队讨论）

---

## 目录

1. [Issue #3: 报告质量 — 根因分析](#issue-3-报告质量--根因分析)
2. [Issue #4: 全景基线分析 — 架构方案](#issue-4-全景基线分析--架构方案)
3. [Issue #5: 交付物导航合并 — 数据模型变化](#issue-5-交付物导航合并--数据模型变化)

---

## Issue #3: 报告质量 — 根因分析

### 问题现象

A5 报告中出现：
- 平台分析章节为空
- 竞品对比表为空
- 优化建议泛泛而谈

### 根因分析

经过深入阅读 `nodes_a5.py`，根因有三层：

#### 根因 1: LLM 输出验证过于宽松 (nodes_a5.py:217-227)

当前验证仅检查 `executive_summary` 长度和 `actionable_recommendations` 是否为空：

```python
if len(executive_summary) < 80 or not actionable_recs:
    report_data = None  # 触发 fallback
```

但 **不检查** `platform_analysis`、`competitor_deep_analysis` 等章节是否为空。LLM 可能生成了合格的摘要但跳过了其他章节，此时不会触发 fallback。

#### 根因 2: _normalize_report_data 默认值掩盖了空数据 (nodes_a5.py:1045-1068)

```python
report_data.setdefault("platform_analysis", [])
report_data.setdefault("competitor_deep_analysis", None)
report_data.setdefault("actionable_recommendations", [])
```

当 LLM 未输出这些字段时，`setdefault` 填入空值，但下游代码不再区分"LLM 没输出"和"确实为空"。

#### 根因 3: LLM 上下文输入不够结构化 (nodes_a5.py:913-991)

`_build_a5_user_content()` 组装的 prompt 中：
- **platform_breakdown** 是嵌套 JSON（`{platform: {total, mentions, success}}`），LLM 需要自行解读
- **竞品数据** 只传了 `name` 和 `relevance_score`，没有传已计算的竞品 mention_rate（`_calculate_competitor_metrics` 的结果在 prompt 构建 **之后** 才计算）
- **max_tokens=8192** 对于 7 章节报告可能不够，特别是竞品多时

#### 数据流时序问题

```
_calculate_metrics()                   → metrics（含 platform_breakdown）
_build_a5_user_content(metrics, ...)   → LLM prompt（此时竞品指标尚未计算）
call_llm_streaming()                   → report_data（LLM 只能靠 prompt 中竞品名称猜测）
_calculate_competitor_metrics()        → competitor_metrics（在 LLM 调用之后才计算）
```

**关键发现**: `_calculate_competitor_metrics()` 在 A5 node 第 277 行调用，但 LLM prompt 在第 192-211 行就已经发出。竞品的真实 mention_rate 没有传给 LLM，LLM 自然无法引用具体数字。

### 修复建议

| 优先级 | 修复项 | 影响范围 | 复杂度 |
|-------|--------|---------|--------|
| P0 | 将 `_calculate_competitor_metrics()` 提前到 LLM 调用之前，并将结果传入 prompt | `nodes_a5.py` ~10 行 | 低 |
| P0 | 在 `_build_a5_user_content()` 中将 platform_breakdown 格式化为可读表格 | `nodes_a5.py` ~15 行 | 低 |
| P1 | 加强 LLM 输出验证：检查 `platform_analysis` 非空（至少 1 项）、`competitor_deep_analysis` 非 None | `nodes_a5.py:217-227` | 低 |
| P1 | max_tokens 提升到 12288 或动态计算 | `nodes_a5.py:211` | 低 |
| P2 | 拆分 A5 为两步 LLM 调用（先分析后建议），降低单次输出复杂度 | 中等重构 | 中 |

---

## Issue #4: 全景基线分析 — 架构方案

### 需求理解

两阶段分析流程：
1. **基线分析**：品牌 → 全景问题 → 抓取 → 分析 → 基线报告
2. **场景细化**：基于用户画像 → 场景问题 → 抓取 → 对比基线 → 场景报告

### 当前架构约束

- **单 Graph 单拓扑**: `graph.py` 定义了一个 StateGraph，orchestrator 通过 Function Calling 动态路由
- **State 扁平结构**: `AgentState` 中 `fetch_results`、`metrics` 等字段是单值，不支持多组分析结果共存
- **Snapshot 与 Entity 一对多**: 每次分析产出一个 AnalysisSnapshot
- **Orchestrator 工具注册表**: `AGENT_REGISTRY` 中 `question_simulation` 已有 `mode` 参数（`brand_panorama` / `persona_focused`）

### 方案对比

#### 方案 A: 单 Graph + State 扩展（渐进式）

**思路**: 复用现有 Graph，在 State 中新增 `baseline_*` 字段存储基线数据，场景分析时引用。

**State 变化**:
```python
class AgentState(TypedDict):
    # 新增
    analysis_phase: str | None  # "baseline" | "scenario" | None
    baseline_metrics: dict | None  # 基线阶段的 metrics 快照
    baseline_fetch_results: list | None  # 已存在但当前用于 selective_refetch
    baseline_report: dict | None  # 基线报告
    baseline_snapshot_id: str | None  # 基线 snapshot 的 ID
```

**Orchestrator 变化**:
- `question_simulation` 工具的 `mode` 参数已就绪（`brand_panorama` 作为基线，`persona_focused` 作为场景）
- 编排器 system prompt 新增 `analysis_phase` 状态感知
- 场景分析阶段的 A5 prompt 注入基线数据作为对比参照

**A5 变化**:
- `_build_a5_user_content()` 接受 `baseline_metrics` 参数
- System prompt 增加"与基线对比"的指令

**Pros**:
- 最小改动，复用现有 Graph/编排器/LangGraph checkpoint
- 不影响现有单轮分析流程（`analysis_phase=None` 时行为不变）
- LangGraph checkpoint 自动持久化 baseline 数据

**Cons**:
- State 膨胀（已有 25+ 字段，再加 4-5 个）
- 两个阶段共享同一个 Graph 执行上下文，调试复杂
- 场景分析需要"清空"部分 State（如 `simulated_questions`、`fetch_results`）再重新填充

**影响估算**: ~100 行后端代码，不需要新 DB 迁移（State 在 LangGraph checkpoint 中），前端不需要改动

---

#### 方案 B: 双 Graph 独立执行（干净分离）

**思路**: 基线分析和场景分析各自是独立的 Graph 执行。通过 DB（AnalysisSnapshot）传递基线数据。

**Graph 变化**: 不变。同一个 Graph 定义被两次独立执行。

**关键机制**:
```
基线执行: graph.invoke({analysis_phase: "baseline", ...})
  → A1 → A3(brand_panorama) → A4 → A5 → Snapshot(type="baseline")

场景执行: graph.invoke({analysis_phase: "scenario", baseline_snapshot_id: "xxx", ...})
  → A2 → A3(persona_focused) → A4 → A5(对比基线) → Snapshot(type="scenario")
```

**DB 变化**:
```sql
ALTER TABLE analysis_snapshots ADD COLUMN snapshot_type VARCHAR(20) DEFAULT 'standard';
-- 'baseline' | 'scenario' | 'standard'
ALTER TABLE analysis_snapshots ADD COLUMN baseline_snapshot_id UUID REFERENCES analysis_snapshots(id);
```

**Pros**:
- State 干净，两次执行互不污染
- 可以并行化（基线完成后可同时跑多个场景）
- Snapshot 之间的关联关系清晰（scenario → baseline FK）

**Cons**:
- 需要新的 DB 迁移（`snapshot_type` + `baseline_snapshot_id`）
- 场景执行需要从 DB 加载基线数据注入 State
- 两个 Graph 执行对应两个不同的 LangGraph thread，需要前端管理多个 thread_id
- 用户体验上是"两段对话"还是"一段连续对话"需要产品定义

**影响估算**: ~200 行后端代码 + 1 个 DB 迁移 + 前端 thread 管理逻辑

---

#### 方案 C: 单 Graph + 子流程（混合方案，推荐）

**思路**: 保持单 Graph 单 session，但引入"阶段"概念。基线结果写入 Snapshot 并缓存在 State 中。场景分析开始时清空中间 State、保留基线引用。

**State 变化**:
```python
class AgentState(TypedDict):
    # 新增
    analysis_phase: str | None  # "baseline" | "scenario" | None
    baseline_snapshot_id: str | None  # 基线 snapshot ID
    baseline_metrics: dict | None  # 基线 metrics（A5 输出时写入）
```

**Orchestrator 变化**:
- 新增工具 `start_scenario_analysis`：
  ```python
  {
      "name": "start_scenario_analysis",
      "description": "基线分析完成后，启动场景细化分析。会清空中间数据并保留基线引用。",
      "parameters": {...}
  }
  ```
- 基线 A5 完成后，orchestrator 主动建议进入场景分析（类似当前 A2→A3 的 ask_user 流程）

**Graph 变化**:
- 新增 `reset_for_scenario` 节点：清空 `simulated_questions`、`fetch_results`、`metrics`、`report`，保留 `brand_profile`、`competitors`、`baseline_*`
- Graph 新增边：`reset_for_scenario → orchestrator`

**DB 变化**:
```sql
ALTER TABLE analysis_snapshots ADD COLUMN snapshot_type VARCHAR(20) DEFAULT 'standard';
ALTER TABLE analysis_snapshots ADD COLUMN baseline_snapshot_id UUID REFERENCES analysis_snapshots(id);
```

**Pros**:
- 单 session 连续对话，用户体验最自然
- State 增加有限（3 个字段）
- 基线数据既在 State 中（即时可用）也在 DB 中（持久化）
- 复用现有 Graph 拓扑，只加一个节点
- Orchestrator 通过 LLM 自然引导用户从基线进入场景

**Cons**:
- `reset_for_scenario` 节点的 State 清理需要仔细设计（确保不遗漏字段）
- 比方案 A 多一个节点和 DB 迁移
- LangGraph checkpoint 中会保留清理前后的完整历史

**影响估算**: ~150 行后端代码 + 1 个 DB 迁移 + 前端小量调整（报告对比展示）

### 架构建议

**推荐方案 C**。理由：
1. 与"Chat-first"产品定位最契合 — 用户在一个对话中完成基线和场景分析
2. 对现有代码侵入最小 — 复用 Graph 拓扑和编排器
3. 数据模型干净 — Snapshot 上的 `baseline_snapshot_id` 明确表达了依赖关系
4. 为 P2 阶段的"持续监测"铺路 — 定时任务可以只跑场景分析（复用基线）

### 对现有 Agent Prompt 的影响

| Agent | 影响 | 变化 |
|-------|------|------|
| A1 (Brand) | 无 | 基线和场景共享同一份 brand_profile |
| A2 (Persona) | 无 | 只在场景阶段运行，逻辑不变 |
| A3 (Question) | 低 | 已有 `mode` 参数，基线用 `brand_panorama`，场景用 `persona_focused` |
| A4 (Fetch) | 无 | 纯执行，不关心阶段 |
| A5 (Analytics) | 中 | Prompt 需要增加基线对比指令；`_build_a5_user_content()` 注入基线数据 |
| Orchestrator | 中 | System prompt 增加阶段感知；新增 `start_scenario_analysis` 工具 |

---

## Issue #5: 交付物导航合并与历史回溯

### 当前架构

**前端 (canvasStore.ts)**:
- `contents: CanvasContent[]` — 扁平列表，每个 Agent 产出一个 CanvasContent
- 每个 content 有 `id`、`type`、`title`、`data`、`createdAt`、`relatedMessageId`
- 通过 `activeContentIndex` 切换当前展示的内容
- 没有分组/版本概念

**后端 (events.py: save_and_send_artifact)**:
- 每次调用生成一个新的 Message（type=output），通过 WebSocket 发送
- `output_type` 区分内容类型：`report`、`questionList`、`fetchResults`、`touchpointMap`、`workflow` 等
- 没有版本号或父子关系

**CanvasContent 类型** (`canvas.ts`):
```typescript
type CanvasContentType =
  | 'report' | 'chart' | 'dataTable' | 'selection'
  | 'workflow' | 'questionList' | 'fetchResults' | 'touchpointMap';
```

### 需求拆解

1. **合并同类型内容**: 如 `report` 类型可能产出多次（初始报告 + drill_down 报告），需要合并为一个导航项并支持版本
2. **版本历史**: 同一类型内容的多次产出形成版本链（v1 → v2 → v3）
3. **跳转到对话上下文**: 从 Canvas 中的内容项跳转到对应的聊天消息位置

### 数据模型变化分析

#### 方案：前端引入 ContentGroup 概念

```typescript
// 新增
type ContentGroup = {
  id: string;
  type: CanvasContentType;
  title: string;
  versions: CanvasContent[];  // 按 createdAt 排序，最新在前
  activeVersionIndex: number;
};

// canvasStore 变化
interface CanvasState {
  // 替代现有 contents
  groups: ContentGroup[];
  activeGroupIndex: number;
  // ...
}
```

**分组策略**:
- 按 `type` 分组（所有 `report` 归为一组，所有 `questionList` 归为一组）
- 同一组内按 `createdAt` 排序形成版本链
- 导航栏显示组（如"分析报告 v3"），点击后展示最新版本，可切换历史版本

**跳转到对话上下文**:
- 每个 `CanvasContent` 已有 `relatedMessageId` 字段
- 前端实现：点击"查看上下文" → `conversationStore` 滚动到对应消息
- 后端无需改动

#### 后端 DB 变化

**方案 A（推荐）: 纯前端方案，不改 DB**

当前 Message 模型已有 `output_type` 字段，前端加载历史 Messages 后在客户端按 `output_type` 分组。

优点：零 DB 迁移，零后端代码改动
缺点：分组逻辑在前端，如果未来需要服务端查询"某类型的最新版本"会比较麻烦

**方案 B: 后端增加 output_version**

```sql
ALTER TABLE messages ADD COLUMN output_version INTEGER DEFAULT 1;
ALTER TABLE messages ADD COLUMN output_group_key VARCHAR(100);
-- output_group_key = "{session_id}:{output_type}"
```

后端在 `save_and_send_artifact` 中自动递增 `output_version`。

优点：版本信息服务端可查询
缺点：增加 DB 迁移和后端代码

### 架构建议

**Issue #5 推荐纯前端方案（方案 A）**。理由：
1. `relatedMessageId` 已经提供了上下文跳转所需的一切
2. `output_type` 已经可以作为分组 key
3. 版本排序直接用 `createdAt` 即可
4. 不需要后端改动，风险最低
5. 如果 P2 阶段需要服务端版本查询，再追加 DB 字段不迟

### canvasStore 重构估算

| 改动项 | 文件 | 复杂度 |
|-------|------|--------|
| 引入 `ContentGroup` 类型 | `types/canvas.ts` | 低 |
| canvasStore 新增 group 管理方法 | `stores/canvasStore.ts` | 中 |
| Canvas 导航栏改为 group tabs + version selector | `components/canvas/` | 中 |
| "查看上下文"按钮 + 滚动到消息 | `components/canvas/` + `conversationStore` | 低 |
| 兼容现有 addContent 逻辑（自动归入 group） | `stores/canvasStore.ts` | 低 |

**总估算**: ~200 行前端代码（类型 + store + 组件），后端 0 行

---

## 汇总：修改影响矩阵

| Issue | 后端改动量 | 前端改动量 | DB 迁移 | 风险等级 |
|-------|-----------|-----------|---------|---------|
| #3 报告质量 | ~40 行 (`nodes_a5.py`) | 0 | 无 | 低 |
| #4 基线分析（方案 C） | ~150 行 (State/Graph/A5/Orchestrator) | ~50 行 (报告对比展示) | 1 个 (snapshot_type) | 中 |
| #5 交付物导航 | 0 | ~200 行 (types/store/组件) | 无 | 低 |

### 建议实施顺序

1. **Issue #3** (P0): 先修复报告质量，这是当前最紧迫的问题，改动小风险低
2. **Issue #5** (P1): 纯前端改动，可以与 #3 并行
3. **Issue #4** (P1-P2): 依赖 #3 的报告质量修复（否则基线报告本身质量就差），且需要产品/UX 先出文档

---

## 附录：关键文件索引

| 文件 | 路径 | 关键行号 |
|------|------|---------|
| Graph 定义 | `aeo-platform/backend/app/workflow/graph.py` | 全文 |
| Orchestrator | `aeo-platform/backend/app/workflow/orchestrator_node.py` | L34-277 (工具注册), L635-880 (主逻辑) |
| A5 节点 | `aeo-platform/backend/app/workflow/nodes_a5.py` | L97-506 (主流程), L509-673 (metrics), L773-991 (LLM prompt) |
| A3 节点 | `aeo-platform/backend/app/workflow/nodes_a3.py` | L39-54 (路由), L62-241 (brand mode), L249-469 (persona mode) |
| State 定义 | `aeo-platform/backend/app/workflow/state.py` | L32-255 |
| Snapshot 模型 | `aeo-platform/backend/app/models/snapshot.py` | L56-133 |
| Entity 模型 | `aeo-platform/backend/app/models/entity.py` | L28-70 |
| Canvas Store | `frontend/src/stores/canvasStore.ts` | 全文 |
| Canvas 类型 | `frontend/src/types/canvas.ts` | 全文 |
