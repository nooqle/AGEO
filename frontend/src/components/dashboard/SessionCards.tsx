'use client';

import { motion } from 'framer-motion';
import { SessionCard } from './SessionCard';
import type { SessionListItem } from '@/types/session';

interface SessionCardsProps {
  sessions: SessionListItem[];
  isLoading: boolean;
  maxItems?: number;
}

const containerVariants = {
  hidden: {},
  show: {
    transition: { staggerChildren: 0.06 },
  },
};

const itemVariants = {
  hidden: { opacity: 0, x: 20 },
  show: { opacity: 1, x: 0, transition: { duration: 0.3 } },
};

function SkeletonCard() {
  return (
    <div
      className="w-[280px] flex-shrink-0 card-modern snap-start animate-pulse"
      style={{ padding: 'var(--space-lg)' }}
    >
      <div className="h-4 rounded" style={{ background: 'var(--bg-elevated)', width: '60%' }} />
      <div className="h-3 rounded mt-3" style={{ background: 'var(--bg-elevated)', width: '90%' }} />
      <div className="h-3 rounded mt-3" style={{ background: 'var(--bg-elevated)', width: '40%' }} />
    </div>
  );
}

export function SessionCards({ sessions, isLoading, maxItems = 8 }: SessionCardsProps) {
  if (!isLoading && sessions.length === 0) return null;

  const displayed = sessions.slice(0, maxItems);

  return (
    <div>
      {/* Section header */}
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
          最近分析
        </h2>
        {sessions.length > maxItems && (
          <button
            className="text-xs font-medium cursor-pointer hover:opacity-80 transition-opacity"
            style={{ color: 'var(--color-primary)' }}
          >
            查看全部
          </button>
        )}
      </div>

      {/* Horizontal scroll */}
      {isLoading ? (
        <div className="flex overflow-x-auto snap-x snap-mandatory gap-4 pb-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : (
        <motion.div
          className="flex overflow-x-auto snap-x snap-mandatory gap-4 pb-2"
          variants={containerVariants}
          initial="hidden"
          animate="show"
        >
          {displayed.map((session) => (
            <motion.div key={session.id} variants={itemVariants}>
              <SessionCard session={session} />
            </motion.div>
          ))}
        </motion.div>
      )}
    </div>
  );
}
