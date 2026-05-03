/**
 * Cycle 4: Continuous Monitoring Types
 *
 * All field names use snake_case to match backend JSON responses directly.
 * This is consistent with other types in the project (e.g. AnalysisTask).
 */

// =========================================================================
// Enums
// =========================================================================

export type ScheduleFrequency = 'daily' | 'weekly' | 'biweekly' | 'monthly';

export type ScheduleStatus = 'active' | 'paused' | 'completed' | 'error';
export type MonitorMode = 'panorama' | 'scenario';
export type QuestionSetStatus = 'draft' | 'confirmed' | 'archived';
export type MonitoringPlanStatus = 'draft' | 'active' | 'paused' | 'archived';
export type MonitoringRunPolicy = 'quick' | 'full_browser' | 'manual';
export type MonitoringRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'partial';
export type MonitoringTrendGroupBy = 'overall' | 'endpoint' | 'question_set';

export type AlertSeverity = 'critical' | 'high' | 'medium' | 'low';

export type AlertStatus = 'unread' | 'read' | 'dismissed' | 'actioned';

export type TrendDirection = 'improving' | 'declining' | 'stable' | 'volatile';

// =========================================================================
// Monitoring Schedule (matches schedule_to_dict)
// =========================================================================

export interface BaselineSummary {
  question_count: number;
  saved_at: string | null;
  source_task_id: string | null;
}

export interface PanoramaAnalysisStatus {
  has_report: boolean;
  mention_rate: number | null;
  brand_rank: number | null;
  brand_rank_total: number | null;
  brand_rank_label: string | null;
  created_at: string | null;
  triggered_by: string | null;
  session_id: string | null;
}

export interface BaselineData {
  questions: Array<{ id: string; text: string; category?: string }>;
  simulated_questions: Record<string, unknown> | null;
  brand_profile: Record<string, unknown> | null;
  competitors: Array<Record<string, unknown>> | null;
  competitive_landscape: Record<string, unknown> | null;
  saved_at: string;
  source_task_id: string;
}

export interface MonitoringSchedule {
  id: string;
  user_id: string;
  entity_id: string;
  entity_name: string;
  frequency: ScheduleFrequency;
  status: ScheduleStatus;
  preferred_hour: number;
  timezone: string;
  platforms: string[] | null;
  monitor_mode: MonitorMode;
  question_set_ids: string[];
  endpoint_ids: string[];
  endpoint_labels: string[];
  run_policy: MonitoringRunPolicy;
  monitoring_plan_id: string | null;
  alert_on_significant_change: boolean;
  alert_threshold_bwvs: number;
  has_baseline: boolean;
  baseline_summary: BaselineSummary | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_task_id: string | null;
  total_runs: number;
  consecutive_failures: number;
  max_failures: number;
  max_runs: number | null;
  end_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface CreateScheduleInput {
  entity_id: string;
  frequency?: ScheduleFrequency;
  status?: ScheduleStatus;
  preferred_hour?: number;
  timezone?: string;
  platforms?: string[];
  monitor_mode?: MonitorMode;
  question_set_ids?: string[];
  endpoint_ids?: string[];
  run_policy?: MonitoringRunPolicy;
  alert_on_significant_change?: boolean;
  alert_threshold_bwvs?: number;
  max_runs?: number;
  end_date?: string;
}

export interface UpdateScheduleInput {
  frequency?: ScheduleFrequency;
  status?: ScheduleStatus;
  preferred_hour?: number;
  timezone?: string;
  platforms?: string[];
  monitor_mode?: MonitorMode;
  question_set_ids?: string[];
  endpoint_ids?: string[];
  run_policy?: MonitoringRunPolicy;
  alert_on_significant_change?: boolean;
  alert_threshold_bwvs?: number;
}

export interface MonitoringEndpoint {
  id: string;
  platform: string;
  fetch_method: 'api' | 'browser';
  display_name: string;
}

export interface MonitoringQuestion {
  question_id: string;
  question_text: string;
  scene?: string;
  intent?: string;
  stage?: string;
}

export interface MonitoringQuestionSet {
  id: string;
  user_id: string;
  entity_id: string;
  monitor_mode: MonitorMode;
  status: QuestionSetStatus;
  source: string;
  title: string;
  version: number;
  questions: MonitoringQuestion[];
  question_count: number;
  source_session_id: string | null;
  source_task_id: string | null;
  confirmed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface MonitoringPlan {
  id: string;
  user_id: string;
  entity_id: string;
  monitor_mode: MonitorMode;
  status: MonitoringPlanStatus;
  title: string;
  question_set_ids: string[];
  question_set_label: string;
  question_count: number;
  endpoint_ids: string[];
  endpoint_labels: string[];
  run_policy: MonitoringRunPolicy;
  frequency: ScheduleFrequency;
  preferred_hour: number;
  timezone: string;
  schedule_id: string | null;
  schedule_status: ScheduleStatus | null;
  created_at: string;
  updated_at: string;
}

export interface MonitoringRun {
  id: string;
  user_id: string;
  entity_id: string;
  plan_id: string;
  schedule_id: string | null;
  task_id: string | null;
  task_run_id: string | null;
  snapshot_id: string | null;
  status: MonitoringRunStatus;
  run_policy: MonitoringRunPolicy;
  monitor_mode: MonitorMode;
  endpoint_ids: string[];
  endpoint_labels: string[];
  question_set_ids: string[];
  question_count: number;
  error_message: string | null;
  error_stage: string | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

// =========================================================================
// Monitoring Alert (matches alert_to_dict)
// =========================================================================

export interface MonitoringAlert {
  id: string;
  user_id: string;
  entity_id: string;
  entity_name: string;
  schedule_id: string | null;
  snapshot_id: string | null;
  severity: AlertSeverity;
  status: AlertStatus;
  title: string;
  summary: string;
  metric_name: string | null;
  previous_value: number | null;
  current_value: number | null;
  change_absolute: number | null;
  change_percentage: number | null;
  details: Record<string, unknown> | null;
  created_at: string;
  read_at: string | null;
}

// =========================================================================
// Trend Data (matches /analytics/trend response)
// =========================================================================

/** Single data point from GET /analytics/trend */
export interface TrendDataPoint {
  date: string;
  value: number | null;
  snapshot_id: string;
  triggered_by: string;
  is_significant: boolean;
  run_id?: string | null;
  data_point_count?: number;
}

export interface MonitoringTrendSeriesPoint {
  date: string;
  value: number | null;
  snapshot_id?: string | null;
  run_id?: string | null;
  data_point_count?: number;
}

export interface MonitoringTrendSeries {
  id: string;
  label: string;
  metric: string;
  metric_label?: string;
  group_by: MonitoringTrendGroupBy;
  points: MonitoringTrendSeriesPoint[];
  data_point_count: number;
  current_value: number | null;
  previous_value: number | null;
  average_value: number | null;
  change_absolute: number | null;
  change_percentage: number | null;
  direction: TrendDirection;
}

export interface MonitoringTrendResponse {
  metric: string;
  metric_label?: string;
  group_by: MonitoringTrendGroupBy;
  monitor_mode: MonitorMode;
  date_range_days: number;
  period_label: string;
  series: MonitoringTrendSeries[];
  data_point_count: number;
}

/** Period delta nested inside TrendMetricSummary */
export interface TrendPeriodDelta {
  absolute: number;
  percentage: number;
  is_significant: boolean;
  direction: string;
}

/** Single metric summary from GET /analytics/trend/summary */
export interface TrendMetricSummary {
  metric_name: string;
  current_value: number | null;
  direction: TrendDirection;
  period_delta: TrendPeriodDelta | null;
  data_points: number;
  time_range_days: number;
  moving_average: number | null;
  min_value: number | null;
  max_value: number | null;
}

/** Response shape from GET /analytics/trend/summary */
export interface TrendSummaryResponse {
  summaries: Record<string, TrendMetricSummary>;
}

/**
 * Flattened trend summary used by UI components.
 * Derived from TrendMetricSummary for easier rendering.
 */
export interface TrendSummary {
  direction: TrendDirection;
  current_value: number | null;
  previous_value: number | null;
  change_absolute: number | null;
  change_percentage: number | null;
  data_point_count: number;
  period_label: string;
}

// =========================================================================
// Metric Delta (frontend-only, derived from trend summary)
// =========================================================================

export interface MetricDelta {
  metric_key: string;
  label: string;
  current_value: number | null;
  previous_value: number | null;
  delta: number | null;
  delta_percent: number | null;
  direction: TrendDirection;
  sparkline_data: number[];
}

// =========================================================================
// Run History (matches task_to_dict from /monitoring/schedules/{id}/history)
// =========================================================================

export type RunStatus = 'completed' | 'failed' | 'running' | 'pending';

export interface RunHistoryEntry {
  id: string;
  user_id: string;
  session_id: string | null;
  entity_id: string | null;
  brand_name: string | null;
  status: RunStatus;
  current_stage: string | null;
  progress: number | null;
  progress_message: string | null;
  snapshot_id: string | null;
  error_message: string | null;
  error_stage: string | null;
  monitoring_schedule_id: string | null;
  triggered_by: string;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

// =========================================================================
// Scheduler Health (matches get_scheduler_status)
// =========================================================================

export interface SchedulerHealth {
  running: boolean;
  active_pipeline_count: number;
  max_concurrent: number;
  semaphore_available: number;
  poll_interval_seconds: number;
}

// =========================================================================
// Frequency display helpers
// =========================================================================

export const FREQUENCY_LABELS: Record<ScheduleFrequency, string> = {
  daily: '每天',
  weekly: '每周',
  biweekly: '每两周',
  monthly: '每月',
};

export const SEVERITY_LABELS: Record<AlertSeverity, string> = {
  critical: '严重',
  high: '重要',
  medium: '一般',
  low: '低',
};
