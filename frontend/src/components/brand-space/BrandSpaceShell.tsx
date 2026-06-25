'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  FileText,
  Pause,
  Play,
  Square,
} from 'lucide-react';
import { AssetsView } from './AssetsView';
import { BoardRuntimeView } from './BoardRuntimeView';
import { GraphHomeView } from './GraphHomeView';
import { ReportReviewView } from './ReportReviewView';
import styles from './BrandSpace.module.css';
import {
  DashboardBrandSidebar,
  DashboardMobileBrandSwitcher,
} from '@/components/dashboard/DashboardBrandSidebar';
import {
  artifacts,
  boardEdges,
  brandSpaceNavItems,
  buildStressBoardFixture,
  initialBoardNodes,
  initialGraphPatches,
  initialPlatforms,
  reportGuardrails,
} from '@/mocks/brandSpaceMock';
import { api } from '@/services/api';
import type {
  ArtifactDetail,
  ArtifactRef,
  ArtifactTraceLink,
  AssetListSummary,
  BoardNode,
  BoardRunStatus,
  BrandSpaceBoardRun,
  BrandSpaceGraph,
  BrandSpaceGraphUpdate,
  BrandSpacePayload,
  BrandSpaceReport,
  BrandSpaceReportSummary,
  BrandSpaceView,
  GraphReviewItem,
  GraphPatch,
  GraphPatchStatus,
  InspectorTab,
  NodeStatus,
  PaginationInfo,
  PlatformFetchNode,
  RuntimeEvent,
} from '@/types/brandSpace';
import type { Entity } from '@/types/entity';

interface BrandSpaceShellProps {
  entities: Entity[];
  selectedEntityId: string | null;
  entitiesLoading: boolean;
  hasFetchedEntities: boolean;
  entityError: string | null;
  onSelectBrand: (brandId: string) => void;
  onAddBrand: () => void;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function runStatusLabel(status: BoardRunStatus) {
  if (status === 'running') return '运行中';
  if (status === 'pause_requested') return '暂停中';
  if (status === 'paused') return '已暂停';
  if (status === 'stopped') return '已停止';
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  return '就绪';
}

function runModeLabel(isBackendMode: boolean, isDemoMode: boolean, spaceRun: BrandSpaceBoardRun | null) {
  if (isDemoMode) return '底版演示运行';
  if (!isBackendMode) return '品牌空间状态';
  if (spaceRun?.is_scaffold) return '脚手架预览运行';
  if (spaceRun?.status === 'stopped' || spaceRun?.status === 'completed' || spaceRun?.status === 'failed') {
    return `真实运行记录 · ${runStatusLabel(spaceRun.status)}`;
  }
  return '真实运行态';
}

function graphUpdateBuildStatus(spaceRun: BrandSpaceBoardRun | null) {
  const status = spaceRun?.output_refs?.graph_update_build_status;
  return typeof status === 'string' ? status : '';
}

function shouldAwaitGraphUpdate(spaceRun: BrandSpaceBoardRun | null, graphUpdate: BrandSpaceGraphUpdate | null) {
  if (!spaceRun || spaceRun.is_scaffold || spaceRun.status !== 'completed') return false;
  const buildStatus = graphUpdateBuildStatus(spaceRun);
  return !graphUpdate || buildStatus === 'pending' || buildStatus === 'queued' || buildStatus === 'building';
}

function advanceStatus(status: NodeStatus): NodeStatus {
  if (status === 'paused') return 'running';
  if (status === 'idle' || status === 'queued') return 'running';
  return status;
}

function pauseStatus(status: NodeStatus): NodeStatus {
  return status === 'running' ? 'paused' : status;
}

function progressPlatform(platform: PlatformFetchNode, index: number): PlatformFetchNode {
  if (platform.status !== 'running') return platform;
  return {
    ...platform,
    progress: Math.min(96, platform.progress + 2 + index),
    answers: platform.answers + 3 + index,
  };
}

function progressNode(node: BoardNode, index: number): BoardNode {
  if (node.status !== 'running') return node;
  return {
    ...node,
    progress: Math.min(96, node.progress + 1 + (index % 3)),
  };
}

const emptyBrandSpaceContext = {
  brandName: '品牌空间',
  graphVersion: '未连接',
  boardName: 'AI 能见度监测画布',
  runId: '',
  startedAt: '',
  duration: '00:00:00',
};

const emptyGraph: BrandSpaceGraph = {
  entities: [],
  relations: [],
  evidenceRefs: [],
};

const ASSET_PAGE_SIZE = 6;

function assetSummaryFromList(items: ArtifactRef[]): AssetListSummary {
  return {
    total: items.length,
    returned: items.length,
    by_type: items.reduce<Record<string, number>>((acc, artifact) => {
      acc[artifact.type] = (acc[artifact.type] ?? 0) + 1;
      return acc;
    }, {}),
  };
}

function buildLocalArtifactDetail(artifact: ArtifactRef): ArtifactDetail {
  return {
    artifact,
    preview: {
      kind: 'summary',
      title: artifact.label,
      summary: '当前处于本地演示底版，资产详情使用安全摘要预览；连接后端后会显示真实图谱更新、回答样本和报告追溯。',
      items: [
        { label: '类型', value: artifactTypeLabel(artifact.type) },
        { label: '记录数', value: artifact.rowCount ?? '-' },
        { label: '来源节点', value: artifact.linkedNodeId ?? '-' },
      ],
      rowCount: artifact.rowCount ?? 0,
      truncated: false,
    },
    trace: {
      links: [
        {
          kind: 'board_run',
          id: artifact.boardRunId ?? 'local-run',
          label: '本地演示画布',
          targetView: 'boards',
        },
        ...(artifact.linkedNodeId
          ? [{
              kind: 'node_run',
              id: artifact.linkedNodeId,
              label: artifact.linkedNodeId,
              nodeId: artifact.linkedNodeId,
              targetView: 'boards' as const,
            }]
          : []),
      ],
    },
    access: {
      canPreview: true,
      mode: 'local_mock_summary',
      provider: 'local',
      objectKey: artifact.path,
      available: false,
      downloadUrl: null,
      reason: 'object_not_materialized',
    },
  };
}

function artifactTypeLabel(type: string) {
  const labels: Record<string, string> = {
    entity_lexicon: '实体词表',
    question_set: '问题集',
    raw_answers: '原始答案',
    parsed_answers: '标准化回答',
    entity_relation_set: '实体关系集',
    graph_patch_set: '图谱补丁集',
    review_queue: '审阅队列',
    graph_update: '图谱更新',
    report: '报告',
  };
  return labels[type] ?? type;
}

function runtimeEventSequence(event: RuntimeEvent) {
  return typeof event.sequence === 'number' ? event.sequence : -1;
}

const RUNTIME_EVENT_WINDOW_LIMIT = 240;
const RUNTIME_EVENT_TRUNCATION_TYPE = 'event_window_truncated';

function limitRuntimeEvents(events: RuntimeEvent[]) {
  const source = [...events]
    .filter((event) => event.type !== RUNTIME_EVENT_TRUNCATION_TYPE)
    .sort((left, right) => runtimeEventSequence(left) - runtimeEventSequence(right));
  if (source.length <= RUNTIME_EVENT_WINDOW_LIMIT) return source;

  const retained = source.slice(-(RUNTIME_EVENT_WINDOW_LIMIT - 1));
  const firstRetained = retained[0];
  const firstSequence = firstRetained ? runtimeEventSequence(firstRetained) : -1;
  const droppedCount = source.length - retained.length;
  const marker: RuntimeEvent = {
    id: `runtime-event-window-truncated-${droppedCount}-${firstSequence}`,
    sequence: firstSequence > 0 ? firstSequence - 1 : null,
    timestamp: firstRetained?.timestamp ?? new Date(0).toISOString(),
    type: RUNTIME_EVENT_TRUNCATION_TYPE,
    severity: 'info',
    message: `已折叠 ${droppedCount} 条较早运行日志，当前保留最近 ${retained.length} 条。`,
    payload: {
      droppedCount,
      retainedCount: retained.length,
      windowLimit: RUNTIME_EVENT_WINDOW_LIMIT,
    },
  };
  return [marker, ...retained];
}

function mergeRuntimeEvents(current: RuntimeEvent[], incoming: RuntimeEvent[]) {
  if (!incoming.length) return limitRuntimeEvents(current);
  const byId = new Map<string, RuntimeEvent>();
  [...current, ...incoming].forEach((event) => {
    if (event.type === RUNTIME_EVENT_TRUNCATION_TYPE) return;
    byId.set(event.id, event);
  });
  return limitRuntimeEvents([...byId.values()]);
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(url);
}

function fallbackReviewCategory(patch: GraphPatch) {
  if (patch.category) return patch.category;
  if (patch.patchType === 'add_competitor_relation' || patch.relationType === 'competes_with') return 'competitor';
  if (patch.patchType === 'add_risk_relation') return 'risk';
  if (patch.patchType === 'add_entity') return 'new_entity';
  if (patch.confidence !== null && patch.confidence !== undefined && patch.confidence < 0.7) return 'low_confidence';
  return patch.status === 'blocked' ? 'conflict' : 'graph_change';
}

function reviewItemsFromPatches(patches: GraphPatch[], graphUpdate?: BrandSpaceGraphUpdate | null): GraphReviewItem[] {
  return patches
    .filter((patch) => patch.status === 'needs_review' || patch.status === 'blocked')
    .map((patch) => ({
      ...patch,
      graphUpdateId: patch.graphUpdateId ?? graphUpdate?.id ?? 'local-graph-update',
      graphUpdateStatus: graphUpdate?.status ?? 'needs_review',
      boardRunId: graphUpdate?.board_run_id ?? null,
      beforeGraphVersion: graphUpdate?.before_graph_version ?? 'v0.0.0',
      afterGraphVersion: graphUpdate?.after_graph_version ?? 'v0.1.0',
      graphUpdateCreatedAt: graphUpdate?.created_at ?? patch.createdAt ?? '',
      category: fallbackReviewCategory(patch),
      priority: patch.priority ?? (patch.status === 'blocked' ? 'high' : 'medium'),
    }));
}

function backendNoticeFromError(error: unknown, fallback: string) {
  if (!(error instanceof Error)) return fallback;
  if (/not authenticated|unauthorized|forbidden|401|403/i.test(error.message)) {
    return `${fallback}（请重新登录，或确认当前账号有该品牌的访问权限）`;
  }
  if (/internal server error|request failed:\s*5\d\d/i.test(error.message)) {
    return `${fallback}（服务暂时异常，已保留当前页面状态）`;
  }
  if (/failed to fetch|fetch failed|load failed|networkerror/i.test(error.message)) {
    return `${fallback}（后端连接不可用）`;
  }
  if (/request failed:\s*\d+/i.test(error.message)) {
    return `${fallback}（接口返回异常）`;
  }
  return fallback;
}

function idleBoardNodes() {
  return initialBoardNodes.map((node) => ({
    ...node,
    status: 'idle' as NodeStatus,
    progress: 0,
    metrics: [],
    outputArtifactIds: [],
  }));
}

function idlePlatforms() {
  return initialPlatforms.map((platform) => ({
    ...platform,
    status: 'idle' as NodeStatus,
    progress: 0,
    answers: 0,
    failures: 0,
  }));
}

function canvasStressFixtureCount() {
  if (typeof window === 'undefined') return null;
  const params = new URLSearchParams(window.location.search);
  const value = params.get('canvasFixture');
  const match = value?.match(/^(\d+)-nodes$/);
  if (!match) return null;
  const count = Number.parseInt(match[1], 10);
  if (!Number.isFinite(count) || count < 1) return null;
  return Math.min(count, 120);
}

async function loadBrandSpacePayloadForEntity(entityId: string) {
  return {
    entityId,
    payload: await api.getBrandSpace(entityId),
  };
}

export function BrandSpaceShell({
  entities,
  selectedEntityId,
  entitiesLoading,
  hasFetchedEntities,
  entityError,
  onSelectBrand,
  onAddBrand,
}: BrandSpaceShellProps) {
  const [activeView, setActiveView] = useState<BrandSpaceView>('graph');
  const [context, setContext] = useState(emptyBrandSpaceContext);
  const [spaceRun, setSpaceRun] = useState<BrandSpaceBoardRun | null>(null);
  const [entityId, setEntityId] = useState<string | null>(null);
  const [isBackendMode, setIsBackendMode] = useState(false);
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [isLoadingSpace, setIsLoadingSpace] = useState(true);
  const [spaceLoadError, setSpaceLoadError] = useState('');
  const [spaceReloadKey, setSpaceReloadKey] = useState(0);
  const [backendNotice, setBackendNotice] = useState('');
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [runStatus, setRunStatus] = useState<BoardRunStatus>('idle');
  const [nodes, setNodes] = useState<BoardNode[]>(() => idleBoardNodes());
  const [platforms, setPlatforms] = useState<PlatformFetchNode[]>(() => idlePlatforms());
  const [edges, setEdges] = useState(boardEdges);
  const [patches, setPatches] = useState<GraphPatch[]>([]);
  const [reviewItems, setReviewItems] = useState<GraphReviewItem[]>([]);
  const [artifactsState, setArtifactsState] = useState<ArtifactRef[]>([]);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [graph, setGraph] = useState<BrandSpaceGraph>(emptyGraph);
  const [graphUpdate, setGraphUpdate] = useState<BrandSpaceGraphUpdate | null>(null);
  const [guardrails, setGuardrails] = useState(reportGuardrails);
  const [report, setReport] = useState<BrandSpaceReport | null>(null);
  const [reports, setReports] = useState<BrandSpaceReportSummary[]>([]);
  const [selectedArtifactDetail, setSelectedArtifactDetail] = useState<ArtifactDetail | null>(null);
  const [isLoadingArtifactDetail, setIsLoadingArtifactDetail] = useState(false);
  const [isLoadingAssets, setIsLoadingAssets] = useState(false);
  const [assetTypeFilter, setAssetTypeFilter] = useState('all');
  const [assetSummary, setAssetSummary] = useState<AssetListSummary | null>(() => assetSummaryFromList([]));
  const [assetPagination, setAssetPagination] = useState<PaginationInfo | null>(null);
  const [pendingPatchDecisionIds, setPendingPatchDecisionIds] = useState<string[]>([]);
  const [downloadingArtifactIds, setDownloadingArtifactIds] = useState<string[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState('platform-rack');
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('overview');
  const lastEventSequenceRef = useRef(0);
  const activeRunIdRef = useRef<string | null>(null);

  const selectedView = useMemo(
    () => brandSpaceNavItems.find((item) => item.id === activeView) ?? brandSpaceNavItems[0],
    [activeView],
  );
  const selectedEntity = useMemo(
    () => entities.find((entity) => entity.id === selectedEntityId) ?? null,
    [entities, selectedEntityId],
  );

  const resetSpaceState = useCallback((notice = '', brandName?: string) => {
    setIsBackendMode(false);
    setIsDemoMode(false);
    setSpaceLoadError('');
    setSpaceRun(null);
    setEntityId(null);
    setContext({
      ...emptyBrandSpaceContext,
      brandName: brandName ? `${brandName}品牌空间` : emptyBrandSpaceContext.brandName,
    });
    setRunStatus('idle');
    setNodes(idleBoardNodes());
    setPlatforms(idlePlatforms());
    setEdges(boardEdges);
    setPatches([]);
    setReviewItems([]);
    setArtifactsState([]);
    setAssetSummary(assetSummaryFromList([]));
    setAssetPagination(null);
    setEvents([]);
    setGraph(emptyGraph);
    setGraphUpdate(null);
    setGuardrails([]);
    setReport(null);
    setReports([]);
    setSelectedArtifactDetail(null);
    setAssetTypeFilter('all');
    setBackendNotice(notice);
    activeRunIdRef.current = null;
    lastEventSequenceRef.current = 0;
  }, []);

  const applySpacePayload = useCallback((payload: BrandSpacePayload) => {
    const incomingRunId = payload.run?.id ?? null;
    const runChanged = activeRunIdRef.current !== incomingRunId;
    activeRunIdRef.current = incomingRunId;
    setContext(payload.context);
    setSpaceRun(payload.run);
    setRunStatus(payload.run?.status ?? 'idle');
    setNodes(payload.nodes.length ? payload.nodes : initialBoardNodes);
    setPlatforms(payload.platforms.length ? payload.platforms : initialPlatforms);
    setEdges(payload.edges.length ? payload.edges : boardEdges);
    setPatches(payload.patches);
    setArtifactsState(payload.artifacts);
    setAssetSummary(assetSummaryFromList(payload.artifacts));
    setAssetPagination(null);
    setEvents(limitRuntimeEvents(payload.events));
    lastEventSequenceRef.current = Math.max(0, ...payload.events.map(runtimeEventSequence));
    setGraph(payload.graph ?? emptyGraph);
    setGraphUpdate(payload.graph_update);
    setGuardrails(payload.guardrails);
    if (payload.report !== undefined) {
      setReport(payload.report);
    }
    if (payload.reports) {
      setReports(payload.reports);
    }
    if (runChanged) {
      setSelectedArtifactDetail(null);
      setAssetTypeFilter('all');
    }
  }, []);

  const refreshReports = useCallback(async (targetEntityId: string) => {
    try {
      const response = await api.getBrandSpaceReports(targetEntityId, { limit: 30 });
      setReports(response.reports);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '报告列表刷新失败'));
    }
  }, []);

  const refreshAssets = useCallback(async (
    options?: {
      artifactType?: string;
      offset?: number;
      append?: boolean;
    },
  ): Promise<ArtifactRef[]> => {
    const artifactType = options?.artifactType ?? assetTypeFilter;
    const normalizedType = artifactType === 'all' ? undefined : artifactType;
    const offset = options?.offset ?? 0;
    const append = Boolean(options?.append);
    if (!isBackendMode || !spaceRun?.id) {
      if (!isDemoMode) {
        setArtifactsState([]);
        setAssetSummary(assetSummaryFromList([]));
        setAssetPagination(null);
        return [];
      }
      const localAssets = normalizedType
        ? artifacts.filter((artifact) => artifact.type === normalizedType)
        : artifacts;
      setArtifactsState(localAssets);
      setAssetSummary(assetSummaryFromList(artifacts));
      setAssetPagination(null);
      return localAssets;
    }
    setIsLoadingAssets(true);
    try {
      const response = await api.getBrandSpaceRunAssets(spaceRun.id, {
        artifactType: normalizedType,
        limit: ASSET_PAGE_SIZE,
        offset,
      });
      setArtifactsState((current) => {
        if (!append) return response.artifacts;
        const seen = new Set(current.map((artifact) => artifact.artifactId ?? artifact.id));
        return [
          ...current,
          ...response.artifacts.filter((artifact) => !seen.has(artifact.artifactId ?? artifact.id)),
        ];
      });
      setAssetSummary(response.summary ?? assetSummaryFromList(response.artifacts));
      setAssetPagination(response.pagination ?? null);
      return response.artifacts;
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '资产列表刷新失败'));
      return [];
    } finally {
      setIsLoadingAssets(false);
    }
  }, [assetTypeFilter, isBackendMode, isDemoMode, spaceRun?.id]);

  const refreshReviewItems = useCallback(async (targetEntityId: string, fallbackPatches: GraphPatch[], fallbackUpdate?: BrandSpaceGraphUpdate | null) => {
    try {
      const response = await api.getBrandSpaceReviewItems(targetEntityId);
      setReviewItems(response.review_items);
    } catch (error) {
      setReviewItems(reviewItemsFromPatches(fallbackPatches, fallbackUpdate));
      setBackendNotice(backendNoticeFromError(error, '审阅队列刷新失败'));
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadBrandSpace() {
      try {
        const stressFixtureCount = canvasStressFixtureCount();
        if (stressFixtureCount) {
          setIsLoadingSpace(true);
          const fixture = buildStressBoardFixture(stressFixtureCount);
          setIsBackendMode(false);
          setIsDemoMode(true);
          setRunStatus('running');
          setNodes(fixture.nodes);
          setEdges(fixture.edges);
          setSelectedNodeId(fixture.nodes[0]?.id ?? 'platform-rack');
          setReviewItems(reviewItemsFromPatches(initialGraphPatches));
          setBackendNotice(`${stressFixtureCount} 节点压力验证底版已启用。`);
          return;
        }

        if (entityError) {
          resetSpaceState('品牌列表加载失败，请刷新页面或回到品牌情报页重试。');
          return;
        }

        if (!hasFetchedEntities || entitiesLoading) {
          setIsLoadingSpace(true);
          resetSpaceState('', selectedEntity?.name);
          return;
        }

        if (!selectedEntityId) {
          resetSpaceState('', selectedEntity?.name);
          return;
        }

        setIsLoadingSpace(true);
        setSpaceLoadError('');
        const { entityId: loadedEntityId, payload } = await loadBrandSpacePayloadForEntity(selectedEntityId);
        if (cancelled) return;
        setEntityId(loadedEntityId);
        setIsBackendMode(true);
        setIsDemoMode(false);
        setSpaceLoadError('');
        setBackendNotice('');
        applySpacePayload(payload);
        setReviewItems(reviewItemsFromPatches(payload.patches, payload.graph_update));
        await refreshReviewItems(loadedEntityId, payload.patches, payload.graph_update);
      } catch (error) {
        if (cancelled) return;
        resetSpaceState('', selectedEntity?.name);
        setSpaceLoadError(backendNoticeFromError(error, '品牌空间数据加载失败'));
      } finally {
        if (!cancelled && hasFetchedEntities && !entitiesLoading) {
          setIsLoadingSpace(false);
        }
      }
    }

    void loadBrandSpace();

    return () => {
      cancelled = true;
    };
  }, [
    applySpacePayload,
    hasFetchedEntities,
    entitiesLoading,
    entityError,
    refreshReviewItems,
    resetSpaceState,
    selectedEntity?.name,
    selectedEntityId,
    spaceReloadKey,
  ]);

  useEffect(() => {
    if (!isBackendMode || !spaceRun?.id || runStatus !== 'running') return undefined;

    let cancelled = false;
    const pollEvents = () => {
      void api
        .getBrandSpaceRunEvents(spaceRun.id, {
          limit: 120,
          afterSequence: lastEventSequenceRef.current,
          sync: false,
        })
        .then((response) => {
          if (cancelled) return;
          if (response.events.length) {
            setEvents((current) => mergeRuntimeEvents(current, response.events));
          }
          const nextSequence = response.cursor?.next_sequence
            ?? Math.max(lastEventSequenceRef.current, ...response.events.map(runtimeEventSequence));
          lastEventSequenceRef.current = Math.max(lastEventSequenceRef.current, nextSequence);
        })
        .catch((error) => {
          setBackendNotice(backendNoticeFromError(error, '运行日志刷新失败'));
        });
    };

    pollEvents();

    const eventIntervalId = window.setInterval(pollEvents, 2500);
    const fullRefreshIntervalId = window.setInterval(() => {
      void api
        .getBrandSpaceBoardRun(spaceRun.id)
        .then(applySpacePayload)
        .catch((error) => {
          setBackendNotice(backendNoticeFromError(error, '运行态刷新失败'));
        });
    }, 15000);

    return () => {
      cancelled = true;
      window.clearInterval(eventIntervalId);
      window.clearInterval(fullRefreshIntervalId);
    };
  }, [applySpacePayload, isBackendMode, runStatus, spaceRun?.id]);

  useEffect(() => {
    if (!isBackendMode || !spaceRun?.id || !shouldAwaitGraphUpdate(spaceRun, graphUpdate)) return undefined;

    let cancelled = false;
    let attempts = 0;
    let intervalId: number | null = null;

    const refreshCompletedRun = async () => {
      attempts += 1;
      try {
        const payload = await api.getBrandSpaceBoardRun(spaceRun.id);
        if (cancelled) return;
        applySpacePayload(payload);
        if (entityId) {
          await refreshReviewItems(entityId, payload.patches, payload.graph_update);
        }
        if (!shouldAwaitGraphUpdate(payload.run, payload.graph_update) && intervalId !== null) {
          window.clearInterval(intervalId);
        }
      } catch (error) {
        if (!cancelled) {
          setBackendNotice(backendNoticeFromError(error, '图谱更新状态刷新失败'));
        }
      }

      if (!cancelled && attempts >= 10) {
        if (intervalId !== null) window.clearInterval(intervalId);
        setBackendNotice('图谱更新仍在后台构建中，稍后会自动进入图谱与报告视图。');
      }
    };

    const timeoutId = window.setTimeout(() => {
      void refreshCompletedRun();
    }, 2000);
    intervalId = window.setInterval(() => {
      void refreshCompletedRun();
    }, 5000);

    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
      if (intervalId !== null) window.clearInterval(intervalId);
    };
  }, [
    applySpacePayload,
    entityId,
    graphUpdate,
    isBackendMode,
    refreshReviewItems,
    spaceRun,
  ]);

  useEffect(() => {
    if (isBackendMode || !isDemoMode) return undefined;
    if (runStatus !== 'running') return undefined;

    const intervalId = window.setInterval(() => {
      setPlatforms((current) => current.map(progressPlatform));
      setNodes((current) => current.map(progressNode));
    }, 1400);

    return () => window.clearInterval(intervalId);
  }, [isBackendMode, isDemoMode, runStatus]);

  useEffect(() => {
    if (activeView !== 'assets') return;
    void refreshAssets({ artifactType: assetTypeFilter, offset: 0, append: false });
  }, [activeView, assetTypeFilter, refreshAssets]);

  const startLocalRun = () => {
    setRunStatus('running');
    setPlatforms((current) => current.map((platform) => ({ ...platform, status: advanceStatus(platform.status) })));
    setNodes((current) => current.map((node) => ({ ...node, status: advanceStatus(node.status) })));
  };

  const pauseLocalRun = () => {
    setRunStatus('paused');
    setPlatforms((current) => current.map((platform) => ({ ...platform, status: pauseStatus(platform.status) })));
    setNodes((current) => current.map((node) => ({ ...node, status: pauseStatus(node.status) })));
  };

  const resumeLocalRun = () => {
    setRunStatus('running');
    setPlatforms((current) => current.map((platform) => ({ ...platform, status: platform.status === 'paused' ? 'running' : platform.status })));
    setNodes((current) => current.map((node) => ({ ...node, status: node.status === 'paused' ? 'running' : node.status })));
  };

  const stopLocalRun = () => {
    setRunStatus('stopped');
    setPlatforms((current) => current.map((platform) => ({ ...platform, status: platform.status === 'running' ? 'paused' : platform.status })));
    setNodes((current) => current.map((node) => ({ ...node, status: node.status === 'running' ? 'paused' : node.status })));
  };

  const handleRunStart = async () => {
    if (!isBackendMode || !entityId) {
      if (!isDemoMode) {
        setBackendNotice('品牌空间数据尚未连接成功，请先重新加载品牌空间。');
        return;
      }
      startLocalRun();
      return;
    }
    try {
      const payload = spaceRun?.id && runStatus === 'paused'
        ? await api.resumeBrandSpaceBoardRun(spaceRun.id)
        : await api.createBrandSpaceBoardRun(entityId, { execution_mode: 'real' });
      applySpacePayload(payload);
      await refreshReviewItems(entityId, payload.patches, payload.graph_update);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '启动画布失败'));
    }
  };

  const handleRunPause = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      if (!isDemoMode) {
        setBackendNotice('品牌空间数据尚未连接成功，请先重新加载品牌空间。');
        return;
      }
      pauseLocalRun();
      return;
    }
    try {
      const payload = await api.pauseBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '暂停失败'));
    }
  };

  const handleRunResume = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      if (!isDemoMode) {
        setBackendNotice('品牌空间数据尚未连接成功，请先重新加载品牌空间。');
        return;
      }
      resumeLocalRun();
      return;
    }
    try {
      const payload = await api.resumeBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '继续失败'));
    }
  };

  const handleRunStop = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      if (!isDemoMode) {
        setBackendNotice('品牌空间数据尚未连接成功，请先重新加载品牌空间。');
        return;
      }
      stopLocalRun();
      return;
    }
    try {
      const payload = await api.stopBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '停止失败'));
    }
  };

  const handlePatchDecision = async (
    patchId: string,
    status: Extract<GraphPatchStatus, 'accepted' | 'rejected' | 'needs_review'>,
  ) => {
    if (pendingPatchDecisionIds.includes(patchId)) return;
    setPendingPatchDecisionIds((current) => [...current, patchId]);
    if (isBackendMode) {
      try {
        const response = await api.decideBrandSpaceGraphPatch(patchId, { status });
        setPatches(response.patches);
        setGraphUpdate(response.graph_update);
        setGuardrails(response.guardrails.length ? response.guardrails : guardrails);
        if (spaceRun?.id) {
          const payload = await api.getBrandSpaceBoardRun(spaceRun.id);
          applySpacePayload(payload);
          if (entityId) {
            await refreshReviewItems(entityId, payload.patches, payload.graph_update);
          }
        } else if (entityId) {
          await refreshReviewItems(entityId, response.patches, response.graph_update);
        }
        return;
      } catch (error) {
        setBackendNotice(backendNoticeFromError(error, '审阅提交失败'));
        return;
      } finally {
        setPendingPatchDecisionIds((current) => current.filter((id) => id !== patchId));
      }
    }
    setPatches((current) => {
      const nextPatches = current.map((patch) => (patch.id === patchId ? { ...patch, status } : patch));
      setReviewItems(reviewItemsFromPatches(nextPatches, graphUpdate));
      return nextPatches;
    });
    setPendingPatchDecisionIds((current) => current.filter((id) => id !== patchId));
  };

  const handleGenerateReport = async (publishRequested = false) => {
    if (!graphUpdate?.id) return;
    setIsGeneratingReport(true);
    try {
      const response = await api.generateBrandSpaceReport(graphUpdate.id, { publishRequested });
      setReport(response.report);
      setGuardrails(response.guardrails);
      if (entityId) {
        await refreshReports(entityId);
      }
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '报告生成失败'));
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const handleSelectReport = async (reportId: string) => {
    if (!isBackendMode) {
      return;
    }
    try {
      const response = await api.getBrandSpaceReport(reportId);
      setReport(response.report);
      setGuardrails(response.guardrails);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '报告读取失败'));
    }
  };

  const handleOpenArtifact = async (artifact: ArtifactRef) => {
    const artifactId = artifact.artifactId ?? artifact.id;
    if (!isBackendMode) {
      setSelectedArtifactDetail(buildLocalArtifactDetail(artifact));
      return;
    }
    setIsLoadingArtifactDetail(true);
    setSelectedArtifactDetail(null);
    try {
      const response = await api.getBrandSpaceArtifact(artifactId);
      setSelectedArtifactDetail(response);
    } catch (error) {
      setSelectedArtifactDetail(buildLocalArtifactDetail(artifact));
      setBackendNotice(backendNoticeFromError(error, '资产详情读取失败，已显示本地摘要'));
    } finally {
      setIsLoadingArtifactDetail(false);
    }
  };

  const handleDownloadArtifact = async (artifact: ArtifactRef) => {
    const artifactId = artifact.artifactId ?? artifact.id;
    if (!isBackendMode || downloadingArtifactIds.includes(artifactId)) return;
    setDownloadingArtifactIds((current) => [...current, artifactId]);
    try {
      const response = await api.downloadBrandSpaceArtifact(artifactId);
      downloadBlob(response.blob, response.filename);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '资产对象下载失败'));
    } finally {
      setDownloadingArtifactIds((current) => current.filter((id) => id !== artifactId));
    }
  };

  const handleAssetTypeChange = (artifactType: string) => {
    setAssetTypeFilter(artifactType);
    setSelectedArtifactDetail(null);
  };

  const handleLoadMoreAssets = () => {
    if (!assetPagination?.has_more) return;
    void refreshAssets({
      artifactType: assetTypeFilter,
      offset: assetPagination.offset + assetPagination.limit,
      append: true,
    });
  };

  const handleOpenReportAsset = async () => {
    setActiveView('assets');
    setAssetTypeFilter('report');
    const loadedAssets = await refreshAssets({
      artifactType: 'report',
      offset: 0,
      append: false,
    });
    const reportAsset = loadedAssets.find((artifact) => artifact.type === 'report');
    if (!reportAsset) {
      setSelectedArtifactDetail(null);
      setBackendNotice('本次运行暂无报告资产；请先生成图谱更新解读报告。');
      return;
    }
    await handleOpenArtifact(reportAsset);
  };

  const handleTraceTarget = (link: ArtifactTraceLink) => {
    if (link.targetView) {
      setActiveView(link.targetView);
    }
    if (link.nodeId) {
      setSelectedNodeId(link.nodeId);
      setInspectorTab('output');
    }
    if (link.reportVersionId) {
      void handleSelectReport(link.reportVersionId);
    }
  };

  const handlePublishReport = async () => {
    if (!report?.id) return;
    setIsGeneratingReport(true);
    try {
      const response = await api.publishBrandSpaceReport(report.id);
      setReport(response.report);
      setGuardrails(response.guardrails);
      if (entityId) {
        await refreshReports(entityId);
      }
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '报告发布失败'));
    } finally {
      setIsGeneratingReport(false);
    }
  };

  const hasSelectedBrand = Boolean(selectedEntityId && selectedEntity);
  const showBackendErrorState = !isDemoMode
    && hasSelectedBrand
    && !isLoadingSpace
    && !isBackendMode
    && Boolean(spaceLoadError);
  const runControlsDisabled = !hasSelectedBrand
    || Boolean(entityError)
    || isLoadingSpace
    || (!isBackendMode && !isDemoMode);
  const showSetupEmptyState = !isDemoMode && !showBackendErrorState && (Boolean(entityError) || (hasFetchedEntities && !hasSelectedBrand));
  const showLoadingState = !isDemoMode && !showSetupEmptyState && isLoadingSpace;
  const showWorkspaceViews = !showSetupEmptyState && !showLoadingState && !showBackendErrorState;
  const setupTitle = entityError ? '品牌列表暂时不可用' : '先创建或选择一个品牌';
  const setupDescription = entityError
    ? '当前无法读取账号下的品牌列表。你可以刷新页面，或返回品牌情报页检查账号和品牌数据。'
    : '品牌空间围绕一个品牌的实体关系库运行。请选择左侧已有品牌，或新建品牌后再启动图谱更新画布。';

  return (
    <div className={styles.root}>
      <div className={styles.shell}>
        <aside className={styles.sidebar}>
          <DashboardBrandSidebar
            entities={entities}
            selectedBrandId={selectedEntityId}
            onSelectBrand={onSelectBrand}
            onAddBrand={onAddBrand}
            showBrandSpaceLink={false}
          />
        </aside>

        <main className={styles.main}>
          <div className="px-4 pt-4 lg:hidden">
            <DashboardMobileBrandSwitcher
              entities={entities}
              selectedBrandId={selectedEntityId}
              onSelectBrand={onSelectBrand}
              onAddBrand={onAddBrand}
              showBrandSpaceLink={false}
            />
          </div>
          <header className={classNames(styles.topbar, 'flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-6')}>
            <div className="flex min-w-0 items-center gap-3">
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold text-[var(--text-primary)]">{context.brandName}</h1>
                <p className="mt-1 text-xs text-[var(--text-secondary)]">
                  {context.boardName} · {context.graphVersion}
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }} aria-live="polite">
                <span className={classNames('h-2 w-2 rounded-full', runStatus === 'running' && 'animate-pulse')} style={{ background: runStatus === 'running' ? 'var(--brand-primary)' : 'var(--text-tertiary)' }} />
                {runStatusLabel(runStatus)}
              </span>
              <button
                type="button"
                onClick={runStatus === 'running' ? handleRunPause : runStatus === 'paused' ? handleRunResume : handleRunStart}
                disabled={runControlsDisabled}
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-55"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                aria-label={runStatus === 'running' ? '暂停当前画布运行' : runStatus === 'paused' ? '继续当前画布运行' : '启动当前画布运行'}
              >
                {runStatus === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {runStatus === 'running' ? '暂停' : runStatus === 'paused' ? '继续' : '运行'}
              </button>
              <button
                type="button"
                onClick={handleRunStop}
                disabled={runControlsDisabled || (!spaceRun?.id && !isDemoMode)}
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)] disabled:cursor-not-allowed disabled:opacity-55"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                aria-label="停止当前画布运行"
              >
                <Square className="h-4 w-4" />
                停止
              </button>
            </div>
          </header>

          <div className={classNames(styles.viewTabs, 'flex flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-6')}>
            <div className="flex flex-wrap items-center gap-2">
              {brandSpaceNavItems.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveView(item.id)}
                  className="rounded-lg px-3 py-2 text-sm font-medium transition-colors"
                  aria-current={activeView === item.id ? 'page' : undefined}
                  aria-pressed={activeView === item.id}
                  style={{
                    background: activeView === item.id ? 'var(--bg-elevated)' : 'transparent',
                    color: activeView === item.id ? 'var(--brand-text)' : 'var(--text-secondary)',
                    boxShadow: activeView === item.id ? 'var(--shadow-sm)' : 'none',
                  }}
                >
                  {item.label}
                </button>
              ))}
            </div>
            <div className="flex items-center gap-2 text-xs text-[var(--text-secondary)]">
              <FileText className="h-3.5 w-3.5" />
              <span>{selectedView.description}</span>
            </div>
          </div>

          <div className="min-h-0 overflow-auto p-4 lg:p-6">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
              <div>
                <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">
                  {runModeLabel(isBackendMode, isDemoMode, spaceRun)}
                  {isLoadingSpace ? ' · 加载中' : ''}
                </p>
                <h2 className="mt-1 text-xl font-semibold text-[var(--text-primary)]">{selectedView.label}</h2>
                {backendNotice ? (
                  <p className="mt-1 text-xs text-[var(--warning)]">{backendNotice}</p>
                ) : null}
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                <span className="rounded-lg border px-2.5 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>
                  运行 ID：{context.runId || '未创建'}
                </span>
                <span className="rounded-lg border px-2.5 py-1.5" style={{ borderColor: 'var(--border-subtle)' }}>
                  开始：{context.startedAt || '待启动'}
                </span>
              </div>
            </div>

            {showSetupEmptyState ? (
              <section className={classNames(styles.surface, 'rounded-xl p-6')}>
                <div className="max-w-2xl">
                  <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">品牌空间设置</p>
                  <h2 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">{setupTitle}</h2>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">{setupDescription}</p>
                  {backendNotice ? (
                    <p className="mt-3 rounded-lg border px-3 py-2 text-xs text-[var(--warning)]" style={{ borderColor: 'var(--border-subtle)' }}>
                      {backendNotice}
                    </p>
                  ) : null}
                  <div className="mt-5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={onAddBrand}
                      className="inline-flex h-10 items-center rounded-lg bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)]"
                    >
                      新建品牌
                    </button>
                    <button
                      type="button"
                      onClick={() => window.location.assign('/dashboard')}
                      className="inline-flex h-10 items-center rounded-lg border px-4 text-sm font-medium text-[var(--text-secondary)]"
                      style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                    >
                      返回品牌情报
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            {showLoadingState ? (
              <section className={classNames(styles.surface, 'rounded-xl p-6')}>
                <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">品牌空间</p>
                <h2 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">正在加载品牌空间</h2>
                <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                  系统正在读取当前品牌的图谱、画布运行、资产和报告状态。
                </p>
              </section>
            ) : null}

            {showBackendErrorState ? (
              <section className={classNames(styles.surface, 'rounded-xl p-6')}>
                <div className="max-w-2xl">
                  <p className="text-xs font-medium uppercase text-[var(--text-tertiary)]">品牌空间连接</p>
                  <h2 className="mt-2 text-xl font-semibold text-[var(--text-primary)]">当前品牌空间未连接成功</h2>
                  <p className="mt-3 text-sm leading-6 text-[var(--text-secondary)]">
                    画布运行必须先读取该品牌的图谱、节点和运行状态。当前读取失败，系统已禁用运行按钮，避免创建不可追踪的运行。
                  </p>
                  <p className="mt-3 rounded-lg border px-3 py-2 text-xs text-[var(--warning)]" style={{ borderColor: 'var(--border-subtle)' }}>
                    {spaceLoadError}
                  </p>
                  <div className="mt-5 flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => setSpaceReloadKey((value) => value + 1)}
                      className="inline-flex h-10 items-center rounded-lg bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)]"
                    >
                      重新加载品牌空间
                    </button>
                    <button
                      type="button"
                      onClick={() => window.location.assign('/dashboard')}
                      className="inline-flex h-10 items-center rounded-lg border px-4 text-sm font-medium text-[var(--text-secondary)]"
                      style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                    >
                      返回品牌情报
                    </button>
                  </div>
                </div>
              </section>
            ) : null}

            {showWorkspaceViews && activeView === 'boards' ? (
              <BoardRuntimeView
                runStatus={runStatus}
                nodes={nodes}
                platforms={platforms}
                edges={edges}
                patches={patches}
                graphUpdate={graphUpdate}
                artifacts={artifactsState}
                events={events}
                selectedNodeId={selectedNodeId}
                inspectorTab={inspectorTab}
                onSelectNode={setSelectedNodeId}
                onInspectorTabChange={setInspectorTab}
                onRunStart={handleRunStart}
                onRunPause={handleRunPause}
                onRunResume={handleRunResume}
                onRunStop={handleRunStop}
                onPatchDecision={handlePatchDecision}
                pendingPatchDecisionIds={pendingPatchDecisionIds}
              />
            ) : null}

            {showWorkspaceViews && activeView === 'graph' ? (
              <GraphHomeView
                patches={patches}
                graph={graph}
                graphUpdate={graphUpdate}
                brandName={context.brandName.replace('品牌空间', '')}
                onPatchDecision={handlePatchDecision}
                reviewItems={reviewItems}
                pendingPatchDecisionIds={pendingPatchDecisionIds}
              />
            ) : null}

            {showWorkspaceViews && activeView === 'assets' ? (
              <AssetsView
                artifacts={artifactsState}
                detail={selectedArtifactDetail}
                summary={assetSummary}
                pagination={assetPagination}
                isDetailLoading={isLoadingArtifactDetail}
                isLoadingAssets={isLoadingAssets}
                selectedArtifactId={selectedArtifactDetail?.artifact.artifactId ?? selectedArtifactDetail?.artifact.id ?? null}
                selectedType={assetTypeFilter}
                downloadingArtifactIds={downloadingArtifactIds}
                onTypeChange={handleAssetTypeChange}
                onLoadMore={handleLoadMoreAssets}
                onOpenArtifact={handleOpenArtifact}
                onDownloadArtifact={handleDownloadArtifact}
                onCloseDetail={() => setSelectedArtifactDetail(null)}
                onTraceTarget={handleTraceTarget}
                onOpenBoard={() => setActiveView('boards')}
              />
            ) : null}

            {showWorkspaceViews && activeView === 'reports' ? (
              <ReportReviewView
                report={report}
                reports={graphUpdate ? reports : []}
                graphUpdate={graphUpdate}
                guardrails={guardrails}
                onGenerateReport={() => handleGenerateReport(false)}
                onPublishReport={handlePublishReport}
                onSelectReport={handleSelectReport}
                onOpenAssets={handleOpenReportAsset}
                onOpenBoard={() => setActiveView('boards')}
                isGenerating={isGeneratingReport}
                selectedReportId={report?.id ?? null}
              />
            ) : null}
          </div>
        </main>
      </div>
    </div>
  );
}
