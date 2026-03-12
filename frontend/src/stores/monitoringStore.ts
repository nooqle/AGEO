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
  citation: 'citation_score',
  citation_score: 'citation_score',
};

/** Map metric names to display labels for MetricDelta cards */
const METRIC_LABELS: Record<string, string> = {
  bwvs_index: '品牌可见度',
  mention_rate: '提及率',
  sentiment_score: '情感倾向',
  coverage_score: '平台覆盖',
  citation_score: '引用质量',
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

  // Loading states
  isLoading: boolean;
  isTrendLoading: boolean;
  isScheduleLoading: boolean;
  isHistoryLoading: boolean;
  isBaselineLoading: boolean;

  // Error
  error: string | null;

  // Actions — Schedule
  fetchSchedule: (entityId: string) => Promise<void>;
  pauseSchedule: (scheduleId: string) => Promise<void>;
  resumeSchedule: (scheduleId: string) => Promise<void>;
  updateSchedule: (scheduleId: string, data: UpdateScheduleInput) => Promise<void>;
  deleteSchedule: (scheduleId: string) => Promise<boolean>;

  // Actions — Baseline
  fetchBaseline: (scheduleId: string) => Promise<void>;
  clearBaseline: (scheduleId: string) => Promise<void>;

  // Actions — Trend Data
  fetchTrendData: (entityId: string, dimension?: string) => Promise<void>;
  fetchTrendSummary: (entityId: string, dimension?: string) => Promise<void>;
  fetchMetricDeltas: (entityId: string) => Promise<void>;

  // Actions — Alerts & History
  fetchAlerts: (entityId: string, limit?: number) => Promise<void>;
  fetchRunHistory: (scheduleId: string, limit?: number) => Promise<void>;

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
  isLoading: false,
  isTrendLoading: false,
  isScheduleLoading: false,
  isHistoryLoading: false,
  isBaselineLoading: false,
  error: null,
};

export const useMonitoringStore = create<MonitoringState>((set) => ({
  ...initialState,

  // =========================================================================
  // Schedule Actions
  // =========================================================================

  fetchSchedule: async (entityId: string) => {
    set({ isScheduleLoading: true, error: null });
    try {
      const schedule = await api.getEntitySchedule(entityId);
      set({ schedule, isScheduleLoading: false });
    } catch {
      // No schedule found — this is normal for entities without monitoring
      set({ schedule: null, isScheduleLoading: false });
    }
  },

  pauseSchedule: async (scheduleId: string) => {
    try {
      const updated = await api.pauseSchedule(scheduleId);
      set({ schedule: updated });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '暂停监测失败' });
    }
  },

  resumeSchedule: async (scheduleId: string) => {
    try {
      const updated = await api.resumeSchedule(scheduleId);
      set({ schedule: updated });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '恢复监测失败' });
    }
  },

  updateSchedule: async (scheduleId: string, data: UpdateScheduleInput) => {
    try {
      const updated = await api.updateSchedule(scheduleId, data);
      set({ schedule: updated });
    } catch (err) {
      set({ error: err instanceof Error ? err.message : '更新监测设置失败' });
    }
  },

  deleteSchedule: async (scheduleId: string) => {
    try {
      await api.deleteSchedule(scheduleId);
      set({ schedule: null });
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

  fetchTrendData: async (entityId: string, dimension = 'mention_rate') => {
    set({ isTrendLoading: true });
    try {
      const metric = DIMENSION_TO_METRIC[dimension] ?? 'mention_rate';
      const result = await api.getMonitoringTrend(entityId, metric);
      set({ trendData: result.trend, isTrendLoading: false });
    } catch {
      set({ trendData: [], isTrendLoading: false });
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
      const deltas: MetricDelta[] = Object.entries(resp.summaries).map(
        ([name, s]) => summaryToMetricDelta(name, s)
      );

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

  // =========================================================================
  // Reset
  // =========================================================================

  reset: () => set(initialState),
}));
