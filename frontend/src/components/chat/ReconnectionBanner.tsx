'use client';

import { useState, useCallback, useEffect } from 'react';
import {
  RiCheckboxCircleLine,
  RiErrorWarningLine,
  RiCloseLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';
import type { AnalysisTask } from '@/types/task';
import { formatTime } from '@/lib/utils';
import { getUserFacingStageLabel } from '@/lib/workflowStageLabels';

interface ReconnectionBannerProps {
  task: AnalysisTask;
  /** Callback when user clicks "View Report" */
  onViewReport?: () => void;
  /** Callback when user clicks "Retry" on failed task */
  onRetry?: () => void;
  /** Callback when banner is dismissed */
  onDismiss?: () => void;
  className?: string;
}

export function ReconnectionBanner({
  task,
  onViewReport,
  onRetry,
  onDismiss,
  className,
}: ReconnectionBannerProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  const [isFadingOut, setIsFadingOut] = useState(false);

  const handleDismiss = useCallback(() => {
    setIsDismissed(true);
    onDismiss?.();
  }, [onDismiss]);

  // Auto-dismiss completed banner after 8 seconds with fade-out
  useEffect(() => {
    if (task.status !== 'completed' || isDismissed) return;
    const fadeTimer = setTimeout(() => setIsFadingOut(true), 7000);
    const dismissTimer = setTimeout(() => {
      setIsDismissed(true);
      onDismiss?.();
    }, 8000);
    return () => {
      clearTimeout(fadeTimer);
      clearTimeout(dismissTimer);
    };
  }, [task.status, isDismissed, onDismiss]);

  if (isDismissed) return null;

  // Scenario B: Task COMPLETED while user was away
  if (task.status === 'completed') {
    const completedTime = task.completed_at ? formatTime(task.completed_at) : '';

    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={`品牌 ${task.brand_name} 分析已完成${completedTime ? `，完成时间 ${completedTime}` : ''}，可查看报告或关闭此通知`}
        className={cn(
          'relative rounded-[10px] mx-4 my-2 p-3 animate-slide-up transition-opacity duration-1000',
          isFadingOut && 'opacity-0',
          className
        )}
        style={{
          background: 'rgba(34,197,94,0.06)',
          border: '1px solid rgba(34,197,94,0.2)',
        }}
      >
        {/* Close button */}
        <button
          onClick={handleDismiss}
          className="absolute top-2 right-2 p-0.5 rounded hover:bg-white/5 transition-colors"
          aria-label={`关闭${task.brand_name}分析完成通知`}
        >
          <RiCloseLine className="w-3.5 h-3.5" style={{ color: 'var(--text-tertiary)' }} />
        </button>

        <div className="flex items-center gap-2">
          <RiCheckboxCircleLine className="w-[18px] h-[18px] flex-shrink-0" style={{ color: 'var(--success)' }} />
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
              &ldquo;{task.brand_name}&rdquo; 分析已完成
              {completedTime && (
                <span className="ml-1 font-normal" style={{ color: 'var(--text-secondary)' }}>
                  ({completedTime})
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 mt-1">
              {task.snapshot_id && (
                <button
                  onClick={onViewReport}
                  className="text-xs font-medium hover:underline cursor-pointer"
                  style={{ color: 'var(--brand-primary)' }}
                  aria-label={`查看 ${task.brand_name} 的分析报告`}
                >
                  查看报告 &rarr;
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Scenario C: Task FAILED while user was away
  if (task.status === 'failed') {
    const errorStageLabel = getUserFacingStageLabel(task.error_stage);
    return (
      <div
        role="alert"
        aria-live="assertive"
        aria-label={`品牌 ${task.brand_name} 分析失败${errorStageLabel ? `，失败环节 ${errorStageLabel}` : ''}，可重新分析或关闭`}
        className={cn(
          'relative rounded-[10px] mx-4 my-2 p-3 animate-slide-up',
          className
        )}
        style={{
          background: 'rgba(239,68,68,0.06)',
          border: '1px solid rgba(239,68,68,0.2)',
        }}
      >
        <div className="flex items-start gap-2">
          <RiErrorWarningLine className="w-[18px] h-[18px] flex-shrink-0 mt-0.5" style={{ color: 'var(--error)' }} />
          <div className="flex-1 min-w-0">
            <div className="text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
              &ldquo;{task.brand_name}&rdquo; 分析失败
              {errorStageLabel && (
                <span className="font-normal" style={{ color: 'var(--text-secondary)' }}>
                  {' '}({errorStageLabel})
                </span>
              )}
            </div>
            {task.error_message && (
              <div className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                {task.error_message}
              </div>
            )}
            <div className="flex items-center gap-2 mt-2">
              <button
                onClick={onRetry}
                className="px-3.5 py-1.5 rounded-md text-xs font-medium text-white cursor-pointer transition-colors"
                style={{ background: 'var(--brand-primary)' }}
                aria-label={`重新分析 ${task.brand_name}`}
              >
                重新分析
              </button>
              <button
                onClick={handleDismiss}
                className="px-3.5 py-1.5 text-xs cursor-pointer transition-colors"
                style={{ color: 'var(--text-secondary)' }}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // For running / pending tasks, no reconnection banner is shown
  // (TaskStatusBadge handles the running state in the header)
  return null;
}

export default ReconnectionBanner;
