# Plan：3c-C0/C1 自然语言 → 拓扑 ops

日期：2026-07-21  
分支：`codex/amwaychina-mainline`  
前置：3c-B/B+ 管道 + F1/F2 修复完成

| 切片 | 含义 |
|---|---|
| **C0** | 本 Plan：范围、非目标、缓存纪律、文件分拆 |
| **C1** | **规则编译** NL → ops/intent（无 LLM 调用）+ 画布输入框 + 复用 preview/apply |
| **C2**（后续） | 稳定 system prompt + LLM 仅产出 JSON ops，接同一管道 |

---

## 1. 目标

1. 用户在生产线画布用**一句话**改拓扑，仍走：`compile → preview → 确认 → apply`（F1 冻结 ops）。  
2. C1 **不依赖 LLM**，保证可测、可离线、零费用。  
3. 为 C2 预留：**固定前缀 prompt 文件** + **动态后缀**（用户句 + 当前拓扑摘要），利于 prompt cache。  
4. 触达超大文件时**边做边拆**，禁止再往 God 文件堆 200+ 行。

## 2. 非目标

- 完整 chat 会话 / Orchestrator 主循环接入  
- 模板库、意图相似度  
- 一次 NL 直接 dispatch 运行  
- 重写 `orchestrator_node.py`（7k 行，另开里程碑）

---

## 3. 缓存友好纪律（强制）

对齐 `docs/design-cache-friendly-agent-harness-2026-05-03.md`：

| 规则 | 落地 |
|---|---|
| **稳定前缀不动** | C2 system 规则写在 `prompts/topology_ops_compiler.md`，版本化、少改；ops schema / 允许 op 表放文件前半 |
| **易变内容垫后** | 用户自然语言、当前 topology 摘要、entity_id **永远放消息末尾** |
| **工具/契约稳定** | 只允许输出 B 已冻结的 ops；新增 op 必须改契约+测试，不在 prompt 里临时发明 |
| **编译与执行分离** | LLM/规则只产出 ops；校验与落库永远是 `apply_topology_ops` + `validate_topology_document` |
| **小文件、可缓存片段** | 编译器、prompt、UI 条分文件；避免把动态拓扑嵌进 system |

C1 不调用 LLM，但仍按同一形状实现 `compile_nl`，以便 C2 只换「规则 → LLM」一层。

---

## 4. 超大文件审查与分拆策略

| 文件 | 约行数 | 本切片策略 |
|---|---|---|
| `orchestrator_node.py` | ~7k | **不碰**；3c 不经主 Orch |
| `AmwayAssociationCircleDashboardViews.tsx` | ~6k | **不碰** |
| `nodes_a4.py` / a5/* | 3k–6k | **不碰** |
| **`AmwayFlowCanvas.tsx`** | **~2.8k** | **本切片必拆**：编排建议条 + NL 输入 → 独立组件 |
| `amwaychina.py` | ~1.2k | 仅追加 thin 路由；逻辑在 `topology_*` 模块 |
| `topology_patch.py` | ~260 | 保持纯函数；NL 编译另文件 `topology_nl_compiler.py` |

**分拆原则**：按「稳定契约 / 易变 UI / 纯算法」切开，而不是按文件大小机械砍半。

---

## 5. API（C1）

`POST /amwaychina/entities/{id}/flow-topology/compile-nl`

```json
{ "text": "这次先别跑豆包", "expected_version": 3 }
```

成功：与 preview-patch 同形，外加：

```json
{
  "compile": {
    "mode": "rule",
    "matched": "skip_doubao",
    "intent_id": "skip_doubao",
    "confidence": 1.0
  },
  "ops": [...],
  "proposed": {...},
  "plan": {...},
  "summary": {...}
}
```

失败 400：无法识别，返回可展示的示例句（中文）。  
版本冲突 409：同 preview。

**不写库**；前端再走现有 apply（只带 ops）。

---

## 6. 规则覆盖（C1 最小集合）

| 用户说法（例） | 结果 |
|---|---|
| 跳过/不要/别跑 豆包 | intent `skip_doubao` |
| 恢复/打开 全部平台 | intent `enable_all_platforms` |
| 加一个分析/解读节点 | intent `add_projection_analysis` |
| 跳过 kimi / deepseek / 元宝 | op `disable_platform` |
| 不生成报告 / 断开报告 | op `remove_builtin_edge` `e-projection-report` |

无法识别 → 400，不瞎猜。

---

## 7. 任务板

| ID | 任务 | 状态 |
|---|---|---|
| C0 | 本 Plan | ✅ |
| C1-1 | `topology_nl_compiler.py` + 单测 | ✅ |
| C1-2 | `compile-nl` API | ✅ |
| C1-3 | 稳定 prompt 文件骨架（C2 用，C1 不调） | ✅ `prompts/topology_ops_compiler.md` |
| C1-4 | `AmwayFlowTopologyPatchBar` 抽出 + NL 输入 | ✅ Canvas ~2768→~2590 行 |
| C1-5 | suite + tsc + 本地 commit | ✅ |
| C2 | LLM 编译（rule-first + 稳定 prompt） | ✅ `topology_nl_llm.py` |

---

## 8. 验收

1. 「跳过豆包」compile → ops 与 preset 一致 → apply 后 removed 含 `e-fetch-doubao`。  
2. 胡言乱语 → 400 中文提示，无写库。  
3. `AmwayFlowCanvas.tsx` 行数下降（编排条移出）。  
4. 新逻辑单测进 freeze suite。  
