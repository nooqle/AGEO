'use client';

import { AlertCircle, CheckCircle2, Loader2, Play, RefreshCw, X } from 'lucide-react';

import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import { isActiveBrandIntelligenceRun } from '@/types/intelligenceRun';

interface BrandIntelligenceRunBannerProps {
  run?: BrandIntelligenceRun | null;
  isLoading?: boolean;
  isSubmitting?: boolean;
  error?: string | null;
  onStart: () => void;
  onResume: () => void;
  onCancel: () => void;
  onOpenChat: () => void;
}

const STATUS_LABELS: Partial<Record<BrandIntelligenceRun['status'], string>> = {
  not_started: '待开始',
  planning_questions: '正在生成问题',
  waiting_scope_confirmation: '等待确认范围',
  fetching_answers: '正在采集回答',
  waiting_takeover: '等待接管',
  analyzing_metrics: '正在计算指标',
  building_world: '正在整理证据',
  generating_recommendations: '正在生成建议',
  waiting_user: '等待确认',
  completed: '已完成',
  failed: '失败',
  cancelled: '已取消',
};

function progressLabel(run?: BrandIntelligenceRun | null): string {
  if (!run) return '尚未开始';
  const value = Math.max(0, Math.min(100, Math.round((run.progress || 0) * 100)));
  if (run.status === 'completed') return '100%';
  if (run.status === 'failed' || run.status === 'cancelled') return STATUS_LABELS[run.status] || '';
  return `${value}%`;
}

function runMessage(run?: BrandIntelligenceRun | null): string {
  if (!run) return '开始后，系统会在后台生成问题、采集回答并沉淀情报。';
  if (run.requires_user_action) {
    return run.blocking_reason || '需要确认后继续。';
  }
  if (run.status === 'completed') return '可以查看简要情报、情报来源和品牌世界。';
  if (run.status === 'failed') return run.error_message || '任务失败，可以重试或进入对话说明情况。';
  if (run.status === 'cancelled') return '任务已取消。';
  return run.message || '任务进行中。';
}

export function BrandIntelligenceRunBanner({
  run,
  isLoading,
  isSubmitting,
  error,
  onStart,
  onResume,
  onCancel,
  onOpenChat,
}: BrandIntelligenceRunBannerProps) {
  const active = isActiveBrandIntelligenceRun(run);
  const running = active && run?.status !== 'not_started';
  const waiting = run?.requires_user_action || run?.status === 'waiting_user';
  const failed = run?.status === 'failed';
  const completed = run?.status === 'completed';
  const statusLabel = run ? STATUS_LABELS[run.status] || run.status : '未开始';
  const primaryLabel = !run || run.status === 'not_started'
    ? '开始分析'
    : failed || run.status === 'cancelled'
      ? '重新开始'
      : '继续分析';
  const showPrimary = !completed && !waiting;

  return (
    <section className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="inline-flex h-7 items-center gap-2 rounded-lg bg-[var(--bg-secondary)] px-2.5 text-[12px] font-medium text-[var(--brand-primary)]">
              {isLoading ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
              当前情报任务
            </span>
            <span className="text-[12px] text-[var(--text-tertiary)]">{statusLabel}</span>
            {run ? (
              <span className="text-[12px] text-[var(--text-tertiary)]">{progressLabel(run)}</span>
            ) : null}
          </div>
          <div className="mt-2 flex items-start gap-2">
            {waiting ? (
              <AlertCircle className="mt-1 h-4 w-4 flex-shrink-0 text-[var(--status-warning)]" />
            ) : completed ? (
              <CheckCircle2 className="mt-1 h-4 w-4 flex-shrink-0 text-[var(--success)]" />
            ) : running ? (
              <Loader2 className="mt-1 h-4 w-4 flex-shrink-0 animate-spin text-[var(--brand-primary)]" />
            ) : (
              <Play className="mt-1 h-4 w-4 flex-shrink-0 text-[var(--brand-primary)]" />
            )}
            <p className="text-[13px] leading-6 text-[var(--text-secondary)]">
              {error || runMessage(run)}
            </p>
          </div>
          {run?.sample_scope ? (
            <p className="mt-2 text-[12px] text-[var(--text-tertiary)]">
              {[
                typeof run.sample_scope.platform_count === 'number' ? `${run.sample_scope.platform_count} 个平台` : null,
                typeof run.sample_scope.question_count === 'number' ? `${run.sample_scope.question_count} 个问题` : null,
                typeof run.sample_scope.answer_count === 'number' ? `${run.sample_scope.answer_count} 条回答` : null,
              ].filter(Boolean).join(' · ')}
            </p>
          ) : null}
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {showPrimary ? (
            <button
              type="button"
              disabled={isSubmitting}
              onClick={!run || run.status === 'not_started' || failed || run.status === 'cancelled' ? onStart : onResume}
              className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-3.5 text-[13px] font-semibold text-[var(--brand-contrast)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isSubmitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              {primaryLabel}
            </button>
          ) : null}
          <button
            type="button"
            onClick={onOpenChat}
            className="inline-flex min-h-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3.5 text-[13px] font-medium text-[var(--text-primary)] hover:border-[var(--brand-primary)]"
          >
            进入对话
          </button>
          {running || waiting ? (
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex min-h-10 w-10 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)] hover:border-[var(--status-error)] hover:text-[var(--status-error)]"
              aria-label="取消任务"
            >
              <X className="h-4 w-4" />
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}
