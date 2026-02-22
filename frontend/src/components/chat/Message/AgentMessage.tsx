'use client';

import { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Message } from '@/types/message';
import { PlanCard } from './PlanCard';
import { ActionLog } from './ActionLog';
import { ConfirmationCard } from '../ConfirmationCard';
import { OutputCard } from './OutputCard';
import { MarkdownContent } from './MarkdownContent';
import { GuidedOptions } from './GuidedOptions';
import { WaitingPanel } from './WaitingPanel';
import { CompletionChecklist } from './CompletionChecklist';
import { AttachmentList } from './AttachmentList';
import { formatTime } from '@/lib/utils';
import { cn } from '@/lib/cn';
import { RiSparklingLine, RiArrowDownSLine, RiBrainLine } from '@remixicon/react';

interface AgentMessageProps {
  message: Message;
  onConfirmation?: (optionId: string) => void;
  isStreaming?: boolean;
}

export function AgentMessage({ message, onConfirmation, isStreaming = false }: AgentMessageProps) {
  const messageEndRef = useRef<HTMLDivElement>(null);
  const [showThought, setShowThought] = useState(false);

  const mainContent = message.content || '';
  const layers = message.layers;
  const hasThought = Boolean(layers?.thought);
  const isThinking = isStreaming && hasThought;

  // Don't render empty messages (only thought, no content/plan/action/confirmation/output)
  const hasVisibleContent = mainContent
    || layers?.planText
    || (layers?.actionLogs && layers.actionLogs.length > 0)
    || message.inlineConfirmation
    || message.confirmationRequest
    || (message.outputCards && message.outputCards.length > 0)
    || (message.attachments && message.attachments.length > 0)
    || isStreaming;
  if (!hasVisibleContent) return null;

  // Auto-scroll to bottom during streaming
  useEffect(() => {
    if (isStreaming && messageEndRef.current) {
      messageEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [message.content, isStreaming]);

  return (
    <motion.div
      className="flex gap-4 max-w-full"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Agent avatar */}
      <div className="flex-shrink-0">
        <motion.div
          className="w-8 h-8 rounded-xl bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] flex items-center justify-center shadow-lg"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        >
          <RiSparklingLine className="w-4 h-4 text-white" />
        </motion.div>
      </div>

      {/* Message content - 4 layer architecture */}
      <div className="flex-1 min-w-0 space-y-4">
        {/* Timestamp */}
        <div className="text-xs text-[--text-tertiary]">
          {formatTime(message.timestamp)}
        </div>

        {/* Layer 2: Plan Card */}
        {layers?.planText && (
          <PlanCard
            planText={layers.planText}
            isActive={isStreaming}
          />
        )}

        {/* Layer 3: Action Log */}
        {layers?.actionLogs && layers.actionLogs.length > 0 && (
          <ActionLog
            logs={layers.actionLogs}
            isExpanded={isStreaming}
          />
        )}

        {/* Layer 1: Main reply content */}
        {mainContent && (
          <motion.div
            className="px-1 py-0"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <MarkdownContent content={mainContent} className="break-words" />
          </motion.div>
        )}

        {/* Output cards */}
        {message.outputCards && message.outputCards.length > 0 && (
          <motion.div
            className="space-y-3"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            {message.outputCards.map((card, index) => (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.15 + index * 0.08, type: 'spring', stiffness: 320, damping: 28 }}
              >
                <OutputCard card={card} />
              </motion.div>
            ))}
          </motion.div>
        )}

        {/* Attachments */}
        {message.attachments && message.attachments.length > 0 && (
          <AttachmentList attachments={message.attachments} />
        )}

        {/* Layer 4: Inline confirmation (guided or simple) */}
        {message.inlineConfirmation && onConfirmation && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            {message.inlineConfirmation.type === 'guided' ? (
              <div className="rounded-xl border border-[--border-default] bg-[--bg-secondary] p-4">
                <GuidedOptions
                  message={message.inlineConfirmation.message}
                  options={message.inlineConfirmation.options}
                  onSelect={onConfirmation}
                  selectedId={message.inlineConfirmation.selectedOptionId}
                />
              </div>
            ) : (
              <div className="rounded-xl border border-[--border-default] bg-[--bg-secondary] p-4">
                <p className="text-sm text-[--text-primary] mb-3">{message.inlineConfirmation.message}</p>
                <div className="flex flex-wrap gap-2">
                  {message.inlineConfirmation.options.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => onConfirmation(option.id)}
                      disabled={!!message.inlineConfirmation?.selectedOptionId}
                      className={cn(
                        'px-4 py-2 rounded-xl text-sm font-medium transition-all',
                        'bg-[--bg-secondary] border border-[--border-default] text-[--text-primary] hover:bg-[--bg-tertiary] hover:border-[--border-hover]',
                        message.inlineConfirmation?.selectedOptionId === option.id && 'ring-2 ring-indigo-500',
                        message.inlineConfirmation?.selectedOptionId && message.inlineConfirmation.selectedOptionId !== option.id && 'opacity-50'
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {!message.inlineConfirmation.selectedOptionId && (
                  <p className="text-xs text-[--text-tertiary] mt-3">
                    Specta AI 将在你回复后继续工作
                  </p>
                )}
              </div>
            )}

            {/* Waiting tips */}
            {message.inlineConfirmation.waitingTips && message.inlineConfirmation.selectedOptionId && (
              <WaitingPanel
                tips={message.inlineConfirmation.waitingTips}
                estimatedTime={message.inlineConfirmation.estimatedTime}
              />
            )}

            {/* Completion checklist */}
            {message.inlineConfirmation.checklist && (
              <CompletionChecklist items={message.inlineConfirmation.checklist} />
            )}
          </motion.div>
        )}

        {/* Legacy confirmation request (backward compat) */}
        {message.confirmationRequest && onConfirmation && !message.inlineConfirmation && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <ConfirmationCard
              title="需要您的确认"
              message={message.confirmationRequest.message}
              options={message.confirmationRequest.options.map(opt => ({
                id: opt.id,
                label: opt.label,
                description: opt.description,
                variant: opt.recommended ? 'primary' : 'secondary',
              }))}
              onConfirm={onConfirmation}
            />
          </motion.div>
        )}

        {/* Thought process - collapsible */}
        {hasThought && (
          <div className="space-y-2">
            <button
              onClick={() => setShowThought(!showThought)}
              className={cn(
                'flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs transition-all',
                'bg-[--bg-secondary] border border-[--border-default] hover:bg-[--bg-tertiary] hover:border-[--border-hover] text-[--text-secondary] hover:text-[--text-primary]'
              )}
            >
              <RiBrainLine className="w-3.5 h-3.5" />
              <span>{isThinking ? '思考中...' : '思考过程'}</span>
              <motion.div
                animate={{ rotate: showThought ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <RiArrowDownSLine className="w-3.5 h-3.5" />
              </motion.div>
            </button>

            <AnimatePresence>
              {showThought && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.3 }}
                  className="overflow-hidden"
                >
                  <div className="rounded-lg border border-[--border-default] bg-[--bg-primary] px-3 py-2">
                    <p className="text-xs text-[--text-tertiary] whitespace-pre-wrap leading-relaxed">
                      {layers?.thought}
                    </p>
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </div>
        )}

        <div ref={messageEndRef} />
      </div>
    </motion.div>
  );
}

export default AgentMessage;
