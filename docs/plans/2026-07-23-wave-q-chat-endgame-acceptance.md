# Wave Q — Chat 终局（整图计划确认 → 可选运行）

日期：2026-07-23  
状态：**工程 PASS，待统一手测**  
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

## 2. 验收（与 Wave P 统一手测）

| ID | 项 | 结果 |
|---|---|---|
| F1 | 「跳过豆包」预览含计划平台 + 计划摘要/steps | ✓ 代码；手测见统一清单 |
| F2 | 应用后写库、无自动 run | ✓ 代码契约 |
| F3 | applied 后 CTA 开跑；未点则无 run | ✓ 代码 |
| F4 | 推荐配方路径仍确认套用 | ✓ 代码 |
| F5 | 主分析话术不进短路 | ✓ intent 脚本 |
| E1 | intent 脚本绿 | ✓ 11 passed |
| E2 | tsc / 无 `???` | ✓（工程侧） |

## 3. 总裁决

| **总裁决** | **工程 PASS · 统一手测见 `2026-07-23-wave-pq-unified-acceptance.md`** |
