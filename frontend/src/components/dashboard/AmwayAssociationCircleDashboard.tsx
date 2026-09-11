import { useEffect, useMemo, useRef, useState, type ChangeEvent } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { Database, FileText, RefreshCw, Settings2, Upload, X } from 'lucide-react';
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import type { DashboardHomeData } from '@/types/dashboard';
import type { Entity } from '@/types/entity';
import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import type { StageResult } from '@/types/snapshot';
import type { AnalysisTask } from '@/types/task';
import type {
  AmwayCircleRunSummary,
  AmwayCirclePeriodType,
  AmwayCirclePeriodViewResponse,
  AmwayQuestionHistoryResponse,
  AmwayQuestionHistorySet,
} from '@/types/amwayChina';
import { api } from '@/services/api';
import { COLLECTION_PLATFORMS, defaultPlatformFetchMethods, describePlatformFetchMethods, platformFetchMethodsFromScope, type PlatformFetchMethods } from '@/lib/platformFetchMethods';
import { semanticTypeLabels } from './amwaySemanticLabels';
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
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
} from './AmwayAssociationCircleDashboardViews';
import {
  AmwayEntityLexiconPanel,
  AmwayQuestionHistoryPanel,
} from './AmwayConsoleAssetPanels';

type CircleStatus = 'empty' | 'loading' | 'ready';
type ConsoleWorkspace = 'map' | 'lexicon' | 'questions';

function normalizedAnswerCount(value: number): number {
  return Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function amwayCircleRunStatusLabel(
  latestRun: AmwayCircleRunSummary | null,
  hasProjection: boolean,
): string {
  if (!latestRun) return hasProjection ? '采集状态未确认' : '待运行';

  const validCount = normalizedAnswerCount(latestRun.valid_answer_count);
  const failedCount = normalizedAnswerCount(latestRun.failed_answer_count);
  const expectedCount = normalizedAnswerCount(latestRun.expected_answer_count);
  const totalCount = expectedCount || validCount + failedCount;
  if (latestRun.status === 'pending' || latestRun.status === 'running') return '正在抓取';
  if (latestRun.status === 'failed') return '采集失败';
  if (latestRun.status === 'cancelled') return '采集已取消';
  const isPartial = latestRun.status === 'partial'
    || failedCount > 0
    || (expectedCount > 0 && validCount < expectedCount);

  if (isPartial) {
    return totalCount > 0
      ? `最新一轮部分采集 ${validCount}/${totalCount}`
      : '最新一轮部分采集';
  }
  return hasProjection ? '圈层已生成' : '待运行';
}

const PERIOD_OPTIONS: Array<{ value: AmwayCirclePeriodType; label: string }> = [
  { value: 'latest_run', label: '最近一次' },
  { value: 'last_7_days', label: '最近 7 天' },
  { value: 'last_14_days', label: '最近 14 天' },
  { value: 'last_30_days', label: '最近 30 天' },
  { value: 'custom', label: '自定义' },
];

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
  questionSetId?: string | null;
  questionSetVersion?: number | null;
  persistQuestionSet?: boolean;
  fetchMode?: 'fast' | 'full';
  platformFetchMethods?: PlatformFetchMethods;
}

interface AmwayAssociationCircleDashboardProps {
  entities: Entity[];
  selectedEntity: Entity;
  selectedEntityId: string | null;
  enabledPlatforms: string[];
  centerOptions: string[];
  selectedCenterTerm: string | null;
  home?: DashboardHomeData | null;
  world?: OntologyWorldSummary | null;
  activeRun?: BrandIntelligenceRun | null;
  activeTask?: AnalysisTask | null;
  latestCircleRun?: AmwayCircleRunSummary | null;
  isLatestCircleRunLoading?: boolean;
  latestCircleRunError?: boolean;
  isRunActive?: boolean;
  isRunSubmitting?: boolean;
  isCancellingRun?: boolean;
  isProjectionLoading?: boolean;
  runError?: string | null;
  liveStageResults?: StageResult[];
  periodType?: AmwayCirclePeriodType;
  periodCustomStart?: string;
  periodCustomEnd?: string;
  periodView?: AmwayCirclePeriodViewResponse | null;
  isPeriodLoading?: boolean;
  isPeriodReportGenerating?: boolean;
  periodError?: string | null;
  periodReportError?: string | null;
  openRunSettingsSignal?: number;
  openReportSignal?: number;
  onSelectEntity: (entityId: string) => void;
  onSelectCenterTerm: (term: string) => void;
  onSelectPeriodType?: (periodType: AmwayCirclePeriodType) => void;
  onChangePeriodCustomStart?: (value: string) => void;
  onChangePeriodCustomEnd?: (value: string) => void;
  onGeneratePeriodReport: () => Promise<boolean>;
  onStart: (payload?: AssociationCircleStartPayload) => boolean | void | Promise<boolean | void>;
  onCancelRun?: () => void;
  onOpenLatestReport: () => void;
}

export function AmwayAssociationCircleDashboard({
  selectedEntity,
  selectedEntityId,
  enabledPlatforms,
  centerOptions,
  selectedCenterTerm,
  home,
  world,
  activeRun,
  activeTask,
  latestCircleRun = null,
  isLatestCircleRunLoading = false,
  latestCircleRunError = false,
  isRunActive,
  isRunSubmitting,
  isCancellingRun = false,
  isProjectionLoading,
  runError,
  liveStageResults = [],
  periodType = 'last_30_days',
  periodCustomStart = '',
  periodCustomEnd = '',
  periodView,
  isPeriodLoading,
  isPeriodReportGenerating,
  periodError,
  periodReportError,
  openRunSettingsSignal = 0,
  openReportSignal = 0,
  onSelectCenterTerm,
  onSelectPeriodType,
  onChangePeriodCustomStart,
  onChangePeriodCustomEnd,
  onGeneratePeriodReport,
  onStart,
  onCancelRun,
}: AmwayAssociationCircleDashboardProps) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<ConsoleWorkspace>('map');
  const [uploadedQuestions, setUploadedQuestions] = useState<UploadedAssociationQuestion[]>([]);
  const [uploadedQuestionSource, setUploadedQuestionSource] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [isReadingUpload, setIsReadingUpload] = useState(false);
  const [isReportOpen, setIsReportOpen] = useState(false);
  const [questionHistory, setQuestionHistory] = useState<AmwayQuestionHistoryResponse | null>(null);
  const [questionHistoryRefreshKey, setQuestionHistoryRefreshKey] = useState(0);
  const [selectedQuestionSetId, setSelectedQuestionSetId] = useState<string | null>(null);
  const [platformFetchMethods, setPlatformFetchMethods] = useState(defaultPlatformFetchMethods);
  const [startError, setStartError] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const startingRef = useRef(false);
  const [runSettingsOpen, setRunSettingsOpen] = useState(false);
  const [prevRunSettingsSignal, setPrevRunSettingsSignal] = useState(0);
  if (openRunSettingsSignal > 0 && openRunSettingsSignal !== prevRunSettingsSignal) {
    setPrevRunSettingsSignal(openRunSettingsSignal);
    setRunSettingsOpen(true);
  }
  const runSettingsTriggerRef = useRef<HTMLButtonElement>(null);
  const baseProjection = useMemo(() => buildAssociationProjection(world, home), [home, world]);
  const centerTerms = normalizeCenterTerms(centerOptions.length ? centerOptions : baseProjection.center_terms);
  const activeCenterTerm = selectedCenterTerm && centerTerms.includes(selectedCenterTerm)
    ? selectedCenterTerm
    : centerTerms[0] || '安利';
  const isCustomPeriodIncomplete = periodType === 'custom' && (!periodCustomStart || !periodCustomEnd);
  const isCustomPeriodInvalid = periodType === 'custom'
    && Boolean(periodCustomStart && periodCustomEnd && periodCustomStart > periodCustomEnd);
  const periodSelectionUnavailable = Boolean(
    periodError || isPeriodLoading || isCustomPeriodIncomplete || isCustomPeriodInvalid,
  );
  useEffect(() => {
    setIsReportOpen(false);
  }, [activeCenterTerm, periodCustomEnd, periodCustomStart, periodType, selectedEntityId]);
  const emptyPeriodProjection = useMemo(
    () => buildEmptyPeriodProjection(activeCenterTerm, centerTerms),
    [activeCenterTerm, centerTerms],
  );
  const officialProjection = useMemo(() => {
    if (periodView) return periodView.projection || emptyPeriodProjection;
    if (periodError || isPeriodLoading || isCustomPeriodIncomplete || isCustomPeriodInvalid) return baseProjection;
    return baseProjection;
  }, [baseProjection, emptyPeriodProjection, isCustomPeriodIncomplete, isCustomPeriodInvalid, isPeriodLoading, periodError, periodView]);
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
  const questionSets = questionHistory?.question_sets || [];
  const selectedQuestionSet = questionSets.find((item) => item.id === selectedQuestionSetId) || null;
  const selectedPeriodHasNoData = Boolean(
    periodView
      && (Number(periodView.current_period?.run_count || 0) <= 0
        || !(periodView.projection?.nodes?.length)),
  );
  const sampleScope = projection.sample_scope || {};
  const evidenceSamples = projection.evidence_samples || [];
  const evidenceFindings = projection.evidence_findings || [];
  const sourceAppendix = projection.source_appendix || [];
  const answerCount = sampleAnswerCount(sampleScope);
  const configuredPlatformCount = isRunActive
    ? targetPlatforms.length
      || numericSampleValue(sampleScope.requested_platform_count)
      || samplePlatformCountFromScope(sampleScope)
    : enabledPlatforms.length;
  const hasPeriodReport = Boolean(
    periodView?.report_id && hasReportContent(periodView.projection),
  );
  const headerStatusLabel = isRunSubmitting
    ? '正在启动…'
    : isRunActive
      ? nodes.length > 0 ? '实时抽取中' : '正在抓取'
    : status === 'loading' || isLatestCircleRunLoading
      ? '正在读取报告'
      : latestCircleRunError
        ? '采集状态读取失败'
        : amwayCircleRunStatusLabel(latestCircleRun, status === 'ready');
  useEffect(() => {
    if (!selectedEntityId) {
      setQuestionHistory(null);
      setSelectedQuestionSetId(null);
      return undefined;
    }
    let cancelled = false;
    void api.listAmwayQuestionHistory(selectedEntityId, 80)
      .then((nextHistory) => {
        if (cancelled) return;
        setQuestionHistory(nextHistory);
        setSelectedQuestionSetId((current) => (
          current && nextHistory.question_sets.some((item) => item.id === current) ? current : null
        ));
      })
      .catch(() => {
        if (!cancelled) setQuestionHistory(null);
      });
    return () => {
      cancelled = true;
    };
  }, [questionHistoryRefreshKey, selectedEntityId]);
  useEffect(() => {
    const runScope = activeRun?.input_scope;
    if (!runScope) return;
    const runQuestionSetId = typeof runScope.uploaded_question_set_id === 'string'
      ? runScope.uploaded_question_set_id
      : null;
    if (isRunActive && runQuestionSetId && questionHistory?.question_sets.some((item) => item.id === runQuestionSetId)) {
      setSelectedQuestionSetId(runQuestionSetId);
    }
  }, [activeRun?.id, activeRun?.input_scope, isRunActive, questionHistory]);
  useEffect(() => {
    setPlatformFetchMethods(defaultPlatformFetchMethods());
    setStartError(null);
  }, [selectedEntityId]);
  const handleStart = async () => {
    if (startingRef.current || isRunSubmitting || isRunActive || isCancellingRun || isReadingUpload || !enabledPlatforms.length) return false;
    startingRef.current = true;
    setIsStarting(true);
    setStartError(null);
    try {
      setIsReportOpen(false);
      const selectedQuestions = uploadedQuestions.length
        ? uploadedQuestions
        : selectedQuestionSet
          ? uploadedQuestionsFromHistorySet(selectedQuestionSet)
          : [];
      const started = await onStart({
        uploadedQuestions: selectedQuestions.map((question) => ({
          ...question,
          center_terms: [activeCenterTerm],
        })),
        uploadedQuestionSource: uploadedQuestionSource || selectedQuestionSet?.title || null,
        questionSetId: uploadedQuestions.length || selectedQuestionSet?.source_type !== 'question_set'
          ? null
          : selectedQuestionSet.id,
        questionSetVersion: uploadedQuestions.length || selectedQuestionSet?.source_type !== 'question_set'
          ? null
          : selectedQuestionSet.version || 1,
        persistQuestionSet: Boolean(uploadedQuestions.length || selectedQuestionSet?.source_type === 'run_input'),
        platformFetchMethods: { ...platformFetchMethods },
      });
      if (started !== true) {
        setStartError('运行未启动，请检查错误后重试。当前设置与上传问题已保留。');
        return false;
      }
      setQuestionHistoryRefreshKey((current) => current + 1);
      return true;
    } catch (error) {
      setStartError(error instanceof Error ? error.message : '运行启动失败，请重试。');
      return false;
    } finally {
      startingRef.current = false;
      setIsStarting(false);
    }
  };
  const handleRunFromSettings = async () => {
    if (isModeling || isCancellingRun) return;
    if (await handleStart()) setRunSettingsOpen(false);
  };
  const openReport = () => {
    setIsReportOpen(true);
    window.setTimeout(() => document.getElementById('strategy-report')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0);
  };
  const handleReportAction = async () => {
    if (hasPeriodReport) {
      openReport();
      return;
    }
    if (await onGeneratePeriodReport()) openReport();
  };
  const openReportSignalRef = useRef(0);
  useEffect(() => {
    if (openReportSignal > 0 && openReportSignal !== openReportSignalRef.current) {
      openReportSignalRef.current = openReportSignal;
      void handleReportAction();
    }
  });
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
      setSelectedQuestionSetId(null);
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : '问题列表读取失败，请检查文件格式后重新上传。');
      setUploadedQuestions([]);
      setUploadedQuestionSource(null);
    } finally {
      setIsReadingUpload(false);
    }
  };

  const isModeling = Boolean(isStarting || isRunSubmitting || isRunActive);
  const canCancelRun = Boolean(isRunActive && activeRun?.id && onCancelRun);
  const runningScope = activeRun?.input_scope;
  const displayedMethods = isRunActive ? platformFetchMethodsFromScope(runningScope) : platformFetchMethods;
  const displayedPlatforms = (isRunActive ? targetPlatforms : enabledPlatforms)
    .map((id) => id === 'hunyuan' ? 'yuanbao' : id);
  const runningQuestionCount = Number(runningScope?.uploaded_question_count || 0);
  const configuredQuestionSetLabel = isRunActive
    ? runningQuestionCount > 0
      ? `${String(runningScope?.uploaded_question_source || '本轮问题集')}（${runningQuestionCount} 题）`
      : '系统默认问题集'
    : uploadedQuestions.length
      ? `${uploadedQuestionSource || '上传问题'}（${uploadedQuestions.length} 题）`
      : selectedQuestionSet
        ? `${selectedQuestionSet.title}（${selectedQuestionSet.question_count} 题）`
        : '系统默认问题集';
  const configuredFetchModeLabel = describePlatformFetchMethods(
    isRunActive ? runningScope : { platform_fetch_methods: platformFetchMethods },
    isRunActive ? targetPlatforms : enabledPlatforms,
  );
  const runConfigurationSummary = `${configuredQuestionSetLabel} · ${configuredFetchModeLabel} · ${configuredPlatformCount} 个平台`;
  const runButtonLabel = isStarting || isRunSubmitting
    ? '正在启动…'
    : isRunActive
      ? '运行中'
      : status === 'loading'
        ? '读取中'
        : status === 'ready'
          ? '重新运行'
          : '开始运行';
  const assistiveStatusMessage = periodError
    || periodReportError
    || uploadError
    || (isReadingUpload ? '正在读取上传的问题文件。' : null)
    || (isPeriodReportGenerating ? '正在生成周期报告。' : null)
    || (isPeriodLoading ? '正在切换统计周期，当前保留上一份可用图谱。' : null)
    || headerStatusLabel;
  const workspaceItems: Array<{
    id: ConsoleWorkspace;
    label: string;
    icon: typeof Database;
  }> = [
    { id: 'map', label: '品牌图谱', icon: RefreshCw },
    { id: 'lexicon', label: '实体词库', icon: Database },
    { id: 'questions', label: '问题集管理', icon: FileText },
  ];

  return (
    <div className="amway-console min-h-screen bg-[var(--bg-secondary)] text-[var(--text-primary)]">
      <p className="sr-only" role="status" aria-live="polite" aria-atomic="true">
        {assistiveStatusMessage}
      </p>

      <main className="mx-auto max-w-[1920px] min-w-0 px-5 py-4 lg:px-7 2xl:px-10">
        <div className="mb-4 flex overflow-x-auto">
          <div className="inline-flex items-center gap-1 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-1">
            {workspaceItems.map((item) => {
              const Icon = item.icon;
              const active = workspace === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setWorkspace(item.id)}
                  aria-current={active ? 'page' : undefined}
                  aria-pressed={active}
                  className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg px-3 text-sm transition"
                  style={{
                    background: active ? 'var(--bg-primary)' : 'transparent',
                    color: active ? 'var(--brand-primary)' : 'var(--text-secondary)',
                    boxShadow: active ? 'var(--shadow-sm)' : 'none',
                  }}
                >
                  <Icon size={14} />
                  {item.label}
                </button>
              );
            })}
          </div>
        </div>
        {workspace === 'lexicon' ? (
          <AmwayEntityLexiconPanel entityId={selectedEntityId} entityName={selectedEntity.name} />
        ) : workspace === 'questions' ? (
          <AmwayQuestionHistoryPanel
            entityId={selectedEntityId}
            entityName={selectedEntity.name}
            selectedForRunId={selectedQuestionSetId}
            onSelectForRun={(questionSet) => {
              setSelectedQuestionSetId(questionSet.id);
              setUploadedQuestions([]);
              setUploadedQuestionSource(null);
              setWorkspace('map');
            }}
            onQuestionSetsChanged={() => setQuestionHistoryRefreshKey((current) => current + 1)}
          />
        ) : (
        <section className="min-w-0 space-y-4">
          {Boolean(projection.object_index?.length) && <details className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4 text-sm">
            <summary>独立对象证据（含未归入主题的对象）</summary>
            <div className="mt-2 max-h-80 overflow-y-auto divide-y divide-[var(--border-subtle)]">
              {projection.object_index?.map((item, index) => <div className="py-2" key={`${item.entity_id}-${item.answer_id}-${index}`}>
                <p className="font-medium">{item.entity_name} · {semanticTypeLabels[item.semantic_definition?.semantic_type || ''] || '对象'} · {item.platform}</p>
                <p>{item.evidence_text}</p><p className="text-xs text-[var(--text-tertiary)]">对象 ID：{item.entity_id}</p>
              </div>)}
            </div>
          </details>}
          {runError ? (
            <InlineActionError message={runError} actionLabel="重试运行" onAction={handleStart} />
          ) : null}

          <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-5 shadow-sm">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--brand-primary)]">
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--brand-primary)]" />
                  {activeCenterTerm} 专属
                </div>
                <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                  <h1 className="text-2xl font-semibold leading-tight tracking-tight">品牌联想图谱</h1>
                  <p className="text-sm tabular-nums text-[var(--text-secondary)]" aria-label="本轮数据范围">
                    {answerCount > 0
                      ? `${headerStatusLabel} · ${samplePlatformCountFromScope(sampleScope)} 个平台 · ${nodes.length} 个节点`
                      : headerStatusLabel === '待运行'
                        ? '尚未运行采集，从图谱中心开始'
                        : headerStatusLabel}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <div className="min-w-0 text-xs leading-5 text-[var(--text-secondary)]">
                  <span className="block text-[var(--text-tertiary)]">{isModeling ? '本轮配置' : '下次运行'}</span>
                  <span className="font-medium text-[var(--text-primary)]">{runConfigurationSummary}</span>
                </div>
                {isRunSubmitting ? (
                  <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 text-sm font-medium text-[var(--text-secondary)]">
                    <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
                    正在启动…
                  </div>
                ) : canCancelRun ? (
                  <button
                    type="button"
                    onClick={onCancelRun}
                    disabled={isCancellingRun}
                    className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-primary)] px-3.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-secondary)] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isCancellingRun ? (
                      <RefreshCw size={14} className="animate-spin" aria-hidden="true" />
                    ) : (
                      <X size={14} aria-hidden="true" />
                    )}
                    {isCancellingRun ? '正在停止…' : '停止采集'}
                  </button>
                ) : (
                  <button
                    ref={runSettingsTriggerRef}
                    type="button"
                    onClick={() => setRunSettingsOpen(true)}
                    disabled={status === 'loading'}
                    className="amway-cta-glow inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:border-[var(--border-subtle)] disabled:bg-[var(--bg-secondary)] disabled:text-[var(--text-tertiary)] disabled:shadow-none"
                  >
                    <Settings2 size={15} />
                    {status === 'ready' ? '设置并重新运行' : '设置并运行'}
                  </button>
                )}
              </div>
            </div>

            <div className="mt-4 flex flex-col gap-4 border-t border-[var(--border-subtle)] pt-4 xl:flex-row xl:items-start xl:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-tertiary)]">
                  分析对象
                  <span
                    className="inline-flex h-4 w-4 cursor-help items-center justify-center rounded-full border border-[var(--border-subtle)] text-[10px] leading-none"
                    title="其他对象将在独立投影生成后开放"
                    aria-label="其他对象将在独立投影生成后开放"
                  >
                    ?
                  </span>
                </div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {centerTerms.map((term) => (
                    <button
                      key={term}
                      type="button"
                      onClick={() => {
                        onSelectCenterTerm(term);
                        setSelectedNodeId(null);
                      }}
                      disabled={term !== activeCenterTerm}
                      aria-pressed={term === activeCenterTerm}
                      title={term === activeCenterTerm ? '当前分析对象' : '尚未生成该对象的独立投影'}
                      className="inline-flex h-9 min-w-0 items-center gap-2 rounded-lg border px-3 text-left text-sm transition"
                      style={{
                        borderColor: term === activeCenterTerm ? 'var(--brand-primary)' : 'var(--border-subtle)',
                        background: 'var(--bg-primary)',
                        color: term === activeCenterTerm ? 'var(--text-primary)' : 'var(--text-tertiary)',
                      }}
                    >
                      <span className="truncate font-semibold">{term}</span>
                      <span className="shrink-0 text-[11px] text-[var(--text-tertiary)]">{term === activeCenterTerm ? '当前' : '待生成'}</span>
                    </button>
                  ))}
                </div>
              </div>
              <PeriodSelector
                value={periodType}
                customStart={periodCustomStart}
                customEnd={periodCustomEnd}
                isLoading={Boolean(isPeriodLoading)}
                error={periodError}
                notice={isRunActive
                  ? '建模运行中显示实时图谱，完成后再按观察周期查看。'
                  : selectedPeriodHasNoData
                    ? '该周期暂无采集数据。可运行图谱采集，或选择其他观察周期。'
                    : ''}
                disabled={Boolean(isRunActive || isPeriodReportGenerating)}
                onChange={onSelectPeriodType}
                onChangeCustomStart={onChangePeriodCustomStart}
                onChangeCustomEnd={onChangePeriodCustomEnd}
              />
            </div>
          </section>

          <Dialog.Root open={runSettingsOpen} onOpenChange={setRunSettingsOpen}>
            <Dialog.Portal>
              <Dialog.Overlay className={modalScrimClassName('z-50')} />
              <Dialog.Content
                onCloseAutoFocus={(event) => {
                  event.preventDefault();
                  runSettingsTriggerRef.current?.focus();
                }}
                className="fixed left-1/2 top-1/2 z-50 max-h-[calc(100vh-2rem)] w-[calc(100%-2rem)] max-w-[680px] -translate-x-1/2 -translate-y-1/2 overflow-y-auto overscroll-contain rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-sm"
              >
                  <div className="flex items-start justify-between gap-5 border-b border-[var(--border-subtle)] px-6 py-5">
                    <div>
                      <Dialog.Title className="text-xl font-semibold text-[var(--text-primary)]">运行设置</Dialog.Title>
                      <Dialog.Description className="mt-1.5 text-sm leading-6 text-[var(--text-secondary)]">
                        选择本轮问题与采集方式。确认后会创建不可变运行快照。
                      </Dialog.Description>
                    </div>
                    <Dialog.Close asChild>
                      <button
                        type="button"
                        aria-label="关闭运行设置"
                        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
                      >
                        <X size={16} />
                      </button>
                    </Dialog.Close>
                  </div>

                  <div className="space-y-6 px-6 py-6">
                    <section>
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <label htmlFor="amway-run-question-set" className="text-sm font-semibold text-[var(--text-primary)]">
                          本轮问题集
                        </label>
                        <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] focus-within:outline focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-[var(--brand-primary)]">
                          <Upload size={14} />
                          {isReadingUpload ? '正在读取' : '上传问题文件'}
                          <input
                            type="file"
                            accept=".csv,.xlsx,.txt,text/csv,text/plain,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            className="sr-only"
                            disabled={isReadingUpload || isModeling}
                            onChange={handleQuestionFileChange}
                          />
                        </label>
                      </div>
                      <select
                        id="amway-run-question-set"
                        disabled={isModeling || isReadingUpload}
                        value={uploadedQuestions.length ? '__upload__' : selectedQuestionSetId || ''}
                        onChange={(event) => {
                          const nextId = event.target.value || null;
                          setSelectedQuestionSetId(nextId);
                          setUploadedQuestions([]);
                          setUploadedQuestionSource(null);
                          setUploadError(null);
                        }}
                        className="mt-3 h-11 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] outline-none focus:border-[var(--brand-primary)]"
                      >
                        <option value="">系统默认问题集</option>
                        {uploadedQuestions.length ? (
                          <option value="__upload__">待保存：{uploadedQuestionSource}（{uploadedQuestions.length} 题）</option>
                        ) : null}
                        {questionSets.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.title}（{item.question_count} 题）
                          </option>
                        ))}
                      </select>
                      <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">
                        {uploadedQuestions.length
                          ? `已读取 ${uploadedQuestionSource || '上传文件'}，共 ${uploadedQuestions.length} 题；运行时保存并绑定版本。`
                          : selectedQuestionSet
                            ? `已选择 ${selectedQuestionSet.title}，共 ${selectedQuestionSet.question_count} 题。`
                            : '未指定题库时，运行阶段生成系统默认问题集。'}
                      </p>
                      {uploadError ? <InlineActionError message={uploadError} compact /> : null}
                    </section>

                    <fieldset disabled={isModeling}>
                      <legend className="text-sm font-semibold text-[var(--text-primary)]">采集方式</legend>
                      <p className="mt-2 text-xs leading-5 text-[var(--text-secondary)]">逐个平台选择采集方式；本次启动成功后设置固定。平台启停沿用生产线配置。</p>
                      <div className="mt-3 divide-y divide-[var(--border-subtle)]">
                        {COLLECTION_PLATFORMS.map(({ id, label }) => (
                          <fieldset key={id} disabled={!displayedPlatforms.includes(id)} className="flex flex-wrap items-center gap-4 py-3 disabled:opacity-60">
                            <legend className="sr-only">{label} 采集方式</legend>
                            <span className="min-w-24 flex-1 text-sm font-semibold">{label}{!displayedPlatforms.includes(id) ? '（已停用）' : ''}</span>
                            {(['browser', 'api'] as const).map((method) => (
                              <label key={method} className="inline-flex items-center gap-2 text-sm">
                                <input type="radio" name={`fetch-method-${id}`} value={method}
                                  checked={displayedMethods[id] === method}
                                  onChange={() => setPlatformFetchMethods((current) => ({ ...current, [id]: method }))}
                                  className="h-4 w-4 accent-[var(--brand-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]" />
                                {method === 'browser' ? '浏览器' : 'API'}
                              </label>
                            ))}
                          </fieldset>
                        ))}
                      </div>
                    </fieldset>

                    <div className="border-t border-[var(--border-subtle)] pt-4">
                      <div className="text-xs font-medium text-[var(--text-tertiary)]">本轮配置</div>
                      <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{runConfigurationSummary}</div>
                      {!enabledPlatforms.length ? <p role="status" className="mt-2 text-sm text-[var(--error)]">所有平台已停用，请先在生产线启用至少一个平台。</p> : null}
                      {startError || runError ? <InlineActionError message={runError || startError || ''} compact /> : null}
                    </div>
                  </div>

                  <div className="flex items-center justify-end gap-3 border-t border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-6 py-4">
                    <Dialog.Close asChild>
                      <button
                        type="button"
                        className="h-10 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                      >
                        取消
                      </button>
                    </Dialog.Close>
                    <button
                      type="button"
                      onClick={() => void handleRunFromSettings()}
                      disabled={isModeling || isCancellingRun || isReadingUpload || !enabledPlatforms.length || status === 'loading'}
                      className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      <RefreshCw size={15} />
                      {runButtonLabel}
                    </button>
                  </div>
              </Dialog.Content>
            </Dialog.Portal>
          </Dialog.Root>

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
                onStartRun={() => setRunSettingsOpen(true)}
              />

              {isReportOpen && status === 'ready' && nodes.length > 0 ? (
                <section id="strategy-report" className="scroll-mt-20">
                  <div aria-hidden="true" className="mb-8 flex items-center gap-4">
                    <span className="h-px flex-1 bg-[var(--border-subtle)]" />
                    <span className="text-xs font-medium tracking-[0.2em] text-[var(--text-tertiary)]">解读报告</span>
                    <span className="h-px flex-1 bg-[var(--border-subtle)]" />
                  </div>
                  <AssociationReportPanel
                    projection={projection}
                    activeCenterTerm={activeCenterTerm}
                    groups={mapGroups}
                  />
                </section>
              ) : (
                <ReportGenerationGate
                  disabled={isModeling || Boolean(isPeriodReportGenerating) || !nodes.length || periodSelectionUnavailable}
                  activeCenterTerm={activeCenterTerm}
                  answerCount={answerCount}
                  nodeCount={nodes.length}
                  isModeling={isModeling}
                  hasReport={hasPeriodReport}
                  isGenerating={Boolean(isPeriodReportGenerating)}
                  hasError={Boolean(periodReportError)}
                  onGenerate={() => void handleReportAction()}
                />
              )}
            </div>
          )}
        </section>
        )}
      </main>
    </div>
  );
}

function uploadedQuestionsFromHistorySet(
  questionSet: AmwayQuestionHistorySet,
): UploadedAssociationQuestion[] {
  return questionSet.questions.flatMap((question, index) => {
    const text = String(
      question.question_text
      || question.text
      || question.core_question
      || question.question
      || '',
    ).trim();
    if (!text) return [];
    return [{
      ...question,
      id: String(question.id || `question_set_${index + 1}`),
      text,
      source: String(question.source || questionSet.source || 'question_set'),
      center_terms: questionSet.center_terms,
    } as UploadedAssociationQuestion];
  });
}

function buildEmptyPeriodProjection(
  centerTerm: string,
  centerTerms: string[],
): OntologyAssociationCircleProjection {
  return {
    status: 'empty_period',
    center_terms: centerTerms.length ? centerTerms : [centerTerm],
    nodes: [],
    evidence_samples: [],
    question_bank: [],
    platform_comparison: [],
    association_actions: [],
    report_narrative_sections: [],
    sample_scope: {},
    generated_from: 'period_view_empty',
  };
}

export function hasReportContent(
  projection: AmwayCirclePeriodViewResponse['projection'],
): boolean {
  return Boolean(
    projection
      && (
        (projection.report_narrative_sections || []).length > 0
        || projection.report_markdown?.trim()
        || projection.full_markdown?.trim()
      ),
  );
}

export function reportQualityPassed(
  projection: AmwayCirclePeriodViewResponse['projection'] | undefined,
): boolean {
  return projection?.report_quality_checks?.passed === true;
}

function PeriodSelector({
  value,
  customStart,
  customEnd,
  isLoading,
  error,
  notice,
  disabled,
  onChange,
  onChangeCustomStart,
  onChangeCustomEnd,
}: {
  value: AmwayCirclePeriodType;
  customStart: string;
  customEnd: string;
  isLoading: boolean;
  error?: string | null;
  notice?: string;
  disabled?: boolean;
  onChange?: (value: AmwayCirclePeriodType) => void;
  onChangeCustomStart?: (value: string) => void;
  onChangeCustomEnd?: (value: string) => void;
}) {
  const helperText = value === 'custom' && (!customStart || !customEnd)
    ? '选择起止日期后更新图谱。'
    : value === 'custom' && customStart > customEnd
      ? '开始日期不能晚于结束日期。'
    : notice;
  return (
    <div className="min-w-0 xl:max-w-[560px]">
      <div className="flex flex-wrap items-center gap-2">
        <span className="px-1 text-xs font-medium text-[var(--text-tertiary)]">观察周期</span>
        {PERIOD_OPTIONS.map((item) => {
          const active = item.value === value;
          return (
            <button
              key={item.value}
              type="button"
              onClick={() => onChange?.(item.value)}
              disabled={disabled}
              aria-pressed={active}
              className="h-9 rounded-lg border px-3 text-xs font-medium transition"
              style={{
                borderColor: active ? 'var(--brand-border)' : 'var(--border-subtle)',
                background: 'var(--bg-primary)',
                color: active ? 'var(--text-primary)' : 'var(--text-secondary)',
                boxShadow: active ? 'inset 0 -2px var(--brand-primary)' : 'none',
              }}
            >
              {item.label}
            </button>
          );
        })}
        {value === 'custom' ? (
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              aria-label="开始日期"
              value={customStart}
              max={customEnd || undefined}
              onChange={(event) => onChangeCustomStart?.(event.target.value)}
              disabled={disabled}
              className="h-9 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs text-[var(--text-secondary)]"
            />
            <span className="text-xs text-[var(--text-tertiary)]">至</span>
            <input
              type="date"
              aria-label="结束日期"
              value={customEnd}
              min={customStart || undefined}
              onChange={(event) => onChangeCustomEnd?.(event.target.value)}
              disabled={disabled}
              className="h-9 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs text-[var(--text-secondary)]"
            />
          </div>
        ) : null}
        {isLoading ? (
          <span className="text-xs text-[var(--text-tertiary)]">正在更新图谱...</span>
        ) : null}
      </div>
      {error ? (
        <div className="mt-2 flex flex-wrap items-center gap-3 text-xs leading-5 text-[var(--error)]">
          <span>{error}</span>
          {value === 'custom' ? (
            <button
              type="button"
              onClick={() => onChange?.('last_30_days')}
              className="rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-1 font-semibold text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
            >
              返回最近 30 天
            </button>
          ) : null}
        </div>
      ) : helperText ? (
        <p className="mt-2 text-xs leading-5 text-[var(--text-tertiary)]">{helperText}</p>
      ) : null}
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

export function mergeStageResults(primary: StageResult[], secondary: StageResult[]): StageResult[] {
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
  semantic_definition?: { graph_role?: string };
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

export function buildLiveAssociationProjection(
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
      const semantic = signal.semantic_definition as { graph_role?: string } | undefined;
      if (semantic?.graph_role === 'object' || semantic?.graph_role === 'context') return;
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
      answer_refs: Array.from(accumulator.answerIds),
      answer_count_is_exact: true,
      count_semantics: 'distinct_answer_refs',
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

function samplePlatformCountFromScope(sampleScope?: Record<string, unknown>): number {
  if (!sampleScope) return 0;
  const platforms = Array.isArray(sampleScope.platforms) ? sampleScope.platforms.length : 0;
  return numericSampleValue(sampleScope.platform_count)
    || numericSampleValue(sampleScope.requested_platform_count)
    || platforms;
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
  hasReport,
  isGenerating,
  hasError,
  onGenerate,
}: {
  disabled: boolean;
  activeCenterTerm: string;
  answerCount: number;
  nodeCount: number;
  isModeling: boolean;
  hasReport: boolean;
  isGenerating: boolean;
  hasError: boolean;
  onGenerate: () => void;
}) {
  return (
    <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-4">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold">{hasReport ? '查看' : '生成'}{activeCenterTerm}解读报告</h2>
          <p className="mt-1 text-sm leading-6 text-[var(--text-secondary)]">
            {isModeling
              ? '抓取与实时抽取还在进行，校准完成后会开放报告生成。'
              : hasReport
                ? `已基于校准后的 ${answerCount} 条回答和 ${nodeCount} 个节点生成报告。`
              : answerCount > 0
                ? `基于当前 ${answerCount} 条回答和 ${nodeCount} 个节点，展开战略词验证、平台差异和下一轮建议。`
                : '运行图谱采集后，即可基于真实回答展开战略词验证、平台差异和下一轮建议。'}
          </p>
        </div>
        <button
          type="button"
          onClick={onGenerate}
          disabled={disabled}
          className="inline-flex h-11 items-center justify-center rounded-xl bg-[var(--brand-primary)] px-5 text-sm font-semibold text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] disabled:opacity-50"
        >
          {isGenerating ? '生成中' : hasReport ? '查看报告' : '生成报告'}
        </button>
      </div>
      {hasError ? <ReportGenerationError onRetry={onGenerate} /> : null}
    </section>
  );
}

function ReportGenerationError({ onRetry }: { onRetry: () => void }) {
  return (
    <div
      role="alert"
      className="mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color-mix(in_srgb,var(--evidence-risk)_28%,var(--border-subtle))] bg-[var(--status-error-bg)] px-3 py-2 text-sm text-[var(--error)]"
    >
      <span className="leading-5">报告生成失败，请稍后重试。当前图谱数据已保留。</span>
      <button
        type="button"
        onClick={onRetry}
        className="h-9 rounded-lg border border-[color-mix(in_srgb,var(--evidence-risk)_35%,var(--border-subtle))] bg-[var(--bg-primary)] px-3 text-xs font-semibold text-[var(--error)] hover:bg-[var(--bg-secondary)]"
      >
        重试生成报告
      </button>
    </div>
  );
}

function InlineActionError({
  message,
  actionLabel,
  onAction,
  compact = false,
}: {
  message: string;
  actionLabel?: string;
  onAction?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      role="alert"
      className={`flex flex-wrap items-center justify-between gap-3 rounded-xl border border-[color-mix(in_srgb,var(--evidence-risk)_28%,var(--border-subtle))] bg-[var(--status-error-bg)] text-sm text-[var(--error)] ${compact ? 'mt-3 px-3 py-2' : 'px-5 py-4'}`}
    >
      <span className="leading-5">{message}</span>
      {actionLabel && onAction ? (
        <button
          type="button"
          onClick={onAction}
          className="h-9 rounded-lg border border-[color-mix(in_srgb,var(--evidence-risk)_35%,var(--border-subtle))] bg-[var(--bg-primary)] px-3 text-xs font-semibold text-[var(--error)] hover:bg-[var(--bg-secondary)]"
        >
          {actionLabel}
        </button>
      ) : null}
    </div>
  );
}
