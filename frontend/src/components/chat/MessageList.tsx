'use client';

import type { ReactNode } from 'react';
import { Message as MessageType } from '@/types/message';
import { Message } from './Message';
import { cn } from '@/lib/cn';
import { ExampleBrand, FEATURE_HIGHLIGHTS, FeatureHighlight } from '@/config/brands';
import { ThemedLogo } from '@/components/ui/ThemedLogo';
import {
  RiCompassDiscoverLine,
  RiBookMarkedLine,
  RiSwordLine,
} from '@remixicon/react';

interface MessageListProps {
  messages: MessageType[];
  onConfirmation?: (optionId: string) => void;
  onRetry?: (messageId: string) => void;
  onRecall?: (messageId: string) => void;
  isAgentExecuting?: boolean;
  className?: string;
  exampleBrands?: ExampleBrand[];
  onBrandClick?: (brandName: string) => void;
  onStepContinue?: () => void;
  onStepSkip?: () => void;
  onStepRetry?: () => void;
  renderAfterMessage?: (message: MessageType, index: number) => ReactNode;
  emptyStateOverride?: ReactNode;
}

export function MessageList({
  messages,
  onConfirmation,
  onRetry,
  onRecall,
  isAgentExecuting = false,
  className,
  exampleBrands,
  onBrandClick,
  onStepContinue,
  onStepSkip,
  onStepRetry,
  renderAfterMessage,
  emptyStateOverride,
}: MessageListProps) {
  if (messages.length === 0) {
    if (emptyStateOverride) {
      return <>{emptyStateOverride}</>;
    }
    return (
      <EmptyState
        exampleBrands={exampleBrands}
        onBrandClick={onBrandClick}
      />
    );
  }

  return (
    <div className={cn('space-y-2', className)}>
      {messages.map((message, index) => (
        <Message
          key={message.id}
          message={message}
          isStreaming={isAgentExecuting && index === messages.length - 1 && message.type === 'agent'}
          onConfirmation={onConfirmation}
          onRetry={onRetry}
          onRecall={onRecall}
          recallDisabled={isAgentExecuting}
          messagesAfterCount={messages.slice(index + 1).filter(m => m.type === 'user' || m.type === 'agent').length}
          onStepContinue={onStepContinue}
          onStepSkip={onStepSkip}
          onStepRetry={onStepRetry}
          afterContent={renderAfterMessage?.(message, index)}
        />
      ))}
    </div>
  );
}

interface EmptyStateProps {
  exampleBrands?: ExampleBrand[];
  onBrandClick?: (brandName: string) => void;
}

function FeatureIcon({ feature }: { feature: FeatureHighlight }) {
  const commonProps = {
    size: 20,
    className: 'text-[var(--color-brand-primary)]',
  };

  switch (feature.key) {
    case 'brandMention':
      return <RiCompassDiscoverLine {...commonProps} />;
    case 'contentCitation':
      return <RiBookMarkedLine {...commonProps} />;
    case 'competitionScene':
      return <RiSwordLine {...commonProps} />;
    default:
      return <RiCompassDiscoverLine {...commonProps} />;
  }
}

function EmptyState({ exampleBrands, onBrandClick }: EmptyStateProps) {
  const brands = exampleBrands?.length ? exampleBrands : [];

  const handleBrandClick = (brandName: string) => {
    if (onBrandClick) {
      onBrandClick(brandName);
    } else {
      // Fallback: directly set input value
      const input = document.querySelector('textarea');
      if (input) {
        (input as HTMLTextAreaElement).value = brandName;
        input.dispatchEvent(new Event('input', { bubbles: true }));
        input.focus();
      }
    }
  };

  return (
    <div className="flex flex-col items-center justify-center py-20 px-4">
      <div className="mb-6 flex h-16 w-16 items-center justify-center rounded-[16px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] shadow-[var(--shadow-sm)]">
        <ThemedLogo size={42} />
      </div>

      <h2 className="text-2xl font-semibold text-[var(--text-primary)] mb-2 text-center">
        欢迎使用 Specta AI 智能分析助手
      </h2>

      <p className="text-[var(--text-secondary)] text-center mb-8 max-w-md">
        快速看清品牌在 AI 答案里的位置。
      </p>

      {brands.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {brands.map((brand) => (
            <button
              key={brand.name}
              onClick={() => handleBrandClick(brand.name)}
              className="inline-flex items-center gap-2 rounded-md border border-[var(--border-subtle)] bg-[var(--bg-elevated)] px-4 py-2.5 text-sm text-[var(--text-primary)] transition-colors hover:border-[var(--brand-border)] hover:bg-[var(--bg-tertiary)]"
            >
              <span>{brand.emoji}</span>
              <span>{brand.name}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-12 grid grid-cols-3 gap-8 text-center">
        {FEATURE_HIGHLIGHTS.map((feature) => (
          <div key={feature.title} className="text-[var(--text-tertiary)]">
            <div className="mb-3 flex justify-center">
              <div className="flex h-11 w-11 items-center justify-center rounded-[12px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)]">
                <FeatureIcon feature={feature} />
              </div>
            </div>
            <div className="font-medium text-[var(--text-secondary)]">{feature.title}</div>
            <div className="text-xs">{feature.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
