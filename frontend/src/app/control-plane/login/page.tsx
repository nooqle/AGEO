'use client';

import Link from 'next/link';
import { Suspense, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiShieldUserLine,
} from '@remixicon/react';

import { api } from '@/services/api';
import { clearStoredAccessToken, getStoredAccessToken } from '@/lib/auth-storage';
import type { AuthUser } from '@/types/auth';

function ControlPlaneLoginContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = useMemo(
    () => searchParams.get('next') || '/control-plane',
    [searchParams]
  );
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [checking, setChecking] = useState(() => !!getStoredAccessToken());

  useEffect(() => {
    let cancelled = false;
    const token = getStoredAccessToken();
    if (!token) {
      return;
    }

    api.getMe()
      .then((user) => {
        if (cancelled) return;
        if (user.role === 'internal_admin') {
          router.replace(nextPath);
          return;
        }
        setCurrentUser(user);
        setChecking(false);
      })
      .catch(() => {
        if (cancelled) return;
        clearStoredAccessToken();
        setChecking(false);
      });

    return () => {
      cancelled = true;
    };
  }, [nextPath, router]);

  if (checking) {
    return (
      <main
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
            正在进入运营后台...
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <div className="mx-auto flex min-h-screen max-w-3xl items-center px-4 py-10 lg:px-8">
        <div
          className="w-full rounded-[32px] border px-6 py-7 shadow-[0_24px_80px_rgba(35,31,26,0.08)] lg:px-8 lg:py-9"
          style={{
            borderColor: 'var(--border-subtle)',
            backgroundColor: 'color-mix(in srgb, var(--bg-secondary) 95%, white 5%)',
          }}
        >
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition-colors"
            style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
          >
            <RiArrowLeftLine className="h-3.5 w-3.5" />
            返回首页
          </Link>

          <div className="mt-8 flex items-center gap-3">
            <span
              className="inline-flex h-12 w-12 items-center justify-center rounded-2xl text-white"
              style={{ backgroundColor: 'var(--color-primary)' }}
            >
              <RiShieldUserLine className="h-6 w-6" />
            </span>
            <div>
              <div className="text-xs tracking-[0.2em]" style={{ color: 'var(--text-tertiary)' }}>
                SPECTA OPS
              </div>
              <h1 className="mt-1 text-3xl font-semibold tracking-[-0.04em]">
                运营后台登录
              </h1>
            </div>
          </div>

          <div className="mt-6 space-y-3 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
            <p>内部管理员通过邮箱验证码登录后进入运营后台。</p>
            <p>客户账号登录后不会进入这里。</p>
            {currentUser && currentUser.role !== 'internal_admin' ? (
              <div
                className="rounded-[18px] border px-4 py-3"
                style={{
                  borderColor: 'rgba(191, 146, 91, 0.22)',
                  backgroundColor: 'rgba(191, 146, 91, 0.08)',
                }}
              >
                当前账号没有运营后台权限。
              </div>
            ) : null}
          </div>

          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href={`/auth?next=${encodeURIComponent(nextPath)}`}
              className="inline-flex items-center gap-2 rounded-[18px] px-4 py-3 text-sm font-medium text-white"
              style={{
                background:
                  'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 88%, #8092ff 12%), color-mix(in srgb, var(--color-primary) 74%, #4458d7 26%))',
              }}
            >
              前往登录
              <RiArrowRightLine className="h-4 w-4" />
            </Link>
            <Link
              href="/auth"
              className="inline-flex items-center gap-2 rounded-[18px] border px-4 py-3 text-sm font-medium"
              style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
            >
              打开统一登录页
            </Link>
          </div>

          <div className="mt-8 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            后台地址：/control-plane/login
          </div>
        </div>
      </div>
    </main>
  );
}

export default function ControlPlaneLoginPage() {
  return (
    <Suspense>
      <ControlPlaneLoginContent />
    </Suspense>
  );
}
