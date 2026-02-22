## 执行计划

### Step 1: 创建统一数据结构
**文件**: `backend/app/schemas/fetch.py`

定义 Pydantic Schema：
- `Platform` - 平台枚举 (DOUBAO, HUNYUAN, KIMI, DEEPSEEK)
- `FetchMethod` - 抓取方式枚举 (API, BROWSER)
- `SearchReference` - 搜索引用数据结构
- `FetchResult` - 单条抓取结果
- `FetchInput` - 输入配置
- `FetchOutput` - 输出结果
- `FetchEventType` / `FetchEvent` - 事件流

### Step 2: 创建 Fetcher 基类和结构
**目录**: `backend/app/core/fetchers/`

创建基础结构：
- `base.py` - 通用基类和结构
- `api/base_client.py` - API Client 基类
- `browser/base_handler.py` - Browser Handler 基类
- `browser/agent_browser.py` - agent-browser CLI 封装

### Step 3: 实现 API Fetchers
**文件**: 
- `backend/app/core/fetchers/api/doubao_client.py` - 豆包 API 客户端
- `backend/app/core/fetchers/api/hunyuan_client.py` - 混元 API 客户端

实现要点：
- 豆包：调用 Responses API，解析 web_search_call 结果
- 混元：调用 OpenAI 兼容接口，解析 search_info 字段
- 统一的 LLMResponse 格式

### Step 4: 实现 Browser Fetchers
**文件**:
- `backend/app/core/fetchers/browser/deepseek_handler.py` - DeepSeek 浏览器处理器
- `backend/app/core/fetchers/browser/kimi_handler.py` - Kimi 浏览器处理器

实现要点：
- 使用 agent-browser CLI 进行浏览器自动化
- 状态流管理（initializing → navigating → checking_login → ... → completed）
- 事件流产出（用于 SSE 推送）
- 登录状态检测和处理

### Step 5: 实现统一 FetchAgent
**文件**: `backend/app/agents/fetch_agent.py`

实现 `FetchAgent` 类：
- 继承 `AEOAgentBase`
- `agent_id = "A4"`
- 平台路由配置（API vs Browser）
- `fetch()` 方法：异步生成器，产出事件流
- `_fetch_via_api()`：高并发 API 抓取
- `_fetch_via_browser()`：低并发浏览器抓取
- 统计信息计算

### Step 6: 创建系统提示词
**文件**: `backend/prompts/fetch_agent.md`

包含：
- Agent 角色定义
- 平台接入方式说明
- API 调用规范（豆包、混元）
- Browser Agent 调用规范（DeepSeek、Kimi）
- 输出格式定义
- 错误处理规范

### 关键设计

**平台路由**:
| 平台 | 方式 | 并发 |
|------|------|------|
| 豆包 | API | 高 (10+) |
| 混元 | API | 高 (10+) |
| Kimi | Browser | 低 (2) |
| DeepSeek | Browser | 低 (2) |

**事件流**:
- PROGRESS - 进度更新
- PLATFORM_START - 开始抓取平台
- PLATFORM_COMPLETE - 平台抓取完成
- BROWSER_STATE - 浏览器详细状态
- COMPLETE - 全部完成
- ERROR - 错误

请确认此计划后，我将开始执行具体的代码实现。