# 置信度信号交付物技术设计

**作者**: Martin Fowler + John Carmack
**日期**: 2026-03-12
**状态**: 可实施设计
**关联文档**:
- `docs/debate-confidence-signal-artifact-2026-03-12.md`
- `docs/arch-content-evaluation-aice-2026-03-11.md`
- `docs/ux-confidence-signal-artifact-2026-03-12.md`

---

## 1. 目标

本设计要解决 4 个技术问题：

1. A4 完成后如何自动生成 `置信度信号` 交付物
2. 交付物内的 `额外评估` 如何触发一次新的 A7 任务
3. 主 LLM 如何在 artifact 上下文中驱动 A7，而不是依赖独立意图分类模块
4. 增量结果如何合并回同一个交付物而不破坏现有 Canvas 架构

---

## 2. 推荐原则

### 2.1 保留现有稳定抽象

不新增 Canvas 一级类型。  
继续使用：

- `report`
- `report_kind = confidence_signal`

### 2.2 新增 Artifact 作用域动作

不要把 `额外评估` 伪装成普通 chat message。

推荐新增一条 WebSocket 事件：

```text
artifact_action
```

这样可以保留“由主 LLM 驱动 A7”的原则，同时避免污染主对话流。

### 2.3 主 LLM 仍负责路由

系统不新增独立的 intent classifier 服务。

而是在 artifact action 的上下文中，把主 LLM 约束为：

- 只允许在当前 artifact 的能力边界内选工具
- 只判断输入是 URL / 文本 / 不支持
- 然后决定是否调用 A7

---

## 3. 总体架构

```text
A4 fetch_results
  -> collect citations
  -> build confidence_signal_request
  -> A7 batch evaluate citations
  -> save artifact(report_kind=confidence_signal)
  -> Canvas render confidence signal

artifact extra input
  -> send artifact_action
  -> orchestrator with artifact context
  -> main LLM chooses a7_extra_evaluate
  -> A7 evaluate extra input
  -> patch artifact data
  -> frontend update same artifact
```

---

## 4. 数据模型

### 4.1 Artifact 顶层结构

推荐 `report.data` 结构：

```json
{
  "report_kind": "confidence_signal",
  "artifact_kind": "confidence_signal",
  "summary": {
    "total_citations": 18,
    "evaluated_count": 16,
    "failed_count": 2,
    "high_confidence_count": 5,
    "neutral_count": 7,
    "caution_count": 4,
    "average_score": 71.4,
    "updated_at": "2026-03-12T10:20:00Z"
  },
  "auto_items": [],
  "manual_items": [],
  "aggregate_findings": [],
  "composer": {
    "enabled": true,
    "allowed_input_types": ["url", "text"],
    "placeholder": "输入链接或文本…"
  },
  "status": {
    "phase": "ready",
    "message": ""
  }
}
```

### 4.2 item 结构

自动 citation 与手动追加结果，统一成同一种 item：

```json
{
  "item_id": "cite_001",
  "item_origin": "auto_citation",
  "input_type": "url",
  "label": "Example Article",
  "url": "https://example.com/article",
  "domain": "example.com",
  "signal_level": "caution",
  "overall_score": 63,
  "overall_confidence": 0.84,
  "top_signals": [
    "缺少 Schema",
    "日期不清晰",
    "来源非官方"
  ],
  "dimension_scores": [],
  "recommendations": [],
  "status": "ready",
  "error_message": ""
}
```

`item_origin` 枚举：

- `auto_citation`
- `manual_extra`

### 4.3 manual composer 请求结构

```json
{
  "artifact_id": "session_xxx_report_confidence_signal_main",
  "action": "extra_evaluate",
  "payload": {
    "raw_input": "https://example.com/article",
    "entrypoint": "confidence_signal_extra_eval"
  }
}
```

---

## 5. 新增协议

### 5.1 前端 -> 后端：`artifact_action`

WebSocket 消息：

```json
{
  "event": "artifact_action",
  "data": {
    "artifact_id": "session_xxx_report_confidence_signal_main",
    "action": "extra_evaluate",
    "payload": {
      "raw_input": "https://example.com/article",
      "entrypoint": "confidence_signal_extra_eval"
    }
  }
}
```

### 5.2 后端 -> 前端：`artifact_patch`

推荐新增一条增量事件，而不是频繁复用 `output_ready`。

原因：

1. citation 自动批量评估是分批返回的
2. 若每批都发 `output_ready`，Canvas 会不断生成版本
3. 用户不需要为每一条 citation 评估都留一个版本快照

因此推荐：

```json
{
  "event": "artifact_patch",
  "data": {
    "artifact_id": "session_xxx_report_confidence_signal_main",
    "patch_type": "merge",
    "patch": {
      "summary": {
        "evaluated_count": 9
      },
      "auto_items": [
        {
          "item_id": "cite_009",
          "status": "ready",
          "overall_score": 76
        }
      ],
      "status": {
        "phase": "running",
        "message": "已完成 9 / 18"
      }
    }
  }
}
```

### 5.3 后端 -> 前端：`output_ready`

`output_ready` 仍然保留，但只用于：

1. 首次创建 `置信度信号` 交付物
2. 某次 `额外评估` 完成后落一个稳定快照

这样版本历史才有业务意义。

---

## 6. 主 LLM 驱动 A7 的方式

### 6.1 不是 intent classifier

对 `artifact_action(extra_evaluate)`，不要新增一个独立意图识别模块。

正确做法是：

1. 构造 artifact 上下文
2. 将允许的工具和输入类型一起给主 LLM
3. 主 LLM 输出严格 tool choice

### 6.2 artifact 上下文

推荐注入：

```json
{
  "entrypoint": "confidence_signal_extra_eval",
  "artifact_kind": "confidence_signal",
  "allowed_tools": ["a7_extra_evaluate"],
  "allowed_input_types": ["url", "text"],
  "forbidden_tools": [
    "answer_fetch",
    "question_simulation",
    "brand_analysis"
  ]
}
```

### 6.3 主 LLM 输出格式

```json
{
  "tool_name": "a7_extra_evaluate",
  "input_kind": "url",
  "confidence": 0.93,
  "normalized_payload": {
    "url_list": ["https://example.com/article"]
  },
  "needs_confirmation": false
}
```

或：

```json
{
  "tool_name": "a7_extra_evaluate",
  "input_kind": "text",
  "confidence": 0.87,
  "normalized_payload": {
    "text": "用户输入的一段正文"
  },
  "needs_confirmation": false
}
```

如果主 LLM 发现是混合输入：

```json
{
  "tool_name": "clarify",
  "input_kind": "mixed",
  "confidence": 0.42,
  "needs_confirmation": true
}
```

### 6.4 Guardrail

程序只负责最小校验：

1. 空输入
2. 超长输入
3. 混合 URL + 大段文本
4. URL 数量超过阈值

如果触发 guardrail：

- 返回局部错误
- 或在交付物内 ask_user

---

## 7. A7 节点设计

### 7.1 推荐接口

新增一个面向 artifact action 的内部入口：

```python
async def a7_extra_evaluate(
    session_id: str,
    artifact_id: str,
    input_kind: str,
    normalized_payload: dict[str, Any],
) -> dict[str, Any]:
```

### 7.2 两类输入

#### URL

流程：

```text
normalize urls
  -> extract page
  -> build web features
  -> run AICE-Web
  -> build manual_items patch
```

#### Text

流程：

```text
normalize text
  -> build text features
  -> run AICE-Text
  -> build manual_items patch
```

### 7.3 与自动 citation 评估的关系

自动 citation 评估与手动追加评估，建议复用相同的 A7 评分与 item schema。

差异只保留在：

- `item_origin`
- `input_type`
- `trigger_context`

这样后续聚合逻辑最简单。

---

## 8. Artifact 更新策略

### 8.1 自动 citation 批量阶段

推荐策略：

1. 先创建一个空壳 artifact
2. 状态为 `running`
3. citation 逐批写入 `artifact_patch`
4. 完成后写一次持久化快照

### 8.2 手动额外评估阶段

推荐策略：

1. 用户提交时，先 patch `status.phase = running`
2. A7 完成后把结果追加到 `manual_items`
3. 更新 `summary`
4. 再通过一次 `output_ready` 或持久化 patch 生成稳定版本

### 8.3 为什么不全靠 `output_ready`

因为 `output_ready` 在当前前端 store 里意味着“新版本”。

如果 citation 自动评估每返回一条就触发一次 `output_ready`：

1. 版本历史会爆炸
2. 用户看不到有意义的版本边界
3. 交付物会像流式日志，不像工作面板

所以：

- `artifact_patch` 负责过程内更新
- `output_ready` 负责阶段性稳定快照

---

## 9. 前端改动

### 9.1 类型

需要扩展 `ReportCanvasData`：

- `report_kind = confidence_signal`
- `summary`
- `auto_items`
- `manual_items`
- `aggregate_findings`
- `composer`
- `status`

### 9.2 渲染器

新增：

- `ConfidenceSignalContent.tsx`
- `ConfidenceSignalItemRow.tsx`
- `ConfidenceSignalComposer.tsx`

并在 `ReportContent.tsx` 下按 `report_kind` 分支。

### 9.3 Store

`canvasStore.updateContent()` 目前只适合浅层 merge。

若要支持 `artifact_patch`，建议新增：

```ts
patchContent: (id: string, patch: Record<string, unknown>) => void
```

对 `auto_items` / `manual_items` 采用按 `item_id` merge。

### 9.4 WebSocket

`useWebSocket.ts` 新增处理：

- `artifact_patch`

并新增发送：

- `sendArtifactAction(artifactId, action, payload)`

---

## 10. 后端改动

### 10.1 A4 完成后触发

在 A4 结果稳定后：

1. 提取 citation URL
2. 建立 `confidence_signal_request`
3. 调用 A7 批量评估
4. 创建 artifact shell

### 10.2 Orchestrator

主 LLM 的新职责不是处理全局 chat intent，而是处理：

- artifact action scope 下的受限工具选择

建议在 orchestrator 增加一个分支：

```text
artifact_scope_request
```

### 10.3 新增事件处理

在 `websocket_langgraph.py` 新增：

- `artifact_action` 事件入口

处理逻辑：

1. 校验 artifact 是否存在
2. 读取 artifact metadata
3. 构造 artifact-scope orchestrator context
4. 调主 LLM 做 tool choice
5. 路由到 `a7_extra_evaluate`

### 10.4 持久化

推荐为 artifact 增加 metadata：

```json
{
  "artifact_kind": "confidence_signal",
  "artifact_key": "session_xxx_report_confidence_signal_main",
  "entrypoint": "a4_citation_confidence_signal"
}
```

同时为手动评估 item 保留：

- `created_by = auto|manual`
- `created_from_artifact_action = true|false`

---

## 11. 失败模式

### 11.1 支持的失败隔离

1. 某个 citation 失败，不影响其它 citation
2. 某次 `额外评估` 失败，不影响现有 artifact
3. 手动追加失败时，仅在 `manual_items` 区显示错误卡片

### 11.2 不支持的输入

对于以下输入，直接在交付物内提示而不是转去别的 agent：

1. 问题抓取命令
2. 竞品分析命令
3. 混合 URL + 问题列表

这类输入建议返回：

```text
当前额外评估仅支持链接或文本。若需抓取问题回答，请回到主对话区发起。
```

---

## 12. 实施顺序

### Phase A

1. `report_kind = confidence_signal` 渲染器
2. A4 完成后自动创建 citation 评估 artifact
3. 先不支持交付物内输入

### Phase B

1. `额外评估` composer UI
2. `artifact_action` 协议
3. artifact-scope orchestrator
4. 主 LLM 驱动 `a7_extra_evaluate`

### Phase C

1. `artifact_patch` 增量更新
2. 版本快照策略
3. manual / auto item 聚合统计

---

## 13. 架构结论

这套方案的关键不是“再造一个评估页面”，而是把 Artifact 从只读结果升级为受限交互面板。

最重要的三条原则是：

1. 主 LLM 继续承担路由职责
2. 路由发生在 artifact 上下文中，而不是全局 chat 歧义里
3. 交付物内输入只允许 URL / 文本，不开放成迷你 Chat

如果按这个边界实现，`置信度信号` 方案会比之前的 Chat-first 方案更贴近你想要的系统结构。
