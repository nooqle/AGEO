'use client';

import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useRef } from 'react';
import { ChatLayout } from '@/components/layout/ChatLayout';
import { ChatPanel } from '@/components/chat';
import { CanvasPanel } from '@/components/canvas/CanvasPanel';
import { ChatSidebar } from '@/components/layout/ChatSidebar';
import { TaskNotificationPoller } from '@/components/chat/TaskNotificationPoller';
import { api } from '@/services/api';

function ChatPageContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;
  const isCreatingSessionRef = useRef(false);

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
      api.createSession(entityId)
        .then((session) => {
          console.log('[ChatPage] Created new session:', session.id);
          router.replace(`/chat/${session.id}`);
        })
        .catch((error) => {
          console.error('[ChatPage] Failed to create session:', error);
          isCreatingSessionRef.current = false;
        });
    }
  }, [sessionId, router, searchParams]);

  // Show minimal loading state while creating session
  if (sessionId === 'new') {
    return (
      <div className="h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div className="text-center">
          <div
            className="animate-spin rounded-full h-10 w-10 border-2 mx-auto mb-4"
            style={{ borderColor: 'var(--border-default)', borderTopColor: 'var(--color-primary)' }}
          />
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>创建新会话...</p>
        </div>
      </div>
    );
  }

  return (
    <ChatLayout
      canvas={<CanvasPanel key={sessionId} />}
      sidebar={<ChatSidebar activeSessionId={sessionId} />}
    >
      <ChatPanel key={sessionId} sessionId={sessionId} />
      <TaskNotificationPoller activeSessionId={sessionId} />
    </ChatLayout>
  );
}

export default function ChatPage() {
  return (
    <Suspense>
      <ChatPageContent />
    </Suspense>
  );
}
