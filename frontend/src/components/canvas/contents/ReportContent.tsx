'use client';

import type { ReportCanvasContent } from '@/types/canvas';
import { buildReportViewModel } from '@/adapters/reportV2';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { ReportMentionSection } from './ReportMentionSection';
import { ReportHero, ReportPage } from './ReportScaffold';
import { ReportSummarySection } from './ReportSummarySection';
import { ScenarioCoverageSection } from './ScenarioCoverageSection';
import { SourceSection } from './SourceSection';

interface ReportContentProps {
  content: ReportCanvasContent;
  printMode?: boolean;
}

export function ReportContent({ content, printMode = false }: ReportContentProps) {
  if (content.data.report_kind === 'confidence_signal' || content.data.artifact_kind === 'confidence_signal') {
    return <ConfidenceSignalContent content={content} printMode={printMode} />;
  }

  const view = buildReportViewModel(content);
  const reportData = content.data as typeof content.data & {
    brand_profile?: { brand_name?: string; brand_name_en?: string };
    brandProfile?: { brand_name?: string; brand_name_en?: string };
    brand_summary?: { brand_name?: string };
  };
  const resolvedBrandName =
    reportData.brand_name ||
    reportData.brand_profile?.brand_name ||
    reportData.brand_profile?.brand_name_en ||
    reportData.brandProfile?.brand_name ||
    reportData.brandProfile?.brand_name_en ||
    reportData.brand_summary?.brand_name;

  return (
    <ReportPage>
      <ReportHero
        eyebrow="分析报告"
        title={view.headline || '品牌战况报告'}
        badge={
          view.isBaseline ? (
            <span
              className="inline-flex h-fit items-center rounded-full border px-3 py-1.5 text-[12px] font-medium text-[var(--text-secondary)]"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              基线报告
            </span>
          ) : null
        }
        note={view.degradationNote}
      />

      <div className="space-y-5">
        <ReportSummarySection data={view.summary} />
        <ScenarioCoverageSection data={view.scenarioCoverage} />
        <ReportMentionSection data={view.mentions} brandName={resolvedBrandName} />
        <SourceSection data={view.sources} printMode={printMode} />
      </div>
    </ReportPage>
  );
}
