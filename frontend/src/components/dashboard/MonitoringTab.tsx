'use client';

import { useEffect, useCallback } from 'react';
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
import type { MonitoringAlert, UpdateScheduleInput } from '@/types/monitoring';

// =========================================================================
// MonitoringTab Component
// =========================================================================

interface MonitoringTabProps {
  entityId: string | null;
}

export function MonitoringTab({ entityId }: MonitoringTabProps) {
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

  // Fetch all monitoring data when entity changes
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

  // Fetch run history when schedule changes
  useEffect(() => {
    if (schedule?.id) {
      fetchRunHistory(schedule.id);
    }
  }, [schedule?.id, fetchRunHistory]);

  // Handlers
  const handlePause = useCallback(
    (scheduleId: string) => pauseSchedule(scheduleId),
    [pauseSchedule]
  );

  const handleResume = useCallback(
    (scheduleId: string) => resumeSchedule(scheduleId),
    [resumeSchedule]
  );

  const handleUpdate = useCallback(
    (scheduleId: string, data: UpdateScheduleInput) => updateSchedule(scheduleId, data),
    [updateSchedule]
  );

  const handleDelete = useCallback(
    (scheduleId: string) => deleteSchedule(scheduleId),
    [deleteSchedule]
  );

  const handleDimensionChange = useCallback(
    (dimension: string) => {
      if (activeEntityId) {
        fetchTrendData(activeEntityId, dimension);
        fetchTrendSummary(activeEntityId, dimension);
      }
    },
    [activeEntityId, fetchTrendData, fetchTrendSummary]
  );

  const handleAlertClick = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    (_alert: MonitoringAlert) => {
      // Already on the monitoring tab, no navigation needed
    },
    []
  );

  const scheduleId = schedule?.id;
  const handleClearBaseline = useCallback(async () => {
    if (scheduleId) {
      await clearBaseline(scheduleId);
    }
  }, [scheduleId, clearBaseline]);

  const handleStartChat = useCallback(() => {
    router.push('/dashboard');
  }, [router]);

  // =========================================================================
  // Loading State
  // =========================================================================

  if (isScheduleLoading) {
    return (
      <div className="space-y-4">
        <div className="h-20 rounded-xl animate-shimmer" />
        <div className="h-80 rounded-xl animate-shimmer" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-24 rounded-xl animate-shimmer" />
          ))}
        </div>
      </div>
    );
  }

  // =========================================================================
  // Empty State — no schedule configured
  // =========================================================================

  if (!schedule) {
    return (
      <EmptyState
        icon={RiCalendar2Line}
        title="尚未设置自动监测"
        description="通过对话设置品牌的自动监测计划，定期跟踪 BWVS 分数和品牌可见度变化。"
        action={{
          label: '进入对话设置',
          onClick: handleStartChat,
        }}
      />
    );
  }

  // =========================================================================
  // Full Monitoring Dashboard
  // =========================================================================

  return (
    <div className="space-y-6">
      {/* 1. Schedule Status Card (full width) */}
      <ScheduleStatusCard
        schedule={schedule}
        onPause={handlePause}
        onResume={handleResume}
        onUpdate={handleUpdate}
        onDelete={handleDelete}
      />

      {/* 1.5. Baseline Info Card */}
      <BaselineInfoCard
        hasBaseline={schedule.has_baseline}
        baselineSummary={schedule.baseline_summary}
        totalRuns={schedule.total_runs}
        onClearBaseline={handleClearBaseline}
      />

      {/* 2. Trend Chart (full width) */}
      <TrendChart
        data={trendData}
        summary={trendSummary}
        isLoading={isTrendLoading}
        onDimensionChange={handleDimensionChange}
      />

      {/* 3. Metric Delta Cards (2x2 grid, responsive) */}
      {metricDeltas.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {metricDeltas.map((metric) => (
            <MetricDeltaCard key={metric.metric_key} metric={metric} />
          ))}
        </div>
      )}

      {/* 4. Recent Alerts (max 3) */}
      {alerts.length > 0 && (
        <div
          className="rounded-xl overflow-hidden"
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
              <AlertCard
                key={alert.id}
                alert={alert}
                onClick={handleAlertClick}
              />
            ))}
          </div>
        </div>
      )}

      {/* 5. Run History Table */}
      <RunHistoryTable
        entries={runHistory}
        isLoading={isHistoryLoading}
      />
    </div>
  );
}
