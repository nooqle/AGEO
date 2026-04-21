import type {
  CanvasContent,
  FetchCitation,
  FetchPlatformResult,
  ReportCanvasContent,
} from '@/types/canvas';
import {
  buildConfidenceExportViewModel,
  buildFetchExportViewModel,
  isConfidenceCanvasReport,
  isSiteConfidenceCanvasReport,
} from '@/adapters/exportArtifacts';

export type SupportedExportFormat = 'pdf' | 'md' | 'csv';

export type SupportedDeliverable =
  | 'AI答案抓取'
  | '品牌全景分析'
  | '用户场景细分分析'
  | '置信度报告'
  | '官网AI友好度分析报告'
  | '过往资料表';

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
  const keywordIndex = ['品牌全景分析报告', '用户画像场景分析报告', 'AI 可见性分析报告', '置信度报告', '分析报告']
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
    return '过往资料表';
  }

  if (content.type !== 'report') {
    return null;
  }

  if (isConfidenceCanvasReport(content)) {
    return '置信度报告';
  }

  if (isSiteConfidenceCanvasReport(content)) {
    return '官网AI友好度分析报告';
  }

  if (content.category === 'panorama' || content.category === 'baseline') {
    return '品牌全景分析';
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

function buildCustomerReportMarkdown(content: ReportCanvasContent): string {
  const explicitMarkdown =
    typeof content.data.report_markdown === 'string' && content.data.report_markdown.trim()
      ? content.data.report_markdown.trim()
      : typeof content.data.full_markdown === 'string' && content.data.full_markdown.trim()
        ? content.data.full_markdown.trim()
      : '';

  if (explicitMarkdown) {
    return explicitMarkdown;
  }
  if (Array.isArray(content.data.sections)) {
    return content.data.sections
      .filter(isRecord)
      .map((section) => toStringValue(section.markdown))
      .filter((item): item is string => Boolean(item))
      .join('\n\n')
      .trim();
  }

  return '';
}

function buildFetchCitationLine(citation: FetchCitation): string {
  return joinInline([
    `[${citation.index}] ${citation.title}`,
    citation.site_name || citation.url,
    citation.is_official ? '官网' : null,
  ], ' ｜ ') || citation.title || citation.url;
}

function getFetchResultStatusLabel(result: FetchPlatformResult): string {
  const status = typeof result.status === 'string' ? result.status.trim().toLowerCase() : '';
  if (status === 'success' || (!status && result.success)) {
    return '成功';
  }
  if (status === 'skipped') {
    return '已跳过';
  }
  if (status === 'running') {
    return '进行中';
  }
  if (status === 'pending') {
    return '待处理';
  }
  if (status === 'takeover_required') {
    return '待接管';
  }
  return '失败';
}

function buildFetchPlatformBlock(result: FetchPlatformResult): string[] {
  const lines: string[] = [];
  lines.push(`### ${result.platform || '未知平台'}`);
  const statusLabel = getFetchResultStatusLabel(result);

  if (statusLabel !== '成功') {
    lines.push(`- 状态：${statusLabel}`);
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

function buildStandardReportMarkdown(content: ReportCanvasContent, descriptor: ExportDescriptor): string {
  const reportMarkdown = buildCustomerReportMarkdown(content);
  const title = content.data.title || content.data.headline || descriptor.title || descriptor.deliverableName;
  const subtitle = content.data.subtitle || content.data.executive_summary || content.data.content;
  const lines: string[] = [
    `# ${title}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  if (reportMarkdown) {
    if (subtitle) {
      lines.push(subtitle, '');
    }
    lines.push(reportMarkdown, '');
    return lines.join('\n');
  }

  lines.push('当前报告缺少 canonical markdown，旧版 fallback 已被禁用。', '');
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
