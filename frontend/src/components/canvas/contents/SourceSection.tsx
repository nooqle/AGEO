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

function renderAICE(value: number | null | undefined): string {
  return value == null ? '--' : value.toFixed(1);
}

function buildQuestionLabel(item: ReportCitationCase, index: number): string {
  const label = (item.scenario_label || '').trim();
  if (label && !/引用案例|引用样本/i.test(label)) return label;
  return item.citation_titles?.find(Boolean) || `引用案例 ${index + 1}`;
}

function buildCitationRows(item: ReportCitationCase) {
  const urls = item.citation_urls ?? [];
  const domains = item.citation_domains ?? [];
  const titles = item.citation_titles ?? [];
  const count = Math.max(urls.length, domains.length, titles.length, 1);

  return Array.from({ length: count }).map((_, index) => {
    const url = urls[index] || urls[0];
    const domain = domains[index] || domains[0] || '';
    const title = titles[index] || titles[0];
    return {
      key: `${item.scenario_label}-${domain}-${index}`,
      domain,
      url,
      label: getSourceLabel(domain, Boolean(item.is_official)),
      title,
    };
  });
}

function CitationCaseCard({ item, index }: { item: ReportCitationCase; index: number }) {
  const links = buildCitationRows(item);
  return (
    <article className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border px-2.5 py-1 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {item.is_official ? '官网' : '第三方'}
        </span>
        <span className="rounded-full border px-2.5 py-1 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {item.platform ? getPlatformDisplayName(item.platform) : '--'}
        </span>
      </div>

      <div className="mt-4 space-y-1">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的问题</div>
        <div className="text-[16px] font-semibold leading-7 text-[var(--text-primary)]">{buildQuestionLabel(item, index)}</div>
      </div>

      <div className="mt-4 space-y-2">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">引用链接</div>
        <div className="space-y-2">
          {links.map((link) => (
            <div key={link.key} className="rounded-[14px] border bg-[var(--bg-secondary)] px-3.5 py-3" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="rounded-full border px-2 py-0.5 text-[11px] text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
                  {link.label}
                </span>
                {link.domain ? <span className="text-[11px] text-[var(--text-tertiary)]">{link.domain}</span> : null}
              </div>
              <div className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
                {link.url ? (
                  <a href={link.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 break-all text-[var(--color-primary)] hover:underline">
                    <span>{link.url}</span>
                    <RiExternalLinkLine className="h-3.5 w-3.5 shrink-0" />
                  </a>
                ) : (
                  <span>当前未保留原始链接</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-4 space-y-1">
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">涉及的答案</div>
        <div className="rounded-[16px] border bg-[var(--bg-secondary)] px-4 py-3.5 text-[14px] leading-7 text-[var(--text-secondary)]" style={{ borderColor: 'var(--border-subtle)' }}>
          {item.matched_answer || '当前没有保留可直接对应的答案片段。'}
        </div>
      </div>

      <div className="mt-4 rounded-[16px] border bg-[var(--bg-secondary)] px-4 py-3.5" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="text-[12px] font-medium text-[var(--text-secondary)]">链接置信度（AICE）</div>
        {item.aice_score != null || item.aice_dimensions ? (
          <div className="mt-3 grid gap-2 sm:grid-cols-5">
            <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">总分</div>
              <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICE(item.aice_score)}</div>
            </div>
            <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">权威性</div>
              <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICE(item.aice_dimensions?.authority)}</div>
            </div>
            <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">意图匹配</div>
              <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICE(item.aice_dimensions?.intent)}</div>
            </div>
            <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">清晰度</div>
              <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICE(item.aice_dimensions?.clarity)}</div>
            </div>
            <div className="rounded-[12px] bg-[var(--bg-elevated)] px-3 py-2">
              <div className="text-[11px] text-[var(--text-tertiary)]">证据性</div>
              <div className="mt-1 text-[16px] font-semibold text-[var(--text-primary)]">{renderAICE(item.aice_dimensions?.evidence)}</div>
            </div>
          </div>
        ) : (
          <div className="mt-2 text-[13px] leading-6 text-[var(--text-tertiary)]">待接入 AICE 评估，当前先展示引用证据链。</div>
        )}
      </div>
    </article>
  );
}

export function SourceSection({ data }: SourceSectionProps) {
  const cases = data?.citation_cases ?? [];
  const officialCases = cases.filter((item) => item.is_official);
  const thirdPartyCases = cases.filter((item) => !item.is_official);
  const analysis = data?.citation_analysis;

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
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data?.official_case_count ?? officialCases.length}</div>
        </div>
        <div className="rounded-[16px] border bg-[var(--bg-elevated)] p-4" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="text-[12px] text-[var(--text-tertiary)]">第三方引用</div>
          <div className="mt-2 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">{data?.non_official_case_count ?? thirdPartyCases.length}</div>
        </div>
      </div>

      <div className="mt-5 grid gap-6 xl:grid-cols-2">
        <section className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">官网引用案例</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">{officialCases.length} 条</span>
          </div>
          <div className="mt-4 space-y-3">
            {officialCases.length > 0 ? officialCases.map((item, index) => <CitationCaseCard key={`${item.scenario_label}-official-${index}`} item={item} index={index} />) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有官网引用案例。</div>}
          </div>
        </section>

        <section className="rounded-[18px] border bg-[var(--bg-elevated)] p-5" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="flex items-center justify-between gap-3 border-b border-[var(--border-subtle)] pb-3">
            <h3 className="text-[18px] font-semibold text-[var(--text-primary)]">第三方引用案例</h3>
            <span className="text-[12px] text-[var(--text-tertiary)]">{thirdPartyCases.length} 条</span>
          </div>
          <div className="mt-4 space-y-3">
            {thirdPartyCases.length > 0 ? thirdPartyCases.map((item, index) => <CitationCaseCard key={`${item.scenario_label}-third-${index}`} item={item} index={index} />) : <div className="rounded-[16px] border border-dashed border-[var(--border-subtle)] px-4 py-6 text-[14px] text-[var(--text-tertiary)]">当前还没有第三方引用案例。</div>}
          </div>
        </section>
      </div>

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
