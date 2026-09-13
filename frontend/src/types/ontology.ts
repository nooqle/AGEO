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
  sample_status?: {
    is_ready?: boolean;
    status?: string;
    status_label?: string;
    reason?: string;
    question_count?: number;
    answer_count?: number;
    platform_count?: number;
  };
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

export interface AmwayTopicContribution {
  entity_id: string;
  entity_name: string;
  semantic_type?: string;
  contribution_kind: 'mapped' | 'direct';
  matched_text?: string;
  evidence_text?: string;
  answer_id?: string;
  platform?: string;
  mapping_sources?: Array<{ source_id: string; locator: string; quote: string }>;
  source_refs?: Array<{ source_id: string; locator: string; quote: string }>;
}

  export interface OntologyAssociationCircleNode {
    contribution_mode?: 'direct' | 'mapped' | 'mixed';
    contribution_label?: string;
    direct_answer_count?: number;
    mapped_answer_count?: number;
    overlap_answer_count?: number;
    supporting_answer_count?: number;
    topic_contributions?: AmwayTopicContribution[];
    node_id: string;
    entity_id?: string;
    entity_type?: string;
    term: string;
  orbit: 'core_near' | 'strong' | 'contestable' | 'weak' | 'blank' | 'risk_shadow' | 'R1' | 'R2' | 'R3' | string;
  orbit_label?: string;
  business_tag?: string;
  maturity_tier?: string;
  maturity_label?: string;
  priority_rank?: number;
  association_score?: number;
  gravity_score?: number;
  raw_gravity_score?: number;
  closeness_score?: number;
  distance_score?: number;
  frequency_score?: number;
  position_score?: number;
  relation_type_score?: number;
  scene_coverage_score?: number;
  model_consistency_score?: number;
  semantic_direction?: string;
  theme?: string;
  planet_group?: string;
  is_risk_term?: boolean;
  is_target_term?: boolean;
  answer_count?: number;
  answer_refs?: string[];
  answer_count_is_exact?: boolean;
  count_semantics?: 'distinct_answer_refs' | 'known_answer_refs_lower_bound' | 'legacy_summed_mentions' | string;
  platform_count?: number;
  platform_distribution?: Record<string, number>;
  primary_audience_segments?: string[];
  primary_mother_themes?: string[];
  primary_life_stages?: string[];
  primary_opportunity_points?: string[];
  relation_type_distribution?: Record<string, number>;
  supportive_evidence_count?: number;
  skeptical_evidence_count?: number;
  risk_evidence_count?: number;
  competitive_evidence_count?: number;
  trigger_questions?: string[];
  evidence_samples?: string[];
  evidence_refs?: string[];
  evidence_count?: number;
    evidence_strength?: string;
    orbit_reason?: string;
    source?: string;
    term_origin?: 'strategy' | 'answer' | string;
    origin_label?: string;
    source_policy?: Record<string, unknown>;
    graph_policy?: Record<string, unknown>;
    review_status?: string;
  }

export interface OntologyAssociationCircleEvidence {
  topic_contributions?: AmwayTopicContribution[];
  evidence_id: string;
  entity_id?: string;
  lexicon_entity_id?: string;
  node_id?: string;
  node_term?: string;
  platform?: string;
  question_id?: string;
  question?: string;
  audience_segment?: string | null;
  core_anxiety?: string | null;
  life_scene?: string | null;
  opportunity_point?: string | null;
  probe_type?: string | null;
  mother_theme?: string | null;
  question_type?: string | null;
  mentions_amway?: string | null;
  life_stage?: string | null;
  four_have?: string | null;
  touchpoint?: string | null;
  monitoring_purpose?: string | null;
  answer_excerpt?: string;
  answer_position?: string;
  relation_type?: string;
  context_polarity?: string;
  evidence_strength?: string;
}

export interface OntologyAssociationCircleQuestion {
  id?: string;
  text?: string;
  question?: string;
  question_text?: string;
  category?: string;
  intent?: string;
  stage?: string;
  audience_segment?: string | null;
  core_anxiety?: string | null;
  life_scene?: string | null;
  opportunity_point?: string | null;
  probe_type?: string | null;
  mother_theme?: string | null;
  question_type?: string | null;
  mentions_amway?: string | null;
  life_stage?: string | null;
  four_have?: string | null;
  touchpoint?: string | null;
  monitoring_purpose?: string | null;
  center_terms?: string[];
  question_set_version?: string;
  metadata_status?: string;
  metadata_missing_fields?: string[];
  source?: string;
}

export interface OntologyAssociationCirclePlatformComparison {
  platform: string;
  valid_answer_count?: number;
  answer_preference?: string;
  dominant_orbit?: string;
  preferred_nodes?: string[];
  competition_nodes?: string[];
  risk_nodes?: string[];
  risk_bias?: string;
  opportunity_bias?: string;
  recommendation?: string;
}

export interface OntologyAssociationCircleAction {
  id: string;
  action_type?: 'amplify' | 'translate' | 'build_path' | 'build_evidence' | string;
  action_label?: string;
  title?: string;
  node_id?: string;
  node_term?: string;
  orbit?: string;
  business_tag?: string;
  priority?: 'high' | 'medium' | 'low' | string;
  priority_reason?: string;
  target_platforms?: string[];
  target_audience?: string;
  target_scene?: string;
  goal_metric?: string;
  reason?: string;
  expected_impact?: string;
  review_criteria?: string;
  execution_steps?: string[];
  evidence_refs?: string[];
  next_question_suggestion?: string;
}

export interface OntologyAssociationCircleNarrativeSection {
  section_id?: string;
  role?: string;
  title: string;
  reader_question?: string;
  takeaway?: string;
  claims?: string[];
  so_what?: string;
  paragraphs: string[];
  supporting_facts?: string[];
  evidence_refs?: string[];
  next_probe?: string;
}

export interface OntologyAssociationCircleQuestionDefinition {
  center_term?: string;
  center_terms?: string[];
  question_count?: number;
  question_bank_count?: number;
  question_set_version?: string | null;
  question_sources?: Record<string, number>;
  audience_segments?: string[];
  probe_types?: string[];
  opportunity_points?: string[];
  life_scenes?: string[];
  sample_questions?: Array<{
    id?: string;
    question_id?: string;
    text?: string;
    question_text?: string;
    audience_segment?: string;
    life_scene?: string;
    opportunity_point?: string;
    probe_type?: string;
    metadata_status?: string;
  }>;
  definition_sentence?: string;
}

export interface OntologyAssociationCirclePlatformSourceRow {
  platform?: string;
  total_answer_count?: number;
  valid_answer_count?: number;
  failed_answer_count?: number;
  empty_answer_count?: number;
  question_ids?: string[];
  answer_preference?: string;
  preferred_nodes?: string[];
  competition_nodes?: string[];
  risk_nodes?: string[];
  dominant_orbit?: string;
  risk_bias?: string;
  opportunity_bias?: string;
  recommendation?: string;
}

export interface OntologyAssociationCirclePlatformSourceSummary {
  total_answer_count?: number;
  valid_answer_count?: number;
  failed_answer_count?: number;
  empty_answer_count?: number;
  platform_count?: number;
  platform_names?: string[];
  platforms?: OntologyAssociationCirclePlatformSourceRow[];
}

export interface OntologyAssociationCircleEvidenceFinding {
  node_id?: string;
  node_term?: string;
  claim?: string;
  orbit?: string;
  orbit_label?: string;
  business_tag?: string;
  supporting_facts?: string[];
  evidence_refs?: string[];
  sample_platform?: string;
  sample_question?: string;
  sample_excerpt?: string;
  implication?: string;
}

export interface OntologyAssociationCircleReportOutlineItem {
  chapter_id?: string;
  title?: string;
  reader_question?: string;
  required_evidence?: string[];
}

export interface OntologyAssociationCircleStrategyValidation {
  strategy_id?: string;
  strategy_term?: string;
  entity_type?: string;
  status?: 'validated' | 'partial' | 'missing' | 'risk' | string;
  validation_label?: string;
  decision_tier?: string;
  evidence_band?: string;
  node_score?: number;
  stance_summary?: {
    supportive?: number;
    neutral?: number;
    skeptical?: number;
    risk?: number;
    competitive?: number;
  };
  question_count?: number;
  question_refs?: string[];
  answer_mention_count?: number;
  answer_refs?: string[];
  answer_count_is_exact?: boolean;
  count_semantics?: 'distinct_answer_refs' | 'known_answer_refs_lower_bound' | 'legacy_summed_mentions' | string;
  platform_count?: number;
  platform_distribution?: Record<string, number>;
  related_node_ids?: string[];
  evidence_refs?: string[];
  platform_outcomes?: Array<{
    platform?: string;
    answer_count?: number;
    status?: string;
    sample_excerpt?: string;
    stance?: string;
    stance_summary?: {
      supportive?: number;
      neutral?: number;
      skeptical?: number;
      risk?: number;
      competitive?: number;
    };
  }>;
  interpretation?: string;
  action_recommendation?: string;
  review_status?: string;
}

export interface OntologyAssociationCircleStrategyPillar {
  key?: 'have_health' | 'have_companionship' | 'have_security' | 'have_value' | string;
  label?: string;
  status?: string;
  status_label?: string;
  answer_mention_count?: number;
  answer_count_is_exact?: boolean;
  count_semantics?: string;
  platform_count?: number;
  platform_distribution?: Record<string, number>;
  node_terms?: string[];
  risk_terms?: string[];
  competition_terms?: string[];
  strategy_terms?: string[];
  evidence_refs?: string[];
}

export interface OntologyAssociationCircleStrategyStoryline {
  framework?: string;
  pillars?: OntologyAssociationCircleStrategyPillar[];
  verdict?: Record<string, unknown>;
  weekly_actions?: Array<Record<string, unknown>>;
  platform_scope?: Record<string, unknown>;
  risk_absorption?: Record<string, unknown>;
}

export interface OntologyAssociationCirclePriorityItem {
  rank?: number;
  node_id?: string;
  term?: string;
  focus_type?: 'risk' | 'competitor' | 'opportunity' | 'asset' | string;
  business_tag?: string;
  maturity_tier?: string;
  score?: number;
  evidence_count?: number;
  answer_refs?: string[];
  answer_count_is_exact?: boolean;
  count_semantics?: 'distinct_answer_refs' | 'known_answer_refs_lower_bound' | 'legacy_summed_mentions' | string;
  platform_count?: number;
  scene_hint?: string;
  reason?: string;
  recommended_action?: string;
  evidence_refs?: string[];
  platform_distribution?: Record<string, number>;
  question_refs?: string[];
  sample_excerpt?: string;
}

export interface OntologyAssociationCirclePrioritySummary {
  top_risks?: OntologyAssociationCirclePriorityItem[];
  top_competitors?: OntologyAssociationCirclePriorityItem[];
  top_opportunities?: OntologyAssociationCirclePriorityItem[];
  top_assets?: OntologyAssociationCirclePriorityItem[];
  next_focus?: OntologyAssociationCirclePriorityItem[];
  reading?: string;
}

export interface OntologyAssociationCircleAnalysisTraceItem {
  step?: string;
  title?: string;
  summary?: string;
  outputs?: string[];
}

export interface OntologyAssociationCircleSourceAppendixItem {
  evidence_id?: string;
  answer_id?: string;
  entity_id?: string;
  lexicon_entity_id?: string;
  entity_type?: string;
  node_term?: string;
  platform?: string;
  question_id?: string;
  question?: string;
  answer_excerpt?: string;
  relation_type?: string;
  context_polarity?: string;
  audience_segment?: string;
  life_scene?: string;
  opportunity_point?: string;
  probe_type?: string;
  platform_valid_answer_count?: number;
}

export interface OntologyAssociationCircleBlindSpotMetrics {
  diagnosis?: string;
  active_mention_rate?: number | null;
  open_answer_count?: number;
  open_brand_mention_count?: number;
  brand_named_answer_count?: number;
  brand_named_brand_mention_count?: number;
  answer_count_is_exact?: boolean;
}

export interface OntologyAssociationCircleStorylineAnalysis {
  sample_profile?: Record<string, unknown>;
  blind_spot?: OntologyAssociationCircleBlindSpotMetrics;
  evidence_refs?: string[];
}

export type AmwayTopicCoverageStatus = 'included' | 'unmatched' | 'relation_filtered' | 'pending_review' | 'excluded';

export interface AmwayTopicCoverageRow {
  entity_id: string;
  canonical_name: string;
  status: AmwayTopicCoverageStatus;
  reason: string;
  review_status: string;
  answer_count: number;
  signal_count: number;
  reason_counts: Record<string, number>;
  score?: number;
  evidence_samples: Array<{
    answer_id: string;
    question_id: string;
    platform: string;
    question: string;
    evidence_text: string;
    reason: string;
  }>;
}

export interface AmwayTopicCoverage {
  schema_version: 1;
  scope: 'run' | 'period';
  analysis_version: string;
  lexicon_hash: string;
  total_topic_count: number;
  included_topic_count: number;
  anchor_node_count: number;
  other_node_count: number;
  status_counts: Record<string, number>;
  topics: AmwayTopicCoverageRow[];
}

export interface OntologyAssociationCircleProjection {
  topic_coverage?: AmwayTopicCoverage | null;
  object_index?: Array<{ entity_id: string; entity_name: string; evidence_text: string; platform: string; answer_id: string; semantic_definition?: { semantic_type?: string } }>;
  dashboard_variant?: string | null;
  analysis_mode?: string;
  report_kind?: string;
  status?: 'not_generated' | 'sample_limited' | 'ready' | string;
  center_terms: string[];
  nodes: OntologyAssociationCircleNode[];
  evidence_samples?: OntologyAssociationCircleEvidence[];
  question_bank?: OntologyAssociationCircleQuestion[];
  platform_comparison?: OntologyAssociationCirclePlatformComparison[];
  association_actions?: OntologyAssociationCircleAction[];
  report_narrative_sections?: OntologyAssociationCircleNarrativeSection[];
  report_quality_checks?: Record<string, unknown>;
  question_definition?: OntologyAssociationCircleQuestionDefinition;
  platform_source_summary?: OntologyAssociationCirclePlatformSourceSummary;
  evidence_findings?: OntologyAssociationCircleEvidenceFinding[];
  report_outline?: OntologyAssociationCircleReportOutlineItem[];
  strategy_validation?: OntologyAssociationCircleStrategyValidation[];
  strategy_storyline?: OntologyAssociationCircleStrategyStoryline;
  storyline_analysis?: OntologyAssociationCircleStorylineAnalysis;
  analysis_tool_trace?: OntologyAssociationCircleAnalysisTraceItem[];
  source_appendix?: OntologyAssociationCircleSourceAppendixItem[];
  copy_constraints?: Record<string, unknown>;
  sample_scope?: Record<string, unknown>;
  tracking_projection?: Record<string, unknown>;
  executive_summary?: Record<string, unknown>;
  priority_summary?: OntologyAssociationCirclePrioritySummary;
  generated_from?: string | null;
  report_id?: string | null;
  artifact_id?: string | null;
  updated_at?: string | null;
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
  dashboard_variant?: string | null;
  analysis_mode?: string | null;
  center_terms?: string[];
  association_circle_projection?: OntologyAssociationCircleProjection;
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
