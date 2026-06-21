export interface SnapshotSummary {
  id: string;
  entity_id: string;
  status: 'completed' | 'partial';
  bwvs_index: number | null;
  mention_rate: number | null;
  sentiment_score: number | null;
  coverage_score: number | null;
  citation_score: number | null;
  platforms_success: number;
  platforms_total: number;
  total_questions: number;
  total_mentions: number;
  triggered_by: string;
  created_at: string;
  completed_at: string | null;
}

export interface SnapshotTrendPoint {
  date: string;
  bwvs_index: number;
  mention_rate: number;
  sentiment_score: number;
  coverage_score: number;
  citation_score: number;
  snapshot_id: string;
}

export interface SnapshotDelta {
  value: number;
  percentage: number;
  direction: 'up' | 'down' | 'stable';
}

export interface SnapshotCompare {
  base: SnapshotSummary;
  target: SnapshotSummary;
  delta: Record<string, SnapshotDelta>;
}

export interface StageResult {
  stage: string;
  stageName?: string;
  stage_name?: string;
  resultType?: 'brand_profile' | 'personas' | 'questions' | 'platform_status' | 'metrics_preview' | 'entity_extraction_signal' | 'entity_calibration_summary';
  result_type?: 'brand_profile' | 'personas' | 'questions' | 'platform_status' | 'metrics_preview' | 'entity_extraction_signal' | 'entity_calibration_summary';
  data: Record<string, unknown>;
  timestamp?: string;
  /** Cycle 3: Quality level from A1 validation (only on brand_profile) */
  qualityLevel?: 'high' | 'good' | 'adequate' | 'partial';
  /** Cycle 3: Quality description message */
  qualityMessage?: string;
}

export interface PlatformStatusData {
  platform: string;
  status: 'success' | 'failed' | 'fetching' | 'waiting';
  questionsCompleted?: number;
  questionsTotal?: number;
  mentionCount?: number;
  error?: string | null;
}
