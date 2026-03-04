# Specta AI 战略蓝图

> **版本**：1.0
> **日期**：2026-02-28
> **定位**：产品发展方向的核心纲领性文件
> **依据**：团队四方 Debate（产品/架构/QA/UX）+ 行业调研 + 实测数据
> **关联**：`reform-plan.md`（技术实施计划）

---

## Executive Summary

三个改变一切的发现：

**1. AI 回答天然不稳定——这是我们存在的根本理由**

实测证明：同一个问题用 API 调用3次，品牌推荐列表的一致性仅 ~20%。这不是 Bug，是 AI 大模型的本质特性。品牌方自己查一次得到的只是随机快照——**只有专业工具做大规模统计聚合才能看到真相**。

**2. 中国 AI 搜索监测市场几乎完全空白**

全球所有 AEO 竞品（Profound、Scrunch、Peec、Otterly）只覆盖英文平台。中国 GEO 市场 2025 H1 规模 $36.5亿（YoY +240%），豆包 MAU 1.63亿，85% 企业计划增加 AI 搜索优化投入——但没有专业监测工具。

**3. SEO 行业二十年经验指明了确定方向**

Google 从未提供 SERP API → SEO 工具靠爬虫建立了 $749亿产业。Google 个性化搜索没有杀死 SEO → 反而催生更大市场。产品定位从"精确排名"转向"可见度概率" → 打开了更大商业空间。AEO 正在走同一条路。

---

## 第一章：基础认知——AI 回答的本质

### 1.1 颠覆性发现：AI 不跟自己说一样的话

QA 对实测数据严格审查后发现，Kimi API 同一问题3次调用返回的品牌列表：

| 运行 | 返回品牌 | 品牌数 |
|------|---------|--------|
| 第1次 | 黛珂, The Ordinary, 科颜氏, 理肤泉, CPB, OLAY, 雅漾 | 7 |
| 第2次 | 修丽可, 雅诗兰黛, OLAY, The Ordinary, 珀莱雅, CeraVe, 理肤泉, 薇诺娜, 雅漾, Paula's Choice | 10 |
| 第3次 | 雅诗兰黛, 优色林, 修丽可, 溪木源, The Ordinary | 5 |

三次之间的品牌重叠率：**9% ~ 21%**。

而此前我们认为"很大差异"的 API vs Browser 对比（~48% 重叠），**反而比 API 和自己的一致性高出一倍多**。

> **关键结论：我们此前以为在测"渠道差异"，实际上测到的是 AI 回答的天然随机性。**

### 1.2 为什么这反而是好消息

| 如果 AI 回答是稳定的（假设） | 如果 AI 回答是不稳定的（事实） |
|---|---|
| 品牌方自己打开网页查一次就知道结果 | 品牌方自己查到的只是随机快照，没有代表性 |
| 一次性报告就够了 | 必须持续监测，多次采样才有意义 |
| 工具价值有限——用户自己也能做 | **工具价值极高——只有工具能做大规模统计聚合** |
| 竞争壁垒低 | 竞争壁垒高（基础设施 + 统计能力） |

> **AI 回答的不稳定性不是产品的敌人，是产品存在的理由。** 正如天气越不确定，气象服务越有价值。

### 1.3 产品叙事的范式转变

**旧叙事**："我们帮你看在 AI 搜索中排第几"（确定性思维）

**新叙事**："AI 搜索的推荐每次都不同——我们帮你理解品牌在这个动态环境中的真实可见度"（概率性思维）

**产品语言示例**：

- 不说："你的品牌在豆包上排名第3"
- 而说："当消费者在 AI 平台搜索护肤品时，你的品牌有 **67%** 的概率被提及，其中 **38%** 的概率被首位推荐"

---

## 第二章：行业格局——SEO 的二十年和 AEO 的现在

### 2.1 SEO 的三个关键历史教训

**教训一：数据采集方式跟着"真相"走，不跟着"方便"走**

Google 从未提供过 SERP 排名的官方 API。Ahrefs（年收入 $1.49亿，+49% YoY）和 SEMrush（年收入 $3.77亿，+22% YoY）从第一天起就靠爬虫。2025年9月 Google 砍掉 `&num=100` 参数，成本翻10倍——Ahrefs 一个月内恢复。**消费者用浏览器看搜索结果，所以 SEO 工具也用浏览器采集。**

**教训二：个性化没有杀死行业，反而催生了更大市场**

| 时间 | 事件 | SEO 市场规模 |
|------|------|-------------|
| 2009 | Google 推出个性化搜索，行业恐慌 | ~$200亿 |
| 2024 | Google Core Update 进一步加深个性化 | ~$600亿 |
| 2025 | 个性化成为常态 | **$749亿** |
| 2030（预测） | — | **$1,273亿** |

原因：越复杂的环境，品牌方越需要专业工具。

**教训三：产品定位比技术路线更重要**

SEO 工具三次转型：精确排名 → 可见度分数 → E-E-A-T 内容质量诊断。SEMrush 的成功不是因为爬虫最强，而是把数据包装成了所有部门都能理解的可见度仪表盘。

> 来源：[SEO Services Market Projected to Reach $171.77B by 2030](https://www.prnewswire.com/news-releases/search-engine-optimization-seo-services-market-projected-to-reach-usd-171-77-billion-by-2030--growing-at-13-24-cagr-markntel-advisors-top-companies---semrush-holdings-inc-ahrefs-pte-ltd-moz-group-llc-302505098.html)

### 2.2 AEO 竞品全景

**所有主流 AEO 工具都使用浏览器/前端抓取，没有一家依赖 API 作为主数据源。**

| 工具 | 数据方法 | 月价 | 监测量 | 覆盖引擎 | 中国平台 |
|------|---------|------|--------|---------|---------|
| **Profound** | 前端抓取 + CDN日志 | $399起 | 24K回答/月 | 10+ | DeepSeek仅 |
| **Scrunch AI** | 合成提示词 + 浏览器 | $500 | 700提示词/月 | 8 | 无 |
| **Peec AI** | 近实时监测 | €199 | 9K回答/月 | 4+ | 无 |
| **Otterly.ai** | 实时多LLM审计 | €20起 | 未公开 | 3 | 无 |
| **AirOps** | 内容运营 + 监测 | $2,000 | 250提示词 | 3+ | 无 |
| **Gumshoe AI** | Persona-driven | 公测中 | 未公开 | 6 | 无 |

**Profound（行业龙头，红杉 $3500万 B轮）的核心方法论**：
- 每天 600万条提示词，10+ AI 引擎前端抓取
- 1.3亿条真实用户对话（合规数据面板）
- CDN 服务端日志分析（Cloudflare/Vercel/Fastly）
- 官方表述："追踪真实用户看到的，不是净化过的 API 响应"

> 来源：[Profound Review](https://nicklafferty.com/reviews/profound-best-aeo-geo-platform-for-ai-search/)、[AEO Tools Compared](https://www.redirects.net/articles/aeo-tools-compared-airops-profound-peec-ai)

### 2.3 中国市场：被忽略的巨大空白

| 数据点 | 值 | 来源 |
|--------|-----|------|
| 中国 GEO 市场规模（2025 H1） | **$36.5亿** | YOYI TECH |
| YoY 增长率 | **240%** | YOYI TECH |
| 豆包 MAU | **1.63亿** | 公开数据 |
| 企业计划增加 AI 搜索优化投入（2026） | **85%** | Conductor |
| 覆盖中国 AI 平台（Kimi/豆包/混元）的 AEO 工具 | **0 家** | 调研结论 |

> 来源：[YOYI TECH Chinese GEO Ecosystem](https://en.yoyi.com.cn/unlock-the-mistery-of-chinese-geo-ecosystem.html)、[Conductor AEO/GEO Benchmarks Report 2026](https://www.conductor.com/academy/aeo-geo-benchmarks-report/)

### 2.4 AI 个性化：正在发生什么

| 平台 | 功能 | 时间 | 影响 |
|------|------|------|------|
| **ChatGPT** | Memory with Search | 2025年4月 | 基于历史对话个性化搜索结果 |
| **ChatGPT** | 个性化人格设置 | 2025年 | Plus/Pro 用户可自定义回答风格 |
| **Google AI Mode** | 深度个性化 | 2025年夏 | 基于搜索历史、应用、Drive、Gmail |
| **Gartner 预测** | 传统搜索量下降25% | 到2026年 | 用户转向 AI 助手 |

**影响预判**：
- **短期（6-12月）**：影响小。中国平台个性化程度远低于 ChatGPT。核心推荐保持稳定。
- **中期（1-2年）**：高频用户与新用户回答开始分化。差异主要在长尾推荐和回答风格。
- **长期（2-3年+）**：从"统一排名"→"分人群可见度"。**这恰恰是商业价值更大的方向**——品牌方更需要理解"不同人群中我的品牌表现如何"。

> 来源：[A Survey of Personalized LLMs (arXiv 2502.11528)](https://arxiv.org/html/2502.11528v2)、[Gumshoe AI Pre-Seed](https://blog.gumshoe.ai/gumshoe-raises-2m-pre-seed-to-help-marketers-navigate-ai-search/)

---

## 第三章：战略定位

### 3.1 三重护城河

| 护城河 | 说明 | 竞品复制难度 |
|--------|------|------------|
| **中国 4 平台覆盖** | Kimi / 豆包 / DeepSeek / 混元 | 高——需要中国账号体系、DOM 适配、本地基础设施 |
| **Chat-first 交互** | 品牌方不同部门用自然语言提问 | 中——但交互质量需要深度 Prompt 工程 |
| **Persona-driven 分析** | A2 Persona Agent 生成用户画像，模拟不同群体的 AI 搜索体验 | 高——Gumshoe AI 靠这一个点拿到 $200万 Pre-seed |

### 3.2 市场定位

**目标市场**：中国 AI 搜索可见度监测平台

**核心定位**：
> 帮助品牌方理解和优化在 AI 搜索中的可见度——基于统计概率，而非单次快照。

**初始目标客户**：

| 优先级 | 客户类型 | 理由 |
|--------|---------|------|
| 第一 | 国际品牌在华团队（如欧莱雅中国、宝洁中国） | 已有 SEO 认知，理解 AEO 逻辑，现有工具不覆盖中国 AI 平台 |
| 第一 | 国内 DTC 品牌（如完美日记、花西子） | AI 搜索中争夺"推荐位"是核心增长诉求 |
| 第二 | 营销 Agency | 一个 Agency 管理 10-50 个品牌客户，ARPU 高，网络效应强 |

### 3.3 定价体系

| 版本 | 月价 | 核心能力 | 目标客户 |
|------|------|---------|---------|
| 基础版 | **¥999** | 1 品牌，50 Prompt/月，2 平台（API 快速扫描） | 初次尝试 AEO 的品牌 |
| **专业版** | **¥2,499** | 3 品牌，200 Prompt/月，4 平台，画像分析，竞品对比 | 认真做 AEO 的品牌市场部 |
| 旗舰版 | **¥4,999** | 10 品牌，500 Prompt/月，趋势监测，部门视角，优先客服 | 品牌集团或 Agency |

**定价逻辑**：
- 计价维度：品牌数 × Prompt 数（对标行业标准）
- 专业版为主推档，¥2,499 约等于一个 SEO 工具 + 一个社媒监测工具的月费
- 基础版 < ¥1,000 降低决策门槛（通常不需上级审批）
- 年付 8 折，14 天免费试用 + 首月 5 折
- 预估毛利率：**~85%**（变动成本 ~¥360/月/专业版客户）

> 来源：[Profound Pricing](https://www.tryprofound.com/pricing)、[Scrunch AI Pricing](https://cairrot.com/alternatives/scrunch-ai-review-pricing-comparison/)、[SaaS Pricing Benchmark 2025](https://www.getmonetizely.com/articles/saas-pricing-benchmark-study-2025-key-insights-from-100-companies-analyzed)

---

## 第四章：产品设计

### 4.1 核心指标体系 BWVS 2.0

```
BWVS = 0.35 × 提及率
     + 0.25 × 提及位置分
     + 0.15 × 情感得分
     + 0.15 × 平台覆盖率
     + 0.10 × 引用质量分
```

| 子指标 | 定义 | 范围 |
|--------|------|------|
| 提及率 | 品牌被提及的回答数 / 总回答数 | 0-100 |
| 提及位置分 | 加权平均：首位推荐=100, 前3=80, 列举=50, 附带提及=20 | 0-100 |
| 情感得分 | (正面 - 负面) / 总提及 * 100，映射到 0-100 | 0-100 |
| 平台覆盖率 | 品牌出现的平台数 / 监测平台总数 | 0-100 |
| 引用质量分 | 品牌官网/权威来源被引用次数的归一化值 | 0-100 |

**关键变化**：基于统计聚合（多次采样），而非单次快照。每个数字后跟一句人话解释"所以呢"。

**新增维度——一致性分数（Consistency Score）**：
衡量品牌在不同场景/画像中被推荐的一致程度。高一致性 = 品牌心智强。这是竞品没有的独特指标。

> 参考：[SEMrush AI Share of Voice](https://www.semrush.com/blog/how-to-measure-ai-share-of-voice/)、[SEMrush AI Visibility Index](https://ai-visibility-index.semrush.com/)

### 4.2 双轨采集策略

| | Fast Track（快速扫描） | Deep Scan（深度扫描） |
|---|---|---|
| **驱动** | API | Browser |
| **速度** | 30秒-2分钟 | 5-10分钟 |
| **用途** | 日常监测、仪表盘刷新、快速预览 | 月度报告、竞品深度对比、向上汇报 |
| **数据标注** | "基于 API 采样，约60-70%反映真实用户体验" | "基于前端模拟，完整还原真实用户体验" |
| **默认推荐** | 基础版默认 | 专业版以上默认 |

### 4.3 UX 信息架构

**核心设计原则**：帮用户从"我排第几"的旧心智模型，迁移到"我的 AI 可见度健康状况如何"的新心智模型。

**仪表盘层级**：

```
第一层：Hero 指标
┌──────────────────────────────────────────────────┐
│  BWVS 72.4  ▲+3.2  [良好]                        │
│  ═══════════════════════════════════  趋势线       │
│                                                    │
│  提及率 45.2% ▲   声量份额 31.7% ▼   情感 正面 →  │
└──────────────────────────────────────────────────┘

第二层：四维雷达图 + 竞品叠加

第三层：Tab 细分（可见度 / 平台对比 / 诊断详情 / 行动计划 / 监测）
```

**三层不确定性表达**：

| 层级 | 受众 | 展示方式 |
|------|------|---------|
| 第一层 | 大多数用户 | 信号强度图标 + "基于 N 个样本" |
| 第二层 | 好奇的用户 | 展开面板：API vs Browser 值 + 自然语言解释 |
| 第三层 | 专业用户 | 趋势图上的置信区间阴影带 |

**渐进式加载**（解决 Browser 慢的 UX 问题）：

```
阶段一（0-3秒）：Skeleton 屏 + "正在启动分析..."
阶段二（30秒-2分钟）：API 数据先到先展示 + "浏览器深度采集中..."
阶段三（5-10分钟）：Browser 数据融合，Toast 通知"深度采集完成"
```

**行动中心**：

```
紧急（红）：品牌在某平台被竞品替代，本周下降12%  │ 影响: BWVS +8.5
重要（橙）：情感倾向偏中性，缺乏正面评价内容      │ 影响: BWVS +4.2
优化机会（蓝）：增加FAQ结构化内容可提升AI抓取率   │ 影响: BWVS +2.1
已完成（灰）：上周"优化品牌描述" → BWVS +3.2 ✓  │ 效果反馈
```

每条建议包含：影响量化、自然语言问题描述、可执行动作列表、效果反馈循环。

**竞品对比**：三视图切换（概览/详细雷达/趋势对比），一次只对比一个竞品，自动标注优劣势。

> 参考：[SEMrush AI Visibility Toolkit](https://www.semrush.com/kb/1493-ai-visibility-toolkit)、[Ahrefs Brand Radar](https://ahrefs.com/brand-radar)、[B2B SaaS Dashboard Design](https://uxdesign.cc/design-thoughtful-dashboards-for-b2b-saas-ff484385960d)

---

## 第五章：技术架构路线

### 5.1 三阶段演进

```
┌─────────────────────────────────────────────────────────────────┐
│  Phase 1: 混合校准期（现在 → Q2 2026）                            │
│  ──────────────────────────────────────                           │
│  基础设施：2台阿里云 ECS（4vCPU, 8GB），¥900/月                     │
│  采集能力：6 并发浏览器，15-20 分钟/全量分析                         │
│                                                                   │
│  ● API 为日常快速采集主力                                          │
│  ● Browser 每周做校准采样（50-100题/平台）                          │
│  ● Patchright 替换 Playwright（一行 import 改动，最高 ROI）         │
│  ● CSS Selector 外部化到配置文件（支持远程热更新）                    │
│  ● 建立 API→Browser 线性偏差系数                                   │
│  ● 2-3 个测试账号/平台做轮转                                       │
│                                                                   │
│  决策信号（进入 Phase 2）：                                         │
│  → 单次分析耗时超过 20 分钟                                        │
│  → 日均分析请求超过 20 次                                          │
│  → 单账号限流频率超过 10%                                          │
├─────────────────────────────────────────────────────────────────┤
│  Phase 2: Browser 主力期（Q3-Q4 2026）                             │
│  ──────────────────────────────────────                           │
│  基础设施：8台云主机 + Redis + RDS，¥3,750/月                       │
│  采集能力：24 并发浏览器，5-8 分钟/全量分析                          │
│                                                                   │
│  ● Celery + Redis 分布式任务队列                                   │
│  ● Docker 化 Worker（每个含 Chromium + Browser Profile）           │
│  ● 账号池（10-15 个/平台）+ Round-Robin + LRU 轮转                 │
│  ● Cookie/Profile 存储迁移到 OSS 对象存储                          │
│  ● 持续监测模式（定时 CronJob 自动采集）                             │
│  ● DOM 变更自动检测（每 4-6 小时 Cron）+ 告警                      │
│  ● API 降级为"快速预览"和"趋势预警"                                │
│                                                                   │
│  决策信号（进入 Phase 3）：                                         │
│  → 日均分析超过 200 次                                             │
│  → 需要 SLA 保障（分析延迟 < 5 分钟）                               │
│  → 客户要求"持续监测"功能                                          │
├─────────────────────────────────────────────────────────────────┤
│  Phase 3: 多维可见度平台（2027）                                    │
│  ──────────────────────────────────────                           │
│  基础设施：Kubernetes (ACK) + 抢占式实例，¥9,000/月                  │
│  采集能力：每天 10,000+ 次查询                                      │
│                                                                   │
│  ● K8s + HPA 自动伸缩（基于 Redis Queue 深度）                     │
│  ● 抢占式实例降本 50-70%                                           │
│  ● 个性化 Profile 系统（A2 Persona → 浏览器画像物化）               │
│  ● DOM 三层防御：多 Selector → 自动检测 → VLM 截图兜底             │
│  ● 扩展到非中国平台（ChatGPT/Claude/Perplexity via BaaS）          │
│  ● 服务端日志分析（参考 Profound Agent Analytics）                   │
│  ● 统计显著性保障（每问题 N≥30 次重复采集）                         │
└─────────────────────────────────────────────────────────────────┘
```

### 5.2 关键技术决策

| 决策 | 选择 | 理由 | 可逆性 |
|------|------|------|--------|
| Playwright → Patchright | 一行 import 替换 | 反检测能力，零迁移成本 | 完全可逆（5分钟） |
| Selector 外部化 | JSON/YAML 配置文件 | 支持热更新，不需要重新部署 | 纯改进 |
| 任务队列 | Celery + Redis | Python 生态原生，成熟稳定 | 可逆但有成本 |
| 容器化 | Docker | Worker 隔离，环境一致性 | 可逆但不值得 |
| 弹性溢出 | Browserbase / Browserless | 处理非中国平台，按需付费 | 完全可逆 |
| Browser Profile 存储 | 阿里云 OSS | Worker 无状态化 | 可迁移 |

### 5.3 采集架构设计

```
                        ┌──────────────────────────────┐
                        │      Task Scheduler          │
                        │  (Redis Queue + Priority)    │
                        └──────┬───────────────────────┘
                               │
                  ┌────────────┼────────────────┐
                  ▼            ▼                ▼
           ┌──────────┐ ┌──────────┐    ┌──────────────┐
           │ Worker 1 │ │ Worker 2 │    │  Worker N    │
           │ (Docker) │ │ (Docker) │    │  (Docker)    │
           │ Patchright│ │ Patchright│   │  Patchright  │
           │ + Profile │ │ + Profile│   │  + Profile   │
           └──────┬───┘ └──────┬───┘    └──────┬───────┘
                  │            │                │
                  ▼            ▼                ▼
           ┌──────────────────────────────────────────┐
           │       Result Store (PostgreSQL)          │
           │  + Profile Store (OSS for Cookies)       │
           │  + Bias Calibration Model (per platform) │
           └──────────────────────────────────────────┘
```

**DOM 三层防御**：

| 层级 | 机制 | 触发条件 |
|------|------|---------|
| Layer 1 | 多 Selector 降级（已有 7 个 fallback） | 主 Selector 失效 |
| Layer 2 | 自动化 DOM 变更检测（4-6h Cron） + LLM 推断新 Selector | 核心 Selector 命中率低于阈值 |
| Layer 3 | 截图 + VLM（视觉语言模型）提取文本 | 所有 Selector 均失效 |

> 参考：[Patchright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)、[Browserbase](https://www.browserbase.com/pricing)、[Browserless](https://github.com/browserless/browserless)

---

## 第六章：个性化时代的战略准备

### 6.1 A2 Persona Agent：被低估的战略资产

Gumshoe AI 靠 "Persona-driven AI visibility tracking" 这一个差异化点拿到了 **$200万 Pre-seed**（2025年5月）。它的核心卖点不是"你在 AI 搜索中排第几"，而是"对于一个25岁的敏感肌女性用户，你在 AI 搜索中的表现如何"。

我们的 A2 Persona Agent 做的本质上是同一件事——生成用户画像，基于画像模拟搜索问题。而且我们有 Gumshoe 不具备的优势：
1. **中国市场 4 平台覆盖**
2. **Chat-first 交互**（Gumshoe 是 Dashboard 产品）

### 6.2 分阶段的个性化路线

```
阶段一（现在）：修好 A2，让画像生成可靠运行
  → reform-plan P0-1，成功率从 0% → 60-80%

阶段二（Phase 2）：画像驱动的分段可见度报告
  → 生成 3-5 个典型用户画像
  → 每个画像下的 BWVS 独立计算
  → "年轻女性 vs 年轻男性，品牌可见度差异是什么"

阶段三（Phase 3）：个性化可见度追踪
  → Browser Profile 物化（Cookie、历史记录、偏好设置）
  → 模拟不同"用户状态"的 AI 搜索体验
  → 这是 Browser 模式的又一个战略价值——API 无法模拟个性化
```

### 6.3 "干净基线"优先

架构师和 QA 一致认为：先用"干净 Profile"（新用户/匿名模式）做基线采集。这本身就是最有价值的数据——品牌方最想知道的是"一个普通新用户问这个问题时会看到什么"。个性化差异是锦上添花，不是当前必需品。

---

## 第七章：数据质量路线

### 7.1 当前问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| API 自身重复性 ~20% | 高 | 实验无法区分"渠道差异"和"天然随机性" |
| 品牌提取假阳性 | 中 | POLA/宝丽被识别为两个品牌 |
| 品牌提取假阴性 | 高 | 正则词典估计召回率 < 60% |
| 空集 Jaccard=1.0 | 中 | 虚假拉高均值 |
| "出现顺序=排名"假设 | 高 | AI 常按价格/肤质分类，非推荐度排序 |
| 单一领域（护肤品） | 高 | 无法推广结论到其他行业 |
| 样本量（16有效点） | 高 | 置信区间宽达 40+ 个百分点 |

### 7.2 提升优先级

| 优先级 | 改进项 | 预期效果 | 工期 |
|--------|--------|----------|------|
| **P0** | 修复空集 Jaccard=1.0 + POLA/宝丽重复 Bug | 消除已确认的数据错误 | 30分钟 |
| **P0** | **跑 API 自身重复性基线**（5题×5次） | 确定天然变异度，为后续实验奠基 | 2-3小时 |
| **P1** | LLM 替代正则词典做品牌提取 | 召回率 ~60% → 90%+ | 1天 |
| **P1** | 扩展到 3+ 行业领域 | 结论的推广性 | 2天 |
| **P2** | 样本量扩展到 140+ 有效对照 | 置信区间收窄到 ±5% | 1周 |
| **P2** | 配对实验设计 | 从根本上回答"渠道是否有影响" | 1-2周 |

### 7.3 配对实验设计（QA 推荐）

```
实验目标：区分"渠道引入的系统性差异"和"AI回答的天然随机性"

基线实验：
  20 题 × 5 次 API 重复 → intra-API Jaccard 基线
  20 题 × 5 次 Browser 重复 → intra-Browser Jaccard 基线

配对实验：
  30 题 × 5 行业 × 3 次 API + 3 次 Browser → inter-channel Jaccard

统计方法：
  paired t-test 比较 inter-channel vs intra-channel
  仅当 inter-channel 显著低于 intra-channel 时 → "渠道有系统性差异"

覆盖领域：
  护肤品(6) + 3C数码(6) + 汽车(6) + 餐饮(6) + 金融(6) = 30 题
```

---

## 第八章：执行路线图

### 8.1 总览

```
         2026 Q1          2026 Q2          2026 Q3-Q4         2027
         (现在)
    ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────┐
数据 │ P0 Bug修复    │  │ 配对实验      │  │ 140+ 样本量扩展   │  │ 统计显著  │
质量 │ API基线测试   │  │ LLM品牌提取   │  │ 多行业覆盖       │  │ 性保障    │
    └─────────────┘  └─────────────┘  └─────────────────┘  └──────────┘
    ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────┐
产品 │ 定位调整      │  │ BWVS 2.0     │  │ 双轨策略上线     │  │ Persona  │
    │ (排名→可见度)  │  │ 指标体系      │  │ 行动中心         │  │ 分段报告  │
    └─────────────┘  └─────────────┘  └─────────────────┘  └──────────┘
    ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────┐
架构 │ Patchright    │  │ 2台云主机     │  │ Celery + Docker  │  │ K8s 集群 │
    │ Selector外部化 │  │ 偏差校准模型  │  │ 账号池 + 轮转     │  │ 自动伸缩  │
    └─────────────┘  └─────────────┘  └─────────────────┘  └──────────┘
    ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐  ┌──────────┐
UX  │ 产品语言更新   │  │ 渐进式加载    │  │ 不确定性表达     │  │ 个性化   │
    │             │  │ 仪表盘重构    │  │ 竞品对比视图     │  │ 可见度   │
    └─────────────┘  └─────────────┘  └─────────────────┘  └──────────┘

    月成本：¥0           ¥900/月         ¥3,750/月          ¥9,000/月
```

### 8.2 本周立即执行（P0）

| # | 动作 | 负责 | 预计耗时 |
|---|------|------|---------|
| 1 | 修复品牌提取 Bug（空集 Jaccard、POLA/宝丽重复） | 开发 | 30分钟 |
| 2 | 跑 API 自身重复性基线实验（5题×5次×2平台） | QA + 开发 | 2-3小时 |
| 3 | 将 `from playwright` 替换为 `from patchright` | 开发 | 5分钟 |
| 4 | 更新产品文案（排名→可见度概率） | 产品 | 同步进行 |

---

## 第九章：未解决的分歧

| 分歧点 | 正方 | 反方 | 决策时机 |
|--------|------|------|---------|
| Browser 投入时机 | 产品/UX：方向比速度重要，尽早开始 | 架构/QA：先验证基线数据 | Phase 1 结束时 |
| A2 Persona 优先级 | 产品：P0 修好 A2 | 架构：推迟到 Phase 3 | Phase 2 开始时 |
| 初始客户选择 | 产品：国际品牌在华团队 | UX：国内 DTC 品牌 | PMF 验证阶段 |
| API 长期角色 | 产品：最终可能淘汰 | 架构：永远保留为快速信号通道 | Phase 2 数据验证后 |

---

## 附录：信息来源

### 行业与市场

- [SEO Services Market Projected to $171.77B by 2030 (PRNewswire)](https://www.prnewswire.com/news-releases/search-engine-optimization-seo-services-market-projected-to-reach-usd-171-77-billion-by-2030--growing-at-13-24-cagr-markntel-advisors-top-companies---semrush-holdings-inc-ahrefs-pte-ltd-moz-group-llc-302505098.html)
- [Ahrefs $149.1M Revenue (Latka)](https://getlatka.com/companies/ahrefs)
- [YOYI TECH Chinese GEO Ecosystem](https://en.yoyi.com.cn/unlock-the-mistery-of-chinese-geo-ecosystem.html)
- [Conductor AEO/GEO Benchmarks Report 2026](https://www.conductor.com/academy/aeo-geo-benchmarks-report/)
- [Gumshoe AI Pre-Seed $2M (Gumshoe Blog)](https://blog.gumshoe.ai/gumshoe-raises-2m-pre-seed-to-help-marketers-navigate-ai-search/)
- [Digiday Marketer's Guide to AEO 2026](https://digiday.com/marketing/digiday-research-the-marketers-guide-to-ai-applications-agentic-ai-ai-search-and-geo-aeo-in-2026/)

### 竞品分析

- [Profound Review (Nick Lafferty)](https://nicklafferty.com/reviews/profound-best-aeo-geo-platform-for-ai-search/)
- [Profound Pricing](https://www.tryprofound.com/pricing)
- [AEO Tools Compared (Redirects.net)](https://www.redirects.net/articles/aeo-tools-compared-airops-profound-peec-ai)
- [9 Best AEO Platforms (Profound)](https://www.tryprofound.com/blog/9-best-answer-engine-optimization-platforms)
- [Scrunch AI Pricing (Cairrot)](https://cairrot.com/alternatives/scrunch-ai-review-pricing-comparison/)
- [10 Best AEO Tools 2026 (NoGood)](https://nogood.io/blog/best-aeo-tools/)

### 产品参考

- [SEMrush AI Visibility Metrics](https://www.semrush.com/kb/1594-ai-seo-metrics)
- [SEMrush AI Share of Voice](https://www.semrush.com/blog/how-to-measure-ai-share-of-voice/)
- [SEMrush AI Visibility Toolkit](https://www.semrush.com/kb/1493-ai-visibility-toolkit)
- [Ahrefs Brand Radar](https://ahrefs.com/brand-radar)
- [SaaS Pricing Benchmark 2025 (Monetizely)](https://www.getmonetizely.com/articles/saas-pricing-benchmark-study-2025-key-insights-from-100-companies-analyzed)

### 技术架构

- [Patchright - Undetected Playwright (GitHub)](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
- [Browserbase Pricing](https://www.browserbase.com/pricing)
- [Browserless Self-hosted (GitHub)](https://github.com/browserless/browserless)
- [Top 10 Remote Browsers for AI Agents](https://o-mega.ai/articles/top-10-remote-browsers-for-ai-agents-full-2025-review)

### UX 设计

- [Fundamentals of Data Visualization - Uncertainty](https://clauswilke.com/dataviz/visualizing-uncertainty.html)
- [B2B SaaS Dashboard Design (UX Design)](https://uxdesign.cc/design-thoughtful-dashboards-for-b2b-saas-ff484385960d)
- [Carbon Design System Loading Patterns](https://carbondesignsystem.com/patterns/loading-pattern/)

### 个性化研究

- [A Survey of Personalized LLMs (arXiv 2502.11528)](https://arxiv.org/html/2502.11528v2)
- [Google Search Personalization 2024 (Williams Media)](https://williamsmedia.co/google-search-personalization)
- [Is Google Personalizing More? (Stan Ventures)](https://www.stanventures.com/news/is-google-personalizing-search-results-more-than-ever-1335/)

### 内部数据

- 实测结果：`aeo-platform/backend/scripts/results/` 下 13 个 JSON 文件
- 品牌提取脚本：`api_vs_browser_test.py` 第 82-115 行（词典）、第 133-139 行（Jaccard）
- 前置讨论报告：`docs/report-api-vs-browser-debate-2026-02-28.md`

---

*本文件为 Specta AI 发展方向的核心纲领性文件，后续所有功能开发应对照本文件的战略框架执行。*
