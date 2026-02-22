## 修复概览

基于测试报告中的6个问题，制定完整的 Phase 1-3 修复计划，涉及4个核心文件的修改。

---

## Phase 1: 高优先级修复（立即执行）

### 1.1 修复报告面板标题重复问题
**文件**: `src/components/canvas/contents/WorkflowContent.tsx`

**问题**: 报告面板出现多个重复标题，造成视觉混乱

**修复方案**:
- 移除内部重复的"执行流程"标题（第189行）
- 通过 props 控制是否显示章节标题
- 统一使用外层传入的标题

**代码变更**:
```typescript
// 修改前 (第11-13行)
interface WorkflowContentProps {
  content: WorkflowCanvasContent;
}

// 修改后
interface WorkflowContentProps {
  content: WorkflowCanvasContent;
  showSectionTitles?: boolean; // 新增：控制是否显示章节标题
}

// 修改前 (第187-196行)
{data?.currentStep && (
  <div>
    <h4 className="text-sm font-medium text-[#E5E5E5] mb-3">执行流程</h4>
    <WorkflowVisualizerV2 ... />
  </div>
)}

// 修改后 - 条件渲染标题
{data?.currentStep && (
  <div>
    {showSectionTitles !== false && (
      <h4 className="text-sm font-medium text-[#E5E5E5] mb-3">执行流程</h4>
    )}
    <WorkflowVisualizerV2 ... />
  </div>
)}
```

---

### 1.2 优化输入框状态提示
**文件**: `src/components/chat/InputArea.tsx`

**问题**: Agent执行时提示不够明确，用户不清楚可以做什么

**修复方案**:
- 优化 placeholder 文案
- 增强底部提示区域，添加加载动画

**代码变更**:
```typescript
// 修改前 (第84-88行)
const placeholder = customPlaceholder || (isExecuting
  ? 'Agent 正在执行，请等待...'
  : pendingConfirmation
  ? '输入回复或点击上方按钮确认...'
  : '输入品牌名称开始分析，如：观夏');

// 修改后
const placeholder = customPlaceholder || (isExecuting
  ? 'Agent 正在分析品牌数据，您可查看右侧报告面板...'
  : pendingConfirmation
  ? '输入回复或点击上方按钮确认...'
  : '输入品牌名称开始分析，如：观夏');

// 修改底部提示区域 (第194-199行)
// 添加 RiLoader4Line 导入
import { RiSendPlaneLine, RiStopLine, RiAttachmentLine, RiLoader4Line } from '@remixicon/react';

// 修改提示渲染
{isExecuting ? (
  <span className="flex items-center gap-2 text-[#F59E0B]">
    <RiLoader4Line className="w-3 h-3 animate-spin" />
    Agent 正在执行分析任务...
    <span className="text-[#737373]">按</span>
    <kbd className="px-1.5 py-0.5 bg-[#262626] rounded text-[#A3A3A3]">Esc</kbd>
    <span className="text-[#737373]">可停止</span>
  </span>
) : (
  // ... 原有提示
)}
```

---

## Phase 2: 中优先级修复（本周完成）

### 2.1 优化竞品列表 - 增加筛选/折叠功能
**文件**: `src/components/canvas/contents/WorkflowContent.tsx`

**问题**: 11个竞品纵向排列，单屏无法完整查看

**修复方案**:
- 添加按竞争类型筛选功能
- 添加展开/折叠控制
- 使用 AnimatePresence 实现平滑动画

**代码变更**:
```typescript
// 修改前 (第86-119行)
function CompetitorList({ competitors }: { competitors: WorkflowCompetitor[] }) {
  return (
    <div className="space-y-2">
      {competitors.map((c, i) => (...))}
    </div>
  );
}

// 修改后
import { useState, useMemo } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

function CompetitorList({ competitors }: { competitors: WorkflowCompetitor[] }) {
  const [filterType, setFilterType] = useState<string>('all');
  const [isExpanded, setIsExpanded] = useState(true);
  
  const filteredCompetitors = useMemo(() => {
    if (filterType === 'all') return competitors;
    return competitors.filter(c => c.competition_type === filterType);
  }, [competitors, filterType]);
  
  const competitionTypes = ['all', '直接竞争', '间接竞争', '潜在竞争'];
  const typeLabels: Record<string, string> = {
    'all': '全部',
    '直接竞争': '直接',
    '间接竞争': '间接', 
    '潜在竞争': '潜在'
  };
  
  const typeCounts = useMemo(() => ({
    'all': competitors.length,
    '直接竞争': competitors.filter(c => c.competition_type === '直接竞争').length,
    '间接竞争': competitors.filter(c => c.competition_type === '间接竞争').length,
    '潜在竞争': competitors.filter(c => c.competition_type === '潜在竞争').length,
  }), [competitors]);
  
  return (
    <div className="space-y-3">
      {/* 筛选和折叠控制栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5 flex-wrap">
          {competitionTypes.map(type => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={cn(
                'px-2 py-1 rounded text-xs transition-colors',
                filterType === type 
                  ? 'bg-[#6366F1] text-white' 
                  : 'bg-[#262626] text-[#A3A3A3] hover:bg-[#333333]'
              )}
            >
              {typeLabels[type]}
              <span className="ml-1 text-[10px] opacity-70">
                ({typeCounts[type]})
              </span>
            </button>
          ))}
        </div>
        
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-[#737373] hover:text-[#A3A3A3] px-2 py-1 rounded hover:bg-[#262626] transition-colors"
        >
          {isExpanded ? '收起' : `展开 (${filteredCompetitors.length})`}
        </button>
      </div>
      
      {/* 竞品列表 */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div 
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="space-y-2 overflow-hidden"
          >
            {filteredCompetitors.map((c, i) => (
              <CompetitorItem key={i} competitor={c} index={i} />
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// 提取单个竞品项为独立组件
function CompetitorItem({ competitor: c, index }: { competitor: WorkflowCompetitor; index: number }) {
  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: index * 0.05 }}
      className="bg-[#1A1A1A] border border-[#333333] rounded-lg p-3 flex items-start gap-3 hover:border-[#404040] transition-colors"
    >
      <div className="w-8 h-8 rounded-lg bg-[#262626] flex items-center justify-center shrink-0">
        <span className="text-xs font-semibold text-[#6366F1]">
          {c.relevance_score}
        </span>
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-[#E5E5E5] font-medium">{c.name}</span>
          <span className={cn(
            'text-xs px-1.5 py-0.5 rounded',
            c.competition_type === '直接竞争' ? 'bg-red-500/10 text-red-400' :
            c.competition_type === '间接竞争' ? 'bg-yellow-500/10 text-yellow-400' :
            'bg-blue-500/10 text-blue-400'
          )}>
            {c.competition_type}
          </span>
        </div>
        {c.competitive_advantage && (
          <p className="text-xs text-[#737373] mt-1 line-clamp-2">{c.competitive_advantage}</p>
        )}
      </div>
    </motion.div>
  );
}
```

---

### 2.2 统一按钮样式
**文件**: `src/components/canvas/CanvasHeader.tsx`

**问题**: 按钮样式混用（圆角lg/xl不一致）

**修复方案**:
- 统一所有操作按钮样式
- 统一使用 `rounded-lg` 和 `p-2`

**代码变更**:
```typescript
// 在文件顶部添加统一按钮样式常量
const ACTION_BUTTON_CLASS = cn(
  'p-2 rounded-lg transition-all duration-200',
  'hover:bg-[#1A1A1A] text-[#A3A3A3] hover:text-[#E5E5E5]',
  'active:scale-95'
);

// 修改所有按钮应用统一样式
// 第128-159行 Copy button
<button onClick={handleCopy} className={ACTION_BUTTON_CLASS}>

// 第163-169行 Share button  
<button onClick={() => setShareMenuOpen(!shareMenuOpen)} className={ACTION_BUTTON_CLASS}>

// 第201-207行 Export button
<button onClick={() => setExportMenuOpen(!exportMenuOpen)} className={ACTION_BUTTON_CLASS}>

// 第248-258行 Expand/Collapse button
<button onClick={toggleMode} className={ACTION_BUTTON_CLASS}>

// 第261-267行 Close button
<button onClick={closeCanvas} className={ACTION_BUTTON_CLASS}>
```

---

## Phase 3: 低优先级优化（后续迭代）

### 3.1 优化报告面板边框样式
**文件**: `src/components/canvas/CanvasPanel.tsx`

**问题**: 边框过重，与主内容区区分不够柔和

**修复方案**:
- 使用更轻的分割线颜色
- 或添加左侧阴影效果

**代码变更**:
```typescript
// 修改前 (第67-70行)
<motion.div
  className={cn(
    'flex flex-col h-full bg-[#0D0D0D] border-l border-[#262626]',
    'w-[480px] flex-shrink-0'
  )}

// 修改后 - 选项A：更轻的分割线
<motion.div
  className={cn(
    'flex flex-col h-full bg-[#0D0D0D] border-l border-[#1A1A1A]',
    'w-[480px] flex-shrink-0'
  )}

// 或选项B：使用阴影替代边框（推荐）
<motion.div
  className={cn(
    'flex flex-col h-full bg-[#0D0D0D]',
    'w-[480px] flex-shrink-0',
    'shadow-[-4px_0_24px_rgba(0,0,0,0.4)]'
  )}
```

---

### 3.2 品牌竞品关系图谱交互增强
**文件**: `src/components/graph/BrandCompetitionGraph.tsx`（需查看现有实现）

**问题**: Canvas绘制的图谱为静态展示，无法交互

**修复方案**:
- 添加鼠标悬停tooltip显示节点详情
- 添加点击节点高亮相关连接
- 支持缩放和平移（短期）
- 长期考虑使用 ECharts 替换

**代码变更**（需要在查看 BrandCompetitionGraph.tsx 后确定）:
```typescript
// 预期修改方向：
// 1. 添加 mousemove 事件监听
// 2. 计算鼠标位置与节点距离
// 3. 显示浮动tooltip
// 4. 添加点击高亮逻辑
```

---

## 修改文件清单

| 优先级 | 文件 | 修改内容 |
|--------|------|----------|
| 🔴 P1 | `src/components/canvas/contents/WorkflowContent.tsx` | 标题重复问题 + 竞品列表筛选 |
| 🔴 P1 | `src/components/chat/InputArea.tsx` | 输入框状态提示优化 |
| 🟡 P2 | `src/components/canvas/CanvasHeader.tsx` | 统一按钮样式 |
| 🟢 P3 | `src/components/canvas/CanvasPanel.tsx` | 边框样式优化 |
| 🟢 P3 | `src/components/graph/BrandCompetitionGraph.tsx` | 图谱交互增强 |

---

## 验证清单

- [ ] 报告面板标题不再重复显示
- [ ] 输入框执行状态提示包含"查看右侧报告面板"
- [ ] 底部提示区域显示加载动画
- [ ] 竞品列表可按类型筛选
- [ ] 竞品列表支持展开/折叠
- [ ] 所有按钮样式统一（圆角、尺寸）
- [ ] 报告面板边框更柔和
- [ ] 品牌图谱支持悬停/点击交互

---

请确认此修复计划后，我将开始执行具体代码修改。