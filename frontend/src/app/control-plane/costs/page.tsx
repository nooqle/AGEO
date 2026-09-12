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
  ControlPlaneCurrencyCost,
  ControlPlaneCacheCoverage,
} from '@/types/controlPlane';

const palette = controlPlanePalette();

function formatCost(value: number | null | undefined, currency: string | null | undefined = null) {
  return formatControlPlaneCost(value, currency === 'UNKNOWN' ? null : currency);
}

function formatPercent(value: number | null | undefined) {
  if (value == null || !Number.isFinite(value)) return '未知';
  if (!Number.isFinite(value) || value <= 0) return '0%';
  return `${(value * 100).toFixed(value >= 0.1 ? 1 : 2)}%`;
}

function formatCostSubtotal(row: {
  total_cost_cache_aware: number | null;
  total_cost: number | null;
  estimated_savings: number | null;
  currency: string | null;
  costs_by_currency?: ControlPlaneCurrencyCost[];
}, field: 'total_cost_cache_aware' | 'total_cost' | 'estimated_savings' = 'total_cost_cache_aware') {
  if (row.costs_by_currency?.length) return row.costs_by_currency.map((cost) => formatCost(cost[field], cost.currency)).join(' / ');
  return formatCost(row[field], row.currency);
}

function pricingCoverageLabel(row: ControlPlaneCacheCoverage) {
  return `已计价 ${row.priced_call_count ?? '未知'} 次 · 未计价 ${row.unknown_pricing_call_count ?? '未知'} 次`;
}

function pricingStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    priced: '已计价', unknown_price: '定价未知', unknown_usage: '用量未知',
    unknown_cache: '缓存未知', invalid_usage: '用量异常', legacy_snapshot: '历史费用快照', legacy_unknown: '历史定价未知',
  };
  return labels[status || ''] || '定价状态未记录';
}

function formatHash(value: string | null) {
  if (!value) return '--';
  return value.length > 8 ? value.slice(0, 8) : value;
}

function formatSize(value: number | null | undefined) {
  if (value == null) return '未记录';
  if (!Number.isFinite(value) || value <= 0) return '0';
  return value.toLocaleString();
}

function tariffPeriodLabel(row: ControlPlaneRecentCall) {
  const period = row.pricing?.tariff_period;
  if (period === 'peak') return '高峰';
  if (period === 'off_peak') return '低谷';
  if (period === 'flat' || row.pricing?.source === 'tencent_hy3_guangzhou_2026_09_11') return '不区分峰谷';
  return '计价时段未记录';
}

function pricingTimeLabel(value: string) {
  // Display the timestamp in the same explicit timezone as the label, regardless of browser locale.
  if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)) return `${value}（原始时间，时区未记录）`;
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return '计价时间无效';
  return `${date.toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })}（北京时间）`;
}

function SearchCostDetail({ row }: { row: ControlPlaneRecentCall }) {
  const known = row.search_tool_cost_status === 'estimated' && row.estimated_search_tool_cost != null;
  return (
    <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
      搜索工具费：{known ? formatCost(row.estimated_search_tool_cost, row.search_tool_currency || row.currency) : '未知（未计入）'}
      {row.provider_web_search_requests != null ? ` · 搜索请求 ${row.provider_web_search_requests.toLocaleString()} 次` : ''}
      {known ? ' · 另列估算，未含在 Token 小计中' : ' · 未知不等于零费用'}
    </div>
  );
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
        <div className="flex flex-wrap items-center gap-2">
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
              label="Token 估算 · 已计价小计"
              value={
                snapshot
                  ? formatCostSubtotal(snapshot.summary)
                  : '--'
              }
              hint={
                snapshot
                  ? `未缓存基准 ${formatCostSubtotal(snapshot.summary, 'total_cost')}`
                  : '等待数据'
              }
            />
            <ControlPlaneStatCard
              label="缓存节省估算"
              value={
                snapshot
                  ? formatCostSubtotal(snapshot.summary, 'estimated_savings')
                  : '--'
              }
              hint={
                snapshot
                  ? `输入加权命中率 ${formatPercent(snapshot.summary.cache_hit_ratio)}`
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

          {snapshot ? (
            <div className="space-y-1 text-sm" style={{ color: palette.muted }}>
              <p>{pricingCoverageLabel(snapshot.summary)} · 定价覆盖率 {formatPercent(snapshot.summary.pricing_coverage)}</p>
              <p>缓存已知 {snapshot.summary.cache_known_call_count ?? '未知'} 次 / 未知 {snapshot.summary.cache_unknown_call_count ?? '未知'} 次；输入加权命中率仅统计缓存已知的输入。</p>
              <p>小计仅含 Token 费用，搜索工具费在最近调用中另列。费用使用调用时保存的定价快照，均为估算；未计价调用不计入小计，未知不等于零费用。</p>
              <p>未缓存基准与缓存后费用使用相同费率；缓存节省不等同峰谷优惠，也不是供应商账单。</p>
              <p>常规调用按本系统记录调用的时刻估算峰谷费率；显式导入的调用按所提供的时刻估算。跨时段调用的最终金额以供应商账单为准。</p>
              <p>DeepSeek 原生搜索当前按返回的 token 用量估算；若供应商另收搜索工具费，该费用尚未计入，不能视为零费用。</p>
            </div>
          ) : null}

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

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)] [&>section]:min-w-0">
            <ControlPlanePanel
              title="客户与品牌"
            >
              <CostBreakdownTable
                rows={filteredCustomerBrandRows}
                loading={loading}
                columns="customer-brand"
              />
            </ControlPlanePanel>

            <div className="min-w-0 space-y-6">
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
            <th className="pb-3 pr-4 font-semibold">Token 费用估算</th>
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
                    未命中输入 {row.billable_prompt_tokens.toLocaleString()}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.prompt_tokens.toLocaleString()} / {row.completion_tokens.toLocaleString()}
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatPercent(row.cache_hit_ratio)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    已知命中 {row.cached_prompt_tokens.toLocaleString()} · 未知 {row.cache_unknown_call_count ?? '未知'} 次
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatCostSubtotal(row)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    基准 {formatCostSubtotal(row, 'total_cost')} · 缓存节省 {formatCostSubtotal(row, 'estimated_savings')}
                  </div>
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    {pricingCoverageLabel(row)}
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
      hint: `缓存命中偏低 ${summary.low_cache_call_count.toLocaleString()} 次`,
    },
    {
      label: '单次缓存命中偏低比例',
      value: formatPercent(summary.low_cache_call_ratio),
      hint: `单次命中率低于 ${formatPercent(0.2)}，不代表浪费`,
    },
    {
      label: '固定提示词版本',
      value: summary.static_prompt_variant_count > 0 ? summary.static_prompt_variant_count.toLocaleString() : '未记录',
      hint: '跨模型和步骤的版本可不同',
    },
    {
      label: '工具清单版本',
      value: summary.tool_surface_variant_count > 0 ? summary.tool_surface_variant_count.toLocaleString() : '未记录',
      hint: '需在同模型、同步骤内比较',
    },
    {
      label: '平均动态上下文（字符）',
      value: formatSize(summary.avg_runtime_context_size),
      hint: summary.max_runtime_context_size == null ? '尚未采集长度' : `最大 ${formatSize(summary.max_runtime_context_size)} 字符`,
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
            <th className="pb-3 pr-4 font-semibold">Token 与搜索费估算 / 定价依据</th>
            <th className="pb-3 pr-4 font-semibold">输入缓存命中</th>
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
                  Token {formatCost(row.estimated_cost_cache_aware, row.currency)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    基准 {formatCost(row.estimated_cost, row.currency)} · 缓存节省 {formatCost(row.estimated_savings, row.currency)}
                  </div>
                  <SearchCostDetail row={row} />
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    {pricingStatusLabel(row.pricing_status)} · {tariffPeriodLabel(row)}
                  </div>
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    {row.pricing?.rate_version || row.pricing?.source || '定价依据未记录'}
                    {row.pricing?.priced_at ? ` · ${pricingTimeLabel(row.pricing.priced_at)}` : ''}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.cache_status === 'known' ? formatPercent(row.cache_hit_ratio) : '未知'}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    {row.cache_status === 'known' ? `命中 ${row.cached_prompt_tokens.toLocaleString()} / 未命中 ${row.billable_prompt_tokens.toLocaleString()}` : '未获得有效缓存用量'}
                  </div>
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {row.reuse_diagnosis === '缺少提示词指纹' ? '诊断信息未采集' : row.reuse_diagnosis || '未发现复用提示'}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    动态上下文：{row.runtime_context_size == null ? '未记录' : `${row.runtime_context_size.toLocaleString()} 字符`}
                  </div>
                </td>
                <td className="py-4" style={{ color: palette.muted }}>
                  {row.created_at ? pricingTimeLabel(row.created_at) : '未记录'}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
