'use client';

import type { DashboardBoardTrend } from '@/types/dashboard';

interface DashboardBoardTrendStripProps {
  trend?: DashboardBoardTrend | null;
  accentColor: string;
}

const DIRECTION_LABELS: Record<string, string> = {
  improving: '上升中',
  declining: '下降中',
  stable: '保持稳定',
  volatile: '波动较大',
};

function formatValue(value: number | null, format: DashboardBoardTrend['value_format']) {
  if (value == null) return '--';
  if (format === 'percent') {
    return `${(value * 100).toFixed(1)}%`;
  }
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

function formatChange(trend: DashboardBoardTrend) {
  if (trend.change_absolute == null) return null;

  if (trend.value_format === 'percent') {
    const sign = trend.change_absolute > 0 ? '+' : '';
    return `${sign}${(trend.change_absolute * 100).toFixed(1)}%`;
  }

  const sign = trend.change_absolute > 0 ? '+' : '';
  return `${sign}${Number.isInteger(trend.change_absolute) ? trend.change_absolute : trend.change_absolute.toFixed(1)}`;
}

function buildPolylinePoints(values: number[]) {
  const width = 220;
  const height = 44;
  const padding = 4;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  return values
    .map((value, index) => {
      const x = padding + (index * (width - padding * 2)) / Math.max(values.length - 1, 1);
      const y = height - padding - ((value - min) / range) * (height - padding * 2);
      return `${x},${y}`;
    })
    .join(' ');
}

export function DashboardBoardTrendStrip({ trend, accentColor }: DashboardBoardTrendStripProps) {
  const values = (trend?.points || [])
    .map((point) => point.value)
    .filter((value): value is number => value != null);

  if (!trend || values.length < 2) {
    return (
      <div
        className="mt-4 rounded-[18px] border px-3 py-3"
        style={{
          borderColor: 'var(--border-subtle)',
          background: 'color-mix(in srgb, var(--bg-tertiary) 88%, white 12%)',
        }}
      >
        <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">监测趋势</div>
          <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
            连续监测结果达到 2 次后可显示趋势曲线。
          </div>
      </div>
    );
  }

  const polylinePoints = buildPolylinePoints(values);
  const directionLabel = DIRECTION_LABELS[trend.direction || ''] || '趋势待观察';
  const changeLabel = formatChange(trend);

  return (
    <div
      className="mt-4 rounded-[18px] border px-3 py-3"
      style={{
        borderColor: 'var(--border-subtle)',
        background: 'color-mix(in srgb, var(--bg-tertiary) 88%, white 12%)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">监测趋势</div>
        <div className="text-[11px] text-[var(--text-tertiary)]">{trend.period_label}</div>
      </div>

      <div className="mt-2 flex items-baseline justify-between gap-3">
        <div>
          <div className="text-[12px] text-[var(--text-secondary)]">{trend.metric_label}</div>
          <div className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">
            {formatValue(trend.current_value, trend.value_format)}
          </div>
        </div>
        <div className="text-right">
          <div className="text-[12px] font-medium" style={{ color: accentColor }}>
            {directionLabel}
          </div>
          <div className="mt-1 text-[12px] text-[var(--text-secondary)]">
            {changeLabel ? `较上次 ${changeLabel}` : '等待更多样本'}
          </div>
        </div>
      </div>

      <div className="mt-3">
        <svg viewBox="0 0 220 44" className="h-[44px] w-full overflow-visible" preserveAspectRatio="none">
          <polyline
            fill="none"
            points={polylinePoints}
            stroke={accentColor}
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </div>

      <div className="mt-2 text-[11px] text-[var(--text-tertiary)]">
        最近 {trend.data_point_count} 次监测结果
      </div>
    </div>
  );
}
