'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import { clearStoredAccessToken, getStoredAccessToken } from '@/lib/auth-storage';
import type { AuthUser } from '@/types/auth';

interface RequireAuthProps {
  children: React.ReactNode | ((context: { currentUser: AuthUser }) => React.ReactNode);
}

export function RequireAuth({ children }: RequireAuthProps) {
  const router = useRouter();
  const pathname = usePathname();
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const token = getStoredAccessToken();
    const allowDevBypass = process.env.NODE_ENV === 'development';

    if (!token && !allowDevBypass) {
      router.replace(`/auth?next=${encodeURIComponent(pathname || '/dashboard')}`);
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
        clearStoredAccessToken();
        router.replace(`/auth?next=${encodeURIComponent(pathname || '/dashboard')}`);
      });

    return () => {
      cancelled = true;
    };
  }, [pathname, router]);

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
