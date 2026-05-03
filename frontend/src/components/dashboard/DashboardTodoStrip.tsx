'use client';

import { RiArrowRightLine } from '@remixicon/react';
import type { DashboardTodoItem } from '@/types/dashboard';

interface DashboardTodoStripProps {
  item?: DashboardTodoItem | null;
  onAction?: (item: DashboardTodoItem) => void;
}

export function DashboardTodoStrip({ item, onAction }: DashboardTodoStripProps) {
  if (!item) return null;

  return (
    <section
      className="grid gap-4 rounded-[18px] border px-5 py-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-center"
      style={{
        background: 'var(--status-warning-bg)',
        borderColor: 'color-mix(in srgb, var(--status-warning) 24%, var(--border-subtle) 76%)',
      }}
    >
      <div className="min-w-0">
        <div
          className="mb-2 inline-flex h-6 items-center rounded-full border px-2.5 text-[12px] font-semibold"
          style={{
            background: 'color-mix(in srgb, var(--bg-elevated) 70%, var(--status-warning-bg) 30%)',
            borderColor: 'color-mix(in srgb, var(--status-warning) 18%, var(--border-subtle) 82%)',
            color: 'var(--status-warning)',
          }}
        >
          待办
        </div>
        <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">{item.title}</h3>
        <p className="mt-1 text-[13px] leading-6 text-[var(--text-secondary)]">{item.description}</p>
      </div>

      <button
        type="button"
        onClick={() => onAction?.(item)}
        className="inline-flex min-h-9 items-center justify-center gap-1.5 rounded-[11px] border bg-[var(--bg-secondary)] px-3 text-[13px] font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
        style={{ borderColor: 'color-mix(in srgb, var(--status-warning) 20%, var(--border-subtle) 80%)' }}
      >
        {item.action_label || '处理'}
        <RiArrowRightLine className="h-4 w-4" />
      </button>
    </section>
  );
}
