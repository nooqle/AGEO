# Specta AIO Session 持久化模型设计

> 日期：2026-03-31
> 状态：Draft
> 目标：把 Specta 的 AIO session / takeover 控制面从进程内内存提升为“重启后可恢复、前后端可对齐”的持久模型。

---

## 1. 一句话结论

Specta 的 AIO 持久化必须拆成三层：

1. `数据库中的权威控制面`
2. `进程内缓存中的热态镜像`
3. `sandbox 文件系统中的 profile / run 状态`

其中：

1. 数据库负责 `session_state / takeover_state / request 关联 / 时间戳 / lease`
2. 进程内缓存只负责加速和 live probe
3. sandbox 文件系统负责登录态、browser state、单次 run 产物

本设计中的术语以
[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
为准。

---

## 2. 官方依据

### 2.1 official guide

1. [Sandbox](https://sandbox.agent-infra.com/zh/guide/basic/sandbox)
2. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)
3. [File](https://sandbox.agent-infra.com/zh/guide/basic/file)
4. [Shell](https://sandbox.agent-infra.com/zh/guide/basic/shell)

### 2.2 official openapi

当前 runtime 已验证可用的基础接口：

1. `GET /v1/sandbox`
2. `GET /v1/browser/info`
3. `POST /v1/file/read`
4. `POST /v1/file/write`
5. `POST /v1/file/list`
6. `POST /v1/file/find`
7. `POST /v1/file/search`
8. `POST /v1/shell/exec`
9. `POST /v1/shell/view`
10. `POST /v1/shell/wait`

### 2.3 best-practice article

1. `connect / disconnect` 保留浏览器会话
2. 通过文件系统传递状态，不用进程级全局变量
3. 统一把 runtime 产物落到 `home_dir/data`

### 2.4 Specta wrapper decision

1. `home_dir` 只能从 `GET /v1/sandbox` 派生，不能写死
2. `profile_root` 与 `run_root` 必须分层
3. `request_id -> takeover_id -> session_id -> task_id/run_id` 必须能持久恢复

---

## 3. 持久化目标

必须满足：

1. Backend 重启后仍能恢复既有 session / takeover
2. 前端刷新后仍能重开当前 takeover
3. 同 workspace 下多次分析不会串 `run_root`
4. resolve / cancel / expire 后旧 takeover 不会错误复用
5. 旧 request 和新 task/run 不会串场

---

## 4. 三层模型

## 4.1 数据库层

数据库是权威事实源。

### 表 1：`aio_runtime_sessions`

字段：

1. `id`
2. `session_id`
3. `workspace_id`
4. `sandbox_ref`
5. `base_url`
6. `aio_version`
7. `home_dir`
8. `data_root`
9. `browser_info_json`
10. `session_state`
11. `holders_json`
12. `ref_count`
13. `current_takeover_id`
14. `automation_lock`
15. `human_takeover_lock`
16. `last_seen_at`
17. `last_healthcheck_at`
18. `expires_at`
19. `created_at`
20. `updated_at`

### 表 2：`aio_runtime_takeovers`

字段：

1. `id`
2. `takeover_id`
3. `session_id`
4. `workspace_id`
5. `user_id`
6. `platform`
7. `mode`
8. `reason`
9. `takeover_state`
10. `frontend_id`
11. `request_id`
12. `task_id`
13. `run_id`
14. `action_type`
15. `resume_gate_result`
16. `requested_at`
17. `issued_at`
18. `last_heartbeat_at`
19. `resolved_at`
20. `expires_at`
21. `created_at`
22. `updated_at`

### 表 3：`aio_platform_runtime_states`

字段：

1. `id`
2. `session_id`
3. `workspace_id`
4. `task_id`
5. `platform`
6. `profile_root`
7. `run_root`
8. `cookies_path`
9. `state_path`
10. `session_meta_path`
11. `checkpoint_root`
12. `snapshot_root`
13. `download_root`
14. `extraction_path`
15. `last_state_save_at`
16. `last_state_load_at`
17. `updated_at`

### 运行约束

1. `profile_root` 只承载长期登录态与浏览器 state
2. `run_root` 只承载单次 task/run 的 checkpoint、snapshot、download、extraction
3. `last_state_save_at` 与 `last_state_load_at` 必须由 backend adapter 在真实读写时更新，不能只靠目录存在来推断

---

## 4.2 进程内缓存层

进程内缓存不是权威源，只是热态镜像。

保留内容：

1. `session_id -> SpectaAioSession`
2. `takeover_id -> SpectaAioTakeover`
3. `workspace_id -> session_id`
4. `readiness_probe`

### 说明

`readiness_probe` 是典型的进程内 live 句柄，不能持久化。  
Backend 重启后：

1. takeover/session 仍可恢复
2. live probe 丢失
3. 自动恢复会退化成“用户显式点完成后再继续”

这是允许的，但必须有清晰日志。

---

## 4.3 sandbox 文件系统层

`data_root` 必须通过：

```text
data_root = <home_dir>/data
```

派生，不能写死。

### 目录规则

```text
profile_root = <data_root>/<workspace_id>/<platform>/profile
run_root = <data_root>/<workspace_id>/<task_id>/<platform>/run
```

### `profile_root` 存放

1. `cookies.json`
2. `browser_state.json`
3. `session_meta.json`
4. `local_storage.json`

### `run_root` 存放

1. `checkpoints/`
2. `snapshots/`
3. `downloads/`
4. `extraction.json`
5. `last_error_state.json`

---

## 5. 权威状态机

## 5.1 `session_state`

只有这些合法值：

1. `provisioning`
2. `ready`
3. `leased`
4. `takeover_frozen`
5. `idle`
6. `draining`
7. `failed`
8. `destroyed`

### 关键迁移

| from | to | 谁能迁移 | 前置条件 | 后置条件 | 幂等语义 |
| --- | --- | --- | --- | --- | --- |
| provisioning | ready | SessionManager | runtime 探测成功 | 写入 `home_dir/data_root/browser_info_json` | 重复执行仅刷新元数据 |
| ready | leased | SessionManager | 获得 automation holder | `ref_count + 1`，写入 `automation_lock` | 同一 holder 重放只刷新 lease |
| leased | takeover_frozen | SessionManager | takeover `issued/active` | `current_takeover_id` 生效，冻结 automation | 重复冻结不重复写 holder |
| takeover_frozen | leased | SessionManager | takeover `resolved` 且 `resume_gate_result=pass` | 恢复 automation | 多次调用不重复递增 `ref_count` |
| leased | idle | SessionManager | holder 全释放 | `ref_count=0` | 重复释放保持 idle |
| idle | draining | CleanupJob 经 SessionManager | idle TTL 到期 | 标记待回收 | 重复执行不重复排队 |
| draining | destroyed | SessionManager | 外部资源已清理 | 永不再分配 | 幂等 |
| * | failed | SessionManager / HealthcheckJob | runtime 无法恢复 | 写入失败事实 | 幂等刷新错误信息 |

## 5.2 `takeover_state`

只有这些合法值：

1. `requested`
2. `issued`
3. `active`
4. `resolved`
5. `expired`
6. `cancelled`
7. `resume_failed`

### 关键迁移

| from | to | 谁能迁移 | 前置条件 | 后置条件 | 幂等语义 |
| --- | --- | --- | --- | --- | --- |
| requested | issued | TakeoverService | bundle 已签发 | takeover 可打开 | 旧 bundle 失效，新 bundle 生效 |
| issued | active | TakeoverService | 首个 heartbeat | 绑定 `frontend_id`，冻结 session | 同一 frontend 重放只刷新时间 |
| active | resolved | TakeoverService | resolve 请求 | 进入 resume gate | 重复 resolve 不重新激活 |
| active | cancelled | TakeoverService | cancel 请求 | 释放冻结 | 幂等 |
| issued/active | expired | ExpiryJob | TTL 到期 / missed heartbeat | bundle 作废 | 幂等 |
| resolved | resume_failed | ResumeGate | `resume_gate_result != pass` | 保留 takeover 事实供 reopen | 幂等刷新结果 |

---

## 6. 关键关联链

必须能从数据库恢复出：

```text
request_id -> takeover_id -> session_id -> workspace_id -> task_id/run_id
```

恢复用途：

1. 页面刷新后的接管重开
2. backend 重启后的 takeover 查询
3. 旧 request 和当前 run 的隔离判断
4. QA 与日志审计

---

## 7. 缓存如何回填

当进程内没有命中时：

1. `get_session(session_id)`
   - 先查 DB
   - 再回填 `_sessions_by_id`
2. `get_takeover(takeover_id)`
   - 先查 DB
   - 再回填 `_takeovers_by_id`
3. `ensure_workspace_session(workspace_id)`
   - 优先查 DB 中未 `failed/destroyed` 的 session
   - 再决定是否新建

说明：

1. DB 是权威
2. 内存只做热缓存

---

## 8. TTL 与清理

### Session

1. `idle`：默认 30 分钟
2. `draining`：默认 5 分钟
3. `failed`：尽快回收

### Takeover

1. `issued`：短 TTL
2. `active`：heartbeat 刷新 TTL
3. `resolved/cancelled/expired`：保留事实，但旧 bundle 立刻失效

### 文件系统

1. `profile_root`：按 workspace/platform 复用
2. `run_root`：按 task 单次隔离
3. 清理 job 只能删 `run_root`，不能误删活跃 `profile_root`

---

## 9. 实施路径

1. 新增 3 张 AIO 持久化表
2. SessionManager 写操作先落 DB，再更新内存镜像
3. 读操作允许内存 miss 后从 DB 回填
4. `ensure_platform_roots` 持久化 `profile_root/run_root`
5. heartbeat / resolve / cancel / expire 全部改成 DB 驱动

---

## 10. 非目标

本设计不负责：

1. follow-up 路由
2. orchestrator policy
3. skill 决策
4. 前端 Canvas 样式

---

## 11. 下一步

1. 实现 DB 模型与 SessionManager 持久层
2. 再把 takeover relay 和前端重开恢复接到持久控制面
