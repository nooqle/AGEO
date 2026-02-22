'use client';

import { useState, useMemo } from 'react';
import { RiArrowRightSLine, RiArrowDownSLine, RiLoader4Line, RiCheckLine } from '@remixicon/react';
import { cn } from '@/lib/cn';
import { useConversationStore } from '@/stores/conversationStore';

export interface ProgressStep {
  id: string;
  label: string;
  description?: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error' | 'skipped';
}

interface MiniProgressProps {
  steps: ProgressStep[];
  isExecuting: boolean;
  className?: string;
}

/** Estimated time per stage in seconds */
const STEP_ESTIMATES: Record<string, number> = {
  a1_brand: 15,
  a2_persona: 20,
  a3_question: 15,
  a4_fetch: 120,
  a5_analytics: 30,
};

function estimateRemaining(steps: ProgressStep[]): string | null {
  let remaining = 0;
  for (const step of steps) {
    if (step.status === 'pending' || step.status === 'in_progress') {
      const estimate = STEP_ESTIMATES[step.id] ?? 30;
      remaining += step.status === 'in_progress' ? estimate * 0.5 : estimate;
    }
  }
  if (remaining <= 0) return null;
  if (remaining < 60) return `约 ${Math.ceil(remaining)} 秒`;
  return `约 ${Math.ceil(remaining / 60)} 分钟`;
}

export function MiniProgress({ steps, isExecuting, className }: MiniProgressProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const executionProgress = useConversationStore((s) => s.executionProgress);

  const completedCount = steps.filter(s => s.status === 'completed' || s.status === 'skipped').length;
  const totalCount = steps.length;
  const isComplete = completedCount === totalCount;
  const globalProgress = executionProgress?.progress ?? (totalCount > 0 ? (completedCount / totalCount) * 100 : 0);

  const timeEstimate = useMemo(() => estimateRemaining(steps), [steps]);

  // 如果没有步骤，不显示
  if (steps.length === 0) return null;

  return (
    <div className={cn('w-full', className)}>
      {/* Global progress bar */}
      {isExecuting && (
        <div
          role="progressbar"
          aria-valuenow={Math.round(globalProgress)}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="分析进度"
          className="w-full h-1 rounded-full overflow-hidden mb-2"
          style={{ backgroundColor: 'var(--bg-tertiary)' }}
        >
          <div
            className="h-full rounded-full transition-all duration-500 ease-out"
            style={{
              width: `${Math.min(100, Math.max(2, globalProgress))}%`,
              backgroundColor: 'var(--brand-primary)',
            }}
          />
        </div>
      )}

      {/* 迷你行 - 始终显示 */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className={cn(
          'w-full flex items-center justify-between px-3 py-2 rounded-lg',
          'bg-[--bg-secondary] border border-[--border-default]',
          'hover:border-[--border-hover] transition-all duration-200',
          'text-xs'
        )}
      >
        <div className="flex items-center gap-2">
          {isExecuting ? (
            <RiLoader4Line className="w-3.5 h-3.5 text-[--warning] animate-spin" />
          ) : isComplete ? (
            <RiCheckLine className="w-3.5 h-3.5 text-[--success]" />
          ) : (
            <div className="w-3.5 h-3.5 rounded-full border-2 border-[--text-disabled]" />
          )}
          <span className={cn(
            'font-medium',
            isExecuting ? 'text-[--warning]' : isComplete ? 'text-[--success]' : 'text-[--text-tertiary]'
          )}>
            {isExecuting ? '正在分析...' : isComplete ? '分析完成' : '等待中...'}
          </span>
          <span className="text-[--text-disabled]">
            · {completedCount}/{totalCount}
          </span>
          {isExecuting && timeEstimate && (
            <span className="text-[--text-disabled] ml-1">
              ({timeEstimate})
            </span>
          )}
        </div>
        {isExpanded ? (
          <RiArrowDownSLine className="w-4 h-4 text-[--text-tertiary]" />
        ) : (
          <RiArrowRightSLine className="w-4 h-4 text-[--text-tertiary]" />
        )}
      </button>

      {/* 展开详情 */}
      {isExpanded && (
        <div className="mt-2 space-y-1">
          {steps.map((step) => (
            <div
              key={step.id}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-md',
                'text-xs',
                step.status === 'in_progress' && 'bg-[--bg-tertiary]'
              )}
            >
              {/* 状态图标 */}
              <div className="w-4 flex justify-center">
                {step.status === 'completed' && (
                  <RiCheckLine className="w-3.5 h-3.5 text-[--success]" />
                )}
                {step.status === 'in_progress' && (
                  <RiLoader4Line className="w-3.5 h-3.5 text-[--warning] animate-spin" />
                )}
                {step.status === 'pending' && (
                  <div className="w-2.5 h-2.5 rounded-full border border-[--text-disabled]" />
                )}
                {step.status === 'error' && (
                  <div className="w-3.5 h-3.5 rounded-full bg-[--error] flex items-center justify-center">
                    <span className="text-[8px] text-white">!</span>
                  </div>
                )}
                {step.status === 'skipped' && (
                  <span className="text-[10px] text-[--text-disabled]">—</span>
                )}
              </div>

              {/* 步骤标签 */}
              <span className={cn(
                'flex-1',
                step.status === 'completed' && 'text-[--text-secondary]',
                step.status === 'in_progress' && 'text-[--text-primary]',
                step.status === 'pending' && 'text-[--text-disabled]',
                step.status === 'error' && 'text-[--error]',
                step.status === 'skipped' && 'text-[--text-disabled] line-through',
              )}>
                {step.label}
              </span>

              {/* 状态标签 */}
              <span className={cn(
                'text-[10px]',
                step.status === 'completed' && 'text-[--success]',
                step.status === 'in_progress' && 'text-[--warning]',
                step.status === 'pending' && 'text-[--text-disabled]',
                step.status === 'error' && 'text-[--error]',
                step.status === 'skipped' && 'text-[--text-disabled]',
              )}>
                {step.status === 'completed' && '完成'}
                {step.status === 'in_progress' && '进行中'}
                {step.status === 'pending' && '等待'}
                {step.status === 'error' && '错误'}
                {step.status === 'skipped' && '跳过'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default MiniProgress;
