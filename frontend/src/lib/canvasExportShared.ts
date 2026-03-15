import type {
  CanvasContent,
  FetchCitation,
  FetchPlatformResult,
  ReportCanvasContent,
  ReportMentionItem,
  ReportRiskItem,
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

function toTextList(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isNonEmptyString).map((item) => item.trim());
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

function buildRiskLine(item: ReportRiskItem): string {
  return joinInline([
    item.scenario_label || item.risk_type,
    item.severity ? `严重度：${item.severity}` : null,
    item.reason,
    item.impact_summary,
    item.recommended_action_ref ? `建议：${item.recommended_action_ref}` : null,
  ], ' ｜ ') || '未命名风险';
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

  if (view.competitorBattle.summary_cards && view.competitorBattle.summary_cards.length > 0) {
    lines.push('## 竞品压力概览');
    for (const item of view.competitorBattle.summary_cards) {
      lines.push(`- ${joinInline([
        item.competitor,
        typeof item.shared_scenarios === 'number' ? `共享场景：${item.shared_scenarios}` : null,
        typeof item.competitor_only_scenarios === 'number' ? `竞品独占：${item.competitor_only_scenarios}` : null,
        typeof item.brand_only_scenarios === 'number' ? `我方独占：${item.brand_only_scenarios}` : null,
        item.pressure_level ? `压力：${item.pressure_level}` : null,
      ], ' ｜ ') || item.competitor}`);
    }
    lines.push('');
  }

  if (view.competitorBattle.items && view.competitorBattle.items.length > 0) {
    lines.push(`## ${view.competitorBattle.title || '竞品争夺'}`);
    if (view.competitorBattle.overview) {
      lines.push(view.competitorBattle.overview, '');
    }
    for (const item of view.competitorBattle.items) {
      lines.push(`- ${joinInline([
        item.scenario_label,
        item.competitors_present && item.competitors_present.length > 0 ? `竞品：${item.competitors_present.join('、')}` : null,
        item.battle_status ? `态势：${item.battle_status}` : null,
        item.evidence,
        item.recommended_focus ? `建议：${item.recommended_focus}` : null,
      ], ' ｜ ') || item.scenario_label}`);
    }
    lines.push('');
  }

  if (view.risks.items && view.risks.items.length > 0) {
    lines.push(`## ${view.risks.title || '缺口与风险'}`);
    if (view.risks.summary) {
      lines.push(view.risks.summary, '');
    }
    for (const item of view.risks.items) {
      lines.push(`- ${buildRiskLine(item)}`);
    }
    lines.push('');
  }

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

  if (view.actionQueue.items && view.actionQueue.items.length > 0) {
    lines.push(`## ${view.actionQueue.title || '行动队列'}`);
    if (view.actionQueue.summary) {
      lines.push(view.actionQueue.summary, '');
    }
    for (const item of view.actionQueue.items) {
      lines.push(`- ${joinInline([
        item.title || item.action || item.scenario_label || '未命名动作',
        item.priority ? `优先级：${item.priority}` : null,
        item.target ? `目标：${item.target}` : null,
        item.expected_impact ? `预期影响：${item.expected_impact}` : null,
        item.difficulty ? `难度：${item.difficulty}` : null,
        item.timeline ? `周期：${item.timeline}` : null,
      ], ' ｜ ')}`);
    }
    lines.push('');
  }

  if (view.insights.strengths && view.insights.strengths.length > 0) {
    lines.push('## 优势洞察');
    for (const item of view.insights.strengths) {
      lines.push(`- ${joinInline([
        item.title,
        item.scenario ? `场景：${item.scenario}` : null,
        item.evidence,
        item.improvement_hint ? `延展：${item.improvement_hint}` : null,
      ], ' ｜ ') || item.title}`);
    }
    lines.push('');
  }

  if (view.insights.weaknesses && view.insights.weaknesses.length > 0) {
    lines.push('## 待修复洞察');
    for (const item of view.insights.weaknesses) {
      lines.push(`- ${joinInline([
        item.title,
        item.scenario ? `场景：${item.scenario}` : null,
        item.evidence,
        item.improvement_hint ? `修复建议：${item.improvement_hint}` : null,
      ], ' ｜ ') || item.title}`);
    }
    lines.push('');
  }

  return lines.join('\n');
}

function buildConfidenceItemLine(item: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['items']>[number]): string {
  return joinInline([
    item.label,
    item.entity_label || item.entity_classification,
    item.quadrant_label || item.quadrant,
    typeof item.frequency === 'number' ? `频次：${item.frequency}` : null,
    typeof item.aice_score === 'number' ? `AICE：${formatScore(item.aice_score)}` : null,
    item.repair_action ? `动作：${item.repair_action}` : null,
  ], ' ｜ ') || item.label;
}

function buildConfidenceQuadrantLine(item: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['quadrantOverview']>[number]): string {
  return joinInline([
    item.quadrant_label || item.quadrant,
    typeof item.count === 'number' ? `数量：${item.count}` : null,
    item.strategy ? `策略：${item.strategy}` : null,
    item.description,
  ], ' ｜ ') || item.quadrant;
}

function buildConfidenceActionLine(item: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['repairActions']>[number]): string {
  return joinInline([
    item.priority,
    item.title,
    item.summary,
    typeof item.count === 'number' ? `涉及样本：${item.count}` : null,
  ], ' ｜ ') || item.title || '未命名动作';
}

function pushConfidenceBlock(
  lines: string[],
  block: NonNullable<ReturnType<typeof buildConfidenceExportViewModel>['analysisBlocks']>[number]
) {
  if (!block.items || block.items.length === 0) {
    return;
  }

  lines.push(`## ${block.title || block.key}`);
  if (block.description) {
    lines.push(block.description, '');
  }
  for (const item of block.items) {
    lines.push(`- ${buildConfidenceItemLine(item)}`);
    const reasons = toTextList(item.primary_reasons || item.top_signals);
    if (reasons.length > 0) {
      lines.push(`  - ${block.reason_label || '原因'}：${reasons.slice(0, 3).join('；')}`);
    }
  }
  lines.push('');
}

function buildConfidenceReportMarkdown(content: ReportCanvasContent, descriptor: ExportDescriptor): string {
  const view = buildConfidenceExportViewModel(content);
  const summary = view.summary;
  const findings = view.findings;
  const quadrantOverview = view.quadrantOverview;
  const analysisBlocks = view.analysisBlocks;
  const repairActions = view.repairActions;
  const generalKnowledgeInsight = view.generalKnowledgeInsight;

  const lines: string[] = [
    `# ${view.title || descriptor.deliverableName}`,
    '',
    ...createMetadataLines(descriptor),
    '',
  ];

  pushSection(lines, '报告摘要', view.subtitle || view.diagnosis);

  if (summary) {
    lines.push('## 核心指标');
    lines.push(`- 总引用来源：${summary.evaluated_count ?? 0}`);
    lines.push(`- 我方阵营：${summary.brand_count ?? 0}`);
    lines.push(`- 竞方阵营：${summary.competitor_count ?? 0}`);
    lines.push(`- 共业阵营：${summary.general_knowledge_count ?? 0}`);
    lines.push(`- 第二象限：${summary.second_quadrant_count ?? 0}`);
    lines.push(`- 平均 AICE：${formatScore(summary.average_score)}`);
    lines.push('');
  }

  if (findings.length > 0) {
    lines.push('## 关键发现');
    for (const item of findings) {
      lines.push(`- ${joinInline([item.title, item.description], ' ｜ ') || '未命名发现'}`);
    }
    lines.push('');
  }

  if (quadrantOverview.length > 0) {
    lines.push('## 象限概览');
    for (const item of quadrantOverview) {
      lines.push(`- ${buildConfidenceQuadrantLine(item)}`);
    }
    lines.push('');
  }

  for (const block of analysisBlocks) {
    pushConfidenceBlock(lines, block);
  }

  if (generalKnowledgeInsight?.summary) {
    pushSection(lines, '共业阵营观察', generalKnowledgeInsight.summary);
  }

  pushBulletSection(
    lines,
    '共业高频来源',
    (generalKnowledgeInsight?.top_frequency_items || []).map((item) => buildConfidenceItemLine(item))
  );
  pushBulletSection(
    lines,
    '共业高分来源',
    (generalKnowledgeInsight?.top_score_items || []).map((item) => buildConfidenceItemLine(item))
  );

  if (repairActions.length > 0) {
    lines.push('## 修我行动清单');
    for (const item of repairActions) {
      lines.push(`- ${buildConfidenceActionLine(item)}`);
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
