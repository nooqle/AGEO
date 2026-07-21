# Session Log: 3b-2.1 计划可视化（拓扑即计划）

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
前置：3b-1.1～1.6 + P0 闭合

## 目标

蓝皮书 3b-2.1：**执行计划投影到画布**。本切片先做「画布发起 / 拓扑约束模式」——计划由当前拓扑实时推导，不依赖 chat Orchestrator。

## 交付

| 项 | 说明 |
|---|---|
| 前端计划引擎 | `frontend/src/lib/amwayFlowExecutionPlan.ts`：topology + 平台开关 → steps / active edges / summary |
| 画布计划条 | `AmwayFlowCanvas` 顶部「本次执行计划」步骤链（pending/active/done/skipped） |
| 节点/边高亮 | 计划路径节点描边；计划边虚线品牌色；跳过节点降低透明度 |
| 后端镜像 | `topology_resolver.build_execution_plan_summary` + `GET /amwaychina/entities/{id}/flow-plan` |
| 测试 | `test_execution_plan_summary_skips_disconnected_platform_and_report` 等 29 相关 passed |

## 边界（本切片不做）

- chat 发起任务的 Orchestrator plan_update → 画布实时投影（3b-2 深水区 / 接近 3c）
- 意图相似度 → 模板推荐（3b-2.2）
- 图确认流（3c）

## 验证

- backend pytest topology/custom/gate：29 passed  
- frontend `tsc --noEmit`：通过  

## 下一站

- 3b-2.2 模板推荐，或  
- 将 `plan_update` WS 事件映射到画布临时高亮（chat 路径）
