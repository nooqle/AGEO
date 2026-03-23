import type { ActionQueueData, ActionQueueItem } from '@/types/canvas';

interface ActionQueueSectionProps {
  data?: ActionQueueData | null;
}

function priorityRank(priority: ActionQueueItem['priority']): number {
  if (typeof priority === 'number') {
    return priority;
  }

  if (typeof priority !== 'string') {
    return 99;
  }

  const upper = priority.toUpperCase();
  if (/^P\d+$/.test(upper)) {
    return Number(upper.slice(1));
  }
  if (upper === 'HIGH') return 1;
  if (upper === 'MEDIUM') return 2;
  if (upper === 'LOW') return 3;
  return 99;
}

function formatPriority(priority: ActionQueueItem['priority']): string {
  if (priority === null || priority === undefined || priority === '') {
    return '待定';
  }

  return String(priority).toUpperCase();
}

export function ActionQueueSection({ data }: ActionQueueSectionProps) {
  const items = [...(data?.items ?? [])].sort((a, b) => priorityRank(a.priority) - priorityRank(b.priority));

  return (
    <section className="space-y-4">
      <div className="space-y-1">
        <h2 className="text-lg font-semibold text-[var(--text-primary)]">
          {data?.title || '下一步优化'}
        </h2>
        <p className="text-sm text-[var(--text-secondary)]">
          {data?.description || '建议优先处理的动作列表。'}
        </p>
      </div>

      {data?.summary && (
        <div className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4 text-sm leading-6 text-[var(--text-secondary)]">
          {data.summary}
        </div>
      )}

      {items.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-[var(--border-subtle)] px-4 py-8 text-sm text-[var(--text-tertiary)]">
          暂无可执行优化动作。待风险和场景判断完成后自动生成。
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item, index) => (
            <article
              key={item.action_id || `${item.title || item.action || 'action'}-${index}`}
              className="rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full bg-[var(--accent-primary,#6366F1)]/10 px-2 py-1 text-xs font-medium text-[var(--accent-primary,#6366F1)]">
                  {formatPriority(item.priority)}
                </span>
                <h3 className="text-base font-semibold text-[var(--text-primary)]">
                  {item.title || item.action || '待补充动作'}
                </h3>
                {item.status && (
                  <span className="rounded-full bg-[var(--bg-secondary)] px-2 py-1 text-xs text-[var(--text-secondary)]">
                    {item.status}
                  </span>
                )}
              </div>

              {item.scenario_label && (
                <div className="mt-3 text-sm text-[var(--text-secondary)]">目标场景：{item.scenario_label}</div>
              )}
              {item.action && item.title !== item.action && (
                <p className="mt-3 text-sm leading-6 text-[var(--text-primary)]">{item.action}</p>
              )}

              <div className="mt-3 grid gap-3 md:grid-cols-2">
                <div className="rounded-xl bg-[var(--bg-secondary)] p-3">
                  <div className="text-xs text-[var(--text-tertiary)]">优化目标</div>
                  <div className="mt-1 text-sm text-[var(--text-primary)]">{item.target || '--'}</div>
                </div>
                <div className="rounded-xl bg-[var(--bg-secondary)] p-3">
                  <div className="text-xs text-[var(--text-tertiary)]">预期指标</div>
                  <div className="mt-1 text-sm text-[var(--text-primary)]">{item.expected_metric || item.expected_impact || '--'}</div>
                </div>
              </div>

              {(item.related_competitors?.length || item.difficulty || item.timeline) && (
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-[var(--text-secondary)]">
                  {item.related_competitors?.map((competitor) => (
                    <span
                      key={competitor}
                      className="rounded-full border border-[var(--border-subtle)] px-2 py-1"
                    >
                      {competitor}
                    </span>
                  ))}
                  {item.difficulty && (
                    <span className="rounded-full bg-[var(--bg-secondary)] px-2 py-1">难度：{item.difficulty}</span>
                  )}
                  {item.timeline && (
                    <span className="rounded-full bg-[var(--bg-secondary)] px-2 py-1">时间：{item.timeline}</span>
                  )}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
