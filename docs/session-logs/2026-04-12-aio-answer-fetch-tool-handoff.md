# 2026-04-12 AIO Answer Fetch Tool Handoff

## Context Scope

本记录覆盖 2026-04-12 这轮 AIO Answer Fetch Tool 迭代：从架构讨论、工具门面设计、过渡实现落地，到提交 `30abb2a feat(aio): add answer fetch tool facade`。

当前实现 worktree：

```text
D:\AGEO-worktrees\aio-runtime-isolation
```

当前分支：

```text
codex/aio-runtime-isolation
```

当前已确认的关键提交：

```text
30abb2a feat(aio): add answer fetch tool facade
8833a4a docs(aio): add answer fetch handoff note
a910e97 feat(aio): attach platform result packets
```

## User Goal & Constraints

目标是把 AIO 从临时浏览器连接能力归位成 Fetch Answer Agent 可调用的稳定工具能力：

```text
Fetch Answer Agent
  -> aio_answer_fetch tool
  -> AIO / Playwright browser execution
  -> takeover_required when human action is needed
  -> result packet
  -> Artifact / Analytics
```

关键约束：

1. Agent 应通过 Tool 操作浏览器，不应由前端临时驱动云电脑。
2. AIO Tool 默认覆盖四个平台：豆包、元宝、Kimi、DeepSeek。
3. `hunyuan` 只允许作为内部 legacy executor alias，对外必须显示 `yuanbao / 元宝`。
4. 普通弹窗、广告、Cookie、新手引导、页面恢复等应由 AIO / Browser Agent 自动处理。
5. 登录、验证码、人机验证、账号安全确认才进入人工接管。
6. VNC / 云电脑只是人工接管 surface；理想状态是 AIO job 已经跑到阻塞现场，前端只 attach `surface_url`。
7. 登录态绑定 `env + specta_user_id + platform`。
8. 抓取结果绑定 `entity_id + task_id + platform`。
9. 当前 `connect_over_cdp` 只能作为过渡 / fallback；生产级方向是 Playwright executor 下沉到 AIO Runtime 内。

## Key Decisions

1. 本轮先做 Tool Facade，不直接迁移到 AIO Runtime 内部 worker。
2. `aio_answer_fetch` 是内部 runtime tool，不是新的 public skill，也不是前端 artifact。
3. A4 仍保留 LangGraph executor，但 AIO 相关创建和并行调度收敛到 `AioAnswerFetchTool`。
4. 四平台完整采集应按平台级 job 并行；人工 takeover 对用户串行展示，避免焦点和 VNC 互抢。
5. `hunyuan` 暂时保留在旧 API client / executor 层，业务展示与新契约统一为 `yuanbao / 元宝`。
6. Redis 不是这轮核心阻塞；若后续多 worker 部署，再迁移 browser action request / takeover resolve 状态。

## Actions Taken

新增核心工具门面：

```text
aeo-platform/backend/app/tools/a4_fetch_agent.py
```

已实现：

1. `AioAnswerFetchTool`
2. `AioAnswerFetchRequest`
3. `AioPlatformFetchJob`
4. `AioPlatformFetchResult`
5. `AioTakeoverRequiredPacket`
6. `AioAuthContext`
7. `AioRunContext`
8. public platform normalize：`doubao / yuanbao / kimi / deepseek`
9. legacy alias：`hunyuan -> yuanbao`

更新 A4：

```text
aeo-platform/backend/app/workflow/nodes_a4.py
```

已完成：

1. A4 通过 `AioAnswerFetchTool` 创建 browser client / handler。
2. A4 平台过滤支持字符串平台名，不再把 `"yuanbao"` 按字符拆开。
3. 全浏览器模式从顺序执行恢复为受 `AIO_MAX_PARALLEL_BROWSER_SESSIONS` 控制的并行执行。
4. 用户文案去掉 `Phase 1`，预计时间统一为 `8-15 分钟`。
5. 快速模式文案使用“元宝”，不暴露“腾讯混元”。

更新 AIO runtime context：

```text
aeo-platform/backend/app/services/aio_runtime_contracts.py
aeo-platform/backend/app/services/aio_session_manager.py
aeo-platform/backend/app/core/fetchers/browser/aio_connected_client.py
```

已完成：

1. 拆分 AuthContext 与 RunContext 路径。
2. auth path: `/data/auth/{env}/{specta_user_id}/{platform}/profile/...`
3. run path: `/data/runs/{entity_id}/{task_id}/{platform}/run/...`
4. 保留 legacy storage state fallback，便于从旧路径迁移。

更新 takeover / 前端：

```text
aeo-platform/backend/app/workflow/browser_action_contract.py
aeo-platform/backend/app/workflow/browser_action_runtime.py
aeo-platform/backend/app/api/v1/aio.py
frontend/src/components/canvas/contents/BrowserTakeoverContent.tsx
frontend/src/components/chat/BrowserActionBanner.tsx
frontend/src/components/chat/ChatPanel.tsx
frontend/src/config/platforms.ts
frontend/src/lib/canvasExportShared.ts
frontend/src/types/agent.ts
```

已完成：

1. 人工 takeover 增加 session/run 级 handoff slot，避免多个用户接管提示同时抢 UI。
2. 停止任务时释放 handoff slot。
3. 停止任务时前端清理 browser states、takeover store 和 browser workspace。
4. noVNC 代理注入 CSS 隐藏原生控制栏。
5. VNC iframe 黑屏加载改为白底 loading 和延迟 reveal。
6. 前端平台类型和标签补齐 `yuanbao`。
7. A5 postprocess 中 `hunyuan` 展示改为“元宝”。

新增 / 更新设计文档：

```text
docs/architecture-aio-answer-fetch-tool-runtime-2026-04-12.md
docs/design-aio-parallel-playwright-context-2026-04-11.md
docs/design-aio-browser-runtime-boundary-2026-04-09.md
docs/design-aio-tool-schema-2026-03-31.md
docs/design-a4-aio-routing-2026-03-31.md
docs/design-aio-four-platform-skill-contract-2026-03-31.md
docs/design-harness-layering-agent-skill-tool-2026-04-01.md
```

验证结果：

```text
python -m compileall app\tools\a4_fetch_agent.py app\workflow\nodes_a4.py app\workflow\a5\postprocess.py
=> passed

pytest tests\test_harness_refactor_foundations.py -q
=> 101 passed

npx eslint src/components/chat/BrowserActionBanner.tsx src/components/chat/ChatPanel.tsx src/components/canvas/contents/BrowserTakeoverContent.tsx src/types/agent.ts src/config/platforms.ts src/lib/canvasExportShared.ts
=> passed

npx tsc --noEmit
=> passed

git diff --check
=> passed, only CRLF warnings

Select-String affected files -Pattern "\?\?\?"
=> no matches
```

P1a 增量（与 `feat(aio): attach platform result packets` 同一提交落地）：

```text
aeo-platform/backend/app/tools/a4_fetch_agent.py
aeo-platform/backend/app/workflow/nodes_a4.py
aeo-platform/backend/tests/test_harness_refactor_foundations.py
```

已完成：

1. 给 legacy A4 `platform_results` 附加 `aio_packet`，保持旧结构不变。
2. `aio_packet` 支持 `result / skipped / takeover_required / failed` 状态分类。
3. `hunyuan` legacy 平台在 packet 中归一为 `yuanbao`。
4. `takeover_required` packet 包含 `takeover_id / platform / reason_code / surface_url / target_url / expires_at / resume_policy`。
5. 每个 question-level `fetch_results` 增加 `aio_platform_packets` 汇总，便于后续 A4/A5 逐步切到新契约。
6. 平台级 provenance 写入 `source / source_type / platform_legacy_id / duration / auth_context / run_context`。
7. 新增 result、skip 终态、takeover_required packet 的单测。

P1b / P1c 当前未提交增量：

```text
aeo-platform/backend/app/workflow/nodes_a4.py
aeo-platform/backend/app/tools/a4_fetch_agent.py
aeo-platform/backend/app/api/v1/aio.py
frontend/src/components/chat/ChatPanel.tsx
aeo-platform/backend/tests/test_harness_refactor_foundations.py
```

已完成：

1. A4 下游汇总逻辑优先读取 `aio_platform_packets`，不再以 legacy `platform_results.success` 作为唯一事实来源。
2. 新增 `_build_aio_packet_fetch_summary()`，统一生成 `successful_fetches / successful_platforms / platform_fetch_stats / platform_statuses / total_answers / brand_mentions`。
3. 浏览器阶段 question-level 成功计数和阶段汇总切到 packet-first，避免 packet 与 legacy bool 打架。
4. `skip / takeover_required / failed / result` 现在都能进入 A4 的阶段结果与降级判断。
5. 登录接管恢复成功后，browser result 会写入 `auth_state_updated=true`。
6. 登录恢复失败或用户跳过时，legacy result 与 `aio_packet` 都会附加 `reason_code / target_url / final_url / probe_result / request_id`。
7. noVNC 隐藏 CSS 进一步收紧，补充隐藏 `settings / disconnect / panel / expander / noVNC_button` 等控制项。
8. Chat 遇到新的接管消息时增加双 `requestAnimationFrame` + `setTimeout` fallback 自动滚动，降低用户看不到当前接管卡片的概率。

## Current Known State

已提交：

```text
30abb2a feat(aio): add answer fetch tool facade
8833a4a docs(aio): add answer fetch handoff note
```

P1a 当前验证：

```text
python -m compileall app\tools\a4_fetch_agent.py app\workflow\nodes_a4.py
=> passed

pytest tests\test_harness_refactor_foundations.py -q
=> 104 passed

python -m ruff check app\tools\a4_fetch_agent.py app\workflow\nodes_a4.py tests\test_harness_refactor_foundations.py
=> passed

Select-String affected files -Pattern "\?\?\?"
=> no matches
```

P1b / P1c 当前验证：

```text
python -m compileall app\tools\a4_fetch_agent.py app\workflow\nodes_a4.py app\api\v1\aio.py
=> passed

pytest tests\test_harness_refactor_foundations.py -q
=> 107 passed

python -m ruff check app\tools\a4_fetch_agent.py app\workflow\nodes_a4.py app\api\v1\aio.py tests\test_harness_refactor_foundations.py
=> passed

npx eslint src/components/chat/ChatPanel.tsx
=> passed

npx tsc --noEmit
=> passed

Select-String affected files -Pattern "\?\?\?"
=> no matches

git diff --check
=> only CRLF warnings
```

Browser Agent seam 当前验证：

```text
python -m compileall app\core\fetchers\browser\base_handler.py app\core\fetchers\browser\deepseek_handler.py app\core\fetchers\browser\doubao_handler.py app\core\fetchers\browser\kimi_handler.py app\core\fetchers\browser\yuanbao_handler.py app\core\fetchers\browser\browser_agent_contract.py app\core\fetchers\browser\browser_agent_loop.py app\core\fetchers\browser\browser_agent_policy.py
=> passed

$env:DEBUG='true'; $env:DEV_MODE_ENABLED='true'; python -m pytest tests\test_browser_agent_contract.py tests\test_browser_agent_policy.py tests\test_browser_agent_loop.py tests\test_browser_agent_resume_probe.py tests\test_harness_refactor_foundations.py -q
=> 123 passed

python -m ruff check app\core\fetchers\browser\base_handler.py app\core\fetchers\browser\deepseek_handler.py app\core\fetchers\browser\doubao_handler.py app\core\fetchers\browser\kimi_handler.py app\core\fetchers\browser\yuanbao_handler.py app\core\fetchers\browser\browser_agent_contract.py app\core\fetchers\browser\browser_agent_loop.py app\core\fetchers\browser\browser_agent_policy.py tests\test_browser_agent_contract.py tests\test_browser_agent_policy.py tests\test_browser_agent_loop.py tests\test_browser_agent_resume_probe.py tests\test_harness_refactor_foundations.py
=> passed

Select-String affected files -Pattern "\?\?\?"
=> no matches
```

2026-04-12 晚间补充架构决策：

```text
1. 不再接受“模型先选错工具 -> runtime 再 realign 改写回来”的 follow-up 控制方式。
2. 当前会话追问场景改走 Harness contextual tool exposure：
   - 当前会话细节追问时隐藏 knowledge_*
   - 平台/情感等明确 drill-down 场景时进一步隐藏 compare_snapshots / post_analysis_skill
   - Prompt 的“公共技能索引”与“当前回合工具面约束”也必须同步反映这套收口，不能再静态暴露已隐藏工具
3. Browser 页面理解不应继续堆在 platform handler selector 里；
   生产级方向是 AIO Tool 内部 Browser Agent loop 负责 observe / act / classify blocker。
4. Human takeover 是最后兜底，不是默认浏览器驱动方。
5. 已新增 `app/core/fetchers/browser/browser_agent_contract.py` 作为第一层代码 seam，先统一 Observation / Action / Decision / Takeover 契约，再逐步把页面理解从各平台 handler 中抽走。
6. 已新增 `app/core/fetchers/browser/browser_agent_policy.py`，并把 `BaseBrowserHandler` 接上统一 preflight：
   - 登录检查前统一先收集 observation
   - 公共 policy 优先判断空白页 / 导航错误 / 登录 / 验证 / 轻量弹窗
   - 普通弹窗先自动动作，真正需要人的 blocker 才进入 takeover
   - `Target page/context/browser has been closed` 这类 stale page 问题先在 base handler 里尝试 live-page resync
7. 已新增 `app/core/fetchers/browser/browser_agent_loop.py`，把 handler 对 policy 的直接依赖改成可替换 loop seam：
   - 当前默认是 `BrowserAgentBootstrapPolicy`
   - `collect_browser_agent_step(...)` 统一负责 `observe -> decide`
   - `BaseBrowserHandler` 不再直接绑死某个 policy 实现
8. Browser Agent loop 继续升级为“阶段上下文 + 混合执行器”：
   - 新增 `BrowserAgentLoopContext`，把 `preflight / wait_gate / resume_probe / empty_answer` 阶段信息显式带进 loop
   - 新增 `HybridBrowserAgentPolicy`
   - 新增 `LLMBrowserAgentPolicy`（默认关闭，作为后续真正 agent-driven browser policy 的运行时入口）
   - `build_default_browser_agent_policy()` 负责按配置选择默认执行器，而不是让 BaseHandler 直接假定只有 bootstrap policy
9. 四个平台在 DOM fallback / 空答案阶段也开始走公共 Browser Agent wait gate：
   - 提交后再弹登录/验证，不再只靠 Kimi 私有 late-login 检测
   - SSE 明确返回 `auth_required / verify / captcha` 时，也先尝试映射到公共 takeover
   - “未能提取到有效回答”前会先让 Browser Agent 再看一轮当前页面
10. 手动“我已完成”后的 resume probe 开始优先走共享 Browser Agent 当前页观察：
   - 新增 `BaseBrowserHandler._browser_agent_resume_probe_ready(...)`
   - `login / verify / captcha / security_confirmation / account_selection` 先用共享 observation 判断 blocker 是否已解除
   - Doubao / Yuanbao / Kimi / DeepSeek 的平台专属 readiness check 改成 fallback，不再是唯一事实来源
11. parser 错误、wait blocker、空答案兜底继续往 Base 收：
   - 新增 `BaseBrowserHandler._handle_browser_agent_parser_error(...)`
   - 新增 `BaseBrowserHandler._handle_browser_agent_wait_blocker(...)`
   - 新增 `BaseBrowserHandler._handle_browser_agent_empty_answer(...)`
   - 四个平台进一步减少对 blocker 恢复分支的直接拼接
12. 新增 `tests/test_browser_agent_resume_probe.py`，覆盖 login/modal 的共享 resume probe 行为
13. 新增 `tests/test_browser_agent_llm_policy.py`，覆盖：
   - LLM policy JSON 解析
   - bootstrap 优先、LLM 次级的 hybrid 行为
   - 默认 policy 的配置选择
```

仍有未跟踪文件：

```text
aeo-platform/backend/scripts/probe_aio_parallel_contexts.py
```

该文件是 AIO 并行 context 探测脚本，按“不要默认提交测试脚本 / 临时脚本”的偏好未纳入提交。

## Open Risks / Unknowns

1. `AioPlatformFetchResult` 已被附加到 legacy `platform_results`，但还没有完全替代 A4 内部 legacy `fetch_results/platform_results` 合并结构。
2. `takeover_required / skipped / failed / result` 已进入 packet，A4 汇总已优先使用 packet；但更深层的 browser action request/resolution 仍是底层执行机制，尚未完全抽离。
3. BlockerPolicy 还没有系统化；普通弹窗和轻量阻塞处理仍散落在各平台 handler 中。
4. 当前后端仍通过 `connect_over_cdp` 控制远端 AIO Chromium，未下沉到 AIO Runtime worker。
5. 当前 AIO 是否能稳定支持四平台多 Playwright context 并行，尚需 probe / UAT 验证。
6. 如果底层只有一个可视 browser process，VNC focus / tab 互扰仍可能存在。
7. 登录态复用闭环必须通过真实 UAT 验证：`takeover -> resume_probe -> persist auth state -> next run reuse`。
8. 真实“雅姿”四平台全浏览器 UAT 尚未完成。
9. 当前 Browser Agent 已经不再只有 bootstrap seam，而是具备“阶段上下文 + hybrid executor”骨架；但 LLM policy 默认仍关闭，避免未验证前直接进入生产路径。
10. 当前这轮 Browser Agent 还不是最终的 LLM-driven browser loop；页面理解控制权已经开始从平台 handler 收回到公共层，但平台旧逻辑还没有完全删除。
11. `network intercept -> ParsedResponse` 这一路仍然有平台 parser 差异；目前只是把其 `auth_required / verify` 结果先映射进公共 takeover，还没有完全进入统一 Browser Agent runtime。
12. 共享 resume probe 已经落地，但当前仍是“共享 observation 优先 + 平台 fallback”双轨，平台专属 probe 还没有完全删除。
13. 当前本地 worktree 和共享 env 都没有配置 `AIO_BASE_URL / AIO_ENABLED / AIO_AUTH_TOKEN`，因此真实 AIO probe / UAT 目前被运行时配置阻塞，而不是被代码测试阻塞。

## Next Step

建议下一步不要直接迁 worker，先继续 P1b / P2：

1. 先提交当前 P1b / P1c 代码与测试，保留 `probe_aio_parallel_contexts.py` 为未跟踪诊断脚本。
2. 补齐 AIO 运行时配置：至少让当前 worktree 或共享 env 具备 `AIO_BASE_URL / AIO_ENABLED / AIO_AUTH_TOKEN`。
3. P2：运行 AIO 并行 context probe，确认当前 runtime 支持多 context、多 page、多 browser process 还是必须多 sandbox lease。
4. 继续把 `network intercept` 之后的错误恢复、空答案复判、登录恢复 probe 逐步迁到统一 Browser Agent runtime，并减少平台 fallback。
5. 在共享 env 补齐 AIO 运行时配置后，跑真实“雅姿”四平台完整采集 UAT，记录卡点并修复。
6. P3：在 P1/P2 明确后，让 `LLMBrowserAgentPolicy` 真正接管默认执行路径，逐步替代 `BrowserAgentBootstrapPolicy` 只作为 deterministic guardrail。
