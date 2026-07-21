# 3c-B 出口：确定性 topology patch 管道

日期：2026-07-21  
Plan：`docs/plans/2026-07-21-3c-chat-to-topology-plan.md`  
定案：A（Plan）→ B（无 LLM 竖切）

## 交付

| 层 | 内容 |
|---|---|
| Plan A | 范围/非目标/ops 契约/API/与 M3 缝合 |
| B1 | `app/workflow/topology_patch.py`：ops + presets + summary |
| B2 | `POST .../preview-patch` · `POST .../apply-patch` |
| B3 | 画布「编排建议（试验）」预设 → 预览 → 确认 |
| B4 | `tests/test_topology_patch.py` 纳入 `run_3b1_suite` |

## 验证

- `python scripts/run_3b1_suite.py` → **66 passed**
- `frontend tsc --noEmit` → **exit 0**

## 验收对照（B）

1. `skip_doubao` → `e-fetch-doubao` 进入 removed，plan 无 doubao — 单测覆盖  
2. apply 需 `expected_version`；冲突 409 — API 实现  
3. 自环边 validate 400 — 单测覆盖  
4. 前端确认应用后 setTopology + 刷新 version — 代码落地  

## 非范围（下一批）

- C：自然语言 → ops  
- 模板库  
- apply 后自动进 M3 开跑（仅文档缝合点，未做自动 dispatch）

## 结论

**3c-B 管道可验收关闭**；可进 C 或本地 commit。
