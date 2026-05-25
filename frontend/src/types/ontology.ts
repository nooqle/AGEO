export interface OntologyLifecycle {
  status: string;
  raw_status?: string | null;
  allowed_statuses?: string[];
}

export interface OntologyObject {
  object_type: string;
  object_id: string;
  lifecycle: OntologyLifecycle;
  properties: Record<string, unknown>;
}

export interface OntologyObjectCollection {
  object_type: string;
  objects: OntologyObject[];
  total: number;
  limit: number;
  offset: number;
  filters?: {
    status?: string | null;
    created_after?: string | null;
    created_before?: string | null;
    sort?: string | null;
  };
}

export interface OntologyObjectSample {
  object_id: string;
  label: string;
  lifecycle?: string | null;
}

export interface OntologyObjectSummary {
  object_type: string;
  display_name: string;
  total: number;
  lifecycle_counts: Record<string, number>;
  sample_lifecycle_counts?: Record<string, number>;
  samples: OntologyObjectSample[];
}

export interface OntologyObjectLink {
  id: string;
  link_type: string;
  from_object_type: string;
  from_object_id: string;
  to_object_type: string;
  to_object_id: string;
  source_action_record_id?: string | null;
  extra_metadata?: Record<string, unknown>;
  created_at: string;
}

export interface OntologyObjectLinksResponse {
  links: OntologyObjectLink[];
  total: number;
}

export interface OntologyRelationshipSummary {
  link_type: string;
  display_name: string;
  from_object?: string | null;
  to_object?: string | null;
  count: number;
  visibility?: 'core' | 'supporting' | string;
  default_visible?: boolean;
}

export interface OntologyActionQueueItem {
  action_key: string;
  display_name: string;
  readiness: 'ready' | 'ready_with_defaults' | 'needs_input' | 'needs_confirmation' | 'blocked' | string;
  priority: number;
  permission_scope?: string | null;
  requires_confirmation: boolean;
  missing_inputs: string[];
  defaulted_inputs: Array<Record<string, unknown>>;
  missing_objects: Array<Record<string, unknown>>;
  reason?: string;
  source?: string;
  target_object_type?: string | null;
  target_object_id?: string | null;
  feedback_type?: string | null;
  latest_feedback_type?: OntologyActionFeedbackType | string | null;
  latest_feedback_at?: string | null;
  latest_feedback_status?: string | null;
  user_feedback_state?: 'none' | 'confirmed' | 'input_provided' | 'deferred' | string;
  has_user_feedback?: boolean;
  provided_input_keys?: string[];
  consumed_by_action_record_id?: string | null;
  consumed_by_action_type?: string | null;
}

export interface OntologyTaskFlowStep {
  key: string;
  label: string;
  status: 'complete' | 'current' | 'waiting' | string;
  owner: 'system' | 'human' | 'shared' | string;
  summary: string;
  evidence: string;
}

export interface OntologyTaskFlow {
  title: string;
  stage_label: string;
  owner_label: string;
  objective: string;
  expected_output: string;
  risk_label: string;
  action_label: string;
  action_prompt: string;
  steps: OntologyTaskFlowStep[];
}

export interface OntologyActionGap {
  key: string;
  severity?: string;
  object_type?: string;
  message?: string;
}

export interface OntologyIntelligenceFinding {
  object_id?: string | null;
  title: string;
  summary?: string;
  finding_type?: string;
  severity?: string;
  confidence?: number | null;
  status?: string | null;
  evidence_summary?: string;
  supporting_question_count?: number;
  supporting_answer_count?: number;
  supporting_citation_count?: number;
  suggested_action_type?: string;
  updated_at?: string | null;
}

export interface OntologyEvidenceSample {
  citation_id?: string;
  url?: string;
  domain?: string;
  title: string;
  snippet_preview?: string;
  platform?: string;
  confidence?: number | null;
  sample_reason?: string;
  is_official?: boolean;
  created_at?: string | null;
}

export interface OntologyEvidenceCluster {
  cluster_id: string;
  title: string;
  topic_key: string;
  topic_label: string;
  source_role: string;
  source_role_label: string;
  citation_count: number;
  answer_count: number;
  question_count: number;
  domain_count: number;
  official_citation_count: number;
  source_domains: string[];
  samples: OntologyEvidenceSample[];
  business_readout: string;
}

export interface OntologySourceDomainSummary {
  domain: string;
  site_name?: string;
  source_role: string;
  source_role_label: string;
  citation_count: number;
  answer_count: number;
  platform_count: number;
  is_official: boolean;
  sample_titles: string[];
}

export interface OntologyOfficialWebsiteSamplingPolicy {
  object_type: string;
  sample_unit: string;
  max_samples: number;
  summary: string;
  priority: string[];
  comparison_baseline: string;
}

export interface OntologyOfficialWebsiteComparisonDomain {
  domain: string;
  source_role: string;
  source_role_label: string;
  citation_count: number;
  answer_count: number;
}

export interface OntologyOfficialWebsiteContentAudit {
  status: string;
  value_score: number;
  value_label: string;
  http_status?: number | null;
  final_url?: string;
  content_type?: string;
  title?: string;
  meta_description?: string;
  h1_texts?: string[];
  schema_types?: string[];
  body_text_length?: number;
  brand_name_in_title?: boolean;
  brand_name_in_body?: boolean;
  business_readout?: string;
  gaps?: string[];
}

export interface OntologyOfficialWebsiteObservation {
  status:
    | 'missing_domain'
    | 'no_evidence'
    | 'not_cited'
    | 'weak'
    | 'visible'
    | 'strong'
    | string;
  domain: string;
  observed_domain_count: number;
  citation_count: number;
  citation_share: number;
  question_count: number;
  platform_count: number;
  value_score: number;
  value_label: string;
  business_readout: string;
  sampling_policy?: OntologyOfficialWebsiteSamplingPolicy;
  comparison_domains?: OntologyOfficialWebsiteComparisonDomain[];
  content_audit?: OntologyOfficialWebsiteContentAudit;
  samples: OntologyEvidenceSample[];
  gaps: string[];
}

export interface OntologyFindingFeedbackSummary {
  total: number;
  by_feedback_type?: Record<string, number>;
  validated_count?: number;
  dismissed_count?: number;
  correction_count?: number;
  correction_without_text_count?: number;
  latest?: Array<{
    decision_id?: string;
    finding_id?: string | null;
    feedback_type?: string;
    status?: string | null;
    has_feedback_text?: boolean;
    decided_at?: string;
  }>;
}

export interface OntologyActionFeedbackSummary {
  total: number;
  by_feedback_type?: Record<string, number>;
  latest?: Array<{
    decision_id?: string;
    action_record_id?: string | null;
    action_key?: string;
    feedback_type?: string;
    status?: string | null;
    has_feedback_text?: boolean;
    decided_at?: string;
  }>;
  latest_by_action?: Record<
    string,
    {
      decision_id?: string;
      action_record_id?: string | null;
      action_key?: string;
      feedback_type?: string;
      status?: string | null;
      has_feedback_text?: boolean;
      decided_at?: string;
    }
  >;
}

export interface OntologyGovernanceCheck {
  key: string;
  status: 'passed' | 'warning' | 'failed' | string;
  severity: 'info' | 'warning' | 'blocking' | string;
  message: string;
  details?: Array<Record<string, unknown>>;
}

export interface OntologyGovernanceReport {
  status: 'healthy' | 'degraded' | 'blocked' | string;
  checks: OntologyGovernanceCheck[];
  link_audit?: {
    scanned: number;
    limit: number;
    issue_count: number;
    issues: Array<Record<string, unknown>>;
  };
  generated_at?: string;
}

export interface OntologyMetricProjection {
  key: string;
  label: string;
  value?: number | null;
  display_value?: string | null;
  numerator?: number;
  denominator?: number;
  rank?: number | null;
  display_rank?: number | null;
  total?: number;
  rows?: OntologyRankingRow[];
  sample_sufficiency?: OntologyRankingSufficiency;
  official_domain?: string | null;
  official_domains?: string[];
  top_external_domain?: string | null;
  positive?: number;
  neutral?: number;
  negative?: number;
  dominant_sentiment?: string;
}

export interface OntologyRankingRow {
  brand_id: string;
  brand_name: string;
  mention_count: number;
  mention_rate: number | null;
  sample_count: number;
  is_current_brand: boolean;
  rank: number | null;
  provisional_rank?: number;
}

export interface OntologyRankingSufficiency {
  is_comparable?: boolean;
  is_rank_reliable?: boolean;
  status?: string;
  status_label?: string;
  reason?: string;
  sample_count?: number;
  evidence_count?: number;
  rank_status?: string;
  rank_status_label?: string;
  rank_reason?: string;
  comparison_sample?: {
    answer_count?: number;
    competitor_count?: number;
    competitor_mention_count?: number;
    competitors_with_mentions?: number;
    current_brand_mention_count?: number;
    minimum_answer_sample?: number;
    minimum_competitor_count?: number;
    minimum_competitors_with_mentions?: number;
    minimum_competitor_mention_count?: number;
  };
}

export interface OntologySampleQuality {
  metric_key?: string;
  status?: string;
  status_label?: string;
  sample_count?: number;
  evidence_count?: number;
  excluded_unreadable_count?: number;
}

export interface OntologyPlatformMetricRow {
  platform: string;
  answer_count: number;
  mention_count: number;
  mention_rate: number | null;
}

export interface OntologyAnswerEvidenceSample {
  answer_id?: string;
  question_id?: string;
  question?: string;
  platform?: string;
  answer_preview?: string;
  mention_quote?: string;
  sentiment?: 'positive' | 'neutral' | 'negative' | string;
  cited_domains?: string[];
  citation_sources?: Array<{
    citation_id?: string;
    url?: string;
    domain?: string;
    title?: string;
    snippet_preview?: string;
  }>;
  captured_at?: string;
}

export interface OntologyExternalDomainRow {
  domain: string;
  citation_count: number;
  answer_count: number;
  sample_titles?: string[];
}

export interface OntologySummaryProjection {
  brand?: {
    id?: string;
    name?: string;
    domain?: string;
    industry?: string;
  };
  sample_scope?: {
    platform_count?: number;
    question_count?: number;
    answer_count?: number;
    citation_count?: number;
    mention_count?: number;
    raw_answer_record_count?: number;
    excluded_unreadable_answer_count?: number;
    captured_from?: string | null;
    captured_to?: string | null;
  };
  metrics?: {
    mention_rate?: OntologyMetricProjection;
    mention_ranking?: OntologyMetricProjection;
    official_citation_rate?: OntologyMetricProjection;
    sentiment_distribution?: OntologyMetricProjection;
  };
  top_opportunity?: {
    title?: string;
    target_metric?: string;
    reason?: string;
  };
  top_risk?: {
    title?: string;
    target_metric?: string;
    reason?: string;
  };
}

export interface OntologyEvidenceProjection {
  mention_rate_detail?: {
    metric_key: string;
    numerator: number;
    denominator: number;
    value?: number | null;
    unmentioned_count?: number;
    unmentioned_sample_count?: number;
    unmentioned_unreadable_count?: number;
    excluded_unreadable_answer_count?: number;
    platform_rows: OntologyPlatformMetricRow[];
    answer_samples: OntologyAnswerEvidenceSample[];
    unmentioned_answer_samples?: OntologyAnswerEvidenceSample[];
    sample_quality?: OntologySampleQuality;
  };
  ranking_detail?: {
    metric_key: string;
    rank?: number | null;
    display_rank?: number | null;
    total: number;
    brands: OntologyRankingRow[];
    sample_sufficiency?: OntologyRankingSufficiency;
    sample_quality?: OntologySampleQuality;
  };
  official_citation_detail?: {
    metric_key: string;
    official_domain?: string;
    official_domains?: string[];
    official_citation_count: number;
    total_citation_count: number;
    value?: number | null;
    top_external_domains: OntologyExternalDomainRow[];
    official_samples?: OntologyEvidenceSample[];
    sample_quality?: OntologySampleQuality;
  };
  sentiment_detail?: {
    metric_key: string;
    summary: {
      positive?: number;
      neutral?: number;
      negative?: number;
      total?: number;
      dominant_sentiment?: string;
    };
    positive: OntologyAnswerEvidenceSample[];
    neutral: OntologyAnswerEvidenceSample[];
    negative: OntologyAnswerEvidenceSample[];
    sample_quality?: OntologySampleQuality;
  };
}

export interface OntologyGraphNode {
  id: string;
  type: string;
  label: string;
  level?: number;
  metric_key?: string | null;
  summary?: string;
  value?: string | null;
  parent_id?: string | null;
  business_meaning?: string;
  evidence_count?: number;
  next_actions?: Array<{
    label?: string;
    action?: string;
    recommendation_id?: string;
  }>;
}

export interface OntologyGraphEdge {
  id: string;
  from: string;
  to: string;
  label: string;
  type: string;
  strength?: string;
  business_meaning?: string;
  evidence_count?: number;
}

export interface OntologyGraphProjection {
  nodes: OntologyGraphNode[];
  edges: OntologyGraphEdge[];
  default_focus?: string | null;
  metric_snapshot_id?: string | null;
  expand_rules?: Array<Record<string, unknown>>;
}

export interface OntologyRecommendationItem {
  id: string;
  title: string;
  target_metric: string;
  reason: string;
  impact?: string;
  expected_impact?: string;
  review_criteria?: string;
  priority?: 'high' | 'medium' | 'low' | string;
  next_action?: 'open_monitoring_settings' | 'ask_chat' | string;
  cta_label?: string;
  task_state?: 'not_started' | 'in_progress' | 'completed' | 'review_pending' | string;
  owner_label?: string;
  due_at?: string;
  review_at?: string;
  latest_feedback_at?: string | null;
  content_brief?: string;
  content_format?: string;
  content_directions?: Array<{
    title?: string;
    angle?: string;
    evidence?: string;
  }>;
  distribution_targets?: Array<{
    name?: string;
    role?: string;
    domain?: string;
    platform?: string;
    reason?: string;
  }>;
  execution_steps?: string[];
  content_generation_brief?: string;
  evidence_refs?: string[];
}

export interface OntologyRecommendationProjection {
  recommendations: OntologyRecommendationItem[];
}

export interface OntologyRecommendationTaskRequest {
  task_status: 'not_started' | 'in_progress' | 'completed' | 'review_pending';
  owner_label?: string;
  due_at?: string;
  review_at?: string;
  feedback_text?: string;
  origin_event_id?: string;
}

export interface OntologyRecommendationTaskResponse {
  action_record: {
    id: string;
    entity_id: string;
    user_id?: string | null;
    actor_type: string;
    action_type: string;
    status: string;
    requires_confirmation: boolean;
    permission_scope: string;
    origin_surface?: string | null;
    origin_event_id?: string | null;
    submitted_at: string;
    completed_at?: string | null;
  };
  recommendation?: OntologyRecommendationItem | null;
  world: OntologyWorldSummary;
}

export interface OntologyWorldSummary {
  entity_id: string;
  projection_version?: number;
  brand: {
    object_id?: string;
    label?: string;
    lifecycle?: string | null;
  };
  entity?: {
    object_id?: string;
    label?: string;
    lifecycle?: string | null;
  };
  object_summaries: OntologyObjectSummary[];
  relationship_counts: Record<string, number>;
  relationship_summary: OntologyRelationshipSummary[];
  supporting_relationship_summary?: OntologyRelationshipSummary[];
  intelligence_findings?: OntologyIntelligenceFinding[];
  evidence_clusters?: OntologyEvidenceCluster[];
  source_domain_summary?: OntologySourceDomainSummary[];
  official_website_observation?: OntologyOfficialWebsiteObservation;
  finding_feedback_summary?: OntologyFindingFeedbackSummary;
  action_feedback_summary?: OntologyActionFeedbackSummary;
  governance_report?: OntologyGovernanceReport;
  summary_projection?: OntologySummaryProjection;
  evidence_projection?: OntologyEvidenceProjection;
  graph_projection?: OntologyGraphProjection;
  recommendation_projection?: OntologyRecommendationProjection;
  action_queue: OntologyActionQueueItem[];
  task_flow?: OntologyTaskFlow;
  world_phase?: string | null;
  gaps?: OntologyActionGap[];
  warnings?: string[];
}

export type OntologyFindingFeedbackType = 'validate' | 'dismiss' | 'correct';
export type OntologyActionFeedbackType = 'confirm' | 'defer' | 'provide_input';

export interface OntologyFindingFeedbackResponse {
  action_record: {
    id: string;
    entity_id: string;
    user_id?: string | null;
    actor_type: string;
    action_type: string;
    status: string;
    requires_confirmation: boolean;
    permission_scope: string;
    origin_surface?: string | null;
    origin_event_id?: string | null;
    submitted_at: string;
    completed_at?: string | null;
  };
  finding: OntologyIntelligenceFinding;
  world: OntologyWorldSummary;
}

export interface OntologyActionFeedbackResponse {
  action_record: {
    id: string;
    entity_id: string;
    user_id?: string | null;
    actor_type: string;
    action_type: string;
    status: string;
    requires_confirmation: boolean;
    permission_scope: string;
    origin_surface?: string | null;
    origin_event_id?: string | null;
    submitted_at: string;
    completed_at?: string | null;
  };
  world: OntologyWorldSummary;
}
