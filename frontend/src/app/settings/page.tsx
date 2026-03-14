'use client';

import { startTransition, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  RiArrowLeftLine,
  RiBarChartBoxLine,
  RiCheckLine,
  RiDatabase2Line,
  RiFileTextLine,
  RiNotification3Line,
  RiSettings4Line,
  RiTeamLine,
} from '@remixicon/react';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { toast } from '@/components/ui/toast';
import { api } from '@/services/api';
import { useAlertStore } from '@/stores/alertStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useMonitoringStore } from '@/stores/monitoringStore';
import { FREQUENCY_LABELS, type MonitoringSchedule, type ScheduleFrequency } from '@/types/monitoring';
import { PLATFORM_DISPLAY_NAMES, getPlatformDisplayName } from '@/lib/platformLabel';
import { cn, formatDateTime, formatRelativeTime } from '@/lib/utils';

const SETTINGS_STORAGE_KEY = 'specta-settings-v1';
const PLATFORM_OPTIONS = Object.entries(PLATFORM_DISPLAY_NAMES);
const SECTIONS = [
  { id: 'monitoring', label: '监测与通知', hint: '真实后端能力' },
  { id: 'exports', label: '数据与导出', hint: '导出预设' },
  { id: 'collection', label: '采集偏好', hint: 'AEO 运行偏好' },
  { id: 'account', label: '账户与工作区', hint: '主题与默认品牌' },
  { id: 'legal', label: '法务与数据说明', hint: '合规入口' },
] as const;

type ExportFormat = 'pdf' | 'excel';
type ExportScope = 'overview' | 'full' | 'trend';
type CollectionMode = 'fast' | 'full';

interface LocalSettings {
  exportFormat: ExportFormat;
  exportScope: ExportScope;
  filenameTemplate: string;
  collectionMode: CollectionMode;
  preferredPlatforms: string[];
  browserFirst: boolean;
  defaultEntityId: string | null;
}

interface MonitoringFormState {
  frequency: ScheduleFrequency;
  preferredHour: number;
  timezone: string;
  platforms: string[];
  alertOnSignificantChange: boolean;
  alertThresholdBwvs: number;
}

const DEFAULT_LOCAL_SETTINGS: LocalSettings = {
  exportFormat: 'pdf',
  exportScope: 'full',
  filenameTemplate: '{brand}-{date}-aeo-report',
  collectionMode: 'full',
  preferredPlatforms: ['doubao', 'kimi', 'deepseek'],
  browserFirst: true,
  defaultEntityId: null,
};

function getDefaultTimezone() {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Asia/Hong_Kong';
}

function readLocalSettings(): LocalSettings {
  if (typeof window === 'undefined') return DEFAULT_LOCAL_SETTINGS;
  try {
    const raw = window.localStorage.getItem(SETTINGS_STORAGE_KEY);
    if (!raw) return DEFAULT_LOCAL_SETTINGS;
    const parsed = JSON.parse(raw) as Partial<LocalSettings>;
    return {
      ...DEFAULT_LOCAL_SETTINGS,
      ...parsed,
      preferredPlatforms:
        parsed.preferredPlatforms?.filter((platform) => platform in PLATFORM_DISPLAY_NAMES) ||
        DEFAULT_LOCAL_SETTINGS.preferredPlatforms,
    };
  } catch {
    return DEFAULT_LOCAL_SETTINGS;
  }
}

function saveLocalSettings(settings: LocalSettings) {
  if (typeof window !== 'undefined') {
    window.localStorage.setItem(SETTINGS_STORAGE_KEY, JSON.stringify(settings));
  }
}

function createMonitoringForm(
  schedule: MonitoringSchedule | null,
  fallbackPlatforms: string[],
  timezone: string
): MonitoringFormState {
  return {
    frequency: schedule?.frequency || 'weekly',
    preferredHour: schedule?.preferred_hour ?? 9,
    timezone: schedule?.timezone || timezone,
    platforms:
      schedule?.platforms?.length ? schedule.platforms : fallbackPlatforms.length ? fallbackPlatforms : ['doubao', 'kimi'],
    alertOnSignificantChange: schedule?.alert_on_significant_change ?? true,
    alertThresholdBwvs: schedule?.alert_threshold_bwvs ?? 10,
  };
}

function getStatusLabel(status: MonitoringSchedule['status'] | 'inactive') {
  switch (status) {
    case 'active':
      return '运行中';
    case 'paused':
      return '已暂停';
    case 'error':
      return '异常';
    case 'completed':
      return '已完成';
    default:
      return '未启用';
  }
}

function getStatusTone(status: MonitoringSchedule['status'] | 'inactive') {
  if (status === 'active') {
    return { border: 'rgba(34,197,94,0.34)', bg: 'rgba(34,197,94,0.12)', text: 'var(--success)' };
  }
  if (status === 'paused') {
    return { border: 'rgba(245,158,11,0.34)', bg: 'rgba(245,158,11,0.12)', text: 'var(--warning)' };
  }
  if (status === 'error') {
    return { border: 'rgba(239,68,68,0.34)', bg: 'rgba(239,68,68,0.12)', text: 'var(--error)' };
  }
  return { border: 'var(--border-subtle)', bg: 'var(--bg-tertiary)', text: 'var(--text-secondary)' };
}

function SectionCard({
  id,
  eyebrow,
  title,
  description,
  tone,
  actions,
  children,
}: {
  id: string;
  eyebrow: string;
  title: string;
  description: string;
  tone: 'violet' | 'amber' | 'mint';
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        'dashboard-board scroll-mt-24 rounded-[28px] border px-5 py-5 md:px-7 md:py-7',
        tone === 'violet' && 'dashboard-board--violet',
        tone === 'amber' && 'dashboard-board--amber',
        tone === 'mint' && 'dashboard-board--mint'
      )}
    >
      <div className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-end md:justify-between" style={{ borderColor: 'var(--border-subtle)' }}>
        <div className="max-w-2xl">
          <div className="text-[11px] font-semibold uppercase tracking-[0.22em]" style={{ color: 'var(--text-tertiary)' }}>
            {eyebrow}
          </div>
          <h2 className="mt-2 text-xl font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
            {title}
          </h2>
          <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
            {description}
          </p>
        </div>
        {actions}
      </div>
      <div className="mt-6 space-y-6">{children}</div>
    </section>
  );
}

function FieldLabel({ label, hint }: { label: string; hint?: string }) {
  return (
    <div className="mb-2">
      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
        {label}
      </div>
      {hint ? (
        <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
          {hint}
        </div>
      ) : null}
    </div>
  );
}

function ToggleRow({
  label,
  description,
  checked,
  onChange,
  disabled = false,
  badge,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  badge?: string;
}) {
  return (
    <button
      type="button"
      onClick={disabled ? undefined : onChange}
      className="flex w-full items-start justify-between gap-4 rounded-2xl border px-4 py-4 text-left"
      style={{
        borderColor: checked ? 'color-mix(in srgb, var(--brand-primary) 42%, var(--border-subtle) 58%)' : 'var(--border-subtle)',
        backgroundColor: checked ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-tertiary) 90%)' : 'var(--bg-tertiary)',
        opacity: disabled ? 0.55 : 1,
      }}
    >
      <div>
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {label}
          </span>
          {badge ? (
            <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-tertiary)' }}>
              {badge}
            </span>
          ) : null}
        </div>
        <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
          {description}
        </div>
      </div>
      <span className="relative mt-0.5 inline-flex h-6 w-11 flex-shrink-0 items-center rounded-full p-0.5" style={{ backgroundColor: checked ? 'var(--brand-primary)' : 'var(--bg-elevated)', border: checked ? '1px solid transparent' : '1px solid var(--border-subtle)' }}>
        <span className="h-5 w-5 rounded-full transition-transform" style={{ transform: checked ? 'translateX(20px)' : 'translateX(0)', backgroundColor: '#fff' }} />
      </span>
    </button>
  );
}

function PillOption({
  active,
  label,
  description,
  onClick,
}: {
  active: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-2xl border px-4 py-4 text-left transition-transform hover:-translate-y-0.5"
      style={{
        borderColor: active ? 'color-mix(in srgb, var(--brand-primary) 44%, var(--border-subtle) 56%)' : 'var(--border-subtle)',
        background: active
          ? 'linear-gradient(180deg, color-mix(in srgb, var(--brand-primary) 16%, var(--bg-elevated) 84%), color-mix(in srgb, var(--brand-primary) 8%, var(--bg-tertiary) 92%))'
          : 'var(--bg-tertiary)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
        {active ? <RiCheckLine className="h-4 w-4" style={{ color: 'var(--brand-primary)' }} /> : null}
      </div>
      <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
        {description}
      </div>
    </button>
  );
}

export default function SettingsPage() {
  const timezone = getDefaultTimezone();
  const { entities, isLoading: isEntityLoading, fetchEntities } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const { schedule, alerts, isScheduleLoading, fetchSchedule, fetchAlerts } = useMonitoringStore();
  const { unreadCount, fetchUnreadCount } = useAlertStore();

  const [localSettings, setLocalSettings] = useState<LocalSettings>(DEFAULT_LOCAL_SETTINGS);
  const [selectedEntityId, setSelectedEntityId] = useState<string | null>(null);
  const [workspaceEntityId, setWorkspaceEntityId] = useState<string | null>(null);
  const [monitoringForm, setMonitoringForm] = useState<MonitoringFormState>(
    createMonitoringForm(null, DEFAULT_LOCAL_SETTINGS.preferredPlatforms, timezone)
  );
  const [schedulerRunning, setSchedulerRunning] = useState<boolean | null>(null);
  const [isSavingMonitoring, setIsSavingMonitoring] = useState(false);
  const [isSavingExport, setIsSavingExport] = useState(false);
  const [isSavingCollection, setIsSavingCollection] = useState(false);
  const [isSavingWorkspace, setIsSavingWorkspace] = useState(false);

  const selectedEntity = useMemo(
    () => entities.find((entity) => entity.id === selectedEntityId) || null,
    [entities, selectedEntityId]
  );

  useEffect(() => {
    const settings = readLocalSettings();
    setLocalSettings(settings);

    void Promise.allSettled([
      fetchEntities(),
      fetchUnreadCount(),
      api
        .getSchedulerHealth()
        .then((health) => setSchedulerRunning(health.running))
        .catch(() => setSchedulerRunning(null)),
    ]);
  }, [fetchEntities, fetchUnreadCount]);

  useEffect(() => {
    if (!entities.length) return;

    const fallbackId =
      (localSettings.defaultEntityId &&
      entities.some((entity) => entity.id === localSettings.defaultEntityId)
        ? localSettings.defaultEntityId
        : null) ||
      (selectedBrandId && entities.some((entity) => entity.id === selectedBrandId)
        ? selectedBrandId
        : null) ||
      entities[0].id;

    startTransition(() => {
      setSelectedEntityId((current) =>
        current && entities.some((entity) => entity.id === current) ? current : fallbackId
      );
      setWorkspaceEntityId((current) =>
        current && entities.some((entity) => entity.id === current) ? current : fallbackId
      );
    });
  }, [entities, localSettings.defaultEntityId, selectedBrandId]);

  useEffect(() => {
    if (!selectedEntityId) return;
    void Promise.allSettled([fetchSchedule(selectedEntityId), fetchAlerts(selectedEntityId, 4)]);
  }, [selectedEntityId, fetchAlerts, fetchSchedule]);

  useEffect(() => {
    setMonitoringForm(createMonitoringForm(schedule, localSettings.preferredPlatforms, timezone));
  }, [localSettings.preferredPlatforms, schedule, timezone]);

  const monitoringStatusTone = getStatusTone(schedule?.status || 'inactive');

  async function handleSaveMonitoring() {
    if (!selectedEntity) {
      toast.error('请先选择一个品牌');
      return;
    }

    setIsSavingMonitoring(true);
    try {
      const payload = {
        frequency: monitoringForm.frequency,
        preferred_hour: monitoringForm.preferredHour,
        timezone: monitoringForm.timezone,
        platforms: monitoringForm.platforms,
        alert_on_significant_change: monitoringForm.alertOnSignificantChange,
        alert_threshold_bwvs: monitoringForm.alertThresholdBwvs,
      };

      if (schedule?.id) {
        await api.updateSchedule(schedule.id, payload);
      } else {
        await api.createSchedule({ entity_id: selectedEntity.id, ...payload });
      }

      await Promise.allSettled([
        fetchSchedule(selectedEntity.id),
        fetchAlerts(selectedEntity.id, 4),
        fetchUnreadCount(),
      ]);
      toast.success(schedule?.id ? '监测设置已更新' : '已为该品牌启用自动监测');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存监测设置失败');
    } finally {
      setIsSavingMonitoring(false);
    }
  }

  function persistLocalSettings(nextSettings: LocalSettings, successMessage: string) {
    setLocalSettings(nextSettings);
    saveLocalSettings(nextSettings);
    toast.success(successMessage);
  }

  async function handleSaveExportPreferences() {
    setIsSavingExport(true);
    try {
      persistLocalSettings(localSettings, '导出偏好已保存');
    } finally {
      setIsSavingExport(false);
    }
  }

  async function handleSaveCollectionPreferences() {
    setIsSavingCollection(true);
    try {
      const nextSettings = {
        ...localSettings,
        preferredPlatforms:
          localSettings.preferredPlatforms.length > 0 ? localSettings.preferredPlatforms : ['doubao', 'kimi'],
      };
      persistLocalSettings(nextSettings, '采集偏好已保存');
      if (!schedule) {
        setMonitoringForm((current) => ({ ...current, platforms: nextSettings.preferredPlatforms }));
      }
    } finally {
      setIsSavingCollection(false);
    }
  }

  async function handleSaveWorkspace() {
    if (!workspaceEntityId) {
      toast.error('请选择默认品牌');
      return;
    }

    setIsSavingWorkspace(true);
    try {
      const nextSettings = { ...localSettings, defaultEntityId: workspaceEntityId };
      setSelectedBrandId(workspaceEntityId);
      setSelectedEntityId(workspaceEntityId);
      persistLocalSettings(nextSettings, '默认品牌已更新');
    } finally {
      setIsSavingWorkspace(false);
    }
  }

  const summaryCards = [
    {
      icon: RiTeamLine,
      label: '当前管理品牌',
      value: selectedEntity?.name || (isEntityLoading ? '加载中...' : '尚未创建品牌'),
      meta: `${entities.length} 个品牌实体`,
    },
    {
      icon: RiSettings4Line,
      label: '自动监测状态',
      value: getStatusLabel(schedule?.status || 'inactive'),
      meta: schedule?.next_run_at ? `下一次执行 ${formatDateTime(schedule.next_run_at)}` : '尚未设置监测计划',
    },
    {
      icon: RiNotification3Line,
      label: '通知中心',
      value: unreadCount > 0 ? `${unreadCount} 条未读` : '已清空',
      meta: schedulerRunning === null ? '调度状态待确认' : schedulerRunning ? '调度器运行中' : '调度器暂未运行',
    },
    {
      icon: RiBarChartBoxLine,
      label: '默认采集方式',
      value: localSettings.collectionMode === 'full' ? '完整采集' : '快速采集',
      meta: localSettings.browserFirst ? '优先浏览器采集' : '优先接口采集',
    },
  ];

  return (
    <div className="dashboard-page-bg min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
      <DashboardTopBar />
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-8 px-4 py-6 md:px-6 lg:px-8">
        <div className="dashboard-shell rounded-[32px] p-4 md:p-6 lg:p-8">
          <div className="dashboard-inner-panel rounded-[28px] border px-5 py-6 md:px-7 md:py-8">
            <div className="flex flex-col gap-6 border-b pb-8" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                <div className="max-w-3xl">
                  <Link href="/dashboard" className="inline-flex items-center gap-1.5 text-sm transition-colors" style={{ color: 'var(--text-tertiary)' }}>
                    <RiArrowLeftLine className="h-4 w-4" />
                    返回控制台
                  </Link>
                  <h1 className="mt-4 text-3xl font-semibold tracking-tight md:text-4xl" style={{ color: 'var(--text-primary)' }}>
                    设置中心
                  </h1>
                  <p className="mt-3 max-w-2xl text-sm leading-7 md:text-base" style={{ color: 'var(--text-secondary)' }}>
                    把自动监测、告警通知、导出规则和 AEO 采集偏好集中管理。优先展示已经落地的系统能力，未接后端的能力只作为本地预设。
                  </p>
                </div>

                <div className="rounded-3xl border px-4 py-4 md:px-5" style={{ borderColor: 'color-mix(in srgb, var(--brand-primary) 28%, var(--border-subtle) 72%)', background: 'linear-gradient(135deg, color-mix(in srgb, var(--brand-primary) 14%, var(--bg-tertiary) 86%), color-mix(in srgb, #d3a46a 10%, var(--bg-secondary) 90%))' }}>
                  <div className="text-xs font-medium uppercase tracking-[0.2em]" style={{ color: 'var(--text-tertiary)' }}>
                    当前焦点
                  </div>
                  <div className="mt-2 text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                    {selectedEntity?.name || '选择品牌后开始配置'}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2">
                    <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: monitoringStatusTone.bg, border: `1px solid ${monitoringStatusTone.border}`, color: monitoringStatusTone.text }}>
                      {getStatusLabel(schedule?.status || 'inactive')}
                    </span>
                    <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                      默认时区 {monitoringForm.timezone}
                    </span>
                  </div>
                </div>
              </div>

              <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                {summaryCards.map((card) => (
                  <div key={card.label} className="rounded-3xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', background: 'linear-gradient(180deg, color-mix(in srgb, var(--bg-elevated) 80%, transparent), var(--bg-tertiary))' }}>
                    <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>
                      <card.icon className="h-4 w-4" />
                      {card.label}
                    </div>
                    <div className="mt-3 text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {card.value}
                    </div>
                    <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                      {card.meta}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="mt-8 grid gap-8 lg:grid-cols-[220px_minmax(0,1fr)]">
              <aside className="lg:sticky lg:top-24 lg:self-start">
                <nav className="rounded-[24px] border p-3" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'color-mix(in srgb, var(--bg-secondary) 88%, transparent)' }}>
                  {SECTIONS.map((item) => (
                    <a key={item.id} href={`#${item.id}`} className="block rounded-2xl px-3 py-3 transition-colors" style={{ color: 'var(--text-secondary)' }}>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        {item.label}
                      </div>
                      <div className="mt-1 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                        {item.hint}
                      </div>
                    </a>
                  ))}
                </nav>
              </aside>

              <div className="space-y-6">
                <SectionCard
                  id="monitoring"
                  tone="violet"
                  eyebrow="P0 / Monitoring"
                  title="监测与通知"
                  description="这部分直接复用现有监测计划与告警能力。品牌、频率、平台、阈值都会写入后端；通知通道只展示已接通的站内能力。"
                  actions={<Button variant="primary" size="md" onClick={handleSaveMonitoring} isLoading={isSavingMonitoring}>{schedule ? '保存监测设置' : '启用自动监测'}</Button>}
                >
                  {entities.length === 0 && !isEntityLoading ? (
                    <div className="rounded-3xl border border-dashed px-5 py-8 text-center" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="text-base font-medium" style={{ color: 'var(--text-primary)' }}>还没有可配置的品牌</div>
                      <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>先在控制台创建品牌实体，再为它设置自动监测和告警策略。</div>
                      <div className="mt-4">
                        <Link
                          href="/dashboard"
                          className="inline-flex h-10 items-center justify-center rounded-lg border px-4 text-sm font-medium transition-colors"
                          style={{
                            borderColor: 'var(--border-subtle)',
                            backgroundColor: 'var(--bg-elevated)',
                            color: 'var(--text-primary)',
                          }}
                        >
                          返回控制台创建品牌
                        </Link>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
                        <div>
                          <FieldLabel label="配置对象" hint="设置页当前按品牌维度管理监测计划。" />
                          <select value={selectedEntityId || ''} onChange={(event) => setSelectedEntityId(event.target.value)} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                            {entities.map((entity) => (
                              <option key={entity.id} value={entity.id}>{entity.name}</option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <FieldLabel label="执行时区" hint="默认取当前浏览器时区，可按品牌单独覆盖。" />
                          <input value={monitoringForm.timezone} onChange={(event) => setMonitoringForm((current) => ({ ...current, timezone: event.target.value }))} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }} />
                        </div>
                        <div>
                          <FieldLabel label="执行时间" hint="按整点调度，保存后写入监测计划。" />
                          <select value={monitoringForm.preferredHour} onChange={(event) => setMonitoringForm((current) => ({ ...current, preferredHour: Number(event.target.value) }))} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                            {Array.from({ length: 24 }).map((_, hour) => (
                              <option key={hour} value={hour}>{String(hour).padStart(2, '0')}:00</option>
                            ))}
                          </select>
                        </div>
                        <div className="rounded-2xl border px-4 py-4" style={{ borderColor: monitoringStatusTone.border, backgroundColor: monitoringStatusTone.bg }}>
                          <div className="text-xs uppercase tracking-[0.16em]" style={{ color: 'var(--text-tertiary)' }}>当前状态</div>
                          <div className="mt-2 text-lg font-semibold" style={{ color: monitoringStatusTone.text }}>{isScheduleLoading ? '读取中...' : getStatusLabel(schedule?.status || 'inactive')}</div>
                          <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                            {schedule?.last_run_at ? `最近执行 ${formatRelativeTime(schedule.last_run_at)}` : '保存后即可开始自动监测'}
                          </div>
                        </div>
                      </div>

                      <div>
                        <FieldLabel label="默认监测频率" hint="使用现有调度能力，变更后会影响后续自动跑批。" />
                        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
                          {(Object.entries(FREQUENCY_LABELS) as Array<[ScheduleFrequency, string]>).map(([value, label]) => (
                            <PillOption
                              key={value}
                              active={monitoringForm.frequency === value}
                              label={label}
                              description={value === 'daily' ? '适合高敏感品牌与舆情监测。' : value === 'weekly' ? '平衡成本与趋势感知。' : value === 'biweekly' ? '适合稳定品牌的阶段复盘。' : '适合低频品牌盘点。'}
                              onClick={() => setMonitoringForm((current) => ({ ...current, frequency: value }))}
                            />
                          ))}
                        </div>
                      </div>

                      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
                        <div>
                          <FieldLabel label="默认监测平台" hint="与监测计划绑定。未启用监测时，会优先继承采集偏好中的平台预设。" />
                          <div className="grid gap-3 sm:grid-cols-2">
                            {PLATFORM_OPTIONS.map(([value, label]) => {
                              const active = monitoringForm.platforms.includes(value);
                              return (
                                <button
                                  key={value}
                                  type="button"
                                  onClick={() => setMonitoringForm((current) => ({ ...current, platforms: active ? current.platforms.filter((platform) => platform !== value) : [...current.platforms, value] }))}
                                  className="rounded-2xl border px-4 py-4 text-left"
                                  style={{ borderColor: active ? 'color-mix(in srgb, var(--brand-primary) 44%, var(--border-subtle) 56%)' : 'var(--border-subtle)', backgroundColor: active ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-tertiary) 90%)' : 'var(--bg-tertiary)' }}
                                >
                                  <div className="flex items-center justify-between gap-3">
                                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</div>
                                    {active ? <RiCheckLine className="h-4 w-4" style={{ color: 'var(--brand-primary)' }} /> : null}
                                  </div>
                                  <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>作为监测计划的默认采集入口。</div>
                                </button>
                              );
                            })}
                          </div>
                        </div>

                        <div className="space-y-4">
                          <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                            <FieldLabel label="告警阈值" hint="当前后端使用 BWVS 变化阈值触发显著变化告警。" />
                            <div className="flex items-end justify-between gap-4">
                              <div>
                                <div className="text-3xl font-semibold" style={{ color: 'var(--text-primary)' }}>{monitoringForm.alertThresholdBwvs.toFixed(0)}%</div>
                                <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>建议 8% 到 15%，过低会增加噪音。</div>
                              </div>
                              <input type="range" min={5} max={30} step={1} value={monitoringForm.alertThresholdBwvs} onChange={(event) => setMonitoringForm((current) => ({ ...current, alertThresholdBwvs: Number(event.target.value) }))} className="w-full max-w-[180px]" />
                            </div>
                          </div>

                          <ToggleRow
                            label="显著变化触发站内告警"
                            description="保存后直接写入监测计划。适用于品牌可见度、提及率等指标发生较大波动时。"
                            checked={monitoringForm.alertOnSignificantChange}
                            onChange={() => setMonitoringForm((current) => ({ ...current, alertOnSignificantChange: !current.alertOnSignificantChange }))}
                          />

                          <ToggleRow
                            label="邮件 / 协作通知"
                            description="当前版本仅支持站内通知中心。邮件、企业微信、飞书、Slack 会在通道接入后开放。"
                            checked={false}
                            onChange={() => undefined}
                            disabled
                            badge="后续能力"
                          />
                        </div>
                      </div>

                      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(300px,0.85fr)]">
                        <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                          <div className="flex items-center justify-between gap-3">
                            <div>
                              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>最近站内告警</div>
                              <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>这里直接读取现有 alerts API，并保持和右上角通知中心一致。</div>
                            </div>
                            <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>未读 {unreadCount}</span>
                          </div>

                          <div className="mt-4 space-y-3">
                            {alerts.length === 0 ? (
                              <div className="rounded-2xl border border-dashed px-4 py-5 text-sm" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>该品牌最近没有新的监测告警。</div>
                            ) : (
                              alerts.map((alert) => (
                                <div key={alert.id} className="rounded-2xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}>
                                  <div className="flex items-start justify-between gap-3">
                                    <div>
                                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{alert.title}</div>
                                      <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>{alert.summary}</div>
                                    </div>
                                    <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ backgroundColor: alert.severity === 'critical' || alert.severity === 'high' ? 'rgba(239,68,68,0.12)' : 'rgba(245,158,11,0.12)', color: alert.severity === 'critical' || alert.severity === 'high' ? 'var(--error)' : 'var(--warning)' }}>
                                      {alert.severity}
                                    </span>
                                  </div>
                                  <div className="mt-3 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>{formatRelativeTime(alert.created_at)}</div>
                                </div>
                              ))
                            )}
                          </div>
                        </div>

                        <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>当前生效范围</div>
                          <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                            <div className="flex justify-between gap-4"><span>监测品牌</span><span style={{ color: 'var(--text-primary)' }}>{selectedEntity?.name || '--'}</span></div>
                            <div className="flex justify-between gap-4"><span>监测平台</span><span style={{ color: 'var(--text-primary)' }}>{monitoringForm.platforms.length ? monitoringForm.platforms.map(getPlatformDisplayName).join(' / ') : '--'}</span></div>
                            <div className="flex justify-between gap-4"><span>下一次调度</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.next_run_at ? formatDateTime(schedule.next_run_at) : '保存后生成'}</span></div>
                            <div className="flex justify-between gap-4"><span>累计运行</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.total_runs ?? 0} 次</span></div>
                            <div className="flex justify-between gap-4"><span>连续失败</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.consecutive_failures ?? 0} 次</span></div>
                          </div>
                        </div>
                      </div>
                    </>
                  )}
                </SectionCard>

                <SectionCard
                  id="exports"
                  tone="amber"
                  eyebrow="P1 / Export"
                  title="数据与导出"
                  description="当前后端已有输出导出接口，但还没有全局导出设置。这里先把格式、范围和命名规则做成稳定预设。"
                  actions={<Button variant="secondary" size="md" onClick={handleSaveExportPreferences} isLoading={isSavingExport}>保存导出偏好</Button>}
                >
                  <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
                    <div className="space-y-6">
                      <div>
                        <FieldLabel label="默认导出格式" hint="当前真实支持 PDF 与 Excel。JSON 先不暴露，避免出现无效选项。" />
                        <div className="grid gap-3 sm:grid-cols-2">
                          <PillOption active={localSettings.exportFormat === 'pdf'} label="PDF" description="适合分享汇报与正式交付。" onClick={() => setLocalSettings((current) => ({ ...current, exportFormat: 'pdf' }))} />
                          <PillOption active={localSettings.exportFormat === 'excel'} label="Excel" description="适合继续分析和做二次整理。" onClick={() => setLocalSettings((current) => ({ ...current, exportFormat: 'excel' }))} />
                        </div>
                      </div>

                      <div>
                        <FieldLabel label="导出内容范围" hint="当前先作为导出预填规则，供后续输出面板复用。" />
                        <div className="grid gap-3 md:grid-cols-3">
                          <PillOption active={localSettings.exportScope === 'overview'} label="首页指标" description="只保留总览 KPI 与核心结论。" onClick={() => setLocalSettings((current) => ({ ...current, exportScope: 'overview' }))} />
                          <PillOption active={localSettings.exportScope === 'full'} label="完整报告" description="导出完整分析结论、证据与建议。" onClick={() => setLocalSettings((current) => ({ ...current, exportScope: 'full' }))} />
                          <PillOption active={localSettings.exportScope === 'trend'} label="监测趋势" description="聚焦连续监测的变化与预警。" onClick={() => setLocalSettings((current) => ({ ...current, exportScope: 'trend' }))} />
                        </div>
                      </div>

                      <div>
                        <FieldLabel label="默认文件命名规则" hint="支持品牌名与日期占位，后续导出时可自动替换。" />
                        <input value={localSettings.filenameTemplate} onChange={(event) => setLocalSettings((current) => ({ ...current, filenameTemplate: event.target.value }))} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }} />
                        <div className="mt-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
                          示例：{localSettings.filenameTemplate.replace('{brand}', selectedEntity?.name || 'brand').replace('{date}', '2026-03-12')}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        <RiDatabase2Line className="h-4 w-4" />
                        当前导出预设
                      </div>
                      <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        <div className="flex justify-between gap-4"><span>默认格式</span><span style={{ color: 'var(--text-primary)' }}>{localSettings.exportFormat.toUpperCase()}</span></div>
                        <div className="flex justify-between gap-4"><span>导出范围</span><span style={{ color: 'var(--text-primary)' }}>{localSettings.exportScope === 'overview' ? '首页指标' : localSettings.exportScope === 'full' ? '完整报告' : '监测趋势'}</span></div>
                        <div className="flex justify-between gap-4"><span>目标品牌</span><span style={{ color: 'var(--text-primary)' }}>{selectedEntity?.name || '--'}</span></div>
                      </div>
                      <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                        自动导出、定时投递和 JSON 导出暂未接后端，这里先沉淀稳定偏好，不再展示“即将推出”空卡片。
                      </div>
                    </div>
                  </div>
                </SectionCard>

                <SectionCard
                  id="collection"
                  tone="mint"
                  eyebrow="P0 / Collection"
                  title="模型与采集偏好"
                  description="这是 AEO 产品特有的运行偏好。当前以本地预设形式保存，用于后续监测创建和导出流程的默认参数。"
                  actions={<Button variant="secondary" size="md" onClick={handleSaveCollectionPreferences} isLoading={isSavingCollection}>保存采集偏好</Button>}
                >
                  <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(300px,0.8fr)]">
                    <div className="space-y-6">
                      <div>
                        <FieldLabel label="默认采集模式" hint="快速采集适合快读复盘；完整采集更适合做正式监测或大盘分析。" />
                        <div className="grid gap-3 md:grid-cols-2">
                          <PillOption active={localSettings.collectionMode === 'fast'} label="快速采集" description="更快返回结果，适合日常检查。" onClick={() => setLocalSettings((current) => ({ ...current, collectionMode: 'fast' }))} />
                          <PillOption active={localSettings.collectionMode === 'full'} label="完整采集" description="覆盖更多平台和上下文，适合正式分析。" onClick={() => setLocalSettings((current) => ({ ...current, collectionMode: 'full' }))} />
                        </div>
                      </div>

                      <div>
                        <FieldLabel label="默认平台选择" hint="用于新建监测计划时的初始值，也作为手动采集的推荐平台。" />
                        <div className="grid gap-3 sm:grid-cols-2">
                          {PLATFORM_OPTIONS.map(([value, label]) => {
                            const active = localSettings.preferredPlatforms.includes(value);
                            return (
                              <button
                                key={value}
                                type="button"
                                onClick={() => setLocalSettings((current) => ({ ...current, preferredPlatforms: active ? current.preferredPlatforms.filter((platform) => platform !== value) : [...current.preferredPlatforms, value] }))}
                                className="rounded-2xl border px-4 py-4 text-left"
                                style={{ borderColor: active ? 'color-mix(in srgb, var(--brand-primary) 44%, var(--border-subtle) 56%)' : 'var(--border-subtle)', backgroundColor: active ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-tertiary) 90%)' : 'var(--bg-tertiary)' }}
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>{label}</div>
                                  {active ? <RiCheckLine className="h-4 w-4" style={{ color: 'var(--brand-primary)' }} /> : null}
                                </div>
                                <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>作为默认采集平台组合。</div>
                              </button>
                            );
                          })}
                        </div>
                      </div>

                      <ToggleRow
                        label="优先使用浏览器采集"
                        description="优先使用真实浏览器路径做抓取，适合提高平台兼容性与页面稳定性。"
                        checked={localSettings.browserFirst}
                        onChange={() => setLocalSettings((current) => ({ ...current, browserFirst: !current.browserFirst }))}
                      />
                    </div>

                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        <RiBarChartBoxLine className="h-4 w-4" />
                        当前采集画像
                      </div>
                      <div className="mt-4 text-2xl font-semibold" style={{ color: 'var(--text-primary)' }}>
                        {localSettings.collectionMode === 'full' ? '全面型' : '轻量型'}
                      </div>
                      <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                        {localSettings.collectionMode === 'full' ? '用于核心品牌和正式交付，默认保留更完整的平台与证据覆盖。' : '用于日常巡检和问题排查，优先获取变化信号。'}
                      </div>
                      <div className="mt-5 flex flex-wrap gap-2">
                        {localSettings.preferredPlatforms.map((platform) => (
                          <span key={platform} className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                            {getPlatformDisplayName(platform)}
                          </span>
                        ))}
                      </div>
                      <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                        失败重试策略暂不外露，避免把高级调试参数过早塞进主设置页。
                      </div>
                    </div>
                  </div>
                </SectionCard>

                <SectionCard
                  id="account"
                  tone="violet"
                  eyebrow="P1 / Workspace"
                  title="账户与工作区"
                  description="账户资料、安全和团队体系暂未成型，因此这里只放已经真实存在的主题能力，以及默认品牌工作区的设置入口。"
                  actions={<Button variant="secondary" size="md" onClick={handleSaveWorkspace} isLoading={isSavingWorkspace}>保存工作区偏好</Button>}
                >
                  <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
                    <div className="space-y-6">
                      <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>外观主题</div>
                            <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>直接复用现有主题切换能力，设置会即时生效。</div>
                          </div>
                          <ThemeToggle />
                        </div>
                      </div>

                      <div>
                        <FieldLabel label="默认品牌工作区" hint="用于控制台默认品牌和设置页初始配置对象。" />
                        <select value={workspaceEntityId || ''} onChange={(event) => setWorkspaceEntityId(event.target.value)} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                          {entities.map((entity) => (
                            <option key={entity.id} value={entity.id}>{entity.name}</option>
                          ))}
                        </select>
                      </div>
                    </div>

                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>当前账户状态</div>
                      <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        <div className="flex justify-between gap-4"><span>默认品牌</span><span style={{ color: 'var(--text-primary)' }}>{entities.find((entity) => entity.id === workspaceEntityId)?.name || '--'}</span></div>
                        <div className="flex justify-between gap-4"><span>主题能力</span><span style={{ color: 'var(--text-primary)' }}>已启用</span></div>
                        <div className="flex justify-between gap-4"><span>资料编辑</span><span style={{ color: 'var(--text-primary)' }}>待身份体系接入</span></div>
                        <div className="flex justify-between gap-4"><span>团队与权限</span><span style={{ color: 'var(--text-primary)' }}>暂不外露</span></div>
                      </div>
                      <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                        团队管理和 API Key 管理不再出现在主设置页里。前者要等 RBAC 成熟，后者只适合未来的管理员高级设置。
                      </div>
                    </div>
                  </div>
                </SectionCard>

                <SectionCard
                  id="legal"
                  tone="amber"
                  eyebrow="P0 / Compliance"
                  title="法务与数据说明"
                  description="这部分不再伪装成可调参数，而是作为设置页底部的合规与说明入口，明确当前版本会保存哪些数据、如何用于持续监测。"
                >
                  <div className="grid gap-4 lg:grid-cols-3">
                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}><RiFileTextLine className="h-4 w-4" />用户协议</div>
                      <div className="mt-3 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>使用本平台即代表你授权系统对所选品牌执行 AI 可见度分析、监测调度与结果导出。调度计划仅针对你拥有的品牌实体生效。</div>
                    </div>
                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}><RiNotification3Line className="h-4 w-4" />隐私政策</div>
                      <div className="mt-3 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>当前版本会保存品牌名称、域名、监测基线、快照趋势、告警记录以及你在本地设置的偏好，用于持续分析与提醒。</div>
                    </div>
                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}><RiDatabase2Line className="h-4 w-4" />数据使用说明</div>
                      <div className="mt-3 text-sm leading-7" style={{ color: 'var(--text-secondary)' }}>连续监测会复用基线中的问题集合、品牌画像与竞争对手结构，以减少重复计算并提高趋势可比性。清空基线后，下次调度会重新跑完整链路。</div>
                    </div>
                  </div>

                  <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>版本与更新时间</div>
                        <div className="mt-1 text-sm" style={{ color: 'var(--text-secondary)' }}>当前前端版本 0.1.0，设置页结构更新于 2026-03-12。</div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>设置中心已替代占位卡片</span>
                        <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>法务入口独立呈现</span>
                      </div>
                    </div>
                  </div>
                </SectionCard>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
