# Specta AioSandboxBackend 适配设计

> 日期：2026-03-31
> 状态：Draft
> 目标：把 `AioSandboxBackend` 收敛成 Specta A4 可直接依赖的正式子集，并且只建立在 AIO 官网 guide / OpenAPI 与已验证 runtime 能力之上。

---

## 1. 一句话结论

`AioSandboxBackend` 不是万能 runtime client，而是 Specta A4 的受限执行适配层。

它只负责：

1. 获取和复用 AIO runtime
2. 用官方已存在的 transport 执行浏览器动作
3. 把错误映射成 Specta 共享合同
4. 为接管链路提供 handoff 所需能力

它不负责：

1. policy 决策
2. 平台编排
3. follow-up 路由
4. session / takeover 权威状态迁移

本设计中的状态词和职责边界以
[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
为准。

---

## 2. 官方依据

### 2.1 official guide

1. [Introduction](https://sandbox.agent-infra.com/zh/guide/start/introduction)
2. [Quick Start](https://sandbox.agent-infra.com/zh/guide/start/quick-start)
3. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)
4. [Shell](https://sandbox.agent-infra.com/zh/guide/basic/shell)
5. [File](https://sandbox.agent-infra.com/zh/guide/basic/file)
6. [Authentication](https://sandbox.agent-infra.com/zh/guide/basic/authentication)

### 2.2 official openapi

基于当前 runtime `GET /v1/openapi.json` 已验证存在的接口：

1. `GET /v1/sandbox`
2. `GET /v1/browser/info`
3. `GET /v1/browser/config`
4. `POST /v1/browser/actions`
5. `GET /v1/browser/screenshot`
6. `POST /v1/file/read`
7. `POST /v1/file/write`
8. `POST /v1/file/list`
9. `POST /v1/file/find`
10. `POST /v1/file/search`
11. `GET /v1/file/download`
12. `POST /v1/file/upload`
13. `POST /v1/file/replace`
14. `POST /v1/shell/exec`
15. `POST /v1/shell/view`
16. `POST /v1/shell/wait`
17. `POST /v1/shell/write`
18. `POST /v1/shell/kill`
19. `POST /v1/shell/sessions/create`
20. `GET /v1/shell/sessions`
21. `GET /v1/shell/sessions/{session_id}`
22. `GET /v1/shell/terminal-url`
23. `POST /v1/code/execute`

### 2.3 best-practice article

1. [AgentRun/AIO 实践 1](https://www.cnblogs.com/alisystemsoftware/p/19646364)
2. [AIO 浏览器接管实践 2](https://segmentfault.com/a/1190000047359831)

### 2.4 Specta wrapper decision

1. `REST-first / CDP-second / MCP-third`
2. `Canvas 为主，VNC 为 fallback`
3. `A4 V1 公开路径不直接暴露 shell/file/code`

---

## 3. 现实接口边界

当前接入必须接受这个事实：

1. 我们的 AIO runtime 没有公开 `page/*`
2. 也没有公开 `tabs/cookies/state/save/state/load/captcha/network/*`
3. 浏览器公开面主要是：
   - `browser/info`
   - `browser/actions`
   - `browser/screenshot`
4. 更细粒度浏览器能力来自：
   - `CDP`
   - `browser-ui`
5. 文件、终端、代码执行走各自 REST
6. `browser/config`、`file/download/upload/replace`、`shell/sessions/*` 虽然存在，但 V1 只在 internal capability 范围内按需使用

因此，AioSandboxBackend 不能按不存在的高层 browser REST 设计。

---

## 4. 职责边界

### 4.1 Backend Adapter 负责

1. `ensure_runtime`
2. `ensure_platform_roots`
3. `execute_action`
4. `take_screenshot`
5. `handoff_takeover`
6. `save_runtime_state`
7. `load_runtime_state`
8. `map_error`

### 4.2 Backend Adapter 不负责

1. `blocker_code -> policy_decision`
2. 选择抓哪个平台
3. 解释业务结果
4. 维护前端 takeover UI 状态
5. 直接写 `session_state / takeover_state`

---

## 5. A4VisibleBrowserSubset

A4 V1 对 AIO backend 的正式依赖只有这五类：

1. `navigation / interaction`
2. `perception`
3. `extraction`
4. `state save/load`
5. `takeover handoff`

### 5.1 navigation / interaction

来源：

1. `official openapi`
   - `POST /v1/browser/actions`
2. `Specta wrapper decision`
   - 所有点击、输入、滚动、等待统一包成动作载荷

### 5.2 perception

来源：

1. `official openapi`
   - `GET /v1/browser/screenshot`
2. `official openapi`
   - `GET /v1/browser/info`
3. `Specta wrapper decision`
   - 需要更深页面判断时，走受控 CDP，不臆造高层 REST

### 5.3 extraction

来源：

1. `Specta wrapper decision`
   - A4 的提取 contract 由 handler 负责
2. `official openapi`
   - 浏览器截图
   - 文件读写
   - 受控代码执行

解释：

1. AIO runtime 不直接提供“答案提取”高层接口
2. Specta 需要在 handler 或受控代码工具里完成抽取
3. 一旦抽取成功，必须通过 `POST /v1/file/write` 将统一提取 artifact 写入 `run_root/extraction.json`

### 5.4 state save/load

来源：

1. `best-practice article`
   - 文件系统传状态
   - browser connect/disconnect 后复用 profile
2. `official openapi`
   - `file/read|write|list|find`
3. `Specta wrapper decision`
   - `browser_state.json / cookies.json / session_meta.json` 由 Specta 自己管理

### 5.5 takeover handoff

来源：

1. `official guide`
   - browser-ui / VNC
2. `official openapi`
   - `browser/info`
3. `official guide`
   - `authentication`
4. `Specta wrapper decision`
   - 前端不直连原始 `cdp_url`

---

## 6. Transport 优先级

### 6.1 REST-first

默认优先：

1. `browser/actions`
2. `browser/screenshot`
3. `file/*`
4. `shell/*`
5. `code/execute`

原因：

1. 官方已提供
2. 请求可审计
3. 失败模式更清晰

### 6.2 CDP-second

只在这些场景启用：

1. browser-ui Canvas 接管
2. 需要 live DOM/Tab 状态但 REST 不提供
3. handler 的 readiness probe 需要轻量页面探针

### 6.3 MCP-third

V1 只保留为后续扩展入口，不进入 A4 主执行路径。

原因：

1. 当前 AIO runtime 已有足够 REST 能力
2. MCP 会扩大调用面和排错面

---

## 7. tool -> capability -> transport -> caller 映射表

| tool_name | required_capability | transport | allowed_caller | customer_exposed? | source_type |
| --- | --- | --- | --- | --- | --- |
| `aio_browser_execute_action` | navigation / interaction | `POST /v1/browser/actions` | A4 handler / resume gate | 否 | official openapi |
| `aio_browser_take_screenshot` | perception | `GET /v1/browser/screenshot` | A4 handler / QA | 否 | official openapi |
| `aio_browser_get_runtime_info` | runtime inspect | `GET /v1/browser/info` | SessionManager / relay | 否 | official openapi |
| `aio_browser_connect_canvas` | takeover canvas | `cdp-relay -> cdp_url` | frontend browser canvas | 是 | official guide + Specta wrapper decision |
| `aio_browser_get_vnc_fallback` | takeover fallback | `ticket + vnc redirect` | frontend browser canvas | 是 | official guide + official runtime behavior |
| `aio_runtime_read_file` | state save/load | `POST /v1/file/read` | SessionManager / adapter internal | 否 | official openapi |
| `aio_runtime_write_file` | state save/load | `POST /v1/file/write` | SessionManager / adapter internal | 否 | official openapi |
| `aio_runtime_list_files` | state inspect | `POST /v1/file/list` | SessionManager / QA | 否 | official openapi |
| `aio_runtime_exec_shell` | internal recovery | `POST /v1/shell/exec` | adapter internal | 否 | official openapi |
| `aio_runtime_wait_shell` | internal recovery | `POST /v1/shell/wait` | adapter internal | 否 | official openapi |
| `aio_runtime_execute_code` | controlled extraction helper | `POST /v1/code/execute` | adapter internal / QA tool | 否 | official openapi |

---

## 7.1 Workstream 3 共享执行骨架

为了让四个平台真正共用一条 AIO 执行链，A4 V1 还要求这两个共享约束：

1. `login/modal handoff` 统一由 Base handler 的共享门控原语负责
2. `success extraction persistence` 统一由 Base handler 调用 Backend Adapter 落到 `run_root/extraction.json`

这两个约束的来源类型为：

1. `official openapi`
   - `POST /v1/file/write`
2. `best-practice article`
   - 文件系统传递多步骤状态与结果
3. `Specta wrapper decision`
   - handler 只拼装平台差异，不各自发明状态持久化实现

---

## 8. 错误映射合同

Backend Adapter 的标准错误对象固定为：

```json
{
  "error_code": "runtime_unavailable",
  "recover_hint": "check_runtime_health",
  "transport_used": "rest",
  "retryable": true
}
```

### 字段定义

1. `error_code`
   - 引用共享 `blocker_code`
2. `recover_hint`
   - Specta wrapper decision，表达下一步排障方向
3. `transport_used`
   - `rest | cdp | mcp | relay`
4. `retryable`
   - 当前 transport 是否值得重试

### 映射规则

1. AIO 连不上
   - `error_code=runtime_unavailable`
   - `recover_hint=check_runtime_health`
   - `transport_used=rest`
2. relay 不可达
   - `error_code=runtime_unavailable`
   - `recover_hint=check_takeover_relay`
   - `transport_used=relay`
3. 页面动作失败但页面仍活着
   - `error_code=ui_drift`
   - `recover_hint=re_perceive_and_retry`
   - `transport_used=rest|cdp`
4. 明确跳到登录页
   - `error_code=login_required`
   - `recover_hint=request_takeover`
5. 地域或代理阻断
   - `error_code=proxy_or_region_blocked`
   - `recover_hint=check_region_route`

---

## 9. 实施路径

### Phase 1

1. 保持 `aio_client` 只做官方接口访问
2. `AioSandboxBackend` 补齐正式方法
3. SessionManager 负责 runtime/session/takeover 生命周期

### Phase 2

1. 把四平台 handler 全部切到统一 backend
2. 把 extraction helper 从 scattered code 收口成 adapter 内部能力

### Phase 3

1. 把 internal-only shell/file/code 能力做成更稳定的内部 wrapper
2. 增加 AIO-only QA fixtures

---

## 10. 非目标

本设计不包含：

1. follow-up 路由
2. orchestrator policy
3. 本地客户端
4. 浏览器插件
5. 任意脚本执行开放给 A4

---

## 11. 下一步

1. 先补完 Session / Takeover 持久控制面
2. 再让 `AioSandboxBackend` 真正接住四平台 handler
3. 最后再做 takeover 恢复链路硬化
