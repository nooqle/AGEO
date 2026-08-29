import type { OntologyAssociationCircleProjection } from './ontology';

export interface AmwayEntityTypeDefinition {
  type_id: string;
  label: string;
  definition: string;
  default_graph_role: string;
  extractable_from: string[];
  allowed_relation_types: string[];
  review_required: boolean;
}

export interface AmwayEntityLexiconEntry {
  id: string;
  entity_id: string;
  canonical_name: string;
  entity_type: string;
  aliases: string[];
  description: string;
  related_terms: string[];
  graph_policy: {
    main_orbit: string;
    risk_view: string;
    target_gap_view: string;
  };
  source_policy: {
    source_kind: string;
    source_document_section: string;
    user_confirmed: boolean;
  };
  review_status: string;
  origin: 'default' | 'overridden' | 'custom';
  is_deleted: boolean;
  updated_at: string | null;
}

export interface AmwayEntityLexiconResponse {
  entity_id: string;
  entity_name: string;
  ontology_id: string;
  version: string;
  entity_types: AmwayEntityTypeDefinition[];
  entries: AmwayEntityLexiconEntry[];
  deleted_entry_ids: string[];
}

export interface AmwayEntityLexiconMutationInput {
  canonical_name?: string;
  entity_type?: string;
  aliases?: string[];
  description?: string;
  related_terms?: string[];
  review_status?: string;
}

export interface AmwayQuestionHistorySet {
  id: string;
  source_type: 'question_set' | 'run_input';
  title: string;
  source: string;
  version?: number | null;
  status: string;
  question_count: number;
  questions: Array<Record<string, unknown>>;
  center_terms: string[];
  source_file_name?: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface AmwayQuestionHistoryResponse {
  question_sets: AmwayQuestionHistorySet[];
  total: number;
}

export type AmwayCircleRunStatus =
  | 'pending'
  | 'running'
  | 'partial'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type AmwayProjectionScope = 'run' | 'cumulative' | 'compare';

export type AmwayCirclePeriodType =
  | 'latest_run'
  | 'last_7_days'
  | 'last_14_days'
  | 'last_30_days'
  | 'custom';

export type AmwayOrbitTrack = 'stable' | 'opportunity' | 'watch' | 'risk';

export type AmwayNodeChangeType =
  | 'strengthened'
  | 'weakened'
  | 'new'
  | 'dropped'
  | 'track_moved'
  | 'stable';

export interface AmwayCircleRunSummary {
  id: string;
  entity_id: string;
  run_sequence: number;
  run_label: string;
  status: AmwayCircleRunStatus;
  center_term: string;
  platforms_requested: string[];
  platforms_completed: string[];
  question_count: number;
  expected_answer_count: number;
  valid_answer_count: number;
  failed_answer_count: number;
  include_in_cumulative: boolean;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  latest_projection_id?: string | null;
  latest_report_id?: string | null;
}

export interface AmwaySampleScope {
  run_count: number;
  question_count: number;
  valid_answer_count: number;
  failed_answer_count: number;
  platforms: string[];
  latest_run_id?: string | null;
}

export interface AmwayDataQuality {
  status: 'ready' | 'partial' | 'insufficient' | 'failed';
  warnings: string[];
  platform_failures?: Array<{
    platform: string;
    failed_answer_count: number;
    reason?: string | null;
  }>;
}

export interface AmwayNodePlatformStats {
  platform: string;
  mention_answer_count: number;
  question_count: number;
  tendency: string;
}

export interface AmwayNodeChange {
  change_type: AmwayNodeChangeType;
  gravity_delta: number;
  distance_delta: number;
  mention_delta: number;
  platform_delta: number;
  track_from?: AmwayOrbitTrack | null;
  track_to?: AmwayOrbitTrack | null;
  explanation: string;
  evidence_refs: string[];
}

export interface AmwayCircleNode {
  node_id: string;
  lexicon_entity_id?: string | null;
  canonical_name: string;
  display_name: string;
  entity_type: string;
  source_type: 'strategy_term' | 'answer_entity' | 'risk' | 'competitor';
  track: AmwayOrbitTrack;
  track_reason: string;
  mention_answer_count: number;
  question_count: number;
  platform_count: number;
  evidence_count: number;
  center_anchor_count: number;
  amway_anchor_ratio: number;
  gravity_score: number;
  distance_score: number;
  stability_score: number;
  risk_score: number;
  position: {
    x: number;
    y: number;
  };
  node_size: number;
  display_priority: number;
  platform_summary: Record<string, AmwayNodePlatformStats>;
  evidence_refs: string[];
  change?: AmwayNodeChange | null;
}

export interface AmwayCircleEdge {
  edge_id: string;
  source_node_id: string;
  target_node_id: string;
  relation_type: string;
  relation_label: string;
  strength_score: number;
  risk_context?: string | null;
  evidence_count: number;
  platform_count: number;
  question_count: number;
  evidence_refs: string[];
}

export interface AmwayCompareSummary {
  compare_mode: 'latest_vs_previous' | 'run_vs_run' | 'run_vs_cumulative';
  base_run_id?: string | null;
  target_run_id?: string | null;
  top_changes: AmwayNodeChange[];
}

export interface AmwayAssociationCircleProjectionV2 {
  schema_version: string;
  view_scope: AmwayProjectionScope;
  entity_id: string;
  center: {
    center_term: string;
    center_terms: string[];
    display_name: string;
  };
  sample_scope: AmwaySampleScope;
  tracks: Array<{
    track_id: AmwayOrbitTrack;
    label: string;
    meaning: string;
    node_count: number;
  }>;
  nodes: AmwayCircleNode[];
  edges: AmwayCircleEdge[];
  risk_cluster?: {
    node_count: number;
    top_nodes: AmwayCircleNode[];
    entry_node_id: string;
  } | null;
  platform_summary: Record<string, unknown>;
  strategy_validation: Record<string, unknown>;
  compare_summary?: AmwayCompareSummary | null;
  updated_at: string;
}

export interface AmwayCircleProjectionResponse {
  id: string;
  entity_id: string;
  projection_scope: AmwayProjectionScope;
  circle_run_id?: string | null;
  base_run_id?: string | null;
  target_run_id?: string | null;
  as_of_run_id?: string | null;
  projection_version: string;
  status: 'ready' | 'partial' | 'building' | 'failed';
  source_run_ids: string[];
  source_run_count: number;
  source_run_hash: string;
  sample_scope: AmwaySampleScope;
  association_circle_projection: AmwayAssociationCircleProjectionV2;
  compare_summary?: AmwayCompareSummary | null;
  data_quality: AmwayDataQuality;
  built_at: string;
}

export interface AmwayCirclePeriodSummary {
  period_type: string;
  run_ids: string[];
  run_count: number;
  question_count: number;
  valid_answer_count: number;
  failed_answer_count: number;
  platforms: string[];
  start_at: string | null;
  end_at: string | null;
  latest_run_id?: string | null;
}

export interface AmwayCirclePeriodChange {
  node_id: string;
  term: string;
  change_type: AmwayNodeChangeType;
  gravity_delta: number;
  distance_delta: number;
  mention_delta: number;
  platform_delta: number;
  track_from?: AmwayOrbitTrack | null;
  track_to?: AmwayOrbitTrack | null;
  explanation: string;
}

export interface AmwayCirclePeriodProjection extends OntologyAssociationCircleProjection {
  report_markdown?: string | null;
  full_markdown?: string | null;
}

export interface AmwayCirclePeriodReportRequest {
  period_type: AmwayCirclePeriodType;
  start_at: string | null;
  end_at: string | null;
  center_term: string;
}

export interface AmwayCirclePeriodViewResponse {
  period_type: AmwayCirclePeriodType;
  current_period: AmwayCirclePeriodSummary;
  previous_period: AmwayCirclePeriodSummary | null;
  question_set_changed: boolean;
  comparison_notice: string;
  change_top5: AmwayCirclePeriodChange[];
  report_id: string | null;
  projection: AmwayCirclePeriodProjection | null;
  report_input: Record<string, unknown>;
}

export interface AmwayEvidenceQuote {
  circle_run_id?: string;
  evidence_ref: string;
  platform: string;
  platform_model?: string | null;
  fetch_agent_version?: string;
  question_id: string;
  question_hash?: string;
  question_text: string;
  quote_text: string;
  quote_type: 'support' | 'risk' | 'competitor' | 'clarification' | 'neutral';
  entity_names: string[];
  strategy_terms: string[];
}

export interface AmwayNodeInsight {
  node_id: string;
  title: string;
  role_label: string;
  relationship_to_center: string;
  brand_meaning: string;
  evidence_summary: {
    question_count: number;
    answer_count: number;
    platform_count: number;
    top_platforms: Array<{
      platform: string;
      count: number;
      tendency: string;
    }>;
  };
  representative_quotes: AmwayEvidenceQuote[];
  next_action: string;
}
