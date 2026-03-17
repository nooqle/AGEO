import { getPlatformDisplayName } from '@/lib/platformLabel';
import type { ReportMentionSectionData } from '@/types/canvas';
import { ReportMetricCard, ReportSection } from './ReportScaffold';

interface ReportMentionSectionProps {
  data?: ReportMentionSectionData | null;
  brandName?: string;
}

const sentimentLabel: Record<string, string> = {
  positive: '正向提及',
  neutral: '中性提及',
  negative: '负向提及',
};

const sentimentTone: Record<string, string> = {
  positive: 'bg-emerald-500/12 text-emerald-700 border-emerald-500/20',
  neutral: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
  negative: 'bg-rose-500/12 text-rose-700 border-rose-500/20',
};

function formatRate(value: number | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

export function ReportMentionSection({ data, brandName }: ReportMentionSectionProps) {
  const groups = (data?.groups ?? []).filter((group) => group.brand_count > 0);

  return (
    <ReportSection title={data?.title || '提及率分析'}>
      <div className="grid gap-3 md:grid-cols-3">
        <ReportMetricCard label="提及率" value={formatRate(data?.mention_rate)} />
        <ReportMetricCard label={`${brandName || '我方品牌'}被提及的问题数`} value={groups.length} />
        <ReportMetricCard label="负向提及" value={data?.sentiment_summary?.negative ?? 0} />
      </div>

      <div className="mt-6 space-y-4">
        {groups.length > 0 ? (
          groups.map((group) => {
            return (
              <article key={group.key} className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="text-[20px] font-semibold leading-8 text-[var(--text-primary)]">{group.question}</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      <span className={`rounded-full border px-2.5 py-1 text-[11px] font-semibold ${sentimentTone[group.sentiment] || sentimentTone.neutral}`}>
                        {sentimentLabel[group.sentiment] || '中性提及'}
                      </span>
                      {group.platforms.map((platform) => (
                        <span key={`${group.key}-${platform}`} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                          {getPlatformDisplayName(platform)}
                        </span>
                      ))}
                    </div>
                  </div>
                  <div className="text-right text-[12px] leading-6 text-[var(--text-tertiary)]">
                    <div>{brandName || '我方品牌'}提及 {group.brand_count} 次</div>
                    <div>同场竞品 {group.competitor_count} 次</div>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-2">
                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">{brandName || '我方品牌'} / 产品</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {group.brand_labels.map((label) => (
                        <span key={`${group.key}-${label}`} className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[12px] font-medium text-emerald-700">
                          {label}
                        </span>
                      ))}
                    </div>
                    <div className="mt-3 space-y-2">
                      {group.brand_facts.length ? (
                        group.brand_facts.map((fact) => (
                          <div key={`${group.key}-${fact}`} className="rounded-[14px] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                            {fact}
                          </div>
                        ))
                      ) : null}
                    </div>
                  </div>

                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">同场竞品 / 产品</div>
                    {group.competitor_labels.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {group.competitor_labels.map((label) => (
                          <span key={`${group.key}-${label}`} className="rounded-full bg-rose-500/10 px-2.5 py-1 text-[12px] font-medium text-rose-700">
                            {label}
                          </span>
                        ))}
                      </div>
                    ) : null}
                    <div className="mt-3 space-y-2">
                      {group.competitor_facts.length ? (
                        group.competitor_facts.map((fact) => (
                          <div key={`${group.key}-${fact}`} className="rounded-[14px] bg-[var(--bg-elevated)] px-3 py-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                            {fact}
                          </div>
                        ))
                      ) : null}
                    </div>
                  </div>
                </div>

                {group.source_labels.length > 0 ? (
                  <div className="mt-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">引用来源</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {group.source_labels.slice(0, 8).map((label) => (
                        <span key={`${group.key}-${label}`} className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]">
                          {label}
                        </span>
                      ))}
                    </div>
                  </div>
                ) : null}
              </article>
            );
          })
        ) : (
          <div className="rounded-[18px] border border-dashed border-[var(--border-subtle)] px-4 py-8 text-[14px] text-[var(--text-tertiary)]">
            当前还没有品牌提及明细。
          </div>
        )}
      </div>
    </ReportSection>
  );
}
