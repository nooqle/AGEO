'use client';

import { cn } from '@/lib/cn';
import type { AnalysisTask } from '@/types/task';
import {
  getUserFacingStageLabel,
  sanitizeUserFacingErrorMessage,
} from '@/lib/workflowStageLabels';

interface ReconnectionBannerProps {
  task: AnalysisTask;
  className?: string;
}

export function ReconnectionBanner({
  task,
  className,
}: ReconnectionBannerProps) {
  if (task.status === 'completed') return null;

  if (task.status === 'failed') {
    const errorStageLabel = getUserFacingStageLabel(task.error_stage);
    const isScheduledTask =
      task.latest_run?.run_kind === 'scheduled' ||
      task.latest_run?.trigger_source === 'scheduler' ||
      task.error_stage === 'sched_snap';
    const fallbackMessage = isScheduledTask
      ? '本次自动监测已结束，但没有生成可用于看板展示的报告。'
      : '本次分析没有生成可用于展示的结果。';
    const detail = sanitizeUserFacingErrorMessage(task.error_message, fallbackMessage);
    const title = isScheduledTask
      ? `“${task.brand_name}”本次自动监测未完成`
      : `“${task.brand_name}”本次分析未完成`;

    return (
      <div
        role="status"
        aria-live="polite"
        aria-label={title}
        className={cn(
          'mx-4 my-2 rounded-2xl border px-4 py-4 animate-slide-up',
          className
        )}
        style={{
          background: 'rgba(245, 158, 11, 0.08)',
          borderColor: 'rgba(245, 158, 11, 0.18)',
        }}
      >
        <div className="flex items-start gap-3">
          <div
            className="mt-1 h-2.5 w-2.5 rounded-full"
            style={{ background: 'var(--warning)' }}
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {title}
              </p>
              <span
                className="rounded-full bg-[var(--bg-secondary)] px-2 py-0.5 text-[11px]"
                style={{ color: 'var(--text-secondary)' }}
              >
                需要处理
              </span>
            </div>

            {detail && (
              <p className="mt-1 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                {detail}
              </p>
            )}
            {errorStageLabel && (
              <p className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
                处理环节：{errorStageLabel}
              </p>
            )}
            <p className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
              这是一条状态提示，不需要在这里确认。需要重新复测时，直接在下方输入你的要求。
            </p>
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
