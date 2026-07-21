'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Panel,
  Position,
  ReactFlow,
  getNodesBounds,
  type Connection,
  type Edge,
  type EdgeChange,
  type IsValidConnection,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import {
  ChartNoAxesColumn,
  CheckCircle2,
  Database,
  FileText,
  ListChecks,
  Orbit,
  PenLine,
  Play,
  Plus,
  RotateCcw,
  ScanSearch,
  Settings2,
  Workflow,
  X,
} from 'lucide-react';
import { api } from '@/services/api';
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

type FlowNodeStatus = 'idle' | 'active' | 'done' | 'failed' | 'skipped';
type FlowArtifactKey = 'questions' | 'answers' | 'entities' | 'circle' | 'report' | 'lexicon' | 'analysisResult' | 'contentDraft';

type FlowNodeOutput = {
  key: FlowArtifactKey;
  label: string;
  count?: number | null;
  disabled?: boolean;
};

type AmwayFlowNodeData = {
  label: string;
  subtitle: string;
  icon: string;
  status: FlowNodeStatus;
  variant: 'asset' | 'process' | 'platform' | 'analysis' | 'content';
  outputs: FlowNodeOutput[];
  description: string;
  enabled?: boolean;
  /** 3b-2: node is on the planned path (even when still idle). */
  planned?: boolean;
  onOutput?: (nodeId: string, key: FlowArtifactKey) => void;
  onToggle?: (nodeId: string) => void;
};

type AmwayFlowNode = Node<AmwayFlowNodeData, 'amway'>;

type PanelState =
  | { kind: 'node'; nodeId: string }
  | { kind: 'artifact'; nodeId: string; artifact: FlowArtifactKey }
  | null;

const PLATFORM_META: Array<{ id: string; label: string }> = [
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'kimi', label: 'Kimi' },
  { id: 'doubao', label: '豆包' },
  { id: 'hunyuan', label: '腾讯元宝' },
];

const NODE_DEFINITIONS: Array<{
  id: string;
  label: string;
  icon: string;
  variant: 'asset' | 'process';
  description: string;
  position: { x: number; y: number };
}> = [
  {
    id: 'question-set',
    label: '问题集',
    icon: 'list',
    variant: 'asset',
    description: '本轮采集使用的题目来源。默认由系统按品牌生成问题集，也可以上传自己的问题文件。',
    position: { x: 0, y: 0 },
  },
  {
    id: 'lexicon',
    label: '实体词库',
    icon: 'database',
    variant: 'asset',
    description: '回答分析时的品牌实体识别范围。词库在品牌圈层页的实体词库标签中维护。',
    position: { x: 0, y: 250 },
  },
  {
    id: 'fetch',
    label: '答案采集',
    icon: 'workflow',
    variant: 'process',
    description: '把问题逐条投给各个 AI 平台，复现真实用户看到的回答。',
    position: { x: 320, y: 40 },
  },
  {
    id: 'extract',
    label: '实体抽取与校准',
    icon: 'scan',
    variant: 'process',
    description: '从回答原文中识别与品牌相关的实体和关系，并按样本量校准置信度。',
    position: { x: 320, y: 300 },
  },
  {
    id: 'projection',
    label: '图谱构建',
    icon: 'orbit',
    variant: 'process',
    description: '把校准后的实体按与品牌的距离排布成圈层图谱。',
    position: { x: 660, y: 330 },
  },
  {
    id: 'report',
    label: '报告生成',
    icon: 'file',
    variant: 'process',
    description: '基于图谱与原文证据生成可交付的解读报告。',
    position: { x: 980, y: 330 },
  },
];

const PLATFORM_POSITIONS = [
  { x: 660, y: -110 },
  { x: 660, y: -30 },
  { x: 660, y: 50 },
  { x: 660, y: 130 },
];

const STATUS_TEXT: Record<FlowNodeStatus, string> = {
  idle: '待运行',
  active: '运行中',
  done: '已完成',
  failed: '失败',
  skipped: '计划跳过',
};

const ALL_PLATFORM_IDS = PLATFORM_META.map((item) => item.id);
const PLATFORMS_STORAGE_PREFIX = 'amway-flow-platforms:';

/** 读取画布平台开关（按实体持久化）。ConsolePage 启动运行时也会读取，保持两处一致。 */
export function readEnabledFlowPlatforms(entityId: string): string[] {
  if (typeof window === 'undefined') return ALL_PLATFORM_IDS;
  try {
    const raw = window.localStorage.getItem(PLATFORMS_STORAGE_PREFIX + entityId);
    if (!raw) return ALL_PLATFORM_IDS;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return ALL_PLATFORM_IDS;
    const valid = parsed.filter((id) => ALL_PLATFORM_IDS.includes(String(id))).map(String);
    return valid.length ? valid : ALL_PLATFORM_IDS;
  } catch {
    return ALL_PLATFORM_IDS;
  }
}

function writeEnabledFlowPlatforms(entityId: string, platforms: string[]): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PLATFORMS_STORAGE_PREFIX + entityId, JSON.stringify(platforms));
  } catch {
    // 忽略持久化失败
  }
}

const GUIDE_STORAGE_KEY = 'amway-flow-guide-seen';

// ===== 拓扑数据模型（3a 编排 + 3b 真执行/计划投影）=====
// 拓扑是执行约束与计划投影的唯一前端事实源；布局（amway-flow-layout）只管位置。
type CustomFlowNodeType = 'analysis' | 'content';

type FlowTopologyCustomNode = {
  id: string;
  type: CustomFlowNodeType;
  position: { x: number; y: number };
  config: Record<string, unknown>;
};

type FlowTopologyCustomEdge = {
  id: string;
  source: string;
  target: string;
};

type FlowTopology = {
  version: 1;
  customNodes: FlowTopologyCustomNode[];
  customEdges: FlowTopologyCustomEdge[];
  removedEdgeIds: string[];
};

const TOPOLOGY_STORAGE_PREFIX = 'amway-flow-topology:';
const MAX_CUSTOM_NODES = 20;

function emptyFlowTopology(): FlowTopology {
  return { version: 1, customNodes: [], customEdges: [], removedEdgeIds: [] };
}

function parseFlowTopology(raw: unknown): FlowTopology {
  const parsed = raw as Partial<FlowTopology> | null;
  if (!parsed || typeof parsed !== 'object') return emptyFlowTopology();
  const customNodes = (Array.isArray(parsed.customNodes) ? parsed.customNodes : [])
    .filter((node): node is FlowTopologyCustomNode => {
      if (!node || typeof node !== 'object') return false;
      const candidate = node as Partial<FlowTopologyCustomNode>;
      return (
        typeof candidate.id === 'string'
        && (candidate.type === 'analysis' || candidate.type === 'content')
        && Boolean(candidate.position)
        && typeof candidate.position!.x === 'number'
        && typeof candidate.position!.y === 'number'
      );
    })
    .slice(0, MAX_CUSTOM_NODES)
    .map((node) => ({ ...node, config: node.config && typeof node.config === 'object' ? node.config : {} }));
  const nodeIds = new Set(customNodes.map((node) => node.id));
  const isKnownEndpoint = (id: unknown): id is string =>
    typeof id === 'string'
    && (NODE_DEFINITIONS.some((definition) => definition.id === id)
      || ALL_PLATFORM_IDS.includes(id.replace(/^platform-/, ''))
      || nodeIds.has(id));
  const customEdges = (Array.isArray(parsed.customEdges) ? parsed.customEdges : [])
    .filter((edge): edge is FlowTopologyCustomEdge => {
      if (!edge || typeof edge !== 'object') return false;
      const candidate = edge as Partial<FlowTopologyCustomEdge>;
      return (
        typeof candidate.id === 'string'
        && isKnownEndpoint(candidate.source)
        && isKnownEndpoint(candidate.target)
        && candidate.source !== candidate.target
      );
    });
  const removedEdgeIds = (Array.isArray(parsed.removedEdgeIds) ? parsed.removedEdgeIds : [])
    .filter((id): id is string => typeof id === 'string' && EDGE_DEFS.some((definition) => definition.id === id));
  return { version: 1, customNodes, customEdges, removedEdgeIds };
}

function readFlowTopology(entityId: string): FlowTopology {
  if (typeof window === 'undefined') return emptyFlowTopology();
  try {
    const raw = window.localStorage.getItem(TOPOLOGY_STORAGE_PREFIX + entityId);
    if (!raw) return emptyFlowTopology();
    return parseFlowTopology(JSON.parse(raw));
  } catch {
    return emptyFlowTopology();
  }
}

function writeFlowTopology(entityId: string, topology: FlowTopology): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(TOPOLOGY_STORAGE_PREFIX + entityId, JSON.stringify(topology));
  } catch {
    // 忽略持久化失败
  }
}

function clearFlowTopology(entityId: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(TOPOLOGY_STORAGE_PREFIX + entityId);
  } catch {
    // 忽略
  }
}

function layoutStorageKey(entityId: string, centerTerm: string): string {
  return `amway-flow-layout:${entityId}:${centerTerm}`;
}

function readStoredPositions(entityId: string, centerTerm: string): Record<string, { x: number; y: number }> {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(layoutStorageKey(entityId, centerTerm));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, { x: number; y: number }>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function flowNodeIcon(icon: string) {
  const props = { size: 15, 'aria-hidden': true as const };
  switch (icon) {
    case 'list':
      return <ListChecks {...props} />;
    case 'database':
      return <Database {...props} />;
    case 'workflow':
      return <Workflow {...props} />;
    case 'scan':
      return <ScanSearch {...props} />;
    case 'orbit':
      return <Orbit {...props} />;
    case 'file':
      return <FileText {...props} />;
    case 'chart':
      return <ChartNoAxesColumn {...props} />;
    case 'pen':
      return <PenLine {...props} />;
    default:
      return <Workflow {...props} />;
  }
}

/** 节点图标底色：资产=品牌色，数据分析=紫色系，内容创作=橙色系，其余中性。 */
function iconBadgeClass(variant: AmwayFlowNodeData['variant']): string {
  switch (variant) {
    case 'asset':
      return 'bg-[var(--brand-bg)] text-[var(--brand-primary)]';
    case 'analysis':
      return 'bg-[rgba(139,92,246,0.14)] text-[rgb(124,58,237)] dark:text-[rgb(167,139,250)]';
    case 'content':
      return 'bg-[rgba(249,115,22,0.14)] text-[rgb(234,88,12)] dark:text-[rgb(251,146,60)]';
    default:
      return 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

function statusDotClass(status: FlowNodeStatus): string {
  switch (status) {
    case 'active':
      return 'bg-[var(--brand-primary)] amway-flow-node-pulse';
    case 'done':
      return 'bg-[var(--brand-primary)]';
    case 'failed':
      return 'bg-[var(--error)]';
    case 'skipped':
      return 'bg-[var(--text-tertiary)] opacity-50';
    default:
      return 'bg-[var(--border-strong)]';
  }
}

function statusBarClass(status: FlowNodeStatus): string {
  switch (status) {
    case 'active':
      return 'bg-[var(--brand-primary)]';
    case 'done':
      return 'bg-[var(--brand-primary)] opacity-60';
    case 'failed':
      return 'bg-[var(--error)]';
    case 'skipped':
      return 'bg-[var(--text-tertiary)] opacity-40';
    default:
      return 'bg-transparent';
  }
}

function AmwayFlowNodeCard({ id, data, selected }: NodeProps<AmwayFlowNode>) {
  const isPlatform = data.variant === 'platform';
  const disabled = data.enabled === false;
  const skipped = data.status === 'skipped';
  const plannedIdle = data.status === 'idle' && Boolean(data.planned);
  return (
    <div
      className={`group relative rounded-xl border bg-[var(--bg-primary)] text-left shadow-sm transition-all duration-150 hover:-translate-y-px hover:shadow-md ${
        selected
          ? 'border-[var(--brand-primary)]'
          : plannedIdle
            ? 'border-[var(--brand-primary)]/45 hover:border-[var(--brand-primary)]'
            : 'border-[var(--border-subtle)] hover:border-[var(--border-strong)]'
      } ${isPlatform ? 'w-[148px] px-3 py-2' : 'w-[208px] px-3.5 py-3'} ${disabled || skipped ? 'opacity-45' : ''}`}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0 !bg-[var(--border-strong)]" />
      <span
        aria-hidden="true"
        className={`absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-full ${statusBarClass(data.status)}`}
      />
      {data.status === 'done' && !isPlatform ? (
        <CheckCircle2
          size={14}
          aria-hidden="true"
          className="absolute -right-1.5 -top-1.5 rounded-full bg-[var(--bg-primary)] text-[var(--brand-primary)]"
        />
      ) : null}
      <div className="flex items-center gap-2">
        <span
          className={`flex shrink-0 items-center justify-center rounded-lg ${
            iconBadgeClass(data.variant)
          } ${isPlatform ? '!h-5 !w-5' : 'h-7 w-7'}`}
        >
          {flowNodeIcon(data.icon)}
        </span>
        <div className="min-w-0 flex-1">
          <div className={`font-semibold text-[var(--text-primary)] ${isPlatform ? 'text-xs' : 'text-sm'}`}>
            {data.label}
          </div>
          {!isPlatform && data.subtitle ? (
            <div className="mt-0.5 truncate text-[11px] tabular-nums text-[var(--text-tertiary)]">{data.subtitle}</div>
          ) : null}
        </div>
        {isPlatform && data.onToggle ? (
          <button
            type="button"
            role="switch"
            aria-checked={!disabled}
            aria-label={`${data.label} 采集开关`}
            title={disabled ? '已停用，下一轮不采集该平台' : '已启用'}
            onClick={(event) => {
              event.stopPropagation();
              data.onToggle?.(id);
            }}
            className={`relative h-4 w-7 shrink-0 rounded-full transition-colors ${
              disabled ? 'bg-[var(--border-strong)]' : 'bg-[var(--brand-primary)]'
            }`}
          >
            <span
              className={`absolute top-0.5 h-3 w-3 rounded-full bg-white shadow transition-all ${
                disabled ? 'left-0.5' : 'left-3.5'
              }`}
            />
          </button>
        ) : (
          <span className={`h-2 w-2 shrink-0 rounded-full ${statusDotClass(data.status)}`} title={STATUS_TEXT[data.status]} />
        )}
      </div>
      {!isPlatform && data.outputs.length ? (
        <div className="mt-2 flex flex-wrap gap-1">
          {data.outputs.map((output) => (
            <button
              key={output.key}
              type="button"
              disabled={output.disabled}
              onClick={(event) => {
                event.stopPropagation();
                data.onOutput?.(id, output.key);
              }}
              className="rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2 py-0.5 text-[10px] font-medium text-[var(--text-secondary)] transition-all hover:scale-105 hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 disabled:hover:border-[var(--border-subtle)] disabled:hover:text-[var(--text-secondary)]"
            >
              {output.label}
              {typeof output.count === 'number' && output.count > 0 ? ` ${output.count}` : ''}
            </button>
          ))}
        </div>
      ) : null}
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0 !bg-[var(--border-strong)]" />
    </div>
  );
}

const nodeTypes = { amway: AmwayFlowNodeCard };

function buildDefaultPositions(): Record<string, { x: number; y: number }> {
  const positions: Record<string, { x: number; y: number }> = {};
  NODE_DEFINITIONS.forEach((definition) => {
    positions[definition.id] = definition.position;
  });
  PLATFORM_META.forEach((platform, index) => {
    positions[`platform-${platform.id}`] = PLATFORM_POSITIONS[index] || { x: 660, y: index * 80 };
  });
  return positions;
}

const EDGE_DEFS: Array<{ id: string; source: string; target: string }> = [
  { id: 'e-questions-fetch', source: 'question-set', target: 'fetch' },
  { id: 'e-lexicon-extract', source: 'lexicon', target: 'extract' },
  { id: 'e-fetch-extract', source: 'fetch', target: 'extract' },
  { id: 'e-extract-projection', source: 'extract', target: 'projection' },
  { id: 'e-projection-report', source: 'projection', target: 'report' },
  ...PLATFORM_META.map((platform) => ({
    id: `e-fetch-${platform.id}`,
    source: 'fetch',
    target: `platform-${platform.id}`,
  })),
];

// ===== Phase 3a 连线改接：端口类型系统 + DAG 环校验 =====
// 产出物类型：连线只能从"输出类型"连到"接受该类型"的输入端口。
const BUILTIN_OUTPUT_TYPE: Record<string, string> = {
  'question-set': 'questions',
  lexicon: 'lexicon',
  fetch: 'answers',
  extract: 'entities',
  projection: 'circle',
  report: 'report',
};

const BUILTIN_ACCEPTED_INPUTS: Record<string, string[]> = {
  fetch: ['questions'],
  extract: ['lexicon', 'answers'],
  projection: ['entities'],
  report: ['circle'],
};

const CUSTOM_NODE_OUTPUT_TYPE: Record<CustomFlowNodeType, string> = {
  analysis: 'analysis',
  content: 'content',
};

const CUSTOM_NODE_ACCEPTED_INPUTS: Record<CustomFlowNodeType, string[]> = {
  analysis: ['circle', 'report'],
  content: ['lexicon', 'analysis'],
};

// ===== Phase 3a 数据分析节点：确定性分析（基于当前 projection，零后端改动）=====
// 设计文档原计划"调现有 report API 做 LLM 二级解读"，但现有 report API 只产出整份标准报告，
// 没有自定义 prompt 的二级解读接口；3a 先用确定性数据分析真跑，LLM 解读归入 3b。
type FlowAnalysisDimension = 'platform' | 'entities' | 'risk';

const ANALYSIS_DIMENSION_META: Record<FlowAnalysisDimension, { label: string; hint: string }> = {
  platform: { label: '平台覆盖', hint: '各平台有效回答与请求覆盖对比' },
  entities: { label: '高频实体', hint: '按回答数排序的实体 Top 10 与轨道分布' },
  risk: { label: '风险信号', hint: '风险轨节点与监管相关信号汇总' },
};

const DEFAULT_ANALYSIS_DIMENSIONS: FlowAnalysisDimension[] = ['platform', 'entities', 'risk'];

type FlowAnalysisCard = { title: string; lines: string[] };

type FlowAnalysisResult = {
  generatedAt: string;
  dimensions: FlowAnalysisDimension[];
  cards: FlowAnalysisCard[];
  mode?: 'llm' | 'deterministic' | string;
  summary?: string;
  fallback_reason?: string;
};

type FlowContentResult = {
  generatedAt: string;
  mode?: 'llm' | 'template' | string;
  draft?: string;
  promptUsed?: string;
  fallback_reason?: string;
};

type ProjectionNodeLike = Record<string, unknown>;

function analysisNodeAnswerCount(node: ProjectionNodeLike): number {
  const value = Number(node.answer_count ?? node.mention_answer_count ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function runFlowAnalysis(
  dimensions: FlowAnalysisDimension[],
  projection: OntologyAssociationCircleProjection,
): FlowAnalysisResult {
  const cards: FlowAnalysisCard[] = [];
  const scope = (projection.sample_scope || {}) as Record<string, unknown>;
  const nodes = (projection.nodes || []) as unknown as ProjectionNodeLike[];

  if (dimensions.includes('platform')) {
    const validPlatforms = Array.isArray(scope.valid_platform_names) ? scope.valid_platform_names.map(String) : [];
    const requested = Array.isArray(scope.requested_platforms) ? scope.requested_platforms.map(String) : [];
    const missing = requested.filter((platform) => !validPlatforms.includes(platform));
    cards.push({
      title: '平台覆盖',
      lines: [
        `有效回答 ${Number(scope.valid_answer_count) || 0} 条，覆盖 ${validPlatforms.length}/${requested.length || validPlatforms.length} 个请求平台`,
        validPlatforms.length ? `产出平台：${validPlatforms.join('、')}` : '暂无有效产出平台',
        missing.length ? `未产出平台：${missing.join('、')}（建议下一轮重点观察）` : '请求平台全部有产出',
      ],
    });
  }

  if (dimensions.includes('entities')) {
    const sorted = [...nodes].sort((a, b) => analysisNodeAnswerCount(b) - analysisNodeAnswerCount(a));
    const top = sorted.slice(0, 10).filter((node) => analysisNodeAnswerCount(node) > 0);
    const byTrack = new Map<string, number>();
    nodes.forEach((node) => {
      const track = String(node.track || 'unknown');
      byTrack.set(track, (byTrack.get(track) || 0) + 1);
    });
    cards.push({
      title: '高频实体 Top 10',
      lines: [
        ...top.map((node, index) => `${index + 1}. ${String(node.term || node.node_id || '未命名')}（${analysisNodeAnswerCount(node)} 条回答）`),
        top.length ? '' : '暂无带回答计数的实体',
        `轨道分布：${Array.from(byTrack.entries()).map(([track, count]) => `${track} ${count}`).join(' / ') || '无'}`,
      ].filter(Boolean),
    });
  }

  if (dimensions.includes('risk')) {
    const riskNodes = nodes.filter((node) => String(node.track || '') === 'risk');
    const regulatory = nodes.filter((node) => {
      const text = `${String(node.term || '')} ${String(node.entity_type || '')}`;
      return text.includes('监管') || text.includes('合规');
    });
    const riskMap = ((projection as unknown as Record<string, unknown>).risk_map || {}) as Record<string, unknown>;
    cards.push({
      title: '风险信号',
      lines: [
        `风险轨节点 ${riskNodes.length} 个${riskNodes.length ? `：${riskNodes.slice(0, 5).map((node) => String(node.term || '')).filter(Boolean).join('、')}${riskNodes.length > 5 ? ' 等' : ''}` : ''}`,
        regulatory.length ? `监管/合规相关 ${regulatory.length} 个：${regulatory.slice(0, 3).map((node) => String(node.term || '')).filter(Boolean).join('、')}` : '未发现监管/合规相关节点',
        Object.keys(riskMap).length ? `风险地图字段：${Object.keys(riskMap).slice(0, 4).join('、')}` : '风险地图暂无数据',
      ],
    });
  }

  return {
    generatedAt: new Date().toISOString(),
    dimensions,
    cards,
  };
}

// 自定义节点类型学：视觉（紫色=数据分析 / 橙色=内容创作）+ 节点库展示信息
const CUSTOM_NODE_META: Record<CustomFlowNodeType, {
  label: string;
  icon: string;
  description: string;
  libraryHint: string;
}> = {
  analysis: {
    label: '数据分析',
    icon: 'chart',
    description: '接入圈层图或报告原文做二级解读，产出分析结论卡片。',
    libraryHint: '对圈层/报告做二级解读',
  },
  content: {
    label: '内容创作',
    icon: 'pen',
    description: '基于实体词库与分析结论起草内容文案。',
    libraryHint: '基于词库/分析起草文案',
  },
};

// 内容创作节点默认 prompt 模板（3a 占位：可编辑、可预览，执行能力规划中）
const DEFAULT_CONTENT_PROMPT_TEMPLATE = `你是一位熟悉 {{centerTerm}} 品牌的内容策划。
请基于以下输入起草一篇内容文案：
- 实体词库：{{entities}}
- 分析结论：{{analysis}}
要求：口吻自然、避免夸大宣传、符合广告法规范。`;

function customNodeTypeOf(topology: FlowTopology, nodeId: string): CustomFlowNodeType | null {
  return topology.customNodes.find((node) => node.id === nodeId)?.type || null;
}

function nodeOutputTypeOf(topology: FlowTopology, nodeId: string): string | null {
  const customType = customNodeTypeOf(topology, nodeId);
  if (customType) return CUSTOM_NODE_OUTPUT_TYPE[customType];
  return BUILTIN_OUTPUT_TYPE[nodeId] || null;
}

function nodeAcceptedInputsOf(topology: FlowTopology, nodeId: string): string[] {
  const customType = customNodeTypeOf(topology, nodeId);
  if (customType) return CUSTOM_NODE_ACCEPTED_INPUTS[customType];
  return BUILTIN_ACCEPTED_INPUTS[nodeId] || [];
}

/** 从 newTarget 沿现有连线出发能否到达 newSource（能则新连线会成环）。 */
function wouldCreateCycle(
  edges: Array<{ source: string; target: string }>,
  newSource: string,
  newTarget: string,
): boolean {
  const adjacency = new Map<string, string[]>();
  edges.forEach((edge) => {
    const list = adjacency.get(edge.source);
    if (list) list.push(edge.target);
    else adjacency.set(edge.source, [edge.target]);
  });
  const stack = [newTarget];
  const visited = new Set<string>();
  while (stack.length) {
    const current = stack.pop()!;
    if (current === newSource) return true;
    if (visited.has(current)) continue;
    visited.add(current);
    (adjacency.get(current) || []).forEach((next) => stack.push(next));
  }
  return false;
}

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
  liveStageResults = [],
  onQuickRun,
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
  liveStageResults?: StageResult[];
  onQuickRun: () => void;
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
  const [enabledPlatforms, setEnabledPlatforms] = useState<string[]>(() => readEnabledFlowPlatforms(entityId));
  // Phase 3a 自定义拓扑（视图层编排）。3b-1.4 起后端为权威存储，
  // localStorage 降级为首帧缓存与离线回退。
  const [topology, setTopology] = useState<FlowTopology>(() => readFlowTopology(entityId));
  // 不变式：传给 updateTopology 的 updater 必须是纯函数——React StrictMode（dev）
  // 会双跑 updater 检测纯度，含 Math.random/副作用会产生 state 与后端各存一份的分叉。
  // id 生成等不纯逻辑在调用处完成；持久化副作用统一收敛到下方 useEffect。
  const topologyDirtyRef = useRef(false);
  const updateTopology = useCallback(
    (updater: (current: FlowTopology) => FlowTopology) => {
      topologyDirtyRef.current = true;
      setTopology(updater);
    },
    [],
  );

  // 拓扑变化后统一持久化：localStorage 缓存 + 后端权威存储（fire-and-forget；
  // 失败时 localStorage 仍保有最新拓扑，下次挂载后端拉取失败回退到本地）
  useEffect(() => {
    if (!topologyDirtyRef.current) return;
    topologyDirtyRef.current = false;
    writeFlowTopology(entityId, topology);
    void api.putAmwayFlowTopology(entityId, topology).catch(() => undefined);
  }, [entityId, topology]);

  // 挂载后从后端拉取权威拓扑；与本地有差异时以后端为准并回写缓存
  useEffect(() => {
    let cancelled = false;
    void api.getAmwayFlowTopology(entityId)
      .then((resp) => {
        if (cancelled) return;
        const remote = parseFlowTopology(resp?.topology);
        setTopology((current) =>
          JSON.stringify(current) === JSON.stringify(remote) ? current : remote,
        );
        writeFlowTopology(entityId, remote);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [entityId]);
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
      if (running) return;
      const platformId = nodeId.replace(/^platform-/, '');
      setEnabledPlatforms((current) => {
        const next = current.includes(platformId)
          ? current.filter((id) => id !== platformId)
          : [...current, platformId];
        if (!next.length) return current;
        writeEnabledFlowPlatforms(entityId, next);
        return next;
      });
    },
    [entityId, running],
  );

  const nodeSubtitleMap = useMemo(() => {
    const fetching = running && stageCode.startsWith('A4');
    const analyzing = running && stageCode.startsWith('A5');
    const subtitles = new Map<string, string>();
    subtitles.set('question-set', questionBank.length ? `${questionBank.length} 题` : '系统默认问题集');
    subtitles.set('lexicon', '品牌实体识别范围');
    subtitles.set(
      'fetch',
      fetching
        ? progressMessage || '正在采集'
        : answerCount
          ? `${answerCount} 条回答`
          : `${enabledPlatforms.length}/${ALL_PLATFORM_IDS.length} 个平台`,
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
  const [customNodeError, setCustomNodeError] = useState<string | null>(null);

  // 3b-1.5 / 3b-1.6: analysis/content 真执行；cascade 跑下游分支。
  const runCustomNode = useCallback(
    async (nodeId: string, options?: { cascade?: boolean }) => {
      const customNode = topology.customNodes.find((node) => node.id === nodeId);
      if (!customNode || (customNode.type !== 'analysis' && customNode.type !== 'content')) return;
      setCustomNodeError(null);
      setRunningCustomNodeId(nodeId);
      try {
        await api.putAmwayFlowTopology(entityId, topology);
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
        topologyDirtyRef.current = true;
        setTopology(remote);
        writeFlowTopology(entityId, remote);
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
          setCustomNodeError(message);
        }
      } finally {
        setRunningCustomNodeId(null);
      }
    },
    [entityId, projection, projectionNodes.length, topology, updateCustomNodeConfig],
  );

  const runBranchFrom = useCallback(
    async (fromNodeId: string, mode: 'node_only' | 'downstream' = 'downstream') => {
      setCustomNodeError(null);
      setRunningCustomNodeId(fromNodeId);
      try {
        await api.putAmwayFlowTopology(entityId, topology);
        const resp = await api.runAmwayFlowBranch(entityId, {
          from_node_id: fromNodeId,
          mode,
        });
        const remote = parseFlowTopology(resp.topology);
        topologyDirtyRef.current = true;
        setTopology(remote);
        writeFlowTopology(entityId, remote);
      } catch (error) {
        const message = error instanceof Error ? error.message : '分支运行失败';
        setCustomNodeError(message);
      } finally {
        setRunningCustomNodeId(null);
      }
    },
    [entityId, topology],
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
              {running ? (
                <div className="inline-flex h-10 items-center gap-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 text-sm font-medium text-[var(--text-secondary)]">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-[var(--brand-primary)]" />
                  {progressMessage || '正在运行'}
                </div>
              ) : (
                <button
                  type="button"
                  onClick={onQuickRun}
                  className="amway-cta-glow inline-flex h-10 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)]"
                >
                  <Play size={14} fill="currentColor" aria-hidden />
                  开始运行
                </button>
              )}
            </div>
          </div>

          {/* 3b-2.1 执行计划投影：拓扑即计划 */}
          <div className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <Workflow size={14} className="text-[var(--brand-primary)]" aria-hidden />
                <span className="text-xs font-semibold text-[var(--text-primary)]">
                  {running ? '运行计划' : '本次执行计划'}
                </span>
                <span
                  className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                    executionPlan.source === 'run_flow_plan'
                      ? 'border-[var(--brand-primary)]/40 text-[var(--brand-primary)]'
                      : 'border-[var(--border-subtle)] text-[var(--text-tertiary)]'
                  }`}
                >
                  {executionPlan.source === 'run_flow_plan' ? '任务计划' : '拓扑预览'}
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
              {executionPlan.source === 'run_flow_plan'
                ? '任务启动时按当时拓扑锁定的执行计划；运行态会随 stage 推进高亮当前步骤。'
                : '计划由当前画布拓扑实时推导：断开连线或关闭平台会立刻反映在路径上。开始运行后将锁定为任务计划。'}
            </p>
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
                        running={runningCustomNodeId === customNode.id}
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
                  return (
                    <FlowNodeDetail
                      node={selectedNode}
                      activeRun={activeRun}
                      enabledPlatforms={enabledPlatforms}
                      questionSets={questionSets}
                      running={running}
                      branchRunning={runningCustomNodeId === selectedNode.id}
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

function nodeLabel(nodeId: string): string {
  if (nodeId.startsWith('platform-')) {
    const platform = PLATFORM_META.find((item) => `platform-${item.id}` === nodeId);
    return platform?.label || nodeId;
  }
  return NODE_DEFINITIONS.find((item) => item.id === nodeId)?.label || nodeId;
}

function artifactTitle(artifact: FlowArtifactKey): string {
  switch (artifact) {
    case 'questions':
      return '问题列表';
    case 'answers':
      return '答案原文';
    case 'entities':
      return '抽取实体';
    case 'report':
      return '报告原文';
    case 'lexicon':
      return '实体词库';
    case 'analysisResult':
      return '分析结论';
    case 'contentDraft':
      return '内容草稿';
    default:
      return '';
  }
}

function questionTextOf(record: Record<string, unknown>): string {
  return String(record.question_text || record.question || record.text || '').trim();
}

function CustomNodeDetail({
  node,
  customNode,
  running = false,
  error = null,
  onUpdateConfig,
  onDelete,
  onRunAnalysis,
  onRunAnalysisBranch,
  onRunContent,
  onOpenArtifact,
}: {
  node: AmwayFlowNode;
  customNode: FlowTopologyCustomNode;
  running?: boolean;
  error?: string | null;
  onUpdateConfig: (nodeId: string, patch: Record<string, unknown>) => void;
  onDelete: (nodeId: string) => void;
  onRunAnalysis: (nodeId: string) => void;
  onRunAnalysisBranch: (nodeId: string) => void;
  onRunContent: (nodeId: string) => void;
  onOpenArtifact: (key: FlowArtifactKey) => void;
}) {
  const isAnalysis = customNode.type === 'analysis';
  const result = customNode.config.result as FlowAnalysisResult | FlowContentResult | undefined;
  const analysisResult = isAnalysis ? (result as FlowAnalysisResult | undefined) : undefined;
  const contentResult = !isAnalysis ? (result as FlowContentResult | undefined) : undefined;
  const dimensions = (Array.isArray(customNode.config.dimensions)
    ? (customNode.config.dimensions as string[]).filter((item): item is FlowAnalysisDimension =>
        item === 'platform' || item === 'entities' || item === 'risk')
    : DEFAULT_ANALYSIS_DIMENSIONS);
  const template = String(customNode.config.promptTemplate || DEFAULT_CONTENT_PROMPT_TEMPLATE);
  void node;

  return (
    <div className="space-y-5">
      <p className="text-sm leading-6 text-[var(--text-secondary)]">{customNode.type === 'analysis' ? CUSTOM_NODE_META.analysis.description : CUSTOM_NODE_META.content.description}</p>

      <div>
        <label className="text-xs font-medium text-[var(--text-tertiary)]" htmlFor="custom-node-label">
          节点名称
        </label>
        <input
          id="custom-node-label"
          type="text"
          value={String(customNode.config.label || '')}
          placeholder={CUSTOM_NODE_META[customNode.type].label}
          onChange={(event) => onUpdateConfig(customNode.id, { label: event.target.value })}
          className="mt-1.5 h-9 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-sm text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
        />
      </div>

      {isAnalysis ? (
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">分析维度</div>
          <div className="mt-2 space-y-2">
            {(Object.keys(ANALYSIS_DIMENSION_META) as FlowAnalysisDimension[]).map((dimension) => {
              const meta = ANALYSIS_DIMENSION_META[dimension];
              const checked = dimensions.includes(dimension);
              return (
                <label
                  key={dimension}
                  className="flex cursor-pointer items-start gap-2.5 rounded-lg border border-[var(--border-subtle)] px-3 py-2 transition hover:border-[var(--border-strong)]"
                >
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() => {
                      const next = checked
                        ? dimensions.filter((item) => item !== dimension)
                        : [...dimensions, dimension];
                      onUpdateConfig(customNode.id, { dimensions: next });
                    }}
                    className="mt-0.5 accent-[var(--brand-primary)]"
                  />
                  <span>
                    <span className="block text-sm font-medium text-[var(--text-primary)]">{meta.label}</span>
                    <span className="block text-xs text-[var(--text-tertiary)]">{meta.hint}</span>
                  </span>
                </label>
              );
            })}
          </div>
          <label className="mt-3 block text-xs font-medium text-[var(--text-tertiary)]" htmlFor="analysis-prompt">
            二级解读 Prompt（可选）
          </label>
          <textarea
            id="analysis-prompt"
            value={String(customNode.config.prompt || '')}
            onChange={(event) => onUpdateConfig(customNode.id, { prompt: event.target.value })}
            rows={3}
            placeholder="例如：重点对比竞品与风险信号，给出三条可执行建议"
            className="mt-1.5 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={running}
              onClick={() => onRunAnalysis(customNode.id)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
            >
              <Play size={13} fill="currentColor" aria-hidden />
              {running ? '运行中…' : '仅运行此节点'}
            </button>
            <button
              type="button"
              disabled={running}
              onClick={() => onRunAnalysisBranch(customNode.id)}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--border-strong)] bg-[var(--bg-primary)] px-3.5 text-sm font-medium text-[var(--text-primary)] transition hover:bg-[var(--bg-secondary)] disabled:opacity-60"
            >
              <Workflow size={13} aria-hidden />
              运行此分支
            </button>
          </div>
          <p className="mt-1.5 text-xs text-[var(--text-tertiary)]">
            「运行此分支」会连同下游已接线的内容创作节点一起执行。
          </p>
          {analysisResult ? (
            <button
              type="button"
              onClick={() => onOpenArtifact('analysisResult')}
              className="mt-2 block text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              查看分析结论（{new Date(analysisResult.generatedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {analysisResult.mode ? ` · ${analysisResult.mode === 'llm' ? 'LLM' : '确定性'}` : ''}）
            </button>
          ) : null}
        </div>
      ) : (
        <div>
          <label className="text-xs font-medium text-[var(--text-tertiary)]" htmlFor="custom-node-template">
            Prompt 模板
          </label>
          <textarea
            id="custom-node-template"
            value={template}
            onChange={(event) => onUpdateConfig(customNode.id, { promptTemplate: event.target.value })}
            rows={7}
            className="mt-1.5 w-full rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2 text-[13px] leading-5 text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)]"
          />
          <p className="mt-1.5 text-xs leading-5 text-[var(--text-tertiary)]">
            可用变量：{'{{centerTerm}}'}（品牌）、{'{{entities}}'}（实体词库）、{'{{analysis}}'}（分析结论）。
          </p>
          <button
            type="button"
            disabled={running}
            onClick={() => onRunContent(customNode.id)}
            className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
          >
            <Play size={13} fill="currentColor" aria-hidden />
            {running ? '生成中…' : '生成草稿'}
          </button>
          {contentResult?.draft ? (
            <button
              type="button"
              onClick={() => onOpenArtifact('contentDraft')}
              className="mt-2 block text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              查看内容草稿（{new Date(contentResult.generatedAt).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
              {contentResult.mode ? ` · ${contentResult.mode === 'llm' ? 'LLM' : '模板'}` : ''}）
            </button>
          ) : null}
        </div>
      )}

      {error ? (
        <p className="rounded-lg border border-[rgba(220,38,38,0.25)] bg-[rgba(220,38,38,0.06)] px-3 py-2 text-xs leading-5 text-[var(--error)]">
          {error}
        </p>
      ) : null}

      <div className="border-t border-[var(--border-subtle)] pt-4">
        <button
          type="button"
          onClick={() => onDelete(customNode.id)}
          className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--error)] px-3.5 text-sm font-medium text-[var(--error)] transition hover:bg-[rgba(220,38,38,0.06)]"
        >
          <X size={13} aria-hidden />
          删除节点
        </button>
        <p className="mt-1.5 text-xs text-[var(--text-tertiary)]">删除后与其相连的自定义连线会一并移除。</p>
      </div>
    </div>
  );
}

function AnalysisResultArtifact({ result }: { result: FlowAnalysisResult }) {
  const modeLabel = result.mode === 'llm' ? 'LLM 二级解读' : '确定性分析';
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-tertiary)]">
        生成于 {new Date(result.generatedAt).toLocaleString('zh-CN')}
        ，模式：{modeLabel}
        {result.fallback_reason ? `（降级：${result.fallback_reason}）` : ''}
      </p>
      {result.summary ? (
        <p className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
          {result.summary}
        </p>
      ) : null}
      {result.cards.map((card) => (
        <section key={card.title} className="rounded-xl border border-[var(--border-subtle)] px-4 py-3">
          <h3 className="text-sm font-semibold text-[var(--text-primary)]">{card.title}</h3>
          <ul className="mt-2 space-y-1.5">
            {card.lines.map((line, index) => (
              <li key={index} className="text-[13px] leading-5 text-[var(--text-secondary)]">
                {line}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function ContentDraftArtifact({
  result,
  template,
}: {
  result?: FlowContentResult;
  template: string;
}) {
  const draft = String(result?.draft || '').trim();
  const modeLabel = result?.mode === 'llm' ? 'LLM 生成' : '模板回填';
  return (
    <div className="space-y-4">
      <p className="text-xs text-[var(--text-tertiary)]">
        {result?.generatedAt
          ? `生成于 ${new Date(result.generatedAt).toLocaleString('zh-CN')}，模式：${modeLabel}`
          : '尚未生成草稿'}
        {result?.fallback_reason ? `（降级：${result.fallback_reason}）` : ''}
      </p>
      <pre className="whitespace-pre-wrap rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
        {draft || '（空草稿）'}
      </pre>
      {result?.mode === 'template' || !draft ? (
        <details className="rounded-lg border border-[var(--border-subtle)] px-3 py-2">
          <summary className="cursor-pointer text-xs font-medium text-[var(--text-secondary)]">查看 Prompt 模板</summary>
          <pre className="mt-2 whitespace-pre-wrap text-[12px] leading-5 text-[var(--text-tertiary)]">{template}</pre>
        </details>
      ) : null}
    </div>
  );
}

function FlowNodeDetail({
  node,
  activeRun,
  enabledPlatforms,
  questionSets,
  running,
  branchRunning = false,
  branchError = null,
  onRetry,
  onOpenRunSettings,
  onOpenArtifact,
  onOpenCircle,
  onRunDownstreamBranch,
}: {
  node: AmwayFlowNode;
  activeRun?: BrandIntelligenceRun | null;
  enabledPlatforms: string[];
  questionSets: AmwayQuestionHistorySet[];
  running: boolean;
  branchRunning?: boolean;
  branchError?: string | null;
  onRetry: () => void;
  onOpenRunSettings: () => void;
  onOpenArtifact: (key: FlowArtifactKey) => void;
  onOpenCircle: () => void;
  onRunDownstreamBranch?: () => void;
}) {
  const inputScope = (activeRun?.input_scope || {}) as Record<string, unknown>;
  const boundSetId = typeof inputScope.uploaded_question_set_id === 'string' ? inputScope.uploaded_question_set_id : null;
  const boundSet = boundSetId ? questionSets.find((item) => item.id === boundSetId) || null : null;
  const boundSource = typeof inputScope.uploaded_question_source === 'string' ? inputScope.uploaded_question_source : null;
  const fetchModeLabel = inputScope.fetch_mode === 'fast' ? 'API 采集' : '浏览器采集';
  const previewQuestions = (boundSet?.questions || []).slice(0, 3);

  return (
    <div className="space-y-4">
      <p className="text-sm leading-6 text-[var(--text-secondary)]">{node.data.description}</p>

      {onRunDownstreamBranch ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">局部运行</div>
          <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            不重跑采集，仅执行从此节点连出的数据分析 / 内容创作自定义分支。
          </p>
          <button
            type="button"
            disabled={branchRunning || running}
            onClick={onRunDownstreamBranch}
            className="mt-3 inline-flex h-9 items-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3.5 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
          >
            <Workflow size={13} aria-hidden />
            {branchRunning ? '分支运行中…' : '运行下游自定义节点'}
          </button>
          {branchError ? (
            <p className="mt-2 text-xs leading-5 text-[var(--error)]">{branchError}</p>
          ) : null}
        </section>
      ) : null}

      {node.id === 'question-set' ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">当前绑定</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">
            {boundSet
              ? `${boundSet.title}（${boundSet.question_count} 题）`
              : boundSource
                ? `${boundSource}${typeof inputScope.uploaded_question_count === 'number' ? `（${inputScope.uploaded_question_count} 题）` : ''}`
                : '系统默认问题集'}
          </div>
          {previewQuestions.length ? (
            <ol className="mt-2 space-y-1 text-xs leading-5 text-[var(--text-secondary)]">
              {previewQuestions.map((question, index) => (
                <li key={index} className="truncate">
                  <span className="mr-1.5 tabular-nums text-[var(--text-tertiary)]">{index + 1}.</span>
                  {questionTextOf(question) || '（未命名问题）'}
                </li>
              ))}
            </ol>
          ) : null}
          <button
            type="button"
            onClick={onOpenRunSettings}
            className="mt-3 inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--brand-primary)] transition hover:border-[var(--brand-primary)]"
          >
            更换问题集
          </button>
        </section>
      ) : null}

      {node.id === 'fetch' ? (
        <section className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3.5 py-3">
          <div className="text-xs font-medium text-[var(--text-tertiary)]">采集配置</div>
          <div className="mt-1 text-sm font-semibold text-[var(--text-primary)]">{fetchModeLabel}</div>
          <div className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">
            平台通道：{enabledPlatforms.length}/{ALL_PLATFORM_IDS.length} 启用
            {enabledPlatforms.length < ALL_PLATFORM_IDS.length
              ? `（已停用 ${ALL_PLATFORM_IDS.filter((id) => !enabledPlatforms.includes(id)).map((id) => PLATFORM_META.find((item) => item.id === id)?.label || id).join('、')}）`
              : ''}
          </div>
          <button
            type="button"
            onClick={onOpenRunSettings}
            className="mt-3 inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--brand-primary)] transition hover:border-[var(--brand-primary)]"
          >
            调整采集方式
          </button>
        </section>
      ) : null}

      {node.id === 'lexicon' ? (
        <button
          type="button"
          onClick={onOpenCircle}
          className="inline-flex h-9 items-center rounded-lg border border-[var(--border-subtle)] px-3 text-xs font-medium text-[var(--brand-primary)] hover:bg-[var(--brand-bg)]"
        >
          在品牌圈层页管理词库
        </button>
      ) : null}

      {node.data.outputs.length ? (
        <div>
          <div className="text-xs font-medium text-[var(--text-tertiary)]">节点产出</div>
          <div className="mt-2 space-y-1.5">
            {node.data.outputs.map((output) => (
              <button
                key={output.key}
                type="button"
                disabled={output.disabled}
                onClick={() => onOpenArtifact(output.key)}
                className="flex w-full items-center justify-between rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-left text-sm text-[var(--text-primary)] transition hover:border-[var(--brand-primary)] disabled:cursor-not-allowed disabled:opacity-40"
              >
                <span>{output.label}</span>
                {typeof output.count === 'number' && output.count > 0 ? (
                  <span className="text-xs tabular-nums text-[var(--text-tertiary)]">{output.count}</span>
                ) : null}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {node.data.status === 'failed' && !running ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-4 text-sm font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)]"
        >
          <RotateCcw size={14} aria-hidden />
          重新运行
        </button>
      ) : null}
    </div>
  );
}

function ArtifactEmpty({ text }: { text: string }) {
  return <div className="py-10 text-center text-sm text-[var(--text-tertiary)]">{text}</div>;
}

function QuestionsArtifact({
  questions,
}: {
  questions: OntologyAssociationCircleProjection['question_bank'];
}) {
  const list = (questions || []).slice(0, 120);
  if (!list.length) {
    return <ArtifactEmpty text="本轮问题列表会在运行后显示在这里。" />;
  }
  return (
    <ol className="space-y-2">
      {list.map((question, index) => (
        <li
          key={question.id || index}
          className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm leading-6 text-[var(--text-primary)]"
        >
          <span className="mr-2 text-xs tabular-nums text-[var(--text-tertiary)]">{index + 1}.</span>
          {question.question_text || question.question || question.text || '（未命名问题）'}
        </li>
      ))}
    </ol>
  );
}

function AnswersArtifact({
  appendix,
  fallback,
}: {
  appendix: OntologyAssociationCircleProjection['source_appendix'];
  fallback: OntologyAssociationCircleProjection['evidence_samples'];
}) {
  const groups = useMemo(() => {
    const byPlatform = new Map<string, Array<{ question: string; excerpt: string }>>();
    const push = (platform: unknown, question: unknown, excerpt: unknown) => {
      const platformLabel = String(platform || '未知平台');
      const text = String(excerpt || '').trim();
      if (!text) return;
      const list = byPlatform.get(platformLabel) || [];
      if (list.length < 40) {
        list.push({ question: String(question || '').trim(), excerpt: text });
      }
      byPlatform.set(platformLabel, list);
    };
    (appendix || []).forEach((item) => push(item.platform, item.question, item.answer_excerpt));
    if (!byPlatform.size) {
      (fallback || []).forEach((item) => push(item.platform, item.question, item.answer_excerpt));
    }
    return Array.from(byPlatform.entries());
  }, [appendix, fallback]);

  if (!groups.length) {
    return <ArtifactEmpty text="答案原文会在采集完成后显示在这里。" />;
  }
  return (
    <div className="space-y-5">
      {groups.map(([platform, items]) => (
        <section key={platform}>
          <h3 className="text-xs font-semibold text-[var(--text-tertiary)]">
            {platform} · {items.length} 条
          </h3>
          <div className="mt-2 space-y-2">
            {items.map((item, index) => (
              <details
                key={index}
                className="rounded-lg border border-[var(--border-subtle)] px-3 py-2 text-sm"
              >
                <summary className="cursor-pointer font-medium leading-6 text-[var(--text-primary)]">
                  {item.question || `回答 ${index + 1}`}
                </summary>
                <p className="mt-2 whitespace-pre-wrap text-[13px] leading-6 text-[var(--text-secondary)]">
                  {item.excerpt}
                </p>
              </details>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function EntitiesArtifact({
  nodes,
}: {
  nodes: OntologyAssociationCircleProjection['nodes'];
}) {
  const list = useMemo(() => {
    return [...(nodes || [])]
      .sort((a, b) => Number(b.answer_count || 0) - Number(a.answer_count || 0))
      .slice(0, 100);
  }, [nodes]);
  if (!list.length) {
    return <ArtifactEmpty text="抽取出的实体会在这里列出。" />;
  }
  return (
    <div className="overflow-hidden rounded-lg border border-[var(--border-subtle)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--bg-secondary)] text-left text-xs text-[var(--text-tertiary)]">
            <th className="px-3 py-2 font-medium">实体</th>
            <th className="px-3 py-2 font-medium">类型</th>
            <th className="px-3 py-2 text-right font-medium">提及回答</th>
          </tr>
        </thead>
        <tbody>
          {list.map((node) => (
            <tr key={node.node_id} className="border-t border-[var(--border-subtle)]">
              <td className="px-3 py-2 text-[var(--text-primary)]">{node.term}</td>
              <td className="px-3 py-2 text-xs text-[var(--text-tertiary)]">{node.entity_type}</td>
              <td className="px-3 py-2 text-right tabular-nums text-[var(--text-secondary)]">
                {node.answer_count || 0}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
