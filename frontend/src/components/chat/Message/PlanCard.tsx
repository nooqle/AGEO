'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RiListCheck3, RiArrowDownSLine } from '@remixicon/react';
import { cn } from '@/lib/cn';

interface PlanCardProps {
  planText: string;
  isActive: boolean;
}

export function PlanCard({ planText, isActive }: PlanCardProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      className={cn(
        'rounded-xl border p-3 transition-all',
        isActive
          ? 'border-indigo-500/30 bg-indigo-500/5'
          : 'border-[--border-default] bg-[--bg-secondary]'
      )}
    >
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 w-full text-left"
      >
        <div className={cn(
          'p-1 rounded-md',
          isActive ? 'bg-indigo-500/10 text-indigo-400' : 'bg-[--bg-tertiary] text-[--text-secondary]'
        )}>
          <RiListCheck3 className="w-3.5 h-3.5" />
        </div>
        <span className={cn(
          'text-xs font-medium flex-1',
          isActive ? 'text-indigo-300' : 'text-[--text-secondary]'
        )}>
          {isActive ? '执行计划' : '计划'}
        </span>
        {isActive && (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-indigo-500" />
          </span>
        )}
        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
        >
          <RiArrowDownSLine className="w-3.5 h-3.5 text-[--text-tertiary]" />
        </motion.div>
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <p className="text-sm text-[--text-primary] mt-2 leading-relaxed whitespace-pre-wrap">
              {planText}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}
