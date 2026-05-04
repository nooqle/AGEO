'use client';

import { useEffect, useRef } from 'react';
import { RiNotification3Line } from '@remixicon/react';
import { useAlertStore } from '@/stores/alertStore';
import { NotificationPanel } from './NotificationPanel';

interface NotificationBellProps {
  /** Alignment of the dropdown panel */
  align?: 'left' | 'right';
  className?: string;
}

export function NotificationBell({ align = 'right', className }: NotificationBellProps) {
  const { unreadCount, isPanelOpen, togglePanel, startPolling, stopPolling } =
    useAlertStore();
  const buttonRef = useRef<HTMLButtonElement | null>(null);

  // Start polling on mount, stop on unmount
  useEffect(() => {
    startPolling(60_000);
    return () => stopPolling();
  }, [startPolling, stopPolling]);

  const displayCount = unreadCount > 99 ? '99+' : String(unreadCount);
  const hasUnread = unreadCount > 0;

  return (
    <div className={`relative ${className ?? ''}`}>
      <button
        ref={buttonRef}
        data-notification-bell
        onClick={togglePanel}
        className="relative h-10 w-10 rounded-lg p-2 transition-colors"
        style={{
          color: hasUnread ? 'var(--text-secondary)' : 'var(--text-tertiary)',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)';
          e.currentTarget.style.color = 'var(--text-secondary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.backgroundColor = 'transparent';
          e.currentTarget.style.color = hasUnread
            ? 'var(--text-secondary)'
            : 'var(--text-tertiary)';
        }}
        aria-label={`通知${hasUnread ? `，${unreadCount}条未读` : ''}`}
        aria-haspopup="true"
        aria-expanded={isPanelOpen}
      >
        <RiNotification3Line className="w-5 h-5" />

        {/* Badge */}
        {hasUnread && (
          <span
            className="notification-badge absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] flex items-center justify-center rounded-full text-[10px] font-bold leading-none px-1"
            style={{
              backgroundColor: 'var(--error)',
              color: 'var(--brand-contrast)',
            }}
          >
            {displayCount}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      <NotificationPanel align={align} anchorRef={buttonRef} />
    </div>
  );
}
