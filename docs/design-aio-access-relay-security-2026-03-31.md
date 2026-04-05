# Specta AIO Access Relay 与安全边界设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义 Specta 如何安全代理 AIO 的 Canvas/CDP、VNC ticket 和 takeover 生命周期，确保前端只能拿到受限 bundle，而不是原始 runtime 能力。

---

## 1. 一句话结论

前端只能通过 Specta 自己的 takeover 协议访问 AIO：

1. Canvas 走 Specta `cdp-relay`
2. VNC 走 Specta `ticket broker + redirect`
3. heartbeat / resolve / cancel 全部走 Specta API

前端不能直接拿：

1. AIO JWT
2. 原始 `cdp_url`
3. 原始 AIO base URL

本设计中的状态词以
[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
为准。

---

## 2. 官方依据

### 2.1 official guide

1. [Authentication](https://sandbox.agent-infra.com/zh/guide/basic/authentication)
2. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)

### 2.2 official openapi

当前 relay 依赖这些能力：

1. `GET /v1/browser/info`
2. `POST /tickets`

### 2.3 best-practice article

1. browser-ui 适合 Canvas 主交互
2. VNC 适合完整浏览器 fallback
3. 接管链路必须有心跳与过期机制

### 2.4 Specta wrapper decision

1. 前端不直连 `cdp_url`
2. access bundle 只绑定一个 takeover
3. 旧 bundle 在 `resolve/cancel/expire` 后立即失效

---

## 3. 安全边界

### 3.1 Backend 持有

1. AIO `base_url`
2. AIO 鉴权能力
3. ticket 创建能力
4. cdp 上游连接能力

### 3.2 Frontend 持有

1. Specta 用户登录态
2. `takeover_id`
3. 受限 access bundle 路径

### 3.3 明确禁止

1. 前端拿到原始 AIO JWT
2. 前端拿到原始 AIO `cdp_url`
3. 前端绕过 Specta 直接访问其它 sandbox

---

## 4. Access Bundle 合同

一个 access bundle 只绑定一个：

1. `takeover_id`
2. `session_id`
3. `user_id`
4. `frontend_id`（激活后）

bundle 对外只暴露这些路径：

1. `canvas-config`
2. `vnc-url`
3. `heartbeat`
4. `resolve`
5. `cancel`

说明：

1. 这些不是原始 AIO path
2. 都是 Specta 自己的 gateway path

---

## 5. Specta 对外协议

### 5.1 `GET /api/v1/aio/takeovers/{id}/canvas-config`

返回：

1. `mode`
2. `cdp_endpoint`
3. `expires_at`
4. `heartbeat_interval_ms`

### 5.2 `GET /api/v1/aio/takeovers/{id}/vnc-url`

返回：

1. `mode`
2. `url`
3. `expires_at`

### 5.3 `POST /api/v1/aio/takeovers/{id}/heartbeat`

作用：

1. 绑定或续约 active frontend
2. 刷新 heartbeat TTL
3. 检测 takeover 是否仍有效

### 5.4 `POST /api/v1/aio/takeovers/{id}/resolve`

作用：

1. 提交“用户已完成”
2. 迁移 takeover 状态
3. 进入 resume gate
4. 立即废弃旧 bundle

### 5.5 `POST /api/v1/aio/takeovers/{id}/cancel`

作用：

1. 用户主动取消
2. 迁移 takeover 状态
3. 立即废弃旧 bundle

---

## 6. VNC 协议

### 6.1 来源

1. `official guide`
2. `POST /tickets`
3. 官方 ticket query 模式

### 6.2 规则

1. 后端验证当前用户与 takeover 绑定
2. 后端用 AIO 能力申请 ticket
3. 只签发短时 ticket
4. 前端只拿到 Specta 包装后的 redirect URL

### 6.3 失效规则

1. `resolve`
2. `cancel`
3. `expire`

以上任一发生时：

1. 旧 ticket 不再可用
2. 若允许 reopen，必须重新签发 bundle

---

## 7. Canvas / CDP Relay 协议

### 7.1 原则

browser-ui 看到的是：

`/api/v1/aio/takeovers/{id}/cdp-relay`

而不是原始 `cdp_url`。

### 7.2 relay 职责

1. 鉴别当前用户
2. 校验 takeover 是否属于当前用户
3. 校验 takeover 是否仍可用
4. 建立到 AIO 上游的受控 websocket
5. 记录审计日志

### 7.3 生命周期

1. bundle 只绑定一个 takeover
2. 同一 takeover 同时只允许一个 active frontend
3. reopen 若允许，必须重新获得有效 takeover 状态

---

## 8. 规则补充

### 8.1 同一 takeover 是否允许 reopen

允许，但前提是 takeover 仍处于：

1. `issued`
2. `active`
3. `resume_failed`

并且必须重新校验：

1. 当前用户
2. 当前 frontend
3. bundle 是否仍有效

### 8.2 resolve / cancel / expire 后

旧 bundle 立即失效。

### 8.3 terminal-url

`/v1/shell/terminal-url` 不进入主接管流程，只保留给 internal appendix / 运维调试，不扩大攻击面。

---

## 9. 审计要求

至少记录：

1. takeover 创建
2. bundle 签发
3. 首个 heartbeat
4. resolve
5. cancel
6. expire
7. relay open / relay close

---

## 10. 非目标

本设计不处理：

1. 平台 policy
2. follow-up 路由
3. 本地客户端或插件

---

## 11. 下一步

1. 把 takeover 协议真正落到持久控制面
2. 再让前端 Canvas 和 VNC 都只依赖这套协议
