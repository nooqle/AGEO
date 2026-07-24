# 圈层拆分第一刀 — pure helpers package（零行为）

日期：2026-07-23  
状态：**工程完成 · 待手测冒烟（圈层地图/报告）**  
范围：FE only（`AmwayAssociationCircleDashboardViews.tsx`）  
**非目标：** a5/association_circle.py、平台化 2.4、行为变更  

---

## 1. 做了什么

新建目录 `frontend/src/components/dashboard/amway-circle/`：

| 文件 | 职责 |
|---|---|
| `types.ts` | map group / filter / orbit band 类型 |
| `constants.ts` | `DEFAULT_CENTER_TERMS`、`platformLabel` |
| `nodeMetrics.ts` | 证据数/平台数/风险节点判定等纯函数 |
| `mapGroups.ts` | `buildAssociationMapGroups` / `classifyAssociationNode` |
| `projection.ts` | `buildAssociationProjection` / `normalizeCenterTerms` / sample counts |
| `index.ts` | 包出口 |

壳文件 `AmwayAssociationCircleDashboardViews.tsx`：

- 从 `./amway-circle` 导入上述纯函数  
- **再导出** `buildAssociationMapGroups` / `buildAssociationProjection` / `normalizeCenterTerms` / `sampleAnswerCount`（外部 import 路径不变）  

行数：Views **~6203 → ~5915**（约 **-290**）；逻辑迁出到 ~400 行包内。

---

## 2. 验收

| ID | 项 | 结果 |
|---|---|---|
| A1 | 外部 import 路径不变（Dashboard / Console / FlowCanvas） | ✓ |
| A2 | tsc 相关面通过 | ✓ |
| A3 | 中文无 `???` | ✓ |
| F1 | 手测：圈层地图打开 / 节点分组正常 | ⬜ |
| F2 | 手测：报告面板 / 投影 empty 态正常 | ⬜ |

| **总裁决** | **工程 PASS · 冒烟手测后可标刀 1 完成** |
|---|---|

---

## 3. 下一刀候选

1. **orbit layout 纯几何**（`orbitScreenPosition` / `buildCommercialOrbitEntries`…）→ `orbitLayout.ts`  
2. **CommercialOrbitMap 组件** 外提  
3. **AssociationReportPanel** 外提  
4. 后端 `a5/association_circle.py` 另轨（勿与 FE 刀混 PR）  
