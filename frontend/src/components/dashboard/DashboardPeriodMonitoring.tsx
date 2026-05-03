'use client';

import type {
  DashboardHomeData,
  DashboardMonitorMode,
  DashboardPeriodMetricSummary,
  DashboardPlatformDiagnosisRow,
} from '@/types/dashboard';

interface DashboardPeriodMonitoringProps {
  home?: DashboardHomeData | null;
  selectedMonitorMode: DashboardMonitorMode;
  selectedBrandName?: string;
  onMonitorModeChange?: (mode: DashboardMonitorMode) => void;
  isLoading?: boolean;
}

const DEFAULT_SOURCES = [
  { id: 'doubao_api', label: '豆包API', mark: '豆' },
  { id: 'doubao_browser', label: '豆包网页版', mark: '豆' },
  { id: 'deepseek_browser', label: 'DeepSeek网页版', mark: 'D' },
  { id: 'yuanbao_api', label: '元宝API', mark: '元' },
  { id: 'yuanbao_browser', label: '元宝网页版', mark: '元' },
  { id: 'kimi_api', label: 'Kimi API', mark: 'K' },
  { id: 'kimi_browser', label: 'Kimi 网页版', mark: 'K' },
];

function metricByKey(home: DashboardHomeData | null | undefined, key: string): DashboardPeriodMetricSummary | undefined {
  return home?.period_summary?.metrics.find((metric) => metric.metric === key || metric.id === key);
}

function formatPercent(value: number | null | undefined): string {
  if (value == null) return '0%';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function formatRank(value: number | null | undefined): string {
  if (!value || value <= 0) return '--';
  return `第 ${value} 名`;
}

function formatDateRange(home: DashboardHomeData | null | undefined): string {
  const label = home?.period_summary?.period_label;
  if (label) return label;
  return '近 30 天';
}

function sourceMark(label: string): string {
  if (label.includes('豆包')) return '豆';
  if (label.includes('元宝')) return '元';
  if (label.includes('Kimi')) return 'K';
  if (label.includes('DeepSeek')) return 'D';
  return label.slice(0, 1).toUpperCase();
}

function totalAnswerCount(rows: DashboardPlatformDiagnosisRow[]): number {
  return rows.reduce((sum, row) => sum + row.answer_count, 0);
}

function totalMentionCount(rows: DashboardPlatformDiagnosisRow[]): number {
  return rows.reduce((sum, row) => sum + row.brand_mention_count, 0);
}

function totalPositiveCount(rows: DashboardPlatformDiagnosisRow[]): number {
  return rows.reduce((sum, row) => sum + row.positive_count, 0);
}

function totalNegativeCount(rows: DashboardPlatformDiagnosisRow[]): number {
  return rows.reduce((sum, row) => sum + row.negative_count, 0);
}

function currentBrandRank(home: DashboardHomeData | null | undefined, brandName?: string): number | null {
  const ranking = home?.mention_ranking || [];
  const current =
    ranking.find((row) => row.is_current_brand) ||
    ranking.find((row) => brandName && row.brand === brandName);
  return current?.rank ?? null;
}

function PlatformCard({ row }: { row: DashboardPlatformDiagnosisRow | { platform: string; answer_count?: number; brand_mention_count?: number; positive_count?: number; negative_count?: number } }) {
  const answerCount = row.answer_count ?? 0;
  const mentionCount = row.brand_mention_count ?? 0;
  const hasData = answerCount > 0 || mentionCount > 0;
  return (
    <section className="min-h-[174px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
      <div className="mb-3 flex items-center gap-2.5 font-semibold text-[var(--text-primary)]">
        <span className="grid h-8 w-8 place-items-center rounded-[10px] bg-[var(--brand-bg)] text-[13px] font-bold text-[var(--brand-text)]">
          {sourceMark(row.platform)}
        </span>
        <span className="truncate">{row.platform}</span>
      </div>
      <div className="space-y-1.5 text-[13px]">
        <div className="flex justify-between gap-3 text-[var(--text-tertiary)]">
          <span>对话次数</span>
          <b className="font-medium text-[var(--text-primary)]">{hasData ? `${answerCount} 次` : '未提及'}</b>
        </div>
        <div className="flex justify-between gap-3 text-[var(--text-tertiary)]">
          <span>提及次数</span>
          <b className="font-medium text-[var(--text-primary)]">{hasData ? `${mentionCount} 次` : '未提及'}</b>
        </div>
        <div className="flex justify-between gap-3 text-[var(--text-tertiary)]">
          <span>提及率</span>
          <b className="font-medium text-[var(--text-primary)]">{answerCount ? formatPercent(mentionCount / answerCount) : '未提及'}</b>
        </div>
        <div className="flex justify-between gap-3 text-[var(--text-tertiary)]">
          <span>正向 / 风险</span>
          <b className="font-medium text-[var(--text-primary)]">
            {hasData ? `${row.positive_count ?? 0} / ${row.negative_count ?? 0}` : '--'}
          </b>
        </div>
      </div>
    </section>
  );
}

function ChartPlaceholder({ title, value }: { title: string; value: string }) {
  return (
    <section className="grid min-h-[246px] grid-rows-[auto_minmax(0,1fr)] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-5">
      <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">{title}</h3>
      <div className="grid place-items-center text-center text-[13px] text-[var(--text-tertiary)]">
        <div>
          <div className="mx-auto mb-4 grid h-[72px] w-[96px] place-items-center rounded-[16px] border border-[var(--brand-border)] bg-[var(--brand-bg)] text-[22px] font-semibold text-[var(--brand-text)]">
            {value}
          </div>
          数据较少，暂时无法分析
        </div>
      </div>
    </section>
  );
}

function RankingPanel({
  home,
  selectedBrandName,
}: {
  home?: DashboardHomeData | null;
  selectedBrandName?: string;
}) {
  const ranking = (home?.mention_ranking || []).slice(0, 6);
  if (!ranking.length) {
    return <ChartPlaceholder title="品牌提及排名" value="--" />;
  }
  return (
    <section className="min-h-[246px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-5">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-[16px] font-semibold text-[var(--text-primary)]">品牌提及排名</h3>
        <span className="text-[12px] text-[var(--text-tertiary)]">当前品牌</span>
      </div>
      <div className="mt-4 space-y-2">
        {ranking.map((row) => {
          const isCurrent = row.is_current_brand || row.brand === selectedBrandName;
          return (
            <div
              key={`${row.rank}-${row.brand}`}
              className="grid grid-cols-[44px_minmax(0,1fr)_auto] items-center gap-3 rounded-[12px] border px-3 py-2.5"
              style={{
                borderColor: isCurrent
                  ? 'color-mix(in srgb, var(--brand-primary) 34%, var(--border-subtle) 66%)'
                  : 'var(--border-subtle)',
                background: isCurrent
                  ? 'color-mix(in srgb, var(--brand-bg) 72%, var(--bg-secondary) 28%)'
                  : 'var(--bg-tertiary)',
              }}
            >
              <span className="text-[13px] font-semibold text-[var(--text-primary)]">#{row.rank}</span>
              <span className="truncate text-[13px] font-medium text-[var(--text-primary)]">{row.brand}</span>
              <span className="text-[12px] text-[var(--text-tertiary)]">{row.mention_count} 次</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function DashboardPeriodMonitoring({
  home,
  selectedMonitorMode,
  selectedBrandName,
  onMonitorModeChange,
  isLoading = false,
}: DashboardPeriodMonitoringProps) {
  const periodDataCount = home?.period_summary?.data_point_count ?? 0;
  const mention = metricByKey(home, 'mention_rate');
  const citation = metricByKey(home, 'content_citation_rate') || metricByKey(home, 'official_conversion_rate');
  const platformRows = home?.platform_diagnosis || [];
  const answerTotal = totalAnswerCount(platformRows);
  const mentionTotal = totalMentionCount(platformRows);
  const positiveTotal = totalPositiveCount(platformRows);
  const negativeTotal = totalNegativeCount(platformRows);
  const mentionRateFromRows = answerTotal > 0 ? mentionTotal / answerTotal : null;
  const displayedMentionRate = mentionRateFromRows ?? mention?.current_value;
  const rank = currentBrandRank(home, selectedBrandName);
  const sources = platformRows.length
    ? platformRows
    : DEFAULT_SOURCES.map((source) => ({
        platform: source.label,
        answer_count: 0,
        brand_mention_count: 0,
        positive_count: 0,
        negative_count: 0,
      }));

  if (isLoading && !home) {
    return (
      <section className="dashboard-shell rounded-[24px] px-5 py-5">
        <div className="h-8 w-32 rounded-lg animate-shimmer" />
        <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 rounded-[16px] animate-shimmer" />
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="dashboard-shell rounded-[24px] px-5 py-5">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
        <div>
          <h2 className="text-[24px] font-semibold text-[var(--text-primary)]">周期监测</h2>
          <p className="mt-1 text-[13px] text-[var(--text-tertiary)]">
            {periodDataCount > 0 ? `${formatDateRange(home)} · ${periodDataCount} 个样本` : '暂无样本，首次快速分析完成后会形成周期趋势。'}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <div
            className="inline-flex rounded-[12px] border bg-[var(--bg-secondary)] p-1"
            style={{ borderColor: 'var(--border-subtle)' }}
            role="tablist"
            aria-label="分析类型"
          >
            {[
              { value: 'panorama' as const, label: '全景分析' },
              { value: 'scenario' as const, label: '用户场景分析' },
            ].map((option) => {
              const isActive = option.value === selectedMonitorMode;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => onMonitorModeChange?.(option.value)}
                  className="min-h-8 rounded-lg px-3 text-[12px] font-medium transition-colors"
                  style={{
                    background: isActive ? 'var(--bg-elevated)' : 'transparent',
                    color: isActive ? 'var(--brand-primary)' : 'var(--text-secondary)',
                    boxShadow: isActive ? 'var(--shadow-sm)' : 'none',
                  }}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <select
            className="h-10 rounded-[12px] border bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-secondary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
            aria-label="问题范围"
          >
            <option>全部问题</option>
            {home?.monitoring_plan?.question_set_label ? (
              <option>{home.monitoring_plan.question_set_label}</option>
            ) : null}
          </select>
          <div
            className="inline-flex h-10 items-center rounded-[12px] border bg-[var(--bg-secondary)] px-3 text-[13px] text-[var(--text-secondary)]"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            {formatDateRange(home)}
          </div>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
        <section className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">对话次数 / 提及次数</div>
          <div className="mt-3 flex items-baseline gap-1 text-[var(--text-primary)]">
            <strong className="text-[30px] leading-none">{answerTotal}</strong>
            <span className="text-[13px] text-[var(--text-tertiary)]">/ {mentionTotal} 次</span>
          </div>
        </section>
        <section className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">提及率 / 引用率</div>
          <div className="mt-3 flex items-baseline gap-1 text-[var(--text-primary)]">
            <strong className="text-[30px] leading-none">{formatPercent(displayedMentionRate)}</strong>
            <span className="text-[13px] text-[var(--text-tertiary)]">/ {formatPercent(citation?.current_value)}</span>
          </div>
        </section>
        <section className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">品牌提及排名</div>
          <div className="mt-3 flex items-baseline gap-1 text-[var(--text-primary)]">
            <strong className="text-[30px] leading-none">{formatRank(rank)}</strong>
          </div>
        </section>
        <section className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-4">
          <div className="text-[13px] text-[var(--text-tertiary)]">正向提及 / 负向提及</div>
          <div className="mt-3 flex items-baseline gap-1 text-[var(--text-primary)]">
            <strong className="text-[30px] leading-none">{positiveTotal}</strong>
            <span className="text-[13px] text-[var(--text-tertiary)]">/ {negativeTotal} 次</span>
          </div>
        </section>
      </div>

      <div className="mt-6">
        <h3 className="border-l-4 border-[var(--brand-primary)] pl-3 text-[18px] font-semibold text-[var(--text-primary)]">
          平台表现
        </h3>
        <div className="mt-4 grid gap-3 md:grid-cols-2 2xl:grid-cols-4">
          {sources.map((row) => (
            <PlatformCard key={row.platform} row={row} />
          ))}
        </div>
      </div>

      <div className="mt-5 grid gap-4 xl:grid-cols-2">
        <RankingPanel home={home} selectedBrandName={selectedBrandName} />
        <ChartPlaceholder title="排名趋势" value={formatRank(rank)} />
        <ChartPlaceholder title="提及率趋势" value={formatPercent(displayedMentionRate)} />
        <ChartPlaceholder title="提及次数趋势" value={String(mentionTotal)} />
      </div>
    </section>
  );
}
