## 背景

当前 Harness 已经能产出 `ValidationGateResult / HarnessDecision`，但 runtime 仍偏“记录型”：

- A4 / A5 / A7 会写回 gate 与 decision
- orchestrator 在进入下一轮前没有稳定消费这些决策
- follow-up 遇到重抓诉求时，只会提示“请改走 answer_fetch”，而不会真正重定向
- `auto_trigger_a5` 只是布尔标记，不是确定性的恢复动作
- `answer_fetch` 对 `fetch_mode` 过度依赖 ask_user，默认路径容易卡死

因此系统会表现为：

- 守门很多
- 提示很多
- 方案不够自动化
- 看起来像“知道该做什么，但不会自己接着做”

## 目标

本轮改造聚焦 5 个点：

1. 引入 `Runtime Policy Executor`，让 runtime 决策真正驱动下一步
2. 用 `next_required_action` 替代 `auto_trigger_a5`
3. 把 `post_analysis -> answer_fetch` 做成结构化重定向
4. 为 `answer_fetch` 建立默认模式策略，减少无意义确认
5. 增加 `alternative_action catalog`，让失败恢复和替代方案来自 runtime，而不是临场 prompt

## 设计原则

### 1. Runtime 优先于 Prompt

以下事情优先交给 runtime：

- 自动续跑
- 结构化重定向
- 默认抓取模式
- 常见失败后的替代动作

Prompt 只负责说明原则，不承担主要恢复逻辑。

### 2. 只有一个采集入口

保持既定边界：

- `post_analysis_skill` 只读已有结果
- 任何重新采集诉求都统一走 `answer_fetch`

局部重跑、全量重跑、切换 API / 浏览器，都只是 `answer_fetch` 参数，不是独立能力。

### 3. next_required_action 是 runtime contract，不是文案提示

`next_required_action` 用来表达“当前步骤结束后，系统必须继续执行的动作”。

典型场景：

- A4 局部重跑完成后，必须刷新 A5 报告
- post_analysis 检测到用户真实诉求是重抓，应立即改走 `answer_fetch`
- 用户从恢复弹窗中选择“先执行答案抓取/重新生成报告”等确定动作

## 新的数据结构

### next_required_action

建议 state 中新增：

```python
next_required_action: dict | None
```

结构：

```python
{
  "action_type": "run_tool",
  "tool_name": "analysis_report_skill",
  "tool_args": {"report_type": "persona"},
  "reason": "A4 局部重跑完成后需要刷新报告",
  "reply_text": "局部重跑已完成，继续刷新分析报告。",
  "source_step": "A4"
}
```

当前只支持 `action_type="run_tool"`，后续如有需要再扩展。

### alternative_action

恢复选项统一表达为：

```python
{
  "id": "run_answer_fetch",
  "label": "先执行答案抓取",
  "description": "补齐抓取结果后再继续后续分析",
  "action_type": "run_tool",
  "tool_name": "answer_fetch",
  "tool_args": {}
}
```

## Runtime Policy Executor

新增 runtime 执行层，挂在 orchestrator 进入 LLM 之前。

顺序：

1. 消费 `next_required_action`
2. 如果存在，就直接合成 synthetic tool call，复用 orchestrator 的正常 tool routing
3. 消费完成后清空 `next_required_action / last_validation_result / last_harness_decision`
4. 若没有待执行动作，再进入 LLM

这样可以保证：

- runtime 决策先于模型思考
- 继续执行的动作是确定性的
- 不再依赖模型“想起来下一步该做什么”

## A4 改造

### 现状问题

`auto_trigger_a5=True` 只是意图，不是行为。

### 新行为

当 A4 完成 scoped rerun 时，不再写 `auto_trigger_a5`，改为：

```python
next_required_action = {
  "action_type": "run_tool",
  "tool_name": "analysis_report_skill",
  "tool_args": {"report_type": current_analysis_mode},
  "reason": "A4 局部重跑完成后需要刷新报告",
  "reply_text": "定向重跑已完成，继续刷新分析报告。",
  "source_step": "A4",
}
```

## post_analysis -> answer_fetch 结构化重定向

### 现状问题

当前 follow-up 只会返回：

- “请改走答案抓取”

但这只是文本提示，不是运行时动作。

### 新行为

当 `post_analysis_executor` 检测到：

- `platforms`
- `fetch_mode`
- 其他采集型参数

则直接写入：

```python
next_required_action = {
  "action_type": "run_tool",
  "tool_name": "answer_fetch",
  "tool_args": filtered_fetch_args,
  "reason": "后续分析检测到重抓诉求，改走答案抓取",
  "reply_text": "已识别为重抓诉求，改由答案抓取继续执行。",
  "source_step": "post_analysis_executor",
}
```

节点自身只负责识别，不再要求用户手工改口。

## answer_fetch 默认模式策略

### 目标

减少不必要的 `ask_user`，但仍保留关键模式切换的可控性。

### 策略顺序

1. 如果 tool args 已显式给出 `fetch_mode`，直接使用
2. 如果用户最近一句明确表达“完整/全量/浏览器/full”，使用 `full`
3. 如果用户最近一句明确表达“快速/fast”，使用 `fast`
4. 如果当前 state 已有 `fetch_mode`，优先沿用
5. 如果是 headless，默认 `fast`
6. 如果当前已有问题集但没有显式模式，默认 `fast`
7. 仅当以上都无法判断时，才 ask_user

### 为什么默认 fast

因为 `fast` 是安全默认值：

- 成本更低
- 启动更快
- 用户之后仍可明确要求切 `full`

## alternative_action catalog

建立 blocker -> 替代动作目录。

初版覆盖：

- `fetch_results_missing`
- `analysis_context_missing`
- `artifact_writeback_failed`
- `all_platforms_failed`
- `partial_platform_failure`

典型映射：

- `fetch_results_missing` -> `run_answer_fetch`
- `analysis_context_missing` 且已有抓取结果 -> `run_analysis_report`
- `artifact_writeback_failed` in A5 -> `run_analysis_report`
- `artifact_writeback_failed` in A7 -> `run_confidence_signal`
- `partial_platform_failure` -> `run_answer_fetch`

这套目录用于：

- 失败恢复弹窗选项
- 恢复消息中的“建议优先”
- 后续 headless 安全默认策略

## 用户确认处理

恢复选项不再只是自然语言标签。

前端确认回传后，runtime 将识别：

- `run_answer_fetch`
- `run_analysis_report`
- `run_confidence_signal`

并写入对应的 `next_required_action`，由 orchestrator 下一轮自动执行。

## 与现有 Harness 的关系

本轮不是新建一套 Harness，而是把现有壳补成“驱动型”：

- `ValidationGateResult` 继续负责 gate 结果
- `HarnessDecision` 继续负责运行时判断
- `next_required_action` 负责把判断落成确定动作
- `Runtime Policy Executor` 负责消费这些动作

## 测试计划

至少覆盖：

1. `next_required_action` 能被 orchestrator 消费并转成 synthetic tool call
2. A4 scoped rerun 后写出 `next_required_action=analysis_report_skill`
3. post_analysis 的重抓诉求会写出 `next_required_action=answer_fetch`
4. `answer_fetch` 缺省模式会走默认策略，不再无条件 ask_user
5. `alternative_action catalog` 会为常见 blocker 产出确定恢复选项
6. 恢复选项被确认后，会写入对应 `next_required_action`

## 非目标

本轮不覆盖：

- AIO / browser runtime
- headless ask_user 全面策略重写
- unknown tool 的完整恢复机制
- 全部 blocker 的 catalog 覆盖

先把主路径打通：A4/A5/A7/follow-up/recovery。 
