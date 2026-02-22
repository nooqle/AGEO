## 执行计划

### 1. 更新配置文件
**文件**: `backend/app/config.py`
- 添加 MiniMax 相关配置项
- MINIMAX_API_KEY
- MINIMAX_BASE_URL (默认: https://api.minimaxi.com/v1)
- MINIMAX_MODEL_NAME (默认: MiniMax-M2.1)
- MINIMAX_REASONING_SPLIT (默认: True)

### 2. 创建 MiniMax 配置类
**文件**: `backend/app/core/minimax_config.py`
- 创建 MiniMaxConfig 配置类
- 管理模型参数 (temperature, max_tokens 等)
- 支持 reasoning_split 开关

### 3. 创建 MiniMax 模型封装
**文件**: `backend/app/core/minimax_model.py`
- 继承 AgentScope 的 ChatModelBase
- 使用 OpenAI 客户端调用 MiniMax API
- 实现关键功能:
  - `__call__()` - 同步调用
  - `async_call()` - 异步调用
  - `format()` - 消息格式化
  - `parse_response()` - 解析 reasoning_details 到 ThinkingBlock
  - `stream()` - 流式输出支持
- 正确处理 reasoning_details 和 tool_calls 的完整回传

### 4. 创建测试脚本
**文件**: `backend/tests/test_minimax.py`
- 测试 API 连通性
- 测试 Thinking 内容解析
- 测试 Tool Calling 功能
- 测试流式输出

### 5. 更新依赖
**文件**: `backend/requirements.txt`
- 添加 `agentscope` 依赖
- 确保 `openai` 版本兼容

### 关键实现要点

1. **reasoning_split 支持**:
   ```python
   extra_body = {"reasoning_split": True}
   ```

2. **ThinkingBlock 转换**:
   ```python
   from agentscope.models import ThinkingBlock
   
   if hasattr(message, "reasoning_details"):
       for detail in message.reasoning_details:
           if detail.get("type") == "reasoning.text":
               thinking_block = ThinkingBlock(text=detail["text"])
   ```

3. **完整回传机制**:
   - 在多轮对话中，assistant 消息必须包含完整的 reasoning_details
   - tool_calls 也必须完整保留

### 文件产出
1. `backend/app/core/minimax_model.py` - 模型封装
2. `backend/app/core/minimax_config.py` - 配置类
3. `backend/tests/test_minimax.py` - 测试脚本
4. 更新 `backend/app/config.py` - 添加配置项
5. 更新 `backend/requirements.txt` - 添加依赖

请确认此计划后，我将开始执行具体的代码实现。