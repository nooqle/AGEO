'use client';

import { useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  RiArrowLeftLine,
  RiCheckLine,
  RiNotification3Line,
  RiSettings4Line,
  RiTeamLine,
} from '@remixicon/react';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { DashboardTopBar } from '@/components/layout/DashboardTopBar';
import { Button } from '@/components/ui/button';
import { ThemeToggle } from '@/components/ui/ThemeToggle';
import { toast } from '@/components/ui/toast';
import { getPlatformDisplayName } from '@/config/platformLabel';
import { cn, formatDateTime } from '@/lib/utils';
import { api } from '@/services/api';
import { useDashboardStore } from '@/stores/dashboardStore';
import { useEntityStore } from '@/stores/entityStore';
import { useMonitoringStore } from '@/stores/monitoringStore';
import type { AuthUser } from '@/types/auth';
import {
  FREQUENCY_LABELS,
  type CreateScheduleInput,
  type MonitoringSchedule,
  type ScheduleFrequency,
  type UpdateScheduleInput,
} from '@/types/monitoring';

const SETTINGS_STORAGE_KEY = 'specta-settings-v1';
const MONITORING_PLATFORM_KEYS = ['doubao', 'yuanbao', 'kimi', 'deepseek'] as const;
const DEFAULT_MONITORING_PLATFORMS = ['doubao', 'kimi'] as const;
const PLATFORM_OPTIONS = MONITORING_PLATFORM_KEYS.map((platformKey) => [
  platformKey,
  getPlatformDisplayName(platformKey),
]) as Array<[string, string]>;
const FREQUENCY_OPTIONS: ScheduleFrequency[] = ['daily', 'weekly', 'biweekly', 'monthly'];
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, index) => index);

interface LocalSettings {
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
    return {
      ...DEFAULT_LOCAL_SETTINGS,
      ...(JSON.parse(raw) as Partial<LocalSettings>),
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

function filterSupportedMonitoringPlatforms(platforms: string[] | null | undefined): string[] {
  return (platforms || []).filter((platform): platform is string =>
    MONITORING_PLATFORM_KEYS.includes(platform as (typeof MONITORING_PLATFORM_KEYS)[number])
  );
}

function createMonitoringForm(schedule: MonitoringSchedule | null, timezone: string): MonitoringFormState {
  const platforms = schedule
    ? filterSupportedMonitoringPlatforms(schedule.platforms)
    : [...DEFAULT_MONITORING_PLATFORMS];

  return {
    frequency: schedule?.frequency || 'weekly',
    preferredHour: schedule?.preferred_hour ?? 9,
    timezone: schedule?.timezone || timezone,
    platforms,
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

function formatAccountStatusLabel(status?: string | null) {
  switch (status) {
    case 'active':
      return '正常';
    case 'pending_review':
      return '待开通';
    case 'suspended':
      return '已停用';
    default:
      return '--';
  }
}

function formatHour(hour: number) {
  return `${String(hour).padStart(2, '0')}:00`;
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
  tone: 'violet' | 'mint';
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        'dashboard-board rounded-[28px] border px-5 py-5 md:px-7 md:py-7',
        tone === 'violet' && 'dashboard-board--violet',
        tone === 'mint' && 'dashboard-board--mint'
      )}
    >
      <div
        className="flex flex-col gap-4 border-b pb-5 md:flex-row md:items-end md:justify-between"
        style={{ borderColor: 'var(--border-subtle)' }}
      >
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
      <div className="mt-6">{children}</div>
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
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onChange}
      className="flex w-full items-start justify-between gap-4 rounded-2xl border px-4 py-4 text-left"
      style={{
        borderColor: checked ? 'color-mix(in srgb, var(--brand-primary) 42%, var(--border-subtle) 58%)' : 'var(--border-subtle)',
        backgroundColor: checked ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-tertiary) 90%)' : 'var(--bg-tertiary)',
      }}
    >
      <div>
        <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </div>
        <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
          {description}
        </div>
      </div>
      <div
        className="relative mt-0.5 h-6 w-11 rounded-full border transition-colors"
        style={{
          borderColor: checked ? 'var(--brand-primary)' : 'var(--border-subtle)',
          backgroundColor: checked ? 'var(--brand-primary)' : 'var(--bg-elevated)',
        }}
      >
        <span
          className="absolute top-0.5 h-4.5 w-4.5 rounded-full bg-white transition-transform"
          style={{
            left: checked ? 'calc(100% - 1.25rem)' : '0.125rem',
            boxShadow: '0 6px 12px rgba(15, 23, 42, 0.15)',
          }}
        />
      </div>
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
  const { entities, isLoading: isEntityLoading, hasFetched, fetchEntities } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const { schedule, isScheduleLoading, fetchSchedule, pauseSchedule, resumeSchedule } = useMonitoringStore();

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [workspaceEntityId, setWorkspaceEntityId] = useState('');
  const [monitoringEntityId, setMonitoringEntityId] = useState('');
  const [localSettings, setLocalSettings] = useState<LocalSettings>(() => readLocalSettings());
  const [monitoringForm, setMonitoringForm] = useState<MonitoringFormState>(() => createMonitoringForm(null, timezone));
  const [isSavingWorkspace, setIsSavingWorkspace] = useState(false);
  const [isSavingMonitoring, setIsSavingMonitoring] = useState(false);
  const [isTogglingMonitoring, setIsTogglingMonitoring] = useState(false);

  useEffect(() => {
    if (!hasFetched) {
      void fetchEntities();
    }
  }, [fetchEntities, hasFetched]);

  useEffect(() => {
    let cancelled = false;
    api
      .getMe()
      .then((user) => {
        if (!cancelled) {
          setCurrentUser(user);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCurrentUser(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (entities.length === 0) return;
    const validIds = new Set(entities.map((entity) => entity.id));
    const preferredEntityId =
      [localSettings.defaultEntityId, selectedBrandId, entities[0]?.id].find((value) => value && validIds.has(value)) ||
      entities[0].id;

    if (!workspaceEntityId || !validIds.has(workspaceEntityId)) {
      setWorkspaceEntityId(preferredEntityId);
    }
    if (!monitoringEntityId || !validIds.has(monitoringEntityId)) {
      setMonitoringEntityId(preferredEntityId);
    }
  }, [entities, localSettings.defaultEntityId, monitoringEntityId, selectedBrandId, workspaceEntityId]);

  useEffect(() => {
    if (!monitoringEntityId) return;
    void fetchSchedule(monitoringEntityId);
  }, [fetchSchedule, monitoringEntityId]);

  useEffect(() => {
    setMonitoringForm(createMonitoringForm(schedule, timezone));
  }, [schedule, timezone]);

  const workspaceEntity = useMemo(
    () => entities.find((entity) => entity.id === workspaceEntityId) || null,
    [entities, workspaceEntityId]
  );
  const monitoringEntity = useMemo(
    () => entities.find((entity) => entity.id === monitoringEntityId) || null,
    [entities, monitoringEntityId]
  );
  const statusTone = getStatusTone(schedule?.status || 'inactive');

  const handleSaveWorkspace = async () => {
    if (!workspaceEntityId) {
      toast.error('请先选择默认品牌');
      return;
    }
    setIsSavingWorkspace(true);
    try {
      const nextSettings = { defaultEntityId: workspaceEntityId };
      saveLocalSettings(nextSettings);
      setLocalSettings(nextSettings);
      setSelectedBrandId(workspaceEntityId);
      if (!monitoringEntityId) {
        setMonitoringEntityId(workspaceEntityId);
      }
      toast.success('默认设置已保存');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存默认设置失败');
    } finally {
      setIsSavingWorkspace(false);
    }
  };

  const handleSaveMonitoring = async () => {
    if (!monitoringEntityId) {
      toast.error('请先选择要监测的品牌');
      return;
    }
    if (monitoringForm.platforms.length === 0) {
      toast.error('请至少选择一个监测平台');
      return;
    }

    setIsSavingMonitoring(true);
    try {
      const payload: UpdateScheduleInput & CreateScheduleInput = {
        entity_id: monitoringEntityId,
        frequency: monitoringForm.frequency,
        preferred_hour: monitoringForm.preferredHour,
        timezone: monitoringForm.timezone,
        platforms: filterSupportedMonitoringPlatforms(monitoringForm.platforms),
        alert_on_significant_change: monitoringForm.alertOnSignificantChange,
        alert_threshold_bwvs: monitoringForm.alertThresholdBwvs,
      };

      if (schedule?.id) {
        await api.updateSchedule(schedule.id, payload);
      } else {
        await api.createSchedule(payload);
      }

      await fetchSchedule(monitoringEntityId);
      toast.success('监测设置已保存');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存监测设置失败');
    } finally {
      setIsSavingMonitoring(false);
    }
  };

  const handleToggleMonitoringStatus = async () => {
    if (!schedule?.id) {
      await handleSaveMonitoring();
      return;
    }

    setIsTogglingMonitoring(true);
    try {
      if (schedule.status === 'active') {
        await pauseSchedule(schedule.id);
        toast.success('已暂停自动监测');
      } else {
        await resumeSchedule(schedule.id);
        toast.success('已恢复自动监测');
      }
      await fetchSchedule(monitoringEntityId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新监测状态失败');
    } finally {
      setIsTogglingMonitoring(false);
    }
  };

  const handlePlatformToggle = (platform: string) => {
    setMonitoringForm((current) => {
      const exists = current.platforms.includes(platform);
      return {
        ...current,
        platforms: exists ? current.platforms.filter((item) => item !== platform) : [...current.platforms, platform],
      };
    });
  };

  return (
    <RequireAuth>
      <div className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <DashboardTopBar />
        <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
          <div
            className="rounded-[32px] border px-6 py-6 md:px-8 md:py-8"
            style={{
              borderColor: 'var(--border-subtle)',
              background:
                'linear-gradient(135deg, color-mix(in srgb, var(--bg-primary) 86%, #f3efe8 14%) 0%, color-mix(in srgb, var(--bg-elevated) 88%, #e8f0ff 12%) 100%)',
            }}
          >
            <div className="flex flex-col gap-5 md:flex-row md:items-start md:justify-between">
              <div className="max-w-2xl">
                <Link
                  href="/dashboard"
                  className="inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    color: 'var(--text-secondary)',
                    backgroundColor: 'var(--bg-elevated)',
                  }}
                >
                  <RiArrowLeftLine className="h-3.5 w-3.5" />
                  返回概览
                </Link>
                <div className="mt-4 inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-tertiary)' }}>
                  <RiSettings4Line className="h-3.5 w-3.5" />
                  设置
                </div>
                <h1 className="mt-4 text-3xl font-semibold tracking-tight md:text-[2rem]" style={{ color: 'var(--text-primary)' }}>
                  只保留真正需要改的设置
                </h1>
                <p className="mt-3 max-w-2xl text-sm leading-7 md:text-[15px]" style={{ color: 'var(--text-secondary)' }}>
                  这里仅保留默认品牌、账号信息和自动监测配置。导出、采集方式和内部能力管理不再放在这个页面。
                </p>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="min-w-[180px] rounded-3xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>默认品牌</div>
                  <div className="mt-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {workspaceEntity?.name || '未选择'}
                  </div>
                </div>
                <div className="min-w-[180px] rounded-3xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>自动监测</div>
                  <div className="mt-2 text-sm font-medium" style={{ color: statusTone.text }}>
                    {getStatusLabel(schedule?.status || 'inactive')}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {isEntityLoading && entities.length === 0 ? (
            <div className="rounded-[28px] border px-6 py-8 text-sm" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
              正在加载品牌列表...
            </div>
          ) : entities.length === 0 ? (
            <div className="rounded-[28px] border px-6 py-8" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
              <div className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>还没有可设置的品牌</div>
              <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                请先创建品牌，再回来配置默认品牌和自动监测。
              </div>
              <div className="mt-5">
                <Link href="/dashboard" className="inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                  去创建品牌
                </Link>
              </div>
            </div>
          ) : (
            <>
              <SectionCard
                id="monitoring"
                tone="mint"
                eyebrow="监测设置"
                title="自动监测"
                description="选择要监测的品牌，设置监测频率、时间、平台和提醒阈值。"
                actions={
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" size="md" onClick={() => void handleToggleMonitoringStatus()} isLoading={isTogglingMonitoring}>
                      {schedule?.status === 'active' ? '暂停监测' : '启用监测'}
                    </Button>
                    <Button variant="primary" size="md" onClick={() => void handleSaveMonitoring()} isLoading={isSavingMonitoring}>
                      保存监测设置
                    </Button>
                  </div>
                }
              >
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="space-y-6">
                    <div>
                      <FieldLabel label="监测品牌" hint="你可以单独配置每个品牌的自动监测规则。" />
                      <select value={monitoringEntityId} onChange={(event) => setMonitoringEntityId(event.target.value)} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                        {entities.map((entity) => (
                          <option key={entity.id} value={entity.id}>{entity.name}</option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <FieldLabel label="监测频率" hint="按固定节奏生成新的监测结果。" />
                      <div className="grid gap-3 md:grid-cols-4">
                        {FREQUENCY_OPTIONS.map((frequency) => (
                          <PillOption
                            key={frequency}
                            active={monitoringForm.frequency === frequency}
                            label={FREQUENCY_LABELS[frequency]}
                            description={frequency === 'daily' ? '适合高频监测。' : frequency === 'weekly' ? '适合常规跟踪。' : frequency === 'biweekly' ? '适合稳定品牌。' : '适合低频回顾。'}
                            onClick={() => setMonitoringForm((current) => ({ ...current, frequency }))}
                          />
                        ))}
                      </div>
                    </div>

                    <div className="grid gap-6 md:grid-cols-2">
                      <div>
                        <FieldLabel label="执行时间" hint="每天在这个整点附近启动监测。" />
                        <select value={monitoringForm.preferredHour} onChange={(event) => setMonitoringForm((current) => ({ ...current, preferredHour: Number(event.target.value) }))} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                          {HOUR_OPTIONS.map((hour) => (
                            <option key={hour} value={hour}>{formatHour(hour)}</option>
                          ))}
                        </select>
                      </div>

                      <div>
                        <FieldLabel label="提醒阈值" hint="品牌可见度变化达到这个数值时提醒你。" />
                        <input type="number" min={1} max={100} value={monitoringForm.alertThresholdBwvs} onChange={(event) => setMonitoringForm((current) => ({ ...current, alertThresholdBwvs: Number(event.target.value) || 1 }))} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }} />
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="监测平台" hint="只保留你当前最关心的平台，不需要全选。" />
                      <div className="grid gap-3 md:grid-cols-2">
                        {PLATFORM_OPTIONS.map(([platformKey, platformLabel]) => (
                          <PillOption key={platformKey} active={monitoringForm.platforms.includes(platformKey)} label={platformLabel} description="纳入自动监测范围。" onClick={() => handlePlatformToggle(platformKey)} />
                        ))}
                      </div>
                    </div>

                    <ToggleRow label="开启变化提醒" description="当品牌可见度出现明显变化时，在通知里提醒你。" checked={monitoringForm.alertOnSignificantChange} onChange={() => setMonitoringForm((current) => ({ ...current, alertOnSignificantChange: !current.alertOnSignificantChange }))} />
                  </div>

                  <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiNotification3Line className="h-4 w-4" />
                      当前状态
                    </div>
                    <div className="mt-4 rounded-2xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>状态</div>
                      <div className="mt-1 text-sm font-medium" style={{ color: statusTone.text }}>{getStatusLabel(schedule?.status || 'inactive')}</div>
                    </div>

                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4"><span>当前品牌</span><span style={{ color: 'var(--text-primary)' }}>{monitoringEntity?.name || '--'}</span></div>
                      <div className="flex justify-between gap-4"><span>下次执行</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.next_run_at ? formatDateTime(schedule.next_run_at) : '--'}</span></div>
                      <div className="flex justify-between gap-4"><span>上次执行</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.last_run_at ? formatDateTime(schedule.last_run_at) : '--'}</span></div>
                      <div className="flex justify-between gap-4"><span>基线状态</span><span style={{ color: 'var(--text-primary)' }}>{schedule?.has_baseline ? '已建立' : '未建立'}</span></div>
                      <div className="flex justify-between gap-4"><span>监测平台</span><span className="text-right" style={{ color: 'var(--text-primary)' }}>{monitoringForm.platforms.length > 0 ? monitoringForm.platforms.map((platform) => getPlatformDisplayName(platform)).join('、') : '--'}</span></div>
                    </div>

                    {isScheduleLoading ? (
                      <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                        正在读取当前监测配置...
                      </div>
                    ) : null}
                  </div>
                </div>
              </SectionCard>

              <SectionCard
                id="account"
                tone="violet"
                eyebrow="账户与工作区"
                title="默认品牌与账号信息"
                description="设置默认品牌，查看当前账号和组织信息。"
                actions={<Button variant="secondary" size="md" onClick={() => void handleSaveWorkspace()} isLoading={isSavingWorkspace}>保存默认设置</Button>}
              >
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="space-y-6">
                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>外观主题</div>
                          <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>即时切换浅色或深色界面。</div>
                        </div>
                        <ThemeToggle />
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="默认品牌" hint="进入概览和对话时，优先使用这个品牌。" />
                      <select value={workspaceEntityId} onChange={(event) => setWorkspaceEntityId(event.target.value)} className="h-11 w-full rounded-2xl border px-3 text-sm outline-none" style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}>
                        {entities.map((entity) => (
                          <option key={entity.id} value={entity.id}>{entity.name}</option>
                        ))}
                      </select>
                    </div>

                    {currentUser?.role === 'internal_admin' ? (
                      <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>运营后台</div>
                            <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>审批、组织管理和运营任务请在运营后台处理。</div>
                          </div>
                          <Link href="/control-plane" className="inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
                            进入运营后台
                          </Link>
                        </div>
                      </div>
                    ) : null}
                  </div>

                  <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiTeamLine className="h-4 w-4" />
                      当前账号
                    </div>
                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4"><span>默认品牌</span><span style={{ color: 'var(--text-primary)' }}>{workspaceEntity?.name || '--'}</span></div>
                      <div className="flex justify-between gap-4"><span>登录账号</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.email || currentUser?.phone || '--'}</span></div>
                      <div className="flex justify-between gap-4"><span>账户状态</span><span style={{ color: 'var(--text-primary)' }}>{formatAccountStatusLabel(currentUser?.status)}</span></div>
                      <div className="flex justify-between gap-4"><span>组织归属</span><span className="text-right" style={{ color: 'var(--text-primary)' }}>{currentUser?.organization_name || (currentUser?.organization_id ? '已加入组织' : '个人账号')}</span></div>
                      <div className="flex justify-between gap-4"><span>职位信息</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.job_title || '--'}</span></div>
                    </div>
                    <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                      这里不再展示审批列表、能力管理和导出预设。需要处理运营事项时，请进入对应页面。
                    </div>
                  </div>
                </div>
              </SectionCard>
            </>
          )}
        </div>
      </div>
    </RequireAuth>
  );
}
