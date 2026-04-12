# Specta A4 AIO 路由设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义 A4 节点在接入 AIO 后，如何基于四平台 Platform Execution Contract、AIO BlockerPolicy 与 Specta Tools 做决策式路由，而不是把执行逻辑写死在 node 或 handler 中。

> 2026-04-12 更新：A4 不再被理解为“直接路由到 AioSandboxBackend 并自己操作浏览器”。生产级架构中，A4 / Fetch Answer Agent 调用 `AIO Answer Fetch Tool`，AIO Tool 在 Runtime 内用 Browser Agent / Playwright 操作四个平台，并通过事件把 `takeover_required`、`platform_result`、`job_completed` 回传给 Agent。总体架构以 [architecture-aio-answer-fetch-tool-runtime-2026-04-12.md](./architecture-aio-answer-fetch-tool-runtime-2026-04-12.md) 和 [design-aio-parallel-playwright-context-2026-04-11.md](./design-aio-parallel-playwright-context-2026-04-11.md) 为准。

---

## 1. 一句话结论

接入 AIO 后，A4 的职责应重新定义为：

`构造抓取 job + 调用 AIO Tool + 消费运行事件 + 驱动用户接管 + 校验结果包 + 写入 artifact + 推进分析`

而不是：

`自己创建浏览器 client 并直接写平台步骤`

权威分层固定为：

1. `Orchestrator`
   - 负责用户意图、采集模式选择、后续分析路由
2. `Fetch Answer Agent / A4`
   - 负责把业务意图变成 `answer_fetch_job`，调用 `aio_answer_fetch`，消费事件并写回 Artifact
3. `AIO Answer Fetch Tool`
   - 负责四平台 PlatformFetchJob 编排、BlockerPolicy、接管事件、结果包归一化
4. `AIO Runtime`
   - 负责 Browser Agent / Playwright executor、Chromium / CDP / VNC、AuthContext 与 RunContext
5. `Frontend`
   - 只负责展示聊天事件与 attach 到已经准备好的 `surface_url`，不创建浏览器、不导航页面、不决定平台调度

本设计中的状态词与治理语义以 [design-aio-runtime-contracts-2026-04-01.md](./design-aio-runtime-contracts-2026-04-01.md) 为准。

---

## 2. 官方依据

本路由设计依赖的官方事实：

1. 官方 browser guide 明确了：
   - `browser-ui`
   - `VNC`
   - GUI action
   - `Canvas + CDP`
2. 官方 OpenAPI browser 组提供：
   - `page/*`
   - `tabs`
   - `cookies`
   - `state/*`
   - `network/*`
   - `captcha/*`
3. 官方 sandbox/file/shell/code 说明：
   - 浏览器、文件、代码、终端共处一个 runtime
4. 实践文章证明：
   - 可在同一 sandbox 内持续会话、接管、恢复

因此 A4 可以把“浏览器 + 接管 + 持久化结果”作为一组统一 Tool 能力来调用，但不直接决定底层 transport、tab 生命周期、VNC surface 创建和恢复策略。

---

## 3. 当前代码出发点

当前 A4 现实是：

1. [nodes_a4.py](../aeo-platform/backend/app/workflow/nodes_a4.py)
   - 同时包含平台选择、client 初始化、执行、容错
2. [browser_action_runtime.py](../aeo-platform/backend/app/workflow/browser_action_runtime.py)
   - 已有浏览器人工交接原语
3. 各平台 handler
   - 平台逻辑与动作细节耦合较深

AIO 路由的目标不是推翻 A4，而是把其中的：

1. 决策
2. policy
3. 执行
4. 状态迁移

拆开。

---

## 4. 路由输入

A4 Agent 在进入 AIO 路由时只应读取这些输入，并把它们组装成 `answer_fetch_job`：

1. `workspace_id`
2. `session_id`
3. `task_id`
4. `questions`
5. `brand_profile`
6. `platform_filter`
7. `fetch_mode`
8. `runtime_preference`
9. `resume_context`
10. `specta_user_id`

### 解释

1. `platform_filter`
   - 用户显式指定的平台子集
2. `fetch_mode`
   - 保留用户侧语义，但在 AIO 路由里不再等价于“API vs Browser”
3. `runtime_preference`
   - `aio_cloud | local_runtime | legacy`
4. `resume_context`
   - 表示当前是否是接管后恢复
5. `specta_user_id`
   - 用于定位用户级 AuthContext，不能用 task/entity 代替

---

## 5. 路由输出

A4 节点最终输出这些统一结果。它们来自 AIO Tool 的 result packet，而不是 A4 私有抓取实现：

1. `platform_plan`
2. `platform_runs`
3. `platform_results`
4. `pending_takeover`
5. `resume_checkpoint`
6. `artifacts`
7. `progress`
8. `blocker_code`
9. `policy_decision`
10. `resume_gate_result`
11. `tool_events`

其中：

1. `blocker_code`
   - 当前阻塞原因，必须来自共享合同枚举
2. `policy_decision`
   - AIO Tool / BlockerPolicy 对当前阻塞的治理决策
3. `resume_gate_result`
   - 接管后恢复闸门的权威结果
4. `tool_events`
   - 包括 `platform_started / blocker_detected / auto_action_taken / takeover_required / platform_result / job_completed`

---

## 6. A4 主循环

统一流程固定为：

```text
select platforms
-> build answer_fetch_job
-> dispatch aio_answer_fetch
-> stream platform events
-> if takeover_required: ask user to attach prepared surface
-> on user_done: call resume_takeover / continue tool job
-> receive result packet
-> validate / normalize / persist
-> continue analytics
```

也就是：

`answer_fetch_job -> aio_answer_fetch -> tool_events -> user_takeover_if_needed -> result_packet -> artifact_writeback -> analytics`

这是生产主循环。
不允许在平台 handler、前端 Canvas 或 backend adapter 内另起一套私有接管/恢复循环。

---

## 7. 平台选择规则

## 7.1 基础选择

1. 若 `platform_filter` 不为空
   - 只跑过滤后的平台
2. 否则默认跑四平台：
   - `deepseek`
   - `doubao`
   - `yuanbao`
   - `kimi`

## 7.2 AIO 路由下的执行原则

在 `runtime_preference = aio_cloud` 下：

1. 四平台都按 `AIO Answer Fetch Tool` 的 execution contract 执行
2. 旧 API client 路径不再作为 AIO 路由默认实现
3. 旧 API client 可保留为 legacy/回退，不纳入 AIO 主流程

---

## 8. 并发与串行策略

## 8.1 顶层策略

默认采用：

1. `问题级串行`
2. `平台级四路并行`
3. `人工接管队列串行`

理由：

1. 问题之间有明确进度顺序和 artifact 写入顺序
2. 平台之间应并行执行，避免 DeepSeek 阻塞 Kimi / 豆包 / 元宝
3. 用户的人机接管是稀缺注意力资源，可以排队串行

## 8.2 生产目标默认值

1. 同一问题默认并发 `4` 个平台执行
2. 同一时刻只允许 `1` 个 `takeover_state=active`
3. 一旦某平台进入接管，其他平台自动化继续执行，但不得抢占用户当前正在接管的可视 surface
4. 如果底层 AIO Runtime 仍只有一个可视浏览器进程，则必须由 Runtime 层提供 browser context / page 隔离或接管队列，不允许前端通过自动切 tab 来模拟并行

## 8.3 过渡实现约束

当前后端 `connect_over_cdp` 方式只能作为过渡路径或能力探针。生产级目标是把 Playwright executor 放在 AIO Runtime 内或与 AIO Runtime 同机协作，避免后端跨网络持有 UI 操作细节。

## 8.4 单平台上下文规则

同一平台在同一时刻只允许：

1. 一个活动 platform run
2. 一个 `profile_root`
3. 一个 `run_root`
4. 一个最新 state snapshot

### 8.5 AuthContext 与 RunContext

用户登录态绑定 Specta 用户与平台：

```text
/data/auth/{env}/{specta_user_id}/{platform}/browser_state.json
```

单次抓取产物绑定品牌实体、任务与平台：

```text
/data/runs/{entity_id}/{task_id}/{platform}/result.json
```

A4 只传递上下文 key，不直接读写浏览器 profile 细节。

---

## 9. 单平台执行循环

对每个平台，AIO Tool 内部固定采用以下循环。A4 只消费事件与结果：

1. `ensure_session`
2. `ensure_platform_roots`
3. `aio_browser_manage_state(load)`
4. `aio_browser_perceive_page`
5. 生成 `blocker_code`
6. 调用 AIO Tool / BlockerPolicy
7. 根据 `policy_decision` 执行：
   - tool action
   - auto recover
   - request takeover
   - skip/fail
8. 结果稳定后：
   - `extract_answer`
   - `extract_references`
   - `manage_state(save)`
9. 写入 artifact 和 runtime state

A4 不应把这些步骤重新写成四套平台脚本。A4 的边界是调用 Tool、处理事件、驱动用户确认、校验结果、写入业务 artifact。

---

## 10. BlockerPolicy Decision

BlockerPolicy 的输入固定为：

1. `blocker_code`
2. `platform`
3. `runtime_health`
4. `retry_count`
5. `resume_context`

输出固定为：

1. `policy_decision`
2. `preferred_takeover_mode`
3. `retry_budget_delta`

### 说明

1. `AIO Tool / Browser Agent`
   - 负责把页面感知结果归一化成 `blocker_code`
2. `AIO Tool / BlockerPolicy`
   - 负责把 `blocker_code` 翻译成治理决策
3. `A4`
   - 只消费 blocker event，并把需要人工处理的事件翻译成用户可理解的接管消息
4. `Platform Execution Contract`
   - 只声明该平台已知 blocker 类型和 guardrails

明确删除旧约束：  
平台 contract 不再承担“是否接管”的判定。
接管条件统一由 `blocker_code + AIO Tool / BlockerPolicy` 决定。

---

## 11. `blocker_code` 分类规则

允许的 blocker 来源只有共享合同定义的八类：

1. `login_required`
2. `captcha_required`
3. `ui_drift`
4. `state_invalid`
5. `navigation_failed`
6. `element_not_found`
7. `proxy_or_region_blocked`
8. `runtime_unavailable`

分类顺序建议：

1. 先判断 runtime 是否可用
2. 再判断登录/验证码
3. 再判断导航/元素
4. 最后判断 UI 漂移和状态损坏

---

## 12. 典型 `policy_decision` 映射

以下只是 AIO Tool / BlockerPolicy 的默认决策基线，不属于 Platform Execution Contract：

1. `login_required`
   - 默认 `request_takeover`
2. `captcha_required`
   - 默认 `request_takeover`
3. `ui_drift`
   - 首次 `auto_recover`，多次失败后 `request_takeover` 或 `fail_platform`
4. `state_invalid`
   - 默认 `auto_recover`
5. `navigation_failed`
   - 默认 `retry` 或 `auto_recover`
6. `element_not_found`
   - 默认 `retry` 或 `auto_recover`
7. `proxy_or_region_blocked`
   - 默认 `skip_platform` 或 `fail_platform`
8. `runtime_unavailable`
   - 默认 `fail_session`

---

## 13. `resume_gate_result` 规则

接管完成后 A4 不能直接假定成功，必须由 AIO Tool 进入恢复闸门：

1. `aio_browser_perceive_page`
2. `aio_browser_detect_captcha`
3. 必要时 `aio_browser_extract_error_state`
4. 必要时 `aio_browser_manage_state(load)`

恢复闸门只允许输出：

1. `pass`
2. `fail_login_required`
3. `fail_captcha_required`
4. `fail_ui_not_ready`
5. `fail_state_corrupt`
6. `fail_unknown`

### 允许恢复的唯一条件

只有 `resume_gate_result = pass` 时，AIO Tool 才能恢复自动执行，A4 才能继续等待 `platform_result`。

否则：

1. 再次分类 blocker
2. 再次交给 AIO Tool / BlockerPolicy
3. 由 policy 决定重新接管、跳过、失败还是终止 session

---

## 14. 失败降级规则

## 14.1 平台级

1. `skip_platform`
   - 记录失败 artifact，继续其他平台
2. `fail_platform`
   - 当前平台立即终止，继续整体 A4

## 14.2 会话级

1. `fail_session`
   - 标记当前 session 不可继续使用
2. A4 可选择：
   - 重新申请 session
   - 或整体失败

---

## 15. 职责边界

### Platform Execution Contract 只定义

1. `allowed_tools`
2. `extraction_schema`
3. `known_blockers`
4. `platform_guardrails`

### AIO Tool / BlockerPolicy 负责

1. `blocker_code -> policy_decision`
2. 接管模式选择
3. retry budget 调整

### A4 负责

1. 平台选择
2. 构造 `answer_fetch_job`
3. 调用 `aio_answer_fetch`
4. 消费 tool events
5. 将 `takeover_required` 翻译成用户可理解的接管消息
6. 在用户点击完成后通知 Tool 继续
7. 校验、归一化、持久化 result packet
8. 推进后续 analytics / report

### Backend Adapter 不负责

1. takeover 触发 policy
2. session/takeover 状态迁移
3. 平台业务 guardrail
4. 前端可见云电脑 surface 的产品交互策略

### Frontend 不负责

1. 创建浏览器
2. 导航到登录页
3. 自动切换平台 tab
4. 判定哪个平台应该继续抓取
5. 保存登录态
6. 解释 AIO 内部 blocker

---

## 16. 非目标

1. 不在本设计里定义具体 DOM selector
2. 不在本设计里定义数据库表结构
3. 不在本设计里定义前端弹层 UI 细节
4. 不允许 Platform Execution Contract 再定义私有接管判定
5. 不把 `aio_answer_fetch` 退化成前端云电脑交付物

---

## 17. 下一步

1. 与 Session Persistence 文档对齐共享状态机
2. 与 Platform Execution Contract 文档对齐 `known_blockers` 字段
3. 实现阶段把 `blocker_code/policy_decision/resume_gate_result` 落成显式字段
4. 将 A4 代码主路径收敛到 `aio_answer_fetch` Tool Contract，逐步减少 A4 内直接 CDP/Playwright 细节

---

## 18. 相关文档

1. 共享合同：[design-aio-runtime-contracts-2026-04-01.md](./design-aio-runtime-contracts-2026-04-01.md)
2. 四平台 Platform Execution Contract：[design-aio-four-platform-skill-contract-2026-03-31.md](./design-aio-four-platform-skill-contract-2026-03-31.md)
3. Session 持久化模型：[design-aio-session-persistence-model-2026-03-31.md](./design-aio-session-persistence-model-2026-03-31.md)
