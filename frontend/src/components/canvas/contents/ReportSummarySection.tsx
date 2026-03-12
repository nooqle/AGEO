import { cn } from '@/lib/cn';
import type { ReportSummaryData, ReportV2Metric } from '@/types/canvas';

interface ReportSummarySectionProps {
  data?: ReportSummaryData | null;
}

function formatMetricValue(metric: ReportV2Metric): string {
  if (metric.value === null || metric.value === undefined || metric.value === '') return '--';
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
  return metric.unit && !String(metric.value).endsWith(metric.unit) ? `${metric.value}${metric.unit}` : String(metric.value);
}

function formatTrend(trend: number | null | undefined): string | null {
  if (trend === null || trend === undefined) return null;
  const prefix = trend > 0 ? '+' : '';
  return `${prefix}${trend.toFixed(1)}`;
}

export function ReportSummarySection({ data }: ReportSummarySectionProps) {
  const metrics = data?.metrics ?? [];
  const highlights = data?.highlights ?? [];
  const hasContent = Boolean(data?.summary || data?.status_summary || metrics.length || highlights.length);

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5 border-b border-[var(--border-subtle)] pb-4">
        <h2 className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">{data?.title || '品牌现状'}</h2>
        <p className="max-w-3xl text-[14px] leading-7 text-[var(--text-secondary)]">{data?.description || '先看品牌当前在 AI 回答中的整体战况。'}</p>
      </div>

      {!hasContent ? (
        <div className="mt-5 rounded-[16px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[14px] text-[var(--text-tertiary)]">本次分析尚未形成品牌现状摘要。</div>
      ) : (
        <>
          {(data?.status_summary || data?.summary) ? (
            <div className="mt-5 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <p className="text-[15px] font-medium leading-7 text-[var(--text-primary)]">{data?.status_summary || data?.summary}</p>
            </div>
          ) : null}

          {metrics.length > 0 ? (
            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {metrics.map((metric) => (
                <div key={metric.id} className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <div className="text-[12px] text-[var(--text-tertiary)]">{metric.label}</div>
                      <div className="mt-2 text-[32px] font-semibold leading-none tracking-[-0.04em] text-[var(--text-primary)]">{formatMetricValue(metric)}</div>
                    </div>
                    {formatTrend(metric.trend) ? (
                      <span className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">{formatTrend(metric.trend)}</span>
                    ) : null}
                  </div>
                  {metric.description ? <p className="mt-4 text-[13px] leading-6 text-[var(--text-secondary)]">{metric.description}</p> : null}
                </div>
              ))}
            </div>
          ) : null}

          {highlights.length > 0 ? (
            <div className="mt-5 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="mb-3 text-[16px] font-semibold text-[var(--text-primary)]">战况摘要</div>
              <div className="space-y-2.5">
                {highlights.map((highlight, index) => (
                  <div key={`${highlight}-${index}`} className="flex gap-3 text-[14px] leading-7 text-[var(--text-secondary)]">
                    <span className="mt-[10px] h-1.5 w-1.5 flex-shrink-0 rounded-full bg-[var(--accent-primary,#6366F1)]" />
                    <span>{highlight}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}
    </section>
  );
}
