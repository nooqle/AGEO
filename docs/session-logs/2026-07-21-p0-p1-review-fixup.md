# Review 修复记录：P0–P1（对照 `docs/review-3b1-3b2-blueprint-2026-07-21.md`）

日期：2026-07-21

## P0

| ID | 修复 |
|---|---|
| P0-1 | `branch_custom_executors` 单一 `visited`；`validate_topology_document` 校验端点/自环/DAG/边数；PUT 接入 |
| P0-2 | `load_flow_topology` 统一 `UUID(raw)`；失败 warning 标明 gates degrade；happy path 测试 |
| P0-3 | A4 全平台断连写 `execution_status=completed`；gate→`build_request` 无 doubao 测试；A5→analysis 链意图测试；extract 自查边 |
| P0-4 | `scripts/m1_exit_check.py` 仅输出本脚本可复现字段；证据 `2026-07-21-p0-p1-fix-evidence.json` |

## P1

| # | 修复 |
|---|---|
| 1 | A4 自查 `fetch_chain`；extract 自查 `extract_chain` |
| 2 | 全平台断连 / 断 fetch 链早退补终态 |
| 3 | PUT 支持 `expected_version` 乐观锁；并发 create 409 |
| 4 | content 计划条件前后端对齐 |
| 5 | `lexicon_chain_enabled`：断词库边则不加载可编辑词库 |
| 6 | `togglePlatform` 副作用移出 setState updater |
| 7 | 圈层发起运行后跳转生产线 + toast；拓扑 PUT 失败可见错误 |
| 8 | `TOOL_TO_NODE` 用 registry graph_node 覆盖 amway 工具映射 |

## 验证

- `python scripts/run_3b1_suite.py` → **58 passed**
- `python scripts/m1_exit_check.py` → **all_ok**
- frontend tsc：见提交时结果

## 未在本批做的（P2 / 残留）

- `circle` 端口泛化、God component 拆分、branch 总时限后台化等 P2
- live UI 全链路手点（环境依赖）
