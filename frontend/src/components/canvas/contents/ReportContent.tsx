'use client';

import { isConfidenceCanvasReport } from '@/adapters/exportArtifacts';
import type { ReportCanvasContent } from '@/types/canvas';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { ReportPage } from './ReportScaffold';

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

function getCanonicalSections(content: ReportCanvasContent): CanonicalSection[] {
  return Array.isArray(content.data.sections)
    ? content.data.sections.filter(isRecord) as CanonicalSection[]
    : [];
}

function getFullMarkdown(content: ReportCanvasContent, sections: CanonicalSection[]): string {
  const bodySections = sections.filter((section) => section.section_name !== 'header');
  if (bodySections.length > 0) {
    return bodySections
      .map((section) => (typeof section.markdown === 'string' ? section.markdown.trim() : ''))
      .filter(Boolean)
      .join('\n\n')
      .trim();
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
          className="rounded-[20px] border bg-[var(--bg-tertiary)] px-6 py-6"
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
      className="rounded-[24px] border bg-[var(--bg-tertiary)] px-7 py-8 md:px-10 md:py-10"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="report-markdown text-[17px] leading-9 text-[var(--text-primary)]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="text-[40px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
                {children}
              </h1>
            ),
            h2: ({ children }) => (
              <h2 className="mt-14 pt-1 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)] first:mt-0">
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
              <blockquote className="mt-5 border-l-2 border-[var(--border-strong)] pl-4 text-[16px] leading-8 text-[var(--text-secondary)]">
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

function MissingCanonicalReport() {
  return (
    <section
      className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-8 md:py-8"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="space-y-3 text-[15px] leading-8 text-[var(--text-primary)]">
        <p>当前报告产物缺失 canonical `full_markdown / sections`，已阻止旧报告 fallback 渲染。</p>
        <p>需要回到后端 A5 canonical pipeline 重新生成报告。</p>
      </div>
    </section>
  );
}

export function ReportContent({ content, printMode = false }: { content: ReportCanvasContent; printMode?: boolean }) {
  if (isConfidenceCanvasReport(content)) {
    return <ConfidenceSignalContent content={content} printMode={printMode} />;
  }

  const sections = getCanonicalSections(content);
  const markdown = getFullMarkdown(content, sections);
  const metrics = getSummaryMetrics(sections);
  const headline = content.data.title || content.data.headline || 'GEO 评估报告';
  const subtitle =
    content.data.subtitle ||
    content.data.executive_summary ||
    '本页只渲染后端输出的 canonical GEO 报告，不再拼接旧版 report_v2。';
  const updatedAt = content.data.updated_at;

  return (
    <ReportPage className="w-full max-w-[1320px] space-y-6">
      <header
        className="rounded-[26px] border bg-[var(--bg-tertiary)] px-7 py-7 md:px-10 md:py-10"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="text-[12px] font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
          {content.category === 'scenario' ? 'GEO 场景分析报告' : 'GEO 全景分析报告'}
        </div>
        <h1 className="mt-3 text-[38px] font-semibold tracking-[-0.05em] text-[var(--text-primary)]">
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

      {markdown ? <MarkdownDocument markdown={markdown} /> : <MissingCanonicalReport />}
    </ReportPage>
  );
}
