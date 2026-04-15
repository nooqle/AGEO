import type { BrowserState, ExecutionProgress, ProgressStep, TPAORPhase } from '@/types/agent';
import type { WebSocketEventData } from '@/types/websocket';

export interface WebSocketMessage {
  event: string;
  data: WebSocketEventData;
}

export function isValidWebSocketMessage(message: unknown): message is WebSocketMessage {
  if (!message || typeof message !== 'object') {
    return false;
  }

  const msg = message as Record<string, unknown>;
  return typeof msg.event === 'string' && !!msg.event && 'data' in msg;
}

export function mapStepStatus(status: string | undefined): ProgressStep['status'] {
  switch (status) {
    case 'completed':
      return 'completed';
    case 'in_progress':
    case 'running':
      return 'in_progress';
    case 'error':
      return 'error';
    case 'skipped':
      return 'skipped';
    default:
      return 'pending';
  }
}

export const TPAOR_PHASE_MAP: Record<string, string> = {
  '\u601d\u8003': 'thought',
  '\u89c4\u5212': 'plan',
  '\u884c\u52a8': 'action',
  '\u89c2\u5bdf': 'observation',
  '\u56de\u590d': 'response',
};

export const TPAOR_PHASES: TPAORPhase[] = ['thought', 'plan', 'action', 'observation', 'response'];
export const EXECUTION_STATUSES: ExecutionProgress['status'][] = ['pending', 'running', 'completed', 'failed'];
export const BROWSER_STATES: BrowserState['state'][] = [
  'idle',
  'initializing',
  'navigating',
  'checking_login',
  'waiting_for_login',
  'waiting_for_modal',
  'logged_in',
  'enabling_search',
  'waiting_response',
  'extracting',
  'completed',
  'error',
];
export const BROWSER_PLATFORMS: BrowserState['platform'][] = [
  'kimi',
  'deepseek',
  'doubao',
  'yuanbao',
];
