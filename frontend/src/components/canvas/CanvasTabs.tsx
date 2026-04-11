'use client';

import { useCanvasStore } from '@/stores/canvasStore';
import { cn } from '@/lib/cn';
import { RiCloseLine } from '@remixicon/react';

export function CanvasTabs() {
  const { contents, activeContentIndex, setActiveContent, removeContent, setActiveSurface } =
    useCanvasStore();

  return (
    <div className="flex items-center gap-1 px-2 py-2 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)] overflow-x-auto">
      {contents.map((content, index) => (
        <div
          key={content.id}
          className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm cursor-pointer transition-colors',
            index === activeContentIndex
              ? 'bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border-hover)]'
              : 'text-[var(--text-secondary)] hover:bg-[var(--bg-secondary)]'
          )}
          onClick={() => {
            setActiveSurface('artifact');
            setActiveContent(index);
          }}
        >
          <span className="truncate max-w-[120px]">{content.title}</span>
          {content.hasNewVersion && index !== activeContentIndex && (
            <span
              className="px-1 py-0.5 rounded text-[9px] font-bold leading-none"
              style={{
                backgroundColor: 'var(--status-error-bg)',
                color: 'var(--error)',
              }}
            >
              NEW
            </span>
          )}
          <button
            className="p-0.5 hover:bg-[var(--bg-tertiary)] rounded transition-colors"
            onClick={(e) => {
              e.stopPropagation();
              removeContent(content.id);
            }}
          >
            <RiCloseLine className="w-3 h-3 text-[var(--text-secondary)]" />
          </button>
        </div>
      ))}
    </div>
  );
}
