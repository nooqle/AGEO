'use client';

import { useCallback, useRef } from 'react';
import {
  RiSearchEyeLine,
  RiArrowLeftRightLine,
  RiRefreshLine,
  RiQuestionLine,
} from '@remixicon/react';
import { cn } from '@/lib/cn';
import type { FollowUpSuggestion } from '@/types/task';

interface FollowUpChipsProps {
  suggestions: FollowUpSuggestion[];
  onSelect: (suggestion: FollowUpSuggestion) => void;
  className?: string;
}

const ICON_MAP: Record<FollowUpSuggestion['type'], typeof RiSearchEyeLine> = {
  drill_down: RiSearchEyeLine,
  compare: RiArrowLeftRightLine,
  refetch: RiRefreshLine,
  general: RiQuestionLine,
};

const ICON_COLORS: Record<FollowUpSuggestion['type'], string> = {
  drill_down: 'var(--info, #3B82F6)',
  compare: 'var(--phase-plan, #8B5CF6)',
  refetch: 'var(--warning, #F59E0B)',
  general: 'var(--text-secondary)',
};

const MAX_CHIPS = 4;

export function FollowUpChips({ suggestions, onSelect, className }: FollowUpChipsProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const visibleSuggestions = suggestions.slice(0, MAX_CHIPS);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent, index: number) => {
      const buttons = containerRef.current?.querySelectorAll<HTMLButtonElement>('[role="button"]');
      if (!buttons) return;

      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        const next = (index + 1) % buttons.length;
        buttons[next].focus();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        const prev = (index - 1 + buttons.length) % buttons.length;
        buttons[prev].focus();
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        onSelect(visibleSuggestions[index]);
      }
    },
    [onSelect, visibleSuggestions]
  );

  if (visibleSuggestions.length === 0) return null;

  return (
    <div
      ref={containerRef}
      role="group"
      aria-label="推荐追问"
      className={cn(
        'flex flex-wrap gap-2 mt-3 pt-3',
        className
      )}
      style={{ borderTop: '1px solid var(--border-subtle)' }}
    >
      {visibleSuggestions.map((suggestion, index) => {
        const Icon = ICON_MAP[suggestion.type] || RiQuestionLine;
        return (
          <button
            key={suggestion.id}
            role="button"
            tabIndex={0}
            aria-label={suggestion.label}
            onClick={() => onSelect(suggestion)}
            onKeyDown={(e) => handleKeyDown(e, index)}
            className={cn(
              'inline-flex items-center gap-1 px-3.5 py-1.5 rounded-lg text-xs',
              'cursor-pointer transition-all duration-150 ease-out',
              'animate-fade-in',
              `animate-stagger-${index + 1}`,
            )}
            style={{
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--border-subtle)',
              color: 'var(--text-secondary)',
              opacity: 0,
              animationFillMode: 'forwards',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'var(--bg-elevated)';
              e.currentTarget.style.borderColor = 'var(--border-hover)';
              e.currentTarget.style.color = 'var(--text-primary)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'var(--bg-tertiary)';
              e.currentTarget.style.borderColor = 'var(--border-subtle)';
              e.currentTarget.style.color = 'var(--text-secondary)';
            }}
          >
            <Icon className="w-3 h-3 flex-shrink-0" style={{ color: ICON_COLORS[suggestion.type] || 'var(--text-secondary)' }} />
            <span>{suggestion.label}</span>
          </button>
        );
      })}
    </div>
  );
}

export default FollowUpChips;
