'use client';

import { useMemo } from 'react';
import { RiArrowUpLine, RiArrowDownLine, RiSubtractLine } from '@remixicon/react';
import type { MetricDelta, TrendDirection } from '@/types/monitoring';

// =========================================================================
// Direction styling
// =========================================================================

const DIRECTION_STYLE: Record<TrendDirection, { color: string; Icon: typeof RiArrowUpLine }> = {
  improving: { color: 'var(--success)', Icon: RiArrowUpLine },
  declining: { color: 'var(--error)', Icon: RiArrowDownLine },
  stable: { color: 'var(--text-secondary)', Icon: RiSubtractLine },
  volatile: { color: 'var(--warning)', Icon: RiSubtractLine },
};

// =========================================================================
// Sparkline (inline SVG, 20px tall, last 5 data points)
// =========================================================================

interface SparklineProps {
  data: number[];
  color: string;
  width?: number;
  height?: number;
}

function Sparkline({ data, color, width = 60, height = 20 }: SparklineProps) {
  const points = useMemo(() => {
    if (data.length === 0) return '';
    const min = Math.min(...data);
    const max = Math.max(...data);
    const range = max - min || 1;

    return data
      .map((v, i) => {
        const x = (i / Math.max(data.length - 1, 1)) * width;
        const y = height - ((v - min) / range) * (height - 2) - 1;
        return `${x},${y}`;
      })
      .join(' ');
  }, [data, width, height]);

  if (data.length < 2) return null;

  return (
    <svg width={width} height={height} className="flex-shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke={color}
        strokeWidth={1.5}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// =========================================================================
// MetricDeltaCard Component
// =========================================================================

interface MetricDeltaCardProps {
  metric: MetricDelta;
  className?: string;
}

export function MetricDeltaCard({ metric, className }: MetricDeltaCardProps) {
  const dirStyle = DIRECTION_STYLE[metric.direction];
  const DirIcon = dirStyle.Icon;

  const formattedValue = useMemo(() => {
    if (metric.current_value == null) return '--';
    if (metric.metric_key === 'mention_rate' || metric.metric_key === 'content_citation_rate') {
      return `${(metric.current_value * 100).toFixed(1)}%`;
    }
    return metric.current_value.toFixed(1);
  }, [metric.current_value, metric.metric_key]);

  const formattedDelta = useMemo(() => {
    if (metric.delta == null) return null;
    const prefix = metric.delta > 0 ? '+' : '';
    if (metric.metric_key === 'mention_rate' || metric.metric_key === 'content_citation_rate') {
      return `${prefix}${(metric.delta * 100).toFixed(1)}%`;
    }
    return `${prefix}${metric.delta.toFixed(1)}`;
  }, [metric.delta, metric.metric_key]);

  const sparklineColor = useMemo(() => {
    switch (metric.direction) {
      case 'improving':
        return '#22C55E';
      case 'declining':
        return '#EF4444';
      case 'volatile':
        return '#F59E0B';
      default:
        return 'var(--text-secondary)';
    }
  }, [metric.direction]);

  return (
    <div
      className={`rounded-xl p-4 ${className ?? ''}`}
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Title */}
      <div
        className="text-xs uppercase tracking-wider mb-2"
        style={{ color: 'var(--text-tertiary)' }}
      >
        {metric.label}
      </div>

      {/* Value + delta row */}
      <div className="flex items-end justify-between gap-2">
        <div className="flex items-end gap-2">
          <span
            className="text-2xl font-bold"
            style={{ color: 'var(--text-primary)' }}
          >
            {formattedValue}
          </span>
          {formattedDelta && (
            <span
              className="flex items-center text-xs font-medium mb-0.5"
              style={{ color: dirStyle.color }}
            >
              <DirIcon className="w-3 h-3" />
              {formattedDelta}
            </span>
          )}
        </div>

        {/* Sparkline */}
        <Sparkline
          data={metric.sparkline_data.slice(-5)}
          color={sparklineColor}
        />
      </div>

      {/* vs label */}
      <div className="text-[11px] mt-1.5" style={{ color: 'var(--text-muted)' }}>
        vs 上周
      </div>
    </div>
  );
}
