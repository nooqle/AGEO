export interface LLMObservabilitySummary {
  days: number;
  entity_id: string | null;
  call_count: number;
  total_tokens: number;
  total_cost: number;
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
  call_count: number;
  total_tokens: number;
  total_cost: number;
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
  step: string | null;
  step_name: string | null;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  latency_ms: number;
  estimated_cost: number;
  created_at: string | null;
}

export interface LLMObservabilitySnapshot {
  summary: LLMObservabilitySummary;
  by_model: LLMObservabilityBreakdown[];
  by_step: LLMObservabilityBreakdown[];
  recent_calls: LLMObservabilityCall[];
}
