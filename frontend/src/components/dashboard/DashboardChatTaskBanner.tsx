'use client';

import { AlertCircle, Loader2, MessageCircle } from 'lucide-react';

import type { AnalysisTask } from '@/types/task';
import { getUserFacingStageLabel } from '@/lib/workflowStageLabels';

interface DashboardChatTaskBannerProps {
  task?: AnalysisTask | null;
  brandName?: string | null;
  isCurrentBrandTask?: boolean;
  isLoading?: boolean;
  onOpenChat: () => void;
}

function statusLabel(task: AnalysisTask): string {
  const latestRunStatus = task.latest_run?.status;
  if (latestRunStatus === 'waiting_input') return '等待确认';
  if (task.status === 'pending') return '排队中';
  if (task.status === 'running') return '运行中';
  return task.status;
}

function taskMessage(task: AnalysisTask): string {
  if (task.latest_run?.status === 'waiting_input') {
    return task.progress_message || '任务需要你回到对话确认后继续。';
  }
  const stageLabel = getUserFacingStageLabel(task.current_stage);
  const message = task.progress_message || '任务正在对话里继续执行。';
  return stageLabel ? `${stageLabel} · ${message}` : message;
}

export function DashboardChatTaskBanner({
  task,
  brandName,
  isCurrentBrandTask = true,
  isLoading,
  onOpenChat,
}: DashboardChatTaskBannerProps) {
  if (!task) return null;

  const progress = Math.max(0, Math.min(100, Math.round((task.progress || 0) * 100)));
  const waitingForInput = task.latest_run?.status === 'waiting_input';

  return (
    <section className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-7 items-center gap-2 rounded-lg bg-[var(--bg-secondary)] px-2.5 text-[12px] font-medium text-[var(--brand-primary)]">
              {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <MessageCircle className="h-3.5 w-3.5" />}
              对话任务
            </span>
            <span className="text-[12px] text-[var(--text-tertiary)]">{statusLabel(task)}</span>
            <span className="text-[12px] text-[var(--text-tertiary)]">{progress}%</span>
            {!isCurrentBrandTask ? (
              <span className="text-[12px] text-[var(--text-tertiary)]">
                {brandName ? `${brandName} 的任务` : '其他品牌任务'}
              </span>
            ) : null}
          </div>
          <div className="mt-2 flex items-start gap-2">
            {waitingForInput ? (
              <AlertCircle className="mt-1 h-4 w-4 flex-shrink-0 text-[var(--status-warning)]" />
            ) : (
              <Loader2 className="mt-1 h-4 w-4 flex-shrink-0 animate-spin text-[var(--brand-primary)]" />
            )}
            <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
              {taskMessage(task)}
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onOpenChat}
          className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3.5 text-[13px] font-medium text-[var(--text-primary)] hover:border-[var(--brand-primary)]"
        >
          回到对话
        </button>
      </div>
    </section>
  );
}
