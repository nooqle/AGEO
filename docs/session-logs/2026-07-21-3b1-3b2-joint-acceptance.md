# 联合验收：3b-1 + 3b-2（甲+甲）

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
Plan：`docs/plans/2026-07-21-3b1-3b2-completion-plan.md`

## 范围

| 包含 | 不包含 |
|---|---|
| 3b-1 甲：门控 + 拓扑上下文 + 自定义真执行 + 局部边界 | Orch LLM 动态读图 |
| 3b-2 甲：console 任务 plan 上画布 + 确认闸 | 模板推荐；必须 chat 窗口发起 |

## 场景结果

| # | 场景 | 结果 | 证据类型 |
|---|---|---|---|
| 1 | 默认拓扑 → 计划合理 → 可确认后执行 | ✅ 合约 | create `waiting_scope_confirmation` + confirm → `planning_questions` smoke |
| 2 | 断 doubao → 计划与执行门控一致 | ✅ | A4 `platform_filter` 无 doubao；plan planned_platforms 无 doubao |
| 3 | 自定义 analysis/content 可产出 | ✅ | 真 LLM mode=llm（p0 evidence） |
| 4 | 确认闸：刷新 / 确认 / 取消 | ✅ 合约 | refresh 保持 waiting；confirm 锁 plan；cancel API 既有 |

## 自动化门禁

- `python scripts/run_3b1_suite.py` → **49 passed**  
- `python scripts/p0_3b1_closure_verify.py` → **all_ok**  
- T7/T8 seam smoke → **ALL_SEAM_OK**  

## 残留（不挡 3b 阶段关门）

1. 本机 8000/3000 未起时的 **live UI 点穿**（徽章/三按钮手点）  
2. 完整 brand-intelligence **多平台真采集一轮** 日志对照  
3. chat 窗口 Orch `plan_update` 投影（甲方案不要求）  

## 结论

**PASS_WITH_RESIDUAL**

- 蓝图 **3b-1（甲）**：可宣告完成  
- 蓝图 **3b-2.1 约束模式（甲）**：可宣告完成  
- 蓝图 **3b-2.2 模板推荐**：Out of scope  
- **下一阶段**：3c / M5（自然语言 → 拓扑 diff），或先补 live UI 残留  

## 代码质量简报（本阶段）

| 项 | 说明 |
|---|---|
| 改动面 | topology plan → run state/dashboard_context/Orch 渲染；确认闸；画布计划 UI |
| 风险 | 中低；采集内核未重写；association create 默认确认闸 |
| 测试 | 冻结套 49 + P0 真 LLM + seam smoke |
| 纪律 | 未混入模板推荐 / 3c 编译器 |
