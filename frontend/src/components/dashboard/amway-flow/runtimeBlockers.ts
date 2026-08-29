export type RuntimeChildAttemptLike = {
  id?: string;
  platform?: string | null;
  action_type?: string | null;
  request_id?: string | null;
  status?: string | null;
  message?: string | null;
  action_hint?: string | null;
  error_message?: string | null;
  updated_at?: string | null;
  created_at?: string | null;
};

export type RuntimePlatformStateLike = {
  id?: string;
  platform?: string | null;
  action_type?: string | null;
  request_id?: string | null;
  status?: string | null;
  auth_state?: string | null;
  reason_code?: string | null;
  error_kind?: string | null;
  error_message?: string | null;
  questions_completed?: number | null;
  questions_total?: number | null;
  updated_at?: string | null;
  created_at?: string | null;
};

export type FlowRuntimeBlocker = {
  id: string;
  platform: string;
  actionType: string;
  requestId: string | null;
  status: 'waiting_input' | 'failed';
  message: string;
  actionHint: string | null;
  errorKind: string | null;
  errorMessage: string | null;
  questionsCompleted: number | null;
  questionsTotal: number | null;
};

function canonicalPlatform(value: string | null | undefined): string {
  const platform = String(value || '').trim().toLowerCase();
  return platform === 'yuanbao' ? 'hunyuan' : platform;
}

function attemptTimestamp(attempt: RuntimeChildAttemptLike): number {
  const value = attempt.updated_at || attempt.created_at;
  const timestamp = value ? Date.parse(value) : Number.NaN;
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

/**
 * Project the durable child-attempt history into one current blocker per
 * platform/action pair. Terminal successful/skipped attempts clear a prior
 * blocker; expired/failed attempts remain visible as final evidence.
 */
export function buildFlowRuntimeBlockers(
  attempts: RuntimeChildAttemptLike[] | null | undefined,
): FlowRuntimeBlocker[] {
  const latestByKey = new Map<string, RuntimeChildAttemptLike>();
  for (const attempt of attempts || []) {
    const platform = canonicalPlatform(attempt.platform);
    const actionType = String(attempt.action_type || 'browser_action').trim();
    if (!platform) continue;
    const key = `${platform}:${actionType}`;
    const current = latestByKey.get(key);
    if (!current || attemptTimestamp(attempt) >= attemptTimestamp(current)) {
      latestByKey.set(key, attempt);
    }
  }

  return [...latestByKey.values()]
    .map<FlowRuntimeBlocker | null>((attempt) => {
      const status = String(attempt.status || '').trim().toLowerCase();
      if (status !== 'waiting_input' && status !== 'expired' && status !== 'failed') {
        return null;
      }
      const platform = canonicalPlatform(attempt.platform);
      const actionType = String(attempt.action_type || 'browser_action').trim();
      return {
        id: String(attempt.id || attempt.request_id || `${platform}:${actionType}`),
        platform,
        actionType,
        requestId: String(attempt.request_id || '').trim() || null,
        status: status === 'waiting_input' ? 'waiting_input' : 'failed',
        message: String(attempt.message || '').trim(),
        actionHint: String(attempt.action_hint || '').trim() || null,
        errorKind: null,
        errorMessage: String(attempt.error_message || '').trim() || null,
        questionsCompleted: null,
        questionsTotal: null,
      } satisfies FlowRuntimeBlocker;
    })
    .filter((item): item is FlowRuntimeBlocker => item !== null)
    .sort((left, right) => left.platform.localeCompare(right.platform));
}

/**
 * Project authoritative per-platform fetch rows into visible blockers.  A
 * takeover-required row is the durable fallback when the WebSocket event was
 * missed; failed rows preserve final coverage and error kind after the task
 * itself reaches a terminal state.
 */
export function buildFlowPlatformStateBlockers(
  states: RuntimePlatformStateLike[] | null | undefined,
): FlowRuntimeBlocker[] {
  return (states || [])
    .map<FlowRuntimeBlocker | null>((state) => {
      const platform = canonicalPlatform(state.platform);
      if (!platform) return null;
      const status = String(state.status || '').trim().toLowerCase();
      const reasonCode = String(state.reason_code || '').trim().toLowerCase();
      const authState = String(state.auth_state || '').trim().toLowerCase();
      const waiting = status === 'takeover_required'
        || ((status === 'pending' || status === 'running')
          && (authState === 'needs_verify'
            || ['verify', 'captcha', 'security_confirmation', 'needs_verify'].includes(reasonCode)));
      const failed = status === 'failed';
      if (!waiting && !failed) return null;
      const actionType = String(state.action_type || 'browser_action').trim() || 'browser_action';
      return {
        id: String(state.id || state.request_id || `${platform}:${actionType}`),
        platform,
        actionType,
        requestId: String(state.request_id || '').trim() || null,
        status: waiting ? 'waiting_input' : 'failed',
        message: '',
        actionHint: null,
        errorKind: String(state.error_kind || '').trim() || null,
        errorMessage: String(state.error_message || '').trim() || null,
        questionsCompleted: Number.isFinite(state.questions_completed)
          ? Math.max(0, Number(state.questions_completed))
          : null,
        questionsTotal: Number.isFinite(state.questions_total)
          ? Math.max(0, Number(state.questions_total))
          : null,
      } satisfies FlowRuntimeBlocker;
    })
    .filter((item): item is FlowRuntimeBlocker => item !== null)
    .sort((left, right) => left.platform.localeCompare(right.platform));
}
