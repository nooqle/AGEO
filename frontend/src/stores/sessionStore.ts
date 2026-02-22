import { create } from 'zustand';
import type { SessionListItem } from '@/types/session';
import { api } from '@/services/api';

interface Session {
  id: string;
  brandName?: string;
  status: string;
  createdAt: Date;
  updatedAt: Date;
  currentPhase?: string;
}

interface SessionState {
  sessions: Session[];
  currentSession: Session | null;

  // Session list (from API)
  sessionList: SessionListItem[];
  totalSessions: number;
  isLoadingList: boolean;
  listError: string | null;

  // Actions
  setSessions: (sessions: Session[]) => void;
  setCurrentSession: (session: Session | null) => void;
  addSession: (session: Session) => void;
  updateSession: (id: string, updates: Partial<Session>) => void;
  removeSession: (id: string) => void;
  fetchSessionList: (params?: { limit?: number; offset?: number; status?: string }) => Promise<void>;
}

export const useSessionStore = create<SessionState>((set) => ({
  sessions: [],
  currentSession: null,

  sessionList: [],
  totalSessions: 0,
  isLoadingList: false,
  listError: null,

  setSessions: (sessions) => set({ sessions }),

  setCurrentSession: (session) => set({ currentSession: session }),

  addSession: (session) => set((state) => ({
    sessions: [session, ...state.sessions],
    currentSession: session,
  })),

  updateSession: (id, updates) => set((state) => ({
    sessions: state.sessions.map((s) =>
      s.id === id ? { ...s, ...updates } : s
    ),
    currentSession: state.currentSession?.id === id
      ? { ...state.currentSession, ...updates }
      : state.currentSession,
  })),

  removeSession: (id) => set((state) => ({
    sessions: state.sessions.filter((s) => s.id !== id),
    currentSession: state.currentSession?.id === id ? null : state.currentSession,
  })),

  fetchSessionList: async (params) => {
    set({ isLoadingList: true, listError: null });
    try {
      const res = await api.listSessions(params);
      set({
        sessionList: res.sessions,
        totalSessions: res.total,
        isLoadingList: false,
      });
    } catch (err) {
      set({
        listError: err instanceof Error ? err.message : '加载会话列表失败',
        isLoadingList: false,
      });
    }
  },
}));
