import type { WebSocketEventData } from '@/types/websocket';
import type { StopState } from '@/types/agent';
import type { AnalysisTask, FollowUpSuggestion } from '@/types/task';

const VALID_FOLLOWUP_TYPES = ['drill_down', 'compare', 'refetch', 'general'] as const;
type SuggestionType = typeof VALID_FOLLOWUP_TYPES[number];

export function buildCompletedTask(
  currentTask: AnalysisTask | null,
  data: WebSocketEventData,
): AnalysisTask | null {
  if (!currentTask || currentTask.status !== 'running') {
    return null;
  }

  return {
    ...currentTask,
    status: 'completed',
    progress: 1.0,
    progress_message: '分析完成',
    completed_at: new Date().toISOString(),
    snapshot_id: typeof data.snapshot_id === 'string' ? data.snapshot_id : currentTask.snapshot_id,
  };
}


export function buildStopState(data: WebSocketEventData): StopState | null {
  const completedStages = Array.isArray(data.completed_stages)
    ? data.completed_stages
        .map((stage) => {
          if (typeof stage !== 'object' || stage === null) {
            return null;
          }
          const raw = stage as Record<string, unknown>;
          const name = typeof raw.name === 'string' ? raw.name : '';
          if (!name) return null;
          const description = typeof raw.description === 'string' ? raw.description : undefined;
          const completedAt = raw.completedAt instanceof Date
            ? raw.completedAt
            : new Date(typeof raw.completedAt === 'string' ? raw.completedAt : Date.now());
          return { name, description, completedAt };
        })
        .filter((stage): stage is { name: string; description: string | undefined; completedAt: Date } => stage !== null)
    : [];

  const pendingStages = Array.isArray(data.pending_stages)
    ? data.pending_stages
        .map((stage) => {
          if (typeof stage !== 'object' || stage === null) {
            return null;
          }
          const raw = stage as Record<string, unknown>;
          const name = typeof raw.name === 'string' ? raw.name : '';
          if (!name) return null;
          const description = typeof raw.description === 'string' ? raw.description : undefined;
          return { name, description };
        })
        .filter((stage): stage is { name: string; description: string | undefined } => stage !== null)
    : [];

  const partialResults = typeof data.partial_results === 'object' && data.partial_results !== null
    ? data.partial_results as {
        fetchedCount?: number;
        totalCount?: number;
        platforms?: Record<string, { completed: number; total: number }>;
      }
    : undefined;

  return {
    isStopped: true,
    stoppedAt: new Date(),
    completedStages,
    pendingStages,
    partialResults: partialResults
      ? {
          fetchedCount: partialResults.fetchedCount ?? 0,
          totalCount: partialResults.totalCount ?? 0,
          platforms: partialResults.platforms ?? {},
        }
      : undefined,
    canResume: Boolean(data.can_resume ?? false),
    canRetry: Boolean(data.can_retry ?? false),
  };
}

export function buildFollowUpSuggestions(data: WebSocketEventData): FollowUpSuggestion[] {
  if (!Array.isArray(data.follow_up_suggestions) || data.follow_up_suggestions.length === 0) {
    return [];
  }

  return data.follow_up_suggestions.map((item: Record<string, unknown>, index: number) => {
    const rawType = typeof item.type === 'string' ? item.type : 'general';
    const type: SuggestionType = (VALID_FOLLOWUP_TYPES as readonly string[]).includes(rawType)
      ? (rawType as SuggestionType)
      : 'general';

    return {
      id: typeof item.id === 'string' ? item.id : `fu_${index}`,
      label: typeof item.label === 'string' ? item.label : '',
      message: typeof item.message === 'string' ? item.message : '',
      type,
      icon: typeof item.icon === 'string' ? item.icon : undefined,
    };
  });
}

