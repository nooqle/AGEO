# Wave P — 记忆 / 校准加深（可见信号贯通）

日期：2026-07-23  
状态：**PASS（2026-07-23 统一手测）**  
实现：`552adf0` · 建议即时重载修复：`5943089`  
前置：Wave O PASS；Orch A+B 收口  
产品：把 events + lessons 注入 **推荐理由** 与 **compile 可见上下文**；**不**静默改图 / 不黑盒学习。

---

## 1. 范围

| ID | 事项 |
|---|---|
| P1 | recommend：lessons + 相关 event 信号 → 分数与中文 reasons |
| P2 | compile-nl：LLM user_payload 注入 `visible_memory`（system prompt 不动） |
| P3 | 响应 `calibration` 溯源块；FE 推荐/Chat 卡展示「校准依据」 |
| P4 | apply-patch event payload 加厚（ops 预览 / platforms_touched，无 migration） |

**不做：** auto-apply、改 system prompt 塞动态记忆、新表、Orch 语义。

---

## 2. 验收

| ID | 项 | 结果 |
|---|---|---|
| F1 | 断豆包 + 同结构候选 → reason 含教训对齐；**无需整页刷新** | **PASS**（~2.2s 自动更新） |
| F2 | recommend `calibration.auto_applied=false` + signals | **PASS** |
| F3 | compile-nl：visible_memory 进 user；system 不动 | **PASS** |
| F4 | 编排区校准依据一行 | **PASS** |
| E1 | 相关单测绿 | **PASS** |
| E2 | tsc / 中文无 `???` | **PASS** |

## 3. 总裁决

| **总裁决** | **PASS** |
|---|---|

统一清单：`2026-07-23-wave-pq-unified-acceptance.md`
