# Specta AI 报告交付体验视觉设计稿

**方法**: `impeccable-critique` + UX 视角拆解  
**日期**: 2026-03-08  
**状态**: Draft  
**范围**:
- `frontend/src/components/canvas/`
- `frontend/src/components/canvas/contents/`
- `frontend/src/components/chat/`
- `frontend/src/components/notifications/`

---

## 1. 文档目的

本文件用于将“报告交付体验”的视觉优化 TODO 转成一份可执行的设计稿说明，供产品、UX、视觉和前端共同对齐。

本次文档默认接受以下前提：
- 当前信息层级整体成立，不在本稿中重做信息架构
- 本稿只聚焦视觉表现、阅读节奏、控件权重、状态反馈和交付感
- 本稿不直接约束后端数据结构，也不要求本轮改动交互主流程

---

## 2. 设计目标

### 2.1 一级目标

当用户进入聊天与报告界面时，应立即感受到：

1. 这是一份正式交付物，而不是聊天附属面板  
2. 当前主角是报告内容，工具按钮只是辅助  
3. 我能轻松切换、回看、定位重点，不会被界面噪音打断  

### 2.2 二级目标

- 降低“通用 AI 工作台”气质
- 增强“分析报告”而非“功能卡片”的文档感
- 提升长内容阅读舒适度
- 提升报告切换、版本切换、关联回看时的稳定感

---

## 3. 用户心智假设

本稿默认的核心用户心智如下：

- 用户已经发起分析，当前希望消费结果，而不是研究系统本身
- 用户默认会把“报告标题、摘要、更新时间、版本”当作交付页入口
- 用户不希望在阅读报告时被过多 hover、chip、badge、微动效打断
- 用户愿意接受工作台式辅助能力，但前提是这些能力不能盖过报告主体

---

## 4. 当前视觉问题总览

当前界面的问题不在于“不能用”，而在于“像工具，不像交付物”。

主要表现：
- Header 更像工具栏，不像报告页眉
- 报告各 section 卡片语法过于统一，长页阅读节奏偏单一
- badge / pill 使用过多，页面带有明显 dashboard / AI workbench 气质
- 聊天侧的渐变、chip、提示文案仍在持续释放“AI 产品模板感”
- 某些半成品状态直接暴露在交付界面中，削弱专业感

`Anti-pattern verdict: Partial fail`

不是典型 AI slop，但仍保留明显的 AI 工具界面指纹。

---

## 5. 设计原则

### 5.1 报告优先

报告页中的视觉重心必须稳定落在：
- 标题
- 摘要
- 章节内容

而不是：
- 图标按钮
- 状态 chip
- hover 装饰

### 5.2 文档感优先于卡片感

信息可以继续用卡片承载，但整体阅读体验应更接近“分析文档”而不是“控制面板”。

### 5.3 节制的强调

强调色只用于：
- 关键状态
- 关键 CTA
- 重点数据

不要让所有模块都在争夺注意力。

### 5.4 识别快于解释

用户扫一眼就应知道：
- 这是页眉
- 这是摘要
- 这是风险
- 这是行动项

不应依赖读完整段文字后才理解模块作用。

---

## 6. 模块拆分 TODO

以下按模块拆分为设计稿任务。每项包含：
- 问题
- 用户感知
- 设计动作
- 验收标准

---

## 7. Canvas Header 设计稿

**对应文件**:
- `frontend/src/components/canvas/CanvasHeader.tsx`

### 7.1 问题

- 当前页眉标题过轻，视觉中心落在右侧图标按钮
- 操作区过密，复制、导出、展开、关闭几乎同权
- “即将推出”能力长期暴露在主头部，削弱完成度
- 类型标签、版本、跳转对话都偏轻，像辅助信息而非正式报告元数据

### 7.2 用户感知

用户打开报告时，第一感觉更像“操作一个侧栏工具”，而不是“阅读一份分析交付物”。

### 7.3 设计动作

1. 重新定义页眉层级
   - 一级：报告标题
   - 二级：类型 / 更新时间 / 版本 / 平台范围
   - 三级：辅助操作

2. 收敛右侧操作区
   - 高优先动作外显：导出、关闭
   - 次级动作收纳：复制、分享、展开等
   - 避免 5 个以上同权图标并排

3. 去除半成品感
   - 不在主菜单常驻展示“即将推出”
   - 未开放能力要么隐藏，要么进入说明态，不要混入主操作

4. 提升文档页眉气质
   - 标题更大、更稳
   - 元信息更规整
   - 行高、留白、分组更接近报告页眉

### 7.4 验收标准

- 用户 2 秒内能确定当前看到的是哪份报告
- 标题是页内最强视觉锚点之一
- 工具按钮不会先于标题吸引注意力
- 页眉不再暴露“半完成功能”痕迹

---

## 8. Canvas Tabs 设计稿

**对应文件**:
- `frontend/src/components/canvas/CanvasTabs.tsx`

### 8.1 问题

- Tab 标题宽度过窄，长标题容易被截断成相似块
- 关闭按钮噪音偏高，削弱 tab 本身的信息识别
- `NEW` 标签风格偏内部标记，不够交付化

### 8.2 用户感知

当 artifact 较多时，用户会先看到一排相似的标签块，而不是清晰的报告切换入口。

### 8.3 设计动作

1. 提升 tab 可读性
   - 放宽标题最大宽度
   - 提升选中态辨识度
   - 让当前 tab 更像“当前文档”

2. 降低关闭动作侵入感
   - 关闭按钮默认更安静
   - 避免每个 tab 都像“可删除标签”

3. 更新提示去工程化
   - 将 `NEW` 改成更克制的更新提示
   - 强调“内容有更新”，不要强调“系统打了标”

### 8.4 验收标准

- 用户可以快速区分多个 artifact
- tab 切换更像文档导航，不像浏览器调试标签
- 更新提示存在，但不会抢主内容焦点

---

## 9. Report 首屏设计稿

**对应文件**:
- `frontend/src/components/canvas/contents/ReportContent.tsx`
- `frontend/src/components/canvas/contents/ReportSummarySection.tsx`

### 9.1 问题

- 首屏标题、副标题、更新时间之间层级差还不够大
- “品牌现状”区块虽然结构清晰，但仍偏组件感
- 指标卡和摘要卡更像 dashboard 模块，而不是执行摘要

### 9.2 用户感知

用户会理解“这里有摘要”，但未必立刻感受到“这是报告首页”。

### 9.3 设计动作

1. 强化首屏封面感
   - 主标题更明确
   - 副标题更稳定
   - 更新时间、平台范围做成整齐的元信息带

2. 将 Summary 区升级为执行摘要
   - 摘要块视觉权重高于普通 section
   - 指标卡减少模板感，提升主指标与次说明区分度
   - 让“战况摘要”更像主结论，而不是普通 bullet box

3. 增加阅读呼吸感
   - 拉开首屏与后续 section 的空间
   - 不让首屏看起来只是正文第一段

### 9.4 验收标准

- 首屏看起来像“正式报告首页”
- 用户先看到主结论，再看到支撑指标
- 报告开头具备明显的交付气质

---

## 10. Report Sections 通用视觉稿

**对应文件**:
- `frontend/src/components/canvas/contents/ScenarioCoverageSection.tsx`
- `frontend/src/components/canvas/contents/CompetitorBattleSection.tsx`
- `frontend/src/components/canvas/contents/RiskSection.tsx`
- `frontend/src/components/canvas/contents/SourceSection.tsx`
- `frontend/src/components/canvas/contents/ActionQueueSection.tsx`

### 10.1 问题

- 多个 section 使用近似同一张卡片模板
- 边框、圆角、密度、标签语法重复度高
- 长页中容易形成“卡片堆叠疲劳”

### 10.2 用户感知

用户虽然知道每个 section 在讲什么，但页面在视觉上缺少节奏变化，读久了会有“都差不多”的感觉。

### 10.3 设计动作

建立三类 section 视觉语法：

1. `摘要/概览型`
   - 适用于 Summary、Source 总览
   - 更强调留白、数字、概览结论

2. `诊断/风险型`
   - 适用于 Risk、部分 Competitor
   - 更强调警示、判断依据、问题陈述

3. `执行/行动型`
   - 适用于 Action Queue
   - 更强调优先级、动作、目标和预期结果

补充规范：
- 不是所有信息都需要胶囊标签
- 不是所有容器都需要完整边框
- section 标题、摘要框、子项卡片要拉开语气差异

### 10.4 验收标准

- 连续浏览多个 section 时仍能快速感知章节差异
- 风险、行动、来源分析不会再显得像同构卡片
- 页面整体更像编辑过的分析文档，而不是模块拼装页

---

## 11. Badge / Pill 使用规范

**涉及文件**:
- `frontend/src/components/canvas/contents/*Section.tsx`
- `frontend/src/components/canvas/CanvasHeader.tsx`
- `frontend/src/components/chat/FollowUpChips.tsx`

### 11.1 问题

- badge 与 pill 使用频率过高
- 很多元信息都被做成视觉强调
- 导致页面呈现 dashboard 化、AI workbench 化

### 11.2 用户感知

每块内容都在“发光”或“打标签”，页面会显得忙、碎、焦点分散。

### 11.3 设计动作

建立 badge 使用约束：

- 只对以下信息使用高强调 badge
  - 风险等级
  - 动作优先级
  - 当前版本或关键状态

- 以下信息不再默认使用强调 badge
  - 普通平台名
  - 普通来源标题
  - 普通辅助属性

- 优先用以下形式替代
  - 文本行
  - definition row
  - 轻列表
  - 次级标签

### 11.4 验收标准

- badge 数量明显下降
- 页面看起来更稳、更安静
- 高强调标签真正只服务于少数关键信息

---

## 12. 聊天区气质收敛设计稿

**对应文件**:
- `frontend/src/components/chat/Message/AgentMessage.tsx`
- `frontend/src/components/chat/Message/OutputCard.tsx`
- `frontend/src/components/chat/FollowUpChips.tsx`
- `frontend/src/components/chat/Message/MarkdownContent.tsx`

### 12.1 问题

- Agent 头像使用紫色渐变，AI 产品模板感明显
- OutputCard 的发光、hover、图标组合仍偏功能卡
- Follow-up chips 更像轻标签，不像真正下一步动作
- Markdown 排版仍偏技术预览风格，缺少分析文本质感

### 12.2 用户感知

用户在聊天区仍能明显感受到“这是一个 AI 工具”，而不是“我正在消费一套专业分析产出”。

### 12.3 设计动作

1. 收敛 AI 装饰感
   - 头像更克制
   - 降低默认渐变和泛紫强调
   - 减少“智能感装饰”承担品牌角色

2. 调整 OutputCard 语气
   - 更像交付入口
   - 更少发光和悬浮炫技
   - 标题、用途说明、进入动作更清楚

3. 强化下一步 CTA
   - 首个推荐动作应更明确
   - 其余建议维持次级
   - 不能全部做成同权弱 chip

4. 提升 Markdown 阅读质感
   - 正文行高提高
   - 标题层级拉开
   - 表格、列表、段落更像分析注释而不是技术文档预览

### 12.4 验收标准

- 聊天区和报告区的气质差异更合理
- 聊天区不会持续把用户拉回“AI 工具”心智
- 长解释文本更耐读

---

## 13. 通知与完成态视觉稿

**对应文件**:
- `frontend/src/components/notifications/NotificationPanel.tsx`
- `frontend/src/components/notifications/AlertCard.tsx`
- `frontend/src/components/chat/ReconnectionBanner.tsx`
- `frontend/src/components/chat/TaskStatusBadge.tsx`

### 13.1 问题

- 通知区更偏系统告警，不够像“交付完成提示”
- 完成 banner 与 badge 的视觉承接较弱
- 某些关键动作仍偏轻或偏 hover-only

### 13.2 用户感知

用户能知道“有事发生了”，但不一定感受到“我有一个正式结果可以去看”。

### 13.3 设计动作

1. 完成态更明确
   - 把“分析已完成”做成更稳定的结果提示
   - CTA 更明确指向报告消费

2. 通知卡更专业
   - 让已读/未读、严重度、目标对象更容易扫读
   - 减少隐藏动作暗门

3. Badge 更节制
   - 避免过度依赖小字号、细色块承担重要反馈

### 13.4 验收标准

- 用户看到完成态时，会自然联想到“可以去看报告”
- 通知区不只是告警区，也能承接结果消费语义
- 核心动作不再依赖 hover 发现

---

## 14. 视觉系统统一任务

### 14.1 Typography

- 减少 11px 及以下文本的使用比例
- 用字重、留白、对比度而不是一味缩小字号来区分层级
- 报告正文、元信息、标签、按钮建立固定字号档位

### 14.2 Radius

- 统一圆角体系
- 避免 `lg / xl / 2xl / full` 随意混用导致页面风格松散

### 14.3 Border & Surface

- 一级容器、二级容器、强调容器要有明确区分
- 避免所有块都依赖同一种 subtle border

### 14.4 Color

- 限定颜色职责
  - 绿色：正向状态
  - 红色：风险与错误
  - 琥珀：警示与处理中
  - 品牌强调色：关键 CTA / 主交互

- 不让紫色承担所有“智能感”和所有强调任务

---

## 15. 设计实施优先级

### P0

- `CanvasHeader`
- `CanvasTabs`
- `ReportContent` 首屏
- `ReportSummarySection`

### P1

- `ScenarioCoverageSection`
- `CompetitorBattleSection`
- `RiskSection`
- `ActionQueueSection`
- `SourceSection`

### P1

- `AgentMessage`
- `OutputCard`
- `FollowUpChips`
- `MarkdownContent`

### P2

- `NotificationPanel`
- `AlertCard`
- `ReconnectionBanner`
- `TaskStatusBadge`

---

## 16. 验收标准

优化完成后，应满足以下用户感知结果：

### 报告感

- 用户进入后第一反应是“在看报告”，不是“在操作右侧工具”
- 页眉、摘要、章节结构形成稳定阅读路径

### 专业感

- 页面不再暴露明显的半成品提示和工程化标记
- badge、chip、颜色和边框使用更克制

### 阅读感

- 长页阅读更轻松
- section 之间差异清晰
- 重点更容易扫读

### 结果消费感

- 结果入口更稳
- 回看、切换、定位更顺
- 交付物整体看起来更可信、更完整

---

## 17. 结论

这次视觉优化的重点不是“再加更多花样”，而是收敛。

需要收敛的不是功能，而是噪音：
- 收敛工具栏感
- 收敛模板化卡片感
- 收敛 badge 泛滥
- 收敛 AI 产品默认审美痕迹

当这些细节被收敛后，现有的信息层级和报告骨架才会真正显得像一套正式交付体验。
