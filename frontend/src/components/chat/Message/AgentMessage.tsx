'use client';

import { motion, useReducedMotion } from 'framer-motion';
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
import { RiLoader4Line } from '@remixicon/react';

interface AgentMessageProps {
  message: Message;
  onConfirmation?: (optionId: string) => void;
  isStreaming?: boolean;
}

export function AgentMessage({ message, onConfirmation, isStreaming = false }: AgentMessageProps) {
  const mainContent = message.content || '';
  const layers = message.layers;
  const hasThought = Boolean(layers?.thought);
  const isThinking = isStreaming && hasThought;
  const prefersReducedMotion = useReducedMotion();

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
          className="flex h-7 w-7 items-center justify-center rounded-md border bg-[var(--bg-elevated)] text-[11px] font-semibold tracking-[0.08em] text-[var(--brand-text)] shadow-[var(--shadow-sm)]"
          style={{ borderColor: 'var(--border-subtle)' }}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
        >
          S
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
        {message.inlineConfirmation && onConfirmation && message.inlineConfirmation.options.length > 0 && (
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
                  {message.inlineConfirmation.options.map((option) => (
                    <button
                      key={option.id}
                      onClick={() => onConfirmation(option.id)}
                      disabled={!!message.inlineConfirmation?.selectedOptionId}
                      className={cn(
                        'px-4 py-1.5 rounded-full text-sm font-medium transition-all border',
                        // Only highlight explicitly recommended options
                        option.recommended && !message.inlineConfirmation?.selectedOptionId
                          ? 'bg-[var(--brand-primary)] border-[var(--brand-primary)] text-[var(--brand-contrast)] hover:bg-[var(--brand-hover)] shadow-sm'
                          : 'bg-transparent border-[var(--border-hover)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)]',
                        message.inlineConfirmation?.selectedOptionId === option.id && 'ring-2 ring-[var(--brand-primary)] ring-offset-1 ring-offset-[var(--bg-primary)]',
                        message.inlineConfirmation?.selectedOptionId && message.inlineConfirmation.selectedOptionId !== option.id && 'opacity-40 cursor-not-allowed'
                      )}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
                {!message.inlineConfirmation.selectedOptionId && (
                  <p className="text-[11px] text-[var(--text-tertiary)] flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--warning)] animate-pulse inline-block" />
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

        {/* Thought state — user-facing UI only shows a minimal thinking marker */}
        {isThinking && (
          <motion.div
            className="inline-flex w-fit items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-2.5 py-1 text-[11px] text-[var(--text-tertiary)]"
            animate={prefersReducedMotion ? undefined : { opacity: [0.78, 1, 0.82] }}
            transition={prefersReducedMotion ? undefined : { duration: 1.6, repeat: Infinity, ease: [0.25, 1, 0.5, 1] }}
          >
            <motion.div
              animate={prefersReducedMotion ? undefined : { rotate: 360 }}
              transition={prefersReducedMotion ? undefined : { duration: 1.2, repeat: Infinity, ease: 'linear' }}
            >
              <RiLoader4Line className="h-3 w-3 text-[var(--brand-text)]" />
            </motion.div>

            <span className="text-[var(--text-secondary)]">分析中</span>
          </motion.div>
        )}

      </div>
    </motion.div>
  );
}

export default AgentMessage;
