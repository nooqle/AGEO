export interface AdminUserRecord {
  id: string;
  email: string | null;
  phone: string | null;
  is_active: boolean;
  status: string;
  role: string;
  job_title: string | null;
  feature_flags: Record<string, boolean>;
  organization_id: string | null;
  organization_name: string | null;
  created_at: string;
  updated_at: string;
}

export interface AdminUserUpdateInput {
  email?: string | null;
  phone?: string | null;
  job_title?: string | null;
  is_active?: boolean;
  status?: string;
  organization_id?: string | null;
  feature_flags?: Record<string, boolean>;
}

export interface OrganizationRecord {
  id: string;
  legal_name: string;
  status: string;
  feature_flags: Record<string, boolean>;
  primary_account: string | null;
  member_count: number;
  entity_count: number;
  created_at: string;
  updated_at: string;
}

export interface OrganizationUpdateInput {
  legal_name?: string;
  status?: string;
  feature_flags?: Record<string, boolean>;
}

export interface AccountInvitationCreateInput {
  email: string;
  organization_id: string;
  applicant_name?: string | null;
  job_title?: string | null;
  feature_flags?: Record<string, boolean>;
}

export interface AccountInvitationResponse {
  status: string;
  email: string;
  feature_flags: Record<string, boolean>;
  user: AdminUserRecord | null;
  application: import('./auth').RegistrationApplication | null;
}
