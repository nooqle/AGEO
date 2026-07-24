/**
 * Association projection loading panel (knife 6b, zero behavior).
 */

'use client';

import { RefreshCw } from 'lucide-react';

export function AssociationProjectionLoadingPanel({ centerTerm }: { centerTerm: string }) {
  return (
    <section className="amway-surface rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] p-8">
      <div className="mx-auto flex max-w-3xl flex-col items-center text-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--brand-border)] bg-[var(--brand-bg)] text-[var(--brand-primary)]">
          <RefreshCw size={20} className="animate-spin" />
        </div>
        <h2 className="mt-5 text-2xl font-semibold">{centerTerm}圈层报告读取中</h2>
        <p className="mt-3 text-sm leading-7 text-[var(--text-secondary)]">
          正在读取最近一次图谱、报告和证据链。读取完成前不会展示空态，也不会把已有结果误判为未生成。
        </p>
      </div>
    </section>
  );
}
