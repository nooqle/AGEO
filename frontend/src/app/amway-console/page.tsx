'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function AmwayConsolePage() {
  const router = useRouter();

  useEffect(() => {
    router.replace('/amwaychina');
  }, [router]);

  return (
    <div className="min-h-screen bg-[var(--bg-secondary)] px-6 py-10 text-[var(--text-primary)]">
      <div className="mx-auto max-w-3xl rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
        正在进入安利中国专属 Console...
      </div>
    </div>
  );
}
