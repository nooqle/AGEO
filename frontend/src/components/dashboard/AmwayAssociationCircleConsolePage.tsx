'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Orbit, Settings, Workflow } from 'lucide-react';
import {
  AmwayAssociationCircleDashboard,
  hasReportContent,
  reportQualityPassed,
  type AssociationCircleStartPayload,
} from './AmwayAssociationCircleDashboard';
import { buildAssociationProjection } from './AmwayAssociationCircleDashboardViews';
import { AmwayConsoleHeader } from './AmwayConsoleHeader';
import { AmwayFlowCanvas, readEnabledFlowPlatforms } from './AmwayFlowCanvas';
import { useEntityStore } from '@/stores/entityStore';
import { useIntelligenceRunStore } from '@/stores/intelligenceRunStore';
import { useOntologyStore } from '@/stores/ontologyStore';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import {
  associationCenterOptionsForEntity,
  isAmwayAssociationEntity,
} from '@/lib/brandEntityHygiene';
import { buildDashboardChatUrlWithHandoff } from '@/lib/dashboardChatHandoff';
import type { DashboardHomeData, DashboardLatestReport } from '@/types/dashboard';
import {
  isActiveBrandIntelligenceRun,
  isAwaitingFlowPlanConfirmation,
  isExecutingBrandIntelligenceRun,
} from '@/types/intelligenceRun';
import type { Entity } from '@/types/entity';
import type { AnalysisTask } from '@/types/task';
import type { StageResult } from '@/types/snapshot';
import type { OntologyWorldSummary } from '@/types/ontology';
import type {
  AmwayCirclePeriodType,
  AmwayCirclePeriodViewResponse,
} from '@/types/amwayChina';

const ASSOCIATION_ANALYSIS_MODE = 'brand_association_circle';
const ASSOCIATION_DASHBOARD_VARIANT = 'amway_association_circle';
const DEFAULT_CENTER_TERMS = ['安利', '安利中国', '纽崔莱'];
const DEV_ENTITY_FALLBACK_DELAY_MS = 6000;

type ConsoleView = 'circle' | 'flow' | 'settings';

const CONSOLE_VIEWS: Array<{ id: ConsoleView; label: string; icon: typeof Orbit }> = [
  { id: 'circle', label: '品牌圈层', icon: Orbit },
  { id: 'flow', label: '品牌生产线', icon: Workflow },
  { id: 'settings', label: '设置', icon: Settings },
];

function normalizeConsoleView(raw: string | null): ConsoleView {
  return raw === 'flow' || raw === 'settings' ? raw : 'circle';
}
const ASSOCIATION_STAGE_RESULT_TYPES = new Set([
  'entity_extraction_signal',
  'entity_calibration_summary',
]);

function customPeriodEndExclusive(value: string): string | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (!match) return null;
  const nextDay = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + 1));
  return `${nextDay.toISOString().slice(0, 10)}T00:00:00+08:00`;
}

function normalizeWebSocketBase(rawUrl: string | undefined): string {
  const value = (rawUrl || 'ws://localhost:8001').trim().replace(/\/+$/, '');
  if (value.endsWith('/ws')) {
    return value.slice(0, -3);
  }
  return value;
}

const WS_URL = normalizeWebSocketBase(process.env.NEXT_PUBLIC_WS_URL);

function buildDevelopmentAmwayEntity(entityId: string): Entity {
  const now = new Date().toISOString();
  return {
    id: entityId,
    name: '安利',
    aliases: ['安利', '安利中国', '纽崔莱', 'Amway', 'Amway China', 'Nutrilite'],
    domain: 'https://www.amway.com.cn',
    industry: '健康生活',
    description: '安利品牌圈层 Console 开发态入口',
    visibilityScope: 'personal',
    ownerUserId: null,
    organizationId: null,
    lastAnalyzed: null,
    status: 'active',
    dashboardVariant: ASSOCIATION_DASHBOARD_VARIANT,
    analysisMode: ASSOCIATION_ANALYSIS_MODE,
    reportKind: 'brand_association_circle',
    centerTerms: ['安利', '安利中国', '纽崔莱'],
    enabledSurfaces: ['dashboard', 'chat', 'canvas', 'brand_world'],
    associationBrandCluster: ['安利', '安利中国', '纽崔莱'],
    isInternalTestData: false,
    hygieneLabels: [],
    createdAt: now,
    updatedAt: now,
  };
}

function createHandoffId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function latestReportRef(report?: DashboardLatestReport): string {
  return (
    report?.artifact_id ||
    report?.output_id ||
    report?.session_id ||
    report?.created_at ||
    ''
  );
}

function reportTodoStorageKey(brandId: string, reportRef: string): string {
  return `specta.dashboard.report.viewed.${brandId}.${reportRef}`;
}

function markReportTodoViewed(brandId: string | null, reportRef: string | null | undefined) {
  if (!brandId || !reportRef || typeof window === 'undefined') return;
  window.localStorage.setItem(reportTodoStorageKey(brandId, reportRef), '1');
}

function parseAssociationStageResult(raw: string): StageResult | null {
  try {
    const message = JSON.parse(raw) as {
      event?: string;
      data?: Record<string, unknown>;
    };
    if (message.event !== 'stage_result') return null;
    const data = message.data || {};
    const resultType = String(data.result_type || data.resultType || '').trim();
    if (!ASSOCIATION_STAGE_RESULT_TYPES.has(resultType)) return null;
    return {
      stage: String(data.stage || ''),
      stageName: String(data.stage_name || data.stageName || ''),
      stage_name: String(data.stage_name || data.stageName || ''),
      resultType: resultType as StageResult['resultType'],
      result_type: resultType as StageResult['result_type'],
      data: typeof data.data === 'object' && data.data !== null
        ? data.data as Record<string, unknown>
        : {},
      timestamp: String(data.timestamp || new Date().toISOString()),
    };
  } catch {
    return null;
  }
}

function appendUniqueStageResult(
  current: StageResult[],
  next: StageResult,
  maxCount: number,
): StageResult[] {
  const nextKey = associationStageResultKey(next);
  const filtered = current.filter((item) => associationStageResultKey(item) !== nextKey);
  return [...filtered, next].slice(-maxCount);
}

function associationStageResultKey(item: StageResult): string {
  const resultType = String(item.result_type || item.resultType || '').trim();
  const data = item.data || {};
  const answerId = String(data.answer_id || '').trim();
  if (resultType === 'entity_extraction_signal' && answerId) {
    return `${resultType}:${answerId}`;
  }
  const generatedFrom = String(data.generated_from || '').trim();
  return `${item.stage || ''}:${resultType}:${generatedFrom}:${item.timestamp || ''}`;
}

function selectInitialAmwayEntity(
  entities: Entity[],
  requestedEntityId: string | null,
): Entity | null {
  const amwayEntities = entities.filter(isAmwayAssociationEntity);
  if (!amwayEntities.length) return null;
  if (requestedEntityId) {
    const requested = amwayEntities.find((entity) => entity.id === requestedEntityId);
    if (requested) return requested;
  }
  return amwayEntities[0] || null;
}

export function AmwayAssociationCircleConsolePage({
  lockedEntityId = null,
}: {
  lockedEntityId?: string | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedEntityId = lockedEntityId || searchParams.get('entity_id');
  const consoleView = normalizeConsoleView(searchParams.get('view'));
  const [runSettingsRequest, setRunSettingsRequest] = useState(0);
  const [reportRequest, setReportRequest] = useState(0);
  const entities = useEntityStore((state) => state.entities);
  const entitiesLoading = useEntityStore((state) => state.isLoading);
  const entityError = useEntityStore((state) => state.error);
  const fetchEntities = useEntityStore((state) => state.fetchEntities);
  const { worldsByEntity, loadingByEntity, fetchWorld } = useOntologyStore();
  const {
    runsByEntity,
    submittingByEntity,
    errorByEntity,
    fetchActiveRun,
    createRun,
    confirmRun,
    cancelRun,
  } = useIntelligenceRunStore();
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedCenterTerm, setSelectedCenterTerm] = useState<string | null>(DEFAULT_CENTER_TERMS[0]);
  const [home, setHome] = useState<DashboardHomeData | null>(null);
  const [isHomeLoading, setIsHomeLoading] = useState(false);
  const [homeLoadedEntityId, setHomeLoadedEntityId] = useState<string | null>(null);
  const [homeError, setHomeError] = useState<string | null>(null);
  const [activeTask, setActiveTask] = useState<AnalysisTask | null>(null);
  const [directEntity, setDirectEntity] = useState<Entity | null>(null);
  const [directEntityError, setDirectEntityError] = useState<string | null>(null);
  const [allowEntityFallback, setAllowEntityFallback] = useState(false);
  const [directWorld, setDirectWorld] = useState<OntologyWorldSummary | null>(null);
  const [directWorldEntityId, setDirectWorldEntityId] = useState<string | null>(null);
  const [directWorldError, setDirectWorldError] = useState<string | null>(null);
  const [streamedStageResults, setStreamedStageResults] = useState<StageResult[]>([]);
  const [periodType, setPeriodType] = useState<AmwayCirclePeriodType>('last_30_days');
  const [periodCustomStart, setPeriodCustomStart] = useState('');
  const [periodCustomEnd, setPeriodCustomEnd] = useState('');
  const [periodView, setPeriodView] = useState<AmwayCirclePeriodViewResponse | null>(null);
  const [isPeriodLoading, setIsPeriodLoading] = useState(false);
  const [isPeriodReportGenerating, setIsPeriodReportGenerating] = useState(false);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const [periodReportError, setPeriodReportError] = useState<string | null>(null);

  useEffect(() => {
    void fetchEntities();
  }, [fetchEntities]);

  useEffect(() => {
    if (!requestedEntityId) {
      setDirectEntity(null);
      setDirectEntityError(null);
      return;
    }
    if (entities.some((entity) => entity.id === requestedEntityId)) return;
    let cancelled = false;
    setDirectEntityError(null);
    void api
      .getEntity(requestedEntityId)
      .then((entity) => {
        if (!cancelled) setDirectEntity(entity);
      })
      .catch((error) => {
        if (!cancelled) {
          setDirectEntity(null);
          setDirectEntityError(error instanceof Error ? error.message : '当前品牌实体读取失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [entities, requestedEntityId]);

  useEffect(() => {
    setAllowEntityFallback(false);
    if (process.env.NODE_ENV !== 'development') return undefined;
    if (!requestedEntityId || directEntity || entities.length) return undefined;
    const timer = window.setTimeout(() => {
      setAllowEntityFallback(true);
    }, DEV_ENTITY_FALLBACK_DELAY_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, [directEntity, entities.length, requestedEntityId]);

  const fallbackEntity = useMemo(
    () => (
      process.env.NODE_ENV === 'development' && allowEntityFallback && requestedEntityId
        ? buildDevelopmentAmwayEntity(requestedEntityId)
        : null
    ),
    [allowEntityFallback, requestedEntityId],
  );

  const consoleEntities = useMemo(
    () => {
      const additions = [directEntity, fallbackEntity].filter(Boolean) as Entity[];
      const nextEntities = [...entities];
      additions.forEach((entity) => {
        if (!nextEntities.some((item) => item.id === entity.id)) {
          nextEntities.unshift(entity);
        }
      });
      return nextEntities;
    },
    [directEntity, entities, fallbackEntity],
  );

  const amwayEntities = useMemo(
    () => {
      const candidates = consoleEntities.filter(isAmwayAssociationEntity);
      if (!lockedEntityId) return candidates;
      return candidates.filter((entity) => entity.id === lockedEntityId);
    },
    [consoleEntities, lockedEntityId],
  );

  useEffect(() => {
    if (entitiesLoading && !directEntity && !fallbackEntity) return;
    const selectedStillValid = selectedEntityId
      ? amwayEntities.some((entity) => entity.id === selectedEntityId)
      : false;
    if (selectedStillValid) return;
    const initial = selectInitialAmwayEntity(consoleEntities, requestedEntityId);
    setSelectedEntityId(initial?.id || null);
  }, [amwayEntities, consoleEntities, directEntity, entitiesLoading, fallbackEntity, requestedEntityId, selectedEntityId]);

  const selectedEntity = useMemo(
    () => amwayEntities.find((entity) => entity.id === selectedEntityId) || null,
    [amwayEntities, selectedEntityId],
  );
  const centerOptions = useMemo(
    () => associationCenterOptionsForEntity(selectedEntity),
    [selectedEntity],
  );
  const effectiveCenterTerm = centerOptions.includes(selectedCenterTerm || '')
    ? selectedCenterTerm
    : centerOptions[0] || DEFAULT_CENTER_TERMS[0];
  const selectedWorld = selectedEntityId
    ? worldsByEntity[selectedEntityId] || (directWorldEntityId === selectedEntityId ? directWorld : null)
    : null;
  const selectedRun = selectedEntityId ? runsByEntity[selectedEntityId] : null;
  const isSelectedRunActive = isActiveBrandIntelligenceRun(selectedRun);
  const isAwaitingPlanConfirm = isAwaitingFlowPlanConfirmation(selectedRun);
  const isSelectedRunExecuting = isExecutingBrandIntelligenceRun(selectedRun);
  const isWorldLoading = selectedEntityId ? Boolean(loadingByEntity[selectedEntityId]) : false;
  const hasHomeLoadedForSelectedEntity = Boolean(
    selectedEntityId && homeLoadedEntityId === selectedEntityId,
  );
  const hasHomeReport = Boolean(home?.latest_report);
  const isProjectionLoading = Boolean(
    selectedEntityId
      && !selectedWorld
      && !hasHomeReport
      && (isWorldLoading || isHomeLoading || !hasHomeLoadedForSelectedEntity),
  );

  useEffect(() => {
    if (!centerOptions.length) {
      setSelectedCenterTerm(DEFAULT_CENTER_TERMS[0]);
      return;
    }
    setSelectedCenterTerm((current) => (
      current && centerOptions.includes(current) ? current : centerOptions[0]
    ));
  }, [centerOptions]);

  useEffect(() => {
    if (!selectedEntityId) {
      setHome(null);
      setIsHomeLoading(false);
      setHomeLoadedEntityId(null);
      return;
    }
    let cancelled = false;
    setHomeError(null);
    setIsHomeLoading(true);
    setHomeLoadedEntityId(null);
    setHome(null);
    void api
      .getDashboardHomeSummary(selectedEntityId, 'panorama', '30')
      .then((nextHome) => {
        if (!cancelled) {
          setHome(nextHome);
          setHomeLoadedEntityId(selectedEntityId);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setHome(null);
          setHomeLoadedEntityId(selectedEntityId);
          setHomeError(error instanceof Error ? error.message : '安利 Console 首页数据加载失败');
        }
      })
      .finally(() => {
        if (!cancelled) setIsHomeLoading(false);
      });
    void fetchActiveRun(selectedEntityId);
    void fetchWorld(selectedEntityId);
    return () => {
      cancelled = true;
    };
  }, [fetchActiveRun, fetchWorld, selectedEntityId]);

  useEffect(() => {
    if (!selectedEntityId) {
      setDirectWorld(null);
      setDirectWorldEntityId(null);
      setDirectWorldError(null);
      return undefined;
    }
    let cancelled = false;
    setDirectWorld(null);
    setDirectWorldEntityId(selectedEntityId);
    setDirectWorldError(null);
    void api
      .getOntologyWorld(selectedEntityId)
      .then((world) => {
        if (!cancelled) setDirectWorld(world);
      })
      .catch((error) => {
        if (!cancelled) {
          setDirectWorld(null);
          setDirectWorldError(error instanceof Error ? error.message : '圈层图谱读取失败');
        }
      });
    return () => {
      cancelled = true;
    };
  }, [selectedEntityId]);

  useEffect(() => {
    if (!selectedEntityId) {
      setPeriodView(null);
      setPeriodError(null);
      setPeriodReportError(null);
      setIsPeriodLoading(false);
      return;
    }
    if (periodType === 'custom' && (!periodCustomStart || !periodCustomEnd)) {
      setPeriodError(null);
      setPeriodReportError(null);
      setIsPeriodLoading(false);
      return;
    }
    if (periodType === 'custom' && periodCustomStart > periodCustomEnd) {
      setPeriodError('开始日期不能晚于结束日期。');
      setPeriodReportError(null);
      setIsPeriodLoading(false);
      return;
    }
    let cancelled = false;
    setPeriodError(null);
    setPeriodReportError(null);
    setIsPeriodLoading(true);
    void api
      .getAmwayCirclePeriodView(selectedEntityId, {
        periodType,
        startAt: periodType === 'custom' && periodCustomStart
          ? `${periodCustomStart}T00:00:00+08:00`
          : null,
        endAt: periodType === 'custom' && periodCustomEnd
          ? customPeriodEndExclusive(periodCustomEnd)
          : null,
        centerTerm: effectiveCenterTerm,
      })
      .then((nextPeriodView) => {
        if (cancelled) return;
        const runCount = Number(nextPeriodView.current_period?.run_count || 0);
        const nodeCount = nextPeriodView.projection?.nodes?.length || 0;
        if (runCount <= 0 || nodeCount <= 0) {
          setPeriodError(null);
          setPeriodView(nextPeriodView);
          return;
        }
        setPeriodView(nextPeriodView);
      })
      .catch((error) => {
        if (!cancelled) {
          setPeriodError(error instanceof Error ? error.message : '周期图谱读取失败');
        }
      })
      .finally(() => {
        if (!cancelled) setIsPeriodLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [
    effectiveCenterTerm,
    periodCustomEnd,
    periodCustomStart,
    periodType,
    selectedEntityId,
    selectedRun?.id,
    selectedRun?.status,
  ]);

  useEffect(() => {
    if (!selectedEntityId || !isSelectedRunActive) return;
    const timer = window.setInterval(() => {
      void fetchActiveRun(selectedEntityId);
      void fetchWorld(selectedEntityId);
      void api
        .getDashboardHomeSummary(selectedEntityId, 'panorama', '30')
        .then((nextHome) => {
          setHome(nextHome);
          setHomeLoadedEntityId(selectedEntityId);
        })
        .catch(() => undefined);
    }, 6000);
    return () => window.clearInterval(timer);
  }, [fetchActiveRun, fetchWorld, isSelectedRunActive, selectedEntityId, selectedRun?.id, selectedRun?.status]);

  const liveTaskLookup = useMemo(() => {
    const rawOutputSessionId = selectedRun?.output_refs?.session_id;
    const outputSessionId = typeof rawOutputSessionId === 'string' ? rawOutputSessionId : null;
    const originSessionId = typeof selectedRun?.origin_session_id === 'string'
      ? selectedRun.origin_session_id
      : null;
    const sessionId = originSessionId || outputSessionId;
    const taskId = typeof selectedRun?.analysis_task_id === 'string'
      ? selectedRun.analysis_task_id
      : null;
    return { sessionId, taskId };
  }, [
    selectedRun?.analysis_task_id,
    selectedRun?.origin_session_id,
    selectedRun?.output_refs?.session_id,
  ]);

  useEffect(() => {
    setStreamedStageResults([]);
  }, [selectedRun?.id, liveTaskLookup.sessionId]);

  useEffect(() => {
    const { sessionId, taskId } = liveTaskLookup;
    if (!sessionId || !isSelectedRunActive) {
      setActiveTask(null);
      return;
    }
    let cancelled = false;
    const fetchLiveTask = () => {
      const request = taskId
        ? api.getTask(sessionId, taskId)
        : api.getActiveTask(sessionId);
      void request.then((task) => {
        if (!cancelled) setActiveTask(task);
      });
    };
    fetchLiveTask();
    const timer = window.setInterval(fetchLiveTask, 1000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [isSelectedRunActive, liveTaskLookup]);

  useEffect(() => {
    const { sessionId } = liveTaskLookup;
    if (!sessionId || !isSelectedRunActive || typeof window === 'undefined') return undefined;

    let closedByEffect = false;
    let reconnectTimer: number | null = null;
    let reconnectCount = 0;
    let socket: WebSocket | null = null;

    const connect = () => {
      if (closedByEffect) return;
      const token = window.localStorage.getItem('access_token')
        || (process.env.NODE_ENV === 'development' ? 'dev-token' : '');
      if (!token) return;
      const url = token === 'dev-token'
        ? `${WS_URL}/ws/${sessionId}?token=${encodeURIComponent(token)}`
        : `${WS_URL}/ws/${sessionId}`;
      socket = new WebSocket(url);
      socket.onopen = () => {
        reconnectCount = 0;
      };
      socket.onmessage = (event) => {
        if (closedByEffect) return;
        const stageResult = parseAssociationStageResult(event.data);
        if (!stageResult) return;
        setStreamedStageResults((current) => appendUniqueStageResult(current, stageResult, 500));
      };
      socket.onclose = () => {
        if (closedByEffect) return;
        const delay = Math.min(4000, 600 + reconnectCount * 600);
        reconnectCount += 1;
        reconnectTimer = window.setTimeout(connect, delay);
      };
      socket.onerror = () => {
        socket?.close();
      };
    };

    connect();
    return () => {
      closedByEffect = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [isSelectedRunActive, liveTaskLookup]);

  const handleStart = useCallback(
    async (payload?: AssociationCircleStartPayload) => {
      if (!selectedEntityId) return;
      const uploadedQuestions =
        payload?.uploadedQuestions?.filter((question) => question.text.trim()) || [];
      try {
        let uploadedQuestionSetId: string | null = payload?.questionSetId || null;
        let questionSetVersion: number | null = payload?.questionSetVersion || null;
        if (uploadedQuestions.length && payload?.persistQuestionSet && !uploadedQuestionSetId) {
          const savedQuestionSet = await api.saveAmwayQuestionHistory({
            entity_id: selectedEntityId,
            title: payload?.uploadedQuestionSource || `安利上传题库 ${new Date().toLocaleDateString('zh-CN')}`,
            source_file_name: payload?.uploadedQuestionSource || null,
            center_term: effectiveCenterTerm,
            center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : centerOptions,
            questions: uploadedQuestions.map((question) => ({
              ...question,
              question_text: question.text,
              center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : question.center_terms,
            })),
          });
          uploadedQuestionSetId = savedQuestionSet.id;
          questionSetVersion = savedQuestionSet.version || 1;
        }
        await createRun(selectedEntityId, {
          run_goal: '生成安利品牌联想圈层报告',
          analysis_mode: ASSOCIATION_ANALYSIS_MODE,
          origin_surface: 'amwaychina_console',
          origin_event_id: `amwaychina-start:${selectedEntityId}:${createHandoffId()}`,
          // M3: create plan snapshot and wait for canvas confirmation before dispatch
          auto_dispatch: false,
          input_scope: {
            dashboard_variant: ASSOCIATION_DASHBOARD_VARIANT,
            analysis_mode: ASSOCIATION_ANALYSIS_MODE,
            report_kind: ASSOCIATION_ANALYSIS_MODE,
            active_center_term: effectiveCenterTerm,
            center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : centerOptions,
            brand_cluster_terms: centerOptions.length ? centerOptions : DEFAULT_CENTER_TERMS,
            platforms: readEnabledFlowPlatforms(selectedEntityId),
            fetch_mode: payload?.fetchMode || 'full',
            enabled_surfaces: ['amwaychina_console', 'chat', 'canvas', 'brand_world'],
            question_input_mode: uploadedQuestions.length ? 'uploaded_list' : 'default_matrix',
            ...(uploadedQuestions.length
              ? {
                  uploaded_question_source: payload?.uploadedQuestionSource || 'amwaychina_upload',
                  uploaded_question_set_id: uploadedQuestionSetId,
                  question_set_version: questionSetVersion,
                  uploaded_question_count: uploadedQuestions.length,
                  uploaded_questions: uploadedQuestions.map((question) => ({
                    ...question,
                    center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : question.center_terms,
                  })),
                }
              : {}),
          },
        });
        // P1-7: confirmation CTA lives on the flow canvas — navigate there after plan is created
        const params = new URLSearchParams(searchParams.toString());
        params.set('view', 'flow');
        const query = params.toString();
        router.replace(query ? `?${query}` : '?', { scroll: false });
        toast.info('请在生产线视图确认执行计划后再开始采集');
        void fetchActiveRun(selectedEntityId);
        void fetchWorld(selectedEntityId);
        void api.getDashboardHomeSummary(selectedEntityId, 'panorama', '30').then((nextHome) => {
          setHome(nextHome);
          setHomeLoadedEntityId(selectedEntityId);
        });
      } catch (error) {
        toast.error(error instanceof Error ? error.message : '安利圈层建模启动失败');
      }
    },
    [
      centerOptions,
      createRun,
      effectiveCenterTerm,
      fetchActiveRun,
      fetchWorld,
      router,
      searchParams,
      selectedEntityId,
    ],
  );

  const handleOpenLatestReport = useCallback(() => {
    if (!home?.latest_report?.session_id) {
      toast.info('当前还没有可打开的圈层报告。');
      return;
    }
    const reportRef = latestReportRef(home.latest_report);
    markReportTodoViewed(selectedEntityId, reportRef);
    const params = new URLSearchParams();
    const artifactTarget = home.latest_report.artifact_id || home.latest_report.output_id;
    if (artifactTarget) params.set('artifact_id', artifactTarget);
    if (home.latest_report.output_id) params.set('output_id', home.latest_report.output_id);
    if (selectedEntity) {
      params.set('entity_id', selectedEntity.id);
      params.set('brand', selectedEntity.name);
      params.set('entry_source', 'amway_association_console_report');
    }
    router.push(
      buildDashboardChatUrlWithHandoff(
        home.latest_report.session_id,
        Object.fromEntries(params.entries()),
      ),
    );
  }, [home, router, selectedEntity, selectedEntityId]);

  const handleGeneratePeriodReport = useCallback(async (): Promise<boolean> => {
    if (!selectedEntityId || isPeriodReportGenerating) return false;
    if (periodError) {
      toast.info(periodError);
      return false;
    }
    if (periodType === 'custom' && periodCustomStart > periodCustomEnd) {
      const message = '开始日期不能晚于结束日期。';
      setPeriodReportError(message);
      toast.error(message);
      return false;
    }
    setPeriodReportError(null);
    setIsPeriodReportGenerating(true);
    try {
      const nextPeriodView = await api.generateAmwayCirclePeriodReport(selectedEntityId, {
        period_type: periodType,
        start_at: periodType === 'custom' && periodCustomStart
          ? `${periodCustomStart}T00:00:00+08:00`
          : null,
        end_at: periodType === 'custom' && periodCustomEnd
          ? customPeriodEndExclusive(periodCustomEnd)
          : null,
        center_term: effectiveCenterTerm || DEFAULT_CENTER_TERMS[0],
      });
      setPeriodError(null);
      setPeriodReportError(null);
      setPeriodView(nextPeriodView);
      return true;
    } catch {
      const message = '周期报告生成失败，请稍后重试。';
      setPeriodReportError(message);
      toast.error(message);
      return false;
    } finally {
      setIsPeriodReportGenerating(false);
    }
  }, [
    effectiveCenterTerm,
    isPeriodReportGenerating,
    periodCustomEnd,
    periodCustomStart,
    periodType,
    periodError,
    selectedEntityId,
  ]);

  const handleSelectView = useCallback(
    (view: ConsoleView) => {
      const params = new URLSearchParams(searchParams.toString());
      if (view === 'circle') params.delete('view');
      else params.set('view', view);
      const query = params.toString();
      router.replace(query ? `?${query}` : '?', { scroll: false });
    },
    [router, searchParams],
  );

  const handleOpenRunSettings = useCallback(() => {
    handleSelectView('circle');
    setRunSettingsRequest((current) => current + 1);
  }, [handleSelectView]);

  const handleOpenReport = useCallback(() => {
    handleSelectView('circle');
    setReportRequest((current) => current + 1);
  }, [handleSelectView]);

  const consoleProjection = useMemo(
    () => buildAssociationProjection(selectedWorld, home),
    [home, selectedWorld],
  );
  const headerIsRunning =
    isSelectedRunExecuting
    || Boolean(selectedEntity && submittingByEntity[selectedEntity.id]);
  const headerStatusLabel = isAwaitingPlanConfirm
    ? '待确认计划'
    : headerIsRunning
      ? '正在运行'
      : isProjectionLoading
        ? '正在读取'
        : consoleProjection.nodes.length > 0
          ? '圈层已生成'
          : '待运行';
  const headerHasPeriodReport = Boolean(
    periodView?.report_id && hasReportContent(periodView.projection),
  );
  const headerReportLabel = isPeriodReportGenerating
    ? '生成中'
    : headerHasPeriodReport
      ? reportQualityPassed(periodView?.projection) ? '查看报告' : '查看待校验报告'
      : '生成报告';
  const headerReportDisabled = headerIsRunning
    || Boolean(isPeriodReportGenerating)
    || (!headerHasPeriodReport && !consoleProjection.nodes.length);

  const handleQuickRun = useCallback(() => {
    void handleStart();
  }, [handleStart]);

  const handleConfirmFlowPlan = useCallback(async () => {
    if (!selectedEntityId || !selectedRun?.id) return;
    try {
      await confirmRun(selectedEntityId, selectedRun.id, {
        user_action_type: 'confirm_flow_plan',
        provided_inputs: {
          platforms: readEnabledFlowPlatforms(selectedEntityId),
        },
      });
      void fetchActiveRun(selectedEntityId);
      toast.success('计划已确认，开始执行');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '确认计划失败');
    }
  }, [confirmRun, fetchActiveRun, selectedEntityId, selectedRun?.id]);

  const handleRefreshFlowPlan = useCallback(async () => {
    if (!selectedEntityId || !selectedRun?.id) return;
    try {
      await confirmRun(selectedEntityId, selectedRun.id, {
        user_action_type: 'refresh_flow_plan',
        provided_inputs: {
          platforms: readEnabledFlowPlatforms(selectedEntityId),
        },
      });
      void fetchActiveRun(selectedEntityId);
      toast.success('已按当前拓扑刷新计划');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '刷新计划失败');
    }
  }, [confirmRun, fetchActiveRun, selectedEntityId, selectedRun?.id]);

  const handleCancelFlowPlan = useCallback(async () => {
    if (!selectedEntityId || !selectedRun?.id) return;
    try {
      await cancelRun(selectedEntityId, selectedRun.id);
      void fetchActiveRun(selectedEntityId);
      toast.info('已取消本次运行');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '取消失败');
    }
  }, [cancelRun, fetchActiveRun, selectedEntityId, selectedRun?.id]);

  if (entitiesLoading && !consoleEntities.length) {
    return (
      <div className="amway-console min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          正在加载安利品牌圈层 Console...
        </div>
      </div>
    );
  }

  if ((entityError && !directEntity) || directEntityError || directWorldError || homeError) {
    return (
      <div className="amway-console min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          <h1 className="text-2xl font-semibold">安利 Console 加载失败</h1>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
            {entityError || directEntityError || directWorldError || homeError}
          </p>
        </div>
      </div>
    );
  }

  if (!selectedEntity) {
    return (
      <div className="amway-console min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          <div className="text-xs font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
            安利专项权限
          </div>
          <h1 className="mt-2 text-2xl font-semibold">当前账号未开通安利品牌圈层 Console</h1>
          <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
            Console 只读取带安利圈层权限的品牌实体。普通品牌仍在标准 Dashboard 中使用原有分析流程。
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="amway-console flex min-h-screen bg-[var(--bg-secondary)]">
      <nav
        aria-label="安利 Console 导航"
        className="sticky top-0 flex h-screen w-52 shrink-0 flex-col border-r border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-5"
      >
        <div className="px-2 text-xs font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
          安利品牌圈层
        </div>
        <div className="mt-4 space-y-1">
          {CONSOLE_VIEWS.map((item) => {
            const Icon = item.icon;
            const active = consoleView === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => handleSelectView(item.id)}
                aria-current={active ? 'page' : undefined}
                className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition ${
                  active
                    ? 'bg-[var(--brand-bg)] text-[var(--brand-primary)]'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)] hover:text-[var(--text-primary)]'
                }`}
              >
                <Icon size={16} aria-hidden />
                {item.label}
              </button>
            );
          })}
        </div>
      </nav>

      <div className="min-w-0 flex-1">
        <AmwayConsoleHeader
          viewLabel={CONSOLE_VIEWS.find((item) => item.id === consoleView)?.label || '品牌圈层'}
          statusLabel={headerStatusLabel}
          isRunning={headerIsRunning}
          reportLabel={headerReportLabel}
          reportDisabled={headerReportDisabled}
          reportPrimary={headerHasPeriodReport}
          onReportClick={handleOpenReport}
        />
        {consoleView === 'circle' ? (
          <AmwayAssociationCircleDashboard
            entities={amwayEntities}
            selectedEntity={selectedEntity}
            selectedEntityId={selectedEntityId}
            centerOptions={centerOptions}
            selectedCenterTerm={effectiveCenterTerm}
            home={home}
            world={selectedWorld}
            activeRun={selectedRun}
            activeTask={activeTask}
            isRunActive={isSelectedRunExecuting}
            isRunSubmitting={Boolean(submittingByEntity[selectedEntity.id])}
            isProjectionLoading={isProjectionLoading}
            runError={errorByEntity[selectedEntity.id]}
            liveStageResults={streamedStageResults}
            periodType={periodType}
            periodCustomStart={periodCustomStart}
            periodCustomEnd={periodCustomEnd}
            periodView={periodView}
            isPeriodLoading={isPeriodLoading}
            isPeriodReportGenerating={isPeriodReportGenerating}
            periodError={periodError}
            periodReportError={periodReportError}
            openRunSettingsSignal={runSettingsRequest}
            openReportSignal={reportRequest}
            onSelectEntity={setSelectedEntityId}
            onSelectCenterTerm={setSelectedCenterTerm}
            onSelectPeriodType={setPeriodType}
            onChangePeriodCustomStart={setPeriodCustomStart}
            onChangePeriodCustomEnd={setPeriodCustomEnd}
            onGeneratePeriodReport={handleGeneratePeriodReport}
            onStart={handleStart}
            onOpenLatestReport={handleOpenLatestReport}
          />
        ) : null}

        {consoleView === 'flow' ? (
          <AmwayFlowCanvas
            key={`flow:${selectedEntity.id}:${effectiveCenterTerm}`}
            entityId={selectedEntity.id}
            centerTerm={effectiveCenterTerm || DEFAULT_CENTER_TERMS[0]}
            world={selectedWorld}
            home={home}
            periodView={periodView}
            activeRun={selectedRun}
            activeTask={activeTask}
            isRunActive={isSelectedRunExecuting}
            isRunSubmitting={Boolean(submittingByEntity[selectedEntity.id])}
            isAwaitingPlanConfirm={isAwaitingPlanConfirm}
            liveStageResults={streamedStageResults}
            onQuickRun={handleQuickRun}
            onConfirmFlowPlan={handleConfirmFlowPlan}
            onRefreshFlowPlan={handleRefreshFlowPlan}
            onCancelFlowPlan={handleCancelFlowPlan}
            onOpenRunSettings={handleOpenRunSettings}
            onOpenCircle={() => handleSelectView('circle')}
          />
        ) : null}

        {consoleView === 'settings' ? (
          <div className="mx-auto max-w-[1920px] px-5 py-4 text-[var(--text-primary)] lg:px-7 2xl:px-10">
            <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-4 shadow-sm">
              <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--brand-primary)]">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--brand-primary)]" />
                系统设置
              </div>
              <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <h1 className="text-2xl font-semibold leading-tight tracking-tight">设置</h1>
                <p className="text-sm text-[var(--text-secondary)]">账号、登录与权限管理</p>
              </div>
            </section>
            <div className="mt-4 max-w-2xl rounded-2xl border border-dashed border-[var(--border-strong)] bg-[var(--bg-primary)] p-8">
              <h2 className="text-base font-semibold">系统设置入口已保留</h2>
              <p className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                账号信息、登录方式与权限管理会放在这里，目前正在规划中。实体词库与问题集仍在「品牌圈层」页内维护。
              </p>
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}
