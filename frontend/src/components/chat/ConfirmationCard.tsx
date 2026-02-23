'use client';

import { useEffect, useCallback } from 'react';
import { RiErrorWarningLine, RiCloseLine } from '@remixicon/react';
import { cn } from '@/lib/cn';
import { MarkdownContent } from './Message/MarkdownContent';

export interface ConfirmationOption {
  id: string;
  label: string;
  description?: string;
  variant?: 'primary' | 'secondary' | 'danger';
}

interface ConfirmationCardProps {
  title?: string;
  message: string;
  options: ConfirmationOption[];
  onConfirm: (optionId: string) => void;
  onCancel?: () => void;
  disabled?: boolean;
  className?: string;
}

export function ConfirmationCard({
  title = '需要您的确认',
  message,
  options,
  onConfirm,
  onCancel,
  disabled = false,
  className,
}: ConfirmationCardProps) {
  // 键盘快捷键支持
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (disabled) return;
    
    if (e.key === 'Enter') {
      // 默认选择第一个主要按钮
      const primaryOption = options.find(o => o.variant === 'primary') || options[0];
      if (primaryOption) {
        onConfirm(primaryOption.id);
      }
    } else if (e.key === 'Escape' && onCancel) {
      onCancel();
    }
  }, [disabled, options, onConfirm, onCancel]);

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  // 自动滚动到底部
  useEffect(() => {
    const element = document.getElementById('confirmation-card');
    if (element) {
      element.scrollIntoView({ behavior: 'smooth', block: 'end' });
    }
  }, []);

  return (
    <div
      id="confirmation-card"
      className={cn(
        'rounded-lg overflow-hidden',
        'bg-[--brand-bg] border border-[--brand-border]',
        className
      )}
    >
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-[--brand-border] flex items-center gap-2">
        <div className="w-6 h-6 rounded-md bg-[--brand-bg] flex items-center justify-center">
          <RiErrorWarningLine className="w-4 h-4 text-[--brand-primary]" />
        </div>
        <span className="text-sm font-medium text-[--text-primary]">{title}</span>
      </div>

      {/* 内容 */}
      <div className="px-4 py-4">
        <MarkdownContent content={message} />

        {/* 按钮组 */}
        <div className="flex flex-wrap gap-3 mt-4">
          {options.map((option) => (
            <button
              key={option.id}
              onClick={() => !disabled && onConfirm(option.id)}
              disabled={disabled}
              className={cn(
                'px-4 py-2 rounded-md text-sm font-medium transition-all duration-150',
                'flex items-center gap-2',
                'disabled:opacity-50 disabled:cursor-not-allowed',
                option.variant === 'primary' && [
                  'bg-[--brand-primary] text-white',
                  'hover:bg-[--brand-hover]',
                  'active:bg-[--brand-active]',
                ],
                option.variant === 'secondary' && [
                  'bg-[--bg-tertiary] text-[--text-primary] border border-[--border-hover]',
                  'hover:bg-[--bg-elevated] hover:border-[--border-hover]',
                ],
                option.variant === 'danger' && [
                  'bg-[--status-error-bg] text-[--error] border border-[--error]',
                  'hover:opacity-80',
                ],
                !option.variant && [
                  'bg-[--bg-tertiary] text-[--text-primary] border border-[--border-hover]',
                  'hover:bg-[--bg-elevated]',
                ]
              )}
            >
              {option.label}
            </button>
          ))}

          {onCancel && (
            <button
              onClick={() => !disabled && onCancel()}
              disabled={disabled}
              className={cn(
                'px-4 py-2 rounded-md text-sm font-medium transition-all duration-150',
                'flex items-center gap-2',
                'text-[--text-tertiary] hover:text-[--text-secondary]',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              <RiCloseLine className="w-4 h-4" />
              取消
            </button>
          )}
        </div>
      </div>

      {/* 快捷键提示 */}
      <div className="px-4 py-2 bg-[--bg-primary] border-t border-[--brand-border]">
        <div className="flex items-center gap-4 text-xs text-[--text-disabled]">
          <span className="flex items-center gap-1">
            <kbd className="px-1.5 py-0.5 bg-[--bg-tertiary] rounded text-[--text-tertiary]">Enter</kbd>
            确认
          </span>
          {onCancel && (
            <span className="flex items-center gap-1">
              <kbd className="px-1.5 py-0.5 bg-[--bg-tertiary] rounded text-[--text-tertiary]">Esc</kbd>
              取消
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

// 简化版确认按钮（用于嵌入其他组件）
interface ConfirmButtonsProps {
  options: ConfirmationOption[];
  onConfirm: (optionId: string) => void;
  disabled?: boolean;
  className?: string;
}

export function ConfirmButtons({
  options,
  onConfirm,
  disabled = false,
  className,
}: ConfirmButtonsProps) {
  return (
    <div className={cn('flex flex-wrap gap-2', className)}>
      {options.map((option) => (
        <button
          key={option.id}
          onClick={() => !disabled && onConfirm(option.id)}
          disabled={disabled}
          className={cn(
            'px-3 py-1.5 rounded text-xs font-medium transition-all duration-150',
            'disabled:opacity-50 disabled:cursor-not-allowed',
            option.variant === 'primary' && [
              'bg-[--brand-primary] text-white',
              'hover:bg-[--brand-hover]',
            ],
            option.variant === 'secondary' && [
              'bg-[--bg-tertiary] text-[--text-primary] border border-[--border-hover]',
              'hover:bg-[--bg-elevated]',
            ],
            !option.variant && [
              'bg-[--bg-tertiary] text-[--text-primary] border border-[--border-hover]',
              'hover:bg-[--bg-elevated]',
            ]
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export default ConfirmationCard;
