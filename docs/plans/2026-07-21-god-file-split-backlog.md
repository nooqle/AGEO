# Backlog：超大文件分拆进度

日期：2026-07-21  
状态：**进行中**（本批只完成与 3c 触达相关的拆分；其余登记后续）

目标：把「稳定契约 / 纯算法 / 易变 UI」切开，降低改动冲突面，并让提示词/模块边界利于 LLM prompt cache。

---

## 1. 规模扫描（工作树量级）

| 文件 | 约行数 | 风险 | 状态 |
|---|---:|---|---|
| `app/workflow/orchestrator_node.py` | ~7058 | 主 Orch 巨石；改一处牵全身 | ⬜ 未开（独立里程碑） |
| `app/workflow/a5/association_circle.py` | ~6347 | A5 安利圈层内核 | ⬜ 不碰 3c |
| `AmwayAssociationCircleDashboardViews.tsx` | ~5941 | 圈层视图 God | ⬜ 后续 |
| `app/workflow/a5/canonical.py` | ~4453 | 分析内核 | ⬜ 不碰 |
| `app/workflow/nodes_a4.py` | ~4354 | 采集节点 | ⬜ 不碰（门控已外置） |
| `websocket_langgraph.py` | ~3160 | 通信层 | ⬜ 后续 |
| **`AmwayFlowCanvas.tsx`** | **~2590**（曾 ~2768） | 生产线画布 | 🔄 **部分完成** |
| `BrandOntologyHome.tsx` | ~2747 | 首页 | ⬜ 后续 |
| `orchestrator_context_packets.py` | ~2164 | 上下文包 | ⬜ 与 cache harness 一并 |
| `amwaychina.py` | ~1.2k+ | API 路由 | 🔄 逻辑已外置 topology_* |

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

Canvas 行数：约 **2768 → 2590**（编排条移出后）。

---

## 3. 建议下一拆（优先级）

### P0 — 继续拆 `AmwayFlowCanvas.tsx`（仍偏大）

| 块 | 建议目标文件 | 内容 |
|---|---|---|
| 节点卡片 / 样式 | `amway-flow/AmwayFlowNodeCard.tsx` | `AmwayFlowNodeCard` + status class helpers |
| 侧栏详情 | `amway-flow/AmwayFlowCanvasPanels.tsx` | `CustomNodeDetail` / `FlowNodeDetail` / artifacts |
| 拓扑 IO | `lib/amwayFlowTopologyDoc.ts` | parse/read/write/empty topology |
| 分析本地 fallback | `lib/amwayFlowAnalysis.ts` | `runFlowAnalysis`（已有部分逻辑） |

验收：Canvas 壳 **< 1800 行**，只保留 ReactFlow 图状态与连线。

### P1 — `amwaychina.py` 路由分包

| 模块 | 职责 |
|---|---|
| `api/v1/amwaychina_flow_topology.py` | GET/PUT topology、preview/apply/compile-nl、flow-plan |
| `api/v1/amwaychina_flow_run.py` | flow-nodes/run、flow-branch/run |
| `amwaychina.py` | 实体词库等其它 console API + include_router |

### P2 — 巨石（单独里程碑，勿与 3c 混做）

1. `orchestrator_node.py`：按 tool dispatch / confirm / context 切模块  
2. `nodes_a4.py`：gate 已在 resolver；可继续抽 platform client 装配  
3. `AmwayAssociationCircleDashboardViews.tsx`：按 map / lexicon / report 分文件  

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
- [ ] Canvas panels / node card 再拆（P0）  
- [ ] amwaychina 路由分包（P1）  
- [ ] orchestrator_node 拆分设计稿（P2）  

**下次继续**：从 Canvas P0 三表（NodeCard / Panels / topologyDoc）开刀。  
