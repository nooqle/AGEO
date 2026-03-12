import type { BrowserActionType, BrowserState, ExecutionProgress, ProgressStep, SubTask } from '@/types/agent';
import type { WebSocketEventData } from '@/types/websocket';
import { BROWSER_PLATFORMS, BROWSER_STATES, EXECUTION_STATUSES, mapStepStatus } from './protocol';

export function buildExecutionProgress(
  data: WebSocketEventData,
  previous: ExecutionProgress | null | undefined,
): ExecutionProgress {
  const mappedSteps: ProgressStep[] = Array.isArray(data.steps)
    ? (data.steps.map((s, index) => ({
        id: String((s as Record<string, unknown>).id || index),
        label: String((s as Record<string, unknown>).label || (s as Record<string, unknown>).id || ''),
        status: mapStepStatus((s as Record<string, unknown>).status as string),
      })) as ProgressStep[])
    : (previous?.steps || []);

  const oldSteps = previous?.steps || [];
  const mergedSteps = mappedSteps.map((newStep: ProgressStep) => {
    const oldStep = oldSteps.find((step) => step.id === newStep.id);
    if (oldStep?.status === 'completed' && newStep.status === 'pending') {
      return { ...newStep, status: 'completed' as const };
    }
    return newStep;
  });

  const oldProgress = previous?.progress ?? 0;
  const newProgress = data.progress ?? 0;
  const safeProgress = Math.max(oldProgress, newProgress);

  return {
    stage: data.stage || '',
    stageName: data.stage_name || '',
    stageIndex: data.current_step_index ?? 0,
    totalStages: data.total_steps ?? 5,
    progress: safeProgress,
    status: EXECUTION_STATUSES.includes((data.status || 'running') as ExecutionProgress['status'])
      ? ((data.status || 'running') as ExecutionProgress['status'])
      : 'running',
    details: data.message || data.details || '',
    steps: mergedSteps,
    subTasks: Array.isArray(data.sub_tasks)
      ? (data.sub_tasks.map((t, index) => ({
          id: String((t as Record<string, unknown>).id || index),
          name: String((t as Record<string, unknown>).name || ''),
          status: ((t as Record<string, unknown>).status || 'pending') as SubTask['status'],
          platform: typeof (t as Record<string, unknown>).platform === 'string'
            ? ((t as Record<string, unknown>).platform as SubTask['platform'])
            : undefined,
          progress: typeof (t as Record<string, unknown>).progress === 'number'
            ? ((t as Record<string, unknown>).progress as SubTask['progress'])
            : undefined,
          message: typeof (t as Record<string, unknown>).message === 'string'
            ? ((t as Record<string, unknown>).message as SubTask['message'])
            : undefined,
        })) as SubTask[])
      : [],
  };
}

export function buildBrowserState(data: WebSocketEventData): BrowserState {
  const state = BROWSER_STATES.includes((data.state || '') as BrowserState['state'])
    ? ((data.state || '') as BrowserState['state'])
    : 'idle';
  const message = data.message || '';
  const explicitActionType = typeof data.action_type === 'string'
    ? (data.action_type as BrowserActionType)
    : undefined;

  let actionType: BrowserActionType | undefined;
  if (explicitActionType === 'login' || explicitActionType === 'verify' || explicitActionType === 'modal') {
    actionType = explicitActionType;
  } else if (message.includes('\u9a8c\u8bc1')) {
    actionType = 'verify';
  } else if (state === 'waiting_for_modal') {
    actionType = 'modal';
  } else if (state === 'waiting_for_login') {
    actionType = 'login';
  }

  return {
    state,
    message,
    platform: BROWSER_PLATFORMS.includes((data.platform || '') as BrowserState['platform'])
      ? ((data.platform || '') as BrowserState['platform'])
      : 'kimi',
    requiresAction: typeof data.requires_action === 'boolean' ? data.requires_action : false,
    actionType,
    actionHint: typeof data.action_hint === 'string' ? data.action_hint : undefined,
    progress: typeof data.progress === 'number' ? data.progress : undefined,
  };
}
