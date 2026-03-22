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
  family_skill_key: string;
  family_display_name: string;
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
  is_profile: boolean;
  version: number;
  package_key: string | null;
  package_display_name: string | null;
  package_description: string | null;
  package_path: string | null;
  created_at: string;
  updated_at: string;
  assignments: SkillAssignment[];
}

export interface UpdateSkillInput {
  display_name?: string;
  description?: string;
  default_params?: Record<string, unknown> | null;
  prompt_overlay?: string | null;
  enabled?: boolean;
  assignment_scope_kind?: string;
  assignment_scope_ref?: string | null;
}
