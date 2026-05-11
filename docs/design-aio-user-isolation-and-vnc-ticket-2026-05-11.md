# AIO 用户隔离与 VNC 接管稳定性修复

## 背景

本次排查覆盖两个线上现象：

1. AIO 接管打开后 noVNC 显示 `something went wrong connection is closed`。
2. imspecta 切换到新账号后，AIO 抓取仍然看到旧账号在豆包、元宝、Kimi、DeepSeek 的网页登录态。

## 确定根因

### 1. 远端浏览器 context 被跨用户复用

A4 创建 `AioConnectedBrowserClient` 时已经把 `workspace_id`、`auth_scope_id` 设置为当前 Specta 用户 id，文件态的 `browser_state.json` 目录也按用户隔离。

真正破坏隔离的是活浏览器层：

- AIO runtime 由 `AIO_BASE_URL` 指向一个长活 sandbox / Chromium。
- `AioConnectedBrowserClient._get_or_create_remote_context()` 会枚举 `self.browser.contexts`。
- 只要发现已有 page 的 host 等于目标平台 host，就直接复用该 context。
- DeepSeek 还允许在没有 host 命中的情况下复用默认 context。

这意味着新 Specta 用户虽然拿到了自己的 takeover bundle 和自己的状态目录，但实际 attach 到了旧用户已经登录过的平台网页 context。之后如果持久化状态，还可能把旧网页登录态保存到新用户目录。

### 2. VNC websocket 复用了提前签发的 AIO ticket

当前 `/vnc-url` 创建一次 AIO ticket，并把它写进 noVNC iframe URL 的 `path`：

`/api/v1/aio/takeovers/{id}/vnc-websockify?ticket={ticket}`

但是 noVNC/React 接管页存在重挂载、重试、自动重连场景。每次 websocket 连接都会继续复用同一个 ticket。AIO ticket 是短时访问凭据，不能作为长期可重连会话凭据使用；当 ticket 已被消费、过期或上游关闭后，noVNC 会看到连接立即关闭，也就是用户看到的 `connection is closed`。

## 修复策略

1. A4 自动化打开平台时，不再从远端 Chromium 的全局 context 池按 host/default 复用旧 context。
2. 每次创建平台页面，都走当前 Specta 用户的 `auth_scope_id` 对应的 storage state 创建隔离 context。
3. takeover 完成后的 resume 只在当前 client 已持有的 context 内找用户操作过的页面，不跨全局 context 扫描。
4. VNC relay 每次 websocket 连接上游 AIO 时即时创建 fresh ticket；URL 里的 ticket 只保留兼容，不作为上游连接的唯一凭据。

## 验证点

1. 单测覆盖：有旧 host-matched context 时，新用户 client 必须创建新 isolated context。
2. 单测覆盖：DeepSeek 默认不再复用无 host 命中的默认 context。
3. 单测覆盖：VNC relay 的 upstream URL helper 支持 fresh ticket。
4. 静态检查和 targeted pytest 通过。

