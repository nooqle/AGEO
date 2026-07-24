# Backlog：超大文件分拆进度

日期：2026-07-21（**2026-07-24 增补：圈层 FE Sprint GO**）
状态：**圈层 FE God-file 拆分 Sprint 已完成并验收**；其它巨石仍按里程碑排队

目标：把「稳定契约 / 纯算法 / 易变 UI」切开，降低改动冲突面，并让提示词/模块边界利于 LLM prompt cache。

---

## 1. 规模扫描（工作树量级）

| 文件 | 约行数 | 风险 | 状态 |
|---|---:|---|---|
| `app/workflow/orchestrator_node.py` | ~7058 | 主 Orch 巨石；改一处牵全身 | ⬜ 未开（独立里程碑） |
| `app/workflow/a5/association_circle.py` | ~6347 | A5 安利圈层内核 | ⬜ **另轨 · 未做** |
| `AmwayAssociationCircleDashboardViews.tsx` | **~16**（壳） | 圈层视图 | ✅ **FE Sprint GO**（`2026-07-24-circle-split-sprint-acceptance.md`） |
| `app/workflow/a5/canonical.py` | ~4453 | 分析内核 | ⬜ 不碰 |
| `app/workflow/nodes_a4.py` | ~4354 | 采集节点 | ⬜ 不碰（门控已外置） |
| `websocket_langgraph.py` | ~3160 | 通信层 | ⬜ 后续 |
| **`AmwayFlowCanvas.tsx`** | **~1547**（曾 ~2768→2590） | 生产线画布 | ✅ **P0 壳达标** |
| `BrandOntologyHome.tsx` | ~2747 | 首页 | ⬜ 后续 |
| `orchestrator_context_packets.py` | ~2164 | 上下文包 | ⬜ 与 cache harness 一并 |
| `amwaychina.py` | **~552**（曾 ~1.2k） | 圈层/词库/问题集 + include | ✅ **P1 完成** |

---

## 2. 已完成分拆（3c 相关）

| 抽出物 | 路径 | 从哪来 | 备注 |
|---|---|---|---|
| 拓扑 ops 纯函数 | `topology_patch.py` | — | B 管道 |
| NL 规则编译 | `topology_nl_compiler.py` | — | C1 |
| NL LLM 编译 | `topology_nl_llm.py` | — | C2；稳定 prompt 文件外置 |
| 稳定编译 prompt | `prompts/topology_ops_compiler.md` | — | **cache 前缀** |
| 执行计划投影（FE） | `lib/amwayFlowExecutionPlan.ts` | 早期 | 前后端对齐 |
| 预设列表 | `lib/amwayFlowTopologyPatch.ts` | Canvas | |
| **编排条 UI** | **`AmwayFlowTopologyPatchBar.tsx`** | **Canvas** | 预设 + NL + 预览确认 |
| types / constants | `amway-flow/types.ts`, `constants.ts` | Canvas | |
| 拓扑 IO | `amway-flow/topologyDoc.ts` | Canvas | parse/read/write + 平台开关 |
| 本地分析 | `amway-flow/analysis.ts` | Canvas | `runFlowAnalysis` |
| 端口/环校验 | `amway-flow/graphUtils.ts` | Canvas | |
| 节点卡片 | `amway-flow/AmwayFlowNodeCard.tsx` | Canvas | |
| 侧栏详情 | `amway-flow/AmwayFlowCanvasPanels.tsx` | Canvas | Detail + artifacts |

Canvas 行数：**~2768 → ~2590（编排条）→ ~1547（P0 全拆）**，已 **< 1800**。

---

## 3. 建议下一拆（优先级）

### P0 — `AmwayFlowCanvas.tsx` — ✅ 已完成（2026-07-21）

壳内保留：ReactFlow 状态、运行计划条、与 PatchBar/Panels 接线。
目录：`frontend/src/components/dashboard/amway-flow/`

### P1 — `amwaychina.py` 路由分包 — ✅ 已完成（2026-07-21）

| 模块 | 约行 | 职责 |
|---|---:|---|
| `api/v1/amwaychina_common.py` | ~118 | 鉴权 / UUID / iso / projection body |
| `api/v1/amwaychina_flow_topology.py` | ~373 | flow-plan、GET/PUT topology、preview/apply/compile-nl |
| `api/v1/amwaychina_flow_run.py` | ~392 | flow-nodes/run、flow-branch/run |
| `amwaychina.py` | ~552 | 圈层/词库/问题集 + `include_router`；测试仍可 `from amwaychina import _normalize_topology` |

### P2 — 巨石（单独里程碑，勿与 3c 混做）

1. `orchestrator_node.py`：按 tool dispatch / confirm / context 切模块
2. `nodes_a4.py`：gate 已在 resolver；可继续抽 platform client 装配
3. `AmwayAssociationCircleDashboardViews.tsx`：按 map / report 分文件 → ✅ **FE 已完成**（见下节勾选；BE 圈层内核仍另轨）

---

## 4. 与 prompt cache 的对齐

| 原则 | 在拆分中的体现 |
|---|---|
| 稳定前缀独立文件 | `prompts/topology_ops_compiler.md` 少改 |
| 易变内容不进 system | topology digest 只在 user JSON 尾部（`topology_nl_llm.py`） |
| 算法与 IO 分离 | ops 应用不依赖 API 层 |
| 避免 God 文件塞动态字符串 | UI 中文案进小组件；引擎 reason 后续可 code 化 |

---

## 5. 进度勾选

- [x] 扫描并登记超大文件
- [x] 3c 编排条从 Canvas 拆出
- [x] NL 规则 / LLM 编译独立模块 + 稳定 prompt
- [x] Canvas P0：types/constants/topologyDoc/analysis/graphUtils/NodeCard/Panels
- [x] amwaychina 路由分包（P1）
- [x] **P1.5** 配方条+编排条合并为单一 Orchestration 面板（`AmwayFlowOrchestrationPanel`）
- [x] orchestrator_node 拆分设计稿（P2）→ `docs/plans/2026-07-22-orchestrator-p2-split-design.md`
- [x] orchestrator_node **第一刀**（纯函数包）→ Wave F（~-257 行）
- [x] orchestrator_node **第二刀**（history/workflow/knowledge）→ Wave G（再 ~-566 行）
- [x] orchestrator_node **第三刀**（ontology 情报回复 / seed / prompt_bundle）→ Wave H（再 ~-923）
- [x] orchestrator_node **第四刀（谨慎）** → Wave I（~-246）
- [x] orchestrator_node **第五刀（谨慎）** → Wave J（~-327）
- [x] orchestrator_node **第六刀（谨慎）** → Wave K（~-310）
- [x] orchestrator_node **第七刀（谨慎）** → Wave L（~-425）
- [x] orchestrator_node **第八刀** → Wave M（~-571）
- [x] orchestrator_node **阶段 B 收口** → Wave N prompt_assembly / tool_gate_command（~-477；累计 ~-4103）
- [x] **阶段 A+B 完成** — 见 `2026-07-22-orch-p2-split-enough-criteria.md`
- [ ] 阶段 C 薄壳（async 路由）→ **另立项，不阻塞产品主线**
- [x] 圈层 FE **第一刀** pure helpers → `amway-circle/*`（`2026-07-23-circle-split-knife1-acceptance.md`）
- [x] 圈层 FE **刀 2–6** orbit / map evidence / map UI / report pure / report UI（+ export 与面板同拆）
- [x] 圈层 FE **Sprint 收口验收 GO** → `docs/plans/2026-07-24-circle-split-sprint-acceptance.md`（终点实现 `c4b01fa`；壳 ~16 行）
- [ ] 圈层 BE `association_circle.py` 另轨（**未做**）

**与总路线对齐：** 见 `docs/plans/2026-07-21-blueprint-status-and-next.md`。

**下次继续（建议，未启动）：** 后端 `association_circle.py` 另轨；Orch 阶段 C / 平台化 2.4 后置。不做黑盒自学。
