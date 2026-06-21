import { api, type QuestionTableIntakeResult } from '@/services/api';
import type { OntologyAssociationCircleQuestion } from '@/types/ontology';
import type { UploadedAssociationQuestion } from './AmwayAssociationCircleDashboard';

const DEFAULT_CENTER_TERMS = ['安利', '安利中国', '纽崔莱'];

export async function parseUploadedQuestionTableViaBackend(
  file: File,
  centerTerms: string[],
): Promise<UploadedAssociationQuestion[]> {
  const uploaded = await api.uploadFile(file);
  if (!uploaded.id) {
    throw new Error('问题表格上传成功，但没有返回文件 ID。');
  }
  const result = await api.analyzeQuestionTable(uploaded.id);
  return normalizeQuestionTableResult(result, centerTerms);
}

function normalizeQuestionTableResult(
  result: QuestionTableIntakeResult,
  centerTerms: string[],
): UploadedAssociationQuestion[] {
  const rows = Array.isArray(result.normalized_payload?.questions)
    ? result.normalized_payload.questions
    : [];
  return rows
    .map((row, index) => {
      const text = stringField(row, 'text', 'core_question', 'question');
      if (!text) return null;
      const centerTermText = stringField(row, 'center_terms');
      const question: UploadedAssociationQuestion = {
        id: stringField(row, 'id', 'question_id') || `upload_ui_${String(index + 1).padStart(3, '0')}`,
        text,
        category: stringField(row, 'category') || stringField(row, 'mother_theme') || '上传问题',
        intent: stringField(row, 'intent', 'user_intent', 'monitoring_purpose'),
        stage: stringField(row, 'stage', 'decision_stage'),
        audience_segment: stringField(row, 'audience_segment', 'life_stage'),
        core_anxiety: stringField(row, 'core_anxiety'),
        life_scene: stringField(row, 'life_scene', 'touchpoint', 'mother_theme'),
        opportunity_point: stringField(row, 'opportunity_point', 'monitoring_purpose', 'mother_theme'),
        probe_type: stringField(row, 'probe_type', 'question_type'),
        mother_theme: stringField(row, 'mother_theme'),
        question_type: stringField(row, 'question_type'),
        mentions_amway: stringField(row, 'mentions_amway'),
        life_stage: stringField(row, 'life_stage'),
        four_have: stringField(row, 'four_have'),
        touchpoint: stringField(row, 'touchpoint'),
        monitoring_purpose: stringField(row, 'monitoring_purpose'),
        question_set_version: stringField(row, 'question_set_version') || 'uploaded_amway_gravity_circle_v1',
        center_terms: centerTermText ? splitCenterTerms(centerTermText) : centerTerms,
        metadata_status: 'pending_inference',
        source: 'uploaded_table',
      };
      question.metadata_status = hasVisibleAssociationTags(question) ? 'complete' : 'pending_inference';
      return question;
    })
    .filter((question): question is UploadedAssociationQuestion => Boolean(question));
}

export function normalizeAssociationQuestionForReview(
  row: OntologyAssociationCircleQuestion,
  index: number,
): UploadedAssociationQuestion | null {
  const record = row as Record<string, unknown>;
  const text = stringField(record, 'text', 'core_question', 'question', 'question_text');
  if (!text) return null;
  const centerTermText = stringField(record, 'center_terms');
  const centerTerms = Array.isArray(row.center_terms)
    ? row.center_terms.map(String).filter(Boolean)
    : splitCenterTerms(centerTermText);
  const question: UploadedAssociationQuestion = {
    id: stringField(record, 'id', 'question_id') || `report_question_${String(index + 1).padStart(3, '0')}`,
    text,
    category: stringField(record, 'category') || stringField(record, 'mother_theme') || '历史问题',
    intent: stringField(record, 'intent', 'user_intent', 'monitoring_purpose'),
    stage: stringField(record, 'stage', 'decision_stage'),
    audience_segment: stringField(record, 'audience_segment', 'life_stage'),
    core_anxiety: stringField(record, 'core_anxiety'),
    life_scene: stringField(record, 'life_scene', 'touchpoint', 'mother_theme'),
    opportunity_point: stringField(record, 'opportunity_point', 'monitoring_purpose', 'mother_theme'),
    probe_type: stringField(record, 'probe_type', 'question_type'),
    mother_theme: stringField(record, 'mother_theme'),
    question_type: stringField(record, 'question_type'),
    mentions_amway: stringField(record, 'mentions_amway'),
    life_stage: stringField(record, 'life_stage'),
    four_have: stringField(record, 'four_have'),
    touchpoint: stringField(record, 'touchpoint'),
    monitoring_purpose: stringField(record, 'monitoring_purpose'),
    question_set_version: stringField(record, 'question_set_version'),
    center_terms: centerTerms.length ? centerTerms : DEFAULT_CENTER_TERMS,
    metadata_status: stringField(record, 'metadata_status') || 'from_latest_report',
    source: stringField(record, 'source') || 'latest_report_question_bank',
  };
  return question;
}

function stringField(row: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = row[key];
    if (value === null || value === undefined) continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return '';
}

export function parseUploadedQuestionFile(
  content: string,
  centerTerms: string[],
): UploadedAssociationQuestion[] {
  const normalizedContent = content.replace(/^\uFEFF/, '').trim();
  if (!normalizedContent) return [];

  const lines = normalizedContent
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
  if (!lines.length) return [];

  const delimiter = detectDelimiter(lines[0]);
  const firstCells = splitDelimitedLine(lines[0], delimiter).map(normalizeHeaderKey);
  const hasHeader = firstCells.some((cell) => QUESTION_TEXT_HEADER_KEYS.has(cell));

  if (!hasHeader) {
    return lines
      .map((line, index) => ({
        id: `upload_ui_${String(index + 1).padStart(3, '0')}`,
        text: cleanupQuestionLine(line),
        center_terms: centerTerms,
        source: 'uploaded_table',
      }))
      .filter((question) => question.text);
  }

  const headers = firstCells;
  const questionIndex = headers.findIndex((header) => QUESTION_TEXT_HEADER_KEYS.has(header));
  return lines
    .slice(1)
    .map((line, index) => {
      const cells = splitDelimitedLine(line, delimiter);
      const question: UploadedAssociationQuestion = {
        id: textAt(cells, headers, 'id') || `upload_ui_${String(index + 1).padStart(3, '0')}`,
        text: cleanupQuestionLine(cells[questionIndex] || ''),
        source: 'uploaded_table',
      };
      applyOptionalQuestionField(question, 'category', textAt(cells, headers, 'category'));
      applyOptionalQuestionField(question, 'intent', textAt(cells, headers, 'intent'));
      applyOptionalQuestionField(question, 'stage', textAt(cells, headers, 'stage'));
      applyOptionalQuestionField(question, 'audience_segment', textAt(cells, headers, 'audience_segment'));
      applyOptionalQuestionField(question, 'core_anxiety', textAt(cells, headers, 'core_anxiety'));
      applyOptionalQuestionField(question, 'life_scene', textAt(cells, headers, 'life_scene'));
      applyOptionalQuestionField(question, 'opportunity_point', textAt(cells, headers, 'opportunity_point'));
      applyOptionalQuestionField(question, 'probe_type', textAt(cells, headers, 'probe_type'));
      applyOptionalQuestionField(question, 'mother_theme', textAt(cells, headers, 'mother_theme'));
      applyOptionalQuestionField(question, 'question_type', textAt(cells, headers, 'question_type'));
      applyOptionalQuestionField(question, 'mentions_amway', textAt(cells, headers, 'mentions_amway'));
      applyOptionalQuestionField(question, 'life_stage', textAt(cells, headers, 'life_stage'));
      applyOptionalQuestionField(question, 'four_have', textAt(cells, headers, 'four_have'));
      applyOptionalQuestionField(question, 'touchpoint', textAt(cells, headers, 'touchpoint'));
      applyOptionalQuestionField(question, 'monitoring_purpose', textAt(cells, headers, 'monitoring_purpose'));
      applyOptionalQuestionField(question, 'question_set_version', textAt(cells, headers, 'question_set_version'));
      if (!question.audience_segment && question.life_stage) question.audience_segment = question.life_stage;
      if (!question.life_scene && question.touchpoint) question.life_scene = question.touchpoint;
      if (!question.opportunity_point && question.monitoring_purpose) question.opportunity_point = question.monitoring_purpose;
      if (!question.probe_type && question.question_type) question.probe_type = question.question_type;
      const centerTermText = textAt(cells, headers, 'center_terms');
      question.center_terms = centerTermText ? splitCenterTerms(centerTermText) : centerTerms;
      question.metadata_status = hasCoreAssociationTags(question) ? 'complete' : 'pending_inference';
      return question;
    })
    .filter((question) => question.text);
}

const QUESTION_TEXT_HEADER_KEYS = new Set(['question', 'question_text', 'core_question', 'text', '问题', '问题文本', '用户问题', '模拟问题']);

const HEADER_ALIASES: Record<string, string> = {
  question: 'question',
  question_text: 'question',
  core_question: 'question',
  text: 'question',
  问题: 'question',
  问题文本: 'question',
  用户问题: 'question',
  模拟问题: 'question',
  id: 'id',
  question_id: 'id',
  qid: 'id',
  编号: 'id',
  题号: 'id',
  category: 'category',
  scene: 'category',
  场景: 'life_scene',
  类别: 'category',
  母题: 'mother_theme',
  mother_theme: 'mother_theme',
  theme: 'mother_theme',
  intent: 'intent',
  user_intent: 'intent',
  意图: 'intent',
  主要监测目的: 'monitoring_purpose',
  监测目的: 'monitoring_purpose',
  monitoring_purpose: 'monitoring_purpose',
  stage: 'stage',
  decision_stage: 'stage',
  阶段: 'stage',
  audience_segment: 'audience_segment',
  人群: 'audience_segment',
  目标人群: 'audience_segment',
  '年龄/人生阶段': 'life_stage',
  年龄人生阶段: 'life_stage',
  年龄_人生阶段: 'life_stage',
  人生阶段: 'life_stage',
  life_stage: 'life_stage',
  core_anxiety: 'core_anxiety',
  核心焦虑: 'core_anxiety',
  焦虑: 'core_anxiety',
  life_scene: 'life_scene',
  生活场景: 'life_scene',
  对应触点: 'touchpoint',
  触点: 'touchpoint',
  touchpoint: 'touchpoint',
  opportunity_point: 'opportunity_point',
  机会点: 'opportunity_point',
  probe_type: 'probe_type',
  探针类型: 'probe_type',
  问题类型: 'question_type',
  question_type: 'question_type',
  是否点名安利: 'mentions_amway',
  mentions_amway: 'mentions_amway',
  对应四有: 'four_have',
  四有: 'four_have',
  four_have: 'four_have',
  center_terms: 'center_terms',
  中心词: 'center_terms',
  中心品牌: 'center_terms',
  question_set_version: 'question_set_version',
  问题版本: 'question_set_version',
};

function normalizeHeaderKey(value: string): string {
  const normalized = value.trim().replace(/^\uFEFF/, '').toLowerCase();
  return HEADER_ALIASES[normalized] || normalized;
}

function detectDelimiter(line: string): ',' | '\t' {
  return line.includes('\t') ? '\t' : ',';
}

function splitDelimitedLine(line: string, delimiter: ',' | '\t'): string[] {
  if (delimiter === '\t') {
    return line.split('\t').map((cell) => cell.trim());
  }
  const cells: string[] = [];
  let current = '';
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    const nextChar = line[index + 1];
    if (char === '"' && quoted && nextChar === '"') {
      current += '"';
      index += 1;
      continue;
    }
    if (char === '"') {
      quoted = !quoted;
      continue;
    }
    if (char === ',' && !quoted) {
      cells.push(current.trim());
      current = '';
      continue;
    }
    current += char;
  }
  cells.push(current.trim());
  return cells;
}

function textAt(cells: string[], headers: string[], canonicalKey: string): string {
  const index = headers.findIndex((header) => header === canonicalKey);
  return index >= 0 ? String(cells[index] || '').trim() : '';
}

function cleanupQuestionLine(line: string): string {
  return line
    .replace(/^\s*(?:\d+[\.\)、)]|[-*])\s*/, '')
    .trim();
}

function applyOptionalQuestionField(
  question: UploadedAssociationQuestion,
  field: keyof UploadedAssociationQuestion,
  value: string,
) {
  if (!value) return;
  if (field === 'center_terms') {
    question.center_terms = splitCenterTerms(value);
    return;
  }
  question[field] = value as never;
}

function splitCenterTerms(value: string): string[] {
  const terms = value
    .split(/[、;；|/]/)
    .map((item) => item.trim())
    .filter(Boolean);
  return terms.length ? terms : DEFAULT_CENTER_TERMS;
}

function hasCoreAssociationTags(question: UploadedAssociationQuestion): boolean {
  return Boolean(
    question.audience_segment &&
      question.core_anxiety &&
      question.life_scene &&
      question.opportunity_point &&
      question.probe_type,
  );
}

export function hasVisibleAssociationTags(question: UploadedAssociationQuestion): boolean {
  return Boolean(
    question.audience_segment &&
      question.life_scene &&
      question.opportunity_point &&
      question.probe_type,
  );
}

export function displayQuestionMetadataStatus(question: UploadedAssociationQuestion): string {
  if (question.source === 'latest_report_preview') return question.metadata_status || '来自最近报告';
  if (hasCoreAssociationTags(question)) return '标签完整';
  if (hasVisibleAssociationTags(question)) return '关键标签完整';
  return '待补标';
}
