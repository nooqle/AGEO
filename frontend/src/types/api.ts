/**
 * API response types for Specta AI platform
 */

export interface Session {
  id: string;
  created_at: string;
  updated_at: string;
  user_id: string;
  status?: string;
  metadata?: Record<string, unknown>;
}

export interface Message {
  id: string;
  session_id: string;
  role: string;
  type?: string;
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
  output_type?: string;
  output_data?: Record<string, unknown>;
}

export interface Output {
  id: string;
  session_id: string;
  type: string;
  title: string;
  data: Record<string, unknown>;
  created_at: string;
}

export interface AgentControlResponse {
  success: boolean;
  message?: string;
}

export interface ConfirmationResponse {
  success: boolean;
  message?: string;
}
