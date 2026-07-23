/**
 * Wave E1: single source of journey language for production line + Chat.
 * Prefer these strings over ad-hoc synonyms (ops / topology / version in happy path).
 */

export const JOURNEY = {
  /** Three steps for newcomers */
  stepsOneLiner: '定干法 → 运行 → 看证据（可选：存为配方）',

  productionLine: '生产线',
  recipe: '配方',
  orchestration: '编排',
  recentChanges: '最近变更',

  /** Panel headers */
  orchTitle: '编排',
  orchSubtitle: '① 配方记住怎么干　② 改当前生产线　③ 点「开始运行」即按图开跑',

  recipeHint: '切换即替换当前生产线',
  recipeSuggestTitle: '建议配方',
  recipeSuggestHint: '按结构、近期使用与可见教训排序 · 点击才套用',
  calibrationHint: '校准依据（可见记忆，不自动改图）',

  patchTitle: '改生产线',
  patchHint: '预设或一句话改图 · 先预览再应用',

  planStripHint:
    '当前图 = 下次运行怎么干。改完可直接运行；需要复用时存为配方。',
  planStripRunHint: '点「开始运行」后按当前图直接执行（运行即确认）。',

  chatCompileTitle: '改生产线 · 整图计划预览',
  chatRecipeTitle: '配方建议',
  chatSharedPipe: '与生产线同一结果 · 需你确认后才写入 · 不会自动开跑',
  chatNoEntity:
    '当前会话未绑定品牌，无法改生产线或套用配方。请从品牌进入，或打开生产线。',
  chatOpenLine: '打开生产线',
  chatApply: '应用变更',
  chatApplyRecipe: '套用',
  chatViewLine: '在生产线查看',
  chatAsNormal: '当作普通对话发送',
  chatCompileFail: '未能生成可应用的变更。可改用生产线预设，或当作普通对话发送。',
  chatVersionConflict: '生产线已在别处更新。请打开生产线刷新后再试，或重新发送指令。',
  chatApplied: '已写入生产线。可点下方「按此图开始运行」，或打开生产线查看。',
  chatStartRun: '按此图开始运行',
  chatRunStarting: '正在启动运行…',
  chatRunStarted: '已开始运行。可在生产线查看进度。',
  chatRunFail: '未能启动运行。请打开生产线重试，或检查是否已有进行中的任务。',

  conflictRefresh: '拓扑版本冲突：请刷新页面后再试。',
} as const;
