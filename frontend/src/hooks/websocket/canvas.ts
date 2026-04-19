import type { CanvasContentDataMap, CanvasContentType, CanvasPreviewMetricValue } from '@/types/canvas';

export const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const PREVIEW_METRIC_PRIORITY = [
  '品牌提及率',
  '官网引用率',
  '缺席高价值场景',
  '高风险场景',
  '有效场景数',
  '覆盖平台数',
] as const;

function normalizePreviewMetricLabel(key: string): string | null {
  const normalized = key.trim().toLowerCase();
  if (!normalized) return null;
  if (['bwvs', 'bwvs_index', 'overallscore', 'overall_score', 'scoreband', 'score_band', 'bwvs指数', 'bwvs 指数', 'total_questions', 'totalquestions', '总问题数', 'total_mentions', 'totalmentions', '总提及数'].includes(normalized)) {
    return null;
  }
  if (['brand_mention_rate', 'mention_rate', 'mentionrate', '提及率', '品牌提及率'].includes(normalized)) {
    return '品牌提及率';
  }
  if (['official_citation_rate', 'officialcitationrate', '官网引用率'].includes(normalized)) {
    return '官网引用率';
  }
  if (['platform_coverage_count', 'platformcoveragecount', '覆盖平台数'].includes(normalized)) {
    return '覆盖平台数';
  }
  if (['scenario_hit_count', 'scenariohitcount', '有效场景数'].includes(normalized)) {
    return '有效场景数';
  }
  if (['missing_high_value_scenario_count', 'missinghighvaluescenariocount', '缺席高价值场景'].includes(normalized)) {
    return '缺席高价值场景';
  }
  if (['high_risk_scenario_count', 'highriskscenariocount', '高风险场景'].includes(normalized)) {
    return '高风险场景';
  }
  return key;
}

function normalizePreviewMetricValue(label: string, value: unknown, unit?: unknown): CanvasPreviewMetricValue {
  const numeric = typeof value === 'number'
    ? value
    : typeof value === 'string'
    ? Number(value.replace('%', '').trim())
    : NaN;

  const isRatio = unit === 'ratio' || label === '品牌提及率' || label === '官网引用率';

  if (Number.isFinite(numeric)) {
    if (isRatio) {
      const ratio = numeric <= 1 ? numeric * 100 : numeric;
      return `${ratio.toFixed(1)}%`;
    }
    return Number.isInteger(numeric) ? numeric : Number(numeric.toFixed(1));
  }

  return value as CanvasPreviewMetricValue;
}

function readPreviewMetricsFromStructuredSummary(raw: Record<string, unknown>): Record<string, CanvasPreviewMetricValue> | null {
  const summarySection = Array.isArray(raw.sections)
    ? raw.sections.find(
        (section) =>
          isRecord(section) &&
          section.section_name === 'summary' &&
          isRecord(section.data) &&
          Array.isArray(section.data.metrics)
      )
    : null;
  const canonicalMetrics =
    isRecord(summarySection) && isRecord(summarySection.data) && Array.isArray(summarySection.data.metrics)
      ? summarySection.data.metrics
      : null;
  const summary =
    canonicalMetrics
      ? { metrics: canonicalMetrics }
      : isRecord(raw.report_v2)
      ? (isRecord(raw.report_v2.summary) ? raw.report_v2.summary : null)
      : isRecord(raw.report_summary)
      ? raw.report_summary
      : null;

  const metricArray = Array.isArray(summary?.metrics) ? summary.metrics : null;
  if (!metricArray || metricArray.length === 0) {
    return null;
  }

  const entries = metricArray
    .filter(isRecord)
    .map((metric) => {
      const label = typeof metric.label === 'string' ? normalizePreviewMetricLabel(metric.label) : null;
      if (!label) {
        return null;
      }
      return [label, normalizePreviewMetricValue(label, metric.value, metric.unit)] as const;
    })
    .filter((entry): entry is readonly [string, CanvasPreviewMetricValue] => Boolean(entry));

  if (entries.length === 0) {
    return null;
  }

  const ordered = [...entries].sort((a, b) => {
    const aPriority = PREVIEW_METRIC_PRIORITY.indexOf(a[0] as typeof PREVIEW_METRIC_PRIORITY[number]);
    const bPriority = PREVIEW_METRIC_PRIORITY.indexOf(b[0] as typeof PREVIEW_METRIC_PRIORITY[number]);
    return (aPriority === -1 ? 999 : aPriority) - (bPriority === -1 ? 999 : bPriority);
  });

  return Object.fromEntries(ordered);
}

function normalizePreviewMetrics(raw: Record<string, unknown>): Record<string, CanvasPreviewMetricValue> | undefined {
  const structured = readPreviewMetricsFromStructuredSummary(raw);
  if (structured) {
    return structured;
  }

  const metrics = isRecord(raw.summary_metrics)
    ? raw.summary_metrics
    : isRecord(raw.metrics)
    ? raw.metrics
    : null;

  if (!metrics) {
    return undefined;
  }

  const normalizedEntries = Object.entries(metrics)
    .map(([key, value]) => {
      const label = normalizePreviewMetricLabel(key);
      if (!label) {
        return null;
      }
      return [label, normalizePreviewMetricValue(label, value)] as const;
    })
    .filter((entry): entry is readonly [string, CanvasPreviewMetricValue] => Boolean(entry))
    .sort((a, b) => {
      const aPriority = PREVIEW_METRIC_PRIORITY.indexOf(a[0] as typeof PREVIEW_METRIC_PRIORITY[number]);
      const bPriority = PREVIEW_METRIC_PRIORITY.indexOf(b[0] as typeof PREVIEW_METRIC_PRIORITY[number]);
      return (aPriority === -1 ? 999 : aPriority) - (bPriority === -1 ? 999 : bPriority);
    });

  return normalizedEntries.length > 0 ? Object.fromEntries(normalizedEntries) : undefined;
}

export const normalizePreviewData = (raw: Record<string, unknown>) => ({
  description: typeof raw.description === 'string' ? raw.description : undefined,
  metrics: normalizePreviewMetrics(raw),
  itemCount: typeof raw.itemCount === 'number'
    ? raw.itemCount
    : Array.isArray(raw.items)
    ? raw.items.length
    : undefined,
});
export const normalizeCanvasData = <T extends CanvasContentType>(
  type: T,
  raw: unknown
): CanvasContentDataMap[T] => {
  const data = isRecord(raw) ? raw : {};
  const preview = normalizePreviewData(data);

  if (type === 'report') {
    const insights = Array.isArray(data.insights)
      ? (data.insights as CanvasContentDataMap['report']['insights'])
      : undefined;
    const recommendations = Array.isArray(data.recommendations)
      ? (data.recommendations as CanvasContentDataMap['report']['recommendations'])
      : undefined;

    const rawBreakdown = isRecord(data.bwvs_breakdown) ? data.bwvs_breakdown : undefined;
    const bwvs_breakdown = rawBreakdown &&
      typeof rawBreakdown.mention_score === 'number' &&
      typeof rawBreakdown.sentiment_score === 'number' &&
      typeof rawBreakdown.coverage_score === 'number' &&
      typeof rawBreakdown.citation_score === 'number' &&
      isRecord(rawBreakdown.weights)
      ? (rawBreakdown as unknown as CanvasContentDataMap['report']['bwvs_breakdown'])
      : undefined;

    return {
      ...preview,
      report_kind: typeof data.report_kind === 'string' ? data.report_kind : undefined,
      artifact_kind: typeof data.artifact_kind === 'string' ? data.artifact_kind : undefined,
      title: typeof data.title === 'string' ? data.title : undefined,
      headline: typeof data.headline === 'string' ? data.headline : undefined,
      subtitle: typeof data.subtitle === 'string' ? data.subtitle : undefined,
      overallScore: typeof data.overallScore === 'number'
        ? data.overallScore
        : typeof data.overall_score === 'number'
        ? data.overall_score
        : undefined,
      scoreBand: typeof data.scoreBand === 'string'
        ? data.scoreBand
        : typeof data.score_band === 'string'
        ? data.score_band
        : undefined,
      metrics: isRecord(data.metrics)
        ? (data.metrics as Record<string, CanvasPreviewMetricValue>)
        : preview.metrics,
      insights,
      recommendations,
      content: typeof data.content === 'string' ? data.content : undefined,
      executive_summary: typeof data.executive_summary === 'string' ? data.executive_summary : undefined,
      report_markdown: typeof data.report_markdown === 'string' ? data.report_markdown : undefined,
      full_markdown: typeof data.full_markdown === 'string' ? data.full_markdown : undefined,
      sections: Array.isArray(data.sections) ? data.sections : undefined,
      metric_bundle: isRecord(data.metric_bundle) ? data.metric_bundle : undefined,
      comparison_bundle: isRecord(data.comparison_bundle) ? data.comparison_bundle : undefined,
      dashboard_projection: isRecord(data.dashboard_projection) ? data.dashboard_projection : undefined,
      bwvs_breakdown,
      brand_name: typeof data.brand_name === 'string' ? data.brand_name : undefined,
      analysis_period: typeof data.analysis_period === 'string' ? data.analysis_period : undefined,
      platform_scope: Array.isArray(data.platform_scope)
        ? data.platform_scope.filter((item): item is string => typeof item === 'string')
        : undefined,
      updated_at: typeof data.updated_at === 'string' ? data.updated_at : undefined,
      report_v2: isRecord(data.report_v2)
        ? (data.report_v2 as CanvasContentDataMap['report']['report_v2'])
        : undefined,
      report_summary: isRecord(data.report_summary)
        ? (data.report_summary as CanvasContentDataMap['report']['report_summary'])
        : undefined,
      scenario_coverage: isRecord(data.scenario_coverage)
        ? (data.scenario_coverage as CanvasContentDataMap['report']['scenario_coverage'])
        : undefined,
      competitor_battle: isRecord(data.competitor_battle)
        ? (data.competitor_battle as CanvasContentDataMap['report']['competitor_battle'])
        : undefined,
      risk_section: isRecord(data.risk_section)
        ? (data.risk_section as CanvasContentDataMap['report']['risk_section'])
        : undefined,
      source_section: isRecord(data.source_section)
        ? (data.source_section as CanvasContentDataMap['report']['source_section'])
        : undefined,
      action_queue_section: isRecord(data.action_queue_section)
        ? (data.action_queue_section as CanvasContentDataMap['report']['action_queue_section'])
        : undefined,
      insight_section: isRecord(data.insight_section)
        ? (data.insight_section as CanvasContentDataMap['report']['insight_section'])
        : undefined,
      summary_metrics: data.summary_metrics,
      scenario_matrix: data.scenario_matrix,
      competitor_battles: data.competitor_battles,
      risk_map: data.risk_map,
      action_queue: data.action_queue,
      source_overview: data.source_overview,
      mention_sentiment_analysis: data.mention_sentiment_analysis,
      key_findings: data.key_findings,
      strengths: data.strengths,
      weaknesses: data.weaknesses,
      opportunities: data.opportunities,
      threats: data.threats,
      action_plan: data.action_plan,
      actionable_recommendations: data.actionable_recommendations,
      platform_breakdown: data.platform_breakdown,
      sentiment_distribution: data.sentiment_distribution,
      industry_insights: data.industry_insights,
      platform_analysis: data.platform_analysis,
      competitor_deep_analysis: data.competitor_deep_analysis,
      risk_alerts: data.risk_alerts,
      delta_vs_previous: data.delta_vs_previous,
      competitor_bwvs: data.competitor_bwvs,
      report_data: data.report_data,
      metrics_raw: data.metrics_raw,
      _degradation_note: typeof data._degradation_note === 'string' ? data._degradation_note : undefined,
      citation_analysis: data.citation_analysis,
      keyword_analysis: data.keyword_analysis,
      summary: isRecord(data.summary)
        ? (data.summary as CanvasContentDataMap['report']['summary'])
        : undefined,
      auto_items: Array.isArray(data.auto_items)
        ? (data.auto_items as CanvasContentDataMap['report']['auto_items'])
        : undefined,
      manual_items: Array.isArray(data.manual_items)
        ? (data.manual_items as CanvasContentDataMap['report']['manual_items'])
        : undefined,
      aggregate_findings: Array.isArray(data.aggregate_findings)
        ? (data.aggregate_findings as CanvasContentDataMap['report']['aggregate_findings'])
        : undefined,
      composer: isRecord(data.composer)
        ? (data.composer as CanvasContentDataMap['report']['composer'])
        : undefined,
      status: isRecord(data.status)
        ? (data.status as CanvasContentDataMap['report']['status'])
        : undefined,
      brand_keywords: Array.isArray(data.brand_keywords)
        ? data.brand_keywords.filter((item): item is string => typeof item === 'string')
        : undefined,
      competitor_names: Array.isArray(data.competitor_names)
        ? data.competitor_names.filter((item): item is string => typeof item === 'string')
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'chart') {
    return {
      ...preview,
      chartType: typeof data.chartType === 'string'
        ? (data.chartType as CanvasContentDataMap['chart']['chartType'])
        : typeof data.chart_type === 'string'
        ? (data.chart_type as CanvasContentDataMap['chart']['chartType'])
        : undefined,
      data: Array.isArray(data.data)
        ? (data.data as CanvasContentDataMap['chart']['data'])
        : undefined,
      xAxisKey: typeof data.xAxisKey === 'string'
        ? data.xAxisKey
        : typeof data.x_axis_key === 'string'
        ? data.x_axis_key
        : undefined,
      valueKey: typeof data.valueKey === 'string'
        ? data.valueKey
        : typeof data.value_key === 'string'
        ? data.value_key
        : undefined,
      angleKey: typeof data.angleKey === 'string'
        ? data.angleKey
        : typeof data.angle_key === 'string'
        ? data.angle_key
        : undefined,
      series: Array.isArray(data.series)
        ? (data.series as CanvasContentDataMap['chart']['series'])
        : undefined,
      summary: typeof data.summary === 'string' ? data.summary : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'dataTable') {
    return {
      ...preview,
      artifact_kind: typeof data.artifact_kind === 'string' ? data.artifact_kind : undefined,
      brand_name: typeof data.brand_name === 'string' ? data.brand_name : undefined,
      analysis_period: typeof data.analysis_period === 'string' ? data.analysis_period : undefined,
      export_title: typeof data.export_title === 'string' ? data.export_title : undefined,
      truncated: typeof data.truncated === 'boolean' ? data.truncated : undefined,
      has_more_records: typeof data.has_more_records === 'boolean' ? data.has_more_records : undefined,
      export_limit: typeof data.export_limit === 'number' ? data.export_limit : undefined,
      columns: Array.isArray(data.columns)
        ? (data.columns as CanvasContentDataMap['dataTable']['columns'])
        : undefined,
      rows: Array.isArray(data.rows)
        ? (data.rows as CanvasContentDataMap['dataTable']['rows'])
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'pipeline') {
    return {
      ...preview,
      pipeline: data.pipeline && typeof data.pipeline === 'object'
        ? data.pipeline as CanvasContentDataMap['pipeline']['pipeline']
        : undefined,
      maxSelection: typeof data.maxSelection === 'number'
        ? data.maxSelection
        : typeof data.max_selection === 'number'
        ? data.max_selection
        : undefined,
      minSelection: typeof data.minSelection === 'number'
        ? data.minSelection
        : typeof data.min_selection === 'number'
        ? data.min_selection
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'workflow') {
    const statusOptions: Array<NonNullable<CanvasContentDataMap['workflow']['executionStatus']>> = [
      'idle',
      'running',
      'paused',
      'completed',
      'error',
    ];
    const rawStatus = typeof data.executionStatus === 'string'
      ? data.executionStatus
      : typeof data.execution_status === 'string'
      ? data.execution_status
      : undefined;
    const executionStatus = rawStatus && statusOptions.includes(rawStatus as NonNullable<CanvasContentDataMap['workflow']['executionStatus']>)
      ? (rawStatus as NonNullable<CanvasContentDataMap['workflow']['executionStatus']>)
      : undefined;

    return {
      ...preview,
      currentStep: typeof data.currentStep === 'string'
        ? data.currentStep
        : typeof data.current_step === 'string'
        ? data.current_step
        : undefined,
      executionStatus,
      completedSteps: Array.isArray(data.completedSteps)
        ? (data.completedSteps as CanvasContentDataMap['workflow']['completedSteps'])
        : Array.isArray(data.completed_steps)
        ? (data.completed_steps as CanvasContentDataMap['workflow']['completedSteps'])
        : undefined,
      brandProfile: isRecord(data.brandProfile)
        ? (data.brandProfile as CanvasContentDataMap['workflow']['brandProfile'])
        : undefined,
      brand_profile: isRecord(data.brand_profile)
        ? (data.brand_profile as CanvasContentDataMap['workflow']['brand_profile'])
        : undefined,
      competitors: Array.isArray(data.competitors)
        ? (data.competitors as CanvasContentDataMap['workflow']['competitors'])
        : undefined,
      competitive_landscape: isRecord(data.competitive_landscape)
        ? (data.competitive_landscape as CanvasContentDataMap['workflow']['competitive_landscape'])
        : undefined,
      personas: Array.isArray(data.personas)
        ? (data.personas as CanvasContentDataMap['workflow']['personas'])
        : undefined,
      user_personas: Array.isArray(data.user_personas)
        ? (data.user_personas as CanvasContentDataMap['workflow']['user_personas'])
        : undefined,
      brand_summary: isRecord(data.brand_summary)
        ? (data.brand_summary as CanvasContentDataMap['workflow']['brand_summary'])
        : undefined,
      selection: isRecord(data.selection)
        ? (data.selection as CanvasContentDataMap['workflow']['selection'])
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'questionList') {
    return {
      ...preview,
      questions: Array.isArray(data.questions)
        ? (data.questions as CanvasContentDataMap['questionList']['questions'])
        : undefined,
      simulatedQuestions: isRecord(data.simulatedQuestions)
        ? (data.simulatedQuestions as CanvasContentDataMap['questionList']['simulatedQuestions'])
        : isRecord(data.simulated_questions)
        ? (data.simulated_questions as CanvasContentDataMap['questionList']['simulatedQuestions'])
        : undefined,
      generationMode: typeof data.generationMode === 'string'
        ? data.generationMode
        : typeof data.generation_mode === 'string'
        ? data.generation_mode
        : undefined,
    } as CanvasContentDataMap[T];
  }

  return {
    ...preview,
    fetchResults: Array.isArray(data.fetchResults)
      ? (data.fetchResults as CanvasContentDataMap['fetchResults']['fetchResults'])
      : Array.isArray(data.fetch_results)
      ? (data.fetch_results as CanvasContentDataMap['fetchResults']['fetchResults'])
      : undefined,
    platformStatus: isRecord(data.platformStatus)
      ? (data.platformStatus as CanvasContentDataMap['fetchResults']['platformStatus'])
      : isRecord(data.platform_status)
      ? (data.platform_status as CanvasContentDataMap['fetchResults']['platformStatus'])
      : undefined,
    timingSummary: isRecord(data.timingSummary)
      ? (data.timingSummary as CanvasContentDataMap['fetchResults']['timingSummary'])
      : isRecord(data.timing_summary)
      ? (data.timing_summary as CanvasContentDataMap['fetchResults']['timingSummary'])
      : undefined,
  } as CanvasContentDataMap[T];
};







