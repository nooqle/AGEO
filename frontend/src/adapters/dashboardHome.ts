import type {
  DashboardCitationDomain,
  DashboardCitationSourceType,
  DashboardEmotionSentiment,
  DashboardEmotionWord,
  DashboardEmotionWordCloud,
  DashboardHomeAdvantageCard,
  DashboardHomeData,
  DashboardHomeMetric,
  DashboardTodoItem,
  DashboardMonitoringIssue,
  DashboardMonitoringPlanSummary,
  DashboardPeriodSummary,
  DashboardHomeRiskCard,
  DashboardLatestReport,
  DashboardMentionRankingRow,
  DashboardPlatformDiagnosisRow,
  DashboardRelatedQuestion,
  DashboardSourceStructure,
} from '@/types/dashboard';
import { normalizeAiSourceDisplayName } from '@/lib/aiSourceDisplay';

type UnknownRecord = Record<string, unknown>;

const NULLISH_DISPLAY_VALUES = new Set(['null', 'none', 'undefined', 'nan']);

function toNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }
  return NULLISH_DISPLAY_VALUES.has(trimmed.toLowerCase()) ? undefined : trimmed;
}

function pick(row: UnknownRecord, ...keys: string[]): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(row, key)) {
      return row[key];
    }
  }
  return undefined;
}

function toInteger(value: unknown): number {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return Math.round(value);
  }
  return 0;
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
    monitoring_plan: undefined,
    period_summary: undefined,
    data_point_count: 0,
    recent_issue: undefined,
    todo_items: [],
    word_cloud: {
      positive: [],
      negative: [],
    },
    platform_diagnosis: [],
    risks: [],
    advantages: [],
    mention_ranking: [],
    source_structure: {
      official_conversion_rate: null,
      source_types: [],
      top_domains: [],
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

function normalizeMonitorMode(value: unknown): DashboardMonitoringPlanSummary['monitor_mode'] {
  return value === 'scenario' || value === 'scenario_monitoring' || value === 'persona'
    ? 'scenario'
    : 'panorama';
}

function normalizePlanStatus(value: unknown): DashboardMonitoringPlanSummary['status'] {
  if (value === 'draft' || value === 'active' || value === 'paused' || value === 'archived') {
    return value;
  }
  return 'draft';
}

function normalizeRunPolicy(value: unknown): DashboardMonitoringPlanSummary['run_policy'] {
  if (value === 'quick' || value === 'full_browser' || value === 'manual') {
    return value;
  }
  return 'quick';
}

function normalizeMonitoringPlan(value: unknown): DashboardMonitoringPlanSummary | undefined {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : null;
  if (!row) return undefined;
  const id = toStringValue(row.id);
  if (!id) return undefined;
  return {
    id,
    status: normalizePlanStatus(row.status),
    monitor_mode: normalizeMonitorMode(pick(row, 'monitorMode', 'monitor_mode')),
    title: toStringValue(row.title) ?? '',
    question_set_ids: normalizeStringArray(pick(row, 'questionSetIds', 'question_set_ids')) ?? [],
    question_set_label: toStringValue(pick(row, 'questionSetLabel', 'question_set_label')) ?? '',
    question_count: toInteger(pick(row, 'questionCount', 'question_count')),
    endpoint_ids: normalizeStringArray(pick(row, 'endpointIds', 'endpoint_ids')) ?? [],
    endpoint_labels: normalizeStringArray(pick(row, 'endpointLabels', 'endpoint_labels')) ?? [],
    run_policy: normalizeRunPolicy(pick(row, 'runPolicy', 'run_policy')),
    frequency: toStringValue(row.frequency),
    schedule_id: toStringValue(pick(row, 'scheduleId', 'schedule_id')) ?? null,
    schedule_status: toStringValue(pick(row, 'scheduleStatus', 'schedule_status')) ?? null,
  };
}

function normalizeLatestReport(value: unknown): DashboardLatestReport | undefined {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : null;
  if (!row) return undefined;
  const preview = pick(row, 'questionPreview', 'question_preview');
  return {
    title: toStringValue(row.title) ?? '分析报告',
    subtitle: toStringValue(row.subtitle),
    report_kind: toStringValue(pick(row, 'reportKind', 'report_kind')),
    report_kind_label: toStringValue(pick(row, 'reportKindLabel', 'report_kind_label')),
    scope_label: toStringValue(pick(row, 'scopeLabel', 'scope_label')),
    scope_description: toStringValue(pick(row, 'scopeDescription', 'scope_description')),
    question_set_label: toStringValue(pick(row, 'questionSetLabel', 'question_set_label')),
    sample_summary: toStringValue(pick(row, 'sampleSummary', 'sample_summary')),
    question_preview: Array.isArray(preview)
      ? preview.map((item) => toStringValue(item)).filter((item): item is string => Boolean(item)).slice(0, 3)
      : [],
    badge_label: toStringValue(pick(row, 'badgeLabel', 'badge_label')),
    triggered_by: toStringValue(pick(row, 'triggeredBy', 'triggered_by')),
    session_id: toStringValue(pick(row, 'sessionId', 'session_id')),
    artifact_id: toStringValue(pick(row, 'artifactId', 'artifact_id')),
    output_id: toStringValue(pick(row, 'outputId', 'output_id')),
    created_at: toStringValue(pick(row, 'createdAt', 'created_at')),
    action_label: toStringValue(pick(row, 'actionLabel', 'action_label')),
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
      label: toStringValue(row.label) ?? '',
      value: toNumber(row.value),
      format:
        row.format === 'rank' || row.format === 'count' || row.format === 'percent'
          ? row.format
          : 'percent',
      subtitle: toStringValue(row.subtitle),
      data_point_count: toInteger(pick(row, 'dataPointCount', 'data_point_count')),
      average_value: toNumber(pick(row, 'averageValue', 'average_value')),
      change_absolute: toNumber(pick(row, 'changeAbsolute', 'change_absolute')),
    });
  }
  return metrics;
}

function normalizePeriodSummary(value: unknown): DashboardPeriodSummary | undefined {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : null;
  if (!row) return undefined;
  const rawMetrics = pick(row, 'metrics');
  const metrics = Array.isArray(rawMetrics)
    ? rawMetrics
        .map((item) => {
          const metric = item && typeof item === 'object' ? (item as UnknownRecord) : null;
          if (!metric) return null;
          const id = toStringValue(metric.id) ?? toStringValue(metric.metric) ?? '';
          if (!id) return null;
          const rawPoints = pick(metric, 'points');
          return {
            id,
            label: toStringValue(metric.label) ?? id,
            metric: toStringValue(metric.metric) ?? id,
            data_point_count: toInteger(pick(metric, 'dataPointCount', 'data_point_count')),
            current_value: toNumber(pick(metric, 'currentValue', 'current_value')),
            previous_value: toNumber(pick(metric, 'previousValue', 'previous_value')),
            average_value: toNumber(pick(metric, 'averageValue', 'average_value')),
            change_absolute: toNumber(pick(metric, 'changeAbsolute', 'change_absolute')),
            change_percentage: toNumber(pick(metric, 'changePercentage', 'change_percentage')),
            direction: toStringValue(metric.direction) ?? null,
            points: Array.isArray(rawPoints)
              ? rawPoints
                  .map((point) => {
                    const pointRow = point && typeof point === 'object' ? (point as UnknownRecord) : null;
                    if (!pointRow) return null;
                    const date = toStringValue(pointRow.date) ?? '';
                    if (!date) return null;
                    return { date, value: toNumber(pointRow.value) };
                  })
                  .filter((point): point is { date: string; value: number | null } => Boolean(point))
              : [],
          };
        })
        .filter((item): item is DashboardPeriodSummary['metrics'][number] => Boolean(item))
    : [];
  return {
    date_range_days: toInteger(pick(row, 'dateRangeDays', 'date_range_days')),
    period_label: toStringValue(pick(row, 'periodLabel', 'period_label')) ?? '',
    data_point_count: toInteger(pick(row, 'dataPointCount', 'data_point_count')),
    metrics,
  };
}

function normalizeMonitoringIssue(value: unknown): DashboardMonitoringIssue | undefined {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : null;
  if (!row) return undefined;
  const id = toStringValue(row.id) ?? toStringValue(pick(row, 'monitoringRunId', 'monitoring_run_id'));
  if (!id) return undefined;
  return {
    id,
    type: toStringValue(row.type) ?? 'failed',
    status: toStringValue(row.status) ?? '',
    title: toStringValue(row.title) ?? '自动监测异常',
    error_stage: toStringValue(pick(row, 'errorStage', 'error_stage')) ?? null,
    error_message: toStringValue(pick(row, 'errorMessage', 'error_message')) ?? null,
    monitor_mode: normalizeMonitorMode(pick(row, 'monitorMode', 'monitor_mode')),
    monitoring_plan_id: toStringValue(pick(row, 'monitoringPlanId', 'monitoring_plan_id')) ?? null,
    monitoring_run_id: toStringValue(pick(row, 'monitoringRunId', 'monitoring_run_id')) ?? id,
    plan_title: toStringValue(pick(row, 'planTitle', 'plan_title')) ?? null,
    question_count: toInteger(pick(row, 'questionCount', 'question_count')),
    endpoint_ids: normalizeStringArray(pick(row, 'endpointIds', 'endpoint_ids')) ?? [],
    endpoint_labels: normalizeStringArray(pick(row, 'endpointLabels', 'endpoint_labels')) ?? [],
    question_set_ids: normalizeStringArray(pick(row, 'questionSetIds', 'question_set_ids')) ?? [],
    created_at: toStringValue(pick(row, 'createdAt', 'created_at')) ?? null,
    updated_at: toStringValue(pick(row, 'updatedAt', 'updated_at')) ?? null,
  };
}

function normalizeTodoItems(value: unknown): DashboardTodoItem[] {
  if (!Array.isArray(value)) return [];
  const items: DashboardTodoItem[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const id = toStringValue(row.id) ?? toStringValue(pick(row, 'refId', 'ref_id'));
    const title = toStringValue(row.title);
    if (!id || !title) continue;
    items.push({
      id,
      kind: toStringValue(row.kind) ?? id,
      priority: toInteger(row.priority),
      title,
      description: toStringValue(row.description) ?? '',
      action: toStringValue(row.action) ?? '',
      action_label: toStringValue(pick(row, 'actionLabel', 'action_label')) ?? '',
      monitor_mode: normalizeMonitorMode(pick(row, 'monitorMode', 'monitor_mode')),
      monitoring_plan_id: toStringValue(pick(row, 'monitoringPlanId', 'monitoring_plan_id')) ?? null,
      ref_id: toStringValue(pick(row, 'refId', 'ref_id')) ?? null,
      report_created_at: toStringValue(pick(row, 'reportCreatedAt', 'report_created_at')) ?? null,
    });
  }
  return items.sort((a, b) => a.priority - b.priority);
}

function normalizeSourceTypes(value: unknown): DashboardCitationSourceType[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => {
      const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
      if (!row) return null;
      const key = toStringValue(row.key) ?? '';
      if (!key) return null;
      return {
        key,
        label: toStringValue(row.label) ?? '',
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
    const domain = toStringValue(row.domain) ?? '';
    if (!domain) continue;
    domains.push({
      domain,
      display_name: toStringValue(row.displayName) ?? toStringValue(row.domain) ?? domain,
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
    const questionText = toStringValue(row.questionText) ?? '';
    if (!questionText) continue;
    questions.push({
      question_id: String(row.questionId ?? ''),
      question_text: questionText,
      scene: toStringValue(row.scene),
    });
  }
  return questions;
}

function normalizeEmotion(value: unknown, fallback: DashboardEmotionSentiment): DashboardEmotionSentiment {
  if (value === 'positive' || value === 'negative') {
    return value;
  }
  return fallback;
}

function normalizeStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value
    .map((item) => toStringValue(item))
    .filter((item): item is string => Boolean(item));
  return items.length ? items : undefined;
}

function normalizeEmotionWords(value: unknown, sentiment: DashboardEmotionSentiment): DashboardEmotionWord[] {
  if (!Array.isArray(value)) return [];
  const words: DashboardEmotionWord[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const text = toStringValue(pick(row, 'text', 'word', 'label')) ?? '';
    if (!text) continue;
    words.push({
      text,
      weight: toNumber(pick(row, 'weight', 'value', 'rate')) ?? 0,
      sentiment: normalizeEmotion(pick(row, 'sentiment'), sentiment),
      count: toInteger(pick(row, 'count', 'mentionCount', 'mention_count')),
      platforms: normalizeStringArray(pick(row, 'platforms')),
    });
  }
  return words;
}

function normalizeWordCloud(value: unknown): DashboardEmotionWordCloud {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    positive: normalizeEmotionWords(pick(row, 'positive'), 'positive'),
    negative: normalizeEmotionWords(pick(row, 'negative'), 'negative'),
  };
}

function normalizePlatformStatus(value: unknown): DashboardPlatformDiagnosisRow['status'] {
  if (value === 'good' || value === 'watch' || value === 'risk') {
    return value;
  }
  return 'unknown';
}

function normalizePlatformDiagnosis(value: unknown): DashboardPlatformDiagnosisRow[] {
  if (!Array.isArray(value)) return [];
  const rows: DashboardPlatformDiagnosisRow[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const fetchMethod = toStringValue(pick(row, 'fetchMethod', 'fetch_method'));
    const platform = normalizeAiSourceDisplayName(toStringValue(row.platform), fetchMethod);
    if (!platform) continue;
    rows.push({
      platform,
      platform_id: toStringValue(pick(row, 'platformId', 'platform_id')),
      fetch_method: fetchMethod,
      status: normalizePlatformStatus(pick(row, 'status')),
      answer_count: toInteger(pick(row, 'answerCount', 'answer_count')),
      brand_mention_count: toInteger(pick(row, 'brandMentionCount', 'brand_mention_count')),
      positive_count: toInteger(pick(row, 'positiveCount', 'positive_count')),
      negative_count: toInteger(pick(row, 'negativeCount', 'negative_count')),
      main_concern: toStringValue(pick(row, 'mainConcern', 'main_concern')),
    });
  }
  return rows;
}

function normalizeRiskLevel(value: unknown): DashboardHomeRiskCard['level'] {
  if (value === 'high' || value === 'medium' || value === 'low') {
    return value;
  }
  return 'medium';
}

function normalizeRisks(value: unknown): DashboardHomeRiskCard[] {
  if (!Array.isArray(value)) return [];
  const rows: DashboardHomeRiskCard[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const title = toStringValue(pick(row, 'title', 'scenarioLabel', 'scenario_label')) ?? '';
    if (!title) continue;
    rows.push({
      title,
      level: normalizeRiskLevel(pick(row, 'level', 'severity')),
      platform: normalizeAiSourceDisplayName(toStringValue(row.platform)),
      evidence: toStringValue(pick(row, 'evidence', 'reason')),
    });
  }
  return rows;
}

function normalizeAdvantages(value: unknown): DashboardHomeAdvantageCard[] {
  if (!Array.isArray(value)) return [];
  const rows: DashboardHomeAdvantageCard[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const title = toStringValue(pick(row, 'title', 'scenarioLabel', 'scenario_label')) ?? '';
    if (!title) continue;
    rows.push({
      title,
      platform_count: toInteger(pick(row, 'platformCount', 'platform_count')),
      evidence: toStringValue(pick(row, 'evidence', 'reason')),
    });
  }
  return rows;
}

function normalizeMentionRanking(value: unknown): DashboardMentionRankingRow[] {
  if (!Array.isArray(value)) return [];
  const rows: DashboardMentionRankingRow[] = [];
  for (const item of value) {
    const row = item && typeof item === 'object' ? (item as UnknownRecord) : null;
    if (!row) continue;
    const brand = toStringValue(row.brand) ?? '';
    const rank = toInteger(row.rank);
    if (!brand || rank <= 0) continue;
    rows.push({
      rank,
      brand,
      mention_rate: toNumber(pick(row, 'mentionRate', 'mention_rate')),
      mention_count: toInteger(pick(row, 'mentionCount', 'mention_count', 'brandPresenceCount', 'brand_presence_count')),
      is_current_brand: Boolean(pick(row, 'isCurrentBrand', 'is_current_brand')),
    });
  }
  return rows.slice(0, 10);
}

function normalizeSourceStructure(value: unknown): DashboardSourceStructure {
  const row = value && typeof value === 'object' ? (value as UnknownRecord) : {};
  return {
    official_conversion_rate: toNumber(pick(row, 'officialConversionRate', 'official_conversion_rate')),
    source_types: normalizeSourceTypes(pick(row, 'sourceTypes', 'source_types')),
    top_domains: normalizeTopDomains(pick(row, 'topDomains', 'top_domains')),
  };
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
  const sourceStructure = normalizeSourceStructure(pick(row, 'sourceStructure', 'source_structure'));

  return {
    ...base,
    summary: {
      headline: toStringValue(summary.headline) ?? '',
    },
    latest_report: normalizeLatestReport(pick(row, 'latestReport', 'latest_report')),
    monitoring_plan: normalizeMonitoringPlan(pick(row, 'monitoringPlan', 'monitoring_plan')),
    period_summary: normalizePeriodSummary(pick(row, 'periodSummary', 'period_summary')),
    data_point_count: toInteger(pick(row, 'dataPointCount', 'data_point_count')),
    recent_issue: normalizeMonitoringIssue(pick(row, 'recentIssue', 'recent_issue')),
    todo_items: normalizeTodoItems(pick(row, 'todoItems', 'todo_items')),
    metrics: normalizeMetrics(row.metrics),
    word_cloud: normalizeWordCloud(pick(row, 'wordCloud', 'word_cloud')),
    platform_diagnosis: normalizePlatformDiagnosis(pick(row, 'platformDiagnosis', 'platform_diagnosis')),
    risks: normalizeRisks(pick(row, 'risks')),
    advantages: normalizeAdvantages(pick(row, 'advantages')),
    mention_ranking: normalizeMentionRanking(pick(row, 'mentionRanking', 'mention_ranking')),
    source_structure: sourceStructure,
    citation_distribution: {
      summary: toStringValue(citationDistribution.summary) ?? '',
      source_types: normalizeSourceTypes(citationDistribution.sourceTypes),
      top_domains: normalizeTopDomains(citationDistribution.topDomains),
    },
    related_questions: {
      summary: toStringValue(relatedQuestions.summary) ?? '',
      items: normalizeRelatedQuestions(relatedQuestions.items),
    },
  };
}
