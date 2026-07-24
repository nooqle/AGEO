import { useState, type CSSProperties } from 'react';
import { useEffect, useRef, type ReactNode } from 'react';
import {
  ArrowLeft,
  Check,
  Download,
  Info,
  Orbit,
  Play,
  RefreshCw,
  ShieldAlert,
  X,
} from 'lucide-react';
import type { DashboardHomeData } from '@/types/dashboard';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleAnalysisTraceItem,
  OntologyAssociationCircleBlindSpotMetrics,
  OntologyAssociationCircleNarrativeSection,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePlatformSourceSummary,
  OntologyAssociationCirclePlatformComparison,
  OntologyAssociationCirclePriorityItem,
  OntologyAssociationCirclePrioritySummary,
  OntologyAssociationCircleProjection,
  OntologyAssociationCircleQuestionDefinition,
  OntologyAssociationCircleQuestion,
  OntologyAssociationCircleSourceAppendixItem,
  OntologyAssociationCircleStrategyValidation,
  OntologyAssociationCircleStrategyPillar,
  OntologyAssociationCircleStrategyStoryline,
  OntologyAssociationCircleStorylineAnalysis,
  OntologyWorldSummary,
} from '@/types/ontology';

import {
  buildAssociationMapGroups,
  buildAssociationProjection,
  buildCommercialOrbitEntries,
  buildAssociationNarrativeReport,
  buildAnalysisTraceFallback,
  buildCoreVerdictMetrics,
  buildEvidenceFindingsFallback,
  buildNodeFrequencyBars,
  buildPeriodScopeText,
  buildPlatformSourceSummaryFallback,
  buildPreviousPeriodScopeText,
  buildQuestionDefinitionFallback,
  buildReportEntityTerms,
  buildReportQualityChecksFallback,
  buildSourceAppendixFallback,
  buildStrategyValidationRows,
  cleanEvidenceExcerpt,
  clampNumber,
  commercialReportCopy,
  evidenceFindingCopy,
  escapeRegexValue,
  nodeCountPhrase,
  nodeEvidenceCount,
  nodeFrequencyChartTitle,
  nodePlatformCount,
  normalizeCenterTerms,
  normalizeReportNarrativeSections,
  parseReportEvidenceLine,
  periodChangeLabel,
  periodChangeRows,
  platformLabel,
  readableNarrativeSections,
  readPeriodView,
  regulatoryScopedReportCopy,
  reportBarToneColor,
  reportEvidenceLine,
  reportPlatformAccent,
  sampleAnswerCount,
  samplePlatformCount,
  signedNumber,
  uniqueEvidenceFindingFacts,
  type AssociationMapGroup,
  type AssociationMapGroupKey,
  type NodeFrequencyBarItem,
  type ReportNarrativeSection,
} from './amway-circle';

// Re-export pure helpers and map entrypoint for existing importers of this shell file.
export {
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
};
export { CommercialOrbitView } from './amway-circle/CommercialOrbitView';


export function AssociationProjectionLoadingPanel({ centerTerm }: { centerTerm: string }) {
  return (
    <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
      <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]">
          <RefreshCw size={20} className="animate-spin" />
        </div>
        <h2 className="mt-5 text-2xl font-semibold">{centerTerm}圈层报告读取中</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
          正在读取最近一次图谱、报告和证据链。读取完成前不会展示空态，也不会把已有结果误判为未生成。
        </p>
      </div>
    </section>
  );
}

export function InfoPill({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'brand' | 'warning' | 'neutral';
}) {
  const className =
    tone === 'brand'
      ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
      : tone === 'warning'
        ? 'border-[var(--status-warning-bg)] bg-[var(--status-warning-bg)] text-[var(--text-secondary)]'
        : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  return (
    <span className={`rounded-full border px-3 py-1 ${className}`}>
      <span className="font-medium">{label}：</span>{value}
    </span>
  );
}


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


function ReportPeriodChangeSummary({
  periodView,
}: {
  periodView: Record<string, unknown> | null;
}) {
  const rows = periodChangeRows(periodView);
  const notice = String(periodView?.comparison_notice || '').trim();
  const hasPreviousPeriod = Boolean(periodView?.previous_period);
  const previousScopeText = buildPreviousPeriodScopeText(periodView);
  if (!rows.length && !notice) return null;
  return (
    <section className="rounded-3xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-6">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">周期变化</div>
      <h2 className="mt-2 text-2xl font-semibold">
        {hasPreviousPeriod ? '相比上一周期，最该关注的变化' : '本周期基线说明'}
      </h2>
      {notice ? (
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">{notice}</p>
      ) : null}
      {previousScopeText ? (
        <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
          对比周期：{previousScopeText}
        </p>
      ) : null}
      {rows.length ? (
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          {rows.map((row) => (
            <div key={`${row.node_id || row.term}`} className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
              <div className="flex items-start justify-between gap-3">
                <h3 className="font-semibold">{String(row.term || '变化节点')}</h3>
                <span className="rounded-full border border-[var(--brand-border)] px-2 py-1 text-xs text-[var(--brand-primary)]">
                  {periodChangeLabel(String(row.change_type || 'stable'))}
                </span>
              </div>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                {String(row.explanation || '')}
              </p>
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-tertiary)]">
                <span>提及 {signedNumber(row.mention_delta)}</span>
                <span>贴近 {signedNumber(row.gravity_delta)}</span>
                <span>平台 {signedNumber(row.platform_delta)}</span>
              </div>
            </div>
          ))}
        </div>
      ) : null}
    </section>
  );
}


function StrategyValidationSection({
  activeCenterTerm,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
  strategyValidation,
}: {
  activeCenterTerm: string;
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
}) {
  const rows = buildStrategyValidationRows({
    strategyValidation,
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
  if (!rows.length) return null;
  const validatedCount = rows.filter((row) => row.status === 'validated').length;
  const partialCount = rows.filter((row) => row.status === 'partial').length;
  const riskCount = rows.filter((row) => row.status === 'risk').length;

  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <header>
        <div className="text-xs font-medium text-[var(--text-tertiary)]">战略验证</div>
        <h3 className="report-font mt-2 text-[26px] font-semibold leading-snug">
          把安利的战略词放回 AI 回答里检验
        </h3>
        <p className="report-font mt-4 text-[17px] leading-9 text-[var(--text-secondary)]">
          这一部分按品牌战略词展开。先看哪些题在验证它，再看各个平台是否把它带回{activeCenterTerm}，最后回到图谱里的位置和证据。
        </p>
        <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
          回答接住 {validatedCount} 个，部分验证 {partialCount} 个，风险相关 {riskCount} 个。
        </p>
      </header>

      <div className="mt-7 space-y-8">
        {rows.map((row) => (
          <article key={row.term} className="border-t border-[var(--border-subtle)] pt-7 first:border-t-0 first:pt-0">
            <h4 className="report-font text-2xl font-semibold">{row.term}</h4>
            <p className="mt-1 text-sm text-[var(--text-tertiary)]">{row.statusLabel}</p>

            <div className="report-font mt-5 space-y-4 text-[16px] leading-8 text-[var(--text-secondary)]">
              <p><span className="font-semibold text-[var(--text-primary)]">战略意图：</span>{row.intent}</p>
              <p><span className="font-semibold text-[var(--text-primary)]">相关问题：</span>共 {row.questionCount} 道题在验证这个方向。</p>
              {row.relatedQuestions.length ? (
                <ul className="space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]" style={{ fontFamily: 'var(--font-sans, inherit)' }}>
                  {row.relatedQuestions.slice(0, 3).map((question) => (
                    <li key={question.id || question.text || question.question} className="list-disc">
                      {question.text || question.question || question.question_text}
                    </li>
                  ))}
                </ul>
              ) : null}
              <p><span className="font-semibold text-[var(--text-primary)]">AI 回答结果：</span>{row.answerResult}</p>
              <p><span className="font-semibold text-[var(--text-primary)]">图谱表现：</span>{row.graphPerformance}</p>
              <p>
                <span className="font-semibold text-[var(--text-primary)]">品牌判断：</span>{row.implication}
              </p>
              {row.actionRecommendation ? (
                <p>
                  <span className="font-semibold text-[var(--text-primary)]">下一步动作：</span>
                  {row.actionRecommendation}
                </p>
              ) : null}
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}


function renderParagraphWithBoldEntities(text: string, entities: string[]) {
  // 先解析 **加粗** Markdown 语法，再对非加粗部分做实体词加粗
  const boldSplit = text.split(/\*\*(.+?)\*\*/g);
  return boldSplit.map((segment, segmentIndex) => {
    if (!segment) return null;
    if (segmentIndex % 2 === 1) {
      return (
        <strong key={`m-${segmentIndex}`} className="font-semibold text-[var(--text-primary)]">
          {segment}
        </strong>
      );
    }
    if (!entities.length) {
      return <span key={`t-${segmentIndex}`}>{segment}</span>;
    }
    const pattern = new RegExp(`(${entities.map(escapeRegexValue).join('|')})`, 'g');
    const subParts = segment.split(pattern);
    return subParts.map((sub, subIndex) => {
      if (!sub) return null;
      if (entities.includes(sub)) {
        return (
          <strong key={`e-${segmentIndex}-${subIndex}`} className="font-semibold text-[var(--text-primary)]">
            {sub}
          </strong>
        );
      }
      return <span key={`s-${segmentIndex}-${subIndex}`}>{sub}</span>;
    });
  });
}

function ReportSection({
  section,
  index,
  groups,
  sampleScope,
  centerTerm,
  strategyStoryline,
  storylineAnalysis,
}: {
  section: ReportNarrativeSection;
  index: number;
  groups?: AssociationMapGroup[];
  sampleScope?: Record<string, unknown>;
  centerTerm?: string;
  strategyStoryline?: OntologyAssociationCircleStrategyStoryline;
  storylineAnalysis?: OntologyAssociationCircleStorylineAnalysis;
}) {
  const paragraphs = section.text.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
  const isVerdict = index === 0 || section.sectionId === 'core_verdict';
  const titleText = section.title || '';
  const isCoreVerdict = isVerdict || titleText === '核心判断';
  const isAiArchive = titleText.includes('AI 档案') || titleText.includes('档案里写了什么');
  const isFourPillars = titleText.includes('四个价值支柱') || titleText.includes('四有');
  const isPlatformDiff = titleText === '平台差异' || titleText.includes('平台差异');
  const isAction = titleText.includes('从数据到行动') || (titleText.includes('本周') && titleText.includes('件事'));
  const isBlindSpot = titleText.includes('盲区') || section.sectionId === 'ai_blind_spot';

  const coreMetrics = isCoreVerdict && sampleScope && groups?.length ? buildCoreVerdictMetrics(sampleScope, groups) : null;
  const barChartItems = isAiArchive && groups?.length ? buildNodeFrequencyBars(groups) : null;
  const actionClaims = isAction && section.claims?.length ? section.claims : null;
  const entityTerms = buildReportEntityTerms(groups, centerTerm);

  return (
    <section className={isVerdict ? 'rounded-2xl border border-[var(--brand-border)] bg-[var(--brand-bg)] px-5 py-6 sm:px-7 sm:py-7' : 'border-t border-[var(--border-subtle)] pt-10 first:border-t-0 first:pt-0'}>
      <div className="flex items-start gap-3">
        {!isVerdict ? (
          <div className="mt-1 flex h-8 w-12 shrink-0 items-center border-r border-[var(--brand-border)] pr-3" aria-hidden="true">
            <span className="text-xs font-bold tabular-nums tracking-[0.16em] text-[var(--brand-primary)]">
              {String(index).padStart(2, '0')}
            </span>
          </div>
        ) : null}
        <div className="min-w-0 flex-1">
          <h3
            className={isVerdict ? 'report-font text-[24px] font-semibold leading-snug text-[var(--brand-primary)] sm:text-[28px]' : 'report-font text-[26px] font-semibold leading-snug text-[var(--text-primary)]'}
          >
            {section.title}
          </h3>
        </div>
      </div>
      {section.readerQuestion ? (
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
          {section.readerQuestion}
        </p>
      ) : null}
      {section.takeaway ? (
        isVerdict ? (
          <div
            className="report-font mt-5 rounded-r-lg border-l-4 bg-[var(--report-takeaway-strong-bg)] px-5 py-4 text-[17px] leading-8 text-[var(--brand-primary)]"
            style={{ borderLeftColor: 'var(--brand-primary)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        ) : isBlindSpot ? (
          <div
            className="report-font mt-5 rounded-r-lg border-l-4 bg-[var(--report-takeaway-risk-bg)] px-5 py-4 text-[17px] leading-8 text-[var(--error)]"
            style={{ borderLeftColor: 'var(--error)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        ) : (
          <div
            className="report-font mt-5 rounded-r-lg border-l-4 bg-[var(--report-takeaway-bg)] px-5 py-4 text-[17px] leading-8 text-[var(--text-primary)]"
            style={{ borderLeftColor: 'var(--brand-primary)' }}
          >
            {renderParagraphWithBoldEntities(section.takeaway, entityTerms)}
          </div>
        )
      ) : null}
      {coreMetrics?.length ? <ReportMetricRow metrics={coreMetrics} /> : null}
      {isBlindSpot ? <ReportBlindSpotTable metrics={storylineAnalysis?.blind_spot} /> : null}
      {isFourPillars && section.claims?.length ? (
        <ReportFourHaveMetricCards
          claims={section.claims}
          pillars={strategyStoryline?.pillars || []}
        />
      ) : null}
      {actionClaims?.length ? (
        <ReportActionCards claims={actionClaims} tone="problem" />
      ) : (isAiArchive || isPlatformDiff) && section.claims?.length ? (
        <ReportPersonaClaimCards claims={section.claims} />
      ) : section.claims?.length && !isFourPillars && !isBlindSpot ? (
        <ul className="mt-5 grid gap-2 text-sm leading-7 text-[var(--text-secondary)] sm:grid-cols-2">
          {section.claims.slice(0, 4).map((claim) => (
            <li key={claim} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
              {claim}
            </li>
          ))}
        </ul>
      ) : null}
      <div className="mt-4 space-y-4">
        {paragraphs.map((paragraph) => (
          isAction ? (
            <div
              key={paragraph}
              className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
              style={{ borderLeft: '4px solid var(--brand-primary)' }}
            >
              <p className="report-font text-[15px] leading-7 text-[var(--text-secondary)]">
                {renderParagraphWithBoldEntities(paragraph, entityTerms)}
              </p>
            </div>
          ) : (
            <p
              key={paragraph}
              className="report-font text-[17px] leading-9 text-[var(--text-secondary)]"
            >
              {renderParagraphWithBoldEntities(paragraph, entityTerms)}
            </p>
          )
        ))}
      </div>
      {barChartItems?.length ? <ReportBarChart items={barChartItems} /> : null}
      {isPlatformDiff && section.claims?.length ? <ReportPlatformEvaluationTable claims={section.claims} /> : null}
      {section.soWhat && !isVerdict ? (
        <p className="mt-6 rounded-xl bg-[var(--bg-secondary)] px-4 py-3 text-sm leading-7 text-[var(--text-primary)]">
          {section.soWhat}
        </p>
      ) : null}
      {section.evidenceRefs?.length && !isVerdict ? (
        <div className="mt-6 border-t border-[var(--border-subtle)] pt-5 text-sm leading-6 text-[var(--text-secondary)]">
          <p>已关联 {section.evidenceRefs.length} 个证据引用，问题、平台和摘录见下方证据链。</p>
        </div>
      ) : null}
    </section>
  );
}


function ReportMetricRow({ metrics }: { metrics: Array<{ label: string; value: string; sub?: string; tone?: 'default' | 'risk' | 'opportunity' }> }) {
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {metrics.map((metric) => (
        <div key={metric.label} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3">
          <div className="text-xs text-[var(--text-secondary)]">{metric.label}</div>
          <div className={`mt-1 text-2xl font-semibold tabular-nums ${metric.tone === 'risk' ? 'text-[var(--error)]' : metric.tone === 'opportunity' ? 'text-[var(--evidence-opportunity)]' : 'text-[var(--text-primary)]'}`}>
            {metric.value}
          </div>
          {metric.sub ? <div className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{metric.sub}</div> : null}
        </div>
      ))}
    </div>
  );
}

function ReportBarChart({ items }: { items: NodeFrequencyBarItem[] }) {
  if (!items.length) return null;
  const maxValue = Math.max(...items.map((item) => item.value), 1);
  return (
    <div className="mt-6 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-4">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">{nodeFrequencyChartTitle(items)}</div>
      <div className="mt-3 space-y-2">
        {items.map((item) => (
          <div key={item.label} className="flex items-center gap-3 text-sm">
            <span className="w-28 shrink-0 truncate text-right text-[var(--text-secondary)]" title={item.label}>{item.label}</span>
            <div className="h-5 flex-1 overflow-hidden rounded bg-[var(--bg-secondary)]">
              <div
                className="h-full rounded transition-all"
                style={{ width: `${Math.max(4, (item.value / maxValue) * 100)}%`, backgroundColor: reportBarToneColor(item.tone) }}
              />
            </div>
            <span className="w-12 shrink-0 text-right font-semibold tabular-nums text-[var(--text-primary)]">{item.valueLabel}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-[var(--text-tertiary)]">
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('strong') }} />稳定轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('growth') }} />机会轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('story') }} />观察轨</span>
        <span className="inline-flex items-center gap-1"><span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: reportBarToneColor('risk') }} />风险关系</span>
      </div>
    </div>
  );
}

function ReportActionCards({ claims, tone = 'action' }: { claims: string[]; tone?: 'problem' | 'action' }) {
  const borderColor = tone === 'problem' ? 'var(--error)' : 'var(--brand-primary)';
  return (
    <div className="mt-5 space-y-3">
      {claims.slice(0, 4).map((claim, index) => (
        <div
          key={claim}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
          style={{ borderLeft: `4px solid ${borderColor}` }}
        >
          <div className="flex items-start gap-3">
            <span
              className="mt-1 inline-flex w-7 shrink-0 text-[11px] font-semibold tabular-nums tracking-[0.14em]"
              style={{ color: borderColor }}
            >
              {String(index + 1).padStart(2, '0')}
            </span>
            <p className="min-w-0 flex-1 text-sm leading-7 text-[var(--text-secondary)]">{claim}</p>
          </div>
        </div>
      ))}
    </div>
  );
}

function ReportPersonaClaimCards({ claims }: { claims: string[] }) {
  return (
    <div className="mt-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {claims.slice(0, 4).map((claim) => {
        const match = claim.match(/^([^｜]+)｜(.+)$/);
        const platform = match?.[1]?.trim() || '';
        const rest = match?.[2] || claim;
        const accent = platform ? reportPlatformAccent(platform) : 'var(--brand-primary)';
        const parenIndex = rest.indexOf('（');
        const personaLine = parenIndex > 0 ? rest.slice(0, parenIndex).trim() : rest;
        const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
        return (
          <div
            key={claim}
            className="overflow-hidden rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
            style={{ borderTop: `3px solid ${accent}` }}
          >
            <div className="px-4 pt-3 pb-3">
              <div className="text-base font-semibold" style={{ color: accent }}>{platform}</div>
              <p className="mt-1.5 text-sm leading-6 text-[var(--text-primary)]">{personaLine}</p>
              {dataLine ? (
                <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">{dataLine}</p>
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function ReportBlindSpotTable({ metrics }: { metrics?: OntologyAssociationCircleBlindSpotMetrics }) {
  const numberOrNull = (value: unknown): number | null => (
    typeof value === 'number' && Number.isFinite(value) ? value : null
  );
  const brandNamed = numberOrNull(metrics?.brand_named_answer_count);
  const brandNamedMentions = numberOrNull(metrics?.brand_named_brand_mention_count);
  const openAnswers = numberOrNull(metrics?.open_answer_count);
  const openMentions = numberOrNull(metrics?.open_brand_mention_count);
  const openRate = numberOrNull(metrics?.active_mention_rate);
  const brandNamedRate = brandNamed !== null && brandNamed > 0 && brandNamedMentions !== null
    ? brandNamedMentions / brandNamed
    : null;
  const exactAnswers = metrics?.answer_count_is_exact === true;
  const countLabel = exactAnswers ? '回答总量' : '去重原文观察';
  const formatCount = (value: number | null) => value === null ? '未评估' : String(value);
  const formatRate = (value: number | null) => value === null ? '未评估' : `${Math.round(value * 1000) / 10}%`;
  return (
    <div className="mt-6 rounded-xl border border-[var(--error)] bg-[var(--report-blindspot-bg)] p-5">
      <div className="text-sm font-semibold text-[var(--error)]">最值得重视的一组数字</div>
      <table className="mt-3 w-full text-sm">
        <thead>
          <tr className="text-left text-xs text-[var(--text-tertiary)]">
            <th className="py-2 font-medium">问题类型</th>
            <th className="py-2 text-right font-medium">{countLabel}</th>
            <th className="py-2 text-right font-medium">主动提到安利</th>
            <th className="py-2 text-right font-medium">比率</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="py-2">问题中包含「安利」</td>
            <td className="py-2 text-right tabular-nums">{formatCount(brandNamed)}</td>
            <td className="py-2 text-right tabular-nums text-[var(--brand-primary)]">{formatCount(brandNamedMentions)}</td>
            <td className="py-2 text-right tabular-nums text-[var(--brand-primary)]">{formatRate(brandNamedRate)}</td>
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="py-2">问题中不含「安利」</td>
            <td className="py-2 text-right tabular-nums">{formatCount(openAnswers)}</td>
            <td className="py-2 text-right tabular-nums text-[var(--error)]">{formatCount(openMentions)}</td>
            <td className="py-2 text-right tabular-nums text-[var(--error)]">
              {formatRate(openRate)}
            </td>
          </tr>
        </tbody>
      </table>
      {!exactAnswers ? (
        <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
          历史产物未保存可去重回答 ID；本表按运行、平台和问题去重展示原文观察，不冒充精确回答数。
        </p>
      ) : null}
    </div>
  );
}

function ReportFourHaveMetricCards({
  claims,
  pillars,
}: {
  claims: string[];
  pillars: OntologyAssociationCircleStrategyPillar[];
}) {
  const parseClaim = (claim: string) => {
    const labelMatch = claim.match(/^有(健康|陪伴|保障|价值)/);
    const label = labelMatch ? `有${labelMatch[1]}` : '';
    const gapMatch = claim.match(/差距类型为([^；；]+)/);
    const gap = gapMatch?.[1]?.trim() || '';
    const cumulativeMatch = claim.match(/累计命中\s*(\d+)\s*次，样本回答\s*(\d+)\s*条/);
    const countMatch = claim.match(/(\d+)\s*条/);
    const count = cumulativeMatch ? '' : countMatch?.[1] || '0';
    const pctMatch = claim.match(/占\s*([\d.]+)%/);
    const pct = pctMatch?.[1] || '';
    const nodeMatch = claim.match(/代表节点为([^。]+)|风险入口为([^。]+)|线索为([^。]+)/);
    const nodes = nodeMatch?.[1] || nodeMatch?.[2] || nodeMatch?.[3] || '';
    const note = cumulativeMatch
      ? `旧报告仅保存 ${cumulativeMatch[1]} 次跨词命中与 ${cumulativeMatch[2]} 条总样本；去重回答数待重新生成`
      : pct
        ? `占样本回答 ${pct}%`
        : '占比待评估';
    return { label, gap, count, pct, nodes, note };
  };
  const structuredItems = pillars.map((pillar) => ({
    label: pillar.label || '',
    gap: pillar.status_label || '待观察',
    count: pillar.answer_count_is_exact === true
      ? String(pillar.answer_mention_count || 0)
      : pillar.count_semantics === 'known_answer_refs_lower_bound'
        ? `≥${pillar.answer_mention_count || 0}`
        : String(pillar.answer_mention_count || 0),
    unit: pillar.answer_count_is_exact === true
      || pillar.count_semantics === 'known_answer_refs_lower_bound'
      ? '条'
      : '次',
    nodes: (pillar.node_terms || []).join('、'),
    note: pillar.answer_count_is_exact === true
      ? `去重回答数 · 覆盖 ${pillar.platform_count || 0} 个平台`
      : pillar.count_semantics === 'known_answer_refs_lower_bound'
        ? '旧新证据混合，仅展示可确认下限'
        : '节点提及次数（跨词可重复），不可作为去重回答数',
  })).filter((item) => item.label);
  const items = structuredItems.length
    ? structuredItems
    : claims.map(parseClaim).filter((item) => item.label).map((item) => ({ ...item, unit: '条' }));
  const toneColor = (gap: string) => {
    if (gap.includes('反转') || gap.includes('劫持') || gap.includes('遮蔽')) return 'var(--error)';
    if (gap.includes('层级') || gap.includes('牵制') || gap.includes('偏产品') || gap.includes('萌芽')) {
      return 'var(--status-warning)';
    }
    if (gap.includes('缺位') || gap.includes('缺故事') || gap.includes('弱信号') || gap.includes('待观察')) {
      return 'var(--text-secondary)';
    }
    return 'var(--brand-primary)';
  };
  return (
    <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 py-3"
          style={{ borderTop: `3px solid ${toneColor(item.gap)}` }}
        >
          <div className="text-sm font-semibold text-[var(--text-primary)]">{item.label}</div>
          <div className="mt-1 text-xs font-medium text-[var(--text-secondary)]">{item.gap}</div>
          <div className="mt-2 text-2xl font-semibold tabular-nums" style={{ color: toneColor(item.gap) }}>
            {item.count || '—'}{item.count ? <span className="ml-1 text-sm font-medium">{item.unit}</span> : null}
          </div>
          <div className="mt-1 text-xs font-medium leading-5 text-[var(--text-secondary)]">
            {item.note}
          </div>
          {item.nodes ? (
            <div className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">{item.nodes}</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function ReportPlatformEvaluationTable({ claims }: { claims: string[] }) {
  const platforms = claims.map((claim) => {
    const match = claim.match(/^([^｜]+)｜(.+)$/);
    const platform = match?.[1]?.trim() || '';
    const rest = match?.[2] || claim;
    const parenIndex = rest.indexOf('（');
    const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
    const answerMatch = dataLine.match(/(?:回答|品牌关联原文片段)\s*(\d+)\s*条/);
    const riskMatch = dataLine.match(/风险语境\s*(\d+)\s*条/);
    const transMatch = dataLine.match(/转型叙事\s*(\d+)\s*条/);
    const activeMatch = dataLine.match(/主动带出品牌\s*(\d+)\s*条/);
    const answers = answerMatch ? parseInt(answerMatch[1], 10) : 0;
    const risks = riskMatch ? parseInt(riskMatch[1], 10) : null;
    const trans = transMatch ? parseInt(transMatch[1], 10) : null;
    const active = activeMatch ? parseInt(activeMatch[1], 10) : null;
    const sampleLimited = answers > 0 && answers < 3;
    const riskRate = answers && risks !== null ? risks / answers : null;
    const transRate = answers && trans !== null ? trans / answers : null;
    return {
      platform,
      answers,
      riskDensity: sampleLimited ? '样本不足' : riskRate === null ? '未评估' : riskRate >= 0.45 ? '高' : riskRate >= 0.3 ? '中' : '低',
      transitionNarrative: sampleLimited ? '样本不足' : transRate === null ? '未评估' : transRate >= 0.6 ? '高' : transRate >= 0.3 ? '中' : '低',
      activeRecommend: active === null ? '未评估' : active >= 1 ? '有' : '无',
    };
  }).filter((p) => p.platform);
  if (!platforms.length) return null;
  const riskColor = (val: string) => {
    if (val === '未评估' || val === '样本不足') return 'text-[var(--text-secondary)]';
    if (val === '高') return 'text-[var(--error)]';
    if (val === '低') return 'text-[var(--brand-primary)]';
    return 'text-[var(--status-warning)]';
  };
  const goodColor = (val: string) => {
    if (val === '未评估' || val === '样本不足') return 'text-[var(--text-secondary)]';
    if (val === '高' || val === '有') return 'text-[var(--brand-primary)]';
    if (val === '低' || val === '无') return 'text-[var(--error)]';
    return 'text-[var(--status-warning)]';
  };
  return (
    <div className="mt-6 overflow-x-auto rounded-xl border border-[var(--border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)] text-left text-xs text-[var(--text-tertiary)]">
            <th className="px-3 py-2 font-medium">维度</th>
            {platforms.map((p) => (
              <th key={p.platform} className="px-3 py-2 font-medium">{p.platform}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">品牌关联原文片段</td>
            {platforms.map((p) => (
              <td key={p.platform} className="px-3 py-2 font-semibold tabular-nums text-[var(--text-primary)]">{p.answers}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">风险语境密度</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${riskColor(p.riskDensity)}`}>{p.riskDensity}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">转型叙事覆盖度</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${goodColor(p.transitionNarrative)}`}>{p.transitionNarrative}</td>
            ))}
          </tr>
          <tr className="border-t border-[var(--border-subtle)]">
            <td className="px-3 py-2 text-[var(--text-secondary)]">主动带出品牌</td>
            {platforms.map((p) => (
              <td key={p.platform} className={`px-3 py-2 font-semibold ${p.activeRecommend === '未评估' ? 'text-[var(--text-tertiary)]' : goodColor(p.activeRecommend === '有' ? '高' : '低')}`}>{p.activeRecommend}</td>
            ))}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function renderAnswerMarkdown(text: string) {
  const normalized = text
    .replace(/([^\n])\s*(#{1,6}\s)/g, '$1\n$2')
    .replace(/([^\n])\s+([-*]\s)/g, '$1\n$2');
  const lines = normalized.split('\n');
  return lines.map((line, i) => {
    const trimmed = line.trim();
    const hMatch = trimmed.match(/^#{1,6}\s+(.+)$/);
    if (hMatch) {
      return (
        <div key={i} className="report-font mt-3 mb-1 font-semibold text-[var(--text-primary)]">
          {renderParagraphWithBoldEntities(hMatch[1], [])}
        </div>
      );
    }
    const liMatch = trimmed.match(/^[-*]\s+(.+)$/);
    if (liMatch) {
      return (
        <div key={i} className="report-font pl-3 leading-7">
          <span className="text-[var(--text-tertiary)]">· </span>
          {renderParagraphWithBoldEntities(liMatch[1], [])}
        </div>
      );
    }
    if (!trimmed) {
      return <div key={i} className="h-2" />;
    }
    return (
      <div key={i} className="report-font leading-7">
        {renderParagraphWithBoldEntities(line, [])}
      </div>
    );
  });
}

function ReportEvidenceSamples({ quotes }: { quotes: string[] }) {
  const uniqueQuotes = Array.from(new Set(quotes));
  if (!uniqueQuotes.length) return null;
  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <h3 className="report-font text-[26px] font-semibold leading-snug text-[var(--text-primary)]">
        事实举例
      </h3>
      <p className="mt-3 text-sm leading-7 text-[var(--text-tertiary)]">
        以下是平台回答安利相关问题的原文摘录，按平台色区分。点击展开可查看完整原文。
      </p>
      <div className="mt-6 space-y-3">
        {uniqueQuotes.map((fact, index) => {
          const parsed = parseReportEvidenceLine(fact);
          const accent = reportPlatformAccent(parsed.platform);
          const body = parsed.body;
          const isPlatformQuote = fact.startsWith('平台原文');
          const label = isPlatformQuote ? '平台原文' : 'AI 摘录';
          const isComplete = body.length > 500 || /[。？！…」"']$/.test(body.trim());
          const isLong = body.length > 120;
          const preview = isLong ? `${body.slice(0, 120)}...` : body;
          return (
            <blockquote
              key={`${index}-${parsed.platform}`}
              className="overflow-hidden rounded-r-xl rounded-l-sm border-l-4 bg-[var(--bg-secondary)] pr-4 text-sm leading-7 text-[var(--text-secondary)]"
              style={{ borderLeftColor: accent }}
            >
              <div className="flex items-center gap-2 px-4 pt-3">
                <span
                  className="inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold text-white"
                  style={{ backgroundColor: accent }}
                >
                  {parsed.platform}
                </span>
                <span className="text-[11px] font-medium text-[var(--text-tertiary)]">{label}</span>
                {!isComplete ? (
                  <span className="text-[11px] font-medium text-[var(--status-warning)]">· 摘录可能不完整</span>
                ) : null}
              </div>
              {isLong ? (
                <details className="px-4 pb-3 pt-2">
                  <summary className="report-font cursor-pointer leading-7">
                    {preview}
                  </summary>
                  <div className="mt-3">{renderAnswerMarkdown(body)}</div>
                </details>
              ) : (
                <div className="px-4 pb-3 pt-2">{renderAnswerMarkdown(body)}</div>
              )}
            </blockquote>
          );
        })}
      </div>
    </section>
  );
}

function ReportEvidenceBrief({
  questionDefinition,
  platformSourceSummary,
  evidenceFindings,
  sourceAppendix,
  nodes,
}: {
  questionDefinition?: OntologyAssociationCircleQuestionDefinition;
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  nodes: OntologyAssociationCircleNode[];
}) {
  if (!questionDefinition && !platformSourceSummary && !evidenceFindings.length) return null;
  const audienceText = (questionDefinition?.audience_segments || []).join('、') || '题库未携带人群标签';
  const probeText = (questionDefinition?.probe_types || []).join('、') || '题库未携带探针标签';
  const opportunityText = (questionDefinition?.opportunity_points || []).join('、') || '题库未携带机会点标签';
  return (
    <section className="border-t border-[var(--border-subtle)] pt-10">
      <div className="text-xs font-medium text-[var(--text-tertiary)]">附录</div>
      <h3 className="report-font mt-2 text-[26px] font-semibold leading-snug">
        样本、平台与原文证据
      </h3>
      {questionDefinition?.definition_sentence ? (
        <p className="report-font mt-4 text-[16px] leading-8 text-[var(--text-secondary)]">
          {questionDefinition.definition_sentence}
        </p>
      ) : null}

      <div className="mt-6 space-y-7">
        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">问题定义</h4>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            人群：{audienceText}；探针：{probeText}；机会点：{opportunityText}。
          </p>
          {(questionDefinition?.sample_questions || []).length ? (
            <ul className="mt-3 space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
              {(questionDefinition?.sample_questions || []).slice(0, 5).map((question, index) => (
                <li key={question.id || question.question_id || question.text || question.question_text || index} className="list-disc">
                  {question.text || question.question_text}
                </li>
              ))}
            </ul>
          ) : null}
        </section>

        <section>
          <h4 className="text-sm font-semibold text-[var(--text-primary)]">平台来源</h4>
          <p className="mt-2 text-sm leading-7 text-[var(--text-secondary)]">
            本轮记录有效回答 {platformSourceSummary?.valid_answer_count ?? 0} 条，有效平台 {platformSourceSummary?.platform_count ?? 0} 个；失败 {platformSourceSummary?.failed_answer_count ?? 0} 条，空回答 {platformSourceSummary?.empty_answer_count ?? 0} 条。
          </p>
          <ul className="mt-3 space-y-2 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
            {(platformSourceSummary?.platforms || []).slice(0, 5).map((row) => (
              <li key={row.platform} className="list-disc">
                {platformLabel(row.platform || '')}：{row.valid_answer_count || 0} 条有效；{row.answer_preference || '偏好待观察'}；代表节点：{(row.preferred_nodes || []).join('、') || '暂无'}{(row.competition_nodes || []).length ? `；竞品参照：${(row.competition_nodes || []).join('、')}` : ''}。
              </li>
            ))}
          </ul>
        </section>

        {evidenceFindings.length ? (
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">证据样本</h4>
            <ul className="mt-3 space-y-3 pl-5 text-sm leading-7 text-[var(--text-secondary)]">
              {evidenceFindings.slice(0, 8).map((finding) => (
                <li key={finding.node_id || finding.node_term} className="list-disc">
                  <span className="font-semibold text-[var(--text-primary)]">{commercialReportCopy(finding.node_term)}：</span>
                  {evidenceFindingCopy(finding.claim, finding, nodes)}
                  {(() => {
                    const facts = uniqueEvidenceFindingFacts(finding, nodes, 2);
                    return facts.length
                      ? ` ${facts.join('；')}`
                      : '';
                  })()}
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {sourceAppendix.length ? (
          <section>
            <h4 className="text-sm font-semibold text-[var(--text-primary)]">原文摘录</h4>
            <div className="mt-3 space-y-4 text-sm leading-7 text-[var(--text-secondary)]">
              {sourceAppendix.slice(0, 8).map((item, index) => (
                <div key={`${item.evidence_id || index}`} className="border-t border-[var(--border-subtle)] pt-4 first:border-t-0 first:pt-0">
                  <p className="font-semibold text-[var(--text-primary)]">
                    {commercialReportCopy(item.node_term || '节点')} / {platformLabel(item.platform || '')}
                  </p>
                  <p className="mt-1">{cleanEvidenceExcerpt(item.question, 120)}</p>
                  <p className="mt-1 text-[var(--text-tertiary)]">{cleanEvidenceExcerpt(item.answer_excerpt, 180)}</p>
                </div>
              ))}
            </div>
          </section>
        ) : null}

      </div>
    </section>
  );
}

function buildExportOrbitSnapshotHtml(
  centerTerm: string,
  groups: AssociationMapGroup[] | undefined,
  sampleScope: Record<string, unknown>,
) {
  if (!groups?.length) return '';
  const associationGroups = groups.filter((group) => group.key !== 'risk');
  const riskNodes = groups.find((group) => group.key === 'risk')?.nodes || [];
  const entries = buildCommercialOrbitEntries(associationGroups, riskNodes);
  const counts = {
    strong: associationGroups.find((group) => group.key === 'strong')?.nodes.length || 0,
    growth: associationGroups.find((group) => group.key === 'growth')?.nodes.length || 0,
    story: associationGroups.find((group) => group.key === 'story')?.nodes.length || 0,
    risk: riskNodes.length,
  };
  const labelEntries = entries
    .filter((entry) => entry.labelPriority || nodeEvidenceCount(entry.node) >= 20 || nodePlatformCount(entry.node) >= 4)
    .sort((left, right) => nodeEvidenceCount(right.node) - nodeEvidenceCount(left.node))
    .slice(0, 44);
  const topNodes = entries
    .slice()
    .sort((left, right) => nodeEvidenceCount(right.node) - nodeEvidenceCount(left.node))
    .slice(0, 8);
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const labelIds = new Set(labelEntries.map((entry) => entry.node.node_id));
  const nodeDots = entries.map((entry) => {
    const x = entry.left * 12;
    const y = entry.top * 6;
    const radius = clampNumber(entry.size * 0.24, 3.2, 8.8);
    const color = exportOrbitColor(entry.groupKey);
    const opacity = labelIds.has(entry.node.node_id) ? 0.88 : 0.42;
    return `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="${radius.toFixed(1)}" fill="${color}" opacity="${opacity}" />`;
  }).join('');
  const nodeLinks = topNodes.map((entry) => {
    const x = entry.left * 12;
    const y = entry.top * 6;
    return `<line x1="600" y1="300" x2="${x.toFixed(1)}" y2="${y.toFixed(1)}" stroke="${exportOrbitColor(entry.groupKey)}" stroke-width="1.2" opacity="0.22" />`;
  }).join('');
  const labels = labelEntries.map((entry) => {
    const tone = entry.groupKey;
    const evidence = nodeEvidenceCount(entry.node);
    const origin = entry.node.term_origin === 'strategy' || entry.node.origin_label === '战略词' ? '战略' : '回答';
    const labelLeft = clampNumber(entry.left, 7.5, 92.5);
    const labelTop = clampNumber(entry.top, 8, 92);
    return `
      <span
        class="orbit-export-label orbit-label-${tone}"
        style="left:${labelLeft.toFixed(2)}%;top:${labelTop.toFixed(2)}%;"
        title="${escapeHtml(entry.node.term)} / ${escapeHtml(nodeCountPhrase(entry.node, evidence))} / ${nodePlatformCount(entry.node)} 个平台"
      >
        ${escapeHtml(entry.node.term)}
        <em>${origin}</em>
      </span>
    `;
  }).join('');
  const topList = topNodes.map((entry, index) => `
    <li>
      <span>${index + 1}. ${escapeHtml(entry.node.term)}</span>
      <b>${escapeHtml(nodeCountPhrase(entry.node, nodeEvidenceCount(entry.node)))}</b>
    </li>
  `).join('');
  return `
    <section class="orbit-export-section">
      <div class="orbit-export-head">
        <div>
          <div class="eyebrow">BRAND ASSOCIATION MAP</div>
          <h2>${escapeHtml(centerTerm)}品牌联想图谱</h2>
          <p>图谱来自本轮抓取回答后的实体抽取与校准结果。越靠近中心，说明回答越容易把该词带回品牌；红色节点表示需要单独解释的风险或竞争关系。</p>
        </div>
        <div class="orbit-export-metrics">
          <div><b>${answerCount || '-'}</b><span>有效回答</span></div>
          <div><b>${platformCount || '-'}</b><span>有效平台</span></div>
          <div><b>${entries.length}</b><span>图谱节点</span></div>
        </div>
      </div>
      <div class="orbit-export-wrap">
        <svg class="orbit-export-svg" viewBox="0 0 1200 600" role="img" aria-label="${escapeHtml(centerTerm)}品牌联想圈层图">
          <rect x="0" y="0" width="1200" height="600" rx="28" fill="#fffdf8" />
          <ellipse cx="600" cy="300" rx="288" ry="104" fill="#e1f1ed" fill-opacity="0.46" stroke="#8ecbc0" stroke-width="2" />
          <ellipse cx="600" cy="300" rx="420" ry="151" fill="none" stroke="#d7ae72" stroke-width="2" stroke-dasharray="10 12" opacity="0.62" />
          <ellipse cx="600" cy="300" rx="564" ry="203" fill="none" stroke="#c8c2b8" stroke-width="2" opacity="0.62" />
          <ellipse cx="600" cy="342" rx="582" ry="230" fill="none" stroke="#d98279" stroke-width="1.5" stroke-dasharray="8 14" opacity="0.26" />
          ${nodeLinks}
          ${nodeDots}
          <circle cx="600" cy="300" r="58" fill="#dff0ec" stroke="#1f7a6b" stroke-width="2.4" />
          <text x="600" y="286" text-anchor="middle" font-size="15" fill="#1f7a6b">中心品牌</text>
          <text x="600" y="324" text-anchor="middle" font-size="34" font-weight="700" fill="#1f7a6b">${escapeHtml(centerTerm)}</text>
        </svg>
        ${labels}
      </div>
      <div class="orbit-export-footer">
        <div class="orbit-export-legend">
          <span><i style="background:#1f7a6b"></i>稳定轨 ${counts.strong}</span>
          <span><i style="background:#b9822d"></i>机会轨 ${counts.growth}</span>
          <span><i style="background:#8f8a80"></i>观察轨 ${counts.story}</span>
          <span><i style="background:#b95046"></i>风险关系 ${counts.risk}</span>
        </div>
        <ol class="orbit-export-top">${topList}</ol>
      </div>
    </section>
  `;
}

function exportOrbitColor(groupKey: AssociationMapGroupKey) {
  if (groupKey === 'risk') return '#b95046';
  if (groupKey === 'growth') return '#b9822d';
  if (groupKey === 'story') return '#8f8a80';
  return '#1f7a6b';
}

function downloadAssociationReportHtml(
  centerTerm: string,
  sections: ReportNarrativeSection[],
  evidence?: {
    questionDefinition?: OntologyAssociationCircleQuestionDefinition;
    platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
    evidenceFindings?: OntologyAssociationCircleEvidenceFinding[];
    analysisTrace?: OntologyAssociationCircleAnalysisTraceItem[];
    sourceAppendix?: OntologyAssociationCircleSourceAppendixItem[];
    actions?: OntologyAssociationCircleProjection['association_actions'];
    reportQualityChecks?: Record<string, unknown>;
    groups?: AssociationMapGroup[];
    platformComparison?: OntologyAssociationCirclePlatformComparison[];
    sampleScope?: Record<string, unknown>;
    periodView?: Record<string, unknown> | null;
  },
) {
  if (typeof window === 'undefined') return;
  const groups = evidence?.groups;
  const reportNodes = (groups || []).flatMap((group) => group.nodes);
  const reportCopy = (value?: string | null) => regulatoryScopedReportCopy(value, reportNodes);
  const platformComparison = evidence?.platformComparison || [];
  const sampleScope = evidence?.sampleScope || {};
  const entityTerms = buildReportEntityTerms(groups, centerTerm);
  const orbitSnapshotHtml = buildExportOrbitSnapshotHtml(centerTerm, groups, sampleScope);
  const periodScopeText = buildPeriodScopeText(evidence?.periodView || null);
  const periodChangeHtml = buildExportPeriodChangeHtml(evidence?.periodView || null);

  const sectionHtml = sections.map((section, index) => {
    const titleText = reportCopy(section.title);
    const sectionClaims = (section.claims || []).map((claim) => reportCopy(claim));
    const isVerdict = index === 0 || section.sectionId === 'core_verdict';
    const isAiArchive = titleText.includes('AI 档案') || titleText.includes('档案里写了什么');
    const isAction = titleText.includes('从数据到行动') || (titleText.includes('本周') && titleText.includes('件事'));
    const isBlindSpot = titleText.includes('盲区') || section.sectionId === 'ai_blind_spot';
    const isPlatformDiff = titleText === '平台差异' || titleText.includes('平台差异');

    const takeawayClass = isBlindSpot ? 'takeaway-box-red' : isVerdict ? 'takeaway-box-green-strong' : 'takeaway-box-green';
    const takeawayHtml = section.takeaway ? `<div class="${takeawayClass}">${renderExportParagraphHtml(reportCopy(section.takeaway), entityTerms)}</div>` : '';

    let claimsHtml = '';
    if (isAiArchive && sectionClaims.length) {
      claimsHtml = `<div class="persona-grid">${sectionClaims.slice(0, 4).map((claim) => {
        const match = claim.match(/^([^｜]+)｜(.+)$/);
        const platform = match?.[1]?.trim() || '';
        const rest = match?.[2] || claim;
        const accent = platform ? reportPlatformAccent(platform) : '#1f7a6b';
        const parenIndex = rest.indexOf('（');
        const personaLine = parenIndex > 0 ? rest.slice(0, parenIndex).trim() : rest;
        const dataLine = parenIndex > 0 ? rest.slice(parenIndex) : '';
        return `<div class="persona-card" style="border-top:3px solid ${accent}"><div class="persona-name" style="color:${accent}">${escapeHtml(platform)}</div><div class="persona-desc">${escapeHtml(personaLine)}</div>${dataLine ? `<div class="persona-data">${escapeHtml(dataLine)}</div>` : ''}</div>`;
      }).join('')}</div>`;
    } else if (isAction && sectionClaims.length) {
      claimsHtml = `<div class="action-list">${sectionClaims.slice(0, 4).map((claim, i) => `<div class="problem-card"><span class="action-num">${String(i + 1).padStart(2, '0')}</span><span class="action-text">${escapeHtml(claim)}</span></div>`).join('')}</div>`;
    } else if (sectionClaims.length) {
      claimsHtml = `<ul class="claims">${sectionClaims.slice(0, 4).map((claim) => `<li>${escapeHtml(claim)}</li>`).join('')}</ul>`;
    }

    const paragraphs = reportCopy(section.text).split(/\n{2,}/).map((item) => item.trim()).filter(Boolean);
    const paragraphsHtml = paragraphs.map((p) => {
      const inner = renderExportParagraphHtml(p, entityTerms);
      return isAction
        ? `<div class="action-paragraph">${inner}</div>`
        : `<p>${inner}</p>`;
    }).join('');

    let metricsHtml = '';
    if (isVerdict && groups?.length) {
      const metrics = buildCoreVerdictMetrics(sampleScope, groups);
      metricsHtml = `<div class="metric-row">${metrics.map((m) => `<div class="metric-card"><div class="metric-label">${escapeHtml(m.label)}</div><div class="metric-value ${m.tone === 'risk' ? 'val-red' : m.tone === 'opportunity' ? 'val-opportunity' : ''}">${escapeHtml(m.value)}</div>${m.sub ? `<div class="metric-sub">${escapeHtml(m.sub)}</div>` : ''}</div>`).join('')}</div>`;
    }

    let barChartHtml = '';
    if (isAiArchive && groups?.length) {
      const items = buildNodeFrequencyBars(groups);
      if (items.length) {
        const maxValue = Math.max(...items.map((item) => item.value), 1);
        barChartHtml = `<div class="bar-chart"><div class="bar-chart-title">${escapeHtml(nodeFrequencyChartTitle(items))}</div><div class="bar-chart-body">${items.map((item) => `<div class="bar-row"><span class="bar-label">${escapeHtml(item.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, (item.value / maxValue) * 100)}%;background:${reportBarToneColor(item.tone)}"></div></div><span class="bar-value">${escapeHtml(item.valueLabel)}</span></div>`).join('')}</div></div>`;
      }
    }

    let platformTableHtml = '';
    if (isPlatformDiff && platformComparison.length) {
      platformTableHtml = `<table class="platform-table"><thead><tr><th>平台</th><th>有效回答</th><th>回答偏好</th><th>代表节点</th><th>竞品参照</th></tr></thead><tbody>${platformComparison.map((row) => `<tr><td><span class="platform-tag" style="background:${reportPlatformAccent(row.platform)}">${escapeHtml(platformLabel(row.platform))}</span></td><td class="num">${row.valid_answer_count || 0}</td><td>${escapeHtml(row.answer_preference || '偏好待观察')}</td><td>${escapeHtml((row.preferred_nodes || []).slice(0, 3).join('、') || '—')}</td><td>${escapeHtml((row.competition_nodes || []).slice(0, 3).join('、') || '—')}</td></tr>`).join('')}</tbody></table>`;
    }

    const supportingFacts = (section.supportingFacts || []).map((fact) => reportCopy(fact));
    const quoteFacts = supportingFacts.filter(reportEvidenceLine);
    const quoteHtml = quoteFacts.length && !isVerdict ? quoteFacts.slice(0, 4).map((fact) => {
      const parsed = parseReportEvidenceLine(fact);
      const accent = reportPlatformAccent(parsed.platform);
      return `<blockquote style="border-left-color:${accent}"><span class="quote-tag" style="background:${accent}">${escapeHtml(parsed.platform)}</span> <span class="quote-label">平台原文</span><br />${escapeHtml(cleanEvidenceExcerpt(parsed.body, 2000))}</blockquote>`;
    }).join('') : '';

    return `
    <section>
      <h2>${index === 0 ? '' : `<span class="section-num">${String(index).padStart(2, '0')}</span>`}${escapeHtml(titleText)}</h2>
      ${section.readerQuestion ? `<p class="chapter-question">${escapeHtml(reportCopy(section.readerQuestion))}</p>` : ''}
      ${takeawayHtml}
      ${metricsHtml}
      ${claimsHtml}
      ${paragraphsHtml}
      ${barChartHtml}
      ${platformTableHtml}
      ${quoteHtml}
      ${section.soWhat && !isVerdict ? `<p class="source-line">${escapeHtml(reportCopy(section.soWhat))}</p>` : ''}
    </section>
  `;
  }).join('\n');
  const questionDefinition = evidence?.questionDefinition;
  const platformSourceSummary = evidence?.platformSourceSummary;
  const evidenceFindings = evidence?.evidenceFindings || [];
  const analysisTrace = evidence?.analysisTrace || [];
  const sourceAppendix = evidence?.sourceAppendix || [];
  const actions = evidence?.actions || [];
  const reportQualityChecks = evidence?.reportQualityChecks || {};
  const requiredChecks = Array.isArray(reportQualityChecks.required_checks)
    ? reportQualityChecks.required_checks.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : [];
  const questionHtml = questionDefinition ? `
    <section>
      <h2>这轮问题在问什么</h2>
      <p>${escapeHtml(questionDefinition.definition_sentence || '')}</p>
      <div class="scope-grid">
        <div><b>人群</b><span>${escapeHtml((questionDefinition.audience_segments || []).join('、') || '题库未携带人群标签')}</span></div>
        <div><b>探针</b><span>${escapeHtml((questionDefinition.probe_types || []).join('、') || '题库未携带探针标签')}</span></div>
        <div><b>机会点</b><span>${escapeHtml((questionDefinition.opportunity_points || []).join('、') || '题库未携带机会点标签')}</span></div>
        <div><b>生活场景</b><span>${escapeHtml((questionDefinition.life_scenes || []).join('、') || '题库未携带生活场景标签')}</span></div>
      </div>
      ${(questionDefinition.sample_questions || []).slice(0, 6).map((question) => `
        <p class="source-line">${escapeHtml(question.text || question.question_text || '')}</p>
      `).join('')}
    </section>
  ` : '';
  const platformHtml = platformSourceSummary ? `
    <section>
      <h2>答案来源与平台样本</h2>
      <p>有效回答 ${platformSourceSummary.valid_answer_count || 0} 条，失败 ${platformSourceSummary.failed_answer_count || 0} 条，空回答 ${platformSourceSummary.empty_answer_count || 0} 条。</p>
      <table>
        <thead><tr><th>平台</th><th>有效回答</th><th>偏好</th><th>代表节点</th><th>竞品参照</th></tr></thead>
        <tbody>
          ${(platformSourceSummary.platforms || []).map((row) => `
            <tr>
              <td>${escapeHtml(platformLabel(row.platform || ''))}</td>
              <td>${row.valid_answer_count || 0}</td>
              <td>${escapeHtml(row.answer_preference || '待观察')}</td>
              <td>${escapeHtml((row.preferred_nodes || []).join('、') || '暂无')}</td>
              <td>${escapeHtml((row.competition_nodes || []).join('、') || '暂无')}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </section>
  ` : '';
  const evidenceHtml = evidenceFindings.length ? `
    <section>
      <h2>关键证据链</h2>
      ${evidenceFindings.slice(0, 8).map((finding) => `
        <article class="evidence-card">
          <h3>${escapeHtml(reportCopy(finding.node_term || ''))}</h3>
          <p>${escapeHtml(cleanEvidenceExcerpt(evidenceFindingCopy(finding.claim, finding, reportNodes), 2000))}</p>
          <ul>
            ${uniqueEvidenceFindingFacts(finding, reportNodes, 4).map((fact) => `<li>${escapeHtml(cleanEvidenceExcerpt(fact, 2000))}</li>`).join('')}
          </ul>
          ${finding.sample_excerpt ? `<blockquote>${escapeHtml(finding.sample_platform || '')} / ${escapeHtml(cleanEvidenceExcerpt(finding.sample_question, 160))}: ${escapeHtml(cleanEvidenceExcerpt(finding.sample_excerpt, 4000))}</blockquote>` : ''}
        </article>
      `).join('')}
    </section>
  ` : '';
  const traceHtml = analysisTrace.length ? `
    <section>
      <h2>分析依据轨迹</h2>
      ${analysisTrace.slice(0, 6).map((trace, index) => `
        <p class="source-line"><b>${index + 1}. ${escapeHtml(reportCopy(trace.title || ''))}</b><br />${escapeHtml(reportCopy(trace.summary || ''))}</p>
      `).join('')}
    </section>
  ` : '';
  const actionHtml = actions.length ? `
    <section>
      <h2>下一轮行动</h2>
      ${actions.slice(0, 8).map((action) => `
        <article class="evidence-card">
          <h3>${escapeHtml(reportCopy(action.title || action.action_label || action.node_term || '圈层行动'))}</h3>
          <p>${escapeHtml(reportCopy(action.expected_impact || action.reason))}</p>
          ${action.review_criteria ? `<p class="source-line"><b>复测标准</b><br />${escapeHtml(reportCopy(action.review_criteria))}</p>` : ''}
          ${(action.evidence_refs || []).length ? `<p class="source-line">已关联 ${(action.evidence_refs || []).length} 个证据引用，复测时回看对应节点和平台摘录。</p>` : ''}
        </article>
      `).join('')}
    </section>
  ` : '';
  const appendixHtml = sourceAppendix.length ? `
    <section>
      <h2>来源附录</h2>
      ${sourceAppendix.slice(0, 16).map((item) => `
        <p class="source-line"><b>${escapeHtml(reportCopy(item.node_term || '联想节点'))} / ${escapeHtml(platformLabel(item.platform || ''))} / ${escapeHtml(item.question_id ? `Q${item.question_id}` : '问题样本')}</b><br />${escapeHtml(cleanEvidenceExcerpt(item.question, 160))}<br />${escapeHtml(cleanEvidenceExcerpt(item.answer_excerpt, 220))}</p>
      `).join('')}
    </section>
  ` : '';
  const qualityHtml = requiredChecks.length ? `
    <section>
      <h2>报告完整性</h2>
      <div class="scope-grid">
        ${requiredChecks.map((check) => `
          <div><b>${escapeHtml(String(check.label || check.key || '检查项'))}</b><span>${check.passed ? '已满足' : '待补齐'}</span></div>
        `).join('')}
      </div>
    </section>
  ` : '';
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(centerTerm)}品牌圈层解读报告</title>
  <style>
    :root {
      color: #1f2933;
      background: #f7f4ed;
      font-family: "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
      --brand-primary: #1f7a6b;
      --success: #1f7a6b;
      --evidence-opportunity: #b7792b;
      --error: #b95046;
      --text-tertiary: #657184;
      --bg-secondary: #f4eee2;
    }
    body { margin: 0; background: #f7f4ed; }
    main {
      width: min(1120px, calc(100vw - 48px));
      margin: 56px auto;
      border: 1px solid #ded8cc;
      background: #fffdf8;
      padding: 56px;
      box-shadow: 0 18px 50px rgba(31, 41, 51, 0.08);
    }
    .section-num {
      display: inline-block; margin-right: 14px; padding-right: 10px;
      border-right: 1px solid rgba(31,122,107,0.34); color: #1f7a6b;
      font: 650 12px/1 ui-sans-serif, system-ui, sans-serif;
      letter-spacing: 0.16em; vertical-align: 3px;
    }
    .eyebrow {
      color: #657184;
      font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif;
      letter-spacing: .16em;
    }
    h1 {
      margin: 14px 0 8px;
      font-size: 40px;
      line-height: 1.18;
      font-weight: 700;
      letter-spacing: 0;
    }
    .meta {
      color: #657184;
      font: 14px/1.8 ui-sans-serif, system-ui, sans-serif;
    }
    section {
      margin-top: 34px;
      padding-top: 26px;
      border-top: 1px solid #ebe5da;
    }
    h2 { margin: 0; font-size: 22px; line-height: 1.35; }
    h3 { margin: 0; font-size: 18px; line-height: 1.5; }
    p {
      margin: 14px 0 0;
      color: #384556;
      font-size: 16px;
      line-height: 2;
      white-space: normal;
    }
    table { width: 100%; margin-top: 16px; border-collapse: collapse; font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; }
    th, td { border-top: 1px solid #ebe5da; padding: 10px 8px; text-align: left; vertical-align: top; }
    th { color: #657184; font-weight: 600; }
    .scope-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px 24px; margin-top: 18px; }
    .source-line { padding-left: 14px; border-left: 3px solid #ded8cc; }
    .chapter-question { color: #657184; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    .takeaway { color: #1f2933; font-weight: 600; }
    .claims { margin: 16px 0 0; padding-left: 22px; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .claims li { margin-top: 6px; }
    .evidence-strip { margin-top: 18px; color: #384556; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    .evidence-strip ul { margin: 8px 0 0; padding-left: 22px; }
    .scope-grid b, .scope-grid span { display: block; }
    .scope-grid b { color: #657184; font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .scope-grid span { margin-top: 6px; font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .evidence-card { margin-top: 18px; padding-left: 14px; border-left: 3px solid #ded8cc; }
    .evidence-card ul { margin: 12px 0 0; padding-left: 20px; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    blockquote { margin: 14px 0 0; padding-left: 14px; border-left: 3px solid #1f7a6b; color: #4b5565; font: 14px/1.8 ui-sans-serif, system-ui, sans-serif; }
    p strong, .action-paragraph strong { font-weight: 700; color: #1f2933; }

    /* graph snapshot */
    .orbit-export-section {
      margin-top: 34px; padding: 28px; border: 1px solid #ebe5da;
      border-radius: 24px; background: #fbf8f1;
    }
    .orbit-export-section h2 { margin-top: 4px; font-size: 28px; }
    .orbit-export-section p { max-width: 720px; }
    .orbit-export-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 24px; }
    .orbit-export-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; min-width: 320px; }
    .orbit-export-metrics div {
      border: 1px solid #ebe5da; border-radius: 14px; background: #fffdf8;
      padding: 12px 14px; text-align: center;
    }
    .orbit-export-metrics b { display: block; font: 700 26px/1.2 ui-sans-serif, system-ui, sans-serif; color: #1f2933; }
    .orbit-export-metrics span { display: block; margin-top: 4px; font: 12px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
    .orbit-export-wrap {
      position: relative; margin-top: 24px; min-height: 520px;
      border: 1px solid #ebe5da; border-radius: 22px; overflow: hidden; background: #fffdf8;
    }
    .orbit-export-svg { display: block; width: 100%; height: 520px; }
    .orbit-export-label {
      position: absolute; transform: translate(-50%, -50%);
      display: inline-flex; align-items: center; gap: 5px;
      max-width: 142px; padding: 4px 8px; border-radius: 999px;
      border: 1px solid #e3ded3; background: rgba(255,253,248,0.92);
      box-shadow: 0 2px 8px rgba(31,41,51,0.08);
      color: #384556; font: 600 12px/1.3 ui-sans-serif, system-ui, sans-serif;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    }
    .orbit-export-label em {
      flex: 0 0 auto; border-radius: 999px; padding: 1px 5px;
      font: 700 10px/1.3 ui-sans-serif, system-ui, sans-serif;
      background: rgba(31,122,107,0.10); color: #1f7a6b; font-style: normal;
    }
    .orbit-label-growth { border-color: rgba(185,130,45,0.34); }
    .orbit-label-story { border-color: rgba(143,138,128,0.28); }
    .orbit-label-risk { border-color: rgba(185,80,70,0.32); color: #6f403a; }
    .orbit-label-risk em { background: rgba(185,80,70,0.10); color: #b95046; }
    .orbit-export-footer {
      display: grid; grid-template-columns: minmax(0, 1fr) minmax(280px, 0.9fr);
      gap: 20px; margin-top: 18px; align-items: start;
    }
    .orbit-export-legend { display: flex; flex-wrap: wrap; gap: 10px; font: 13px/1.6 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .orbit-export-legend span {
      display: inline-flex; align-items: center; gap: 6px; border: 1px solid #ebe5da;
      border-radius: 999px; background: #fffdf8; padding: 5px 10px;
    }
    .orbit-export-legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; }
    .orbit-export-top {
      margin: 0; padding: 12px 16px; border: 1px solid #ebe5da; border-radius: 14px;
      background: #fffdf8; list-style: none; font: 13px/1.7 ui-sans-serif, system-ui, sans-serif;
    }
    .orbit-export-top li { display: flex; justify-content: space-between; gap: 12px; padding: 4px 0; border-top: 1px solid #f0ebe2; }
    .orbit-export-top li:first-child { border-top: 0; }
    .orbit-export-top span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .orbit-export-top b { color: #1f2933; }

    /* takeaway 高亮框 */
    .takeaway-box-green, .takeaway-box-green-strong, .takeaway-box-red {
      margin: 16px 0 0; padding: 14px 18px; border-left: 4px solid #1f7a6b;
      border-radius: 0 8px 8px 0; font: 600 17px/1.8 "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif;
    }
    .takeaway-box-green { background: rgba(31,122,107,0.08); color: #1f2933; }
    .takeaway-box-green-strong { background: rgba(31,122,107,0.18); color: #1f7a6b; }
    .takeaway-box-red { background: rgba(239,91,107,0.10); color: #ef5b6b; border-left-color: #ef5b6b; }

    /* persona card */
    .persona-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin: 16px 0 0; }
    .persona-card { background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 12px 14px; }
    .persona-name { font: 700 16px/1.4 ui-sans-serif, system-ui, sans-serif; margin-bottom: 6px; }
    .persona-desc { font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #1f2933; }
    .persona-data { margin-top: 8px; font: 12px/1.6 ui-sans-serif, system-ui, sans-serif; color: #657184; }

    /* action / problem card */
    .action-list { margin: 16px 0 0; display: flex; flex-direction: column; gap: 10px; }
    .problem-card { background: #fffdf8; border: 1px solid #ebe5da; border-left: 4px solid #ef5b6b; border-radius: 8px; padding: 12px 14px; display: flex; align-items: flex-start; gap: 10px; }
    .action-num { display: inline-flex; width: 28px; color: #b95046; font: 700 11px/1.7 ui-sans-serif, system-ui, sans-serif; letter-spacing: .14em; flex-shrink: 0; }
    .action-text { font: 14px/1.7 ui-sans-serif, system-ui, sans-serif; color: #384556; }
    .action-paragraph { margin: 12px 0 0; background: #fffdf8; border: 1px solid #ebe5da; border-left: 4px solid #1f7a6b; border-radius: 8px; padding: 12px 14px; font: 15px/1.8 "PingFang SC", "Microsoft YaHei", "Segoe UI", sans-serif; color: #384556; }

    /* metric card */
    .metric-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin: 16px 0 0; }
    .metric-card { background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 12px 14px; }
    .metric-label { font: 12px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
    .metric-value { font: 700 26px/1.2 ui-sans-serif, system-ui, sans-serif; color: #1f2933; margin-top: 4px; }
    .metric-value.val-red { color: #ef5b6b; }
    .metric-value.val-opportunity { color: var(--evidence-opportunity); }
    .metric-sub { margin-top: 4px; font: 12px/1.5 ui-sans-serif, system-ui, sans-serif; color: #657184; }

    /* bar chart */
    .bar-chart { margin: 16px 0 0; background: #fffdf8; border: 1px solid #ebe5da; border-radius: 10px; padding: 14px; }
    .bar-chart-title { font: 600 12px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
    .bar-chart-body { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
    .bar-row { display: flex; align-items: center; gap: 10px; font: 13px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .bar-label { width: 100px; flex-shrink: 0; text-align: right; color: #384556; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .bar-track { flex: 1; height: 20px; background: #f4eee2; border-radius: 4px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 4px; }
    .bar-value { width: 36px; flex-shrink: 0; text-align: right; font-weight: 700; color: #1f2933; }

    /* platform table */
    .platform-table { width: 100%; margin: 16px 0 0; border-collapse: collapse; font: 13px/1.6 ui-sans-serif, system-ui, sans-serif; }
    .platform-table th { background: #f4eee2; padding: 8px 10px; text-align: left; font-weight: 600; color: #657184; border-bottom: 1px solid #ebe5da; }
    .platform-table td { padding: 8px 10px; border-bottom: 1px solid #ebe5da; vertical-align: top; }
    .platform-table td.num { text-align: right; font-weight: 700; color: #1f2933; }
    .platform-tag { display: inline-block; padding: 2px 8px; border-radius: 4px; color: #fff; font: 700 12px/1.4 ui-sans-serif, system-ui, sans-serif; }

    /* quote tag */
    .quote-tag { display: inline-block; padding: 1px 6px; border-radius: 3px; color: #fff; font: 700 11px/1.4 ui-sans-serif, system-ui, sans-serif; }
    .quote-label { font: 600 11px/1.4 ui-sans-serif, system-ui, sans-serif; color: #657184; }
  </style>
</head>
<body>
  <main>
    <div class="eyebrow">Specta AI 品牌圈层报告</div>
    <h1>${escapeHtml(centerTerm)}品牌圈层解读报告</h1>
    <div class="meta">由平台回答解析结果生成。外围节点来自回答证据，战略词只作为解释背景。${periodScopeText ? `当前口径：${escapeHtml(periodScopeText)}。` : ''}</div>
    ${orbitSnapshotHtml}
    ${sectionHtml}
    ${periodChangeHtml}
    ${questionHtml}
    ${platformHtml}
    ${evidenceHtml}
    ${traceHtml}
    ${actionHtml}
    ${appendixHtml}
    ${qualityHtml}
  </main>
</body>
</html>`;
  if (
    /[\uE000-\uF8FF]/.test(html)
    || /(?:cite\s*)?(?:web[_\s-]?search|websearch|turn\d+[a-z]*|search\d+)[\s:=#-]*\d*/i.test(html)
    || /\b(?:web|eb|b|e)?[_\s-]?search\s*[:=#-]\s*\d+(?:\s*#\s*\d+)?\b/i.test(html)
  ) {
    throw new Error('报告导出已阻止：仍存在未清理的模型引用标记。');
  }
  const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${centerTerm}-brand-association-report.html`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}


function buildExportPeriodChangeHtml(periodView: Record<string, unknown> | null) {
  const rows = periodChangeRows(periodView);
  const notice = String(periodView?.comparison_notice || '').trim();
  const hasPreviousPeriod = Boolean(periodView?.previous_period);
  const previousScopeText = buildPreviousPeriodScopeText(periodView);
  if (!rows.length && !notice) return '';
  return `
    <section>
      <h2>${hasPreviousPeriod ? '相比上一周期，最该关注的变化' : '本周期基线说明'}</h2>
      ${notice ? `<p>${escapeHtml(notice)}</p>` : ''}
      ${previousScopeText ? `<p>对比周期：${escapeHtml(previousScopeText)}</p>` : ''}
      ${rows.length ? `
        <table>
          <thead><tr><th>节点</th><th>变化</th><th>提及</th><th>贴近</th><th>平台</th><th>说明</th></tr></thead>
          <tbody>
            ${rows.map((row) => `
              <tr>
                <td>${escapeHtml(String(row.term || '变化节点'))}</td>
                <td>${escapeHtml(periodChangeLabel(String(row.change_type || 'stable')))}</td>
                <td>${escapeHtml(signedNumber(row.mention_delta))}</td>
                <td>${escapeHtml(signedNumber(row.gravity_delta))}</td>
                <td>${escapeHtml(signedNumber(row.platform_delta))}</td>
                <td>${escapeHtml(String(row.explanation || ''))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      ` : ''}
    </section>
  `;
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function renderExportParagraphHtml(text: string, entities: string[]): string {
  const boldSplit = text.split(/\*\*(.+?)\*\*/g);
  const parts: string[] = [];
  boldSplit.forEach((segment, segmentIndex) => {
    if (!segment) return;
    if (segmentIndex % 2 === 1) {
      parts.push(`<strong>${escapeHtml(segment)}</strong>`);
      return;
    }
    if (!entities.length) {
      parts.push(escapeHtml(segment));
      return;
    }
    const pattern = new RegExp(`(${entities.map(escapeRegexValue).join('|')})`, 'g');
    const subParts = segment.split(pattern);
    subParts.forEach((sub) => {
      if (!sub) return;
      if (entities.includes(sub)) {
        parts.push(`<strong>${escapeHtml(sub)}</strong>`);
      } else {
        parts.push(escapeHtml(sub));
      }
    });
  });
  return parts.join('');
}
