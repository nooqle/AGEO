'use client';

import { useState } from 'react';
import { RiArrowDownSLine, RiSearchLine, RiListCheck, RiFlashlightLine, RiEyeLine, RiMessage3Line, RiLoader4Line } from '@remixicon/react';
import { cn } from '@/lib/cn';

interface TPAORBlockProps {
  phase: 'thought' | 'plan' | 'action' | 'observation' | 'response';
  content: string;
  isActive?: boolean;
  isComplete?: boolean;
  defaultExpanded?: boolean;
  progress?: number;
}

const phaseConfig = {
  thought: {
    icon: RiSearchLine,
    label: '思考',
    activeLabel: '正在思考...',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--brand-border)]',
      text: 'text-[var(--text-primary)]',
      icon: 'text-[var(--brand-text)]',
      ring: 'ring-[var(--brand-border)]',
    },
  },
  plan: {
    icon: RiListCheck,
    label: '规划',
    activeLabel: '正在规划...',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-hover)]',
      text: 'text-[var(--text-primary)]',
      icon: 'text-[var(--info)]',
      ring: 'ring-[var(--border-hover)]',
    },
  },
  action: {
    icon: RiFlashlightLine,
    label: '执行',
    activeLabel: '正在执行...',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-hover)]',
      text: 'text-[var(--text-primary)]',
      icon: 'text-[var(--warning)]',
      ring: 'ring-[var(--border-hover)]',
    },
  },
  observation: {
    icon: RiEyeLine,
    label: '观察',
    activeLabel: '正在观察...',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--border-hover)]',
      text: 'text-[var(--text-primary)]',
      icon: 'text-[var(--success)]',
      ring: 'ring-[var(--border-hover)]',
    },
  },
  response: {
    icon: RiMessage3Line,
    label: '回复',
    activeLabel: '正在生成回复...',
    colors: {
      bg: 'bg-[var(--bg-elevated)]',
      border: 'border-[var(--brand-border)]',
      text: 'text-[var(--text-primary)]',
      icon: 'text-[var(--brand-text)]',
      ring: 'ring-[var(--brand-border)]',
    },
  },
};

export function TPAORBlock({
  phase,
  content,
  isActive = false,
  defaultExpanded = false,
  progress,
}: TPAORBlockProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = phaseConfig[phase];
  const Icon = config.icon;

  return (
    <div
      className={cn(
        'rounded-xl border overflow-hidden transition-all',
        config.colors.bg,
        isActive ? config.colors.border : 'border-transparent',
      )}
    >
      {/* 标题栏 */}
      <button
        className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-white/5 transition-colors"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex items-center gap-2">
          {isActive ? (
            <RiLoader4Line className={cn('w-4 h-4 animate-spin', config.colors.icon)} />
          ) : (
            <Icon className={cn('w-4 h-4', config.colors.icon)} />
          )}
          <span className={cn('text-sm font-medium', config.colors.text)}>
            {isActive ? config.activeLabel : config.label}
          </span>
        </div>
        <RiArrowDownSLine
          className={cn(
            'w-4 h-4 text-[var(--text-tertiary)] transition-transform duration-200',
            isExpanded && 'rotate-180'
          )}
        />
      </button>

      {/* 内容区 */}
      <div
        className={cn(
          'overflow-hidden transition-all duration-200',
          isExpanded ? 'max-h-96' : 'max-h-0'
        )}
      >
        <div className="px-3 pb-3">
          <div className={cn('text-sm whitespace-pre-wrap text-[var(--text-secondary)]')}>
            {content}
          </div>

          {/* 进度条 */}
          {typeof progress === 'number' && (
            <div className="mt-3">
              <div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-300',
                    config.colors.icon
                  )}
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
              <div className="text-xs text-[var(--text-tertiary)] mt-1 text-right">
                {Math.round(progress * 100)}%
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
