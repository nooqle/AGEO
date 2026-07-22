'use client';

/**
 * Wave A: single orchestration surface — recipes (primary) + compile/presets (secondary).
 * Keeps AmwayFlowCanvas free of dual stacked tool chrome.
 */

import type { AmwayFlowTopologyDoc } from '@/services/api';
import { AmwayFlowRecipeBar } from '@/components/dashboard/AmwayFlowRecipeBar';
import { AmwayFlowTopologyPatchBar } from '@/components/dashboard/AmwayFlowTopologyPatchBar';

export function AmwayFlowOrchestrationPanel({
  entityId,
  getExpectedVersion,
  setExpectedVersion,
  onTopologyApplied,
  disabled = false,
  isAwaitingPlanConfirm = false,
  onRefreshFlowPlan,
  suggestSaveAfterRun = false,
}: {
  entityId: string;
  getExpectedVersion: () => number | null;
  setExpectedVersion: (version: number) => void;
  onTopologyApplied: (topology: AmwayFlowTopologyDoc, meta?: { recipeName?: string }) => void;
  disabled?: boolean;
  isAwaitingPlanConfirm?: boolean;
  onRefreshFlowPlan?: () => void | Promise<void>;
  /** When true, recipe section surfaces post-run "save as recipe" prompt */
  suggestSaveAfterRun?: boolean;
}) {
  return (
    <section className="mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-primary)] shadow-sm">
      <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-[var(--border-subtle)] px-3.5 py-2.5">
        <div>
          <h2 className="text-sm font-semibold text-[var(--text-primary)]">编排</h2>
          <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-tertiary)]">
            配方记住怎么干 · 预设/自然语言改当前生产线 · 点运行即开跑
          </p>
        </div>
      </header>

      <div className="px-3.5 py-3">
        <AmwayFlowRecipeBar
          embedded
          entityId={entityId}
          getExpectedVersion={getExpectedVersion}
          setExpectedVersion={setExpectedVersion}
          onTopologyApplied={onTopologyApplied}
          disabled={disabled}
          suggestSaveAfterRun={suggestSaveAfterRun}
        />
      </div>

      <div className="border-t border-[var(--border-subtle)] px-3.5 py-3">
        <AmwayFlowTopologyPatchBar
          embedded
          entityId={entityId}
          getExpectedVersion={getExpectedVersion}
          setExpectedVersion={setExpectedVersion}
          onTopologyApplied={onTopologyApplied}
          disabled={disabled}
          isAwaitingPlanConfirm={isAwaitingPlanConfirm}
          onRefreshFlowPlan={onRefreshFlowPlan}
        />
      </div>
    </section>
  );
}
