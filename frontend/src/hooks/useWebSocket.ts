'use client';

import { useEffect, useRef, useCallback, useState } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import type { Message, ExecutionStep, TPAORContent, ConfirmationRequest, ConfirmationOption, ActionLogEntry, SystemNoticeData } from '@/types/message';
import type { CanvasContent, CanvasContentDataMap, CanvasContentType, CanvasPreviewMetricValue } from '@/types/canvas';
import type { TPAORPhase, ExecutionProgress, ProgressStep, SubTask, BrowserState } from '@/types/agent';
import { toast } from '@/components/ui/toast';
import { LLMDecision, ExecutionPlanStep } from '@/types/orchestration';
import { WebSocketEventData } from '@/types/websocket';

const WS_URL = process.env.NEXT_PUBLIC_WS_URL || 'ws://localhost:8001';

/** Map backend step status to frontend ProgressStep status */
function _mapStepStatus(status: string | undefined): ProgressStep['status'] {
  switch (status) {
    case 'completed': return 'completed';
    case 'in_progress':
    case 'running': return 'in_progress';
    case 'error': return 'error';
    case 'skipped': return 'skipped';
    default: return 'pending';
  }
}

// TPAOR phase mapping from Chinese to English
const TPAOR_PHASE_MAP: Record<string, string> = {
  '思考': 'thought',
  '规划': 'plan',
  '行动': 'action',
  '观察': 'observation',
  '回复': 'response',
};

const TPAOR_PHASES: TPAORPhase[] = ['thought', 'plan', 'action', 'observation', 'response'];
const EXECUTION_STATUSES: ExecutionProgress['status'][] = ['pending', 'running', 'completed', 'failed'];
const BROWSER_STATES: BrowserState['state'][] = [
  'idle',
  'initializing',
  'navigating',
  'checking_login',
  'waiting_for_login',
  'waiting_for_modal',
  'logged_in',
  'enabling_search',
  'submitting',
  'waiting_response',
  'extracting',
  'completed',
  'error',
];
const BROWSER_PLATFORMS: BrowserState['platform'][] = ['kimi', 'deepseek', 'doubao', 'hunyuan'];

// WebSocket message validation
interface WebSocketMessage {
  event: string;
  data: WebSocketEventData;
}

function isValidWebSocketMessage(message: unknown): message is WebSocketMessage {
  if (!message || typeof message !== 'object') {
    return false;
  }

  const msg = message as Record<string, unknown>;

  // 验证 event 字段
  if (typeof msg.event !== 'string' || !msg.event) {
    return false;
  }

  // 验证 data 字段存在（可以是任何类型）
  if (!('data' in msg)) {
    return false;
  }

  return true;
}

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null;

const normalizePreviewData = (raw: Record<string, unknown>) => ({
  description: typeof raw.description === 'string' ? raw.description : undefined,
  metrics: isRecord(raw.metrics) ? (raw.metrics as Record<string, CanvasPreviewMetricValue>) : undefined,
  itemCount: typeof raw.itemCount === 'number'
    ? raw.itemCount
    : Array.isArray(raw.items)
    ? raw.items.length
    : undefined,
});

const normalizeCanvasData = <T extends CanvasContentType>(
  type: T,
  raw: unknown
): CanvasContentDataMap[T] => {
  const data = isRecord(raw) ? raw : {};
  const preview = normalizePreviewData(data);

  if (type === 'report') {
    const insights = Array.isArray(data.insights)
      ? (data.insights as CanvasContentDataMap['report']['insights'])
      : undefined;
    const recommendations = Array.isArray(data.recommendations)
      ? (data.recommendations as CanvasContentDataMap['report']['recommendations'])
      : undefined;

    // Validate and pass through bwvs_breakdown only if all four scores are numbers
    const rawBreakdown = isRecord(data.bwvs_breakdown) ? data.bwvs_breakdown : undefined;
    const bwvs_breakdown = rawBreakdown &&
      typeof rawBreakdown.mention_score === 'number' &&
      typeof rawBreakdown.sentiment_score === 'number' &&
      typeof rawBreakdown.coverage_score === 'number' &&
      typeof rawBreakdown.citation_score === 'number' &&
      isRecord(rawBreakdown.weights)
      ? (rawBreakdown as unknown as CanvasContentDataMap['report']['bwvs_breakdown'])
      : undefined;

    return {
      ...preview,
      headline: typeof data.headline === 'string' ? data.headline : undefined,
      subtitle: typeof data.subtitle === 'string' ? data.subtitle : undefined,
      overallScore: typeof data.overallScore === 'number'
        ? data.overallScore
        : typeof data.overall_score === 'number'
        ? data.overall_score
        : undefined,
      scoreBand: typeof data.scoreBand === 'string'
        ? data.scoreBand
        : typeof data.score_band === 'string'
        ? data.score_band
        : undefined,
      metrics: isRecord(data.metrics)
        ? (data.metrics as Record<string, CanvasPreviewMetricValue>)
        : preview.metrics,
      insights,
      recommendations,
      content: typeof data.content === 'string' ? data.content : undefined,
      bwvs_breakdown,
      // A5 extended fields passthrough (consumed by ReportContent via ext = data as Record<string, unknown>)
      key_findings: data.key_findings,
      strengths: data.strengths,
      weaknesses: data.weaknesses,
      opportunities: data.opportunities,
      threats: data.threats,
      action_plan: data.action_plan,
      platform_breakdown: data.platform_breakdown,
      sentiment_distribution: data.sentiment_distribution,
      industry_insights: data.industry_insights,
      platform_analysis: data.platform_analysis,
      competitor_deep_analysis: data.competitor_deep_analysis,
      risk_alerts: data.risk_alerts,
      delta_vs_previous: data.delta_vs_previous,
      competitor_bwvs: data.competitor_bwvs,
      _degradation_note: typeof data._degradation_note === 'string' ? data._degradation_note : undefined,
      citation_analysis: data.citation_analysis,
    } as CanvasContentDataMap[T];
  }

  if (type === 'chart') {
    return {
      ...preview,
      chartType: typeof data.chartType === 'string'
        ? (data.chartType as CanvasContentDataMap['chart']['chartType'])
        : typeof data.chart_type === 'string'
        ? (data.chart_type as CanvasContentDataMap['chart']['chartType'])
        : undefined,
      data: Array.isArray(data.data)
        ? (data.data as CanvasContentDataMap['chart']['data'])
        : undefined,
      xAxisKey: typeof data.xAxisKey === 'string'
        ? data.xAxisKey
        : typeof data.x_axis_key === 'string'
        ? data.x_axis_key
        : undefined,
      valueKey: typeof data.valueKey === 'string'
        ? data.valueKey
        : typeof data.value_key === 'string'
        ? data.value_key
        : undefined,
      angleKey: typeof data.angleKey === 'string'
        ? data.angleKey
        : typeof data.angle_key === 'string'
        ? data.angle_key
        : undefined,
      series: Array.isArray(data.series)
        ? (data.series as CanvasContentDataMap['chart']['series'])
        : undefined,
      summary: typeof data.summary === 'string' ? data.summary : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'dataTable') {
    return {
      ...preview,
      columns: Array.isArray(data.columns)
        ? (data.columns as CanvasContentDataMap['dataTable']['columns'])
        : undefined,
      rows: Array.isArray(data.rows)
        ? (data.rows as CanvasContentDataMap['dataTable']['rows'])
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'pipeline') {
    return {
      ...preview,
      pipeline: data.pipeline && typeof data.pipeline === 'object'
        ? data.pipeline as CanvasContentDataMap['pipeline']['pipeline']
        : undefined,
      maxSelection: typeof data.maxSelection === 'number'
        ? data.maxSelection
        : typeof data.max_selection === 'number'
        ? data.max_selection
        : undefined,
      minSelection: typeof data.minSelection === 'number'
        ? data.minSelection
        : typeof data.min_selection === 'number'
        ? data.min_selection
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'workflow') {
    const statusOptions: Array<NonNullable<CanvasContentDataMap['workflow']['executionStatus']>> = [
      'idle',
      'running',
      'paused',
      'completed',
      'error',
    ];
    const rawStatus = typeof data.executionStatus === 'string'
      ? data.executionStatus
      : typeof data.execution_status === 'string'
      ? data.execution_status
      : undefined;
    const executionStatus = rawStatus && statusOptions.includes(rawStatus as NonNullable<CanvasContentDataMap['workflow']['executionStatus']>)
      ? (rawStatus as NonNullable<CanvasContentDataMap['workflow']['executionStatus']>)
      : undefined;

    return {
      ...preview,
      currentStep: typeof data.currentStep === 'string'
        ? data.currentStep
        : typeof data.current_step === 'string'
        ? data.current_step
        : undefined,
      executionStatus,
      completedSteps: Array.isArray(data.completedSteps)
        ? (data.completedSteps as CanvasContentDataMap['workflow']['completedSteps'])
        : Array.isArray(data.completed_steps)
        ? (data.completed_steps as CanvasContentDataMap['workflow']['completedSteps'])
        : undefined,
      brandProfile: isRecord(data.brandProfile)
        ? (data.brandProfile as CanvasContentDataMap['workflow']['brandProfile'])
        : undefined,
      brand_profile: isRecord(data.brand_profile)
        ? (data.brand_profile as CanvasContentDataMap['workflow']['brand_profile'])
        : undefined,
      competitors: Array.isArray(data.competitors)
        ? (data.competitors as CanvasContentDataMap['workflow']['competitors'])
        : undefined,
      competitive_landscape: isRecord(data.competitive_landscape)
        ? (data.competitive_landscape as CanvasContentDataMap['workflow']['competitive_landscape'])
        : undefined,
      personas: Array.isArray(data.personas)
        ? (data.personas as CanvasContentDataMap['workflow']['personas'])
        : undefined,
      user_personas: Array.isArray(data.user_personas)
        ? (data.user_personas as CanvasContentDataMap['workflow']['user_personas'])
        : undefined,
      brand_summary: isRecord(data.brand_summary)
        ? (data.brand_summary as CanvasContentDataMap['workflow']['brand_summary'])
        : undefined,
      selection: isRecord(data.selection)
        ? (data.selection as CanvasContentDataMap['workflow']['selection'])
        : undefined,
    } as CanvasContentDataMap[T];
  }

  if (type === 'questionList') {
    return {
      ...preview,
      questions: Array.isArray(data.questions)
        ? (data.questions as CanvasContentDataMap['questionList']['questions'])
        : undefined,
      simulatedQuestions: isRecord(data.simulatedQuestions)
        ? (data.simulatedQuestions as CanvasContentDataMap['questionList']['simulatedQuestions'])
        : isRecord(data.simulated_questions)
        ? (data.simulated_questions as CanvasContentDataMap['questionList']['simulatedQuestions'])
        : undefined,
      generationMode: typeof data.generationMode === 'string'
        ? data.generationMode
        : typeof data.generation_mode === 'string'
        ? data.generation_mode
        : undefined,
    } as CanvasContentDataMap[T];
  }

  return {
    ...preview,
    fetchResults: Array.isArray(data.fetchResults)
      ? (data.fetchResults as CanvasContentDataMap['fetchResults']['fetchResults'])
      : Array.isArray(data.fetch_results)
      ? (data.fetch_results as CanvasContentDataMap['fetchResults']['fetchResults'])
      : undefined,
  } as CanvasContentDataMap[T];
};

export function useWebSocket(sessionId: string | null) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const heartbeatRef = useRef<NodeJS.Timeout | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const agentMessageIdRef = useRef<string | null>(null);
  const pendingMessagesRef = useRef<string[]>([]);

  const {
    addMessage,
    updateMessage,
    addExecutionStep,
    updateExecutionStep,
    appendExecutionLog,
    updateTPAOR,
    setExecutionProgress,
    setBrowserState,
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
    setPlanText,
    setInlineConfirmation,
    finalizeCurrentMessage,
    resetStreamingState,
    // Cycle 3: task & follow-up
    setActiveTask,
    updateActiveTaskProgress,
    setFollowUpSuggestions,
    setWsConfirmation,
    // Recall support
    clearMessagesAfter,
    removeMessage,
    clearStageResults,
    replaceMessageId,
  } = useConversationStore();

  const { addContent } = useCanvasStore();

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
    pending.forEach((content) => {
      wsRef.current?.send(JSON.stringify({
        event: 'user_message',
        data: { content },
      }));
    });
  }, []);

  // Event handler function
  const handleEvent = useCallback((eventName: string, data: WebSocketEventData) => {
    console.log(`[WebSocket] Received event: ${eventName}`, data);

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

        // 查找是否已有同 step 的日志（用于更新完成状态）
        const existingLogs = useConversationStore.getState().currentActionLogs;
        const existingLog = step ? existingLogs.find(l => l.step === step && !l.isComplete) : null;

        if (existingLog && isComplete) {
          updateActionLog(existingLog.id, { isComplete: true, message });
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
        const mappedSteps: ProgressStep[] = Array.isArray(data.steps)
          ? (data.steps.map((s, index) => ({
              id: String((s as Record<string, unknown>).id || index),
              label: String((s as Record<string, unknown>).label || (s as Record<string, unknown>).id || ''),
              status: _mapStepStatus((s as Record<string, unknown>).status as string),
            })) as ProgressStep[])
          : (useConversationStore.getState().executionProgress?.steps || []);

        // Merge with existing steps: a completed step must not regress to pending
        // This guards against out-of-order backend events (e.g. A4 still running
        // but a new progress event carries A4=pending in the steps array).
        const oldSteps = useConversationStore.getState().executionProgress?.steps || [];
        const mergedSteps = mappedSteps.map((newStep: ProgressStep) => {
          const oldStep = oldSteps.find((s: ProgressStep) => s.id === newStep.id);
          if (oldStep?.status === 'completed' && newStep.status === 'pending') {
            return { ...newStep, status: 'completed' as const };
          }
          return newStep;
        });

        // Guard: progress must never go backwards (multiple parallel pipelines
        // in Full mode can emit out-of-order progress values)
        const oldProgress = useConversationStore.getState().executionProgress?.progress ?? 0;
        const newProgress = data.progress ?? 0;
        const safeProgress = Math.max(oldProgress, newProgress);

        setExecutionProgress({
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
        });

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
            requestId: (typeof data.request_id === 'string' ? data.request_id : `step_${data.step_id || ''}`),
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
        setBrowserState({
          state: BROWSER_STATES.includes((data.state || '') as BrowserState['state'])
            ? ((data.state || '') as BrowserState['state'])
            : 'idle',
          message: data.message || '',
          platform: BROWSER_PLATFORMS.includes((data.platform || '') as BrowserState['platform'])
            ? ((data.platform || '') as BrowserState['platform'])
            : 'kimi',
          requiresAction: typeof data.requires_action === 'boolean' ? data.requires_action : false,
          actionHint: typeof data.action_hint === 'string' ? data.action_hint : undefined,
        });
        break;

      case 'output_ready': {
        const outputTypeStr = typeof data.type === 'string' ? data.type : 'report';
        const validTypes: CanvasContentType[] = ['report', 'chart', 'dataTable', 'pipeline', 'workflow', 'questionList', 'fetchResults'];
        // Map report_baseline/report_persona to 'report' Canvas type
        const canvasTypeStr = outputTypeStr.startsWith('report') ? 'report' : outputTypeStr;
        const outputType: CanvasContentType = validTypes.includes(canvasTypeStr as CanvasContentType)
          ? (canvasTypeStr as CanvasContentType)
          : 'report';
        const outputTitle = typeof data.title === 'string' ? data.title : '分析结果';
        const relatedMessageId = typeof data.related_message_id === 'string' ? data.related_message_id : '';
        const linkedMessageId = typeof data.linked_message_id === 'string' ? data.linked_message_id : undefined;
        const category = typeof data.category === 'string' ? data.category as 'baseline' | 'scenario' : undefined;
        const scenarioLabel = typeof data.scenario_label === 'string' ? data.scenario_label : undefined;
        const fallbackId = `output_${outputType}_${outputTitle}_${relatedMessageId || 'global'}`;
        const outputId = typeof data.output_id === 'string' ? data.output_id : fallbackId;
        const outputData = normalizeCanvasData(outputType, data.data) as CanvasContentDataMap['report'];
        const preview = normalizePreviewData(isRecord(data.data) ? data.data : {});
        addContent({
          id: outputId,
          type: outputType,
          title: outputTitle,
          data: outputData,
          createdAt: new Date(),
          relatedMessageId: relatedMessageId,
          versions: [],
          currentVersionIndex: -1,
          linkedMessageId: agentMessageIdRef.current || linkedMessageId,
          category: category,
          scenarioLabel: scenarioLabel,
        } as CanvasContent);
        const targetMessageId = relatedMessageId || agentMessageIdRef.current;
        if (targetMessageId) {
          const state = useConversationStore.getState();
          const msg = state.messages.find((m) => m.id === targetMessageId);
          const existingCards = msg?.outputCards || [];
          const alreadyExists = existingCards.some((card) => card.id === outputId);
          if (!alreadyExists) {
            const card: NonNullable<Message['outputCards']>[number] = {
              id: outputId,
              type: outputType,
              title: outputTitle,
              preview: {
                description: preview.description,
                itemCount: preview.itemCount,
                metrics: preview.metrics,
              },
            };
            updateMessage(targetMessageId, {
              outputCards: [...existingCards, card],
            });
          }
        }
        break;
      }

      case 'confirmation_request': {
        const requestId = typeof data.request_id === 'string' ? data.request_id : `request_${Date.now()}`;
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
          const content = data.canvas_content as Record<string, unknown>;
          const id = typeof content.id === 'string' ? content.id : `canvas_${Date.now()}`;
          const type: CanvasContentType =
            typeof content.type === 'string' &&
            ['report', 'chart', 'dataTable', 'pipeline', 'workflow', 'questionList', 'fetchResults'].includes(content.type)
              ? (content.type as CanvasContentType)
              : 'report';
          const title = typeof content.title === 'string' ? content.title : '分析结果';
          const contentData = normalizeCanvasData(type, content.data) as CanvasContentDataMap['report'];
          const createdAt = content.createdAt instanceof Date
            ? content.createdAt
            : new Date(typeof content.createdAt === 'string' ? content.createdAt : Date.now());
          const relatedMessageId = typeof content.relatedMessageId === 'string' ? content.relatedMessageId : '';
          addContent({
            id,
            type,
            title,
            data: contentData,
            createdAt,
            relatedMessageId,
            versions: [],
            currentVersionIndex: -1,
          } as CanvasContent);
        }
        break;
      }

      case 'agent_message': {
        const messageId = typeof data.id === 'string' ? data.id : `agent_${Date.now()}`;
        const messageContent = typeof data.content === 'string' ? data.content : '';
        const timestamp = data.timestamp ? new Date(data.timestamp as string) : new Date();
        const relatedOutputIds = Array.isArray(data.related_output_ids) ? data.related_output_ids : [];
        const metadata = typeof data.metadata === 'object' && data.metadata !== null
          ? data.metadata as Message['metadata']
          : {
              canEdit: false,
              canRollback: true,
              relatedOutputIds,
            };
        const confirmationRequest = (() => {
          if (typeof data.confirmation_request !== 'object' || data.confirmation_request === null) {
            return undefined;
          }
          const req = data.confirmation_request as Record<string, unknown>;
          const requestId = typeof req.request_id === 'string'
            ? req.request_id
            : typeof req.requestId === 'string'
            ? req.requestId
            : `request_${Date.now()}`;
          const type: ConfirmationRequest['type'] =
            typeof req.type === 'string' &&
            ['brand_info', 'persona_selection', 'action_choice', 'continue', 'step_confirmation'].includes(req.type)
              ? (req.type as ConfirmationRequest['type'])
              : 'step_confirmation';
          const message = typeof req.message === 'string' ? req.message : '';
          const options = Array.isArray(req.options) ? req.options : [];
          const allowTextInput = typeof req.allow_text_input === 'boolean'
            ? req.allow_text_input
            : typeof req.allowTextInput === 'boolean'
            ? req.allowTextInput
            : false;
          const stepId = typeof req.step_id === 'string'
            ? req.step_id
            : typeof req.stepId === 'string'
            ? req.stepId
            : undefined;
          const stepName = typeof req.step_name === 'string'
            ? req.step_name
            : typeof req.stepName === 'string'
            ? req.stepName
            : undefined;
          return {
            requestId,
            type,
            message,
            options,
            allowTextInput,
            stepId,
            stepName,
          };
        })();
        const message: Message = {
          id: messageId,
          type: 'agent',
          content: messageContent,
          timestamp,
          tpaor: typeof data.tpaor === 'object' && data.tpaor !== null ? data.tpaor : undefined,
          outputCards: Array.isArray(data.output_cards) ? data.output_cards : undefined,
          confirmationRequest,
          metadata,
        };
        addMessage(message);
        break;
      }

      case 'execution_complete': {
        finalizeCurrentMessage();
        resetStreamingState();
        // NOTE: Do NOT reset agentMessageIdRef here.
        // The orchestrator may run multiple rounds (e.g., orchestrator → agent → orchestrator).
        // If we reset the ref, the next round's reply_delta creates a duplicate message.
        // The ref is reset in 'agent_start' when a new user message triggers execution.
        stopExecution();
        setExecutionProgress(null);
        setBrowserState(null);
        setStopState(null);

        // Cycle 3: Update active task to completed
        const currentTask = useConversationStore.getState().activeTask;
        if (currentTask && currentTask.status === 'running') {
          setActiveTask({
            ...currentTask,
            status: 'completed',
            progress: 1.0,
            progress_message: '分析完成',
            completed_at: new Date().toISOString(),
            snapshot_id: typeof data.snapshot_id === 'string' ? data.snapshot_id : currentTask.snapshot_id,
          });
        }

        // Cycle 3: Handle follow-up suggestions from backend
        if (Array.isArray(data.follow_up_suggestions) && data.follow_up_suggestions.length > 0) {
          const validTypes = ['drill_down', 'compare', 'refetch', 'general'] as const;
          type SuggestionType = typeof validTypes[number];
          setFollowUpSuggestions(
            data.follow_up_suggestions.map((s: Record<string, unknown>, i: number) => {
              const rawType = typeof s.type === 'string' ? s.type : 'general';
              const type: SuggestionType = (validTypes as readonly string[]).includes(rawType)
                ? (rawType as SuggestionType)
                : 'general';
              return {
                id: typeof s.id === 'string' ? s.id : `fu_${i}`,
                label: typeof s.label === 'string' ? s.label : '',
                message: typeof s.message === 'string' ? s.message : '',
                type,
                icon: typeof s.icon === 'string' ? s.icon : undefined,
              };
            })
          );
        }
        break;
      }

      case 'execution_stopped':
        stopExecution();
        setExecutionProgress(null);
        setBrowserState(null);
        if (data) {
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
            ? data.partial_results as { fetchedCount?: number; totalCount?: number; platforms?: Record<string, { completed: number; total: number }> }
            : undefined;
          setStopState({
            isStopped: true,
            stoppedAt: new Date(),
            completedStages,
            pendingStages,
            partialResults: partialResults ? {
              fetchedCount: partialResults.fetchedCount ?? 0,
              totalCount: partialResults.totalCount ?? 0,
              platforms: partialResults.platforms ?? {},
            } : undefined,
            canResume: Boolean(data.can_resume ?? false),
            canRetry: Boolean(data.can_retry ?? false),
          });
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
        setBrowserState(null);

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
        console.error('[WebSocket] Error:', data);
        toast.error(errorMsg);
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

        if (taskStatus === 'running') {
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
            });
          }
        } else if (taskStatus === 'failed') {
          const ft = useConversationStore.getState().activeTask;
          if (ft) {
            setActiveTask({
              ...ft,
              status: 'failed',
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
    setPlanText,
    setInlineConfirmation,
    finalizeCurrentMessage,
    resetStreamingState,
    addContent,
    setActiveTask,
    updateActiveTaskProgress,
    setFollowUpSuggestions,
    replaceMessageId,
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
  const sendMessage = useCallback((content: string, context?: Array<{ id: string; type: string; label: string }>) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      pendingMessagesRef.current.push(content);
      return;
    }

    // Reset agent message ref so the next reply_delta creates a NEW message
    // (instead of overwriting the previous agent message)
    agentMessageIdRef.current = null;
    resetStreamingState();

    const payload: Record<string, unknown> = { content };
    if (context && context.length > 0) {
      payload.context = context;
    }

    wsRef.current.send(JSON.stringify({
      event: 'user_message',
      data: payload,
    }));
  }, [resetStreamingState]);

  // Send confirmation
  const sendConfirmation = useCallback((requestId: string, selection: string | Record<string, unknown>) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;

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
    sendStepControl,
    stopExecution: sendStop,
    resumeExecution,
    rollback,
    sendRecall,
    isConnected,
  };
}
