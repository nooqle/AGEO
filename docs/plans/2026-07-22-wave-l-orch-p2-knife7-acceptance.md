# Wave L — Orch P2 第七刀验收 + 功能影响复查

日期：2026-07-22  
状态：**实现完成 · 待确认 PASS**  
前置：Wave K PASS

---

## 1. 本刀范围

| 模块 | 内容 |
|---|---|
| `knowledge_fallback.py` | recent knowledge context / planning hint / fallback tool / stream thoughts |
| `command_helpers.py` | error recovery message / sanitize policy state / merge command update |

**未碰：** async 主路由 `_handle_tool_call` / `orchestrator_node` 主体、文案语义改写。

---

## 2. 验收结果

| ID | 项 | 结果 |
|---|---|---|
| A1 | import + re-export `is` | ✓ |
| A2 | 行为钉死单测 | ✓ knife7 pins |
| A3 | orch 相关回归 | ✓ **202 passed**（2 既有 Dashboard 文案失败） |
| A4 | 行数 | ✓ **5062 → 4637**（约 **-425**） |

累计七刀：约 **7692 → 4637**（约 **-3055 / ~40%**）。

---

## 3. 功能影响复查（针对「拆完是不是调不通」）

### 3.1 结论（先说）

**没有证据表明「很多功能因拆分而调不通」。**  
拆分策略是 **搬家 + 再导出**，不是改业务语义。公开入口与测试覆盖路径仍通。

### 3.2 调用链是否仍通

| 检查 | 结果 |
|---|---|
| `from app.workflow.graph import …` / `orchestrator_node` 入口 | ✓ 可 import |
| `orchestrator_node` / `wait_for_user_node` / `build_orchestrator_prompt_assembly` / `build_agent_tools` / `validate_tool_available_in_current_state` / `_handle_tool_call` | ✓ 均存在 |
| 包模块符号 vs `orchestrator_node` 再导出 | ✓ 抽样 **~175 符号 identity 一致，0 mismatch** |
| knife1–7 钉死单测 | ✓ 全绿 |
| orch 相关 harness / intelligence / prompt cache / monitoring | ✓ **202 passed** |

### 3.3 什么可能「看起来像坏了」但其实不是拆分造成

| 现象 | 说明 |
|---|---|
| harness 2 条 `Dashboard 品牌：` 断言失败 | **拆分前即失败**（渲染为「品牌：」）；在 `orchestrator_context_packets` 文案，**非本系列 re-export 引入** |
| 未跑真实浏览器 E2E / 真 LLM 全链路 | 本系列是纯重构刀；**不能**用「未手点全站」反证「已全坏」 |
| 剩余 ~4600 行仍在 god file | 主决策、async 路由仍在原文件，**未被拆坏** |

### 3.4 理论风险（诚实）

| 风险 | 等级 | 缓解 |
|---|---|---|
| 漏 re-export 导致 `NameError` | 低 | 导入冒烟 + identity 扫描 + 测试 |
| 循环导入 | 低 | 包内依赖单向；启动 import 已过 |
| 语义静默漂移 | 极低（设计为零行为） | 钉死单测 + harness 既有覆盖 |
| 未覆盖路径回归 | 中（任何大文件都有） | 继续小步 + 对关键路径补测；非「拆了就断」 |

### 3.5 产品功能面（amwaychina 生产线 / Chat 编译）与 Orch 拆分的关系

- **生产线拓扑 / 配方 / Chat 编排短路** 主要走 amwaychina API 与 FE 管道，**不依赖**本 Orch 巨石搬家才能工作。  
- **主 Chat ReAct 长跑** 走 `orchestrator_node` 入口——入口未改签名；内部调用的纯函数通过 **同名 re-export** 保持可调。

---

## 4. 总裁决

| 字段 | 填写 |
|---|---|
| **总裁决** | **待用户确认 PASS** |
