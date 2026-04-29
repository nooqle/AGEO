import type { ReactNode } from 'react';
import {
  buildConfidenceExportViewModel,
  buildFetchExportViewModel,
  isConfidenceCanvasReport,
} from '@/adapters/exportArtifacts';
import type {
  CanvasContent,
  ReportCanvasContent,
} from '@/types/canvas';
import {
  buildCanvasContentTextFromDescriptor,
  getReportExecutiveSummaryText,
  type ExportDescriptor,
} from '@/lib/canvasExportShared';

export const PDF_CSS = `
  @page {
    size: A4;
    margin: 12mm 10mm 14mm;
  }

  :root {
    --ink: #172033;
    --muted: #5f6b85;
    --line: #d7ddea;
    --line-strong: #b8c4d9;
    --paper: #f6f2ea;
    --panel: #fffdfa;
    --panel-soft: #f4efe5;
    --accent: #123b6a;
    --accent-soft: #dbe7f3;
    --good: #1d6f5f;
    --warn: #b7791f;
    --risk: #b14242;
    --brand: #1d4ed8;
    --competitor: #e11d48;
    --general: #64748b;
    --q1: #dff4eb;
    --q2: #fdf0cf;
    --q3: #e9eef3;
    --q4: #dff1fb;
  }

  * {
    box-sizing: border-box;
  }

  html, body {
    margin: 0;
    padding: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: "Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", sans-serif;
    -webkit-print-color-adjust: exact;
    print-color-adjust: exact;
  }

  body {
    font-size: 12px;
    line-height: 1.6;
  }

  .document {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }

  .hero {
    padding: 18px 20px;
    border: 1px solid var(--line);
    border-radius: 22px;
    background:
      radial-gradient(circle at top right, rgba(18, 59, 106, 0.16), transparent 32%),
      linear-gradient(180deg, #fffefa 0%, #f8f2e8 100%);
  }

  .eyebrow {
    margin: 0 0 10px;
    color: var(--accent);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.18em;
    text-transform: uppercase;
  }

  h1, h2, h3, p {
    margin: 0;
  }

  h1 {
    font-size: 28px;
    line-height: 1.18;
    letter-spacing: -0.04em;
  }

  .lede {
    margin-top: 10px;
    max-width: 88%;
    color: var(--muted);
    font-size: 13px;
    line-height: 1.8;
  }

  .meta-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 16px;
  }

  .pill {
    display: inline-flex;
    align-items: center;
    padding: 5px 9px;
    border-radius: 999px;
    border: 1px solid var(--line);
    background: rgba(255, 255, 255, 0.75);
    color: var(--muted);
    font-size: 10px;
    white-space: nowrap;
  }

  .section {
    border: 1px solid var(--line);
    border-radius: 18px;
    background: var(--panel);
    padding: 14px 16px;
  }

  .print-block {
    break-inside: avoid;
    page-break-inside: avoid;
  }

  .section-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--line);
  }

  .section-kicker {
    margin-bottom: 4px;
    color: var(--accent);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }

  .section-subtitle {
    color: var(--muted);
    font-size: 11px;
  }

  .grid {
    display: grid;
    gap: 10px;
  }

  .grid-2 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .grid-3 {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .metric-card,
  .info-card,
  .tone-card,
  .quote-card,
  .platform-card {
    border: 1px solid var(--line);
    border-radius: 14px;
    padding: 12px;
    background: linear-gradient(180deg, #fffdfa 0%, #f8f5ef 100%);
  }

  .metric-label {
    color: var(--muted);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
  }

  .metric-value {
    margin-top: 8px;
    font-size: 22px;
    font-weight: 700;
    line-height: 1.1;
  }

  .metric-note {
    margin-top: 6px;
    color: var(--muted);
    font-size: 11px;
    line-height: 1.65;
  }

  .prose {
    color: var(--ink);
    font-size: 12px;
    line-height: 1.8;
    white-space: pre-wrap;
  }

  .muted {
    color: var(--muted);
  }

  .list {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .list-item {
    padding: 10px 12px;
    border: 1px solid var(--line);
    border-radius: 12px;
    background: var(--panel-soft);
  }

  .list-title {
    font-size: 12px;
    font-weight: 700;
  }

  .list-meta {
    margin-top: 4px;
    color: var(--muted);
    font-size: 11px;
  }

  .list-body {
    margin-top: 6px;
    color: var(--ink);
    font-size: 11px;
    line-height: 1.7;
  }

  .table {
    width: 100%;
    border-collapse: collapse;
    table-layout: fixed;
  }

  .table th,
  .table td {
    vertical-align: top;
    padding: 9px 10px;
    border-bottom: 1px solid var(--line);
    text-align: left;
    font-size: 11px;
    line-height: 1.65;
    word-break: break-word;
  }

  .table th {
    color: var(--muted);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
  }

  .table tr:last-child td {
    border-bottom: none;
  }

  .tag {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 999px;
    background: var(--accent-soft);
    color: var(--accent);
    font-size: 10px;
    font-weight: 700;
  }

  .tag-good {
    background: rgba(29, 111, 95, 0.12);
    color: var(--good);
  }

  .tag-warn {
    background: rgba(183, 121, 31, 0.12);
    color: var(--warn);
  }

  .tag-risk {
    background: rgba(177, 66, 66, 0.12);
    color: var(--risk);
  }

  .platform-name {
    font-size: 14px;
    font-weight: 700;
  }

  .answer {
    margin-top: 10px;
    padding-top: 10px;
    border-top: 1px dashed var(--line-strong);
    white-space: pre-wrap;
    font-size: 11px;
    line-height: 1.72;
  }

  .small-list {
    margin-top: 10px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .small-item {
    padding: 8px 9px;
    border-radius: 10px;
    background: rgba(18, 59, 106, 0.04);
    font-size: 10px;
    line-height: 1.6;
  }

  .matrix-wrap {
    display: grid;
    grid-template-columns: 1.25fr 0.85fr;
    gap: 12px;
    align-items: start;
  }

  .legend {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .legend-item {
    display: flex;
    align-items: center;
    gap: 8px;
    color: var(--muted);
    font-size: 11px;
  }

  .swatch {
    width: 10px;
    height: 10px;
    border-radius: 999px;
    flex: none;
  }

  .quad-card {
    border-radius: 14px;
    border: 1px solid var(--line);
    padding: 12px;
  }

  .quad-q1 { background: var(--q1); }
  .quad-q2 { background: var(--q2); }
  .quad-q3 { background: var(--q3); }
  .quad-q4 { background: var(--q4); }

  .footer-note {
    color: var(--muted);
    font-size: 10px;
    text-align: right;
  }

  .page-break-before {
    break-before: page;
    page-break-before: always;
  }

  .appendix-section {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .appendix-block {
    padding: 12px;
    border: 1px solid var(--line);
    border-radius: 14px;
    background: linear-gradient(180deg, #fffdfa 0%, #f7f1e7 100%);
  }

  .appendix-title {
    font-size: 14px;
    font-weight: 700;
  }

  .appendix-body {
    margin-top: 8px;
    white-space: pre-wrap;
    word-break: break-word;
    font-size: 11px;
    line-height: 1.75;
  }
`;

function parseCompactTimestamp(value: string) {
  const match = /^(\\d{4})(\\d{2})(\\d{2})-(\\d{2})(\\d{2})(\\d{2})$/.exec(value);
  if (!match) {
    return value;
  }
  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}:${match[6]}`;
}

function joinInline(values: Array<string | undefined | null>, separator = ' · ') {
  return values.filter((value): value is string => Boolean(value && value.trim())).join(separator);
}

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(1);
}

function extractHostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\\./, '');
  } catch {
    return url;
  }
}

function getFetchResultStatusLabel(result: {
  status?: string;
  success?: boolean;
}) {
  const status = typeof result.status === 'string' ? result.status.trim().toLowerCase() : '';
  if (status === 'success' || (!status && result.success)) return '成功';
  if (status === 'skipped') return '已跳过';
  if (status === 'running') return '进行中';
  if (status === 'pending') return '待处理';
  if (status === 'takeover_required') return '待接管';
  return '失败';
}

function DocumentFrame({
  descriptor,
  title,
  subtitle,
  extraMeta,
  children,
}: {
  descriptor: ExportDescriptor;
  title: string;
  subtitle?: string;
  extraMeta?: string[];
  children: ReactNode;
}) {
  return (
    <div className="document">
      <section className="hero print-block">
        <p className="eyebrow">{descriptor.deliverableName}</p>
        <h1>{title}</h1>
        {subtitle ? <p className="lede">{subtitle}</p> : null}
        <div className="meta-row">
          <span className="pill">品牌：{descriptor.brandName}</span>
          <span className="pill">版本：v{descriptor.version}</span>
          <span className="pill">时间：{parseCompactTimestamp(descriptor.timestamp)}</span>
          {(extraMeta || []).map((item) => (
            <span key={item} className="pill">{item}</span>
          ))}
        </div>
      </section>
      {children}
      <div className="footer-note">Specta AI Export · {descriptor.brandName} · {descriptor.deliverableName}</div>
    </div>
  );
}

function Section({
  title,
  subtitle,
  kicker,
  children,
}: {
  title: string;
  subtitle?: string;
  kicker?: string;
  children: ReactNode;
}) {
  return (
    <section className="section print-block">
      <div className="section-header">
        <div>
          {kicker ? <div className="section-kicker">{kicker}</div> : null}
          <h2>{title}</h2>
        </div>
        {subtitle ? <div className="section-subtitle">{subtitle}</div> : null}
      </div>
      {children}
    </section>
  );
}

type AppendixBlock = {
  title: string;
  body: string;
};

function buildAppendixBlocks(markdown: string): AppendixBlock[] {
  const lines = markdown
    .split(/\r?\n/)
    .map((line) => line.trimEnd());

  const blocks: AppendixBlock[] = [];
  let currentTitle = '导出正文';
  let currentBody: string[] = [];

  const flush = () => {
    const body = currentBody.join('\n').trim();
    if (!body) {
      currentBody = [];
      return;
    }
    blocks.push({ title: currentTitle, body });
    currentBody = [];
  };

  for (const line of lines) {
    if (line.startsWith('# ')) {
      currentTitle = line.slice(2).trim() || currentTitle;
      continue;
    }

    if (line.startsWith('## ')) {
      flush();
      currentTitle = line.slice(3).trim() || '未命名章节';
      continue;
    }

    if (line.startsWith('### ')) {
      currentBody.push(line.slice(4).trim());
      continue;
    }

    if (line.startsWith('- ')) {
      currentBody.push(`• ${line.slice(2)}`);
      continue;
    }

    currentBody.push(line);
  }

  flush();
  return blocks;
}

function AppendixSection({ content, descriptor }: { content: CanvasContent; descriptor: ExportDescriptor }) {
  const appendixMarkdown = buildCanvasContentTextFromDescriptor(content, descriptor);
  const blocks = buildAppendixBlocks(appendixMarkdown);

  if (blocks.length === 0) {
    return null;
  }

  return (
    <div className="page-break-before">
      <Section
        title="完整导出附录"
        subtitle="附录保留完整文本内容。"
        kicker="Appendix"
      >
        <div className="appendix-section">
          {blocks.map((block, index) => (
            <div key={`${block.title}-${index}`} className="appendix-block">
              <div className="appendix-title">{block.title}</div>
              <div className="appendix-body">{block.body}</div>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

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
  if (Array.isArray(content.data.report_sections)) {
    return content.data.report_sections.filter(isRecord) as CanonicalSection[];
  }
  return Array.isArray(content.data.sections)
    ? content.data.sections.filter(isRecord) as CanonicalSection[]
    : [];
}

function getCanonicalSummaryMetrics(sections: CanonicalSection[]): SummaryMetricRow[] {
  const summary = sections.find((section) => section.section_name === 'summary');
  const data = isRecord(summary?.data) ? summary.data : {};
  const metrics = data.metrics;
  if (!Array.isArray(metrics)) {
    return [];
  }
  return metrics.filter(
    (row): row is SummaryMetricRow =>
      Array.isArray(row) &&
      row.length >= 3 &&
      typeof row[0] === 'string' &&
      typeof row[1] === 'string' &&
      typeof row[2] === 'string'
  );
}

function getCanonicalReportMarkdown(content: ReportCanvasContent, sections: CanonicalSection[]): string {
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

function normalizeMarkdownForPdf(markdown: string): string {
  return markdown
    .replace(/^#{1,6}\s+/gm, '')
    .replace(/^\|(.+)\|$/gm, '$1')
    .replace(/^\|?\s*---.*$/gm, '')
    .replace(/^\d+\.\s+/gm, '• ')
    .replace(/^- /gm, '• ')
    .replace(/^\> /gm, '')
    .replace(/`([^`]+)`/g, '$1')
    .trim();
}

function ReportPdfDocument({ content, descriptor }: { content: ReportCanvasContent; descriptor: ExportDescriptor }) {
  const sections = getCanonicalSections(content);
  const summaryMetrics = getCanonicalSummaryMetrics(sections);
  const canonicalMarkdown = getCanonicalReportMarkdown(content, sections);
  const renderedSections = sections.filter(
    (section) =>
      section.section_name !== 'header' &&
      section.section_name !== 'appendix' &&
      typeof section.markdown === 'string' &&
      section.markdown.trim()
  );
  const platforms = content.data.platform_scope && content.data.platform_scope.length > 0
    ? [`平台：${content.data.platform_scope.join(' / ')}`]
    : [];
  const title = content.data.title || content.data.headline || descriptor.title || descriptor.deliverableName;
  const subtitle = getReportExecutiveSummaryText(content);

  return (
    <DocumentFrame
      descriptor={descriptor}
      title={title}
      subtitle={subtitle}
      extraMeta={platforms}
    >
      {summaryMetrics.length > 0 ? (
        <Section title="核心指标" subtitle="本次交付的关键指标">
          <div className="grid grid-3">
            {summaryMetrics.map(([label, value, description]) => (
              <div key={label} className="metric-card">
                <div className="metric-label">{label}</div>
                <div className="metric-value">{value}</div>
                <div className="metric-note">{description}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {renderedSections.map((section, index) => {
        const normalized = normalizeMarkdownForPdf(section.markdown || '');
        const blocks = buildAppendixBlocks(normalized);
        return (
          <Section
            key={`${section.section_name || section.title || 'section'}-${index}`}
            title={section.title || `章节 ${index + 1}`}
            subtitle={section.section_name === 'summary' ? '本节由后端 canonical builder 直接生成。' : undefined}
          >
            <div className="appendix-section">
              {blocks.length > 0 ? (
                blocks.map((block, blockIndex) => (
                  <div key={`${block.title}-${blockIndex}`} className="appendix-block">
                    <div className="appendix-title">{block.title}</div>
                    <div className="appendix-body">{block.body}</div>
                  </div>
                ))
              ) : (
                <div className="prose">{normalized || '当前章节暂无可导出的正文。'}</div>
              )}
            </div>
          </Section>
        );
      })}

      {!renderedSections.length && canonicalMarkdown ? (
        <Section title="报告正文" subtitle="当前 PDF 直接导出 canonical markdown。">
          <div className="prose">{normalizeMarkdownForPdf(canonicalMarkdown)}</div>
        </Section>
      ) : null}


      <AppendixSection content={content} descriptor={descriptor} />
    </DocumentFrame>
  );
}

function FetchPdfDocument({ content, descriptor }: { content: Extract<CanvasContent, { type: 'fetchResults' }>; descriptor: ExportDescriptor }) {
  const view = buildFetchExportViewModel(content);
  const fetchResults = view.items;

  return (
    <DocumentFrame
      descriptor={descriptor}
      title={descriptor.title || view.title || descriptor.deliverableName}
      subtitle={view.subtitle}
      extraMeta={[`问题数：${view.totalQuestions}`, `平台数：${view.totalPlatforms}`, `成功答案：${view.successCount}`]}
    >
      {fetchResults.map((item, index) => (
        <Section key={item.question_id || `${index}`} title={`问题 ${index + 1}`} subtitle={item.question_text}>
          <div className="grid grid-2">
            {item.platform_results.map((result, resultIndex) => (
              <div key={`${result.platform}-${resultIndex}`} className="platform-card">
                {(() => {
                  const statusLabel = getFetchResultStatusLabel(result);
                  const isSuccess = statusLabel === '成功';
                  return (
                    <>
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <div className="platform-name">{result.platform_name || result.platform}</div>
                  <span className={isSuccess ? 'tag tag-good' : statusLabel === '已跳过' ? 'tag' : 'tag tag-risk'}>
                    {statusLabel}
                  </span>
                </div>
                <div className="list-meta" style={{ marginTop: 6 }}>
                  {joinInline([
                    result.fetch_method ? `方式 ${result.fetch_method}` : undefined,
                    typeof result.duration === 'number' ? `耗时 ${result.duration.toFixed(1)}s` : undefined,
                    typeof result.answer?.word_count === 'number' ? `${result.answer.word_count} 字` : undefined,
                    typeof result.answer?.has_brand_mention === 'boolean' ? (result.answer.has_brand_mention ? '提到品牌' : '未提到品牌') : undefined,
                  ]) || '--'}
                </div>
                {isSuccess ? (
                  <div className="answer">{result.answer?.content || '无答案内容'}</div>
                ) : (
                  <div className="answer">
                    {statusLabel === '已跳过'
                      ? '该平台已跳过'
                      : statusLabel === '进行中'
                        ? '该平台仍在抓取中'
                        : statusLabel === '待处理'
                          ? '该平台尚未开始处理'
                          : statusLabel === '待接管'
                            ? '该平台等待人工接管'
                            : result.error || '抓取失败'}
                  </div>
                )}
                {result.citations && result.citations.length > 0 ? (
                  <div className="small-list">
                    {result.citations.map((citation) => (
                      <div key={`${citation.index}-${citation.url}`} className="small-item">
                        <strong>[{citation.index}] {citation.title}</strong>
                        <br />
                        {joinInline([
                          citation.site_name || extractHostname(citation.url),
                          citation.is_official ? '官网' : '第三方',
                          citation.url,
                        ])}
                      </div>
                    ))}
                  </div>
                ) : null}
                    </>
                  );
                })()}
              </div>
            ))}
          </div>
        </Section>
      ))}

      <AppendixSection content={content} descriptor={descriptor} />
    </DocumentFrame>
  );
}

function ConfidencePdfDocument({ content, descriptor }: { content: ReportCanvasContent; descriptor: ExportDescriptor }) {
  const view = buildConfidenceExportViewModel(content);
  const summary = view.summary;
  const findings = view.findings;
  const brandOverview = view.brandConfidenceOverview;
  const competitorOverview = view.competitorConfidenceOverview;
  const brandPatterns = view.brandLowConfidencePatterns;
  const competitorPatterns = view.competitorLowConfidencePatterns;
  const recommendations = view.strategicRecommendations;
  const extraEvaluation = view.extraEvaluation;
  const items = view.items;

  return (
    <DocumentFrame
      descriptor={descriptor}
      title={view.title || descriptor.deliverableName}
      subtitle={view.subtitle || view.overallConclusion}
      extraMeta={[
        `样本数：${summary?.auto_evaluated_count ?? summary?.evaluated_count ?? items.length}`,
        `额外评估：${summary?.manual_count ?? extraEvaluation?.count ?? 0}`,
      ]}
    >
      {summary ? (
        <Section title="核心指标" subtitle="我方与竞品引用内容的平均置信度">
          <div className="grid grid-2">
            {[
              {
                label: '我方平均置信度',
                value: formatScore(brandOverview?.average_confidence ?? undefined),
                note: joinInline([
                  `加权平均 ${formatScore(brandOverview?.weighted_average_confidence ?? undefined)}`,
                  `样本数 ${brandOverview?.source_count ?? 0}`,
                  `低置信 ${brandOverview?.low_confidence_source_count ?? 0}`,
                ]),
              },
              {
                label: '竞品平均置信度',
                value: formatScore(competitorOverview?.average_confidence ?? undefined),
                note: joinInline([
                  `加权平均 ${formatScore(competitorOverview?.weighted_average_confidence ?? undefined)}`,
                  `样本数 ${competitorOverview?.source_count ?? 0}`,
                  `低置信 ${competitorOverview?.low_confidence_source_count ?? 0}`,
                ]),
              },
              {
                label: '评估来源',
                value: String(summary.auto_evaluated_count ?? summary.evaluated_count ?? 0),
                note: joinInline([
                  `总引用 ${summary.total_citations ?? 0}`,
                  `额外评估 ${summary.manual_count ?? extraEvaluation?.count ?? 0}`,
                ]),
              },
              {
                label: '平均置信分',
                value: formatScore(summary.average_confidence_score ?? summary.average_score),
                note: summary.updated_at ? `最近更新 ${summary.updated_at}` : undefined,
              },
            ].map((metric) => (
              <div key={metric.label} className="metric-card">
                <div className="metric-label">{metric.label}</div>
                <div className="metric-value">{metric.value}</div>
                {metric.note ? <div className="metric-note">{metric.note}</div> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section title="品牌 vs 竞品置信度对比" subtitle="重点看我方与竞品被引用时的整体质量差异">
        <div className="grid grid-2">
          {[
            { title: '我方引用来源', overview: brandOverview },
            { title: '竞品引用来源', overview: competitorOverview },
          ].map((item) => (
            <div key={item.title} className="info-card">
              <div className="metric-label">{item.title}</div>
              <div className="metric-value" style={{ marginTop: 10 }}>
                {formatScore(item.overview?.average_confidence ?? undefined)}
              </div>
              <div className="metric-note">
                {joinInline([
                  `加权平均 ${formatScore(item.overview?.weighted_average_confidence ?? undefined)}`,
                  `样本数 ${item.overview?.source_count ?? 0}`,
                  `低置信 ${item.overview?.low_confidence_source_count ?? 0}`,
                ]) || '暂无概览'}
              </div>
              {item.overview?.representative_sources && item.overview.representative_sources.length > 0 ? (
                <div className="small-list">
                  {item.overview.representative_sources.slice(0, 3).map((source, index) => (
                    <div key={`${item.title}-${source.label || source.domain || index}`} className="small-item">
                      <strong>{source.label || source.domain || '未命名来源'}</strong>
                      <br />
                      {joinInline([
                        source.domain,
                        typeof source.score === 'number' ? `置信度 ${formatScore(source.score)}` : undefined,
                        typeof source.frequency === 'number' ? `频次 ${source.frequency}` : undefined,
                      ])}
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </Section>

      {findings.length > 0 ? (
        <Section title="关键发现" subtitle="给 PM、运营、内容团队看的结论层">
          <div className="list">
            {findings.map((item, index) => (
              <div key={`${item.title}-${index}`} className="list-item">
                <div className="list-title">{item.title || `发现 ${index + 1}`}</div>
                {item.description ? <div className="list-body">{item.description}</div> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {brandPatterns.length > 0 ? (
        <Section title="我方低置信内容共性" subtitle="低置信内容中的重复问题模式">
          <div className="list">
            {brandPatterns.map((pattern, index) => (
              <div key={`${pattern.pattern_key || pattern.pattern_label}-${index}`} className="list-item">
                <div className="list-title">{pattern.pattern_label || `模式 ${index + 1}`}</div>
                <div className="list-meta">
                  {joinInline([
                    typeof pattern.sample_count === 'number' ? `样本 ${pattern.sample_count}` : undefined,
                    typeof pattern.average_confidence === 'number'
                      ? `平均置信度 ${formatScore(pattern.average_confidence ?? undefined)}`
                      : undefined,
                    pattern.affected_dimensions?.length ? `维度 ${pattern.affected_dimensions.join('、')}` : undefined,
                  ])}
                </div>
                {pattern.suggestion ? <div className="list-body">建议：{pattern.suggestion}</div> : null}
                {pattern.evidence_examples && pattern.evidence_examples.length > 0 ? (
                  <div className="small-list">
                    {pattern.evidence_examples.slice(0, 3).map((example, exampleIndex) => (
                      <div key={`${pattern.pattern_key || pattern.pattern_label}-${example.label || exampleIndex}`} className="small-item">
                        <strong>{example.label || '未命名样例'}</strong>
                        <br />
                        {joinInline([
                          example.domain,
                          typeof example.score === 'number' ? `置信度 ${formatScore(example.score)}` : undefined,
                          example.evidence,
                        ])}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {competitorPatterns.length > 0 ? (
        <Section title="竞品低置信内容共性" subtitle="重点看竞品高频但低质量的重复模式">
          <div className="list">
            {competitorPatterns.map((pattern, index) => (
              <div key={`${pattern.pattern_key || pattern.pattern_label}-${index}`} className="list-item">
                <div className="list-title">{pattern.pattern_label || `模式 ${index + 1}`}</div>
                <div className="list-meta">
                  {joinInline([
                    typeof pattern.sample_count === 'number' ? `样本 ${pattern.sample_count}` : undefined,
                    typeof pattern.average_confidence === 'number'
                      ? `平均置信度 ${formatScore(pattern.average_confidence ?? undefined)}`
                      : undefined,
                    pattern.affected_dimensions?.length ? `维度 ${pattern.affected_dimensions.join('、')}` : undefined,
                  ])}
                </div>
                {pattern.suggestion ? <div className="list-body">建议：{pattern.suggestion}</div> : null}
                {pattern.evidence_examples && pattern.evidence_examples.length > 0 ? (
                  <div className="small-list">
                    {pattern.evidence_examples.slice(0, 3).map((example, exampleIndex) => (
                      <div key={`${pattern.pattern_key || pattern.pattern_label}-${example.label || exampleIndex}`} className="small-item">
                        <strong>{example.label || '未命名样例'}</strong>
                        <br />
                        {joinInline([
                          example.domain,
                          typeof example.score === 'number' ? `置信度 ${formatScore(example.score)}` : undefined,
                          example.evidence,
                        ])}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {recommendations.length > 0 ? (
        <Section title="补位建议" subtitle="建议必须来自真实低置信模式，而不是规则层脑补">
          <div className="list">
            {recommendations.map((item, index) => (
              <div key={`${item.title || 'recommendation'}-${index}`} className="list-item">
                <div className="list-title">{item.title || `建议 ${index + 1}`}</div>
                {item.reason ? <div className="list-meta">{item.reason}</div> : null}
                {item.action ? <div className="list-body">{item.action}</div> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {extraEvaluation?.items && extraEvaluation.items.length > 0 ? (
        <Section title="额外评估结果" subtitle="保留追加评估的单条结果，便于追溯">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '36%' }}>来源</th>
                <th style={{ width: '14%' }}>置信度</th>
                <th style={{ width: '14%' }}>频次</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {extraEvaluation.items.map((item, index) => (
                <tr key={`${item.item_id || item.label}-${index}`}>
                  <td>{item.label}</td>
                  <td>{formatScore(item.aice_score ?? item.overall_confidence)}</td>
                  <td>{item.frequency ?? item.occurrences ?? '--'}</td>
                  <td>{joinInline([item.domain, item.site_name, item.error_message], ' ｜ ') || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      <AppendixSection content={content} descriptor={descriptor} />
    </DocumentFrame>
  );
}

function PdfDocument({ content, descriptor }: { content: CanvasContent; descriptor: ExportDescriptor }) {
  if (content.type === 'fetchResults') {
    return <FetchPdfDocument content={content} descriptor={descriptor} />;
  }

  if (content.type === 'report' && isConfidenceCanvasReport(content)) {
    return <ConfidencePdfDocument content={content} descriptor={descriptor} />;
  }

  if (content.type === 'report') {
    return <ReportPdfDocument content={content} descriptor={descriptor} />;
  }

  return (
    <DocumentFrame descriptor={descriptor} title={descriptor.title || descriptor.deliverableName}>
      <Section title="暂不支持的交付物">
        <div className="prose">当前内容类型暂不支持 PDF 模板导出。</div>
      </Section>
    </DocumentFrame>
  );
}

export function buildPdfDocumentElement(content: CanvasContent, descriptor: ExportDescriptor) {
  return <PdfDocument content={content} descriptor={descriptor} />;
}
