'use client';

import type { ReportCanvasContent } from '@/types/canvas';
import type { ReactNode } from 'react';
import { ReportPage } from './ReportScaffold';

type MetricRow = [string, string, string];

type AssociationNode = {
  node_id?: string;
  term?: string;
  orbit?: string;
  orbit_label?: string;
  business_tag?: string;
  closeness_score?: number;
  distance_score?: number;
  answer_count?: number;
  evidence_count?: number;
  platform_count?: number;
  orbit_reason?: string;
};

type EvidenceSample = {
  evidence_id?: string;
  node_term?: string;
  platform?: string;
  question?: string;
  answer_excerpt?: string;
  probe_type?: string;
};

type PlatformComparison = {
  platform?: string;
  answer_preference?: string;
  dominant_orbit?: string;
  preferred_nodes?: string[];
  competition_nodes?: string[];
  risk_nodes?: string[];
  risk_bias?: string;
  opportunity_bias?: string;
  recommendation?: string;
};

type AssociationAction = {
  id?: string;
  action_label?: string;
  title?: string;
  node_term?: string;
  priority?: string;
  expected_impact?: string;
  review_criteria?: string;
  execution_steps?: string[];
  evidence_refs?: string[];
  next_question_suggestion?: string;
};

type ReportNarrativeSection = {
  title: string;
  text: string;
  supportingFacts?: string[];
  evidenceRefs?: string[];
};

type QuestionDefinition = {
  centerTerm?: string;
  questionCount?: number;
  audienceSegments: string[];
  probeTypes: string[];
  opportunityPoints: string[];
  lifeScenes: string[];
  sampleQuestions: Array<{
    id?: string;
    text?: string;
    audienceSegment?: string;
    probeType?: string;
    opportunityPoint?: string;
  }>;
  definitionSentence?: string;
};

type PlatformSourceRow = {
  platform?: string;
  totalAnswerCount?: number;
  validAnswerCount?: number;
  failedAnswerCount?: number;
  emptyAnswerCount?: number;
  answerPreference?: string;
  preferredNodes?: string[];
};

type PlatformSourceSummary = {
  totalAnswerCount?: number;
  validAnswerCount?: number;
  failedAnswerCount?: number;
  emptyAnswerCount?: number;
  platformCount?: number;
  platformNames: string[];
  platforms: PlatformSourceRow[];
};

type EvidenceFinding = {
  nodeId?: string;
  nodeTerm?: string;
  claim?: string;
  orbitLabel?: string;
  businessTag?: string;
  supportingFacts: string[];
  evidenceRefs: string[];
  samplePlatform?: string;
  sampleQuestion?: string;
  sampleExcerpt?: string;
  implication?: string;
};

type AnalysisTraceItem = {
  step?: string;
  title?: string;
  summary?: string;
  outputs: string[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function asNumber(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map(asString).filter((item) => item.length > 0)
    : [];
}

function formatUpdatedAt(value?: string) {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function getExecutiveSummary(content: ReportCanvasContent) {
  const summary = content.data.executive_summary;
  if (!isRecord(summary)) {
    return {
      oneLine: asString(content.data.subtitle),
      currentIdentity: '',
      primaryRisk: '',
      primaryOpportunity: '',
    };
  }
  const summaryRecord: Record<string, unknown> = summary;
  return {
    oneLine: asString(summaryRecord.one_line_judgment),
    currentIdentity: asString(summaryRecord.current_default_identity),
    primaryRisk: asString(summaryRecord.primary_risk),
    primaryOpportunity: asString(summaryRecord.primary_opportunity),
  };
}

function getMetricRows(content: ReportCanvasContent): MetricRow[] {
  const rows = content.data.summary_metrics;
  if (!Array.isArray(rows)) return [];
  return rows.filter(
    (row): row is MetricRow =>
      Array.isArray(row) &&
      row.length >= 3 &&
      typeof row[0] === 'string' &&
      typeof row[1] === 'string' &&
      typeof row[2] === 'string'
  );
}

function getAssociationNodes(content: ReportCanvasContent): AssociationNode[] {
  const circle = content.data.association_circle;
  if (!isRecord(circle) || !Array.isArray(circle.nodes)) return [];
  return circle.nodes.filter(isRecord).map((node) => ({
    node_id: asString(node.node_id),
    term: asString(node.term),
    orbit: asString(node.orbit),
    orbit_label: asString(node.orbit_label),
    business_tag: asString(node.business_tag),
    closeness_score: asNumber(node.closeness_score),
    distance_score: asNumber(node.distance_score),
    answer_count: asNumber(node.answer_count),
    evidence_count: asNumber(node.evidence_count),
    platform_count: asNumber(node.platform_count),
    orbit_reason: asString(node.orbit_reason),
  }));
}

function getEvidenceSamples(content: ReportCanvasContent): EvidenceSample[] {
  const circle = content.data.association_circle;
  if (!isRecord(circle) || !Array.isArray(circle.evidence_samples)) return [];
  return circle.evidence_samples.filter(isRecord).map((sample) => ({
    evidence_id: asString(sample.evidence_id),
    node_term: asString(sample.node_term),
    platform: asString(sample.platform),
    question: asString(sample.question),
    answer_excerpt: asString(sample.answer_excerpt),
    probe_type: asString(sample.probe_type),
  }));
}

function getPlatformComparison(content: ReportCanvasContent): PlatformComparison[] {
  const rows = content.data.platform_comparison;
  if (!Array.isArray(rows)) return [];
  return rows.filter(isRecord).map((row) => ({
    platform: asString(row.platform),
    answer_preference: asString(row.answer_preference),
    dominant_orbit: asString(row.dominant_orbit),
    preferred_nodes: asStringArray(row.preferred_nodes),
    risk_bias: asString(row.risk_bias),
    opportunity_bias: asString(row.opportunity_bias),
    recommendation: asString(row.recommendation),
  }));
}

function getAssociationActions(content: ReportCanvasContent): AssociationAction[] {
  const rows = content.data.association_actions;
  if (!Array.isArray(rows)) return [];
  return rows.filter(isRecord).map((row) => ({
    id: asString(row.id),
    action_label: asString(row.action_label),
    title: asString(row.title),
    node_term: asString(row.node_term),
    priority: asString(row.priority),
    expected_impact: asString(row.expected_impact),
    review_criteria: asString(row.review_criteria),
    execution_steps: asStringArray(row.execution_steps),
    evidence_refs: asStringArray(row.evidence_refs),
    next_question_suggestion: asString(row.next_question_suggestion),
  }));
}

function getReportNarrativeSections(content: ReportCanvasContent): ReportNarrativeSection[] {
  const rows = content.data.report_narrative_sections;
  if (!Array.isArray(rows)) return [];
  return rows
    .filter(isRecord)
    .map((row): ReportNarrativeSection | null => {
      const title = asString(row.title);
      const paragraphs = Array.isArray(row.paragraphs)
        ? row.paragraphs.map(asString).filter(Boolean)
        : [];
      const supportingFacts = asStringArray(row.supporting_facts);
      const evidenceRefs = asStringArray(row.evidence_refs);
      if (!title || !paragraphs.length) return null;
      return { title, text: paragraphs.join('\n\n'), supportingFacts, evidenceRefs };
    })
    .filter((section): section is ReportNarrativeSection => Boolean(section));
}

function getQuestionDefinition(content: ReportCanvasContent): QuestionDefinition | null {
  const raw = content.data.question_definition;
  if (!isRecord(raw)) return null;
  const sampleQuestions = Array.isArray(raw.sample_questions)
    ? raw.sample_questions.filter(isRecord).map((item) => ({
      id: asString(item.id),
      text: asString(item.text),
      audienceSegment: asString(item.audience_segment),
      probeType: asString(item.probe_type),
      opportunityPoint: asString(item.opportunity_point),
    })).filter((item) => item.text)
    : [];
  return {
    centerTerm: asString(raw.center_term),
    questionCount: asNumber(raw.question_count),
    audienceSegments: asStringArray(raw.audience_segments),
    probeTypes: asStringArray(raw.probe_types),
    opportunityPoints: asStringArray(raw.opportunity_points),
    lifeScenes: asStringArray(raw.life_scenes),
    sampleQuestions,
    definitionSentence: asString(raw.definition_sentence),
  };
}

function getPlatformSourceSummary(content: ReportCanvasContent): PlatformSourceSummary | null {
  const raw = content.data.platform_source_summary;
  if (!isRecord(raw)) return null;
  const platforms = Array.isArray(raw.platforms)
    ? raw.platforms.filter(isRecord).map((row) => ({
      platform: asString(row.platform),
      totalAnswerCount: asNumber(row.total_answer_count),
      validAnswerCount: asNumber(row.valid_answer_count),
      failedAnswerCount: asNumber(row.failed_answer_count),
      emptyAnswerCount: asNumber(row.empty_answer_count),
      answerPreference: asString(row.answer_preference),
      preferredNodes: asStringArray(row.preferred_nodes),
    }))
    : [];
  return {
    totalAnswerCount: asNumber(raw.total_answer_count),
    validAnswerCount: asNumber(raw.valid_answer_count),
    failedAnswerCount: asNumber(raw.failed_answer_count),
    emptyAnswerCount: asNumber(raw.empty_answer_count),
    platformCount: asNumber(raw.platform_count),
    platformNames: asStringArray(raw.platform_names),
    platforms,
  };
}

function getEvidenceFindings(content: ReportCanvasContent): EvidenceFinding[] {
  const rows = content.data.evidence_findings;
  if (!Array.isArray(rows)) return [];
  return rows.filter(isRecord).map((row) => ({
    nodeId: asString(row.node_id),
    nodeTerm: asString(row.node_term),
    claim: asString(row.claim),
    orbitLabel: asString(row.orbit_label),
    businessTag: asString(row.business_tag),
    supportingFacts: asStringArray(row.supporting_facts),
    evidenceRefs: asStringArray(row.evidence_refs),
    samplePlatform: asString(row.sample_platform),
    sampleQuestion: asString(row.sample_question),
    sampleExcerpt: asString(row.sample_excerpt),
    implication: asString(row.implication),
  })).filter((finding) => finding.nodeTerm || finding.claim);
}

function getAnalysisTrace(content: ReportCanvasContent): AnalysisTraceItem[] {
  const rows = content.data.analysis_tool_trace;
  if (!Array.isArray(rows)) return [];
  return rows.filter(isRecord).map((row) => ({
    step: asString(row.step),
    title: asString(row.title),
    summary: asString(row.summary),
    outputs: asStringArray(row.outputs),
  })).filter((item) => item.title || item.summary);
}

function chineseList(items: string[], fallback: string) {
  const clean = items.map((item) => item.trim()).filter(Boolean);
  if (!clean.length) return fallback;
  if (clean.length === 1) return clean[0];
  return `${clean.slice(0, -1).join('、')}和${clean[clean.length - 1]}`;
}

function isRiskAssociationNode(node: AssociationNode) {
  const text = `${node.term || ''} ${node.orbit || ''} ${node.orbit_label || ''} ${node.business_tag || ''}`;
  return /risk|风险|阴影|传销|智商税|夸大|压力|争议|负面/.test(text);
}

function isStrongAssociationNode(node: AssociationNode) {
  const text = `${node.orbit || ''} ${node.orbit_label || ''} ${node.business_tag || ''}`;
  return /core_near|strong|R1|强|当前资产|稳定|核心/.test(text) && !isRiskAssociationNode(node);
}

function isStoryAssociationNode(node: AssociationNode) {
  const text = `${node.term || ''} ${node.orbit || ''} ${node.orbit_label || ''} ${node.business_tag || ''}`;
  return /weak|blank|R3|弱|新叙事|证据不足|长寿|人生再出发|被需要|价值感/.test(text) && !isRiskAssociationNode(node);
}

function relationLabelForNode(node: AssociationNode) {
  if (isRiskAssociationNode(node)) return '风险认知';
  if (isStrongAssociationNode(node)) return '已绑定资产';
  if (isStoryAssociationNode(node)) return '弱信号 / 新叙事';
  return '可拉近机会';
}

function evidenceTextForNode(node: AssociationNode) {
  const answerCount = node.answer_count ?? node.evidence_count ?? 0;
  const platformCount = node.platform_count ?? 0;
  if (answerCount && platformCount) return `${answerCount} 条回答，${platformCount} 个平台`;
  if (answerCount) return `${answerCount} 条回答`;
  if (platformCount) return `${platformCount} 个平台`;
  return '样本待补充';
}

function topNodeTerms(nodes: AssociationNode[], predicate: (node: AssociationNode) => boolean, limit = 3) {
  return nodes.filter(predicate).slice(0, limit).map((node) => node.term || '').filter(Boolean);
}

function buildReportNarrative({
  headline,
  summary,
  nodes,
  platformComparison,
  evidenceSamples,
  associationActions,
}: {
  headline: string;
  summary: ReturnType<typeof getExecutiveSummary>;
  nodes: AssociationNode[];
  platformComparison: PlatformComparison[];
  evidenceSamples: EvidenceSample[];
  associationActions: AssociationAction[];
}): ReportNarrativeSection[] {
  const strongTerms = topNodeTerms(nodes, isStrongAssociationNode, 3);
  const opportunityTerms = topNodeTerms(
    nodes,
    (node) => !isStrongAssociationNode(node) && !isRiskAssociationNode(node) && !isStoryAssociationNode(node),
    3,
  );
  const storyTerms = topNodeTerms(nodes, isStoryAssociationNode, 2);
  const riskTerms = topNodeTerms(nodes, isRiskAssociationNode, 3);
  const platform = platformComparison[0];
  const evidence = evidenceSamples[0];
  const action = associationActions[0];

  return [
    {
      title: '先看回答把品牌放到哪里',
      text: [
        summary.oneLine || headline,
        '报告只读取回答中已经出现的词。近端词进入资产判断，机会词进入复测清单，风险词单独追踪。这样读，品牌能看到平台回答里的默认联想、证据路径和行动优先级。',
      ].join('\n\n'),
    },
    {
      title: '安利已经被稳定带出的资产',
      text: strongTerms.length
        ? `${chineseList(strongTerms, '')}是这一轮更稳定的品牌资产。它们反复和安利同框，已经能把回答带到健康、产品、社群或生活方式语境。`
        : '这一轮还没有形成非常稳定的第一反应。品牌需要更多可引用的公开证据，让平台回答有更可靠的抓手。',
    },
    {
      title: '机会正在形成，下一轮要看能否拉近',
      text: [
        opportunityTerms.length
          ? `${chineseList(opportunityTerms, '')}已经能通向品牌，但出现频率和平台一致性还不够稳。下一轮要看它们能否更稳定地回到中心品牌。`
          : '机会区暂时还不够集中，新的需求场景尚未被平台回答稳定带回品牌。',
        storyTerms.length
          ? `${chineseList(storyTerms, '')}更适合作为观察词。它们还没有成为成熟资产，可以放进下一轮问题和内容里继续看。`
          : '如果要建立新的品牌联想，下一轮要更多覆盖人群、生活场景和真实使用理由。',
      ].join('\n\n'),
    },
    {
      title: '风险会改变回答方向',
      text: riskTerms.length
        ? `${chineseList(riskTerms, '')}会把回答从健康和产品带到信任、争议或销售方式。风险管理要看触发次数、平台分布，以及有没有新的正向证据替代旧认知。`
        : '这一轮风险认知没有被明显放大。这个结果值得保留为基线，下一轮继续观察它是否会在具体问题或特定平台里重新出现。',
    },
    {
      title: '平台会选择不同解释入口',
      text: platform
        ? `${platform.platform || '某个平台'}这一轮偏向“${platform.answer_preference || '偏好待观察'}”。同一个品牌，在不同模型里会被带到不同入口：产品、健康、社群，或风险解释。`
        : '平台样本还不足时，先保留为观察项。等样本更完整后，这部分应该成为内容分发和证据建设的依据。',
    },
    {
      title: '下一步先抓一个节点',
      text: [
        evidence
          ? `先看一条原文证据：${evidence.platform || '某个平台'}在回答“${evidence.question || '相关问题'}”时，带出了“${evidence.node_term || '某个联想'}”。这句话能看到平台怎样组织答案，也能看到品牌该补哪类材料。`
          : '下一步仍然要保留原始回答。没有原文，圈层就只是一张图；有了原文，品牌才能知道该补哪条证据。',
        action
          ? `行动上，先抓住“${action.title || action.node_term || action.action_label || '优先节点'}”。先让一个节点在下一轮回答里变得更稳定，再扩到下一组节点。`
          : '行动上，先选一个机会节点补证据，再选一个风险节点做澄清，下轮用同一组问题复测。',
      ].join('\n\n'),
    },
  ];
}

function MetricStrip({ rows }: { rows: MetricRow[] }) {
  if (!rows.length) return null;
  return (
    <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-5" aria-label="核心指标">
      {rows.map(([label, value, description]) => (
        <article
          key={label}
          className="rounded-[12px] border bg-[var(--bg-report-muted)] px-5 py-5"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[13px] font-medium tracking-normal text-[var(--text-tertiary)]">
            {label}
          </div>
          <div className="mt-3 text-[30px] font-semibold tracking-normal text-[var(--text-primary)]">
            {value}
          </div>
          <p className="mt-2 text-[14px] leading-6 text-[var(--text-secondary)]">{description}</p>
        </article>
      ))}
    </section>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section
      className="rounded-[12px] border bg-[var(--bg-report)] px-6 py-6 md:px-8"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <h2 className="text-[24px] font-semibold tracking-normal text-[var(--text-primary)]">
        {title}
      </h2>
      <div className="mt-5">{children}</div>
    </section>
  );
}

function NarrativeReport({
  sections,
}: {
  sections: ReportNarrativeSection[];
}) {
  return (
    <article
      className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-8 md:px-10 md:py-10"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
        解读正文
      </div>
      <div className="mt-6 max-w-[900px] space-y-8">
        {sections.map((section) => (
          <section key={section.title} className="border-t border-[var(--border-subtle)] pt-7 first:border-t-0 first:pt-0">
            <h2
              className="text-[27px] font-semibold leading-snug tracking-normal text-[var(--text-primary)]"
              style={{ fontFamily: 'ui-serif, "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, serif' }}
            >
              {section.title}
            </h2>
            <div className="mt-4 space-y-4">
              {section.text.split(/\n{2,}/).map((paragraph) => (
                <p
                  key={paragraph}
                  className="text-[17px] leading-9 text-[var(--text-secondary)]"
                  style={{ fontFamily: 'ui-serif, "Noto Serif SC", "Source Han Serif SC", "Songti SC", Georgia, serif' }}
                >
                  {paragraph}
                </p>
              ))}
              {(section.supportingFacts || []).length ? (
                <div className="mt-5 rounded-[10px] border bg-[var(--bg-report-muted)] px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
                  <div className="text-[12px] font-medium text-[var(--text-tertiary)]">证据支撑</div>
                  <ul className="mt-2 space-y-1 text-[14px] leading-7 text-[var(--text-secondary)]">
                    {(section.supportingFacts || []).slice(0, 4).map((fact) => (
                      <li key={fact}>• {fact}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          </section>
        ))}
      </div>
    </article>
  );
}

function EvidenceFoundation({
  questionDefinition,
  platformSourceSummary,
  evidenceFindings,
  analysisTrace,
}: {
  questionDefinition: QuestionDefinition | null;
  platformSourceSummary: PlatformSourceSummary | null;
  evidenceFindings: EvidenceFinding[];
  analysisTrace: AnalysisTraceItem[];
}) {
  if (!questionDefinition && !platformSourceSummary && !evidenceFindings.length) {
    return null;
  }
  return (
    <section className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
      <article
        className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-6 md:px-8"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
          样本边界
        </div>
        <h2 className="mt-2 text-[26px] font-semibold text-[var(--text-primary)]">
          本轮先问了什么
        </h2>
        {questionDefinition?.definitionSentence ? (
          <p className="mt-4 text-[16px] leading-8 text-[var(--text-secondary)]">
            {questionDefinition.definitionSentence}
          </p>
        ) : null}
        <div className="mt-5 grid gap-3 md:grid-cols-2">
          <ScopeList title="人群" items={questionDefinition?.audienceSegments || []} />
          <ScopeList title="探针" items={questionDefinition?.probeTypes || []} />
          <ScopeList title="机会点" items={questionDefinition?.opportunityPoints || []} />
          <ScopeList title="生活场景" items={questionDefinition?.lifeScenes || []} />
        </div>
        {(questionDefinition?.sampleQuestions || []).length ? (
          <div className="mt-6">
            <div className="text-[13px] font-medium text-[var(--text-tertiary)]">代表问题</div>
            <div className="mt-3 space-y-3">
              {(questionDefinition?.sampleQuestions || []).slice(0, 5).map((item) => (
                <div
                  key={item.id || item.text}
                  className="rounded-[10px] border bg-[var(--bg-report-muted)] px-4 py-3"
                  style={{ borderColor: 'var(--border-subtle)' }}
                >
                  <p className="text-[15px] leading-7 text-[var(--text-primary)]">{item.text}</p>
                  <div className="mt-2 text-[12px] text-[var(--text-tertiary)]">
                    {[item.audienceSegment, item.probeType, item.opportunityPoint].filter(Boolean).join(' / ')}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </article>

      <aside className="space-y-5">
        <article
          className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-6"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
            平台来源
          </div>
          <h2 className="mt-2 text-[22px] font-semibold text-[var(--text-primary)]">
            答案从哪里来
          </h2>
          <div className="mt-4 grid grid-cols-2 gap-3">
            {[
              ['有效回答', platformSourceSummary?.validAnswerCount ?? 0],
              ['平台数', platformSourceSummary?.platformCount ?? 0],
              ['失败', platformSourceSummary?.failedAnswerCount ?? 0],
              ['空回答', platformSourceSummary?.emptyAnswerCount ?? 0],
            ].map(([label, value]) => (
              <div key={label} className="rounded-[10px] bg-[var(--bg-report-muted)] px-4 py-3">
                <div className="text-[12px] text-[var(--text-tertiary)]">{label}</div>
                <div className="mt-1 text-[24px] font-semibold text-[var(--text-primary)]">{value}</div>
              </div>
            ))}
          </div>
          {(platformSourceSummary?.platforms || []).length ? (
            <div className="mt-5 space-y-3">
              {(platformSourceSummary?.platforms || []).slice(0, 5).map((row) => (
                <div key={row.platform} className="border-t border-[var(--border-subtle)] pt-3 first:border-t-0 first:pt-0">
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-medium text-[var(--text-primary)]">{row.platform}</span>
                    <span className="text-[12px] text-[var(--text-tertiary)]">
                      {row.validAnswerCount || 0} 条有效
                    </span>
                  </div>
                  <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">
                    {row.answerPreference || '偏好待观察'}；{(row.preferredNodes || []).join('、') || '暂无代表节点'}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
        </article>

        {analysisTrace.length ? (
          <article
            className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-6"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
              分析轨迹
            </div>
            <div className="mt-4 space-y-4">
              {analysisTrace.slice(0, 5).map((item, index) => (
                <div key={item.step || item.title} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3">
                  <div className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--brand-bg)] text-[12px] font-semibold text-[var(--brand-text)]">
                    {index + 1}
                  </div>
                  <div>
                    <div className="text-[14px] font-medium text-[var(--text-primary)]">{item.title}</div>
                    <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">{item.summary}</p>
                  </div>
                </div>
              ))}
            </div>
          </article>
        ) : null}
      </aside>

      {evidenceFindings.length ? (
        <article
          className="xl:col-span-2 rounded-[16px] border bg-[var(--bg-report)] px-6 py-6 md:px-8"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
            证据链
          </div>
          <h2 className="mt-2 text-[26px] font-semibold text-[var(--text-primary)]">
            这些判断从哪些回答里来
          </h2>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            {evidenceFindings.slice(0, 6).map((finding) => (
              <article
                key={finding.nodeId || finding.nodeTerm}
                className="rounded-[12px] border bg-[var(--bg-report-muted)] p-5"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">{finding.nodeTerm}</h3>
                  {finding.businessTag ? (
                    <span className="rounded-full bg-[var(--brand-bg)] px-2.5 py-1 text-[12px] text-[var(--brand-text)]">
                      {finding.businessTag}
                    </span>
                  ) : null}
                </div>
                <p className="mt-3 text-[15px] leading-7 text-[var(--text-primary)]">{finding.claim}</p>
                <ul className="mt-3 space-y-1 text-[13px] leading-6 text-[var(--text-secondary)]">
                  {finding.supportingFacts.slice(0, 3).map((fact) => (
                    <li key={fact}>• {fact}</li>
                  ))}
                </ul>
                {finding.sampleExcerpt ? (
                  <blockquote className="mt-4 border-l-2 border-[var(--brand-border)] pl-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                    {finding.samplePlatform} / {finding.sampleQuestion}: {finding.sampleExcerpt}
                  </blockquote>
                ) : null}
              </article>
            ))}
          </div>
        </article>
      ) : null}
    </section>
  );
}

function ScopeList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="rounded-[10px] border bg-[var(--bg-report-muted)] px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="text-[12px] text-[var(--text-tertiary)]">{title}</div>
      <div className="mt-2 text-[14px] leading-6 text-[var(--text-primary)]">
        {items.length ? items.join('、') : '待补充'}
      </div>
    </div>
  );
}

export function BrandAssociationCircleContent({
  content,
}: {
  content: ReportCanvasContent;
  printMode?: boolean;
}) {
  const headline = content.data.title || content.data.headline || '品牌联想圈层报告';
  const updatedAt = formatUpdatedAt(content.data.updated_at);
  const centerTerms = asStringArray(content.data.center_terms);
  const summary = getExecutiveSummary(content);
  const metrics = getMetricRows(content);
  const nodes = getAssociationNodes(content);
  const platformComparison = getPlatformComparison(content);
  const evidenceSamples = getEvidenceSamples(content);
  const associationActions = getAssociationActions(content);
  const generatedNarrativeSections = getReportNarrativeSections(content);
  const questionDefinition = getQuestionDefinition(content);
  const platformSourceSummary = getPlatformSourceSummary(content);
  const evidenceFindings = getEvidenceFindings(content);
  const analysisTrace = getAnalysisTrace(content);
  const narrativeSections = generatedNarrativeSections.length ? generatedNarrativeSections : buildReportNarrative({
    headline,
    summary,
    nodes,
    platformComparison,
    evidenceSamples,
    associationActions,
  });

  return (
    <ReportPage className="w-full max-w-[1320px] space-y-6">
      <header
        className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-7 md:px-8 md:py-10"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="text-[12px] font-medium tracking-normal text-[var(--text-tertiary)]">
          品牌联想圈层全景报告
        </div>
        <h1 className="mt-3 text-[36px] font-semibold tracking-normal text-[var(--text-primary)]">
          {headline}
        </h1>
        {summary.oneLine ? (
          <p className="mt-5 max-w-[980px] text-[17px] leading-9 text-[var(--text-secondary)]">
            {summary.oneLine}
          </p>
        ) : null}
        <div className="mt-6 grid gap-3 md:grid-cols-3">
          {[
            ['当前认知底盘', summary.currentIdentity],
            ['主要风险', summary.primaryRisk],
            ['主要机会', summary.primaryOpportunity],
          ].map(([label, value]) =>
            value ? (
              <div
                key={label}
                className="rounded-[10px] border bg-[var(--bg-report-muted)] px-4 py-3"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="text-[12px] text-[var(--text-tertiary)]">{label}</div>
                <div className="mt-1 text-[14px] leading-6 text-[var(--text-primary)]">{value}</div>
              </div>
            ) : null
          )}
        </div>
        <div className="mt-5 flex flex-wrap gap-2 text-[14px] text-[var(--text-secondary)]">
          {centerTerms.map((term) => (
            <span
              key={term}
              className="rounded-full border px-3 py-1"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              {term}
            </span>
          ))}
          {updatedAt ? <span className="px-1 py-1">更新于 {updatedAt}</span> : null}
        </div>
      </header>

      <MetricStrip rows={metrics} />

      <EvidenceFoundation
        questionDefinition={questionDefinition}
        platformSourceSummary={platformSourceSummary}
        evidenceFindings={evidenceFindings}
        analysisTrace={analysisTrace}
      />

      <NarrativeReport sections={narrativeSections} />

      <Section title="节点证据清单">
        <div className="grid gap-4 lg:grid-cols-3">
          {nodes.slice(0, 9).map((node) => (
            <article
              key={node.node_id || node.term}
              className="rounded-[10px] border bg-[var(--bg-report-muted)] p-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="text-[18px] font-semibold text-[var(--text-primary)]">{node.term}</div>
                  <div className="mt-1 text-[13px] text-[var(--text-tertiary)]">
                    {node.orbit} {node.orbit_label}
                  </div>
                </div>
                <span className="rounded-full bg-[var(--brand-bg)] px-3 py-1 text-[13px] text-[var(--brand-text)]">
                  {node.business_tag}
                </span>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3 text-[14px]">
                <div>
                  <div className="text-[var(--text-tertiary)]">关系状态</div>
                  <div className="mt-1 text-[22px] font-semibold text-[var(--text-primary)]">
                    {relationLabelForNode(node)}
                  </div>
                </div>
                <div>
                  <div className="text-[var(--text-tertiary)]">回答出现</div>
                  <div className="mt-1 text-[22px] font-semibold text-[var(--text-primary)]">
                    {evidenceTextForNode(node)}
                  </div>
                </div>
              </div>
              <p className="mt-4 text-[14px] leading-7 text-[var(--text-secondary)]">
                {node.orbit_reason}
              </p>
            </article>
          ))}
        </div>
      </Section>

      <Section title="平台差异">
        <div className="overflow-x-auto">
          <table className="min-w-full border-collapse text-left text-[14px]">
            <thead className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">
              <tr>
                <th className="px-3 py-3 font-medium">平台</th>
                <th className="px-3 py-3 font-medium">回答偏好</th>
                <th className="px-3 py-3 font-medium">代表节点</th>
                <th className="px-3 py-3 font-medium">主要轨道</th>
                <th className="px-3 py-3 font-medium">建议动作</th>
              </tr>
            </thead>
            <tbody>
              {platformComparison.map((item) => (
                <tr key={item.platform} className="border-b border-[var(--border-subtle)]">
                  <td className="px-3 py-4 align-top font-medium text-[var(--text-primary)]">
                    {item.platform}
                  </td>
                  <td className="px-3 py-4 align-top leading-7 text-[var(--text-secondary)]">
                    {item.answer_preference}
                  </td>
                  <td className="px-3 py-4 align-top leading-7 text-[var(--text-primary)]">
                    {(item.preferred_nodes || []).join('、') || '-'}
                  </td>
                  <td className="px-3 py-4 align-top text-[var(--text-primary)]">
                    {item.dominant_orbit}
                  </td>
                  <td className="px-3 py-4 align-top leading-7 text-[var(--text-secondary)]">
                    {item.recommendation}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section title="证据样本">
        <div className="space-y-4">
          {evidenceSamples.slice(0, 8).map((sample) => (
            <article
              key={sample.evidence_id}
              className="rounded-[10px] border bg-[var(--bg-report-muted)] p-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex flex-wrap gap-2 text-[13px] text-[var(--text-tertiary)]">
                <span>{sample.node_term}</span>
                <span>{sample.platform}</span>
                <span>{sample.probe_type}</span>
              </div>
              <p className="mt-3 text-[15px] leading-7 text-[var(--text-primary)]">
                {sample.question}
              </p>
              <p className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
                {sample.answer_excerpt}
              </p>
            </article>
          ))}
        </div>
      </Section>

      {associationActions.length ? (
        <Section title="圈层行动">
          <div className="grid gap-4 lg:grid-cols-3">
            {associationActions.slice(0, 6).map((action) => (
              <article
                key={action.id || action.title}
                className="rounded-[10px] border bg-[var(--bg-report-muted)] p-5"
                style={{ borderColor: 'var(--border-subtle)' }}
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded-full bg-[var(--brand-bg)] px-3 py-1 text-[13px] text-[var(--brand-text)]">
                    {action.action_label || '跟进行动'}
                  </span>
                  {action.priority ? (
                    <span className="text-[13px] text-[var(--text-tertiary)]">{action.priority}</span>
                  ) : null}
                </div>
                <h3 className="mt-3 text-[18px] font-semibold text-[var(--text-primary)]">
                  {action.title || action.node_term}
                </h3>
                {action.expected_impact ? (
                  <p className="mt-3 text-[14px] leading-7 text-[var(--text-secondary)]">
                    {action.expected_impact}
                  </p>
                ) : null}
                {(action.execution_steps || []).length ? (
                  <ol className="mt-3 list-decimal space-y-1 pl-4 text-[14px] leading-7 text-[var(--text-secondary)]">
                    {(action.execution_steps || []).slice(0, 3).map((step, index) => (
                      <li key={`${action.id || action.title}-step-${index}`}>{step}</li>
                    ))}
                  </ol>
                ) : null}
                {action.next_question_suggestion ? (
                  <p className="mt-3 text-[13px] leading-6 text-[var(--text-tertiary)]">
                    {action.next_question_suggestion}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        </Section>
      ) : null}
    </ReportPage>
  );
}
