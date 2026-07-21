# 3c-B+：apply 后刷新 flow_plan（不 dispatch）

日期：2026-07-21  
依赖：M3 `confirm_run(user_action_type=refresh_flow_plan)` 已存在且 API 层不 dispatch。

## 行为

1. 用户在画布「编排建议」确认 apply-patch 成功。  
2. 若 `isAwaitingPlanConfirm`：调用父组件 `onRefreshFlowPlan`  
   → `confirmRun(..., { user_action_type: 'refresh_flow_plan' })`  
   → 后端 `_attach_flow_execution_plan` 按**最新** topology 写 `input_scope.flow_plan`  
   → status 保持 `waiting_scope_confirmation`，`intelligence_runs` confirm 路由**不** `dispatch_brand_intelligence_run`。  
3. 若不在待确认闸：仅更新画布拓扑；提示「下次发起运行时使用新计划」。

## 代码

- `AmwayFlowCanvas.applyTopologyPatch`  
- 复用 `AmwayAssociationCircleConsolePage.handleRefreshFlowPlan`（已接好）

## 手点

见 `2026-07-21-3c-b-live-checklist.md` **L5**。

## 结论

B+ 为前端缝合，零新后端动作；遵守「改图 ≠ 开跑」。
