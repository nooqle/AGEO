# AIO Answer Fetch Tool 架构归位

> 日期：2026-04-12
> 状态：In Progress（P0-P2 进行中）
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
4. 在模型已经选错工具后，再做语义级 runtime 改写把它“改回来”。

### 当前会话追问的 Harness 原则

当用户是在追问**当前会话刚产生的 fetch_results / report / metrics** 时，Harness 的首选控制方式不是：

```text
先把所有工具都暴露给模型
-> 模型选错 knowledge_*
-> runtime 再 realign 成 drill_down_analysis
```

而应该是：

```text
先根据当前上下文裁剪 tool surface
-> 当前会话追问时隐藏 knowledge_*
-> 平台/情感等明确深挖场景时进一步隐藏 compare_snapshots / post_analysis_skill
-> 让模型直接在正确工具面内规划
```

这属于 Harness 的 **contextual tool exposure**，不是业务层 hardcode。

原因很直接：

1. 事后 realign 会制造多控制器冲突。
2. prompt、tool list、runtime rewrite 同时生效时，模型容易来回思考、重复调用、击中 retry blocker。
3. Claude Code 风格的 Harness 更强调 **先收敛可选动作空间**，而不是等模型犯错后再修正。

补充要求：

1. Prompt 中的“公共技能索引”也必须遵循同一套 tool surface，不能继续静态展示已经被 Harness 隐藏的 `knowledge_* / post_analysis_skill`。
2. 对于已经收敛到 `drill_down_analysis` 的当前会话追问，Prompt 应显式增加“当前回合工具面约束”段落，明确告诉模型：
   - 当前问题属于本次结果追问
   - 历史知识工具已隐藏
   - 当前应直接使用 `drill_down_analysis`
   - 不要再先走 `post_analysis_skill` 或 `knowledge_*`

否则即使运行时真实工具面已经收口，Prompt 仍会继续给模型错误暗示，造成思考漂移。

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

## 3.1 Browser Agent 才负责页面理解

平台 handler 不应该继续长期承担“页面理解”职责。生产级方向应改成：

```text
AIO Answer Fetch Tool
  -> Browser Agent loop
       observe(url / screenshot / DOM snapshot / aria tree)
       decide(click / type / press / wait / close / retry / navigate)
       classify blocker(auto-fix / human takeover / fatal)
  -> stable result packet / takeover packet
```

也就是说：

1. Harness / Tool 管契约、并发、持久化、恢复。
2. Browser Agent 管页面理解和操作。
3. Human takeover 只接管真正需要人的步骤。

如果继续靠平台 handler 堆 selector、位置规则、登录按钮判断，系统只会不断为当下页面补丁，无法适应平台 UI 演化。

当前已落地的第一层代码 seam：

- `app/core/fetchers/browser/browser_agent_contract.py`
- `app/core/fetchers/browser/browser_agent_policy.py`
- `app/core/fetchers/browser/browser_agent_loop.py`

这层先把 Browser Agent loop 的公共契约明确下来，避免一上来就继续改平台 handler。当前已经定义：

- `BrowserPageObservation`
- `BrowserAgentAction`
- `BrowserAgentDecision`
- `BrowserTakeoverNeed`
- `BrowserAgentLoopContext`
- `collect_browser_page_observation(...)`
- `decide_browser_preflight(...)`
- `collect_browser_agent_step(...)`
- `build_default_browser_agent_policy(...)`
- `observation_to_llm_payload(...)`
- `requires_human_takeover(...)`

这意味着下一步可以直接基于当前已有 client 原语推进 Browser Agent loop：

- `snapshot / click / fill / press / eval`
- AIO runtime 的 `take_screenshot()`
- AIO client 的 `sync_to_existing_target_page() / persist_runtime_state()`

当前已经落地的第一步接入：

- `BrowserAgentBootstrapPolicy`
- `HybridBrowserAgentPolicy`
- `LLMBrowserAgentPolicy`
- `LLMBrowserAgentPolicy` 现在已按 `preflight / wait_gate / resume_probe / empty_answer` 生成阶段化 prompt
- `collect_browser_agent_step(...)`
- `BaseBrowserHandler._run_browser_agent_preflight(...)`
- `BaseBrowserHandler._wait_for_content_with_browser_agent(...)`
- `BaseBrowserHandler._browser_agent_resume_probe_ready(...)`
- `BaseBrowserHandler._handle_browser_agent_parser_error(...)`
- `BaseBrowserHandler._handle_browser_agent_wait_blocker(...)`
- `BaseBrowserHandler._handle_browser_agent_empty_answer(...)`
- `BaseBrowserHandler._execute_browser_agent_action(...)`
- 四个平台在登录检查前统一先跑 preflight
- 四个平台在 DOM fallback 等待阶段统一先跑 wait gate
- preflight / wait gate / resume probe / empty answer 现在都带 `BrowserAgentLoopContext` 阶段信息进入 loop
- “我已完成”后的 resume probe 现在进入共享 Browser Agent resume loop：
  - 支持 `action_type`
  - 支持平台自然语言 stage note / meta
  - 支持自动执行轻量动作后再次观察
  - `takeover_required / failed` 直接保持阻塞
  - 只对 `blank_page / navigation_error / target_closed` 这类瞬时状态继续轮询
- 四个平台不再 override `probe_resume_gate_ready`；平台只补充自然语言恢复期望，不再各自维护 selector 轮询
- parser 错误、wait blocker、空答案兜底继续往 Base 收，减少平台 handler 对 blocker 恢复的直接分叉
- 默认执行链现在是 **LLM-first + deterministic fallback**：
  - `LLMBrowserAgentPolicy` 默认只接管 `preflight / wait_gate / resume_probe`
  - `empty_answer` 仍可生成阶段化 prompt，但不属于本轮默认接管目标
  - LLM 只允许安全轻量动作：`click / press / wait / focus / close modal / safe navigate`
  - 账号密码、短信码、验证码、任意跨站导航仍被禁止
  - LLM 决策解析失败、超时、动作不安全时，立即回退到 bootstrap policy
- `safe navigate` 现在只允许：
  - 同 host 导航
  - 或显式目标 URL 导航
- 登录类 blocker 的分类优先级已上移到共享 policy，避免“登录弹窗因为含验证码输入框而被归成 verification”

也就是说，下一阶段不需要先重写浏览器底层，而是把 handler 中的页面理解与 blocker 分类逐步迁移到 Browser Agent policy / executor，并把 stale page / live page resync 这类确定性问题继续留在 runtime / base handler 层。当前 Browser Agent 还不是最终的 LLM planner，但运行时已经具备“阶段上下文 + 可替换执行器”的骨架。

### P0-P2 当前完成度

这一轮已经落地的，不应再回退：

1. 初始登录判定、late blocker、resume probe 的主控制面已经开始从平台 handler 收回到共享 Browser Agent runtime。
2. 平台 handler 正在逐步削成“平台薄配置层”，当前主要保留：
   - 平台入口 URL / 会话 URL 语义
   - 平台自然语言提示与 profile hints
   - 提交问题动作
   - 答案抽取契约与平台特有归一化
3. `takeover_required` 的结构化事实来源已扩展为：
   - `platform`
   - `action_type`
   - `reason_code`
   - `target_url`
   - `blocking_url`
   - `blocking_fingerprint`
   - `resume_policy`
4. 停止任务后的浏览器占用释放与卡片保留语义，已经开始围绕 settled state 建模，而不是粗暴清空前端状态。

这一轮尚未完成的：

1. 初始登录判定和 late blocker 仍有残留在平台 handler，尤其是平台特有首屏登录页与提交后弹窗。
2. `LLMBrowserAgentPolicy` 目前只接管受控阶段，不是整条提问/抓取主流程的默认执行者。
3. 平台 handler 还没有完全收敛为“纯配置 + 抽取契约”。
4. 真实线上 UAT 还没有证明“首次登录 -> 我已完成 -> 继续抓取 -> 下次复用登录态”已经完全闭环。

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

补充要求：

1. 前端只 attach 后端已经准备好的 `surface_url`，不能再通过“打开后再导航平台主页”的方式制造新的阻塞现场。
2. 停止任务后必须释放 browser workspace 与接管占用，不能继续劫持档案/问题导航。
3. 登录、验证、验证码、安全确认统一收敛到单一结算卡片语义，不再保留额外说明消息。

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

接管原则补充：

1. AIO 应优先把用户 attach 到 **阻塞现场**，而不是平台首页。
2. Browser Agent 先尝试自动关闭普通弹窗、恢复空白页、重新聚焦输入区。
3. 只有 Browser Agent 明确判断为登录、验证码、人机验证、账号安全确认时，才生成 `takeover_required`。
4. 用户点击“我已完成”后，恢复逻辑必须先走 `resume_probe`；只有 probe 通过，才允许继续抓取并持久化 AuthContext。
5. 同一平台、同一任务、同一阻塞现场必须去重；默认去重键应包含：
   - `platform`
   - `specta_user_id`
   - `task_id`
   - `blocking_fingerprint`
6. 接管卡片在聊天区采用统一结算态：
   - `issued`
   - `opened`
   - `resolved`
   - `skipped`
   - `resume_failed`
   - `expired`
   - `cancelled`
7. 结算后的卡片可以保留，但不应再残留额外说明消息。

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
