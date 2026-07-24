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
  cleanEvidenceExcerpt,
  clampNumber,
  commercialReportCopy,
  isCompetitorNode,
  nodeClosenessValue,
  nodeCountMode,
  nodeCountPhrase,
  nodeCountShortUnit,
  nodeDistanceValue,
  nodeEvidenceCount,
  nodePlatformCount,
  normalizeCenterTerms,
  platformLabel,
  relationshipRead,
  sampleAnswerCount,
  samplePlatformCount,
  sampleQuestionCount,
  scoreNumber,
  firstSampleNumber,
  uniqueStrings,
  type AssociationMapGroup,
  type AssociationMapGroupKey,
  type NodeCountSource,
} from './amway-circle';

// Re-export pure helpers and map entrypoint for existing importers of this shell file.
export {
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
};
export { CommercialOrbitView } from './amway-circle/CommercialOrbitView';


type ReportNarrativeSection = {
  sectionId?: string;
  title: string;
  text: string;
  readerQuestion?: string;
  takeaway?: string;
  claims?: string[];
  soWhat?: string;
  supportingFacts?: string[];
  evidenceRefs?: string[];
  nextProbe?: string;
};


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


function topTermsForReport(groups: AssociationMapGroup[], key: AssociationMapGroupKey, limit = 3) {
  return (groups.find((group) => group.key === key)?.nodes || [])
    .slice(0, limit)
    .map((node) => node.term)
    .filter(Boolean);
}

function sentenceJoin(items: string[], fallback: string) {
  if (!items.length) return fallback;
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join('、')}和${items[items.length - 1]}`;
}

function buildAssociationNarrativeReport({
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

function fallbackOverallStrategyStatus({
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

function normalizeReportNarrativeSections(
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

function readableNarrativeSections(
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


function buildQuestionDefinitionFallback(
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

function buildPlatformSourceSummaryFallback(
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

function buildEvidenceFindingsFallback(
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

function buildAnalysisTraceFallback(
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

function buildSourceAppendixFallback(
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

function buildReportQualityChecksFallback({
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


function readTrackingProjection(projection: OntologyAssociationCircleProjection) {
  const tracking = projection.tracking_projection;
  return tracking && typeof tracking === 'object' ? tracking as Record<string, unknown> : null;
}

function readPeriodView(projection: OntologyAssociationCircleProjection) {
  const tracking = readTrackingProjection(projection);
  const periodView = tracking?.period_view;
  return periodView && typeof periodView === 'object' ? periodView as Record<string, unknown> : null;
}

function buildPeriodScopeText(periodView: Record<string, unknown> | null | undefined) {
  return buildPeriodSummaryText(periodView?.current_period);
}

function buildPreviousPeriodScopeText(periodView: Record<string, unknown> | null | undefined) {
  return buildPeriodSummaryText(periodView?.previous_period);
}

function buildPeriodSummaryText(value: unknown) {
  if (!value || typeof value !== 'object') return '';
  const period = value as Record<string, unknown>;
  const runCount = Number(period.run_count || 0);
  const start = formatPeriodDate(period.start_at);
  const end = formatPeriodDate(period.end_at);
  const range = start && end ? `${start} 至 ${end}` : '当前可用周期';
  return `${range} / ${runCount || 0} 轮采集`;
}

function formatPeriodDate(value: unknown) {
  const text = String(value || '').trim();
  if (!text) return '';
  const date = new Date(text);
  if (Number.isNaN(date.getTime())) return text.slice(0, 10);
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(date);
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function periodChangeRows(periodView: Record<string, unknown> | null | undefined) {
  const rows = periodView?.change_top5;
  return Array.isArray(rows)
    ? rows.filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))
    : [];
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

function periodChangeLabel(value: string) {
  return {
    new: '新增',
    dropped: '消失',
    track_moved: '轨道变化',
    strengthened: '增强',
    weakened: '减弱',
  }[value] || '变化';
}

function signedNumber(value: unknown) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num === 0) return '0';
  return num > 0 ? `+${Math.round(num)}` : String(Math.round(num));
}

interface StrategyValidationRow {
  term: string;
  status: 'validated' | 'partial' | 'risk' | 'missing';
  statusLabel: string;
  validationLabel?: string;
  decisionTier?: string;
  stanceSummary?: OntologyAssociationCircleStrategyValidation['stance_summary'];
  intent: string;
  questionCount: number;
  relatedQuestions: OntologyAssociationCircleQuestion[];
  relatedNodes: OntologyAssociationCircleNode[];
  platformNames: string[];
  platformMentions: string[];
  answerResult: string;
  graphPerformance: string;
  implication: string;
  actionRecommendation?: string;
  evidenceRefs: string[];
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

function buildStrategyValidationRows({
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

function buildBackendStrategyValidationRows({
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

function buildFallbackStrategyValidationRows({
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

function isStrategyNode(node: OntologyAssociationCircleNode): boolean {
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

function buildFallbackPlatformMentions({
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

function buildBackendPlatformMentions(
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

function normalizeStrategyStatus(
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

function strategyStatusLabel(status: StrategyValidationRow['status']): string {
  if (status === 'validated') return '已被回答接住';
  if (status === 'partial') return '部分验证';
  if (status === 'risk') return '被风险遮蔽';
  return '尚未验证';
}

function strategyStanceLabel(stance?: string): string {
  if (stance === 'supportive') return '正向提及';
  if (stance === 'skeptical') return '质疑提及';
  if (stance === 'risk') return '风险提醒';
  if (stance === 'competitive') return '竞品替代';
  if (stance === 'neutral') return '中性提及';
  return '提及';
}

function strategyIntentText(term: string): string {
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

function strategyAnswerResultText({
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

function strategyGraphPerformanceText(nodes: OntologyAssociationCircleNode[]): string {
  if (!nodes.length) return '图谱上还没有形成稳定节点。';
  return nodes.slice(0, 4).map((node) => (
    `${node.term}位于${relationshipRead(node).label}，距离值 ${nodeDistanceValue(node)}，${nodeCountPhrase(node, nodeEvidenceCount(node))}，覆盖 ${nodePlatformCount(node)} 个平台`
  )).join('；');
}


function strategyImplication(
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

function strategyLane(term: string): 'relationship' | 'career' | 'green' | 'health' | 'general' {
  if (/财务|保障|事业|安利人|价值|再出发|成长/.test(term)) return 'career';
  if (/关系|陪伴|社群|一起/.test(term)) return 'relationship';
  if (/绿色|和谐|环境/.test(term)) return 'green';
  if (/健康|抗衰|长寿|活力|营养|身体|情绪|大健康/.test(term)) return 'health';
  return 'general';
}

function strategyMeaningFocus(
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

function strategyActionRecommendationText(
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

function isTemplateStrategyAction(text: string): boolean {
  return /补\s*2\s*条品牌锚定题和\s*2\s*条场景题/.test(text)
    || /补产品证据、使用场景和可复述案例/.test(text)
    || /下轮目标是进入稳定资产/.test(text);
}

function reportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  return /^(AI 原文|平台原文|平台原文样本)/.test(text);
}

function parseReportEvidenceLine(value: string) {
  const text = String(value || '').trim();
  const cleaned = text
    .replace(/^平台原文样本：/, '')
    .replace(/^平台原文：/, '')
    .replace(/^AI 原文：/, '');
  const platformMatch = cleaned.match(/^([^｜；:：]+)[｜；:：]/);
  const platform = platformMatch?.[1]?.trim() || '平台';
  const body = platformMatch ? cleaned.slice(platformMatch[0].length).trim() : cleaned;
  return { platform, body };
}

function reportPlatformAccent(platform: string) {
  const value = platform.toLowerCase();
  if (value.includes('豆包')) return '#1f7a6b';
  if (value.includes('元宝')) return '#4f7f72';
  if (value.includes('kimi')) return '#b9822d';
  if (value.includes('deepseek')) return '#586f9a';
  return '#1f7a6b';
}

function escapeRegexValue(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

function buildReportEntityTerms(
  groups: AssociationMapGroup[] | undefined,
  centerTerm?: string,
): string[] {
  const terms = new Set<string>();
  groups?.forEach((group) => {
    group.nodes.forEach((node) => {
      const term = String(node.term || '').trim();
      if (term.length >= 2) terms.add(term);
    });
  });
  ['豆包', '元宝', 'Kimi', 'DeepSeek', '安利', '安利中国', '纽崔莱'].forEach((term) => terms.add(term));
  if (centerTerm) {
    const trimmed = String(centerTerm).trim();
    if (trimmed.length >= 2) terms.add(trimmed);
  }
  return Array.from(terms).sort((a, b) => b.length - a.length);
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

function buildCoreVerdictMetrics(
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

interface NodeFrequencyBarItem {
  label: string;
  value: number;
  tone: 'strong' | 'growth' | 'story' | 'risk';
  countMode: ReturnType<typeof nodeCountMode>;
  valueLabel: string;
}

function buildNodeFrequencyBars(groups: AssociationMapGroup[]): NodeFrequencyBarItem[] {
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

function nodeFrequencyChartTitle(items: NodeFrequencyBarItem[]): string {
  const modes = new Set(items.map((item) => item.countMode));
  if (modes.size === 1 && modes.has('answers')) return '节点频率（按去重回答数）';
  if (modes.size === 1 && modes.has('mentions')) return '节点频率（按节点提及次数）';
  if (modes.size === 1 && modes.has('lower_bound')) return '节点频率（按可确认回答下限）';
  return '节点出现量（答＝去重回答；答+＝可确认回答下限；次＝节点提及）';
}

function reportBarToneColor(tone: string) {
  switch (tone) {
    case 'strong': return 'var(--brand-primary)';
    case 'growth': return 'var(--evidence-opportunity)';
    case 'story': return 'var(--text-tertiary)';
    case 'risk': return 'var(--error)';
    default: return 'var(--brand-primary)';
  }
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

function evidenceFindingCopy(
  value: string | null | undefined,
  finding: OntologyAssociationCircleEvidenceFinding,
  nodes: OntologyAssociationCircleNode[],
) {
  const copy = commercialReportCopy(value);
  const nodeTerm = commercialReportCopy(finding.node_term);
  const node = nodes.find((item) => (
    (finding.node_id && item.node_id === finding.node_id)
    || commercialReportCopy(item.term) === nodeTerm
  ));
  if (!node) return copy;
  const count = nodeEvidenceCount(node);
  if (!count) return copy;
  const countPhrase = nodeCountPhrase(node, count);
  const escapedTerm = escapeRegexValue(nodeTerm);
  let normalized = copy
    .replace(
      new RegExp(`${escapedTerm}已经被\\s*\\d+\\s*条回答稳定带回品牌`, 'g'),
      `${nodeTerm}已通过 ${countPhrase}进入稳定资产区`,
    )
    .replace(
      new RegExp(`${escapedTerm}已有\\s*\\d+\\s*条回答证据`, 'g'),
      `${nodeTerm}已有 ${countPhrase}`,
    )
    .replace(/\d+\s*条回答提及/g, countPhrase)
    .replace(/\d+\s*条回答提到/g, countPhrase)
    .replace(/本周期证据\s*\d+\s*条/g, `本周期按 ${countPhrase}计量`);
  if (nodeTerm === '监管合规质疑') {
    normalized = regulatoryScopedReportCopy(normalized, nodes, true);
  }
  return normalized;
}

function uniqueEvidenceFindingFacts(
  finding: OntologyAssociationCircleEvidenceFinding,
  nodes: OntologyAssociationCircleNode[],
  limit: number,
) {
  const canonicalize = (value: string) => value.replace(/[\s，。；、：:,.!?！？（）()]/g, '');
  const claim = evidenceFindingCopy(finding.claim, finding, nodes);
  const claimKey = canonicalize(claim);
  const seen = new Set<string>();
  const facts: string[] = [];
  for (const rawFact of finding.supporting_facts || []) {
    const fact = evidenceFindingCopy(rawFact, finding, nodes);
    const key = canonicalize(fact);
    if (!key || seen.has(key) || claimKey.includes(key)) continue;
    seen.add(key);
    facts.push(fact);
    if (facts.length >= limit) break;
  }
  return facts;
}

function regulatoryScopedReportCopy(
  value: string | null | undefined,
  nodes: OntologyAssociationCircleNode[],
  forceRegulatoryScope = false,
) {
  const copy = commercialReportCopy(value);
  if (!copy.includes('监管合规质疑') && !forceRegulatoryScope) return copy;
  const node = nodes.find((item) => item.entity_id === 'evidence_regulation');
  const count = node ? nodeEvidenceCount(node) : 0;
  if (!count) return copy;
  const countPhrase = node ? nodeCountPhrase(node, count) : `${count} 次节点提及`;
  const platformCount = node ? scoreNumber(node.platform_count) : 0;
  let normalized = copy
    .replace(
      /监管合规质疑被\s*\d+\s*条回答提到/g,
      `监管合规质疑以质疑或风险语境出现 ${countPhrase}`,
    )
    .replace(
      /监管合规质疑在\s*\d+\s*条回答中以质疑或风险语境出现/g,
      `监管合规质疑以质疑或风险语境出现 ${countPhrase}`,
    )
    .replace(
      /监管合规质疑（\s*\d+\s*(?:条回答|次节点提及|条可确认回答)\s*）/g,
      `监管合规质疑（${countPhrase}）`,
    );
  if (forceRegulatoryScope) {
    normalized = normalized
      .replace(/^\s*\d+\s*条回答提及/g, countPhrase)
      .replace(/^\s*\d+\s*次节点提及/g, countPhrase)
      .replace(/^\s*本周期证据\s*\d+\s*条/g, `本周期按 ${countPhrase}计量`)
      .replace(
        /覆盖\s*\d+\s*个平台/g,
        platformCount ? `覆盖 ${platformCount} 个平台` : '平台覆盖待复核',
      );
  }
  return normalized;
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
