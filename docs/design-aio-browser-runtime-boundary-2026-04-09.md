# AIO 作为 Browser Runtime 的边界说明

## 目标

把 `AIO` 明确收敛为 **浏览器执行 runtime / human takeover backend**，而不是新的业务 skill。

目标分层：

```text
Orchestrator
  -> answer_fetch skill
    -> A4 executor
      -> browser action contract
        -> browser execution backend
          -> Playwright backend / AIO backend
```

## 第一性定义

### 1. AIO 不是新的业务 skill

`AIO` 不应该被建模成新的用户能力名，也不应该直接暴露成新的顶层 workflow。

`AIO` 的职责是：
- 提供远程浏览器执行能力
- 提供人工接管 / 恢复 / resolve / cancel / heartbeat 协议
- 向上返回标准化的浏览器操作状态

### 2. A4 是答案抓取 executor

`A4` 负责：
- 决定抓哪些平台 / 哪些问题
- 调度 fetch 执行
- 合并结果
- 决定 completion / merge policy

`A4` 不应该长期持有：
- AIO bundle 拼装细节
- takeover session lifecycle 细节
- chat/canvas 专属事件拼装细节

### 3. browser action contract 是关键中间层

当浏览器执行遇到：
- login
- verify
- modal

执行 backend 不应该直接操作前端 UI，而应该只向上表达：

```text
action_required = {
  request_id,
  platform,
  action_type,
  state,
  message,
  action_hint,
  target_url,
  progress,
  takeover_bundle?
}
```

然后：
- chat 消费这份 contract，展示打开/完成/跳过
- AIO runtime 消费 takeover bundle，负责 open / heartbeat / resolve / cancel
- executor 等待 resolution，再继续业务抓取

## 当前设计问题

当前代码里，`A4` 仍然部分承担了：
- browser action request 注册/复用
- AIO takeover bundle 生成和缓存
- browser state / user action event 发射
- chat 提示文案拼装

这会导致：
- A4 既是业务 executor，又部分变成接管编排器
- 未来其他 executor 想复用 AIO 时，需要复制 A4 glue code
- runtime / UI / executor 的边界变模糊

## 本轮收口方案

新增独立的 `browser_action_contract` 层，负责：

### 1. request contract
- 注册 / 复用 browser action request
- 持久化 reconnect 所需的 request metadata

### 2. takeover contract
- 为 request 绑定 AIO takeover bundle
- 对 `request_id -> takeover_bundle` 做缓存和重入复用
- 恢复 target_url / frontend-facing access bundle

### 3. frontend event contract
- 向前端发 `browser_state`
- 向前端发 `browser_user_action`
- 只在 created_new 时发 chat reply 提示

### 4. resolution contract
- 等待 `completed / skip`
- 清理 request / bundle 临时缓存

## A4 经过收口后应保留的职责

`A4` 保留：
- 识别 login / verify / modal
- 调用 `browser_action_contract.emit_browser_action_handoff(...)`
- 基于 resolution 决定：
  - retry
  - stop current platform
  - continue fetch

`A4` 不再直接关心：
- takeover bundle 字段拼装
- open/resolve/cancel 路由字符串细节
- browser action UI 事件协议拼装

## 可复用性要求

未来其他 executor 若要接入浏览器人工接管，应该只需要：

1. 触发 browser backend 执行
2. 在需要人工动作时调用 `browser_action_contract`
3. 等待 resolution 后恢复自身流程

而不需要复制 A4 的 takeover / event glue。

## 非目标

本轮不做：
- 把 AIO 升成新的 public skill
- 重写 chat / canvas 交互协议
- 改 A5/A7 业务语义
- 改 `post_analysis_skill` / `answer_fetch` 边界

## 一句话结论

`AIO` 应该是可复用的浏览器 runtime，
`browser action contract` 应该是 runtime 与 executor/UI 之间的协议层，
`A4` 只负责答案抓取业务，不再继续膨胀成私有接管编排器。
