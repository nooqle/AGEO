import { RiExternalLinkLine } from '@remixicon/react';
import { getPlatformDisplayName } from '@/lib/platformLabel';
import { getSourceLabel } from '@/lib/sourceLabel';
import type { ReportCitationCase, SourceSectionData } from '@/types/canvas';

interface SourceSectionProps {
  data?: SourceSectionData | null;
}

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

function resolveOfficialDomains(data?: SourceSectionData | null): string[] {
  const roots = new Set<string>();
  const explicit = extractRootDomain(data?.citation_analysis?.brand_domain);
  if (explicit) roots.add(explicit);

  for (const item of data?.citation_analysis?.top_domains ?? []) {
    if (!item.is_official) continue;
    const root = extractRootDomain(item.domain);
    if (root) roots.add(root);
  }

  if (roots.size > 0) {
    return Array.from(roots);
  }

  for (const item of data?.citation_cases ?? []) {
    if (!item.is_official) continue;
    for (const domain of item.citation_domains ?? []) {
      const root = extractRootDomain(domain);
      if (root) roots.add(root);
    }
    for (const url of item.citation_urls ?? []) {
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

function buildQuestionLabel(item: ReportCitationCase, index: number): string {
  const label = (item.scenario_label || '').trim();
  if (label && !/引用案例|引用样本/i.test(label)) return label;
  return item.citation_titles?.find(Boolean) || `引用案例 ${index + 1}`;
}

function buildCitationRows(item: ReportCitationCase, officialDomains: string[]) {
  const urls = item.citation_urls ?? [];
  const domains = item.citation_domains ?? [];
  const titles = item.citation_titles ?? [];
  const count = Math.max(urls.length, domains.length, titles.length, 1);

  return Array.from({ length: count }).map((_, index) => {
    const url = urls[index] || urls[0];
    const domain = domains[index] || extractDomainFromUrl(url) || domains[0] || '';
    const title = titles[index] || titles[0];
    return {
      key: `${item.scenario_label}-${domain}-${index}`,
      domain,
      url,
      is_official: officialDomains.length > 0
        ? isOfficialCitationDomain(domain, officialDomains)
        : Boolean(item.is_official),
      label: getSourceLabel(
        domain,
        officialDomains.length > 0 ? isOfficialCitationDomain(domain, officialDomains) : Boolean(item.is_official),
      ),
      title,
    };
  });
}

function splitCitationCases(items: ReportCitationCase[], officialDomains: string[]): ReportCitationCase[] {
  return items.flatMap((item) => {
    const links = buildCitationRows(item, officialDomains);
    if (links.length === 0) return [];

    const groups = [
      { is_official: true, links: links.filter((link) => link.is_official) },
      { is_official: false, links: links.filter((link) => !link.is_official) },
    ].filter((group) => group.links.length > 0);

    if (groups.length === 1) {
      return [{
        ...item,
        is_official: groups[0].is_official,
        citation_domains: groups[0].links.map((link) => link.domain),
        citation_titles: groups[0].links.map((link) => link.title || ''),
        citation_urls: groups[0].links.map((link) => link.url || ''),
      }];
    }

    return groups.map((group) => ({
      ...item,
      is_official: group.is_official,
      citation_domains: group.links.map((link) => link.domain),
      citation_titles: group.links.map((link) => link.title || ''),
      citation_urls: group.links.map((link) => link.url || ''),
    }));
  });
}

function buildCitationTableRows(items: ReportCitationCase[], officialDomains: string[]) {
  return items.flatMap((item, index) => {
    const question = buildQuestionLabel(item, index);
    return buildCitationRows(item, officialDomains).map((link, linkIndex) => ({
      key: `${item.scenario_label || question}-${item.platform || 'unknown'}-${link.domain}-${linkIndex}`,
      type: link.is_official ? '官网' : '第三方',
      platform: item.platform ? getPlatformDisplayName(item.platform) : '--',
      question,
      sourceLabel: link.label,
      domain: link.domain || '--',
      url: link.url,
    }));
  });
}

export function SourceSection({ data }: SourceSectionProps) {
  const officialDomains = resolveOfficialDomains(data);
  const rawCases = data?.citation_cases ?? [];
  const cases = splitCitationCases(rawCases, officialDomains);
  const analysis = data?.citation_analysis;
  const tableRows = buildCitationTableRows(cases, officialDomains);
  const officialLinkCount = tableRows.filter((item) => item.type === '官网').length;
  const thirdPartyLinkCount = tableRows.filter((item) => item.type === '第三方').length;

  return (
    <section className="rounded-[20px] border bg-[var(--bg-tertiary)] p-6" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="space-y-1.5 border-b border-[var(--border-subtle)] pb-4">
        <h2 className="text-[24px] font-semibold tracking-[-0.02em] text-[var(--text-primary)]">{data?.title || '内容引用分析'}</h2>
        <p className="max-w-3xl text-[14px] leading-7 text-[var(--text-secondary)]">
          {data?.description || '看品牌内容是否进入了答案，以及引用来自官网还是第三方站点。'}
        </p>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-4">
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">内容引用率</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{formatRate(data?.content_citation_rate)}</div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">被引用回答</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data?.cited_answer_count ?? '--'}</div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">官网引用</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{officialLinkCount}</div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">第三方引用</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{thirdPartyLinkCount}</div>
        </div>
      </div>

      <section className="mt-5 rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
          <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">引用明细表</h3>
          <span className="text-[12px] text-[var(--text-tertiary)]">{tableRows.length} 条链接</span>
        </div>
        {tableRows.length > 0 ? (
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full border-separate border-spacing-0">
              <thead>
                <tr className="text-left text-[12px] text-[var(--text-tertiary)]">
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">类型</th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">平台</th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">涉及问题</th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">来源</th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">域名</th>
                  <th className="border-b border-[var(--border-subtle)] px-3 py-3 font-medium">链接</th>
                </tr>
              </thead>
              <tbody>
                {tableRows.map((row) => (
                  <tr key={row.key} className="align-top">
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3">
                      <span
                        className="rounded-full px-2.5 py-1 text-[11px] font-medium"
                        style={{
                          color: row.type === '官网' ? '#0f766e' : 'var(--text-secondary)',
                          backgroundColor: row.type === '官网' ? 'rgba(20,184,166,0.12)' : 'var(--bg-secondary)',
                        }}
                      >
                        {row.type}
                      </span>
                    </td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">{row.platform}</td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-primary)]">{row.question}</td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-secondary)]">{row.sourceLabel || '--'}</td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] text-[var(--text-tertiary)]">{row.domain}</td>
                    <td className="border-b border-[var(--border-subtle)] px-3 py-3 text-[13px] leading-6 text-[var(--text-secondary)]">
                      {row.url ? (
                        <a href={row.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-[var(--color-primary)] hover:underline">
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

      {analysis?.top_domains && analysis.top_domains.length > 0 ? (
        <section className="mt-5 rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">来源分布</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">{analysis.total_citations ?? 0} 次引用</span>
          </div>
          <div className="mt-4 space-y-3">
            {analysis.top_domains.slice(0, 8).map((domain, index) => (
              <div key={`${domain.domain}-${index}`} className="flex items-center justify-between gap-3 rounded-[14px] border bg-[var(--bg-secondary)] px-4 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
                <div className="min-w-0">
                  <div className="text-[14px] font-semibold text-[var(--text-primary)]">{getSourceLabel(domain.domain, domain.is_official)}</div>
                  <div className="mt-1 text-[12px] text-[var(--text-tertiary)]">{domain.domain}</div>
                </div>
                <div className="text-right text-[12px] leading-5 text-[var(--text-secondary)]">
                  <div>{domain.share.toFixed(1)}%</div>
                  <div>{domain.count} 次</div>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </section>
  );
}
