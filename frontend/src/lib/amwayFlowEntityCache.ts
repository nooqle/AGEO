/**
 * Wave E3: short-lived in-memory cache + in-flight dedupe for production-line GETs.
 * Invalidated on recipe/topology writes. Not a persistence layer.
 */

type Entry<T> = {
  expiresAt: number;
  value?: T;
  inflight?: Promise<T>;
};

const store = new Map<string, Entry<unknown>>();

/** Default TTL: enough to absorb remount storms / dual-bar reloads */
export const FLOW_CACHE_TTL_MS = 12_000;

function now() {
  return Date.now();
}

export function flowCacheKey(parts: Array<string | number | null | undefined>): string {
  return parts.map((p) => String(p ?? '')).join('|');
}

export function invalidateFlowEntityCache(entityId: string): void {
  const prefix = `${entityId}|`;
  for (const key of store.keys()) {
    if (key === entityId || key.startsWith(prefix) || key.includes(`|${entityId}|`)) {
      store.delete(key);
    }
  }
  // keys are entity-first in helpers below
  for (const key of [...store.keys()]) {
    if (key.startsWith(`${entityId}|`)) store.delete(key);
  }
}

export async function getOrLoadFlowCache<T>(
  key: string,
  loader: () => Promise<T>,
  ttlMs: number = FLOW_CACHE_TTL_MS,
): Promise<T> {
  const hit = store.get(key) as Entry<T> | undefined;
  if (hit) {
    if (hit.value !== undefined && hit.expiresAt > now()) {
      return hit.value;
    }
    if (hit.inflight) {
      return hit.inflight;
    }
  }

  const inflight = loader()
    .then((value) => {
      store.set(key, { expiresAt: now() + ttlMs, value });
      return value;
    })
    .catch((err) => {
      store.delete(key);
      throw err;
    });

  store.set(key, { expiresAt: now() + ttlMs, inflight });
  return inflight;
}

/** Test / debug helper */
export function clearFlowEntityCacheAll(): void {
  store.clear();
}
