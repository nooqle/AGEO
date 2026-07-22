/**
 * Wave D: conservative Chat → production-line orchestration intent probe.
 * Pure functions only. Prefer miss over false intercept of main analysis chat.
 */

export type ChatTopologyIntentKind = 'compile_nl' | 'recipe_suggest';

export type ChatTopologyIntent = {
  kind: ChatTopologyIntentKind | null;
  /** machine reason for tests / debug */
  reason: string;
};

const MAX_LEN = 120;

/** Explicit opt-in prefixes (strip before sending to compile-nl). */
const PREFIX_RE = /^(?:\/(?:编排|生产线)|@生产线)\s+/;

const MAIN_FLOW_RE =
  /分析品牌|品牌分析|生成报告|执行摘要|用户画像|问题集|抓取答案|品牌全景|深度分析|竞品分析/;

const RECIPE_RE =
  /推荐配方|换(?:一个)?配方|套用配方|有什么配方|配方列表|用.+配方|切换配方|配方建议/;

const COMPILE_STRONG_RE =
  /跳过豆包|禁用豆包|不要跑豆包|不要抓豆包|恢复全部平台|恢复所有平台|加(?:一个)?图谱分析|加(?:一个)?分析节点|关掉豆包/;

const COMPILE_PLATFORM_RE =
  /(?:跳过|禁用|不要抓|不要跑|关掉|关闭|恢复|启用|打开).{0,12}(?:豆包|deepseek|kimi|元宝|混元|平台)/i;

const LINE_RE = /生产线|拓扑|编排|采集连线/;

export function stripChatTopologyPrefix(text: string): string {
  return String(text || '').trim().replace(PREFIX_RE, '').trim();
}

/**
 * Classify whether Chat should short-circuit to compile/recipe APIs.
 * Returns kind=null when the message should go to the normal agent path.
 */
export function classifyChatTopologyIntent(raw: string): ChatTopologyIntent {
  const text = String(raw || '').trim();
  if (!text) {
    return { kind: null, reason: 'empty' };
  }
  if (text.length > MAX_LEN) {
    return { kind: null, reason: 'too_long' };
  }

  const hasPrefix = PREFIX_RE.test(text);
  const body = stripChatTopologyPrefix(text);

  // Explicit prefix always routes to compile (remaining text can be empty → still compile path with full original stripped)
  if (hasPrefix) {
    if (RECIPE_RE.test(body) || RECIPE_RE.test(text)) {
      return { kind: 'recipe_suggest', reason: 'prefix_recipe' };
    }
    return { kind: 'compile_nl', reason: 'prefix' };
  }

  // Do not steal main analysis / report language unless recipe/compile signals dominate
  if (MAIN_FLOW_RE.test(text) && !RECIPE_RE.test(text) && !COMPILE_STRONG_RE.test(text)) {
    return { kind: null, reason: 'main_flow' };
  }

  if (RECIPE_RE.test(text)) {
    return { kind: 'recipe_suggest', reason: 'recipe_kw' };
  }

  if (COMPILE_STRONG_RE.test(text) || COMPILE_PLATFORM_RE.test(text)) {
    return { kind: 'compile_nl', reason: 'topology_kw' };
  }

  // Weak line keywords alone are not enough (avoid "生产线怎么样" style false positives)
  if (LINE_RE.test(text) && /(?:改|调整|修改|跳过|恢复|断开|连上|关掉)/.test(text)) {
    return { kind: 'compile_nl', reason: 'line_edit_kw' };
  }

  return { kind: null, reason: 'no_match' };
}

export function buildProductionLineHref(entityId: string): string {
  const qs = new URLSearchParams({
    entity_id: entityId,
    view: 'flow',
  });
  return `/amwaychina?${qs.toString()}`;
}
