# AIO 作为 Browser Runtime 的边界说明

> 2026-04-12 更新：AIO 的生产级归位应以 [AIO Answer Fetch Tool 架构归位](./architecture-aio-answer-fetch-tool-runtime-2026-04-12.md) 和 [AIO Answer Fetch Tool 生产级架构设计](./design-aio-parallel-playwright-context-2026-04-11.md) 为准。本文保留 `browser_action_contract` 作为过渡实现和中间层说明。

## 目标

把 `AIO` 明确收敛为 **浏览器执行 runtime / human takeover backend**，而不是新的业务 skill。

目标分层：

```text
Orchestrator
  -> answer fetch capability
    -> Fetch Answer Agent / A4 executor
      -> AIO Answer Fetch Tool
        -> AIO Runtime
          -> Playwright Browser Agent
          -> Chromium / CDP / VNC
          -> AuthContext / RunContext
      -> Result Packet
    -> Artifact Writeback
```

## 第一性定义

### 1. AIO 不是新的业务 skill

`AIO` 不应该被建模成新的用户能力名，也不应该直接暴露成新的顶层 workflow。

`AIO` 的职责是：
- 提供远程浏览器执行能力
- 提供人工接管 / 恢复 / resolve / cancel / heartbeat 协议
- 向上返回标准化的浏览器操作状态
- 承载四平台浏览器执行 runtime
- 管理用户级 AuthContext 与任务级 RunContext

生产级默认关系：

```text
Agent 通过 AIO Tool 操作浏览器。
AIO Tool 内部用 Playwright 执行豆包、元宝、Kimi、DeepSeek 四个平台抓取。
普通页面阻塞由 AIO 自动处理。
身份/安全阻塞才进入人工接管。
```

### 2. A4 是答案抓取 executor

`A4` 负责：
- 决定抓哪些平台 / 哪些问题
- 调度 fetch 执行
- 合并结果
- 决定 completion / merge policy
- 消费 AIO 返回的结构化 result packet
- 校验、归一化并写入 Artifact

`A4` 不应该长期持有：
- AIO bundle 拼装细节
- takeover session lifecycle 细节
- chat/canvas 专属事件拼装细节
- CDP page / tab / browser context 的长期生命周期

当前后端直接 `connect_over_cdp` 控制 AIO Chromium 的实现，只能作为过渡层或 fallback。生产级应将 Playwright executor 下沉到 AIO runtime 内部，由 AIO Tool 以 job/event/result contract 对外暴露。

### 3. browser action contract 是关键中间层

当浏览器执行遇到：
- login
- verify
- modal

执行 backend 不应该直接操作前端 UI，而应该先分类 blocker：

1. 普通弹窗、广告、Cookie、新手引导、页面恢复，优先由 AIO Browser Agent 自动处理
2. 登录、验证码、人机验证、账号安全确认，才向上表达人工接管需求

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

## 生产级补充边界

### 1. 四平台整体建模

完整采集默认覆盖：

```text
doubao
yuanbao
kimi
deepseek
```

四个平台都必须拥有独立的：

1. `PlatformFetchJob`
2. `AuthContext`
3. `RunContext`
4. `BlockerPolicy`
5. `resume_probe`
6. `result packet`

不能只围绕某一两个平台做特判。

### 2. 接管 surface 是已准备好的现场

正确模型：

```text
AIO Playwright 已经跑到阻塞页面
  -> freeze 当前 platform page
  -> 生成 takeover surface_url
  -> Agent 提示用户
  -> 前端 attach 已存在 surface_url
```

错误模型：

```text
前端点击打开
  -> 临时创建云电脑
  -> 再导航平台页面
  -> 用户等待 loading / about:blank
```

### 3. 登录态绑定 Specta 用户

AuthContext 必须绑定：

```text
{env}/{specta_user_id}/{platform}
```

而不是绑定 task 或 entity。

RunContext 才绑定：

```text
{entity_id}/{task_id}/{platform}
```

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
