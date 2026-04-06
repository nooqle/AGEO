'use client';

import { useEffect, useRef } from 'react';

import { api } from '@/services/api';
import { useAioTakeoverStore } from '@/stores/aioTakeoverStore';
import type { BrowserTakeoverAccess } from '@/types/agent';

const TERMINAL_TAKEOVER_STATES = new Set([
  'resolved',
  'expired',
  'cancelled',
  'resume_failed',
]);

type TimerRef = number;

export function useAioTakeoverHeartbeat(
  takeovers: BrowserTakeoverAccess[],
) {
  const timersRef = useRef<Map<string, TimerRef>>(new Map());

  useEffect(() => {
    const stopTimer = (takeoverId: string) => {
      const timer = timersRef.current.get(takeoverId);
      if (timer) {
        window.clearTimeout(timer);
        timersRef.current.delete(takeoverId);
      }
    };

    const scheduleHeartbeat = (takeoverId: string, delayMs: number) => {
      stopTimer(takeoverId);
      const timer = window.setTimeout(() => {
        void sendHeartbeat(takeoverId);
      }, Math.max(delayMs, 1000));
      timersRef.current.set(takeoverId, timer);
    };

    const sendHeartbeat = async (takeoverId: string) => {
      const store = useAioTakeoverStore.getState();
      const registration = store.registrations[takeoverId];
      if (!registration?.heartbeatPath) {
        stopTimer(takeoverId);
        return;
      }

      const knownRecord = store.records[takeoverId];
      if (
        knownRecord &&
        TERMINAL_TAKEOVER_STATES.has(knownRecord.takeoverState)
      ) {
        stopTimer(takeoverId);
        return;
      }

      try {
        const nextRecord = await api.heartbeatAioTakeover(
          registration.heartbeatPath,
          {
            frontendId: registration.frontendId,
            mode: registration.mode,
          },
        );
        useAioTakeoverStore.getState().upsertRecord(nextRecord);
        if (TERMINAL_TAKEOVER_STATES.has(nextRecord.takeoverState)) {
          stopTimer(takeoverId);
          return;
        }
        const nextDelay =
          useAioTakeoverStore.getState().registrations[takeoverId]
            ?.heartbeatIntervalMs ?? registration.heartbeatIntervalMs;
        scheduleHeartbeat(takeoverId, nextDelay);
      } catch {
        scheduleHeartbeat(
          takeoverId,
          (registration.heartbeatIntervalMs || 10000) * 0.75,
        );
      }
    };

    const store = useAioTakeoverStore.getState();
    const nextIds = new Set(takeovers.map((takeover) => takeover.takeoverId));

    takeovers.forEach((takeover) => {
      store.upsertRegistration(takeover);
    });

    for (const takeoverId of Object.keys(store.registrations)) {
      if (!nextIds.has(takeoverId)) {
        store.removeRegistration(takeoverId);
        stopTimer(takeoverId);
      }
    }

    for (const [takeoverId, registration] of Object.entries(store.registrations)) {
      if (!registration.heartbeatPath) {
        stopTimer(takeoverId);
        continue;
      }
      const record = store.records[takeoverId];
      if (record && TERMINAL_TAKEOVER_STATES.has(record.takeoverState)) {
        stopTimer(takeoverId);
        continue;
      }
      if (!timersRef.current.has(takeoverId)) {
        scheduleHeartbeat(takeoverId, 0);
      }
    }
  }, [takeovers]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timer of timers.values()) {
        window.clearTimeout(timer);
      }
      timers.clear();
    };
  }, []);
}
