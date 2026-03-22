'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { RiArrowLeftLine, RiShieldUserLine } from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AuthUser } from '@/types/auth';
import type { ControlPlaneCustomerSummary } from '@/types/controlPlane';
import { formatRelativeTime } from '@/lib/utils';

function formatCost(value: number) {
  return `¥${value.toFixed(4)}`;
}

export default function ControlPlanePage() {
  return (
    <RequireAuth>
      <ControlPlaneContent />
    </RequireAuth>
  );
}

function ControlPlaneContent() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [customers, setCustomers] = useState<ControlPlaneCustomerSummary[]>([]);
  const [days, setDays] = useState(7);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    async function load() {
      setLoading(true);
      try {
        const user = await api.getMe();
        if (!active) return;
        setCurrentUser(user);
        if (user.role !== 'internal_admin') {
          setCustomers([]);
          return;
        }
        const summaries = await api.getControlPlaneCustomers(days);
        if (!active) return;
        setCustomers(summaries);
      } catch (error) {
        if (!active) return;
        toast.error(error instanceof Error ? error.message : '加载运营控制台失败');
      } finally {
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [days]);

  const summary = useMemo(() => {
    return customers.reduce(
      (acc, item) => {
        acc.customers += 1;
        acc.tokens += item.tokens_7d;
        acc.cost += item.cost_7d;
        acc.activeTasks += item.active_task_count;
        return acc;
      },
      { customers: 0, tokens: 0, cost: 0, activeTasks: 0 }
    );
  }, [customers]);

  const isAdmin = currentUser?.role === 'internal_admin';

  return (
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <DashboardTopBar />
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 pb-10 pt-6 md:px-6 xl:px-8">
        <div className="flex flex-col gap-4 rounded-[28px] border px-5 py-5 md:flex-row md:items-center md:justify-between" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
          <div className="space-y-2">
            <Link href="/settings" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <RiArrowLeftLine className="h-4 w-4" />
              返回设置
            </Link>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--text-tertiary)' }}>
              P5 / Internal Control Plane
            </div>
            <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              客户运营控制台
            </h1>
            <p className="max-w-3xl text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              顶层对象先按组织视角管理。你可以查看组织最近 7 天的 token、费用和活跃任务，再进入客户详情处理账号、品牌与任务。
            </p>
          </div>
          <div className="flex items-center gap-3">
            <ThemeToggle />
            <div className="inline-flex rounded-full border p-1" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-tertiary)' }}>
              {[7, 30].map((option) => (
                <button
                  key={option}
                  type="button"
                  onClick={() => setDays(option)}
                  className="rounded-full px-3 py-1.5 text-xs font-medium"
                  style={{
                    background: days === option ? 'var(--brand-primary)' : 'transparent',
                    color: days === option ? '#fff' : 'var(--text-secondary)',
                  }}
                >
                  最近 {option} 天
                </button>
              ))}
            </div>
          </div>
        </div>

        {!isAdmin ? (
          <div className="rounded-[28px] border px-6 py-8" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
            <div className="flex items-center gap-3 text-lg font-medium" style={{ color: 'var(--text-primary)' }}>
              <RiShieldUserLine className="h-5 w-5" />
              仅内部管理员可见
            </div>
            <p className="mt-3 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              当前账号没有内部运营权限，无法访问客户运营控制台。
            </p>
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-4">
              <SummaryCard title="组织数" value={summary.customers.toString()} />
              <SummaryCard title={`最近 ${days} 天 Token`} value={summary.tokens.toLocaleString()} />
              <SummaryCard title={`最近 ${days} 天费用`} value={formatCost(summary.cost)} />
              <SummaryCard title="运行中任务" value={summary.activeTasks.toString()} />
            </div>

            <section className="rounded-[28px] border px-5 py-5 md:px-6 md:py-6" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    客户列表
                  </div>
                  <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                    这里的客户暂时映射为组织。账号登录、品牌采集与任务运行先围绕组织展开。
                  </div>
                </div>
              </div>

              <div className="mt-5 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr style={{ color: 'var(--text-tertiary)' }}>
                      <th className="pb-3 pr-4 font-medium">客户名称</th>
                      <th className="pb-3 pr-4 font-medium">账号</th>
                      <th className="pb-3 pr-4 font-medium">成员</th>
                      <th className="pb-3 pr-4 font-medium">品牌</th>
                      <th className="pb-3 pr-4 font-medium">Token</th>
                      <th className="pb-3 pr-4 font-medium">费用</th>
                      <th className="pb-3 pr-4 font-medium">运行中任务</th>
                      <th className="pb-3 pr-4 font-medium">最近活跃</th>
                      <th className="pb-3 font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center" style={{ color: 'var(--text-secondary)' }}>
                          正在加载客户列表...
                        </td>
                      </tr>
                    ) : customers.length === 0 ? (
                      <tr>
                        <td colSpan={9} className="py-8 text-center" style={{ color: 'var(--text-secondary)' }}>
                          当前还没有组织客户数据。
                        </td>
                      </tr>
                    ) : (
                      customers.map((customer) => (
                        <tr key={customer.organization_id} className="border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                          <td className="py-4 pr-4 font-medium" style={{ color: 'var(--text-primary)' }}>
                            <Link href={`/control-plane/${customer.organization_id}`} className="hover:underline">
                              {customer.customer_name}
                            </Link>
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.primary_account || '--'}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.member_count}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.brand_count}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.tokens_7d.toLocaleString()}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {formatCost(customer.cost_7d)}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.active_task_count}
                          </td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>
                            {customer.last_active_at ? formatRelativeTime(customer.last_active_at) : '--'}
                          </td>
                          <td className="py-4">
                            <Link
                              href={`/control-plane/${customer.organization_id}`}
                              className="inline-flex h-9 items-center rounded-full border px-3 text-sm font-medium"
                              style={{
                                borderColor: 'var(--border-subtle)',
                                background: 'var(--bg-elevated)',
                                color: 'var(--text-primary)',
                              }}
                            >
                              查看详情
                            </Link>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}

function SummaryCard({ title, value }: { title: string; value: string }) {
  return (
    <div className="rounded-[24px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
      <div className="text-xs uppercase tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>
        {title}
      </div>
      <div className="mt-3 text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}
