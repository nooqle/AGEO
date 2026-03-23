'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  RiAlarmWarningLine,
  RiArrowRightUpLine,
  RiCheckDoubleLine,
  RiSearch2Line,
} from '@remixicon/react';

import { Button } from '@/components/ui/button';
import { controlPlanePalette, ControlPlanePanel } from '@/components/control-plane/ControlPlaneShell';
import type { OrganizationRecord } from '@/types/accountAdmin';
import type { RegistrationApplication } from '@/types/auth';
import type { ControlPlaneCustomerSummary } from '@/types/controlPlane';
import { formatRelativeTime } from '@/lib/utils';

const palette = controlPlanePalette();

export function formatControlPlaneCost(value: number) {
  return `¥${value.toFixed(2)}`;
}

export function SummaryPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone: 'blue' | 'green' | 'amber' | 'slate';
}) {
  const tones = {
    blue: { bg: '#eef4ff', fg: '#0052d9' },
    green: { bg: '#edfdf5', fg: '#047857' },
    amber: { bg: '#fff7ed', fg: '#b45309' },
    slate: { bg: '#f3f5f8', fg: '#516074' },
  };
  const paletteTone = tones[tone];
  return (
    <div
      className="rounded-2xl border px-4 py-4"
      style={{
        borderColor: 'rgba(15,23,42,0.08)',
        background: paletteTone.bg,
      }}
    >
      <div
        className="text-xs font-semibold uppercase tracking-[0.16em]"
        style={{ color: paletteTone.fg }}
      >
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold" style={{ color: '#15243a' }}>
        {value}
      </div>
    </div>
  );
}

export function ReviewQueuePanel({
  applications,
  organizations,
  reviewSelections,
  reviewingApplicationId,
  onSelectionChange,
  onReview,
  compact = false,
  actionSlot,
}: {
  applications: RegistrationApplication[];
  organizations: OrganizationRecord[];
  reviewSelections: Record<string, string>;
  reviewingApplicationId: string | null;
  onSelectionChange: (applicationId: string, organizationId: string) => void;
  onReview: (applicationId: string, action: 'approve' | 'reject') => void;
  compact?: boolean;
  actionSlot?: ReactNode;
}) {
  return (
    <ControlPlanePanel
      id="reviews"
      title="待处理事项"
      actions={
        actionSlot ?? (
          <div
            className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
            style={{ background: '#fff4e8', color: '#b45309' }}
          >
            <RiAlarmWarningLine className="h-4 w-4" />
            {applications.length} 个待处理
          </div>
        )
      }
    >
      {applications.length === 0 ? (
        <div
          className="rounded-2xl border border-dashed px-4 py-6 text-sm"
          style={{ borderColor: palette.borderStrong, color: palette.muted }}
        >
          当前没有待审核注册申请。
        </div>
      ) : (
        <div className="space-y-3">
          {(compact ? applications.slice(0, 3) : applications).map((application) => (
            <div
              key={application.id}
              className="rounded-2xl border px-4 py-4"
              style={{
                borderColor: palette.border,
                background: '#fafcff',
              }}
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px_auto] xl:items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold">{application.organization_name}</div>
                    <span
                      className="rounded-full px-2 py-1 text-[11px] font-semibold"
                      style={{
                        background: '#eef4ff',
                        color: palette.accent,
                      }}
                    >
                      {application.email || application.phone || '--'}
                    </span>
                  </div>
                  <div className="mt-2 text-sm leading-6" style={{ color: palette.muted }}>
                    申请人：{application.applicant_name || '--'}
                    <br />
                    职位：{application.job_title}
                    <br />
                    提交时间：{formatRelativeTime(application.created_at)}
                  </div>
                </div>

                <label className="block">
                  <div
                    className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                    style={{ color: palette.subtle }}
                  >
                    审核归属
                  </div>
                  <select
                    value={reviewSelections[application.id] || ''}
                    onChange={(event) =>
                      onSelectionChange(application.id, event.target.value)
                    }
                    className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                    style={{
                      background: palette.panel,
                      borderColor: palette.borderStrong,
                      color: palette.text,
                    }}
                  >
                    <option value="">创建新组织</option>
                    {organizations.map((organization) => (
                      <option key={organization.id} value={organization.id}>
                        {organization.legal_name}
                      </option>
                    ))}
                  </select>
                </label>

                <div className="flex flex-wrap gap-2 xl:justify-end">
                  <Button
                    variant="ghost"
                    size="md"
                    onClick={() => onReview(application.id, 'reject')}
                    isLoading={reviewingApplicationId === application.id}
                  >
                    拒绝
                  </Button>
                  <Button
                    variant="primary"
                    size="md"
                    onClick={() => onReview(application.id, 'approve')}
                    isLoading={reviewingApplicationId === application.id}
                    leftIcon={<RiCheckDoubleLine className="h-4 w-4" />}
                  >
                    审核通过
                  </Button>
                </div>
              </div>
            </div>
          ))}
          {compact && applications.length > 3 ? (
            <div className="pt-1">
              <Link
                href="/control-plane/reviews"
                className="inline-flex items-center gap-1 text-sm font-semibold"
                style={{ color: palette.accent }}
              >
                查看全部审核申请
                <RiArrowRightUpLine className="h-4 w-4" />
              </Link>
            </div>
          ) : null}
        </div>
      )}
    </ControlPlanePanel>
  );
}

export function CustomerTablePanel({
  customers,
  loading,
  query,
  onQueryChange,
  compact = false,
  actionSlot,
}: {
  customers: ControlPlaneCustomerSummary[];
  loading: boolean;
  query: string;
  onQueryChange: (value: string) => void;
  compact?: boolean;
  actionSlot?: ReactNode;
}) {
  const visibleCustomers = compact ? customers.slice(0, 8) : customers;

  return (
    <ControlPlanePanel
      id="customers"
      title="客户组织"
      actions={
        actionSlot ?? (
          <div
            className="flex h-11 items-center gap-2 rounded-2xl border px-3"
            style={{ borderColor: palette.borderStrong, background: palette.panel }}
          >
            <RiSearch2Line className="h-4 w-4" style={{ color: palette.subtle }} />
            <input
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="搜索客户名称或主账号"
              className="w-56 bg-transparent text-sm outline-none"
              style={{ color: palette.text }}
            />
          </div>
        )
      }
    >
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-sm">
          <thead>
            <tr style={{ color: palette.subtle }}>
              <th className="pb-3 pr-4 font-semibold">客户名称</th>
              <th className="pb-3 pr-4 font-semibold">主账号</th>
              <th className="pb-3 pr-4 font-semibold">成员</th>
              <th className="pb-3 pr-4 font-semibold">品牌资产</th>
              <th className="pb-3 pr-4 font-semibold">近 7 天 Token</th>
              <th className="pb-3 pr-4 font-semibold">近 7 天费用</th>
              <th className="pb-3 pr-4 font-semibold">运行中任务</th>
              <th className="pb-3 pr-4 font-semibold">最近活跃</th>
              <th className="pb-3 font-semibold">操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                  正在加载客户列表...
                </td>
              </tr>
            ) : visibleCustomers.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center" style={{ color: palette.muted }}>
                  没有匹配的客户组织。
                </td>
              </tr>
            ) : (
              visibleCustomers.map((customer) => (
                <tr
                  key={customer.organization_id}
                  className="border-t"
                  style={{ borderColor: palette.border }}
                >
                  <td className="py-4 pr-4">
                    <div className="font-semibold" style={{ color: palette.text }}>
                      {customer.customer_name}
                    </div>
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {customer.primary_account || '--'}
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {customer.member_count}
                  </td>
                  <td className="py-4 pr-4">
                    <div style={{ color: palette.text }}>{customer.brand_count}</div>
                    <div className="text-xs" style={{ color: palette.subtle }}>
                      共享 {customer.organization_brand_count} / 个人{' '}
                      {customer.personal_brand_count}
                    </div>
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {customer.tokens_7d.toLocaleString()}
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {formatControlPlaneCost(customer.cost_7d)}
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {customer.active_task_count}
                  </td>
                  <td className="py-4 pr-4" style={{ color: palette.muted }}>
                    {customer.last_active_at ? formatRelativeTime(customer.last_active_at) : '--'}
                  </td>
                  <td className="py-4">
                    <Link
                      href={`/control-plane/customers/${customer.organization_id}`}
                      className="inline-flex items-center gap-1 rounded-full px-3 py-2 text-sm font-semibold"
                      style={{
                        background: palette.accentSoft,
                        color: palette.accent,
                      }}
                    >
                      查看详情
                      <RiArrowRightUpLine className="h-4 w-4" />
                    </Link>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {compact && customers.length > 8 ? (
        <div className="mt-5">
          <Link
            href="/control-plane/customers"
            className="inline-flex items-center gap-1 text-sm font-semibold"
            style={{ color: palette.accent }}
          >
            查看完整客户列表
            <RiArrowRightUpLine className="h-4 w-4" />
          </Link>
        </div>
      ) : null}
    </ControlPlanePanel>
  );
}
