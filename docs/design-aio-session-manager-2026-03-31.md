# Specta AioSandboxSessionManager 设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义 Specta 如何基于 AIO Sandbox 官方 guide / OpenAPI / 实践文章，建立稳定的云端会话管理层，而不是在业务代码里零散地直接调用沙箱接口。

---

## 1. 一句话结论

`AioSandboxSessionManager` 是 Specta 接入 AIO 的控制面中枢。  
它不做业务编排，不直接决定平台流程，只负责：

1. 获取和绑定 sandbox
2. 发现官方能力与运行上下文
3. 派生标准 `data_root`
4. 暴露稳定的 browser / shell / takeover 访问句柄
5. 管理租约、持久化与回收

它的设计必须优先服从官方接口和已验证实践，而不是自行发明会话模型。

本设计中的 `session_state`、`takeover_state`、`profile_root`、`run_root` 以 [design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md) 为准。

---

## 2. 设计依据

本设计直接基于以下官方与实践信息：

1. `GET /v1/sandbox`
   - 返回 `home_dir`、`version`、`detail`
2. `GET /v1/browser/info`
   - 返回浏览器信息和 `cdp_url`
3. `POST /v1/browser/state/save` / `load`
   - 用于浏览器状态文件保存与恢复
4. `GET|POST|DELETE /v1/browser/cookies`
   - 用于 cookies 读写与清理
5. `POST /v1/shell/sessions/create` / `update`
   - 用于交互式 shell 会话
6. `POST /tickets`
   - 用于 VNC 等不能带 header 场景的短时票据
7. `GET /auth`
   - 用于鉴权检查
8. 官方 browser guide
   - 明确 `VNC` 与 `browser-ui + CDP` 是两种接管方式
9. 实践文章
   - 强调 `connect` / `disconnect` / 文件系统持久化 / 登录流程拆分

---

## 3. 不该由 SessionManager 负责的事

### 不负责

1. 判断当前问题该不该抓取
2. 决定四个平台的执行顺序
3. 决定哪个平台该用哪些业务工具
4. 生成报告
5. 做客户业务权限判断

### 负责

1. 把 Specta 的业务任务绑定到一个稳定 sandbox runtime
2. 暴露可复用的 browser / shell / takeover 句柄
3. 保证状态目录、ticket、lease、timeout 有统一策略

---

## 4. 角色定位

在整体架构中，`AioSandboxSessionManager` 位于：

`Specta Backend / Orchestrator` 与 `AIO Sandbox Instance`

之间。

它更像：

`Session Control Plane`

而不是：

`Platform Handler`

---

## 5. 官方约束带来的三个关键设计决定

## 5.1 不写死固定 home 路径

官方 `GET /v1/sandbox` 返回 `home_dir`。  
因此 Specta 不能把状态根目录写死成某个固定 home 路径。

统一规则：

1. 先调用 `GET /v1/sandbox`
2. 读取 `home_dir`
3. 派生：

```text
data_root = <home_dir>/data
```

4. 再生成：

```text
profile_root = <data_root>/<workspace_id>/<platform>/profile
run_root = <data_root>/<task_id>/<platform>/run
```

## 5.2 Browser 访问以 `GET /v1/browser/info` 为标准入口

为了避免路径、鉴权、代理实现差异，  
SessionManager 必须统一以：

1. `GET /v1/browser/info`

作为浏览器可用性发现与 `cdp_url` 获取的标准入口。

## 5.3 接管鉴权不能自己发明

官方明确给出：

1. JWT 鉴权
2. `POST /tickets`
3. `VNC` 的 ticket URL 构造方式

因此：

1. `VNC` 必须走官方 ticket 模式
2. `browser-ui + CDP` 因官方未明确给出前端 ticket 模式，Specta 不应假设前端直接持有原始 JWT
3. Specta 应在自己的后端/BFF 中包一层受控 relay

---

## 6. SessionManager 的内部对象模型

建议定义一个内部统一对象：

```yaml
SpectaAioSession:
  session_id:
  workspace_id:
  sandbox_ref:
  base_url:
  auth_mode:
  jwt_subject:
  aio_version:
  home_dir:
  data_root:
  browser:
    cdp_url:
    viewport:
    user_agent:
    cookies_supported:
    state_supported:
  shell:
    session_id:
  takeover:
    current_takeover_id:
    current_mode:
    vnc_ticket_expires_at:
  leases:
    holders:
    ref_count:
    automation_lock:
    human_takeover_lock:
  capabilities:
    browser:
    shell:
    bash:
    file:
    nodejs:
    jupyter:
    mcp:
    code:
    proxy:
    auth:
  state:
    session_state:
    last_seen_at:
    last_healthcheck_at:
    expires_at:
```

---

## 7. 生命周期状态机

SessionManager 只承认共享合同里的 `session_state`：

1. `provisioning`
2. `ready`
3. `leased`
4. `takeover_frozen`
5. `idle`
6. `draining`
7. `failed`
8. `destroyed`

迁移规则以 [design-aio-session-persistence-model-2026-03-31.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-session-persistence-model-2026-03-31.md) 的权威状态机为准。

---

## 8. 标准生命周期流程

## 8.1 Acquire

当 Specta A4 需要浏览器 runtime 时：

1. 用 `workspace_id` 查询是否已有可复用 session
2. 若无，则分配或创建 sandbox instance
3. 调用 `GET /v1/sandbox`
4. 解析 `home_dir`、`version`、`detail`
5. 派生 `data_root = <home_dir>/data`
6. 调用 `GET /v1/browser/info`
7. 获取 `cdp_url`
8. 如需要持久终端，则调用 `POST /v1/shell/sessions/create`
9. 将 session 状态标记为 `ready -> leased`

## 8.2 Use

后续业务工具不直接关心 base_url 和 ticket，而是从 SessionManager 获取：

1. `sandbox_ref`
2. `browser_handle`
3. `profile_root`
4. `run_root`
5. `shell_handle`
6. `takeover_access`

## 8.3 Release

任务结束后：

1. 减少 `ref_count`
2. 若仍有其它 holder，则只释放业务租约
3. 若无 holder，则进入 `idle`
4. `idle` 达到 TTL 后再进入 `draining`

## 8.4 Destroy

命中以下任一情况时回收：

1. workspace 明确结束
2. 持久化失败且不可恢复
3. healthcheck 连续失败
4. 超出空闲 TTL

---

## 9. SessionManager 对外接口

建议给 Specta 后端内部暴露这组稳定方法：

### `acquire_session(workspace_id, task_id, purpose, platforms)`

返回：

1. `session_id`
2. `sandbox_ref`
3. `browser_handle`
4. `data_root`
5. `capabilities`

### `ensure_platform_roots(session_id, task_id, platform)`

返回：

1. `profile_root`
2. `run_root`
3. `cookies_path`
4. `state_path`

### `get_browser_connection(session_id)`

返回：

1. `cdp_url`
2. `browser_info`
3. `preferred_access_mode`

### `get_shell_session(session_id, exec_dir)`

若不存在则创建，返回：

1. `shell_session_id`

### `create_takeover_access(session_id, mode, reason)`

返回：

1. `takeover_id`
2. `canvas_access`
3. `vnc_access`
4. `expires_at`

### `release_session(session_id, holder)`

### `destroy_session(session_id, reason)`

---

## 10. 非目标

1. 不在 SessionManager 中决定 A4 的平台顺序
2. 不在 SessionManager 中直接写前端 UI 逻辑
3. 不在业务代码里暴露原始 AIO 鉴权凭证

---

## 11. 下一步

1. 与 Session Persistence 文档对齐 `ready -> leased -> takeover_frozen`
2. 实现阶段把所有状态迁移统一收口到 SessionManager API

---

## 12. 相关文档

1. 共享合同：[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
2. Session Persistence：[design-aio-session-persistence-model-2026-03-31.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-session-persistence-model-2026-03-31.md)
