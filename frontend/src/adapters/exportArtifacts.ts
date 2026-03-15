import type {
  ConfidenceAnalysisBlock,
  ConfidenceSignalDimensionScore,
  ConfidenceEcosystemMatrix,
  ConfidenceGeneralKnowledgeInsight,
  ConfidenceQuadrant,
  ConfidenceQuadrantOverview,
  ConfidenceRepairAction,
  ConfidenceSignalFinding,
  ConfidenceSignalItem,
  ConfidenceSignalRecommendation,
  ConfidenceSignalSummary,
  FetchCitation,
  FetchPlatformResult,
  FetchResultItem,
  FetchResultsCanvasContent,
  ReportCanvasContent,
} from '@/types/canvas';

type UnknownRecord = Record<string, unknown>;

export type FetchExportViewModel = {
  title: string;
  subtitle: string;
  totalQuestions: number;
  totalPlatforms: number;
  successCount: number;
  items: FetchResultItem[];
};

export type ConfidenceExportViewModel = {
  title: string;
  subtitle?: string;
  diagnosis?: string;
  summary?: ConfidenceSignalSummary;
  findings: ConfidenceSignalFinding[];
  quadrantOverview: ConfidenceQuadrantOverview[];
  analysisBlocks: ConfidenceAnalysisBlock[];
  repairActions: ConfidenceRepairAction[];
  generalKnowledgeInsight?: ConfidenceGeneralKnowledgeInsight;
  matrixConfig?: {
    aice_threshold?: number;
    frequency_threshold?: number;
  };
  ecosystemMatrix?: ConfidenceEcosystemMatrix;
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

function normalizeFetchPlatformResult(record: UnknownRecord): FetchPlatformResult | null {
  const platform =
    readString(record, 'platform', 'provider', 'engine', 'name', 'platform_id') || undefined;
  const answerRecord = isRecord(readField(record, 'answer', 'result')) ? (readField(record, 'answer', 'result') as UnknownRecord) : undefined;
  const success =
    readBoolean(record, 'success', 'ok') ??
    Boolean(answerRecord || readString(record, 'error', 'message') === undefined);

  if (!platform && !answerRecord && !readString(record, 'error', 'message')) {
    return null;
  }

  return {
    platform: platform || 'unknown',
    platform_name: readString(record, 'platform_name', 'platformName', 'display_name', 'displayName') || platform,
    fetch_method: readString(record, 'fetch_method', 'fetchMethod', 'method'),
    success,
    answer: answerRecord
      ? {
          content: readString(answerRecord, 'content', 'text', 'answer'),
          word_count: readNumber(answerRecord, 'word_count', 'wordCount', 'length'),
          has_brand_mention: readBoolean(answerRecord, 'has_brand_mention', 'hasBrandMention'),
        }
      : undefined,
    citations: toRecordArray(readField(record, 'citations', 'references', 'sources')).map(normalizeFetchCitation),
    error: readString(record, 'error', 'message'),
    duration: readNumber(record, 'duration', 'latency', 'elapsed'),
  };
}

function normalizeFetchItem(record: UnknownRecord, index: number): FetchResultItem | null {
  const questionText =
    readString(record, 'question_text', 'questionText', 'question', 'query', 'title') || undefined;
  const platformResults = toRecordArray(readField(record, 'platform_results', 'platformResults', 'results', 'answers'))
    .map(normalizeFetchPlatformResult)
    .filter((item): item is FetchPlatformResult => Boolean(item));

  if (!questionText && platformResults.length === 0) {
    return null;
  }

  return {
    question_id: readString(record, 'question_id', 'questionId', 'id') || `question_${index + 1}`,
    question_text: questionText || `问题 ${index + 1}`,
    platform_results: platformResults,
  };
}

export function buildFetchExportViewModel(content: FetchResultsCanvasContent): FetchExportViewModel {
  const rawItems = toRecordArray(
    readField(content.data as UnknownRecord, 'fetchResults', 'fetch_results', 'results', 'items')
  );
  const items = rawItems
    .map(normalizeFetchItem)
    .filter((item): item is FetchResultItem => Boolean(item));

  const platformSet = new Set<string>();
  let successCount = 0;
  items.forEach((item) => {
    item.platform_results.forEach((result) => {
      platformSet.add(result.platform_name || result.platform);
      if (result.success) {
        successCount += 1;
      }
    });
  });

  return {
    title: content.title || 'AI答案抓取',
    subtitle: '按照问题逐条归档 AI 平台抓取结果，保留答案、成功状态、引用来源与耗时元信息。',
    totalQuestions: items.length,
    totalPlatforms: platformSet.size,
    successCount,
    items,
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

function normalizeConfidenceQuadrant(record: UnknownRecord): ConfidenceQuadrantOverview | null {
  const quadrant = readString(record, 'quadrant', 'key') as ConfidenceQuadrant | undefined;
  if (!quadrant) {
    return null;
  }
  return {
    quadrant,
    quadrant_label: readString(record, 'quadrant_label', 'quadrantLabel', 'label'),
    description: readString(record, 'description', 'summary'),
    strategy: readString(record, 'strategy', 'action'),
    count: readNumber(record, 'count', 'item_count', 'itemCount'),
  };
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

function normalizeConfidenceBlock(record: UnknownRecord, index: number): ConfidenceAnalysisBlock | null {
  const key = readString(record, 'key', 'id') || `block_${index + 1}`;
  const items = toRecordArray(readField(record, 'items'))
    .map((item, itemIndex) => normalizeConfidenceItem(item, itemIndex))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));

  if (!key && items.length === 0) {
    return null;
  }

  return {
    key,
    title: readString(record, 'title', 'label'),
    description: readString(record, 'description', 'summary'),
    reason_label: readString(record, 'reason_label', 'reasonLabel'),
    action_label: readString(record, 'action_label', 'actionLabel'),
    item_count: readNumber(record, 'item_count', 'itemCount') ?? items.length,
    items,
  };
}

function normalizeRepairAction(record: UnknownRecord): ConfidenceRepairAction | null {
  const title = readString(record, 'title', 'action');
  if (!title) {
    return null;
  }
  return {
    priority: readString(record, 'priority'),
    title,
    summary: readString(record, 'summary', 'description', 'reason'),
    count: readNumber(record, 'count', 'item_count', 'itemCount'),
    related_item_ids: readStringList(record, 'related_item_ids', 'relatedItemIds'),
  };
}

function normalizeGeneralKnowledge(record: UnknownRecord | undefined): ConfidenceGeneralKnowledgeInsight | undefined {
  if (!record) {
    return undefined;
  }

  const topFrequencyItems = toRecordArray(readField(record, 'top_frequency_items', 'topFrequencyItems'))
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));
  const topScoreItems = toRecordArray(readField(record, 'top_score_items', 'topScoreItems'))
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));
  const representativeItems = toRecordArray(readField(record, 'representative_items', 'representativeItems'))
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));

  if (!readString(record, 'summary') && topFrequencyItems.length === 0 && topScoreItems.length === 0 && representativeItems.length === 0) {
    return undefined;
  }

  return {
    summary: readString(record, 'summary'),
    top_frequency_items: topFrequencyItems,
    top_score_items: topScoreItems,
    representative_items: representativeItems,
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

function extractConfidenceItems(data: UnknownRecord, blocks: ConfidenceAnalysisBlock[]): ConfidenceSignalItem[] {
  const autoItems = toRecordArray(readField(data, 'auto_items', 'autoItems'))
    .map((item, index) => normalizeConfidenceItem(item, index))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));
  const manualItems = toRecordArray(readField(data, 'manual_items', 'manualItems'))
    .map((item, index) => normalizeConfidenceItem(item, index + autoItems.length))
    .filter((item): item is ConfidenceSignalItem => Boolean(item));

  const blockItems = blocks.flatMap((block) => block.items || []);
  const merged = [...autoItems, ...manualItems];
  const effectiveItems = merged.length > 0 ? merged : blockItems;

  return uniqueByKey(effectiveItems, (item) => item.item_id || item.label);
}

export function isConfidenceCanvasReport(content: ReportCanvasContent): boolean {
  const data = content.data as UnknownRecord;
  const reportKind = readString(data, 'report_kind', 'reportKind');
  const artifactKind = readString(data, 'artifact_kind', 'artifactKind');
  if (reportKind === 'confidence_signal' || artifactKind === 'confidence_signal') {
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

export function buildConfidenceExportViewModel(content: ReportCanvasContent): ConfidenceExportViewModel {
  const data = content.data as UnknownRecord;
  const findings = toRecordArray(readField(data, 'aggregate_findings', 'aggregateFindings', 'findings', 'key_findings'))
    .map(normalizeConfidenceFinding)
    .filter((item): item is ConfidenceSignalFinding => Boolean(item));
  const quadrantOverview = toRecordArray(readField(data, 'quadrant_overview', 'quadrantOverview', 'quadrants'))
    .map(normalizeConfidenceQuadrant)
    .filter((item): item is ConfidenceQuadrantOverview => Boolean(item));
  const analysisBlocks = toRecordArray(readField(data, 'analysis_blocks', 'analysisBlocks', 'blocks'))
    .map(normalizeConfidenceBlock)
    .filter((item): item is ConfidenceAnalysisBlock => Boolean(item));
  const repairActions = toRecordArray(readField(data, 'repair_actions', 'repairActions', 'actions'))
    .map(normalizeRepairAction)
    .filter((item): item is ConfidenceRepairAction => Boolean(item));
  const generalKnowledgeInsight = normalizeGeneralKnowledge(
    isRecord(readField(data, 'general_knowledge_insight', 'generalKnowledgeInsight'))
      ? (readField(data, 'general_knowledge_insight', 'generalKnowledgeInsight') as UnknownRecord)
      : undefined
  );
  const summary = normalizeConfidenceSummary(
    isRecord(readField(data, 'summary')) ? (readField(data, 'summary') as UnknownRecord) : undefined
  );
  const matrixConfigRecord = isRecord(readField(data, 'matrix_config', 'matrixConfig'))
    ? (readField(data, 'matrix_config', 'matrixConfig') as UnknownRecord)
    : undefined;
  const ecosystemMatrixRecord = isRecord(readField(data, 'ecosystem_matrix', 'ecosystemMatrix'))
    ? (readField(data, 'ecosystem_matrix', 'ecosystemMatrix') as UnknownRecord)
    : undefined;
  const items = extractConfidenceItems(data, analysisBlocks);

  return {
    title: readString(data, 'headline') || content.title || '置信度报告',
    subtitle: readString(data, 'subtitle'),
    diagnosis: readString(data, 'diagnosis') || readString(ecosystemMatrixRecord, 'diagnosis'),
    summary,
    findings,
    quadrantOverview,
    analysisBlocks,
    repairActions,
    generalKnowledgeInsight,
    matrixConfig: matrixConfigRecord
      ? {
          aice_threshold: readNumber(matrixConfigRecord, 'aice_threshold', 'aiceThreshold'),
          frequency_threshold: readNumber(matrixConfigRecord, 'frequency_threshold', 'frequencyThreshold'),
        }
      : undefined,
    ecosystemMatrix: ecosystemMatrixRecord
      ? {
          title: readString(ecosystemMatrixRecord, 'title'),
          x_axis_label: readString(ecosystemMatrixRecord, 'x_axis_label', 'xAxisLabel'),
          y_axis_label: readString(ecosystemMatrixRecord, 'y_axis_label', 'yAxisLabel'),
          total_points: readNumber(ecosystemMatrixRecord, 'total_points', 'totalPoints'),
          diagnosis: readString(ecosystemMatrixRecord, 'diagnosis'),
        }
      : undefined,
    items,
  };
}
