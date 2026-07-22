# Wave O — 节点运行教训 annotation v0（蓝图主线）

日期：2026-07-22  
状态：**工程 PASS，待手测**  
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

| ID | 项 | 结果 |
|---|---|---|
| F1 | 断豆包边后 lessons 含 platform-doubao 跳过类文案 | ✓ 单测 + 合成 |
| F2 | 画布节点可见 lesson | ✓ 代码挂点（手测确认） |
| F3 | 无 run/无事件时不报错，列表可空 | ✓ 单测 empty |
| E1 | 单测绿 | ✓ `test_flow_run_lesson_service` 3 passed |
| E2 | tsc 相关面 0 | ✓ |
| E3 | 中文无损坏 | ✓ 扫描 + 豆包文案 |

## 4. 总裁决

| **总裁决** | **工程 PASS，待用户手测 F2 画布/编排区** |
|---|---|

**非目标再确认：** 不静默改图；不写学习表；阶段 C Orch 薄壳不在本波。
