const ACCESS_TOKEN_KEY = 'access_token';
const ACCESS_TOKEN_COOKIE = 'specta_access_token';
const ACCESS_TOKEN_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24;

function getStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

export function getStoredAccessToken() {
  const token = getStorage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
  if (token) {
    syncAccessTokenCookie(token);
  }
  return token;
}

function syncAccessTokenCookie(token: string | null) {
  if (typeof document === 'undefined') {
    return;
  }

  const secure = window.location.protocol === 'https:' ? '; Secure' : '';
  if (!token) {
    document.cookie = `${ACCESS_TOKEN_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax${secure}`;
    return;
  }

  document.cookie = `${ACCESS_TOKEN_COOKIE}=${encodeURIComponent(token)}; Path=/; Max-Age=${ACCESS_TOKEN_COOKIE_MAX_AGE_SECONDS}; SameSite=Lax${secure}`;
}

export function setStoredAccessToken(token: string) {
  getStorage()?.setItem(ACCESS_TOKEN_KEY, token);
  syncAccessTokenCookie(token);
}

export function clearStoredAccessToken() {
  getStorage()?.removeItem(ACCESS_TOKEN_KEY);
  syncAccessTokenCookie(null);
}
