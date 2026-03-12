'use client';

import type { ReportCanvasContent } from '@/types/canvas';
import { buildReportViewModel } from '@/adapters/reportV2';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { InsightSection } from './InsightSection';
import { ReportMentionSection } from './ReportMentionSection';
import { ReportSummarySection } from './ReportSummarySection';
import { SourceSection } from './SourceSection';

interface ReportContentProps {
  content: ReportCanvasContent;
}

export function ReportContent({ content }: ReportContentProps) {
  if (content.data.report_kind === 'confidence_signal') {
    return <ConfidenceSignalContent content={content} />;
  }

  const view = buildReportViewModel(content);

  return (
    <div className="mx-auto max-w-[1080px] space-y-6 px-6 py-6 md:px-8 md:py-8">
      <header className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-7" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
          <div>
            <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">分析报告</div>
            <h1 className="mt-3 text-[clamp(2rem,3.2vw,3rem)] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {view.headline || '品牌战况报告'}
            </h1>
          </div>
          {view.isBaseline ? (
            <span className="inline-flex h-fit items-center rounded-full border px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
              基线报告
            </span>
          ) : null}
        </div>

        {view.subtitle ? <p className="mt-4 max-w-4xl text-[14px] leading-7 text-[var(--text-secondary)]">{view.subtitle}</p> : null}

        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-[12px] text-[var(--text-tertiary)]">
          {view.updatedAt ? <span>最近更新：{view.updatedAt}</span> : null}
          {content.data.platform_scope && content.data.platform_scope.length > 0 ? <span>平台范围：{content.data.platform_scope.join(' / ')}</span> : null}
        </div>

        {view.degradationNote ? (
          <div className="mt-5 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
            {view.degradationNote}
          </div>
        ) : null}
      </header>

      <div className="space-y-5">
        <ReportSummarySection data={view.summary} />
        <ReportMentionSection data={view.mentions} />
        <SourceSection data={view.sources} />
        <InsightSection data={view.insights} />
      </div>
    </div>
  );
}
