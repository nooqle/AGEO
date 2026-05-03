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
import type {
  MonitoringTrendGroupBy,
  MonitoringTrendSeries,
  TrendDataPoint,
  TrendSummary,
  TrendDirection,
} from '@/types/monitoring';
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

const API_DIMENSION_MAP: Record<DimensionKey, string> = {
  mention_rate: 'mention_rate',
  bwvs_index: 'bwvs',
  sentiment_score: 'sentiment',
  coverage_score: 'coverage',
  content_citation_rate: 'citation',
};

const GROUP_BY_OPTIONS: Array<{ key: MonitoringTrendGroupBy; label: string }> = [
  { key: 'overall', label: '总览' },
  { key: 'endpoint', label: 'AI 来源' },
  { key: 'question_set', label: '问题集' },
];

const SERIES_COLORS = [
  chart.colors.primary,
  chart.colors.green,
  chart.colors.yellow,
  chart.colors.source,
  'var(--evidence-risk)',
  'var(--text-secondary)',
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
    color?: string;
    name?: string;
    payload: TrendDataPoint & Record<string, unknown>;
  }>;
  dimension: DimensionConfig;
  seriesByKey?: Record<string, { label: string; color: string }>;
}

function TrendTooltip({ active, payload, dimension, seriesByKey }: TrendTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  const entries = payload.filter((item) => item.value != null);

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
        {entries.map((item) => {
          const config = seriesByKey?.[item.dataKey];
          return (
            <div key={item.dataKey} className="flex items-center justify-between gap-4">
              <span className="text-[var(--text-secondary)]">
                {config?.label || dimension.label}:
              </span>
              <span className="font-semibold" style={{ color: config?.color || dimension.color }}>
                {dimension.formatValue(Number(item.value))}
              </span>
            </div>
          );
        })}
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
// Custom Dot (significant data point)
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
  series?: MonitoringTrendSeries[];
  groupBy?: MonitoringTrendGroupBy;
  summary: TrendSummary | null;
  isLoading?: boolean;
  onDimensionChange?: (dimension: string) => void;
  onGroupByChange?: (groupBy: MonitoringTrendGroupBy, dimension: string) => void;
}

export function TrendChart({
  data,
  series = [],
  groupBy = 'overall',
  summary,
  isLoading,
  onDimensionChange,
  onGroupByChange,
}: TrendChartProps) {
  const [activeDimension, setActiveDimension] = useState<DimensionKey>('mention_rate');

  const dimConfig = useMemo(
    () => DIMENSIONS.find((d) => d.key === activeDimension) || DIMENSIONS[0],
    [activeDimension]
  );

  const handleDimensionChange = useCallback(
    (key: DimensionKey) => {
      setActiveDimension(key);
      onDimensionChange?.(API_DIMENSION_MAP[key]);
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
  const activeSeries = useMemo(
    () => (series.length ? series.filter((item) => item.points.length > 0) : []),
    [series],
  );
  const chartSeries = useMemo(
    () =>
      activeSeries.length
        ? activeSeries.map((item, index) => ({
            key: `series_${index}`,
            id: item.id,
            label: item.label,
            color: SERIES_COLORS[index % SERIES_COLORS.length],
          }))
        : [{ key: 'value', id: 'overall', label: dimConfig.label, color: dimConfig.color }],
    [activeSeries, dimConfig.label, dimConfig.color],
  );
  const seriesByKey = useMemo(
    () =>
      chartSeries.reduce<Record<string, { label: string; color: string }>>((acc, item) => {
        acc[item.key] = { label: item.label, color: item.color };
        return acc;
      }, {}),
    [chartSeries],
  );
  const chartData = useMemo(() => {
    if (!activeSeries.length) {
      return data;
    }
    const rows = new Map<string, Record<string, string | number | null>>();
    activeSeries.forEach((item, seriesIndex) => {
      const key = `series_${seriesIndex}`;
      item.points.forEach((point) => {
        const current = rows.get(point.date) || { date: point.date };
        current[key] = point.value;
        rows.set(point.date, current);
      });
    });
    return Array.from(rows.values()).sort((a, b) => String(a.date).localeCompare(String(b.date)));
  }, [activeSeries, data]);

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

      <div className="mb-4 inline-flex rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
        {GROUP_BY_OPTIONS.map((option) => (
          <button
            key={option.key}
            type="button"
            onClick={() => onGroupByChange?.(option.key, API_DIMENSION_MAP[activeDimension])}
            className={cn(
              'rounded-full px-3 py-1 text-[11px] font-medium transition-colors',
              groupBy === option.key
                ? 'bg-[var(--brand-primary)] text-white'
                : 'text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]'
            )}
          >
            {option.label}
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

      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
          <XAxis dataKey="date" tick={axisTick} />
          <YAxis tick={axisTick} tickFormatter={formatYAxis} />
          <Tooltip content={<TrendTooltip dimension={dimConfig} seriesByKey={seriesByKey} />} />
          {/* Reference lines for significant changes */}
          {!activeSeries.length && data
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
          {chartSeries.map((item) => (
            <Line
              key={item.key}
              type="monotone"
              dataKey={item.key}
              name={item.label}
              stroke={item.color}
              strokeWidth={2}
              dot={activeSeries.length ? { r: 2.5 } : <SignificantDot color={item.color} />}
              activeDot={{ r: 5 }}
              animationDuration={300}
              connectNulls
            />
          ))}
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
