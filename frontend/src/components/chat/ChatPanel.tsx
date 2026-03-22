'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { MessageList } from './MessageList';
import { TaskStatusBadge } from './TaskStatusBadge';
import { ReconnectionBanner } from './ReconnectionBanner';
import { FollowUpChips } from './FollowUpChips';
import { BrowserActionBanner } from './BrowserActionBanner';
import { InputArea } from './InputArea';
import { cn } from '@/lib/cn';
import { DEFAULT_EXAMPLE_BRANDS, ExampleBrand } from '@/config/brands';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { DEFAULT_FOLLOWUPS } from '@/types/task';
import type { CanvasContent, CanvasContentDataMap, CanvasContentType } from '@/types/canvas';
import type { ContextTag } from '@/stores/contextStore';
import type { StageResult } from '@/types/snapshot';
import type { AnalysisTask, FollowUpSuggestion } from '@/types/task';
import {
  buildOutputCardsFromApiMessage,
  getSupersededHistoryMessageIds,
  rebuildPersistedLayers,
  VALID_OUTPUT_TYPES,
} from '@/adapters/chatMessage';


interface ChatPanelProps {
  sessionId: string;
  className?: string;
  exampleBrands?: ExampleBrand[];
}

export function ChatPanel({ sessionId, className, exampleBrands }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const recalledContentRef = useRef<string | null>(null);
  const autoScrollEnabledRef = useRef(true);
  const [inputValue, setInputValue] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const router = useRouter();
  const searchParams = useSearchParams();
  const autoStartBrand = searchParams.get('brand');
  const autoStartDraft = searchParams.get('draft');
  const shouldAutoSendDraft = searchParams.get('autosend') === '1';
  const autoSentRef = useRef(false);
  const [isAutoStartingPrompt, setIsAutoStartingPrompt] = useState(Boolean(autoStartBrand || autoStartDraft));
  const safeToLeaveShownRef = useRef(false);
  const [showSafeToLeave, setShowSafeToLeave] = useState(false);
  const [reconnectionTask, setReconnectionTask] = useState<AnalysisTask | null>(null);
  const replayAnimatingRef = useRef(false);
  const browserActionToastRef = useRef<Set<string>>(new Set());

  const {
    messages,
    isAgentExecuting,
    stopState,
    browserStates,
    pendingConfirmation,
    executionProgress,
    stageResults,
    activeTask,
    followUpSuggestions,
    addMessage,
    startExecution,
    stopExecution: stopExecutionAction,
    setPendingConfirmation,
    markConfirmationSelected,
    reset: resetConversation,
    setActiveTask,
    clearFollowUpSuggestions,
    addStageResult,
    setExecutionProgress,
  } = useConversationStore();

  const setOptimisticExecutionProgress = useCallback((optionId: string) => {
    const optimisticProgressMap: Record<string, {
      stage: string;
      stageName: string;
      progress: number;
      details: string;
    }> = {
      persona_focused: {
        stage: 'question_simulation',
        stageName: '问题模拟生成',
        progress: 0.45,
        details: '已确认画像聚焦分析，正在生成问题...',
      },
      brand_panorama: {
        stage: 'question_simulation',
        stageName: '问题模拟生成',
        progress: 0.45,
        details: '已确认品牌全景分析，正在生成问题...',
      },
      fast: {
        stage: 'answer_fetch',
        stageName: 'AI答案抓取',
        progress: 0.55,
        details: '已确认快速采集，正在启动抓取...',
      },
      full: {
        stage: 'answer_fetch',
        stageName: 'AI答案抓取',
        progress: 0.55,
        details: '已确认完整采集，正在启动全平台浏览器抓取...',
      },
      regenerate: {
        stage: 'question_simulation',
        stageName: '问题模拟生成',
        progress: 0.45,
        details: '已确认重新生成问题，正在启动问题模拟...',
      },
    };

    const optimistic = optimisticProgressMap[optionId];
    if (!optimistic) {
      return;
    }

    setExecutionProgress({
      stage: optimistic.stage,
      stageName: optimistic.stageName,
      stageIndex: 0,
      totalStages: 5,
      progress: optimistic.progress,
      status: 'running',
      details: optimistic.details,
      steps: [],
      subTasks: [],
    });
  }, [setExecutionProgress]);

  // Initialize WebSocket connection
  const {
    sendMessage,
    sendConfirmation,
    stopExecution: sendStopExecution,
    sendRecall,
    isConnected,
  } = useWebSocket(sessionId);

  // Reset stores on mount (component is keyed by sessionId, so this runs on session switch)
  useEffect(() => {
    resetConversation();
    useCanvasStore.getState().clearContents();
  }, [resetConversation]);

  const updateAutoScrollState = useCallback(() => {
    const container = scrollRef.current;
    if (!container) return;

    const distanceFromBottom = container.scrollHeight - container.clientHeight - container.scrollTop;
    autoScrollEnabledRef.current = distanceFromBottom < 80;
  }, []);

  // Auto-scroll only when the user is still following the latest message.
  useEffect(() => {
    if (scrollRef.current && autoScrollEnabledRef.current) {
      scrollRef.current.scrollTo({
        top: scrollRef.current.scrollHeight,
        behavior: isAgentExecuting ? 'auto' : 'smooth',
      });
    }
  }, [messages, isAgentExecuting, stageResults, followUpSuggestions]);

  // Listen for scroll-to-message events from Canvas (version jump-to-conversation)
  useEffect(() => {
    const handler = (e: Event) => {
      const { messageId } = (e as CustomEvent).detail;
      if (!messageId || !scrollRef.current) return;
      const el = scrollRef.current.querySelector(`[data-message-id="${messageId}"]`);
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('message-highlight');
        setTimeout(() => el.classList.remove('message-highlight'), 3000);
      }
    };
    window.addEventListener('scroll-to-message', handler);
    return () => window.removeEventListener('scroll-to-message', handler);
  }, []);

  // Listen for recall-fill-input events from useWebSocket recall_complete handler
  useEffect(() => {
    const handler = () => {
      const content = recalledContentRef.current;
      if (content) {
        setInputValue(content);
        recalledContentRef.current = null;
      }
    };
    window.addEventListener('recall-fill-input', handler);
    return () => window.removeEventListener('recall-fill-input', handler);
  }, []);

  // Listen for recall-reload-artifacts: reload surviving artifacts from DB after recall
  useEffect(() => {
    let cancelled = false;
    const handler = async () => {
      try {
        const outputs = await api.getOutputs(sessionId);
        if (cancelled || !outputs || outputs.length === 0) return;
        const store = useCanvasStore.getState();
        for (const output of outputs) {
          const artifactId = output.artifact_id || output.id;
          const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(output.type as CanvasContentType)
            ? (output.type as CanvasContentType)
            : 'report';
          store.addContent({
            id: artifactId,
            type: outputType,
            title: output.title || output.type || '分析结果',
            data: (output.data || {}) as CanvasContent['data'],
            createdAt: new Date(output.created_at),
            relatedMessageId: '',
            linkedMessageId: output.message_id,
            versions: [],
            currentVersionIndex: -1,
          } as CanvasContent);
        }
        useCanvasStore.getState().setOpen(true);
      } catch {
        // Silently ignore — Canvas stays empty, user can refresh to recover
      }
    };
    window.addEventListener('recall-reload-artifacts', handler);
    return () => {
      cancelled = true;
      window.removeEventListener('recall-reload-artifacts', handler);
    };
  }, [sessionId]);

  // Load persisted messages on mount
  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const msgs = await api.getMessages(sessionId, { limit: 100 });
        if (cancelled || !msgs || msgs.length === 0) return;
        const suppressedMessageIds = getSupersededHistoryMessageIds(msgs);
        // Convert API messages to store format, reconstructing outputCards and layers from metadata
        for (const msg of msgs) {
          const role = msg.role === 'agent' || msg.role === 'assistant' ? 'agent' : 'user';
          const outputCards = buildOutputCardsFromApiMessage(msg, sessionId);

          // Reconstruct layers and stage results from persisted metadata
          const reconstructed = rebuildPersistedLayers(msg.metadata as Record<string, unknown> | null);
          const layers = reconstructed.layers;
          for (const sr of reconstructed.stageResults) {
            addStageResult(sr);
          }

          if (suppressedMessageIds.has(msg.id)) {
            continue;
          }

          addMessage({
            id: msg.id || undefined,
            type: role,
            content: msg.content || '',
            ...(outputCards ? { outputCards } : {}),
            ...(layers ? { layers } : {}),
          });
        }
      } catch {
        toast.error('消息加载失败');
      } finally {
        if (!cancelled) setIsLoadingHistory(false);
      }
    };
    // Always load on mount — resetConversation() already cleared stale state,
    // and key={sessionId} guarantees a fresh mount on every session change.
    loadHistory();
    return () => { cancelled = true; };
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Load persisted artifacts on mount
  const { addContent } = useCanvasStore();
  useEffect(() => {
    let cancelled = false;
    const loadArtifacts = async () => {
      try {
        const outputs = await api.getOutputs(sessionId);
        if (cancelled || !outputs || outputs.length === 0) return;
        for (const output of outputs) {
          const artifactId = output.artifact_id || output.id;
          // Map report_baseline/report_persona to 'report' Canvas type (same as useWebSocket)
          const rawType = typeof output.type === 'string' ? output.type : 'report';
          const canvasTypeStr = rawType.startsWith('report') ? 'report' : rawType;
          const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(canvasTypeStr as CanvasContentType)
            ? (canvasTypeStr as CanvasContentType)
            : 'report';
          const category = typeof output.category === 'string' ? output.category as 'baseline' | 'scenario' : undefined;
          addContent({
            id: artifactId,
            type: outputType,
            title: output.title || output.type || '分析结果',
            data: (output.data || {}) as CanvasContentDataMap['report'],
            createdAt: new Date(output.created_at),
            relatedMessageId: '',
            linkedMessageId: output.message_id,
            versions: [],
            currentVersionIndex: -1,
            category,
          } as CanvasContent);
        }
      } catch {
        // Silently ignore — artifacts will be populated via WebSocket events
      }
    };
    loadArtifacts();
    return () => { cancelled = true; };
  }, [sessionId, addContent]);

  // Cycle 3: Check for active task on mount (reconnection flow)
  useEffect(() => {
    let cancelled = false;
    const checkActiveTask = async () => {
      try {
        const task = await api.getActiveTask(sessionId);
        if (cancelled) return;

        if (task) {
          setActiveTask(task);
        } else {
          const { tasks } = await api.getSessionTasks(sessionId, { limit: 1 });
          if (cancelled) return;
          const latestTask = tasks[0] ?? null;
          setActiveTask(latestTask);
          if (latestTask && (latestTask.status === 'completed' || latestTask.status === 'failed')) {
            setReconnectionTask(latestTask);
          }
          return;
        }

        if (task.status === 'running') {
          // Restore progress UI
          useConversationStore.setState({ isAgentExecuting: true });
          if (task.progress > 0) {
            setExecutionProgress({
              stage: task.current_stage,
              stageName: task.current_stage,
              stageIndex: 0,
              totalStages: 5,
              progress: task.progress,
              status: 'running',
              details: task.progress_message,
              steps: [],
              subTasks: [],
            });
          }

          // Replay cached stage results with staggered animation
          if (task.stage_results_cache && task.stage_results_cache.length > 0) {
            replayAnimatingRef.current = true;
            const existingKeys = new Set(
              useConversationStore.getState().stageResults.map(
                (r: StageResult) => `${r.stage}:${r.resultType}`
              )
            );
            const toReplay = task.stage_results_cache.filter(
              (r: StageResult) => !existingKeys.has(`${r.stage}:${r.resultType}`)
            );
            toReplay.forEach((result: StageResult, index: number) => {
              setTimeout(() => {
                if (!cancelled) {
                  addStageResult({
                    ...result,
                    data: { ...result.data, _isReplay: true },
                  });
                }
                if (index === toReplay.length - 1) {
                  replayAnimatingRef.current = false;
                }
              }, index * 150);
            });
          }
        } else if (task.status === 'completed' || task.status === 'failed') {
          // Show reconnection banner
          setReconnectionTask(task);
        }
      } catch {
        // Silently ignore if task API is not available
      }
    };

    checkActiveTask();
    return () => { cancelled = true; };
  }, [sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cycle 3: Safe-to-leave signal (only on fresh execution, once per session)
  useEffect(() => {
    if (isAgentExecuting && executionProgress && !safeToLeaveShownRef.current && !replayAnimatingRef.current) {
      safeToLeaveShownRef.current = true;
      const timer = setTimeout(() => {
        setShowSafeToLeave(true);
        // Auto-hide after 10s (animation handles visual fade)
        setTimeout(() => setShowSafeToLeave(false), 10000);
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [isAgentExecuting, executionProgress]);


  const actionableBrowserStates = browserStates.filter((state) => state.requiresAction);

  useEffect(() => {
    const nextFingerprints = new Set<string>();
    const platformNameMap: Record<string, string> = {
      doubao: '豆包',
      deepseek: 'DeepSeek',
      kimi: 'Kimi',
      hunyuan: '元宝',
    };
    actionableBrowserStates.forEach((state) => {
      const fingerprint = state.requestId || `${state.platform}:${state.state}:${state.message}:${state.actionHint || ''}`;
      nextFingerprints.add(fingerprint);
      if (browserActionToastRef.current.has(fingerprint)) {
        return;
      }

      const platformName = platformNameMap[state.platform] || state.platform;
      const actionLabel = state.actionType === 'verify'
        ? '\u89e6\u53d1\u4e86\u5b89\u5168\u9a8c\u8bc1'
        : state.actionType === 'login'
        ? '\u9700\u8981\u767b\u5f55'
        : state.actionType === 'modal'
        ? '\u51fa\u73b0\u4e86\u9875\u9762\u5f39\u6846'
        : '\u9700\u8981\u4f60\u5728\u6d4f\u89c8\u5668\u7a97\u53e3\u4e2d\u64cd\u4f5c';
      toast.info(`${platformName}${actionLabel}\uff0c\u7cfb\u7edf\u5df2\u5c1d\u8bd5\u5c06\u7a97\u53e3\u5207\u5230\u524d\u53f0\u3002`, 8000);
    });
    browserActionToastRef.current = nextFingerprints;
  }, [actionableBrowserStates]);
  // Handle sending message
  const handleSendMessage = useCallback((content: string, _attachments?: unknown[], context?: ContextTag[]) => {
    if (!content.trim() || isAgentExecuting) return;

    // If user types while there's a pending confirmation, clear it
    // (user chose to type freely instead of clicking an option)
    if (pendingConfirmation) {
      setPendingConfirmation(null);
    }

    // Add user message to local state
    addMessage({
      type: 'user',
      content: content.trim(),
    });

    autoScrollEnabledRef.current = true;

    // Start execution state
    startExecution();

    // Send message via WebSocket (with optional context)
    sendMessage(content.trim(), context);
  }, [addMessage, startExecution, sendMessage, isAgentExecuting, pendingConfirmation, setPendingConfirmation]);

  // Auto-send brand name when navigating from Dashboard with ?brand= param
  useEffect(() => {
    const draft = autoStartDraft?.trim() || '';
    const brand = autoStartBrand?.trim() || '';
    const autoMessage = draft || brand;
    const shouldAutoSendExistingDraft = Boolean(draft && shouldAutoSendDraft && messages.length > 0);

    if (!autoMessage) {
      setIsAutoStartingPrompt(false);
      return;
    }

    if (isLoadingHistory) {
      setIsAutoStartingPrompt(true);
      return;
    }

    if (autoSentRef.current) {
      return;
    }

    if (messages.length > 0 && !shouldAutoSendExistingDraft) {
      setIsAutoStartingPrompt(false);
      if (draft) {
        setInputValue(draft);
      }
      if (autoSentRef.current || draft) {
        router.replace(`/chat/${sessionId}`);
      }
      return;
    }

    if (draft && !shouldAutoSendDraft && messages.length === 0) {
      setInputValue(draft);
      setIsAutoStartingPrompt(false);
      router.replace(`/chat/${sessionId}`);
      return;
    }

    setIsAutoStartingPrompt(true);

    if (!isConnected) {
      const fallbackTimer = setTimeout(() => {
        if (!autoSentRef.current) {
          setIsAutoStartingPrompt(false);
          setInputValue(autoMessage);
          router.replace(`/chat/${sessionId}`);
          toast.error('自动启动分析失败，请点击发送后重试');
        }
      }, 5000);
      return () => clearTimeout(fallbackTimer);
    }

    autoSentRef.current = true;
    const timer = setTimeout(() => {
      handleSendMessage(autoMessage);
      setIsAutoStartingPrompt(false);
      router.replace(`/chat/${sessionId}`);
    }, 500);

    return () => clearTimeout(timer);
  }, [
    autoStartBrand,
    autoStartDraft,
    shouldAutoSendDraft,
    messages.length,
    isConnected,
    isLoadingHistory,
    handleSendMessage,
    router,
    sessionId,
  ]);

  // Handle stopping execution
  const handleStopExecution = useCallback(() => {
    stopExecutionAction();
    sendStopExecution();
  }, [stopExecutionAction, sendStopExecution]);

  // Handle confirmation
  const handleConfirmation = useCallback((optionId: string) => {
    // Legacy modal confirmation path
    if (pendingConfirmation) {
      const option = pendingConfirmation.options.find(o => o.id === optionId);
      if (option) {
        addMessage({ type: 'user', content: option.label });
      }
      sendConfirmation(pendingConfirmation.requestId, { optionId });
      setPendingConfirmation(null);
      startExecution();
      return;
    }

    // Inline confirmation path: find option from the last agent message
    const lastAgentMsg = [...messages].reverse().find(m => m.type === 'agent' && m.inlineConfirmation);
    const inlineConf = lastAgentMsg?.inlineConfirmation;
    if (inlineConf) {
      const option = inlineConf.options.find((o: { id: string }) => o.id === optionId);
      const label = option?.label || optionId;

      // Mark the button as selected (disables re-clicking)
      if (lastAgentMsg) {
        markConfirmationSelected(lastAgentMsg.id, optionId);
      }

      // Add user message showing the selection
      addMessage({ type: 'user', content: label });

      // Start execution state (backend will restart workflow)
      startExecution();
      setOptimisticExecutionProgress(optionId);

      // Send confirmation to backend — selection must be a plain string
      sendConfirmation('', label);
    }
  }, [
    pendingConfirmation,
    messages,
    addMessage,
    sendConfirmation,
    setPendingConfirmation,
    startExecution,
    markConfirmationSelected,
    setOptimisticExecutionProgress,
  ]);

  // Handle retry: re-send the user message that preceded the agent message
  const handleRetry = useCallback((messageId: string) => {
    // Find the agent message being retried
    const idx = messages.findIndex(m => m.id === messageId);
    if (idx < 0) return;
    // Walk backward to find the preceding user message
    let userContent = '';
    for (let i = idx - 1; i >= 0; i--) {
      if (messages[i].type === 'user') {
        userContent = messages[i].content;
        break;
      }
    }
    if (!userContent) return;
    handleSendMessage(userContent);
  }, [messages, handleSendMessage]);

  // Handle recall: send recall to backend, wait for recall_complete to clean UI
  const handleRecall = useCallback((messageId: string) => {
    if (!isConnected) {
      alert('与服务器的连接已断开，请刷新页面后重试。');
      return;
    }
    // Stash the message content so we can fill the input box after recall_complete
    const msg = messages.find(m => m.id === messageId);
    if (msg) {
      recalledContentRef.current = msg.content;
    }
    // Send recall command — UI cleanup happens in recall_complete handler
    sendRecall(messageId);
  }, [messages, sendRecall, isConnected]);

  // Handle brand button click — directly send to start analysis
  const handleBrandClick = useCallback((brandName: string) => {
    handleSendMessage(brandName);
  }, [handleSendMessage]);

  // Handle input change
  const handleInputChange = useCallback((value: string) => {
    setInputValue(value);
  }, []);

  // Cycle 3: Handle follow-up chip selection
  const handleFollowUpSelect = useCallback((suggestion: FollowUpSuggestion) => {
    clearFollowUpSuggestions();
    handleSendMessage(suggestion.message);
  }, [clearFollowUpSuggestions, handleSendMessage]);

  // Cycle 3: Handle reconnection banner actions
  const handleViewReport = useCallback(() => {
    const { setOpen } = useCanvasStore.getState();
    setOpen(true);
    setReconnectionTask(null);
  }, []);

  const handleReconnectionRetry = useCallback(() => {
    if (reconnectionTask) {
      handleSendMessage(reconnectionTask.brand_name);
      setReconnectionTask(null);
    }
  }, [reconnectionTask, handleSendMessage]);

  // Determine if we should show the empty state with example brands
  // Skip welcome screen when: loading history, has ?brand= param (auto-starting), or already executing
  const hasAutoStartParam = Boolean(autoStartBrand || autoStartDraft);
  const showExampleBrands = messages.length === 0 && !isAgentExecuting && !isLoadingHistory && !isAutoStartingPrompt && !hasAutoStartParam;

  const inputDisabled = Boolean(!isConnected);

  // Determine follow-up suggestions to show (backend-provided or defaults)
  const suggestionsToShow = followUpSuggestions.length > 0 ? followUpSuggestions : (
    !isAgentExecuting && activeTask?.status === 'completed' && stageResults.length > 0 ? DEFAULT_FOLLOWUPS : []
  );

  // Determine lightweight badge label for follow-up operations
  const getLightweightLabel = (): string | undefined => {
    if (!isAgentExecuting || !executionProgress) return undefined;
    const stage = executionProgress.stage?.toLowerCase() || '';
    if (stage.includes('drill_down')) return '思考中...';
    if (stage.includes('compare')) return '对比中...';
    return undefined;
  };

  const liveCurrentStage = isAgentExecuting
    ? executionProgress?.stage
    : activeTask?.current_stage ?? executionProgress?.stage;
  const liveProgress = isAgentExecuting
    ? executionProgress?.progress
    : activeTask?.progress ?? executionProgress?.progress;
  const liveProgressMessage = isAgentExecuting
    ? executionProgress?.details
    : activeTask?.progress_message ?? executionProgress?.details;
  const shouldShowUsageSummary = Boolean(
    !isAgentExecuting &&
    activeTask &&
    ['completed', 'failed', 'cancelled'].includes(activeTask.status) &&
    (
      (activeTask.llm_total_latency_ms ?? 0) > 0 ||
      (activeTask.llm_total_tokens ?? 0) > 0 ||
      (activeTask.llm_estimated_cost ?? 0) > 0 ||
      (activeTask.llm_call_count ?? 0) > 0
    )
  );
  const formatTokenCount = (value?: number): string | null => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return null;
    }
    return value.toLocaleString('zh-CN');
  };
  const formatEstimatedCost = (value?: number): string | null => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return null;
    }
    const digits = value >= 1 ? 2 : 4;
    return `¥${value.toFixed(digits)}`;
  };
  const formatCallCount = (value?: number): string | null => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return null;
    }
    return `${value} 次调用`;
  };
  const formatTotalLatency = (value?: number): string | null => {
    if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) {
      return null;
    }
    if (value < 1000) {
      return `${Math.round(value)}ms`;
    }
    if (value < 60_000) {
      return `${(value / 1000).toFixed(value >= 10_000 ? 1 : 2)}s`;
    }
    const totalSeconds = Math.round(value / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    return `${minutes}m ${seconds}s`;
  };
  const usageCallCountLabel = formatCallCount(activeTask?.llm_call_count);
  const usageLatencyLabel = formatTotalLatency(activeTask?.llm_total_latency_ms);
  const usageTokenLabel = formatTokenCount(activeTask?.llm_total_tokens);
  const usageCostLabel = formatEstimatedCost(activeTask?.llm_estimated_cost);

  return (
    <div className={cn('relative flex flex-col h-full bg-[var(--bg-primary)]', className)}>
      {/* Cycle 3: Task status badge in header area */}
      {(activeTask || (isAgentExecuting && executionProgress)) && (
        <div
          className="flex items-center justify-between px-4 py-1.5 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            {shouldShowUsageSummary && (
              <div
                className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium whitespace-nowrap"
                style={{
                  background: 'rgba(15,23,42,0.04)',
                  color: 'var(--text-secondary)',
                }}
              >
                {usageCallCountLabel && <span>{usageCallCountLabel}</span>}
                {usageCallCountLabel && (usageLatencyLabel || usageTokenLabel || usageCostLabel) && <span aria-hidden="true">/</span>}
                {usageLatencyLabel && <span>{usageLatencyLabel}</span>}
                {usageLatencyLabel && (usageTokenLabel || usageCostLabel) && <span aria-hidden="true">/</span>}
                {usageTokenLabel && <span>{usageTokenLabel} tokens</span>}
                {usageTokenLabel && usageCostLabel && <span aria-hidden="true">/</span>}
                {usageCostLabel && <span>估算 {usageCostLabel}</span>}
              </div>
            )}
            <TaskStatusBadge
              status={isAgentExecuting ? 'running' : (activeTask?.status ?? 'running')}
              currentStage={liveCurrentStage}
              progress={liveProgress}
              progressMessage={liveProgressMessage}
              lightweightLabel={getLightweightLabel()}
            />
          </div>
        </div>
      )}

      {/* Connection status indicator */}
      {!isConnected && messages.length > 0 && (
        <div
          role="alert"
          aria-live="assertive"
          className="px-4 py-2 text-sm text-center flex items-center justify-center gap-2"
          style={{ backgroundColor: 'var(--bg-tertiary)', borderBottom: '1px solid var(--border-hover)' }}
        >
          <span style={{ color: 'var(--warning)' }}>
            连接断开
          </span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>
            您的分析会安全继续，结果将被保留
          </span>
        </div>
      )}
      {actionableBrowserStates.length > 0 && (
        <div className="flex flex-col">
          {actionableBrowserStates.map((state) => (
            <BrowserActionBanner
              key={state.requestId || `${state.platform}:${state.state}:${state.message}`}
              browserState={state}
            />
          ))}
        </div>
      )}

      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scroll-smooth"
        onScroll={updateAutoScrollState}
      >
        <div className="max-w-3xl mx-auto px-4 py-6">
          {/* Cycle 3: Reconnection banner */}
          {reconnectionTask && (
            <ReconnectionBanner
              task={reconnectionTask}
              onViewReport={handleViewReport}
              onRetry={handleReconnectionRetry}
              onDismiss={() => setReconnectionTask(null)}
            />
          )}

          {/* Loading state when entering from brand card */}
          {messages.length === 0 && (isLoadingHistory || isAutoStartingPrompt) && !showExampleBrands && (
            <div className="flex flex-col items-center justify-center py-20">
              <div
                className="animate-spin rounded-full h-8 w-8 border-2 mb-4"
                style={{ borderColor: 'var(--border-subtle)', borderTopColor: 'var(--color-primary)' }}
              />
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {autoStartDraft
                  ? '正在为当前看板准备 AI 解读...'
                  : autoStartBrand
                  ? `正在为「${autoStartBrand}」启动分析...`
                  : '加载对话历史...'}
              </p>
            </div>
          )}

          <MessageList
            messages={messages}
            onConfirmation={handleConfirmation}
            onRetry={handleRetry}
            onRecall={handleRecall}
            isAgentExecuting={isAgentExecuting}
            exampleBrands={showExampleBrands ? (exampleBrands || DEFAULT_EXAMPLE_BRANDS) : undefined}
            onBrandClick={handleBrandClick}
          />

          {/* Cycle 3: Safe-to-leave signal */}
          {showSafeToLeave && isAgentExecuting && (
            <div
              role="status"
              aria-live="polite"
              className="flex items-center gap-2 mt-3 px-3 py-2 rounded-lg animate-safe-leave"
              style={{
                background: 'rgba(99,102,241,0.06)',
                border: '1px solid rgba(99,102,241,0.15)',
              }}
            >
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                您可以
                <span className="font-medium" style={{ color: 'var(--text-primary)' }}>安全关闭此页面</span>
                ，分析完成后我们会通知您。
              </span>
            </div>
          )}

          {/* Stopped state */}
          {stopState?.isStopped && (
            <div
              className="mt-4 p-4 rounded-xl border"
              style={{ backgroundColor: 'var(--bg-tertiary)', borderColor: 'var(--border-hover)' }}
            >
              <div className="flex items-center gap-2 font-medium mb-2" style={{ color: 'var(--warning)' }}>
                <span>&#9208;&#65039;</span>
                <span>任务已停止</span>
              </div>
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                您可以在输入框中继续对话，或点击上方按钮重新开始。
              </p>
            </div>
          )}

          {/* Cycle 3: Follow-up suggestion chips */}
          {!isAgentExecuting && suggestionsToShow.length > 0 && (
            <FollowUpChips
              suggestions={suggestionsToShow}
              onSelect={handleFollowUpSelect}
            />
          )}
        </div>
      </div>

      {/* Input area */}
      <InputArea
        onSend={handleSendMessage}
        onStop={handleStopExecution}
        isExecuting={isAgentExecuting}
        disabled={inputDisabled}
        pendingConfirmation={pendingConfirmation}
        onConfirmation={handleConfirmation}
        value={inputValue}
        onChange={handleInputChange}
        placeholder={!isConnected ? '正在重新连接...' : undefined}
        progressMessage={liveProgressMessage}
      />
    </div>
  );
}

