import { create } from 'zustand';
import type { DashboardData } from '@/types/dashboard';
import { api } from '@/services/api';

interface DashboardState {
  data: DashboardData | null;
  isLoading: boolean;
  error: string | null;
  selectedBrandId: string | null;
  dateRange: 'week' | 'month' | 'quarter';

  setData: (data: DashboardData) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  setSelectedBrandId: (id: string | null) => void;
  setDateRange: (range: 'week' | 'month' | 'quarter') => void;
  fetchData: () => Promise<void>;
  reset: () => void;
}

export const useDashboardStore = create<DashboardState>((set, get) => ({
  data: null,
  isLoading: false,
  error: null,
  selectedBrandId: null,
  dateRange: 'month',

  setData: (data) => set({ data, isLoading: false, error: null }),
  setLoading: (isLoading) => set({ isLoading }),
  setError: (error) => set({ error, isLoading: false }),
  setSelectedBrandId: (selectedBrandId) => set({ selectedBrandId, data: null }),
  setDateRange: (dateRange) => set({ dateRange }),

  fetchData: async () => {
    const { selectedBrandId, dateRange } = get();
    set({ isLoading: true, error: null });
    try {
      const data = await api.getAnalyticsAll(
        selectedBrandId || undefined,
        dateRange,
      );
      set({ data, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : 'Failed to load analytics',
        isLoading: false,
      });
    }
  },

  reset: () =>
    set({
      data: null,
      isLoading: false,
      error: null,
      selectedBrandId: null,
      dateRange: 'month',
    }),
}));
