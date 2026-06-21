'use client';

import {
  Maximize2,
  MousePointer2,
  Pause,
  Play,
  Plus,
  Square,
  Trash2,
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
  rack: { width: 270, height: 560 },
};

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

function statusLabel(status: BoardRunStatus) {
  if (status === 'running') return '运行中';
  if (status === 'paused') return '已暂停';
  if (status === 'stopped') return '已停止';
  return '就绪';
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
}: BoardRuntimeViewProps) {
  const selectedNode = nodes.find((node) => node.id === selectedNodeId) ?? nodes[0];
  const isRunning = runStatus === 'running';
  const nodeById = new Map(nodes.map((node) => [node.id, node]));
  const platformRackNode = nodeById.get('platform-rack');
  const platformProgress = platforms.length
    ? Math.round(platforms.reduce((sum, platform) => sum + platform.progress, 0) / platforms.length)
    : 0;
  const stageSize = stageSizeForNodes(nodes);

  return (
    <div className="grid min-h-0 grid-cols-1 gap-4 2xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0 space-y-4">
        <div className={classNames(styles.surface, 'flex flex-wrap items-center justify-between gap-3 rounded-xl px-4 py-3')}>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={runStatus === 'running' ? onRunPause : runStatus === 'paused' ? onRunResume : onRunStart}
              className="inline-flex h-10 items-center gap-2 rounded-lg bg-[var(--brand-primary)] px-3 text-sm font-semibold text-[var(--brand-contrast)]"
              aria-label={runStatus === 'running' ? '暂停画布运行' : runStatus === 'paused' ? '继续画布运行' : '启动画布运行'}
            >
              {runStatus === 'running' ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}
              {runStatus === 'running' ? '暂停' : runStatus === 'paused' ? '继续' : '全部运行'}
            </button>
            <button
              type="button"
              onClick={onRunStop}
              className="inline-flex h-10 items-center gap-2 rounded-lg border px-3 text-sm font-medium text-[var(--text-secondary)]"
              style={{ borderColor: 'var(--border-subtle)' }}
              aria-label="停止画布运行"
            >
              <Square className="h-4 w-4" />
              停止
            </button>
            <button type="button" className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="选择" aria-label="选择节点工具">
              <MousePointer2 className="h-4 w-4" />
            </button>
            <button type="button" className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="适配视图" aria-label="适配画布视图">
              <Maximize2 className="h-4 w-4" />
            </button>
            <button type="button" className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="添加节点" aria-label="添加节点">
              <Plus className="h-4 w-4" />
            </button>
            <button type="button" className="inline-flex h-10 w-10 items-center justify-center rounded-lg border text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }} title="删除" aria-label="删除所选节点">
              <Trash2 className="h-4 w-4" />
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
            style={{ minWidth: stageSize.width, height: stageSize.height }}
          >
            <svg
              className={styles.edgeLayer}
              data-brand-space-edges="workflow"
              viewBox={`0 0 ${stageSize.width} ${stageSize.height}`}
              aria-hidden="true"
            >
              {edges.map((edge, index) => {
                const from = nodeById.get(edge.from);
                const to = nodeById.get(edge.to);
                if (!from || !to) return null;
                const path = edgePath(from, to, stageSize);
                return (
                  <g key={edge.id} data-brand-space-edge={edge.id} className={styles.edgeGroup}>
                    <path
                      d={path.d}
                      className={classNames(
                        styles.edgePath,
                        edge.dashed && styles.edgePathDashed,
                      )}
                    />
                    {edge.active && isRunning ? (
                      <path d={path.d} className={styles.edgePathPulse} />
                    ) : null}
                    {edge.active && isRunning ? (
                      <circle r="3.5" className={styles.edgePacket}>
                        <animateMotion
                          dur="2.4s"
                          begin={`${index * 0.16}s`}
                          repeatCount="indefinite"
                          path={path.d}
                        />
                      </circle>
                    ) : null}
                    <circle
                      cx={path.start.x}
                      cy={path.start.y}
                      r="4"
                      className={classNames(styles.edgePort, edge.active && isRunning && styles.edgePortActive)}
                    />
                    <circle
                      cx={path.end.x}
                      cy={path.end.y}
                      r="4"
                      className={classNames(styles.edgePort, edge.active && isRunning && styles.edgePortActive)}
                    />
                  </g>
                );
              })}
            </svg>

            {nodes.filter((node) => node.id !== 'platform-rack').map((node) => (
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
                    {platforms.filter((platform) => platform.status === 'running').length} / 4 运行中
                  </span>
                </div>
                <div className="space-y-3">
                  {platforms.map((platform) => (
                    <button
                      key={platform.id}
                      type="button"
                      onClick={() => onSelectNode('platform-rack')}
                      className={classNames(styles.platformCard, platform.status === 'running' && styles.platformRunning, 'w-full rounded-xl p-3 text-left')}
                      aria-label={`查看${platform.label}，进度${platform.progress}%，回答${platform.answers}条`}
                    >
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-3">
                          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-[var(--bg-tertiary)] text-xs font-bold text-[var(--text-primary)]">
                            {platform.platformKey === 'deepseek' ? 'DS' : platform.platformKey.slice(0, 1).toUpperCase()}
                          </span>
                          <span>
                            <span className="block text-sm font-semibold text-[var(--text-primary)]">{platform.label}</span>
                            <span className="mt-0.5 block text-xs text-[var(--text-secondary)]">{platform.model}</span>
                          </span>
                        </div>
                        <span className="text-xs font-semibold text-[var(--text-primary)]">{platform.progress}%</span>
                      </div>
                      <div className="mt-3 flex items-center justify-between text-[11px] text-[var(--text-tertiary)]">
                        <span>{platform.answers} 条回答</span>
                        <span>{platform.failures ? `${platform.failures} 个失败` : '无失败'}</span>
                      </div>
                      <div className="mt-3 h-1.5 rounded-full bg-[var(--bg-tertiary)]">
                        <div className="h-full rounded-full bg-[var(--brand-primary)]" style={{ width: `${platform.progress}%` }} />
                      </div>
                    </button>
                  ))}
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
