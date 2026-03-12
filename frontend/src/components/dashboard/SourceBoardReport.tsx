import { RiExternalLinkLine } from '@remixicon/react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { getPlatformDisplayName } from '@/lib/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import { PIE_COLORS } from '@/styles/chart-theme';
import type { DashboardAICEDimensions, DashboardSourceBoard, DashboardSourceCitationCase } from '@/types/dashboard';

interface SourceBoardReportProps {
  data: DashboardSourceBoard;
}

type TooltipPayload = {
  source?: string;
  label?: string;
  count?: number;
  percentage?: number;
};

type CitationEntry = {
  key: string;
  label: string;
  domain: string;
  url?: string;
  title?: string;
};

function SourceTooltip({ active, payload }: { active?: boolean; payload?: Array<{ value?: number; payload?: TooltipPayload }> }) {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload as TooltipPayload | undefined;
  if (!item) return null;

  return (
    <div
      className="min-w-[220px] rounded-[16px] border bg-[var(--bg-secondary)] px-3.5 py-3 shadow-[0_12px_28px_rgba(15,23,42,0.12)]"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="text-[13px] font-semibold text-[var(--text-primary)]">{item.label || item.source || '--'}</div>
      <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">{item.source || '--'}</div>
      <div className="mt-2 text-[12px] text-[var(--text-secondary)]">{(item.percentage ?? 0).toFixed(1)}% · {item.count ?? 0} 次引用</div>
    </div>
  );
}

function buildCitationEntries(item: DashboardSourceCitationCase): CitationEntry[] {
  const urls = item.citation_urls || [];
  const domains = item.citation_domains || [];
  const titles = item.citation_titles || [];
  const count = Math.max(urls.length, domains.length, titles.length, 1);
  const rows: CitationEntry[] = [];

  for (let index = 0; index < count; index += 1) {
    const url = urls[index] || urls[0] || undefined;
    const domain = domains[index] || domains[0] || '';
    const title = titles[index] || titles[0] || undefined;
    const label = getSourceLabel(domain, Boolean(item.is_official)) || title || domain || '未命名来源';
    rows.push({
      key: `${item.scenario_id || item.scenario_label}-${domain || 'domain'}-${index}`,
      label,
      domain,
      url,
      title,
    });
  }

  const seen = new Set<string>();
  return rows.filter((row) => {
    const dedupeKey = `${row.url || ''}|${row.domain}|${row.title || ''}`;
    if (seen.has(dedupeKey)) return false;
    seen.add(dedupeKey);
    return true;
  });
}

function getCaseQuestion(item: DashboardSourceCitationCase): string {
  const label = (item.scenario_label || '').trim();
  if (label && !/引用案例|引用样本/i.test(label)) return label;
  return item.citation_titles?.find(Boolean) || '未命名问题';
}

function renderAICEValue(value: number | null | undefined) {
  return value == null ? '--' : value.toFixed(1);
}

function AICEBlock({ score, dimensions }: { score?: number | null; dimensions?: DashboardAICEDimensions | null }) {
  const hasAice = score != null || Boolean(dimensions && Object.values(dimensions).some((value) => value != null));

  return (
    <div className="rounded-[16px] border bg-[var(--bg-secondary)] px-4 py-3.5" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="text-[12px] font-medium text-[var(--text-secondary)]">链接置信度（AICE）</div>
      {hasAice ? (
        <div className="mt-3 grid gap-2 sm:grid-cols-5">
          <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">总分</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICEValue(score)}</div>
          </div>
          <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">权威性</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICEValue(dimensions?.authority)}</div>
          </div>
          <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">意图匹配</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICEValue(dimensions?.intent)}</div>
          </div>
          <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">清晰度</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICEValue(dimensions?.clarity)}</div>
          </div>
          <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
            <div className="text-[11px] text-[var(--text-tertiary)]">证据性</div>
            <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICEValue(dimensions?.evidence)}</div>
          </div>
        </div>
      ) : (
        <div className="mt-2 text-[13px] leading-6 text-[var(--text-tertiary)]">待接入 AICE 评估，当前先展示引用证据链。</div>
      )}
    </div>
  );
}

function CitationCaseCard({ item }: { item: DashboardSourceCitationCase }) {
  const entries = buildCitationEntries(item);
  const question = getCaseQuestion(item);
  const caseType = item.is_official ? '官网' : '第三方';

  return (
    <article className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border px-2.5 py-1 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {item.platform ? getPlatformDisplayName(item.platform) : '--'}
        </span>
        <span className="rounded-full border px-2.5 py-1 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {caseType}
        </span>
      </div>

      <div className="mt-4 space-y-2">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的问题</div>
        <div className="text-[16px] font-semibold leading-7 text-[var(--text-primary)]">{question}</div>
      </div>

      <div className="mt-4 space-y-2">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">引用链接</div>
        <div className="space-y-2">
          {entries.length > 0 ? entries.map((entry) => (
            <div key={entry.key} className="rounded-[14px] border bg-[var(--bg-secondary)] px-3.5 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border px-2 py-0.5 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                  {entry.label}
                </span>
                {entry.domain ? (
                  <span className="text-[11px] text-[var(--text-tertiary)]">{entry.domain}</span>
                ) : null}
              </div>
              <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                {entry.url ? (
                  <a href={entry.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-[var(--color-primary)] hover:underline">
                    <span>{entry.url}</span>
                    <RiExternalLinkLine className="h-3.5 w-3.5 shrink-0" />
                  </a>
                ) : (
                  <span>当前未保留原始链接</span>
                )}
              </div>
            </div>
          )) : (
            <div className="rounded-[14px] border border-dashed px-3.5 py-3 text-[13px] text-[var(--text-tertiary)]" style={{ borderColor: 'var(--border-subtle)' }}>
              当前没有可展示的引用链接。
            </div>
          )}
        </div>
      </div>

      <div className="mt-4 space-y-2">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的答案</div>
        <div className="rounded-[16px] border bg-[var(--bg-secondary)] px-4 py-3.5 text-[14px] leading-7 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {item.matched_answer || '当前没有保留可直接对应的答案片段。'}
        </div>
      </div>

      <div className="mt-4">
        <AICEBlock score={item.aice_score} dimensions={item.aice_dimensions} />
      </div>
    </article>
  );
}

export function SourceBoardReport({ data }: SourceBoardReportProps) {
  const topDomains = data.report.top_domains.map((item) => ({
    source: item.domain,
    label: getSourceLabel(item.domain, Boolean(item.is_official)),
    count: item.count,
    percentage: item.share * 100,
  }));

  return (
    <div className="space-y-6">
      <section className="dashboard-report-panel rounded-[26px] p-6 md:p-7">
        <div className="mt-5 grid gap-4 md:grid-cols-4">
          <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">被引用回答</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data.cited_answer_count}</div>
          </div>
          <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">被引用内容</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data.cited_content_count}</div>
          </div>
          <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">官网引用</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data.report.official_cases.length}</div>
          </div>
          <div className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">第三方引用</div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data.report.non_official_cases.length}</div>
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        <section className="dashboard-report-panel rounded-[24px] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">官网引用案例</h4>
            <span className="text-[12px] text-[var(--text-tertiary)]">{data.report.official_cases.length} 条</span>
          </div>
          <div className="mt-4 space-y-3">
            {data.report.official_cases.length > 0 ? data.report.official_cases.map((item, index) => (
              <CitationCaseCard key={`${item.scenario_id}-${item.platform}-${index}`} item={item} />
            )) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有官网引用案例。</div>}
          </div>
        </section>

        <section className="dashboard-report-panel rounded-[24px] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">第三方引用案例</h4>
            <span className="text-[12px] text-[var(--text-tertiary)]">{data.report.non_official_cases.length} 条</span>
          </div>
          <div className="mt-4 space-y-3">
            {data.report.non_official_cases.length > 0 ? data.report.non_official_cases.map((item, index) => (
              <CitationCaseCard key={`${item.scenario_id}-${item.platform}-${index}`} item={item} />
            )) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有第三方引用案例。</div>}
          </div>
        </section>
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.06fr_0.94fr]">
        <section className="dashboard-report-panel rounded-[24px] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-3">
            <div>
              <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">来源分布</h4>
            </div>
            <div className="text-right text-[12px] leading-6 text-[var(--text-tertiary)]">
              <div>被引回答 {data.cited_answer_count}</div>
              <div>被引内容 {data.cited_content_count}</div>
            </div>
          </div>

          <div className="mt-5 grid gap-5 lg:grid-cols-[0.9fr_1.1fr]">
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={topDomains} cx="50%" cy="50%" innerRadius={62} outerRadius={106} dataKey="percentage" nameKey="source">
                    {topDomains.map((_, index) => (
                      <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip cursor={false} content={<SourceTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1">
              {topDomains.length > 0 ? topDomains.map((item, index) => (
                <div key={item.source} className="flex items-center gap-3 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-3.5" style={{ borderColor: 'var(--border-subtle)' }}>
                  <div className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }} />
                  <div className="min-w-0 flex-1">
                    <div className="text-[13px] font-semibold text-[var(--text-primary)]">{item.label}</div>
                    <div className="mt-1 truncate text-[11px] text-[var(--text-tertiary)]">{item.source}</div>
                  </div>
                  <div className="text-right text-[12px] leading-5 text-[var(--text-secondary)]">
                    <div>{item.percentage.toFixed(1)}%</div>
                    <div>{item.count} 次</div>
                  </div>
                </div>
              )) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有来源结构数据。</div>}
            </div>
          </div>
        </section>

        <section className="dashboard-report-panel rounded-[24px] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
          <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">平台引用差异</h4>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {data.report.platform_stats.length > 0 ? data.report.platform_stats.map((platform) => (
              <div key={platform.platform} className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="text-[15px] font-semibold text-[var(--text-primary)]">{getPlatformDisplayName(platform.platform)}</div>
                <div className="mt-3 space-y-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                  <div>内容引用率 {(platform.content_citation_rate * 100).toFixed(1)}%</div>
                  <div>官网引用率 {(platform.official_citation_rate * 100).toFixed(1)}%</div>
                  <div>主要来源 {getSourceLabel(platform.top_domains[0]?.domain || '', false) || platform.top_domains[0]?.domain || '--'}</div>
                </div>
              </div>
            )) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有平台级引用差异数据。</div>}
          </div>
        </section>
      </div>
    </div>
  );
}
