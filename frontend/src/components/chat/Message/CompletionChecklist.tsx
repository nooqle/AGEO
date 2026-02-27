'use client';

import { RiCheckLine, RiCloseLine } from '@remixicon/react';

interface ChecklistItem {
  id: string;
  label: string;
  status: 'completed' | 'in_progress' | 'pending' | 'failed';
}

interface CompletionChecklistProps {
  title?: string;
  items: ChecklistItem[];
}

const STATUS_ICONS = {
  completed: <RiCheckLine className="w-3.5 h-3.5 text-[#22C55E]" />,
  in_progress: (
    <div className="w-3.5 h-3.5 rounded-full border-2 border-[#6366F1] border-t-transparent animate-spin" />
  ),
  pending: <div className="w-3.5 h-3.5 rounded-full border border-[var(--border-subtle)]" />,
  failed: <RiCloseLine className="w-3.5 h-3.5 text-[#EF4444]" />,
};

export function CompletionChecklist({ title, items }: CompletionChecklistProps) {
  if (!items || items.length === 0) return null;

  const completedCount = items.filter((i) => i.status === 'completed').length;

  return (
    <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-xl p-4 mt-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-[var(--text-primary)]">
          {title || 'Analysis Progress'}
        </span>
        <span className="text-[10px] text-[var(--text-tertiary)]">
          {completedCount}/{items.length}
        </span>
      </div>

      {/* Progress bar */}
      <div className="h-1 bg-[var(--bg-tertiary)] rounded-full mb-3 overflow-hidden">
        <div
          className="h-full bg-[#6366F1] rounded-full transition-all duration-500"
          style={{ width: `${(completedCount / items.length) * 100}%` }}
        />
      </div>

      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.id} className="flex items-center gap-2">
            {STATUS_ICONS[item.status]}
            <span
              className={`text-xs ${
                item.status === 'completed'
                  ? 'text-[var(--text-secondary)] line-through'
                  : item.status === 'in_progress'
                  ? 'text-[var(--text-primary)]'
                  : item.status === 'failed'
                  ? 'text-[#EF4444]'
                  : 'text-[var(--text-tertiary)]'
              }`}
            >
              {item.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
