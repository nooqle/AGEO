'use client';

import { useCallback } from 'react';
import {
  RiAlarmWarningLine,
  RiErrorWarningLine,
  RiInformationLine,
  RiCloseLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';
import type { MonitoringAlert, AlertSeverity } from '@/types/monitoring';
import { SEVERITY_LABELS } from '@/types/monitoring';

// =========================================================================
// Severity visual configuration
// =========================================================================

const SEVERITY_CONFIG: Record<
  AlertSeverity,
  { color: string; Icon: typeof RiAlarmWarningLine }
> = {
  critical: { color: '#EF4444', Icon: RiAlarmWarningLine },
  high: { color: '#F59E0B', Icon: RiErrorWarningLine },
  medium: { color: '#3B82F6', Icon: RiInformationLine },
  low: { color: '#6B6B6B', Icon: RiInformationLine },
};

// =========================================================================
// Component
// =========================================================================

interface AlertCardProps {
  alert: MonitoringAlert;
  onRead?: (alertId: string) => void;
  onDismiss?: (alertId: string) => void;
  onClick?: (alert: MonitoringAlert) => void;
  className?: string;
}

export function AlertCard({
  alert,
  onRead,
  onDismiss,
  onClick,
  className,
}: AlertCardProps) {
  const isUnread = alert.status === 'unread';
  const config = SEVERITY_CONFIG[alert.severity];
  const IconComponent = config.Icon;

  const handleClick = useCallback(() => {
    if (isUnread && onRead) {
      onRead(alert.id);
    }
    onClick?.(alert);
  }, [alert, isUnread, onRead, onClick]);

  const handleDismiss = useCallback(
    (e: React.MouseEvent) => {
      e.stopPropagation();
      onDismiss?.(alert.id);
    },
    [alert.id, onDismiss]
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        handleClick();
      }
    },
    [handleClick]
  );

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMin = Math.floor(diffMs / 60_000);
    const diffHour = Math.floor(diffMs / 3_600_000);
    const diffDay = Math.floor(diffMs / 86_400_000);

    if (diffMin < 1) return '刚刚';
    if (diffMin < 60) return `${diffMin}分钟前`;
    if (diffHour < 24) return `${diffHour}小时前`;
    if (diffDay < 7) return `${diffDay}天前`;
    return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' });
  };

  return (
    <div
      role="article"
      aria-label={`${SEVERITY_LABELS[alert.severity]}级告警: ${alert.title}`}
      tabIndex={0}
      onClick={handleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        'group alert-card relative px-4 py-3 cursor-pointer transition-all duration-300 ease-out',
        isUnread ? 'alert-card-unread' : 'alert-card-read',
        className
      )}
      style={{
        borderLeft: `2px solid ${config.color}`,
        backgroundColor: isUnread ? 'var(--bg-tertiary)' : 'transparent',
      }}
    >
      <div className="flex items-start gap-3">
        {/* Severity icon */}
        <IconComponent
          className="w-4 h-4 mt-0.5 flex-shrink-0"
          style={{ color: config.color }}
        />

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-2">
            <div className="flex-1 min-w-0">
              <p
                className="text-sm font-medium truncate"
                style={{
                  color: isUnread ? 'var(--text-primary)' : 'var(--text-tertiary)',
                }}
              >
                {alert.title}
              </p>
              <p
                className="text-xs mt-0.5 line-clamp-2"
                style={{
                  color: isUnread ? 'var(--text-secondary)' : 'var(--text-muted)',
                }}
              >
                {alert.summary}
              </p>
            </div>

            {/* Dismiss button */}
            {onDismiss && (
              <button
                onClick={handleDismiss}
                className="p-1 rounded opacity-0 group-hover:opacity-100 hover:opacity-100 transition-opacity flex-shrink-0"
                style={{ color: 'var(--text-muted)' }}
                aria-label="忽略告警"
                onMouseEnter={(e) => {
                  e.currentTarget.style.backgroundColor = 'var(--bg-elevated)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.backgroundColor = 'transparent';
                }}
              >
                <RiCloseLine className="w-3.5 h-3.5" />
              </button>
            )}
          </div>

          {/* Metric change info */}
          {alert.previous_value != null && alert.current_value != null && (
            <div className="flex items-center gap-2 mt-1.5">
              <span
                className="text-xs px-1.5 py-0.5 rounded"
                style={{
                  backgroundColor: `${config.color}15`,
                  color: config.color,
                }}
              >
                {alert.metric_name}: {alert.previous_value.toFixed(1)} → {alert.current_value.toFixed(1)}
                {alert.change_percentage != null && (
                  <span className="ml-1">({alert.change_percentage > 0 ? '+' : ''}{alert.change_percentage.toFixed(1)}%)</span>
                )}
              </span>
            </div>
          )}

          {/* Entity + time */}
          <div className="flex items-center gap-2 mt-1.5">
            <span className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
              {alert.entity_name}
            </span>
            <span className="text-[11px]" style={{ color: 'var(--text-disabled)' }}>
              {formatTime(alert.created_at)}
            </span>
          </div>
        </div>

        {/* Unread indicator */}
        {isUnread && (
          <div
            className="w-2 h-2 rounded-full flex-shrink-0 mt-1.5"
            style={{ backgroundColor: 'var(--info)' }}
          />
        )}
      </div>
    </div>
  );
}
