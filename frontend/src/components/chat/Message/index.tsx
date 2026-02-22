'use client';

import { Message as MessageType } from '@/types/message';
import { UserMessage } from './UserMessage';
import { AgentMessage } from './AgentMessage';
import { SystemMessage } from './SystemMessage';
import { ExecutionStepMessage } from './ExecutionStepMessage';
import { DegradationNotice } from './DegradationNotice';
import { MessageActions } from '../MessageActions';
import { cn } from '@/lib/cn';

interface MessageProps {
  message: MessageType;
  isStreaming?: boolean;
  onConfirmation?: (optionId: string) => void;
  onRetry?: (messageId: string) => void;
  onStepContinue?: () => void;
  onStepSkip?: () => void;
  onStepRetry?: () => void;
}

const ACTIONABLE_TYPES = new Set(['user', 'agent']);

export function Message({ message, isStreaming, onConfirmation, onRetry, onStepContinue, onStepSkip, onStepRetry }: MessageProps) {
  const showActionMenu = ACTIONABLE_TYPES.has(message.type) && !isStreaming;

  const renderMessage = () => {
    switch (message.type) {
      case 'user':
        return <UserMessage message={message} />;
      case 'agent':
        return (
          <AgentMessage
            message={message}
            onConfirmation={onConfirmation}
            isStreaming={isStreaming}
          />
        );
      case 'system':
        return <SystemMessage message={message} />;
      case 'execution_step':
        return message.executionStep ? (
          <ExecutionStepMessage
            step={message.executionStep}
            onContinue={onStepContinue}
            onSkip={onStepSkip}
            onRetry={onStepRetry}
          />
        ) : null;
      case 'system_notice':
        return message.systemNotice ? (
          <DegradationNotice notice={message.systemNotice} />
        ) : null;
      default:
        return null;
    }
  };

  return (
    <div
      data-message-id={message.id}
      className={cn(
        'group relative',
        message.type === 'user' ? 'flex justify-end' : ''
      )}
    >
      {renderMessage()}

      {/* 操作菜单 — 纯 CSS group-hover 控制可见性 */}
      {showActionMenu && (
        <MessageActions
          message={message}
          onRetry={message.type === 'agent' && onRetry ? () => onRetry(message.id) : undefined}
          className={cn(
            'absolute top-1 z-10',
            message.type === 'user' ? 'left-2' : 'right-2'
          )}
        />
      )}
    </div>
  );
}
