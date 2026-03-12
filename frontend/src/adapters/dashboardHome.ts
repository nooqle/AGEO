import type {
  DashboardHomeData,
  DashboardMentionBoard,
  DashboardMentionItem,
  DashboardMonitoringEntry,
  DashboardRadarBoard,
  DashboardRadarDimension,
  DashboardSentimentSummary,
  DashboardSourceBoard,
  DashboardSourceCitationCase,
  DashboardSourceContent,
  DashboardSourcePlatformStat,
} from '@/types/dashboard';

type UnknownRecord = Record<string, unknown>;

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function toStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map((item) => String(item)).filter(Boolean) : [];
}

function normalizeSentimentSummary(value: unknown): DashboardSentimentSummary {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    positive: Number(row.positive ?? 0),
    neutral: Number(row.neutral ?? 0),
    negative: Number(row.negative ?? 0),
  };
}

function normalizeMentionItem(value: unknown): DashboardMentionItem {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    competitor: typeof row.competitor === 'string' ? row.competitor : undefined,
    scenario_id: String(row.scenarioId ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    platform: String(row.platform ?? ''),
    sentiment: String(row.sentiment ?? 'neutral'),
    evidence: typeof row.evidence === 'string' ? row.evidence : undefined,
    citation_domains: toStringArray(row.citationDomains),
    citation_titles: toStringArray(row.citationTitles),
    citation_urls: toStringArray(row.citationUrls),
    official_citation_present: Boolean(row.officialCitationPresent),
  };
}

function normalizeScenarioInsight(value: unknown) {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    scenario_id: String(row.scenarioId ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    reason: String(row.reason ?? ''),
    platforms: toStringArray(row.platforms),
  };
}

function normalizeSourceCase(value: unknown): DashboardSourceCitationCase {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    scenario_id: String(row.scenarioId ?? ''),
    scenario_label: String(row.scenarioLabel ?? ''),
    platform: typeof row.platform === 'string' ? row.platform : undefined,
    matched_answer: typeof row.matchedAnswer === 'string' ? row.matchedAnswer : undefined,
    citation_domains: toStringArray(row.citationDomains),
    citation_titles: toStringArray(row.citationTitles),
    citation_urls: toStringArray(row.citationUrls),
    is_official: Boolean(row.isOfficial),
    aice_score: toNumber(row.aiceScore),
    aice_dimensions: row.aiceDimensions && typeof row.aiceDimensions === 'object' ? {
      authority: toNumber((row.aiceDimensions as UnknownRecord).authority),
      intent: toNumber((row.aiceDimensions as UnknownRecord).intent),
      clarity: toNumber((row.aiceDimensions as UnknownRecord).clarity),
      evidence: toNumber((row.aiceDimensions as UnknownRecord).evidence),
    } : null,
  };
}

function normalizeSourceContent(value: unknown): DashboardSourceContent {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    title: String(row.title ?? ''),
    domain: typeof row.domain === 'string' ? row.domain : undefined,
    count: typeof row.count === 'number' ? row.count : undefined,
    is_official: Boolean(row.isOfficial),
  };
}

function normalizeSourcePlatformStat(value: unknown): DashboardSourcePlatformStat {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    platform: String(row.platform ?? ''),
    content_citation_rate: Number(row.contentCitationRate ?? 0),
    official_citation_rate: Number(row.officialCitationRate ?? 0),
    top_domains: Array.isArray(row.topDomains)
      ? row.topDomains.map((item) => {
          const domain = item && typeof item === 'object' ? (item as UnknownRecord) : {};
          return {
            domain: String(domain.domain ?? ''),
            count: Number(domain.count ?? 0),
          };
        })
      : [],
  };
}

function normalizeMentionBoard(value: unknown): DashboardMentionBoard {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  const report = row.report && typeof row.report === 'object' ? (row.report as UnknownRecord) : {};
  return {
    mention_rate: toNumber(row.mentionRate),
    headline: String(row.headline ?? ''),
    sentiment_summary: normalizeSentimentSummary(row.sentimentSummary),
    leading_competitors: Array.isArray(row.leadingCompetitors)
      ? row.leadingCompetitors.map((item) => {
          const competitor = item && typeof item === 'object' ? (item as UnknownRecord) : {};
          return {
            competitor: String(competitor.competitor ?? ''),
            pressure_level: String(competitor.pressureLevel ?? 'medium'),
            competitor_only_scenarios: Number(competitor.competitorOnlyScenarios ?? 0),
            sentiment_summary: normalizeSentimentSummary(competitor.sentimentSummary),
          };
        })
      : [],
    report: {
      brand_mentions: Array.isArray(report.brandMentions) ? report.brandMentions.map(normalizeMentionItem) : [],
      competitor_mentions: Array.isArray(report.competitorMentions) ? report.competitorMentions.map(normalizeMentionItem) : [],
      strong_scenarios: Array.isArray(report.strongScenarios) ? report.strongScenarios.map(normalizeScenarioInsight) : [],
      weak_scenarios: Array.isArray(report.weakScenarios) ? report.weakScenarios.map(normalizeScenarioInsight) : [],
    },
  };
}

function normalizeSourceBoard(value: unknown): DashboardSourceBoard {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  const report = row.report && typeof row.report === 'object' ? (row.report as UnknownRecord) : {};
  return {
    content_citation_rate: toNumber(row.contentCitationRate),
    cited_answer_count: Number(row.citedAnswerCount ?? 0),
    cited_content_count: Number(row.citedContentCount ?? 0),
    headline: String(row.headline ?? ''),
    report: {
      official_cases: Array.isArray(report.officialCases) ? report.officialCases.map(normalizeSourceCase) : [],
      non_official_cases: Array.isArray(report.nonOfficialCases) ? report.nonOfficialCases.map(normalizeSourceCase) : [],
      official_contents: Array.isArray(report.officialContents) ? report.officialContents.map(normalizeSourceContent) : [],
      non_official_contents: Array.isArray(report.nonOfficialContents) ? report.nonOfficialContents.map(normalizeSourceContent) : [],
      top_domains: Array.isArray(report.topDomains)
        ? report.topDomains.map((item) => {
            const domain = item && typeof item === 'object' ? (item as UnknownRecord) : {};
            return {
              domain: String(domain.domain ?? ''),
              count: Number(domain.count ?? 0),
              share: Number(domain.share ?? 0),
              is_official: Boolean(domain.isOfficial),
            };
          })
        : [],
      platform_stats: Array.isArray(report.platformStats) ? report.platformStats.map(normalizeSourcePlatformStat) : [],
    },
  };
}

function normalizeRadarBoard(value: unknown): DashboardRadarBoard {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    headline: String(row.headline ?? ''),
    strongest_dimension: String(row.strongestDimension ?? ''),
    weakest_dimension: String(row.weakestDimension ?? ''),
    dimensions: Array.isArray(row.dimensions)
      ? row.dimensions.map((item) => {
          const dimension = item && typeof item === 'object' ? (item as UnknownRecord) : {};
          return {
            id: String(dimension.id ?? ''),
            label: String(dimension.label ?? ''),
            score: Number(dimension.score ?? 0),
            summary: String(dimension.summary ?? ''),
          } satisfies DashboardRadarDimension;
        })
      : [],
  };
}

function normalizeMonitoringEntry(value: unknown): DashboardMonitoringEntry {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    title: String(row.title ?? '持续监测'),
    description: String(row.description ?? ''),
    cta_label: String(row.ctaLabel ?? '进入监测'),
  };
}

export function buildDashboardHomeData(value: unknown): DashboardHomeData | undefined {
  if (!value || typeof value !== 'object') {
    return undefined;
  }
  const row = value as UnknownRecord;
  const summary = row.summary && typeof row.summary === 'object' ? (row.summary as UnknownRecord) : {};
  return {
    summary: {
      headline: String(summary.headline ?? ''),
    },
    mention_board: normalizeMentionBoard(row.mentionBoard),
    source_board: normalizeSourceBoard(row.sourceBoard),
    radar_board: normalizeRadarBoard(row.radarBoard),
    monitoring_entry: normalizeMonitoringEntry(row.monitoringEntry),
  };
}
