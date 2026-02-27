# API vs 网页采集结果差异 — 团队讨论纪要

**日期**: 2026-02-27
**参与角色**: 产品 (Marty Cagan)、架构 (Martin Fowler)、质量 (James Bach)

---

## 问题描述

同一个问题（如"推荐一款好用的牙膏"），通过 API 调用和通过网页界面搜索同一个 AI 平台（如豆包），返回的答案完全不同：

- **网页版**：推荐品牌 A、B、C
- **API 版**：推荐品牌 X、Y、Z

AGEO 的 A4 模块当前以 API 采集为主（豆包、混元、Kimi），仅 DeepSeek 走浏览器采集。这意味着分析报告可能无法反映用户在网页上的真实体验。

---

## 差异根因分析（架构视角）

API 和网页端本质上是**两个不同的产品端点**，差异来自三层：

| 层级 | API | 网页 |
|------|-----|------|
| **模型层** | 固定模型版本（如 `doubao-seed-1-8-251228`） | 可能有不同版本、A/B routing |
| **检索增强层** | `web_search` tool，搜索源受限（豆包限定 `["douyin", "toutiao"]`） | 全量搜索索引 + 私有 ranking 算法 |
| **后处理层** | 原始模型输出 | 安全过滤 + UI 格式化 + 品牌策略 |

此外，AGEO 的 API 调用注入了自定义 system prompt（要求 JSON 格式输出、至少 5 个引用等），进一步偏离了用户在网页上的真实体验。

**结论：差异是结构性的、不可消除的。**

---

## 三方观点

### 产品视角

- **用户关心的是网页/App 体验**（消费者视角），不是 API 输出。没有消费者通过 API 问"推荐牙膏"
- **最大风险：用户可以轻易证伪** — 拿到报告后自己去网页搜，发现不一样 → 平台信任度归零
- **竞品（Semrush、Otterly.ai、Profound）普遍采用模拟真实用户搜索路径**
- **优先级 P0** — 直接影响产品核心价值主张
- 不建议默认同时展示两种结果（增加用户认知负担），但可作为高级功能

### 架构视角

- API 和 Browser 结果**必须视为不同数据源**，建议引入 `DataChannel` 概念（`doubao_api`、`kimi_browser` 等）
- Browser 采集应定位为 **best-effort 补充**，技术风险高（反爬检测、DOM 变更、登录态、并发限制）
- 当前 `FetchResult` 的 `fetch_method` 字段已存在但**未被 A5 分析层消费**，API 和 Browser 结果被等权混合
- 建议 A5 分析分层输出：L1 全通道聚合 / L2 按 data_channel 分组 / L3 API vs Browser 对比
- 每条 `FetchResult` 应增加采集上下文元数据（模型版本、system prompt hash、搜索源等）

### 质量视角

- 这是一个**测量效度（validity）问题** — 系统测量的不是"用户看到什么"，而是"API 在特定配置下返回什么"
- BWVS 核心指标受影响：mention 占 40% 权重，如果品牌集合不同，指标基础数据就是偏的
- 豆包搜索源硬编码为 `["douyin", "toutiao"]`，会系统性低估微信生态强但抖音弱的品牌
- 建议建立**双通道对照实验**，用 Jaccard 相似度和 Kendall's tau 量化品牌重叠度和排名一致性
- 建议每周做一致性审计，Kimi 是天然对照组（唯一已实现双通道的平台）

---

## 共识结论

1. **API 和网页是不同数据源**，不应视为同一平台的重复采样
2. **用户关心的是网页端体验**，这是产品价值的基础
3. **当前系统存在可信度风险**，用户可轻易通过网页验证证伪
4. **行业实践偏向模拟真实用户路径**

---

## 分歧点

| 议题 | 产品 | 架构 | 质量 |
|------|------|------|------|
| Browser 定位 | 应逐步迁移为主力 | best-effort 补充 | 生产数据以 Browser 为主 |
| 优先行动 | 先做 A/B 测试量化差异 | 先加 data_channel 字段 | 先建立一致性审计 |
| 双轨展示 | 不建议默认双轨 | 推荐分层展示 | 分层报告 |

---

## 建议行动路径（未启动）

### 第一步：验证假设（1 周）

- 选 20 个典型问题，对 Kimi 跑 API vs Browser 对照
- 计算品牌重叠度（Jaccard）和排名一致性（Kendall's tau）
- 用数据决定差异程度是否可接受

### 第二步：数据标注（1-2 周）

- `FetchResult` 增加 `data_channel` 字段
- A5 分析按 `data_channel` 分组统计
- 前端报告标注采集方式

### 第三步：看数据决策

- 差异 < 10%：API 方案继续用，标注即可
- 差异 10-30%：增加 Browser Handler，双轨并行
- 差异 > 30%：核心平台必须迁移到 Browser

---

## 当前代码现状参考

```
API_PLATFORMS = ["doubao", "hunyuan", "kimi"]      # constants.py:85
BROWSER_PLATFORMS = ["deepseek"]                     # constants.py:86
```

- Kimi 同时有 `KimiClient`（API）和 `KimiHandler`（Browser），当前配置只用 API
- `FetchResult.fetch_method` 字段已存在，A5 未消费
- 豆包 API 搜索源硬编码为 `["douyin", "toutiao"]`
