## 问题
在 llm_orchestrator.py 的 _run_agent 方法中，处理 tool_result 事件时没有使用 ToolResult.content 字段，导致用户看到固定消息而不是实际的执行结果。

## 修复
修改 _run_agent 方法（第637-649行）：
- 从 result_data 中提取 content 字段
- 将 content 作为 message 传递给 AgentEvent
- 如果 content 为空，使用默认消息

## 修改文件
- app/agents/llm_orchestrator.py

## 预期结果
用户将看到 Tool 执行的实际结果内容，而不是固定的"✅ 完成"消息。