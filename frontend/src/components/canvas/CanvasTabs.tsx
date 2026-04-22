'use client';

import { useCanvasStore } from '@/stores/canvasStore';
import { cn } from '@/lib/cn';
import { RiCloseLine } from '@remixicon/react';

function formatDuplicateSuffix(createdAt: Date | string | undefined): string {
  if (!createdAt) {
    return '';
  }
  const parsed = createdAt instanceof Date ? createdAt : new Date(createdAt);
  if (Number.isNaN(parsed.getTime())) {
    return '';
  }
  const month = `${parsed.getMonth() + 1}`.padStart(2, '0');
  const day = `${parsed.getDate()}`.padStart(2, '0');
  const hours = `${parsed.getHours()}`.padStart(2, '0');
  const minutes = `${parsed.getMinutes()}`.padStart(2, '0');
  return `${month}-${day} ${hours}:${minutes}`;
}

export function CanvasTabs() {
  const { contents, activeContentIndex, setActiveContentById, removeContent, setActiveSurface } =
    useCanvasStore();
  const titleCounts = contents.reduce((acc, content) => {
    const next = acc.get(content.title) ?? 0;
    acc.set(content.title, next + 1);
    return acc;
  }, new Map<string, number>());

  return (
    <div className="flex items-center gap-1 px-2 py-2 border-b border-[var(--border-subtle)] bg-[var(--bg-primary)] overflow-x-auto">
      {contents.map((content, index) => {
        const hasDuplicateTitle = (titleCounts.get(content.title) ?? 0) > 1;
        const duplicateSuffix = hasDuplicateTitle
          ? formatDuplicateSuffix(content.createdAt)
          : '';
        const displayTitle = duplicateSuffix
          ? `${content.title} · ${duplicateSuffix}`
          : content.title;

        return (
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
              setActiveContentById(content.id);
            }}
          >
            <span className="truncate max-w-[180px]" title={displayTitle}>
              {displayTitle}
            </span>
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
              type="button"
              className="p-0.5 hover:bg-[var(--bg-tertiary)] rounded transition-colors"
              onClick={(e) => {
                e.stopPropagation();
                removeContent(content.id);
              }}
            >
              <RiCloseLine className="w-3 h-3 text-[var(--text-secondary)]" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
