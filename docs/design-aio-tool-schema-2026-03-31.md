# Specta AIO Tool Schema 设计

> 日期：2026-03-31
> 状态：Draft
> 目标：将 AIO Sandbox 的原子能力收口为 Specta 可控、可审计、可路由的工具层，使节点 Agent 能按状态选择工具，而不是在业务层直接依赖底层 CDP/MCP 接口。
> 2026-04-12 更新：AIO Answer Fetch 的生产级归位见 [AIO Answer Fetch Tool 架构归位](./architecture-aio-answer-fetch-tool-runtime-2026-04-12.md)。本文件继续描述工具 schema，但应以 `AIO Tool Facade -> runtime atomic tools` 的方式理解。

---

## 1. 一句话结论

Specta 不应把 AIO 的底层能力直接裸暴露给业务 Agent。  
正确做法是建立四层抽象：

1. `AIO 原子能力`
2. `Specta Tool Schema / Tool Facade`
3. `Platform Execution Contract`
4. `Node Agent / Orchestrator 决策`

其中：

1. `AIO 原子能力` 提供浏览器、文件、代码、接管等基本动作
2. `Specta Tool Schema / Tool Facade` 把这些能力封装成稳定工具，例如 `aio_answer_fetch`
3. `Platform Execution Contract` 描述四个平台如何使用这些工具
4. `Agent` 决定是否调用 AIO Tool，以及如何处理其 event / result packet

本设计中的共享状态词、路径术语和职责边界以 [design-aio-runtime-contracts-2026-04-01.md](./design-aio-runtime-contracts-2026-04-01.md) 为准。

补充边界：

1. `AIO Answer Fetch Tool` 是 A4 / Fetch Answer Agent 调用的浏览器执行 Tool Facade。
2. 它默认覆盖豆包、元宝、Kimi、DeepSeek 四个平台。
3. 它内部可以调用 browser action、file、takeover、state、trace 等原子工具。
4. 它不是新的 public skill，也不应该把 CDP/MCP/tab/page 细节暴露给业务 Agent。
5. 普通页面阻塞应由 AIO Browser Agent 自动处理；登录、验证码、人机验证才返回 `takeover_required`。

---

## 2. 设计原则

## 原则 1：先定义稳定工具，再接具体运行时

工具名、参数结构、返回结构、错误结构都应由 Specta 定义。  
底层可以是：

1. AIO REST API
1. AIO MCP
2. CDP
3. GUI action
4. Shell/Python/Node

但这些都不应该直接成为业务层契约。

## 原则 2：工具按“意图层级”分组，而不是按底层 API 分组

例如：

1. `aio_browser_perceive_page`
2. `aio_browser_click_element`
3. `aio_browser_extract_answer`

这些工具是 Specta 的业务意图工具。  
底层是否通过 `browser_get_clickable_elements`、CDP DOM、GUI action 实现，是工具层自己的事。

## 原则 3：工具必须可审计

每次工具调用至少要记录：

1. `tool_name`
2. `session_id`
3. `task_id`
4. `platform`
5. `request_payload`
6. `result_summary`
7. `error_type`
8. `duration_ms`

## 原则 4：所有工具都必须对接 artifact/state

工具不能只返回一段文本然后消失。  
关键结果要能够落到：

1. runtime state
2. `profile_root` / `run_root`
   - `data_root = <home_dir>/data`
   - `profile_root = <data_root>/<workspace>/<platform>/profile`
   - `run_root = <data_root>/<task>/<platform>/run`
   - `home_dir` 由 `GET /v1/sandbox` 返回
3. artifact/version 系统

---

## 3. 官方能力映射（基于指南/API/examples）

在接入 AIO 时，应优先依赖官方已经稳定公开的入口，而不是自己猜内部实现。

### 3.1 浏览器

官方明确公开的浏览器入口包括：

1. `GET /v1/browser/info`
   - 返回浏览器信息与 `cdp_url`
2. `GET /cdp/json/version`
   - 用于获取 CDP 端点信息
3. `GET /v1/browser/screenshot`
   - GUI 截图（带 Tabs 的完整浏览器窗口）
4. `POST /v1/browser/actions`
   - GUI 原子动作执行
5. `POST /v1/browser/page/*`
   - 高层页面动作，如 navigate / click / fill / type / press_key / select_option / fill_form / upload_file / scroll
6. `GET|POST|DELETE /v1/browser/cookies`
   - cookie 读写与清理
7. `POST /v1/browser/state/save` 与 `POST /v1/browser/state/load`
   - 浏览器状态持久化
8. `GET|POST|DELETE /v1/browser/tabs/*`
   - tab 管理
9. `POST|GET /v1/browser/network/*`
   - headers / route / requests / HAR
10. `GET|POST /v1/browser/captcha/*`
    - captcha 检测与等待
11. `POST /v1/browser/restart`
    - 浏览器重启

### 3.2 接管

1. `GET /vnc/index.html`
2. `POST /tickets`
   - 用于生成短时 ticket 访问 VNC 等无法带 Header 的页面
3. `@agent-infra/browser-ui`
   - 官方前端组件，用于 `Canvas + CDP` 接管

### 3.3 文件

官方指南确认的文件入口至少包括：

1. `POST /v1/file/read`
2. `POST /v1/file/write`
3. `POST /v1/file/find`
4. `POST /v1/file/replace`

### 3.4 Shell

官方指南确认：

1. `WS /v1/shell/ws`
   - 支持 session 复连、历史恢复、心跳
2. `shell session` 与受控终端调试入口
   - 返回可嵌入或外跳的终端访问地址
3. `POST /v1/shell/sessions/create`
   - 创建持久会话
4. `POST /v1/shell/sessions/update`
   - 更新持久会话

官方 examples 还展示了：

5. `POST /v1/shell/exec`
   - 用于一次性 shell 执行
6. `POST /v1/shell/view` / `wait` / `write` / `kill`
   - 用于过程观察、等待、输入与中断

### 3.5 Bash

OpenAPI 还公开了独立的 `bash` 组：

1. `POST /v1/bash/exec`
2. `POST /v1/bash/output`
3. `POST /v1/bash/write`
4. `POST /v1/bash/kill`
5. `GET /v1/bash/sessions`
6. `POST /v1/bash/sessions/create`
7. `POST /v1/bash/sessions/{session_id}/close`

这说明官方把：

1. `shell`
   - 更偏交互式、终端式、可恢复
2. `bash`
   - 更偏命令式、进程式、执行控制

已经在 API 层做了分工。

### 3.6 文件

OpenAPI 公开的文件能力比 guide 摘要更完整，至少包括：

1. `read`
2. `write`
3. `replace`
4. `search`
5. `find`
6. `grep`
7. `glob`
8. `upload`
9. `download`
10. `list`
11. `str_replace_editor`

### 3.7 Jupyter / Node.js / Code

OpenAPI 显示 AIO 不是只提供 Python 一次性执行，而是有三层代码/计算能力：

1. `code`
   - `POST /v1/code/execute`
   - `GET /v1/code/info`
2. `nodejs`
   - `execute/info`
   - `sessions` 的创建、查询、更新、删除
3. `jupyter`
   - `execute/info`
   - notebook session 的创建、列举、清理

因此 Specta 在“代码工具”层不应只考虑 Python snippet，也要保留：

1. Node.js session 级执行
2. Jupyter notebook 级执行
3. 一次性 code execute

### 3.8 MCP / skills / util

官方指南确认 `/mcp` 是聚合入口，至少包含：

1. browser server
2. file server
3. terminal server
4. markitdown server

OpenAPI 还公开了：

1. `skills`
   - register / metadata / clear / delete / content
2. `util`
   - `convert_to_markdown`

这意味着 AIO 在产品形态上已经开始支持“工具 + skill 元数据”，但对 Specta 来说，这些仍然应该被视为底层运行时能力，不直接等价于 Specta 自己的 Skill Contract。

### 3.9 预览 / 控制面板 / 鉴权

1. `/index.html`
   - 控制面板
2. `/code-server/`
   - VSCode Server
3. `/proxy/{port}` / `/absproxy/{port}` / `${port}-${domain}`
   - 服务预览代理
4. `POST /tickets`
   - 票据换取
5. `GET /auth`
   - 鉴权验证

### 3.10 接入建议

虽然官方文档同时出现了：

1. `/cdp/json/version`
2. browser-ui 示例中的 `/json/version`

为了避免路径差异、反代差异、鉴权差异带来的歧义，  
Specta 接入时应统一以：

1. `GET /v1/browser/info`

作为获取 `cdp_url` 的标准入口，而不是在业务代码里硬编码具体的 CDP 路径。

此外，Specta 的默认调用优先级应写死为：

1. `REST-first`
   - 优先复用 AIO 已提供的高层稳定接口
2. `CDP-second`
   - 用于细粒度控制、browser-ui 接管、DOM/网络深度能力
3. `MCP-third`
   - 用于统一聚合接入或在 Agent/Tool 环境中做标准化调用
4. `VNC/browser-ui`
   - 仅用于 human-in-the-loop 接管，不作为默认自动化执行通道

---

## 4. 工具分层

## 3.1 Session 工具

用于管理 AIO sandbox 与平台会话。

### `aio_answer_fetch`

用途：

1. 作为 Fetch Answer Agent / A4 调用 AIO 的主入口。
2. 创建四平台 answer fetch job。
3. 返回平台级 event 和最终 result packet。

输入：

```json
{
  "job_id": "answer_fetch_job_123",
  "session_id": "specta_session_1",
  "task_id": "task_789",
  "entity_id": "entity_456",
  "specta_user_id": "user_123",
  "brand": "雅姿",
  "questions": [
    {
      "question_id": "q1",
      "text": "30岁刚开始抗老，有什么推荐？"
    }
  ],
  "platforms": ["doubao", "yuanbao", "kimi", "deepseek"],
  "execution_mode": "full_browser",
  "auth_scope": "prod/user_123",
  "run_scope": "entity_456/task_789"
}
```

输出：

```json
{
  "job_id": "answer_fetch_job_123",
  "status": "completed",
  "platform_results": {
    "doubao": {"status": "succeeded"},
    "yuanbao": {"status": "succeeded"},
    "kimi": {"status": "skipped"},
    "deepseek": {"status": "succeeded"}
  }
}
```

关键事件：

```text
platform_started
blocker_detected
auto_action_taken
takeover_required
platform_result
job_completed
```

实现要求：

1. 默认四平台整体调度，不允许只围绕局部平台实现。
2. 普通弹窗和页面恢复先自动处理。
3. 人工接管 surface 必须是 AIO 已准备好的阻塞现场。
4. 登录态保存到 AuthContext，任务结果保存到 RunContext。

### `aio_session_acquire`

用途：

1. 获取或创建当前 workspace 的 AIO sandbox session

输入：

```json
{
  "workspace_id": "uuid",
  "task_id": "uuid",
  "purpose": "a4_fetch",
  "platforms": ["deepseek", "doubao", "yuanbao", "kimi"]
}
```

输出：

```json
{
  "sandbox_id": "sbx_xxx",
  "session_id": "sess_xxx",
  "connected": true,
  "capabilities": {
    "browser": true,
    "gui_actions": true,
    "code_exec": true,
    "file_io": true,
    "takeover": true,
    "shell_terminal": true,
    "nodejs": true,
    "jupyter": true,
    "code_server": true,
    "proxy_preview": true,
    "ticket_auth": true
  }
}
```

### `aio_session_release`

用途：

1. 释放当前任务对 sandbox 的占用
2. 不默认销毁浏览器或状态

### `aio_session_destroy`

用途：

1. 在任务真正结束、超时、清理策略命中时销毁 sandbox

---

## 3.2 Browser 感知工具

用于感知页面、标签页和交互元素。

### `aio_browser_get_window_state`

返回：

1. 当前活动 tab
2. tab 列表
3. 当前 URL
4. 页面标题
5. 是否存在多窗口

### `aio_browser_perceive_page`

用途：

1. 获取当前 page 的结构化感知结果

输出建议包含：

1. `url`
2. `title`
3. `visible_text_summary`
4. `interactive_elements`
5. `screenshot_path`
6. `dom_snapshot_path`
7. `page_state_tags`

其中 `page_state_tags` 建议标准化成：

1. `login_required`
2. `captcha_required`
3. `input_ready`
4. `answer_streaming`
5. `answer_complete`
6. `reference_expandable`
7. `error_banner_present`

### `aio_browser_find_elements`

用途：

1. 按文本、角色、selector、视觉区域查找候选元素

---

## 3.3 Browser 动作工具

用于执行页面内操作。

### `aio_browser_navigate`

用途：

1. 打开目标 URL
2. 支持 `wait_until`

### `aio_browser_click_element`

优先实现顺序：

1. CDP/DOM 定位点击
2. 失败后 GUI action 点击

### `aio_browser_fill_input`

优先实现顺序：

1. DOM fill
2. 失败后 GUI TYPING

### `aio_browser_press_key`

### `aio_browser_scroll`

### `aio_browser_open_new_tab`

### `aio_browser_switch_tab`

### `aio_browser_manage_tabs`

用途：

1. 获取 tab 列表
2. 激活 tab
3. 关闭 tab

### `aio_browser_set_form_or_upload`

用途：

1. 统一封装 `fill_form`
2. 统一封装 `upload_file`

### `aio_browser_set_interaction_mode`

用途：

1. 设置浏览器 config
2. 控制 viewport / user agent / 交互策略

---

## 3.4 Browser 会话、状态与网络工具

这些工具直接对应官方 browser 组中比我们之前预想更完整的会话能力。

### `aio_browser_manage_cookies`

用途：

1. 获取当前 cookies
2. 写入 cookies
3. 清理 cookies

### `aio_browser_manage_state`

用途：

1. 保存浏览器状态
2. 加载浏览器状态

### `aio_browser_set_network_policy`

用途：

1. 设置 extra headers
2. 设置 scoped headers
3. 添加或移除 network route

### `aio_browser_capture_requests`

用途：

1. 获取请求列表
2. 导出 HAR
3. 供平台 Skill 做 network-aware 提取与诊断

### `aio_browser_detect_captcha`

用途：

1. 直接调用官方 captcha detect / wait 能力
2. 作为人工接管前的标准化判断

---

## 3.5 Browser 结果提取工具

这是 Specta 的核心业务工具，不应继续散落在各 handler 中。

### `aio_browser_extract_answer`

用途：

1. 从当前平台页面提取回答正文

输出：

```json
{
  "answer_text": "...",
  "word_count": 1234,
  "is_partial": false,
  "source": "dom|network|hybrid"
}
```

### `aio_browser_extract_references`

用途：

1. 提取引用/来源链接

### `aio_browser_extract_error_state`

用途：

1. 识别登录失败、平台报错、限流、验证提示

输出错误类型建议标准化：

1. `login_required`
2. `captcha_required`
3. `rate_limited`
4. `platform_error`
5. `network_error`
6. `unknown_error`

---

## 3.6 Takeover 工具

用于请求人工接管与恢复自动执行。

### `aio_browser_request_takeover`

用途：

1. 生成接管会话
2. 返回 browser-ui URL 和 VNC fallback URL

输出：

```json
{
  "takeover_id": "takeover_xxx",
  "mode": "canvas_cdp",
  "canvas_url": "https://...",
  "vnc_url": "https://...",
  "reason": "login_required"
}
```

### `aio_browser_wait_takeover_resolution`

用途：

1. 等待用户完成登录/验证码/人工确认

### `aio_browser_check_takeover_ready`

用途：

1. 接管结束后复检页面是否恢复可执行

---

## 3.7 状态持久化工具

### `aio_browser_save_platform_state`

用途：

1. 将当前平台状态写入 `data_root/<workspace>/<platform>/`

输出文件建议包括：

1. `cookies.json`
2. `local_storage.json`
3. `session_meta.json`
4. `last_page_snapshot.json`

### `aio_browser_restore_platform_state`

用途：

1. 从持久目录恢复当前平台状态

### `aio_browser_validate_state`

用途：

1. 判断恢复后的状态是否仍有效

---

## 3.8 文件、终端与代码工具

这些工具允许 AIO 的代码能力进入 Specta，但必须受控。

### 文件工具

1. `aio_fs_read_text`
2. `aio_fs_write_json`
3. `aio_fs_list_dir`
4. `aio_fs_wait_file_ready`
5. `aio_fs_find_files`
6. `aio_fs_grep_files`
7. `aio_fs_upload_file`
8. `aio_fs_download_file`
9. `aio_fs_str_replace`

### 终端工具

1. `aio_shell_exec`
2. `aio_shell_open_session`
3. `aio_shell_write`
4. `aio_shell_wait`
5. `aio_shell_kill`
6. `aio_shell_get_terminal_url`
7. `aio_bash_exec`

### 代码工具

1. `aio_python_run_snippet`
2. `aio_node_run_snippet`
3. `aio_node_session_run`
4. `aio_jupyter_run_cell`
5. `aio_code_execute_once`
6. `aio_cookie_merge_validate`
7. `aio_parse_downloaded_file`
8. `aio_convert_to_markdown`

执行规则：

1. 必须有超时
2. 只能在受限工作目录运行
3. 只能访问允许的路径
4. 输出必须写到显式文件
5. 错误必须标准化返回

---

## 4. 工具输入输出规范

## 4.1 统一输入信封

所有工具都建议接受统一信封：

```json
{
  "workspace_id": "uuid",
  "task_id": "uuid",
  "session_id": "uuid",
  "platform": "deepseek",
  "sandbox_id": "sbx_xxx",
  "payload": {}
}
```

## 4.2 统一输出信封

```json
{
  "ok": true,
  "tool_name": "aio_browser_perceive_page",
  "platform": "deepseek",
  "result": {},
  "artifacts": [],
  "warnings": [],
  "error": null
}
```

## 4.3 标准错误结构

```json
{
  "code": "captcha_required",
  "message": "页面检测到验证码，需人工接管",
  "retryable": true,
  "needs_takeover": true
}
```

---

## 5. 工具调用策略

## 5.1 Agent 可以决定何时调用工具

但 Agent 不应直接自由组合所有底层动作。  
应通过 `Platform Skill Contract` 约束：

1. 哪些工具允许在该平台使用
2. 工具的优先顺序
3. 哪些错误应触发人工接管

## 5.2 优先策略

统一建议：

1. `先感知`
2. `再判断`
3. `再动作`
4. `动作后再感知`
5. `必要时接管`
6. `接管后复检`

也就是典型的：

`perceive -> decide -> act -> observe -> recover`

---

## 6. 与现有代码的映射

## 6.1 当前可复用点

1. [playwright_client.py](../aeo-platform/backend/app/core/fetchers/browser/playwright_client.py)
2. [deepseek_handler.py](../aeo-platform/backend/app/core/fetchers/browser/deepseek_handler.py)
3. [nodes_a4.py](../aeo-platform/backend/app/workflow/nodes_a4.py)
4. [browser_action_runtime.py](../aeo-platform/backend/app/workflow/browser_action_runtime.py)

## 6.2 当前需要改造点

1. 不再让 handler 直接依赖具体 `PlaywrightBrowserClient`
2. 将 handler 中的平台逻辑上移为 `Platform Skill Contract`
3. 将页面操作和状态恢复动作下沉为 `Specta AIO Tools`

---

## 7. 非目标

1. 不在 V1 暴露任意脚本执行给业务 Agent
2. 不让节点 Agent 自己发明新的工具名字
3. 不允许工具直接写 Git 仓库源码文件
4. 不在 V1 提供“任意站点通用全能浏览器代理”

---

## 8. 相关文档

本工具文档现已与以下文档组成完整 AIO 设计包：

1. `四平台 Skill Contract`
2. `AioSandboxSessionManager`
3. `AIO 前端接管协议`
4. `AioSandboxBackend`
5. `A4 AIO 路由`
6. `Session 持久化模型`
7. `Access Relay 与安全边界`
8. `前端接管 UI`
9. `验证 / 运维 / 成本`
