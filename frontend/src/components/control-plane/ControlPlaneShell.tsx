'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import type { ReactNode } from 'react';
import {
  RiApps2Line,
  RiArrowRightSLine,
  RiBuilding2Line,
  RiCoinsLine,
  RiDashboardLine,
  RiFileList3Line,
  RiSettings4Line,
  RiTimeLine,
} from '@remixicon/react';

import { cn } from '@/lib/utils';

const palette = {
  page: '#f5f7fb',
  panel: '#ffffff',
  sidebar: '#fbfcfe',
  border: 'rgba(15, 23, 42, 0.08)',
  borderStrong: 'rgba(15, 23, 42, 0.12)',
  text: '#15243a',
  muted: '#5f6f86',
  subtle: '#95a1b2',
  accent: '#0052d9',
  accentSoft: '#e9f2ff',
  successSoft: '#edfdf5',
};

type NavItem = {
  label: string;
  href: string;
  icon: ReactNode;
  exact?: boolean;
};

const navItems: NavItem[] = [
  {
    label: '运营工作台',
    href: '/control-plane',
    icon: <RiDashboardLine className="h-4 w-4" />,
    exact: true,
  },
  {
    label: '邀请码中心',
    href: '/control-plane/reviews',
    icon: <RiTimeLine className="h-4 w-4" />,
  },
  {
    label: '客户组织',
    href: '/control-plane/customers',
    icon: <RiBuilding2Line className="h-4 w-4" />,
  },
  {
    label: '任务运营',
    href: '/control-plane/tasks',
    icon: <RiFileList3Line className="h-4 w-4" />,
  },
  {
    label: '成本观测',
    href: '/control-plane/costs',
    icon: <RiCoinsLine className="h-4 w-4" />,
  },
];

export function ControlPlaneShell({
  title,
  description,
  breadcrumbs,
  actions,
  asideMeta,
  children,
}: {
  title: string;
  description?: string;
  breadcrumbs?: Array<{ label: string; href?: string }>;
  actions?: ReactNode;
  asideMeta?: ReactNode;
  children: ReactNode;
}) {
  const pathname = usePathname();

  return (
    <div className="min-h-screen" style={{ background: palette.page, color: palette.text }}>
      <div className="mx-auto grid min-h-screen max-w-[1680px] lg:grid-cols-[248px_minmax(0,1fr)]">
        <aside
          className="border-r px-4 py-5"
          style={{
            borderColor: palette.border,
            background: palette.sidebar,
          }}
        >
          <div
            className="rounded-[22px] border px-4 py-4"
            style={{
              borderColor: palette.borderStrong,
              background:
                'linear-gradient(180deg, rgba(0,82,217,0.08), rgba(0,82,217,0.02))',
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 w-10 items-center justify-center rounded-2xl"
                style={{ background: palette.accent, color: '#fff' }}
              >
                <RiApps2Line className="h-5 w-5" />
              </div>
              <div>
                <div className="text-sm font-semibold">Specta AI</div>
                <div className="text-xs" style={{ color: palette.muted }}>
                  运营后台
                </div>
              </div>
            </div>
          </div>

          <div className="mt-6">
            <div
              className="mb-3 px-2 text-[11px] font-semibold uppercase tracking-[0.22em]"
              style={{ color: palette.subtle }}
            >
              导航
            </div>
            <nav className="space-y-1.5">
              {navItems.map((item) => {
                const isActive = item.exact
                  ? pathname === item.href
                  : pathname === item.href || pathname.startsWith(`${item.href}/`);
                return (
                  <Link
                    key={item.label}
                    href={item.href}
                    className={cn(
                      'group flex items-center gap-3 rounded-2xl px-3 py-3 text-sm transition-all'
                    )}
                    style={{
                      background: isActive ? palette.accentSoft : 'transparent',
                      color: isActive ? palette.accent : palette.muted,
                    }}
                  >
                    <span>{item.icon}</span>
                    <span className="font-medium">{item.label}</span>
                    <RiArrowRightSLine
                      className="ml-auto h-4 w-4 opacity-0 transition-opacity group-hover:opacity-100"
                    />
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="mt-8 space-y-3">
            <Link
              href="/settings"
              className="flex items-center gap-3 rounded-2xl border px-3 py-3 text-sm"
              style={{
                borderColor: palette.border,
                background: palette.panel,
                color: palette.muted,
              }}
            >
              <RiSettings4Line className="h-4 w-4" />
              返回设置
            </Link>
            {asideMeta ? (
              <div
                className="rounded-2xl border px-3 py-3 text-xs leading-6"
                style={{
                  borderColor: palette.border,
                  background: palette.successSoft,
                  color: palette.muted,
                }}
              >
                {asideMeta}
              </div>
            ) : null}
          </div>
        </aside>

        <div className="min-w-0">
          <header
            className="sticky top-0 z-20 border-b px-5 py-4 lg:px-8"
            style={{
              borderColor: palette.border,
              background: 'rgba(245, 247, 251, 0.94)',
              backdropFilter: 'blur(16px)',
            }}
          >
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div className="space-y-2">
                {breadcrumbs?.length ? (
                  <div className="flex flex-wrap items-center gap-2 text-xs" style={{ color: palette.subtle }}>
                    {breadcrumbs.map((crumb, index) => (
                      <div key={`${crumb.label}-${index}`} className="flex items-center gap-2">
                        {crumb.href ? (
                          <Link href={crumb.href} className="hover:underline">
                            {crumb.label}
                          </Link>
                        ) : (
                          <span>{crumb.label}</span>
                        )}
                        {index < breadcrumbs.length - 1 ? <RiArrowRightSLine className="h-3.5 w-3.5" /> : null}
                      </div>
                    ))}
                  </div>
                ) : null}
                <div>
                  <h1 className="text-[28px] font-semibold tracking-tight">{title}</h1>
                  {description ? (
                    <p className="mt-1 max-w-3xl text-sm leading-6" style={{ color: palette.muted }}>
                      {description}
                    </p>
                  ) : null}
                </div>
              </div>
              {actions ? <div className="flex items-center gap-3">{actions}</div> : null}
            </div>
          </header>

          <main className="px-4 py-6 lg:px-8">{children}</main>
        </div>
      </div>
    </div>
  );
}

export function ControlPlanePanel({
  id,
  title,
  description,
  actions,
  children,
}: {
  id?: string;
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="rounded-[24px] border px-5 py-5 lg:px-6 lg:py-6"
      style={{
        borderColor: palette.border,
        background: palette.panel,
        boxShadow: '0 14px 30px rgba(15, 23, 42, 0.04)',
      }}
    >
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-sm font-semibold">{title}</div>
          {description ? (
            <div className="mt-1 text-sm leading-6" style={{ color: palette.muted }}>
              {description}
            </div>
          ) : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
      <div className="mt-5">{children}</div>
    </section>
  );
}

export function ControlPlaneStatCard({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div
      className="rounded-[22px] border px-5 py-5"
      style={{
        borderColor: palette.border,
        background: palette.panel,
        boxShadow: '0 12px 26px rgba(15, 23, 42, 0.03)',
      }}
    >
      <div className="text-xs font-semibold uppercase tracking-[0.18em]" style={{ color: palette.subtle }}>
        {label}
      </div>
      <div className="mt-3 text-[28px] font-semibold leading-none">{value}</div>
      {hint ? (
        <div className="mt-2 text-xs leading-5" style={{ color: palette.muted }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

export function controlPlanePalette() {
  return palette;
}
