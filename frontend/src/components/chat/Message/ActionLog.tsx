'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiArrowDownSLine, RiCheckLine, RiLoader4Line, RiSearchLine, RiBrainLine, RiGlobalLine, RiCodeLine } from '@remixicon/react';
import { ActionLogEntry } from '@/types/message';
import { cn } from '@/lib/cn';

interface ActionLogProps {
  logs: ActionLogEntry[];
  isExpanded?: boolean;
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  agent_call: <RiBrainLine className="w-3 h-3" />,
  llm_call: <RiBrainLine className="w-3 h-3" />,
  search: <RiSearchLine className="w-3 h-3" />,
  browser: <RiGlobalLine className="w-3 h-3" />,
  parse: <RiCodeLine className="w-3 h-3" />,
  generic: <RiCodeLine className="w-3 h-3" />,
};

export function ActionLog({ logs, isExpanded: defaultExpanded = false }: ActionLogProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  if (logs.length === 0) return null;

  const completedCount = logs.filter((l) => l.isComplete).length;
  const isAllComplete = completedCount === logs.length;
  const latestLog = logs[logs.length - 1];

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-xl border border-[--border-default] bg-[--bg-secondary] overflow-hidden"
    >
      {/* Summary bar */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-[--bg-tertiary] transition-colors"
      >
        {!isAllComplete ? (
          <RiLoader4Line className="w-3.5 h-3.5 text-indigo-400 animate-spin flex-shrink-0" />
        ) : (
          <RiCheckLine className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
        )}
        <span className="text-xs text-[--text-secondary] flex-1 truncate">
          {isAllComplete
            ? `执行了 ${logs.length} 个步骤`
            : latestLog?.message || '执行中...'}
        </span>
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <RiArrowDownSLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
        </motion.div>
      </button>

      {/* Expanded log list */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: 'auto' }}
            exit={{ height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t border-[--border-default] px-3 py-2 space-y-1.5">
              {logs.map((log, index) => (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -8 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05 }}
                  className="flex items-start gap-2"
                >
                  <div className={cn(
                    'mt-0.5 flex-shrink-0',
                    log.isComplete ? 'text-emerald-400' : 'text-[--text-tertiary]'
                  )}>
                    {log.isComplete ? (
                      <RiCheckLine className="w-3 h-3" />
                    ) : (
                      ACTION_ICONS[log.actionType] || ACTION_ICONS.generic
                    )}
                  </div>
                  <span className={cn(
                    'text-xs leading-relaxed',
                    log.isComplete ? 'text-[--text-secondary]' : 'text-[--text-primary]'
                  )}>
                    {log.message}
                  </span>
                </motion.div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
