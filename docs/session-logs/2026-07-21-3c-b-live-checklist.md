# 3c-B Live 手点清单（①）

日期：2026-07-21  
前置：本地后端 + 前端已起；amwaychina 实体有 manage 权限；画布在「品牌生产线」视图。

对照实现：`编排建议（试验）` 条（`AmwayFlowCanvas`）+  
`POST .../flow-topology/preview-patch|apply-patch`

## 环境

| 项 | 填写 |
|---|---|
| 前端 URL | `http://localhost:3000/...` |
| 实体 / 中心词 | |
| 操作人 | |
| 开始前 topology version（Network GET flow-topology） | |

## 用例矩阵

### L1 · 跳过豆包（无在途 run）

| 步 | 操作 | 期望 | 结果 (✓/✗) | 备注 |
|---|---|---|---|---|
| 1 | 点「跳过豆包」 | 出现变更摘要，含断开 `e-fetch-doubao` 或可读文案；计划平台无 doubao | | |
| 2 | 点「确认应用」 | 画布豆包平台边视觉断开/灰；localStorage 与 GET topology 一致 | | |
| 3 | 再 GET topology | `removedEdgeIds` 含 `e-fetch-doubao`；version +1 | | |
| 4 | **未**点确认开跑 | 无新的 intelligence run 自动 dispatch | | |

### L2 · 恢复全部平台

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 在 L1 后点「恢复全部平台」→ 预览 → 确认 | `removedEdgeIds` 去掉平台边；四平台可计划 | | |

### L3 · 加图谱分析节点

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 点「加图谱分析节点」→ 确认 | 出现 analysis 自定义节点 + projection→节点边 | | |
| 2 | 再点一次同预设 | 幂等 upsert 或新 id（允许其一，记下实际） | | |

### L4 · 版本冲突（可选）

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 两标签同实体；A 应用 patch；B 用旧 version 确认 | B 见版本冲突提示，不静默覆盖 | | |

### L5 · B+ 待确认计划中改拓扑（② 落地后必点）

| 步 | 操作 | 期望 | 结果 | 备注 |
|---|---|---|---|---|
| 1 | 发起运行至「待确认计划」 | 画布显示待确认 + run.flow_plan | | |
| 2 | 不确认执行；点「跳过豆包」→ 确认应用 | 拓扑更新；**自动** refresh_flow_plan；仍 waiting；**未**开跑 | | |
| 3 | 看计划徽章 / run.message | 摘要反映无 doubao；status 仍 waiting_scope_confirmation | | |
| 4 | 再点「确认计划」 | 才进入执行 | | |

## 总判

- [ ] L1–L3 全 ✓ → **B 手点 PASS**
- [ ] L5 ✓ → **B+ 手点 PASS**
- [ ] 任一项 ✗ → 记 failure 样例到本文件「失败记录」

## 失败记录

（信号 / 为何漏 / 杀死步骤）

## 结论

- 手点人：  
- 日期：  
- 裁决：⬜ PASS / ⬜ FAIL / ⬜ 部分  
