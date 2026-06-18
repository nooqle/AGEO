import type { LucideIcon } from 'lucide-react';

export type BrandSpaceView = 'graph' | 'boards' | 'assets' | 'reports';

export type BoardRunStatus =
  | 'idle'
  | 'running'
  | 'pause_requested'
  | 'paused'
  | 'stopped'
  | 'completed'
  | 'failed';

export type NodeStatus =
  | 'idle'
  | 'queued'
  | 'running'
  | 'paused'
  | 'completed'
  | 'needs_review'
  | 'failed';

export type NodeKind =
  | 'input'
  | 'prepare'
  | 'fetch'
  | 'extract'
  | 'review'
  | 'graph_update';

export type InspectorTab = 'overview' | 'events' | 'output' | 'config';

export type GraphPatchStatus =
  | 'auto_applied'
  | 'needs_review'
  | 'accepted'
  | 'rejected'
  | 'blocked';

export type GraphZone =
  | 'center'
  | 'inner'
  | 'middle'
  | 'outer'
  | 'risk'
  | 'competitor'
  | 'pending_review';

export type GuardrailSeverity = 'pass' | 'warn' | 'block';

export interface BrandSpaceNavItem {
  id: BrandSpaceView;
  label: string;
  description: string;
  icon: LucideIcon;
}

export interface BrandSpaceContext {
  brandName: string;
  graphVersion: string;
  boardName: string;
  runId: string;
  startedAt: string;
  duration: string;
}

export interface ArtifactRef {
  id: string;
  type: string;
  label: string;
  path: string;
  rowCount?: number;
  createdAt: string;
  linkedNodeId?: string;
}

export interface RuntimeEvent {
  id: string;
  timestamp: string;
  type: string;
  severity: 'info' | 'success' | 'warning' | 'risk';
  message: string;
  nodeId?: string;
  payload?: Record<string, unknown>;
}

export interface BoardNode {
  id: string;
  title: string;
  subtitle: string;
  kind: NodeKind;
  status: NodeStatus;
  progress: number;
  position: {
    x: number;
    y: number;
  };
  metrics: Array<{
    label: string;
    value: string;
  }>;
  outputArtifactIds: string[];
}

export interface PlatformFetchNode {
  id: string;
  platformKey: 'chatgpt' | 'doubao' | 'kimi' | 'deepseek';
  label: string;
  model: string;
  status: NodeStatus;
  progress: number;
  answers: number;
  failures: number;
}

export interface BoardEdge {
  id: string;
  from: string;
  to: string;
  active?: boolean;
  dashed?: boolean;
}

export interface GraphEntity {
  id: string;
  label: string;
  zone: GraphZone;
  x: number;
  y: number;
  strength: number;
  evidenceCount: number;
}

export interface GraphRelation {
  id: string;
  from: string;
  to: string;
  kind: string;
  strength: number;
}

export interface EvidenceRef {
  id: string;
  question: string;
  platform: string;
  excerpt: string;
  polarity: 'positive' | 'neutral' | 'questioning' | 'negative';
}

export interface GraphPatch {
  id: string;
  title: string;
  description: string;
  status: GraphPatchStatus;
  patchType: string;
  score: number;
  evidenceRefIds: string[];
  affectedEntityId?: string;
  evidenceRefs?: EvidenceRef[];
  confidence?: number | null;
  sentimentOrRiskScore?: number | null;
}

export interface ReportGuardrailResult {
  id: string;
  severity: GuardrailSeverity;
  title: string;
  message: string;
}

export interface TraceStep {
  id: string;
  label: string;
  value: string;
}

export interface BrandSpaceBoardRun {
  id: string;
  entity_id: string;
  brand_intelligence_run_id?: string | null;
  analysis_task_id?: string | null;
  board_id: string;
  template_id: string;
  status: BoardRunStatus;
  progress: number;
  summary: string;
  input_scope?: Record<string, unknown> | null;
  active_node_ids: string[];
  output_refs: Record<string, unknown>;
  started_at?: string | null;
  completed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BrandSpaceGraph {
  entities: GraphEntity[];
  relations: GraphRelation[];
  evidenceRefs: EvidenceRef[];
}

export interface BrandSpaceGraphUpdate {
  id: string;
  entity_id: string;
  board_run_id?: string | null;
  before_graph_version: string;
  after_graph_version: string;
  status: string;
  summary: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface BrandSpaceReport {
  id: string;
  report_id: string;
  version: number;
  report_kind: string;
  artifact_id: string;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface BrandSpacePayload {
  context: BrandSpaceContext;
  run: BrandSpaceBoardRun | null;
  nodes: BoardNode[];
  edges: BoardEdge[];
  platforms: PlatformFetchNode[];
  artifacts: ArtifactRef[];
  events: RuntimeEvent[];
  graph: BrandSpaceGraph;
  graph_update: BrandSpaceGraphUpdate | null;
  patches: GraphPatch[];
  guardrails: ReportGuardrailResult[];
  report?: BrandSpaceReport | null;
}

export interface CreateBrandSpaceBoardRunInput {
  board_id?: string;
  template_id?: string;
  input_scope?: Record<string, unknown> | null;
  auto_dispatch?: boolean;
}
