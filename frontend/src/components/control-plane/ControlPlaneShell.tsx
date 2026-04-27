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
  RiTimeLine,
} from '@remixicon/react';

import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/ui/ThemeToggle';

const palette = {
  page: 'var(--bg-primary)',
  panel: 'var(--bg-elevated)',
  panelMuted: 'var(--bg-report-muted)',
  sidebar: 'var(--bg-secondary)',
  border: 'var(--border-subtle)',
  borderStrong: 'var(--border-default)',
  text: 'var(--text-primary)',
  muted: 'var(--text-secondary)',
  subtle: 'var(--text-tertiary)',
  accent: 'var(--brand-primary)',
  accentText: 'var(--brand-text)',
  accentSoft: 'var(--brand-bg)',
  accentContrast: 'var(--brand-contrast)',
  successSoft: 'var(--status-success-bg)',
  warning: 'var(--status-warning)',
  warningSoft: 'var(--status-warning-bg)',
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
            className="rounded-xl border px-4 py-4"
            style={{
              borderColor: palette.borderStrong,
              background: palette.panel,
            }}
          >
            <div className="flex items-center gap-3">
              <div
                className="flex h-10 w-10 items-center justify-center rounded-xl"
                style={{ background: palette.accentSoft, color: palette.accentText }}
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
                      'group flex items-center gap-3 rounded-xl px-3 py-3 text-sm transition-all'
                    )}
                    style={{
                      background: isActive ? palette.accentSoft : 'transparent',
                      color: isActive ? palette.accentText : palette.muted,
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
              href="/dashboard"
              className="flex items-center gap-3 rounded-xl border px-3 py-3 text-sm"
              style={{
                borderColor: palette.border,
                background: palette.panel,
                color: palette.muted,
              }}
            >
              <RiDashboardLine className="h-4 w-4" />
              回到平台 Dashboard
            </Link>
            {asideMeta ? (
              <div
                className="rounded-xl border px-3 py-3 text-xs leading-6"
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
              background: palette.page,
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
              <div className="flex items-center gap-3">
                <ThemeToggle />
                {actions}
              </div>
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
      className="rounded-xl border px-5 py-5 lg:px-6 lg:py-6"
      style={{
        borderColor: palette.border,
        background: palette.panel,
        boxShadow: 'var(--shadow-sm)',
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
      className="rounded-xl border px-5 py-5"
      style={{
        borderColor: palette.border,
        background: palette.panel,
        boxShadow: 'var(--shadow-sm)',
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
