import { RiExternalLinkLine } from '@remixicon/react';
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts';
import { getPlatformDisplayName } from '@/config/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import { PIE_COLORS } from '@/styles/chart-theme';
import type {
  DashboardSourceBoard,
  DashboardSourceCitationCase,
} from '@/types/dashboard';

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
  domain: string;
  url?: string;
  title?: string;
  is_official: boolean;
  label: string;
};

type CitationTableRow = {
  key: string;
  type: '官网' | '第三方';
  platform: string;
  question: string;
  sourceLabel: string;
  domain: string;
  url?: string;
};

function normalizeDomain(domain: string | null | undefined): string {
  const raw = String(domain || '').trim().toLowerCase();
  if (!raw) return '';
  const withoutProtocol = raw.replace(/^https?:\/\//, '');
  return withoutProtocol.split('/')[0]?.split('?')[0]?.split('#')[0]?.replace(/:.*$/, '') || '';
}

function extractDomainFromUrl(url: string | null | undefined): string {
  const raw = String(url || '').trim();
  if (!raw) return '';
  try {
    return normalizeDomain(new URL(raw).hostname);
  } catch {
    return normalizeDomain(raw);
  }
}

function extractRootDomain(domain: string | null | undefined): string {
  const normalized = normalizeDomain(domain);
  const parts = normalized.split('.').filter(Boolean);
  if (parts.length <= 2) return normalized;

  const tld2 = `${parts[parts.length - 2]}.${parts[parts.length - 1]}`;
  const knownSecondLevel = new Set(['com.cn', 'net.cn', 'org.cn', 'gov.cn']);
  if (knownSecondLevel.has(tld2) && parts.length >= 3) {
    return `${parts[parts.length - 3]}.${tld2}`;
  }
  return `${parts[parts.length - 2]}.${parts[parts.length - 1]}`;
}

function resolveOfficialDomains(
  topDomains: Array<{ domain: string; is_official?: boolean }>,
  cases: DashboardSourceCitationCase[],
): string[] {
  const roots = new Set<string>();

  for (const item of topDomains) {
    if (!item.is_official) continue;
    const root = extractRootDomain(item.domain);
    if (root) roots.add(root);
  }

  if (roots.size > 0) {
    return Array.from(roots);
  }

  for (const item of cases) {
    if (!item.is_official) continue;
    for (const domain of item.citation_domains || []) {
      const root = extractRootDomain(domain);
      if (root) roots.add(root);
    }
    for (const url of item.citation_urls || []) {
      const root = extractRootDomain(extractDomainFromUrl(url));
      if (root) roots.add(root);
    }
  }

  return Array.from(roots);
}

function isOfficialCitationDomain(domain: string, officialDomains: string[]): boolean {
  const normalized = normalizeDomain(domain);
  if (!normalized || officialDomains.length === 0) return false;
  return officialDomains.some((officialDomain) => {
    const official = normalizeDomain(officialDomain);
    return official && (normalized === official || normalized.endsWith(`.${official}`));
  });
}

function SourceTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ value?: number; payload?: TooltipPayload }>;
}) {
  if (!active || !payload?.length) return null;
  const item = payload[0]?.payload as TooltipPayload | undefined;
  if (!item) return null;

  return (
    <div
      className="min-w-[220px] rounded-[16px] border bg-[var(--bg-secondary)] px-3.5 py-3 shadow-[0_12px_28px_rgba(15,23,42,0.12)]"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="text-[13px] font-semibold text-[var(--text-primary)]">
        {item.label || item.source || '--'}
      </div>
      <div className="mt-1 text-[11px] text-[var(--text-tertiary)]">
        {item.source || '--'}
      </div>
      <div className="mt-2 text-[12px] text-[var(--text-secondary)]">
        {(item.percentage ?? 0).toFixed(1)}% · {item.count ?? 0} 次引用
      </div>
    </div>
  );
}

function buildCitationEntries(
  item: DashboardSourceCitationCase,
  officialDomains: string[],
): CitationEntry[] {
  const urls = item.citation_urls || [];
  const domains = item.citation_domains || [];
  const titles = item.citation_titles || [];
  const count = Math.max(urls.length, domains.length, titles.length, 1);
  const rows: CitationEntry[] = [];

  for (let index = 0; index < count; index += 1) {
    const url = urls[index] || urls[0] || undefined;
    const domain = domains[index] || extractDomainFromUrl(url) || domains[0] || '';
    const title = titles[index] || titles[0] || undefined;
    const isOfficial = officialDomains.length > 0
      ? isOfficialCitationDomain(domain, officialDomains)
      : Boolean(item.is_official);
    rows.push({
      key: `${item.scenario_id || item.scenario_label}-${domain || 'domain'}-${index}`,
      domain,
      url,
      title,
      is_official: isOfficial,
      label: getSourceLabel(domain, isOfficial) || title || domain || '未命名来源',
    });
  }

  const seen = new Set<string>();
  return rows.filter((row) => {
    const dedupeKey = `${row.url || ''}|${row.domain}|${row.title || ''}|${row.is_official}`;
    if (seen.has(dedupeKey)) return false;
    seen.add(dedupeKey);
    return true;
  });
}

function splitCitationCases(
  items: DashboardSourceCitationCase[],
  officialDomains: string[],
): DashboardSourceCitationCase[] {
  return items.flatMap((item) => {
    const links = buildCitationEntries(item, officialDomains);
    if (links.length === 0) return [];

    const groups = [
      { is_official: true, links: links.filter((link) => link.is_official) },
      { is_official: false, links: links.filter((link) => !link.is_official) },
    ].filter((group) => group.links.length > 0);

    return groups.map((group) => ({
      ...item,
      is_official: group.is_official,
      citation_domains: group.links.map((link) => link.domain),
      citation_titles: group.links.map((link) => link.title || ''),
      citation_urls: group.links.map((link) => link.url || ''),
    }));
  });
}

function getCaseQuestion(item: DashboardSourceCitationCase): string {
  const label = (item.scenario_label || '').trim();
  if (label && !/引用案例|引用样本/i.test(label)) return label;
  return item.citation_titles?.find(Boolean) || '未命名问题';
}

function buildCitationTableRows(
  items: DashboardSourceCitationCase[],
  officialDomains: string[],
): CitationTableRow[] {
  return items.flatMap((item) => {
    const question = getCaseQuestion(item);
    return buildCitationEntries(item, officialDomains).map((entry, entryIndex) => ({
      key: `${item.scenario_id || question}-${item.platform || 'unknown'}-${entry.domain}-${entryIndex}`,
      type: entry.is_official ? '官网' : '第三方',
      platform: item.platform ? getPlatformDisplayName(item.platform) : '--',
      question,
      sourceLabel: entry.label,
      domain: entry.domain || '--',
      url: entry.url,
    }));
  });
}

export function SourceBoardReport({ data }: SourceBoardReportProps) {
  const rawCases = [
    ...data.report.official_cases,
    ...data.report.non_official_cases,
  ];
  const officialDomains = resolveOfficialDomains(
    data.report.top_domains.map((item) => ({
      domain: item.domain,
      is_official: item.is_official,
    })),
    rawCases,
  );
  const topDomains = data.report.top_domains.map((item) => ({
    source: item.domain,
    label: getSourceLabel(item.domain, Boolean(item.is_official)),
    count: item.count,
    percentage: item.share * 100,
  }));
  const cases = splitCitationCases(rawCases, officialDomains);
  const tableRows = buildCitationTableRows(cases, officialDomains);
  const officialRowCount = tableRows.filter((item) => item.type === '官网').length;
  const thirdPartyRowCount = tableRows.filter((item) => item.type === '第三方').length;

  return (
    <div className="space-y-6">
      <section className="dashboard-report-panel rounded-[26px] p-6 md:p-7">
        <div className="mt-5 grid gap-4 md:grid-cols-4">
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">
              被引用回答
            </div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {data.cited_answer_count}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">
              被引用内容
            </div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {data.cited_content_count}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">
              官网引用链接
            </div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {officialRowCount}
            </div>
          </div>
          <div
            className="rounded-[18px] border bg-[var(--bg-elevated)] px-5 py-4"
            style={{ borderColor: 'var(--border-subtle)' }}
          >
            <div className="text-[11px] tracking-[0.12em] text-[var(--text-tertiary)]">
              第三方引用链接
            </div>
            <div className="mt-2 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {thirdPartyRowCount}
            </div>
          </div>
        </div>
      </section>

      <section
        className="dashboard-report-panel rounded-[24px] p-6"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
          <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">
            引用明细表
          </h4>
          <span className="text-[12px] text-[var(--text-tertiary)]">
            {tableRows.length} 条链接
          </span>
        </div>
        {tableRows.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-0">
              <thead>
                <tr className="text-left text-[12px] text-[var(--text-tertiary)]">
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    类型
                  </th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    平台
                  </th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    涉及问题
                  </th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    来源
                  </th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    域名
                  </th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">
                    链接
                  </th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row) => (
                  <tr key={row.key} className="align-top">
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3">
                      <span
                        className="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        style={{
                          color:
                            row.type === '官网' ? '#0f766e' : 'var(--text-secondary)',
                          backgroundColor:
                            row.type === '官网'
                              ? 'rgba(20,184,166,0.12)'
                              : 'var(--bg-secondary)',
                        }}
                      >
                        {row.type}
                      </span>
                    </td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">
                      {row.platform}
                    </td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-primary)]">
                      {row.question}
                    </td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">
                      {row.sourceLabel}
                    </td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-tertiary)]">
                      {row.domain}
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
                          <RiExternalLinkLine className="h-3.5 w-3.5 shrink-0" />
                        </a>
                      ) : (
                        <span>当前未保留原始链接</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-4 rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
            当前还没有可展示的引用明细。
          </div>
        )}
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.06fr_0.94fr]">
        <section
          className="dashboard-report-panel rounded-[24px] p-6"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="flex items-end justify-between gap-4 border-b border-[var(--border-subtle)] pb-3">
            <div>
              <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">
                来源分布
              </h4>
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
                  <Pie
                    data={topDomains}
                    cx="50%"
                    cy="50%"
                    innerRadius={62}
                    outerRadius={106}
                    dataKey="percentage"
                    nameKey="source"
                  >
                    {topDomains.map((_, index) => (
                      <Cell key={index} fill={PIE_COLORS[index % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip cursor={false} content={<SourceTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>

            <div className="max-h-[300px] space-y-2.5 overflow-y-auto pr-1">
              {topDomains.length > 0 ? (
                topDomains.map((item, index) => (
                  <div
                    key={item.source}
                    className="flex items-center gap-3 rounded-[16px] border bg-[var(--bg-elevated)] px-4 py-3.5"
                    style={{ borderColor: 'var(--border-subtle)' }}
                  >
                    <div
                      className="h-2.5 w-2.5 rounded-full"
                      style={{ backgroundColor: PIE_COLORS[index % PIE_COLORS.length] }}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="text-[13px] font-semibold text-[var(--text-primary)]">
                        {item.label}
                      </div>
                      <div className="mt-1 truncate text-[11px] text-[var(--text-tertiary)]">
                        {item.source}
                      </div>
                    </div>
                    <div className="text-right text-[12px] leading-5 text-[var(--text-secondary)]">
                      <div>{item.percentage.toFixed(1)}%</div>
                      <div>{item.count} 次</div>
                    </div>
                  </div>
                ))
              ) : (
                <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
                  当前还没有来源结构数据。
                </div>
              )}
            </div>
          </div>
        </section>

        <section
          className="dashboard-report-panel rounded-[24px] p-6"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <h4 className="text-[18px] font-semibold text-[var(--text-primary)]">
            平台引用差异
          </h4>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            {data.report.platform_stats.length > 0 ? (
              data.report.platform_stats.map((platform) => (
                <div
                  key={platform.platform}
                  className="rounded-[18px] border bg-[var(--bg-elevated)] p-5"
                  style={{ borderColor: 'var(--border-subtle)' }}
                >
                  <div className="text-[15px] font-semibold text-[var(--text-primary)]">
                    {getPlatformDisplayName(platform.platform)}
                  </div>
                  <div className="mt-3 space-y-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                    <div>
                      内容引用率 {(platform.content_citation_rate * 100).toFixed(1)}%
                    </div>
                    <div>
                      官网引用率 {(platform.official_citation_rate * 100).toFixed(1)}%
                    </div>
                    <div>
                      主要来源{' '}
                      {getSourceLabel(platform.top_domains[0]?.domain || '', false) ||
                        platform.top_domains[0]?.domain ||
                        '--'}
                    </div>
                  </div>
                </div>
              ))
            ) : (
              <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">
                当前还没有平台级引用差异数据。
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
