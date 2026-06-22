'use client';

import { AlertTriangle, Check, Eye, RotateCcw, X } from 'lucide-react';
import styles from './BrandSpace.module.css';
import type { BrandSpaceGraphUpdate, GraphPatch, GraphPatchStatus } from '@/types/brandSpace';

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
  graphUpdate?: BrandSpaceGraphUpdate | null;
  graphVersion?: string;
  onPatchDecision?: (patchId: string, status: Extract<GraphPatchStatus, 'accepted' | 'rejected' | 'needs_review'>) => void;
  onPatchSelect?: (patchId: string) => void;
  selectedPatchId?: string;
  pendingPatchDecisionIds?: string[];
  compact?: boolean;
}

function classNames(...classes: Array<string | false | undefined>) {
  return classes.filter(Boolean).join(' ');
}

const statusOrder: GraphPatchStatus[] = ['needs_review', 'blocked', 'accepted', 'auto_applied', 'rejected'];

export function GraphUpdateQueue({
  patches,
  graphUpdate,
  graphVersion,
  onPatchDecision,
  onPatchSelect,
  selectedPatchId,
  pendingPatchDecisionIds = [],
  compact = false,
}: GraphUpdateQueueProps) {
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
  const versionLabel = graphUpdate?.after_graph_version ?? graphVersion ?? null;

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
          {versionLabel ? `图谱 ${versionLabel}` : '图谱待更新'}
        </span>
      </div>

      <div className="space-y-4">
        {statusOrder.map((status) => {
          const items = grouped[status];
          if (!items.length) return null;
          return (
            <div key={status}>
              <div className="mb-2 flex items-center gap-2">
                <span className="h-2 w-2 rounded-full" style={{ background: statusTone[status] }} aria-hidden />
                <h3 className="text-xs font-semibold text-[var(--text-secondary)]">{statusLabels[status]}</h3>
                <span className="text-[11px] text-[var(--text-tertiary)]">{items.length}</span>
              </div>
              <div className={classNames('grid gap-3', compact ? 'grid-cols-1' : 'xl:grid-cols-2')}>
                {items.map((patch) => {
                  const needsAction = patch.status === 'needs_review' || patch.status === 'blocked';
                  const isPending = pendingPatchDecisionIds.includes(patch.id);
                  const isSelected = selectedPatchId === patch.id;
                  return (
                    <article
                      key={patch.id}
                      className={classNames(
                        styles.queueItem,
                        needsAction && styles.queueAttention,
                        isSelected && styles.queueSelected,
                        'rounded-xl p-3',
                      )}
                    >
                      <button
                        type="button"
                        onClick={() => onPatchSelect?.(patch.id)}
                        className="block w-full text-left"
                        aria-label={`查看图谱补丁：${patch.title}，状态${statusLabels[patch.status]}`}
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
                            <h4 className="mt-2 text-sm font-semibold text-[var(--text-primary)]">{patch.title}</h4>
                            <p className="mt-1 text-xs leading-5 text-[var(--text-secondary)]">{patch.description}</p>
                          </div>
                          <div className="rounded-lg border px-2 py-1 text-xs font-semibold text-[var(--text-primary)]">
                            {patch.score}
                          </div>
                        </div>
                      </button>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-[var(--text-tertiary)]">
                        <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">{patchTypeLabels[patch.patchType] ?? patch.patchType}</span>
                        <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">
                          {patch.evidenceRefIds.length} 条证据
                        </span>
                        {patch.priority ? (
                          <span className="rounded-md bg-[var(--bg-tertiary)] px-2 py-1">
                            {patch.priority === 'high' ? '高优先级' : patch.priority === 'medium' ? '中优先级' : '低优先级'}
                          </span>
                        ) : null}
                      </div>

                      {needsAction && onPatchDecision ? (
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button
                            type="button"
                            disabled={isPending}
                            onClick={() => onPatchDecision(patch.id, 'accepted')}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg bg-[var(--brand-primary)] px-2.5 text-xs font-medium text-[var(--brand-contrast)] disabled:opacity-55"
                            aria-label={`接受补丁：${patch.title}`}
                          >
                            <Check className="h-3.5 w-3.5" />
                            {isPending ? '处理中' : '接受'}
                          </button>
                          <button
                            type="button"
                            disabled={isPending}
                            onClick={() => onPatchDecision(patch.id, 'needs_review')}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--text-secondary)] disabled:opacity-55"
                            aria-label={`保留审阅补丁：${patch.title}`}
                          >
                            <RotateCcw className="h-3.5 w-3.5" />
                            保留
                          </button>
                          <button
                            type="button"
                            disabled={isPending}
                            onClick={() => onPatchDecision(patch.id, 'rejected')}
                            className="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium text-[var(--error)] disabled:opacity-55"
                            aria-label={`拒绝补丁：${patch.title}`}
                          >
                            <X className="h-3.5 w-3.5" />
                            拒绝
                          </button>
                        </div>
                      ) : (
                        <div className="mt-3 flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
                          {patch.status === 'blocked' ? <AlertTriangle className="h-3.5 w-3.5" /> : <Eye className="h-3.5 w-3.5" />}
                          <span>{patch.reviewedAt ? '已记录审阅结果' : '从追溯面板查看证据'}</span>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
