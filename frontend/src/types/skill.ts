export type SkillTemplateKey =
  | 'analysis_report_skill'
  | 'confidence_signal_skill'
  | 'post_analysis_skill';

export interface SkillAssignment {
  id: string;
  skill_id: string;
  scope_kind: string;
  scope_ref: string | null;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface SkillVersion {
  id: string;
  skill_id: string;
  version: number;
  config_payload: Record<string, unknown>;
  created_at: string;
}

export interface SkillDefinition {
  id: string;
  skill_key: string;
  display_name: string;
  description: string;
  executor_kind: string;
  executor_ref: string;
  template_skill_key: string | null;
  intent_signals: string[];
  prerequisites: string[];
  artifact_types: string[];
  default_params: Record<string, unknown> | null;
  prompt_overlay: string | null;
  cost_class: string;
  latency_class: string;
  confirmation_policy: string;
  enabled: boolean;
  assignment_enabled: boolean;
  effective_enabled: boolean;
  is_builtin: boolean;
  version: number;
  created_at: string;
  updated_at: string;
  assignments: SkillAssignment[];
}

export interface CreateSkillInput {
  template_skill_key: SkillTemplateKey;
  display_name: string;
  description: string;
  default_params: Record<string, unknown> | null;
  prompt_overlay: string | null;
  enabled: boolean;
}

export interface UpdateSkillInput {
  display_name?: string;
  description?: string;
  default_params?: Record<string, unknown> | null;
  prompt_overlay?: string | null;
  enabled?: boolean;
}

export interface PublishSkillResponse {
  skill: SkillDefinition;
  published_version: SkillVersion;
}
