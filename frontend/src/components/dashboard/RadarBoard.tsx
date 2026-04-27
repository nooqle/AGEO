import { RiRadarLine } from '@remixicon/react';
import { PolarAngleAxis, PolarGrid, Radar, RadarChart, ResponsiveContainer } from 'recharts';
import type { DashboardRadarBoard } from '@/types/dashboard';
import { chart } from '@/styles/chart-theme';
import { DashboardBoardTrendStrip } from './DashboardBoardTrendStrip';

interface RadarBoardProps {
  data: DashboardRadarBoard;
  onClick: () => void;
}

export function RadarBoard({ data, onClick }: RadarBoardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="dashboard-board dashboard-board--mint group relative h-full overflow-hidden rounded-[18px] p-6 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-hover)]"
    >
      <div className="relative flex h-full flex-col">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[14px]" style={{ background: 'color-mix(in srgb, #8bb0a2 16%, var(--bg-elevated) 84%)' }}>
            <RiRadarLine className="h-5 w-5" style={{ color: '#568874' }} />
          </div>
          <div className="min-w-0">
            <div className="text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">五维雷达</div>
            <div className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">从五个维度看品牌当前的优势、短板和整体状态。</div>
          </div>
        </div>

        <div className="mt-6 grid gap-5 md:grid-cols-[1fr_200px] md:items-center">
          <div>
            <div className="text-[13px] leading-7 text-[var(--text-secondary)]">{data.headline}</div>
            <DashboardBoardTrendStrip trend={data.trend} accentColor="#568874" />
            <div className="mt-4 space-y-2.5 text-[12px] leading-7 text-[var(--text-secondary)]">
              <div>
                <span className="text-[var(--text-tertiary)]">当前最大优势：</span>
                <span className="font-medium text-[var(--text-primary)]">{data.strongest_dimension || '--'}</span>
              </div>
              <div>
                <span className="text-[var(--text-tertiary)]">当前最大短板：</span>
                <span className="font-medium text-[var(--text-primary)]">{data.weakest_dimension || '--'}</span>
              </div>
            </div>
          </div>

          <div className="h-[196px] rounded-[20px] border p-4" style={{ borderColor: 'var(--border-subtle)', background: 'color-mix(in srgb, var(--bg-tertiary) 84%, #f6faf8 16%)' }}>
            <ResponsiveContainer width="100%" height="100%">
              <RadarChart data={data.dimensions} outerRadius="68%">
                <PolarGrid stroke="var(--border-subtle)" />
                <PolarAngleAxis dataKey="label" tick={{ fill: chart.colors.secondary, fontSize: 11 }} />
                <Radar dataKey="score" stroke={chart.colors.source} fill={chart.colors.source} fillOpacity={0.14} />
              </RadarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-[var(--border-subtle)] pt-4 text-[13px] text-[var(--text-secondary)]">
          <span>查看各维度得分和解释</span>
          <span className="font-medium text-[var(--text-primary)]">展开分析</span>
        </div>
      </div>
    </button>
  );
}
