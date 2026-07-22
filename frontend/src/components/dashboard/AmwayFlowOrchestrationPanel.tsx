'use client';

/**
 * Wave A: single orchestration surface — recipes (primary) + compile/presets (secondary).
 * Keeps AmwayFlowCanvas free of dual stacked tool chrome.
 */

import { useCallback, useEffect, useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { api, type AmwayFlowTopologyDoc } from '@/services/api';
import {
  readActiveRecipeSession,
  writeActiveRecipeSession,
} from '@/lib/amwayFlowActiveRecipe';
import { AmwayFlowRecipeBar } from '@/components/dashboard/AmwayFlowRecipeBar';
import { AmwayFlowTopologyPatchBar } from '@/components/dashboard/AmwayFlowTopologyPatchBar';
import { JOURNEY } from '@/lib/amwayFlowJourneyCopy';
import {
  flowCacheKey,
  getOrLoadFlowCache,
  invalidateFlowEntityCache,
} from '@/lib/amwayFlowEntityCache';

export function AmwayFlowOrchestrationPanel({
  entityId,
  getExpectedVersion,
  setExpectedVersion,
  onTopologyApplied,
  disabled = false,
  isAwaitingPlanConfirm = false,
  onRefreshFlowPlan,
  /** Live in-flight run from active-run API (excludes completed). */
  activeRunCompleted = false,
}: {
  entityId: string;
  getExpectedVersion: () => number | null;
  setExpectedVersion: (version: number) => void;
  onTopologyApplied: (topology: AmwayFlowTopologyDoc, meta?: { recipeName?: string }) => void;
  disabled?: boolean;
  isAwaitingPlanConfirm?: boolean;
  onRefreshFlowPlan?: () => void | Promise<void>;
  activeRunCompleted?: boolean;
}) {
  const session = readActiveRecipeSession(entityId);
  const [activeRecipeId, setActiveRecipeId] = useState<string | null>(session?.id || null);
  const [activeRecipeName, setActiveRecipeName] = useState<string | null>(session?.name || null);
  const [activeRecipeDirty, setActiveRecipeDirty] = useState(Boolean(session?.dirty));
  const [latestCompleted, setLatestCompleted] = useState(false);
  const [eventsOpen, setEventsOpen] = useState(false);
  const [events, setEvents] = useState<
    Array<{ id: string; summary: string; created_at?: string | null; event_type: string }>
  >([]);

  const persistRecipeSession = useCallback(
    (next: { id: string; name: string; dirty: boolean } | null) => {
      writeActiveRecipeSession(entityId, next);
      if (!next) {
        setActiveRecipeId(null);
        setActiveRecipeName(null);
        setActiveRecipeDirty(false);
        return;
      }
      setActiveRecipeId(next.id);
      setActiveRecipeName(next.name);
      setActiveRecipeDirty(next.dirty);
    },
    [entityId],
  );

  const reloadEvents = useCallback(async () => {
    try {
      const resp = await getOrLoadFlowCache(
        flowCacheKey([entityId, 'events', 15]),
        () => api.listAmwayOrchestrationEvents(entityId, 15),
        8_000,
      );
      setEvents(resp.events || []);
    } catch {
      setEvents([]);
    }
  }, [entityId]);

  // F7: active-run API drops completed; load latest completed explicitly
  useEffect(() => {
    let cancelled = false;
    void api
      .getLatestBrandIntelligenceRun(entityId, 'completed')
      .then((run) => {
        if (cancelled) return;
        setLatestCompleted(Boolean(run) && String(run?.status || '').toLowerCase() === 'completed');
      })
      .catch(() => {
        if (!cancelled) setLatestCompleted(false);
      });
    return () => {
      cancelled = true;
    };
  }, [entityId, activeRunCompleted]);

  useEffect(() => {
    void reloadEvents();
  }, [reloadEvents]);

  const suggestSaveAfterRun = activeRunCompleted || latestCompleted;

  const handleRecipeApplied = useCallback(
    (topology: AmwayFlowTopologyDoc, meta?: { recipeName?: string; recipeId?: string }) => {
      const name = meta?.recipeName || null;
      const id = meta?.recipeId || null;
      if (id && name) persistRecipeSession({ id, name, dirty: false });
      else persistRecipeSession(null);
      invalidateFlowEntityCache(entityId);
      onTopologyApplied(topology, meta);
      void reloadEvents();
    },
    [entityId, onTopologyApplied, persistRecipeSession, reloadEvents],
  );

  const handlePatchApplied = useCallback(
    (topology: AmwayFlowTopologyDoc) => {
      if (activeRecipeId && activeRecipeName) {
        persistRecipeSession({ id: activeRecipeId, name: activeRecipeName, dirty: true });
      }
      invalidateFlowEntityCache(entityId);
      onTopologyApplied(topology);
      void reloadEvents();
    },
    [activeRecipeId, activeRecipeName, entityId, onTopologyApplied, persistRecipeSession, reloadEvents],
  );

  const handleRecipeSaved = useCallback(
    (name: string, id?: string) => {
      if (id) persistRecipeSession({ id, name, dirty: false });
      else if (activeRecipeId) persistRecipeSession({ id: activeRecipeId, name, dirty: false });
      else setActiveRecipeName(name);
      invalidateFlowEntityCache(entityId);
      void reloadEvents();
    },
    [activeRecipeId, entityId, persistRecipeSession, reloadEvents],
  );

  return (
    <section className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-sm">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-subtle)] px-3.5 py-2.5">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">{JOURNEY.orchTitle}</h2>
          <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {JOURNEY.orchSubtitle}
          </p>
          <p className="mt-1 text-[10px] leading-4 text-[var(--text-tertiary)]">
            {JOURNEY.stepsOneLiner}
          </p>
        </div>
      </header>

      <div className="px-3.5 py-3">
        <AmwayFlowRecipeBar
          embedded
          entityId={entityId}
          getExpectedVersion={getExpectedVersion}
          setExpectedVersion={setExpectedVersion}
          onTopologyApplied={(topology, meta) => {
            handleRecipeApplied(topology, {
              recipeName: meta?.recipeName,
              recipeId: meta?.recipeId,
            });
          }}
          onRecipeSaved={handleRecipeSaved}
          disabled={disabled}
          suggestSaveAfterRun={suggestSaveAfterRun}
          activeRecipeName={activeRecipeName}
          activeRecipeDirty={activeRecipeDirty}
          activeRecipeId={activeRecipeId}
          onActiveRecipeCleared={() => persistRecipeSession(null)}
        />
      </div>

      <div className="border-t border-[var(--border-subtle)] px-3.5 py-3">
        <AmwayFlowTopologyPatchBar
          embedded
          entityId={entityId}
          getExpectedVersion={getExpectedVersion}
          setExpectedVersion={setExpectedVersion}
          onTopologyApplied={handlePatchApplied}
          disabled={disabled}
          isAwaitingPlanConfirm={isAwaitingPlanConfirm}
          onRefreshFlowPlan={onRefreshFlowPlan}
        />
      </div>

      <div className="border-t border-[var(--border-subtle)] px-3.5 py-2.5">
        <button
          type="button"
          onClick={() => {
            setEventsOpen((open) => !open);
            if (!eventsOpen) void reloadEvents();
          }}
          className="inline-flex items-center gap-1 text-xs font-medium text-[var(--text-secondary)] hover:text-[var(--brand-primary)]"
        >
          {eventsOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
          {JOURNEY.recentChanges}
          {events.length ? (
            <span className="text-[10px] text-[var(--text-tertiary)]">({events.length})</span>
          ) : null}
        </button>
        {eventsOpen ? (
          <ul className="mt-2 max-h-40 space-y-1.5 overflow-y-auto">
            {events.length === 0 ? (
              <li className="text-[11px] text-[var(--text-tertiary)]">暂无变更记录</li>
            ) : (
              events.map((ev) => (
                <li
                  key={ev.id}
                  className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-2.5 py-1.5 text-[11px] leading-4 text-[var(--text-secondary)]"
                >
                  <span className="text-[var(--text-primary)]">{ev.summary}</span>
                  {ev.created_at ? (
                    <span className="mt-0.5 block text-[10px] text-[var(--text-tertiary)]">
                      {new Date(ev.created_at).toLocaleString('zh-CN')}
                    </span>
                  ) : null}
                </li>
              ))
            )}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
