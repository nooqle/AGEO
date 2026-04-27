'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { RiArrowLeftLine, RiRefreshLine } from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import {
  ControlPlaneShell,
  ControlPlaneStatCard,
  controlPlanePalette,
} from '@/components/control-plane/ControlPlaneShell';
import {
  CustomerTablePanel,
  formatControlPlaneCost,
} from '@/components/control-plane/ControlPlaneDataPanels';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AuthUser } from '@/types/auth';
import type { ControlPlaneCustomerSummary } from '@/types/controlPlane';

const palette = controlPlanePalette();

export default function ControlPlaneCustomersPage() {
  return (
    <RequireAuth>
      <ControlPlaneCustomersContent />
    </RequireAuth>
  );
}

function ControlPlaneCustomersContent() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [customers, setCustomers] = useState<ControlPlaneCustomerSummary[]>([]);
  const [days, setDays] = useState(7);
  const [customerQuery, setCustomerQuery] = useState('');
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
        return;
      }
      const summaries = await api.getControlPlaneCustomers(days);
      setCustomers(summaries);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载客户组织失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadData();
    // loadData intentionally reads latest state and is invoked manually elsewhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [days]);

  const filteredCustomers = useMemo(() => {
    const query = customerQuery.trim().toLowerCase();
    if (!query) return customers;
    return customers.filter((customer) => {
      return (
        customer.customer_name.toLowerCase().includes(query) ||
        (customer.primary_account || '').toLowerCase().includes(query)
      );
    });
  }, [customerQuery, customers]);

  const summary = useMemo(() => {
    return customers.reduce(
      (acc, customer) => {
        acc.tokens += customer.tokens_7d;
        acc.cost += customer.cost_7d;
        acc.activeTasks += customer.active_task_count;
        return acc;
      },
      { tokens: 0, cost: 0, activeTasks: 0 }
    );
  }, [customers]);

  return (
    <ControlPlaneShell
      title="客户组织"
      description="按组织查看账号、品牌和近 7 天使用。"
      breadcrumbs={[
        { label: '设置', href: '/settings' },
        { label: '运营工作台', href: '/control-plane' },
        { label: '客户组织' },
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
          <div
            className="inline-flex rounded-2xl border p-1"
            style={{ borderColor: palette.border, background: palette.panel }}
          >
            {[7, 30].map((option) => (
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
            刷新列表
          </Button>
        </div>
      }
    >
      {currentUser?.role !== 'internal_admin' && !loading ? (
        <div className="rounded-2xl border px-4 py-6 text-sm" style={{ borderColor: palette.border, color: palette.muted, background: palette.panel }}>
          当前账号没有内部运营权限，无法访问客户组织列表。
        </div>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-3">
            <ControlPlaneStatCard
              label="客户数量"
              value={customers.length.toString()}
              hint={`最近 ${days} 天`}
            />
            <ControlPlaneStatCard
              label="窗口内费用"
              value={formatControlPlaneCost(summary.cost)}
              hint={`运行中任务 ${summary.activeTasks} 个`}
            />
            <ControlPlaneStatCard
              label="窗口内 Token"
              value={summary.tokens.toLocaleString()}
              hint={`${filteredCustomers.length} 个结果`}
            />
          </div>

          <CustomerTablePanel
            customers={filteredCustomers}
            loading={loading}
            query={customerQuery}
            onQueryChange={setCustomerQuery}
          />
        </div>
      )}
    </ControlPlaneShell>
  );
}
