'use client';

import { useRef, useEffect, useState, useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useConversationStore } from '@/stores/conversationStore';
import { useCanvasStore } from '@/stores/canvasStore';
import { useAioTakeoverStore } from '@/stores/aioTakeoverStore';
import { useWebSocket } from '@/hooks/useWebSocket';
import { useAioTakeoverHeartbeat } from '@/hooks/useAioTakeoverHeartbeat';
import { MessageList } from './MessageList';
import { TaskStatusBadge } from './TaskStatusBadge';
import { ReconnectionBanner } from './ReconnectionBanner';
import { FollowUpChips } from './FollowUpChips';
import { BrowserActionBanner } from './BrowserActionBanner';
import { InputArea } from './InputArea';
import { cn } from '@/lib/cn';
import { getUserFacingStageLabel } from '@/lib/workflowStageLabels';
import { DEFAULT_EXAMPLE_BRANDS, ExampleBrand } from '@/config/brands';
import { normalizePublicPlatformId } from '@/config/platformLabel';
import { api } from '@/services/api';
import { toast } from '@/components/ui/toast';
import { DEFAULT_FOLLOWUPS } from '@/types/task';
import type { CanvasContent, CanvasContentDataMap, CanvasContentType } from '@/types/canvas';
import type { Output } from '@/types/api';
import type { ContextTag } from '@/stores/contextStore';
import type { StageResult } from '@/types/snapshot';
import type { AnalysisTask, FollowUpSuggestion } from '@/types/task';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';
import type { ToolMode } from '@/types/toolMode';
import type { BrowserState } from '@/types/agent';
import type { Message as ChatMessage } from '@/types/message';
import type { AioTakeoverRecord } from '@/types/aio';
import {
  buildOutputCardsFromApiMessage,
  getSupersededHistoryMessageIds,
  rebuildPersistedLayers,
  VALID_OUTPUT_TYPES,
} from '@/adapters/chatMessage';
import { normalizeCanvasData } from '@/hooks/websocket/canvas';


interface ChatPanelProps {
  sessionId: string;
  className?: string;
  exampleBrands?: ExampleBrand[];
}

const INITIAL_HISTORY_MESSAGE_LIMIT = 30;
const STABLE_AIO_TAKEOVER_MODE = 'vnc_fallback' as const;
type ArtifactCategory = 'baseline' | 'panorama' | 'scenario';

const BROWSER_MESSAGE_KEYWORDS: Record<
  BrowserState['platform'],
  { labels: string[]; actionHints: string[] }
> = {
  doubao: {
    labels: ['豆包'],
    actionHints: ['需要登录', '需要验证', '页面弹窗', '完成登录', '完成验证', '关闭弹窗'],
  },
  deepseek: {
    labels: ['DeepSeek', 'Deep Seek'],
    actionHints: ['需要登录', '需要验证', '页面弹窗', '完成登录', '完成验证', '关闭弹窗'],
  },
  kimi: {
    labels: ['Kimi'],
    actionHints: ['需要登录', '需要验证', '页面弹窗', '完成登录', '完成验证', '关闭弹窗'],
  },
  yuanbao: {
    labels: ['元宝', 'Yuanbao'],
    actionHints: ['需要登录', '需要验证', '页面弹窗', '完成登录', '完成验证', '关闭弹窗'],
  },
};

function resolveBrowserActionMessageId(
  state: BrowserState,
  messages: ChatMessage[],
  assignedMessageIds: Set<string>,
): string | null {
  if (state.relatedMessageId) {
    return state.relatedMessageId;
  }

  const keywords = BROWSER_MESSAGE_KEYWORDS[state.platform];
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.type !== 'agent' || assignedMessageIds.has(message.id)) {
      continue;
    }

    const content = typeof message.content === 'string' ? message.content : '';
    if (!content) {
      continue;
    }

    const hasPlatformMention = keywords.labels.some((label) => content.includes(label));
    const hasActionHint = keywords.actionHints.some((hint) => content.includes(hint));
    if (hasPlatformMention && hasActionHint) {
      return message.id;
    }
  }

  return null;
}

function normalizeArtifactCategory(value: unknown): ArtifactCategory | undefined {
  if (value === 'baseline' || value === 'panorama' || value === 'scenario') {
    return value;
  }
  return undefined;
}

function buildHydratedCanvasContents(outputs: Output[]): CanvasContent[] {
  const sortedOutputs = [...(outputs || [])].sort((left, right) => {
    const leftSequence =
      typeof left.sequence === 'number' && Number.isFinite(left.sequence)
        ? left.sequence
        : Number.MAX_SAFE_INTEGER;
    const rightSequence =
      typeof right.sequence === 'number' && Number.isFinite(right.sequence)
        ? right.sequence
        : Number.MAX_SAFE_INTEGER;
    if (leftSequence !== rightSequence) {
      return leftSequence - rightSequence;
    }
    return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
  });
  const grouped = new Map<string, CanvasContent>();

  for (const output of sortedOutputs) {
    const artifactId = output.artifact_id || output.id;
    const rawType = typeof output.type === 'string' ? output.type : 'report';
    const canvasTypeStr = rawType.startsWith('report') ? 'report' : rawType;
    const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(
      canvasTypeStr as CanvasContentType,
    )
      ? (canvasTypeStr as CanvasContentType)
      : 'report';
    const createdAt = new Date(output.created_at);
    const normalizedData = normalizeCanvasData(
      outputType,
      output.data || {},
    ) as CanvasContentDataMap['report'];
    const category = normalizeArtifactCategory(output.category);
    const nextContent = {
      id: artifactId,
      type: outputType,
      title: output.title || output.type || '分析结果',
      data: normalizedData,
      createdAt,
      relatedMessageId: '',
      linkedMessageId: output.message_id,
      versions: [],
      currentVersionIndex: -1,
      outputSequence:
        typeof output.sequence === 'number' && Number.isFinite(output.sequence)
          ? output.sequence
          : undefined,
      category,
    } as CanvasContent;

    const existing = grouped.get(artifactId);
    if (!existing) {
      grouped.set(artifactId, nextContent);
      continue;
    }

    const previousVersion = {
      versionNumber: (existing.versions?.length ?? 0) + 1,
      timestamp: existing.createdAt.toISOString(),
      data: existing.data as Record<string, unknown>,
      linkedMessageId: existing.linkedMessageId,
      sourceSequence: existing.outputSequence,
    };

    grouped.set(artifactId, {
      ...existing,
      ...nextContent,
      outputSequence: nextContent.outputSequence ?? existing.outputSequence,
      versions: [previousVersion, ...(existing.versions || [])],
      currentVersionIndex: -1,
      hasNewVersion: existing.hasNewVersion,
    } as CanvasContent);
  }

  return Array.from(grouped.values());
}

function buildBrowserCanvasContent(state: BrowserState): CanvasContent | null {
  const takeoverId = state.takeover?.takeoverId;
  if (!takeoverId) return null;
  const blockingUrl = state.takeover?.blockingUrl || state.blockingUrl;
  const targetUrl = blockingUrl || state.takeover?.targetUrl;
  return {
    id: 'browser_runtime_workspace',
    type: 'browser',
    title: '云电脑工作区',
    data: {
      takeoverId,
      platform: state.platform,
      browserState: state,
      mode: state.takeover?.mode,
      targetUrl,
      description: state.message,
      itemCount: 1,
    },
    createdAt: new Date(),
    relatedMessageId: '',
    versions: [],
    currentVersionIndex: -1,
  };
}

function buildBrowserTakeoverFromRecord(record: AioTakeoverRecord): NonNullable<BrowserState['takeover']> {
  return {
    takeoverId: record.takeoverId,
    mode: record.mode,
    actionType:
      record.actionType === 'login' || record.actionType === 'verify' || record.actionType === 'modal'
        ? record.actionType
        : record.accessBundle.actionType === 'login' || record.accessBundle.actionType === 'verify' || record.accessBundle.actionType === 'modal'
          ? record.accessBundle.actionType
          : undefined,
    reasonCode: record.reasonCode ?? record.accessBundle.reasonCode ?? undefined,
    openPath: record.accessBundle.openPath ?? undefined,
    canvasConfigPath: record.accessBundle.canvasConfigPath || undefined,
    vncUrlPath: record.accessBundle.vncUrlPath || undefined,
    heartbeatPath: record.accessBundle.heartbeatPath || undefined,
    resolvePath: record.accessBundle.resolvePath || undefined,
    cancelPath: record.accessBundle.cancelPath || undefined,
    expiresAt: record.expiresAt || undefined,
    targetUrl: record.targetUrl ?? record.accessBundle.targetUrl ?? undefined,
    blockingUrl: record.blockingUrl ?? record.accessBundle.blockingUrl ?? undefined,
    blockingFingerprint:
      record.blockingFingerprint ?? record.accessBundle.blockingFingerprint ?? undefined,
  };
}

function buildCancelledTakeoverRecord(
  state: BrowserState,
  sessionId: string,
): AioTakeoverRecord | null {
  const takeover = state.takeover;
  if (!takeover?.takeoverId) {
    return null;
  }

  return {
    takeoverId: takeover.takeoverId,
    sessionId,
    platform: normalizePublicPlatformId(state.platform) || state.platform,
    mode: takeover.mode ?? STABLE_AIO_TAKEOVER_MODE,
    reason: state.actionHint || state.message,
    takeoverState: 'cancelled',
    actionType: takeover.actionType ?? state.actionType ?? null,
    reasonCode: takeover.reasonCode ?? state.reasonCode ?? null,
    frontendId: null,
    requestedAt: null,
    issuedAt: null,
    expiresAt: takeover.expiresAt ?? null,
    lastHeartbeatAt: null,
    targetUrl: takeover.targetUrl ?? null,
    blockingUrl: takeover.blockingUrl ?? state.blockingUrl ?? null,
    blockingFingerprint:
      takeover.blockingFingerprint ?? state.blockingFingerprint ?? null,
    accessBundle: {
      openPath: takeover.openPath ?? null,
      canvasConfigPath: takeover.canvasConfigPath ?? '',
      vncUrlPath: takeover.vncUrlPath ?? '',
      heartbeatPath: takeover.heartbeatPath ?? '',
      resolvePath: takeover.resolvePath ?? '',
      cancelPath: takeover.cancelPath ?? '',
      actionType: takeover.actionType ?? state.actionType ?? null,
      reasonCode: takeover.reasonCode ?? state.reasonCode ?? null,
      targetUrl: takeover.targetUrl ?? null,
      blockingUrl: takeover.blockingUrl ?? state.blockingUrl ?? null,
      blockingFingerprint:
        takeover.blockingFingerprint ?? state.blockingFingerprint ?? null,
    },
  };
}

function getBrowserActionCardKey(state: BrowserState): string {
  return state.requestId
    || state.takeover?.takeoverId
    || (state.blockingFingerprint
      ? `${state.platform}:${state.actionType || state.state}:${state.blockingFingerprint}`
      : `${state.platform}:${state.state}:${state.message}`);
}

export function ChatPanel({ sessionId, className, exampleBrands }: ChatPanelProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const recalledContentRef = useRef<string | null>(null);
  const autoScrollEnabledRef = useRef(true);
  const lastBrowserActionScrollKeyRef = useRef<string | null>(null);
  const artifactsHydratedRef = useRef(false);
  const artifactsHydratingPromiseRef = useRef<Promise<CanvasContent[]> | null>(null);
  const [inputValue, setInputValue] = useState('');
  const [selectedToolMode, setSelectedToolMode] = useState<ToolMode | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialArtifactId = searchParams.get('artifact_id');
  const autoStartBrand = initialArtifactId ? null : searchParams.get('brand');
  const autoStartDraft = initialArtifactId ? null : searchParams.get('draft');
  const shouldAutoSendDraft = !initialArtifactId && searchParams.get('autosend') === '1';
  const autoSentRef = useRef(false);
  const [isAutoStartingPrompt, setIsAutoStartingPrompt] = useState(Boolean(autoStartBrand || autoStartDraft));
  const safeToLeaveShownRef = useRef(false);
  const [showSafeToLeave, setShowSafeToLeave] = useState(false);
  const [reconnectionTask, setReconnectionTask] = useState<AnalysisTask | null>(null);
  const replayAnimatingRef = useRef(false);

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
    updateBrowserState,
    settleBrowserActionStates,
    wsBrowserActionResolution,
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

  // Load persisted messages on mount
  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const msgs = await api.getMessages(sessionId, { limit: INITIAL_HISTORY_MESSAGE_LIMIT });
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
            timestamp: msg.created_at ? new Date(msg.created_at) : undefined,
            ...(
              Array.isArray((msg.metadata as Record<string, unknown> | null)?.attachments)
                ? {
                    attachments: ((msg.metadata as Record<string, unknown>).attachments as Attachment[]),
                  }
                : {}
            ),
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

  const {
    browserWorkspace,
    clearBrowserWorkspace,
    contents: canvasContents,
    activeContentIndex: activeCanvasContentIndex,
    activeSurface,
    isOpen: isCanvasOpen,
    openBrowserWorkspace,
    setActiveSurface,
    setOpen: setCanvasOpen,
    updateBrowserWorkspace,
  } = useCanvasStore();
  const upsertTakeoverRegistration = useAioTakeoverStore(
    (state) => state.upsertRegistration,
  );
  const openedTakeoverIds = useAioTakeoverStore((state) => state.openedTakeoverIds);
  const openedRequestIds = useAioTakeoverStore((state) => state.openedRequestIds);
  const openedAtMsByTakeoverId = useAioTakeoverStore((state) => state.openedAtMsByTakeoverId);
  const markTakeoverOpened = useAioTakeoverStore((state) => state.markTakeoverOpened);
  const upsertTakeoverRecord = useAioTakeoverStore((state) => state.upsertRecord);
  const removeTakeoverRegistration = useAioTakeoverStore((state) => state.removeRegistration);
  const clearTakeover = useAioTakeoverStore((state) => state.clearTakeover);
  const hydrateArtifacts = useCallback(async (
    force = false,
    options?: { keepClosed?: boolean },
  ): Promise<CanvasContent[]> => {
    if (artifactsHydratedRef.current && !force) {
      return useCanvasStore.getState().contents;
    }

    if (artifactsHydratingPromiseRef.current && !force) {
      await artifactsHydratingPromiseRef.current;
      return useCanvasStore.getState().contents;
    }

    const promise = (async (): Promise<CanvasContent[]> => {
      try {
        const outputs = await api.getOutputs(sessionId);
        const hydratedContents = buildHydratedCanvasContents(outputs || []);
        let nextContents: CanvasContent[] = hydratedContents;
        useCanvasStore.setState((state) => {
          const existingById = new Map(state.contents.map((content) => [content.id, content]));
          const mergedContents = hydratedContents.map((content) => {
            const existing = existingById.get(content.id);
            if (!existing) {
              return content;
            }
            const nextVersionIndex =
              existing.currentVersionIndex >= 0
              && existing.currentVersionIndex < content.versions.length
                ? existing.currentVersionIndex
                : -1;
            return {
              ...content,
              currentVersionIndex: nextVersionIndex,
              hasNewVersion: existing.hasNewVersion ?? content.hasNewVersion,
            } as CanvasContent;
          });
          nextContents = mergedContents;
          const activeId = state.contents[state.activeContentIndex]?.id;
          const nextActiveIndex = activeId
            ? mergedContents.findIndex((content) => content.id === activeId)
            : -1;
          const resolvedActiveIndex =
            nextActiveIndex >= 0
              ? nextActiveIndex
              : Math.min(
                  state.activeContentIndex,
                  Math.max(0, mergedContents.length - 1),
                );
          return {
            contents: mergedContents,
            activeContentIndex: resolvedActiveIndex,
            activeSurface:
              mergedContents.length === 0 && state.browserWorkspace
                ? 'browser'
                : state.activeSurface,
          };
        });
        if (options?.keepClosed) {
          useCanvasStore.getState().setOpen(false);
        }
        artifactsHydratedRef.current = true;
        return nextContents;
      } catch (error) {
        // Silently ignore — artifacts will be populated via WebSocket events or retried on demand
        console.error('[ChatPanel] Failed to hydrate artifacts:', error);
        return useCanvasStore.getState().contents;
      } finally {
        artifactsHydratingPromiseRef.current = null;
      }
    })();

    artifactsHydratingPromiseRef.current = promise;
    return await promise;
  }, [sessionId]);

  useEffect(() => {
    if (!initialArtifactId) {
      return;
    }

    useCanvasStore.setState((state) => ({
      activeSurface: 'artifact',
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
    }));

    const focusArtifact = async () => {
      const hydratedContents = await hydrateArtifacts();
      const targetIndex = hydratedContents.findIndex((content) => content.id === initialArtifactId);
      if (targetIndex === -1) {
        return;
      }
      useCanvasStore.setState((state) => ({
        activeContentIndex: targetIndex,
        activeSurface: 'artifact',
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
      }));
    };

    void focusArtifact();
  }, [hydrateArtifacts, initialArtifactId]);

  useEffect(() => {
    artifactsHydratedRef.current = false;
    artifactsHydratingPromiseRef.current = null;
  }, [sessionId]);

  useEffect(() => {
    if (!initialArtifactId) {
      return;
    }

    const targetIndex = canvasContents.findIndex((content) => content.id === initialArtifactId);
    if (targetIndex === -1) {
      return;
    }

    const activeId = canvasContents[activeCanvasContentIndex]?.id;
    if (isCanvasOpen && activeSurface === 'artifact' && activeId === initialArtifactId) {
      return;
    }

    useCanvasStore.setState((state) => ({
      activeContentIndex: targetIndex,
      activeSurface: 'artifact',
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
    }));
  }, [
    activeCanvasContentIndex,
    activeSurface,
    canvasContents,
    initialArtifactId,
    isCanvasOpen,
  ]);

  useEffect(() => {
    if (!isCanvasOpen || activeSurface !== 'artifact' || artifactsHydratedRef.current) {
      return;
    }
    void hydrateArtifacts();
  }, [activeSurface, hydrateArtifacts, isCanvasOpen]);

  // Listen for recall-reload-artifacts: reload surviving artifacts from DB after recall
  useEffect(() => {
    let cancelled = false;
    const handler = async () => {
      try {
        artifactsHydratedRef.current = false;
        await hydrateArtifacts(true, { keepClosed: true });
        if (cancelled) return;
        setReconnectionTask(null);
      } catch {
        // Silently ignore — Canvas stays empty, user can refresh to recover
      }
    };
    window.addEventListener('recall-reload-artifacts', handler);
    return () => {
      cancelled = true;
      window.removeEventListener('recall-reload-artifacts', handler);
    };
  }, [hydrateArtifacts, sessionId]);

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
          if (latestTask && (latestTask.status === 'completed' || latestTask.status === 'failed')) {
            const outputs = await api.getOutputs(sessionId);
            if (cancelled) return;
            const hasRecoverableOutputs = (outputs || []).length > 0;
            setActiveTask(hasRecoverableOutputs ? latestTask : null);
            setReconnectionTask(hasRecoverableOutputs ? latestTask : null);
          } else {
            setActiveTask(latestTask);
            setReconnectionTask(null);
          }
          return;
        }

        const waitingForInput = task.latest_run?.status === 'waiting_input';

        if (task.status === 'running' && !waitingForInput) {
          // Restore progress UI
          useConversationStore.setState({ isAgentExecuting: true });
          if (task.progress > 0) {
            const stageLabel = getUserFacingStageLabel(task.current_stage);
            setExecutionProgress({
              stage: task.current_stage,
              stageName: stageLabel ?? task.current_stage,
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
        } else if (waitingForInput) {
          stopExecutionAction();
          setExecutionProgress(null);
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

  const actionableBrowserStates = useMemo(
    () => browserStates.filter((state) => state.requiresAction),
    [browserStates],
  );
  const browserActionCardStates = useMemo(
    () =>
      browserStates.filter(
        (state) =>
          Boolean(
            state.requestId ||
              state.takeover?.takeoverId ||
              state.actionType,
          ),
      ),
    [browserStates],
  );
  const actionableTakeoverStates = useMemo(
    () => actionableBrowserStates.filter((state) => Boolean(state.takeover?.takeoverId)),
    [actionableBrowserStates],
  );
  const actionableTakeoverAccess = useMemo(
    () =>
      actionableTakeoverStates
        .map((state) => state.takeover)
        .filter((takeover): takeover is NonNullable<BrowserState['takeover']> => Boolean(takeover?.takeoverId)),
    [actionableTakeoverStates],
  );

  const actionableBrowserCards = useMemo(() => {
    const assignedMessageIds = new Set<string>();
    const byMessageId = new Map<string, BrowserState[]>();
    const unassigned: BrowserState[] = [];

    browserActionCardStates.forEach((state) => {
      const messageId = resolveBrowserActionMessageId(state, messages, assignedMessageIds);
      if (!messageId) {
        unassigned.push(state);
        return;
      }

      assignedMessageIds.add(messageId);
      const existing = byMessageId.get(messageId) || [];
      existing.push(state);
      byMessageId.set(messageId, existing);
    });

    return { byMessageId, unassigned };
  }, [browserActionCardStates, messages]);
  const pendingBrowserActionCount = actionableBrowserStates.length;
  const latestBrowserActionScrollKey = useMemo(() => {
    if (actionableBrowserStates.length === 0) {
      return null;
    }
    return getBrowserActionCardKey(
      actionableBrowserStates[actionableBrowserStates.length - 1],
    );
  }, [actionableBrowserStates]);

  useEffect(() => {
    actionableTakeoverAccess.forEach((takeover) => {
      upsertTakeoverRegistration(takeover);
    });
  }, [actionableTakeoverAccess, upsertTakeoverRegistration]);

  useEffect(() => {
    if (!latestBrowserActionScrollKey) {
      lastBrowserActionScrollKeyRef.current = null;
      return;
    }
    if (lastBrowserActionScrollKeyRef.current === latestBrowserActionScrollKey) {
      return;
    }

    lastBrowserActionScrollKeyRef.current = latestBrowserActionScrollKey;
    autoScrollEnabledRef.current = true;

    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
    const scrollToBrowserAction = () => {
      const container = scrollRef.current;
      if (!container) {
        return;
      }

      const target = Array.from(
        container.querySelectorAll<HTMLElement>('[data-browser-action-card]'),
      ).find(
        (element) => element.dataset.browserActionCard === latestBrowserActionScrollKey,
      );

      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }

      container.scrollTo({
        top: container.scrollHeight,
        behavior: 'smooth',
      });
    };

    const animationFrame = window.requestAnimationFrame(() => {
      window.requestAnimationFrame(scrollToBrowserAction);
      timeoutHandle = setTimeout(scrollToBrowserAction, 250);
    });

    return () => {
      window.cancelAnimationFrame(animationFrame);
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    };
  }, [latestBrowserActionScrollKey]);

  const openedTakeoverAccess = useMemo(
    () =>
      actionableTakeoverAccess.filter(
        (takeover) => Boolean(openedTakeoverIds[takeover.takeoverId]),
      ),
    [actionableTakeoverAccess, openedTakeoverIds],
  );

  useAioTakeoverHeartbeat(openedTakeoverAccess, openedAtMsByTakeoverId);

  useEffect(() => {
    const actionableByTakeoverId = new Map<string, BrowserState>();
    actionableTakeoverStates.forEach((state) => {
      const takeoverId = state.takeover?.takeoverId;
      if (takeoverId) {
        actionableByTakeoverId.set(takeoverId, state);
      }
    });

    const currentTakeoverId =
      browserWorkspace?.type === 'browser' ? browserWorkspace.data.takeoverId : null;
    if (!currentTakeoverId) {
      return;
    }

    const nextState = actionableByTakeoverId.get(currentTakeoverId);
    if (!nextState) {
      return;
    }

    const nextContent = buildBrowserCanvasContent(nextState);
    if (nextContent) {
      updateBrowserWorkspace(nextContent as Extract<CanvasContent, { type: 'browser' }>);
    }
  }, [
    actionableTakeoverStates,
    browserWorkspace,
    updateBrowserWorkspace,
  ]);

  useEffect(() => {
    const currentTakeoverId =
      browserWorkspace?.type === 'browser' ? browserWorkspace.data.takeoverId : null;
    if (!currentTakeoverId) {
      return;
    }

    const isStillActionable = actionableTakeoverStates.some(
      (state) => state.takeover?.takeoverId === currentTakeoverId,
    );
    if (!isStillActionable) {
      clearBrowserWorkspace();
    }
  }, [actionableTakeoverStates, browserWorkspace, clearBrowserWorkspace]);

  const reopenTakeover = useCallback(async (state: BrowserState) => {
    const takeover = state.takeover;
    if (!takeover?.takeoverId) return;

    upsertTakeoverRegistration(takeover);
    const existingRegistration =
      useAioTakeoverStore.getState().registrations[takeover.takeoverId];

    try {
      const nextRecord = await api.openAioTakeover(
        takeover.openPath || `/api/v1/aio/takeovers/${takeover.takeoverId}/open`,
        {
          frontendId: existingRegistration?.frontendId ?? null,
          mode: STABLE_AIO_TAKEOVER_MODE,
        },
      );
      upsertTakeoverRecord(nextRecord);

      const nextTakeover = buildBrowserTakeoverFromRecord(nextRecord);
      const nextState: BrowserState = {
        ...state,
        takeover: nextTakeover,
        blockingUrl: nextTakeover.blockingUrl ?? state.blockingUrl,
        blockingFingerprint:
          nextTakeover.blockingFingerprint ?? state.blockingFingerprint,
        reasonCode: nextTakeover.reasonCode ?? state.reasonCode,
        message: state.message,
      };

      if (nextRecord.takeoverId !== takeover.takeoverId) {
        clearTakeover(takeover.takeoverId);
      }

      if (state.requestId) {
        updateBrowserState(state.requestId, {
          takeover: nextTakeover,
          blockingUrl: nextTakeover.blockingUrl ?? state.blockingUrl,
          blockingFingerprint:
            nextTakeover.blockingFingerprint ?? state.blockingFingerprint,
          reasonCode: nextTakeover.reasonCode ?? state.reasonCode,
          requiresAction: true,
        });
      }

      markTakeoverOpened(nextRecord.takeoverId, undefined, state.requestId);
      const content = buildBrowserCanvasContent(nextState);
      if (content) {
        openBrowserWorkspace(content as Extract<CanvasContent, { type: 'browser' }>);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '打开浏览器失败，请重试。');
    }
  }, [
    clearTakeover,
    markTakeoverOpened,
    openBrowserWorkspace,
    updateBrowserState,
    upsertTakeoverRecord,
    upsertTakeoverRegistration,
  ]);

  const handleResolveBrowserAction = useCallback(async (state: BrowserState) => {
    const requestId = state.requestId;
    if (!requestId) {
      return;
    }

    const takeover = state.takeover;
    if (takeover?.takeoverId && takeover.resolvePath) {
      const aioState = useAioTakeoverStore.getState();
      const registration = aioState.registrations[takeover.takeoverId];
      if (!registration?.frontendId) {
        toast.error('请先点击“打开浏览器”，完成操作后再确认。');
        return;
      }

      const previousMessage = state.message;
      const previousActionHint = state.actionHint;

      try {
        updateBrowserState(requestId, {
          state: 'waiting_response',
          requiresAction: false,
          message: '已收到完成确认，正在继续当前平台抓取...',
          actionHint: '已收到完成确认，正在继续当前平台抓取...',
        });
        const next = await api.resolveAioTakeover(takeover.resolvePath, {
          frontendId: registration.frontendId,
          mode: STABLE_AIO_TAKEOVER_MODE,
          clientObservation: 'user_confirmed_done_from_chat',
        });
        upsertTakeoverRecord(next);
        if (next.takeoverState === 'resolved') {
          removeTakeoverRegistration(takeover.takeoverId);
          updateBrowserState(requestId, {
            state: 'waiting_response',
            requiresAction: false,
            message: '已收到完成确认，正在继续当前平台抓取...',
            actionHint: '已收到完成确认，正在继续当前平台抓取...',
            takeover: buildBrowserTakeoverFromRecord(next),
            blockingUrl:
              next.blockingUrl ??
              next.accessBundle.blockingUrl ??
              state.blockingUrl,
            blockingFingerprint:
              next.blockingFingerprint ??
              next.accessBundle.blockingFingerprint ??
              state.blockingFingerprint,
            reasonCode: next.reasonCode ?? next.accessBundle.reasonCode ?? state.reasonCode,
          });
          toast.success('已收到完成确认，正在继续当前平台抓取。');
          return;
        }
        updateBrowserState(requestId, {
          state: state.state,
          requiresAction: true,
          message: '当前接管尚未完成，请稍后重试。',
          actionHint: '当前接管尚未完成，请稍后重试。',
          takeover: buildBrowserTakeoverFromRecord(next),
          blockingUrl:
            next.blockingUrl ??
            next.accessBundle.blockingUrl ??
            state.blockingUrl,
          blockingFingerprint:
            next.blockingFingerprint ??
            next.accessBundle.blockingFingerprint ??
            state.blockingFingerprint,
          reasonCode: next.reasonCode ?? next.accessBundle.reasonCode ?? state.reasonCode,
        });
        toast.error('当前接管尚未完成，请稍后重试。');
      } catch (error) {
        updateBrowserState(requestId, {
          state: state.state,
          requiresAction: true,
          message: previousMessage,
          actionHint: previousActionHint,
        });
        toast.error(error instanceof Error ? error.message : '提交完成失败，请重试。');
      }
      return;
    }

    wsBrowserActionResolution?.(requestId, 'completed');
    updateBrowserState(requestId, {
      requiresAction: false,
      message: '已收到完成确认，正在继续当前平台抓取...',
    });
  }, [
    removeTakeoverRegistration,
    updateBrowserState,
    upsertTakeoverRecord,
    wsBrowserActionResolution,
  ]);

  const handleSkipBrowserAction = useCallback(async (state: BrowserState) => {
    const requestId = state.requestId;
    if (!requestId) {
      return;
    }

    wsBrowserActionResolution?.(requestId, 'skip');

    const takeover = state.takeover;
    if (takeover?.takeoverId && takeover.cancelPath) {
      const aioState = useAioTakeoverStore.getState();
      const registration = aioState.registrations[takeover.takeoverId];

      try {
        const next = await api.cancelAioTakeover(takeover.cancelPath, {
          frontendId: registration?.frontendId ?? null,
          reason: 'user_skipped_from_chat',
        });
        upsertTakeoverRecord(next);
        removeTakeoverRegistration(takeover.takeoverId);
        updateBrowserState(requestId, {
          requiresAction: false,
          message: '已跳过该平台，本轮将继续其他平台采集。',
          actionHint: '已跳过该平台，本轮将继续其他平台采集。',
          takeover: buildBrowserTakeoverFromRecord(next),
          blockingUrl:
            next.blockingUrl ??
            next.accessBundle.blockingUrl ??
            state.blockingUrl,
          blockingFingerprint:
            next.blockingFingerprint ??
            next.accessBundle.blockingFingerprint ??
            state.blockingFingerprint,
          reasonCode: next.reasonCode ?? next.accessBundle.reasonCode ?? state.reasonCode,
        });
        if (
          browserWorkspace?.type === 'browser' &&
          browserWorkspace.data.takeoverId === takeover.takeoverId
        ) {
          clearBrowserWorkspace();
        }
        toast.info('已跳过该平台，本轮将继续其他平台采集。');
      } catch (error) {
        removeTakeoverRegistration(takeover.takeoverId);
        updateBrowserState(requestId, {
          requiresAction: false,
          message: '已跳过该平台，本轮将继续其他平台采集。',
          actionHint: '已跳过该平台，本轮将继续其他平台采集。',
        });
        if (
          browserWorkspace?.type === 'browser' &&
          browserWorkspace.data.takeoverId === takeover.takeoverId
        ) {
          clearBrowserWorkspace();
        }
        toast.error(
          error instanceof Error
            ? `平台已跳过，但清理浏览器会话失败：${error.message}`
            : '平台已跳过，但清理浏览器会话失败。',
        );
      }
      return;
    }

    updateBrowserState(requestId, {
      requiresAction: false,
      message: '已跳过该平台，本轮将继续其他平台采集。',
      actionHint: '已跳过该平台，本轮将继续其他平台采集。',
    });
  }, [
    browserWorkspace,
    clearBrowserWorkspace,
    removeTakeoverRegistration,
    upsertTakeoverRecord,
    updateBrowserState,
    wsBrowserActionResolution,
  ]);
  // Handle sending message
  const handleSendMessage = useCallback((
    content: string,
    attachments?: Attachment[],
    context?: ContextTag[],
    toolMode?: ToolMode | null,
  ) => {
    if ((!content.trim() && (!attachments || attachments.length === 0)) || isAgentExecuting) return;

    // If user types while there's a pending confirmation, clear it
    // (user chose to type freely instead of clicking an option)
    if (pendingConfirmation) {
      setPendingConfirmation(null);
    }

    // Add user message to local state
    addMessage({
      type: 'user',
      content: content.trim(),
      ...(attachments && attachments.length > 0 ? { attachments } : {}),
    });

    autoScrollEnabledRef.current = true;

    // Start execution state
    startExecution();

    // Send message via WebSocket (with optional context)
    sendMessage(content.trim(), context, attachments, toolMode);
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
    const conversationState = useConversationStore.getState();
    const takeoverState = useAioTakeoverStore.getState();

    conversationState.browserStates.forEach((state) => {
      if (!state.requiresAction) {
        return;
      }
      const localCancelledRecord = buildCancelledTakeoverRecord(state, sessionId);
      if (localCancelledRecord) {
        upsertTakeoverRecord(localCancelledRecord);
        removeTakeoverRegistration(localCancelledRecord.takeoverId);
      }
    });

    stopExecutionAction();
    settleBrowserActionStates('任务已停止，本轮接管已结束。', '任务已停止，本轮接管已结束。');
    clearBrowserWorkspace();
    Object.keys(takeoverState.registrations).forEach((takeoverId) => {
      removeTakeoverRegistration(takeoverId);
    });
    sendStopExecution();
  }, [
    clearBrowserWorkspace,
    removeTakeoverRegistration,
    sendStopExecution,
    sessionId,
    settleBrowserActionStates,
    stopExecutionAction,
    upsertTakeoverRecord,
  ]);

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

  const previousUserMessage = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.type !== 'user') {
        continue;
      }

      const content = typeof message.content === 'string' ? message.content.trim() : '';
      if (content) {
        return content;
      }
    }

    return null;
  }, [messages]);

  // Cycle 3: Handle follow-up chip selection
  const handleFollowUpSelect = useCallback((suggestion: FollowUpSuggestion) => {
    clearFollowUpSuggestions();
    handleSendMessage(suggestion.message);
  }, [clearFollowUpSuggestions, handleSendMessage]);

  // Cycle 3: Handle reconnection banner actions
  const handleViewReport = useCallback(async () => {
    await hydrateArtifacts();
    const { setOpen } = useCanvasStore.getState();
    setOpen(true);
    setReconnectionTask(null);
  }, [hydrateArtifacts]);

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

  const isWaitingForInput = !isAgentExecuting && activeTask?.latest_run?.status === 'waiting_input';
  const liveCurrentStage = isAgentExecuting
    ? executionProgress?.stage
    : activeTask?.current_stage ?? executionProgress?.stage;
  const liveProgress = isAgentExecuting
    ? executionProgress?.progress
    : activeTask?.progress ?? executionProgress?.progress;
  const liveProgressMessage = isAgentExecuting
    ? executionProgress?.details
    : (isWaitingForInput
      ? activeTask?.progress_message ?? executionProgress?.details
      : activeTask?.progress_message ?? executionProgress?.details);
  const inputPlaceholder = !isConnected
    ? '正在重新连接...'
    : isWaitingForInput
      ? '请继续补充信息，或点击上方按钮确认...'
      : messages.length > 0
        ? '继续追问当前结果，或输入新的分析问题...'
        : undefined;
  const hasBrowserWorkspace = Boolean(browserWorkspace);
  const handleFocusBrowserWorkspace = useCallback(() => {
    if (!browserWorkspace) {
      return;
    }
    setCanvasOpen(true);
    setActiveSurface('browser');
  }, [browserWorkspace, setActiveSurface, setCanvasOpen]);

  useEffect(() => {
    const resumedState = actionableTakeoverStates.find((state) => {
      const takeoverId = state.takeover?.takeoverId;
      return Boolean(
        (takeoverId && openedTakeoverIds[takeoverId]) ||
        (state.requestId && openedRequestIds[state.requestId]),
      );
    });
    if (!resumedState) {
      return;
    }

    const resumedContent = buildBrowserCanvasContent(resumedState);
    if (!resumedContent || resumedContent.type !== 'browser') {
      return;
    }

    const currentTakeoverId =
      browserWorkspace?.type === 'browser' ? browserWorkspace.data.takeoverId : null;
    if (currentTakeoverId === resumedContent.data.takeoverId) {
      return;
    }

    openBrowserWorkspace(resumedContent);
  }, [
    actionableTakeoverStates,
    browserWorkspace,
    openBrowserWorkspace,
    openedRequestIds,
    openedTakeoverIds,
  ]);

  return (
    <div className={cn('relative flex flex-col h-full bg-[var(--bg-primary)]', className)}>
      {/* Cycle 3: Task status badge in header area */}
      {(activeTask || (isAgentExecuting && executionProgress) || pendingBrowserActionCount > 0) && (
        <div
          className="flex items-center justify-between px-4 py-1.5 flex-shrink-0"
          style={{ borderBottom: '1px solid var(--border-subtle)' }}
        >
          <div className="flex-1" />
          <div className="flex items-center gap-2">
            {pendingBrowserActionCount > 0 && (
              hasBrowserWorkspace ? (
                <button
                  type="button"
                  onClick={handleFocusBrowserWorkspace}
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-colors"
                  style={{
                    background: 'rgba(245,158,11,0.12)',
                    color: 'var(--warning)',
                    border: '1px solid rgba(245,158,11,0.2)',
                  }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: 'var(--warning)' }}
                  />
                  云电脑已打开 · 待接管 {pendingBrowserActionCount}
                </button>
              ) : (
                <div
                  className="inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium"
                  style={{
                    background: 'rgba(245,158,11,0.12)',
                    color: 'var(--warning)',
                    border: '1px solid rgba(245,158,11,0.2)',
                  }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full"
                    style={{ background: 'var(--warning)' }}
                  />
                  待接管 {pendingBrowserActionCount}
                </div>
              )
            )}
            <TaskStatusBadge
              status={isAgentExecuting ? 'running' : (activeTask?.status ?? 'running')}
              waitingForInput={isWaitingForInput}
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
            renderAfterMessage={(message) => {
              const states = actionableBrowserCards.byMessageId.get(message.id);
              if (!states || states.length === 0) {
                return null;
              }

              return (
                <div className="flex flex-col gap-3">
                  {states.map((state) => {
                    const takeoverId = state.takeover?.takeoverId;
                    const cardKey = getBrowserActionCardKey(state);
                    const isOpened = Boolean(
                      (takeoverId && openedTakeoverIds[takeoverId]) ||
                      (state.requestId && openedRequestIds[state.requestId]),
                    );
                    const openedAtMs =
                      takeoverId ? openedAtMsByTakeoverId[takeoverId] : undefined;
                    return (
                      <div key={cardKey} data-browser-action-card={cardKey}>
                        <BrowserActionBanner
                          browserState={state}
                          isOpened={isOpened}
                          openedAtMs={openedAtMs}
                          onOpenTakeover={
                            state.takeover?.takeoverId
                              ? () => reopenTakeover(state)
                              : null
                          }
                          onResolve={() => handleResolveBrowserAction(state)}
                          onSkip={() => handleSkipBrowserAction(state)}
                        />
                      </div>
                    );
                  })}
                </div>
              );
            }}
          />

          {actionableBrowserCards.unassigned.length > 0 && (
            <div className="mt-4 flex flex-col gap-3">
              {actionableBrowserCards.unassigned.map((state) => {
                const takeoverId = state.takeover?.takeoverId;
                const cardKey = getBrowserActionCardKey(state);
                const isOpened = Boolean(
                  (takeoverId && openedTakeoverIds[takeoverId]) ||
                  (state.requestId && openedRequestIds[state.requestId]),
                );
                const openedAtMs =
                  takeoverId ? openedAtMsByTakeoverId[takeoverId] : undefined;
                return (
                  <div key={cardKey} data-browser-action-card={cardKey}>
                    <BrowserActionBanner
                      browserState={state}
                      isOpened={isOpened}
                      openedAtMs={openedAtMs}
                      onOpenTakeover={
                        state.takeover?.takeoverId
                          ? () => reopenTakeover(state)
                          : null
                      }
                      onResolve={() => handleResolveBrowserAction(state)}
                      onSkip={() => handleSkipBrowserAction(state)}
                    />
                  </div>
                );
              })}
            </div>
          )}

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
        placeholder={inputPlaceholder}
        progressMessage={liveProgressMessage}
        selectedToolMode={selectedToolMode}
        onToolModeChange={setSelectedToolMode}
        previousUserMessage={previousUserMessage}
      />
    </div>
  );
}

