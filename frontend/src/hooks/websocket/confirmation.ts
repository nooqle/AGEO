import type { CanvasContent, CanvasContentDataMap, CanvasContentType } from '@/types/canvas';
import { normalizeCanvasData } from './canvas';

const VALID_CONFIRMATION_CONTENT_TYPES: CanvasContentType[] = ['report', 'chart', 'dataTable', 'pipeline', 'workflow', 'questionList', 'fetchResults'];

export function buildCanvasContentFromConfirmation(content: Record<string, unknown>): CanvasContent {
  const id = typeof content.id === 'string' ? content.id : `canvas_${Date.now()}`;
  const type: CanvasContentType =
    typeof content.type === 'string' && VALID_CONFIRMATION_CONTENT_TYPES.includes(content.type as CanvasContentType)
      ? (content.type as CanvasContentType)
      : 'report';
  const title = typeof content.title === 'string' ? content.title : '分析结果';
  const contentData = normalizeCanvasData(type, content.data) as CanvasContentDataMap['report'];
  const createdAt = content.createdAt instanceof Date
    ? content.createdAt
    : new Date(typeof content.createdAt === 'string' ? content.createdAt : Date.now());
  const relatedMessageId = typeof content.relatedMessageId === 'string' ? content.relatedMessageId : '';

  return {
    id,
    type,
    title,
    data: contentData,
    createdAt,
    relatedMessageId,
    versions: [],
    currentVersionIndex: -1,
  } as CanvasContent;
}

