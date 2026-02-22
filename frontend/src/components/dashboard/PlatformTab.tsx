'use client';

import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from 'recharts';
import { RiBarChart2Line } from '@remixicon/react';
import type { PlatformData } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { chart, tooltipStyle, axisTick } from '@/styles/chart-theme';

interface PlatformTabProps {
  data: PlatformData[];
}

export function PlatformTab({ data }: PlatformTabProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={RiBarChart2Line}
        title="暂无平台数据"
        description="完成答案抓取（A4）后即可查看平台对比"
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
        <h3 className="text-sm font-medium mb-4" style={{ color: 'var(--text-primary)' }}>
          平台表现对比
        </h3>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={data}>
            <CartesianGrid strokeDasharray="3 3" stroke={chart.grid} />
            <XAxis dataKey="platform" tick={axisTick} />
            <YAxis tick={axisTick} />
            <Tooltip contentStyle={tooltipStyle} />
            <Legend wrapperStyle={{ color: chart.colors.secondary }} />
            <Bar dataKey="mentionRate" fill={chart.colors.primary} name="提及率" radius={[4, 4, 0, 0]} />
            <Bar dataKey="sentiment" fill={chart.colors.green} name="情感" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div
        className="rounded-xl overflow-hidden"
        style={{
          background: 'var(--bg-tertiary)',
          border: '1px solid var(--border-default)',
        }}
      >
        <table className="w-full">
          <thead style={{ background: 'var(--bg-elevated)' }}>
            <tr>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>平台</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>提及率</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>平均排名</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>情感</th>
              <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>查询数</th>
            </tr>
          </thead>
          <tbody>
            {data.map((p) => (
              <tr
                key={p.platform}
                className="hover-bg-elevated transition-colors"
                style={{ borderBottom: '1px solid var(--border-default)' }}
              >
                <td className="px-4 py-3 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{p.platform}</td>
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{(p.mentionRate * 100).toFixed(1)}%</td>
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{p.avgRanking.toFixed(1)}</td>
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{(p.sentiment * 100).toFixed(0)}%</td>
                <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{p.totalQueries}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
