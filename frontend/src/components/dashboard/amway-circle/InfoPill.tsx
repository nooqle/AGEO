/**
 * Info pill chip used by association-circle surfaces (knife 6b, zero behavior).
 */

'use client';

export function InfoPill({
  label,
  value,
  tone = 'neutral',
}: {
  label: string;
  value: string;
  tone?: 'brand' | 'warning' | 'neutral';
}) {
  const className =
    tone === 'brand'
      ? 'border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
      : tone === 'warning'
        ? 'border-[var(--status-warning-bg)] bg-[var(--status-warning-bg)] text-[var(--text-secondary)]'
        : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  return (
    <span className={`rounded-full border px-3 py-1 ${className}`}>
      <span className="font-medium">{label}：</span>{value}
    </span>
  );
}
