'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import type { Message, ExecutionStep, TPAORContent, ConfirmationRequest, ConfirmationOption, ActionLogEntry, SystemNoticeData } from '@/types/message';
import type { TPAORPhase } from '@/types/agent';
import { toast } from '@/components/ui/toast';
import { LLMDecision, ExecutionPlanStep } from '@/types/orchestration';
import { WebSocketEventData } from '@/types/websocket';
import { collectPendingActionLogs, findMatchingPendingActionLog } from '@/hooks/websocket/actionLog';
import { buildAgentMessage } from '@/hooks/websocket/agentMessage';
import { buildBrowserState, buildExecutionProgress } from '@/hooks/websocket/execution';
import { buildCompletedTask, buildFollowUpSuggestions, buildStopState } from '@/hooks/websocket/executionComplete';
import { TPAOR_PHASE_MAP, TPAOR_PHASES, isValidWebSocketMessage } from '@/hooks/websocket/protocol';
import { isRecord } from '@/hooks/websocket/canvas';
import { buildOutputReadyPayload } from '@/hooks/websocket/output';
import { buildCanvasContentFromConfirmation } from '@/hooks/websocket/confirmation';
import { isSupersededA5FailureText } from '@/adapters/chatMessage';
import { api } from '@/services/api';
import type { AnalysisTask } from '@/types/task';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import type { ToolMode } from '@/types/toolMode';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001';
const RUNTIME_STREAM_EVENTS = new Set([
  'action_log',
  'artifact_patch',
  'browser_state',
  'browser_user_action',
  'confirmation_request',
  'error',
  'execution_complete',
  'execution_progress',
  'inline_confirmation',
  'output_ready',
  'plan_update',
  'reply_delta',
  'stage_result',
  'system_notice',
  'thought_delta',
]);

function generateClientMessageId(): string {
  return `client_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

interface AttachmentRefPayload {
  file_id: string;
  name: string;
  mime_type: string;
  size: number;
  sheet_hint?: string;
}

interface QueuedUserMessage {
  clientMessageId: string;
  content: string;
  context?: Array<{ id: string; type: string; label: string }>;
  attachments?: AttachmentRefPayload[];
  tool_mode?: ToolMode;
}

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const agentMessageIdRef = useRef<string | null>(null);
  const pendingMessagesRef = useRef<QueuedUserMessage[]>([]);
  const suppressRuntimeStreamRef = useRef(false);

  const {
    addMessage,
    updateMessage,
    addExecutionStep,
    updateExecutionStep,
    appendExecutionLog,
    updateTPAOR,
    setExecutionProgress,
    setBrowserState,
    updateBrowserState,
    clearBrowserStates,
    startExecution,
    stopExecution,
    setPendingConfirmation,
    setStopState,
    // LLM 编排相关（v2 新增）
    setExecutionPlan,
    updateContextData,
    addDecision,
    setCurrentIntent,
    // 新编排器流式状态
    appendReplyDelta,
    appendThoughtDelta,
    addActionLog,
    updateActionLog,
    completePendingActionLogs,
    setPlanText,
    setInlineConfirmation,
    finalizeCurrentMessage,
    resetStreamingState,
    // Cycle 3: task & follow-up
    setActiveTask,
    updateActiveTaskProgress,
    setFollowUpSuggestions,
    setWsConfirmation,
    setWsArtifactAction,
    setWsBrowserActionResolution,
    // Recall support
    clearMessagesAfter,
    removeMessage,
    clearStageResults,
    replaceMessageId,
  } = useConversationStore();

  const { addContent, patchContent } = useCanvasStore();

  const getAuthToken = useCallback(() => {
    if (typeof window === 'undefined') return null;

    let token = window.localStorage.getItem('access_token');

    // Development mode: Use default dev-token if no token is available
    if (!token && process.env.NODE_ENV === 'development') {
      token = 'dev-token';
      console.warn('[WebSocket] ⚠️  DEVELOPMENT MODE: Using default dev-token');
    }

    return token;
  }, []);

  const flushPendingMessages = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    if (pendingMessagesRef.current.length === 0) return;
    const pending = [...pendingMessagesRef.current];
    pendingMessagesRef.current = [];
    pending.forEach((payload) => {
      suppressRuntimeStreamRef.current = false;
      wsRef.current?.send(JSON.stringify({
        event: 'user_message',
        data: payload,
      }));
    });
  }, []);

  // Event handler function
  const handleEvent = useCallback((eventName: string, data: WebSocketEventData) => {
    console.log(`[WebSocket] Received event: ${eventName}`, data);

    if (
      suppressRuntimeStreamRef.current &&
      RUNTIME_STREAM_EVENTS.has(eventName)
    ) {
      console.log(`[WebSocket] Ignoring stale runtime event after stop: ${eventName}`);
      return;
    }

    switch (eventName) {
      case 'agent_start':
        startExecution();
        agentMessageIdRef.current = null;
        resetStreamingState();
        break;

      case 'tpaor_update': {
        const phase = data.phase || '';
        const mappedPhase = TPAOR_PHASE_MAP[phase] || phase;
        const phaseEn: TPAORPhase = TPAOR_PHASES.includes(mappedPhase as TPAORPhase)
          ? (mappedPhase as TPAORPhase)
          : 'thought';
        updateTPAOR({
          phase: phaseEn,
          content: data.content || '',
          isComplete: data.is_complete ?? false,
          timestamp: new Date(),
        });
        const content = typeof data.content === 'string' ? data.content : '';
        if (TPAOR_PHASES.includes(phaseEn)) {
          if (!agentMessageIdRef.current) {
            const newId = addMessage({
              type: 'agent',
              content: phaseEn === 'response' ? content : '',
              tpaor: { [phaseEn]: content } as TPAORContent,
              metadata: { canEdit: false, canRollback: true, relatedOutputIds: [] },
            });
            agentMessageIdRef.current = newId;
          }
          const id = agentMessageIdRef.current;
          if (id) {
            const existing = useConversationStore.getState().messages.find((m) => m.id === id);
            const newTpaor: TPAORContent = {
              ...(existing?.tpaor || {}),
              [phaseEn]: content,
            };
            const updates: Partial<Message> = {
              tpaor: newTpaor,
            };
            if (phaseEn === 'response') {
              updates.content = content;
            }
            updateMessage(id, updates);
          }
        }
        break;
      }

      // ========== 新编排器事件 ==========

      case 'user_message_ack': {
        // Backend saved the user message and returned its DB UUID.
        // Replace the local random ID with the real UUID so recall can work.
        const dbId = data.message_id as string;
        const ackContent = data.content as string;
        const clientMessageId = data.client_message_id as string | undefined;
        if (dbId && clientMessageId) {
          replaceMessageId(clientMessageId, dbId);
          break;
        }
        if (dbId && ackContent) {
          const { messages } = useConversationStore.getState();
          // Find the most recent user message with matching content
          for (let i = messages.length - 1; i >= 0; i--) {
            if (messages[i].type === 'user' && messages[i].content === ackContent) {
              replaceMessageId(messages[i].id, dbId);
              break;
            }
          }
        }
        break;
      }

      case 'reply_delta': {
        const content = typeof data.content === 'string' ? data.content : '';
        const isDelta = data.is_delta !== false;
        const isComplete = data.is_complete === true;
        const isNewRound = data.is_new_round === true;

        // 如果还没有 agent message，创建一个
        if (!agentMessageIdRef.current) {
          const newId = addMessage({
            type: 'agent',
            content: isDelta ? content : content,
            layers: { actionLogs: [] },
          });
          agentMessageIdRef.current = newId;
          // 同步到 store 的 currentAgentMessageId
          useConversationStore.setState({ currentAgentMessageId: newId });
        }

        // 新一轮编排器回复：finalize 当前消息，创建新消息
        // 这样上一轮 Agent 的内容保留在独立消息中，不会被覆盖
        if (isNewRound && agentMessageIdRef.current) {
          completePendingActionLogs();
          finalizeCurrentMessage();
          useConversationStore.setState({
            streamingReply: '',
            streamingThought: '',
            currentActionLogs: [],
            currentPlanText: null,
          });
          const newId = addMessage({
            type: 'agent',
            content: '',
            layers: { actionLogs: [] },
          });
          agentMessageIdRef.current = newId;
          useConversationStore.setState({ currentAgentMessageId: newId });
        }

        if (isDelta && content) {
          appendReplyDelta(content);
        }

        if (isComplete) {
          // 回复完成，不需要额外操作（finalizeCurrentMessage 在 execution_complete 时调用）
          console.log('[WebSocket] Reply stream complete');
        }
        break;
      }

      case 'thought_delta': {
        const content = typeof data.content === 'string' ? data.content : '';
        const isDelta = data.is_delta !== false;

        if (isDelta && content) {
          // 确保有 agent message
          if (!agentMessageIdRef.current) {
            const newId = addMessage({
              type: 'agent',
              content: '',
              layers: { actionLogs: [] },
            });
            agentMessageIdRef.current = newId;
            useConversationStore.setState({ currentAgentMessageId: newId });
          }
          appendThoughtDelta(content);
        }
        break;
      }

      case 'plan_update': {
        const planText = typeof data.text === 'string' ? data.text : '';
        if (planText) {
          // 确保有 agent message
          if (!agentMessageIdRef.current) {
            const newId = addMessage({
              type: 'agent',
              content: '',
              layers: { actionLogs: [] },
            });
            agentMessageIdRef.current = newId;
            useConversationStore.setState({ currentAgentMessageId: newId });
          }
          setPlanText(planText);
        }
        break;
      }

      case 'action_log': {
        const actionType = typeof data.action_type === 'string' ? data.action_type : 'generic';
        const message = typeof data.message === 'string' ? data.message : '';
        const step = typeof data.step === 'string' ? data.step : '';
        const isComplete = data.is_complete === true;
        const timestamp = typeof data.timestamp === 'string' ? data.timestamp : new Date().toISOString();

        // 确保有 agent message
        if (!agentMessageIdRef.current) {
          const newId = addMessage({
            type: 'agent',
            content: '',
            layers: { actionLogs: [] },
          });
          agentMessageIdRef.current = newId;
          useConversationStore.setState({ currentAgentMessageId: newId });
        }

        const storeState = useConversationStore.getState();
        const existingLogs = collectPendingActionLogs(storeState.currentActionLogs, storeState.messages);
        const existingLog = findMatchingPendingActionLog(existingLogs, {
          actionType,
          message,
          step,
          isComplete,
        });

        if (existingLog) {
          updateActionLog(existingLog.id, {
            actionType: actionType as ActionLogEntry['actionType'],
            message: message || existingLog.message,
            step: step || existingLog.step,
            timestamp,
            isComplete: existingLog.isComplete || isComplete,
          });
        } else {
          const logEntry: ActionLogEntry = {
            id: `log_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`,
            actionType: actionType as ActionLogEntry['actionType'],
            message,
            step,
            timestamp,
            isComplete,
          };
          addActionLog(logEntry);
        }
        break;
      }

      case 'inline_confirmation': {
        const confirmMessage = typeof data.message === 'string' ? data.message : '';
        const options = Array.isArray(data.options) ? data.options : [];

        // 确保有 agent message
        if (!agentMessageIdRef.current) {
          const newId = addMessage({
            type: 'agent',
            content: '',
            layers: { actionLogs: [] },
          });
          agentMessageIdRef.current = newId;
          useConversationStore.setState({ currentAgentMessageId: newId });
        }

        setInlineConfirmation({
          message: confirmMessage,
          options: options.map((opt: Record<string, unknown>) => ({
            id: typeof opt.id === 'string' ? opt.id : String(opt.label || ''),
            label: typeof opt.label === 'string' ? opt.label : '',
            description: typeof opt.description === 'string' ? opt.description : undefined,
          })),
          type: typeof data.type === 'string' && (data.type === 'simple' || data.type === 'guided')
            ? data.type as 'simple' | 'guided'
            : 'simple',
          waitingTips: Array.isArray(data.waiting_tips) ? data.waiting_tips as string[] : undefined,
          estimatedTime: typeof data.estimated_time === 'string' ? data.estimated_time : undefined,
        });

        // Backend is now in wait_for_user state — unlock the UI so user can click buttons or type
        stopExecution();
        break;
      }

      case 'execution_progress': {
        const previousProgress = useConversationStore.getState().executionProgress;
        setExecutionProgress(buildExecutionProgress(data, previousProgress));

        // Only update workflow visualization when steps array is present
        // (agent-level progress events omit steps, which would reset the counter)
        // Workflow progress is shown via MiniProgress in Chat panel only.
        // Canvas space is reserved for analysis results (brand profile, competitors, etc.).

        // Cycle 3: Sync activeTask progress
        updateActiveTaskProgress(
          data.stage || '',
          data.progress ?? 0,
          data.message || data.details || ''
        );
        break;
      }

      case 'step_started': {
        const step: ExecutionStep = {
          stepId: data.step_id || '',
          stepName: data.message || '',
          stepIndex: (typeof data.step_index === 'number' ? data.step_index : 1),
          totalSteps: (typeof data.total_steps === 'number' ? data.total_steps : 5),
          status: 'running',
          description: data.description as string | undefined,
          startTime: new Date(),
        };
        addExecutionStep(step);
        break;
      }

      case 'step_completed':
        updateExecutionStep(data.step_id || '', {
          status: 'completed',
          result: data.output_data as Record<string, unknown> | undefined,
          endTime: new Date(),
        });
        break;

      case 'step_failed':
        updateExecutionStep(data.step_id || '', {
          status: 'failed',
          endTime: new Date(),
        });
        break;

      case 'step_waiting_confirmation':
        updateExecutionStep(data.step_id || '', {
          status: 'waiting_confirmation',
        });
        if (data.confirmation_data) {
          setPendingConfirmation({
            requestId: typeof data.request_id === 'string' ? data.request_id : '',
            type: 'step_confirmation',
            message: data.message || '',
            options: Array.isArray((data.confirmation_data as Record<string, unknown>).options)
              ? ((data.confirmation_data as Record<string, unknown>).options as ConfirmationOption[])
              : [],
            allowTextInput: false,
            stepId: data.step_id,
            stepName: data.step_name,
          });
        }
        break;

      case 'step_log':
        appendExecutionLog(
          (typeof data.step_id === 'string' ? data.step_id : ''),
          (typeof data.log === 'string' ? data.log : '')
        );
        break;

      case 'browser_state':
      case 'browser_user_action':
        setBrowserState(buildBrowserState(data));
        break;

      case 'browser_user_action_ack': {
        const requestId = typeof data.request_id === 'string' ? data.request_id : '';
        const resolution = typeof data.resolution === 'string' ? data.resolution : '';
        if (requestId) {
          updateBrowserState(
            requestId,
            resolution === 'completed'
              ? {
                  requiresAction: false,
                  message: '已收到您的完成确认，正在检查页面状态并继续任务...',
                }
              : {
                  requiresAction: false,
                  message: '已跳过当前平台的人工处理，系统将继续后续流程...',
                },
          );
        }
        break;
      }

      case 'output_ready': {
        const payload = buildOutputReadyPayload(data, agentMessageIdRef.current);
        const targetMessageId = payload.targetMessageId;

        addContent(payload.content);
        const isFinalReportArtifact = payload.content.type === 'report';
        if (targetMessageId) {
          const state = useConversationStore.getState();
          const msg = state.messages.find((m) => m.id === targetMessageId);
          const existingCards = msg?.outputCards || [];
          const alreadyExists = existingCards.some((card) => card.id === payload.outputId);
          const nextContent = payload.content.type === 'report' && isSupersededA5FailureText(msg?.content)
            ? `${payload.card.title}已生成，右侧画布已更新。`
            : msg?.content;
          if (!alreadyExists) {
            updateMessage(targetMessageId, {
              ...(nextContent !== undefined ? { content: nextContent } : {}),
              outputCards: [...existingCards, payload.card],
            });
          } else if (nextContent !== undefined && nextContent !== msg?.content) {
            updateMessage(targetMessageId, {
              content: nextContent,
            });
          }
          if (
            nextContent !== undefined
            && targetMessageId === useConversationStore.getState().currentAgentMessageId
          ) {
            useConversationStore.setState({ streamingReply: nextContent });
          }
        } else {
          console.warn(
            '[WebSocket] output_ready arrived without target message id; canvas updated but card was not attached to chat message.',
            payload.outputId,
          );
        }
        if (isFinalReportArtifact && useConversationStore.getState().isAgentExecuting) {
          const currentProgress = useConversationStore.getState().executionProgress;
          const stage = String(currentProgress?.stage || '').toLowerCase();
          const isReportTerminalStage =
            stage.includes('data_analytics')
            || stage.includes('a5')
            || stage.includes('analysis_report');
          if (isReportTerminalStage || (currentProgress?.progress ?? 0) >= 1) {
            completePendingActionLogs();
            finalizeCurrentMessage();
            resetStreamingState();
            stopExecution();
            setExecutionProgress(null);
            clearBrowserStates();
            setStopState(null);
          }
        }
        break;
      }

      case 'artifact_patch': {
        const artifactId = typeof data.artifact_id === 'string' ? data.artifact_id : '';
        const patch = isRecord(data.patch) ? data.patch : null;
        if (!artifactId || !patch) {
          break;
        }
        patchContent(artifactId, patch as Record<string, unknown>);
        const nextStatus = isRecord((patch as Record<string, unknown>).status)
          ? ((patch as Record<string, unknown>).status as Record<string, unknown>)
          : null;
        const nextPhase = typeof nextStatus?.phase === 'string' ? nextStatus.phase : '';
        const nextMessage = typeof nextStatus?.message === 'string' ? nextStatus.message : '';
        if (nextPhase === 'ready' && nextMessage) {
          toast.success(nextMessage);
        } else if (nextPhase === 'error' && nextMessage) {
          toast.error(nextMessage);
        }
        break;
      }

      case 'confirmation_request': {
        const requestId = typeof data.request_id === 'string' ? data.request_id : '';
        const type: ConfirmationRequest['type'] =
          typeof data.type === 'string' &&
          ['brand_info', 'persona_selection', 'action_choice', 'continue', 'step_confirmation'].includes(data.type)
            ? (data.type as ConfirmationRequest['type'])
            : 'step_confirmation';
        const message = typeof data.message === 'string' ? data.message : '';
        const options = Array.isArray(data.options) ? data.options : [];
        const allowTextInput = typeof data.allow_text_input === 'boolean' ? data.allow_text_input : false;
        const stepId = typeof data.step_id === 'string' ? data.step_id : undefined;
        const stepName = typeof data.step_name === 'string' ? data.step_name : undefined;
        setPendingConfirmation({
          requestId,
          type,
          message,
          options,
          allowTextInput,
          stepId,
          stepName,
        });
        if (data.canvas_content && typeof data.canvas_content === 'object') {
          addContent(buildCanvasContentFromConfirmation(data.canvas_content as Record<string, unknown>));
        }

        break;
      }

      case 'agent_message': {
        addMessage(buildAgentMessage(data));
        break;
      }

      case 'execution_complete': {
        completePendingActionLogs();
        finalizeCurrentMessage();
        resetStreamingState();
        // NOTE: Do NOT reset agentMessageIdRef here.
        // The orchestrator may run multiple rounds (e.g., orchestrator -> agent -> orchestrator).
        // If we reset the ref, the next round's reply_delta creates a duplicate message.
        // The ref is reset in 'agent_start' when a new user message triggers execution.
        stopExecution();
        setExecutionProgress(null);
        clearBrowserStates();
        setStopState(null);

        const completedTask = buildCompletedTask(useConversationStore.getState().activeTask, data);
        if (completedTask) {
          setActiveTask(completedTask);
        }
        const taskId =
          completedTask?.id ||
          useConversationStore.getState().activeTask?.id ||
          (typeof data.task_id === 'string' ? data.task_id : null);
        if (sessionId && taskId) {
          void api.getTask(sessionId, taskId).then((latestTask) => {
            if (latestTask) {
              setActiveTask(latestTask);
            }
          }).catch(() => {
            // Ignore task refresh errors and keep optimistic completion state.
          });
        }

        const suggestions = buildFollowUpSuggestions(data);
        if (suggestions.length > 0) {
          setFollowUpSuggestions(suggestions);
        }
        break;
      }

      case 'execution_stopped':
        suppressRuntimeStreamRef.current = true;
        completePendingActionLogs('（已停止）');
        finalizeCurrentMessage();
        resetStreamingState();
        stopExecution();
        setExecutionProgress(null);
        clearBrowserStates();
        if (data) {
          setStopState(buildStopState(data));
        }
        break;

      case 'recall_complete': {
        // Backend has deleted DB messages. Now clean up frontend state.
        const recallMessageId = data.message_id as string;
        // 1. Clear messages from store (target + everything after)
        clearMessagesAfter(recallMessageId);
        removeMessage(recallMessageId);

        // 2. Clear stage results and execution progress
        clearStageResults();
        setExecutionProgress(null);
        clearBrowserStates();

        // 3. Reset execution / stop / task / confirmation state (BUG-RECALL-01/03/06)
        stopExecution();
        setStopState(null);
        setActiveTask(null);
        setFollowUpSuggestions([]);
        setPendingConfirmation(null);

        // 4. Clear Canvas, then trigger reload of surviving artifacts from DB
        useCanvasStore.getState().clearContents();
        window.dispatchEvent(new CustomEvent('recall-reload-artifacts'));

        // 5. Notify ChatPanel to fill input box with recalled message content
        window.dispatchEvent(new CustomEvent('recall-fill-input', {
          detail: { messageId: recallMessageId },
        }));
        break;
      }

      case 'error': {
        // Guard: require non-empty string in message or error field.
        // Empty/missing fields come from ASGI lifecycle events during
        // hot-reload or disconnect and should not interrupt running tasks.
        const errorMsg =
          (typeof data.message === 'string' && data.message.trim()) ||
          (typeof data.error === 'string' && data.error.trim()) ||
          null;
        if (!errorMsg) {
          console.warn('[WebSocket] Received empty error event, ignoring:', data);
          break;
        }
        console.warn('[WebSocket] Error event:', errorMsg, data);
        toast.error(errorMsg);
        completePendingActionLogs('（已中断）');
        // 所有有效错误都解锁输入框 — 用户必须随时可以继续输入或重试
        stopExecution();
        break;
      }

      // LLM 编排相关事件（v2 新增）
      case 'llm_decision': {
        const decision = data as unknown as LLMDecision;
        addDecision(decision);
        setCurrentIntent(decision.user_intent);
        console.log('[LLM Decision]', decision.intent_type, decision.reasoning);
        break;
      }

      case 'plan_created': {
        const planData = data as { plan: ExecutionPlanStep[] };
        setExecutionPlan(planData.plan);
        break;
      }

      case 'plan_updated': {
        const planData = data as { plan: ExecutionPlanStep[]; reason: string };
        setExecutionPlan(planData.plan);
        console.log('[Plan Updated]', planData.reason);
        break;
      }

      case 'agent_call_start': {
        console.log(`[Agent Call Start] ${data.agent_id}: ${data.agent_name} - ${data.reason}`);
        break;
      }

      case 'agent_call_complete': {
        console.log(`[Agent Call Complete] ${data.agent_id}: ${data.success ? 'success' : 'failed'}`);
        if (data.success && data.output && typeof data.output === 'object') {
          Object.entries(data.output as Record<string, unknown>).forEach(([key, value]) => {
            updateContextData(key, value);
          });
        }
        break;
      }

      case 'context_updated':
        console.log('[Context Updated]', data.data_keys);
        break;

      case 'stage_result': {
        const stageResult = {
          stage: typeof data.stage === 'string' ? data.stage : '',
          stageName: typeof data.stage_name === 'string'
            ? data.stage_name
            : typeof data.stageName === 'string'
            ? data.stageName
            : '',
          resultType: typeof data.result_type === 'string'
            ? data.result_type
            : typeof data.resultType === 'string'
            ? data.resultType
            : 'brand_profile',
          data: isRecord(data.data) ? data.data : {},
          timestamp: typeof data.timestamp === 'string' ? data.timestamp : new Date().toISOString(),
        };
        useConversationStore.getState().addStageResult(stageResult as import('@/types/snapshot').StageResult);

        const stageToStep: Record<string, string> = {
          A1: 'brand_analysis',
          A2: 'persona_generation',
          A3: 'question_simulation',
          A4: 'answer_fetch',
          A5: 'data_analytics',
        };
        const mappedStep = stageToStep[stageResult.stage];
        if (mappedStep) {
          const storeState = useConversationStore.getState();
          const existingLogs = collectPendingActionLogs(storeState.currentActionLogs, storeState.messages);
          const pendingLog = findMatchingPendingActionLog(existingLogs, {
            actionType: 'tool_call',
            message: stageResult.stageName || mappedStep,
            step: mappedStep,
            isComplete: true,
          });
          if (pendingLog) {
            const completedLabel = stageResult.stageName || pendingLog.message.replace(/^调用\s+/, '').replace(/(?:\.\.\.|…)+$/, '');
            updateActionLog(pendingLog.id, {
              isComplete: true,
              step: pendingLog.step || mappedStep,
              message: `${completedLabel} 完成`,
            });
          }
        }

        console.log(`[WebSocket] Stage result: ${stageResult.stage} (${stageResult.resultType})`);
        break;
      }

      case 'system_notice': {
        // Degradation / platform_status notices from resilience layer
        const subtype = typeof data.subtype === 'string'
          ? (data.subtype as SystemNoticeData['subtype'])
          : 'degradation';
        const level = typeof data.level === 'string' &&
          ['info', 'warning', 'error'].includes(data.level)
          ? (data.level as SystemNoticeData['level'])
          : 'warning';
        const noticeTitle = typeof data.title === 'string' ? data.title : '';
        const description = typeof data.description === 'string' ? data.description : undefined;
        const impact = typeof data.impact === 'string' ? data.impact : undefined;
        const platforms = Array.isArray(data.platforms)
          ? data.platforms.map((p: Record<string, unknown>) => ({
              name: typeof p.name === 'string' ? p.name : '',
              status: typeof p.status === 'string' &&
                ['success', 'failed', 'skipped'].includes(p.status)
                ? (p.status as 'success' | 'failed' | 'skipped')
                : 'failed',
              detail: typeof p.detail === 'string' ? p.detail : undefined,
            }))
          : undefined;

        const noticeData: SystemNoticeData = {
          subtype,
          level,
          title: noticeTitle,
          description,
          impact,
          platforms,
        };

        addMessage({
          type: 'system_notice',
          content: noticeTitle,
          systemNotice: noticeData,
          metadata: { canEdit: false, canRollback: false, relatedOutputIds: [] },
        });

        console.log(`[WebSocket] System notice: ${subtype} - ${noticeTitle}`);
        break;
      }

      case 'task_status_change': {
        // Cycle 3: Task lifecycle event from backend
        const taskStatus = typeof data.status === 'string' ? data.status : '';
        const taskData = typeof data.task === 'object' && data.task !== null
          ? data.task as Record<string, unknown>
          : data;
        const hasTaskPayload = typeof taskData.id === 'string';
        const currentTask = useConversationStore.getState().activeTask;
        const latestRunStatus = isRecord(taskData.latest_run)
          && typeof taskData.latest_run.status === 'string'
          ? taskData.latest_run.status
          : '';

        if (hasTaskPayload) {
          setActiveTask({
            ...(currentTask ?? {}),
            ...(taskData as unknown as AnalysisTask),
            status: (taskStatus || taskData.status || currentTask?.status || 'pending') as AnalysisTask['status'],
          } as AnalysisTask);
        }

        if (taskStatus === 'running' && latestRunStatus === 'waiting_input') {
          stopExecution();
          setExecutionProgress(null);
        } else if (taskStatus === 'running') {
          updateActiveTaskProgress(
            typeof taskData.current_stage === 'string' ? taskData.current_stage : '',
            typeof taskData.progress === 'number' ? taskData.progress : 0,
            typeof taskData.progress_message === 'string' ? taskData.progress_message : '分析中...'
          );
        } else if (taskStatus === 'completed') {
          const ct = useConversationStore.getState().activeTask;
          if (ct) {
            setActiveTask({
              ...ct,
              status: 'completed',
              progress: 1.0,
              progress_message: '分析完成',
              completed_at: typeof taskData.completed_at === 'string' ? taskData.completed_at : new Date().toISOString(),
              snapshot_id: typeof taskData.snapshot_id === 'string' ? taskData.snapshot_id : ct.snapshot_id,
              llm_call_count: typeof taskData.llm_call_count === 'number' ? taskData.llm_call_count : ct.llm_call_count,
              llm_prompt_tokens: typeof taskData.llm_prompt_tokens === 'number' ? taskData.llm_prompt_tokens : ct.llm_prompt_tokens,
              llm_completion_tokens: typeof taskData.llm_completion_tokens === 'number' ? taskData.llm_completion_tokens : ct.llm_completion_tokens,
              llm_total_tokens: typeof taskData.llm_total_tokens === 'number' ? taskData.llm_total_tokens : ct.llm_total_tokens,
              llm_total_latency_ms: typeof taskData.llm_total_latency_ms === 'number' ? taskData.llm_total_latency_ms : ct.llm_total_latency_ms,
              llm_estimated_cost: typeof taskData.llm_estimated_cost === 'number' ? taskData.llm_estimated_cost : ct.llm_estimated_cost,
            });
          }
        } else if (taskStatus === 'cancelled') {
          suppressRuntimeStreamRef.current = true;
          const ct = useConversationStore.getState().activeTask;
          if (ct) {
            setActiveTask({
              ...ct,
              status: 'cancelled',
              progress_message: typeof taskData.progress_message === 'string' ? taskData.progress_message : '任务已取消',
              completed_at: typeof taskData.completed_at === 'string' ? taskData.completed_at : new Date().toISOString(),
            });
          }
        } else if (taskStatus === 'failed') {
          const ft = useConversationStore.getState().activeTask;
          if (ft) {
            setActiveTask({
              ...ft,
              status: 'failed',
              llm_call_count: typeof taskData.llm_call_count === 'number' ? taskData.llm_call_count : ft.llm_call_count,
              llm_prompt_tokens: typeof taskData.llm_prompt_tokens === 'number' ? taskData.llm_prompt_tokens : ft.llm_prompt_tokens,
              llm_completion_tokens: typeof taskData.llm_completion_tokens === 'number' ? taskData.llm_completion_tokens : ft.llm_completion_tokens,
              llm_total_tokens: typeof taskData.llm_total_tokens === 'number' ? taskData.llm_total_tokens : ft.llm_total_tokens,
              llm_total_latency_ms: typeof taskData.llm_total_latency_ms === 'number' ? taskData.llm_total_latency_ms : ft.llm_total_latency_ms,
              llm_estimated_cost: typeof taskData.llm_estimated_cost === 'number' ? taskData.llm_estimated_cost : ft.llm_estimated_cost,
              error_message: typeof taskData.error_message === 'string' ? taskData.error_message : null,
              error_stage: typeof taskData.error_stage === 'string' ? taskData.error_stage : null,
            });
          }
        }
        console.log(`[WebSocket] Task status change: ${taskStatus}`);
        break;
      }

      case 'pong':
        // Heartbeat response from server
        console.log('[WebSocket] Heartbeat pong received');
        break;

      case 'heartbeat':
        // Server heartbeat - respond with pong
        if (wsRef.current?.readyState === WebSocket.OPEN) {
          wsRef.current.send(JSON.stringify({ event: 'ping', data: {} }));
        }
        break;

      default:
        console.warn(`[WebSocket] Unknown event: ${eventName}`, data);
    }
  }, [
    addMessage,
    updateMessage,
    addExecutionStep,
    updateExecutionStep,
    appendExecutionLog,
    updateTPAOR,
    setExecutionProgress,
    setBrowserState,
    updateBrowserState,
    clearBrowserStates,
    startExecution,
    stopExecution,
    setPendingConfirmation,
    setStopState,
    setExecutionPlan,
    updateContextData,
    addDecision,
    setCurrentIntent,
    appendReplyDelta,
    appendThoughtDelta,
    addActionLog,
    updateActionLog,
    completePendingActionLogs,
    setPlanText,
    setInlineConfirmation,
    finalizeCurrentMessage,
    resetStreamingState,
    addContent,
    patchContent,
    setActiveTask,
    updateActiveTaskProgress,
    setFollowUpSuggestions,
    clearMessagesAfter,
    removeMessage,
    clearStageResults,
    replaceMessageId,
    sessionId,
  ]);

  useEffect(() => {
    if (!sessionId || sessionId === 'new') return;

    const maxReconnectAttempts = 5;
    const baseReconnectDelay = 1000;
    // Guard flag: prevents stale closures (e.g. React strict mode cleanup) from
    // triggering reconnection after the effect has been torn down.
    let isActive = true;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const connect = () => {
      if (!isActive) return;

      try {
        console.log('[WebSocket] Initiating connection...');

        const token = getAuthToken();
        if (!token) {
          console.error('[WebSocket] Missing auth token');
          setIsConnected(false);
          return;
        }

        const wsUrl = `${WS_URL}/ws/${sessionId}?token=${encodeURIComponent(token)}`;

        // 关闭旧连接（移除事件监听器以防止触发重连）
        if (wsRef.current) {
          const oldWs = wsRef.current;
          wsRef.current = null;
          oldWs.onclose = null;
          oldWs.onerror = null;
          oldWs.close();
        }

        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => {
          if (!isActive) { ws.close(); return; }
          console.log('[WebSocket] Connection opened');
          setIsConnected(true);
          reconnectCountRef.current = 0;
          flushPendingMessages();
        };

        ws.onmessage = (event) => {
          if (!isActive) return;
          try {
            const message = JSON.parse(event.data);
            if (!isValidWebSocketMessage(message)) return;

            const { event: eventName, data } = message;

            if (typeof window !== 'undefined') {
              window.dispatchEvent(new CustomEvent('websocket-message', {
                detail: { event: eventName, data, rawData: event.data }
              }));
            }

            handleEvent(eventName, data);
          } catch (error) {
            console.error('[WebSocket] Error parsing message:', error);
          }
        };

        ws.onclose = (event) => {
          // If effect was cleaned up, do not reconnect
          if (!isActive) return;

          // Suppress noisy log for initial 1006 close (expected on first connect)
          const isInitial1006 = event.code === 1006 && reconnectCountRef.current === 0;
          if (!isInitial1006) {
            console.log(`[WebSocket] Connection closed (code=${event.code}, reason=${event.reason || 'none'})`);
          }
          setIsConnected(false);
          wsRef.current = null;

          // Auto reconnect with exponential backoff
          if (reconnectCountRef.current < maxReconnectAttempts) {
            const delay = baseReconnectDelay * Math.pow(2, reconnectCountRef.current);
            if (!isInitial1006) {
              console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${reconnectCountRef.current + 1}/${maxReconnectAttempts})`);
            }

            reconnectTimer = setTimeout(() => {
              if (!isActive) return;
              reconnectCountRef.current++;
              connect();
            }, delay);
          } else {
            console.error('[WebSocket] Max reconnection attempts reached');
          }
        };

        ws.onerror = () => {
          // Browser limits error details; onclose will fire after this
        };
      } catch (error) {
        console.error('[WebSocket] Error creating connection:', error);
      }
    };

    // Small delay before first connection to let backend fully initialise
    // (avoids the common 1006 on the very first attempt)
    const initialTimer = setTimeout(connect, 300);

    // Heartbeat
    heartbeatRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ event: 'ping', data: {} }));
      }
    }, 30000);

    // Reconnect when the page becomes visible again (e.g. after tab switch or backend restart)
    const handleVisibilityChange = () => {
      if (
        document.visibilityState === 'visible' &&
        isActive &&
        (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN)
      ) {
        console.log('[WebSocket] Page became visible, reconnecting...');
        reconnectCountRef.current = 0;
        if (reconnectTimer) clearTimeout(reconnectTimer);
        reconnectTimer = null;
        connect();
      }
    };
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      isActive = false;
      clearTimeout(initialTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      if (heartbeatRef.current) {
        clearInterval(heartbeatRef.current);
        heartbeatRef.current = null;
      }
      if (wsRef.current) {
        // Detach handlers before closing to prevent stale reconnect
        const ws = wsRef.current;
        wsRef.current = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.close();
      }
    };
  }, [sessionId, handleEvent, getAuthToken, flushPendingMessages]);

  // ========== Send methods ==========

  // Send user message
  const sendMessage = useCallback((
    content: string,
    context?: Array<{ id: string; type: string; label: string }>,
    attachments?: Attachment[],
    toolMode?: ToolMode | null,
  ) => {
    const clientMessageId = generateClientMessageId();
    const payload: QueuedUserMessage = {
      clientMessageId,
      content,
    };
    if (context && context.length > 0) {
      payload.context = context;
    }
    if (attachments && attachments.length > 0) {
      const validAttachments = attachments.filter(
        (attachment): attachment is Attachment & { id: string } =>
          typeof attachment.id === 'string' && attachment.id.trim().length > 0
      );

      if (validAttachments.length > 0) {
        payload.attachments = validAttachments.map((attachment) => ({
          file_id: attachment.id,
          name: attachment.name,
          mime_type: typeof attachment.type === 'string' ? attachment.type : '',
          size: typeof attachment.size === 'number' ? attachment.size : 0,
        }));
      }
    }
    if (toolMode) {
      payload.tool_mode = toolMode;
    }

    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      pendingMessagesRef.current.push(payload);
      return;
    }

    suppressRuntimeStreamRef.current = false;
    // Reset agent message ref so the next reply_delta creates a NEW message
    // (instead of overwriting the previous agent message)
    agentMessageIdRef.current = null;
    resetStreamingState();

    wsRef.current.send(JSON.stringify({
      event: 'user_message',
      data: payload,
    }));
  }, [resetStreamingState]);

  // Send confirmation
  const sendConfirmation = useCallback((requestId: string, selection: string | Record<string, unknown>) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    suppressRuntimeStreamRef.current = false;
    // Reset agent message ref so the next reply_delta creates a NEW message
    // (instead of overwriting the previous agent message)
    agentMessageIdRef.current = null;
    resetStreamingState();

    wsRef.current.send(JSON.stringify({
      event: 'confirmation',
      data: {
        request_id: requestId,
        selection,
      },
    }));
    setPendingConfirmation(null);
  }, [setPendingConfirmation, resetStreamingState]);

  // Register sendConfirmation in store so Canvas components can reuse it without creating new WS connections
  useEffect(() => {
    setWsConfirmation(sendConfirmation);
    return () => {
      setWsConfirmation(null);
    };
  }, [sendConfirmation, setWsConfirmation]);

  const sendArtifactAction = useCallback((artifactId: string, action: string, payload: Record<string, unknown> = {}) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      event: 'artifact_action',
      data: {
        artifact_id: artifactId,
        action,
        payload,
      },
    }));
  }, []);

  useEffect(() => {
    setWsArtifactAction(sendArtifactAction);
    return () => {
      setWsArtifactAction(null);
    };
  }, [sendArtifactAction, setWsArtifactAction]);

  const sendBrowserActionResolution = useCallback((requestId: string, resolution: 'completed' | 'skip') => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({
      event: 'browser_action_resolution',
      data: {
        request_id: requestId,
        resolution,
      },
    }));
  }, []);

  useEffect(() => {
    setWsBrowserActionResolution(sendBrowserActionResolution);
    return () => {
      setWsBrowserActionResolution(null);
    };
  }, [sendBrowserActionResolution, setWsBrowserActionResolution]);

  // Send step control
  const sendStepControl = useCallback((action: 'continue' | 'skip' | 'retry', stepId?: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      event: 'step_control',
      data: {
        action,
        step_id: stepId,
      },
    }));
  }, []);

  // Stop execution
  const sendStop = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      event: 'stop',
      data: {},
    }));
  }, []);

  // Continue execution
  const resumeExecution = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      event: 'resume',
      data: {},
    }));
    setStopState(null);
  }, [setStopState]);

  // Rollback
  const rollback = useCallback((messageId: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({
      event: 'rollback',
      data: { message_id: messageId },
    }));
  }, []);

  // Recall (rollback + re-execute)
  const sendRecall = useCallback((messageId: string) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn('[WebSocket] Cannot send recall: connection not open (readyState:', wsRef.current?.readyState, ')');
      window.dispatchEvent(new CustomEvent('websocket-send-failed', {
        detail: { action: 'recall' },
      }));
      return;
    }

    wsRef.current.send(JSON.stringify({
      event: 'recall',
      data: { message_id: messageId },
    }));
  }, []);

  return {
    sendMessage,
    sendConfirmation,
    sendArtifactAction,
    sendStepControl,
    stopExecution: sendStop,
    resumeExecution,
    rollback,
    sendRecall,
    isConnected,
  };
}










