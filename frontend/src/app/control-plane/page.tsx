'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  RiArrowRightUpLine,
  RiRefreshLine,
} from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import {
  ControlPlanePanel,
  ControlPlaneShell,
  ControlPlaneStatCard,
  controlPlanePalette,
} from '@/components/control-plane/ControlPlaneShell';
import {
  CustomerTablePanel,
  ReviewQueuePanel,
  formatControlPlaneCost,
} from '@/components/control-plane/ControlPlaneDataPanels';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { OrganizationRecord } from '@/types/accountAdmin';
import type { AuthUser, RegistrationApplication } from '@/types/auth';
import type { ControlPlaneCustomerSummary } from '@/types/controlPlane';

const palette = controlPlanePalette();

export default function ControlPlanePage() {
  return (
    <RequireAuth>
      <ControlPlaneWorkbench />
    </RequireAuth>
  );
}

function ControlPlaneWorkbench() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [customers, setCustomers] = useState<ControlPlaneCustomerSummary[]>([]);
  const [organizations, setOrganizations] = useState<OrganizationRecord[]>([]);
  const [registrationApplications, setRegistrationApplications] = useState<
    RegistrationApplication[]
  >([]);
  const [reviewSelections, setReviewSelections] = useState<Record<string, string>>({});
  const [reviewingApplicationId, setReviewingApplicationId] = useState<string | null>(
    null
  );
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  function buildDefaultReviewSelections(
    apps: RegistrationApplication[],
    orgs: OrganizationRecord[]
  ) {
    const next: Record<string, string> = {};
    apps.forEach((application) => {
      const matchedOrganization = orgs.find(
        (organization) => organization.legal_name === application.organization_name
      );
      if (matchedOrganization) {
        next[application.id] = matchedOrganization.id;
      }
    });
    return next;
  }

  async function loadData(isRefresh = false) {
    if (isRefresh) setRefreshing(true);
    else setLoading(true);
    try {
      const user = await api.getMe();
      setCurrentUser(user);
      if (user.role !== 'internal_admin') {
        setCustomers([]);
        setOrganizations([]);
        setRegistrationApplications([]);
        return;
      }
      const [summaries, orgs, applications] = await Promise.all([
        api.getControlPlaneCustomers(7),
        api.getOrganizations(),
        api.listRegistrationApplications(),
      ]);
      setCustomers(summaries);
      setOrganizations(orgs);
      setRegistrationApplications(applications);
      setReviewSelections(buildDefaultReviewSelections(applications, orgs));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载运营工作台失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  useEffect(() => {
    void loadData();
    // loadData intentionally reads latest state and is invoked manually elsewhere.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleReviewApplication(
    applicationId: string,
    action: 'approve' | 'reject'
  ) {
    setReviewingApplicationId(applicationId);
    try {
      if (action === 'approve') {
        await api.approveRegistrationApplication(
          applicationId,
          reviewSelections[applicationId] || null
        );
        toast.success('账号申请已审核通过');
      } else {
        await api.rejectRegistrationApplication(applicationId);
        toast.success('账号申请已拒绝');
      }
      await loadData(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '审核操作失败');
    } finally {
      setReviewingApplicationId(null);
    }
  }

  const pendingApplications = registrationApplications.filter(
    (item) => item.status === 'pending_review'
  );

  const summary = useMemo(() => {
    return customers.reduce(
      (acc, item) => {
        acc.customers += 1;
        acc.tokens += item.tokens_7d;
        acc.cost += item.cost_7d;
        acc.activeTasks += item.active_task_count;
        acc.organizationBrands += item.organization_brand_count;
        acc.personalBrands += item.personal_brand_count;
        return acc;
      },
      {
        customers: 0,
        tokens: 0,
        cost: 0,
        activeTasks: 0,
        organizationBrands: 0,
        personalBrands: 0,
      }
    );
  }, [customers]);

  const isAdmin = currentUser?.role === 'internal_admin';

  return (
    <ControlPlaneShell
      title="运营工作台"
      description="处理待审核事项，查看客户组织。"
      breadcrumbs={[{ label: '设置', href: '/settings' }, { label: '运营工作台' }]}
      actions={
        <Button
          variant="outline"
          size="md"
          onClick={() => void loadData(true)}
          isLoading={refreshing}
          leftIcon={<RiRefreshLine className="h-4 w-4" />}
        >
          刷新工作台
        </Button>
      }
    >
      {!isAdmin ? (
        <ControlPlanePanel
          title="需要内部管理员权限"
          description="当前账号没有内部运营权限，无法访问控制台。"
        >
          <div className="text-sm leading-6" style={{ color: palette.muted }}>
            请使用内部管理员账号访问，或返回设置页确认当前账号状态。
          </div>
        </ControlPlanePanel>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-3">
            <ControlPlaneStatCard
              label="待处理申请"
              value={pendingApplications.length.toString()}
              hint="待审核"
            />
            <ControlPlaneStatCard
              label="客户组织"
              value={summary.customers.toString()}
              hint="最近 7 天活跃"
            />
            <ControlPlaneStatCard
              label="近 7 天费用"
              value={formatControlPlaneCost(summary.cost)}
              hint={`运行中任务 ${summary.activeTasks} 个 / 品牌 ${summary.organizationBrands + summary.personalBrands}`}
            />
          </div>

          <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_220px]">
            <ReviewQueuePanel
              applications={pendingApplications}
              organizations={organizations}
              reviewSelections={reviewSelections}
              reviewingApplicationId={reviewingApplicationId}
              onSelectionChange={(applicationId, organizationId) =>
                setReviewSelections((current) => ({
                  ...current,
                  [applicationId]: organizationId,
                }))
              }
              onReview={(applicationId, action) =>
                void handleReviewApplication(applicationId, action)
              }
              compact
            />
            <ControlPlanePanel title="模块">
              <div className="space-y-2">
                {[
                  ['审核中心', '/control-plane/reviews'],
                  ['客户组织', '/control-plane/customers'],
                  ['任务运营', '/control-plane/tasks'],
                  ['成本观测', '/control-plane/costs'],
                ].map(([label, href]) => (
                  <Link
                    key={href}
                    href={href}
                    className="block rounded-2xl border px-4 py-3 text-sm font-medium"
                    style={{
                      borderColor: palette.border,
                      background: '#fafcff',
                      color: palette.text,
                    }}
                  >
                    {label}
                  </Link>
                ))}
              </div>
            </ControlPlanePanel>
          </div>

          <CustomerTablePanel
            customers={customers}
            loading={loading}
            query=""
            onQueryChange={() => undefined}
            compact
            actionSlot={
              <Link
                href="/control-plane/customers"
                className="inline-flex items-center gap-1 text-sm font-semibold"
                style={{ color: palette.accent }}
              >
                查看完整客户列表
                <RiArrowRightUpLine className="h-4 w-4" />
              </Link>
            }
          />
        </div>
      )}
    </ControlPlaneShell>
  );
}
