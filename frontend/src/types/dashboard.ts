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

export interface DashboardData {
  kpi: KPIData;
  visibility: VisibilityDataPoint[];
  platforms: PlatformData[];
  sources: SourceData[];
  aeoMetrics: AEOMetric[];
  sentiment: SentimentData[];
  optimizations: OptimizationUnit[];
  competitors: CompetitorRow[];
}
