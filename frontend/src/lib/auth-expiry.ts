'use client';

import { clearStoredAccessToken } from '@/lib/auth-storage';

const AUTH_REDIRECT_TOAST_KEY = 'specta-auth-redirect-toast';

let authRedirectInFlight = false;

export function queueAuthRedirectToast(message: string) {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    window.sessionStorage.setItem(AUTH_REDIRECT_TOAST_KEY, message);
  } catch {
    // Ignore storage failures and continue redirect flow.
  }
}

export function consumeAuthRedirectToast(): string | null {
  if (typeof window === 'undefined') {
    return null;
  }
  try {
    const message = window.sessionStorage.getItem(AUTH_REDIRECT_TOAST_KEY);
    if (!message) {
      return null;
    }
    window.sessionStorage.removeItem(AUTH_REDIRECT_TOAST_KEY);
    return message;
  } catch {
    return null;
  }
}

export function resolveAuthNextPath(nextPath: string | null | undefined, fallback: string): string {
  const rawPath = (nextPath || fallback).trim();
  if (!rawPath || !rawPath.startsWith('/') || rawPath.startsWith('//')) {
    return fallback;
  }

  if (rawPath.startsWith('/auth') || rawPath.startsWith('/control-plane/login')) {
    const nestedNext = new URL(rawPath, window.location.origin).searchParams.get('next');
    return nestedNext ? resolveAuthNextPath(nestedNext, fallback) : fallback;
  }

  return rawPath;
}

function buildLoginPath(nextPath?: string): string {
  if (typeof window === 'undefined') {
    return '/auth';
  }
  const currentPath =
    nextPath
    || `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const isControlPlane = currentPath.startsWith('/control-plane');
  const fallback = isControlPlane ? '/control-plane' : '/dashboard';
  const resolvedNextPath = resolveAuthNextPath(currentPath, fallback);
  const basePath = isControlPlane ? '/control-plane/login' : '/auth';
  return `${basePath}?next=${encodeURIComponent(resolvedNextPath)}`;
}

export function redirectToLoginForExpiredAuth(
  message: string = '您需要重新登录才能继续操作',
  nextPath?: string,
) {
  if (typeof window === 'undefined' || authRedirectInFlight) {
    return;
  }

  authRedirectInFlight = true;
  clearStoredAccessToken();
  queueAuthRedirectToast(message);
  window.location.replace(buildLoginPath(nextPath));
}

export function redirectToLogin(nextPath?: string) {
  if (typeof window === 'undefined' || authRedirectInFlight) {
    return;
  }
  authRedirectInFlight = true;
  clearStoredAccessToken();
  window.location.replace(buildLoginPath(nextPath));
}
