export type DashboardChatHandoffPayload = Record<
  string,
  string | number | boolean | string[] | null | undefined
>;

const DASHBOARD_CHAT_HANDOFF_PREFIX = 'specta.dashboard.chat.handoff.';
const DASHBOARD_CHAT_HANDOFF_MAX_AGE_MS = 5 * 60 * 1000;
const DASHBOARD_CHAT_HANDOFF_CREATED_AT = 'created_at_ms';

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
  if (!raw) return null;
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
