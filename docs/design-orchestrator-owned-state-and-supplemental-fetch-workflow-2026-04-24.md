# Orchestrator-Owned State 与补抓闭环 Workflow 设计（2026-04-24）

状态：Implemented locally, runtime smoke passed, pending deployment  
范围：Workflow state、Task/Run 状态回写、Node/Skill 结果契约、A4 补抓、A5 报告衔接  
背景问题：线上出现 artifact 已完成但 Chat 进度条停在 60%，以及补抓后报告基于局部补抓结果而不是全量结果。

## Implementation State

| Phase | State | Evidence | Open Risk |
| --- | --- | --- | --- |
| Phase 0 - Baseline 与旧补丁废弃 | Done | 已从 `origin/main` 创建 `codex/orchestrator-state-runtime-refactor`，旧 `state-writeback-supplemental-merge` worktree/branch 已删除。 | 线上 copy-deploy 差异仍需最终部署前复核。 |
| Phase 1 - 状态写入基础设施 | Done | 新增 `TaskRuntimeStateWriter` 与 `WorkflowTransition`，stream 结束后通过 transition reconcile task/run 状态。咪咕体育 E2E 暴露 `orchestrator` 长阶段名超出 `analysis_tasks.error_stage String(10)`，已在 `TaskService` 统一归一短阶段码。A7 E2E 又暴露 completed transition 的 stage/message 被 `TaskService.complete_task()` 推断覆盖，已改为由 writer 显式传入 `final_stage/progress_message`。Targeted writer/stage tests passed。 | 线上 copy-deploy 前仍需复核迁移后字段与运行配置。 |
| Phase 2 - 节点状态权限收敛 | Done | A1/A2/A3/A4/A5/A7 workflow nodes 不再直接调用 `update_progress/complete_task/fail_task`；grep 仅剩 writer 入口。 | Scheduler 作为 headless adapter 暂保留专用状态写入。 |
| Phase 3 - 补抓闭环 workflow | Done | 补抓 target 只经 `tool_args` 传递，不再覆盖全量 `questions`；A4 merge 只覆盖目标 question-platform pair，非目标 pair 完整保留，并写入 `merge_metadata`。Targeted A4 test passed。 | 仍需用线上同形 session 做 runtime smoke。 |
| Phase 4 - A5 与前端状态验证 | Done | A5 validation 会拒绝 pair count 变窄的 supplemental canonical result；前端 `updateActiveTaskProgress` 不再用普通 progress event 覆盖 terminal/waiting task，且拒绝低于当前进度的回退事件。A7 skill completion event 修正为 `1.0/completed`，避免独立 skill 被 A1-A5 workflow step 计数拉回 `0%/running`。Targeted A5 test、frontend lint、tsc passed。 | 未做前端浏览器 UI 截图验证，本轮走 HTTP+WebSocket runtime path。 |
| Phase 5 - Code Review 与收口 | Done | `python scripts/validate_change.py` PASS；targeted pytest 14 passed；direct state-write grep 仅剩 `TaskRuntimeStateWriter`；diff check PASS；branch backend `/health` smoke PASS。咪咕体育本地 HTTP+WebSocket E2E 使用 `glm-5` 与指定 key override 跑通 A1-A5，session `75076001-e79d-42d7-84a8-96d9bbe5df84`，outputs 包含 `workflow/questionList/fetchResults/report`。A7 官网 AI 友好度 E2E 跑通，session `3c739d6b-b960-41b5-8aba-d2ac194dd805`，最终 task/latest_run `completed`，stage `A7`，progress `1.0`，message `官网 AI 友好度已完成`，outputs 包含 `site_confidence_report`。 | 尚未做线上部署与生产流量验证。 |

## Collaboration Execution Card State

### Boundary

- 本线程解决：Orchestrator-owned task state、本地补抓闭环 merge、A5 full canonical result gate、前端 progress 不覆盖官方终态。
- 本线程不解决：线上部署、生产流量验证、完整前端 UI 截图验证。
- 当前 Done 边界：本地实现、静态检查、单元测试、前端类型/lint、本地 backend health smoke、HTTP+WebSocket A1-A5 runtime smoke、任务文档状态回写完成。

### Four Calibration Questions

1. **What is this thing exactly?**
   - 官方 task state 是 workflow 执行状态真相；artifact/canonical result 是业务结果真相。两者不能互相推断。
2. **Who is the authority source?**
   - Orchestrator 决定 workflow transition，`TaskRuntimeStateWriter` 是唯一持久化入口；A4/A5 等 nodes 只返回事实与 artifact。
3. **What is the state lifecycle?**
   - Node/Skill result -> Orchestrator transition -> writer persist -> websocket/frontend projection。
   - 补抓 lifecycle：base full canonical result -> scoped overlay fetch -> pair merge -> new full canonical artifact -> A5 consumption。
4. **At what boundary is this "done" claim true?**
- 当前 done 到本地 implementation + validation closure + backend health smoke + 咪咕体育 A1-A5 HTTP+WebSocket runtime smoke + 咪咕体育 A7 官网 AI 友好度 runtime smoke；deployment / production validation 仍是 open。

### State Split

- `Project State`：代码已在 `codex/orchestrator-state-runtime-refactor`，旧补丁 worktree/branch 已删除；状态写入口和补抓 merge contract 已实现。
- `Conversation State`：用户明确要求废弃旧补丁，以设计文档为准，按阶段回写计划 State，并做 validation/code review。
- `Validation State`：design + implementation + static/unit/frontend validation + backend health smoke 已闭合；websocket runtime path 已覆盖 A1-A5 completed transition 和 A7 独立 skill completed transition，线上验证未闭合。

### Failure Samples

| Signal | Why it survived | Kill step | Writeback |
| --- | --- | --- | --- |
| Artifact 已完成但 Chat 进度卡 60% | Node local progress 与 official task state 混写，A4 可在 artifact 后把 task 写回 running/0.60。 | grep workflow direct `TaskService.update_progress/complete_task/fail_task`，只允许 writer 入口。 | 本文档 Phase 1/2 与 `TaskRuntimeStateWriter`。 |
| 补抓后 A5 只基于 partial result | 补抓 target 覆盖了 state `questions`，merge base 被缩成补抓子集；A5 没有识别 partial supplemental canonical result。 | target 只走 `tool_args`；A4 pair merge 保留非目标 pair；A5 校验 supplemental pair count。 | 本文档 Phase 3/4 与 targeted tests。 |
| 咪咕体育 E2E 第一轮用临时 SQLite 卡在 resume run | SQLite 对 Postgres partial unique index 支持不同，`task_runs.task_id` 在本地 create_all 下表现为全局唯一，导致第二个 run 插入失败。 | 真实 workflow/resume E2E 使用共享 Postgres 或迁移后的 Postgres，不把临时 SQLite 当 runtime-equivalent。 | E2E runner 改为共享 `DATABASE_URL`，该轮只作为环境差异样本。 |
| 咪咕体育 E2E 第二轮 A1 后失败态回写失败 | Orchestrator 失败阶段名 `orchestrator` 长度 12，超过 `analysis_tasks.error_stage String(10)`；writer 统一后首次覆盖到该路径。 | Task-level stage 统一归一为短码，长阶段保留在 `task_runs.checkpoint_stage`。 | `TaskService._coerce_task_stage_code` + targeted test；第三轮指定 `glm-5` 与正确 key 后已跑通 completed path。 |
| 咪咕体育 E2E 第三轮 A1-A5 完成 | 前两轮 runtime 使用了错误模型/key 或非等价 SQLite 环境，验证信号被外部因素污染。 | 显式进程级覆盖 `GLM5_MODEL_NAME=glm-5` 与指定 GLM5 key，使用共享 Postgres，走 HTTP+WebSocket runtime path。 | Session `75076001-e79d-42d7-84a8-96d9bbe5df84`：task/latest_run `completed`，progress `1.0`，stage `A5`，outputs 为 `workflow/questionList/fetchResults/report`。 |
| 咪咕体育 A7 E2E 首轮最终 stage 被写成 A5 | `RuntimeStateWriter` transition 已是 `stage=A7`，但 `TaskService.complete_task()` 没有接收权威 stage，回退到 `_infer_terminal_stage()` 默认 A5。 | completed transition 必须把 `final_stage/progress_message` 传入 TaskService；默认 `开始分析.../等待开始...` 不能作为完成文案。 | 修复后 session `3c739d6b-b960-41b5-8aba-d2ac194dd805`：task/latest_run `completed`，stage `A7`，progress `1.0`，message `官网 AI 友好度已完成`。 |
| 咪咕体育 A7 E2E 出现 `1.0 completed` 后又收到 `0.0 running` | Orchestrator 通用工具完成事件用 A1-A5 workflow step 计数计算独立 skill，site confidence 不在该列表内，所以完成事件被发成 `0%/running`。 | 独立 skill completed path 直接发 `1.0/completed`；前端 activeTask progress 增加单调保护，拒绝低进度覆盖。 | 最终 A7 E2E WS events 为 `A7 1.0 completed` 与 `site_confidence_assessment_skill 1.0 completed`，无回退。 |

## 1. 文档目标

本文档不是为某一个 bug 写局部修复方案，而是重新明确两个系统边界：

1. **谁拥有 workflow / task state 的流转权**
2. **补抓是否是一条独立闭合 workflow，而不是 A4 的一个参数分支**

目标是避免继续通过局部 patch 修补状态错乱，重新把系统拉回 `Agent + Skills + Context + Memory + Artifact/Version` 的基本设计价值观。

## 2. 价值观与基本原则

### 2.1 Orchestrator 拥有状态流转

`nodes / skills` 不应该各自决定全局 task 状态、terminal status、Chat 进度条状态。

正确职责划分：

- `Node / Skill`：执行能力，返回结构化结果、artifact 引用、observation、错误信息、建议下一步
- `Orchestrator`：理解执行结果，决定 workflow transition
- `TaskRuntimeStateWriter`：持久化 Orchestrator 的状态决策
- `Frontend`：渲染统一状态投影，不从多个事件源猜状态

目标调用链：

```text
Node / Skill result
  -> Orchestrator transition
  -> TaskRuntimeStateWriter persist
  -> WebSocket task/progress projection
  -> Frontend render
```

### 2.2 Node 可以汇报局部进度，但不能拥有全局状态

允许：

- A4 browser executor 发“第 N 个问题正在抓取”
- A5 发“报告生成中”
- Browser runtime 发 takeover / resume / error observation

不允许：

- A4 在 artifact 写完后自行把 task 写成 `running / 60%`
- A5 自己决定整个 task `completed`
- A1/A2/A3/A4/A5 各自独立写 `TaskService.update_progress()`
- WebSocket handler、node、orchestrator 同时竞争 terminal state

### 2.3 Artifact 是业务结果真相，Task State 是执行状态真相

两者不能混用：

- `Artifact / canonical result` 表示业务数据是否已经产出
- `Task / Run state` 表示本轮 workflow 是否完成、等待、失败、取消

Artifact 完成后，是否进入 `completed`、是否继续 A5、是否等待用户，必须由 Orchestrator 根据 workflow contract 决定。

### 2.4 补抓是 workflow，不是普通重抓

补抓复用 A4 抓取能力，但不是普通 A4 全量抓取。

补抓的独特职责是：

- 从上一轮全量 canonical result 中确定失败的 `question_id + platform`
- 只抓这些 target
- 用本轮补抓结果覆盖上一轮对应 pair
- 保留所有未命中的旧结果
- 生成新的全量 JSON 与全量 fetch artifact
- 后续 A5 只消费这份新的全量 canonical artifact

## 3. 当前实现问题

### 3.1 状态回写入口分散

当前至少这些层会直接写状态：

- `nodes.py`：A1/A2 直接调用 `TaskService.update_progress()` / `fail_task()`
- `nodes_a3.py`：A3 直接发送 progress，并在失败时写 task
- `nodes_a4.py`：A4 多处直接发送 progress，完成后写 `progress=0.60`
- `nodes_a5.py`：A5 直接 `complete_task()` / `fail_task()`，并返回 `execution_status=completed/error`
- `nodes_site_confidence.py`：A7 直接写 progress / complete / fail
- `websocket_langgraph.py`：stream 结束后根据 state 再次同步 task terminal state
- `orchestrator_node.py`：根据 workflow step 发送自己的 progress event
- `scheduler.py`：headless 任务直接 complete / fail

这说明当前不是“某个节点写错了”，而是状态所有权没有收口。

### 3.2 多个真相源竞争

当前用户看到的状态可能来自：

- `execution_progress` websocket event
- `task_status_change` websocket event
- `AnalysisTask.progress / status`
- `TaskRun.status`
- `current_step / execution_status` in LangGraph state
- artifact 输出事件
- browser takeover state

这些事件没有统一的 transition owner，因此会出现：

- artifact 已经出现，但 task 仍显示 running
- A4 已发 `completed / 1.0`，随后 task 又被写回 `A4 / 0.60`
- 刷新后从 DB 恢复出的 active task 与最新 artifact 不一致
- A5 已经生成报告，但前端仍显示上一阶段进度

### 3.3 补抓不是闭合 workflow

当前补抓主要通过：

- `run_supplemental_fetch`
- `retry_failed_only=True`
- `question_targets`
- `platforms`

把补抓意图塞回 A4。

问题在于：

- A4 scoped fetch 的抓取逻辑和补抓相同，但汇总逻辑不同
- 补抓需要以前一轮全量 result 为 base，而不是只看当前 run
- 当前 latest run / latest projection 容易把补抓局部结果当成全量结果
- A5 可能消费局部补抓结果，导致报告输入变窄

线上样本已经出现：

- 前两份 `fetchResults` 为 `11 问题 / 44 平台结果`
- 最后一份补抓后变成 `11 问题 / 33 平台结果`
- 随后生成报告

这证明当前补抓 artifact 没有稳定保持全量矩阵。

## 4. 目标状态模型

### 4.1 WorkflowTransition

新增或明确一个由 Orchestrator 产生的 transition contract：

```python
{
    "status": "running" | "waiting_input" | "failed" | "completed" | "cancelled",
    "stage": "A1" | "A2" | "A3" | "A4" | "A5" | "A7" | "orchestrator",
    "progress": 0.0,
    "message": "用户可见状态文案",
    "reason": "内部状态流转原因",
    "source": "orchestrator",
    "run_id": "...",
    "task_id": "...",
    "next_action": {...} | None,
    "artifact_refs": [...],
}
```

规则：

- 只有 Orchestrator 可以产生官方 workflow transition
- `TaskRuntimeStateWriter` 只接受这个结构写 DB
- 前端 task 状态只从该 transition 投影
- node 内部 progress 只能是 local event，不写 `AnalysisTask.status`

### 4.2 SkillResult / NodeResult

Node / Skill 返回能力执行结果，不返回全局 task 决策：

```python
{
    "skill_key": "answer_fetch",
    "executor_ref": "a4_answer_fetch",
    "status": "completed" | "degraded" | "failed" | "waiting_input",
    "summary": "...",
    "artifacts": [
        {
            "kind": "fetch_results",
            "message_id": "...",
            "artifact_key": "...",
            "version": "..."
        }
    ],
    "canonical_result": {...},
    "observation": {...},
    "error": {...} | None,
    "suggested_next_action": {...} | None,
}
```

规则：

- `status=completed` 只表示 skill 完成，不表示 workflow completed
- `suggested_next_action` 是建议，是否执行由 Orchestrator 决定
- `canonical_result` 是下游消费的唯一业务数据入口

### 4.3 TaskRuntimeStateWriter

新增或收口一个写入层，隐藏 `TaskService` 的多入口写入：

```text
TaskRuntimeStateWriter.apply_transition(WorkflowTransition)
```

职责：

- 更新 `AnalysisTask.status/current_stage/progress/progress_message`
- 更新目标 `TaskRun.status/checkpoint_stage/heartbeat/finished_at`
- 发布 `task_status_change`
- 保证 terminal state 不被 non-terminal progress 覆盖
- 拒绝非法倒退，例如 `completed -> running`

不负责：

- 判断业务是否完成
- 判断是否继续 A5
- 判断是否需要用户确认

## 5. Orchestrator 状态流转规则

### 5.1 Node 返回后统一结算

每个 node / skill 执行结束后，Orchestrator 做一次统一结算：

1. 读取 `last_skill_result` / `observation` / `validation_result`
2. 判断是否有 error 或 waiting input
3. 判断是否存在 deterministic `next_required_action`
4. 判断当前 workflow 是否还有后续步骤
5. 生成 `WorkflowTransition`
6. 决定输出用户可见总结、确认卡片、或继续执行下一个 tool

### 5.2 Terminal state 只在 Orchestrator 层写

以下状态只能由 Orchestrator 写：

- `completed`
- `failed`
- `cancelled`
- `waiting_input`

Node 可以返回：

- `error_info`
- `requires_user_decision`
- `followup_options`
- `artifact_write_validated`
- `completion_decision`

但不能直接写 task terminal。

### 5.3 Progress 语义分层

建议拆分：

- `local_progress`：node 内部执行进度，例如 A4 第几个问题
- `workflow_progress`：Orchestrator 根据 workflow steps 计算的全局进度
- `task_progress`：持久化后的官方进度，只由 transition writer 更新

前端 Chat 进度条使用 `task_progress / workflow_progress`，不使用 node 局部 progress 作为 terminal 判断。

## 6. 补抓闭环 Workflow

### 6.1 输入

补抓 workflow 的输入必须包含：

```python
{
    "base_a4_canonical_result": {...},
    "recovery_plan": {
        "question_targets": [
            {
                "question_id": "...",
                "question_text": "...",
                "platforms": ["kimi", "yuanbao"]
            }
        ],
        "platforms": ["kimi", "yuanbao"],
        "failed_question_count": 0,
        "failed_platform_count": 0
    },
    "fetch_mode": "full" | "fast",
}
```

`base_a4_canonical_result` 必须是上一轮全量 result，不允许只从 latest run 局部状态推断。

### 6.2 TPAOR 流程

补抓应有独立 TPAOR：

1. **Thought**
   - 说明上一轮哪些问题/平台失败
   - 明确本轮只补抓这些 target

2. **Plan**
   - 构造 `question_platform_targets`
   - 决定抓取模式和平台
   - 声明 merge 规则

3. **Action**
   - 调用 A4 executor 执行 scoped fetch
   - A4 executor 只负责抓取，不负责最终全量 artifact 语义

4. **Observation**
   - 记录补抓成功/失败统计
   - 得到 `supplemental_fetch_result`

5. **Response**
   - 执行 merge
   - 生成新的全量 canonical result
   - 写新的全量 artifact
   - 告知用户补抓完成，以及是否仍有失败

### 6.3 Merge Contract

Merge key：

```text
question_id + canonical_platform
```

规则：

1. `base` 来自上一轮全量 canonical result
2. `overlay` 来自本轮补抓结果
3. 如果 `overlay` 中存在相同 key，用 overlay 覆盖 base
4. 如果 base key 不在 overlay 中，必须保留
5. 如果 overlay 产生新 key，追加进入结果
6. 输出必须是新的全量 `fetch_results`
7. 输出必须重新计算：
   - `platform_status`
   - `timing_summary`
   - `fetch_recovery_plan`
   - `validation`

伪代码：

```python
merged = index_by_pair(base.fetch_results)
for result in supplemental.fetch_results:
    pair = (result.question_id, canonical_platform(result.platform))
    merged[pair] = result

full_fetch_results = group_by_question(merged.values())
```

### 6.4 Artifact 规则

补抓完成后必须写：

- 新的 `a4_canonical_result`
- 新的全量 `fetchResults` artifact
- 新的 artifact version / message id
- 新的 `fetch_recovery_plan`

不允许：

- 只把补抓局部结果写成 latest fetch artifact
- 让 A5 从本轮补抓局部 run 直接读数据
- 让 Canvas latest artifact 与 A5 input 不一致

### 6.5 A5 消费规则

A5 前置条件：

- 必须存在 validated `a4_canonical_result`
- `a4_canonical_result.fetch_results` 必须是全量结果
- 如果来自补抓，必须带 merge metadata：

```python
{
    "source": "supplemental_fetch_workflow",
    "base_artifact_id": "...",
    "supplemental_artifact_id": "...",
    "merge_key": "question_id+platform",
    "base_pair_count": 44,
    "overlay_pair_count": 11,
    "merged_pair_count": 44
}
```

## 7. 迁移计划

### Phase 1：冻结状态写入边界

目标：停止继续扩大多源写状态。

动作：

- 增加文档约束：新增 node/skill 不得直接调用 `TaskService.update_progress/complete_task/fail_task`
- 标记现有直接写状态位置为 legacy
- 新增 `TaskRuntimeStateWriter`，先包住现有 `TaskService`
- Orchestrator 开始通过 transition writer 写 terminal state

验收：

- 新增代码中没有新的散落 `TaskService` direct write
- terminal state 有唯一写入口

### Phase 2：Orchestrator-owned terminal state

目标：把 completed / failed / waiting_input 收回 Orchestrator。

动作：

- A5 不再直接 `complete_task()`
- A4/A5 error 不再直接 `fail_task()`
- `websocket_langgraph._sync_runtime_after_stream()` 只做兜底 reconciliation，不做主要状态决策
- Orchestrator 在 node 返回后统一结算 transition

验收：

- artifact 完成后不会被后续 node progress 覆盖为 running
- `completed -> running` 被 writer 拒绝或忽略
- 前端 active task 与 DB task terminal state 一致

### Phase 3：补抓 Workflow 一等化

目标：补抓不再只是 A4 参数。

动作：

- 新增 `supplemental_fetch_workflow` 或等价 node
- A4 executor 暴露 scoped fetch 能力
- 补抓 workflow 负责 base/overlay merge
- 补抓 artifact 始终写全量结果

验收：

- `11 问题 / 44 pair` 的 base，经任意局部补抓后仍输出全量 pair 数
- A5 消费的是补抓后 full canonical artifact
- Canvas latest fetch artifact 与 A5 input 一致

### Phase 4：清理 legacy direct writes

目标：逐步移除 node 内直接 task 状态写入。

动作：

- A1/A2/A3/A4/A5/A7 direct writes 迁移到 result contract
- `send_progress_event()` 用途收窄为局部 live progress
- `TaskService` 对外暴露更少方法，避免被 node 滥用

验收：

- grep node 目录不再出现 direct `complete_task/fail_task/update_progress`
- 所有 task status change 都能追溯到 Orchestrator transition

## 8. 验收标准

### 状态回写

必须验证：

- A4 artifact 写入成功后，Chat 不会倒退到 60% running
- A5 report artifact 完成后，task 状态稳定为 completed
- waiting input 的任务刷新后仍显示等待，而不是 running 进度条
- failed / cancelled / completed 不会被后续 progress event 覆盖
- WebSocket 断线重连后，active task 与 artifact 状态一致

### 补抓

必须验证：

- 初始全量结果 N 个 question-platform pair
- 补抓 M 个 failed pair
- merge 后仍是 N 个 pair，且 M 个 pair 被新结果覆盖
- 新 artifact 是全量 artifact
- A5 input 与新 artifact 完全一致
- 如果补抓后仍有失败，新的 recovery plan 基于 merged full result 生成

### 回归

必须覆盖：

- 普通全量 A4 -> A5
- 用户选择补抓 -> 补抓 artifact -> 用户选择报告
- headless scheduler A4 -> A5
- browser takeover waiting -> resume -> completed
- refresh/reconnect restore

## 9. 非目标

本文档不要求一次性重写全部 workflow。

非目标：

- 不重写 A1/A2/A3 业务生成逻辑
- 不重写平台 handler selector/parser
- 不改变现有 artifact 用户可见结构，除非为了补充 metadata
- 不把所有 live progress 都交给 Orchestrator 逐条生成
- 不取消 A4 executor 的局部实时进度

重点是先收口 **official state ownership** 与 **supplemental merge contract**。

## 10. Open Questions

1. `TaskRuntimeStateWriter` 是否作为新 service，还是先放在 `workflow/runtime_state_writer.py`？
2. 补抓 workflow 是新 node，还是作为 `answer_fetch` skill 的 sub-mode 但拥有独立 result contract？
3. A4 scoped fetch executor 的返回结构是否需要从 `fetch_results` 拆成 `supplemental_fetch_result`？
4. 旧 artifact version 是否保留在同一个 Canvas tab 里，还是补抓生成同 key 新 version？
5. Headless scheduler 的状态流转是否完全复用 Orchestrator transition，还是保留 scheduler 专用 adapter？

## 11. 当前结论

系统稳定性的关键不在于再给 A4 或前端补一个判断，而在于：

- 状态必须由 Orchestrator 统一流转
- Node/Skill 必须回到能力执行者角色
- Artifact 与 Task State 必须分清真相边界
- 补抓必须成为闭合 workflow，明确 base、overlay、merge、new full artifact、A5 consumption

如果这个设计原则不先落地，后续每一个线上问题都会继续变成局部 patch，最终让系统越来越难以推理。
