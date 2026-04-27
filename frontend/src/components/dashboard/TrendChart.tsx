'use client';

import { useState, useCallback, useMemo } from 'react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
} from 'recharts';
import { RiArrowUpLine, RiArrowDownLine, RiSubtractLine, RiFlashlightLine } from '@remixicon/react';
import type { TrendDataPoint, TrendSummary, TrendDirection } from '@/types/monitoring';
import { chart, axisTick } from '@/styles/chart-theme';
import { cn } from '@/lib/cn';

// =========================================================================
// Dimension configuration
// =========================================================================

/** Dimension keys used for UI toggling and API metric mapping */
type DimensionKey = 'mention_rate' | 'bwvs_index' | 'sentiment_score' | 'coverage_score' | 'content_citation_rate';

interface DimensionConfig {
  key: DimensionKey;
  /** Display label in the UI */
  label: string;
  color: string;
  formatValue: (v: number | null) => string;
}

const DIMENSIONS: DimensionConfig[] = [
  {
    key: 'mention_rate',
    label: '提及率',
    color: chart.colors.green,
    formatValue: (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '--'),
  },
  {
    key: 'bwvs_index',
    label: '品牌可见度',
    color: chart.colors.primary,
    formatValue: (v) => (v != null ? v.toFixed(1) : '--'),
  },
  {
    key: 'sentiment_score',
    label: '情感倾向',
    color: chart.colors.source,
    formatValue: (v) => (v != null ? v.toFixed(1) : '--'),
  },
  {
    key: 'coverage_score',
    label: '平台覆盖',
    color: chart.colors.primary,
    formatValue: (v) => (v != null ? v.toFixed(1) : '--'),
  },
  {
    key: 'content_citation_rate',
    label: '内容引用率',
    color: chart.colors.yellow,
    formatValue: (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '--'),
  },
];

// =========================================================================
// Trend direction display
// =========================================================================

const DIRECTION_CONFIG: Record<
  TrendDirection,
  { label: string; color: string; Icon: typeof RiArrowUpLine }
> = {
  improving: { label: '上升中', color: 'var(--success)', Icon: RiArrowUpLine },
  declining: { label: '下降中', color: 'var(--error)', Icon: RiArrowDownLine },
  stable: { label: '保持稳定', color: 'var(--text-secondary)', Icon: RiSubtractLine },
  volatile: { label: '波动较大', color: 'var(--warning)', Icon: RiFlashlightLine },
};

// =========================================================================
// Custom Tooltip
// =========================================================================

interface TrendTooltipProps {
  active?: boolean;
  payload?: Array<{
    value: number;
    dataKey: string;
    payload: TrendDataPoint;
  }>;
  dimension: DimensionConfig;
}

function TrendTooltip({ active, payload, dimension }: TrendTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  return (
    <div
      className="rounded-lg p-3 text-xs shadow-lg"
      style={{
        backgroundColor: chart.tooltip.bg,
        border: `1px solid ${chart.tooltip.border}`,
        color: chart.tooltip.text,
      }}
    >
      <div className="font-medium mb-1.5">{point.date}</div>
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-4">
          <span className="text-[var(--text-secondary)]">{dimension.label}:</span>
          <span className="font-semibold" style={{ color: dimension.color }}>
            {dimension.formatValue(point.value)}
          </span>
        </div>
      </div>
      {point.is_significant && (
        <div
          className="mt-1.5 pt-1.5 text-[10px] font-medium"
          style={{
            borderTop: '1px solid var(--border-subtle)',
            color: chart.colors.yellow,
          }}
        >
          显著变化
        </div>
      )}
    </div>
  );
}

// =========================================================================
// Custom Dot (significant data point glow)
// =========================================================================

interface CustomDotProps {
  cx?: number;
  cy?: number;
  payload?: TrendDataPoint;
  color: string;
}

function SignificantDot({ cx, cy, payload, color }: CustomDotProps) {
  if (!cx || !cy || !payload) return null;

  if (payload.is_significant) {
    return (
      <g>
        {/* Glow effect */}
        <circle cx={cx} cy={cy} r={8} fill={color} fillOpacity={0.2} />
        <circle cx={cx} cy={cy} r={5} fill={color} stroke="var(--bg-primary)" strokeWidth={2} />
      </g>
    );
  }

  return <circle cx={cx} cy={cy} r={3} fill={color} />;
}

// =========================================================================
// Main Component
// =========================================================================

interface TrendChartProps {
  data: TrendDataPoint[];
  summary: TrendSummary | null;
  isLoading?: boolean;
  onDimensionChange?: (dimension: string) => void;
}

export function TrendChart({ data, summary, isLoading, onDimensionChange }: TrendChartProps) {
  const [activeDimension, setActiveDimension] = useState<DimensionKey>('mention_rate');

  const dimConfig = useMemo(
    () => DIMENSIONS.find((d) => d.key === activeDimension) || DIMENSIONS[0],
    [activeDimension]
  );

  const handleDimensionChange = useCallback(
    (key: DimensionKey) => {
      setActiveDimension(key);
      // Pass the dimension key directly as the API metric parameter
      // The monitoringStore maps this to the backend metric name
      const apiDimMap: Record<DimensionKey, string> = {
        mention_rate: 'mention_rate',
        bwvs_index: 'bwvs',
        sentiment_score: 'sentiment',
        coverage_score: 'coverage',
        content_citation_rate: 'citation',
      };
      onDimensionChange?.(apiDimMap[key]);
    },
    [onDimensionChange]
  );

  const formatYAxis = useCallback(
    (value: number) => {
      if (activeDimension === 'mention_rate' || activeDimension === 'content_citation_rate') {
        return `${(value * 100).toFixed(0)}%`;
      }
      return value.toFixed(0);
    },
    [activeDimension]
  );

  const directionConfig = summary?.direction ? DIRECTION_CONFIG[summary.direction] : null;
  const DirectionIcon = directionConfig?.Icon;

  const hasLowData = data.length > 0 && data.length < 3;

  return (
    <div
      role="img"
      aria-label={`趋势图: ${dimConfig.label}${summary ? `，当前值 ${dimConfig.formatValue(summary.current_value)}，趋势 ${directionConfig?.label ?? '未知'}` : ''}`}
      className="rounded-xl p-4"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            趋势变化
          </h3>
          {/* Trend direction indicator */}
          {directionConfig && DirectionIcon && (
            <span
              className="flex items-center gap-1 text-xs font-medium"
              style={{ color: directionConfig.color }}
            >
              <DirectionIcon className="w-3.5 h-3.5" />
              {directionConfig.label}
            </span>
          )}
        </div>
        {isLoading && (
          <span className="text-[10px]" style={{ color: 'var(--text-muted)' }}>
            加载中...
          </span>
        )}
      </div>

      {/* Dimension toggle pills */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {DIMENSIONS.map((dim) => (
          <button
            key={dim.key}
            onClick={() => handleDimensionChange(dim.key)}
            className={cn(
              'px-2.5 py-1 rounded-full text-[11px] font-medium transition-all cursor-pointer',
              activeDimension === dim.key
                ? 'text-white'
                : 'text-[var(--text-secondary)] bg-[var(--bg-tertiary)] hover:bg-[var(--bg-elevated)]'
            )}
            style={
              activeDimension === dim.key
                ? { backgroundColor: dim.color, color: '#fff' }
                : undefined
            }
          >
            {dim.label}
          </button>
        ))}
      </div>

      {/* Low data notice */}
      {hasLowData && (
        <div
          className="mb-3 px-3 py-2 rounded-lg text-xs"
          style={{
            backgroundColor: 'rgba(59, 130, 246, 0.1)',
            color: 'var(--info)',
            border: '1px solid rgba(59, 130, 246, 0.15)',
          }}
        >
          数据点较少（{data.length}/{3}），随着更多监测执行完成趋势将更加清晰
        </div>
      )}

      {/* Chart — dataKey is always "value" since backend returns single-metric data */}
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
          <XAxis dataKey="date" tick={axisTick} />
          <YAxis tick={axisTick} tickFormatter={formatYAxis} />
          <Tooltip content={<TrendTooltip dimension={dimConfig} />} />
          {/* Reference lines for significant changes */}
          {data
            .filter((p) => p.is_significant)
            .map((point, i) => (
              <ReferenceLine
                key={`sig-${i}`}
                x={point.date}
                stroke={chart.colors.yellow}
                strokeDasharray="4 4"
                strokeOpacity={0.5}
              />
            ))}
          <Line
            type="monotone"
            dataKey="value"
            stroke={dimConfig.color}
            strokeWidth={2}
            dot={<SignificantDot color={dimConfig.color} />}
            activeDot={{ r: 5 }}
            animationDuration={300}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>

      {/* Summary stats */}
      {summary && (
        <div
          className="mt-3 pt-3 flex items-center gap-4 text-xs flex-wrap"
          style={{ borderTop: '1px solid var(--border-subtle)' }}
        >
          <span style={{ color: 'var(--text-muted)' }}>
            {summary.period_label}
          </span>
          {summary.change_absolute != null && (
            <span
              style={{
                color:
                  summary.change_absolute > 0
                    ? 'var(--success)'
                    : summary.change_absolute < 0
                      ? 'var(--error)'
                      : 'var(--text-tertiary)',
              }}
            >
              {summary.change_absolute > 0 ? '+' : ''}
              {(activeDimension === 'mention_rate' || activeDimension === 'content_citation_rate')
                ? `${(summary.change_absolute * 100).toFixed(1)}%`
                : summary.change_absolute.toFixed(1)}
              {summary.change_percentage != null && (
                <span className="ml-1">
                  ({summary.change_percentage > 0 ? '+' : ''}
                  {summary.change_percentage.toFixed(1)}%)
                </span>
              )}
            </span>
          )}
          <span style={{ color: 'var(--text-muted)' }}>
            {summary.data_point_count} 个数据点
          </span>
        </div>
      )}
    </div>
  );
}
