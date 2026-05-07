'use client';

import Link from 'next/link';
import { useSyncExternalStore } from 'react';
import { RiArrowRightUpLine } from '@remixicon/react';
import { getStoredAccessToken } from '@/lib/auth-storage';

function subscribeToAuthChanges(onStoreChange: () => void) {
  window.addEventListener('storage', onStoreChange);
  return () => window.removeEventListener('storage', onStoreChange);
}

function readAuthSnapshot() {
  return Boolean(getStoredAccessToken());
}

export function HomeAuthLink() {
  const isSignedIn = useSyncExternalStore(
    subscribeToAuthChanges,
    readAuthSnapshot,
    () => false
  );

  if (isSignedIn) {
    return (
      <Link href="/dashboard" className="home-auth-link home-auth-link--signed-in">
        进入
        <RiArrowRightUpLine className="h-4 w-4" />
      </Link>
    );
  }

  return (
    <Link href="/auth?mode=login" className="home-auth-link home-auth-link--guest">
      登录
    </Link>
  );
}

export function HomeNavActions() {
  return (
    <div className="nav-actions">
      <HomeAuthLink />
      <Link href="/auth?mode=apply">
        申请体验
        <RiArrowRightUpLine className="h-4 w-4" />
      </Link>
    </div>
  );
}
