# Wave P — 记忆 / 校准加深（可见信号贯通）

日期：2026-07-23  
状态：**工程 PASS，待统一手测**  
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

## 2. 验收（工程 + 统一手测时勾）

| ID | 项 | 结果 |
|---|---|---|
| F1 | 当前图跳过豆包 + 候选同结构 → reason 含教训对齐类文案 | ✓ 单测；手测见统一清单 |
| F2 | recommend 响应 `calibration.auto_applied=false` 且含 signals | ✓ 单测 payload |
| F3 | compile-nl：visible_memory 进 user；system 不动 | ✓ 代码契约 |
| F4 | 编排区 / Chat 配方卡可见校准依据一行 | ✓ 代码挂点 |
| E1 | 相关单测绿 | ✓ |
| E2 | tsc / 中文无 `???` | ✓（工程侧） |

## 3. 总裁决

| **总裁决** | **工程 PASS · 统一手测见 `2026-07-23-wave-pq-unified-acceptance.md`** |
