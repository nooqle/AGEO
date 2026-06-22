'use client';

import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import Link from 'next/link';
import {
  RiArrowLeftLine,
  RiBuildingLine,
  RiFolderChartLine,
  RiPulseLine,
  RiUserSettingsLine,
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
import { modalScrimClassName } from '@/components/ui/modal-scrim';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AdminUserUpdateInput } from '@/types/accountAdmin';
import type { AuthUser } from '@/types/auth';
import type {
  ControlPlaneCustomerDetail,
  ControlPlaneEntitySummary,
  ControlPlaneTaskSummary,
} from '@/types/controlPlane';
import { formatDateTime, formatRelativeTime } from '@/lib/utils';

const palette = controlPlanePalette();

function formatCost(value: number, currency = 'CNY') {
  return formatControlPlaneCost(value, currency);
}

type DetailTab = 'overview' | 'accounts' | 'brands' | 'access' | 'tasks';

type EditableUserState = {
  email: string;
  phone: string;
  job_title: string;
  status: string;
  amwaychina_console: boolean;
};

type InviteAccountDraft = {
  email: string;
  applicant_name: string;
  job_title: string;
  amwaychina_console: boolean;
};

export function ControlPlaneCustomerDetailView({
  customerId,
}: {
  customerId: string;
}) {
  return (
    <RequireAuth>
      <ControlPlaneCustomerDetailContent customerId={customerId} />
    </RequireAuth>
  );
}

function ControlPlaneCustomerDetailContent({ customerId }: { customerId: string }) {
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [detail, setDetail] = useState<ControlPlaneCustomerDetail | null>(null);
  const [activeTab, setActiveTab] = useState<DetailTab>('overview');
  const [loading, setLoading] = useState(true);
  const [savingOrg, setSavingOrg] = useState(false);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [sendingInvite, setSendingInvite] = useState(false);
  const [orgNameDraft, setOrgNameDraft] = useState('');
  const [orgStatusDraft, setOrgStatusDraft] = useState('active');
  const [amwayChinaEnabledDraft, setAmwayChinaEnabledDraft] = useState(false);
  const [userDrafts, setUserDrafts] = useState<Record<string, EditableUserState>>({});
  const [inviteDraft, setInviteDraft] = useState<InviteAccountDraft>({
    email: '',
    applicant_name: '',
    job_title: '团队成员',
    amwaychina_console: true,
  });

  const hydrateDetail = useCallback((payload: ControlPlaneCustomerDetail) => {
    setDetail(payload);
    setOrgNameDraft(payload.organization.legal_name);
    setOrgStatusDraft(payload.organization.status);
    setAmwayChinaEnabledDraft(Boolean(payload.organization.feature_flags?.amwaychina_console));
    const drafts: Record<string, EditableUserState> = {};
    payload.users.forEach((item) => {
      drafts[item.id] = {
        email: item.email || '',
        phone: item.phone || '',
        job_title: item.job_title || '',
        status: item.status,
        amwaychina_console: Boolean(item.feature_flags?.amwaychina_console),
      };
    });
    setUserDrafts(drafts);
  }, []);

  useEffect(() => {
    let active = true;
    async function loadDetail() {
      setLoading(true);
      try {
        const user = await api.getMe();
        if (!active) return;
        setCurrentUser(user);
        if (user.role !== 'internal_admin') {
          setDetail(null);
          return;
        }
        const payload = await api.getControlPlaneCustomerDetail(customerId);
        if (!active) return;
        hydrateDetail(payload);
      } catch (error) {
        if (!active) return;
        toast.error(error instanceof Error ? error.message : '加载客户详情失败');
      } finally {
        if (active) setLoading(false);
      }
    }
    void loadDetail();
    return () => {
      active = false;
    };
  }, [customerId, hydrateDetail]);

  const isAdmin = currentUser?.role === 'internal_admin';
  const detailUsers = useMemo(
    () => (Array.isArray(detail?.users) ? detail.users : []),
    [detail]
  );
  const detailEntities = useMemo(
    () => (Array.isArray(detail?.entities) ? detail.entities : []),
    [detail]
  );
  const detailRecentTasks = useMemo(
    () => (Array.isArray(detail?.recent_tasks) ? detail.recent_tasks : []),
    [detail]
  );
  const organization = detail?.organization ?? {
    id: customerId,
    legal_name: '客户详情',
    status: 'active',
    feature_flags: {},
    primary_account: null,
    member_count: 0,
    entity_count: 0,
    created_at: '',
    updated_at: '',
  };
  const summary = detail?.summary ?? {
    organization_id: customerId,
    customer_name: '客户详情',
    primary_account: null,
    member_count: 0,
    brand_count: 0,
    organization_brand_count: 0,
    personal_brand_count: 0,
    tokens_7d: 0,
    cost_7d: 0,
    active_task_count: 0,
    last_active_at: null,
  };

  const memberSummary = useMemo(() => {
    if (!detailUsers.length) {
      return { active: 0, inactive: 0 };
    }
    return detailUsers.reduce(
      (acc, user) => {
        if (user.status === 'active') acc.active += 1;
        else acc.inactive += 1;
        return acc;
      },
      { active: 0, inactive: 0 }
    );
  }, [detailUsers]);

  const sharedEntities = useMemo(
    () =>
      detailEntities.filter((entity) => entity.visibility_scope === 'organization'),
    [detailEntities]
  );

  const personalEntities = useMemo(
    () =>
      detailEntities.filter((entity) => entity.visibility_scope === 'personal'),
    [detailEntities]
  );

  const recentTasksPreview = detailRecentTasks.slice(0, 5);

  async function handleSaveOrganization() {
    if (!detail) return;
    setSavingOrg(true);
    try {
      const updated = await api.updateOrganization(organization.id, {
        legal_name: orgNameDraft.trim(),
        status: orgStatusDraft,
        feature_flags: {
          ...(organization.feature_flags || {}),
          amwaychina_console: amwayChinaEnabledDraft,
        },
      });
      setDetail((current) =>
        current
          ? {
              ...current,
              organization: updated,
              summary: { ...current.summary, customer_name: updated.legal_name },
            }
          : current
      );
      setAmwayChinaEnabledDraft(Boolean(updated.feature_flags?.amwaychina_console));
      toast.success('组织信息已更新');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新组织信息失败');
    } finally {
      setSavingOrg(false);
    }
  }

  async function handleSaveUser(userId: string) {
    const draft = userDrafts[userId];
    if (!draft) return;
    setSavingUserId(userId);
    try {
      const payload: AdminUserUpdateInput = {
        email: draft.email.trim() || null,
        phone: draft.phone.trim() || null,
        job_title: draft.job_title.trim() || null,
        status: draft.status,
        is_active: draft.status === 'active',
        feature_flags: {
          ...(detailUsers.find((item) => item.id === userId)?.feature_flags || {}),
          amwaychina_console: draft.amwaychina_console,
        },
      };
      const updated = await api.updateAdminUser(userId, payload);
      setDetail((current) =>
        current
          ? {
              ...current,
              users: current.users.map((item) => (item.id === userId ? updated : item)),
            }
          : current
      );
      setUserDrafts((current) => ({
        ...current,
        [userId]: {
          email: updated.email || '',
          phone: updated.phone || '',
          job_title: updated.job_title || '',
          status: updated.status,
          amwaychina_console: Boolean(updated.feature_flags?.amwaychina_console),
        },
      }));
      toast.success('账号信息已更新');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新账号信息失败');
    } finally {
      setSavingUserId(null);
    }
  }

  async function handleCreateInvitation() {
    if (!detail) return;
    const email = inviteDraft.email.trim();
    if (!email) {
      toast.error('请输入邀请邮箱');
      return;
    }
    setSendingInvite(true);
    try {
      const response = await api.createAccountInvitation({
        email,
        organization_id: organization.id,
        applicant_name: inviteDraft.applicant_name.trim() || null,
        job_title: inviteDraft.job_title.trim() || '团队成员',
        feature_flags: {
          amwaychina_console: inviteDraft.amwaychina_console,
        },
      });
      const refreshed = await api.getControlPlaneCustomerDetail(customerId);
      hydrateDetail(refreshed);
      setInviteOpen(false);
      setInviteDraft({
        email: '',
        applicant_name: '',
        job_title: '团队成员',
        amwaychina_console: true,
      });
      toast.success(
        response.status === 'existing_user_granted'
          ? '账号权限已开通'
          : '邀请已发送'
      );
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '邀请发送失败');
    } finally {
      setSendingInvite(false);
    }
  }

  return (
    <ControlPlaneShell
      title={organization.legal_name || '客户详情'}
      description="组织概览、账号、品牌和任务。"
      breadcrumbs={[
        { label: '设置', href: '/settings' },
        { label: '运营工作台', href: '/control-plane' },
        { label: '客户组织', href: '/control-plane/customers' },
        { label: organization.legal_name || '客户详情' },
      ]}
      actions={
        <Link
          href="/control-plane/customers"
          className="inline-flex min-h-10 items-center gap-2 rounded-lg border px-3 py-2 text-sm font-semibold"
          style={{
            borderColor: palette.borderStrong,
            background: palette.panel,
            color: palette.muted,
          }}
        >
          <RiArrowLeftLine className="h-4 w-4" />
          返回客户列表
        </Link>
      }
    >
      {!isAdmin ? (
        <ControlPlanePanel
          title="需要内部管理员权限"
          description="当前账号没有内部运营权限，无法访问客户详情。"
        >
          <div className="text-sm leading-6" style={{ color: palette.muted }}>
            请回到平台 Dashboard 切换内部管理员账号，或让已开通的内部管理员代为处理。
          </div>
        </ControlPlanePanel>
      ) : loading || !detail ? (
        <ControlPlanePanel title="正在加载客户详情">
          <div className="text-sm leading-6" style={{ color: palette.muted }}>
            正在拉取组织、账号、品牌和任务数据...
          </div>
        </ControlPlanePanel>
      ) : (
        <div className="space-y-6">
          <div className="grid gap-4 xl:grid-cols-4">
            <ControlPlaneStatCard
              label="近 7 天费用"
              value={formatCost(summary.cost_7d)}
              hint={
                summary.last_active_at
                  ? `最近活跃 ${formatRelativeTime(summary.last_active_at)}`
                  : '暂无活跃记录'
              }
            />
            <ControlPlaneStatCard
              label="近 7 天 Token"
              value={summary.tokens_7d.toLocaleString()}
              hint="覆盖组织成员整体使用"
            />
            <ControlPlaneStatCard
              label="成员"
              value={`${summary.member_count}`}
              hint={`活跃 ${memberSummary?.active || 0} / 其他 ${memberSummary?.inactive || 0}`}
            />
            <ControlPlaneStatCard
              label="品牌资产"
              value={summary.brand_count.toString()}
              hint={`共享 ${summary.organization_brand_count} / 个人 ${summary.personal_brand_count} / 运行中任务 ${summary.active_task_count}`}
            />
          </div>

          <div
            className="inline-flex rounded-xl border p-1"
            style={{ borderColor: palette.border, background: palette.panel }}
          >
            <TabButton
              active={activeTab === 'overview'}
              onClick={() => setActiveTab('overview')}
              icon={<RiPulseLine className="h-4 w-4" />}
              label="总览"
            />
            <TabButton
              active={activeTab === 'accounts'}
              onClick={() => setActiveTab('accounts')}
              icon={<RiUserSettingsLine className="h-4 w-4" />}
              label="账号"
            />
            <TabButton
              active={activeTab === 'brands'}
              onClick={() => setActiveTab('brands')}
              icon={<RiBuildingLine className="h-4 w-4" />}
              label="品牌"
            />
            <TabButton
              active={activeTab === 'access'}
              onClick={() => setActiveTab('access')}
              icon={<RiUserSettingsLine className="h-4 w-4" />}
              label="权限"
            />
            <TabButton
              active={activeTab === 'tasks'}
              onClick={() => setActiveTab('tasks')}
              icon={<RiFolderChartLine className="h-4 w-4" />}
              label="任务"
            />
          </div>

          {activeTab === 'overview' ? (
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_380px]">
              <ControlPlanePanel
                title="最近任务"
              >
                <TaskTable rows={recentTasksPreview} compact />
              </ControlPlanePanel>

              <ControlPlanePanel
                title="组织信息"
                actions={
                  <Button
                    variant="primary"
                    size="md"
                    onClick={() => void handleSaveOrganization()}
                    isLoading={savingOrg}
                  >
                    保存组织信息
                  </Button>
                }
              >
                <div className="space-y-4">
                  <label className="block">
                    <div
                      className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                      style={{ color: palette.subtle }}
                    >
                      组织名称
                    </div>
                    <input
                      value={orgNameDraft}
                      onChange={(event) => setOrgNameDraft(event.target.value)}
                      className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                      style={{
                        background: palette.panel,
                        borderColor: palette.borderStrong,
                        color: palette.text,
                      }}
                    />
                  </label>
                  <label className="block">
                    <div
                      className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                      style={{ color: palette.subtle }}
                    >
                      组织状态
                    </div>
                    <select
                      value={orgStatusDraft}
                      onChange={(event) => setOrgStatusDraft(event.target.value)}
                      className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                      style={{
                        background: palette.panel,
                        borderColor: palette.borderStrong,
                        color: palette.text,
                      }}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                    </select>
                  </label>
                  <div className="text-sm leading-7" style={{ color: palette.muted }}>
                    主账号：{organization.primary_account || '--'}
                    <br />
                    创建时间：{organization.created_at ? formatDateTime(organization.created_at) : '--'}
                    <br />
                    最近活跃：
                    {summary.last_active_at
                      ? formatRelativeTime(summary.last_active_at)
                      : '--'}
                  </div>
                </div>
              </ControlPlanePanel>
            </div>
          ) : null}

          {activeTab === 'accounts' ? (
            <ControlPlanePanel
              title="组织账号"
              actions={
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => setInviteOpen(true)}
                >
                  邀请账号
                </Button>
              }
            >
              <div className="space-y-4">
                {detailUsers.map((user) => {
                  const draft = userDrafts[user.id] || {
                    email: '',
                    phone: '',
                    job_title: '',
                    status: 'active',
                    amwaychina_console: false,
                  };
                  return (
                    <div
                      key={user.id}
                      className="rounded-xl border px-4 py-4"
                      style={{ borderColor: palette.border, background: palette.panelMuted }}
                    >
                      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_220px_180px_190px_auto]">
                        <input
                          value={draft.email}
                          onChange={(event) =>
                            setUserDrafts((current) => ({
                              ...current,
                              [user.id]: { ...draft, email: event.target.value },
                            }))
                          }
                          placeholder="邮箱"
                          className="h-11 rounded-lg border px-3 text-sm outline-none"
                          style={{
                            background: palette.panel,
                            borderColor: palette.borderStrong,
                            color: palette.text,
                          }}
                        />
                        <input
                          value={draft.phone}
                          onChange={(event) =>
                            setUserDrafts((current) => ({
                              ...current,
                              [user.id]: { ...draft, phone: event.target.value },
                            }))
                          }
                          placeholder="手机号"
                          className="h-11 rounded-lg border px-3 text-sm outline-none"
                          style={{
                            background: palette.panel,
                            borderColor: palette.borderStrong,
                            color: palette.text,
                          }}
                        />
                        <input
                          value={draft.job_title}
                          onChange={(event) =>
                            setUserDrafts((current) => ({
                              ...current,
                              [user.id]: { ...draft, job_title: event.target.value },
                            }))
                          }
                          placeholder="职位"
                          className="h-11 rounded-lg border px-3 text-sm outline-none"
                          style={{
                            background: palette.panel,
                            borderColor: palette.borderStrong,
                            color: palette.text,
                          }}
                        />
                        <select
                          value={draft.status}
                          onChange={(event) =>
                            setUserDrafts((current) => ({
                              ...current,
                              [user.id]: { ...draft, status: event.target.value },
                            }))
                          }
                          className="h-11 rounded-lg border px-3 text-sm outline-none"
                          style={{
                            background: palette.panel,
                            borderColor: palette.borderStrong,
                            color: palette.text,
                          }}
                        >
                          <option value="active">active</option>
                          <option value="disabled">disabled</option>
                          <option value="rejected">rejected</option>
                          <option value="pending_review">pending_review</option>
                        </select>
                        <Button
                          variant="secondary"
                          size="md"
                          onClick={() =>
                            setUserDrafts((current) => ({
                              ...current,
                              [user.id]: {
                                ...draft,
                                amwaychina_console: !draft.amwaychina_console,
                              },
                            }))
                          }
                        >
                          {draft.amwaychina_console ? 'Console 已开通' : 'Console 未开通'}
                        </Button>
                        <Button
                          variant="primary"
                          size="md"
                          onClick={() => void handleSaveUser(user.id)}
                          isLoading={savingUserId === user.id}
                        >
                          保存
                        </Button>
                      </div>
                      <div className="mt-3 text-sm leading-6" style={{ color: palette.muted }}>
                        角色：{user.role} · 创建时间：{formatDateTime(user.created_at)}
                        {organization.feature_flags?.amwaychina_console ? (
                          <>
                            <br />
                            组织级权限已开通，账号级开关只记录该账号的独立授权状态。
                          </>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </ControlPlanePanel>
          ) : null}

          {activeTab === 'brands' ? (
            <div className="grid gap-6 xl:grid-cols-2">
              <ControlPlanePanel title="组织共享品牌">
                <EntityList entities={sharedEntities} emptyText="当前组织还没有共享品牌。" />
              </ControlPlanePanel>

              <ControlPlanePanel
                title="成员个人品牌"
              >
                <EntityList
                  entities={personalEntities}
                  emptyText="当前组织成员还没有个人空间品牌。"
                />
              </ControlPlanePanel>
            </div>
          ) : null}

          {activeTab === 'access' ? (
            <ControlPlanePanel
              title="专属功能权限"
              actions={
                <Button
                  variant="primary"
                  size="md"
                  onClick={() => void handleSaveOrganization()}
                  isLoading={savingOrg}
                >
                  保存权限
                </Button>
              }
            >
              <div
                className="rounded-xl border px-4 py-4"
                style={{ borderColor: palette.border, background: palette.panelMuted }}
              >
                <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
                  <div>
                    <div className="text-sm font-semibold" style={{ color: palette.text }}>
                      安利中国专属 Console
                    </div>
                    <p className="mt-2 max-w-2xl text-sm leading-6" style={{ color: palette.muted }}>
                      打开后，该组织成员可以访问 /amwaychina。系统会准备组织空间的安利中心品牌，用于上传问题、抓取平台答案、生成圈层图谱和报告。
                    </p>
                    <div className="mt-3 text-xs leading-5" style={{ color: palette.subtle }}>
                      当前状态：{organization.feature_flags?.amwaychina_console ? '已开通' : '未开通'}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setAmwayChinaEnabledDraft((current) => !current)}
                    className="inline-flex min-h-10 items-center justify-center rounded-lg border px-4 text-sm font-semibold transition-colors"
                    style={{
                      borderColor: amwayChinaEnabledDraft ? palette.accent : palette.borderStrong,
                      background: amwayChinaEnabledDraft ? palette.accentSoft : palette.panel,
                      color: amwayChinaEnabledDraft ? palette.accentText : palette.muted,
                    }}
                  >
                    {amwayChinaEnabledDraft ? '已允许访问' : '未允许访问'}
                  </button>
                </div>
              </div>
            </ControlPlanePanel>
          ) : null}

          {activeTab === 'tasks' ? (
            <ControlPlanePanel
              title="最近任务"
            >
              <TaskTable rows={detailRecentTasks} />
            </ControlPlanePanel>
          ) : null}

          <InviteAccountDialog
            open={inviteOpen}
            draft={inviteDraft}
            organizationName={organization.legal_name}
            isSubmitting={sendingInvite}
            onDraftChange={setInviteDraft}
            onClose={() => setInviteOpen(false)}
            onSubmit={() => void handleCreateInvitation()}
          />
        </div>
      )}
    </ControlPlaneShell>
  );
}

function InviteAccountDialog({
  open,
  draft,
  organizationName,
  isSubmitting,
  onDraftChange,
  onClose,
  onSubmit,
}: {
  open: boolean;
  draft: InviteAccountDraft;
  organizationName: string;
  isSubmitting: boolean;
  onDraftChange: (draft: InviteAccountDraft) => void;
  onClose: () => void;
  onSubmit: () => void;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={(next) => !next && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay className={modalScrimClassName('z-50')} />
        <Dialog.Content className="fixed inset-0 z-50 flex items-center justify-center p-4 md:p-6">
          <div
            className="w-full max-w-[560px] rounded-2xl border p-6 shadow-[var(--shadow-lg)]"
            style={{ borderColor: palette.borderStrong, background: palette.panel }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <Dialog.Title className="text-[22px] font-semibold" style={{ color: palette.text }}>
                  邀请账号
                </Dialog.Title>
                <Dialog.Description className="mt-2 text-sm leading-6" style={{ color: palette.muted }}>
                  邀请对象会加入 {organizationName}。如果邮箱已在该组织内启用，系统会直接开通所选权限。
                </Dialog.Description>
              </div>
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg border px-3 py-2 text-sm font-semibold"
                  style={{ borderColor: palette.borderStrong, color: palette.muted }}
                >
                  关闭
                </button>
              </Dialog.Close>
            </div>

            <div className="mt-6 space-y-4">
              <label className="block">
                <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                  邮箱
                </div>
                <input
                  value={draft.email}
                  onChange={(event) =>
                    onDraftChange({ ...draft, email: event.target.value })
                  }
                  placeholder="name@company.com"
                  className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                  style={{
                    background: palette.panelMuted,
                    borderColor: palette.borderStrong,
                    color: palette.text,
                  }}
                />
              </label>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="block">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                    姓名
                  </div>
                  <input
                    value={draft.applicant_name}
                    onChange={(event) =>
                      onDraftChange({ ...draft, applicant_name: event.target.value })
                    }
                    placeholder="可选"
                    className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                    style={{
                      background: palette.panelMuted,
                      borderColor: palette.borderStrong,
                      color: palette.text,
                    }}
                  />
                </label>
                <label className="block">
                  <div className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]" style={{ color: palette.subtle }}>
                    职位
                  </div>
                  <input
                    value={draft.job_title}
                    onChange={(event) =>
                      onDraftChange({ ...draft, job_title: event.target.value })
                    }
                    className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
                    style={{
                      background: palette.panelMuted,
                      borderColor: palette.borderStrong,
                      color: palette.text,
                    }}
                  />
                </label>
              </div>
              <button
                type="button"
                onClick={() =>
                  onDraftChange({
                    ...draft,
                    amwaychina_console: !draft.amwaychina_console,
                  })
                }
                className="flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left text-sm"
                style={{
                  borderColor: draft.amwaychina_console ? palette.accent : palette.borderStrong,
                  background: draft.amwaychina_console ? palette.accentSoft : palette.panelMuted,
                  color: draft.amwaychina_console ? palette.accentText : palette.muted,
                }}
              >
                <span className="font-semibold">同时开通安利中国 Console</span>
                <span>{draft.amwaychina_console ? '已选择' : '未选择'}</span>
              </button>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="secondary" size="md" onClick={onClose}>
                取消
              </Button>
              <Button
                variant="primary"
                size="md"
                onClick={onSubmit}
                isLoading={isSubmitting}
              >
                发送邀请
              </Button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean;
  onClick: () => void;
  icon: ReactNode;
  label: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition-colors"
      style={{
        background: active ? palette.accent : 'transparent',
        color: active ? palette.accentContrast : palette.muted,
      }}
    >
      {icon}
      {label}
    </button>
  );
}

function EntityList({
  entities,
  emptyText,
}: {
  entities: ControlPlaneEntitySummary[];
  emptyText: string;
}) {
  if (entities.length === 0) {
    return (
      <div
        className="rounded-xl border border-dashed px-4 py-6 text-sm"
        style={{ borderColor: palette.borderStrong, color: palette.muted }}
      >
        {emptyText}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {entities.map((entity) => (
        <div
          key={entity.id}
          className="rounded-xl border px-4 py-4"
          style={{ borderColor: palette.border, background: palette.panelMuted }}
        >
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-sm font-semibold">{entity.name}</div>
              <div className="mt-2 text-sm leading-6" style={{ color: palette.muted }}>
                {entity.visibility_scope === 'organization' ? '组织空间' : '个人空间'}
                <br />
                所属账号：{entity.owner_account || '--'}
                <br />
                最近分析：{entity.last_analyzed ? formatDateTime(entity.last_analyzed) : '--'}
              </div>
            </div>
            <span
              className="rounded-full px-2 py-1 text-[11px] font-semibold"
              style={{
                background:
                  entity.visibility_scope === 'organization'
                    ? palette.accentSoft
                    : 'var(--bg-report-muted)',
                color:
                  entity.visibility_scope === 'organization'
                    ? palette.accentText
                    : palette.muted,
              }}
            >
              更新于 {formatRelativeTime(entity.updated_at)}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}

function TaskTable({
  rows,
  compact = false,
}: {
  rows: ControlPlaneTaskSummary[];
  compact?: boolean;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-[980px] text-left text-sm">
        <thead>
          <tr style={{ color: palette.subtle }}>
            <th className="pb-3 pr-4 font-semibold">品牌</th>
            <th className="pb-3 pr-4 font-semibold">空间</th>
            <th className="pb-3 pr-4 font-semibold">执行账号</th>
            <th className="pb-3 pr-4 font-semibold">状态</th>
            <th className="pb-3 pr-4 font-semibold">Token</th>
            <th className="pb-3 pr-4 font-semibold">费用</th>
            {!compact ? <th className="pb-3 pr-4 font-semibold">用时</th> : null}
            <th className="pb-3 font-semibold">更新时间</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td
                colSpan={compact ? 7 : 8}
                className="py-8 text-center"
                style={{ color: palette.muted }}
              >
                当前组织还没有相关任务记录。
              </td>
            </tr>
          ) : (
            rows.map((task) => (
              <tr
                key={task.task_id}
                className="border-t"
                style={{ borderColor: palette.border }}
              >
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
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {task.status}
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {task.llm_total_tokens.toLocaleString()}
                </td>
                <td className="py-4 pr-4" style={{ color: palette.muted }}>
                  {formatCost(task.llm_estimated_cost_cache_aware, task.currency)}
                  <div className="mt-1 text-xs" style={{ color: palette.subtle }}>
                    缓存 {task.llm_cached_prompt_tokens.toLocaleString()} / 计费输入 {task.llm_billable_prompt_tokens.toLocaleString()}
                  </div>
                </td>
                {!compact ? (
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {task.llm_total_latency_ms} ms
                  </td>
                ) : null}
                <td className="py-4" style={{ color: palette.muted }}>
                  {formatDateTime(task.updated_at)}
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
