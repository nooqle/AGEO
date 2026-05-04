'use client';

import Link from 'next/link';
import type { ReactNode } from 'react';
import {
  RiMailSendLine,
  RiArrowRightUpLine,
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
    blue: { bg: 'var(--brand-bg)', fg: 'var(--brand-text)' },
    green: { bg: 'var(--status-success-bg)', fg: 'var(--status-success)' },
    amber: { bg: 'var(--status-warning-bg)', fg: 'var(--status-warning)' },
    slate: { bg: 'var(--bg-report-muted)', fg: 'var(--text-secondary)' },
  };
  const paletteTone = tones[tone];
  return (
    <div
      className="rounded-xl border px-4 py-4"
      style={{
        borderColor: 'var(--border-subtle)',
        background: paletteTone.bg,
      }}
    >
      <div
        className="text-xs font-semibold uppercase tracking-[0.16em]"
        style={{ color: paletteTone.fg }}
      >
        {label}
      </div>
      <div className="mt-2 text-xl font-semibold" style={{ color: palette.text }}>
        {value}
      </div>
    </div>
  );
}

export function ReviewQueuePanel({
  applications,
  organizations,
  reviewSelections,
  issuingApplicationId,
  onSelectionChange,
  onIssueInvite,
  compact = false,
  actionSlot,
}: {
  applications: RegistrationApplication[];
  organizations: OrganizationRecord[];
  reviewSelections: Record<string, string>;
  issuingApplicationId: string | null;
  onSelectionChange: (applicationId: string, organizationId: string) => void;
  onIssueInvite: (applicationId: string) => void;
  compact?: boolean;
  actionSlot?: ReactNode;
}) {
  return (
    <ControlPlanePanel
      id="reviews"
      title="邀请码队列"
      actions={
        actionSlot ?? (
          <div
            className="inline-flex items-center gap-2 rounded-full px-3 py-1.5 text-xs font-semibold"
            style={{ background: palette.warningSoft, color: palette.warning }}
          >
            <RiMailSendLine className="h-4 w-4" />
            待发放 {applications.length} 个
          </div>
        )
      }
    >
      {applications.length === 0 ? (
        <div
          className="rounded-xl border border-dashed px-4 py-6 text-sm"
          style={{ borderColor: palette.borderStrong, color: palette.muted }}
        >
          当前没有待发放的邀请码申请。
        </div>
      ) : (
        <div className="space-y-3">
          {(compact ? applications.slice(0, 3) : applications).map((application) => (
            <div
              key={application.id}
              className="rounded-xl border px-4 py-4"
              style={{
                borderColor: palette.border,
                background: palette.panelMuted,
              }}
            >
              <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_260px_auto] xl:items-center">
                <div>
                  <div className="flex items-center gap-2">
                    <div className="text-sm font-semibold">{application.organization_name}</div>
                    <span
                      className="rounded-full px-2 py-1 text-[11px] font-semibold"
                      style={{
                        background: palette.accentSoft,
                        color: palette.accentText,
                      }}
                    >
                      {application.email || application.phone || '--'}
                    </span>
                  </div>
                  <div className="mt-2 text-sm leading-6" style={{ color: palette.muted }}>
                    申请人：{application.applicant_name || '--'}
                    <br />
                    公司规模：{application.company_size || '--'}
                    <br />
                    类型：{application.is_agency ? '代理机构' : '品牌方 / 企业'}
                    <br />
                    提交时间：{formatRelativeTime(application.created_at)}
                    {application.invite_code_sent_at ? (
                      <>
                        <br />
                        最近发放：{formatRelativeTime(application.invite_code_sent_at)}
                      </>
                    ) : null}
                  </div>
                </div>

                <label className="block">
                  <div
                    className="mb-2 text-xs font-semibold uppercase tracking-[0.16em]"
                    style={{ color: palette.subtle }}
                  >
                    归属组织
                  </div>
                  <select
                    value={reviewSelections[application.id] || ''}
                    onChange={(event) =>
                      onSelectionChange(application.id, event.target.value)
                    }
                    className="h-11 w-full rounded-lg border px-3 text-sm outline-none"
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
                    variant="primary"
                    size="md"
                    onClick={() => onIssueInvite(application.id)}
                    isLoading={issuingApplicationId === application.id}
                    leftIcon={<RiMailSendLine className="h-4 w-4" />}
                  >
                    {application.invite_code_sent_at ? '重新发放邀请码' : '发放邀请码'}
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
                查看全部邀请码申请
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
            className="flex h-11 items-center gap-2 rounded-lg border px-3"
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
        <table className="min-w-[920px] text-left text-sm">
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
                      className="inline-flex min-h-10 items-center gap-1 rounded-lg px-3 py-2 text-sm font-semibold"
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
