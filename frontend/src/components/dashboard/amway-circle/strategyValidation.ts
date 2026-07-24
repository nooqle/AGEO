/**
 * Pure strategy-validation helpers for association-circle reports (knife 5, zero behavior).
 */

import type {
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePlatformSourceSummary,
  OntologyAssociationCircleQuestion,
  OntologyAssociationCircleSourceAppendixItem,
  OntologyAssociationCircleStrategyValidation,
} from '@/types/ontology';
import {
  cleanEvidenceExcerpt,
  commercialReportCopy,
  uniqueStrings,
} from './evidenceHelpers';
import {
  isCompetitorNode,
  nodeClosenessValue,
  nodeCountPhrase,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
  scoreNumber,
} from './nodeMetrics';
import { relationshipRead } from './nodeInsightCopy';
import type { NodeCountSource, StrategyValidationRow } from './types';

export function buildStrategyValidationRows({
  strategyValidation,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  const backendRows = buildBackendStrategyValidationRows({
    strategyValidation,
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
  if (backendRows.length) return backendRows;
  return buildFallbackStrategyValidationRows({
    questionBank,
    nodes,
    sourceAppendix,
    platformSourceSummary,
  });
}

export function buildBackendStrategyValidationRows({
  strategyValidation,
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  strategyValidation: OntologyAssociationCircleStrategyValidation[];
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  if (!Array.isArray(strategyValidation) || !strategyValidation.length) return [];
  const nodesById = new Map(nodes.map((node) => [node.node_id, node]));
  const questionsById = new Map(
    questionBank
      .map((question) => [String(question.id || '').trim(), question] as const)
      .filter(([id]) => Boolean(id)),
  );
  const platformNames = uniqueStrings([
    ...(platformSourceSummary?.platform_names || []),
    ...((platformSourceSummary?.platforms || []).map((row) => row.platform || '')),
    ...sourceAppendix.map((item) => item.platform || ''),
  ]);

  return strategyValidation.slice(0, 12).map((row) => {
    const term = String(row.strategy_term || '').trim() || '未命名战略词';
    const relatedNodes = (row.related_node_ids || [])
      .map((id) => nodesById.get(String(id || '').trim()))
      .filter((item): item is OntologyAssociationCircleNode => Boolean(item));
    const evidenceQuestionIds = uniqueStrings(
      relatedNodes.flatMap((node) => (node.trigger_questions || []).map((id) => String(id || '').trim())),
    );
    const displayQuestionIds = evidenceQuestionIds.length
      ? evidenceQuestionIds
      : uniqueStrings((row.question_refs || []).map((id) => String(id || '').trim()));
    const relatedQuestions = displayQuestionIds
      .map((id) => questionsById.get(id))
      .filter((item): item is OntologyAssociationCircleQuestion => Boolean(item));
    const platformMentions = buildBackendPlatformMentions(row, platformNames);
    const status = normalizeStrategyStatus(row.status, relatedNodes);
    return {
      term,
      status,
      statusLabel: String(row.validation_label || '').trim() || strategyStatusLabel(status),
      validationLabel: String(row.validation_label || '').trim() || undefined,
      decisionTier: String(row.decision_tier || '').trim() || undefined,
      stanceSummary: row.stance_summary,
      intent: strategyIntentText(term),
      questionCount: displayQuestionIds.length || Number(row.question_count || 0),
      relatedQuestions,
      relatedNodes,
      platformNames,
      platformMentions,
      answerResult: strategyAnswerResultText({
        answerMentionCount: Number(row.answer_mention_count || 0),
        platformCount: Number(row.platform_count || 0),
        platformMentions,
        countSource: row,
      }),
      graphPerformance: strategyGraphPerformanceText(relatedNodes),
      implication: strategyImplication(term, status, relatedNodes, Number(row.platform_count || 0), row),
      actionRecommendation: strategyActionRecommendationText(
        String(row.action_recommendation || '').trim(),
        term,
        status,
        relatedNodes,
        Number(row.platform_count || 0),
        row,
      ),
      evidenceRefs: Array.isArray(row.evidence_refs) ? row.evidence_refs : [],
    };
  });
}

export function buildFallbackStrategyValidationRows({
  questionBank,
  nodes,
  sourceAppendix,
  platformSourceSummary,
}: {
  questionBank: OntologyAssociationCircleQuestion[];
  nodes: OntologyAssociationCircleNode[];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
}): StrategyValidationRow[] {
  const questionsById = new Map(
    questionBank
      .map((question) => [String(question.id || '').trim(), question] as const)
      .filter(([id]) => Boolean(id)),
  );
  const fallbackPlatforms = uniqueStrings([
    ...(platformSourceSummary?.platform_names || []),
    ...((platformSourceSummary?.platforms || []).map((row) => row.platform || '')),
    ...sourceAppendix.map((item) => item.platform || ''),
  ]);
  const strategyNodes = nodes
    .filter((node) => isStrategyNode(node))
    .sort((left, right) => nodeClosenessValue(right) - nodeClosenessValue(left))
    .slice(0, 12);

  return strategyNodes.map((node) => {
    const evidenceRows = sourceAppendix.filter(
      (item) => commercialReportCopy(item.node_term) === commercialReportCopy(node.term),
    );
    const relatedQuestionIds = uniqueStrings([
      ...((node.trigger_questions || []).map((id) => String(id || ''))),
      ...evidenceRows.map((item) => item.question_id || ''),
    ]);
    const relatedQuestions = relatedQuestionIds
      .map((id) => questionsById.get(id))
      .filter((item): item is OntologyAssociationCircleQuestion => Boolean(item));
    const platformDistribution = node.platform_distribution || {};
    const platformMentions = buildFallbackPlatformMentions({
      distribution: platformDistribution,
      evidenceRows,
      fallbackPlatforms,
    });
    const platformCount = Number(node.platform_count || Object.keys(platformDistribution).length || 0);
    const answerMentionCount = Number(node.answer_count || node.evidence_count || evidenceRows.length || 0);
    const relatedNodes = [node];
    const status = normalizeStrategyStatus(undefined, relatedNodes);
    return {
      term: node.term || '未命名战略词',
      status,
      statusLabel: strategyStatusLabel(status),
      intent: strategyIntentText(node.term || ''),
      questionCount: relatedQuestionIds.length || relatedQuestions.length,
      relatedQuestions,
      relatedNodes,
      platformNames: fallbackPlatforms,
      platformMentions,
      answerResult: strategyAnswerResultText({
        answerMentionCount,
        platformCount,
        platformMentions,
        countSource: node,
      }),
      graphPerformance: strategyGraphPerformanceText(relatedNodes),
      implication: strategyImplication(node.term || '', status, relatedNodes, platformCount),
      actionRecommendation: strategyActionRecommendationText(
        '',
        node.term || '',
        status,
        relatedNodes,
        platformCount,
      ),
      evidenceRefs: Array.isArray(node.evidence_samples) ? node.evidence_samples : [],
    };
  });
}

export function isStrategyNode(node: OntologyAssociationCircleNode): boolean {
  const originText = `${node.term_origin || ''} ${node.origin_label || ''} ${node.business_tag || ''}`;
  return Boolean(
    node.term
      && !node.is_risk_term
      && (
        node.is_target_term
        || node.term_origin === 'strategy'
        || /战略词|目标心智|战略验证/.test(originText)
      ),
  );
}

export function buildFallbackPlatformMentions({
  distribution,
  evidenceRows,
  fallbackPlatforms,
}: {
  distribution: Record<string, number>;
  evidenceRows: OntologyAssociationCircleSourceAppendixItem[];
  fallbackPlatforms: string[];
}): string[] {
  const rowsByPlatform = new Map<string, OntologyAssociationCircleSourceAppendixItem[]>();
  evidenceRows.forEach((item) => {
    const platform = String(item.platform || '').trim();
    if (!platform) return;
    const rows = rowsByPlatform.get(platform) || [];
    rows.push(item);
    rowsByPlatform.set(platform, rows);
  });
  const platformNames = uniqueStrings([
    ...Object.keys(distribution || {}),
    ...Array.from(rowsByPlatform.keys()),
    ...fallbackPlatforms,
  ]);
  return platformNames.slice(0, 6).map((platform) => {
    const count = Number(distribution?.[platform] || rowsByPlatform.get(platform)?.length || 0);
    const sample = rowsByPlatform.get(platform)?.find((item) => item.answer_excerpt)?.answer_excerpt || '';
    if (sample && count > 0) {
      return `${platform}提及 ${count} 次，代表摘录：“${cleanEvidenceExcerpt(sample, 64)}”`;
    }
    return count > 0 ? `${platform}提及 ${count} 次` : `${platform}暂未形成稳定提及`;
  });
}

export function buildBackendPlatformMentions(
  row: OntologyAssociationCircleStrategyValidation,
  fallbackPlatforms: string[],
): string[] {
  const outcomes = Array.isArray(row.platform_outcomes) ? row.platform_outcomes : [];
  if (outcomes.length) {
    return outcomes.map((item) => {
      const platform = String(item.platform || '').trim() || '未知平台';
      const count = Number(item.answer_count || 0);
      const excerpt = String(item.sample_excerpt || '').trim();
      const stanceText = strategyStanceLabel(item.stance);
      const mentionText = count > 0 ? `${platform}${stanceText} ${count} 次` : `${platform}暂未形成稳定提及`;
      return excerpt
        ? `${mentionText}，样本：“${cleanEvidenceExcerpt(excerpt, 72)}”`
        : mentionText;
    });
  }
  const distribution = row.platform_distribution || {};
  const platforms = uniqueStrings([...Object.keys(distribution), ...fallbackPlatforms]);
  return platforms.slice(0, 6).map((platform) => {
    const count = Number(distribution[platform] || 0);
    return count > 0 ? `${platform}提及 ${count} 次` : `${platform}暂未形成稳定提及`;
  });
}

export function normalizeStrategyStatus(
  status: OntologyAssociationCircleStrategyValidation['status'],
  relatedNodes: OntologyAssociationCircleNode[],
): StrategyValidationRow['status'] {
  if (relatedNodes.some((node) => node.is_risk_term)) return 'risk';
  if (status === 'validated') return 'validated';
  if (status === 'partial') return 'partial';
  if (status === 'missing') return 'missing';
  if (status === 'risk') return 'risk';
  return relatedNodes.length ? 'partial' : 'missing';
}

export function strategyStatusLabel(status: StrategyValidationRow['status']): string {
  if (status === 'validated') return '已被回答接住';
  if (status === 'partial') return '部分验证';
  if (status === 'risk') return '被风险遮蔽';
  return '尚未验证';
}

export function strategyStanceLabel(stance?: string): string {
  if (stance === 'supportive') return '正向提及';
  if (stance === 'skeptical') return '质疑提及';
  if (stance === 'risk') return '风险提醒';
  if (stance === 'competitive') return '竞品替代';
  if (stance === 'neutral') return '中性提及';
  return '提及';
}

export function strategyIntentText(term: string): string {
  if (/健康|抗衰|长寿|百岁|营养/.test(term)) {
    return '让品牌从产品认知进入长期健康管理和人生周期支持。';
  }
  if (/陪伴|关系|社群|一起/.test(term)) {
    return '让品牌承担关系连接、社群支持和持续陪伴的心智角色。';
  }
  if (/人生|价值|再出发|安利人|成长/.test(term)) {
    return '让品牌连接个人成长、角色转换和重新被需要的生活叙事。';
  }
  return '让这个词成为平台回答可以自然带回品牌的目标心智。';
}

export function strategyAnswerResultText({
  answerMentionCount,
  platformCount,
  platformMentions,
  countSource,
}: {
  answerMentionCount: number;
  platformCount?: number;
  platformMentions: string[];
  countSource: NodeCountSource;
}): string {
  const summary = `${nodeCountPhrase(countSource, answerMentionCount)}，覆盖 ${platformCount ?? 0} 个平台。`;
  return platformMentions.length ? `${summary}${platformMentions.join('；')}` : summary;
}

export function strategyGraphPerformanceText(nodes: OntologyAssociationCircleNode[]): string {
  if (!nodes.length) return '图谱上还没有形成稳定节点。';
  return nodes.slice(0, 4).map((node) => (
    `${node.term}位于${relationshipRead(node).label}，距离值 ${nodeDistanceValue(node)}，${nodeCountPhrase(node, nodeEvidenceCount(node))}，覆盖 ${nodePlatformCount(node)} 个平台`
  )).join('；');
}

export function strategyImplication(
  term: string,
  status: StrategyValidationRow['status'],
  nodes: OntologyAssociationCircleNode[],
  platformCount: number,
  backendRow?: OntologyAssociationCircleStrategyValidation,
): string {
  const nodeText = nodes.length ? nodes.slice(0, 3).map((node) => node.term).join('、') : '稳定节点';
  const stance = backendRow?.stance_summary || {};
  const supportive = Number(stance.supportive || 0);
  const skeptical = Number(stance.skeptical || 0);
  const riskLike = Number(stance.risk || 0) + Number(stance.competitive || 0);
  const evidenceCount = Number(backendRow?.answer_mention_count || 0);
  const countSource = backendRow || nodes[0] || {};
  const tier = backendRow?.decision_tier || '';
  const lane = strategyLane(term);
  const focus = strategyMeaningFocus(term, lane, tier, status);
  if (tier === 'amplify' || (status === 'validated' && supportive >= 30)) {
    return `${term}已有 ${nodeCountPhrase(countSource, supportive || evidenceCount)}正向支撑，覆盖 ${platformCount} 个平台，并通过${nodeText}回到品牌。${focus}`;
  }
  if (tier === 'risk_first' || status === 'risk') {
    return `${term}当前有 ${nodeCountPhrase(countSource, riskLike || evidenceCount)}风险或竞品替代语境。${focus}`;
  }
  if (tier === 'evidence_building' || status === 'partial') {
    const cautionText = skeptical || riskLike ? `同时出现 ${nodeCountPhrase(countSource, skeptical + riskLike)}质疑或风险语境，` : '';
    return `${term}已经有 ${nodeCountPhrase(countSource, evidenceCount)}线索，${cautionText}${focus}`;
  }
  return `${term}在本轮问题里被测试过，回答证据仍不足。${focus}`;
}

export function strategyLane(term: string): 'relationship' | 'career' | 'green' | 'health' | 'general' {
  if (/财务|保障|事业|安利人|价值|再出发|成长/.test(term)) return 'career';
  if (/关系|陪伴|社群|一起/.test(term)) return 'relationship';
  if (/绿色|和谐|环境/.test(term)) return 'green';
  if (/健康|抗衰|长寿|活力|营养|身体|情绪|大健康/.test(term)) return 'health';
  return 'general';
}

export function strategyMeaningFocus(
  term: string,
  lane: ReturnType<typeof strategyLane>,
  tier: string,
  status: StrategyValidationRow['status'],
) {
  if (tier === 'amplify' || status === 'validated') {
    return ({
      relationship: '关系陪伴已经被平台理解，下一步要补社群边界、真实陪伴案例和弱销售压力表达。',
      career: '事业与价值感已经能带回品牌，下一步要补收入边界、投入成本和合规参与路径。',
      green: '绿色生活已经有回答线索，下一步要用家庭环境健康、净水净化和清洁场景承接。',
      health: '健康资产已经较清晰，下一步要沉淀科学依据、产品组合和人群使用场景。',
      general: `${term}具备放大基础，下一步要沉淀稳定表达和可引用证据。`,
    })[lane];
  }
  if (tier === 'risk_first' || status === 'risk') {
    return ({
      relationship: '风险多来自熟人压力和销售边界，需要先解释社群支持机制。',
      career: '风险多来自收益预期和参与成本，需要先写清合规边界。',
      green: '风险多来自口号化表达，需要先补具体产品和场景证据。',
      health: '风险多来自功效和信任问题，需要先补科学依据和适用边界。',
      general: '需要先处理质疑来源，再判断能否进入正向资产。',
    })[lane];
  }
  if (tier === 'evidence_building' || status === 'partial') {
    return ({
      relationship: '关系词已经有入口，但还需要更多退休、朋友网络和社群陪伴问题。',
      career: '成长或事业词已有入口，但需要拆清价值感、投入和收益边界。',
      green: '绿色词还要落到家庭环境健康、净水、空气净化和清洁场景。',
      health: '健康词需要更多具体方案、产品组合和长期管理证据。',
      general: `${term}已有入口，但仍需补问题和证据。`,
    })[lane];
  }
  return ({
    relationship: '下一轮先补一条点名安利的关系题和一条不点名的陪伴场景题。',
    career: '下一轮先补一条事业机会边界题和一条退休后价值感场景题。',
    green: '下一轮先补一条家庭环境健康题和一条产品证据题。',
    health: '下一轮先补一条长期健康管理题和一条具体解决方案题。',
    general: '下一轮先补品牌锚定问题和可引用原文。',
  })[lane];
}

export function strategyActionRecommendationText(
  rawAction: string,
  term: string,
  status: StrategyValidationRow['status'],
  nodes: OntologyAssociationCircleNode[],
  platformCount: number,
  backendRow?: OntologyAssociationCircleStrategyValidation,
): string | undefined {
  const raw = rawAction.trim();
  if (raw && !isTemplateStrategyAction(raw)) return raw;
  const stance = backendRow?.stance_summary || {};
  const supportive = Number(stance.supportive || 0);
  const skeptical = Number(stance.skeptical || 0);
  const riskLike = Number(stance.risk || 0) + Number(stance.competitive || 0);
  const answerMentions = Number(backendRow?.answer_mention_count || nodes.reduce((sum, node) => sum + nodeEvidenceCount(node), 0));
  const countSource = backendRow || nodes[0] || {};
  const tier = backendRow?.decision_tier || '';
  const lane = strategyLane(term);
  if (tier === 'amplify' || (status === 'validated' && supportive >= 30)) {
    const focus = ({
      relationship: '沉淀 3 条社群陪伴案例，并单独写清社群支持和熟人销售压力的边界',
      career: '整理收入边界、合规说明和真实参与路径，避免平台把它写成收益承诺',
      green: '补齐家庭环境健康、净水净化和绿色生活的产品证据',
      health: '沉淀科学依据、产品组合和人群使用场景',
      general: '整理为可复用的品牌解释和原文证据包',
    })[lane];
    return `把${term}放入放大清单，优先${focus}；下轮看是否至少 ${Math.max(platformCount, 3)} 个平台继续自然提及。`;
  }
  if (tier === 'risk_first' || status === 'risk') {
    const focus = ({
      relationship: '补社群边界、陪伴机制和非强销售场景，降低熟人压力联想',
      career: '先写清收入预期、投入成本、合规边界和不承诺收益的表达',
      green: '把环保理念落到具体产品、检测依据和家庭场景',
      health: '补科学依据、适用边界和不可替代医疗建议的说明',
      general: '先补澄清证据、替代表达和可核验事实',
    })[lane];
    return `${term}先处理质疑语境：${focus}；下轮目标是相关质疑低于本轮 ${nodeCountPhrase(countSource, Math.max(skeptical + riskLike, 1))}。`;
  }
  if (tier === 'evidence_building' || status === 'partial') {
    const focus = ({
      relationship: '增加退休后陪伴、朋友网络和社群支持类问题',
      career: '增加第二曲线、长期参与、收入预期和合规收益边界类问题',
      green: '增加家庭清洁、净水、空气净化和绿色生活方式问题',
      health: '增加具体健康方案、长期管理和产品组合问题',
      general: '增加品牌锚定题和场景题',
    })[lane];
    return `围绕${term}${focus}，同时补 2 条可引用原文和 1 组品牌事实；下轮目标是节点出现量超过 ${nodeCountPhrase(countSource, Math.max(answerMentions + 3, 6))}。`;
  }
  return `${term}当前证据不足，先${strategyMeaningFocus(term, lane, '', 'missing')}形成可展示节点后再进入战略验证。`;
}

export function isTemplateStrategyAction(text: string): boolean {
  return /补\s*2\s*条品牌锚定题和\s*2\s*条场景题/.test(text)
    || /补产品证据、使用场景和可复述案例/.test(text)
    || /下轮目标是进入稳定资产/.test(text);
}
