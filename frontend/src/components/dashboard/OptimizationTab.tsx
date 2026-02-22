'use client';

import { RiCheckLine, RiTimeLine, RiMoreLine, RiFlashlightLine } from '@remixicon/react';
import type { OptimizationUnit } from '@/types/dashboard';
import { EmptyState } from '@/components/ui/empty-state';
import { chart } from '@/styles/chart-theme';

interface OptimizationTabProps {
  data: OptimizationUnit[];
}

const priorityColors: Record<string, { color: string; bg: string }> = {
  high: { color: chart.colors.red, bg: `${chart.colors.red}1a` },
  medium: { color: chart.colors.yellow, bg: `${chart.colors.yellow}1a` },
  low: { color: chart.colors.green, bg: `${chart.colors.green}1a` },
};

export function OptimizationTab({ data }: OptimizationTabProps) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={RiFlashlightLine}
        title="暂无优化单元"
        description="完成完整分析流程后即可查看优化建议"
      />
    );
  }

  const statusIcons: Record<string, React.ReactNode> = {
    optimized: <RiCheckLine className="w-4 h-4" style={{ color: 'var(--status-success)' }} />,
    in_progress: <RiTimeLine className="w-4 h-4" style={{ color: 'var(--status-warning)' }} />,
    not_started: <RiMoreLine className="w-4 h-4" style={{ color: 'var(--text-tertiary)' }} />,
  };

  return (
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
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>状态</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>查询词</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>当前排名</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>目标排名</th>
            <th className="px-4 py-3 text-left text-xs font-medium uppercase" style={{ color: 'var(--text-tertiary)' }}>优先级</th>
          </tr>
        </thead>
        <tbody>
          {data.map((unit) => (
            <tr
              key={unit.id}
              className="hover-bg-elevated transition-colors"
              style={{ borderBottom: '1px solid var(--border-default)' }}
            >
              <td className="px-4 py-3">{statusIcons[unit.status]}</td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-primary)' }}>{unit.query}</td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                {unit.currentRank != null ? `#${unit.currentRank}` : '--'}
              </td>
              <td className="px-4 py-3 text-sm" style={{ color: 'var(--text-secondary)' }}>#{unit.targetRank}</td>
              <td className="px-4 py-3">
                <span
                  className="px-2 py-0.5 rounded-full text-xs font-medium"
                  style={{
                    color: priorityColors[unit.priority]?.color,
                    backgroundColor: priorityColors[unit.priority]?.bg,
                  }}
                >
                  {unit.priority}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
