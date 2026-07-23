/**
 * Wave Switch / M2 (blueprint §1.3): product shell paths.
 * Primary workspace = production-line console. Legacy Dashboard is not the default shell.
 */

/** Canonical product home after login / primary CTA. */
export const PRODUCT_SHELL_HOME = '/amwaychina';

/** Legacy Dashboard+Chat shell (redirected; optional ?legacy=1 escape). */
export const LEGACY_DASHBOARD_PATH = '/dashboard';

/** Escape hatch for temporary legacy Dashboard access. */
export function legacyDashboardHref(): string {
  return `${LEGACY_DASHBOARD_PATH}?legacy=1`;
}

export function isLegacyDashboardAllowed(search: string | null | undefined): boolean {
  if (!search) return false;
  const qs = search.startsWith('?') ? search.slice(1) : search;
  return new URLSearchParams(qs).get('legacy') === '1';
}
