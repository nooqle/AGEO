# Prototype v0.4 评估

> 评估对象：`docs/prototypes/brand-circle-board-v0.4/` (README.md + index.html)
> 评估日期：2026-06-17
> 评估依据：PRD v0.3 + 安利报告 10 个真实问题 + 原型实际交互
> 评估结论：**方向正确，核心概念已落地，但存在 3 个错位、4 个缺失、2 个设计矛盾。可用作开发参考，不可直接作为实施蓝图。**

---

## 一、做对了什么

### 十个真实问题在原型中全部有可视化回应

| 报告问题 | 原型如何回应 | 评价 |
|----------|-------------|------|
| P01 提及≠认可 | Inspector 显示 sentiment score，Guardrails 面板显示"情感 3-5 不进内圈"规则 | ✅ 直击根因 |
| P02 分层无区分度 | Graph view 有 6 种实体类型，含近端/远端/审阅浮层 | ✅ 区分度足够 |
| P03 风险消失 | risk 节点红色渲染，"监管信息"出现在风险浮层而非内圈 | ✅ 修正了错分 |
| P04 竞品缺失 | "汤臣倍健"以 competitor 候选出现，confidence 0.74 | ✅ 有了 |
| P05 判断模板化 | Report view 战略词结论分三档，稳定度不同结论不同 | ✅ 差异化 |
| P06 证据来源单一 | 证据引用 Q08 + Q17 两个问题 | ✅ 不再只引 Q11 |
| P07 监管信息错分 | 出现在风险浮层，标注"负面语境" | ✅ 关键修正 |
| P08 无时间维度 | Selected Entity 面板显示 last_seen_at | ⚠️ 仅显示时间戳，无趋势 |
| P09 内容三遍重复 | Report view 结构化：变更表 + 证据 + 结论，无重复 | ✅ 结构化消重 |
| P10 行动建议空洞 | 战略词结论含具体平台和场景 | ✅ 有针对性 |

### 架构边界清晰

README 明确声明"frontend should not own scoring, graph patch resolution, report validation, or evidence rules"，这是正确的。前端是控制面，不是计算面。

### 三个视图的定位准确

Board 是运行时画布，Graph 是品牌图谱主页，Report 是审阅界面。三者角色不重叠。

---

## 二、三个错位

### 错位 1：Board 画布与 PRD 的"并行平台机架"概念不匹配

PRD Section 6.5-6.6 定义了"Parallel Platform Rack"——4 个平台节点应表现为**一个组合单元**，用户可以整体运行也可以单独运行某个平台。原型中 4 个平台节点是**独立散布在画布上的 4 个节点**，没有视觉上的组合关系。

这不仅仅是视觉问题——如果 4 个节点各自独立，用户无法理解"这是一个并行组"，也无法一键运行全部平台。原型的实现更像传统 DAG 编辑器，而不是 PRD 定义的"机架"。

**建议**：至少在视觉上用一个浅色容器包裹 4 个平台节点，顶部标注平台名，底部显示整体进度。不需要做折叠/展开，只需要视觉分组。

### 错位 2：Graph Update Queue 的交互与 PRD 状态机脱节

PRD 17.2 定义了完整的状态机：`proposed → auto_applied / needs_review → accepted → rejected → applied`。原型中 Graph Update Queue 只显示了 3 个审阅项，点击后弹出简单的"接受/拒绝"按钮。

缺失：
- 没有 `auto_applied` 项的展示（原型中应有一些已经自动应用的 patch，但完全没有）
- 没有 patch 详情——用户不知道"接受"的是什么变更
- 没有 diff 预览——PRD 在 Report view 实现了 Graph Diff，但 Graph view 的 Queue 里没有

**建议**：Queue 中应分两组显示——"已自动应用（3）"折叠展示 + "待审阅（2）"展开展示。每个审阅项点击后显示变更摘要（实体 X 从 middle → inner，connection_strength 从 62 → 78）。

### 错位 3：Report Guardrails 是一次性展示，而非实时校验

PRD 17.6 定义 Guardrails 为**后处理校验**——报告生成后自动运行，不合格的报告不发布。原型中 Guardrails 以静态面板形式展示在右侧，4 条规则全部显示"通过"或"警告"。

但原型的 Guardrails 看起来像**装饰性信息**，不像**阻断性校验**。用户无法理解：
- "警告"之后会发生什么？报告还能发布吗？
- 如果"竞品置信度低于 0.7"这条触发了，是阻断报告还是标记？
- Guardrails 是自动运行的还是用户手动触发的？

**建议**：Guardrails 应有明确的状态标签——"✓ PASS"（通过，不影响发布）/ "⚠ WARN"（警告，可发布但需确认）/ "✗ BLOCK"（阻断，不可发布）。至少有一条规则在原型中展示为 BLOCK 状态，让用户理解这个机制的强制力。

---

## 三、四个缺失

### 缺失 1：待审阅浮层的交互完全空白

PRD 8.4 定义了待审阅浮层的交互——实体出现在图谱外圈，用户可以接受（进入对应圈层）或拒绝（移出或保持浮层）。原型中 `review` 类型的节点在 Graph view 存在，但没有：
- 接受/拒绝的交互入口
- 浮层的视觉编码（虚线？半透明？独立区域？）
- 浮层实体与圈层的空间关系

这是 PRD v0.3 新增的重要概念，原型中只有数据没有交互。

### 缺失 2：Board 的运行控制与 Orchestrator 的关系不可见

原型中 Board 有 Pause/Stop/Play 按钮，但点击后只是改变了一个模拟状态。用户无法理解：
- Pause 后，正在运行的 4 个平台 fetch 节点怎么办？等当前节点完成还是立即中断？
- Stop 后，已产出的 Graph Patch 会保留还是丢弃？
- 用户能否在运行中修改 Config tab 的参数？

PRD 17.3 定义了 Board/Orchestrator/Node 三层运行时，但原型只展示了 Board 层的控制。

### 缺失 3：Node Inspector 的 Output tab 内容是空壳

Overview tab 有 metrics，Events tab 有事件流，Config tab 有参数——但 Output tab 只有一个占位标签。Output 是 Board 执行的核心产物（GraphPatchSet、EntityRelationSet 等），用户需要看到每个节点产出了什么。

**建议**：至少为 fetch 节点的 Output 展示：平台名、获取的回答数、提取的实体数、耗时。这比 Overview 的指标更有操作价值。

### 缺失 4：Report view 缺少 Trace Chain 的实际内容

README 提到 Report view 有"trace chain"，原型右侧面板确实有"Trace Chain"标签，但内容只是一个静态列表（Question → Fetch → Extract → Review → Report），没有真实的溯源链接。

PRD 强调证据必须可追溯到具体的问题和平台。Trace Chain 应该是：报告中的每条结论 → 支撑它的证据 → 证据来自的回答 → 回答来自的平台和问题。这个链条是报告可信度的核心证明，不应省略。

---

## 四、两个设计矛盾

### 矛盾 1：两套 CSS 设计语言

index.html 的 CSS 有两个阶段：
- 前 850 行是暖色/纸质设计（cream 背景、warm gray 文字、teal 强调）
- 852-1341 行被蓝色/灰冷设计覆盖（#1e293b 深色底、蓝色强调、hover 发光效果）

结果是一个视觉混合体——Board view 偏冷色系，Graph view 偏暖色系，Report view 两者都有。这不是有意的风格切换，而是原型迭代遗留。

**建议**：生产构建前必须统一设计语言。PRD 已确定"Specta Evidence Teal (#1F7A6B)"，应以此为基础，light-first/paper-neutral 作为底色，不要用深色底。

### 矛盾 2：Board view 的"工具栏"定位不清

画布底部有 6 个工具按钮（选择、平移、框选、注释、撤销、重做），但原型的 Board 定位是"运行时画布"而非"编辑画布"——用户不需要编辑节点布局，只需要控制执行。这些工具来自通用 DAG 编辑器模板，不适合 Board 的定位。

PRD 定义的 Board 交互是：运行/暂停/停止、查看节点状态、审阅 Graph Patch。不是：拖拽节点、画框选、添加注释。

**建议**：移除编辑类工具（框选、注释、撤销、重做），只保留运行控制类工具（运行、暂停、停止、查看 Inspector）。或者将编辑工具作为"高级模式"隐藏。

---

## 五、实施准备度评估

| 维度 | 评分 | 说明 |
|------|------|------|
| 概念对齐 | 8/10 | 核心概念与 PRD v0.3 对齐，仅有并行机架一个概念错位 |
| 交互完整性 | 5/10 | 审阅浮层、运行控制、Trace Chain 三项关键交互缺失 |
| 视觉一致性 | 4/10 | 两套 CSS 矛盾，需统一设计语言后才能给设计稿 |
| 数据流可追溯 | 6/10 | Board → Graph Patch → Report 的链路可感知，但缺少中间节点的 Output 展示 |
| 开发就绪度 | 6/10 | README 的组件拆分列表足够，但缺少状态管理方案和 API contract |

**总体评分：6/10 — 方向正确，需要一轮修正后才能进入开发。**

---

## 六、修订建议优先级

| 优先级 | 修订项 | 理由 |
|--------|--------|------|
| **P0** | 补齐待审阅浮层的交互 | PRD 新增的关键概念，原型中完全空白 |
| **P0** | 统一 CSS 设计语言 | 两套风格矛盾会直接误导开发 |
| **P0** | Graph Update Queue 补充 diff 预览和 auto_applied 项 | 状态机的核心交互，不能只有接受/拒绝按钮 |
| **P1** | Guardrails 加 BLOCK 状态 | 不展示阻断力，用户会以为是建议而非强制 |
| **P1** | 补充 Node Inspector Output tab | 产出物是 Board 的核心价值 |
| **P1** | 补充 Trace Chain 实际内容 | 证据溯源是报告可信度的基础 |
| **P1** | 并行平台机架视觉分组 | 影响用户对 Board 运行模型的理解 |
| **P2** | 移除编辑类工具栏 | Board 不是 DAG 编辑器 |
| **P2** | Board 运行控制的 Orchestrator 行为说明 | Pause/Stop 对正在运行节点的影响 |

---

## 七、一句话评估

**Prototype v0.4 是一份诚实的概念验证——它证明了 PRD v0.3 的核心概念可以被可视化，但还没有证明它们可以被交互。** 三个视图的布局和信息层级是对的，但用户到达关键操作（审阅浮层实体、查看 patch diff、追溯证据链）的路径还不存在。修正这些交互后，原型才能从"看对了"升级为"用对了"。
