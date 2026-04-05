export type AioTakeoverMode = 'canvas_cdp' | 'vnc_fallback';

export type AioTakeoverState =
  | 'requested'
  | 'issued'
  | 'active'
  | 'resolved'
  | 'expired'
  | 'cancelled'
  | 'resume_failed';

export type AioResumeGateResult =
  | 'pass'
  | 'fail_login_required'
  | 'fail_captcha_required'
  | 'fail_ui_not_ready'
  | 'fail_state_corrupt'
  | 'fail_unknown';

export interface AioTakeoverAccessBundle {
  canvasConfigPath: string;
  vncUrlPath: string;
  heartbeatPath: string;
  resolvePath: string;
  cancelPath: string;
}

export interface AioTakeoverRecord {
  takeoverId: string;
  sessionId: string;
  platform: string;
  mode: AioTakeoverMode;
  reason: string;
  takeoverState: AioTakeoverState;
  frontendId?: string | null;
  requestedAt?: string | null;
  issuedAt?: string | null;
  expiresAt?: string | null;
  lastHeartbeatAt?: string | null;
  resumeGateResult?: string | null;
  accessBundle: AioTakeoverAccessBundle;
}

export interface AioCanvasConfig {
  mode: AioTakeoverMode;
  takeoverId: string;
  cdpEndpoint: string;
  expiresAt?: string | null;
  heartbeatIntervalMs: number;
}

export interface AioVncUrl {
  mode: AioTakeoverMode;
  takeoverId: string;
  url: string;
  expiresAt?: string | null;
  upstreamVncAvailable: boolean;
}
