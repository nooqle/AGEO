/** Stable canvas constants (keep in sync with backend topology gates). */
import type {
  CustomFlowNodeType,
  FlowAnalysisDimension,
  FlowNodeStatus,
} from './types';

export const PLATFORM_META: Array<{ id: string; label: string }> = [
  { id: 'deepseek', label: 'DeepSeek' },
  { id: 'kimi', label: 'Kimi' },
  { id: 'doubao', label: '豆包' },
  { id: 'hunyuan', label: '腾讯元宝' },
];

export const NODE_DEFINITIONS: Array<{
  id: string;
  label: string;
  icon: string;
  variant: 'asset' | 'process';
  description: string;
  position: { x: number; y: number };
}> = [
  {
    id: 'question-set',
    label: '问题集',
    icon: 'list',
    variant: 'asset',
    description: '本轮采集使用的题目来源。默认由系统按品牌生成问题集，也可以上传自己的问题文件。',
    position: { x: 0, y: 0 },
  },
  {
    id: 'lexicon',
    label: '实体词库',
    icon: 'database',
    variant: 'asset',
    description: '回答分析时的品牌实体识别范围。词库在品牌圈层页的实体词库标签中维护。',
    position: { x: 0, y: 250 },
  },
  {
    id: 'fetch',
    label: '答案采集',
    icon: 'workflow',
    variant: 'process',
    description: '把问题逐条投给各个 AI 平台，复现真实用户看到的回答。',
    position: { x: 320, y: 40 },
  },
  {
    id: 'extract',
    label: '实体抽取与校准',
    icon: 'scan',
    variant: 'process',
    description: '从回答原文中识别与品牌相关的实体和关系，并按样本量校准置信度。',
    position: { x: 320, y: 300 },
  },
  {
    id: 'projection',
    label: '图谱构建',
    icon: 'orbit',
    variant: 'process',
    description: '把校准后的实体按与品牌的距离排布成圈层图谱。',
    position: { x: 660, y: 330 },
  },
  {
    id: 'report',
    label: '报告生成',
    icon: 'file',
    variant: 'process',
    description: '基于图谱与原文证据生成可交付的解读报告。',
    position: { x: 980, y: 330 },
  },
];

export const PLATFORM_POSITIONS = [
  { x: 660, y: -110 },
  { x: 660, y: -30 },
  { x: 660, y: 50 },
  { x: 660, y: 130 },
];

export const STATUS_TEXT: Record<FlowNodeStatus, string> = {
  idle: '待运行',
  active: '运行中',
  done: '已完成',
  failed: '失败',
  skipped: '计划跳过',
};

export const ALL_PLATFORM_IDS = PLATFORM_META.map((item) => item.id);
export const PLATFORMS_STORAGE_PREFIX = 'amway-flow-platforms:';

export const GUIDE_STORAGE_KEY = 'amway-flow-guide-seen';
export const TOPOLOGY_STORAGE_PREFIX = 'amway-flow-topology:';
export const MAX_CUSTOM_NODES = 20;

export const EDGE_DEFS: Array<{ id: string; source: string; target: string }> = [
  { id: 'e-questions-fetch', source: 'question-set', target: 'fetch' },
  { id: 'e-lexicon-extract', source: 'lexicon', target: 'extract' },
  { id: 'e-fetch-extract', source: 'fetch', target: 'extract' },
  { id: 'e-extract-projection', source: 'extract', target: 'projection' },
  { id: 'e-projection-report', source: 'projection', target: 'report' },
  ...PLATFORM_META.map((platform) => ({
    id: `e-fetch-${platform.id}`,
    source: 'fetch',
    target: `platform-${platform.id}`,
  })),
];

// ===== Phase 3a 连线改接：端口类型系统 + DAG 环校验 =====
// 产出物类型：连线只能从"输出类型"连到"接受该类型"的输入端口。
export const BUILTIN_OUTPUT_TYPE: Record<string, string> = {
  'question-set': 'questions',
  lexicon: 'lexicon',
  fetch: 'answers',
  extract: 'entities',
  // P2-1: domain-agnostic port name (legacy alias "circle" still accepted below)
  projection: 'entity_graph',
  report: 'report',
};

export const BUILTIN_ACCEPTED_INPUTS: Record<string, string[]> = {
  fetch: ['questions'],
  extract: ['lexicon', 'answers'],
  projection: ['entities'],
  report: ['entity_graph', 'circle'],
};

export const CUSTOM_NODE_OUTPUT_TYPE: Record<CustomFlowNodeType, string> = {
  analysis: 'analysis',
  content: 'content',
};

export const CUSTOM_NODE_ACCEPTED_INPUTS: Record<CustomFlowNodeType, string[]> = {
  analysis: ['entity_graph', 'circle', 'report'],
  content: ['lexicon', 'analysis'],
};

export const ANALYSIS_DIMENSION_META: Record<FlowAnalysisDimension, { label: string; hint: string }> = {
  platform: { label: '平台覆盖', hint: '各平台有效回答与请求覆盖对比' },
  entities: { label: '高频实体', hint: '按回答数排序的实体 Top 10 与轨道分布' },
  risk: { label: '风险信号', hint: '风险轨节点与监管相关信号汇总' },
};

export const DEFAULT_ANALYSIS_DIMENSIONS: FlowAnalysisDimension[] = [
  'platform',
  'entities',
  'risk',
];

export const CUSTOM_NODE_META: Record<CustomFlowNodeType, {
  label: string;
  icon: string;
  description: string;
  libraryHint: string;
}> = {
  analysis: {
    label: '数据分析',
    icon: 'chart',
    description: '接入圈层图或报告原文做二级解读，产出分析结论卡片。',
    libraryHint: '对圈层/报告做二级解读',
  },
  content: {
    label: '内容创作',
    icon: 'pen',
    description: '基于实体词库与分析结论起草内容文案。',
    libraryHint: '基于词库/分析起草文案',
  },
};

// 内容创作节点默认 prompt 模板（3a 占位：可编辑、可预览，执行能力规划中）
export const DEFAULT_CONTENT_PROMPT_TEMPLATE = `你是一位熟悉 {{centerTerm}} 品牌的内容策划。
请基于以下输入起草一篇内容文案：
- 实体词库：{{entities}}
- 分析结论：{{analysis}}
要求：口吻自然、避免夸大宣传、符合广告法规范。`;
