# Specta AIO 四平台执行合同设计

> 日期：2026-03-31
> 状态：Draft
> 目标：为 DeepSeek、Doubao、Yuanbao、Kimi 定义统一的 AIO 执行合同，只保留平台差异，不再把平台执行逻辑散落成互不一致的半脚本 handler。

> 2026-04-12 更新：本文件里的 “Skill Contract” 现在应理解为 `AIO Answer Fetch Tool` 内部的 `Platform Execution Contract`，不是一个新的 public skill，也不是前端 Canvas 交付物。总体架构以 [architecture-aio-answer-fetch-tool-runtime-2026-04-12.md](./architecture-aio-answer-fetch-tool-runtime-2026-04-12.md) 和 [design-aio-parallel-playwright-context-2026-04-11.md](./design-aio-parallel-playwright-context-2026-04-11.md) 为准。

---

## 1. 一句话结论

四个平台都必须复用同一条 AIO 执行骨架：

1. `runtime acquisition`
2. `auth context restore`
3. `page/context lifecycle`
4. `browser-agent operation`
5. `blocker classification`
6. `auto recover or human takeover`
7. `readiness probe`
8. `extraction completion`
9. `result packet emission`

更准确地说，四个平台不是四套孤立脚本，而是同一个 `aio_answer_fetch` job 下的四个 `PlatformFetchJob`。A4 / Fetch Answer Agent 只调用 `AIO Answer Fetch Tool`，不直接操作 tab、CDP、VNC、DOM selector，也不把接管逻辑散落在前端或平台 handler 里。

平台差异只允许留在：

1. `login detection`
2. `modal detection`
3. `success criteria`
4. `extraction schema`
5. `known_blockers`
6. `platform_guardrails`

本设计中的共享状态词以
[design-aio-runtime-contracts-2026-04-01.md](./design-aio-runtime-contracts-2026-04-01.md)
为准。

---

## 2. 官方依据

### 2.1 official guide

1. [Browser](https://sandbox.agent-infra.com/zh/guide/basic/browser)
2. [Sandbox](https://sandbox.agent-infra.com/zh/guide/basic/sandbox)
3. [Authentication](https://sandbox.agent-infra.com/zh/guide/basic/authentication)

### 2.2 official openapi

当前四平台执行合同只建立在这些已存在能力上：

1. `GET /v1/browser/info`
2. `POST /v1/browser/actions`
3. `GET /v1/browser/screenshot`
4. `POST /v1/file/read|write|list`
5. `POST /v1/code/execute`

### 2.3 best-practice article

1. `connect / disconnect`
2. profile 与 run 状态分层
3. VNC / browser-ui 接管边界

### 2.4 Specta wrapper decision

1. 本文件只定义 `allowed_tools / extraction_schema / known_blockers / platform_guardrails`
2. `blocker_code -> policy_decision` 不在本设计里定义
3. follow-up 路由不在本设计里定义
4. `AIO Answer Fetch Tool` 负责把四个平台组织成统一 job，并把 `takeover_required / platform_result / job_completed` 等事件回传给 Agent
5. 前端只根据 `takeover_required.surface_url` attach 到已经准备好的云电脑现场，不负责创建浏览器、不负责导航目标页、不负责调度平台

---

## 3. 统一骨架

四个平台都必须服从这个最小阶段集合：

1. `ensure_runtime`
2. `ensure_auth_context`
3. `ensure_run_context`
4. `open_entry`
5. `restore_profile_state`
6. `check_login_ready`
7. `prepare_chat_surface`
8. `classify_blocker`
9. `auto_handle_dismissible_blocker`
10. `emit_takeover_required`，仅限登录、验证码、人机验证、账号安全确认等必须由用户完成的阻塞
11. `resume_after_takeover_probe`
12. `submit_question`
13. `wait_answer_progress`
14. `wait_answer_complete`
15. `extract_answer`
16. `extract_references`
17. `save_profile_state`
18. `persist_run_artifact`

这条骨架里的“操作浏览器”属于 AIO Runtime 内的 Browser Agent / Playwright executor。Agent 调用 Tool，Tool 操作浏览器；前端只显示接管现场。

### 3.1 共享 handler 原语

四个平台的 browser handler 必须复用同一组共享原语，不再各自维护半套登录/弹窗/提取流程：

1. `prepare_takeover_surface`
2. `prepare_user_action_request`
3. `wait_for_user_action_completion`
4. `run_login_takeover_gate`
5. `run_modal_takeover_gate`
6. `classify_blocker`
7. `auto_recover_dismissible_blocker`
8. `run_resume_probe`
9. `build_success_result`
10. `persist_extraction_artifact`

来源类型：

1. `official openapi`
   - `POST /v1/browser/actions`
   - `GET /v1/browser/screenshot`
   - `POST /v1/file/read`
   - `POST /v1/file/write`
2. `best-practice article`
   - 浏览器状态与提取结果通过文件系统落盘
3. `Specta wrapper decision`
   - handler 共享骨架负责接管门控与结果持久化
   - 平台差异只保留在探针和 schema 层

### 3.2.1 自动处理与人工接管边界

默认由 Browser Agent 自动处理：

1. 广告弹窗
2. cookie / 协议确认
3. app 下载提示
4. 新手引导
5. 轻量 UI 漂移
6. `about:blank`、白屏、错误子页、输入框失焦等可恢复页面状态

必须进入人工接管：

1. 登录
2. 扫码
3. 短信验证码
4. 图形验证码
5. 人机验证
6. 账号安全确认
7. 平台风险控制
8. 用户账号或授权选择

因此，`takeover_required` 不是“平台遇到问题就交给用户”，而是 Browser Agent 已经无法安全自动处理时才上报给 Fetch Answer Agent 的明确事件。

### 3.2 提取结果落盘要求

四个平台一旦产生 `FetchResult(status=success)`，都必须把当次提取结果写入：

1. `run_root/extraction.json`

统一 payload 至少包含：

1. `platform`
2. `question`
3. `answer_text`
4. `references`
5. `source`
6. `saved_at`

来源类型：

1. `official openapi`
   - `POST /v1/file/write`
2. `best-practice article`
   - 多步骤任务状态与产物通过文件系统传递
3. `Specta wrapper decision`
   - `profile_root` 保留登录态
   - `run_root` 保留单次执行 artifact

### 3.3 AuthContext 与 RunContext

登录态必须绑定 Specta 用户与平台，不绑定单次任务：

```text
/data/auth/{env}/{specta_user_id}/{platform}/browser_state.json
```

单次抓取结果必须绑定任务、品牌实体与平台：

```text
/data/runs/{entity_id}/{task_id}/{platform}/result.json
```

这两个上下文不能混用。否则会出现“用户已经登录，但下一次任务仍然反复要求登录”或“一个品牌任务污染另一个品牌任务产物”的问题。

---

## 4. Contract 结构

每个平台合同固定只包含：

```yaml
platform_id:
display_name:
entry_urls:
allowed_tools:
extraction_schema:
known_blockers:
platform_guardrails:
```

### 明确禁止

以下内容不属于 Platform Execution Contract：

1. `policy_decision`
2. 接管是否发起
3. retry 预算
4. session / takeover 状态迁移
5. follow-up 意图理解

---

## 5. DeepSeek

```yaml
platform_id: deepseek
display_name: DeepSeek
entry_urls:
  - https://chat.deepseek.com/
allowed_tools:
  - aio_browser_execute_action
  - aio_browser_take_screenshot
  - aio_browser_request_takeover
  - aio_runtime_read_file
  - aio_runtime_write_file
  - aio_runtime_execute_code
extraction_schema:
  answer: markdown_stream_or_dom_extract
  references: normalized_reference_list
known_blockers:
  - login_required
  - captcha_required
  - proxy_or_region_blocked
  - ui_drift
platform_guardrails:
  - verify_region_variant_before_submit
  - never_assume_existing_login
```

### 成功标准

1. 已离开登录页
2. 输入区可操作
3. 回答流已开始或最终回答节点可见
4. 能抽出非空回答文本

---

## 6. Doubao

```yaml
platform_id: doubao
display_name: 豆包
entry_urls:
  - https://www.doubao.com/chat/
allowed_tools:
  - aio_browser_execute_action
  - aio_browser_take_screenshot
  - aio_browser_request_takeover
  - aio_runtime_read_file
  - aio_runtime_write_file
  - aio_runtime_execute_code
extraction_schema:
  answer: dom_first_answer_extract
  references: dom_or_empty_reference_list
known_blockers:
  - login_required
  - captcha_required
  - element_not_found
  - ui_drift
platform_guardrails:
  - re-perceive_after_major_interaction
```

### 成功标准

1. 聊天主界面已进入
2. 登录或协议弹层不再阻塞
3. 输入框可用
4. 回答区域出现有效文本

---

## 7. Yuanbao

```yaml
platform_id: yuanbao
display_name: 元宝
entry_urls:
  - https://yuanbao.tencent.com/
allowed_tools:
  - aio_browser_execute_action
  - aio_browser_take_screenshot
  - aio_browser_request_takeover
  - aio_runtime_read_file
  - aio_runtime_write_file
  - aio_runtime_execute_code
extraction_schema:
  answer: dom_answer_extract
  references: normalized_reference_list
known_blockers:
  - login_required
  - captcha_required
  - element_not_found
  - ui_drift
platform_guardrails:
  - verify_chat_ready_before_submit
```

### 成功标准

1. 登录完成或输入区已恢复
2. 页面没有阻塞 modal
3. 回答容器出现
4. 能抽出非空回答

---

## 8. Kimi

```yaml
platform_id: kimi
display_name: Kimi
entry_urls:
  - https://kimi.moonshot.cn/
allowed_tools:
  - aio_browser_execute_action
  - aio_browser_take_screenshot
  - aio_browser_request_takeover
  - aio_runtime_read_file
  - aio_runtime_write_file
  - aio_runtime_execute_code
extraction_schema:
  answer: stream_completion_extract
  references: normalized_reference_list_or_empty
known_blockers:
  - login_required
  - captcha_required
  - element_not_found
  - ui_drift
platform_guardrails:
  - wait_until_stream_completed_before_extract
```

### 成功标准

1. 登录态有效
2. 输入框恢复可用
3. 流式回答完成或进入稳定状态
4. 能抽出最终回答

---

## 9. 统一 blocker 分类

四个平台都只能输出共享合同里的 blocker：

1. `login_required`
2. `captcha_required`
3. `ui_drift`
4. `state_invalid`
5. `navigation_failed`
6. `element_not_found`
7. `proxy_or_region_blocked`
8. `runtime_unavailable`

平台 handler 不允许发明私有 blocker 词。

### 9.1 blocker 处置分层

`known_blockers` 只是分类词，不等于都要人工接管：

1. `auto_recoverable`
   - `ui_drift`
   - `state_invalid`
   - `navigation_failed`
   - `element_not_found`
2. `human_takeover_required`
   - `login_required`
   - `captcha_required`
3. `terminal_or_platform_risk`
   - `proxy_or_region_blocked`
   - `runtime_unavailable`

实际处置权在 `AIO Answer Fetch Tool` 的 Browser Agent / BlockerPolicy，而不是前端，也不是每个平台私有 handler。

---

## 10. 实施路径

1. 四个平台都统一走 `aio_answer_fetch` job
2. 每个平台都是一个 `PlatformFetchJob`
3. 生产目标是 AIO Runtime 内部运行 Playwright executor；当前后端 `connect_over_cdp` 只能作为过渡或探针路径
4. 每个平台只保留最少量 detection / extraction 差异
5. 把 readiness probe 收口成每个平台的统一接口：
   - `probe_login_ready`
   - `probe_modal_cleared`
   - `probe_answer_ready`
6. 把 extraction contract 收口成：
   - `extract_answer_payload`
   - `extract_reference_payload`
7. 把接管合同收口成：
   - `takeover_required.surface_url`
   - `takeover_required.platform`
   - `takeover_required.blocker_code`
   - `resume_after_takeover_probe`

---

## 11. 非目标

本设计不处理：

1. follow-up 路由
2. orchestrator prompt
3. A4 policy
4. 前端云电脑样式
5. 本地 Playwright 后端的长期生产化

---

## 12. 下一步

1. 按本合同回改四个平台 handler 的接口形状
2. 让 `nodes_a4.py` 只依赖统一 AIO 执行接口
3. 将旧的 “Skill Contract” 命名逐步迁移为 `Platform Execution Contract`，避免误解成 public skill
