'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
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
import { RiLineChartLine } from '@remixicon/react';
import type { VisibilityDataPoint } from '@/types/dashboard';
import type { SnapshotTrendPoint } from '@/types/snapshot';
import { CompetitorTable } from './CompetitorTable';
import { useDashboardStore } from '@/stores/dashboardStore';
import { EmptyState } from '@/components/ui/empty-state';
import { chart, tooltipStyle, axisTick } from '@/styles/chart-theme';
import { cn } from '@/lib/cn';
import { api } from '@/services/api';

type DimensionKey = 'bwvs_index' | 'mention_rate' | 'sentiment_score' | 'coverage_score' | 'citation_score';

interface DimensionConfig {
  key: DimensionKey;
  label: string;
  color: string;
}

const DIMENSIONS: DimensionConfig[] = [
  { key: 'bwvs_index', label: 'BWVS 指数', color: chart.colors.primary },
  { key: 'mention_rate', label: '提及率', color: chart.colors.green },
  { key: 'sentiment_score', label: '情感', color: chart.colors.purple },
  { key: 'coverage_score', label: '覆盖度', color: chart.colors.cyan },
  { key: 'citation_score', label: '引用', color: chart.colors.yellow },
];

interface VisibilityTabProps {
  data: VisibilityDataPoint[];
  entityId?: string;
}

interface SnapshotTooltipProps {
  active?: boolean;
  payload?: Array<{
    value: number;
    dataKey: string;
    payload: SnapshotTrendPoint;
  }>;
  label?: string;
  dimension: DimensionKey;
}

function SnapshotTooltip({ active, payload, dimension }: SnapshotTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  const dimConfig = DIMENSIONS.find((d) => d.key === dimension);

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
          <span className="text-[--text-secondary]">{dimConfig?.label || dimension}:</span>
          <span className="font-semibold" style={{ color: dimConfig?.color }}>
            {dimension === 'mention_rate'
              ? `${(point[dimension] * 100).toFixed(1)}%`
              : point[dimension]?.toFixed(1) ?? '--'}
          </span>
        </div>
        {dimension !== 'bwvs_index' && (
          <div className="flex items-center justify-between gap-4">
            <span className="text-[--text-secondary]">BWVS:</span>
            <span className="text-[--text-primary]">{point.bwvs_index?.toFixed(1) ?? '--'}</span>
          </div>
        )}
      </div>
      <div className="mt-1.5 pt-1.5 border-t border-[--border-default] text-[10px] text-[--text-tertiary]">
        快照 ID: {point.snapshot_id?.slice(0, 8)}
      </div>
    </div>
  );
}

export function VisibilityTab({ data, entityId }: VisibilityTabProps) {
  const { data: dashboardData } = useDashboardStore();
  const [activeDimension, setActiveDimension] = useState<DimensionKey>('bwvs_index');
  const [snapshotTrend, setSnapshotTrend] = useState<SnapshotTrendPoint[]>([]);
  const [isLoadingTrend, setIsLoadingTrend] = useState(false);

  // Load snapshot trend data when entityId is available
  useEffect(() => {
    if (!entityId) return;
    let cancelled = false;

    const loadTrend = async () => {
      setIsLoadingTrend(true);
      try {
        const result = await api.getSnapshotTrend(entityId, 20);
        if (!cancelled && result?.trend) {
          setSnapshotTrend(result.trend);
        }
      } catch {
        // Silently ignore -- snapshot API may not be available yet
      } finally {
        if (!cancelled) setIsLoadingTrend(false);
      }
    };

    loadTrend();
    return () => { cancelled = true; };
  }, [entityId]);

  // Use snapshot trend data if available, otherwise fall back to legacy data
  const chartData = useMemo(() => {
    if (snapshotTrend.length > 0) {
      return snapshotTrend;
    }
    // Convert legacy VisibilityDataPoint[] to a compatible format
    return data.map((d) => ({
      date: d.date,
      bwvs_index: d.score,
      mention_rate: 0,
      sentiment_score: 0,
      coverage_score: 0,
      citation_score: 0,
      snapshot_id: '',
    }));
  }, [snapshotTrend, data]);

  const hasSnapshotData = snapshotTrend.length > 0;

  const formatYAxis = useCallback((value: number) => {
    if (activeDimension === 'mention_rate') return `${(value * 100).toFixed(0)}%`;
    return value.toFixed(0);
  }, [activeDimension]);

  if (data.length === 0 && snapshotTrend.length === 0) {
    return (
      <EmptyState
        icon={RiLineChartLine}
        title="暂无可见度数据"
        description="完成品牌分析后即可查看可见度趋势"
      />
    );
  }

  return (
    <div className="space-y-6">
      <div
        className="rounded-xl p-4"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-default)',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {hasSnapshotData ? 'BWVS 趋势' : '可见度得分趋势'}
          </h3>
          {isLoadingTrend && (
            <span className="text-[10px] text-[--text-tertiary]">加载趋势数据...</span>
          )}
        </div>

        {/* Dimension toggle pills */}
        {hasSnapshotData && (
          <div className="flex flex-wrap gap-1.5 mb-4">
            {DIMENSIONS.map((dim) => (
              <button
                key={dim.key}
                onClick={() => setActiveDimension(dim.key)}
                className={cn(
                  'px-2.5 py-1 rounded-full text-[11px] font-medium transition-all',
                  activeDimension === dim.key
                    ? 'text-white'
                    : 'text-[--text-secondary] bg-[--bg-tertiary] hover:bg-[--bg-elevated]'
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
        )}

        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
            <XAxis dataKey="date" tick={axisTick} />
            <YAxis tick={axisTick} tickFormatter={formatYAxis} />
            {hasSnapshotData ? (
              <Tooltip
                content={
                  <SnapshotTooltip dimension={activeDimension} />
                }
              />
            ) : (
              <Tooltip contentStyle={tooltipStyle} />
            )}
            {/* Reference lines for snapshot dates */}
            {hasSnapshotData && chartData.map((point, i) => (
              <ReferenceLine
                key={i}
                x={point.date}
                stroke="var(--border-default)"
                strokeDasharray="2 4"
              />
            ))}
            <Line
              type="monotone"
              dataKey={hasSnapshotData ? activeDimension : 'bwvs_index'}
              stroke={DIMENSIONS.find((d) => d.key === activeDimension)?.color || chart.colors.primary}
              strokeWidth={2}
              dot={{ fill: DIMENSIONS.find((d) => d.key === activeDimension)?.color || chart.colors.primary, r: 3 }}
              activeDot={{ r: 5 }}
              animationDuration={300}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <CompetitorTable data={dashboardData?.competitors || []} />
    </div>
  );
}
