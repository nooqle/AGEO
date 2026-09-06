/**
 * Orbit node insight panel UI (knife 4b, zero behavior).
 */

'use client';

import { useEffect, useRef, type ReactNode } from 'react';
import { semanticTypeLabels } from '../amwaySemanticLabels';
import { X } from 'lucide-react';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCircleSourceAppendixItem,
} from '@/types/ontology';
import { platformLabel } from './constants';
import {
  buildNodeEvidenceForPanel,
  buildPlatformEvidenceSummaries,
  cleanEvidenceExcerpt,
  distinctEvidenceQuestionCount,
  nodePlatformNames,
  platformTendencyText,
  sampleEvidenceAcrossPlatforms,
  sampleKey,
} from './evidenceHelpers';
import { classifyAssociationNode } from './mapGroups';
import {
  isCompetitorNode,
  nodeCountMetricLabel,
  nodeCountPhrase,
  nodeEvidenceCount,
  nodePlatformCount,
  scoreNumber,
} from './nodeMetrics';
import {
  nodeBrandImplicationText,
  nodeBrandRelationText,
  nodeEvidenceSummaryText,
  nodeOriginRead,
  nodeScoreBreakdown,
  orbitBandExplanationText,
  orbitDistanceBandChipStyle,
  orbitDistanceBandLabel,
  relationshipRead,
  riskRoutingExplanationText,
} from './nodeInsightCopy';
import { orbitDistanceBandForNode } from './orbitLayout';
import {
  sampleAnswerCount,
  sampleQuestionCount,
} from './projection';

export function OrbitNodeInsightPanel({
  node,
  centerTerm,
  evidenceSamples,
  evidenceFindings,
  sourceAppendix,
  strategyTerms,
  sampleScope,
  onClose,
}: {
  node: OntologyAssociationCircleNode | null;
  centerTerm: string;
  evidenceSamples: OntologyAssociationCircleEvidence[];
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  strategyTerms: string[];
  sampleScope: Record<string, unknown>;
  onClose: () => void;
}) {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);
  const selectedNodeId = node?.node_id;
  useEffect(() => {
    if (selectedNodeId) closeButtonRef.current?.focus();
  }, [selectedNodeId]);
  useEffect(() => {
    if (!node) return undefined;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [node, onClose]);
  if (!node) {
    return null;
  }
  const evidence = buildNodeEvidenceForPanel(node, evidenceSamples, sourceAppendix, evidenceFindings);
  const origin = nodeOriginRead(node, strategyTerms);
  const groupKey = classifyAssociationNode(node);
  const distanceBand = orbitDistanceBandForNode(groupKey, node);
  const questionCount = sampleQuestionCount(sampleScope);
  const totalAnswerCount = sampleAnswerCount(sampleScope);
  const mentionAnswerCount = nodeEvidenceCount(node) || evidence.length;
  const mentionCountPhrase = nodeCountPhrase(node, mentionAnswerCount);
  const relatedQuestionCount = distinctEvidenceQuestionCount(evidence);
  const platformNames = nodePlatformNames(node, evidence);
  const platformSummaries = buildPlatformEvidenceSummaries(node, evidence);
  const sampledEvidence = sampleEvidenceAcrossPlatforms(evidence, 4);
  const hasLargeEvidenceSet = mentionAnswerCount > 5;
  const scoreBreakdown = nodeScoreBreakdown(node);
  const finalClosenessScore = scoreNumber(
    node.closeness_score ?? node.association_score ?? node.gravity_score,
  );
  const rawClosenessScore = typeof node.raw_gravity_score === 'number'
    ? scoreNumber(node.raw_gravity_score)
    : null;
  const calibrationDelta = rawClosenessScore === null
    ? null
    : finalClosenessScore - rawClosenessScore;
  const competitionScoped = groupKey === 'risk' && isCompetitorNode(node);
  const riskScoped = groupKey === 'risk' && !competitionScoped;
  const usesContextPenalty = ['BrandStrategy', 'FourValue', 'FlowerDimension'].includes(String(node.entity_type || ''));
  return (
    <aside
      className="amway-node-insight-enter absolute inset-y-0 right-0 z-50 w-full max-w-[520px] overflow-hidden border-l border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-sm lg:w-[clamp(440px,36vw,520px)]"
      aria-label={`${node.term}节点解读`}
    >
      <div className="flex h-full min-h-0 flex-col">
        <div className="flex items-start justify-between gap-4 border-b border-[var(--border-subtle)] bg-[var(--bg-report)] px-5 py-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="rounded-full border px-2 py-1 text-xs font-medium"
                style={{
                  borderColor: origin.kind === 'strategy' ? 'var(--brand-border)' : 'var(--border-subtle)',
                  background: origin.kind === 'strategy' ? 'var(--brand-bg)' : 'var(--bg-secondary)',
                  color: origin.kind === 'strategy' ? 'var(--brand-primary)' : 'var(--text-secondary)',
                }}
              >
                {origin.label}
              </span>
              <span
                className="rounded-full border px-2 py-1 text-xs font-medium"
                style={competitionScoped ? {
                  borderColor: 'var(--border-subtle)',
                  background: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)',
                } : orbitDistanceBandChipStyle(distanceBand)}
              >
                {competitionScoped ? '竞品参照' : orbitDistanceBandLabel(distanceBand)}
              </span>
              <span className="text-xs text-[var(--text-tertiary)]">{relationshipRead(node).label}</span>
            </div>
            <h3 className="mt-2 truncate text-2xl font-semibold">{node.term}</h3>
          </div>
          <button
            ref={closeButtonRef}
            type="button"
            aria-label="关闭节点解读"
            onClick={onClose}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-tertiary)] hover:text-[var(--text-primary)]"
          >
            <X size={15} />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-1">
            <InsightLayer index="01" label="认知" title="关系意味着什么">
              <p>{nodeBrandRelationText(node, centerTerm, origin)}</p>
              <p className="mt-3 border-l-2 border-[var(--brand-primary)] pl-3 font-medium text-[var(--text-primary)]">
                {nodeBrandImplicationText(node, centerTerm, origin)}
              </p>
            </InsightLayer>

            <InsightLayer index="02" label="理知" title="如何计算并进入这条轨道">
              <p>{orbitBandExplanationText(node, distanceBand)}</p>
              {groupKey !== 'risk' ? (
                <>
                  <div className="mt-4 grid gap-2 rounded-lg bg-[var(--bg-secondary)] px-3 py-3 sm:grid-cols-[1fr_auto_1fr] sm:items-center">
                    <div>
                      <div className="text-xs text-[var(--text-tertiary)]">五项基础加权值</div>
                      <div className="mt-1 text-lg font-semibold tabular-nums text-[var(--text-primary)]">
                        {rawClosenessScore === null ? '历史数据未保存' : `${rawClosenessScore} / 100`}
                      </div>
                    </div>
                    <span className="hidden text-[var(--text-tertiary)] sm:inline" aria-hidden="true">→</span>
                    <div className="sm:text-right">
                      <div className="text-xs text-[var(--text-tertiary)]">语境与样本校准后贴近值</div>
                      <div className="mt-1 text-xl font-semibold tabular-nums text-[var(--brand-primary)]">
                        {finalClosenessScore} / 100
                      </div>
                      <div className="text-xs text-[var(--text-tertiary)]">
                        距离值 {scoreNumber(node.distance_score)}
                      </div>
                    </div>
                  </div>
                  <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
                    基础加权值 = 回答频率 30% + 回答位置 20% + 品牌关系 20% + 场景覆盖 15% + 平台一致性 15%。
                    {usesContextPenalty
                      ? '战略类节点随后按回答语境与低样本置信度校准，得到最终贴近值。'
                      : '该节点类型不使用语境惩罚；系统只在低样本时收紧置信度，语境计数用于解释而不直接改分。'}
                  </p>
                  <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                    {rawClosenessScore === null
                      ? '这份历史产物未保存基础分，因此不反推校准差值；最终轨道以当次后端产物为准。'
                      : `${usesContextPenalty ? '本次语境与样本校准差值' : '本次低样本校准差值'} ${calibrationDelta && calibrationDelta > 0 ? '+' : ''}${calibrationDelta || 0} 分；语境证据为支持 ${scoreNumber(node.supportive_evidence_count)}、质疑 ${scoreNumber(node.skeptical_evidence_count)}、风险 ${scoreNumber(node.risk_evidence_count)}、竞争 ${scoreNumber(node.competitive_evidence_count)} 条${usesContextPenalty ? '。' : '，仅用于解释。'}`}
                  </p>
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
                    {scoreBreakdown.map((item) => (
                      <div key={item.label} className="border-t border-[var(--border-subtle)] pt-2">
                        <div className="text-[11px] text-[var(--text-tertiary)]">{item.label} · {item.weight}</div>
                        <div className="mt-1 font-semibold tabular-nums text-[var(--text-primary)]">{item.value}</div>
                      </div>
                    ))}
                  </div>
                </>
              ) : (
                <div className="mt-4 rounded-lg bg-[var(--status-error-bg)] px-3 py-3 text-xs leading-5 text-[var(--text-secondary)]">
                  {riskRoutingExplanationText(node, sampledEvidence.length > 0)}
                </div>
              )}
            </InsightLayer>

            <InsightLayer index="03" label="感知" title="具体证据数据">
              {node.contribution_mode && <p className="mb-2 text-sm text-[var(--text-secondary)]">
                {node.contribution_label}：直接提及 {node.direct_answer_count || 0} 条回答，对象归组 {node.mapped_answer_count || 0} 条回答；两者重合 {node.overlap_answer_count || 0} 条，合计去重 {node.supporting_answer_count || 0} 条。
              </p>}
              {Boolean(node.topic_contributions?.length) && <details className="mb-3 text-sm">
                <summary>查看独立对象与主题贡献（同一回答只计一次）</summary>
                <div className="mt-2 divide-y divide-[var(--border-subtle)]">
                  {node.topic_contributions?.map((item, index) => <div key={`${item.entity_id}-${item.answer_id}-${index}`} className="py-2">
                    <p className="font-medium">{item.entity_name} · {item.platform} · {item.contribution_kind === 'direct' ? '直接提及' : '主题映射'}</p>
                    <p className="text-xs text-[var(--text-tertiary)]">{semanticTypeLabels[item.semantic_type || ''] || '旧版分类'} · 对象 ID：{item.entity_id}</p>
                    <p>当前回答证据：{item.evidence_text}</p>
                    {item.source_refs?.map((source, sourceIndex) => <p key={sourceIndex} className="text-xs text-[var(--text-secondary)]">对象文章来源：{source.source_id} / {source.locator}：“{source.quote}”</p>)}
                    {item.mapping_sources?.map((source, sourceIndex) => <p key={sourceIndex} className="text-xs text-[var(--text-tertiary)]">主题映射依据：{source.source_id} / {source.locator}：“{source.quote}”</p>)}
                  </div>)}
                </div>
              </details>}
              <p>
                {nodeEvidenceSummaryText({
                  term: node.term,
                  questionCount,
                  totalAnswerCount,
                  mentionAnswerCount,
                  node,
                  relatedQuestionCount,
                  platformNames,
                  riskScoped,
                  competitionScoped,
                })}
              </p>
              <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                <InsightMetric label="样本问题" value={String(questionCount || '-')} />
                <InsightMetric label={nodeCountMetricLabel(node)} value={String(mentionAnswerCount || '-')} />
                <InsightMetric label="覆盖平台" value={String(platformNames.length || nodePlatformCount(node) || '-')} />
              </div>
            </InsightLayer>
          </div>

          <div className="mt-4 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <div className="text-xs font-medium text-[var(--text-tertiary)]">平台倾向与抽样原文</div>
                <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
                  {hasLargeEvidenceSet
                    ? competitionScoped
                      ? `${mentionCountPhrase}将它作为竞争或替代参照，先看平台分布，再看每个平台的代表性片段。`
                      : riskScoped
                      ? `${mentionCountPhrase}形成质疑或风险语境，先看平台分布，再看每个平台的代表性片段。`
                      : `${mentionCountPhrase}，先看平台分布，再看每个平台的代表性片段。`
                    : '样本量较少，直接查看平台样例。'}
                </p>
              </div>
              <span className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-1 text-xs text-[var(--text-secondary)]">
                原文样例 {sampledEvidence.length} 个平台
              </span>
            </div>

            {platformSummaries.length ? (
              <div className="mt-4 grid grid-cols-2 gap-2">
                {platformSummaries.map((item) => (
                  <div key={item.platform} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
                    <div className="flex items-center justify-between gap-2">
                      <div className="text-sm font-semibold text-[var(--text-primary)]">{item.label}</div>
                      <div className="text-lg font-semibold text-[var(--brand-primary)]">{item.answerCount}</div>
                    </div>
                    <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
                      {platformTendencyText(item)}
                    </p>
                    <div className="mt-2 rounded-lg bg-[var(--bg-primary)] px-2 py-1 text-[11px] text-[var(--text-tertiary)]">
                      {item.samples.length ? '有可读原文样例' : '统计有提及，原文样例未收录'}
                    </div>
                  </div>
                ))}
              </div>
            ) : null}

            <div className="mt-5">
              <div className="text-xs font-medium text-[var(--text-tertiary)]">代表性原文（按平台去重）</div>
              {sampledEvidence.length ? (
                <div className="mt-2 grid gap-3 xl:grid-cols-2">
                  {sampledEvidence.map((item) => (
                    <blockquote
                      key={sampleKey(item)}
                      className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-3 text-xs leading-5 text-[var(--text-secondary)]"
                    >
                      <div className="mb-1 font-medium text-[var(--text-primary)]">
                        {platformLabel(item.platform || '')}
                      </div>
                      {item.question ? (
                        <p className="text-[var(--text-tertiary)]">问题：{cleanEvidenceExcerpt(item.question, 72)}</p>
                      ) : null}
                      <p className="mt-1">回答摘录：“{cleanEvidenceExcerpt(item.answer_excerpt, 160)}”</p>
                    </blockquote>
                  ))}
                </div>
              ) : (
                <p className="mt-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-xs leading-5 text-[var(--text-secondary)]">
                  当前历史报告只保留了这个词的计数和平台分布，没有保留可读原文。重新生成图谱后，系统会优先保留该节点的回答摘录。
                </p>
              )}
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}

export function InsightLayer({
  index,
  label,
  title,
  children,
}: {
  index: string;
  label: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="border-t border-[var(--border-subtle)] py-5 first:border-t-0">
      <div className="flex items-start gap-3">
        <span className="mt-0.5 w-7 shrink-0 text-[11px] font-semibold tabular-nums tracking-[0.14em] text-[var(--brand-primary)]">
          {index}
        </span>
        <div>
          <div className="text-[11px] font-semibold tracking-[0.16em] text-[var(--brand-primary)]">{label}</div>
          <h4 className="mt-1 text-base font-semibold text-[var(--text-primary)]">{title}</h4>
        </div>
      </div>
      <div className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{children}</div>
    </section>
  );
}

export function InsightMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2">
      <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
      <div className="mt-1 text-lg font-semibold">{value}</div>
    </div>
  );
}
