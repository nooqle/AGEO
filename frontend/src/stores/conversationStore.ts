import { create } from 'zustand';
import { Message, ConfirmationRequest, ExecutionStep, ActionLogEntry, InlineConfirmation } from '@/types/message';
import { TPAORUpdate, ExecutionProgress, BrowserState, StopState } from '@/types/agent';
import { ExecutionPlanStep, LLMDecision } from '@/types/orchestration';
import { generateId } from '@/lib/utils';
import type { StageResult, PlatformStatusData } from '@/types/snapshot';
import type { AnalysisTask, FollowUpSuggestion } from '@/types/task';

interface CurrentTPAOR {
  thought: string;
  plan: string;
  action: string;
  observation: string;
  response: string;
  activePhase: 'thought' | 'plan' | 'action' | 'observation' | 'response' | null;
}

export interface TPAORPhaseEntry {
  phase: 'thought' | 'plan' | 'action' | 'observation' | 'response';
  content: string;
  isComplete: boolean;
  startTime: number;
}

interface ConversationState {
  // 消息
  messages: Message[];

  // 执行状态
  isAgentExecuting: boolean;
  executionStartTime: Date | null;

  // TPAOR 状态 (legacy, kept for backward compat)
  currentTPAOR: CurrentTPAOR;
  tpaorPhaseHistory: TPAORPhaseEntry[];

  // 执行进度
  executionProgress: ExecutionProgress | null;

  // 浏览器状态
  browserState: BrowserState | null;

  // 停止状态
  stopState: StopState | null;

  // 确认请求 (legacy modal)
  pendingConfirmation: ConfirmationRequest | null;

  // 当前执行步骤
  currentExecutionStep: ExecutionStep | null;

  // LLM 编排相关（v2 新增）
  executionPlan: ExecutionPlanStep[] | null;
  contextData: Record<string, unknown>;
  decisionHistory: LLMDecision[];
  currentIntent: string | null;

  // Stage results (progressive wait experience)
  stageResults: StageResult[];

  // Cycle 3: Task persistence & multi-turn follow-up
  activeTask: AnalysisTask | null;
  followUpSuggestions: FollowUpSuggestion[];

  // WebSocket send function (registered by ChatPanel's useWebSocket, shared with Canvas components)
  wsConfirmation: ((requestId: string, selection: string | Record<string, unknown>) => void) | null;

  // New: 实时流式状态（当前正在执行的消息）
  streamingReply: string;
  streamingThought: string;
  currentActionLogs: ActionLogEntry[];
  currentPlanText: string | null;
  currentAgentMessageId: string | null;

  // Actions
  addMessage: (message: Omit<Message, 'id' | 'timestamp' | 'metadata'> & Partial<Pick<Message, 'id' | 'metadata'>>) => string;
  updateMessage: (id: string, updates: Partial<Message>) => void;
  replaceMessageId: (oldId: string, newId: string) => void;
  removeMessage: (id: string) => void;

  updateTPAOR: (update: TPAORUpdate) => void;
  resetTPAOR: () => void;

  setExecutionProgress: (progress: ExecutionProgress | null) => void;
  setBrowserState: (state: BrowserState | null) => void;
  setStopState: (state: StopState | null) => void;
  setPendingConfirmation: (request: ConfirmationRequest | null) => void;

  // 执行步骤相关
  addExecutionStep: (step: ExecutionStep) => string;
  updateExecutionStep: (stepId: string, updates: Partial<ExecutionStep>) => void;
  setCurrentExecutionStep: (step: ExecutionStep | null) => void;
  appendExecutionLog: (stepId: string, log: string) => void;

  // LLM 编排相关（v2 新增）
  setExecutionPlan: (plan: ExecutionPlanStep[] | null) => void;
  updateContextData: (key: string, value: unknown) => void;
  addDecision: (decision: LLMDecision) => void;
  setCurrentIntent: (intent: string | null) => void;

  // Stage result actions
  addStageResult: (result: StageResult) => void;
  clearStageResults: () => void;

  // Cycle 3: Task & follow-up actions
  setActiveTask: (task: AnalysisTask | null) => void;
  updateActiveTaskProgress: (stage: string, progress: number, message: string) => void;
  setFollowUpSuggestions: (suggestions: FollowUpSuggestion[]) => void;
  clearFollowUpSuggestions: () => void;

  // New: 流式状态 actions
  appendReplyDelta: (delta: string) => void;
  appendThoughtDelta: (delta: string) => void;
  addActionLog: (log: ActionLogEntry) => void;
  updateActionLog: (id: string, updates: Partial<ActionLogEntry>) => void;
  setPlanText: (text: string) => void;
  setInlineConfirmation: (confirmation: InlineConfirmation | null) => void;
  markConfirmationSelected: (messageId: string, optionId: string) => void;
  finalizeCurrentMessage: () => void;
  resetStreamingState: () => void;
  setWsConfirmation: (fn: ((requestId: string, selection: string | Record<string, unknown>) => void) | null) => void;

  startExecution: () => void;
  stopExecution: () => void;

  clearMessagesAfter: (messageId: string) => Message[];
  reset: () => void;
}

const initialTPAOR: CurrentTPAOR = {
  thought: '',
  plan: '',
  action: '',
  observation: '',
  response: '',
  activePhase: null,
};

export const useConversationStore = create<ConversationState>((set, get) => ({
  messages: [],
  isAgentExecuting: false,
  executionStartTime: null,
  currentTPAOR: initialTPAOR,
  tpaorPhaseHistory: [],
  executionProgress: null,
  browserState: null,
  stopState: null,
  pendingConfirmation: null,
  currentExecutionStep: null,
  // LLM 编排相关（v2 新增）
  executionPlan: null,
  contextData: {},
  decisionHistory: [],
  currentIntent: null,
  // Stage results
  stageResults: [],
  // Cycle 3
  activeTask: null,
  followUpSuggestions: [],
  // WebSocket confirmation function
  wsConfirmation: null,
  // New: streaming state
  streamingReply: '',
  streamingThought: '',
  currentActionLogs: [],
  currentPlanText: null,
  currentAgentMessageId: null,

  addMessage: (messageData) => {
    const id = messageData.id || generateId();
    const message: Message = {
      id,
      timestamp: new Date(),
      metadata: {
        canEdit: messageData.type === 'user',
        canRollback: true,
        relatedOutputIds: [],
      },
      ...messageData,
    };

    set((state) => ({
      messages: [...state.messages, message],
    }));

    return id;
  },

  updateMessage: (id, updates) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === id ? { ...m, ...updates } : m
      ),
    }));
  },

  replaceMessageId: (oldId, newId) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === oldId ? { ...m, id: newId } : m
      ),
    }));
  },

  removeMessage: (id) => {
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== id),
    }));
  },

  updateTPAOR: (update) => {
    set((state) => {
      const existingIndex = state.tpaorPhaseHistory.findIndex(
        (entry) => entry.phase === update.phase
      );
      let newHistory: TPAORPhaseEntry[];
      if (existingIndex >= 0) {
        newHistory = state.tpaorPhaseHistory.map((entry, i) =>
          i === existingIndex
            ? { ...entry, content: update.content, isComplete: update.isComplete }
            : entry
        );
      } else {
        newHistory = [
          ...state.tpaorPhaseHistory,
          {
            phase: update.phase,
            content: update.content,
            isComplete: update.isComplete,
            startTime: Date.now(),
          },
        ];
      }
      return {
        currentTPAOR: {
          ...state.currentTPAOR,
          [update.phase]: update.content,
          activePhase: update.isComplete ? null : update.phase,
        },
        tpaorPhaseHistory: newHistory,
      };
    });
  },

  resetTPAOR: () => {
    set({ currentTPAOR: initialTPAOR, tpaorPhaseHistory: [] });
  },

  setExecutionProgress: (progress) => {
    set({ executionProgress: progress });
  },

  setBrowserState: (browserState) => {
    set({ browserState });
  },

  setStopState: (stopState) => {
    set({ stopState });
  },

  setPendingConfirmation: (request) => {
    set({ pendingConfirmation: request });
  },

  // 添加执行步骤消息
  addExecutionStep: (step) => {
    const id = generateId();
    const message: Message = {
      id,
      type: 'execution_step',
      content: `${step.stepName} - ${step.status}`,
      timestamp: new Date(),
      executionStep: step,
      metadata: {
        canEdit: false,
        canRollback: false,
        relatedOutputIds: [],
      },
    };

    set((state) => ({
      messages: [...state.messages, message],
      currentExecutionStep: step,
    }));

    return id;
  },

  // 更新执行步骤
  updateExecutionStep: (stepId, updates) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.type === 'execution_step' && m.executionStep?.stepId === stepId
          ? {
              ...m,
              executionStep: m.executionStep
                ? { ...m.executionStep, ...updates }
                : undefined,
            }
          : m
      ),
      currentExecutionStep: state.currentExecutionStep?.stepId === stepId
        ? { ...state.currentExecutionStep, ...updates }
        : state.currentExecutionStep,
    }));
  },

  // 设置当前执行步骤
  setCurrentExecutionStep: (step) => {
    set({ currentExecutionStep: step });
  },

  // 追加执行日志
  appendExecutionLog: (stepId, log) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.type === 'execution_step' && m.executionStep?.stepId === stepId
          ? {
              ...m,
              executionStep: m.executionStep
                ? {
                    ...m.executionStep,
                    logs: [...(m.executionStep.logs || []), log],
                  }
                : undefined,
            }
          : m
      ),
    }));
  },

  startExecution: () => {
    set({
      isAgentExecuting: true,
      executionStartTime: new Date(),
      currentTPAOR: initialTPAOR,
      tpaorPhaseHistory: [],
      stopState: null,
      executionProgress: null,
      stageResults: [],
      followUpSuggestions: [],
      // Reset streaming state
      streamingReply: '',
      streamingThought: '',
      currentActionLogs: [],
      currentPlanText: null,
    });
  },

  stopExecution: () => {
    set({
      isAgentExecuting: false,
      browserState: null,
    });
  },

  // LLM 编排相关（v2 新增）
  setExecutionPlan: (plan) => {
    set({ executionPlan: plan });
  },

  updateContextData: (key, value) => {
    set((state) => ({
      contextData: { ...state.contextData, [key]: value },
    }));
  },

  addDecision: (decision) => {
    set((state) => ({
      decisionHistory: [...state.decisionHistory, decision],
      currentIntent: decision.user_intent,
    }));
  },

  setCurrentIntent: (intent) => {
    set({ currentIntent: intent });
  },

  // =========================================================================
  // Stage result actions (progressive wait experience)
  // =========================================================================

  addStageResult: (result) => {
    set((state) => {
      // For platform_status, merge into existing A4 entry
      if (result.resultType === 'platform_status') {
        const existingIndex = state.stageResults.findIndex(
          (r) => r.resultType === 'platform_status'
        );
        if (existingIndex >= 0) {
          const existing = state.stageResults[existingIndex];
          const existingPlatforms = Array.isArray((existing.data as Record<string, unknown>).platforms)
            ? (existing.data as Record<string, unknown>).platforms as PlatformStatusData[]
            : [];
          const newPlatforms = Array.isArray((result.data as Record<string, unknown>).platforms)
            ? (result.data as Record<string, unknown>).platforms as PlatformStatusData[]
            : [];

          // Merge: update existing platforms or add new ones
          const mergedPlatforms = [...existingPlatforms];
          for (const np of newPlatforms) {
            const idx = mergedPlatforms.findIndex((p) => p.platform === np.platform);
            if (idx >= 0) {
              mergedPlatforms[idx] = np;
            } else {
              mergedPlatforms.push(np);
            }
          }

          const completedCount = mergedPlatforms.filter(
            (p) => p.status === 'success' || p.status === 'failed'
          ).length;

          const updated = [...state.stageResults];
          updated[existingIndex] = {
            ...existing,
            data: {
              ...existing.data,
              platforms: mergedPlatforms,
              completedCount,
            },
            timestamp: result.timestamp,
          };
          return { stageResults: updated };
        }
      }

      // Deduplicate by stage + resultType (Review T7: reconnection replay dedup)
      const key = `${result.stage}:${result.resultType}`;
      const existingDedupIndex = state.stageResults.findIndex(
        (existing) => `${existing.stage}:${existing.resultType}` === key
      );
      if (existingDedupIndex >= 0) {
        // Replace existing entry (latest wins)
        return {
          stageResults: state.stageResults.map((existing, i) =>
            i === existingDedupIndex ? result : existing
          ),
        };
      }

      return { stageResults: [...state.stageResults, result] };
    });
  },

  clearStageResults: () => {
    set({ stageResults: [] });
  },

  // =========================================================================
  // Cycle 3: Task & Follow-Up actions
  // =========================================================================

  setActiveTask: (task) => {
    set({ activeTask: task });
  },

  updateActiveTaskProgress: (stage, progress, message) => {
    set((state) => {
      if (!state.activeTask) return {};
      return {
        activeTask: {
          ...state.activeTask,
          current_stage: stage,
          progress,
          progress_message: message,
          status: 'running' as const,
        },
      };
    });
  },

  setFollowUpSuggestions: (suggestions) => {
    set({ followUpSuggestions: suggestions });
  },

  clearFollowUpSuggestions: () => {
    set({ followUpSuggestions: [] });
  },

  // =========================================================================
  // New: Streaming state actions (4-layer architecture)
  // =========================================================================

  appendReplyDelta: (delta) => {
    set((state) => {
      // Defensive dedup: skip if delta would cause the reply to end with
      // the same content repeated (e.g., full content_buffer echoed again)
      if (delta.length > 20 && state.streamingReply.length > 20) {
        if (state.streamingReply.endsWith(delta)) {
          return {};
        }
        // Check if delta contains the entire existing reply (full buffer echo)
        if (delta.startsWith(state.streamingReply) && delta.length >= state.streamingReply.length) {
          return {};
        }
      }
      const newReply = state.streamingReply + delta;
      // Also update the current agent message content in real-time
      const msgId = state.currentAgentMessageId;
      if (msgId) {
        return {
          streamingReply: newReply,
          messages: state.messages.map((m) =>
            m.id === msgId ? { ...m, content: newReply } : m
          ),
        };
      }
      return { streamingReply: newReply };
    });
  },

  appendThoughtDelta: (delta) => {
    set((state) => {
      const newThought = state.streamingThought + delta;
      const msgId = state.currentAgentMessageId;
      if (msgId) {
        return {
          streamingThought: newThought,
          messages: state.messages.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  layers: {
                    ...(m.layers || { actionLogs: [] }),
                    thought: newThought,
                  },
                }
              : m
          ),
        };
      }
      return { streamingThought: newThought };
    });
  },

  addActionLog: (log) => {
    set((state) => {
      const newLogs = [...state.currentActionLogs, log];
      const msgId = state.currentAgentMessageId;
      if (msgId) {
        return {
          currentActionLogs: newLogs,
          messages: state.messages.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  layers: {
                    ...(m.layers || { actionLogs: [] }),
                    actionLogs: newLogs,
                  },
                }
              : m
          ),
        };
      }
      return { currentActionLogs: newLogs };
    });
  },

  updateActionLog: (id, updates) => {
    set((state) => {
      const newLogs = state.currentActionLogs.map((log) =>
        log.id === id ? { ...log, ...updates } : log
      );
      const msgId = state.currentAgentMessageId;
      if (msgId) {
        return {
          currentActionLogs: newLogs,
          messages: state.messages.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  layers: {
                    ...(m.layers || { actionLogs: [] }),
                    actionLogs: newLogs,
                  },
                }
              : m
          ),
        };
      }
      return { currentActionLogs: newLogs };
    });
  },

  setPlanText: (text) => {
    set((state) => {
      const msgId = state.currentAgentMessageId;
      if (msgId) {
        return {
          currentPlanText: text,
          messages: state.messages.map((m) =>
            m.id === msgId
              ? {
                  ...m,
                  layers: {
                    ...(m.layers || { actionLogs: [] }),
                    planText: text,
                  },
                }
              : m
          ),
        };
      }
      return { currentPlanText: text };
    });
  },

  setInlineConfirmation: (confirmation) => {
    set((state) => {
      const msgId = state.currentAgentMessageId;
      if (msgId && confirmation) {
        return {
          messages: state.messages.map((m) =>
            m.id === msgId
              ? { ...m, inlineConfirmation: confirmation }
              : m
          ),
        };
      }
      return {};
    });
  },

  markConfirmationSelected: (messageId, optionId) => {
    set((state) => ({
      messages: state.messages.map((m) =>
        m.id === messageId && m.inlineConfirmation
          ? {
              ...m,
              inlineConfirmation: {
                ...m.inlineConfirmation,
                selectedOptionId: optionId,
              },
            }
          : m
      ),
    }));
  },

  finalizeCurrentMessage: () => {
    // Freeze the streaming state into the current message
    const state = get();
    const msgId = state.currentAgentMessageId;
    if (msgId) {
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === msgId
            ? {
                ...m,
                content: s.streamingReply || m.content,
                layers: {
                  planText: s.currentPlanText || m.layers?.planText,
                  actionLogs: s.currentActionLogs.length > 0
                    ? s.currentActionLogs
                    : (m.layers?.actionLogs || []),
                  thought: s.streamingThought || m.layers?.thought,
                },
              }
            : m
        ),
        currentAgentMessageId: null,
      }));
    }
  },

  resetStreamingState: () => {
    set({
      streamingReply: '',
      streamingThought: '',
      currentActionLogs: [],
      currentPlanText: null,
      currentAgentMessageId: null,
    });
  },

  setWsConfirmation: (fn) => set({ wsConfirmation: fn }),

  clearMessagesAfter: (messageId) => {
    const { messages } = get();
    const index = messages.findIndex((m) => m.id === messageId);
    if (index === -1) return [];

    const removed = messages.slice(index + 1);
    set({ messages: messages.slice(0, index + 1) });
    return removed;
  },

  reset: () => {
    set({
      messages: [],
      isAgentExecuting: false,
      executionStartTime: null,
      currentTPAOR: initialTPAOR,
      tpaorPhaseHistory: [],
      executionProgress: null,
      browserState: null,
      stopState: null,
      pendingConfirmation: null,
      currentExecutionStep: null,
      // LLM 编排相关（v2 新增）
      executionPlan: null,
      contextData: {},
      decisionHistory: [],
      currentIntent: null,
      // Stage results
      stageResults: [],
      // Cycle 3
      activeTask: null,
      followUpSuggestions: [],
      // WebSocket confirmation function
      wsConfirmation: null,
      // Streaming state
      streamingReply: '',
      streamingThought: '',
      currentActionLogs: [],
      currentPlanText: null,
      currentAgentMessageId: null,
    });
  },
}));
