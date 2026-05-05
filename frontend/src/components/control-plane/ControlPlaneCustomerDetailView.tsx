'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
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

type DetailTab = 'overview' | 'accounts' | 'brands' | 'tasks';

type EditableUserState = {
  email: string;
  phone: string;
  job_title: string;
  status: string;
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
  const [orgNameDraft, setOrgNameDraft] = useState('');
  const [orgStatusDraft, setOrgStatusDraft] = useState('active');
  const [userDrafts, setUserDrafts] = useState<Record<string, EditableUserState>>({});

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
        setDetail(payload);
        setOrgNameDraft(payload.organization.legal_name);
        setOrgStatusDraft(payload.organization.status);
        const drafts: Record<string, EditableUserState> = {};
        payload.users.forEach((item) => {
          drafts[item.id] = {
            email: item.email || '',
            phone: item.phone || '',
            job_title: item.job_title || '',
            status: item.status,
          };
        });
        setUserDrafts(drafts);
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
  }, [customerId]);

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
        },
      }));
      toast.success('账号信息已更新');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新账号信息失败');
    } finally {
      setSavingUserId(null);
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
            >
              <div className="space-y-4">
                {detailUsers.map((user) => {
                  const draft = userDrafts[user.id] || {
                    email: '',
                    phone: '',
                    job_title: '',
                    status: 'active',
                  };
                  return (
                    <div
                      key={user.id}
                      className="rounded-xl border px-4 py-4"
                      style={{ borderColor: palette.border, background: palette.panelMuted }}
                    >
                      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_220px_180px_auto]">
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

          {activeTab === 'tasks' ? (
            <ControlPlanePanel
              title="最近任务"
            >
              <TaskTable rows={detailRecentTasks} />
            </ControlPlanePanel>
          ) : null}
        </div>
      )}
    </ControlPlaneShell>
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
