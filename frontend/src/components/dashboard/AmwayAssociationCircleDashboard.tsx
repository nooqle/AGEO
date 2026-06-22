import { useMemo, useState, type ChangeEvent } from 'react';
import { RefreshCw, Upload } from 'lucide-react';
import type { DashboardHomeData } from '@/types/dashboard';
import type { Entity } from '@/types/entity';
import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import type { StageResult } from '@/types/snapshot';
import type { AnalysisTask } from '@/types/task';
import type {
  OntologyAssociationCircleEvidence,
  OntologyAssociationCircleEvidenceFinding,
  OntologyAssociationCircleNode,
  OntologyAssociationCirclePlatformComparison,
  OntologyAssociationCircleProjection,
  OntologyAssociationCircleSourceAppendixItem,
  OntologyWorldSummary,
} from '@/types/ontology';
import {
  parseUploadedQuestionFile,
  parseUploadedQuestionTableViaBackend,
} from './amwayQuestionBank';
import {
  AssociationProjectionLoadingPanel,
  AssociationReportPanel,
  CommercialOrbitView,
  InfoPill,
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
} from './AmwayAssociationCircleDashboardViews';

type CircleStatus = 'empty' | 'loading' | 'ready';

export interface UploadedAssociationQuestion {
  id: string;
  text: string;
  category?: string;
  intent?: string;
  stage?: string;
  audience_segment?: string;
  core_anxiety?: string;
  life_scene?: string;
  opportunity_point?: string;
  probe_type?: string;
  mother_theme?: string;
  question_type?: string;
  mentions_amway?: string;
  life_stage?: string;
  four_have?: string;
  touchpoint?: string;
  monitoring_purpose?: string;
  center_terms?: string[];
  question_set_version?: string;
  metadata_status?: string;
  source?: string;
}

export interface AssociationCircleStartPayload {
  uploadedQuestions?: UploadedAssociationQuestion[];
  uploadedQuestionSource?: string | null;
}

interface AmwayAssociationCircleDashboardProps {
  entities: Entity[];
  selectedEntity: Entity;
  selectedEntityId: string | null;
  centerOptions: string[];
  selectedCenterTerm: string | null;
  home?: DashboardHomeData | null;
  world?: OntologyWorldSummary | null;
  activeRun?: BrandIntelligenceRun | null;
  activeTask?: AnalysisTask | null;
  isRunActive?: boolean;
  isRunSubmitting?: boolean;
  isProjectionLoading?: boolean;
  runError?: string | null;
  liveStageResults?: StageResult[];
  onSelectEntity: (entityId: string) => void;
  onSelectCenterTerm: (term: string) => void;
  onStart: (payload?: AssociationCircleStartPayload) => void;
  onOpenLatestReport: () => void;
}

export function AmwayAssociationCircleDashboard({
  centerOptions,
  selectedCenterTerm,
  home,
  world,
  activeRun,
  activeTask,
  isRunActive,
  isRunSubmitting,
  isProjectionLoading,
  runError,
  liveStageResults = [],
  onSelectCenterTerm,
  onStart,
}: AmwayAssociationCircleDashboardProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [uploadedQuestions, setUploadedQuestions] = useState<UploadedAssociationQuestion[]>([]);
  const [uploadedQuestionSource, setUploadedQuestionSource] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isReadingUpload, setIsReadingUpload] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const officialProjection = useMemo(() => buildAssociationProjection(world, home), [home, world]);
  const centerTerms = normalizeCenterTerms(centerOptions.length ? centerOptions : officialProjection.center_terms);
  const activeCenterTerm = selectedCenterTerm && centerTerms.includes(selectedCenterTerm)
    ? selectedCenterTerm
    : centerTerms[0] || '安利';
  const combinedLiveStageResults = useMemo(
    () => mergeStageResults(activeTask?.stage_results_cache || [], liveStageResults),
    [activeTask?.stage_results_cache, liveStageResults],
  );
  const liveProjection = useMemo(
    () => buildLiveAssociationProjection(combinedLiveStageResults, activeCenterTerm, centerTerms),
    [activeCenterTerm, combinedLiveStageResults, centerTerms],
  );
  const targetPlatforms = useMemo(
    () => normalizeTargetPlatformIds(activeRun?.input_scope?.platforms),
    [activeRun?.input_scope],
  );
  const projection = isRunActive ? liveProjection : officialProjection;
  const nodes = useMemo(() => projection.nodes || [], [projection.nodes]);
  const mapGroups = useMemo(() => buildAssociationMapGroups(nodes), [nodes]);
  const strategyTerms = useMemo(() => buildAssociationStrategyTerms(projection), [projection]);
  const status: CircleStatus = isRunActive
    ? (nodes.length > 0 ? 'ready' : 'empty')
    : isProjectionLoading ? 'loading' : nodes.length > 0 ? 'ready' : 'empty';
  const selectedNode =
    nodes.find((node) => node.node_id === selectedNodeId) ||
    null;
  const sampleScope = projection.sample_scope || {};
  const evidenceSamples = projection.evidence_samples || [];
  const evidenceFindings = projection.evidence_findings || [];
  const sourceAppendix = projection.source_appendix || [];
  const questionBank = projection.question_bank || [];
  const answerCount = sampleAnswerCount(sampleScope);
  const targetQuestionCount = numericSampleValue(activeRun?.input_scope?.uploaded_question_count) || uploadedQuestions.length || questionBank.length || 0;
  const targetPlatformCount = targetPlatforms.length || samplePlatformCountFromScope(sampleScope);
  const liveQuestionCount = sampleQuestionCountFromScope(sampleScope) || 0;
  const hasA5Report = Boolean(
    projection.report_id
      && projection.generated_from === 'entity_calibration'
      && (projection.report_narrative_sections || []).length >= 6,
  );
  const headerStatusLabel = isRunSubmitting || isRunActive
    ? nodes.length > 0 ? '实时抽取中' : '正在抓取'
    : status === 'loading'
      ? '正在读取报告'
    : status === 'ready'
      ? '圈层已生成'
      : '等待题目与抓取';
  const handleStart = () => {
    setIsReportOpen(false);
    onStart({
      uploadedQuestions: uploadedQuestions.map((question) => ({
        ...question,
        center_terms: [activeCenterTerm],
      })),
      uploadedQuestionSource,
    });
  };
  const handleQuestionFileChange = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    setIsReadingUpload(true);
    try {
      const lowerName = file.name.toLowerCase();
      const parsed = lowerName.endsWith('.xlsx') || lowerName.endsWith('.csv')
        ? await parseUploadedQuestionTableViaBackend(file, [activeCenterTerm])
        : parseUploadedQuestionFile(await file.text(), [activeCenterTerm]);
      if (!parsed.length) {
        setUploadError('没有识别到有效问题。请上传每行一个问题的 TXT，或包含问题列的 CSV/XLSX。');
        setUploadedQuestions([]);
        setUploadedQuestionSource(null);
        return;
      }
      setUploadError(null);
      setIsReportOpen(false);
      setUploadedQuestions(parsed);
      setUploadedQuestionSource(file.name);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : '问题列表读取失败，请检查文件格式后重新上传。');
      setUploadedQuestions([]);
      setUploadedQuestionSource(null);
    } finally {
      setIsReadingUpload(false);
    }
  };

  const isModeling = Boolean(isRunSubmitting || isRunActive);
  const runButtonLabel = isModeling ? '运行中' : status === 'loading' ? '读取中' : status === 'ready' ? '重新生成图谱' : '生成图谱';

  return (
    <div className="min-h-screen bg-[var(--bg-secondary)] text-[var(--text-primary)]">
      <header className="sticky top-0 z-30 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)]/96">
        <div className="mx-auto flex h-16 max-w-[1920px] items-center justify-between gap-4 px-5 lg:px-7 2xl:px-10">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[var(--brand-primary)] text-sm font-semibold text-[var(--brand-contrast)]">
              S
            </div>
            <div className="min-w-0">
              <div className="text-sm font-semibold leading-5">Specta AI</div>
              <div className="truncate text-xs text-[var(--text-tertiary)]">安利品牌圈层</div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2 text-sm text-[var(--text-secondary)]">
              <span className="font-medium text-[var(--brand-primary)]">{headerStatusLabel}</span>
              {status === 'ready' ? (
                <span className="ml-2 text-[var(--text-tertiary)]">
                  {answerCount || '-'} 条回答 / {nodes.length} 个节点
                </span>
              ) : null}
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1920px] min-w-0 px-5 py-4 lg:px-7 2xl:px-10">
        <section className="min-w-0 space-y-4">
          {runError ? (
            <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-4 text-sm text-[var(--text-secondary)]">
              {runError}
            </div>
          ) : null}

          <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-5 sm:p-6">
            <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_420px]">
              <div className="max-w-5xl">
                <div className="text-xs font-medium text-[var(--text-tertiary)]">安利专属</div>
                <h1 className="mt-1 text-3xl font-semibold leading-tight">品牌联想图谱</h1>
                <p className="mt-3 max-w-4xl text-sm leading-7 text-[var(--text-secondary)]">
                  上传问题，生成图谱，再生成报告。页面只保留这条主线；节点和报告都来自抓取回答后的解析结果。
                </p>
                <div className="mt-4 flex flex-wrap items-center gap-2 text-sm">
                  <InfoPill label="题库目标" value={`${targetQuestionCount || '-'} 题 / ${targetPlatformCount || '-'} 平台`} />
                  <InfoPill label="实时样本" value={`${liveQuestionCount || '-'} 题 / ${answerCount || '-'} 回答 / ${nodes.length || '-'} 节点`} />
                  <InfoPill label="位置判断" value="由回答证据决定" tone="warning" />
                </div>
              </div>

              <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                <div className="text-xs font-medium text-[var(--text-tertiary)]">观察品牌</div>
                <div className="mt-3 grid gap-2">
                  {centerTerms.map((term) => (
                    <button
                      key={term}
                      type="button"
                      onClick={() => {
                        onSelectCenterTerm(term);
                        setSelectedNodeId(null);
                      }}
                      className="flex items-center justify-between rounded-xl border px-3 py-2 text-left text-sm transition"
                      style={{
                        borderColor: term === activeCenterTerm ? 'var(--brand-primary)' : 'var(--border-subtle)',
                        background: term === activeCenterTerm ? 'var(--brand-bg)' : 'var(--bg-primary)',
                        color: term === activeCenterTerm ? 'var(--brand-primary)' : 'var(--text-secondary)',
                      }}
                    >
                      <span className="font-semibold">{term}</span>
                      <span className="text-xs">{term === activeCenterTerm ? '当前' : '切换'}</span>
                    </button>
                  ))}
                </div>
                <div className="mt-4 flex flex-wrap gap-2">
                  <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-xl border border-[var(--brand-border)] bg-[var(--bg-primary)] px-3 text-sm font-medium text-[var(--brand-primary)] hover:bg-[var(--brand-bg)]">
                    <Upload size={15} />
                    {isReadingUpload ? '正在读取' : '上传问题'}
                    <input
                      type="file"
                      accept=".csv,.xlsx,.txt,text/csv,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                      className="sr-only"
                      disabled={isReadingUpload}
                      onChange={handleQuestionFileChange}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={handleStart}
                    disabled={isRunSubmitting || status === 'loading'}
                    className="inline-flex h-10 items-center gap-2 rounded-xl bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-60"
                  >
                    <RefreshCw size={15} />
                    {runButtonLabel}
                  </button>
                </div>
                {uploadError ? (
                  <p className="mt-3 text-xs leading-5 text-[var(--error)]">{uploadError}</p>
                ) : null}
                {uploadedQuestionSource ? (
                  <p className="mt-3 text-xs leading-5 text-[var(--text-tertiary)]">
                    已读取：{uploadedQuestionSource}
                  </p>
                ) : null}
              </div>
            </div>
          </section>

          {status === 'loading' ? (
            <AssociationProjectionLoadingPanel centerTerm={activeCenterTerm} />
          ) : (
            <div className="space-y-5">
              <CommercialOrbitView
                centerTerm={activeCenterTerm}
                groups={mapGroups}
                selectedNode={selectedNode}
                selectedNodeId={selectedNode?.node_id || null}
                sampleScope={sampleScope}
                targetPlatforms={targetPlatforms}
                liveProgressMessage={activeTask?.progress_message || activeRun?.message || null}
                liveCurrentStage={activeTask?.current_stage || activeRun?.stage || null}
                evidenceSamples={evidenceSamples}
                evidenceFindings={evidenceFindings}
                sourceAppendix={sourceAppendix}
                strategyTerms={strategyTerms}
                prioritySummary={projection.priority_summary || null}
                onSelectNode={setSelectedNodeId}
              />

              {isReportOpen ? (
                <section id="strategy-report">
                  <AssociationReportPanel
                    projection={projection}
                    activeCenterTerm={activeCenterTerm}
                    groups={mapGroups}
                  />
                </section>
              ) : (
                <ReportGenerationGate
                  disabled={isModeling || !nodes.length}
                  activeCenterTerm={activeCenterTerm}
                  answerCount={answerCount}
                  nodeCount={nodes.length}
                  isModeling={isModeling}
                  hasA5Report={hasA5Report}
                  onGenerate={() => setIsReportOpen(true)}
                />
              )}
            </div>
          )}
        </section>
      </main>
    </div>
  );
}

function buildAssociationStrategyTerms(projection: OntologyAssociationCircleProjection) {
  const terms = new Set<string>();
  const add = (value?: string | null) => {
    const text = String(value || '').trim();
    if (text) terms.add(text);
  };
  (projection.question_definition?.opportunity_points || []).forEach(add);
  (projection.question_bank || []).forEach((question) => {
    add(question.opportunity_point);
    add(question.mother_theme);
  });
  (projection.source_appendix || []).forEach((item) => {
    add(item.opportunity_point);
  });
  (projection.nodes || []).forEach((node) => {
    if (node.is_target_term) add(node.term);
  });
  return Array.from(terms);
}

function mergeStageResults(primary: StageResult[], secondary: StageResult[]): StageResult[] {
  if (!primary.length) return secondary;
  if (!secondary.length) return primary;
  const merged: StageResult[] = [];
  const seen = new Set<string>();
  [...primary, ...secondary].forEach((item) => {
    const key = stageResultStableKey(item);
    if (seen.has(key)) return;
    seen.add(key);
    merged.push(item);
  });
  return merged;
}

function stageResultStableKey(item: StageResult): string {
  const resultType = String(item.result_type || item.resultType || '').trim();
  const data = item.data || {};
  const answerId = String(data.answer_id || '').trim();
  if (resultType === 'entity_extraction_signal' && answerId) {
    return `${resultType}:${answerId}`;
  }
  const generatedFrom = String(data.generated_from || '').trim();
  const timestamp = String(item.timestamp || '').trim();
  return `${item.stage || ''}:${resultType}:${generatedFrom}:${timestamp}`;
}

type LiveSignal = {
  entity_name?: string;
  entity_type?: string;
  matched_text?: string;
  relation_type?: string;
  term_origin?: string;
  evidence_text?: string;
  answer_position?: string;
};

type LiveNodeAccumulator = {
  term: string;
  entityType: string;
  termOrigin: string;
  answerIds: Set<string>;
  questionIds: Set<string>;
  platforms: Map<string, number>;
  relationTypes: Map<string, number>;
  samples: OntologyAssociationCircleEvidence[];
};

function buildLiveAssociationProjection(
  stageResults: StageResult[],
  centerTerm: string,
  blockedCenterTerms: string[] = [centerTerm],
): OntologyAssociationCircleProjection {
  const accumulators = new Map<string, LiveNodeAccumulator>();
  let signalCount = 0;
  const blockedTerms = new Set(blockedCenterTerms.filter(Boolean));

  stageResults.forEach((stageResult) => {
    const resultType = stageResult.result_type || stageResult.resultType;
    if (resultType !== 'entity_extraction_signal') return;
    const data = stageResult.data || {};
    const answerId = stringValue(data.answer_id);
    const questionId = stringValue(data.question_id);
    const question = stringValue(data.question);
    const platform = normalizeLivePlatform(stringValue(data.platform));
    const signals = Array.isArray(data.signals) ? data.signals : [];

    signals.forEach((item) => {
      const signal = item as LiveSignal;
      const term = stringValue(signal.entity_name || signal.matched_text);
      if (!term) return;
      if (blockedTerms.has(term)) return;
      const entityType = stringValue(signal.entity_type) || 'Entity';
      if (entityType === 'CenterBrand') return;
      signalCount += 1;
      const key = `${entityType}:${term}`;
      const accumulator = accumulators.get(key) || {
        term,
        entityType,
        termOrigin: stringValue(signal.term_origin) || 'answer',
        answerIds: new Set<string>(),
        questionIds: new Set<string>(),
        platforms: new Map<string, number>(),
        relationTypes: new Map<string, number>(),
        samples: [],
      };
      if (answerId) accumulator.answerIds.add(answerId);
      if (questionId) accumulator.questionIds.add(questionId);
      if (platform) accumulator.platforms.set(platform, (accumulator.platforms.get(platform) || 0) + 1);
      const relationType = stringValue(signal.relation_type);
      if (relationType) accumulator.relationTypes.set(relationType, (accumulator.relationTypes.get(relationType) || 0) + 1);
      if (accumulator.samples.length < 6) {
        accumulator.samples.push({
          evidence_id: `live_${safeLiveId(term)}_${accumulator.samples.length + 1}`,
          node_id: `live_${safeLiveId(term)}`,
          node_term: term,
          platform,
          question_id: questionId,
          question,
          answer_excerpt: cleanLiveExcerpt(stringValue(signal.evidence_text)),
          answer_position: stringValue(signal.answer_position),
          relation_type: relationType,
          evidence_strength: 'live_preview',
        });
      }
      accumulators.set(key, accumulator);
    });
  });

  const evidenceSamples: OntologyAssociationCircleEvidence[] = [];
  const sourceAppendix: OntologyAssociationCircleSourceAppendixItem[] = [];
  const nodes = Array.from(accumulators.values()).map((accumulator): OntologyAssociationCircleNode => {
    const answerCount = accumulator.answerIds.size;
    const platformCount = accumulator.platforms.size;
    const relationTypes = Object.fromEntries(accumulator.relationTypes.entries());
    const isRisk = liveNodeIsRisk(accumulator);
    const closeness = clampMetric(24 + answerCount * 5 + platformCount * 10);
    const distance = clampMetric(100 - closeness);
    const nodeId = `live_${safeLiveId(accumulator.term)}`;
    accumulator.samples.forEach((sample) => {
      evidenceSamples.push({ ...sample, node_id: nodeId });
      sourceAppendix.push({
        evidence_id: sample.evidence_id,
        node_term: accumulator.term,
        platform: sample.platform,
        question_id: sample.question_id,
        question: sample.question,
        answer_excerpt: sample.answer_excerpt,
      });
    });
    return {
      node_id: nodeId,
      entity_type: accumulator.entityType,
      term: accumulator.term,
      orbit: isRisk ? 'risk_shadow' : closeness >= 62 ? 'strong' : closeness >= 44 ? 'contestable' : 'weak',
      orbit_label: isRisk ? '风险认知' : closeness >= 62 ? '稳定联想' : closeness >= 44 ? '正在形成' : '弱信号',
      business_tag: liveEntityTypeLabel(accumulator.entityType),
      association_score: closeness,
      gravity_score: closeness,
      closeness_score: closeness,
      distance_score: distance,
      frequency_score: clampMetric(answerCount * 8),
      model_consistency_score: clampMetric(platformCount * 25),
      relation_type_score: clampMetric(answerCount * 6 + platformCount * 6),
      semantic_direction: isRisk ? '风险认知' : '回答抽取中的品牌联想',
      is_risk_term: isRisk,
      is_target_term: accumulator.termOrigin === 'strategy',
      answer_count: answerCount,
      platform_count: platformCount,
      platform_distribution: Object.fromEntries(accumulator.platforms.entries()),
      relation_type_distribution: relationTypes,
      trigger_questions: Array.from(accumulator.questionIds).slice(0, 8),
      evidence_samples: accumulator.samples.map((sample) => sample.evidence_id || '').filter(Boolean),
      evidence_count: answerCount,
      evidence_strength: 'live_preview',
      orbit_reason: '抓取过程中实时抽取到的实体信号，最终位置会在校准后确认。',
      source: 'realtime_entity_extraction',
      term_origin: accumulator.termOrigin,
      origin_label: accumulator.termOrigin === 'strategy' ? '战略词' : '回答词',
    };
  }).sort((left, right) => (right.closeness_score || 0) - (left.closeness_score || 0));

  const platformComparison = buildLivePlatformComparison(nodes);
  const questionIds = new Set<string>();
  const answerIds = new Set<string>();
  nodes.forEach((node) => {
    (node.trigger_questions || []).forEach((questionId) => questionIds.add(questionId));
    (node.evidence_samples || []).forEach((evidenceId) => {
      const sample = evidenceSamples.find((item) => item.evidence_id === evidenceId);
      if (sample?.question_id) questionIds.add(sample.question_id);
    });
  });
  stageResults.forEach((stageResult) => {
    if ((stageResult.result_type || stageResult.resultType) !== 'entity_extraction_signal') return;
    const data = stageResult.data || {};
    const answerId = stringValue(data.answer_id);
    const questionId = stringValue(data.question_id);
    if (answerId) answerIds.add(answerId);
    if (questionId) questionIds.add(questionId);
  });

  const evidenceFindings: OntologyAssociationCircleEvidenceFinding[] = nodes.slice(0, 12).map((node) => ({
    node_id: node.node_id,
    node_term: node.term,
    claim: `${node.term} 已在抓取过程中出现 ${node.answer_count || 0} 次，覆盖 ${node.platform_count || 0} 个平台。`,
    orbit: node.orbit,
    orbit_label: node.orbit_label,
    supporting_facts: [
      `回答命中：${node.answer_count || 0}`,
      `有效平台数：${node.platform_count || 0}`,
    ],
    evidence_refs: node.evidence_samples,
    sample_platform: evidenceSamples.find((sample) => sample.node_id === node.node_id)?.platform,
    sample_question: evidenceSamples.find((sample) => sample.node_id === node.node_id)?.question,
    sample_excerpt: evidenceSamples.find((sample) => sample.node_id === node.node_id)?.answer_excerpt,
    implication: '运行中预览，最终结论等待校准汇总确认。',
  }));

  return {
    dashboard_variant: 'amway_association_circle',
    analysis_mode: 'brand_association_circle',
    report_kind: 'brand_association_circle',
    status: 'live_preview',
    center_terms: [centerTerm],
    nodes,
    evidence_samples: evidenceSamples,
    question_bank: [],
    platform_comparison: platformComparison,
    association_actions: [],
    report_narrative_sections: [],
    evidence_findings: evidenceFindings,
    analysis_tool_trace: [{
      step: 'EntityExtraction',
      title: '实时实体抽取',
      summary: `已收到 ${stageResults.length} 条阶段事件，抽取 ${signalCount} 个实体信号。`,
      outputs: ['live_preview_projection'],
    }],
    report_outline: [],
    strategy_validation: [],
    source_appendix: sourceAppendix,
    sample_scope: {
      status: 'live_preview',
      question_count: questionIds.size,
      total_question_count: questionIds.size,
      answer_count: answerIds.size,
      valid_answer_count: answerIds.size,
      platform_count: countLivePlatforms(nodes),
      normalized_node_count: nodes.length,
      signal_count: signalCount,
      extraction_event_count: stageResults.filter((stageResult) => (
        (stageResult.result_type || stageResult.resultType) === 'entity_extraction_signal'
      )).length,
    },
    executive_summary: {},
  };
}

function stringValue(value: unknown): string {
  return String(value || '').trim();
}

function sampleQuestionCountFromScope(sampleScope?: Record<string, unknown>): number {
  if (!sampleScope) return 0;
  return numericSampleValue(sampleScope.question_count) || numericSampleValue(sampleScope.total_question_count);
}

function samplePlatformCountFromScope(sampleScope?: Record<string, unknown>): number {
  if (!sampleScope) return 0;
  return numericSampleValue(sampleScope.platform_count) || numericSampleValue(sampleScope.requested_platform_count);
}

function normalizeTargetPlatformIds(value: unknown): string[] {
  const raw = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : [];
  const seen = new Set<string>();
  const platforms: string[] = [];
  raw.forEach((item) => {
    const platform = String(item || '').trim().toLowerCase();
    if (!platform || seen.has(platform)) return;
    seen.add(platform);
    platforms.push(platform);
  });
  return platforms;
}

function numericSampleValue(value: unknown): number {
  const numberValue = Number(value || 0);
  return Number.isFinite(numberValue) && numberValue > 0 ? Math.round(numberValue) : 0;
}

function clampMetric(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function safeLiveId(value: string): string {
  return encodeURIComponent(value)
    .replace(/%/g, '')
    .replace(/[^a-zA-Z0-9_-]/g, '')
    .slice(0, 48) || 'node';
}

function cleanLiveExcerpt(value: string): string {
  const text = value.replace(/\s+/g, ' ').trim();
  return text.length > 180 ? `${text.slice(0, 180)}...` : text;
}

function normalizeLivePlatform(value: string): string {
  const normalized = value.toLowerCase();
  if (normalized.includes('doubao')) return '豆包';
  if (normalized.includes('hunyuan') || normalized.includes('yuanbao')) return '元宝';
  if (normalized.includes('kimi')) return 'Kimi';
  if (normalized.includes('deepseek')) return 'DeepSeek';
  return value || '未知平台';
}

function liveEntityTypeLabel(entityType: string): string {
  if (/strategy|fourvalue|flower/i.test(entityType)) return '战略词';
  if (/competitor/i.test(entityType)) return '竞品/风险';
  if (/solution|product|brand/i.test(entityType)) return '回答词';
  return entityType || '回答词';
}

function liveNodeIsRisk(accumulator: LiveNodeAccumulator): boolean {
  const text = `${accumulator.term} ${accumulator.entityType} ${Array.from(accumulator.relationTypes.keys()).join(' ')}`;
  return /risk|competitor|negative|风险|竞品|竞争|传销|拉人|智商税|夸大|压力/.test(text);
}

function countLivePlatforms(nodes: OntologyAssociationCircleNode[]): number {
  const platforms = new Set<string>();
  nodes.forEach((node) => {
    Object.keys(node.platform_distribution || {}).forEach((platform) => platforms.add(platform));
  });
  return platforms.size;
}

function buildLivePlatformComparison(
  nodes: OntologyAssociationCircleNode[],
): OntologyAssociationCirclePlatformComparison[] {
  const rows = new Map<string, {
    validAnswerCount: number;
    preferredNodes: Map<string, number>;
    riskNodes: Set<string>;
  }>();
  nodes.forEach((node) => {
    Object.entries(node.platform_distribution || {}).forEach(([platform, count]) => {
      const row = rows.get(platform) || {
        validAnswerCount: 0,
        preferredNodes: new Map<string, number>(),
        riskNodes: new Set<string>(),
      };
      row.validAnswerCount += Number(count) || 0;
      row.preferredNodes.set(node.term, (row.preferredNodes.get(node.term) || 0) + (Number(count) || 0));
      if (node.is_risk_term) row.riskNodes.add(node.term);
      rows.set(platform, row);
    });
  });
  return Array.from(rows.entries()).map(([platform, row]) => ({
    platform,
    valid_answer_count: row.validAnswerCount,
    answer_preference: '运行中实体抽取预览',
    dominant_orbit: 'live_preview',
    preferred_nodes: Array.from(row.preferredNodes.entries())
      .sort((left, right) => right[1] - left[1])
      .slice(0, 5)
      .map(([term]) => term),
    risk_nodes: Array.from(row.riskNodes),
    recommendation: '等待校准汇总后确认平台偏好。',
  }));
}

function ReportGenerationGate({
  disabled,
  activeCenterTerm,
  answerCount,
  nodeCount,
  isModeling,
  hasA5Report,
  onGenerate,
}: {
  disabled: boolean;
  activeCenterTerm: string;
  answerCount: number;
  nodeCount: number;
  isModeling: boolean;
  hasA5Report: boolean;
  onGenerate: () => void;
}) {
  return (
    <section className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{hasA5Report ? '查看' : '生成'}{activeCenterTerm}解读报告</h2>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {isModeling
              ? '抓取与实时抽取还在进行，校准完成后会开放报告生成。'
              : hasA5Report
                ? `A5 已基于校准后的 ${answerCount || '-'} 条回答和 ${nodeCount || '-'} 个节点生成报告。`
              : `基于当前 ${answerCount || '-'} 条回答和 ${nodeCount || '-'} 个节点，展开战略词验证、平台差异和下一轮建议。`}
          </p>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={disabled}
          className="inline-flex h-11 items-center justify-center rounded-xl bg-[var(--brand-primary)] px-5 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
        >
          {hasA5Report ? '查看报告' : '生成报告'}
        </button>
      </div>
    </section>
  );
}
