export type DashboardChatHandoffPayload = Record<
  string,
  string | number | boolean | string[] | null | undefined
>;

const DASHBOARD_CHAT_HANDOFF_PREFIX = 'specta.dashboard.chat.handoff.';
const DASHBOARD_CHAT_HANDOFF_MAX_AGE_MS = 5 * 60 * 1000;
const DASHBOARD_CHAT_HANDOFF_REPLAY_MS = 15 * 1000;
const DASHBOARD_CHAT_HANDOFF_CREATED_AT = 'created_at_ms';
const SAFE_DASHBOARD_CHAT_QUERY_KEYS = new Set([
  'entity_id',
  'brand',
  'entry_source',
  'monitor_mode',
  'question_set_label',
  'sample_summary',
  'current_metrics',
  'run_id',
  'handoff_id',
  'intent',
  'task_title',
  'task_goal',
  'clean_handoff',
  'ai_sources',
  'monitoring_plan_id',
  'question_set_ids',
  'endpoint_ids',
  'monitoring_run_id',
  'error_stage',
  'artifact_id',
  'output_id',
]);

const recentlyConsumedHandoffs = new Map<
  string,
  { expiresAt: number; payload: DashboardChatHandoffPayload }
>();

function handoffKey(sessionId: string): string {
  return `${DASHBOARD_CHAT_HANDOFF_PREFIX}${sessionId}`;
}

function getSessionStorage(): Storage | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

export function writeDashboardChatHandoff(
  sessionId: string,
  payload: DashboardChatHandoffPayload,
): boolean {
  const storage = getSessionStorage();
  if (!storage) return false;
  try {
    storage.setItem(
      handoffKey(sessionId),
      JSON.stringify({
        ...payload,
        [DASHBOARD_CHAT_HANDOFF_CREATED_AT]: Date.now(),
      }),
    );
    return true;
  } catch {
    return false;
  }
}

export function consumeDashboardChatHandoff(
  sessionId: string,
): DashboardChatHandoffPayload | null {
  const storage = getSessionStorage();
  if (!storage) return null;

  const key = handoffKey(sessionId);
  const raw = storage.getItem(key);
  if (!raw) {
    const cached = recentlyConsumedHandoffs.get(key);
    if (!cached) return null;
    if (Date.now() > cached.expiresAt) {
      recentlyConsumedHandoffs.delete(key);
      return null;
    }
    return cached.payload;
  }
  storage.removeItem(key);

  try {
    const parsed = JSON.parse(raw) as DashboardChatHandoffPayload;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return null;
    }

    const createdAt = parsed[DASHBOARD_CHAT_HANDOFF_CREATED_AT];
    if (
      typeof createdAt === 'number' &&
      Number.isFinite(createdAt) &&
      Date.now() - createdAt > DASHBOARD_CHAT_HANDOFF_MAX_AGE_MS
    ) {
      return null;
    }

    recentlyConsumedHandoffs.set(key, {
      expiresAt: Date.now() + DASHBOARD_CHAT_HANDOFF_REPLAY_MS,
      payload: parsed,
    });
    return parsed;
  } catch {
    return null;
  }
}

export function readDashboardChatHandoffValue(
  payload: DashboardChatHandoffPayload | null,
  key: string,
): string | null {
  if (!payload) return null;
  const value = payload[key];
  if (typeof value === 'string') {
    const normalized = value.trim();
    return normalized || null;
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    return String(value);
  }
  if (Array.isArray(value)) {
    const normalized = value.filter((item): item is string => typeof item === 'string');
    return normalized.length > 0 ? normalized.join(',') : null;
  }
  return null;
}

export function isDashboardChatHandoffAutosend(
  payload: DashboardChatHandoffPayload | null,
): boolean {
  if (!payload) return false;
  const value = payload.autosend;
  return value === true || value === '1' || value === 'true';
}

export function buildSafeDashboardChatQuery(
  payload: DashboardChatHandoffPayload,
): URLSearchParams {
  const params = new URLSearchParams();
  Object.entries(payload).forEach(([key, value]) => {
    if (!SAFE_DASHBOARD_CHAT_QUERY_KEYS.has(key)) return;
    if (typeof value === 'string') {
      const normalized = value.trim();
      if (normalized) params.set(key, normalized);
      return;
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
      params.set(key, String(value));
      return;
    }
    if (typeof value === 'boolean') {
      params.set(key, value ? '1' : '0');
      return;
    }
    if (Array.isArray(value)) {
      const normalized = value.filter((item): item is string => typeof item === 'string');
      if (normalized.length) params.set(key, normalized.join(','));
    }
  });
  if (params.size > 0) {
    params.set('handoff', '1');
  }
  return params;
}

export function buildDashboardChatUrlWithHandoff(
  sessionId: string,
  payload: DashboardChatHandoffPayload,
): string {
  const safeQuery = buildSafeDashboardChatQuery(payload);
  const query = safeQuery.toString();
  const safeUrl = `/chat/${sessionId}${query ? `?${query}` : ''}`;
  if (writeDashboardChatHandoff(sessionId, payload)) {
    return safeUrl;
  }
  return safeUrl;
}
