/**
 * Pure association-circle report narrative builders (knife 5, zero behavior).
 */

import type {
  OntologyAssociationCircleAnalysisTraceItem,
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNarrativeSection,
  OntologyAssociationCirclePlatformComparison,
  OntologyAssociationCirclePlatformSourceSummary,
  OntologyAssociationCircleProjection,
  OntologyAssociationCircleQuestion,
  OntologyAssociationCircleQuestionDefinition,
  OntologyAssociationCircleSourceAppendixItem,
} from '@/types/ontology';
import { platformLabel } from './constants';
import { commercialReportCopy } from './evidenceHelpers';
import {
  isCompetitorNode,
  nodeCountMode,
  nodeCountPhrase,
  nodeCountShortUnit,
  nodeEvidenceCount,
} from './nodeMetrics';
import {
  firstSampleNumber,
  sampleAnswerCount,
  samplePlatformCount,
  sampleQuestionCount,
} from './projection';
import type {
  AssociationMapGroup,
  AssociationMapGroupKey,
  NodeFrequencyBarItem,
  ReportNarrativeSection,
} from './types';

export function topTermsForReport(groups: AssociationMapGroup[], key: AssociationMapGroupKey, limit = 3) {
  return (groups.find((group) => group.key === key)?.nodes || [])
    .slice(0, limit)
    .map((node) => node.term)
    .filter(Boolean);
}

export function sentenceJoin(items: string[], fallback: string) {
  if (!items.length) return fallback;
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join('、')}和${items[items.length - 1]}`;
}

export function buildAssociationNarrativeReport({
  centerTerm,
  groups,
  platformComparison,
  evidenceSamples,
  sampleScope,
}: {
  centerTerm: string;
  groups: AssociationMapGroup[];
  platformComparison: OntologyAssociationCirclePlatformComparison[];
  evidenceSamples: OntologyAssociationCircleEvidence[];
  sampleScope: Record<string, unknown>;
}) {
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const strongTerms = topTermsForReport(groups, 'strong', 3);
  const growthTerms = topTermsForReport(groups, 'growth', 3);
  const storyTerms = topTermsForReport(groups, 'story', 2);
  const riskTerms = topTermsForReport(groups, 'risk', 3);
  const firstPlatform = platformComparison[0];
  const firstEvidence = evidenceSamples[0];
  const strongText = sentenceJoin(strongTerms, '近端资产');
  const growthText = sentenceJoin(growthTerms, '机会词');
  const storyText = sentenceJoin(storyTerms, '观察词');
  const riskText = sentenceJoin(riskTerms, '风险词');
  const firstEvidenceRefs = firstEvidence?.evidence_id ? [firstEvidence.evidence_id] : [];
  const centerLinkedSignalCount = Number(sampleScope.center_linked_signal_count || 0);
  const marketContextSignalCount = Number(sampleScope.market_context_signal_count || 0);
  const competitionTerms = platformComparison
    .flatMap((row) => row.competition_nodes || [])
    .map((term) => String(term || '').trim())
    .filter(Boolean)
    .filter((term, index, terms) => terms.indexOf(term) === index)
    .slice(0, 4);
  const competitionText = sentenceJoin(competitionTerms, '本轮未形成明显竞品参照');
  const opportunityText = [...growthTerms, ...storyTerms].length
    ? `近端机会包括${growthText}；远端观察包括${storyText}`
    : '新的机会词还需要继续采样';
  const riskAndCompetitionText = [
    competitionTerms.length ? competitionText : '',
    riskTerms.length ? riskText : '',
  ].filter(Boolean).join('、') || '竞品与风险关系';
  const overallStatus = fallbackOverallStrategyStatus({
    strongCount: strongTerms.length,
    growthCount: growthTerms.length,
    storyCount: storyTerms.length,
    riskCount: riskTerms.length + competitionTerms.length,
  });

  return [
    {
      title: '核心判断',
      readerQuestion: '这一轮 AI 到底怎样理解品牌？',
      takeaway: answerCount && platformCount
        ? `${centerTerm}本轮最容易被回答带回的联想集中在${strongText}；近端机会集中在${growthText}；总体判断为${overallStatus}。`
        : `${centerTerm}先以回答里真实出现的词作为观察边界。`,
      claims: [
        answerCount && platformCount ? `样本边界：${answerCount} 条有效回答，有效平台 ${platformCount} 个。` : '样本边界还需要继续补齐。',
        `回答最容易带回品牌的联想：${strongText}。`,
        `主要优势：平台已经能把${strongText}带回${centerTerm}。`,
        `当前短板：${sentenceJoin([...growthTerms, ...storyTerms], '机会词')}还需要更多证据。`,
        `最大风险：${riskText}。`,
        `总体判断：${overallStatus}。`,
      ],
      text: [
        answerCount && platformCount
          ? `这一轮读到 ${answerCount} 条有效回答，有效平台 ${platformCount} 个。图上越靠近中心的词，越容易在回答里和${centerTerm}形成同一段解释；越靠外的词，还停留在机会、观察或风险语境里。`
          : '这一轮先读取回答里真实出现过的词，战略词只作为解释背景。',
        `${centerTerm}的主要优势来自${strongText}。这些词已经具备内容沉淀价值，适合继续补产品事实、使用场景和权威背书。`,
        `当前短板集中在尚未完全站稳的机会：${opportunityText}。这些词已经进入品牌故事边缘，但还需要更多点名问题、原文证据和跨平台一致性。`,
        `最大风险来自${riskAndCompetitionText}。这类关系要回到触发它们的问题场景，判断用户是在比较、疑虑、误读，还是在寻找替代方案。`,
        `综合来看，${centerTerm}本轮品牌战略处于${overallStatus}状态。已被回答接住的资产可以先放大，尚未站稳的机会需要继续补问题、补场景和补证据。`,
      ].join('\n\n'),
      soWhat: '品牌团队可以先守住已绑定资产，再把机会词补成平台愿意引用的证据链。',
      supportingFacts: [
        answerCount ? `${answerCount} 条有效回答进入本轮解析。` : '有效回答样本待补充。',
        platformCount ? `${platformCount} 个平台进入本轮比较。` : '平台样本待补充。',
        centerLinkedSignalCount ? `${centerLinkedSignalCount} 条信号进入品牌关系判断。` : '',
        marketContextSignalCount ? `${marketContextSignalCount} 条信号仅作为市场背景保留。` : '',
      ].filter(Boolean),
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮保持同一批核心问题，继续追踪正向资产、部分验证战略词和风险词的位置变化。',
    },
    {
      title: `${centerTerm}的 AI 档案里写了什么`,
      readerQuestion: '平台给品牌贴上的默认标签是什么？',
      takeaway: strongTerms.length
        ? `越靠近中心，代表 AI 回答越容易自然地把该词带回${centerTerm}。`
        : `${centerTerm}暂时还没有形成足够稳定的第一反应。`,
      claims: [
        `内圈：${strongText}。`,
        `中圈：${growthText}。`,
        `外圈：${storyText}。`,
        '风险采用独立关系层，不进入远近轨道。',
      ],
      text: [
        strongTerms.length
          ? `${sentenceJoin(strongTerms, '')}位于更靠近中心的位置，代表回答已经较稳定地把这些词和${centerTerm}放在同一段品牌解释里。`
          : `这一轮还没有出现足够稳定的第一反应。${centerTerm}需要更多可被回答引用的公开证据，先把已有事实讲得更清楚。`,
        `中圈看${growthText}，它们已经有连接路径，但还需要更明确的问题、内容和证据。外圈看${storyText}，它们适合作为下一轮战略验证对象。`,
        `越靠近中心，代表 AI 回答越容易自然地把该词带回${centerTerm}。风险关系单独展开，处理信任、合规、销售方式或争议语境。`,
      ].join('\n\n'),
      soWhat: '读图时先看远近，再看词源和证据，最后回到原文判断它和品牌的真实关系。',
      supportingFacts: [
        strongTerms.length ? `本轮近端资产包括：${strongText}。` : '本轮近端资产不足。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮围绕近端资产追加产品事实题、场景题和品牌锚定题，观察它们是否仍被平台稳定带回品牌。',
    },
    {
      title: '四个价值支柱，在 AI 叙事里是什么状态',
      readerQuestion: '四有分别被接住、牵制、反转还是缺席？',
      takeaway: growthTerms.length || storyTerms.length
        ? `${sentenceJoin([...growthTerms, ...storyTerms], '机会词')}可以作为下一轮战略验证对象，节点只是证据。`
        : '新的需求场景尚未形成稳定机会词。',
      claims: [
        `近端机会：${growthText}。`,
        `长期观察词：${storyText}。`,
      ],
      text: [
        '这一章不再逐词填表，只看几个价值支柱分别处在什么差距类型里。',
        growthTerms.length
          ? `${sentenceJoin(growthTerms, '')}已经能通向${centerTerm}，但出现频率和平台一致性还不够稳。下一轮要把这些词拆回具体问题，逐项检查哪些回答、哪些平台、哪些原文把它们带回品牌。`
          : '这一轮机会区还不明显，新的需求场景暂时没有稳定地回到品牌。',
        storyTerms.length
          ? `${sentenceJoin(storyTerms, '')}更适合作为观察词。它们尚未成为成熟资产，但可能接到长寿、陪伴、人生阶段和美好生活这些长期议题。`
          : '如果要建立新的品牌联想，下一轮问题和内容应更多覆盖人群、生活场景和真实使用理由。',
      ].join('\n\n'),
      soWhat: '机会词需要通过问题、内容和回答证据反复带回中心品牌。',
      supportingFacts: [
        `机会词：${sentenceJoin([...growthTerms, ...storyTerms], '暂未形成')}。`,
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '把机会词拆成自然提问、路径提问和品牌锚定提问，分别看平台是否会主动连回品牌。',
    },
    {
      title: '平台差异',
      readerQuestion: '不同平台怎样验证同一个战略词？',
      takeaway: firstPlatform
        ? `${platformLabel(firstPlatform.platform)}这一轮更容易从“${firstPlatform.answer_preference || '偏好待观察'}”进入${centerTerm}，但平台差异需要绑定战略词来看。`
        : '平台偏好样本还不足，暂不形成稳定判断。',
      claims: [
        firstPlatform
          ? `${platformLabel(firstPlatform.platform)}有效回答 ${firstPlatform.valid_answer_count || 0} 条。`
          : '平台有效样本不足。',
        firstPlatform
          ? `代表节点：${(firstPlatform.preferred_nodes || []).join('、') || '待观察'}。`
          : '代表节点待观察。',
      ],
      text: firstPlatform
        ? [
            `${platformLabel(firstPlatform.platform)}这一轮偏向“${firstPlatform.answer_preference || '偏好待观察'}”。同一个中心品牌，在不同平台会先进入不同入口：产品、健康、社群，或风险解释；每个平台的差异要回到具体战略词判断。`,
            firstPlatform.recommendation
              ? `内容准备要跟着平台入口走。${firstPlatform.recommendation}`
              : '内容准备要跟着平台入口走，每个平台优先补它最容易采用的证据。',
          ].join('\n\n')
        : '这一轮平台样本还不足以形成明确差异。等有效平台样本更完整后，报告应继续比较不同平台的回答偏好。',
      soWhat: '同一品牌在不同平台会被不同入口接住；内容建设应按平台补证据，避免用一套话术覆盖所有平台。',
      supportingFacts: [
        firstPlatform
          ? `${platformLabel(firstPlatform.platform)}代表节点：${(firstPlatform.preferred_nodes || []).join('、') || '待观察'}。`
          : '平台样本不足。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮按平台分别补材料，比较它们是否仍沿同一入口组织回答。',
    },
    {
      title: '从数据到行动',
      readerQuestion: '品牌团队这周先做哪三件事？',
      takeaway: riskTerms.length
        ? `${centerTerm}应先守住${strongText}，再拉近${growthText}，并单独处理${riskText}。`
        : `${centerTerm}应先守住${strongText}，再拉近${growthText}。`,
      claims: [
        `已绑定资产：${strongText}。`,
        `正在形成的机会：${growthText}。`,
        `风险关系：${riskText}。`,
      ],
      text: [
        `${strongText}适合沉淀成可复述的问题回答素材，继续补产品事实、使用场景和权威证据。`,
        `${growthText}仍需要更多直接证据，暂时适合作为下一轮重点验证对象。`,
        competitionTerms.length
          ? `${sentenceJoin(competitionTerms, '')}要纳入竞争场景复盘，追踪它们在什么问题里替代了${centerTerm}。`
          : '竞品参照暂时不强，但后续要持续观察替代品牌是否进入同类问题。',
        riskTerms.length
          ? `${sentenceJoin(riskTerms, '')}会把回答带向信任、争议或销售方式，需要先看原文语境，再设计澄清和替代表达。`
          : '风险认知这一轮没有被明显放大，但仍需保留为复测基线。',
      ].join('\n\n'),
      soWhat: '这部分结论可以直接用于内部策略会：哪些放大、哪些补证据、哪些先澄清。',
      supportingFacts: [
        `稳定资产：${strongText}。`,
        `机会词：${growthText}。`,
        competitionTerms.length ? `竞品参照：${competitionText}。` : '本轮竞品参照未明显放大。',
        riskTerms.length ? `风险词：${riskText}。` : '本轮风险认知未明显放大。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下一轮分别复测已绑定资产、机会词、未验证战略词和风险关系，看它们是否发生位置变化。',
    },
    {
      title: '附录：样本、平台与原文证据',
      readerQuestion: '这轮判断的样本边界是什么？',
      takeaway: '下一轮要固定题库口径，分别追踪战略词、核心问题、风险词和机会词的轨道变化。',
      claims: [
        `继续追踪：${growthText}。`,
        `新增问题聚焦：${storyText}。`,
        `风险复测对象：${riskText}。`,
      ],
      text: [
        `${growthText}要继续追踪，重点看它们是否从中圈进入内圈。`,
        `本轮能触发${strongText}和${riskText}的问题要保留，保证下一轮可以比较位置变化。`,
        `新增问题应围绕${storyText}，补充人群、生活场景、产品证据和品牌锚定探针。`,
        `${riskText}要看提及是否下降，${growthText}和${storyText}要看是否向中心移动。`,
      ].join('\n\n'),
      soWhat: '下一轮追踪要服务决策：哪些词可以放大，哪些词继续补证据，哪些风险需要先澄清。',
      supportingFacts: [
        answerCount ? `${answerCount} 条有效回答作为本轮复测基线。` : '有效回答样本待补充。',
        platformCount ? `${platformCount} 个平台作为本轮平台基线。` : '平台样本待补充。',
      ],
      evidenceRefs: firstEvidenceRefs,
      nextProbe: '下轮报告应输出同一批战略词的位置变化、平台提及变化和风险词变化。',
    },
  ];
}

export function fallbackOverallStrategyStatus({
  strongCount,
  growthCount,
  storyCount,
  riskCount,
}: {
  strongCount: number;
  growthCount: number;
  storyCount: number;
  riskCount: number;
}) {
  if (riskCount >= Math.max(strongCount + growthCount, 1) && riskCount >= 3) {
    return '被风险遮蔽';
  }
  if (strongCount >= 3 && growthCount === 0 && storyCount === 0) {
    return '回答接住较多';
  }
  if (strongCount || growthCount) {
    return '部分验证';
  }
  return '尚未验证';
}

export function normalizeReportNarrativeSections(
  sections?: OntologyAssociationCircleNarrativeSection[] | null,
): ReportNarrativeSection[] | null {
  if (!Array.isArray(sections) || !sections.length) return null;
  const normalized = sections
    .map((section): ReportNarrativeSection | null => {
      const title = commercialReportCopy(section?.title);
      const paragraphs = Array.isArray(section?.paragraphs)
        ? section.paragraphs.map((paragraph) => commercialReportCopy(paragraph)).filter(Boolean)
        : [];
      const supportingFacts = Array.isArray(section?.supporting_facts)
        ? section.supporting_facts.map((fact) => commercialReportCopy(fact)).filter(Boolean)
        : [];
      const evidenceRefs = Array.isArray(section?.evidence_refs)
        ? section.evidence_refs.map((ref) => String(ref || '').trim()).filter(Boolean)
        : [];
      const readerQuestion = commercialReportCopy(section?.reader_question);
      const nextProbe = commercialReportCopy(section?.next_probe);
      const takeaway = commercialReportCopy(section?.takeaway);
      const claims = Array.isArray(section?.claims)
        ? section.claims.map((claim) => commercialReportCopy(claim)).filter(Boolean)
        : [];
      const soWhat = commercialReportCopy(section?.so_what);
      if (!title || !paragraphs.length) return null;
      return {
        sectionId: String(section?.section_id || '').trim() || undefined,
        title,
        text: paragraphs.join('\n\n'),
        readerQuestion,
        takeaway,
        claims,
        soWhat,
        supportingFacts,
        evidenceRefs,
        nextProbe,
      };
    })
    .filter((section): section is ReportNarrativeSection => Boolean(section));
  return normalized.length ? normalized : null;
}

export function readableNarrativeSections(
  sections: ReportNarrativeSection[] | null,
): ReportNarrativeSection[] | null {
  if (!sections?.length) return null;
  const titles = sections.map((section) => section.title);
  const legacyStoryTitles = [
    '品牌联想裁决',
    '有健康｜唯一被接住的有',
    '有陪伴｜萌芽被旧认知牵制',
    '有保障 + 有价值｜先修复信任，再谈人生再出发',
    '本周 3 件事',
  ];
  const aiArchiveStoryTitles = [
    '核心判断',
    '四个价值支柱，在 AI 叙事里是什么状态',
    '平台差异',
    '从数据到行动',
  ];
  const hasStoryShape = legacyStoryTitles.every((title) => titles.includes(title))
    || aiArchiveStoryTitles.every((title) => titles.includes(title));
  if (!hasStoryShape) return null;
  const completeCount = sections.filter((section) => (
    section.readerQuestion
    && section.takeaway
    && section.claims?.length
    && section.soWhat
    && section.nextProbe
  )).length;
  return completeCount >= Math.min(3, sections.length) ? sections : null;
}

export function buildQuestionDefinitionFallback(
  projection: OntologyAssociationCircleProjection,
  centerTerm: string,
): OntologyAssociationCircleQuestionDefinition | undefined {
  const questionBank = projection.question_bank || [];
  const sampleScope = projection.sample_scope || {};
  const questionCount = sampleQuestionCount(sampleScope) || questionBank.length;
  if (!questionCount && !questionBank.length) return undefined;
  const uniqueValues = (key: keyof OntologyAssociationCircleQuestion) =>
    Array.from(new Set(questionBank.map((question) => String(question[key] || '').trim()).filter(Boolean))).slice(0, 6);
  const audienceSegments = uniqueValues('audience_segment');
  const probeTypes = uniqueValues('probe_type');
  const opportunityPoints = uniqueValues('opportunity_point');
  const lifeScenes = uniqueValues('life_scene');
  return {
    center_term: centerTerm,
    center_terms: projection.center_terms || [centerTerm],
    question_count: questionCount,
    question_bank_count: questionBank.length,
    audience_segments: audienceSegments,
    probe_types: probeTypes,
    opportunity_points: opportunityPoints,
    life_scenes: lifeScenes,
    sample_questions: questionBank.slice(0, 8).map((question) => ({
      id: question.id,
      text: question.text || question.question || question.question_text,
      audience_segment: question.audience_segment || undefined,
      life_scene: question.life_scene || undefined,
      opportunity_point: question.opportunity_point || undefined,
      probe_type: question.probe_type || undefined,
      metadata_status: question.metadata_status,
    })),
    definition_sentence: `中心品牌：${centerTerm}；题目数：${questionCount}；人群：${audienceSegments.join('、') || '待补充'}；探针：${probeTypes.join('、') || '待补充'}。`,
  };
}

export function buildPlatformSourceSummaryFallback(
  projection: OntologyAssociationCircleProjection,
): OntologyAssociationCirclePlatformSourceSummary | undefined {
  const rows = projection.platform_comparison || [];
  const sampleScope = projection.sample_scope || {};
  if (!rows.length && !samplePlatformCount(sampleScope)) return undefined;
  const totalValidAnswers = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope) || rows.length;
  const estimatedPerPlatform = totalValidAnswers && platformCount
    ? Math.max(1, Math.round(totalValidAnswers / platformCount))
    : undefined;
  const platforms = rows.map((row) => ({
    platform: row.platform,
    total_answer_count: estimatedPerPlatform,
    valid_answer_count: estimatedPerPlatform,
    failed_answer_count: 0,
    empty_answer_count: 0,
    answer_preference: row.answer_preference,
    preferred_nodes: row.preferred_nodes,
    dominant_orbit: row.dominant_orbit,
    risk_bias: row.risk_bias,
    opportunity_bias: row.opportunity_bias,
    recommendation: row.recommendation,
  }));
  return {
    total_answer_count: totalValidAnswers || platforms.reduce((sum, row) => sum + (row.valid_answer_count || 0), 0),
    valid_answer_count: totalValidAnswers || platforms.reduce((sum, row) => sum + (row.valid_answer_count || 0), 0),
    failed_answer_count: firstSampleNumber(sampleScope.failed_answer_count),
    empty_answer_count: firstSampleNumber(sampleScope.empty_answer_count),
    platform_count: platformCount,
    platform_names: platforms.map((row) => row.platform || '').filter(Boolean),
    platforms,
  };
}

export function buildEvidenceFindingsFallback(
  projection: OntologyAssociationCircleProjection,
): OntologyAssociationCircleEvidenceFinding[] {
  if (projection.evidence_findings?.length) return projection.evidence_findings;
  const samplesById = new Map((projection.evidence_samples || []).map((sample) => [sample.evidence_id, sample]));
  return (projection.nodes || []).slice(0, 12).map((node) => {
    const evidenceRefs = (node.evidence_samples || []).filter(Boolean);
    const sample = evidenceRefs.length ? samplesById.get(evidenceRefs[0]) : undefined;
    return {
      node_id: node.node_id,
      node_term: node.term,
      claim: node.orbit_reason || `${node.term}已经进入本轮回答，需要结合平台和证据继续判断。`,
      orbit: node.orbit,
      orbit_label: node.orbit_label,
      business_tag: node.business_tag,
      supporting_facts: [
        `${nodeCountPhrase(node, nodeEvidenceCount(node))}，有效平台 ${node.platform_count || 0} 个。`,
        `图谱贴近值 ${node.closeness_score ?? node.gravity_score ?? '-'}，距离值 ${node.distance_score ?? '-'}。`,
      ],
      evidence_refs: evidenceRefs,
      sample_platform: sample?.platform,
      sample_question: sample?.question,
      sample_excerpt: sample?.answer_excerpt,
      implication: node.orbit_reason,
    };
  }).filter((finding) => finding.node_term);
}

export function buildAnalysisTraceFallback(
  questionDefinition?: OntologyAssociationCircleQuestionDefinition,
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary,
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[] = [],
): OntologyAssociationCircleAnalysisTraceItem[] {
  return [
    {
      step: 'question_scope_scan',
      title: '题目范围扫描',
      summary: questionDefinition?.definition_sentence || '从题库恢复题目、人群和探针范围。',
      outputs: questionDefinition?.probe_types || [],
    },
    {
      step: 'platform_scope_scan',
      title: '平台样本扫描',
      summary: `有效回答 ${platformSourceSummary?.valid_answer_count || 0} 条，平台 ${platformSourceSummary?.platform_count || 0} 个。`,
      outputs: platformSourceSummary?.platform_names || [],
    },
    {
      step: 'association_evidence_forge',
      title: '联想证据锻造',
      summary: '把节点、有效平台数和原文摘录合并成可解释判断。',
      outputs: evidenceFindings.slice(0, 6).map((finding) => finding.node_term || '').filter(Boolean),
    },
  ];
}

export function buildSourceAppendixFallback(
  evidenceSamples: OntologyAssociationCircleEvidence[] = [],
): OntologyAssociationCircleSourceAppendixItem[] {
  return evidenceSamples.slice(0, 20).map((sample) => ({
    evidence_id: sample.evidence_id,
    node_term: sample.node_term,
    platform: sample.platform,
    question_id: sample.question_id,
    question: sample.question,
    answer_excerpt: sample.answer_excerpt,
    audience_segment: sample.audience_segment || undefined,
    life_scene: sample.life_scene || undefined,
    opportunity_point: sample.opportunity_point || undefined,
    probe_type: sample.probe_type || undefined,
  }));
}

export function buildReportQualityChecksFallback({
  questionDefinition,
  platformSourceSummary,
  evidenceFindings,
  actions,
  sourceAppendix,
}: {
  questionDefinition?: OntologyAssociationCircleQuestionDefinition;
  platformSourceSummary?: OntologyAssociationCirclePlatformSourceSummary;
  evidenceFindings: OntologyAssociationCircleEvidenceFinding[];
  actions: OntologyAssociationCircleProjection['association_actions'];
  sourceAppendix: OntologyAssociationCircleSourceAppendixItem[];
}): Record<string, unknown> {
  const requiredChecks = [
    {
      key: 'question_definition',
      label: '题目定义',
      passed: Boolean(questionDefinition?.definition_sentence || questionDefinition?.sample_questions?.length),
    },
    {
      key: 'platform_source_summary',
      label: '平台来源',
      passed: Boolean(platformSourceSummary?.platform_count || platformSourceSummary?.platforms?.length),
    },
    {
      key: 'evidence_findings',
      label: '证据链',
      passed: Boolean(evidenceFindings.length),
    },
    {
      key: 'source_appendix',
      label: '来源附录',
      passed: Boolean(sourceAppendix.length),
    },
    {
      key: 'action_review',
      label: '行动复测',
      passed: Boolean(actions?.length),
    },
  ];
  return {
    version: 'frontend_legacy_artifact_fallback',
    passed: requiredChecks.every((check) => check.passed),
    required_checks: requiredChecks,
  };
}

export function buildCoreVerdictMetrics(
  sampleScope: Record<string, unknown>,
  groups: AssociationMapGroup[],
): Array<{ label: string; value: string; sub?: string; tone?: 'default' | 'risk' | 'opportunity' }> {
  const answerCount = sampleAnswerCount(sampleScope);
  const platformCount = samplePlatformCount(sampleScope);
  const riskGroupNodes = groups.find((g) => g.key === 'risk')?.nodes || [];
  const riskCount = riskGroupNodes.filter((node) => !isCompetitorNode(node)).length;
  const competitorCount = riskGroupNodes.filter(isCompetitorNode).length;
  const opportunityCount = groups.find((g) => g.key === 'growth')?.nodes.length || 0;
  const watchCount = groups.find((g) => g.key === 'story')?.nodes.length || 0;
  return [
    { label: '有效回答', value: answerCount ? String(answerCount) : '-', sub: '本轮解析基线' },
    { label: '有效平台', value: platformCount ? String(platformCount) : '-', sub: '进入比较的平台数' },
    { label: '机会节点', value: String(opportunityCount), sub: '机会轨节点数', tone: 'opportunity' },
    { label: '观察节点', value: String(watchCount), sub: '观察轨节点数' },
    { label: '风险认知', value: String(riskCount), sub: '质疑与负向关系', tone: 'risk' },
    { label: '竞品参照', value: String(competitorCount), sub: '竞争与替代关系' },
  ];
}

export function buildNodeFrequencyBars(groups: AssociationMapGroup[]): NodeFrequencyBarItem[] {
  const items: NodeFrequencyBarItem[] = [];
  (['strong', 'growth', 'story', 'risk'] as const).forEach((key) => {
    const group = groups.find((g) => g.key === key);
    if (!group) return;
    group.nodes.slice(0, 4).forEach((node) => {
      const raw = node.answer_count || node.frequency_score || node.gravity_score || node.closeness_score || 0;
      const value = Number(raw) || 0;
      items.push({
        label: node.term,
        value,
        tone: key,
        countMode: nodeCountMode(node),
        valueLabel: `${value}${nodeCountShortUnit(node)}`,
      });
    });
  });
  items.sort((a, b) => b.value - a.value);
  return items.slice(0, 8);
}

export function nodeFrequencyChartTitle(items: NodeFrequencyBarItem[]): string {
  const modes = new Set(items.map((item) => item.countMode));
  if (modes.size === 1 && modes.has('answers')) return '节点频率（按去重回答数）';
  if (modes.size === 1 && modes.has('mentions')) return '节点频率（按节点提及次数）';
  if (modes.size === 1 && modes.has('lower_bound')) return '节点频率（按可确认回答下限）';
  return '节点出现量（答＝去重回答；答+＝可确认回答下限；次＝节点提及）';
}

export function reportBarToneColor(tone: string) {
  switch (tone) {
    case 'strong': return 'var(--brand-primary)';
    case 'growth': return 'var(--evidence-opportunity)';
    case 'story': return 'var(--text-tertiary)';
    case 'risk': return 'var(--error)';
    default: return 'var(--brand-primary)';
  }
}
