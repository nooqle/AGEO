/**
 * Pure map evidence / filter helpers for association-circle (knife 3, zero behavior).
 * Extracted from AmwayAssociationCircleDashboardViews.
 */

import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePriorityItem,
  OntologyAssociationCircleSourceAppendixItem,
} from '@/types/ontology';
import { platformLabel } from './constants';
import { classifyAssociationNode } from './mapGroups';
import {
  isCompetitorNode,
  nodeEvidenceCount,
  nodePlatformCount,
  scoreNumber,
} from './nodeMetrics';
import type {
  AssociationMapGroup,
  AssociationMapGroupKey,
  AssociationNodeFilterKey,
  AssociationNodeFilterOption,
  OrbitEvidenceItem,
  PlatformEvidenceSummary,
} from './types';

export function priorityItemsOrFallback(
  items: OntologyAssociationCirclePriorityItem[] | undefined,
  nodes: OntologyAssociationCircleNode[],
  focusType: OntologyAssociationCirclePriorityItem['focus_type'],
): OntologyAssociationCirclePriorityItem[] {
  if (Array.isArray(items) && items.length) {
    return items.slice(0, 3).map((item) => {
      const matchingNode = nodes.find((node) => (
        (item.node_id && node.node_id === item.node_id)
        || (item.term && node.term === item.term)
      ));
      if (!matchingNode) return item;
      return {
        ...item,
        evidence_count: nodeEvidenceCount(matchingNode),
        answer_refs: matchingNode.answer_refs,
        answer_count_is_exact: matchingNode.answer_count_is_exact,
        count_semantics: matchingNode.count_semantics,
      };
    });
  }
  return nodes.slice(0, 3).map((node, index) => ({
    rank: index + 1,
    node_id: node.node_id,
    term: node.term,
    focus_type: focusType,
    business_tag: node.business_tag,
    score: node.gravity_score || node.closeness_score || node.association_score,
    evidence_count: nodeEvidenceCount(node),
    answer_refs: node.answer_refs,
    answer_count_is_exact: node.answer_count_is_exact,
    count_semantics: node.count_semantics,
    platform_count: nodePlatformCount(node),
    scene_hint: (node.primary_opportunity_points || [])[0] || '',
    recommended_action: focusType === 'risk' ? '先看原文语境和澄清证据' : '补问题和证据',
  }));
}

export function priorityItemBrief(item: OntologyAssociationCirclePriorityItem): string {
  const scene = item.scene_hint ? `场景：${item.scene_hint}。` : '';
  const platform = item.platform_count ? `${item.platform_count} 个平台。` : '';
  const action = item.recommended_action || '点击查看原文语境。';
  return `${scene}${platform}${action}`;
}

export function cleanWorkflowProgressMessage(value?: string | null): string {
  const text = String(value || '').trim();
  if (!text) return '';
  return text
    .replace(/\s+/g, ' ')
    .replace(/^API抓取进度:\s*/i, 'API ')
    .replace(/完成（/g, '（')
    .replace(/完成\(/g, '(')
    .slice(0, 56);
}

export function buildAssociationNodeFilterOptions(
  groups: AssociationMapGroup[],
): AssociationNodeFilterOption[] {
  const nodes = groups.flatMap((group) => group.nodes.map((node) => ({ node, groupKey: group.key })));
  return [
    {
      key: 'stable',
      label: '稳定轨',
      hint: '回答已经较稳定绑定品牌',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['stable'])).length,
      tone: 'strong',
    },
    {
      key: 'opportunity',
      label: '机会轨',
      hint: '已有连接，还需要更多直接证据',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['opportunity'])).length,
      tone: 'growth',
    },
    {
      key: 'watch',
      label: '观察轨',
      hint: '远端机会或待观察词',
      count: nodes.filter(({ node, groupKey }) => nodePassesAssociationFilters(node, groupKey, ['watch'])).length,
      tone: 'story',
    },
  ];
}

export function nodePassesAssociationFilters(
  _node: OntologyAssociationCircleNode,
  groupKey: AssociationMapGroupKey | null,
  activeFilters: AssociationNodeFilterKey[],
): boolean {
  if (!activeFilters.length) return true;
  return activeFilters.some((filterKey) => {
    if (filterKey === 'stable') return groupKey === 'strong';
    if (filterKey === 'opportunity') return groupKey === 'growth';
    if (filterKey === 'watch') return groupKey === 'story';
    return false;
  });
}

export function trackFilterToGroupKey(track: AssociationNodeFilterKey | null): AssociationMapGroupKey | null {
  if (track === 'stable') return 'strong';
  if (track === 'opportunity') return 'growth';
  if (track === 'watch') return 'story';
  return null;
}

export function groupKeyToTrackFilter(groupKey: Exclude<AssociationMapGroupKey, 'risk'>): AssociationNodeFilterKey {
  if (groupKey === 'strong') return 'stable';
  if (groupKey === 'growth') return 'opportunity';
  return 'watch';
}

export function compactStrategyText(value?: string | null) {
  return String(value || '').replace(/\s+/g, '').trim();
}

export function buildPlatformEvidenceSummaries(
  node: OntologyAssociationCircleNode,
  evidence: OrbitEvidenceItem[],
): PlatformEvidenceSummary[] {
  const rows = new Map<string, PlatformEvidenceSummary>();
  const distribution = node.platform_distribution || {};
  const hasDistribution = Object.keys(distribution).length > 0;
  const ensureRow = (platform?: string): PlatformEvidenceSummary => {
    const label = platformLabel(platform || '');
    const key = label || '未知平台';
    const existing = rows.get(key);
    if (existing) return existing;
    const row = {
      platform: key,
      label: key,
      answerCount: 0,
      questionCount: 0,
      samples: [],
    };
    rows.set(key, row);
    return row;
  };

  Object.entries(distribution).forEach(([platform, count]) => {
    const row = ensureRow(platform);
    row.answerCount = scoreNumber(count);
  });

  evidence.forEach((item) => {
    const row = ensureRow(item.platform);
    if (!hasDistribution) row.answerCount += 1;
    if (!row.samples.some((sample) => sampleKey(sample) === sampleKey(item))) {
      row.samples.push(item);
    }
  });

  rows.forEach((row) => {
    row.questionCount = distinctEvidenceQuestionCount(row.samples);
  });

  return Array.from(rows.values())
    .filter((row) => row.answerCount > 0 || row.samples.length > 0)
    .sort((a, b) => b.answerCount - a.answerCount || a.label.localeCompare(b.label, 'zh-Hans'));
}

export function platformTendencyText(item: PlatformEvidenceSummary) {
  const questionText = item.questionCount ? `，样例覆盖 ${item.questionCount} 个问题` : '';
  if (item.answerCount >= 20) {
    return `高频提及${questionText}，该平台容易把这个词放进核心回答路径。`;
  }
  if (item.answerCount >= 6) {
    return `多次提及${questionText}，已经形成可观察的平台倾向。`;
  }
  if (item.answerCount > 0) {
    return `少量提及${questionText}，需要结合样例语境继续观察。`;
  }
  return `当前只有样例摘录，缺少稳定计数。`;
}

export function sampleEvidenceAcrossPlatforms(evidence: OrbitEvidenceItem[], limit: number) {
  const selected: OrbitEvidenceItem[] = [];
  const usedPlatforms = new Set<string>();
  const usedSamples = new Set<string>();
  const addSample = (item: OrbitEvidenceItem) => {
    const key = sampleKey(item);
    if (usedSamples.has(key)) return;
    const platform = platformLabel(item.platform || '');
    if (usedPlatforms.has(platform)) return;
    selected.push(item);
    usedSamples.add(key);
    usedPlatforms.add(platform);
  };

  for (const item of evidence) {
    const platform = platformLabel(item.platform || '');
    if (usedPlatforms.has(platform)) continue;
    addSample(item);
    if (selected.length >= limit) return selected;
  }
  return selected;
}

export function sampleKey(item: OrbitEvidenceItem) {
  return [
    platformLabel(item.platform || ''),
    String(item.question_id || '').trim(),
    cleanEvidenceExcerpt(item.question, 80),
    cleanEvidenceExcerpt(item.answer_excerpt, 120),
  ].join('|');
}

export function buildLiveExtractionStreamSamples(
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[],
  evidenceSamples: OntologyAssociationCircleEvidence[],
): OrbitEvidenceItem[] {
  const rows: OrbitEvidenceItem[] = [];
  const used = new Set<string>();
  const append = (item: OrbitEvidenceItem) => {
    const key = sampleKey(item);
    if (used.has(key)) return;
    if (!item.node_term && !item.answer_excerpt) return;
    rows.unshift(item);
    used.add(key);
  };

  sourceAppendix.forEach((item) => append({
    evidence_id: item.evidence_id,
    entity_id: item.entity_id,
    lexicon_entity_id: item.lexicon_entity_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
    relation_type: item.relation_type,
    context_polarity: item.context_polarity,
  }));
  evidenceSamples.forEach((item) => append({
    evidence_id: item.evidence_id,
    entity_id: item.entity_id,
    lexicon_entity_id: item.lexicon_entity_id,
    node_id: item.node_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
  }));

  return rows;
}

export function buildNodeEvidenceForPanel(
  node: OntologyAssociationCircleNode,
  evidenceSamples: OntologyAssociationCircleEvidence[],
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[],
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[],
): OrbitEvidenceItem[] {
  const evidenceRefSet = new Set(
    [...(node.evidence_samples || []), ...(node.evidence_refs || [])]
      .map((item) => String(item || '').trim())
      .filter(Boolean),
  );
  const sourceItems = sourceAppendix.map((item): OrbitEvidenceItem => ({
    evidence_id: item.evidence_id,
    entity_id: item.entity_id,
    lexicon_entity_id: item.lexicon_entity_id,
    node_term: item.node_term,
    platform: item.platform,
    question_id: item.question_id,
    question: item.question,
    answer_excerpt: item.answer_excerpt,
    relation_type: item.relation_type,
    context_polarity: item.context_polarity,
  }));
  const findingItems = evidenceFindings
    .filter((item) => evidenceFindingMatchesNode(item, node, evidenceRefSet))
    .map((item, index): OrbitEvidenceItem => ({
      evidence_id: item.evidence_refs?.[0] || `${node.node_id}-finding-${index}`,
      node_id: item.node_id,
      node_term: item.node_term,
      platform: item.sample_platform,
      question: item.sample_question,
      answer_excerpt: item.sample_excerpt,
    }))
    .filter((item) => evidenceItemMatchesNode(item, node, evidenceRefSet));
  const matched = [
    ...evidenceSamples.filter((item) => evidenceItemMatchesNode(item, node, evidenceRefSet)),
    ...sourceItems.filter((item) => evidenceItemMatchesNode(item, node, evidenceRefSet)),
    ...findingItems,
  ].filter((item) => String(item.answer_excerpt || '').trim());
  const scopedMatched = node.entity_id === 'evidence_regulation' && classifyAssociationNode(node) === 'risk'
    ? matched.filter((item) => (
        item.relation_type === 'RISKS_AS'
        || item.context_polarity === 'negative'
        || evidenceMatchesControlledRiskCue(item, node)
      ))
    : matched;

  const seen = new Set<string>();
  return scopedMatched.filter((item) => {
    const key = sampleKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function evidenceItemMatchesNode(
  item: OrbitEvidenceItem,
  node: OntologyAssociationCircleNode,
  evidenceRefSet: Set<string>,
) {
  const itemId = String(item.evidence_id || '').trim();
  const nodeTerm = compactStrategyText(node.term);
  const itemTerm = compactStrategyText(item.node_term);
  const nodeEntityId = String(node.entity_id || '').trim();
  const itemEntityIds = [item.entity_id, item.lexicon_entity_id]
    .map((value) => String(value || '').trim())
    .filter(Boolean);
  const hasExplicitIdentityConflict = Boolean(
    (item.node_id && item.node_id !== node.node_id)
    || (nodeEntityId && itemEntityIds.length > 0 && !itemEntityIds.includes(nodeEntityId))
    || (nodeTerm && itemTerm && nodeTerm !== itemTerm),
  );
  const refBound = Boolean(itemId && evidenceRefSet.has(itemId));
  const nodeIdentityBound = Boolean(item.node_id && item.node_id === node.node_id);
  const entityIdentityBound = Boolean(nodeEntityId && itemEntityIds.includes(nodeEntityId));
  const termAndRefBound = Boolean(nodeTerm && itemTerm && nodeTerm === itemTerm && refBound);
  const textMentionsNode = evidenceTextMentionsNode(item, node);
  if (textMentionsNode) return true;
  if (hasExplicitIdentityConflict) return false;
  if (RISK_EVIDENCE_PATTERNS[nodeEntityId]) {
    return Boolean(
      (nodeIdentityBound || entityIdentityBound || termAndRefBound || refBound)
      && evidenceMatchesControlledRiskCue(item, node),
    );
  }
  if (isCompetitorNode(node)) return false;
  return nodeIdentityBound || entityIdentityBound || termAndRefBound;
}

export const RISK_EVIDENCE_PATTERNS: Record<string, RegExp> = {
  evidence_regulation: /(监管|合规|政策|法规|法律|违法|违规|处罚|许可|投诉|直销模式|风险库存|库存风险)/,
  risk_pyramid_scheme: /(传销|拉人头|发展下线|发展团队|团队招募|依赖招募|入门费|层级计酬|多层分销)/,
  risk_exaggerated_claim: /(夸大|虚假宣传|神奇功效|包治|治愈|慢病功效)/,
  risk_over_selling: /(过度推销|强行推荐|逼单|囤货|库存压力|频繁推销)/,
  risk_high_price: /(高价|价格高|大额囤货|付费培训|溢价|性价比)/,
  risk_iq_tax: /(智商税|人情成本|销售费用|附加成本)/,
};

export function evidenceMatchesControlledRiskCue(
  item: OrbitEvidenceItem,
  node: OntologyAssociationCircleNode,
) {
  const pattern = RISK_EVIDENCE_PATTERNS[String(node.entity_id || '').trim()];
  if (!pattern) return false;
  return pattern.test(`${item.question || ''}${item.answer_excerpt || ''}`);
}

export function evidenceTextMentionsNode(
  item: OrbitEvidenceItem,
  node: OntologyAssociationCircleNode,
) {
  const text = compactStrategyText(`${item.question || ''}${item.answer_excerpt || ''}`);
  if (!text) return false;
  const aliases = String(node.term || '')
    .split(/[\/／、|｜,，()（）]/)
    .map((value) => compactStrategyText(value))
    .filter((value) => value.length >= 2);
  const fullTerm = compactStrategyText(node.term);
  if (fullTerm) aliases.unshift(fullTerm);
  return Array.from(new Set(aliases)).some((alias) => text.includes(alias));
}

export function evidenceFindingMatchesNode(
  item: OntologyAssociationCircleEvidenceFinding,
  node: OntologyAssociationCircleNode,
  evidenceRefSet: Set<string>,
) {
  if (item.node_id && item.node_id === node.node_id) return true;
  const nodeTerm = compactStrategyText(node.term);
  const itemTerm = compactStrategyText(item.node_term);
  if (nodeTerm && itemTerm && nodeTerm === itemTerm) return true;
  return Boolean(item.evidence_refs?.some((ref) => evidenceRefSet.has(String(ref || '').trim())));
}

export function distinctEvidenceQuestionCount(evidence: OrbitEvidenceItem[]) {
  const keys = evidence
    .map((item) => item.question_id || item.question)
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  return new Set(keys).size;
}

export function nodePlatformNames(
  node: OntologyAssociationCircleNode,
  evidence: OrbitEvidenceItem[],
) {
  const fromEvidence = evidence.map((item) => item.platform).filter(Boolean) as string[];
  const fromDistribution = Object.keys(node.platform_distribution || {});
  return Array.from(new Set(
    [...fromEvidence, ...fromDistribution]
      .map((platform) => platformLabel(platform))
      .filter(Boolean),
  )).slice(0, 4);
}

export function cleanEvidenceExcerpt(value?: string, maxLength = 180) {
  const text = String(value || '证据摘录待补充。')
    .replace(/[\u{1F300}-\u{1FAFF}]/gu, '')
    .replace(/[\uE000-\uF8FF]+(?:ci(?:te)?|web[_\s-]?search|websearch|turn\d+[a-z]*|search\d+)(?:[\uE000-\uF8FF]|[\w:=#./-]){0,160}/gi, '')
    .replace(/[\uE000-\uF8FF]/g, '')
    .replace(/(?:cite\s*)?(?:web[_\s-]?search|websearch|turn\d+[a-z]*|search\d+)[\s:=#-]*\d*/gi, '')
    .replace(/\b(?:web|eb|b|e)?[_\s-]?search\s*[:=#-]\s*\d+(?:\s*#\s*\d+)?\b/gi, '')
    .replace(/(?:ci(?:te)?|web[_-]?search|turn\d+[a-z]*|search\d+)[\w:=#./-]*\s*$/gi, '')
    .replace(/[#*_`>|[\]()]/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
}
