# 置信度信号交付物实施拆解

**作者**: Martin Fowler + John Carmack
**日期**: 2026-03-12
**状态**: 开发拆解稿
**关联文档**:
- `docs/tech-confidence-signal-artifact-2026-03-12.md`
- `docs/ux-confidence-signal-artifact-2026-03-12.md`
- `docs/debate-confidence-signal-artifact-2026-03-12.md`

---

## 1. 实施目标

本拆解面向工程执行，输出 4 类内容：

1. 前端开发任务清单
2. 后端开发任务清单
3. WebSocket 协议字段表
4. 类型定义草案

目标不是再讨论方向，而是给出一版可直接排期的工作包。

---

## 2. 建议实施顺序

推荐按 4 个增量来做：

### Increment 1：只读版 `置信度信号`

目标：

1. A4 完成后自动创建 `confidence_signal` Artifact
2. 自动跑 citation 批量 AICE
3. 前端只读展示自动结果

不做：

1. `额外评估`
2. `artifact_action`
3. `artifact_patch`

### Increment 2：交付物内 `额外评估`

目标：

1. 在交付物里增加 URL / 文本输入框
2. 支持通过 `artifact_action` 触发一次额外评估
3. 主 LLM 在 artifact scope 内路由到 A7

### Increment 3：增量更新与局部状态

目标：

1. 引入 `artifact_patch`
2. 支持局部 loading / 局部错误 / 逐批完成
3. 避免 citation 批量阶段生成过多版本快照

### Increment 4：稳定性与治理

目标：

1. artifact metadata 持久化
2. 历史恢复一致性
3. manual / auto item 聚合统计
4. 测试补齐

---

## 3. 前端开发任务清单

### FE-1 扩展 `report_kind` 渲染分支

文件：

- [ReportContent.tsx](/D:/AGEO/frontend/src/components/canvas/contents/ReportContent.tsx)

任务：

1. 保留现有品牌报告渲染
2. 增加 `report_kind = confidence_signal` 分支
3. 接入新的 `ConfidenceSignalContent`

验收：

1. 不影响现有 `report_v2`
2. `confidence_signal` 可单独渲染

### FE-2 新增 `ConfidenceSignalContent`

建议新增文件：

- `frontend/src/components/canvas/contents/ConfidenceSignalContent.tsx`
- `frontend/src/components/canvas/contents/confidence-signal/ConfidenceSignalSummary.tsx`
- `frontend/src/components/canvas/contents/confidence-signal/ConfidenceSignalItemRow.tsx`
- `frontend/src/components/canvas/contents/confidence-signal/ConfidenceSignalComposer.tsx`

任务：

1. 顶部摘要区
2. auto citation 列表
3. manual extra 列表
4. `额外评估` 输入区
5. 局部 loading / error / empty states

### FE-3 扩展 `ReportCanvasData`

文件：

- [canvas.ts](/D:/AGEO/frontend/src/types/canvas.ts)

任务：

1. 新增 `report_kind`
2. 新增 `confidence_signal` 相关字段
3. 尽量以可选字段扩展，不破坏现有调用

建议新增：

- `artifact_kind?: string`
- `summary?: ConfidenceSignalSummary`
- `auto_items?: ConfidenceSignalItem[]`
- `manual_items?: ConfidenceSignalItem[]`
- `aggregate_findings?: ConfidenceSignalFinding[]`
- `composer?: ConfidenceSignalComposerState`
- `status?: ConfidenceSignalStatus`

### FE-4 扩展 Canvas Store 的 patch 能力

文件：

- [canvasStore.ts](/D:/AGEO/frontend/src/stores/canvasStore.ts)

任务：

1. 保留现有 `updateContent`
2. 新增 `patchContent`
3. 支持按 `item_id` merge `auto_items` / `manual_items`

原因：

当前 `updateContent` 更适合浅层对象 merge，不适合 Artifact 的分批增量更新。

### FE-5 WebSocket 收发扩展

文件：

- [useWebSocket.ts](/D:/AGEO/frontend/src/hooks/useWebSocket.ts)
- [websocket.ts](/D:/AGEO/frontend/src/types/websocket.ts)

任务：

1. 新增发送方法 `sendArtifactAction`
2. 新增接收事件 `artifact_patch`
3. 在 `WebSocketEventData` 中补齐新字段

### FE-6 交付物内输入交互

任务：

1. composer 输入内容校验
2. URL / 文本提示
3. 禁止空输入
4. 发送后清空或保留策略
5. loading 态和错误态

验收：

1. 输入一个 URL 可以触发 action
2. 输入一段文本可以触发 action
3. 混合输入能收到局部错误

### FE-7 历史恢复

文件：

- [ChatPanel.tsx](/D:/AGEO/frontend/src/components/chat/ChatPanel.tsx)

任务：

1. 历史 artifact 恢复时保留 `report_kind = confidence_signal`
2. 恢复 `artifact_key`
3. 恢复 `manual_items` / `auto_items`

---

## 4. 后端开发任务清单

### BE-1 定义 `confidence_signal` Artifact schema

建议新增模块：

- `aeo-platform/backend/app/workflow/a7/confidence_signal_schema.py`

任务：

1. 定义顶层 payload
2. 定义 item schema
3. 定义 patch schema

### BE-2 A4 完成后触发 citation 评估

候选改动点：

- A4 完成节点
- A4 -> A5 之间或 A4 完成后并行触发

任务：

1. 提取 citation URL
2. 创建 `confidence_signal` Artifact shell
3. 异步或串行调用 A7 批量评估

决策建议：

- MVP 先串行接入，降低并发复杂度
- 稳定后再考虑与 A5 并行

### BE-3 新增 A7 批量 citation 入口

建议新增：

- `evaluate_citations_for_confidence_signal(...)`

任务：

1. 接收 citation 列表
2. 逐条跑 AICE-Web
3. 生成 `auto_items`
4. 计算 summary

### BE-4 新增 `artifact_action` 事件处理

文件：

- [websocket_langgraph.py](/D:/AGEO/aeo-platform/backend/app/api/v1/websocket_langgraph.py)

任务：

1. 注册新的 websocket 事件分支
2. 校验 `artifact_id`
3. 读取 artifact metadata
4. 构造 artifact-scope 上下文
5. 调用 orchestrator 或直接走 constrained router

### BE-5 主 LLM 的 artifact-scope tool routing

建议新增模块：

- `app/workflow/artifact_router.py`

职责：

1. 构造受限上下文
2. 调主 LLM
3. 输出严格 JSON
4. 只允许 `a7_extra_evaluate`

### BE-6 新增 `a7_extra_evaluate`

建议新增：

- `app/workflow/a7/extra_eval.py`

任务：

1. 处理 URL 输入
2. 处理文本输入
3. 归一化结果为 `manual_items`
4. 返回 patch payload

### BE-7 新增 `artifact_patch` 事件发送

建议新增：

- `send_artifact_patch(...)`

位置：

- [events.py](/D:/AGEO/aeo-platform/backend/app/workflow/events.py)

任务：

1. 统一 patch payload 结构
2. 向前端推送局部更新
3. 与 `output_ready` 分工明确

### BE-8 artifact 元数据持久化

现状：

- [message.py](/D:/AGEO/aeo-platform/backend/app/models/message.py) 有 `extra_metadata`

任务：

1. 在 OUTPUT message 的 `extra_metadata` 中存：
   - `artifact_key`
   - `artifact_kind`
   - `entrypoint`
2. `output_service.py` 恢复时优先读 `artifact_key`

### BE-9 输入 guardrail

任务：

1. 空输入拦截
2. 超长文本拦截
3. 混合 URL + 长文本拦截
4. 不支持“问题抓取命令”

返回：

- 交付物内局部错误
- 或 ask_user

---

## 5. WebSocket 协议字段表

### 5.1 前端 -> 后端：`artifact_action`

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `event` | string | 是 | 固定为 `artifact_action` |
| `data.artifact_id` | string | 是 | 当前 Artifact ID |
| `data.action` | string | 是 | 固定为 `extra_evaluate` |
| `data.payload.raw_input` | string | 是 | 用户粘贴的原始内容 |
| `data.payload.entrypoint` | string | 是 | 固定为 `confidence_signal_extra_eval` |
| `data.payload.client_request_id` | string | 否 | 前端请求幂等 ID |

示例：

```json
{
  "event": "artifact_action",
  "data": {
    "artifact_id": "session_xxx_report_confidence_signal_main",
    "action": "extra_evaluate",
    "payload": {
      "raw_input": "https://example.com/article",
      "entrypoint": "confidence_signal_extra_eval",
      "client_request_id": "req_001"
    }
  }
}
```

### 5.2 后端 -> 前端：`artifact_patch`

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `event` | string | 是 | 固定为 `artifact_patch` |
| `data.artifact_id` | string | 是 | 要更新的 Artifact |
| `data.patch_type` | string | 是 | 初期固定 `merge` |
| `data.patch` | object | 是 | 局部 patch 内容 |
| `data.status` | string | 否 | `running|ready|error` |
| `data.message` | string | 否 | 面向 UI 的状态文案 |

示例：

```json
{
  "event": "artifact_patch",
  "data": {
    "artifact_id": "session_xxx_report_confidence_signal_main",
    "patch_type": "merge",
    "patch": {
      "manual_items": [
        {
          "item_id": "manual_001",
          "item_origin": "manual_extra",
          "input_type": "text",
          "label": "手动追加文本",
          "overall_score": 78,
          "overall_confidence": 0.82,
          "status": "ready"
        }
      ],
      "summary": {
        "average_score": 72.1
      }
    },
    "status": "ready",
    "message": "额外评估已完成"
  }
}
```

### 5.3 后端 -> 前端：`artifact_action_error`

建议新增，避免滥用全局 `error`：

| 字段 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| `event` | string | 是 | 固定为 `artifact_action_error` |
| `data.artifact_id` | string | 是 | 当前 Artifact |
| `data.action` | string | 是 | `extra_evaluate` |
| `data.message` | string | 是 | 错误文案 |
| `data.recoverable` | boolean | 是 | 是否可重试 |

---

## 6. 类型定义草案

### 6.1 前端 TypeScript

建议补到 [canvas.ts](/D:/AGEO/frontend/src/types/canvas.ts)：

```ts
export type ConfidenceSignalLevel = 'high' | 'neutral' | 'caution';

export type ConfidenceSignalStatus = {
  phase?: 'idle' | 'running' | 'ready' | 'error';
  message?: string;
};

export type ConfidenceSignalSummary = {
  total_citations?: number;
  evaluated_count?: number;
  failed_count?: number;
  high_confidence_count?: number;
  neutral_count?: number;
  caution_count?: number;
  average_score?: number;
  updated_at?: string;
};

export type ConfidenceSignalDimensionScore = {
  key: string;
  label: string;
  max_score: number;
  score: number;
  confidence?: number;
  reasoning?: string;
};

export type ConfidenceSignalItem = {
  item_id: string;
  item_origin: 'auto_citation' | 'manual_extra';
  input_type: 'url' | 'text';
  label: string;
  url?: string;
  domain?: string;
  signal_level?: ConfidenceSignalLevel;
  overall_score?: number;
  overall_confidence?: number;
  top_signals?: string[];
  dimension_scores?: ConfidenceSignalDimensionScore[];
  recommendations?: Array<{ title?: string; action?: string; reason?: string }>;
  status?: 'pending' | 'running' | 'ready' | 'error';
  error_message?: string;
};

export type ConfidenceSignalComposerState = {
  enabled?: boolean;
  allowed_input_types?: Array<'url' | 'text'>;
  placeholder?: string;
};
```

### 6.2 前端 WebSocket

建议补到 [websocket.ts](/D:/AGEO/frontend/src/types/websocket.ts)：

```ts
export interface ArtifactActionPayload {
  artifact_id: string;
  action: 'extra_evaluate';
  payload: {
    raw_input: string;
    entrypoint: 'confidence_signal_extra_eval';
    client_request_id?: string;
  };
}
```

### 6.3 后端 Python TypedDict / Pydantic

建议新增：

```python
class ConfidenceSignalSummary(TypedDict, total=False):
    total_citations: int
    evaluated_count: int
    failed_count: int
    high_confidence_count: int
    neutral_count: int
    caution_count: int
    average_score: float
    updated_at: str


class ConfidenceSignalItem(TypedDict, total=False):
    item_id: str
    item_origin: Literal["auto_citation", "manual_extra"]
    input_type: Literal["url", "text"]
    label: str
    url: str
    domain: str
    signal_level: Literal["high", "neutral", "caution"]
    overall_score: float
    overall_confidence: float
    top_signals: list[str]
    dimension_scores: list[dict[str, Any]]
    recommendations: list[dict[str, Any]]
    status: Literal["pending", "running", "ready", "error"]
    error_message: str
```

---

## 7. 测试任务清单

### FE 测试

1. `confidence_signal` 渲染不影响已有 report
2. `artifact_patch` 可正确更新同一 Artifact
3. `manual_items` 与 `auto_items` 不混淆
4. Composer 在 loading 态可禁用重复提交

### BE 测试

1. citation URL 提取为空时仍能创建空壳 Artifact
2. `artifact_action` 非法 artifact_id 返回 recoverable error
3. `extra_evaluate` 对 URL 和文本都能返回标准 item
4. `artifact_key` 持久化后刷新恢复一致

### 集成测试

1. A4 -> 自动出现 `置信度信号`
2. 在交付物内输入 URL -> 结果追加到 `manual_items`
3. 在交付物内输入文本 -> 结果追加到 `manual_items`
4. 输入不支持命令 -> 局部错误，不污染 Chat

---

## 8. 估算建议

粗略按增量估算：

| 增量 | 范围 | 复杂度 |
| :--- | :--- | :--- |
| Increment 1 | 自动 citation 评估 + 只读渲染 | 中 |
| Increment 2 | `artifact_action` + artifact-scope LLM routing | 中高 |
| Increment 3 | `artifact_patch` + store patch merge | 中高 |
| Increment 4 | 持久化治理 + 测试补齐 | 中 |

风险最高的不是 A7 评分本身，而是：

1. Artifact 增量更新语义
2. 历史恢复一致性
3. 交付物内输入不污染主对话流

---

## 9. 最终建议

如果现在要立即进入开发，我建议从下面这条最小链路开始：

1. A4 完成后自动创建 `confidence_signal`
2. 前端只读显示 citation AICE 结果
3. 完成 `artifact_key` 持久化治理
4. 然后再做 `额外评估`

理由是：

1. 先验证 `置信度信号` 作为交付物是否成立
2. 先把 Artifact 身份和恢复问题解决
3. 再叠加交互和 LLM 驱动动作，整体风险最低
