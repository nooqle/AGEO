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
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AuthUser } from '@/types/auth';
import type {
  ControlPlaneCustomerSummary,
  ControlPlaneTaskSummary,
} from '@/types/controlPlane';
import { formatDateTime } from '@/lib/utils';

const palette = controlPlanePalette();

const STATUS_OPTIONS = [
  { label: '全部状态', value: 'all' },
  { label: '运行中', value: 'running' },
  { label: '待执行', value: 'pending' },
  { label: '已完成', value: 'completed' },
  { label: '失败', value: 'failed' },
  { label: '已取消', value: 'cancelled' },
] as const;

function formatCost(value: number) {
  return `¥${value.toFixed(2)}`;
}

export default function ControlPlaneTasksPage() {
  return (
    <RequireAuth>
      <ControlPlaneTasksContent />
    </RequireAuth>
  );
}

function ControlPlaneTasksContent() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [customers, setCustomers] = useState<ControlPlaneCustomerSummary[]>([]);
  const [tasks, setTasks] = useState<ControlPlaneTaskSummary[]>([]);
  const [days, setDays] = useState(7);
  const [statusFilter, setStatusFilter] = useState('all');
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
        setTasks([]);
        return;
      }
      const [summaries, taskRows] = await Promise.all([
        api.getControlPlaneCustomers(days),
        api.getControlPlaneTasks({
          days,
          status: statusFilter === 'all' ? undefined : statusFilter,
          organizationId: organizationFilter === 'all' ? undefined : organizationFilter,
          limit: 120,
        }),
      ]);
      setCustomers(summaries);
      setTasks(taskRows);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载任务运营失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadData();
    // loadData intentionally reads latest state and is invoked manually elsewhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days, statusFilter, organizationFilter]);

  const filteredTasks = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    if (!normalizedQuery) return tasks;
    return tasks.filter((task) =>
      [
        task.customer_name,
        task.brand_name,
        task.initiator_account,
        task.status,
        task.visibility_scope,
      ]
        .filter(Boolean)
        .some((value) => String(value).toLowerCase().includes(normalizedQuery))
    );
  }, [query, tasks]);

  const summary = useMemo(() => {
    return filteredTasks.reduce(
      (acc, task) => {
        acc.tokens += task.llm_total_tokens;
        acc.cost += task.llm_estimated_cost;
        acc.latency += task.llm_total_latency_ms;
        if (task.status === 'running' || task.status === 'pending') acc.active += 1;
        return acc;
      },
      { tokens: 0, cost: 0, latency: 0, active: 0 }
    );
  }, [filteredTasks]);

  return (
    <ControlPlaneShell
      title="任务运营"
      description="按组织、状态和时间窗口查看任务。"
      breadcrumbs={[
        { label: '设置', href: '/settings' },
        { label: '运营工作台', href: '/control-plane' },
        { label: '任务运营' },
      ]}
      actions={
        <div className="flex items-center gap-2">
          <Link
            href="/control-plane"
            className="inline-flex items-center gap-2 rounded-2xl border px-3 py-2 text-sm font-semibold"
            style={{
              borderColor: palette.borderStrong,
              background: palette.panel,
              color: palette.muted,
            }}
          >
            <RiArrowLeftLine className="h-4 w-4" />
            返回工作台
          </Link>
          <Button
            variant="outline"
            size="md"
            onClick={() => void loadData(true)}
            isLoading={refreshing}
            leftIcon={<RiRefreshLine className="h-4 w-4" />}
          >
            刷新任务
          </Button>
        </div>
      }
    >
      {currentUser?.role !== 'internal_admin' && !loading ? (
        <div
          className="rounded-2xl border px-4 py-6 text-sm"
          style={{ borderColor: palette.border, color: palette.muted, background: palette.panel }}
        >
          当前账号没有内部运营权限，无法访问任务运营。
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-3">
            <ControlPlaneStatCard
              label="筛选结果"
              value={filteredTasks.length.toString()}
              hint={`总任务 ${tasks.length}`}
            />
            <ControlPlaneStatCard
              label="运行中任务"
              value={summary.active.toString()}
              hint="含 pending 与 running"
            />
            <ControlPlaneStatCard
              label="窗口内费用"
              value={formatCost(summary.cost)}
              hint={`Token ${summary.tokens.toLocaleString()}`}
            />
          </div>

            <ControlPlanePanel
              title="筛选条件"
            >
            <div className="grid gap-4 xl:grid-cols-[180px_220px_minmax(260px,1fr)_minmax(260px,1fr)]">
              <label className="block">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                  时间窗口
                </div>
                <select
                  value={days}
                  onChange={(event) => setDays(Number(event.target.value))}
                  className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                  style={{ background: palette.panel, borderColor: palette.borderStrong, color: palette.text }}
                >
                  <option value={7}>最近 7 天</option>
                  <option value={30}>最近 30 天</option>
                  <option value={90}>最近 90 天</option>
                </select>
              </label>

              <label className="block">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                  状态
                </div>
                <select
                  value={statusFilter}
                  onChange={(event) => setStatusFilter(event.target.value)}
                  className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                  style={{ background: palette.panel, borderColor: palette.borderStrong, color: palette.text }}
                >
                  {STATUS_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>

              <label className="block">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                  客户组织
                </div>
                <select
                  value={organizationFilter}
                  onChange={(event) => setOrganizationFilter(event.target.value)}
                  className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                  style={{ background: palette.panel, borderColor: palette.borderStrong, color: palette.text }}
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
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                  关键词
                </div>
                <div
                  className="flex h-11 items-center gap-2 rounded-2xl border px-3"
                  style={{
                    background: palette.panel,
                    borderColor: palette.borderStrong,
                    color: palette.text,
                  }}
                >
                  <RiSearch2Line className="h-4 w-4" style={{ color: palette.subtle }} />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="搜索客户、品牌、账号、状态"
                    className="w-full bg-transparent text-sm outline-none"
                    style={{ color: palette.text }}
                  />
                </div>
              </label>
            </div>
          </ControlPlanePanel>

          <ControlPlanePanel
            title="任务列表"
          >
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr style={{ color: palette.subtle }}>
                    <th className="pb-3 pr-4 font-semibold">客户</th>
                    <th className="pb-3 pr-4 font-semibold">品牌</th>
                    <th className="pb-3 pr-4 font-semibold">空间</th>
                    <th className="pb-3 pr-4 font-semibold">执行账号</th>
                    <th className="pb-3 pr-4 font-semibold">状态</th>
                    <th className="pb-3 pr-4 font-semibold">Token</th>
                    <th className="pb-3 pr-4 font-semibold">费用</th>
                    <th className="pb-3 pr-4 font-semibold">用时</th>
                    <th className="pb-3 font-semibold">更新时间</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                        正在加载任务...
                      </td>
                    </tr>
                  ) : filteredTasks.length === 0 ? (
                    <tr>
                      <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                        当前筛选条件下没有任务记录。
                      </td>
                    </tr>
                  ) : (
                    filteredTasks.map((task) => (
                      <tr key={task.task_id} className="border-t" style={{ borderColor: palette.border }}>
                        <td className="py-4 pr-4">
                          {task.organization_id ? (
                            <Link
                              href={`/control-plane/customers/${task.organization_id}`}
                              className="inline-flex items-center gap-1 font-medium"
                              style={{ color: palette.accent }}
                            >
                              {task.customer_name || '--'}
                              <RiArrowRightUpLine className="h-3.5 w-3.5" />
                            </Link>
                          ) : (
                            <span>{task.customer_name || '--'}</span>
                          )}
                        </td>
                        <td className="py-4 pr-4">{task.brand_name}</td>
                        <td className="py-4 pr-4" style={{ color: palette.muted }}>
                          {task.visibility_scope === 'organization'
                            ? '组织空间'
                            : task.visibility_scope === 'personal'
                              ? '个人空间'
                              : '--'}
                        </td>
                        <td className="py-4 pr-4" style={{ color: palette.muted }}>
                          {task.initiator_account || '--'}
                        </td>
                        <td className="py-4 pr-4">
                          <span
                            className="inline-flex rounded-full px-2.5 py-1 text-xs font-semibold"
                            style={statusBadgeStyle(task.status)}
                          >
                            {task.status}
                          </span>
                        </td>
                        <td className="py-4 pr-4" style={{ color: palette.muted }}>
                          {task.llm_total_tokens.toLocaleString()}
                        </td>
                        <td className="py-4 pr-4" style={{ color: palette.muted }}>
                          {formatCost(task.llm_estimated_cost)}
                        </td>
                        <td className="py-4 pr-4" style={{ color: palette.muted }}>
                          {task.llm_total_latency_ms.toLocaleString()} ms
                        </td>
                        <td className="py-4" style={{ color: palette.muted }}>
                          {formatDateTime(task.updated_at)}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </ControlPlanePanel>
        </div>
      )}
    </ControlPlaneShell>
  );
}

function statusBadgeStyle(status: string) {
  if (status === 'completed') {
    return { background: 'var(--status-success-bg)', color: 'var(--status-success)' };
  }
  if (status === 'running' || status === 'pending') {
    return { background: 'var(--status-info-bg)', color: 'var(--status-info)' };
  }
  if (status === 'failed') {
    return { background: 'var(--status-error-bg)', color: 'var(--status-error)' };
  }
  if (status === 'cancelled') {
    return { background: 'var(--bg-report-muted)', color: 'var(--text-secondary)' };
  }
  return { background: 'var(--status-warning-bg)', color: 'var(--status-warning)' };
}
