'use client';

import { AlertCircle, CheckCircle2, Loader2, MessageCircle } from 'lucide-react';

import { cn } from '@/lib/utils';
import type { BrandIntelligenceRun } from '@/types/intelligenceRun';
import { isActiveBrandIntelligenceRun } from '@/types/intelligenceRun';

interface BrandIntelligenceChatBubbleProps {
  run?: BrandIntelligenceRun | null;
  isOpening?: boolean;
  onOpenChat: () => void;
}

function bubbleLabel(run?: BrandIntelligenceRun | null, isOpening?: boolean): string {
  if (isOpening) return '打开中';
  if (!run) return '进入对话';
  if (run.status === 'not_started') return '进入对话';
  if (run.requires_user_action || run.status === 'waiting_user') return '需要确认';
  if (run.status === 'failed') return '处理失败';
  if (isActiveBrandIntelligenceRun(run)) return '分析中';
  return '解释情报';
}

function bubbleCaption(run?: BrandIntelligenceRun | null, isOpening?: boolean): string {
  if (isOpening) return '正在进入对话';
  if (!run || run.status === 'not_started') return '带当前品牌';
  if (run.requires_user_action || run.status === 'waiting_user') return '等待确认';
  if (run.status === 'failed') return '查看原因';
  if (isActiveBrandIntelligenceRun(run)) return '正在生成';
  return '带当前结论';
}

function BubbleIcon({ run, isOpening }: { run?: BrandIntelligenceRun | null; isOpening?: boolean }) {
  if (isOpening) {
    return <Loader2 className="h-5 w-5 animate-spin" />;
  }
  if (run?.requires_user_action || run?.status === 'waiting_user' || run?.status === 'failed') {
    return <AlertCircle className="h-5 w-5" />;
  }
  if (run?.status === 'completed') {
    return <CheckCircle2 className="h-5 w-5" />;
  }
  if (run?.status !== 'not_started' && isActiveBrandIntelligenceRun(run)) {
    return <Loader2 className="h-5 w-5 animate-spin" />;
  }
  return <MessageCircle className="h-5 w-5" />;
}

export function BrandIntelligenceChatBubble({
  run,
  isOpening,
  onOpenChat,
}: BrandIntelligenceChatBubbleProps) {
  const needsAttention = Boolean(
    run?.requires_user_action || run?.status === 'waiting_user' || run?.status === 'failed',
  );
  const isRunning = Boolean(run && run.status !== 'not_started' && isActiveBrandIntelligenceRun(run));

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-5 z-40 flex justify-center px-4 md:bottom-7">
      <button
        type="button"
        data-testid="brand-intelligence-chat-bubble"
        disabled={isOpening}
        aria-busy={isOpening || undefined}
        onClick={onOpenChat}
        className={cn(
          'group pointer-events-auto relative inline-flex min-h-14 items-center gap-3 overflow-hidden rounded-[18px] border px-3 py-2 pr-4 text-left text-[var(--text-primary)] shadow-[0_14px_34px_rgba(34,31,25,0.14)] transition-all duration-200 hover:-translate-y-0.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--brand-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-primary)]',
          'border-[color-mix(in_srgb,var(--brand-primary)_24%,var(--border-subtle)_76%)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--bg-elevated)_96%,#eef4f0_4%),var(--bg-elevated))]',
          isOpening && 'cursor-progress hover:translate-y-0',
          needsAttention &&
            'border-[color-mix(in_srgb,var(--status-warning)_46%,var(--border-subtle)_54%)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--bg-elevated)_92%,var(--status-warning-bg)_8%),var(--bg-elevated))]',
        )}
        aria-label="打开品牌情报对话"
      >
        <span
          aria-hidden="true"
          className="absolute inset-x-6 top-0 h-px bg-[linear-gradient(90deg,transparent,color-mix(in_srgb,var(--brand-primary)_44%,transparent),transparent)]"
        />
        <span
          className={cn(
            'relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-[14px] border text-[var(--brand-primary)] transition-colors group-hover:border-[color-mix(in_srgb,var(--brand-primary)_44%,var(--border-subtle)_56%)]',
            'border-[color-mix(in_srgb,var(--brand-primary)_18%,var(--border-subtle)_82%)] bg-[color-mix(in_srgb,var(--brand-primary)_9%,var(--bg-secondary)_91%)]',
            needsAttention &&
              'border-[color-mix(in_srgb,var(--status-warning)_42%,var(--border-subtle)_58%)] bg-[var(--status-warning-bg)] text-[var(--status-warning)]',
          )}
        >
          <BubbleIcon run={run} isOpening={isOpening} />
          {needsAttention || isRunning || isOpening ? (
            <span
              className={cn(
                'absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border border-[var(--bg-elevated)]',
                needsAttention && !isOpening ? 'bg-[var(--status-warning)]' : 'bg-[var(--brand-primary)]',
                (isRunning || isOpening) && 'motion-safe:animate-pulse',
              )}
            />
          ) : null}
        </span>
        <span className="flex min-w-0 flex-col leading-tight">
          <span className="whitespace-nowrap text-[14px] font-semibold">{bubbleLabel(run, isOpening)}</span>
          <span className="mt-0.5 whitespace-nowrap text-[11px] font-medium text-[var(--text-tertiary)]">
            {bubbleCaption(run, isOpening)}
          </span>
        </span>
      </button>
    </div>
  );
}
