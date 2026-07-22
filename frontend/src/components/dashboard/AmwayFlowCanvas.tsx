'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  MiniMap,
  Panel,
  ReactFlow,
  getNodesBounds,
  type Connection,
  type Edge,
  type EdgeChange,
  type IsValidConnection,
  type NodeChange,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  Play,
  Plus,
  RotateCcw,
  Settings2,
  Workflow,
  X,
} from 'lucide-react';
import { api } from '@/services/api';
import { AmwayFlowOrchestrationPanel } from '@/components/dashboard/AmwayFlowOrchestrationPanel';
import { useTheme } from '@/hooks/useTheme';
import type { DashboardHomeData } from '@/types/dashboard';
import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import type { AnalysisTask } from '@/types/task';
import type { StageResult } from '@/types/snapshot';
import type { AmwayCirclePeriodViewResponse, AmwayQuestionHistorySet } from '@/types/amwayChina';
import type {
  OntologyAssociationCircleProjection,
  OntologyWorldSummary,
} from '@/types/ontology';
import {
  AssociationReportPanel,
  buildAssociationMapGroups,
  buildAssociationProjection,
  normalizeCenterTerms,
  sampleAnswerCount,
} from './AmwayAssociationCircleDashboardViews';
import {
  buildLiveAssociationProjection,
  mergeStageResults,
} from './AmwayAssociationCircleDashboard';
import {
  buildAmwayFlowExecutionPlan,
  mergeRuntimeOntoPlan,
  parseServerFlowPlan,
  plannedNodeIdSet,
  skippedNodeIdSet,
  type FlowExecutionPlan,
} from '@/lib/amwayFlowExecutionPlan';
import {
  ALL_PLATFORM_IDS,
  CUSTOM_NODE_META,
  DEFAULT_ANALYSIS_DIMENSIONS,
  DEFAULT_CONTENT_PROMPT_TEMPLATE,
  EDGE_DEFS,
  GUIDE_STORAGE_KEY,
  MAX_CUSTOM_NODES,
  NODE_DEFINITIONS,
  PLATFORM_META,
  STATUS_TEXT,
} from './amway-flow/constants';
import type {
  AmwayFlowNode,
  AmwayFlowNodeData,
  CustomFlowNodeType,
  FlowAnalysisDimension,
  FlowAnalysisResult,
  FlowArtifactKey,
  FlowContentResult,
  FlowNodeOutput,
  FlowNodeStatus,
  FlowTopology,
  FlowTopologyCustomNode,
  PanelState,
} from './amway-flow/types';
import {
  clearFlowTopology,
  emptyFlowTopology,
  layoutStorageKey,
  parseFlowTopology,
  platformsEnabledByTopology,
  readEnabledFlowPlatforms,
  readFlowTopology,
  readStoredPositions,
  syncPlatformStorageFromTopology,
  writeEnabledFlowPlatforms,
  writeFlowTopology,
} from './amway-flow/topologyDoc';
import { runFlowAnalysis } from './amway-flow/analysis';
import {
  buildDefaultPositions,
  nodeAcceptedInputsOf,
  nodeOutputTypeOf,
  wouldCreateCycle,
} from './amway-flow/graphUtils';
import {
  AmwayFlowNodeCard,
  flowNodeIcon,
  iconBadgeClass,
} from './amway-flow/AmwayFlowNodeCard';
import {
  AnalysisResultArtifact,
  AnswersArtifact,
  ArtifactEmpty,
  ContentDraftArtifact,
  CustomNodeDetail,
  EntitiesArtifact,
  FlowNodeDetail,
  QuestionsArtifact,
  artifactTitle,
  nodeLabel,
} from './amway-flow/AmwayFlowCanvasPanels';

/** Re-export for console start-run path (must match canvas platform switches). */
export { readEnabledFlowPlatforms } from './amway-flow/topologyDoc';

const nodeTypes = { amway: AmwayFlowNodeCard };

export function AmwayFlowCanvas({
  entityId,
  centerTerm,
  world,
  home,
  periodView,
  activeRun,
  activeTask,
  isRunActive,
  isRunSubmitting,
  isAwaitingPlanConfirm = false,
  liveStageResults = [],
  onQuickRun,
  onConfirmFlowPlan,
  onRefreshFlowPlan,
  onCancelFlowPlan,
  onOpenRunSettings,
  onOpenCircle,
}: {
  entityId: string;
  centerTerm: string;
  world?: OntologyWorldSummary | null;
  home?: DashboardHomeData | null;
  periodView?: AmwayCirclePeriodViewResponse | null;
  activeRun?: BrandIntelligenceRun | null;
  activeTask?: AnalysisTask | null;
  isRunActive?: boolean;
  isRunSubmitting?: boolean;
  /** M3: parked at plan confirmation gate */
  isAwaitingPlanConfirm?: boolean;
  liveStageResults?: StageResult[];
  onQuickRun: () => void;
  onConfirmFlowPlan?: () => void;
  onRefreshFlowPlan?: () => void;
  onCancelFlowPlan?: () => void;
  onOpenRunSettings: () => void;
  onOpenCircle: () => void;
}) {
  const canvasKey = `${entityId}:${centerTerm}`;
  const { theme } = useTheme();
  const [positions, setPositions] = useState<Record<string, { x: number; y: number }>>(() => ({
    ...buildDefaultPositions(),
    ...readStoredPositions(entityId, centerTerm),
  }));
  // 节点测量尺寸回流：受控模式下 nodes 数组每次重建都会丢失 internal measured，
  // 必须随 userNode 回传，否则运行状态翻转等高频更新时节点可能停留在 visibility:hidden。
  const [measuredSizes, setMeasuredSizes] = useState<Record<string, { width: number; height: number }>>({});
  const [panel, setPanel] = useState<PanelState>(null);
  // Phase 3a 自定义拓扑（视图层编排）。3b-1.4 起后端为权威存储，
  // localStorage 降级为首帧缓存与离线回退。
  const [topology, setTopology] = useState<FlowTopology>(() => readFlowTopology(entityId));
  // Wave B3: platform enablement follows topology e-fetch-* edges (authority)
  const [enabledPlatforms, setEnabledPlatforms] = useState<string[]>(() => {
    const localTopo = readFlowTopology(entityId);
    return platformsEnabledByTopology(localTopo);
  });
  // 不变式：传给 updateTopology 的 updater 必须是纯函数——React StrictMode（dev）
  // 会双跑 updater 检测纯度，含 Math.random/副作用会产生 state 与后端各存一份的分叉。
  // id 生成等不纯逻辑在调用处完成；持久化副作用统一收敛到下方 useEffect。
  const topologyDirtyRef = useRef(false);
  const topologyVersionRef = useRef<number | null>(null);
  const [topologySaveError, setTopologySaveError] = useState<string | null>(null);
  const updateTopology = useCallback(
    (updater: (current: FlowTopology) => FlowTopology) => {
      topologyDirtyRef.current = true;
      setTopology(updater);
    },
    [],
  );

  // 拓扑变化后统一持久化：localStorage 缓存 + 后端权威存储。
  // P1-7: PUT 失败必须提示用户，禁止静默丢编辑。
  useEffect(() => {
    if (!topologyDirtyRef.current) return;
    topologyDirtyRef.current = false;
    writeFlowTopology(entityId, topology);
    void api
      .putAmwayFlowTopology(entityId, topology, topologyVersionRef.current)
      .then((resp) => {
        if (typeof resp?.version === 'number') {
          topologyVersionRef.current = resp.version;
        }
        setTopologySaveError(null);
      })
      .catch((error: unknown) => {
        const message = error instanceof Error ? error.message : '拓扑保存失败';
        setTopologySaveError(
          message.includes('版本冲突')
            ? '拓扑已被其他操作更新，请刷新页面后再改，以免覆盖他人/运行结果。'
            : `拓扑未能同步到服务器：${message}。本地仍保留本次编辑。`,
        );
      });
  }, [entityId, topology]);

  // 挂载后从后端拉取权威拓扑；与本地有差异时以后端为准并回写缓存
  useEffect(() => {
    let cancelled = false;
    void api.getAmwayFlowTopology(entityId)
      .then((resp) => {
        if (cancelled) return;
        const remote = parseFlowTopology(resp?.topology);
        if (typeof (resp as { version?: number })?.version === 'number') {
          topologyVersionRef.current = Number((resp as { version?: number }).version);
        }
        setTopology((current) =>
          JSON.stringify(current) === JSON.stringify(remote) ? current : remote,
        );
        writeFlowTopology(entityId, remote);
        setEnabledPlatforms(syncPlatformStorageFromTopology(entityId, remote));
        setTopologySaveError(null);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  // Keep localStorage platform switches aligned with topology gates (B3)
  useEffect(() => {
    setEnabledPlatforms(syncPlatformStorageFromTopology(entityId, topology));
  }, [entityId, topology.removedEdgeIds]);
  const [hoveredEdgeId, setHoveredEdgeId] = useState<string | null>(null);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const [questionSets, setQuestionSets] = useState<AmwayQuestionHistorySet[]>([]);
  const [showGuide, setShowGuide] = useState(() => {
    if (typeof window === 'undefined') return false;
    try {
      return !window.localStorage.getItem(GUIDE_STORAGE_KEY);
    } catch {
      return false;
    }
  });
  const flowInstanceRef = useRef<ReactFlowInstance<AmwayFlowNode, Edge> | null>(null);

  useEffect(() => {
    let cancelled = false;
    void api.listAmwayQuestionHistory(entityId, 80)
      .then((history) => {
        if (!cancelled) setQuestionSets(history.question_sets || []);
      })
      .catch(() => {
        if (!cancelled) setQuestionSets([]);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId]);

  const dismissGuide = useCallback(() => {
    setShowGuide(false);
    try {
      window.localStorage.setItem(GUIDE_STORAGE_KEY, '1');
    } catch {
      // 忽略
    }
  }, []);

  // 抽屉打开时画布视口平滑偏移，避免右侧节点被遮挡
  useEffect(() => {
    const instance = flowInstanceRef.current;
    if (!instance) return;
    const bounds = getNodesBounds(instance.getNodes());
    const zoom = instance.getZoom();
    const offsetX = panel ? 280 / zoom : 0;
    void instance.setCenter(
      bounds.x + bounds.width / 2 + offsetX,
      bounds.y + bounds.height / 2,
      { zoom, duration: 280 },
    );
  }, [panel]);

  const centerTerms = useMemo(() => normalizeCenterTerms([centerTerm]), [centerTerm]);
  const combinedLiveStageResults = useMemo(
    () => mergeStageResults(activeTask?.stage_results_cache || [], liveStageResults),
    [activeTask?.stage_results_cache, liveStageResults],
  );
  const liveProjection = useMemo(
    () => buildLiveAssociationProjection(combinedLiveStageResults, centerTerm, centerTerms),
    [centerTerm, centerTerms, combinedLiveStageResults],
  );
  const baseProjection = useMemo(() => buildAssociationProjection(world, home), [home, world]);
  const projection: OntologyAssociationCircleProjection = isRunActive
    ? liveProjection
    : periodView?.projection || baseProjection;
  const projectionNodes = useMemo(() => projection.nodes || [], [projection.nodes]);
  const mapGroups = useMemo(() => buildAssociationMapGroups(projectionNodes), [projectionNodes]);
  const sampleScope = projection.sample_scope || {};
  const answerCount = sampleAnswerCount(sampleScope);
  const evidenceSamples = useMemo(() => projection.evidence_samples || [], [projection.evidence_samples]);
  const sourceAppendix = useMemo(() => projection.source_appendix || [], [projection.source_appendix]);
  const questionBank = projection.question_bank || [];
  const hasReport = Boolean(
    (projection.report_narrative_sections || []).length
      || String((projection as unknown as Record<string, unknown>).report_markdown || '').trim()
      || String((projection as unknown as Record<string, unknown>).full_markdown || '').trim(),
  );

  const stageCode = String(activeTask?.current_stage || activeRun?.stage || '').trim().toUpperCase();
  const errorStage = String(activeTask?.error_stage || '').trim().toUpperCase();
  const runFailed = Boolean(
    activeRun && ['failed', 'error'].includes(String(activeRun.status || '').toLowerCase()),
  );
  const liveSignalCount = combinedLiveStageResults.filter(
    (item) => String(item.result_type || item.resultType) === 'entity_extraction_signal',
  ).length;

  const platformAnswerCounts = useMemo(() => {
    const counts = new Map<string, number>();
    const add = (platform: unknown) => {
      const key = String(platform || '').trim().toLowerCase();
      if (!key) return;
      counts.set(key, (counts.get(key) || 0) + 1);
    };
    combinedLiveStageResults.forEach((item) => add((item.data || {}).platform));
    if (!counts.size) {
      evidenceSamples.forEach((item) => add(item.platform));
    }
    if (!counts.size) {
      sourceAppendix.forEach((item) => add(item.platform));
    }
    return counts;
  }, [combinedLiveStageResults, evidenceSamples, sourceAppendix]);

  const running = Boolean(isRunActive || isRunSubmitting);
  const progressMessage = String(activeTask?.progress_message || activeRun?.message || '').trim();

  // M1: local topology preview + authoritative run.flow_plan when a task is active
  const executionPlan = useMemo<FlowExecutionPlan>(() => {
    const local = buildAmwayFlowExecutionPlan({
      topology,
      enabledPlatforms,
      allPlatformIds: ALL_PLATFORM_IDS,
      stageCode,
      isRunning: running,
      runFailed,
      hasProjectionData: projectionNodes.length > 0,
      hasReportData: hasReport,
      answerCount,
    });
    const serverRaw = (activeRun?.input_scope || {}) as Record<string, unknown>;
    const serverPlan = parseServerFlowPlan(serverRaw.flow_plan);
    // Prefer run snapshot whenever the run is active/submitting/recently completed
    // so the canvas shows the plan that was committed at task start (not live edits).
    if (serverPlan && (running || isRunActive || Boolean(activeRun))) {
      return mergeRuntimeOntoPlan(serverPlan, local);
    }
    return local;
  }, [
    activeRun,
    answerCount,
    enabledPlatforms,
    hasReport,
    isRunActive,
    projectionNodes.length,
    runFailed,
    running,
    stageCode,
    topology,
  ]);
  const planPlannedNodes = useMemo(() => plannedNodeIdSet(executionPlan), [executionPlan]);
  const planSkippedNodes = useMemo(() => skippedNodeIdSet(executionPlan), [executionPlan]);
  const planActiveEdgeIds = useMemo(
    () => new Set(executionPlan.activeEdgeIds),
    [executionPlan.activeEdgeIds],
  );

  const nodeStatusMap = useMemo(() => {
    const hasData = projectionNodes.length > 0 || answerCount > 0;
    const fetching = running && stageCode.startsWith('A4');
    const analyzing = running && (stageCode.startsWith('A5') || stageCode.includes('SECONDARY') || stageCode.includes('CONTENT'));
    const status = new Map<string, FlowNodeStatus>();
    const failNodeId = (() => {
      if (!runFailed) return null;
      const code = errorStage || stageCode;
      if (code.startsWith('A5')) return 'extract';
      if (code.startsWith('A4')) return 'fetch';
      return 'fetch';
    })();

    // Prefer plan step status when available (skipped / active / done / pending→idle)
    executionPlan.steps.forEach((step) => {
      if (step.status === 'skipped') status.set(step.nodeId, 'skipped');
      else if (step.status === 'active') status.set(step.nodeId, 'active');
      else if (step.status === 'done') status.set(step.nodeId, 'done');
    });

    const setIfAbsent = (id: string, value: FlowNodeStatus) => {
      if (!status.has(id)) status.set(id, value);
    };

    setIfAbsent('question-set', running || hasData ? 'done' : 'idle');
    setIfAbsent('lexicon', running || hasData ? 'done' : 'idle');
    setIfAbsent(
      'fetch',
      failNodeId === 'fetch' ? 'failed' : fetching ? 'active' : answerCount > 0 || liveSignalCount > 0 || hasData ? 'done' : 'idle',
    );
    PLATFORM_META.forEach((platform) => {
      const nodeId = `platform-${platform.id}`;
      if (status.get(nodeId) === 'skipped') return;
      const count = platformAnswerCounts.get(platform.id) || 0;
      setIfAbsent(
        nodeId,
        count > 0 ? 'done' : fetching && planPlannedNodes.has(nodeId) ? 'active' : 'idle',
      );
    });
    setIfAbsent(
      'extract',
      failNodeId === 'extract' ? 'failed' : projectionNodes.length > 0 ? 'done' : running && liveSignalCount > 0 ? 'active' : 'idle',
    );
    setIfAbsent(
      'projection',
      projectionNodes.length > 0 && !running ? 'done' : analyzing || (running && projectionNodes.length > 0) ? 'active' : 'idle',
    );
    setIfAbsent('report', hasReport && !running ? 'done' : analyzing ? 'active' : 'idle');

    // custom nodes: plan-aware
    topology.customNodes.forEach((customNode) => {
      if (status.has(customNode.id)) return;
      const hasResult = Boolean(customNode.config.result);
      if (planSkippedNodes.has(customNode.id)) status.set(customNode.id, 'skipped');
      else if (hasResult) status.set(customNode.id, 'done');
      else status.set(customNode.id, 'idle');
    });

    return status;
  }, [
    answerCount,
    errorStage,
    executionPlan.steps,
    hasReport,
    liveSignalCount,
    planPlannedNodes,
    planSkippedNodes,
    platformAnswerCounts,
    projectionNodes.length,
    runFailed,
    running,
    stageCode,
    topology.customNodes,
  ]);

  const togglePlatform = useCallback(
    (nodeId: string) => {
      if (running || isAwaitingPlanConfirm) return;
      const platformId = nodeId.replace(/^platform-/, '');
      const edgeId = `e-fetch-${platformId}`;
      // Wave B3: toggle = connect/disconnect platform edge on topology
      updateTopology((current) => {
        const removed = new Set(current.removedEdgeIds);
        if (removed.has(edgeId)) removed.delete(edgeId);
        else removed.add(edgeId);
        const enabled = ALL_PLATFORM_IDS.filter((id) => !removed.has(`e-fetch-${id}`));
        if (!enabled.length) return current;
        return { ...current, removedEdgeIds: Array.from(removed) };
      });
    },
    [isAwaitingPlanConfirm, running, updateTopology],
  );

  const nodeSubtitleMap = useMemo(() => {
    const fetching = running && stageCode.startsWith('A4');
    const analyzing = running && stageCode.startsWith('A5');
    // F2: prefer locked/planned platform count over local switches (4/4 trap)
    const plannedPlatformCount = executionPlan.steps.filter(
      (step) => step.kind === 'platform' && step.status !== 'skipped',
    ).length;
    const platformDenom = ALL_PLATFORM_IDS.length;
    const platformSubtitle =
      plannedPlatformCount > 0 || executionPlan.steps.some((s) => s.kind === 'platform')
        ? `${plannedPlatformCount}/${platformDenom} 个平台`
        : `${enabledPlatforms.length}/${platformDenom} 个平台`;
    const subtitles = new Map<string, string>();
    subtitles.set('question-set', questionBank.length ? `${questionBank.length} 题` : '系统默认问题集');
    subtitles.set('lexicon', '品牌实体识别范围');
    subtitles.set(
      'fetch',
      fetching
        ? progressMessage || '正在采集'
        : answerCount
          ? `${answerCount} 条回答`
          : platformSubtitle,
    );
    subtitles.set(
      'extract',
      analyzing && liveSignalCount > 0
        ? `已识别 ${liveSignalCount} 个实体信号`
        : projectionNodes.length
          ? `${projectionNodes.length} 个节点`
          : '识别品牌相关实体',
    );
    subtitles.set('projection', '圈层距离排布');
    subtitles.set('report', hasReport ? '已生成' : '解读报告');
    return subtitles;
  }, [
    answerCount,
    enabledPlatforms.length,
    executionPlan.steps,
    hasReport,
    liveSignalCount,
    progressMessage,
    projectionNodes.length,
    questionBank.length,
    running,
    stageCode,
  ]);

  const nodeOutputsMap = useMemo(() => {
    const outputs = new Map<string, FlowNodeOutput[]>();
    outputs.set('question-set', [
      { key: 'questions', label: '问题列表', count: questionBank.length || null, disabled: !questionBank.length },
    ]);
    outputs.set('lexicon', [{ key: 'lexicon', label: '词库说明' }]);
    outputs.set('fetch', [
      { key: 'answers', label: '答案原文', count: answerCount || null, disabled: !answerCount },
    ]);
    outputs.set('extract', [
      { key: 'entities', label: '抽取实体', count: projectionNodes.length || null, disabled: !projectionNodes.length },
    ]);
    outputs.set('projection', [
      { key: 'circle', label: '圈层图', disabled: !projectionNodes.length },
    ]);
    outputs.set('report', [{ key: 'report', label: '报告原文', disabled: !hasReport }]);
    return outputs;
  }, [answerCount, hasReport, projectionNodes.length, questionBank.length]);

  const handleOutput = useCallback(
    (nodeId: string, key: FlowArtifactKey) => {
      if (key === 'circle') {
        onOpenCircle();
        return;
      }
      setPanel({ kind: 'artifact', nodeId, artifact: key });
    },
    [onOpenCircle],
  );

  const nodes = useMemo<AmwayFlowNode[]>(() => {
    const list: AmwayFlowNode[] = NODE_DEFINITIONS.map((definition) => ({
      id: definition.id,
      type: 'amway',
      position: positions[definition.id] || definition.position,
      measured: measuredSizes[definition.id],
      selected: panel?.kind === 'node' && panel.nodeId === definition.id,
      deletable: false,
      data: {
        label: definition.label,
        subtitle: nodeSubtitleMap.get(definition.id) || '',
        icon: definition.icon,
        status: nodeStatusMap.get(definition.id) || 'idle',
        variant: definition.variant,
        outputs: nodeOutputsMap.get(definition.id) || [],
        description: definition.description,
        planned: planPlannedNodes.has(definition.id),
        onOutput: handleOutput,
      },
    }));
    PLATFORM_META.forEach((platform) => {
      const nodeId = `platform-${platform.id}`;
      list.push({
        id: nodeId,
        type: 'amway',
        position: positions[nodeId] || { x: 660, y: 0 },
        measured: measuredSizes[nodeId],
        selected: panel?.kind === 'node' && panel.nodeId === nodeId,
        deletable: false,
        data: {
          label: platform.label,
          subtitle: '',
          icon: 'workflow',
          status: nodeStatusMap.get(nodeId) || 'idle',
          variant: 'platform',
          outputs: [],
          description: `${platform.label} 采集通道。关闭后下一轮运行不再采集该平台。`,
          enabled: enabledPlatforms.includes(platform.id),
          planned: planPlannedNodes.has(nodeId),
          onOutput: handleOutput,
          onToggle: togglePlatform,
        },
      });
    });
    // 自定义节点（数据分析/内容创作）
    topology.customNodes.forEach((customNode) => {
      const meta = CUSTOM_NODE_META[customNode.type];
      const hasResult = Boolean(customNode.config.result);
      const planStatus = nodeStatusMap.get(customNode.id);
      list.push({
        id: customNode.id,
        type: 'amway',
        position: positions[customNode.id] || customNode.position,
        measured: measuredSizes[customNode.id],
        selected: panel?.kind === 'node' && panel.nodeId === customNode.id,
        data: {
          label: String(customNode.config.label || meta.label),
          subtitle: planStatus === 'skipped'
            ? '计划跳过'
            : hasResult
              ? (customNode.type === 'content' ? '已生成草稿' : '已生成结论')
              : planPlannedNodes.has(customNode.id)
                ? '计划执行'
                : '待连线',
          icon: meta.icon,
          status: planStatus || (hasResult ? 'done' : 'idle'),
          variant: customNode.type,
          outputs: customNode.type === 'analysis'
            ? [{ key: 'analysisResult' as FlowArtifactKey, label: '分析结论', disabled: !hasResult }]
            : [{ key: 'contentDraft' as FlowArtifactKey, label: '内容草稿', disabled: !hasResult }],
          description: meta.description,
          planned: planPlannedNodes.has(customNode.id),
          onOutput: handleOutput,
        },
      });
    });
    return list;
  }, [enabledPlatforms, handleOutput, measuredSizes, nodeOutputsMap, nodeStatusMap, nodeSubtitleMap, panel, planPlannedNodes, positions, togglePlatform, topology.customNodes]);

  const onNodesChange = useCallback((changes: NodeChange<AmwayFlowNode>[]) => {
    setPositions((current) => {
      let next = current;
      changes.forEach((change) => {
        if (change.type === 'position' && change.position) {
          if (next === current) next = { ...current };
          next[change.id] = change.position;
        }
      });
      return next;
    });
    setMeasuredSizes((current) => {
      let next = current;
      changes.forEach((change) => {
        if (change.type === 'dimensions' && change.dimensions) {
          const prev = current[change.id];
          const dims = { width: change.dimensions.width, height: change.dimensions.height };
          if (!prev || prev.width !== dims.width || prev.height !== dims.height) {
            if (next === current) next = { ...current };
            next[change.id] = dims;
          }
        }
      });
      return next;
    });
    // 自定义节点删除：内置骨架/平台节点 deletable=false 不会走到这里；
    // 删除时同步清理与其相连的自定义连线，避免悬挂连线。
    const removedCustomIds = changes
      .filter((change) => change.type === 'remove')
      .map((change) => change.id);
    if (removedCustomIds.length) {
      setPanel((current) => (current && removedCustomIds.includes(current.nodeId) ? null : current));
      updateTopology((current) => ({
        ...current,
        customNodes: current.customNodes.filter((node) => !removedCustomIds.includes(node.id)),
        customEdges: current.customEdges.filter(
          (edge) => !removedCustomIds.includes(edge.source) && !removedCustomIds.includes(edge.target),
        ),
      }));
    }
  }, [updateTopology]);

  const persistPositions = useCallback(() => {
    if (typeof window === 'undefined') return;
    try {
      window.localStorage.setItem(layoutStorageKey(entityId, centerTerm), JSON.stringify(positions));
    } catch {
      // 忽略持久化失败
    }
  }, [centerTerm, entityId, positions]);

  const resetLayout = useCallback(() => {
    if (typeof window !== 'undefined') {
      try {
        window.localStorage.removeItem(layoutStorageKey(entityId, centerTerm));
      } catch {
        // 忽略
      }
    }
    // 重置布局同时恢复默认拓扑（自定义节点/连线/断开全部还原）
    // 经 updateTopology 走，后端权威存储一并清空
    clearFlowTopology(entityId);
    updateTopology(() => emptyFlowTopology());
    setPanel(null);
    setPositions(buildDefaultPositions());
  }, [centerTerm, entityId, updateTopology]);

  // 拓扑合并：内置连线（剔除用户断开的）+ 自定义连线
  const mergedEdgeDefs = useMemo(() => {
    const builtin = EDGE_DEFS
      .filter((definition) => !topology.removedEdgeIds.includes(definition.id))
      .map((definition) => ({ ...definition, custom: false }));
    const custom = topology.customEdges.map((definition) => ({ ...definition, custom: true }));
    return [...builtin, ...custom];
  }, [topology]);

  // 节点库拖入/点击创建自定义节点（上限 MAX_CUSTOM_NODES）
  const addCustomNode = useCallback(
    (type: CustomFlowNodeType, position: { x: number; y: number }) => {
      // id 在事件处理器里生成一次——updater 内放 Math.random 会在 StrictMode
      // 双跑时产生两个 id，导致画布 state 与后端各存一份
      const id = `custom-${type}-${Math.random().toString(36).slice(2, 10)}`;
      updateTopology((current) => {
        if (current.customNodes.length >= MAX_CUSTOM_NODES) return current;
        return {
          ...current,
          customNodes: [...current.customNodes, { id, type, position, config: {} }],
        };
      });
    },
    [updateTopology],
  );

  const addCustomNodeAtViewportCenter = useCallback(
    (type: CustomFlowNodeType) => {
      const instance = flowInstanceRef.current;
      if (!instance) {
        addCustomNode(type, { x: 660, y: 470 });
        return;
      }
      addCustomNode(
        type,
        instance.screenToFlowPosition({ x: window.innerWidth / 2, y: window.innerHeight / 2 }),
      );
    },
    [addCustomNode],
  );

  const updateCustomNodeConfig = useCallback(
    (nodeId: string, patch: Record<string, unknown>) => {
      updateTopology((current) => ({
        ...current,
        customNodes: current.customNodes.map((node) =>
          node.id === nodeId ? { ...node, config: { ...node.config, ...patch } } : node,
        ),
      }));
    },
    [updateTopology],
  );

  const deleteCustomNode = useCallback(
    (nodeId: string) => {
      setPanel(null);
      updateTopology((current) => ({
        ...current,
        customNodes: current.customNodes.filter((node) => node.id !== nodeId),
        customEdges: current.customEdges.filter((edge) => edge.source !== nodeId && edge.target !== nodeId),
      }));
    },
    [updateTopology],
  );

  const [runningCustomNodeId, setRunningCustomNodeId] = useState<string | null>(null);
  // Sync lock: setState 异步，连点时 runningCustomNodeId 仍可能为 null（P1-3 前端半边）
  const customRunLockRef = useRef<string | null>(null);
  const [customNodeError, setCustomNodeError] = useState<string | null>(null);

  const refreshTopologyVersion = useCallback(async () => {
    try {
      const latest = await api.getAmwayFlowTopology(entityId);
      if (typeof latest?.version === 'number') {
        topologyVersionRef.current = latest.version;
      }
    } catch {
      // best-effort; next PUT may 409 and surface via topologySaveError
    }
  }, [entityId]);

  // 3b-1.5 / 3b-1.6: analysis/content 真执行；cascade 跑下游分支。
  // P1-3 前端半边：全局互斥 + PUT 带 expected_version；成功后不 dirty 回写（服务端已落库）。
  const runCustomNode = useCallback(
    async (nodeId: string, options?: { cascade?: boolean }) => {
      if (customRunLockRef.current) return;
      const customNode = topology.customNodes.find((node) => node.id === nodeId);
      if (!customNode || (customNode.type !== 'analysis' && customNode.type !== 'content')) return;
      customRunLockRef.current = nodeId;
      setCustomNodeError(null);
      setRunningCustomNodeId(nodeId);
      try {
        const putResp = await api.putAmwayFlowTopology(
          entityId,
          topology,
          topologyVersionRef.current,
        );
        if (typeof putResp?.version === 'number') {
          topologyVersionRef.current = putResp.version;
        }
        const body =
          customNode.type === 'analysis'
            ? {
                dimensions: (Array.isArray(customNode.config.dimensions)
                  ? (customNode.config.dimensions as string[]).filter((item): item is FlowAnalysisDimension =>
                      item === 'platform' || item === 'entities' || item === 'risk')
                  : DEFAULT_ANALYSIS_DIMENSIONS),
                prompt: String(customNode.config.prompt || ''),
                cascade: Boolean(options?.cascade),
              }
            : {
                promptTemplate: String(
                  customNode.config.promptTemplate || DEFAULT_CONTENT_PROMPT_TEMPLATE,
                ),
              };
        const resp = await api.runAmwayFlowNode(entityId, nodeId, body);
        const remote = parseFlowTopology(resp.topology);
        // Server already persisted results; avoid dirty→PUT race with bumped row.version
        topologyDirtyRef.current = false;
        setTopology(remote);
        writeFlowTopology(entityId, remote);
        await refreshTopologyVersion();
      } catch (error) {
        if (customNode.type === 'analysis' && projectionNodes.length > 0 && !options?.cascade) {
          const dimensions = (Array.isArray(customNode.config.dimensions)
            ? (customNode.config.dimensions as string[]).filter((item): item is FlowAnalysisDimension =>
                item === 'platform' || item === 'entities' || item === 'risk')
            : DEFAULT_ANALYSIS_DIMENSIONS);
          const result = runFlowAnalysis(
            dimensions.length ? dimensions : DEFAULT_ANALYSIS_DIMENSIONS,
            projection,
          );
          updateCustomNodeConfig(nodeId, {
            result: { ...result, mode: 'deterministic', fallback_reason: 'api_unavailable' },
            dimensions: result.dimensions,
          });
          setCustomNodeError('后端运行失败，已使用本地确定性分析。');
        } else {
          const message = error instanceof Error ? error.message : '节点运行失败';
          setCustomNodeError(
            message.includes('版本冲突')
              ? '拓扑版本冲突：请刷新页面后重试，以免覆盖其他运行结果。'
              : message,
          );
        }
      } finally {
        customRunLockRef.current = null;
        setRunningCustomNodeId(null);
      }
    },
    [
      entityId,
      projection,
      projectionNodes.length,
      refreshTopologyVersion,
      topology,
      updateCustomNodeConfig,
    ],
  );

  const runBranchFrom = useCallback(
    async (fromNodeId: string, mode: 'node_only' | 'downstream' = 'downstream') => {
      if (customRunLockRef.current) return;
      customRunLockRef.current = fromNodeId;
      setCustomNodeError(null);
      setRunningCustomNodeId(fromNodeId);
      try {
        const putResp = await api.putAmwayFlowTopology(
          entityId,
          topology,
          topologyVersionRef.current,
        );
        if (typeof putResp?.version === 'number') {
          topologyVersionRef.current = putResp.version;
        }
        const resp = await api.runAmwayFlowBranch(entityId, {
          from_node_id: fromNodeId,
          mode,
        });
        const remote = parseFlowTopology(resp.topology);
        topologyDirtyRef.current = false;
        setTopology(remote);
        writeFlowTopology(entityId, remote);
        await refreshTopologyVersion();
      } catch (error) {
        const message = error instanceof Error ? error.message : '分支运行失败';
        setCustomNodeError(
          message.includes('版本冲突')
            ? '拓扑版本冲突：请刷新页面后重试，以免覆盖其他运行结果。'
            : message,
        );
      } finally {
        customRunLockRef.current = null;
        setRunningCustomNodeId(null);
      }
    },
    [entityId, refreshTopologyVersion, topology],
  );

  const runAnalysis = useCallback(
    (nodeId: string) => {
      void runCustomNode(nodeId);
    },
    [runCustomNode],
  );

  const runAnalysisBranch = useCallback(
    (nodeId: string) => {
      void runCustomNode(nodeId, { cascade: true });
    },
    [runCustomNode],
  );

  const runContent = useCallback(
    (nodeId: string) => {
      void runCustomNode(nodeId);
    },
    [runCustomNode],
  );

  const edges = useMemo<Edge[]>(() => {
    return mergedEdgeDefs.map((definition) => {
      const sourceStatus = nodeStatusMap.get(definition.source) || 'idle';
      const targetStatus = nodeStatusMap.get(definition.target) || 'idle';
      const flowing = sourceStatus === 'active' || (sourceStatus === 'done' && targetStatus === 'active');
      const isPlatformEdge = definition.target.startsWith('platform-');
      const platformDisabled = isPlatformEdge
        && !enabledPlatforms.includes(definition.target.replace(/^platform-/, ''));
      const onPlanPath = planActiveEdgeIds.has(definition.id);
      const highlighted = hoveredEdgeId === definition.id
        || (hoveredNodeId != null && (definition.source === hoveredNodeId || definition.target === hoveredNodeId));
      const emphasized = (flowing && !platformDisabled) || highlighted || (onPlanPath && !platformDisabled && !running);
      return {
        id: definition.id,
        source: definition.source,
        target: definition.target,
        animated: flowing && !platformDisabled,
        selected: selectedEdgeIds.includes(definition.id),
        style: {
          stroke: emphasized ? 'var(--brand-primary)' : 'var(--border-strong)',
          strokeWidth: emphasized ? 2.5 : isPlatformEdge ? 1 : 1.5,
          strokeDasharray: isPlatformEdge ? '4 4' : onPlanPath && !running ? '6 3' : undefined,
          opacity: platformDisabled
            ? 0.18
            : onPlanPath
              ? 1
              : isPlatformEdge && !emphasized
                ? 0.55
                : planActiveEdgeIds.size && !onPlanPath
                  ? 0.35
                  : 1,
          transition: 'stroke 0.15s, stroke-width 0.15s, opacity 0.15s',
        },
      };
    });
  }, [
    enabledPlatforms,
    hoveredEdgeId,
    hoveredNodeId,
    mergedEdgeDefs,
    nodeStatusMap,
    planActiveEdgeIds,
    running,
    selectedEdgeIds,
  ]);

  // 连线改接校验：类型匹配 + 平台通道不可改接（用开关管理）+ DAG 无环
  const isValidConnection = useCallback<IsValidConnection<Edge>>(
    (connection) => {
      const { source, target } = connection;
      if (!source || !target || source === target) return false;
      if (source.startsWith('platform-') || target.startsWith('platform-')) return false;
      const outputType = nodeOutputTypeOf(topology, source);
      if (!outputType) return false;
      if (!nodeAcceptedInputsOf(topology, target).includes(outputType)) return false;
      return !wouldCreateCycle(mergedEdgeDefs, source, target);
    },
    [mergedEdgeDefs, topology],
  );

  // 新连线落地：输入端口单连接（新连线替换旧连线）；若恰好恢复某条内置连线则取消断开标记
  const onConnect = useCallback(
    (connection: Connection) => {
      const { source, target } = connection;
      if (!source || !target) return;
      updateTopology((current) => {
        const activeBuiltin = EDGE_DEFS.filter(
          (definition) => definition.target === target && !current.removedEdgeIds.includes(definition.id),
        );
        const removedEdgeIds = new Set(current.removedEdgeIds);
        activeBuiltin.forEach((definition) => {
          if (definition.source !== source) removedEdgeIds.add(definition.id);
        });
        const restored = EDGE_DEFS.find(
          (definition) => definition.source === source && definition.target === target,
        );
        if (restored) removedEdgeIds.delete(restored.id);
        const customEdges = current.customEdges.filter((edge) => edge.target !== target);
        if (!restored) {
          customEdges.push({ id: `e-custom-${source}-to-${target}`, source, target });
        }
        return { ...current, removedEdgeIds: Array.from(removedEdgeIds), customEdges };
      });
    },
    [updateTopology],
  );

  // 连线删除：内置连线进 removedEdgeIds（骨架断开二次确认），自定义连线直接移除
  const onEdgesChange = useCallback(
    (changes: EdgeChange<Edge>[]) => {
      const selectChanges = changes.filter((change) => change.type === 'select');
      if (selectChanges.length) {
        setSelectedEdgeIds((current) => {
          let next = current;
          selectChanges.forEach((change) => {
            if (change.type !== 'select') return;
            const has = next.includes(change.id);
            if (change.selected && !has) {
              if (next === current) next = [...current];
              next.push(change.id);
            } else if (!change.selected && has) {
              if (next === current) next = current.filter((id) => id !== change.id);
              else next = next.filter((id) => id !== change.id);
            }
          });
          return next;
        });
      }
      const removedBuiltin: string[] = [];
      const removedCustom: string[] = [];
      changes.forEach((change) => {
        if (change.type !== 'remove') return;
        if (EDGE_DEFS.some((definition) => definition.id === change.id)) removedBuiltin.push(change.id);
        else removedCustom.push(change.id);
      });
      if (!removedBuiltin.length && !removedCustom.length) return;
      if (removedBuiltin.length) {
        const confirmed = window.confirm('断开后该节点不再接收数据，确定断开内置连线吗？');
        if (!confirmed) return;
      }
      setSelectedEdgeIds((current) => current.filter((id) => !removedBuiltin.includes(id) && !removedCustom.includes(id)));
      updateTopology((current) => ({
        ...current,
        removedEdgeIds: [...new Set([...current.removedEdgeIds, ...removedBuiltin])],
        customEdges: current.customEdges.filter((edge) => !removedCustom.includes(edge.id)),
      }));
    },
    [updateTopology],
  );

  const selectedNode = panel?.kind === 'node' ? nodes.find((node) => node.id === panel.nodeId) || null : null;

  return (
    <div className="flex h-full min-h-[calc(100vh-64px)] flex-col">
      <div className="px-5 pt-4 lg:px-7 2xl:px-10">
        <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-5 py-4 shadow-sm">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--brand-primary)]">
                <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--brand-primary)]" />
                {centerTerm} 生产线
              </div>
              <div className="mt-1 flex flex-wrap items-baseline gap-x-4 gap-y-1">
                <h1 className="text-2xl font-semibold leading-tight tracking-tight">品牌生产线</h1>
                <p className="text-sm text-[var(--text-secondary)]">从问题到图谱的完整过程，节点可自由拖拽</p>
              </div>
              {topology.customNodes.length > 0 || topology.customEdges.length > 0 || topology.removedEdgeIds.length > 0 ? (
                <p className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2.5 py-1 text-xs text-[var(--text-tertiary)]">
                  <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-[var(--brand-primary)]" />
                  已自定义编排 · 断开的连线在下次运行时生效（断开平台即跳过该平台采集）
                </p>
              ) : null}
              <AmwayFlowOrchestrationPanel
                entityId={entityId}
                getExpectedVersion={() => topologyVersionRef.current}
                setExpectedVersion={(version) => {
                  topologyVersionRef.current = version;
                }}
                disabled={Boolean(runningCustomNodeId)}
                isAwaitingPlanConfirm={isAwaitingPlanConfirm}
                onRefreshFlowPlan={onRefreshFlowPlan}
                activeRunCompleted={
                  Boolean(activeRun)
                  && String(activeRun?.status || '').toLowerCase() === 'completed'
                }
                onTopologyApplied={(remote) => {
                  topologyDirtyRef.current = false;
                  const next = parseFlowTopology(remote);
                  setTopology(next);
                  writeFlowTopology(entityId, next);
                  setEnabledPlatforms(syncPlatformStorageFromTopology(entityId, next));
                }}
              />
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={resetLayout}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-3.5 text-sm font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-secondary)]"
              >
                <RotateCcw size={14} aria-hidden />
                重置布局
              </button>
              <button
                type="button"
                onClick={onOpenRunSettings}
                className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-3.5 text-sm font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-secondary)]"
              >
                <Settings2 size={14} aria-hidden />
                运行设置
              </button>
              {isAwaitingPlanConfirm ? (
                <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--brand-primary)]/40 bg-[var(--bg-secondary)] px-3.5 text-sm font-medium text-[var(--brand-primary)]">
                  待确认计划
                </div>
              ) : running ? (
                <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 text-sm font-medium text-[var(--text-secondary)]">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--brand-primary)]" />
                  {progressMessage || '正在运行'}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={onQuickRun}
                  disabled={Boolean(isRunSubmitting)}
                  className="inline-flex h-10 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] shadow-sm transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
                >
                  <Play size={14} fill="currentColor" aria-hidden />
                  {isRunSubmitting ? '启动中…' : '开始运行'}
                </button>
              )}
            </div>
          </div>

          {/* 3b-2.1 / M3 执行计划投影 + 确认闸 */}
          <div
            className={`mt-3 rounded-xl border px-3.5 py-3 ${
              isAwaitingPlanConfirm
                ? 'border-[var(--brand-primary)]/50 bg-[rgba(31,122,107,0.06)]'
                : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)]'
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Workflow size={14} className="text-[var(--brand-primary)]" aria-hidden />
                <span className="text-xs font-semibold text-[var(--text-primary)]">
                  {isAwaitingPlanConfirm
                    ? '请确认执行计划'
                    : running
                      ? '运行计划'
                      : '本次执行计划'}
                </span>
                {typeof (activeRun?.input_scope as Record<string, unknown> | undefined)?.recipe_name === 'string'
                  && String((activeRun?.input_scope as Record<string, unknown>).recipe_name || '').trim()
                  ? (
                    <span className="rounded-full border border-[var(--brand-primary)]/30 bg-[var(--brand-bg)] px-2 py-0.5 text-[10px] font-medium text-[var(--brand-primary)]">
                      基于配方：{String((activeRun?.input_scope as Record<string, unknown>).recipe_name)}
                    </span>
                  ) : null}
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                    isAwaitingPlanConfirm || executionPlan.source === 'run_flow_plan'
                      ? 'border-[var(--brand-primary)]/40 text-[var(--brand-primary)]'
                      : 'border-[var(--border-subtle)] text-[var(--text-tertiary)]'
                  }`}
                >
                  {isAwaitingPlanConfirm
                    ? '待确认'
                    : executionPlan.source === 'run_flow_plan'
                      ? '任务计划'
                      : '拓扑预览'}
                </span>
              </div>
              <span className="text-[11px] text-[var(--text-tertiary)]">{executionPlan.summary}</span>
            </div>
            <ol className="mt-2.5 flex flex-wrap items-center gap-1.5">
              {executionPlan.steps
                .filter((step) => step.kind !== 'platform' || step.status !== 'skipped')
                .map((step, index, list) => {
                  const tone =
                    step.status === 'active'
                      ? 'border-[var(--brand-primary)] bg-[var(--brand-primary)] text-[var(--brand-contrast)]'
                      : step.status === 'done'
                        ? 'border-[var(--brand-primary)]/40 bg-[var(--bg-primary)] text-[var(--brand-primary)]'
                        : step.status === 'skipped'
                          ? 'border-[var(--border-subtle)] bg-transparent text-[var(--text-tertiary)] line-through'
                          : 'border-[var(--border-subtle)] bg-[var(--bg-primary)] text-[var(--text-secondary)]';
                  return (
                    <li key={step.id} className="flex items-center gap-1.5">
                      <button
                        type="button"
                        title={step.skipReason || step.label}
                        onClick={() => setPanel({ kind: 'node', nodeId: step.nodeId })}
                        className={`inline-flex h-7 max-w-[9.5rem] items-center truncate rounded-full border px-2.5 text-[11px] font-medium transition hover:opacity-90 ${tone}`}
                      >
                        {step.status === 'active' ? '● ' : step.status === 'done' ? '✓ ' : ''}
                        {step.label}
                      </button>
                      {index < list.length - 1 ? (
                        <span className="text-[10px] text-[var(--text-tertiary)]" aria-hidden>
                          →
                        </span>
                      ) : null}
                    </li>
                  );
                })}
            </ol>
            <p className="mt-2 text-[11px] leading-5 text-[var(--text-tertiary)]">
              {isAwaitingPlanConfirm
                ? '仍停在待确认的历史任务：可点「确认并执行」继续，或取消后重新开始。'
                : executionPlan.source === 'run_flow_plan'
                  ? '当前按已锁定的运行计划推进；高亮步骤会随 stage 变化。'
                  : '计划由当前画布拓扑实时推导。点击「开始运行」后按该计划直接执行（运行即确认）。'}
            </p>
            {topologySaveError ? (
              <p className="mt-2 rounded-lg border border-[rgba(220,38,38,0.25)] bg-[rgba(220,38,38,0.06)] px-3 py-2 text-[11px] leading-5 text-[var(--error)]">
                {topologySaveError}
              </p>
            ) : null}
            {isAwaitingPlanConfirm ? (
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => onConfirmFlowPlan?.()}
                  disabled={Boolean(isRunSubmitting)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
                >
                  <Play size={13} fill="currentColor" aria-hidden />
                  确认并执行
                </button>
                <button
                  type="button"
                  onClick={() => onRefreshFlowPlan?.()}
                  disabled={Boolean(isRunSubmitting)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-primary)] px-3.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-secondary)] disabled:opacity-60"
                >
                  <RotateCcw size={13} aria-hidden />
                  刷新计划
                </button>
                <button
                  type="button"
                  onClick={() => onCancelFlowPlan?.()}
                  disabled={Boolean(isRunSubmitting)}
                  className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] px-3.5 text-sm font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-secondary)] disabled:opacity-60"
                >
                  <X size={13} aria-hidden />
                  取消
                </button>
              </div>
            ) : null}
          </div>
        </section>
      </div>

      <div className="relative flex-1 px-5 pb-5 pt-3 lg:px-7 2xl:px-10">
        <ReactFlow
          key={canvasKey}
          className="overflow-hidden rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)]"
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          isValidConnection={isValidConnection}
          deleteKeyCode={['Backspace', 'Delete']}
          onNodeDragStop={persistPositions}
          onNodeClick={(_, node) => setPanel({ kind: 'node', nodeId: node.id })}
          onPaneClick={() => setPanel(null)}
          onEdgeMouseEnter={(_, edge) => setHoveredEdgeId(edge.id)}
          onEdgeMouseLeave={() => setHoveredEdgeId(null)}
          onNodeMouseEnter={(_, node) => setHoveredNodeId(node.id)}
          onNodeMouseLeave={() => setHoveredNodeId(null)}
          onDragOver={(event) => {
            if (event.dataTransfer.types.includes('application/amway-flow-node')) {
              event.preventDefault();
              event.dataTransfer.dropEffect = 'move';
            }
          }}
          onDrop={(event) => {
            const type = event.dataTransfer.getData('application/amway-flow-node');
            if (type !== 'analysis' && type !== 'content') return;
            event.preventDefault();
            const instance = flowInstanceRef.current;
            addCustomNode(
              type,
              instance
                ? instance.screenToFlowPosition({ x: event.clientX, y: event.clientY })
                : { x: 660, y: 470 },
            );
          }}
          onInit={(instance) => {
            flowInstanceRef.current = instance;
          }}
          fitView
          fitViewOptions={{ padding: 0.25, maxZoom: 1 }}
          minZoom={0.4}
          maxZoom={1.6}
          proOptions={{ hideAttribution: false }}
          colorMode={theme}
        >
          <Background gap={22} size={1} color="var(--border-subtle)" />
          <Controls showInteractive={false} position="bottom-left" />
          <MiniMap
            pannable
            zoomable
            position="bottom-right"
            style={{ width: 140, height: 90 }}
            nodeColor={(node) => {
              const status = (node.data as AmwayFlowNodeData | undefined)?.status;
              if (status === 'active') return 'var(--brand-primary)';
              if (status === 'done') return 'var(--brand-border)';
              if (status === 'failed') return 'var(--error)';
              return 'var(--border-subtle)';
            }}
            maskColor={theme === 'dark' ? 'rgba(0, 0, 0, 0.45)' : 'rgba(0, 0, 0, 0.06)'}
          />
          {showGuide ? (
            <Panel position="top-center" className="m-4 w-72 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-4 shadow-lg">
              <div className="flex items-start justify-between gap-2">
                <div className="text-sm font-semibold text-[var(--text-primary)]">生产线画布</div>
                <button
                  type="button"
                  aria-label="关闭引导"
                  onClick={dismissGuide}
                  className="flex h-6 w-6 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-secondary)]"
                >
                  <X size={13} />
                </button>
              </div>
              <p className="mt-1.5 text-xs leading-5 text-[var(--text-secondary)]">
                节点可以自由拖拽排布，位置会自动记住。点击节点查看说明与配置，点击节点上的产出徽章查看答案原文、实体与报告。
              </p>
            </Panel>
          ) : null}
          {/* Phase 3a 节点库：左侧折叠面板，拖入画布创建自定义节点 */}
          <Panel position="top-left" className="m-3">
            {libraryOpen ? (
              <div className="w-52 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-3 shadow-lg">
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs font-semibold text-[var(--text-primary)]">节点库</div>
                  <button
                    type="button"
                    aria-label="收起节点库"
                    onClick={() => setLibraryOpen(false)}
                    className="flex h-5 w-5 items-center justify-center rounded-md text-[var(--text-tertiary)] hover:bg-[var(--bg-secondary)]"
                  >
                    <X size={12} />
                  </button>
                </div>
                <p className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">
                  拖入画布创建，或点击加到画布中心
                </p>
                <div className="mt-2.5 space-y-2">
                  {(Object.keys(CUSTOM_NODE_META) as CustomFlowNodeType[]).map((type) => {
                    const meta = CUSTOM_NODE_META[type];
                    const libraryFull = topology.customNodes.length >= MAX_CUSTOM_NODES;
                    return (
                      <div
                        key={type}
                        draggable={!libraryFull}
                        onDragStart={(event) => {
                          event.dataTransfer.setData('application/amway-flow-node', type);
                          event.dataTransfer.effectAllowed = 'move';
                        }}
                        onClick={() => {
                          if (!libraryFull) addCustomNodeAtViewportCenter(type);
                        }}
                        className={`rounded-lg border border-[var(--border-subtle)] px-3 py-2 transition ${
                          libraryFull
                            ? 'cursor-not-allowed opacity-45'
                            : 'cursor-grab hover:border-[var(--border-strong)] hover:shadow-sm active:cursor-grabbing'
                        }`}
                      >
                        <div className="flex items-center gap-2">
                          <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-md ${iconBadgeClass(type)}`}>
                            {flowNodeIcon(meta.icon)}
                          </span>
                          <span className="text-xs font-medium text-[var(--text-primary)]">{meta.label}</span>
                        </div>
                        <p className="mt-1 text-[11px] leading-4 text-[var(--text-tertiary)]">{meta.libraryHint}</p>
                      </div>
                    );
                  })}
                </div>
                {topology.customNodes.length >= MAX_CUSTOM_NODES ? (
                  <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">
                    已达上限（{MAX_CUSTOM_NODES} 个自定义节点）
                  </p>
                ) : null}
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setLibraryOpen(true)}
                className="flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--text-secondary)] shadow-md transition hover:bg-[var(--bg-secondary)]"
              >
                <Plus size={13} aria-hidden />
                节点库
              </button>
            )}
          </Panel>
        </ReactFlow>


        {panel ? (
          <aside className="amway-flow-drawer absolute bottom-5 right-5 top-3 z-10 flex w-[min(560px,92%)] flex-col rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-[-8px_0_24px_-16px_rgba(38,45,43,0.25)] lg:right-7 2xl:right-10">
            <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] px-5 py-3.5">
              <div className="min-w-0">
                <div className="truncate text-sm font-semibold text-[var(--text-primary)]">
                  {panel.kind === 'node' && selectedNode
                    ? selectedNode.data.label
                    : panel.kind === 'artifact'
                      ? artifactTitle(panel.artifact)
                      : ''}
                </div>
                <div className="mt-0.5 text-xs text-[var(--text-tertiary)]">
                  {panel.kind === 'node' && selectedNode
                    ? STATUS_TEXT[selectedNode.data.status]
                    : panel.kind === 'artifact'
                      ? `${nodeLabel(panel.nodeId)} 的产出`
                      : ''}
                </div>
              </div>
              <button
                type="button"
                aria-label="关闭面板"
                onClick={() => setPanel(null)}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-[var(--border-subtle)] text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]"
              >
                <X size={14} />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4">
              {panel.kind === 'node' && selectedNode ? (
                (() => {
                  const customNode = topology.customNodes.find((item) => item.id === selectedNode.id);
                  if (customNode) {
                    return (
                      <CustomNodeDetail
                        node={selectedNode}
                        customNode={customNode}
                        // 全局互斥：任一自定义/分支运行中，所有运行按钮禁用（不限当前节点）
                        running={Boolean(runningCustomNodeId)}
                        error={customNodeError}
                        onUpdateConfig={updateCustomNodeConfig}
                        onDelete={deleteCustomNode}
                        onRunAnalysis={runAnalysis}
                        onRunAnalysisBranch={runAnalysisBranch}
                        onRunContent={runContent}
                        onOpenArtifact={(key) => setPanel({ kind: 'artifact', nodeId: selectedNode.id, artifact: key })}
                      />
                    );
                  }
                  const plannedPlatformIds = executionPlan.steps
                    .filter((step) => step.kind === 'platform' && step.status !== 'skipped')
                    .map((step) => step.nodeId.replace(/^platform-/, ''));
                  return (
                    <FlowNodeDetail
                      node={selectedNode}
                      activeRun={activeRun}
                      enabledPlatforms={enabledPlatforms}
                      plannedPlatformIds={plannedPlatformIds}
                      questionSets={questionSets}
                      running={running}
                      branchRunning={Boolean(runningCustomNodeId)}
                      branchError={customNodeError}
                      onRetry={onQuickRun}
                      onOpenRunSettings={onOpenRunSettings}
                      onRunDownstreamBranch={
                        selectedNode.id === 'projection'
                          || selectedNode.id === 'report'
                          || selectedNode.id === 'lexicon'
                          ? () => { void runBranchFrom(selectedNode.id, 'downstream'); }
                          : undefined
                      }
                      onOpenArtifact={(key) => {
                        if (key === 'circle') onOpenCircle();
                        else setPanel({ kind: 'artifact', nodeId: selectedNode.id, artifact: key });
                      }}
                      onOpenCircle={onOpenCircle}
                    />
                  );
                })()
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'questions' ? (
                <QuestionsArtifact questions={questionBank} />
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'answers' ? (
                <AnswersArtifact appendix={sourceAppendix} fallback={evidenceSamples} />
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'entities' ? (
                <EntitiesArtifact nodes={projectionNodes} />
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'lexicon' ? (
                <div className="text-sm leading-6 text-[var(--text-secondary)]">
                  实体词库在品牌圈层页的「实体词库」标签中维护。
                  <button
                    type="button"
                    onClick={onOpenCircle}
                    className="ml-2 font-medium text-[var(--brand-primary)] hover:underline"
                  >
                    前往管理
                  </button>
                </div>
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'report' ? (
                hasReport ? (
                  <AssociationReportPanel
                    projection={projection}
                    activeCenterTerm={centerTerm}
                    groups={mapGroups}
                  />
                ) : (
                  <ArtifactEmpty text="报告还没有生成。运行完成后，解读报告会出现在这里。" />
                )
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'analysisResult' ? (
                (() => {
                  const customNode = topology.customNodes.find((item) => item.id === panel.nodeId);
                  const result = customNode?.config.result as FlowAnalysisResult | undefined;
                  return result ? (
                    <AnalysisResultArtifact result={result} />
                  ) : (
                    <ArtifactEmpty text="还没有分析结论。在节点配置中点击「运行分析」生成。" />
                  );
                })()
              ) : null}
              {panel.kind === 'artifact' && panel.artifact === 'contentDraft' ? (
                (() => {
                  const customNode = topology.customNodes.find((item) => item.id === panel.nodeId);
                  const result = customNode?.config.result as FlowContentResult | undefined;
                  return result?.draft ? (
                    <ContentDraftArtifact
                      result={result}
                      template={String(customNode?.config.promptTemplate || DEFAULT_CONTENT_PROMPT_TEMPLATE)}
                    />
                  ) : (
                    <ArtifactEmpty text="还没有内容草稿。在节点配置中点击「生成草稿」运行。" />
                  );
                })()
              ) : null}
            </div>
          </aside>
        ) : null}
      </div>
      <style>{`
        .amway-flow-node-pulse {
          animation: amwayFlowNodePulse 1.6s ease-in-out infinite;
        }
        @keyframes amwayFlowNodePulse {
          0%, 100% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--brand-primary) 45%, transparent); }
          50% { box-shadow: 0 0 0 5px transparent; }
        }
        .amway-flow-drawer {
          animation: amwayFlowDrawerIn 0.28s cubic-bezier(0.32, 0.72, 0, 1);
        }
        @keyframes amwayFlowDrawerIn {
          from { transform: translateX(28px); opacity: 0; }
          to { transform: translateX(0); opacity: 1; }
        }
      `}</style>
    </div>
  );
}

