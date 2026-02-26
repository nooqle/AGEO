'use client';

import { useEffect, useCallback } from 'react';
import { RiArrowGoBackLine } from '@remixicon/react';

interface RecallConfirmationProps {
  messageCount: number;
  onConfirm: () => void;
  onCancel: () => void;
}

export function RecallConfirmation({ messageCount, onConfirm, onCancel }: RecallConfirmationProps) {
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopImmediatePropagation();
      onCancel();
    }
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      e.stopImmediatePropagation();
      onConfirm();
    }
  }, [onConfirm, onCancel]);

  useEffect(() => {
    // Use capture phase so this fires before InputArea's Enter handler (BUG-RECALL-02)
    document.addEventListener('keydown', handleKeyDown, true);
    return () => document.removeEventListener('keydown', handleKeyDown, true);
  }, [handleKeyDown]);

  const countText = messageCount > 0
    ? `该消息之后的 ${messageCount} 条对话和对应的分析结果将被清除，之前已完成的分析结果将保留。`
    : '该消息和对应的分析结果将被清除。';

  return (
    <div
      className="mt-2 rounded-xl px-4 py-3 shadow-sm"
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--border-subtle)',
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <RiArrowGoBackLine className="w-3.5 h-3.5 flex-shrink-0" style={{ color: 'var(--warning)' }} />
        <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          确定回退至此次问答吗？
        </span>
      </div>

      <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
        {countText}
        <br />
        消息内容将填入输入框供您修改后重新发送。
      </p>

      <div className="flex items-center justify-between">
        <span className="text-[11px]" style={{ color: 'var(--text-tertiary)' }}>
          Esc 取消 · Enter 确认
        </span>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            className="px-3 py-1.5 text-sm rounded-lg transition-colors cursor-pointer"
            style={{
              color: 'var(--text-secondary)',
              border: '1px solid var(--border-subtle)',
              background: 'transparent',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-elevated)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
          >
            取消
          </button>
          <button
            onClick={onConfirm}
            className="px-3 py-1.5 text-sm rounded-lg transition-colors cursor-pointer flex items-center gap-1"
            style={{
              color: '#fff',
              background: '#d97706',
              border: 'none',
            }}
            onMouseEnter={(e) => { e.currentTarget.style.background = '#b45309'; }}
            onMouseLeave={(e) => { e.currentTarget.style.background = '#d97706'; }}
          >
            确认回退
            <RiArrowGoBackLine className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
