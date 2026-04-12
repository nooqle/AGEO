import type {
  CanvasContent,
  FetchCitation,
  FetchPlatformResult,
  ReportCanvasContent,
  ReportMentionItem,
  ReportV2Metric,
} from '@/types/canvas';
import { buildReportViewModel } from '@/adapters/reportV2';
import {
  buildConfidenceExportViewModel,
  buildFetchExportViewModel,
  isConfidenceCanvasReport,
} from '@/adapters/exportArtifacts';

export type SupportedExportFormat = 'pdf' | 'md' | 'csv';

export type SupportedDeliverable =
  | 'AI答案抓取'
  | '基线全景分析'
  | '用户场景细分分析'
  | '置信度报告'
  | '历史知识导出';

export type ExportDescriptor = {
  brandName: string;
  deliverableName: SupportedDeliverable;
  timestamp: string;
  version: number;
  title: string;
};

export function resolveActiveContent(content: CanvasContent): CanvasContent {
  const versionIndex = content.currentVersionIndex;
  const versions = content.versions || [];

  if (versionIndex >= 0 && versionIndex < versions.length) {
    return {
      ...content,
      data: versions[versionIndex].data as CanvasContent['data'],
    } as CanvasContent;
  }

  return content;
}

function getVersionNumber(content: CanvasContent): number {
  const versions = content.versions || [];
  if (content.currentVersionIndex >= 0 && content.currentVersionIndex < versions.length) {
    return versions[content.currentVersionIndex]?.versionNumber || 1;
  }
  return versions.length + 1;
}

function getVersionTimestamp(content: CanvasContent): Date {
  const versions = content.versions || [];
  if (content.currentVersionIndex >= 0 && content.currentVersionIndex < versions.length) {
    const timestamp = versions[content.currentVersionIndex]?.timestamp;
    if (timestamp) {
      const parsed = new Date(timestamp);
      if (!Number.isNaN(parsed.getTime())) {
        return parsed;
      }
    }
  }

  const parsed = new Date(content.createdAt);
  return Number.isNaN(parsed.getTime()) ? new Date() : parsed;
}

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

function formatTimestampForFilename(date: Date): string {
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
  ].join('') + '-' + [pad(date.getHours()), pad(date.getMinutes()), pad(date.getSeconds())].join('');
}

export function sanitizeFilenamePart(value: string): string {
  return value
    .trim()
    .replace(/[\\/:*?"<>|]+/g, '-')
    .replace(/\s+/g, '')
    .replace(/\.+$/g, '') || 'brand';
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0;
}

function uniqueStrings(values: Array<string | undefined | null>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const value of values) {
    if (!isNonEmptyString(value)) {
      continue;
    }
    const normalized = value.trim();
    if (seen.has(normalized)) {
      continue;
    }
    seen.add(normalized);
    result.push(normalized);
  }

  return result;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function toNumberValue(value: unknown): number | undefined {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string') {
    const normalized = value.replace('%', '').replace(/,/g, '').trim();
    if (!normalized) {
      return undefined;
    }
    const parsed = Number(normalized);
    return Number.isFinite(parsed) ? parsed : undefined;
  }
  if (isRecord(value) && 'value' in value) {
    return toNumberValue(value.value);
  }
  return undefined;
}

function readNumber(record: Record<string, unknown>, key: string): number | undefined {
  return toNumberValue(record[key]);
}

function formatMetricValue(metric: ReportV2Metric): string {
  if (metric.value === undefined || metric.value === null || metric.value === '') {
    return '--';
  }
  const value = metric.value;
  if (metric.unit === 'ratio' && typeof value === 'number') {
    return `${(value <= 1 ? value * 100 : value).toFixed(1)}%`;
  }
  return `${value}${metric.unit && metric.unit !== 'ratio' ? metric.unit : ''}`;
}

function formatPercent(value?: number): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--';
  }
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
}

function formatScore(value?: number): string {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return '--';
  }
  return value.toFixed(1);
}

function joinInline(values: Array<string | undefined | null>, separator = ' | '): string | null {
  const normalized = values
    .filter((value): value is string => Boolean(value && value.trim()))
    .map((value) => value.trim());
  return normalized.length > 0 ? normalized.join(separator) : null;
}

function inferBrandFromHeadline(headline?: string): string | null {
  if (!isNonEmptyString(headline)) {
    return null;
  }

  const normalized = headline.trim();
  const keywordIndex = ['基线全景分析报告', 'AI 可见性分析报告', '置信度报告', '分析报告']
    .map((keyword) => normalized.indexOf(keyword))
    .find((index) => typeof index === 'number' && index > 0);

  if (typeof keywordIndex === 'number' && keywordIndex > 0) {
    const candidate = normalized.slice(0, keywordIndex).trim();
    const cleaned = candidate
      .replace(/AI\s*可见性?$/i, '')
      .replace(/AI\s*可见度$/i, '')
      .replace(/品牌可见性?$/i, '')
      .replace(/品牌可见度$/i, '')
      .replace(/可见性?$/i, '')
      .replace(/可见度$/i, '')
      .trim();
    return cleaned || candidate || null;
  }

  return null;
}

export function getDeliverableName(content: CanvasContent): SupportedDeliverable | null {
  if (content.type === 'fetchResults') {
    return 'AI答案抓取';
  }

  if (content.type === 'dataTable') {
    return '历史知识导出';
  }

  if (content.type !== 'report') {
    return null;
  }

  if (isConfidenceCanvasReport(content)) {
    return '置信度报告';
  }

  if (content.category === 'baseline') {
    return '基线全景分析';
  }

  return '用户场景细分分析';
}

export function inferBrandName(content: CanvasContent, allContents: CanvasContent[]): string {
  const active = resolveActiveContent(content);

  if (active.type === 'dataTable' && isNonEmptyString(active.data.brand_name)) {
    return active.data.brand_name.trim();
  }

  if (active.type === 'report' && isNonEmptyString(active.data.brand_name)) {
    return active.data.brand_name.trim();
  }

  if (active.type === 'report') {
    const fromHeadline = inferBrandFromHeadline(active.data.headline);
    if (fromHeadline) {
      return fromHeadline;
    }
  }

  for (const candidate of allContents) {
    const resolved = resolveActiveContent(candidate);
    if (resolved.type === 'report' && isNonEmptyString(resolved.data.brand_name)) {
      return resolved.data.brand_name.trim();
    }
    if (resolved.type === 'report') {
      const fromHeadline = inferBrandFromHeadline(resolved.data.headline);
      if (fromHeadline) {
        return fromHeadline;
      }
    }
  }

  return 'brand';
}

function stringifyTableCell(value: unknown): string {
  if (value === null || value === undefined) {
    return '';
  }
  if (Array.isArray(value)) {
    return value.map((item) => stringifyTableCell(item)).join('、');
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

function escapeCsvCell(value: string): string {
  const normalized = value.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  const shouldQuote = /[",\n]/.test(normalized);
  const escaped = normalized.replace(/"/g, '""');
  return shouldQuote ? `"${escaped}"` : escaped;
}

function buildDataTableMarkdown(
  content: Extract<CanvasContent, { type: 'dataTable' }>,
  descriptor: ExportDescriptor
): string {
  const columns = content.data.columns || [];
  const rows = content.data.rows || [];
  const lines: string[] = [
    `# ${content.data.export_title || descriptor.title || descriptor.deliverableName}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  if (content.data.analysis_period) {
    lines.push(`- 范围：${content.data.analysis_period}`, '');
  }

  if (content.data.truncated) {
    lines.push(
      `- 说明：当前仅导出前 ${content.data.export_limit || rows.length} 条记录，请缩小筛选范围以获取完整结果。`,
      ''
    );
  }

  if (content.data.description) {
    lines.push(content.data.description, '');
  }

  if (columns.length === 0) {
    lines.push('暂无可导出的表格列。');
    return lines.join('\n');
  }

  lines.push(
    `| ${columns.map((column) => column.label || column.key).join(' | ')} |`,
    `| ${columns.map(() => '---').join(' | ')} |`
  );
  for (const row of rows) {
    lines.push(
      `| ${columns
        .map((column) => stringifyTableCell(row[column.key]).replace(/\|/g, '\\|'))
        .join(' | ')} |`
    );
  }
  lines.push('');
  return lines.join('\n');
}

export function buildDataTableCsv(
  content: Extract<CanvasContent, { type: 'dataTable' }>
): string {
  const columns = content.data.columns || [];
  const rows = content.data.rows || [];

  if (columns.length === 0) {
    return '';
  }

  const header = columns.map((column) => escapeCsvCell(column.label || column.key));
  const lines = [header.join(',')];

  for (const row of rows) {
    lines.push(
      columns
        .map((column) => escapeCsvCell(stringifyTableCell(row[column.key])))
        .join(',')
    );
  }

  return lines.join('\n');
}

export function buildExportDescriptor(content: CanvasContent, allContents: CanvasContent[]): ExportDescriptor | null {
  const active = resolveActiveContent(content);
  const deliverableName = getDeliverableName(active);
  if (!deliverableName) {
    return null;
  }

  const timestamp = getVersionTimestamp(content);
  const brandName = inferBrandName(content, allContents);

  return {
    brandName,
    deliverableName,
    timestamp: formatTimestampForFilename(timestamp),
    version: getVersionNumber(content),
    title:
      active.type === 'report'
        ? active.data.headline || active.title
        : active.title,
  };
}

export function buildExportFileName(descriptor: ExportDescriptor, format: SupportedExportFormat): string {
  return [
    sanitizeFilenamePart(descriptor.brandName),
    sanitizeFilenamePart(descriptor.deliverableName),
    descriptor.timestamp,
    `v${descriptor.version}`,
  ].join('_') + `.${format}`;
}

function createMetadataLines(descriptor: ExportDescriptor): string[] {
  return [
    `- 品牌：${descriptor.brandName}`,
    `- 交付物：${descriptor.deliverableName}`,
    `- 版本：v${descriptor.version}`,
    `- 时间：${descriptor.timestamp}`,
  ];
}

function pushSection(lines: string[], title: string, body?: string | null) {
  if (!body || !body.trim()) {
    return;
  }
  lines.push(`## ${title}`, body.trim(), '');
}

function pushBulletSection(lines: string[], title: string, items: Array<string | null | undefined>) {
  const normalized = items
    .filter((item): item is string => Boolean(item && item.trim()))
    .map((item) => item.trim());

  if (normalized.length === 0) {
    return;
  }

  lines.push(`## ${title}`);
  for (const item of normalized) {
    lines.push(`- ${item}`);
  }
  lines.push('');
}

function buildMentionLine(item: ReportMentionItem): string {
  const meta = joinInline([
    item.platform ? `平台：${item.platform}` : null,
    item.sentiment ? `情绪：${item.sentiment}` : null,
    item.official_citation_present === true ? '官网引用：是' : item.official_citation_present === false ? '官网引用：否' : null,
    item.competitor ? `竞品：${item.competitor}` : null,
  ]);

  const details = joinInline([
    item.evidence,
    item.citation_domains && item.citation_domains.length > 0 ? `来源：${item.citation_domains.join('、')}` : null,
  ], '；');

  return joinInline([item.scenario_label, meta, details], ' ｜ ') || item.scenario_label;
}

function shortenScenarioLabel(value: string | undefined, limit = 42): string | undefined {
  if (!isNonEmptyString(value)) {
    return undefined;
  }
  const trimmed = value.trim();
  return trimmed.length > limit ? `${trimmed.slice(0, limit).trim()}...` : trimmed;
}

const REPORT_PLATFORM_ORDER = ['doubao', 'yuanbao', 'kimi', 'deepseek', 'hunyuan'];

function getReportPlatformLabel(platform: string): string {
  const normalized = platform.trim().toLowerCase();
  if (normalized === 'doubao') return '豆包';
  if (normalized === 'yuanbao') return '元宝';
  if (normalized === 'kimi') return 'Kimi';
  if (normalized === 'deepseek') return 'DeepSeek';
  if (normalized === 'hunyuan') return '元宝';
  return platform;
}

function getSourceSiteName(domain: string | undefined): string | undefined {
  const normalized = toStringValue(domain)?.toLowerCase();
  if (!normalized) {
    return undefined;
  }

  const mapping: Record<string, string> = {
    'mp.weixin.qq.com': '微信公众号',
    'baijiahao.baidu.com': '百家号',
    'baike.baidu.com': '百度百科',
    'finance.sina.com.cn': '新浪财经',
    'finance.ifeng.com': '凤凰财经',
    'xueqiu.com': '雪球',
    '36kr.com': '36氪',
    'zhihu.com': '知乎',
    'm.chinairn.com': '中研网',
    'bkso.baidu.com': '百度知识搜索',
    'iesdouyin.com': '抖音',
    'toutiao.com': '今日头条',
    'sohu.com': '搜狐',
    'sohu.com.cn': '搜狐',
    'qq.com': '腾讯',
    '163.com': '网易',
  };

  return mapping[normalized] ?? normalized;
}

function getPlatformPreference(platform: string): string {
  const normalized = platform.trim().toLowerCase();
  if (normalized === 'deepseek') return '更偏向技术内容、深度长文和结构完整的资料页。';
  if (normalized === 'kimi') return '更偏向长文解析、媒体报道和信息组织较完整的页面。';
  if (normalized === 'doubao') return '更偏向资讯流、泛生活内容和短内容聚合来源。';
  if (normalized === 'hunyuan' || normalized === 'yuanbao') return '更偏向中文综合内容、社区讨论和微信生态来源。';
  return '更偏向高频可访问的中文综合内容。';
}

function readUnknownRecord(value: unknown): Record<string, unknown> | undefined {
  return isRecord(value) ? value : undefined;
}

function collectReportPlatforms(
  platformBreakdown: Record<string, unknown> | undefined,
  sourceOverview: Record<string, unknown> | undefined,
  mentions: ReportMentionItem[]
): string[] {
  const candidates = uniqueStrings([
    ...(platformBreakdown ? Object.keys(platformBreakdown) : []),
    ...(isRecord(sourceOverview?.platform_citation_stats)
      ? Object.keys(sourceOverview.platform_citation_stats)
      : []),
    ...mentions.map((item) => item.platform),
  ]).map((item) => item.toLowerCase());

  const known = REPORT_PLATFORM_ORDER.filter((item) => candidates.includes(item));
  const others = candidates
    .filter((item) => !known.includes(item))
    .sort((a, b) => a.localeCompare(b));

  return [...known, ...others];
}

function buildSourceDistributionTable(
  sourceOverview: Record<string, unknown> | undefined,
  factRows?: Array<Record<string, unknown>>
): string[] {
  const rows = [
    '| 网站名 | 域名 | 引用次数 | 占比 |',
    '| --- | --- | ---: | ---: |',
  ];

  if (factRows && factRows.length > 0) {
    for (const item of factRows.slice(0, 15)) {
      const domain = toStringValue(item.domain);
      if (!domain) {
        continue;
      }
      const siteName = toStringValue(item.site_name) || getSourceSiteName(domain) || '未知来源';
      const count = toNumberValue(item.count);
      const share = toStringValue(item.share) || formatPercent(toNumberValue(item.share));
      rows.push(`| ${siteName} | ${domain} | ${count ?? '--'} | ${share || '--'} |`);
    }
    return rows;
  }

  const topDomains = Array.isArray(sourceOverview?.top_domains) ? sourceOverview.top_domains.filter(isRecord) : [];

  for (const item of topDomains.slice(0, 15)) {
    const domain = toStringValue(item.domain);
    if (!domain) {
      continue;
    }
    const siteName = getSourceSiteName(domain) || domain;
    const count = toNumberValue(item.count);
    const share = formatPercent(toNumberValue(item.share));
    rows.push(`| ${siteName} | ${domain} | ${count ?? '--'} | ${share} |`);
  }

  return rows;
}

function buildCustomerReportMarkdown(content: ReportCanvasContent): string {
  const explicitMarkdown =
    typeof content.data.report_markdown === 'string' && content.data.report_markdown.trim()
      ? content.data.report_markdown.trim()
      : '';

  // Backend is the only authority for A5 report content. Frontend falls back only
  // for legacy artifacts that do not contain report_markdown at all.
  if (explicitMarkdown) {
    return explicitMarkdown;
  }

  const dataRecord = content.data as Record<string, unknown>;
  const reportDataRecord = readUnknownRecord(dataRecord.report_data);
  const aeoFacts = readUnknownRecord(reportDataRecord?.aeo_report_facts);
  const view = buildReportViewModel(content);
  const summaryMetrics = readUnknownRecord(content.data.summary_metrics);
  const sourceOverview = readUnknownRecord(content.data.source_overview);
  const reportRecord = dataRecord;
  const platformBreakdown =
    readUnknownRecord(content.data.platform_breakdown) ||
    readUnknownRecord(readUnknownRecord(content.data.metrics_raw)?.platform_breakdown) ||
    readUnknownRecord(readUnknownRecord(content.data.report_data)?.platform_breakdown);
  const brandName =
    (isNonEmptyString(content.data.brand_name) ? content.data.brand_name.trim() : null) ||
    inferBrandFromHeadline(content.data.headline) ||
    toStringValue(aeoFacts?.brand_name) ||
    '品牌';
  const factMetricRows = Array.isArray(aeoFacts?.metric_rows) ? aeoFacts.metric_rows.filter(isRecord) : [];
  const factPlatformRows = Array.isArray(aeoFacts?.platform_rows) ? aeoFacts.platform_rows.filter(isRecord) : [];
  const factMissingExamples = Array.isArray(aeoFacts?.missing_examples) ? aeoFacts.missing_examples.filter(isRecord) : [];
  const factContestedExamples = Array.isArray(aeoFacts?.contested_examples) ? aeoFacts.contested_examples.filter(isRecord) : [];
  const factSourceRows = Array.isArray(aeoFacts?.source_rows) ? aeoFacts.source_rows.filter(isRecord) : [];
  const competitorAName = toStringValue(aeoFacts?.competitor_a_name) || '竞品A';
  const competitorBName = toStringValue(aeoFacts?.competitor_b_name) || '竞品B';
  const mentionRate = formatPercent(
    toNumberValue(summaryMetrics?.brand_mention_rate) ??
      toNumberValue((content.data.metrics as Record<string, unknown> | undefined)?.brand_mention_rate)
  );
  const scenarioHitCount = toNumberValue(summaryMetrics?.scenario_hit_count);
  const scenarioTotal = toNumberValue(summaryMetrics?.scenario_total);
  const officialCitationRate = formatPercent(toNumberValue(sourceOverview?.official_citation_rate));
  const officialCitations = toNumberValue(sourceOverview?.official_citations);
  const totalCitations = toNumberValue(sourceOverview?.total_citations);
  const brandDomain = toStringValue(reportRecord.brand_domain);
  const remainingSourceCount = toNumberValue(aeoFacts?.remaining_source_count);

  const positiveCount = view.mentions.sentiment_summary?.positive ?? 0;
  const neutralCount = view.mentions.sentiment_summary?.neutral ?? 0;
  const negativeCount = view.mentions.sentiment_summary?.negative ?? 0;
  const brandMentions = view.mentions.brand_mentions ?? [];
  const negativeMentions = brandMentions.filter(
    (item) => item.sentiment?.toLowerCase() === 'negative'
  );
  const legacyCompetitors = isRecord(content.data) && Array.isArray((content.data as Record<string, unknown>).competitors)
    ? ((content.data as Record<string, unknown>).competitors as unknown[])
    : [];
  const threatCompetitors = legacyCompetitors
    .filter(isRecord)
    .map((item) => {
      const name = toStringValue(item.name);
      const mentionRateValue = toNumberValue(item.mention_rate);
      if (!name || mentionRateValue === undefined) {
        return null;
      }
      return {
        name,
        mentionRateValue,
        mentionRateText: formatPercent(mentionRateValue),
      };
    })
    .filter((item): item is { name: string; mentionRateValue: number; mentionRateText: string } => Boolean(item))
    .sort((a, b) => b.mentionRateValue - a.mentionRateValue)
    .filter((item) => {
      const brandMentionRate = toNumberValue(summaryMetrics?.brand_mention_rate) ?? 0;
      return item.mentionRateValue >= brandMentionRate * 0.75 || item.mentionRateValue >= brandMentionRate;
    })
    .slice(0, 3);

  const scenarioItems = view.scenarioCoverage.items ?? [];
  const missingItems = view.scenarioCoverage.missing_items ?? [];
  const riskItems = view.scenarioCoverage.risk_items ?? [];
  const contestedItems = [
    ...riskItems,
    ...scenarioItems.filter((item) => item.battle_status === 'contested'),
  ].slice(0, 4);

  const sourceDistributionTable = buildSourceDistributionTable(sourceOverview, factSourceRows);

  const suggestionLines: string[] = [];
  if (missingItems.length > 0) {
    suggestionLines.push(
      `优先补齐 ${missingItems
      .slice(0, 2)
      .map((item) => `“${shortenScenarioLabel(item.scenario_label, 22) || item.scenario_label}”`)
        .join('、')} 相关的官网 FAQ、参数页和对比页，先解决品牌缺席。`
    );
  }
  if (officialCitations !== undefined && totalCitations !== undefined && officialCitations <= 5) {
    suggestionLines.push(
      `官网当前仅被引用 ${officialCitations} 次（总引用 ${totalCitations} 次），需要优先补强官网结构化数据、车型对比页和问答页，提升官方信源进入 AI 引用链的概率。`
    );
  }
  if (threatCompetitors.length > 0) {
    suggestionLines.push(
      `围绕 ${threatCompetitors.map((item) => item.name).join('、')} 这些高压竞品，补充“对比型内容 + 场景型证据页”，减少被一比一压制的场景。`
    );
  }

  const lines: string[] = [];
  const summaryText =
    (isNonEmptyString(content.data.executive_summary) ? content.data.executive_summary.trim() : null) ||
    view.summary.summary ||
    `${brandName} 当前提及率为 ${mentionRate}，在 ${scenarioTotal ?? '--'} 个核心问题里只进入了 ${scenarioHitCount ?? '--'} 个场景，品牌还没有形成稳定的跨平台占位。`;

  lines.push('## 一、核心执行摘要');
  lines.push(summaryText);
  lines.push('');
  lines.push('## 二、核心数据基准看板');
  lines.push(`| 指标名称 | 指标定义 | ${brandName} 数据 | ${competitorAName} 数据 | ${competitorBName} 数据 | 诊断结论 |`);
  lines.push('| --- | --- | ---: | ---: | ---: | --- |');
  if (factMetricRows.length > 0) {
    for (const row of factMetricRows) {
      lines.push(
        `| ${toStringValue(row.metric_name) || '--'} | ${toStringValue(row.definition) || '--'} | ${toStringValue(row.brand_value) || '--'} | ${toStringValue(row.competitor_a_value) || '--'} | ${toStringValue(row.competitor_b_value) || '--'} | ${toStringValue(row.diagnosis) || '--'} |`
      );
    }
  } else {
    lines.push(`| 提及率 | 在监测问题中，被至少一个平台提及的比例。 | ${mentionRate} | -- | -- | 当前已形成基础曝光，但还没有稳定的领先优势。 |`);
    lines.push(`| 官网引用占比 | 在提及该品牌的回答里，引用链接指向官网的占比。 | ${officialCitationRate} | -- | -- | 官网信源是否真正影响答案，还需要结合来源分布继续判断。 |`);
    lines.push(`| 品牌内容引用占比 | 在提及该品牌的回答里，所有引用链接中直接指向品牌相关内容的占比。 | ${formatPercent(content.data.report_v2?.sources?.content_citation_rate ?? view.sources.content_citation_rate)} | -- | -- | 品牌内容储备是否足够，会直接决定品牌能否被持续引用。 |`);
    lines.push(`| 负向情感占比 | 在提及该品牌的回答里，带有明显负向倾向的占比。 | ${negativeMentions.length > 0 ? formatPercent(negativeMentions.length / Math.max(brandMentions.length, 1)) : '0.0%'} | -- | -- | 需要继续追溯具体负向样本，判断是历史语料还是竞品压制。 |`);
  }
  lines.push('');
  lines.push('### 证据来源分布（Top 15）');
  lines.push(...sourceDistributionTable);
  if ((remainingSourceCount ?? 0) > 0) {
    lines.push('');
    lines.push(`- 其余长尾来源合计 ${remainingSourceCount} 次引用。`);
  }
  lines.push('');

  lines.push('## 三、跨大模型平台表现拆解');
  lines.push('| 平台名称 | 平台抓取偏好 | 本品牌在该平台现状 | 存在问题与突破口 |');
  lines.push('| --- | --- | --- | --- |');
  if (factPlatformRows.length > 0) {
    for (const row of factPlatformRows) {
      lines.push(
        `| ${toStringValue(row.platform) || '--'} | ${toStringValue(row.preference) || '--'} | ${toStringValue(row.status) || '--'} | ${toStringValue(row.problem) || '--'} |`
      );
    }
  } else {
    const platforms = collectReportPlatforms(platformBreakdown, sourceOverview, brandMentions);
    for (const platform of platforms) {
      const raw = platformBreakdown && isRecord(platformBreakdown[platform]) ? (platformBreakdown[platform] as Record<string, unknown>) : {};
      const mentionCount =
        readNumber(raw, 'mentions') ??
        brandMentions.filter((item) => item.platform?.trim().toLowerCase() === platform).length;
      const total = readNumber(raw, 'total') ?? scenarioTotal ?? 0;
      const success = readNumber(raw, 'success') ?? total;
      const status = mentionCount > 0
        ? `本轮成功回答 ${success ?? '--'}/${total || '--'} 次，提及本品牌 ${mentionCount} 次。`
        : `本轮成功回答 ${success ?? '--'}/${total || '--'} 次，但尚未稳定提及本品牌。`;
      const problem = mentionCount > 0
        ? '已有基础提及，但仍需补齐更强的对比型与场景型品牌证据。'
        : '当前更像收录或语料缺口问题，应优先补齐该平台可抓取的品牌内容。';
      lines.push(`| ${getReportPlatformLabel(platform)} | ${getPlatformPreference(platform)} | ${status} | ${problem} |`);
    }
  }
  lines.push('');

  const missingExamples = factMissingExamples.length > 0
    ? factMissingExamples
    : missingItems.slice(0, 3).map((item) => {
        const itemRecord = item as unknown as Record<string, unknown>;
        return {
          scenario_label: item.scenario_label,
          evidence: item.evidence,
          query_examples: Array.isArray(itemRecord.query_examples) ? itemRecord.query_examples : [],
        };
      });
  const contestedExamples = factContestedExamples.length > 0
    ? factContestedExamples
    : contestedItems.slice(0, 3).map((item) => {
        const itemRecord = item as unknown as Record<string, unknown>;
        return {
          scenario_label: item.scenario_label,
          evidence: item.evidence,
          competitors_present: item.competitors_present ?? [],
          query_examples: Array.isArray(itemRecord.query_examples) ? itemRecord.query_examples : [],
          action_hint: toStringValue(itemRecord.action_hint),
        };
      });

  lines.push('## 四、主题场景诊断：缺位与竞争图谱');
  lines.push('### 品牌缺位场景');
  if (missingExamples.length > 0) {
    missingExamples.slice(0, 3).forEach((item, index) => {
      const examples = Array.isArray(item.query_examples) ? item.query_examples.filter(isNonEmptyString) : [];
      const question = (examples[0] as string | undefined) || toStringValue(item.scenario_label) || `缺位场景 ${index + 1}`;
      lines.push(`#### 典型问题 ${index + 1}`);
      lines.push(`- 问题：${question}`);
      lines.push(`- 数据依据：${toStringValue(item.evidence) || 'AI 已回答该问题，但品牌没有进入最终答案。'}`);
      lines.push('- 业务影响：这类问题通常已经进入高意图决策阶段，品牌如果完全缺位，用户会直接被带向竞品或替代方案。');
    });
  } else {
    lines.push('- 本轮没有观察到完全缺位的典型场景，但仍建议持续扩大样本，排查长尾问题。');
  }
  lines.push('');
  lines.push('### 竞争胶着场景');
  if (contestedExamples.length > 0) {
    contestedExamples.slice(0, 3).forEach((item, index) => {
      const examples = Array.isArray(item.query_examples) ? item.query_examples.filter(isNonEmptyString) : [];
      const question = (examples[0] as string | undefined) || toStringValue(item.scenario_label) || `竞争场景 ${index + 1}`;
      const rivals = Array.isArray(item.competitors_present) ? item.competitors_present.filter(isNonEmptyString).join('、') : '';
      lines.push(`#### 典型问题 ${index + 1}`);
      lines.push(`- 问题：${question}`);
      lines.push(`- 同框竞品：${rivals || '已观察到竞品同框，但当前样本未记录具体名称。'}`);
      lines.push(`- 数据依据：${toStringValue(item.evidence) || '品牌进入了答案，但未形成稳定主胜。'}`);
      if (toStringValue(item.action_hint)) {
        lines.push(`- 当前缺口：${toStringValue(item.action_hint)}`);
      }
      lines.push('- 诊断：这类问题通常已经进入横向对比阶段，大模型会优先采用证据更完整、对比语料更充分的一方。');
    });
  } else {
    lines.push('- 本轮没有观察到典型的竞品胶着场景，但仍建议持续监测对比类问题。');
  }
  lines.push('');

  lines.push('## 五、AEO 常态化运营与优化策略');
  lines.push('### 1. 基建优化（夯实第一信源）');
  if (brandDomain) {
    lines.push(`- 当前官网信号：${brandDomain} 被引用 ${officialCitations ?? '--'} 次，官网引用占比 ${officialCitationRate}。`);
  } else {
    lines.push('- 当前官网信号仍然偏弱，需要补齐更容易被 AI 解析的 FAQ、参数页、对比页和品牌说明页。');
  }
  lines.push('- 优先补齐结构化官网页面与问答页面，让品牌自己的权威内容真正进入答案引用链。');
  lines.push('');
  lines.push('### 2. 语料防御与对冲（处理负向与胶着）');
  lines.push(`- 当前情绪分布：正向 ${positiveCount}、中性 ${neutralCount}、负向 ${negativeCount}。`);
  lines.push(`- 当前高压竞品：${threatCompetitors.length > 0 ? threatCompetitors.map((item) => `${item.name}（提及率 ${item.mentionRateText}）`).join('、') : '暂无明显高压竞品'}。`);
  lines.push('- 需要持续铺设更高权重、更可验证的 EEAT 语料，尤其是对比型、场景型与权威背书型内容。');
  lines.push('');
  lines.push('### 3. 填补盲区漏洞（拓展增量流量）');
  if (suggestionLines.length > 0) {
    suggestionLines.slice(0, 2).forEach((line) => lines.push(`- ${line}`));
  } else {
    lines.push('- 针对仍未进入答案的问题场景，定向生产首发内容，先解决缺位，再争取主胜。');
  }
  lines.push('- 内容选题必须直接对应真实提问方式，而不是泛化品牌宣传。');
  lines.push('');
  lines.push('### 4. 按月度 / 双周回测监测');
  lines.push('- 持续回测提及率、官网引用占比、品牌内容引用占比、负向情感占比四项核心指标。');
  lines.push('- 同时跟踪平台表现、缺位场景与竞争胶着场景，验证新增语料是否真的进入了答案与引用链。');

  return lines.join('\n').trim();
}

function buildFetchCitationLine(citation: FetchCitation): string {
  return joinInline([
    `[${citation.index}] ${citation.title}`,
    citation.site_name || citation.url,
    citation.is_official ? '官网' : null,
  ], ' ｜ ') || citation.title || citation.url;
}

function buildFetchPlatformBlock(result: FetchPlatformResult): string[] {
  const lines: string[] = [];
  lines.push(`### ${result.platform || '未知平台'}`);

  if (!result.success) {
    lines.push('- 状态：失败');
    if (result.error) {
      lines.push(`- 原因：${result.error}`);
    }
    lines.push('');
    return lines;
  }

  const meta = joinInline([
    result.fetch_method ? `抓取方式：${result.fetch_method}` : null,
    typeof result.duration === 'number' ? `耗时：${result.duration.toFixed(1)}s` : null,
    typeof result.answer?.word_count === 'number' ? `字数：${result.answer.word_count}` : null,
    typeof result.answer?.has_brand_mention === 'boolean' ? `品牌提及：${result.answer.has_brand_mention ? '是' : '否'}` : null,
  ]);

  if (meta) {
    lines.push(meta);
  }

  if (isNonEmptyString(result.answer?.content)) {
    lines.push('', result.answer.content.trim());
  }

  if (Array.isArray(result.citations) && result.citations.length > 0) {
    lines.push('', '#### 引用来源');
    for (const citation of result.citations) {
      lines.push(`- ${buildFetchCitationLine(citation)}`);
    }
  }

  lines.push('');
  return lines;
}

function buildFetchResultsMarkdown(content: Extract<CanvasContent, { type: 'fetchResults' }>, descriptor: ExportDescriptor): string {
  const view = buildFetchExportViewModel(content);
  const lines: string[] = [
    `# ${descriptor.title || view.title || 'AI答案抓取'}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  const fetchResults = view.items;
  if (fetchResults.length === 0) {
    lines.push('暂无抓取结果。');
    return lines.join('\n');
  }

  for (const [index, item] of fetchResults.entries()) {
    lines.push(`## 问题 ${index + 1}`);
    lines.push(isNonEmptyString(item.question_text) ? item.question_text.trim() : '未提供问题文本');
    lines.push('');

    for (const platformResult of item.platform_results || []) {
      lines.push(...buildFetchPlatformBlock(platformResult));
    }
  }

  return lines.join('\n');
}

function pushScenarioCoverageBlock(
  lines: string[],
  title: string,
  summary: string | undefined,
  items: Array<{
    scenario_label: string;
    scenario_priority?: string;
    present_platforms?: string[];
    competitors_present?: string[];
    battle_status?: string;
    evidence?: string;
  }>
) {
  if (!items.length) {
    return;
  }

  lines.push(`## ${title}`);
  if (summary) {
    lines.push(summary, '');
  }
  for (const item of items) {
    lines.push(`- ${joinInline([
      item.scenario_label,
      item.scenario_priority ? `优先级：${item.scenario_priority}` : null,
      item.present_platforms && item.present_platforms.length > 0 ? `平台：${item.present_platforms.join('、')}` : null,
      item.competitors_present && item.competitors_present.length > 0 ? `竞品：${item.competitors_present.join('、')}` : null,
      item.battle_status ? `态势：${item.battle_status}` : null,
      item.evidence,
    ], ' ｜ ') || item.scenario_label}`);
  }
  lines.push('');
}

function buildStandardReportMarkdown(content: ReportCanvasContent, descriptor: ExportDescriptor): string {
  const view = buildReportViewModel(content);
  const reportMarkdown = buildCustomerReportMarkdown(content);
  const lines: string[] = [
    `# ${view.headline || descriptor.title || descriptor.deliverableName}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  if (reportMarkdown) {
    if (content.data.subtitle) {
      lines.push(content.data.subtitle, '');
    }
    lines.push(reportMarkdown, '');
    return lines.join('\n');
  }

  pushSection(lines, '摘要', view.subtitle || content.data.content);

  if (view.summary.metrics && view.summary.metrics.length > 0) {
    lines.push('## 核心指标');
    for (const metric of view.summary.metrics) {
      lines.push(`- ${metric.label}：${formatMetricValue(metric)}${metric.description ? `（${metric.description}）` : ''}`);
    }
    lines.push('');
  }

  pushSection(lines, '状态总结', view.summary.status_summary || view.summary.summary);
  pushBulletSection(lines, '重点高亮', view.summary.highlights || []);

  if (view.mentions.brand_mentions && view.mentions.brand_mentions.length > 0) {
    lines.push('## 品牌提及');
    for (const item of view.mentions.brand_mentions) {
      lines.push(`- ${buildMentionLine(item)}`);
    }
    lines.push('');
  }

  if (view.mentions.competitor_mentions && view.mentions.competitor_mentions.length > 0) {
    lines.push('## 竞品提及');
    for (const item of view.mentions.competitor_mentions) {
      lines.push(`- ${buildMentionLine(item)}`);
    }
    lines.push('');
  }

  if (view.scenarioCoverage.semantic_lenses && view.scenarioCoverage.semantic_lenses.length > 0) {
    lines.push('## 场景标签归纳');
    for (const lens of view.scenarioCoverage.semantic_lenses) {
      if (!lens.items || lens.items.length === 0) {
        continue;
      }
      lines.push(`### ${lens.label}`);
      for (const item of lens.items) {
        lines.push(`- ${joinInline([
          item.label,
          `我方：${item.brandCount}`,
          `竞品：${item.competitorCount}`,
          item.missingCount > 0 ? `待进入：${item.missingCount}` : null,
          item.riskCount > 0 ? `高风险：${item.riskCount}` : null,
        ], ' ｜ ') || lens.label}`);
      }
      lines.push('');
    }
  }

  pushScenarioCoverageBlock(
    lines,
    view.scenarioCoverage.title || '已覆盖场景',
    view.scenarioCoverage.summary,
    view.scenarioCoverage.items || []
  );
  pushScenarioCoverageBlock(
    lines,
    '待进入场景',
    view.scenarioCoverage.missing_summary,
    view.scenarioCoverage.missing_items || []
  );
  pushScenarioCoverageBlock(
    lines,
    '高风险场景',
    view.scenarioCoverage.risk_summary,
    view.scenarioCoverage.risk_items || []
  );


  if (view.sources.citation_analysis?.top_domains && view.sources.citation_analysis.top_domains.length > 0) {
    lines.push(`## ${view.sources.title || '信息源分析'}`);
    const sourceSummary = joinInline([
      view.sources.summary,
      `官网引用率：${formatPercent(view.sources.official_citation_rate)}`,
    ], ' ｜ ');
    if (sourceSummary) {
      lines.push(sourceSummary, '');
    }
    for (const domain of view.sources.citation_analysis.top_domains) {
      lines.push(`- ${joinInline([
        domain.domain,
        typeof domain.count === 'number' ? `次数：${domain.count}` : null,
        domain.is_official ? '官网' : null,
        domain.sample_titles && domain.sample_titles.length > 0 ? `样例：${domain.sample_titles.slice(0, 2).join('；')}` : null,
      ], ' ｜ ') || domain.domain}`);
    }
    lines.push('');
  }

  if (view.sources.citation_cases && view.sources.citation_cases.length > 0) {
    lines.push('## 引用案例');
    for (const item of view.sources.citation_cases) {
      lines.push(`- ${joinInline([
        item.scenario_label,
        item.platform ? `平台：${item.platform}` : null,
        item.is_official ? '官网' : '第三方',
        item.citation_domains && item.citation_domains.length > 0 ? `来源：${item.citation_domains.join('、')}` : null,
        item.matched_answer,
      ], ' ｜ ') || item.scenario_label}`);
    }
    lines.push('');
  }


  return lines.join('\n');
}

export { buildCustomerReportMarkdown };

function buildConfidenceItemLine(item: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['items']>[number]): string {
  return joinInline([
    item.label,
    item.entity_label || item.entity_classification,
    typeof item.frequency === 'number' ? `频次：${item.frequency}` : null,
    typeof item.aice_score === 'number' ? `AICE：${formatScore(item.aice_score)}` : null,
  ], ' ｜ ') || item.label;
}

function buildConfidenceActionLine(item: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['strategicRecommendations']>[number]): string {
  return joinInline([
    item.title,
    item.reason,
    item.action ? `动作：${item.action}` : null,
  ], ' ｜ ') || item.title || '未命名动作';
}

function pushConfidencePattern(
  lines: string[],
  pattern: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['brandLowConfidencePatterns']>[number]
) {
  const title = pattern.pattern_label || pattern.pattern_key;
  if (!title) {
    return;
  }

  lines.push(`### ${title}`);
  const meta = joinInline([
    typeof pattern.sample_count === 'number' ? `样本：${pattern.sample_count}` : null,
    typeof pattern.average_confidence === 'number' ? `平均置信度：${formatScore(pattern.average_confidence)}` : null,
    typeof pattern.weighted_average_confidence === 'number'
      ? `加权平均：${formatScore(pattern.weighted_average_confidence)}`
      : null,
    pattern.affected_dimensions && pattern.affected_dimensions.length > 0
      ? `维度：${pattern.affected_dimensions.join('、')}`
      : null,
  ], ' ｜ ');
  if (meta) {
    lines.push(meta);
  }

  const examples = pattern.evidence_examples || [];
  for (const example of examples) {
    lines.push(`- ${joinInline([
      example.label,
      example.domain,
      typeof example.score === 'number' ? `置信度：${formatScore(example.score)}` : null,
      example.evidence,
    ], ' ｜ ') || '未命名样例'}`);
  }

  if (pattern.suggestion) {
    lines.push(`- 建议：${pattern.suggestion}`);
  }
  lines.push('');
}

function buildConfidenceReportMarkdown(content: ReportCanvasContent, descriptor: ExportDescriptor): string {
  const view = buildConfidenceExportViewModel(content);
  const summary = view.summary;
  const findings = view.findings;
  const brandOverview = view.brandConfidenceOverview;
  const competitorOverview = view.competitorConfidenceOverview;
  const brandPatterns = view.brandLowConfidencePatterns;
  const competitorPatterns = view.competitorLowConfidencePatterns;
  const recommendations = view.strategicRecommendations;
  const extraEvaluation = view.extraEvaluation;

  const lines: string[] = [
    `# ${view.title || descriptor.deliverableName}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  pushSection(lines, '报告摘要', view.subtitle || view.overallConclusion);

  if (summary) {
    lines.push('## 核心指标');
    lines.push(`- 评估来源：${summary.auto_evaluated_count ?? summary.evaluated_count ?? 0}`);
    lines.push(`- 额外评估：${summary.manual_count ?? extraEvaluation?.count ?? 0}`);
    lines.push(`- 平均置信分：${formatScore(summary.average_confidence_score ?? summary.average_score)}`);
    lines.push('');
  }

  if (brandOverview || competitorOverview) {
    lines.push('## 品牌 vs 竞品置信度对比');
    if (brandOverview) {
      lines.push(`- 我方平均置信度：${formatScore(brandOverview.average_confidence ?? undefined)} ｜ 加权平均：${formatScore(brandOverview.weighted_average_confidence ?? undefined)} ｜ 样本数：${brandOverview.source_count ?? 0} ｜ 低置信来源：${brandOverview.low_confidence_source_count ?? 0}`);
    }
    if (competitorOverview) {
      lines.push(`- 竞品平均置信度：${formatScore(competitorOverview.average_confidence ?? undefined)} ｜ 加权平均：${formatScore(competitorOverview.weighted_average_confidence ?? undefined)} ｜ 样本数：${competitorOverview.source_count ?? 0} ｜ 低置信来源：${competitorOverview.low_confidence_source_count ?? 0}`);
    }
    lines.push('');
  }

  if (findings.length > 0) {
    lines.push('## 关键发现');
    for (const item of findings) {
      lines.push(`- ${joinInline([item.title, item.description], ' ｜ ') || '未命名发现'}`);
    }
    lines.push('');
  }

  if (brandPatterns.length > 0) {
    lines.push('## 我方低置信内容共性');
    for (const pattern of brandPatterns) {
      pushConfidencePattern(lines, pattern);
    }
  }

  if (competitorPatterns.length > 0) {
    lines.push('## 竞品低置信内容共性');
    for (const pattern of competitorPatterns) {
      pushConfidencePattern(lines, pattern);
    }
  }

  if (recommendations.length > 0) {
    lines.push('## 补位建议');
    for (const item of recommendations) {
      lines.push(`- ${buildConfidenceActionLine(item)}`);
    }
    lines.push('');
  }

  if (extraEvaluation?.items && extraEvaluation.items.length > 0) {
    lines.push('## 额外评估结果');
    for (const item of extraEvaluation.items) {
      lines.push(`- ${buildConfidenceItemLine(item)}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

export function isCanvasContentExportable(content: CanvasContent): boolean {
  return getDeliverableName(resolveActiveContent(content)) !== null;
}

export function getCanvasExportLabel(content: CanvasContent): SupportedDeliverable | null {
  return getDeliverableName(resolveActiveContent(content));
}

export function buildCanvasContentTextFromDescriptor(
  content: CanvasContent,
  descriptor: ExportDescriptor
): string {
  const active = resolveActiveContent(content);
  if (active.type === 'fetchResults') {
    return buildFetchResultsMarkdown(active, descriptor);
  }

  if (active.type === 'report' && isConfidenceCanvasReport(active)) {
    return buildConfidenceReportMarkdown(active, descriptor);
  }

  if (active.type === 'report') {
    return buildStandardReportMarkdown(active, descriptor);
  }

  if (active.type === 'dataTable') {
    return buildDataTableMarkdown(active, descriptor);
  }

  return JSON.stringify(active.data, null, 2);
}

export function getCanvasContentText(content: CanvasContent, allContents: CanvasContent[]): string {
  const active = resolveActiveContent(content);
  const descriptor = buildExportDescriptor(content, allContents);
  if (!descriptor) {
    return JSON.stringify(active.data, null, 2);
  }

  return buildCanvasContentTextFromDescriptor(active, descriptor);
}
