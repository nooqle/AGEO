'use client';

import { motion, AnimatePresence } from 'framer-motion';
import { useCanvasStore } from '@/stores/canvasStore';
import { useConversationStore } from '@/stores/conversationStore';
import { CanvasHeader } from './CanvasHeader';
import { CanvasTabs } from './CanvasTabs';
import { ReportContent } from './contents/ReportContent';
import { ChartContent } from './contents/ChartContent';
import { DataTableContent } from './contents/DataTableContent';
import { PipelineContent } from './contents/PipelineContent';
import { WorkflowContent } from './contents/WorkflowContent';
import { QuestionListContent } from './contents/QuestionListContent';
import { FetchResultsContent } from './contents/FetchResultsContent';
import { BrowserTakeoverContent } from './contents/BrowserTakeoverContent';
import { cn } from '@/lib/cn';
import { RiLayoutRightLine, RiFileTextLine, RiLoader4Line } from '@remixicon/react';

export function CanvasPanel() {
  const {
    contents,
    browserWorkspace,
    activeContentIndex,
    activeSurface,
    isOpen,
  } = useCanvasStore();
  const isAgentExecuting = useConversationStore((s) => s.isAgentExecuting);
  const hasArtifacts = contents.length > 0;
  const hasBrowserWorkspace = Boolean(browserWorkspace);

  if (!isOpen) {
    return null;
  }

  if (!hasArtifacts && !hasBrowserWorkspace) {
    return (
      <div className="flex flex-col h-full shadow-[-2px_0_16px_rgba(0,0,0,0.08)]" style={{ backgroundColor: 'var(--bg-primary)' }}>
        {/* 空状态 / 分析中间态 */}
        <div className="flex-1 flex flex-col items-center justify-center p-8 text-center">
          {isAgentExecuting ? (
            <>
              <div className="w-16 h-16 rounded-2xl bg-[var(--bg-secondary)] border border-[var(--border-subtle)] flex items-center justify-center mb-4">
                <RiLoader4Line className="w-8 h-8 text-[#F59E0B] animate-spin" />
              </div>
              <h3 className="text-lg font-medium text-[var(--text-secondary)] mb-2">
                分析进行中
              </h3>
              <p className="text-sm text-[var(--text-tertiary)] max-w-[280px]">
                报告即将生成，请稍候...
              </p>
            </>
          ) : (
            <>
              <div className="w-16 h-16 rounded-2xl bg-[var(--bg-secondary)] border border-[var(--border-subtle)] flex items-center justify-center mb-4">
                <RiFileTextLine className="w-8 h-8 text-[var(--text-disabled)]" />
              </div>
              <h3 className="text-lg font-medium text-[var(--text-secondary)] mb-2">
                暂无分析报告
              </h3>
              <p className="text-sm text-[var(--text-tertiary)] max-w-[280px]">
                开始发起分析，完成后可在此处查看详细报告
              </p>
            </>
          )}
        </div>
      </div>
    );
  }

  const rawContent =
    activeSurface === 'browser' && browserWorkspace
      ? browserWorkspace
      : contents[activeContentIndex] ?? browserWorkspace ?? null;

  // When viewing a historical version, overlay the version's data
  const activeContent = (() => {
    if (!rawContent) return rawContent;
    const vIdx = rawContent.currentVersionIndex;
    const versions = rawContent.versions || [];
    if (vIdx >= 0 && vIdx < versions.length) {
      return { ...rawContent, data: versions[vIdx].data } as typeof rawContent;
    }
    return rawContent;
  })();

  const renderContent = () => {
    if (!activeContent) return null;

    switch (activeContent.type) {
      case 'report':
        return <ReportContent content={activeContent} />;
      case 'chart':
        return <ChartContent content={activeContent} />;
      case 'dataTable':
        return <DataTableContent content={activeContent} />;
      case 'pipeline':
        return <PipelineContent content={activeContent} />;
      case 'workflow':
        return <WorkflowContent content={activeContent} />;
      case 'questionList':
        return <QuestionListContent content={activeContent} />;
      case 'fetchResults':
        return <FetchResultsContent content={activeContent} />;
      case 'browser':
        return <BrowserTakeoverContent content={activeContent} />;
      default:
        return null;
    }
  };

  return (
    <motion.div
      className={cn(
        'flex flex-col h-full',
        'shadow-[-2px_0_16px_rgba(0,0,0,0.08)]'
      )}
      data-canvas-export-root="true"
      data-canvas-export-id={rawContent?.id || ''}
      style={{ backgroundColor: 'var(--bg-primary)' }}
      initial={{ x: 100, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      exit={{ x: 100, opacity: 0 }}
      transition={{ duration: 0.3, ease: [0.4, 0, 0.2, 1] }}
    >
      {/* 顶部栏 — pass raw content so version selector has access to versions[] */}
      <CanvasHeader content={rawContent} />

      {/* Tab 栏（多内容时显示） */}
      {activeContent?.type !== 'browser' && contents.length > 1 && <CanvasTabs />}

      {/* 内容区 */}
      {/* pipeline 类型：不在此层滚动，让 PipelineContent 自控滚动与固定底栏 */}
      {/* 其他类型：在此层滚动（原有行为不变） */}
      <div
        className={cn(
          'flex-1 overflow-x-hidden',
          activeContent?.type === 'pipeline' || activeContent?.type === 'browser'
            ? 'overflow-hidden'
            : 'overflow-y-auto'
        )}
        data-canvas-export-scroll="true"
      >
        <AnimatePresence mode="wait">
          <motion.div
            key={`${activeContent?.id || 'empty'}_v${rawContent?.currentVersionIndex ?? -1}`}
            className={cn(
              activeContent?.type === 'pipeline' || activeContent?.type === 'browser'
                ? 'h-full'
                : ''
            )}
            data-canvas-export-body="true"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2 }}
          >
            {renderContent()}
          </motion.div>
        </AnimatePresence>
      </div>
    </motion.div>
  );
}

// 可折叠的 Canvas 触发按钮
interface CanvasToggleProps {
  onClick?: () => void;
  hasContent?: boolean;
}

export function CanvasToggle({ onClick, hasContent = false }: CanvasToggleProps) {
  const { isOpen, openCanvas } = useCanvasStore();

  const handleClick = () => {
    if (onClick) {
      onClick();
    } else if (!isOpen) {
      openCanvas();
    }
  };

  return (
    <motion.button
      onClick={handleClick}
      className={cn(
        'fixed right-4 top-1/2 -translate-y-1/2 z-40',
        'w-10 h-10 rounded-full flex items-center justify-center',
        'bg-[var(--bg-secondary)] border border-[var(--border-subtle)] shadow-lg',
        'hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-hover)] transition-all duration-200',
        hasContent && 'ring-2 ring-[#6366F1] ring-offset-2 ring-offset-[var(--bg-primary)]'
      )}
      initial={{ x: 20, opacity: 0 }}
      animate={{ x: 0, opacity: 1 }}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      title="打开分析报告"
    >
      <RiLayoutRightLine className="w-5 h-5 text-[var(--text-secondary)]" />
      {hasContent && (
        <span className="absolute -top-1 -right-1 w-3 h-3 bg-[#6366F1] rounded-full" />
      )}
    </motion.button>
  );
}

export default CanvasPanel;
