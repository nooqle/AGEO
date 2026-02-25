'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import { RiCheckDoubleLine } from '@remixicon/react';
import { useAlertStore } from '@/stores/alertStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { AlertCard } from './AlertCard';
import type { MonitoringAlert } from '@/types/monitoring';

interface NotificationPanelProps {
  /** Alignment direction of the dropdown relative to the bell */
  align?: 'left' | 'right';
  className?: string;
}

export function NotificationPanel({ align = 'right', className }: NotificationPanelProps) {
  const router = useRouter();
  const panelRef = useRef<HTMLDivElement>(null);
  const {
    alerts,
    unreadCount,
    isLoading,
    isPanelOpen,
    closePanel,
    markRead,
    markAllRead,
    dismiss,
  } = useAlertStore();
  const { setSelectedBrandId } = useDashboardStore();

  // Close on Escape key
  useEffect(() => {
    if (!isPanelOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closePanel();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isPanelOpen, closePanel]);

  // Close on click outside
  useEffect(() => {
    if (!isPanelOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        // Also check if the click was on the bell button itself (handled by toggle)
        const bellButton = (e.target as HTMLElement).closest('[data-notification-bell]');
        if (!bellButton) {
          closePanel();
        }
      }
    };

    // Use timeout to avoid closing immediately on the same click that opened it
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 0);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isPanelOpen, closePanel]);

  // Track closing animation state
  const [isClosing, setIsClosing] = useState(false);
  // Keep panel mounted while the close animation plays
  const [shouldRender, setShouldRender] = useState(isPanelOpen);
  const [prevIsPanelOpen, setPrevIsPanelOpen] = useState(isPanelOpen);

  // Sync animation state with open/close transitions (derived state during render)
  if (prevIsPanelOpen !== isPanelOpen) {
    setPrevIsPanelOpen(isPanelOpen);
    if (isPanelOpen) {
      setIsClosing(false);
      setShouldRender(true);
    } else if (shouldRender) {
      setIsClosing(true);
    }
  }

  const handleAnimationEnd = useCallback(() => {
    if (isClosing) {
      setIsClosing(false);
      setShouldRender(false);
    }
  }, [isClosing]);

  // Close on route change
  useEffect(() => {
    closePanel();
  }, [router, closePanel]);

  const handleAlertClick = useCallback(
    (alert: MonitoringAlert) => {
      closePanel();
      // Navigate to dashboard with the entity selected and monitoring tab active
      setSelectedBrandId(alert.entity_id);
      router.push('/dashboard?tab=monitoring');
    },
    [closePanel, setSelectedBrandId, router]
  );

  const handleViewAll = useCallback(() => {
    closePanel();
    router.push('/dashboard?tab=monitoring');
  }, [closePanel, router]);

  if (!shouldRender) return null;

  return (
    <div
      ref={panelRef}
      role="region"
      aria-label="通知面板"
      aria-live="polite"
      onAnimationEnd={handleAnimationEnd}
      className={`absolute z-50 ${isClosing ? 'animate-panel-close' : 'animate-scale-in'} ${className ?? ''}`}
      style={{
        width: '380px',
        maxHeight: 'min(480px, calc(100vh - 80px))',
        top: '100%',
        marginTop: '8px',
        [align === 'right' ? 'right' : 'left']: 0,
        backgroundColor: 'var(--bg-secondary)',
        border: '1px solid var(--border-default)',
        borderRadius: '12px',
        boxShadow: '0 12px 40px rgba(0, 0, 0, 0.4)',
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3 flex-shrink-0"
        style={{ borderBottom: '1px solid var(--border-default)' }}
      >
        <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
          通知
          {unreadCount > 0 && (
            <span
              className="ml-1.5 text-xs font-normal"
              style={{ color: 'var(--text-tertiary)' }}
            >
              ({unreadCount}条未读)
            </span>
          )}
        </h3>
        {unreadCount > 0 && (
          <button
            onClick={markAllRead}
            className="flex items-center gap-1 text-xs transition-colors"
            style={{ color: 'var(--text-tertiary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--text-tertiary)';
            }}
          >
            <RiCheckDoubleLine className="w-3.5 h-3.5" />
            全部标记已读
          </button>
        )}
      </div>

      {/* Alert List */}
      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="py-8 text-center">
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              加载中...
            </span>
          </div>
        ) : alerts.length === 0 ? (
          <div className="py-12 text-center">
            <p className="text-sm" style={{ color: 'var(--text-tertiary)' }}>
              暂无通知
            </p>
            <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
              设置监测后将在此接收告警
            </p>
          </div>
        ) : (
          <div className="py-1">
            {alerts.slice(0, 6).map((alert) => (
              <AlertCard
                key={alert.id}
                alert={alert}
                onRead={markRead}
                onDismiss={dismiss}
                onClick={handleAlertClick}
              />
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      {alerts.length > 0 && (
        <div
          className="flex-shrink-0 px-4 py-2.5 text-center"
          style={{ borderTop: '1px solid var(--border-default)' }}
        >
          <button
            onClick={handleViewAll}
            className="text-xs font-medium transition-colors"
            style={{ color: 'var(--brand-primary)' }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = 'var(--brand-hover)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = 'var(--brand-primary)';
            }}
          >
            查看全部通知 →
          </button>
        </div>
      )}
    </div>
  );
}
