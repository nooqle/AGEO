import { create } from 'zustand';
import type {
  MonitoringSchedule,
  BaselineData,
  TrendDataPoint,
  TrendSummary,
  MetricDelta,
  MonitoringAlert,
  RunHistoryEntry,
  UpdateScheduleInput,
  TrendMetricSummary,
  MonitoringEndpoint,
  MonitoringPlan,
  MonitoringQuestionSet,
  MonitoringRun,
  MonitoringTrendGroupBy,
  MonitoringTrendSeries,
} from '@/types/monitoring';
import { api } from '@/services/api';

/** Map UI dimension keys to backend metric names used by /analytics/trend */
const DIMENSION_TO_METRIC: Record<string, string> = {
  bwvs: 'bwvs_index',
  bwvs_index: 'bwvs_index',
  mention_rate: 'mention_rate',
  sentiment: 'sentiment_score',
  sentiment_score: 'sentiment_score',
  coverage: 'coverage_score',
  coverage_score: 'coverage_score',
  citation: 'content_citation_rate',
  content_citation_rate: 'content_citation_rate',
};

const DISPLAY_METRIC_ORDER = [
  'bwvs_index',
  'mention_rate',
  'sentiment_score',
  'coverage_score',
  'content_citation_rate',
] as const;

/** Map metric names to display labels for MetricDelta cards */
const METRIC_LABELS: Record<string, string> = {
  bwvs_index: '品牌可见度',
  mention_rate: '提及率',
  sentiment_score: '情感倾向',
  coverage_score: '平台覆盖',
  content_citation_rate: '内容引用率',
};

/** Convert a TrendMetricSummary to a MetricDelta for UI rendering */
function summaryToMetricDelta(name: string, s: TrendMetricSummary): MetricDelta {
  const prev = s.period_delta
    ? (s.current_value ?? 0) - s.period_delta.absolute
    : null;
  return {
    metric_key: name,
    label: METRIC_LABELS[name] ?? name,
    current_value: s.current_value,
    previous_value: prev,
    delta: s.period_delta?.absolute ?? null,
    delta_percent: s.period_delta?.percentage ?? null,
    direction: s.direction,
    sparkline_data: [],
  };
}

/** Convert a TrendMetricSummary to a flattened TrendSummary for UI */
function summaryToTrendSummary(s: TrendMetricSummary): TrendSummary {
  const prev = s.period_delta
    ? (s.current_value ?? 0) - s.period_delta.absolute
    : null;
  return {
    direction: s.direction,
    current_value: s.current_value,
    previous_value: prev,
    change_absolute: s.period_delta?.absolute ?? null,
    change_percentage: s.period_delta?.percentage ?? null,
    data_point_count: s.data_points,
    period_label: `${s.time_range_days}天`,
  };
}

interface MonitoringState {
  // Data
  schedule: MonitoringSchedule | null;
  baseline: BaselineData | null;
  trendData: TrendDataPoint[];
  trendSummary: TrendSummary | null;
  metricDeltas: MetricDelta[];
  alerts: MonitoringAlert[];
  runHistory: RunHistoryEntry[];
  endpoints: MonitoringEndpoint[];
  plan: MonitoringPlan | null;
  questionSets: MonitoringQuestionSet[];
  planRuns: MonitoringRun[];
  trendGroupBy: MonitoringTrendGroupBy;
  trendSeries: MonitoringTrendSeries[];

  // Loading states
  isLoading: boolean;
  isTrendLoading: boolean;
  isScheduleLoading: boolean;
  isHistoryLoading: boolean;
  isBaselineLoading: boolean;
  isPlanLoading: boolean;
  isPlanRunSubmitting: boolean;

  // Error
  error: string | null;

  // Actions — Schedule
  fetchSchedule: (entityId: string, monitorMode?: 'panorama' | 'scenario') => Promise<void>;
  pauseSchedule: (scheduleId: string) => Promise<void>;
  resumeSchedule: (scheduleId: string) => Promise<void>;
  updateSchedule: (scheduleId: string, data: UpdateScheduleInput) => Promise<void>;
  deleteSchedule: (scheduleId: string) => Promise<boolean>;

  // Actions — Baseline
  fetchBaseline: (scheduleId: string) => Promise<void>;
  clearBaseline: (scheduleId: string) => Promise<void>;

  // Actions — Trend Data
  fetchTrendData: (
    entityId: string,
    dimension?: string,
    monitorMode?: 'panorama' | 'scenario',
    groupBy?: MonitoringTrendGroupBy,
  ) => Promise<void>;
  fetchTrendSummary: (entityId: string, dimension?: string) => Promise<void>;
  fetchMetricDeltas: (entityId: string) => Promise<void>;

  // Actions — Alerts & History
  fetchAlerts: (entityId: string, limit?: number) => Promise<void>;
  fetchRunHistory: (scheduleId: string, limit?: number) => Promise<void>;
  fetchEndpoints: () => Promise<void>;
  fetchPlan: (entityId: string, monitorMode?: 'panorama' | 'scenario') => Promise<void>;
  fetchQuestionSets: (entityId: string, monitorMode?: 'panorama' | 'scenario') => Promise<void>;
  submitPlanRun: (planId: string) => Promise<void>;

  // Actions — Reset
  reset: () => void;
}

const initialState = {
  schedule: null,
  baseline: null,
  trendData: [],
  trendSummary: null,
  metricDeltas: [],
  alerts: [],
  runHistory: [],
  endpoints: [],
  plan: null,
  questionSets: [],
  planRuns: [],
  trendGroupBy: 'overall' as MonitoringTrendGroupBy,
  trendSeries: [],
  isLoading: false,
  isTrendLoading: false,
  isScheduleLoading: false,
  isHistoryLoading: false,
  isBaselineLoading: false,
  isPlanLoading: false,
  isPlanRunSubmitting: false,
  error: null,
};

export const useMonitoringStore = create<MonitoringState>((set, get) => ({
  ...initialState,

  // =========================================================================
  // Schedule Actions
  // =========================================================================

  fetchSchedule: async (entityId: string, monitorMode?: 'panorama' | 'scenario') => {
    set({ isScheduleLoading: true, error: null });
    try {
      const schedule = await api.getEntitySchedule(entityId, monitorMode);
      set({ schedule, isScheduleLoading: false });
    } catch {
      // No schedule found — this is normal for entities without monitoring
      set({ schedule: null, isScheduleLoading: false });
    }
  },

  pauseSchedule: async (scheduleId: string) => {
    try {
      const updated = await api.pauseSchedule(scheduleId);
      const currentPlan = get().plan;
      let plan = currentPlan;
      if (currentPlan?.id && currentPlan.id === updated.monitoring_plan_id) {
        plan = await api.pauseMonitoringPlan(currentPlan.id).catch(() => currentPlan);
      }
      set({ schedule: updated, plan });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '暂停监测失败' });
    }
  },

  resumeSchedule: async (scheduleId: string) => {
    try {
      const updated = await api.resumeSchedule(scheduleId);
      const currentPlan = get().plan;
      let plan = currentPlan;
      if (currentPlan?.id && currentPlan.id === updated.monitoring_plan_id) {
        plan = await api.activateMonitoringPlan(currentPlan.id).catch(() => currentPlan);
      }
      set({ schedule: updated, plan });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '恢复监测失败' });
    }
  },

  updateSchedule: async (scheduleId: string, data: UpdateScheduleInput) => {
    try {
      const updated = await api.updateSchedule(scheduleId, data);
      const currentPlan = get().plan;
      const planUpdate: Parameters<typeof api.updateMonitoringPlan>[1] = {};
      if (data.frequency !== undefined) planUpdate.frequency = data.frequency;
      if (data.preferred_hour !== undefined) planUpdate.preferred_hour = data.preferred_hour;
      if (data.timezone !== undefined) planUpdate.timezone = data.timezone;
      if (data.status === 'active' || data.status === 'paused') planUpdate.status = data.status;
      let plan = currentPlan;
      if (currentPlan?.id === updated.monitoring_plan_id && Object.keys(planUpdate).length > 0) {
        plan = await api.updateMonitoringPlan(currentPlan.id, planUpdate).catch(() => currentPlan);
      }
      set({ schedule: updated, plan });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '更新监测设置失败' });
    }
  },

  deleteSchedule: async (scheduleId: string) => {
    try {
      const currentPlan = get().plan;
      const currentSchedule = get().schedule;
      await api.deleteSchedule(scheduleId);
      if (currentPlan?.id && currentPlan.id === currentSchedule?.monitoring_plan_id) {
        await api.archiveMonitoringPlan(currentPlan.id).catch(() => null);
      }
      set({ schedule: null, plan: null });
      return true;
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '删除监测失败' });
      return false;
    }
  },

  // =========================================================================
  // Baseline Actions
  // =========================================================================

  fetchBaseline: async (scheduleId: string) => {
    set({ isBaselineLoading: true });
    try {
      const resp = await api.getScheduleBaseline(scheduleId);
      set({ baseline: resp.baseline, isBaselineLoading: false });
    } catch {
      set({ baseline: null, isBaselineLoading: false });
    }
  },

  clearBaseline: async (scheduleId: string) => {
    try {
      await api.clearScheduleBaseline(scheduleId);
      set((state) => ({
        baseline: null,
        schedule: state.schedule
          ? { ...state.schedule, has_baseline: false, baseline_summary: null }
          : null,
      }));
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '重置基线失败' });
    }
  },

  // =========================================================================
  // Trend Data Actions
  // =========================================================================

  fetchTrendData: async (
    entityId: string,
    dimension = 'mention_rate',
    monitorMode: 'panorama' | 'scenario' = 'panorama',
    groupBy: MonitoringTrendGroupBy = 'overall',
  ) => {
    set({ isTrendLoading: true });
    try {
      const metric = DIMENSION_TO_METRIC[dimension] ?? 'mention_rate';
      const result = await api.getMonitoringTrendsV2({
        entityId,
        metric,
        monitorMode,
        groupBy,
      });
      const primarySeries = result.series[0];
      const trendData = primarySeries
        ? primarySeries.points.map((point) => ({
            date: point.date,
            value: point.value,
            snapshot_id: point.snapshot_id || '',
            run_id: point.run_id || null,
            triggered_by: result.group_by,
            is_significant: false,
            data_point_count: point.data_point_count,
          }))
        : [];
      const trendSummary: TrendSummary | null = primarySeries
        ? {
            direction: primarySeries.direction,
            current_value: primarySeries.current_value,
            previous_value: primarySeries.previous_value,
            change_absolute: primarySeries.change_absolute,
            change_percentage: primarySeries.change_percentage,
            data_point_count: primarySeries.data_point_count,
            period_label: result.period_label,
          }
        : null;
      set({
        trendData,
        trendSeries: result.series,
        trendGroupBy: result.group_by,
        trendSummary,
        isTrendLoading: false,
      });
    } catch {
      set({ trendData: [], trendSeries: [], trendSummary: null, isTrendLoading: false });
    }
  },

  fetchTrendSummary: async (entityId: string, dimension = 'mention_rate') => {
    try {
      const metric = DIMENSION_TO_METRIC[dimension] ?? 'mention_rate';
      const resp = await api.getMonitoringTrendSummary(entityId);
      const metricSummary = resp.summaries[metric];
      if (metricSummary) {
        set({ trendSummary: summaryToTrendSummary(metricSummary) });
      } else {
        set({ trendSummary: null });
      }
    } catch {
      set({ trendSummary: null });
    }
  },

  fetchMetricDeltas: async (entityId: string) => {
    try {
      // Derive metric deltas from trend summary (no separate backend endpoint)
      const resp = await api.getMonitoringTrendSummary(entityId);
      const deltas: MetricDelta[] = DISPLAY_METRIC_ORDER
        .map((metricKey) => {
          const summary = resp.summaries[metricKey];
          return summary ? summaryToMetricDelta(metricKey, summary) : null;
        })
        .filter((item): item is MetricDelta => item != null);

      // Fetch sparkline data (last 5 data points) for each metric in parallel
      const sparklinePromises = deltas.map(async (delta) => {
        try {
          const trendResp = await api.getMonitoringTrend(entityId, delta.metric_key, 5);
          const points = trendResp.trend
            .map((p) => p.value)
            .filter((v): v is number => v != null);
          return { ...delta, sparkline_data: points };
        } catch {
          // Graceful degradation: keep empty sparkline on failure
          return delta;
        }
      });
      const deltasWithSparklines = await Promise.all(sparklinePromises);

      set({ metricDeltas: deltasWithSparklines });
    } catch {
      set({ metricDeltas: [] });
    }
  },

  // =========================================================================
  // Alerts & History Actions
  // =========================================================================

  fetchAlerts: async (entityId: string, limit = 5) => {
    try {
      const result = await api.getMonitoringAlerts({ entityId, limit });
      set({ alerts: result.alerts });
    } catch {
      set({ alerts: [] });
    }
  },

  fetchRunHistory: async (scheduleId: string, limit = 20) => {
    set({ isHistoryLoading: true });
    try {
      const result = await api.getMonitoringRunHistory(scheduleId, limit);
      set({ runHistory: result.tasks, isHistoryLoading: false });
    } catch {
      set({ runHistory: [], isHistoryLoading: false });
    }
  },

  fetchEndpoints: async () => {
    try {
      const result = await api.getMonitoringEndpoints();
      set({ endpoints: result.endpoints });
    } catch {
      set({ endpoints: [] });
    }
  },

  fetchPlan: async (entityId: string, monitorMode: 'panorama' | 'scenario' = 'panorama') => {
    set({ isPlanLoading: true });
    try {
      const plan = await api.getEntityMonitoringPlan(entityId, monitorMode);
      const runs = plan ? await api.listMonitoringPlanRuns(plan.id, 10).catch(() => ({ runs: [] })) : { runs: [] };
      set({ plan, planRuns: runs.runs, isPlanLoading: false });
    } catch {
      set({ plan: null, planRuns: [], isPlanLoading: false });
    }
  },

  fetchQuestionSets: async (entityId: string, monitorMode: 'panorama' | 'scenario' = 'panorama') => {
    try {
      const result = await api.listMonitoringQuestionSets({
        entityId,
        monitorMode,
        limit: 20,
      });
      set({ questionSets: result.question_sets });
    } catch {
      set({ questionSets: [] });
    }
  },

  submitPlanRun: async (planId: string) => {
    set({ isPlanRunSubmitting: true, error: null });
    try {
      const run = await api.submitMonitoringPlanRun(planId);
      set((state) => ({
        isPlanRunSubmitting: false,
        planRuns: [run, ...state.planRuns.filter((item) => item.id !== run.id)],
      }));
    } catch (err) {
      set({
        isPlanRunSubmitting: false,
        error: err instanceof Error ? err.message : '触发快速复测失败',
      });
    }
  },

  // =========================================================================
  // Reset
  // =========================================================================

  reset: () => set(initialState),
}));
