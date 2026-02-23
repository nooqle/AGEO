'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RiArrowDownSLine,
  RiCheckLine,
  RiLoader4Line,
  RiSearchLine,
  RiBrainLine,
  RiGlobalLine,
  RiCodeLine,
} from '@remixicon/react';
import { ActionLogEntry } from '@/types/message';
import { cn } from '@/lib/cn';

interface ActionLogProps {
  logs: ActionLogEntry[];
  isExpanded?: boolean;
}

const ACTION_ICONS: Record<string, React.ReactNode> = {
  agent_call: <RiBrainLine className="w-3 h-3" />,
  llm_call:   <RiBrainLine className="w-3 h-3" />,
  search:     <RiSearchLine className="w-3 h-3" />,
  browser:    <RiGlobalLine className="w-3 h-3" />,
  parse:      <RiCodeLine className="w-3 h-3" />,
  generic:    <RiCodeLine className="w-3 h-3" />,
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
      className="space-y-1"
    >
      {/* Summary row — no outer border box */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 group cursor-pointer"
      >
        {!isAllComplete ? (
          <RiLoader4Line className="w-3.5 h-3.5 text-indigo-400 animate-spin flex-shrink-0" />
        ) : (
          <RiCheckLine className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
        )}

        <span className="text-xs text-[--text-tertiary] flex-1 truncate max-w-xs group-hover:text-[--text-secondary] transition-colors">
          {isAllComplete
            ? `执行了 ${logs.length} 个步骤`
            : (latestLog?.message || '执行中...')}
        </span>

        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiArrowDownSLine className="w-3 h-3 text-[--text-tertiary]" />
        </motion.div>
      </button>

      {/* Expanded log entries — left-border, no outer box */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="ml-[22px] pl-3 border-l-2 border-[--border-default] space-y-1.5 py-1">
              {logs.map((log, index) => (
                <motion.div
                  key={log.id}
                  initial={{ opacity: 0, x: -6 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.04 }}
                  className="flex items-start gap-1.5"
                >
                  <div className={cn(
                    'mt-0.5 flex-shrink-0 transition-colors',
                    log.isComplete ? 'text-emerald-400' : 'text-[--text-tertiary]'
                  )}>
                    {log.isComplete
                      ? <RiCheckLine className="w-3 h-3" />
                      : (ACTION_ICONS[log.actionType] || ACTION_ICONS.generic)
                    }
                  </div>
                  <span className={cn(
                    'text-xs leading-relaxed',
                    log.isComplete ? 'text-[--text-tertiary]' : 'text-[--text-secondary]'
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
