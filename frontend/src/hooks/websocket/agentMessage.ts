import type { ConfirmationRequest, Message } from '@/types/message';
import type { WebSocketEventData } from '@/types/websocket';

const VALID_CONFIRMATION_TYPES: ConfirmationRequest['type'][] = [
  'brand_info',
  'persona_selection',
  'action_choice',
  'continue',
  'step_confirmation',
];

function buildConfirmationRequest(data: WebSocketEventData): ConfirmationRequest | undefined {
  if (typeof data.confirmation_request !== 'object' || data.confirmation_request === null) {
    return undefined;
  }

  const request = data.confirmation_request as Record<string, unknown>;
  const rawType = typeof request.type === 'string' ? request.type : 'step_confirmation';

  return {
    requestId:
      typeof request.request_id === 'string'
        ? request.request_id
        : typeof request.requestId === 'string'
          ? request.requestId
          : `request_${Date.now()}`,
    type: VALID_CONFIRMATION_TYPES.includes(rawType as ConfirmationRequest['type'])
      ? (rawType as ConfirmationRequest['type'])
      : 'step_confirmation',
    message: typeof request.message === 'string' ? request.message : '',
    options: Array.isArray(request.options) ? request.options : [],
    allowTextInput:
      typeof request.allow_text_input === 'boolean'
        ? request.allow_text_input
        : typeof request.allowTextInput === 'boolean'
          ? request.allowTextInput
          : false,
    stepId:
      typeof request.step_id === 'string'
        ? request.step_id
        : typeof request.stepId === 'string'
          ? request.stepId
          : undefined,
    stepName:
      typeof request.step_name === 'string'
        ? request.step_name
        : typeof request.stepName === 'string'
          ? request.stepName
          : undefined,
  };
}

export function buildAgentMessage(data: WebSocketEventData): Message {
  const relatedOutputIds = Array.isArray(data.related_output_ids) ? data.related_output_ids : [];

  return {
    id: typeof data.id === 'string' ? data.id : `agent_${Date.now()}`,
    type: 'agent',
    content: typeof data.content === 'string' ? data.content : '',
    timestamp: data.timestamp ? new Date(data.timestamp as string) : new Date(),
    tpaor: typeof data.tpaor === 'object' && data.tpaor !== null ? data.tpaor : undefined,
    outputCards: Array.isArray(data.output_cards) ? data.output_cards : undefined,
    confirmationRequest: buildConfirmationRequest(data),
    metadata:
      typeof data.metadata === 'object' && data.metadata !== null
        ? (data.metadata as Message['metadata'])
        : {
            canEdit: false,
            canRollback: true,
            relatedOutputIds,
          },
  };
}
