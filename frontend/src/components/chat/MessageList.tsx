'use client';

import { Message as MessageType } from '@/types/message';
import { Message } from './Message';
import { cn } from '@/lib/cn';
import { ExampleBrand, FEATURE_HIGHLIGHTS } from '@/config/brands';

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
      <div className="w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center mb-6 shadow-lg">
        <span className="text-4xl">🔍</span>
      </div>

      <h2 className="text-2xl font-bold text-[--text-primary] mb-2 text-center">
        欢迎使用 Specta AI 智能分析
      </h2>

      <p className="text-[--text-secondary] text-center mb-8 max-w-md">
        输入品牌名称，AI 将自动分析该品牌在主流 AI 平台的声量表现，并生成优化建议
      </p>

      {brands.length > 0 && (
        <div className="flex flex-wrap justify-center gap-2">
          {brands.map((brand) => (
            <button
              key={brand.name}
              onClick={() => handleBrandClick(brand.name)}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-full border border-[--border-subtle] bg-[--bg-elevated] text-sm text-[--text-primary] hover:border-[#6366F1] hover:bg-[--bg-tertiary] transition-all"
            >
              <span>{brand.emoji}</span>
              <span>{brand.name}</span>
            </button>
          ))}
        </div>
      )}

      <div className="mt-12 grid grid-cols-3 gap-8 text-center">
        {FEATURE_HIGHLIGHTS.map((feature) => (
          <div key={feature.title} className="text-[--text-tertiary]">
            <div className="text-2xl mb-2">{feature.icon}</div>
            <div className="font-medium text-[--text-secondary]">{feature.title}</div>
            <div className="text-xs">{feature.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}
