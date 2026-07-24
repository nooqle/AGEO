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
  ReportPlatformEvaluationTable,
  ReportFourHaveMetricCards,
  ReportBlindSpotTable,
  ReportPersonaClaimCards,
  ReportActionCards,
  ReportBarChart,
  ReportMetricRow,
  renderAnswerMarkdown,
  renderParagraphWithBoldEntities,
  ReportEvidenceBrief,
  ReportEvidenceSamples,
  ReportSection,
  StrategyValidationSection,
  ReportPeriodChangeSummary,
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
  cleanEvidenceExcerpt,
  clampNumber,
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
