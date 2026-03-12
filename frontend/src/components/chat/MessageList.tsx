'use client';

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
}: MessageListProps) {
  if (messages.length === 0) {
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
      <div className="mb-6 flex h-20 w-20 items-center justify-center rounded-[28px] border border-[var(--border-subtle)] bg-[var(--bg-elevated)] shadow-[0_20px_50px_rgba(99,102,241,0.12)]">
        <ThemedLogo size={42} />
      </div>

      <h2 className="text-2xl font-bold text-[var(--text-primary)] mb-2 text-center">
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
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full border border-[var(--border-subtle)] bg-[var(--bg-elevated)] text-sm text-[var(--text-primary)] hover:border-[#6366F1] hover:bg-[var(--bg-tertiary)] transition-all"
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
              <div className="flex h-12 w-12 items-center justify-center rounded-2xl border border-[var(--border-subtle)] bg-[var(--bg-elevated)] shadow-[0_10px_24px_rgba(99,102,241,0.08)]">
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
