'use client';

import { useState, useRef, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
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
  const [menuPos, setMenuPos] = useState<{ top: number; left: number } | null>(null);
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

  const toggleMenu = useCallback(() => {
    if (!showMenu && buttonRef.current) {
      const rect = buttonRef.current.getBoundingClientRect();
      // Menu width is w-36 = 144px
      const menuWidth = 144;
      let left = rect.right - menuWidth;
      // Clamp to viewport left edge
      if (left < 4) left = 4;
      setMenuPos({ top: rect.bottom + 4, left });
    }
    setShowMenu((prev) => !prev);
  }, [showMenu]);

  // Close menu when clicking outside
  const handleClickOutside = useCallback((e: MouseEvent) => {
    if (
      menuRef.current && !menuRef.current.contains(e.target as Node) &&
      buttonRef.current && !buttonRef.current.contains(e.target as Node)
    ) {
      setShowMenu(false);
    }
  }, []);

  // Close menu on scroll or resize
  useEffect(() => {
    if (!showMenu) return;
    document.addEventListener('mousedown', handleClickOutside);
    const closeMenu = () => setShowMenu(false);
    window.addEventListener('scroll', closeMenu, true);
    window.addEventListener('resize', closeMenu);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      window.removeEventListener('scroll', closeMenu, true);
      window.removeEventListener('resize', closeMenu);
    };
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
      <button
        ref={buttonRef}
        onClick={toggleMenu}
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

      {showMenu && menuPos && createPortal(
        <div
          ref={menuRef}
          className="fixed w-36 rounded-xl shadow-lg py-1 z-[9999]"
          style={{
            top: menuPos.top,
            left: menuPos.left,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border-subtle)',
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
              <div className="my-1" style={{ borderTop: '1px solid var(--border-subtle)' }} />
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

          <div className="my-1" style={{ borderTop: '1px solid var(--border-subtle)' }} />

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
        </div>,
        document.body,
      )}
    </div>
  );
}
