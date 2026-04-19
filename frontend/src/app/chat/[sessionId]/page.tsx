'use client';

import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { ChatLayout } from '@/components/layout/ChatLayout';
import { ChatPanel } from '@/components/chat';
import { CanvasPanel } from '@/components/canvas/CanvasPanel';
import { ChatSidebar } from '@/components/layout/ChatSidebar';
import { TaskNotificationPoller } from '@/components/chat/TaskNotificationPoller';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { VALID_OUTPUT_TYPES } from '@/adapters/chatMessage';
import { api } from '@/services/api';
import { useCanvasStore } from '@/stores/canvasStore';
import type { CanvasContent, CanvasContentDataMap, CanvasContentType } from '@/types/canvas';

const CHAT_SIDEBAR_COLLAPSED_STORAGE_KEY = 'specta-chat-sidebar-collapsed';

function ChatPageContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;
  const isCreatingSessionRef = useRef(false);
  const queryEntityId = searchParams.get('entity_id') || undefined;
  const queryBrand = searchParams.get('brand') || undefined;
  const targetArtifactId = searchParams.get('artifact_id') || undefined;
  const [resolvedEntityId, setResolvedEntityId] = useState<string | undefined>(
    () => queryEntityId
  );
  const [isResolvingSession, setIsResolvingSession] = useState(() => sessionId !== 'new');
  const artifactRestoreAttemptedRef = useRef<string | null>(null);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(() => {
    if (typeof window === 'undefined') {
      return false;
    }
    try {
      return window.localStorage.getItem(CHAT_SIDEBAR_COLLAPSED_STORAGE_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(
        CHAT_SIDEBAR_COLLAPSED_STORAGE_KEY,
        sidebarCollapsed ? '1' : '0'
      );
    } catch {
      // ignore localStorage failures
    }
  }, [sidebarCollapsed]);

  useEffect(() => {
    if (sessionId === 'new') {
      return;
    }

    let cancelled = false;
    const restoreSessionForEntity = async () => {
      if (!queryEntityId) {
        return false;
      }

      const fallback = await api.getOrCreateSessionByEntity(queryEntityId);
      if (cancelled) {
        return true;
      }
      setResolvedEntityId(queryEntityId);
      if (fallback.id !== sessionId) {
        const nextQuery = new URLSearchParams();
        nextQuery.set('entity_id', queryEntityId);
        if (queryBrand) {
          nextQuery.set('brand', queryBrand);
        }
        router.replace(`/chat/${fallback.id}?${nextQuery.toString()}`);
      }
      return true;
    };

    const validateSession = async () => {
      try {
        const session = await api.getSession(sessionId);
        if (cancelled) {
          return;
        }

        const entityId = session.entity_id || undefined;
        setResolvedEntityId(entityId);

        if (queryEntityId && entityId && entityId !== queryEntityId) {
          const restored = await restoreSessionForEntity();
          if (!restored) {
            setResolvedEntityId(queryEntityId);
          }
        }
      } catch {
        if (cancelled) {
          return;
        }
        const restored = await restoreSessionForEntity();
        if (!restored) {
          setResolvedEntityId(undefined);
        }
      } finally {
        if (!cancelled) {
          setIsResolvingSession(false);
        }
      }
    };

    setIsResolvingSession(true);
    void validateSession();

    return () => {
      cancelled = true;
    };
  }, [queryBrand, queryEntityId, router, sessionId]);

  // Handle /chat/new - create a new session and redirect
  useEffect(() => {
    if (sessionId === 'new' && !isCreatingSessionRef.current) {
      const entityId = searchParams.get('entity_id') || undefined;

      // If no entity_id, redirect to dashboard to use brand selection flow
      if (!entityId) {
        router.replace('/dashboard');
        return;
      }

      isCreatingSessionRef.current = true;
      api.getOrCreateSessionByEntity(entityId)
        .then((session) => {
          console.log('[ChatPage] Resolved session:', session.id);
          router.replace(`/chat/${session.id}`);
        })
        .catch((error) => {
          console.error('[ChatPage] Failed to create session:', error);
          isCreatingSessionRef.current = false;
          router.replace('/dashboard');
        });
    }
  }, [sessionId, router, searchParams]);

  useEffect(() => {
    if (!targetArtifactId || sessionId === 'new' || isResolvingSession) {
      return;
    }

    const restoreKey = `${sessionId}:${targetArtifactId}`;
    if (artifactRestoreAttemptedRef.current === restoreKey) {
      return;
    }
    artifactRestoreAttemptedRef.current = restoreKey;

    let cancelled = false;
    const openTargetArtifact = async () => {
      try {
        const outputs = await api.getOutputs(sessionId);
        if (cancelled) {
          return;
        }
        const output = outputs.find(
          (item) => item.artifact_id === targetArtifactId || item.id === targetArtifactId
        );
        if (!output) {
          return;
        }

        const artifactId = output.artifact_id || output.id;
        const rawType = typeof output.type === 'string' ? output.type : 'report';
        const canvasTypeStr = rawType.startsWith('report') ? 'report' : rawType;
        const outputType: CanvasContentType = VALID_OUTPUT_TYPES.includes(canvasTypeStr as CanvasContentType)
          ? (canvasTypeStr as CanvasContentType)
          : 'report';
        const category = typeof output.category === 'string'
          ? output.category as 'baseline' | 'scenario'
          : undefined;
        const content = {
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
        } as CanvasContent;

        const store = useCanvasStore.getState();
        store.upsertContent(content);
        store.openCanvas(content);
      } catch {
        // Ignore deep-link restoration failures and let chat page load normally.
      }
    };

    void openTargetArtifact();

    return () => {
      cancelled = true;
    };
  }, [isResolvingSession, sessionId, targetArtifactId]);

  // Show minimal loading state while creating or restoring session
  if (sessionId === 'new' || isResolvingSession) {
    return (
      <div className="h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="text-center">
          <div
            className="animate-spin rounded-full h-10 w-10 border-2 mx-auto mb-4"
            style={{ borderColor: 'var(--border-subtle)', borderTopColor: 'var(--color-primary)' }}
          />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            {sessionId === 'new' ? '创建新会话...' : '正在恢复会话...'}
          </p>
        </div>
      </div>
    );
  }

  return (
    <ChatLayout
      canvas={<CanvasPanel key={sessionId} />}
      sidebar={(
        <ChatSidebar
          activeSessionId={sessionId}
          activeEntityId={queryEntityId ?? resolvedEntityId}
          collapsed={sidebarCollapsed}
          onToggleCollapsed={() => setSidebarCollapsed((current) => !current)}
        />
      )}
      sidebarCollapsed={sidebarCollapsed}
    >
      <ChatPanel key={sessionId} sessionId={sessionId} />
      <TaskNotificationPoller activeSessionId={sessionId} />
    </ChatLayout>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <RequireAuth>
        <ChatPageContent />
      </RequireAuth>
    </Suspense>
  );
}
