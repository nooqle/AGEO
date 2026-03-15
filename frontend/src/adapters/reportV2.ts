import type {
  ActionQueueData,
  ActionQueueItem,
  CitationAnalysis,
  CitationDomainItem,
  CompetitorBattleData,
  CompetitorBattleItem,
  CompetitorBattleSummaryCard,
  InsightSectionData,
  PlatformCitationStats,
  ReportCitationCase,
  ReportCanvasContent,
  ReportMentionItem,
  ReportMentionSectionData,
  ReportRiskItem,
  ReportSummaryData,
  ReportV2Metric,
  RiskSectionData,
  ScenarioCoverageData,
  ScenarioCoverageItem,
  ScenarioCoverageLens,
  SourceSectionData,
} from '@/types/canvas';
import {
  buildScenarioSemanticLenses,
  enrichScenarioItemSemantics,
  summarizeSemanticTags,
} from '@/lib/a5Semantic';
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

function guessOfficialCitation(evidence: string | undefined): boolean | undefined {
  if (!evidence) {
    return undefined;
  }

  const lowered = evidence.toLowerCase();
  if (lowered.includes('官网') || lowered.includes('official')) {
    return true;
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

  return enrichScenarioItemSemantics({
    scenario_id: readString(record, 'scenario_id', 'scenarioId'),
    scenario_label: scenarioLabel,
    scenario_priority: readString(record, 'scenario_priority', 'scenarioPriority', 'priority'),
    brand_present: readBoolean(record, 'brand_present', 'brandPresent') ?? defaultPresent,
    present_platforms: readStringList(record, 'present_platforms', 'presentPlatforms', 'platforms'),
    official_citation_present:
      readBoolean(record, 'official_citation_present', 'officialCitationPresent', 'official_cited', 'officialCited') ??
      guessOfficialCitation(evidence),
    official_source_domains: readStringList(record, 'official_source_domains', 'officialSourceDomains'),
    battle_status: readString(record, 'battle_status', 'battleStatus'),
    evidence,
    confidence: readNumber(record, 'confidence'),
    competitors_present: readStringList(record, 'competitors_present', 'competitorsPresent', 'competitors'),
  });
}

function toRiskScenarioItem(
  item: ReportRiskItem,
  scenarioMap: Map<string, ScenarioCoverageItem>
): ScenarioCoverageItem {
  const scenarioLabel = item.scenario_label || '待补强场景';
  const scenarioKey = scenarioLabel.trim().toLowerCase();
  const matched = scenarioMap.get(scenarioKey);
  return enrichScenarioItemSemantics({
    scenario_id: matched?.scenario_id || item.risk_id,
    scenario_label: scenarioLabel,
    scenario_priority: matched?.scenario_priority || (item.severity === 'high' ? 'high' : 'medium'),
    brand_present: matched?.brand_present ?? (item.risk_type === 'no_official_citation'),
    present_platforms: matched?.present_platforms ?? [],
    official_citation_present: matched?.official_citation_present ?? false,
    official_source_domains: matched?.official_source_domains ?? [],
    battle_status:
      matched?.battle_status ||
      (item.risk_type === 'missing_presence'
        ? 'missing'
        : item.risk_type === 'competitor_substitution'
        ? 'contested'
        : 'defend'),
    evidence: sanitizeCustomerText(item.reason) || sanitizeCustomerText(item.impact_summary) || matched?.evidence,
    confidence: matched?.confidence,
    competitors_present: matched?.competitors_present ?? [],
  });
}

function buildScenarioMap(items: ScenarioCoverageItem[]): Map<string, ScenarioCoverageItem> {
  return new Map(
    items
      .filter((item) => item.scenario_label.trim())
      .map((item) => [item.scenario_label.trim().toLowerCase(), item] as const)
  );
}

function buildScenarioSemanticSummary(
  prefix: string,
  items: ScenarioCoverageItem[]
): string | undefined {
  if (items.length === 0) {
    return undefined;
  }

  const topLabels = (values: string[], fallback: string) => {
    if (values.length === 0) return fallback;
    const counter = new Map<string, number>();
    values.forEach((value) => counter.set(value, (counter.get(value) ?? 0) + 1));
    return [...counter.entries()]
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'))
      .slice(0, 3)
      .map(([label]) => label)
      .join('、');
  };

  const audiences = topLabels(items.flatMap((item) => item.semantic_tags?.audiences ?? []), '泛人群');
  const prices = topLabels(items.flatMap((item) => item.semantic_tags?.prices ?? []), '价格未明确');
  const features = topLabels(items.flatMap((item) => item.semantic_tags?.features ?? []), '决策点未明确');
  const usages = topLabels(items.flatMap((item) => item.semantic_tags?.usages ?? []), '使用场景未明确');

  return `${prefix}主要集中在 ${audiences}，价格带以 ${prices} 为主，用户最关心 ${features}，对应的使用场景主要是 ${usages}。`;
}

function collectScenarioLenses(
  effectiveItems: ScenarioCoverageItem[],
  missingItems: ScenarioCoverageItem[],
  riskItems: ScenarioCoverageItem[]
): ScenarioCoverageLens[] {
  const recordMap = new Map<
    string,
    {
      texts: string[];
      brandPresent?: boolean;
      competitorPresent?: boolean;
      missing?: boolean;
      risk?: boolean;
    }
  >();
  [...effectiveItems, ...missingItems, ...riskItems].forEach((item) => {
    const key = item.scenario_label.trim().toLowerCase();
    const existing = recordMap.get(key) ?? {
      texts: [],
      brandPresent: false,
      competitorPresent: false,
      missing: false,
      risk: false,
    };
    existing.texts = uniqueStrings([...existing.texts, item.scenario_label, item.evidence || '']);
    existing.brandPresent = existing.brandPresent || item.brand_present;
    existing.competitorPresent =
      existing.competitorPresent ||
      (item.competitors_present?.length ?? 0) > 0 ||
      item.battle_status === 'contested' ||
      item.battle_status === 'missing';
    existing.missing = existing.missing || item.battle_status === 'missing';
    existing.risk = existing.risk || item.battle_status === 'contested' || item.battle_status === 'defend';
    recordMap.set(key, existing);
  });
  const records = [...recordMap.values()];
  return buildScenarioSemanticLenses(records);
}

function normalizeCompetitorCard(record: UnknownRecord): CompetitorBattleSummaryCard | null {
  const competitor = readString(record, 'competitor', 'name');
  if (!competitor) {
    return null;
  }

  const vsBrand = readString(record, 'vs_brand', 'vsBrand');
  let pressureLevel: CompetitorBattleSummaryCard['pressure_level'];
  if (vsBrand?.includes('高于')) {
    pressureLevel = 'high';
  } else if (vsBrand?.includes('低于')) {
    pressureLevel = 'low';
  } else if (vsBrand?.includes('接近')) {
    pressureLevel = 'medium';
  }

  return {
    competitor,
    shared_scenarios: readNumber(record, 'shared_scenarios', 'sharedScenarios'),
    competitor_only_scenarios: readNumber(record, 'competitor_only_scenarios', 'competitorOnlyScenarios'),
    brand_only_scenarios: readNumber(record, 'brand_only_scenarios', 'brandOnlyScenarios'),
    pressure_level: readString(record, 'pressure_level', 'pressureLevel') || pressureLevel,
    top_conflict_scenarios: readStringList(record, 'top_conflict_scenarios', 'topConflictScenarios'),
  };
}

function normalizeCompetitorItem(record: UnknownRecord, fallbackLabel: string): CompetitorBattleItem | null {
  const scenarioLabel =
    readString(record, 'scenario_label', 'scenarioLabel', 'scenario', 'title') ||
    fallbackLabel;

  if (!scenarioLabel) {
    return null;
  }

  return {
    scenario_id: readString(record, 'scenario_id', 'scenarioId'),
    scenario_label: scenarioLabel,
    brand_present: readBoolean(record, 'brand_present', 'brandPresent'),
    competitors_present: readStringList(record, 'competitors_present', 'competitorsPresent', 'competitors'),
    winner_brands: uniqueStrings([
      ...readStringList(record, 'winner_brands', 'winnerBrands'),
      readString(record, 'winner_brand', 'winnerBrand'),
    ]),
    battle_status: readString(record, 'battle_status', 'battleStatus'),
    evidence: readString(record, 'evidence', 'reason', 'description'),
    recommended_focus: readString(record, 'recommended_focus', 'recommendedFocus'),
  };
}

function guessRiskType(record: UnknownRecord): string | undefined {
  const text = [record.risk_type, record.title, record.reason, record.description]
    .map(toStringValue)
    .filter((value): value is string => Boolean(value))
    .join(' ')
    .toLowerCase();

  if (!text) {
    return undefined;
  }
  if (text.includes('官网')) {
    return 'no_official_citation';
  }
  if (text.includes('竞品')) {
    return 'competitor_substitution';
  }
  if (text.includes('缺席') || text.includes('未进入')) {
    return 'missing_presence';
  }
  return 'weak_presence';
}

function normalizeRiskItem(record: UnknownRecord): ReportRiskItem | null {
  const title = readString(record, 'title');
  const reason = readString(record, 'reason', 'description');
  const scenarioLabel =
    readString(record, 'scenario_label', 'scenarioLabel', 'scenario') ||
    (title && !reason ? title : undefined);

  if (!scenarioLabel && !title && !reason) {
    return null;
  }

  return {
    risk_id: readString(record, 'risk_id', 'riskId', 'id'),
    risk_type: readString(record, 'risk_type', 'riskType') || guessRiskType(record),
    scenario_label: scenarioLabel,
    severity: readString(record, 'severity', 'level'),
    reason: reason || title,
    impact_summary: readString(record, 'impact_summary', 'impactSummary', 'mitigation'),
    evidence: readString(record, 'evidence', 'trigger_condition', 'triggerCondition'),
    recommended_action_ref: readString(record, 'recommended_action_ref', 'mitigation_hint', 'mitigationHint'),
  };
}

function normalizeActionItem(record: UnknownRecord, fallbackAction?: string): ActionQueueItem | null {
  const title = readString(record, 'title');
  const action = readString(record, 'action') || title || fallbackAction;

  if (!action) {
    return null;
  }

  return {
    action_id: readString(record, 'action_id', 'actionId', 'scenario_id', 'scenarioId'),
    priority: readNumber(record, 'priority') ?? readString(record, 'priority'),
    scenario_label: readString(record, 'scenario_label', 'scenarioLabel', 'scenario'),
    action,
    title,
    target: readString(record, 'target', 'improvement_area', 'improvementArea', 'rationale'),
    expected_metric: readString(record, 'expected_metric', 'expectedMetric', 'expected_impact', 'expectedImpact'),
    related_competitors: readStringList(record, 'related_competitors', 'relatedCompetitors', 'competitors'),
    status: readString(record, 'status'),
    owner_hint: readString(record, 'owner_hint', 'ownerHint'),
    expected_impact: readString(record, 'expected_impact', 'expectedImpact'),
    difficulty: readString(record, 'difficulty'),
    timeline: readString(record, 'timeline'),
  };
}

function dedupeActionItems(items: ActionQueueItem[]): ActionQueueItem[] {
  const map = new Map<string, ActionQueueItem>();

  for (const item of items) {
    const key = `${item.title || item.action || ''}::${item.scenario_label || ''}`.trim().toLowerCase();
    if (!key) {
      continue;
    }

    if (!map.has(key)) {
      map.set(key, item);
    }
  }

  return [...map.values()];
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
  risks: RiskSectionData,
  sources: SourceSectionData
): ReportV2Metric[] {
  const scenarioItems = scenarios.items ?? [];
  const riskItems = risks.items ?? [];
  const brandMentionRate = normalizePercent(
    toNumberValue(pickMetricValue(metrics, ['brand_mention_rate', 'mention_rate', 'mentionRate']))
  );
  const officialCitationRate =
    sources.official_citation_rate ??
    normalizePercent(toNumberValue(pickMetricValue(metrics, ['official_citation_rate', 'citation_rate'])));
  const inferredMissingHighValueScenarioCount = riskItems.filter((item) => item.risk_type === 'missing_presence').length || undefined;
  const missingHighValueScenarioCount =
    toNumberValue(
      pickMetricValue(metrics, ['missing_high_value_scenario_count', 'missing_scenario_count'])
    ) ?? inferredMissingHighValueScenarioCount;
  const highValueScenarioCoverageCount =
    scenarioItems.filter((item) => item.brand_present && item.scenario_priority === 'high').length || undefined;
  const totalHighValueScenarioCount =
    (highValueScenarioCoverageCount ?? 0) + (missingHighValueScenarioCount ?? 0) || undefined;
  const inferredHighRiskScenarioCount =
    riskItems.filter((item) => item.severity === 'high').length || undefined;
  const highRiskScenarioCount =
    toNumberValue(pickMetricValue(metrics, ['high_risk_scenario_count'])) ?? inferredHighRiskScenarioCount;

  const highValueCoverageRate =
    totalHighValueScenarioCount && totalHighValueScenarioCount > 0
      ? ((highValueScenarioCoverageCount ?? 0) / totalHighValueScenarioCount) * 100
      : undefined;

  const items: ReportV2Metric[] = [
    {
      id: 'brand_mention_rate',
      label: '品牌提及率',
      value: brandMentionRate,
      unit: brandMentionRate !== undefined ? '%' : undefined,
      description: '回答里直接提到品牌的占比，先看品牌有没有进场。',
      status:
        brandMentionRate === undefined ? 'neutral' : brandMentionRate >= 50 ? 'good' : brandMentionRate >= 20 ? 'warning' : 'risk',
    },
    {
      id: 'official_citation_rate',
      label: '官网引用率',
      value: officialCitationRate,
      unit: officialCitationRate !== undefined ? '%' : undefined,
      description: 'AI 引用链里有多少比例来自官网，决定官方说法有没有被采信。',
      status:
        officialCitationRate === undefined
          ? 'neutral'
          : officialCitationRate >= 30
          ? 'good'
          : officialCitationRate >= 10
          ? 'warning'
          : 'risk',
    },
    {
      id: 'high_value_scenario_coverage_count',
      label: '高价值场景覆盖数',
      value: highValueScenarioCoverageCount,
      description:
        totalHighValueScenarioCount && totalHighValueScenarioCount > 0
          ? `已覆盖 ${highValueScenarioCoverageCount ?? 0}/${totalHighValueScenarioCount} 个高价值场景。`
          : '高价值场景指购买意图强、值得优先抢占的问题。',
      status:
        highValueCoverageRate === undefined
          ? 'neutral'
          : highValueCoverageRate >= 70
          ? 'good'
          : highValueCoverageRate >= 40
          ? 'warning'
          : 'risk',
    },
    {
      id: 'high_risk_scenario_count',
      label: '高风险场景数',
      value: highRiskScenarioCount,
      description: '需要优先补强的问题数，通常意味着竞品抢位、品牌缺席或官网证据链薄弱。',
      status:
        highRiskScenarioCount === undefined
          ? 'neutral'
          : highRiskScenarioCount === 0
          ? 'good'
          : highRiskScenarioCount <= 2
          ? 'warning'
          : 'risk',
    },
  ];

  return items.map((metric) => ({
    ...metric,
    assessment: statusToAssessment(metric.status),
  }));
}

function buildStatusSummary(
  scenarios: ScenarioCoverageData,
  risks: RiskSectionData,
  metrics: ReportV2Metric[],
  summaryMetrics: UnknownRecord | undefined
): string | undefined {
  const metricMap = new Map(metrics.map((metric) => [metric.id, metric.value]));
  const missingCount =
    readNumber(summaryMetrics ?? {}, 'missing_high_value_scenario_count', 'missingHighValueScenarioCount') ??
    0;
  const highValueCoveredCount =
    (typeof metricMap.get('high_value_scenario_coverage_count') === 'number'
      ? Number(metricMap.get('high_value_scenario_coverage_count'))
      : undefined) ??
    scenarios.items?.filter((item) => item.brand_present && item.scenario_priority === 'high').length ??
    0;
  const highRiskCount =
    readNumber(summaryMetrics ?? {}, 'high_risk_scenario_count', 'highRiskScenarioCount') ??
    risks.items?.filter((item) => item.severity === 'high').length;
  const officialCitationRate = metricMap.get('official_citation_rate');
  const brandMentionRate = metricMap.get('brand_mention_rate');

  if (highValueCoveredCount === undefined && missingCount === undefined && highRiskCount === undefined && officialCitationRate === undefined) {
    return undefined;
  }

  const effectiveSummary = scenarios.summary;
  if ((highRiskCount ?? 0) > 0 || (missingCount ?? 0) > 0) {
    return `${effectiveSummary || '这份报告在看品牌进入了哪些购车场景。'} 其中仍有 ${missingCount ?? 0} 个高价值场景缺席，${highRiskCount ?? 0} 个场景已经进入优先补强区。`;
  }

  return `${effectiveSummary || '这份报告在看品牌进入了哪些购车场景。'} 当前品牌提及率 ${brandMentionRate ?? '--'}%，官网引用率 ${officialCitationRate ?? '--'}%。`;
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

  const strengthItems = [
    ...toRecordArray(data.strengths).map((record, index) => normalizeScenarioItem(record, `优势场景 ${index + 1}`, true)),
    ...(data.insights ?? [])
      .filter((item) => item.type === 'strength')
      .map((item, index) =>
        normalizeScenarioItem(
          {
            scenario_label: item.title,
            evidence: item.description,
            brand_present: true,
          },
          `优势场景 ${index + 1}`,
          true
        )
      ),
  ].filter((item): item is ScenarioCoverageItem => Boolean(item));

  const items = dedupeScenarioItems(
    explicitItems.length > 0 ? explicitItems : rawScenarioItems.length > 0 ? rawScenarioItems : strengthItems
  );
  const hitCount = items.filter((item) => item.brand_present).length;
  const scenarioMap = buildScenarioMap(allRawScenarioItems.length > 0 ? allRawScenarioItems : items);
  const riskCandidates = normalizeRisks(data).items ?? [];
  const missingItems = riskCandidates
    .filter((item) => item.risk_type === 'missing_presence')
    .map((item) => toRiskScenarioItem(item, scenarioMap));
  const riskItems = riskCandidates
    .filter((item) => item.severity === 'high' || item.risk_type === 'competitor_substitution' || item.risk_type === 'no_official_citation')
    .map((item) => toRiskScenarioItem(item, scenarioMap));
  const semanticLenses = collectScenarioLenses(items, missingItems, riskItems);
  const overview =
    allRawScenarioItems.length > 0
      ? `本次共识别 ${allRawScenarioItems.length} 个购车问题，其中品牌已进入 ${hitCount} 个，缺席高价值场景 ${missingItems.length} 个，高风险场景 ${riskItems.length} 个。`
      : undefined;

  return {
    title: '有效场景',
    description: '有效场景指品牌已经进入 AI 回答，说明这类问题里已经建立了基础存在感。',
    summary: explicit?.summary || buildScenarioSemanticSummary('品牌当前已经进入的场景', items),
    overview,
    items,
    missing_items: missingItems,
    risk_items: riskItems,
    missing_summary: buildScenarioSemanticSummary('品牌当前缺席的高价值场景', missingItems),
    risk_summary: buildScenarioSemanticSummary('当前高风险场景', riskItems),
    semantic_lenses: semanticLenses,
  };
}

function normalizeCompetitorBattle(data: ReportCanvasContent['data']): CompetitorBattleData {
  const explicit = data.report_v2?.competitorBattle ?? data.competitor_battle;
  const competitorDeep = isRecord(data.competitor_deep_analysis) ? data.competitor_deep_analysis : undefined;

  const explicitCards = [
    ...(explicit?.summary_cards ?? []),
    ...((explicit?.summary_cards?.length ?? 0) === 0 ? (explicit?.items ?? []) : []),
  ]
    .map((item) => normalizeCompetitorCard(item as unknown as UnknownRecord))
    .filter((item): item is CompetitorBattleSummaryCard => Boolean(item));
  const rawCards = toRecordArray(data.competitor_battles)
    .map(normalizeCompetitorCard)
    .filter((item): item is CompetitorBattleSummaryCard => Boolean(item));
  const legacyCards = toRecordArray(competitorDeep?.comparison_matrix)
    .map(normalizeCompetitorCard)
    .filter((item): item is CompetitorBattleSummaryCard => Boolean(item));

  const explicitItems = (explicit?.items ?? [])
    .map((item, index) => normalizeCompetitorItem(item as unknown as UnknownRecord, `争夺场景 ${index + 1}`))
    .filter((item): item is CompetitorBattleItem => Boolean(item));
  const rawItems = toRecordArray(data.scenario_matrix)
    .map((item, index) => normalizeCompetitorItem(item, `争夺场景 ${index + 1}`))
    .filter((item): item is CompetitorBattleItem => item !== null && (item.competitors_present?.length ?? 0) > 0);

  return {
    title: explicit?.title || '竞品争夺',
    description: explicit?.description || '这些关键场景里，品牌正在和竞品争夺用户心智。',
    overview: explicit?.overview || readString(competitorDeep ?? {}, 'overview'),
    summary_cards: explicitCards.length > 0 ? explicitCards : rawCards.length > 0 ? rawCards : legacyCards,
    items: explicitItems.length > 0 ? explicitItems : rawItems,
    differentiation_strategy:
      explicit?.differentiation_strategy || readString(competitorDeep ?? {}, 'differentiation_strategy', 'differentiationStrategy'),
  };
}

function normalizeRisks(data: ReportCanvasContent['data']): RiskSectionData {
  const explicit = data.report_v2?.risks ?? data.risk_section;
  const explicitItems = (explicit?.items ?? [])
    .map((item) => normalizeRiskItem(item as unknown as UnknownRecord))
    .filter((item): item is ReportRiskItem => Boolean(item));
  const rawItems = toRecordArray(data.risk_map)
    .map(normalizeRiskItem)
    .filter((item): item is ReportRiskItem => Boolean(item));
  const legacyItems = toRecordArray(data.risk_alerts)
    .map(normalizeRiskItem)
    .filter((item): item is ReportRiskItem => Boolean(item));
  const items = explicitItems.length > 0 ? explicitItems : rawItems.length > 0 ? rawItems : legacyItems;
  const highRiskCount = items.filter((item) => item.severity === 'high').length;

  return {
    title: '缺席高价值场景与高风险场景',
    description: '缺席高价值场景，指购买意图强但品牌没进回答；高风险场景，指已经出现竞品抢位、品牌缺席或官网证据链薄弱。',
    summary:
      explicit?.summary ||
      (items.length > 0 ? `当前识别 ${items.length} 个需要补强的场景，其中 ${highRiskCount} 个属于高风险。` : undefined),
    items,
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

function normalizeActionQueue(data: ReportCanvasContent['data']): ActionQueueData {
  const explicit = data.report_v2?.actionQueue ?? data.action_queue_section;
  const explicitItems = (explicit?.items ?? [])
    .map((item) => normalizeActionItem(item as unknown as UnknownRecord))
    .filter((item): item is ActionQueueItem => Boolean(item));
  const rawItems = toRecordArray(data.action_queue)
    .map((item) => normalizeActionItem(item))
    .filter((item): item is ActionQueueItem => Boolean(item));
  const actionableItems = toRecordArray(data.actionable_recommendations)
    .map((item) => normalizeActionItem(item))
    .filter((item): item is ActionQueueItem => Boolean(item));
  const recommendationItems = (data.recommendations ?? [])
    .map((item) =>
      normalizeActionItem({
        priority: item.priority,
        title: item.title,
        target: item.expected_impact || item.rationale,
        expected_impact: item.expected_impact,
        difficulty: item.difficulty,
        timeline: item.timeline,
      })
    )
    .filter((item): item is ActionQueueItem => Boolean(item));

  const actionPlan = isRecord(data.action_plan) ? data.action_plan : undefined;
  const actionPlanItems = [
    ...toStringArray(actionPlan?.short_term).map((action) => normalizeActionItem({ priority: 'P1', title: action, action, target: '短期推进' })),
    ...toStringArray(actionPlan?.medium_term).map((action) => normalizeActionItem({ priority: 'P2', title: action, action, target: '中期推进' })),
    ...toStringArray(actionPlan?.long_term).map((action) => normalizeActionItem({ priority: 'P3', title: action, action, target: '长期推进' })),
  ].filter((item): item is ActionQueueItem => Boolean(item));

  const items = dedupeActionItems(
    explicitItems.length > 0
      ? explicitItems
      : rawItems.length > 0
      ? rawItems
      : [...actionableItems, ...recommendationItems, ...actionPlanItems]
  );

  return {
    title: explicit?.title || '下一步优化',
    description: explicit?.description || '优先处理这些动作，才能改善接下来的战况。',
    summary:
      explicit?.summary ||
      (items.length > 0 ? `已整理 ${items.length} 条优先动作，建议从高优先级项开始推进。` : undefined),
    items,
  };
}

function normalizeSummary(
  data: ReportCanvasContent['data'],
  scenarios: ScenarioCoverageData,
  risks: RiskSectionData,
  sources: SourceSectionData
): ReportSummaryData {
  const explicit = data.report_v2?.summary ?? data.report_summary;
  const summaryMetrics = isRecord(data.summary_metrics) ? data.summary_metrics : undefined;
  const explicitHighlights = (explicit?.highlights ?? []).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));
  const keyFindings = toStringArray(data.key_findings).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));

  const fallbackMetrics = createSummaryMetrics(
    data.metrics as Record<string, unknown> | undefined,
    scenarios,
    risks,
    sources
  );
  const metrics = mergeSummaryMetrics(explicit?.metrics, fallbackMetrics);

  const summaryText =
    sanitizeNarrativeText(explicit?.summary) ||
    keyFindings[0] ||
    undefined;
  const statusSummary =
    sanitizeNarrativeText(explicit?.status_summary) ||
    buildStatusSummary(scenarios, risks, metrics, summaryMetrics) ||
    summaryText;

  return {
    title: explicit?.title || '核心指标',
    description: explicit?.description || '先看这份报告到底在统计什么：品牌进入了哪些购车场景、官网有没有进引用链、还有哪些高价值问题没打进去。',
    summary: summaryText,
    status_summary: statusSummary,
    highlights:
      explicitHighlights.length > 0
        ? explicitHighlights
        : [
            scenarios.summary,
            scenarios.missing_items?.length
              ? buildScenarioSemanticSummary('品牌当前缺席的高价值场景', scenarios.missing_items)
              : undefined,
            scenarios.risk_items?.length
              ? buildScenarioSemanticSummary('当前高风险场景', scenarios.risk_items)
              : undefined,
          ].filter((item): item is string => Boolean(item)),
    metrics,
  };
}

function formatSubtitle(data: ReportCanvasContent['data']): string | undefined {
  const explicitSubtitle = sanitizeNarrativeText(data.subtitle);
  if (explicitSubtitle) {
    return explicitSubtitle;
  }

  const brandName = toStringValue(data.brand_name);
  const analysisPeriod = toStringValue(data.analysis_period);
  const platformScope = data.platform_scope && data.platform_scope.length > 0 ? data.platform_scope.join(' / ') : undefined;

  const parts = [
    brandName && analysisPeriod ? `${brandName} 在 ${analysisPeriod} 的 AI 品牌战况分析` : undefined,
    platformScope ? `覆盖平台：${platformScope}` : undefined,
  ].filter((value): value is string => Boolean(value));

  return parts.length > 0 ? parts.join(' · ') : undefined;
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
    return explicit;
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
  const groupedCount = new Set(
    brandMentions.map((item) => item.scenario_id || item.scenario_label).filter((value): value is string => Boolean(value))
  ).size;
  const summaryRecord = isRecord(brandPayload?.summary) ? brandPayload.summary : {};

  return {
    title: '提及率分析',
    description: '这里重点看品牌进入了哪些问题、提到了什么产品、涉及什么场景，以及同场竞品是谁。',
    mention_rate: mentionRate,
    mention_count: groupedCount,
    sentiment_summary: {
      positive: readNumber(summaryRecord, 'positive') ?? 0,
      neutral: readNumber(summaryRecord, 'neutral') ?? 0,
      negative: readNumber(summaryRecord, 'negative') ?? 0,
    },
    brand_mentions: brandMentions,
    competitor_mentions: competitorMentions,
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
    description: '把进入答案的品牌内容和头部引用来源放在一起看，重点判断官网有没有真正进入证据链。',
    content_citation_rate: explicit?.content_citation_rate ?? contentCitationRate,
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

function normalizeInsightsForReport(
  scenarios: ScenarioCoverageData,
  mentions: ReportMentionSectionData
): InsightSectionData {
  const effectiveItems = scenarios.items ?? [];
  const missingItems = scenarios.missing_items ?? [];
  const riskItems = scenarios.risk_items ?? [];
  const officialCoveredCount = effectiveItems.filter((item) => item.official_citation_present).length;
  const mentionPlatforms = uniqueStrings((mentions.brand_mentions ?? []).map((item) => item.platform));

  const strengths: NonNullable<InsightSectionData['strengths']> = [];
  if (effectiveItems.length > 0) {
    strengths.push({
      title: '品牌已经站住的场景',
      scenario: summarizeSemanticTags(
        effectiveItems.flatMap((item) => item.semantic_tags?.usages ?? []),
        '使用场景未明确'
      ),
      evidence:
        buildScenarioSemanticSummary('品牌已经站住的高价值场景', effectiveItems) ||
        '品牌已经在部分关键购车问题里建立基础存在感。',
      platforms: mentionPlatforms,
      official_citation_present: officialCoveredCount > 0,
      improvement_hint:
        officialCoveredCount > 0
          ? '优先打开置信度分析，确认这些已站住场景里到底是哪些官网页面和第三方内容在支撑优势，再沿着同一主题继续扩写。'
          : '这些场景已经有回答存在感，但官网还没稳定进入引用链，下一步优先补官网版本和证据链。',
    });
    strengths.push({
      title: '目前吃到的主要人群与预算带',
      scenario: summarizeSemanticTags(
        effectiveItems.flatMap((item) => item.semantic_tags?.audiences ?? []),
        '泛人群'
      ),
      evidence: `当前有效覆盖主要落在 ${summarizeSemanticTags(
        effectiveItems.flatMap((item) => item.semantic_tags?.audiences ?? []),
        '泛人群'
      )}，预算带集中在 ${summarizeSemanticTags(
        effectiveItems.flatMap((item) => item.semantic_tags?.prices ?? []),
        '价格未明确'
      )}。`,
      improvement_hint: '建议继续沿着这些已经有效的人群与预算带扩写相邻问题，把单点回答优势做成连续覆盖。',
    });
  }

  const weaknesses: NonNullable<InsightSectionData['weaknesses']> = [];
  if (missingItems.length > 0) {
    weaknesses.push({
      title: '仍缺席的高价值场景',
      scenario: summarizeSemanticTags(
        missingItems.flatMap((item) => item.semantic_tags?.usages ?? []),
        '高价值场景'
      ),
      evidence:
        buildScenarioSemanticSummary('品牌缺席的高价值场景', missingItems) ||
        '仍有高价值场景没有进入回答。',
      improvement_hint:
        '先打开场景细分分析，把这些缺席问题拆到具体人群、预算和决策点，再决定优先补 FAQ、对比页还是场景案例。',
    });
  }
  if (riskItems.length > 0) {
    weaknesses.push({
      title: '高风险场景还没打透',
      scenario: summarizeSemanticTags(
        riskItems.flatMap((item) => item.semantic_tags?.features ?? []),
        '关键决策点'
      ),
      evidence:
        buildScenarioSemanticSummary('当前高风险场景', riskItems) ||
        '部分场景虽然有提及，但官网证据链或竞争优势仍不稳定。',
      improvement_hint:
        '建议先看这些场景里竞品覆盖了什么，再回到置信度分析确认哪些页面和来源在支撑竞争对手。',
    });
  }

  return {
    title: '当前优势与补强',
    description: '先看已经站住的高价值场景，再看最该补的风险场景，并直接引导到置信度分析或场景细分分析。',
    summary:
      strengths.length > 0 || weaknesses.length > 0
        ? '优势和补强都直接基于上面的场景统计结果来写，不再脱离事实单独胡写。'
        : '当前还没有足够的场景统计结果可形成优势与补强结论。',
    strengths,
    weaknesses,
  };
}

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
  const scenarios = normalizeScenarioCoverage(data);
  const competitorBattle = normalizeCompetitorBattle(data);
  const risks = normalizeRisks(data);
  const mentions = normalizeMentions(data);
  const sources = normalizeSourcesForReport(data, mentions);
  const insights = normalizeInsightsForReport(scenarios, mentions);
  const actionQueue = normalizeActionQueue(data);
  const summary = normalizeSummary(data, scenarios, risks, sources);
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
    competitorBattle,
    risks,
    mentions,
    sources,
    insights,
    actionQueue,
  };
}










