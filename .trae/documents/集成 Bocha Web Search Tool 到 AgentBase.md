## 执行计划

### Step 1: 实现 Bocha API 服务层
**文件**: `backend/app/services/bocha_service.py`

实现 `BochaService` 类：
- 从环境变量获取 `BOCHA_API_KEY`
- `search(query, count=10, freshness='noLimit') -> dict` 方法
- 异常处理：超时、4xx/5xx 错误，返回空字典
- 数据清洗：只保留 `name`, `url`, `snippet`, `datePublished`

### Step 2: 定义工具结构
**文件**: `backend/app/tools/search_tool.py`

实现：
- `WEB_SEARCH_SCHEMA`: OpenAI Function Calling 格式的工具描述
- `execute_search(query: str) -> str`: 
  - 调用 `BochaService.search()`
  - 格式化为 Markdown 字符串（紧凑格式，节省 Token）
  - 无结果时返回 "未找到相关信息"

### Step 3: 集成到 Agent 基类
**文件**: `backend/app/agents/base.py`

修改：
- `__init__`: 引入 `WEB_SEARCH_SCHEMA` 并传给 MiniMax client
- `_execute_tool_calls`: 检测 `web_search` 调用
- 执行搜索后将结果构造成 `role: tool` 的 message
- 触发二次生成（Observation -> Response）

### 关键设计

**搜索结果格式化**（节省 Token）：
```markdown
### 搜索结果 (query):
1. [标题](url) - 日期: 摘要...
2. [标题](url) - 日期: 摘要...
```

**错误处理**：
- API 失败时返回友好提示，Agent 使用自身知识回答
- 超时设置：10秒
- 重试机制：最多2次

**工具调用流程**：
1. Agent 生成 Thought/Plan
2. 模型请求调用 `web_search`
3. AgentBase 拦截 tool_call
4. 打印日志并执行搜索
5. 将结果追加到 messages
6. 触发二次生成

请确认此计划后，我将开始执行具体的代码实现。