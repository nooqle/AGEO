## 修复计划

### 1. 解决编码问题

**问题分析**：中文字符在 WebSocket 传输中显示为 `???`，可能是 Python 字符串编码或 JSON 序列化问题。

**修复方案**：
- 在 `events.py` 中确保所有字符串都是 UTF-8 编码
- 在 WebSocket 发送前显式处理中文字符
- 可能需要设置 Python 默认编码

### 2. 实现 Human-in-loop 确认功能

**问题分析**：之前移除了 `interrupt()` 调用，因为它需要在 LangGraph 的特定上下文中使用。需要重新实现让用户能够确认信息。

**修复方案**：
采用替代方案，不使用 LangGraph 的 `interrupt()`，而是：

1. **修改工作流结构**：
   - A2 决策节点发送确认请求后，将状态标记为 `waiting_confirmation`
   - 工作流暂停在该节点，等待用户响应
   - 用户通过 WebSocket 发送确认消息后，从该状态继续

2. **实现状态机模式**：
   - 在 `AgentState` 中添加 `pending_confirmation` 字段
   - 决策节点检查是否有待确认的决策，如果有则返回等待状态
   - WebSocket 处理确认消息，更新状态并继续工作流

3. **修改节点逻辑**：
   - `a2_decision_node`：发送确认请求，返回等待状态
   - `a3_decision_node`：发送确认请求，返回等待状态
   - 添加 `handle_confirmation` WebSocket 事件处理

4. **WebSocket 集成**：
   - 在 `websocket_langgraph.py` 中处理 `confirmation` 事件
   - 确认消息触发工作流继续执行

### 具体修改文件

1. `app/workflow/state.py` - 添加 pending_confirmation 字段
2. `app/workflow/nodes.py` - 修改 A2 决策节点实现状态机
3. `app/workflow/nodes_a3.py` - 修改 A3 决策节点实现状态机
4. `app/workflow/events.py` - 确保 UTF-8 编码
5. `app/api/v1/websocket_langgraph.py` - 处理确认消息
6. `app/core/websocket_server.py` - 确保 UTF-8 编码

### 验证步骤
1. 测试中文显示正常
2. 测试 A2 步骤确认功能
3. 测试 A3 步骤确认功能
4. 测试完整工作流