'use client';

import { useCallback } from 'react';
import { RiLoader4Line, RiCheckLine, RiAlertLine, RiIndeterminateCircleLine } from '@remixicon/react';
import { cn } from '@/lib/cn';
import { getUserFacingStageLabel, sanitizeUserFacingWorkflowText } from '@/lib/workflowStageLabels';
import type { TaskStatus } from '@/types/task';

interface TaskStatusBadgeProps {
  status: TaskStatus;
  waitingForInput?: boolean;
  currentStage?: string;
  progress?: number;
  progressMessage?: string;
  /** Lightweight follow-up operation badge text override */
  lightweightLabel?: string;
  className?: string;
  onScrollToContent?: () => void;
}

export function TaskStatusBadge({
  status,
  waitingForInput = false,
  currentStage,
  progress,
  progressMessage,
  lightweightLabel,
  className,
  onScrollToContent,
}: TaskStatusBadgeProps) {
  const handleInteraction = useCallback(() => {
    onScrollToContent?.();
  }, [onScrollToContent]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleInteraction();
      }
    },
    [handleInteraction]
  );

  const stageLabel = getUserFacingStageLabel(currentStage);
  const safeProgressMessage = sanitizeUserFacingWorkflowText(progressMessage) || '';
  const shouldShowStageLabel = Boolean(
    stageLabel && !safeProgressMessage.includes(stageLabel)
  );

  // Build aria-label for screen readers
  const getAriaLabel = (): string => {
    if (waitingForInput) {
      return safeProgressMessage || '等待用户确认';
    }

    switch (status) {
      case 'pending':
        return '准备中';
      case 'running': {
        if (lightweightLabel) return `正在处理追问`;
        const parts = ['分析进行中'];
        if (stageLabel) parts.push(`阶段 ${stageLabel}`);
        if (progress !== undefined) parts.push(`${Math.round(progress * 100)}% 完成`);
        return parts.join('，');
      }
      case 'completed':
        return '分析已完成';
      case 'failed':
        return '分析失败';
      case 'cancelled':
        return '已取消';
      default:
        return '';
    }
  };

  // Lightweight badge for drill_down / compare
  if (lightweightLabel && status === 'running') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer transition-opacity duration-200',
          className
        )}
        style={{
          background: 'var(--brand-bg)',
          color: 'var(--brand-primary)',
        }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full animate-pulse-slow"
          style={{ background: 'var(--brand-primary)' }}
        />
        {lightweightLabel}
      </div>
    );
  }

  if (waitingForInput) {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'rgba(59,130,246,0.10)',
          color: 'var(--color-primary)',
        }}
      >
        <RiIndeterminateCircleLine className="w-3 h-3" />
        {safeProgressMessage || '等待用户确认'}
      </div>
    );
  }

  if (status === 'pending') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'var(--bg-tertiary)',
          color: 'var(--text-tertiary)',
        }}
      >
        <span
          className="w-2.5 h-2.5 rounded-full"
          style={{ border: '1.5px solid var(--text-disabled)' }}
        />
        准备中...
      </div>
    );
  }

  if (status === 'running') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'rgba(245,158,11,0.1)',
          color: 'var(--warning)',
        }}
      >
        <RiLoader4Line className="w-3 h-3 animate-spin" />
        {safeProgressMessage || '正在分析...'}
        {shouldShowStageLabel && (
          <span className="font-semibold">{stageLabel}</span>
        )}
        {progress !== undefined && progress > 0 && (
          <span style={{ color: 'var(--text-tertiary)' }}>
            {Math.round(progress * 100)}%
          </span>
        )}
        {progress !== undefined && progress > 0 && (
          <div className="relative w-12 h-1 rounded-full overflow-hidden" style={{ background: 'rgba(245,158,11,0.15)' }}>
            <div
              className="absolute left-0 top-0 h-full rounded-full transition-all duration-700 ease-out"
              style={{
                width: `${Math.round(progress * 100)}%`,
                background: 'var(--warning)',
              }}
            />
          </div>
        )}
      </div>
    );
  }

  if (status === 'completed') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'rgba(34,197,94,0.1)',
          color: 'var(--success)',
        }}
      >
        <RiCheckLine className="w-3 h-3" />
        分析完成
      </div>
    );
  }

  if (status === 'failed') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'rgba(239,68,68,0.1)',
          color: 'var(--error)',
        }}
      >
        <RiAlertLine className="w-3 h-3" />
        分析失败
      </div>
    );
  }

  if (status === 'cancelled') {
    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={getAriaLabel()}
        tabIndex={0}
        onClick={handleInteraction}
        onKeyDown={handleKeyDown}
        className={cn(
          'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap cursor-pointer',
          className
        )}
        style={{
          background: 'var(--bg-tertiary)',
          color: 'var(--text-muted)',
        }}
      >
        <RiIndeterminateCircleLine className="w-3 h-3" />
        已取消
      </div>
    );
  }

  return null;
}

export default TaskStatusBadge;
