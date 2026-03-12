import { getPlatformDisplayName } from '@/lib/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import type { ReportMentionItem, ReportMentionSectionData } from '@/types/canvas';

interface ReportMentionSectionProps {
  data?: ReportMentionSectionData | null;
}

const PLATFORM_ORDER = ['doubao', 'kimi', 'hunyuan', 'deepseek'] as const;

const sentimentLabel: Record<string, string> = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
};

const sentimentTone: Record<string, string> = {
  positive: 'bg-emerald-500/12 text-emerald-500 border-emerald-500/20',
  neutral: 'bg-[var(--bg-secondary)] text-[var(--text-secondary)] border-[var(--border-subtle)]',
  negative: 'bg-red-500/10 text-red-500 border-red-500/20',
  missing: 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)] border-[var(--border-subtle)]',
};

type MentionGroup = {
  key: string;
  question: string;
  platforms: Map<string, ReportMentionItem>;
  evidence?: string;
  sources: string[];
};

function formatRate(value: number | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function groupMentions(items: ReportMentionItem[]): MentionGroup[] {
  const groups = new Map<string, MentionGroup>();
  items.forEach((item) => {
    const key = item.scenario_id || item.scenario_label;
    if (!key) return;
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        question: item.scenario_label,
        platforms: new Map(),
        evidence: item.evidence,
        sources: [],
      });
    }
    const row = groups.get(key)!;
    if (item.platform) row.platforms.set(item.platform, item);
    row.evidence = row.evidence || item.evidence;
    row.sources = [...new Set([...row.sources, ...(item.citation_domains ?? [])])];
  });
  return [...groups.values()];
}

export function ReportMentionSection({ data }: ReportMentionSectionProps) {
  const brandMentions = data?.brand_mentions ?? [];
  const grouped = groupMentions(brandMentions);

  return (
    <section
      className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="space-y-1.5 border-b border-[var(--border-subtle)] pb-4">
        <h2 className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">
          {data?.title || '提及率分析'}
        </h2>
        <p className="max-w-3xl text-[14px] leading-7 text-[var(--text-secondary)]">
          {data?.description || '先看品牌在哪些问题进入了答案，再看四个平台的提及状态和语气差异。'}
        </p>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">提及率</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {formatRate(data?.mention_rate)}
          </div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">被提及问题</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {data?.mention_count ?? grouped.length}
          </div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">正向提及</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {data?.sentiment_summary?.positive ?? 0}
          </div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">负向提及</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {data?.sentiment_summary?.negative ?? 0}
          </div>
        </div>
      </div>

      <div className="mt-5 space-y-4">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">品牌被提及的问题</h3>
          <span className="text-[12px] text-[var(--text-tertiary)]">{grouped.length} 个问题</span>
        </div>
        {grouped.length > 0 ? (
          grouped.map((item) => (
            <article
              key={item.key}
              className="rounded-[18px] border bg-[var(--bg-elevated)] p-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="text-[17px] font-semibold leading-7 text-[var(--text-primary)]">{item.question}</div>
              <div className="mt-4 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
                {PLATFORM_ORDER.map((platform) => {
                  const mention = item.platforms.get(platform);
                  const tone = mention ? mention.sentiment || 'neutral' : 'missing';
                  const label = mention ? sentimentLabel[mention.sentiment || 'neutral'] || '中性' : '未提及';
                  return (
                    <div
                      key={`${item.key}-${platform}`}
                      className={`rounded-[14px] border px-3 py-3 ${sentimentTone[tone] || sentimentTone.missing}`}
                    >
                      <div className="text-[11px] tracking-[0.08em]">{getPlatformDisplayName(platform)}</div>
                      <div className="mt-1 text-[14px] font-semibold">{label}</div>
                    </div>
                  );
                })}
              </div>
              {item.evidence ? (
                <div className="mt-4 space-y-1">
                  <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的答案</div>
                  <p className="text-[14px] leading-7 text-[var(--text-secondary)]">{item.evidence}</p>
                </div>
              ) : null}
              {item.sources.length > 0 ? (
                <div className="mt-4 space-y-1">
                  <div className="text-[12px] font-medium text-[var(--text-secondary)]">引用来源</div>
                  <div className="flex flex-wrap gap-2">
                    {item.sources.slice(0, 6).map((domain) => (
                      <span
                        key={`${item.key}-${domain}`}
                        className="rounded-full border border-[var(--border-subtle)] px-2.5 py-1 text-[11px] text-[var(--text-secondary)]"
                      >
                        {getSourceLabel(domain, false)}
                      </span>
                    ))}
                  </div>
                </div>
              ) : null}
            </article>
          ))
        ) : (
          <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-5 py-8 text-[14px] text-[var(--text-tertiary)]">
            当前还没有品牌提及明细。
          </div>
        )}
      </div>
    </section>
  );
}
