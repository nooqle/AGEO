'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiArrowDownSLine, RiPlayLine, RiCheckLine, RiCloseLine, RiLoader4Line, RiTimeLine, RiErrorWarningLine, RiTerminalLine } from '@remixicon/react';
import { ExecutionStep, ExecutionStepStatus } from '@/types/message';
import { cn } from '@/lib/cn';
import { formatTime } from '@/lib/utils';
import { stepMessageVariants } from '@/lib/animations';

interface ExecutionStepMessageProps {
  step: ExecutionStep;
  onContinue?: () => void;
  onSkip?: () => void;
  onRetry?: () => void;
}

const statusConfig: Record<ExecutionStepStatus, { icon: React.ReactNode; label: string; color: string; bgColor: string }> = {
  pending: {
    icon: <RiTimeLine className="w-4 h-4" />,
    label: '等待中',
    color: 'text-[var(--text-disabled)]',
    bgColor: 'bg-[var(--bg-tertiary)]',
  },
  running: {
    icon: <RiLoader4Line className="w-4 h-4 animate-spin" />,
    label: '执行中',
    color: 'text-indigo-400',
    bgColor: 'bg-indigo-500/10',
  },
  completed: {
    icon: <RiCheckLine className="w-4 h-4" />,
    label: '已完成',
    color: 'text-green-400',
    bgColor: 'bg-green-500/10',
  },
  failed: {
    icon: <RiCloseLine className="w-4 h-4" />,
    label: '失败',
    color: 'text-red-400',
    bgColor: 'bg-red-500/10',
  },
  waiting_confirmation: {
    icon: <RiTimeLine className="w-4 h-4" />,
    label: '等待确认',
    color: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
  },
};

export function ExecutionStepMessage({
  step,
  onContinue,
  onSkip,
  onRetry,
}: ExecutionStepMessageProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const status = statusConfig[step.status];

  const toggleExpand = () => setIsExpanded(!isExpanded);

  return (
    <motion.div 
      className="flex gap-3 max-w-[90%]"
      variants={stepMessageVariants}
      initial="hidden"
      animate="visible"
      exit="exit"
    >
      {/* 步骤图标 */}
      <div className="flex-shrink-0">
        <motion.div 
          className={cn(
            'w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium',
            status.bgColor,
            status.color
          )}
          initial={{ scale: 0 }}
          animate={{ scale: 1 }}
          transition={{ type: 'spring', stiffness: 500, damping: 30 }}
        >
          {step.stepIndex}
        </motion.div>
      </div>

      {/* 内容 */}
      <div className="flex-1 min-w-0">
        {/* 头部 - 始终显示 */}
        <motion.div
          className={cn(
            'rounded-xl border overflow-hidden transition-all',
            step.status === 'running' && 'border-indigo-500/30 shadow-sm',
            step.status === 'waiting_confirmation' && 'border-amber-500/30 shadow-sm',
            step.status === 'completed' && 'border-green-500/30',
            step.status === 'failed' && 'border-red-500/30',
            'bg-[var(--bg-elevated)]'
          )}
          initial={{ opacity: 0, y: 5 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          {/* 标题栏 */}
          <button
            onClick={toggleExpand}
            className={cn(
              'w-full px-4 py-3 flex items-center justify-between transition-colors',
              'hover:bg-[var(--bg-tertiary)]'
            )}
          >
            <div className="flex items-center gap-3">
              <span className={cn('flex items-center gap-1.5 text-sm font-medium', status.color)}>
                {status.icon}
                <span>{status.label}</span>
              </span>
              <span className="text-sm font-medium text-[var(--text-primary)]">{step.stepName}</span>
              <span className="text-xs text-[var(--text-disabled)]">
                ({step.stepIndex}/{step.totalSteps})
              </span>
            </div>
            <div className="flex items-center gap-2">
              {step.startTime && (
                <span className="text-xs text-[var(--text-disabled)]">
                  {formatTime(step.startTime)}
                </span>
              )}
              <motion.div
                animate={{ rotate: isExpanded ? 180 : 0 }}
                transition={{ duration: 0.2 }}
              >
                <RiArrowDownSLine className="w-4 h-4 text-[var(--text-disabled)]" />
              </motion.div>
            </div>
          </button>

          {/* 展开内容 */}
          <AnimatePresence>
            {isExpanded && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: 'auto', opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.25, ease: 'easeInOut' }}
                className="border-t border-[var(--border-subtle)]"
              >
                <div className="p-4 space-y-3">
                  {/* 描述 */}
                  {step.description && (
                    <motion.p
                      className="text-sm text-[var(--text-secondary)]"
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      transition={{ delay: 0.1 }}
                    >
                      {step.description}
                    </motion.p>
                  )}

                  {/* 执行日志 */}
                  {step.logs && step.logs.length > 0 && (
                    <motion.div 
                      className="bg-gray-900 rounded-lg p-3 font-mono text-xs text-gray-300 max-h-48 overflow-y-auto"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.15 }}
                    >
                      <div className="flex items-center gap-2 mb-2 text-gray-500 border-b border-gray-700 pb-2">
                        <RiTerminalLine className="w-3 h-3" />
                        <span className="text-xs">执行日志</span>
                      </div>
                      {step.logs.map((log, index) => (
                        <motion.div 
                          key={index} 
                          className="py-0.5"
                          initial={{ opacity: 0, x: -5 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: index * 0.05 }}
                        >
                          <span className="text-gray-500">[{formatTime(new Date())}]</span>{' '}
                          <span className="text-green-400">$</span> {log}
                        </motion.div>
                      ))}
                    </motion.div>
                  )}

                  {/* 执行结果摘要 */}
                  {step.result && (
                    <motion.div 
                      className="bg-[var(--bg-tertiary)] rounded-lg p-3 border border-[var(--border-subtle)]"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.2 }}
                    >
                      <div className="text-xs font-medium text-[var(--text-tertiary)] mb-1">执行结果</div>
                      <div className="text-sm text-[var(--text-primary)]">
                        {typeof step.result === 'string'
                          ? step.result
                          : JSON.stringify(step.result, null, 2)}
                      </div>
                    </motion.div>
                  )}

                  {/* 等待确认时的操作按钮 */}
                  {step.status === 'waiting_confirmation' && (
                    <motion.div 
                      className="flex items-center gap-2 pt-2"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.25 }}
                    >
                      <motion.button
                        onClick={onContinue}
                        className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white text-sm font-medium rounded-lg hover:bg-indigo-700 transition-colors"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <RiPlayLine className="w-4 h-4" />
                        继续下一步
                      </motion.button>
                      <motion.button
                        onClick={onSkip}
                        className="px-4 py-2 text-[var(--text-secondary)] text-sm font-medium hover:text-[var(--text-primary)] transition-colors"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        跳过此步
                      </motion.button>
                    </motion.div>
                  )}

                  {/* 失败时的重试按钮 */}
                  {step.status === 'failed' && (
                    <motion.div 
                      className="flex items-center gap-2 pt-2"
                      initial={{ opacity: 0, y: 5 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.25 }}
                    >
                      <motion.button
                        onClick={onRetry}
                        className="flex items-center gap-1.5 px-4 py-2 text-amber-600 text-sm font-medium hover:text-amber-700 transition-colors"
                        whileHover={{ scale: 1.02 }}
                        whileTap={{ scale: 0.98 }}
                      >
                        <RiErrorWarningLine className="w-4 h-4" />
                        重试
                      </motion.button>
                    </motion.div>
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      </div>
    </motion.div>
  );
}
