'use client';

/**
 * Wave D: Chat-side preview for topology compile / recipe suggestions.
 * Applies only on explicit user click; deep-links to production-line Console.
 */

import Link from 'next/link';
import { buildProductionLineHref } from '@/lib/chatTopologyIntent';

export type TopologyCompilePreview = {
  summaryText: string;
  planSummary?: string;
  plannedPlatforms: string[];
  compileMatched?: string;
  compileMode?: string;
  opsCount: number;
};

export type TopologyRecipeSuggestion = {
  recipe_id: string;
  name: string;
  scope: string;
  reasons: string[];
};

export type TopologyOrchestrationCardProps = {
  kind: 'compile_nl' | 'recipe_suggest';
  status: 'loading' | 'ready' | 'applying' | 'applied' | 'error' | 'no_entity';
  entityId: string | null;
  userText: string;
  error?: string | null;
  compile?: TopologyCompilePreview | null;
  recommendations?: TopologyRecipeSuggestion[];
  onApplyCompile?: () => void;
  onApplyRecipe?: (recipeId: string) => void;
  onDismiss?: () => void;
  onSendAsNormalChat?: () => void;
};

export function TopologyOrchestrationCard({
  kind,
  status,
  entityId,
  userText,
  error,
  compile,
  recommendations,
  onApplyCompile,
  onApplyRecipe,
  onDismiss,
  onSendAsNormalChat,
}: TopologyOrchestrationCardProps) {
  const title =
    kind === 'recipe_suggest' ? '配方建议' : '生产线编排预览';
  const flowHref = entityId ? buildProductionLineHref(entityId) : '/amwaychina';
  const busy = status === 'loading' || status === 'applying';

  return (
    <div
      className="mt-2 max-w-xl rounded-lg border border-[var(--brand-border)] bg-[var(--brand-bg)]"
      data-testid="chat-topology-orchestration-card"
      data-status={status}
    >
      <div className="flex items-center justify-between gap-2 border-b border-[var(--brand-border)] px-3.5 py-2.5">
        <div>
          <p className="text-sm font-medium text-[var(--text-primary)]">{title}</p>
          <p className="mt-0.5 text-[11px] leading-4 text-[var(--text-tertiary)]">
            与生产线共用同一管道 · 不会自动套用或开跑
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
          <p className="text-xs text-[var(--text-secondary)]">正在生成预览…</p>
        ) : null}

        {status === 'no_entity' ? (
          <div className="rounded-md border border-dashed border-[var(--border-strong)] bg-[var(--bg-primary)] px-3 py-2">
            <p className="text-xs leading-5 text-[var(--text-secondary)]">
              当前会话未绑定品牌，无法改生产线或套用配方。请从品牌看板进入 Chat，或打开生产线选择品牌。
            </p>
            <Link
              href="/amwaychina"
              className="mt-2 inline-flex text-xs font-medium text-[var(--brand-primary)] hover:underline"
            >
              打开生产线
            </Link>
          </div>
        ) : null}

        {status === 'error' && error ? (
          <p className="text-xs leading-5 text-[var(--error)]">{error}</p>
        ) : null}

        {status === 'applied' ? (
          <p className="text-xs leading-5 text-[var(--brand-primary)]">
            已应用到生产线。可在 Console 刷新查看；开跑请在生产线点击运行。
          </p>
        ) : null}

        {kind === 'compile_nl' && compile && (status === 'ready' || status === 'applying') ? (
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
            <p className="mt-1 text-[10px] text-[var(--text-tertiary)]">
              ops {compile.opsCount}
              {compile.compileMode ? ` · ${compile.compileMode}` : ''}
              {compile.compileMatched ? ` · ${compile.compileMatched}` : ''}
            </p>
          </div>
        ) : null}

        {kind === 'recipe_suggest' &&
        (status === 'ready' || status === 'applying') &&
        recommendations ? (
          recommendations.length === 0 ? (
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
                    disabled={busy}
                    onClick={() => onApplyRecipe?.(item.recipe_id)}
                    className="inline-flex h-7 shrink-0 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-bg)] px-2.5 text-[11px] font-semibold text-[var(--brand-primary)] transition hover:bg-[var(--brand-primary)] hover:text-[var(--brand-contrast)] disabled:opacity-50"
                  >
                    套用
                  </button>
                </li>
              ))}
            </ul>
          )
        ) : null}

        <div className="flex flex-wrap items-center gap-2 pt-0.5">
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
              {status === 'applying' ? '应用中…' : '应用变更'}
            </button>
          ) : null}

          {entityId ? (
            <Link
              href={flowHref}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--text-secondary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)]"
            >
              在生产线查看
            </Link>
          ) : null}

          {onSendAsNormalChat && (status === 'error' || status === 'no_entity' || status === 'ready') ? (
            <button
              type="button"
              disabled={busy}
              onClick={onSendAsNormalChat}
              className="inline-flex h-8 items-center px-1 text-xs text-[var(--text-tertiary)] hover:text-[var(--text-secondary)] disabled:opacity-50"
            >
              当作普通对话发送
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
