import { cn } from '@/lib/cn';
import type { SourceSectionData } from '@/types/canvas';
import { PLATFORM_COLORS, PLATFORM_NAMES } from '@/config/platforms';

interface SourceSectionProps {
  data?: SourceSectionData | null;
}

function formatPercent(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '--';
  }

  return `${value.toFixed(1)}%`;
}

export function SourceSection({ data }: SourceSectionProps) {
  const analysis = data?.citation_analysis;
  const officialCitationRate = data?.official_citation_rate ?? analysis?.official_share;
  const hasContent = Boolean(
    analysis &&
      ((analysis.total_citations ?? 0) > 0 ||
        (analysis.top_domains?.length ?? 0) > 0 ||
        Object.keys(analysis.platform_citation_stats ?? {}).length > 0)
  );

  const officialTopTitles = (data?.official_top_titles ?? [])
    .filter((title, index, arr) => Boolean(title) && arr.indexOf(title) === index)
    .slice(0, 6);

  return (
    <section className="space-y-5">
      <div className="space-y-1.5">
        <h2 className="text-xl font-semibold tracking-[-0.01em] text-[var(--text-primary)]">
          {data?.title || '信息源分析'}
        </h2>
        <p className="max-w-3xl text-sm leading-6 text-[var(--text-secondary)]">
          {data?.description || 'AI 平台正在引用哪些来源来形成回答。'}
        </p>
      </div>

      {data?.summary && (
        <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4 text-sm leading-7 text-[var(--text-secondary)]">
          {data.summary}
        </div>
      )}

      {!hasContent ? (
        <div className="rounded-[24px] border border-dashed border-[var(--border-subtle)] px-5 py-10 text-sm text-[var(--text-tertiary)]">
          暂无引用来源数据。完成引用抓取后将展示 AI 平台引用了哪些来源。
        </div>
      ) : (
        <>
          <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-5 md:px-6">
            <div className="grid gap-5 md:grid-cols-[200px_1fr] md:items-center">
              <div>
                <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--text-tertiary)]">官网引用率</div>
                <div className="mt-2 text-[32px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                  {formatPercent(officialCitationRate)}
                </div>
                <div className="mt-2 text-sm leading-6 text-[var(--text-secondary)]">
                  官网域名：{analysis?.brand_domain || '未配置'}
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <div className="rounded-2xl bg-[var(--bg-secondary)] px-3 py-4 text-center">
                  <div className="text-xs text-[var(--text-tertiary)]">总引用数</div>
                  <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{analysis?.total_citations ?? '--'}</div>
                </div>
                <div className="rounded-2xl bg-[var(--bg-secondary)] px-3 py-4 text-center">
                  <div className="text-xs text-[var(--text-tertiary)]">独立来源域名</div>
                  <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{analysis?.unique_domains ?? '--'}</div>
                </div>
                <div className="rounded-2xl bg-[var(--bg-secondary)] px-3 py-4 text-center">
                  <div className="text-xs text-[var(--text-tertiary)]">官网引用次数</div>
                  <div className="mt-1 text-lg font-semibold text-[var(--text-primary)]">{analysis?.official_citations ?? '--'}</div>
                </div>
              </div>
            </div>
          </div>

          {officialTopTitles.length > 0 && (
            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4">
              <div className="mb-3 text-sm font-medium text-[var(--text-primary)]">被引用的官网信息</div>
              <div className="flex flex-wrap gap-2">
                {officialTopTitles.map((title) => (
                  <span
                    key={title}
                    className="rounded-full bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-400"
                  >
                    {title}
                  </span>
                ))}
              </div>
            </div>
          )}

          {analysis?.top_domains && analysis.top_domains.length > 0 && (
            <div className="space-y-4">
              {analysis.top_domains.map((domain, index) => (
                <div
                  key={`${domain.domain}-${index}`}
                  className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4"
                >
                  <div className="flex items-center gap-3">
                    <span className="flex h-7 w-7 items-center justify-center rounded-full bg-[var(--bg-secondary)] text-xs font-semibold text-[var(--text-secondary)]">
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="truncate text-sm font-medium text-[var(--text-primary)]">{domain.domain}</span>
                        {domain.is_official && (
                          <span className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[11px] font-medium text-emerald-400">
                            官方
                          </span>
                        )}
                      </div>
                      <div className="mt-2 flex items-center gap-3 text-xs text-[var(--text-secondary)]">
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--bg-secondary)]">
                          <div
                            className={cn('h-full rounded-full', domain.is_official ? 'bg-emerald-400' : 'bg-[var(--accent-primary,#6366F1)]')}
                            style={{ width: `${Math.min(domain.share, 100)}%` }}
                          />
                        </div>
                        <span>{domain.count} 次</span>
                        <span>{domain.share.toFixed(1)}%</span>
                      </div>
                      {(() => {
                        const sampleTitles = [...new Set((domain.sample_titles ?? []).filter(Boolean))].slice(0, 3);
                        if (sampleTitles.length === 0) {
                          return null;
                        }

                        return (
                          <div className="mt-4 flex flex-wrap gap-2">
                            {sampleTitles.map((title, index) => (
                              <span
                                key={`${domain.domain}-${index}-${title}`}
                                className="rounded-full bg-[var(--bg-secondary)] px-2 py-1 text-[11px] text-[var(--text-secondary)]"
                              >
                                {title}
                              </span>
                            ))}
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {analysis?.platform_citation_stats && Object.keys(analysis.platform_citation_stats).length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {Object.entries(analysis.platform_citation_stats).map(([platform, stats]) => (
                <div
                  key={platform}
                  className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4"
                >
                  <div className="flex items-center gap-2">
                    <span
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: PLATFORM_COLORS[platform] || '#6366F1' }}
                    />
                    <span className="text-sm font-medium text-[var(--text-primary)]">
                      {PLATFORM_NAMES[platform] || platform}
                    </span>
                  </div>
                  <div className="mt-3 space-y-2.5 text-sm text-[var(--text-secondary)]">
                    <div className="flex items-center justify-between gap-3">
                      <span>总引用数</span>
                      <span className="font-medium text-[var(--text-primary)]">{stats.total_citations}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>官网引用率</span>
                      <span className="font-medium text-[var(--text-primary)]">{formatPercent(stats.official_share)}</span>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <span>独立域名</span>
                      <span className="font-medium text-[var(--text-primary)]">{stats.unique_domains}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {analysis?.note && (
            <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-4 text-sm leading-7 text-[var(--text-secondary)]">
              {analysis.note}
            </div>
          )}
        </>
      )}
    </section>
  );
}
