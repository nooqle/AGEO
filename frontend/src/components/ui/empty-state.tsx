'use client';

import type { ComponentType, CSSProperties } from 'react';
import { cn } from '@/lib/cn';

interface EmptyStateProps {
  icon?: ComponentType<{ className?: string; style?: CSSProperties }>;
  title: string;
  description?: string;
  action?: {
    label: string;
    onClick: () => void;
  };
  className?: string;
}

export function EmptyState({ icon: Icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cn('flex flex-col items-center justify-center py-16 px-4', className)}>
      {Icon && (
        <div
          className="w-14 h-14 rounded-2xl flex items-center justify-center mb-4"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <Icon className="w-7 h-7" style={{ color: 'var(--border-hover)' }} />
        </div>
      )}
      <p className="text-sm font-medium mb-1" style={{ color: 'var(--text-tertiary)' }}>
        {title}
      </p>
      {description && (
        <p className="text-xs text-center max-w-xs" style={{ color: 'var(--text-muted)' }}>
          {description}
        </p>
      )}
      {action && (
        <button
          onClick={action.onClick}
          className="mt-4 px-4 py-1.5 text-xs font-medium rounded-lg transition-colors"
          style={{
            color: 'var(--color-primary)',
            border: '1px solid rgba(99, 102, 241, 0.3)',
          }}
        >
          {action.label}
        </button>
      )}
    </div>
  );
}
