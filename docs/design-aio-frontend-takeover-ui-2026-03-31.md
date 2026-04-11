# Specta AIO 前端接管 UI 设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义右侧 Canvas 形态下的 AIO takeover UI，使前端实现、后端 relay、安全协议和恢复行为保持一致。

---

## 1. 一句话结论

AIO 接管 UI 的唯一业务入口是：

`右侧 Canvas 的 browser content`

不是 modal。  
Canvas 默认挂载 `browser-ui`，失败时切到 `VNC fallback`。  
前端只渲染后端权威 `takeover_state`，不再发明平行业务状态。
用户点击 `完成` 后，只有服务端 `resume gate` 返回 `pass` 才允许关闭当前 browser Canvas；若返回 `resume_failed`，必须保留当前接管面并展示失败状态。

本设计中的状态词以
[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
为准。

---

## 2. 官方依据

### 2.1 official guide

1. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)
2. [Authentication](https://sandbox.agent-infra.com/zh/guide/basic/authentication)

### 2.2 official openapi

前端接管依赖的后端桥接能力最终落到：

1. `GET /v1/browser/info`
2. `POST /tickets`

### 2.3 best-practice article

1. Canvas 更适合产品主交互
2. VNC 适合完整浏览器 fallback
3. 接管需要心跳和恢复机制

### 2.4 Specta wrapper decision

1. 右侧 Canvas 为主，禁止回到 modal
2. 前端不直连原始 `cdp_url`
3. VNC 只做 fallback

---

## 3. 组件边界

### 3.1 权威 UI 容器

1. `CanvasPanel`
2. `browser` content type
3. `BrowserTakeoverContent`

### 3.2 不再存在的形态

1. `AioTakeoverModal`

如果文档或代码里还有 modal 表述，视为过期设计。

---

## 4. 权威数据形状

`browser` Canvas content 必须至少携带：

```ts
type BrowserCanvasContent = {
  type: 'browser'
  data: {
    browserState: {
      platform: string
      state: string
      message: string
      requestId?: string | null
      requiresAction: boolean
      takeover?: {
        takeoverId: string
        mode: 'canvas_cdp' | 'vnc_fallback'
        canvasConfigPath: string
        vncUrlPath: string
        heartbeatPath: string
        resolvePath: string
        cancelPath: string
        expiresAt?: string | null
      } | null
    }
  }
}
```

来源：

1. `Specta wrapper decision`
2. 后端 `/api/v1/aio/takeovers/*` 协议

---

## 5. 后端权威状态与前端渲染状态

### 5.1 后端权威状态

只允许：

1. `requested`
2. `issued`
3. `active`
4. `resolved`
5. `expired`
6. `cancelled`
7. `resume_failed`

### 5.2 前端渲染状态

前端只允许维护渲染层状态：

1. `hidden`
2. `opening`
3. `canvas_ready`
4. `vnc_ready`
5. `submitting`
6. `error`

说明：

1. `takeover_state` 是业务状态
2. `renderState` 是 UI 状态

前端不能再让 `renderState` 充当业务真相。

---

## 6. 用户流程

## 6.1 正常流程

1. 后端推送 browser state，带 takeover bundle
2. 前端在右侧打开 `browser` Canvas
3. 默认请求 `canvas-config`
4. 挂载 `browser-ui`
5. browser-ui ready 后开始 heartbeat
6. 用户完成登录或处理 modal
7. 用户点“完成”
8. 前端调用 `resolve`
9. 后端执行 resume gate
10. 若返回 `resolved`
   - 关闭当前 browser Canvas 或切回原内容
11. 若返回 `resume_failed`
   - 保留当前 browser Canvas
   - 显示失败状态

## 6.2 Fallback 流程

1. Canvas 初始化失败
2. 后端强制 `vnc_fallback`
3. 用户主动切换 VNC

以上任一成立时：

1. 请求 `vnc-url`
2. 以 iframe 打开 VNC
3. heartbeat 继续保活 takeover

---

## 7. Heartbeat and Reconnect Behavior

### 7.1 heartbeat 开始时机

1. `canvas_cdp`
   - browser-ui 真正 ready 后开始
2. `vnc_fallback`
   - iframe 成功加载后开始

### 7.2 heartbeat 周期

使用后端返回的：

`canvasConfig.heartbeatIntervalMs`

### 7.3 丢心跳处理

1. 连续 1 次失败
   - 标记连接不稳定
2. 连续 2 次失败
   - 尝试重新获取 takeover 状态
3. 连续达到阈值
   - 等待后端把 takeover 迁移为 `expired`
   - 前端只渲染 `expired`

### 7.4 页面刷新后的 reopen

页面刷新后：

1. 先从 conversation runtime / browser_state 恢复当前 takeover
2. 再调用 `GET /api/v1/aio/takeovers/{id}`
3. 若状态仍为 `issued|active|resume_failed`
   - 重新打开 browser Canvas
4. 若状态为 `resolved|cancelled|expired`
   - 不再 reopen

---

## 8. 控制按钮

右侧 browser Canvas 底部只保留必要动作：

1. `完成`
2. `切换到 VNC`
3. `取消`

行为要求：

1. `完成`
   - 调用 `resolve`
   - 仅当后端返回 `resolved` 时关闭 Canvas
2. `取消`
   - 调用 `cancel`
   - 成功后关闭 Canvas
3. `切换到 VNC`
   - 不改变业务状态，只切换接管显示方式

禁止增加解释性废话文案。  
状态提示必须简短，只表达：

1. 平台
2. 当前模式
3. 当前接管状态
4. 失败原因

---

## 9. Canvas vs VNC 规则

### 9.1 默认 Canvas

用于：

1. 登录表单填写
2. 普通 modal 关闭
3. 单页面聊天交互

### 9.2 强制 VNC

用于：

1. browser-ui 初始化失败
2. 多窗口或文件对话框
3. 后端显式要求 fallback

---

## 10. 与安全协议的边界

前端只看这些受限路径：

1. `canvasConfigPath`
2. `vncUrlPath`
3. `heartbeatPath`
4. `resolvePath`
5. `cancelPath`

前端不持有：

1. 原始 AIO JWT
2. 原始 AIO `cdp_url`
3. 原始 AIO base URL

相关安全边界以
[design-aio-access-relay-security-2026-03-31.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-access-relay-security-2026-03-31.md)
为准。

---

## 11. 非目标

本设计不包含：

1. follow-up 路由
2. orchestrator 文案
3. 本地客户端
4. 插件路线

---

## 12. 下一步

1. 让 frontend/browser canvas 完全映射后端权威 `takeover_state`
2. 再补强刷新重开、过期、resume_failed 的可见行为
