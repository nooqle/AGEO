# PRD: Specta 品牌圈层图谱与可操作画布改版

> 日期：2026-06-17  
> 状态：Draft v0.4 with implementation guardrails  
> 范围：品牌空间信息架构、圈层图谱、可操作画布、节点化 Workflow、图谱更新、报告解读、资产归档  
> 非目标：本文不定义最终视觉稿、不替代后端详细技术设计、不直接实现代码、不把安利专属实体词表硬编码为通用规则

## 0. 一句话结论

Specta 的主体验从“Chat 驱动分析、Canvas 展示报告”改为：

```text
可操作画布驱动品牌圈层图谱更新。
每次图谱更新都会沉淀中间资产，并生成一份围绕圈层状态变化的报告解读。
```

新的主心智：

1. 品牌不是一次性分析对象，而是一个长期增长的实体关系库。
2. 画布不是报告容器，而是用户组合、运行、调试品牌情报 Workflow 的操作空间。
3. 画布唯一核心交付物是 Graph Update，即品牌圈层图谱的状态更新。
4. 报告不是主界面交付物，而是对某次图谱更新结果的业务解读。
5. AI 平台抓取、文档上传、手动问题列表、周期监控都是不同来源的圈层更新方式。

## 1. 背景与问题

当前 Specta 已经具备多项能力：

1. Chat 可以发起品牌分析。
2. Orchestrator 可以推进 A3 问题生成、A4 回答抓取、A5 指标和报告。
3. Canvas 可以承载 workflow、questionList、fetchResults、report 等交付物。
4. 后端已有 ontology / brand world / artifact / run 等方向的设计基础。
5. 安利方向已经探索了品牌实体词表，用于定义什么可以被抽取为实体、如何识别关系、如何让用户审阅。

但当前主体验仍然有三个断点：

1. **报告过重**：用户容易以为系统的核心价值是生成一份报告，而不是持续维护品牌在 AI 世界里的关系半径。
2. **图谱过晚**：图谱经常被当作报告里的一个输出，而不是品牌长期资产的主界面。
3. **过程不可操作**：现有 workflow 虽有节点和阶段，但用户不能像操作画布一样替换、组合、删除节点，例如把“问题模拟”替换为“手动上传问题列表”。

新的改版要解决的问题：

```text
用户进入一个品牌后，应该直接看到品牌圈层状态；
用户通过画布更新这个圈层；
系统动态展示外部信息如何被折叠进品牌实体关系库；
报告只负责解释这次圈层为什么变化。
```

### 1.1 与既有设计的关系

本 PRD 不推翻已有品牌知识图谱和任务中枢设计，而是调整主体验和用户心智：

1. `design-specta-ai-brand-knowledge-graph-2026-05-22.md` 已经定义了品牌世界、图谱事实网络和四类投影。本 PRD 继承其“长期事实层”的方向，但把前台从页签式 Dashboard 重心迁到品牌圈层图谱。
2. `design-brand-intelligence-run-center-2026-05-25.md` 已经定义了后台任务中枢。本 PRD 继承“任务不依赖 Chat 常驻”的原则，但将任务的用户可见操作面升级为 Board / Node / Graph Update。
3. `amway-entity-lexicon-v0.1-2026-06-15.md` 是品牌实体词表样例。本 PRD 将它上升为通用产品能力：每个品牌都应有可审阅、可增长的实体词表，作为圈层图谱的种子库。
4. 现有 Canvas / Artifact 能力不直接废弃，但需要重新分工：Canvas 变成操作画布，Artifact 中间产物进入 Assets，Report 进入 Reports，并围绕 Graph Update 解读。

## 2. 产品目标

### 2.1 目标

1. 建立新的品牌空间信息架构：`Graph / Boards / Assets / Reports`。
2. 将全景分析、用户画像分析、手动问题分析、文档上传分析、周期监控沉淀为 Workflow Template。
3. 让用户能在画布中查看节点、替换节点、连接节点、运行节点、重跑节点。
4. 让每次节点运行都以 Graph Patch Stream 的形式动态更新品牌圈层图谱。
5. 将中间产物归档到 Assets 文件夹，不再在主界面堆叠展示。
6. 将报告定义为 Graph Update Report，即围绕本次圈层状态变化的解读。
7. 在视觉上形成“动态建模”的科技感，但继续遵守 Specta light-first、evidence-led、paper-neutral 的设计系统。

### 2.2 非目标

本轮不做：

1. 不把产品做成通用低代码工作流平台。
2. 不开放任意自由编程节点。
3. 不把所有原始回答、抽取记录、日志都暴露在主界面。
4. 不把报告继续作为 Canvas 主交付物。
5. 不用黑底霓虹、紫蓝渐变、发光卡片制造科技感。
6. 不在第一版解决所有品牌的通用实体本体自动生成问题。

## 3. 核心概念定义

### 3.1 Brand Space

一个品牌的长期工作空间。

```text
Brand Space
├─ Graph：品牌圈层图谱
├─ Boards：可操作画布
├─ Assets：中间资产文件夹
└─ Reports：图谱更新解读报告
```

Brand Space 是用户进入品牌后的一级语境，不再默认进入 Chat 或某份报告。

### 3.2 Entity Lexicon

品牌实体词表，用于定义本品牌希望识别、追踪、审阅和增长的实体边界。

实体词表包含：

1. 中心品牌。
2. 子品牌 / 产品资产。
3. 产品品类。
4. 解决方案。
5. 战略词。
6. 人群、场景、社群、触点。
7. 证据资产。
8. 风险认知。
9. 竞品实体。
10. 别名和触发词。
11. 推荐关系类型。

用户可以审阅：

1. 新实体是否保留。
2. 实体是否合并。
3. 别名是否归错。
4. 风险词是否进入风险圈。
5. 战略词是否进入目标圈或差距圈。

### 3.3 Brand Circle Graph

品牌圈层图谱是实体关系库的可视化投影。

它不是普通关系图，也不是报告插图。它回答：

```text
哪些实体正在靠近品牌？
哪些实体仍在外圈等待验证？
哪些实体被竞品占据？
哪些风险认知正在靠近？
哪些战略词没有被 AI 回答接住？
```

建议默认圈层：

| 圈层 | 含义 | 示例 |
| --- | --- | --- |
| 中心 | 当前品牌 | 安利 |
| 内圈 | 已被 AI 回答稳定连接的强实体 | 纽崔莱、营养早餐、体重管理 |
| 中圈 | 有出现但连接弱或不稳定的实体 | 关系抗衰、社群陪伴 |
| 外圈 | 品牌希望建立但 AI 暂未接住的目标实体 | 长寿时代、丰盛人生支持体系 |
| 竞品圈 | 被竞品占据或强对照的实体 | 汤臣倍健、Swisse、康宝莱 |
| 风险圈 | 争议、误解、合规风险 | 传销/拉人头、夸大功效、智商税 |

### 3.4 Board

画布是可操作的 Workflow 空间。

画布负责：

1. 承载节点。
2. 展示节点之间的数据流。
3. 允许运行、暂停、重跑、替换节点。
4. 显示每个节点对图谱产生的更新。
5. 触发中间资产归档。

画布不负责：

1. 长期存放报告正文。
2. 长期展示全部原始回答。
3. 替代品牌圈层图谱作为主界面。

### 3.5 Node

节点是可组合的能力组件。

节点必须有明确输入、输出和图谱写入边界。

示例：

| 节点 | 输入 | 输出 | 图谱影响 |
| --- | --- | --- | --- |
| 品牌输入 | 用户输入 / 品牌档案 | BrandSeed | 创建或更新中心品牌 |
| 实体词表导入 | 文档 / 表格 | EntityLexicon | 新增候选实体和别名 |
| 问题模拟 | BrandSeed / EntityLexicon | QuestionSet | 新增问题组 |
| 手动上传问题 | Excel / CSV / 文本 | QuestionSet | 新增问题组 |
| AI 回答抓取 | QuestionSet / Platforms | AnswerSet | 形成回答资产 |
| 实体关系抽取 | AnswerSet / EntityLexicon | EntityRelationSet | 产生 Graph Patch |
| 圈层更新 | EntityRelationSet | GraphUpdate | 更新圈层状态 |
| 报告解读 | GraphUpdate | CircleReport | 解释本次变化 |

### 3.6 Graph Update

Graph Update 是画布的核心交付物。

它描述本次运行对品牌圈层造成了什么变化：

1. 新增哪些实体。
2. 强化哪些连接。
3. 弱化哪些连接。
4. 哪些目标实体仍未被接住。
5. 哪些风险靠近。
6. 哪些竞品占位增强。
7. 哪些实体需要用户审阅。

### 3.7 Assets

Assets 是中间产物文件夹。

包括：

1. 上传文档。
2. 问题列表。
3. AI 平台回答。
4. 原始抽取结果。
5. 实体关系抽取表。
6. 图谱更新记录。
7. 导出文件。

默认不在主界面铺开，但必须可追溯、可下载、可被报告和图谱引用。

### 3.8 Circle Report

报告是图谱更新的业务解读。

它回答：

```text
这次圈层状态发生了什么变化？
为什么这些实体靠近或疏远？
哪些战略词被 AI 接住？
哪些目标还在外圈？
哪些竞品正在占据相关场景？
下一次应该用什么画布继续更新？
```

报告不再承担完整过程展示，也不再是画布主交付物。

## 4. 信息架构

### 4.1 品牌空间顶部导航

建议一级导航：

```text
Graph | Boards | Assets | Reports
```

默认进入 `Graph`。

### 4.2 Graph

Graph 是品牌空间首页。

页面组成：

1. 圈层图谱主视图。
2. 顶部 Lens 切换。
3. 右侧实体 Inspector。
4. 底部最近 Graph Update Timeline。
5. 更新前 / 更新后 / 只看新增 / 只看增强 / 只看风险 等筛选。

### 4.3 Boards

Boards 管理多张画布。

画布类型：

1. 全景抓取画布。
2. 用户画像抓取画布。
3. 手动问题抓取画布。
4. 文档上传建模画布。
5. 周期监控画布。
6. 自定义画布。

### 4.4 Assets

Assets 是文件夹视图。

建议分组：

```text
Questions
Answers
Uploads
Extractions
Graph Updates
Exports
```

### 4.5 Reports

Reports 是报告文件夹。

报告按以下维度组织：

1. 品牌。
2. 画布。
3. Graph Update。
4. 时间。
5. 版本。
6. 运行类型。

打开报告时进入独立 Reader。Reader 内可以定位回 Graph Update 或 Board Run。

## 5. 用户旅程

### 5.1 新品牌初始化

```text
用户创建品牌
  -> 进入空 Graph
  -> 系统提示导入品牌资料或选择初始化模板
  -> 用户上传官网资料、品牌介绍、产品资料或历史报告
  -> 文档上传建模画布运行
  -> 系统抽取初始实体词表
  -> 用户审阅候选实体、别名和风险词
  -> Graph 生成初始圈层
  -> Reports 生成初始圈层解读
```

成功标准：

1. 用户知道品牌初始圈层由哪些资料生成。
2. 用户能审阅和修正实体词表。
3. 初始 Graph 不要求 AI 抓取完成后才存在。

### 5.2 全景 AI 抓取更新

```text
用户在 Graph 看到当前圈层
  -> 选择“运行全景抓取”
  -> 打开全景画布
  -> 节点执行：问题生成 / 四平台并行抓取 / 实体匹配 / 圈层更新 / 报告解读
  -> Graph 实时浮现新增候选实体和连接变化
  -> 用户在更新队列中审阅关键变化
  -> Graph 稳定为更新后状态
  -> Reports 新增本次圈层解读
```

### 5.3 替换问题来源

```text
用户打开全景画布
  -> 删除“问题模拟”节点
  -> 从节点库拖入“手动上传问题列表”
  -> 系统校验该节点输出 QuestionSet
  -> 用户上传 Excel
  -> 下游“AI 回答抓取”节点保持可运行
  -> 执行后更新 Graph
```

关键原则：

```text
只要节点输出类型兼容，下游节点不应关心问题来自模拟还是上传。
```

### 5.4 文档上传更新

```text
用户上传品牌白皮书、产品手册或活动资料
  -> 文档解析节点抽取实体和关系
  -> 实体匹配节点对齐现有词表
  -> 发现新实体、别名、冲突和战略词
  -> 用户审阅
  -> Graph 更新品牌目标圈、资产圈或证据资产
  -> Reports 生成资料更新解读
```

### 5.5 回访查看

```text
用户再次进入品牌空间
  -> 默认看到 Graph 当前圈层状态
  -> Timeline 显示最近 Graph Update
  -> 用户点击“上次 AI 抓取更新”
  -> Graph 进入 before/after diff
  -> 用户查看本次报告解读
  -> 用户决定继续运行一个画布或开启周期监控
```

### 5.6 报告查看

```text
用户进入 Reports
  -> 打开某次圈层更新报告
  -> 阅读本次变化摘要
  -> 点击“定位到图谱”
  -> Graph 高亮本次变化实体
  -> 点击“查看生成画布”
  -> Board 打开对应 run 的节点状态
```

## 6. 画布交互需求

### 6.1 画布基础能力

画布必须支持：

1. 创建新画布。
2. 从模板创建画布。
3. 添加节点。
4. 删除节点。
5. 替换节点。
6. 连接节点。
7. 校验节点输入输出兼容性。
8. 运行整张画布。
9. 运行单个节点。
10. 从失败节点继续。
11. 查看节点输入、输出、状态、资产引用和图谱影响。

### 6.2 节点状态

节点状态：

| 状态 | 含义 |
| --- | --- |
| idle | 未运行 |
| ready | 输入已满足，可运行 |
| blocked | 缺少输入或需要用户处理 |
| running | 正在执行 |
| writing_asset | 正在写入中间资产 |
| matching_graph | 正在匹配实体关系 |
| updating_graph | 正在产生图谱更新 |
| needs_review | 需要用户审阅 |
| completed | 完成 |
| failed | 失败 |

### 6.3 节点 Inspector

选中节点后，右侧 Inspector 展示：

1. 节点名称和状态。
2. 输入对象。
3. 输出对象。
4. 运行日志摘要。
5. 中间资产链接。
6. 图谱更新摘要。
7. 错误和重试入口。
8. 可替换节点建议。

### 6.4 节点库

第一版节点库建议：

| 分类 | 节点 |
| --- | --- |
| 输入 | 品牌输入、文档上传、问题上传、平台选择 |
| 生成 | 问题模拟、用户画像生成、实体词表生成 |
| 抓取 | AI 回答抓取、官网内容读取 |
| 解析 | 实体抽取、关系抽取、别名匹配 |
| 图谱 | 圈层更新、风险圈更新、竞品圈更新 |
| 输出 | 报告解读、导出 |
| 监控 | 周期计划、快照对比 |

### 6.5 默认画布视觉方案：并行平台机架

本轮原型默认采用“并行平台机架”方向。

目标不是让画布更炫，而是让用户能直接看懂：

```text
哪些节点属于输入？
哪些节点正在并行抓取？
哪些节点正在抽取实体？
哪些节点正在写入图谱？
哪些节点需要人工审阅？
```

默认布局：

```text
Brand Entity Seed
  -> Question Source
  -> AI Platform Fetch Group
       ├─ ChatGPT Fetch
       ├─ DeepSeek Fetch
       ├─ Kimi Fetch
       └─ Doubao Fetch
  -> Answer Normalize
  -> Entity Relation Extraction
  -> Entity Match
  -> Graph Patch
  -> Circle Report
```

画布要求：

1. 节点默认保持紧凑，宽度建议 `180-220px`，高度建议 `72-110px`。
2. 不使用大卡片式节点；节点应更接近 ComfyUI / React Flow 的密度。
3. 节点通过顶部色条、端口色、状态点和进度条表达类型，不用整块高饱和底色。
4. 并行节点用轻量 group boundary 包裹，明确这是一组并发任务。
5. 右侧 Inspector 解释选中节点，不抢占画布主视觉。
6. 图谱预览在画布中是次级元素，除非用户切换到 Graph 首页。

节点类型色建议：

| 节点类型 | 用途 | 视觉编码 |
| --- | --- | --- |
| Input / Upload | 品牌输入、文档上传、问题上传 | 暖琥珀色条和输入端口 |
| Generate / Prepare | 问题模拟、画像生成、问题整理 | 中性橄榄或石墨色条 |
| Fetch | ChatGPT、DeepSeek、Kimi、Doubao 等平台抓取 | 冷灰蓝色条和独立进度 |
| Extract / Match | 实体抽取、关系抽取、别名匹配 | Specta Evidence Teal `#1F7A6B` |
| Review / Conflict | 冲突、风险、待审阅 | 克制玫瑰红状态点 |
| Graph Update | Graph Patch、圈层应用 | 深绿色状态条 |
| Output | 报告解读、导出 | 中性灰 + 状态完成标记 |

动态视觉语义：

| 动态元素 | 表达含义 |
| --- | --- |
| 节点边缘细光 | 节点正在运行 |
| 节点内进度条 | 当前节点进度 |
| 连线上的小光点 | 数据正在流向下游 |
| 并行组内多条进度 | 多平台并行抓取状态 |
| Graph Patch 流线 | 更新正在写入图谱 |
| 状态点闪烁 | 需要关注，不代表装饰光效 |

### 6.6 四平台并行抓取交互

AI 回答抓取节点在画布上不应只呈现为一个黑箱节点。第一版至少要支持展开为四个平台并行节点：

```text
AI Platform Fetch Group
├─ ChatGPT Fetch：running / 72% / 36 answers
├─ DeepSeek Fetch：running / 64% / 32 answers
├─ Kimi Fetch：running / 48% / 24 answers
└─ Doubao Fetch：retrying / 41% / 20 answers
```

并行组行为：

1. 默认折叠时显示总进度、平台数、成功数、失败数。
2. 展开后显示每个平台的独立节点、进度、错误、输出资产。
3. 单个平台失败不应阻塞已完成平台写入 Assets。
4. 下游 `Answer Normalize` 节点可以等待全部完成，也可以在策略允许时增量处理已完成平台。
5. Inspector 需要同时支持“选中平台节点”和“选中并行组”两种视角。
6. Graph Patch Stream 中必须保留平台来源，避免实体变化失去出处。

## 7. 动态更新需求

动态是本次改版的关键体验。系统必须让用户感到：

```text
外部信息正在被实时吸收、匹配、折叠进品牌圈层。
```

### 7.1 Graph Patch Stream

画布执行过程中，系统持续产生 Graph Patch Stream。

事件类型：

| 事件 | 说明 |
| --- | --- |
| node_started | 节点开始 |
| node_progress | 节点进度和计数 |
| asset_written | 中间资产写入 |
| entity_detected | 发现候选实体 |
| entity_matched | 匹配到已有实体 |
| entity_created | 新增候选实体 |
| relation_detected | 发现关系 |
| relation_strengthened | 连接增强 |
| relation_weakened | 连接减弱 |
| relation_not_connected | 目标实体未被接住 |
| risk_detected | 风险关系出现 |
| competitor_pressure_detected | 竞品占位增强 |
| review_required | 需要用户审阅 |
| graph_patch_applied | 图谱更新应用 |
| report_generated | 报告解读完成 |

### 7.2 动态视觉原则

允许：

1. 细网格画布。
2. 连线轻微流动。
3. 节点状态环。
4. 实时计数器。
5. 候选实体从边缘浮现。
6. 实体吸附到圈层。
7. 连接线加粗或变淡。
8. 节点轻微靠近或远离中心。
9. 更新前后 diff。
10. 时间轴回放。

禁止：

1. 黑底霓虹 AI SaaS 风格。
2. 紫蓝渐变作为主视觉。
3. 发光卡片和装饰性 bloom。
4. sparkle / robot / brain / magic 图标作为核心语言。
5. 为了“科技感”牺牲可读性和稳定性。

### 7.3 图谱动态状态

Graph 需要支持五种视图：

```text
当前状态
更新前
更新后
只看新增
只看变化
```

变化类型：

1. 新增实体。
2. 新增关系。
3. 连接增强。
4. 连接减弱。
5. 目标未连接。
6. 风险靠近。
7. 竞品占位。
8. 需要审阅。

### 7.4 更新队列

右侧 Inspector 需要有 Graph Update Queue。

队列项示例：

```text
+ 新实体：关系抗衰
  来源：Kimi / 3 条回答
  建议：加入战略目标圈

~ 连接增强：营养早餐 -> 安利
  来源：4 个平台，18 条回答
  变化：中圈 -> 内圈

! 风险靠近：直销 -> 传销/拉人头
  来源：豆包 / 2 条回答
  建议：进入风险圈，等待审阅
```

用户可以：

1. 接受。
2. 拒绝。
3. 合并。
4. 改名。
5. 移入风险圈。
6. 标记为战略目标。

## 8. 图谱交互需求

### 8.1 默认图谱

默认 Graph 首页显示：

1. 中心品牌。
2. 内圈强连接实体。
3. 中圈弱连接实体。
4. 外圈目标实体。
5. 风险入口。
6. 竞品入口。
7. 最近一次更新摘要。

不默认展开所有回答、所有问题和所有引用来源。

### 8.2 Lens

Graph Lens：

| Lens | 用途 |
| --- | --- |
| 圈层状态 | 看品牌关系半径 |
| 本次更新 | 看本次 run 改变了什么 |
| 战略目标 | 看目标词是否被 AI 接住 |
| 竞品压力 | 看哪些实体被竞品占据 |
| 风险认知 | 看风险关系是否靠近 |
| 来源资产 | 看实体由哪些资料或抓取来源推动 |
| 时间变化 | 看不同 Graph Update 的变化 |

### 8.3 实体 Inspector

选中实体后展示：

1. 实体名称。
2. 实体类型。
3. 当前圈层。
4. 连接强度。
5. 最近变化。
6. 关联画布运行。
7. 关联中间资产。
8. 关联报告。
9. 可执行动作。

可执行动作：

1. 用这个实体生成问题。
2. 用这个实体开一张新画布。
3. 把它加入监控。
4. 合并实体。
5. 标记为风险。
6. 标记为战略目标。

### 8.4 待审阅浮层

待审阅浮层不是正式圈层，而是 Graph 上的临时决策区。

进入浮层的对象：

1. 新发现但置信度不足的实体。
2. 高强度但负面语境占优的实体。
3. 自动分类和人工历史判断冲突的实体。
4. 可能是竞品、风险或别名合并对象的实体。
5. 基于旧 graph_version 生成、需要 rebase 的 Patch。

渲染原则：

1. 浮层实体不参与正式内圈 / 中圈 / 外圈稳定布局。
2. 浮层默认在 Graph 右侧或外缘显示，用虚线边界和待审阅状态点表达。
3. 风险相关浮层项必须始终可见，不允许默认折叠或隐藏。
4. 用户可以接受、拒绝、合并、改名、移入风险圈、移入竞品圈或标记为战略目标。
5. 处理后必须写入 Graph Update 和 Review Inbox。

## 9. 报告需求

### 9.1 报告定位

报告只解读 Graph Update。

报告不再是：

1. 主界面。
2. 画布交付物。
3. 所有中间数据的集合。

### 9.2 报告结构

建议结构：

```text
本次圈层更新摘要
强连接变化
目标心智变化
竞品压力变化
风险认知变化
未被接住的实体
建议下一张画布
附录：样本范围和资产引用
```

### 9.3 报告入口

报告入口：

1. Graph Update Timeline。
2. Reports 文件夹。
3. Board Run 完成状态。
4. 实体 Inspector 的关联报告。

报告内必须提供：

1. 定位到图谱。
2. 查看生成画布。
3. 查看相关资产。

## 10. 资产归档需求

Assets 默认文件夹：

| 文件夹 | 内容 |
| --- | --- |
| Uploads | 用户上传文档 |
| Questions | 模拟或上传问题 |
| Answers | AI 平台回答抓取结果 |
| Extractions | 实体和关系抽取结果 |
| Graph Updates | 图谱更新记录 |
| Exports | 用户导出文件 |

资产必须记录：

1. 来源画布。
2. 来源节点。
3. 来源 run。
4. 创建时间。
5. 所属品牌。
6. 是否参与 Graph Update。
7. 是否被报告引用。

## 11. Workflow Template

### 11.1 全景抓取模板

```text
品牌输入
  -> 问题模拟
  -> AI Platform Fetch Group
       ├─ ChatGPT Fetch
       ├─ DeepSeek Fetch
       ├─ Kimi Fetch
       └─ Doubao Fetch
  -> 实体关系抽取
  -> 圈层更新
  -> 报告解读
```

### 11.2 手动问题模板

```text
品牌输入
  -> 手动上传问题列表
  -> AI Platform Fetch Group
       ├─ ChatGPT Fetch
       ├─ DeepSeek Fetch
       ├─ Kimi Fetch
       └─ Doubao Fetch
  -> 实体关系抽取
  -> 圈层更新
  -> 报告解读
```

### 11.3 文档建模模板

```text
文档上传
  -> 文档解析
  -> 实体词表生成 / 匹配
  -> 用户审阅
  -> 圈层更新
  -> 报告解读
```

### 11.4 用户画像模板

```text
品牌输入
  -> 用户画像生成
  -> 场景问题生成
  -> AI Platform Fetch Group
       ├─ ChatGPT Fetch
       ├─ DeepSeek Fetch
       ├─ Kimi Fetch
       └─ Doubao Fetch
  -> 实体关系抽取
  -> 圈层更新
  -> 报告解读
```

### 11.5 周期监控模板

```text
监控计划
  -> 定期问题集
  -> AI Platform Fetch Group
  -> 实体关系抽取
  -> 圈层 diff
  -> 报告解读 / 提醒
```

## 12. 数据与状态字段草案

### 12.1 Circle Entity State

每个实体至少需要：

| 字段 | 说明 |
| --- | --- |
| entity_id | 实体 ID |
| brand_id | 所属品牌 |
| entity_name | 标准实体名 |
| entity_type | 实体类型 |
| aliases | 别名 |
| circle_zone | inner / middle / outer / competitor / risk |
| connection_strength | 连接强度 |
| connection_direction | strengthened / weakened / new / unchanged |
| platform_coverage | 覆盖平台 |
| source_count | 来源数量 |
| competitor_pressure | 竞品压力 |
| review_status | auto / reviewed / rejected / merged |
| first_seen_at | 首次出现 |
| last_seen_at | 最近出现 |

### 12.2 Graph Update

每次更新至少包含：

| 字段 | 说明 |
| --- | --- |
| graph_update_id | 更新 ID |
| brand_id | 品牌 |
| board_id | 来源画布 |
| run_id | 来源运行 |
| update_source | ai_fetch / document_upload / manual_questions / monitoring |
| before_version | 更新前图谱版本 |
| after_version | 更新后图谱版本 |
| patch_summary | 变化摘要 |
| changed_entities | 变化实体 |
| changed_relations | 变化关系 |
| review_items | 待审阅项 |
| report_id | 解读报告 |

### 12.3 Node Run

每个节点运行至少包含：

| 字段 | 说明 |
| --- | --- |
| node_run_id | 节点运行 ID |
| board_run_id | 画布运行 ID |
| node_id | 节点 ID |
| status | 状态 |
| input_refs | 输入引用 |
| output_refs | 输出引用 |
| asset_refs | 写入资产 |
| graph_patch_refs | 图谱更新引用 |
| started_at | 开始时间 |
| completed_at | 完成时间 |

## 13. Chat / 命令层定位

Chat 不再是主工作台。

新的定位：

```text
Chat 是当前节点、当前实体、当前报告段落的解释和命令层。
```

入口：

1. 选中图谱实体后提问。
2. 选中节点后请求解释或修改。
3. 读报告时追问某段解释。
4. 运行失败时处理确认。

Chat 必须携带上下文：

```text
brand_id
graph_update_id
selected_entity_id
board_id
node_id
asset_refs
intent
```

禁止让用户从空白 Chat 重新描述当前画布和图谱状态。

## 14. 视觉和动效方向

### 14.1 设计原则

本次改版需要有动态感和科技感，但方向是：

```text
精密、实时、可解释的数据建模感。
```

不是：

```text
炫光、霓虹、魔法、机器人、AI 玩具感。
```

必须遵守：

1. light-first。
2. paper-neutral surface。
3. Specta Evidence Teal 作为主品牌色。
4. 状态色只表达业务状态。
5. 使用克制边框、细线、状态点、轻量流动动画。

### 14.2 推荐动效

1. 节点运行时状态环转动。
2. 数据沿边线轻微流动。
3. 实体候选点从图谱边缘浮现。
4. 匹配成功后吸附到对应圈层。
5. 连接增强时线宽和位置轻微变化。
6. 更新完成后 Graph 稳定重排。
7. Graph Update Timeline 出现新事件。
8. 报告生成完成后以轻提示进入 Reports。

### 14.3 无障碍与降级

1. 所有动态状态必须有文本状态。
2. 用户开启 reduced motion 时，改为淡入和状态变化，不做位移动画。
3. 动态计数必须有最终数字。
4. Graph 变化必须可以在列表视图中阅读。

## 15. 分阶段落地

### Phase 0：产品、算法和运行架构冻结

产物：

1. 本 PRD。
2. 关键概念命名表。
3. Graph / Boards / Assets / Reports 信息架构。
4. 第一版 Workflow Template 列表。
5. 圈层分配规则 v0.1。
6. Board / Orchestrator / Node Runtime 关系说明。
7. Graph Patch 冲突和审阅状态机。
8. Node I/O Contract v0.1。
9. 实体关系抽取节点规格 v0.1。

验收：

1. 团队同意报告降级为图谱更新解读。
2. 团队同意画布核心交付物为 Graph Update。
3. 团队同意 Graph 为品牌空间默认入口。
4. 团队同意第一版圈层阈值、冲突处理和节点契约足够支持原型实现。
5. 团队同意 Board 是用户可见执行计划，Orchestrator / Runtime 是执行和异常处理层。

### Phase 1：只读原型

范围：

1. Brand Space shell。
2. Graph 首页静态数据。
3. Boards 列表。
4. Assets / Reports 文件夹结构。
5. Graph Update Timeline。

验收：

1. 用户能理解四个一级区域。
2. 用户能理解报告和中间资产不再是主界面。

### Phase 2：画布运行演示 + 真实最小链路

范围：

1. 全景模板画布。
2. 节点状态流转。
3. Graph Patch Stream 模拟事件。
4. Graph before/after diff。
5. 报告解读生成入口。
6. 真实最小链路验证：`1 个品牌 × 1 个平台 × 10 个问题`。
7. 至少跑通 `QuestionSet -> AnswerSet -> EntityRelationSet -> Graph Patch -> Circle Report` 的端到端链路。

验收：

1. 用户能看懂画布如何更新图谱。
2. 动态感成立，但不牺牲可读性。
3. 真实回答能写入 Assets，并生成可审阅 Graph Patch。
4. Demo 数据和真实数据的差异被记录，不允许只基于模拟数据判断体验成立。

### Phase 3：模板内节点可替换

范围：

1. 删除问题模拟节点。
2. 添加手动问题上传节点。
3. 校验 QuestionSet 输出兼容性。
4. 下游抓取节点复用。
5. Guided Mode 默认开启，只允许在模板定义的替换槽中换节点。
6. Expert Mode 暂不面向普通品牌用户开放。

验收：

1. 用户能完成“问题模拟 -> 手动上传问题列表”的替换。
2. 系统能解释节点为什么兼容或不兼容。
3. 用户不能创建无效 Board；当替换不兼容时，系统给出可修复建议。

### Phase 4：实体审阅闭环

范围：

1. 新实体审阅。
2. 别名合并。
3. 风险圈归类。
4. 战略目标标记。
5. Graph Update 应用。

验收：

1. 用户能参与实体关系库增长。
2. 审阅结果影响 Graph。

### Phase 5：扩展真实 A4/A5 和资产归档

范围：

1. AI 回答抓取写入 Assets。
2. 实体关系抽取写入 Extractions。
3. Graph Update 写入 Graph Updates。
4. Reports 生成真实圈层解读。

验收：

1. 一次真实抓取能产生可查看资产、图谱更新和报告解读。
2. 刷新后状态不丢。

## 16. 验收标准

### 16.1 产品验收

1. 用户进入品牌后默认看到 Graph，而不是 Chat 或报告。
2. 用户能通过 Boards 创建或打开画布。
3. 用户能理解画布运行的结果是 Graph Update。
4. 用户能在 Assets 找到中间产物。
5. 用户能在 Reports 找到图谱更新解读。
6. 用户能查看一次更新前后图谱差异。
7. 用户能从报告回到对应图谱变化和画布运行。

### 16.2 交互验收

1. 节点运行状态清晰。
2. Graph Patch Stream 有实时计数和变化队列。
3. 更新队列支持接受、拒绝、合并、改名。
4. 节点替换有输入输出兼容性提示。
5. Chat 只作为上下文命令层，不抢主工作台。

### 16.3 视觉验收

1. 动态感来自节点、连线、图谱 diff 和实时事件，不来自装饰光效。
2. 不出现紫蓝渐变、霓虹、glow、sparkle、robot、brain 作为核心视觉。
3. 符合 Specta Evidence Teal 和 paper-neutral 设计系统。
4. reduced motion 下可用。

### 16.4 技术验收

1. 每个节点有明确 input / output / asset_refs / graph_patch_refs。
2. Graph Update 可版本化。
3. Assets 可追溯到 board、node、run。
4. Report 可追溯到 graph_update_id。
5. Graph before/after 可重建。
6. 审阅动作可回写实体关系库。

## 17. 评审阻断项处理

第三方评审结论是正确的：当前 PRD 已经说明产品方向，但还不足以直接进入实现。以下内容作为 Phase 0 必须冻结的补充规格。

### 17.1 圈层分配规则 v0.1

第一版圈层分配采用可解释评分，而不是纯 LLM 判断。

`connection_strength` 为 `0-100` 的连续值，默认由以下维度加权得到：

| 维度 | 权重 | 说明 |
| --- | --- | --- |
| platform_coverage_score | 20 | 覆盖多少 AI 平台 |
| mention_frequency_score | 15 | 在问题和回答中的出现频次 |
| explicit_association_score | 20 | 是否被明确和品牌、产品、场景建立关系 |
| context_relevance_score | 15 | 语义上下文是否符合品牌实体词表 |
| evidence_quality_score | 10 | 是否来自高质量回答、用户上传资料或明确出处 |
| sentiment_or_risk_score | 10 | 正向、负向、风险或争议语境 |
| stability_score | 10 | 是否在多次 Graph Update 中稳定出现 |

评分之前必须先做极性和风险分类，避免“高频负面共现”被误判为品牌资产。

一票否决规则：

1. 当 `sentiment_or_risk_score < 3/10`，实体不得进入内圈或中圈，必须进入风险圈或待审阅浮层。
2. 当 `sentiment_or_risk_score >= 3/10` 且 `< 5/10`，实体不得进入内圈；最多进入中圈或待审阅浮层。
3. 当 `sentiment_or_risk_score < 5/10` 且负面 / 质疑 evidence 占多数，实体不得进入中圈，必须进入风险圈或待审阅浮层。
4. 内圈要求 `sentiment_or_risk_score >= 6/10`，且正面 evidence 占多数。
5. 灰区实体从中圈升级到内圈，必须连续 2 次 Graph Update 满足正面 evidence 占多数。
6. 当负面 evidence 占多数，实体不得被标记为“已正面验证”。
7. 高频出现 + 负面语境 = 风险信号，不是品牌强连接资产。
8. 涉及监管、传销、骗局、夸大功效、价格争议等实体时，即使 `connection_strength >= 75`，也必须进入风险圈或待审阅浮层。
9. 所有被一票否决或降级的实体必须保留 evidence span，方便用户判断是误杀还是实际风险。

圈层分配先处理强制类型，再处理强度：

| 圈层 | 默认规则 |
| --- | --- |
| 中心 | 当前品牌实体 |
| 风险圈 | `entity_type = risk`，或风险关系得分 >= 60，或用户标记为风险 |
| 竞品圈 | `entity_type = competitor`，或 competitor_pressure >= 60 |
| 内圈 | connection_strength >= 75，且 platform_coverage >= 3，且 source_count >= 8 |
| 中圈 | connection_strength 45-74，或 platform_coverage >= 2 |
| 外圈 | 战略目标实体但 connection_strength < 45，或 source_count 不足 |
| 待审阅浮层 | 新实体、冲突实体、低置信实体，不直接稳定进入正式圈层 |

迁移规则：

1. 自动升级需要满足阈值，并且 `review_status != rejected`。
2. 内圈 / 中圈之间的迁移需要连续两次 Graph Update 满足新圈层条件，避免抖动。
3. 风险圈和竞品圈优先级高于内圈 / 中圈 / 外圈。
4. 用户人工审阅结果优先级高于自动规则；后续自动 Patch 不能静默覆盖人工判断。
5. 每次圈层迁移必须写入 `Graph Update`，并记录评分拆解。
6. 风险实体不可因平台覆盖率、提及频次或稳定出现而自动升级为品牌资产。
7. 竞品实体不可进入内圈；它只能进入竞品圈、待审阅浮层或作为竞品关系挂接到相关场景实体。

### 17.2 Graph Patch 冲突与审阅状态机

Graph Patch 不是直接写数据库的事件流，而是一组可审阅、可重放的变更提案。

Patch 状态：

```text
proposed -> auto_applied
         -> needs_review -> accepted -> applied
                         -> rejected
                         -> merged
                         -> superseded
         -> conflict
```

队列作用域：

1. 每次 Board Run 生成一个 `Graph Update Queue`，用于解释本次运行。
2. 品牌级存在一个 `Review Inbox`，汇总跨 Board 的待审阅和冲突项。
3. Report 只引用某次 Graph Update 的队列结果，不替代全局 Review Inbox。

冲突规则：

| 冲突类型 | 示例 | 默认处理 |
| --- | --- | --- |
| 圈层冲突 | 同一实体被一个 Board 推入目标圈，另一个 Board 推入竞品圈 | 进入 conflict，等待审阅 |
| 别名冲突 | Nutrilite 被合并到不同实体 | 进入 needs_review |
| 风险冲突 | 自动规则认为是风险，人工曾拒绝风险归类 | 人工判断优先，自动 Patch 标记 superseded |
| 版本冲突 | Patch 基于旧 graph_version | 重新基于最新版本 rebase，再决定是否冲突 |

`auto_applied` 判定：

| Patch 类型 | 是否可自动应用 | 规则 |
| --- | --- | --- |
| source_count 更新 | 是 | 只增加来源计数，不改变圈层 |
| last_seen_at 更新 | 是 | 只更新最近出现时间 |
| connection_strength 微调 | 是 | 变化幅度 < 10%，且不触发圈层迁移 |
| platform_coverage 更新 | 是 | 只增加覆盖平台，不触发竞品 / 风险 |
| 新增实体 | 否 | 默认进入 needs_review 或待审阅浮层 |
| 圈层迁移 | 否 | 特别是进入内圈、风险圈、竞品圈 |
| 新增风险关系 | 否 | 必须进入 Review Inbox |
| 新增竞品关系 | 否 | 必须进入 Review Inbox |
| 别名合并 | 否 | 除非是 EntityLexicon 中已确认的精确别名 |
| 人工曾处理对象的重判 | 否 | 进入 conflict 或 superseded |

写入规则：

1. Graph 应采用版本化写入：`before_version -> patch_set -> after_version`。
2. 同一品牌同一时刻只能有一个 Graph Patch Apply 写入事务。
3. Board 可以并行运行，但 Graph Apply 必须串行化或通过乐观锁重试。
4. 自动 Patch 只能更新低风险字段；高影响变化进入审阅。
5. 所有人工审阅动作必须可追溯到用户、时间、来源 run 和理由。

### 17.3 Board / Orchestrator / Node Runtime 关系

新架构不取消 Orchestrator，而是重新分工。

```text
Board = 用户可见的声明式执行计划
Node = 有类型输入输出的能力组件
Node Runtime = 确定性执行、校验、重试、资产写入
Orchestrator = 在 Board 约束内做路由、失败恢复、用户确认和策略选择
Agent / Skill = Node Runtime 可调用的底层能力
```

关键边界：

1. Board 是用户理解和操作 Workflow 的主界面，不是底层执行引擎。
2. Orchestrator 不再在用户不可见处任意改写流程；它只能在 Board 模板和节点契约允许范围内决策。
3. 失败重试、平台降级、继续运行、用户确认由 Orchestrator / Runtime 处理，并回写到节点状态。
4. 现有 A1-A6 Agent 不要求一一映射为节点；节点可以调用 Agent 的一个能力切片。
5. Agent 能力可以隐藏在节点背后，但节点的 input / output / asset / graph_patch 边界必须显式。

现有能力映射建议：

| 现有能力 | 新节点 / 运行层 |
| --- | --- |
| A1 品牌竞争分析 | Brand Entity Seed、Competitor Entity Match |
| A2 用户画像 | Persona Generate、Scenario Question Generate |
| A3 问题模拟 | Question Simulation Node |
| A4 回答抓取 | AI Platform Fetch Group 与平台子节点 |
| A5 指标 / 报告 | Entity Metrics、Circle Report |
| A6 浏览器自动化 | Web / Platform Fetch Runtime capability |

### 17.4 Node I/O Contract v0.1

所有节点输出必须使用统一对象包裹：

```ts
type NodeObjectEnvelope<T> = {
  object_type: string;
  schema_version: string;
  brand_id: string;
  board_id: string;
  run_id: string;
  node_run_id: string;
  created_at: string;
  asset_ref?: string;
  provenance_refs: string[];
  payload_hash: string;
  payload: T;
};
```

第一版 I/O 类型：

| 类型 | 必要字段 | 用途 |
| --- | --- | --- |
| BrandSeed | brand_name, category, market, known_assets | 品牌初始化 |
| EntityLexicon | entities, aliases, relation_types, review_status | 实体词表 |
| QuestionSet | questions, source_type, persona_refs, topic_refs | 下游抓取输入 |
| PlatformFetchPlan | platforms, rate_limit, retry_policy, question_refs | 平台抓取计划 |
| AnswerSet | platform, question_id, answer_text, captured_at, raw_ref | 回答资产 |
| EntityRelationSet | entities, relations, evidence_refs, scoring_breakdown | 抽取结果 |
| GraphPatchSet | patches, conflicts, review_items, base_graph_version | 图谱变更提案 |
| GraphUpdate | before_version, after_version, applied_patches, summary | 图谱更新结果 |
| CircleReport | graph_update_id, sections, asset_refs, next_board_suggestions | 报告解读 |

兼容性规则：

1. 节点连接必须校验 `object_type` 和 `schema_version`。
2. 同一输出类型可由不同节点产生，例如 QuestionSet 可来自问题模拟或手动上传。
3. 下游节点不能依赖上游节点名称，只能依赖类型、schema 和必要字段。
4. Breaking schema change 必须提升 `schema_version`，并提供迁移或拒绝连接。

### 17.5 实体关系抽取节点规格 v0.1

`Entity Relation Extraction` 是关键节点，不能作为黑箱处理。

输入：

```text
AnswerSet[]
EntityLexicon
BrandSeed
relation_type_taxonomy
```

输出：

```text
EntityRelationSet
GraphPatchSet
Extraction Asset
```

关系类型枚举 v0.1：

| relation_type | 含义 |
| --- | --- |
| associated_with | 与品牌或实体有关联 |
| belongs_to | 属于某品牌、品类或产品体系 |
| solution_for | 解决某需求、场景或问题 |
| audience_for | 对应某人群 |
| scenario_for | 对应某使用场景 |
| competes_with | 形成竞品或替代关系 |
| risk_of | 指向风险、误解或争议 |
| evidence_for | 作为证据资产支撑某关系 |
| target_gap | 品牌目标实体未被 AI 回答接住 |

风险检测规则：

1. EntityLexicon 中 `entity_type = risk` 的实体自动进入风险候选。
2. 风险词库命中时生成 `risk_of` 候选关系，例如传销、骗局、智商税、夸大功效、拉人头、监管处罚、价格虚高。
3. 负面情感 + 高频共现 + 显式品牌关联时，必须生成风险信号，而不是品牌资产信号。
4. 风险实体在图谱上拥有独立视觉优先级，不允许被普通圈层筛选隐藏。
5. 风险关系必须保留 evidence span、问题原文、平台和回答资产引用。

竞品检测规则：

1. EntityLexicon 中 `entity_type = competitor` 的实体自动进入竞品候选。
2. AI 回答中出现“替代”“相比之下”“不如选”“更推荐”“同类品牌”“竞品”等比较语境时，抽取 `competes_with` 关系。
3. 单纯同品类并列提及不构成 `competes_with`，例如“安利和汤臣倍健都是保健品品牌”只能标记为同品类候选。
4. `competes_with` 必须包含明确替代、推荐、优劣、价格、功效、适用人群或购买决策语境。
5. 当某品牌实体在同一问题中替代或压过当前品牌时，记录 `competitor_pressure`。
6. 竞品关系不能只靠词表标记，必须至少有一条 evidence span 支撑。
7. `competes_with.confidence < 0.7` 时，只进入待审阅浮层，不进入竞品圈。
8. `competes_with.confidence >= 0.7` 且存在明确替代 / 推荐 evidence 时，才生成竞品圈候选 Patch；该 Patch 仍需进入 Review Inbox。
9. 每条 `competes_with` 关系必须记录：竞品名、被替代的品牌 / 场景、问题、平台、回答摘录、比较触发词和置信度。

情感极性规则：

1. 每条 evidence 必须标记 `positive`、`neutral`、`negative`、`questioning` 之一。
2. “提及”不等于“认可”；只有正面 evidence 占多数时，才能判定为正面验证。
3. 战略词可以被标记为“被提及但伴随风险”或“被质疑”，不能统一写成“已被验证”。
4. LLM 抽取结果必须输出情感理由短句，供报告和 Review Inbox 使用。

抽取流程：

1. 对 AnswerSet 做平台、问题、语言和时间标准化。
2. 使用 EntityLexicon 做别名匹配和候选实体召回。
3. 抽取新候选实体，并标记是否命中已有别名。
4. 对实体关系进行分类，生成 `relation_type`。
5. 对每条 evidence 做情感极性和风险语境判断。
6. 对比较语境做竞品检测和 `competitor_pressure` 计算。
7. 为每条关系记录 evidence span、平台、问题、回答资产引用。
8. 计算关系强度、风险状态和圈层建议。
9. 生成 GraphPatchSet，而不是直接改 Graph。

消歧规则：

1. 别名精确命中优先自动合并。
2. 高相似度但非精确命中的实体进入 needs_review。
3. 竞品名、风险词和品牌子资产不做静默合并。
4. 每次合并必须保留原始 mention 和来源资产。

### 17.6 报告生成规则

报告采用结构化数据 + LLM 解读的混合模式。

1. Graph Update 先生成结构化报告骨架。
2. LLM 只能基于 GraphUpdate、GraphPatchSet、EntityRelationSet 和 Asset refs 写解释。
3. 报告正文必须保留关键变化对应的实体、平台、资产引用。
4. 变化量很小时生成短报告；变化量大时生成完整报告。
5. 报告必须区分正面验证、中性提及、负面提及、质疑提及，不能把“出现过”写成“已被验证”。

长度规则建议：

| Graph Update 变化量 | 报告形态 |
| --- | --- |
| 1-3 个低风险变化 | 短摘要 |
| 4-15 个变化，含少量审阅 | 标准报告 |
| 15+ 个变化，或含风险 / 竞品冲突 | 完整报告 + 审阅清单 |

证据选择规则：

1. 每个战略词至少引用 2 个不同问题的 evidence；如果不足，必须标记“证据不足”。
2. 不允许同一个问题的回答成为某个战略词的唯一证据来源。
3. 证据选择优先级：精准命中战略词或别名 > 跨平台覆盖 > 与圈层变化直接相关 > 长文本。
4. 每条证据必须包含问题原文、平台、回答摘录、情感倾向、资产引用。
5. 风险和竞品证据必须优先展示原文摘录，避免只给结论。
6. 如果 80% 以上证据来自同一问题，报告生成节点必须进入 needs_review。

战略词结论分段：

| 稳定度 | 证据量 | 情感条件 | 结论方向 |
| --- | --- | --- | --- |
| >= 60 | >= 30 | 正面 evidence 占多数 | 已站稳：可放大传播，建议进入内容资产管理 |
| 50-59 | 15-29 | 正面或中性 evidence 占多数 | 有基础但需补强：建议定向投放指定平台和场景内容 |
| < 50 | < 15 | 任意 | 尚在萌芽：先补充问题和证据，不建议进入主传播 |
| 任意 | 任意 | 负面或质疑 evidence 占多数 | 伴随风险：需要先澄清具体风险，再考虑传播 |

报告生成约束：

1. LLM 必须在战略词判断中写出具体平台、场景、风险或证据缺口。
2. 禁止所有战略词复用同一句“可以进入稳定内容资产管理”。
3. 行动建议必须包含做什么、对谁、在哪个平台、期望改善什么指标。
4. 如果缺少竞品 evidence，报告不得声称“发现竞品参照”；只能写“本次未形成可引用竞品证据”。

报告生成后处理校验：

1. 战略词结论相似度检查：任意两条战略词结论字符串相似度 > 0.8，报告节点进入 `needs_review`。
2. 竞品一致性检查：报告出现竞品声明，但缺少 `competes_with` evidence span，报告节点进入 `needs_review`。
3. 风险一致性检查：报告出现风险结论，但 GraphPatchSet 中没有 `risk_of` 关系或风险 evidence，报告节点进入 `needs_review`。
4. 证据集中度检查：80% 以上 evidence 来自同一问题，报告节点进入 `needs_review`。
5. 行动建议具体性检查：行动建议缺少平台、人群 / 场景、目标变化三者之一，报告节点进入 `needs_review`。
6. 验证标签检查：报告使用“已验证”“已站稳”“可放大”等结论时，必须满足对应稳定度、证据量和正面 evidence 条件，否则进入 `needs_review`。
7. 后处理校验结果必须写入 Report metadata，供用户和开发者追溯是 LLM 文本问题还是上游数据不足。

“建议下一张画布”优先由规则生成，再由 LLM 转写：

1. 目标实体长期在外圈：建议运行用户画像或手动问题画布。
2. 风险靠近：建议运行风险澄清问题画布。
3. 竞品压力增强：建议运行竞品对照画布。
4. 来源不足：建议上传品牌资料或补充问题列表。

### 17.7 新用户冷启动与 Guided Mode

Chat 降级后，必须补足非 Chat 入口。

空 Graph 页面默认提供三个入口：

1. `导入品牌资料`：进入文档建模画布。
2. `运行全景抓取`：进入全景模板，要求用户先填写品牌信息。
3. `使用示例品牌查看`：展示 demo 品牌的 Graph / Board / Report 关系。

Guided Mode 默认开启：

1. 用户从模板开始，而不是从空白画布开始。
2. 可替换节点只出现在模板定义的替换槽中。
3. 替换动作以菜单或节点库推荐完成，不要求用户理解所有类型系统。
4. 无效连接不允许创建；系统直接说明缺少哪个输出类型。

Expert Mode 第一版只作为内部或高级开关，不作为默认体验。

### 17.8 “不是低代码”的边界

本产品不是通用低代码平台，而是模板驱动的有限编排。

开放：

1. 在模板内替换同类型节点。
2. 添加已批准的辅助节点。
3. 删除可选节点。
4. 调整平台、问题来源、监控频率等参数。
5. 运行单节点、继续失败节点、查看资产和图谱影响。

不开放：

1. 任意代码节点。
2. 任意循环、条件分支和脚本。
3. 跨品牌任意数据读写。
4. 无契约节点连接。
5. 让普通用户从零搭建复杂 DAG。

### 17.9 旧数据映射和过渡

第一版需要保留旧数据可读性。

| 旧实体 / 产物 | 新位置 |
| --- | --- |
| Session | Brand Space 的历史入口或 Legacy Conversation |
| Message | 关联到 run / report 的 conversation refs |
| Canvas Artifact: workflow | Board Snapshot |
| Canvas Artifact: questionList | Assets / Questions |
| Canvas Artifact: fetchResults | Assets / Answers |
| Canvas Artifact: report | Reports |
| Snapshot | Graph Version 或 Board Run Snapshot |

过渡策略：

1. 不立即删除旧 Chat / Canvas 数据。
2. 新运行默认写入 Brand Space / Boards / Assets / Reports。
3. 旧报告只读展示，并标记为 Legacy Report。
4. 可迁移的旧 questionList / fetchResults 进入 Assets，但不强制生成 Graph Update。

### 17.10 技术选型、性能、保留和协作边界

第一版决策：

1. Board 渲染优先使用 React Flow 或等价节点画布方案。
2. Graph 渲染在 Phase 1 做 POC：比较 D3 / Cytoscape / Canvas 或 WebGL 的圈层布局可行性。
3. Graph Patch Stream 前端采用批处理，建议 `200ms` 合并窗口，避免每个事件都触发重排。
4. Assets 默认保留，不做自动删除；后续增加归档策略。
5. 第一版按单人主操作设计；多人协作、审批和角色权限进入后续版本。

## 18. 待确认问题

以下问题在 v0.3 中先锁定为产品决策：

| 原问题 | 决策 | 理由 |
| --- | --- | --- |
| Graph Update 是否必须人工审阅后才应用？ | 低风险 Patch 自动应用，高影响变化进入审阅 | 全部人工审阅会淹没用户，全部自动应用会污染图谱 |
| 风险圈是否默认折叠？ | 不折叠 | 安利案例已证明风险消失是致命问题 |
| Chat 命令层是否保留全局输入框？ | 保留，但必须预填当前 Brand / Graph / Board 上下文 | 冷启动和空 Graph 状态仍需要自然语言入口 |

仍待确认：

1. 第一版 Graph 是否以“圈层布局”为主，还是提供圈层 + 力导向双模式？
2. Entity Lexicon 是每个品牌必须先有，还是允许系统先自动生成候选词表？
3. 报告是否每次 Graph Update 必生成，还是只在用户要求时生成？
4. Assets 文件夹是否需要支持权限和分享？
5. 周期监控的每次 run 是否都生成完整报告，还是只生成变化摘要？

## 19. 关键决策建议

建议本轮先确认这些产品决策：

```text
1. Graph 是品牌空间默认首页。
2. Board 是更新 Graph 的操作空间。
3. Graph Update 是画布核心交付物。
4. Assets 存放中间产物。
5. Reports 只解读 Graph Update。
6. Chat 降级为上下文命令层。
7. 动态感来自 Graph Patch Stream。
8. 画布默认采用“并行平台机架”方案。
9. 节点系统是模板驱动的有限编排，不是通用低代码平台。
10. Phase 2 必须纳入真实最小链路验证，不能只做模拟 Demo。
11. 高频负面共现不得进入内圈或中圈；必须进入风险圈或待审阅浮层。
12. 风险和竞品必须有检测逻辑和 evidence span，不能只停留在字段或关系类型。
13. 报告必须按证据量、稳定度和情感极性分段，不能把提及写成认可。
14. 内圈必须是明确正面关系，情感灰区实体需要连续正面证据才能升级。
15. 竞品关系必须有明确替代 / 推荐语境和置信度门槛，单纯同品类提及不算竞品占位。
16. 报告生成必须有后处理校验，不能只依赖 LLM prompt 自觉遵守约束。
```

只要这十六条成立，后续 UI、数据模型和执行管道都可以围绕同一条主线展开。
