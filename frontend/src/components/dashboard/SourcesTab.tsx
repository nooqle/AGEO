'use client';

import {
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Tooltip,
} from 'recharts';
import { RiPieChart2Line } from '@remixicon/react';
import type { SourceData } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { tooltipStyle, PIE_COLORS } from '@/styles/chart-theme';

interface SourcesTabProps {
  data: SourceData[];
}

export function SourcesTab({ data }: SourcesTabProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={RiPieChart2Line}
        title="暂无来源数据"
        description="完成数据分析（A5）后即可查看来源分布"
      />
    );
  }

  return (
    <div className="grid grid-cols-2 gap-6">
      {/* Pie Chart */}
      <div
        className="rounded-xl p-4"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
          来源分布
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie
              data={data}
              cx="50%"
              cy="50%"
              innerRadius={60}
              outerRadius={100}
              dataKey="percentage"
              nameKey="source"
              label={(entry) => `${(entry as unknown as Record<string, unknown>).source} ${Number((entry as unknown as Record<string, unknown>).percentage).toFixed(0)}%`}
            >
              {data.map((_, index) => (
                <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip contentStyle={tooltipStyle} />
          </PieChart>
        </ResponsiveContainer>
      </div>

      {/* Source List */}
      <div
        className="rounded-xl p-4"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
          来源明细
        </h3>
        <div className="space-y-3">
          {data.map((source, index) => (
            <div key={source.source} className="flex items-center gap-3">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                    {source.source}
                  </span>
                  <span className="text-sm ml-2" style={{ color: 'var(--text-secondary)' }}>
                    {source.count}
                  </span>
                </div>
                <div
                  className="mt-1 h-1.5 rounded-full overflow-hidden"
                  style={{ background: 'var(--border-subtle)' }}
                >
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${source.percentage}%`,
                      backgroundColor: PIE_COLORS[index % PIE_COLORS.length],
                    }}
                  />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
