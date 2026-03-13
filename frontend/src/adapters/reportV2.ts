import type {
  ActionQueueData,
  ActionQueueItem,
  CitationAnalysis,
  CitationDomainItem,
  CompetitorBattleData,
  CompetitorBattleItem,
  CompetitorBattleSummaryCard,
  InsightSectionData,
  InsightSectionItem,
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

  return {
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
  };
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

function buildSummaryMetricsFromRoot(summaryMetrics: UnknownRecord | undefined): ReportV2Metric[] {
  if (!summaryMetrics) {
    return [];
  }

  return [
    {
      id: 'brand_mention_rate',
      label: '品牌提及率',
      value: readNumber(summaryMetrics, 'brand_mention_rate', 'brandMentionRate'),
      unit: 'ratio',
      description: '品牌在 AI 回答中被直接提到的频率。',
    },
    {
      id: 'official_citation_rate',
      label: '内容引用率',
      value: readNumber(summaryMetrics, 'official_citation_rate', 'officialCitationRate'),
      unit: 'ratio',
      description: '品牌相关内容是否进入 AI 答案的证据链。',
    },
    {
      id: 'platform_coverage_count',
      label: '覆盖平台数',
      value: readNumber(summaryMetrics, 'platform_coverage_count', 'platformCoverageCount'),
      description: '品牌已进入回答的平台数量。',
    },
    {
      id: 'scenario_hit_count',
      label: '被提及问题',
      value: readNumber(summaryMetrics, 'scenario_hit_count', 'scenarioHitCount'),
      description: '当前有多少个问题的回答提到了品牌。',
    },
    {
      id: 'missing_high_value_scenario_count',
      label: '缺席高价值场景',
      value: readNumber(summaryMetrics, 'missing_high_value_scenario_count', 'missingHighValueScenarioCount'),
      description: '高价值但品牌仍未进入回答的场景数。',
    },
    {
      id: 'high_risk_scenario_count',
      label: '高风险场景',
      value: readNumber(summaryMetrics, 'high_risk_scenario_count', 'highRiskScenarioCount'),
      description: '当前需要优先处理的高风险问题数。',
    },
  ];
}

function createSummaryMetrics(
  metrics: Record<string, unknown> | undefined,
  scenarios: ScenarioCoverageData,
  risks: RiskSectionData,
  sources: SourceSectionData,
  summaryMetrics: UnknownRecord | undefined
): ReportV2Metric[] {
  const scenarioItems = scenarios.items ?? [];
  const riskItems = risks.items ?? [];
  const citationAnalysis = sources.citation_analysis;

  const brandMentionRate = normalizePercent(
    toNumberValue(pickMetricValue(metrics, ['brand_mention_rate', 'mention_rate', 'mentionRate']))
  );
  const contentCitationRate =
    sources.content_citation_rate ??
    sources.official_citation_rate ??
    normalizePercent(toNumberValue(pickMetricValue(metrics, ['official_citation_rate', 'citation_rate'])));
  const inferredPlatformCoverageCount =
    uniqueStrings(scenarioItems.flatMap((item) => item.present_platforms ?? [])).length ||
    Object.keys(citationAnalysis?.platform_citation_stats ?? {}).length ||
    undefined;
  const platformCoverageCount =
    toNumberValue(pickMetricValue(metrics, ['platform_coverage_count', 'coverage_platform_count', 'platform_count'])) ??
    inferredPlatformCoverageCount;
  const scenarioTotal =
    toNumberValue(pickMetricValue(metrics, ['scenario_total', 'total_scenarios'])) ??
    (scenarioItems.length > 0 ? scenarioItems.length : undefined);
  const inferredScenarioHitCount = scenarioItems.filter((item) => item.brand_present).length || undefined;
  const scenarioHitCount =
    toNumberValue(pickMetricValue(metrics, ['scenario_hit_count', 'effective_scenario_count'])) ??
    inferredScenarioHitCount;
  const inferredMissingHighValueScenarioCount =
    riskItems.filter((item) => item.risk_type === 'missing_presence').length || undefined;
  const missingHighValueScenarioCount =
    toNumberValue(
      pickMetricValue(metrics, ['missing_high_value_scenario_count', 'missing_scenario_count'])
    ) ?? inferredMissingHighValueScenarioCount;
  const inferredHighRiskScenarioCount =
    riskItems.filter((item) => item.severity === 'high').length || undefined;
  const highRiskScenarioCount =
    toNumberValue(pickMetricValue(metrics, ['high_risk_scenario_count'])) ?? inferredHighRiskScenarioCount;

  const fallbackMetrics: ReportV2Metric[] = [
    {
      id: 'brand_mention_rate',
      label: '品牌提及率',
      value: brandMentionRate,
      unit: brandMentionRate !== undefined ? '%' : undefined,
      description: '品牌在 AI 回答中被直接提到的频率。',
      status:
        brandMentionRate === undefined ? 'neutral' : brandMentionRate >= 50 ? 'good' : brandMentionRate >= 20 ? 'warning' : 'risk',
    },
    {
      id: 'official_citation_rate',
      label: '内容引用率',
      value: contentCitationRate,
      unit: contentCitationRate !== undefined ? '%' : undefined,
      description: '品牌相关内容是否进入 AI 答案的证据链。',
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
      id: 'platform_coverage_count',
      label: '覆盖平台数',
      value: platformCoverageCount,
      description: '品牌已进入回答的平台数量。',
      status: platformCoverageCount === undefined ? 'neutral' : platformCoverageCount >= 3 ? 'good' : 'warning',
    },
    {
      id: 'scenario_hit_count',
      label: '被提及问题',
      value: scenarioHitCount,
      description:
        scenarioTotal !== undefined ? `当前识别问题总数 ${scenarioTotal}。` : '当前有多少个问题的回答提到了品牌。',
      status: scenarioHitCount === undefined ? 'neutral' : scenarioHitCount >= 3 ? 'good' : 'warning',
    },
    {
      id: 'missing_high_value_scenario_count',
      label: '缺席高价值场景',
      value: missingHighValueScenarioCount,
      description: '高价值但品牌仍未进入回答的场景数。',
      status:
        missingHighValueScenarioCount === undefined
          ? 'neutral'
          : missingHighValueScenarioCount === 0
          ? 'good'
          : missingHighValueScenarioCount <= 2
          ? 'warning'
          : 'risk',
    },
    {
      id: 'high_risk_scenario_count',
      label: '高风险场景',
      value: highRiskScenarioCount,
      description: '当前需要优先处理的高风险问题数。',
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

  const rootMetrics = buildSummaryMetricsFromRoot(summaryMetrics);
  if (!summaryMetrics || rootMetrics.length === 0) {
    return fallbackMetrics;
  }

  const fallbackById = new Map(fallbackMetrics.map((metric) => [metric.id, metric]));
  return rootMetrics.map((metric) => {
    const fallback = fallbackById.get(metric.id);
    return {
      ...fallback,
      ...metric,
      value: metric.value !== undefined && metric.value !== null ? metric.value : fallback?.value,
      unit: metric.value !== undefined && metric.value !== null ? metric.unit : fallback?.unit,
      description: metric.description || fallback?.description,
      status: metric.value !== undefined && metric.value !== null ? metric.status || fallback?.status : fallback?.status,
    } satisfies ReportV2Metric;
  });
}

function buildStatusSummary(
  scenarios: ScenarioCoverageData,
  risks: RiskSectionData,
  metrics: ReportV2Metric[],
  summaryMetrics: UnknownRecord | undefined
): string | undefined {
  const rootSummary = summaryMetrics ? sanitizeNarrativeText(readString(summaryMetrics, 'status_summary', 'statusSummary')) : undefined;
  if (rootSummary) {
    return rootSummary;
  }

  const metricMap = new Map(metrics.map((metric) => [metric.id, metric.value]));
  const scenarioHitCount =
    readNumber(summaryMetrics ?? {}, 'scenario_hit_count', 'scenarioHitCount') ??
    metricMap.get('scenario_hit_count');
  const missingCount =
    readNumber(summaryMetrics ?? {}, 'missing_high_value_scenario_count', 'missingHighValueScenarioCount') ??
    metricMap.get('missing_high_value_scenario_count');
  const platformCount =
    readNumber(summaryMetrics ?? {}, 'platform_coverage_count', 'platformCoverageCount') ??
    metricMap.get('platform_coverage_count');
  const scenarioTotal =
    readNumber(summaryMetrics ?? {}, 'scenario_total', 'scenarioTotal') ??
    scenarios.items?.length;
  const highRiskCount =
    readNumber(summaryMetrics ?? {}, 'high_risk_scenario_count', 'highRiskScenarioCount') ??
    risks.items?.filter((item) => item.severity === 'high').length;

  if (
    scenarioHitCount === undefined &&
    missingCount === undefined &&
    platformCount === undefined &&
    scenarioTotal === undefined &&
    highRiskCount === undefined
  ) {
    return undefined;
  }

  return `当前品牌已覆盖 ${scenarioHitCount ?? '--'} / ${scenarioTotal ?? '--'} 个场景，覆盖 ${platformCount ?? '--'} 个平台，仍有 ${missingCount ?? '--'} 个高价值场景缺席，高风险问题 ${highRiskCount ?? '--'} 个。`;
}

function normalizeScenarioCoverage(data: ReportCanvasContent['data']): ScenarioCoverageData {
  const explicit = data.report_v2?.scenarioCoverage ?? data.scenario_coverage;
  const explicitItems = (explicit?.items ?? [])
    .map((item, index) => normalizeScenarioItem(item as unknown as UnknownRecord, `场景 ${index + 1}`))
    .filter((item): item is ScenarioCoverageItem => Boolean(item));

  const rawScenarioItems = toRecordArray(data.scenario_matrix)
    .map((item, index) => normalizeScenarioItem(item, `场景 ${index + 1}`))
    .filter((item): item is ScenarioCoverageItem => item !== null && item.brand_present === true);

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

  return {
    title: explicit?.title || '有效场景',
    description: explicit?.description || '这些场景里，品牌已经建立了有效存在感。',
    summary: explicit?.summary || (items.length > 0 ? `已识别 ${hitCount} 个品牌已进入回答的场景。` : undefined),
    items,
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
    title: explicit?.title || '缺口与风险',
    description: explicit?.description || '这些缺口正在影响品牌被提及和被引用。',
    summary:
      explicit?.summary ||
      (items.length > 0 ? `当前识别 ${items.length} 个风险点，其中 ${highRiskCount} 个为高风险。` : undefined),
    items,
  };
}

function normalizeSources(data: ReportCanvasContent['data']): SourceSectionData {
  const explicit = data.report_v2?.sources ?? data.source_section;
  const rawSourceOverview = isRecord(data.source_overview) ? data.source_overview : undefined;
  const citationAnalysis =
    explicit?.citation_analysis ??
    data.citation_analysis ??
    buildCitationAnalysisFromSourceOverview(rawSourceOverview);
  const officialCitationRate =
    explicit?.official_citation_rate ??
    (citationAnalysis ? citationAnalysis.official_share : undefined) ??
    normalizePercent(readNumber(rawSourceOverview ?? {}, 'official_citation_rate', 'officialCitationRate')) ??
    normalizePercent(toNumberValue(pickMetricValue(data.metrics as Record<string, unknown> | undefined, ['official_citation_rate'])));

  return {
    title: explicit?.title || '信息源分析',
    description: explicit?.description || 'AI 平台正在引用哪些来源来形成回答。',
    summary: explicit?.summary || readString(rawSourceOverview ?? {}, 'note'),
    official_citation_rate: officialCitationRate,
    official_top_titles: uniqueStrings([
      ...toStringArray(readField(rawSourceOverview ?? {}, 'official_top_titles', 'officialTopTitles')),
      ...(citationAnalysis?.top_domains ?? [])
        .filter((item) => item.is_official)
        .flatMap((item) => item.sample_titles ?? []),
    ]),
    citation_analysis: citationAnalysis,
  };
}

function mergeSummaryMetrics(
  explicitMetrics: ReportV2Metric[] | undefined,
  fallbackMetrics: ReportV2Metric[]
): ReportV2Metric[] {
  if (!explicitMetrics || explicitMetrics.length === 0) {
    return fallbackMetrics;
  }

  const fallbackById = new Map(fallbackMetrics.map((metric) => [metric.id, metric]));

  return explicitMetrics.map((metric) => {
    const fallback = fallbackById.get(metric.id);
    return {
      ...fallback,
      ...metric,
      value: metric.value !== undefined && metric.value !== null ? metric.value : fallback?.value,
      unit: metric.value !== undefined && metric.value !== null ? metric.unit : fallback?.unit,
      description: metric.description || fallback?.description,
      status: metric.value !== undefined && metric.value !== null ? metric.status || fallback?.status : fallback?.status,
    } satisfies ReportV2Metric;
  });
}

function normalizeInsightItem(record: UnknownRecord, fallbackTitle: string): InsightSectionItem | null {
  const title = readString(record, 'title', 'label', 'scenario_label', 'scenarioLabel') || fallbackTitle;
  if (!title) {
    return null;
  }

  return {
    title,
    scenario: readString(record, 'scenario', 'scenario_label', 'scenarioLabel'),
    evidence: readString(record, 'evidence', 'description', 'reason'),
    platforms: readStringList(record, 'platforms', 'present_platforms', 'presentPlatforms'),
    improvement_hint: readString(record, 'improvement_hint', 'improvementHint', 'mitigation_hint', 'mitigationHint'),
    sentiment: readString(record, 'sentiment'),
    citation_domains: readStringList(record, 'citation_domains', 'citationDomains'),
    citation_titles: readStringList(record, 'citation_titles', 'citationTitles'),
    official_citation_present: readBoolean(record, 'official_citation_present', 'officialCitationPresent'),
  };
}

function buildSentimentInsightItems(data: ReportCanvasContent['data']) {
  const payload = isRecord(data.mention_sentiment_analysis)
    ? data.mention_sentiment_analysis
    : isRecord(data.report_data) && isRecord(data.report_data.mention_sentiment_analysis)
    ? (data.report_data.mention_sentiment_analysis as UnknownRecord)
    : undefined;

  const brandPayload = payload && isRecord(payload.brand) ? (payload.brand as UnknownRecord) : undefined;
  const brandItems = toRecordArray(brandPayload?.items);

  const strengths = brandItems
    .filter((item) => readString(item, 'sentiment') === 'positive')
    .slice(0, 3)
    .map((item, index) =>
      normalizeInsightItem(
        {
          title: `${readString(item, 'scenario_label', 'scenarioLabel') || `优势 ${index + 1}`}中品牌被正向提及`,
          scenario: readString(item, 'scenario_label', 'scenarioLabel'),
          evidence:
            readString(item, 'evidence') ||
            `${readString(item, 'platform') || 'AI 平台'} 对品牌给出了正向表述。`,
          platforms: readStringList(item, 'platform'),
          sentiment: 'positive',
          citation_domains: readStringList(item, 'citation_domains', 'citationDomains'),
          citation_titles: readStringList(item, 'citation_titles', 'citationTitles'),
          official_citation_present: readBoolean(item, 'official_citation_present', 'officialCitationPresent'),
        },
        `优势 ${index + 1}`
      )
    )
    .filter((item): item is InsightSectionItem => Boolean(item));

  const weaknesses = brandItems
    .filter((item) => ['neutral', 'negative'].includes(readString(item, 'sentiment') || ''))
    .slice(0, 4)
    .map((item, index) => {
      const sentiment = readString(item, 'sentiment') || 'neutral';
      const sentimentText = sentiment === 'negative' ? '负向' : '中性';
      return normalizeInsightItem(
        {
          title: `${readString(item, 'scenario_label', 'scenarioLabel') || `短板 ${index + 1}`}中品牌呈${sentimentText}提及`,
          scenario: readString(item, 'scenario_label', 'scenarioLabel'),
          evidence:
            readString(item, 'evidence') ||
            `${readString(item, 'platform') || 'AI 平台'} 对品牌呈${sentimentText}提及，建议补强证据和内容表达。`,
          platforms: readStringList(item, 'platform'),
          sentiment,
          citation_domains: readStringList(item, 'citation_domains', 'citationDomains'),
          citation_titles: readStringList(item, 'citation_titles', 'citationTitles'),
          official_citation_present: readBoolean(item, 'official_citation_present', 'officialCitationPresent'),
          improvement_hint: '优先补强该场景的官网证据、FAQ 和对比型内容。',
        },
        `短板 ${index + 1}`
      );
    })
    .filter((item): item is InsightSectionItem => Boolean(item));

  return { strengths, weaknesses };
}

function normalizeInsights(data: ReportCanvasContent['data']): InsightSectionData {
  const explicit = data.report_v2?.insights ?? data.insight_section;
  const explicitStrengths = (explicit?.strengths ?? [])
    .map((item, index) => normalizeInsightItem(item as unknown as UnknownRecord, `优势 ${index + 1}`))
    .filter((item): item is InsightSectionItem => Boolean(item));
  const explicitWeaknesses = (explicit?.weaknesses ?? [])
    .map((item, index) => normalizeInsightItem(item as unknown as UnknownRecord, `短板 ${index + 1}`))
    .filter((item): item is InsightSectionItem => Boolean(item));

  const strengths = (explicitStrengths.length > 0
    ? explicitStrengths
    : toRecordArray(data.strengths)
        .map((item, index) => normalizeInsightItem(item, `优势 ${index + 1}`))
        .filter((item): item is InsightSectionItem => Boolean(item))
  );

  const weaknesses = (explicitWeaknesses.length > 0
    ? explicitWeaknesses
    : toRecordArray(data.weaknesses)
        .map((item, index) => normalizeInsightItem(item, `短板 ${index + 1}`))
        .filter((item): item is InsightSectionItem => Boolean(item))
  );

  const fallbackSummary = [
    strengths.length > 0 ? `已识别 ${strengths.length} 条当前优势` : undefined,
    weaknesses.length > 0 ? `${weaknesses.length} 条当前短板待补强` : undefined,
  ].filter((item): item is string => Boolean(item)).join('，');

  return {
    title: explicit?.title || '洞察',
    description: explicit?.description || '先看品牌当前做得好的地方，以及还需要补强的地方。',
    summary: explicit?.summary || fallbackSummary || undefined,
    strengths,
    weaknesses,
  };
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
  const legacyHighlights = [
    ...keyFindings,
    ...(data.insights ?? []).map((item) => sanitizeNarrativeText(item.title)).filter((item): item is string => Boolean(item)),
  ];

  const fallbackMetrics = createSummaryMetrics(
    data.metrics as Record<string, unknown> | undefined,
    scenarios,
    risks,
    sources,
    summaryMetrics
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
    description: explicit?.description || '先看品牌在提及、内容引用和风险上的核心表现。',
    summary: summaryText,
    status_summary: statusSummary,
    highlights: explicitHighlights.length > 0 ? explicitHighlights : legacyHighlights.slice(0, 4),
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
    description: '先看品牌在哪些问题进入了答案，再看四个平台的提及状态和语气差异。',
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
    title: '内容引用分析',
    description: '把进入答案的品牌内容、引用来源和证据链放在一起看。',
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
  mentions: ReportMentionSectionData,
  risks: RiskSectionData
): InsightSectionData {
  const groupedByScenario = new Map<
    string,
    {
      scenario: string;
      platforms: string[];
      positive: number;
      negative: number;
      neutral: number;
      evidence?: string;
      citationDomains: string[];
      officialCitationPresent: boolean;
    }
  >();
  const competitorsByScenario = new Map<
    string,
    {
      scenario: string;
      competitors: string[];
      platforms: string[];
    }
  >();

  for (const item of mentions.brand_mentions ?? []) {
    const key = item.scenario_id || item.scenario_label;
    if (!key) continue;
    if (!groupedByScenario.has(key)) {
      groupedByScenario.set(key, {
        scenario: item.scenario_label,
        platforms: [],
        positive: 0,
        negative: 0,
        neutral: 0,
        evidence: item.evidence,
        citationDomains: [],
        officialCitationPresent: false,
      });
    }
    const row = groupedByScenario.get(key)!;
    if (item.platform && !row.platforms.includes(item.platform)) row.platforms.push(item.platform);
    if (item.sentiment === 'positive') row.positive += 1;
    else if (item.sentiment === 'negative') row.negative += 1;
    else row.neutral += 1;
    row.evidence = row.evidence || item.evidence;
    row.citationDomains = uniqueStrings([...row.citationDomains, ...(item.citation_domains ?? [])]);
    row.officialCitationPresent = row.officialCitationPresent || Boolean(item.official_citation_present);
  }

  for (const item of mentions.competitor_mentions ?? []) {
    const key = item.scenario_id || item.scenario_label;
    if (!key) continue;
    if (!competitorsByScenario.has(key)) {
      competitorsByScenario.set(key, {
        scenario: item.scenario_label,
        competitors: [],
        platforms: [],
      });
    }
    const row = competitorsByScenario.get(key)!;
    row.competitors = uniqueStrings([...row.competitors, item.competitor]);
    row.platforms = uniqueStrings([...row.platforms, item.platform]);
  }

  const strongestScenario = [...groupedByScenario.values()]
    .filter((item) => item.positive > 0 || item.officialCitationPresent || item.platforms.length > 1)
    .sort(
      (a, b) =>
        b.platforms.length * 10 +
        b.positive * 3 +
        (b.officialCitationPresent ? 4 : 0) -
        (a.platforms.length * 10 + a.positive * 3 + (a.officialCitationPresent ? 4 : 0)),
    )[0];

  const strengths = strongestScenario
    ? [{
        title: strongestScenario.scenario,
        scenario: strongestScenario.scenario,
        evidence: strongestScenario.officialCitationPresent
          ? `这个场景里品牌已经稳定进入回答，并且已有品牌自有内容被引用，说明当前表达方式已经开始被 AI 采纳。`
          : `这个场景里品牌已经稳定进入回答，在 ${strongestScenario.platforms.length} 个平台出现，属于当前可继续放大的优势场景。`,
        platforms: strongestScenario.platforms,
        citation_domains: strongestScenario.citationDomains,
        official_citation_present: strongestScenario.officialCitationPresent,
        improvement_hint:
          '下一步建议：打开引用内容置信度报告，优先检查这个场景里哪些高置信度内容被采纳了，再围绕同一表述扩展到相邻问题，放大已有优势。',
      }]
    : [];

  const riskWeaknesses = (risks.items ?? [])
    .filter((item) => isMeaningfulQuestionLabel(item.scenario_label))
    .map((item) => {
      const key = item.risk_id || item.scenario_label || '';
      const competitors = competitorsByScenario.get(key)?.competitors || competitorsByScenario.get(item.scenario_label || '')?.competitors || [];
      const platforms = competitorsByScenario.get(key)?.platforms || competitorsByScenario.get(item.scenario_label || '')?.platforms || [];
      const competitorLabel = competitors.length > 0 ? competitors.join('、') : '竞品';

      let evidence = sanitizeCustomerText(item.reason) || sanitizeCustomerText(item.impact_summary) || '该场景已经出现明显竞争压力。';
      let improvementHint =
        '下一步建议：进入用户画像分析，拆开这个问题背后的人群、预算和使用场景，再围绕最有价值的细分场景补充对比页、FAQ 和案例内容。';

      if (item.risk_type === 'no_official_citation') {
        evidence = `品牌虽然已经被提及，但当前答案主要依赖第三方内容，官方信息链路还没有稳定进入回答。`;
        improvementHint =
          '下一步建议：先看置信度报告，确认当前被采纳的是哪些第三方高置信度内容；再把这些表达补成官网或自有内容版本，争取把引用链路收回到官方。';
      } else if (item.risk_type === 'competitor_substitution' || item.risk_type === 'missing_presence') {
        evidence = `${competitorLabel} 已经在这个场景先进入答案，品牌当前还没有稳定站住。`;
        improvementHint =
          '下一步建议：从用户画像里继续下钻，找到这个场景下真正被抢走的是哪类人群与需求，再针对对应细分场景补强内容和对比表达。';
      }

      return {
        title: item.scenario_label || '待补强问题',
        scenario: item.scenario_label,
        evidence,
        platforms,
        improvement_hint: improvementHint,
      };
    })
    .slice(0, 2);

  return {
    title: '当前优势与补强',
    description: '这里只保留最值得立刻行动的场景，直接对应你下一步该看置信度，还是该继续做用户画像下钻。',
    summary: '先守住已经站住的优势场景，再把有竞争压力的场景拆到更细的人群和需求层继续优化。',
    strengths,
    weaknesses: riskWeaknesses,
  };
}

export interface ReportViewModel {
  headline: string;
  subtitle?: string;
  updatedAt?: string;
  degradationNote?: string;
  isBaseline: boolean;
  summary: ReportSummaryData;
  mentions: ReportMentionSectionData;
  sources: SourceSectionData;
  insights: InsightSectionData;
}

export function buildReportViewModel(content: ReportCanvasContent): ReportViewModel {
  const data = content.data;
  const scenarios = normalizeScenarioCoverage(data);
  const risks = normalizeRisks(data);
  const mentions = normalizeMentions(data);
  const sources = normalizeSourcesForReport(data, mentions);
  const insights = normalizeInsightsForReport(mentions, risks);
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
    mentions,
    sources,
    insights,
  };
}










