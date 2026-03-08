import type { Message as ApiMessage } from '@/types/api';
import type { Message as UiMessage, ActionLogEntry, AgentMessageLayers, OutputCard } from '@/types/message';
import type { StageResult } from '@/types/snapshot';
import type { CanvasContentType, CanvasPreviewMetricValue } from '@/types/canvas';
import { normalizePreviewData } from '@/hooks/websocket/canvas';
import { findMatchingPendingActionLog } from '@/hooks/websocket/actionLog';

export const VALID_OUTPUT_TYPES: CanvasContentType[] = ['report', 'chart', 'dataTable', 'pipeline', 'workflow', 'questionList', 'fetchResults'];

type UnknownRecord = Record<string, unknown>;

function isRecord(value: unknown): value is UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}


function reconcilePersistedActionLogs(rawLogs: Array<Record<string, unknown>>): ActionLogEntry[] {
  const reconciled: ActionLogEntry[] = [];

  for (const rawLog of rawLogs) {
    const normalizedLog: ActionLogEntry = {
      id: typeof rawLog.id === 'string' ? rawLog.id : `log_${reconciled.length}`,
      actionType: ((rawLog.action_type as string) || 'generic') as ActionLogEntry['actionType'],
      message: (rawLog.message as string) || '',
      step: (rawLog.step as string) || '',
      timestamp: (rawLog.timestamp as string) || '',
      isComplete: Boolean(rawLog.is_complete),
    };

    if (!normalizedLog.isComplete) {
      reconciled.push(normalizedLog);
      continue;
    }

    const existingLog = findMatchingPendingActionLog(reconciled, {
      actionType: normalizedLog.actionType,
      message: normalizedLog.message,
      step: normalizedLog.step || '',
      isComplete: true,
    });

    if (existingLog) {
      const existingIndex = reconciled.findIndex((log) => log.id == existingLog.id);
      if (existingIndex >= 0) {
        reconciled[existingIndex] = {
          ...existingLog,
          message: normalizedLog.message || existingLog.message,
          step: normalizedLog.step || existingLog.step,
          timestamp: normalizedLog.timestamp || existingLog.timestamp,
          isComplete: true,
        };
        continue;
      }
    }

    reconciled.push(normalizedLog);
  }

  return reconciled;
}

export function normalizeCanvasOutputType(rawType: string | undefined): CanvasContentType | null {
  const normalized = (rawType || '').startsWith('report') ? 'report' : (rawType || '');
  return normalized && VALID_OUTPUT_TYPES.includes(normalized as CanvasContentType)
    ? (normalized as CanvasContentType)
    : null;
}

export function buildOutputCardsFromApiMessage(msg: ApiMessage, sessionId: string): UiMessage['outputCards'] | undefined {
  const outputType = normalizeCanvasOutputType(msg.output_type);
  const parsed = msg.output_data ?? null;
  if (!outputType || !parsed) {
    return undefined;
  }

  const preview = normalizePreviewData(parsed as UnknownRecord);
  const metadata = isRecord(msg.metadata) ? msg.metadata : undefined;
  const outputId =
    (typeof metadata?.output_id === 'string' ? metadata.output_id : undefined) ||
    (typeof (parsed as UnknownRecord).output_id === 'string' ? (parsed as UnknownRecord).output_id as string : undefined) ||
    `${sessionId}_${msg.output_type}`;

  return [{
    id: outputId,
    type: outputType,
    title: (parsed as UnknownRecord).headline as string || (parsed as UnknownRecord).title as string || msg.content || '分析结果',
    preview,
  } satisfies OutputCard];
}

export function buildRealtimeOutputCard(outputId: string, outputType: CanvasContentType, outputTitle: string, preview: { description?: string; itemCount?: number; metrics?: Record<string, CanvasPreviewMetricValue> }): OutputCard {
  return {
    id: outputId,
    type: outputType,
    title: outputTitle,
    preview: {
      description: preview.description,
      itemCount: preview.itemCount,
      metrics: preview.metrics,
    },
  };
}

export function rebuildPersistedLayers(metadata: Record<string, unknown> | null | undefined): {
  layers?: AgentMessageLayers;
  stageResults: StageResult[];
} {
  const persistedLayers = metadata?.layers as Record<string, unknown> | undefined;
  if (!persistedLayers) {
    return { layers: undefined, stageResults: [] };
  }

  const actionLogs: ActionLogEntry[] = Array.isArray(persistedLayers.actionLogs)
    ? reconcilePersistedActionLogs(persistedLayers.actionLogs as Array<Record<string, unknown>>)
    : [];

  const stageResults: StageResult[] = Array.isArray(persistedLayers.stageResults)
    ? (persistedLayers.stageResults as Array<Record<string, unknown>>).map((sr) => ({
        stage: (sr.stage as string) || '',
        stageName: (sr.stage_name as string) || '',
        resultType: (sr.result_type as StageResult['resultType']) || 'brand_profile',
        data: (sr.data as Record<string, unknown>) || {},
        timestamp: (sr.timestamp as string) || '',
      }))
    : [];

  return {
    layers: {
      thought: (persistedLayers.thought as string) || undefined,
      planText: (persistedLayers.planText as string) || undefined,
      actionLogs,
    },
    stageResults,
  };
}





