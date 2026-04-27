'use client';

import { useCallback, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { RiCalendar2Line } from '@remixicon/react';
import { useMonitoringStore } from '@/stores/monitoringStore';
import { useDashboardStore } from '@/stores/dashboardStore';
import { ScheduleStatusCard } from './ScheduleStatusCard';
import { BaselineInfoCard } from './BaselineInfoCard';
import { TrendChart } from './TrendChart';
import { MetricDeltaCard } from './MetricDeltaCard';
import { RunHistoryTable } from './RunHistoryTable';
import { AlertCard } from '../notifications/AlertCard';
import { EmptyState } from '@/components/ui/empty-state';
import type { UpdateScheduleInput } from '@/types/monitoring';

interface MonitoringTabProps {
  entityId: string | null;
  brandName?: string;
  contextCopy?: string;
}

export function MonitoringTab({ entityId, brandName, contextCopy }: MonitoringTabProps) {
  const router = useRouter();
  const { selectedBrandId } = useDashboardStore();
  const {
    schedule,
    trendData,
    trendSummary,
    metricDeltas,
    alerts,
    runHistory,
    isScheduleLoading,
    isTrendLoading,
    isHistoryLoading,
    fetchSchedule,
    fetchTrendData,
    fetchTrendSummary,
    fetchMetricDeltas,
    fetchAlerts,
    fetchRunHistory,
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

    fetchSchedule(activeEntityId);
    fetchTrendData(activeEntityId);
    fetchTrendSummary(activeEntityId);
    fetchMetricDeltas(activeEntityId);
    fetchAlerts(activeEntityId);
  }, [activeEntityId, fetchSchedule, fetchTrendData, fetchTrendSummary, fetchMetricDeltas, fetchAlerts, reset]);

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
        fetchTrendData(activeEntityId, dimension);
        fetchTrendSummary(activeEntityId, dimension);
      }
    },
    [activeEntityId, fetchTrendData, fetchTrendSummary]
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
      router.push('/settings?section=monitoring');
      return;
    }
    router.push(`/settings?section=monitoring&entity_id=${encodeURIComponent(activeEntityId)}`);
  }, [activeEntityId, router]);

  if (isScheduleLoading) {
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

  if (!schedule) {
    return (
      <EmptyState
        icon={RiCalendar2Line}
        title="尚未启用全景自动监测"
        description="先在设置页配置监测频率和平台，再按固定节奏重跑全景问题并生成新的全景分析报告。"
        action={{
          label: '进入监测设置',
          onClick: () => {
            void handleStartChat();
          },
        }}
      />
    );
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

      <BaselineInfoCard
        hasBaseline={schedule.has_baseline}
        baselineSummary={schedule.baseline_summary}
        totalRuns={schedule.total_runs}
        onClearBaseline={handleClearBaseline}
      />

      <TrendChart
        data={trendData}
        summary={trendSummary}
        isLoading={isTrendLoading}
        onDimensionChange={handleDimensionChange}
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
