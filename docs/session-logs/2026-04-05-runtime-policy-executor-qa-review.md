# Runtime Policy Executor / Recovery Routing QA & Code Review（2026-04-05）

## 范围

本轮覆盖：

- `Runtime Policy Executor`
- `next_required_action`
- `post_analysis -> answer_fetch` 结构化重定向
- `answer_fetch` 默认模式策略
- `alternative_action catalog`

明确不含：

- AIO / browser runtime
- unknown tool 全面恢复机制
- headless ask_user 全面重写

## Code Review

### 发现并已修复

1. 错误恢复面板的结构化动作虽然能写入 `next_required_action`，但确认回流时没有清掉 `error_info`。
   - 风险：orchestrator 下一轮仍会先走旧的错误恢复分支，导致结构化恢复动作失效。
   - 修复：在 [websocket_langgraph.py](/D:/AGEO-worktrees/validation-retro-harness/aeo-platform/backend/app/api/v1/websocket_langgraph.py) 的 confirmation 回流状态里显式清掉 `error_info / last_validation_result / last_harness_decision`，并保留 `next_required_action`。

2. `alternative_action catalog` 初版把 `artifact_writeback_failed` 直接映射到了 `run_confidence_signal`，会把 A5 持久化失败错误地引导到 A7。
   - 风险：恢复建议跨错步骤，破坏 runtime policy 的可信度。
   - 修复：只在当前步骤为 `A7` 时才暴露 `run_confidence_signal`。

### 复审结论

当前没有发现新的阻塞问题。  
这轮改造已经把 runtime policy 从“写状态”推进到“能驱动主路径继续执行”，但仍有后续工作：

- recovery catalog 还只是首批 blocker
- AIO / browser runtime 尚未并轨
- unknown tool / headless 默认策略还没纳入本轮

## QA

### 自动验证

1. `python -m py_compile` 覆盖本轮修改文件，通过
2. 复用 `D:\AGEO\.codex-main-merge\aeo-platform\backend\.env.local` 跑：

```bash
pytest aeo-platform/backend/tests/test_harness_refactor_foundations.py -q
```

结果：

- `33 passed`

### 覆盖点

1. `next_required_action` 可被 runtime executor 消费
2. `post_analysis_executor` 会把重抓诉求结构化重定向到 `answer_fetch`
3. `answer_fetch` 默认模式策略会优先用显式意图、已有模式和安全默认值
4. `alternative_action catalog` 会返回确定恢复选项

### 编码检查

仅对本轮变更文件做了问号污染扫描，未发现新引入污染。

## 当前结论

本轮可以放行到当前 worktree：

- runtime policy 已具备主路径驱动能力
- `auto_trigger_a5` 已被 `next_required_action` 取代
- `post_analysis -> answer_fetch` 已从文案提示变成结构化动作
- orchestrator 的默认抓取策略不再无条件卡在 ask_user
