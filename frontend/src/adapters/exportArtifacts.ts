import type {
  ConfidenceSignalDimensionScore,
  ConfidenceExtraEvaluation,
  ConfidenceSignalFinding,
  ConfidenceSignalItem,
  ConfidenceOverview,
  ConfidencePattern,
  ConfidenceSignalRecommendation,
  ConfidenceStrategicRecommendation,
  ConfidenceSignalSummary,
  FetchCitation,
  FetchPlatformPacket,
  FetchPlatformResult,
  FetchPlatformStatusProjection,
  FetchPlatformStatusSummary,
  FetchPlatformStatusValue,
  FetchResultItem,
  FetchResultsCanvasContent,
  FetchTimingSummary,
  ReportCanvasContent,
} from '@/types/canvas';

type UnknownRecord = Record<string, unknown>;

export type FetchExportViewModel = {
  title: string;
  subtitle: string;
  totalQuestions: number;
  totalPlatforms: number;
  successCount: number;
  failedCount: number;
  skippedCount: number;
  items: FetchResultItem[];
  platformStatus?: FetchPlatformStatusProjection;
  timingSummary?: FetchTimingSummary;
};

export type ConfidenceExportViewModel = {
  title: string;
  subtitle?: string;
  summary?: ConfidenceSignalSummary;
  overallConclusion?: string;
  findings: ConfidenceSignalFinding[];
  brandConfidenceOverview?: ConfidenceOverview;
  competitorConfidenceOverview?: ConfidenceOverview;
  brandLowConfidencePatterns: ConfidencePattern[];
  competitorLowConfidencePatterns: ConfidencePattern[];
  strategicRecommendations: ConfidenceStrategicRecommendation[];
  extraEvaluation?: ConfidenceExtraEvaluation;
  items: ConfidenceSignalItem[];
};

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toStringValue(value: unknown): string | undefined {
  if (typeof value !== 'string') {
    return undefined;
  }
  const normalized = value.trim();
  return normalized || undefined;
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
    if (['true', '1', 'yes', 'y', '是', '有', '已'].includes(normalized)) {
      return true;
    }
    if (['false', '0', 'no', 'n', '否', '无', '未'].includes(normalized)) {
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
    .map((item) => toStringValue(item))
    .filter((item): item is string => Boolean(item));
}

function readField(record: UnknownRecord | undefined, ...keys: string[]): unknown {
  if (!record) {
    return undefined;
  }
  for (const key of keys) {
    if (key in record) {
      return record[key];
    }
  }
  return undefined;
}

function readString(record: UnknownRecord | undefined, ...keys: string[]): string | undefined {
  return toStringValue(readField(record, ...keys));
}

function readNumber(record: UnknownRecord | undefined, ...keys: string[]): number | undefined {
  return toNumberValue(readField(record, ...keys));
}

function readBoolean(record: UnknownRecord | undefined, ...keys: string[]): boolean | undefined {
  return toBooleanValue(readField(record, ...keys));
}

function readStringList(record: UnknownRecord | undefined, ...keys: string[]): string[] {
  return keys.flatMap((key) => toStringArray(record?.[key]));
}

export function isConfidenceReportKind(value: string | undefined): boolean {
  return value === 'confidence_signal' || value === 'confidence_analysis';
}

export function isSiteConfidenceReportKind(value: string | undefined): boolean {
  return value === 'site_confidence_report';
}

function uniqueByKey<T>(items: T[], getKey: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = getKey(item);
    if (!key || seen.has(key)) {
      return false;
    }
    seen.add(key);
    return true;
  });
}

function canonicalizeFetchPlatform(platform: string | undefined): string {
  const normalized = platform?.trim().toLowerCase();
  if (!normalized) {
    return 'unknown';
  }
  if (
    [
      'hunyuan',
      'hunyuan_api',
      'hunyuan_browser',
      'yuanbao_api',
      'yuanbao_browser',
      'tencent_yuanbao',
      '腾讯元宝',
      '混元',
      '元宝',
    ].includes(normalized)
  ) {
    return 'yuanbao';
  }
  return normalized;
}

function mergePlatformStatusSummaries(
  summaries: FetchPlatformStatusSummary[],
): FetchPlatformStatusSummary[] {
  const byPlatform = new Map<string, FetchPlatformStatusSummary>();
  summaries.forEach((summary) => {
    const platform = canonicalizeFetchPlatform(summary.platform);
    if (platform === 'unknown') return;
    const existing = byPlatform.get(platform);
    byPlatform.set(platform, {
      ...existing,
      ...summary,
      platform,
      questions_completed:
        summary.questions_completed ?? existing?.questions_completed,
      questions_total: summary.questions_total ?? existing?.questions_total,
      mention_count: summary.mention_count ?? existing?.mention_count,
      timing: {
        ...(existing?.timing || {}),
        ...(summary.timing || {}),
      },
    });
  });
  return Array.from(byPlatform.values());
}

function normalizeFetchTimingSummary(
  timingSummary: FetchTimingSummary | undefined,
): FetchTimingSummary | undefined {
  if (!timingSummary?.platforms) {
    return timingSummary;
  }
  const platforms: NonNullable<FetchTimingSummary['platforms']> = {};
  Object.entries(timingSummary.platforms).forEach(([platform, timing]) => {
    const canonical = canonicalizeFetchPlatform(platform);
    if (canonical === 'unknown') return;
    platforms[canonical] = {
      ...(platforms[canonical] || {}),
      ...timing,
    };
  });
  return {
    ...timingSummary,
    platforms,
  };
}

function normalizeFetchStatus(value: unknown): FetchPlatformStatusValue {
  const normalized = typeof value === 'string' ? value.trim().toLowerCase() : '';
  if (['success', 'succeeded', 'result'].includes(normalized)) {
    return 'success';
  }
  if (normalized === 'skipped') {
    return 'skipped';
  }
  if (normalized === 'running') {
    return 'running';
  }
  if (normalized === 'pending') {
    return 'pending';
  }
  if (normalized === 'takeover_required') {
    return 'takeover_required';
  }
  return 'failed';
}

function isFetchSuccessStatus(status: FetchPlatformStatusValue | undefined, success: boolean | undefined): boolean {
  if (status) {
    return status === 'success';
  }
  return Boolean(success);
}

function normalizeFetchCitation(record: UnknownRecord, index: number): FetchCitation {
  return {
    index: readNumber(record, 'index', 'order') ?? index + 1,
    title: readString(record, 'title', 'name', 'label') || `引用 ${index + 1}`,
    url: readString(record, 'url', 'href', 'link') || '',
    snippet: readString(record, 'snippet', 'summary', 'description'),
    site_name: readString(record, 'site_name', 'siteName', 'source'),
    is_official: readBoolean(record, 'is_official', 'isOfficial'),
  };
}

function normalizeAnswerPayload(value: unknown): FetchPlatformResult['answer'] | undefined {
  if (typeof value === 'string') {
    const content = value.trim();
    return content ? { content } : undefined;
  }
  if (!isRecord(value)) {
    return undefined;
  }
  return {
    content: readString(value, 'content', 'text', 'answer'),
    word_count: readNumber(value, 'word_count', 'wordCount', 'length'),
    has_brand_mention: readBoolean(value, 'has_brand_mention', 'hasBrandMention'),
  };
}

function normalizeFetchPlatformPacket(record: UnknownRecord): FetchPlatformPacket | null {
  const platform =
    readString(record, 'platform', 'provider', 'engine', 'name', 'platform_id') || undefined;
  const status =
    readString(record, 'status') ||
    (readBoolean(record, 'skipped_by_user') ? 'skipped' : undefined);

  if (!platform && status === undefined && !readString(record, 'error', 'message')) {
    return null;
  }

  return {
    platform: canonicalizeFetchPlatform(platform),
    status: normalizeFetchStatus(status),
    auth_state: readString(record, 'auth_state', 'authState'),
    action_type: readString(record, 'action_type', 'actionType'),
    reason_code: readString(record, 'reason_code', 'reasonCode'),
    request_id: readString(record, 'request_id', 'requestId'),
    target_url: readString(record, 'target_url', 'targetUrl'),
    blocking_url: readString(record, 'blocking_url', 'blockingUrl'),
    blocking_fingerprint: readString(record, 'blocking_fingerprint', 'blockingFingerprint'),
    fetch_method: readString(record, 'fetch_method', 'fetchMethod', 'method'),
    answer: normalizeAnswerPayload(readField(record, 'answer', 'result')),
    citations: toRecordArray(readField(record, 'citations', 'references', 'sources')).map(normalizeFetchCitation),
    error: readString(record, 'error', 'message'),
    duration: readNumber(record, 'duration', 'latency', 'elapsed'),
    timing_json: isRecord(readField(record, 'timing_json', 'timingJson'))
      ? ((readField(record, 'timing_json', 'timingJson') as UnknownRecord) as Record<string, number | string>)
      : undefined,
  };
}

function normalizeFetchPlatformResult(record: UnknownRecord): FetchPlatformResult | null {
  const platform =
    readString(record, 'platform', 'provider', 'engine', 'name', 'platform_id') || undefined;
  const status = readString(record, 'status');
  const answerRecord = readField(record, 'answer', 'result');
  const success =
    isFetchSuccessStatus(
      status ? normalizeFetchStatus(status) : undefined,
      readBoolean(record, 'success', 'ok') ?? undefined
    ) ||
    (!status &&
      (readBoolean(record, 'success', 'ok') ??
        Boolean(answerRecord || readString(record, 'error', 'message') === undefined)));

  if (!platform && !answerRecord && !readString(record, 'error', 'message')) {
    return null;
  }

  return {
    platform: canonicalizeFetchPlatform(platform),
    platform_name:
      readString(record, 'platform_name', 'platformName', 'display_name', 'displayName') ||
      platform,
    status: status ? normalizeFetchStatus(status) : success ? 'success' : 'failed',
    fetch_method: readString(record, 'fetch_method', 'fetchMethod', 'method'),
    success,
    answer: normalizeAnswerPayload(answerRecord),
    citations: toRecordArray(readField(record, 'citations', 'references', 'sources')).map(normalizeFetchCitation),
    error: readString(record, 'error', 'message'),
    duration: readNumber(record, 'duration', 'latency', 'elapsed'),
  };
}

function mergeFetchPlatformResult(
  legacy: FetchPlatformResult | undefined,
  packet: FetchPlatformPacket | undefined
): FetchPlatformResult | null {
  if (!legacy && !packet) {
    return null;
  }
  const status = packet?.status ?? legacy?.status ?? (legacy?.success ? 'success' : 'failed');
  const normalizedStatus = normalizeFetchStatus(status);
  const platform = canonicalizeFetchPlatform(packet?.platform || legacy?.platform);
  return {
    platform,
    platform_name: legacy?.platform_name || packet?.platform || legacy?.platform || platform,
    status: normalizedStatus,
    fetch_method: packet?.fetch_method || legacy?.fetch_method,
    success: normalizedStatus === 'success',
    answer: packet?.answer || legacy?.answer,
    citations: packet?.citations?.length ? packet.citations : legacy?.citations,
    error:
      packet?.error ||
      legacy?.error ||
      (normalizedStatus === 'skipped' ? '已跳过该平台' : undefined),
    duration: packet?.duration ?? legacy?.duration,
  };
}

function normalizePlatformStatusSummary(record: UnknownRecord): FetchPlatformStatusSummary | null {
  const platform = canonicalizeFetchPlatform(readString(record, 'platform'));
  if (platform === 'unknown') {
    return null;
  }
  return {
    platform,
    status: normalizeFetchStatus(readField(record, 'status')),
    questions_completed: readNumber(record, 'questions_completed', 'questionsCompleted'),
    questions_total: readNumber(record, 'questions_total', 'questionsTotal'),
    mention_count: readNumber(record, 'mention_count', 'mentionCount'),
    error: readString(record, 'error') ?? null,
    auth_state: readString(record, 'auth_state', 'authState'),
    artifact_write_status: readString(record, 'artifact_write_status', 'artifactWriteStatus') ?? null,
    timing: isRecord(readField(record, 'timing')) ? (readField(record, 'timing') as Record<string, number | string>) : undefined,
  };
}

function normalizeFetchItem(record: UnknownRecord, index: number): FetchResultItem | null {
  const questionText =
    readString(record, 'question_text', 'questionText', 'question', 'query', 'title') || undefined;
  const legacyResults = toRecordArray(readField(record, 'platform_results', 'platformResults', 'results', 'answers'))
    .map(normalizeFetchPlatformResult)
    .filter((item): item is FetchPlatformResult => Boolean(item));
  const packetResults = toRecordArray(readField(record, 'aio_platform_packets', 'aioPlatformPackets'))
    .map(normalizeFetchPlatformPacket)
    .filter((item): item is FetchPlatformPacket => Boolean(item));

  const mergedByPlatform = new Map<string, FetchPlatformResult>();
  legacyResults.forEach((result) => {
    mergedByPlatform.set(canonicalizeFetchPlatform(result.platform), result);
  });
  packetResults.forEach((packet) => {
    const platform = canonicalizeFetchPlatform(packet.platform);
    const merged = mergeFetchPlatformResult(mergedByPlatform.get(platform), packet);
    if (merged) {
      mergedByPlatform.set(platform, merged);
    }
  });
  const platformResults = Array.from(mergedByPlatform.values());

  if (!questionText && platformResults.length === 0) {
    return null;
  }

  return {
    question_id: readString(record, 'question_id', 'questionId', 'id') || `question_${index + 1}`,
    question_text: questionText || `问题 ${index + 1}`,
    platform_results: platformResults,
    aio_platform_packets: packetResults,
  };
}

export function buildFetchExportViewModel(content: FetchResultsCanvasContent): FetchExportViewModel {
  const rawItems = toRecordArray(
    readField(content.data as UnknownRecord, 'fetchResults', 'fetch_results', 'results', 'items')
  );
  const items = rawItems
    .map(normalizeFetchItem)
    .filter((item): item is FetchResultItem => Boolean(item));

  const rawPlatformStatus = isRecord(
    readField(content.data as UnknownRecord, 'platformStatus', 'platform_status')
  )
    ? (readField(content.data as UnknownRecord, 'platformStatus', 'platform_status') as UnknownRecord)
    : undefined;
  const platformStatusPlatforms = mergePlatformStatusSummaries(toRecordArray(readField(rawPlatformStatus, 'platforms'))
    .map(normalizePlatformStatusSummary)
    .filter((item): item is FetchPlatformStatusSummary => Boolean(item)));
  const platformStatuses = isRecord(readField(rawPlatformStatus, 'platform_statuses', 'platformStatuses'))
    ? Object.fromEntries(
        Object.entries(
          readField(rawPlatformStatus, 'platform_statuses', 'platformStatuses') as Record<string, unknown>
        ).map(([platform, value]) => [canonicalizeFetchPlatform(platform), normalizeFetchStatus(value)])
      )
    : undefined;
  const platformStatus: FetchPlatformStatusProjection | undefined =
    platformStatusPlatforms.length > 0 || platformStatuses
      ? {
          platforms: platformStatusPlatforms,
          platform_statuses: platformStatuses,
        }
      : undefined;

  const timingSummary = normalizeFetchTimingSummary(isRecord(
    readField(content.data as UnknownRecord, 'timingSummary', 'timing_summary')
  )
    ? ((readField(content.data as UnknownRecord, 'timingSummary', 'timing_summary') as UnknownRecord) as FetchTimingSummary)
    : undefined);

  const platformSet = new Set<string>();
  let successCount = 0;
  let failedCount = 0;
  let skippedCount = 0;
  items.forEach((item) => {
    item.platform_results.forEach((result) => {
      platformSet.add(canonicalizeFetchPlatform(result.platform));
      const status = normalizeFetchStatus(result.status ?? (result.success ? 'success' : 'failed'));
      if (status === 'success') {
        successCount += 1;
      } else if (status === 'skipped') {
        skippedCount += 1;
      } else if (status === 'failed') {
        failedCount += 1;
      }
    });
  });

  return {
    title: content.title || 'AI答案抓取',
    subtitle: '按照问题逐条归档 AI 平台抓取结果，保留答案、成功状态、引用来源与耗时元信息。',
    totalQuestions: items.length,
    totalPlatforms: platformSet.size,
    successCount,
    failedCount,
    skippedCount,
    items,
    platformStatus,
    timingSummary,
  };
}

function normalizeConfidenceFinding(record: UnknownRecord): ConfidenceSignalFinding | null {
  const title = readString(record, 'title', 'label');
  const description = readString(record, 'description', 'summary', 'reason');
  if (!title && !description) {
    return null;
  }
  return { title, description };
}

function normalizeConfidenceDimensionScore(record: UnknownRecord) {
  const label = readString(record, 'label', 'name', 'key');
  if (!label) {
    return null;
  }
  return {
    key: readString(record, 'key'),
    label,
    max_score: readNumber(record, 'max_score', 'maxScore'),
    score: readNumber(record, 'score'),
    confidence: readNumber(record, 'confidence'),
    reasoning: readString(record, 'reasoning', 'description'),
  };
}

function normalizeConfidenceRecommendation(record: UnknownRecord) {
  const title = readString(record, 'title', 'action');
  if (!title) {
    return null;
  }
  return {
    title,
    action: readString(record, 'action'),
    reason: readString(record, 'reason', 'description'),
  };
}

function normalizeDimensionScores(record: UnknownRecord): ConfidenceSignalDimensionScore[] {
  const scores: ConfidenceSignalDimensionScore[] = [];
  for (const item of toRecordArray(readField(record, 'dimension_scores', 'dimensionScores'))) {
    const normalized = normalizeConfidenceDimensionScore(item);
    if (normalized) {
      scores.push(normalized);
    }
  }
  return scores;
}

function normalizeRecommendations(record: UnknownRecord): ConfidenceSignalRecommendation[] {
  const recommendations: ConfidenceSignalRecommendation[] = [];
  for (const item of toRecordArray(readField(record, 'recommendations'))) {
    const normalized = normalizeConfidenceRecommendation(item);
    if (normalized) {
      recommendations.push(normalized);
    }
  }
  return recommendations;
}

function normalizeConfidenceItem(record: UnknownRecord, index: number): ConfidenceSignalItem | null {
  const itemId = readString(record, 'item_id', 'itemId', 'id') || `item_${index + 1}`;
  const label = readString(record, 'label', 'title', 'name', 'url', 'domain');
  if (!label) {
    return null;
  }

  return {
    item_id: itemId,
    item_origin:
      (readString(record, 'item_origin', 'itemOrigin') as ConfidenceSignalItem['item_origin']) ||
      'auto_citation',
    input_type:
      (readString(record, 'input_type', 'inputType') as ConfidenceSignalItem['input_type']) ||
      'url',
    label,
    url: readString(record, 'url'),
    domain: readString(record, 'domain'),
    site_name: readString(record, 'site_name', 'siteName'),
    is_official: readBoolean(record, 'is_official', 'isOfficial'),
    occurrences: readNumber(record, 'occurrences'),
    platforms: readStringList(record, 'platforms'),
    signal_level: readString(record, 'signal_level', 'signalLevel') as ConfidenceSignalItem['signal_level'],
    overall_score: readNumber(record, 'overall_score', 'overallScore'),
    overall_confidence: readNumber(record, 'overall_confidence', 'overallConfidence'),
    entity_classification:
      (readString(record, 'entity_classification', 'entityClassification') as ConfidenceSignalItem['entity_classification']) ||
      undefined,
    entity_label: readString(record, 'entity_label', 'entityLabel'),
    frequency: readNumber(record, 'frequency', 'count'),
    aice_score: readNumber(record, 'aice_score', 'aiceScore', 'score'),
    quadrant: readString(record, 'quadrant') as ConfidenceSignalItem['quadrant'],
    quadrant_label: readString(record, 'quadrant_label', 'quadrantLabel'),
    quadrant_description: readString(record, 'quadrant_description', 'quadrantDescription'),
    primary_reasons: readStringList(record, 'primary_reasons', 'primaryReasons', 'reasons'),
    repair_action: readString(record, 'repair_action', 'repairAction', 'action'),
    analysis_group: readString(record, 'analysis_group', 'analysisGroup', 'group'),
    top_signals: readStringList(record, 'top_signals', 'topSignals'),
    dimension_scores: normalizeDimensionScores(record),
    recommendations: normalizeRecommendations(record),
    status: readString(record, 'status') as ConfidenceSignalItem['status'],
    error_message: readString(record, 'error_message', 'errorMessage'),
    question_samples: readStringList(record, 'question_samples', 'questionSamples'),
    created_at: readString(record, 'created_at', 'createdAt'),
    raw_text: readString(record, 'raw_text', 'rawText'),
    crawl_readable: readBoolean(record, 'crawl_readable', 'crawlReadable'),
    http_status: readNumber(record, 'http_status', 'httpStatus') ?? null,
    has_h1: readBoolean(record, 'has_h1', 'hasH1'),
    h1_count: readNumber(record, 'h1_count', 'h1Count'),
    has_main: readBoolean(record, 'has_main', 'hasMain'),
    has_article: readBoolean(record, 'has_article', 'hasArticle'),
    schema_types: readStringList(record, 'schema_types', 'schemaTypes'),
    published_at: readString(record, 'published_at', 'publishedAt'),
  };
}

function normalizeConfidenceSummary(record: UnknownRecord | undefined): ConfidenceSignalSummary | undefined {
  if (!record) {
    return undefined;
  }
  return {
    total_citations: readNumber(record, 'total_citations', 'totalCitations'),
    evaluated_count: readNumber(record, 'evaluated_count', 'evaluatedCount'),
    failed_count: readNumber(record, 'failed_count', 'failedCount'),
    high_confidence_count: readNumber(record, 'high_confidence_count', 'highConfidenceCount'),
    neutral_count: readNumber(record, 'neutral_count', 'neutralCount'),
    caution_count: readNumber(record, 'caution_count', 'cautionCount'),
    manual_count: readNumber(record, 'manual_count', 'manualCount'),
    brand_count: readNumber(record, 'brand_count', 'brandCount'),
    competitor_count: readNumber(record, 'competitor_count', 'competitorCount'),
    general_knowledge_count: readNumber(record, 'general_knowledge_count', 'generalKnowledgeCount'),
    second_quadrant_count: readNumber(record, 'second_quadrant_count', 'secondQuadrantCount'),
    average_score: readNumber(record, 'average_score', 'averageScore'),
    average_confidence_score: readNumber(record, 'average_confidence_score', 'averageConfidenceScore'),
    vulnerable_source_count: readNumber(record, 'vulnerable_source_count', 'vulnerableSourceCount'),
    updated_at: readString(record, 'updated_at', 'updatedAt'),
  };
}

function normalizeConfidenceOverview(record: UnknownRecord | undefined): ConfidenceOverview | undefined {
  if (!record) {
    return undefined;
  }

  const representativeSources = toRecordArray(
    readField(record, 'representative_sources', 'representativeSources')
  ).map((item) => ({
    item_id: readString(item, 'item_id', 'itemId', 'id'),
    label: readString(item, 'label', 'title'),
    domain: readString(item, 'domain'),
    url: readString(item, 'url'),
    score: readNumber(item, 'score', 'aice_score', 'aiceScore'),
    frequency: readNumber(item, 'frequency', 'occurrences'),
  }));

  if (
    readNumber(record, 'average_confidence', 'averageConfidence') === undefined &&
    readNumber(record, 'weighted_average_confidence', 'weightedAverageConfidence') === undefined &&
    readNumber(record, 'source_count', 'sourceCount') === undefined &&
    representativeSources.length === 0
  ) {
    return undefined;
  }

  return {
    entity_label: readString(record, 'entity_label', 'entityLabel'),
    average_confidence: readNumber(record, 'average_confidence', 'averageConfidence'),
    weighted_average_confidence: readNumber(
      record,
      'weighted_average_confidence',
      'weightedAverageConfidence'
    ),
    source_count: readNumber(record, 'source_count', 'sourceCount'),
    low_confidence_source_count: readNumber(
      record,
      'low_confidence_source_count',
      'lowConfidenceSourceCount'
    ),
    representative_sources: representativeSources,
  };
}

function normalizeConfidencePattern(record: UnknownRecord): ConfidencePattern | null {
  const patternLabel = readString(record, 'pattern_label', 'patternLabel', 'title', 'label');
  if (!patternLabel) {
    return null;
  }
  return {
    pattern_key: readString(record, 'pattern_key', 'patternKey', 'key'),
    pattern_label: patternLabel,
    sample_count: readNumber(record, 'sample_count', 'sampleCount', 'count'),
    average_confidence: readNumber(record, 'average_confidence', 'averageConfidence'),
    weighted_average_confidence: readNumber(
      record,
      'weighted_average_confidence',
      'weightedAverageConfidence'
    ),
    affected_dimensions: readStringList(
      record,
      'affected_dimensions',
      'affectedDimensions',
      'dimensions'
    ),
    evidence_examples: toRecordArray(readField(record, 'evidence_examples', 'evidenceExamples')).map(
      (item) => ({
        label: readString(item, 'label', 'title'),
        domain: readString(item, 'domain'),
        score: readNumber(item, 'score', 'aice_score', 'aiceScore'),
        evidence: readString(item, 'evidence', 'summary', 'reason'),
      })
    ),
    suggestion: readString(record, 'suggestion', 'action', 'recommendation'),
  };
}

function normalizeStrategicRecommendation(
  record: UnknownRecord
): ConfidenceStrategicRecommendation | null {
  const title = readString(record, 'title', 'label');
  const action = readString(record, 'action');
  const reason = readString(record, 'reason', 'summary', 'description');
  if (!title && !action && !reason) {
    return null;
  }
  return { title, action, reason };
}

function extractConfidenceItems(data: UnknownRecord): ConfidenceSignalItem[] {
  const autoItems = toRecordArray(readField(data, 'auto_items', 'autoItems'))
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));
  const manualItems = toRecordArray(readField(data, 'manual_items', 'manualItems'))
    .map((item, index) => normalizeConfidenceItem(item, index + autoItems.length))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));

  return uniqueByKey([...autoItems, ...manualItems], (item) => item.item_id || item.label);
}

export function isConfidenceCanvasReport(content: ReportCanvasContent): boolean {
  const data = content.data as UnknownRecord;
  const reportKind = readString(data, 'report_kind', 'reportKind');
  const artifactKind = readString(data, 'artifact_kind', 'artifactKind');
  if (isConfidenceReportKind(reportKind) || isConfidenceReportKind(artifactKind)) {
    return true;
  }

  return Boolean(
    readField(data, 'matrix_config', 'matrixConfig') ||
    readField(data, 'quadrant_overview', 'quadrantOverview') ||
    readField(data, 'analysis_blocks', 'analysisBlocks') ||
    readField(data, 'auto_items', 'autoItems') ||
    readField(data, 'manual_items', 'manualItems')
  );
}

export function isSiteConfidenceCanvasReport(content: ReportCanvasContent): boolean {
  const data = content.data as UnknownRecord;
  const reportKind = readString(data, 'report_kind', 'reportKind');
  const artifactKind = readString(data, 'artifact_kind', 'artifactKind');
  return isSiteConfidenceReportKind(reportKind) || isSiteConfidenceReportKind(artifactKind);
}

export function buildConfidenceExportViewModel(content: ReportCanvasContent): ConfidenceExportViewModel {
  const data = content.data as UnknownRecord;
  const extraEvaluationRecord = isRecord(readField(data, 'extra_evaluation', 'extraEvaluation'))
    ? (readField(data, 'extra_evaluation', 'extraEvaluation') as UnknownRecord)
    : undefined;
  const findings = toRecordArray(readField(data, 'aggregate_findings', 'aggregateFindings', 'findings', 'key_findings'))
    .map(normalizeConfidenceFinding)
    .filter((item): item is ConfidenceSignalFinding => Boolean(item));
  const summary = normalizeConfidenceSummary(
    isRecord(readField(data, 'summary')) ? (readField(data, 'summary') as UnknownRecord) : undefined
  );
  const brandConfidenceOverview = normalizeConfidenceOverview(
    isRecord(readField(data, 'brand_confidence_overview', 'brandConfidenceOverview'))
      ? (readField(data, 'brand_confidence_overview', 'brandConfidenceOverview') as UnknownRecord)
      : undefined
  );
  const competitorConfidenceOverview = normalizeConfidenceOverview(
    isRecord(readField(data, 'competitor_confidence_overview', 'competitorConfidenceOverview'))
      ? (readField(data, 'competitor_confidence_overview', 'competitorConfidenceOverview') as UnknownRecord)
      : undefined
  );
  const brandLowConfidencePatterns = toRecordArray(
    readField(data, 'brand_low_confidence_patterns', 'brandLowConfidencePatterns')
  )
    .map(normalizeConfidencePattern)
    .filter((item): item is ConfidencePattern => Boolean(item));
  const competitorLowConfidencePatterns = toRecordArray(
    readField(data, 'competitor_low_confidence_patterns', 'competitorLowConfidencePatterns')
  )
    .map(normalizeConfidencePattern)
    .filter((item): item is ConfidencePattern => Boolean(item));
  const strategicRecommendations = toRecordArray(
    readField(data, 'strategic_recommendations', 'strategicRecommendations')
  )
    .map(normalizeStrategicRecommendation)
    .filter((item): item is ConfidenceStrategicRecommendation => Boolean(item));
  const items = extractConfidenceItems(data);
  const extraEvaluationItems = toRecordArray(
    readField(extraEvaluationRecord, 'items') ?? readField(data, 'manual_items', 'manualItems')
  )
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));

  return {
    title: readString(data, 'headline') || content.title || '置信度报告',
    subtitle: readString(data, 'subtitle'),
    summary,
    overallConclusion: readString(data, 'overall_conclusion', 'overallConclusion'),
    findings,
    brandConfidenceOverview,
    competitorConfidenceOverview,
    brandLowConfidencePatterns,
    competitorLowConfidencePatterns,
    strategicRecommendations,
    extraEvaluation: extraEvaluationItems.length > 0
      ? {
          count: readNumber(extraEvaluationRecord, 'count') ?? extraEvaluationItems.length,
          items: extraEvaluationItems,
        }
      : undefined,
    items,
  };
}
