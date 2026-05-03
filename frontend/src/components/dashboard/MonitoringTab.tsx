'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { RiCalendar2Line, RiPlayCircleLine } from '@remixicon/react';
import { useMonitoringStore } from '@/stores/monitoringStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { ScheduleStatusCard } from './ScheduleStatusCard';
import { BaselineInfoCard } from './BaselineInfoCard';
import { TrendChart } from './TrendChart';
import { MetricDeltaCard } from './MetricDeltaCard';
import { RunHistoryTable } from './RunHistoryTable';
import { AlertCard } from '../notifications/AlertCard';
import { EmptyState } from '@/components/ui/empty-state';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import type { MonitoringRun, MonitoringTrendGroupBy, UpdateScheduleInput } from '@/types/monitoring';

const STALE_RUN_CUTOFF_MS = Date.now() - 2 * 60 * 60 * 1000;

interface MonitoringTabProps {
  entityId: string | null;
  brandName?: string;
  contextCopy?: string;
}

function MonitoringIssueCard({
  issue,
  onOpenChat,
  onRetry,
  isRetrying,
}: {
  issue: MonitoringRun;
  onOpenChat: (issue: MonitoringRun) => void;
  onRetry: () => void;
  isRetrying?: boolean;
}) {
  const title = issue.status === 'failed' ? '自动监测运行失败' : '自动监测可能卡住';
  const sourceLabel = issue.endpoint_labels?.join('、') || 'AI 来源待确认';
  return (
    <div
      className="rounded-xl px-5 py-4"
      style={{
        background: 'var(--status-error-bg)',
        border: '1px solid color-mix(in srgb, var(--evidence-risk) 22%, var(--border-subtle) 78%)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-xs font-medium" style={{ color: 'var(--evidence-risk)' }}>
            监测异常
          </div>
          <h3 className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {title}
          </h3>
          <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
            阶段：{issue.error_stage || 'monitoring_run'} · {issue.question_count} 个问题 · {sourceLabel}
          </p>
          {issue.error_message && (
            <p className="mt-1 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
              {issue.error_message}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onOpenChat(issue)}
            className="rounded-full border px-4 py-2 text-sm font-medium"
            style={{
              borderColor: 'var(--border-subtle)',
              background: 'var(--bg-secondary)',
              color: 'var(--text-primary)',
            }}
          >
            AI 对话处理
          </button>
          <button
            type="button"
            onClick={onRetry}
            disabled={isRetrying}
            className="rounded-full px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            style={{
              background: 'var(--brand-primary)',
              color: 'white',
            }}
          >
            {isRetrying ? '正在触发' : '重新触发快速复测'}
          </button>
        </div>
      </div>
    </div>
  );
}

export function MonitoringTab({ entityId, brandName, contextCopy }: MonitoringTabProps) {
  const router = useRouter();
  const { selectedBrandId, homeMonitorMode } = useDashboardStore();
  const [trendGroupBy, setTrendGroupBy] = useState<MonitoringTrendGroupBy>('overall');
  const {
    schedule,
    plan,
    questionSets,
    planRuns,
    trendData,
    trendSeries,
    trendSummary,
    metricDeltas,
    alerts,
    runHistory,
    isScheduleLoading,
    isPlanLoading,
    isPlanRunSubmitting,
    isTrendLoading,
    isHistoryLoading,
    fetchSchedule,
    fetchEndpoints,
    fetchPlan,
    fetchQuestionSets,
    fetchTrendData,
    fetchTrendSummary,
    fetchMetricDeltas,
    fetchAlerts,
    fetchRunHistory,
    submitPlanRun,
    pauseSchedule,
    resumeSchedule,
    updateSchedule,
    deleteSchedule,
    clearBaseline,
    reset,
  } = useMonitoringStore();

  const activeEntityId = entityId || selectedBrandId;
  const introCopy =
    contextCopy ||
    `${brandName ? `${brandName} ` : ''}当前监测面板会持续记录品牌提及、官网引用、风险变化和整体走势，便于判断修复动作是否生效。`;

  useEffect(() => {
    if (!activeEntityId) {
      reset();
      return;
    }

    fetchEndpoints();
    fetchSchedule(activeEntityId, homeMonitorMode);
    fetchPlan(activeEntityId, homeMonitorMode);
    fetchQuestionSets(activeEntityId, homeMonitorMode);
    fetchTrendData(activeEntityId, 'mention_rate', homeMonitorMode, trendGroupBy);
    fetchTrendSummary(activeEntityId);
    fetchMetricDeltas(activeEntityId);
    fetchAlerts(activeEntityId);
  }, [activeEntityId, fetchEndpoints, fetchSchedule, fetchPlan, fetchQuestionSets, homeMonitorMode, trendGroupBy, fetchTrendData, fetchTrendSummary, fetchMetricDeltas, fetchAlerts, reset]);

  useEffect(() => {
    if (schedule?.id) {
      fetchRunHistory(schedule.id);
    }
  }, [schedule?.id, fetchRunHistory]);

  const handlePause = useCallback((scheduleId: string) => pauseSchedule(scheduleId), [pauseSchedule]);
  const handleResume = useCallback((scheduleId: string) => resumeSchedule(scheduleId), [resumeSchedule]);
  const handleUpdate = useCallback(
    (scheduleId: string, data: UpdateScheduleInput) => updateSchedule(scheduleId, data),
    [updateSchedule]
  );
  const handleDelete = useCallback((scheduleId: string) => deleteSchedule(scheduleId), [deleteSchedule]);

  const handleDimensionChange = useCallback(
    (dimension: string) => {
      if (activeEntityId) {
        fetchTrendData(activeEntityId, dimension, homeMonitorMode, trendGroupBy);
        fetchTrendSummary(activeEntityId, dimension);
      }
    },
    [activeEntityId, fetchTrendData, fetchTrendSummary, homeMonitorMode, trendGroupBy]
  );

  const handleTrendGroupByChange = useCallback(
    (groupBy: MonitoringTrendGroupBy, dimension: string = 'mention_rate') => {
      setTrendGroupBy(groupBy);
      if (activeEntityId) {
        fetchTrendData(activeEntityId, dimension, homeMonitorMode, groupBy);
      }
    },
    [activeEntityId, fetchTrendData, homeMonitorMode],
  );

  const handleAlertClick = useCallback(() => {
    // Already in monitoring context.
  }, []);

  const scheduleId = schedule?.id;
  const handleClearBaseline = useCallback(async () => {
    if (scheduleId) {
      await clearBaseline(scheduleId);
    }
  }, [scheduleId, clearBaseline]);

  const handleStartChat = useCallback(async () => {
    if (!activeEntityId) {
      router.push('/dashboard');
      return;
    }
    try {
      const session = await api.getOrCreateSessionByEntity(activeEntityId);
      const params = new URLSearchParams();
      params.set('entity_id', activeEntityId);
      if (brandName) params.set('brand', brandName);
      params.set('entry_source', 'dashboard_monitoring_tab');
      params.set(
        'monitor_mode',
        homeMonitorMode === 'scenario' ? 'scenario_monitoring' : 'panorama_monitoring',
      );
      if (plan?.id) params.set('monitoring_plan_id', plan.id);
      if (plan?.question_set_ids?.length) {
        params.set('question_set_ids', plan.question_set_ids.join(','));
      }
      params.set(
        'draft',
        `${brandName ? `请基于「${brandName}」` : '请'}继续完善${homeMonitorMode === 'scenario' ? '用户场景监测' : '全景监测'}计划。`,
      );
      params.set('autosend', '1');
      router.push(`/chat/${session.id}?${params.toString()}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开 AI 对话失败，请稍后重试。');
    }
  }, [activeEntityId, brandName, homeMonitorMode, plan, router]);

  const handleOpenIssueChat = useCallback(async (issue: MonitoringRun) => {
    if (!activeEntityId) return;
    try {
      const session = await api.getOrCreateSessionByEntity(activeEntityId);
      const params = new URLSearchParams();
      params.set('entity_id', activeEntityId);
      if (brandName) params.set('brand', brandName);
      params.set('entry_source', 'dashboard_monitoring_issue');
      params.set(
        'monitor_mode',
        homeMonitorMode === 'scenario' ? 'scenario_monitoring' : 'panorama_monitoring',
      );
      params.set('monitoring_run_id', issue.id);
      params.set('monitoring_plan_id', issue.plan_id);
      if (issue.error_stage) params.set('error_stage', issue.error_stage);
      if (issue.error_message) params.set('error_message', issue.error_message);
      if (issue.endpoint_ids?.length) params.set('endpoint_ids', issue.endpoint_ids.join(','));
      if (issue.question_set_ids?.length) params.set('question_set_ids', issue.question_set_ids.join(','));
      params.set(
        'draft',
        `${brandName ? `请基于「${brandName}」` : '请'}处理这次自动监测异常：${issue.error_stage || 'monitoring_run'}，${issue.error_message || '请读取监测运行记录后说明原因。'}`,
      );
      params.set('autosend', '1');
      router.push(`/chat/${session.id}?${params.toString()}`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开 AI 对话失败，请稍后重试。');
    }
  }, [activeEntityId, brandName, homeMonitorMode, router]);

  const handleSubmitPlanRun = useCallback(async () => {
    if (!plan?.id) return;
    await submitPlanRun(plan.id);
  }, [plan, submitPlanRun]);

  const recentIssue = useMemo(
    () => {
      const failed = planRuns.find((run) => run.status === 'failed');
      if (failed) return failed;
      return (
        planRuns.find((run) => {
          if (run.status !== 'pending' && run.status !== 'running') return false;
          const time = Date.parse(run.updated_at || run.created_at || '');
          return Number.isFinite(time) && time < STALE_RUN_CUTOFF_MS;
        }) || null
      );
    },
    [planRuns],
  );

  const latestQuestionSet = questionSets[0];
  const planStatusLabel = plan?.status === 'active' ? '已启用' : plan?.status === 'paused' ? '已暂停' : '草稿';
  const planModeLabel = homeMonitorMode === 'scenario' ? '用户场景监测' : '全景监测';
  const planCard = plan ? (
    <div
      className="rounded-xl px-5 py-4"
      style={{
        background: 'var(--bg-tertiary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="text-xs font-medium" style={{ color: 'var(--text-tertiary)' }}>
            Monitoring Plan
          </div>
          <h3 className="mt-1 text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
            {plan.title || `${brandName || '当前品牌'} ${planModeLabel}`}
          </h3>
          <p className="mt-2 text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
            {plan.question_count} 个问题 · {plan.endpoint_labels.join('、') || '待选择 AI 来源'} · {planStatusLabel}
          </p>
        </div>
        <button
          type="button"
          onClick={handleSubmitPlanRun}
          disabled={plan.status !== 'active' || isPlanRunSubmitting}
          className="inline-flex items-center gap-2 rounded-full px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
          style={{
            background: 'var(--brand-primary)',
            color: 'white',
          }}
        >
          <RiPlayCircleLine className="h-4 w-4" />
          {isPlanRunSubmitting ? '正在触发' : '触发快速复测'}
        </button>
      </div>
    </div>
  ) : null;

  if (isScheduleLoading || isPlanLoading) {
    return (
      <div className="space-y-4">
        <div className="h-20 rounded-xl animate-shimmer" />
        <div className="h-80 rounded-xl animate-shimmer" />
        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="h-24 rounded-xl animate-shimmer" />
          ))}
        </div>
      </div>
    );
  }

  if (!schedule && !plan) {
    return (
      <EmptyState
        icon={RiCalendar2Line}
        title={`尚未建立${planModeLabel}`}
        description="需要先通过 AI 对话完成品牌信息、问题集和 AI 来源确认。确认后才能启用自动监测。"
        action={{
          label: `AI 对话建立${planModeLabel}`,
          onClick: () => {
            void handleStartChat();
          },
        }}
      />
    );
  }

  if (!schedule && plan) {
    return (
      <div className="space-y-5">
        {planCard}
        {recentIssue && (
          <MonitoringIssueCard
            issue={recentIssue}
            onOpenChat={handleOpenIssueChat}
            onRetry={handleSubmitPlanRun}
            isRetrying={isPlanRunSubmitting}
          />
        )}
        <EmptyState
          icon={RiCalendar2Line}
          title="监测计划已建立，等待首次运行"
          description={latestQuestionSet ? `最近问题集：${latestQuestionSet.title}` : '可以先触发一次快速复测，生成新的 A5 完整报告。'}
          action={{
            label: 'AI 对话调整计划',
            onClick: () => {
              void handleStartChat();
            },
          }}
        />
      </div>
    );
  }
  if (!schedule) {
    return null;
  }

  return (
    <div className="space-y-6">
      <div
        className="rounded-xl px-5 py-4"
        style={{
          background: 'color-mix(in srgb, var(--brand-primary) 8%, var(--bg-elevated) 92%)',
          border: '1px solid var(--border-subtle)',
        }}
      >
        <div className="mb-1 text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          持续跟踪
        </div>
        <p className="text-sm leading-6" style={{ color: 'var(--text-secondary)' }}>
          {introCopy}
        </p>
      </div>

      <ScheduleStatusCard
        schedule={schedule}
        onPause={handlePause}
        onResume={handleResume}
        onUpdate={handleUpdate}
        onDelete={handleDelete}
      />

      {planCard}

      {recentIssue && (
        <MonitoringIssueCard
          issue={recentIssue}
          onOpenChat={handleOpenIssueChat}
          onRetry={handleSubmitPlanRun}
          isRetrying={isPlanRunSubmitting}
        />
      )}

      <BaselineInfoCard
        hasBaseline={schedule.has_baseline}
        baselineSummary={schedule.baseline_summary}
        totalRuns={schedule.total_runs}
        onClearBaseline={handleClearBaseline}
      />

      <TrendChart
        data={trendData}
        series={trendSeries}
        groupBy={trendGroupBy}
        summary={trendSummary}
        isLoading={isTrendLoading}
        onDimensionChange={handleDimensionChange}
        onGroupByChange={handleTrendGroupByChange}
      />

      {metricDeltas.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {metricDeltas.map((metric) => (
            <MetricDeltaCard key={metric.metric_key} metric={metric} />
          ))}
        </div>
      )}

      {alerts.length > 0 && (
        <div
          className="overflow-hidden rounded-xl"
          style={{
            background: 'var(--bg-tertiary)',
            border: '1px solid var(--border-subtle)',
          }}
        >
          <div className="px-4 py-3">
            <h3 className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              最近告警
            </h3>
          </div>
          <div>
            {alerts.slice(0, 3).map((alert) => (
              <AlertCard key={alert.id} alert={alert} onClick={handleAlertClick} />
            ))}
          </div>
        </div>
      )}

      <RunHistoryTable entries={runHistory} isLoading={isHistoryLoading} />
    </div>
  );
}
