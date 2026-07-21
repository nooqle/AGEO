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

export function AmwayFlowRecipeBar({
  entityId,
  getExpectedVersion,
  setExpectedVersion,
  onTopologyApplied,
  disabled = false,
}: {
  entityId: string;
  getExpectedVersion: () => number | null;
  setExpectedVersion: (version: number) => void;
  onTopologyApplied: (topology: AmwayFlowTopologyDoc, meta?: { recipeName?: string }) => void;
  disabled?: boolean;
}) {
  const [recipes, setRecipes] = useState<RecipeItem[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [saveName, setSaveName] = useState('');
  const [saveScope, setSaveScope] = useState<'entity' | 'organization'>('entity');

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
      // list may fail if offline; keep empty
    }
  }, [entityId]);

  useEffect(() => {
    void reload();
  }, [reload]);

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
        onTopologyApplied(resp.topology, { recipeName: resp.recipe_name });
        setNotice(`已切换配方「${resp.recipe_name}」（直接替换当前生产线）`);
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
    [busy, disabled, entityId, getExpectedVersion, onTopologyApplied, setExpectedVersion],
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
      setNotice(
        `已保存配方「${created.name}」（${created.scope === 'organization' ? '组织共享' : '本品牌'}）`,
      );
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : '保存失败');
    } finally {
      setBusy(false);
    }
  }, [busy, disabled, entityId, reload, saveName, saveScope]);

  const removeRecipe = useCallback(
    async (recipeId: string, name: string) => {
      if (busy || disabled) return;
      if (!window.confirm(`删除配方「${name}」？此操作不可撤销。`)) return;
      setBusy(true);
      setError(null);
      try {
        await api.deleteAmwayFlowRecipe(recipeId, entityId);
        setNotice(`已删除配方「${name}」`);
        await reload();
      } catch (err) {
        setError(err instanceof Error ? err.message : '删除失败');
      } finally {
        setBusy(false);
      }
    },
    [busy, disabled, entityId, reload],
  );

  return (
    <div className="mt-2 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-tertiary)]">
          <BookMarked size={13} className="text-[var(--brand-primary)]" aria-hidden />
          配方
          <span className="font-normal">
            组织共享 / 本品牌 · 切换即替换生产线 · 点运行即开跑
          </span>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {recipes.length === 0 ? (
          <span className="text-[11px] text-[var(--text-tertiary)]">暂无配方，可将当前生产线另存</span>
        ) : (
          recipes.map((recipe) => (
            <div key={recipe.id} className="inline-flex items-center gap-0.5">
              <button
                type="button"
                title={recipe.description || recipe.name}
                disabled={busy || disabled}
                onClick={() => {
                  void applyRecipe(recipe.id);
                }}
                className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 text-xs font-medium text-[var(--text-secondary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:opacity-50"
              >
                {recipe.name}
                <span className="ml-1 text-[10px] text-[var(--text-tertiary)]">
                  {recipe.scope === 'organization' ? '组织' : '品牌'}
                </span>
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
          ))
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={saveName}
          disabled={busy || disabled}
          onChange={(e) => setSaveName(e.target.value)}
          placeholder="另存当前为配方名称"
          className="h-8 min-w-[140px] flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 text-xs outline-none focus:border-[var(--brand-primary)] disabled:opacity-50"
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
          另存
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
