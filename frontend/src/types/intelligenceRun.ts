export type BrandIntelligenceRunStatus =
  | 'not_started'
  | 'planning_questions'
  | 'waiting_scope_confirmation'
  | 'fetching_answers'
  | 'waiting_takeover'
  | 'analyzing_metrics'
  | 'building_world'
  | 'generating_recommendations'
  | 'waiting_user'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface BrandIntelligenceRun {
  id: string;
  entity_id: string;
  created_by_user_id?: string | null;
  origin_session_id?: string | null;
  analysis_task_id?: string | null;
  origin_surface: string;
  origin_event_id?: string | null;
  status: BrandIntelligenceRunStatus;
  stage: string;
  progress: number;
  message: string;
  run_goal: string;
  analysis_mode: string;
  dashboard_variant?: string | null;
  center_terms?: string[] | null;
  enabled_surfaces?: string[] | null;
  input_scope?: Record<string, unknown> | null;
  sample_scope?: Record<string, unknown> | null;
  output_refs?: Record<string, unknown> | null;
  requires_user_action: boolean;
  user_action_type?: string | null;
  blocking_reason?: string | null;
  error_code?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
  failed_at?: string | null;
  last_activity_at: string;
  created_at: string;
  updated_at: string;
}

export interface CreateBrandIntelligenceRunInput {
  run_goal?: string | null;
  analysis_mode?: string;
  input_scope?: Record<string, unknown> | null;
  origin_surface?: string;
  origin_session_id?: string | null;
  origin_event_id?: string | null;
  auto_dispatch?: boolean;
}

export interface ConfirmBrandIntelligenceRunInput {
  user_action_type?: string | null;
  feedback_text?: string | null;
  provided_inputs?: Record<string, unknown> | null;
  origin_event_id?: string | null;
}

export interface BrandIntelligenceRunResponse {
  run: BrandIntelligenceRun | null;
}

export const ACTIVE_BRAND_INTELLIGENCE_RUN_STATUSES: BrandIntelligenceRunStatus[] = [
  'not_started',
  'planning_questions',
  'waiting_scope_confirmation',
  'fetching_answers',
  'waiting_takeover',
  'analyzing_metrics',
  'building_world',
  'generating_recommendations',
  'waiting_user',
];

export function isActiveBrandIntelligenceRun(
  run?: BrandIntelligenceRun | null,
): boolean {
  return Boolean(run && ACTIVE_BRAND_INTELLIGENCE_RUN_STATUSES.includes(run.status));
}

/** M3: run is parked at the flow-plan confirmation gate (not yet executing). */
export function isAwaitingFlowPlanConfirmation(
  run?: BrandIntelligenceRun | null,
): boolean {
  if (!run) return false;
  if (run.status !== 'waiting_scope_confirmation') return false;
  const action = String(run.user_action_type || '');
  return (
    run.requires_user_action
    || action === 'flow_plan_confirmation'
    || action === 'confirm_flow_plan'
    || String(run.blocking_reason || '') === 'flow_plan_confirmation_required'
  );
}

/** True when the pipeline is actually executing (excludes plan confirmation). */
export function isExecutingBrandIntelligenceRun(
  run?: BrandIntelligenceRun | null,
): boolean {
  return isActiveBrandIntelligenceRun(run) && !isAwaitingFlowPlanConfirmation(run) && run?.status !== 'not_started';
}
