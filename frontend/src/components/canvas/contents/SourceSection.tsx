import { useEffect, useRef, useState } from 'react';
import { Cell, Pie, PieChart, Tooltip } from 'recharts';
import { getSourceLabel } from '@/lib/sourceLabel';
import type { ReportCitationCase, SourceSectionData } from '@/types/canvas';
import { ReportMetricCard, ReportSection } from './ReportScaffold';

interface SourceSectionProps {
  data?: SourceSectionData | null;
  printMode?: boolean;
}

const PIE_COLORS = ['#1d4ed8', '#0f766e', '#b45309', '#7c3aed', '#be123c', '#2563eb', '#4d7c0f', '#9f1239', '#0f766e', '#334155'];

function formatRate(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function normalizeDomain(domain: string | null | undefined): string {
  const raw = String(domain || '').trim().toLowerCase();
  if (!raw) return '';
  const withoutProtocol = raw.replace(/^https?:\/\//, '');
  return withoutProtocol.split('/')[0]?.split('?')[0]?.split('#')[0]?.replace(/:.*$/, '') || '';
}

function buildTopSourcesFromCases(cases: ReportCitationCase[]) {
  const grouped = new Map<
    string,
    {
      label: string;
      count: number;
      isOfficial: boolean;
      domains: string[];
    }
  >();

  cases.forEach((item) => {
    const rawDomains = [
      ...(item.citation_domains ?? []),
      ...(item.citation_urls ?? []).map((url) => normalizeDomain(url)),
    ];
    const domains = [...new Set(rawDomains.map((domain) => normalizeDomain(domain)).filter(Boolean))];
    domains.forEach((domain) => {
      const label = getSourceLabel(domain, Boolean(item.is_official)) || `外部站点（${domain}）`;
      const existing = grouped.get(label) ?? {
        label,
        count: 0,
        isOfficial: Boolean(item.is_official),
        domains: [],
      };
      existing.count += 1;
      existing.isOfficial = existing.isOfficial || Boolean(item.is_official);
      existing.domains = [...new Set([...existing.domains, domain])];
      grouped.set(label, existing);
    });
  });

  const totalCount = [...grouped.values()].reduce((sum, item) => sum + item.count, 0);
  return [...grouped.values()]
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'zh-CN'))
    .slice(0, 10)
    .map((item) => ({
      domain: item.domains[0] || '',
      label: item.label,
      count: item.count,
      share: totalCount > 0 ? (item.count / totalCount) * 100 : 0,
      isOfficial: item.isOfficial,
      domains: item.domains,
    }));
}

function buildTopSources(data?: SourceSectionData | null) {
  if ((data?.citation_analysis?.top_domains?.length ?? 0) === 0 && (data?.citation_cases?.length ?? 0) > 0) {
    return buildTopSourcesFromCases(data?.citation_cases ?? []);
  }

  const grouped = new Map<
    string,
    {
      label: string;
      count: number;
      share: number;
      isOfficial: boolean;
      domains: string[];
    }
  >();

  (data?.citation_analysis?.top_domains ?? []).forEach((item) => {
    const domain = normalizeDomain(item.domain);
    if (!domain) return;
    const label = getSourceLabel(item.domain, item.is_official) || `外部站点（${domain}）`;
    const existing = grouped.get(label) ?? {
      label,
      count: 0,
      share: 0,
      isOfficial: item.is_official,
      domains: [],
    };
    existing.count += item.count;
    existing.share += item.share;
    existing.isOfficial = existing.isOfficial || item.is_official;
    existing.domains = [...new Set([...existing.domains, domain])];
    grouped.set(label, existing);
  });

  return [...grouped.values()]
    .sort((a, b) => b.count - a.count || b.share - a.share)
    .slice(0, 10)
    .map((item) => ({
      domain: item.domains[0] || '',
      label: item.label,
      count: item.count,
      share: item.share,
      isOfficial: item.isOfficial,
      domains: item.domains,
    }));
}

function buildPieData(data?: SourceSectionData | null) {
  const topSources = buildTopSources(data);
  if (topSources.length <= 5) return topSources;

  const primary = topSources.slice(0, 5);
  const others = topSources.slice(5);
  const othersCount = others.reduce((sum, item) => sum + item.count, 0);
  const othersShare = others.reduce((sum, item) => sum + item.share, 0);

  return [
    ...primary,
    {
      domain: 'others',
      label: '其他来源',
      count: othersCount,
      share: Number(othersShare.toFixed(1)),
      isOfficial: false,
    },
  ];
}

export function SourceSection({ data, printMode = false }: SourceSectionProps) {
  const chartFrameRef = useRef<HTMLDivElement | null>(null);
  const [chartSize, setChartSize] = useState(() => (printMode ? { width: 320, height: 240 } : { width: 0, height: 0 }));
  const topSources = buildTopSources(data);
  const pieData = buildPieData(data);
  const officialCount = topSources.filter((item) => item.isOfficial).reduce((sum, item) => sum + item.count, 0);
  const thirdPartyCount = topSources.filter((item) => !item.isOfficial).reduce((sum, item) => sum + item.count, 0);
  const citedQuestionCount = data?.cited_answer_count ?? 0;
  const mentionQuestionCount = data?.mention_question_count ?? 0;

  useEffect(() => {
    if (printMode) {
      return;
    }

    const node = chartFrameRef.current;
    if (!node || typeof ResizeObserver === 'undefined') {
      return;
    }

    const updateSize = () => {
      const width = Math.floor(node.clientWidth);
      const height = Math.floor(node.clientHeight);
      if (width > 0 && height > 0) {
        setChartSize((current) =>
          current.width === width && current.height === height ? current : { width, height }
        );
      }
    };

    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(node);

    return () => observer.disconnect();
  }, [printMode]);

  return (
    <ReportSection title={data?.title || '引用来源分析'}>
      <div className="grid gap-3 md:grid-cols-3">
        <ReportMetricCard
          label="内容引用率"
          value={formatRate(data?.content_citation_rate)}
          caption={
            <>
              公式：有引用来源的问题数 ÷ {mentionQuestionCount > 0 ? `${mentionQuestionCount} 个我方品牌被提及的问题` : '我方品牌被提及的问题数'}
              {mentionQuestionCount > 0 ? ` = ${citedQuestionCount}/${mentionQuestionCount}` : ''}
            </>
          }
        />
        <ReportMetricCard label="官网引用次数" value={officialCount} />
        <ReportMetricCard label="第三方引用次数" value={thirdPartyCount} />
      </div>

      <div className="mt-6 grid gap-5 xl:grid-cols-[minmax(320px,400px)_1fr]">
        <section className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">来源分布</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">{data?.citation_analysis?.total_citations ?? 0} 次引用</span>
          </div>
          {pieData.length > 0 ? (
            <div
              ref={printMode ? null : chartFrameRef}
              className="mt-4 h-[240px]"
              style={printMode ? { width: `${chartSize.width}px` } : undefined}
            >
              {chartSize.width > 0 && chartSize.height > 0 ? (
                <PieChart width={chartSize.width} height={chartSize.height}>
                  <Pie
                    data={pieData}
                    dataKey="count"
                    nameKey="label"
                    innerRadius={62}
                    outerRadius={92}
                    paddingAngle={3}
                    stroke="transparent"
                  >
                    {pieData.map((entry, index) => (
                      <Cell key={`${entry.domain}-${index}`} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(value, _name, payload) => [`${value ?? '--'} 次`, payload?.payload?.label || '来源']}
                    labelFormatter={() => '来源分布'}
                  />
                </PieChart>
              ) : null}
            </div>
          ) : (
            <div className="mt-4 rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
              当前还没有足够的来源分布数据。
            </div>
          )}
          {pieData.length > 0 ? (
            <div className="mt-4 space-y-2">
              {pieData.map((item, index) => (
                <div key={`${item.label}-${index}`} className="flex items-center justify-between gap-3 text-[12px] text-[var(--text-secondary)]">
                  <div className="flex items-center gap-2">
                    <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }} />
                    <span>{item.label}</span>
                  </div>
                  <span>{item.share.toFixed(1)}%</span>
                </div>
              ))}
            </div>
          ) : null}
        </section>

        <section className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">Top 10 来源</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">按引用次数排序</span>
          </div>
          {topSources.length > 0 ? (
            <div className="mt-4 space-y-3">
              {topSources.map((source, index) => (
                <div key={`${source.domain}-${index}`} className="rounded-[14px] border bg-[var(--bg-secondary)] px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-[13px] font-semibold text-[var(--text-primary)]">{index + 1}. {source.label}</span>
                        {source.isOfficial ? (
                          <span className="rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-700">官网</span>
                        ) : null}
                      </div>
                      <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{source.domains?.slice(0, 2).join(' / ') || source.domain}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-[14px] font-semibold text-[var(--text-primary)]">{source.count} 次</div>
                      <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{source.share.toFixed(1)}%</div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="mt-4 rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
              当前还没有可展示的头部来源。
            </div>
          )}
        </section>
      </div>
    </ReportSection>
  );
}
