/**
 * Cycle 3: Task Persistence & Multi-Turn Follow-Up Types
 */

export type TaskStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
export type TaskRunStatus =
  | 'queued'
  | 'claimed'
  | 'running'
  | 'waiting_input'
  | 'cancelling'
  | 'cancelled'
  | 'failed'
  | 'completed';

export interface TaskRunRecord {
  id: string;
  task_id: string;
  run_kind: 'initial' | 'scheduled' | 'resume_after_input' | 'retry' | 'follow_up';
  trigger_source: 'websocket' | 'scheduler' | 'messages_api' | 'system_retry';
  executor_kind: 'local_workflow' | 'sandbox_workflow' | 'celery_fetch' | 'external';
  status: TaskRunStatus;
  attempt_no: number;
  priority: number;
  lease_owner: string | null;
  executor_ref: string | null;
  checkpoint_stage: string | null;
  checkpoint_payload_ref: string | null;
  error_kind: string | null;
  error_message: string | null;
  cancel_requested_at: string | null;
  heartbeat_at: string | null;
  submitted_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface AnalysisTask {
  id: string;
  brand_name: string;
  status: TaskStatus;
  current_stage: string;
  progress: number;
  progress_message: string;
  llm_call_count?: number;
  llm_prompt_tokens?: number;
  llm_completion_tokens?: number;
  llm_total_tokens?: number;
  llm_cached_prompt_tokens?: number;
  llm_billable_prompt_tokens?: number;
  llm_total_latency_ms?: number;
  llm_estimated_cost?: number;
  llm_estimated_cost_cache_aware?: number;
  snapshot_id: string | null;
  session_id: string;
  entity_id: string | null;
  error_message: string | null;
  error_stage: string | null;
  stage_results_cache: import('@/types/snapshot').StageResult[] | null;
  latest_run?: TaskRunRecord | null;
  task_runs?: TaskRunRecord[] | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface FollowUpSuggestion {
  id: string;
  label: string;
  message: string;
  type: 'drill_down' | 'compare' | 'refetch' | 'general';
  icon?: string;
}

export interface TaskNotification {
  taskId: string;
  brandName: string;
  status: 'completed' | 'failed';
  bwvsScore?: number;
  scoreBand?: string;
  sessionId: string;
  completedAt: string;
  errorMessage?: string;
  errorStage?: string;
}

/** Quality level for A1 data validation */
export type QualityLevel = 'high' | 'good' | 'adequate' | 'partial';
