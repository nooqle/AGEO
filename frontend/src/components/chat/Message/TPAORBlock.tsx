'use client';

import { useState } from 'react';
import { RiArrowDownSLine, RiBrainLine, RiListCheck, RiFlashlightLine, RiEyeLine, RiMessage3Line, RiLoader4Line } from '@remixicon/react';
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
    icon: RiBrainLine,
    label: '思考',
    activeLabel: '正在思考...',
    colors: {
      bg: 'bg-[--bg-secondary]',
      border: 'border-[#8B5CF6]/30',
      text: 'text-[--text-primary]',
      icon: 'text-[#8B5CF6]',
      ring: 'ring-[#8B5CF6]/50',
    },
  },
  plan: {
    icon: RiListCheck,
    label: '规划',
    activeLabel: '正在规划...',
    colors: {
      bg: 'bg-[--bg-secondary]',
      border: 'border-[#3B82F6]/30',
      text: 'text-[--text-primary]',
      icon: 'text-[#3B82F6]',
      ring: 'ring-[#3B82F6]/50',
    },
  },
  action: {
    icon: RiFlashlightLine,
    label: '执行',
    activeLabel: '正在执行...',
    colors: {
      bg: 'bg-[--bg-secondary]',
      border: 'border-[#F59E0B]/30',
      text: 'text-[--text-primary]',
      icon: 'text-[#F59E0B]',
      ring: 'ring-[#F59E0B]/50',
    },
  },
  observation: {
    icon: RiEyeLine,
    label: '观察',
    activeLabel: '正在观察...',
    colors: {
      bg: 'bg-[--bg-secondary]',
      border: 'border-[#22C55E]/30',
      text: 'text-[--text-primary]',
      icon: 'text-[#22C55E]',
      ring: 'ring-[#22C55E]/50',
    },
  },
  response: {
    icon: RiMessage3Line,
    label: '回复',
    activeLabel: '正在生成回复...',
    colors: {
      bg: 'bg-[--bg-secondary]',
      border: 'border-[#6366F1]/30',
      text: 'text-[--text-primary]',
      icon: 'text-[#6366F1]',
      ring: 'ring-[#6366F1]/50',
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
        config.colors.border,
        isActive && 'ring-2 ring-offset-1 ring-offset-[--bg-primary]',
        isActive && config.colors.ring
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
            'w-4 h-4 text-[--text-tertiary] transition-transform duration-200',
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
          <div className={cn('text-sm whitespace-pre-wrap text-[--text-secondary]')}>
            {content}
          </div>

          {/* 进度条 */}
          {typeof progress === 'number' && (
            <div className="mt-3">
              <div className="h-1.5 bg-[--bg-tertiary] rounded-full overflow-hidden">
                <div
                  className={cn(
                    'h-full rounded-full transition-all duration-300',
                    config.colors.icon
                  )}
                  style={{ width: `${progress * 100}%` }}
                />
              </div>
              <div className="text-xs text-[--text-tertiary] mt-1 text-right">
                {Math.round(progress * 100)}%
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
