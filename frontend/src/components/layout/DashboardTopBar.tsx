'use client';

import { useRouter } from 'next/navigation';
import { RiAddLine, RiSettings4Line } from '@remixicon/react';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { HomeBrandLink } from './HomeBrandLink';

interface DashboardTopBarProps {
  onNewAnalysis?: () => void;
}

export function DashboardTopBar({ onNewAnalysis }: DashboardTopBarProps) {
  const router = useRouter();

  return (
    <header
      className="sticky top-0 z-30 flex h-14 items-center justify-between border-b px-4 lg:px-7"
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderBottomColor: 'var(--border-subtle)',
      }}
    >
      <HomeBrandLink />

      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={onNewAnalysis ?? (() => router.push('/amwaychina'))}
          className="flex min-h-10 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-[12px] font-medium transition-opacity hover:opacity-90 sm:px-3.5"
          style={{
            background: 'var(--brand-primary)',
            color: 'var(--brand-contrast)',
            boxShadow: 'var(--shadow-sm)',
          }}
          aria-label="新建品牌"
        >
          <RiAddLine className="h-3.5 w-3.5" />
          <span className="hidden sm:inline">新建品牌</span>
        </button>
        <ThemeToggle />
        <NotificationBell align="right" />
        <button
          type="button"
          onClick={() => router.push('/settings')}
          className="h-10 w-10 rounded-lg p-2 transition-colors"
          style={{ color: 'var(--text-tertiary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }}
          aria-label="打开设置"
          title="设置"
        >
          <RiSettings4Line className="h-4.5 w-4.5" />
        </button>
      </div>
    </header>
  );
}
