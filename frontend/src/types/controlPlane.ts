export interface ControlPlaneCurrencyCost {
  currency: string;
  total_cost: number;
  total_cost_cache_aware: number | null;
  estimated_savings: number | null;
  priced_call_count: number;
}

export interface ControlPlanePricingCoverage {
  priced_call_count?: number;
  unknown_pricing_call_count?: number;
  pricing_coverage?: number;
  costs_by_currency?: ControlPlaneCurrencyCost[];
}

export interface ControlPlaneCacheCoverage extends ControlPlanePricingCoverage {
  cache_known_call_count?: number;
  cache_unknown_call_count?: number;
  cache_coverage?: number;
  cache_known_prompt_tokens?: number;
}

export interface ControlPlanePricingSnapshot {
  tariff_period?: string;
  rate_version?: string;
  source?: string;
  source_url?: string;
  priced_at?: string;
  pricing_timezone?: string;
}

export interface ControlPlaneCustomerSummary extends ControlPlanePricingCoverage {
  organization_id: string;
  customer_name: string;
  primary_account: string | null;
  member_count: number;
  brand_count: number;
  organization_brand_count: number;
  personal_brand_count: number;
  tokens_7d: number;
  cost_7d: number | null;
  currency?: string | null;
  active_task_count: number;
  last_active_at: string | null;
}

export interface ControlPlaneTaskSummary extends ControlPlanePricingCoverage {
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
  llm_estimated_cost: number | null;
  llm_estimated_cost_cache_aware: number | null;
  currency: string | null;
  llm_cached_prompt_tokens: number;
  llm_billable_prompt_tokens: number;
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
    feature_flags: Record<string, boolean>;
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

export interface AmwayChinaEntitlement {
  enabled: boolean;
  reason: string;
  entity_id: string | null;
  entity_name: string | null;
  dashboard_variant: string;
  center_terms: string[];
}

export interface ControlPlaneObservabilitySummary extends ControlPlaneCacheCoverage {
  days: number;
  call_count: number;
  total_tokens: number;
  prompt_tokens: number;
  completion_tokens: number;
  cached_prompt_tokens: number;
  billable_prompt_tokens: number;
  cache_hit_ratio: number | null;
  total_cost: number | null;
  total_cost_cache_aware: number | null;
  estimated_savings: number | null;
  currency: string | null;
  total_latency_ms: number;
  avg_latency_ms: number;
  unique_models: number;
  diagnostic_sample_count: number;
  low_cache_call_count: number;
  low_cache_call_ratio: number;
  static_prompt_variant_count: number;
  tool_surface_variant_count: number;
  model_identity_variant_count: number;
  avg_runtime_context_size: number | null;
  max_runtime_context_size: number | null;
  runtime_context_known_call_count?: number;
  first_call_at: string | null;
  last_call_at: string | null;
}

export interface ControlPlaneReuseDiagnostic {
  severity: string;
  code: string;
  title: string;
  message: string;
  affected_count: number;
  ratio: number | null;
}

export interface ControlPlaneCostBreakdown extends ControlPlaneCacheCoverage {
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
  completion_tokens: number;
  cached_prompt_tokens: number;
  billable_prompt_tokens: number;
  cache_hit_ratio: number | null;
  total_cost: number | null;
  total_cost_cache_aware: number | null;
  estimated_savings: number | null;
  currency: string | null;
  total_latency_ms: number;
  avg_latency_ms: number;
}

export interface ControlPlaneRecentCall {
  usage_time_basis?: 'recorded_at_estimate' | 'caller_supplied_estimate' | 'legacy_unknown';
  cost_is_estimate?: boolean;
  cost_scope?: string;
  provider_web_search_requests?: number | null;
  search_tool_cost_status?: string;
  estimated_search_tool_cost?: number | null;
  search_tool_currency?: string | null;
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
  cache_hit_ratio: number | null;
  latency_ms: number;
  estimated_cost: number | null;
  estimated_cost_cache_aware: number | null;
  estimated_savings: number | null;
  currency: string | null;
  pricing_status?: string;
  cache_status?: string;
  pricing?: ControlPlanePricingSnapshot | null;
  static_prompt_hash: string | null;
  tool_surface_hash: string | null;
  model_identity: string | null;
  runtime_context_size: number | null;
  runtime_reminder_enabled: boolean | null;
  stable_tool_surface_enabled: boolean | null;
  stable_skill_tool_description_enabled: boolean | null;
  reuse_diagnosis: string | null;
  created_at: string | null;
}

export interface ControlPlaneObservabilitySnapshot {
  summary: ControlPlaneObservabilitySummary;
  reuse_diagnostics: ControlPlaneReuseDiagnostic[];
  by_customer_brand: ControlPlaneCostBreakdown[];
  by_model: ControlPlaneCostBreakdown[];
  by_step: ControlPlaneCostBreakdown[];
  recent_calls: ControlPlaneRecentCall[];
}
