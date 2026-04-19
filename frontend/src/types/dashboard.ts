/** BWVS v2 breakdown: four-dimensional scoring */
export interface BwvsBreakdown {
  mention_score: number;
  sentiment_score: number;
  coverage_score: number;
  citation_score: number;
  citation_note?: string;
  weights: {
    mention: number;
    sentiment: number;
    coverage: number;
    citation: number;
  };
  formula: string;
}

export interface KPIData {
  brandVisibility: number | null;
  mentionRate: number | null;
  shareOfVoice: number | null;
  visibilityTrend: number | null;
  mentionTrend: number | null;
  sovTrend: number | null;
  bwvsBreakdown?: BwvsBreakdown | null;
}

export interface VisibilityDataPoint {
  date: string;
  score: number;
  platform?: string;
}

export interface PlatformData {
  platform: string;
  mentionRate: number;
  avgRanking: number;
  sentiment: number;
  totalQueries: number;
}

export interface SourceData {
  source: string;
  count: number;
  percentage: number;
}

export interface AEOMetric {
  metric: string;
  value: number;
  benchmark: number;
  status: 'good' | 'warning' | 'poor';
}

export interface SentimentData {
  category: string;
  positive: number;
  neutral: number;
  negative: number;
}

export interface OptimizationUnit {
  id: string;
  query: string;
  currentRank: number | null;
  targetRank: number;
  priority: 'high' | 'medium' | 'low';
  status: 'optimized' | 'in_progress' | 'not_started';
}

export interface CompetitorRow {
  name: string;
  visibility: number;
  mentionRate: number;
  avgRanking: number;
  sentiment: number;
}

export interface DashboardV2KPI {
  id:
    | 'brand_mention_rate'
    | 'official_citation_rate'
    | 'scenario_hit_count'
    | 'missing_high_value_scenario_count'
    | 'high_risk_scenario_count'
    | string;
  label: string;
  value: number | null;
  unit?: string;
  subtitle?: string;
  trend?: number | null;
  trendUnit?: string;
  targetTab?: 'overview' | 'scenarios' | 'competitors' | 'sources' | 'riskAction' | 'monitoring' | string;
}

export interface DashboardScenarioRow {
  scenario_id: string;
  scenario_label: string;
  scenario_priority: 'high' | 'medium' | 'low' | string;
  brand_present: boolean;
  present_platforms: string[];
  official_citation_present: boolean;
  official_sources?: string[];
  competitors_present: string[];
  winner_brands: string[];
  battle_status: 'advantage' | 'defend' | 'contested' | 'missing' | string;
  risk_level: 'high' | 'medium' | 'low' | string;
  action_hint: string;
  evidence?: string;
  query_examples?: string[];
  recent_changes?: string[];
}

export interface DashboardCompetitorPressureCard {
  competitor: string;
  shared_scenarios: number;
  competitor_only_scenarios: number;
  brand_only_scenarios: number;
  pressure_level?: 'high' | 'medium' | 'low' | string;
  top_conflict_scenarios: string[];
}

export interface DashboardScenarioMatrixCell {
  brand: string;
  state: 'win' | 'present' | 'absent' | 'official_cited' | string;
  official_cited?: boolean;
}

export interface DashboardScenarioMatrixRow {
  scenario_id: string;
  scenario_label: string;
  competitor_states: DashboardScenarioMatrixCell[];
  winner_brand: string;
  battle_status: 'advantage' | 'defend' | 'contested' | 'missing' | string;
  recommended_focus?: string;
}

export interface DashboardRiskItem {
  risk_id: string;
  risk_type: 'missing_presence' | 'competitor_substitution' | 'no_official_citation' | 'weak_presence' | string;
  scenario_label: string;
  severity: 'high' | 'medium' | 'low' | string;
  reason: string;
  impact_summary: string;
  evidence?: string;
  recommended_action_ref?: string;
}

export interface DashboardActionItem {
  action_id: string;
  priority: number | 'high' | 'medium' | 'low' | string;
  scenario_label: string;
  action: string;
  target: string;
  expected_metric?: string;
  related_competitors?: string[];
  status?: 'not_started' | 'in_progress' | 'done' | string;
}

export interface DashboardSourcesV2 {
  official_citation_rate?: number | null;
  official_domain?: string | null;
  total_citations?: number | null;
  unique_domains?: number | null;
  top_domains?: Array<SourceData & { is_official?: boolean }>;
  platform_citation_stats?: Array<{
    platform: string;
    official_citation_rate: number;
    top_domains: Array<{ domain: string; count: number }>;
    citation_style?: string;
  }>;
}

export interface DashboardOverviewV2 {
  status_summary?: string;
  kpis?: DashboardV2KPI[];
  key_scenarios?: DashboardScenarioRow[];
  competitor_pressure?: DashboardCompetitorPressureCard[];
  recommended_actions?: DashboardActionItem[];
}

export interface DashboardV2Data {
  overview?: DashboardOverviewV2;
  scenarios?: DashboardScenarioRow[];
  competitorBattle?: {
    summary_cards?: DashboardCompetitorPressureCard[];
    scenario_matrix?: DashboardScenarioMatrixRow[];
  };
  home?: DashboardHomeData;
  sources?: DashboardSourcesV2;
  riskAction?: {
    risks?: DashboardRiskItem[];
    actions?: DashboardActionItem[];
  };
  monitoring_context_copy?: string;
}

export interface DashboardSentimentSummary {
  positive: number;
  neutral: number;
  negative: number;
}

export interface DashboardMentionItem {
  scenario_id: string;
  scenario_label: string;
  platform: string;
  sentiment: 'positive' | 'neutral' | 'negative' | string;
  evidence?: string;
  citation_domains?: string[];
  citation_titles?: string[];
  citation_urls?: string[];
  official_citation_present?: boolean;
  competitor?: string;
}

export interface DashboardScenarioInsight {
  scenario_id: string;
  scenario_label: string;
  reason: string;
  platforms?: string[];
}

export interface DashboardBoardTrendPoint {
  date: string;
  value: number | null;
}

export interface DashboardBoardTrend {
  metric_key: string;
  metric_label: string;
  value_format: 'percent' | 'score';
  current_value: number | null;
  previous_value: number | null;
  change_absolute: number | null;
  change_percentage: number | null;
  direction: string | null;
  data_point_count: number;
  period_label: string;
  points: DashboardBoardTrendPoint[];
}

export interface DashboardMentionBoard {
  mention_rate: number | null;
  headline: string;
  sentiment_summary: DashboardSentimentSummary;
  trend?: DashboardBoardTrend | null;
  leading_competitors: Array<{
    competitor: string;
    pressure_level: 'high' | 'medium' | 'low' | string;
    competitor_only_scenarios: number;
    sentiment_summary: DashboardSentimentSummary;
  }>;
  report: {
    brand_mentions: DashboardMentionItem[];
    competitor_mentions: DashboardMentionItem[];
    strong_scenarios: DashboardScenarioInsight[];
    weak_scenarios: DashboardScenarioInsight[];
  };
}

export interface DashboardAICEDimensions {
  authority?: number | null;
  intent?: number | null;
  clarity?: number | null;
  evidence?: number | null;
}

export interface DashboardSourceCitationCase {
  scenario_id: string;
  scenario_label: string;
  platform?: string;
  matched_answer?: string;
  citation_domains?: string[];
  citation_titles?: string[];
  citation_urls?: string[];
  is_official?: boolean;
  aice_score?: number | null;
  aice_dimensions?: DashboardAICEDimensions | null;
}

export interface DashboardSourceContent {
  title: string;
  domain?: string;
  count?: number;
  is_official?: boolean;
}

export interface DashboardSourcePlatformStat {
  platform: string;
  content_citation_rate: number;
  official_citation_rate: number;
  top_domains: Array<{ domain: string; count: number }>;
}

export interface DashboardSourceBoard {
  content_citation_rate: number | null;
  cited_answer_count: number;
  cited_content_count: number;
  headline: string;
  trend?: DashboardBoardTrend | null;
  report: {
    official_cases: DashboardSourceCitationCase[];
    non_official_cases: DashboardSourceCitationCase[];
    official_contents: DashboardSourceContent[];
    non_official_contents: DashboardSourceContent[];
    top_domains: Array<{
      domain: string;
      count: number;
      share: number;
      is_official?: boolean;
    }>;
    platform_stats: DashboardSourcePlatformStat[];
  };
}

export interface DashboardRadarDimension {
  id: string;
  label: string;
  score: number;
  summary: string;
}

export interface DashboardRadarBoard {
  headline: string;
  strongest_dimension: string;
  weakest_dimension: string;
  dimensions: DashboardRadarDimension[];
  trend?: DashboardBoardTrend | null;
}

export interface DashboardMonitoringEntry {
  title: string;
  description: string;
  cta_label: string;
}

export interface DashboardHomeMetric {
  id: string;
  label: string;
  value: number | null;
  format: 'percent' | 'rank' | 'count';
  subtitle?: string;
}

export interface DashboardLatestReport {
  title: string;
  subtitle?: string;
  report_kind?: string | null;
  report_kind_label?: string | null;
  badge_label?: string | null;
  triggered_by?: string | null;
  session_id?: string;
  artifact_id?: string;
  output_id?: string;
  created_at?: string;
  action_label?: string;
}

export interface DashboardCitationSourceType {
  key: string;
  label: string;
  share: number | null;
}

export interface DashboardCitationDomain {
  domain: string;
  display_name: string;
  count: number;
  share: number | null;
  is_official?: boolean;
  source_type?: string;
  source_type_label?: string;
}

export interface DashboardRelatedQuestion {
  question_id: string;
  question_text: string;
  scene?: string;
}

export interface DashboardHomeData {
  summary: {
    headline: string;
  };
  latest_report?: DashboardLatestReport;
  metrics?: DashboardHomeMetric[];
  citation_distribution?: {
    summary: string;
    source_types: DashboardCitationSourceType[];
    top_domains: DashboardCitationDomain[];
  };
  related_questions?: {
    summary: string;
    items: DashboardRelatedQuestion[];
  };
  /**
   * Compatibility-only legacy homepage fields.
   *
   * The canonical homepage path should use `summary`, `latest_report`,
   * `metrics`, `citation_distribution`, and `related_questions`.
   *
   * These fields are intentionally retained during controlled rollout so that
   * older dialog/reporting surfaces and monitoring-adjacent views are not
   * broken before their replacement path is finalized.
   */
  mention_board: DashboardMentionBoard;
  source_board: DashboardSourceBoard;
  radar_board: DashboardRadarBoard;
  monitoring_entry: DashboardMonitoringEntry;
}
export interface DashboardData {
  kpi: KPIData;
  visibility: VisibilityDataPoint[];
  platforms: PlatformData[];
  sources: SourceData[];
  aeoMetrics: AEOMetric[];
  sentiment: SentimentData[];
  optimizations: OptimizationUnit[];
  competitors: CompetitorRow[];
  v2?: DashboardV2Data | null;
}

