'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  RiCoinsLine,
  RiCpuLine,
  RiFlashlightLine,
  RiRefreshLine,
  RiPulseLine,
  RiTimeLine,
} from '@remixicon/react';
import { api } from '@/services/api';
import type { LLMObservabilitySnapshot } from '@/types/observability';

interface LLMObservabilityPanelProps {
  entityId: string | null;
  brandName?: string;
}

const WINDOW_OPTIONS = [
  { label: '7 天', value: 7 },
  { label: '30 天', value: 30 },
  { label: '90 天', value: 90 },
] as const;

const REFRESH_INTERVAL_MS = 30_000;

function formatInteger(value: number) {
  return value.toLocaleString('zh-CN');
}

function formatTokens(value: number) {
  return formatInteger(value);
}

function formatPercent(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0%';
  return `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
}

function formatCost(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '¥0';
  return `¥${value >= 1 ? value.toFixed(2) : value.toFixed(4)}`;
}

function formatLatency(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0 毫秒';
  if (value < 1000) return `${Math.round(value)} 毫秒`;
  if (value < 60_000) return `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)} 秒`;
  const totalSeconds = Math.round(value / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes} 分 ${seconds} 秒`;
}

function formatRelativeTime(value: string | null) {
  if (!value) return '--';
  const timestamp = new Date(value).getTime();
  const diff = Date.now() - timestamp;
  const minutes = Math.floor(diff / 60_000);
  if (minutes < 1) return '刚刚';
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(value).toLocaleDateString('zh-CN');
}

function SummaryCard({
  label,
  value,
  meta,
  icon: Icon,
}: {
  label: string;
  value: string;
  meta: string;
  icon: typeof RiCpuLine;
}) {
  return (
    <div
      className="rounded-[24px] border px-4 py-4"
      style={{
        borderColor: 'var(--border-subtle)',
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 86%, transparent), var(--bg-tertiary))',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <div className="text-[12px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
          {label}
        </div>
        <Icon className="h-4 w-4" style={{ color: 'var(--text-tertiary)' }} />
      </div>
      <div className="mt-3 text-[26px] font-semibold tracking-[-0.03em]" style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
      <div className="mt-2 text-[12px] leading-5" style={{ color: 'var(--text-secondary)' }}>
        {meta}
      </div>
    </div>
  );
}

function BreakdownList({
  title,
  emptyText,
  items,
  mode,
}: {
  title: string;
  emptyText: string;
  items: Array<{
    key: string;
    label: string;
    calls: number;
    tokens: number;
    cost: number;
    rawCost: number;
    savings: number;
    cacheHitRatio: number;
    cachedTokens: number;
    latency: number;
  }>;
  mode: 'model' | 'step' | 'skill';
}) {
  return (
    <div
      className="rounded-[24px] border px-5 py-5"
      style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}
    >
      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {title}
      </div>
      {items.length === 0 ? (
        <div className="mt-4 text-sm" style={{ color: 'var(--text-secondary)' }}>
          {emptyText}
        </div>
      ) : (
        <div className="mt-4 space-y-3">
          {items.map((item) => (
            <div
              key={`${mode}-${item.key}`}
              className="rounded-2xl border px-4 py-4"
              style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}
            >
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {item.label}
                  </div>
                  <div className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                    {item.calls} 次调用 / {formatTokens(item.tokens)} 令牌 / 缓存 {formatPercent(item.cacheHitRatio)}
                  </div>
                </div>
                <div className="text-right text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                  <div>{formatLatency(item.latency)}</div>
                  <div>{formatCost(item.cost)}</div>
                  <div style={{ color: 'var(--text-tertiary)' }}>
                    节省 {formatCost(item.savings)}
                  </div>
                </div>
              </div>
              <div className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                命中缓存 {formatTokens(item.cachedTokens)}，原始估算 {formatCost(item.rawCost)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function LLMObservabilityPanel({
  entityId,
  brandName,
}: LLMObservabilityPanelProps) {
  const [days, setDays] = useState<number>(30);
  const [snapshot, setSnapshot] = useState<LLMObservabilitySnapshot | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasSnapshotRef = useRef(false);
  const inFlightRef = useRef(false);

  useEffect(() => {
    hasSnapshotRef.current = snapshot !== null;
  }, [snapshot]);

  useEffect(() => {
    let cancelled = false;

    async function loadSnapshot(options?: { background?: boolean }) {
      if (!entityId) {
        setSnapshot(null);
        setError(null);
        hasSnapshotRef.current = false;
        return;
      }
      if (inFlightRef.current) return;

      const isBackground = Boolean(options?.background && hasSnapshotRef.current);
      inFlightRef.current = true;
      if (isBackground) {
        setIsRefreshing(true);
      } else {
        setIsLoading(true);
        setError(null);
      }
      try {
        const next = await api.getTaskObservability({
          entityId,
          days,
          limit: 8,
        });
        if (!cancelled) {
          setError(null);
          setSnapshot(next);
          hasSnapshotRef.current = true;
        }
      } catch (err) {
        if (!cancelled) {
          if (hasSnapshotRef.current) {
            console.warn('[LLMObservability] refresh failed', err);
          } else {
            setError(err instanceof Error ? err.message : '观测数据加载失败');
            setSnapshot(null);
            hasSnapshotRef.current = false;
          }
        }
      } finally {
        inFlightRef.current = false;
        if (!cancelled) setIsLoading(false);
        if (!cancelled) setIsRefreshing(false);
      }
    }

    void loadSnapshot();

    const refreshIfVisible = () => {
      if (document.visibilityState === 'visible') {
        void loadSnapshot({ background: true });
      }
    };

    const intervalId = window.setInterval(refreshIfVisible, REFRESH_INTERVAL_MS);
    window.addEventListener('focus', refreshIfVisible);
    window.addEventListener('online', refreshIfVisible);
    document.addEventListener('visibilitychange', refreshIfVisible);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
      window.removeEventListener('focus', refreshIfVisible);
      window.removeEventListener('online', refreshIfVisible);
      document.removeEventListener('visibilitychange', refreshIfVisible);
    };
  }, [days, entityId]);

  const handleRefresh = async () => {
    if (!entityId || inFlightRef.current) return;

    setError(null);
    setIsRefreshing(true);
    inFlightRef.current = true;
    try {
      const next = await api.getTaskObservability({
        entityId,
        days,
        limit: 8,
      });
      setSnapshot(next);
      hasSnapshotRef.current = true;
    } catch (err) {
      setError(err instanceof Error ? err.message : '观测数据加载失败');
    } finally {
      inFlightRef.current = false;
      setIsRefreshing(false);
    }
  };

  const summary = snapshot?.summary;
  const hasData = Boolean(summary && summary.call_count > 0);
  const modelItems = useMemo(
    () =>
      (snapshot?.by_model || []).map((item) => ({
        key: `${item.provider || ''}-${item.model_name || ''}`,
        label: item.model_name || item.provider || '未命名模型',
        calls: item.call_count,
        tokens: item.total_tokens,
        cost: item.total_cost_cache_aware,
        rawCost: item.total_cost,
        savings: item.estimated_savings,
        cacheHitRatio: item.cache_hit_ratio,
        cachedTokens: item.cached_prompt_tokens,
        latency: item.avg_latency_ms,
      })),
    [snapshot?.by_model]
  );
  const stepItems = useMemo(
    () =>
      (snapshot?.by_step || []).map((item) => ({
        key: `${item.step || ''}-${item.step_name || ''}`,
        label: item.step_name || item.step || '未命名步骤',
        calls: item.call_count,
        tokens: item.total_tokens,
        cost: item.total_cost_cache_aware,
        rawCost: item.total_cost,
        savings: item.estimated_savings,
        cacheHitRatio: item.cache_hit_ratio,
        cachedTokens: item.cached_prompt_tokens,
        latency: item.avg_latency_ms,
      })),
    [snapshot?.by_step]
  );
  const skillItems = useMemo(
    () =>
      (snapshot?.by_skill || []).map((item) => ({
        key: item.skill_key || 'unknown-skill',
        label: item.skill_key || '未归类 Skill',
        calls: item.call_count,
        tokens: item.total_tokens,
        cost: item.total_cost_cache_aware,
        rawCost: item.total_cost,
        savings: item.estimated_savings,
        cacheHitRatio: item.cache_hit_ratio,
        cachedTokens: item.cached_prompt_tokens,
        latency: item.avg_latency_ms,
      })),
    [snapshot?.by_skill]
  );

  if (!entityId) return null;

  return (
    <section
      className="rounded-[28px] border px-5 py-5 md:px-6 md:py-6"
      style={{
        borderColor: 'var(--border-subtle)',
        background:
          'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 88%, transparent), var(--bg-tertiary))',
      }}
    >
      <div className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-end md:justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="max-w-3xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--text-tertiary)' }}>
            大模型可观测性
          </div>
          <h2 className="mt-2 text-[22px] font-semibold tracking-[-0.02em]" style={{ color: 'var(--text-primary)' }}>
            {brandName ? `${brandName} 的令牌消耗 / 缓存 / 成本 / 时延` : '当前品牌的大模型观测'}
          </h2>
            <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              展示当前品牌在最近时间窗口内的模型调用量、令牌消耗、缓存命中、估算成本和响应时延。
            </p>
          <p className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
            页面保持可见时会自动刷新，也可以手动拉取最新观测结果。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => void handleRefresh()}
            disabled={isLoading || isRefreshing}
            className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-60"
            style={{
              color: 'var(--text-secondary)',
              backgroundColor: 'var(--bg-secondary)',
              border: '1px solid var(--border-subtle)',
            }}
          >
            <RiRefreshLine className={`h-3.5 w-3.5 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? '刷新中' : '刷新'}
          </button>
          {WINDOW_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              onClick={() => setDays(option.value)}
              className="rounded-full px-3 py-1.5 text-xs font-medium transition-colors"
              style={{
                color: days === option.value ? '#fff' : 'var(--text-secondary)',
                backgroundColor: days === option.value ? 'var(--color-primary)' : 'var(--bg-secondary)',
                border: days === option.value ? '1px solid transparent' : '1px solid var(--border-subtle)',
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className="h-[128px] rounded-[24px] animate-shimmer" />
          ))}
        </div>
      ) : error ? (
        <div
          className="mt-6 rounded-[22px] border px-4 py-4 text-sm"
          style={{
            borderColor: 'rgba(239,68,68,0.24)',
            backgroundColor: 'rgba(239,68,68,0.08)',
            color: 'var(--text-primary)',
          }}
        >
          {error}
        </div>
      ) : !hasData ? (
        <div
          className="mt-6 rounded-[22px] border border-dashed px-5 py-5 text-sm leading-7"
          style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}
        >
          当前窗口内暂无模型调用记录。
        </div>
      ) : (
        <div className="mt-6 space-y-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <SummaryCard
              label="总调用量"
              value={formatInteger(summary?.call_count || 0)}
              meta={`${summary?.unique_models || 0} 个模型参与`}
              icon={RiCpuLine}
            />
            <SummaryCard
              label="总令牌消耗"
              value={formatTokens(summary?.total_tokens || 0)}
              meta={`输入 ${formatTokens(summary?.prompt_tokens || 0)} / 输出 ${formatTokens(summary?.completion_tokens || 0)}`}
              icon={RiFlashlightLine}
            />
            <SummaryCard
              label="缓存命中率"
              value={formatPercent(summary?.cache_hit_ratio || 0)}
              meta={`命中 ${formatTokens(summary?.cached_prompt_tokens || 0)} / 输入 ${formatTokens(summary?.prompt_tokens || 0)}`}
              icon={RiRefreshLine}
            />
            <SummaryCard
              label="缓存后成本"
              value={formatCost(summary?.total_cost_cache_aware || 0)}
              meta={`较原始估算节省 ${formatCost(summary?.estimated_savings || 0)}`}
              icon={RiCoinsLine}
            />
            <SummaryCard
              label="平均时延"
              value={formatLatency(summary?.avg_latency_ms || 0)}
              meta={`总等待 ${formatLatency(summary?.total_latency_ms || 0)}`}
              icon={RiTimeLine}
            />
          </div>

          <div className="grid gap-4 xl:grid-cols-3">
            <BreakdownList
              title="模型分布"
              emptyText="当前窗口没有模型分布数据。"
              items={modelItems}
              mode="model"
            />
            <BreakdownList
              title="步骤分布"
              emptyText="当前窗口没有步骤分布数据。"
              items={stepItems}
              mode="step"
            />
            <BreakdownList
              title="Skill 分布"
              emptyText="当前窗口没有 Skill 分布数据。"
              items={skillItems}
              mode="skill"
            />
          </div>

          <div
            className="rounded-[24px] border"
            style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}
          >
            <div className="flex items-center gap-2 border-b px-5 py-4" style={{ borderColor: 'var(--border-subtle)' }}>
              <RiPulseLine className="h-4 w-4" style={{ color: 'var(--text-tertiary)' }} />
              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                最近调用
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr style={{ color: 'var(--text-tertiary)' }}>
                    <th className="px-5 py-3 font-medium">时间</th>
                    <th className="px-5 py-3 font-medium">步骤</th>
                    <th className="px-5 py-3 font-medium">模型</th>
                    <th className="px-5 py-3 font-medium">令牌</th>
                    <th className="px-5 py-3 font-medium">缓存</th>
                    <th className="px-5 py-3 font-medium">时延</th>
                    <th className="px-5 py-3 font-medium">成本</th>
                  </tr>
                </thead>
                <tbody>
                  {(snapshot?.recent_calls || []).map((call) => (
                    <tr key={call.id} style={{ borderTop: '1px solid var(--border-subtle)' }}>
                      <td className="px-5 py-3 align-top" style={{ color: 'var(--text-secondary)' }}>
                        {formatRelativeTime(call.created_at)}
                      </td>
                      <td className="px-5 py-3 align-top">
                        <div className="font-medium" style={{ color: 'var(--text-primary)' }}>
                          {call.step_name || call.step || '未命名步骤'}
                        </div>
                        <div className="mt-1 flex flex-wrap items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          <span>{call.brand_name}</span>
                          {call.skill_key ? (
                            <span
                              className="rounded-full px-2 py-0.5"
                              style={{
                                border: '1px solid var(--border-subtle)',
                                backgroundColor: 'var(--bg-secondary)',
                                color: 'var(--text-secondary)',
                              }}
                            >
                              {call.skill_key}
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td className="px-5 py-3 align-top">
                        <div className="font-medium" style={{ color: 'var(--text-primary)' }}>
                          {call.model_name}
                        </div>
                        <div className="mt-1 text-xs uppercase tracking-[0.14em]" style={{ color: 'var(--text-tertiary)' }}>
                          {call.provider}
                        </div>
                      </td>
                      <td className="px-5 py-3 align-top" style={{ color: 'var(--text-secondary)' }}>
                        {formatInteger(call.total_tokens)}
                      </td>
                      <td className="px-5 py-3 align-top" style={{ color: 'var(--text-secondary)' }}>
                        <div>{formatInteger(call.cached_prompt_tokens)}</div>
                        <div className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          {formatPercent(call.cache_hit_ratio)}
                        </div>
                      </td>
                      <td className="px-5 py-3 align-top" style={{ color: 'var(--text-secondary)' }}>
                        {formatLatency(call.latency_ms)}
                      </td>
                      <td className="px-5 py-3 align-top" style={{ color: 'var(--text-secondary)' }}>
                        <div>{formatCost(call.estimated_cost_cache_aware)}</div>
                        <div className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          节省 {formatCost(call.estimated_savings)}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
