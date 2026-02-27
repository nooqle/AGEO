'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { RiTimeLine, RiCheckboxCircleLine, RiMessage3Line, RiErrorWarningLine } from '@remixicon/react';
import { ConfirmationRequest } from '@/types/message';
import { cn } from '@/lib/cn';
import { MarkdownContent } from './MarkdownContent';

interface ConfirmationBlockProps {
  request: ConfirmationRequest;
  onSelect?: (optionId: string) => void;
  className?: string;
}

export function ConfirmationBlock({ request, onSelect, className }: ConfirmationBlockProps) {
  const [selectedOption, setSelectedOption] = useState<string | null>(null);

  const handleSelect = (optionId: string) => {
    setSelectedOption(optionId);
    onSelect?.(optionId);
  };

  // 根据确认类型显示不同的图标和颜色
  const getTypeConfig = () => {
    switch (request.type) {
      case 'step_confirmation':
        return {
          icon: <RiErrorWarningLine className="w-4 h-4" />,
          label: '步骤确认',
          color: 'border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
          iconBg: 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)]',
          iconColor: 'text-indigo-300',
          titleColor: 'text-[var(--text-primary)]',
          labelColor: 'text-indigo-300',
        };
      case 'brand_info':
        return {
          icon: <RiMessage3Line className="w-4 h-4" />,
          label: '品牌信息确认',
          color: 'border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
          iconBg: 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)]',
          iconColor: 'text-amber-300',
          titleColor: 'text-[var(--text-primary)]',
          labelColor: 'text-amber-300',
        };
      case 'action_choice':
        return {
          icon: <RiTimeLine className="w-4 h-4" />,
          label: '操作选择',
          color: 'border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
          iconBg: 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)]',
          iconColor: 'text-purple-300',
          titleColor: 'text-[var(--text-primary)]',
          labelColor: 'text-purple-300',
        };
      default:
        return {
          icon: <RiTimeLine className="w-4 h-4" />,
          label: '等待确认',
          color: 'border-[var(--border-subtle)] bg-[var(--bg-elevated)]',
          iconBg: 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)]',
          iconColor: 'text-amber-300',
          titleColor: 'text-[var(--text-primary)]',
          labelColor: 'text-amber-300',
        };
    }
  };

  const config = getTypeConfig();

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn('rounded-xl border p-4 shadow-sm', config.color, className)}
    >
      {/* 标题 */}
      <div className="flex items-center gap-2 mb-3">
        <div className={cn('p-1.5 rounded-full', config.iconBg)}>
          <span className={config.iconColor}>{config.icon}</span>
        </div>
        <div className="flex-1">
          <span className={cn('text-sm font-medium', config.titleColor)}>
            {config.label}
          </span>
          {request.stepName && (
            <span className="text-xs text-[var(--text-tertiary)] ml-2">
              · {request.stepName}
            </span>
          )}
        </div>
      </div>

      {/* 消息 */}
      <div className="bg-[var(--bg-elevated)] border border-[var(--border-subtle)] rounded-lg p-4 mb-4 max-h-80 overflow-y-auto">
        <MarkdownContent content={request.message} />
      </div>

      {/* 选项按钮 */}
      <div className="flex flex-wrap gap-2">
        {request.options.map((option) => (
          <button
            key={option.id}
            onClick={() => handleSelect(option.id)}
            disabled={selectedOption !== null}
            className={cn(
              'inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm font-medium transition-all',
              option.recommended
                ? 'bg-indigo-600 text-white hover:bg-indigo-500 shadow-sm'
                : 'bg-[var(--bg-elevated)] border border-[var(--border-subtle)] text-[var(--text-primary)] hover:bg-[var(--bg-tertiary)] hover:border-[var(--border-hover)]',
              selectedOption === option.id && 'ring-2 ring-indigo-500 ring-offset-0',
              selectedOption !== null && selectedOption !== option.id && 'opacity-50'
            )}
          >
            {option.icon && <span>{option.icon}</span>}
            {option.label}
            {option.recommended && (
              <span className="inline-flex items-center gap-1 text-xs bg-white/10 px-1.5 py-0.5 rounded">
                <RiCheckboxCircleLine className="w-3 h-3" />
                推荐
              </span>
            )}
          </button>
        ))}
      </div>

      {/* 提示 */}
      {request.allowTextInput && (
        <p className="text-xs text-[var(--text-tertiary)] mt-3 flex items-center gap-1">
          <span>💡</span>
          您也可以在输入框中直接输入回复
        </p>
      )}
    </motion.div>
  );
}
