# Wave P + Q 统一验收清单

日期：2026-07-23  
分支：`codex/amwaychina-mainline`  
状态：**PASS（2026-07-23 统一手测 + 阻塞复测）**  
实现基线：`552adf0`  
阻塞修复：`5943089`  
前置：Wave O PASS；本波实现校准贯通 + Chat 终局  

分册：

- `2026-07-23-wave-p-calibration-memory-acceptance.md`
- `2026-07-23-wave-q-chat-endgame-acceptance.md`

---

## 0. 产品纪律（两波共同 · 已守住）

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
| P-F1 | 断豆包后建议配方理由含教训对齐（无需整页刷新） | **PASS**（复测：约 2.2s 自动出现「与近期教训一致：跳过豆包」） |
| P-F2 | `GET …/recommendations` 含 `calibration.auto_applied=false` 与 signals | **PASS** |
| P-F3 | 建议区「校准依据」一行 | **PASS** |
| P-F4 | 单测 recommend + calibration_memory | **PASS** 工程 |
| P-E1 | 中文无 `???` | **PASS** 工程 |

---

## 2. Wave Q — Chat 终局

| ID | 手测 / 工程 | 结果 |
|---|---|---|
| Q-F1 | 「跳过豆包」整图计划预览（平台 + steps + ops） | **PASS** |
| Q-F2 | 应用后写库、无自动 run | **PASS** |
| Q-F3 | 「按此图开始运行」创建 run 且不立刻 failed | **PASS**（复测：run `4a0587a7…`；11s/34s 未 failed；推进至 A4 ~59%） |
| Q-F4 | 推荐配方点击才套用、不 auto-run | **PASS** |
| Q-F5 | 主分析话术不进编排短路 | **PASS** |
| Q-F6 | 「搭一条生产线」进短路 | **PASS***（路由通过；cannot_compile 非阻断） |
| Q-E1 | intent 脚本 | **PASS** 工程 |
| Q-E2 | tsc / 无 `???` | **PASS** 工程 |

### 首轮阻塞 → 已关闭

| Bug | 信号 | 修复 | 复测 |
|---|---|---|---|
| P-F1 建议陈旧 | 刷新才出教训理由 | cache key + `topologySaveEpoch` | **PASS** ~2.2s 无需整页刷新 |
| Q-F3 起跑 NameError | `TOOL_TO_NODE is not defined` | `tool_node_map.py` | **PASS** 无 TOOL_TO_NODE / NameError |

### 非阻断观察（不判 FAIL）

- 真实采集阶段偶发 Kimi 浏览器上下文关闭、PostgreSQL 短暂断连/恢复：属运行时环境，**非**本波 TOOL_TO_NODE 回归；未造成即时 failed。

---

## 3. 总裁决

| **总裁决** | **PASS** |
|---|---|

**非目标再确认：** 无静默写图；无 auto-run；未改 Orch 语义；黑盒自学仍排除。
