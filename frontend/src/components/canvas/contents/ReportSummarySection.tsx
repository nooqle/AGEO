import { cn } from '@/lib/cn';
import type { ReportSummaryData, ReportV2Metric } from '@/types/canvas';

interface ReportSummarySectionProps {
  data?: ReportSummaryData | null;
}

const statusClasses: Record<string, string> = {
  good: 'border-emerald-500/30 bg-emerald-500/5',
  warning: 'border-amber-500/30 bg-amber-500/5',
  risk: 'border-red-500/30 bg-red-500/5',
  neutral: 'border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
};

function formatMetricValue(metric: ReportV2Metric): string {
  if (metric.value === null || metric.value === undefined || metric.value === '') {
    return '--';
  }

  if (typeof metric.value === 'number') {
    if (metric.unit === 'ratio') {
      const ratioValue = metric.value <= 1 ? metric.value * 100 : metric.value;
      return `${ratioValue.toFixed(1)}%`;
    }

    const formatted = Number.isInteger(metric.value) ? String(metric.value) : metric.value.toFixed(1);
    return metric.unit ? `${formatted}${metric.unit}` : formatted;
  }

  if (metric.unit === 'ratio') {
    const parsed = Number(metric.value);
    if (Number.isFinite(parsed)) {
      const ratioValue = parsed <= 1 ? parsed * 100 : parsed;
      return `${ratioValue.toFixed(1)}%`;
    }
  }

  return metric.unit && !String(metric.value).endsWith(metric.unit)
    ? `${metric.value}${metric.unit}`
    : String(metric.value);
}

function formatTrend(trend: number | null | undefined): string | null {
  if (trend === null || trend === undefined) {
    return null;
  }

  const prefix = trend > 0 ? '+' : '';
  return `${prefix}${trend.toFixed(1)}`;
}

export function ReportSummarySection({ data }: ReportSummarySectionProps) {
  const metrics = data?.metrics ?? [];
  const highlights = data?.highlights ?? [];
  const hasContent = Boolean(data?.summary || data?.status_summary || metrics.length || highlights.length);

  return (
    <section className="space-y-5">
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '品牌现状'}
        </h2>
        <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          {data?.description || '先看品牌当前在 AI 回答中的整体战况。'}
        </p>
      </div>

      {!hasContent ? (
        <div className="rounded-[24px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-sm text-[var(--text-tertiary)]">
          本次分析尚未形成品牌现状摘要。
        </div>
      ) : (
        <>
          {(data?.status_summary || data?.summary) && (
            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4 md:px-6">
              <p className="text-sm font-medium leading-7 text-[var(--text-primary)]">
                {data?.status_summary || data?.summary}
              </p>
            </div>
          )}

          {metrics.length > 0 && (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {metrics.map((metric) => (
                <div
                  key={metric.id}
                  className={cn(
                    'flex min-h-[168px] flex-col justify-between rounded-[24px] border px-5 py-4 transition-colors',
                    statusClasses[metric.status || 'neutral'] || statusClasses.neutral
                  )}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-2">
                      <div className="text-[11px] font-medium uppercase tracking-[0.14em] text-[var(--text-tertiary)]">
                        {metric.label}
                      </div>
                      <div className="text-[30px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                        {formatMetricValue(metric)}
                      </div>
                    </div>
                    {formatTrend(metric.trend) && (
                      <span className="rounded-full bg-[var(--bg-secondary)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)]">
                        {formatTrend(metric.trend)}
                      </span>
                    )}
                  </div>
                  {metric.description && (
                    <p className="mt-4 text-sm leading-6 text-[var(--text-secondary)]">{metric.description}</p>
                  )}
                </div>
              ))}
            </div>
          )}

          {highlights.length > 0 && (
            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4 md:px-6">
              <div className="mb-3 text-sm font-medium text-[var(--text-primary)]">战况摘要</div>
              <div className="space-y-2.5">
                {highlights.map((highlight, index) => (
                  <div key={`${highlight}-${index}`} className="flex gap-3 text-sm leading-6 text-[var(--text-secondary)]">
                    <span className="mt-[10px] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--accent-primary,#6366F1)]" />
                    <span>{highlight}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </section>
  );
}
