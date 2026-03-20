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

export type SupportedExportFormat = 'pdf' | 'md';

export type SupportedDeliverable =
  | 'AI答案抓取'
  | '基线全景分析'
  | '用户场景细分分析'
  | '置信度报告';

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

  if (content.type !== 'report') {
    return null;
  }

  if (content.data.report_kind === 'confidence_signal' || content.data.artifact_kind === 'confidence_signal') {
    return '置信度报告';
  }

  if (content.category === 'baseline') {
    return '基线全景分析';
  }

  return '用户场景细分分析';
}

export function inferBrandName(content: CanvasContent, allContents: CanvasContent[]): string {
  const active = resolveActiveContent(content);

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
  const lines: string[] = [
    `# ${view.headline || descriptor.title || descriptor.deliverableName}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

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
