# AIO Answer Fetch Tool 生产级架构设计

> 日期：2026-04-12
> 状态：Draft v2
> 范围：Fetch Answer Agent、AIO Tool、四平台 Playwright 抓取、VNC 人工接管、用户级登录态、Artifact 写入。

---

## 一句话结论

AIO 对 Specta 来说不是一个前端浏览器交付物，也不是一个临时 CDP 连接能力；它应该是 **Fetch Answer Agent 可调用的浏览器执行 Tool / Runtime Capability**。

正确关系是：

```text
Fetch Answer Agent
  -> 调用 AIO Answer Fetch Tool
  -> AIO Tool 驱动浏览器执行四个平台抓取
  -> AIO Tool 返回结构化 events / result packet
  -> Fetch Answer Agent 校验、归一化、写入 Artifacts
  -> 下游进入 Analytics / Report
```

用户看到的 VNC / 云电脑只是 **人工接管 surface**。它不应该负责决定打开哪个平台，也不应该负责临时初始化抓取环境。用户点击“打开云电脑”时，页面应该已经被 AIO job 跑到需要人工处理的位置。

---

## 核心原则

## 1. Agent 应该操作浏览器，但通过 Tool 操作

“Agent 操作浏览器”是正确方向，但工程实现不能变成前端或普通业务代码直接操作 tab、URL、CDP。

推荐边界：

```text
Agent 决策：
  - 是否执行完整采集
  - 四个平台是否继续、跳过、重试
  - 如何解释 AIO 返回的 blocker / result
  - 如何写入 Artifact 并推进 workflow

AIO Tool 执行：
  - 打开平台页面
  - 输入问题
  - 等待回答
  - 提取答案和引用
  - 自动关闭普通弹窗
  - 遇到登录/验证码时暂停并发出 takeover_required
  - 用户完成后 resume_probe
  - 保存登录态
```

因此更准确的描述是：

```text
Agent 通过 AIO Tool 操作浏览器。
```

而不是：

```text
前端打开浏览器后再让用户或前端决定怎么操作。
```

## 2. 四个平台是一个整体，不允许局部特判

AIO Answer Fetch Tool 的默认完整采集对象固定是四个平台：

```text
doubao
yuanbao
kimi
deepseek
```

所有设计都必须同时覆盖四个平台：

1. 四个平台并行抓取。
2. 四个平台独立 AuthContext。
3. 四个平台独立 RunContext。
4. 四个平台独立状态机。
5. 四个平台都能进入 takeover 队列。
6. 任一平台失败不应直接破坏其他平台。

禁止只围绕 DeepSeek / Kimi 做局部逻辑，否则后续一定会出现平台串台、重复提示、登录态不保存、Artifact 缺口等问题。

## 3. 普通阻塞由 Agent/AIO 自动处理，人工接管是最后手段

不要把所有页面异常都交给用户。

AIO Tool 应先自动处理：

```text
广告弹窗
Cookie 弹窗
新手引导层
下载 App 提示
普通遮罩
输入框失焦
about:blank 恢复
页面白屏刷新
错误子页面回到 chat 页
```

只有这些情况才请求人工接管：

```text
账号登录
二维码扫码
手机验证码
图形验证码
人机验证
账号安全确认
平台风控确认
需要用户选择账号或授权
```

---

## 推荐生产架构

## 1. 当前过渡实现

当前实现更接近：

```text
Specta Backend Python
  -> Patchright / Playwright connect_over_cdp(cdp_url)
  -> 远程控制 AIO Docker 里的 Chromium
  -> 结果回到 Backend
```

这个方案可以验证 AIO CDP 能力，也可以作为短期 fallback，但不应该作为长期生产主路径。

风险：

1. 后端长期持有跨机器 CDP 连接，容易遇到 `Target closed`、网络抖动、页面失联。
2. 浏览器执行生命周期和业务 workflow 混在后端进程里。
3. 多 worker 部署时，接管锁、浏览器 context 和任务状态容易跨进程不一致。
4. VNC 可视状态和后端 page/context 状态容易不同步。

## 2. 推荐生产实现

生产级应该把 Playwright executor 下沉到 AIO runtime 内部：

```text
Specta Backend / Fetch Answer Agent
  -> AIO Answer Fetch Tool API

AIO Runtime
  -> aio-worker: Playwright executor / browser agent
  -> browser: Chromium + CDP + VNC/noVNC
  -> shared volume:
       /data/auth
       /data/runs
       /data/traces
```

推荐部署形态：

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
    auth state
    run output
    screenshots / traces
```

这样后端只 dispatch job 和消费结果，不再直接长期控制 CDP。

---

## AIO Tool Contract

## 1. 创建完整采集任务

```http
POST /aio/jobs/answer-fetch
```

请求参数：

```json
{
  "job_id": "answer_fetch_job_123",
  "session_id": "specta_session_1",
  "task_id": "task_789",
  "entity_id": "entity_456",
  "specta_user_id": "user_123",
  "brand": "雅姿",
  "questions": [
    {
      "question_id": "q1",
      "text": "30岁刚开始抗老，有什么推荐？"
    }
  ],
  "platforms": ["doubao", "yuanbao", "kimi", "deepseek"],
  "execution_mode": "full_browser",
  "auth_scope": "prod/user_123",
  "run_scope": "entity_456/task_789"
}
```

原则：

1. `platforms` 默认必须是四个平台。
2. 后端可以显式传平台子集，但完整采集模式必须覆盖四个平台。
3. `specta_user_id` 用于登录态隔离。
4. `entity_id/task_id` 用于 run result 隔离。

## 2. Job Event

AIO Tool 应返回结构化事件流：

```json
{
  "event": "platform_started",
  "job_id": "answer_fetch_job_123",
  "platform": "doubao",
  "status": "running"
}
```

人工接管事件：

```json
{
  "event": "takeover_required",
  "job_id": "answer_fetch_job_123",
  "platform": "yuanbao",
  "takeover_id": "takeover_456",
  "reason": "login_required",
  "surface_url": "https://aio-runtime/takeovers/takeover_456",
  "target_url": "https://yuanbao.tencent.com/",
  "current_page_url": "https://yuanbao.tencent.com/chat/...",
  "auth_context_key": "prod/user_123/yuanbao",
  "run_context_key": "entity_456/task_789/yuanbao",
  "message": "元宝需要登录"
}
```

平台结果事件：

```json
{
  "event": "platform_result",
  "job_id": "answer_fetch_job_123",
  "platform": "kimi",
  "status": "succeeded",
  "result_ref": "/data/runs/entity_456/task_789/kimi/result.json"
}
```

## 3. 完整 Result Packet

```json
{
  "job_id": "answer_fetch_job_123",
  "status": "completed",
  "platform_results": {
    "doubao": {
      "status": "succeeded",
      "answer": "...",
      "citations": [],
      "duration_ms": 12000
    },
    "yuanbao": {
      "status": "succeeded",
      "answer": "...",
      "citations": [],
      "duration_ms": 15000
    },
    "kimi": {
      "status": "skipped",
      "error_code": "user_skipped"
    },
    "deepseek": {
      "status": "failed",
      "error_code": "rate_limited"
    }
  }
}
```

Fetch Answer Agent 收到这个 packet 后再做：

```text
validate
normalize
persist artifact
continue analytics
```

---

## 四平台 PlatformFetchJob

每个平台都必须有独立 sub-job：

```json
{
  "platform": "doubao",
  "status": "pending",
  "auth_context_key": "prod/user_123/doubao",
  "run_context_key": "entity_456/task_789/doubao",
  "browser_context_id": "ctx_doubao",
  "takeover_id": null
}
```

完整状态表：

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

状态规则：

1. `pending -> running`
   - 平台开始 Playwright 抓取。
2. `running -> auto_recovering`
   - 普通弹窗、白屏、页面轻量异常，AIO 自动处理。
3. `auto_recovering -> running`
   - 自动处理成功，继续抓取。
4. `running -> blocked_waiting_takeover`
   - 登录、验证码、人机验证等需要用户身份动作。
5. `blocked_waiting_takeover -> takeover_active`
   - 该平台进入当前接管位。
6. `takeover_active -> resuming`
   - 用户点击“我已完成”。
7. `resuming -> running`
   - resume_probe 通过，保存登录态，继续抓取。
8. `resuming -> blocked_waiting_takeover`
   - 用户操作还没完成，但可以继续让用户处理。
9. `takeover_active -> skipped`
   - 用户跳过该平台。
10. `running/auto_recovering/resuming -> failed`
   - 不可恢复错误。

---

## BlockerPolicy

AIO Tool 必须先识别阻塞类型，再决定自动处理还是交给用户。

```json
{
  "platform": "deepseek",
  "blocker_type": "dismissible_modal",
  "confidence": 0.86,
  "auto_action_allowed": true,
  "auto_action_taken": "clicked_close",
  "requires_human": false,
  "evidence": {
    "text": "Download app",
    "selector": "button.close",
    "screenshot_ref": "/data/traces/job_123/deepseek/modal.png"
  }
}
```

自动处理类型：

```text
dismissible_modal
cookie_banner
onboarding
download_app_prompt
page_blank
page_error
input_focus_lost
wrong_subpage
```

必须人工处理类型：

```text
login_required
captcha_required
phone_verify_required
qr_scan_required
human_verification_required
account_security_required
oauth_authorization_required
```

不可恢复类型：

```text
rate_limited
platform_unavailable
policy_denied
unsupported_flow
```

原则：

1. 普通弹窗不提示用户。
2. 自动处理必须记录 evidence。
3. 同一 blocker 自动处理失败超过阈值后再升级。
4. 只有身份、安全、验证码类动作交给用户。
5. 用户跳过平台后，平台必须进入 `skipped`，不能继续重复提示。

---

## Human Takeover

## 1. 接管 surface 必须提前准备好

错误模型：

```text
用户点击打开浏览器
  -> 前端请求创建云电脑
  -> 云电脑再开始导航
  -> 用户等待 loading / about:blank
```

正确模型：

```text
AIO Playwright 已经跑到阻塞页面
  -> freeze 当前 platform page
  -> 生成 takeover surface_url
  -> 返回 takeover_required event
  -> Agent 提示用户
  -> 用户点击打开
  -> 前端 attach 已存在 surface_url
  -> 用户直接看到当前阻塞页面
```

前端职责只有：

```text
展示提示
打开 surface_url
发送 completed / skip / cancel
渲染当前状态
```

前端不应该：

```text
决定平台 URL
创建浏览器
切换平台 tab
判断登录是否成功
保存登录态
```

## 2. 四平台 takeover 队列

自动抓取可以四个平台并行，人工接管必须串行：

```text
takeover_queue(job_id, specta_user_id):
  concurrency = 1
```

例子：

```text
doubao   running
yuanbao  blocked_waiting_takeover
kimi     blocked_waiting_takeover
deepseek running

当前展示：
  yuanbao takeover_active

队列等待：
  kimi
```

这样可以避免：

1. 一次弹出多个登录提示。
2. 用户正在操作元宝时被 Kimi 抢焦点。
3. 云电脑里自动打开一堆混合平台 tab。
4. 用户跳过一个平台后仍然重复提示。

## 3. 完成后的 resume

用户点击“我已完成”后，不应该直接相信完成。

正确流程：

```text
Backend -> AIO resolve_takeover(takeover_id, completed)
AIO -> sync current page
AIO -> run resume_probe(platform)
if ready:
  save storage_state to AuthContext
  mark platform resumed
  continue Playwright fetch
else:
  return takeover_required again with clearer reason
```

resume_probe 示例：

```text
doubao:
  check chat input exists
  check user avatar or logged-in menu exists

yuanbao:
  check chat input exists
  check login button gone

kimi:
  check chat composer exists
  check sign-in route gone

deepseek:
  check chat textarea exists
  check sign_in route gone
```

---

## Context 设计

## 1. AuthContext

登录态必须绑定 Specta 用户，不绑定品牌任务。

```text
auth_context_key = "{env}/{specta_user_id}/{platform}"
```

路径：

```text
/data/auth/{env}/{specta_user_id}/doubao/browser_state.json
/data/auth/{env}/{specta_user_id}/yuanbao/browser_state.json
/data/auth/{env}/{specta_user_id}/kimi/browser_state.json
/data/auth/{env}/{specta_user_id}/deepseek/browser_state.json
```

规则：

1. 同一 Specta 用户跨品牌、跨 session 复用平台登录态。
2. 不同 Specta 用户不能复用登录态。
3. 用户明确重新绑定时，清理该用户该平台的 auth state。
4. ready probe 通过后才保存 auth state。
5. auth state 不写入 run artifact。

## 2. RunContext

采集结果必须绑定任务。

```text
run_context_key = "{entity_id}/{task_id}/{platform}"
```

路径：

```text
/data/runs/{entity_id}/{task_id}/doubao/result.json
/data/runs/{entity_id}/{task_id}/yuanbao/result.json
/data/runs/{entity_id}/{task_id}/kimi/result.json
/data/runs/{entity_id}/{task_id}/deepseek/result.json
```

规则：

1. 每个平台独立 result。
2. 单个平台失败不覆盖其他平台结果。
3. Artifact 写入读取的是 result packet，不直接读浏览器状态。

## 3. BrowserContext

短期推荐：

```text
一个 AIO runtime
  -> 一个 Chromium
  -> 四个 BrowserContext
  -> 四个平台并行 Playwright job
```

如果 VNC/Canvas 下仍然出现焦点和 tab 干扰，再升级：

```text
一个 AIO runtime
  -> 四个 browser process
  -> 每个平台独立 user-data-dir
```

再往后才考虑：

```text
四个 sandbox lease
```

不要一开始就四个 sandbox，因为成本和调度复杂度更高。

---

## Playwright 与 MCP 的位置

## Playwright

Playwright 是 AIO Tool 的主执行能力。

生产级建议：

```text
Playwright executor 跑在 AIO runtime 内部
Chromium/CDP 也在 AIO runtime 内部
Specta Backend 通过 AIO Job API 控制执行
```

过渡期可以保留：

```text
Specta Backend Playwright -> connect_over_cdp(AIO cdp_url)
```

但它只能作为 fallback / probe / 临时实现。

## MCP

MCP 可以作为浏览器能力的另一种 adapter，但不建议直接作为 A4 主调度协议。

适合：

```text
通用 Browser Agent
临时网页查询
非固定平台的探索任务
调试工具
```

不适合直接替代：

```text
四平台 answer fetch job contract
AuthContext / RunContext 管理
takeover queue
resume_probe
Artifact 写入合同
```

如果未来需要多浏览器物理隔离，可以考虑：

```text
platform -> dedicated browser process
platform -> dedicated MCP server
platform -> dedicated profile
```

但对 Agent 暴露的接口仍应该是 AIO Tool Contract，而不是把 MCP 的 tab/page 细节泄漏给业务 Agent。

---

## Fetch Answer Agent 职责

Fetch Answer Agent 不应该知道某个平台具体 DOM selector，也不应该自己维护 CDP page。

它应该负责：

1. 决定是否调用完整采集。
2. 调用 AIO Answer Fetch Tool。
3. 订阅四个平台事件。
4. 将 `takeover_required` 翻译成用户可理解提示。
5. 将用户 `completed/skip/cancel` 回传给 AIO。
6. 接收 result packet。
7. 校验字段、归一化、写入 Artifacts。
8. 决定是否进入 A5 Analytics。

它不应该负责：

1. 直接操作前端 VNC。
2. 直接切浏览器 tab。
3. 硬编码平台 DOM 选择器。
4. 把普通广告弹窗都交给用户。
5. 把登录态存在任务产物里。

---

## 前端职责

前端是接管 surface 的展示者，不是浏览器执行器。

正确职责：

```text
显示四平台整体进度
显示当前 takeover 卡片
点击打开已准备好的 surface_url
用户完成后发送 completed
用户跳过后发送 skip
显示平台状态和结果
```

错误职责：

```text
创建云电脑
决定平台 URL
导航浏览器
自动切换 tab
判断是否登录成功
保存登录态
```

---

## 事件与状态示例

完整采集开始：

```text
job_started
platform_started doubao
platform_started yuanbao
platform_started kimi
platform_started deepseek
```

普通弹窗自动处理：

```text
blocker_detected platform=doubao blocker_type=dismissible_modal
auto_action_taken platform=doubao action=clicked_close
platform_resumed platform=doubao
```

人工接管：

```text
blocker_detected platform=yuanbao blocker_type=login_required
takeover_required platform=yuanbao takeover_id=...
takeover_active platform=yuanbao
```

用户完成：

```text
takeover_completed platform=yuanbao
resume_probe_started platform=yuanbao
resume_probe_passed platform=yuanbao
auth_context_saved platform=yuanbao
platform_resumed platform=yuanbao
```

用户跳过：

```text
takeover_skipped platform=kimi
platform_skipped platform=kimi
```

最终：

```text
platform_result doubao succeeded
platform_result yuanbao succeeded
platform_result kimi skipped
platform_result deepseek succeeded
job_completed partial_success
```

---

## 验收标准

## 功能验收

1. 完整采集默认覆盖豆包、元宝、Kimi、DeepSeek 四个平台。
2. 四个平台能并行启动抓取。
3. 普通弹窗由 AIO 自动处理，不提示用户。
4. 登录、验证码、人机验证才进入人工接管。
5. 用户点击打开云电脑时，页面已经停在对应平台的阻塞现场。
6. 点击元宝卡片只打开元宝，不打开其他平台。
7. 用户完成后 AIO 执行 resume_probe，通过才保存登录态。
8. 同一 Specta 用户下次不重复登录同一平台。
9. 换 Specta 用户不能复用前一个用户的登录态。
10. 用户跳过某平台后，该平台进入 skipped，不再反复提示。

## 架构验收

1. Fetch Answer Agent 只调用 AIO Tool Contract，不直接维护 CDP page。
2. AIO Tool 负责 Playwright 执行、BlockerPolicy、resume_probe。
3. AuthContext 与 RunContext 分离。
4. Artifact 写入只消费结构化 result packet。
5. 前端只 attach 已存在 takeover surface，不创建抓取环境。
6. 四平台状态机统一，不允许局部平台特判破坏整体模型。

## 日志验收

每个平台必须有结构化日志：

```text
platform_job_started platform=...
auth_context_loaded user_id=... platform=...
browser_context_created platform=...
blocker_detected platform=... blocker_type=...
auto_action_taken platform=... action=...
takeover_enqueued platform=...
takeover_active platform=...
takeover_resolved platform=...
resume_probe_passed platform=...
auth_context_saved user_id=... platform=...
platform_result_persisted platform=...
```

---

## 实施路线

## Phase 0: 设计与 Probe

目标：

1. 固定本设计文档。
2. 验证 AIO runtime 是否支持四 context 并行。
3. 验证 storage_state 隔离。
4. 明确当前后端 CDP 实现只是过渡层。

已完成的 probe 结果：

```text
ok=true
connect_over_cdp=true
parallel_context_navigation=true
platform_count=4
max_parallel=4
storage_state_isolated=true
```

## Phase 1: AIO Tool Contract

目标：

1. 定义 `answer_fetch_job` API。
2. 定义 `platform_started / blocker_detected / takeover_required / platform_result / job_completed` events。
3. 定义 result packet schema。
4. 定义 takeover resume/skip/cancel API。

## Phase 2: AIO Worker 内置 Playwright

目标：

1. 在 AIO runtime 内增加 Playwright executor。
2. executor 连接 runtime 内部 Chromium/CDP。
3. 四个平台并行 job 在 AIO 内执行。
4. 后端不再长期持有 CDP 连接。

## Phase 3: BlockerPolicy 与 ResumeProbe

目标：

1. 自动处理普通弹窗。
2. 身份/安全阻塞才发 takeover。
3. resume_probe 平台化。
4. 登录态保存前必须 probe 通过。

## Phase 4: 后端 A4 Adapter

目标：

1. A4 从直接 Playwright 改为调用 AIO Tool。
2. 保留当前 CDP 连接实现作为 fallback。
3. A4 只消费 result packet 并写 Artifact。
4. 失败/跳过按平台结构化返回。

## Phase 5: 前端接管体验

目标：

1. Chat 卡片按平台展示 takeover。
2. 打开按钮 attach 已准备好的 surface_url。
3. “我已完成 / 跳过平台 / 重试打开”在 Chat 卡片里。
4. 云电脑不再作为普通 Canvas artifact tab 混入结果区。

---

## 非目标

本方案不做：

1. 把普通弹窗都交给用户。
2. 让前端创建或导航云电脑。
3. 只为 DeepSeek/Kimi 写局部逻辑。
4. 把 A4 整个塞进 sandbox，导致业务编排和执行器混杂。
5. 让 Agent 直接感知 MCP tab/page 细节。
6. 把登录态写进任务 artifact。

---

## 最终判断

生产级架构应该是：

```text
Agent 调用 AIO Tool。
AIO Tool 内部用 Playwright 操作四个平台。
AIO 自动处理普通页面阻塞。
只有身份/安全类动作交给用户接管。
接管 surface 是已经准备好的现场，不是点击后临时启动。
登录态绑定 Specta 用户和平台。
结果以 JSON packet 返回 Agent，再写 Artifact。
```

这是后续实现的基准线。任何偏离这条线的局部补丁，都应该先回到这个文档检查是否破坏了 Agent / Tool / Runtime / Frontend 的边界。
