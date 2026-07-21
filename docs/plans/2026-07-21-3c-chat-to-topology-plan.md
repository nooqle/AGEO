# Plan：3c chat-to-topology（A 定案 → B 竖切）

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
定案：**先 A 后 B**（用户确认）

| 定案 | 含义 |
|---|---|
| A | 本 Plan：范围、非目标、任务板、与 3b/M3 缝合点写死 |
| B | **无 LLM** 的确定性拓扑 patch：preview → 确认 → 写库；预设意图映射 ops |
| C（后续） | 自然语言 → Orchestrator 生成 ops/diff（接 B 管道） |
| 模板库 | **3c 后半** 或独立里程碑；B 不做 |

前置：`3b-1` / `3b-2` 约束模式工程完成（含 review P0–P1 + P1-3 前端半边）。  
对照蓝图：`docs/specta-agentic-infrastructure-blueprint-2026-07-21.md` §3c。

---

## 1. 目标与非目标

### 目标（本 Plan 覆盖）

1. **管道先于聪明**：先打通 `意图(可固定) → 拓扑 ops → 校验 → preview → 用户确认 → 落库`，不依赖 LLM。  
2. **单一写路径**：落库仍走 `validate_topology_document` + `expected_version` 乐观锁（与 PUT 同源）。  
3. **图确认可演进到 M3**：B 只确认「拓扑变更」；后续「变更后开跑」复用 `waiting_scope_confirmation` / `confirm_run`，不另造闸。  
4. **为 C 预留契约**：LLM 只允许产出 **ops 列表**（或 intent_id），不得直接写 DB / 绕过校验。

### 非目标

- 自然语言理解 / Orch 动态调度（C）  
- 拓扑模板库与意图相似度推荐  
- 通用 DAG 引擎重写  
- 分支运行总时限后台化（已拍板 P2）  
- 改动 A4 采集内核  

---

## 2. 架构切片

```
[B] Preset intent_id  ──┐
                        ├──► apply_topology_ops(base, ops)
[C 未来] NL → Orch ─────┘              │
                                       ▼
                         validate_topology_document
                                       │
                    ┌──────────────────┼──────────────────┐
                    ▼                  ▼                  ▼
              preview (只读)     apply (写库+version)   plan summary
                    │                  │
                    └──── 画布 diff 预览 / 确认 ────────┘
```

### 命根子与纪律（继承 3b + 评审给 3c 的三条）

| # | 纪律 | B 落点 |
|---|---|---|
| 1 | 注册表驱动，勿再硬编码工具表叠床架屋 | B 不碰 Orch tool 表；ops 只改 topology 文档 |
| 2 | 图确认复用 M3 | B：拓扑 apply 确认；执行确认仍走现有 flow_plan 闸（后续缝） |
| 3 | diff 必须服务端校验 | preview/apply 均 `validate_topology_document` |
| 4 | 契约领域无关 | ops 用 edge_id / node type，不用安利业务词进契约层 |

---

## 3. Ops 契约（B 冻结 v1）

机器可读、幂等友好、可测：

| op | 字段 | 语义 |
|---|---|---|
| `disable_platform` | `platform` | 将 `e-fetch-{platform}` 加入 `removedEdgeIds` |
| `enable_platform` | `platform` | 从 `removedEdgeIds` 去掉该平台边 |
| `remove_builtin_edge` | `edge_id` | 断开内置边（须 ∈ BUILTIN_EDGE_IDS） |
| `restore_builtin_edge` | `edge_id` | 恢复内置边 |
| `add_custom_node` | `node` `{id,type,position,config}` | 追加自定义节点（type∈analysis\|content） |
| `remove_custom_node` | `node_id` | 删节点及其关联 customEdges |
| `add_custom_edge` | `edge` `{id,source,target}` | 追加自定义边 |
| `remove_custom_edge` | `edge_id` | 删自定义边 |
| `patch_node_config` | `node_id`, `config` (merge) | 合并 config（不整表替换） |

规则：

- 未知 op → 400  
- 应用后 **整图** 过 `validate_topology_document`（端点/自环/DAG/数量/config 大小）  
- 节点数仍 ≤20，边 ≤60  
- `add_*` 遇已存在 id：节点/边 **幂等跳过或合并**（B 定：**同 id 覆盖 position/config 或 edge endpoints**，写进测试）

### 预设意图（B  deterministic，无 LLM）

| intent_id | 中文 | 展开 ops（示意） |
|---|---|---|
| `skip_doubao` | 跳过豆包采集 | `disable_platform doubao` |
| `enable_all_platforms` | 恢复全部平台连线 | 对四个平台 `enable_platform` |
| `add_projection_analysis` | 在图谱后挂一个分析节点 | `add_custom_node` + `add_custom_edge` projection→node |

C 阶段：Orch 只输出 `intent_id` 或 `ops[]`，同一管道。

---

## 4. API（B）

均在 amwaychina 路由，auth 与 `flow-topology` 一致（写操作 manage）。

### `POST /entities/{entity_id}/flow-topology/preview-patch`

Request:

```json
{
  "intent_id": "skip_doubao",
  "ops": null,
  "base_version": 3
}
```

- `intent_id` 与 `ops` 至少其一；同时给时 **ops 优先**（或 intent 展开后再 append ops——B 定：**仅允许其一**，同时给 400）  
- 读当前拓扑（无行则 empty）  
- 若 `base_version` 与当前 `row.version` 不一致 → **409**（preview 也校验，防基于过期图做决策）  
- 返回：

```json
{
  "base": { "topology": {...}, "version": 3 },
  "proposed": { "topology": {...} },
  "ops": [ ... ],
  "summary": { "text": "...", "removed_edge_ids_added": [], "nodes_added": [], ... },
  "plan": { "steps": ..., "planned_platforms": ... }
}
```

不写库。

### `POST /entities/{entity_id}/flow-topology/apply-patch`

Request 同 preview，且 **必须** `expected_version`（= 当前 version，乐观锁）。

- 与 preview 同一 apply 路径  
- 校验通过后写入 `FlowTopologyRecord`，version+1  
- 返回 `{ topology, version, plan, ops, summary }`  

实现上复用 PUT 的 normalize + version 逻辑，避免第二套持久化。

---

## 5. 前端（B 最小）

| 项 | 说明 |
|---|---|
| API client | `previewAmwayFlowTopologyPatch` / `applyAmwayFlowTopologyPatch` |
| UI | 生产线画布工具区增加 **「编排建议（试验）」** 条：预设按钮 → preview 摘要 → 确认应用 |
| 应用成功 | `setTopology` + 刷新 version；**dirty=false** 或与现有 version 同步（对齐 P1-3） |
| 不做 | 画布内自由 chat 输入框（留给 C）；不接 WebSocket Orch |

视觉：跟 Specta tokens（`--brand-*`、纸面中性），无 AI 紫渐变。

---

## 6. 与 M3 / 3b-2 的缝合点

| 阶段 | 行为 |
|---|---|
| B（本切片） | 只改拓扑；用户仍用现有「开始采集 / 待确认计划」跑约束模式 |
| B+（已落地） | apply 成功且 run 在待确认闸 → 调 `onRefreshFlowPlan` → `user_action_type=refresh_flow_plan`；**不 dispatch** |
| C | NL → ops → preview 画在画布（高亮 diff）→ 确认 apply → 若用户要跑，进 M3 `waiting_scope_confirmation` |

**禁止**：apply-patch 内部直接 `create_run` 并跳过确认。

---

## 7. 任务板

| ID | 任务 | 状态 | 完成定义 |
|---|---|---|---|
| **A0** | 本 Plan 落地 | ✅ | 甲：A→B 写死 |
| **B1** | `apply_topology_ops` + presets + summary | ✅ | `topology_patch.py` + `test_topology_patch.py` |
| **B2** | preview-patch / apply-patch API | ✅ | `amwaychina.py` 两 POST |
| **B3** | 前端 API + 试验条 preview/confirm | ✅ | `api.ts` + 画布「编排建议（试验）」 |
| **B4** | 套件入口 / session-log 证据 | ✅ | `run_3b1_suite` 纳入 patch 测试 |
| **B-live** | Live 手点清单 | ✅ 清单 | `docs/session-logs/2026-07-21-3c-b-live-checklist.md`（结果待人填） |
| **B+** | apply 后 M3 `refresh_flow_plan`，不 dispatch | ✅ | 画布 apply 成功且 `isAwaitingPlanConfirm` → `onRefreshFlowPlan` |
| **C0** | NL→ops（另开 Plan） | ⏭ | 不在 B |

---

## 8. 验收（B）

1. `skip_doubao` preview：`proposed.removedEdgeIds` 含 `e-fetch-doubao`，plan 平台列表无 doubao。  
2. apply 后 GET topology 与 proposed 一致，version+1。  
3. 错误 ops（自环边）preview/apply 均 400。  
4. 错误 `expected_version` apply 409。  
5. 前端确认后画布反映断开/新节点，无静默丢 version。  

**非验收**：chat 里说中文自动改图；模板推荐。

---

## 9. 风险

| 风险 | 对策 |
|---|---|
| 与 canvas 本地 dirty 竞态 | apply 成功强制后端 topology + refresh version；冲突 409 提示刷新 |
| God component 再膨胀 | 试验条逻辑尽量 `lib/amwayFlowTopologyPatch.ts` + 小组件；能抽则抽 |
| C 时 ops 爆炸 | v1 op 集合冻结；新 op 必须改契约+测试 |

---

## 10. 本会话执行顺序

1. ✅ A：本 Plan  
2. → B1–B4 实现与验证  
3. 停在 B 可验收；C 等下一指令  
