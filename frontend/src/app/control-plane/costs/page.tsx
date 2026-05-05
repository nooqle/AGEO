'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  RiArrowLeftLine,
  RiArrowRightUpLine,
  RiRefreshLine,
  RiSearch2Line,
} from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import {
  ControlPlanePanel,
  ControlPlaneShell,
  ControlPlaneStatCard,
  controlPlanePalette,
} from '@/components/control-plane/ControlPlaneShell';
import { formatControlPlaneCost } from '@/components/control-plane/ControlPlaneDataPanels';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AuthUser } from '@/types/auth';
import type {
  ControlPlaneCostBreakdown,
  ControlPlaneCustomerSummary,
  ControlPlaneObservabilitySnapshot,
  ControlPlaneRecentCall,
  ControlPlaneReuseDiagnostic,
} from '@/types/controlPlane';
import { formatDateTime } from '@/lib/utils';

const palette = controlPlanePalette();

function formatCost(value: number, currency = 'CNY') {
  return formatControlPlaneCost(value, currency);
}

function formatPercent(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0%';
  return `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
}

function formatHash(value: string | null) {
  if (!value) return '--';
  return value.length > 8 ? value.slice(0, 8) : value;
}

function formatSize(value: number) {
  if (!Number.isFinite(value) || value <= 0) return '0';
  return value.toLocaleString();
}

export default function ControlPlaneCostsPage() {
  return (
    <RequireAuth>
      <ControlPlaneCostsContent />
    </RequireAuth>
  );
}

function ControlPlaneCostsContent() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [days, setDays] = useState(30);
  const [customers, setCustomers] = useState<ControlPlaneCustomerSummary[]>([]);
  const [snapshot, setSnapshot] = useState<ControlPlaneObservabilitySnapshot | null>(
    null
  );
  const [organizationFilter, setOrganizationFilter] = useState('all');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  async function loadData(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const user = await api.getMe();
      setCurrentUser(user);
      if (user.role !== 'internal_admin') {
        setCustomers([]);
        setSnapshot(null);
        return;
      }
      const [customerRows, observability] = await Promise.all([
        api.getControlPlaneCustomers(days),
        api.getControlPlaneObservability({
          days,
          organizationId:
            organizationFilter === 'all' ? undefined : organizationFilter,
          limit: 16,
        }),
      ]);
      setCustomers(customerRows);
      setSnapshot(observability);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载成本观测失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadData();
    // loadData intentionally reads latest state and is invoked manually elsewhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, organizationFilter]);

  const filteredCustomerBrandRows = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const rows = snapshot?.by_customer_brand || [];
    if (!normalizedQuery) return rows;
    return rows.filter((row) =>
      [row.customer_name, row.brand_name]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery))
    );
  }, [query, snapshot]);

  const filteredRecentCalls = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const rows = snapshot?.recent_calls || [];
    if (!normalizedQuery) return rows;
    return rows.filter((row) =>
      [
        row.customer_name,
        row.brand_name,
        row.provider,
        row.model_name,
        row.step_name,
        row.step,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery))
    );
  }, [query, snapshot]);

  return (
    <ControlPlaneShell
      title="成本观测"
      description="查看客户、品牌、模型、步骤和最近调用，区分输入、输出、缓存命中和估算费用。"
      breadcrumbs={[
        { label: '设置', href: '/settings' },
        { label: '运营工作台', href: '/control-plane' },
        { label: '成本观测' },
      ]}
      actions={
        <div className="flex items-center gap-2">
          <Link
            href="/control-plane"
            className="inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold"
            style={{
              borderColor: palette.borderStrong,
              background: palette.panel,
              color: palette.muted,
            }}
          >
            <RiArrowLeftLine className="h-4 w-4" />
            返回工作台
          </Link>
          <div
            className="inline-flex rounded-xl border p-1"
            style={{ borderColor: palette.border, background: palette.panel }}
          >
            {[7, 30, 90].map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => setDays(option)}
                className="rounded-xl px-3 py-2 text-xs font-semibold transition-colors"
                style={{
                  background: days === option ? palette.accent : 'transparent',
                  color: days === option ? palette.accentContrast : palette.muted,
                }}
              >
                最近 {option} 天
              </button>
            ))}
          </div>
          <Button
            variant="outline"
            size="md"
            onClick={() => void loadData(true)}
            isLoading={refreshing}
            leftIcon={<RiRefreshLine className="h-4 w-4" />}
          >
            刷新观测
          </Button>
        </div>
      }
    >
      {currentUser?.role !== 'internal_admin' && !loading ? (
        <div
          className="rounded-xl border px-4 py-6 text-sm"
          style={{
            borderColor: palette.border,
            color: palette.muted,
            background: palette.panel,
          }}
        >
          当前账号没有内部运营权限，无法访问成本观测。
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-4">
            <ControlPlaneStatCard
              label="估算成本"
              value={
                snapshot
                  ? formatCost(
                      snapshot.summary.total_cost_cache_aware,
                      snapshot.summary.currency
                    )
                  : '--'
              }
              hint={
                snapshot
                  ? `未计缓存 ${formatCost(
                      snapshot.summary.total_cost,
                      snapshot.summary.currency
                    )}`
                  : '等待数据'
              }
            />
            <ControlPlaneStatCard
              label="缓存节省"
              value={
                snapshot
                  ? formatCost(
                      snapshot.summary.estimated_savings,
                      snapshot.summary.currency
                    )
                  : '--'
              }
              hint={
                snapshot
                  ? `命中 ${formatPercent(snapshot.summary.cache_hit_ratio)}`
                  : '等待数据'
              }
            />
            <ControlPlaneStatCard
              label="Token 用量"
              value={snapshot ? snapshot.summary.total_tokens.toLocaleString() : '--'}
              hint={
                snapshot
                  ? `输入 ${snapshot.summary.prompt_tokens.toLocaleString()} / 输出 ${snapshot.summary.completion_tokens.toLocaleString()}`
                  : `最近 ${days} 天`
              }
            />
            <ControlPlaneStatCard
              label="平均时延"
              value={
                snapshot
                  ? `${Math.round(snapshot.summary.avg_latency_ms).toLocaleString()} ms`
                  : '--'
              }
              hint={
                snapshot
                  ? `调用 ${snapshot.summary.call_count.toLocaleString()} 次`
                  : '等待数据'
              }
            />
          </div>

          <ControlPlanePanel title="提示词复用诊断">
            <PromptReuseDiagnostics snapshot={snapshot} loading={loading} />
          </ControlPlanePanel>

          <ControlPlanePanel title="筛选条件">
            <div className="grid gap-4 xl:grid-cols-[280px_minmax(320px,1fr)]">
              <label className="block">
                <div
                  className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                  style={{ color: palette.subtle }}
                >
                  客户组织
                </div>
                <select
                  value={organizationFilter}
                  onChange={(event) => setOrganizationFilter(event.target.value)}
                  className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                  style={{
                    background: palette.panel,
                    borderColor: palette.borderStrong,
                    color: palette.text,
                  }}
                >
                  <option value="all">全部组织</option>
                  {customers.map((customer) => (
                    <option key={customer.organization_id} value={customer.organization_id}>
                      {customer.customer_name}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <div
                  className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                  style={{ color: palette.subtle }}
                >
                  关键词
                </div>
                <div
                  className="flex h-11 items-center gap-2 rounded-lg border px-3"
                  style={{
                    borderColor: palette.borderStrong,
                    background: palette.panel,
                  }}
                >
                  <RiSearch2Line className="h-4 w-4" style={{ color: palette.subtle }} />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索客户、品牌、模型、步骤"
                    className="w-full bg-transparent text-sm outline-none"
                    style={{ color: palette.text }}
                  />
                </div>
              </label>
            </div>
          </ControlPlanePanel>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
            <ControlPlanePanel
              title="客户与品牌"
            >
              <CostBreakdownTable
                rows={filteredCustomerBrandRows}
                loading={loading}
                columns="customer-brand"
              />
            </ControlPlanePanel>

            <div className="space-y-6">
              <ControlPlanePanel title="模型维度">
                <CostBreakdownTable
                  rows={snapshot?.by_model || []}
                  loading={loading}
                  columns="model"
                />
              </ControlPlanePanel>

              <ControlPlanePanel title="步骤维度">
                <CostBreakdownTable
                  rows={snapshot?.by_step || []}
                  loading={loading}
                  columns="step"
                />
              </ControlPlanePanel>
            </div>
          </div>

          <ControlPlanePanel title="Recent Calls">
            <RecentCallsTable rows={filteredRecentCalls} loading={loading} />
          </ControlPlanePanel>
        </div>
      )}
    </ControlPlaneShell>
  );
}

function CostBreakdownTable({
  rows,
  loading,
  columns,
}: {
  rows: ControlPlaneCostBreakdown[];
  loading: boolean;
  columns: 'customer-brand' | 'model' | 'step';
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[760px] text-left text-sm">
        <thead>
          <tr style={{ color: palette.subtle }}>
            {columns === 'customer-brand' ? (
              <>
                <th className="pb-3 pr-4 font-semibold">客户</th>
                <th className="pb-3 pr-4 font-semibold">品牌</th>
              </>
            ) : null}
            {columns === 'model' ? (
              <>
                <th className="pb-3 pr-4 font-semibold">Provider</th>
                <th className="pb-3 pr-4 font-semibold">Model</th>
              </>
            ) : null}
            {columns === 'step' ? (
              <>
                <th className="pb-3 pr-4 font-semibold">步骤</th>
                <th className="pb-3 pr-4 font-semibold">名称</th>
              </>
            ) : null}
            <th className="pb-3 pr-4 font-semibold">调用</th>
            <th className="pb-3 pr-4 font-semibold">Token</th>
            <th className="pb-3 pr-4 font-semibold">输入 / 输出</th>
            <th className="pb-3 pr-4 font-semibold">缓存</th>
            <th className="pb-3 pr-4 font-semibold">费用</th>
            <th className="pb-3 font-semibold">平均时延</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={8} className="py-8 text-center" style={{ color: palette.muted }}>
                正在加载明细...
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={8} className="py-8 text-center" style={{ color: palette.muted }}>
                当前窗口内没有明细记录。
              </td>
            </tr>
          ) : (
            rows.map((row, index) => (
              <tr key={`${columns}-${index}`} className="border-t" style={{ borderColor: palette.border }}>
                {columns === 'customer-brand' ? (
                  <>
                    <td className="py-4 pr-4">
                      {row.organization_id ? (
                        <Link
                          href={`/control-plane/customers/${row.organization_id}`}
                          className="inline-flex items-center gap-1 font-medium"
                          style={{ color: palette.accent }}
                        >
                          {row.customer_name || '--'}
                          <RiArrowRightUpLine className="h-3.5 w-3.5" />
                        </Link>
                      ) : (
                        <span>{row.customer_name || '--'}</span>
                      )}
                    </td>
                    <td className="py-4 pr-4">{row.brand_name || '--'}</td>
                  </>
                ) : null}
                {columns === 'model' ? (
                  <>
                    <td className="py-4 pr-4">{row.provider || '--'}</td>
                    <td className="py-4 pr-4">{row.model_name || '--'}</td>
                  </>
                ) : null}
                {columns === 'step' ? (
                  <>
                    <td className="py-4 pr-4">{row.step || '--'}</td>
                    <td className="py-4 pr-4">{row.step_name || '--'}</td>
                  </>
                ) : null}
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.call_count}
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.total_tokens.toLocaleString()}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    计费输入 {row.billable_prompt_tokens.toLocaleString()}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.prompt_tokens.toLocaleString()} / {row.completion_tokens.toLocaleString()}
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatPercent(row.cache_hit_ratio)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    命中 {row.cached_prompt_tokens.toLocaleString()}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatCost(row.total_cost_cache_aware, row.currency)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    省 {formatCost(row.estimated_savings, row.currency)}
                  </div>
                </td>
                <td className="py-4" style={{ color: palette.muted }}>
                  {Math.round(row.avg_latency_ms).toLocaleString()} ms
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

function PromptReuseDiagnostics({
  snapshot,
  loading,
}: {
  snapshot: ControlPlaneObservabilitySnapshot | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="py-6 text-sm" style={{ color: palette.muted }}>
        正在加载提示词复用诊断...
      </div>
    );
  }
  if (!snapshot) {
    return (
      <div className="py-6 text-sm" style={{ color: palette.muted }}>
        当前窗口内没有可诊断的调用。
      </div>
    );
  }
  const summary = snapshot.summary;
  if (summary.diagnostic_sample_count === 0) {
    return (
      <div className="py-6 text-sm" style={{ color: palette.muted }}>
        当前窗口内没有可诊断的调用。
      </div>
    );
  }
  const metrics = [
    {
      label: '诊断样本',
      value: summary.diagnostic_sample_count.toLocaleString(),
      hint: `低复用 ${summary.low_cache_call_count.toLocaleString()} 次`,
    },
    {
      label: '低复用比例',
      value: formatPercent(summary.low_cache_call_ratio),
      hint: `阈值 ${formatPercent(0.2)}`,
    },
    {
      label: '固定提示词版本',
      value: summary.static_prompt_variant_count.toLocaleString(),
      hint: '同一版本内越少越稳定',
    },
    {
      label: '工具清单版本',
      value: summary.tool_surface_variant_count.toLocaleString(),
      hint: '工具面变化会影响复用',
    },
    {
      label: '平均动态上下文',
      value: formatSize(summary.avg_runtime_context_size),
      hint: `最大 ${formatSize(summary.max_runtime_context_size)}`,
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-4 md:grid-cols-5">
        {metrics.map((metric) => (
          <div
            key={metric.label}
            className="border-l pl-3"
            style={{ borderColor: palette.borderStrong }}
          >
            <div className="text-xs font-semibold" style={{ color: palette.subtle }}>
              {metric.label}
            </div>
            <div className="mt-1 text-xl font-semibold" style={{ color: palette.text }}>
              {metric.value}
            </div>
            <div className="mt-1 text-xs" style={{ color: palette.muted }}>
              {metric.hint}
            </div>
          </div>
        ))}
      </div>
      <div className="divide-y" style={{ borderColor: palette.border }}>
        {snapshot.reuse_diagnostics.map((item) => (
          <ReuseDiagnosticRow key={item.code} item={item} />
        ))}
      </div>
    </div>
  );
}

function ReuseDiagnosticRow({ item }: { item: ControlPlaneReuseDiagnostic }) {
  const tone =
    item.severity === 'critical'
      ? 'var(--status-error)'
      : item.severity === 'warning'
        ? 'var(--status-warning)'
        : palette.accent;
  return (
    <div className="grid gap-3 py-4 md:grid-cols-[180px_minmax(0,1fr)_120px]">
      <div className="text-sm font-semibold" style={{ color: tone }}>
        {item.title}
      </div>
      <div className="text-sm" style={{ color: palette.muted }}>
        {item.message}
      </div>
      <div className="text-sm md:text-right" style={{ color: palette.subtle }}>
        {item.affected_count > 0 ? `${item.affected_count.toLocaleString()} 次` : '无异常'}
        {typeof item.ratio === 'number' ? ` / ${formatPercent(item.ratio)}` : ''}
      </div>
    </div>
  );
}

function RecentCallsTable({
  rows,
  loading,
}: {
  rows: ControlPlaneRecentCall[];
  loading: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[1080px] text-left text-sm">
        <thead>
          <tr style={{ color: palette.subtle }}>
            <th className="pb-3 pr-4 font-semibold">客户</th>
            <th className="pb-3 pr-4 font-semibold">品牌</th>
            <th className="pb-3 pr-4 font-semibold">Model</th>
            <th className="pb-3 pr-4 font-semibold">Step</th>
            <th className="pb-3 pr-4 font-semibold">Token</th>
            <th className="pb-3 pr-4 font-semibold">费用</th>
            <th className="pb-3 pr-4 font-semibold">缓存命中</th>
            <th className="pb-3 pr-4 font-semibold">诊断</th>
            <th className="pb-3 font-semibold">时间</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                正在加载最近调用...
              </td>
            </tr>
          ) : rows.length === 0 ? (
            <tr>
              <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                当前窗口内没有调用明细。
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={row.id} className="border-t" style={{ borderColor: palette.border }}>
                <td className="py-4 pr-4">
                  {row.organization_id ? (
                    <Link
                      href={`/control-plane/customers/${row.organization_id}`}
                      className="inline-flex items-center gap-1 font-medium"
                      style={{ color: palette.accent }}
                    >
                      {row.customer_name || '--'}
                      <RiArrowRightUpLine className="h-3.5 w-3.5" />
                    </Link>
                  ) : (
                    <span>{row.customer_name || '--'}</span>
                  )}
                </td>
                <td className="py-4 pr-4">{row.brand_name}</td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.provider} / {row.model_name}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    {row.model_identity || `${row.provider}:${row.model_name}`}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.step_name || row.step || '--'}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    prompt {formatHash(row.static_prompt_hash)} / tool {formatHash(row.tool_surface_hash)}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.total_tokens.toLocaleString()}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    输入 {row.prompt_tokens.toLocaleString()} / 输出 {row.completion_tokens.toLocaleString()}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatCost(row.estimated_cost_cache_aware, row.currency)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    省 {formatCost(row.estimated_savings, row.currency)}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatPercent(row.cache_hit_ratio)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    命中 {row.cached_prompt_tokens.toLocaleString()} / 未命中 {row.billable_prompt_tokens.toLocaleString()}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.reuse_diagnosis || '正常'}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    动态 {row.runtime_context_size === null ? '--' : row.runtime_context_size.toLocaleString()}
                  </div>
                </td>
                <td className="py-4" style={{ color: palette.muted }}>
                  {row.created_at ? formatDateTime(row.created_at) : '--'}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
