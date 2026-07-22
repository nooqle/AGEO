'use client';

/**
 * 3c-B/C1: topology patch presets + NL compile strip.
 * Extracted from AmwayFlowCanvas to keep the canvas shell smaller.
 */

import { useCallback, useState } from 'react';
import { api } from '@/services/api';
import {
  TOPOLOGY_PATCH_PRESETS,
  type TopologyPatchIntentId,
} from '@/lib/amwayFlowTopologyPatch';
import type { AmwayFlowTopologyDoc } from '@/services/api';
import { JOURNEY } from '@/lib/amwayFlowJourneyCopy';
import { invalidateFlowEntityCache } from '@/lib/amwayFlowEntityCache';

export type FlowTopologyDoc = AmwayFlowTopologyDoc;

type PatchPreview = {
  source: 'preset' | 'nl';
  intentId?: TopologyPatchIntentId;
  ops: Array<Record<string, unknown>>;
  summaryText: string;
  planSummary: string;
  plannedPlatforms: string[];
  compileMatched?: string;
  compileMode?: string;
};

function parseTopologyDoc(raw: unknown): FlowTopologyDoc {
  const parsed = raw as Partial<FlowTopologyDoc> | null;
  if (!parsed || typeof parsed !== 'object') {
    return { version: 1, customNodes: [], customEdges: [], removedEdgeIds: [] };
  }
  return {
    version: typeof parsed.version === 'number' ? parsed.version : 1,
    customNodes: Array.isArray(parsed.customNodes) ? parsed.customNodes : [],
    customEdges: Array.isArray(parsed.customEdges) ? parsed.customEdges : [],
    removedEdgeIds: Array.isArray(parsed.removedEdgeIds) ? parsed.removedEdgeIds : [],
  };
}

export function AmwayFlowTopologyPatchBar({
  entityId,
  getExpectedVersion,
  setExpectedVersion,
  disabled = false,
  isAwaitingPlanConfirm = false,
  onRefreshFlowPlan,
  onTopologyApplied,
  embedded = false,
}: {
  entityId: string;
  getExpectedVersion: () => number | null;
  setExpectedVersion: (version: number) => void;
  disabled?: boolean;
  isAwaitingPlanConfirm?: boolean;
  onRefreshFlowPlan?: () => void | Promise<void>;
  onTopologyApplied: (topology: FlowTopologyDoc) => void;
  embedded?: boolean;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [preview, setPreview] = useState<PatchPreview | null>(null);
  const [nlText, setNlText] = useState('');

  const ingestPreview = useCallback(
    (resp: {
      base?: { version?: number };
      ops?: Array<Record<string, unknown>>;
      summary?: { text?: string };
      plan?: { summary?: string; planned_platforms?: string[] };
      compile?: { matched?: string; mode?: string };
    }, source: 'preset' | 'nl', intentId?: TopologyPatchIntentId) => {
      if (typeof resp.base?.version === 'number') {
        setExpectedVersion(resp.base.version);
      }
      const ops = Array.isArray(resp.ops) ? resp.ops : [];
      if (!ops.length) {
        setPreview(null);
        setError(JOURNEY.chatCompileFail);
        return;
      }
      const planned = Array.isArray(resp.plan?.planned_platforms)
        ? resp.plan!.planned_platforms!.map(String)
        : [];
      setPreview({
        source,
        intentId,
        ops,
        summaryText: String(resp.summary?.text || '无实质变更'),
        planSummary: String(resp.plan?.summary || ''),
        plannedPlatforms: planned,
        compileMatched: resp.compile?.matched ? String(resp.compile.matched) : undefined,
        compileMode: resp.compile?.mode ? String(resp.compile.mode) : undefined,
      });
      setError(null);
    },
    [setExpectedVersion],
  );

  const previewPreset = useCallback(
    async (intentId: TopologyPatchIntentId) => {
      if (busy || disabled) return;
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const resp = await api.previewAmwayFlowTopologyPatch(entityId, {
          intent_id: intentId,
          expected_version: getExpectedVersion(),
        });
        ingestPreview(resp, 'preset', intentId);
      } catch (err) {
        const message = err instanceof Error ? err.message : '预览失败';
        setPreview(null);
        setError(
          message.includes('版本冲突')
            ? '拓扑版本冲突：请刷新页面后再预览。'
            : message,
        );
      } finally {
        setBusy(false);
      }
    },
    [busy, disabled, entityId, getExpectedVersion, ingestPreview],
  );

  const previewNl = useCallback(async () => {
    if (busy || disabled) return;
    const text = nlText.trim();
    if (!text) {
      setError('请输入编排指令，例如：跳过豆包');
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const resp = await api.compileAmwayFlowTopologyNl(entityId, {
        text,
        expected_version: getExpectedVersion(),
        allow_llm: true,
      });
      ingestPreview(resp, 'nl');
    } catch (err) {
      const message = err instanceof Error ? err.message : '编译失败';
      setPreview(null);
      setError(
        message.includes('版本冲突')
          ? '拓扑版本冲突：请刷新页面后再试。'
          : message,
      );
    } finally {
      setBusy(false);
    }
  }, [busy, disabled, entityId, getExpectedVersion, ingestPreview, nlText]);

  const applyPreview = useCallback(async () => {
    if (!preview || busy || disabled) return;
    const version = getExpectedVersion();
    if (version == null) {
      setError('缺少拓扑版本，请刷新页面后重试。');
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const resp = await api.applyAmwayFlowTopologyPatch(entityId, {
        ops: preview.ops,
        expected_version: version,
      });
      if (typeof resp.version === 'number') {
        setExpectedVersion(resp.version);
      }
      invalidateFlowEntityCache(entityId);
      onTopologyApplied(parseTopologyDoc(resp.topology));
      setPreview(null);

      if (isAwaitingPlanConfirm && onRefreshFlowPlan) {
        try {
          await Promise.resolve(onRefreshFlowPlan());
          setNotice('已写入生产线，并已刷新待确认任务的计划（仍未开跑）。');
        } catch {
          setNotice('已写入生产线，但刷新计划失败；请点「刷新计划」或重新发起。');
        }
      } else {
        setNotice('已写入生产线；点「开始运行」将按新计划直接执行。');
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : '应用失败';
      setError(
        message.includes('版本冲突')
          ? JOURNEY.conflictRefresh
          : message,
      );
    } finally {
      setBusy(false);
    }
  }, [
    busy,
    disabled,
    entityId,
    getExpectedVersion,
    isAwaitingPlanConfirm,
    onRefreshFlowPlan,
    onTopologyApplied,
    preview,
    setExpectedVersion,
  ]);

  const shellClass = embedded
    ? ''
    : 'mt-3 rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2.5';

  return (
    <div className={shellClass}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs font-medium text-[var(--text-primary)]">
          {JOURNEY.patchTitle}
          <span className="ml-1.5 font-normal text-[var(--text-tertiary)]">
            {JOURNEY.patchHint}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {TOPOLOGY_PATCH_PRESETS.map((preset) => (
            <button
              key={preset.intentId}
              type="button"
              title={preset.hint}
              disabled={busy || disabled}
              onClick={() => {
                void previewPreset(preset.intentId);
              }}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-2.5 text-xs font-medium text-[var(--text-secondary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:opacity-50"
            >
              {preset.label}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={nlText}
          disabled={busy || disabled}
          onChange={(event) => setNlText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter') {
              event.preventDefault();
              void previewNl();
            }
          }}
          placeholder="例如：跳过豆包 / 加一个图谱分析节点 / 这次不生成报告"
          className="h-9 min-w-[220px] flex-1 rounded-lg border border-[var(--border-subtle)] bg-[var(--bg-primary)] px-3 text-xs text-[var(--text-primary)] outline-none transition focus:border-[var(--brand-primary)] disabled:opacity-50"
        />
        <button
          type="button"
          disabled={busy || disabled}
          onClick={() => {
            void previewNl();
          }}
          className="inline-flex h-9 items-center rounded-lg border border-[var(--border-strong)] bg-[var(--bg-primary)] px-3 text-xs font-medium text-[var(--text-primary)] transition hover:border-[var(--brand-primary)] hover:text-[var(--brand-primary)] disabled:opacity-50"
        >
          {busy ? '编译中…' : '编译预览'}
        </button>
      </div>

      {preview ? (
        <div className="mt-2 rounded-lg border border-[var(--brand-primary)]/25 bg-[var(--bg-primary)] px-3 py-2">
          <p className="text-xs leading-5 text-[var(--text-secondary)]">
            <span className="font-medium text-[var(--text-primary)]">变更摘要：</span>
            {preview.summaryText}
            {preview.compileMatched || preview.compileMode ? (
              <span className="ml-1 text-[var(--text-tertiary)]">
                （
                {preview.compileMode === 'llm'
                  ? '智能'
                  : preview.compileMode === 'rule'
                    ? '规则'
                    : preview.source === 'nl'
                      ? '编译'
                      : '预设'}
                {preview.compileMatched ? `：${preview.compileMatched}` : ''}
                ）
              </span>
            ) : null}
          </p>
          {preview.planSummary || preview.plannedPlatforms.length ? (
            <p className="mt-1 text-xs leading-5 text-[var(--text-tertiary)]">
              {preview.planSummary
                || `计划平台：${preview.plannedPlatforms.join(', ') || '无'}`}
            </p>
          ) : null}
          <div className="mt-2 flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                void applyPreview();
              }}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--brand-primary)] bg-[var(--brand-primary)] px-3 text-xs font-semibold text-[var(--brand-contrast)] transition hover:bg-[var(--brand-hover)] disabled:opacity-60"
            >
              {busy ? '应用中…' : JOURNEY.chatApply}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={() => {
                setPreview(null);
                setError(null);
                setNotice(null);
              }}
              className="inline-flex h-8 items-center rounded-lg border border-[var(--border-subtle)] px-3 text-xs font-medium text-[var(--text-secondary)] transition hover:bg-[var(--bg-secondary)] disabled:opacity-60"
            >
              取消
            </button>
          </div>
        </div>
      ) : null}

      {notice ? (
        <p className="mt-2 text-xs leading-5 text-[var(--brand-primary)]">{notice}</p>
      ) : null}
      {error ? (
        <p className="mt-2 text-xs leading-5 text-[var(--error)]">{error}</p>
      ) : null}
      {isAwaitingPlanConfirm ? (
        <p className="mt-1.5 text-[11px] leading-4 text-[var(--text-tertiary)]">
          仍有待确认的历史任务：应用编排会刷新其计划快照，不会自动开始采集。
        </p>
      ) : null}
    </div>
  );
}
