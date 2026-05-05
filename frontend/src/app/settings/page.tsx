'use client';

import { Suspense, useEffect, useMemo, useState, type ChangeEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import {
  RiArrowLeftLine,
  RiArrowDownSLine,
  RiCheckLine,
  RiNotification3Line,
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
import type { PanoramaAnalysisStatus } from '@/types/monitoring';
import {
  FREQUENCY_LABELS,
  type CreateScheduleInput,
  type MonitoringSchedule,
  type ScheduleFrequency,
  type UpdateScheduleInput,
} from '@/types/monitoring';

const SETTINGS_STORAGE_KEY = 'specta-settings-v1';
const DEFAULT_MONITORING_PLATFORMS = ['doubao', 'yuanbao', 'kimi', 'deepseek'] as const;
const FREQUENCY_OPTIONS: ScheduleFrequency[] = ['daily', 'weekly', 'biweekly', 'monthly'];
const HOUR_OPTIONS = Array.from({ length: 24 }, (_, index) => index);
const PLATFORM_OPTIONS = [
  { key: 'doubao', label: '豆包', description: '使用豆包 API 自动抓取', disabled: false },
  { key: 'yuanbao', label: '元宝', description: '使用元宝 API 自动抓取', disabled: false },
  { key: 'kimi', label: 'Kimi', description: '使用 Kimi API 自动抓取', disabled: false },
  { key: 'deepseek', label: 'DeepSeek', description: '使用 DeepSeek 网页版自动抓取', disabled: false },
] as const;

interface LocalSettings {
  defaultEntityId: string | null;
}

interface MonitoringFormState {
  frequency: ScheduleFrequency;
  preferredHour: number;
  timezone: string;
  platforms: string[];
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
  return (platforms || []).filter(
    (platform): platform is string =>
      PLATFORM_OPTIONS.some((option) => option.key === platform && !option.disabled)
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

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== 'number' || Number.isNaN(value)) return '--';
  const normalized = value <= 1 ? value * 100 : value;
  return `${normalized.toFixed(1)}%`;
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
  description?: string;
  tone: 'analysis' | 'mint';
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className={cn(
        'dashboard-board rounded-[28px] border px-5 py-5 md:px-7 md:py-7',
        tone === 'analysis' && 'dashboard-board--analysis',
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
          {description ? (
            <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {description}
            </p>
          ) : null}
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

function NativeSelect({
  value,
  onChange,
  children,
}: {
  value: string | number;
  onChange: (event: ChangeEvent<HTMLSelectElement>) => void;
  children: ReactNode;
}) {
  return (
      <div className="relative overflow-hidden rounded-xl">
      <select
        value={value}
        onChange={onChange}
        className="h-11 w-full appearance-none rounded-xl border bg-transparent px-3 pr-12 text-sm outline-none"
        style={{
          backgroundColor: 'var(--bg-tertiary)',
          borderColor: 'var(--border-subtle)',
          color: 'var(--text-primary)',
        }}
      >
        {children}
      </select>
      <span
        className="pointer-events-none absolute inset-y-0 right-0 flex w-11 items-center justify-center border-l"
        style={{
          color: 'var(--text-secondary)',
          borderColor: 'var(--border-subtle)',
          backgroundColor: 'var(--bg-tertiary)',
        }}
      >
        <RiArrowDownSLine className="h-4 w-4" />
      </span>
    </div>
  );
}

function PillOption({
  active,
  disabled = false,
  label,
  description,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  label: string;
  description: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={() => {
        if (!disabled) onClick();
      }}
      disabled={disabled}
      className={cn(
        'rounded-xl border px-4 py-4 text-left transition-transform',
        !disabled && 'hover:-translate-y-0.5',
        disabled && 'cursor-not-allowed opacity-70'
      )}
      style={{
        borderColor: active
          ? 'color-mix(in srgb, var(--brand-primary) 44%, var(--border-subtle) 56%)'
          : 'var(--border-subtle)',
        background: disabled
          ? 'var(--bg-tertiary)'
          : active
            ? 'color-mix(in srgb, var(--brand-primary) 10%, var(--bg-elevated) 90%)'
            : 'var(--bg-tertiary)',
      }}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {label}
        </span>
        {disabled ? (
          <span className="text-[11px] font-medium" style={{ color: 'var(--text-tertiary)' }}>
            不可用
          </span>
        ) : active ? (
          <RiCheckLine className="h-4 w-4" style={{ color: 'var(--brand-primary)' }} />
        ) : null}
      </div>
      <div className="mt-2 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
        {description}
      </div>
    </button>
  );
}

function PanoramaStatusBlock({
  status,
  loading,
}: {
  status: PanoramaAnalysisStatus | null;
  loading: boolean;
}) {
  if (loading) {
    return (
      <div className="rounded-xl border px-4 py-4 text-sm" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
        正在读取最近一次全景分析。
      </div>
    );
  }

  if (!status?.has_report) {
    return (
      <div className="rounded-xl border px-4 py-4 text-sm leading-6" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)', color: 'var(--text-secondary)' }}>
        未建立
      </div>
    );
  }

  return (
    <div className="rounded-xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
      <div className="space-y-3">
        <div>
          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>提及率</div>
          <div className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {formatPercent(status.mention_rate)}
          </div>
        </div>
        <div>
          <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>品牌排名</div>
          <div className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {status.brand_rank_label || '--'}
          </div>
        </div>
        {status.created_at ? (
          <div className="text-xs leading-5" style={{ color: 'var(--text-tertiary)' }}>
            最近更新：{formatDateTime(status.created_at)}
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SettingsPageContent() {
  const searchParams = useSearchParams();
  const timezone = getDefaultTimezone();
  const requestedEntityId = searchParams.get('entity_id');
  const requestedSection = searchParams.get('section');

  const { entities, isLoading: isEntityLoading, hasFetched, fetchEntities } = useEntityStore();
  const { selectedBrandId, setSelectedBrandId } = useDashboardStore();
  const { schedule, fetchSchedule, pauseSchedule, resumeSchedule } = useMonitoringStore();

  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [workspaceEntityId, setWorkspaceEntityId] = useState('');
  const [monitoringEntityId, setMonitoringEntityId] = useState('');
  const [localSettings, setLocalSettings] = useState<LocalSettings>(() => readLocalSettings());
  const [monitoringForm, setMonitoringForm] = useState<MonitoringFormState>(() => createMonitoringForm(null, timezone));
  const [panoramaStatus, setPanoramaStatus] = useState<PanoramaAnalysisStatus | null>(null);
  const [isPanoramaStatusLoading, setIsPanoramaStatusLoading] = useState(false);
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
      [requestedEntityId, localSettings.defaultEntityId, selectedBrandId, entities[0]?.id].find(
        (value) => value && validIds.has(value)
      ) || entities[0].id;

    if (!workspaceEntityId || !validIds.has(workspaceEntityId)) {
      setWorkspaceEntityId(preferredEntityId);
    }
    if (!monitoringEntityId || !validIds.has(monitoringEntityId)) {
      setMonitoringEntityId(preferredEntityId);
    }
  }, [
    entities,
    localSettings.defaultEntityId,
    monitoringEntityId,
    requestedEntityId,
    selectedBrandId,
    workspaceEntityId,
  ]);

  useEffect(() => {
    if (!monitoringEntityId) return;
    void fetchSchedule(monitoringEntityId);
  }, [fetchSchedule, monitoringEntityId]);

  useEffect(() => {
    let cancelled = false;
    if (!monitoringEntityId) {
      setPanoramaStatus(null);
      return;
    }
    setIsPanoramaStatusLoading(true);
    api
      .getPanoramaAnalysisStatus(monitoringEntityId)
      .then((status) => {
        if (!cancelled) {
          setPanoramaStatus(status);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setPanoramaStatus(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setIsPanoramaStatusLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [monitoringEntityId]);

  useEffect(() => {
    setMonitoringForm(createMonitoringForm(schedule, timezone));
  }, [schedule, timezone]);

  useEffect(() => {
    if (requestedSection !== 'monitoring') return;
    const timer = window.setTimeout(() => {
      document.getElementById('monitoring')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 120);
    return () => window.clearTimeout(timer);
  }, [requestedSection, entities.length]);

  const workspaceEntity = useMemo(
    () => entities.find((entity) => entity.id === workspaceEntityId) || null,
    [entities, workspaceEntityId]
  );
  const monitoringEntity = useMemo(
    () => entities.find((entity) => entity.id === monitoringEntityId) || null,
    [entities, monitoringEntityId]
  );
  const statusTone = getStatusTone(schedule?.status || 'inactive');

  const buildMonitoringPayload = (): UpdateScheduleInput & CreateScheduleInput => ({
    entity_id: monitoringEntityId,
    frequency: monitoringForm.frequency,
    preferred_hour: monitoringForm.preferredHour,
    timezone: monitoringForm.timezone,
    platforms: filterSupportedMonitoringPlatforms(monitoringForm.platforms),
  });

  const validateMonitoringForm = () => {
    if (!monitoringEntityId) {
      toast.error('请先选择要监测的品牌');
      return false;
    }
    if (filterSupportedMonitoringPlatforms(monitoringForm.platforms).length === 0) {
      toast.error('请至少选择一个可自动抓取的平台');
      return false;
    }
    return true;
  };

  const refreshMonitoringState = async (entityId: string) => {
    await fetchSchedule(entityId);
    try {
      const latestPanorama = await api.getPanoramaAnalysisStatus(entityId);
      setPanoramaStatus(latestPanorama);
    } catch {
      setPanoramaStatus(null);
    }
  };

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
    if (!validateMonitoringForm()) return;

    setIsSavingMonitoring(true);
    try {
      const payload = buildMonitoringPayload();
      if (schedule?.id) {
        await api.updateSchedule(schedule.id, payload);
      } else {
        await api.createSchedule({
          ...payload,
          status: 'paused',
        });
      }
      await refreshMonitoringState(monitoringEntityId);
      toast.success('监测设置已保存');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存监测设置失败');
    } finally {
      setIsSavingMonitoring(false);
    }
  };

  const handleToggleMonitoringStatus = async () => {
    if (!validateMonitoringForm()) return;

    setIsTogglingMonitoring(true);
    try {
      const payload = buildMonitoringPayload();
      if (!schedule?.id) {
        await api.createSchedule({
          ...payload,
          status: 'active',
        });
        toast.success('已启用自动监测');
      } else if (schedule.status === 'active') {
        await pauseSchedule(schedule.id);
        toast.success('已暂停自动监测');
      } else {
        await api.updateSchedule(schedule.id, payload);
        await resumeSchedule(schedule.id);
        toast.success('已启用自动监测');
      }
      await refreshMonitoringState(monitoringEntityId);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新监测状态失败');
    } finally {
      setIsTogglingMonitoring(false);
    }
  };

  const handlePlatformToggle = (platform: string) => {
    const option = PLATFORM_OPTIONS.find((item) => item.key === platform);
    if (!option || option.disabled) return;
    setMonitoringForm((current) => {
      const exists = current.platforms.includes(platform);
      return {
        ...current,
        platforms: exists
          ? current.platforms.filter((item) => item !== platform)
          : [...current.platforms, platform],
      };
    });
  };

  return (
    <RequireAuth>
      <div className="min-h-screen" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <DashboardTopBar />
        <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
          <div
            className="rounded-[32px] border px-6 py-6 md:px-8"
            style={{
              borderColor: 'var(--border-subtle)',
              background:
                'linear-gradient(180deg, color-mix(in srgb, var(--bg-primary) 94%, #f3efe8 6%), color-mix(in srgb, var(--bg-elevated) 97%, #efe4d3 3%))',
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
                <h1 className="mt-5 text-[30px] font-semibold tracking-tight" style={{ color: 'var(--text-primary)' }}>
                  设置
                </h1>
              </div>

              <div className="grid gap-3 sm:grid-cols-2">
                <div className="min-w-[180px] rounded-xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-elevated)' }}>
                  <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>默认品牌</div>
                  <div className="mt-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                    {workspaceEntity?.name || '未选择'}
                  </div>
                </div>
                <div className="min-w-[180px] rounded-xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
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
                请先创建品牌，再回来设置默认品牌和全景自动监测。
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
                title="全景自动监测"
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
                      <FieldLabel label="监测品牌" hint="自动监测会沿用这个品牌最近一次全景分析的问题集。" />
                      <NativeSelect
                        value={monitoringEntityId}
                        onChange={(event) => setMonitoringEntityId(event.target.value)}
                      >
                        {entities.map((entity) => (
                          <option key={entity.id} value={entity.id}>
                            {entity.name}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>

                    <div>
                      <FieldLabel label="监测频率" hint="按这个频率自动抓取并更新全景分析报告。" />
                      <div className="grid gap-3 md:grid-cols-4">
                        {FREQUENCY_OPTIONS.map((frequency) => (
                          <PillOption
                            key={frequency}
                            active={monitoringForm.frequency === frequency}
                            label={FREQUENCY_LABELS[frequency]}
                            description={
                              frequency === 'daily'
                                ? '适合高频跟踪。'
                                : frequency === 'weekly'
                                  ? '适合常规回看。'
                                  : frequency === 'biweekly'
                                    ? '适合稳定品牌。'
                                    : '适合低频巡检。'
                            }
                            onClick={() => setMonitoringForm((current) => ({ ...current, frequency }))}
                          />
                        ))}
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="执行时间" hint="到点后开始执行。" />
                      <NativeSelect
                        value={monitoringForm.preferredHour}
                        onChange={(event) =>
                          setMonitoringForm((current) => ({
                            ...current,
                            preferredHour: Number(event.target.value),
                          }))
                        }
                      >
                        {HOUR_OPTIONS.map((hour) => (
                          <option key={hour} value={hour}>
                            {formatHour(hour)}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>

                    <div>
                      <FieldLabel label="监测平台" hint="豆包、元宝、Kimi 使用 API 自动抓取；DeepSeek 使用网页版自动抓取。" />
                      <div className="grid gap-3 md:grid-cols-2">
                        {PLATFORM_OPTIONS.map((option) => (
                          <PillOption
                            key={option.key}
                            active={monitoringForm.platforms.includes(option.key)}
                            disabled={option.disabled}
                            label={option.label}
                            description={option.description}
                            onClick={() => handlePlatformToggle(option.key)}
                          />
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiNotification3Line className="h-4 w-4" />
                      当前状态
                    </div>

                    <div className="mt-4 rounded-xl border px-4 py-4" style={{ borderColor: statusTone.border, backgroundColor: statusTone.bg }}>
                      <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>状态</div>
                      <div className="mt-1 text-sm font-medium" style={{ color: statusTone.text }}>
                        {getStatusLabel(schedule?.status || 'inactive')}
                      </div>
                    </div>

                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4">
                        <span>当前品牌</span>
                        <span style={{ color: 'var(--text-primary)' }}>{monitoringEntity?.name || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>下次执行</span>
                        <span style={{ color: 'var(--text-primary)' }}>
                          {schedule?.next_run_at ? formatDateTime(schedule.next_run_at) : '--'}
                        </span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>上次执行</span>
                        <span style={{ color: 'var(--text-primary)' }}>
                          {schedule?.last_run_at ? formatDateTime(schedule.last_run_at) : '--'}
                        </span>
                      </div>
                      <div>
                        <div className="mb-2 text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
                          全景分析状态
                        </div>
                        <PanoramaStatusBlock status={panoramaStatus} loading={isPanoramaStatusLoading} />
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>监测平台</span>
                        <span className="text-right" style={{ color: 'var(--text-primary)' }}>
                          {monitoringForm.platforms.length > 0
                            ? monitoringForm.platforms.map((platform) => getPlatformDisplayName(platform)).join('、')
                            : '--'}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              </SectionCard>

              <SectionCard
                id="account"
                tone="analysis"
                eyebrow="账户与工作区"
                title="默认品牌与账号信息"
                actions={
                  <Button variant="secondary" size="md" onClick={() => void handleSaveWorkspace()} isLoading={isSavingWorkspace}>
                    保存默认设置
                  </Button>
                }
              >
                <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_340px]">
                  <div className="space-y-6">
                    <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>外观主题</div>
                          <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                            即时切换浅色或深色界面。
                          </div>
                        </div>
                        <ThemeToggle />
                      </div>
                    </div>

                    <div>
                      <FieldLabel label="默认品牌" hint="进入概览和对话时默认使用这个品牌。" />
                      <NativeSelect
                        value={workspaceEntityId}
                        onChange={(event) => setWorkspaceEntityId(event.target.value)}
                      >
                        {entities.map((entity) => (
                          <option key={entity.id} value={entity.id}>
                            {entity.name}
                          </option>
                        ))}
                      </NativeSelect>
                    </div>
                  </div>

                  <div className="rounded-xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                    <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      <RiTeamLine className="h-4 w-4" />
                      当前账号
                    </div>
                    <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                      <div className="flex justify-between gap-4">
                        <span>默认品牌</span>
                        <span style={{ color: 'var(--text-primary)' }}>{workspaceEntity?.name || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>登录账号</span>
                        <span style={{ color: 'var(--text-primary)' }}>{currentUser?.email || currentUser?.phone || '--'}</span>
                      </div>
                      <div className="flex justify-between gap-4">
                        <span>账户状态</span>
                        <span style={{ color: 'var(--text-primary)' }}>{formatAccountStatusLabel(currentUser?.status)}</span>
                      </div>
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

export default function SettingsPage() {
  return (
    <Suspense fallback={null}>
      <SettingsPageContent />
    </Suspense>
  );
}
