# AIO Answer Fetch Tool 架构归位

> 日期：2026-04-12
> 状态：Draft
> 目的：把 AIO、Fetch Answer Agent、四平台浏览器抓取、Playwright、VNC 人工接管、用户登录态和 Artifact 写入放回同一张架构图里，作为后续讨论和实现的统一基准。

---

## 一句话结论

`AIO` 应被建模为 Fetch Answer Agent 可调用的 **Browser Execution Tool / Runtime Capability**。

它不是新的 public skill，不是前端 Canvas 交付物，也不是一个临时 CDP 连接技巧。

正确关系是：

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
    -> Analytics / Report
```

---

## 架构分层

## 1. Orchestrator

职责：

1. 理解用户是否要做完整采集、快速采集、重试或跳过。
2. 选择答案抓取能力路径。
3. 接收 AIO 返回的需要用户介入事件，并决定如何提示用户。
4. 根据四平台结果决定是否继续进入分析报告。

不负责：

1. 直接操作浏览器。
2. 直接拼接 CDP / VNC URL。
3. 直接判断页面 DOM 是否登录成功。

## 2. Fetch Answer Agent / A4 Executor

职责：

1. 按四个平台创建抓取计划。
2. 调用 AIO Answer Fetch Tool。
3. 消费四个平台的 event 和 result packet。
4. 处理平台级成功、失败、跳过、重试。
5. 校验和归一化结果。
6. 写入 Artifact。

不负责：

1. 维护长期 CDP page。
2. 管理云电脑可视窗口焦点。
3. 把所有弹窗交给用户处理。
4. 把登录态写入任务结果。

## 3. AIO Answer Fetch Tool

职责：

1. 对 Fetch Answer Agent 暴露稳定 Tool Contract。
2. 默认执行四个平台：豆包、元宝、Kimi、DeepSeek。
3. 管理平台级 Playwright job。
4. 返回结构化事件：`platform_started`、`blocker_detected`、`takeover_required`、`platform_result`、`job_completed`。
5. 返回结构化 result packet。

它是一个 **Tool Facade**：

```text
AIO Answer Fetch Tool
  -> platform job scheduler
  -> blocker policy
  -> browser action tools
  -> takeover tools
  -> auth state tools
  -> run artifact tools
```

因此它可以比单个 click/fill 工具更粗，但仍然属于工具层，因为它对 Agent 暴露的是稳定输入输出合同，而不是新的业务 skill。

## 4. AIO Runtime

职责：

1. 承载 Chromium / CDP / VNC / noVNC。
2. 承载 Playwright executor 或 Browser Agent。
3. 存储用户级 AuthContext。
4. 存储任务级 RunContext。
5. 暴露 takeover surface。

推荐生产形态：

```text
AIO runtime unit
  browser container:
    Chromium / CDP / VNC / noVNC

  worker container:
    Playwright executor
    blocker classifier
    resume probe
    result extractor

  shared volume:
    /data/auth
    /data/runs
    /data/traces
```

当前后端通过 `connect_over_cdp` 远程控制 AIO browser 的实现，只应视为过渡实现和 fallback。

## 5. Frontend / Canvas / VNC

职责：

1. 展示 Agent 生成的四平台进度和接管提示。
2. 打开 AIO 已准备好的 `surface_url`。
3. 发送 `completed / skip / cancel`。
4. 渲染状态和 Artifact。

不负责：

1. 创建云电脑。
2. 决定打开哪个平台。
3. 导航平台页面。
4. 判断登录是否成功。
5. 保存登录态。

---

## 四平台模型

完整采集默认覆盖：

```text
doubao
yuanbao
kimi
deepseek
```

每个平台都是独立 sub-job：

```json
{
  "platform": "yuanbao",
  "status": "running",
  "auth_context_key": "prod/user_123/yuanbao",
  "run_context_key": "entity_456/task_789/yuanbao",
  "takeover_id": null
}
```

统一状态：

```text
pending
running
auto_recovering
blocked_waiting_takeover
takeover_active
resuming
succeeded
skipped
failed
```

核心要求：

1. 四个平台并行抓取。
2. 任一平台需要用户接管时，只暂停该平台。
3. 人工接管对用户串行展示。
4. 用户跳过某平台后，该平台进入 `skipped`，不再重复提示。
5. 任一平台失败不覆盖其他平台结果。

---

## BlockerPolicy

AIO Browser Agent 不能把所有阻塞交给用户。它必须先判断 blocker 类型。

自动处理：

```text
广告弹窗
Cookie 弹窗
新手引导层
下载 App 提示
普通遮罩
输入框失焦
about:blank 恢复
白屏刷新
错误子页面回到 chat 页
```

人工接管：

```text
登录
二维码扫码
手机验证码
图形验证码
人机验证
账号安全确认
平台风控确认
用户选择账号或授权
```

不可恢复：

```text
平台不可用
账号限流
策略拒绝
连续验证失败
不支持的页面流程
```

结构化 blocker event：

```json
{
  "event": "blocker_detected",
  "platform": "doubao",
  "blocker_type": "dismissible_modal",
  "auto_action_allowed": true,
  "auto_action_taken": "clicked_close",
  "requires_human": false,
  "evidence": {
    "text": "下载 App",
    "screenshot_ref": "/data/traces/job_123/doubao/modal.png"
  }
}
```

---

## Human Takeover

正确链路：

```text
AIO Playwright 已经跑到阻塞页面
  -> freeze 当前 platform page
  -> 生成 takeover surface_url
  -> 返回 takeover_required event
  -> Agent 在 Chat 提示用户
  -> 用户点击打开云电脑
  -> 前端 attach 已存在 surface_url
  -> 用户直接看到当前平台阻塞现场
  -> 用户点击我已完成
  -> AIO resume_probe
  -> probe 通过后保存 auth state
  -> 平台 job 继续抓取
```

错误链路：

```text
用户点击打开浏览器
  -> 前端请求创建云电脑
  -> 云电脑再导航到平台页面
  -> 用户等待 loading / about:blank
```

takeover event：

```json
{
  "event": "takeover_required",
  "platform": "kimi",
  "takeover_id": "takeover_456",
  "reason": "captcha_required",
  "surface_url": "https://aio-runtime/takeovers/takeover_456",
  "current_page_url": "https://kimi.com/",
  "auth_context_key": "prod/user_123/kimi",
  "run_context_key": "entity_456/task_789/kimi"
}
```

---

## Context 分离

## AuthContext

登录态绑定 Specta 用户和平台：

```text
/data/auth/{env}/{specta_user_id}/doubao/browser_state.json
/data/auth/{env}/{specta_user_id}/yuanbao/browser_state.json
/data/auth/{env}/{specta_user_id}/kimi/browser_state.json
/data/auth/{env}/{specta_user_id}/deepseek/browser_state.json
```

规则：

1. 同一 Specta 用户跨品牌复用平台登录态。
2. 不同 Specta 用户不能复用登录态。
3. `resume_probe` 通过后才保存登录态。
4. 用户要求重新绑定时，只清理该用户该平台 AuthContext。

## RunContext

抓取结果绑定任务：

```text
/data/runs/{entity_id}/{task_id}/doubao/result.json
/data/runs/{entity_id}/{task_id}/yuanbao/result.json
/data/runs/{entity_id}/{task_id}/kimi/result.json
/data/runs/{entity_id}/{task_id}/deepseek/result.json
```

规则：

1. Artifact 只读取 result packet。
2. RunContext 不保存登录态。
3. 单个平台失败不覆盖其他平台。

---

## 与现有文档的关系

本文件是总体架构归位文档。细节设计见：

1. [AIO Answer Fetch Tool 生产级架构设计](./design-aio-parallel-playwright-context-2026-04-11.md)
2. [AIO 作为 Browser Runtime 的边界说明](./design-aio-browser-runtime-boundary-2026-04-09.md)
3. [Specta AIO 四平台执行合同设计](./design-aio-four-platform-skill-contract-2026-03-31.md)
4. [Specta AIO Tool Schema 设计](./design-aio-tool-schema-2026-03-31.md)
5. [AGEO Harness 分层边界重定义](./design-harness-layering-agent-skill-tool-2026-04-01.md)

---

## 实施基准线

后续实现必须以以下判断为基准：

1. AIO 是 Agent 可调用的 Tool / Runtime Capability。
2. Fetch Answer Agent 通过 AIO Tool 操作浏览器。
3. 四个平台作为一个整体建模。
4. 普通页面阻塞由 AIO Browser Agent 自动处理。
5. 登录、验证码、人机验证才交给用户。
6. VNC / 云电脑是已准备好的现场接管 surface。
7. 登录态绑定 Specta 用户和平台。
8. Result packet 才进入 Artifact。
9. 当前后端 CDP 直连只能是过渡和 fallback。
