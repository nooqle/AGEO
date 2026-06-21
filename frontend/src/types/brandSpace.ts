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
  artifactId?: string;
  entityId?: string;
  boardRunId?: string;
  nodeRunId?: string | null;
  type: string;
  label: string;
  path: string;
  mimeType?: string;
  rowCount?: number;
  createdAt: string;
  linkedNodeId?: string;
  metadata?: Record<string, unknown>;
}

export interface PaginationInfo {
  limit: number;
  offset: number;
  total: number;
  has_more: boolean;
}

export interface AssetListSummary {
  total: number;
  returned: number;
  by_type: Record<string, number>;
}

export interface ArtifactPreview {
  kind: 'json' | 'jsonl' | 'table' | 'summary';
  title: string;
  rowCount?: number;
  truncated?: boolean;
  columns?: Array<{ key: string; label: string }>;
  rows?: Array<Record<string, unknown>>;
  lines?: string[];
  json?: Record<string, unknown> | null;
  summary?: string;
  items?: Array<{ label: string; value: unknown }>;
  emptySummary?: string;
}

export interface ArtifactTraceLink {
  kind: 'board_run' | 'node_run' | 'graph_update' | 'report_version' | string;
  id: string;
  label: string;
  targetView?: BrandSpaceView;
  nodeId?: string;
  reportVersionId?: string;
}

export interface ArtifactAccess {
  canPreview: boolean;
  mode?: string;
  provider?: 'local' | string;
  objectKey?: string | null;
  available?: boolean;
  downloadUrl?: string | null;
  filename?: string | null;
  sizeBytes?: number | null;
  reason?: string | null;
}

export interface ArtifactDetail {
  artifact: ArtifactRef;
  preview: ArtifactPreview;
  trace: {
    links: ArtifactTraceLink[];
    boardRun?: BrandSpaceBoardRun;
    nodeRun?: BoardNode | null;
    graphUpdate?: BrandSpaceGraphUpdate | null;
    report?: BrandSpaceReportSummary | null;
  };
  access?: ArtifactAccess;
}

export interface RuntimeEvent {
  id: string;
  sequence?: number | null;
  timestamp: string;
  type: string;
  severity: 'info' | 'success' | 'warning' | 'risk' | 'error';
  message: string;
  nodeId?: string;
  payload?: Record<string, unknown>;
}

export interface RuntimeEventCursor {
  after_sequence?: number | null;
  next_sequence: number;
  has_more: boolean;
}

export interface RuntimeEventPagination {
  limit: number;
  offset: number;
  total: number | null;
  has_more: boolean;
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
  patchId?: string;
  patchStatus?: GraphPatchStatus;
  patchType?: string;
  category?: string;
  priority?: string;
}

export interface GraphRelation {
  id: string;
  from: string;
  to: string;
  kind: string;
  strength: number;
  patchId?: string;
  patchStatus?: GraphPatchStatus;
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
  graphUpdateId?: string;
  title: string;
  description: string;
  status: GraphPatchStatus;
  patchType: string;
  relationType?: string;
  score: number;
  evidenceRefIds: string[];
  affectedEntityId?: string;
  affectedObjectType?: string;
  affectedObjectId?: string;
  evidenceRefs?: EvidenceRef[];
  confidence?: number | null;
  sentimentOrRiskScore?: number | null;
  category?: string;
  priority?: 'high' | 'medium' | 'low' | string;
  reviewReason?: string | null;
  reviewedByUserId?: string | null;
  reviewedAt?: string | null;
  suggestedAction?: string;
  createdAt?: string;
  updatedAt?: string;
}

export interface GraphReviewItem extends GraphPatch {
  graphUpdateId: string;
  graphUpdateStatus: string;
  boardRunId?: string | null;
  beforeGraphVersion: string;
  afterGraphVersion: string;
  graphUpdateCreatedAt: string;
}

export interface GraphReviewItemsResponse {
  review_items: GraphReviewItem[];
  summary: {
    total: number;
    needs_review?: number;
    blocked?: number;
    accepted?: number;
    rejected?: number;
    by_category?: Record<string, number>;
  };
}

export interface ReportGuardrailResult {
  id: string;
  severity: GuardrailSeverity;
  title: string;
  message: string;
  guardrailKey?: string;
  guardrail_key?: string;
  payload?: Record<string, unknown>;
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
  is_scaffold: boolean;
  progress: number;
  summary: string;
  input_scope?: Record<string, unknown> | null;
  active_node_ids: string[];
  output_refs: Record<string, unknown>;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  last_synced_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface BrandSpaceGraph {
  entities: GraphEntity[];
  relations: GraphRelation[];
  evidenceRefs: EvidenceRef[];
  meta?: {
    state?: string;
    message?: string;
  };
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
  entity_id?: string;
  report_id: string;
  version: number;
  report_kind: string;
  artifact_id: string;
  title: string;
  summary: string;
  payload: Record<string, unknown>;
  source_type?: 'graph_update' | 'pre_graph_update';
  graph_update_id?: string | null;
  publication_status?: string;
  created_at: string;
  updated_at?: string;
}

export interface BrandSpaceReportSummary {
  id: string;
  report_id: string;
  version: number;
  report_kind: string;
  title: string;
  summary: string;
  source_type: 'graph_update' | 'pre_graph_update';
  graph_update_id?: string | null;
  publication_status: string;
  created_at: string;
  updated_at: string;
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
  reports?: BrandSpaceReportSummary[];
}

export interface CreateBrandSpaceBoardRunInput {
  board_id?: string;
  template_id?: string;
  input_scope?: Record<string, unknown> | null;
  execution_mode?: 'scaffold' | 'real';
}
