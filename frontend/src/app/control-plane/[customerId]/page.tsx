'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { RiArrowLeftLine, RiBuildingLine, RiGroupLine, RiPulseLine } from '@remixicon/react';

import { RequireAuth } from '@/components/auth/RequireAuth';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import type { AdminUserUpdateInput } from '@/types/accountAdmin';
import type { AuthUser } from '@/types/auth';
import type { ControlPlaneCustomerDetail } from '@/types/controlPlane';
import { formatDateTime, formatRelativeTime } from '@/lib/utils';

function formatCost(value: number) {
  return `¥${value.toFixed(4)}`;
}

type EditableUserState = {
  email: string;
  phone: string;
  job_title: string;
  status: string;
};

export default function ControlPlaneCustomerDetailPage() {
  return (
    <RequireAuth>
      <ControlPlaneCustomerDetailContent />
    </RequireAuth>
  );
}

function ControlPlaneCustomerDetailContent() {
  const params = useParams<{ customerId: string }>();
  const customerId = params.customerId;
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [detail, setDetail] = useState<ControlPlaneCustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [savingOrg, setSavingOrg] = useState(false);
  const [savingUserId, setSavingUserId] = useState<string | null>(null);
  const [orgNameDraft, setOrgNameDraft] = useState('');
  const [orgStatusDraft, setOrgStatusDraft] = useState('active');
  const [userDrafts, setUserDrafts] = useState<Record<string, EditableUserState>>({});

  async function loadDetail() {
    setLoading(true);
    try {
      const user = await api.getMe();
      setCurrentUser(user);
      if (user.role !== 'internal_admin') {
        setDetail(null);
        return;
      }
      const payload = await api.getControlPlaneCustomerDetail(customerId);
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
      toast.error(error instanceof Error ? error.message : '加载客户详情失败');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadDetail();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [customerId]);

  const isAdmin = currentUser?.role === 'internal_admin';

  const memberSummary = useMemo(() => {
    return detail?.users.reduce(
      (acc, user) => {
        if (user.status === 'active') acc.active += 1;
        else acc.inactive += 1;
        return acc;
      },
      { active: 0, inactive: 0 }
    );
  }, [detail]);

  async function handleSaveOrganization() {
    if (!detail) return;
    setSavingOrg(true);
    try {
      const updated = await api.updateOrganization(detail.organization.id, {
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
    <div className="min-h-screen" style={{ background: 'var(--bg-primary)' }}>
      <DashboardTopBar />
      <main className="mx-auto flex w-full max-w-[1440px] flex-col gap-6 px-4 pb-10 pt-6 md:px-6 xl:px-8">
        <div className="flex flex-col gap-4 rounded-[28px] border px-5 py-5 md:flex-row md:items-center md:justify-between" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
          <div className="space-y-2">
            <Link href="/control-plane" className="inline-flex items-center gap-2 text-sm" style={{ color: 'var(--text-secondary)' }}>
              <RiArrowLeftLine className="h-4 w-4" />
              返回客户列表
            </Link>
            <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--text-tertiary)' }}>
              Customer Detail
            </div>
            <h1 className="text-2xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
              {detail?.organization.legal_name || '客户详情'}
            </h1>
            <p className="max-w-3xl text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              先按组织维度运营客户账号、组织品牌和最近运行任务。组织空间下的品牌可共享，个人空间下的数据仍保留个人隔离。
            </p>
          </div>
          <ThemeToggle />
        </div>

        {!isAdmin ? (
          <div className="rounded-[28px] border px-6 py-8" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
            当前账号没有内部运营权限，无法访问客户详情。
          </div>
        ) : loading || !detail ? (
          <div className="rounded-[28px] border px-6 py-8" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
            正在加载客户详情...
          </div>
        ) : (
          <>
            <div className="grid gap-4 md:grid-cols-4">
              <MetricCard icon={<RiBuildingLine className="h-4 w-4" />} title="最近 7 天费用" value={formatCost(detail.summary.cost_7d)} />
              <MetricCard icon={<RiPulseLine className="h-4 w-4" />} title="最近 7 天 Token" value={detail.summary.tokens_7d.toLocaleString()} />
              <MetricCard icon={<RiGroupLine className="h-4 w-4" />} title="成员" value={`${detail.summary.member_count}（活跃 ${memberSummary?.active || 0}）`} />
              <MetricCard icon={<RiPulseLine className="h-4 w-4" />} title="运行中任务" value={detail.summary.active_task_count.toString()} />
            </div>

            <section className="grid gap-6 xl:grid-cols-[minmax(320px,0.9fr)_minmax(0,1.1fr)]">
              <div className="rounded-[28px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>组织信息</div>
                <div className="mt-4 space-y-4">
                  <label className="block">
                    <div className="mb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>组织名称</div>
                    <input
                      value={orgNameDraft}
                      onChange={(event) => setOrgNameDraft(event.target.value)}
                      className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                      style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                    />
                  </label>
                  <label className="block">
                    <div className="mb-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>组织状态</div>
                    <select
                      value={orgStatusDraft}
                      onChange={(event) => setOrgStatusDraft(event.target.value)}
                      className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                      style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                    >
                      <option value="active">active</option>
                      <option value="disabled">disabled</option>
                    </select>
                  </label>
                  <div className="text-xs leading-6" style={{ color: 'var(--text-secondary)' }}>
                    主账号：{detail.organization.primary_account || '--'}<br />
                    最近活跃：{detail.summary.last_active_at ? formatRelativeTime(detail.summary.last_active_at) : '--'}<br />
                    创建时间：{formatDateTime(detail.organization.created_at)}
                  </div>
                  <Button variant="primary" size="md" onClick={() => void handleSaveOrganization()} isLoading={savingOrg}>
                    保存组织信息
                  </Button>
                </div>
              </div>

              <div className="rounded-[28px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>组织品牌</div>
                <div className="mt-4 space-y-3">
                  {detail.entities.length === 0 ? (
                    <div className="rounded-2xl border border-dashed px-4 py-4 text-sm" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                      当前组织还没有共享品牌。
                    </div>
                  ) : (
                    detail.entities.map((entity) => (
                      <div key={entity.id} className="rounded-2xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-tertiary)' }}>
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{entity.name}</div>
                            <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                              可见范围：{entity.visibility_scope === 'organization' ? '组织空间' : '个人空间'}<br />
                              最近分析：{entity.last_analyzed ? formatDateTime(entity.last_analyzed) : '--'}
                            </div>
                          </div>
                          <span className="rounded-full px-2 py-1 text-[11px]" style={{ border: '1px solid var(--border-subtle)', background: 'var(--bg-elevated)', color: 'var(--text-tertiary)' }}>
                            更新于 {formatRelativeTime(entity.updated_at)}
                          </span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            </section>

            <section className="rounded-[28px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>组织账号</div>
              <div className="mt-4 space-y-4">
                {detail.users.map((user) => {
                  const draft = userDrafts[user.id] || {
                    email: '',
                    phone: '',
                    job_title: '',
                    status: 'active',
                  };
                  return (
                    <div key={user.id} className="rounded-2xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-tertiary)' }}>
                      <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_220px_180px_auto]">
                        <input
                          value={draft.email}
                          onChange={(event) => setUserDrafts((current) => ({ ...current, [user.id]: { ...draft, email: event.target.value } }))}
                          placeholder="邮箱"
                          className="h-11 rounded-2xl border px-3 text-sm outline-none"
                          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                        />
                        <input
                          value={draft.phone}
                          onChange={(event) => setUserDrafts((current) => ({ ...current, [user.id]: { ...draft, phone: event.target.value } }))}
                          placeholder="手机号"
                          className="h-11 rounded-2xl border px-3 text-sm outline-none"
                          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                        />
                        <input
                          value={draft.job_title}
                          onChange={(event) => setUserDrafts((current) => ({ ...current, [user.id]: { ...draft, job_title: event.target.value } }))}
                          placeholder="职位"
                          className="h-11 rounded-2xl border px-3 text-sm outline-none"
                          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                        />
                        <select
                          value={draft.status}
                          onChange={(event) => setUserDrafts((current) => ({ ...current, [user.id]: { ...draft, status: event.target.value } }))}
                          className="h-11 rounded-2xl border px-3 text-sm outline-none"
                          style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                        >
                          <option value="active">active</option>
                          <option value="disabled">disabled</option>
                          <option value="rejected">rejected</option>
                          <option value="pending_review">pending_review</option>
                        </select>
                        <Button
                          variant="secondary"
                          size="md"
                          onClick={() => void handleSaveUser(user.id)}
                          isLoading={savingUserId === user.id}
                        >
                          保存
                        </Button>
                      </div>
                      <div className="mt-3 text-xs leading-6" style={{ color: 'var(--text-secondary)' }}>
                        创建时间：{formatDateTime(user.created_at)}<br />
                        角色：{user.role}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="rounded-[28px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>最近任务</div>
              <div className="mt-4 overflow-x-auto">
                <table className="min-w-full text-left text-sm">
                  <thead>
                    <tr style={{ color: 'var(--text-tertiary)' }}>
                      <th className="pb-3 pr-4 font-medium">品牌</th>
                      <th className="pb-3 pr-4 font-medium">状态</th>
                      <th className="pb-3 pr-4 font-medium">Token</th>
                      <th className="pb-3 pr-4 font-medium">费用</th>
                      <th className="pb-3 pr-4 font-medium">用时</th>
                      <th className="pb-3 font-medium">更新时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {detail.recent_tasks.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="py-6 text-center" style={{ color: 'var(--text-secondary)' }}>
                          当前组织还没有组织空间下的任务记录。
                        </td>
                      </tr>
                    ) : (
                      detail.recent_tasks.map((task) => (
                        <tr key={task.task_id} className="border-t" style={{ borderColor: 'var(--border-subtle)' }}>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-primary)' }}>{task.brand_name}</td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>{task.status}</td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>{task.llm_total_tokens.toLocaleString()}</td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>{formatCost(task.llm_estimated_cost)}</td>
                          <td className="py-4 pr-4" style={{ color: 'var(--text-secondary)' }}>{task.llm_total_latency_ms} ms</td>
                          <td className="py-4" style={{ color: 'var(--text-secondary)' }}>{formatDateTime(task.updated_at)}</td>
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

function MetricCard({ icon, title, value }: { icon: ReactNode; title: string; value: string }) {
  return (
    <div className="rounded-[24px] border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', background: 'var(--bg-secondary)' }}>
      <div className="flex items-center gap-2 text-xs uppercase tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>
        {icon}
        {title}
      </div>
      <div className="mt-3 text-xl font-semibold" style={{ color: 'var(--text-primary)' }}>
        {value}
      </div>
    </div>
  );
}
