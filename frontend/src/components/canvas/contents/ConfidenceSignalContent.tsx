'use client';

import { useMemo } from 'react';
import {
  RiArrowRightUpLine,
  RiCheckDoubleLine,
  RiFlashlightLine,
  RiShieldCheckLine,
  RiSparklingLine,
} from '@remixicon/react';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/cn';
import type {
  ConfidenceSignalDimensionScore,
  ConfidenceSignalItem,
  ConfidenceSignalStatus,
  ReportCanvasContent,
} from '@/types/canvas';

interface ConfidenceSignalContentProps {
  content: ReportCanvasContent;
}

type RankedSignalRow = {
  key: string;
  rank: number;
  tag: '涉及品牌' | '涉及竞品';
  title: string;
  url?: string;
  score: string;
  bestDimensionLabel: string;
  bestDimensionReason: string;
  suggestion: string;
};

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(1);
}

function formatUpdatedAt(value?: string) {
  if (!value) return '刚刚更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function statusTone(status?: ConfidenceSignalStatus) {
  switch (status?.phase) {
    case 'running':
      return 'border-amber-500/30 bg-amber-500/10 text-amber-100';
    case 'error':
      return 'border-rose-500/30 bg-rose-500/10 text-rose-100';
    default:
      return 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]';
  }
}

function normalizeKeyword(value: string): string {
  return value.trim().toLowerCase();
}

function buildKeywordSet(values: Array<string | undefined>): string[] {
  const seen = new Set<string>();
  const keywords: string[] = [];

  values
    .filter((value): value is string => Boolean(value?.trim()))
    .forEach((value) => {
      const normalized = normalizeKeyword(value);
      if (!normalized || seen.has(normalized)) return;
      seen.add(normalized);
      keywords.push(value.trim());
    });

  return keywords;
}

function itemSearchText(item: ConfidenceSignalItem): string {
  return [
    item.label,
    item.url,
    item.domain,
    item.site_name,
    item.raw_text,
    ...(item.question_samples ?? []),
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
}

function countKeywordHits(text: string, keywords: string[]): number {
  return keywords.reduce((count, keyword) => {
    const normalized = normalizeKeyword(keyword);
    return normalized && text.includes(normalized) ? count + 1 : count;
  }, 0);
}

function classifySignalItem(
  item: ConfidenceSignalItem,
  brandKeywords: string[],
  competitorKeywords: string[],
): 'brand' | 'competitor' | null {
  if (item.is_official) return 'brand';

  const text = itemSearchText(item);
  const brandHits = countKeywordHits(text, brandKeywords);
  const competitorHits = countKeywordHits(text, competitorKeywords);

  if (brandHits === 0 && competitorHits === 0) return null;
  if (competitorHits > brandHits) return 'competitor';
  return 'brand';
}

function getBestDimension(
  dimensions?: ConfidenceSignalDimensionScore[],
): { label: string; reason: string } {
  if (!dimensions || dimensions.length === 0) {
    return {
      label: '暂无维度说明',
      reason: '当前还没有返回可展示的维度分析。',
    };
  }

  const best = [...dimensions].sort((a, b) => {
    const ratioA =
      typeof a.score === 'number' && typeof a.max_score === 'number' && a.max_score > 0
        ? a.score / a.max_score
        : -1;
    const ratioB =
      typeof b.score === 'number' && typeof b.max_score === 'number' && b.max_score > 0
        ? b.score / b.max_score
        : -1;
    return ratioB - ratioA;
  })[0];

  return {
    label: best.label || best.key || '优势维度',
    reason: best.reasoning || '当前该维度表现较稳。',
  };
}

function getPrimarySuggestion(item: ConfidenceSignalItem): string {
  const recommendation = item.recommendations?.[0];
  if (!recommendation) {
    return '优先补充来源主体、发布时间、结构化信息和可核查证据。';
  }
  const title = recommendation.title?.trim();
  const action = recommendation.action?.trim();
  const reason = recommendation.reason?.trim();
  return [title, action, reason].filter(Boolean).join('：');
}

function buildRankedRows(
  items: ConfidenceSignalItem[],
  tag: 'brand' | 'competitor',
  brandKeywords: string[],
  competitorKeywords: string[],
): RankedSignalRow[] {
  const filtered = items
    .filter((item) => classifySignalItem(item, brandKeywords, competitorKeywords) === tag)
    .sort((a, b) => {
      const scoreGap = (b.overall_score ?? 0) - (a.overall_score ?? 0);
      if (scoreGap !== 0) return scoreGap;
      return (b.overall_confidence ?? 0) - (a.overall_confidence ?? 0);
    })
    .slice(0, 15);

  return filtered.map((item, index) => {
    const bestDimension = getBestDimension(item.dimension_scores);
    return {
      key: item.item_id,
      rank: index + 1,
      tag: tag === 'brand' ? '涉及品牌' : '涉及竞品',
      title: item.label,
      url: item.url,
      score: formatScore(item.overall_score),
      bestDimensionLabel: bestDimension.label,
      bestDimensionReason: bestDimension.reason,
      suggestion: getPrimarySuggestion(item),
    };
  });
}

function RankingTable({
  title,
  subtitle,
  rows,
}: {
  title: string;
  subtitle: string;
  rows: RankedSignalRow[];
}) {
  return (
    <Card
      padding="none"
      className="rounded-[24px] border bg-[var(--bg-tertiary)] p-5"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-3">
        <div>
          <div className="text-[18px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
            {title}
          </div>
          <div className="mt-1 text-[13px] text-[var(--text-secondary)]">{subtitle}</div>
        </div>
        <div className="text-[12px] text-[var(--text-tertiary)]">{rows.length} 条</div>
      </div>

      {rows.length > 0 ? (
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full border-separate border-spacing-0">
            <thead>
              <tr className="text-left text-[12px] text-[var(--text-tertiary)]">
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">排名</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">标题</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">链接</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">标签</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">置信度评分</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">表现优异的维度与原因</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">提升建议</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.key} className="align-top">
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] font-medium text-[var(--text-primary)]">
                    #{row.rank}
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
                    {row.title}
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                    {row.url ? (
                      <a
                        href={row.url}
                        target="_blank"
                        rel="noreferrer"
                        className="inline-flex items-center gap-1 break-all text-[var(--color-primary)] hover:underline"
                      >
                        <span>{row.url}</span>
                        <RiArrowRightUpLine className="h-3.5 w-3.5 shrink-0" />
                      </a>
                    ) : (
                      <span>当前未保留原始链接</span>
                    )}
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3">
                    <span className="rounded-full bg-[var(--bg-secondary)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-secondary)]">
                      {row.tag}
                    </span>
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] font-medium text-[var(--text-primary)]">
                    {row.score}
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                    <div className="font-medium text-[var(--text-primary)]">{row.bestDimensionLabel}</div>
                    <div className="mt-1">{row.bestDimensionReason}</div>
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                    {row.suggestion}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-4 rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
          当前还没有可展示的排名结果。
        </div>
      )}
    </Card>
  );
}

export function ConfidenceSignalContent({ content }: ConfidenceSignalContentProps) {
  const summary = content.data.summary;
  const findings = content.data.aggregate_findings ?? [];
  const status = content.data.status;
  const allItems = useMemo(
    () => [...(content.data.auto_items ?? []), ...(content.data.manual_items ?? [])],
    [content.data.auto_items, content.data.manual_items],
  );
  const brandKeywords = useMemo(
    () =>
      buildKeywordSet([
        content.data.brand_name,
        ...(content.data.brand_keywords ?? []),
      ]),
    [content.data.brand_keywords, content.data.brand_name],
  );
  const competitorKeywords = useMemo(
    () => buildKeywordSet(content.data.competitor_names ?? []),
    [content.data.competitor_names],
  );
  const brandRows = useMemo(
    () => buildRankedRows(allItems, 'brand', brandKeywords, competitorKeywords),
    [allItems, brandKeywords, competitorKeywords],
  );
  const competitorRows = useMemo(
    () => buildRankedRows(allItems, 'competitor', brandKeywords, competitorKeywords),
    [allItems, brandKeywords, competitorKeywords],
  );

  return (
    <div className="mx-auto max-w-[1280px] space-y-6 px-6 py-6 md:px-8 md:py-8">
      <section
        className="overflow-hidden rounded-[30px] border"
        style={{
          borderColor: 'rgba(148, 163, 184, 0.18)',
          background:
            'radial-gradient(circle at top left, rgba(16,185,129,0.16), transparent 30%), radial-gradient(circle at top right, rgba(245,158,11,0.14), transparent 28%), linear-gradient(180deg, rgba(15,23,42,0.95), rgba(17,24,39,0.92))',
        }}
      >
        <div className="grid gap-6 px-6 py-6 md:px-7 md:py-7 lg:grid-cols-[1.2fr_0.8fr]">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-[11px] tracking-[0.16em] text-white/70">
                <RiSparklingLine className="h-3.5 w-3.5" />
                CONFIDENCE SIGNAL
              </span>
              <span
                className={cn(
                  'inline-flex items-center rounded-full border px-3 py-1 text-[12px]',
                  statusTone(status),
                )}
              >
                {status?.message || '引用内容置信度评估已就绪'}
              </span>
            </div>

            <h1 className="mt-5 text-[clamp(2.2rem,4vw,3.6rem)] font-semibold tracking-[-0.05em] text-white">
              {content.data.headline || '置信度信号'}
            </h1>
            <p className="mt-4 max-w-3xl text-[15px] leading-8 text-white/70">
              这里只保留最值得看的两类链接排名：涉及品牌的高置信度内容，以及涉及竞品的高置信度内容。
              每类最多展示 15 条，避免全量链接拖慢浏览器。
            </p>

            <div className="mt-5 flex flex-wrap items-center gap-x-5 gap-y-2 text-[12px] text-white/50">
              <span>仅展示高价值排名，不再全量铺开链接</span>
              <span>额外评估入口已移动到画布头部按钮</span>
              <span>最近更新 {formatUpdatedAt(summary?.updated_at || content.data.updated_at)}</span>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-2">
            <Card
              padding="none"
              className="rounded-[24px] border border-white/10 bg-white/[0.06] p-5"
            >
              <div className="text-[12px] tracking-[0.16em] text-white/60">已评估来源</div>
              <div className="mt-3 text-[40px] font-semibold tracking-[-0.06em] text-white">
                {summary?.evaluated_count ?? 0}
              </div>
              <div className="mt-2 text-[13px] leading-6 text-white/70">
                当前自动引用与额外评估合计可用的来源数。
              </div>
            </Card>
            <Card
              padding="none"
              className="rounded-[24px] border border-white/10 bg-white/[0.06] p-5"
            >
              <div className="text-[12px] tracking-[0.16em] text-white/60">平均置信度评分</div>
              <div className="mt-3 text-[40px] font-semibold tracking-[-0.06em] text-white">
                {formatScore(summary?.average_score)}
              </div>
              <div className="mt-2 text-[13px] leading-6 text-white/70">
                用于判断当前引用内容整体是否稳定可采信。
              </div>
            </Card>
          </div>
        </div>

        <div
          className="grid gap-3 border-t px-6 py-5 md:grid-cols-4 md:px-7"
          style={{ borderColor: 'rgba(255,255,255,0.08)' }}
        >
          <Card padding="none" className="rounded-[20px] border border-white/10 bg-white/[0.06] p-4">
            <div className="text-[12px] tracking-[0.14em] text-white/60">品牌相关排名</div>
            <div className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-white">{brandRows.length}</div>
          </Card>
          <Card padding="none" className="rounded-[20px] border border-white/10 bg-white/[0.06] p-4">
            <div className="text-[12px] tracking-[0.14em] text-white/60">竞品相关排名</div>
            <div className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-white">{competitorRows.length}</div>
          </Card>
          <Card padding="none" className="rounded-[20px] border border-white/10 bg-white/[0.06] p-4">
            <div className="text-[12px] tracking-[0.14em] text-white/60">高置信来源</div>
            <div className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-white">{summary?.high_confidence_count ?? 0}</div>
          </Card>
          <Card padding="none" className="rounded-[20px] border border-white/10 bg-white/[0.06] p-4">
            <div className="text-[12px] tracking-[0.14em] text-white/60">需审慎来源</div>
            <div className="mt-3 text-[28px] font-semibold tracking-[-0.04em] text-white">{summary?.caution_count ?? 0}</div>
          </Card>
        </div>
      </section>

      {findings.length > 0 ? (
        <section className="grid gap-4 xl:grid-cols-3">
          {findings.slice(0, 3).map((finding, index) => (
            <Card
              key={`${finding.title}_${index}`}
              padding="none"
              className="rounded-[22px] border bg-[var(--bg-tertiary)] p-5"
              style={{ borderColor: 'var(--border-subtle)' }}
            >
              <div className="flex items-center gap-2 text-[12px] tracking-[0.14em] text-[var(--text-tertiary)]">
                {index === 0 ? <RiCheckDoubleLine className="h-4 w-4" /> : index === 1 ? <RiShieldCheckLine className="h-4 w-4" /> : <RiFlashlightLine className="h-4 w-4" />}
                摘要
              </div>
              <div className="mt-3 text-[16px] font-semibold text-[var(--text-primary)]">
                {finding.title || `发现 ${index + 1}`}
              </div>
              <div className="mt-2 text-[13px] leading-7 text-[var(--text-secondary)]">
                {finding.description}
              </div>
            </Card>
          ))}
        </section>
      ) : null}

      <div className="space-y-6">
        <RankingTable
          title="涉及品牌相关内容链接的置信度排名"
          subtitle="优先看哪些品牌相关内容已经具备较强采信基础。"
          rows={brandRows}
        />
        <RankingTable
          title="涉及竞品相关内容链接的置信度排名"
          subtitle="优先看哪些竞品相关内容正在形成更强的话语权。"
          rows={competitorRows}
        />
      </div>
    </div>
  );
}
