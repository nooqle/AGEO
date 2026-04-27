'use client';

import type { ReactNode } from 'react';
import type {
  DashboardCitationDomain,
  DashboardCitationSourceType,
  DashboardEmotionWord,
  DashboardHomeAdvantageCard,
  DashboardHomeData,
  DashboardHomeMetric,
  DashboardHomeRiskCard,
  DashboardMentionRankingRow,
  DashboardPlatformDiagnosisRow,
  DashboardSourceStructure,
} from '@/types/dashboard';
import { DashboardSectionHeader } from './DashboardSectionHeader';

interface DashboardHomeBoardsProps {
  home: DashboardHomeData;
  onOpenLatestReport?: () => void;
  isOpeningLatestReport?: boolean;
}

function formatMetricValue(metric: DashboardHomeMetric): string {
  if (metric.value == null) return '--';
  if (metric.format === 'percent') {
    const normalized = metric.value <= 1 ? metric.value * 100 : metric.value;
    return `${normalized.toFixed(1)}%`;
  }
  if (metric.format === 'rank') {
    return `#${Math.round(metric.value)}`;
  }
  return Number.isInteger(metric.value) ? String(metric.value) : metric.value.toFixed(1);
}

function formatPercent(value: number | null): string {
  if (value == null) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function percentWidth(value: number | null): string {
  if (value == null) return '0%';
  const normalized = value <= 1 ? value * 100 : value;
  return `${Math.max(5, Math.min(100, normalized))}%`;
}

function SectionBlock({
  title,
  compact = false,
  children,
}: {
  title: string;
  compact?: boolean;
  children: ReactNode;
}) {
  return (
    <section className={`rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] ${compact ? 'px-4 py-4' : 'px-5 py-5'}`}>
      <div className="text-[17px] font-semibold text-[var(--text-primary)]">{title}</div>
      <div className={compact ? 'mt-3' : 'mt-4'}>{children}</div>
    </section>
  );
}

function EmptyInline({ label = '暂无数据' }: { label?: string }) {
  return <div className="rounded-xl border border-dashed border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-4 py-3 text-[14px] text-[var(--text-tertiary)]">{label}</div>;
}

function MetricStrip({ metrics }: { metrics: DashboardHomeMetric[] }) {
  if (metrics.length === 0) {
    return <EmptyInline />;
  }

  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {metrics.slice(0, 4).map((metric) => (
        <div
          key={metric.id}
          className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4"
        >
          <div className="text-[13px] text-[var(--text-tertiary)]">{metric.label}</div>
          <div className="mt-2 text-[30px] font-semibold text-[var(--text-primary)]">
            {formatMetricValue(metric)}
          </div>
        </div>
      ))}
    </div>
  );
}

function wordSize(word: DashboardEmotionWord): string {
  const weight = word.weight <= 1 ? word.weight * 100 : word.weight;
  const size = 15 + Math.min(34, Math.max(0, weight) * 0.24);
  return `${size}px`;
}

function WordCloudColumn({
  title,
  words,
  tone,
}: {
  title: string;
  words: DashboardEmotionWord[];
  tone: 'positive' | 'negative';
}) {
  const toneStyle =
    tone === 'positive'
      ? {
          label: 'var(--success)',
          chipBg: 'var(--status-success-bg)',
          word: 'var(--success)',
          empty: '暂无正向词云数据',
        }
      : {
          label: 'var(--evidence-risk)',
          chipBg: 'var(--status-error-bg)',
          word: 'var(--evidence-risk)',
          empty: '暂无负向词云数据',
        };

  return (
    <div className="min-h-[170px] rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-5 py-4">
      <div className="flex items-center gap-2">
        <span
          className="h-2 w-2 rounded-full"
          style={{ backgroundColor: toneStyle.label }}
        />
        <div className="text-[14px] font-semibold text-[var(--text-primary)]">{title}</div>
      </div>
      {words.length === 0 ? (
        <div className="mt-5 text-[14px] text-[var(--text-tertiary)]">{toneStyle.empty}</div>
      ) : (
        <div className="mt-5 flex flex-wrap items-center gap-x-4 gap-y-3">
          {words.slice(0, 18).map((word) => (
            <span
              key={`${tone}-${word.text}`}
              className="leading-none"
              style={{
                fontSize: wordSize(word),
                fontWeight: word.weight > 50 || word.weight > 0.5 ? 700 : 500,
                color: toneStyle.word,
                opacity: word.weight > 50 || word.weight > 0.5 ? 0.92 : 0.68,
              }}
              title={word.count ? `${word.count} 次` : undefined}
            >
              {word.text}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function EmotionWordCloud({ positive, negative }: { positive: DashboardEmotionWord[]; negative: DashboardEmotionWord[] }) {
  return (
    <SectionBlock title="正负词云">
      <div className="grid gap-3 xl:grid-cols-2">
        <WordCloudColumn title="正向" words={positive} tone="positive" />
        <WordCloudColumn title="负向" words={negative} tone="negative" />
      </div>
    </SectionBlock>
  );
}

const PLATFORM_STATUS_LABEL: Record<DashboardPlatformDiagnosisRow['status'], string> = {
  good: '优势',
  watch: '观察',
  risk: '风险',
  unknown: '待观察',
};

function PlatformDiagnosis({ rows }: { rows: DashboardPlatformDiagnosisRow[] }) {
  return (
    <SectionBlock title="平台诊断">
      {rows.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[680px] border-separate border-spacing-0 text-left">
            <thead>
              <tr className="text-[12px] text-[var(--text-tertiary)]">
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">平台</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">状态</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">回答</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">提及</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">正向</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">负向</th>
                <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">主要顾虑</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.platform} className="text-[14px] text-[var(--text-primary)]">
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 font-semibold">{row.platform}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">
                    <span className="rounded-full bg-[var(--bg-tertiary)] px-2.5 py-1 text-[12px] text-[var(--text-secondary)]">
                      {PLATFORM_STATUS_LABEL[row.status]}
                    </span>
                  </td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">{row.answer_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4">{row.brand_mention_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--success)]">{row.positive_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--evidence-risk)]">{row.negative_count}</td>
                  <td className="border-b border-[var(--border-subtle)] px-3 py-4 text-[var(--text-secondary)]">
                    {row.main_concern || '--'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </SectionBlock>
  );
}

function RiskLevelBadge({ level }: { level: DashboardHomeRiskCard['level'] }) {
  const label = level === 'high' ? '高风险' : level === 'low' ? '低风险' : '需防守';
  return <span className="rounded-full px-2.5 py-1 text-[12px] font-medium text-[var(--evidence-risk)]" style={{ backgroundColor: 'var(--status-error-bg)' }}>{label}</span>;
}

function RiskCards({ risks }: { risks: DashboardHomeRiskCard[] }) {
  return (
    <SectionBlock title="高风险问题" compact>
      {risks.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {risks.slice(0, 4).map((risk) => (
            <div key={`${risk.title}-${risk.platform || ''}`} className="rounded-[20px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[16px] font-semibold text-[var(--text-primary)]">{risk.title}</div>
                <RiskLevelBadge level={risk.level} />
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[13px] text-[var(--text-secondary)]">
                {risk.platform ? <span>{risk.platform}</span> : null}
                {risk.evidence ? <span>{risk.evidence}</span> : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function AdvantageCards({ advantages }: { advantages: DashboardHomeAdvantageCard[] }) {
  return (
    <SectionBlock title="优势场景" compact>
      {advantages.length === 0 ? (
        <EmptyInline />
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {advantages.slice(0, 4).map((advantage) => (
            <div key={advantage.title} className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-report-muted)] px-4 py-4">
              <div className="flex items-start justify-between gap-3">
                <div className="text-[16px] font-semibold text-[var(--text-primary)]">{advantage.title}</div>
                <span className="rounded-full px-2.5 py-1 text-[12px] font-medium text-[var(--success)]" style={{ backgroundColor: 'var(--status-success-bg)' }}>优势</span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2 text-[13px] text-[var(--text-secondary)]">
                {advantage.platform_count ? <span>{advantage.platform_count} 个平台</span> : null}
                {advantage.evidence ? <span>{advantage.evidence}</span> : null}
              </div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function MentionRanking({ rows }: { rows: DashboardMentionRankingRow[] }) {
  return (
    <SectionBlock title="提及率排行">
      {rows.length === 0 ? (
        <EmptyInline label="暂无排行" />
      ) : (
        <div className="space-y-2">
          {rows.slice(0, 10).map((row) => (
            <div
              key={`${row.rank}-${row.brand}`}
              className={`grid grid-cols-[42px_minmax(0,1fr)_84px_72px] items-center gap-3 rounded-[16px] px-3 py-3 text-[14px] ${
                row.is_current_brand ? 'bg-[var(--color-primary)]/10 text-[var(--text-primary)]' : 'bg-[var(--bg-tertiary)] text-[var(--text-secondary)]'
              }`}
            >
              <div className="font-semibold text-[var(--text-primary)]">#{row.rank}</div>
              <div className="truncate font-medium text-[var(--text-primary)]">{row.brand}</div>
              <div className="text-right font-semibold text-[var(--text-primary)]">{formatPercent(row.mention_rate)}</div>
              <div className="text-right text-[12px] text-[var(--text-tertiary)]">{row.mention_count} 次</div>
            </div>
          ))}
        </div>
      )}
    </SectionBlock>
  );
}

function SourceTypeList({ items }: { items: DashboardCitationSourceType[] }) {
  if (items.length === 0) {
    return <EmptyInline />;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={item.key} className="space-y-1.5">
          <div className="flex items-center justify-between gap-3 text-[14px]">
            <span className="text-[var(--text-primary)]">{item.label}</span>
            <span className="font-medium text-[var(--text-primary)]">{formatPercent(item.share)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-tertiary)]">
            <div className="h-full rounded-full bg-[var(--color-primary)]" style={{ width: percentWidth(item.share) }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

function TopDomainList({ items }: { items: DashboardCitationDomain[] }) {
  if (items.length === 0) {
    return <EmptyInline />;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={`${item.domain}-${item.display_name}`} className="rounded-[16px] bg-[var(--bg-tertiary)] px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[14px] font-medium text-[var(--text-primary)]">{item.display_name}</div>
              <div className="mt-1 truncate text-[12px] text-[var(--text-tertiary)]">{item.domain}</div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[14px] font-semibold text-[var(--text-primary)]">{item.count} 次</div>
              <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{formatPercent(item.share)}</div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

function resolveSourceStructure(home: DashboardHomeData): DashboardSourceStructure {
  const sourceStructure = home.source_structure;
  const hasSourceStructure = Boolean(
    sourceStructure
      && (sourceStructure.official_conversion_rate != null
        || sourceStructure.source_types.length > 0
        || sourceStructure.top_domains.length > 0),
  );

  if (hasSourceStructure && sourceStructure) {
    return sourceStructure;
  }

  return {
    official_conversion_rate: null,
    source_types: home.citation_distribution?.source_types || [],
    top_domains: home.citation_distribution?.top_domains || [],
  };
}

function SourceStructure({ source }: { source: DashboardSourceStructure }) {
  return (
    <SectionBlock title="信源结构">
      <div className="grid gap-5 xl:grid-cols-[0.75fr_1fr_1fr]">
        <div className="rounded-[18px] bg-[var(--bg-tertiary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">官网转化率</div>
          <div className="mt-3 text-[32px] font-semibold text-[var(--text-primary)]">
            {formatPercent(source.official_conversion_rate)}
          </div>
        </div>
        <div>
          <div className="mb-3 text-[13px] font-medium text-[var(--text-tertiary)]">来源分布</div>
          <SourceTypeList items={source.source_types} />
        </div>
        <div>
          <div className="mb-3 text-[13px] font-medium text-[var(--text-tertiary)]">主要站点</div>
          <TopDomainList items={source.top_domains} />
        </div>
      </div>
    </SectionBlock>
  );
}

export function DashboardHomeBoards({ home, onOpenLatestReport, isOpeningLatestReport = false }: DashboardHomeBoardsProps) {
  const metrics = home.metrics || [];
  const latestReport = home.latest_report;
  const sourceStructure = resolveSourceStructure(home);
  const wordCloud = home.word_cloud || { positive: [], negative: [] };

  return (
    <section className="dashboard-shell rounded-[30px] px-6 py-6">
      <DashboardSectionHeader
        title="最近一轮分析"
        action={latestReport?.created_at ? (
          <div className="text-right">
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">最近更新</div>
            <div className="mt-1 text-[13px] text-[var(--text-secondary)]">
              {new Date(latestReport.created_at).toLocaleString('zh-CN', { hour12: false })}
            </div>
          </div>
        ) : undefined}
      />

      <div className="space-y-4 rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-5">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">
              {latestReport?.report_kind_label || '分析报告'}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="text-[28px] font-semibold text-[var(--text-primary)]">
                {latestReport?.title || '暂无最新报告'}
              </h2>
              {latestReport?.badge_label ? (
                <span className="inline-flex items-center rounded-full bg-[var(--bg-tertiary)] px-2.5 py-1 text-[12px] font-medium text-[var(--color-primary)]">
                  {latestReport.badge_label}
                </span>
              ) : null}
            </div>
          </div>

          {onOpenLatestReport && latestReport?.session_id ? (
            <button
              type="button"
              onClick={onOpenLatestReport}
              disabled={isOpeningLatestReport}
              aria-busy={isOpeningLatestReport}
              className="inline-flex min-h-10 shrink-0 items-center justify-center gap-2 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[13px] font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)] disabled:cursor-wait disabled:opacity-70"
            >
              {isOpeningLatestReport ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" /> : null}
              {isOpeningLatestReport ? '打开中' : latestReport.action_label || '打开报告'}
            </button>
          ) : null}
        </div>

        <MetricStrip metrics={metrics} />
        <EmotionWordCloud positive={wordCloud.positive} negative={wordCloud.negative} />
        <PlatformDiagnosis rows={home.platform_diagnosis || []} />
        <RiskCards risks={home.risks || []} />
        <AdvantageCards advantages={home.advantages || []} />
        <MentionRanking rows={home.mention_ranking || []} />
        <SourceStructure source={sourceStructure} />
      </div>
    </section>
  );
}
