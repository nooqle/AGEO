import type {
  DashboardCitationDomain,
  DashboardCitationSourceType,
  DashboardHomeData,
  DashboardHomeMetric,
  DashboardLatestReport,
  DashboardRelatedQuestion,
} from '@/types/dashboard';

type UnknownRecord = Record<string, unknown>;

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function toStringValue(value: unknown): string | undefined {
  return typeof value === 'string' && value.trim() ? value : undefined;
}

function emptyHome(): DashboardHomeData {
  return {
    summary: { headline: '' },
    latest_report: undefined,
    metrics: [],
    citation_distribution: {
      summary: '',
      source_types: [],
      top_domains: [],
    },
    related_questions: {
      summary: '',
      items: [],
    },
    // Compatibility-only legacy boards kept during controlled rollout so the
    // remaining non-homepage analytics surfaces do not break before they are
    // intentionally replaced or retired.
    mention_board: {
      mention_rate: null,
      headline: '',
      sentiment_summary: { positive: 0, neutral: 0, negative: 0 },
      trend: null,
      leading_competitors: [],
      report: {
        brand_mentions: [],
        competitor_mentions: [],
        strong_scenarios: [],
        weak_scenarios: [],
      },
    },
    source_board: {
      content_citation_rate: null,
      cited_answer_count: 0,
      cited_content_count: 0,
      headline: '',
      trend: null,
      report: {
        official_cases: [],
        non_official_cases: [],
        official_contents: [],
        non_official_contents: [],
        top_domains: [],
        platform_stats: [],
      },
    },
    radar_board: {
      headline: '',
      strongest_dimension: '',
      weakest_dimension: '',
      dimensions: [],
      trend: null,
    },
    monitoring_entry: {
      title: '',
      description: '',
      cta_label: '',
    },
  };
}

function normalizeLatestReport(value: unknown): DashboardLatestReport | undefined {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : null;
  if (!row) return undefined;
  return {
    title: String(row.title ?? '分析报告'),
    subtitle: toStringValue(row.subtitle),
    report_kind: toStringValue(row.reportKind),
    report_kind_label: toStringValue(row.reportKindLabel),
    badge_label: toStringValue(row.badgeLabel),
    triggered_by: toStringValue(row.triggeredBy),
    session_id: toStringValue(row.sessionId),
    artifact_id: toStringValue(row.artifactId),
    output_id: toStringValue(row.outputId),
    created_at: toStringValue(row.createdAt),
    action_label: toStringValue(row.actionLabel),
  };
}

function normalizeMetrics(value: unknown): DashboardHomeMetric[] {
  if (!Array.isArray(value)) return [];
  const metrics: DashboardHomeMetric[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const id = String(row.id ?? '');
    if (!id) continue;
    metrics.push({
      id,
      label: String(row.label ?? ''),
      value: toNumber(row.value),
      format:
        row.format === 'rank' || row.format === 'count' || row.format === 'percent'
          ? row.format
          : 'percent',
      subtitle: toStringValue(row.subtitle),
    });
  }
  return metrics;
}

function normalizeSourceTypes(value: unknown): DashboardCitationSourceType[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
      if (!row) return null;
      return {
        key: String(row.key ?? ''),
        label: String(row.label ?? ''),
        share: toNumber(row.share),
      } satisfies DashboardCitationSourceType;
    })
    .filter((item): item is DashboardCitationSourceType => Boolean(item?.key));
}

function normalizeTopDomains(value: unknown): DashboardCitationDomain[] {
  if (!Array.isArray(value)) return [];
  const domains: DashboardCitationDomain[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const domain = String(row.domain ?? '');
    if (!domain) continue;
    domains.push({
      domain,
      display_name: String(row.displayName ?? row.domain ?? ''),
      count: Number(row.count ?? 0),
      share: toNumber(row.share),
      is_official: Boolean(row.isOfficial),
      source_type: toStringValue(row.sourceType),
      source_type_label: toStringValue(row.sourceTypeLabel),
    });
  }
  return domains;
}

function normalizeRelatedQuestions(value: unknown): DashboardRelatedQuestion[] {
  if (!Array.isArray(value)) return [];
  const questions: DashboardRelatedQuestion[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const questionText = String(row.questionText ?? '');
    if (!questionText) continue;
    questions.push({
      question_id: String(row.questionId ?? ''),
      question_text: questionText,
      scene: toStringValue(row.scene),
    });
  }
  return questions;
}

export function buildDashboardHomeData(value: unknown): DashboardHomeData | undefined {
  if (!value || typeof value !== 'object') {
    return undefined;
  }
  const row = value as UnknownRecord;
  const base = emptyHome();
  const summary = row.summary && typeof row.summary === 'object' ? (row.summary as UnknownRecord) : {};
  const citationDistribution =
    row.citationDistribution && typeof row.citationDistribution === 'object'
      ? (row.citationDistribution as UnknownRecord)
      : {};
  const relatedQuestions =
    row.relatedQuestions && typeof row.relatedQuestions === 'object'
      ? (row.relatedQuestions as UnknownRecord)
      : {};

  return {
    ...base,
    summary: {
      headline: String(summary.headline ?? ''),
    },
    latest_report: normalizeLatestReport(row.latestReport),
    metrics: normalizeMetrics(row.metrics),
    citation_distribution: {
      summary: String(citationDistribution.summary ?? ''),
      source_types: normalizeSourceTypes(citationDistribution.sourceTypes),
      top_domains: normalizeTopDomains(citationDistribution.topDomains),
    },
    related_questions: {
      summary: String(relatedQuestions.summary ?? ''),
      items: normalizeRelatedQuestions(relatedQuestions.items),
    },
  };
}
