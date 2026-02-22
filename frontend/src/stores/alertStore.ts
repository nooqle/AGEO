import { create } from 'zustand';
import type { MonitoringAlert } from '@/types/monitoring';
import { api } from '@/services/api';

interface AlertState {
  alerts: MonitoringAlert[];
  unreadCount: number;
  isLoading: boolean;
  isPanelOpen: boolean;
  error: string | null;

  // Polling control
  _pollingTimer: ReturnType<typeof setInterval> | null;

  // Actions
  fetchAlerts: (limit?: number) => Promise<void>;
  fetchUnreadCount: () => Promise<void>;
  markRead: (alertId: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  dismiss: (alertId: string) => Promise<void>;
  togglePanel: () => void;
  closePanel: () => void;
  startPolling: (intervalMs?: number) => void;
  stopPolling: () => void;
}

export const useAlertStore = create<AlertState>((set, get) => ({
  alerts: [],
  unreadCount: 0,
  isLoading: false,
  isPanelOpen: false,
  error: null,
  _pollingTimer: null,

  fetchAlerts: async (limit = 20) => {
    set({ isLoading: true, error: null });
    try {
      const result = await api.getMonitoringAlerts({ limit, status: 'unread' });
      set({ alerts: result.alerts, isLoading: false });
    } catch (err) {
      set({
        error: err instanceof Error ? err.message : '加载告警失败',
        isLoading: false,
      });
    }
  },

  fetchUnreadCount: async () => {
    try {
      const result = await api.getAlertUnreadCount();
      set({ unreadCount: result.unread_count });
    } catch {
      // Silently ignore — polling should not crash the UI
    }
  },

  markRead: async (alertId: string) => {
    try {
      await api.markAlertRead(alertId);
      set((state) => ({
        alerts: state.alerts.map((a) =>
          a.id === alertId ? { ...a, status: 'read' as const, read_at: new Date().toISOString() } : a
        ),
        unreadCount: Math.max(0, state.unreadCount - 1),
      }));
    } catch {
      // Optimistic update already applied; ignore API errors silently
    }
  },

  markAllRead: async () => {
    try {
      await api.markAllAlertsRead();
      set((state) => ({
        alerts: state.alerts.map((a) => ({
          ...a,
          status: 'read' as const,
          read_at: a.read_at || new Date().toISOString(),
        })),
        unreadCount: 0,
      }));
    } catch {
      // Silently ignore
    }
  },

  dismiss: async (alertId: string) => {
    // Optimistic removal from list
    set((state) => ({
      alerts: state.alerts.filter((a) => a.id !== alertId),
      unreadCount: state.alerts.find((a) => a.id === alertId)?.status === 'unread'
        ? Math.max(0, state.unreadCount - 1)
        : state.unreadCount,
    }));
    try {
      await api.dismissAlert(alertId);
    } catch {
      // Already removed optimistically
    }
  },

  togglePanel: () => {
    const willOpen = !get().isPanelOpen;
    set({ isPanelOpen: willOpen });
    if (willOpen) {
      get().fetchAlerts();
    }
  },

  closePanel: () => set({ isPanelOpen: false }),

  startPolling: (intervalMs = 60_000) => {
    const { _pollingTimer } = get();
    if (_pollingTimer) return; // Already polling

    // Fetch immediately on start
    get().fetchUnreadCount();

    const timer = setInterval(() => {
      get().fetchUnreadCount();
    }, intervalMs);

    set({ _pollingTimer: timer });
  },

  stopPolling: () => {
    const { _pollingTimer } = get();
    if (_pollingTimer) {
      clearInterval(_pollingTimer);
      set({ _pollingTimer: null });
    }
  },
}));
