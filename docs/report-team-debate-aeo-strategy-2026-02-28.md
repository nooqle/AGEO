# Specta AI 战略方向 — 团队 Debate 综合报告

> **日期**：2026-02-28
> **参与角色**：产品经理（Marty Cagan）、架构师（Martin Fowler）、QA（James Bach）、UX（Don Norman）
> **核心议题**：借鉴 SEO 二十年发展经验，为 Specta AI 的 AEO 方向做出战略决策
> **前置报告**：`report-api-vs-browser-debate-2026-02-28.md`、`report-seo-lessons-for-aeo-2026-02-28.md`

---

## 零、QA 的颠覆性发现（本次讨论最重要的发现）

在团队讨论开始前，James Bach（QA）对原始数据做了严格审查，发现了一个**颠覆前述所有假设**的关键事实：

### API 自身的重复一致性只有 ~20%

Bach 从测试目录中找到了同一问题的多次迭代数据。Kimi 问题1（"抗蓝光护肤品"）被 API 调用了3次：

| 运行 | 返回品牌 |
|------|---------|
| 第1次 | 黛珂, The Ordinary, 科颜氏, 理肤泉, CPB, OLAY, 雅漾（7个） |
| 第2次 | 修丽可, 雅诗兰黛, OLAY, The Ordinary, 珀莱雅, CeraVe, 理肤泉, 薇诺娜, 雅漾, Paula's Choice（10个） |
| 第3次 | 雅诗兰黛, 优色林, 修丽可, 溪木源, The Ordinary（5个） |

三次之间的品牌重叠率：**9% ~ 21%**。

**这意味着：API 对自己说的话都不到 20% 一致，而 API vs Browser 的重叠率反而有 48%。**

> **结论：我们此前以为测到的是"渠道差异"（API vs Browser），但实际上测到的是 AI 回答本身的天然随机性。用什么渠道采集是第二位的问题；AI 回答不稳定才是第一位的问题。**

Bach 同时发现了品牌提取代码中的确认 Bug：
- POLA/宝丽被识别为两个不同品牌（假阳性）
- 空集时 Jaccard=1.0 的处理逻辑虚假拉高了均值
- 60个品牌的正则词典估计召回率低于 60%（大量小众品牌漏检）
- "出现顺序=排名"的假设不合理（AI 回答常按价格/肤质分类，非推荐度排序）

**数据质量评级：D（不可用于决策）。** 但这不是坏消息——这恰恰证明了产品存在的价值（详见第三部分）。

---

## 一、SEO 的三个关键历史教训

### 教训1：数据采集从来都是靠"浏览器"

Google 从未提供过 SERP 排名的官方 API。Ahrefs（年收入 $1.49亿）和 SEMrush（年收入 $3.77亿）从第一天起就靠爬虫抓取。2025年9月 Google 砍掉 `&num=100` 参数，运营成本一夜翻 10 倍——Ahrefs 一个月内恢复了 Top 100 追踪。

**对应到 AEO**：Profound（行业龙头，红杉 $3500万投资）明确选择了前端抓取（Browser），官方表述："追踪真实用户看到的，不是 API 响应"。所有主流 AEO 工具都用 Browser/前端抓取，无一依赖 API。

### 教训2：个性化没有杀死 SEO，反而催生了更大市场

Google 2009年推个性化搜索后，SEO 市场从 ~$200亿 增长到了 **$749亿**（2025），CAGR 12-17%。原因：越复杂的环境，品牌方越需要专业工具。

**对应到 AEO**：ChatGPT 已推出 Memory with Search（2025年4月），Google AI Mode 将在2025年夏季全面个性化。这对我们是机会而非威胁。

### 教训3：产品定位从"精确排名"转型为"可见度概率"

SEO 工具经历了三次转型：精确排名 → 可见度分数 → 内容质量诊断（E-E-A-T）。SEMrush 的成功不是因为爬虫最强，而是把数据包装成所有部门都能理解的可见度仪表盘。

---

## 二、四方辩论：核心议题

### 议题一：API vs Browser，到底该信谁？

| 角色 | 立场 | 核心论据 |
|------|------|---------|
| **QA** | 问题被问错了 | API 自身一致性仅 ~20%，"信谁"是伪命题——两者都不够稳定，需要多次采样取统计分布 |
| **产品** | Browser 是方向 | 品牌方买的是"消费者看到什么"，不是"模型底层知识"。Profound 明确选 Browser 并拿到红杉投资 |
| **架构** | 混合架构是务实选择 | Browser 单次 20-70秒，资源消耗是 API 的 100-350 倍。短期 API 主力 + Browser 校准，长期渐进演进 |
| **UX** | 用户不关心你怎么采集 | 关键是产品如何表达不确定性——诚实但不吓人，增强而非削弱信任 |

**共识**：
> Browser 方向正确（行业验证），但 QA 的发现改变了讨论的本质——**真正的挑战不是"用哪个渠道"，而是"AI 回答天然不稳定，如何在此基础上构建可信的产品"**。答案是统计聚合：多次采样 → 计算分布 → 展示概率。

### 议题二：个性化会不会打破我们的商业价值？

| 角色 | 立场 | 核心论据 |
|------|------|---------|
| **产品** | 是机会 | Gumshoe AI 靠 "Persona-driven AI visibility" 拿到 $200万 Pre-seed。我们的 A2 Persona Agent 做的是同一件事，而且覆盖中国平台 |
| **架构** | 技术可行但推迟到 Phase 3 | 个性化 Profile 预热成本极高（6 画像 × 4 平台 × 50 条对话 = 10 小时预热），先用"干净 Profile"做基线 |
| **QA** | 先证明基线有价值 | 如果 API 自身一致性只有 20%，连基线都不稳定，讨论个性化差异为时过早 |
| **UX** | 引入"一致性分数"新维度 | 衡量品牌在不同场景/画像中被推荐的一致程度——高一致性 = 品牌心智强，这对品牌方有独特价值 |

**共识**：
> 个性化是机会而非威胁（SEO 历史验证），A2 Persona Agent 是被低估的战略资产。但执行上分阶段：先做"干净基线"→ 再做"分画像可见度"。

### 议题三：中国市场空白——我们的真正护城河在哪？

**产品经理的关键发现**：

> 所有现有 AEO 竞品（Profound、Scrunch、Peec、Otterly）全部聚焦英文市场和西方 AI 平台。**中国 AI 搜索市场（Kimi/豆包/DeepSeek/混元）目前几乎没有专业的 AEO 监测工具。**

| 数据点 | 值 | 来源 |
|--------|-----|------|
| 中国 GEO 市场规模（2025 H1） | **$36.5亿** | YOYI TECH |
| YoY 增长率 | **240%** | 同上 |
| 豆包 MAU | **1.63亿** | 公开数据 |
| 85% 企业计划增加 AI 搜索优化投入 | 2026 | Conductor 报告 |

**四方一致认为的三重护城河**：

1. **中国 4 平台覆盖**（Kimi/豆包/DeepSeek/混元）——竞品无法快速复制
2. **Chat-first 交互**——品牌方不同部门用自然语言提问，不需要学复杂 Dashboard
3. **Persona-driven 分析**（A2）——在个性化时代变为核心引擎

---

## 三、QA 发现的深层含义：为什么"AI 不稳定"反而是好消息

Bach 的发现（API 自身一致性 ~20%）看似是坏消息，但产品经理和 UX 同时指出了它的正面含义：

### 对产品价值的影响

| 如果 AI 回答是稳定的（假设） | 如果 AI 回答是不稳定的（事实） |
|---|---|
| 品牌方自己打开网页查一次就知道排名 | 品牌方自己查到的只是一个随机快照，没有代表性 |
| 一次性报告就够了 | 必须持续监测，多次采样才有意义 |
| 工具的价值有限——用户自己也能做 | **工具的价值极高——只有工具能做大规模统计聚合** |
| 竞争壁垒低 | 竞争壁垒高（需要基础设施支撑多次采样） |

> **核心洞察：AI 回答的不稳定性不是产品的敌人，而是产品存在的理由。** 正因为不稳定，品牌方才需要一个专业工具来回答"在过去1000次提问中，我的品牌出现概率是多少"。这和天气预报完全一样——天气越不确定，气象服务越有价值。

### 产品叙事的转变

**旧叙事**："我们帮你看在AI搜索中排第几"（确定性思维）

**新叙事**："AI 搜索的推荐每次都不同——我们帮你理解你的品牌在这个动态环境中的真实可见度"（概率性思维）

---

## 四、战略方向：全员共识

### 4.1 产品定位（立即调整）

**目标市场**：中国 AI 搜索可见度监测平台

**核心定位**：
> 不说"你在豆包上排第3"，而说"当消费者在 AI 平台上搜索护肤品时，你的品牌有 67% 的概率被提及，其中 38% 的概率被首位推荐"

**定价建议**（产品经理）：
| 版本 | 月价 | 核心能力 | 目标客户 |
|------|------|---------|---------|
| 基础版 | ¥999 | 1 品牌，50 Prompt，2 平台（API） | 初次尝试 AEO 的品牌 |
| **专业版** | **¥2,499** | **3 品牌，200 Prompt，4 平台，画像分析** | **认真做 AEO 的品牌市场部** |
| 旗舰版 | ¥4,999 | 10 品牌，500 Prompt，趋势监测，部门视角 | 品牌集团或 Agency |

预估毛利率：~85%（变动成本 ~¥360/月/专业版客户）。

### 4.2 核心指标体系 BWVS 2.0（产品经理设计）

```
BWVS = 0.35×提及率 + 0.25×提及位置分 + 0.15×情感得分 + 0.15×平台覆盖率 + 0.10×引用质量分
```

关键变化：从"单次快照排名"到"统计概率指标"，每个数字后跟一句人话解释"所以呢"。

### 4.3 技术架构演进路线（架构师设计）

```
Phase 1（现在→3个月，¥900/月）
├── API 为日常快速采集主力
├── Browser 每周做校准采样（50-100题/平台）
├── Patchright 替换 Playwright（一行 import，最高 ROI）
├── Selector 外部化配置（支持热更新）
├── 2台云主机，6并发浏览器，15-20分钟/全量分析
└── 建立 API→Browser 线性偏差系数

Phase 2（3-6个月，¥3,750/月）
├── Celery + Redis 分布式任务队列
├── Docker 化 Worker（每个含 Chromium + Profile）
├── 8台云主机，24并发浏览器，5-8分钟/全量分析
├── 账号池（10-15个/平台）+ 轮转策略
└── 持续监测模式（定时自动采集）

Phase 3（6-12个月，¥9,000/月）
├── Kubernetes + 自动伸缩（抢占式实例降本50-70%）
├── 个性化 Profile 系统（A2 Persona → 浏览器画像）
├── DOM 三层防御：多selector → 自动检测 → VLM截图兜底
├── 扩展到非中国平台（ChatGPT/Claude/Perplexity via BaaS）
└── 每天 10,000+ 次查询能力
```

### 4.4 UX 信息架构（UX 设计）

**核心设计原则**：帮用户从"我排第几"的旧心智模型，迁移到"我的 AI 可见度健康状况如何"的新心智模型。

**三个关键设计方案**：

**1. 三层不确定性表达**

| 层级 | 受众 | 展示方式 |
|------|------|---------|
| 第一层 | 大多数用户 | 信号强度图标（████▒）+ "基于 N 个样本" |
| 第二层 | 好奇的用户 | 展开面板：API采集值 vs Browser采集值 + 自然语言解释 |
| 第三层 | 专业用户 | 趋势图上的置信区间阴影带 |

**2. 渐进式加载（解决 Browser 慢的 UX 问题）**

```
阶段一（0-3秒）：Skeleton 屏 + "正在启动分析..."
阶段二（30秒-2分钟）：API 数据先到先展示 + 标注"浏览器深度采集中..."
阶段三（5-10分钟）：Browser 数据融合，Toast 通知"深度采集完成"
```

**3. 行动中心**

```
紧急（红）：品牌在某平台被竞品替代，本周下降12%
重要（橙）：情感倾向偏中性，缺乏正面评价内容
优化机会（蓝）：增加FAQ结构化内容可提升AI抓取率
已完成（灰）：上周建议"优化品牌描述" → BWVS +3.2 ✓
```

每条建议包含：影响量化（BWVS +8.5）、自然语言问题描述、可执行动作列表、效果反馈循环。

### 4.5 数据质量提升优先级（QA 设计）

| 优先级 | 改进项 | 预期效果 | 工期 |
|--------|--------|----------|------|
| **P0** | 修复空集 Jaccard=1.0 + POLA/宝丽重复 Bug | 消除已确认的数据错误 | 30分钟 |
| **P0** | **跑 API 自身重复性基线**（5题×5次） | 确定 AI 回答的天然变异度 | 2-3小时 |
| **P1** | LLM 替代正则词典做品牌提取 | 召回率从 ~60% 提升到 90%+ | 1天 |
| **P1** | 扩展到 3+ 行业领域（护肤/3C/汽车/餐饮/金融） | 结论的推广性 | 2天 |
| **P2** | 样本量扩展到 140+ 有效对照 | 置信区间收窄到 ±5% | 1周 |
| **P2** | 配对实验（区分渠道差异 vs 天然随机性） | 从根本上回答"渠道是否有影响" | 1-2周 |

**QA 的实验设计建议**：
- 20 题 × 5 次 API 重复 → 测量 API 自身基线
- 20 题 × 5 次 Browser 重复 → 测量 Browser 自身基线
- 30 题 × 3 次 API + 3 次 Browser × 5 行业领域 → 配对实验
- 用 paired t-test 比较 inter-channel vs intra-channel Jaccard
- 只有 inter-channel 显著低于 intra-channel 时，才能得出"渠道有系统性差异"的结论

---

## 五、未解决的分歧

| 分歧点 | 正方 | 反方 |
|--------|------|------|
| **Browser 投入时机** | 产品/UX：方向比速度重要，尽早开始 | 架构/QA：先验证数据基线，再投入基础设施 |
| **A2 Persona 优先级** | 产品：P0 修好 A2 是最高优先级 | 架构：推迟到 Phase 3，先用干净 Profile |
| **初始客户选择** | 产品：国际品牌在华团队（已有 SEO 认知） | UX：国内 DTC 品牌（决策链更短） |
| **商业模式** | 产品：SaaS 订阅（¥999-4999/月） | 全员认同，无反对意见 |
| **API 长期角色** | 产品：最终可能淘汰 | 架构：永远保留为快速信号通道 |

---

## 六、最终建议：三句话总结

1. **方向**：Browser-first + 中国 4 平台覆盖 + Chat-first 交互 + Persona-driven 分析 = 全球 AEO 赛道中独一无二的定位。

2. **节奏**：先跑 QA 的基线实验（P0，本周就做），证明数据基础可靠，再按架构师的三阶段路线演进。产品定位调整（"排名"→"可见度概率"）可以立即开始，不依赖技术改造。

3. **核心认知**：AI 回答的不稳定性不是 Bug，是 Feature——这是我们产品存在的根本理由。品牌方越是无法通过一次提问得到确定答案，就越需要专业工具做统计聚合和趋势追踪。

---

## 附录：信息来源

### 团队成员引用的外部来源

**产品（Marty Cagan）**：
- [SEMrush AI Visibility Metrics](https://www.semrush.com/kb/1594-ai-seo-metrics)
- [SEMrush AI Share of Voice Methodology](https://www.semrush.com/blog/how-to-measure-ai-share-of-voice/)
- [Profound Pricing & Review](https://getmint.ai/resources/profound-review)
- [Gumshoe AI Pre-Seed Funding](https://blog.gumshoe.ai/gumshoe-raises-2m-pre-seed-to-help-marketers-navigate-ai-search/)
- [YOYI TECH Chinese GEO Ecosystem](https://en.yoyi.com.cn/unlock-the-mistery-of-chinese-geo-ecosystem.html)
- [Conductor AEO/GEO Benchmarks Report 2026](https://www.conductor.com/academy/aeo-geo-benchmarks-report/)

**架构（Martin Fowler）**：
- [Patchright - Undetected Playwright](https://github.com/Kaliiiiiiiiii-Vinyzu/patchright)
- [Browserbase Pricing](https://www.browserbase.com/pricing)
- [Browserless Self-hosted Docker](https://github.com/browserless/browserless)
- [Top 10 Remote Browsers for AI Agents](https://o-mega.ai/articles/top-10-remote-browsers-for-ai-agents-full-2025-review)
- [Peec AI Documentation](https://docs.peec.ai/intro-to-peec-ai)

**QA（James Bach）**：
- 项目内测试数据：`D:\AGEO\aeo-platform\backend\scripts\results\` 下 13 个 JSON 文件
- 品牌提取脚本审查：`api_vs_browser_test.py` 第 82-115 行词典定义，第 133-139 行 Jaccard 计算

**UX（Don Norman）**：
- [SEMrush AI Visibility Toolkit](https://www.semrush.com/kb/1493-ai-visibility-toolkit)
- [Ahrefs Brand Radar](https://ahrefs.com/brand-radar)
- [Fundamentals of Data Visualization - Uncertainty](https://clauswilke.com/dataviz/visualizing-uncertainty.html)
- [B2B SaaS Dashboard Design](https://uxdesign.cc/design-thoughtful-dashboards-for-b2b-saas-ff484385960d)
- [Carbon Design System Loading Patterns](https://carbondesignsystem.com/patterns/loading-pattern/)

---

*报告完。各角色完整分析详见独立报告文件。*
