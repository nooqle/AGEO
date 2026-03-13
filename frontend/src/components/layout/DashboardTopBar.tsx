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
      className="sticky top-0 z-30 flex h-14 items-center justify-between border-b px-5 lg:px-7"
      style={{
        backgroundColor: 'color-mix(in srgb, var(--bg-primary) 88%, #efe7dc 12%)',
        borderBottomColor: 'var(--border-subtle)',
        backdropFilter: 'blur(18px)',
      }}
    >
      <HomeBrandLink />

      <div className="flex items-center gap-2">
        <button
          onClick={onNewAnalysis ?? (() => router.push('/dashboard'))}
          className="flex items-center gap-1.5 rounded-full px-3.5 py-2 text-[12px] font-medium transition-opacity hover:opacity-90"
          style={{
            background: 'linear-gradient(180deg, color-mix(in srgb, var(--color-primary) 88%, #8092ff 12%), color-mix(in srgb, var(--color-primary) 74%, #4458d7 26%))',
            color: '#ffffff',
            boxShadow: '0 10px 22px rgba(54, 79, 124, 0.16)',
          }}
        >
          <RiAddLine className="h-3.5 w-3.5" />
          <span>新建品牌</span>
        </button>
        <ThemeToggle />
        <NotificationBell align="right" />
        <button
          onClick={() => router.push('/settings')}
          className="rounded-full p-2 transition-colors"
          style={{ color: 'var(--text-tertiary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.color = 'var(--text-tertiary)';
          }}
          title="设置"
        >
          <RiSettings4Line className="h-4.5 w-4.5" />
        </button>
      </div>
    </header>
  );
}
