import { getPlatformDisplayName } from '@/lib/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import { buildBrandProductLabels, extractProductMentions, extractScenarioSemanticTags } from '@/lib/a5Semantic';
import type { ReportMentionItem, ReportMentionSectionData } from '@/types/canvas';

interface ReportMentionSectionProps {
  data?: ReportMentionSectionData | null;
  brandName?: string;
}

type MentionGroup = {
  key: string;
  question: string;
  platforms: string[];
  brandItems: ReportMentionItem[];
  competitorItems: ReportMentionItem[];
  sourceLabels: string[];
};

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

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  return [...new Set(values.map((value) => String(value || '').trim()).filter(Boolean))];
}

function formatRate(value: number | undefined): string {
  if (value === undefined || value === null || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function normalizeMentionItems(items: ReportMentionItem[] | undefined) {
  return (items ?? []).filter((item) => item.scenario_label.trim());
}

function isPlaceholderTag(label: string) {
  return ['泛人群', '价格未明确', '决策点未明确', '使用场景未明确'].includes(label.trim());
}

function groupMentions(brandMentions: ReportMentionItem[], competitorMentions: ReportMentionItem[]): MentionGroup[] {
  const map = new Map<string, MentionGroup>();
  const ensureGroup = (item: ReportMentionItem) => {
    const key = item.scenario_id || item.scenario_label;
    const existing = map.get(key);
    if (existing) return existing;
    const created: MentionGroup = {
      key,
      question: item.scenario_label,
      platforms: [],
      brandItems: [],
      competitorItems: [],
      sourceLabels: [],
    };
    map.set(key, created);
    return created;
  };

  brandMentions.forEach((item) => {
    const group = ensureGroup(item);
    group.brandItems.push(item);
    group.platforms = uniqueStrings([...group.platforms, item.platform]);
    group.sourceLabels = uniqueStrings([
      ...group.sourceLabels,
      ...(item.citation_domains ?? []).map((domain) => getSourceLabel(domain, false) || domain),
    ]);
  });

  competitorMentions.forEach((item) => {
    const group = ensureGroup(item);
    group.competitorItems.push(item);
    group.platforms = uniqueStrings([...group.platforms, item.platform]);
    group.sourceLabels = uniqueStrings([
      ...group.sourceLabels,
      ...(item.citation_domains ?? []).map((domain) => getSourceLabel(domain, false) || domain),
    ]);
  });

  return [...map.values()];
}

function dominantSentiment(items: ReportMentionItem[]): string {
  const positive = items.filter((item) => item.sentiment === 'positive').length;
  const negative = items.filter((item) => item.sentiment === 'negative').length;
  if (positive > negative) return 'positive';
  if (negative > positive) return 'negative';
  return 'neutral';
}

function buildBrandLabels(group: MentionGroup, brandName?: string): string[] {
  const texts = [
    group.question,
    ...group.brandItems.map((item) => item.evidence || ''),
    ...group.brandItems.flatMap((item) => item.citation_titles ?? []),
  ];
  const products = extractProductMentions(texts, uniqueStrings([brandName]));
  const labels = buildBrandProductLabels(brandName, products).filter(Boolean);
  if (labels.length > 0) {
    return labels;
  }
  return [brandName ? `${brandName}/未涉及具体型号` : '品牌已被提及'];
}

function buildCompetitorLabels(group: MentionGroup): string[] {
  const competitorNames = uniqueStrings(group.competitorItems.map((item) => item.competitor));
  if (competitorNames.length === 0) {
    return ['未识别明显竞品'];
  }

  const texts = [
    group.question,
    ...group.competitorItems.map((item) => item.evidence || ''),
    ...group.competitorItems.flatMap((item) => item.citation_titles ?? []),
  ];
  const products = extractProductMentions(texts, competitorNames);
  const explicitProducts = products.filter((product) => competitorNames.some((name) => product.includes(name)));
  if (explicitProducts.length > 0) {
    return explicitProducts;
  }
  if (products.length === 0 || competitorNames.length > 1) {
    return competitorNames.map((name) => `${name}/未涉及具体型号`);
  }

  return uniqueStrings(competitorNames.map((name) => `${name}/${products[0].replace(/\s+/g, ' ').trim()}`)).slice(0, 4);
}

export function ReportMentionSection({ data, brandName }: ReportMentionSectionProps) {
  const brandMentions = normalizeMentionItems(data?.brand_mentions);
  const competitorMentions = normalizeMentionItems(data?.competitor_mentions);
  const groups = groupMentions(brandMentions, competitorMentions)
    .map((group) => {
      const sentiment = dominantSentiment(group.brandItems);
      const semantic = extractScenarioSemanticTags([group.question, ...group.brandItems.map((item) => item.evidence || '')]);
      const brandLabels = buildBrandLabels(group, brandName);
      const competitorLabels = buildCompetitorLabels(group);
      const sceneLabels = uniqueStrings([
        ...semantic.prices,
        ...semantic.features,
        ...semantic.usages,
      ])
        .filter((label) => !isPlaceholderTag(label))
        .slice(0, 6);

      return {
        ...group,
        sentiment,
        brandLabels,
        competitorLabels,
        sceneLabels,
      };
    });

  return (
    <section className="rounded-[24px] border bg-[var(--bg-tertiary)] p-6 md:p-7" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-2">
        <div className="text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">{data?.title || '提及率分析'}</div>
        <h2 className="text-[26px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
          这里重点看品牌和车型有没有被提到、提到时围绕什么决策点，以及同场出现了哪些竞品。
        </h2>
        <p className="max-w-4xl text-[15px] leading-8 text-[var(--text-secondary)]">
          不再展示截不准的答案原文，只保留真正有信息价值的内容：我方品牌/车型、同场竞品/车型、问题里的决策点和引用来源。
        </p>
      </div>

      <div className="mt-6 grid gap-3 md:grid-cols-4">
        <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">提及率</div>
          <div className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{formatRate(data?.mention_rate)}</div>
        </div>
        <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">品牌进入的问题数</div>
          <div className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{groups.length}</div>
        </div>
        <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">正向提及</div>
          <div className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{data?.sentiment_summary?.positive ?? 0}</div>
        </div>
        <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-4 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">负向提及</div>
          <div className="mt-2 text-[34px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">{data?.sentiment_summary?.negative ?? 0}</div>
        </div>
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
                    <div>我方提及 {group.brandItems.length} 次</div>
                    <div>同场竞品 {group.competitorItems.length} 次</div>
                  </div>
                </div>

                <div className="mt-4 grid gap-3 lg:grid-cols-[1.1fr_1.1fr_1fr]">
                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">提及我方品牌 / 产品</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {group.brandLabels.map((label) => (
                        <span key={`${group.key}-${label}`} className="rounded-full bg-emerald-500/10 px-2.5 py-1 text-[12px] font-medium text-emerald-700">
                          {label}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">提及的场景 / 决策点</div>
                    {group.sceneLabels.length ? (
                      <div className="mt-3 flex flex-wrap gap-2">
                        {group.sceneLabels.map((label) => (
                          <span key={`${group.key}-${label}`} className="rounded-full bg-slate-100 px-2.5 py-1 text-[12px] text-slate-700">
                            {label}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <div className="mt-3 text-[12px] text-[var(--text-tertiary)]">当前问题里没有足够明确的场景标签。</div>
                    )}
                  </div>

                  <div className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] p-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">同场竞品 / 产品</div>
                    <div className="mt-3 flex flex-wrap gap-2">
                      {group.competitorLabels.map((label) => (
                        <span key={`${group.key}-${label}`} className="rounded-full bg-rose-500/10 px-2.5 py-1 text-[12px] font-medium text-rose-700">
                          {label}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>

                {group.sourceLabels.length > 0 ? (
                  <div className="mt-4">
                    <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">引用来源</div>
                    <div className="mt-2 flex flex-wrap gap-2">
                      {group.sourceLabels.slice(0, 8).map((label) => (
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
    </section>
  );
}
