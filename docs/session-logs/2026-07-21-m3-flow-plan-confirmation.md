# Session Log: M3 轻量图确认闸

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
主线：P1 / M3（确认后再执行）  
非目标：模板推荐、3c 自然语言改图、完整 multi-party 审批

## 需求

用户在 amwaychina 画布发起运行时：

1. **不立刻采集** — 先生成并展示任务计划  
2. **确认闸**：确认并执行 / 刷新计划 / 取消  
3. **确认时再锁拓扑** — `flow_plan` 以确认瞬间拓扑为准  

## 交付

| 层 | 内容 |
|---|---|
| 后端 create | `auto_dispatch=false` 的 association 任务 → `waiting_scope_confirmation` + `user_action_type=flow_plan_confirmation` |
| 后端 confirm | `refresh_flow_plan` 仅刷新快照不 dispatch；`confirm_flow_plan` 再锁 plan 并进入 `planning_questions` + dispatch |
| API | confirm 若仍 `requires_user_action` 则不 `ensure_runtime_submitted` |
| 前端 console | 创建 run 改为 `auto_dispatch: false`；confirm/refresh/cancel handlers |
| 前端 canvas | 待确认态计划条 + 三按钮；header「待确认计划」 |
| 类型 | `isAwaitingFlowPlanConfirmation` / `isExecutingBrandIntelligenceRun` |

## 用户路径

```
开始运行
  → 任务进入 waiting_scope_confirmation（任务计划可见）
  → [可选] 改拓扑/平台 → 刷新计划
  → 确认并执行 → 真正 dispatch
  → 或 取消
```

## 验证

- confirm_run refresh/execute smoke：ok  
- tsc：见提交时结果  

## 代码质量

- **改动面**：run lifecycle + console/canvas UI；复用既有 confirm API  
- **风险**：中（改了 create 默认路径）；非 association 的 `auto_dispatch=true` 行为不变  
- **债**：live UI 未点穿；确认闸暂无二次编辑 input_scope 全字段，主要平台+拓扑  

## 下一主线

**M5：受控 chat → 拓扑 diff**（或先补 M3 live 点穿）
