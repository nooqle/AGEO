'use client';

import { startTransition, useEffect, useMemo, useState, type ReactNode } from 'react';
import Link from 'next/link';
import {
  RiArrowLeftLine,
  RiBarChartBoxLine,
  RiCheckLine,
  RiDatabase2Line,
  RiFileTextLine,
  RiFlashlightLine,
  RiNotification3Line,
  RiSettings4Line,
  RiTeamLine,
} from '@remixicon/react';
import { RequireAuth } from '@/components/auth/RequireAuth';
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
import type { AuthUser, RegistrationApplication } from '@/types/auth';
import type {
  SkillDefinition,
  SkillVersion,
} from '@/types/skill';
import { PLATFORM_DISPLAY_NAMES, getPlatformDisplayName } from '@/lib/platformLabel';
import { cn, formatDateTime, formatRelativeTime } from '@/lib/utils';

const SETTINGS_STORAGE_KEY = 'specta-settings-v1';
const PLATFORM_OPTIONS = Object.entries(PLATFORM_DISPLAY_NAMES);
const SECTIONS = [
  { id: 'monitoring', label: '监测与通知', hint: '真实后端能力' },
  { id: 'exports', label: '数据与导出', hint: '导出预设' },
  { id: 'collection', label: '采集偏好', hint: 'AEO 运行偏好' },
  { id: 'skills', label: 'Skills', hint: '轻量控制面' },
  { id: 'account', label: '账户与工作区', hint: '主题与默认品牌' },
  { id: 'legal', label: '法务与数据说明', hint: '合规入口' },
] as const;

type ExportFormat = 'pdf' | 'excel';
type ExportScope = 'overview' | 'full' | 'trend';
type CollectionMode = 'fast' | 'full';
type SkillScopeKind = 'global' | 'workspace' | 'entity';

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

interface SkillFormState {
  enabled: boolean;
  assignmentScopeKind: SkillScopeKind;
  assignmentScopeRef: string | null;
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

const DEFAULT_SKILL_FORM: SkillFormState = {
  enabled: true,
  assignmentScopeKind: 'global',
  assignmentScopeRef: null,
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

function buildSkillFormState(
  skill?: SkillDefinition | null,
  defaultEntityId?: string | null
): SkillFormState {
  if (!skill) {
    return {
      ...DEFAULT_SKILL_FORM,
      assignmentScopeRef: defaultEntityId || null,
    };
  }
  const primaryAssignment = getPrimaryAssignment(skill);
  return {
    enabled: skill.enabled,
    assignmentScopeKind: (primaryAssignment?.scope_kind as SkillScopeKind | undefined) || 'global',
    assignmentScopeRef:
      primaryAssignment?.scope_ref ||
      (primaryAssignment?.scope_kind === 'entity' ? defaultEntityId || null : null),
  };
}

function getPrimaryAssignment(skill: SkillDefinition) {
  const assignments = [...(skill.assignments || [])];
  if (assignments.length === 0) return null;
  const priority = { global: 0, workspace: 1, entity: 2 } as const;
  assignments.sort((a, b) => {
    const ap = priority[a.scope_kind as keyof typeof priority] ?? -1;
    const bp = priority[b.scope_kind as keyof typeof priority] ?? -1;
    if (ap !== bp) return bp - ap;
    return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
  });
  return assignments[0];
}

function formatAssignmentScopeLabel(skill: SkillDefinition, entities: Array<{ id: string; name: string }>) {
  const assignment = getPrimaryAssignment(skill);
  if (!assignment) return '未配置范围';
  if (assignment.scope_kind === 'global') return '全局';
  if (assignment.scope_kind === 'workspace') return '当前工作区';
  if (assignment.scope_kind === 'entity') {
    const entityName = entities.find((entity) => entity.id === assignment.scope_ref)?.name;
    return entityName ? `品牌：${entityName}` : `品牌：${assignment.scope_ref || '--'}`;
  }
  return assignment.scope_kind;
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
  const [skills, setSkills] = useState<SkillDefinition[]>([]);
  const [skillVersions, setSkillVersions] = useState<Record<string, SkillVersion[]>>({});
  const [expandedSkillId, setExpandedSkillId] = useState<string | null>(null);
  const [editingSkillId, setEditingSkillId] = useState<string | null>(null);
  const [skillForm, setSkillForm] = useState<SkillFormState>(DEFAULT_SKILL_FORM);
  const [isSkillsLoading, setIsSkillsLoading] = useState(false);
  const [isSkillFormSaving, setIsSkillFormSaving] = useState(false);
  const [savingSkillId, setSavingSkillId] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [registrationApplications, setRegistrationApplications] = useState<RegistrationApplication[]>([]);
  const [isApplicationsLoading, setIsApplicationsLoading] = useState(false);

  const selectedEntity = useMemo(
    () => entities.find((entity) => entity.id === selectedEntityId) || null,
    [entities, selectedEntityId]
  );
  const editingSkill = useMemo(
    () => skills.find((skill) => skill.id === editingSkillId) || null,
    [editingSkillId, skills]
  );

  async function loadRegistrationApplications() {
    setIsApplicationsLoading(true);
    try {
      const applications = await api.listRegistrationApplications();
      setRegistrationApplications(applications);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '加载注册申请失败');
    } finally {
      setIsApplicationsLoading(false);
    }
  }

  useEffect(() => {
    if (!selectedEntityId) return;
    if (editingSkillId) return;
    setSkillForm((current) => {
      if (current.assignmentScopeKind !== 'entity') return current;
      if (current.assignmentScopeRef === selectedEntityId) return current;
      return { ...current, assignmentScopeRef: selectedEntityId };
    });
  }, [editingSkillId, selectedEntityId]);

  useEffect(() => {
    const settings = readLocalSettings();
    setLocalSettings(settings);

    void loadSkills();
    void Promise.allSettled([
      fetchEntities(),
      fetchUnreadCount(),
      api
        .getMe()
        .then((user) => {
          setCurrentUser(user);
          if (user.role === 'internal_admin') {
            return loadRegistrationApplications();
          }
          setRegistrationApplications([]);
          return undefined;
        })
        .catch(() => {
          setCurrentUser(null);
          setRegistrationApplications([]);
        }),
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

  async function loadSkills(options?: { preserveExpanded?: boolean }) {
    setIsSkillsLoading(true);
    try {
      const nextSkills = (await api.getSkills()).filter((skill) => skill.is_builtin);
      setSkills(nextSkills);
      if (!options?.preserveExpanded) {
        setExpandedSkillId(null);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '读取 Skills 失败');
    } finally {
      setIsSkillsLoading(false);
    }
  }

  async function handleToggleSkill(skill: SkillDefinition) {
    setSavingSkillId(skill.id);
    try {
      const updated = await api.updateSkill(skill.id, { enabled: !skill.enabled });
      setSkills((current) => current.map((item) => (item.id === skill.id ? updated : item)));
      toast.success(updated.enabled ? 'Skill 已启用' : 'Skill 已停用');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '更新 Skill 状态失败');
    } finally {
      setSavingSkillId(null);
    }
  }

  async function handleToggleVersions(skill: SkillDefinition) {
    if (expandedSkillId === skill.id) {
      setExpandedSkillId(null);
      return;
    }

    setExpandedSkillId(skill.id);
    if (skillVersions[skill.id]) return;

    setSavingSkillId(skill.id);
    try {
      const versions = await api.getSkillVersions(skill.id);
      setSkillVersions((current) => ({ ...current, [skill.id]: versions }));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '读取 Skill 版本失败');
    } finally {
      setSavingSkillId(null);
    }
  }

  function handleEditSkill(skill: SkillDefinition) {
    if (!skill.is_builtin) return;
    setEditingSkillId(skill.id);
    setSkillForm(buildSkillFormState(skill, selectedEntityId));
  }

  function handleCancelSkillEdit() {
    setEditingSkillId(null);
    setSkillForm(buildSkillFormState(null, selectedEntityId));
  }

  async function handleSubmitSkillForm() {
    setIsSkillFormSaving(true);
    try {
      if (!editingSkillId) {
        toast.error('请先选择一个 Skill Family');
        return;
      }

      const payload = {
        enabled: skillForm.enabled,
        assignment_scope_kind: skillForm.assignmentScopeKind,
        assignment_scope_ref:
          skillForm.assignmentScopeKind === 'global'
            ? null
            : skillForm.assignmentScopeKind === 'workspace'
              ? 'current-workspace'
              : skillForm.assignmentScopeRef,
      };

      if (payload.assignment_scope_kind === 'entity' && !payload.assignment_scope_ref) {
        toast.error('请选择 Skill Family 的品牌范围');
        return;
      }

      const updated = await api.updateSkill(editingSkillId, payload);
      setSkills((current) => current.map((item) => (item.id === editingSkillId ? updated : item)));
      setSkillForm(buildSkillFormState(updated, selectedEntityId));
      toast.success('Skill Family 配置已更新');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '保存 Skill 失败');
    } finally {
      setIsSkillFormSaving(false);
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
  const builtinSkills = useMemo(
    () => skills.filter((skill) => skill.is_builtin),
    [skills]
  );

  return (
    <RequireAuth>
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
                  id="skills"
                  tone="violet"
                  eyebrow="P0 / Skill Control"
                  title="Skills"
                  description="这里先只保留 3 个固定业务 Skill Family 的控制面。当前版本不开放自定义 Skill，避免把 orchestrator 和配置面做得过重。"
                  actions={
                    <div className="flex gap-2">
                      {editingSkillId ? (
                        <Button variant="ghost" size="md" onClick={handleCancelSkillEdit}>
                          取消编辑
                        </Button>
                      ) : null}
                      <Button variant="secondary" size="md" onClick={() => void loadSkills({ preserveExpanded: true })} isLoading={isSkillsLoading}>
                        刷新 Skills
                      </Button>
                    </div>
                  }
                >
                  <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(320px,0.85fr)]">
                    <div className="space-y-5">
                      <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>当前固定 Skill Families</div>
                            <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                              当前生产版本固定为 3 个业务 Skill Family。这里只配置启用状态与生效范围，不开放创建额外 Skill 或 Profile。
                            </div>
                          </div>
                          <div className="flex flex-wrap gap-2">
                            <span className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-elevated)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                              builtin {builtinSkills.length}
                            </span>
                          </div>
                        </div>
                      </div>

                      {isSkillsLoading ? (
                        <div className="rounded-3xl border border-dashed px-5 py-8 text-center text-sm" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                          正在读取 Skill 列表...
                        </div>
                      ) : (
                        builtinSkills.map((skill) => (
                          <div
                            key={skill.id}
                            className="rounded-3xl border px-5 py-5"
                            style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}
                          >
                            <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                              <div>
                                <div className="flex flex-wrap items-center gap-2">
                                  <div className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
                                    {skill.display_name}
                                  </div>
                                  <span className="rounded-full px-2 py-0.5 text-[11px]" style={{ backgroundColor: skill.effective_enabled ? 'rgba(34,197,94,0.12)' : 'rgba(148,163,184,0.12)', color: skill.effective_enabled ? 'var(--success)' : 'var(--text-tertiary)' }}>
                                    {skill.effective_enabled ? '启用中' : '已停用'}
                                  </span>
                                </div>
                                <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                                  {skill.description}
                                </div>
                                <div className="mt-3 flex flex-wrap gap-2 text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
                                  <span className="rounded-full px-2 py-0.5" style={{ border: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}>
                                    范围: {formatAssignmentScopeLabel(skill, entities)}
                                  </span>
                                  <span className="rounded-full px-2 py-0.5" style={{ border: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}>
                                    v{skill.version}
                                  </span>
                                </div>
                              </div>
                              <div className="flex flex-wrap gap-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => void handleToggleSkill(skill)}
                                  isLoading={savingSkillId === skill.id}
                                >
                                  {skill.enabled ? '停用' : '启用'}
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => void handleToggleVersions(skill)}
                                  isLoading={savingSkillId === skill.id && expandedSkillId !== skill.id}
                                >
                                  {expandedSkillId === skill.id ? '收起版本' : '查看版本'}
                                </Button>
                                <Button variant="ghost" size="sm" onClick={() => handleEditSkill(skill)}>
                                  配置范围
                                </Button>
                              </div>
                            </div>

                            <div className="mt-4 grid gap-3 md:grid-cols-2">
                              <div>
                                <div className="text-xs font-medium uppercase tracking-[0.14em]" style={{ color: 'var(--text-tertiary)' }}>
                                  意图信号
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {skill.intent_signals.map((item) => (
                                    <span key={item} className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              </div>
                              <div>
                                <div className="text-xs font-medium uppercase tracking-[0.14em]" style={{ color: 'var(--text-tertiary)' }}>
                                  Artifact 类型
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  {skill.artifact_types.map((item) => (
                                    <span key={item} className="rounded-full px-2.5 py-1 text-xs" style={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', color: 'var(--text-secondary)' }}>
                                      {item}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>

                            {expandedSkillId === skill.id ? (
                              <div className="mt-5 rounded-2xl border px-4 py-4" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}>
                                <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                                  版本记录
                                </div>
                                <div className="mt-3 space-y-3">
                                  {(skillVersions[skill.id] || []).length === 0 ? (
                                    <div className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                                      还没有额外版本记录。
                                    </div>
                                  ) : (
                                    skillVersions[skill.id].map((version) => (
                                      <div key={version.id} className="rounded-2xl border px-4 py-3" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                                        <div className="flex items-center justify-between gap-4">
                                          <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                                            v{version.version}
                                          </div>
                                        <div className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
                                          {formatDateTime(version.created_at)}
                                        </div>
                                      </div>
                                      <div className="mt-3 rounded-xl border px-3 py-3 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)', color: 'var(--text-secondary)' }}>
                                        记录该 Skill Family 在当时的启用状态与范围配置，用于发布追踪与回溯。
                                      </div>
                                      </div>
                                    ))
                                  )}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        ))
                      )}
                    </div>

                      <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                        <div className="flex items-center gap-2 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                          <RiFlashlightLine className="h-4 w-4" />
                          {editingSkillId ? '配置 Skill Family' : 'Skill Family 设置'}
                        </div>
                        <div className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
                          {editingSkill
                            ? '当前版本只开放固定 Skill Family 的启停与范围配置，不开放自定义 Skill、Profile 或额外执行器。'
                            : '从左侧选择一个固定 Skill Family，即可调整它的启用状态和生效范围。'}
                        </div>

                      <div className="mt-5 space-y-5">
                        {editingSkill ? (
                          <div className="rounded-2xl border px-4 py-4 text-sm" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}>
                            <div className="text-xs font-medium uppercase tracking-[0.14em]" style={{ color: 'var(--text-tertiary)' }}>
                              当前 Skill Family
                            </div>
                            <div className="mt-2 font-medium" style={{ color: 'var(--text-primary)' }}>
                              {editingSkill.display_name}
                            </div>
                            <div className="mt-2 leading-6" style={{ color: 'var(--text-secondary)' }}>
                              {editingSkill.description}
                            </div>
                          </div>
                        ) : null}

                        <div>
                          <FieldLabel label="生效范围" hint="决定这个固定 Skill Family 在什么范围内会被主 Agent 视为可用能力。" />
                          <div className="grid gap-3 md:grid-cols-3">
                            <PillOption
                              active={skillForm.assignmentScopeKind === 'global'}
                              label="全局"
                              description="对当前系统所有工作区生效。"
                              onClick={() =>
                                setSkillForm((current) => ({
                                  ...current,
                                  assignmentScopeKind: 'global',
                                  assignmentScopeRef: null,
                                }))
                              }
                            />
                            <PillOption
                              active={skillForm.assignmentScopeKind === 'workspace'}
                              label="当前工作区"
                              description="只对当前用户工作区生效。"
                              onClick={() =>
                                setSkillForm((current) => ({
                                  ...current,
                                  assignmentScopeKind: 'workspace',
                                  assignmentScopeRef: 'current-workspace',
                                }))
                              }
                            />
                            <PillOption
                              active={skillForm.assignmentScopeKind === 'entity'}
                              label="当前品牌"
                              description="只对当前选中的品牌实体生效。"
                              onClick={() =>
                                setSkillForm((current) => ({
                                  ...current,
                                  assignmentScopeKind: 'entity',
                                  assignmentScopeRef: selectedEntityId || current.assignmentScopeRef,
                                }))
                              }
                            />
                          </div>
                          {skillForm.assignmentScopeKind === 'entity' ? (
                            <div className="mt-3">
                              <select
                                value={skillForm.assignmentScopeRef || ''}
                                onChange={(event) =>
                                  setSkillForm((current) => ({
                                    ...current,
                                    assignmentScopeRef: event.target.value || null,
                                  }))
                                }
                                className="h-11 w-full rounded-2xl border px-3 text-sm outline-none"
                                style={{ backgroundColor: 'var(--bg-secondary)', borderColor: 'var(--border-subtle)', color: 'var(--text-primary)' }}
                              >
                                <option value="">请选择品牌</option>
                                {entities.map((entity) => (
                                  <option key={entity.id} value={entity.id}>
                                    {entity.name}
                                  </option>
                                ))}
                              </select>
                            </div>
                          ) : null}
                        </div>

                        <ToggleRow
                          label="启用这个 Skill Family"
                          description="关闭后主 Agent 不会再调用这类能力，但相关 Package 和执行器仍保留在系统内部。"
                          checked={skillForm.enabled}
                          onChange={() => setSkillForm((current) => ({ ...current, enabled: !current.enabled }))}
                        />

                          <div className="flex flex-wrap gap-2">
                            <Button variant="primary" size="md" onClick={() => void handleSubmitSkillForm()} isLoading={isSkillFormSaving}>
                              保存 Skill 设置
                            </Button>
                          {editingSkillId ? (
                            <Button variant="ghost" size="md" onClick={handleCancelSkillEdit}>
                              放弃修改
                            </Button>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </div>
                </SectionCard>

                <SectionCard
                  id="account"
                  tone="violet"
                  eyebrow="P1 / Workspace"
                  title="账户与工作区"
                  description="账号体系已切到验证码注册申请 + 人工审核开通。这里承载当前账户信息、默认品牌工作区，以及内部管理员进入运营控制台与审核入口。"
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

                      {currentUser?.role === 'internal_admin' ? (
                        <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                          <div className="flex items-center justify-between gap-4">
                            <div>
                              <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>待审核注册申请</div>
                              <div className="mt-1 text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                                当前设置页只展示申请摘要。实际审批、组织归属选择和账号开通统一在运营控制台完成。
                              </div>
                            </div>
                            <div className="flex flex-wrap items-center gap-2">
                              <Link
                                href="/control-plane"
                                className="inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium"
                                style={{
                                  borderColor: 'var(--border-subtle)',
                                  background: 'var(--bg-elevated)',
                                  color: 'var(--text-primary)',
                                }}
                              >
                                进入运营控制台
                              </Link>
                              <Button variant="ghost" size="md" onClick={() => void loadRegistrationApplications()} isLoading={isApplicationsLoading}>
                                刷新
                              </Button>
                            </div>
                          </div>

                          <div className="mt-4 space-y-3">
                            {registrationApplications.length === 0 ? (
                              <div className="rounded-2xl border border-dashed px-4 py-4 text-sm" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                                当前没有待处理注册申请。
                              </div>
                            ) : registrationApplications.map((application) => (
                              <div
                                key={application.id}
                                className="rounded-2xl border px-4 py-4"
                                style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-secondary)' }}
                              >
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                                  <div className="space-y-2">
                                    <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                                      {application.organization_name}
                                    </div>
                                    <div className="text-xs leading-6" style={{ color: 'var(--text-secondary)' }}>
                                      账号：{application.email || application.phone || '--'}<br />
                                      职位：{application.job_title}<br />
                                      申请人：{application.applicant_name || '--'}<br />
                                      状态：{application.status}<br />
                                      提交时间：{formatDateTime(application.created_at)}
                                    </div>
                                  </div>
                                  {application.status === 'pending_review' ? (
                                    <Link
                                      href="/control-plane"
                                      className="inline-flex h-10 items-center rounded-full border px-4 text-sm font-medium"
                                      style={{
                                        borderColor: 'var(--border-subtle)',
                                        background: 'var(--bg-elevated)',
                                        color: 'var(--text-primary)',
                                      }}
                                    >
                                      去运营控制台审核
                                    </Link>
                                  ) : (
                                    <div className="rounded-full px-3 py-1 text-xs" style={{ backgroundColor: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
                                      已处理
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))}
                          </div>
                        </div>
                      ) : null}
                    </div>

                    <div className="rounded-3xl border px-5 py-5" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-tertiary)' }}>
                      <div className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>当前账户状态</div>
                      <div className="mt-4 space-y-3 text-sm" style={{ color: 'var(--text-secondary)' }}>
                        <div className="flex justify-between gap-4"><span>默认品牌</span><span style={{ color: 'var(--text-primary)' }}>{entities.find((entity) => entity.id === workspaceEntityId)?.name || '--'}</span></div>
                        <div className="flex justify-between gap-4"><span>登录账号</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.email || currentUser?.phone || '--'}</span></div>
                        <div className="flex justify-between gap-4"><span>账户状态</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.status || '--'}</span></div>
                        <div className="flex justify-between gap-4"><span>组织归属</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.organization_name || (currentUser?.organization_id ? '已加入组织' : '个人账号')}</span></div>
                        <div className="flex justify-between gap-4"><span>职位信息</span><span style={{ color: 'var(--text-primary)' }}>{currentUser?.job_title || '--'}</span></div>
                      </div>
                      <div className="mt-5 rounded-2xl border border-dashed px-4 py-4 text-xs leading-6" style={{ borderColor: 'var(--border-subtle)', color: 'var(--text-secondary)' }}>
                        当前阶段账号体系已支持验证码登录、人工审核、个人 / 组织空间归属。换绑邮箱、换绑手机号、组织信息编辑与客户列表运营已收口到运营控制台。
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
    </RequireAuth>
  );
}
