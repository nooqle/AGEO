import type { CanvasContent, CanvasContentType, CanvasContentDataMap } from '@/types/canvas';
import type { WebSocketEventData } from '@/types/websocket';
import { buildRealtimeOutputCard } from '@/adapters/chatMessage';
import { isRecord, normalizeCanvasData, normalizePreviewData } from './canvas';

const VALID_OUTPUT_TYPES: CanvasContentType[] = ['report', 'chart', 'dataTable', 'pipeline', 'workflow', 'questionList', 'fetchResults'];

export function buildOutputReadyPayload(data: WebSocketEventData, currentAgentMessageId: string | null) {
  const outputTypeStr = typeof data.type === 'string' ? data.type : 'report';
  const canvasTypeStr = outputTypeStr.startsWith('report') ? 'report' : outputTypeStr;
  const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(canvasTypeStr as CanvasContentType)
    ? (canvasTypeStr as CanvasContentType)
    : 'report';
  const relatedMessageId = typeof data.related_message_id === 'string' ? data.related_message_id : '';
  const linkedMessageId = typeof data.linked_message_id === 'string' ? data.linked_message_id : undefined;
  const category =
    data.category === 'baseline' || data.category === 'panorama' || data.category === 'scenario'
      ? data.category
      : undefined;
  const scenarioLabel = typeof data.scenario_label === 'string' ? data.scenario_label : undefined;
  const isSiteConfidenceReport =
    outputType === 'report'
    && isRecord(data.data)
    && data.data.report_kind === 'site_confidence_report';
  const outputTitle = isSiteConfidenceReport
    ? '官网 AI 友好度'
    : (typeof data.title === 'string' ? data.title : '\u5206\u6790\u7ed3\u679c');
  const fallbackId = `output_${outputType}_${outputTitle}_${relatedMessageId || 'global'}`;
  const outputId = typeof data.output_id === 'string' ? data.output_id : fallbackId;
  const outputData = normalizeCanvasData(outputType, data.data) as CanvasContentDataMap['report'];
  const preview = normalizePreviewData(isRecord(data.data) ? data.data : {});
  const createdAt =
    typeof data.timestamp === 'string' && data.timestamp
      ? new Date(data.timestamp)
      : new Date();
  const outputSequence =
    typeof data.sequence === 'number' && Number.isFinite(data.sequence)
      ? data.sequence
      : undefined;

  return {
    outputId,
    targetMessageId: relatedMessageId || currentAgentMessageId,
    content: {
      id: outputId,
      type: outputType,
      title: outputTitle,
      data: outputData,
      createdAt,
      relatedMessageId,
      versions: [],
      currentVersionIndex: -1,
      outputSequence,
      linkedMessageId: currentAgentMessageId || linkedMessageId,
      category,
      scenarioLabel,
    } as CanvasContent,
    card: buildRealtimeOutputCard(outputId, outputType, outputTitle, preview),
  };
}
