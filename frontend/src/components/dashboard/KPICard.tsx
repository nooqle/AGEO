'use client';

import { useState } from 'react';
import { RiArrowDownLine, RiArrowRightLine, RiArrowUpLine } from '@remixicon/react';

interface KPICardProps {
  title: string;
  value: string | number;
  subtitle: string;
  trend: { value: number; isPositive: boolean; unit?: string } | null;
  sparklineData?: number[];
  tooltip?: string;
  actionLabel?: string;
  onClick?: () => void;
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 2) return null;

  const width = 72;
  const height = 22;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data
    .map((point, index) => {
      const x = (index / Math.max(data.length - 1, 1)) * width;
      const y = height - ((point - min) / range) * (height - 3) - 1.5;
      return `${x},${y}`;
    })
    .join(' ');

  return (
    <svg width={width} height={height} className="flex-shrink-0">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function KPICard({ title, value, subtitle, trend, sparklineData = [], tooltip, actionLabel, onClick }: KPICardProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const isInteractive = typeof onClick === 'function';
  const Container = isInteractive ? 'button' : 'div';

  return (
    <Container
      {...(isInteractive ? { type: 'button', onClick } : {})}
      className={`rounded-[16px] p-4 text-left ${isInteractive ? 'transition-transform hover:-translate-y-0.5 cursor-pointer' : ''}`}
      style={{
        background: 'linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0))',
        border: '1px solid var(--border-subtle)',
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
      <div className="mb-2 flex items-end justify-between gap-3">
        <div className="flex items-end gap-2">
          <span className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            {value}
          </span>
          {trend && (
            <span
              className="flex items-center text-xs font-medium"
              style={{ color: trend.isPositive ? 'var(--status-success)' : 'var(--status-error)' }}
            >
              {trend.isPositive ? <RiArrowUpLine className="w-3 h-3" /> : <RiArrowDownLine className="w-3 h-3" />}
              {trend.unit === '%' ? Math.abs(trend.value).toFixed(1) : Number.isInteger(trend.value) ? Math.abs(trend.value).toString() : Math.abs(trend.value).toFixed(1)}
              {trend.unit ?? ''}
            </span>
          )}
        </div>
        {sparklineData.length >= 2 ? (
          <div className="text-[var(--brand-primary)]">
            <Sparkline data={sparklineData} />
          </div>
        ) : null}
      </div>
      <div className="text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
        {subtitle}
      </div>
      {actionLabel && (
        <div className="mt-3 inline-flex items-center gap-1 text-xs font-medium" style={{ color: 'var(--brand-primary)' }}>
          {actionLabel}
          <RiArrowRightLine className="w-3 h-3" />
        </div>
      )}
    </Container>
  );
}
