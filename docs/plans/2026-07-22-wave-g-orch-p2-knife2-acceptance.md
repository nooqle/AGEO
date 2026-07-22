# Wave G — Orch P2 第二刀验收

日期：2026-07-22  
状态：**实现完成 · 待统一确认 PASS**  
前置：Wave F PASS

---

## 1. 范围（已做）

| 模块 | 内容 |
|---|---|
| `history_query.py` | 历史回答/延续/报告 follow-up/question-only 判定 |
| `workflow_progress.py` | `WORKFLOW_STEPS` + 步骤完成/跳过/失败匹配 |
| `knowledge_format.py` | 知识结果格式化 |
| re-export | `orchestrator_node` 兼容旧 import |

**不做：** effects 大搬家、薄壳 &lt;400、改调度语义、新功能。

---

## 2. 验收结果

| ID | 项 | 结果 |
|---|---|---|
| A1 | 新模块可 import | ✓ |
| A2 | node 行数再降 ≥200 | ✓ **7434 → 6868**（约 **-566**） |
| A3 | knife1+2 + orch 相关测试 | ✓ **38+ passed**（含 knife2 断言） |
| A4 | 无 migration / API 破坏 | ✓ |

累计两刀：约 **7692 → 6868**（约 **-824 行**）。

---

## 3. 总裁决

| 字段 | 填写 |
|---|---|
| **总裁决** | **待用户确认 PASS** |
