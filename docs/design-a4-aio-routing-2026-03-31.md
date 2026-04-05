# Specta A4 AIO 路由设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义 A4 节点在接入 AIO 后，如何基于四平台 Skill Contract、Harness Policy 与 Specta Tools 做决策式路由，而不是把执行逻辑写死在 node 或 handler 中。

---

## 1. 一句话结论

接入 AIO 后，A4 的职责应重新定义为：

`平台选择 + blocker 分类 + Harness Policy 调用 + 执行控制 + 恢复推进`

而不是：

`自己创建浏览器 client 并直接写平台步骤`

权威分层固定为：

1. `Skill Contract`
   - 只定义 `allowed_tools / extraction_schema / known_blockers / platform_guardrails`
2. `Harness Policy`
   - 统一决定 `blocker_code -> policy_decision`
3. `A4`
   - 负责执行控制
4. `AioSandboxBackend`
   - 负责能力落地，不做 policy
5. `SessionManager / TakeoverService`
   - 负责共享状态机

本设计中的状态词与治理语义以 [design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md) 为准。

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

因此 A4 可以把“浏览器 + 接管 + 持久化结果”作为一组统一 runtime 能力来调度，但不直接决定底层 transport 和恢复策略。

---

## 3. 当前代码出发点

当前 A4 现实是：

1. [nodes_a4.py](/D:/AGEO-worktrees/browser-operator-design/aeo-platform/backend/app/workflow/nodes_a4.py)
   - 同时包含平台选择、client 初始化、执行、容错
2. [browser_action_runtime.py](/D:/AGEO-worktrees/browser-operator-design/aeo-platform/backend/app/workflow/browser_action_runtime.py)
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

A4 Agent 在进入 AIO 路由时只应读取这些输入：

1. `workspace_id`
2. `session_id`
3. `task_id`
4. `questions`
5. `brand_profile`
6. `platform_filter`
7. `fetch_mode`
8. `runtime_preference`
9. `resume_context`

### 解释

1. `platform_filter`
   - 用户显式指定的平台子集
2. `fetch_mode`
   - 保留用户侧语义，但在 AIO 路由里不再等价于“API vs Browser”
3. `runtime_preference`
   - `aio_cloud | local_runtime | legacy`
4. `resume_context`
   - 表示当前是否是接管后恢复

---

## 5. 路由输出

A4 节点最终输出这些统一结果：

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

其中：

1. `blocker_code`
   - 当前阻塞原因，必须来自共享合同枚举
2. `policy_decision`
   - Harness Policy 对当前阻塞的治理决策
3. `resume_gate_result`
   - 接管后恢复闸门的权威结果

---

## 6. A4 主循环

统一流程固定为：

```text
select platforms
-> acquire runtime
-> build per-platform plan
-> perceive
-> classify blocker
-> ask harness policy
-> act / recover / takeover
-> resume gate
-> extract
-> persist
```

也就是：

`perceive -> classify blocker -> ask harness policy -> act/recover/takeover -> resume gate -> extract -> persist`

这是 V1 的唯一允许循环。  
不允许在平台 skill 或 backend adapter 内另起一套私有接管/恢复循环。

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

1. 四平台都按 browser skill 执行
2. 旧 API client 路径不再作为 AIO 路由默认实现
3. 旧 API client 可保留为 legacy/回退，不纳入 AIO 主流程

---

## 8. 并发与串行策略

## 8.1 顶层策略

默认采用：

1. `问题级串行`
2. `平台级有界并发`

理由：

1. 问题之间有明确进度顺序和 artifact 写入顺序
2. 平台之间可以有限并发，但同一 sandbox 的接管只能单活

## 8.2 V1 默认值

1. 同一问题最多并发 `2` 个平台执行
2. 同一时刻只允许 `1` 个 `takeover_state=active`
3. 一旦某平台进入接管，其他平台自动化继续执行，但不得抢占同一浏览器上下文

## 8.3 单平台上下文规则

同一平台在同一时刻只允许：

1. 一个活动 skill run
2. 一个 `profile_root`
3. 一个 `run_root`
4. 一个最新 state snapshot

---

## 9. 单平台执行循环

对每个平台，A4 Agent 固定采用以下循环：

1. `ensure_session`
2. `ensure_platform_roots`
3. `aio_browser_manage_state(load)`
4. `aio_browser_perceive_page`
5. 生成 `blocker_code`
6. 调用 Harness Policy
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

---

## 10. Harness Policy Decision

Harness Policy 的输入固定为：

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

1. `A4`
   - 负责把感知结果归一化成 `blocker_code`
2. `Harness Policy`
   - 负责把 `blocker_code` 翻译成治理决策
3. `Skill Contract`
   - 只声明该平台已知 blocker 类型和 guardrails

明确删除旧约束：  
平台 skill 不再承担“是否接管”的判定。  
V1 起接管条件统一由 `blocker_code + Harness Policy` 决定。

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

以下只是 Harness Policy 的默认决策基线，不属于 Skill Contract：

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

接管完成后 A4 不能直接假定成功，必须进入恢复闸门：

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

只有 `resume_gate_result = pass` 时，A4 才能恢复自动执行。

否则：

1. 再次分类 blocker
2. 再次调用 Harness Policy
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

### Skill Contract 只定义

1. `allowed_tools`
2. `extraction_schema`
3. `known_blockers`
4. `platform_guardrails`

### Harness Policy 负责

1. `blocker_code -> policy_decision`
2. 接管模式选择
3. retry budget 调整

### A4 负责

1. 平台选择
2. blocker 分类
3. policy 调用
4. 执行循环
5. 恢复闸门
6. 抽取与持久化

### Backend Adapter 不负责

1. takeover 触发 policy
2. session/takeover 状态迁移
3. 平台业务 guardrail

---

## 16. 非目标

1. 不在本设计里定义具体 DOM selector
2. 不在本设计里定义数据库表结构
3. 不在本设计里定义前端弹层 UI 细节
4. 不允许 Skill Contract 再定义私有接管判定

---

## 17. 下一步

1. 与 Session Persistence 文档对齐共享状态机
2. 与 Skill Contract 文档对齐 `known_blockers` 字段
3. 实现阶段把 `blocker_code/policy_decision/resume_gate_result` 落成显式字段

---

## 18. 相关文档

1. 共享合同：[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
2. 四平台 Skill Contract：[design-aio-four-platform-skill-contract-2026-03-31.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-four-platform-skill-contract-2026-03-31.md)
3. Session 持久化模型：[design-aio-session-persistence-model-2026-03-31.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-session-persistence-model-2026-03-31.md)
