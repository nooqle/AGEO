# Browser Agent 状态统一与接管主链路修复设计

日期：2026-04-14  
状态：Draft  
范围：A4 浏览器抓取、A5 报告衔接、Browser Agent、AIO takeover、Orchestrator prompt/context  
工作目录：`D:\AGEO-worktrees\aio-runtime-isolation`

## 1. 文档目标

这份设计文档解决的不是某一个页面 bug，而是当前浏览器抓取链路在以下几类问题上的共同病根：

1. 浏览器现场接管与恢复不稳定
2. A4/A5/Artifact/Message/TaskRun 状态不一致
3. 刷新与重连后旧 pending 状态复活
4. Prompt 与 Context 过大，导致 Browser Agent 和 Orchestrator 都存在预算失控
5. 性能没有结构化遥测，只能靠碎片日志猜问题

目标是在**不改 A1-A7 业务语义、不破坏现有 artifact 结构、不把系统改成另一套产品**的前提下，收紧控制面与状态面。

## 2. 当前问题不是散点，而是四类系统性缺陷

### 2.1 状态真相分裂

当前至少存在以下并行状态面：

- `Message` 中的抓取状态
- `Artifact` 中的抓取状态
- A4 legacy `platform_results`
- A4 `aio packet summary`
- `TaskRun / active_task`
- `pending_confirmation`
- `browser_action_request`
- `OUTPUT` message 恢复面

这些状态面不是从同一个 authoritative source 投影出来的，因此会出现：

- Message 里 `Kimi=已跳过`，Artifact 里 `Kimi=失败`
- Message 里 `元宝=失败`，Artifact 里 `元宝=成功`
- 刷新后 Message / Artifact 丢失，但 Agent 仍能基于已有数据继续分析
- A4 摘要已经出现，但系统仍认为任务在运行，阻止后续输入

### 2.2 浏览器现场 ownership 不稳定

当前 Browser Agent 的理论目标是“观察并接管当前 live scene”，但实际上仍可能观察到：

- 已关闭的旧 page handle
- 被错误复用的 context
- 新开的空 context
- 平台主页，而不是实际阻塞弹窗现场

这会直接导致：

- 已登录仍反复提示登录
- 点“我已完成”后没有无缝继续，而是重新打开或重新判断
- late login / verify / captcha 识别不稳定
- 多平台抓取看起来像“只有一个平台在动”

### 2.3 刷新/重连恢复状态机没有闭合

当前重连时会做：

- 状态重建
- pending confirmation replay
- pending browser actions replay

但系统没有足够清晰地区分：

- 当前仍有效的 pending
- 已经过期的 pending
- 已被新 run 覆盖的 pending
- 已被 resolve 但未正确结算的 pending

结果是刷新后会出现：

- 多张旧卡片复活
- 页面停留在明显错误的“待处理”状态
- 当前任务和旧任务的交互提示混在一起

### 2.4 Prompt / Context 预算失控

当前两个控制器都出现过同类问题：

- Orchestrator prompt 虽然已经 section 化，但仍有“大 prompt”倾向
- Browser Agent 把 `screenshot / refs / text / meta` 过量打包进同一次判定

这会导致：

- `Prompt exceeds max length`
- LLM 退化回 deterministic fallback
- late blocker 检测质量下降
- 模型理解没有变强，反而被上下文噪音压垮

## 3. 设计原则

### 3.1 Agent First，但必须配合确定性运行时

本系统不是“纯规则浏览器自动化”，也不是“纯视觉大模型乱点页面”。

正确分层是：

- `Harness / Tool / Runtime` 负责确定性事情
- `Browser Agent` 负责开放世界判断
- `Human Takeover` 只做最后兜底

### 3.2 不再继续把页面理解堆回 handler

平台 handler 不再承担页面主判断职责。  
handler 只能保留平台薄配置和平台特有提问/抽取语义。

### 3.3 不再新增 runtime semantic rewrite

当前会话追问场景应当依赖：

- contextual tool exposure
- skill contract 边界
- packet-first context

而不是在 runtime 里做“模型选错了，我再帮它改写成另一个工具”的补锅逻辑。

### 3.4 单一真相源，其他全部是投影

抓取状态、任务状态、接管状态、报告状态必须来自同一 authoritative state。  
Message、Artifact、WebSocket replay、Canvas、通知，只能是这个状态的投影。

### 3.5 Browser Agent 默认 `state-first`

借鉴 OpenCLI Browser Skill，可抽象成以下原则：

1. 优先结构化 `state`，不是优先 `screenshot`
2. 交互走原语：`click/type/select/press/wait/get/network`
3. 页面变化后重新获取 state，不猜页面
4. 优先结构化 DOM / network / ready signal，不靠视觉硬猜
5. 每一轮只给模型必须知道的那一小块上下文

这不是照搬 OpenCLI 的命令格式，而是吸收它的控制策略。

## 4. 目标架构

### 4.1 Browser Runtime

Browser Runtime 负责：

- `page/context/lease ownership`
- AIO / CDP / VNC attach
- action primitives
- deterministic wait / resync / target-closed 处理
- takeover surface issuance
- timing / telemetry

它不负责页面语义判断。

### 4.2 Browser Agent

Browser Agent 负责：

- 判断当前是不是登录页/登录弹窗
- 判断是不是验证码/验证/账号确认
- 判断是不是普通弹窗/广告/cookie/下载提示
- 决定点哪个 CTA、是否关闭弹窗、是否等待
- 判断当前页面是否 ready 可以继续提问或继续抓取

它不负责：

- 账号密码输入
- 短信码输入
- 验证码识别与处理
- 抽取答案主流程

### 4.3 Platform Handler

平台 handler 只保留：

- `entry_url`
- `ready_url_patterns`
- `login_url_patterns`
- 平台自然语言 hints
- 提问动作
- 答案抽取契约
- 平台特有 postprocess

平台 handler 不再主导：

- 初始登录判定
- late login/verify 判定
- resume 主逻辑
- takeover 触发主逻辑

### 4.4 Human Takeover

人工接管只处理：

- 登录
- 二维码扫码
- 短信码
- 验证码 / 人机验证
- 账号安全确认

人类不再承担：

- 自己去判断该点哪个登录按钮
- 自己把平台首页操作到阻塞现场
- 自己判断是否已恢复可继续抓取

## 5. Authoritative State 设计

### 5.1 新的统一状态模型

引入 `FetchRunState` 作为抓取链路唯一真相源，主键：

- `task_id`
- `platform`

字段至少包含：

- `status`
  - `pending`
  - `running`
  - `takeover_required`
  - `skipped`
  - `succeeded`
  - `failed`
- `attempt`
- `timing`
- `latest_packet`
- `auth_state`
- `takeover`
- `artifact_write_status`
- `last_error`

### 5.2 投影规则

以下所有表面都必须改成从 `FetchRunState` 投影：

- Message 中的平台抓取状态
- Artifact 中的平台成功/失败/跳过统计
- A4 摘要卡片
- WebSocket replay
- Canvas 平台状态展示

禁止继续出现：

- Message 用 packet
- Artifact 用 legacy `platform_results`
- replay 用数据库旧 message
- active task 用另一套状态

### 5.3 A5 衔接规则

A5 是否可以开始，不看 Message 是否已经显示摘要，而只看：

- 所有平台是否达到终态
- 是否允许部分成功降级继续
- `FetchRunState` 是否已经完成最终写回

这能避免“答案抓取看起来完成了，但系统仍卡在 60%”。

## 6. Takeover 生命周期重构

### 6.1 当前错误模式

当前错误模式是：

1. 人工点“我已完成”
2. 后端同步跑重型 `resume_probe`
3. `resume_probe` 里又重新判断/重建 context
4. UI 长时间显示“正在确认”
5. 最终可能又回到重新登录/重新接管

这条链不应存在。

### 6.2 正确生命周期

正确逻辑应为：

1. Browser Agent 发现人工 blocker
2. Runtime 发行 takeover，并 attach 到**当前 live blocking scene**
3. 用户处理完成，点击“我已完成”
4. 后端立即 ACK，释放 human lock
5. Agent 直接接回原 scene 继续执行
6. 若继续执行时再次卡住，再抛新的 takeover

### 6.3 `resume_probe` 的新角色

`resume_probe` 不再是主阻塞 gate，只保留轻量职责：

- 校验原 scene ownership 是否仍有效
- 校验当前 blocker fingerprint 是否已变化
- 记录恢复时刻和恢复结果

它不得再：

- 阻塞 `resolve_takeover`
- 默认新开 context
- 代替 Agent 再做一轮页面主判断

### 6.4 去重与过期

takeover 去重键统一为：

- `platform + task_id + specta_user_id + blocking_fingerprint`

规则：

- fingerprint 不变，不重复发卡
- resolve 后进入 settled 态
- refresh 时只 replay 仍有效的 active takeover
- 已被新 run 覆盖的 takeover 不得复活

## 7. Browser Agent Prompt / Context 设计

### 7.1 Browser Agent 只看阶段化 observation

不再把完整 `BrowserPageObservation` 整包送进 LLM。  
改成 stage-specific slicing：

- `preflight`
- `wait_gate`
- `resume_after_handoff`
- `empty_answer`

### 7.2 默认 observation slicing

#### preflight

- `url`
- `title`
- 少量 CTA refs
- 最多 320 字可见文本
- 不带 screenshot

#### wait_gate

- `url`
- loading / blocker 相关文字
- 最多 6 个高相关 refs
- 最多 220 字可见文本
- 不带 screenshot

#### resume_after_handoff

- blocker 相关少量 state
- `action_type`
- 最多 220 字文本
- 不带 screenshot

#### empty_answer

- 仅保留答案区附近最小片段
- 默认不带 screenshot
- 只有明确视觉回退条件才允许

### 7.3 Browser Agent 输出能力

Browser Agent 的动作范围固定为：

- `click`
- `press`
- `focus`
- `wait`
- `close_modal`
- `navigate` 到已知平台入口

显式禁止：

- 填账号密码
- 填短信码
- 处理验证码
- 任意导航到未知 URL

### 7.4 Browser Agent 的默认工作模式

默认模式是：

- deterministic runtime 负责 page lifecycle 和基础恢复
- Browser Agent 负责页面语义判断和轻量操作
- fallback 存在，但 fallback 不得变回“平台 handler 自己决定一切”

## 8. Orchestrator Prompt / Context 设计

### 8.1 Prompt 不再是 section 化的大说明书

Prompt 需要严格 budget 化。

system prompt 只保留四层：

1. `immutable_core_policy`
2. `contextual_tool_surface`
3. `runtime_context_packets`
4. `conditional_runtime_reminders`

### 8.2 保留策略

在 budget 冲突时，优先级固定为：

1. core policy
2. 当前回合真实工具面
3. 当前轮必要 runtime packet
4. 条件提醒
5. 扩展型 skill index

### 8.3 当前会话追问的控制方式

当前会话 follow-up 不靠 runtime rewrite，而靠：

- contextual tool exposure
- skill contract
- prompt 中极短的当前回合约束

这意味着：

- 当前会话已经有 `fetch_results / report`
- 用户问“本次结果细节”
- 就不暴露 `knowledge_*`
- 只暴露 `drill_down_analysis / compare_snapshots / answer_fetch(必要时)`

## 9. 性能遥测设计

### 9.1 必须结构化记录的耗时

为每个 A4 run 记录：

- 总耗时
- 平台总耗时
- 平台阶段耗时

平台阶段至少拆为：

- `preflight`
- `submit_question`
- `wait_for_answer`
- `extract_answer`
- `takeover_wait`
- `resume_after_handoff`
- `persist_result`

### 9.2 失败分类

失败不再只看“无有效答案”，而是明确分类：

- `platform_rate_limit`
- `late_login_required`
- `verification_required`
- `target_closed`
- `resync_failed`
- `empty_answer`
- `artifact_write_failed`
- `task_state_transition_failed`

### 9.3 目标

这样后续我们才能回答：

- 整体慢在哪里
- 哪个平台慢
- 是平台风控慢，还是系统恢复慢
- 优化该投在 Browser Runtime、Browser Agent、还是平台执行器

## 10. 迁移顺序

### R1：状态真相收口

先引入 `FetchRunState`，并让 Message / Artifact / replay 都从它投影。  
这是修：

- 状态不一致
- 刷新丢答案
- 60% 卡住
- 刷新 pending 复活

的总阀门。

### R2：接管与浏览器控制面收口

把：

- 初始登录判定
- late blocker 判定
- 接管恢复

收回 Browser Runtime + Browser Agent。

这是修：

- 已登录反复提示登录
- “我已完成”后不继续
- 打开后不是阻塞现场

的总阀门。

### R3：Prompt / Observation 收口

落实：

- Orchestrator budgeted prompt
- Browser Agent observation slicing

这是修：

- Prompt 超长
- Browser Agent 判定退化
- 控制器噪音过高

的总阀门。

### R4：性能遥测与真实验收

补上 timing/telemetry 后，再跑：

- Kimi / DeepSeek 接管烟测
- 一次完整品牌浏览器采集
- 一次“我已完成 -> Agent 继续”
- 一次 A5 报告生成

## 11. 验收标准

达到以下条件，才算这轮收口完成：

1. Message / Artifact / replay 的平台状态一致
2. 刷新后不丢抓取结果，不复活过期 pending
3. 点击“我已完成”后，Agent 直接继续；若再次卡住，抛新的 takeover
4. 已登录平台不会因为 scene ownership 丢失而反复要求登录
5. Browser Agent 日志中不再出现大规模 `Prompt exceeds max length`
6. A4 能正确进入 A5，部分成功降级路径也能稳定写出报告
7. 可以输出总耗时、平台耗时、阶段耗时

## 12. 非目标

本轮不做：

- 改 A1-A7 的产品语义
- 让 LLM 接管答案提交主流程
- 让 LLM 接管答案抽取与证据解析
- 把 AIO runtime 全面替换成另一套浏览器框架
- 为了止血重新堆回一堆平台 selector 特判

## 13. 与现有设计文档的关系

这份文档是对以下文档的收口与修订，不是替代：

- [architecture-aio-answer-fetch-tool-runtime-2026-04-12.md](D:/AGEO-worktrees/aio-runtime-isolation/docs/architecture-aio-answer-fetch-tool-runtime-2026-04-12.md)
- [design-aio-browser-runtime-boundary-2026-04-09.md](D:/AGEO-worktrees/aio-runtime-isolation/docs/design-aio-browser-runtime-boundary-2026-04-09.md)
- [design-harness-phase7-orchestrator-context-2026-04-04.md](D:/AGEO-worktrees/aio-runtime-isolation/docs/design-harness-phase7-orchestrator-context-2026-04-04.md)
- [design-post-analysis-fetch-boundary-and-orchestrator-solution-policy-2026-04-05.md](D:/AGEO-worktrees/aio-runtime-isolation/docs/design-post-analysis-fetch-boundary-and-orchestrator-solution-policy-2026-04-05.md)

本文件新增的关键约束是：

- `FetchRunState` 作为唯一真相源
- `resolve_takeover` 不再同步阻塞重型恢复逻辑
- Browser Agent 采用 `state-first` 的小 observation 模式
- Orchestrator prompt 进入严格预算治理

## 14. 下一步

写完本设计后，实际实现应严格按以下顺序推进：

1. 先实现 `FetchRunState`
2. 再实现 takeover 生命周期收口
3. 再继续 Browser Agent 页面理解收回共享 runtime
4. 最后补 timing/telemetry 与真实验收

如果顺序反过来，系统会继续陷入“表面 bug 修不完，底层状态始终不稳”的循环。
