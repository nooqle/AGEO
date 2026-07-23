# Wave Q — Chat 终局（整图计划确认 → 可选运行）

日期：2026-07-23  
状态：**PASS（2026-07-23 统一手测）**  
实现：`552adf0` · TOOL_TO_NODE 修复：`5943089`  
前置：Wave D PASS；Wave P 校准字段可透传  
产品：Chat 内 **整图计划预览 → 人确认写入 →（可选）人确认开跑**；不静默改图/开跑；不改 Orch。

---

## 1. 范围

| ID | 事项 |
|---|---|
| Q1 | 预览升级：plan.summary + platforms + steps（若有）+ ops 摘要 |
| Q2 | applied 后显式「按此图开始运行」→ `createBrandIntelligenceRun` |
| Q3 | 意图小扩：搭生产线 / 生成整图 / 整条线 等（不劫持主分析） |
| Q4 | 编排前缀路径 MAX_LEN 放宽；普通路径仍保守 |
| Q5 | JOURNEY 文案同步 |

**不做：** auto-run、嵌完整画布、改 orchestrator、新 migration。

---

## 2. 验收

| ID | 项 | 结果 |
|---|---|---|
| F1 | 「跳过豆包」预览含计划平台 + 计划摘要/steps | **PASS** |
| F2 | 应用后写库、无自动 run | **PASS** |
| F3 | applied 后 CTA 开跑；run 不立刻 failed | **PASS**（`4a0587a7…` → A4 ~59%） |
| F4 | 推荐配方路径仍确认套用 | **PASS** |
| F5 | 主分析话术不进短路 | **PASS** |
| E1 | intent 脚本绿 | **PASS** |
| E2 | tsc / 无 `???` | **PASS** |

## 3. 总裁决

| **总裁决** | **PASS** |
|---|---|

统一清单：`2026-07-23-wave-pq-unified-acceptance.md`  
非阻断：采集阶段 Kimi/PG 环境抖动不记本波 FAIL。
