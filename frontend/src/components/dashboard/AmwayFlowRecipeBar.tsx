'use client';

/**
 * Production-line recipes: org-wide + brand-scoped presets.
 * Apply = direct topology replace (no confirm dialog).
 */

import { useCallback, useEffect, useState } from 'react';
import { BookMarked, Trash2 } from 'lucide-react';
import { api, type AmwayFlowTopologyDoc } from '@/services/api';

type RecipeItem = {
  id: string;
  name: string;
  scope: string;
  entity_id: string | null;
  description?: string | null;
};

type RecipeSuggestion = {
  recipe_id: string;
  name: string;
  scope: string;
  reasons: string[];
  score: number;
};

export function AmwayFlowRecipeBar({
  entityId,
  getExpectedVersion,
  setExpectedVersion,
  onTopologyApplied,
  onRecipeSaved,
  disabled = false,
  embedded = false,
  suggestSaveAfterRun = false,
  activeRecipeName = null,
  activeRecipeDirty = false,
  activeRecipeId = null,
  onActiveRecipeCleared,
}: {
  entityId: string;
  getExpectedVersion: () => number | null;
  setExpectedVersion: (version: number) => void;
  onTopologyApplied: (
    topology: AmwayFlowTopologyDoc,
    meta?: { recipeName?: string; recipeId?: string },
  ) => void;
  onRecipeSaved?: (name: string, id?: string) => void;
  disabled?: boolean;
  embedded?: boolean;
  suggestSaveAfterRun?: boolean;
  activeRecipeName?: string | null;
  activeRecipeDirty?: boolean;
  activeRecipeId?: string | null;
  onActiveRecipeCleared?: () => void;
}) {
  const [recipes, setRecipes] = useState<RecipeItem[]>([]);
  const [suggestions, setSuggestions] = useState<RecipeSuggestion[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saveName, setSaveName] = useState('');
  const [saveScope, setSaveScope] = useState<'entity' | 'organization'>('entity');
  const [loaded, setLoaded] = useState(false);

  const reloadSuggestions = useCallback(async () => {
    try {
      const resp = await api.recommendAmwayFlowRecipes(entityId, {
        activeRecipeId: activeRecipeDirty ? null : activeRecipeId,
        limit: 3,
      });
      setSuggestions(
        (resp.recommendations || []).map((item) => ({
          recipe_id: item.recipe_id,
          name: item.name,
          scope: item.scope,
          reasons: Array.isArray(item.reasons) ? item.reasons.filter(Boolean) : [],
          score: item.score,
        })),
      );
    } catch {
      setSuggestions([]);
    }
  }, [activeRecipeDirty, activeRecipeId, entityId]);

  const reload = useCallback(async () => {
    try {
      const resp = await api.listAmwayFlowRecipes(entityId);
      setRecipes(
        (resp.recipes || []).map((r) => ({
          id: r.id,
          name: r.name,
          scope: r.scope,
          entity_id: r.entity_id,
          description: r.description,
        })),
      );
    } catch {
      // keep empty
    } finally {
      setLoaded(true);
    }
    await reloadSuggestions();
  }, [entityId, reloadSuggestions]);

  useEffect(() => {
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!suggestSaveAfterRun) return;
    setSaveName((current) => {
      if (current.trim()) return current;
      const stamp = new Date().toLocaleDateString('zh-CN', {
        month: 'numeric',
        day: 'numeric',
      });
      return `运行成功 ${stamp}`;
    });
  }, [suggestSaveAfterRun]);

  const applyRecipe = useCallback(
    async (recipeId: string) => {
      if (busy || disabled) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const resp = await api.applyAmwayFlowRecipe(
          entityId,
          recipeId,
          getExpectedVersion(),
        );
        if (typeof resp.version === 'number') setExpectedVersion(resp.version);
        onTopologyApplied(resp.topology, {
          recipeName: resp.recipe_name,
          recipeId: resp.recipe_id,
        });
        setNotice(`已切换配方「${resp.recipe_name}」（直接替换当前生产线）`);
        await reloadSuggestions();
      } catch (err) {
        const message = err instanceof Error ? err.message : '套用配方失败';
        setError(
          message.includes('版本冲突')
            ? '拓扑版本冲突：请刷新页面后再切换配方。'
            : message,
        );
      } finally {
        setBusy(false);
      }
    },
    [
      busy,
      disabled,
      entityId,
      getExpectedVersion,
      onTopologyApplied,
      reloadSuggestions,
      setExpectedVersion,
    ],
  );

  const saveCurrent = useCallback(async () => {
    if (busy || disabled) return;
    const name = saveName.trim();
    if (!name) {
      setError('请填写配方名称');
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await api.createAmwayFlowRecipe({
        name,
        scope: saveScope,
        entity_id: entityId,
        from_current: true,
      });
      setSaveName('');
      onRecipeSaved?.(created.name, created.id);
      setNotice(
        `已保存配方「${created.name}」（${created.scope === 'organization' ? '组织共享' : '本品牌'}）`,
      );
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }, [busy, disabled, entityId, onRecipeSaved, reload, saveName, saveScope]);

  const overwriteRecipe = useCallback(
    async (recipeId: string, name: string) => {
      if (busy || disabled) return;
      if (!window.confirm(`用当前生产线覆盖配方「${name}」？`)) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const updated = await api.updateAmwayFlowRecipe(recipeId, entityId, {
          from_current: true,
        });
        onRecipeSaved?.(updated.name, updated.id);
        setNotice(`已用当前生产线覆盖配方「${updated.name}」`);
        await reload();
      } catch (err) {
        setError(err instanceof Error ? err.message : '覆盖失败');
      } finally {
        setBusy(false);
      }
    },
    [busy, disabled, entityId, onRecipeSaved, reload],
  );

  const removeRecipe = useCallback(
    async (recipeId: string, name: string) => {
      if (busy || disabled) return;
      if (!window.confirm(`删除配方「${name}」？此操作不可撤销。`)) return;
      setBusy(true);
      setError(null);
      try {
        await api.deleteAmwayFlowRecipe(recipeId, entityId);
        if (activeRecipeName === name) onActiveRecipeCleared?.();
        setNotice(`已删除配方「${name}」`);
        await reload();
      } catch (err) {
        setError(err instanceof Error ? err.message : '删除失败');
      } finally {
        setBusy(false);
      }
    },
    [activeRecipeName, busy, disabled, entityId, onActiveRecipeCleared, reload],
  );

  const shellClass = embedded
    ? ''
    : 'mt-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5';

  const badgeLabel = activeRecipeName
    ? activeRecipeDirty
      ? `基于：${activeRecipeName} · 已修改`
      : `当前：${activeRecipeName}`
    : null;

  return (
    <div className={shellClass}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5 text-xs font-medium text-[var(--text-primary)]">
          <BookMarked size={13} className="text-[var(--brand-primary)]" aria-hidden />
          配方
          <span className="font-normal text-[var(--text-tertiary)]">
            组织 / 本品牌 · 切换即替换
          </span>
          {badgeLabel ? (
            <span
              className={`rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                activeRecipeDirty
                  ? 'border-[var(--border-strong)] bg-[var(--bg-secondary)] text-[var(--text-secondary)]'
                  : 'border-[var(--brand-primary)]/30 bg-[var(--brand-bg)] text-[var(--brand-primary)]'
              }`}
            >
              {badgeLabel}
            </span>
          ) : null}
        </div>
      </div>

      {suggestSaveAfterRun ? (
        <div className="mt-2 rounded-lg border border-[var(--brand-primary)]/30 bg-[var(--brand-bg)] px-3 py-2">
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            最近有已完成的运行。可将当前生产线存为配方，供组织或本品牌下次一键套用。
          </p>
        </div>
      ) : null}

      {loaded && suggestions.length > 0 ? (
        <div
          className="mt-2 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
          data-testid="amway-recipe-suggestions"
        >
          <p className="text-[11px] font-medium text-[var(--text-secondary)]">建议配方</p>
          <p className="mt-0.5 text-[10px] leading-4 text-[var(--text-tertiary)]">
            按结构相近、近期套用与品牌范围排序 · 不会自动套用
          </p>
          <ul className="mt-2 space-y-2">
            {suggestions.map((item) => (
              <li
                key={item.recipe_id}
                className="flex flex-wrap items-start justify-between gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 py-2"
              >
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-xs font-medium text-[var(--text-primary)]">
                      {item.name}
                    </span>
                    <span className="text-[10px] text-[var(--text-tertiary)]">
                      {item.scope === 'organization' ? '组织' : '品牌'}
                    </span>
                  </div>
                  <ul className="mt-1 space-y-0.5">
                    {(item.reasons.length ? item.reasons : ['可见配方池候选']).map((reason) => (
                      <li
                        key={`${item.recipe_id}-${reason}`}
                        className="text-[10px] leading-4 text-[var(--text-tertiary)]"
                      >
                        · {reason}
                      </li>
                    ))}
                  </ul>
                </div>
                <button
                  type="button"
                  disabled={busy || disabled}
                  onClick={() => {
                    void applyRecipe(item.recipe_id);
                  }}
                  className="inline-flex h-7 shrink-0 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-bg)] px-2.5 text-[11px] font-semibold text-[var(--brand-primary)] transition hover:bg-[var(--brand-primary)] hover:text-[var(--brand-contrast)] disabled:opacity-50"
                >
                  套用
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {loaded && recipes.length === 0 ? (
        <div className="mt-2 rounded-lg border border-dashed border-[var(--border-strong)] bg-[var(--bg-secondary)] px-3 py-3">
          <p className="text-sm font-medium text-[var(--text-primary)]">还没有配方</p>
          <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
            配方是可命名的生产线干法（像组织/项目级 skill）。先调好画布，再存一条，同事与下次可一键切换。
          </p>
          <p className="mt-2 text-[11px] text-[var(--text-tertiary)]">
            在下方填写名称后点「存为配方」即可。
          </p>
        </div>
      ) : (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {recipes.map((recipe) => (
            <div key={recipe.id} className="inline-flex items-center gap-0.5">
              <button
                type="button"
                title={recipe.description || recipe.name}
                disabled={busy || disabled}
                onClick={() => {
                  void applyRecipe(recipe.id);
                }}
                className={`inline-flex h-8 items-center rounded-lg border px-2.5 text-xs font-medium transition disabled:opacity-50 ${
                  activeRecipeName === recipe.name && !activeRecipeDirty
                    ? 'border-[var(--brand-primary)] bg-[var(--brand-bg)] text-[var(--brand-primary)]'
                    : 'border-[var(--border-subtle)] bg-[var(--bg-secondary)] text-[var(--text-secondary)] hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]'
                }`}
              >
                {recipe.name}
                <span className="ml-1 text-[10px] opacity-70">
                  {recipe.scope === 'organization' ? '组织' : '品牌'}
                </span>
              </button>
              <button
                type="button"
                title="用当前生产线覆盖此配方"
                disabled={busy || disabled}
                onClick={() => {
                  void overwriteRecipe(recipe.id, recipe.name);
                }}
                className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] px-2 text-[10px] font-medium text-[var(--text-tertiary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:opacity-50"
              >
                覆盖
              </button>
              <button
                type="button"
                aria-label={`删除配方 ${recipe.name}`}
                disabled={busy || disabled}
                onClick={() => {
                  void removeRecipe(recipe.id, recipe.name);
                }}
                className="inline-flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--border-subtle)] text-[var(--text-tertiary)] transition hover:border-[var(--error)] hover:text-[var(--error)] disabled:opacity-50"
              >
                <Trash2 size={12} aria-hidden />
              </button>
            </div>
          ))}
        </div>
      )}

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={saveName}
          disabled={busy || disabled}
          onChange={(e) => setSaveName(e.target.value)}
          placeholder="配方名称，例如：日常三平台监测"
          className="h-8 min-w-[160px] flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 text-xs outline-none focus:border-[var(--brand-primary)] disabled:opacity-50"
        />
        <select
          value={saveScope}
          disabled={busy || disabled}
          onChange={(e) => setSaveScope(e.target.value as 'entity' | 'organization')}
          className="h-8 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2 text-xs text-[var(--text-secondary)] disabled:opacity-50"
        >
          <option value="entity">本品牌</option>
          <option value="organization">组织共享</option>
        </select>
        <button
          type="button"
          disabled={busy || disabled}
          onClick={() => {
            void saveCurrent();
          }}
          className="inline-flex h-8 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3 text-xs font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
        >
          {recipes.length === 0 || suggestSaveAfterRun ? '存为配方' : '另存'}
        </button>
      </div>

      {notice ? (
        <p className="mt-2 text-xs leading-5 text-[var(--brand-primary)]">{notice}</p>
      ) : null}
      {error ? (
        <p className="mt-2 text-xs leading-5 text-[var(--error)]">{error}</p>
      ) : null}
    </div>
  );
}
