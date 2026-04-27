'use client';

import {
  isConfidenceCanvasReport,
  isSiteConfidenceCanvasReport,
} from '@/adapters/exportArtifacts';
import type { ReportCanvasContent } from '@/types/canvas';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { ReportPage } from './ReportScaffold';
import { SiteConfidenceReportContent } from './SiteConfidenceReportContent';

type CanonicalSection = {
  section_name?: string;
  title?: string;
  markdown?: string;
  data?: unknown;
};

type SummaryMetricRow = [string, string, string];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function looksLikeSiteConfidenceFallback(content: ReportCanvasContent): boolean {
  const data = content.data;
  const title = [data.title, data.headline, content.title]
    .filter((value): value is string => typeof value === 'string' && value.trim().length > 0)
    .join(' ')
    .toLowerCase();

  if (title.includes('官网 ai 友好度') || title.includes('官网ai友好度')) {
    return true;
  }

  return Boolean(data.root_domain || data.site_root_url);
}

function formatUpdatedAt(value?: string) {
  if (!value) return undefined;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function getCanonicalSections(content: ReportCanvasContent): CanonicalSection[] {
  return Array.isArray(content.data.sections)
    ? content.data.sections.filter(isRecord) as CanonicalSection[]
    : [];
}

function getFullMarkdown(content: ReportCanvasContent, sections: CanonicalSection[]): string {
  const bodySections = sections.filter((section) => section.section_name !== 'header');
  if (bodySections.length > 0) {
    const sectionMarkdown = bodySections
      .map((section) => (typeof section.markdown === 'string' ? section.markdown.trim() : ''))
      .filter(Boolean)
      .join('\n\n')
      .trim();
    if (sectionMarkdown) {
      return sectionMarkdown;
    }
  }
  if (typeof content.data.full_markdown === 'string' && content.data.full_markdown.trim()) {
    return content.data.full_markdown.trim();
  }
  if (typeof content.data.report_markdown === 'string' && content.data.report_markdown.trim()) {
    return content.data.report_markdown.trim();
  }
  return sections
    .map((section) => (typeof section.markdown === 'string' ? section.markdown.trim() : ''))
    .filter(Boolean)
    .join('\n\n')
    .trim();
}

function getSummaryMetrics(sections: CanonicalSection[]): SummaryMetricRow[] {
  const summarySection = sections.find((section) => section.section_name === 'summary');
  const data = isRecord(summarySection?.data) ? summarySection.data : {};
  const rows = data.metrics;
  if (!Array.isArray(rows)) {
    return [];
  }
  return rows.filter(
    (row): row is SummaryMetricRow =>
      Array.isArray(row) &&
      row.length >= 3 &&
      typeof row[0] === 'string' &&
      typeof row[1] === 'string' &&
      typeof row[2] === 'string'
  );
}

function SummaryMetricStrip({ rows }: { rows: SummaryMetricRow[] }) {
  if (rows.length === 0) {
    return null;
  }

  return (
    <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-5" aria-label="核心指标">
      {rows.map(([label, value, description]) => (
        <article
          key={label}
          className="rounded-[12px] border bg-[var(--bg-report-muted)] px-6 py-6"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[13px] font-medium tracking-[0.08em] text-[var(--text-tertiary)]">
            {label}
          </div>
          <div className="mt-4 text-[32px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {value}
          </div>
          <p className="mt-3 text-[15px] leading-7 text-[var(--text-secondary)]">
            {description}
          </p>
        </article>
      ))}
    </section>
  );
}

function MarkdownDocument({ markdown }: { markdown: string }) {
  return (
    <section
      className="rounded-[12px] border bg-[var(--bg-report)] px-7 py-8 md:px-10 md:py-10"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="report-markdown text-[17px] leading-9 text-[var(--text-primary)]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="text-[38px] font-semibold tracking-normal text-[var(--text-primary)]">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-14 pt-1 text-[28px] font-semibold tracking-normal text-[var(--text-primary)] first:mt-0">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mt-8 text-[22px] font-semibold text-[var(--text-primary)]">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="mt-4 text-[17px] leading-9 text-[var(--text-primary)] first:mt-0">{children}</p>
            ),
            ul: ({ children }) => (
              <ul className="mt-4 list-disc space-y-3 pl-6 text-[17px] leading-9 text-[var(--text-primary)]">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="mt-4 list-decimal space-y-3 pl-6 text-[17px] leading-9 text-[var(--text-primary)]">{children}</ol>
            ),
            li: ({ children }) => <li className="pl-1 marker:text-[var(--text-tertiary)]">{children}</li>,
            table: ({ children }) => (
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full border-collapse text-left text-[15px] leading-8">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="border-b border-[var(--border-subtle)] text-[var(--text-secondary)]">{children}</thead>,
            th: ({ children }) => <th className="px-3 py-2 text-[14px] font-medium">{children}</th>,
            td: ({ children }) => (
              <td className="border-t border-[var(--border-subtle)] px-3 py-2 align-top text-[15px] text-[var(--text-primary)]">
                {children}
              </td>
            ),
            blockquote: ({ children }) => (
              <blockquote className="mt-4 rounded-md border border-[var(--border-subtle)] border-l-4 border-l-[var(--text-accent)] bg-[var(--bg-secondary)] px-5 py-3 text-[15px] leading-8 text-[var(--text-secondary)]">
                {children}
              </blockquote>
            ),
            strong: ({ children }) => (
              <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>
            ),
            code: ({ children }) => (
              <code className="rounded bg-[var(--bg-secondary)] px-1.5 py-0.5 text-[14px] text-[var(--text-primary)]">
                {children}
              </code>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>
    </section>
  );
}

function MissingCanonicalReport({
  debug,
  isHydrationStub = false,
}: {
  debug?: Record<string, string>;
  isHydrationStub?: boolean;
}) {
  if (isHydrationStub) {
    return (
      <section
        className="rounded-[12px] border bg-[var(--bg-report-muted)] px-6 py-8 md:px-8 md:py-10"
        style={{ borderColor: 'var(--border-subtle)' }}
        {...debug}
      >
        <div className="space-y-4 text-[15px] leading-8 text-[var(--text-primary)]">
          <div
            className="h-2 w-28 animate-pulse rounded-full"
            style={{ backgroundColor: 'var(--bg-secondary)' }}
          />
          <div className="space-y-2">
            <p>报告加载中，请稍候...</p>
            <p className="text-[var(--text-secondary)]">
              正在补全最新报告内容并打开右侧画布。
            </p>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      className="rounded-[12px] border bg-[var(--bg-report-muted)] px-6 py-6 md:px-8 md:py-8"
      style={{ borderColor: 'var(--border-subtle)' }}
      {...debug}
    >
      <div className="space-y-3 text-[15px] leading-8 text-[var(--text-primary)]">
        <p>当前报告内容不完整，暂时无法正常展示。</p>
        <p>请重新生成一次分析报告后再查看。</p>
      </div>
    </section>
  );
}

export function ReportContent({ content, printMode = false }: { content: ReportCanvasContent; printMode?: boolean }) {
  if (isConfidenceCanvasReport(content)) {
    return <ConfidenceSignalContent content={content} printMode={printMode} />;
  }

  if (isSiteConfidenceCanvasReport(content) || looksLikeSiteConfidenceFallback(content)) {
    return <SiteConfidenceReportContent content={content} printMode={printMode} />;
  }

  const sections = getCanonicalSections(content);
  const markdown = getFullMarkdown(content, sections);
  const metrics = getSummaryMetrics(sections);
  const headline = content.data.title || content.data.headline || '分析报告';
  const eyebrow =
    content.category === 'scenario' ? '用户场景分析报告' : '品牌全景分析报告';
  const subtitle =
    content.data.subtitle ||
    content.data.executive_summary ||
    '这里展示的是本次分析生成的最新报告内容。';
  const updatedAt = formatUpdatedAt(content.data.updated_at);
  const isMissingCanonicalMarkdown = !markdown;
  const fallbackDebugAttributes = isMissingCanonicalMarkdown
    ? {
        'data-debug-fallback': '1',
        'data-debug-artifact-id': content.id,
        'data-debug-source-output-id': content.sourceOutputId || '',
        'data-debug-is-hydration-stub': content.isHydrationStub ? '1' : '0',
        'data-debug-has-full-markdown': content.data.full_markdown ? '1' : '0',
        'data-debug-has-report-markdown': content.data.report_markdown ? '1' : '0',
        'data-debug-sections-len': Array.isArray(content.data.sections)
          ? String(content.data.sections.length)
          : '0',
      }
    : undefined;

  if (isMissingCanonicalMarkdown) {
    console.warn('[ReportContent] missing canonical markdown', {
      title: headline,
      artifactId: content.id,
      sourceOutputId: content.sourceOutputId,
      isHydrationStub: content.isHydrationStub,
      hasFullMarkdown: Boolean(content.data.full_markdown),
      hasReportMarkdown: Boolean(content.data.report_markdown),
      sectionsLen: Array.isArray(content.data.sections) ? content.data.sections.length : null,
      contentKeys: Object.keys(content.data || {}).slice(0, 40),
    });
  }

  return (
    <ReportPage className="w-full max-w-[1320px] space-y-6">
      <header
        className="rounded-[16px] border bg-[var(--bg-report)] px-6 py-7 md:px-8 md:py-10"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="text-[12px] font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
          {eyebrow}
        </div>
        <h1 className="mt-3 text-[36px] font-semibold tracking-normal text-[var(--text-primary)]">
          {headline}
        </h1>
        <p className="mt-5 max-w-[980px] text-[17px] leading-9 text-[var(--text-secondary)]">
          {subtitle}
        </p>
        {updatedAt ? (
          <div className="mt-5 text-[14px] text-[var(--text-secondary)]">更新于 {updatedAt}</div>
        ) : null}
      </header>

      <SummaryMetricStrip rows={metrics} />

      {markdown ? (
        <MarkdownDocument markdown={markdown} />
      ) : (
        <MissingCanonicalReport
          debug={fallbackDebugAttributes}
          isHydrationStub={content.isHydrationStub}
        />
      )}
    </ReportPage>
  );
}
