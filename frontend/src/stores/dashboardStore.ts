import { create } from 'zustand';
import type { DashboardData, DashboardHomeData, DashboardMonitorMode } from '@/types/dashboard';
import { api } from '@/services/api';

type DashboardDateRange = '7' | '14' | '30';

function buildCacheKey(
  selectedBrandId: string | null,
  dateRange: DashboardDateRange,
): string {
  return `${selectedBrandId ?? 'all'}:${dateRange}`;
}

function buildHomeCacheKey(
  selectedBrandId: string | null,
  dateRange: DashboardDateRange,
  monitorMode: DashboardMonitorMode,
): string {
  return `${selectedBrandId ?? 'all'}:${dateRange}:${monitorMode}`;
}

let activeDashboardRequestController: AbortController | null = null;
let activeDashboardHomeRequestController: AbortController | null = null;

interface DashboardState {
  data: DashboardData | null;
  home: DashboardHomeData | null;
  isLoading: boolean;
  isHomeLoading: boolean;
  error: string | null;
  homeError: string | null;
  selectedBrandId: string | null;
  dateRange: DashboardDateRange;
  homeMonitorMode: DashboardMonitorMode;
  cache: Record<string, DashboardData>;
  homeCache: Record<string, DashboardHomeData | null>;
  activeRequestId: number;
  activeHomeRequestId: number;

  setData: (data: DashboardData) => void;
  setHome: (home: DashboardHomeData | null) => void;
  setLoading: (loading: boolean) => void;
  setHomeLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setHomeError: (error: string | null) => void;
  setSelectedBrandId: (id: string | null) => void;
  setDateRange: (range: DashboardDateRange) => void;
  setHomeMonitorMode: (mode: DashboardMonitorMode) => void;
  fetchData: () => Promise<void>;
  fetchHome: () => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  data: null,
  home: null,
  isLoading: false,
  isHomeLoading: false,
  error: null,
  homeError: null,
  selectedBrandId: null,
  dateRange: '30',
  homeMonitorMode: 'panorama',
  cache: {},
  homeCache: {},
  activeRequestId: 0,
  activeHomeRequestId: 0,

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
  setHome: (home) =>
    set((state) => {
      const cacheKey = buildHomeCacheKey(
        state.selectedBrandId,
        state.dateRange,
        state.homeMonitorMode,
      );
      return {
        home,
        isHomeLoading: false,
        homeError: null,
        homeCache: {
          ...state.homeCache,
          [cacheKey]: home,
        },
      };
    }),
  setLoading: (isLoading) => set({ isLoading }),
  setHomeLoading: (isHomeLoading) => set({ isHomeLoading }),
  setError: (error) => set({ error, isLoading: false }),
  setHomeError: (homeError) => set({ homeError, isHomeLoading: false }),
  setSelectedBrandId: (selectedBrandId) =>
    set((state) => {
      const homeMonitorMode: DashboardMonitorMode = 'panorama';
      const cacheKey = buildCacheKey(selectedBrandId, state.dateRange);
      const homeCacheKey = buildHomeCacheKey(
        selectedBrandId,
        state.dateRange,
        homeMonitorMode,
      );
      return {
        selectedBrandId,
        homeMonitorMode,
        data: state.cache[cacheKey] ?? null,
        home: state.homeCache[homeCacheKey] ?? null,
        error: null,
        homeError: null,
      };
    }),
  setDateRange: (dateRange) =>
    set((state) => {
      const cacheKey = buildCacheKey(state.selectedBrandId, dateRange);
      const homeCacheKey = buildHomeCacheKey(
        state.selectedBrandId,
        dateRange,
        state.homeMonitorMode,
      );
      return {
        dateRange,
        data: state.cache[cacheKey] ?? null,
        home: state.homeCache[homeCacheKey] ?? null,
        error: null,
        homeError: null,
      };
    }),
  setHomeMonitorMode: (homeMonitorMode) =>
    set((state) => {
      const homeCacheKey = buildHomeCacheKey(
        state.selectedBrandId,
        state.dateRange,
        homeMonitorMode,
      );
      const hasCachedHome = Object.prototype.hasOwnProperty.call(
        state.homeCache,
        homeCacheKey,
      );
      return {
        homeMonitorMode,
        home: state.homeCache[homeCacheKey] ?? null,
        isHomeLoading: !hasCachedHome,
        homeError: null,
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

  fetchHome: async () => {
    const {
      selectedBrandId,
      dateRange,
      homeMonitorMode,
      homeCache,
      activeHomeRequestId,
    } = get();
    const cacheKey = buildHomeCacheKey(selectedBrandId, dateRange, homeMonitorMode);
    const requestId = activeHomeRequestId + 1;
    const cachedHome = homeCache[cacheKey] ?? null;
    activeDashboardHomeRequestController?.abort();
    const controller = new AbortController();
    activeDashboardHomeRequestController = controller;
    set({
      activeHomeRequestId: requestId,
      isHomeLoading: true,
      homeError: null,
      home: cachedHome,
    });
    try {
      const home = await api.getDashboardHomeSummary(
        selectedBrandId || undefined,
        homeMonitorMode,
        dateRange,
        { signal: controller.signal },
      );
      const latest = get();
      if (
        activeDashboardHomeRequestController !== controller ||
        latest.activeHomeRequestId !== requestId ||
        latest.selectedBrandId !== selectedBrandId ||
        latest.dateRange !== dateRange ||
        latest.homeMonitorMode !== homeMonitorMode
      ) {
        return;
      }
      activeDashboardHomeRequestController = null;
      set((state) => ({
        home,
        isHomeLoading: false,
        homeError: null,
        homeCache: {
          ...state.homeCache,
          [cacheKey]: home,
        },
      }));
    } catch (err) {
      if (controller.signal.aborted) {
        return;
      }
      const latest = get();
      if (
        activeDashboardHomeRequestController !== controller ||
        latest.activeHomeRequestId !== requestId ||
        latest.selectedBrandId !== selectedBrandId ||
        latest.dateRange !== dateRange ||
        latest.homeMonitorMode !== homeMonitorMode
      ) {
        return;
      }
      activeDashboardHomeRequestController = null;
      set({
        homeError: err instanceof Error ? err.message : 'Failed to load dashboard home',
        isHomeLoading: false,
      });
    }
  },

  reset: () => {
    activeDashboardRequestController?.abort();
    activeDashboardHomeRequestController?.abort();
    activeDashboardRequestController = null;
    activeDashboardHomeRequestController = null;
    set({
      data: null,
      isLoading: false,
      error: null,
      selectedBrandId: null,
      dateRange: '30',
      homeMonitorMode: 'panorama',
      cache: {},
      activeRequestId: 0,
      activeHomeRequestId: 0,
      home: null,
      isHomeLoading: false,
      homeError: null,
      homeCache: {},
    });
  },
}));
