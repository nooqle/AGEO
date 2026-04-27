'use client';

import { useState } from 'react';
import { RiArrowGoBackLine } from '@remixicon/react';
import { Message } from '@/types/message';
import { formatTime } from '@/lib/utils';
import { RecallConfirmation } from './RecallConfirmation';
import { AttachmentList } from './AttachmentList';

interface UserMessageProps {
  message: Message;
  onRecall?: () => void;
  recallDisabled?: boolean;
  messagesAfterCount?: number;
}

export function UserMessage({ message, onRecall, recallDisabled, messagesAfterCount = 0 }: UserMessageProps) {
  const [showConfirm, setShowConfirm] = useState(false);
  const hasContent = Boolean(message.content?.trim());

  const handleRecallClick = () => {
    if (recallDisabled) return;
    setShowConfirm(true);
  };

  const handleConfirm = () => {
    setShowConfirm(false);
    onRecall?.();
  };

  return (
    <div className="max-w-[85%] md:max-w-[70%]">
      <div className="flex items-center gap-1.5 justify-end">
        {/* Recall button — hover visible via parent group */}
        {onRecall && (
          <button
            onClick={handleRecallClick}
            disabled={recallDisabled}
            className="p-1.5 rounded-lg transition-all cursor-pointer opacity-0 group-hover:opacity-100"
            style={{
              color: 'var(--text-muted)',
              opacity: recallDisabled ? 0.3 : undefined,
              cursor: recallDisabled ? 'not-allowed' : 'pointer',
            }}
            title={recallDisabled ? '请先停止当前任务' : '回退到此消息'}
            onMouseEnter={(e) => {
              if (!recallDisabled) {
                e.currentTarget.style.background = 'var(--bg-elevated)';
                e.currentTarget.style.color = 'var(--text-secondary)';
              }
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-muted)';
            }}
          >
            <RiArrowGoBackLine className="w-4 h-4" />
          </button>
        )}

        {/* Message bubble */}
        <div className="flex flex-col items-end gap-2">
          {hasContent && (
            <div className="rounded-[14px] rounded-tr-sm border bg-[var(--surface-command)] px-4 py-3 text-[var(--text-primary)] shadow-[var(--shadow-sm)]" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="whitespace-pre-wrap break-words">
                {message.content}
              </div>
            </div>
          )}
          {message.attachments && message.attachments.length > 0 && (
            <AttachmentList attachments={message.attachments} />
          )}
          {!hasContent && (!message.attachments || message.attachments.length === 0) && (
            <div className="rounded-[14px] rounded-tr-sm border bg-[var(--surface-command)] px-4 py-3 text-[var(--text-primary)] shadow-[var(--shadow-sm)]" style={{ borderColor: 'var(--border-subtle)' }}>
              <div className="whitespace-pre-wrap break-words">
                {message.content}
              </div>
            </div>
          )}
        </div>
      </div>

      <div className="text-xs text-[var(--text-tertiary)] mt-1 text-right">
        {formatTime(message.timestamp)}
      </div>

      {/* Inline recall confirmation card */}
      {showConfirm && (
        <RecallConfirmation
          messageCount={messagesAfterCount}
          onConfirm={handleConfirm}
          onCancel={() => setShowConfirm(false)}
        />
      )}
    </div>
  );
}
