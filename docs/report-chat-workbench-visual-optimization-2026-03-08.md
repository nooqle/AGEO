# Specta AI 聊天工作台视觉优化文档

**方法**: `impeccable-audit`  
**日期**: 2026-03-08  
**范围**:
- `frontend/src/app/chat/[sessionId]/page.tsx`
- `frontend/src/components/chat/`
- `frontend/src/components/canvas/`
- `frontend/src/components/layout/ChatSidebar.tsx`
- `frontend/src/components/notifications/`

---

## 1. 文档目的

本文件用于整合两轮审查中发现的界面问题，形成一份面向产品、设计、前端共同使用的视觉优化文档。

目标不是讨论后端能力，而是明确以下问题：
- 聊天、状态、交付物三层在视觉上是否有清晰层级
- 用户是否容易发现当前任务状态、可消费结果与下一步动作
- 桌面端与移动端在控件可见性、触达尺寸、信息密度上是否稳定
- 当前界面是否存在明显的“AI 模板感”、交互暗门和视觉噪音

---

## 2. 总体结论

当前聊天工作台已经具备较完整的产品骨架，但视觉和交互组织仍偏向“增强版聊天页”，还没有完全站稳“任务执行台 + 状态展示台 + 报告交付入口”的产品定位。

核心问题集中在四个方面：
- 状态层太弱，存在数据但没有形成稳定可见的状态面板
- 报告入口不稳定，不同断点下入口方式不一致
- 很多关键动作依赖 hover，小屏和触屏体验明显不足
- 视觉语言仍带有较重的通用 AI 产品模板感，工作台气质不够鲜明

`Anti-pattern verdict: Fail`

主要表现：
- 紫色渐变、emoji、圆润胶囊和轻玻璃式高亮占比过高
- 重要动作和次要动作混在一起，按钮密度高但主次不清
- 长报告和长对话都缺少更强的阅读节奏
- 移动端没有建立独立的视觉模型，仍在复用桌面 dropdown / hover 习惯

---

## 3. 优化目标

### 3.1 一级目标

把聊天工作台统一成一套稳定的视觉结构：

1. `主线层`
   - 用户当前在和谁对话
   - 当前任务是否正在推进
   - 当前输入区是否可操作

2. `状态层`
   - 当前阶段
   - 已完成步骤
   - 等待中 / 失败 / 重连 / 可安全离开
   - 下一步需要用户做什么

3. `交付层`
   - 已生成了什么
   - 新结果在哪里看
   - 如何从报告回到对话上下文

4. `结果消费层`
   - 用户当前可以先看什么
   - 用户读完之后下一步做什么

### 3.2 二级目标

- 降低信息过载
- 提升移动端可发现性
- 提升控件触达稳定性
- 降低“AI 模板感”
- 建立更专业的分析工作台气质

---

## 4. 严重问题清单

以下问题按严重程度排序，并合并了结构问题与 UI 细节问题。

### P0. 执行状态层太弱，没有形成稳定的视觉信息层

**分类**:
- 状态反馈问题
- 结果消费问题

**位置**:
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/components/chat/ProgressIndicator.tsx`

**现象**:
- 后端已经持续推送 `executionProgress`、`steps`、`subTasks`、`stageResults`
- 聊天工作台里主要只显示一个 `TaskStatusBadge`
- 输入框底部只有一行执行文案
- 没有稳定的“步骤进度区 / 当前阻塞区 / 平台并行状态区”

**影响范围**:
- 首次分析
- 多轮追问
- 断线重连
- 长任务等待
- 失败后恢复

**用户影响**:
- 用户看不清任务做到哪一步
- 用户不知道当前是“继续运行中”还是“卡住”
- 用户不知道是否该等待、刷新、停止还是重试

**视觉/交互问题**:
- badge 过轻，无法承担状态台职责
- 进度信息被压缩成碎片化短句
- 状态数据存在，但视觉承载缺位

**优化建议**:
- 将状态从 header 小徽章提升为明确的二级信息区
- 固定展示当前阶段、完成步骤、当前等待原因、异常入口
- 在执行中为用户提供稳定的“状态锚点”，不要让状态散落在输入框和系统消息里

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-clarify`

---

### P0. 报告入口不稳定，桌面和移动端不是一套清晰的交付链路

**分类**:
- 报告交付问题
- 上下文衔接问题

**位置**:
- `frontend/src/components/layout/ChatLayout.tsx`
- `frontend/src/components/layout/ArtifactNav.tsx`
- `frontend/src/components/canvas/CanvasPanel.tsx`

**现象**:
- 桌面端存在一条 48px 的 artifact rail，但空状态时 rail 仍占位
- `ArtifactNav` 在没有内容时直接不渲染，造成“有栏无信息”
- 移动端没有对应的稳定交付入口
- `CanvasToggle` 存在但没有形成统一入口模型

**影响范围**:
- 首次进入
- 报告未生成时
- 报告刚生成时
- 小屏和触屏环境

**用户影响**:
- 用户不知道报告入口在哪里
- 用户不知道是否已经有结果可看
- 用户不知道当前结果是聊天的一部分还是独立交付物

**视觉/交互问题**:
- 桌面端入口太窄且语义弱
- 移动端入口弱于桌面端
- 空态缺少明确 CTA

**优化建议**:
- 建立显式且持续存在的交付入口
- 空状态也要显示“报告区尚未生成”的可理解提示
- 桌面与移动采用同一套交付链路语义，只改变容器形式

**更适合的 skill**:
- `impeccable-frontend-design`
- `impeccable-clarify`

---

### P0. 关键操作大量依赖 hover，移动端存在明显可用性问题

**分类**:
- 聊天问题
- 状态反馈问题

**位置**:
- `frontend/src/components/chat/Message/UserMessage.tsx`
- `frontend/src/components/chat/MessageActions.tsx`
- `frontend/src/components/layout/ChatSidebar.tsx`
- `frontend/src/components/notifications/AlertCard.tsx`

**现象**:
- 回退按钮 hover 才出现
- agent 消息菜单 hover 才出现
- 品牌列表菜单 hover 才出现
- 通知忽略按钮 hover 才出现

**影响范围**:
- 移动端
- 平板触摸设备
- 非熟练用户

**用户影响**:
- 很多关键能力像“暗门”
- 用户不知道可以回退、重试、忽略、删除
- 失败恢复和上下文修正效率低

**视觉/交互问题**:
- 控件发现性差
- 触屏下几乎等于隐藏
- 重要动作没有稳定存在感

**优化建议**:
- 核心动作在移动端常显或有固定入口
- 不要把回退、重试、通知管理这类动作藏在 hover 态
- 重新区分“危险动作”和“高频修正动作”的露出策略

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-polish`

---

### P0. 通知面板在移动侧栏中的视觉模型和尺寸模型不成立

**分类**:
- 状态反馈问题

**位置**:
- `frontend/src/components/layout/ChatSidebar.tsx`
- `frontend/src/components/notifications/NotificationPanel.tsx`
- `frontend/src/components/layout/MobileDrawer.tsx`

**现象**:
- 侧栏抽屉宽度是 `280px`
- 通知面板固定宽度是 `380px`
- 抽屉 `overflow-hidden`
- 通知仍沿用桌面 dropdown 形态

**用户影响**:
- 小屏下通知弹层容易被裁切
- 即使功能不报错，视觉上也不属于同一套体系

**优化建议**:
- 移动端通知改成全宽 sheet / drawer
- 停止在移动端复用桌面 dropdown 尺寸和交互

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-frontend-design`

---

### P1. 新交付物到达后自动展开 Canvas，造成对话与结果抢焦点

**分类**:
- 报告交付问题
- 上下文衔接问题

**位置**:
- `frontend/src/hooks/useWebSocket.ts`
- `frontend/src/stores/canvasStore.ts`

**现象**:
- 新增 artifact 时默认 `isOpen: true`
- 布局会自动切换成 split
- 对话区宽度突然收缩

**用户影响**:
- 用户正在看聊天或状态时被强行拉去看交付物
- 信息过载被进一步放大

**视觉/交互问题**:
- 布局主动打断用户注意力
- 交付物出现时缺少更温和的视觉提示机制

**优化建议**:
- 结果到达时优先提示“新结果已生成”
- 由用户决定是否展开 Canvas
- 自动展开仅适用于极少数关键里程碑

**更适合的 skill**:
- `impeccable-frontend-design`
- `impeccable-polish`

---

### P1. 完成 / 失败 / 重连的视觉桥接太短，无法稳定承接任务上下文

**分类**:
- 上下文衔接问题
- 结果消费问题

**位置**:
- `frontend/src/components/chat/ReconnectionBanner.tsx`
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/components/chat/TaskStatusBadge.tsx`

**现象**:
- 完成 banner 8 秒后自动消失
- 失败重试只是重新发送品牌名
- badge 只显示“完成/失败”，不承接更多上下文

**用户影响**:
- 用户回来后不知道该先看哪里
- 失败恢复缺少原任务语义
- “继续当前任务”与“重跑任务”边界模糊

**优化建议**:
- 完成态 CTA 至少应保留到用户处理
- 失败态保留失败阶段、原因与原任务上下文
- 重试入口应绑定原任务参数，不要退化成粗粒度重开

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-clarify`

---

### P1. 空状态仍像普通聊天欢迎页，不像任务执行工作台

**分类**:
- 聊天问题
- 报告交付问题

**位置**:
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/canvas/CanvasPanel.tsx`
- `frontend/src/components/chat/ChatPanel.tsx`

**现象**:
- 紫色渐变图标
- emoji 主视觉
- 三栏 marketing 风格亮点
- Canvas 空状态与聊天空状态彼此独立

**用户影响**:
- 用户不清楚完整工作链路
- 第一屏更像宣传页，不像分析工作台
- 移动端三栏亮点会明显拥挤

**优化建议**:
- 改成工作台 onboarding
- 明确呈现“发起任务 -> 查看状态 -> 打开结果 -> 继续追问”
- 减少装饰型 AI 视觉符号

**更适合的 skill**:
- `impeccable-frontend-design`
- `impeccable-clarify`

---

### P1. 从聊天打开报告时，可能先打开预览壳，再被真实内容覆盖

**分类**:
- 报告交付问题
- 上下文衔接问题

**位置**:
- `frontend/src/components/chat/ChatPanel.tsx`
- `frontend/src/components/chat/Message/OutputCard.tsx`

**现象**:
- 历史消息和历史 artifact 异步分开加载
- 用户点击消息里的 `OutputCard` 时，组件会用 preview 数据构造临时 content

**用户影响**:
- 先看到不完整结果，再被真实数据替换
- 聊天到报告的链路显得不稳定

**优化建议**:
- 优先打开 store 内已存在 artifact
- 若完整内容未就绪，应显示明确 loading 态
- 不要用 preview 数据伪造“完整报告”

**更适合的 skill**:
- `impeccable-harden`

---

## 5. UI 细节问题清单

以下问题更偏向视觉质感、排版、控件细节和响应式细部。

### P1. 空状态视觉语言过于“通用 AI 模板化”

**位置**:
- `frontend/src/components/chat/MessageList.tsx`

**表现**:
- 紫色渐变球
- emoji 图标
- 三栏 feature highlights
- 整体像常见 AI SaaS 迎宾页

**影响**:
- 品牌辨识度不足
- 工作台专业感偏弱

**建议**:
- 改为更克制、更像分析控制台的工作台空状态
- 将“开始分析”的路径做成明确主 CTA

**更适合的 skill**:
- `impeccable-frontend-design`

---

### P1. 关键控件触达尺寸不足，重要按钮太轻

**位置**:
- `frontend/src/components/notifications/NotificationBell.tsx`
- `frontend/src/components/canvas/CanvasTabs.tsx`
- `frontend/src/components/chat/Message/UserMessage.tsx`
- `frontend/src/components/chat/InputArea.tsx`

**表现**:
- 多个图标按钮小于推荐触达尺寸
- Tab 关闭按钮、消息回退按钮、铃铛按钮偏小

**影响**:
- 触屏误触率高
- 可达性较弱
- 视觉上显得“细碎”

**建议**:
- 将核心操作统一提升到 44px 左右的触达标准
- 高风险动作和高频动作分开处理

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-polish`

---

### P1. Canvas 头部动作区过密，图标按钮过多

**位置**:
- `frontend/src/components/canvas/CanvasHeader.tsx`

**表现**:
- 复制、分享、导出、展开、关闭并列
- 导出菜单里还常驻两个“即将推出”
- 大部分动作只有图标，没有文本

**影响**:
- 头部认知负担大
- 视觉上拥挤
- 高频与低频动作没有明显优先级

**建议**:
- 保留最高频动作外显
- 将低频动作收纳进菜单
- “即将推出”功能不要长期占据主头部

**更适合的 skill**:
- `impeccable-polish`
- `impeccable-clarify`

---

### P1. 长报告视觉节奏单一，卡片堆叠感过强

**位置**:
- `frontend/src/components/canvas/contents/ReportContent.tsx`
- `frontend/src/components/canvas/contents/*Section.tsx`

**表现**:
- 大多数 section 采用相似的卡片、边框、圆角和间距
- 不同性质信息缺少明显的视觉语气差异

**影响**:
- 长报告容易形成阅读疲劳
- 用户扫读重点困难

**建议**:
- 拉开摘要、风险、行动项、来源分析的视觉语气差异
- 增强章节节奏和重点锚点

**更适合的 skill**:
- `impeccable-frontend-design`
- `impeccable-polish`

---

### P2. 聊天主回复缺少统一收束规则，信息块边界模糊

**位置**:
- `frontend/src/components/chat/Message/AgentMessage.tsx`

**表现**:
- 正文无容器
- plan/action/output/confirmation 各自风格不完全统一
- 长消息时模块之间关系不够稳定

**影响**:
- 对话区阅读秩序弱
- 容易显得“块很多但层级不清”

**建议**:
- 定义正文层、辅助层、操作层的统一间距与分隔规范
- 不一定要加重卡片，但要统一节奏

**更适合的 skill**:
- `impeccable-frontend-design`
- `impeccable-polish`

---

### P2. 小字号使用过多，中文阅读密度偏紧

**位置**:
- `frontend/src/components/chat/Message/AgentMessage.tsx`
- `frontend/src/components/chat/TaskStatusBadge.tsx`
- `frontend/src/components/chat/FollowUpChips.tsx`
- `frontend/src/components/chat/Message/MarkdownContent.tsx`

**表现**:
- 10px 到 12px 文本大量出现
- 正文 `leading-normal`
- 辅助信息主要通过“缩小”区分层级

**影响**:
- 暗色主题下更显灰、更累
- 长时间使用工作台会有疲劳感

**建议**:
- 减少 11px 以下文本
- 用字重、间距、对比而不是单纯缩小来区分层级
- 正文提高行高

**更适合的 skill**:
- `impeccable-polish`
- `impeccable-clarify`

---

### P2. 追问 chips 更像弱标签，不像真正的下一步 CTA

**位置**:
- `frontend/src/components/chat/FollowUpChips.tsx`

**表现**:
- 字号小
- icon 小
- 边框和底色弱
- 推荐项与普通项差异不足

**影响**:
- 完成分析后，“下一步做什么”没有被足够突出

**建议**:
- 给首个推荐动作更明确的主 CTA 视觉
- 其余建议保持次级

**更适合的 skill**:
- `impeccable-clarify`
- `impeccable-frontend-design`

---

### P2. 通知卡片对齐较稳，但“忽略”能力仍是视觉暗门

**位置**:
- `frontend/src/components/notifications/AlertCard.tsx`

**表现**:
- 关闭按钮 hover 才显示
- 移动端不可发现

**影响**:
- 通知管理能力不完整

**建议**:
- 移动端常显或稳定预留位置
- 不再把通知管理入口全部藏在 hover

**更适合的 skill**:
- `impeccable-harden`
- `impeccable-polish`

---

### P2. Markdown 排版可用，但仍停留在“技术预览”质感

**位置**:
- `frontend/src/components/chat/Message/MarkdownContent.tsx`

**表现**:
- 标题、段落、表格、代码块样式都较基础
- 缺少更成熟的分析文档排版节奏

**影响**:
- 在聊天中尚可
- 作为正式分析解释文本时质感不够

**建议**:
- 将 Markdown 风格向“分析师注释 / 工作台正文”靠拢
- 强化段落、列表、表格的阅读秩序

**更适合的 skill**:
- `impeccable-polish`
- `impeccable-frontend-design`

---

### P3. 配色仍有明显“紫色优先”惯性

**位置**:
- `frontend/src/components/chat/Message/AgentMessage.tsx`
- `frontend/src/components/canvas/CanvasHeader.tsx`
- `frontend/src/components/chat/MessageList.tsx`

**表现**:
- Agent 头像
- 欢迎态主视觉
- 推荐态与标签态
- 各类高亮经常落在紫色系

**影响**:
- 容易继续强化“通用 AI 产品模板感”

**建议**:
- 后续建立更贴近 Specta AI 的工作台配色策略
- 不要让紫色承担所有“智能感”

**更适合的 skill**:
- `impeccable-frontend-design`

---

### P3. 个别语义和 aria 细节仍不够精细

**位置**:
- `frontend/src/components/chat/FollowUpChips.tsx`
- `frontend/src/components/notifications/NotificationPanel.tsx`

**表现**:
- 原生 `button` 上重复声明 `role="button"`
- 通知面板更像 popover / dialog，但语义较宽泛

**影响**:
- 不会直接阻断使用，但细节不够严谨

**建议**:
- 清理冗余 role
- 统一弹层语义

**更适合的 skill**:
- `impeccable-harden`

---

## 6. 系统性问题总结

### 6.1 信息层级问题

当前不是没有层级，而是层级存在但不稳定：
- 聊天主线存在
- 执行状态存在
- 交付物存在
- 下一步建议存在

但这些层没有被稳定组织成一套视觉秩序，导致用户需要自己拼接。

### 6.2 控件露出策略问题

当前界面把很多关键能力处理成了“知道的人会用”的专家型入口：
- 回退
- 重试
- 忽略通知
- 更多操作
- 报告入口

这对新用户和移动端都不友好。

### 6.3 响应式模型问题

当前更多是在做“桌面版缩到小屏”，而不是“为小屏重构信息与动作组织”。

主要表现：
- 桌面 dropdown 直接进入移动端
- hover 行为进入触屏环境
- 三栏和横向标签在窄屏里仍保持原结构

### 6.4 视觉语言问题

当前界面已经有自己的 token 和组件基础，但仍保留明显的通用 AI 审美惯性：
- 紫色过多
- 渐变过多
- 胶囊过多
- 关键 CTA 不够坚定
- 正式交付页与聊天正文的视觉差异不够强

---

## 7. 优化优先级建议

### 第一阶段：先修可用性与状态认知

目标：
- 让用户知道现在发生了什么
- 让移动端核心操作可发现、可点击

建议优先处理：
1. 状态层升级为稳定信息区
2. 移动端关键动作常显
3. 通知移动端模型重做
4. 报告入口显式化

建议 skill：
- `impeccable-harden`
- `impeccable-clarify`

### 第二阶段：重构聊天 / 状态 / 报告三层关系

目标：
- 降低信息过载
- 让报告成为自然延伸，而不是突然打开的侧栏

建议优先处理：
1. Canvas 打开策略
2. 报告入口和新结果提示
3. 完成态 / 失败态 / 重连态桥接
4. 空状态改造成工作台 onboarding

建议 skill：
- `impeccable-frontend-design`
- `impeccable-clarify`

### 第三阶段：做视觉打磨和阅读质感优化

目标：
- 提升工作台专业感
- 降低通用 AI 模板感

建议优先处理：
1. 报告节奏和 section 差异化
2. 小字号与行高体系
3. CTA 主次重排
4. Markdown 和长内容排版
5. 配色收敛

建议 skill：
- `impeccable-polish`
- `impeccable-frontend-design`

---

## 8. 建议的 skill 映射

### 更适合用 `impeccable-harden` 处理

- 状态层缺失或太弱
- 移动端 hover-only 问题
- 通知面板在移动端裁切
- OutputCard 打开预览壳问题
- aria / 语义 / 触达尺寸问题

### 更适合用 `impeccable-clarify` 处理

- 空状态工作台文案
- 状态文案与完成态引导
- 报告入口提示
- 下一步建议 CTA 文案
- 完成 / 失败 / 重连承接文案

### 更适合用 `impeccable-polish` 处理

- 控件尺寸、间距、对齐
- 小字号与层级节奏
- Canvas 头部动作精简
- Notification / chip / tag 的细节收口
- Markdown 排版质感

### 更适合用 `impeccable-frontend-design` 处理

- 聊天工作台整体视觉方向
- 聊天 / 状态 / 交付三层结构
- 报告页节奏重构
- 空状态和结果入口重设计
- 去模板化配色与工作台气质建立

---

## 9. 验收标准建议

视觉优化完成后，至少应达到以下结果：

### 聊天层
- 用户一眼能分辨正文、系统状态、确认动作、结果入口
- 回退、重试等关键动作在移动端也可发现

### 状态层
- 用户能明确知道当前阶段、当前等待原因、已完成步骤
- 失败时有明确恢复路径
- 重连后用户知道该看哪里、做什么

### 报告层
- 用户始终知道报告入口在哪里
- 有新结果时有明显但不过度打断的提示
- 报告与对话之间的来回跳转清楚可控

### 结果消费层
- 完成后用户能明确知道“先看什么”
- 看完之后知道“下一步做什么”
- 默认界面不会制造过度信息堆叠

### UI 细节
- 核心控件满足基本触达尺寸
- 小字号显著减少
- 移动端无明显裁切和隐藏暗门
- 整体气质更像分析工作台，而不是通用 AI 聊天页

---

## 10. 结论

这套聊天工作台当前最需要的不是继续往里加能力，而是把已有能力重新组织成一套更稳定的视觉秩序。

如果只做单点修补，问题会继续表现为：
- 状态数据越来越多，但用户还是看不懂
- 交付物越来越丰富，但入口还是不稳定
- 聊天越来越强，但工作台定位还是像聊天页

更合理的推进顺序是：

1. 先补强状态层与移动端可用性  
2. 再重构交付入口与完成态桥接  
3. 最后统一视觉语言、排版节奏和工作台气质
