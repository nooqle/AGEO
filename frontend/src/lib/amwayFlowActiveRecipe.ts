/** Session-scoped active recipe for run input_scope injection (Wave B2). */

export type ActiveRecipeSession = {
  id: string;
  name: string;
  dirty: boolean;
};

function key(entityId: string): string {
  return `amway-flow-active-recipe:${entityId}`;
}

export function readActiveRecipeSession(entityId: string): ActiveRecipeSession | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.sessionStorage.getItem(key(entityId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ActiveRecipeSession>;
    if (!parsed?.id || !parsed?.name) return null;
    return {
      id: String(parsed.id),
      name: String(parsed.name),
      dirty: Boolean(parsed.dirty),
    };
  } catch {
    return null;
  }
}

export function writeActiveRecipeSession(
  entityId: string,
  value: ActiveRecipeSession | null,
): void {
  if (typeof window === 'undefined') return;
  try {
    if (!value) window.sessionStorage.removeItem(key(entityId));
    else window.sessionStorage.setItem(key(entityId), JSON.stringify(value));
  } catch {
    // ignore
  }
}
