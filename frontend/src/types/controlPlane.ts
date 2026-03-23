export interface ControlPlaneCustomerSummary {
  organization_id: string;
  customer_name: string;
  primary_account: string | null;
  member_count: number;
  brand_count: number;
  organization_brand_count: number;
  personal_brand_count: number;
  tokens_7d: number;
  cost_7d: number;
  active_task_count: number;
  last_active_at: string | null;
}

export interface ControlPlaneTaskSummary {
  task_id: string;
  organization_id: string | null;
  customer_name: string | null;
  brand_name: string;
  session_id: string | null;
  entity_id: string | null;
  visibility_scope: string | null;
  initiator_account: string | null;
  status: string;
  llm_total_tokens: number;
  llm_estimated_cost: number;
  llm_total_latency_ms: number;
  updated_at: string;
}

export interface ControlPlaneEntitySummary {
  id: string;
  name: string;
  visibility_scope: string;
  owner_account: string | null;
  last_analyzed: string | null;
  updated_at: string;
}

export interface ControlPlaneCustomerDetail {
  organization: {
    id: string;
    legal_name: string;
    status: string;
    primary_account: string | null;
    member_count: number;
    entity_count: number;
    created_at: string;
    updated_at: string;
  };
  summary: ControlPlaneCustomerSummary;
  users: import('./accountAdmin').AdminUserRecord[];
  entities: ControlPlaneEntitySummary[];
  recent_tasks: ControlPlaneTaskSummary[];
}

export interface ControlPlaneObservabilitySummary {
  days: number;
  call_count: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_prompt_tokens: number;
  billable_prompt_tokens: number;
  cache_hit_ratio: number;
  total_cost: number;
  total_cost_cache_aware: number;
  estimated_savings: number;
  total_latency_ms: number;
  avg_latency_ms: number;
  unique_models: number;
  first_call_at: string | null;
  last_call_at: string | null;
}

export interface ControlPlaneCostBreakdown {
  organization_id: string | null;
  customer_name: string | null;
  brand_name: string | null;
  provider: string | null;
  model_name: string | null;
  step: string | null;
  step_name: string | null;
  call_count: number;
  total_tokens: number;
  prompt_tokens: number;
  cached_prompt_tokens: number;
  cache_hit_ratio: number;
  total_cost: number;
  total_cost_cache_aware: number;
  estimated_savings: number;
  total_latency_ms: number;
  avg_latency_ms: number;
}

export interface ControlPlaneRecentCall {
  id: string;
  task_id: string | null;
  session_id: string | null;
  organization_id: string | null;
  customer_name: string | null;
  brand_name: string;
  provider: string;
  model_name: string;
  step: string | null;
  step_name: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_prompt_tokens: number;
  billable_prompt_tokens: number;
  cache_hit_ratio: number;
  latency_ms: number;
  estimated_cost: number;
  estimated_cost_cache_aware: number;
  estimated_savings: number;
  created_at: string | null;
}

export interface ControlPlaneObservabilitySnapshot {
  summary: ControlPlaneObservabilitySummary;
  by_customer_brand: ControlPlaneCostBreakdown[];
  by_model: ControlPlaneCostBreakdown[];
  by_step: ControlPlaneCostBreakdown[];
  recent_calls: ControlPlaneRecentCall[];
}
