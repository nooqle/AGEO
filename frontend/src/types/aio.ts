export type AioTakeoverMode = 'canvas_cdp' | 'vnc_fallback';

export type AioTakeoverState =
  | 'requested'
  | 'issued'
  | 'active'
  | 'resolved'
  | 'expired'
  | 'cancelled'
  | 'resume_failed';

export interface AioTakeoverAccessBundle {
  openPath?: string | null;
  canvasConfigPath: string;
  vncUrlPath: string;
  heartbeatPath: string;
  resolvePath: string;
  cancelPath: string;
  actionType?: string | null;
  reasonCode?: string | null;
  targetUrl?: string | null;
  blockingUrl?: string | null;
  blockingFingerprint?: string | null;
}

export interface AioTakeoverRecord {
  takeoverId: string;
  sessionId: string;
  platform: string;
  mode: AioTakeoverMode;
  reason: string;
  takeoverState: AioTakeoverState;
  actionType?: string | null;
  reasonCode?: string | null;
  frontendId?: string | null;
  requestedAt?: string | null;
  issuedAt?: string | null;
  expiresAt?: string | null;
  lastHeartbeatAt?: string | null;
  targetUrl?: string | null;
  blockingUrl?: string | null;
  blockingFingerprint?: string | null;
  accessBundle: AioTakeoverAccessBundle;
}

export interface AioCanvasConfig {
  mode: AioTakeoverMode;
  takeoverId: string;
  cdpEndpoint: string;
  expiresAt?: string | null;
  heartbeatIntervalMs: number;
  targetUrl?: string | null;
}

export interface AioVncUrl {
  mode: AioTakeoverMode;
  takeoverId: string;
  url: string;
  expiresAt?: string | null;
  upstreamVncAvailable: boolean;
}
