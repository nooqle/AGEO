'use client';

import { AlertTriangle, Check, Eye, RotateCcw, X } from 'lucide-react';
import styles from './BrandSpace.module.css';
import type { GraphPatch, GraphPatchStatus } from '@/types/brandSpace';

const statusLabels: Record<GraphPatchStatus, string> = {
  auto_applied: '自动应用',
  needs_review: '待审阅',
  accepted: '已接受',
  rejected: '已拒绝',
  blocked: '已阻断',
};

const statusTone: Record<GraphPatchStatus, string> = {
  auto_applied: 'var(--success)',
  needs_review: 'var(--warning)',
  accepted: 'var(--brand-primary)',
  rejected: 'var(--text-tertiary)',
  blocked: 'var(--error)',
};

const patchTypeLabels: Record<string, string> = {
  update_strength: '更新强度',
  add_risk_relation: '新增风险关系',
  add_competitor_relation: '新增竞品关系',
  add_entity: '新增实体',
};

interface GraphUpdateQueueProps {
  patches: GraphPatch[];
  onPatchDecision?: (patchId: string, status: Extract<GraphPatchStatus, 'accepted' | 'rejected' | 'needs_review'>) => void;
  compact?: boolean;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

export function GraphUpdateQueue({ patches, onPatchDecision, compact = false }: GraphUpdateQueueProps) {
  const grouped = patches.reduce<Record<GraphPatchStatus, GraphPatch[]>>(
    (acc, patch) => {
      acc[patch.status].push(patch);
      return acc;
    },
    {
      auto_applied: [],
      needs_review: [],
      accepted: [],
      rejected: [],
      blocked: [],
    },
  );

  return (
    <section className={classNames(styles.surface, 'rounded-xl p-4')}>
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">图谱更新队列</h2>
          <p className="mt-1 text-xs text-[var(--text-secondary)]">
            {patches.length} 个补丁 · {grouped.needs_review.length + grouped.blocked.length} 个需要处理
          </p>
        </div>
        <span className="rounded-lg border px-2.5 py-1 text-xs text-[var(--brand-text)]" style={{ borderColor: 'var(--brand-border)', background: 'var(--brand-bg)' }}>
          图谱 v3.2.1
        </span>
      </div>

      <div className={classNames('grid gap-3', compact ? 'grid-cols-1' : 'xl:grid-cols-2')}>
        {patches.map((patch) => {
          const needsAction = patch.status === 'needs_review' || patch.status === 'blocked';
          return (
            <article
              key={patch.id}
              className={classNames(
                styles.queueItem,
                needsAction && styles.queueAttention,
                'rounded-xl p-3',
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2 w-2 rounded-full"
                      style={{ background: statusTone[patch.status] }}
                      aria-hidden
                    />
                    <span className="text-[11px] font-medium uppercase text-[var(--text-tertiary)]">
                      {statusLabels[patch.status]}
                    </span>
                  </div>
                  <h3 className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{patch.title}</h3>
                  <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{patch.description}</p>
                </div>
                <div className="rounded-lg border px-2 py-1 text-xs font-semibold text-[var(--text-primary)]">
                  {patch.score}
                </div>
              </div>

              <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">{patchTypeLabels[patch.patchType] ?? patch.patchType}</span>
                <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">
                  {patch.evidenceRefIds.length} 条证据
                </span>
              </div>

              {needsAction && onPatchDecision ? (
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => onPatchDecision(patch.id, 'accepted')}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-2.5 text-xs font-medium text-[var(--brand-contrast)]"
                  >
                    <Check className="h-3.5 w-3.5" />
                    接受
                  </button>
                  <button
                    type="button"
                    onClick={() => onPatchDecision(patch.id, 'needs_review')}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--text-secondary)]"
                  >
                    <RotateCcw className="h-3.5 w-3.5" />
                    保留
                  </button>
                  <button
                    type="button"
                    onClick={() => onPatchDecision(patch.id, 'rejected')}
                    className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--error)]"
                  >
                    <X className="h-3.5 w-3.5" />
                    拒绝
                  </button>
                </div>
              ) : (
                <div className="mt-3 flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                  {patch.status === 'blocked' ? <AlertTriangle className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                  <span>从追溯面板查看证据</span>
                </div>
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
