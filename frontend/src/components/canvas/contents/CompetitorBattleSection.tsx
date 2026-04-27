import { cn } from '@/lib/cn';
import type { CompetitorBattleData } from '@/types/canvas';

interface CompetitorBattleSectionProps {
  data?: CompetitorBattleData | null;
}

const battleStatusLabel: Record<string, string> = {
  advantage: '我方占优',
  defend: '需要防守',
  contested: '激烈争夺',
  missing: '我方缺席',
};

const pressureLabel: Record<string, string> = {
  high: '高压力',
  medium: '中压力',
  low: '低压力',
};

const sentimentLabel: Record<string, string> = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
};

export function CompetitorBattleSection({ data }: CompetitorBattleSectionProps) {
  const summaryCards = data?.summary_cards ?? [];
  const items = data?.items ?? [];
  const hasContent = Boolean(data?.overview || summaryCards.length || items.length || data?.differentiation_strategy);

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5">
        <h2 className="text-[18px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '竞品争夺'}
        </h2>
        <p className="max-w-3xl text-[13px] leading-7 text-[var(--text-secondary)]">
          {data?.description || '这些关键场景里，品牌正在和竞品争夺用户心智。'}
        </p>
      </div>

      {!hasContent ? (
        <div className="mt-5 rounded-[18px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[13px] text-[var(--text-tertiary)]">
          暂无可判断的竞品争夺数据。
        </div>
      ) : (
        <>
          {data?.overview && (
            <div className="mt-5 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4 text-[13px] leading-7 text-[var(--text-secondary)]">
              {data.overview}
            </div>
          )}

          {summaryCards.length > 0 && (
            <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {summaryCards.map((card, index) => (
                <div key={`${card.competitor}-${index}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
                  <div className="flex items-center justify-between gap-3">
                    <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">{card.competitor}</h3>
                    {card.pressure_level && (
                      <span
                        className={cn(
                          'rounded-full px-2.5 py-1 text-[11px] font-medium',
                          card.pressure_level === 'high' && 'bg-red-500/10 text-red-400',
                          card.pressure_level === 'medium' && 'bg-amber-500/10 text-amber-400',
                          card.pressure_level === 'low' && 'bg-emerald-500/10 text-emerald-400'
                        )}
                      >
                        {pressureLabel[card.pressure_level] || card.pressure_level}
                      </span>
                    )}
                  </div>
                  <div className="mt-4 grid grid-cols-3 gap-2 text-center text-[11px]">
                    <div className="rounded-[14px] bg-[var(--bg-secondary)] px-2 py-3">
                      <div className="text-[var(--text-tertiary)]">共享场景</div>
                      <div className="mt-1 text-[14px] font-semibold text-[var(--text-primary)]">{card.shared_scenarios ?? '--'}</div>
                    </div>
                    <div className="rounded-[14px] bg-[var(--bg-secondary)] px-2 py-3">
                      <div className="text-[var(--text-tertiary)]">竞品独占</div>
                      <div className="mt-1 text-[14px] font-semibold text-[var(--text-primary)]">{card.competitor_only_scenarios ?? '--'}</div>
                    </div>
                    <div className="rounded-[14px] bg-[var(--bg-secondary)] px-2 py-3">
                      <div className="text-[var(--text-tertiary)]">我方独占</div>
                      <div className="mt-1 text-[14px] font-semibold text-[var(--text-primary)]">{card.brand_only_scenarios ?? '--'}</div>
                    </div>
                  </div>
                  {card.sentiment_summary && (
                    <div className="mt-4 flex flex-wrap gap-2 text-[11px]">
                      {(['positive', 'neutral', 'negative'] as const).map((key) => (
                        <span key={`${card.competitor}-${key}`} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 font-medium text-[var(--text-secondary)]">
                          {sentimentLabel[key]} {card.sentiment_summary?.[key] ?? 0}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {items.length > 0 && (
            <div className="mt-5 space-y-3.5">
              {items.map((item, index) => (
                <article key={item.scenario_id || `${item.scenario_label}-${index}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-[var(--text-primary)]">{item.scenario_label}</h3>
                    {item.battle_status && (
                      <span
                        className={cn(
                          'rounded-full px-2.5 py-1 text-[11px] font-medium',
                          item.battle_status === 'advantage' && 'bg-emerald-500/10 text-emerald-400',
                          item.battle_status === 'defend' && 'bg-amber-500/10 text-amber-400',
                          item.battle_status === 'contested' && 'bg-[var(--status-info-bg)] text-[var(--status-info)]',
                          item.battle_status === 'missing' && 'bg-red-500/10 text-red-400'
                        )}
                      >
                        {battleStatusLabel[item.battle_status] || item.battle_status}
                      </span>
                    )}
                  </div>

                  <div className="mt-4 grid gap-4 md:grid-cols-2">
                    <div>
                      <div className="text-[11px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">主要竞品</div>
                      <div className="mt-2.5 flex flex-wrap gap-2">
                        {(item.competitors_present ?? []).length > 0 ? (
                          item.competitors_present?.map((competitor) => (
                            <span key={competitor} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
                              {competitor}
                            </span>
                          ))
                        ) : (
                          <span className="text-[13px] text-[var(--text-tertiary)]">暂无</span>
                        )}
                      </div>
                    </div>
                    <div>
                      <div className="text-[11px] font-medium tracking-[0.12em] text-[var(--text-tertiary)]">当前占优品牌</div>
                      <div className="mt-2.5 text-[13px] font-medium text-[var(--text-primary)]">
                        {item.winner_brands && item.winner_brands.length > 0 ? item.winner_brands.join(' / ') : '--'}
                      </div>
                    </div>
                  </div>

                  {item.evidence && <p className="mt-4 text-[13px] leading-7 text-[var(--text-secondary)]">{item.evidence}</p>}
                  {item.recommended_focus && (
                    <p className="mt-3 text-[13px] leading-7 text-[var(--text-primary)]">建议聚焦：{item.recommended_focus}</p>
                  )}
                </article>
              ))}
            </div>
          )}

          {data?.differentiation_strategy && (
            <div className="mt-5 rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4 text-[13px] leading-7 text-[var(--text-secondary)]">
              <span className="font-medium text-[var(--text-primary)]">差异化建议：</span>
              {data.differentiation_strategy}
            </div>
          )}
        </>
      )}
    </section>
  );
}
