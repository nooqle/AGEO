import { create } from 'zustand';

import type { BrowserTakeoverAccess } from '@/types/agent';
import type { AioTakeoverMode, AioTakeoverRecord } from '@/types/aio';

const DEFAULT_HEARTBEAT_MS = 10000;

type TakeoverRegistration = {
  takeoverId: string;
  frontendId: string;
  heartbeatPath?: string;
  mode: AioTakeoverMode;
  heartbeatIntervalMs: number;
  targetUrl?: string;
};

function createFrontendId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `fe_${crypto.randomUUID()}`;
  }
  return `fe_${Math.random().toString(36).slice(2, 10)}`;
}

interface AioTakeoverStoreState {
  registrations: Record<string, TakeoverRegistration>;
  records: Record<string, AioTakeoverRecord>;
  upsertRegistration: (access: BrowserTakeoverAccess) => void;
  removeRegistration: (takeoverId: string) => void;
  clearTakeover: (takeoverId: string) => void;
  setTakeoverMode: (takeoverId: string, mode: AioTakeoverMode) => void;
  setHeartbeatInterval: (takeoverId: string, heartbeatIntervalMs: number) => void;
  upsertRecord: (record: AioTakeoverRecord) => void;
  clear: () => void;
}

export const useAioTakeoverStore = create<AioTakeoverStoreState>((set) => ({
  registrations: {},
  records: {},

  upsertRegistration: (access) =>
    set((state) => {
      const existing = state.registrations[access.takeoverId];
      const nextRegistration: TakeoverRegistration = {
        takeoverId: access.takeoverId,
        frontendId: existing?.frontendId ?? createFrontendId(),
        heartbeatPath: access.heartbeatPath,
        mode: access.mode,
        heartbeatIntervalMs: existing?.heartbeatIntervalMs ?? DEFAULT_HEARTBEAT_MS,
        targetUrl: access.targetUrl ?? existing?.targetUrl,
      };
      return {
        registrations: {
          ...state.registrations,
          [access.takeoverId]: nextRegistration,
        },
      };
    }),

  removeRegistration: (takeoverId) =>
    set((state) => {
      if (!state.registrations[takeoverId]) {
        return state;
      }
      const registrations = { ...state.registrations };
      delete registrations[takeoverId];
      return {
        registrations,
      };
    }),

  clearTakeover: (takeoverId) =>
    set((state) => {
      if (!state.registrations[takeoverId] && !state.records[takeoverId]) {
        return state;
      }
      const registrations = { ...state.registrations };
      const records = { ...state.records };
      delete registrations[takeoverId];
      delete records[takeoverId];
      return {
        registrations,
        records,
      };
    }),

  setTakeoverMode: (takeoverId, mode) =>
    set((state) => {
      const registration = state.registrations[takeoverId];
      if (!registration) {
        return state;
      }
      return {
        registrations: {
          ...state.registrations,
          [takeoverId]: {
            ...registration,
            mode,
          },
        },
      };
    }),

  setHeartbeatInterval: (takeoverId, heartbeatIntervalMs) =>
    set((state) => {
      const registration = state.registrations[takeoverId];
      if (!registration) {
        return state;
      }
      return {
        registrations: {
          ...state.registrations,
          [takeoverId]: {
            ...registration,
            heartbeatIntervalMs: Math.max(heartbeatIntervalMs, 1000),
          },
        },
      };
    }),

  upsertRecord: (record) =>
    set((state) => {
      const registration = state.registrations[record.takeoverId];
      return {
        records: {
          ...state.records,
          [record.takeoverId]: record,
        },
        registrations: registration
          ? {
              ...state.registrations,
              [record.takeoverId]: {
                ...registration,
                targetUrl:
                  record.targetUrl ??
                  record.accessBundle.targetUrl ??
                  registration.targetUrl,
              },
            }
          : state.registrations,
      };
    }),

  clear: () => ({
    registrations: {},
    records: {},
  }),
}));
