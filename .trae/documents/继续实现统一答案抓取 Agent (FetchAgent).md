我已经完成了 Step 1（创建统一数据结构 schemas/fetch.py）。

现在需要继续执行：

### Step 2: 创建 Fetcher 基类和结构
**目录**: `backend/app/core/fetchers/`

创建以下文件：
- `__init__.py` - 包初始化
- `base.py` - 通用基类和结构
- `api/__init__.py` - API 包初始化
- `api/base_client.py` - API Client 基类
- `browser/__init__.py` - Browser 包初始化
- `browser/base_handler.py` - Browser Handler 基类
- `browser/agent_browser.py` - agent-browser CLI 封装

### Step 3: 实现 API Fetchers
- `api/doubao_client.py` - 豆包 API 客户端
- `api/hunyuan_client.py` - 混元 API 客户端

### Step 4: 实现 Browser Fetchers
- `browser/deepseek_handler.py` - DeepSeek 浏览器处理器
- `browser/kimi_handler.py` - Kimi 浏览器处理器

### Step 5: 实现统一 FetchAgent
- `agents/fetch_agent.py` - 统一 FetchAgent

### Step 6: 创建系统提示词
- `prompts/fetch_agent.md`

请确认后，我将继续执行这些步骤。