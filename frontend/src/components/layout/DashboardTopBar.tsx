'use client';

import { useRouter } from 'next/navigation';
import { RiAddLine, RiSettings4Line } from '@remixicon/react';
import { NotificationBell } from '@/components/notifications/NotificationBell';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { ThemedLogo } from '@/components/ui/ThemedLogo';

interface DashboardTopBarProps {
  onNewAnalysis?: () => void;
}

export function DashboardTopBar({ onNewAnalysis }: DashboardTopBarProps) {
  const router = useRouter();

  return (
    <header
      className="h-14 sticky top-0 z-30 flex items-center justify-between px-6"
      style={{
        backgroundColor: 'var(--bg-primary)',
        borderBottom: '1px solid var(--border-default)',
      }}
    >
      {/* Left: Logo + Brand */}
      <div className="flex items-center gap-2.5">
        <ThemedLogo size={28} />
        <span
          className="text-sm font-semibold tracking-tight"
          style={{ color: 'var(--text-primary)' }}
        >
          Specta AI
        </span>
      </div>

      {/* Right: Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={onNewAnalysis ?? (() => router.push('/dashboard'))}
          className="btn-primary flex items-center gap-1.5 text-xs !py-1.5 !px-3"
        >
          <RiAddLine className="w-4 h-4" />
          <span>新建品牌</span>
        </button>
        <ThemeToggle />
        <NotificationBell align="right" />
        <button
          onClick={() => router.push('/settings')}
          className="p-2 rounded-lg transition-colors"
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
          <RiSettings4Line className="w-5 h-5" />
        </button>
      </div>
    </header>
  );
}
