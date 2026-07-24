# 圈层 FE God-file 拆分 Sprint — 验收收口

日期：2026-07-24
分支：`codex/amwaychina-mainline`
状态：**Sprint GO · 前端 association-circle 拆分完成并验收**
范围：**仅 FE** — `AmwayAssociationCircleDashboardViews.tsx` + `frontend/src/components/dashboard/amway-circle/*`

**非目标（本 Sprint 明确不做）：**

- 后端 `app/workflow/a5/association_circle.py` 拆分
- 平台化 2.4
- 部署 / demo 发布
- 产品行为、文案、质量门、导出门槛变更

---

## 1. 范围与目标

| 项 | 内容 |
|---|---|
| 目标 | 将圈层 Dashboard Views God 文件拆为 `amway-circle` 包；壳文件保留历史公开 import 路径 |
| 约束 | 零产品行为变更；不改外部消费者 import；UTF-8 中文完好 |
| Sprint Done | 壳为薄 re-export；纯函数 + Map/Report UI 外提；静态 + 独立运行时/导出验收通过 |

---

## 2. 提交链（本 Sprint）

| 顺序 | SHA（短） | 说明 |
|---|---|---|
| 刀 1 | `c5a1d07` | pure map/projection helpers → `amway-circle/*` |
| 刀 2 | `304a1b4` | orbit layout pure geometry → `orbitLayout.ts` |
| 刀 3 | `7606677` | map evidence / insight pure → `evidenceHelpers` + `nodeInsightCopy` |
| 刀 4a | `4e2d777` | orbit map chrome + visual helpers |
| 刀 4b | `71040f5` | CommercialOrbitMap + OrbitNodeInsightPanel |
| 刀 4c | `ed49aa7` | CommercialOrbitView composition |
| 刀 5 | `3b52009` | report pure narrative / strategy / copy |
| 刀 6a | `deccb81` | reportSections UI |
| 刀 6b | `c4b01fa` | AssociationReportPanel + Loading/InfoPill；export 与面板同拆（接线需要） |

**实现终点 HEAD（代码）：** `c4b01fa`

壳文件：`AmwayAssociationCircleDashboardViews.tsx` ≈ **16 行**兼容 re-export。

---

## 3. 验收证据

### 3.1 静态（工程）

| ID | 项 | 结果 |
|---|---|---|
| A1 | 外部 import 路径不变（Dashboard / Console / FlowCanvas 仍从 Views 壳导入） | ✓ |
| A2 | `npx tsc --noEmit -p tsconfig.json` | ✓ |
| A3 | 改动面无 `???` / 替换字符；中文样例完好 | ✓ |
| A4 | 单一定义（无残留重复组件/纯函数定义） | ✓ |
| A5 | 相关 commit `git show --check` | ✓ |

### 3.2 运行时浏览器（独立验收 · Codex）

| ID | 项 | 结果 |
|---|---|---|
| F1 | 圈层地图概览打开、分组正常 | ✓ |
| F1b | 风险模式切换 | ✓ |
| F1c | 稳定轨过滤 | ✓ |
| F1d | 节点证据侧板 | ✓ |
| F2 | 完整报告打开 | ✓ |
| F2x | 页面无新 console error | ✓ |

### 3.3 导出（独立验收 · Codex）

| ID | 项 | 结果 |
|---|---|---|
| F3 | 点击「导出报告」生成 HTML | ✓ |
| F3 证据 | `C:\Users\Administrator\Downloads\安利-brand-association-report (12).html`，**78027** bytes | ✓ |
| F3 内容 | 合法 doctype/title；含核心判断、本周期基线说明、质量门章节 | ✓ |

---

## 4. 未覆盖 / 明确不做

| 项 | 说明 |
|---|---|
| 后端 `association_circle.py` 拆分 | **未做**；另轨里程碑 |
| 平台化 2.4 | **未做** |
| 部署 / 线上验证 | **未做、未声称完成** |
| 产品行为增量 | **无**；本 Sprint 为纯工程债 |
| 全量回归矩阵外场景 | 以独立手测清单为证；非自动化 E2E 全覆盖 |

---

## 5. 蓝图 delta（工程债）

| 变化 | 说明 |
|---|---|
| 工程债减少 | 圈层 FE God 文件由 ~6k 行降至 16 行壳 + 模块化 `amway-circle` 包 |
| 可维护性 | map / report / pure helpers 边界清晰，后续改 UI 与纯逻辑冲突面下降 |
| 产品能力 | **无**新功能；公开路径与行为保持 |
| 后端巨石 | **未变**；`association_circle.py` 仍待另轨 |

---

## 6. Go / No-Go

| 裁决 | **GO** |
|---|---|
| 含义 | 前端 association-circle God-file 拆分 Sprint **关闭**；代码与独立静态/浏览器/导出验收一致 |
| 部署 | **不**视为部署完成；不触发 demo 发布判定 |
| 下一 Sprint（建议，不启动） | ① 后端 `association_circle.py` 拆分另轨；② Orch 阶段 C / 平台化 2.4 后置；③ 可选：将外部 import 逐步迁到 `amway-circle` 包（非必须） |

---

## 7. 文档索引

- 进度 backlog：`docs/plans/2026-07-21-god-file-split-backlog.md`
- 蓝图对照：`docs/plans/2026-07-21-blueprint-status-and-next.md`
- 刀 1 工程记录：`docs/plans/2026-07-23-circle-split-knife1-acceptance.md`（手测已由本 Sprint 收口覆盖）
