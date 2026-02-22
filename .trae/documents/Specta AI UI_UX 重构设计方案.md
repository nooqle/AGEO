# Specta AI UI/UX 重构设计方案

## 项目概述
完成第一阶段（Landing Page + Design System）和第二阶段（数据可视化 + 响应式设计）的全部内容。

## 技术栈
- Next.js 16.1.6 + React 19.2.3
- Tailwind CSS v4
- Framer Motion (动画)
- Recharts (数据可视化)
- Radix UI (组件基础)

---

## 第一阶段：Landing Page + Design System

### 1.1 新建 Landing Page (`app/page.tsx` 重构)

**设计概念**：
- 参考 Manus 的极简主义
- 深色/浅色双主题
- 大字体 Hero Section
- 清晰的价值主张

**页面结构**：
```
Landing Page
├── Navigation (固定顶部)
├── Hero Section (全屏)
├── Features Section (3个核心功能)
├── How It Works (TPAOR流程可视化)
├── Use Cases (使用案例)
├── CTA Section (行动召唤)
└── Footer
```

**视觉设计**：
- 主色调：Indigo 600 (#4F46E5)
- 背景：渐变深色 (from-gray-900 to-gray-800)
- 强调色：Cyan 400 (#22D3EE)
- 字体：Inter (系统字体)

### 1.2 Design System 建立

**色彩系统** (`app/globals.css`):
```css
:root {
  /* 主色 */
  --primary-50: #EEF2FF;
  --primary-100: #E0E7FF;
  --primary-500: #6366F1;
  --primary-600: #4F46E5;
  --primary-700: #4338CA;
  
  /* 强调色 */
  --accent-cyan: #22D3EE;
  --accent-purple: #A855F7;
  --accent-pink: #EC4899;
  
  /* 中性色 */
  --gray-50: #F9FAFB;
  --gray-100: #F3F4F6;
  --gray-800: #1F2937;
  --gray-900: #111827;
}
```

**组件库** (`components/ui/`):
- Button (变体: primary, secondary, ghost, outline)
- Card (变体: default, hover, interactive)
- Input (带图标支持)
- Badge (状态标签)
- Tooltip
- Progress
- Skeleton (加载状态)

### 1.3 TPAOR 流程可视化优化

**ProcessStep 组件升级**:
- 垂直时间线布局
- 步骤状态指示 (pending, active, completed, error)
- 可展开/折叠详情
- 实时进度百分比
- 工具调用可视化

---

## 第二阶段：数据可视化 + 响应式设计

### 2.1 数据可视化组件

**Chart Components** (`components/charts/`):
1. **RadarChart** - 品牌对比雷达图
   - 维度：知名度、美誉度、差异化、忠诚度、创新度
   - 多品牌对比

2. **LineChart** - 趋势折线图
   - 时间序列数据
   - 多线对比
   - 交互式提示框

3. **BarChart** - 柱状图
   - 竞品对比
   - 平台分布

4. **PieChart** - 饼图
   - 情感分析分布
   - 平台占比

5. **MetricCard** - 指标卡片
   - 大数字展示
   - 趋势指示器
   - 环比/同比

### 2.2 A5 分析结果展示优化

**ReportDashboard 组件**:
```
ReportDashboard
├── SummaryCards (关键指标概览)
├── BrandComparison (品牌对比雷达图)
├── SentimentAnalysis (情感分析饼图)
├── PlatformDistribution (平台分布柱状图)
├── TrendAnalysis (趋势折线图)
├── SWOTAnalysis (SWOT矩阵)
└── Recommendations (优化建议列表)
```

### 2.3 响应式设计

**断点设计**:
- Mobile: < 640px
- Tablet: 640px - 1024px
- Desktop: > 1024px
- Large Desktop: > 1280px

**移动端适配**:
- 底部固定输入栏
- 侧边栏变为抽屉式
- 图表自适应宽度
- 触摸友好的交互

### 2.4 动画与过渡

**Framer Motion 动画**:
- 页面过渡：fade + slide
- 消息出现：scale + fade
- 卡片悬停：lift + shadow
- 加载状态：skeleton shimmer
- 进度条：smooth width transition

---

## 文件结构规划

```
frontend/src/
├── app/
│   ├── page.tsx                 # Landing Page (重构)
│   ├── layout.tsx               # 根布局
│   ├── globals.css              # 全局样式 + Design System
│   ├── chat/
│   │   └── [id]/
│   │       └── page.tsx         # 聊天页面
│   └── specta-chat/
│       └── page.tsx             # 现有聊天页面
├── components/
│   ├── ui/                      # 基础UI组件
│   │   ├── button.tsx
│   │   ├── card.tsx
│   │   ├── input.tsx
│   │   ├── badge.tsx
│   │   ├── tooltip.tsx
│   │   ├── progress.tsx
│   │   └── skeleton.tsx
│   ├── landing/                 # Landing Page 组件
│   │   ├── hero.tsx
│   │   ├── features.tsx
│   │   ├── how-it-works.tsx
│   │   ├── use-cases.tsx
│   │   ├── cta-section.tsx
│   │   └── footer.tsx
│   ├── chat/                    # 聊天组件
│   │   ├── specta-chat.tsx      # (重构)
│   │   ├── message-list.tsx
│   │   ├── process-timeline.tsx # (新增)
│   │   └── input-area.tsx
│   ├── charts/                  # 图表组件
│   │   ├── radar-chart.tsx
│   │   ├── line-chart.tsx
│   │   ├── bar-chart.tsx
│   │   ├── pie-chart.tsx
│   │   └── metric-card.tsx
│   └── report/                  # 报告组件
│       ├── report-dashboard.tsx
│       ├── summary-cards.tsx
│       ├── swot-analysis.tsx
│       └── recommendations.tsx
├── hooks/                       # 自定义Hooks
│   ├── use-chat.ts
│   ├── use-theme.ts
│   └── use-media-query.ts
├── lib/                         # 工具函数
│   ├── utils.ts
│   └── constants.ts
└── types/                       # 类型定义
    └── index.ts
```

---

## 实施计划

### Week 1: Landing Page + Design System
- Day 1-2: Design System (colors, typography, spacing)
- Day 3-4: Landing Page Hero + Features
- Day 5-6: Landing Page How It Works + Use Cases
- Day 7: UI Components (Button, Card, Input)

### Week 2: Chat Interface + TPAOR Visualization
- Day 1-2: Refactor SpectaChat component
- Day 3-4: ProcessTimeline component (TPAOR可视化)
- Day 5-6: MessageList + InputArea optimization
- Day 7: Animation integration

### Week 3: Data Visualization
- Day 1-2: Chart components (Radar, Line, Bar, Pie)
- Day 3-4: ReportDashboard component
- Day 5-6: MetricCard + SummaryCards
- Day 7: Chart interactions

### Week 4: Responsive Design + Polish
- Day 1-2: Mobile responsive design
- Day 2-3: Tablet responsive design
- Day 4-5: Animation polish
- Day 6-7: Testing + Bug fixes

---

## 预期成果

1. **专业级 Landing Page** - 提升产品形象
2. **统一的 Design System** - 确保一致性
3. **可视化的 TPAOR 流程** - 提升用户体验
4. **丰富的数据图表** - 直观展示分析结果
5. **完整的响应式支持** - 适配所有设备

请确认后开始实施。