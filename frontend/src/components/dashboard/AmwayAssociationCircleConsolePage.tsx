'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  AmwayAssociationCircleDashboard,
  type AssociationCircleStartPayload,
} from './AmwayAssociationCircleDashboard';
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
import { isActiveBrandIntelligenceRun } from '@/types/intelligenceRun';
import type { Entity } from '@/types/entity';
import type { AnalysisTask } from '@/types/task';
import type { StageResult } from '@/types/snapshot';
import type { OntologyWorldSummary } from '@/types/ontology';

const ASSOCIATION_ANALYSIS_MODE = 'brand_association_circle';
const ASSOCIATION_DASHBOARD_VARIANT = 'amway_association_circle';
const DEFAULT_CENTER_TERMS = ['安利', '安利中国', '纽崔莱'];
const DEFAULT_ASSOCIATION_PLATFORMS = ['deepseek', 'kimi', 'hunyuan', 'doubao'];
const DEV_ENTITY_FALLBACK_DELAY_MS = 6000;
const ASSOCIATION_STAGE_RESULT_TYPES = new Set([
  'entity_extraction_signal',
  'entity_calibration_summary',
]);

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

export function AmwayAssociationCircleConsolePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedEntityId = searchParams.get('entity_id');
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
  } = useIntelligenceRunStore();
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [selectedCenterTerm, setSelectedCenterTerm] = useState<string | null>(DEFAULT_CENTER_TERMS[0]);
  const [home, setHome] = useState<DashboardHomeData | null>(null);
  const [isHomeLoading, setIsHomeLoading] = useState(false);
  const [homeLoadedEntityId, setHomeLoadedEntityId] = useState<string | null>(null);
  const [homeError, setHomeError] = useState<string | null>(null);
  const [isOpeningChat, setIsOpeningChat] = useState(false);
  const [activeTask, setActiveTask] = useState<AnalysisTask | null>(null);
  const [directEntity, setDirectEntity] = useState<Entity | null>(null);
  const [directEntityError, setDirectEntityError] = useState<string | null>(null);
  const [allowEntityFallback, setAllowEntityFallback] = useState(false);
  const [directWorld, setDirectWorld] = useState<OntologyWorldSummary | null>(null);
  const [directWorldEntityId, setDirectWorldEntityId] = useState<string | null>(null);
  const [directWorldError, setDirectWorldError] = useState<string | null>(null);
  const [streamedStageResults, setStreamedStageResults] = useState<StageResult[]>([]);

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
    () => consoleEntities.filter(isAmwayAssociationEntity),
    [consoleEntities],
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
        await createRun(selectedEntityId, {
          run_goal: '生成安利品牌联想圈层报告',
          analysis_mode: ASSOCIATION_ANALYSIS_MODE,
          origin_surface: 'amway_association_console',
          origin_event_id: `amway-console-start:${selectedEntityId}:${createHandoffId()}`,
          auto_dispatch: true,
          input_scope: {
            dashboard_variant: ASSOCIATION_DASHBOARD_VARIANT,
            analysis_mode: ASSOCIATION_ANALYSIS_MODE,
            report_kind: ASSOCIATION_ANALYSIS_MODE,
            active_center_term: effectiveCenterTerm,
            center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : centerOptions,
            brand_cluster_terms: centerOptions.length ? centerOptions : DEFAULT_CENTER_TERMS,
            platforms: DEFAULT_ASSOCIATION_PLATFORMS,
            enabled_surfaces: ['amway_console', 'chat', 'canvas', 'brand_world'],
            question_input_mode: uploadedQuestions.length ? 'uploaded_list' : 'default_matrix',
            ...(uploadedQuestions.length
              ? {
                  uploaded_question_source: payload?.uploadedQuestionSource || 'amway_console_upload',
                  uploaded_question_count: uploadedQuestions.length,
                  uploaded_questions: uploadedQuestions.map((question) => ({
                    ...question,
                    center_terms: effectiveCenterTerm ? [effectiveCenterTerm] : question.center_terms,
                  })),
                }
              : {}),
          },
        });
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
  }, [home?.latest_report, router, selectedEntity, selectedEntityId]);

  const handleOpenChat = useCallback(async () => {
    if (!selectedEntity || isOpeningChat) return;
    setIsOpeningChat(true);
    try {
      const session = await api.createSession(selectedEntity.id);
      const params = new URLSearchParams();
      params.set('entity_id', selectedEntity.id);
      params.set('brand', selectedEntity.name);
      params.set('entry_source', 'amway_association_console');
      params.set('analysis_mode', ASSOCIATION_ANALYSIS_MODE);
      params.set('dashboard_variant', ASSOCIATION_DASHBOARD_VARIANT);
      params.set('active_center_term', effectiveCenterTerm || selectedEntity.name);
      params.set('clean_handoff', '1');
      params.set('draft', '请基于当前安利品牌联想圈层解释重点、证据和下一步建议。');
      router.push(
        buildDashboardChatUrlWithHandoff(
          session.id,
          Object.fromEntries(params.entries()),
        ),
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开安利圈层对话失败');
    } finally {
      setIsOpeningChat(false);
    }
  }, [effectiveCenterTerm, isOpeningChat, router, selectedEntity]);

  if (entitiesLoading && !consoleEntities.length) {
    return (
      <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
        <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
          正在加载安利品牌圈层 Console...
        </div>
      </div>
    );
  }

  if ((entityError && !directEntity) || directEntityError || directWorldError || homeError) {
    return (
      <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
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
      <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
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
      isRunActive={isSelectedRunActive}
      isRunSubmitting={Boolean(submittingByEntity[selectedEntity.id])}
      isProjectionLoading={isProjectionLoading}
      runError={errorByEntity[selectedEntity.id]}
      isOpeningChat={isOpeningChat}
      liveStageResults={streamedStageResults}
      onSelectEntity={setSelectedEntityId}
      onSelectCenterTerm={setSelectedCenterTerm}
      onStart={(payload) => {
        void handleStart(payload);
      }}
      onOpenChat={() => {
        void handleOpenChat();
      }}
      onOpenLatestReport={handleOpenLatestReport}
    />
  );
}
