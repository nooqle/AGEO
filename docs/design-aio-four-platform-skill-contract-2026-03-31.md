# Specta AIO 四平台执行合同设计

> 日期：2026-03-31
> 状态：Draft
> 目标：为 DeepSeek、Doubao、Yuanbao、Kimi 定义统一的 AIO 执行合同，只保留平台差异，不再把平台执行逻辑散落成互不一致的半脚本 handler。

---

## 1. 一句话结论

四个平台都必须复用同一条 AIO 执行骨架：

1. `runtime acquisition`
2. `page/context lifecycle`
3. `login/modal handoff`
4. `readiness probe`
5. `extraction completion`

平台差异只允许留在：

1. `login detection`
2. `modal detection`
3. `success criteria`
4. `extraction schema`
5. `known_blockers`
6. `platform_guardrails`

本设计中的共享状态词以
[design-aio-runtime-contracts-2026-04-01.md](/D:/AGEO-worktrees/browser-operator-design/docs/design-aio-runtime-contracts-2026-04-01.md)
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

1. Skill Contract 只定义 `allowed_tools / extraction_schema / known_blockers / platform_guardrails`
2. `blocker_code -> policy_decision` 不在本设计里定义
3. follow-up 路由不在本设计里定义

---

## 3. 统一骨架

四个平台都必须服从这个最小阶段集合：

1. `ensure_runtime`
2. `open_entry`
3. `restore_profile_state`
4. `check_login_ready`
5. `prepare_chat_surface`
6. `submit_question`
7. `wait_answer_progress`
8. `wait_answer_complete`
9. `extract_answer`
10. `extract_references`
11. `save_profile_state`

### 3.1 共享 handler 原语

四个平台的 browser handler 必须复用同一组共享原语，不再各自维护半套登录/弹窗/提取流程：

1. `prepare_takeover_surface`
2. `prepare_user_action_request`
3. `wait_for_user_action_completion`
4. `run_login_takeover_gate`
5. `run_modal_takeover_gate`
6. `build_success_result`
7. `persist_extraction_artifact`

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

以下内容不属于 Skill Contract：

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

---

## 10. 实施路径

1. 四个平台都统一走 `AioConnectedBrowserClient + AioSandboxBackend`
2. 每个平台只保留最少量 detection / extraction 差异
3. 把 readiness probe 收口成每个平台的统一接口：
   - `probe_login_ready`
   - `probe_modal_cleared`
   - `probe_answer_ready`
4. 把 extraction contract 收口成：
   - `extract_answer_payload`
   - `extract_reference_payload`

---

## 11. 非目标

本设计不处理：

1. follow-up 路由
2. orchestrator prompt
3. A4 policy
4. 本地 Playwright 后端

---

## 12. 下一步

1. 按本合同回改四个平台 handler 的接口形状
2. 让 `nodes_a4.py` 只依赖统一 AIO 执行接口
