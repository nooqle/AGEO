# Specta AIO 验证、运维与成本设计

> 日期：2026-03-31
> 状态：Draft
> 目标：定义 AIO-only 这条线的最终验收、监控、故障演练和成本守卫，作为进入生产前的统一标准。

---

## 1. 一句话结论

AIO 集成只有在同时满足这四类正确性后，才算进入可生产状态：

1. `Runtime correctness`
2. `Business correctness`
3. `Governance correctness`
4. `Cost correctness`

验收不能只看“浏览器打开了”，而要看：

`接管、恢复、状态隔离、旧 bundle 失效、清理回收、四平台真实结果`

---

## 2. 官方依据

### 2.1 official guide

1. [Introduction](https://sandbox.agent-infra.com/zh/guide/start/introduction)
2. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)
3. [Sandbox](https://sandbox.agent-infra.com/zh/guide/basic/sandbox)
4. [Authentication](https://sandbox.agent-infra.com/zh/guide/basic/authentication)

### 2.2 official openapi

至少围绕这些接口建立验收：

1. `GET /v1/sandbox`
2. `GET /v1/browser/info`
3. `POST /v1/browser/actions`
4. `GET /v1/browser/screenshot`
5. `POST /v1/file/read|write|list`
6. `POST /v1/shell/exec|wait`
7. `POST /tickets`

### 2.3 best-practice article

1. connect/disconnect 保持会话
2. 文件系统传状态
3. VNC 只做 fallback

### 2.4 Specta wrapper decision

1. Canvas 为主，VNC 为 fallback
2. `profile_root` 与 `run_root` 分层
3. takeover 只经 Specta 控制面

---

## 3. V1 最小可交付标准

## 3.1 Runtime correctness

必须满足：

1. `8011 /health = healthy`
2. `18180 /v1/sandbox = 200`
3. `runtime/info / session acquire / browser info` 可用
4. browser actions 能通过真实 AIO 接口执行
5. Canvas 主接管可用
6. VNC fallback 可用

## 3.2 Business correctness

必须满足：

1. 四个平台都能进入 AIO 执行
2. 触发接管后能恢复继续
3. `extract_answer` 返回有效数据
4. `extract_references` 不会串平台
5. `resume gate` 决策能解释继续或失败原因
6. `resume_failed` 时不会误关闭当前 takeover Canvas，且 handler 会收到非 `completed` 结算

## 3.3 Governance correctness

必须满足：

1. 旧 bundle 失效
2. refresh 后可 reopen 当前 takeover
3. 不同 `task_id/run_id` 不串 `run_root`
4. `session_state / takeover_state` 迁移可审计
5. resolve 后 replay 旧 bundle 必须失败

## 3.4 Cost correctness

必须满足：

1. 同一 workspace 默认只有一个主 session
2. 空闲 session 可回收
3. VNC 只在 fallback 时启用
4. `run_root` 可定期清理，不无限增长

---

## 4. 局部 QA 矩阵

## 4.1 Session / Takeover 持久控制面

1. Backend 重启后 takeover 还能读出
2. 前端刷新后可 reopen
3. 同一 request 的 takeover 不丢失
4. 不同 task/run 不串 state
5. 旧 takeover 过期后不可继续使用

## 4.2 Backend Adapter

1. `browser/info` 正常
2. `browser/actions` 正常
3. `browser/screenshot` 正常
4. `file read/write/list` 正常
5. 错误能归一化为标准错误对象

## 4.3 四平台执行

1. Doubao
2. Yuanbao
3. Kimi
4. DeepSeek

每个平台至少验证：

1. 进入 AIO
2. 碰到 login 或 modal 可发起 takeover
3. 完成后能继续执行
4. 能拿到有效回答

## 4.4 接管恢复

1. Canvas ready 后 heartbeat 正常
2. refresh 后 reopen 正常
3. resolve 后任务继续
4. cancel 后状态明确
5. expire 后状态明确
6. resume_failed 后不静默失败

---

## 5. 全量 E2E 矩阵

每个平台都至少覆盖：

1. 首次接管
2. 页面刷新后恢复
3. resolve 正常继续
4. cancel 行为正确
5. expire 行为正确

### Doubao

1. 登录接管
2. 继续执行
3. 成功提取

### Yuanbao

1. 登录或 modal 接管
2. 继续执行
3. 成功提取

### Kimi

1. 登录接管
2. 流式完成
3. 成功提取

### DeepSeek

1. 登录接管
2. 地域/登录态边界处理
3. 成功提取

---

## 6. 监控指标

### Session

1. `aio_sessions_total`
2. `aio_sessions_ready`
3. `aio_sessions_idle`
4. `aio_sessions_failed`
5. `aio_sessions_draining`

### Takeover

1. `aio_takeover_requested_total`
2. `aio_takeover_resolved_total`
3. `aio_takeover_cancelled_total`
4. `aio_takeover_expired_total`
5. `aio_takeover_resume_failed_total`
6. `resume_gate_denied_rate`
7. `takeover_expired_due_to_missed_heartbeat`

### State / Isolation

1. `aio_state_save_success_rate`
2. `aio_state_load_success_rate`
3. `cross_run_state_bleed_count`

### Runtime

1. `aio_runtime_unavailable_total`
2. `aio_canvas_to_vnc_fallback_rate`
3. `aio_session_reclaim_total`

---

## 7. Chaos / 故障演练

必须覆盖：

1. AIO runtime 短暂失联
2. active takeover 时前端刷新
3. resolve 后 replay 旧 bundle
4. 同 workspace 第二个 task 错复用前一个 `run_root`
5. missed heartbeat 导致 takeover 过期
6. `profile_root` 存在但 `run_root` 损坏

每项都要验证：

1. 是否有明确错误
2. 是否能受控恢复
3. 是否有审计日志

---

## 8. 成本守卫

1. 一个 workspace 默认一个主 session
2. idle session 默认 30 分钟回收
3. VNC 只在 fallback 时开启
4. run 级下载、截图、快照必须有清理 job
5. shell/code 内部能力只在必要时调用

---

## 9. 最终 Code Review

全部开发完成后，做两轮 review：

### 9.1 架构师 review

重点检查：

1. 控制面与执行面边界
2. session/takeover 单一权威源
3. adapter 是否膨胀成万能 client
4. 前后端状态词是否仍一致
5. 四平台是否真正共用执行骨架

### 9.2 QA review

重点检查：

1. 行为是否符合设计文档
2. 四平台 E2E 是否稳定
3. 接管恢复是否残留边界 bug
4. 错误日志与错误文案是否可定位问题
5. 清理与回收是否生效

---

## 10. 非目标

本设计不处理：

1. follow-up 路由
2. orchestrator 稳定性
3. 本地客户端 / 插件路线

---

## 11. 下一步

1. 先完成 Session / Takeover 持久控制面
2. 再补完 Backend Adapter
3. 再做四平台 AIO 执行收口和 takeover 恢复硬化
