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

  // Auto-scroll to bottom during streaming
  useEffect(() => {
    if (isStreaming && messageEndRef.current) {
      messageEndRef.current.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, [message.content, isStreaming]);

  if (!hasVisibleContent) return null;

  return (
    <motion.div
      className="flex gap-3 max-w-full"
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Agent avatar */}
      <div className="flex-shrink-0">
        <motion.div
          className="w-7 h-7 rounded-lg bg-gradient-to-br from-[#6366F1] to-[#8B5CF6] flex items-center justify-center shadow-md"
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        >
          <RiSparklingLine className="w-3.5 h-3.5 text-white" />
        </motion.div>
      </div>

      {/* Message content */}
      <div className="flex-1 min-w-0 space-y-3 pt-0.5">
        {/* Timestamp */}
        <div className="text-[10px] text-[var(--text-tertiary)] leading-none">
          {formatTime(message.timestamp)}
        </div>

        {/* Layer 2: Plan — lightweight row, no box */}
        {layers?.planText && (
          <PlanCard
            planText={layers.planText}
            isActive={isStreaming}
          />
        )}

        {/* Layer 3: Action Log — lightweight rows, no box */}
        {layers?.actionLogs && layers.actionLogs.length > 0 && (
          <ActionLog
            logs={layers.actionLogs}
            isExpanded={isStreaming}
          />
        )}

        {/* Layer 1: Main reply content — most prominent, no container */}
        {mainContent && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.2 }}
          >
            <MarkdownContent content={mainContent} className="break-words" />
          </motion.div>
        )}

        {/* Output cards */}
        {message.outputCards && message.outputCards.length > 0 && (
          <motion.div
            className="space-y-2"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
          >
            {message.outputCards.map((card, index) => (
              <motion.div
                key={card.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + index * 0.06, type: 'spring', stiffness: 320, damping: 28 }}
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

        {/* Layer 4: Inline confirmation */}
        {message.inlineConfirmation && onConfirmation && (
          <motion.div
            className="space-y-3"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            {message.inlineConfirmation.type === 'guided' ? (
              /* Guided options keep a light container for structure */
              <div className="rounded-xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] p-4">
                <GuidedOptions
                  message={message.inlineConfirmation.message}
                  options={message.inlineConfirmation.options}
                  onSelect={onConfirmation}
                  selectedId={message.inlineConfirmation.selectedOptionId}
                />
              </div>
            ) : (
              /* Simple confirmation — no heavy box, just buttons */
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {message.inlineConfirmation.options.map((option, i) => (
                    <button
                      key={option.id}
                      onClick={() => onConfirmation(option.id)}
                      disabled={!!message.inlineConfirmation?.selectedOptionId}
                      className={cn(
                        'px-4 py-1.5 rounded-full text-sm font-medium transition-all border',
                        // Only highlight explicitly recommended options
                        option.recommended && !message.inlineConfirmation?.selectedOptionId
                          ? 'bg-indigo-600 border-indigo-600 text-white hover:bg-indigo-500 shadow-sm'
                          : 'bg-transparent border-[var(--border-hover)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
                        message.inlineConfirmation?.selectedOptionId === option.id && 'ring-2 ring-indigo-500 ring-offset-1 ring-offset-[var(--bg-primary)]',
                        message.inlineConfirmation?.selectedOptionId && message.inlineConfirmation.selectedOptionId !== option.id && 'opacity-40 cursor-not-allowed'
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {!message.inlineConfirmation.selectedOptionId && (
                  <p className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse inline-block" />
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
            initial={{ opacity: 0, y: 8 }}
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

        {/* Thought process — collapsible, very subtle */}
        {hasThought && (
          <div className="space-y-1.5">
            <button
              onClick={() => setShowThought(!showThought)}
              className={cn(
                'flex items-center gap-1.5 text-[11px] transition-colors cursor-pointer',
                'text-[var(--text-tertiary)] hover:text-[var(--text-secondary)]'
              )}
            >
              <RiBrainLine className="w-3 h-3" />
              <span>{isThinking ? '思考中...' : '查看思考过程'}</span>
              <motion.div
                animate={{ rotate: showThought ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <RiArrowDownSLine className="w-3 h-3" />
              </motion.div>
            </button>

            <AnimatePresence>
              {showThought && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: 'auto' }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.25 }}
                  className="overflow-hidden"
                >
                  <div className="ml-4 pl-3 border-l-2 border-[var(--border-subtle)]">
                    <p className="text-[11px] text-[var(--text-tertiary)] whitespace-pre-wrap leading-relaxed">
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
