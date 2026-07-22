# Wave D 验收标准（开工锁定 · 开发后对照）

日期：2026-07-22  
状态：**PASS（2026-07-22 手测验收）**  
前置：Wave A/B/C **PASS**  
关联：`docs/plans/2026-07-21-blueprint-status-and-next.md`  
产品目标：主 Chat 成为 **compile / 配方建议** 的入口之一，与 Console 共用同一套 API，**不改 orchestrator**。  
实现提交：`aafb5d8`（入口）；逃生口双气泡修复见后续 commit。

---

## 0. 协议

同 Wave A–C：开工写本文件 → 开发 → 结束逐条勾选 → 全过才 PASS。

---

## 1. 范围

**做：**

| ID | 事项 |
|---|---|
| D1 | Chat 内**保守意图拦截**（短句/关键词/前缀）：编排改图 or 配方建议 |
| D2 | 命中后 **不发** `user_message` / 不启动主 agent 长跑；本地 user bubble + 预览卡 |
| D3 | 改图：`compile-nl` → 预览（summary/平台/mode）→ 用户确认 → `apply-patch` |
| D4 | 配方：`recommendations?intent=` → 可见理由 → 用户点击 → `apply-recipe` |
| D5 | 稳定解析 `entityId`（query / handoff / prop）；无 entity 友好提示 + deep-link |
| D6 | 预览卡「在生产线查看」→ `/amwaychina?entity_id=…&view=flow` |
| D7 | 普通分析话术仍走 WebSocket orchestrator |

**不做：**

- Orch / LangGraph / skill 表改造与巨石代码大拆  
- 自动套用、静默改默认拓扑、apply 后自动开跑  
- 完整画布内嵌 Chat / 跨 tab 实时同步  
- 节点级运行教训 annotation（原 C3）  
- 覆盖配方 Dialog  

---

## 2. 功能验收

| ID | 验收项 | 怎么验 | 结果 |
|---|---|---|---|
| F1 | 绑定 entity 的 Chat 发「跳过豆包」→ 出现编排预览卡，**无**主 agent 长跑 | 手测 | ✓ PASS |
| F2 | 预览卡展示变更摘要；点「应用变更」后拓扑 version+1，Console flow 刷新一致 | 手测 | ✓ PASS |
| F3 | 「推荐配方」类话术 → 建议列表含理由；点「套用」才替换 | 有 ≥2 配方 | ✓ PASS |
| F4 | 「帮我分析××品牌」等仍走 WS，不进编排短路 | 手测 | ✓ PASS |
| F5 | 无 entity 时不 crash；提示并提供去生产线/看板入口 | 去掉 entity 或旧会话 | ✓ PASS |
| F6 | 卡上「在生产线查看」打开 flow 视图且 entity 正确 | 手测 | ✓ PASS |
| F7 | 不自动套用、不自动开跑 | 刷新/仅预览 | ✓ PASS |

---

## 3. 工程验收

| ID | 验收项 | 结果 |
|---|---|---|
| E1 | 意图探测纯函数可测；相关自动化不红 | ✓ PASS（`check_chat_topology_intent` 7 passed） |
| E2 | `tsc --noEmit` 0 | ✓ PASS |
| E3 | `ChatPanel` 仅薄接线；逻辑在 `chatTopologyIntent` + 独立 Card | ✓ PASS |
| E4 | Canvas 壳不膨胀；无 orch 后端大改；无新 migration | ✓ PASS |
| E5 | 中文无损坏占位 | ✓ PASS |
| E6 | 非目标守住（见 §4） | ✓ PASS |

---

## 4. 非目标核对

| 项 | 结果 |
|---|---|
| 未改 orchestrator / websocket 主路径语义（除不调用） | ✓ |
| 未静默写拓扑 / 未自动开跑 | ✓ |
| 未实现 Orch 巨石代码大拆 | ✓ |

---

## 5. 总裁决

| 字段 | 填写 |
|---|---|
| 执行人 | 用户手测 + Codex 工程核对 |
| 完成日 | 2026-07-22 |
| 功能 F1–F7 | ✓ 7/7 |
| 工程 E1–E6 | ✓ 6/6 |
| 非目标 | ✓ 3/3 |
| **总裁决** | **PASS** |
| 证据 | 手测 OK；应用→Console 拓扑/9 步/豆包关闭一致 |

**PASS：** F∧E 全过 ∧ 非目标守住。

---

## 6. 非阻断观察

| 现象 | 说明 | 处理 |
|---|---|---|
| 「当作普通对话发送」短暂两条相同用户消息 | 拦截路径已 `addMessage`，逃生口再次 `addMessage`；刷新后只剩 WS 持久化一条 | **P2 已修**：逃生口 `forceNormal` 不再二次 `addMessage` |
| 首次进 Console 偶发 Failed to fetch | 刷新后稳定；完整应用→Console 流程结果正确 | 记档，不拦 PASS；疑似冷启动/首连，非 Wave D 功能回归 |

**Wave D 功能 Bug（阻断）：0。**
