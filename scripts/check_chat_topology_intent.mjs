/**
 * Wave D: lightweight node checks for chatTopologyIntent rules.
 * Keep in sync with frontend/src/lib/chatTopologyIntent.ts (manual mirror of classify logic).
 * Run: node scripts/check_chat_topology_intent.mjs
 */

const MAX_LEN = 120;
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

function classify(raw) {
  const text = String(raw || '').trim();
  if (!text) return { kind: null, reason: 'empty' };
  if (text.length > MAX_LEN) return { kind: null, reason: 'too_long' };
  const hasPrefix = PREFIX_RE.test(text);
  const body = text.replace(PREFIX_RE, '').trim();
  if (hasPrefix) {
    if (RECIPE_RE.test(body) || RECIPE_RE.test(text)) {
      return { kind: 'recipe_suggest', reason: 'prefix_recipe' };
    }
    return { kind: 'compile_nl', reason: 'prefix' };
  }
  if (MAIN_FLOW_RE.test(text) && !RECIPE_RE.test(text) && !COMPILE_STRONG_RE.test(text)) {
    return { kind: null, reason: 'main_flow' };
  }
  if (RECIPE_RE.test(text)) return { kind: 'recipe_suggest', reason: 'recipe_kw' };
  if (COMPILE_STRONG_RE.test(text) || COMPILE_PLATFORM_RE.test(text)) {
    return { kind: 'compile_nl', reason: 'topology_kw' };
  }
  if (LINE_RE.test(text) && /(?:改|调整|修改|跳过|恢复|断开|连上|关掉)/.test(text)) {
    return { kind: 'compile_nl', reason: 'line_edit_kw' };
  }
  return { kind: null, reason: 'no_match' };
}

const cases = [
  ['跳过豆包', 'compile_nl'],
  ['恢复全部平台', 'compile_nl'],
  ['/编排 跳过豆包', 'compile_nl'],
  ['推荐配方', 'recipe_suggest'],
  ['帮我分析品牌可见度并生成报告', null],
  ['今天天气怎么样', null],
  ['a'.repeat(200), null],
];

let failed = 0;
for (const [input, expected] of cases) {
  const got = classify(input).kind;
  if (got !== expected) {
    console.error('FAIL', JSON.stringify(input), 'expected', expected, 'got', got);
    failed += 1;
  }
}

if (failed) {
  console.error(`check_chat_topology_intent: ${failed} failed`);
  process.exit(1);
}
console.log(`check_chat_topology_intent: ${cases.length} passed`);
