# Wave O — 节点运行教训 annotation v0（蓝图主线）

日期：2026-07-22  
状态：**PASS（2026-07-22 用户手测 3/3）**  
基线提交：`bee1abc`  
前置：Wave A–D / 完善轨 / Orch 阶段 A+B 收口  
产品：可见校准，**不**静默改默认拓扑。

---

## 1. 范围

**做：**

| ID | 事项 |
|---|---|
| O1 | 后端从 topology + 最近编排事件 + 最近 run.flow_plan 合成 lessons |
| O2 | `GET …/flow-lessons` 返回 node_id + 中文 headline + source |
| O3 | 生产线画布：节点卡片展示 lesson（可见） |
| O4 | 编排区「运行教训」列表（可折叠） |
| O5 | 单测：合成逻辑 DB-free |

**不做：** 自动改图、黑盒学习、新 migration、跨会话强制写库教训表。

---

## 2. 实现要点

| 层 | 路径 |
|---|---|
| 合成 | `app/services/flow_run_lesson_service.py` |
| API | `GET /amwaychina/entities/{id}/flow-lessons` |
| FE API | `api.listAmwayFlowLessons` |
| 节点卡 | `AmwayFlowNodeCard` → `教训：…` |
| 编排区 | `AmwayFlowOrchestrationPanel` → 「运行教训」 |
| 单测 | `tests/test_flow_run_lesson_service.py` |

契约：每条 lesson 含 `id/node_id/kind/headline/source/dismissible`；payload `engine=visible_v0`、`auto_applied=false`。

---

## 3. 验收

### 3.1 工程

| ID | 项 | 结果 |
|---|---|---|
| E1 | 单测绿 | ✓ `test_flow_run_lesson_service` 3 passed |
| E2 | tsc 相关面 0 | ✓ |
| E3 | 中文无损坏 | ✓ 扫描 + 豆包文案 |

### 3.2 手测（用户，基于 `bee1abc`，3/3）

| ID | 项 | 结果 | 实测表现 |
|---|---|---|---|
| F1 | 断豆包边后 lessons 可见 | **PASS** | 豆包节点显示「当前生产线未连接豆包…」；答案采集节点及编排区显示跳过豆包（拓扑门控） |
| F2 | 无 run 空列表不炸 | **PASS** | 可空列表；无阻断 Console error |
| F3 | 不自动改图 | **PASS** | 查询教训未生成拓扑记录、编排事件或 run；`auto_applied=false` |

### 3.3 非阻断观察

| 项 | 说明 | 裁决 |
|---|---|---|
| 教训刷新延迟 | 断边后约数秒才出现，非瞬时；最终节点与编排区均正确 | **不判 FAIL**（本波未规定响应时限）；记为后续体验优化 |

---

## 4. 总裁决

| **总裁决** | **PASS** |
|---|---|

**非目标再确认：** 不静默改图；不写学习表；阶段 C Orch 薄壳不在本波。

**可选后续（非本波阻塞）：** 教训列表/节点 annotation 的即时刷新（依赖 deps / 乐观本地合成 / 断边后主动 reload）。
