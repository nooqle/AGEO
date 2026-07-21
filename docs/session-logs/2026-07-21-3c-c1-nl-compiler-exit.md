# 3c-C0/C1 出口：规则 NL→ops + 分拆 + 缓存骨架

日期：2026-07-21

## 交付

| 项 | 路径 |
|---|---|
| C0 Plan | `docs/plans/2026-07-21-3c-c0-nl-to-ops-plan.md` |
| 规则编译器 | `app/workflow/topology_nl_compiler.py` |
| API | `POST .../flow-topology/compile-nl` |
| 稳定 prompt 前缀（C2） | `prompts/topology_ops_compiler.md` |
| UI 分拆 | `AmwayFlowTopologyPatchBar.tsx`（预设 + NL + 预览确认） |
| 单测 | `tests/test_topology_nl_compiler.py` |

## 缓存纪律

- 静态 ops 契约 / 编译角色 → `topology_ops_compiler.md`（稳定前缀，少改）  
- 用户句 + topology → 仅 trailing（C2 接线时遵守）  
- C1 不调 LLM，但编译结果形状与 preview 一致，C2 只替换 compiler 实现  

## 超大文件

| 文件 | 动作 |
|---|---|
| `AmwayFlowCanvas.tsx` | 编排条拆出；约 2768→2590 行 |
| `orchestrator_node.py` ~7k 等 | 本切片不碰，记入后续 refactor |

## 验证

- `run_3b1_suite.py`：**74 passed**  
- `tsc --noEmit`：exit 0  

## 下一步

- ~~C2：读稳定 prompt + 动态尾消息调用 LLM~~ → 见 C2 提交 / `topology_nl_llm.py`  
- 继续拆 Canvas panels：`docs/plans/2026-07-21-god-file-split-backlog.md`
