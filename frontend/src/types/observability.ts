export interface LLMObservabilitySummary {
  days: number;
  entity_id: string | null;
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

export interface LLMObservabilityBreakdown {
  provider?: string | null;
  model_name?: string | null;
  step?: string | null;
  step_name?: string | null;
  skill_key?: string | null;
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

export interface LLMObservabilityCall {
  id: string;
  task_id: string | null;
  session_id: string | null;
  brand_name: string;
  provider: string;
  model_name: string;
  skill_key: string | null;
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

export interface LLMObservabilitySnapshot {
  summary: LLMObservabilitySummary;
  by_model: LLMObservabilityBreakdown[];
  by_step: LLMObservabilityBreakdown[];
  by_skill: LLMObservabilityBreakdown[];
  recent_calls: LLMObservabilityCall[];
}
