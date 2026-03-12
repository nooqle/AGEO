'use client';

import type { ReactNode } from 'react';

interface DashboardSectionHeaderProps {
  eyebrow?: string;
  title: string;
  action?: ReactNode;
}

export function DashboardSectionHeader({ eyebrow, title, action }: DashboardSectionHeaderProps) {
  return (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="min-w-0">
        {eyebrow ? (
          <div className="text-[10px] font-medium tracking-[0.14em]" style={{ color: 'var(--text-tertiary)' }}>
            {eyebrow}
          </div>
        ) : null}
        <h2 className={`${eyebrow ? 'mt-2' : ''} text-[20px] font-semibold tracking-[-0.03em]`} style={{ color: 'var(--text-primary)' }}>
          {title}
        </h2>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}
