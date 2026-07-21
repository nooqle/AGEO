# 3c-B Live 手点清单（①）

日期：2026-07-21  
前置：本地后端 + 前端已起；amwaychina 实体有 manage 权限；画布在「品牌生产线」视图。

对照实现：`编排建议（试验）` 条（`AmwayFlowCanvas`）+  
`POST .../flow-topology/preview-patch|apply-patch`

## 环境

| 项 | 填写 |
|---|---|
| 前端 URL | `http://127.0.0.1:3000/amwaychina` |
| 实体 / 中心词 | `18e1597a-a9c0-4918-ae64-c0d7cd96f04d` / 安利 |
| 操作人 | Codex（真实浏览器手点） |
| 开始前 topology version（Network GET flow-topology） | `0` |
| 被测提交 | `4120d9b` |

## 用例矩阵

### L1 · 跳过豆包（无在途 run）

| 步 | 操作 | 期望 | 结果 (✓/✗) | 备注 |
|---|---|---|---|---|
| 1 | 点「跳过豆包」 | 出现变更摘要，含断开 `e-fetch-doubao` 或可读文案；计划平台无 doubao | ✓ | 预览显示“断开：e-fetch-doubao”，平台仅 deepseek/kimi/hunyuan |
| 2 | 点「确认应用」 | 画布豆包平台边视觉断开/灰；localStorage 与 GET topology 一致 | ✓ | 画布计划移除豆包并显示“跳过 1 项”；因浏览器测试安全约束未直接读取 localStorage，服务端 GET/数据库与重载后的 UI 一致 |
| 3 | 再 GET topology | `removedEdgeIds` 含 `e-fetch-doubao`；version +1 | ✓ | version `0 → 1`，`removedEdgeIds=["e-fetch-doubao"]` |
| 4 | **未**点确认开跑 | 无新的 intelligence run 自动 dispatch | ✓ | 最新 run 仍为 2026-07-11 历史任务，未新增 run |

### L2 · 恢复全部平台

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 在 L1 后点「恢复全部平台」→ 预览 → 确认 | `removedEdgeIds` 去掉平台边；四平台可计划 | ✓ | version `1 → 2`，`removedEdgeIds=[]`，四平台恢复 |

### L3 · 加图谱分析节点

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 点「加图谱分析节点」→ 确认 | 出现 analysis 自定义节点 + projection→节点边 | ✓ | 写入 `custom-analysis-3c-preset` + `e-custom-analysis-3c-preset`，version `2 → 3` |
| 2 | 再点一次同预设 | 幂等 upsert 或新 id（允许其一，记下实际） | ✓ | 采用新 id，写库实际为 `custom-analysis-3c-04a23c29`；version `3 → 4`。但预览显示的是另一随机 id，见失败记录 F1 |

### L4 · 版本冲突（可选）

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 两标签同实体；A 应用 patch；B 用旧 version 确认 | B 见版本冲突提示，不静默覆盖 | ✓ | B 明确提示“拓扑版本冲突：请刷新页面后再应用”，数据库保持 A 的 version `5` |

### L5 · B+ 待确认计划中改拓扑（② 落地后必点）

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 发起运行至「待确认计划」 | 画布显示待确认 + run.flow_plan | ✓ | run `047df57c-83af-4bd7-8498-7de20e1ea307`；status/stage 均为 `waiting_scope_confirmation` |
| 2 | 不确认执行；点「跳过豆包」→ 确认应用 | 拓扑更新；**自动** refresh_flow_plan；仍 waiting；**未**开跑 | ✓ | 成功提示“已按新拓扑刷新待确认计划（未自动开跑）”；`analysis_task_id=null` |
| 3 | 看计划徽章 / run.message | 摘要反映无 doubao；status 仍 waiting_scope_confirmation | ✓ | `planned_platforms=[deepseek,kimi,hunyuan]`；豆包 step=`skipped`；status 仍 waiting |
| 4 | 再点「确认计划」 | 才进入执行 | ✓ | 点击“确认并执行”后进入 `fetching_answers`，生成 `analysis_task_id=e39f1387-a431-419f-a535-8aa0332fe66a`；消息仅列 DeepSeek/Kimi/元宝 |

## 总判

- [x] L1–L3 全 ✓ → **B 手点 PASS**
- [x] L5 ✓ → **B+ 手点 PASS**
- [ ] 任一项 ✗ → 记 failure 样例到本文件「失败记录」

## 失败记录

### F1 · 第二次新增分析节点时，预览 ID 与实际写库 ID 不一致 — **已修**

- 信号：预览显示 `custom-analysis-3c-26cf761a`，确认后数据库实际新增 `custom-analysis-3c-04a23c29`。
- 为何漏：preview 与 apply 都根据 `intent_id` 重新展开操作；碰撞后 ID 使用随机 UUID，因此两次展开得到不同 ID。
- 杀死步骤：
  1. expand 碰撞改用确定性序号 `custom-analysis-3c-preset-2`…
  2. 前端 apply **只提交 preview 返回的 `ops`**，禁止再次 expand intent
- 修复提交：见后续 `fix(workflow): align preview/apply ops and plan step parity`

### F2 · 服务端预览与画布计划步数差 1，运行节点一度仍显示 4/4 平台 — **已修**

- 信号：跳过豆包时服务端预览为 8 步，画布落地后为 9 步；加两个分析节点后服务端为 11 步，画布为 12 步。确认执行后锁定计划已无豆包，但“答案采集”节点短暂显示 `4/4 个平台`。
- 为何漏：后端 plan 不含 `lexicon` 步骤，前端本地 plan 包含；采集节点副标题读取平台开关数量，而不是锁定后的 run.flow_plan。
- 杀死步骤：
  1. 后端 `build_execution_plan_summary` 补 `lexicon` 步（在 extract 前）
  2. 画布 fetch 副标题 / 详情面板改读 executionPlan 计划平台数
- 修复提交：同上

## 回归与清理

- 后端定向回归：`36 passed`（flow topology / patch / resolver / flow-plan / intelligence-run API）。
- 前端静态检查：`npx tsc --noEmit` 通过。
- 浏览器 console warning/error：0。
- 测试运行在确认进入执行后立即取消，最终 run status=`cancelled`，避免继续消耗真实采集资源。
- 测试拓扑已恢复到开始前的空拓扑；持久化 version 因真实写入与清理递增至 `8`，页面重载后恢复四平台、无自定义节点。

## 结论

- 手点人：Codex  
- 日期：2026-07-21  
- 裁决：☑ 功能 PASS（带 F1/F2 两项非阻断缺陷） / ⬜ FAIL / ⬜ 部分  
