/**
 * WebSocket event data types for Specta AI platform
 */

export interface WebSocketEventData {
  // Progress event fields
  phase?: string;
  content?: string;
  is_complete?: boolean;
  stage?: string;
  stage_name?: string;
  current_step_index?: number;
  total_steps?: number;
  progress?: number;
  status?: string;
  message?: string;
  details?: string;

  // Step/task tracking
  steps?: Array<{
    id: string;
    status: string;
    name?: string;
    description?: string;
  }>;

  sub_tasks?: Array<{
    name: string;
    status: string;
    progress?: number;
  }>;

  // Error information
  error?: string;
  error_type?: string;
  recoverable?: boolean;

  // Output data
  output_type?: string;
  data?: Record<string, unknown>;
  title?: string;

  // Confirmation request
  step_id?: string;
  step_name?: string;
  options?: Array<{
    id: string;
    label: string;
    description?: string;
  }>;

  // Browser state / user action
  platform?: string;
  state?: string;
  requires_action?: boolean;
  action_type?: string;
  action_hint?: string;

  // Generic fields
  [key: string]: unknown;
}

export interface WebSocketMessage {
  event: string;
  data: WebSocketEventData;
  timestamp?: string;
}
