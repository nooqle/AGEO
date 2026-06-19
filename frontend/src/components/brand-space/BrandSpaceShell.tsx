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
              <span className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}>
                <span className={classNames('h-2 w-2 rounded-full', runStatus === 'running' && 'animate-pulse')} style={{ background: runStatus === 'running' ? 'var(--brand-primary)' : 'var(--text-tertiary)' }} />
                {runStatusLabel(runStatus)}
              </span>
              <button
                type="button"
                onClick={runStatus === 'running' ? handleRunPause : runStatus === 'paused' ? handleRunResume : handleRunStart}
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)]"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
              >
                {runStatus === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
                {runStatus === 'running' ? '暂停' : runStatus === 'paused' ? '继续' : '运行'}
              </button>
              <button
                type="button"
                onClick={handleRunStop}
                className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-primary)]"
                style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-elevated)' }}
              >
                <Square className="h-4 w-4" />
                停止
              </button>
              <button type="button" className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)]">
                <Share2 className="h-4 w-4" />
                分享
              </button>
              <button type="button" className="grid h-10 w-10 place-items-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="帮助">
                <CircleHelp className="h-4 w-4" />
              </button>
              <button type="button" className="grid h-10 w-10 place-items-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="通知">
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
                brandName={context.brandName.replace('品牌空间', '')}
                onPatchDecision={handlePatchDecision}
                reviewItems={reviewItems}
                pendingPatchDecisionIds={pendingPatchDecisionIds}
              />
            ) : null}

            {activeView === 'assets' ? <AssetsView artifacts={artifactsState} /> : null}

            {activeView === 'reports' ? (
              <ReportReviewView
                report={report}
                reports={reports}
                graphUpdate={graphUpdate}
                guardrails={guardrails}
                onGenerateReport={() => handleGenerateReport(false)}
                onPublishReport={handlePublishReport}
                onSelectReport={handleSelectReport}
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
