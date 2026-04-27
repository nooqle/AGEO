import { RiBookMarkedLine } from '@remixicon/react';
import type { DashboardSourceBoard } from '@/types/dashboard';
import { getSourceLabel } from '@/lib/sourceLabel';
import { DashboardBoardTrendStrip } from './DashboardBoardTrendStrip';

interface SourceBoardProps {
  data: DashboardSourceBoard;
  onClick: () => void;
}

export function SourceBoard({ data, onClick }: SourceBoardProps) {
  const citationRate = data.content_citation_rate != null ? `${(data.content_citation_rate * 100).toFixed(1)}%` : '--';
  const officialCount = data.report.official_cases.length;
  const nonOfficialCount = data.report.non_official_cases.length;
  const topSource = data.report.top_domains[0];
  const topSourceLabel = topSource ? getSourceLabel(topSource.domain, Boolean(topSource.is_official)) : '--';

  return (
    <button
      type="button"
      onClick={onClick}
      className="dashboard-board dashboard-board--amber group relative h-full overflow-hidden rounded-[18px] p-6 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-[var(--border-hover)]"
    >
      <div className="relative flex h-full flex-col">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-[14px]" style={{ background: 'color-mix(in srgb, #d6a05c 16%, var(--bg-elevated) 84%)' }}>
            <RiBookMarkedLine className="h-5 w-5" style={{ color: '#b67e38' }} />
          </div>
          <div className="min-w-0">
            <div className="text-[20px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">内容引用率</div>
            <div className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">看多少条答案引用了品牌内容，并区分官网与第三方来源。</div>
          </div>
        </div>

        <div className="mt-6 flex items-end gap-3">
          <div className="text-[46px] font-semibold leading-none tracking-[-0.06em] text-[var(--text-primary)]">{citationRate}</div>
          <div className="pb-1 text-[13px] leading-6 text-[var(--text-secondary)]">被引用内容 {data.cited_content_count} 条</div>
        </div>

        <DashboardBoardTrendStrip trend={data.trend} accentColor="#b67e38" />

        <div className="mt-5 grid grid-cols-3 gap-3">
          <div className="rounded-[18px] border px-3 py-3" style={{ borderColor: 'var(--border-subtle)', background: 'color-mix(in srgb, var(--bg-tertiary) 80%, #edf4f0 20%)' }}>
            <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">官网引用</div>
            <div className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{officialCount}</div>
          </div>
          <div className="rounded-[18px] border px-3 py-3" style={{ borderColor: 'var(--border-subtle)', background: 'color-mix(in srgb, var(--bg-tertiary) 82%, #f8f0e6 18%)' }}>
            <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">第三方引用</div>
            <div className="mt-1 text-[20px] font-semibold text-[var(--text-primary)]">{nonOfficialCount}</div>
          </div>
          <div className="rounded-[18px] border px-3 py-3" style={{ borderColor: 'var(--border-subtle)', background: 'color-mix(in srgb, var(--bg-tertiary) 84%, #eef3f4 16%)' }}>
            <div className="text-[11px] tracking-[0.08em] text-[var(--text-tertiary)]">主要来源</div>
            <div className="mt-1 text-[15px] font-semibold text-[var(--text-primary)]">{topSourceLabel || '--'}</div>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between border-t border-[var(--border-subtle)] pt-4 text-[13px] text-[var(--text-secondary)]">
          <span>查看引用链接、涉及问题、答案片段与置信度</span>
          <span className="font-medium text-[var(--text-primary)]">展开分析</span>
        </div>
      </div>
    </button>
  );
}
