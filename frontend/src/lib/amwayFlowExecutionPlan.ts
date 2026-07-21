/**
 * AmwayChina flow execution plan projection (blueprint 3b-2.1).
 *
 * Derives the planned run path from canvas topology + platform switches.
 * Must stay aligned with backend topology gates:
 * - app.workflow.topology_resolver (platform + chain gates)
 * - analysis/content auto-run rules (wired custom edges only)
 */

export type FlowPlanStepStatus = 'pending' | 'active' | 'done' | 'skipped';

export type FlowPlanStep = {
  id: string;
  nodeId: string;
  label: string;
  kind: 'asset' | 'executor' | 'platform' | 'custom';
  status: FlowPlanStepStatus;
  skipReason?: string;
};

export type FlowExecutionPlan = {
  steps: FlowPlanStep[];
  /** Builtin + custom edge ids that participate in the planned path. */
  activeEdgeIds: string[];
  /** Human-readable one-line summary for the plan strip. */
  summary: string;
  /** Index of the first non-skipped step matching current stage (or -1). */
  activeStepIndex: number;
  /** Where the plan structure came from (M1). */
  source?: 'local_topology' | 'run_flow_plan';
  generatedAt?: string;
};

/** Server snapshot attached to BrandIntelligenceRun.input_scope.flow_plan */
export type ServerFlowPlanSnapshot = {
  version?: number;
  source?: string;
  generated_at?: string;
  summary?: string;
  planned_platforms?: string[];
  active_edge_ids?: string[];
  steps?: Array<{
    node_id?: string;
    label?: string;
    status?: string;
    skip_reason?: string | null;
  }>;
};

function kindOfNodeId(nodeId: string): FlowPlanStep['kind'] {
  if (nodeId.startsWith('platform-')) return 'platform';
  if (nodeId === 'question-set' || nodeId === 'lexicon') return 'asset';
  if (nodeId === 'fetch' || nodeId === 'extract' || nodeId === 'projection' || nodeId === 'report') {
    return 'executor';
  }
  return 'custom';
}

/**
 * Convert a run-scoped server flow_plan into the canvas FlowExecutionPlan shape.
 * Runtime active/done is applied separately via mergeRuntimeOntoPlan.
 */
export function parseServerFlowPlan(raw: unknown): FlowExecutionPlan | null {
  if (!raw || typeof raw !== 'object') return null;
  const doc = raw as ServerFlowPlanSnapshot;
  const stepsRaw = Array.isArray(doc.steps) ? doc.steps : [];
  if (!stepsRaw.length && !doc.summary) return null;
  const steps: FlowPlanStep[] = stepsRaw
    .filter((s) => s && typeof s === 'object' && s.node_id)
    .map((s, index) => {
      const nodeId = String(s.node_id);
      const statusRaw = String(s.status || 'pending');
      const status: FlowPlanStepStatus =
        statusRaw === 'skipped'
          ? 'skipped'
          : statusRaw === 'active' || statusRaw === 'running'
            ? 'active'
            : statusRaw === 'done' || statusRaw === 'completed'
              ? 'done'
              : 'pending';
      return {
        id: `server-step-${index}-${nodeId}`,
        nodeId,
        label: String(s.label || nodeId),
        kind: kindOfNodeId(nodeId),
        status,
        skipReason: s.skip_reason ? String(s.skip_reason) : undefined,
      };
    });
  return {
    steps,
    activeEdgeIds: Array.isArray(doc.active_edge_ids)
      ? doc.active_edge_ids.map(String)
      : [],
    summary: String(doc.summary || ''),
    activeStepIndex: steps.findIndex((s) => s.status === 'active'),
    source: 'run_flow_plan',
    generatedAt: doc.generated_at ? String(doc.generated_at) : undefined,
  };
}

/**
 * Overlay runtime stage statuses from a locally derived plan onto a base plan
 * (typically the authoritative run snapshot). Skip reasons stay from base.
 */
export function mergeRuntimeOntoPlan(
  base: FlowExecutionPlan,
  runtime: FlowExecutionPlan,
): FlowExecutionPlan {
  const runtimeByNode = new Map(runtime.steps.map((s) => [s.nodeId, s]));
  const steps = base.steps.map((step) => {
    if (step.status === 'skipped') return step;
    const rt = runtimeByNode.get(step.nodeId);
    if (!rt || rt.status === 'skipped') return { ...step, status: 'pending' as const };
    return { ...step, status: rt.status };
  });
  return {
    ...base,
    steps,
    activeStepIndex: steps.findIndex((s) => s.status === 'active'),
    // keep base edges as the committed plan path
    activeEdgeIds: base.activeEdgeIds.length ? base.activeEdgeIds : runtime.activeEdgeIds,
  };
}

export type FlowTopologyLike = {
  customNodes: Array<{ id: string; type: string; config?: Record<string, unknown> }>;
  customEdges: Array<{ id: string; source: string; target: string }>;
  removedEdgeIds: string[];
};

const PLATFORM_LABELS: Record<string, string> = {
  deepseek: 'DeepSeek',
  kimi: 'Kimi',
  doubao: '豆包',
  hunyuan: '腾讯元宝',
};

const EDGE_QUESTIONS_FETCH = 'e-questions-fetch';
const EDGE_FETCH_EXTRACT = 'e-fetch-extract';
const EDGE_EXTRACT_PROJECTION = 'e-extract-projection';
const EDGE_PROJECTION_REPORT = 'e-projection-report';

function edgeActive(topology: FlowTopologyLike, edgeId: string): boolean {
  return !topology.removedEdgeIds.includes(edgeId);
}

function platformEdgeId(platform: string): string {
  return `e-fetch-${platform}`;
}

/** Map runtime stage codes to a primary canvas node id. */
export function stageCodeToNodeId(stageCode: string): string | null {
  const code = String(stageCode || '').trim().toUpperCase();
  if (!code) return null;
  if (
    code.includes('QUESTION')
    || code === 'A3'
    || code.includes('PLANNING')
  ) {
    return 'question-set';
  }
  if (code.startsWith('A4') || code.includes('FETCH') || code.includes('ANSWER')) {
    return 'fetch';
  }
  if (code.includes('EXTRACT') || code.includes('ENTITY')) {
    return 'extract';
  }
  if (code.includes('PROJECTION') || code.includes('CIRCLE') || code.includes('BUILDING')) {
    return 'projection';
  }
  if (
    code.includes('SECONDARY')
    || code.includes('CONTENT')
    || code.includes('DRAFT')
  ) {
    // Prefer custom nodes; caller may refine by scanning steps
    return code.includes('CONTENT') || code.includes('DRAFT') ? '__content__' : '__analysis__';
  }
  if (code.startsWith('A5') || code.includes('ANALYZ') || code.includes('REPORT') || code.includes('METRIC')) {
    return 'report';
  }
  if (code.includes('COMPLETE')) {
    return '__done__';
  }
  return null;
}

export function buildAmwayFlowExecutionPlan(input: {
  topology: FlowTopologyLike;
  enabledPlatforms: string[];
  allPlatformIds?: string[];
  stageCode?: string;
  isRunning?: boolean;
  runFailed?: boolean;
  hasProjectionData?: boolean;
  hasReportData?: boolean;
  answerCount?: number;
}): FlowExecutionPlan {
  const {
    topology,
    enabledPlatforms,
    allPlatformIds = Object.keys(PLATFORM_LABELS),
    stageCode = '',
    isRunning = false,
    runFailed = false,
    hasProjectionData = false,
    hasReportData = false,
    answerCount = 0,
  } = input;

  const steps: FlowPlanStep[] = [];
  const activeEdgeIds: string[] = [];

  const fetchChain = edgeActive(topology, EDGE_QUESTIONS_FETCH);
  const extractChain = edgeActive(topology, EDGE_FETCH_EXTRACT);
  const projectionChain = edgeActive(topology, EDGE_EXTRACT_PROJECTION);
  const reportChain = edgeActive(topology, EDGE_PROJECTION_REPORT);

  // 1) question-set
  steps.push({
    id: 'step-question-set',
    nodeId: 'question-set',
    label: '问题集',
    kind: 'asset',
    status: fetchChain ? 'pending' : 'skipped',
    skipReason: fetchChain ? undefined : '已断开「问题集 → 采集」',
  });
  if (fetchChain) activeEdgeIds.push(EDGE_QUESTIONS_FETCH);

  // 2) fetch
  const fetchPlanned = fetchChain;
  steps.push({
    id: 'step-fetch',
    nodeId: 'fetch',
    label: '答案采集',
    kind: 'executor',
    status: fetchPlanned ? 'pending' : 'skipped',
    skipReason: fetchPlanned ? undefined : '采集链未启用',
  });

  // 3) platforms
  const plannedPlatforms: string[] = [];
  for (const platform of allPlatformIds) {
    const nodeId = `platform-${platform}`;
    const edgeId = platformEdgeId(platform);
    const edgeOn = edgeActive(topology, edgeId);
    const switchOn = enabledPlatforms.includes(platform);
    let status: FlowPlanStepStatus = 'pending';
    let skipReason: string | undefined;
    if (!fetchPlanned) {
      status = 'skipped';
      skipReason = '采集链未启用';
    } else if (!edgeOn) {
      status = 'skipped';
      skipReason = '画布已断开该平台连线';
    } else if (!switchOn) {
      status = 'skipped';
      skipReason = '平台开关已关闭';
    } else {
      plannedPlatforms.push(platform);
      activeEdgeIds.push(edgeId);
    }
    steps.push({
      id: `step-${nodeId}`,
      nodeId,
      label: PLATFORM_LABELS[platform] || platform,
      kind: 'platform',
      status,
      skipReason,
    });
  }

  // 4) extract
  const extractPlanned = fetchPlanned && extractChain && plannedPlatforms.length > 0;
  steps.push({
    id: 'step-extract',
    nodeId: 'extract',
    label: '实体抽取',
    kind: 'executor',
    status: extractPlanned ? 'pending' : 'skipped',
    skipReason: extractPlanned
      ? undefined
      : !extractChain
        ? '已断开「采集 → 抽取」'
        : plannedPlatforms.length === 0
          ? '无可用采集平台'
          : '上游未计划采集',
  });
  if (extractPlanned) {
    activeEdgeIds.push(EDGE_FETCH_EXTRACT);
    if (edgeActive(topology, 'e-lexicon-extract')) {
      activeEdgeIds.push('e-lexicon-extract');
    }
  }

  // lexicon asset appears when extract planned
  steps.splice(
    steps.findIndex((s) => s.nodeId === 'extract'),
    0,
    {
      id: 'step-lexicon',
      nodeId: 'lexicon',
      label: '实体词库',
      kind: 'asset',
      status: extractPlanned || topology.customNodes.some((n) => n.type === 'content')
        ? 'pending'
        : 'skipped',
      skipReason:
        extractPlanned || topology.customNodes.some((n) => n.type === 'content')
          ? undefined
          : '本轮未使用词库下游',
    },
  );

  // 5) projection
  const projectionPlanned = extractPlanned && projectionChain;
  steps.push({
    id: 'step-projection',
    nodeId: 'projection',
    label: '图谱构建',
    kind: 'executor',
    status: projectionPlanned ? 'pending' : 'skipped',
    skipReason: projectionPlanned
      ? undefined
      : !projectionChain
        ? '已断开「抽取 → 图谱」'
        : '上游抽取未计划',
  });
  if (projectionPlanned) activeEdgeIds.push(EDGE_EXTRACT_PROJECTION);

  // 6) report
  const reportPlanned = projectionPlanned && reportChain;
  steps.push({
    id: 'step-report',
    nodeId: 'report',
    label: '报告生成',
    kind: 'executor',
    status: reportPlanned ? 'pending' : 'skipped',
    skipReason: reportPlanned
      ? undefined
      : !reportChain
        ? '已断开「图谱 → 报告」'
        : '上游图谱未计划',
  });
  if (reportPlanned) activeEdgeIds.push(EDGE_PROJECTION_REPORT);

  // 7) analysis custom nodes (wired from projection/report)
  const analysisNodes = topology.customNodes.filter((n) => n.type === 'analysis');
  const contentNodes = topology.customNodes.filter((n) => n.type === 'content');
  const analysisIds = new Set(analysisNodes.map((n) => n.id));
  const plannedAnalysisIds = new Set<string>();

  for (const node of analysisNodes) {
    const sources = topology.customEdges
      .filter((e) => e.target === node.id)
      .map((e) => e.source);
    const fromProjection = sources.includes('projection') && (projectionPlanned || hasProjectionData);
    const fromReport = sources.includes('report') && (reportPlanned || hasReportData);
    const wired = fromProjection || fromReport;
    if (wired) {
      plannedAnalysisIds.add(node.id);
      for (const edge of topology.customEdges) {
        if (edge.target === node.id && (edge.source === 'projection' || edge.source === 'report')) {
          activeEdgeIds.push(edge.id);
        }
      }
    }
    const label = String(node.config?.label || '数据分析');
    steps.push({
      id: `step-${node.id}`,
      nodeId: node.id,
      label,
      kind: 'custom',
      status: wired ? 'pending' : 'skipped',
      skipReason: wired ? undefined : '未从图谱/报告接入连线',
    });
  }

  // 8) content custom nodes
  for (const node of contentNodes) {
    const sources = topology.customEdges
      .filter((e) => e.target === node.id)
      .map((e) => e.source);
    const fromLexicon = sources.includes('lexicon');
    const fromAnalysis = sources.some((s) => plannedAnalysisIds.has(s));
    // Keep in sync with backend build_execution_plan_summary (P1-4).
    const planned =
      fromAnalysis
      || (fromLexicon && (extractPlanned || plannedAnalysisIds.size > 0 || hasProjectionData));
    const wired = fromLexicon || sources.some((s) => analysisIds.has(s));
    if (planned) {
      for (const edge of topology.customEdges) {
        if (edge.target === node.id) activeEdgeIds.push(edge.id);
      }
    }
    const label = String(node.config?.label || '内容创作');
    steps.push({
      id: `step-${node.id}`,
      nodeId: node.id,
      label,
      kind: 'custom',
      status: planned ? 'pending' : 'skipped',
      skipReason: planned
        ? undefined
        : !wired
          ? '未从词库/分析接入连线'
          : '上游分析未计划',
    });
  }

  // Assign runtime status on top of pending/skipped
  const stageNode = stageCodeToNodeId(stageCode);
  const hasDataDone = {
    'question-set': answerCount > 0 || hasProjectionData || isRunning,
    lexicon: hasProjectionData || isRunning,
    fetch: answerCount > 0,
    extract: hasProjectionData,
    projection: hasProjectionData,
    report: hasReportData,
  } as Record<string, boolean>;

  let activeStepIndex = -1;
  const completedRun = stageNode === '__done__' || (!isRunning && (hasProjectionData || hasReportData));

  steps.forEach((step, index) => {
    if (step.status === 'skipped') return;

    if (runFailed && isRunning) {
      // keep pending except mark active stage as failed via active flag only
    }

    if (completedRun && !isRunning) {
      if (hasDataDone[step.nodeId] || step.kind === 'custom') {
        // custom: done if config.result exists — unknown here, leave pending unless running finished with cascade
        if (step.kind !== 'custom') {
          step.status = hasDataDone[step.nodeId] ? 'done' : 'pending';
        }
      }
      return;
    }

    if (!isRunning) {
      step.status = 'pending';
      return;
    }

    // running
    if (stageNode === '__done__') {
      step.status = 'done';
      return;
    }

    if (stageNode === '__analysis__') {
      if (step.kind === 'custom' && analysisIds.has(step.nodeId)) {
        step.status = 'active';
        if (activeStepIndex < 0) activeStepIndex = index;
      } else if (
        step.nodeId === 'question-set'
        || step.nodeId === 'lexicon'
        || step.nodeId === 'fetch'
        || step.nodeId.startsWith('platform-')
        || step.nodeId === 'extract'
        || step.nodeId === 'projection'
        || step.nodeId === 'report'
      ) {
        step.status = 'done';
      }
      return;
    }

    if (stageNode === '__content__') {
      if (step.kind === 'custom' && contentNodes.some((n) => n.id === step.nodeId)) {
        step.status = 'active';
        if (activeStepIndex < 0) activeStepIndex = index;
      } else if (step.kind === 'custom' && analysisIds.has(step.nodeId)) {
        step.status = 'done';
      } else if (step.kind !== 'custom') {
        step.status = 'done';
      }
      return;
    }

    const order = [
      'question-set',
      'fetch',
      ...allPlatformIds.map((p) => `platform-${p}`),
      'lexicon',
      'extract',
      'projection',
      'report',
    ];
    const stageIdx = stageNode ? order.indexOf(stageNode) : -1;
    const stepOrderIdx = order.indexOf(step.nodeId);

    if (step.kind === 'custom') {
      // custom after builtins
      if (stageIdx >= order.indexOf('report') || stageNode === 'report') {
        step.status = 'pending';
      }
      return;
    }

    if (stageIdx < 0) {
      step.status = 'pending';
      return;
    }

    if (step.nodeId.startsWith('platform-')) {
      if (stageNode === 'fetch') {
        step.status = 'active';
        if (activeStepIndex < 0) activeStepIndex = index;
      } else if (stageIdx > order.indexOf('fetch')) {
        step.status = 'done';
      } else {
        step.status = 'pending';
      }
      return;
    }

    if (stepOrderIdx < 0) {
      step.status = 'pending';
      return;
    }
    if (stepOrderIdx < stageIdx) {
      step.status = 'done';
    } else if (stepOrderIdx === stageIdx || (stageNode === 'fetch' && step.nodeId === 'fetch')) {
      step.status = 'active';
      if (activeStepIndex < 0) activeStepIndex = index;
    } else {
      step.status = 'pending';
    }
  });

  if (activeStepIndex < 0) {
    activeStepIndex = steps.findIndex((s) => s.status === 'active');
  }

  const plannedLabels = steps
    .filter((s) => s.status !== 'skipped')
    .map((s) => s.label);
  const skippedCount = steps.filter((s) => s.status === 'skipped').length;
  const platformPlan = plannedPlatforms
    .map((p) => PLATFORM_LABELS[p] || p)
    .join('、');

  const summaryParts = [
    plannedLabels.length
      ? `将执行 ${plannedLabels.length} 步`
      : '当前拓扑下无可执行步骤',
  ];
  if (platformPlan) summaryParts.push(`平台：${platformPlan}`);
  if (skippedCount) summaryParts.push(`跳过 ${skippedCount} 项`);

  return {
    steps,
    activeEdgeIds: Array.from(new Set(activeEdgeIds)),
    summary: summaryParts.join(' · '),
    activeStepIndex,
    source: 'local_topology',
  };
}

/** Node ids that are part of the planned (non-skipped) path. */
export function plannedNodeIdSet(plan: FlowExecutionPlan): Set<string> {
  return new Set(plan.steps.filter((s) => s.status !== 'skipped').map((s) => s.nodeId));
}

export function skippedNodeIdSet(plan: FlowExecutionPlan): Set<string> {
  return new Set(plan.steps.filter((s) => s.status === 'skipped').map((s) => s.nodeId));
}
