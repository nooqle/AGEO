import type {
  ActionQueueData,
  CitationAnalysis,
  CitationDomainItem,
  CompetitorBattleData,
  InsightSectionData,
  PlatformCitationStats,
  ReportCitationCase,
  ReportCanvasContent,
  ReportMentionItem,
  ReportMentionScenarioGroup,
  ReportMentionSectionData,
  ReportSummaryData,
  ReportV2Metric,
  RiskSectionData,
  ScenarioCoverageData,
  ScenarioCoverageItem,
  ScenarioCoverageLens,
  ScenarioCoverageLensItem,
  SourceSectionData,
} from '@/types/canvas';
type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
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

function toBooleanValue(value: unknown): boolean | undefined {
  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'number') {
    return value !== 0;
  }

  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'y', '有', '是', '已'].includes(normalized)) {
      return true;
    }
    if (['false', '0', 'no', 'n', '无', '否', '未'].includes(normalized)) {
      return false;
    }
  }

  return undefined;
}

function toRecordArray(value: unknown): UnknownRecord[] {
  return Array.isArray(value) ? value.filter(isRecord) : [];
}

function toStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) {
    return [];
  }

  return value
    .map((item) => (typeof item === 'string' ? item.trim() : undefined))
    .filter((item): item is string => Boolean(item));
}

function uniqueStrings(values: Array<string | undefined>): string[] {
  return [...new Set(values.filter((value): value is string => Boolean(value)))];
}

function normalizePercent(value: number | undefined): number | undefined {
  if (value === undefined) {
    return undefined;
  }

  return value <= 1 ? value * 100 : value;
}

function containsDeprecatedScoreNarrative(value: string | undefined): boolean {
  if (!value) {
    return false;
  }

  const lowered = value.toLowerCase();
  return [
    'bwvs',
    '品牌ai可见度指数',
    '可见度指数',
    '综合分',
    '总体得分',
    '评分体系',
    'score band',
    'overall score',
  ].some((keyword) => lowered.includes(keyword.toLowerCase()));
}

function sanitizeNarrativeText(value: string | undefined): string | undefined {
  const text = toStringValue(value);
  if (!text || containsDeprecatedScoreNarrative(text)) {
    return undefined;
  }
  return text;
}

function statusToAssessment(status: ReportV2Metric['status']): string {
  if (status === 'good') return '优秀';
  if (status === 'warning') return '及格';
  if (status === 'risk') return '不及格';
  return '待判断';
}

function readField(record: UnknownRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    if (key in record) {
      return record[key];
    }
  }
  return undefined;
}

function readString(record: UnknownRecord, ...keys: string[]): string | undefined {
  return toStringValue(readField(record, ...keys));
}

function readNumber(record: UnknownRecord, ...keys: string[]): number | undefined {
  return toNumberValue(readField(record, ...keys));
}

function readBoolean(record: UnknownRecord, ...keys: string[]): boolean | undefined {
  return toBooleanValue(readField(record, ...keys));
}

function readStringList(record: UnknownRecord, ...keys: string[]): string[] {
  return uniqueStrings(keys.flatMap((key) => toStringArray(record[key])));
}

function pickMetricValue(metrics: Record<string, unknown> | undefined, keys: string[]): unknown {
  if (!metrics) {
    return undefined;
  }

  for (const key of keys) {
    if (key in metrics) {
      return metrics[key];
    }
  }

  const lowerMap = new Map(Object.entries(metrics).map(([key, value]) => [key.toLowerCase(), value]));
  for (const key of keys) {
    const match = lowerMap.get(key.toLowerCase());
    if (match !== undefined) {
      return match;
    }
  }

  return undefined;
}

function dedupeScenarioItems(items: ScenarioCoverageItem[]): ScenarioCoverageItem[] {
  const map = new Map<string, ScenarioCoverageItem>();

  for (const item of items) {
    const key = item.scenario_label.trim().toLowerCase();
    if (!key) {
      continue;
    }

    const existing = map.get(key);
    if (!existing) {
      map.set(key, item);
      continue;
    }

    map.set(key, {
      ...existing,
      ...item,
      present_platforms: uniqueStrings([...(existing.present_platforms ?? []), ...(item.present_platforms ?? [])]),
      official_source_domains: uniqueStrings([
        ...(existing.official_source_domains ?? []),
        ...(item.official_source_domains ?? []),
      ]),
      evidence: existing.evidence || item.evidence,
      battle_status: existing.battle_status || item.battle_status,
      brand_present: existing.brand_present ?? item.brand_present,
      official_citation_present: existing.official_citation_present ?? item.official_citation_present,
    });
  }

  return [...map.values()];
}

function normalizeScenarioItem(record: UnknownRecord, fallbackLabel: string, defaultPresent?: boolean): ScenarioCoverageItem | null {
  const scenarioLabel =
    readString(record, 'scenario_label', 'scenarioLabel', 'label', 'scenario', 'title', 'name') ||
    fallbackLabel;

  if (!scenarioLabel) {
    return null;
  }

  const evidence =
    readString(record, 'evidence', 'reason', 'description', 'improvement_hint', 'improvementHint') ||
    undefined;

  return {
    scenario_id: readString(record, 'scenario_id', 'scenarioId'),
    scenario_label: scenarioLabel,
    scenario_priority: readString(record, 'scenario_priority', 'scenarioPriority', 'priority'),
    brand_present: readBoolean(record, 'brand_present', 'brandPresent') ?? defaultPresent,
    present_platforms: readStringList(record, 'present_platforms', 'presentPlatforms', 'platforms'),
    official_citation_present: readBoolean(
      record,
      'official_citation_present',
      'officialCitationPresent',
      'official_cited',
      'officialCited'
    ),
    official_source_domains: readStringList(record, 'official_source_domains', 'officialSourceDomains'),
    battle_status: readString(record, 'battle_status', 'battleStatus'),
    evidence,
    confidence: readNumber(record, 'confidence'),
    competitors_present: readStringList(record, 'competitors_present', 'competitorsPresent', 'competitors'),
    risk_reason_type: readString(record, 'risk_reason_type', 'riskReasonType'),
    risk_reason_summary: readString(record, 'risk_reason_summary', 'riskReasonSummary'),
    fact_basis: readStringList(record, 'fact_basis', 'factBasis'),
    semantic_tags: isRecord(readField(record, 'semantic_tags', 'semanticTags'))
      ? {
          audiences: readStringList(readField(record, 'semantic_tags', 'semanticTags') as UnknownRecord, 'audiences'),
          prices: readStringList(readField(record, 'semantic_tags', 'semanticTags') as UnknownRecord, 'prices'),
          features: readStringList(readField(record, 'semantic_tags', 'semanticTags') as UnknownRecord, 'features'),
          usages: readStringList(readField(record, 'semantic_tags', 'semanticTags') as UnknownRecord, 'usages'),
        }
      : undefined,
  };
}

function normalizeMentionGroup(record: UnknownRecord): ReportMentionScenarioGroup | null {
  const key = readString(record, 'key');
  const question = readString(record, 'question');
  if (!key || !question) {
    return null;
  }

  return {
    key,
    question,
    platforms: readStringList(record, 'platforms'),
    source_labels: readStringList(record, 'source_labels', 'sourceLabels'),
    brand_count: readNumber(record, 'brand_count', 'brandCount') ?? 0,
    competitor_count: readNumber(record, 'competitor_count', 'competitorCount') ?? 0,
    sentiment: readString(record, 'sentiment') || 'neutral',
    brand_labels: readStringList(record, 'brand_labels', 'brandLabels'),
    competitor_labels: readStringList(record, 'competitor_labels', 'competitorLabels'),
    brand_facts: readStringList(record, 'brand_facts', 'brandFacts'),
    competitor_facts: readStringList(record, 'competitor_facts', 'competitorFacts'),
  };
}

function normalizeScenarioLensItem(record: UnknownRecord): ScenarioCoverageLensItem | null {
  const label = readString(record, 'label');
  if (!label) {
    return null;
  }
  return {
    label,
    count: readNumber(record, 'count') ?? 0,
    brandCount: readNumber(record, 'brandCount', 'brand_count') ?? 0,
    competitorCount: readNumber(record, 'competitorCount', 'competitor_count') ?? 0,
    missingCount: readNumber(record, 'missingCount', 'missing_count') ?? 0,
    riskCount: readNumber(record, 'riskCount', 'risk_count') ?? 0,
  };
}

function normalizeScenarioLenses(value: unknown): ScenarioCoverageLens[] {
  const lenses = toRecordArray(value)
    .map((record): ScenarioCoverageLens | null => {
      const key = readString(record, 'key') as ScenarioCoverageLens['key'] | undefined;
      const label = readString(record, 'label');
      if (!key || !label) {
        return null;
      }
      return {
        key,
        label,
        items: toRecordArray(readField(record, 'items'))
          .map(normalizeScenarioLensItem)
          .filter((item): item is ScenarioCoverageLensItem => Boolean(item)),
      } satisfies ScenarioCoverageLens;
    });
  return lenses.filter((item): item is ScenarioCoverageLens => Boolean(item));
}

function normalizeTopDomains(raw: UnknownRecord | undefined): CitationDomainItem[] {
  return toRecordArray(raw ? readField(raw, 'top_domains', 'topDomains') : undefined).map((item) => ({
    domain: readString(item, 'domain') || '',
    count: readNumber(item, 'count') ?? 0,
    share: normalizePercent(readNumber(item, 'share')) ?? 0,
    is_official: readBoolean(item, 'is_official', 'isOfficial') ?? false,
    sample_titles: toStringArray(item.sample_titles),
  }));
}

function normalizePlatformCitationStats(raw: UnknownRecord | undefined): Record<string, PlatformCitationStats> {
  const stats = readField(raw ?? {}, 'platform_citation_stats', 'platformCitationStats');
  if (!isRecord(stats)) {
    return {};
  }

  return Object.fromEntries(
    Object.entries(stats).map(([platform, value]) => {
      const row = isRecord(value) ? value : {};
      return [platform, {
        total_citations: readNumber(row, 'total_citations', 'totalCitations') ?? 0,
        unique_domains: readNumber(row, 'unique_domains', 'uniqueDomains') ?? 0,
        official_count: readNumber(row, 'official_count', 'officialCount', 'official_citations', 'officialCitations') ?? 0,
        official_share: normalizePercent(readNumber(row, 'official_share', 'officialShare', 'official_citation_rate', 'officialCitationRate')) ?? 0,
        avg_citations_per_answer: readNumber(row, 'avg_citations_per_answer', 'avgCitationsPerAnswer') ?? 0,
        top_domains: toRecordArray(readField(row, 'top_domains', 'topDomains')).map((item) => ({
          domain: readString(item, 'domain') || '',
          count: readNumber(item, 'count') ?? 0,
        })),
      } satisfies PlatformCitationStats];
    })
  );
}

function buildCitationAnalysisFromSourceOverview(raw: UnknownRecord | undefined): CitationAnalysis | null {
  if (!raw) {
    return null;
  }

  return {
    total_citations: readNumber(raw, 'total_citations', 'totalCitations') ?? 0,
    unique_domains: readNumber(raw, 'unique_domains', 'uniqueDomains') ?? 0,
    official_citations: readNumber(raw, 'official_citations', 'officialCitations') ?? 0,
    official_share: normalizePercent(readNumber(raw, 'official_citation_rate', 'officialCitationRate')) ?? 0,
    brand_domain: readString(raw, 'brand_domain', 'brandDomain') || '',
    top_domains: normalizeTopDomains(raw),
    platform_citation_stats: normalizePlatformCitationStats(raw),
    note: readString(raw, 'note'),
  };
}

function createSummaryMetrics(
  metrics: Record<string, unknown> | undefined,
  scenarios: ScenarioCoverageData,
  sources: SourceSectionData
): ReportV2Metric[] {
  const scenarioItems = scenarios.items ?? [];
  const brandMentionRate = normalizePercent(
    toNumberValue(pickMetricValue(metrics, ['brand_mention_rate', 'mention_rate', 'mentionRate']))
  );
  const contentCitationRate =
    sources.content_citation_rate ??
    normalizePercent(
      toNumberValue(pickMetricValue(metrics, ['content_citation_rate', 'contentCitationRate']))
    );
  const scenarioCoverageCount = scenarioItems.filter((item) => item.brand_present).length || undefined;

  const items: ReportV2Metric[] = [
    {
      id: 'brand_mention_rate',
      label: '品牌提及率',
      value: brandMentionRate,
      unit: brandMentionRate !== undefined ? '%' : undefined,
      description: '回答里直接提到品牌的占比。',
      status:
        brandMentionRate === undefined ? 'neutral' : brandMentionRate >= 50 ? 'good' : brandMentionRate >= 20 ? 'warning' : 'risk',
    },
    {
      id: 'content_citation_rate',
      label: '内容引用率',
      value: contentCitationRate,
      unit: contentCitationRate !== undefined ? '%' : undefined,
      description: '品牌被提及的问题里，有多少已经进入了引用来源链。',
      status:
        contentCitationRate === undefined
          ? 'neutral'
          : contentCitationRate >= 30
          ? 'good'
          : contentCitationRate >= 10
          ? 'warning'
          : 'risk',
    },
    {
      id: 'scenario_coverage_count',
      label: '场景覆盖数',
      value: scenarioCoverageCount,
      description: '品牌进入回答的问题数。',
      status:
        scenarioCoverageCount === undefined
          ? 'neutral'
          : scenarioCoverageCount >= 8
          ? 'good'
          : scenarioCoverageCount >= 4
          ? 'warning'
          : 'risk',
    },
  ];

  return items.map((metric) => ({
    ...metric,
    assessment: statusToAssessment(metric.status),
  }));
}

function normalizeScenarioCoverage(data: ReportCanvasContent['data']): ScenarioCoverageData {
  const explicit = data.report_v2?.scenarioCoverage ?? data.scenario_coverage;
  const explicitItems = (explicit?.items ?? [])
    .map((item, index) => normalizeScenarioItem(item as unknown as UnknownRecord, `场景 ${index + 1}`))
    .filter((item): item is ScenarioCoverageItem => Boolean(item));

  const allRawScenarioItems = toRecordArray(data.scenario_matrix)
    .map((item, index) => normalizeScenarioItem(item, `场景 ${index + 1}`))
    .filter((item): item is ScenarioCoverageItem => item !== null && isMeaningfulQuestionLabel(item.scenario_label));
  const rawScenarioItems = allRawScenarioItems.filter((item) => item.brand_present === true);

  const items = dedupeScenarioItems(
    explicitItems.length > 0 ? explicitItems : rawScenarioItems
  ).filter((item) => item.brand_present === true);
  const missingItems = dedupeScenarioItems(
    (explicit?.missing_items ?? [])
      .map((item, index) => normalizeScenarioItem(item as unknown as UnknownRecord, `待进入场景 ${index + 1}`))
      .filter((item): item is ScenarioCoverageItem => Boolean(item))
  );
  const riskItems = dedupeScenarioItems(
    (explicit?.risk_items ?? [])
      .map((item, index) => normalizeScenarioItem(item as unknown as UnknownRecord, `高风险问题 ${index + 1}`))
      .filter((item): item is ScenarioCoverageItem => Boolean(item))
  );
  const semanticLenses = normalizeScenarioLenses(explicit?.semantic_lenses);

  return {
    title: '场景覆盖',
    description: sanitizeNarrativeText(explicit?.description),
    summary: sanitizeNarrativeText(explicit?.summary),
    overview: sanitizeNarrativeText(explicit?.overview),
    items,
    missing_items: missingItems,
    risk_items: riskItems,
    missing_summary: sanitizeNarrativeText(explicit?.missing_summary),
    risk_summary: sanitizeNarrativeText(explicit?.risk_summary),
    semantic_lenses: semanticLenses,
  };
}

function mergeSummaryMetrics(
  explicitMetrics: ReportV2Metric[] | undefined,
  fallbackMetrics: ReportV2Metric[]
): ReportV2Metric[] {
  if (!explicitMetrics || explicitMetrics.length === 0) {
    return fallbackMetrics;
  }

  const explicitById = new Map(explicitMetrics.map((metric) => [metric.id, metric]));
  const fallbackIds = new Set(fallbackMetrics.map((metric) => metric.id));

  const merged = fallbackMetrics.map((fallback) => {
    const metric = explicitById.get(fallback.id);
    if (!metric) {
      return fallback;
    }
    return {
      ...fallback,
      ...metric,
      value: metric.value !== undefined && metric.value !== null ? metric.value : fallback.value,
      unit: metric.value !== undefined && metric.value !== null ? metric.unit : fallback.unit,
      description: metric.description || fallback.description,
      status: metric.value !== undefined && metric.value !== null ? metric.status || fallback.status : fallback.status,
      assessment: metric.assessment || fallback.assessment,
    } satisfies ReportV2Metric;
  });

  const extras = explicitMetrics
    .filter((metric) => !fallbackIds.has(metric.id))
    .map((metric) => ({
      ...metric,
      assessment: metric.assessment || statusToAssessment(metric.status),
    }));

  return [...merged, ...extras];
}

function normalizeSummary(
  data: ReportCanvasContent['data'],
  scenarios: ScenarioCoverageData,
  sources: SourceSectionData
): ReportSummaryData {
  const explicit = data.report_v2?.summary ?? data.report_summary;
  const explicitHighlights = (explicit?.highlights ?? []).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));
  const keyFindings = toStringArray(data.key_findings).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));

  const fallbackMetrics = createSummaryMetrics(
    data.metrics as Record<string, unknown> | undefined,
    scenarios,
    sources
  );
  const metrics = mergeSummaryMetrics(explicit?.metrics, fallbackMetrics).filter((metric) =>
    ['brand_mention_rate', 'content_citation_rate', 'scenario_coverage_count'].includes(metric.id)
  );

  const summaryText =
    sanitizeNarrativeText(explicit?.summary) ||
    keyFindings[0] ||
    undefined;
  const statusSummary = sanitizeNarrativeText(explicit?.status_summary);

  return {
    title: explicit?.title || '核心指标',
    description: sanitizeNarrativeText(explicit?.description),
    summary: summaryText,
    status_summary: statusSummary,
    highlights: explicitHighlights,
    metrics,
  };
}

function formatSubtitle(data: ReportCanvasContent['data']): string | undefined {
  return sanitizeNarrativeText(data.subtitle);
}

function formatUpdatedAt(updatedAt: string | undefined): string | undefined {
  if (!updatedAt) {
    return undefined;
  }

  const parsed = new Date(updatedAt);
  if (Number.isNaN(parsed.getTime())) {
    return updatedAt;
  }

  return parsed.toLocaleString('zh-CN', {
    hour12: false,
  });
}

function extractMentionPayload(data: ReportCanvasContent['data']): UnknownRecord | undefined {
  if (isRecord(data.mention_sentiment_analysis)) {
    return data.mention_sentiment_analysis;
  }
  if (isRecord(data.report_data) && isRecord(data.report_data.mention_sentiment_analysis)) {
    return data.report_data.mention_sentiment_analysis as UnknownRecord;
  }
  return undefined;
}

function sanitizeCustomerText(value: string | undefined): string | undefined {
  const text = sanitizeNarrativeText(value);
  if (!text) return undefined;
  return text
    .replace(/bwvs[^。！？]*[。！？]?/gi, '')
    .replace(/引用得分为[^。！？]*[。！？]?/g, '')
    .replace(/品牌口碑基础/g, '品牌认知基础')
    .replace(/全平台权威性背书/g, '权威来源背书')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

function isMeaningfulQuestionLabel(value: string | undefined): boolean {
  const label = (value || '').trim();
  if (!label) return false;
  const lowered = label.toLowerCase();
  if (lowered.includes('bwvs')) return false;
  return !['未命名问题', '问题待补全', '回答样本', '引用样本', '品牌认知基础', '权威来源背书'].some((token) =>
    label.includes(token)
  );
}

function buildQuestionLabel(record: UnknownRecord, index: number): string {
  const label =
    readString(record, 'scenario_label', 'scenarioLabel', 'question_text', 'questionText', 'query', 'question', 'title') ||
    `问题 ${index + 1}`;
  return isMeaningfulQuestionLabel(label) ? label : `问题 ${index + 1}`;
}

function normalizeMentionItem(record: UnknownRecord, index: number) {
  return {
    scenario_id: readString(record, 'scenario_id', 'scenarioId'),
    scenario_label: buildQuestionLabel(record, index),
    platform: readString(record, 'platform'),
    sentiment: readString(record, 'sentiment') || 'neutral',
    evidence: sanitizeCustomerText(readString(record, 'evidence', 'matched_answer', 'matchedAnswer')),
    citation_domains: readStringList(record, 'citation_domains', 'citationDomains'),
    citation_titles: readStringList(record, 'citation_titles', 'citationTitles'),
    citation_urls: readStringList(record, 'citation_urls', 'citationUrls'),
    official_citation_present: readBoolean(record, 'official_citation_present', 'officialCitationPresent'),
    competitor: readString(record, 'competitor'),
  };
}

function normalizeMentions(data: ReportCanvasContent['data']): ReportMentionSectionData {
  const explicit = data.report_v2?.mentions;
  if (explicit) {
    const explicitGroups = (explicit.groups ?? [])
      .map((group) => normalizeMentionGroup(group as unknown as UnknownRecord))
      .filter((group): group is ReportMentionScenarioGroup => Boolean(group));
    return {
      ...explicit,
      groups: explicitGroups,
    };
  }

  const payload = extractMentionPayload(data);
  const brandPayload = payload && isRecord(payload.brand) ? (payload.brand as UnknownRecord) : undefined;
  const competitorPayload = payload && Array.isArray(payload.competitors) ? payload.competitors : [];
  const brandMentions = toRecordArray(brandPayload?.items).map(normalizeMentionItem);
  const competitorMentions = competitorPayload.flatMap((competitor) =>
    toRecordArray(isRecord(competitor) ? competitor.items : undefined).map((item, index) =>
      normalizeMentionItem(
        {
          ...(item as UnknownRecord),
          competitor: readString(isRecord(competitor) ? (competitor as UnknownRecord) : {}, 'competitor'),
        },
        index
      )
    )
  );
  const mentionRate =
    readNumber(isRecord(data.summary_metrics) ? data.summary_metrics : {}, 'brand_mention_rate', 'brandMentionRate') ??
    normalizePercent(toNumberValue(pickMetricValue(data.metrics as Record<string, unknown> | undefined, ['brand_mention_rate', 'mention_rate', 'mentionRate'])));
  const groupedMentions = toRecordArray(payload?.groups)
    .map(normalizeMentionGroup)
    .filter((group): group is ReportMentionScenarioGroup => Boolean(group));
  const groupedCount = groupedMentions.length;
  const summaryRecord = isRecord(brandPayload?.summary) ? brandPayload.summary : {};

  return {
    title: '提及率分析',
    description: undefined,
    mention_rate: mentionRate,
    mention_count: groupedCount,
    sentiment_summary: {
      positive: readNumber(summaryRecord, 'positive') ?? 0,
      neutral: readNumber(summaryRecord, 'neutral') ?? 0,
      negative: readNumber(summaryRecord, 'negative') ?? 0,
    },
    brand_mentions: brandMentions,
    competitor_mentions: competitorMentions,
    groups: groupedMentions,
  };
}

function buildCitationCasesFromMentions(items: ReportMentionItem[]): ReportCitationCase[] {
  return items
    .filter((item) => (item.citation_domains?.length ?? 0) > 0 || (item.citation_titles?.length ?? 0) > 0 || (item.citation_urls?.length ?? 0) > 0)
    .map((item) => ({
      scenario_label: item.scenario_label,
      platform: item.platform,
      matched_answer: item.evidence,
      citation_domains: item.citation_domains,
      citation_titles: item.citation_titles,
      citation_urls: item.citation_urls,
      is_official: item.official_citation_present,
      aice_score: null,
      aice_dimensions: null,
    }));
}

function normalizeSourcesForReport(
  data: ReportCanvasContent['data'],
  mentions: ReportMentionSectionData
): SourceSectionData {
  const explicit = data.report_v2?.sources ?? data.source_section;
  const rawSourceOverview = isRecord(data.source_overview) ? data.source_overview : undefined;
  const citationAnalysis =
    explicit?.citation_analysis ??
    data.citation_analysis ??
    buildCitationAnalysisFromSourceOverview(rawSourceOverview);

  const cases = explicit?.citation_cases && explicit.citation_cases.length > 0
    ? explicit.citation_cases
    : buildCitationCasesFromMentions(mentions.brand_mentions ?? []);

  const officialCases = cases.filter((item) => item.is_official);
  const nonOfficialCases = cases.filter((item) => !item.is_official);
  const citedAnswerCount = new Set(
    cases.map((item) => `${item.scenario_label}::${item.platform || ''}`).filter(Boolean)
  ).size;
  const citedContentCount = new Set(
    cases.flatMap((item) => [
      ...(item.citation_titles ?? []),
      ...(item.citation_domains ?? []),
      ...(item.citation_urls ?? []),
    ]).filter(Boolean)
  ).size;
  const mentionCount = mentions.brand_mentions?.length ?? 0;
  const contentCitationRate =
    mentionCount > 0 ? normalizePercent((citedAnswerCount / mentionCount) as number) : undefined;

  return {
    title: '引用来源分析',
    description: sanitizeNarrativeText(explicit?.description),
    content_citation_rate: explicit?.content_citation_rate ?? contentCitationRate,
    mention_question_count: mentionCount,
    cited_answer_count: explicit?.cited_answer_count ?? citedAnswerCount,
    cited_content_count: explicit?.cited_content_count ?? citedContentCount,
    official_case_count: explicit?.official_case_count ?? officialCases.length,
    non_official_case_count: explicit?.non_official_case_count ?? nonOfficialCases.length,
    official_citation_rate:
      explicit?.official_citation_rate ??
      (citationAnalysis ? citationAnalysis.official_share : undefined) ??
      normalizePercent(readNumber(rawSourceOverview ?? {}, 'official_citation_rate', 'officialCitationRate')),
    official_top_titles: uniqueStrings([
      ...toStringArray(readField(rawSourceOverview ?? {}, 'official_top_titles', 'officialTopTitles')),
      ...officialCases.flatMap((item) => item.citation_titles ?? []),
    ]),
    citation_cases: cases,
    citation_analysis: citationAnalysis,
  };
}

const EMPTY_COMPETITOR_BATTLE: CompetitorBattleData = {
  title: '竞品争夺',
  summary_cards: [],
  items: [],
};

const EMPTY_RISKS: RiskSectionData = {
  title: '待进入场景与高风险场景',
  items: [],
};

const EMPTY_INSIGHTS: InsightSectionData = {
  title: '当前优势与补强',
  strengths: [],
  weaknesses: [],
};

const EMPTY_ACTION_QUEUE: ActionQueueData = {
  title: '下一步优化',
  items: [],
};

export interface ReportViewModel {
  headline: string;
  subtitle?: string;
  updatedAt?: string;
  degradationNote?: string;
  isBaseline: boolean;
  summary: ReportSummaryData;
  scenarioCoverage: ScenarioCoverageData;
  competitorBattle: CompetitorBattleData;
  risks: RiskSectionData;
  mentions: ReportMentionSectionData;
  sources: SourceSectionData;
  insights: InsightSectionData;
  actionQueue: ActionQueueData;
}

export function buildReportViewModel(content: ReportCanvasContent): ReportViewModel {
  const data = content.data;
  const mentions = normalizeMentions(data);
  const scenarios = normalizeScenarioCoverage(data);
  const sources = normalizeSourcesForReport(data, mentions);
  const summary = normalizeSummary(data, scenarios, sources);
  const subtitle = formatSubtitle(data);
  const headline = sanitizeNarrativeText(data.headline) || '品牌战况报告';
  const updatedAt = formatUpdatedAt(data.updated_at);
  const degradationNote = toStringValue(data._degradation_note);
  const isBaseline = content.category === 'baseline';

  return {
    headline,
    subtitle,
    updatedAt,
    degradationNote,
    isBaseline,
    summary,
    scenarioCoverage: scenarios,
    competitorBattle: EMPTY_COMPETITOR_BATTLE,
    risks: EMPTY_RISKS,
    mentions,
    sources,
    insights: EMPTY_INSIGHTS,
    actionQueue: EMPTY_ACTION_QUEUE,
  };
}










