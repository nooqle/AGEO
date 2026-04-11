'use client';

import { useEffect, useRef, useCallback } from 'react';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { getUserFacingStageLabel } from '@/lib/workflowStageLabels';

interface TaskNotificationPollerProps {
  /** Polling interval in ms (default 30s) */
  intervalMs?: number;
  /** Currently active session ID (to skip notifications for visible session) */
  activeSessionId?: string;
}

/**
 * Background poller that checks for completed/failed tasks across all sessions.
 * Shows toast notifications for tasks that finished while user was away.
 * Mount this once in the app layout (not per-session).
 */
export function TaskNotificationPoller({
  intervalMs = 30000,
  activeSessionId,
}: TaskNotificationPollerProps) {
  const knownTasksRef = useRef<Set<string>>(new Set());
  const initializedRef = useRef(false);

  const pollTasks = useCallback(async () => {
    try {
      // Fetch recently completed and failed tasks
      const [completed, failed] = await Promise.all([
        api.getUserTasks({ status: 'completed', limit: 10 }),
        api.getUserTasks({ status: 'failed', limit: 5 }),
      ]);

      const allTasks = [...(completed.tasks || []), ...(failed.tasks || [])];

      if (!initializedRef.current) {
        // First poll: seed known tasks without showing notifications
        for (const task of allTasks) {
          knownTasksRef.current.add(task.id);
        }
        initializedRef.current = true;
        return;
      }

      // Check for new completed/failed tasks
      for (const task of allTasks) {
        if (knownTasksRef.current.has(task.id)) continue;
        knownTasksRef.current.add(task.id);

        // Skip notifications for the session the user is currently viewing
        if (task.session_id === activeSessionId) continue;

        if (task.status === 'completed') {
          toast.success(
            `「${task.brand_name}」分析已完成`,
          );
        } else if (task.status === 'failed') {
          const errorStageLabel = getUserFacingStageLabel(task.error_stage);
          toast.error(
            `「${task.brand_name}」分析失败${errorStageLabel ? ` (${errorStageLabel})` : ''}`,
          );
        }
      }
    } catch {
      // Silently ignore polling errors — will retry next interval
    }
  }, [activeSessionId]);

  useEffect(() => {
    // Initial poll
    pollTasks();

    // Set up periodic polling
    const timer = setInterval(pollTasks, intervalMs);
    return () => clearInterval(timer);
  }, [pollTasks, intervalMs]);

  // This component renders nothing — it's a side-effect-only component
  return null;
}

export default TaskNotificationPoller;
