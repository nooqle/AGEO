'use client';

import { RiRobot2Line } from '@remixicon/react';
import type { AEOMetric } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { chart } from '@/styles/chart-theme';

interface AEOTabProps {
  data: AEOMetric[];
}

const statusColors: Record<string, { color: string; bg: string }> = {
  good: { color: chart.colors.green, bg: `${chart.colors.green}1a` },
  warning: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a` },
  poor: { color: chart.colors.red, bg: `${chart.colors.red}1a` },
};

const statusLabels: Record<string, string> = {
  good: '良好',
  warning: '需改进',
  poor: '较差',
};

const barColor = (status: string) =>
  status === 'good'
    ? chart.colors.green
    : status === 'warning'
    ? chart.colors.yellow
    : chart.colors.red;

export function AEOTab({ data }: AEOTabProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={RiRobot2Line}
        title="暂无 AEO 指标"
        description="完成数据分析后即可查看 AI 引擎优化指标"
      />
    );
  }

  return (
    <div className="space-y-4">
      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div
          className="px-4 py-3"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            AEO 性能指标
          </h3>
        </div>
        <div>
          {data.map((metric) => (
            <div
              key={metric.metric}
              className="px-4 py-4 flex items-center gap-4"
              style={{ borderBottom: '1px solid var(--border-subtle)' }}
            >
              <div className="flex-1">
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {metric.metric}
                </div>
                <div className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                  基准值: {metric.benchmark.toFixed(1)}
                </div>
              </div>
              <div className="text-right">
                <div className="text-lg font-bold" style={{ color: 'var(--text-primary)' }}>
                  {metric.value.toFixed(1)}
                </div>
              </div>
              <div className="w-32">
                <div
                  className="h-2 rounded-full overflow-hidden"
                  style={{ background: 'var(--border-subtle)' }}
                >
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min((metric.value / metric.benchmark) * 100, 100)}%`,
                      backgroundColor: barColor(metric.status),
                    }}
                  />
                </div>
              </div>
              <span
                className="px-2 py-0.5 rounded-full text-xs font-medium"
                style={{
                  color: statusColors[metric.status]?.color,
                  backgroundColor: statusColors[metric.status]?.bg,
                }}
              >
                {statusLabels[metric.status]}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
