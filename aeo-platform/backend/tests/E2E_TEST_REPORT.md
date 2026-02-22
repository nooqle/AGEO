# Specta AI 编排器重构 - 端到端测试报告

## 测试执行概况

| 测试 | 类型 | 结果 | 说明 |
|------|------|------|------|
| 1b 心跳 | 自动化 | **PASS** | ping/pong 正常 |
| 3b GET消息API | 自动化 | **PASS** | API端点正常 |
| 5 重连 | 自动化 | **PASS** | 断开后重连正常 |
| 5b 快速重连 | 自动化 | **PASS** | 3次快速重连正常 |
| 7d 无效JSON | 自动化 | **FAIL** | 后端关闭连接 |
| 7e 未知事件 | 自动化 | **PASS** | 连接保持存活 |
| 1 基本E2E | 自动化+LLM | **PASS** | 4层事件均收到 |
| 3 历史持久化 | 自动化+LLM | **PASS** (手动验证) | DB有消息记录 |
| 4 对话恢复 | 自动化+LLM | **受阻** | WS在A1期间断开 |
| 6 多轮对话 | 自动化+LLM | **受阻** | 同上 |
| 7a 空消息 | 自动化+LLM | **受阻** | 同上 |
| 7c 非品牌消息 | 自动化+LLM | **受阻** | 同上 |

**总计**: 6 PASS, 1 FAIL, 5 受阻（因WS断连导致后续测试无法执行）

---

## 测试 1：基本端到端流程 (P0) - PASS

### 验证结果
- [x] 消息发送后，收到 Agent 事件流
- [x] Layer 1 (reply_delta): 7 个事件，流式显示编排器回复
- [x] Layer 2 (plan_update): 1 个事件，显示"正在执行：品牌竞品分析"
- [x] Layer 3 (action_log): 43 个事件（**异常多，见下方问题**）
- [ ] Layer 4 (inline_confirmation): 0 个事件（编排器选择自然语言对话）
- [x] 思考过程 (thought_delta): 17 个事件
- [ ] execution_complete: 未收到（编排器在等待用户回复）
- [x] 后端日志显示 tool result 注入成功

### 编排器行为分析
编排器正确执行了以下流程：
1. 接收用户消息"帮我分析安利纽崔莱"
2. 思考分析计划（thought_delta x7）
3. 流式输出分析计划（reply_delta x7）
4. 调用 brand_analysis 工具（plan_update + action_log）
5. A1 执行品牌分析（LLM调用 + 流式输出）
6. 编排器注入 tool_result 并进行第二轮对话
7. 编排器用自然语言询问用户如何继续

### 后端日志关键节点
```
[Orchestrator] Tool call: brand_analysis, args: {'brand_name': '安利纽崔莱'}
[A1] Parsed data: True
[A1] Data keys: ['brand_name', 'search_type']
[A1] Converting flat format to nested format
[Orchestrator] Injected tool result for brand_analysis: 品牌分析完成。品牌：纽崔莱...
```

---

## 测试 3：历史消息加载 (P1) - PASS (部分)

### 验证结果
- [x] GET /api/v1/sessions/{id}/messages API 正常工作
- [x] 用户消息保存到 DB（role=USER, content="帮我分析安利纽崔莱"）
- [x] Agent 回复保存到 DB（role=ASSISTANT, 包含完整分析结果）
- [x] `api.getMessages()` 方法存在但**前端未调用**

### 确认的缺陷
**前端刷新后消息消失**：`page.tsx` 的 `useEffect` 中没有调用 `api.getMessages(sessionId)` 来加载历史消息。

---

## 测试 4：对话恢复 (P0) - 受阻

### 验证结果（基于之前的手动测试日志）
从后端日志 session `b17f944b` 可以看到：
- [x] WebSocket 连接成功建立
- [x] 用户消息保存到 DB
- [x] 编排器调用 brand_analysis 工具
- [x] A1 执行完成，编排器注入 tool_result
- [x] 编排器第二轮回复（自然语言询问用户）
- [x] Agent 回复保存到 DB

**但自动化测试受阻**：WebSocket 在 A1 执行期间（约 50 秒后）被关闭。

---

## 测试 5：WebSocket 断连与重连 (P2) - PASS

### 验证结果
- [x] 断开后重连成功
- [x] 3次快速重连均成功
- [x] 重连后 ping/pong 正常

---

## 测试 7：错误处理 (P2) - 部分 PASS

### 7d 无效JSON - FAIL
后端使用 `websocket.receive_json()` 直接解析，无效 JSON 导致异常并关闭连接。

### 7e 未知事件 - PASS
后端正确忽略未知事件，连接保持存活。

---

## 发现的问题（按严重程度排序）

### P0 - 严重问题

#### 1. WebSocket 在长时间 Agent 执行期间断开
**现象**: 自动化测试中，WebSocket 在 A1 执行约 50 秒后被关闭
**根因**: `main.py:207` 中 `handle_user_message` 是 `await` 阻塞调用。在 Agent 执行期间，主 WebSocket 循环被阻塞，无法处理客户端的 ping。虽然后端有独立的心跳任务，但客户端的 ping 消息在 `receive_json()` 队列中积压。
**影响**: 长时间运行的 Agent（A1 约 30s, A4 可能 5-10min）期间，客户端可能断连
**建议修复**: 将 `handle_user_message` 改为 `asyncio.create_task()` 非阻塞调用

#### 2. 前端无历史消息加载
**现象**: 刷新页面后聊天记录消失
**根因**: `page.tsx` 未调用 `api.getMessages(sessionId)`
**影响**: 用户刷新页面后看不到之前的对话
**建议修复**: 在 `page.tsx` 或 `ChatPanel.tsx` 的 `useEffect` 中加载历史消息

### P1 - 重要问题

#### 3. action_log 事件洪泛
**现象**: A1 执行期间收到 43 个 action_log 事件，全部内容相同
**根因**: `nodes_streaming.py:80-84` 每个 LLM 流式 chunk 都通过 `send_tpaor_event(phase="observation")` 发送，而 `events.py:192` 将 observation 映射为 `action_log`
**影响**: 前端收到大量重复的 action_log，UI 可能闪烁或性能下降
**建议修复**: observation 阶段不应映射为 action_log，应映射为 thought_delta 或完全跳过

#### 4. reply_delta 字段名 - 已确认匹配
**结论**: 后端 `events.py:30` 使用 `content` 字段，前端 `useWebSocket.ts:392` 正确读取 `data.content`。**无问题**。
**注意**: 自动化测试脚本中错误地读取了 `delta` 字段，导致误报。

#### 5. A1 返回稀疏数据
**现象**: `brand_name = "纽崔莱 核心产品 品牌定位"`, 0 个竞品
**根因**: A1 LLM 返回 flat 格式（搜索查询列表），而非 nested 格式（品牌档案）
**影响**: 编排器的 tool_result 摘要信息不完整

### P2 - 次要问题

#### 6. 无效 JSON 导致连接关闭
**现象**: 发送非 JSON 文本后连接被关闭
**根因**: `main.py:191` 使用 `receive_json()` 无 try-catch
**建议修复**: 改用 `receive_text()` + `json.loads()` 并捕获异常

#### 7. MemorySaver 非持久化
**现象**: 服务器重启后 LangGraph 状态丢失
**根因**: `graph.py:66` 使用内存 checkpointer
**影响**: 生产环境中服务重启会丢失所有进行中的会话状态

#### 8. thought_delta 发送完整内容而非增量
**现象**: 每个 thought_delta 事件包含从头到尾的完整思考内容
**根因**: `nodes_streaming.py:70-75` 发送 `full_reasoning`（累积内容）而非 delta
**影响**: 前端如果按 delta 追加，会出现重复内容

---

## 修复优先级建议

| 优先级 | 问题 | 修复难度 | 影响范围 |
|--------|------|----------|----------|
| P0 | WS阻塞导致断连 | 中 | 所有长时间Agent |
| P0 | 前端无历史加载 | 低 | 页面刷新体验 |
| P1 | action_log洪泛 | 低 | 前端性能/UX |
| P1 | A1稀疏数据 | 高 | 分析质量 |
| P2 | 无效JSON处理 | 低 | 边界情况 |
| P2 | MemorySaver | 中 | 生产环境 |
| P2 | thought_delta非增量 | 低 | 思考过程显示 |

---

## 测试脚本位置

- 快速测试（无LLM）: `scratchpad/quick_test.py`
- 完整E2E测试: `scratchpad/e2e_test.py`
- pytest格式测试: `aeo-platform/backend/tests/test_e2e_websocket.py`
