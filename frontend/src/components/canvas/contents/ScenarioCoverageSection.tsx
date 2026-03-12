import { cn } from '@/lib/cn';
import type { ScenarioCoverageData } from '@/types/canvas';

interface ScenarioCoverageSectionProps {
  data?: ScenarioCoverageData | null;
}

const priorityLabel: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
};

const battleStatusLabel: Record<string, string> = {
  advantage: '已建立优势',
  defend: '需要防守',
  contested: '激烈争夺',
  missing: '我方缺席',
};

export function ScenarioCoverageSection({ data }: ScenarioCoverageSectionProps) {
  const items = data?.items ?? [];

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5">
        <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '有效场景'}
        </h2>
        <p className="max-w-3xl text-[13px] leading-7 text-[var(--text-secondary)]">
          {data?.description || '这些场景里，品牌已经建立了有效存在感。'}
        </p>
      </div>

      {data?.summary && (
        <div className="mt-5 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4 text-[13px] leading-7 text-[var(--text-secondary)]">
          {data.summary}
        </div>
      )}

      {items.length === 0 ? (
        <div className="mt-5 rounded-[18px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[13px] text-[var(--text-tertiary)]">
          暂无可确认的有效场景。完成场景分析后将展示品牌已建立优势的场景。
        </div>
      ) : (
        <div className="mt-5 space-y-3.5">
          {items.map((item, index) => (
            <article
              key={item.scenario_id || `${item.scenario_label}-${index}`}
              className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4"
            >
              <div className="flex flex-wrap items-center gap-2.5">
                <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">{item.scenario_label}</h3>
                {item.scenario_priority && (
                  <span className="rounded-full border px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                    {priorityLabel[item.scenario_priority] || item.scenario_priority}
                  </span>
                )}
                {item.battle_status && (
                  <span
                    className={cn(
                      'rounded-full px-2.5 py-1 text-[11px] font-medium',
                      item.battle_status === 'advantage' && 'bg-emerald-500/10 text-emerald-400',
                      item.battle_status === 'defend' && 'bg-amber-500/10 text-amber-400',
                      item.battle_status === 'contested' && 'bg-blue-500/10 text-blue-400',
                      item.battle_status === 'missing' && 'bg-red-500/10 text-red-400'
                    )}
                  >
                    {battleStatusLabel[item.battle_status] || item.battle_status}
                  </span>
                )}
              </div>

              <div className="mt-4 flex flex-wrap gap-2 text-[11px] font-medium">
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1',
                    item.brand_present ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400'
                  )}
                >
                  {item.brand_present ? '已进入回答' : '未进入回答'}
                </span>
                <span
                  className={cn(
                    'rounded-full px-2.5 py-1',
                    item.official_citation_present ? 'bg-blue-500/10 text-blue-400' : 'bg-[var(--bg-secondary)] text-[var(--text-secondary)]'
                  )}
                >
                  {item.official_citation_present ? '有官网引用' : '无官网引用'}
                </span>
              </div>

              {item.present_platforms && item.present_platforms.length > 0 && (
                <div className="mt-4 flex flex-wrap gap-2">
                  {item.present_platforms.map((platform) => (
                    <span key={platform} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
                      {platform}
                    </span>
                  ))}
                </div>
              )}

              {item.evidence && (
                <p className="mt-4 text-[13px] leading-7 text-[var(--text-secondary)]">{item.evidence}</p>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
