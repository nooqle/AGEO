# Specta AIO Runtime 共享合同设计

> 日期：2026-04-01
> 状态：Draft
> 目标：为 Specta AIO 文档包提供单一权威的运行时术语、状态机合同、错误与治理边界，避免各文档各自发明状态词、恢复语义和职责边界。

---

## 1. 一句话结论

从这一版开始，AIO 文档包中的：

1. `blocker_code`
2. `policy_decision`
3. `resume_gate_result`
4. `session_state`
5. `takeover_state`

都必须引用本合同，不允许在单个文档里再定义平行语义。

---

## 2. 官方依据

本合同不是直接来自某一条单一 API，而是对下列官方能力和实践的 Specta 收口：

1. 官方 guide
   - sandbox / browser / shell / file / mcp / authentication
2. 官方 OpenAPI
   - `sandbox`, `browser`, `file`, `shell`, `code`, `auth`, `proxy`, `skills`
3. 实践文章
   - 持久化、接管、connect/disconnect、VNC/browser-ui 的使用边界
4. Specta 自身封装决策
   - `REST-first / CDP-second / MCP-third`
   - Agent-first 架构
   - A4 执行控制与 Harness Policy 分层

因此本合同属于：

`官方能力之上的 Specta 统一治理合同`

---

## 3. 适用范围

以下文档必须引用本合同：

1. `design-a4-aio-routing-2026-03-31.md`
2. `design-aio-session-persistence-model-2026-03-31.md`
3. `design-aio-backend-adapter-2026-03-31.md`
4. `design-aio-access-relay-security-2026-03-31.md`
5. `design-aio-frontend-takeover-ui-2026-03-31.md`
6. `design-aio-validation-ops-and-cost-2026-03-31.md`
7. `design-aio-four-platform-skill-contract-2026-03-31.md`
8. `design-aio-session-manager-2026-03-31.md`
9. `design-aio-takeover-protocol-2026-03-31.md`

---

## 4. 权威枚举定义

## 4.1 `blocker_code`

用于表达：

`当前平台自动化无法继续的归一化阻塞原因`

合法取值只有：

1. `login_required`
2. `captcha_required`
3. `ui_drift`
4. `state_invalid`
5. `navigation_failed`
6. `element_not_found`
7. `proxy_or_region_blocked`
8. `runtime_unavailable`

## 4.2 `policy_decision`

用于表达：

`Harness Policy 对 blocker_code 的统一治理决策`

合法取值只有：

1. `retry`
2. `auto_recover`
3. `request_takeover`
4. `skip_platform`
5. `fail_platform`
6. `fail_session`

## 4.3 `resume_gate_result`

用于表达：

`人工接管结束后，恢复闸门对“是否允许自动化继续”的判定`

合法取值只有：

1. `pass`
2. `fail_login_required`
3. `fail_captcha_required`
4. `fail_ui_not_ready`
5. `fail_state_corrupt`
6. `fail_unknown`

## 4.4 `session_state`

用于表达：

`AioSandboxSessionManager 权威管理的 session 生命周期`

合法取值只有：

1. `provisioning`
2. `ready`
3. `leased`
4. `takeover_frozen`
5. `idle`
6. `draining`
7. `failed`
8. `destroyed`

## 4.5 `takeover_state`

用于表达：

`TakeoverService / Security Relay / Frontend UI 共同遵守的接管生命周期`

合法取值只有：

1. `requested`
2. `issued`
3. `active`
4. `resolved`
5. `expired`
6. `cancelled`
7. `resume_failed`

---

## 5. 统一职责边界

## 5.1 Skill Contract

只定义：

1. `allowed_tools`
2. `extraction_schema`
3. `known_blockers`
4. `platform_guardrails`

明确不定义：

1. `blocker_code -> policy_decision`
2. 接管是否发起
3. session 状态迁移
4. recovery/retry 的预算策略

## 5.2 Harness Policy

统一决定：

`blocker_code -> policy_decision`

输入至少包括：

1. `blocker_code`
2. `platform`
3. `runtime_health`
4. `retry_count`
5. `resume_context`

输出至少包括：

1. `policy_decision`
2. `preferred_takeover_mode`
3. `retry_budget_delta`

## 5.3 A4

只负责执行控制：

1. 感知
2. 分类 blocker
3. 调用 Harness Policy
4. 执行动作 / 自动恢复 / 接管请求
5. 通过 resume gate 决定是否继续
6. 抽取并持久化结果

## 5.4 Backend Adapter

只负责能力落地：

1. 把 Specta Tools 翻译成 AIO 官方能力
2. 统一 transport、错误映射、恢复提示

明确不做：

1. 平台 policy
2. 业务排序
3. session/takeover 权威状态迁移

## 5.5 Session / Takeover

所有 `session_state` 与 `takeover_state` 的迁移，必须走共享状态机。  
不允许前端、单个平台 skill 或单个 backend 方法绕过权威状态机直接改状态。

---

## 6. 权威状态机边界

## 6.1 `session_state` 权威者

唯一权威写入方：

1. `AioSandboxSessionManager`

允许触发迁移的协作方：

1. `TakeoverService`
2. `CleanupJob`
3. `HealthcheckJob`

但这些协作方必须通过 SessionManager API 迁移，不直接写数据库状态。

## 6.2 `takeover_state` 权威者

唯一权威写入方：

1. `TakeoverService`

允许触发迁移的协作方：

1. 前端 `resolve/cancel/heartbeat`
2. `ResumeGate`
3. `ExpiryJob`

同样只能通过 TakeoverService API 迁移。

---

## 7. 共享运行字段

下列字段从本合同起视为 A4 / Session / Takeover 的公共运行字段：

1. `blocker_code`
2. `policy_decision`
3. `resume_gate_result`
4. `session_state`
5. `takeover_state`
6. `sandbox_ref`
7. `session_id`
8. `takeover_id`
9. `home_dir`
10. `data_root`
11. `platform_root`
12. `profile_root`
13. `run_root`

---

## 8. 命名与路径约束

统一约束：

1. 不写死固定 home 路径
2. `data_root` 必须由 `GET /v1/sandbox` 返回的 `home_dir` 派生
3. `profile_root` 与 `run_root` 必须分离

标准派生：

```text
home_dir
-> data_root = <home_dir>/data
-> profile_root = <data_root>/<workspace_id>/<platform>/profile
-> run_root = <data_root>/<task_id>/<platform>/run
-> platform_root = { profile_root, run_root } 的统称，不单指某一个具体目录
```

---

## 9. 非目标

1. 本合同不定义具体数据库字段实现
2. 本合同不定义具体前端组件 props
3. 本合同不替代官方 AIO guide/OpenAPI
4. 本合同不定义平台特有 DOM 细节

---

## 10. 下一步

1. 所有 AIO 子文档引用本合同并删除平行状态词
2. 所有实现代码在进入开发时先按本合同建立枚举与状态机
3. 文档验收时优先检查是否出现未授权的新状态词

---

## 11. 参考资料

1. AIO 简介: https://sandbox.agent-infra.com/zh/guide/start/introduction
2. AIO Quick Start: https://sandbox.agent-infra.com/zh/guide/start/quick-start
3. AIO Sandbox Guide: https://sandbox.agent-infra.com/zh/guide/basic/sandbox
4. AIO Browser Guide: https://sandbox.agent-infra.com/zh/guide/basic/browser
5. AIO Shell Guide: https://sandbox.agent-infra.com/zh/guide/basic/shell
6. AIO File Guide: https://sandbox.agent-infra.com/zh/guide/basic/file
7. AIO MCP Guide: https://sandbox.agent-infra.com/zh/guide/basic/mcp
8. AIO Authentication Guide: https://sandbox.agent-infra.com/zh/guide/basic/authentication
9. AIO API: https://sandbox.agent-infra.com/zh/api
10. 实践文章（connect/disconnect/persist）: https://www.cnblogs.com/alisystemsoftware/p/19646364
11. 实践文章（browser-ui/VNC）: https://segmentfault.com/a/1190000047359831
