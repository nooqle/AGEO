'use client';

import type { ReportCanvasContent } from '@/types/canvas';
import { buildReportViewModel } from '@/adapters/reportV2';
import { CompetitorBattleSection } from './CompetitorBattleSection';
import { InsightSection } from './InsightSection';
import { ReportSummarySection } from './ReportSummarySection';
import { RiskSection } from './RiskSection';
import { ScenarioCoverageSection } from './ScenarioCoverageSection';
import { SourceSection } from './SourceSection';

interface ReportContentProps {
  content: ReportCanvasContent;
}

export function ReportContent({ content }: ReportContentProps) {
  const view = buildReportViewModel(content);

  return (
    <div className="space-y-10 p-6 md:p-8">
      <header className="space-y-4 rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-5 md:px-6">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-3">
            <div className="text-[11px] font-medium uppercase tracking-[0.16em] text-[var(--text-tertiary)]">
              Report Artifact
            </div>
            <h1 className="text-[28px] font-semibold tracking-[-0.02em] text-[var(--text-primary)] md:text-[32px]">
              {view.headline || '品牌战况报告'}
            </h1>
          </div>
          {view.isBaseline && (
            <span className="inline-flex h-fit items-center rounded-full border border-violet-500/25 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-300">
              基线报告
            </span>
          )}
        </div>

        {view.subtitle && (
          <p className="max-w-3xl text-sm leading-7 text-[var(--text-secondary)]">{view.subtitle}</p>
        )}

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-[var(--text-tertiary)]">
          {view.updatedAt && <span>最近更新：{view.updatedAt}</span>}
          {content.data.platform_scope && content.data.platform_scope.length > 0 && (
            <span>平台范围：{content.data.platform_scope.join(' / ')}</span>
          )}
        </div>

        {view.degradationNote && (
          <div className="rounded-2xl border border-amber-500/20 bg-amber-500/8 px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]">
            {view.degradationNote}
          </div>
        )}
      </header>

      <div className="space-y-10">
        <ReportSummarySection data={view.summary} />
        <ScenarioCoverageSection data={view.scenarios} />
        <CompetitorBattleSection data={view.competitorBattle} />
        <RiskSection data={view.risks} />
        <SourceSection data={view.sources} />
        <InsightSection data={view.insights} />
      </div>
    </div>
  );
}
