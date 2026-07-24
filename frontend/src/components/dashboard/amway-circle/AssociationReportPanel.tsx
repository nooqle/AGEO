/**
 * Association report panel UI (knife 6b, zero behavior).
 */

'use client';

import { Download } from 'lucide-react';
import type { OntologyAssociationCircleProjection } from '@/types/ontology';
import {
  buildAnalysisTraceFallback,
  buildAssociationNarrativeReport,
  buildEvidenceFindingsFallback,
  buildPlatformSourceSummaryFallback,
  buildQuestionDefinitionFallback,
  buildReportQualityChecksFallback,
  buildSourceAppendixFallback,
  normalizeReportNarrativeSections,
  readableNarrativeSections,
} from './reportNarrative';
import {
  buildPeriodScopeText,
  readPeriodView,
  reportEvidenceLine,
} from './reportCopy';
import { downloadAssociationReportHtml } from './reportExport';
import {
  ReportEvidenceBrief,
  ReportEvidenceSamples,
  ReportPeriodChangeSummary,
  ReportSection,
  StrategyValidationSection,
} from './reportSections';
import type { AssociationMapGroup } from './types';

export function AssociationReportPanel({
  projection,
  activeCenterTerm,
  groups,
}: {
  projection: OntologyAssociationCircleProjection;
  activeCenterTerm: string;
  groups: AssociationMapGroup[];
}) {
  const nodes = projection.nodes || [];
  const actions = projection.association_actions || [];
  const evidenceSamples = projection.evidence_samples || [];
  const platformComparison = projection.platform_comparison || [];
  const questionDefinition = projection.question_definition || buildQuestionDefinitionFallback(projection, activeCenterTerm);
  const platformSourceSummary = projection.platform_source_summary || buildPlatformSourceSummaryFallback(projection);
  const evidenceFindings = buildEvidenceFindingsFallback(projection);
  const sourceAppendix = projection.source_appendix?.length
    ? projection.source_appendix
    : buildSourceAppendixFallback(evidenceSamples);
  const reportQualityChecks = projection.report_quality_checks || buildReportQualityChecksFallback({
    questionDefinition,
    platformSourceSummary,
    evidenceFindings,
    actions,
    sourceAppendix,
  });
  const analysisTrace = projection.analysis_tool_trace?.length
    ? projection.analysis_tool_trace
    : buildAnalysisTraceFallback(questionDefinition, platformSourceSummary, evidenceFindings);
  const generatedReportSections = buildAssociationNarrativeReport({
    centerTerm: activeCenterTerm,
    groups,
    platformComparison,
    evidenceSamples,
    sampleScope: projection.sample_scope || {},
  });
  const hasBackendReportSpine = Boolean(
    projection.question_definition
      || projection.platform_source_summary
      || projection.evidence_findings?.length
      || projection.analysis_tool_trace?.length,
  );
  const normalizedReportSections = normalizeReportNarrativeSections(projection.report_narrative_sections);
  const reportSections = hasBackendReportSpine
    ? readableNarrativeSections(normalizedReportSections) || generatedReportSections
    : generatedReportSections;
  const compactReportSections = reportSections.slice(0, 6);
  const exportReportSections = compactReportSections;
  const periodView = readPeriodView(projection);
  const periodScopeText = buildPeriodScopeText(periodView);
  const isReportDeliverable = reportQualityChecks.passed === true;
  const failedQualityChecks = Array.isArray(reportQualityChecks.required_checks)
    ? reportQualityChecks.required_checks.filter((item) => (
      typeof item === 'object' && item !== null && (item as { passed?: unknown }).passed !== true
    ))
    : [];
  return (
    <section>
      <article className="amway-surface border-t-4 border-[var(--brand-primary)] bg-[var(--bg-primary)] px-6 py-7 sm:px-10 sm:py-10">
        <header className="mx-auto max-w-[1040px] border-b border-[var(--border-subtle)] pb-7">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div>
              <div className="text-xs font-semibold text-[var(--brand-primary)]">
                {isReportDeliverable ? 'SPECTA 品牌证据交付' : '报告预览 · 待校验'}
              </div>
              <h2 className="mt-2 text-3xl font-semibold text-[var(--text-primary)]">{activeCenterTerm} 品牌联想解读报告</h2>
              <p className="mt-2 text-sm text-[var(--text-secondary)]">
                已按本轮回答证据、平台来源与节点关系完成整理
                {periodScopeText ? <span> · {periodScopeText}</span> : null}
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => downloadAssociationReportHtml(activeCenterTerm, exportReportSections, {
                  questionDefinition,
                  platformSourceSummary,
                  evidenceFindings,
                  analysisTrace,
                  sourceAppendix,
                  actions,
                  reportQualityChecks,
                  groups,
                  platformComparison,
                  sampleScope: projection.sample_scope || {},
                  periodView,
                })}
                disabled={!nodes.length || !isReportDeliverable}
                title={isReportDeliverable ? '导出报告' : '质量检查通过后才可导出'}
                className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
              >
                <Download size={16} />
                导出报告
              </button>
            </div>
          </div>
        </header>

        {!isReportDeliverable ? (
          <div className="mx-auto mt-5 max-w-[1040px] rounded-xl border border-[var(--status-warning)] bg-[var(--status-warning-bg)] px-4 py-3 text-sm leading-6 text-[var(--text-secondary)]" role="status">
            这份报告尚未通过全部质量检查，仅供预览，暂不可导出。
            {failedQualityChecks.length ? ` 待处理：${failedQualityChecks.map((item) => String((item as { label?: unknown }).label || '未命名检查')).join('、')}。` : ''}
          </div>
        ) : null}

        <div className="mx-auto mt-9 max-w-[1040px] space-y-10">
          {compactReportSections.map((section, index) => {
            const sectionId = 'sectionId' in section ? section.sectionId : undefined;
            const shouldRenderStrategyDetails =
              sectionId === 'strategy_validation' || section.title.includes('战略词逐项验证');
            return (
              <div key={section.title} className="space-y-8">
                <ReportSection
                  section={section}
                  index={index}
                  groups={groups}
                  sampleScope={projection.sample_scope || {}}
                  centerTerm={activeCenterTerm}
                  strategyStoryline={projection.strategy_storyline}
                  storylineAnalysis={projection.storyline_analysis}
                />
                {shouldRenderStrategyDetails ? (
                  <StrategyValidationSection
                    activeCenterTerm={activeCenterTerm}
                    questionBank={projection.question_bank || []}
                    nodes={nodes}
                    sourceAppendix={sourceAppendix}
                    platformSourceSummary={platformSourceSummary}
                    strategyValidation={projection.strategy_validation || []}
                  />
                ) : null}
              </div>
            );
          })}

          <ReportEvidenceSamples quotes={compactReportSections.flatMap((section) => (section.supportingFacts || []).filter(reportEvidenceLine))} />

          <ReportPeriodChangeSummary periodView={periodView} />

          <ReportEvidenceBrief
            questionDefinition={questionDefinition}
            platformSourceSummary={platformSourceSummary}
            evidenceFindings={evidenceFindings}
            sourceAppendix={sourceAppendix}
            nodes={nodes}
          />
        </div>
      </article>
    </section>
  );
}
