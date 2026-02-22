'use client';

import { useRef, useEffect, useState, useCallback } from 'react';
import { useSearchParams } from 'next/navigation';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { MessageList } from './MessageList';
import { MiniProgress } from './MiniProgress';
import { ConfirmationCard } from './ConfirmationCard';
import { StageResultCard } from './StageResultCard';
import { TaskStatusBadge } from './TaskStatusBadge';
import { ReconnectionBanner } from './ReconnectionBanner';
import { FollowUpChips } from './FollowUpChips';
import { InputArea } from './InputArea';
import { cn } from '@/lib/cn';
import { DEFAULT_EXAMPLE_BRANDS, ExampleBrand } from '@/config/brands';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { DEFAULT_FOLLOWUPS } from '@/types/task';
import type { CanvasContent, CanvasContentType, CanvasContentDataMap } from '@/types/canvas';
import type { ContextTag } from '@/stores/contextStore';
import type { AnalysisTask, FollowUpSuggestion } from '@/types/task';
import type { StageResult } from '@/types/snapshot';

const VALID_OUTPUT_TYPES: CanvasContentType[] = ['report', 'chart', 'dataTable', 'selection', 'workflow', 'questionList', 'fetchResults'];

interface ChatPanelProps {
  sessionId: string;
  className?: string;
  exampleBrands?: ExampleBrand[];
}

export function ChatPanel({ sessionId, className, exampleBrands }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [inputValue, setInputValue] = useState('');
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const searchParams = useSearchParams();
  const autoSentRef = useRef(false);
  const safeToLeaveShownRef = useRef(false);
  const [showSafeToLeave, setShowSafeToLeave] = useState(false);
  const [reconnectionTask, setReconnectionTask] = useState<AnalysisTask | null>(null);
  const replayAnimatingRef = useRef(false);

  const {
    messages,
    isAgentExecuting,
    stopState,
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
    setFollowUpSuggestions,
    clearFollowUpSuggestions,
    addStageResult,
    setExecutionProgress,
  } = useConversationStore();

  // Initialize WebSocket connection
  const {
    sendMessage,
    sendConfirmation,
    stopExecution: sendStopExecution,
    isConnected,
  } = useWebSocket(sessionId);

  // Reset stores on mount (component is keyed by sessionId, so this runs on session switch)
  useEffect(() => {
    resetConversation();
    useCanvasStore.getState().clearContents();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Auto-scroll to bottom
  useEffect(() => {
    if (scrollRef.current) {
      const { scrollHeight, clientHeight, scrollTop } = scrollRef.current;
      const isNearBottom = scrollHeight - clientHeight - scrollTop < 100;

      if (isNearBottom) {
        scrollRef.current.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: 'smooth',
        });
      }
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

  // Load persisted messages on mount
  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const msgs = await api.getMessages(sessionId, { limit: 100 });
        if (cancelled || !msgs || msgs.length === 0) return;
        // Convert API messages to store format, reconstructing outputCards from output_data
        for (const msg of msgs) {
          const role = msg.role === 'agent' || msg.role === 'assistant' ? 'agent' : 'user';
          const outputType = msg.output_type && VALID_OUTPUT_TYPES.includes(msg.output_type as CanvasContentType)
            ? (msg.output_type as CanvasContentType)
            : null;
          const parsed = msg.output_data ?? null;
          const outputCards = outputType && parsed ? [{
            id: msg.id || `output_${Date.now()}`,
            type: outputType,
            title: (parsed as Record<string, unknown>)?.headline as string || (parsed as Record<string, unknown>)?.title as string || msg.content || '分析结果',
            preview: { description: (parsed as Record<string, unknown>)?.executive_summary as string || (parsed as Record<string, unknown>)?.description as string },
          }] : undefined;
          addMessage({
            type: role,
            content: msg.content || '',
            ...(outputCards ? { outputCards } : {}),
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
        const validTypes: CanvasContentType[] = ['report', 'chart', 'dataTable', 'selection', 'workflow', 'questionList', 'fetchResults'];
        for (const output of outputs) {
          const outputType: CanvasContentType = validTypes.includes(output.type as CanvasContentType)
            ? (output.type as CanvasContentType)
            : 'report';
          addContent({
            id: output.id,
            type: outputType,
            title: output.title || output.type || '分析结果',
            data: (output.data || {}) as CanvasContentDataMap['report'],
            createdAt: new Date(output.created_at),
            relatedMessageId: '',
            versions: [],
            currentVersionIndex: -1,
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
        if (cancelled || !task) return;

        setActiveTask(task);

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

  // Handle sending message
  const handleSendMessage = useCallback((content: string, _attachments?: unknown[], context?: ContextTag[]) => {
    if (!content.trim() || isAgentExecuting) return;
    if (pendingConfirmation && !pendingConfirmation.allowTextInput) return;

    // Add user message to local state
    addMessage({
      type: 'user',
      content: content.trim(),
    });

    // Start execution state
    startExecution();

    // Send message via WebSocket (with optional context)
    sendMessage(content.trim(), context);
  }, [addMessage, startExecution, sendMessage, isAgentExecuting, pendingConfirmation]);

  // Auto-send brand name when navigating from Dashboard with ?brand= param
  useEffect(() => {
    const brand = searchParams.get('brand');
    if (brand && !autoSentRef.current && messages.length === 0 && isConnected) {
      autoSentRef.current = true;
      // Small delay to ensure WebSocket is fully ready
      const timer = setTimeout(() => {
        handleSendMessage(brand);
      }, 500);
      return () => clearTimeout(timer);
    }
  }, [searchParams, messages.length, isConnected, handleSendMessage]);

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

      // Send confirmation to backend — selection must be a plain string
      sendConfirmation('', label);
    }
  }, [pendingConfirmation, messages, addMessage, sendConfirmation, setPendingConfirmation, startExecution, markConfirmationSelected]);

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
  const hasBrandParam = !!searchParams.get('brand');
  const showExampleBrands = messages.length === 0 && !isAgentExecuting && !isLoadingHistory && !hasBrandParam;

  const inputDisabled = Boolean(!isConnected || (pendingConfirmation && !pendingConfirmation.allowTextInput));

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

  return (
    <div className={cn('relative flex flex-col h-full bg-[--bg-primary]', className)}>
      {/* Cycle 3: Task status badge in header area */}
      {activeTask && (
        <div
          className="flex items-center justify-between px-4 py-1.5 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-default)' }}
        >
          <div className="flex-1" />
          <TaskStatusBadge
            status={activeTask.status}
            currentStage={activeTask.current_stage}
            progress={activeTask.progress}
            progressMessage={activeTask.progress_message}
            lightweightLabel={getLightweightLabel()}
          />
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

      {pendingConfirmation && (
        <div className="absolute inset-0 z-20 bg-black/40 backdrop-blur-md flex items-start justify-center px-4 py-12">
          <div className="w-full max-w-2xl">
            <ConfirmationCard
              title={pendingConfirmation.stepName || '需要您的确认'}
              message={pendingConfirmation.message}
              options={pendingConfirmation.options.map((option) => ({
                id: option.id,
                label: option.label,
                description: option.description,
                variant: option.recommended ? 'primary' : 'secondary',
              }))}
              onConfirm={handleConfirmation}
            />
          </div>
        </div>
      )}

      {/* Message list */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto scroll-smooth"
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
          {messages.length === 0 && (isLoadingHistory || hasBrandParam) && !showExampleBrands && (
            <div className="flex flex-col items-center justify-center py-20">
              <div
                className="animate-spin rounded-full h-8 w-8 border-2 mb-4"
                style={{ borderColor: 'var(--border-default)', borderTopColor: 'var(--color-primary)' }}
              />
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {hasBrandParam ? `正在为「${searchParams.get('brand')}」启动分析...` : '加载对话历史...'}
              </p>
            </div>
          )}

          <MessageList
            messages={messages}
            onConfirmation={handleConfirmation}
            onRetry={handleRetry}
            isAgentExecuting={isAgentExecuting}
            exampleBrands={showExampleBrands ? (exampleBrands || DEFAULT_EXAMPLE_BRANDS) : undefined}
            onBrandClick={handleBrandClick}
          />

          {/* Stage Result Cards (progressive wait experience) */}
          {stageResults.length > 0 && (
            <div className="mt-4 space-y-2">
              {stageResults.map((result, index) => (
                <StageResultCard
                  key={`${result.stage}-${result.resultType}-${index}`}
                  result={result}
                  isLatest={index === stageResults.length - 1 && isAgentExecuting}
                  isReplay={Boolean((result.data as Record<string, unknown>)?._isReplay)}
                />
              ))}
            </div>
          )}

          {/* Mini Progress */}
          {isAgentExecuting && executionProgress && executionProgress.steps && executionProgress.steps.length > 0 && (() => {
            const visibleSteps = executionProgress.steps.filter(s => s.status !== 'skipped');
            return visibleSteps.length > 0 ? (
              <div className="mt-4">
                <MiniProgress
                  steps={visibleSteps.map((s) => ({
                    id: s.id,
                    label: s.label,
                    description: s.description,
                    status: s.status,
                  }))}
                  isExecuting={isAgentExecuting}
                />
              </div>
            ) : null;
          })()}

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
      />
    </div>
  );
}
