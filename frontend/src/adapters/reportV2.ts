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
  buildBrandProductLabels,
  buildScenarioSemanticLenses,
  enrichScenarioItemSemantics,
  extractFactSentences,
  extractGenericProductMentions,
  extractProductMentions,
} from '@/lib/a5Semantic';
import { getSourceLabel } from '@/lib/sourceLabel';
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
    risk_reason_type: readString(record, 'risk_reason_type', 'riskReasonType'),
    risk_reason_summary: readString(record, 'risk_reason_summary', 'riskReasonSummary'),
    fact_basis: readStringList(record, 'fact_basis', 'factBasis'),
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

type MentionScenarioGroup = {
  key: string;
  question: string;
  platforms: string[];
  brandItems: ReportMentionItem[];
  competitorItems: ReportMentionItem[];
  sourceLabels: string[];
};

function groupMentionItemsByScenario(mentions: ReportMentionSectionData): MentionScenarioGroup[] {
  const groups = new Map<string, MentionScenarioGroup>();

  const ensureGroup = (item: ReportMentionItem) => {
    const key = item.scenario_id || item.scenario_label;
    const existing = groups.get(key);
    if (existing) {
      return existing;
    }

    const created: MentionScenarioGroup = {
      key,
      question: item.scenario_label,
      platforms: [],
      brandItems: [],
      competitorItems: [],
      sourceLabels: [],
    };
    groups.set(key, created);
    return created;
  };

  (mentions.brand_mentions ?? []).forEach((item) => {
    const group = ensureGroup(item);
    group.brandItems.push(item);
    group.platforms = uniqueStrings([...group.platforms, item.platform]);
    group.sourceLabels = uniqueStrings([
      ...group.sourceLabels,
      ...(item.citation_domains ?? []).map((domain) => getSourceLabel(domain, false) || domain),
    ]);
  });

  (mentions.competitor_mentions ?? []).forEach((item) => {
    const group = ensureGroup(item);
    group.competitorItems.push(item);
    group.platforms = uniqueStrings([...group.platforms, item.platform]);
    group.sourceLabels = uniqueStrings([
      ...group.sourceLabels,
      ...(item.citation_domains ?? []).map((domain) => getSourceLabel(domain, false) || domain),
    ]);
  });

  return [...groups.values()];
}

function dominantSentiment(items: ReportMentionItem[]): 'positive' | 'neutral' | 'negative' {
  const positive = items.filter((item) => item.sentiment === 'positive').length;
  const negative = items.filter((item) => item.sentiment === 'negative').length;
  if (positive > negative) return 'positive';
  if (negative > positive) return 'negative';
  return 'neutral';
}

function pickFactBasis(sentences: string[], fallbackEvidence: Array<string | undefined>): string[] {
  if (sentences.length > 0) {
    return sentences.slice(0, 2);
  }

  return uniqueStrings(fallbackEvidence.map(sanitizeCustomerText)).slice(0, 2);
}

function sanitizeEntityLabel(label: string): string {
  return label
    .replace(/^[与和及、，,\s]+/u, '')
    .replace(/\s+/g, ' ')
    .trim();
}

function buildBrandMentionLabels(group: MentionScenarioGroup, brandName?: string): string[] {
  const texts = [
    group.question,
    ...group.brandItems.map((item) => item.evidence || ''),
    ...group.brandItems.flatMap((item) => item.citation_titles ?? []),
  ];
  const genericProducts = extractGenericProductMentions(texts);
  const products = uniqueStrings([
    ...extractProductMentions(texts, uniqueStrings([brandName])),
    ...genericProducts.filter((item) => (brandName ? item.includes(brandName) : false)),
  ]).map(sanitizeEntityLabel);
  return buildBrandProductLabels(brandName, products).filter(Boolean);
}

function buildCompetitorMentionLabels(group: MentionScenarioGroup, brandName?: string): string[] {
  const competitorNames = uniqueStrings(group.competitorItems.map((item) => item.competitor));
  const texts = [
    group.question,
    ...group.competitorItems.map((item) => item.evidence || ''),
    ...group.competitorItems.flatMap((item) => item.citation_titles ?? []),
  ];
  const products = uniqueStrings([
    ...extractProductMentions(texts, competitorNames),
    ...extractGenericProductMentions(texts),
  ])
    .map(sanitizeEntityLabel)
    .filter((label) => !(brandName && label.includes(brandName)));

  const explicitProducts = products.filter((product) => competitorNames.some((name) => product.includes(name)));
  if (explicitProducts.length > 0) {
    return explicitProducts.slice(0, 6);
  }

  const questionProducts = extractGenericProductMentions([group.question])
    .map(sanitizeEntityLabel)
    .filter((label) => !(brandName && label.includes(brandName)));

  return uniqueStrings([
    ...competitorNames.map((name) => `${name}/未涉及具体型号`),
    ...questionProducts,
    ...products,
  ]).slice(0, 6);
}

function buildMentionFactBasis(
  evidences: string[],
  anchors: string[],
  fallbacks: Array<string | undefined>
): string[] {
  return pickFactBasis(extractFactSentences(evidences, anchors), fallbacks);
}

function buildMentionScenarioGroups(
  brandMentions: ReportMentionItem[],
  competitorMentions: ReportMentionItem[],
  brandName?: string
): ReportMentionScenarioGroup[] {
  return groupMentionItemsByScenario({
    brand_mentions: brandMentions,
    competitor_mentions: competitorMentions,
  })
    .map((group) => {
      const sentiment = dominantSentiment(group.brandItems);
      const brandLabels = buildBrandMentionLabels(group, brandName);
      const competitorLabels = buildCompetitorMentionLabels(group, brandName);
      const competitorNames = uniqueStrings(group.competitorItems.map((item) => item.competitor));
      const brandFacts = buildMentionFactBasis(
        group.brandItems.map((item) => item.evidence || ''),
        uniqueStrings([brandName, ...brandLabels]),
        group.brandItems.map((item) => item.evidence)
      );
      const competitorFacts = buildMentionFactBasis(
        group.competitorItems.map((item) => item.evidence || ''),
        uniqueStrings([...competitorNames, ...competitorLabels]).filter((label) => !(brandName && label.includes(brandName))),
        group.competitorItems.map((item) => item.evidence)
      );

      return {
        key: group.key,
        question: group.question,
        platforms: group.platforms,
        source_labels: group.sourceLabels,
        brand_count: group.brandItems.length,
        competitor_count: group.competitorItems.length,
        sentiment,
        brand_labels: brandLabels.length > 0 ? brandLabels : (brandName ? [`${brandName}/未涉及具体型号`] : []),
        competitor_labels: competitorLabels,
        brand_facts: brandFacts,
        competitor_facts: competitorFacts,
      } satisfies ReportMentionScenarioGroup;
    })
    .filter((group) => group.brand_count > 0);
}

function buildRiskItemsFromMentions(
  mentions: ReportMentionSectionData,
  scenarioMap: Map<string, ScenarioCoverageItem>,
  brandName?: string
): ScenarioCoverageItem[] {
  const mentionGroups =
    mentions.groups && mentions.groups.length > 0
      ? mentions.groups.map((group) => ({
          key: group.key,
          question: group.question,
          platforms: group.platforms,
          brandItems: (mentions.brand_mentions ?? []).filter(
            (item) => (item.scenario_id || item.scenario_label) === group.key
          ),
          competitorItems: (mentions.competitor_mentions ?? []).filter(
            (item) => (item.scenario_id || item.scenario_label) === group.key
          ),
          sourceLabels: group.source_labels,
        }))
      : groupMentionItemsByScenario(mentions);

  return mentionGroups.flatMap((group) => {
    const scenarioKey = group.question.trim().toLowerCase();
    const matched = scenarioMap.get(scenarioKey);
    const competitorNames = uniqueStrings(group.competitorItems.map((item) => item.competitor));
    const competitorDominantSentiment = dominantSentiment(group.competitorItems);
    const brandDominantSentiment = dominantSentiment(group.brandItems);

    const competitorAnchors = uniqueStrings([
      ...competitorNames,
      ...extractGenericProductMentions([
        group.question,
        ...group.competitorItems.map((item) => item.evidence || ''),
      ]),
    ]).filter((label) => !(brandName && label.includes(brandName)));

    const brandAnchors = uniqueStrings([
      brandName,
      ...extractGenericProductMentions([
        group.question,
        ...group.brandItems.map((item) => item.evidence || ''),
      ]).filter((label) => (brandName ? label.includes(brandName) : false)),
    ]);

    const items: ScenarioCoverageItem[] = [];

    if (competitorNames.length >= 3 && competitorDominantSentiment === 'positive') {
      const factBasis = pickFactBasis(
        extractFactSentences(
          group.competitorItems.map((item) => item.evidence || ''),
          competitorAnchors
        ),
        group.competitorItems.map((item) => item.evidence)
      );

      items.push(
        enrichScenarioItemSemantics({
          scenario_id: matched?.scenario_id || group.key,
          scenario_label: group.question,
          scenario_priority: 'high',
          brand_present: matched?.brand_present ?? group.brandItems.length > 0,
          present_platforms: uniqueStrings([
            ...(matched?.present_platforms ?? []),
            ...group.brandItems.map((item) => item.platform),
            ...group.competitorItems.map((item) => item.platform),
          ]),
          official_citation_present: matched?.official_citation_present,
          official_source_domains: matched?.official_source_domains ?? [],
          battle_status: 'competitor_crowding',
          evidence: `答案中同时正向提到 ${competitorNames.slice(0, 4).join('、')}。`,
          confidence: matched?.confidence,
          competitors_present: competitorNames,
          risk_reason_type: 'competitor_crowding',
          risk_reason_summary: `答案中同时出现 ${competitorNames.length} 个竞品，且整体提及倾向为正向。`,
          fact_basis: factBasis,
        })
      );
    }

    if (group.brandItems.length > 0 && brandDominantSentiment === 'negative') {
      const factBasis = pickFactBasis(
        extractFactSentences(
          group.brandItems.map((item) => item.evidence || ''),
          brandAnchors
        ),
        group.brandItems.map((item) => item.evidence)
      );

      items.push(
        enrichScenarioItemSemantics({
          scenario_id: matched?.scenario_id || `${group.key}-brand-negative`,
          scenario_label: group.question,
          scenario_priority: 'high',
          brand_present: true,
          present_platforms: uniqueStrings([
            ...(matched?.present_platforms ?? []),
            ...group.brandItems.map((item) => item.platform),
          ]),
          official_citation_present: matched?.official_citation_present,
          official_source_domains: matched?.official_source_domains ?? [],
          battle_status: 'negative_brand',
          evidence: `${brandName || '我方品牌'}在答案里出现负向提及。`,
          confidence: matched?.confidence,
          competitors_present: competitorNames,
          risk_reason_type: 'negative_brand',
          risk_reason_summary: `${brandName || '我方品牌'}在该问题中整体提及倾向为负向。`,
          fact_basis: factBasis,
        })
      );
    }

    return items;
  });
}

function buildScenarioMap(items: ScenarioCoverageItem[]): Map<string, ScenarioCoverageItem> {
  return new Map(
    items
      .filter((item) => item.scenario_label.trim())
      .map((item) => [item.scenario_label.trim().toLowerCase(), item] as const)
  );
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
    existing.risk =
      existing.risk ||
      item.battle_status === 'contested' ||
      item.battle_status === 'defend' ||
      item.battle_status === 'competitor_crowding' ||
      item.battle_status === 'negative_brand';
    recordMap.set(key, existing);
  });
  const records = [...recordMap.values()];
  return buildScenarioSemanticLenses(records);
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

function extractRiskItems(data: ReportCanvasContent['data']): ReportRiskItem[] {
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

  return explicitItems.length > 0 ? explicitItems : rawItems.length > 0 ? rawItems : legacyItems;
}

function createSummaryMetrics(
  metrics: Record<string, unknown> | undefined,
  scenarios: ScenarioCoverageData,
  mentions: ReportMentionSectionData,
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
      description: '回答里直接提到品牌的占比，先看品牌有没有进场。',
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
      description: '品牌已经进入回答的问题数，先看品牌在哪些购车场景里已经进场。',
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

function normalizeScenarioCoverage(
  data: ReportCanvasContent['data'],
  mentions: ReportMentionSectionData
): ScenarioCoverageData {
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
  ).filter((item) => item.brand_present === true);
  const scenarioMap = buildScenarioMap(allRawScenarioItems.length > 0 ? allRawScenarioItems : items);
  const riskCandidates = extractRiskItems(data);
  const missingItems = riskCandidates
    .filter((item) => item.risk_type === 'missing_presence')
    .map((item) => toRiskScenarioItem(item, scenarioMap));
  const riskItems = dedupeScenarioItems(
    buildRiskItemsFromMentions(mentions, scenarioMap, toStringValue(data.brand_name))
  );
  const semanticLenses = collectScenarioLenses(items, missingItems, riskItems);

  return {
    title: '场景覆盖',
    description: '把购车问题按人群、价格区间、产品特点和使用场景重新归纳，再看品牌已经覆盖了什么、还没进入什么。',
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

function normalizeCompetitorBattle(data: ReportCanvasContent['data']): CompetitorBattleData {
  const explicit = data.report_v2?.competitorBattle ?? data.competitor_battle;
  return {
    title: explicit?.title || '竞品争夺',
    description: explicit?.description,
    overview: sanitizeNarrativeText(explicit?.overview),
    summary_cards: explicit?.summary_cards ?? [],
    items: explicit?.items ?? [],
    differentiation_strategy: sanitizeNarrativeText(explicit?.differentiation_strategy),
  };
}

function normalizeRisks(data: ReportCanvasContent['data']): RiskSectionData {
  const explicit = data.report_v2?.risks ?? data.risk_section;
  const items = extractRiskItems(data);

  return {
    title: '待进入场景与高风险场景',
    description: sanitizeNarrativeText(explicit?.description),
    summary: sanitizeNarrativeText(explicit?.summary),
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

  return {
    title: explicit?.title || '下一步优化',
    description: sanitizeNarrativeText(explicit?.description),
    summary: sanitizeNarrativeText(explicit?.summary),
    items: explicit?.items ?? [],
  };
}

function normalizeSummary(
  data: ReportCanvasContent['data'],
  scenarios: ScenarioCoverageData,
  mentions: ReportMentionSectionData,
  sources: SourceSectionData
): ReportSummaryData {
  const explicit = data.report_v2?.summary ?? data.report_summary;
  const explicitHighlights = (explicit?.highlights ?? []).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));
  const keyFindings = toStringArray(data.key_findings).map(sanitizeNarrativeText).filter((item): item is string => Boolean(item));

  const fallbackMetrics = createSummaryMetrics(
    data.metrics as Record<string, unknown> | undefined,
    scenarios,
    mentions,
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
    description: explicit?.description || '先看品牌提及、场景覆盖、同场竞品和高风险场景这四个核心指标。',
    summary: summaryText,
    status_summary: statusSummary,
    highlights: explicitHighlights,
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
  const brandName = toStringValue(data.brand_name);
  if (explicit) {
    return {
      ...explicit,
      groups:
        explicit.groups && explicit.groups.length > 0
          ? explicit.groups
          : buildMentionScenarioGroups(explicit.brand_mentions ?? [], explicit.competitor_mentions ?? [], brandName),
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
    groups: buildMentionScenarioGroups(brandMentions, competitorMentions, brandName),
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
    description: '只保留来源分布和头部来源，不再展示冗长明细。',
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

function normalizeInsightsForReport(data: ReportCanvasContent['data']): InsightSectionData {
  const explicit = data.report_v2?.insights ?? data.insight_section;
  return {
    title: explicit?.title || '当前优势与补强',
    description: sanitizeNarrativeText(explicit?.description),
    summary: sanitizeNarrativeText(explicit?.summary),
    strengths: explicit?.strengths ?? [],
    weaknesses: explicit?.weaknesses ?? [],
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
  const mentions = normalizeMentions(data);
  const scenarios = normalizeScenarioCoverage(data, mentions);
  const competitorBattle = normalizeCompetitorBattle(data);
  const risks = normalizeRisks(data);
  const sources = normalizeSourcesForReport(data, mentions);
  const insights = normalizeInsightsForReport(data);
  const actionQueue = normalizeActionQueue(data);
  const summary = normalizeSummary(data, scenarios, mentions, sources);
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










