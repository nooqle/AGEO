'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiCheckboxCircleLine, RiArrowDownSLine, RiLoader4Line } from '@remixicon/react';
import { cn } from '@/lib/cn';

interface PlanCardProps {
  planText: string;
  isActive: boolean;
}

export function PlanCard({ planText, isActive }: PlanCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-1"
    >
      {/* Header row — no border box, just an inline row */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 group cursor-pointer"
      >
        {isActive ? (
          <RiLoader4Line className="w-3.5 h-3.5 text-indigo-400 animate-spin flex-shrink-0" />
        ) : (
          <RiCheckboxCircleLine className="w-3.5 h-3.5 text-emerald-400 flex-shrink-0" />
        )}
        <span className={cn(
          'text-xs font-medium transition-colors',
          isActive ? 'text-indigo-300' : 'text-[--text-tertiary]',
          'group-hover:text-[--text-secondary]'
        )}>
          {isActive ? '正在制定计划...' : '执行计划'}
        </span>
        {isActive && (
          <span className="relative flex h-1.5 w-1.5 flex-shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-60" />
            <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-indigo-500" />
          </span>
        )}
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="text-[--text-tertiary] opacity-0 group-hover:opacity-100 transition-opacity"
        >
          <RiArrowDownSLine className="w-3 h-3" />
        </motion.div>
      </button>

      {/* Expanded content — left-border accent, no full box */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="ml-[22px] pl-3 border-l-2 border-[--border-default]">
              <p className="text-xs text-[--text-secondary] leading-relaxed whitespace-pre-wrap py-0.5">
                {planText}
              </p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
