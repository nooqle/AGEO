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

const A5_FAILURE_PATTERNS = [
  /报告生成(?:再次|仍然)?失败/,
  /抓取的数据(?:确实)?存在问题/,
  /无法用于分析/,
  /重新抓取数据/,
  /检查抓取结果/,
  /跳过(?:基线分析|品牌全景分析)/,
];

export function isSupersededA5FailureText(content: string | undefined): boolean {
  const normalized = (content || '').trim();
  if (!normalized) {
    return false;
  }
  return A5_FAILURE_PATTERNS.some((pattern) => pattern.test(normalized));
}

function isReportOutputMessage(message: ApiMessage): boolean {
  return message.type === 'output' && typeof message.output_type === 'string' && message.output_type.startsWith('report');
}

export function getSupersededHistoryMessageIds(messages: ApiMessage[]): Set<string> {
  const suppressed = new Set<string>();

  const processTurn = (turnMessages: ApiMessage[]) => {
    if (!turnMessages.some(isReportOutputMessage)) {
      return;
    }
    for (const message of turnMessages) {
      if (
        typeof message.id === 'string'
        && (message.role === 'agent' || message.role === 'assistant')
        && message.type !== 'output'
        && isSupersededA5FailureText(message.content)
      ) {
        suppressed.add(message.id);
      }
    }
  };

  let currentTurn: ApiMessage[] = [];
  for (const message of messages) {
    if (message.role === 'user') {
      processTurn(currentTurn);
      currentTurn = [message];
      continue;
    }
    currentTurn.push(message);
  }
  processTurn(currentTurn);

  return suppressed;
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

  const isSiteConfidenceReport =
    typeof (parsed as UnknownRecord).report_kind === 'string'
    && (parsed as UnknownRecord).report_kind === 'site_confidence_report';

  return [{
    id: outputId,
    type: outputType,
    title: isSiteConfidenceReport
      ? '官网 AI 友好度'
      : ((parsed as UnknownRecord).headline as string || (parsed as UnknownRecord).title as string || msg.content || '分析结果'),
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





