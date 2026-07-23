/**
 * Wave D + Q: conservative Chat → production-line orchestration intent probe.
 * Pure functions only. Prefer miss over false intercept of main analysis chat.
 */

export type ChatTopologyIntentKind = 'compile_nl' | 'recipe_suggest';

export type ChatTopologyIntent = {
  kind: ChatTopologyIntentKind | null;
  /** machine reason for tests / debug */
  reason: string;
};

/** Default max length for unprefixed free text (still conservative). */
const MAX_LEN = 120;
/** Prefixed /编排|@生产线 commands may be slightly longer for full-line instructions. */
const MAX_LEN_PREFIXED = 200;

/** Explicit opt-in prefixes (strip before sending to compile-nl). */
const PREFIX_RE = /^(?:\/(?:编排|生产线)|@生产线)\s+/;

const MAIN_FLOW_RE =
  /分析品牌|品牌分析|生成报告|执行摘要|用户画像|问题集|抓取答案|品牌全景|深度分析|竞品分析/;

const RECIPE_RE =
  /推荐配方|换(?:一个)?配方|套用配方|有什么配方|配方列表|用.+配方|切换配方|配方建议|按配方重建/;

/** Wave Q: full-line / generate-topology phrasing (still not main analysis). */
const FULL_LINE_RE =
  /搭(?:一条|个)?生产线|生成整图|生成整条线|重建生产线|按这张图|整条生产线|生产线干法/;

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

  const hasPrefix = PREFIX_RE.test(text);
  const maxLen = hasPrefix ? MAX_LEN_PREFIXED : MAX_LEN;
  if (text.length > maxLen) {
    return { kind: null, reason: 'too_long' };
  }

  const body = stripChatTopologyPrefix(text);

  // Explicit prefix always routes to compile (remaining text can be empty → still compile path with full original stripped)
  if (hasPrefix) {
    if (RECIPE_RE.test(body) || RECIPE_RE.test(text)) {
      return { kind: 'recipe_suggest', reason: 'prefix_recipe' };
    }
    if (FULL_LINE_RE.test(body) && /配方/.test(body)) {
      return { kind: 'recipe_suggest', reason: 'prefix_full_line_recipe' };
    }
    return { kind: 'compile_nl', reason: 'prefix' };
  }

  // Do not steal main analysis / report language unless recipe/compile signals dominate
  if (MAIN_FLOW_RE.test(text) && !RECIPE_RE.test(text) && !COMPILE_STRONG_RE.test(text) && !FULL_LINE_RE.test(text)) {
    return { kind: null, reason: 'main_flow' };
  }

  if (RECIPE_RE.test(text)) {
    return { kind: 'recipe_suggest', reason: 'recipe_kw' };
  }

  // Full-line phrasing without "分析/报告" → prefer recipe pool first (org SOP memory)
  if (FULL_LINE_RE.test(text) && /配方|套用|推荐/.test(text)) {
    return { kind: 'recipe_suggest', reason: 'full_line_recipe' };
  }
  if (FULL_LINE_RE.test(text)) {
    return { kind: 'compile_nl', reason: 'full_line' };
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
