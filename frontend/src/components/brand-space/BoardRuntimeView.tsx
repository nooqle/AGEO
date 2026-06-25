'use client';

import {
  Pause,
  Play,
  Square,
} from 'lucide-react';
import { GraphUpdateQueue } from './GraphUpdateQueue';
import { NodeInspector } from './NodeInspector';
import styles from './BrandSpace.module.css';
import type {
  ArtifactRef,
  BoardEdge,
  BoardNode,
  BoardRunStatus,
  BrandSpaceGraphUpdate,
  GraphPatch,
  GraphPatchStatus,
  InspectorTab,
  PlatformFetchNode,
  RuntimeEvent,
} from '@/types/brandSpace';

interface BoardRuntimeViewProps {
  runStatus: BoardRunStatus;
  nodes: BoardNode[];
  platforms: PlatformFetchNode[];
  edges: BoardEdge[];
  patches: GraphPatch[];
  graphUpdate?: BrandSpaceGraphUpdate | null;
  artifacts: ArtifactRef[];
  events: RuntimeEvent[];
  selectedNodeId: string;
  inspectorTab: InspectorTab;
  onSelectNode: (nodeId: string) => void;
  onInspectorTabChange: (tab: InspectorTab) => void;
  onRunStart: () => void;
  onRunPause: () => void;
  onRunResume: () => void;
  onRunStop: () => void;
  onPatchDecision: (patchId: string, status: Extract<GraphPatchStatus, 'accepted' | 'rejected' | 'needs_review'>) => void;
  pendingPatchDecisionIds?: string[];
  isRunCommandPending?: boolean;
}

const nodeAccent: Record<BoardNode['kind'], string> = {
  input: 'var(--warning)',
  prepare: 'var(--warning)',
  fetch: 'var(--info)',
  extract: 'var(--brand-primary)',
  review: 'var(--error)',
  graph_update: 'var(--brand-primary)',
};

const nodeKindLabels: Record<BoardNode['kind'], string> = {
  input: '输入',
  prepare: '准备',
  fetch: '抓取',
  extract: '抽取',
  review: '审阅',
  graph_update: '图谱更新',
};

const boardStage = {
  width: 1120,
  height: 720,
};

const stressBoardStage = {
  width: 1680,
  height: 1320,
};

// More than three rows of eight workflow nodes need the expanded QA canvas.
const STRESS_STAGE_NODE_THRESHOLD = 24;

const nodeSize = {
  default: { width: 188, height: 132 },
  rack: { width: 270, height: 520 },
};

const workflowLayout: Record<string, BoardNode['position']> = {
  'brand-seed': { x: 12, y: 45 },
  'question-set': { x: 30, y: 45 },
  'platform-rack': { x: 52, y: 48 },
  'answer-normalize': { x: 76, y: 24 },
  'entity-match': { x: 76, y: 45 },
  'graph-patch': { x: 76, y: 66 },
  'anomaly-review': { x: 52, y: 82 },
  'graph-update': { x: 76, y: 86 },
};

const stageBands = [
  { label: '输入', x: 4, width: 16 },
  { label: '准备', x: 22, width: 16 },
  { label: '抓取', x: 41, width: 22 },
  { label: '抽取', x: 68, width: 16 },
  { label: '审阅 / 更新', x: 68, width: 16, lower: true },
];

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function statusLabel(status: BoardRunStatus) {
  if (status === 'running') return '运行中';
  if (status === 'pause_requested') return '暂停中';
  if (status === 'paused') return '已暂停';
  if (status === 'stopped') return '已停止';
  if (status === 'completed') return '已完成';
  if (status === 'failed') return '失败';
  return '就绪';
}

function runPrimaryLabel(status: BoardRunStatus) {
  if (status === 'running') return '暂停';
  if (status === 'paused') return '继续';
  if (status === 'completed' || status === 'stopped' || status === 'failed') return '重新运行';
  return '全部运行';
}

function runPrimaryAriaLabel(status: BoardRunStatus) {
  if (status === 'running') return '暂停画布运行';
  if (status === 'paused') return '继续画布运行';
  if (status === 'completed' || status === 'stopped' || status === 'failed') return '重新运行画布并创建新的图谱更新';
  return '启动画布运行';
}

function canStopRun(status: BoardRunStatus) {
  return status === 'running' || status === 'paused' || status === 'pause_requested';
}

function platformRackStatusLabel(runStatus: BoardRunStatus, platforms: PlatformFetchNode[]) {
  const runningCount = platforms.filter((platform) => platform.status === 'running').length;
  const completedCount = platforms.filter((platform) => platform.status === 'completed' || platform.progress >= 100).length;
  if (runStatus === 'running') {
    if (runningCount > 0) return `${runningCount} / ${platforms.length} 运行中`;
    if (platforms.length > 0 && completedCount === platforms.length) return `${completedCount} / ${platforms.length} 已完成`;
    return '等待平台回传';
  }
  if (runStatus === 'completed') return `${completedCount || platforms.length} / ${platforms.length} 已完成`;
  if (runStatus === 'failed') return '运行失败';
  if (runStatus === 'paused' || runStatus === 'pause_requested') return '已暂停';
  if (runStatus === 'stopped') return '已停止';
  return '待启动';
}

function platformAbbreviation(platformKey: string) {
  const key = platformKey.toLowerCase();
  const labels: Record<string, string> = {
    chatgpt: 'GPT',
    deepseek: 'DS',
    kimi: 'K',
    doubao: '豆',
    yuanbao: '元',
    hunyuan: '元',
  };
  return labels[key] ?? platformKey.slice(0, 2).toUpperCase();
}

function platformAnswerLabel(platform: PlatformFetchNode) {
  if (platform.answers > 0) {
    return platform.status === 'running' ? `${platform.answers} 条已回传` : `${platform.answers} 条回答`;
  }
  if (platform.status === 'running') {
    return '抓取中';
  }
  return '0 条回答';
}

function platformFailureLabel(platform: PlatformFetchNode) {
  if (platform.failures > 0) {
    return `${platform.failures} 个失败`;
  }
  if (platform.status === 'running') {
    return '统计中';
  }
  return '无失败';
}

function getNodeClass(node: BoardNode, selectedNodeId: string) {
  return classNames(
    styles.node,
    selectedNodeId === node.id && styles.nodeActive,
    node.status === 'running' && styles.nodeRunning,
    node.status === 'needs_review' && styles.nodeReview,
    'rounded-xl p-3',
  );
}

function stageSizeForNodes(nodes: BoardNode[]) {
  return nodes.length > STRESS_STAGE_NODE_THRESHOLD ? stressBoardStage : boardStage;
}

function layoutNode(node: BoardNode): BoardNode {
  return workflowLayout[node.id] ? { ...node, position: workflowLayout[node.id] } : node;
}

function nodeRect(node: BoardNode, stageSize = boardStage) {
  const size = node.id === 'platform-rack' ? nodeSize.rack : nodeSize.default;
  const centerX = (node.position.x / 100) * stageSize.width;
  const centerY = (node.position.y / 100) * stageSize.height;
  return {
    centerX,
    centerY,
    width: size.width,
    height: size.height,
  };
}

function edgePoints(from: BoardNode, to: BoardNode, stageSize = boardStage) {
  const source = nodeRect(from, stageSize);
  const target = nodeRect(to, stageSize);
  const dx = target.centerX - source.centerX;
  const dy = target.centerY - source.centerY;

  if (Math.abs(dx) >= Math.abs(dy)) {
    const direction = dx >= 0 ? 1 : -1;
    return {
      start: {
        x: source.centerX + direction * (source.width / 2),
        y: source.centerY,
      },
      end: {
        x: target.centerX - direction * (target.width / 2),
        y: target.centerY,
      },
      axis: 'x' as const,
    };
  }

  const direction = dy >= 0 ? 1 : -1;
  return {
    start: {
      x: source.centerX,
      y: source.centerY + direction * (source.height / 2),
    },
    end: {
      x: target.centerX,
      y: target.centerY - direction * (target.height / 2),
    },
    axis: 'y' as const,
  };
}

function edgePath(from: BoardNode, to: BoardNode, stageSize = boardStage) {
  const points = edgePoints(from, to, stageSize);
  if (points.axis === 'x') {
    const midX = (points.start.x + points.end.x) / 2;
    return {
      d: `M ${points.start.x} ${points.start.y} C ${midX} ${points.start.y}, ${midX} ${points.end.y}, ${points.end.x} ${points.end.y}`,
      ...points,
    };
  }

  const midY = (points.start.y + points.end.y) / 2;
  return {
    d: `M ${points.start.x} ${points.start.y} C ${points.start.x} ${midY}, ${points.end.x} ${midY}, ${points.end.x} ${points.end.y}`,
    ...points,
  };
}

function edgeIsRunning(edge: BoardEdge, from: BoardNode, to: BoardNode, runStatus: BoardRunStatus) {
  if (runStatus !== 'running') return false;
  return edge.active || from.status === 'running' || to.status === 'running';
}

function edgeShowsTrace(edge: BoardEdge, runStatus: BoardRunStatus) {
  return Boolean(edge.active && (runStatus === 'running' || runStatus === 'completed'));
}

function edgeTraceIsAnimated(edge: BoardEdge, from: BoardNode, to: BoardNode, runStatus: BoardRunStatus) {
  return edgeIsRunning(edge, from, to, runStatus) || Boolean(edge.active && runStatus === 'completed');
}

export function BoardRuntimeView({
  runStatus,
  nodes,
  platforms,
  edges,
  patches,
  graphUpdate,
  artifacts,
  events,
  selectedNodeId,
  inspectorTab,
  onSelectNode,
  onInspectorTabChange,
  onRunStart,
  onRunPause,
  onRunResume,
  onRunStop,
  onPatchDecision,
  pendingPatchDecisionIds = [],
  isRunCommandPending = false,
}: BoardRuntimeViewProps) {
  const layoutNodes = nodes.map(layoutNode);
  const selectedNode = layoutNodes.find((node) => node.id === selectedNodeId) ?? layoutNodes[0];
  const isRunning = runStatus === 'running';
  const nodeById = new Map(layoutNodes.map((node) => [node.id, node]));
  const platformRackNode = nodeById.get('platform-rack');
  const platformProgress = platforms.length
    ? Math.round(platforms.reduce((sum, platform) => sum + platform.progress, 0) / platforms.length)
    : 0;
  const stageSize = stageSizeForNodes(nodes);
  const stopDisabled = isRunCommandPending || !canStopRun(runStatus);

  return (
    <div className="grid min-h-0 grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-4">
        <div className={classNames(styles.surface, 'flex flex-wrap items-center justify-between gap-3 rounded-xl px-4 py-3')}>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={runStatus === 'running' ? onRunPause : runStatus === 'paused' ? onRunResume : onRunStart}
              disabled={isRunCommandPending}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)] disabled:cursor-not-allowed disabled:opacity-55"
              aria-label={runPrimaryAriaLabel(runStatus)}
            >
              {runStatus === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {isRunCommandPending ? '处理中' : runPrimaryLabel(runStatus)}
            </button>
            <button
              type="button"
              onClick={onRunStop}
              disabled={stopDisabled}
              className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-secondary)] disabled:cursor-not-allowed disabled:opacity-55"
              style={{ borderColor: 'var(--border-subtle)' }}
              aria-label={stopDisabled ? '当前没有可停止的画布运行' : '停止画布运行'}
              title={stopDisabled ? '当前没有可停止的运行' : undefined}
            >
              <Square className="h-4 w-4" />
              停止
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3 text-xs text-[var(--text-secondary)]">
            <span className="inline-flex items-center gap-2 rounded-lg border px-2.5 py-1.5" style={{ borderColor: 'var(--border-subtle)' }} aria-live="polite">
              <span className={classNames('h-2 w-2 rounded-full', isRunning && 'animate-pulse')} style={{ background: isRunning ? 'var(--brand-primary)' : 'var(--text-tertiary)' }} />
              {statusLabel(runStatus)}
            </span>
            <span>平台组 {platformProgress}%</span>
            <span>节点 {nodes.length}</span>
            <span>连接 {edges.length}</span>
          </div>
        </div>

        <div className={classNames(styles.canvas, isRunning && styles.runningCanvas, 'rounded-xl')}>
          <div
            className={styles.boardStage}
            data-brand-space-node-count={nodes.length}
            style={{ width: stageSize.width, height: stageSize.height }}
          >
            {stageBands.map((band) => (
              <div
                key={`${band.label}-${band.x}`}
                className={styles.stageBand}
                style={{
                  left: `${band.x}%`,
                  width: `${band.width}%`,
                  top: band.lower ? '57%' : '4%',
                  height: band.lower ? '38%' : '52%',
                }}
              >
                <span>{band.label}</span>
              </div>
            ))}
            <svg
              className={styles.edgeLayer}
              data-brand-space-edges="workflow"
              viewBox={`0 0 ${stageSize.width} ${stageSize.height}`}
              aria-hidden="true"
            >
              <defs>
                <marker id="brand-space-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                  <path d="M 0 0 L 10 5 L 0 10 z" className={styles.edgeArrow} />
                </marker>
              </defs>
              {edges.map((edge, index) => {
                const from = nodeById.get(edge.from);
                const to = nodeById.get(edge.to);
                if (!from || !to) return null;
                const path = edgePath(from, to, stageSize);
                const isEdgeRunning = edgeIsRunning(edge, from, to, runStatus);
                const showsTrace = edgeShowsTrace(edge, runStatus);
                const traceIsAnimated = edgeTraceIsAnimated(edge, from, to, runStatus);
                return (
                  <g
                    key={edge.id}
                    data-brand-space-edge={edge.id}
                    data-edge-state={isEdgeRunning ? 'running' : showsTrace ? 'trace' : edge.dashed ? 'review' : 'idle'}
                    className={classNames(styles.edgeGroup, isEdgeRunning && styles.edgeGroupRunning)}
                  >
                    <path
                      d={path.d}
                      markerEnd="url(#brand-space-arrow)"
                      className={classNames(
                        styles.edgePath,
                        edge.dashed && styles.edgePathDashed,
                      )}
                    />
                    {showsTrace ? (
                      <path
                        d={path.d}
                        className={classNames(
                          styles.edgePathPulse,
                          !traceIsAnimated && styles.edgePathTrace,
                        )}
                      />
                    ) : null}
                    {traceIsAnimated ? (
                      <circle
                        r="3.5"
                        className={classNames(styles.edgePacket, !isEdgeRunning && styles.edgePacketTrace)}
                      >
                        <animateMotion
                          dur={isEdgeRunning ? '2.4s' : '4.2s'}
                          begin={`${index * 0.16}s`}
                          repeatCount="indefinite"
                          path={path.d}
                        />
                      </circle>
                    ) : null}
                  </g>
                );
              })}
            </svg>

            {layoutNodes.filter((node) => node.id !== 'platform-rack').map((node) => (
              <button
                key={node.id}
                type="button"
                data-brand-space-node={node.id}
                onClick={() => onSelectNode(node.id)}
                className={getNodeClass(node, selectedNodeId)}
                style={{ left: `${node.position.x}%`, top: `${node.position.y}%` }}
                aria-label={`选择节点：${node.title}，状态${node.status}，进度${node.progress}%`}
                aria-pressed={selectedNodeId === node.id}
              >
                <span className="absolute left-0 top-0 h-1 w-full rounded-t-xl" style={{ background: nodeAccent[node.kind] }} />
                <span className="flex items-start justify-between gap-2 text-left">
                  <span className="min-w-0">
                    <span className="block text-[11px] font-semibold uppercase" style={{ color: nodeAccent[node.kind] }}>
                      {nodeKindLabels[node.kind]}
                    </span>
                    <span className="mt-2 block text-sm font-semibold text-[var(--text-primary)]">{node.title}</span>
                    <span className="mt-1 block text-xs leading-4 text-[var(--text-secondary)]">{node.subtitle}</span>
                  </span>
                  <span className="h-2.5 w-2.5 rounded-full" style={{ background: node.status === 'completed' ? 'var(--success)' : node.status === 'needs_review' ? 'var(--warning)' : node.status === 'failed' ? 'var(--error)' : 'var(--brand-primary)' }} />
                </span>
                <span className="mt-2 flex items-center justify-between gap-2 text-[11px] text-[var(--text-tertiary)]">
                  <span>{node.status === 'running' ? '处理中' : node.status === 'needs_review' ? '等待审阅' : node.status === 'completed' ? '已完成' : '排队'}</span>
                  <span>{node.progress}%</span>
                </span>
                <span className="mt-3 block h-1.5 rounded-full bg-[var(--bg-tertiary)]">
                  <span className="block h-full rounded-full bg-[var(--brand-primary)]" style={{ width: `${node.progress}%` }} />
                </span>
              </button>
            ))}

            {platformRackNode ? (
              <section
                data-brand-space-rack="platform-rack"
                className={classNames(styles.rack, isRunning && styles.rackRunning, 'rounded-xl p-4')}
                style={{ left: `${platformRackNode.position.x}%`, top: `${platformRackNode.position.y}%` }}
              >
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-[11px] font-semibold uppercase text-[var(--brand-text)]">抓取组</p>
                    <h3 className="mt-1 text-sm font-semibold text-[var(--text-primary)]">AI 平台抓取组</h3>
                  </div>
                  <span className="rounded-lg bg-[var(--brand-bg)] px-2 py-1 text-xs font-semibold text-[var(--brand-text)]">
                    {platformRackStatusLabel(runStatus, platforms)}
                  </span>
                </div>
                <div className="space-y-3">
                  {platforms.map((platform) => {
                    const answerLabel = platformAnswerLabel(platform);
                    const failureLabel = platformFailureLabel(platform);
                    return (
                      <button
                        key={platform.id}
                        type="button"
                        onClick={() => onSelectNode('platform-rack')}
                        className={classNames(styles.platformCard, platform.status === 'running' && styles.platformRunning, 'w-full rounded-xl p-3 text-left')}
                        aria-label={`查看${platform.label}，进度${platform.progress}%，${answerLabel}，${failureLabel}`}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <div className="flex items-center gap-3">
                            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--bg-tertiary)] text-xs font-bold text-[var(--text-primary)]">
                              {platformAbbreviation(platform.platformKey)}
                            </span>
                            <span>
                              <span className="block text-sm font-semibold text-[var(--text-primary)]">{platform.label}</span>
                              <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">{platform.model}</span>
                            </span>
                          </div>
                          <span className="text-xs font-semibold text-[var(--text-primary)]">{platform.progress}%</span>
                        </div>
                        <div className="mt-3 flex items-center justify-between text-[11px] text-[var(--text-tertiary)]">
                          <span>{answerLabel}</span>
                          <span>{failureLabel}</span>
                        </div>
                        <div className="mt-3 h-1.5 rounded-full bg-[var(--bg-tertiary)]">
                          <div className="h-full rounded-full bg-[var(--brand-primary)]" style={{ width: `${platform.progress}%` }} />
                        </div>
                      </button>
                    );
                  })}
                </div>
              </section>
            ) : null}
          </div>
        </div>

        <GraphUpdateQueue
          patches={patches}
          graphUpdate={graphUpdate}
          onPatchDecision={onPatchDecision}
          pendingPatchDecisionIds={pendingPatchDecisionIds}
        />
      </div>

      <NodeInspector
        node={selectedNode}
        artifacts={artifacts}
        events={events}
        activeTab={inspectorTab}
        onTabChange={onInspectorTabChange}
      />
    </div>
  );
}
