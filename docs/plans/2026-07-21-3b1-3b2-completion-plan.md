# Plan：完善 3b-1 + 推进 3b-2 + 联合验收

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
定案：**甲 + 甲**

| 定案 | 含义 |
|---|---|
| 3b-1 完善甲 | 拓扑摘要进上下文 + 确定性门控全覆盖；**不做** Orch LLM 读图动态调度 |
| 3b-2 推进甲 | console 任务 + 服务端 plan 上画布即可；**不做** 必须 chat 窗口发起 |
| 模板推荐 | **本阶段 Out of scope** |
| 3c / M5 | **联合验收通过后再开** |

---

## 目标与非目标

### 目标

1. 补满蓝图 **3b-1** 可验收缺口（约束执行可靠、可证伪）  
2. 补满蓝图 **3b-2.1** 约束模式语义（计划可见、任务同源、可确认）  
3. 一次 **3b-1 + 3b-2 联合验收** 关门  

### 非目标

- 意图相似度 / 拓扑模板推荐  
- Chat 自然语言 → 拓扑 diff（3c）  
- 通用 DAG 引擎重写  
- A1/A2 全面节点化  

---

## 任务板（对照更新）

| ID | 任务 | 状态 | 完成定义 | 证据 |
|---|---|---|---|---|
| **T0** | 制定本 Plan | ✅ done | 文档落地，甲+甲写死 | 本文档 |
| **T1** | 3b-1-A 拓扑摘要进 association/run 调度上下文 | ✅ done | flow_plan 注入 dashboard_context + Orch 渲染 | `test_flow_plan_context.py` |
| **T2** | 3b-1-B 断平台真路径证据 | ✅ done | A4 入口 filter 无 doubao | p0 evidence JSON |
| **T3** | 3b-1-C 自定义节点真路径证据 | ✅ done | analysis/content mode=llm | p0 evidence JSON |
| **T4** | 3b-1-D 局部运行边界写清 | ✅ done | 画布局部运行文案 | AmwayFlowCanvas |
| **T5** | 3b-1-E 测试冻结入口 | ✅ done | 冻结套 49 passed | `scripts/run_3b1_suite.py` |
| **T6** | 3b-1 小出口检查 | ✅ done | PASS_WITH_RESIDUAL | `docs/session-logs/2026-07-21-3b1-completion-exit.md` |
| **T7** | 3b-2 服务端 plan 与画布统一/收尾 | ✅ done | flow_plan 进 state/context；画布任务计划徽章 | seam + context tests |
| **T8** | M3 与 3b-2 计划同源缝合 | ✅ done | refresh 不 dispatch；confirm 锁 plan | ALL_SEAM_OK smoke |
| **T9** | 3b-1+3b-2 联合验收 | ✅ done | PASS_WITH_RESIDUAL | `docs/session-logs/2026-07-21-3b1-3b2-joint-acceptance.md` |

状态图例：`⬜ pending` · `🔄 in_progress` · `✅ done` · `⏭ skipped` · `⛔ blocked`

---

## 任务详述

### T1 — 3b-1-A 拓扑上下文

- 在 `_build_brand_run_initial_state` 把 `input_scope.flow_plan` 注入 `dashboard_context`  
- Orch context packet 渲染 flow_plan 摘要（平台、跳过项、summary）  
- 单测：有 flow_plan 时 packet/render 非空  

### T2 — 断平台证据

- 复用/扩展 gate wiring + attach plan 脚本  
- 产出 `docs/session-logs/*-3b1-platform-gate-evidence.json`  

### T3 — 自定义节点证据

- 复用 P0 LLM 验证或全链路脚本  
- 产出 analysis mode=llm 证据  

### T4 — 边界说明

- session log + 画布文案（局部运行仅自定义分支）  

### T5 — 测试冻结

- `scripts/run_3b1_suite.py` 或 Makefile/文档命令固定  

### T6 — 3b-1 小出口

- 检查表 + 结论；不阻断小残留（须列出）  

### T7 — 3b-2 收尾

- 校验 create/confirm 后 canvas 一律吃 `run.flow_plan`  
- 修缝：确认前后徽章/文案  

### T8 — M3 缝合

- confirm 锁 plan 与 dispatch 一致  
- refresh 不 dispatch  

### T9 — 联合验收场景

1. 默认全连 → 确认 → 跑  
2. 断 doubao → 计划与执行一致  
3. 断报告边 + analysis → 计划与产出  
4. 确认闸：刷新 / 确认 / 取消  

---

## 进度日志

| 时间 | 事件 |
|---|---|
| 2026-07-21 | 甲+甲定案；Plan 创建；开始 T1 |
| 2026-07-21 | T1–T6 完成；3b-1 甲 PASS_WITH_RESIDUAL；进入 T7 |
| 2026-07-21 | T7–T9 完成；联合验收 PASS_WITH_RESIDUAL；3b-1/3b-2 甲阶段关门 |

---

## 完成标准（阶段关门）

- 蓝图 **3b-1** 可宣称工程完成（甲范围）  
- 蓝图 **3b-2.1** 约束模式可宣称完成（甲范围；模板推荐 out of scope）  
- 联合验收 `PASS` 或 `PASS_WITH_RESIDUAL`（残留可列）  
- 下一步才允许开 **3c / M5**  
