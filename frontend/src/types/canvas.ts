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

export type ReportCanvasData = CanvasPreviewData & {
  headline?: string;
  subtitle?: string;
  overallScore?: number;
  scoreBand?: string;
  metrics?: Record<string, CanvasPreviewMetricValue>;
  insights?: ReportInsight[];
  recommendations?: ReportRecommendation[];
  content?: string;
  bwvs_breakdown?: import('@/types/dashboard').BwvsBreakdown;
  // A5 extended fields (passed through from backend, consumed by ReportContent ext)
  key_findings?: unknown;
  strengths?: unknown;
  weaknesses?: unknown;
  opportunities?: unknown;
  threats?: unknown;
  action_plan?: unknown;
  platform_breakdown?: unknown;
  sentiment_distribution?: unknown;
  industry_insights?: unknown;
  platform_analysis?: unknown;
  competitor_deep_analysis?: unknown;
  risk_alerts?: unknown;
  delta_vs_previous?: unknown;
  competitor_bwvs?: unknown;
  _degradation_note?: string;
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
    }
;

export type ReportCanvasContent = Extract<CanvasContent, { type: 'report' }>;
export type ChartCanvasContent = Extract<CanvasContent, { type: 'chart' }>;
export type DataTableCanvasContent = Extract<CanvasContent, { type: 'dataTable' }>;
export type PipelineCanvasContent = Extract<CanvasContent, { type: 'pipeline' }>;
export type WorkflowCanvasContent = Extract<CanvasContent, { type: 'workflow' }>;
export type QuestionListCanvasContent = Extract<CanvasContent, { type: 'questionList' }>;
export type FetchResultsCanvasContent = Extract<CanvasContent, { type: 'fetchResults' }>;
