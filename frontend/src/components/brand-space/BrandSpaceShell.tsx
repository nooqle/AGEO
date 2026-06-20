'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bell,
  Cable,
  ChevronDown,
  CircleHelp,
  CircleUserRound,
  FileText,
  LayoutGrid,
  Pause,
  Play,
  Share2,
  Square,
  Settings,
  type LucideIcon,
} from 'lucide-react';
import { AssetsView } from './AssetsView';
import { BoardRuntimeView } from './BoardRuntimeView';
import { GraphHomeView } from './GraphHomeView';
import { ReportReviewView } from './ReportReviewView';
import styles from './BrandSpace.module.css';
import {
  artifacts,
  boardEdges,
  brandSpaceContext,
  brandSpaceNavItems,
  buildStressBoardFixture,
  evidenceRefs,
  graphEntities,
  graphRelations,
  initialBoardNodes,
  initialGraphPatches,
  initialPlatforms,
  reportGuardrails,
  runtimeEvents,
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
} from '@/types/brandSpace';

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

const workspaceItems: Array<{ label: string; icon: LucideIcon }> = [
  { label: '模板', icon: LayoutGrid },
  { label: '连接', icon: Cable },
  { label: '设置', icon: Settings },
];

const fallbackGraph: BrandSpaceGraph = {
  entities: graphEntities,
  relations: graphRelations,
  evidenceRefs,
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
      summary: '当前处于本地演示底版，资产详情使用安全摘要预览；连接后端后会显示真实 Graph Update、回答样本和报告追溯。',
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
  if (/failed to fetch|fetch failed|load failed|networkerror/i.test(error.message)) {
    return `${fallback}（后端连接不可用）`;
  }
  if (/request failed:\s*\d+/i.test(error.message)) {
    return `${fallback}（接口返回异常）`;
  }
  return error.message || fallback;
}

function shouldUseCanvasStressFixture() {
  if (typeof window === 'undefined') return false;
  const params = new URLSearchParams(window.location.search);
  return params.get('canvasFixture') === '50-nodes';
}

export function BrandSpaceShell() {
  const [activeView, setActiveView] = useState<BrandSpaceView>('boards');
  const [context, setContext] = useState(brandSpaceContext);
  const [spaceRun, setSpaceRun] = useState<BrandSpaceBoardRun | null>(null);
  const [entityId, setEntityId] = useState<string | null>(null);
  const [isBackendMode, setIsBackendMode] = useState(false);
  const [isLoadingSpace, setIsLoadingSpace] = useState(true);
  const [backendNotice, setBackendNotice] = useState('');
  const [isGeneratingReport, setIsGeneratingReport] = useState(false);
  const [runStatus, setRunStatus] = useState<BoardRunStatus>('running');
  const [nodes, setNodes] = useState<BoardNode[]>(initialBoardNodes);
  const [platforms, setPlatforms] = useState<PlatformFetchNode[]>(initialPlatforms);
  const [edges, setEdges] = useState(boardEdges);
  const [patches, setPatches] = useState<GraphPatch[]>(initialGraphPatches);
  const [reviewItems, setReviewItems] = useState<GraphReviewItem[]>(() => reviewItemsFromPatches(initialGraphPatches));
  const [artifactsState, setArtifactsState] = useState(artifacts);
  const [events, setEvents] = useState(runtimeEvents);
  const [graph, setGraph] = useState<BrandSpaceGraph>(fallbackGraph);
  const [graphUpdate, setGraphUpdate] = useState<BrandSpaceGraphUpdate | null>(null);
  const [guardrails, setGuardrails] = useState(reportGuardrails);
  const [report, setReport] = useState<BrandSpaceReport | null>(null);
  const [reports, setReports] = useState<BrandSpaceReportSummary[]>([]);
  const [selectedArtifactDetail, setSelectedArtifactDetail] = useState<ArtifactDetail | null>(null);
  const [isLoadingArtifactDetail, setIsLoadingArtifactDetail] = useState(false);
  const [isLoadingAssets, setIsLoadingAssets] = useState(false);
  const [assetTypeFilter, setAssetTypeFilter] = useState('all');
  const [assetSummary, setAssetSummary] = useState<AssetListSummary | null>(() => assetSummaryFromList(artifacts));
  const [assetPagination, setAssetPagination] = useState<PaginationInfo | null>(null);
  const [pendingPatchDecisionIds, setPendingPatchDecisionIds] = useState<string[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState('platform-rack');
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('overview');

  const selectedView = useMemo(
    () => brandSpaceNavItems.find((item) => item.id === activeView) ?? brandSpaceNavItems[0],
    [activeView],
  );

  const applySpacePayload = useCallback((payload: BrandSpacePayload) => {
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
    setEvents(payload.events);
    setGraph(payload.graph ?? fallbackGraph);
    setGraphUpdate(payload.graph_update);
    setGuardrails(payload.guardrails);
    if (payload.report !== undefined) {
      setReport(payload.report);
    }
    if (payload.reports) {
      setReports(payload.reports);
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
  }, [assetTypeFilter, isBackendMode, spaceRun?.id]);

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
      setIsLoadingSpace(true);
      try {
        if (shouldUseCanvasStressFixture()) {
          const fixture = buildStressBoardFixture(50);
          setIsBackendMode(false);
          setRunStatus('running');
          setNodes(fixture.nodes);
          setEdges(fixture.edges);
          setSelectedNodeId(fixture.nodes[0]?.id ?? 'platform-rack');
          setReviewItems(reviewItemsFromPatches(initialGraphPatches));
          setBackendNotice('50 节点压力验证底版已启用。');
          return;
        }
        const entities = await api.listEntities();
        const entity = entities.find((item) => !item.isInternalTestData) ?? entities[0];
        if (!entity) {
          throw new Error('当前账号还没有可用品牌');
        }
        let payload = await api.getBrandSpace(entity.id);
        if (!payload.run) {
          payload = await api.createBrandSpaceBoardRun(entity.id);
        }
        if (cancelled) return;
        setEntityId(entity.id);
        setIsBackendMode(true);
        setBackendNotice('');
        applySpacePayload(payload);
        setReviewItems(reviewItemsFromPatches(payload.patches, payload.graph_update));
        await refreshReviewItems(entity.id, payload.patches, payload.graph_update);
      } catch (error) {
        if (cancelled) return;
        setIsBackendMode(false);
        setReviewItems(reviewItemsFromPatches(initialGraphPatches));
        setBackendNotice(backendNoticeFromError(error, '后端不可用，正在使用本地演示底版'));
      } finally {
        if (!cancelled) {
          setIsLoadingSpace(false);
        }
      }
    }

    void loadBrandSpace();

    return () => {
      cancelled = true;
    };
  }, [applySpacePayload, refreshReviewItems]);

  useEffect(() => {
    if (!isBackendMode || !spaceRun?.id || runStatus !== 'running') return undefined;

    const intervalId = window.setInterval(() => {
      void api
        .getBrandSpaceBoardRun(spaceRun.id)
        .then(applySpacePayload)
        .catch((error) => {
          setBackendNotice(backendNoticeFromError(error, '运行态刷新失败'));
        });
    }, 2500);

    return () => window.clearInterval(intervalId);
  }, [applySpacePayload, isBackendMode, runStatus, spaceRun?.id]);

  useEffect(() => {
    if (isBackendMode) return undefined;
    if (runStatus !== 'running') return undefined;

    const intervalId = window.setInterval(() => {
      setPlatforms((current) => current.map(progressPlatform));
      setNodes((current) => current.map(progressNode));
    }, 1400);

    return () => window.clearInterval(intervalId);
  }, [isBackendMode, runStatus]);

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
      setBackendNotice(backendNoticeFromError(error, '启动画布失败，已切回本地动态'));
      startLocalRun();
    }
  };

  const handleRunPause = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      pauseLocalRun();
      return;
    }
    try {
      const payload = await api.pauseBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '暂停失败，已使用本地状态'));
      pauseLocalRun();
    }
  };

  const handleRunResume = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      resumeLocalRun();
      return;
    }
    try {
      const payload = await api.resumeBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '继续失败，已使用本地状态'));
      resumeLocalRun();
    }
  };

  const handleRunStop = async () => {
    if (!isBackendMode || !spaceRun?.id) {
      stopLocalRun();
      return;
    }
    try {
      const payload = await api.stopBrandSpaceBoardRun(spaceRun.id);
      applySpacePayload(payload);
    } catch (error) {
      setBackendNotice(backendNoticeFromError(error, '停止失败，已使用本地状态'));
      stopLocalRun();
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
        setBackendNotice(backendNoticeFromError(error, '审阅提交失败，已使用本地状态'));
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
    setSelectedArtifactDetail(buildLocalArtifactDetail(artifact));
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

  return (
    <div className={styles.root}>
      <div className={styles.shell}>
        <aside className={styles.sidebar}>
          <div className="flex h-16 items-center gap-3 border-b px-5" style={{ borderColor: 'var(--border-subtle)' }}>
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--brand-primary)] text-sm font-bold text-[var(--brand-contrast)]">
              S
            </span>
            <div>
              <p className="text-base font-semibold text-[var(--text-primary)]">specta</p>
              <p className="text-[11px] uppercase text-[var(--text-tertiary)]">品牌空间</p>
            </div>
          </div>

          <nav className="space-y-1 px-3 py-5">
            {brandSpaceNavItems.map((item) => {
              const Icon = item.icon;
              const active = activeView === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => setActiveView(item.id)}
                  className="flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left transition-colors"
                  aria-current={active ? 'page' : undefined}
                  aria-label={`打开${item.label}视图：${item.description}`}
                  style={{
                    background: active ? 'var(--brand-bg)' : 'transparent',
                    color: active ? 'var(--brand-text)' : 'var(--text-secondary)',
                  }}
                >
                  <Icon className="h-4 w-4" />
                  <span>
                    <span className="block text-sm font-semibold">{item.label}</span>
                    <span className="mt-0.5 block text-[11px] text-[var(--text-tertiary)]">{item.description}</span>
                  </span>
                </button>
              );
            })}
          </nav>

          <div className="mt-4 border-t px-3 py-5" style={{ borderColor: 'var(--border-subtle)' }}>
            <p className="mb-2 px-3 text-[11px] font-semibold uppercase text-[var(--text-tertiary)]">工作区</p>
            {workspaceItems.map(({ label, icon: Icon }) => (
              <button
                key={label}
                type="button"
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-[var(--text-secondary)] hover:bg-[var(--bg-tertiary)]"
                aria-label={`打开${label}`}
              >
                <Icon className="h-4 w-4" />
                {label}
              </button>
            ))}
          </div>
        </aside>

        <main className={styles.main}>
          <header className={classNames(styles.topbar, 'flex min-h-16 flex-wrap items-center justify-between gap-3 px-4 py-3 lg:px-6')}>
            <div className="flex min-w-0 items-center gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h1 className="truncate text-lg font-semibold text-[var(--text-primary)]">{context.brandName}</h1>
                  <ChevronDown className="h-4 w-4 text-[var(--text-tertiary)]" />
                </div>
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
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)]"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                aria-label={runStatus === 'running' ? '暂停当前画布运行' : runStatus === 'paused' ? '继续当前画布运行' : '启动当前画布运行'}
              >
                {runStatus === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {runStatus === 'running' ? '暂停' : runStatus === 'paused' ? '继续' : '运行'}
              </button>
              <button
                type="button"
                onClick={handleRunStop}
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)]"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
                aria-label="停止当前画布运行"
              >
                <Square className="h-4 w-4" />
                停止
              </button>
              <button type="button" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)]" aria-label="分享当前品牌空间">
                <Share2 className="h-4 w-4" />
                分享
              </button>
              <button type="button" className="grid h-10 w-10 place-items-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="帮助" aria-label="打开帮助">
                <CircleHelp className="h-4 w-4" />
              </button>
              <button type="button" className="grid h-10 w-10 place-items-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="通知" aria-label="查看通知">
                <Bell className="h-4 w-4" />
              </button>
              <span className="grid h-10 w-10 place-items-center rounded-full bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">
                <CircleUserRound className="h-5 w-5" />
              </span>
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
                  {isBackendMode ? (spaceRun?.is_scaffold ? '脚手架预览运行' : '真实运行态') : '底版演示运行'}
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

            {activeView === 'boards' ? (
              <BoardRuntimeView
                runStatus={runStatus}
                nodes={nodes}
                platforms={platforms}
                edges={edges}
                patches={patches}
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

            {activeView === 'graph' ? (
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

            {activeView === 'assets' ? (
              <AssetsView
                artifacts={artifactsState}
                detail={selectedArtifactDetail}
                summary={assetSummary}
                pagination={assetPagination}
                isDetailLoading={isLoadingArtifactDetail}
                isLoadingAssets={isLoadingAssets}
                selectedArtifactId={selectedArtifactDetail?.artifact.artifactId ?? selectedArtifactDetail?.artifact.id ?? null}
                selectedType={assetTypeFilter}
                onTypeChange={handleAssetTypeChange}
                onLoadMore={handleLoadMoreAssets}
                onOpenArtifact={handleOpenArtifact}
                onCloseDetail={() => setSelectedArtifactDetail(null)}
                onTraceTarget={handleTraceTarget}
              />
            ) : null}

            {activeView === 'reports' ? (
              <ReportReviewView
                report={report}
                reports={reports}
                graphUpdate={graphUpdate}
                guardrails={guardrails}
                onGenerateReport={() => handleGenerateReport(false)}
                onPublishReport={handlePublishReport}
                onSelectReport={handleSelectReport}
                onOpenAssets={handleOpenReportAsset}
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
