# 任务：实现前端 Canvas 区组件

## 背景
实现 Canvas 区的所有组件，包括报告展示、图表交互、数据表、选择确认界面、移动端适配等。

## 参考文档
- `Mittus AEO平台 - 前端交互设计文档 v2.md` 第四节「Canvas 区域设计」

## 组件结构
```
frontend/src/components/canvas/
├── CanvasPanel.tsx            # Canvas 面板容器
├── CanvasHeader.tsx           # 顶部栏（标题、Tab、操作）
├── CanvasTabs.tsx             # 内容切换 Tab
├── contents/
│   ├── ReportContent.tsx      # 报告类型
│   ├── ChartContent.tsx       # 图表类型（可交互）
│   ├── DataTableContent.tsx   # 数据表类型
│   └── SelectionContent.tsx   # 选择确认类型（画像选择）
├── CanvasActions.tsx          # 底部操作栏
└── MobileCanvasSheet.tsx      # 移动端全屏弹出层
```

## 核心组件实现

### 1. CanvasPanel.tsx
```tsx
// frontend/src/components/canvas/CanvasPanel.tsx
'use client';

import { useCanvasStore } from '@/stores/canvasStore';
import { CanvasHeader } from './CanvasHeader';
import { CanvasTabs } from './CanvasTabs';
import { ReportContent } from './contents/ReportContent';
import { ChartContent } from './contents/ChartContent';
import { DataTableContent } from './contents/DataTableContent';
import { SelectionContent } from './contents/SelectionContent';
import { CanvasActions } from './CanvasActions';

export function CanvasPanel() {
  const { contents, activeContentIndex, isOpen } = useCanvasStore();
  
  if (!isOpen || contents.length === 0) return null;
  
  const activeContent = contents[activeContentIndex];
  
  const renderContent = () => {
    if (!activeContent) return null;
    
    switch (activeContent.type) {
      case 'report':
        return <ReportContent content={activeContent} />;
      case 'chart':
        return <ChartContent content={activeContent} />;
      case 'dataTable':
        return <DataTableContent content={activeContent} />;
      case 'selection':
        return <SelectionContent content={activeContent} />;
      default:
        return null;
    }
  };
  
  return (
    <div className="flex flex-col h-full bg-white">
      {/* 顶部栏 */}
      <CanvasHeader content={activeContent} />
      
      {/* Tab 栏（多内容时显示） */}
      {contents.length > 1 && <CanvasTabs />}
      
      {/* 内容区 */}
      <div className="flex-1 overflow-y-auto">
        {renderContent()}
      </div>
      
      {/* 操作栏（选择类型显示） */}
      {activeContent?.type === 'selection' && (
        <CanvasActions content={activeContent} />
      )}
    </div>
  );
}
```

### 2. CanvasHeader.tsx
```tsx
// frontend/src/components/canvas/CanvasHeader.tsx
'use client';

import { Download, Maximize2, Minimize2, X } from 'lucide-react';
import { CanvasContent } from '@/types/canvas';
import { useCanvasStore } from '@/stores/canvasStore';
import { api } from '@/services/api';

interface CanvasHeaderProps {
  content: CanvasContent;
}

export function CanvasHeader({ content }: CanvasHeaderProps) {
  const { mode, setMode, closeCanvas } = useCanvasStore();
  
  const handleExport = async (format: 'pdf' | 'excel') => {
    try {
      const blob = await api.exportOutput('session-id', content.id, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${content.title}.${format === 'pdf' ? 'pdf' : 'xlsx'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Export failed:', error);
    }
  };
  
  const toggleMode = () => {
    setMode(mode === 'split' ? 'focused' : 'split');
  };
  
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b">
      {/* 标题 */}
      <h2 className="font-semibold text-gray-900 truncate">
        {content.title}
      </h2>
      
      {/* 操作按钮 */}
      <div className="flex items-center gap-1">
        {/* 导出按钮 */}
        {(content.type === 'report' || content.type === 'dataTable') && (
          <div className="relative group">
            <button className="p-2 hover:bg-gray-100 rounded-lg transition-colors">
              <Download className="w-4 h-4 text-gray-600" />
            </button>
            <div className="absolute right-0 top-full mt-1 bg-white border rounded-lg shadow-lg py-1 hidden group-hover:block z-10">
              <button
                className="w-full px-4 py-2 text-sm text-left hover:bg-gray-50"
                onClick={() => handleExport('pdf')}
              >
                导出 PDF
              </button>
              <button
                className="w-full px-4 py-2 text-sm text-left hover:bg-gray-50"
                onClick={() => handleExport('excel')}
              >
                导出 Excel
              </button>
            </div>
          </div>
        )}
        
        {/* 展开/收起按钮 */}
        <button
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          onClick={toggleMode}
          title={mode === 'split' ? '展开' : '收起'}
        >
          {mode === 'split' ? (
            <Maximize2 className="w-4 h-4 text-gray-600" />
          ) : (
            <Minimize2 className="w-4 h-4 text-gray-600" />
          )}
        </button>
        
        {/* 关闭按钮 */}
        <button
          className="p-2 hover:bg-gray-100 rounded-lg transition-colors"
          onClick={closeCanvas}
          title="关闭"
        >
          <X className="w-4 h-4 text-gray-600" />
        </button>
      </div>
    </div>
  );
}
```

### 3. SelectionContent.tsx
```tsx
// frontend/src/components/canvas/contents/SelectionContent.tsx
'use client';

import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import { Star, Check } from 'lucide-react';
import { CanvasContent } from '@/types/canvas';
import { useConversationStore } from '@/stores/conversationStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { selectionCardVariants } from '@/lib/animations';
import { cn, getCircledNumber } from '@/lib/utils';

interface SelectionContentProps {
  content: CanvasContent;
}

interface PersonaItem {
  id: string;
  name: string;
  emoji: string;
  description: string;
  ageRange: string;
  characteristics: string[];
  recommendationScore: number;
  relatedWeakness?: string;
  recommendationReason?: string;
}

export function SelectionContent({ content }: SelectionContentProps) {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const { pendingConfirmation } = useConversationStore();
  const { sendConfirmation } = useWebSocket('session-id'); // TODO: 从 context 获取
  
  const personas: PersonaItem[] = content.data.personas || [];
  const maxSelection = content.data.maxSelection || 3;
  const minSelection = content.data.minSelection || 1;
  
  // 切换选择
  const toggleSelection = (id: string) => {
    const newSelected = new Set(selectedIds);
    if (newSelected.has(id)) {
      newSelected.delete(id);
    } else if (newSelected.size < maxSelection) {
      newSelected.add(id);
    }
    setSelectedIds(newSelected);
  };
  
  // 确认选择
  const handleConfirm = () => {
    if (!pendingConfirmation || selectedIds.size < minSelection) return;
    
    const selectedPersonas = personas.filter((p) => selectedIds.has(p.id));
    sendConfirmation(pendingConfirmation.requestId, {
      type: 'persona_selection',
      selectedIds: Array.from(selectedIds),
      selectedLabels: selectedPersonas.map((p) => p.name),
    });
  };
  
  // 跳过
  const handleSkip = () => {
    if (!pendingConfirmation) return;
    sendConfirmation(pendingConfirmation.requestId, {
      type: 'skip',
    });
  };
  
  return (
    <div className="p-4">
      {/* 说明文字 */}
      {content.data.description && (
        <p className="text-sm text-gray-600 mb-4">
          {content.data.description}
        </p>
      )}
      
      {/* 画像列表 */}
      <div className="space-y-3">
        {personas.map((persona, index) => (
          <motion.button
            key={persona.id}
            className={cn(
              'w-full text-left p-4 rounded-lg border-2 transition-colors',
              selectedIds.has(persona.id)
                ? 'border-indigo-500 bg-indigo-50'
                : 'border-gray-200 bg-white hover:border-gray-300'
            )}
            variants={selectionCardVariants}
            initial="unselected"
            animate={selectedIds.has(persona.id) ? 'selected' : 'unselected'}
            onClick={() => toggleSelection(persona.id)}
          >
            <div className="flex items-start gap-3">
              {/* 选择框 */}
              <div className={cn(
                'w-6 h-6 rounded-full border-2 flex items-center justify-center flex-shrink-0 mt-0.5',
                selectedIds.has(persona.id)
                  ? 'border-indigo-500 bg-indigo-500'
                  : 'border-gray-300'
              )}>
                {selectedIds.has(persona.id) && (
                  <Check className="w-4 h-4 text-white" />
                )}
              </div>
              
              {/* 内容 */}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg">{persona.emoji}</span>
                  <span className="font-medium text-gray-900">
                    {getCircledNumber(index + 1)} {persona.name}
                  </span>
                  
                  {/* 推荐星级 */}
                  <div className="flex items-center gap-0.5 ml-auto">
                    {Array.from({ length: 5 }).map((_, i) => (
                      <Star
                        key={i}
                        className={cn(
                          'w-3 h-3',
                          i < persona.recommendationScore
                            ? 'text-amber-400 fill-amber-400'
                            : 'text-gray-300'
                        )}
                      />
                    ))}
                  </div>
                </div>
                
                <p className="text-sm text-gray-500 mb-2">
                  {persona.ageRange} | {persona.description}
                </p>
                
                {/* 关联薄弱点 */}
                {persona.relatedWeakness && (
                  <div className="text-xs text-amber-600 bg-amber-50 px-2 py-1 rounded inline-block">
                    关联薄弱点：{persona.relatedWeakness} ⚠️
                  </div>
                )}
                
                {/* 推荐理由 */}
                {persona.recommendationReason && (
                  <p className="text-xs text-gray-500 mt-2">
                    💡 {persona.recommendationReason}
                  </p>
                )}
              </div>
            </div>
          </motion.button>
        ))}
      </div>
      
      {/* 已选统计 */}
      <div className="mt-4 text-sm text-gray-600">
        已选择：{selectedIds.size} 个画像
        {content.data.estimatedTime && (
          <span className="ml-2">
            | 预计额外耗时：{content.data.estimatedTime}
          </span>
        )}
      </div>
    </div>
  );
}
```

### 4. MobileCanvasSheet.tsx
```tsx
// frontend/src/components/canvas/MobileCanvasSheet.tsx
'use client';

import { ReactNode } from 'react';
import { motion, AnimatePresence, PanInfo } from 'framer-motion';
import { useCanvasStore } from '@/stores/canvasStore';
import { mobileCanvasVariants, overlayVariants } from '@/lib/animations';

interface MobileCanvasSheetProps {
  isOpen: boolean;
  children: ReactNode;
}

export function MobileCanvasSheet({ isOpen, children }: MobileCanvasSheetProps) {
  const { closeCanvas } = useCanvasStore();
  
  // 下拉关闭手势
  const handleDragEnd = (event: MouseEvent | TouchEvent | PointerEvent, info: PanInfo) => {
    if (info.offset.y > 100 || info.velocity.y > 500) {
      closeCanvas();
    }
  };
  
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* 遮罩层 */}
          <motion.div
            className="fixed inset-0 bg-black/50 z-40"
            variants={overlayVariants}
            initial="hidden"
            animate="visible"
            exit="exit"
            onClick={closeCanvas}
          />
          
          {/* Canvas 面板 */}
          <motion.div
            className="fixed inset-x-0 bottom-0 top-16 bg-white rounded-t-2xl z-50 flex flex-col"
            variants={mobileCanvasVariants}
            initial="hidden"
            animate="visible"
            exit="hidden"
            drag="y"
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0, bottom: 0.5 }}
            onDragEnd={handleDragEnd}
          >
            {/* 拖拽把手 */}
            <div className="flex justify-center py-3">
              <div className="w-10 h-1 bg-gray-300 rounded-full" />
            </div>
            
            {/* 内容 */}
            <div className="flex-1 overflow-hidden">
              {children}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
```

### 5. CanvasActions.tsx
```tsx
// frontend/src/components/canvas/CanvasActions.tsx
'use client';

import { CanvasContent } from '@/types/canvas';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import { useWebSocket } from '@/hooks/useWebSocket';

interface CanvasActionsProps {
  content: CanvasContent;
}

export function CanvasActions({ content }: CanvasActionsProps) {
  const { pendingConfirmation } = useConversationStore();
  const { sendConfirmation } = useWebSocket('session-id');
  
  // 仅选择类型显示操作栏
  if (content.type !== 'selection' || !pendingConfirmation) {
    return null;
  }
  
  const handleConfirm = () => {
    // 确认逻辑由 SelectionContent 处理
  };
  
  const handleSkip = () => {
    sendConfirmation(pendingConfirmation.requestId, { type: 'skip' });
  };
  
  return (
    <div className="border-t bg-white px-4 py-3">
      <div className="flex gap-3">
        <button
          className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
          onClick={handleConfirm}
        >
          确认选择 ✓
        </button>
        <button
          className="flex-1 py-2.5 rounded-lg text-sm font-medium bg-white border border-gray-300 text-gray-700 hover:bg-gray-50 transition-colors"
          onClick={handleSkip}
        >
          跳过此步 →
        </button>
      </div>
    </div>
  );
}
```

## 预期产出

1. `frontend/src/components/canvas/CanvasPanel.tsx`
2. `frontend/src/components/canvas/CanvasHeader.tsx`
3. `frontend/src/components/canvas/CanvasTabs.tsx`
4. `frontend/src/components/canvas/contents/ReportContent.tsx`
5. `frontend/src/components/canvas/contents/ChartContent.tsx`
6. `frontend/src/components/canvas/contents/DataTableContent.tsx`
7. `frontend/src/components/canvas/contents/SelectionContent.tsx`
8. `frontend/src/components/canvas/CanvasActions.tsx`
9. `frontend/src/components/canvas/MobileCanvasSheet.tsx`