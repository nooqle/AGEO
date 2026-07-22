# Wave N — Orch P2 阶段 B 收口验收

日期：2026-07-22  
状态：**实现完成 · 待确认 PASS 后回蓝图主线**  
目标：**完成阶段 B（中层组装外提）**，壳内只剩 async 路由 / effects。

---

## 1. 本波外提

| 模块 | 内容 |
|---|---|
| `prompt_assembly_builder.py` | `build_orchestrator_prompt_assembly` / bundle / system_prompt |
| `tool_gate_command.py` | `_build_tool_gate_block_command` |
| `ontology_action_plan.py` | `_build_ontology_action_plan` |

---

## 2. 结果

| ID | 项 | 结果 |
|---|---|---|
| A1 | 中层组装外提 + 再导出 | ✓ |
| A2 | 依赖可 import；prompt assembly 可构建 | ✓ |
| A3 | 钉死单测 + orch 回归 | ✓ **221 passed**（2 既有 Dashboard 文案失败） |
| A4 | 行数 | ✓ **4066 → 3589**（约 **-477**） |

累计拆分：约 **7692 → 3589**（约 **-4103 / ~53%**）。

### 阶段 B 完成定义核对

| 定义 | 状态 |
|---|---|
| gate decision / messages / prompt assembly 已外提 | ✓（含本波） |
| 壳内主要剩 async 路由与 tool handle | ✓ |
| 入口稳定 | ✓ |
| 阶段 C 薄壳未做 | 明确后置 |

---

## 3. 壳内剩余（阶段 C / 不本波）

- `orchestrator_node` 主循环  
- `_handle_tool_call`  
- 各类 `_route_*_without_llm` / force confirm / hydrate  

→ **独立薄壳里程碑**，不阻塞回蓝图主线。

---

## 4. 总裁决

| **总裁决** | **待用户确认 PASS → 回蓝图主线** |
