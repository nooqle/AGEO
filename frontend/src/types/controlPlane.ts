export interface ControlPlaneCustomerSummary {
  organization_id: string;
  customer_name: string;
  primary_account: string | null;
  member_count: number;
  brand_count: number;
  tokens_7d: number;
  cost_7d: number;
  active_task_count: number;
  last_active_at: string | null;
}

export interface ControlPlaneTaskSummary {
  task_id: string;
  brand_name: string;
  session_id: string | null;
  entity_id: string | null;
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
