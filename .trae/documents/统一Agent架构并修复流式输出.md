## 修复步骤

### 步骤 1：修改 ToolRegistryV2.execute() 支持流式输出
**文件：** `app/tools/registry_v2.py` 第 228-279 行
- 检测 Tool 是否有 `execute_with_progress` 方法
- 使用流式执行并 yield 进度事件

### 步骤 2：修改 llm_orchestrator.py 使用 ToolRegistryV2
**文件：** `app/agents/llm_orchestrator.py` 第 574-633 行
- 替换 `asyncio.to_thread(agent.run, ...)` 为 `ToolRegistryV2.execute()`
- 将 Tool 事件流转换为 `AgentEvent`

### 步骤 3：为 A2-A5 Tools 添加 execute_with_progress
**文件：** `a2_marketing_persona.py`, `a3_question_simulation.py`, `a4_fetch_agent.py`, `a5_data_analytics.py`
- 参照 A1 实现，添加流式执行方法

### 步骤 4：统一事件格式
- ToolProgress → AgentEvent 转换
- 映射进度到 TPAOR 阶段

### 步骤 5：修复 JSON 解析错误
**文件：** `app/agents/utils.py`
- 增强 `extract_json_from_content()` 容错能力

## 预期结果
1. A1-A5 执行时有流式进度输出到前端
2. JSON 解析错误被正确处理
3. 架构统一使用 Mini-Agent Tool 模式