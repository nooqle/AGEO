/**
 * Wave E4 + P + Q: Chat topology/recipe short-circuit loaders (pure of React).
 * Keeps ChatPanel thin; reuses Console APIs.
 */

import { api } from '@/services/api';
import { defaultPlatformFetchMethods } from '@/lib/platformFetchMethods';
import { stripChatTopologyPrefix } from '@/lib/chatTopologyIntent';
import { JOURNEY } from '@/lib/amwayFlowJourneyCopy';
import {
  flowCacheKey,
  getOrLoadFlowCache,
  invalidateFlowEntityCache,
} from '@/lib/amwayFlowEntityCache';

export type ChatCalibrationMeta = {
  events_considered?: number;
  lessons_considered?: number;
  signals?: string[];
  memory_injected?: boolean;
  auto_applied?: boolean;
};

export type ChatPlanStep = {
  node_id?: string;
  label?: string;
  status?: string;
};

export type ChatCompilePreview = {
  summaryText: string;
  planSummary?: string;
  plannedPlatforms: string[];
  planSteps: ChatPlanStep[];
  opsSummary: string[];
  compileMatched?: string;
  compileMode?: string;
  opsCount: number;
  calibration?: ChatCalibrationMeta | null;
};

export type ChatRecipeSuggestion = {
  recipe_id: string;
  name: string;
  scope: string;
  reasons: string[];
};

export type ChatCompileReady = {
  status: 'ready';
  ops: Array<Record<string, unknown>>;
  expectedVersion: number | null;
  compile: ChatCompilePreview;
};

export type ChatCompileError = {
  status: 'error';
  error: string;
  expectedVersion?: number | null;
};

export type ChatRecipeReady = {
  status: 'ready';
  recommendations: ChatRecipeSuggestion[];
  calibration?: ChatCalibrationMeta | null;
};

function opsSummaryLines(ops: Array<Record<string, unknown>>): string[] {
  const counts = new Map<string, number>();
  for (const op of ops) {
    const name = String(op?.op || 'op');
    counts.set(name, (counts.get(name) || 0) + 1);
  }
  return Array.from(counts.entries())
    .slice(0, 6)
    .map(([name, n]) => (n > 1 ? `${name}×${n}` : name));
}

function planStepsFromPlan(plan: Record<string, unknown> | null | undefined): ChatPlanStep[] {
  if (!plan || !Array.isArray(plan.steps)) return [];
  return plan.steps
    .filter((s): s is Record<string, unknown> => Boolean(s) && typeof s === 'object')
    .slice(0, 8)
    .map((s) => ({
      node_id: s.node_id != null ? String(s.node_id) : s.id != null ? String(s.id) : undefined,
      label: s.label != null ? String(s.label) : undefined,
      status: s.status != null ? String(s.status) : undefined,
    }));
}

export async function loadChatCompilePreview(
  entityId: string,
  userText: string,
): Promise<ChatCompileReady | ChatCompileError> {
  const topo = await getOrLoadFlowCache(
    flowCacheKey([entityId, 'topology']),
    () => api.getAmwayFlowTopology(entityId),
    8_000,
  );
  const expectedVersion = typeof topo.version === 'number' ? topo.version : null;
  const compileText = stripChatTopologyPrefix(userText) || userText;
  // compile is not cached (depends on text + live graph)
  const resp = await api.compileAmwayFlowTopologyNl(entityId, {
    text: compileText,
    expected_version: expectedVersion,
    allow_llm: true,
  });
  const ops = Array.isArray(resp.ops) ? resp.ops : [];
  const version =
    typeof resp.base?.version === 'number' ? resp.base.version : expectedVersion;
  if (!ops.length) {
    return {
      status: 'error',
      error: JOURNEY.chatCompileFail,
      expectedVersion: version,
    };
  }
  const planned = Array.isArray(resp.plan?.planned_platforms)
    ? resp.plan!.planned_platforms!.map(String)
    : [];
  const planObj = (resp.plan || {}) as Record<string, unknown>;
  return {
    status: 'ready',
    ops,
    expectedVersion: version,
    compile: {
      summaryText: String(resp.summary?.text || '无实质变更'),
      planSummary: resp.plan?.summary ? String(resp.plan.summary) : undefined,
      plannedPlatforms: planned,
      planSteps: planStepsFromPlan(planObj),
      opsSummary: opsSummaryLines(ops),
      compileMatched: resp.compile?.matched ? String(resp.compile.matched) : undefined,
      compileMode: resp.compile?.mode ? String(resp.compile.mode) : undefined,
      opsCount: ops.length,
      calibration: resp.compile?.calibration || null,
    },
  };
}

export async function loadChatRecipeSuggestions(
  entityId: string,
  userText: string,
): Promise<ChatRecipeReady> {
  const resp = await getOrLoadFlowCache(
    flowCacheKey([entityId, 'recommend', userText.trim().slice(0, 80)]),
    () =>
      api.recommendAmwayFlowRecipes(entityId, {
        intent: userText,
        limit: 3,
      }),
    10_000,
  );
  return {
    status: 'ready',
    recommendations: (resp.recommendations || []).map((item) => ({
      recipe_id: item.recipe_id,
      name: item.name,
      scope: item.scope,
      reasons: Array.isArray(item.reasons) ? item.reasons.map(String).filter(Boolean) : [],
    })),
    calibration: resp.calibration || null,
  };
}

export async function applyChatCompilePatch(
  entityId: string,
  ops: Array<Record<string, unknown>>,
  expectedVersion: number | null,
): Promise<void> {
  let expected = expectedVersion;
  if (expected == null) {
    const topo = await api.getAmwayFlowTopology(entityId);
    expected = typeof topo.version === 'number' ? topo.version : null;
  }
  if (expected == null) {
    throw new Error('无法读取拓扑版本，请打开生产线后重试。');
  }
  await api.applyAmwayFlowTopologyPatch(entityId, {
    ops,
    expected_version: expected,
  });
  invalidateFlowEntityCache(entityId);
}

export async function applyChatRecipe(
  entityId: string,
  recipeId: string,
): Promise<{ recipe_name: string }> {
  const topo = await api.getAmwayFlowTopology(entityId);
  const expected = typeof topo.version === 'number' ? topo.version : null;
  const resp = await api.applyAmwayFlowRecipe(entityId, recipeId, expected);
  invalidateFlowEntityCache(entityId);
  return { recipe_name: resp.recipe_name };
}

/** Wave Q: explicit user click → same association run as Console (no auto). */
export async function startChatFlowRun(entityId: string): Promise<{ run_id: string }> {
  const platforms = (() => {
    try {
      // Keep import-free soft read of local platform gates (topology authority on Console)
      const raw = window.localStorage.getItem(`amway-flow-platforms:${entityId}`);
      if (!raw) return undefined;
      const parsed = JSON.parse(raw) as string[];
      return Array.isArray(parsed) ? parsed.map(String) : undefined;
    } catch {
      return undefined;
    }
  })();

  if (platforms?.length === 0) throw new Error('请先在生产线启用至少一个采集平台。');
  let recipeScope: Record<string, string> = {};
  try {
    const raw = sessionStorage.getItem(`amway-flow-active-recipe:${entityId}`);
    if (raw) {
      const parsed = JSON.parse(raw) as { id?: string; name?: string; dirty?: boolean };
      if (parsed?.id && parsed?.name && !parsed.dirty) {
        recipeScope = {
          recipe_id: String(parsed.id),
          recipe_name: String(parsed.name),
        };
      }
    }
  } catch {
    recipeScope = {};
  }

  const run = await api.createBrandIntelligenceRun(entityId, {
    run_goal: '生成安利品牌联想圈层报告',
    analysis_mode: 'brand_association_circle',
    origin_surface: 'chat_topology_endgame',
    origin_event_id: `chat-flow-run:${entityId}:${Date.now()}`,
    auto_dispatch: true,
    input_scope: {
      dashboard_variant: 'amway_association_circle',
      analysis_mode: 'brand_association_circle',
      report_kind: 'brand_association_circle',
      platforms,
      platform_fetch_methods: defaultPlatformFetchMethods(),
      enabled_surfaces: ['amwaychina_console', 'chat', 'canvas', 'brand_world'],
      ...recipeScope,
    },
  });
  return { run_id: String(run.id) };
}
