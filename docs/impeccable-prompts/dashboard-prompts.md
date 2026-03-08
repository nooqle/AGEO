# Dashboard Prompts

适用文件：

- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/components/dashboard/DashboardPage.tsx`
- `frontend/src/components/dashboard/HeroSection.tsx`
- `frontend/src/components/dashboard/KPICard.tsx`
- `frontend/src/components/dashboard/MetricDeltaCard.tsx`
- `frontend/src/components/dashboard/MonitoringTab.tsx`
- `frontend/src/components/dashboard/VisibilityTab.tsx`
- `frontend/src/components/dashboard/PlatformTab.tsx`
- `frontend/src/components/dashboard/OptimizationTab.tsx`

## 1. 仪表盘整体升级

```text
使用 impeccable-frontend-design 重做 Specta AI dashboard 的视觉和信息层级。

目标文件：
- frontend/src/app/dashboard/page.tsx
- frontend/src/components/dashboard/DashboardPage.tsx
- frontend/src/components/dashboard/HeroSection.tsx
- frontend/src/components/dashboard/KPICard.tsx
- frontend/src/components/dashboard/MetricDeltaCard.tsx
- frontend/src/components/dashboard/MonitoringTab.tsx
- frontend/src/components/dashboard/VisibilityTab.tsx
- frontend/src/components/dashboard/PlatformTab.tsx
- frontend/src/components/dashboard/OptimizationTab.tsx

业务目标：
- 让 dashboard 看起来更像高价值分析产品，而不是普通后台
- 让关键指标、趋势、行动建议之间的关系更清楚
- 提升专业感、可信度和决策支持感

约束：
- 保留当前数据结构和主要功能模块
- 不改接口和业务逻辑
- 不做“卡片墙式”的普通后台模板

设计方向：
- premium analytical
- 更强调信息密度控制、层级节奏、数据叙事和局部重点强调

执行要求：
- 直接改代码
- 优先处理首屏和关键指标区
- 最后说明如何提升“可读性 + 决策感”
```

## 2. KPI 区域重点打磨

```text
使用 impeccable-polish 打磨 dashboard 的 KPI 与 summary 区域。

目标文件：
- frontend/src/components/dashboard/HeroSection.tsx
- frontend/src/components/dashboard/KPICard.tsx
- frontend/src/components/dashboard/MetricDeltaCard.tsx
- frontend/src/components/dashboard/BaselineInfoCard.tsx

当前问题：
- KPI 可能存在模板感
- 数字、标签、变化趋势和解释文字的层级可能不够清楚
- 卡片之间的节奏和对齐可能影响专业感

要求：
- 不重做 dashboard 架构
- 重点优化字体、间距、强调关系、对比度和局部组件一致性
- 避免夸张装饰，强调成熟感和清晰度

输出要求：
- 直接改代码
- 最后列出你打磨了哪些关键细节
```

## 3. Dashboard 设计问题审查

```text
使用 impeccable-critique 对 dashboard 做设计点评，但先不要改代码。

范围：
- frontend/src/app/dashboard/page.tsx
- frontend/src/components/dashboard/

重点：
- 指标优先级是否明确
- 页面是否有过度卡片化或层级扁平问题
- 用户能否快速抓住“发生了什么、为什么重要、下一步做什么”
- 表格、图表和建议模块之间是否协调

输出要求：
- 先给最重要的问题
- 再给结构化优化建议
- 最后指出应该优先使用哪个 impeccable skill 落地
```

## 4. Dashboard 做得更有品牌感

```text
使用 impeccable-bolder 提升 dashboard 的品牌辨识度，但不要牺牲专业感。

目标文件：
- frontend/src/components/dashboard/DashboardPage.tsx
- frontend/src/components/dashboard/HeroSection.tsx
- frontend/src/components/dashboard/KPICard.tsx

要求：
- 强化首屏视觉焦点和品牌调性
- 可以增强字体表现、版式张力、色彩重心和关键数据强调
- 仍然要保持 B2B 分析产品的可信和克制
- 不要变成营销页，也不要让数据可读性下降

输出要求：
- 直接改代码
- 最后说明哪些变化提升了品牌感
```

## 5. Dashboard 响应式与稳健性

```text
先使用 impeccable-adapt，再使用 impeccable-harden，处理 dashboard 的移动端与边界情况。

目标文件：
- frontend/src/app/dashboard/page.tsx
- frontend/src/components/dashboard/

适配目标：
- 平板和手机宽度下的布局重组
- 表格、图表、指标卡片和 tabs 的可读性
- 超长品牌名、空数据、加载状态、错误状态、极端数值展示

要求：
- 优先做真正影响使用的改动
- 不要仅靠隐藏内容解决问题
- 最后分开说明 adapt 和 harden 各自解决了什么
```

## 6. Dashboard 决策工作台审查

```text
使用 impeccable-audit 审查 Specta AI dashboard 的完整决策体验，但先不要改代码。

范围：
- frontend/src/app/dashboard/page.tsx
- frontend/src/components/dashboard/
- frontend/src/components/charts/

这不是普通后台页面，而是用户理解品牌可见性现状、发现问题、判断优先级和决定下一步动作的决策工作台。
请从以下 4 个层面一起审查：

1. 指标理解层
- 用户是否能快速理解当前表现
- KPI、趋势、对比、变化值之间的关系是否清楚

2. 诊断分析层
- 平台分析、竞品对比、来源数据、优化建议是否形成因果链路
- 用户是否知道“问题是什么、证据是什么、为什么会这样”

3. 决策行动层
- 页面是否清楚引导用户知道下一步做什么
- 建议模块是否真正支持行动，而不只是信息堆砌

4. 状态与消费层
- 空状态、加载状态、错误状态、无数据状态是否足够清楚
- 表格、图表、tab 切换和重点信息浏览是否顺畅

重点：
- 是否存在信息堆叠但缺乏主次
- 是否过度卡片化，导致决策路径被切碎
- 是否像成熟分析产品，而不是普通 BI 页面
- 移动端和平板下是否仍然能完成核心判断

输出要求：
- 按严重程度排序
- 每个问题说明影响范围和修复建议
- 单独指出“指标表达问题”“分析链路问题”“行动引导问题”“状态反馈问题”
- 标注哪些问题更适合后续用 impeccable-polish、impeccable-harden、impeccable-bolder 或 impeccable-frontend-design 处理
```

## 7. Dashboard 行动导向点评

```text
使用 impeccable-critique 对 Specta AI dashboard 的行动导向和专业感做设计点评，但先不要改代码。

范围：
- frontend/src/app/dashboard/page.tsx
- frontend/src/components/dashboard/

请重点判断：
- 用户是否能在短时间内看懂“现在表现如何”
- 用户是否能看懂“为什么会这样”
- 用户是否能自然走到“下一步该做什么”
- 页面是否更像真正的分析产品，而不是信息拼盘
- 品牌感和决策感是否足够强

输出要求：
- 先列最影响决策效率的核心问题
- 再给结构化优化建议
- 区分哪些是信息架构问题，哪些是视觉表达问题，哪些是交互反馈问题
- 最后指出下一步最适合调用哪个 impeccable skill
```
