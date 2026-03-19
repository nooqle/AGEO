export type CanvasMode = 'hidden' | 'split' | 'focused';

export type CanvasContentType =
  | 'report'
  | 'chart'
  | 'dataTable'
  | 'pipeline'
  | 'workflow'
  | 'questionList'
  | 'fetchResults';

export type CanvasPreviewMetricValue = string | number | { label?: string; value?: string | number };

export type CanvasPreviewData = {
  description?: string;
  metrics?: Record<string, CanvasPreviewMetricValue>;
  itemCount?: number;
};

export type ReportInsight = {
  type?: 'strength' | 'weakness' | 'opportunity' | string;
  title?: string;
  description?: string;
};

export type ReportRecommendation = {
  priority?: number;
  title?: string;
  rationale?: string;
  eeat_dimension?: string;
  current_strength?: string;
  expected_impact?: string;
  difficulty?: string;
  timeline?: string;
};

export type CitationDomainItem = {
  domain: string;
  count: number;
  share: number;
  is_official: boolean;
  sample_titles?: string[];
};

export type PlatformCitationStats = {
  total_citations: number;
  unique_domains: number;
  official_count: number;
  official_share: number;
  avg_citations_per_answer: number;
  top_domains: Array<{ domain: string; count: number }>;
};

export type CitationAnalysis = {
  total_citations: number;
  unique_domains: number;
  official_citations: number;
  official_share: number;
  brand_domain: string;
  top_domains: CitationDomainItem[];
  platform_citation_stats: Record<string, PlatformCitationStats>;
  note?: string;
};

export type KeywordContext = {
  text: string;
  platform: string;
};

export type KeywordItem = {
  word: string;
  value: number;
  platforms: string[];
  contexts: KeywordContext[];
};

export type KeywordAnalysis = {
  total_keywords: number;
  platforms: string[];
  keywords: KeywordItem[];
};

export type ReportMetricStatus = 'good' | 'warning' | 'risk' | 'neutral';

export type ReportV2Metric = {
  id: string;
  label: string;
  value?: string | number;
  unit?: string;
  description?: string;
  trend?: number | null;
  status?: ReportMetricStatus;
  assessment?: string;
};

export type ReportSummaryData = {
  title?: string;
  description?: string;
  summary?: string;
  status_summary?: string;
  highlights?: string[];
  metrics?: ReportV2Metric[];
};

export type ScenarioBattleStatus = 'advantage' | 'defend' | 'contested' | 'missing' | string;
export type ScenarioPriority = 'high' | 'medium' | 'low' | string;
export type RiskSeverity = 'high' | 'medium' | 'low' | string;

export type ScenarioCoverageItem = {
  scenario_id?: string;
  scenario_label: string;
  scenario_priority?: ScenarioPriority;
  brand_present?: boolean;
  present_platforms?: string[];
  official_citation_present?: boolean;
  official_source_domains?: string[];
  battle_status?: ScenarioBattleStatus;
  evidence?: string;
  confidence?: number;
  competitors_present?: string[];
  risk_reason_type?: 'competitor_crowding' | 'negative_brand' | string;
  risk_reason_summary?: string;
  fact_basis?: string[];
  semantic_tags?: {
    audiences?: string[];
    prices?: string[];
    features?: string[];
    usages?: string[];
  };
};

export type ScenarioCoverageLensItem = {
  label: string;
  count: number;
  brandCount: number;
  competitorCount: number;
  missingCount: number;
  riskCount: number;
};

export type ScenarioCoverageLens = {
  key: 'audiences' | 'prices' | 'features' | 'usages';
  label: string;
  items?: ScenarioCoverageLensItem[];
};

export type ScenarioCoverageData = {
  title?: string;
  description?: string;
  summary?: string;
  overview?: string;
  items?: ScenarioCoverageItem[];
  missing_items?: ScenarioCoverageItem[];
  risk_items?: ScenarioCoverageItem[];
  missing_summary?: string;
  risk_summary?: string;
  semantic_lenses?: ScenarioCoverageLens[];
};

export type CompetitorBattleMentionExample = {
  scenario_label?: string;
  platform?: string;
  sentiment?: string;
  citation_domains?: string[];
};

export type CompetitorBattleSummaryCard = {
  competitor: string;
  shared_scenarios?: number;
  competitor_only_scenarios?: number;
  brand_only_scenarios?: number;
  pressure_level?: RiskSeverity;
  top_conflict_scenarios?: string[];
  sentiment_summary?: Partial<Record<'positive' | 'neutral' | 'negative', number>>;
  mention_examples?: CompetitorBattleMentionExample[];
};

export type CompetitorBattleItem = {
  scenario_id?: string;
  scenario_label: string;
  brand_present?: boolean;
  competitors_present?: string[];
  winner_brands?: string[];
  battle_status?: ScenarioBattleStatus;
  evidence?: string;
  recommended_focus?: string;
};

export type CompetitorBattleData = {
  title?: string;
  description?: string;
  overview?: string;
  summary_cards?: CompetitorBattleSummaryCard[];
  items?: CompetitorBattleItem[];
  differentiation_strategy?: string;
};

export type ReportRiskItem = {
  risk_id?: string;
  risk_type?: string;
  scenario_label?: string;
  severity?: RiskSeverity;
  reason?: string;
  impact_summary?: string;
  evidence?: string;
  recommended_action_ref?: string;
};

export type RiskSectionData = {
  title?: string;
  description?: string;
  summary?: string;
  items?: ReportRiskItem[];
};

export type SourceSectionData = {
  title?: string;
  description?: string;
  summary?: string;
  content_citation_rate?: number;
  mention_question_count?: number;
  cited_answer_count?: number;
  cited_content_count?: number;
  official_case_count?: number;
  non_official_case_count?: number;
  official_citation_rate?: number;
  official_top_titles?: string[];
  citation_cases?: ReportCitationCase[];
  citation_analysis?: CitationAnalysis | null;
};

export type ReportCitationCase = {
  scenario_label: string;
  platform?: string;
  matched_answer?: string;
  citation_domains?: string[];
  citation_titles?: string[];
  citation_urls?: string[];
  is_official?: boolean;
  aice_score?: number | null;
  aice_dimensions?: {
    authority?: number | null;
    intent?: number | null;
    clarity?: number | null;
    evidence?: number | null;
  } | null;
};

export type ReportMentionItem = {
  scenario_id?: string;
  scenario_label: string;
  platform?: string;
  sentiment?: 'positive' | 'neutral' | 'negative' | string;
  evidence?: string;
  citation_domains?: string[];
  citation_titles?: string[];
  citation_urls?: string[];
  official_citation_present?: boolean;
  competitor?: string;
};

export type ReportMentionSummary = {
  positive: number;
  neutral: number;
  negative: number;
};

export type ReportMentionScenarioGroup = {
  key: string;
  question: string;
  platforms: string[];
  source_labels: string[];
  brand_count: number;
  competitor_count: number;
  sentiment: 'positive' | 'neutral' | 'negative' | string;
  brand_labels: string[];
  competitor_labels: string[];
  brand_facts: string[];
  competitor_facts: string[];
};

export type ReportMentionSectionData = {
  title?: string;
  description?: string;
  mention_rate?: number;
  mention_count?: number;
  sentiment_summary?: ReportMentionSummary;
  brand_mentions?: ReportMentionItem[];
  competitor_mentions?: ReportMentionItem[];
  groups?: ReportMentionScenarioGroup[];
};

export type ActionQueueItem = {
  action_id?: string;
  priority?: string | number;
  scenario_label?: string;
  action?: string;
  title?: string;
  target?: string;
  expected_metric?: string;
  related_competitors?: string[];
  status?: 'not_started' | 'in_progress' | 'done' | string;
  owner_hint?: string;
  expected_impact?: string;
  difficulty?: string;
  timeline?: string;
};

export type ActionQueueData = {
  title?: string;
  description?: string;
  summary?: string;
  items?: ActionQueueItem[];
};

export type InsightSectionItem = {
  title: string;
  scenario?: string;
  evidence?: string;
  platforms?: string[];
  improvement_hint?: string;
  sentiment?: string;
  citation_domains?: string[];
  citation_titles?: string[];
  official_citation_present?: boolean;
};

export type InsightSectionData = {
  title?: string;
  description?: string;
  summary?: string;
  strengths?: InsightSectionItem[];
  weaknesses?: InsightSectionItem[];
};

export type ReportV2Data = {
  summary?: ReportSummaryData;
  mentions?: ReportMentionSectionData;
  scenarioCoverage?: ScenarioCoverageData;
  competitorBattle?: CompetitorBattleData;
  risks?: RiskSectionData;
  sources?: SourceSectionData;
  actionQueue?: ActionQueueData;
  insights?: InsightSectionData;
};

export type ConfidenceSignalLevel = 'high' | 'neutral' | 'caution';
export type ConfidenceEntityClassification =
  | 'brand'
  | 'competitor'
  | 'general_knowledge';
export type ConfidenceQuadrant =
  | 'q1_anchor'
  | 'q2_false_prosperity'
  | 'q3_noise'
  | 'q4_sleeping_asset';

export type ConfidenceSignalStatus = {
  phase?: 'idle' | 'running' | 'ready' | 'error';
  message?: string;
};

export type ConfidenceSignalSummary = {
  total_citations?: number;
  auto_evaluated_count?: number;
  evaluated_count?: number;
  failed_count?: number;
  high_confidence_count?: number;
  neutral_count?: number;
  caution_count?: number;
  manual_count?: number;
  brand_count?: number;
  competitor_count?: number;
  general_knowledge_count?: number;
  second_quadrant_count?: number;
  average_score?: number;
  average_confidence_score?: number;
  vulnerable_source_count?: number;
  updated_at?: string;
};

export type ConfidenceRepresentativeSource = {
  item_id?: string;
  label?: string;
  domain?: string;
  url?: string;
  score?: number;
  frequency?: number;
};

export type ConfidenceOverview = {
  entity_label?: string;
  average_confidence?: number | null;
  weighted_average_confidence?: number | null;
  source_count?: number;
  low_confidence_source_count?: number;
  representative_sources?: ConfidenceRepresentativeSource[];
};

export type ConfidencePatternExample = {
  label?: string;
  domain?: string;
  score?: number;
  evidence?: string;
};

export type ConfidencePattern = {
  pattern_key?: string;
  pattern_label?: string;
  sample_count?: number;
  average_confidence?: number | null;
  weighted_average_confidence?: number | null;
  affected_dimensions?: string[];
  evidence_examples?: ConfidencePatternExample[];
  suggestion?: string;
};

export type ConfidenceStrategicRecommendation = {
  title?: string;
  reason?: string;
  action?: string;
};

export type ConfidenceExtraEvaluation = {
  count?: number;
  items?: ConfidenceSignalItem[];
};

export type ConfidenceSignalFinding = {
  title?: string;
  description?: string;
};

export type ConfidenceMatrixConfig = {
  aice_threshold?: number;
  aice_threshold_mode?: string;
  frequency_threshold?: number;
  frequency_threshold_mode?: string;
  threshold_diagnostics?: {
    current_threshold?: number;
    average_score?: number;
    median_score?: number;
    percentile_75_score?: number;
    suggested_threshold?: number;
    high_score_share?: number;
    fit?: 'strict' | 'balanced' | 'loose' | string;
    note?: string;
  };
};

export type ConfidenceEcosystemMatrix = {
  title?: string;
  x_axis_label?: string;
  y_axis_label?: string;
  total_points?: number;
  diagnosis?: string;
};

export type ConfidenceQuadrantOverview = {
  quadrant: ConfidenceQuadrant;
  quadrant_label?: string;
  description?: string;
  strategy?: string;
  count?: number;
  entity_breakdown?: Partial<Record<ConfidenceEntityClassification, number>>;
};

export type ConfidenceSignalRecommendation = {
  title?: string;
  action?: string;
  reason?: string;
};

export type ConfidenceAuditPoint = {
  dimension_key?: string;
  dimension_label?: string;
  fact?: string;
  logic?: string;
  evidence?: string;
};

export type ConfidenceAuditActionStep = {
  priority?: number;
  dimension_key?: string;
  dimension_label?: string;
  issue_type?: string;
  instruction?: string;
  reason?: string;
  example?: string | null;
};

export type ConfidenceAuditReport = {
  score_formula?: string;
  core_summary?: string;
  high_confidence_points?: ConfidenceAuditPoint[];
  risk_points?: ConfidenceAuditPoint[];
  action_steps?: ConfidenceAuditActionStep[];
};

export type ConfidenceSignalDimensionScore = {
  key?: string;
  label?: string;
  max_score?: number;
  score?: number;
  confidence?: number;
  reasoning?: string;
};

export type ConfidenceSignalItem = {
  item_id: string;
  item_origin: 'auto_citation' | 'manual_extra';
  input_type: 'url' | 'text';
  label: string;
  url?: string;
  domain?: string;
  site_name?: string;
  is_official?: boolean;
  occurrences?: number;
  platforms?: string[];
  signal_level?: ConfidenceSignalLevel;
  overall_score?: number;
  overall_confidence?: number;
  entity_classification?: ConfidenceEntityClassification;
  entity_label?: string;
  frequency?: number;
  aice_score?: number;
  quadrant?: ConfidenceQuadrant;
  quadrant_label?: string;
  quadrant_description?: string;
  primary_reasons?: string[];
  repair_action?: string;
  analysis_group?: string;
  top_signals?: string[];
  dimension_scores?: ConfidenceSignalDimensionScore[];
  recommendations?: ConfidenceSignalRecommendation[];
  audit_report?: ConfidenceAuditReport;
  status?: 'pending' | 'running' | 'ready' | 'error';
  error_message?: string;
  question_samples?: string[];
  created_at?: string;
  raw_text?: string;
  crawl_readable?: boolean;
  http_status?: number | null;
  has_h1?: boolean;
  h1_count?: number;
  has_main?: boolean;
  has_article?: boolean;
  schema_types?: string[];
  published_at?: string;
};

export type ConfidenceAnalysisBlock = {
  key: string;
  title?: string;
  description?: string;
  reason_label?: string;
  action_label?: string;
  item_count?: number;
  items?: ConfidenceSignalItem[];
};

export type ConfidenceGeneralKnowledgeInsight = {
  summary?: string;
  top_frequency_items?: ConfidenceSignalItem[];
  top_score_items?: ConfidenceSignalItem[];
  representative_items?: ConfidenceSignalItem[];
};

export type ConfidenceRepairAction = {
  priority?: string;
  title?: string;
  summary?: string;
  count?: number;
  related_item_ids?: string[];
};

export type ConfidenceSignalComposerState = {
  enabled?: boolean;
  allowed_input_types?: Array<'url' | 'text'>;
  placeholder?: string;
  helper_text?: string;
};

export type ReportCanvasData = CanvasPreviewData & {
  report_kind?: string;
  artifact_kind?: string;
  headline?: string;
  subtitle?: string;
  overallScore?: number;
  scoreBand?: string;
  metrics?: Record<string, CanvasPreviewMetricValue>;
  insights?: ReportInsight[];
  recommendations?: ReportRecommendation[];
  content?: string;
  bwvs_breakdown?: import('@/types/dashboard').BwvsBreakdown;
  brand_name?: string;
  analysis_period?: string;
  platform_scope?: string[];
  updated_at?: string;
  report_v2?: ReportV2Data;
  report_summary?: ReportSummaryData;
  scenario_coverage?: ScenarioCoverageData;
  competitor_battle?: CompetitorBattleData;
  risk_section?: RiskSectionData;
  source_section?: SourceSectionData;
  action_queue_section?: ActionQueueData;
  insight_section?: InsightSectionData;
  summary_metrics?: unknown;
  scenario_matrix?: unknown;
  competitor_battles?: unknown;
  risk_map?: unknown;
  action_queue?: unknown;
  source_overview?: unknown;
  mention_sentiment_analysis?: unknown;
  // A5 extended fields (passed through from backend, consumed by ReportContent ext)
  key_findings?: unknown;
  strengths?: unknown;
  weaknesses?: unknown;
  opportunities?: unknown;
  threats?: unknown;
  action_plan?: unknown;
  actionable_recommendations?: unknown;
  platform_breakdown?: unknown;
  sentiment_distribution?: unknown;
  industry_insights?: unknown;
  platform_analysis?: unknown;
  competitor_deep_analysis?: unknown;
  risk_alerts?: unknown;
  delta_vs_previous?: unknown;
  competitor_bwvs?: unknown;
  report_data?: unknown;
  metrics_raw?: unknown;
  _degradation_note?: string;
  citation_analysis?: CitationAnalysis;
  keyword_analysis?: KeywordAnalysis;
  summary?: ConfidenceSignalSummary;
  config?: {
    low_confidence_threshold?: number;
    low_confidence_threshold_mode?: string;
    frequency_threshold?: number;
  };
  overall_conclusion?: string;
  brand_confidence_overview?: ConfidenceOverview;
  competitor_confidence_overview?: ConfidenceOverview;
  brand_low_confidence_patterns?: ConfidencePattern[];
  competitor_low_confidence_patterns?: ConfidencePattern[];
  strategic_recommendations?: ConfidenceStrategicRecommendation[];
  extra_evaluation?: ConfidenceExtraEvaluation;
  matrix_config?: ConfidenceMatrixConfig;
  ecosystem_matrix?: ConfidenceEcosystemMatrix;
  quadrant_overview?: ConfidenceQuadrantOverview[];
  analysis_blocks?: ConfidenceAnalysisBlock[];
  general_knowledge_insight?: ConfidenceGeneralKnowledgeInsight;
  repair_actions?: ConfidenceRepairAction[];
  auto_items?: ConfidenceSignalItem[];
  manual_items?: ConfidenceSignalItem[];
  aggregate_findings?: ConfidenceSignalFinding[];
  composer?: ConfidenceSignalComposerState;
  status?: ConfidenceSignalStatus;
  brand_keywords?: string[];
  competitor_names?: string[];
  diagnosis?: string;
};
export type ChartSeries = { key: string; name: string };
export type ChartDataItem = Record<string, string | number>;
export type ChartCanvasData = CanvasPreviewData & {
  chartType?: 'bar' | 'pie' | 'line' | 'radar';
  data?: ChartDataItem[];
  xAxisKey?: string;
  valueKey?: string;
  angleKey?: string;
  series?: ChartSeries[];
  summary?: string;
};

export type TableRow = Record<string, unknown>;
export type TableColumn = {
  key: string;
  label: string;
  sortable?: boolean;
  format?: (value: unknown, row: TableRow) => unknown;
};
export type DataTableCanvasData = CanvasPreviewData & {
  columns?: TableColumn[];
  rows?: TableRow[];
};

export type PipelineCanvasData = CanvasPreviewData & {
  pipeline?: import('./touchpoint').PipelineData;
  maxSelection?: number;
  minSelection?: number;
};

export type WorkflowBrandProfile = {
  brand_name: string;
  brand_name_en?: string;
  industry?: string;
  description?: string;
  core_products?: string[];
  brand_positioning?: string;
  target_audience?: string;
  price_positioning?: string;
  founded_year?: string;
};

export type WorkflowCompetitor = {
  name: string;
  name_en?: string;
  relevance_score: number;
  competition_type: string;
  core_products?: string[];
  competitive_advantage?: string;
  website?: string;
  description?: string;
};

export type WorkflowPersona = {
  id: string;
  persona_id?: string;
  persona_name: string;
  persona_description: string;
  persona_priority: string;
  demographics?: {
    age_range?: string;
    gender?: string;
    city_tier?: string;
    occupation?: string;
  };
  marketing_pain_points?: Array<{
    pain_point_category: string;
    pain_point_description: string;
  }>;
  usage_scenarios?: Array<{
    scenario_name: string;
    scenario_description: string;
  }>;
  psychographics?: {
    lifestyle?: string;
    values?: string;
    pain_points?: string[];
  };
  key_questions?: string[];
};

export type WorkflowSelectionItem = {
  id: string;
  name: string;
  description: string;
  priority?: 'core' | 'growth' | 'opportunity' | string;
  scenarios?: string[];
};

export type WorkflowSelectionData = {
  personas?: WorkflowSelectionItem[];
  maxSelection?: number;
  minSelection?: number;
  description?: string;
};

export type WorkflowCanvasData = CanvasPreviewData & {
  currentStep?: string;
  executionStatus?: 'idle' | 'running' | 'paused' | 'completed' | 'error';
  completedSteps?: string[];
  brandProfile?: WorkflowBrandProfile;
  brand_profile?: WorkflowBrandProfile;
  competitors?: WorkflowCompetitor[];
  competitive_landscape?: {
    market_overview?: string;
    competition_intensity?: string;
    key_battlegrounds?: string[];
  };
  personas?: WorkflowPersona[];
  user_personas?: WorkflowPersona[];
  brand_summary?: {
    brand_name?: string;
    core_value_proposition?: string;
    primary_category?: string;
    price_tier?: string;
  };
  selection?: WorkflowSelectionData;
};

export type SimulatedQuestionVariant = { type: string; question: string; tone: string };
export type SimulatedQuestion = {
  question_id: string;
  category: string;
  subcategory?: string;
  user_intent?: string;
  decision_stage?: string;
  core_question: string;
  question_variants?: {
    variant_a?: SimulatedQuestionVariant;
    variant_b?: SimulatedQuestionVariant;
    variant_c?: SimulatedQuestionVariant;
  };
};

export type QuestionItem = {
  id: string;
  text: string;
  category?: string;
  intent?: string;
  stage?: string;
  variant_type?: string;
};

export type QuestionListCanvasData = CanvasPreviewData & {
  questions?: QuestionItem[];
  simulatedQuestions?: {
    generation_mode?: string;
    simulated_questions?: SimulatedQuestion[];
  };
  generationMode?: string;
};

export type FetchCitation = {
  index: number;
  title: string;
  url: string;
  snippet?: string;
  site_name?: string;
  is_official?: boolean;
};

export type FetchPlatformResult = {
  platform: string;
  platform_name?: string;
  fetch_method?: string;
  success: boolean;
  answer?: {
    content?: string;
    word_count?: number;
    has_brand_mention?: boolean;
  };
  citations?: FetchCitation[];
  error?: string;
  duration?: number;
};

export type FetchResultItem = {
  question_id: string;
  question_text: string;
  platform_results: FetchPlatformResult[];
};

export type FetchResultsCanvasData = CanvasPreviewData & {
  fetchResults?: FetchResultItem[];
};

export type ContentVersion = {
  versionNumber: number;
  timestamp: string;
  data: Record<string, unknown>;
  linkedMessageId?: string;
};

export type CanvasContentDataMap = {
  report: ReportCanvasData;
  chart: ChartCanvasData;
  dataTable: DataTableCanvasData;
  pipeline: PipelineCanvasData;
  workflow: WorkflowCanvasData;
  questionList: QuestionListCanvasData;
  fetchResults: FetchResultsCanvasData;
};

export type CanvasContent =
  | {
      id: string;
      type: 'report';
      title: string;
      data: ReportCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'chart';
      title: string;
      data: ChartCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'dataTable';
      title: string;
      data: DataTableCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'pipeline';
      title: string;
      data: PipelineCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'workflow';
      title: string;
      data: WorkflowCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'questionList';
      title: string;
      data: QuestionListCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
  | {
      id: string;
      type: 'fetchResults';
      title: string;
      data: FetchResultsCanvasData;
      createdAt: Date;
      relatedMessageId: string;
      versions: ContentVersion[];
      currentVersionIndex: number;
      linkedMessageId?: string;
      category?: 'baseline' | 'scenario';
      scenarioLabel?: string;
      hasNewVersion?: boolean;
    }
;

export type ReportCanvasContent = Extract<CanvasContent, { type: 'report' }>;
export type ChartCanvasContent = Extract<CanvasContent, { type: 'chart' }>;
export type DataTableCanvasContent = Extract<CanvasContent, { type: 'dataTable' }>;
export type PipelineCanvasContent = Extract<CanvasContent, { type: 'pipeline' }>;
export type WorkflowCanvasContent = Extract<CanvasContent, { type: 'workflow' }>;
export type QuestionListCanvasContent = Extract<CanvasContent, { type: 'questionList' }>;
export type FetchResultsCanvasContent = Extract<CanvasContent, { type: 'fetchResults' }>;


