import { create } from 'zustand';

import type { BrowserTakeoverAccess } from '@/types/agent';
import type { AioTakeoverMode, AioTakeoverRecord } from '@/types/aio';

const DEFAULT_HEARTBEAT_MS = 10000;
const DEFAULT_UI_TAKEOVER_MODE: AioTakeoverMode = 'vnc_fallback';

function normalizeUiTakeoverMode(mode?: AioTakeoverMode | null): AioTakeoverMode {
  return mode === 'canvas_cdp' ? DEFAULT_UI_TAKEOVER_MODE : (mode ?? DEFAULT_UI_TAKEOVER_MODE);
}

type TakeoverRegistration = {
  takeoverId: string;
  frontendId: string;
  heartbeatPath?: string;
  mode: AioTakeoverMode;
  heartbeatIntervalMs: number;
  targetUrl?: string;
  openPath?: string;
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
  openedTakeoverIds: Record<string, true>;
  openedAtMsByTakeoverId: Record<string, number>;
  upsertRegistration: (access: BrowserTakeoverAccess) => void;
  markTakeoverOpened: (takeoverId: string, openedAtMs?: number) => void;
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
  openedTakeoverIds: {},
  openedAtMsByTakeoverId: {},

  upsertRegistration: (access) =>
    set((state) => {
      const existing = state.registrations[access.takeoverId];
      const nextRegistration: TakeoverRegistration = {
        takeoverId: access.takeoverId,
        frontendId: existing?.frontendId ?? createFrontendId(),
        heartbeatPath: access.heartbeatPath,
        // Use the remote desktop surface as the primary cloud-computer view.
        // The CDP screencast renderer is faster on ideal links, but it is
        // fragile when the backend rebinds targets during manual resume.
        mode: normalizeUiTakeoverMode(existing?.mode),
        heartbeatIntervalMs: existing?.heartbeatIntervalMs ?? DEFAULT_HEARTBEAT_MS,
        targetUrl: access.targetUrl ?? existing?.targetUrl,
        openPath: access.openPath ?? existing?.openPath,
      };
      return {
        registrations: {
          ...state.registrations,
          [access.takeoverId]: nextRegistration,
        },
      };
    }),

  markTakeoverOpened: (takeoverId, openedAtMs) =>
    set((state) => ({
      openedTakeoverIds: {
        ...state.openedTakeoverIds,
        [takeoverId]: true,
      },
      openedAtMsByTakeoverId: {
        ...state.openedAtMsByTakeoverId,
        [takeoverId]: openedAtMs ?? Date.now(),
      },
    })),

  removeRegistration: (takeoverId) =>
    set((state) => {
      if (!state.registrations[takeoverId]) {
        return state;
      }
      const registrations = { ...state.registrations };
      const openedTakeoverIds = { ...state.openedTakeoverIds };
      const openedAtMsByTakeoverId = { ...state.openedAtMsByTakeoverId };
      delete registrations[takeoverId];
      delete openedTakeoverIds[takeoverId];
      delete openedAtMsByTakeoverId[takeoverId];
      return {
        registrations,
        openedTakeoverIds,
        openedAtMsByTakeoverId,
      };
    }),

  clearTakeover: (takeoverId) =>
    set((state) => {
      if (!state.registrations[takeoverId] && !state.records[takeoverId]) {
        return state;
      }
      const registrations = { ...state.registrations };
      const records = { ...state.records };
      const openedTakeoverIds = { ...state.openedTakeoverIds };
      const openedAtMsByTakeoverId = { ...state.openedAtMsByTakeoverId };
      delete registrations[takeoverId];
      delete records[takeoverId];
      delete openedTakeoverIds[takeoverId];
      delete openedAtMsByTakeoverId[takeoverId];
      return {
        registrations,
        records,
        openedTakeoverIds,
        openedAtMsByTakeoverId,
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
                mode: normalizeUiTakeoverMode(registration.mode),
                targetUrl:
                  record.targetUrl ??
                  record.accessBundle.targetUrl ??
                  registration.targetUrl,
                openPath:
                  record.accessBundle.openPath ??
                  registration.openPath,
              },
            }
          : state.registrations,
      };
    }),

  clear: () => ({
    registrations: {},
    records: {},
    openedTakeoverIds: {},
    openedAtMsByTakeoverId: {},
  }),
}));
