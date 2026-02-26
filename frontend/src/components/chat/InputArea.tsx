'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { RiSendPlaneLine, RiStopLine, RiAttachmentLine, RiLoader4Line, RiCloseLine } from '@remixicon/react';
import { ConfirmationRequest } from '@/types/message';
import { useFileUpload } from '@/hooks/useFileUpload';
import { cn } from '@/lib/cn';
import { INPUT_PLACEHOLDERS } from '@/config/brands';
import { useContextStore, type ContextTag } from '@/stores/contextStore';

interface InputAreaProps {
  onSend: (content: string, attachments?: { id: string; name: string; url: string }[], context?: ContextTag[]) => void;
  onStop: () => void;
  isExecuting: boolean;
  disabled?: boolean;
  pendingConfirmation?: ConfirmationRequest | null;
  onConfirmation?: (optionId: string) => void;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
}

export function InputArea({
  onSend,
  onStop,
  isExecuting,
  disabled = false,
  pendingConfirmation,
  onConfirmation,
  value: controlledValue,
  onChange,
  placeholder: customPlaceholder,
}: InputAreaProps) {
  const [internalContent, setInternalContent] = useState('');
  const content = controlledValue !== undefined ? controlledValue : internalContent;

  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { attachments, isUploading, inputRef, openFilePicker, removeAttachment, clearAttachments, handleFileChange } = useFileUpload({
    onError: (msg) => console.warn('[FileUpload]', msg),
  });

  const { contextTags, removeContextTag, clearContextTags } = useContextStore();

  // 自动调整高度
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);

  // 快捷键
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isExecuting) {
        e.preventDefault();
        onStop();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isExecuting, onStop]);

  const handleSubmit = () => {
    if (!content.trim() || isExecuting || disabled) return;
    const atts = attachments.length > 0
      ? attachments.map((a) => ({ id: a.id, name: a.name, url: a.url || '' }))
      : undefined;
    onSend(content.trim(), atts, contextTags.length > 0 ? [...contextTags] : undefined);
    if (onChange) {
      onChange('');
    } else {
      setInternalContent('');
    }
    clearAttachments();
    clearContextTags();

    // 重置高度
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const placeholder = customPlaceholder || (isExecuting
    ? INPUT_PLACEHOLDERS.executing
    : pendingConfirmation
    ? INPUT_PLACEHOLDERS.confirmation
    : INPUT_PLACEHOLDERS.default);

  return (
    <div className="border-t" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)' }}>
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={'.png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.csv,.json,.xlsx,.xls'}
        onChange={handleFileChange}
        className="hidden"
      />

      {/* 快捷确认按钮 */}
      {pendingConfirmation && !isExecuting && (
        <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)' }}>
          <div className="max-w-3xl mx-auto flex items-center gap-2">
            <span className="text-xs" style={{ color: 'var(--text-tertiary)' }}>快捷回复：</span>
            {pendingConfirmation.options.slice(0, 3).map((option) => (
              <button
                key={option.id}
                onClick={() => onConfirmation?.(option.id)}
                className="px-3 py-1.5 rounded-lg text-xs font-medium transition-colors hover:opacity-90"
                style={{
                  backgroundColor: option.recommended ? 'var(--color-primary)' : 'var(--bg-tertiary)',
                  color: option.recommended ? '#fff' : 'var(--text-secondary)',
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Attachment preview strip */}
      {attachments.length > 0 && (
        <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="max-w-3xl mx-auto flex items-center gap-2 flex-wrap">
            {attachments.map((att) => (
              <div
                key={att.id}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                <span className="max-w-[120px] truncate">{att.name}</span>
                <button
                  onClick={() => removeAttachment(att.id)}
                  className="transition-colors"
                  style={{ color: 'var(--text-tertiary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; }}
                >
                  <RiCloseLine className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
            {isUploading && (
              <RiLoader4Line className="w-4 h-4 animate-spin" style={{ color: 'var(--color-primary)' }} />
            )}
          </div>
        </div>
      )}

      {/* Context tags strip */}
      {contextTags.length > 0 && (
        <div className="px-4 py-2 border-b" style={{ borderColor: 'var(--border-subtle)' }}>
          <div className="max-w-3xl mx-auto flex flex-wrap gap-1.5">
            {contextTags.map((tag) => {
              const typeLabels: Record<string, string> = {
                profile: '\u753B\u50CF',
                scenario: '\u573A\u666F',
                intent: '\u610F\u56FE',
              };
              const typeColors: Record<string, string> = {
                profile: '#a855f7',
                scenario: '#3b82f6',
                intent: '#f59e0b',
              };
              return (
                <span
                  key={tag.id}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded-md text-xs"
                  style={{
                    backgroundColor: `${typeColors[tag.type]}15`,
                    color: typeColors[tag.type],
                    border: `1px solid ${typeColors[tag.type]}30`,
                  }}
                >
                  {typeLabels[tag.type]}: {tag.label}
                  <button
                    onClick={() => removeContextTag(tag.id)}
                    className="ml-0.5 hover:opacity-70 cursor-pointer"
                  >
                    <RiCloseLine className="w-3 h-3" />
                  </button>
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* 输入区 */}
      <div className="px-4 py-4">
        <div className="max-w-3xl mx-auto">
          {/* 输入框行 */}
          <div className="flex items-end gap-2">
            {/* 附件按钮 */}
            <button
              onClick={openFilePicker}
              className="p-2 rounded-xl transition-colors flex-shrink-0"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
              title="附件"
              disabled={isExecuting || disabled || isUploading}
            >
              {isUploading ? (
                <RiLoader4Line className="w-5 h-5 animate-spin" />
              ) : (
                <RiAttachmentLine className="w-5 h-5" />
              )}
            </button>

            {/* 输入框 - 单层设计，隐藏滚动条 */}
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => {
                if (onChange) {
                  onChange(e.target.value);
                } else {
                  setInternalContent(e.target.value);
                }
              }}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={isExecuting || disabled}
              rows={1}
              className={cn(
                'flex-1 resize-none rounded-2xl px-4 py-3 text-sm leading-6',
                'border',
                'focus:outline-none focus:ring-2 focus:ring-[--color-primary]/20',
                'min-h-[48px] max-h-[200px]',
                'disabled:cursor-not-allowed disabled:opacity-50',
                disabled && 'opacity-50',
                'scrollbar-hide'
              )}
              style={{
                color: 'var(--text-primary)',
                backgroundColor: 'var(--bg-secondary)',
                borderColor: 'var(--border-subtle)',
                scrollbarWidth: 'none',
                msOverflowStyle: 'none',
              }}
            />

            {/* 发送/停止按钮 */}
            {!isExecuting ? (
              <button
                onClick={handleSubmit}
                disabled={!content.trim() || disabled}
                className="p-2.5 rounded-xl transition-all flex-shrink-0 hover:opacity-90"
                style={{
                  backgroundColor: content.trim() && !disabled ? 'var(--color-primary)' : 'var(--bg-tertiary)',
                  color: content.trim() && !disabled ? '#fff' : 'var(--text-muted)',
                  cursor: content.trim() && !disabled ? 'pointer' : 'not-allowed',
                }}
              >
                <RiSendPlaneLine className="w-5 h-5" />
              </button>
            ) : (
              <button
                onClick={onStop}
                className="p-2.5 rounded-xl text-white hover:opacity-90 transition-colors flex-shrink-0"
                style={{ backgroundColor: 'var(--error, #EF4444)' }}
              >
                <RiStopLine className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* 提示文字 */}
          <div className="flex items-center justify-center gap-4 mt-2 text-xs">
            {!isExecuting ? (
              <>
                <span className="flex items-center gap-1" style={{ color: 'var(--text-tertiary)' }}>
                  <kbd className="px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>Enter</kbd>
                  发送
                </span>
                <span className="flex items-center gap-1" style={{ color: 'var(--text-tertiary)' }}>
                  <kbd className="px-1.5 py-0.5 rounded" style={{ backgroundColor: 'var(--bg-tertiary)', color: 'var(--text-secondary)' }}>Shift + Enter</kbd>
                  换行
                </span>
              </>
            ) : (
              <span className="flex items-center gap-2" style={{ color: 'var(--warning)' }}>
                <RiLoader4Line className="w-3 h-3 animate-spin" />
                Agent 正在执行分析任务，请稍候...
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
