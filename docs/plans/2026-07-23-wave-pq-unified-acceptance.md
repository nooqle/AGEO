# Wave P + Q 统一验收清单

日期：2026-07-23  
分支：`codex/amwaychina-mainline`  
状态：**工程修复后待复测（首轮 7 PASS / 2 FAIL）**  
基线实现：`552adf0` · 阻塞修复见后续 commit  
前置：Wave O PASS；本波实现校准贯通 + Chat 终局  

分册：

- `2026-07-23-wave-p-calibration-memory-acceptance.md`
- `2026-07-23-wave-q-chat-endgame-acceptance.md`

---

## 0. 产品纪律（两波共同）

| 必须 | 禁止 |
|---|---|
| 人确认后才写拓扑 | 静默 auto-apply |
| 人再次点击才开跑 | apply 后 auto-run |
| 校准信号可见（reasons / calibration / visible_memory） | 黑盒改默认拓扑 |
| 复用 Console 同源 API | 改 orchestrator 语义 |

---

## 1. Wave P — 记忆 / 校准加深

| ID | 手测 / 工程 | 结果 |
|---|---|---|
| P-F1 | 断豆包边后「建议配方」理由含「与近期教训一致：跳过豆包」类文案（若有同结构配方） | ❌ 首轮 FAIL → **已修**：cache key 含门控+`topologySaveEpoch`，PUT/apply 后重载 |
| P-F2 | Network：`GET …/recommendations` 含 `calibration.auto_applied=false` 与 signals | ✓ 首轮 PASS |
| P-F3 | 建议区出现「校准依据」一行（教训/变更计数） | ✓ 首轮 PASS（刷新后；修后应即时） |
| P-F4 | 单测：`test_flow_topology_recipe_recommend` + `test_flow_calibration_memory` | ✓ 工程 |
| P-E1 | 中文无 `???` | ✓ 工程 |

---

## 2. Wave Q — Chat 终局

| ID | 手测 / 工程 | 结果 |
|---|---|---|
| Q-F1 | Chat「跳过豆包」→ 卡含计划平台 + 摘要/steps/ops 摘要 | ✓ 首轮 PASS |
| Q-F2 | 点「应用变更」写库；**不**自动出现 run | ✓ 首轮 PASS |
| Q-F3 | applied 后点「按此图开始运行」→ run 创建且**不**立刻 failed | ❌ 首轮 FAIL `TOOL_TO_NODE` → **已修** `tool_node_map.py` |
| Q-F4 | 「推荐配方」→ 套用需确认；不 auto-run | ✓ 首轮 PASS |
| Q-F5 | 「帮我分析品牌…生成报告」仍走普通对话（不短路） | ✓ 首轮 PASS |
| Q-F6 | 「搭一条生产线」进编排短路 | ✓* 路由 PASS；cannot_compile 非阻断 |
| Q-E1 | `node scripts/check_chat_topology_intent.mjs` | ✓ 工程 |
| Q-E2 | tsc 相关面 | ✓ 工程（以本地 tsc 为准） |

### 首轮阻塞根因与修复

| Bug | 信号 | 修复 |
|---|---|---|
| P-F1 建议陈旧 | 断边后仍旧 reasons；刷新才对 | `AmwayFlowRecipeBar` cache key 含 `removedEdgeIds` + `topologySaveEpoch`；Canvas PUT 成功后 epoch++ |
| Q-F3 起跑 failed | `name 'TOOL_TO_NODE' is not defined` | `workflow_progress` 从 `tool_node_map` 导入；壳 re-export |

---

## 3. 总裁决

| **总裁决** | **暂不 PASS · 阻塞已修 · 请复测 P-F1 + Q-F3** |
|---|---|

复测焦点：

1. Console：断豆包 → **无需刷新** 建议配方出现教训对齐理由  
2. Chat：跳过豆包 → 应用 → 按此图开始运行 → run **非**立刻 failed（可进 active / 正常推进）
