'use client';

import { chart } from '@/styles/chart-theme';
import type { CompetitorRow } from '@/types/dashboard';

interface CompetitorTableProps {
  data: CompetitorRow[];
}

export function CompetitorTable({ data }: CompetitorTableProps) {
  if (data.length === 0) return null;

  const sentimentColor = (value: number) =>
    value >= 0.7
      ? chart.colors.green
      : value >= 0.4
      ? chart.colors.yellow
      : chart.colors.red;

  return (
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
          竞品对比
        </h3>
      </div>
      <table className="w-full">
        <thead style={{ background: 'var(--bg-elevated)' }}>
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>品牌</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>可见度</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>提及率</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>平均排名</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>情感</th>
          </tr>
        </thead>
        <tbody>
          {data.map((competitor) => (
            <tr
              key={competitor.name}
              className="hover-bg-elevated transition-colors"
              style={{ borderBottom: '1px solid var(--border-subtle)' }}
            >
              <td className="px-4 py-3 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{competitor.name}</td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{competitor.visibility.toFixed(1)}</td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{(competitor.mentionRate * 100).toFixed(1)}%</td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>{competitor.avgRanking.toFixed(1)}</td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <div
                    className="w-16 h-1.5 rounded-full overflow-hidden"
                    style={{ background: 'var(--border-subtle)' }}
                  >
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${competitor.sentiment * 100}%`,
                        backgroundColor: sentimentColor(competitor.sentiment),
                      }}
                    />
                  </div>
                  <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {(competitor.sentiment * 100).toFixed(0)}%
                  </span>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
