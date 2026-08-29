/**
 * Association-circle report section UI components (knife 6a, zero behavior).
 */

'use client';

import type { ReactNode } from 'react';
import type {
  OntologyAssociationCircleBlindSpotMetrics,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePlatformSourceSummary,
  OntologyAssociationCircleQuestion,
  OntologyAssociationCircleQuestionDefinition,
  OntologyAssociationCircleSourceAppendixItem,
  OntologyAssociationCircleStrategyPillar,
  OntologyAssociationCircleStrategyStoryline,
  OntologyAssociationCircleStrategyValidation,
  OntologyAssociationCircleStorylineAnalysis,
} from '@/types/ontology';
import { platformLabel } from './constants';
import { cleanEvidenceExcerpt, commercialReportCopy } from './evidenceHelpers';
import {
  buildPreviousPeriodScopeText,
  buildReportEntityTerms,
  evidenceFindingCopy,
  escapeRegexValue,
  parseReportEvidenceLine,
  periodChangeLabel,
  periodChangeRows,
  reportEvidenceLine,
  reportPlatformAccent,
  signedNumber,
  uniqueEvidenceFindingFacts,
} from './reportCopy';
import {
  buildCoreVerdictMetrics,
  buildNodeFrequencyBars,
  nodeFrequencyChartTitle,
  reportBarToneColor,
} from './reportNarrative';
import { buildStrategyValidationRows } from './strategyValidation';
import type {
  AssociationMapGroup,
  NodeFrequencyBarItem,
  ReportNarrativeSection,
} from './types';

export function ReportPeriodChangeSummary({
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

export function StrategyValidationSection({
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

export function renderParagraphWithBoldEntities(text: string, entities: string[]) {
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

export function ReportSection({
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
  const isLivingYoungAutonomy = section.sectionId === 'living_young_autonomy';

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
      {isLivingYoungAutonomy && section.claims?.length ? (
        <ReportAutonomyPathCards claims={section.claims} />
      ) : actionClaims?.length ? (
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

function ReportAutonomyPathCards({ claims }: { claims: string[] }) {
  const paths = claims.slice(0, 3).map((claim, index) => {
    const [label, status, ...detailParts] = claim.split('｜').map((part) => part.trim());
    return {
      index,
      label: label || `自主路径 ${index + 1}`,
      status: status || '待验证',
      detail: detailParts.join('｜') || '本轮尚未形成可核验的品牌连接。',
    };
  });
  const connectionJudgment = claims[3]?.trim();

  return (
    <div className="mt-6">
      <ol className="grid list-none gap-3 p-0 md:grid-cols-3" aria-label="活得年轻品牌主张的三条自主路径">
        {paths.map((path) => {
          const isEstablished = /已形成|已接住|较稳定/.test(path.status);
          return (
            <li
              key={`${path.label}-${path.index}`}
              className="min-w-0 rounded-xl border border-[var(--border-subtle)] border-t-[3px] border-t-[var(--brand-primary)] bg-[var(--bg-primary)] px-4 py-4"
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold tabular-nums tracking-[0.14em] text-[var(--brand-primary)]">
                    {String(path.index + 1).padStart(2, '0')}
                  </div>
                  <h4 className="report-font mt-1 text-lg font-semibold text-[var(--text-primary)]">
                    {path.label}
                  </h4>
                </div>
                <span className={`shrink-0 rounded-lg px-2 py-1 text-[11px] font-semibold ${isEstablished ? 'bg-[var(--brand-bg)] text-[var(--brand-text)]' : 'bg-[var(--status-warning-bg)] text-[var(--text-secondary)]'}`}>
                  {path.status}
                </span>
              </div>
              <p className="mt-3 break-words text-sm leading-7 text-[var(--text-secondary)]">
                {path.detail}
              </p>
            </li>
          );
        })}
      </ol>
      {connectionJudgment ? (
        <p className="mt-4 border-y border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-sm leading-7 text-[var(--text-primary)]">
          {connectionJudgment}
        </p>
      ) : null}
    </div>
  );
}

export function ReportMetricRow({ metrics }: { metrics: Array<{ label: string; value: string; sub?: string; tone?: 'default' | 'risk' | 'opportunity' }> }) {
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

export function ReportBarChart({ items }: { items: NodeFrequencyBarItem[] }) {
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

export function ReportActionCards({ claims, tone = 'action' }: { claims: string[]; tone?: 'problem' | 'action' }) {
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

export function ReportPersonaClaimCards({ claims }: { claims: string[] }) {
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

export function ReportBlindSpotTable({ metrics }: { metrics?: OntologyAssociationCircleBlindSpotMetrics }) {
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

export function ReportFourHaveMetricCards({
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

export function ReportPlatformEvaluationTable({ claims }: { claims: string[] }) {
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

export function renderAnswerMarkdown(text: string) {
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

export function ReportEvidenceSamples({ quotes }: { quotes: string[] }) {
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

export function ReportEvidenceBrief({
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
