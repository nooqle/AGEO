'use client';

/**
 * Wave D + P + Q: Chat-side full-plan preview for topology compile / recipe suggestions.
 * Applies only on explicit user click; optional start-run after apply; deep-links Console.
 */

import Link from 'next/link';
import { buildProductionLineHref } from '@/lib/chatTopologyIntent';
import { JOURNEY } from '@/lib/amwayFlowJourneyCopy';
import type { ChatCalibrationMeta, ChatPlanStep } from '@/lib/chatTopologyOrchestration';

export type TopologyCompilePreview = {
  summaryText: string;
  planSummary?: string;
  plannedPlatforms: string[];
  planSteps?: ChatPlanStep[];
  opsSummary?: string[];
  compileMatched?: string;
  compileMode?: string;
  opsCount: number;
  calibration?: ChatCalibrationMeta | null;
};

export type TopologyRecipeSuggestion = {
  recipe_id: string;
  name: string;
  scope: string;
  reasons: string[];
};

export type TopologyOrchestrationCardProps = {
  kind: 'compile_nl' | 'recipe_suggest' | 'line_guide';
  status:
    | 'loading'
    | 'ready'
    | 'applying'
    | 'applied'
    | 'run_starting'
    | 'run_started'
    | 'error'
    | 'no_entity';
  entityId: string | null;
  userText: string;
  error?: string | null;
  compile?: TopologyCompilePreview | null;
  recommendations?: TopologyRecipeSuggestion[];
  calibration?: ChatCalibrationMeta | null;
  onApplyCompile?: () => void;
  onApplyRecipe?: (recipeId: string) => void;
  onStartRun?: () => void;
  onDismiss?: () => void;
  onSendAsNormalChat?: () => void;
};

function CalibrationStrip({ meta }: { meta?: ChatCalibrationMeta | null }) {
  if (!meta) return null;
  const signals = Array.isArray(meta.signals) ? meta.signals.slice(0, 4) : [];
  const parts: string[] = [];
  if (typeof meta.events_considered === 'number' && meta.events_considered > 0) {
    parts.push(`近期变更 ${meta.events_considered}`);
  }
  if (typeof meta.lessons_considered === 'number' && meta.lessons_considered > 0) {
    parts.push(`教训 ${meta.lessons_considered}`);
  }
  if (meta.memory_injected) parts.push('已注入编译上下文');
  if (!parts.length && !signals.length) return null;
  return (
    <p className="text-[10px] leading-4 text-[var(--text-tertiary)]" data-testid="chat-calibration-hint">
      {JOURNEY.calibrationHint}
      {parts.length ? `：${parts.join(' · ')}` : ''}
      {signals.length ? ` · ${signals.join(' · ')}` : ''}
    </p>
  );
}

export function TopologyOrchestrationCard({
  kind,
  status,
  entityId,
  userText,
  error,
  compile,
  recommendations,
  calibration,
  onApplyCompile,
  onApplyRecipe,
  onStartRun,
  onDismiss,
  onSendAsNormalChat,
}: TopologyOrchestrationCardProps) {
  const title =
    kind === 'line_guide'
      ? JOURNEY.chatLineGuideTitle
      : kind === 'recipe_suggest'
        ? JOURNEY.chatRecipeTitle
        : JOURNEY.chatCompileTitle;
  const flowHref = entityId ? buildProductionLineHref(entityId) : '/amwaychina';
  const busy =
    status === 'loading' || status === 'applying' || status === 'run_starting';
  const cal = calibration || compile?.calibration || null;

  return (
    <div
      className="mt-2 max-w-xl rounded-lg border border-[var(--brand-border)] bg-[var(--brand-bg)]"
      data-testid="chat-topology-orchestration-card"
      data-status={status}
      data-kind={kind}
    >
      <div className="flex items-center justify-between gap-2 border-b border-[var(--brand-border)] px-3.5 py-2.5">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
          <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-tertiary)]">
            {kind === 'line_guide' ? JOURNEY.chatRoleHint : JOURNEY.chatSharedPipe}
          </p>
        </div>
        {onDismiss ? (
          <button
            type="button"
            onClick={onDismiss}
            className="text-[11px] text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]"
          >
            关闭
          </button>
        ) : null}
      </div>

      <div className="space-y-2.5 px-3.5 py-3">
        <p className="text-[11px] text-[var(--text-tertiary)]">
          指令：<span className="text-[var(--text-secondary)]">{userText}</span>
        </p>

        {status === 'loading' ? (
          <p className="text-xs text-[var(--text-secondary)]">正在生成整图计划预览…</p>
        ) : null}

        {kind === 'line_guide' && status === 'ready' ? (
          <div
            className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2"
            data-testid="chat-line-guide"
          >
            <p className="text-xs leading-5 text-[var(--text-secondary)]">
              {JOURNEY.chatLineGuideBody}
            </p>
          </div>
        ) : null}

        {status === 'no_entity' ? (
          <div className="rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--bg-primary)] px-3 py-2">
            <p className="text-xs leading-5 text-[var(--text-secondary)]">
              {JOURNEY.chatNoEntity}
            </p>
            <Link
              href="/amwaychina"
              className="mt-2 inline-flex text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              {JOURNEY.chatOpenLine}
            </Link>
          </div>
        ) : null}

        {status === 'error' && error ? (
          <p className="text-xs leading-5 text-[var(--error)]">{error}</p>
        ) : null}

        {status === 'applied' || status === 'run_starting' || status === 'run_started' ? (
          <p className="text-xs leading-5 text-[var(--brand-primary)]">
            {status === 'run_started'
              ? JOURNEY.chatRunStarted
              : status === 'run_starting'
                ? JOURNEY.chatRunStarting
                : JOURNEY.chatApplied}
          </p>
        ) : null}

        {kind === 'compile_nl' &&
        compile &&
        (status === 'ready' || status === 'applying') ? (
          <div className="rounded-md border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 py-2">
            <p className="text-xs font-medium text-[var(--text-primary)]">
              {compile.summaryText || '无实质变更'}
            </p>
            {compile.planSummary ? (
              <p className="mt-1 text-[11px] leading-4 text-[var(--text-secondary)]">
                {compile.planSummary}
              </p>
            ) : null}
            {compile.plannedPlatforms.length ? (
              <p className="mt-1 text-[11px] text-[var(--text-tertiary)]">
                计划平台：{compile.plannedPlatforms.join(' · ')}
              </p>
            ) : null}
            {compile.planSteps && compile.planSteps.length > 0 ? (
              <ul className="mt-1.5 space-y-0.5" data-testid="chat-plan-steps">
                {compile.planSteps.map((step, idx) => (
                  <li
                    key={`${step.node_id || step.label || idx}`}
                    className="text-[10px] leading-4 text-[var(--text-tertiary)]"
                  >
                    · {step.label || step.node_id || `步骤 ${idx + 1}`}
                    {step.status ? `（${step.status}）` : ''}
                  </li>
                ))}
              </ul>
            ) : null}
            {compile.opsSummary && compile.opsSummary.length > 0 ? (
              <p className="mt-1 text-[10px] text-[var(--text-tertiary)]">
                变更：{compile.opsSummary.join(' · ')}
              </p>
            ) : null}
            <p className="mt-1 text-[10px] text-[var(--text-tertiary)]">
              ops {compile.opsCount}
              {compile.compileMode ? ` · ${compile.compileMode}` : ''}
              {compile.compileMatched ? ` · ${compile.compileMatched}` : ''}
            </p>
            <CalibrationStrip meta={cal} />
          </div>
        ) : null}

        {kind === 'recipe_suggest' &&
        (status === 'ready' || status === 'applying') &&
        recommendations ? (
          <>
            <CalibrationStrip meta={cal} />
            {recommendations.length === 0 ? (
              <p className="text-xs text-[var(--text-secondary)]">
                暂无推荐配方。可先在生产线另存配方。
              </p>
            ) : (
              <ul className="space-y-2">
                {recommendations.map((item) => (
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
                        {(item.reasons.length ? item.reasons : ['可见配方池候选']).map(
                          (reason) => (
                            <li
                              key={`${item.recipe_id}-${reason}`}
                              className="text-[10px] leading-4 text-[var(--text-tertiary)]"
                            >
                              · {reason}
                            </li>
                          ),
                        )}
                      </ul>
                    </div>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => onApplyRecipe?.(item.recipe_id)}
                      className="inline-flex h-7 shrink-0 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-bg)] px-2.5 text-[11px] font-semibold text-[var(--brand-primary)] transition hover:bg-[var(--brand-primary)] hover:text-[var(--brand-contrast)] disabled:opacity-50"
                    >
                      {JOURNEY.chatApplyRecipe}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </>
        ) : null}

        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          {kind === 'line_guide' && status === 'ready' ? (
            <Link
              href={flowHref}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3 text-xs font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)]"
            >
              {JOURNEY.chatLineGuideCta}
            </Link>
          ) : null}

          {kind === 'compile_nl' &&
          (status === 'ready' || status === 'applying') &&
          compile &&
          compile.opsCount > 0 ? (
            <button
              type="button"
              disabled={busy}
              onClick={onApplyCompile}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3 text-xs font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
            >
              {status === 'applying' ? '应用中…' : JOURNEY.chatApply}
            </button>
          ) : null}

          {(status === 'applied' || status === 'run_starting') && onStartRun ? (
            <button
              type="button"
              disabled={busy}
              onClick={onStartRun}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3 text-xs font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
              data-testid="chat-start-flow-run"
            >
              {status === 'run_starting' ? JOURNEY.chatRunStarting : JOURNEY.chatStartRun}
            </button>
          ) : null}

          {entityId ? (
            <Link
              href={flowHref}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--text-secondary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
            >
              {JOURNEY.chatViewLine}
            </Link>
          ) : null}

          {onSendAsNormalChat &&
          (status === 'error' || status === 'no_entity' || status === 'ready') ? (
            <button
              type="button"
              disabled={busy}
              onClick={onSendAsNormalChat}
              className="inline-flex h-8 items-center px-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] disabled:opacity-50"
            >
              {JOURNEY.chatAsNormal}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
