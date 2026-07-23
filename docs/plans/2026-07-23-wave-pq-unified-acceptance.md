# Wave P + Q 统一验收清单

日期：2026-07-23  
分支：`codex/amwaychina-mainline`  
状态：**工程 PASS，待手测**  
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
| P-F1 | 断豆包边后「建议配方」理由含「与近期教训一致：跳过豆包」类文案（若有同结构配方） | ⬜ 手测 |
| P-F2 | Network：`GET …/recommendations` 含 `calibration.auto_applied=false` 与 signals | ⬜ 手测 |
| P-F3 | 建议区出现「校准依据」一行（教训/变更计数） | ⬜ 手测 |
| P-F4 | 单测：`test_flow_topology_recipe_recommend` + `test_flow_calibration_memory` | ✓ 工程 |
| P-E1 | 中文无 `???` | ✓ 工程 |

---

## 2. Wave Q — Chat 终局

| ID | 手测 / 工程 | 结果 |
|---|---|---|
| Q-F1 | Chat「跳过豆包」→ 卡含计划平台 + 摘要/steps/ops 摘要 | ⬜ 手测 |
| Q-F2 | 点「应用变更」写库；**不**自动出现 run | ⬜ 手测 |
| Q-F3 | applied 后点「按此图开始运行」才创建 intelligence run | ⬜ 手测 |
| Q-F4 | 「推荐配方」→ 套用需确认；不 auto-run | ⬜ 手测 |
| Q-F5 | 「帮我分析品牌…生成报告」仍走普通对话（不短路） | ⬜ 手测 |
| Q-F6 | 「搭一条生产线」进编排短路 | ⬜ 手测 |
| Q-E1 | `node scripts/check_chat_topology_intent.mjs` | ✓ 工程 |
| Q-E2 | tsc 相关面 | ✓ 工程（以本地 tsc 为准） |

---

## 3. 总裁决

| **总裁决** | **工程 PASS · 待用户统一手测勾选** |
|---|---|

手测建议路径（一次走完）：

1. Console：断豆包 → 看建议配方校准依据与 reasons  
2. Chat：跳过豆包 → 整图预览 → 应用 → **不要**自动跑 → 再点开跑  
3. Chat：推荐配方 → 套用  
4. Chat：分析品牌生成报告 → 不进编排卡  
