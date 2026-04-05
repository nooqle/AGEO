const ACCESS_TOKEN_KEY = 'access_token';

function getStorage() {
  if (typeof window === 'undefined') {
    return null;
  }
  return window.localStorage;
}

export function getStoredAccessToken() {
  return getStorage()?.getItem(ACCESS_TOKEN_KEY) ?? null;
}

export function setStoredAccessToken(token: string) {
  getStorage()?.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearStoredAccessToken() {
  getStorage()?.removeItem(ACCESS_TOKEN_KEY);
}
