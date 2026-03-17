import { cn } from '@/lib/cn';
import type { ReportSummaryData, ReportV2Metric } from '@/types/canvas';
import { ReportMetricCard, ReportSection } from './ReportScaffold';

interface ReportSummarySectionProps {
  data?: ReportSummaryData | null;
}

const STATUS_STYLES: Record<string, string> = {
  good: 'bg-emerald-500/12 text-emerald-700 border-emerald-500/20',
  warning: 'bg-amber-500/12 text-amber-700 border-amber-500/20',
  risk: 'bg-rose-500/12 text-rose-700 border-rose-500/20',
  neutral: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
};

function formatMetricValue(metric: ReportV2Metric): string {
  if (metric.value === null || metric.value === undefined || metric.value === '') return '--';
  if (typeof metric.value === 'number') {
    if (metric.unit === '%' || metric.unit === 'ratio') {
      const ratioValue = metric.value <= 1 ? metric.value * 100 : metric.value;
      return `${ratioValue.toFixed(1)}%`;
    }
    const formatted = Number.isInteger(metric.value) ? String(metric.value) : metric.value.toFixed(1);
    return metric.unit ? `${formatted}${metric.unit}` : formatted;
  }
  return metric.unit && !String(metric.value).endsWith(metric.unit) ? `${metric.value}${metric.unit}` : String(metric.value);
}

export function ReportSummarySection({ data }: ReportSummarySectionProps) {
  const metrics = data?.metrics ?? [];

  return (
    <ReportSection eyebrow={data?.title || '核心指标'}>
      {metrics.length > 0 ? (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {metrics.map((metric) => (
            <ReportMetricCard
              key={metric.id}
              label={metric.label}
              value={formatMetricValue(metric)}
              caption={metric.description}
              badge={
                metric.assessment ? (
                  <span
                    className={cn(
                      'rounded-full border px-2.5 py-1 text-[11px] font-semibold',
                      STATUS_STYLES[metric.status || 'neutral']
                    )}
                  >
                    {metric.assessment}
                  </span>
                ) : null
              }
            />
          ))}
        </div>
      ) : null}
    </ReportSection>
  );
}
