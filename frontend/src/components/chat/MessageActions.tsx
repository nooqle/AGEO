'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { RiMoreLine, RiFileCopyLine, RiCheckLine, RiDeleteBinLine, RiRefreshLine } from '@remixicon/react';
import { Message } from '@/types/message';
import { cn } from '@/lib/cn';

interface MessageActionsProps {
  message: Message;
  onRetry?: () => void;
  className?: string;
}

export function MessageActions({ message, onRetry, className }: MessageActionsProps) {
  const [showMenu, setShowMenu] = useState(false);
  const [copied, setCopied] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(message.content);
    setCopied(true);
    setShowMenu(false);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRetry = () => {
    setShowMenu(false);
    onRetry?.();
  };

  const handleDelete = () => {
    // TODO: 实现删除功能
    setShowMenu(false);
  };

  // Close menu when clicking outside
  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (
      menuRef.current && !menuRef.current.contains(e.target as Node) &&
      buttonRef.current && !buttonRef.current.contains(e.target as Node)
    ) {
      setShowMenu(false);
    }
  }, []);

  useEffect(() => {
    if (showMenu) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [showMenu, handleClickOutside]);

  return (
    <div
      className={cn(
        // 当菜单打开时始终可见，否则跟随 group-hover
        showMenu ? 'opacity-100' : 'opacity-0 group-hover:opacity-100',
        'transition-opacity',
        className,
      )}
    >
      <div className="relative">
        <button
          ref={buttonRef}
          onClick={() => setShowMenu(!showMenu)}
          className="p-1.5 rounded-lg transition-colors cursor-pointer"
          style={{
            color: 'var(--text-muted)',
            background: showMenu ? 'var(--bg-elevated)' : 'transparent',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.background = 'var(--bg-elevated)';
            e.currentTarget.style.color = 'var(--text-secondary)';
          }}
          onMouseLeave={(e) => {
            if (!showMenu) {
              e.currentTarget.style.background = 'transparent';
              e.currentTarget.style.color = 'var(--text-muted)';
            }
          }}
        >
          {copied ? (
            <RiCheckLine className="w-4 h-4" style={{ color: 'var(--status-success)' }} />
          ) : (
            <RiMoreLine className="w-4 h-4" />
          )}
        </button>

        {showMenu && (
          <div
            ref={menuRef}
            className="absolute top-full mt-1 right-0 w-36 rounded-xl shadow-lg py-1 z-20"
            style={{
              background: 'var(--bg-secondary)',
              border: '1px solid var(--border-default)',
            }}
          >
            <button
              onClick={handleCopy}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors cursor-pointer"
              style={{ color: 'var(--text-secondary)' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-elevated)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <RiFileCopyLine className="w-4 h-4" />
              复制内容
            </button>

            {onRetry && (
              <>
                <div className="my-1" style={{ borderTop: '1px solid var(--border-default)' }} />
                <button
                  onClick={handleRetry}
                  className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors cursor-pointer"
                  style={{ color: 'var(--text-secondary)' }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-elevated)'; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
                >
                  <RiRefreshLine className="w-4 h-4" />
                  重新生成
                </button>
              </>
            )}

            <div className="my-1" style={{ borderTop: '1px solid var(--border-default)' }} />

            <button
              onClick={handleDelete}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm transition-colors cursor-pointer"
              style={{ color: 'var(--status-error)' }}
              onMouseEnter={(e) => { e.currentTarget.style.background = 'var(--bg-elevated)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
            >
              <RiDeleteBinLine className="w-4 h-4" />
              删除消息
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
