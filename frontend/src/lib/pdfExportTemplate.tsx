import type { ReactNode } from 'react';
import {
  buildConfidenceExportViewModel,
  buildFetchExportViewModel,
  isConfidenceCanvasReport,
} from '@/adapters/exportArtifacts';
import { buildReportViewModel } from '@/adapters/reportV2';
import type {
  CanvasContent,
  ConfidenceQuadrant,
  ReportCanvasContent,
  ReportV2Metric,
} from '@/types/canvas';
import {
  buildCanvasContentTextFromDescriptor,
  type ExportDescriptor,
} from '@/lib/canvasExportShared';

type MatrixPoint = {
  itemId: string;
  label: string;
  entityLabel: string;
  entityClass: string;
  quadrantLabel: string;
  score: number;
  frequency: number;
  x: number;
  y: number;
};

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

function formatPercent(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function formatScore(value?: number) {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  return value.toFixed(1);
}

function formatMetricValue(metric: ReportV2Metric) {
  if (metric.value === undefined || metric.value === null || metric.value === '') {
    return '--';
  }
  if (metric.unit === 'ratio' && typeof metric.value === 'number') {
    return `${(metric.value <= 1 ? metric.value * 100 : metric.value).toFixed(1)}%`;
  }
  return `${metric.value}${metric.unit && metric.unit !== 'ratio' ? metric.unit : ''}`;
}

function formatAssessmentClass(status?: string) {
  if (status === 'good') return 'tag tag-good';
  if (status === 'warning') return 'tag tag-warn';
  if (status === 'risk') return 'tag tag-risk';
  return 'tag';
}

function extractHostname(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\\./, '');
  } catch {
    return url;
  }
}

function getEntityMeta(entity?: string) {
  if (entity === 'brand') return { label: '我方阵营', color: '#1d4ed8' };
  if (entity === 'competitor') return { label: '竞方阵营', color: '#e11d48' };
  return { label: '共业阵营', color: '#64748b' };
}

function getQuadrantMeta(quadrant?: ConfidenceQuadrant) {
  switch (quadrant) {
    case 'q1_anchor':
      return { className: 'quad-card quad-q1', label: '定海神针' };
    case 'q2_false_prosperity':
      return { className: 'quad-card quad-q2', label: '虚假繁荣' };
    case 'q4_sleeping_asset':
      return { className: 'quad-card quad-q4', label: '高潜伏藏' };
    default:
      return { className: 'quad-card quad-q3', label: '沉寂噪音' };
  }
}

function getConfidenceItems(content: ReportCanvasContent) {
  return buildConfidenceExportViewModel(content).items;
}

function buildMatrixPoints(content: ReportCanvasContent): MatrixPoint[] {
  const items = getConfidenceItems(content)
    .filter((item) => typeof item.aice_score === 'number' && typeof item.frequency === 'number');

  const confidenceView = buildConfidenceExportViewModel(content);
  const thresholdFrequency = confidenceView.matrixConfig?.frequency_threshold ?? 3;
  const maxFrequency = Math.max(thresholdFrequency + 1, ...items.map((item) => item.frequency || 0), 4);
  const chart = { width: 440, height: 300, left: 48, top: 16, right: 16, bottom: 34 };
  const innerWidth = chart.width - chart.left - chart.right;
  const innerHeight = chart.height - chart.top - chart.bottom;

  return items.map((item) => {
    const entityMeta = getEntityMeta(item.entity_classification);
    const score = item.aice_score || 0;
    const frequency = item.frequency || 0;
    const x = chart.left + (score / 100) * innerWidth;
    const y = chart.height - chart.bottom - (frequency / maxFrequency) * innerHeight;
    return {
      itemId: item.item_id,
      label: item.label,
      entityLabel: item.entity_label || entityMeta.label,
      entityClass: entityMeta.color,
      quadrantLabel: item.quadrant_label || getQuadrantMeta(item.quadrant).label,
      score,
      frequency,
      x,
      y,
    };
  });
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
        subtitle="主报告负责阅读体验，附录保留完整文本内容，避免关键模块在导出中缺失。"
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

function ReportPdfDocument({ content, descriptor }: { content: ReportCanvasContent; descriptor: ExportDescriptor }) {
  const view = buildReportViewModel(content);
  const platforms = content.data.platform_scope && content.data.platform_scope.length > 0
    ? [`平台：${content.data.platform_scope.join(' / ')}`]
    : [];

  return (
    <DocumentFrame
      descriptor={descriptor}
      title={view.headline || descriptor.title || descriptor.deliverableName}
      subtitle={view.subtitle || content.data.content}
      extraMeta={platforms}
    >
      {view.summary.metrics && view.summary.metrics.length > 0 ? (
        <Section title="核心指标" subtitle="先看这份交付物最重要的判断指标">
          <div className="grid grid-3">
            {view.summary.metrics.map((metric) => (
              <div key={metric.id} className="metric-card">
                <div className="metric-label">{metric.label}</div>
                <div className="metric-value">{formatMetricValue(metric)}</div>
                {metric.status ? <div style={{ marginTop: 8 }}><span className={formatAssessmentClass(metric.status)}>{metric.assessment || metric.status}</span></div> : null}
                {metric.description ? <div className="metric-note">{metric.description}</div> : null}
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      {(view.summary.status_summary || view.summary.highlights?.length) ? (
        <Section title="执行摘要" subtitle="把当前结果压缩成可快速传阅的结论">
          <div className="grid grid-2">
            {view.summary.status_summary ? (
              <div className="info-card">
                <div className="metric-label">状态总结</div>
                <div className="prose" style={{ marginTop: 8 }}>{view.summary.status_summary}</div>
              </div>
            ) : null}
            {view.summary.highlights && view.summary.highlights.length > 0 ? (
              <div className="info-card">
                <div className="metric-label">重点高亮</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {view.summary.highlights.map((item) => (
                    <div key={item} className="list-item">
                      <div className="list-body" style={{ marginTop: 0 }}>{item}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>
      ) : null}

      {view.scenarioCoverage.items && view.scenarioCoverage.items.length > 0 ? (
        <Section title={view.scenarioCoverage.title || '用户场景覆盖'} subtitle={view.scenarioCoverage.summary}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '24%' }}>场景</th>
                <th style={{ width: '14%' }}>优先级</th>
                <th style={{ width: '22%' }}>平台</th>
                <th>结论</th>
              </tr>
            </thead>
            <tbody>
              {view.scenarioCoverage.items.map((item, index) => (
                <tr key={`${item.scenario_label}-${index}`}>
                  <td>{item.scenario_label}</td>
                  <td>{item.scenario_priority || '--'}</td>
                  <td>{item.present_platforms?.join('、') || '--'}</td>
                  <td>{item.evidence || item.battle_status || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {view.competitorBattle.items && view.competitorBattle.items.length > 0 ? (
        <Section title={view.competitorBattle.title || '竞品争夺'} subtitle={view.competitorBattle.overview}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '24%' }}>争夺场景</th>
                <th style={{ width: '24%' }}>竞品</th>
                <th style={{ width: '16%' }}>态势</th>
                <th>建议</th>
              </tr>
            </thead>
            <tbody>
              {view.competitorBattle.items.map((item, index) => (
                <tr key={`${item.scenario_label}-${index}`}>
                  <td>{item.scenario_label}</td>
                  <td>{item.competitors_present?.join('、') || '--'}</td>
                  <td>{item.battle_status || '--'}</td>
                  <td>{joinInline([item.evidence, item.recommended_focus]) || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {(view.mentions.brand_mentions?.length || view.mentions.competitor_mentions?.length) ? (
        <Section title="提及与引用样本" subtitle="记录品牌和竞品在问答中的真实进入方式">
          <div className="grid grid-2">
            {view.mentions.brand_mentions && view.mentions.brand_mentions.length > 0 ? (
              <div className="tone-card">
                <div className="metric-label">品牌提及</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {view.mentions.brand_mentions.map((item, index) => (
                    <div key={`${item.scenario_label}-${index}`} className="list-item">
                      <div className="list-title">{item.scenario_label}</div>
                      <div className="list-meta">{joinInline([item.platform, item.sentiment, item.official_citation_present ? '官网引用' : undefined])}</div>
                      {item.evidence ? <div className="list-body">{item.evidence}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {view.mentions.competitor_mentions && view.mentions.competitor_mentions.length > 0 ? (
              <div className="tone-card">
                <div className="metric-label">竞品提及</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {view.mentions.competitor_mentions.map((item, index) => (
                    <div key={`${item.scenario_label}-${index}`} className="list-item">
                      <div className="list-title">{item.scenario_label}</div>
                      <div className="list-meta">{joinInline([item.competitor, item.platform, item.sentiment])}</div>
                      {item.evidence ? <div className="list-body">{item.evidence}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>
      ) : null}

      {view.sources.citation_analysis?.top_domains && view.sources.citation_analysis.top_domains.length > 0 ? (
        <Section
          title={view.sources.title || '信息源分析'}
          subtitle={joinInline([view.sources.summary, `官网引用率 ${formatPercent(view.sources.official_citation_rate)}`])}
        >
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '28%' }}>来源域名</th>
                <th style={{ width: '14%' }}>引用次数</th>
                <th style={{ width: '14%' }}>官方性</th>
                <th>代表样本</th>
              </tr>
            </thead>
            <tbody>
              {view.sources.citation_analysis.top_domains.map((domain) => (
                <tr key={domain.domain}>
                  <td>{domain.domain}</td>
                  <td>{domain.count}</td>
                  <td>{domain.is_official ? '官网' : '第三方'}</td>
                  <td>{domain.sample_titles?.slice(0, 3).join('；') || '--'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      ) : null}

      {(view.insights.strengths?.length || view.insights.weaknesses?.length) ? (
        <Section title={view.insights.title || '当前优势与补强'} subtitle={view.insights.summary}>
          <div className="grid grid-2">
            {view.insights.strengths && view.insights.strengths.length > 0 ? (
              <div className="quote-card">
                <div className="metric-label">优势洞察</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {view.insights.strengths.map((item) => (
                    <div key={item.title} className="list-item">
                      <div className="list-title">{item.title}</div>
                      <div className="list-meta">{item.scenario || '--'}</div>
                      {item.evidence ? <div className="list-body">{item.evidence}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {view.insights.weaknesses && view.insights.weaknesses.length > 0 ? (
              <div className="quote-card">
                <div className="metric-label">待补强</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {view.insights.weaknesses.map((item) => (
                    <div key={item.title} className="list-item">
                      <div className="list-title">{item.title}</div>
                      <div className="list-meta">{item.scenario || '--'}</div>
                      {item.evidence ? <div className="list-body">{item.evidence}</div> : null}
                      {item.improvement_hint ? <div className="list-body muted">{item.improvement_hint}</div> : null}
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>
      ) : null}

      {view.actionQueue.items && view.actionQueue.items.length > 0 ? (
        <Section title={view.actionQueue.title || '下一步优化'} subtitle={view.actionQueue.summary}>
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '12%' }}>优先级</th>
                <th style={{ width: '24%' }}>动作</th>
                <th style={{ width: '24%' }}>目标</th>
                <th>影响 / 周期</th>
              </tr>
            </thead>
            <tbody>
              {view.actionQueue.items.map((item, index) => (
                <tr key={`${item.title || item.action}-${index}`}>
                  <td>{item.priority || '--'}</td>
                  <td>{item.title || item.action || '--'}</td>
                  <td>{item.target || item.scenario_label || '--'}</td>
                  <td>{joinInline([item.expected_impact, item.timeline, item.difficulty]) || '--'}</td>
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
                <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}>
                  <div className="platform-name">{result.platform_name || result.platform}</div>
                  <span className={result.success ? 'tag tag-good' : 'tag tag-risk'}>
                    {result.success ? '成功' : '失败'}
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
                {result.success ? (
                  <div className="answer">{result.answer?.content || '无答案内容'}</div>
                ) : (
                  <div className="answer">{result.error || '抓取失败'}</div>
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
              </div>
            ))}
          </div>
        </Section>
      ))}

      <AppendixSection content={content} descriptor={descriptor} />
    </DocumentFrame>
  );
}

function ConfidenceMatrix({ content }: { content: ReportCanvasContent }) {
  const confidenceView = buildConfidenceExportViewModel(content);
  const points = buildMatrixPoints(content);
  const thresholdScore = confidenceView.matrixConfig?.aice_threshold ?? 70;
  const thresholdFrequency = confidenceView.matrixConfig?.frequency_threshold ?? 3;
  const matrixTitle = confidenceView.ecosystemMatrix?.title || '置信度象限矩阵';
  const maxFrequency = Math.max(thresholdFrequency + 1, ...points.map((item) => item.frequency), 4);
  const chart = { width: 440, height: 300, left: 48, top: 16, right: 16, bottom: 34 };
  const innerWidth = chart.width - chart.left - chart.right;
  const innerHeight = chart.height - chart.top - chart.bottom;
  const thresholdX = chart.left + (thresholdScore / 100) * innerWidth;
  const thresholdY = chart.height - chart.bottom - (thresholdFrequency / maxFrequency) * innerHeight;

  return (
    <div className="matrix-wrap">
      <div className="info-card">
        <div className="metric-label">{matrixTitle}</div>
        <svg width="100%" viewBox={`0 0 ${chart.width} ${chart.height}`} aria-label={matrixTitle} style={{ marginTop: 10 }}>
          <rect x={chart.left} y={chart.top} width={thresholdX - chart.left} height={thresholdY - chart.top} fill="#e9eef3" />
          <rect x={thresholdX} y={chart.top} width={chart.width - chart.right - thresholdX} height={thresholdY - chart.top} fill="#dff4eb" />
          <rect x={chart.left} y={thresholdY} width={thresholdX - chart.left} height={chart.height - chart.bottom - thresholdY} fill="#fdf0cf" />
          <rect x={thresholdX} y={thresholdY} width={chart.width - chart.right - thresholdX} height={chart.height - chart.bottom - thresholdY} fill="#dff1fb" />
          <line x1={chart.left} y1={chart.height - chart.bottom} x2={chart.width - chart.right} y2={chart.height - chart.bottom} stroke="#8fa0b8" strokeWidth="1.3" />
          <line x1={chart.left} y1={chart.top} x2={chart.left} y2={chart.height - chart.bottom} stroke="#8fa0b8" strokeWidth="1.3" />
          <line x1={thresholdX} y1={chart.top} x2={thresholdX} y2={chart.height - chart.bottom} stroke="#64748b" strokeDasharray="5 4" strokeWidth="1.1" />
          <line x1={chart.left} y1={thresholdY} x2={chart.width - chart.right} y2={thresholdY} stroke="#64748b" strokeDasharray="5 4" strokeWidth="1.1" />
          <text x={chart.width / 2} y={chart.height - 6} textAnchor="middle" fontSize="11" fill="#5f6b85">AICE 分数</text>
          <text x="14" y={chart.height / 2} textAnchor="middle" fontSize="11" fill="#5f6b85" transform={`rotate(-90 14 ${chart.height / 2})`}>出现频次</text>
          <text x={chart.left + 10} y={chart.top + 16} fontSize="11" fill="#5f6b85">Q3 沉寂噪音</text>
          <text x={thresholdX + 10} y={chart.top + 16} fontSize="11" fill="#2f5d52">Q1 定海神针</text>
          <text x={chart.left + 10} y={thresholdY + 18} fontSize="11" fill="#8a631a">Q2 虚假繁荣</text>
          <text x={thresholdX + 10} y={thresholdY + 18} fontSize="11" fill="#24628c">Q4 高潜伏藏</text>
          {points.map((point) => (
            <g key={point.itemId}>
              <circle cx={point.x} cy={point.y} r="5" fill={point.entityClass} fillOpacity="0.92" />
              <title>{`${point.label} | ${point.entityLabel} | ${point.quadrantLabel} | AICE ${point.score.toFixed(1)} | 频次 ${point.frequency}`}</title>
            </g>
          ))}
        </svg>
      </div>
      <div className="legend">
        <div className="info-card">
          <div className="metric-label">图例</div>
          <div style={{ marginTop: 10 }} className="legend">
            {[
              { label: '我方阵营', color: '#1d4ed8' },
              { label: '竞方阵营', color: '#e11d48' },
              { label: '共业阵营', color: '#64748b' },
            ].map((item) => (
              <div key={item.label} className="legend-item">
                <span className="swatch" style={{ background: item.color }} />
                <span>{item.label}</span>
              </div>
            ))}
          </div>
          <div className="small-list">
            <div className="small-item">AICE 阈值：{formatScore(thresholdScore)}</div>
            <div className="small-item">频次阈值：{thresholdFrequency}</div>
            <div className="small-item">评估点位：{points.length}</div>
          </div>
        </div>
      </div>
    </div>
  );
}

function ConfidencePdfDocument({ content, descriptor }: { content: ReportCanvasContent; descriptor: ExportDescriptor }) {
  const view = buildConfidenceExportViewModel(content);
  const summary = view.summary;
  const findings = view.findings;
  const quadrantOverview = view.quadrantOverview;
  const blocks = view.analysisBlocks;
  const repairActions = view.repairActions;
  const generalKnowledge = view.generalKnowledgeInsight;
  const items = view.items;

  return (
    <DocumentFrame
      descriptor={descriptor}
      title={view.title || descriptor.deliverableName}
      subtitle={view.subtitle || view.diagnosis}
      extraMeta={[`样本数：${summary?.evaluated_count ?? items.length}`, `平均 AICE：${formatScore(summary?.average_score)}`]}
    >
      {summary ? (
        <Section title="核心指标" subtitle="先看阵营分布与整体风险态势">
          <div className="grid grid-3">
            {[
              { label: '总引用来源', value: String(summary.evaluated_count ?? 0) },
              { label: '我方阵营', value: String(summary.brand_count ?? 0) },
              { label: '竞方阵营', value: String(summary.competitor_count ?? 0) },
              { label: '共业阵营', value: String(summary.general_knowledge_count ?? 0) },
              { label: '第二象限', value: String(summary.second_quadrant_count ?? 0) },
              { label: '平均 AICE', value: formatScore(summary.average_score) },
            ].map((metric) => (
              <div key={metric.label} className="metric-card">
                <div className="metric-label">{metric.label}</div>
                <div className="metric-value">{metric.value}</div>
              </div>
            ))}
          </div>
        </Section>
      ) : null}

      <Section title="象限矩阵" subtitle="用专用打印图把高频 / 高分关系固定下来">
        <ConfidenceMatrix content={content} />
      </Section>

      {quadrantOverview.length > 0 ? (
        <Section title="象限概览" subtitle="每个象限代表不同的修复优先级">
          <div className="grid grid-2">
            {quadrantOverview.map((item) => {
              const meta = getQuadrantMeta(item.quadrant);
              return (
                <div key={item.quadrant} className={meta.className}>
                  <div className="list-title">{item.quadrant_label || meta.label}</div>
                  <div className="list-meta">{joinInline([`数量 ${item.count ?? 0}`, item.strategy])}</div>
                  {item.description ? <div className="list-body">{item.description}</div> : null}
                </div>
              );
            })}
          </div>
        </Section>
      ) : null}

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

      {blocks.map((block) => (
        block.items && block.items.length > 0 ? (
          <Section key={block.key} title={block.title || block.key} subtitle={block.description}>
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: '26%' }}>样本</th>
                  <th style={{ width: '16%' }}>阵营</th>
                  <th style={{ width: '16%' }}>象限</th>
                  <th style={{ width: '10%' }}>频次</th>
                  <th style={{ width: '10%' }}>AICE</th>
                  <th>主要原因 / 动作</th>
                </tr>
              </thead>
              <tbody>
                {block.items.map((item) => (
                  <tr key={item.item_id}>
                    <td>{item.label}</td>
                    <td>{item.entity_label || getEntityMeta(item.entity_classification).label}</td>
                    <td>{item.quadrant_label || getQuadrantMeta(item.quadrant).label}</td>
                    <td>{item.frequency ?? '--'}</td>
                    <td>{formatScore(item.aice_score)}</td>
                    <td>{joinInline([item.primary_reasons?.slice(0, 2).join('；'), item.repair_action], ' ｜ ') || '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </Section>
        ) : null
      ))}

      {(generalKnowledge?.summary || generalKnowledge?.top_frequency_items?.length || generalKnowledge?.top_score_items?.length) ? (
        <Section title="共业阵营观察" subtitle={generalKnowledge?.summary}>
          <div className="grid grid-2">
            {generalKnowledge?.top_frequency_items && generalKnowledge.top_frequency_items.length > 0 ? (
              <div className="info-card">
                <div className="metric-label">高频来源</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {generalKnowledge.top_frequency_items.map((item) => (
                    <div key={item.item_id} className="list-item">
                      <div className="list-title">{item.label}</div>
                      <div className="list-meta">{joinInline([`频次 ${item.frequency ?? '--'}`, `AICE ${formatScore(item.aice_score)}`])}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
            {generalKnowledge?.top_score_items && generalKnowledge.top_score_items.length > 0 ? (
              <div className="info-card">
                <div className="metric-label">高分来源</div>
                <div className="list" style={{ marginTop: 8 }}>
                  {generalKnowledge.top_score_items.map((item) => (
                    <div key={item.item_id} className="list-item">
                      <div className="list-title">{item.label}</div>
                      <div className="list-meta">{joinInline([`频次 ${item.frequency ?? '--'}`, `AICE ${formatScore(item.aice_score)}`])}</div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </Section>
      ) : null}

      {repairActions.length > 0 ? (
        <Section title="修我行动清单" subtitle="把高风险来源对应到明确动作">
          <table className="table">
            <thead>
              <tr>
                <th style={{ width: '14%' }}>优先级</th>
                <th style={{ width: '28%' }}>动作</th>
                <th>说明</th>
                <th style={{ width: '14%' }}>样本数</th>
              </tr>
            </thead>
            <tbody>
              {repairActions.map((item, index) => (
                <tr key={`${item.title}-${index}`}>
                  <td>{item.priority || '--'}</td>
                  <td>{item.title || '--'}</td>
                  <td>{item.summary || '--'}</td>
                  <td>{item.count ?? '--'}</td>
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
