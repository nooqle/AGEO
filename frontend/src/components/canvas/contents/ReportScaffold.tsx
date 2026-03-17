'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export function ReportPage({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn('mx-auto max-w-[1440px] space-y-6 px-6 py-6 md:px-8 md:py-8', className)}>{children}</div>;
}

export function ReportHero({
  eyebrow,
  title,
  badge,
  meta,
  note,
}: {
  eyebrow?: string;
  title: string;
  badge?: ReactNode;
  meta?: ReactNode;
  note?: ReactNode;
}) {
  return (
    <header
      className="rounded-[24px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-7"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-[var(--border-subtle)] pb-4">
        <div className="min-w-0 flex-1">
          {eyebrow ? (
            <div className="text-[11px] font-medium tracking-[0.16em] text-[var(--text-tertiary)]">{eyebrow}</div>
          ) : null}
          <h1 className="mt-3 text-[clamp(2rem,3.2vw,3rem)] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {title}
          </h1>
          {meta ? <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-[var(--text-secondary)]">{meta}</div> : null}
        </div>
        {badge}
      </div>

      {note ? (
        <div
          className="mt-4 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-3 text-[13px] leading-7 text-[var(--text-secondary)]"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          {note}
        </div>
      ) : null}
    </header>
  );
}

export function ReportSection({
  eyebrow,
  title,
  description,
  children,
  className,
  bodyClassName,
}: {
  eyebrow?: string;
  title?: string;
  description?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section
      className={cn('rounded-[24px] border bg-[var(--bg-tertiary)] p-6 md:p-7', className)}
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      {eyebrow || title || description ? (
        <div className="space-y-2">
          {eyebrow ? <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{eyebrow}</div> : null}
          {title ? <div className="text-[20px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">{title}</div> : null}
          {description ? <div className="text-[14px] leading-7 text-[var(--text-secondary)]">{description}</div> : null}
        </div>
      ) : null}
      <div className={cn(eyebrow || title || description ? 'mt-6' : '', bodyClassName)}>{children}</div>
    </section>
  );
}

export function ReportMetricCard({
  label,
  value,
  caption,
  badge,
  accent,
  className,
}: {
  label: string;
  value: ReactNode;
  caption?: ReactNode;
  badge?: ReactNode;
  accent?: string;
  className?: string;
}) {
  return (
    <div
      className={cn('rounded-[18px] border px-4 py-4', className)}
      style={{
        borderColor: 'var(--border-subtle)',
        background: accent
          ? `linear-gradient(180deg, ${accent}, transparent 110%), var(--bg-elevated)`
          : 'var(--bg-elevated)',
      }}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-[12px] text-[var(--text-tertiary)]">{label}</div>
          <div className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{value}</div>
        </div>
        {badge}
      </div>
      {caption ? <div className="mt-3 text-[13px] leading-6 text-[var(--text-secondary)]">{caption}</div> : null}
    </div>
  );
}
