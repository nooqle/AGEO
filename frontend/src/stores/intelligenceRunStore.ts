import { create } from 'zustand';

import { api } from '@/services/api';
import type {
  BrandIntelligenceRun,
  ConfirmBrandIntelligenceRunInput,
  CreateBrandIntelligenceRunInput,
} from '@/types/intelligenceRun';

interface IntelligenceRunState {
  runsByEntity: Record<string, BrandIntelligenceRun | null>;
  loadingByEntity: Record<string, boolean>;
  errorByEntity: Record<string, string | null>;
  submittingByEntity: Record<string, boolean>;
  activeRequestByEntity: Record<string, number>;
  fetchActiveRun: (entityId: string) => Promise<BrandIntelligenceRun | null>;
  createRun: (
    entityId: string,
    payload: CreateBrandIntelligenceRunInput,
  ) => Promise<BrandIntelligenceRun>;
  refreshRun: (runId: string) => Promise<BrandIntelligenceRun | null>;
  resumeRun: (entityId: string, runId: string) => Promise<BrandIntelligenceRun>;
  cancelRun: (entityId: string, runId: string) => Promise<BrandIntelligenceRun>;
  confirmRun: (
    entityId: string,
    runId: string,
    payload: ConfirmBrandIntelligenceRunInput,
  ) => Promise<BrandIntelligenceRun>;
  reset: () => void;
}

export const useIntelligenceRunStore = create<IntelligenceRunState>((set, get) => ({
  runsByEntity: {},
  loadingByEntity: {},
  errorByEntity: {},
  submittingByEntity: {},
  activeRequestByEntity: {},

  fetchActiveRun: async (entityId) => {
    const requestId = (get().activeRequestByEntity[entityId] ?? 0) + 1;
    set((state) => ({
      loadingByEntity: { ...state.loadingByEntity, [entityId]: true },
      errorByEntity: { ...state.errorByEntity, [entityId]: null },
      activeRequestByEntity: { ...state.activeRequestByEntity, [entityId]: requestId },
    }));
    try {
      const run = await api.getActiveBrandIntelligenceRun(entityId);
      if (get().activeRequestByEntity[entityId] !== requestId) return run;
      set((state) => ({
        runsByEntity: { ...state.runsByEntity, [entityId]: run },
        loadingByEntity: { ...state.loadingByEntity, [entityId]: false },
        errorByEntity: { ...state.errorByEntity, [entityId]: null },
      }));
      return run;
    } catch (error) {
      if (get().activeRequestByEntity[entityId] !== requestId) return null;
      set((state) => ({
        loadingByEntity: { ...state.loadingByEntity, [entityId]: false },
        errorByEntity: {
          ...state.errorByEntity,
          [entityId]: error instanceof Error ? error.message : '任务状态读取失败',
        },
      }));
      return null;
    }
  },

  createRun: async (entityId, payload) => {
    set((state) => ({
      submittingByEntity: { ...state.submittingByEntity, [entityId]: true },
      errorByEntity: { ...state.errorByEntity, [entityId]: null },
    }));
    try {
      const run = await api.createBrandIntelligenceRun(entityId, payload);
      set((state) => ({
        runsByEntity: { ...state.runsByEntity, [entityId]: run },
        submittingByEntity: { ...state.submittingByEntity, [entityId]: false },
      }));
      return run;
    } catch (error) {
      for (const delayMs of [0, 800, 2000]) {
        if (delayMs > 0) {
          await new Promise((resolve) => setTimeout(resolve, delayMs));
        }
        try {
          const recoveredRun = await api.getActiveBrandIntelligenceRun(entityId);
          if (recoveredRun && payload?.origin_event_id && recoveredRun.origin_event_id === payload.origin_event_id) {
            set((state) => ({
              runsByEntity: { ...state.runsByEntity, [entityId]: recoveredRun },
              submittingByEntity: { ...state.submittingByEntity, [entityId]: false },
              errorByEntity: { ...state.errorByEntity, [entityId]: null },
            }));
            return recoveredRun;
          }
        } catch {
          // Retry the status read before surfacing the original start failure.
        }
      }
      set((state) => ({
        submittingByEntity: { ...state.submittingByEntity, [entityId]: false },
        errorByEntity: {
          ...state.errorByEntity,
          [entityId]: error instanceof Error ? error.message : '任务创建失败',
        },
      }));
      throw error;
    }
  },

  refreshRun: async (runId) => {
    const run = await api.getBrandIntelligenceRun(runId);
    if (run) {
      set((state) => ({
        runsByEntity: { ...state.runsByEntity, [run.entity_id]: run },
      }));
    }
    return run;
  },

  resumeRun: async (entityId, runId) => {
    set((state) => ({
      submittingByEntity: { ...state.submittingByEntity, [entityId]: true },
      errorByEntity: { ...state.errorByEntity, [entityId]: null },
    }));
    try {
      const run = await api.resumeBrandIntelligenceRun(runId);
      set((state) => ({
        runsByEntity: { ...state.runsByEntity, [entityId]: run },
        submittingByEntity: { ...state.submittingByEntity, [entityId]: false },
      }));
      return run;
    } catch (error) {
      set((state) => ({
        submittingByEntity: { ...state.submittingByEntity, [entityId]: false },
        errorByEntity: {
          ...state.errorByEntity,
          [entityId]: error instanceof Error ? error.message : '任务继续失败',
        },
      }));
      throw error;
    }
  },

  cancelRun: async (entityId, runId) => {
    const run = await api.cancelBrandIntelligenceRun(runId);
    set((state) => ({
      runsByEntity: { ...state.runsByEntity, [entityId]: run },
    }));
    return run;
  },

  confirmRun: async (entityId, runId, payload) => {
    const run = await api.confirmBrandIntelligenceRun(runId, payload);
    set((state) => ({
      runsByEntity: { ...state.runsByEntity, [entityId]: run },
    }));
    return run;
  },

  reset: () => {
    set({
      runsByEntity: {},
      loadingByEntity: {},
      errorByEntity: {},
      submittingByEntity: {},
      activeRequestByEntity: {},
    });
  },
}));
