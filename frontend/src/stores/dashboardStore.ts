import { create } from 'zustand';
import type { DashboardData } from '@/types/dashboard';
import { api } from '@/services/api';

type DashboardDateRange = 'week' | 'month' | 'quarter';

function buildCacheKey(
  selectedBrandId: string | null,
  dateRange: DashboardDateRange,
): string {
  return `${selectedBrandId ?? 'all'}:${dateRange}`;
}

let activeDashboardRequestController: AbortController | null = null;

interface DashboardState {
  data: DashboardData | null;
  isLoading: boolean;
  error: string | null;
  selectedBrandId: string | null;
  dateRange: DashboardDateRange;
  cache: Record<string, DashboardData>;
  activeRequestId: number;

  setData: (data: DashboardData) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedBrandId: (id: string | null) => void;
  setDateRange: (range: DashboardDateRange) => void;
  fetchData: () => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  data: null,
  isLoading: false,
  error: null,
  selectedBrandId: null,
  dateRange: 'month',
  cache: {},
  activeRequestId: 0,

  setData: (data) =>
    set((state) => {
      const cacheKey = buildCacheKey(state.selectedBrandId, state.dateRange);
      return {
        data,
        isLoading: false,
        error: null,
        cache: {
          ...state.cache,
          [cacheKey]: data,
        },
      };
    }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error, isLoading: false }),
  setSelectedBrandId: (selectedBrandId) =>
    set((state) => {
      const cacheKey = buildCacheKey(selectedBrandId, state.dateRange);
      return {
        selectedBrandId,
        data: state.cache[cacheKey] ?? null,
        error: null,
      };
    }),
  setDateRange: (dateRange) =>
    set((state) => {
      const cacheKey = buildCacheKey(state.selectedBrandId, dateRange);
      return {
        dateRange,
        data: state.cache[cacheKey] ?? null,
        error: null,
      };
    }),

  fetchData: async () => {
    const { selectedBrandId, dateRange, cache, activeRequestId } = get();
    const cacheKey = buildCacheKey(selectedBrandId, dateRange);
    const requestId = activeRequestId + 1;
    const cachedData = cache[cacheKey] ?? null;
    activeDashboardRequestController?.abort();
    const controller = new AbortController();
    activeDashboardRequestController = controller;
    set({
      activeRequestId: requestId,
      isLoading: true,
      error: null,
      data: cachedData,
    });
    try {
      const data = await api.getAnalyticsAll(
        selectedBrandId || undefined,
        dateRange,
        { signal: controller.signal },
      );
      const latest = get();
      if (
        activeDashboardRequestController !== controller ||
        latest.activeRequestId !== requestId ||
        latest.selectedBrandId !== selectedBrandId ||
        latest.dateRange !== dateRange
      ) {
        return;
      }
      activeDashboardRequestController = null;
      set((state) => ({
        data,
        isLoading: false,
        error: null,
        cache: {
          ...state.cache,
          [cacheKey]: data,
        },
      }));
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      const latest = get();
      if (
        activeDashboardRequestController !== controller ||
        latest.activeRequestId !== requestId
      ) {
        return;
      }
      activeDashboardRequestController = null;
      set({
        error: err instanceof Error ? err.message : 'Failed to load analytics',
        isLoading: false,
      });
    }
  },

  reset: () => {
    activeDashboardRequestController?.abort();
    activeDashboardRequestController = null;
    set({
      data: null,
      isLoading: false,
      error: null,
      selectedBrandId: null,
      dateRange: 'month',
      cache: {},
      activeRequestId: 0,
    });
  },
}));
