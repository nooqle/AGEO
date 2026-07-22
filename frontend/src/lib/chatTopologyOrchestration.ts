/**
 * Wave E4: Chat topology/recipe short-circuit loaders (pure of React).
 * Keeps ChatPanel thin; reuses Console APIs.
 */

import { api } from '@/services/api';
import { stripChatTopologyPrefix } from '@/lib/chatTopologyIntent';
import { JOURNEY } from '@/lib/amwayFlowJourneyCopy';
import {
  flowCacheKey,
  getOrLoadFlowCache,
  invalidateFlowEntityCache,
} from '@/lib/amwayFlowEntityCache';

export type ChatCompilePreview = {
  summaryText: string;
  planSummary?: string;
  plannedPlatforms: string[];
  compileMatched?: string;
  compileMode?: string;
  opsCount: number;
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
};

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
  return {
    status: 'ready',
    ops,
    expectedVersion: version,
    compile: {
      summaryText: String(resp.summary?.text || '无实质变更'),
      planSummary: resp.plan?.summary ? String(resp.plan.summary) : undefined,
      plannedPlatforms: planned,
      compileMatched: resp.compile?.matched ? String(resp.compile.matched) : undefined,
      compileMode: resp.compile?.mode ? String(resp.compile.mode) : undefined,
      opsCount: ops.length,
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
