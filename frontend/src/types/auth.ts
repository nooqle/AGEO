export type VerificationChannel = 'email' | 'phone';
export type VerificationPurpose = 'registration' | 'login' | 'invite_access' | 'bind_email' | 'bind_phone';

export interface AuthUser {
  id: string;
  email: string | null;
  phone: string | null;
  is_active: boolean;
  status: string | null;
  role: string | null;
  job_title: string | null;
  organization_id: string | null;
  organization_name?: string | null;
  created_at: string;
  updated_at?: string | null;
}

export interface VerificationSendCodeInput {
  channel: VerificationChannel;
  purpose: VerificationPurpose;
  target: string;
}

export interface VerificationSendCodeResponse {
  challenge_id: string;
  expires_in_seconds: number;
  debug_code?: string | null;
}

export interface OtpLoginInput {
  channel: VerificationChannel;
  target: string;
  verification_code: string;
}

export interface InvitationRedeemInput {
  email: string;
  invite_code: string;
}

export interface RegistrationApplicationCreateInput {
  email?: string | null;
  phone?: string | null;
  verification_channel: VerificationChannel;
  verification_target: string;
  verification_code: string;
  organization_name: string;
  job_title?: string;
  applicant_name?: string | null;
  company_size?: string | null;
  is_agency?: boolean;
}

export interface RegistrationApplication {
  id: string;
  email: string | null;
  phone: string | null;
  organization_name: string;
  job_title: string;
  applicant_name: string | null;
  company_size: string | null;
  is_agency: boolean;
  feature_flags?: Record<string, boolean> | null;
  status: string;
  review_note: string | null;
  reviewed_by_user_id: string | null;
  approved_user_id: string | null;
  assigned_organization_id: string | null;
  invite_code_issued_by_user_id: string | null;
  invite_code_sent_at: string | null;
  invite_redeemed_at: string | null;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}
