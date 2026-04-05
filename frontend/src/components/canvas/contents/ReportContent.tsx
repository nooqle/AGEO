'use client';

import { buildReportViewModel } from '@/adapters/reportV2';
import { isConfidenceCanvasReport } from '@/adapters/exportArtifacts';
import { buildCustomerReportMarkdown } from '@/lib/canvasExportShared';
import type { ReportCanvasContent, ReportSummaryData, ReportV2Metric } from '@/types/canvas';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ConfidenceSignalContent } from './ConfidenceSignalContent';
import { ReportPage } from './ReportScaffold';

interface ReportContentProps {
  content: ReportCanvasContent;
  printMode?: boolean;
}

function formatMetricValue(metric: ReportV2Metric): string {
  if (metric.value === null || metric.value === undefined || metric.value === '') {
    return '--';
  }

  if (typeof metric.value === 'number') {
    if (metric.unit === '%' || metric.unit === 'ratio') {
      const ratioValue = metric.value <= 1 ? metric.value * 100 : metric.value;
      return `${ratioValue.toFixed(1)}%`;
    }
    const formatted = Number.isInteger(metric.value) ? String(metric.value) : metric.value.toFixed(1);
    return metric.unit ? `${formatted}${metric.unit}` : formatted;
  }

  const raw = String(metric.value);
  return metric.unit && !raw.endsWith(metric.unit) ? `${raw}${metric.unit}` : raw;
}

function joinText(values: Array<string | undefined | null>, fallback = '暂无'): string {
  const resolved = values
    .map((value) => (typeof value === 'string' ? value.trim() : ''))
    .filter(Boolean);
  return resolved.length > 0 ? resolved.join('；') : fallback;
}

function splitExecutiveSummary(summary?: string): string[] {
  if (!summary) {
    return [];
  }
  return summary
    .split(/\n+/)
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, 2);
}

function SummaryMetricStrip({ summary }: { summary: ReportSummaryData }) {
  const metrics = (summary.metrics ?? []).slice(0, 3);
  if (metrics.length === 0) {
    return null;
  }

  return (
    <section
      className="grid gap-3 md:grid-cols-3"
      aria-label="核心指标"
    >
      {metrics.map((metric) => (
        <article
          key={metric.id}
          className="rounded-[18px] border bg-[var(--bg-tertiary)] px-5 py-5"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[12px] font-medium tracking-[0.08em] text-[var(--text-tertiary)]">
            {metric.label}
          </div>
          <div className="mt-3 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
            {formatMetricValue(metric)}
          </div>
          <p className="mt-2 text-[13px] leading-6 text-[var(--text-secondary)]">
            {metric.description || metric.assessment || '可结合正文继续追问具体原因。'}
          </p>
        </article>
      ))}
    </section>
  );
}

function MarkdownDocument({ markdown }: { markdown: string }) {
  return (
    <section
      className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-8 md:py-8"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="report-markdown text-[15px] leading-8 text-[var(--text-primary)]">
        <ReactMarkdown
          remarkPlugins={[remarkGfm]}
          components={{
            h2: ({ children }) => (
              <h2 className="mt-10 border-t border-[var(--border-subtle)] pt-6 text-[22px] font-semibold tracking-[-0.03em] text-[var(--text-primary)] first:mt-0 first:border-t-0 first:pt-0">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="mt-6 text-[17px] font-semibold text-[var(--text-primary)]">{children}</h3>
            ),
            p: ({ children }) => (
              <p className="mt-3 text-[15px] leading-8 text-[var(--text-primary)] first:mt-0">{children}</p>
            ),
            ul: ({ children }) => (
              <ul className="mt-3 space-y-2 pl-5 text-[15px] leading-8 text-[var(--text-primary)]">{children}</ul>
            ),
            ol: ({ children }) => (
              <ol className="mt-3 space-y-2 pl-5 text-[15px] leading-8 text-[var(--text-primary)]">{children}</ol>
            ),
            li: ({ children }) => <li className="marker:text-[var(--text-tertiary)]">{children}</li>,
            table: ({ children }) => (
              <div className="mt-4 overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
                <table className="min-w-full border-collapse text-left text-[14px] leading-7">{children}</table>
              </div>
            ),
            thead: ({ children }) => <thead className="bg-[var(--bg-secondary)] text-[var(--text-secondary)]">{children}</thead>,
            th: ({ children }) => <th className="px-4 py-3 font-medium">{children}</th>,
            td: ({ children }) => (
              <td className="border-t border-[var(--border-subtle)] px-4 py-3 align-top text-[var(--text-primary)]">
                {children}
              </td>
            ),
            blockquote: ({ children }) => (
              <blockquote className="mt-4 rounded-[16px] border-l-4 border-[var(--text-accent)] bg-[var(--bg-secondary)] px-4 py-3 text-[14px] leading-7 text-[var(--text-secondary)]">
                {children}
              </blockquote>
            ),
            strong: ({ children }) => <strong className="font-semibold text-[var(--text-primary)]">{children}</strong>,
            a: ({ href, children }) => (
              <a href={href} className="text-[var(--text-accent)] underline underline-offset-4" target="_blank" rel="noreferrer">
                {children}
              </a>
            ),
            code: ({ children }) => (
              <code className="rounded bg-[var(--bg-secondary)] px-1.5 py-0.5 text-[13px] text-[var(--text-primary)]">{children}</code>
            ),
          }}
        >
          {markdown}
        </ReactMarkdown>
      </div>
    </section>
  );
}

function LegacyFallback({ content }: { content: ReportCanvasContent }) {
  const view = buildReportViewModel(content);
  const fallbackLines = [
    view.summary.summary,
    view.summary.status_summary,
    ...(view.summary.highlights ?? []),
    view.scenarioCoverage.summary,
    view.mentions.description,
    view.sources.summary,
  ].filter((item): item is string => Boolean(item && item.trim()));

  return (
    <section
      className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-8 md:py-8"
      style={{ borderColor: 'var(--border-subtle)' }}
    >
      <div className="space-y-3 text-[15px] leading-8 text-[var(--text-primary)]">
        {fallbackLines.length > 0 ? (
          fallbackLines.map((line) => <p key={line}>{line}</p>)
        ) : (
          <p>本轮报告已更新，可继续在对话中追问品牌提及、引用来源和主题覆盖的具体细节。</p>
        )}
      </div>
    </section>
  );
}

export function ReportContent({ content, printMode = false }: ReportContentProps) {
  if (isConfidenceCanvasReport(content)) {
    return <ConfidenceSignalContent content={content} printMode={printMode} />;
  }

  const view = buildReportViewModel(content);
  const reportMarkdown = buildCustomerReportMarkdown(content);
  const hasReportMarkdown = Boolean(reportMarkdown);
  const executiveSummaryLines = splitExecutiveSummary(content.data.executive_summary || content.data.content);

  return (
    <ReportPage className="max-w-[980px] space-y-5">
      <header
        className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-8 md:py-7"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            <div className="text-[12px] font-medium tracking-[0.14em] text-[var(--text-tertiary)]">
              {view.isBaseline ? '基线分析报告' : '品牌表现报告'}
            </div>
            <h1 className="mt-3 text-[30px] font-semibold tracking-[-0.04em] text-[var(--text-primary)]">
              {view.headline || '品牌分析报告'}
            </h1>
            {view.updatedAt ? (
              <div className="mt-3 text-[13px] text-[var(--text-secondary)]">更新于 {view.updatedAt}</div>
            ) : null}
          </div>
        </div>
        {!hasReportMarkdown && executiveSummaryLines.length > 0 ? (
          <div className="mt-5 space-y-2 text-[15px] leading-8 text-[var(--text-primary)]">
            {executiveSummaryLines.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        ) : !hasReportMarkdown && view.summary.summary ? (
          <p className="mt-5 text-[15px] leading-8 text-[var(--text-primary)]">{view.summary.summary}</p>
        ) : null}
        {view.degradationNote ? (
          <p className="mt-4 text-[13px] leading-7 text-[var(--text-secondary)]">{view.degradationNote}</p>
        ) : null}
      </header>

      <SummaryMetricStrip summary={view.summary} />

      {hasReportMarkdown ? <MarkdownDocument markdown={reportMarkdown} /> : <LegacyFallback content={content} />}

      {!hasReportMarkdown && (view.summary.highlights ?? []).length > 0 ? (
        <section
          className="rounded-[18px] border bg-[var(--bg-tertiary)] px-5 py-5"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="text-[14px] font-medium text-[var(--text-primary)]">重点提醒</div>
          <ul className="mt-3 space-y-2 pl-5 text-[14px] leading-7 text-[var(--text-secondary)]">
            {view.summary.highlights!.slice(0, 4).map((highlight) => (
              <li key={highlight}>{highlight}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {!hasReportMarkdown && (
        <section className="px-1 text-[13px] leading-7 text-[var(--text-secondary)]">
          {joinText(
            [
              '如需继续追问某个平台、具体负向提及、竞品压制场景或官网引用缺失原因，直接在对话里继续问即可。',
            ],
            ''
          )}
        </section>
      )}
    </ReportPage>
  );
}
