# Review 对照闭环：P0–P1 完成 + 关键 P2 + 回归 PASS

日期：2026-07-21  
对照：`docs/review-3b1-3b2-blueprint-2026-07-21.md`  
自动化：`scripts/review_p0_p1_p2_verify.py` → `docs/session-logs/2026-07-21-review-closure-verify.json`

## 总裁决

**PASS**（自动化对照，本轮重跑 `2026-07-21T11:45:06Z`）

| 层级 | 状态 |
|---|---|
| P0-1 BFS DoS + PUT 校验 | ✅ 已修 + 测 |
| P0-2 load_flow_topology UUID/静默失败 | ✅ 已修 + 测 |
| P0-3 验收证据链 | ✅ gate→build_request + 终态 + extract 自查 + suite |
| P0-4 证据可复现 | ✅ 脚本自产 JSON，无手拼字段 |
| P1-1～8 | ✅ 已修（见下；1–5/8 自动化钉住，6–7 代码抽查） |
| 关键 P2 | ✅ 1/2/3/4/5部分/10/11 |

## P0 对照（本轮自动化）

| ID | check id | 结果 |
|---|---|---|
| P0-1 | `P0-1-bfs` / `P0-1-validate` | ✅ |
| P0-2 | `P0-2-invalid-uuid` | ✅ |
| P0-3 | `P0-3-a4-filter` + suite 内 A5 链入 | ✅ |
| P0-4 | `producer=scripts/review_p0_p1_p2_verify.py` | ✅ |

## P1 对照

| # | 状态 | 说明 |
|---|---|---|
| 1 门是劝告式 | ✅ | A4/extract 入口自查边；`P1-1-extract-self-check` |
| 2 断边早退缺终态 | ✅ | `execution_status=completed`；`P1-2-terminal` |
| 3 读写竞态 | ✅ | `expected_version` 乐观锁 + 409；`P1-3-expected-version-field` |
| 4 双端计划分叉 | ✅ | content 条件对齐；`P1-4-content-plan` + FE 注释同源 |
| 5 lexicon 边无效 | ✅ | `lexicon_chain_enabled`；`P1-5-lexicon-gate` |
| 6 updater 纯度 | ✅ | 代码抽查：persist 不在 setState updater 内 |
| 7 确认死胡同 | ✅ | 代码抽查：`view=flow` + toast「请在生产线视图确认…」 |
| 8 注册表无人消费 | ✅ | `TOOL_TO_NODE` registry overlay；`P1-8-registry` |

## 关键 P2

| # | 状态 |
|---|---|
| 1 circle→entity_graph | ✅ `P2-1-entity_graph` |
| 2 fallback_reason 仅类名 | ✅ 代码落地 |
| 3 report 边才喂 report | ✅ `P2-3-report-gate` |
| 4 词库加载 helper 收敛 | ✅ |
| 5 void node / 无用表达式 | ✅ 部分 |
| 10 content 上游按连线取 analysis | ✅ |
| 11 PUT config 大小/id 唯一；无效平台 400 | ✅ `P2-11-unique-node-id` |
| 6 God component 拆分 | ⏭ 未做（体积大，非阻塞） |
| 7–9/12 等 | ⏭ 非阻塞 |

## 本轮回归数字（重跑）

| 命令 | 结果 |
|---|---|
| `python scripts/review_p0_p1_p2_verify.py` | **verdict PASS / all_ok true**（17 checks） |
| suite 内 `run_3b1_suite.py` | **58 passed** in ~3.7s |
| `python scripts/m1_exit_check.py` | **all_ok true** |
| `frontend` `tsc --noEmit` | **exit 0** |

证据文件：
- `docs/session-logs/2026-07-21-review-closure-verify.json`
- `docs/session-logs/2026-07-21-p0-p1-fix-evidence.json`（m1_exit_check 产出）

## 残留裁决（用户知情定夺，2026-07-21 续）

| 项 | 裁决 | 说明 |
|---|---|---|
| **P1-3 前端半边**（自定义节点运行无互斥 + PUT 无 `expected_version`） | ✅ **本批已修** | `customRunLockRef` 全局互斥；`runCustomNode`/`runBranchFrom` PUT 带 version；成功后不 dirty 回写并 refresh version；按钮禁用看「任一在跑」 |
| **分支运行总时限**（最坏 ~30min 占 DB） | ⏭ **正式降为 P2** | manage-only + 20 节点上限可辩护；不阻塞 3b 完成宣称；后续可后台任务 / per-entity 锁 + 总时限 |
| live UI 全链路手点 | 残留 | 依赖本地 8000/3000 |
| God component / reason-code / stage 双轨 | P2 refactor | 非阻塞 |
| 工作区无关 dirty WIP | 范围外 | fetcher/llm_usage 等未纳入对照 |

## 结论

评审报告中的 **P0 阻塞项与 P1 应修项均已代码落地**（含后补的 P1-3 前端半边）；关键 P2 已收口；分支总时限**经用户侧裁决降级为 P2**。

**确认：修复完毕。** 可重新宣称 **3b-1 / 3b-2 约束模式在工程+审查修复维度完成**。
