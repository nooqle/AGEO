'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { ReportHero, ReportPage } from './ReportScaffold';
import type { ReportCanvasContent } from '@/types/canvas';

interface SiteConfidenceReportContentProps {
  content: ReportCanvasContent;
  printMode?: boolean;
}

function normalizeSiteConfidenceMarkdown(value?: string) {
  const markdown = (value || '').trim();
  if (!markdown) return '';
  const lines = markdown.split(/\r?\n/);
  const sectionTitles = new Set([
    '结论',
    '为什么会得到这个判断',
    '直接证据：显著拉低平均分的页面',
    '下一步最高优先级解决的建议',
    '本次结果还需要注意',
  ]);
  const firstSectionIndex = lines.findIndex((line) => {
    const trimmed = line.trim();
    if (trimmed.startsWith('## ')) return true;
    return sectionTitles.has(trimmed.replace(/^#+\s*/, ''));
  });
  if (firstSectionIndex > 0) {
    return lines.slice(firstSectionIndex).join('\n').trim();
  }
  return markdown;
}

function formatUpdatedAt(value?: string) {
  if (!value) return '刚刚更新';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  const pad = (num: number) => String(num).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

export function SiteConfidenceReportContent({
  content,
}: SiteConfidenceReportContentProps) {
  const data = content.data;
  const markdown = normalizeSiteConfidenceMarkdown(
    typeof data.report_markdown === 'string' ? data.report_markdown : '',
  );
  return (
    <ReportPage className="max-w-none space-y-5">
      <ReportHero
        eyebrow="官网评估报告"
        title="官网 AI 友好度分析报告"
        meta={
          <>
            <span>{data.brand_name || data.root_domain || '未识别站点'}</span>
            <span>最近更新 {formatUpdatedAt(data.updated_at)}</span>
            {data.site_root_url ? <span>{data.site_root_url}</span> : null}
          </>
        }
      />

      {markdown ? (
        <section
          className="rounded-[22px] border bg-[var(--bg-tertiary)] px-6 py-6 md:px-8 md:py-8"
          style={{ borderColor: 'var(--border-subtle)' }}
        >
          <div className="report-markdown text-[17px] leading-9 text-[var(--text-primary)]">
            <ReactMarkdown
              remarkPlugins={[remarkGfm]}
              components={{
                h2: ({ children }) => (
                  <h2 className="mt-11 border-t border-[var(--border-subtle)] pt-7 text-[26px] font-semibold tracking-[-0.03em] text-[var(--text-primary)] first:mt-0 first:border-t-0 first:pt-0">
                    {children}
                  </h2>
                ),
                h3: ({ children }) => (
                  <h3 className="mt-7 text-[21px] font-semibold text-[var(--text-primary)]">{children}</h3>
                ),
                em: ({ children }) => (
                  <em className="text-[15px] italic text-[var(--text-secondary)]">{children}</em>
                ),
                p: ({ children }) => (
                  <p className="mt-4 text-[17px] leading-9 text-[var(--text-primary)] first:mt-0">{children}</p>
                ),
                ul: ({ children }) => (
                  <ul className="mt-4 space-y-2.5 pl-6 text-[17px] leading-9 text-[var(--text-primary)]">{children}</ul>
                ),
                ol: ({ children }) => (
                  <ol className="mt-4 space-y-2.5 pl-6 text-[17px] leading-9 text-[var(--text-primary)]">{children}</ol>
                ),
                li: ({ children }) => <li className="marker:text-[var(--text-tertiary)]">{children}</li>,
                blockquote: ({ children }) => (
                  <blockquote className="mt-5 rounded-[16px] border-l-4 border-[var(--text-accent)] bg-[var(--bg-secondary)] px-5 py-4 text-[16px] leading-8 text-[var(--text-secondary)]">
                    {children}
                  </blockquote>
                ),
                table: ({ children }) => (
                  <div className="mt-6 overflow-x-auto rounded-[18px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)]">
                    <table className="min-w-full border-collapse text-left text-[15px] leading-7 text-[var(--text-primary)]">
                      {children}
                    </table>
                  </div>
                ),
                thead: ({ children }) => (
                  <thead className="bg-[var(--bg-tertiary)] text-[var(--text-secondary)]">{children}</thead>
                ),
                tbody: ({ children }) => <tbody>{children}</tbody>,
                tr: ({ children }) => (
                  <tr className="border-t border-[var(--border-subtle)] first:border-t-0">{children}</tr>
                ),
                th: ({ children }) => (
                  <th className="px-4 py-3 text-[13px] font-semibold uppercase tracking-[0.04em]">{children}</th>
                ),
                td: ({ children }) => (
                  <td className="px-4 py-3 align-top text-[15px] leading-7">{children}</td>
                ),
                strong: ({ children }) => <strong className="font-bold text-[var(--text-primary)]">{children}</strong>,
                a: ({ href, children }) => (
                  <a href={href} className="font-medium text-[var(--text-accent)] underline underline-offset-4" target="_blank" rel="noreferrer">
                    {children}
                  </a>
                ),
                code: ({ children }) => (
                  <code className="rounded bg-[var(--bg-secondary)] px-1.5 py-0.5 text-[14px] font-medium text-[var(--text-primary)]">{children}</code>
                ),
              }}
            >
              {markdown}
            </ReactMarkdown>
          </div>
        </section>
      ) : null}
    </ReportPage>
  );
}
