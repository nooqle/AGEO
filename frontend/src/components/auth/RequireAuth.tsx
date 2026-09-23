'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import { ApiError } from '@/services/api-error';
import { getStoredAccessToken } from '@/lib/auth-storage';
import { redirectToLogin } from '@/lib/auth-expiry';
import type { AuthUser } from '@/types/auth';

interface RequireAuthProps {
  children: React.ReactNode | ((context: { currentUser: AuthUser }) => React.ReactNode);
}

export function RequireAuth({ children }: RequireAuthProps) {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);
  const [checkFailed, setCheckFailed] = useState(false);
  const [checkVersion, setCheckVersion] = useState(0);
  const isControlPlanePath = pathname?.startsWith('/control-plane');

  useEffect(() => {
    let cancelled = false;
    const token = getStoredAccessToken();
    const allowDevBypass = process.env.NODE_ENV === 'development';
    const nextPath = pathname || '/amwaychina';

    if (!token && (!allowDevBypass || isControlPlanePath)) {
      redirectToLogin(nextPath);
      return;
    }

    api.getMe()
      .then((user) => {
        if (cancelled) return;
        if (getStoredAccessToken() !== token) {
          setCheckVersion((version) => version + 1);
          return;
        }
        setCurrentUser(user);
        setIsChecking(false);
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (getStoredAccessToken() !== token) {
          if (getStoredAccessToken()) setCheckVersion((version) => version + 1);
          return;
        }
        // The API client handles a genuine /auth/me 401. Other failures are
        // temporary and must not discard a valid session.
        if (error instanceof ApiError && error.status === 401) return;
        setCurrentUser(null);
        setIsChecking(false);
        setCheckFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [checkVersion, isControlPlanePath, pathname]);

  if (checkFailed) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[var(--bg-primary)] px-4">
        <div role="alert" className="text-center text-sm text-[var(--text-secondary)]">
          <p>暂时无法校验账号状态，请检查网络后重试。</p>
          <button
            type="button"
            onClick={() => {
              setIsChecking(true);
              setCheckFailed(false);
              setCheckVersion((version) => version + 1);
            }}
            className="mt-4 rounded-lg bg-[var(--brand-primary)] px-4 py-2 font-medium text-[var(--brand-contrast)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--brand-primary)]"
          >
            重新校验
          </button>
        </div>
      </div>
    );
  }

  if (isChecking || !currentUser) {
    return (
      <div
        className="flex min-h-screen items-center justify-center"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div className="text-center">
          <div
            className="mx-auto mb-4 h-10 w-10 animate-spin rounded-full border-2"
            style={{
              borderColor: 'var(--border-subtle)',
              borderTopColor: 'var(--color-primary)',
            }}
          />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            正在校验账号状态...
          </p>
        </div>
      </div>
    );
  }

  if (typeof children === 'function') {
    return <>{children({ currentUser })}</>;
  }
  return <>{children}</>;
}
