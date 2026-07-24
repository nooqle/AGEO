/**
 * Pure node insight / map explanation copy for association-circle (knife 3, zero behavior).
 * Extracted from AmwayAssociationCircleDashboardViews.
 */

import type { OntologyAssociationCircleNode } from '@/types/ontology';
import { classifyAssociationNode } from './mapGroups';
import {
  isCompetitorNode,
  nodeClosenessValue,
  nodeCountPhrase,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
} from './nodeMetrics';
import { compactStrategyText } from './evidenceHelpers';
import type { OrbitDistanceBand } from './types';

export function nodeScoreBreakdown(node: OntologyAssociationCircleNode) {
  const rows: Array<{ label: string; weight: string; score?: number }> = [
    { label: '回答频率', weight: '30%', score: node.frequency_score },
    { label: '回答位置', weight: '20%', score: node.position_score },
    { label: '品牌关系', weight: '20%', score: node.relation_type_score },
    { label: '场景覆盖', weight: '15%', score: node.scene_coverage_score },
    { label: '平台一致', weight: '15%', score: node.model_consistency_score },
  ];
  return rows.map((row) => ({
    ...row,
    value: typeof row.score === 'number' ? String(Math.round(row.score)) : '-',
  }));
}

export function riskRoutingExplanationText(
  node: OntologyAssociationCircleNode,
  hasReadableEvidence: boolean,
) {
  const relationLabels: Record<string, string> = {
    LINKED_TO_CENTER_BRAND: '连接中心品牌',
    MENTIONED_IN_QUESTION: '问题中提及',
    MENTIONED_IN_ANSWER: '回答中提及',
    SUPPORTED_BY_SUBBRAND: '子品牌支撑',
    SUPPORTED_BY_PRODUCT: '产品支撑',
    COMPARED_WITH: '对比关系',
    MAPS_TO_STRATEGY: '映射品牌战略',
    MAPS_TO_FLOWER_DIMENSION: '映射美好生活维度',
    BACKED_BY_EVIDENCE: '证据支撑',
    CARRIED_BY_TOUCHPOINT: '触点承载',
    NOT_CONNECTED: '尚未连接品牌',
    MARKET_CONTEXT_ONLY: '仅市场语境',
    RISKS_AS: '风险关联',
    RISK_DENIED: '风险澄清',
    COMPETES_WITH: '竞争参照',
  };
  const relations = Object.entries(node.relation_type_distribution || {})
    .filter(([, count]) => Number(count) > 0)
    .map(([key, count]) => `${relationLabels[key] || key} ${count} 次`)
    .join('、');
  const evidenceQualification = hasReadableEvidence
    ? '下方保留了可核对的代表性原文。'
    : '本期只保留统计关系，未保留可读原文，不能据此展示原文支持。';
  if (isCompetitorNode(node)) {
    return `竞争参照不按正向贴近值强弱分轨。系统依据竞品实体与 COMPETES_WITH 关系单独展示；本节点识别到${relations || '竞争或替代关系'}。${evidenceQualification}`;
  }
  return `风险节点不按正向贴近值强弱分轨。系统依据风险实体标记、回答关系类型与负向语境单独路由；本节点识别到${relations || '风险实体或语境信号'}。${evidenceQualification}`;
}

export function orbitDistanceBandLabel(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') return '稳定联想';
  if (distanceBand === 'bridge') return '可拉近';
  if (distanceBand === 'far') return '待观察';
  return '风险';
}

export function orbitDistanceBandChipStyle(distanceBand: OrbitDistanceBand) {
  if (distanceBand === 'near') {
    return {
      borderColor: 'var(--brand-border)',
      background: 'var(--brand-bg)',
      color: 'var(--brand-primary)',
    };
  }
  if (distanceBand === 'bridge') {
    return {
      borderColor: 'color-mix(in srgb, var(--evidence-opportunity) 28%, var(--border-subtle) 72%)',
      background: 'var(--status-warning-bg)',
      color: 'var(--evidence-opportunity)',
    };
  }
  if (distanceBand === 'far') {
    return {
      borderColor: 'var(--border-subtle)',
      background: 'var(--bg-secondary)',
      color: 'var(--text-tertiary)',
    };
  }
  return {
    borderColor: 'color-mix(in srgb, var(--evidence-risk) 32%, var(--border-subtle) 68%)',
    background: 'var(--status-error-bg)',
    color: 'var(--evidence-risk)',
  };
}

export function orbitBandExplanationText(node: OntologyAssociationCircleNode, distanceBand: OrbitDistanceBand) {
  const evidence = nodeEvidenceCount(node);
  const evidencePhrase = nodeCountPhrase(node, evidence || 0);
  const platform = nodePlatformCount(node);
  const closeness = nodeClosenessValue(node);
  if (distanceBand === 'risk') {
    return isCompetitorNode(node)
      ? `竞争参照单独展开，避免和品牌风险共用同一解释。本轮 ${evidencePhrase}将它作为竞争或替代对象，覆盖 ${platform || 0} 个平台。`
      : `风险认知单独展开，避免和正向联想共用同一套强弱判断。本轮累计 ${evidencePhrase}，覆盖 ${platform || 0} 个平台，需要回看原文确认风险语境。`;
  }
  if (distanceBand === 'near') {
    return `系统贴近值为 ${closeness || 0}，达到稳定轨门槛（60–100）。这表示回答已经较稳定地把它带回品牌。`;
  }
  if (distanceBand === 'bridge') {
    return `系统贴近值为 ${closeness || 0}，位于机会轨区间（35–59）。它已经能连到品牌，但还需要更多直接证据拉近。`;
  }
  return `系统贴近值为 ${closeness || 0}，处于观察区间（0–34）：20–34 为待观察信号，0–19 为证据缺口或远端待验证。它仍需要补充回答频率、场景或跨平台证据。`;
}

export function nodeOriginShortLabel(kind: ReturnType<typeof nodeOriginRead>['kind']) {
  return kind === 'strategy' ? '战略' : '回答';
}

export function nodeOriginRead(node: OntologyAssociationCircleNode, strategyTerms: string[]) {
  const backendOrigin = String(node.term_origin || '').toLowerCase();
  const isStrategy = backendOrigin === 'strategy' || (
    backendOrigin !== 'answer' && nodeMatchesStrategyTerms(node, strategyTerms)
  );
  const evidenceCount = nodeEvidenceCount(node);
  if (isStrategy) {
    return {
      kind: 'strategy' as const,
      label: '战略词',
      description: evidenceCount
        ? '这是本轮战略或题目定义里要验证的词，并且已经在抓取回答中被命中。'
        : '这是本轮战略或题目定义里要验证的词，目前还需要回答证据把它带回品牌。',
    };
  }
  return {
    kind: 'answer' as const,
    label: '回答词',
    description: '这是从 AI 平台回答中解析出来的联想词，前端没有预设进图。',
  };
}

export function nodeMatchesStrategyTerms(node: OntologyAssociationCircleNode, strategyTerms: string[]) {
  const source = String(node.source || '').toLowerCase();
  if (node.is_target_term || /strategy|target|seed|manual/.test(source)) return true;
  const nodeTerm = compactStrategyText(node.term);
  if (!nodeTerm) return false;
  return strategyTerms.some((term) => {
    const strategyTerm = compactStrategyText(term);
    return Boolean(strategyTerm) && (
      strategyTerm === nodeTerm ||
      strategyTerm.includes(nodeTerm) ||
      nodeTerm.includes(strategyTerm)
    );
  });
}

export function nodeBrandRelationText(
  node: OntologyAssociationCircleNode,
  centerTerm: string,
  origin: ReturnType<typeof nodeOriginRead>,
) {
  const groupKey = classifyAssociationNode(node);
  const path = associationPathLabel(node);

  if (groupKey === 'risk') {
    if (isCompetitorNode(node)) {
      return `“${node.term}”是回答中与${centerTerm}并列出现的竞争或替代参照。它单独进入竞争关系视图，用来判断平台在什么问题和场景下会把用户导向其他品牌，不代表负面风险。`;
    }
    return `“${node.term}”和${centerTerm}的关系会把品牌带回旧认知风险，属于需要单独管理的风险入口。它需要进入风险关系图，避免混在正向战略轨道里解读。`;
  }

  if (origin.kind === 'strategy') {
    if (groupKey === 'strong') {
      return `“${node.term}”是${centerTerm}本轮要验证的战略词，也已经被平台回答稳定带回品牌。这个词来自本轮战略定义，当前证据显示它已经被回答接住。`;
    }
    if (groupKey === 'growth') {
      return `“${node.term}”是${centerTerm}未来发展的战略方向之一。回答已经能沿着“${path}”把它带回品牌，但它尚未成为平台的第一反应，所以更像正在形成的机会资产。`;
    }
    return `“${node.term}”是${centerTerm}未来想建立的新联想。当前它通过“${path}”和品牌发生连接，但还停留在远端机会区，平台还没有稳定把它记成${centerTerm}的代表性表达。`;
  }

  if (groupKey === 'strong') {
    return `“${node.term}”由平台回答主动带出，属于回答端形成的强联想。用户问到“${path}”相关问题时，AI 已经容易把${centerTerm}放进回答。`;
  }

  return `“${node.term}”来自平台回答解析，属于可继续观察的机会线索。它目前能连接到${centerTerm}，但还需要更清楚的品牌内容和外部证据把关系讲实。`;
}

export function nodeBrandImplicationText(
  node: OntologyAssociationCircleNode,
  centerTerm: string,
  origin: ReturnType<typeof nodeOriginRead>,
) {
  const groupKey = classifyAssociationNode(node);
  if (groupKey === 'risk') {
    if (isCompetitorNode(node)) {
      return `这意味着${centerTerm}需要看清竞品被带出的场景、主张与证据，再决定补充差异化材料。下一轮应观察这个竞争参照是否持续出现，以及是否发生平台迁移。`;
    }
    return `这意味着${centerTerm}需要先处理旧认知：补澄清内容、替代叙事和可验证证据。下一轮要观察这个风险词是否减少出现，或者是否被新的正向解释覆盖。`;
  }
  if (origin.kind === 'strategy') {
    if (groupKey === 'strong') {
      return `这意味着这个战略方向已经被回答接住，适合沉淀成可复述的问题回答素材。下一轮重点观察它是否继续被平台带回品牌、是否被更多平台主动提起。`;
    }
    return `这意味着它仍在培育期。更合理的做法是先补人群故事、场景内容和可引用证据，再看下一轮它是否更稳定地回到品牌。`;
  }
  if (groupKey === 'strong') {
    return `这意味着${centerTerm}已有一个被平台自然带出的优势资产。品牌可以优先把它整理成可复用表达，并在官网、内容和问答素材里继续放大。`;
  }
  return `这意味着它是一个可培育机会，尚未成为已经成立的品牌资产。下一轮应围绕对应人群和场景继续发问，看它是否能被更多平台稳定带回${centerTerm}。`;
}

export function nodeEvidenceSummaryText({
  term,
  questionCount,
  totalAnswerCount,
  mentionAnswerCount,
  node,
  relatedQuestionCount,
  platformNames,
  riskScoped = false,
  competitionScoped = false,
}: {
  term: string;
  questionCount: number;
  totalAnswerCount: number;
  mentionAnswerCount: number;
  node: OntologyAssociationCircleNode;
  relatedQuestionCount: number;
  platformNames: string[];
  riskScoped?: boolean;
  competitionScoped?: boolean;
}) {
  const questionPart = questionCount ? `本轮围绕 ${questionCount} 个问题发问` : '本轮问题样本中';
  const answerPart = totalAnswerCount ? `，抓取到 ${totalAnswerCount} 条有效回答` : '';
  const mentionCountPhrase = nodeCountPhrase(node, mentionAnswerCount);
  const mentionPart = mentionAnswerCount
    ? competitionScoped
      ? `其中 ${mentionCountPhrase}将“${term}”作为竞争或替代参照`
      : riskScoped
      ? `其中 ${mentionCountPhrase}形成与“${term}”有关的质疑或风险语境`
      : `其中“${term}”出现了 ${mentionCountPhrase}`
    : competitionScoped
      ? `目前还没有回答把“${term}”作为竞争或替代参照`
      : riskScoped
      ? `目前还没有回答形成与“${term}”有关的质疑或风险语境`
      : `目前还没有形成与“${term}”有关的稳定节点提及`;
  const relatedPart = relatedQuestionCount ? `，覆盖 ${relatedQuestionCount} 个相关问题` : '';
  const platformPart = platformNames.length ? `，来自 ${platformNames.join('、')}` : '';
  const verdict = mentionAnswerCount
    ? competitionScoped
      ? '它已进入竞争观察范围，需要结合平台分布和原文判断比较发生在哪些场景。'
      : riskScoped
      ? '它已进入风险观察范围，需要结合平台分布和原文语境判断风险如何形成。'
      : '它已经进入 AI 回答的可观察范围，还要结合平台分布和原文语境判断是否真正成立。'
    : competitionScoped
      ? '当前没有形成可验证的竞争关系。'
      : riskScoped
      ? '当前没有形成可验证的风险关系。'
      : '它仍属于待验证方向，当前先按观察中的品牌联想处理。';
  return `${questionPart}${answerPart}；${mentionPart}${relatedPart}${platformPart}。${verdict}`;
}

export function answerPresenceText(node: OntologyAssociationCircleNode) {
  const evidence = nodeEvidenceCount(node);
  const phrase = nodeCountPhrase(node, evidence);
  if (evidence >= 20) return `${phrase}，已形成可观察联想`;
  if (evidence >= 8) return `${phrase}，具备可观察样本`;
  if (evidence > 0) return `${phrase}，仍需继续观察`;
  return '当前样本里只有很弱的出现痕迹';
}

export function platformPresenceText(node: OntologyAssociationCircleNode) {
  const platform = nodePlatformCount(node);
  if (platform >= 3) return `${platform} 个平台同时出现，平台共识较强`;
  if (platform === 2) return '2 个平台出现，已经跨过单平台偶然性';
  if (platform === 1) return '只在 1 个平台出现，先按单平台线索观察';
  return '平台一致性还没有形成';
}

export function associationPathLabel(node: OntologyAssociationCircleNode) {
  const candidates = [
    ...(node.primary_opportunity_points || []),
    ...(node.primary_mother_themes || []),
    ...(node.primary_audience_segments || []),
    node.theme,
    node.planet_group,
    node.orbit_label,
  ]
    .map((item) => String(item || '').trim())
    .filter(Boolean);
  const unique = Array.from(new Set(candidates));
  return unique.length ? unique.slice(0, 2).join(' / ') : '连接路径待继续确认';
}

export function relationshipRead(node: OntologyAssociationCircleNode) {
  const groupKey = classifyAssociationNode(node);
  const distance = nodeDistanceValue(node);
  const answerText = answerPresenceText(node);
  const platformText = platformPresenceText(node);
  const pathText = associationPathLabel(node);

  if (groupKey === 'risk') {
    if (isCompetitorNode(node)) {
      return {
        label: '竞争替代',
        headline: '它是回答中的竞争或替代参照，需要单独比较。',
        reasons: [
          `回答表现：${answerText}。`,
          `平台一致性：${platformText}。`,
          `关系来源：回答把它带到“${pathText}”语境，应回看原文比较竞品主张与证据。`,
        ],
        nextStep: '下一步：确认竞品被带出的场景、主张和证据，下轮观察竞争参照是否持续出现或发生平台迁移。',
      };
    }
    return {
      label: '风险旧认知',
      headline: '它会干扰品牌解释，需要单独管理。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `关系来源：回答把它带到“${pathText}”语境，需要回看原文判断风险来源。`,
      ],
      nextStep: '下一步：优先追溯原文，设计澄清内容或替代叙事，下轮看它是否减少出现、是否被正向解释替代。',
    };
  }

  if (groupKey === 'strong') {
    return {
      label: '已绑定资产',
      headline: '平台回答已经容易把它和品牌放在一起，可以作为当前品牌资产来管理。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：主要通过“${pathText}”进入品牌解释。`,
      ],
      nextStep: '下一步：把它作为稳定卖点保留，同时补更多权威证据，防止被风险词稀释。',
    };
  }

  if (groupKey === 'story') {
    return {
      label: '远端机会 / 待观察',
      headline: '它代表未来想建立的联想，目前还没有被平台回答稳定绑定。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：需要先用“${pathText}”补足人群故事和场景证据。`,
      ],
      nextStep: '下一步：先做内容铺垫，下轮观察是否更稳定地回到品牌。',
    };
  }

  if (distance <= 44) {
    return {
      label: '近端机会',
      headline: '它已经能通向品牌，但还没有成为多数回答的第一反应。',
      reasons: [
        `回答表现：${answerText}。`,
        `平台一致性：${platformText}。`,
        `连接路径：主要沿“${pathText}”把用户需求带回品牌。`,
      ],
      nextStep: '下一步：补充更直接的品牌证据，让它从机会区进入稳定资产区。',
    };
  }

  return {
    label: '待培育机会',
    headline: '它和品牌之间已有线索，但用户还需要看到更明确的内容证据。',
    reasons: [
      `回答表现：${answerText}。`,
      `平台一致性：${platformText}。`,
      `连接路径：目前还需要通过“${pathText}”多绕一层才能回到品牌。`,
    ],
    nextStep: '下一步：围绕对应人群和场景补内容，下轮看它能否进入可拉近区。',
  };
}
