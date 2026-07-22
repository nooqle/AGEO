# Orchestrator P2 拆分设计稿（Wave C / C4 · 仅设计）

日期：2026-07-22  
状态：**设计稿 only — 本波不实现代码大拆**  
关联：`docs/plans/2026-07-21-god-file-split-backlog.md`、`docs/plans/2026-07-22-wave-c-acceptance.md`

---

## 1. 目标与非目标

**目标**

- 把 `orchestrator_node.py`（~7k 行量级）从「全能路由+执行」拆成可测试、可演进的边界。
- 拆分后行为契约不变：同一输入 → 同一步骤序列 / 同一状态机语义。
- 为未来 Chat 入口（Wave 后续 C2）与配方推荐消费同一套 ops/拓扑契约预留挂点。

**非目标（本设计明确不做）**

- 本文件交付周期内**不**落地 PR 大拆。
- 不改黑盒学习策略（仍排除）。
- 不与 C1 推荐功能混在同一实现 PR。

---

## 2. 建议模块边界

| 模块（建议路径） | 职责 | 迁入内容类型 |
|---|---|---|
| `workflow/orchestrator/state_machine.py` | 运行状态迁移、等待点、完成/失败 | 状态枚举、合法迁移表 |
| `workflow/orchestrator/routing.py` | 意图/步骤路由（选下一 skill/node） | 纯函数 + 可单测路由表 |
| `workflow/orchestrator/topology_bridge.py` | 读 topology / flow_plan / platforms | 与 3b 拓扑解析对接 |
| `workflow/orchestrator/run_context.py` | 从 run.input_scope 取 recipe/entity | 元数据读写，无副作用 |
| `workflow/orchestrator/effects.py` | 真正 side-effect：调 A1–A6、写库 | 窄接口，便于 mock |
| `workflow/orchestrator/node.py`（薄壳） | 保留原 entry：`orchestrator_node` 签名 | 只编排调用，无业务分支膨胀 |

原则：**路由与状态机纯函数优先；IO 集中 effects；壳文件 &lt; 400 行。**

---

## 3. 拆分顺序（实现时）

1. **抽纯函数**（零行为变更）：路由表、状态迁移、input_scope 解析。  
2. **抽 topology_bridge**：对齐现有 `topology_resolver` / `flow_plan`。  
3. **effects 适配层**：原内联 await 原样搬家，禁止改语义。  
4. **薄壳替换 + 全量 3b1/编排回归**。  
5. 再考虑 a5 / DashboardViews 等其它巨石（**另里程碑**）。

每步独立 PR；禁止「拆分 + 新功能」同 PR。

---

## 4. 验收口径（将来实现波用）

| ID | 项 |
|---|---|
| P2-E1 | `orchestrator_node` 壳 &lt; 400 行（或团队约定阈值） |
| P2-E2 | 关键路径单测不降；3b1 suite 全绿 |
| P2-E3 | 无公共 API 破坏；无 migration 混入除非必要 |
| P2-E4 | 禁止新业务 if/else 回填进壳文件（codeowners / review 检查） |

---

## 5. 与产品能力的关系

```
Chat / Console  ──►  同一 ops / recipe / topology 契约
                         │
                         ▼
              orchestrator（路由 + 状态）
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
      topology        recipes         agents A1–A6
```

C1 推荐只消费 recipes + events + topology，**不依赖**本拆分完成即可上线。

---

## 6. 结论

Wave C 交付 **C4 设计稿** 即满足工程验收 E5；代码大拆排独立里程碑，勿与推荐/Chat 功能混做。
