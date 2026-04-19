'use client';

import { useState, useCallback } from 'react';
import {
  RiErrorWarningLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';
import type { AnalysisTask } from '@/types/task';
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
  onRetry,
  onDismiss,
  className,
}: ReconnectionBannerProps) {
  const [isDismissed, setIsDismissed] = useState(false);

  const handleDismiss = useCallback(() => {
    setIsDismissed(true);
    onDismiss?.();
  }, [onDismiss]);

  if (isDismissed) return null;

  if (task.status === 'completed') return null;

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
