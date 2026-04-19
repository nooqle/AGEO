const STAGE_LABELS: Record<string, string> = {
  a0: '分析编排',
  orchestrator: '分析编排',
  general_react: '分析编排',
  brand_analysis: '品牌档案分析',
  brand_profile: '品牌档案分析',
  a1: '品牌档案分析',
  persona_generation: '用户画像分析',
  persona_selection: '用户画像分析',
  a2: '用户画像分析',
  question_simulation: '问题生成',
  question_generation: '问题生成',
  a3: '问题生成',
  answer_fetch: '答案抓取',
  fetch_results: '答案抓取',
  data_collection: '答案抓取',
  a4: '答案抓取',
  data_analytics: '报告生成',
  analysis_report: '报告生成',
  analysis_report_skill: '报告生成',
  a5: '报告生成',
  site_confidence_assessment_skill: '官网 AI 友好度',
  site_confidence_assessment_executor: '官网 AI 友好度',
  site_confidence_assessment: '官网 AI 友好度',
  a7: '官网 AI 友好度',
  wait_for_user: '等待你的确认',
  waiting_input: '等待你的确认',
  post_analysis_skill: '追问分析',
  drill_down_analysis: '追问分析',
  compare_analysis: '结果对比',
  table_intake: '表格导入分析',
  apply_import_action: '导入结果处理',
};

function normalizeStageKey(stage: string): string {
  return stage.trim().toLowerCase().replace(/[\s-]+/g, '_');
}

export function getUserFacingStageLabel(stage?: string | null): string | undefined {
  if (!stage) return undefined;

  const normalized = normalizeStageKey(stage);
  if (STAGE_LABELS[normalized]) {
    return STAGE_LABELS[normalized];
  }

  const compact = normalized.replace(/[^a-z0-9_]/g, '');
  if (STAGE_LABELS[compact]) {
    return STAGE_LABELS[compact];
  }

  const match = compact.match(/^a([1-5])$/);
  if (match) {
    return STAGE_LABELS[`a${match[1]}`];
  }

  return stage;
}

export function sanitizeUserFacingWorkflowText(text?: string | null): string | undefined {
  if (!text) return undefined;

  return text
    .replace(/site_confidence_assessment_skill/g, '官网 AI 友好度')
    .replace(/site_confidence_assessment_executor/g, '官网 AI 友好度')
    .replace(/官网置信度报告/g, '官网 AI 友好度报告')
    .replace(/官网置信度评估/g, '官网 AI 友好度')
    .replace(/引用置信度评估/g, '来源引用分析');
}
