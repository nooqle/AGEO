# Session Log: M1 任务计划 → 画布投影

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
主线：P0 / M1（Orchestrator/任务计划 → 画布投影）  
非目标：模板推荐、3c 自然语言改图

## 需求钉死

约束模式（amwaychina 控制台「开始运行」）下：

1. **启动时**按当前拓扑 + 平台开关生成结构化 `flow_plan`
2. 写入 `BrandIntelligenceRun.input_scope.flow_plan`（任务级快照）
3. 画布优先渲染该快照（徽章「任务计划」），并用 stage 推进 active/done
4. 未开跑时仍用本地拓扑预览（徽章「拓扑预览」）

## 交付

| 层 | 内容 |
|---|---|
| 后端 | `create_or_reuse_run` 对 association 任务调用 `_attach_flow_execution_plan` |
| 后端 | plan 复用 `build_execution_plan_summary`（与 3b-1 门控一致） |
| 后端 | 启动 message 含 plan summary：`按拓扑计划执行：…` |
| 前端 | `parseServerFlowPlan` / `mergeRuntimeOntoPlan` |
| 前端 | 画布计划条区分「任务计划」vs「拓扑预览」 |

## 与蓝皮书 3b-2.1 的关系

- 蓝皮书写的是「chat 发起的 Orch 规划上画布」
- 本切片先完成 **约束模式任务计划上画布**（主线可见/可对账的第一刀）
- 自由 chat Orch `plan_update` → 画布 仍属后续（M1 加深或接近 3c）

## 验证

- `tests/test_topology_resolver.py`：12 passed  
- `_attach_flow_execution_plan` smoke：ok  
- `tsc --noEmit`：通过  

## Validation Closure（M1 出口检查 · 2026-07-21）

证据：`docs/session-logs/2026-07-21-m1-exit-check-evidence.json`  
脚本：`scripts/m1_exit_check.py` + frontend `tsx` 纯函数检查

| 检查项 | 结果 |
|---|---|
| 拓扑预览断 doubao | ✅ 计划平台无 doubao |
| Run 写入 flow_plan | ✅ source=topology_constraint |
| Runtime 叠加 stage | ✅ A4→fetch active；skipped 不可被 runtime 打开 |
| 运行中锁快照 | ✅ 设计：有 activeRun 时优先 flow_plan |
| 单测回归 | ✅ 32 passed |
| 前端 parse/merge | ✅ tsx 合约通过 |
| 真机点「开始运行」看徽章 | ⏭ 环境 8000/3000 未起 |

**结论**：`PASS_WITH_RESIDUAL` — **允许进入 M3**。残留仅为 live UI 点穿，不阻塞主线。

## 代码质量（M1）

- **改动面**：run service 附加 plan；canvas 消费快照；纯函数库扩展  
- **风险**：低（不改 A4 采集内核；plan 失败只 warning）  
- **一致性**：与 topology_resolver 门控同源  
- **债**：live UI 未点穿；chat Orch plan_update 未接  

## 下一主线项

**M3：轻量图确认闸**（确认后再执行）— 未开始。
