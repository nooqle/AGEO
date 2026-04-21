'use client';

import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef, useState } from 'react';
import { ChatLayout } from '@/components/layout/ChatLayout';
import { ChatPanel } from '@/components/chat';
import { CanvasPanel } from '@/components/canvas/CanvasPanel';
import { ChatSidebar } from '@/components/layout/ChatSidebar';
import { TaskNotificationPoller } from '@/components/chat/TaskNotificationPoller';
import { RequireAuth } from '@/components/auth/RequireAuth';
import { api } from '@/services/api';

const CHAT_SIDEBAR_COLLAPSED_STORAGE_KEY = 'specta-chat-sidebar-collapsed';

function ChatPageContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;
  const isCreatingSessionRef = useRef(false);
  const queryEntityId = searchParams.get('entity_id') || undefined;
  const queryBrand = searchParams.get('brand') || undefined;
  const queryArtifactId = searchParams.get('artifact_id') || undefined;
  const queryOutputId = searchParams.get('output_id') || undefined;
  const queryDraft = searchParams.get('draft') || undefined;
  const queryAutoSend = searchParams.get('autosend') || undefined;
  const [resolvedEntityId, setResolvedEntityId] = useState<string | undefined>(
    () => queryEntityId
  );
  const [isResolvingSession, setIsResolvingSession] = useState(() => sessionId !== 'new');
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
        if (queryArtifactId) {
          nextQuery.set('artifact_id', queryArtifactId);
        }
        if (queryOutputId) {
          nextQuery.set('output_id', queryOutputId);
        }
        if (queryDraft) {
          nextQuery.set('draft', queryDraft);
        }
        if (queryAutoSend) {
          nextQuery.set('autosend', queryAutoSend);
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
  }, [queryArtifactId, queryAutoSend, queryBrand, queryDraft, queryEntityId, queryOutputId, router, sessionId]);

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
