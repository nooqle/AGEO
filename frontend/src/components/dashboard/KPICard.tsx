'use client';

import { useState } from 'react';
import { RiArrowUpLine, RiArrowDownLine } from '@remixicon/react';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle: string;
  trend: { value: number; isPositive: boolean } | null;
  tooltip?: string;
}

export function KPICard({ title, value, subtitle, trend, tooltip }: KPICardProps) {
  const [showTooltip, setShowTooltip] = useState(false);

  return (
    <div
      className="rounded-xl p-4"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-default)',
      }}
    >
      <div
        className="text-xs uppercase tracking-wider mb-1 flex items-center gap-1.5"
        style={{ color: 'var(--text-tertiary)' }}
      >
        {title}
        {tooltip && (
          <span
            className="relative inline-flex"
            onMouseEnter={() => setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
          >
            <span
              className="w-3.5 h-3.5 rounded-full inline-flex items-center justify-center text-[9px] font-bold cursor-help"
              style={{
                border: '1px solid var(--text-muted)',
                color: 'var(--text-muted)',
              }}
            >
              ?
            </span>
            {showTooltip && (
              <span
                className="absolute left-1/2 -translate-x-1/2 bottom-full mb-2 px-3 py-2 rounded-lg text-xs font-normal normal-case tracking-normal z-50 pointer-events-none"
                style={{
                  background: 'var(--bg-tertiary, #262626)',
                  border: '1px solid var(--border-default, #404040)',
                  color: 'var(--text-primary, #E5E5E5)',
                  minWidth: '200px',
                  maxWidth: '340px',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
                  whiteSpace: 'pre-wrap',
                  lineHeight: '1.6',
                }}
              >
                {tooltip}
              </span>
            )}
          </span>
        )}
      </div>
      <div className="flex items-end gap-2">
        <span className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
          {value}
        </span>
        {trend && (
          <span
            className="flex items-center text-xs font-medium"
            style={{ color: trend.isPositive ? 'var(--status-success)' : 'var(--status-error)' }}
          >
            {trend.isPositive ? (
              <RiArrowUpLine className="w-3 h-3" />
            ) : (
              <RiArrowDownLine className="w-3 h-3" />
            )}
            {Math.abs(trend.value)}%
          </span>
        )}
      </div>
      <div className="text-xs mt-1" style={{ color: 'var(--text-tertiary)' }}>
        {subtitle}
      </div>
    </div>
  );
}
