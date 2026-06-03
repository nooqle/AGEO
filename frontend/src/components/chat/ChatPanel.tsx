'use client';

import { useRef, useEffect, useLayoutEffect, useState, useCallback, useMemo } from 'react';
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
import type { CanvasContent, CanvasContentDataMap, CanvasContentType } from '@/types/canvas';
import type { Message as ApiMessage, Output } from '@/types/api';
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
import { resolveCanonicalArtifactIdFromOutput } from '@/lib/artifactIdentity';
import {
  consumeDashboardChatHandoff,
  isDashboardChatHandoffAutosend,
  readDashboardChatHandoffValue,
  type DashboardChatHandoffPayload,
} from '@/lib/dashboardChatHandoff';


interface ChatPanelProps {
  sessionId: string;
  className?: string;
  exampleBrands?: ExampleBrand[];
}

interface DashboardHandoffView {
  entrySource: string | null;
  entityId: string | null;
  brand: string | null;
  monitorMode: string | null;
  questionSetLabel: string | null;
  sampleSummary: string | null;
  currentMetrics: string | null;
  taskTitle: string | null;
  taskGoal: string | null;
  runId: string | null;
  handoffId: string | null;
  intent: string | null;
  aiSources: string | null;
  draft: string | null;
}

const INITIAL_HISTORY_MESSAGE_LIMIT = 30;
const HISTORY_BACKFILL_BATCH_SIZE = 50;
const STABLE_AIO_TAKEOVER_MODE = 'vnc_fallback' as const;
type ArtifactCategory = 'baseline' | 'panorama' | 'scenario';
const DASHBOARD_AUTO_START_QUERY_KEYS = [
  'brand',
  'draft',
  'autosend',
  'handoff',
  'entry_source',
  'monitor_mode',
  'question_set_label',
  'sample_summary',
  'current_metrics',
  'run_id',
  'handoff_id',
  'intent',
  'task_title',
  'task_goal',
  'ai_sources',
  'entity_id',
  'monitoring_plan_id',
  'question_set_ids',
  'endpoint_ids',
  'monitoring_run_id',
  'error_stage',
];

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

function dashboardEntryLabel(value: string | null): string {
  if (value === 'dashboard_new_brand') return '新建品牌';
  if (value === 'dashboard_command_bar') return '看板反馈';
  return '品牌看板';
}

function dashboardMonitorModeLabel(value: string | null): string {
  if (value?.includes('scenario')) return '用户场景监测';
  if (value?.includes('panorama')) return '全景监测';
  return '品牌情报';
}

function compactDashboardText(value: string | null, fallback: string): string {
  const text = String(value || '').trim();
  if (!text) return fallback;
  return text.length > 96 ? `${text.slice(0, 95)}...` : text;
}

function DashboardHandoffEmptyState({
  context,
  disabled,
  onSend,
}: {
  context: DashboardHandoffView;
  disabled?: boolean;
  onSend: () => void;
}) {
  const brand = compactDashboardText(context.brand, '当前品牌');
  const taskTitle = compactDashboardText(context.taskTitle, '继续处理品牌情报');
  const objective = compactDashboardText(
    context.taskGoal || context.draft,
    '基于当前证据继续解释、补证或生成内容。',
  );
  const facts = [
    ['要处理的事', taskTitle],
    ['已分析范围', compactDashboardText(context.sampleSummary, '等待读取本轮证据')],
    ['关键指标', compactDashboardText(context.currentMetrics, '等待读取指标')],
    ['问题范围', compactDashboardText(context.questionSetLabel, dashboardMonitorModeLabel(context.monitorMode))],
  ];

  return (
    <div className="mx-auto flex max-w-2xl flex-col items-stretch justify-center py-16">
      <div className="rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-5 py-5">
        <div className="text-[12px] font-medium text-[var(--brand-primary)]">
          从看板继续
        </div>
        <h2 className="mt-2 text-[20px] font-semibold leading-7 text-[var(--text-primary)]">
          {brand}
        </h2>
        <p className="mt-3 text-[13px] leading-6 text-[var(--text-secondary)]">
          {objective}
        </p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {facts.map(([label, value]) => (
            <div
              key={label}
              className="rounded-[10px] border border-[var(--border-subtle)] bg-[var(--bg-secondary)] px-3 py-2"
            >
              <div className="text-[11px] text-[var(--text-tertiary)]">{label}</div>
              <div className="mt-1 truncate text-[13px] font-medium text-[var(--text-primary)]">
                {value}
              </div>
            </div>
          ))}
        </div>
        {context.aiSources ? (
          <div className="mt-3 text-[12px] leading-5 text-[var(--text-tertiary)]">
            回答平台：{context.aiSources}
          </div>
        ) : null}
        <div className="mt-5 flex flex-wrap items-center gap-3">
          <button
            type="button"
            disabled={disabled}
            onClick={onSend}
            className="inline-flex min-h-10 items-center justify-center rounded-lg bg-[var(--brand-primary)] px-4 py-2 text-[13px] font-semibold text-[var(--brand-contrast)] transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
          >
            发送到对话
          </button>
          <span className="text-[12px] leading-5 text-[var(--text-tertiary)]">
            补充反馈、追问证据，或生成下一步内容。
          </span>
        </div>
      </div>
    </div>
  );
}

function looksLikeCorruptedQuestionMarks(value: unknown): boolean {
  const normalized = typeof value === 'string' ? value.trim() : '';
  if (normalized.length < 8) {
    return false;
  }
  const meaningfulChars = Array.from(normalized).filter((char) => !/\s/.test(char));
  if (meaningfulChars.length < 8) {
    return false;
  }
  const questionLikeCount = meaningfulChars.filter((char) => char === '?' || char === '？').length;
  return questionLikeCount / meaningfulChars.length >= 0.6;
}

const KNOWN_CONFIRMATION_LABELS: Record<string, string> = {
  view_questions: '先查看问题内容',
  still_empty: '问题列表仍未显示',
  table_import_question_list: '确认导入问题列表',
  table_import_question_list_merge: '整合导入',
  table_import_question_list_replace: '替换导入',
  table_import_brand_info: '更新品牌/竞品信息',
  table_import_link_list: '作为链接清单继续',
  table_import_cancel: '暂不导入',
  run_answer_fetch: '先执行答案抓取',
  run_supplemental_fetch: '补采上一轮失败项',
  run_analysis_report: '重新生成分析报告',
};

function resolveKnownConfirmationLabel(value: unknown): string | null {
  if (typeof value !== 'string') {
    return null;
  }
  const normalized = value.trim();
  if (!normalized) {
    return null;
  }
  return KNOWN_CONFIRMATION_LABELS[normalized] || null;
}

function sanitizePersistedMessageContent(
  role: 'user' | 'agent',
  content: unknown,
  metadata: Record<string, unknown> | null,
): string {
  const normalized = typeof content === 'string' ? content.trim() : '';
  const directKnownLabel = resolveKnownConfirmationLabel(normalized);
  if (directKnownLabel) {
    return directKnownLabel;
  }
  if (!looksLikeCorruptedQuestionMarks(normalized)) {
    return normalized;
  }

  const selectedOptionId = metadata?.selected_option_id;
  const resolvedFromOptionId = resolveKnownConfirmationLabel(selectedOptionId);
  if (resolvedFromOptionId) {
    return resolvedFromOptionId;
  }

  const confirmationLabel = metadata && typeof metadata.confirmation_label === 'string'
    ? metadata.confirmation_label.trim()
    : '';
  if (confirmationLabel) {
    return confirmationLabel;
  }

  const selectedOptionLabel = metadata && typeof metadata.selected_option_label === 'string'
    ? metadata.selected_option_label.trim()
    : '';
  if (selectedOptionLabel) {
    return selectedOptionLabel;
  }

  const resolvedLabel = metadata && typeof metadata.resolved_label === 'string'
    ? metadata.resolved_label.trim()
    : '';
  if (resolvedLabel) {
    return resolvedLabel;
  }

  return role === 'user' ? '用户已确认继续' : '历史消息已恢复，请查看关联交付物。';
}

function sortOutputs(outputs: Output[]): Output[] {
  return [...(outputs || [])].sort((left, right) => {
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
}

function buildHydratedCanvasContent(output: Output): CanvasContent {
  const rawType = typeof output.type === 'string' ? output.type : 'report';
  const canvasTypeStr = rawType.startsWith('report') ? 'report' : rawType;
  const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(
    canvasTypeStr as CanvasContentType,
  )
    ? (canvasTypeStr as CanvasContentType)
    : 'report';
  const artifactId = resolveCanonicalArtifactIdFromOutput(output, outputType);
  const createdAt = new Date(output.created_at);
  const normalizedData = normalizeCanvasData(
    outputType,
    output.data || {},
  ) as CanvasContentDataMap['report'];
  const isHydrationStub = Boolean(
    output.metadata?.hydration_stub
    || (output.data && typeof output.data === 'object' && 'hydration_stub' in output.data),
  );
  const category = normalizeArtifactCategory(output.category);
  return {
    id: artifactId,
    type: outputType,
    title: output.title || output.type || '分析结果',
    data: normalizedData,
    createdAt,
    relatedMessageId: '',
    linkedMessageId: output.message_id,
    sourceOutputId: output.id,
    isHydrationStub,
    versions: [],
    currentVersionIndex: -1,
    outputSequence:
      typeof output.sequence === 'number' && Number.isFinite(output.sequence)
        ? output.sequence
        : undefined,
    category,
  } as CanvasContent;
}

function buildHistoryCanvasStubFromMessage(
  message: ApiMessage,
  sessionId: string,
): CanvasContent | null {
  const outputCards = buildOutputCardsFromApiMessage(message, sessionId);
  const card = outputCards?.[0];
  if (!card) {
    return null;
  }

  return {
    id: card.id,
    type: card.type,
    title: card.title,
    data: {
      description: card.preview.description,
      metrics: card.preview.metrics,
      itemCount: card.preview.itemCount,
    } as CanvasContentDataMap['report'],
    createdAt: message.created_at ? new Date(message.created_at) : new Date(),
    relatedMessageId: message.id,
    linkedMessageId: message.id,
    sourceOutputId: card.outputId,
    isHydrationStub: true,
    versions: [],
    currentVersionIndex: -1,
    outputSequence:
      typeof message.sequence === 'number' && Number.isFinite(message.sequence)
        ? message.sequence
        : undefined,
  } as CanvasContent;
}

function retargetHistoryCanvasStub(
  stub: CanvasContent,
  messageId: string,
): CanvasContent {
  return {
    ...stub,
    relatedMessageId: messageId,
    linkedMessageId: messageId,
  } as CanvasContent;
}

function mergeHistoryCanvasStubs(stubs: CanvasContent[]) {
  if (stubs.length === 0) {
    return;
  }

  useCanvasStore.setState((state) => {
    const nextContents = [...state.contents];

    for (const stub of stubs) {
      const existingIndex = nextContents.findIndex((content) => content.id === stub.id);
      if (existingIndex === -1) {
        nextContents.push(stub);
        continue;
      }

      const existing = nextContents[existingIndex];
      if (!contentNeedsDetailHydration(existing, existing.sourceOutputId)) {
        nextContents[existingIndex] = {
          ...existing,
          linkedMessageId: stub.linkedMessageId ?? existing.linkedMessageId,
          relatedMessageId: stub.relatedMessageId || existing.relatedMessageId,
          outputSequence: stub.outputSequence ?? existing.outputSequence,
        } as CanvasContent;
        continue;
      }

      nextContents[existingIndex] = {
        ...stub,
        hasNewVersion: existing.hasNewVersion,
      } as CanvasContent;
    }

    return {
      contents: nextContents,
      activeContentIndex: Math.min(
        state.activeContentIndex,
        Math.max(0, nextContents.length - 1),
      ),
      activeSurface:
        nextContents.length === 0 && state.browserWorkspace ? 'browser' : state.activeSurface,
    };
  });
}

function mergeRelatedOutputIds(
  existing: string[] | undefined,
  incoming: string[],
): string[] {
  return Array.from(new Set([...(existing || []), ...incoming]));
}

function buildHydratedCanvasContents(outputs: Output[]): CanvasContent[] {
  const sortedOutputs = sortOutputs(outputs);
  const grouped = new Map<string, CanvasContent>();

  for (const output of sortedOutputs) {
    const nextContent = buildHydratedCanvasContent(output);
    const artifactId = nextContent.id;

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

function buildRoutePlaceholderContent(
  artifactId: string,
  outputId?: string | null,
): CanvasContent | null {
  if (!artifactId.includes('report')) {
    return null;
  }

  const title = artifactId.includes('site_confidence')
    ? '官网 AI 友好度分析报告'
    : artifactId.includes('scenario')
      ? '用户场景分析报告'
      : '品牌全景分析报告';

  return {
    id: artifactId,
    type: 'report',
    title,
    data: {
      title,
      subtitle: '报告加载中，请稍候...',
    },
    createdAt: new Date(),
    relatedMessageId: '',
    linkedMessageId: '',
    sourceOutputId: outputId ?? undefined,
    isHydrationStub: true,
    versions: [],
    currentVersionIndex: -1,
  } as CanvasContent;
}

function reportNeedsCanonicalHydration(content: CanvasContent | null | undefined): boolean {
  if (!content || content.type !== 'report') {
    return false;
  }

  const data = content.data;
  const hasSections = Array.isArray(data.sections) && data.sections.length > 0;
  const hasFullMarkdown =
    typeof data.full_markdown === 'string' && data.full_markdown.trim().length > 0;
  const hasReportMarkdown =
    typeof data.report_markdown === 'string' && data.report_markdown.trim().length > 0;
  const hasLegacyContent =
    typeof data.content === 'string' && data.content.trim().length > 0;

  return !(hasSections || hasFullMarkdown || hasReportMarkdown || hasLegacyContent);
}

function contentNeedsDetailHydration(
  content: CanvasContent | null | undefined,
  outputId?: string | null,
): boolean {
  if (!content) {
    return true;
  }

  if (content.isHydrationStub) {
    return true;
  }

  if (outputId && content.sourceOutputId && content.sourceOutputId !== outputId) {
    return true;
  }

  return reportNeedsCanonicalHydration(content);
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
  const oldestLoadedMessageIdRef = useRef<string | null>(null);
  const loadedAllHistoryRef = useRef(false);
  const historyBackfillPromiseRef = useRef<Promise<boolean> | null>(null);
  const artifactsHydratedRef = useRef(false);
  const artifactsHydratingPromiseRef = useRef<Promise<CanvasContent[]> | null>(null);
  const artifactUrlSyncReadyRef = useRef(false);
  const stubHydrationOutputIdsRef = useRef<Set<string>>(new Set());
  const initialRouteCompactHydrationRequestedRef = useRef(false);
  const canonicalRouteArtifactKeysRef = useRef<Set<string>>(new Set());
  const artifactDetailHydrationPromisesRef = useRef<Map<string, Promise<CanvasContent | null>>>(
    new Map(),
  );
  const [inputValue, setInputValue] = useState('');
  const [selectedToolMode, setSelectedToolMode] = useState<ToolMode | null>(null);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialArtifactId = searchParams.get('artifact_id');
  const initialOutputId = searchParams.get('output_id');
  const [dashboardHandoff, setDashboardHandoff] = useState<DashboardChatHandoffPayload | null>(null);
  const [dashboardHandoffChecked, setDashboardHandoffChecked] = useState(Boolean(initialArtifactId));
  const hasAutoStartQueryParams = useMemo(
    () => !initialArtifactId && DASHBOARD_AUTO_START_QUERY_KEYS.some((key) => searchParams.has(key)),
    [initialArtifactId, searchParams],
  );
  const shouldReadDashboardHandoff = !initialArtifactId && searchParams.get('handoff') === '1';
  const readAutoStartParam = useCallback((key: string): string | null => {
    return readDashboardChatHandoffValue(dashboardHandoff, key) || searchParams.get(key)?.trim() || null;
  }, [dashboardHandoff, searchParams]);
  const readDashboardHandoffOnlyParam = useCallback((key: string): string | null => {
    return readDashboardChatHandoffValue(dashboardHandoff, key);
  }, [dashboardHandoff]);
  const autoStartBrand = initialArtifactId ? null : readAutoStartParam('brand');
  const autoStartDraft = initialArtifactId ? null : readDashboardHandoffOnlyParam('draft');
  const shouldAutoSendDraft =
    !initialArtifactId &&
    isDashboardChatHandoffAutosend(dashboardHandoff);
  const dashboardHandoffView = useMemo(() => {
    if (initialArtifactId) return null;
    const entrySource = readAutoStartParam('entry_source');
    const entityId = readAutoStartParam('entity_id');
    const brand = readAutoStartParam('brand');
    const monitorMode = readAutoStartParam('monitor_mode');
    const questionSetLabel = readAutoStartParam('question_set_label');
    const sampleSummary = readAutoStartParam('sample_summary');
    const currentMetrics = readAutoStartParam('current_metrics');
    const taskTitle = readAutoStartParam('task_title');
    const taskGoal = readAutoStartParam('task_goal');
    const runId = readAutoStartParam('run_id');
    const handoffId = readAutoStartParam('handoff_id');
    const intent = readAutoStartParam('intent');
    const aiSources = readAutoStartParam('ai_sources');
    const draft = readDashboardHandoffOnlyParam('draft');
    if (!entrySource && !entityId && !brand && !draft) return null;
    return {
      entrySource,
      entityId,
      brand,
      monitorMode,
      questionSetLabel,
      sampleSummary,
      currentMetrics,
      taskTitle,
      taskGoal,
      runId,
      handoffId,
      intent,
      aiSources,
      draft,
    } satisfies DashboardHandoffView;
  }, [initialArtifactId, readAutoStartParam, readDashboardHandoffOnlyParam]);
  const dashboardAutoContext = useMemo<ContextTag[]>(() => {
    if (initialArtifactId) return [];

    const entrySource = readAutoStartParam('entry_source');
    const monitorMode = readAutoStartParam('monitor_mode');
    const questionSetLabel = readAutoStartParam('question_set_label');
    const sampleSummary = readAutoStartParam('sample_summary');
    const currentMetrics = readAutoStartParam('current_metrics');
    const taskTitle = readAutoStartParam('task_title');
    const taskGoal = readAutoStartParam('task_goal');
    const runId = readAutoStartParam('run_id');
    const handoffId = readAutoStartParam('handoff_id');
    const intent = readAutoStartParam('intent');
    const aiSources = readAutoStartParam('ai_sources');
    const entityId = readAutoStartParam('entity_id');
    const brand = readAutoStartParam('brand');
    const monitoringPlanId = readAutoStartParam('monitoring_plan_id');
    const questionSetIds = readAutoStartParam('question_set_ids');
    const endpointIds = readAutoStartParam('endpoint_ids');
    const monitoringRunId = readAutoStartParam('monitoring_run_id');
    const errorStage = readAutoStartParam('error_stage');
    const draft = readDashboardHandoffOnlyParam('draft');
    const tags: ContextTag[] = [];

    if (entrySource || monitorMode) {
      const modeLabel = monitorMode?.includes('scenario')
        ? '用户场景监测'
        : '全景监测';
      tags.push({
        id: 'dashboard-structured-context',
        type: 'intent',
        label: '品牌看板',
        data: {
          entry_source: dashboardEntryLabel(entrySource),
          monitor_mode: dashboardMonitorModeLabel(monitorMode),
          entity_id: entityId,
          brand,
          monitoring_plan_id: monitoringPlanId,
          question_set_ids: questionSetIds ? questionSetIds.split(',').filter(Boolean) : [],
          endpoint_ids: endpointIds ? endpointIds.split(',').filter(Boolean) : [],
          monitoring_run_id: monitoringRunId,
          error_stage: errorStage,
          question_set_label: questionSetLabel,
          sample_summary: sampleSummary,
          current_metrics: currentMetrics,
          task_title: taskTitle,
          task_goal: taskGoal,
          run_id: runId,
          handoff_id: handoffId,
          intent,
          ai_sources: aiSources ? aiSources.split('、').filter(Boolean) : [],
        },
      });
      tags.push({
        id: 'dashboard-monitor-mode',
        type: 'intent',
        label: `分析范围：${modeLabel}`,
      });
    }
    if (questionSetLabel) {
      tags.push({
        id: 'dashboard-question-set',
        type: 'scenario',
        label: `问题范围：${questionSetLabel}`,
      });
    }
    if (sampleSummary) {
      tags.push({
        id: 'dashboard-sample-summary',
        type: 'intent',
        label: `已分析范围：${sampleSummary}`,
      });
    }
    if (currentMetrics) {
      tags.push({
        id: 'dashboard-current-metrics',
        type: 'intent',
        label: `当前指标：${currentMetrics}`,
      });
    }
    if (aiSources) {
      tags.push({
        id: 'dashboard-ai-sources',
        type: 'intent',
        label: `回答平台：${aiSources}`,
      });
    }
    if (brand || entityId || draft) {
      tags.push({
        id: 'dashboard-intelligence-answer-frame',
        type: 'intent',
        label: '情报研判：按结论、证据、影响、需要确认、下一步建议回答',
      });
    }

    return tags;
  }, [initialArtifactId, readAutoStartParam, readDashboardHandoffOnlyParam]);
  const stripAutoStartQueryParams = useCallback(() => {
    if (hasAutoStartQueryParams) {
      router.replace(`/chat/${sessionId}`, { scroll: false });
    }
  }, [hasAutoStartQueryParams, router, sessionId]);
  const autoSentRef = useRef(false);
  const [isAutoStartingPrompt, setIsAutoStartingPrompt] = useState(
    Boolean((autoStartBrand || autoStartDraft) && shouldAutoSendDraft),
  );
  const [reconnectionTask, setReconnectionTask] = useState<AnalysisTask | null>(null);
  const replayAnimatingRef = useRef(false);

  useEffect(() => {
    if (initialArtifactId || !shouldReadDashboardHandoff) {
      setDashboardHandoff(null);
      setDashboardHandoffChecked(true);
      return;
    }
    setDashboardHandoffChecked(false);
    setDashboardHandoff(consumeDashboardChatHandoff(sessionId));
    setDashboardHandoffChecked(true);
  }, [initialArtifactId, sessionId, shouldReadDashboardHandoff]);

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

  const hydratePersistedMessages = useCallback((msgs: ApiMessage[], prepend: boolean) => {
    if (!msgs || msgs.length === 0) {
      return;
    }

    const suppressedMessageIds = getSupersededHistoryMessageIds(msgs);
    const hydratedMessages: ChatMessage[] = [];
    const historyCanvasStubs: CanvasContent[] = [];
    const pendingOutputs: Array<{
      cards: NonNullable<ChatMessage['outputCards']>;
      canvasStub: CanvasContent | null;
      standaloneMessage: ChatMessage;
    }> = [];
    let lastAgentMessageIndex = -1;

    const attachPendingOutputsTo = (messageIndex: number) => {
      const target = hydratedMessages[messageIndex];
      if (!target || pendingOutputs.length === 0) {
        return;
      }

      const existingCards = target.outputCards || [];
      const existingKeys = new Set(
        existingCards.flatMap((card) => [card.id, card.outputId].filter(Boolean) as string[]),
      );
      const nextCards = [...existingCards];
      const nextRelatedOutputIds: string[] = [];

      for (const pending of pendingOutputs) {
        for (const card of pending.cards) {
          const cardKeys = [card.id, card.outputId].filter(Boolean) as string[];
          if (cardKeys.some((key) => existingKeys.has(key))) {
            continue;
          }
          nextCards.push(card);
          cardKeys.forEach((key) => existingKeys.add(key));
          nextRelatedOutputIds.push(card.id);
        }
        if (pending.canvasStub) {
          historyCanvasStubs.push(retargetHistoryCanvasStub(
            pending.canvasStub,
            target.id,
          ));
        }
      }

      target.outputCards = nextCards;
      target.metadata = {
        ...target.metadata,
        relatedOutputIds: mergeRelatedOutputIds(
          target.metadata.relatedOutputIds,
          nextRelatedOutputIds,
        ),
      };
      pendingOutputs.length = 0;
    };

    const flushPendingOutputsAsStandalone = () => {
      for (const pending of pendingOutputs) {
        hydratedMessages.push(pending.standaloneMessage);
        if (pending.canvasStub) {
          historyCanvasStubs.push(pending.canvasStub);
        }
      }
      pendingOutputs.length = 0;
    };

    for (let index = 0; index < msgs.length; index += 1) {
      const msg = msgs[index];
      const role = msg.role === 'agent' || msg.role === 'assistant' ? 'agent' : 'user';
      const outputCards = buildOutputCardsFromApiMessage(msg, sessionId);
      const canvasStub = buildHistoryCanvasStubFromMessage(msg, sessionId);
      if (canvasStub) {
        historyCanvasStubs.push(canvasStub);
      }
      const reconstructed = rebuildPersistedLayers(msg.metadata as Record<string, unknown> | null);
      const layers = reconstructed.layers;
      const messageId = msg.id || `history_${index}_${msg.created_at || 'unknown'}`;
      const messageTimestamp = msg.created_at ? new Date(msg.created_at) : new Date(0);
      const relatedOutputIds = outputCards?.map((card) => card.id) ?? [];
      const rawMetadata =
        typeof msg.metadata === 'object' && msg.metadata !== null
          ? (msg.metadata as Record<string, unknown>)
          : null;
      const messageMetadata =
        rawMetadata
          ? {
              canEdit: typeof rawMetadata.canEdit === 'boolean' ? rawMetadata.canEdit : false,
              canRollback:
                typeof rawMetadata.canRollback === 'boolean'
                  ? rawMetadata.canRollback
                  : role === 'agent',
              relatedOutputIds: Array.isArray(rawMetadata.relatedOutputIds)
                ? rawMetadata.relatedOutputIds.filter(
                    (value): value is string => typeof value === 'string' && value.length > 0,
                  )
                : relatedOutputIds,
              executionTime:
                typeof rawMetadata.executionTime === 'number'
                  ? rawMetadata.executionTime
                  : undefined,
            }
          : {
              canEdit: false,
              canRollback: role === 'agent',
              relatedOutputIds,
            };

      for (const sr of reconstructed.stageResults) {
        addStageResult(sr);
      }

      const chatMessage: ChatMessage = {
        id: messageId,
        type: role,
        content: sanitizePersistedMessageContent(
          role,
          msg.content,
          rawMetadata,
        ),
        timestamp: messageTimestamp,
        metadata: messageMetadata,
        ...(
          Array.isArray((msg.metadata as Record<string, unknown> | null)?.attachments)
            ? {
                attachments: ((msg.metadata as Record<string, unknown>).attachments as Attachment[]),
              }
            : {}
        ),
        ...(outputCards ? { outputCards } : {}),
        ...(layers ? { layers } : {}),
      };

      if (msg.type === 'output' && outputCards && outputCards.length > 0) {
        pendingOutputs.push({
          cards: outputCards,
          canvasStub,
          standaloneMessage: chatMessage,
        });
        continue;
      }

      if (role === 'user' && pendingOutputs.length > 0) {
        if (lastAgentMessageIndex >= 0) {
          attachPendingOutputsTo(lastAgentMessageIndex);
        } else {
          flushPendingOutputsAsStandalone();
        }
      }

      if (suppressedMessageIds.has(messageId)) {
        continue;
      }

      hydratedMessages.push(chatMessage);
      if (role === 'agent') {
        lastAgentMessageIndex = hydratedMessages.length - 1;
        attachPendingOutputsTo(lastAgentMessageIndex);
      }
    }

    if (pendingOutputs.length > 0) {
      if (lastAgentMessageIndex >= 0) {
        attachPendingOutputsTo(lastAgentMessageIndex);
      } else {
        flushPendingOutputsAsStandalone();
      }
    }

    if (hydratedMessages.length === 0) {
      mergeHistoryCanvasStubs(historyCanvasStubs);
      return;
    }

    useConversationStore.setState((state) => {
      const existingIds = new Set(state.messages.map((message) => message.id));
      const freshMessages = hydratedMessages.filter((message) => !existingIds.has(message.id));
      if (freshMessages.length === 0) {
        return {};
      }
      return {
        messages: prepend
          ? [...freshMessages, ...state.messages]
          : [...state.messages, ...freshMessages],
      };
    });

    mergeHistoryCanvasStubs(historyCanvasStubs);
  }, [addStageResult, sessionId]);

  const loadOlderHistoryUntil = useCallback(async (targetMessageId: string) => {
    if (!targetMessageId || loadedAllHistoryRef.current) {
      return false;
    }
    if (historyBackfillPromiseRef.current) {
      return historyBackfillPromiseRef.current;
    }

    const task = (async () => {
      while (!loadedAllHistoryRef.current && oldestLoadedMessageIdRef.current) {
        const batch = await api.getMessages(sessionId, {
          limit: HISTORY_BACKFILL_BATCH_SIZE,
          before: oldestLoadedMessageIdRef.current,
        });
        if (!batch || batch.length === 0) {
          loadedAllHistoryRef.current = true;
          return false;
        }

        hydratePersistedMessages(batch, true);
        oldestLoadedMessageIdRef.current = batch[0]?.id || oldestLoadedMessageIdRef.current;
        if (batch.length < HISTORY_BACKFILL_BATCH_SIZE) {
          loadedAllHistoryRef.current = true;
        }
        if (batch.some((message) => message.id === targetMessageId)) {
          return true;
        }
      }
      return false;
    })()
      .finally(() => {
        historyBackfillPromiseRef.current = null;
      });

    historyBackfillPromiseRef.current = task;
    return task;
  }, [hydratePersistedMessages, sessionId]);

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

      void (async () => {
        let el = scrollRef.current?.querySelector(`[data-message-id="${messageId}"]`) as HTMLElement | null;
        if (!el) {
          await loadOlderHistoryUntil(messageId);
          el = scrollRef.current?.querySelector(`[data-message-id="${messageId}"]`) as HTMLElement | null;
        }
        if (!el) {
          return;
        }
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        el.classList.add('message-highlight');
        setTimeout(() => el.classList.remove('message-highlight'), 3000);
      })();
    };
    window.addEventListener('scroll-to-message', handler);
    return () => window.removeEventListener('scroll-to-message', handler);
  }, [loadOlderHistoryUntil]);

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
        const initialHistoryLimit = initialArtifactId ? 12 : INITIAL_HISTORY_MESSAGE_LIMIT;
        const msgs = await api.getMessages(sessionId, { limit: initialHistoryLimit });
        if (cancelled) return;
        if (!msgs || msgs.length === 0) {
          loadedAllHistoryRef.current = true;
          return;
        }
        oldestLoadedMessageIdRef.current = msgs[0]?.id || null;
        loadedAllHistoryRef.current = msgs.length < initialHistoryLimit;
        hydratePersistedMessages(msgs, false);
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
  }, [initialArtifactId, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

  const {
    browserWorkspace,
    clearBrowserWorkspace,
    activeSurface,
    activeContentIndex,
    contents,
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
    options?: { keepClosed?: boolean; compact?: boolean },
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
        const keepClosedAfterHydration = Boolean(
          options?.keepClosed && !useCanvasStore.getState().isOpen,
        );
        const outputs = await api.getOutputs(sessionId, {
          compact: options?.compact ?? true,
        });
        const hydratedContents = buildHydratedCanvasContents(outputs || []);
        let nextContents: CanvasContent[] = hydratedContents;
        useCanvasStore.setState((state) => {
          const existingById = new Map(state.contents.map((content) => [content.id, content]));
          const canonicalRouteArtifactKey =
            initialArtifactId && initialOutputId
              ? `${initialArtifactId}::${initialOutputId}`
              : null;
          const hasCanonicalRouteTarget = Boolean(
            canonicalRouteArtifactKey
            && state.contents.some(
              (content) =>
                (content.id === initialArtifactId
                  || content.sourceOutputId === initialOutputId)
                && !contentNeedsDetailHydration(content, initialOutputId),
            ),
          );
          const safeHydratedContents = hasCanonicalRouteTarget
            ? hydratedContents.filter((content) => content.id !== initialArtifactId)
            : canonicalRouteArtifactKey
              ? hydratedContents.filter(
                  (content) =>
                    !(
                      content.id === initialArtifactId
                      && content.sourceOutputId === initialOutputId
                      && content.isHydrationStub
                      && canonicalRouteArtifactKeysRef.current.has(canonicalRouteArtifactKey)
                    ),
                )
            : hydratedContents;
          const hydratedIds = new Set(safeHydratedContents.map((content) => content.id));
          const mergedContents = safeHydratedContents.map((content) => {
            const existing = existingById.get(content.id);
            if (!existing) {
              return content;
            }
            if (content.isHydrationStub && !contentNeedsDetailHydration(existing, content.sourceOutputId)) {
              return {
                ...existing,
                outputSequence: content.outputSequence ?? existing.outputSequence,
              } as CanvasContent;
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
          // Preserve any in-flight artifacts that arrived over WebSocket but are
          // not part of this snapshot yet. Otherwise a slower hydrate response
          // can overwrite a freshly added preview artifact and snap the canvas
          // back to an older target.
          const preservedExisting = state.contents.filter(
            (content) => !hydratedIds.has(content.id),
          );
          nextContents = [...mergedContents, ...preservedExisting];
          const activeId = state.contents[state.activeContentIndex]?.id;
          const nextActiveIndex = activeId
            ? nextContents.findIndex((content) => content.id === activeId)
            : -1;
          const resolvedActiveIndex =
            nextActiveIndex >= 0
              ? nextActiveIndex
              : Math.min(
                  state.activeContentIndex,
                  Math.max(0, nextContents.length - 1),
                );
          return {
            contents: nextContents,
            activeContentIndex: resolvedActiveIndex,
            activeSurface:
              nextContents.length === 0 && state.browserWorkspace
                ? 'browser'
                : state.activeSurface,
          };
        });
        if (keepClosedAfterHydration) {
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
  }, [initialArtifactId, initialOutputId, sessionId]);

  useEffect(() => {
    if (initialArtifactId) {
      return;
    }

    void hydrateArtifacts(false, { keepClosed: true, compact: true });
  }, [hydrateArtifacts, initialArtifactId]);

  const hydrateTargetArtifact = useCallback(async (): Promise<CanvasContent | null> => {
    if (!initialArtifactId || !initialOutputId) {
      return null;
    }

    const existing = useCanvasStore.getState().contents.find((content) => content.id === initialArtifactId);
    if (existing && !contentNeedsDetailHydration(existing, initialOutputId)) {
      return existing;
    }

    const inFlightHydration =
      artifactDetailHydrationPromisesRef.current.get(initialOutputId)
      ?? (async (): Promise<CanvasContent | null> => {
        try {
          console.log('[ChatPanel] route hydrate fetch start', {
            artifactId: initialArtifactId,
            outputId: initialOutputId,
            sessionId,
          });
          const output = await api.getOutput(sessionId, initialOutputId);
          const content = buildHydratedCanvasContent(output);
          if (content.type === 'report') {
            console.warn('[ChatPanel] hydrated route artifact detail', {
              artifactId: content.id,
              outputId: initialOutputId,
              isHydrationStub: content.isHydrationStub,
              hasFullMarkdown: Boolean(content.data.full_markdown),
              hasReportMarkdown: Boolean(content.data.report_markdown),
              sectionsLen: Array.isArray(content.data.sections) ? content.data.sections.length : null,
              currentVersionIndex: content.currentVersionIndex,
            });
          }
          useCanvasStore.setState((state) => {
            const targetIndex = state.contents.findIndex(
              (item) =>
                item.id === initialArtifactId
                || item.id === content.id
                || item.sourceOutputId === initialOutputId,
            );
            const nextContents =
              targetIndex >= 0
                ? state.contents.map((item, index) => (
                  index === targetIndex
                    ? {
                        ...content,
                        hasNewVersion: item.hasNewVersion ?? content.hasNewVersion,
                      }
                    : item
                ))
                : [...state.contents, content];
            const resolvedIndex = nextContents.findIndex(
              (item) =>
                item.id === initialArtifactId
                || item.id === content.id
                || item.sourceOutputId === initialOutputId,
            );
            return {
              contents: nextContents,
              activeContentIndex:
                resolvedIndex >= 0 ? resolvedIndex : state.activeContentIndex,
              activeSurface: 'artifact',
              isOpen: true,
              mode: state.mode === 'hidden' ? 'split' : state.mode,
            };
          });
          console.log('[ChatPanel] route hydrate applied', {
            artifactId: content.id,
            outputId: initialOutputId,
            contentsCount: useCanvasStore.getState().contents.length,
            activeContentIndex: useCanvasStore.getState().activeContentIndex,
            isOpen: useCanvasStore.getState().isOpen,
          });
          if (initialArtifactId && initialOutputId) {
            canonicalRouteArtifactKeysRef.current.add(`${initialArtifactId}::${initialOutputId}`);
          }
          return content;
        } catch (error) {
          console.warn('[ChatPanel] Failed to hydrate target artifact eagerly:', error);
          return null;
        } finally {
          artifactDetailHydrationPromisesRef.current.delete(initialOutputId);
        }
      })();

    artifactDetailHydrationPromisesRef.current.set(initialOutputId, inFlightHydration);
    return await inFlightHydration;
  }, [initialArtifactId, initialOutputId, sessionId]);

  useEffect(() => {
    if (!initialArtifactId) {
      return;
    }

    useCanvasStore.setState((state) => ({
      ...(state.contents.some(
        (content) =>
          content.id === initialArtifactId
          || (initialOutputId ? content.sourceOutputId === initialOutputId : false),
      )
        ? null
        : (() => {
            const placeholder = buildRoutePlaceholderContent(initialArtifactId, initialOutputId);
            if (!placeholder) {
              return null;
            }
            return {
              contents: [...state.contents, placeholder],
              activeContentIndex: state.contents.length,
            };
          })()),
      activeSurface: 'artifact',
      isOpen: true,
      mode: state.mode === 'hidden' ? 'split' : state.mode,
    }));

    const focusArtifact = async () => {
      let targetIndex = useCanvasStore
        .getState()
        .contents.findIndex((content) => content.id === initialArtifactId);

      const currentTarget =
        targetIndex >= 0 ? useCanvasStore.getState().contents[targetIndex] : null;

      if (contentNeedsDetailHydration(currentTarget, initialOutputId)) {
        const hydratedTarget = await hydrateTargetArtifact();
        if (hydratedTarget) {
          targetIndex = useCanvasStore
            .getState()
            .contents.findIndex((content) => content.id === hydratedTarget.id);
        }
      }

      if (targetIndex === -1) {
        initialRouteCompactHydrationRequestedRef.current = true;
        const hydratedContents = await hydrateArtifacts(false, { compact: true });
        targetIndex = hydratedContents.findIndex(
          (content) => content.id === initialArtifactId
        );
      }
      const resolvedTarget =
        targetIndex >= 0 ? useCanvasStore.getState().contents[targetIndex] : null;
      if (targetIndex >= 0) {
        useCanvasStore.setState((state) => ({
          activeContentIndex: targetIndex,
          activeSurface: 'artifact',
          isOpen: true,
          mode: state.mode === 'hidden' ? 'split' : state.mode,
        }));

        // If the route targets a compact hydration stub, render it immediately
        // and let the later background hydration effect replace it with the
        // full payload. This avoids blocking initial navigation on a large
        // report/detail fetch.
        if (contentNeedsDetailHydration(resolvedTarget, initialOutputId)) {
          void hydrateTargetArtifact();
        }
        return;
      }

      if (targetIndex === -1) {
        const hydratedTarget = await hydrateTargetArtifact();
        if (hydratedTarget) {
          targetIndex = useCanvasStore
            .getState()
            .contents.findIndex((content) => content.id === hydratedTarget.id);
        }
      }
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
  }, [hydrateArtifacts, hydrateTargetArtifact, initialArtifactId, initialOutputId]);

  useLayoutEffect(() => {
    artifactsHydratedRef.current = false;
    artifactsHydratingPromiseRef.current = null;
    artifactUrlSyncReadyRef.current = !(initialArtifactId || initialOutputId);
    stubHydrationOutputIdsRef.current.clear();
    initialRouteCompactHydrationRequestedRef.current = false;
    canonicalRouteArtifactKeysRef.current.clear();
    artifactDetailHydrationPromisesRef.current.clear();
  }, [initialArtifactId, initialOutputId, sessionId]);

  useEffect(() => {
    if (!initialArtifactId || !initialOutputId) {
      return;
    }

    if (initialRouteCompactHydrationRequestedRef.current) {
      return;
    }

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;
    let idleCallbackId: number | null = null;
    const scheduleHydration = () => {
      if (cancelled) {
        return;
      }
      void hydrateArtifacts(false, { compact: true });
    };

    if (typeof window !== 'undefined' && 'requestIdleCallback' in window) {
      idleCallbackId = window.requestIdleCallback(scheduleHydration, { timeout: 2000 });
    } else {
      timeoutId = setTimeout(scheduleHydration, 1200);
    }

    return () => {
      cancelled = true;
      if (idleCallbackId !== null && typeof window !== 'undefined' && 'cancelIdleCallback' in window) {
        window.cancelIdleCallback(idleCallbackId);
      }
      if (timeoutId) {
        clearTimeout(timeoutId);
      }
    };
  }, [hydrateArtifacts, initialArtifactId, initialOutputId]);

  useEffect(() => {
    if (
      !isCanvasOpen
      || activeSurface !== 'artifact'
      || artifactsHydratedRef.current
      || Boolean(initialArtifactId && initialOutputId)
    ) {
      return;
    }
    void hydrateArtifacts();
  }, [activeSurface, hydrateArtifacts, initialArtifactId, initialOutputId, isCanvasOpen]);

  useEffect(() => {
    if (
      !initialArtifactId
      || !isCanvasOpen
      || activeSurface !== 'artifact'
      || artifactUrlSyncReadyRef.current
    ) {
      return;
    }

    const routeTargetIndex = contents.findIndex(
      (content) =>
        content.id === initialArtifactId
        || (initialOutputId ? content.sourceOutputId === initialOutputId : false),
    );

    if (routeTargetIndex === -1) {
      return;
    }

    const routeTarget = contents[routeTargetIndex];
    if (!routeTarget) {
      return;
    }

    if (activeContentIndex !== routeTargetIndex) {
      useCanvasStore.setState((state) => ({
        activeContentIndex: routeTargetIndex,
        activeSurface: 'artifact',
        isOpen: true,
        mode: state.mode === 'hidden' ? 'split' : state.mode,
      }));
      return;
    }

    if (!contentNeedsDetailHydration(routeTarget, initialOutputId)) {
      artifactUrlSyncReadyRef.current = true;
    }
  }, [
    activeContentIndex,
    activeSurface,
    contents,
    initialArtifactId,
    initialOutputId,
    isCanvasOpen,
  ]);

  useEffect(() => {
    if (!isCanvasOpen || activeSurface !== 'artifact') {
      return;
    }

    const activeContent = contents[activeContentIndex];
    if (!activeContent?.sourceOutputId || !contentNeedsDetailHydration(activeContent, activeContent.sourceOutputId)) {
      return;
    }

    const outputId = activeContent.sourceOutputId;
    if (stubHydrationOutputIdsRef.current.has(outputId)) {
      return;
    }

    stubHydrationOutputIdsRef.current.add(outputId);
    let cancelled = false;

    const hydrateStubArtifact = async () => {
      try {
        const inFlightHydration =
          artifactDetailHydrationPromisesRef.current.get(outputId)
          ?? (async (): Promise<CanvasContent | null> => {
            try {
              const output = await api.getOutput(sessionId, outputId);
              if (cancelled) {
                return null;
              }
              const hydratedContent = buildHydratedCanvasContent(output);
              if (hydratedContent.type === 'report') {
                console.warn('[ChatPanel] hydrated active artifact detail', {
                  artifactId: hydratedContent.id,
                  outputId,
                  isHydrationStub: hydratedContent.isHydrationStub,
                  hasFullMarkdown: Boolean(hydratedContent.data.full_markdown),
                  hasReportMarkdown: Boolean(hydratedContent.data.report_markdown),
                  sectionsLen: Array.isArray(hydratedContent.data.sections)
                    ? hydratedContent.data.sections.length
                    : null,
                  currentVersionIndex: hydratedContent.currentVersionIndex,
                });
              }
              useCanvasStore.setState((state) => {
                const targetIndex = state.contents.findIndex((item) => item.id === activeContent.id);
                if (targetIndex === -1) {
                  return state;
                }
                const nextContents = [...state.contents];
                nextContents[targetIndex] = {
                  ...hydratedContent,
                  hasNewVersion:
                    nextContents[targetIndex].hasNewVersion ?? hydratedContent.hasNewVersion,
                };
                return {
                  contents: nextContents,
                  activeContentIndex:
                    state.activeContentIndex === targetIndex ? targetIndex : state.activeContentIndex,
                };
              });
              return hydratedContent;
            } catch (error) {
              console.warn('[ChatPanel] Failed to hydrate stub artifact:', error);
              return null;
            } finally {
              artifactDetailHydrationPromisesRef.current.delete(outputId);
            }
          })();

        artifactDetailHydrationPromisesRef.current.set(outputId, inFlightHydration);
        await inFlightHydration;
      } catch (error) {
        console.warn('[ChatPanel] Failed to hydrate stub artifact:', error);
      } finally {
        stubHydrationOutputIdsRef.current.delete(outputId);
      }
    };

    void hydrateStubArtifact();
    return () => {
      cancelled = true;
    };
  }, [activeContentIndex, activeSurface, contents, isCanvasOpen, sessionId]);

  useEffect(() => {
    if (typeof window === 'undefined') {
      return;
    }
    const debugWindow = window as Window & {
      __spectaRouteHydrateDebug?: unknown;
    };
    const routeTargetIndex = initialArtifactId
      ? contents.findIndex(
          (content) =>
            content.id === initialArtifactId
            || (initialOutputId ? content.sourceOutputId === initialOutputId : false),
        )
      : -1;
    const routeTarget =
      routeTargetIndex >= 0 && routeTargetIndex < contents.length
        ? contents[routeTargetIndex]
        : null;
    debugWindow.__spectaRouteHydrateDebug = {
      initialArtifactId,
      initialOutputId,
      isCanvasOpen,
      activeSurface,
      activeContentIndex,
      contentsCount: contents.length,
      contents: contents.map((content) => ({
        id: content.id,
        type: content.type,
        sourceOutputId: content.sourceOutputId ?? null,
        isHydrationStub: Boolean(content.isHydrationStub),
        hasFullMarkdown:
          content.type === 'report' ? Boolean(content.data.full_markdown) : null,
        hasReportMarkdown:
          content.type === 'report' ? Boolean(content.data.report_markdown) : null,
        sectionsLen:
          content.type === 'report' && Array.isArray(content.data.sections)
            ? content.data.sections.length
            : 0,
        currentVersionIndex: content.currentVersionIndex,
      })),
      routeTargetIndex,
      routeTarget: routeTarget
        ? {
            id: routeTarget.id,
            sourceOutputId: routeTarget.sourceOutputId ?? null,
            isHydrationStub: Boolean(routeTarget.isHydrationStub),
            needsDetailHydration: contentNeedsDetailHydration(routeTarget, initialOutputId),
            hasFullMarkdown:
              routeTarget.type === 'report' ? Boolean(routeTarget.data.full_markdown) : null,
            hasReportMarkdown:
              routeTarget.type === 'report' ? Boolean(routeTarget.data.report_markdown) : null,
            sectionsLen:
              routeTarget.type === 'report' && Array.isArray(routeTarget.data.sections)
                ? routeTarget.data.sections.length
                : 0,
            currentVersionIndex: routeTarget.currentVersionIndex,
          }
        : null,
    };
  }, [
    activeContentIndex,
    activeSurface,
    contents,
    initialArtifactId,
    initialOutputId,
    isCanvasOpen,
  ]);

  useEffect(() => {
    if (!isCanvasOpen || activeSurface !== 'artifact') {
      return;
    }

    const activeContent = contents[activeContentIndex];
    if (!activeContent?.id) {
      return;
    }

    const currentArtifactParam = searchParams.get('artifact_id');
    const currentOutputParam = searchParams.get('output_id');

    const nextArtifactId = activeContent.id;
    const nextOutputId = activeContent.sourceOutputId ?? null;
    const routeTargetsActiveArtifact = currentArtifactParam === nextArtifactId;
    const routeMatchesActiveArtifact =
      routeTargetsActiveArtifact
      && (currentOutputParam ?? null) === nextOutputId
    ;

    if (!artifactUrlSyncReadyRef.current) {
      if (routeTargetsActiveArtifact || (!currentArtifactParam && !currentOutputParam)) {
        artifactUrlSyncReadyRef.current = true;
      } else {
        return;
      }
    }

    if (routeMatchesActiveArtifact) {
      return;
    }

    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.set('artifact_id', nextArtifactId);
    if (nextOutputId) {
      nextParams.set('output_id', nextOutputId);
    } else {
      nextParams.delete('output_id');
    }

    if (typeof window !== 'undefined') {
      const nextUrl = `/chat/${sessionId}?${nextParams.toString()}`;
      window.history.replaceState(window.history.state, '', nextUrl);
    }
  }, [
    activeContentIndex,
    activeSurface,
    contents,
    initialArtifactId,
    isCanvasOpen,
    searchParams,
    sessionId,
  ]);

  // Listen for recall-reload-artifacts: reload surviving artifacts from DB after recall
  useEffect(() => {
    let cancelled = false;
    const handler = async () => {
      try {
        artifactsHydratedRef.current = false;
        await hydrateArtifacts(true, { keepClosed: true, compact: true });
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
      if (initialArtifactId) {
        setReconnectionTask(null);
        return;
      }
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
            const outputs = await api.getOutputs(sessionId, { compact: true });
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
              stageName: stageLabel ?? '当前步骤',
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
  }, [initialArtifactId, sessionId]); // eslint-disable-line react-hooks/exhaustive-deps

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

  // Auto-send Dashboard handoffs after history has loaded, so context becomes part of the conversation.
  useEffect(() => {
    const draft = autoStartDraft?.trim() || '';
    const brand = autoStartBrand?.trim() || '';
    const autoMessage = draft || brand;
    const canAutoSendMessage = Boolean(autoMessage && shouldAutoSendDraft);
    const shouldAutoSendExistingDraft = Boolean(
      draft &&
      shouldAutoSendDraft &&
      messages.length > 0,
    );

    if (!autoMessage) {
      setIsAutoStartingPrompt(false);
      return;
    }

    if (!canAutoSendMessage) {
      setIsAutoStartingPrompt(false);
      if (draft) {
        setInputValue(draft);
      }
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
        stripAutoStartQueryParams();
      }
      return;
    }

    if (draft && !shouldAutoSendDraft && messages.length === 0) {
      setInputValue(draft);
      setIsAutoStartingPrompt(false);
      stripAutoStartQueryParams();
      return;
    }

    setIsAutoStartingPrompt(true);

    if (!isConnected) {
      const fallbackTimer = setTimeout(() => {
        if (!autoSentRef.current) {
          setIsAutoStartingPrompt(false);
          setInputValue(autoMessage);
          stripAutoStartQueryParams();
          toast.error('自动启动分析失败，请点击发送后重试');
        }
      }, 5000);
      return () => clearTimeout(fallbackTimer);
    }

    if (isAgentExecuting) {
      setIsAutoStartingPrompt(true);
      return;
    }

    autoSentRef.current = true;
    const timer = setTimeout(() => {
      stripAutoStartQueryParams();
      handleSendMessage(
        autoMessage,
        undefined,
        dashboardAutoContext.length > 0 ? dashboardAutoContext : undefined,
      );
      setIsAutoStartingPrompt(false);
    }, 500);

    return () => clearTimeout(timer);
  }, [
    autoStartBrand,
    autoStartDraft,
    dashboardAutoContext,
    shouldAutoSendDraft,
    messages.length,
    isConnected,
    isLoadingHistory,
    isAgentExecuting,
    handleSendMessage,
    stripAutoStartQueryParams,
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
      sendConfirmation(pendingConfirmation.requestId, {
        optionId,
        label: option?.label || resolveKnownConfirmationLabel(optionId) || optionId,
      });
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
      const requestId = inlineConf.requestId || '';

      // Mark the button as selected (disables re-clicking)
      if (lastAgentMsg) {
        markConfirmationSelected(lastAgentMsg.id, optionId);
      }

      // Add user message showing the selection
      addMessage({ type: 'user', content: label });

      // Start execution state (backend will restart workflow)
      startExecution();
      setOptimisticExecutionProgress(optionId);

      sendConfirmation(requestId, { optionId, label });
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

  const handleSendDashboardHandoff = useCallback(() => {
    const draft = dashboardHandoffView?.draft?.trim();
    const brand = dashboardHandoffView?.brand?.trim();
    const message =
      draft ||
      (brand
        ? `请基于当前品牌情报继续推进「${brand}」的分析任务。`
        : '请基于当前品牌情报继续推进分析任务。');
    handleSendMessage(
      message,
      undefined,
      dashboardAutoContext.length > 0 ? dashboardAutoContext : undefined,
    );
    stripAutoStartQueryParams();
  }, [dashboardAutoContext, dashboardHandoffView, handleSendMessage, stripAutoStartQueryParams]);

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

  // Determine if we should show the empty state with example brands
  // Skip welcome screen when: loading history, has ?brand= param (auto-starting), or already executing
  const hasAutoStartParam = Boolean(autoStartBrand || autoStartDraft);
  const hasDashboardHandoffView = Boolean(dashboardHandoffView);
  const isCheckingDashboardHandoff = !initialArtifactId && !dashboardHandoffChecked;
  const showExampleBrands =
    messages.length === 0 &&
    !isAgentExecuting &&
    !isLoadingHistory &&
    !isAutoStartingPrompt &&
    !hasAutoStartParam &&
    !hasDashboardHandoffView &&
    !isCheckingDashboardHandoff;

  const inputDisabled = Boolean(!isConnected);

  const suggestionsToShow = followUpSuggestions;

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
            />
          )}

          {/* Loading state when entering from brand card */}
          {messages.length === 0 && (isLoadingHistory || isAutoStartingPrompt || isCheckingDashboardHandoff) && !showExampleBrands && (
            <div className="flex flex-col items-center justify-center py-20">
              <div
                className="animate-spin rounded-full h-8 w-8 border-2 mb-4"
                style={{ borderColor: 'var(--border-subtle)', borderTopColor: 'var(--color-primary)' }}
              />
              <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
                {isCheckingDashboardHandoff
                  ? '正在读取看板里的品牌情报...'
                  : autoStartDraft
                  ? '正在准备下一步处理...'
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
            emptyStateOverride={
              !showExampleBrands && dashboardHandoffView ? (
                <DashboardHandoffEmptyState
                  context={dashboardHandoffView}
                  disabled={inputDisabled || isAgentExecuting}
                  onSend={handleSendDashboardHandoff}
                />
              ) : undefined
            }
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

