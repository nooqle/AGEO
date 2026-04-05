'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import {
  RiSendPlaneLine,
  RiStopLine,
  RiAttachmentLine,
  RiLoader4Line,
  RiCloseLine,
  RiToolsLine,
  RiArrowDownSLine,
  RiShieldCheckLine,
} from '@remixicon/react';
import { ConfirmationRequest } from '@/types/message';
import { useFileUpload } from '@/hooks/useFileUpload';
import { cn } from '@/lib/cn';
import { INPUT_PLACEHOLDERS } from '@/config/brands';
import { useContextStore, type ContextTag } from '@/stores/contextStore';
import { toast } from '@/components/ui/toast';
import type { ToolMode } from '@/types/toolMode';
import { CONFIDENCE_ANALYSIS_TOOL_MODE } from '@/types/toolMode';
import type { Attachment } from '@/components/chat/Message/AttachmentCard';

const TABLE_UPLOAD_HINT_SEEN_KEY = 'specta.table-upload-hint-seen';

interface InputAreaProps {
  onSend: (
    content: string,
    attachments?: Attachment[],
    context?: ContextTag[],
    toolMode?: ToolMode | null,
  ) => void;
  onStop: () => void;
  isExecuting: boolean;
  disabled?: boolean;
  pendingConfirmation?: ConfirmationRequest | null;
  onConfirmation?: (optionId: string) => void;
  value?: string;
  onChange?: (value: string) => void;
  placeholder?: string;
  progressMessage?: string;
  selectedToolMode?: ToolMode | null;
  onToolModeChange?: (mode: ToolMode | null) => void;
  previousUserMessage?: string | null;
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
  progressMessage,
  selectedToolMode,
  onToolModeChange,
  previousUserMessage,
}: InputAreaProps) {
  const [internalContent, setInternalContent] = useState('');
  const [toolMenuOpen, setToolMenuOpen] = useState(false);
  const content = controlledValue !== undefined ? controlledValue : internalContent;

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const toolMenuRef = useRef<HTMLDivElement>(null);

  const { attachments, isUploading, inputRef, openFilePicker, removeAttachment, clearAttachments, handleFileChange } = useFileUpload({
    maxFiles: 1,
    onError: (msg) => toast.error(msg),
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

  useEffect(() => {
    if (!toolMenuOpen) return;

    const handlePointerDown = (event: MouseEvent) => {
      if (!toolMenuRef.current?.contains(event.target as Node)) {
        setToolMenuOpen(false);
      }
    };

    window.addEventListener('mousedown', handlePointerDown);
    return () => window.removeEventListener('mousedown', handlePointerDown);
  }, [toolMenuOpen]);

  const handleOpenFilePicker = useCallback(() => {
    try {
      if (!window.localStorage.getItem(TABLE_UPLOAD_HINT_SEEN_KEY)) {
        toast.info('可上传 1 个 CSV/XLSX 表格（2MB 内）：问题表可直接启动抓取，品牌或竞品表可补充分析上下文，链接表可用于来源评估。', 5000);
        window.localStorage.setItem(TABLE_UPLOAD_HINT_SEEN_KEY, '1');
      }
    } catch {
      // Ignore local storage errors and continue opening the picker.
    }

    openFilePicker();
  }, [openFilePicker]);

  const handleSubmit = () => {
    const trimmedContent = content.trim();
    if ((!trimmedContent && attachments.length === 0) || isExecuting || disabled) return;
    if (isUploading) {
      toast.error('文件仍在上传，请等待上传完成后再发送。');
      return;
    }
    if (attachments.some((attachment) => !attachment.id)) {
      toast.error('附件尚未准备完成，请稍后再发送。');
      return;
    }
    const atts = attachments.length > 0
      ? attachments.map((a) => ({
          id: a.id,
          name: a.name,
          size: a.size,
          type: a.type,
          url: a.url || undefined,
        }))
      : undefined;
    onSend(
      trimmedContent,
      atts,
      contextTags.length > 0 ? [...contextTags] : undefined,
      selectedToolMode ?? null,
    );
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
    if (
      e.key === 'ArrowUp' &&
      !e.shiftKey &&
      !e.altKey &&
      !e.ctrlKey &&
      !e.metaKey &&
      !e.nativeEvent.isComposing &&
      previousUserMessage &&
      content.trim().length === 0
    ) {
      e.preventDefault();
      if (onChange) {
        onChange(previousUserMessage);
      } else {
        setInternalContent(previousUserMessage);
      }
      requestAnimationFrame(() => {
        const textarea = textareaRef.current;
        if (!textarea) return;
        const cursor = textarea.value.length;
        textarea.focus();
        textarea.setSelectionRange(cursor, cursor);
      });
      return;
    }

    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const handleToolModeSelect = (mode: ToolMode) => {
    onToolModeChange?.(mode);
    setToolMenuOpen(false);
  };

  const handleToolModeClear = () => {
    onToolModeChange?.(null);
  };

  const placeholder = customPlaceholder || (isExecuting
    ? INPUT_PLACEHOLDERS.executing
    : pendingConfirmation
    ? INPUT_PLACEHOLDERS.confirmation
    : selectedToolMode === CONFIDENCE_ANALYSIS_TOOL_MODE
    ? '粘贴链接、引用列表、一段文本，或说明要分析当前会话里的引用来源'
    : INPUT_PLACEHOLDERS.default);

  return (
    <div className="border-t" style={{ borderColor: 'var(--border-subtle)', backgroundColor: 'var(--bg-primary)' }}>
      {/* Hidden file input */}
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={'.csv,.xlsx'}
        onChange={handleFileChange}
        className="hidden"
      />

      {/* 快捷确认按钮 — 空 options 时不渲染（自然语言模式） */}
      {pendingConfirmation && !isExecuting && pendingConfirmation.options.length > 0 && (
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
                key={att.id || att.url || `${att.name}-${att.size ?? 'na'}`}
                className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs"
                style={{
                  backgroundColor: 'var(--bg-secondary)',
                  border: '1px solid var(--border-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                <span className="max-w-[120px] truncate">{att.name}</span>
                <button
                  onClick={() => {
                    if (att.id) {
                      removeAttachment(att.id);
                    }
                  }}
                  className="transition-colors"
                  style={{ color: 'var(--text-tertiary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-primary)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; }}
                  disabled={!att.id}
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
              onClick={handleOpenFilePicker}
              className="p-2 rounded-xl transition-colors flex-shrink-0"
              style={{ color: 'var(--text-tertiary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.color = 'var(--text-secondary)'; e.currentTarget.style.backgroundColor = 'var(--bg-tertiary)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.color = 'var(--text-tertiary)'; e.currentTarget.style.backgroundColor = 'transparent'; }}
              title="上传表格"
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
              disabled={isExecuting || disabled || isUploading}
              rows={1}
              className={cn(
                'flex-1 resize-none rounded-2xl px-4 py-3 text-sm leading-6',
                'border',
                'focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]/20',
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
                disabled={(!content.trim() && attachments.length === 0) || disabled || isUploading}
                className="p-2.5 rounded-xl transition-all flex-shrink-0 hover:opacity-90"
                style={{
                  backgroundColor: (content.trim() || attachments.length > 0) && !disabled && !isUploading ? 'var(--color-primary)' : 'var(--bg-tertiary)',
                  color: (content.trim() || attachments.length > 0) && !disabled && !isUploading ? '#fff' : 'var(--text-muted)',
                  cursor: (content.trim() || attachments.length > 0) && !disabled && !isUploading ? 'pointer' : 'not-allowed',
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

          <div className="mt-3 flex items-center gap-2" ref={toolMenuRef}>
            <div className="relative">
              <button
                type="button"
                onClick={() => setToolMenuOpen((open) => !open)}
                disabled={isExecuting || disabled}
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                style={{
                  borderColor: 'var(--border-subtle)',
                  backgroundColor: 'var(--bg-secondary)',
                  color: 'var(--text-secondary)',
                }}
              >
                <RiToolsLine className="h-3.5 w-3.5" />
                工具
                <RiArrowDownSLine className="h-3.5 w-3.5" />
              </button>

              {toolMenuOpen && !isExecuting && !disabled ? (
                <div
                  className="absolute bottom-[calc(100%+8px)] left-0 z-20 min-w-[220px] rounded-2xl border p-2 shadow-[0_16px_40px_rgba(15,23,42,0.18)]"
                  style={{
                    borderColor: 'var(--border-subtle)',
                    backgroundColor: 'var(--bg-primary)',
                  }}
                >
                  <button
                    type="button"
                    onClick={() => handleToolModeSelect(CONFIDENCE_ANALYSIS_TOOL_MODE)}
                    className="flex w-full items-start gap-3 rounded-xl px-3 py-3 text-left transition-colors"
                    style={{
                      backgroundColor:
                        selectedToolMode === CONFIDENCE_ANALYSIS_TOOL_MODE
                          ? 'var(--bg-secondary)'
                          : 'transparent',
                    }}
                  >
                    <span
                      className="mt-0.5 inline-flex h-7 w-7 items-center justify-center rounded-full"
                      style={{
                        backgroundColor: 'rgba(37,99,235,0.12)',
                        color: '#2563eb',
                      }}
                    >
                      <RiShieldCheckLine className="h-4 w-4" />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                        置信度分析
                      </span>
                      <span className="mt-1 block text-xs leading-5" style={{ color: 'var(--text-secondary)' }}>
                        评估链接、引用来源或导入链接清单的可信度、结构化质量与可核查性
                      </span>
                    </span>
                  </button>
                </div>
              ) : null}
            </div>

            {selectedToolMode === CONFIDENCE_ANALYSIS_TOOL_MODE ? (
              <span
                className="inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs"
                style={{
                  borderColor: 'rgba(37,99,235,0.22)',
                  backgroundColor: 'rgba(37,99,235,0.08)',
                  color: '#1d4ed8',
                }}
              >
                <RiShieldCheckLine className="h-3.5 w-3.5" />
                置信度分析
                <button
                  type="button"
                  onClick={handleToolModeClear}
                  className="rounded-full p-0.5 transition-colors hover:bg-white/40"
                >
                  <RiCloseLine className="h-3.5 w-3.5" />
                </button>
              </span>
            ) : null}
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
              <span className="flex items-center gap-2 truncate max-w-full" style={{ color: 'var(--warning)' }}>
                <RiLoader4Line className="w-3 h-3 animate-spin flex-shrink-0" />
                {progressMessage || '系统正在分析，请稍候...'}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
