'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { RiArrowLeftLine, RiRefreshLine } from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import {
  ControlPlaneShell,
  controlPlanePalette,
} from '@/components/control-plane/ControlPlaneShell';
import { ReviewQueuePanel } from '@/components/control-plane/ControlPlaneDataPanels';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { OrganizationRecord } from '@/types/accountAdmin';
import type { AuthUser, RegistrationApplication } from '@/types/auth';

const palette = controlPlanePalette();

export default function ControlPlaneReviewsPage() {
  return (
    <RequireAuth>
      <ControlPlaneReviewsContent />
    </RequireAuth>
  );
}

function ControlPlaneReviewsContent() {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [organizations, setOrganizations] = useState<OrganizationRecord[]>([]);
  const [registrationApplications, setRegistrationApplications] = useState<
    RegistrationApplication[]
  >([]);
  const [reviewSelections, setReviewSelections] = useState<Record<string, string>>({});
  const [issuingApplicationId, setIssuingApplicationId] = useState<string | null>(
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
        setOrganizations([]);
        setRegistrationApplications([]);
        return;
      }
      const [orgs, applications] = await Promise.all([
        api.getOrganizations(),
        api.listRegistrationApplications(),
      ]);
      setOrganizations(orgs);
      setRegistrationApplications(applications);
      setReviewSelections(buildDefaultReviewSelections(applications, orgs));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载邀请码中心失败');
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

  async function handleIssueInvite(applicationId: string) {
    setIssuingApplicationId(applicationId);
    try {
      await api.issueInviteCode(applicationId, reviewSelections[applicationId] || null);
      toast.success('邀请码已发送');
      await loadData(true);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '邀请码发放失败');
    } finally {
      setIssuingApplicationId(null);
    }
  }

  const pendingApplications = registrationApplications.filter(
    (item) => item.status === 'pending_review'
  );

  return (
    <ControlPlaneShell
      title="邀请码中心"
      description="为已登记邮箱发放邀请码，并确认归属组织。"
      breadcrumbs={[
        { label: '设置', href: '/settings' },
        { label: '运营工作台', href: '/control-plane' },
        { label: '邀请码中心' },
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
            刷新邀请码队列
          </Button>
        </div>
      }
    >
      {currentUser?.role !== 'internal_admin' && !loading ? (
        <div className="rounded-2xl border px-4 py-6 text-sm" style={{ borderColor: palette.border, color: palette.muted, background: palette.panel }}>
          当前账号没有内部运营权限，无法访问邀请码中心。
        </div>
      ) : (
        <ReviewQueuePanel
          applications={pendingApplications}
          organizations={organizations}
          reviewSelections={reviewSelections}
          issuingApplicationId={issuingApplicationId}
          onSelectionChange={(applicationId, organizationId) =>
            setReviewSelections((current) => ({
              ...current,
              [applicationId]: organizationId,
            }))
          }
          onIssueInvite={(applicationId) => void handleIssueInvite(applicationId)}
          actionSlot={
            <div
              className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
              style={{ background: palette.warningSoft, color: palette.warning }}
            >
              待发放 {pendingApplications.length} 个
            </div>
          }
        />
      )}
    </ControlPlaneShell>
  );
}
