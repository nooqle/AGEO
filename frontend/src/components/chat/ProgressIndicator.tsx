'use client';

import { RiCheckLine, RiLoader4Line, RiCheckboxBlankCircleLine } from '@remixicon/react';
import { cn } from '@/lib/cn';

export type StepStatus = 'completed' | 'in_progress' | 'pending';

export interface ProgressStep {
  id: string;
  label: string;
  description?: string;
  status: StepStatus;
}

interface ProgressIndicatorProps {
  steps: ProgressStep[];
  title?: string;
  className?: string;
}

// 步骤状态配置
const statusConfig = {
  completed: {
    icon: RiCheckLine,
    iconClass: 'text-[#22C55E]',
    bgClass: 'bg-[#22C55E20]',
    textClass: 'text-[#22C55E]',
    label: '完成',
  },
  in_progress: {
    icon: RiLoader4Line,
    iconClass: 'text-[#F59E0B] animate-spin',
    bgClass: 'bg-[#F59E0B20]',
    textClass: 'text-[#F59E0B]',
    label: '进行中',
  },
  pending: {
    icon: RiCheckboxBlankCircleLine,
    iconClass: 'text-[--text-disabled]',
    bgClass: 'bg-transparent',
    textClass: 'text-[--text-tertiary]',
    label: '等待中',
  },
};

export function ProgressIndicator({
  steps,
  title = '执行进度',
  className,
}: ProgressIndicatorProps) {
  const completedCount = steps.filter(s => s.status === 'completed').length;
  const progress = steps.length > 0 ? completedCount / steps.length : 0;

  return (
    <div className={cn('bg-[--bg-primary] rounded-lg border border-[--border-subtle] overflow-hidden', className)}>
      {/* 头部 */}
      <div className="px-4 py-3 border-b border-[--border-subtle]">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-[--text-primary]">{title}</span>
          <span className="text-xs text-[--text-tertiary]">
            {completedCount}/{steps.length}
          </span>
        </div>
        
        {/* 总进度条 */}
        <div className="mt-2 h-1 bg-[--bg-tertiary] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-[#6366F1] to-[#8B5CF6] rounded-full transition-all duration-500 ease-out"
            style={{ width: `${progress * 100}%` }}
          />
        </div>
      </div>

      {/* 步骤列表 */}
      <div className="p-2">
      {steps.map((step) => {
          const config = statusConfig[step.status];
          const Icon = config.icon;

          return (
            <div
              key={step.id}
              className={cn(
                'flex items-start gap-3 p-2 rounded-md transition-colors',
                step.status === 'in_progress' && 'bg-[--bg-tertiary]'
              )}
            >
              {/* 图标 */}
              <div
                className={cn(
                  'w-5 h-5 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5',
                  config.bgClass
                )}
              >
                <Icon className={cn('w-3 h-3', config.iconClass)} />
              </div>

              {/* 内容 */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className={cn('text-sm truncate', config.textClass)}>
                    {step.label}
                  </span>
                  <span className={cn('text-xs flex-shrink-0', config.textClass)}>
                    {config.label}
                  </span>
                </div>
                
                {step.description && (
                  <p className="text-xs text-[--text-tertiary] mt-0.5 truncate">
                    {step.description}
                  </p>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// 简化版进度指示器（用于嵌入 TPAORCard）
interface MiniProgressIndicatorProps {
  steps: ProgressStep[];
  className?: string;
}

export function MiniProgressIndicator({ steps, className }: MiniProgressIndicatorProps) {
  return (
    <div className={cn('space-y-1.5', className)}>
      {steps.map((step) => {
        const config = statusConfig[step.status];
        const Icon = config.icon;

        return (
          <div key={step.id} className="flex items-center gap-2">
            <Icon className={cn('w-3.5 h-3.5', config.iconClass)} />
            <span className={cn('text-xs', config.textClass)}>
              {step.label}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default ProgressIndicator;
