'use client';

import type { DashboardCitationDomain, DashboardCitationSourceType, DashboardHomeData, DashboardHomeMetric } from '@/types/dashboard';
import { DashboardSectionHeader } from './DashboardSectionHeader';

interface DashboardHomeBoardsProps {
  home: DashboardHomeData;
  onOpenLatestReport?: () => void;
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

function formatShare(value: number | null): string {
  if (value == null) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function SourceTypeList({ items }: { items: DashboardCitationSourceType[] }) {
  if (items.length === 0) {
    return <div className="text-[14px] leading-7 text-[var(--text-secondary)]">这轮还没有形成稳定的来源分布。</div>;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={item.key} className="space-y-1.5">
          <div className="flex items-center justify-between gap-3 text-[14px]">
            <span className="text-[var(--text-primary)]">{item.label}</span>
            <span className="font-medium text-[var(--text-primary)]">{formatShare(item.share)}</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-[var(--bg-secondary)]">
            <div
              className="h-full rounded-full bg-[var(--color-primary)]"
              style={{ width: item.share != null ? `${Math.max(6, Math.min(100, (item.share <= 1 ? item.share * 100 : item.share)))}%` : '0%' }}
            />
          </div>
        </li>
      ))}
    </ul>
  );
}

function TopDomainList({ items }: { items: DashboardCitationDomain[] }) {
  if (items.length === 0) {
    return <div className="text-[14px] leading-7 text-[var(--text-secondary)]">这轮还没有拿到稳定的品牌相关引用站点。</div>;
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 5).map((item) => (
        <li key={`${item.domain}-${item.display_name}`} className="rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-3">
          <div className="flex items-center justify-between gap-3">
            <div className="min-w-0">
              <div className="truncate text-[14px] font-medium text-[var(--text-primary)]">{item.display_name}</div>
              <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">
                {item.source_type_label || '其他'} · {item.domain}
              </div>
            </div>
            <div className="shrink-0 text-right">
              <div className="text-[14px] font-semibold text-[var(--text-primary)]">{item.count} 次</div>
              <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{formatShare(item.share)}</div>
            </div>
          </div>
        </li>
      ))}
    </ul>
  );
}

export function DashboardHomeBoards({ home, onOpenLatestReport }: DashboardHomeBoardsProps) {
  const metrics = home.metrics || [];
  const latestReport = home.latest_report;
  const citationDistribution = home.citation_distribution;
  const relatedQuestions = home.related_questions;

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

      <div className="rounded-[24px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-6 py-6">
        <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
          <div className="min-w-0">
            <div className="text-[12px] tracking-[0.12em] text-[var(--text-tertiary)]">
              {latestReport?.report_kind_label || '分析报告'}
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-3">
              <h2 className="text-[28px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                {latestReport?.title || '暂无最新报告'}
              </h2>
              {latestReport?.badge_label ? (
                <span
                  className="inline-flex items-center rounded-full border px-2.5 py-1 text-[12px] font-medium"
                  style={{
                    borderColor: 'color-mix(in srgb, var(--color-primary) 28%, var(--border-subtle) 72%)',
                    backgroundColor: 'color-mix(in srgb, var(--color-primary) 10%, var(--bg-secondary) 90%)',
                    color: 'var(--color-primary)',
                  }}
                >
                  {latestReport.badge_label}
                </span>
              ) : null}
            </div>
            <p className="mt-3 max-w-4xl text-[16px] leading-8 text-[var(--text-secondary)]">
              {home.summary.headline}
            </p>
          </div>

          {onOpenLatestReport && latestReport?.session_id ? (
            <button
              type="button"
              onClick={onOpenLatestReport}
              className="shrink-0 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-4 py-2 text-[13px] font-medium text-[var(--text-primary)] transition-colors hover:border-[var(--color-primary)] hover:text-[var(--color-primary)]"
            >
              {latestReport.action_label || '打开最新报告'}
            </button>
          ) : null}
        </div>

        <div className="mt-6 grid gap-4 lg:grid-cols-3">
          {metrics.map((metric) => (
            <div
              key={metric.id}
              className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-5"
            >
              <div className="text-[13px] text-[var(--text-tertiary)]">{metric.label}</div>
              <div className="mt-3 text-[34px] font-semibold tracking-[-0.03em] text-[var(--text-primary)]">
                {formatMetricValue(metric)}
              </div>
              {metric.subtitle ? (
                <div className="mt-3 text-[14px] leading-7 text-[var(--text-secondary)]">{metric.subtitle}</div>
              ) : null}
            </div>
          ))}
        </div>

        <div className="mt-6 grid gap-5 xl:grid-cols-[0.9fr_1.1fr]">
          <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-5">
            <div className="text-[18px] font-semibold text-[var(--text-primary)]">提及品牌的引用链接分布</div>
            <p className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
              {citationDistribution?.summary || '这轮还没有形成稳定的品牌相关链接分布。'}
            </p>

            <div className="mt-5">
              <div className="text-[13px] font-medium text-[var(--text-tertiary)]">来源分布</div>
              <div className="mt-3">
                <SourceTypeList items={citationDistribution?.source_types || []} />
              </div>
            </div>

            <div className="mt-6">
              <div className="text-[13px] font-medium text-[var(--text-tertiary)]">主要站点</div>
              <div className="mt-3">
                <TopDomainList items={citationDistribution?.top_domains || []} />
              </div>
            </div>
          </div>

          <div className="rounded-[22px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-5 py-5">
            <div className="text-[18px] font-semibold text-[var(--text-primary)]">这轮关联问题</div>
            <p className="mt-2 text-[14px] leading-7 text-[var(--text-secondary)]">
              {relatedQuestions?.summary || '暂无问题样本。'}
            </p>

            <ul className="mt-4 list-disc space-y-3 pl-5 text-[15px] leading-8 text-[var(--text-primary)]">
              {(relatedQuestions?.items || []).map((item) => (
                <li key={item.question_id}>
                  <span>{item.question_text}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </section>
  );
}
