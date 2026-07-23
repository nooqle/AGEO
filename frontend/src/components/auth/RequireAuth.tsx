'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import { getStoredAccessToken } from '@/lib/auth-storage';
import { redirectToLogin, redirectToLoginForExpiredAuth } from '@/lib/auth-expiry';
import type { AuthUser } from '@/types/auth';

interface RequireAuthProps {
  children: React.ReactNode | ((context: { currentUser: AuthUser }) => React.ReactNode);
}

export function RequireAuth({ children }: RequireAuthProps) {
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);
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
        setCurrentUser(user);
        setIsChecking(false);
      })
      .catch(() => {
        if (cancelled) return;
        redirectToLoginForExpiredAuth('您需要重新登录才能继续操作', nextPath);
      });

    return () => {
      cancelled = true;
    };
  }, [isControlPlanePath, pathname]);

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
