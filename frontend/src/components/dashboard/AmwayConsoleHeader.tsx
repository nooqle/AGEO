'use client';

import { FileText } from 'lucide-react';

interface AmwayConsoleHeaderProps {
  viewLabel: string;
  statusLabel: string;
  isRunning: boolean;
  reportLabel: string;
  reportDisabled: boolean;
  reportPrimary: boolean;
  onReportClick: () => void;
}

/**
 * 安利 Console 全局顶栏（三视图共享）。
 * 左：品牌标识与当前视图名；右：运行状态徽章 + 报告入口。
 */
export function AmwayConsoleHeader({
  viewLabel,
  statusLabel,
  isRunning,
  reportLabel,
  reportDisabled,
  reportPrimary,
  onReportClick,
}: AmwayConsoleHeaderProps) {
  return (
    <header className="sticky top-0 z-30 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-[1920px] items-center justify-between gap-4 px-5 lg:px-7 2xl:px-10">
        <div className="flex min-w-0 items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--brand-primary)] text-sm font-semibold text-[var(--brand-contrast)]">
            S
          </div>
          <div className="min-w-0">
            <div className="text-sm font-semibold leading-5">Specta AI</div>
            <div className="truncate text-xs text-[var(--text-secondary)]">安利品牌圈层 · {viewLabel}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="inline-flex items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-secondary)]">
            <span
              className={`h-1.5 w-1.5 rounded-full ${isRunning ? 'animate-pulse bg-[var(--brand-primary)]' : 'bg-[var(--text-tertiary)]'}`}
              aria-hidden="true"
            />
            <span className="font-medium text-[var(--text-primary)]">{statusLabel}</span>
          </div>
          <button
            type="button"
            onClick={onReportClick}
            disabled={reportDisabled}
            className={`inline-flex h-10 items-center gap-2 rounded-lg border px-4 text-sm font-semibold transition ${
              reportDisabled
                ? 'cursor-not-allowed border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-tertiary)]'
                : reportPrimary
                  ? 'border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)]'
                  : 'border-[var(--brand-border)] bg-transparent text-[var(--brand-primary)] hover:bg-[var(--brand-bg)]'
            }`}
          >
            <FileText size={15} />
            {reportLabel}
          </button>
        </div>
      </div>
    </header>
  );
}
